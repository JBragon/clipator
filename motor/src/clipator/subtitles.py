"""Legendas animadas em ASS (libass via FFmpeg) e cartela de título.

A técnica de karaokê (um evento por palavra, a palavra falada com cor ou
animação própria e {\\r} para voltar ao estilo base), o escurecimento por cor e
não por alfa e o estilo "Active" com caixa foram adaptados de
openshorts/subtitles.py (generate_ass), MIT License, Copyright (c) 2024
OpenShorts. Ver THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

from .models import Cartela, Legenda
from .plataformas import Zona
from .timeline import Timeline

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")

POSICOES_Y = {"topo": 0.16, "centro": 0.5, "centro-baixo": 0.68, "terco-inferior": 0.78, "baixo": 0.88}


def _hex(c: str | None, fallback: str = "FFFFFF") -> str:
    c = (c or "").strip()
    return c.lstrip("#").upper() if _HEX.match(c) else fallback


def ass_color(hex_color: str | None, opacidade: float = 1.0, fallback: str = "FFFFFF") -> str:
    """#RRGGBB -> &HAABBGGRR (estilo). Alfa no ASS é invertido: 00 = opaco."""
    h = _hex(hex_color, fallback)
    alpha = int(round((1 - max(0.0, min(1.0, opacidade))) * 255))
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}"


def ass_inline(hex_color: str | None, fallback: str = "FFFFFF") -> str:
    h = _hex(hex_color, fallback)
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&"


def _escurecer(hex_color: str, opacidade: float) -> str:
    h = _hex(hex_color)
    f = 0.5 + 0.5 * max(0.05, min(1.0, opacidade))
    return "#" + "".join(f"{min(255, round(int(h[i:i + 2], 16) * f)):02X}" for i in (0, 2, 4))


def _luminancia(hex_color: str) -> float:
    h = _hex(hex_color)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_ass(texto: str) -> str:
    return str(texto).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


SEGURA_ENTRE_BLOCOS = 0.4  # pausa menor que isso: o bloco espera o próximo, sem a tela piscar vazia
RESPIRO_FIM_BLOCO = 0.25  # pausa maior: o bloco fica mais este tanto depois da última palavra


def blocos_de_palavras(palavras: list[dict], max_palavras: int, max_duracao: float = 2.6,
                       pausa_quebra: float = 0.6) -> list[list[dict]]:
    """Agrupa palavras (já em tempo do clip) em blocos que cabem na tela."""
    blocos: list[list[dict]] = []
    atual: list[dict] = []
    for w in palavras:
        if atual:
            gap = w["inicio"] - atual[-1]["fim"]
            longo = w["fim"] - atual[0]["inicio"] > max_duracao
            fim_frase = bool(re.search(r"[.!?…,;:]$", atual[-1]["texto"]))
            if len(atual) >= max_palavras or gap >= pausa_quebra or longo or (fim_frase and len(atual) >= 2):
                blocos.append(atual)
                atual = []
        atual.append(w)
    if atual:
        blocos.append(atual)
    return blocos


MAX_DURACAO_PALAVRA = 1.2  # o Whisper estica a última palavra antes de uma pausa por segundos
MIN_DURACAO_PALAVRA = 0.06


def ajustar_tempos(palavras: list[dict]) -> list[dict]:
    """Tempos por palavra que a legenda consegue seguir: em ordem, sem uma palavra cobrir a seguinte,
    sem palavra de 0 s (que nunca acendia) e sem palavra presa na tela durante uma pausa."""
    pals = sorted((dict(w) for w in palavras if str(w.get("texto", "")).strip()), key=lambda w: (w["inicio"], w["fim"]))
    for k, w in enumerate(pals):
        prox = pals[k + 1]["inicio"] if k + 1 < len(pals) else None
        fim = min(float(w["fim"]), float(w["inicio"]) + MAX_DURACAO_PALAVRA)
        if prox is not None:
            fim = min(fim, max(float(w["inicio"]), prox))
        if fim - w["inicio"] < MIN_DURACAO_PALAVRA:
            fim = w["inicio"] + MIN_DURACAO_PALAVRA
            if prox is not None and fim > prox:  # duas palavras no mesmo instante: a de trás anda um pouco
                pals[k + 1]["inicio"] = round(fim, 3)
                pals[k + 1]["fim"] = max(pals[k + 1]["fim"], pals[k + 1]["inicio"] + MIN_DURACAO_PALAVRA)
        w["fim"] = round(fim, 3)
    return pals


def palavras_do_clip(palavras: list[dict], tl: Timeline) -> list[dict]:
    """Converte palavras do original para o tempo do clip, descartando as cortadas."""
    out = []
    for w in palavras:
        if w["fim"] <= tl.inicio or w["inicio"] >= tl.fim:
            continue
        iv = tl.mapear_intervalo(w["inicio"], w["fim"])
        if iv is None or iv[1] - iv[0] < 0.02:
            continue
        out.append({**w, "inicio": iv[0], "fim": iv[1]})
    return ajustar_tempos(out)


# fora da tela: vírgula, ponto, dois-pontos e ponto e vírgula no fim da palavra (? e ! ficam)
_PONTUACAO_FINAL = re.compile(r"[.,;:…]+$")


def sem_pontuacao(texto: str) -> str:
    t = _PONTUACAO_FINAL.sub("", texto.strip())
    return t or texto


@functools.lru_cache(maxsize=1)
def _arquivos_de_fonte() -> dict[str, str]:
    """Nome da família (e família + estilo) -> arquivo, das fontes que vêm com o Clipator e das baixadas."""
    from PIL import ImageFont

    from .workspace import fontes_dir

    pastas = [fontes_dir()]
    try:
        from . import fontes

        pastas.append(fontes.pasta())
    except Exception:  # noqa: BLE001 - sem a pasta das baixadas, fica só a embutida
        pass
    mapa: dict[str, str] = {}
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for arq in sorted(pasta.rglob("*")):
            if arq.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                familia, estilo = ImageFont.truetype(str(arq), 40).getname()
            except OSError:
                continue
            for chave in (f"{familia} {estilo}", familia, arq.stem.replace("-", " ")):
                mapa.setdefault(chave.lower(), str(arq))
    return mapa


@functools.lru_cache(maxsize=32)
def _fonte_medida(nome: str) -> tuple[Any, float] | None:
    """A fonte da legenda carregada em tamanho 100 e o fator de pixels: no ASS o tamanho é a altura da
    linha (ascendente + descendente), não o em."""
    from PIL import ImageFont

    arq = _arquivos_de_fonte().get((nome or "").strip().lower())
    if not arq:
        return None
    try:
        f = ImageFont.truetype(arq, 100)
        altura = _altura_win(arq)  # o libass usa a altura do Windows (usWinAscent + usWinDescent) em em
        if altura is None:
            a, d = f.getmetrics()
            return f, 1.0 / max(1, a + d)
        return f, 1.0 / (100 * altura)
    except OSError:
        return None


def _altura_win(arq: str) -> float | None:
    """(usWinAscent + usWinDescent) / unitsPerEm, lidos das tabelas OS/2 e head do arquivo da fonte."""
    import struct

    try:
        dados = Path(arq).read_bytes()
        n = struct.unpack(">H", dados[4:6])[0]
        tabelas = {dados[12 + 16 * k: 16 + 16 * k]: struct.unpack(">I", dados[20 + 16 * k: 24 + 16 * k])[0] for k in range(n)}
        upm = struct.unpack(">H", dados[tabelas[b"head"] + 18: tabelas[b"head"] + 20])[0]
        asc, desc = struct.unpack(">HH", dados[tabelas[b"OS/2"] + 74: tabelas[b"OS/2"] + 78])
        return (asc + desc) / upm if upm and asc + desc else None
    except (OSError, KeyError, struct.error):
        return None


def largura_estimada(texto: str, fs: float, caixa_alta: bool = False, fonte: str | None = None) -> float:
    """Largura do texto na legenda, em pixels.

    Com a fonte do estilo entre as do Clipator, mede com ela (Pillow); senão estima pela média de uma sans
    negrito, entre 0,5 e 0,7 da altura por caractere, mais larga em caixa alta.
    """
    medida = _fonte_medida(fonte) if fonte else None
    if medida is not None:
        f, fator = medida
        return f.getlength(texto) * fator * fs * 1.03  # 3%: negrito sintético e arredondamento do libass
    estreitas = sum(texto.count(c) for c in "iljtfrI.,;:!' ")
    fator = 0.72 if caixa_alta or texto.isupper() else 0.6
    return fs * (fator * (len(texto) - estreitas) + 0.32 * estreitas)


def quebrar_em_linhas(textos: list[str], pesos: list[float], max_por_linha: int, largura_util: float,
                      fs: float, caixa_alta: bool, fonte: str | None = None) -> list[list[int]]:
    """Índices das palavras de cada linha: até `max_por_linha` palavras e sem passar da largura útil."""
    linhas: list[list[int]] = []
    atual: list[int] = []
    larg = 0.0
    espaco = largura_estimada(" ", fs, caixa_alta, fonte)
    for j, t in enumerate(textos):
        w = largura_estimada(t, fs, caixa_alta, fonte) * pesos[j]
        if atual and (len(atual) >= max_por_linha or larg + espaco + w > largura_util):
            linhas.append(atual)
            atual, larg = [], 0.0
        larg += (espaco if atual else 0.0) + w
        atual.append(j)
    if atual:
        linhas.append(atual)
    return linhas


def palavras_chave(pals_clip: list[dict], top: int = 8) -> list[str]:
    """Sem IA: as palavras que se repetem no corte e marcam o assunto, escritas como na fala (com acento)."""
    from .candidates import montar_frases
    from .textutil import normalizar, termos_relevantes

    frases = [f.texto for f in montar_frases(pals_clip)]
    termos = {t for t, _ in termos_relevantes(frases, top=top)}
    termos_n = {normalizar(t) for t in termos}
    vistos = {}
    for w in pals_clip:
        n = normalizar(w["texto"])
        if n in termos_n and n not in vistos:
            vistos[n] = re.escape(w["texto"].strip(".,!?;:\"'()[]…-–—"))
    return list(vistos.values())


def regex_destaque(legenda: Legenda, destaques_extra: list[str] | None = None) -> re.Pattern | None:
    """Palavras sempre destacadas: lista/regex do estilo + destaques da IA + números."""
    padroes = [p for p in (legenda.palavras_destaque + list(destaques_extra or [])) if p]
    if not padroes and not legenda.destacar_numeros:
        return None
    partes = []
    for p in padroes:
        try:
            re.compile(p)
            partes.append(p)
        except re.error:
            partes.append(re.escape(p))
    if legenda.destacar_numeros:
        partes.append(r"\d+[\d.,%]*|R\$")
    return re.compile(r"^(?:" + "|".join(partes) + r")\W*$", re.IGNORECASE)


def _quebrar_titulo(texto: str, max_chars: int) -> list[str]:
    linhas, atual = [], ""
    for p in texto.split():
        if atual and len(atual) + 1 + len(p) > max_chars:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    return linhas


def gerar_ass(
    palavras: list[dict],
    tl: Timeline,
    legenda: Legenda,
    largura: int,
    altura: int,
    saida: str | Path,
    titulo: str | None = None,
    cartela: Cartela | None = None,
    usar_cartela: bool = False,
    destaques_extra: list[str] | None = None,
    zona: Zona | None = None,
) -> Path:
    """Escreve o .ass do clip: legenda palavra a palavra e, se pedido, a cartela de título.

    `zona`: a parte da tela que o app da plataforma cobre; a legenda e a cartela ficam fora dela.
    """
    escala = min(largura, altura) / 1080
    fs = max(10, int(legenda.tamanho * escala))
    contorno = legenda.espessura_contorno * escala
    sombra = legenda.sombra * escala
    base_cor = _escurecer(legenda.cor, legenda.opacidade_base) if legenda.opacidade_base < 1 else legenda.cor
    if legenda.fundo and legenda.opacidade_fundo > 0:
        border_style, outline_c, outline_w = 3, ass_color(legenda.fundo, legenda.opacidade_fundo, "000000"), max(4, fs * 0.15)
    else:
        border_style, outline_c, outline_w = 1, ass_color(legenda.contorno, 1.0, "000000"), contorno
    back_c = ass_color("#000000", 0.55 if sombra else 0.0)
    italic = -1 if legenda.italico else 0
    x = largura // 2
    y_rel = legenda.altura_relativa if legenda.altura_relativa is not None else POSICOES_Y.get(legenda.posicao, 0.68)
    if zona is not None:
        from .plataformas import y_seguro

        # centro da área livre na horizontal (os botões ficam à direita) e altura fora das faixas cobertas
        x = int(largura * (zona.esquerda + (1 - zona.esquerda - zona.direita) / 2))
        y_rel = y_seguro(y_rel, legenda.linhas * fs * 1.25 / altura, zona)
    y = int(altura * y_rel)
    pos = f"\\an5\\pos({x},{y})"
    hl = ass_inline(legenda.destaque, "FFE600")

    estilos = [
        f"Style: Default,{legenda.fonte},{fs},{ass_color(base_cor)},{ass_color(base_cor)},{outline_c},{back_c},"
        f"1,{italic},0,0,100,100,0,0,{border_style},{outline_w:.1f},{sombra:.1f},5,40,40,40,1"
    ]
    anim = legenda.animacao
    esc_d = legenda.escala_destaque
    ativo_grande = None  # palavra destacada e ativa: o pop tem tag própria; nas outras animações a escala vai na frente
    if anim == "marca-texto":
        on_box = "#000000" if _luminancia(legenda.destaque) > 0.6 else legenda.cor
        pad = max(3, round(fs * 0.12))
        estilos.append(
            f"Style: Active,{legenda.fonte},{fs},{ass_color(on_box)},{ass_color(on_box)},{ass_color(legenda.destaque)},"
            f"{ass_color(legenda.destaque)},1,{italic},0,0,100,100,0,0,3,{pad},0,5,40,40,40,1"
        )
        ativo = "{\\rActive}"
    elif anim == "pop":
        ativo = f"{{\\c{hl}\\fscx88\\fscy88\\t(0,110,\\fscx110\\fscy110)}}"
        ativo_grande = (f"{{\\c{hl}\\fscx{88 * esc_d:.0f}\\fscy{88 * esc_d:.0f}"
                        f"\\t(0,110,\\fscx{110 * esc_d:.0f}\\fscy{110 * esc_d:.0f})}}")
    elif anim == "caixa":
        ativo = f"{{\\c&HFFFFFF&\\3c{hl}\\bord{max(4, outline_w + 3):.0f}}}"
    elif anim == "brilho":
        ativo = f"{{\\c&HFFFFFF&\\3c{hl}\\bord{max(3, outline_w + 2):.0f}\\blur4}}"
    else:  # nenhuma / revelar
        ativo = f"{{\\c{hl}}}"

    destaque_re = regex_destaque(legenda, destaques_extra)

    def fmt(texto: str) -> str:
        t = escape_ass(sem_pontuacao(texto) if legenda.remover_pontuacao else texto)
        return t.upper() if legenda.caixa_alta else t

    # largura útil: a tela menos as margens e a faixa que a plataforma cobre dos lados
    livre = 1.0 - ((zona.esquerda + zona.direita) if zona is not None else 0.0)
    largura_util = max(fs * 4, largura * livre - 2 * max(40, int(largura * 0.06)) - 2 * outline_w)
    folga_ativo = 1.1 if anim == "pop" else 1.0  # a palavra ativa cresce no pop

    eventos: list[str] = []
    pals = palavras_do_clip(palavras, tl)
    if legenda.modo != "nenhuma" and pals:
        max_pal = 1 if legenda.modo == "uma-palavra" else legenda.max_palavras_por_linha * legenda.linhas
        por_linha = 1 if legenda.modo == "uma-palavra" else legenda.max_palavras_por_linha
        blocos: list[tuple[list[dict], list[list[int]]]] = []
        for bruto in blocos_de_palavras(pals, max_pal):
            # palavras longas não cabem em N por linha: o bloco vira mais de um, sem passar de `linhas` linhas
            textos_b = [fmt(w["texto"]) for w in bruto]
            pesos_b = [(esc_d if destaque_re and destaque_re.match(w["texto"]) else 1.0) * folga_ativo for w in bruto]
            linhas_b = quebrar_em_linhas(textos_b, pesos_b, por_linha, largura_util, fs, legenda.caixa_alta, legenda.fonte)
            for k in range(0, len(linhas_b), legenda.linhas):
                grupo = linhas_b[k:k + legenda.linhas]
                i0 = grupo[0][0]
                blocos.append((bruto[i0:grupo[-1][-1] + 1], [[j - i0 for j in ln] for ln in grupo]))

        for n_bloco, (bloco, linhas_idx) in enumerate(blocos):
            textos = [fmt(w["texto"]) for w in bloco]
            fixos = [bool(destaque_re and destaque_re.match(w["texto"])) for w in bloco]
            fim_linha = {ln[-1] for ln in linhas_idx[:-1]}
            # uma palavra que sozinha não cabe na largura: a fonte do bloco encolhe
            espaco = largura_estimada(" ", fs, legenda.caixa_alta, legenda.fonte)
            maior = max(sum(largura_estimada(textos[j], fs, legenda.caixa_alta, legenda.fonte) * (esc_d if fixos[j] else 1.0)
                            * folga_ativo for j in ln) + espaco * (len(ln) - 1) for ln in linhas_idx)
            reduz = f"\\fs{max(10, int(fs * largura_util / maior))}" if maior > largura_util else ""

            def montar(i_ativo: int | None) -> str:
                partes = []
                for j, t in enumerate(textos):
                    grande = fixos[j] and esc_d > 1.0
                    esc = f"\\fscx{100 * esc_d:.0f}\\fscy{100 * esc_d:.0f}" if grande else ""
                    if i_ativo is not None and j == i_ativo:
                        tag = (ativo_grande or f"{{{esc}}}{ativo}") if grande else ativo
                        partes.append(f"{tag}{t}{{\\r{reduz}}}" if reduz else f"{tag}{t}{{\\r}}")
                    elif anim == "revelar" and i_ativo is not None and j > i_ativo:
                        partes.append(f"{{\\alpha&HFF&}}{t}{{\\r{reduz}}}" if reduz else f"{{\\alpha&HFF&}}{t}{{\\r}}")
                    elif fixos[j]:
                        partes.append(f"{{\\c{hl}{esc}}}{t}{{\\r{reduz}}}" if reduz else f"{{\\c{hl}{esc}}}{t}{{\\r}}")
                    else:
                        partes.append(t)
                    if j in fim_linha:
                        partes.append("\\N")
                return " ".join(partes).replace(" \\N ", "\\N")

            # o bloco fica na tela até o próximo começar quando a pausa é curta (sem piscar entre blocos),
            # e um pouco depois da última palavra quando a pausa é longa, para dar tempo de ler
            prox = blocos[n_bloco + 1][0][0]["inicio"] if n_bloco + 1 < len(blocos) else None
            fim_bloco = bloco[-1]["fim"]
            if prox is not None and prox - fim_bloco <= SEGURA_ENTRE_BLOCOS:
                fim_bloco = prox
            else:
                fim_bloco = min(fim_bloco + RESPIRO_FIM_BLOCO, prox if prox is not None else tl.duracao)
            fim_bloco = max(fim_bloco, bloco[-1]["fim"])
            abre = f"{{{pos}{reduz}}}"
            if legenda.modo == "frase":
                eventos.append(f"Dialogue: 0,{ass_time(bloco[0]['inicio'])},{ass_time(fim_bloco)},Default,,0,0,0,,{abre}{montar(None)}")
                continue
            for i, w in enumerate(bloco):
                ini = bloco[0]["inicio"] if i == 0 else w["inicio"]
                fim = bloco[i + 1]["inicio"] if i + 1 < len(bloco) else fim_bloco
                if fim - ini < 0.01:
                    continue
                eventos.append(f"Dialogue: 0,{ass_time(ini)},{ass_time(fim)},Default,,0,0,0,,{abre}{montar(i)}")

    if usar_cartela and titulo and cartela is not None:
        cfs = max(10, int(cartela.tamanho * escala))
        estilos.append(
            f"Style: Cartela,{cartela.fonte},{cfs},{ass_color(cartela.cor, 1, '000000')},{ass_color(cartela.cor, 1, '000000')},"
            f"{ass_color(cartela.fundo, 1, 'FFFFFF')},{ass_color(cartela.fundo, 1, 'FFFFFF')},1,0,0,0,100,100,0,0,3,"
            f"{max(6, round(cfs * 0.25))},0,5,40,40,40,1"
        )
        texto_t = titulo.upper() if cartela.caixa_alta else titulo
        max_chars = max(10, int(largura / (cfs * 0.62)))
        linhas = _quebrar_titulo(escape_ass(texto_t), max_chars)
        hl_c = ass_inline(cartela.destaque, "FFE600")
        caps_originais = {p for p in titulo.split() if len(p) > 1 and p.isupper()}
        linhas_fmt = []
        for ln in linhas:
            ps = []
            for p in ln.split():
                if not cartela.caixa_alta and p in caps_originais:
                    ps.append(f"{{\\c{hl_c}}}{p}{{\\c{ass_inline(cartela.cor, '000000')}}}")
                else:
                    ps.append(p)
            linhas_fmt.append(" ".join(ps))
        cy = {"topo": 0.2, "centro": 0.45, "baixo": 0.8}[cartela.posicao]
        if zona is not None:
            from .plataformas import y_seguro

            cy = y_seguro(cy, 2 * cfs * 1.3 / altura, zona)
        dur = min(cartela.duracao, tl.duracao)
        eventos.append(
            f"Dialogue: 1,{ass_time(0)},{ass_time(dur)},Cartela,,0,0,0,,"
            f"{{\\an5\\pos({x},{int(altura * cy)})\\fad(120,250)}}" + "\\N".join(linhas_fmt)
        )

    header = (
        "[Script Info]\n"
        "; Gerado pelo Clipator\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {largura}\n"
        f"PlayResY: {altura}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        + "\n".join(estilos)
        + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(header + "\n".join(eventos) + "\n", encoding="utf-8")
    return saida


# ---- legenda oculta (.srt e .vtt) ----------------------------------------------------
MAX_CARACTERES_LINHA = 42
MAX_LINHAS = 2
MAX_DURACAO_CUE = 6.0
MIN_DURACAO_CUE = 0.8


def cues_de_frases(palavras: list[dict], max_chars: int = MAX_CARACTERES_LINHA, max_linhas: int = MAX_LINHAS,
                   max_dur: float = MAX_DURACAO_CUE, pausa: float = 0.6) -> list[tuple[float, float, list[str]]]:
    """Agrupa as palavras (já no tempo do clip) em legendas de frase inteira: até 2 linhas de 42
    caracteres e 6 s, quebrando em fim de frase e em pausa."""
    cues: list[tuple[float, float, list[str]]] = []
    atual: list[dict] = []

    def linhas_de(ws: list[dict]) -> list[str]:
        linhas, linha = [], ""
        for w in ws:
            t = w["texto"]
            if linha and len(linha) + 1 + len(t) > max_chars:
                linhas.append(linha)
                linha = t
            else:
                linha = f"{linha} {t}".strip()
        if linha:
            linhas.append(linha)
        return linhas

    def fechar() -> None:
        if atual:
            cues.append((atual[0]["inicio"], atual[-1]["fim"], linhas_de(atual)))
            atual.clear()

    for w in palavras:
        if atual:
            gap = w["inicio"] - atual[-1]["fim"]
            longo = w["fim"] - atual[0]["inicio"] > max_dur
            cheio = len(linhas_de(atual + [w])) > max_linhas
            fim_frase = bool(re.search(r"[.!?…]$", atual[-1]["texto"]))
            if gap >= pausa or longo or cheio or fim_frase:
                fechar()
        atual.append(w)
    fechar()
    # cada legenda fica pelo menos MIN_DURACAO_CUE na tela, sem invadir a próxima
    out = []
    for k, (a, b, ls) in enumerate(cues):
        prox = cues[k + 1][0] if k + 1 < len(cues) else None
        b = max(b, a + MIN_DURACAO_CUE)
        if prox is not None:
            b = min(b, prox - 0.01)
        out.append((round(a, 3), round(max(b, a + 0.05), 3), ls))
    return out


def _tempo(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def gerar_srt_vtt(palavras: list[dict], tl: Timeline, pasta: str | Path, nome: str = "legenda") -> tuple[Path, Path] | None:
    """Escreve legenda.srt e legenda.vtt do clip, no tempo do clip (cortes internos já descontados)."""
    cues = cues_de_frases(palavras_do_clip(palavras, tl))
    if not cues:
        return None
    pasta = Path(pasta)
    srt = pasta / f"{nome}.srt"
    vtt = pasta / f"{nome}.vtt"
    srt.write_text("\n".join(f"{i}\n{_tempo(a, ',')} --> {_tempo(b, ',')}\n" + "\n".join(ls) + "\n"
                             for i, (a, b, ls) in enumerate(cues, 1)), encoding="utf-8")
    vtt.write_text("WEBVTT\n\n" + "\n".join(f"{_tempo(a, '.')} --> {_tempo(b, '.')}\n" + "\n".join(ls) + "\n"
                                              for a, b, ls in cues), encoding="utf-8")
    return srt, vtt
