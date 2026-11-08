"""Direções de desenho plano: acervo, mapa de ideias, painel, atlas, gesto de papel e tinta. Formas próprias, em SVG e CSS."""

from __future__ import annotations

from types import SimpleNamespace

from .editoriais import _papel, _sombra
from .kit import ALTURA_LINHA, T0, Ctx, ajustar, g, imagem, largura, linhas, peca, retangulo, traco, txt


# ---- 9 · Acervo natural ------------------------------------------------------------------------------------------
def _acervo(c: Ctx) -> str:
    n = int(c.par["colunas"])
    oc = float(c.par["ocupacao_celula"])
    zoom = float(c.par["zoom_detalhe"])
    mi = float(c.par["margem_interna"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.5)
    obs_h = min(170.0, c.lh * 0.26)
    hc = c.lh - obs_h - 22
    wc = (c.lw - 22 * (n - 1)) / n
    nomes = c.itens(n)
    out = [f"<defs>{_sombra()}</defs>"]
    for i in range(n):
        x = c.x0 + i * (wc + 22)
        lado = min(wc, hc - 74) * oc
        corpo = retangulo(x, c.y0, wc, hc, "var(--superficie)", 6)
        foto = imagem(c, x + wc * mi, c.y0 + hc * mi, wc * (1 - 2 * mi), hc * (1 - 2 * mi) - 60, 4)
        corpo += foto or peca(c.p.get("peca"), x + (wc - lado) / 2, c.y0 + (hc - 60 - lado) / 2, lado, "var(--texto)")
        nome = nomes[i] if i < len(nomes) else ""
        ls, tam = ajustar(nome, c.fonte_corpo, wc - 2 * wc * mi, 56, 1, 42, 34)
        corpo += retangulo(x + wc * mi, c.y0 + hc - 66, wc * (1 - 2 * mi), 54, "var(--fundo)", 3) + linhas(x + wc * mi + 12, c.y0 + hc - 66 + 12 + tam * 0.86, ls, tam)
        out.append(g(corpo, (t1, t2)[i % 2], "a-dir", 0.5))
    # a lupa amplia o detalhe do exemplar citado e fica o tempo de ler
    rad = min(wc, hc) * 0.21 * (zoom / 1.6)
    cx = c.x0 + wc * (0.72 if n == 1 else 1.0) + 11
    cy = c.y0 + hc * 0.42
    lupa = (f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{rad:.0f}" fill="var(--fundo)" stroke="var(--primaria)" stroke-width="8"/>'
            f'<path d="M{cx + rad * 0.72:.0f} {cy + rad * 0.72:.0f}l{rad * 0.5:.0f} {rad * 0.5:.0f}" stroke="var(--primaria)" stroke-width="12" stroke-linecap="round"/>')
    lz = rad * 1.25
    lupa += peca(c.p.get("peca"), cx - lz / 2, cy - lz / 2, lz, "var(--primaria)")
    out.append(g(lupa, t3, "a-pop", 0.45))
    yo = c.y1 - obs_h
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw - 36, obs_h - 44, 3, 44, 34)
    corpo = retangulo(c.x0, yo, c.lw, obs_h, "var(--fundo)", 6, 'stroke="var(--superficie)" stroke-width="3"') + txt(c.x0 + 18, yo + 30, "OBSERVAÇÃO · IMAGENS SEM ESCALA", 26, "var(--texto)", "t") + linhas(c.x0 + 18, yo + 34 + tam, ls, tam)
    out.append(g(corpo, t4 if c.dur > 3 else t2, "a-fade", 0.4))
    return "".join(out)


# ---- 13 · Mapa de ideias -----------------------------------------------------------------------------------------
def _mapa(c: Ctx) -> str:
    n = int(c.par["ilhas"])
    ent = float(c.par["escala_entrada"])
    cont = int(c.par["contorno_px"])
    dc = float(c.par["duracao_conector_s"])
    itens = c.itens(n)
    n = max(1, len(itens))
    ts = c.fases(n + 1, leitura=1.3)
    hb = 96  # a faixa de síntese embaixo
    h = c.lh - hb - 16
    centros = []
    alturas = [0.24, 0.72, 0.3]
    for i in range(n):
        centros.append((c.x0 + c.lw * (i + 0.5) / n, c.y0 + h * (alturas[i] if n > 1 else 0.5)))
    rw = c.lw / n * 0.5
    rh = min(h * 0.34, rw * 0.95)
    cores = ["var(--superficie)", "var(--destaque)", "var(--primaria)"]
    tintas = ["var(--texto)", "var(--sobre-destaque)", "var(--sobre-primaria)"]
    out = ['<style>@keyframes a-ilha { from { opacity: 0; transform: scale(%.3f); } to { opacity: 1; transform: none; } }</style>' % ent]
    for i, (cx, cy) in enumerate(centros):
        if i:
            ax, ay = centros[i - 1]
            out.append(traco(f"M{ax:.0f} {ay:.0f}Q{(ax + cx) / 2:.0f} {min(ay, cy) - 30:.0f} {cx:.0f} {cy:.0f}", "var(--texto)", cont + 2, ts[i] - dc * 0.7 if ts[i] - dc * 0.7 > ts[i - 1] else ts[i - 1] + 0.1, dc))
    for i, (cx, cy) in enumerate(centros):
        ls, tam = ajustar(itens[i], c.fonte_corpo, rw * 1.74, rh * 0.86, 3, 40, 34)
        lado = rh * 0.8
        ilha = (f'<ellipse cx="{cx + 8:.0f}" cy="{cy + 12:.0f}" rx="{rw:.0f}" ry="{rh:.0f}" fill="var(--texto)" opacity=".16"/>'
                f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{rw:.0f}" ry="{rh:.0f}" fill="{cores[i % 3]}" stroke="var(--texto)" stroke-width="{cont}"/>'
                + peca(c.p.get("peca") if i == 0 else ("seta" if i == 1 else "check"), cx - lado * 0.4, cy - rh * 0.9, lado * 0.8, tintas[i % 3])
                + linhas(cx, cy + rh * 0.2, ls, tam, tintas[i % 3], ancora="middle"))
        out.append(g(ilha, ts[i], "a-ilha", 0.35))
    ls, tam = ajustar(c.nota or c.texto, c.fonte_titulo, c.lw, hb - 12, 1, 80, 44)
    out.append(g(linhas(c.W / 2, c.y1 - 14, ls, tam, "var(--texto)", "t", "middle"), ts[-1], "a-sobe", 0.4))
    return "".join(out)


# ---- 15 · Painel de variações ------------------------------------------------------------------------------------
def _painel(c: Ctx) -> str:
    nl, nc = int(c.par["linhas"]), int(c.par["colunas"])
    nt = int(c.par["tratamentos"])
    tr = float(c.par["transicao_s"])
    leitura = float(c.par["leitura_final_s"])
    legenda_h = min(180.0, c.lh * 0.24)
    h = c.lh - legenda_h - 16
    lado_h = (h - 8 * (nl - 1)) / nl
    lado_w = (c.lw - 8 * (nc - 1)) / nc
    t0 = c.fases(1)[0]
    fim_varredura = max(t0 + 0.4, c.dur - leitura)
    passo = (fim_varredura - t0) / max(1, nl + nc - 1)
    # tratamentos: mesma imagem, cada célula com um só filtro
    defs = ('<filter id="tr-mono"><feColorMatrix type="saturate" values="0"/></filter>'
            '<filter id="tr-duo"><feColorMatrix type="matrix" values=".5 .5 0 0 .25  .4 .4 0 0 .08  .2 .2 0 0 0  0 0 0 1 0"/></filter>'
            '<filter id="tr-linha"><feColorMatrix type="saturate" values="0"/><feConvolveMatrix order="3" kernelMatrix="-1 -1 -1 -1 8 -1 -1 -1 -1" preserveAlpha="true"/></filter>'
            '<pattern id="tr-ret" width="9" height="9" patternUnits="userSpaceOnUse"><circle cx="4.5" cy="4.5" r="2.4" fill="var(--texto)"/></pattern>')
    trat = ["", "tr-mono", "tr-duo", "tr-linha"][:nt] if nt > 2 else ["tr-mono", "tr-duo"]
    out = [f"<defs>{defs}</defs>"]
    ordem = 0
    for li in range(nl):
        for co in range(nc):
            x = c.x0 + co * (lado_w + 8)
            y = c.y0 + li * (lado_h + 8)
            f = trat[(li + co) % len(trat)]
            base = _motivo(c, x, y, lado_w, lado_h, "")
            novo = _motivo(c, x, y, lado_w, lado_h, f)
            out.append(base)
            t = t0 + (li + co) * passo + (ordem % 2) * 0.01
            out.append(g(novo, t, "a-abre-meio", tr))
            ordem += 1
    yl = c.y1 - legenda_h
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw - 10, legenda_h - 20, 3, 46, 34)
    out.append(g(linhas(c.x0, yl + 8 + tam, ls, tam), t0, "a-fade", 0.4))
    # a marca fica na alternativa citada, depois da varredura
    out.append(g(f'<rect x="{c.x0 - 2:.0f}" y="{c.y0 - 2:.0f}" width="{lado_w + 4:.0f}" height="{lado_h + 4:.0f}" fill="none" stroke="var(--primaria)" stroke-width="8"/>',
                 fim_varredura, "a-pop", 0.3))
    return "".join(out)


def _motivo(c: Ctx, x: float, y: float, w: float, h: float, filtro: str) -> str:
    """A célula: a foto do usuário ou, sem foto, o mesmo desenho (a alternativa declarada)."""
    foto = imagem(c, x, y, w, h, 2, filtro)
    if foto:
        return foto
    lado = min(w, h) * 0.8
    cores = {"": ("var(--superficie)", "var(--texto)"), "tr-mono": ("#5C6668", "#E8E8E8"), "tr-duo": ("var(--primaria)", "var(--fundo)"),
             "tr-linha": ("var(--fundo)", "var(--destaque)")}[filtro]
    return retangulo(x, y, w, h, cores[0], 2) + peca(c.p.get("peca"), x + (w - lado) / 2, y + (h - lado) / 2, lado, cores[1])


# ---- 16 · Atlas de percursos -------------------------------------------------------------------------------------
def _atlas_fundo(c: Ctx) -> str:
    r = c.rng(3)
    pts = [(c.W * x, c.H * y) for x, y in ((0.0, 0.46), (0.22, 0.38), (0.4, 0.5), (0.62, 0.42), (0.82, 0.54), (1.0, 0.48))]
    d = f"M0 {c.H:.0f}L{pts[0][0]:.0f} {pts[0][1]:.0f}" + "".join(f"Q{(a[0] + b[0]) / 2:.0f} {a[1] + r.uniform(-60, 60):.0f} {b[0]:.0f} {b[1]:.0f}" for a, b in zip(pts, pts[1:])) + f"L{c.W:.0f} {c.H:.0f}Z"
    return retangulo(0, 0, c.W, c.H, "var(--fundo)") + f'<path d="{d}" fill="var(--superficie)"/>' + "".join(
        f'<path d="M0 {c.H * (i + 1) / 8:.0f}H{c.W:.0f}M{c.W * (i + 1) / 8:.0f} 0V{c.H:.0f}" stroke="var(--suave)" stroke-width="1" opacity=".18"/>' for i in range(7))


def _atlas(c: Ctx) -> str:
    n = max(2, min(int(c.par["max_marcos"]), len(c.itens(int(c.par["max_marcos"])))))
    marcos = c.itens(n)
    n = len(marcos)
    simult = int(c.par["rotulos_simultaneos"])
    mg = float(c.par["margem_enquadramento"])
    esp = int(c.par["espessura_rota_px"])
    r = c.rng(1)
    ts = c.fases(max(2, n) + 1, leitura=1.3)
    hb = min(130.0, c.lh * 0.2)
    ax0, ay0 = c.x0 + c.lw * mg, c.y0 + c.lh * mg
    ax1, ay1 = c.x1 - c.lw * mg, c.y1 - hb - 30
    pts = []
    for i in range(n):
        x = ax0 + (ax1 - ax0) * i / max(1, n - 1)
        y = ay0 + (ay1 - ay0) * (0.5 + 0.5 * (1 if i % 2 else -1) * r.uniform(0.45, 1))
        pts.append((x, y))
    d = f"M{pts[0][0]:.0f} {pts[0][1]:.0f}" + "".join(f"L{b[0]:.0f} {b[1]:.0f}" for b in pts[1:])
    out = []
    # a rota é desenhada pelo comprimento: o ponto de progresso anda na mesma velocidade até cada marco
    comp = [0.0]
    for a, b in zip(pts, pts[1:]):
        comp.append(comp[-1] + ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)
    total = comp[-1] or 1
    t_ini, t_fim = ts[0], ts[-2] + 0.3
    kf = "".join(f"{100 * k / total:.1f}% {{ transform: translate({p[0]:.0f}px, {p[1]:.0f}px); }}" for k, p in zip(comp, pts))
    nome = f"a-rota{c.k}"
    out.append(f"<style>@keyframes {nome} {{ {kf} }}</style>")
    out.append(traco(d, "var(--primaria)", esp, t_ini, max(0.4, t_fim - t_ini)))
    atraso = t_ini + T0.get()
    out.append(f'<circle class="an" r="{esp * 2.4:.0f}" fill="var(--primaria)" stroke="var(--fundo)" stroke-width="4" style="transform-box:view-box;transform-origin:0 0;'
               f'animation:{nome} {max(0.4, t_fim - t_ini):.2f}s linear {atraso:.3f}s both"/>')
    for i, (x, y) in enumerate(pts):
        chegada = t_ini + (t_fim - t_ini) * comp[i] / total
        marco = f'<circle cx="{x:.0f}" cy="{y:.0f}" r="13" fill="var(--fundo)" stroke="var(--texto)" stroke-width="5"/>'
        out.append(g(marco, chegada, "a-pop", 0.3))
        if i >= n - simult:  # no máximo dois rótulos ao mesmo tempo: os dos últimos marcos
            ls, tam = ajustar(marcos[i], c.fonte_corpo, 300, 90, 2, 40, 34)
            w = max(largura(s, c.fonte_corpo, tam) for s in ls) + 28
            hh = len(ls) * tam * ALTURA_LINHA + 16
            bx = min(max(x - w / 2, c.x0), c.x1 - w)
            by = y - hh - 26 if y - hh - 26 > c.y0 else y + 26
            out.append(g(retangulo(bx, by, w, hh, "var(--fundo)", 4, 'stroke="var(--texto)" stroke-width="2"') + linhas(bx + 14, by + 6 + tam, ls, tam), chegada + 0.15, "a-sobe", 0.35))
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw, hb - 34, 2, 44, 34)
    out.append(g(linhas(c.x0, c.y1 - hb + 4 + tam, ls, tam) + txt(c.x1, c.y1, "trajeto esquemático", 28, "var(--texto)", "t", "end"), ts[-1], "a-fade", 0.4))
    return "".join(out)


# ---- 19 · Gesto de papel -----------------------------------------------------------------------------------------
_DOBRAS = (
    # (pontos da face clara, pontos da face escura, vinco): um envelope, um bilhete e uma seta de papel
    ("-210,-140 210,-140 0,40", "-210,-140 -210,140 210,140 210,-140 0,40", "M-210 -140L0 40L210 -140"),
    ("-170,-180 90,-180 170,-100 170,180 -170,180", "90,-180 170,-100 90,-100", "M90 -180V-100H170"),
    ("-230,-70 30,-70 30,-160 230,0 30,160 30,70 -230,70", "-230,0 30,0 30,70 -230,70", "M-230 0H30"),
)


def _gesto(c: Ctx) -> str:
    fps = int(c.par["fps_poses"])
    nmax = int(c.par["objetos_maximos"])
    poses = int(c.par["poses_principais"])
    inc = float(c.par["inclinacao_maxima_graus"])
    t1, t2, t3, t4 = c.fases(4, leitura=1.2)
    clara, escura, vinco = _DOBRAS[(c.k + c.semente) % len(_DOBRAS)]
    cx, cy = c.x0 + c.lw * 0.6, c.y0 + c.lh * 0.44
    esc_o = min(c.lh * 0.0017, c.lw * 0.0016)
    dur_gesto = max(0.6, min(1.6, t3 - t1 + 0.6))
    passos = max(3, int(fps * dur_gesto / poses))
    ang = [(-inc * 0.6), inc, -inc * 0.3, inc * 0.2, 0.0][:poses]
    kf = "".join(f"{100 * i / max(1, poses - 1):.0f}% {{ transform: rotate({a:.1f}deg) translateY({-12 if i == 1 else 0}px); }}" for i, a in enumerate(ang))
    sombra = f'<ellipse cx="{cx:.0f}" cy="{cy + 200 * esc_o + 22:.0f}" rx="{200 * esc_o:.0f}" ry="16" fill="var(--texto)" opacity=".16"/>'
    corpo = (f'<g transform="translate({cx:.0f} {cy:.0f}) scale({esc_o:.3f})"><g class="an" style="transform-box:view-box;transform-origin:0 0;animation:a-gesto{c.k} {dur_gesto:.2f}s steps({passos}) {t1 + T0.get():.3f}s both">'
             f'<polygon points="{escura}" fill="var(--primaria)"/><polygon points="{clara}" fill="var(--superficie)"/>'
             f'<path d="{vinco}" fill="none" stroke="var(--texto)" stroke-width="4" opacity=".5"/></g></g>')
    out = [f"<style>@keyframes a-gesto{c.k} {{ {kf} }}</style>", sombra, g(corpo, t1, "a-fade", 0.2)]
    # os objetos menores: no máximo dois, com diferença clara de escala
    for i in range(min(nmax - 1, 2)):
        lado = c.lh * 0.15
        x = c.x0 + (0.04 if i == 0 else 0.2) * c.lw
        out.append(g(peca(c.p.get("peca"), x, c.y0 + c.lh * (0.3 + 0.2 * i), lado, "var(--destaque)"), t2 + i * 0.2, "a-pop", 0.3, classe="deco"))
    verbo = (c.nota or "").upper()
    if verbo:
        lv, tv = ajustar(verbo, c.fonte_titulo, c.lw * 0.5, 120, 1, 96, 54)
        out.append(g(linhas(c.x0, c.y0 + tv * 0.8, lv, tv, "var(--texto)", "t"), t1, "a-fade", 0.3))
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw, c.lh * 0.24, 2, 50, 36)
    out.append(g(linhas(c.W / 2, c.y1 - (len(ls) - 1) * tam * ALTURA_LINHA - 8, ls, tam, ancora="middle"), t3, "a-sobe", 0.35))
    # a saída: a dobra fecha o objeto numa faixa, que é a passagem para a próxima cena
    if c.k < c.total - 1 and c.dur > 1.5:
        out.append(g(retangulo(0, cy - 34, c.W, 68, "var(--primaria)"), c.dur - 0.5, "a-abre-meio", 0.26, classe="deco"))
    return "".join(out)


# ---- 21 · Tinta em etapas ----------------------------------------------------------------------------------------
def _tinta(c: Ctx) -> str:
    n = int(c.par["etapas"])
    cores = ["var(--primaria)", "var(--destaque)"][: int(c.par["cores_tinta"])]
    ps = float(c.par["passagem_s"])
    ret = int(c.par["reticula_passo_px"])
    ts = c.fases(n + 1, leitura=1.3)
    tira_h = 70
    h = c.lh - tira_h - 110
    lado = min(h, c.lw * 0.56)
    x = c.x0
    y = c.y0
    defs = (f'<pattern id="ret{c.k}" width="{ret}" height="{ret}" patternUnits="userSpaceOnUse" patternTransform="rotate(30)">'
            f'<circle cx="{ret / 2:.1f}" cy="{ret / 2:.1f}" r="{ret * 0.32:.1f}" fill="var(--fundo)"/></pattern>')
    # o objeto: a mesma silhueta em cada estado; só a cor muda, na mesma caixa e no mesmo centro
    px, py = x + (c.lw * 0.58 - lado) / 2, y
    out = [f"<defs>{defs}</defs>", retangulo(x, y, c.lw * 0.58, h, "var(--superficie)", 3), peca(c.p.get("peca"), px, py, lado, "var(--suave)")]
    for k in range(n - 1 if n > 1 else 1):
        cor = cores[k % len(cores)]
        t = ts[k + 1] - ps / 2 if ts[k + 1] - ps / 2 > ts[k] else ts[k] + 0.1
        estado = retangulo(x, y, c.lw * 0.58, h, cor, 3)
        if not c.leve:
            estado += f'<rect x="{x:.0f}" y="{y:.0f}" width="{c.lw * 0.58:.0f}" height="{h:.0f}" fill="url(#ret{c.k})" opacity=".28"/>'
        estado += peca(c.p.get("peca"), px, py, lado, "var(--fundo)")
        out.append(g(estado, t, "a-abre-x", ps, curva="linear"))
        if not c.leve:  # a lâmina de tinta passa e sai pela borda
            out.append(f'<rect class="an deco" x="{x:.0f}" y="{y - 6:.0f}" width="16" height="{h + 12:.0f}" fill="{cor}" style="--x:{c.lw * 0.58:.0f}px;animation:a-lamina {ps:.2f}s linear {t + T0.get():.3f}s both"/>')
    xt = x + c.lw * 0.58 + 26
    wt = c.x1 - xt
    verbo = (c.nota or "").upper()
    if verbo:
        lv, tv = ajustar(verbo, c.fonte_titulo, wt, h * 0.5, 3, 78, 44)
        out.append(g(linhas(xt, y + tv * 0.86, lv, tv, "var(--acento)", "t"), ts[0], "a-fade", 0.3))
    y_rod = y + h + 22
    for k in range(n):
        cx = c.x0 + 26 + k * 66
        out.append(f'<circle cx="{cx:.0f}" cy="{y_rod + 24:.0f}" r="20" fill="none" stroke="var(--texto)" stroke-width="4"/>')
        out.append(g(f'<circle cx="{cx:.0f}" cy="{y_rod + 24:.0f}" r="13" fill="{cores[min(k, len(cores) - 1)]}"/>', min(ts[k] + ps, c.dur - 0.5), "a-pop", 0.25))
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw, c.y1 - y_rod - 60, 2, 44, 34)
    out.append(g(linhas(c.x0, y_rod + 64 + tam, ls, tam), ts[0], "a-sobe", 0.4))
    return "".join(out)


_LAMINA = "@keyframes a-lamina { 0% { opacity: 1; transform: translateX(0); } 95% { opacity: 1; } 100% { opacity: 0; transform: translateX(var(--x)); } }"

DIRECOES = {
    "acervo-natural": SimpleNamespace(cena=_acervo, fundo=lambda c: _papel(c, 0.03), css=""),
    "mapa-de-ideias": SimpleNamespace(cena=_mapa, fundo=lambda c: retangulo(0, 0, c.W, c.H, "var(--fundo)"), css=""),
    "painel-de-variacoes": SimpleNamespace(cena=_painel, fundo=lambda c: retangulo(0, 0, c.W, c.H, "var(--fundo)"), css=""),
    "atlas-de-percursos": SimpleNamespace(cena=_atlas, fundo=_atlas_fundo, css=""),
    "gesto-de-papel": SimpleNamespace(cena=_gesto, fundo=lambda c: _papel(c, 0.05, 0.5), css=""),
    "tinta-em-etapas": SimpleNamespace(cena=_tinta, fundo=lambda c: _papel(c, 0.05), css=_LAMINA),
}
