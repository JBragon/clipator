"""Revisão antes de publicar: uma nota de 0 a 100 e a lista do que corrigir, por clip (passo 5).

Sem IA, por regras que o motor sabe medir: gancho (quanto demora a primeira palavra), fechamento (a
última frase termina?), pausas mortas, duração para a plataforma, título, chamada para seguir e números
ditos sem fonte. Com IA, pelo adaptador (texto entra, JSON sai), com as skills ativas do tipo "revisao"
(a régua) e o resultado das regras como ponto de partida; o que a IA devolve é conferido (nota entre 0
e 100, segundos dentro do clip). O resultado fica em clips/<id>/revisao.json.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime
from typing import Any

from . import edicao
from .timeline import Timeline
from .workspace import ProjetoWS, read_json, write_json

ARQUIVO = "revisao.json"
DURACAO_MAX = {"youtube-shorts": 180.0, "instagram-reels": 180.0, "tiktok": 600.0, "youtube": 43200.0}
_NUM = re.compile(r"\d")


def _criterio(nome: str, nota: float, maximo: float, comentario: str) -> dict[str, Any]:
    return {"nome": nome, "nota": round(max(0.0, min(maximo, nota)), 1), "max": maximo, "comentario": comentario}


def por_regras(projeto: ProjetoWS, clip_id: str) -> dict[str, Any]:
    from . import plataformas

    clip, pasta = projeto.clip(clip_id)
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    pals = edicao.palavras_do_clip(projeto, tl)
    plat = plataformas.info(clip.plataforma, clip.formato)
    crit, problemas, alertas = [], [], []
    # gancho: a fala tem de começar logo
    inicio = pals[0]["inicio"] if pals else tl.duracao
    nota = 25 if inicio <= 0.6 else 18 if inicio <= 1.2 else 8
    if inicio > 0.6:
        problemas.append({"segundo": 0.0, "texto": f"A primeira palavra só vem em {inicio:.1f} s: corte o começo.", "gravidade": "media"})
    crit.append(_criterio("Gancho", nota, 25, "A fala começa logo." if inicio <= 0.6 else "Começo lento."))
    # ritmo: pausas mortas
    pausas = [(a["fim"], b["inicio"]) for a, b in zip(pals, pals[1:]) if b["inicio"] - a["fim"] > 1.2]
    for a, b in pausas[:4]:
        problemas.append({"segundo": round(a, 1), "texto": f"Pausa de {b - a:.1f} s sem fala.", "gravidade": "baixa"})
    crit.append(_criterio("Ritmo", 20 - 5 * len(pausas), 20, f"{len(pausas)} pausa(s) longa(s)." if pausas else "Sem pausas mortas."))
    # fechamento: a última frase termina
    fecha = bool(pals) and pals[-1]["texto"].rstrip().endswith((".", "!", "?"))
    if not fecha and pals:
        problemas.append({"segundo": round(pals[-1]["inicio"], 1), "texto": "O clip termina no meio da frase.", "gravidade": "alta"})
    crit.append(_criterio("Fechamento", 10 if fecha else 2, 10, "Termina numa frase completa." if fecha else "Frase cortada no fim."))
    # clareza e legenda: sem como medir sem IA, a conta é neutra
    crit.append(_criterio("Clareza", 11, 15, "Sem IA não dá para julgar: confira se dá para entender sem o resto do vídeo."))
    crit.append(_criterio("Legenda e texto", 12 if (pasta / "legenda.srt").exists() or (pasta / "legenda.ass").exists() else 6, 15,
                          "Legenda gerada." if (pasta / "legenda.srt").exists() else "Ainda sem legenda (renderize)."))
    # chamada
    doc = edicao.carregar(pasta)
    tem_cta = any(i.tipo == "sticker" and str(i.params.get("ref", "")).startswith("cta:") for i in doc.itens)
    texto = " ".join(w["texto"] for w in pals).lower()
    tem_cta = tem_cta or any(x in texto for x in ("inscreve", "segue", "siga", "comenta", "curte"))
    crit.append(_criterio("Chamada", 5 if tem_cta else 1, 5, "Tem chamada." if tem_cta else "Sem chamada para seguir ou comentar."))
    # plataforma
    limite = DURACAO_MAX.get(plat.id, 180.0)
    ok_dur = tl.duracao <= limite
    ok_tit = bool(clip.titulo.strip()) and (plat.limites.titulo is None or len(clip.titulo) <= plat.limites.titulo)
    if not ok_dur:
        problemas.append({"segundo": None, "texto": f"{tl.duracao:.0f} s passa do limite do {plat.nome} ({limite:.0f} s).", "gravidade": "alta"})
    if not ok_tit:
        problemas.append({"segundo": None, "texto": "Falta o título (ou passa do limite da plataforma).", "gravidade": "media"})
    crit.append(_criterio("Plataforma", 10 - (6 if not ok_dur else 0) - (4 if not ok_tit else 0), 10,
                          f"{plat.nome}: {tl.duracao:.0f} s, título {'ok' if ok_tit else 'faltando'}."))
    # números ditos: precisam de fonte (checagem)
    for w in pals:
        if _NUM.search(w["texto"]):
            alertas.append({"segundo": round(w["inicio"], 1), "trecho": w["texto"].strip(), "motivo": "número dito: confira a fonte"})
    nota = sum(c["nota"] for c in crit)
    return {"nota": round(nota), "criterios": crit, "problemas": problemas, "alertas": alertas[:8], "fonte": "regras"}


SCHEMA_REVISAO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nota": {"type": "number"},
        "criterios": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "nota": {"type": "number"}, "max": {"type": "number"}, "comentario": {"type": "string"}},
            "required": ["nome", "nota", "max", "comentario"], "additionalProperties": False}},
        "problemas": {"type": "array", "items": {"type": "object", "properties": {
            "segundo": {"type": "number"}, "texto": {"type": "string"}, "gravidade": {"type": "string", "enum": ["alta", "media", "baixa"]}},
            "required": ["segundo", "texto", "gravidade"], "additionalProperties": False}},
        "alertas": {"type": "array", "items": {"type": "object", "properties": {
            "segundo": {"type": "number"}, "trecho": {"type": "string"}, "motivo": {"type": "string"}},
            "required": ["segundo", "trecho", "motivo"], "additionalProperties": False}},
    },
    "required": ["nota", "criterios", "problemas", "alertas"],
    "additionalProperties": False,
}


def prompt_revisao(pals: list[dict], dur: float, titulo: str, plataforma: str, regras: dict[str, Any], skills_txt: str) -> str:
    import json

    fala = " ".join(f"[{w['inicio']:.1f}]{w['texto'].strip()}" for w in pals)[:9000]
    return (
        "Revise este clip curto antes de ele ser publicado. Dê uma nota de 0 a 100, a nota de cada critério e a lista do que "
        "corrigir (com o segundo do clip), do mais grave para o menos. Em 'alertas', números, citações e acusações que precisam "
        "de fonte. Seja direto e concreto.\n"
        f"Plataforma: {plataforma}. Duração: {dur:.1f} s. Título: “{titulo}”.\n"
        + (f"{skills_txt[:6000]}\n" if skills_txt else "")
        + f"Medições do motor (ponto de partida): {json.dumps(regras, ensure_ascii=False)[:2500]}\n"
        f"Fala com tempos: {fala}"
    )


def validar(resp: Any, dur: float) -> dict[str, Any] | None:
    if not isinstance(resp, dict):
        return None
    try:
        nota = max(0, min(100, round(float(resp.get("nota")))))
    except (TypeError, ValueError):
        return None

    def seg(v: Any) -> float | None:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return round(x, 1) if 0 <= x <= dur else None

    crit = [_criterio(str(c.get("nome") or "")[:40], float(c.get("nota") or 0), float(c.get("max") or 10), str(c.get("comentario") or "")[:200])
            for c in resp.get("criterios") or [] if isinstance(c, dict) and c.get("nome")][:10]
    probs = [{"segundo": seg(p.get("segundo")), "texto": str(p.get("texto") or "")[:240],
              "gravidade": p.get("gravidade") if p.get("gravidade") in ("alta", "media", "baixa") else "media"}
             for p in resp.get("problemas") or [] if isinstance(p, dict) and str(p.get("texto") or "").strip()][:12]
    alertas = [{"segundo": seg(a.get("segundo")), "trecho": str(a.get("trecho") or "")[:120], "motivo": str(a.get("motivo") or "")[:200]}
               for a in resp.get("alertas") or [] if isinstance(a, dict) and str(a.get("trecho") or "").strip()][:10]
    return {"nota": nota, "criterios": crit, "problemas": probs, "alertas": alertas}


def revisar(projeto: ProjetoWS, clip_id: str, ad: Any = None, usar_ia: bool = True, cancelar: threading.Event | None = None) -> dict[str, Any]:
    from . import plataformas, skills

    clip, pasta = projeto.clip(clip_id)
    regras = por_regras(projeto, clip_id)
    out = regras
    if usar_ia:
        if ad is None:
            from .melhorar import ia_do_workspace

            ad = ia_do_workspace(projeto.ws)
        if ad is not None:
            from .ai.adapter import CacheIA, ErroIA, chamar

            tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
            pals = edicao.palavras_do_clip(projeto, tl)
            txt = skills.texto_para_ia(projeto.ws, "revisao", projeto.canal.slug, projeto.id)
            try:
                r = chamar(ad, prompt_revisao(pals, tl.duracao, clip.titulo, plataformas.info(clip.plataforma, clip.formato).nome,
                                              regras, txt), SCHEMA_REVISAO, CacheIA(projeto.analise_dir / "cache_ia"), cancelar)
                v = validar(r, tl.duracao)
                if v is not None:
                    out = {**v, "fonte": getattr(ad, "nome", "ia")}
            except ErroIA as exc:
                out = {**regras, "aviso": f"A IA não respondeu ({exc}); usei as regras."}
    out["feito_em"] = datetime.now().isoformat(timespec="seconds")
    write_json(pasta / ARQUIVO, out)
    return out


def ultima(projeto: ProjetoWS, clip_id: str) -> dict[str, Any] | None:
    _, pasta = projeto.clip(clip_id)
    return read_json(pasta / ARQUIVO)
