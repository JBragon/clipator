# /// script
# requires-python = ">=3.10"
# dependencies = ["fonttools", "pillow"]
# ///
"""Gera a marca do Clipator (SVG e PNG) a partir de uma geometria só.

Rode da raiz do repositório:  uv run docs/marca/gerar_marca.py

O símbolo é um C amarelo com um recorte de "play" que se abre em dois cortes
para a direita. O texto usa a Montserrat ExtraBold que já vem no motor
(SIL OFL 1.1), convertida em contorno para não depender da fonte instalada.
"""
from __future__ import annotations

import math
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[2]
MARCA = RAIZ / "docs" / "marca"
RECURSOS = RAIZ / "app" / "resources"
PUBLICO = RAIZ / "app" / "src" / "renderer" / "public"
FONTE = RAIZ / "motor" / "src" / "clipator" / "dados" / "fontes" / "Montserrat-ExtraBold.ttf"

AMARELO = "#ECEC2E"
ESCURO = "#141518"
BRANCO = "#FFFFFF"

# --- geometria do símbolo (unidades: o C mede 212 x 316) -------------------
C_L, C_A, C_R = 212.0, 316.0, 60.0
# recorte: triângulo de play cuja ponta se abre em dois cortes até a borda
RECORTE = [(67, 104), (150, 146), (240, 112), (240, 204), (150, 170), (67, 212)]
RAIO_RECORTE = [9, 6, 0, 0, 6, 9]


def _arredondar(pts, raios):
    """Polígono com cantos arredondados: lista de (ponto, controle, ponto) por vértice."""
    n = len(pts)
    cantos = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        r = raios[i]
        if r == 0:
            cantos.append((p1, p1, p1))
            continue
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        a = (p1[0] + v1[0] / l1 * r, p1[1] + v1[1] / l1 * r)
        b = (p1[0] + v2[0] / l2 * r, p1[1] + v2[1] / l2 * r)
        cantos.append((a, p1, b))
    return cantos


def _caminho_recorte(dx, dy, s):
    f = lambda p: f"{dx + p[0] * s:.2f} {dy + p[1] * s:.2f}"
    cantos = _arredondar(RECORTE, RAIO_RECORTE)
    d = f"M{f(cantos[0][2])}"
    for a, c, b in cantos[1:] + cantos[:1]:
        d += f"L{f(a)}Q{f(c)} {f(b)}"
    return d + "Z"


def _pontos_recorte(dx, dy, s, passos=8):
    pts = []
    for a, c, b in _arredondar(RECORTE, RAIO_RECORTE):
        for k in range(passos + 1):
            t = k / passos
            x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0]
            y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]
            pts.append((dx + x * s, dy + y * s))
    return pts


def _simbolo_svg(dx, dy, s, cor, ident):
    """O C, como máscara: retângulo arredondado menos o recorte."""
    return (
        f'<mask id="{ident}" maskUnits="userSpaceOnUse">'
        f'<rect x="{dx:.2f}" y="{dy:.2f}" width="{C_L * s:.2f}" height="{C_A * s:.2f}" '
        f'rx="{C_R * s:.2f}" fill="#fff"/>'
        f'<path d="{_caminho_recorte(dx, dy, s)}" fill="#000"/></mask>'
        f'<rect x="{dx:.2f}" y="{dy:.2f}" width="{C_L * s:.2f}" height="{C_A * s:.2f}" '
        f'rx="{C_R * s:.2f}" fill="{cor}" mask="url(#{ident})"/>'
    )


# Ladrilho do ícone: quadrado escuro arredondado com o C no meio
LADO, LADO_R = 512.0, 112.0
C_ESCALA = 300.0 / C_A  # o C ocupa ~59% da altura do ladrilho


def _icone_svg(x0, y0, lado, ident):
    k = lado / LADO
    s = C_ESCALA * k
    dx = x0 + (lado - C_L * s) / 2
    dy = y0 + (lado - C_A * s) / 2
    return (
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{lado:.2f}" height="{lado:.2f}" '
        f'rx="{LADO_R * k:.2f}" fill="{ESCURO}"/>' + _simbolo_svg(dx, dy, s, AMARELO, ident)
    )


def _texto(texto, altura_maiuscula, x0, y_base):
    """Contorno do texto em SVG; devolve (path d, largura)."""
    fonte = TTFont(FONTE)
    gs = fonte.getGlyphSet()
    cmap = fonte.getBestCmap()
    cap = fonte["OS/2"].sCapHeight
    esc = altura_maiuscula / cap
    hmtx = fonte["hmtx"]
    caneta = SVGPathPen(gs)
    x = 0.0
    nomes = [cmap[ord(ch)] for ch in texto]
    kern = _kerning(fonte)
    for i, nome in enumerate(nomes):
        t = TransformPen(caneta, (esc, 0, 0, -esc, x0 + x * esc, y_base))
        gs[nome].draw(t)
        x += hmtx[nome][0]
        if i + 1 < len(nomes):
            x += kern.get((nome, nomes[i + 1]), 0)
    return caneta.getCommands(), x * esc


def _kerning(fonte):
    pares = {}
    if "GPOS" not in fonte:
        return pares
    for lookup in fonte["GPOS"].table.LookupList.Lookup:
        for sub in lookup.SubTable:
            sub = getattr(sub, "ExtSubTable", sub)
            if getattr(sub, "Format", None) == 1 and hasattr(sub, "PairSet"):
                cobertura = sub.Coverage.glyphs
                for g1, ps in zip(cobertura, sub.PairSet):
                    for pv in ps.PairValueRecord:
                        v = pv.Value1.XAdvance if pv.Value1 and hasattr(pv.Value1, "XAdvance") else 0
                        pares.setdefault((g1, pv.SecondGlyph), v)
            elif getattr(sub, "Format", None) == 2:
                c1 = sub.ClassDef1.classDefs
                c2 = sub.ClassDef2.classDefs
                for g1 in sub.Coverage.glyphs:
                    rec = sub.Class1Record[c1.get(g1, 0)]
                    for g2, k2 in c2.items():
                        v1 = rec.Class2Record[k2].Value1
                        v = getattr(v1, "XAdvance", 0) if v1 else 0
                        if v:
                            pares.setdefault((g1, g2), v)
    return pares


def _svg(largura, altura, corpo, titulo="Clipator"):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura:.0f} {altura:.0f}" '
        f'width="{largura:.0f}" height="{altura:.0f}" role="img" aria-label="{titulo}">'
        f"<title>{titulo}</title>{corpo}</svg>\n"
    )


def gerar_svgs():
    MARCA.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    # 1. ícone (ladrilho escuro + C amarelo)
    arquivos["clipator-icone.svg"] = _svg(512, 512, _icone_svg(0, 0, 512, "c"))
    # 2. só o símbolo, amarelo
    arquivos["clipator-simbolo.svg"] = _svg(C_L, C_A, _simbolo_svg(0, 0, 1, AMARELO, "c"))

    # 3. horizontal: ladrilho + "Clipator"
    lado = 160.0
    cap = 78.0
    gap = 34.0
    base = lado / 2 + cap / 2
    d, larg = _texto("Clipator", cap, lado + gap, base)
    L = lado + gap + larg + 4
    # descendente do "p" passa da linha de base: altura total = lado
    for nome, cor in (("escuro", BRANCO), ("claro", ESCURO)):
        corpo = _icone_svg(0, 0, lado, "c") + f'<path d="{d}" fill="{cor}"/>'
        arquivos[f"clipator-horizontal-{nome}.svg"] = _svg(L, lado, corpo)

    # 4. uma cor: o C vazado + texto, numa cor só (branco ou preto)
    s = lado / C_A
    cl = C_L * s
    d1, larg1 = _texto("Clipator", cap, cl + gap, base)
    L1 = cl + gap + larg1 + 4
    for nome, cor in (("branco", BRANCO), ("preto", "#000000")):
        corpo = _simbolo_svg(0, 0, s, cor, "c") + f'<path d="{d1}" fill="{cor}"/>'
        arquivos[f"clipator-uma-cor-{nome}.svg"] = _svg(L1, lado, corpo)

    for nome, conteudo in arquivos.items():
        (MARCA / nome).write_text(conteudo, encoding="utf-8")
    PUBLICO.mkdir(parents=True, exist_ok=True)
    (PUBLICO / "favicon.svg").write_text(arquivos["clipator-icone.svg"], encoding="utf-8")
    return arquivos


def _desenhar_icone(lado_px):
    """O mesmo ícone em PNG, desenhado em 8x e reduzido (sem depender de renderizador SVG)."""
    ss = 8
    L = lado_px * ss
    k = L / LADO
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle((0, 0, L - 1, L - 1), radius=LADO_R * k, fill=ESCURO)
    s = C_ESCALA * k
    dx = (L - C_L * s) / 2
    dy = (L - C_A * s) / 2
    dr.rounded_rectangle((dx, dy, dx + C_L * s, dy + C_A * s), radius=C_R * s, fill=AMARELO)
    dr.polygon(_pontos_recorte(dx, dy, s), fill=ESCURO)
    mascara = Image.new("L", (L, L), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, L - 1, L - 1), radius=LADO_R * k, fill=255)
    img.putalpha(mascara)
    return img.resize((lado_px, lado_px), Image.LANCZOS)


def gerar_pngs():
    RECURSOS.mkdir(parents=True, exist_ok=True)
    grande = _desenhar_icone(1024)
    grande.save(RECURSOS / "icon.png")
    tamanhos = [16, 24, 32, 48, 64, 128, 256]
    _desenhar_icone(256).save(RECURSOS / "icon.ico", sizes=[(t, t) for t in tamanhos])
    _desenhar_icone(512).save(MARCA / "clipator-icone.png")


if __name__ == "__main__":
    gerar_svgs()
    gerar_pngs()
    print("marca gerada em", MARCA, "e", RECURSOS)
