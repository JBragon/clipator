"""Direções de papel e texto: anotação, arquivo, letras, recortes, revista e caderno. SVG e CSS, medidos com a fonte real."""

from __future__ import annotations

import unicodedata
from types import SimpleNamespace

from .kit import ALTURA_LINHA, Ctx, ajustar, g, imagem, largura, linhas, peca, retangulo, ruido, traco, txt


def _papel(c: Ctx, op: float = 0.05, freq: float = 0.9) -> str:
    """Papel com fibra quase invisível; o ruído é fixo no tempo e fica fora da alternativa leve."""
    return (f'<defs>{ruido("fibra", c.semente, freq)}</defs>{retangulo(0, 0, c.W, c.H, "var(--fundo)")}'
            f'<rect class="deco" width="{c.W}" height="{c.H}" filter="url(#fibra)" opacity="{op}"/>')


def _sombra(ident: str = "sombra-curta", d: float = 5, a: float = 0.22) -> str:
    return (f'<filter id="{ident}" x="-10%" y="-10%" width="120%" height="125%"><feDropShadow dx="0" dy="{d}" stdDeviation="{d}" '
            f'flood-color="#000" flood-opacity="{a}"/></filter>')


# ---- 11 · Anotação em foco ---------------------------------------------------------------------------------------
def _anotacao_fundo(c: Ctx) -> str:
    x = c.x0 + c.lw * (1 - float(c.par.get("largura_margem_relativa", 0.16))) - 8
    return _papel(c) + f'<path d="M{x:.0f} 0V{c.H:.0f}" stroke="var(--superficie)" stroke-width="3"/>'


def _anotacao(c: Ctx) -> str:
    margem = c.lw * float(c.par["largura_margem_relativa"])
    larg = c.lw - margem - 44
    pal = c.texto.split()[: int(c.par["max_palavras"])]
    ls, tam = ajustar(" ".join(pal), c.fonte_corpo, larg, c.lh * 0.8, int(c.par["max_linhas"]), 92, 44)
    alt_l = tam * ALTURA_LINHA
    y = c.y0 + (c.lh - alt_l * len(ls)) / 2 + tam * 0.92
    t1, t2, t3, t4 = c.fases(4, leitura=1.4)
    if c.leve:
        t1 = t2 = t3 = t4 = 0.05
    nota = c.nota
    ativa = next((i for i, s in enumerate(ls) if nota and nota.lower() in s.lower()), len(ls) - 1)  # a linha da nota; sem achar, a última
    meio = max(1, len(ls) // 2)
    out = []
    yb = y + ativa * alt_l
    wf = largura(ls[ativa], c.fonte_corpo, tam)
    out.append(g(retangulo(c.x0 - 10, yb - tam * 0.84, wf + 20, alt_l * 0.98, "var(--da-cor-realce, var(--destaque))", 4, f'opacity="{float(c.par["opacidade_faixa"])}"'),
                 t3, "a-abre-x", 0.5))
    if len(ls) > 1:
        out.append(g(linhas(c.x0, y, ls[:meio], tam), t1, "a-sobe", 0.4))
        out.append(g(linhas(c.x0, y + meio * alt_l, ls[meio:], tam), t2, "a-sobe", 0.4))
    else:  # uma linha só: dois grupos de palavras, cada um quando é dito
        ws = ls[0].split()
        a, b = " ".join(ws[: max(1, len(ws) // 2)]), " ".join(ws[max(1, len(ws) // 2):])
        out.append(g(txt(c.x0, y, a, tam), t1, "a-sobe", 0.4))
        if b:
            out.append(g(txt(c.x0 + largura(a + " ", c.fonte_corpo, tam), y, b, tam), t2, "a-sobe", 0.4))
    xc = c.x0 + larg + 18
    y0, y1 = yb - tam * 0.9, yb + tam * 0.3
    out.append(traco(f"M{xc:.0f} {y0:.0f}h16V{y1:.0f}h-16", "var(--primaria)", 6, t3 + 0.15, 0.45))
    if nota:
        ln, tn = ajustar(nota, c.fonte_titulo, margem - 6, c.lh * 0.4, 3, 60, 38)
        yn = max(c.y0 + tn, min((y0 + y1) / 2 - (len(ln) - 1) * tn * 0.6 + tn * 0.35, c.y1 - tn * len(ln)))
        out.append(g(linhas(xc + 26, yn, ln, tn, "var(--acento)", "t"), t4, "a-abre-x", 0.4))
    if c.etiqueta:
        out.append(g(txt(c.x0, c.y0 + 28, c.etiqueta, 36, "var(--texto)", "t"), t1))
    return "".join(out)


# ---- 6 · Arquivo em camadas --------------------------------------------------------------------------------------
def _arquivo_fundo(c: Ctx) -> str:
    n = int(c.par["trilhos"])
    grao = float(c.par["grao_opacidade"])
    trilhos = "".join(f'<path d="M0 {c.y0 + c.lh * (i + 1) / n:.0f}H{c.W:.0f}" stroke="var(--superficie)" stroke-width="4"/>' for i in range(n - 1))
    return _papel(c, grao, 1.1) + trilhos


def _arquivo(c: Ctx) -> str:
    n = int(c.par["trilhos"])
    e = f'--e:{int(c.par["entrada_px"])}px'
    r = c.rng()
    rot = float(c.par["rotacao_maxima_graus"])
    nomes = ["ASSUNTO", "NA FALA", "OBSERVAÇÃO", "FECHAMENTO"][:n]
    alturas = [c.lh * (0.46 if i == 0 else 0.54 / max(1, n - 1)) for i in range(n)]
    ts = c.fases(n + 1, leitura=1.2)
    idx = 74  # índice lateral
    x = c.x0 + idx
    w = c.lw - idx
    conteudos = [c.texto] + c.itens(n - 1)[: max(0, n - 2)]
    while len(conteudos) < n - 1:
        conteudos.append("")
    conteudos.append(c.nota or (c.itens(1)[0] if c.itens(1) else ""))
    out = [f"<defs>{_sombra()}</defs>"]
    y = c.y0
    centros = []
    for i in range(n):
        h = alturas[i] - 14
        if not conteudos[i]:
            conteudos[i] = "fonte não indicada"  # a evidência ausente é dita, nunca inventada
        tam_max = 72 if i == 0 else 48
        ls, tam = ajustar(conteudos[i], c.fonte_corpo, w - 60, h - 62, 3 if i == 0 else 2, tam_max, 34)
        ang = r.uniform(-rot, rot)
        corpo = (retangulo(x, y, w, h, "var(--fundo)", 3, 'filter="url(#sombra-curta)" stroke="var(--superficie)" stroke-width="2"')
                 + retangulo(x, y, 8, h, "var(--primaria)" if i == 0 else "var(--destaque)")
                 + txt(x + 28, y + 36, nomes[i], 30, "var(--texto)", "t")
                 + linhas(x + 28, y + 44 + tam, ls, tam))
        out.append(g(corpo, ts[i], "a-entra-x", 0.45, tf=f"rotate({ang:.2f} {x + w / 2:.0f} {y + h / 2:.0f})", css=e))
        out.append(g(retangulo(c.x0, y + 4, idx - 14, 46, "var(--superficie)", 3) + txt(c.x0 + (idx - 14) / 2, y + 40, f"{i + 1:02d}", 36, "var(--texto)", "t", "middle"),
                     ts[i], "a-fade", 0.3))
        centros.append((x + 4, y + h / 2))
        y += alturas[i]
    # a linha une o assunto ao que a fala dá de apoio: dois cartões que existem, sem inferir mais nada
    if len(centros) > 1:
        (ax, ay), (bx, by) = centros[0], centros[1]
        out.append(traco(f"M{ax - 6:.0f} {ay:.0f}H{ax - 26:.0f}V{by:.0f}H{bx - 6:.0f}", "var(--primaria)", 4, ts[-1], 0.5))
    return "".join(out)


# ---- 7 · Letras de oficina ---------------------------------------------------------------------------------------
def _grafemas(s: str) -> list[str]:
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", s):
        if unicodedata.combining(ch) and out:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def _letras_fundo(c: Ctx) -> str:
    return _papel(c, 0.06, 0.7)


def _letras(c: Ctx) -> str:
    palavra = (c.nota or c.texto.split()[0] if c.texto else c.nota).upper()
    resto = c.texto
    r = c.rng()
    n_mat = int(c.par["materiais"])
    rot = float(c.par["rotacao_maxima_graus"])
    passo = float(c.par["atraso_letras_s"])
    corr = int(c.par["correcao_final_px"])
    util = c.lw * 0.86
    letras = _grafemas(palavra)[:14]
    tam = min(c.lh * 0.34, 210.0)
    while tam > 46 and sum(largura(x, c.fonte_titulo, tam) + tam * 0.34 for x in letras) > util:
        tam -= 4
    y_base = c.y0 + c.lh * 0.52
    ws = [largura(x, c.fonte_titulo, tam) + tam * 0.34 for x in letras]
    x = c.x0 + (c.lw - sum(ws)) / 2
    t0, t1, t2 = c.fases(3, leitura=1.2)
    # as letras chegam junto da palavra dita, mas sempre com tempo de ler
    falado = min(c.quando(palavra, t0), max(t0, c.dur - 1.6 - passo * len(letras)))
    regua = retangulo(c.x0, y_base + 16, c.lw, 10, "var(--texto)") + "".join(
        f'<path d="M{c.x0 + c.lw * i / 20:.0f} {y_base + 26:.0f}v{14 if i % 5 == 0 else 8}" stroke="var(--texto)" stroke-width="3"/>' for i in range(21))
    out = [g(regua, t0, "a-abre-x", 0.4)]
    if c.leve:  # cartões de palavras inteiras, com a mesma régua
        w = largura(palavra, c.fonte_titulo, tam) + tam * 0.6
        corpo = retangulo(c.x0 + (c.lw - w) / 2, y_base - tam * 1.04, w, tam * 1.16, "var(--superficie)", 3) + txt(c.W / 2, y_base - tam * 0.1, palavra, tam, "var(--texto)", "t", "middle")
        out.append(g(corpo, falado))
    else:
        materiais = [("var(--superficie)", "var(--texto)"), ("var(--texto)", "var(--fundo)"), ("var(--fundo)", "var(--texto)"), ("var(--primaria)", "var(--sobre-primaria)")][:n_mat]
        for i, ch in enumerate(letras):
            fundo, tinta = materiais[r.randrange(len(materiais))]
            w = ws[i] - 6
            borda = ' stroke="var(--suave)" stroke-width="2"' if fundo == "var(--fundo)" else ""
            carta = retangulo(x, y_base - tam * 1.04, w, tam * 1.16, fundo, r.uniform(0, 6), borda) + txt(x + w / 2, y_base - tam * 0.1, ch, tam, tinta, "t", "middle")
            lado = i % 4
            dx, dy = {0: (-260, 0), 1: (0, -240), 2: (260, 0), 3: (0, 240)}[lado]
            ang = r.uniform(-rot, rot)
            out.append(g(carta, falado + i * passo, "a-assenta", 0.42, tf=f"rotate({ang:.1f} {x + w / 2:.0f} {y_base:.0f}) translate(0 {corr * (1 if i % 2 else -1) / 2:.1f})",
                         css=f"--dx:{dx}px;--dy:{dy}px;--r:{ang * 2:.1f}deg"))
            x += ws[i]
    ls, ts = ajustar(resto, c.fonte_corpo, c.lw * 0.9, c.y1 - y_base - 60, 2, 56, 36)
    out.append(g(linhas(c.W / 2, y_base + 56 + ts, ls, ts, ancora="middle"), t0, "a-sobe", 0.4))
    return "".join(out)


# ---- 14 · Quadro de recortes -------------------------------------------------------------------------------------
def _borda_cortada(r, x: float, y: float, w: float, h: float, passo: float = 44) -> str:
    """Um retângulo de borda irregular: a semente da peça é a mesma em toda a cena."""
    pts = []
    n = max(3, int(w // passo))
    m = max(3, int(h // passo))
    for i in range(n):
        pts.append((x + w * i / n, y + r.uniform(-3, 3)))
    for i in range(m):
        pts.append((x + w + r.uniform(-3, 3), y + h * i / m))
    for i in range(n):
        pts.append((x + w - w * i / n, y + h + r.uniform(-3, 3)))
    for i in range(m):
        pts.append((x + r.uniform(-3, 3), y + h - h * i / m))
    return " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)


def _quadro_fundo(c: Ctx) -> str:
    n = int(c.par["colunas"])
    guias = "".join(f'<path d="M{c.x0 + c.lw * i / n:.0f} 0V{c.H:.0f}" stroke="var(--superficie)" stroke-width="2" stroke-dasharray="4 12"/>' for i in range(1, n))
    return _papel(c, 0.07, 0.6) + guias


def _quadro(c: Ctx) -> str:
    n = int(c.par["colunas"])
    r = c.rng()
    fps = int(c.par["fps_poses"])
    rot = float(c.par["rotacao_maxima_graus"])
    mg = c.lw * float(c.par["margem_foto_relativa"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.2)
    col = c.lw / n
    wp = col * (2 if n >= 2 else 1) - 18
    hp = c.lh * 0.62
    x, y = c.x0, c.y0
    curva = f"steps({max(3, int(fps * 0.45))})"
    principal = f'<polygon points="{_borda_cortada(r, x, y, wp, hp)}" fill="var(--superficie)" filter="url(#sombra-curta)"/>'
    foto = imagem(c, x + mg, y + mg, wp - 2 * mg, hp - 2 * mg, 2)
    if foto:
        principal += foto
    else:
        lado = min(wp, hp) - 2 * mg - 40
        principal += peca(c.p.get("peca"), x + (wp - lado) / 2, y + (hp - lado) / 2, lado, "var(--texto)")
    out = [f"<defs>{_sombra()}</defs>",
           g(principal, t1, "a-assenta", 0.46, tf=f"rotate({r.uniform(-rot, rot):.1f} {x + wp / 2:.0f} {y + hp / 2:.0f})", curva=curva, css="--dy:-90px;--r:3deg")]
    notas = c.itens(2) or [c.nota]
    if n >= 3:
        xn, wn = x + wp + 18, col - 18
        hn = (hp - 18) / 2
        for i, s in enumerate(notas[:2]):
            ls, tam = ajustar(s, c.fonte_corpo, wn - 36, hn - 30, 3, 46, 34)
            yy = y + i * (hn + 18)
            corpo = f'<polygon points="{_borda_cortada(r, xn, yy, wn, hn, 30)}" fill="var(--fundo)" stroke="var(--suave)" stroke-width="2" filter="url(#sombra-curta)"/>'
            corpo += linhas(xn + 18, yy + (hn - len(ls) * tam * ALTURA_LINHA) / 2 + tam, ls, tam)
            out.append(g(corpo, (t2, t3)[i], "a-assenta", 0.4, tf=f"rotate({r.uniform(-rot, rot):.1f} {xn + wn / 2:.0f} {yy + hn / 2:.0f})", curva=curva, css="--dx:90px;--dy:0px;--r:-2deg"))
    # a seta de papel dobra pela metade antes de abrir entre as peças
    yb = y + hp + 26
    seta = f'<path d="M{x + 30:.0f} {yb + 34:.0f}h{wp * 0.34:.0f}v-20l44 34-44 34v-20h-{wp * 0.34:.0f}z" fill="var(--primaria)"/>'
    out.append(g(seta, t3, "a-abre-x", 0.4, curva="steps(4)"))
    ls, tam = ajustar(c.nota or c.texto, c.fonte_corpo, c.lw - wp * 0.34 - 160, c.y1 - yb - 16, 2, 58, 36)
    etiqueta_x = x + wp * 0.34 + 104
    largura_rot = max(largura(s, c.fonte_corpo, tam) for s in ls) + 48
    corpo = retangulo(etiqueta_x, yb + 4, largura_rot, len(ls) * tam * ALTURA_LINHA + 26, "var(--texto)", 2) + linhas(etiqueta_x + 24, yb + 14 + tam, ls, tam, "var(--fundo)")
    out.append(g(corpo, t4, "a-assenta", 0.36, curva="steps(4)", css="--dy:30px;--r:-2deg"))
    return "".join(out)


# ---- 17 · Revista de bancada -------------------------------------------------------------------------------------
def _revista(c: Ctx) -> str:
    cf = float(c.par["coluna_foto"])
    desloc = int(c.par["deslocamento_entrada_px"])
    rot = float(c.par["rotacao_nota_graus"])
    max_notas = int(c.par["max_notas"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.4)
    wf = c.lw * cf
    xc = c.x0 + wf + 34
    wc = c.x1 - xc
    out = [f"<defs>{_sombra()}</defs>"]
    foto = imagem(c, c.x0, c.y0, wf, c.lh, 2)
    if foto:
        corpo = foto
    else:  # sem foto: moldura retangular com o desenho do assunto, nunca um rosto inventado
        lado = min(wf, c.lh) * 0.72
        corpo = retangulo(c.x0, c.y0, wf, c.lh, "var(--superficie)", 2) + peca(c.p.get("peca"), c.x0 + (wf - lado) / 2, c.y0 + (c.lh - lado) / 2, lado)
    out.append(g(f'<g filter="url(#sombra-curta)">{corpo}</g>', t2, "a-entra-y", 0.5, css=f"--e:{desloc}px"))
    out.append(g(retangulo(xc - 18, c.y0, 6, c.lh, "var(--destaque)"), t1, "a-abre-y", 0.5))
    titulo = (c.etiqueta or c.nota or "").upper()
    y = c.y0 + 4
    if titulo:
        lt, tt = ajustar(titulo, c.fonte_titulo, wc, c.lh * 0.3, 2, 110, 54)
        out.append(g(linhas(xc, y + tt * 0.86, lt, tt, "var(--texto)", "t"), t1, "a-fade", 0.35))
        y += len(lt) * tt * ALTURA_LINHA + 16
    ls, tam = ajustar(c.texto, c.fonte_corpo, wc, (c.y1 - y) * 0.62, 6, 44, 34)
    out.append(g(linhas(xc, y + tam, ls, tam), t2, "a-fade", 0.4))
    y += len(ls) * tam * ALTURA_LINHA + 26
    notas = c.itens(max_notas)
    for i, s in enumerate(notas):
        if y > c.y1 - 66:
            break
        ln, tn = ajustar(s, c.fonte_corpo, wc - 34, min(110, c.y1 - y - 16), 2, 36, 34)
        h = len(ln) * tn * ALTURA_LINHA + 22
        corpo = retangulo(xc, y, wc, h, "var(--primaria)", 2) + linhas(xc + 16, y + 8 + tn, ln, tn, "var(--sobre-primaria)")
        out.append(g(corpo, (t3, t4)[min(i, 1)], "a-esq", 0.4, tf=f"rotate({rot * (-1 if i % 2 else 1):.1f} {xc + wc / 2:.0f} {y + h / 2:.0f})"))
        y += h + 12
    return "".join(out)


# ---- 20 · Caderno de materiais -----------------------------------------------------------------------------------
def _caderno_fundo(c: Ctx) -> str:
    op = float(c.par["textura_opacidade"])
    return (f'<defs>{ruido("trama-mad", c.semente, 0.02, 3)}</defs>{retangulo(0, 0, c.W, c.H, "var(--superficie)")}'
            f'<rect class="deco" width="{c.W}" height="{c.H}" filter="url(#trama-mad)" opacity="{op * 2:.2f}"/>')


def _caderno(c: Ctx) -> str:
    n = int(c.par["materiais"])
    aba = float(c.par["duracao_aba_s"])
    wa = c.lw * float(c.par["largura_aba_relativa"])
    op = float(c.par["textura_opacidade"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.4)
    x, y = c.x0, c.y0
    wp = c.lw - wa - 18
    hp = c.lh * 0.70
    pagina = retangulo(x, y, wp, hp, "var(--fundo)", 4, 'filter="url(#sombra-curta)"')
    foto = imagem(c, x + 18, y + 18, wp - 36, hp - 36, 3)
    lado = min(wp, hp) - 100
    pagina += foto or peca(c.p.get("peca"), x + (wp - lado) / 2, y + (hp - lado) / 2, lado, "var(--primaria)")
    trama = (f'<pattern id="trama{c.k}" width="14" height="14" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="var(--destaque)"/>'
             f'<path d="M0 3.5h14M0 10.5h14" stroke="var(--fundo)" stroke-width="2" opacity="{0.25 + op * 3:.2f}"/>'
             f'<path d="M3.5 0v14M10.5 0v14" stroke="var(--texto)" stroke-width="2" opacity="{0.12 + op * 2:.2f}"/></pattern>')
    out = [f"<defs>{_sombra()}{trama}</defs>", g(pagina, t1, "a-abre-x", 0.6)]
    xa = x + wp + 18
    hb = (hp - 18) / 2 if n >= 3 else hp
    cor_aba = "var(--destaque)" if c.leve else f"url(#trama{c.k})"
    out.append(g(retangulo(xa, y, wa, hb, cor_aba, 4, 'filter="url(#sombra-curta)"'), t2, "a-abre-y", aba))
    # a costura une as abas sem sugerir causa: um filete tracejado
    if n >= 3:
        lado2 = min(wa, hb) - 26
        tecnico = retangulo(xa, y + hb + 18, wa, hb, "var(--fundo)", 4, 'filter="url(#sombra-curta)"')
        desenho = peca(c.p.get("peca"), xa + (wa - lado2) / 2, y + hb + 18 + (hb - lado2) / 2, lado2, "var(--texto)")
        out.append(g(tecnico + desenho, t3, "a-abre-y", aba))
    yc = y + hp + 16
    costura = f'<path d="M{x:.0f} {yc:.0f}H{c.x1:.0f}" stroke="var(--primaria)" stroke-width="5" stroke-dasharray="20 12" stroke-linecap="round"/>'
    out.append(g(costura, t4, "a-abre-x", 0.5))
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw, c.y1 - yc - 14, 2, 54, 36)
    out.append(g(linhas(x, yc + 12 + tam, ls, tam), t1, "a-sobe", 0.4))
    return "".join(out)


DIRECOES = {
    "anotacao-em-foco": SimpleNamespace(cena=_anotacao, fundo=_anotacao_fundo, css=""),
    "arquivo-em-camadas": SimpleNamespace(cena=_arquivo, fundo=_arquivo_fundo, css=""),
    "letras-de-oficina": SimpleNamespace(cena=_letras, fundo=_letras_fundo, css=""),
    "quadro-de-recortes": SimpleNamespace(cena=_quadro, fundo=_quadro_fundo, css=""),
    "revista-de-bancada": SimpleNamespace(cena=_revista, fundo=lambda c: _papel(c, 0.04), css=""),
    "caderno-de-materiais": SimpleNamespace(cena=_caderno, fundo=_caderno_fundo, css=""),
}
