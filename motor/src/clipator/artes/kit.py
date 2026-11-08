"""Kit das direções de arte: o contexto de uma cena, a medição de texto e os pedaços de SVG que elas repetem.

Cada renderizador recebe um `Ctx` com o retângulo local da arte (largura sempre 1000 unidades, altura conforme o
layout) e devolve SVG. As animações são CSS com atraso calculado aqui: o HyperFrames busca o tempo de cada elemento,
então nada depende de relógio nem de estado de um quadro anterior. Sorteios só com `c.rng()` (semente fixa).
"""

from __future__ import annotations

import html
import random
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from PIL import ImageFont

ALTURA_LINHA = 1.2
FONTE_MIN = 34  # unidades (1000 = largura do quadro): menor que isso não se lê no celular


@lru_cache(maxsize=8)
def _fonte(nome: str) -> Any:
    from ..thumbs import caminho_fonte

    p = caminho_fonte(nome, [])
    return ImageFont.truetype(str(p), 100) if p else None


def largura(texto: str, nome: str, tam: float) -> float:
    """Largura real do texto na fonte carregada (fonte ausente: uma estimativa, e o relatório avisa)."""
    f = _fonte(nome)
    return f.getlength(texto) * tam / 100 if f else len(texto) * tam * 0.6


def quebrar(texto: str, nome: str, tam: float, larg: float) -> list[str]:
    """Quebra por palavras na largura dada."""
    linhas: list[str] = []
    atual = ""
    for p in texto.split():
        tenta = f"{atual} {p}".strip()
        if atual and largura(tenta, nome, tam) > larg:
            linhas.append(atual)
            atual = p
        else:
            atual = tenta
    return linhas + ([atual] if atual else [])


def ajustar(texto: str, nome: str, larg: float, alt: float, max_linhas: int = 3, tam_max: float = 90,
            tam_min: float = FONTE_MIN) -> tuple[list[str], float]:
    """(linhas, tamanho): o maior corpo em que o texto cabe; sem caber no mínimo, corta por palavras com reticências."""
    tam = float(tam_max)
    while tam >= tam_min:
        linhas = quebrar(texto, nome, tam, larg)
        if len(linhas) <= max_linhas and len(linhas) * tam * ALTURA_LINHA <= alt and all(largura(x, nome, tam) <= larg for x in linhas):
            return linhas, tam
        tam -= 2
    tam = float(tam_min)
    linhas = quebrar(texto, nome, tam, larg)
    cabe = max(1, min(max_linhas, int(alt // (tam * ALTURA_LINHA))))
    if len(linhas) > cabe:
        linhas = linhas[:cabe]
        linhas[-1] = linhas[-1].rstrip(" ,.;:") + "…"
    return linhas, tam


@dataclass
class Ctx:
    W: float
    H: float
    seguro: tuple[float, float, float, float]  # x0, y0, x1, y1 no retângulo local
    p: dict[str, Any]
    par: dict[str, Any]
    dur: float
    semente: int
    k: int = 0  # índice da cena
    total: int = 1
    leve: bool = False
    palavras: list[dict] = field(default_factory=list)  # palavras da cena, com tempo contado do início dela
    midia: str | None = None  # caminho local da imagem da cena, já conferido
    fonte_titulo: str = "Bebas Neue"
    fonte_corpo: str = "Montserrat ExtraBold"
    cores: dict[str, str] = field(default_factory=dict)  # a ficha resolvida: quem pinta fora do CSS (pixels) lê daqui

    @property
    def x0(self) -> float:
        return self.seguro[0]

    @property
    def y0(self) -> float:
        return self.seguro[1]

    @property
    def x1(self) -> float:
        return self.seguro[2]

    @property
    def y1(self) -> float:
        return self.seguro[3]

    @property
    def lw(self) -> float:
        return self.x1 - self.x0

    @property
    def lh(self) -> float:
        return self.y1 - self.y0

    @property
    def texto(self) -> str:
        return str(self.p.get("texto") or "")

    @property
    def nota(self) -> str:
        return str(self.p.get("nota") or "")

    @property
    def dado(self) -> str:
        return str(self.p.get("dado") or "")

    @property
    def etiqueta(self) -> str:
        return str(self.p.get("etiqueta") or "")

    def rng(self, n: int = 0) -> random.Random:
        return random.Random(self.semente * 7919 + self.k * 131 + n)

    def itens(self, n: int) -> list[str]:
        """Até n rótulos curtos da cena: os itens dados ou pedaços do próprio texto, nunca inventados."""
        it = [str(x) for x in (self.p.get("itens") or []) if str(x).strip()]
        if not it:
            pal = self.texto.split()
            passo = max(1, -(-len(pal) // max(1, n)))
            it = [" ".join(pal[i:i + passo]) for i in range(0, len(pal), passo)]
        return it[:n]

    def fases(self, n: int, inicio: float = 0.1, leitura: float = 1.0) -> list[float]:
        """n momentos da cena, presos à fala: o começo de cada grupo de palavras; sem fala, repartidos no tempo.

        A última fase sempre deixa `leitura` segundos: a fala rápida simplifica as fases, não encurta a leitura.
        """
        teto = max(inicio, self.dur - leitura)
        if self.palavras and len(self.palavras) >= n:
            passo = len(self.palavras) / n
            ts = [self.palavras[int(i * passo)]["inicio"] for i in range(n)]
        else:
            ts = [self.dur * 0.72 * i / max(1, n) for i in range(n)]
        ts[0] = inicio
        out: list[float] = []
        for t in ts:
            t = min(max(t, inicio), teto)
            out.append(round(max(t, out[-1] + 0.12) if out else t, 3))
        return [min(t, max(inicio, self.dur - 0.3)) for t in out]

    def quando(self, trecho: str, padrao: float) -> float:
        """O segundo em que o trecho é dito dentro da cena (padrão, se a fala não tem esse trecho)."""
        from . import tokens

        alvo = tokens(trecho)
        ws = [tokens(w["texto"]) for w in self.palavras]
        ws = [w[0] if w else "" for w in ws]
        for i in range(max(0, len(ws) - len(alvo) + 1)):
            if alvo and ws[i:i + len(alvo)] == alvo:
                return round(self.palavras[i]["inicio"], 3)
        return padrao


# ---- pedaços de SVG -------------------------------------------------------------------------------------------
def esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=True)


# O HyperFrames busca pelo tempo do clip só os elementos HTML; os de SVG ele busca pelo tempo da composição inteira. Por isso
# toda animação aqui leva o atraso absoluto: o início da cena (T0) mais o tempo dentro dela.
T0: ContextVar[float] = ContextVar("arte_t0", default=0.0)


def an(nome: str, t: float, d: float = 0.45, curva: str = "cubic-bezier(.2,.8,.2,1)") -> str:
    """A declaração de animação (a entrada fica presa no primeiro quadro até a hora dela)."""
    return f"animation:{nome} {d:.2f}s {curva} {t + T0.get():.3f}s both"


def g(conteudo: str, t: float | None = None, nome: str = "a-fade", d: float = 0.45, tf: str = "", classe: str = "", curva: str = "cubic-bezier(.2,.8,.2,1)",
      css: str = "") -> str:
    """Um grupo com entrada; `tf` (transformação fixa) fica num grupo de fora, porque a animação substitui a de dentro."""
    st = f' style="{an(nome, t, d, curva)};{css}"' if t is not None else ""
    cls = f' class="an {classe}"' if t is not None else (f' class="{classe}"' if classe else "")
    corpo = f"<g{cls}{st}>{conteudo}</g>"
    return f'<g transform="{tf}">{corpo}</g>' if tf else corpo


def txt(x: float, y: float, s: Any, tam: float, cor: str = "var(--texto)", fonte: str = "c", ancora: str = "start", extra: str = "") -> str:
    familia = "var(--f-titulo)" if fonte == "t" else "var(--f-corpo)"
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{cor}" font-family="{familia}" font-size="{tam:.1f}" text-anchor="{ancora}" '
            f'{extra}>{esc(s)}</text>')


def linhas(x: float, y: float, ls: list[str], tam: float, cor: str = "var(--texto)", fonte: str = "c", ancora: str = "start") -> str:
    """Bloco de linhas; `y` é a linha de base da primeira."""
    return "".join(txt(x, y + i * tam * ALTURA_LINHA, s, tam, cor, fonte, ancora) for i, s in enumerate(ls))


def retangulo(x: float, y: float, w: float, h: float, cor: str, r: float = 0, extra: str = "") -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r:.1f}" fill="{cor}" {extra}/>'


def traco(d: str, cor: str, esp: float, t: float | None = None, dur: float = 0.6, extra: str = "") -> str:
    """Um caminho que se desenha pelo comprimento (pathLength=1)."""
    st = f' class="an" style="{an("a-risca", t, dur, "ease-out")};stroke-dasharray:1"' if t is not None else ""
    return f'<path d="{d}" pathLength="1" fill="none" stroke="{cor}" stroke-width="{esp:.1f}" stroke-linecap="round" stroke-linejoin="round"{st} {extra}/>'


def peca(nome: str | None, x: float, y: float, lado: float, cor: str = "var(--texto)") -> str:
    """Uma peça da biblioteca de traço do Clipator (desenho.PECAS) num quadrado."""
    from ..desenho import PECAS

    v = PECAS.get(nome or "") or PECAS["lampada"]
    return f'<svg x="{x:.1f}" y="{y:.1f}" width="{lado:.1f}" height="{lado:.1f}" viewBox="0 0 100 100" color="{cor}" style="color:{cor}">{v[1]}</svg>'


def imagem(c: Ctx, x: float, y: float, w: float, h: float, recorte: float = 0, filtro: str = "") -> str | None:
    """A mídia da cena num retângulo (mantém a proporção, corta o excesso); None sem mídia."""
    if not c.midia:
        return None
    ident = f"m{c.k}-{int(x)}-{int(y)}"
    f = f' filter="url(#{filtro})"' if filtro else ""
    return (f'<clipPath id="{ident}"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{recorte:.1f}"/></clipPath>'
            f'<image href="{esc(c.midia)}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#{ident})"{f}/>')


def ruido(ident: str, semente: int, freq: float = 0.8, oit: int = 2) -> str:
    """Filtro de textura procedural (semente fixa): nada de textura baixada."""
    return (f'<filter id="{ident}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="{freq}" '
            f'numOctaves="{oit}" seed="{semente % 997}" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>')


CSS = """
.cena.arte { left: 0; right: 0; padding: 0; gap: 0; display: block; background: none !important; box-shadow: none !important; animation: none; }
.arte-palco { position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; }
.arte-fundo { position: absolute; left: 0; right: 0; top: var(--topo); height: var(--alt); width: 100%; }
.fundo-da.com-arte { background: var(--fundo); }
.fundo-da.com-arte .malha, .fundo-da.com-arte .brilho { display: none; }
.arte-sai { animation: a-sai .22s ease-in var(--saida) forwards; }
.an { transform-box: fill-box; transform-origin: center; }
@keyframes a-sai { to { opacity: 0; } }
@keyframes a-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes a-sobe { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; transform: none; } }
@keyframes a-desce { from { opacity: 0; transform: translateY(-24px); } to { opacity: 1; transform: none; } }
@keyframes a-esq { from { opacity: 0; transform: translateX(-60px); } to { opacity: 1; transform: none; } }
@keyframes a-dir { from { opacity: 0; transform: translateX(60px); } to { opacity: 1; transform: none; } }
@keyframes a-cresce { from { opacity: 0; transform: scale(.92); } to { opacity: 1; transform: none; } }
@keyframes a-pop { from { opacity: 0; transform: scale(.5); } 70% { opacity: 1; transform: scale(1.05); } to { opacity: 1; transform: none; } }
@keyframes a-entra-x { from { opacity: 0; transform: translateX(calc(var(--e, 24px) * -1)); } to { opacity: 1; transform: none; } }
@keyframes a-entra-y { from { opacity: 0; transform: translateY(var(--e, 24px)); } to { opacity: 1; transform: none; } }
@keyframes a-assenta { 0% { opacity: 0; transform: translate(var(--dx, 0), var(--dy, 40px)) rotate(var(--r, 0deg)); } 60% { opacity: 1; transform: translate(0, 0) rotate(var(--r, 0deg)); } 100% { opacity: 1; transform: none; } }
@keyframes a-risca { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes a-abre-x { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
@keyframes a-abre-y { from { clip-path: inset(0 0 100% 0); } to { clip-path: inset(0 0 0 0); } }
@keyframes a-abre-meio { from { clip-path: inset(0 50% 0 50%); } to { clip-path: inset(0 0 0 0); } }
body.arte-leve .an { animation-name: a-fade !important; animation-duration: .25s !important; animation-timing-function: linear !important; animation-iteration-count: 1 !important; }
body.arte-leve .deco { display: none; }
"""
