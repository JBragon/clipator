"""Renderização de um clip com FFmpeg: corte, reenquadramento, legenda, cartela, logo e áudio.

A ordem do pipeline (extrair trechos, concatenar, compor legenda e overlays num
grafo só e normalizar o áudio no fim) segue video-use/helpers/render.py, MIT
License, Copyright (c) 2026 Browser Use. Ver THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import hyperframes, media, plataformas, reframe, sons, subtitles
from .media import Progress
from .models import Clip, DirecaoArte, Estilo
from .timeline import Timeline
from .workspace import ProjetoWS, fontes_dir, write_json


@dataclass
class ResultadoRender:
    video: Path
    legenda: Path | None
    detector: str
    layout: str
    motor: str = "ffmpeg"
    aviso: str | None = None


def _fps_saida(fps: float) -> float:
    return min(60.0, fps) if fps > 0 else 30.0


def _cadeia_layout(estilo: Estilo, layout: str, src_w: int, src_h: int, out_w: int, out_h: int,
                   cmd_path: Path | None, x0: int, dois: reframe.Dividido | None, cam: reframe.Movel | None = None,
                   moveis: tuple[reframe.Movel, reframe.Movel] | None = None) -> str:
    """Grafo de filtros de vídeo de [vin] até [vlay]. `cam` e `moveis`: crops que andam sem degrau (sendcmd)."""
    cw, ch = reframe.tamanho_crop(src_w, src_h, out_w, out_h)
    y0 = (src_h - ch) // 2
    y0 -= y0 % 2
    send = f"sendcmd=f='{media.escape_filter_path(cmd_path)}'," if cmd_path else ""
    if layout in ("seguir-rosto", "centro"):
        send = send if layout == "seguir-rosto" else ""
        if send and cam is not None:
            return f"[vin]{send}{cam.filtro('cam', x0, y0)},setsar=1[vlay]"
        return f"[vin]{send}crop@cam=w={cw}:h={ch}:x={x0}:y={y0},scale={out_w}:{out_h}:flags=lanczos,setsar=1[vlay]"
    if layout == "dividido" and dois:
        meia = out_h // 2 - (out_h // 2) % 2
        cima, baixo = dois.caixas
        if dois.trilhas and cmd_path and moveis:  # cada metade acompanha a própria pessoa (o sendcmd move os dois recortes)
            (_, xa, ya, _), (_, xb, yb, _) = dois.trilhas[0][0], dois.trilhas[1][0]
            duo = (f"[va]{moveis[0].filtro('cima', xa, ya)},setsar=1[top];"
                   f"[vb]{moveis[1].filtro('baixo', xb, yb)},setsar=1[bot];"
                   f"[top][bot]vstack=inputs=2")
        else:
            duo = (f"[va]crop@cima=w={cima.w}:h={cima.h}:x={cima.x}:y={cima.y},scale={out_w}:{meia}:flags=lanczos,setsar=1[top];"
                   f"[vb]crop@baixo=w={baixo.w}:h={baixo.h}:x={baixo.x}:y={baixo.y},scale={out_w}:{out_h - meia}:flags=lanczos,setsar=1[bot];"
                   f"[top][bot]vstack=inputs=2")
        if not dois.trechos:
            return f"[vin]{send}split=2[va][vb];{duo}[vlay]"
        # a fonte alterna entre plano aberto (as duas pessoas) e close: no close segue o rosto, no aberto empilha
        quando = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in dois.trechos)
        return (f"[vin]{send}split=3[vs][va][vb];"
                + (f"[vs]{cam.filtro('cam', x0, y0)},setsar=1[solo];" if cam is not None else
                   f"[vs]crop@cam=w={cw}:h={ch}:x={x0}:y={y0},scale={out_w}:{out_h}:flags=lanczos,setsar=1[solo];") +
                f"{duo}[duo];[solo][duo]overlay=0:0:enable='{quando}'[vlay]")
    if layout in ("fundo-desfocado", "dividido"):
        return (
            f"[vin]split=2[bgsrc][fgsrc];"
            f"[bgsrc]{media.blurred_backdrop(out_w, out_h)},eq=brightness=-0.08[bg];"
            f"[fgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vlay]"
        )
    # original: só ajusta ao quadro, com barras se precisar
    return (f"[vin]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[vlay]")


def _par(v: float) -> int:
    v = int(round(v))
    return v - v % 2


ROSTO_EM_CIMA = (0.30, 0.40)  # em-cima: o rosto com 30% da altura da metade de baixo, o centro a 40% dela
ROSTO_JANELA = (0.34, 0.42)
ROSTO_CORTE = (0.26, 0.30)  # tela dividida das direções guiadas pela fala: o rosto mais alto, a legenda fica embaixo dele


def enquadrar_rosto(rosto: tuple[float, float, float] | None, out_w: int, out_h: int, caixa_w: int, caixa_h: int,
                    alvo_altura: float, alvo_y: float, zoom_max: float = 2.4) -> tuple[int, int, int, int]:
    """(largura, altura, x, y): escala o vídeo enquadrado e recorta uma caixa com o rosto no lugar certo.

    Sem rosto detectado: sem zoom, a caixa no centro, um pouco para cima (onde o rosto costuma estar).
    """
    if rosto is None:
        return out_w, out_h, _par((out_w - caixa_w) / 2), _par(max(0, min(out_h - caixa_h, out_h * 0.40 - caixa_h * 0.42)))
    cx, cy, fh = rosto[:3]
    topo = rosto[3] if len(rosto) > 3 else None  # o alto da cabeça mais alta do corte (outra câmera, outra pessoa)
    z = max(1.0, min(zoom_max, alvo_altura * caixa_h / max(1.0, fh * out_h)))
    while True:
        sw, sh = _par(out_w * z), _par(out_h * z)
        sw, sh = max(sw, caixa_w), max(sh, caixa_h)
        x = _par(max(0, min(sw - caixa_w, cx * sw - caixa_w / 2)))
        y = max(0.0, min(sh - caixa_h, cy * sh - alvo_y * caixa_h))
        if topo is None:
            break
        y = max(0.0, min(y, topo * sh - 0.03 * caixa_h))  # nenhuma cabeça sai cortada no alto da caixa
        if z <= 1.0 or (cy * sh - y) / caixa_h <= 0.62:
            break
        z = max(1.0, z - 0.1)  # cabeças em alturas muito diferentes: menos zoom para caber todo mundo
    return sw, sh, x, _par(y)


def cadeia_mistura(layout: str, da: DirecaoArte, primaria: str, out_w: int, out_h: int, ic: int, im: int | None,
                   recorte: str, filtro_chroma: str = "", rosto: tuple[float, float, float] | None = None, janela: object | None = None,
                   alvo_em_cima: tuple[float, float] | None = None) -> list[str]:
    """Junta [vlay] (o vídeo matriz já enquadrado) com a camada de cenas (entrada `ic`) até [vda].

    `recorte` (só no layout "fundo"): "chroma" (usa `filtro_chroma`), "mascara" (máscara cinza na entrada `im`)
    ou "nenhum" (a pessoa entra inteira, sem recorte). `rosto` (cx, cy, altura em frações de [vlay]) põe o
    locutor no centro e no tamanho certo em cada layout.
    """
    cor = "0x" + primaria.lstrip("#")
    partes = [f"[{ic}:v]setpts=PTS-STARTPTS,scale={out_w}:{out_h},format=yuva420p[cen]"]
    if layout == "em-cima":
        top = _par(out_h * da.proporcao)
        hb = out_h - top
        sw, sh, xc, yc = enquadrar_rosto(rosto, out_w, out_h, out_w, hb, *(alvo_em_cima or ROSTO_EM_CIMA))
        escala = f"scale={sw}:{sh}:flags=lanczos," if (sw, sh) != (out_w, out_h) else ""
        partes += [f"[vlay]{escala}crop={out_w}:{hb}:{xc}:{yc}[vbaixo]",
                   f"[cen][vbaixo]overlay=0:{top}:eof_action=repeat[vm]",
                   f"[vm]drawbox=x=0:y={max(0, top - 3)}:w=iw:h=6:color={cor}@1:t=fill[vda]"]
    elif layout == "fundo":
        ph = _par(out_h * da.pessoa_escala)
        if recorte == "chroma":
            partes.append(f"[vlay]{filtro_chroma},scale=-2:{ph}[pessoa]")
        elif recorte == "mascara" and im is not None:
            partes += [f"[{im}:v]setpts=PTS-STARTPTS,scale={out_w}:{out_h}:flags=bicubic,format=gray,lut=y=if(lt(val\\,24)\\,0\\,val)[mk]",
                       "[vlay]format=yuva420p[vp]",
                       "[vp][mk]alphamerge[pa]",
                       f"[pa]scale=-2:{ph}[pessoa]"]
        else:
            partes.append(f"[vlay]scale=-2:{ph}[pessoa]")
        if rosto is not None:  # o rosto (não a caixa do vídeo) vai para a posição pedida
            pw = ph * out_w / out_h
            px = int(max(-pw * 0.35, min(out_w - pw * 0.65, da.pessoa_x * out_w - rosto[0] * pw)))
            partes.append(f"[cen][pessoa]overlay=x={px}:y=H-h:format=auto:eof_action=repeat[vda]")
        else:
            partes.append(f"[cen][pessoa]overlay=x=(W-w)*{da.pessoa_x:.3f}:y=H-h:format=auto:eof_action=repeat[vda]")
    elif layout == "janela" and janela is not None:  # o retângulo vem de composicao.py: o mesmo que a arte recebe para desviar
        borda = max(4, _par(out_w * 0.008))
        pw, ph = janela.w - 2 * borda, janela.h - 2 * borda
        if da.janela_encaixe == "barras":  # o quadro inteiro, com barras
            fit = f"scale={pw}:{ph}:force_original_aspect_ratio=decrease:flags=lanczos,pad={pw}:{ph}:(ow-iw)/2:(oh-ih)/2:color=black"
        else:  # recorta pela proporção da janela, com o rosto no lugar; a escala é sempre igual nos dois eixos
            z = max(pw / out_w, ph / out_h)
            cw, ch = _par(pw / z), _par(ph / z)
            sw, sh, xc, yc = enquadrar_rosto(rosto, out_w, out_h, cw, ch, *ROSTO_JANELA)
            perto = f"scale={sw}:{sh}:flags=lanczos," if (sw, sh) != (out_w, out_h) else ""
            fit = f"{perto}crop={cw}:{ch}:{xc}:{yc},scale={pw}:{ph}:flags=lanczos,setsar=1"
        partes += [f"[vlay]{fit},pad=iw+{2 * borda}:ih+{2 * borda}:{borda}:{borda}:color={cor}[pip]",
                   f"[cen][pip]overlay={janela.x}:{janela.y}:eof_action=repeat[vda]"]
    elif layout == "janela":
        pw = _par(out_w * da.janela_escala)
        borda = max(4, _par(out_w * 0.008))
        margem = _par(out_w * 0.05)
        jw, jh, jx, jy = enquadrar_rosto(rosto, out_w, out_h, out_w, out_h, *ROSTO_JANELA) if rosto else (out_w, out_h, 0, 0)
        perto = f"scale={jw}:{jh}:flags=lanczos,crop={out_w}:{out_h}:{jx}:{jy}," if (jw, jh) != (out_w, out_h) else ""
        partes += [f"[vlay]{perto}scale={pw}:-2,pad=iw+{2 * borda}:ih+{2 * borda}:{borda}:{borda}:color={cor}[pip]",
                   f"[cen][pip]overlay=W-w-{margem}:H-h-{_par(out_h * 0.2)}:eof_action=repeat[vda]"]
    else:  # sobreposto: cartões com alfa por cima do vídeo
        partes.append("[vlay][cen]overlay=0:0:format=auto:eof_action=pass[vda]")
    return partes


def _suave(k: str) -> str:
    """Expressão do FFmpeg para a curva suave (smoothstep) de `k`, já limitado a 0..1."""
    return f"(({k})*({k})*(3-2*({k})))"


def cadeia_montagem(partes: list[str], mont: dict, out_w: int, out_h: int, trans: float = 0.3) -> list[str]:
    """Põe a montagem do curta (artes/curta.py: montagem) por cima da mistura de `cadeia_mistura`.

    Por baixo fica o vídeo em tela cheia ([vlay], com o zoom dos trechos marcados); a mistura (vídeo + animação) entra
    deslizando de cima nos trechos "dividida" e sai subindo; nos destaques, a camada de cenas cobre a tela inteira.
    Sem trecho de vídeo nem destaque, nada muda.
    """
    trechos = mont.get("trechos") or []
    destaques = mont.get("destaques") or []
    divididas = [s for s in trechos if s["tela"] == "dividida"]
    if not destaques and len(divididas) == len(trechos):
        return partes
    fim_total = max((s["t1"] for s in trechos), default=0.0)
    novas = [p.replace("[vlay]", "[vlaym]") for p in partes]
    novas[-1] = novas[-1][: novas[-1].rindex("[vda]")] + "[vmix]"
    pre = ["[vlay]split=2[vlaym][vfull0]"]
    if destaques:
        novas[0] = novas[0][: novas[0].rindex("[cen]")] + "[cen0]"
        novas.insert(1, "[cen0]split=2[cen][cenx]")
    zooms = mont.get("zooms") or []
    if zooms:
        z = "1+" + "+".join(f"between(t,{a['t0']:.3f},{a['t1']:.3f})*{a['escala'] - 1:.3f}" for a in zooms)
        pre.append(f"[vfull0]scale=w='trunc(iw*({z})/2)*2':h='trunc(ih*({z})/2)*2':eval=frame:flags=bicubic,"
                   f"crop=w={out_w}:h={out_h}:x='(iw-ow)/2':y='(ih-oh)*0.3',setsar=1[vfull]")
    else:
        pre.append("[vfull0]null[vfull]")
    janelas, ys = [], []
    for k, s in enumerate(trechos):
        if s["tela"] != "dividida":
            continue
        entra = s["t0"] > 0.05 and k > 0
        sai = s["t1"] < fim_total - 0.05
        a, b = (max(0.0, s["t0"] - trans) if entra else s["t0"]), s["t1"]
        janelas.append(f"between(t,{a:.3f},{b:.3f})")
        termos = []
        if entra:
            termos.append(f"1-{_suave(f'clip((t-{a:.3f})/{trans},0,1)')}")
        if sai:
            termos.append(_suave(f"clip((t-{b - trans:.3f})/{trans},0,1)"))
        if termos:
            m = termos[0] if len(termos) == 1 else f"max({termos[0]},{termos[1]})"
            ys.append(f"between(t,{a:.3f},{b:.3f})*({m})")
    y = f"-{out_h}*({'+'.join(ys)})" if ys else "0"
    base = "vfull"
    if janelas:
        novas.append(f"[vfull][vmix]overlay=x=0:y='{y}':enable='{'+'.join(janelas)}':eof_action=pass[vmo]")
        base = "vmo"
    else:
        novas.append("[vmix]nullsink")
    if destaques:
        quando = "+".join(f"between(t,{d['t0']:.3f},{d['t1'] - 0.001:.3f})" for d in destaques)
        novas.append(f"[{base}][cenx]overlay=0:0:enable='{quando}':eof_action=pass[vda]")
    else:
        novas.append(f"[{base}]null[vda]")
    return pre + novas


def _camada_referencias(projeto: ProjetoWS, clip: Clip, estilo: Estilo, tl: Timeline, pals: list[dict], out_w: int, out_h: int,
                        pasta: Path, ad, prog, cancelar, log) -> Path | None:
    """A camada transparente com as imagens reais do que a fala cita (referencias.py), ou None.

    Nos estilos de curta a imagem já vai no painel pelo roteiro; sem IA, sem rede ou sem nome citado, nada muda.
    Falha aqui nunca derruba o render: o clip sai sem as imagens e o relato diz por quê.
    """
    from . import referencias
    from .relato import Relato

    d = estilo.direcao
    if d.ativa and d.modo == "arte" and d.arte:
        from .artes.cortes import eh_corte

        if eh_corte(d.arte) and d.arte != "geo-em-cena":
            return None
    rel = Relato(log, lambda msg: prog(0, msg, 0.0, 0.0))
    try:
        if ad is None:
            from .melhorar import ia_do_workspace

            ad = ia_do_workspace(projeto.ws)
        if ad is None or hyperframes.comando() is None:
            return None
        from .ai.adapter import CacheIA

        pals_clip = subtitles.palavras_do_clip(pals, tl) if pals else []
        refs = referencias.obter(pasta, pals_clip, ad, clip.titulo, cancelar, rel.passo, CacheIA(projeto.analise_dir / "cache_ia"))
        if not refs:
            return None
        pasta_r = pasta / "referencias-camada"
        jan = referencias.preparar(referencias.janelas(refs, tl.duracao), pasta, pasta_r)
        visual = referencias.visual_do_estilo(estilo, clip.estilo or "")
        fonte = estilo.legenda.fonte
        _, p_fonte = hyperframes._fonte_css(fonte, [projeto.canal.path / "assets" / "fontes"])
        doc = referencias.documento(jan, visual, out_w, out_h, tl.duracao, referencias.area(estilo, out_w, out_h),
                                    estilo.legenda.destaque or "#FFD400", fonte)
        if p_fonte is not None:
            doc = doc.replace("<style>", f"<style>@font-face {{ font-family: '{fonte}'; src: url('fontes/{p_fonte.name}'); }}\n", 1)
        saida = pasta_r / "camada.webm"
        indice = pasta_r / "index.html"
        if not (saida.exists() and indice.exists() and indice.read_text(encoding="utf-8") == doc):
            rel.passo(f"desenhando {len(jan)} cartão(ões) de imagem real no visual “{visual}”")
            hyperframes.escrever_projeto(pasta_r, hyperframes.Composicao(doc, [p_fonte] if p_fonte else []))
            hyperframes.renderizar(pasta_r, saida, 30, lambda fr, msg: prog(fr, msg, 0.0, 0.0), cancelar)
        return saida
    except media.Cancelado:
        raise
    except Exception as exc:  # noqa: BLE001
        rel.passo(f"imagens reais ficaram de fora: {exc}")
        return None


def _da_do_estilo(projeto: ProjetoWS, estilo: Estilo):
    """(DA que o estilo pede, com a marca do canal por cima; avisos). (None, []) se o estilo não pede DA.

    Erro na DA não derruba o render: ele segue sem ela e o aviso vai para o relato.
    """
    try:
        from .arte.guia import da_do_estilo

        return da_do_estilo(estilo, projeto.canal.path)
    except Exception as exc:  # noqa: BLE001
        return None, [f"direção de arte ignorada: {exc}"]


def _estilo_com_da(estilo: Estilo, da_canal) -> Estilo:
    """Troca os `da:<token>` do estilo pelos valores da DA (e preenche `legenda: {da: true}`)."""
    texto = estilo.model_dump_json()
    if '"da:' not in texto and '"da":true' not in texto.replace(" ", ""):
        return estilo
    try:
        from .arte.compilar import aplicar_no_estilo

        return aplicar_no_estilo(estilo, da_canal)
    except Exception:  # noqa: BLE001 - token errado não impede o render: fica o valor do estilo
        return estilo


def _css_do_canal(da_canal) -> str:
    if da_canal is None:
        return ""
    from .arte.compilar import css

    return css(da_canal)


def _preparar_direcao(projeto: ProjetoWS, clip: Clip, estilo: Estilo, tl: Timeline, pals: list[dict], out_w: int,
                      out_h: int, fps: float, pasta: Path, preview: bool, video: Path, filtro_vlay: str,
                      entradas_trechos: list[str], prog, cancelar: threading.Event | None, n0: int,
                      edicao_doc=None, ad=None, log=None, rosto=None):
    """Camada de cenas + recorte. Devolve (entradas, partes do grafo até [vda], sons [(chave, t, efeito)], aviso)."""
    from . import direcao, recorte
    from . import edicao as _edicao
    from .relato import Relato

    rel = Relato(log, lambda msg: prog(0, msg, 0.0, 0.0))
    da = estilo.direcao
    try:
        canal_da = projeto.canal.info()[0].direcao_de_arte or {}
    except Exception:  # noqa: BLE001
        canal_da = {}
    cores_clip = {}
    if (pasta / "direcao-arte.json").exists():  # as cores ajustadas na direção de arte do clip
        from . import desenho as _des

        cores_clip = (_des.ler(pasta) or {}).get("cores") or {}
    arte_estilo, _ = _da_do_estilo(projeto, estilo)  # o estilo manda; o canal só pôs a marca por cima
    ajustes_da: dict = {}
    css_da = ""
    if arte_estilo is not None:
        from .arte.compilar import css as _css_da, para_ficha

        ajustes_da = para_ficha(arte_estilo)
        css_da = _css_da(arte_estilo)
    f = direcao.ficha(da.ficha, {**ajustes_da, **da.cores, **da.fontes, **canal_da, **cores_clip})
    pals_clip = subtitles.palavras_do_clip(pals, tl) if pals else []
    avisos_arte: list[str] = []
    arte = da.arte if da.modo == "arte" else None
    if arte:
        from . import artes

        f, avisos_arte = artes.ficha_legivel(f)
    # as cenas moram no edicao.json (o editor mexe nelas); na primeira vez o planejador propõe
    doc = edicao_doc if edicao_doc is not None else _edicao.carregar(pasta)
    cenas = [i for i in doc.itens if i.tipo == "cena"]
    if not cenas and not doc.cenas_planejadas and edicao_doc is None and ad is not None:
        # pré-produção da IA: análise do corte -> roteiro -> composição (desenho.py), salvo em direcao-arte.json
        from . import desenho

        dd = desenho.ler(pasta)
        if not desenho.do_modo(dd, da.modo):
            dd = desenho.gerar(projeto, clip, tl, pals_clip, estilo, ad, rel, cancelar)
        novos = [_edicao.Item(**i) for i in desenho.para_itens(dd)]
        if novos and arte_estilo is not None and da.modo != "desenho":  # confere as cenas da IA contra a DA
            from .arte.guia import filtrar_cenas

            cenas_ia = [i for i in novos if i.tipo == "cena"]
            aceitas, fora = filtrar_cenas(cenas_ia, arte_estilo, tl.duracao)
            novos = [i for i in novos if i.tipo != "cena"] + aceitas
            if fora:
                rel.passo(f"direção de arte “{arte_estilo.da.nome}”: {len(fora)} cena(s) fora — " + "; ".join(fora[:4]))
            if arte:
                novos = artes.encostar(novos, tl.duracao)
        if novos:  # nos estilos de cenas, sem nada da IA quem planeja são as regras, logo abaixo
            doc = doc.model_copy(update={"itens": doc.itens + novos, "cenas_planejadas": True})
            doc = _edicao.salvar(pasta, doc, tl.duracao)
            cenas = [i for i in doc.itens if i.tipo == "cena"]
    if arte and not cenas and not doc.cenas_planejadas and edicao_doc is None:  # sem IA: uma cena por frase, só com o que foi dito
        novos = [_edicao.Item(tipo="cena", origem="heuristica", **c)
                 for c in artes.planejar_regras(arte, pals_clip, tl.duracao, artes.assinatura_timeline(tl), da.parametros)]
        if arte_estilo is not None and novos:  # o ritmo é da direção de arte; a cena fica no ar até a próxima
            from .arte.guia import filtrar_cenas

            novos, fora = filtrar_cenas(novos, arte_estilo, tl.duracao)
            novos = artes.encostar(novos, tl.duracao)
            if fora:
                rel.passo(f"direção de arte “{arte_estilo.da.nome}”: {len(fora)} cena(s) fora — " + "; ".join(fora[:4]))
        rel.passo(f"{len(novos)} cena(s) tiradas das frases da fala")
        doc = doc.model_copy(update={"itens": doc.itens + novos, "cenas_planejadas": True})
        doc = _edicao.salvar(pasta, doc, tl.duracao)
        cenas = [i for i in doc.itens if i.tipo == "cena"]
    if arte and cenas:  # o corte mudou: as cenas voltam a seguir a âncora, e o trecho removido sai com aviso
        cenas, avs, mudou = artes.reancorar(cenas, pals_clip, tl.duracao, artes.assinatura_timeline(tl))
        avisos_arte += avs
        if mudou and edicao_doc is None:
            doc = _edicao.salvar(pasta, doc.model_copy(update={"itens": [i for i in doc.itens if i.tipo != "cena"] + cenas}), tl.duracao)
    if not arte and not cenas and not doc.cenas_planejadas and edicao_doc is None:
        planejadas = direcao.planejar_regras(pals_clip, tl.duracao, clip.titulo, da.densidade)
        rel.passo(f"{len(planejadas)} cena(s) pelas regras (números, listas, nomes e citações da fala)")
        if arte_estilo is not None and planejadas:  # confere as cenas contra a DA do estilo
            from .arte.guia import filtrar_cenas

            planejadas, fora = filtrar_cenas(planejadas, arte_estilo, tl.duracao)
            if fora:
                rel.passo(f"direção de arte “{arte_estilo.da.nome}”: {len(fora)} cena(s) fora — " + "; ".join(fora[:4]))
        novos = [_edicao.Item(tipo="cena", inicio=c.inicio, fim=c.fim, params=c.params, origem="heuristica", motivo=c.motivo)
                 for c in planejadas]
        doc = doc.model_copy(update={"itens": doc.itens + novos, "cenas_planejadas": True})
        doc = _edicao.salvar(pasta, doc, tl.duracao)
        cenas = [i for i in doc.itens if i.tipo == "cena"]
    lista = [{"inicio": c.inicio, "fim": c.fim, "params": c.params} for c in cenas]
    if arte and any(c.params.get("cores") for c in cenas):  # as cores do painel moram na cena (e voltam com a versão)
        cores_cena = next(c.params["cores"] for c in cenas if c.params.get("cores"))
        f, avs = artes.ficha_legivel(direcao.ficha(da.ficha, {**ajustes_da, **da.cores, **da.fontes, **canal_da, **cores_clip, **cores_cena}))
        avisos_arte += avs
    if cenas:
        rel.passo("cenas do clip: " + ", ".join(f"{c.params.get('cena')} em {c.inicio:.1f} s" for c in cenas[:8])
                  + (" …" if len(cenas) > 8 else ""))
    sons_da = direcao.eventos_de_som(lista, f) if da.sons else []

    aviso = None
    entradas: list[str] = []
    # 1) a camada de cenas (HyperFrames); sem ele, só o fundo da ficha
    fontes_css, fontes = "", []
    for nome in dict.fromkeys([f.fonte_titulo, f.fonte_corpo, "Anton", "Montserrat ExtraBold"]):
        bloco, p = hyperframes._fonte_css(nome, [projeto.canal.path / "assets" / "fontes"])
        if p is not None and p not in fontes:
            fontes_css += bloco
            fontes.append(p)
    pasta_c = pasta / (("cenas-versao" if edicao_doc is not None else "cenas-preview") if preview else "cenas")
    if arte:
        for c in lista:
            c["palavras"] = artes.palavras_da_cena(pals_clip, c["inicio"], c["fim"])
        avisos_arte += artes.copiar_midias(lista, projeto.canal.path / "assets" / "arte", pasta_c)
        from .artes import curta as _curta_refs

        avisos_arte += _curta_refs.copiar_referencias(lista, pasta, pasta_c)  # as imagens reais do que a fala cita
    zona_arte = plataformas.info(clip.plataforma, clip.formato).zona if arte else None
    geo, corte = None, False  # um cálculo só: a arte desvia do mesmo retângulo em que o vídeo entra
    if arte:
        from .artes.cortes import eh_corte

        corte = eh_corte(arte)
        if arte == "geo-em-cena":  # lugar ambíguo, ausente ou cortado: aviso, e nada desenhado no lugar
            from .artes import geo as _geo

            avisos_arte += _geo.avisos(lista, tl.duracao)
    if da.layout == "em-cima" or (da.layout == "janela" and da.janela_canto):
        from . import composicao

        geo = composicao.geometria(da, out_w, out_h, plataformas.info(clip.plataforma, clip.formato).zona, estilo.legenda)
    doc_html = direcao.compor_camada(lista, f, out_w, out_h, tl.duracao, da.layout, da.proporcao, clip.titulo, 30,
                                     fontes_css + css_da, arte, zona_arte, da.parametros, geo, da.janela_canto)
    camada = pasta_c / "cenas.webm"
    if hyperframes.comando() is None:
        aviso = "HyperFrames não instalado: a direção de arte saiu só com o fundo, sem as cenas animadas."
        alfa = "@0" if da.layout == "sobreposto" else ""  # por cima do vídeo, sem cenas: camada vazia
        entradas += ["-f", "lavfi", "-i", f"color=c=0x{f.fundo.lstrip('#')}{alfa}:s={out_w}x{out_h}:r=30:d={tl.duracao:.3f},format=rgba"]
    else:
        indice = pasta_c / "index.html"
        if camada.exists() and indice.exists() and indice.read_text(encoding="utf-8") == doc_html:
            rel.passo("camada de cenas igual à anterior: aproveitada")
        else:
            rel.passo(f"desenhando {len(lista)} cena(s) com a ficha {f.nome} (HyperFrames)")
            prog(0, "desenhando as cenas", 0.0, 0.25)
            hyperframes.escrever_projeto(pasta_c, hyperframes.Composicao(doc_html, fontes))
            hyperframes.renderizar(pasta_c, camada, 30, lambda fr, msg: prog(fr, msg, 0.0, 0.25), cancelar)
        entradas += ["-c:v", "libvpx-vp9", "-i", str(camada)]
    ic, im = n0, None
    # 2) o recorte (só quando a pessoa vai na frente da animação)
    modo, filtro_ch = "nenhum", ""
    if da.layout == "fundo":
        ch = None
        if da.recorte in ("auto", "chroma"):
            meios = [(s + e) / 2 for s, e in tl.trechos][:3] or [0.0]
            ch = recorte.detectar_chroma(recorte.quadros_de_amostra(video, meios))
        if ch is not None:
            modo, filtro_ch = "chroma", recorte.filtro_chroma(ch)
            rel.passo(f"fundo {('verde' if ch.canal == 'green' else 'azul')} detectado: recorte por chroma key")
        elif da.recorte == "oval":
            png = pasta / "recorte-oval.png"
            if not png.exists():
                from PIL import Image

                Image.fromarray((recorte.mascara_oval(out_w, out_h) * 255).astype("uint8")).save(png)
            entradas += ["-loop", "1", "-i", str(png)]
            modo, im = "mascara", n0 + 1
        else:
            mw = recorte.LARGURA_MASCARA
            mh = _par(mw * out_h / out_w)
            chave = recorte.chave_mascara(video, list(tl.trechos), filtro_vlay, mw, mh)
            saida = pasta / f"recorte-{chave}.mkv"
            if saida.exists():
                rel.passo("recorte da pessoa já feito antes: aproveitado do cache do clip")
            else:
                for velho in pasta.glob("recorte-*.mkv"):
                    velho.unlink(missing_ok=True)  # enquadramento ou trecho mudou: a máscara antiga não serve
                cmd = ([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", *entradas_trechos,
                        "-filter_complex", f"{filtro_vlay};[vlay]scale={mw}:{mh},format=rgb24[q]", "-map", "[q]",
                        "-t", f"{tl.duracao:.3f}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
                rel.passo(f"recortando a pessoa quadro a quadro ({tl.duracao:.0f} s de vídeo)")
                try:
                    recorte.gerar_mascara(cmd, mw, mh, fps, tl.duracao, saida,
                                          progresso=lambda fr, msg: prog(fr, msg, 0.25, 0.2), cancelar=cancelar)
                except recorte.RecorteTravou as exc:
                    rel.passo(f"o recorte travou ({exc}); segui com a máscara oval")
                    saida = pasta / "recorte-oval.png"
                    if not saida.exists():
                        from PIL import Image

                        Image.fromarray((recorte.mascara_oval(out_w, out_h) * 255).astype("uint8")).save(saida)
                    entradas += ["-loop", "1"]
            entradas += ["-i", str(saida)]
            modo, im = "mascara", n0 + 1
    if da.layout in ("em-cima", "janela", "fundo"):
        rel.passo("locutor enquadrado pelo rosto" + (f" (centro em {rosto[0]:.0%} × {rosto[1]:.0%}, rosto com {rosto[2]:.0%} da altura)"
                                                     if rosto else ": nenhum rosto achado, enquadramento padrão"))
    partes = cadeia_mistura(da.layout, da, f.primaria, out_w, out_h, ic, im, modo, filtro_ch, rosto,
                            geo.video if geo is not None and da.layout == "janela" else None, ROSTO_CORTE if corte else None)
    if arte and corte and da.layout in ("em-cima", "janela"):
        from .artes import curta as _curta

        if _curta.ativo(lista):  # o ritmo de short: vídeo em tela cheia entre as ilustrações, destaques e zoom
            mont = _curta.montagem(lista, tl.duracao)
            partes = cadeia_montagem(partes, mont, out_w, out_h)
            so_video = sum(s["t1"] - s["t0"] for s in mont["trechos"] if s["tela"] == "video")
            rel.passo(f"montagem: {len(mont['trechos'])} trecho(s), {so_video:.1f} s de vídeo em tela cheia, "
                      f"{len(mont['destaques'])} destaque(s)" + "".join(f" · {d['texto']} em {d['t0']:.1f} s" for d in mont["destaques"][:4]))
    for a in avisos_arte:
        rel.passo(a)
    if avisos_arte:
        aviso = " ".join(filter(None, [aviso, *avisos_arte]))
    return entradas, partes, sons_da, aviso


def _aplicar_abertura(projeto: ProjetoWS, estilo: Estilo, tl: Timeline, pals: list[dict], saida: Path, pasta: Path,
                      tem_audio: bool, fps: float, preview: bool, destaques: list[str] | None,
                      cancelar: threading.Event | None, log: Callable[[str], None] | None) -> str | None:
    """Ganchos do próprio corte em preto e branco antes dele (abertura.py). Devolve um aviso quando não deu."""
    from . import abertura

    cfg = estilo.abertura
    pals_clip = subtitles.palavras_do_clip(pals, tl) if pals else []
    ganchos = abertura.manuais(cfg, tl) if cfg.trechos else abertura.escolher(
        pals_clip, tl.duracao, cfg, abertura.energia_do_clip(projeto.sinais(), tl),
        subtitles.regex_destaque(estilo.legenda, destaques))
    if not ganchos:
        return "Corte curto ou sem fala que sirva de gancho: saiu sem a abertura em preto e branco."
    som = None
    if cfg.som:
        som = sons.resolver(cfg.som, [projeto.canal.path, projeto.canal.path / "assets", projeto.ws.root])
    tmp = saida.with_name(saida.stem + ".abertura.tmp.mp4")
    try:
        dur = abertura.montar(saida, tmp, ganchos, cfg, tem_audio, fps, preview, som, estilo.volume_sons,
                              cancelar=cancelar)
    except BaseException:
        media.apagar_parcial(tmp)
        raise
    media.substituir(tmp, saida)
    write_json(pasta / ("abertura.preview.json" if preview else "abertura.json"),
               {"duracao": round(dur, 3), "ganchos": [{"inicio": g.inicio, "fim": g.fim, "texto": g.texto, "nota": g.nota}
                                                     for g in ganchos]})
    if pals_clip and not preview:  # a legenda oculta acompanha o vídeo final, com os ganchos na frente
        subtitles.gerar_srt_vtt(abertura.palavras_finais(pals_clip, ganchos), Timeline.de_clip(0.0, dur + tl.duracao + 1), pasta)
    if log:
        log(f"abertura com {len(ganchos)} gancho(s), {dur:.1f} s")
    return None


def _escolher_layout(estilo: Estilo, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
    if abs(src_w / max(src_h, 1) - out_w / out_h) < 0.02:
        return "original"
    return estilo.reenquadramento


def renderizar_clip(
    projeto: ProjetoWS,
    clip: Clip,
    estilo: Estilo,
    preview: bool = False,
    progresso: Progress | None = None,
    cancelar: threading.Event | None = None,
    destaques_ia: list[str] | None = None,
    pasta_estilo: Path | None = None,
    edicao_doc: object | None = None,
    saida_forcada: Path | None = None,
    exigir_ia: bool = True,
    log: Callable[[str], None] | None = None,
    enquadrar_rosto: bool = True,
) -> ResultadoRender:
    """`edicao_doc` renderiza uma versão guardada (em vez do edicao.json) em `saida_forcada`; `exigir_ia=False` só nas
    amostras do passo 3 (cenas fixas num vídeo neutro, para mostrar o visual)."""
    # direção de arte do canal (arte/direcao.yaml): tokens `da:` do estilo, tratamento de cor e carimbo do clip
    da_canal, _avisos_da = _da_do_estilo(projeto, estilo)  # a DA do estilo (nome mantido: é a que vale no clip)
    try:
        from .arte.guia import referencia_do_estilo

        ref_arte = referencia_do_estilo(estilo)
    except Exception:  # noqa: BLE001
        ref_arte = None
    estilo = _estilo_com_da(estilo, da_canal)
    if estilo.direcao.ativa:  # a composição escolhida no clip vale sobre a do estilo, e volta junto com a versão
        from . import edicao as _ed

        estilo = _ed.estilo_com_layout(estilo, edicao_doc if edicao_doc is not None else _ed.carregar(projeto.clips_dir / clip.id))
    if estilo.direcao.modo == "arte" and da_canal is not None:  # o volume dos efeitos também é da DA
        estilo = estilo.model_copy(update={"volume_sons": da_canal.da.som.volume_efeitos})
    ad = None
    if estilo.direcao.modo == "arte" and not preview:  # a IA melhora o plano, mas o estilo funciona sem ela
        from .melhorar import ia_do_workspace

        ad = ia_do_workspace(projeto.ws)
    if estilo.requer_ia:
        from .melhorar import MSG_SEM_IA, SemIA, ia_do_workspace

        ad = ia_do_workspace(projeto.ws)
        if ad is None and exigir_ia:
            raise SemIA(f"O estilo “{estilo.nome}” usa IA. {MSG_SEM_IA}")
    video = projeto.video_path()
    if video is None:
        raise FileNotFoundError("O projeto ainda não tem vídeo em fonte/")
    info = media.probe(video)
    fim = min(clip.fim, info.duracao) if info.duracao else clip.fim
    tl = Timeline.de_clip(clip.inicio, fim, clip.cortes_internos)
    if clip.formato != estilo.formato:
        estilo = estilo.model_copy(update={"formato": clip.formato, "resolucao": None})
    out_w, out_h = estilo.tamanho_saida()
    if preview:
        out_w, out_h = out_w // 2 - (out_w // 2) % 2, out_h // 2 - (out_h // 2) % 2

    pasta = projeto.clips_dir / clip.id
    pasta.mkdir(parents=True, exist_ok=True)

    def prog(frac: float, msg: str, base: float, peso: float) -> None:
        if progresso:
            progresso(base + peso * frac, msg)

    if estilo.direcao.modo == "desenho" and clip.cartela:  # no desenho, a etiqueta do tema faz o papel da cartela
        clip = clip.model_copy(update={"cartela": False})
    # 1) reenquadramento
    layout = _escolher_layout(estilo, info.largura, info.altura, out_w, out_h)
    cmd_path = None
    x0 = 0
    dois = None
    det_nome = "nenhum"
    aviso_layout: str | None = None
    cw, ch_crop = reframe.tamanho_crop(info.largura, info.altura, out_w, out_h)
    amostras: list = []
    traj = None
    cam_movel = None
    caixas_moveis = None
    if layout in ("seguir-rosto", "dividido") or (enquadrar_rosto and estilo.direcao.ativa and layout == "centro"):
        prog(0, "procurando rostos", 0, 0.3)
        amostras = reframe.amostrar_rostos(video, tl, cancelar=cancelar)
        det_nome = reframe.detector().nome
        sinais = projeto.sinais() or {}
        cenas = [c for c in (tl.para_clip(t) for t in sinais.get("cenas", [])) if c is not None]
        if layout == "dividido":
            meia = out_h // 2 - (out_h // 2) % 2
            dois = reframe.enquadramento_dividido(amostras, info.largura, info.altura, out_w, meia, tl.duracao,
                                                  estilo.dividido.em_cima, estilo.dividido.tamanho_rosto, cenas)
            if dois is None and det_nome != "nenhum":
                # o detector funciona, mas nunca viu as duas pessoas na mesma imagem: segue quem estiver na tela
                layout = "seguir-rosto"
                aviso_layout = "Não achei duas pessoas na mesma imagem neste corte: o vídeo segue o rosto de quem fala."
            elif dois is None:
                aviso_layout = "Sem detector de rosto: a tela dividida virou o vídeo inteiro com fundo desfocado."
        fps_cam = _fps_saida(info.fps)
        comandos = ""
        y_cam = (info.altura - ch_crop) // 2
        y_cam -= y_cam % 2
        if layout == "seguir-rosto" or (dois is not None and dois.trechos):
            traj = reframe.trajetoria(amostras, cenas, largura_crop=cw / max(1, info.largura))
            cantos = reframe.cantos_camera(traj, info.largura, cw)
            cam_movel = reframe.movel(cantos, [y_cam], cw, ch_crop, info.largura, info.altura, out_w, out_h)
            comandos += cam_movel.comandos([(t, (x, y_cam), p) for (t, _, p), x in zip(traj, cantos)], "cam", fps_cam)
            x0 = reframe.x_inicial(traj, info.largura, cw)
        if layout == "dividido" and dois is not None and dois.trilhas:
            meia = out_h // 2 - (out_h // 2) % 2
            moveis_l = []
            for trilha, c, nome, alt in zip(dois.trilhas, dois.caixas, ("cima", "baixo"), (meia, out_h - meia)):
                m = reframe.movel([x for _, x, _, _ in trilha], [y for _, _, y, _ in trilha], c.w, c.h,
                                  info.largura, info.altura, out_w, alt)
                comandos += m.comandos([(t, (x, y), p) for t, x, y, p in trilha], nome, fps_cam)
                moveis_l.append(m)
            caixas_moveis = (moveis_l[0], moveis_l[1])
        if comandos.strip():
            cmd_path = pasta / ("camera.preview.cmd" if preview else "camera.cmd")
            cmd_path.write_text(comandos, encoding="utf-8")
    if layout == "centro":
        x0 = (info.largura - cw) // 2
        rostos_x = [max(rs, key=lambda r: r.area).cx for _, rs in amostras if rs]
        if estilo.direcao.ativa and len(rostos_x) >= 3:  # direção de arte: o crop parado vai para onde o locutor está
            x0 = int(max(0, min(info.largura - cw, float(np.median(rostos_x)) * info.largura - cw / 2)))
        x0 -= x0 % 2
    # direção de arte: onde o rosto do locutor fica no vídeo enquadrado (para centralizar e dar o tamanho em cada layout)
    rosto = (reframe.rosto_no_quadro(amostras, traj, info.largura, info.altura, cw, ch_crop, x0)
             if enquadrar_rosto and estilo.direcao.ativa and layout in ("seguir-rosto", "centro") and amostras else None)
    if rosto is not None:
        topo = reframe.topo_dos_rostos(amostras, traj, info.largura, info.altura, cw, ch_crop, x0)
        rosto = (*rosto, topo) if topo is not None else rosto

    # 2) legenda e cartela: camada HyperFrames (HTML/CSS) ou legenda ASS
    ass_path = None
    overlay = None
    motor_usado, aviso = "ffmpeg", None
    trans = projeto.transcricao() or {}
    from .transcribe import palavras as _palavras

    pals = _palavras(trans) if trans else []
    if estilo.legenda.destacar_chave and pals:  # sem IA: as palavras do assunto saem destacadas
        destaques_ia = list(destaques_ia or []) + subtitles.palavras_chave(subtitles.palavras_do_clip(pals, tl))
    base_hf =0.3 if layout in ("seguir-rosto", "dividido") else 0.0
    if estilo.motor == "hyperframes":
        if hyperframes.comando() is None:
            aviso = "HyperFrames não instalado: usei a legenda ASS no lugar da camada animada."
        else:
            try:
                prog(0, "montando a camada HyperFrames", base_hf, 0.35)
                pasta_hf = pasta / ("hyperframes-preview" if preview else "hyperframes")
                comp = hyperframes.compor(
                    pals, tl, estilo, out_w, out_h, clip.titulo, clip.cartela, destaques_ia, pasta_estilo,
                    [projeto.canal.path / "assets" / "fontes"], fps=30, css_da=_css_do_canal(da_canal))
                hyperframes.escrever_projeto(pasta_hf, comp)
                overlay = hyperframes.renderizar(pasta_hf, pasta_hf / "camada.webm", 30,
                                                 lambda f, m: prog(f, m, base_hf, 0.35), cancelar)
                motor_usado = "hyperframes"
            except media.Cancelado:
                raise
            except Exception as exc:  # cai para o ASS: o clip sai mesmo assim
                aviso = f"A camada HyperFrames falhou e usei a legenda ASS. {exc}"
                overlay = None
    zona = plataformas.info(clip.plataforma, clip.formato).zona
    if overlay is None and ((estilo.legenda.modo != "nenhuma" and pals) or (clip.cartela and clip.titulo)):
        ass_path = subtitles.gerar_ass(
            pals, tl, estilo.legenda, out_w, out_h, pasta / "legenda.ass",
            titulo=clip.titulo, cartela=estilo.cartela, usar_cartela=clip.cartela, destaques_extra=destaques_ia,
            zona=zona,
        )
    if pals and not preview:
        subtitles.gerar_srt_vtt(pals, tl, pasta)  # legenda oculta para subir junto (frases inteiras)

    # 3) grafo do FFmpeg
    entradas: list[str] = []
    for s, e in tl.trechos:
        entradas += ["-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", str(video)]
    n = len(tl.trechos)
    fps = _fps_saida(info.fps)
    partes = []
    if info.tem_audio:
        pares = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
        partes.append(f"{pares}concat=n={n}:v=1:a=1[vcat][acat]")
    else:
        pares = "".join(f"[{i}:v:0]" for i in range(n))
        partes.append(f"{pares}concat=n={n}:v=1:a=0[vcat]")
    tratamento = ""
    if da_canal is not None and da_canal.da.tratamento.aplicar_nos_clips:
        from .arte.compilar import filtro_tratamento

        tratamento = "," + filtro_tratamento(da_canal) if filtro_tratamento(da_canal) else ""
    partes.append(f"[vcat]fps={fps:g},setpts=PTS-STARTPTS{tratamento}[vin]")
    cadeia_vlay = _cadeia_layout(estilo, layout, info.largura, info.altura, out_w, out_h, cmd_path, x0, dois,
                                 cam_movel, caixas_moveis)
    partes.append(cadeia_vlay)
    atual = "vlay"

    # direção de arte: a camada de cenas e o layout que junta ela com o vídeo matriz (entradas logo depois dos trechos)
    sons_da: list[tuple[str, float, str]] = []
    n0 = n
    if estilo.direcao.ativa:
        so_video = "".join(f"[{i}:v:0]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vcat];[vcat]fps={fps:g},setpts=PTS-STARTPTS{tratamento}[vin];{cadeia_vlay}"
        ent_da, partes_da, sons_da, aviso_da = _preparar_direcao(
            projeto, clip, estilo, tl, pals, out_w, out_h, fps, pasta, preview, video, so_video, entradas[:], prog, cancelar, n,
            edicao_doc, ad, log, rosto)
        entradas += ent_da
        n0 = n + ent_da.count("-i")
        partes += partes_da
        atual = "vda"
        aviso = aviso or aviso_da

    # edição do editor do passo 3 (edicao.json): efeitos sobre o vídeo, por baixo da legenda e do logo.
    # As entradas extras dela (stickers) vêm primeiro, por isso os índices abaixo somam `ne`.
    from . import edicao as _edicao

    doc = edicao_doc if edicao_doc is not None else _edicao.carregar(pasta)
    doc = doc.model_copy(update={"itens": _edicao.validar(doc.itens, tl.duracao)})
    ent_ed, partes_ed, atual = _edicao.filtros_video(doc, atual, out_w, out_h, fps, pasta, n0, projeto.canal.path)
    partes += partes_ed
    ne = ent_ed.count("-i")  # uma entrada por sticker

    logo = None
    if estilo.logo:
        for base in (projeto.canal.path, projeto.ws.root):
            p = base / estilo.logo
            if p.exists():
                logo = p
                break
    extra_inputs: list[str] = list(ent_ed)
    if logo:
        extra_inputs += ["-i", str(logo)]
        li = n0 + ne
        lw = int(out_w * 0.16)
        margem = int(out_w * 0.04)
        pos = {
            "topo-esquerda": f"{margem}:{margem}",
            "topo-direita": f"W-w-{margem}:{margem}",
            "baixo-esquerda": f"{margem}:H-h-{margem}",
            "baixo-direita": f"W-w-{margem}:H-h-{margem}",
        }[estilo.posicao_logo]
        partes.append(f"[{li}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa=0.9[logo];[{atual}][logo]overlay={pos}[vlogo]")
        atual = "vlogo"

    if overlay is not None:
        oi = n0 + ne + (1 if logo else 0)
        extra_inputs += ["-c:v", "libvpx-vp9", "-i", str(overlay)]  # decodificador com alfa
        partes.append(f"[{oi}:v]setpts=PTS-STARTPTS[camada];[{atual}][camada]overlay=0:0:format=auto:eof_action=pass[vhf]")
        atual = "vhf"
    camada_refs = None if preview else _camada_referencias(projeto, clip, estilo, tl, pals, out_w, out_h, pasta, ad, prog, cancelar, log)
    if camada_refs is not None:  # imagens reais do que a fala cita, no visual do estilo (referencias.py)
        ri = n0 + ne + (1 if logo else 0) + (1 if overlay is not None else 0)
        extra_inputs += ["-c:v", "libvpx-vp9", "-i", str(camada_refs)]
        partes.append(f"[{ri}:v]setpts=PTS-STARTPTS[refs];[{atual}][refs]overlay=0:0:format=auto:eof_action=pass[vrefs]")
        atual = "vrefs"
    if ass_path:
        partes.append(
            f"[{atual}]subtitles=filename='{media.escape_filter_path(ass_path)}':"
            f"fontsdir='{media.escape_filter_path(fontes_dir())}'[vsub]"
        )
        atual = "vsub"
    partes.append(f"[{atual}]format=yuv420p[vout]")

    aout = None
    if info.tem_audio:
        musica = None
        if estilo.musica.arquivo:
            for base in (projeto.canal.path, projeto.ws.root):
                p = base / estilo.musica.arquivo
                if p.exists():
                    musica = p
                    break
        cadeia_a = "[acat]asetpts=PTS-STARTPTS"
        if estilo.normalizar_audio and not preview:
            cadeia_a += f",{media.LOUDNORM}"
        if musica:
            mi = n0 + ne + (1 if logo else 0) + (1 if overlay is not None else 0) + (1 if camada_refs is not None else 0)
            extra_inputs += ["-stream_loop", "-1", "-i", str(musica)]
            vol = estilo.musica.volume
            partes.append(f"{cadeia_a},asplit=2[voz][voz_sc]")
            partes.append(f"[{mi}:a]volume={vol},atrim=0:{tl.duracao:.3f}[mus]")
            partes.append("[mus][voz_sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
            partes.append("[voz][duck]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            partes.append(f"{cadeia_a}[aout]")
        aout = "[aout]"
        # efeitos sonoros do estilo (sintetizados localmente ou do canal) e os do editor, somados depois
        # da voz e da música
        bases = [projeto.canal.path, projeto.canal.path / "assets", projeto.ws.root]
        evs_ed, arq_ed = _edicao.sons_da_edicao(doc, bases)
        for chave, t_som, nome in sons_da:  # a entrada de cada cena da direção de arte
            p_som = sons.resolver(nome, bases)
            if p_som is not None:
                arq_ed[chave] = p_som
                evs_ed.append((chave, t_som))
        if estilo.sons or evs_ed:
            arquivos = {ev: p for ev, v in (estilo.sons or {}).items() if ev in sons.EVENTOS and (p := sons.resolver(v, bases))}
            pals_clip = subtitles.palavras_do_clip(pals, tl) if pals else []
            evs = [e for e in sons.eventos(arquivos and estilo.sons, tl.duracao, list(tl.trechos), pals_clip,
                                           subtitles.regex_destaque(estilo.legenda, destaques_ia), bool(clip.cartela and clip.titulo))
                   if e[0] in arquivos] if arquivos else []
            evs += evs_ed
            arquivos.update(arq_ed)
            if evs:
                partes[-1] = partes[-1].rsplit("[aout]", 1)[0] + "[avoz]"
                indice = n0 + ne + (1 if logo else 0) + (1 if overlay is not None else 0) + (1 if camada_refs is not None else 0) + (1 if musica else 0)
                ent, grafo = sons.filtro_mix(evs, arquivos, indice, "[avoz]", estilo.volume_sons)
                extra_inputs += ent
                partes += grafo

    saida = saida_forcada or pasta / ("preview.mp4" if preview else "saida.mp4")
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp = saida.with_name(saida.stem + ".tmp.mp4")
    args = entradas + extra_inputs + ["-filter_complex", ";".join(partes), "-map", "[vout]"]
    if aout:
        args += ["-map", aout, "-c:a", "aac", "-b:a", "192k" if not preview else "96k", "-ar", "48000"]
    args += media.video_encode_args("preview" if preview else "final")
    args += ["-t", f"{tl.duracao:.3f}", str(tmp)]
    base = base_hf + (0.35 if overlay is not None else 0.0)

    try:
        media.run_ffmpeg(args, duracao=tl.duracao, progresso=lambda f, m: prog(f, m, base, 1 - base),
                         cancelar=cancelar, descricao="renderizando")
    except BaseException:
        media.apagar_parcial(tmp)  # cancelado ou falhou: não deixa vídeo pela metade
        raise
    media.substituir(tmp, saida)
    if estilo.abertura.ativa:
        aviso_ab = _aplicar_abertura(projeto, estilo, tl, pals, saida, pasta, info.tem_audio, fps, preview,
                                     destaques_ia, cancelar, log)
        if aviso_ab:
            aviso = f"{aviso} {aviso_ab}" if aviso else aviso_ab
    if da_canal is not None and not preview:
        try:
            from .arte.identidade import carimbar

            carimbar(saida, da_canal, "render", {"estilo": estilo.nome, "clip": clip.id, "formato": clip.formato},
                     ref_arte or "canal")
        except Exception as exc:  # noqa: BLE001 - o carimbo não pode derrubar um render pronto
            if log:
                log(f"não consegui carimbar o clip com a direção de arte: {exc}")
    if aviso_layout:
        aviso = f"{aviso_layout} {aviso}" if aviso else aviso_layout
    return ResultadoRender(saida, ass_path, det_nome, layout, motor_usado, aviso)
