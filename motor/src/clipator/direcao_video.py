"""Direção de vídeo: antes de qualquer animação, a IA lê o trecho inteiro e escreve o filme que vai ilustrá-lo.

Toda animação do Clipator (desenho, cenas, artes, curtas, mapas e gráficos) passa por esta etapa, entre a análise do corte
e a montagem das cenas de cada estilo:

1. **Direção**: a IA recebe a fala inteira com tempos, a análise (tema e ideias) e o que o estilo sabe desenhar, e devolve
   por schema a história (assunto, metáfora, logline e o arco começo/meio/fim), o elenco fixo (quem aparece, sempre o mesmo
   em todas as cenas), os cenários e os planos: para cada trecho da fala, onde estamos, quem está em cena, em que posição,
   fazendo o quê, para quem olha, a câmera (plano e movimento) e a transição.
2. **Conferência** (aqui, sem IA): cada plano tem de estar preso a palavras ditas, na ordem; quem está em cena existe no
   elenco; ninguém divide a mesma posição; ninguém olha para quem não está ali; o cenário foi declarado; a história cobre o
   clip sem buracos; e a continuidade vale (no mesmo cenário e no mesmo plano, quem muda de lado tem de andar ou correr).
   O que dá para arrumar sozinho é arrumado (nome que não foi dito sai, número não dito sai, plano curto demais some).
3. **Correção**: se sobrou problema, a IA recebe a própria direção com a lista e devolve a versão corrigida, uma vez. O
   que ainda estiver errado depois disso sai da direção; sem nenhum plano válido, não há animação.

A direção conferida vira o roteiro (início, fim, âncora, etiqueta, descrição) que as etapas de cena de cada estilo já
recebiam, com a descrição completa do plano (quem, onde, como) para a IA montar a cena coerente com o filme. Tudo fica em
direcao-arte.json, campo "direcao_video", para o painel mostrar e o usuário editar.

Texto na tela continua sendo só o que foi dito: o nome de um personagem só aparece se a fala disser.
"""

from __future__ import annotations

import json
from typing import Any, Callable

VERSAO = 1
MAX_ELENCO = 4
MAX_CENARIOS = 5
MAX_EM_CENA = 3
MAX_PLANOS = 24
BURACO_MAX = 6.0  # segundos sem plano no meio do clip
TIPOS_ELENCO = ("pessoa", "robo", "grupo", "animal", "objeto")
POSICOES = ("esquerda", "centro", "direita", "fundo-esquerda", "fundo-centro", "fundo-direita")
LADO = {"esquerda": -1, "fundo-esquerda": -1, "centro": 0, "fundo-centro": 0, "direita": 1, "fundo-direita": 1}
ACOES_DESLOCAMENTO = ("andar", "correr", "pular", "cair")


def _vocab() -> dict[str, list[str]]:
    """O vocabulário de cinema do Clipator (lugares, ações, planos, movimentos, transições): o mesmo dos curtas."""
    from .artes import curta

    L = curta.listas()
    return {"lugar": L["cenario"], "acao": L["acao"], "plano": L["plano"], "movimento": L["movimento"], "transicao": L["transicao"]}


def _t(v: Any, lim: int) -> str:
    return " ".join(str(v or "").split())[:lim]


def schema() -> dict[str, Any]:
    V = _vocab()
    pers = {"type": "object", "properties": {
        "id": {"type": "string"}, "posicao": {"type": "string", "enum": list(POSICOES)},
        "acao": {"type": "string", "enum": V["acao"]}, "olha_para": {"type": "string"}},
        "required": ["id", "posicao", "acao", "olha_para"], "additionalProperties": False}
    plano = {"type": "object", "properties": {
        "ancora": {"type": "string"}, "ate": {"type": "string"}, "etiqueta": {"type": "string"}, "o_que_mostra": {"type": "string"},
        "cenario": {"type": "string"}, "em_cena": {"type": "array", "items": pers},
        "plano": {"type": "string", "enum": V["plano"]}, "movimento": {"type": "string", "enum": V["movimento"]},
        "transicao": {"type": "string", "enum": V["transicao"]}, "dado": {"type": "string"}, "balao": {"type": "string"}},
        "required": ["ancora", "ate", "etiqueta", "o_que_mostra", "cenario", "em_cena", "plano", "movimento", "transicao", "dado", "balao"],
        "additionalProperties": False}
    return {"type": "object", "properties": {
        "historia": {"type": "object", "properties": {
            "assunto": {"type": "string"}, "metafora": {"type": "string"}, "logline": {"type": "string"},
            "comeco": {"type": "string"}, "meio": {"type": "string"}, "fim": {"type": "string"}},
            "required": ["assunto", "metafora", "logline", "comeco", "meio", "fim"], "additionalProperties": False},
        "elenco": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "papel": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPOS_ELENCO)},
            "nome": {"type": "string"}, "visual": {"type": "string"}},
            "required": ["id", "papel", "tipo", "nome", "visual"], "additionalProperties": False}},
        "cenarios": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "lugar": {"type": "string", "enum": V["lugar"]}, "descricao": {"type": "string"}},
            "required": ["id", "lugar", "descricao"], "additionalProperties": False}},
        "planos": {"type": "array", "items": plano}},
        "required": ["historia", "elenco", "cenarios", "planos"], "additionalProperties": False}


def _fala(pals: list[dict], limite: int = 9000) -> str:
    return " ".join(f"[{w['inicio']:.1f}]{w['texto'].strip()}" for w in pals)[:limite]


def prompt(pals: list[dict], dur: float, titulo: str, analise: dict | None, estilo: str, ritmo: str = "2 a 5", extra: str = "") -> str:
    """O pedido da direção. `estilo` diz o que o estilo desenha (forma, layout, ficha e a ficha curta da direção de arte)."""
    V = _vocab()
    return (
        f"Você é o diretor de uma animação de {dur:.0f} segundos que vai por cima de um corte de vídeo e mostra, em cena, a "
        "história ou o fato que a pessoa está contando. Antes de qualquer cena, escreva a DIREÇÃO DE VÍDEO completa: a "
        "história, quem são os personagens, onde a cena acontece, onde cada um fica, o que cada um faz e como a câmera conta.\n\n"
        f"## O corte\nTítulo: “{titulo}”. Tema: {(analise or {}).get('tema') or '—'}.\n"
        f"Ideias do trecho: {json.dumps((analise or {}).get('ideias') or [], ensure_ascii=False)[:2500]}\n\n"
        f"## O estilo\n{estilo[:6000]}\n\n"
        + (f"## Direção de arte e método\n{extra[:8000]}\n\n" if extra else "")
        + "## O que devolver\n"
        "'historia': 'assunto' (uma frase), 'metafora' (a situação concreta que conta o assunto, mantida no vídeo todo), "
        "'logline' (a história em uma frase) e o arco em 'comeco', 'meio' e 'fim' (o que acontece em cada parte).\n"
        f"'elenco': até {MAX_ELENCO} personagens fixos ('id' curto como p1; 'papel' na história; 'tipo' "
        f"{', '.join(TIPOS_ELENCO)}; 'nome' só se a fala disser o nome, senão vazio; 'visual' em poucas palavras, o mesmo do "
        "começo ao fim). Pode ser vazio se o assunto não tem quem mostrar.\n"
        f"'cenarios': até {MAX_CENARIOS} ('id' curto como c1, 'lugar' da lista, 'descricao' do que tem nele).\n"
        f"'planos': um a cada {ritmo} s, cobrindo de 0 a {dur:.0f} s na ordem da fala, no máximo {MAX_PLANOS}. Em cada um: "
        "'ancora' (4 a 8 palavras COPIADAS da fala, onde o plano começa), 'ate' (vazio), 'etiqueta' (o tema do plano em até 4 "
        "palavras), 'o_que_mostra' (o que o público vê e por que isso diz o que a frase quer dizer), 'cenario' (o id), "
        f"'em_cena' (até {MAX_EM_CENA}, pelo id do elenco, cada um numa 'posicao' diferente, com a 'acao' e 'olha_para' = id de "
        "quem também está em cena, 'camera' ou vazio), 'plano' e 'movimento' da câmera, 'transicao' para o próximo, 'dado' (o "
        "número dito a destacar, copiado da fala, ou vazio) e 'balao' (a frase de alguém citado, ou vazio).\n\n"
        "## Regras de continuidade (o motor confere)\n"
        "- Mesmo personagem = mesmo id e mesmo visual no vídeo todo. Ninguém aparece sem estar no elenco.\n"
        "- Dois personagens nunca ficam na mesma posição. Quem olha para alguém, olha para quem está em cena.\n"
        "- No mesmo cenário e no mesmo plano de câmera, quem troca de lado tem de 'andar' ou 'correr' para chegar lá.\n"
        "- Mude de cenário só quando a fala muda de lugar ou de assunto; aí use uma transição que não seja corte seco.\n"
        "- Nada que não foi dito: nome, número e balão só com palavras da fala.\n\n"
        f"## Listas\nLugares: {', '.join(V['lugar'])}.\nAções: {', '.join(V['acao'])}.\nPlanos: {', '.join(V['plano'])}.\n"
        f"Movimentos: {', '.join(V['movimento'])}.\nTransições: {', '.join(V['transicao'])}.\n\n"
        f"## Fala com tempos\n{_fala(pals)}"
    )


def prompt_correcao(anterior: dict, problemas: list[str], pals: list[dict], dur: float) -> str:
    return (
        f"Esta é a direção de vídeo de uma animação de {dur:.0f} s que você escreveu. A conferência achou os problemas abaixo. "
        "Devolva a direção inteira corrigida (mesmo formato), mudando só o necessário e mantendo a história.\n\n"
        "## Problemas\n" + "\n".join(f"- {p}" for p in problemas[:30]) + "\n\n"
        f"## Direção anterior\n{json.dumps(anterior, ensure_ascii=False)[:14000]}\n\n"
        f"## Fala com tempos\n{_fala(pals)}"
    )


# ---- conferência -----------------------------------------------------------------------------------------------
def conferir(resp: Any, pals: list[dict], dur: float) -> tuple[dict[str, Any], list[str]]:
    """(direção limpa, problemas). A direção limpa só tem planos presos à fala, com o tempo de cada um."""
    from .direcao import _na_fala, ancorar

    V = _vocab()
    problemas: list[str] = []
    if not isinstance(resp, dict):
        return {"historia": {}, "elenco": [], "cenarios": [], "planos": []}, ["a resposta não é uma direção"]
    h = resp.get("historia") if isinstance(resp.get("historia"), dict) else {}
    historia = {k: _t(h.get(k), 300) for k in ("assunto", "metafora", "logline", "comeco", "meio", "fim")}
    if not historia["logline"]:
        problemas.append("falta a 'logline': a história em uma frase")

    elenco, ids = [], set()
    for e in (resp.get("elenco") or [])[:MAX_ELENCO + 2]:
        if not isinstance(e, dict):
            continue
        i = _t(e.get("id"), 12)
        if not i or i in ids:
            problemas.append(f"personagem sem id ou com id repetido ({i or 'vazio'})")
            continue
        nome = _t(e.get("nome"), 40)
        if nome and not _na_fala(nome, pals, 0.99):
            nome = ""  # o nome na tela é só o que foi dito
        ids.add(i)
        elenco.append({"id": i, "papel": _t(e.get("papel"), 80), "tipo": e.get("tipo") if e.get("tipo") in TIPOS_ELENCO else "pessoa",
                       "nome": nome, "visual": _t(e.get("visual"), 80)})
    if len(elenco) > MAX_ELENCO:
        problemas.append(f"elenco com {len(elenco)} personagens: o máximo é {MAX_ELENCO}")
        elenco = elenco[:MAX_ELENCO]
        ids = {e["id"] for e in elenco}

    cenarios, cids = [], set()
    for c in (resp.get("cenarios") or [])[:MAX_CENARIOS + 2]:
        if not isinstance(c, dict):
            continue
        i = _t(c.get("id"), 12)
        if not i or i in cids or c.get("lugar") not in V["lugar"]:
            problemas.append(f"cenário inválido ({i or 'sem id'}): precisa de id único e lugar da lista")
            continue
        cids.add(i)
        cenarios.append({"id": i, "lugar": c["lugar"], "descricao": _t(c.get("descricao"), 160)})
    cenarios = cenarios[:MAX_CENARIOS]
    lugar_de = {c["id"]: c["lugar"] for c in cenarios}

    planos: list[dict[str, Any]] = []
    desde = 0
    brutos = [p for p in (resp.get("planos") or []) if isinstance(p, dict)]
    if not brutos:
        problemas.append("nenhum plano")
    if len(brutos) > MAX_PLANOS:
        problemas.append(f"{len(brutos)} planos: o máximo é {MAX_PLANOS}")
    for k, p in enumerate(brutos[:MAX_PLANOS]):
        n = k + 1
        anc = _t(p.get("ancora"), 120)
        achou = ancorar(anc, pals, desde)
        if achou is None:
            fora_de_ordem = ancorar(anc, pals, 0)
            problemas.append(f"plano {n}: a âncora “{anc}” " + ("está fora da ordem da fala" if fora_de_ordem else "não está na fala; copie palavras ditas"))
            continue
        i, j, _ = achou
        desde = i
        cen = _t(p.get("cenario"), 12)
        if cen not in lugar_de:
            problemas.append(f"plano {n}: o cenário “{cen}” não foi declarado em 'cenarios'")
            cen = planos[-1]["cenario"] if planos else (cenarios[0]["id"] if cenarios else "")
        em_cena, ocupadas, presentes = [], {}, set()
        brutos_cena = [x for x in (p.get("em_cena") or []) if isinstance(x, dict)]
        if len(brutos_cena) > MAX_EM_CENA:
            problemas.append(f"plano {n}: {len(brutos_cena)} personagens em cena; o máximo é {MAX_EM_CENA}")
        for x in brutos_cena[:MAX_EM_CENA]:
            pid = _t(x.get("id"), 12)
            if pid not in ids:
                problemas.append(f"plano {n}: “{pid}” está em cena mas não está no elenco")
                continue
            if pid in presentes:
                continue
            pos = x.get("posicao") if x.get("posicao") in POSICOES else "centro"
            if pos in ocupadas:
                problemas.append(f"plano {n}: {pid} e {ocupadas[pos]} estão na mesma posição ({pos})")
            ocupadas.setdefault(pos, pid)
            presentes.add(pid)
            em_cena.append({"id": pid, "posicao": pos, "acao": x.get("acao") if x.get("acao") in V["acao"] else "parado",
                            "olha_para": _t(x.get("olha_para"), 12)})
        for x in em_cena:
            alvo = x["olha_para"]
            if alvo and alvo != "camera" and alvo not in presentes:
                problemas.append(f"plano {n}: {x['id']} olha para “{alvo}”, que não está em cena")
                x["olha_para"] = ""
            if alvo == x["id"]:
                x["olha_para"] = ""
        dado, balao = _t(p.get("dado"), 16), _t(p.get("balao"), 90)
        trecho = pals[i:min(len(pals), j + 40)]
        planos.append({
            "inicio": round(max(0.0, pals[i]["inicio"] - 0.15), 2), "ancora": " ".join(w["texto"] for w in pals[i:j + 1]),
            "etiqueta": _t(p.get("etiqueta"), 40).upper(), "o_que_mostra": _t(p.get("o_que_mostra"), 260), "cenario": cen,
            "em_cena": em_cena, "plano": p.get("plano") if p.get("plano") in V["plano"] else "medio",
            "movimento": p.get("movimento") if p.get("movimento") in V["movimento"] else "fixo",
            "transicao": p.get("transicao") if p.get("transicao") in V["transicao"] else V["transicao"][0],
            "dado": dado if dado and _na_fala(dado, trecho, 0.99) else "", "balao": balao if balao and _na_fala(balao, trecho, 0.6) else ""})

    # tempos: cada plano vai até o próximo; a história começa no 0 e cobre o clip
    for k, p in enumerate(planos):
        p["fim"] = round(planos[k + 1]["inicio"] if k + 1 < len(planos) else dur, 2)
    if planos:
        if planos[0]["inicio"] > 3.0:
            problemas.append(f"a direção só começa em {planos[0]['inicio']:.1f} s: o primeiro plano tem de abrir o vídeo")
        planos[0]["inicio"] = 0.0
    for p in planos:
        if p["fim"] - p["inicio"] > BURACO_MAX + 2:
            problemas.append(f"aviso: o plano “{p['ancora']}” fica {p['fim'] - p['inicio']:.0f} s sem mudar; dá para dividir em planos menores")
    curtos = [p for p in planos if p["fim"] - p["inicio"] < 0.8]
    for c in curtos:  # plano curto demais não dá tempo de ler: some, e o anterior segura
        k = planos.index(c)
        if k > 0:
            planos[k - 1]["fim"] = c["fim"]
        elif len(planos) > 1:
            planos[1]["inicio"] = 0.0
        planos.remove(c)

    # continuidade entre planos seguidos
    lugares_usados = set()
    for k, p in enumerate(planos):
        lugares_usados.add(p["cenario"])
        if k == 0:
            continue
        a = planos[k - 1]
        if a["cenario"] == p["cenario"] and a["plano"] == p["plano"]:
            antes = {x["id"]: x["posicao"] for x in a["em_cena"]}
            for x in p["em_cena"]:
                pa = antes.get(x["id"])
                if pa and LADO[pa] != LADO[x["posicao"]] and x["acao"] not in ACOES_DESLOCAMENTO:
                    problemas.append(f"plano {k + 1}: {x['id']} pula de {pa} para {x['posicao']} sem andar (mesmo cenário e mesmo plano)")
        if a["cenario"] != p["cenario"] and a["transicao"] == "corte" and "corte" in V["transicao"] and len(V["transicao"]) > 1:
            a["transicao"] = next(t for t in V["transicao"] if t != "corte")  # troca de lugar pede transição: arrumado aqui
    em_algum = {x["id"] for p in planos for x in p["em_cena"]}
    elenco = [e for e in elenco if e["id"] in em_algum]  # quem nunca entra em cena sai do elenco
    cenarios = [c for c in cenarios if c["id"] in lugares_usados]
    return {"versao": VERSAO, "historia": historia, "elenco": elenco, "cenarios": cenarios, "planos": planos}, problemas


def criticos(problemas: list[str]) -> list[str]:
    """Os problemas que justificam pedir a correção: os que quebram a coerência do filme (os avisos só ficam anotados)."""
    return [p for p in problemas if not p.startswith("aviso:")]


# ---- do filme ao roteiro de cada estilo -----------------------------------------------------------------------------
def descrever(p: dict[str, Any], d: dict[str, Any]) -> str:
    """O plano em uma frase completa, para a etapa de cenas do estilo montar o que a direção pediu."""
    elenco = {e["id"]: e for e in d.get("elenco", [])}
    lugar = next((c for c in d.get("cenarios", []) if c["id"] == p.get("cenario")), None)
    quem = []
    for x in p.get("em_cena", []):
        e = elenco.get(x["id"], {})
        rotulo = e.get("nome") or e.get("papel") or x["id"]
        olha = f", olhando para {elenco.get(x['olha_para'], {}).get('papel') or x['olha_para']}" if x.get("olha_para") else ""
        quem.append(f"{rotulo} ({e.get('visual') or e.get('tipo', '')}) à {x['posicao'].replace('fundo-', 'fundo, ')}, {x['acao']}{olha}")
    partes = [p.get("o_que_mostra") or ""]
    if lugar:
        partes.append(f"Cenário: {lugar['lugar']}" + (f" ({lugar['descricao']})" if lugar.get("descricao") else ""))
    if quem:
        partes.append("Em cena: " + "; ".join(quem))
    partes.append(f"Câmera: plano {p.get('plano')}, {p.get('movimento')}; sai com {p.get('transicao')}")
    return ". ".join(x.rstrip(". ") for x in partes if x)[:600]


def roteiro(d: dict[str, Any]) -> list[dict[str, Any]]:
    """O roteiro de sempre (o que as etapas de cena recebem), agora com o plano inteiro da direção em cada cena."""
    out = []
    for p in d.get("planos", []):
        if p["fim"] - p["inicio"] < 0.8:
            continue
        out.append({"inicio": p["inicio"], "fim": p["fim"], "ancora": p["ancora"], "etiqueta": p["etiqueta"],
                    "descricao": descrever(p, d), "dado": p["dado"], "balao": p["balao"],
                    "direcao": {k: p[k] for k in ("cenario", "em_cena", "plano", "movimento", "transicao")}})
    return out


def texto(d: dict[str, Any]) -> str:
    """A direção resumida para entrar no pedido das etapas seguintes (história, elenco e cenários)."""
    h = d.get("historia") or {}
    elenco = "; ".join(f"{e['id']} = {e.get('nome') or e['papel']} ({e['tipo']}, {e.get('visual') or 'visual livre'})" for e in d.get("elenco", []))
    cen = "; ".join(f"{c['id']} = {c['lugar']}" + (f" ({c['descricao']})" if c.get("descricao") else "") for c in d.get("cenarios", []))
    return (f"Direção de vídeo (siga em todas as cenas):\nHistória: {h.get('logline') or '—'}. Metáfora: {h.get('metafora') or '—'}.\n"
            f"Começo: {h.get('comeco') or '—'} Meio: {h.get('meio') or '—'} Fim: {h.get('fim') or '—'}\n"
            f"Elenco fixo: {elenco or 'nenhum personagem'}.\nCenários: {cen or '—'}.")


# ---- a etapa inteira -----------------------------------------------------------------------------------------------
def dirigir(ad: Any, pals: list[dict], dur: float, titulo: str, analise: dict | None, estilo: str, chamar: Callable[..., Any],
            cache: Any = None, cancelar: Any = None, ctx: Callable[[str], Any] | None = None, passo: Callable[[str], None] | None = None,
            ritmo: str = "2 a 5", extra: str = "") -> dict[str, Any]:
    """Pede a direção, confere, pede a correção uma vez se precisar e devolve a direção conferida (com o histórico)."""
    from contextlib import nullcontext

    ctx = ctx or (lambda tarefa: nullcontext())
    passo = passo or (lambda t: None)
    sch = schema()
    with ctx("escrevendo a direção de vídeo") as ev:
        r = chamar(ad, prompt(pals, dur, titulo, analise, estilo, ritmo, extra), sch, cache, cancelar, ev)
    d, probs = conferir(r, pals, dur)
    rodadas = [{"problemas": probs}]
    probs_c = criticos(probs)
    if probs_c:
        passo(f"conferência da direção: {len(probs_c)} problema(s); pedindo a correção à IA")
        for pr in probs_c[:6]:
            passo(f"· {pr}")
        with ctx("corrigindo a direção de vídeo") as ev:
            r2 = chamar(ad, prompt_correcao(r if isinstance(r, dict) else {}, probs_c, pals, dur), sch, None, cancelar, ev)
        d2, probs2 = conferir(r2, pals, dur)
        rodadas.append({"problemas": probs2})
        if len(d2["planos"]) >= len(d["planos"]) or not d["planos"]:
            d = d2
        if probs2:
            passo(f"depois da correção: {len(probs2)} problema(s) arrumados pelo motor ou com o plano retirado")
    else:
        passo("conferência da direção: tudo certo (âncoras, elenco, posições, cenários e continuidade)")
    d["rodadas"] = rodadas
    h = d["historia"]
    if h.get("logline"):
        passo(f"história: {h['logline']}")
    if d["elenco"]:
        passo("elenco: " + "; ".join(f"{e['id']} {e.get('nome') or e['papel']}" for e in d["elenco"]))
    passo(f"direção: {len(d['planos'])} plano(s) em {len(d['cenarios'])} cenário(s)")
    return d
