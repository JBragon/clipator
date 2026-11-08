"""Stickers animados de chamada ("Inscreva-se", curtir, sininho, comente, compartilhe, salvar…) e o
sticker de texto digitável.

Desenhos próprios do Clipator, feitos aqui com o Pillow (sem copiar o CapCut nem usar a logo ou o
botão oficial do YouTube): botões, balões, setas e um cursor que clica, animados quadro a quadro e
gravados como APNG com fundo transparente. Texto e cores vêm dos parâmetros do item no editor; cada
combinação é gerada uma vez e fica em cache. Os ícones 3D (joinha, sino, mão, olhos) são do pacote
Fluent Emoji (MIT) quando ele está baixado; sem ele, o desenho sai só com o botão.

O texto ("texto", sem fundo, para o @ do canal) é `fixo`: só tem a animação de entrada e o último quadro fica na tela até o fim do
item (o render segura o último quadro).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .workspace import fontes_dir

VERSAO = "v4"  # muda quando o desenho muda, para não reaproveitar o arquivo antigo
FPS = 25
LARG, ALT = 1300, 560  # tela de desenho; no fim cada animação é recortada ao que foi usado
CX, CY = LARG / 2, ALT / 2
CINZA = (62, 62, 66, 255)
AZUL = (48, 128, 255, 255)
BRANCO = (255, 255, 255, 255)
PRETO = (20, 20, 22, 255)
AMARELO = (255, 200, 40, 255)

# predefinições de cor do editor: (botão, texto)
PRESETS = {
    "vermelho": ("#E62117", "#FFFFFF"),
    "preto": ("#141416", "#FFFFFF"),
    "branco": ("#FFFFFF", "#E62117"),
    "neon": ("#39FF14", "#0A0A0A"),
    "contorno": ("#141416", "#FFFFFF"),  # texto sem fundo: (contorno, texto)
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass
class Opcoes:
    texto: str
    texto2: str
    cor: tuple[int, int, int, int]
    cor_texto: tuple[int, int, int, int]
    formato: dict[str, Any] | None = None  # só o texto livre: fonte, negrito, itálico… (ver `formato()`)
    pasta_fontes: Path | None = None  # fontes do canal (assets/fontes)


@dataclass
class Modelo:
    nome: str
    palavras: list[str]
    textos: dict[str, tuple[str, str]]  # idioma -> (texto, texto2); texto2 é o depois do clique ou a linha de baixo
    preset: str
    duracao: float
    som: tuple[str, float] | None  # (efeito de sons.py, segundo dentro da animação)
    desenho: Callable[[Opcoes, Path | None], list[Image.Image]]
    caixa_alta: bool = True  # o texto vira CAIXA ALTA (o texto livre fica como foi digitado)
    fixo: bool = False  # só a entrada; o último quadro fica até o fim do item


# ---- utilidades de desenho ----------------------------------------------------------------
def _rgba(h: str) -> tuple[int, int, int, int]:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)


def _fonte(tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(fontes_dir() / "Montserrat-ExtraBold.ttf"), tam)


def _sai(t: float) -> float:  # ease-out cúbico
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def _mola(t: float) -> float:
    """Entrada com quique (passa um pouco de 1 e volta)."""
    if t <= 0:
        return 0.0
    t = min(1.0, t)
    return 1 - math.exp(-6 * t) * math.cos(9 * t)


def _saida(t: float, dur: float, tempo: float = 0.3) -> float:
    """Escala de saída: 1 até `dur - tempo`, depois encolhe até sumir."""
    k = (t - (dur - tempo)) / tempo
    return 1.0 if k <= 0 else max(0.0, 1 - _sai(k))


def _icone(nome: str, lado: int, pasta: Path | None) -> Image.Image | None:
    if pasta is None:
        return None
    for p in (pasta / f"{nome}-3d.png", pasta / f"{nome}.png"):
        if p.is_file():
            with Image.open(p) as img:
                return img.convert("RGBA").resize((lado, lado), Image.LANCZOS)
    return None


def _cursor(escala: float = 1.6) -> Image.Image:
    """Seta de mouse branca com contorno escuro."""
    s = 4
    w, h = int(34 * escala * s), int(48 * escala * s)
    m = s * 4
    img = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
    pts = [(0, 0), (0, 0.78), (0.22, 0.6), (0.38, 0.98), (0.52, 0.92), (0.36, 0.56), (0.66, 0.56)]
    ImageDraw.Draw(img).polygon([(x * w + m, y * h + m) for x, y in pts], fill=BRANCO, outline=PRETO,
                                width=int(3 * s * escala))
    return img.resize((img.width // s, img.height // s), Image.LANCZOS)


def _visto(lado: int, cor: tuple) -> Image.Image:
    """Sinal de "feito" desenhado (a fonte não tem o caractere ✓)."""
    s = 4
    L = lado * s
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(0.12 * L, 0.55 * L), (0.4 * L, 0.82 * L), (0.9 * L, 0.2 * L)], fill=cor,
                             width=int(0.17 * L), joint="curve")
    return img.resize((lado, lado), Image.LANCZOS)


def _botao(texto: str, cor: tuple, cor_texto: tuple, tam_fonte: int, icone: Image.Image | None = None,
           pad: tuple[int, int] = (34, 18), icone_depois: bool = False) -> Image.Image:
    f = _fonte(tam_fonte)
    caixa = f.getbbox(texto) if texto else (0, 0, 0, int(tam_fonte * 0.72))
    tw, th = caixa[2] - caixa[0], caixa[3] - caixa[1]
    iw = (icone.width + (14 if texto else 0)) if icone is not None else 0
    w = tw + iw + pad[0] * 2
    h = max(th, icone.height if icone is not None else 0) + pad[1] * 2
    s = 3
    img = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    claro = sum(cor[:3]) > 600  # botão claro ganha um contorno leve para não sumir em fundo claro
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius=h * s // 2, fill=cor,
                                          outline=(0, 0, 0, 45) if claro else None, width=2 * s)
    img = img.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    x = pad[0]
    if icone is not None and not icone_depois:
        img.alpha_composite(icone, (x, (h - icone.height) // 2))
        x += iw
    d.text((x - caixa[0], (h - th) // 2 - caixa[1]), texto, font=f, fill=cor_texto)
    if icone is not None and icone_depois:
        img.alpha_composite(icone, (x + tw + 14, (h - icone.height) // 2))
    return img


def _sombra(img: Image.Image, raio: int = 8, alfa: int = 90) -> Image.Image:
    out = Image.new("RGBA", (img.width + raio * 4, img.height + raio * 4), (0, 0, 0, 0))
    preta = Image.new("RGBA", img.size, (0, 0, 0, 255))
    preta.putalpha(img.split()[3].point(lambda a: a * alfa // 255))
    out.alpha_composite(preta, (raio * 2, raio * 2 + raio // 2))
    out = out.filter(ImageFilter.GaussianBlur(raio))
    out.alpha_composite(img, (raio * 2, raio * 2))
    return out


def _colar(quadro: Image.Image, img: Image.Image | None, cx: float, cy: float, escala: float = 1.0, angulo: float = 0.0,
           alfa: float = 1.0) -> None:
    if img is None or escala <= 0.01 or alfa <= 0.01:
        return
    w, h = max(1, int(img.width * escala)), max(1, int(img.height * escala))
    peca = img.resize((w, h), Image.LANCZOS) if (w, h) != img.size else img.copy()
    if angulo:
        peca = peca.rotate(angulo, resample=Image.BICUBIC, expand=True)
    if alfa < 1:
        peca.putalpha(peca.split()[3].point(lambda v: int(v * alfa)))
    quadro.alpha_composite(peca, (int(cx - peca.width / 2), int(cy - peca.height / 2)))


def _raios(quadro: Image.Image, cx: float, cy: float, r0: float, r1: float, cor: tuple, alfa: float, n: int = 8,
           grossura: int = 8, giro: float = 0.0) -> None:
    """Risquinhos saindo do centro (estouro do joinha, brilho do sino)."""
    if alfa <= 0.01:
        return
    camada = Image.new("RGBA", quadro.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    c = (*cor[:3], int(255 * min(1.0, alfa)))
    for k in range(n):
        a = giro + 2 * math.pi * k / n
        d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a))],
               fill=c, width=grossura)
    quadro.alpha_composite(camada)


def _animar(dur: float, quadro: Callable[[float, Image.Image], None]) -> list[Image.Image]:
    out = []
    for i in range(int(round(dur * FPS))):
        q = Image.new("RGBA", (LARG, ALT), (0, 0, 0, 0))
        quadro(i / FPS, q)
        out.append(q)
    return out


def _recortar(quadros: list[Image.Image], margem: int = 6) -> list[Image.Image]:
    """Corta todos os quadros na mesma caixa: a união do que aparece em qualquer um deles."""
    caixa = None
    for q in quadros:
        b = q.getbbox()
        if b:
            caixa = b if caixa is None else (min(caixa[0], b[0]), min(caixa[1], b[1]), max(caixa[2], b[2]), max(caixa[3], b[3]))
    if caixa is None:
        return quadros
    x0, y0 = max(0, caixa[0] - margem), max(0, caixa[1] - margem)
    x1, y1 = min(LARG, caixa[2] + margem), min(ALT, caixa[3] + margem)
    x1 -= (x1 - x0) % 2  # lados pares (o FFmpeg agradece)
    y1 -= (y1 - y0) % 2
    return [q.crop((x0, y0, x1, y1)) for q in quadros]


def _cursor_ate(q: Image.Image, cur: Image.Image, alvo: tuple[float, float], t: float, chega: float, clique: float,
                some: float) -> None:
    """O cursor entra por baixo à direita, para no alvo, afunda no clique e some."""
    if t < chega or t > some + 0.3:
        return
    k = _sai((t - chega) / max(0.05, clique - chega - 0.1))
    px, py = alvo[0] + (1 - k) * 320, alvo[1] + (1 - k) * 60
    if clique <= t < clique + 0.15:
        px, py = px + 3, py + 3
    alfa = 1.0 if t < some else max(0.0, 1 - (t - some) / 0.3)
    _colar(q, cur, px + cur.width / 2 - 6, py + cur.height / 2 - 6, 1, 0, alfa)


# ---- os desenhos ------------------------------------------------------------------------
def _clicavel(op: Opcoes, icones: Path | None, dur: float, clique: float, sino: bool) -> list[Image.Image]:
    """Botão que recebe o clique e muda de estado (Inscreva-se → Inscrito, Seguir → Seguindo)."""
    antes = _sombra(_botao(op.texto, op.cor, op.cor_texto, 58))
    depois = _sombra(_botao(op.texto2, CINZA, BRANCO, 58, _visto(46, BRANCO), icone_depois=True))
    ic_sino = _icone("bell", 96, icones) if sino else None
    cur = _cursor()
    deslocar = (ic_sino.width + 30) / 2 if ic_sino is not None else 0

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        cx = CX - deslocar
        botao = antes if t < clique else depois
        esc = _mola(t / 0.45) * sai
        if clique <= t < clique + 0.2:
            esc *= 1 - 0.08 * math.sin(math.pi * (t - clique) / 0.2)
        _colar(q, botao, cx, CY, esc)
        _cursor_ate(q, cur, (cx + botao.width * 0.18, CY + 6), t, 0.4, clique, clique + 0.55)
        if ic_sino is not None and t > clique + 0.1:  # o sino aparece balançando, com brilho
            k = t - clique - 0.1
            ang = 24 * math.sin(k * 15) * math.exp(-k * 1.4)
            sx = cx + depois.width / 2 + ic_sino.width / 2 + 8
            _colar(q, ic_sino, sx, CY - 4, _mola(k / 0.35) * sai, ang)
            _raios(q, sx, CY - 10, 62, 84, AMARELO, (1 - k / 0.9) * sai, n=6, grossura=7, giro=-math.pi / 2 - 1.2)

    return _animar(dur, quadro)


def _inscreva(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    return _clicavel(op, icones, 3.2, 1.15, sino=True)


def _siga(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    return _clicavel(op, icones, 2.8, 1.05, sino=False)


def _curtir(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    dur, estouro = 2.8, 0.95
    joinha = _icone("thumbs-up", 150, icones)
    pil_antes = _sombra(_botao(op.texto, op.cor, op.cor_texto, 50))
    pil_depois = _sombra(_botao(op.texto2 or op.texto, op.cor, op.cor_texto, 50))
    jw = joinha.width if joinha is not None else 0

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        pil = pil_antes if t < estouro else pil_depois
        larg = jw + 10 + pil.width
        jx = CX - larg / 2 + jw / 2
        px = CX - larg / 2 + jw + 10 + pil.width / 2 if joinha is not None else CX
        k = (t - estouro) / 0.35
        pulso = 1 + 0.22 * math.sin(math.pi * min(1.0, k)) if t >= estouro else 1
        ang = 18 * math.sin(math.pi * min(1.0, k)) if t >= estouro else 0
        if t >= estouro:
            e = _sai((t - estouro) / 0.4)
            _raios(q, jx, CY - 8, 85 + 50 * e, 105 + 60 * e, op.cor if sum(op.cor[:3]) < 600 else AZUL,
                   (1 - (t - estouro) / 0.5) * sai, n=10, grossura=9)
        _colar(q, joinha, jx, CY - 8, _mola(t / 0.4) * pulso * sai, ang)
        _colar(q, pil, px, CY, _mola((t - 0.15) / 0.4) * sai)

    return _animar(dur, quadro)


def _sininho(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    dur = 2.8
    sino = _icone("bell", 150, icones)
    faixa = _sombra(_botao(op.texto, op.cor, op.cor_texto, 44, pad=(30, 16)))
    sw = sino.width if sino is not None else 0

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        larg = sw + 20 + faixa.width
        sx = CX - larg / 2 + sw / 2
        fx = CX - larg / 2 + sw + 20 + faixa.width / 2 if sino is not None else CX
        _colar(q, faixa, fx, CY + 4, _mola((t - 0.15) / 0.4) * sai)
        ang = 26 * math.sin(t * 17) * (0.3 + 0.7 * abs(math.sin(t * 2.4)))
        _colar(q, sino, sx, CY - 6, _mola(t / 0.4) * sai, ang)
        if sino is not None:  # ondas em volta do sino
            brilho = abs(math.sin(t * 5)) * sai * min(1.0, t / 0.4)
            _raios(q, sx, CY - 20, 92, 116, AMARELO, brilho, n=8, grossura=8, giro=math.pi / 8)

    return _animar(dur, quadro)


def _comente(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    dur = 3.0
    f = _fonte(50)
    caixa = f.getbbox(op.texto)
    bw, bh = max(caixa[2] - caixa[0] + 90, 300), 170
    s = 3
    balao = Image.new("RGBA", (bw * s, (bh + 44) * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(balao)
    d.rounded_rectangle((0, 0, bw * s - 1, bh * s), radius=44 * s, fill=op.cor)
    d.polygon([(60 * s, bh * s - 2), (140 * s, bh * s - 2), (44 * s, (bh + 42) * s)], fill=op.cor)
    balao = balao.resize((bw, bh + 44), Image.LANCZOS)
    ImageDraw.Draw(balao).text(((bw - (caixa[2] - caixa[0])) / 2 - caixa[0], 34 - caixa[1]), op.texto, font=f,
                               fill=op.cor_texto)
    balao = _sombra(balao)
    pontos = (*op.cor_texto[:3], 150)

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        esc = _mola(t / 0.45) * sai
        _colar(q, balao, CX, CY, esc)
        if 0.9 < esc < 1.2 and t > 0.4:  # "digitando…" embaixo do texto
            d = ImageDraw.Draw(q)
            for j in range(3):
                fase = (t * 2.6 - j * 0.3) % 1
                r = 9 + 5 * max(0.0, math.sin(fase * math.pi))
                bx, by = CX - 40 + j * 40, CY - balao.height / 2 + 16 + 126
                d.ellipse((bx - r, by - r, bx + r, by + r), fill=pontos)

    return _animar(dur, quadro)


def _seta_curva(lado: int, cor: tuple) -> Image.Image:
    """Seta curva de compartilhar, desenhada (arco grosso + ponta)."""
    s = 4
    L = lado * s
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.arc((int(L * 0.08), int(L * 0.3), int(L * 0.95), int(L * 1.25)), 190, 275, fill=cor, width=int(L * 0.13))
    d.polygon([(L * 0.58, L * 0.08), (L * 0.98, L * 0.33), (L * 0.58, L * 0.58)], fill=cor)
    return img.resize((lado, lado), Image.LANCZOS)


def _compartilhe(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    dur = 2.8
    seta = _sombra(_seta_curva(110, op.cor), raio=5)
    pil = _sombra(_botao(op.texto, op.cor, op.cor_texto, 50))

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        larg = 130 + pil.width
        ax, px = CX - larg / 2 + 55, CX - larg / 2 + 130 + pil.width / 2
        _colar(q, pil, px, CY, _mola((t - 0.1) / 0.4) * sai)
        if t > 0.3:  # a seta chega num risco, deixando rastro
            k = _sai((t - 0.3) / 0.45)
            for j, alfa in ((3, 0.15), (2, 0.3), (1, 0.5)):
                kj = _sai((t - 0.3 - j * 0.04) / 0.45)
                _colar(q, seta, ax - (1 - kj) * 260, CY - 6, sai, 0, alfa * (1 - k) * sai)
            balanco = 8 * math.sin((t - 0.75) * 7) * math.exp(-(t - 0.75) * 2) if t > 0.75 else 0
            _colar(q, seta, ax - (1 - k) * 260 + balanco, CY - 6, sai)

    return _animar(dur, quadro)


def _marcador(lado: int, cor: tuple, cheio: float) -> Image.Image:
    """Marcador de salvar: contorno branco; `cheio` (0..1) pinta de baixo para cima."""
    s = 4
    w, h = int(lado * 0.72) * s, lado * s
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = int(lado * 0.09 * s)
    pts = [(g, g), (w - g, g), (w - g, h - g), (w / 2, h * 0.7), (g, h - g)]
    if cheio > 0:
        forma = Image.new("L", (w, h), 0)
        ImageDraw.Draw(forma).polygon(pts, fill=255)
        nivel = Image.new("L", (w, h), 0)
        ImageDraw.Draw(nivel).rectangle((0, h * (1 - cheio), w, h), fill=255)
        tinta = Image.new("RGBA", (w, h), cor)
        tinta.putalpha(ImageChops.darker(forma, nivel))
        img.alpha_composite(tinta)
    ImageDraw.Draw(img).line([*pts, pts[0]], fill=BRANCO, width=g, joint="curve")
    return img.resize((w // s, h // s), Image.LANCZOS)


def _salvar(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    dur, clique = 2.8, 1.0
    pil = _sombra(_botao(op.texto, op.cor, op.cor_texto, 50))
    cur = _cursor()
    tinta = AMARELO
    marcadores = [_sombra(_marcador(120, tinta, k / 6), raio=6) for k in range(7)]

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        mw = marcadores[0].width
        larg = mw + 10 + pil.width
        mx, px = CX - larg / 2 + mw / 2, CX - larg / 2 + mw + 10 + pil.width / 2
        cheio = 0 if t < clique else min(6, int((t - clique) / 0.04))
        pulso = 1 + 0.15 * math.sin(math.pi * min(1.0, (t - clique) / 0.3)) if t >= clique else 1
        _colar(q, marcadores[cheio], mx, CY, _mola(t / 0.4) * pulso * sai)
        _colar(q, pil, px, CY, _mola((t - 0.12) / 0.4) * sai)
        _cursor_ate(q, cur, (mx + 10, CY + 10), t, 0.35, clique, clique + 0.5)

    return _animar(dur, quadro)


def _aponta(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    """Botão com a mão apontando para baixo, quicando (Link na bio)."""
    dur = 2.8
    mao = _icone("backhand-index-pointing-down", 90, icones)
    pil = _sombra(_botao(op.texto, op.cor, op.cor_texto, 54))

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        _colar(q, pil, CX, CY - 50, _mola(t / 0.45) * (1 + 0.03 * math.sin(t * 6)) * sai)
        _colar(q, mao, CX, CY + 60 + 16 * abs(math.sin(t * 5)), _mola((t - 0.25) / 0.4) * sai)

    return _animar(dur, quadro)


def _seta_reta(lado: int, cor: tuple) -> Image.Image:
    s = 4
    L = lado * s
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((L * 0.05, L * 0.4, L * 0.6, L * 0.6), fill=cor)
    d.polygon([(L * 0.5, L * 0.15), (L * 0.95, L * 0.5), (L * 0.5, L * 0.85)], fill=cor)
    return img.resize((lado, lado), Image.LANCZOS)


def _parte2(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    dur = 3.0
    grande = _sombra(_botao(op.texto, op.cor, op.cor_texto, 72, pad=(44, 22)))
    pequena = _sombra(_botao(op.texto2, PRETO, BRANCO, 38, _seta_reta(38, BRANCO), pad=(26, 12), icone_depois=True)) \
        if op.texto2 else None

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        _colar(q, grande, CX, CY - 40, _mola(t / 0.45) * sai, -4 * _sai(t / 0.5))
        if t > 0.45:
            k = _sai((t - 0.45) / 0.4)
            _colar(q, pequena, CX + (1 - k) * 200 + 6 * math.sin(t * 7), CY + 62, sai, 0, k)

    return _animar(dur, quadro)


def _assista(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    """Botão com olhos e uma barra de progresso enchendo embaixo."""
    dur = 3.2
    olhos = _icone("eyes", 70, icones)
    pil = _sombra(_botao(op.texto, op.cor, op.cor_texto, 50, olhos, pad=(30, 16)))
    bw, bh = pil.width - 50, 18
    barra = op.cor if sum(op.cor[:3]) > 120 else (230, 33, 23, 255)  # barra preta some no botão preto

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        esc = _mola(t / 0.45) * sai
        _colar(q, pil, CX, CY - 22, esc)
        if 0.95 < esc < 1.2:
            d = ImageDraw.Draw(q)
            x0, y0 = CX - bw / 2, CY - 22 + pil.height / 2 + 6
            d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=bh // 2, fill=(255, 255, 255, 120))
            k = _sai((t - 0.5) / 2.2)
            if k > 0:
                d.rounded_rectangle((x0, y0, x0 + max(bh, bw * k), y0 + bh), radius=bh // 2, fill=barra)
                d.ellipse((x0 + bw * k - 15, y0 + bh / 2 - 15, x0 + bw * k + 15, y0 + bh / 2 + 15), fill=BRANCO,
                          outline=barra, width=5)

    return _animar(dur, quadro)


def _sequencia(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    """Três botões entrando um depois do outro; o texto vem separado por "/" (CURTA / COMENTE / INSCREVA-SE)."""
    dur = 3.4
    partes = [p.strip() for p in op.texto.split("/") if p.strip()][:3] or ["CURTA", "COMENTE", "INSCREVA-SE"]
    nomes_ic = ["thumbs-up", None, "bell"]
    cores = [(AZUL, BRANCO), (PRETO, BRANCO), (op.cor, op.cor_texto)][-len(partes):]
    pecas = [_sombra(_botao(p, cores[k][0], cores[k][1], 42,
                            _icone(nomes_ic[k], 48, icones) if nomes_ic[k] else None, pad=(24, 14)))
             for k, p in enumerate(partes)]
    larg = sum(p.width for p in pecas) - 10 * (len(pecas) - 1)

    def quadro(t: float, q: Image.Image) -> None:
        sai = _saida(t, dur)
        x = CX - larg / 2
        for k, p in enumerate(pecas):
            esc = _mola((t - 0.1 - k * 0.45) / 0.4)
            if t > 1.8:
                esc *= 1 + 0.07 * math.sin((t - 1.8 - k * 0.12) * 10) * math.exp(-(t - 1.8))
            _colar(q, p, x + p.width / 2, CY, esc * sai)
            x += p.width - 10

    return _animar(dur, quadro)


# ---- texto livre: fontes e formatação (como num editor de texto) --------------------------------
# fontes que vêm com o Clipator (todas OFL/Apache, em dados/fontes): id -> (nome, arquivo, arquivo itálico)
FONTES: dict[str, tuple[str, str, str | None]] = {
    "montserrat": ("Montserrat", "Montserrat-ExtraBold.ttf", "Montserrat-ExtraBoldItalic.ttf"),
    "anton": ("Anton", "Anton-Regular.ttf", None),
    "bebas-neue": ("Bebas Neue", "BebasNeue-Regular.ttf", None),
    "bangers": ("Bangers", "Bangers-Regular.ttf", None),
    "special-elite": ("Special Elite (máquina de escrever)", "SpecialElite-Regular.ttf", None),
}
EXT_FONTE = (".ttf", ".otf")
_ARQ_FONTE = re.compile(r"^[\w\-. ]{1,120}\.(ttf|otf)$", re.IGNORECASE)
# chaves de formatação: liga/desliga (padrão)
FORMATO_BOOL = {"negrito": False, "italico": False, "sublinhado": False, "riscado": False, "contorno": True,
                "sombra": True, "maiusculas": False}


def _bool(v: Any, padrao: bool) -> bool:
    if v is None or v == "":
        return padrao
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "sim", "on")
    return bool(v)


def listar_fontes(pasta_fontes: Path | None = None) -> list[dict[str, Any]]:
    """As fontes para o texto livre: as do Clipator, as do pacote do Google Fonts (baixadas quando o usuário
    escolhe) e as que o canal guardou em assets/fontes."""
    from . import fontes

    out = [{"id": k, "nome": v[0], "italico": v[2] is not None, "origem": "clipator", "categoria": "clipator",
            "instalada": True} for k, v in FONTES.items()]
    out += fontes.listar()
    if pasta_fontes is not None and pasta_fontes.is_dir():
        for p in sorted(pasta_fontes.iterdir()):
            if p.is_file() and _ARQ_FONTE.match(p.name):
                out.append({"id": f"canal:{p.name}", "nome": p.stem.replace("-", " ").replace("_", " "), "italico": False,
                            "origem": "canal", "categoria": "canal", "instalada": True})
    return out


def formato(params: dict[str, Any] | None) -> dict[str, Any]:
    """A formatação do texto livre já validada (fonte conhecida ou arquivo simples do canal)."""
    p = params or {}
    fonte = str(p.get("fonte") or "").strip()
    from . import fontes

    if fonte not in FONTES and fontes.info(fonte) is None and not (fonte.startswith("canal:") and _ARQ_FONTE.match(fonte[6:]) and "/" not in fonte):
        fonte = "montserrat"
    return {"fonte": fonte, **{k: _bool(p.get(k), d) for k, d in FORMATO_BOOL.items()}}


def _arquivo_fonte(fmt: dict[str, Any], pasta_fontes: Path | None) -> tuple[Path, bool, list[int] | None]:
    """(arquivo da fonte, já é itálica?, pesos [normal, negrito] se for variável).

    Fonte do canal que sumiu ou do pacote que não foi baixada volta para a Montserrat.
    """
    from . import fontes

    f = fmt["fonte"]
    if f.startswith("canal:") and pasta_fontes is not None:
        p = pasta_fontes / f[6:]
        if p.is_file():
            return p, False, None
        f = "montserrat"
    if f not in FONTES:
        achada = fontes.caminho(f, fmt["italico"])
        if achada is not None:
            return achada
        f = "montserrat"
    nome, arq, arq_it = FONTES[f]
    if fmt["italico"] and arq_it:
        return fontes_dir() / arq_it, True, None
    return fontes_dir() / arq, False, None


def _abrir_fonte(arq: Path, tam: int, pesos: list[int] | None, negrito: bool) -> tuple[ImageFont.FreeTypeFont, bool]:
    """A fonte no tamanho; nas variáveis, já no peso (o negrito usa o peso mais forte). (fonte, negrito já feito?)"""
    f = ImageFont.truetype(str(arq), tam)
    if not pesos:
        return f, False
    alvo = pesos[1] if negrito else pesos[0]
    try:
        eixos = f.get_variation_axes()
        f.set_variation_by_axes([alvo if (e.get("name") in (b"Weight", "Weight") or e.get("name", b"") == b"wght")
                                 else e["default"] for e in eixos])
    except Exception:  # noqa: BLE001 - FreeType sem suporte a fonte variável: fica no peso padrão
        return f, False
    return f, negrito and pesos[1] > pesos[0]


def amostra_fonte(id_: str, pasta_fontes: Path | None, cache: Path) -> Path | None:
    """PNG pequeno com o nome da fonte escrito nela (a lista do editor mostra como cada uma fica)."""
    fmt = formato({"fonte": id_})
    if fmt["fonte"] != id_:
        return None
    from . import fontes

    if id_ not in FONTES and not id_.startswith("canal:") and fontes.caminho(id_, False) is None:
        return None
    arq, _, pesos = _arquivo_fonte(fmt, pasta_fontes)
    nome = next((f["nome"] for f in listar_fontes(pasta_fontes) if f["id"] == id_), id_)
    chave = hashlib.sha1(json.dumps([VERSAO, id_, str(arq), arq.stat().st_mtime_ns]).encode()).hexdigest()[:14]
    destino = cache / f"{chave}.png"
    if not destino.exists():
        f, _ = _abrir_fonte(arq, 40, pesos, False)
        b = f.getbbox(nome)
        img = Image.new("RGBA", (b[2] - b[0] + 12, b[3] - b[1] + 12), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((6 - b[0], 6 - b[1]), nome, font=f, fill=BRANCO)
        cache.mkdir(parents=True, exist_ok=True)
        img.save(destino)
    return destino


def salvar_fonte(pasta_fontes: Path, nome: str, dados: bytes) -> dict[str, Any]:
    """Guarda uma fonte enviada pelo usuário (TTF ou OTF, até 10 MB) nas fontes do canal, se ela abrir de verdade."""
    import io

    if not dados or len(dados) > 10 * 1024 * 1024:
        raise ValueError("A fonte precisa ter até 10 MB.")
    if dados[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ValueError("Envie uma fonte TTF ou OTF.")
    try:
        ImageFont.truetype(io.BytesIO(dados), 40).getbbox("Aa")
    except Exception as exc:  # noqa: BLE001
        raise ValueError("A fonte está corrompida.") from exc
    ext = ".otf" if dados[:4] == b"OTTO" else ".ttf"
    base = re.sub(r"[^\w\-]+", "-", Path(nome or "fonte").stem).strip("-")[:60] or "fonte"
    pasta_fontes.mkdir(parents=True, exist_ok=True)
    arq, n = base + ext, 2
    while (pasta_fontes / arq).exists():
        arq, n = f"{base}-{n}{ext}", n + 1
    (pasta_fontes / arq).write_bytes(dados)
    return {"id": f"canal:{arq}", "nome": base.replace("-", " "), "italico": False, "origem": "canal"}


def _texto_livre(op: Opcoes, icones: Path | None) -> list[Image.Image]:
    """Só o texto digitado (o @ do canal, por exemplo), sem fundo, com a fonte e a formatação escolhidas:
    negrito, itálico, sublinhado, riscado, contorno na `cor`, sombra e caixa alta. Entra com pop."""
    dur = 0.6
    fmt = op.formato or formato(None)
    arq, ja_italica, pesos = _arquivo_fonte(fmt, op.pasta_fontes)
    tam = 72
    f, negrito_feito = _abrir_fonte(arq, tam, pesos, fmt["negrito"])
    texto = op.texto.upper() if fmt["maiusculas"] else op.texto
    borda = 5 if fmt["contorno"] else 0
    grosso = 2 if fmt["negrito"] and not negrito_feito else 0  # negrito sintético: engrossa o traço
    m = borda + grosso + 8
    b = f.getbbox(texto)
    w, h = b[2] - b[0] + 2 * m, b[3] - b[1] + 2 * m + int(tam * 0.18)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    org = (m - b[0], m - b[1])
    linhas = []  # (y, grossura) do sublinhado e do riscado
    esp = max(4, tam // 14)
    if fmt["sublinhado"]:
        linhas.append((m + (b[3] - b[1]) + esp + 2, esp))
    if fmt["riscado"]:
        linhas.append((m + (b[3] - b[1]) // 2, esp))
    x0, x1 = m, w - m
    if borda:
        d.text(org, texto, font=f, fill=op.cor, stroke_width=borda + grosso, stroke_fill=op.cor)
        for y, g in linhas:
            d.rectangle((x0 - borda, y - g // 2 - borda, x1 + borda, y + g - g // 2 + borda), fill=op.cor)
    d.text(org, texto, font=f, fill=op.cor_texto, stroke_width=grosso, stroke_fill=op.cor_texto)
    for y, g in linhas:
        d.rectangle((x0, y - g // 2, x1, y + g - g // 2), fill=op.cor_texto)
    if fmt["italico"] and not ja_italica:  # itálico sintético: inclina o desenho
        k = 0.2
        img = img.transform((w + int(h * k), h), Image.AFFINE, (1, k, -h * k, 0, 1, 0), resample=Image.BICUBIC)
    if fmt["sombra"]:
        img = _sombra(img, raio=5, alfa=110)

    def quadro(t: float, q: Image.Image) -> None:
        _colar(q, img, CX, CY, _mola(t / 0.45))

    return _animar(dur, quadro)


MODELOS: dict[str, Modelo] = {
    "inscreva-se": Modelo("Inscreva-se", ["inscreva-se", "inscrever", "inscrição", "inscrito", "subscribe", "canal"],
                          {"pt": ("INSCREVA-SE", "INSCRITO"), "en": ("SUBSCRIBE", "SUBSCRIBED")}, "vermelho", 3.2,
                          ("click", 1.15), _inscreva),
    "curtir": Modelo("Curtir", ["curtir", "curta", "like", "joinha", "gostei"],
                     {"pt": ("CURTA O VÍDEO", "VALEU!"), "en": ("LIKE THE VIDEO", "THANKS!")}, "branco", 2.8,
                     ("pop", 0.95), _curtir),
    "sininho": Modelo("Ative o sininho", ["sininho", "notificação", "notificações", "sino", "bell"],
                      {"pt": ("ATIVE O SININHO", ""), "en": ("TURN ON NOTIFICATIONS", "")}, "preto", 2.8,
                      ("ding", 0.3), _sininho),
    "comente": Modelo("Comente", ["comente", "comentário", "comentários", "comment", "opinião"],
                      {"pt": ("COMENTE AQUI", ""), "en": ("COMMENT BELOW", "")}, "branco", 3.0, ("pop", 0.1), _comente),
    "compartilhe": Modelo("Compartilhe", ["compartilhe", "compartilhar", "share", "manda"],
                          {"pt": ("COMPARTILHE", ""), "en": ("SHARE", "")}, "neon", 2.8, ("whoosh", 0.25), _compartilhe),
    "salvar": Modelo("Salve o vídeo", ["salvar", "salve", "save", "guardar"],
                     {"pt": ("SALVE PRA DEPOIS", ""), "en": ("SAVE FOR LATER", "")}, "preto", 2.8, ("click", 1.0), _salvar),
    "siga": Modelo("Siga", ["siga", "seguir", "segue", "follow"],
                   {"pt": ("+ SEGUIR", "SEGUINDO"), "en": ("+ FOLLOW", "FOLLOWING")}, "vermelho", 2.8,
                   ("click", 1.05), _siga),
    "link-na-bio": Modelo("Link na bio", ["link", "bio", "descrição", "saiba mais"],
                          {"pt": ("LINK NA BIO", ""), "en": ("LINK IN BIO", "")}, "preto", 2.8, ("pop", 0.1), _aponta),
    "parte-2": Modelo("Parte 2 / Continua", ["parte 2", "continua", "segunda parte", "part 2"],
                      {"pt": ("PARTE 2", "CONTINUA"), "en": ("PART 2", "TO BE CONTINUED")}, "vermelho", 3.0,
                      ("impacto", 0.1), _parte2),
    "assista-ate-o-fim": Modelo("Assista até o fim", ["assista", "até o fim", "final", "espera", "watch"],
                                {"pt": ("ASSISTA ATÉ O FIM", ""), "en": ("WATCH TILL THE END", "")}, "preto", 3.2,
                                ("riser", 0.0), _assista),
    "curta-comente-inscreva": Modelo("Curta · Comente · Inscreva-se", ["curta", "comente", "inscreva-se", "engajamento"],
                                     {"pt": ("CURTA / COMENTE / INSCREVA-SE", ""), "en": ("LIKE / COMMENT / SUBSCRIBE", "")},
                                     "vermelho", 3.4, ("pop", 0.1), _sequencia),
    "texto": Modelo("Texto", ["texto", "arroba", "@", "canal", "escrever", "digitar"],
                    {"pt": ("@seucanal", ""), "en": ("@yourchannel", "")}, "contorno", 5.0, None, _texto_livre,
                    caixa_alta=False, fixo=True),
}


def opcoes(modelo: str, params: dict[str, Any] | None = None) -> dict[str, str]:
    """Texto e cores já resolvidos (vazio = o padrão do idioma e da predefinição de cor)."""
    m = MODELOS[modelo]
    p = params or {}
    idioma = p.get("idioma") if p.get("idioma") in ("pt", "en") else "pt"
    padrao = m.textos[idioma]
    preset = PRESETS.get(str(p.get("preset") or ""), PRESETS[m.preset])

    def txt(v: Any, d: str) -> str:
        t = " ".join(str(v or "").split())[:40] or d
        return t.upper() if m.caixa_alta else t

    cor, cor_t = str(p.get("cor") or ""), str(p.get("cor_texto") or "")
    return {"texto": txt(p.get("texto"), padrao[0]),
            "texto2": txt(p.get("texto2"), padrao[1]) if padrao[1] else "",
            "cor": cor.upper() if _HEX.match(cor) else preset[0],
            "cor_texto": cor_t.upper() if _HEX.match(cor_t) else preset[1]}


def gerar(modelo: str, params: dict[str, Any] | None, destino_dir: Path, icones: Path | None,
          pasta_fontes: Path | None = None) -> Path:
    """O APNG desta chamada com este texto e estas cores; gera só se ainda não estiver em cache."""
    if modelo not in MODELOS:
        raise KeyError(modelo)
    op = opcoes(modelo, params)
    fmt = formato(params) if modelo == "texto" else None
    fonte_canal = pasta_fontes / fmt["fonte"][6:] if fmt and fmt["fonte"].startswith("canal:") and pasta_fontes else None
    id_fonte = [fonte_canal.stat().st_mtime_ns, fonte_canal.stat().st_size] if fonte_canal and fonte_canal.is_file() else None
    if fmt and fmt["fonte"] not in FONTES and not fmt["fonte"].startswith("canal:"):
        from . import fontes

        id_fonte = fontes.caminho(fmt["fonte"], fmt["italico"]) is not None  # baixada ou ainda na Montserrat
    com_icones = icones is not None and (icones / "bell-3d.png").is_file()
    chave = hashlib.sha1(json.dumps([VERSAO, modelo, op, com_icones, fmt, id_fonte], sort_keys=True).encode()).hexdigest()[:14]
    destino = destino_dir / f"{modelo}-{chave}.png"
    if destino.exists():
        return destino
    destino_dir.mkdir(parents=True, exist_ok=True)
    quadros = _recortar(MODELOS[modelo].desenho(
        Opcoes(op["texto"], op["texto2"], _rgba(op["cor"]), _rgba(op["cor_texto"]), fmt, pasta_fontes),
        icones if com_icones else None))
    tmp = destino.with_name(destino.stem + ".tmp.png")
    quadros[0].save(tmp, save_all=True, append_images=quadros[1:], duration=int(1000 / FPS), loop=0, optimize=True)
    tmp.replace(destino)
    return destino


def listar() -> list[dict[str, Any]]:
    """As chamadas para a biblioteca do editor (categoria "chamadas"), com o necessário para editar texto e cor."""
    out = []
    for id_, m in MODELOS.items():
        op = opcoes(id_)
        out.append({"ref": f"cta:{id_}", "nome": m.nome, "categoria": "chamadas", "palavras": m.palavras, "animado": True,
                    "pacote": "Chamadas do Clipator", "licenca": "MIT", "credito": False, "instalado": True,
                    "duracao": m.duracao,
                    "chamada": {"textos": {k: list(v) for k, v in m.textos.items()}, "preset": m.preset,
                                "cor": op["cor"], "cor_texto": op["cor_texto"],
                                "tem_texto2": bool(m.textos["pt"][1]),
                                "som": m.som[0] if m.som else None, "fixo": m.fixo, "caixa_alta": m.caixa_alta}})
    return out
