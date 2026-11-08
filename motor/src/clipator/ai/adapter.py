"""Adaptador único de IA: run_json(prompt, schema) -> dict.

Claude: `claude -p --output-format json --json-schema ... --tools ""`, sem
`--bare`, para usar a assinatura do usuário (o modo --bare exige
ANTHROPIC_API_KEY). Codex: `codex exec --output-schema arquivo -o saida -`,
que reaproveita o login salvo do Codex.

O parser tolerante de JSON foi adaptado de
AI-Youtube-Shorts-Generator/shorts_generator/highlights.py (_parse_json_loose),
MIT License, Copyright (c) 2026 Anil Chandra Naidu Matcha. Ver
THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..media import Cancelado, matar_arvore


class ErroIA(RuntimeError):
    pass


class ErroLoginIA(ErroIA):
    """A CLI está instalada, mas sem login (ou com o login expirado)."""


_SEM_LOGIN = re.compile(r"failed to authenticate|oauth|not logged in|authentication|unauthori[sz]ed|\b401\b|/login",
                        re.IGNORECASE)
_DICA_LOGIN = {
    "claude": "O login do Claude Code expirou. Rode claude no terminal e faça /login, ou escolha o Codex em Configurações.",
    "codex": "O Codex está sem login. Rode codex login no terminal, ou escolha o Claude em Configurações.",
}


def _checar_login(nome: str, texto: str) -> None:
    if _SEM_LOGIN.search(texto or ""):
        raise ErroLoginIA(f"{_DICA_LOGIN.get(nome, 'A IA está sem login.')} ({(texto or '').strip()[:300]})")


def parse_json_loose(texto: str) -> Any:
    """Aceita JSON puro, dentro de ```json``` ou cercado de texto."""
    texto = (texto or "").strip()
    if not texto:
        raise ErroIA("Resposta vazia da IA")
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(.*?)```", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for abre, fecha in (("{", "}"), ("[", "]")):
        i, j = texto.find(abre), texto.rfind(fecha)
        if i != -1 and j > i:
            try:
                return json.loads(texto[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise ErroIA("A IA não devolveu JSON válido")


AoEvento = Callable[[str, str], None]  # (tipo, texto): "texto", "pensando" ou "aviso"


def _rodar_linhas(cmd: list[str], entrada: str, timeout: int, cancelar: threading.Event | None, ao_linha: Callable[[str], None],
                  cwd: str | None = None, nome: str = "") -> str:
    """Como `_rodar`, mas lê a saída linha a linha (a CLI em modo streaming) e passa cada linha para `ao_linha`."""
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", cwd=cwd)
    except FileNotFoundError as exc:
        raise ErroIA(f"{cmd[0]} não encontrado. Instale e faça login, ou desligue a IA.") from exc
    linhas: list[str] = []
    erro: list[str] = []

    def ler() -> None:
        assert proc.stdout is not None
        for linha in proc.stdout:
            linhas.append(linha)
            try:
                ao_linha(linha)
            except Exception:  # noqa: BLE001 - o relato nunca derruba a chamada
                pass

    def ler_erro() -> None:
        assert proc.stderr is not None
        erro.append(proc.stderr.read())

    def escrever() -> None:
        try:
            assert proc.stdin is not None
            proc.stdin.write(entrada)
            proc.stdin.close()
        except OSError:
            pass

    ts = [threading.Thread(target=f, daemon=True) for f in (ler, ler_erro, escrever)]
    for t in ts:
        t.start()
    esperado = 0.0
    while proc.poll() is None:
        time.sleep(0.25)
        esperado += 0.25
        if cancelar is not None and cancelar.is_set():
            matar_arvore(proc)  # o claude/codex do npm é um .cmd: mata o node que ele abriu também
            raise Cancelado()
        if esperado > timeout:
            matar_arvore(proc)  # o claude/codex do npm é um .cmd: mata o node que ele abriu também
            raise ErroIA(f"{cmd[0]} passou de {timeout} s sem responder")
    for t in ts[:2]:
        t.join(5)
    out = "".join(linhas)
    if proc.returncode != 0:
        err = ("".join(erro) or out).strip()[-800:]
        _checar_login(nome, err)
        if "login" in err.lower() or "auth" in err.lower():
            err += " (faça login na CLI e tente de novo)"
        raise ErroIA(f"{cmd[0]} falhou: {err}")
    return out


def _opcao_desconhecida(exc: Exception) -> bool:
    """A CLI instalada é antiga e não conhece a opção de streaming?"""
    t = str(exc).lower()
    return any(x in t for x in ("unknown option", "unexpected argument", "unrecognized", "unknown argument", "não reconhec"))


def _rodar(cmd: list[str], entrada: str, timeout: int, cancelar: threading.Event | None, cwd: str | None = None,
           nome: str = "") -> str:
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace", cwd=cwd)
    except FileNotFoundError as exc:
        raise ErroIA(f"{cmd[0]} não encontrado. Instale e faça login, ou desligue a IA.") from exc
    resultado: dict[str, str] = {}

    def comunicar() -> None:
        out, err = proc.communicate(entrada)
        resultado["out"], resultado["err"] = out, err

    t = threading.Thread(target=comunicar, daemon=True)
    t.start()
    passo = 0.5
    esperado = 0.0
    while t.is_alive():
        t.join(passo)
        esperado += passo
        if cancelar is not None and cancelar.is_set():
            matar_arvore(proc)  # o claude/codex do npm é um .cmd: mata o node que ele abriu também
            raise Cancelado()
        if esperado > timeout:
            matar_arvore(proc)  # o claude/codex do npm é um .cmd: mata o node que ele abriu também
            raise ErroIA(f"{cmd[0]} passou de {timeout} s sem responder")
    if proc.returncode != 0:
        err = (resultado.get("err") or resultado.get("out") or "").strip()[-800:]
        _checar_login(nome, err)
        if "login" in err.lower() or "auth" in err.lower():
            err += " (faça login na CLI e tente de novo)"
        raise ErroIA(f"{cmd[0]} falhou: {err}")
    return resultado.get("out", "")


@dataclass
class AdapterIA:
    nome: str = "nenhum"
    timeout: int = 600

    def disponivel(self) -> bool:
        return False

    def run_json(self, prompt: str, schema: dict, cancelar: threading.Event | None = None,
                 ao_evento: AoEvento | None = None) -> Any:  # pragma: no cover
        raise ErroIA("IA desligada")


@dataclass
class ClaudeCLI(AdapterIA):
    nome: str = "claude"
    binario: str = "claude"
    modelo: str | None = None

    def disponivel(self) -> bool:
        return shutil.which(self.binario) is not None

    def run_json(self, prompt: str, schema: dict, cancelar: threading.Event | None = None,
                 ao_evento: AoEvento | None = None) -> Any:
        base = [self.binario, "-p", "--tools", "", "--no-session-persistence", "--json-schema", json.dumps(schema, ensure_ascii=False)]
        if self.modelo:
            base += ["--model", self.modelo]
        data: Any
        if ao_evento is not None:
            # streaming (stream-json): cada pedaço do que a IA escreve vira um evento; o evento "result" é a resposta
            final: dict[str, Any] = {}

            def linha(t: str) -> None:
                try:
                    ev = json.loads(t)
                except json.JSONDecodeError:
                    return
                if not isinstance(ev, dict):
                    return
                if ev.get("type") == "result":
                    final.update(ev)
                elif ev.get("type") == "stream_event":
                    d = (ev.get("event") or {}).get("delta") or {}
                    if d.get("type") == "text_delta" and d.get("text"):
                        ao_evento("texto", d["text"])
                    elif d.get("type") == "thinking_delta" and d.get("thinking"):
                        ao_evento("pensando", d["thinking"])
                    elif d.get("type") == "input_json_delta" and d.get("partial_json"):
                        ao_evento("texto", d["partial_json"])

            try:
                _rodar_linhas([*base, "--output-format", "stream-json", "--verbose", "--include-partial-messages"], prompt,
                              self.timeout, cancelar, linha, nome=self.nome)
            except ErroIA as exc:
                if not _opcao_desconhecida(exc):
                    raise
                ao_evento("aviso", "esta versão do Claude Code não manda o texto aos poucos: esperando a resposta inteira")
                return self.run_json(prompt, schema, cancelar)
            data = final
        else:
            out = _rodar([*base, "--output-format", "json"], prompt, self.timeout, cancelar, nome=self.nome)
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                return parse_json_loose(out)
        if isinstance(data, dict):
            if data.get("is_error"):
                _checar_login(self.nome, str(data.get("result")))
                raise ErroIA(f"Claude devolveu erro: {str(data.get('result'))[:500]}")
            if data.get("structured_output") is not None:
                return data["structured_output"]
            if "result" in data:
                return parse_json_loose(str(data["result"]))
        return data


@dataclass
class CodexCLI(AdapterIA):
    nome: str = "codex"
    binario: str = "codex"
    modelo: str | None = None

    def disponivel(self) -> bool:
        return shutil.which(self.binario) is not None

    def run_json(self, prompt: str, schema: dict, cancelar: threading.Event | None = None,
                 ao_evento: AoEvento | None = None) -> Any:
        with tempfile.TemporaryDirectory(prefix="clipator-codex-") as tmp:
            sch = Path(tmp) / "schema.json"
            sch.write_text(json.dumps(_schema_estrito(schema)), encoding="utf-8")
            saida = Path(tmp) / "saida.json"
            cmd = [self.binario, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                   "--output-schema", str(sch), "-o", str(saida)]
            if self.modelo:
                cmd += ["-m", self.modelo]
            cmd.append("-")
            if ao_evento is not None:
                def linha(t: str) -> None:  # exec --json: um evento JSON por linha (raciocínio e mensagens)
                    try:
                        ev = json.loads(t)
                    except json.JSONDecodeError:
                        return
                    item = (ev.get("item") or {}) if isinstance(ev, dict) else {}
                    txt = str(item.get("text") or "")
                    if ev.get("type") == "item.completed" and txt:
                        ao_evento("pensando" if (item.get("type") or item.get("item_type")) == "reasoning" else "texto", txt + "\n")

                try:
                    out = _rodar_linhas([*cmd[:-1], "--json", "-"], prompt, self.timeout, cancelar, linha, cwd=tmp, nome=self.nome)
                except ErroIA as exc:
                    if not _opcao_desconhecida(exc):
                        raise
                    ao_evento("aviso", "esta versão do Codex não manda o texto aos poucos: esperando a resposta inteira")
                    out = _rodar(cmd, prompt, self.timeout, cancelar, cwd=tmp, nome=self.nome)
            else:
                out = _rodar(cmd, prompt, self.timeout, cancelar, cwd=tmp, nome=self.nome)
            texto = saida.read_text(encoding="utf-8") if saida.exists() else out
            return parse_json_loose(texto)


def _schema_estrito(schema: Any) -> Any:
    """O Codex (Structured Outputs da OpenAI) exige additionalProperties: false e todos os campos em required."""
    if isinstance(schema, dict):
        s = {k: _schema_estrito(v) for k, v in schema.items()}
        if s.get("type") == "object" and "properties" in s:
            s.setdefault("additionalProperties", False)
            s["required"] = list(s["properties"].keys())
        return s
    if isinstance(schema, list):
        return [_schema_estrito(x) for x in schema]
    return schema


def adaptador(nome: str, timeout: int = 600) -> AdapterIA:
    if nome == "claude":
        return ClaudeCLI(timeout=timeout, binario=os.environ.get("CLIPATOR_CLAUDE", "claude"))
    if nome == "codex":
        return CodexCLI(timeout=timeout, binario=os.environ.get("CLIPATOR_CODEX", "codex"))
    return AdapterIA()


_NOMES = {"claude": "Claude", "codex": "Codex"}


class AdapterComReserva(AdapterIA):
    """Usa a IA configurada e, se ela não estiver instalada ou estiver sem login, a outra CLI.

    Só troca por falta de instalação ou de login; qualquer outro erro sobe como veio.
    """

    def __init__(self, principal: AdapterIA, reservas: list[str], timeout: int = 600,
                 log: Callable[[str], None] | None = None,
                 fabrica: Callable[[str, int], AdapterIA] | None = None,
                 logado: Callable[[str], bool | None] | None = None,
                 esperar_login: Callable[[str], bool] | None = None):
        """esperar_login(nome): pausa até o usuário entrar na CLI; True repete pela mesma IA."""
        super().__init__(nome=principal.nome, timeout=timeout)
        self.atual = principal
        self._reservas = [r for r in reservas if r != principal.nome]
        self._log = log or (lambda _l: None)
        self._fabrica = fabrica or adaptador
        self._logado = logado or logado_na_cli
        self._esperar_login = esperar_login

    def disponivel(self) -> bool:
        return self.atual.disponivel() or any(self._fabrica(r, self.timeout).disponivel() for r in self._reservas)

    def _trocar(self, motivo: str) -> bool:
        while self._reservas:
            nome = self._reservas.pop(0)
            alt = self._fabrica(nome, self.timeout)
            if alt.disponivel() and self._logado(nome) is not False:
                self._log(f"{_NOMES.get(self.atual.nome, self.atual.nome)} {motivo}; usando o {_NOMES.get(nome, nome)}")
                self.atual, self.nome = alt, alt.nome
                return True
        return False

    def run_json(self, prompt: str, schema: dict, cancelar: threading.Event | None = None,
                 ao_evento: AoEvento | None = None) -> Any:
        if not self.atual.disponivel() and not self._trocar("não instalado"):
            raise ErroIA(f"A IA '{self.atual.nome}' não está instalada. Instale e faça login, ou use o modo sem IA.")
        try:
            return _com_eventos(self.atual, prompt, schema, cancelar, ao_evento)
        except ErroLoginIA:
            if self._esperar_login is not None and self._esperar_login(self.atual.nome):
                esperou = True
            elif not self._trocar("sem login"):
                raise
            else:
                esperou = False
        if esperou:
            try:
                return _com_eventos(self.atual, prompt, schema, cancelar, ao_evento)
            except ErroLoginIA:
                if not self._trocar("continua sem login"):
                    raise
        return _com_eventos(self.atual, prompt, schema, cancelar, ao_evento)


def adaptador_com_reserva(nome: str, timeout: int = 600, log: Callable[[str], None] | None = None,
                          esperar_login: Callable[[str], bool] | None = None) -> AdapterIA:
    """A IA configurada com a outra CLI de reserva; com a IA desligada, devolve o adaptador nulo."""
    if nome not in _NOMES:
        return adaptador(nome, timeout)
    return AdapterComReserva(adaptador(nome, timeout), [n for n in _NOMES if n != nome], timeout, log,
                             esperar_login=esperar_login)


def _binario(nome: str) -> str | None:
    return shutil.which(os.environ.get(f"CLIPATOR_{nome.upper()}", nome))


def logado_na_cli(nome: str) -> bool | None:
    """Só o status do login (claude auth status / codex login status); None se não deu para saber."""
    exe = _binario(nome)
    if not exe:
        return False
    try:
        if nome == "claude":
            r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=20)
            return bool(json.loads(r.stdout or "{}").get("loggedIn")) if r.returncode == 0 else False
        if nome == "codex":
            r = subprocess.run([exe, "login", "status"], capture_output=True, text=True, timeout=20)
            return r.returncode == 0 and "not logged" not in (r.stdout + r.stderr).lower()
    except Exception:
        return None
    return None


def abrir_login(nome: str) -> None:
    """Abre o login da CLI numa janela de terminal visível; o usuário termina no navegador."""
    exe = _binario(nome)
    if not exe:
        raise ErroIA(f"{_NOMES.get(nome, nome)} não está instalado.")
    args = [exe, "auth", "login"] if nome == "claude" else [exe, "login"]
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", subprocess.list2cmdline(args) + " & pause"],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif sys.platform == "darwin":
        comando = " ".join(shlex.quote(a) for a in args)
        script = 'tell application "Terminal" to do script "' + comando.replace("\\", "\\\\").replace('"', '\\"') + '"'
        subprocess.Popen(["osascript", "-e", script])
    else:
        for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["konsole", "-e"], ["xterm", "-e"]):
            if shutil.which(term[0]):
                subprocess.Popen(term + args)
                return
        subprocess.Popen(args)  # sem terminal: a CLI abre o navegador sozinha


def _versao(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
    except Exception:
        return None


def detectar_agentes(checar_login: bool = True) -> dict[str, dict]:
    """O que está instalado e logado. A tela de Configurações usa isso."""
    out: dict[str, dict] = {}
    for nome in _NOMES:
        exe = _binario(nome)
        info: dict[str, Any] = {"instalado": bool(exe), "caminho": exe, "versao": None, "logado": None}
        if exe:
            info["versao"] = _versao([exe, "--version"])
            if checar_login:
                info["logado"] = logado_na_cli(nome)
        out[nome] = info
    return out


class CacheIA:
    """Respostas em cache pelo hash do prompt, do schema e do agente."""

    def __init__(self, pasta: Path):
        self.pasta = pasta

    def chave(self, agente: str, prompt: str, schema: dict) -> str:
        h = hashlib.sha256()
        h.update(agente.encode())
        h.update(prompt.encode())
        h.update(json.dumps(schema, sort_keys=True).encode())
        return h.hexdigest()[:24]

    def get(self, chave: str) -> Any:
        p = self.pasta / f"{chave}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def put(self, chave: str, valor: Any) -> None:
        self.pasta.mkdir(parents=True, exist_ok=True)
        (self.pasta / f"{chave}.json").write_text(json.dumps(valor, ensure_ascii=False, indent=1), encoding="utf-8")


def _com_eventos(adapter: Any, prompt: str, schema: dict, cancelar: threading.Event | None, ao_evento: AoEvento | None) -> Any:
    """Chama com `ao_evento` só se houver (adaptadores de fora, como os de teste, podem não aceitar)."""
    if ao_evento is None:
        return adapter.run_json(prompt, schema, cancelar)
    try:
        return adapter.run_json(prompt, schema, cancelar, ao_evento)
    except TypeError as exc:
        if "ao_evento" not in str(exc) and "positional argument" not in str(exc):
            raise
        return adapter.run_json(prompt, schema, cancelar)


def chamar(adapter: AdapterIA, prompt: str, schema: dict, cache: CacheIA | None = None,
           cancelar: threading.Event | None = None, ao_evento: AoEvento | None = None) -> Any:
    """`ao_evento(tipo, texto)` recebe o que a IA vai escrevendo (quando a CLI permite), para mostrar ao usuário."""
    chave = cache.chave(adapter.nome, prompt, schema) if cache else None
    if cache and chave:
        hit = cache.get(chave)
        if hit is not None:
            if ao_evento is not None:
                ao_evento("aviso", "pedido igual a um anterior: a resposta veio do cache, sem chamar a IA")
            return hit
    resp = _com_eventos(adapter, prompt, schema, cancelar, ao_evento)
    if cache and chave:
        cache.put(chave, resp)
    return resp
