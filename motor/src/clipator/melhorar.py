"""Melhorar com IA: a IA refaz a edição de um clip seguindo o estilo escolhido, em versões (v1, v2…).

Cada rodada manda para a IA, pelo adaptador (texto entra, JSON sai), o estilo do clip inteiro (ficha
de direção de arte, legenda, sons, cenas e o texto do estilo, resumidos para caber no limite), as skills
ativas de estilo e de fluxo do canal, a fala do corte com os tempos, os momentos de mais energia, a zona
segura da plataforma, a edição atual e o pedido do usuário ("mais dinâmico", "menos texto"…). A resposta
é um plano de edição inteiro: o que manter, itens novos (cenas citando a fala, efeitos, stickers e
chamadas, textos, sons), palavras da legenda para destacar e pausas mortas para cortar. Tudo é conferido
contra a transcrição e a duração; o que não passa fica de fora com o motivo.

As versões ficam em clips/<id>/versoes-edicao/vN.json (o edicao.json é sempre a versão em uso). Edição
à mão no editor e mudança pelo MCP também viram versão. "Usar esta versão" troca o edicao.json e os
cortes internos do clip pelos daquela versão; o render final usa a versão em uso.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import direcao, edicao
from .edicao import Edicao, Item
from .models import LayoutArte
from .timeline import Timeline
from .workspace import ProjetoWS

PASTA = "versoes-edicao"
LIMITE_ESTILO = 6000  # caracteres do estilo + skills que vão para a IA
JUNTAR_MANUAL_S = 600  # edições à mão seguidas (o editor salva sozinho) viram uma versão só
CHIPS = ("mais dinâmico", "menos texto", "cenas maiores", "seguir mais a fala", "mais calmo", "mais cenas")


class SemIA(RuntimeError):
    """O recurso usa a IA integrada e não há Claude Code nem Codex disponível."""


MSG_SEM_IA = ("Isso usa a IA integrada: instale e entre no Claude Code ou no Codex (Configurações > IA) "
              "e tente de novo.")


def ia_do_workspace(ws: Any, esperar_login: Any = None) -> Any | None:
    """O adaptador da IA configurada (com a outra CLI de reserva), ou None se nenhuma estiver instalada."""
    from .ai.adapter import adaptador_com_reserva

    conf = ws.config()
    ad = adaptador_com_reserva(conf.ia.ranking, conf.ia.timeout_s, esperar_login=esperar_login)
    return ad if ad.disponivel() else None


# ---- versões ---------------------------------------------------------------------------------------
def _pasta(pasta_clip: Path) -> Path:
    return pasta_clip / PASTA


def _indice(pasta_clip: Path) -> dict[str, Any]:
    p = _pasta(pasta_clip) / "indice.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"atual": None}
    except (OSError, json.JSONDecodeError):
        return {"atual": None}


def _salvar_indice(pasta_clip: Path, dados: dict[str, Any]) -> None:
    p = _pasta(pasta_clip) / "indice.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def numeros(pasta_clip: Path) -> list[int]:
    d = _pasta(pasta_clip)
    return sorted(int(m.group(1)) for p in d.glob("v*.json") if (m := re.fullmatch(r"v(\d+)\.json", p.name))) if d.is_dir() else []


def ler(pasta_clip: Path, n: int) -> dict[str, Any]:
    p = _pasta(pasta_clip) / f"v{int(n)}.json"
    if not p.exists():
        raise KeyError(f"Versão {n} não existe")
    return json.loads(p.read_text(encoding="utf-8"))


def _rotulo(i: Item | dict) -> str:
    d = i if isinstance(i, dict) else i.model_dump()
    p = d.get("params") or {}
    if d["tipo"] == "cena":
        return f"cena {direcao.CENAS.get(p.get('cena', ''), {}).get('nome', p.get('cena', ''))}"
    if d["tipo"] == "sticker":
        return "chamada " + str(p.get("ref", ""))[4:] if str(p.get("ref", "")).startswith("cta:") else "sticker"
    return {"texto": "texto", "som": "som", "emoji": "emoji"}.get(d["tipo"], d["tipo"])


def diferencas(antes: list[dict], depois: list[dict], cortes_antes: list | None = None, cortes_depois: list | None = None) -> list[str]:
    """O que mudou entre duas edições, em frases curtas ("+2 cenas: Número, Lista", "−1 zoom"…)."""
    ids_a = {i["id"]: i for i in antes}
    ids_b = {i["id"]: i for i in depois}
    novos = [i for k, i in ids_b.items() if k not in ids_a]
    tirados = [i for k, i in ids_a.items() if k not in ids_b]
    mudados = [k for k in ids_a.keys() & ids_b.keys() if ids_a[k] != ids_b[k]]
    out = []

    def contar(itens: list[dict]) -> str:
        c: dict[str, int] = {}
        for i in itens:
            c[_rotulo(i)] = c.get(_rotulo(i), 0) + 1
        return ", ".join(f"{n}× {r}" if n > 1 else r for r, n in sorted(c.items(), key=lambda x: -x[1]))

    if novos:
        out.append(f"+{len(novos)}: {contar(novos)}")
    if tirados:
        out.append(f"−{len(tirados)}: {contar(tirados)}")
    if mudados:
        out.append(f"{len(mudados)} item(ns) ajustado(s) (tempo ou texto)")
    if cortes_antes is not None and cortes_depois is not None and [list(x) for x in cortes_antes] != [list(x) for x in cortes_depois]:
        n = len(cortes_depois) - len(cortes_antes)
        out.append(f"{abs(n)} pausa(s) {'cortada(s)' if n >= 0 else 'devolvida(s)'}" if n else "cortes internos mudaram")
    return out or ["sem mudanças"]


def criar(pasta_clip: Path, doc: Edicao, origem: str, cortes: list[tuple[float, float]], feedback: str = "",
          resumo: list[str] | None = None, modelo: str = "", descartados: list[dict] | None = None) -> int:
    """Grava a edição como a próxima versão e marca como a em uso. Devolve o número."""
    ns = numeros(pasta_clip)
    anterior = ler(pasta_clip, ns[-1]) if ns else None
    agora = datetime.now()
    # edições à mão seguidas viram uma versão só (o editor grava a cada mudança)
    if (origem == "manual" and anterior and anterior.get("origem") == "manual" and _indice(pasta_clip).get("atual") == ns[-1]
            and (agora - datetime.fromisoformat(anterior["criado"])).total_seconds() < JUNTAR_MANUAL_S):
        n = ns[-1]
        base = ler(pasta_clip, n - 1) if n - 1 in ns else None
    else:
        n = (ns[-1] + 1) if ns else 1
        base = anterior
    itens = [i.model_dump(mode="json") for i in doc.itens]
    if resumo is None:
        resumo = diferencas(base["itens"] if base else [], itens, base.get("cortes") if base else [], [list(c) for c in cortes]) \
            if base else [f"versão inicial ({len(itens)} itens)"]
    dados = {"n": n, "criado": agora.isoformat(timespec="seconds"), "origem": origem, "modelo": modelo, "feedback": feedback,
             "resumo": resumo, "descartados": descartados or [], "itens": itens, "destaques": list(doc.destaques),
             "cenas_planejadas": doc.cenas_planejadas, "cortes": [list(c) for c in cortes],
             "layout_arte": doc.layout_arte.model_dump(mode="json") if doc.layout_arte else None}
    d = _pasta(pasta_clip)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"v{n}.json.tmp"
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / f"v{n}.json")
    (d / f"v{n}-previa.mp4").unlink(missing_ok=True)  # prévia antiga desta versão (edição à mão juntada)
    _salvar_indice(pasta_clip, {"atual": n})
    return n


def garantir_inicial(projeto: ProjetoWS, clip_id: str) -> None:
    """Antes da primeira versão nova, a edição que já existia vira a v1 (dá para voltar a ela)."""
    clip, pasta = projeto.clip(clip_id)
    if not numeros(pasta):
        criar(pasta, edicao.carregar(pasta), "inicial", list(clip.cortes_internos), resumo=["edição antes das versões"])


def registrar(projeto: ProjetoWS, clip_id: str, origem: str, feedback: str = "", resumo: list[str] | None = None,
              modelo: str = "", descartados: list[dict] | None = None) -> int:
    """A edição atual (edicao.json + cortes do clip) vira uma versão."""
    clip, pasta = projeto.clip(clip_id)
    return criar(pasta, edicao.carregar(pasta), origem, list(clip.cortes_internos), feedback, resumo, modelo, descartados)


def listar(projeto: ProjetoWS, clip_id: str) -> dict[str, Any]:
    _, pasta = projeto.clip(clip_id)
    atual = _indice(pasta).get("atual")
    out = []
    for n in reversed(numeros(pasta)):
        v = ler(pasta, n)
        previa = _pasta(pasta) / f"v{n}-previa.mp4"
        out.append({k: v.get(k) for k in ("n", "criado", "origem", "modelo", "feedback", "resumo", "descartados")}
                   | {"itens": len(v.get("itens", [])), "cortes": len(v.get("cortes", [])), "atual": n == atual,
                      "previa": previa.relative_to(projeto.ws.root).as_posix() if previa.exists() else None})
    return {"versoes": out, "atual": atual, "chips": list(CHIPS)}


def usar(projeto: ProjetoWS, clip_id: str, n: int) -> dict[str, Any]:
    """Põe a versão n em uso: o edicao.json e os cortes internos do clip voltam a ser os dela."""
    clip, pasta = projeto.clip(clip_id)
    v = ler(pasta, n)
    clip.cortes_internos = [tuple(c) for c in v.get("cortes", [])]  # type: ignore[misc]
    projeto.salvar_clip(clip)
    atual = edicao.carregar(pasta)
    doc = atual.model_copy(update={"itens": [Item.model_validate(i) for i in v["itens"]], "destaques": v.get("destaques", []),
                                   "cenas_planejadas": bool(v.get("cenas_planejadas", True)),
                                   "layout_arte": LayoutArte.model_validate(v["layout_arte"]) if v.get("layout_arte") else None})
    edicao.salvar(pasta, doc, Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos).duracao)
    _salvar_indice(pasta, {"atual": int(n)})
    return {"atual": int(n)}


def comparar(projeto: ProjetoWS, clip_id: str, a: int, b: int) -> dict[str, Any]:
    _, pasta = projeto.clip(clip_id)
    va, vb = ler(pasta, a), ler(pasta, b)

    def lado(v: dict) -> dict[str, Any]:
        previa = _pasta(pasta) / f"v{v['n']}-previa.mp4"
        return {"n": v["n"], "resumo": v.get("resumo"), "feedback": v.get("feedback"), "origem": v.get("origem"),
                "itens": [{"tipo": i["tipo"], "inicio": i["inicio"], "fim": i["fim"], "rotulo": _rotulo(i),
                           "texto": direcao._limpo(str((i.get("params") or {}).get("texto") or (i.get("params") or {}).get("valor") or ""))}
                          for i in v["itens"]],
                "previa": previa.relative_to(projeto.ws.root).as_posix() if previa.exists() else None}

    return {"a": lado(va), "b": lado(vb), "diferencas": diferencas(va["itens"], vb["itens"], va.get("cortes"), vb.get("cortes"))}


def caminho_previa(pasta_clip: Path, n: int) -> Path:
    return _pasta(pasta_clip) / f"v{int(n)}-previa.mp4"


# ---- o pedido para a IA ----------------------------------------------------------------------------
def resumo_do_estilo(est: Any, corpo: str, f: direcao.Ficha | None, skills_txt: str, limite: int = LIMITE_ESTILO) -> str:
    """O estilo inteiro em texto (cabeçalho compacto + corpo + skills), cortado para caber em `limite`."""
    leg = est.legenda
    cab = {
        "nome": est.nome, "descricao": est.descricao, "formato": est.formato,
        "legenda": {"modo": leg.modo, "fonte": leg.fonte, "cor": leg.cor, "destaque": leg.destaque, "posicao": leg.posicao,
                    "animacao": leg.animacao, "caixa_alta": leg.caixa_alta},
        "cartela": est.cartela.sugerida, "zoom": {"enfase": est.zoom.enfase, "intensidade": est.zoom.intensidade},
        "jump_cuts": est.jump_cuts, "sons": est.sons,
    }
    if est.direcao.ativa and f is not None:
        cab["direcao_de_arte"] = {"layout": est.direcao.layout, "densidade_s": est.direcao.densidade,
                                  "ficha": {"nome": f.nome, "cores": {"fundo": f.fundo, "texto": f.texto, "primaria": f.primaria,
                                                                       "destaque": f.destaque},
                                            "fontes": [f.fonte_titulo, f.fonte_corpo], "entrada": f.entrada, "sons": f.sons}}
    base = "Estilo (YAML resumido): " + json.dumps(cab, ensure_ascii=False)
    sobra = max(0, limite - len(base) - 40)
    corpo = " ".join(corpo.split())
    txt_corpo = corpo[: max(0, min(len(corpo), sobra // 2 if skills_txt else sobra))]
    sobra -= len(txt_corpo)
    txt_skills = skills_txt[: max(0, sobra)]
    return base + ("\nNotas do estilo: " + txt_corpo if txt_corpo else "") + ("\n" + txt_skills if txt_skills else "")


def _item_compacto(i: Item) -> dict[str, Any]:
    p = {k: v for k, v in i.params.items() if k in ("cena", "texto", "valor", "rotulo", "itens", "ref", "emoji", "nome", "escala", "ancora")}
    return {"id": i.id, "tipo": i.tipo, "inicio": round(i.inicio, 2), "fim": round(i.fim, 2), **p}


def picos_de_energia(sinais: dict | None, tl: Timeline, n: int = 6) -> list[float]:
    """Os momentos mais fortes do áudio, em segundos do clip."""
    if not sinais or not sinais.get("energia_db"):
        return []
    passo = float(sinais.get("passo") or 0.5)
    pts = []
    for k, e in enumerate(sinais["energia_db"]):
        t = tl.para_clip(k * passo)
        if t is not None:
            pts.append((e, t))
    pts.sort(reverse=True)
    out: list[float] = []
    for _, t in pts:
        if all(abs(t - x) > 2.0 for x in out):
            out.append(round(t, 1))
        if len(out) >= n:
            break
    return sorted(out)


SCHEMA_MELHORAR: dict[str, Any] = {
    "type": "object",
    "properties": {
        "resumo": {"type": "array", "items": {"type": "string"}},
        "manter": {"type": "array", "items": {"type": "string"}},
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": sorted(edicao.TIPOS)},
                    "inicio": {"type": "number"}, "fim": {"type": "number"},
                    "ancora": {"type": "string"},
                    "cena": {"type": "string"}, "texto": {"type": "string"}, "itens": {"type": "array", "items": {"type": "string"}},
                    "valor": {"type": "string"}, "rotulo": {"type": "string"}, "autor": {"type": "string"},
                    "a": {"type": "string"}, "b": {"type": "string"},
                    "sticker": {"type": "string"}, "emoji": {"type": "string"}, "som": {"type": "string"},
                    "escala": {"type": "number"}, "posicao": {"type": "string"}, "motivo": {"type": "string"},
                },
                "required": ["tipo", "inicio", "fim", "ancora", "cena", "texto", "itens", "valor", "rotulo", "autor", "a", "b",
                             "sticker", "emoji", "som", "escala", "posicao", "motivo"],
                "additionalProperties": False,
            },
        },
        "destaques": {"type": "array", "items": {"type": "string"}},
        "pausas": {"type": "array", "items": {"type": "object", "properties": {"inicio": {"type": "number"}, "fim": {"type": "number"}},
                                               "required": ["inicio", "fim"], "additionalProperties": False}},
    },
    "required": ["resumo", "manter", "itens", "destaques", "pausas"],
    "additionalProperties": False,
}


def prompt_melhorar(estilo_txt: str, pals: list[dict], dur: float, doc: Edicao, feedback: str, zona: Any, picos: list[float],
                    emendas: list[float], stickers_disp: list[str], canal_md: str = "") -> str:
    from . import sons

    fala = " ".join(f"[{w['inicio']:.2f}]{w['texto'].strip()}" for w in pals)[:9000]
    atual = json.dumps([_item_compacto(i) for i in doc.itens], ensure_ascii=False)[:5000]
    return (
        "Você é editor e diretor de arte de vídeos curtos. Refaça a edição do clip abaixo para ficar MELHOR, seguindo o estilo "
        "à risca e o que a pessoa está dizendo.\n"
        f"Pedido do usuário: {feedback.strip() or '(nenhum: melhore o ritmo e a clareza)'}\n"
        f"Clip de {dur:.2f} s. Emendas de cortes em: {', '.join(f'{x:.2f}' for x in emendas) or 'nenhuma'}. "
        f"Momentos de mais energia: {', '.join(f'{x:.1f}' for x in picos) or 'n/d'}. "
        f"Zona segura (o app cobre): {zona.topo:.0%} em cima, {zona.base:.0%} embaixo, {zona.direita:.0%} à direita.\n"
        f"{estilo_txt}\n"
        + (f"Canal: {' '.join(canal_md.split())[:600]}\n" if canal_md else "")
        + "Tipos de item: cena (direção de arte; 'cena' = titulo, numero, citacao, lista, comparacao, linha_do_tempo, local, nome, "
        "palavra ou alerta, e 'ancora' = 4 a 8 palavras COPIADAS da fala que a cena ilustra), zoom, zoom-lento, tremor, flash, pb, "
        "sepia, contraste, saturacao, desfoque, vinheta, transicao, texto (curto), emoji, sticker ('sticker' = uma destas palavras "
        f"ou cta:inscreva-se, cta:curtir, cta:siga, cta:comente: {', '.join(stickers_disp[:60]) or 'nenhuma'}), "
        f"som ('som' = {', '.join(sons.NOMES)}).\n"
        "Responda o plano inteiro: em 'manter' os ids dos itens atuais que ficam como estão; em 'itens' só os novos ou trocados "
        "(tempos em segundos do clip; campos que não se aplicam vazios, escala 0). Só use números, nomes e citações que foram "
        "ditos. 'destaques' = palavras da fala para a legenda destacar. 'pausas' = silêncios mortos para cortar (sem fala dentro, "
        "0,5 a 3 s). 'resumo' = 2 a 5 frases curtas do que mudou.\n"
        f"Edição atual: {atual}\n"
        f"Fala com tempos: {fala}"
    )


def validar_resposta(resp: Any, pals: list[dict], dur: float, doc: Edicao, indice_stickers: dict[str, str]) -> tuple[list[Item], list[str], list[tuple[float, float]], list[str], list[dict]]:
    """(itens, destaques, pausas, resumo, descartados com o motivo) — tudo conferido contra a fala e a duração."""
    from . import cta, sons

    if not isinstance(resp, dict):
        return list(doc.itens), [], [], [], [{"item": "resposta", "motivo": "a IA não devolveu um plano"}]
    descartados: list[dict] = []
    manter = {str(x) for x in resp.get("manter") or []}
    itens = [i for i in doc.itens if i.id in manter]
    indice = {edicao._sem_acento(k): v for k, v in indice_stickers.items()}
    desde = 0
    for e in resp.get("itens") or []:
        if not isinstance(e, dict) or e.get("tipo") not in edicao.TIPOS:
            descartados.append({"item": str(e)[:60], "motivo": "tipo desconhecido"})
            continue
        tipo = e["tipo"]
        nome = f"{tipo} {str(e.get('texto') or e.get('cena') or '')[:30]}".strip()
        try:
            ini, fim = float(e.get("inicio")), float(e.get("fim"))
        except (TypeError, ValueError):
            descartados.append({"item": nome, "motivo": "tempo inválido"})
            continue
        ancora = str(e.get("ancora") or "").strip()
        if tipo == "cena":
            cenas = direcao.de_resposta_ia({"cenas": [{**e, "duracao": max(1.5, fim - ini)}]}, pals, dur)
            if not cenas:
                descartados.append({"item": nome, "motivo": "a cena não bate com a fala (trecho, número ou citação não foi dito)"})
                continue
            c = cenas[0]
            itens.append(Item(tipo="cena", inicio=c.inicio, fim=c.fim, params=c.params, origem="ia", motivo=str(e.get("motivo") or "")[:200]))
            continue
        if ancora:
            achou = direcao.ancorar(ancora, pals, desde) or direcao.ancorar(ancora, pals, 0)
            if achou is None:
                descartados.append({"item": nome, "motivo": "o trecho citado não está na fala"})
                continue
            desde = achou[0]
            d = max(0.3, fim - ini)
            ini = pals[achou[0]]["inicio"]
            fim = ini + d
        if not (0 <= ini < dur) or fim <= ini:
            descartados.append({"item": nome, "motivo": "fora da duração do clip"})
            continue
        params: dict[str, Any] = {}
        if tipo == "texto":
            params["texto"] = str(e.get("texto") or "").strip()[:60]
            if not params["texto"]:
                descartados.append({"item": nome, "motivo": "texto vazio"})
                continue
            if any(ch.isdigit() for ch in params["texto"]) and not direcao._na_fala(params["texto"], pals, 0.3):
                descartados.append({"item": nome, "motivo": "número que não foi dito"})
                continue
            if e.get("posicao") in edicao.POSICOES:
                params["posicao"] = e["posicao"]
        elif tipo == "emoji":
            params["emoji"] = str(e.get("emoji") or "").strip()[:8]
            if not params["emoji"]:
                descartados.append({"item": nome, "motivo": "emoji vazio"})
                continue
        elif tipo == "sticker":
            s = str(e.get("sticker") or "").strip()
            if s.startswith("cta:") and s[4:] in cta.MODELOS:
                params["ref"] = s
                fim = max(fim, ini + cta.MODELOS[s[4:]].duracao)
                params.update({"posicao": "baixo", "tamanho": 0.55, "entrada": "nenhuma", "repetir": False})
            elif edicao._sem_acento(s) in indice:
                params["ref"] = indice[edicao._sem_acento(s)]
            else:
                descartados.append({"item": nome, "motivo": "sticker que não existe na biblioteca"})
                continue
        elif tipo == "som":
            if e.get("som") not in sons.NOMES:
                descartados.append({"item": nome, "motivo": "efeito sonoro desconhecido"})
                continue
            params["nome"] = e["som"]
        elif tipo in ("zoom", "zoom-lento") and e.get("escala"):
            params["escala"] = e["escala"]
        itens.append(Item(tipo=tipo, inicio=ini, fim=min(dur, fim), params=params, origem="ia", motivo=str(e.get("motivo") or "")[:200]))
    falados = {direcao._norm(w["texto"]) for w in pals}
    destaques = [str(x).strip()[:30] for x in resp.get("destaques") or [] if direcao._norm(str(x)) in falados][:12]
    pausas: list[tuple[float, float]] = []
    for p in resp.get("pausas") or []:
        try:
            a, b = float(p["inicio"]), float(p["fim"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 < a < b < dur and 0.5 <= b - a <= 3.0):
            descartados.append({"item": f"pausa {a:.1f}–{b:.1f}", "motivo": "tamanho ou lugar inválido"})
            continue
        if any(w["inicio"] < b - 0.05 and w["fim"] > a + 0.05 for w in pals):
            descartados.append({"item": f"pausa {a:.1f}–{b:.1f}", "motivo": "tem fala dentro"})
            continue
        if any(not (b <= x or a >= y) for x, y in pausas):
            continue
        pausas.append((a, b))
    resumo = [" ".join(str(x).split())[:140] for x in resp.get("resumo") or [] if str(x).strip()][:6]
    return edicao.validar(itens, dur), destaques, sorted(pausas), resumo, descartados


def aplicar_pausas(itens: list[Item], pausas: list[tuple[float, float]], tl: Timeline) -> tuple[list[Item], list[tuple[float, float]]]:
    """Corta as pausas (segundos do clip): devolve os itens com os tempos puxados e os cortes no tempo do original."""
    if not pausas:
        return itens, []
    cortes = [(round(tl.para_original(a), 3), round(tl.para_original(b), 3)) for a, b in pausas]

    def novo_t(t: float) -> float:
        tira = 0.0
        for a, b in pausas:
            if t >= b:
                tira += b - a
            elif t > a:
                tira += t - a
        return t - tira

    out = []
    for i in itens:
        ini, fim = novo_t(i.inicio), novo_t(i.fim)
        if fim - ini >= 0.1:
            out.append(i.model_copy(update={"inicio": round(ini, 3), "fim": round(fim, 3)}))
    return out, cortes


def melhorar(projeto: ProjetoWS, clip_id: str, feedback: str = "", ad: Any = None, cancelar: threading.Event | None = None,
             esperar_login: Any = None, relato: Any = None) -> dict[str, Any]:
    """Uma rodada: pede o plano à IA, valida, grava a versão nova e põe em uso. Sem IA: SemIA."""
    from . import plataformas, skills
    from .ai.adapter import CacheIA, chamar

    ad = ad or ia_do_workspace(projeto.ws, esperar_login)
    if ad is None:
        raise SemIA(MSG_SEM_IA)
    clip, pasta = projeto.clip(clip_id)
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    pals = edicao.palavras_do_clip(projeto, tl)
    doc = edicao.carregar(pasta)
    doc = doc.model_copy(update={"itens": edicao.validar(doc.itens, tl.duracao)})
    est, corpo, _ = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)
    try:
        canal_info, canal_md = projeto.canal.info()
        canal_da = canal_info.direcao_de_arte or {}
    except Exception:  # noqa: BLE001
        canal_md, canal_da = "", {}
    f = direcao.ficha(est.direcao.ficha, {**est.direcao.cores, **est.direcao.fontes, **canal_da}) if est.direcao.ativa else None
    skills_txt = "\n\n".join(t for t in (skills.texto_para_ia(projeto.ws, k, projeto.canal.slug, projeto.id)
                                         for k in ("estilo", "cenas", "fluxo")) if t)
    emendas, acc = [], 0.0
    for s, e in tl.trechos[:-1]:
        acc += e - s
        emendas.append(round(acc, 2))
    indice = edicao._indice_stickers()
    prompt = prompt_melhorar(resumo_do_estilo(est, corpo, f, skills_txt), pals, tl.duracao, doc, feedback,
                             plataformas.info(clip.plataforma, clip.formato).zona, picos_de_energia(projeto.sinais(), tl),
                             emendas, sorted(indice), canal_md)
    garantir_inicial(projeto, clip_id)
    from contextlib import nullcontext

    if relato is not None:
        relato.passo(f"pedido pronto: estilo {est.nome}, {len(pals)} palavras, {len(doc.itens)} item(ns) na edição atual"
                     + (f", pedido “{feedback.strip()[:80]}”" if feedback.strip() else ""))
    with (relato.ia(getattr(ad, "nome", "IA"), "refazendo a edição") if relato is not None else nullcontext()) as ev:
        resp = chamar(ad, prompt, SCHEMA_MELHORAR, CacheIA(projeto.analise_dir / "cache_ia"), cancelar, ev)
    itens, destaques, pausas, resumo, descartados = validar_resposta(resp, pals, tl.duracao, doc, indice)
    if est.direcao.modo == "desenho":  # o desenho animado é o estilo: fica; ele muda pela direção de arte do clip
        fora = [i for i in itens if i.tipo == "cena" and i.params.get("cena") != "desenho"]
        descartados += [{"item": f"cena {i.params.get('cena')}", "motivo": "este estilo usa o desenho animado (ajuste na direção de arte)"}
                        for i in fora]
        ids = {i.id for i in itens}
        itens = [i for i in itens if i not in fora] + [i for i in doc.itens if i.params.get("cena") == "desenho" and i.id not in ids]
    if relato is not None:
        novos = len((resp or {}).get("itens") or []) if isinstance(resp, dict) else 0
        relato.passo(f"conferindo com a fala: {novos - len(descartados)} de {novos} item(ns) novos aceitos, "
                     f"{len(pausas)} pausa(s) para cortar, {len(destaques)} palavra(s) em destaque")
        for d in descartados[:6]:
            relato.passo(f"descartado: {d['item']} — {d['motivo']}")
    itens, cortes_novos = aplicar_pausas(itens, pausas, tl)
    if cortes_novos:
        clip.cortes_internos = sorted([*clip.cortes_internos, *cortes_novos])  # type: ignore[list-item]
        projeto.salvar_clip(clip)
        tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    novo = doc.model_copy(update={"itens": itens, "destaques": destaques, "cenas_planejadas": True})
    edicao.salvar(pasta, novo, tl.duracao)
    antes = ler(pasta, numeros(pasta)[-1])
    mudou = diferencas(antes["itens"], [i.model_dump(mode="json") for i in edicao.carregar(pasta).itens], antes.get("cortes"),
                       [list(c) for c in clip.cortes_internos])
    n = registrar(projeto, clip_id, "ia", feedback, (resumo or []) + [f"({m})" for m in mudou if m != "sem mudanças"] or mudou,
                  getattr(ad, "nome", ""), descartados)
    return {"versao": n, "resumo": ler(pasta, n)["resumo"], "descartados": descartados}


def pedido_para_conversa(projeto: ProjetoWS, clip_id: str) -> str:
    """Trecho do pedido.md da conversa: a ficha do estilo e como mudar a edição pelo MCP (cria versão)."""
    from . import skills

    clip, _ = projeto.clip(clip_id)
    try:
        est, corpo, _ = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)
    except Exception:  # noqa: BLE001
        return ""
    f = direcao.ficha(est.direcao.ficha, {**est.direcao.cores, **est.direcao.fontes}) if est.direcao.ativa else None
    skills_txt = skills.texto_para_ia(projeto.ws, "estilo", projeto.canal.slug, projeto.id)
    return ("## Estilo do clip (siga ao mudar a edição)\n" + resumo_do_estilo(est, corpo, f, skills_txt, 4000) + "\n\n"
            "## Mudar a edição\n"
            f"Use as ferramentas MCP do Clipator: `ler_edicao` (canal {projeto.canal.slug}, projeto {projeto.id}, clip {clip_id}) para ver "
            "a edição atual e `aplicar_edicao` para mudar (cada mudança vira uma versão nova, que o usuário pode comparar e desfazer "
            "no passo 4). Cenas da direção de arte são itens do tipo `cena` com `params.cena`, `params.ancora` (o trecho da fala que "
            "a cena ilustra) e os textos. Use as suas skills de edição, se tiver, mas só com o que foi dito no clip.\n")
