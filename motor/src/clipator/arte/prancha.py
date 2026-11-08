"""A prancha da DA: uma imagem longa que mostra a direção de arte inteira para a pessoa aprovar.

Seções, de cima para baixo: cabeçalho (nome, frase, revisão e estado), referências anotadas, paleta com o
contraste WCAG de cada cor, série dos gráficos e gradientes, tipografia (papéis e escala), o quadro vertical com
zona segura, legenda e tarja na posição real, a faixa em escala 1:1 (confira no celular, na largura da tela),
curvas de movimento, thumbnail com o canto reservado hachurado, faça e não faça, tratamento, som e marca.

Feita só com Pillow (sem navegador): sai igual em qualquer máquina e serve de registro do que foi aprovado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import cores as C
from . import zonas
from .carregar import Resolvida
from .compilar import filtro_tratamento
from .identidade import situacao
from .tipos import arquivo_da_fonte

LARGURA = 1600
MARGEM = 64
CINZA_UI = "#8A8F98"


class _Tela:
    """Tinta de apoio da prancha (só para rótulos): contrasta com o fundo da DA, seja ele claro ou escuro."""

    def __init__(self, r: Resolvida):
        self.fundo = r.cor("fundo")
        escuro = C.luminancia(self.fundo) < 0.2
        self.tinta = "#F3F4F6" if escuro else "#15171B"
        self.suave = "#A3A8B1" if escuro else "#59606B"
        self.linha = C.misturar(self.fundo, self.tinta, 0.18)


def _fonte(r: Resolvida, papel: str, px: int):
    from PIL import ImageFont

    p = r.papel(papel)
    arq = arquivo_da_fonte(p.familia, r, italico=p.italico) if p else None
    try:
        return ImageFont.truetype(str(arq), max(8, px)) if arq else ImageFont.load_default(max(8, px))
    except OSError:
        return ImageFont.load_default(max(8, px))


def _ui(px: int, r: Resolvida | None = None):
    """Fonte dos rótulos da prancha (a de corpo da DA, ou a padrão)."""
    if r is not None:
        return _fonte(r, "dados", px)
    from PIL import ImageFont

    return ImageFont.load_default(px)


def _caixa(texto: str, papel) -> str:
    return texto.upper() if papel is not None and papel.caixa_alta else texto


def _medir(d, texto: str, fonte, espacamento_px: float = 0) -> tuple[int, int]:
    if not texto:
        return 0, 0
    x0, y0, x1, y1 = d.textbbox((0, 0), texto, font=fonte)
    return int(x1 - x0 + espacamento_px * max(0, len(texto) - 1)), int(y1 - y0)


def _texto(d, xy, texto: str, fonte, cor: str, espacamento_px: float = 0, contorno: int = 0,
           cor_contorno: str | None = None) -> int:
    """Escreve (com tracking se houver) e devolve a largura usada."""
    x, y = xy
    kw = {"stroke_width": contorno, "stroke_fill": cor_contorno} if contorno and cor_contorno else {}
    if abs(espacamento_px) < 0.5:
        d.text((x, y), texto, font=fonte, fill=cor, **kw)
        return _medir(d, texto, fonte)[0]
    x_ini = x
    for ch in texto:
        d.text((x, y), ch, font=fonte, fill=cor, **kw)
        x += d.textlength(ch, font=fonte) + espacamento_px
    return int(x - x_ini)


def _largura(d, texto: str, fonte, espacamento_px: float = 0) -> float:
    """A mesma largura que `_texto` vai usar (com tracking, letra a letra)."""
    if abs(espacamento_px) < 0.5:
        return d.textlength(texto, font=fonte)
    return sum(d.textlength(ch, font=fonte) + espacamento_px for ch in texto)


def _quebrar(d, texto: str, fonte, largura: int) -> list[str]:
    linhas, atual = [], ""
    for w in texto.split():
        teste = (atual + " " + w).strip()
        if d.textlength(teste, font=fonte) <= largura or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = w
    if atual:
        linhas.append(atual)
    return linhas


def _titulo_secao(d, y: int, titulo: str, tela: _Tela, r: Resolvida) -> int:
    d.text((MARGEM, y), titulo.upper(), font=_ui(26, r), fill=tela.suave)
    d.line((MARGEM, y + 40, LARGURA - MARGEM, y + 40), fill=tela.linha, width=2)
    return y + 64


def _fundo_amostra(r: Resolvida, w: int, h: int, referencia: Path | None):
    """Um quadro do vídeo (se houver) ou o gradiente/fundo da DA, no tamanho pedido."""
    from PIL import Image, ImageOps

    if referencia is not None and referencia.exists():
        try:
            with Image.open(referencia) as im:
                return ImageOps.fit(im.convert("RGB"), (w, h))
        except OSError:
            pass
    base = Image.new("RGB", (w, h), r.cor("fundo"))
    # um degradê simples de superfície para fundo, para a amostra não ficar chapada
    from PIL import ImageDraw

    d = ImageDraw.Draw(base)
    a, b = r.cor("superficie"), r.cor("fundo")
    for yy in range(h):
        d.line((0, yy, w, yy), fill=C.misturar(a, b, yy / max(1, h - 1)))
    return base


def _hachura(d, ret: tuple[int, int, int, int], cor: str, passo: int = 14) -> None:
    x0, y0, x1, y1 = ret
    for k in range(x0 - (y1 - y0), x1, passo):
        d.line((max(x0, k), y0 + max(0, x0 - k), min(x1, k + (y1 - y0)), y0 + min(y1 - y0, x1 - k)), fill=cor, width=2)
    d.rectangle(ret, outline=cor, width=3)


def _legenda(d, r: Resolvida, cx: int, cy: int, largura_max: int, escala: float, frase: list[str], i_falada: int) -> None:
    """Desenha a legenda da DA (karaokê/palavra/bloco) centrada em (cx, cy) num quadro de 1080 de lado × escala."""
    leg = r.da.legenda
    papel = r.papel(leg.papel)
    tam = max(8, round(leg.tamanho * 1080 * escala))
    f = _fonte(r, leg.papel, tam)
    palavras = [_caixa(w, papel) for w in frase]
    if leg.estilo == "palavra":
        palavras = [palavras[i_falada]]
        i_falada = 0
    esp = (papel.espacamento if papel else 0) * tam
    gap = d.textlength(" ", font=f)
    linhas: list[list[tuple[int, str]]] = [[]]
    larg = 0.0
    contorno_px = max(1, round(leg.contorno.espessura * tam)) if leg.contorno else 0
    gap += contorno_px
    for i, w in enumerate(palavras):
        lw = _largura(d, w, f, esp)
        if linhas[-1] and larg + gap + lw > largura_max and len(linhas) < leg.max_linhas:
            linhas.append([])
            larg = 0.0
        linhas[-1].append((i, w))
        larg += (gap if larg else 0) + lw
    entre = tam * (papel.entrelinha if papel else 1.1)
    altura_total = entre * len(linhas)
    cor = r.campo("legenda.cor") or "#FFFFFF"
    cor_d = r.campo("legenda.cor_destaque") or cor
    cor_f = r.campo("legenda.cor_falada") or cor
    contorno = max(1, round(leg.contorno.espessura * tam)) if leg.contorno else 0
    cor_c = r.campo("legenda.contorno.cor")
    if leg.caixa:
        rx, ry = leg.caixa.respiro
        lmax = max(sum(_largura(d, w, f, esp) for _, w in ln) + gap * (len(ln) - 1) for ln in linhas)
        caixa = (cx - lmax / 2 - rx * tam, cy - altura_total / 2 - ry * tam, cx + lmax / 2 + rx * tam,
                 cy + altura_total / 2 + ry * tam)
        cor_cx = r.campo("legenda.caixa.cor") or r.cor("fundo")
        d.rounded_rectangle(caixa, radius=int(leg.caixa.raio * tam), fill=cor_cx + f"{int(leg.caixa.alfa * 255):02X}")
    y = cy - altura_total / 2
    for ln in linhas:
        lw = sum(_largura(d, w, f, esp) for _, w in ln) + gap * (len(ln) - 1)
        x = cx - lw / 2
        for i, w in ln:
            if leg.estilo == "bloco":
                c = cor_d if i == i_falada else cor
            else:
                c = cor_d if i == i_falada else (cor_f if i < i_falada else cor)
            if leg.sombra:
                s = leg.sombra
                _texto(d, (x + s.dx * tam, y + s.dy * tam), w, f, r.cor(s.cor) + f"{int(s.alfa * 255):02X}", esp,
                       contorno, r.cor(s.cor) + f"{int(s.alfa * 255):02X}")
            _texto(d, (x, y), w, f, c, esp, contorno, cor_c)
            x += _largura(d, w, f, esp) + gap
        y += entre


def _tarja(d, r: Resolvida, ret: tuple[int, int, int, int], escala: float, nome: str, cargo: str) -> None:
    t = r.da.graficos.tarja
    x0, y0, x1, y1 = ret
    tn = max(8, round(t.tamanho_nome * 1080 * escala))
    tc = max(8, round(t.tamanho_cargo * 1080 * escala))
    fn, fc = _fonte(r, t.papel_nome, tn), _fonte(r, t.papel_cargo, tc)
    pn, pc = r.papel(t.papel_nome), r.papel(t.papel_cargo)
    nome, cargo = _caixa(nome, pn), _caixa(cargo, pc)
    pad = round(0.018 * 1080 * escala)
    w = max(d.textlength(nome, font=fn), d.textlength(cargo, font=fc)) + 2 * pad + (pad if t.estilo == "barra" else 0)
    h = tn * 1.15 + tc * 1.35 + 2 * pad
    xa = x0 if not r.da.graficos.tarja.posicao.endswith("direita") else x1 - w
    ya = y1 - h if t.posicao.startswith("inferior") else y0
    fundo = (r.campo("graficos.tarja.cor_fundo") or r.cor("fundo")) + f"{int(t.alfa_fundo * 255):02X}"
    acento = r.campo("graficos.tarja.cor_acento") or r.cor("primaria")
    raio = int(r.da.layout.raio * 1080 * escala)
    tx = xa + pad
    if t.estilo == "barra":
        d.rounded_rectangle((xa, ya, xa + w, ya + h), radius=raio, fill=fundo)
        d.rectangle((xa, ya, xa + max(3, pad // 2), ya + h), fill=acento)
        tx += pad // 2 + 4
    elif t.estilo == "caixa":
        d.rounded_rectangle((xa, ya, xa + w, ya + h), radius=raio, fill=fundo)
        d.line((xa, ya + h, xa + w, ya + h), fill=acento, width=max(2, int(r.da.layout.traco * 1080 * escala)))
    elif t.estilo == "etiqueta":
        d.rounded_rectangle((xa, ya, xa + w, ya + tn * 1.25 + pad), radius=raio, fill=acento)
        d.rounded_rectangle((xa, ya + tn * 1.25 + pad, xa + w, ya + h), radius=raio,
                            fill=r.cor("superficie") + f"{int(t.alfa_fundo * 255):02X}")
    else:  # linha
        d.rounded_rectangle((xa - pad, ya - pad // 2, xa + w + pad, ya + h + pad // 2), radius=raio * 2,
                            fill=fundo[:7] + "B0")
        d.line((xa, ya + tn * 1.2 + pad, xa + w - pad, ya + tn * 1.2 + pad), fill=acento,
               width=max(2, int(r.da.layout.traco * 1080 * escala)))
    cor_nome = r.campo("graficos.tarja.cor_nome") or r.cor("texto")
    if t.estilo == "etiqueta":
        cor_nome = r.cor("fundo") if C.contraste(r.cor("fundo"), acento) > C.contraste(cor_nome, acento) else cor_nome
    d.text((tx, ya + pad * 0.6), nome, font=fn, fill=cor_nome)
    d.text((tx, ya + pad * 0.8 + tn * 1.2), cargo, font=fc, fill=r.campo("graficos.tarja.cor_cargo") or r.cor("texto_suave"))


def _secao_cabecalho(r: Resolvida, tela: _Tela):
    from PIL import Image, ImageDraw

    s = situacao(r)
    img = Image.new("RGB", (LARGURA, 420), tela.fundo)
    d = ImageDraw.Draw(img)
    estado = (f"APROVADA EM {s['aprovada_em'][8:10]}/{s['aprovada_em'][5:7]}/{s['aprovada_em'][:4]}"
              if s.get("aprovada") and not s.get("alterada_apos_aprovacao") and s.get("aprovada_em")
              else "RASCUNHO — AGUARDANDO APROVAÇÃO")
    cor_estado = r.cor("positivo") if estado.startswith("APROVADA") else r.cor("alerta")
    d.text((MARGEM, 40), f"DIREÇÃO DE ARTE · REVISÃO {s['revisao']} · {s['sha'][:10]}", font=_ui(24, r), fill=tela.suave)
    d.text((LARGURA - MARGEM - d.textlength(estado, font=_ui(24, r)), 40), estado, font=_ui(24, r), fill=cor_estado)
    pt = r.papel("titulo")
    ft = _fonte(r, "titulo", 120)
    _texto(d, (MARGEM, 86), _caixa(r.da.nome or "Sem nome", pt), ft, r.cor("texto"), (pt.espacamento if pt else 0) * 120)
    y = 240
    fc = _fonte(r, "corpo", 30)
    for linha in _quebrar(d, r.da.conceito.frase or "—", fc, LARGURA - 2 * MARGEM)[:3]:
        d.text((MARGEM, y), linha, font=fc, fill=r.cor("texto_suave"))
        y += 42
    x = MARGEM
    fchip = _ui(22, r)
    for pc in r.da.conceito.palavras_chave[:8]:
        w = d.textlength(pc, font=fchip) + 36
        d.rounded_rectangle((x, y + 10, x + w, y + 52), radius=21, outline=r.cor("primaria"), width=2)
        d.text((x + 18, y + 18), pc, font=fchip, fill=r.cor("texto"))
        x += w + 14
    return img.crop((0, 0, LARGURA, min(420, y + 76)))


def _secao_referencias(r: Resolvida, tela: _Tela):
    from PIL import Image, ImageDraw, ImageOps

    refs = [x for x in r.da.conceito.referencias if r.pasta is not None and (r.pasta / x.arquivo).exists()]
    if not refs:
        return None
    lado = 340
    por_linha = 4
    linhas = (len(refs) + por_linha - 1) // por_linha
    img = Image.new("RGB", (LARGURA, 80 + linhas * (lado + 120)), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Referências", tela, r)
    for k, ref in enumerate(refs[:12]):
        x = MARGEM + (k % por_linha) * (lado + 26)
        yy = y + (k // por_linha) * (lado + 120)
        try:
            with Image.open(r.pasta / ref.arquivo) as im:
                img.paste(ImageOps.fit(im.convert("RGB"), (lado, round(lado * 0.62))), (x, yy))
        except OSError:
            continue
        ty = yy + round(lado * 0.62) + 10
        for linha in _quebrar(d, ref.nota or Path(ref.arquivo).name, _ui(20, r), lado)[:4]:
            d.text((x, ty), linha, font=_ui(20, r), fill=tela.suave)
            ty += 26
    return img


def _secao_paleta(r: Resolvida, tela: _Tela):
    from PIL import Image, ImageDraw

    p = r.da.cor.paleta
    nomes = list(p)
    por_linha = 5
    cel_w = (LARGURA - 2 * MARGEM - (por_linha - 1) * 20) // por_linha
    cel_h = 200
    linhas = (len(nomes) + por_linha - 1) // por_linha
    altura = 90 + linhas * (cel_h + 24) + 260
    img = Image.new("RGB", (LARGURA, altura), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Paleta · contraste WCAG com o fundo", tela, r)
    f, fp = _ui(22, r), _ui(18, r)
    for k, nome in enumerate(nomes):
        x = MARGEM + (k % por_linha) * (cel_w + 20)
        yy = y + (k // por_linha) * (cel_h + 24)
        h = p[nome]
        d.rounded_rectangle((x, yy, x + cel_w, yy + 120), radius=10, fill=h, outline=tela.linha, width=2)
        sobre = "#000000" if C.contraste("#000000", h) > C.contraste("#FFFFFF", h) else "#FFFFFF"
        d.text((x + 14, yy + 12), "Aa", font=_fonte(r, "titulo", 44), fill=sobre)
        k_f = C.contraste(h, p["fundo"])
        d.text((x, yy + 130), f"{nome}  {h}", font=f, fill=tela.tinta)
        d.text((x, yy + 160), f"{k_f:.2f}:1 no fundo · {C.nivel_wcag(k_f)}".replace(".", ","), font=fp,
               fill=r.cor("negativo") if k_f < 3 and nome not in ("fundo", "superficie") else tela.suave)
    y += linhas * (cel_h + 24)
    d.text((MARGEM, y), "SÉRIE DOS GRÁFICOS", font=_ui(20, r), fill=tela.suave)
    x = MARGEM
    for i, h in enumerate(r.serie_hex, 1):
        altura_barra = 40 + (len(r.serie_hex) - i + 1) * 14
        d.rectangle((x, y + 150 - altura_barra, x + 70, y + 150), fill=h)
        d.text((x, y + 156), f"serie-{i}", font=fp, fill=tela.suave)
        x += 96
    x = MARGEM + 700
    d.text((x, y), "GRADIENTES", font=_ui(20, r), fill=tela.suave)
    for nome, g in list(r.da.cor.gradientes.items())[:4]:
        faixa = Image.new("RGB", (200, 110))
        fd = ImageDraw.Draw(faixa)
        paradas = [(r.cor(c), pos) for c, pos in g.paradas]
        for xx in range(200):
            t = xx / 199
            for (c1, p1), (c2, p2) in zip(paradas, paradas[1:]):
                if p1 <= t <= p2:
                    fd.line((xx, 0, xx, 110), fill=C.misturar(c1, c2, (t - p1) / max(1e-6, p2 - p1)))
                    break
            else:
                fd.line((xx, 0, xx, 110), fill=paradas[-1][0] if t > paradas[-1][1] else paradas[0][0])
        img.paste(faixa, (x, y + 36))
        d.text((x, y + 152), nome, font=fp, fill=tela.suave)
        x += 220
    return img


def _secao_tipografia(r: Resolvida, tela: _Tela):
    from PIL import Image, ImageDraw

    papeis = r.da.tipografia.papeis
    img = Image.new("RGB", (LARGURA, 120 + 150 * len(papeis) + 280), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Tipografia · papéis", tela, r)
    amostras = {"titulo": "A conta não fecha", "subtitulo": "Exclusivo · ao vivo", "corpo": "Ele explicou o plano em detalhes.",
                "dados": "R$ 1.250.000 · 37% · 2026", "legenda": "e foi aí que tudo mudou"}
    for nome, p in papeis.items():
        tam = 70 if nome in ("titulo", "legenda") else 54
        f = _fonte(r, nome, tam)
        arq = arquivo_da_fonte(p.familia, r, italico=p.italico)
        d.text((MARGEM, y), f"{nome} · {p.familia} {p.peso}" + (" itálico" if p.italico else "")
               + (" · caixa alta" if p.caixa_alta else "") + (f" · espaçamento {p.espacamento:g} em" if p.espacamento else "")
               + ("" if arq else " · ARQUIVO DA FONTE NÃO ENCONTRADO"), font=_ui(20, r),
               fill=tela.suave if arq else r.cor("negativo"))
        _texto(d, (MARGEM, y + 30), _caixa(amostras.get(nome, "Amostra do papel"), p), f, r.cor("texto"), p.espacamento * tam)
        y += 150
    d.text((MARGEM, y), "ESCALA (fração do lado menor = px em 1080 = pt num celular de 390 pt)", font=_ui(20, r),
           fill=tela.suave)
    y += 36
    x = MARGEM
    for nome, f in r.da.tipografia.escala.items():
        px = round(f * 1080)
        fonte = _fonte(r, "titulo", max(10, round(px * 0.6)))
        d.text((x, y + 150 - round(px * 0.6)), "Ag", font=fonte, fill=r.cor("texto"))
        d.text((x, y + 170), f"{nome} {f:g}", font=_ui(18, r), fill=tela.suave)
        d.text((x, y + 194), f"{px} px · {zonas.pt_no_celular(f):.0f} pt", font=_ui(18, r), fill=tela.suave)
        x += max(150, round(px * 0.6 * 1.6) + 30)
    return img


def _secao_quadro(r: Resolvida, tela: _Tela, referencia: Path | None):
    """O 9:16 com zona segura, legenda e tarja na posição real; ao lado, a faixa em escala 1:1."""
    from PIL import Image, ImageDraw

    esc = 0.42
    W, H = round(1080 * esc), round(1920 * esc)
    img = Image.new("RGB", (LARGURA, H + 140), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Vertical 9:16 · zona segura, legenda e tarja", tela, r)
    quadro = _fundo_amostra(r, W, H, referencia).convert("RGBA")
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    zona = zonas.zona_segura("uniao", "vertical")
    for plat, cor in (("youtube-shorts", "#FF4D4D"), ("instagram-reels", "#C77DFF"), ("tiktok", "#25F4EE")):
        z = zonas.zona_segura(plat, "vertical")
        dc.rectangle(z.px(W, H), outline=cor + "90", width=1)
    dc.rectangle(zona.px(W, H), outline=tela.tinta + "D0", width=2)
    faixa = zonas.faixa_da_legenda(r, "vertical")
    dc.rectangle(faixa.px(W, H), outline=r.cor("alerta") + "A0", width=1)
    tarja = zonas.lugar_da_tarja(r, "vertical")
    _tarja(dc, r, tarja.px(W, H), esc, "Marina Souza", "economista")
    cx = round((zona.x + zona.w / 2) * W)
    _legenda(dc, r, cx, round(r.da.legenda.y_vertical * H), round(min(r.da.legenda.largura_max, zona.w) * W), esc,
             ["ninguém", "te", "conta", "isso", "sobre", "dinheiro"], 2)
    quadro = Image.alpha_composite(quadro, camada).convert("RGB")
    img.paste(quadro, (MARGEM, y))
    xl = MARGEM + W + 40
    leg_txt = [
        "Contorno grosso: zona livre em Shorts, Reels e TikTok ao mesmo tempo (união).",
        "Vermelho, lilás e ciano: a zona de cada app.",
        "Laranja: a faixa que a legenda pode ocupar no pior caso.",
        "",
        f"Legenda: {r.da.legenda.estilo}, {r.da.legenda.tamanho:g} do lado menor ({round(r.da.legenda.tamanho * 1080)} px, "
        f"≈ {zonas.pt_no_celular(r.da.legenda.tamanho):.0f} pt no celular), até {r.da.legenda.max_palavras} palavras.",
        f"Tarja: {r.da.graficos.tarja.estilo}, nome {r.da.graficos.tarja.tamanho_nome:g} e cargo "
        f"{r.da.graficos.tarja.tamanho_cargo:g} ({zonas.pt_no_celular(r.da.graficos.tarja.tamanho_cargo):.0f} pt).",
    ]
    yy = y
    for linha in leg_txt:
        for parte in _quebrar(d, linha, _ui(20, r), LARGURA - xl - MARGEM) if linha else [""]:
            d.text((xl, yy), parte, font=_ui(20, r), fill=tela.tinta if linha.startswith(("Legenda", "Tarja")) else tela.suave)
            yy += 28
    # a faixa 1:1: 1080 px reais (cortada à largura que sobra na prancha), em volta da legenda
    yy += 30
    d.text((xl, yy), "EM ESCALA 1:1 — abra esta prancha no celular e confira se lê", font=_ui(20, r), fill=r.cor("alerta"))
    yy += 34
    largura_real = LARGURA - xl - MARGEM
    alt_real = max(220, round(faixa.h * 1920) + 80)
    fundo_real = _fundo_amostra(r, 1080, 1920, referencia).convert("RGBA")
    camada_r = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    _legenda(ImageDraw.Draw(camada_r), r, round((zona.x + zona.w / 2) * 1080), round(r.da.legenda.y_vertical * 1920),
             round(min(r.da.legenda.largura_max, zona.w) * 1080), 1.0, ["ninguém", "te", "conta", "isso", "sobre",
                                                                        "dinheiro"], 2)
    real = Image.alpha_composite(fundo_real, camada_r).convert("RGB")
    cy = round(r.da.legenda.y_vertical * 1920)
    cx_r = round((zona.x + zona.w / 2) * 1080)
    x0 = max(0, min(1080 - largura_real, cx_r - largura_real // 2))
    recorte = real.crop((x0, max(0, cy - alt_real // 2), x0 + min(largura_real, 1080), min(1920, cy + alt_real // 2)))
    if yy + recorte.height < img.height:
        img.paste(recorte, (xl, yy))
    return img


def _ponto_bezier(c, t: float) -> tuple[float, float]:
    x1, y1, x2, y2 = c
    u = 1 - t
    return (3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3, 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3)


def _secao_movimento(r: Resolvida, tela: _Tela):
    from PIL import Image, ImageDraw

    mv = r.da.movimento
    img = Image.new("RGB", (LARGURA, 470 + 30 * len(mv.principios)), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Movimento · curvas e durações", tela, r)
    x = MARGEM
    lado = 230
    for nome, c in list(mv.curvas.items())[:6]:
        d.rectangle((x, y, x + lado, y + lado), outline=tela.linha, width=2)
        # y fora de 0–1 (overshoot) cabe na caixa: o gráfico usa a faixa −0,5 a 1,5
        pts = []
        for i in range(61):
            px, py = _ponto_bezier(c, i / 60)
            pts.append((x + px * lado, y + lado - (py + 0.5) / 2 * lado))
        d.line((x, y + lado * 0.75, x + lado, y + lado * 0.75), fill=tela.linha, width=1)
        d.line((x, y + lado * 0.25, x + lado, y + lado * 0.25), fill=tela.linha, width=1)
        d.line(pts, fill=r.cor("primaria"), width=4)
        d.text((x, y + lado + 8), nome, font=_ui(20, r), fill=tela.tinta)
        d.text((x, y + lado + 34), "(" + ", ".join(f"{v:g}" for v in c) + ")", font=_ui(16, r), fill=tela.suave)
        x += lado + 24
    y += lado + 74
    linha = ("Durações: " + " · ".join(f"{n} {v:g} s" for n, v in mv.duracoes.items())
             + f" · escalonamento {mv.escalonamento:g} s · entra por “{mv.entrada}”, sai por “{mv.saida}” · transições: "
             + ", ".join(mv.transicoes) + f" (padrão {mv.transicao_padrao})")
    for parte in _quebrar(d, linha, _ui(20, r), LARGURA - 2 * MARGEM):
        d.text((MARGEM, y), parte, font=_ui(20, r), fill=tela.tinta)
        y += 28
    for pr in mv.principios:
        d.text((MARGEM, y), "• " + pr, font=_ui(20, r), fill=tela.suave)
        y += 30
    return img.crop((0, 0, LARGURA, y + 20))


def _secao_thumb(r: Resolvida, tela: _Tela, referencia: Path | None):
    from PIL import Image, ImageDraw

    esc = 0.62
    W, H = round(1280 * esc), round(720 * esc)
    img = Image.new("RGB", (LARGURA, H + 120), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Thumbnail · 1280×720 com o canto reservado", tela, r)
    th = r.da.thumbnail
    base = _fundo_amostra(r, W, H, referencia if th.fundo == "foto" else None)
    if th.fundo.startswith("gradiente:") and th.fundo.split(":", 1)[1] in r.da.cor.gradientes:
        g = r.da.cor.gradientes[th.fundo.split(":", 1)[1]]
        paradas = [(r.cor(c), pos) for c, pos in g.paradas]
        db = ImageDraw.Draw(base)
        for xx in range(W):
            t = xx / max(1, W - 1)
            cor = paradas[-1][0]
            for (c1, p1), (c2, p2) in zip(paradas, paradas[1:]):
                if p1 <= t <= p2:
                    cor = C.misturar(c1, c2, (t - p1) / max(1e-6, p2 - p1))
                    break
            db.line((xx, 0, xx, H), fill=cor)
    elif th.fundo != "foto":
        base = Image.new("RGB", (W, H), r.fundo_thumb_css() if r.fundo_thumb_css().startswith("#") else r.cor("fundo"))
    db = ImageDraw.Draw(base, "RGBA")
    reserva = zonas.canto_reservado_thumb(r)
    if reserva:
        _hachura(db, reserva.px(W, H), tela.suave)
    papel = r.papel(th.papel)
    tam = round(th.tamanho * 720 * esc)
    f = _fonte(r, th.papel, tam)
    palavras = [_caixa(w, papel) for w in ["Ninguém", "te", "conta", "isso"][: th.max_palavras]]
    yy = round(0.12 * H)
    cont = max(1, round(th.contorno.espessura * tam)) if th.contorno else 0
    cor_c = r.campo("thumbnail.contorno.cor")
    for i, linha in enumerate([" ".join(palavras[:2]), " ".join(palavras[2:])]):
        if not linha:
            continue
        cor = r.campo("thumbnail.cor_destaque") if i == 1 else r.campo("thumbnail.cor")
        _texto(db, (round(0.06 * W), yy), linha, f, cor or "#FFFFFF", (papel.espacamento if papel else 0) * tam, cont, cor_c)
        yy += round(tam * (papel.entrelinha if papel else 1.05))
    if th.borda:
        db.rectangle((0, 0, W - 1, H - 1), outline=r.campo("thumbnail.borda"), width=max(4, round(0.012 * H)))
    img.paste(base, (MARGEM, y))
    xl = MARGEM + W + 40
    textos = [f"Até {th.max_palavras} palavras em “{th.papel}”, {th.tamanho:g} da altura ({tam / esc:.0f} px).",
              f"Palavra-chave em {r.campo('thumbnail.cor_destaque')}; fundo “{th.fundo}”.",
              "Hachurado: onde o app põe a duração do vídeo. O texto não entra ali.",
              f"Foto: saturação {th.tratamento_foto.saturacao:g}, contraste {th.tratamento_foto.contraste:g}"
              + (f", pessoa recortada com contorno {r.campo('thumbnail.tratamento_foto.contorno_pessoa')}"
                 if th.tratamento_foto.recortar_pessoa and r.campo('thumbnail.tratamento_foto.contorno_pessoa') else "") + "."]
    yy = y
    for t in textos:
        for parte in _quebrar(d, t, _ui(20, r), LARGURA - xl - MARGEM):
            d.text((xl, yy), parte, font=_ui(20, r), fill=tela.suave)
            yy += 28
        yy += 8
    return img


def _secao_regras(r: Resolvida, tela: _Tela):
    from PIL import Image, ImageDraw

    c = r.da.conceito
    img = Image.new("RGB", (LARGURA, 1400), tela.fundo)
    d = ImageDraw.Draw(img)
    y = _titulo_secao(d, 10, "Faça · não faça · tratamento · som · marca", tela, r)
    col = (LARGURA - 2 * MARGEM - 40) // 2
    f = _ui(21, r)
    ys = []
    for k, (titulo, itens, cor) in enumerate((("FAÇA", c.faca, r.cor("positivo")), ("NÃO FAÇA", c.nao_faca, r.cor("negativo")))):
        x = MARGEM + k * (col + 40)
        yy = y
        d.text((x, yy), titulo, font=_ui(24, r), fill=cor)
        yy += 40
        for item in itens:
            linhas = _quebrar(d, item, f, col - 30)
            d.ellipse((x, yy + 8, x + 12, yy + 20), fill=cor)
            for linha in linhas:
                d.text((x + 26, yy), linha, font=f, fill=tela.tinta)
                yy += 30
            yy += 8
        ys.append(yy)
    y = max(ys) + 30
    filtro = filtro_tratamento(r)
    blocos = [
        ("TRATAMENTO DO VÍDEO", ((filtro or "neutro").replace(",", ", ").replace(":", ": ")) + (" — aplicado nos clips" if r.da.tratamento.aplicar_nos_clips
                                                         else " — não aplicado nos clips (aplicar_nos_clips: false)")),
        ("SOM", (r.da.som.identidade or "—") + " · efeitos: " + ", ".join(f"{a}: {b}" for a, b in r.da.som.efeitos.items())
         + f" · {r.da.som.loudness.alvo_lufs:g} LUFS / {r.da.som.loudness.pico_dbtp:g} dBTP"),
        ("MARCA", (r.da.marca.assinatura or "sem assinatura") + f" · logo: {r.da.marca.logo or '—'} em "
         f"{r.da.marca.posicao_logo.replace('_', ' ')}" + (" · marca d'água" if r.da.marca.marca_dagua else "")),
    ]
    for titulo, txt in blocos:
        d.text((MARGEM, y), titulo, font=_ui(20, r), fill=tela.suave)
        y += 30
        for linha in _quebrar(d, txt, f, LARGURA - 2 * MARGEM):
            d.text((MARGEM, y), linha, font=f, fill=tela.tinta)
            y += 30
        y += 18
    return img.crop((0, 0, LARGURA, y + 30))


def gerar(r: Resolvida, saida: Path | None = None, referencia: Path | None = None) -> Path:
    """Gera a prancha (PNG). Sem `saida`, grava em arte/prancha.png e registra o sha em arte/build/prancha.json."""
    from PIL import Image

    tela = _Tela(r)
    if referencia is None and r.pasta is not None:
        for ref in r.da.conceito.referencias:
            cand = r.pasta / ref.arquivo
            if cand.exists() and cand.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                referencia = cand
                break
    partes = [p for p in (_secao_cabecalho(r, tela), _secao_referencias(r, tela), _secao_paleta(r, tela),
                          _secao_tipografia(r, tela), _secao_quadro(r, tela, referencia), _secao_movimento(r, tela),
                          _secao_thumb(r, tela, referencia), _secao_regras(r, tela)) if p is not None]
    altura = sum(p.height for p in partes) + 40
    folha = Image.new("RGB", (LARGURA, altura), tela.fundo)
    y = 0
    for p in partes:
        folha.paste(p, (0, y))
        y += p.height
    if saida is None:
        if r.pasta is None:
            raise ValueError("informe onde gravar a prancha de um predefinido")
        saida = r.pasta / "prancha.png"
    saida.parent.mkdir(parents=True, exist_ok=True)
    folha.save(saida, optimize=True)
    if r.pasta is not None and saida.resolve() == (r.pasta / "prancha.png").resolve():
        from .identidade import sha

        (r.pasta / "build").mkdir(exist_ok=True)
        (r.pasta / "build" / "prancha.json").write_text(json.dumps({"sha": sha(r), "arquivo": "prancha.png",
                                                                     "altura": altura}, indent=2), encoding="utf-8")
    return saida


def cartao(r: Resolvida, titulo: str = "", largura: int = 760):
    """Versão compacta para comparar rotas lado a lado: nome, frase, paleta, tipografia, quadro e thumb."""
    from PIL import Image, ImageDraw

    tela = _Tela(r)
    img = Image.new("RGB", (largura, 1900), tela.fundo)
    d = ImageDraw.Draw(img)
    d.text((32, 28), (titulo or r.da.nome).upper(), font=_fonte(r, "titulo", 64), fill=r.cor("texto"))
    y = 110
    for linha in _quebrar(d, r.da.conceito.frase or "", _ui(22, r), largura - 64)[:3]:
        d.text((32, y), linha, font=_ui(22, r), fill=tela.suave)
        y += 30
    y += 16
    x = 32
    for nome in ("fundo", "superficie", "texto", "texto_suave", "primaria", "secundaria", "destaque"):
        d.rectangle((x, y, x + 88, y + 88), fill=r.cor(nome), outline=tela.linha)
        d.text((x, y + 94), nome[:10], font=_ui(15, r), fill=tela.suave)
        x += 98
    y += 130
    for nome in ("titulo", "corpo", "legenda"):
        p = r.papel(nome)
        d.text((32, y), f"{nome}: {p.familia}", font=_ui(17, r), fill=tela.suave)
        d.text((32, y + 22), _caixa("A conta não fecha", p), font=_fonte(r, nome, 46), fill=r.cor("texto"))
        y += 84
    esc = 0.5
    W, H = round(1080 * esc), round(1920 * esc)
    quadro = _fundo_amostra(r, W, H, None).convert("RGBA")
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    zona = zonas.zona_segura("uniao", "vertical")
    dc.rectangle(zona.px(W, H), outline="#FFFFFF60", width=1)
    _tarja(dc, r, zonas.lugar_da_tarja(r, "vertical").px(W, H), esc, "Marina Souza", "economista")
    _legenda(dc, r, round((zona.x + zona.w / 2) * W), round(r.da.legenda.y_vertical * H),
             round(min(r.da.legenda.largura_max, zona.w) * W), esc, ["isso", "muda", "tudo", "agora"], 1)
    img.paste(Image.alpha_composite(quadro, camada).convert("RGB"), ((largura - W) // 2, y + 10))
    return img.crop((0, 0, largura, y + H + 40))


def comparar(resolvidas: list[tuple[str, Resolvida]], saida: Path) -> Path:
    """Cartões das rotas lado a lado, na mesma escala."""
    from PIL import Image

    cartoes = [cartao(r, nome) for nome, r in resolvidas]
    h = max(c.height for c in cartoes)
    folha = Image.new("RGB", (sum(c.width for c in cartoes) + 20 * (len(cartoes) + 1), h + 40), "#0B0B0C")
    x = 20
    for c in cartoes:
        folha.paste(c, (x, 20))
        x += c.width + 20
    saida.parent.mkdir(parents=True, exist_ok=True)
    folha.save(saida, optimize=True)
    return saida


def info(caminho: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(caminho) as im:
        return {"arquivo": str(caminho), "largura": im.width, "altura": im.height}
