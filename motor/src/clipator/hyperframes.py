"""Motor HyperFrames: legendas e motion graphics em HTML/CSS, renderizados em vídeo.

O Clipator monta uma composição HyperFrames (https://github.com/heygen-com/hyperframes,
Apache 2.0) só com a camada de cima do clip: legenda palavra a palavra, cartela,
números e palavras-chave, sobre fundo transparente. O HyperFrames renderiza essa
camada em WebM com alfa, e o FFmpeg junta com o vídeo já reenquadrado. O vídeo do
usuário nunca passa pelo navegador.

As animações são CSS puro (sem GSAP nem CDN), então tudo roda offline. O HyperFrames
busca as animações CSS quadro a quadro, contando o tempo a partir do início de cada
elemento com class="clip".

Templates: dados/hyperframes/<nome>.css (e <nome>.html opcional com decoração fixa).
Um estilo escolhe o template por `template:`; sem isso, usa o de mesmo nome do
estilo e, por último, o "base".
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from string import Template

from .media import Progress, Travado, apagar_parcial, rodar_processo
from .models import Cartela, Estilo, Legenda
from .subtitles import POSICOES_Y, blocos_de_palavras, palavras_do_clip, regex_destaque
from .thumbs import caminho_fonte
from .timeline import Timeline
from .workspace import _dados

ARQ_BASE = "base"
NUMERO_RE = re.compile(r"^(R\$)?\d+(?:[.,]\d+)*%?\W*$")
SUFIXOS_NUMERO = {"mil", "milhão", "milhões", "milhao", "milhoes", "bilhão", "bilhões", "bilhao", "bilhoes", "reais",
                  "dólares", "dolares", "anos", "por", "vezes", "pessoas", "%", "k", "thousand", "million", "billion",
                  "percent", "dollars", "years"}


class ErroHyperFrames(RuntimeError):
    pass


def pasta_templates() -> Path:
    return _dados("hyperframes")


def templates_embutidos() -> list[str]:
    return sorted(p.stem for p in pasta_templates().glob("*.css"))


# ---- onde está o HyperFrames ------------------------------------------------
def pasta_instalacao() -> Path:
    """Onde o instalador põe o HyperFrames (npm install --prefix)."""
    env = os.environ.get("CLIPATOR_HYPERFRAMES_DIR")
    return Path(env).expanduser() if env else Path.home() / ".clipator" / "hyperframes"


def pasta_node() -> Path:
    """Node.js que o instalador põe em ~/.clipator/node quando o sistema não tem um."""
    return Path(os.environ.get("CLIPATOR_NODE_DIR") or Path.home() / ".clipator" / "node")


def node_bin() -> str | None:
    achado = shutil.which("node")
    if achado:
        return achado
    base = pasta_node()
    for c in (base / "node.exe", base / "bin" / "node"):
        if c.is_file():
            return str(c)
    return None


def comando() -> list[str] | None:
    """Comando para rodar o CLI do HyperFrames, ou None se não estiver instalado."""
    env = os.environ.get("CLIPATOR_HYPERFRAMES")
    if env:
        return env.split(" ") if " " in env and not Path(env).exists() else [env]
    node = node_bin()
    mjs = pasta_instalacao() / "node_modules" / "hyperframes" / "bin" / "hyperframes.mjs"
    if node and mjs.is_file():
        return [node, str(mjs)]
    no_path = shutil.which("hyperframes")
    return [no_path] if no_path else None


def versao() -> str | None:
    cmd = comando()
    if not cmd:
        return None
    try:
        r = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=60, env=_env())
        linhas = (r.stdout or r.stderr).strip().splitlines()
        return linhas[-1].strip() if r.returncode == 0 and linhas else None
    except Exception:
        return None


def _env() -> dict[str, str]:
    env = dict(os.environ)
    # nada sai da máquina: sem telemetria do HyperFrames
    env["HYPERFRAMES_NO_TELEMETRY"] = "1"
    env["DO_NOT_TRACK"] = "1"
    env.setdefault("CI", "1")  # sem perguntas interativas
    node = node_bin()
    if node and not shutil.which("node"):  # o node do instalador precisa estar no PATH dos filhos
        env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    return env


# ---- composição ---------------------------------------------------------------
@dataclass
class Composicao:
    html: str
    fontes: list[Path]


def _css_template(estilo: Estilo, pasta_estilo: Path | None) -> tuple[str, str]:
    """CSS e HTML de decoração do template do estilo."""
    candidatos: list[Path] = []
    nome = estilo.template
    if nome and pasta_estilo is not None:
        candidatos.append(pasta_estilo / nome)
    if pasta_estilo is not None and (pasta_estilo / "estilo.md").exists() and (pasta_estilo / "composicao.css").exists():
        candidatos.append(pasta_estilo / "composicao.css")
    for n in [nome, _slug_estilo(estilo)]:
        if n:
            candidatos.append(pasta_templates() / f"{Path(n).stem}.css")
    for c in candidatos:
        if c.suffix == ".html" and c.is_file():
            return "", c.read_text(encoding="utf-8")
        if c.suffix == ".css" and c.is_file():
            deco = c.with_suffix(".html")
            return c.read_text(encoding="utf-8"), deco.read_text(encoding="utf-8") if deco.is_file() else ""
    return "", ""


def _slug_estilo(estilo: Estilo) -> str:
    from .workspace import slugify

    return slugify(estilo.nome) if estilo.nome else ""


def _num(v: float) -> str:
    return f"{max(0.0, v):.3f}"


def _clip(cls: str, ini: float, dur: float, conteudo: str, trilha: int, ident: str, extra: str = "") -> str:
    return (f'<div id="{ident}" class="clip {cls}" data-start="{_num(ini)}" data-duration="{_num(max(dur, 0.04))}" '
            f'data-track-index="{trilha}"{extra}>{conteudo}</div>')


def _fonte_css(nome: str, extras: list[Path]) -> tuple[str, Path | None]:
    p = caminho_fonte(nome, extras)
    if p is None:
        return "", None
    familia = html.escape(nome)
    return f"@font-face {{ font-family: '{familia}'; src: url('fontes/{p.name}'); font-display: block; }}\n", p


def compor(palavras: list[dict], tl: Timeline, estilo: Estilo, largura: int, altura: int, titulo: str = "",
           usar_cartela: bool = False, destaques_extra: list[str] | None = None, pasta_estilo: Path | None = None,
           fontes_extras: list[Path] | None = None, fps: int = 30, css_da: str = "") -> Composicao:
    """Monta o index.html da camada de cima do clip. `css_da`: variáveis `--da-*` da direção de arte do canal."""
    leg: Legenda = estilo.legenda
    cart: Cartela = estilo.cartela
    escala = min(largura, altura) / 1080
    duracao = tl.duracao
    css_t, deco = _css_template(estilo, pasta_estilo)
    destaque_re = regex_destaque(leg, destaques_extra)
    fmt = (lambda t: t.upper()) if leg.caixa_alta else (lambda t: t)

    partes: list[str] = []
    pals = palavras_do_clip(palavras, tl) if palavras else []
    # legenda
    if leg.modo != "nenhuma" and pals:
        max_pal = 1 if leg.modo == "uma-palavra" else leg.max_palavras_por_linha * leg.linhas
        blocos = blocos_de_palavras(pals, max_pal)
        for k, bloco in enumerate(blocos):
            ini = bloco[0]["inicio"]
            prox = blocos[k + 1][0]["inicio"] if k + 1 < len(blocos) else duracao
            fim = min(prox, bloco[-1]["fim"] + 0.6, duracao)
            linhas_html, linha = [], []
            for j, w in enumerate(bloco):
                cls = "p destaque" if destaque_re and destaque_re.match(w["texto"]) else "p"
                linha.append(f'<span class="{cls}" style="--i:{j};--t:{_num(w["inicio"] - ini)}s;'
                             f'--d:{_num(w["fim"] - w["inicio"])}s">{html.escape(fmt(w["texto"]))}</span>')
                if leg.modo != "frase" and len(linha) >= leg.max_palavras_por_linha:
                    linhas_html.append('<div class="linha">' + " ".join(linha) + "</div>")
                    linha = []
            if linha:
                linhas_html.append('<div class="linha">' + " ".join(linha) + "</div>")
            partes.append(_clip("frase", ini, fim - ini, "".join(linhas_html), 2, f"frase-{k + 1}",
                                f' data-modo="{leg.modo}"'))
    # números e palavras-chave (só aparecem nos templates que os estilizam)
    for k, w in enumerate(pals):
        if NUMERO_RE.match(w["texto"]):
            seg = pals[k + 1]["texto"].strip(".,!?").lower() if k + 1 < len(pals) else ""
            sufixo = seg if seg in SUFIXOS_NUMERO else ""
            valor = re.sub(r"[^\d]", "", w["texto"].split(",")[0].split(".")[0]) or "0"
            conteudo = (f'<span class="valor" style="--alvo:{int(valor[:9])}">{html.escape(w["texto"].strip(".,!?"))}</span>'
                        f'<span class="sufixo">{html.escape(sufixo)}</span>')
            partes.append(_clip("numero", w["inicio"], min(2.4, duracao - w["inicio"]), conteudo, 3, f"numero-{k}"))
        elif destaque_re and destaque_re.match(w["texto"]) and len(w["texto"]) > 3:
            partes.append(_clip("chave", w["inicio"], min(1.6, duracao - w["inicio"]),
                                f"<span>{html.escape(w['texto'].strip('.,!?').upper())}</span>", 4, f"chave-{k}"))
    # cartela
    if usar_cartela and titulo:
        texto = titulo.upper() if cart.caixa_alta else titulo
        caps = {p for p in titulo.split() if len(p) > 1 and p.isupper()}
        palavras_t = " ".join(f'<b class="destaque">{html.escape(p)}</b>' if (not cart.caixa_alta and p in caps)
                              else html.escape(p) for p in texto.split())
        partes.append(_clip("cartela", 0, min(cart.duracao, duracao), f'<div class="caixa">{palavras_t}</div>', 5,
                            "cartela", f' data-posicao="{cart.posicao}"'))

    # fontes
    fontes: list[Path] = []
    css_fontes = ""
    for nome in dict.fromkeys([leg.fonte, cart.fonte, "Anton", "Special Elite", "Bebas Neue"]):
        bloco, p = _fonte_css(nome, fontes_extras or [])
        if p is not None and p not in fontes:
            css_fontes += bloco
            fontes.append(p)

    y_rel = leg.altura_relativa if leg.altura_relativa is not None else POSICOES_Y.get(leg.posicao, 0.68)
    variaveis = {
        "--largura": f"{largura}px", "--altura": f"{altura}px", "--escala": f"{escala:.4f}",
        "--fonte": f"'{leg.fonte}', 'Anton', sans-serif", "--tamanho": f"{max(10, int(leg.tamanho * escala))}px",
        "--cor": leg.cor, "--destaque": leg.destaque, "--contorno": leg.contorno,
        "--espessura": f"{leg.espessura_contorno * escala:.1f}px", "--sombra": f"{leg.sombra * escala:.1f}px",
        "--fundo-legenda": leg.fundo or "transparent", "--y": f"{y_rel * 100:.1f}%",
        "--fonte-cartela": f"'{cart.fonte}', 'Anton', sans-serif", "--tamanho-cartela": f"{max(10, int(cart.tamanho * escala))}px",
        "--cor-cartela": cart.cor, "--fundo-cartela": cart.fundo, "--destaque-cartela": cart.destaque,
        "--duracao": f"{duracao:.3f}s",
    }
    raiz_css = ":root {\n" + "".join(f"  {k}: {v};\n" for k, v in variaveis.items()) + "}\n"
    base_css = (pasta_templates() / f"{ARQ_BASE}.css").read_text(encoding="utf-8")
    deco_html = Template(deco).safe_substitute(titulo=html.escape(titulo or ""), duracao=f"{duracao:.3f}")
    doc = f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={largura}, height={altura}" />
<!-- Gerado pelo Clipator. Motor: HyperFrames (Apache 2.0). -->
<style>
{css_fontes}{css_da}{raiz_css}{base_css}
{css_t}
</style>
</head>
<body>
<div id="root" data-composition-id="clipator" data-start="0" data-duration="{_num(duracao)}" data-width="{largura}" data-height="{altura}" data-fps="{fps}" data-no-timeline>
{deco_html}
{chr(10).join(partes)}
</div>
</body>
</html>
"""
    return Composicao(doc, fontes)


# ---- render -----------------------------------------------------------------
def escrever_projeto(pasta: Path, comp: Composicao) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "fontes").mkdir(exist_ok=True)
    for f in comp.fontes:
        destino = pasta / "fontes" / f.name
        if not destino.exists():
            shutil.copyfile(f, destino)
    (pasta / "index.html").write_text(comp.html, encoding="utf-8")
    return pasta / "index.html"


_PROG = re.compile(r"^@hf-progress\s+(\{.*\})\s*$")
SEM_SAIDA_S = 120.0  # o render escreve progresso o tempo todo; 2 min calado é travamento (cai para a legenda ASS)


def renderizar(pasta: Path, saida: Path, fps: int = 30, progresso: Progress | None = None,
               cancelar: threading.Event | None = None, timeout: int = 3600) -> Path:
    """Roda `hyperframes render --format webm` na pasta do projeto. Devolve o .webm com alfa."""
    cmd = comando()
    if not cmd:
        raise ErroHyperFrames("HyperFrames não instalado. Rode o instalador do Clipator ou 'clipator doctor'.")
    tmp = saida.with_name(saida.stem + ".tmp.webm")
    args = [*cmd, "render", "--format", "webm", "--fps", str(fps), "--output", str(tmp)]
    cauda: list[str] = []

    def ao_ler(linha: str) -> None:
        nonlocal cauda
        m = _PROG.match(linha.strip())
        if m and progresso:
            try:
                pct = float(json.loads(m.group(1)).get("pct", 0)) / 100
                progresso(min(1.0, pct), "camada HyperFrames")
            except (ValueError, json.JSONDecodeError):
                pass
        elif linha.strip():
            cauda = (cauda + [linha.rstrip()])[-30:]

    try:
        codigo = rodar_processo(args, ao_ler, cancelar, sem_saida_s=SEM_SAIDA_S, timeout_s=timeout,
                                descricao="O HyperFrames", cwd=pasta, env=_env())
    except Travado as exc:
        apagar_parcial(tmp)
        raise ErroHyperFrames(str(exc)) from exc
    except BaseException:
        apagar_parcial(tmp)
        raise
    if codigo != 0 or not tmp.exists():
        apagar_parcial(tmp)
        raise ErroHyperFrames("O HyperFrames falhou:\n" + "\n".join(cauda[-12:]))
    tmp.replace(saida)
    return saida
