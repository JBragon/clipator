"""Direções de cenário em camadas: cidade de bolso, jardim de luz, janela e mesa em profundidade.

Com WebGL, os planos têm volume e profundidade reais (o script fica em tres.py). O que está aqui é a alternativa: SVG ou uma
grade de pixels gerada com Pillow, semente fixa, com a paralaxe calculada pela distância de cada plano. Os textos são sempre
estes, em SVG, com ou sem WebGL.
"""

from __future__ import annotations

import base64
import io
import math

from .editoriais import _sombra
from .tres import Direcao3D
from .kit import ALTURA_LINHA, T0, Ctx, ajustar, g, imagem, largura, linhas, retangulo, txt


def _png(img) -> str:
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _mistura(a: tuple, b: tuple, k: float) -> tuple[int, int, int]:
    return tuple(int(x + (y - x) * k) for x, y in zip(a, b))  # type: ignore[return-value]


# ---- 2 · Cidade de bolso ---------------------------------------------------------------------------------------
def _fachadas(r, largura_px: int, altura_px: int, base: int, cor: tuple, janela: tuple, alto: tuple) -> object:
    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (largura_px, altura_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 0
    while x < largura_px:
        w = r.randint(22, 44)
        h = r.randint(*alto)
        d.rectangle((x, base - h, x + w, base), fill=cor + (255,))
        d.rectangle((x, base - h, x + w, base - h + 1), fill=_mistura(cor, (255, 255, 255), 0.18) + (255,))
        for yy in range(base - h + 5, base - 8, 8):
            for xx in range(x + 4, x + w - 4, 7):
                if r.random() < 0.55:
                    d.rectangle((xx, yy, xx + 3, yy + 3), fill=janela + (255,))
        x += w + r.randint(0, 3)
    return im


def _sprite(poses: int, pele: tuple, roupa: tuple, escuro: tuple) -> object:
    """O personagem em poses de caminhada, numa folha de sprites. Desenho próprio, poucas cores, silhueta em degraus."""
    from PIL import Image, ImageDraw

    w, h = 18, 26
    im = Image.new("RGBA", (w * poses, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for p in range(poses):
        x = p * w
        fase = math.sin(2 * math.pi * p / poses)
        pe = int(round(fase * 3))
        d.rectangle((x + 6, 1, x + 12, 7), fill=pele + (255,))
        d.rectangle((x + 6, 1, x + 12, 2), fill=escuro + (255,))
        d.rectangle((x + 5, 8, x + 13, 17), fill=roupa + (255,))
        d.rectangle((x + 7 + pe, 18, x + 8 + pe, 24), fill=escuro + (255,))
        d.rectangle((x + 10 - pe, 18, x + 11 - pe, 24), fill=escuro + (255,))
        d.rectangle((x + 3, 9 + (1 if fase > 0 else 0), x + 4, 15), fill=pele + (255,))
    return im


def _cidade_camadas(c: Ctx) -> dict:
    """Os planos em baixa resolução: pixels quadrados na largura do buffer, repetindo o mesmo mundo em todas as cenas."""
    from PIL import Image, ImageDraw

    cores = c.cores
    bw = int(c.par["largura_buffer"])
    # a altura segue o retângulo da arte, com a altura do buffer como teto: pixels sempre quadrados
    bh = min(int(c.par["altura_buffer"]), max(60, int(bw * c.H / c.W)))
    r = c.rng(11)
    largo = int(bw * 1.8)
    fundo, sup, prim, dest, tx = (_rgb(cores[k]) for k in ("fundo", "superficie", "primaria", "destaque", "texto"))
    ceu = Image.new("RGBA", (bw, bh), fundo + (255,))
    d = ImageDraw.Draw(ceu)
    for _ in range(int(bw * bh / 420)):
        x, y = r.randrange(bw), r.randrange(int(bh * 0.6))
        d.point((x, y), fill=_mistura(fundo, tx, r.uniform(0.3, 0.9)) + (255,))
    chao_y = int(bh * 0.8)
    longe = _fachadas(r, largo, bh, chao_y, _mistura(fundo, sup, 0.55), _mistura(sup, prim, 0.35), (int(bh * 0.28), int(bh * 0.52)))
    perto = _fachadas(r, int(largo * 1.3), bh, chao_y, sup, prim, (int(bh * 0.14), int(bh * 0.34)))
    dd = ImageDraw.Draw(perto)
    dd.rectangle((0, chao_y, int(largo * 1.3), bh), fill=_mistura(fundo, sup, 0.3) + (255,))
    dd.rectangle((0, chao_y, int(largo * 1.3), chao_y + 1), fill=dest + (255,))
    for x in range(0, int(largo * 1.3), 20):
        dd.rectangle((x, chao_y + 9, x + 9, chao_y + 10), fill=_mistura(sup, tx, 0.35) + (255,))
    sprite = _sprite(int(c.par["poses"]), (233, 199, 160), prim, _mistura(fundo, (0, 0, 0), 0.25))
    return {"bw": bw, "bh": bh, "chao": chao_y, "ceu": _png(ceu), "longe": _png(longe), "perto": _png(perto), "sprite": _png(sprite), "largo": largo}


def _cidade_fundo(c: Ctx) -> str:
    m = _cidade_camadas(c)
    return f'<image href="{m["ceu"]}" width="{c.W:g}" height="{c.H:g}" preserveAspectRatio="none" style="image-rendering:pixelated"/>'


def _cidade(c: Ctx) -> str:
    m = _cidade_camadas(c)
    px = c.W / m["bw"]
    alt = m["bh"] * px
    fps = int(c.par["fps_sprite"])
    poses = int(c.par["poses"])
    desloc = float(c.par["deslocamento_camera"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.6)
    parada = t3  # o personagem para quando o dado aparece
    t0 = T0.get()
    mov = c.W * desloc * 2
    nome = f"a-rua{c.k}"
    css = (f"<style>@keyframes {nome}l {{ to {{ transform: translateX({-mov:.0f}px); }} }} @keyframes {nome}p {{ to {{ transform: translateX({-mov * 1.5:.0f}px); }} }}"
           f" @keyframes {nome}s {{ to {{ transform: translateX({-poses * 18 * px * 0.95:.1f}px); }} }}</style>")
    wl = m["largo"] * px
    wp = wl * 1.3
    trav = f"{max(0.3, parada):.2f}s steps({max(6, int(parada * 12))}) {t0:.3f}s both"
    fundos = (f'<image class="an" href="{m["longe"]}" width="{wl:.0f}" height="{alt:.0f}" preserveAspectRatio="none" style="image-rendering:pixelated;animation:{nome}l {trav}"/>'
              f'<image class="an" href="{m["perto"]}" width="{wp:.0f}" height="{alt:.0f}" preserveAspectRatio="none" style="image-rendering:pixelated;animation:{nome}p {trav}"/>')
    # o personagem: a folha de sprites anda em passos atrás de uma janela de um quadro; a pose vem do tempo
    sp = 18 * px * 0.95
    sa = 26 * px * 0.95
    xs = c.W * 0.2
    ys = m["chao"] * px - sa + 2 * px
    ciclos = max(1, int(parada * fps / poses))
    clip = f'<clipPath id="spr{c.k}"><rect x="{xs:.1f}" y="{ys:.1f}" width="{sp:.1f}" height="{sa:.1f}"/></clipPath>'
    pers = (f'<g clip-path="url(#spr{c.k})"><image class="an" href="{m["sprite"]}" x="{xs:.1f}" y="{ys:.1f}" width="{sp * poses:.1f}" height="{sa:.1f}" preserveAspectRatio="none" '
            f'style="image-rendering:pixelated;animation:{nome}s {poses / fps:.3f}s steps({poses}) {t0:.3f}s {ciclos}"/></g>')
    out = [css, f"<defs>{clip}</defs>", f'<g class="so-2d">{fundos}{pers}</g>']
    # a placa é desenhada em resolução normal e fica no céu, longe da rua
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw - 60, c.lh * 0.42, 3, 64, 38)
    h = len(ls) * tam * ALTURA_LINHA + 38
    y = c.y0 + 6
    corpo = retangulo(c.x0, y, c.lw, h, "var(--superficie)", 0, 'stroke="var(--primaria)" stroke-width="6"') + linhas(c.x0 + 30, y + 14 + tam, ls, tam)
    out.append(g(corpo, t2, "a-desce", 0.3, curva="steps(5)"))
    if c.nota:
        lt, tt = ajustar(c.nota.upper(), c.fonte_titulo, c.lw * 0.6, 90, 1, 70, 40)
        w = largura(lt[0], c.fonte_titulo, tt) + 40
        xb = c.x1 - w
        yb = y + h + 18
        out.append(g(retangulo(xb, yb, w, tt * 1.3, "var(--primaria)", 0) + txt(xb + 20, yb + tt, lt[0], tt, "var(--sobre-primaria)", "t"), t3, "a-pop", 0.3, curva="steps(4)"))
    return "".join(out)


# ---- 10 · Jardim de luz ------------------------------------------------------------------------------------------
def _folhagem(r, cx: float, cy: float, raio: float, n: int, cor: str) -> str:
    """Uma massa de folhas recortadas: cada folha é um polígono de semente fixa, papel de borda clara."""
    out = []
    for _ in range(n):
        a = r.uniform(0, 2 * math.pi)
        d = raio * r.uniform(0, 1) ** 0.6
        x, y = cx + d * math.cos(a), cy + d * math.sin(a) * 0.85
        comp = raio * r.uniform(0.32, 0.5)
        larg = comp * 0.36
        ang = math.degrees(a) + r.uniform(-30, 30)
        out.append(f'<path transform="translate({x:.0f} {y:.0f}) rotate({ang:.0f})" d="M{-comp:.0f} 0Q0 {-larg:.0f} {comp:.0f} 0Q0 {larg:.0f} {-comp:.0f} 0Z" fill="{cor}" '
                   'stroke="var(--texto)" stroke-opacity=".22" stroke-width="2"/>')
    return "".join(out)


def _jardim_fundo(c: Ctx) -> str:
    return (f'<defs><radialGradient id="lua" cx=".5" cy=".42" r=".7"><stop offset="0" stop-color="var(--superficie)"/>'
            f'<stop offset="1" stop-color="var(--fundo)"/></radialGradient></defs><rect width="{c.W:g}" height="{c.H:g}" fill="url(#lua)"/>')


def _jardim(c: Ctx) -> str:
    n = int(c.par["camadas"])
    bal = float(c.par["balanco_graus"])
    ap = float(c.par["aproximacao_relativa"])
    n_luz = int(c.par["luzes"])
    r = c.rng(5)
    t1, t2, t3, t4 = c.fases(4, leitura=1.6)
    t0 = T0.get()
    # o caminho da luz: uma curva em diagonal até a clareira, com a posição em tempo absoluto
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw * 0.66, c.lh * 0.42, 4, 60, 38)
    ht = len(ls) * tam * ALTURA_LINHA + 44
    wt = max(largura(s, c.fonte_corpo, tam) for s in ls) + 72
    xt, yt = (c.W - wt) / 2, c.y0 + (c.lh - ht) / 2
    camadas = []
    for k in range(n):
        prof = (k + 1) / n
        tom = f"color-mix(in srgb, var(--destaque) {38 + 40 * (1 - prof):.0f}%, var(--fundo))"
        massas = []
        for lado in (0, 1):
            for _ in range(2):
                cx = (-40 + 160 * prof * r.uniform(0.5, 1)) if lado == 0 else (c.W + 40 - 160 * prof * r.uniform(0.5, 1))
                cy = r.uniform(0.05, 1) * c.H
                massas.append(_folhagem(r, cx, cy, 110 + 130 * prof, 26, tom))
        fase = r.uniform(1.6, 3.2)
        camadas.append(f'<g class="an deco" style="transform-box:view-box;transform-origin:{50 + 10 * (k % 2 * 2 - 1)}% 100%;'
                       f'animation:a-balanco {fase:.2f}s ease-in-out {t0 - r.uniform(0, fase):.3f}s infinite alternate;--b:{bal * prof:.2f}deg">{"".join(massas)}</g>')
    px0, py0 = c.x0 + 30, c.y1 - 20
    px1, py1 = xt + wt / 2, yt + ht + 16
    caminho = f"M{px0:.0f} {py0:.0f}C{c.W * 0.25:.0f} {c.H * 0.55:.0f} {c.W * 0.7:.0f} {c.H * 0.95:.0f} {px1:.0f} {py1:.0f}"
    luzes = []
    for i in range(n_luz):  # as outras luzes ficam paradas e fracas; a principal percorre o caminho
        lx, ly = r.uniform(c.x0, c.x1), r.uniform(c.y0, c.y1)
        if xt - 30 < lx < xt + wt + 30 and yt - 30 < ly < yt + ht + 30:
            continue
        luzes.append(f'<circle cx="{lx:.0f}" cy="{ly:.0f}" r="{r.uniform(4, 8):.0f}" fill="var(--primaria)" opacity="{r.uniform(.35, .7):.2f}"/>')
    principal = (f'<g class="an" style="offset-path:path(\'{caminho}\');offset-rotate:0deg;animation:a-luz {max(0.6, t3 - t1):.2f}s cubic-bezier(.45,0,.3,1) {t1 + t0:.3f}s both">'
                 f'<circle r="42" fill="var(--primaria)" opacity=".25"/><circle r="16" fill="var(--primaria)"/></g>')
    # a câmera se aproxima devagar; o texto fica imóvel, numa abertura de contraste uniforme
    cena = (f'<g class="an" style="transform-box:view-box;transform-origin:50% 50%;--z:{1 + ap:.3f};animation:a-aproxima {c.dur:.2f}s linear {t0:.3f}s both">'
            f'{"".join(camadas)}<g class="deco">{"".join(luzes)}</g></g>')
    corpo = retangulo(xt, yt, wt, ht, "var(--fundo)", 18, 'stroke="var(--primaria)" stroke-opacity=".55" stroke-width="3"') + linhas(c.W / 2, yt + 22 + tam, ls, tam, ancora="middle")
    return f'<g class="so-2d">{cena}{principal}</g>' + g(corpo, t2, "a-fade", 0.6)


_CSS_JARDIM = """
@keyframes a-balanco { from { transform: rotate(calc(var(--b) * -1)); } to { transform: rotate(var(--b)); } }
@keyframes a-luz { from { offset-distance: 0%; } to { offset-distance: 100%; } }
@keyframes a-aproxima { from { transform: scale(1); } to { transform: scale(var(--z)); } }
"""


# ---- 12 · Janela em profundidade ---------------------------------------------------------------------------------
def _planos(c: Ctx, n: int) -> list[tuple[float, str]]:
    """(profundidade, SVG) de cada plano: morros recortados do fundo para a frente, com semente fixa."""
    r = c.rng(21)
    out = []
    for k in range(n):
        prof = 1 - k / max(1, n - 1)  # 1 = longe
        base = c.H * (0.42 + 0.52 * (1 - prof))
        pts = [f"-120,{c.H + 40:.0f}"]
        x = -120.0
        while x < c.W + 120:
            pts.append(f"{x:.0f},{base + r.uniform(-1, 1) * (40 + 60 * (1 - prof)):.0f}")
            x += r.uniform(70, 170)
        pts.append(f"{c.W + 120:.0f},{c.H + 40:.0f}")
        cor = f"color-mix(in srgb, var(--destaque) {100 * prof:.0f}%, var(--fundo))" if k % 2 else f"color-mix(in srgb, var(--primaria) {100 * prof:.0f}%, var(--fundo))"
        out.append((prof, f'<polygon points="{" ".join(pts)}" fill="{cor}"/>'))
    return out


def _janela(c: Ctx) -> str:
    n = int(c.par["camadas"])
    prl = float(c.par["paralaxe_maxima"])
    folga = float(c.par["folga_borda"])
    blur = float(c.par["desfoque_maximo_px"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.5)
    t0 = T0.get()
    hb = min(190.0, c.lh * 0.3)
    jx, jy = c.x0, c.y0
    jw, jh = c.lw, c.lh - hb - 14
    anima = f"{max(1.0, c.dur - 0.4):.2f}s cubic-bezier(.4,0,.3,1) {t0 + 0.2:.3f}s both"
    defs = (f'<clipPath id="jan{c.k}"><rect x="{jx:.0f}" y="{jy:.0f}" width="{jw:.0f}" height="{jh:.0f}" rx="4"/></clipPath>'
            f'<filter id="jd{c.k}"><feGaussianBlur stdDeviation="{blur:.2f}"/></filter>')
    foto = imagem(c, jx - jw * folga, jy - jh * folga, jw * (1 + 2 * folga), jh * (1 + 2 * folga))
    if foto:  # imagem inteira: pan único, sem simular camadas que não existem
        plano = f'<g class="an" style="--p:{-jw * prl:.0f}px;animation:a-pan {anima}">{foto}</g>'
    else:
        plano = (f'<rect x="{jx:.0f}" y="{jy:.0f}" width="{jw:.0f}" height="{jh:.0f}" fill="color-mix(in srgb, var(--texto) 42%, var(--primaria))"/>'
                 f'<circle cx="{jx + jw * 0.68:.0f}" cy="{jy + jh * 0.3:.0f}" r="{jh * 0.16:.0f}" fill="var(--texto)"/>')
        for prof, s in _planos(c, n):
            d = jw * prl * (1 - prof) * 2 + jw * prl * 0.2  # o plano de perto anda mais: deslocamento = câmera × (1 - profundidade)
            f = f' filter="url(#jd{c.k})"' if prof > 0.8 and blur > 0 and not c.leve else ""
            plano += f'<g class="an" style="--p:{-d:.0f}px;animation:a-pan {anima}"{f}>{s}</g>'
    classe = "" if foto else ' class="so-2d"'  # a foto fica sempre aqui: a profundidade só vale para os planos desenhados
    out = [f"<defs>{defs}</defs>", f'<g{classe} clip-path="url(#jan{c.k})">{plano}</g>']
    # as folhas laterais abrem e revelam a imagem; o detalhe ganha uma seta curta
    w2 = jw / 2 + 2
    folhas = (f'<g class="an" style="--x:{-w2:.0f}px;animation:a-folha .7s cubic-bezier(.5,0,.2,1) {t1 + t0:.3f}s both"><rect x="{jx:.0f}" y="{jy:.0f}" width="{w2:.0f}" height="{jh:.0f}" fill="var(--fundo)"/></g>'
              f'<g class="an" style="--x:{w2:.0f}px;animation:a-folha .7s cubic-bezier(.5,0,.2,1) {t1 + t0:.3f}s both"><rect x="{jx + jw - w2:.0f}" y="{jy:.0f}" width="{w2:.0f}" height="{jh:.0f}" fill="var(--fundo)"/></g>')
    out.append(f'<g{classe} clip-path="url(#jan{c.k})">{folhas}</g>')
    if c.nota:
        lt, tt = ajustar(c.nota, c.fonte_corpo, jw * 0.5, 100, 2, 44, 34)
        wn = max(largura(s, c.fonte_corpo, tt) for s in lt) + 32
        hn = len(lt) * tt * ALTURA_LINHA + 18
        xn, yn = jx + jw - wn - 24, jy + 24
        corpo = (retangulo(xn, yn, wn, hn, "var(--fundo)", 4) + linhas(xn + 16, yn + 8 + tt, lt, tt)
                 + f'<path d="M{xn + wn / 2:.0f} {yn + hn:.0f}v46m-14 -14l14 14l14 -14" fill="none" stroke="var(--primaria)" stroke-width="6" stroke-linecap="round"/>')
        out.append(g(corpo, t3, "a-sobe", 0.35))
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw, hb - 10, 3, 54, 36)
    out.append(g(linhas(c.x0, c.y1 - hb + 10 + tam, ls, tam), t2, "a-fade", 0.4))
    return "".join(out)


_CSS_JANELA = """
@keyframes a-pan { from { transform: translateX(0); } to { transform: translateX(var(--p)); } }
@keyframes a-folha { from { transform: translateX(0); } to { transform: translateX(var(--x)); } }
"""


# ---- 22 · Mesa em profundidade -----------------------------------------------------------------------------------
def _mesa_fundo(c: Ctx) -> str:
    return (retangulo(0, 0, c.W, c.H, "var(--fundo)")
            + f'<path d="M0 {c.H * 0.3:.0f}H{c.W:.0f}" stroke="var(--superficie)" stroke-width="3"/>'
            + "".join(f'<path d="M{c.W / 2:.0f} {c.H * 0.3:.0f}L{c.W * i / 6:.0f} {c.H:.0f}" stroke="var(--superficie)" stroke-width="2" opacity=".5"/>' for i in range(7)))


def _mesa(c: Ctx) -> str:
    n = int(c.par["cartoes"])
    prl = float(c.par["paralaxe_maxima"])
    av = float(c.par["avanco_relativo"])
    rot = float(c.par["rotacao_maxima_graus"])
    itens = c.itens(n)
    n = max(1, len(itens))
    r = c.rng(9)
    ts = c.fases(n, leitura=1.5)
    t0 = T0.get()
    wc = c.lw * 0.64
    hc = c.lh * 0.42
    out = [f"<defs>{_sombra('sombra-m', 10, .3)}</defs>"]
    guia = []
    cartoes = []
    for i in range(n - 1, -1, -1):  # de trás para a frente: a ordem de leitura vem da posição
        prof = i / max(1, n - 1)
        escala = 0.74 + 0.26 * (1 - prof)
        x = c.x0 + (c.lw - wc * escala) * prof
        y = c.y0 + c.lh * 0.34 * (1 - prof)
        ls, tam = ajustar(itens[i], c.fonte_corpo, wc - 60, hc - 80, 3, 62, 36)
        placa = retangulo(0, 0, wc, hc, "var(--superficie)", 6, 'filter="url(#sombra-m)" stroke="var(--fundo)" stroke-width="10"')
        corpo = (f'<g class="so-2d">{placa}</g>'
                 + txt(30, 50, f"{i + 1:02d}", 40, "var(--texto)", "t") + linhas(30, 70 + tam, ls, tam))
        # cada cartão avança quando é dito e volta ao trilho quando o próximo entra
        inicio = ts[i]
        fim = ts[i + 1] if i + 1 < n else c.dur
        d = max(0.5, fim - inicio)
        ang = r.uniform(-rot, rot)
        nome = f"a-avanca{c.k}-{i}"
        passo = c.H * av * 0.4
        kf = (f"@keyframes {nome} {{ 0% {{ transform: translateY(0) scale(1); }} {min(30, 100 * 0.45 / d):.0f}% {{ transform: translateY({passo:.0f}px) scale(1.08); }} "
              f"{max(70, 100 - 100 * 0.45 / d):.0f}% {{ transform: translateY({passo:.0f}px) scale(1.08); }} 100% {{ transform: translateY({0 if i + 1 < n else passo:.0f}px) scale({1 if i + 1 < n else 1.08}); }} }}")
        cartoes.append(f'<style>{kf}</style><g data-cartao="{i}" transform="translate({x:.0f} {y:.0f}) rotate({ang:.1f}) scale({escala:.3f})">'
                       f'<g class="an mesa-av" style="transform-box:fill-box;transform-origin:50% 100%;animation:{nome} {d:.2f}s cubic-bezier(.3,0,.2,1) {inicio + t0:.3f}s both">{corpo}</g></g>')
        guia.append(g(f'<circle cx="{c.x1 - 14:.0f}" cy="{c.y0 + 30 + i * 50:.0f}" r="11" fill="var(--primaria)"/>', inicio, "a-pop", 0.3))
    # a câmera desloca poucos pontos para o lado: tudo na mesma razão, sem acumular nada entre seeks
    desloc = c.W * prl
    out.append(f'<g class="an mesa-av" style="--p:{-desloc:.0f}px;animation:a-pan {c.dur:.2f}s linear {t0:.3f}s both">{"".join(cartoes)}</g>')
    out.append("".join(f'<circle cx="{c.x1 - 14:.0f}" cy="{c.y0 + 30 + i * 50:.0f}" r="11" fill="none" stroke="var(--suave)" stroke-width="3"/>' for i in range(n)) + "".join(guia))
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw, c.lh * 0.2, 2, 46, 34)
    out.append(g(retangulo(c.x0 - 12, c.y1 - len(ls) * tam * ALTURA_LINHA - 22, c.lw + 24, len(ls) * tam * ALTURA_LINHA + 22, "var(--fundo)", 4)
                 + linhas(c.x0, c.y1 - len(ls) * tam * ALTURA_LINHA - 8 + tam, ls, tam), ts[0], "a-fade", 0.4))
    return "".join(out)


def _dados_janela(c: Ctx) -> dict:
    hb = min(190.0, c.lh * 0.3)
    return {"recorte": [c.x0 / c.W, c.y0 / c.H, c.lw / c.W, (c.lh - hb - 14) / c.H]}


def _dados_mesa(c: Ctx) -> dict:
    itens = c.itens(int(c.par["cartoes"]))
    n = max(1, len(itens))
    return {"n": n, "ts": c.fases(n, leitura=1.5), "wc": c.lw * 0.64}


_MESA_3D = "body.tres-d .mesa-av { animation: none !important; }\n"

DIRECOES = {
    "cidade-de-bolso": Direcao3D(_cidade, _cidade_fundo, cfg={"perspectiva": 24, "pixel": 270, "semChao": True}),
    "jardim-de-luz": Direcao3D(_jardim, _jardim_fundo, _CSS_JARDIM, {"perspectiva": 38, "noite": True, "semChao": True}),
    "janela-em-profundidade": Direcao3D(_janela, lambda c: retangulo(0, 0, c.W, c.H, "var(--fundo)"), _CSS_JANELA,
                                        {"perspectiva": 30, "semChao": True, "janelaMeia": 4.2}, _dados_janela),
    "mesa-em-profundidade": Direcao3D(_mesa, _mesa_fundo, _CSS_JANELA + _MESA_3D, {"perspectiva": 30, "semChao": True}, _dados_mesa),
}
