"""Passos de instalação que rodam igual em Windows, Mac e Linux.

O install.sh e o install.ps1 cuidam do que é do sistema (uv, FFmpeg, Deno,
Node.js) e chamam estes comandos para o resto:

  clipator preparar          baixa o modelo de transcrição, o de rosto e o Chrome do HyperFrames
  clipator mcp registrar     registra o MCP no Claude Code e no Codex
  clipator desinstalar       desfaz tudo isso, sem tocar no workspace
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]
SECAO_CODEX = "[mcp_servers.clipator]"


def executavel_clipator() -> str:
    """Caminho absoluto do `clipator` em uso (o MCP precisa dele, não do PATH do terminal)."""
    achado = shutil.which("clipator")
    if achado:
        return achado
    arg0 = Path(sys.argv[0])
    if arg0.name.startswith("clipator") and arg0.exists():
        return str(arg0.resolve())
    return "clipator"


# ---- preparar ---------------------------------------------------------------
def preparar(log: Log = print, whisper: bool = True, rosto: bool = True, navegador: bool = True,
             modelo: str = "auto", dispositivo: str = "auto", stickers: bool = True) -> list[str]:
    """Baixa o que o motor precisa para funcionar offline. Devolve os erros (vazio = tudo certo)."""
    erros: list[str] = []
    if stickers:
        from . import stickers as _stk

        log("Baixando os stickers do editor (Fluent Emoji, MIT)…")
        try:
            r = _stk.instalar(lambda f, m: None)
            erros += r["erros"]
            log(f"Stickers: {r['instalados']} de {r['total']} prontos em {r['pasta']}.")
        except Exception as exc:  # noqa: BLE001
            erros.append(f"stickers: {exc}")
    if whisper:
        from .transcribe import escolher_modelo

        modelo, dispositivo, _ = escolher_modelo(modelo, dispositivo)
        log(f"Baixando o modelo de transcrição '{modelo}' ({dispositivo})…")
        try:
            from faster_whisper import download_model

            download_model(modelo)  # mesmo cache que o WhisperModel usa na transcrição
        except Exception as exc:
            erros.append(f"modelo de transcrição: {exc}")
    if rosto:
        log("Baixando o modelo de detecção de rosto…")
        try:
            from .reframe import detector

            if detector().nome not in ("yunet", "mediapipe"):
                erros.append("detecção de rosto: YuNet e MediaPipe indisponíveis (o reenquadramento usa o OpenCV ou o centro)")
        except Exception as exc:
            erros.append(f"detecção de rosto: {exc}")
    if navegador:
        from . import hyperframes

        cmd = hyperframes.comando()
        if cmd:
            log("Preparando o Chrome do HyperFrames…")
            try:
                r = subprocess.run([*cmd, "browser", "ensure"], capture_output=True, text=True, timeout=900,
                                   env=hyperframes._env())
                if r.returncode != 0:
                    erros.append("Chrome do HyperFrames: " + (r.stderr or r.stdout).strip()[-300:])
            except Exception as exc:
                erros.append(f"Chrome do HyperFrames: {exc}")
        else:
            log("HyperFrames não instalado: os estilos animados vão usar a legenda simples.")
    return erros


# ---- MCP no Claude Code e no Codex ------------------------------------------
def _config_codex() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _sem_secao_codex(texto: str) -> str:
    """Tira a seção [mcp_servers.clipator] (e subtabelas dela) de um config.toml."""
    out, dentro = [], False
    for linha in texto.splitlines(keepends=True):
        cab = re.match(r"^\s*\[\s*([^\]]+?)\s*\]\s*$", linha)
        if cab:
            nome = cab.group(1).replace('"', "")
            dentro = nome == "mcp_servers.clipator" or nome.startswith("mcp_servers.clipator.")
        if not dentro:
            out.append(linha)
    return "".join(out)


def _args_mcp(workspace: str | None) -> list[str]:
    return ["-w", str(Path(workspace).expanduser().resolve()), "mcp"] if workspace else ["mcp"]


def registrar_codex(clipator: str | None = None, workspace: str | None = None) -> Path:
    cfg = _config_codex()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    texto = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    texto = _sem_secao_codex(texto).rstrip()
    args = ", ".join(_toml_str(a) for a in _args_mcp(workspace))
    bloco = f"{SECAO_CODEX}\ncommand = {_toml_str(clipator or executavel_clipator())}\nargs = [{args}]\n"
    cfg.write_text((texto + "\n\n" if texto else "") + bloco, encoding="utf-8")
    return cfg


def remover_codex() -> bool:
    cfg = _config_codex()
    if not cfg.exists():
        return False
    antes = cfg.read_text(encoding="utf-8")
    depois = _sem_secao_codex(antes)
    if depois != antes:
        cfg.write_text(depois.rstrip() + "\n", encoding="utf-8")
        return True
    return False


def _claude() -> str | None:
    return shutil.which(os.environ.get("CLIPATOR_CLAUDE", "claude"))


def registrar_claude(clipator: str | None = None, workspace: str | None = None) -> bool:
    claude = _claude()
    if not claude:
        return False
    subprocess.run([claude, "mcp", "remove", "-s", "user", "clipator"], capture_output=True, text=True, timeout=60)
    r = subprocess.run([claude, "mcp", "add", "-s", "user", "clipator", "--", clipator or executavel_clipator(),
                        *_args_mcp(workspace)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or "claude mcp add falhou")
    return True


def remover_claude() -> bool:
    claude = _claude()
    if not claude:
        return False
    r = subprocess.run([claude, "mcp", "remove", "-s", "user", "clipator"], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def registrar_mcp(log: Log = print, workspace: str | None = None) -> list[str]:
    erros = []
    exe = executavel_clipator()
    try:
        if registrar_claude(exe, workspace):
            log("MCP registrado no Claude Code (escopo do usuário).")
        else:
            log("Claude Code não encontrado: pulei o registro nele.")
    except Exception as exc:
        erros.append(f"Claude Code: {exc}")
    if shutil.which(os.environ.get("CLIPATOR_CODEX", "codex")) or _config_codex().parent.exists():
        try:
            log(f"MCP registrado no Codex em {registrar_codex(exe, workspace)}.")
        except Exception as exc:
            erros.append(f"Codex: {exc}")
    else:
        log("Codex não encontrado: pulei o registro nele.")
    return erros


def remover_mcp(log: Log = print) -> None:
    if remover_claude():
        log("MCP removido do Claude Code.")
    if remover_codex():
        log("MCP removido do Codex.")


# ---- desinstalar --------------------------------------------------------------
def desinstalar(log: Log = print, apagar_modelos: bool = False) -> None:
    """Remove registros e componentes do Clipator. O workspace (vídeos, canais, clips) fica."""
    remover_mcp(log)
    base = Path.home() / ".clipator"
    alvos = [base / "hyperframes", base / "node"]
    if apagar_modelos:
        alvos.append(base / "modelos")
    for p in alvos:
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
            log(f"Removido: {p}")
    log("Para tirar o próprio comando: uv tool uninstall clipator")
    log("Seu workspace e as skills em ~/.clipator/skills ficaram onde estavam.")
