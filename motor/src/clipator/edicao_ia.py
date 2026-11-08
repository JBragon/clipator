"""Editar um clip com o Claude Code ou o Codex do próprio usuário, numa conversa no terminal dele.

Isto fica FORA do núcleo: o motor não chama IA aqui. Ele só prepara a pasta e o pedido,
abre o terminal do usuário com a CLI interativa e depois lista o que ela gravou. A IA que o
motor usa por conta própria continua indo só pelo adaptador (texto entra, JSON sai).

Como funciona:
- cada pedido ganha uma pasta clips/<id>/edicoes/<data-hora>/ com pedido.md (contexto do clip,
  regras e o pedido do usuário). A IA grava ali o resultado (saida-editada.mp4) e notas.md;
- a CLI recebe só uma frase fixa mandando ler o pedido.md. O texto do usuário nunca passa
  por linha de comando nem por shell;
- o comando é uma lista de argumentos, sem shell e sem flags que pulem as permissões:
  quem aprova cada ação é o usuário, no terminal dele;
- "continuar" retoma a conversa mais recente feita na pasta do clip
  (claude --continue / codex resume --last, que filtra pela pasta);
- o pedido feito no passo 2 vira um lote: um pedido.md por clip e um edicoes-ia/<data-hora>/
  pedido-lote.md na pasta do projeto, com UMA conversa para todos os clips do render.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from . import plataformas
from .candidates import texto_do_trecho
from .models import PedidoIA
from .workspace import ProjetoWS

Agente = Literal["claude", "codex"]
Modo = Literal["abrir", "continuar"]
AGENTES: tuple[Agente, ...] = ("claude", "codex")
NOMES = {"claude": "Claude Code", "codex": "Codex"}
PASTA = "edicoes"
PASTA_LOTE = "edicoes-ia"
EXT_VIDEO = (".mp4", ".mov", ".webm", ".mkv")
SUGESTOES = [
    "Aplique a direção de arte do canal (cores, fonte e legenda do canal.md e do estilo).",
    "Adicione b-roll que ilustre o que é falado, só com mídia de uso livre e com os créditos no notas.md.",
    "Melhore o ritmo: tire pausas mortas e repetições sem cortar o sentido.",
    "Deixe os primeiros 3 segundos mais fortes para segurar quem está rolando o feed.",
]
FERRAMENTAS_MCP = ["ler_edicao", "aplicar_edicao", "ler_transcricao", "corrigir_transcricao", "listar_estilos", "criar_estilo", "ajustar_corte",
                   "renderizar", "status_job", "gerar_thumbnail", "listar_thumbnails", "escolher_thumbnail",
                   "sugerir_titulos", "listar_skills", "abrir_preview"]


def _binario(agente: str) -> str | None:
    return shutil.which(os.environ.get(f"CLIPATOR_{agente.upper()}", agente))


def mcp_registrado(agente: str) -> bool | None:
    """O MCP do Clipator está registrado nessa CLI? None se não deu para saber."""
    from .instalacao import SECAO_CODEX, _config_codex

    if agente == "codex":
        cfg = _config_codex()
        return cfg.exists() and SECAO_CODEX in cfg.read_text(encoding="utf-8", errors="replace")
    exe = _binario("claude")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "mcp", "get", "clipator"], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return None


def detectar(com_mcp: bool = True) -> dict[str, dict[str, Any]]:
    """`com_mcp=False` pula a pergunta à CLI do Claude, que leva segundos, e deixa "mcp" como None."""
    out = {}
    for a in AGENTES:
        exe = _binario(a)
        out[a] = {"nome": NOMES[a], "instalado": bool(exe), "mcp": (mcp_registrado(a) if com_mcp else None) if exe else False}
    return out


def registrar(agente: str) -> None:
    from .instalacao import executavel_clipator, registrar_claude, registrar_codex

    if agente == "claude":
        if not registrar_claude(executavel_clipator()):
            raise RuntimeError("Claude Code não encontrado.")
    elif agente == "codex":
        registrar_codex(executavel_clipator())
    else:
        raise ValueError(agente)


# ---- o pedido ----------------------------------------------------------------------

def _hms(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def montar_pedido(projeto: ProjetoWS, clip_id: str, pedido: str, agora: datetime | None = None) -> tuple[Path, str]:
    """Cria edicoes/<data-hora>/ e devolve (pasta, texto do pedido.md)."""
    clip, pasta = projeto.clip(clip_id)
    carimbo = (agora or datetime.now()).strftime("%Y%m%d-%H%M%S")
    destino = pasta / PASTA / carimbo
    destino.mkdir(parents=True, exist_ok=True)
    canal, canal_md = projeto.canal.info()
    _, regras_md = projeto.canal.regras()
    info = plataformas.info(clip.plataforma, clip.formato)
    z = info.zona
    video = projeto.video_path()
    trans = projeto.transcricao() or {}
    texto = texto_do_trecho(trans, clip.inicio, clip.fim) if trans else ""
    saida = pasta / "saida.mp4"
    srt = pasta / "legenda.srt"
    from .melhorar import pedido_para_conversa

    ficha = pedido_para_conversa(projeto, clip_id)  # o estilo do clip e como mudar a edição pelo MCP (vira versão)
    linhas = [
        f"# Pedido de edição: {clip.titulo or clip.id}",
        "",
        "## O que eu quero",
        pedido.strip() or "(sem pedido: proponha melhorias e espere eu aprovar)",
        "",
        "## Regras obrigatórias",
        "1. NUNCA altere, mova nem sobrescreva o vídeo original, o saida.mp4 nem os arquivos do projeto "
        "(clip.yaml, projeto.yaml, transcricao.json, candidatos.json, legenda.*). Só leia.",
        f"2. Grave tudo o que fizer nesta pasta: {destino}",
        "   - o vídeo final como saida-editada.mp4 (pode haver mais versões: saida-editada-2.mp4…);",
        "   - um notas.md dizendo o que fez, os comandos e ferramentas usados, os arquivos criados e o crédito "
        "e a licença de qualquer mídia de fora.",
        f"3. Mantenha o formato {clip.formato} (mesma largura e altura do saida.mp4) e a duração dentro do limite "
        f"do {info.nome}.",
        f"4. Texto e legenda fora da zona que o app cobre: {z.topo:.0%} de cima, {z.base:.0%} de baixo e "
        f"{z.direita:.0%} da direita (valores aproximados).",
        "5. Antes de baixar algo da internet, usar serviço pago ou apagar qualquer arquivo, me pergunte.",
        "6. Me diga o plano antes de começar e espere eu aprovar.",
        "",
        *([ficha] if ficha else []),
        "## O clip",
        f"- Vídeo renderizado: {saida if saida.exists() else '(ainda não renderizado: use o MCP renderizar)'}",
        f"- Vídeo original do projeto (só leitura): {video or '(sem vídeo)'}",
        f"- Trecho do original: {_hms(clip.inicio)} a {_hms(clip.fim)} ({clip.fim - clip.inicio:.1f} s)"
        + (f"; cortes internos: {', '.join(f'{_hms(a)}–{_hms(b)}' for a, b in clip.cortes_internos)}"
           if clip.cortes_internos else ""),
        f"- Legenda: {srt if srt.exists() else '(sem .srt ainda)'}",
        f"- Estilo: {clip.estilo} · formato {clip.formato} · plataforma {info.nome}",
        f"- Canal: {canal.nome} (pasta {projeto.canal.path})",
        "",
        "## Ferramentas do Clipator",
        "Se o servidor MCP \"clipator\" estiver disponível, use estas ferramentas em vez de mexer nos arquivos do "
        f"projeto: {', '.join(FERRAMENTAS_MCP)}. Canal: {projeto.canal.slug}; projeto: {projeto.id}; clip: {clip.id}.",
        "",
        "## Canal (canal.md)",
        canal_md.strip()[:2000] or "(sem descrição)",
        "",
        "## Regras do canal (regras.md)",
        regras_md.strip()[:2000] or "(sem regras)",
        "",
        "## Transcrição do trecho",
        texto[:12000] or "(sem transcrição)",
        "",
    ]
    conteudo = "\n".join(linhas)
    (destino / "pedido.md").write_text(conteudo, encoding="utf-8")
    return destino, conteudo


def frase_inicial(pasta_clip: Path, destino: Path, arquivo: str = "pedido.md") -> str:
    """O único texto que vai na linha de comando: fixo, sem nada digitado pelo usuário."""
    rel = destino.relative_to(pasta_clip).as_posix()
    return f"Leia o arquivo {rel}/{arquivo} e siga o que ele pede. Comece me mostrando o plano."


def comando(agente: str, modo: str, frase: str, exe: str | None = None) -> list[str]:
    """A CLI interativa com a frase inicial. Sem flags que pulem permissões."""
    exe = exe or _binario(agente)
    if not exe:
        raise RuntimeError(f"{NOMES.get(agente, agente)} não está instalado.")
    if agente == "claude":
        return [exe, "--continue", frase] if modo == "continuar" else [exe, frase]
    if agente == "codex":
        return [exe, "resume", "--last", frase] if modo == "continuar" else [exe, frase]
    raise ValueError(agente)


def lancador(args: list[str], pasta: Path, plataforma: str = sys.platform) -> tuple[list[str], dict[str, Any]]:
    """Como abrir uma janela de terminal com `args` na pasta do clip. Devolve (comando, opções do Popen).

    No Windows, a própria CLI abre num console novo (sem cmd /c nem start, então nada é
    interpretado por shell). No Mac, o Terminal recebe o comando com cada argumento entre aspas
    (shlex.quote). No Linux, o emulador de terminal recebe a lista de argumentos.
    """
    if plataforma == "win32":
        # Sem redirecionar stdin/stdout/stderr: com qualquer um redirecionado, o Windows passa os
        # handles do motor (pipes, no app) para a CLI, que desenha a tela no pipe e o console fica preto.
        wt = None if os.environ.get("CLIPATOR_TERMINAL") == "conhost" else shutil.which("wt")
        if wt:  # Windows Terminal; ";" separa comandos para o wt, então vai escapado
            return [wt, "-w", "new", "new-tab", "--title", "Clipator", "-d", str(pasta),
                    *(a.replace(";", "\\;") for a in args)], {"cwd": str(pasta)}
        return args, {"cwd": str(pasta), "creationflags": getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)}
    if plataforma == "darwin":
        linha = f"cd {shlex.quote(str(pasta))} && " + " ".join(shlex.quote(a) for a in args)
        script = 'tell application "Terminal" to do script ' + _applescript_str(linha)
        return ["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'], {"stdin": subprocess.DEVNULL}
    for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["konsole", "-e"], ["xterm", "-e"]):
        if shutil.which(term[0]):
            return [*term, *args], {"cwd": str(pasta), "stdin": subprocess.DEVNULL}
    raise RuntimeError("Não achei um terminal (x-terminal-emulator, gnome-terminal, konsole ou xterm).")


def _applescript_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def abrir(projeto: ProjetoWS, clip_id: str, agente: str, modo: str, pedido: str, lancar: bool = True) -> dict[str, Any]:
    """Escreve o pedido e abre a conversa no terminal do usuário.

    Com `lancar=False` só prepara: devolve a pasta (`cwd`) e a frase fixa para o app abrir a CLI no
    terminal embutido dele (que monta o mesmo comando de `comando()`).
    """
    _, pasta = projeto.clip(clip_id)
    destino, _ = montar_pedido(projeto, clip_id, pedido)
    frase = frase_inicial(pasta, destino)
    if lancar:
        _lancar(comando(agente, modo, frase), pasta)
    return {"pasta": str(destino), "agente": agente, "modo": modo, "cwd": str(pasta), "frase": frase}


def _lancar(args: list[str], pasta: Path) -> None:
    cmd, opcoes = lancador(args, pasta)
    try:
        subprocess.Popen(cmd, **opcoes)  # noqa: S603 - lista de argumentos, sem shell
    except OSError as exc:
        raise RuntimeError(f"Não consegui abrir o terminal ({Path(cmd[0]).name}): {exc}") from exc


# ---- lote: o pedido feito no passo 2, aberto quando o render termina --------------------
def montar_lote(projeto: ProjetoWS, clip_ids: list[str], agora: datetime | None = None) -> tuple[Path, str]:
    """Um pedido.md por clip (com o texto guardado em clip.pedido_ia) e o pedido-lote.md do projeto."""
    agora = agora or datetime.now()
    carimbo = agora.strftime("%Y%m%d-%H%M%S")
    destino = projeto.path / PASTA_LOTE / carimbo
    destino.mkdir(parents=True, exist_ok=True)

    def rel(x: Path) -> str:
        return x.relative_to(projeto.path).as_posix()

    itens = []
    for cid in clip_ids:
        clip, pasta = projeto.clip(cid)
        texto = clip.pedido_ia.texto if clip.pedido_ia else ""
        dest_clip, _ = montar_pedido(projeto, cid, texto, agora)
        itens.append(f"- {clip.titulo or clip.id}\n  - pasta: {rel(pasta)}\n  - pedido: {rel(dest_clip)}/pedido.md\n"
                     f"  - grave em: {rel(dest_clip)}/saida-editada.mp4 e {rel(dest_clip)}/notas.md")
    linhas = [
        f"# Pedido de edição em lote ({len(clip_ids)} clip(s))",
        "",
        "Cada clip abaixo tem o seu pedido.md com o contexto, o pedido do usuário e as regras obrigatórias. "
        "Leia todos, me mostre UM plano para o lote e espere eu aprovar. Depois trabalhe um clip por vez.",
        "",
        "## Regras do lote",
        "1. Siga as regras obrigatórias de cada pedido.md (nunca altere o original nem o saida.mp4).",
        "2. Cada resultado vai só para a pasta edicoes/ daquele clip.",
        "3. Antes de baixar algo, usar serviço pago ou apagar qualquer arquivo, me pergunte.",
        "",
        "## Clips",
        *itens,
        "",
    ]
    conteudo = "\n".join(linhas)
    (destino / "pedido-lote.md").write_text(conteudo, encoding="utf-8")
    return destino, conteudo


def abrir_lote(projeto: ProjetoWS, clip_ids: list[str], agente: str, modo: str = "abrir",
               agora: datetime | None = None, lancar: bool = True) -> dict[str, Any]:
    """Uma conversa para o lote, na pasta do projeto. "continuar" retoma a última conversa de lá.

    Um lote já preparado é reaproveitado (sem escrever pedidos novos). Com `lancar=False` só prepara
    e devolve `cwd` e a frase fixa para o terminal embutido do app.
    """
    if not clip_ids:
        raise ValueError("Nenhum clip no lote")
    clips = [projeto.clip(c)[0] for c in clip_ids]
    lote = clips[0].pedido_ia.enviado if clips[0].pedido_ia else None
    atual = projeto.path / PASTA_LOTE / lote if lote else None
    if atual and (atual / "pedido-lote.md").exists():
        destino = atual
    else:
        destino, _ = montar_lote(projeto, clip_ids, agora)
    frase = frase_inicial(projeto.path, destino, "pedido-lote.md")
    try:
        args = comando(agente, modo, frase)
        if lancar:
            _lancar(args, projeto.path)
        erro = None
    except Exception as exc:
        erro = str(exc)
    for clip in clips:
        ped = clip.pedido_ia or PedidoIA()
        ped.agente = agente  # type: ignore[assignment]
        ped.enviado, ped.erro = (None, erro) if erro else (destino.name, None)
        clip.pedido_ia = ped
        projeto.salvar_clip(clip)
    if erro:
        raise RuntimeError(erro)
    return {"pasta": str(destino), "lote": destino.name, "agente": agente, "modo": modo, "clips": clip_ids,
            "cwd": str(projeto.path), "frase": frase}


# ---- versões que a IA gravou ---------------------------------------------------------
def listar_versoes(projeto: ProjetoWS, clip_id: str) -> list[dict[str, Any]]:
    clip, pasta = projeto.clip(clip_id)
    base = pasta / PASTA
    if not base.exists():
        return []
    out = []
    for d in sorted((x for x in base.iterdir() if x.is_dir()), reverse=True):
        videos = sorted(p for p in d.iterdir() if p.suffix.lower() in EXT_VIDEO)
        notas = d / "notas.md"
        out.append({
            "id": d.name,
            "videos": [p.relative_to(pasta).as_posix() for p in videos],
            "notas": notas.read_text(encoding="utf-8", errors="replace")[:4000] if notas.exists() else "",
            "pedido": (d / "pedido.md").exists(),
        })
    for v in out:
        v["escolhido"] = next((x for x in v["videos"] if x == clip.versao), None)
    return out


def usar_versao(projeto: ProjetoWS, clip_id: str, video: str | None) -> None:
    """Marca o vídeo editado como a saída escolhida do clip (o saida.mp4 original fica). None volta ao original."""
    clip, pasta = projeto.clip(clip_id)
    if video is not None:
        alvo = (pasta / video).resolve()
        if (pasta / PASTA).resolve() not in alvo.parents or not alvo.is_file() or alvo.suffix.lower() not in EXT_VIDEO:
            raise FileNotFoundError(f"Vídeo editado não encontrado: {video}")
        video = alvo.relative_to(pasta.resolve()).as_posix()
    clip.versao = video
    projeto.salvar_clip(clip)


def apagar_versao(projeto: ProjetoWS, clip_id: str, versao_id: str) -> None:
    clip, pasta = projeto.clip(clip_id)
    alvo = (pasta / PASTA / versao_id).resolve()
    if (pasta / PASTA).resolve() not in alvo.parents or not alvo.is_dir():
        raise FileNotFoundError(f"Versão não encontrada: {versao_id}")
    if clip.versao and clip.versao.startswith(f"{PASTA}/{versao_id}/"):
        clip.versao = None
        projeto.salvar_clip(clip)
    shutil.rmtree(alvo)
