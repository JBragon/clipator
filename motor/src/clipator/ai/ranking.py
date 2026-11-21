"""Camada 2 da detecção (opcional): a IA reordena os candidatos e sugere títulos.

Uma única chamada recebe os melhores candidatos (texto, duração, nota local e o
corpo do regras.md) e devolve JSON: nota, títulos (cada um com a prova na fala),
gancho, ajuste de início e fim e o motivo. No modo completo, antes disso, a IA
entende a conversa inteira e acha os assuntos fortes (assuntos.py).
"""

from __future__ import annotations

import threading
from typing import Any

from .. import pack
from ..candidates import ajustar_a_frases, montar_frases, snap_to_words, texto_do_trecho
from ..models import Regras
from .adapter import AdapterIA, CacheIA, chamar

RUBRICA = """Dê a cada candidato uma nota de 0 a 100 somando:
- Pool de atenção (0 a 40): quantas pessoas do público do canal param para ver esse assunto.
- Prova visível (0 a 20): o trecho mostra algo concreto (número, história, revelação), não só opinião.
- Conexão (0 a 20): emoção, humor, conflito ou identificação.
- Fit de título (0 a 10): dá para resumir o trecho num título curto e forte que o clip entrega.
- Outlier (0 a 10): foge do comum do nicho.
Penalize trechos que dependem de contexto anterior ou terminam sem conclusão."""

REGRA_TITULO = """Títulos: de 3 a 5 opções sensacionalistas no idioma do vídeo, até {max_chars} caracteres,
no máximo {caps} palavras em CAIXA ALTA. O título pode exagerar a emoção, mas tudo o que ele promete
precisa acontecer dentro do clip."""

PADRAO_TITULO = """Padrão dos canais de cortes que mais crescem: diga quem fala e o que ele faz (FAZ ALERTA, EXPLICA,
REVELA, ABRE O JOGO, DESABAFA, RESPONDE, DETONA) e a afirmação mais forte do trecho, no tom mais forte que a fala
sustenta. Sensacionalista na medida certa: exagere o tom, nunca o fato. Use as palavras que a pessoa usou em vez de
inventar uma consequência, e não prometa nada que ela não diga."""

GANCHO_THUMB = ("Texto da thumb: a frase mais forte que a pessoa diz no trecho, quase literal (pode encurtar), "
                "até 40 caracteres por linha, 2 a 4 linhas")

TITULOS_COM_PROVA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string"},
            "prova": {"type": "string", "description": "Trecho literal da fala (6 a 25 palavras) que sustenta a promessa do título"},
        },
        "required": ["titulo", "prova"],
    },
}

SCHEMA_RANKING: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidatos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "nota": {"type": "integer", "minimum": 0, "maximum": 100},
                    "titulos": TITULOS_COM_PROVA,
                    "gancho": {"type": "string", "description": GANCHO_THUMB},
                    "ajuste_inicio": {"type": "number", "description": "Segundos para somar ao início (negativo antecipa)"},
                    "ajuste_fim": {"type": "number", "description": "Segundos para somar ao fim"},
                    "fecha_assunto": {"type": "boolean", "description": "Com o ajuste, o trecho fecha a ideia"},
                    "motivo": {"type": "string"},
                    "destaques": {"type": "array", "items": {"type": "string"}, "description": "Palavras do trecho para destacar na legenda"},
                    "momentos_fortes": {
                        "type": "array",
                        "description": "1 ou 2 falas curtas (1,5 a 4,5 s) que abrem o Short como gancho antes do corte",
                        "items": {"type": "object", "properties": {"inicio": {"type": "number"}, "fim": {"type": "number"}},
                                  "required": ["inicio", "fim"]},
                    },
                },
                "required": ["id", "nota", "titulos", "gancho", "ajuste_inicio", "ajuste_fim", "fecha_assunto", "motivo",
                             "destaques", "momentos_fortes"],
            },
        }
    },
    "required": ["candidatos"],
}

SCHEMA_TITULOS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titulos": TITULOS_COM_PROVA,
        "gancho": {"type": "string"},
    },
    "required": ["titulos", "gancho"],
}


def _contexto_canal(canal_md: str, regras_md: str, titulos_md: str, regras: Regras, titulos_meta: dict) -> str:
    partes = []
    if canal_md.strip():
        partes.append(f"## Canal\n{canal_md.strip()}")
    if regras_md.strip():
        partes.append(f"## Regras do canal\n{regras_md.strip()}")
    if regras.temas_proibidos:
        partes.append("Temas proibidos: " + ", ".join(regras.temas_proibidos))
    from ..titles import DESCRICAO_TEMPERATURA, formulas_do_canal

    temas = titulos_meta.get("temas") or []
    if temas:
        partes.append("Tema do vídeo: " + ", ".join(map(str, temas)))
    temp = str(titulos_meta.get("temperatura") or "")
    if temp in DESCRICAO_TEMPERATURA:
        partes.append(f"## Temperatura dos títulos: {temp}\n{DESCRICAO_TEMPERATURA[temp]}")
    formulas = formulas_do_canal(titulos_meta)
    if formulas:
        partes.append("## Fórmulas de título do canal\n" + "\n".join(f"- {f}" for f in formulas[:30]))
    gatilhos = titulos_meta.get("palavras_gatilho") or []
    if gatilhos:
        partes.append("Palavras-gatilho (use só quando o clip mostra isso): " + ", ".join(map(str, gatilhos[:40])))
    nunca = titulos_meta.get("nunca_usar") or []
    if nunca:
        partes.append("Nunca use nos títulos: " + ", ".join(map(str, nunca)))
    if titulos_md.strip():
        partes.append(titulos_md.strip())
    return "\n\n".join(partes)


def _regra_titulo(titulos_meta: dict, trava: bool) -> str:
    r = REGRA_TITULO.format(max_chars=titulos_meta.get("max_caracteres", 70), caps=titulos_meta.get("palavras_caixa_alta", 2))
    if titulos_meta.get("caixa_alta_total"):
        r = r.replace(f"no máximo {titulos_meta.get('palavras_caixa_alta', 2)} palavras em CAIXA ALTA", "o título inteiro em CAIXA ALTA")
    if titulos_meta.get("temperatura") == "morno":
        r = r.replace("opções sensacionalistas", "opções diretas e informativas")
    if not trava:
        r = r.replace(" O título pode exagerar a emoção, mas tudo o que ele promete\nprecisa acontecer dentro do clip.", "")
    if titulos_meta.get("temperatura") != "morno":
        r += "\n" + PADRAO_TITULO
    return r


AJUSTE_INICIO_MIN, AJUSTE_INICIO_MAX = -30.0, 5.0  # a IA pode antecipar até 30 s para pegar o contexto
AJUSTE_FIM_MIN = -5.0
CONTEXTO_ANTES, CONTEXTO_DEPOIS = 30.0, 30.0  # fala mostrada em volta de cada candidato para a IA estender


def prompt_ranking(cands: list[dict], contexto: str, regra_titulo: str, dur_max: float = 60, dur_ext: float = 90,
                   dur_min: float = 20, dur_alvo: float | None = None) -> str:
    alvo = dur_alvo if dur_alvo is not None else dur_min + 0.75 * (dur_max - dur_min)
    linhas = [
        "Você é o editor de um canal de cortes. Avalie os trechos candidatos de um vídeo longo e",
        "responda só com o JSON do schema.",
        "",
        RUBRICA,
        "",
        regra_titulo,
        "",
        f"Duração: um bom Short deste canal tem perto de {alvo:.0f} s (de {dur_min:.0f} a {dur_max:.0f} s). Corte curto",
        "demais deixa a história pela metade: se o candidato tem menos que isso, estenda até incluir o contexto",
        "e a conclusão. Só encurte para tirar enrolação.",
        "ajuste_inicio e ajuste_fim: o corte precisa FECHAR O ASSUNTO. Comece no início de uma frase e inclua",
        f"a pergunta ou o contexto de que o trecho depende (ajuste_inicio de {AJUSTE_INICIO_MIN:.0f} a {AJUSTE_INICIO_MAX:.0f} s).",
        "Termine depois da conclusão da ideia, nunca no meio de uma frase nem numa pergunta cuja resposta vem",
        f"logo depois (ajuste_fim de {AJUSTE_FIM_MIN:.0f} s até o corte chegar a {dur_max:.0f} s). Pode ir até {dur_ext:.0f} s",
        "só se for para fechar o assunto. Use 0 se já estiver bom.",
        "As linhas em “antes do corte” e “depois do corte” são a fala em volta do trecho, com os tempos do vídeo:",
        "use-as para decidir os ajustes. A nota e os títulos valem para o trecho já ajustado.",
        "fecha_assunto: true se, com o ajuste, o trecho tem começo, meio e fim (a ideia se conclui).",
        "Em cada título, `prova` é o trecho literal da fala do corte que sustenta a promessa. Título sem prova é descartado.",
        "momentos_fortes: 1 ou 2 falas curtas (1,5 a 4,5 s cada, frase inteira ou o pedaço mais quente dela) que abrem",
        "o Short como gancho antes do corte começar: a afirmação mais forte, a reação, o número. Use os tempos das",
        f"linhas, de dentro do corte já ajustado e fora dos primeiros {MOMENTO_INICIO_MINIMO:.0%} dele (o público vê logo depois).",
        "",
        contexto,
        "",
        "## Candidatos",
    ]
    for c in cands:
        linhas.append(f"### {c['id']} ({c['duracao']:.0f} s, nota local {c['nota']:.0f}, de {c['inicio']:.1f} a {c['fim']:.1f})")
        ia = c.get("ia") or {}
        if ia.get("assunto"):  # veio do mapa de assuntos: a IA já sabe do que a conversa trata
            linhas.append(f"assunto: {ia['assunto']} | tese: {ia.get('tese', '')}"
                          + (f" | contexto: {ia['contexto']}" if ia.get("contexto") else ""))
        if c.get("contexto_antes"):
            linhas += ["antes do corte:", c["contexto_antes"], "corte:"]
        linhas.append(c.get("texto_compacto") or c.get("texto", ""))
        if c.get("contexto_depois"):
            linhas += ["depois do corte:", c["contexto_depois"]]
        linhas.append("")
    return "\n".join(linhas)


def _contexto_em_volta(pals: list[dict], c: dict) -> tuple[str, str]:
    """A fala antes e depois do candidato, para a IA ver de onde vem e para onde vai a ideia."""
    ini, fim = c["inicio"], c["fim"]
    antes = pack.compactar([w for w in pals if w["inicio"] < ini - 0.01], ini - CONTEXTO_ANTES, ini)
    depois = pack.compactar([w for w in pals if w["inicio"] >= fim - 0.01], fim, fim + CONTEXTO_DEPOIS)
    return antes, depois


def ranquear(cands: list[dict], transcricao: dict, adapter: AdapterIA, regras: Regras, canal_md: str = "",
             regras_md: str = "", titulos_md: str = "", titulos_meta: dict | None = None, cache: CacheIA | None = None,
             cancelar: threading.Event | None = None, fio: str = "") -> list[dict]:
    """Modo econômico: a IA só vê os N melhores candidatos locais."""
    from ..transcribe import palavras as _palavras

    titulos_meta = titulos_meta or {}
    pals = _palavras(transcricao)
    top = sorted(cands, key=lambda c: -c["nota"])[: regras.candidatos_para_ia]
    for c in top:
        c["texto_compacto"] = pack.compactar(pals, c["inicio"], c["fim"])
        c["contexto_antes"], c["contexto_depois"] = _contexto_em_volta(pals, c)
    contexto = _contexto_canal(canal_md, regras_md, titulos_md, regras, titulos_meta)
    if fio:
        contexto += "\n\n## O episódio (do mapa de assuntos)\n" + fio
    dur_ext = regras.teto_curto()
    prompt = prompt_ranking(top, contexto, _regra_titulo(titulos_meta, regras.trava_titulo), regras.duracao_max, dur_ext,
                            regras.duracao_min, regras.alvo_curto())
    frases = montar_frases(pals)
    resp = chamar(adapter, prompt, SCHEMA_RANKING, cache, cancelar)
    por_id = {r.get("id"): r for r in (resp or {}).get("candidatos", []) if isinstance(r, dict)}
    duracao = float(transcricao.get("duracao") or 0)
    out = []
    for c in cands:
        c = dict(c)
        for k in ("texto_compacto", "contexto_antes", "contexto_depois"):
            c.pop(k, None)
        r = por_id.get(c["id"])
        if r:
            longo = c.get("modo") == "longo"
            teto = regras.corte_longo_max if longo else dur_ext
            piso = regras.corte_longo_min if longo else regras.duracao_min
            ai = max(AJUSTE_INICIO_MIN, min(AJUSTE_INICIO_MAX, _num(r.get("ajuste_inicio"))))
            af = max(AJUSTE_FIM_MIN, min(max(0.0, teto - c["duracao"]), _num(r.get("ajuste_fim"))))
            if ai or af:
                # o ajuste da IA vai para fronteiras de frase: começa numa frase e termina numa que fecha
                ini, fim = ajustar_a_frases(c["inicio"] + ai, c["fim"] + af, frases, teto, max(5.0, piso - 3))
                ini, fim = snap_to_words(ini, fim, pals, duracao)
                # a IA não deixa o corte mais curto que a duração mínima do canal
                if max(5.0, min(piso - 3, c["duracao"])) <= fim - ini <= teto + 1:
                    c["ajuste_ia"] = {"inicio": round(ini - c["inicio"], 2), "fim": round(fim - c["fim"], 2)}
                    c["inicio"], c["fim"], c["duracao"] = ini, fim, round(fim - ini, 2)
                    c["texto"] = texto_do_trecho(transcricao, ini, fim)
            antes = c.get("ia") or {}
            do_mapa = bool(antes.get("assunto"))
            c["nota_local"] = c.get("nota_local", c["nota"])
            nova = float(_num(r.get("nota")) if r.get("nota") is not None else c["nota"])
            # do mapa de assuntos: a nota do editor-chefe viu o episódio inteiro e pesa metade
            c["nota"] = round((c["nota"] + nova) / 2, 1) if do_mapa else nova
            c["ia"] = {**(antes if do_mapa else {}), "agente": adapter.nome,
                       "motivo": r.get("motivo", "") or antes.get("motivo", ""),
                       "gancho": r.get("gancho", "") or antes.get("gancho", ""),
                       "destaques": r.get("destaques", []), "fecha_assunto": bool(r.get("fecha_assunto", True))}
            momentos = momentos_fortes(r.get("momentos_fortes"), c, pals, duracao)
            if momentos:
                c["ia"]["abertura"] = momentos
            if r.get("fecha_assunto") is False:  # a própria IA diz que a ideia ficou aberta
                c["nota"] = max(0.0, c["nota"] - 8)
            tits = _titulos_da_ia(r.get("titulos"), c.get("texto", ""), regras.trava_titulo,
                                  int(titulos_meta.get("max_caracteres", 70) or 70))
            if do_mapa:  # os títulos do mapa (já provados) continuam como opção
                tits = list(dict.fromkeys([*tits, *(c.get("titulos") or [])]))[:5]
            if tits:
                c["titulos"] = tits
            c["fonte"] = "local+ia"
        out.append(c)
    out.sort(key=lambda c: -c["nota"])
    _sem_titulo_repetido(out)
    return out


MOMENTO_INICIO_MINIMO = 0.15
MOMENTO_MIN, MOMENTO_MAX = 1.0, 5.0


def momentos_fortes(itens: Any, c: dict, pals: list[dict], duracao: float) -> list[list[float]]:
    """Os momentos de gancho do Short conferidos: dentro do corte, fora dos primeiros 15%, de 1 a 5 s, encaixados
    em palavras, sem sobreposição e no máximo 2, em ordem. Em segundos do vídeo original (abertura.manuais)."""
    out: list[list[float]] = []
    piso = c["inicio"] + (c["fim"] - c["inicio"]) * MOMENTO_INICIO_MINIMO
    for m in itens if isinstance(itens, list) else []:
        if not isinstance(m, dict):
            continue
        a, b = _num(m.get("inicio")), _num(m.get("fim"))
        if b <= a or a < piso - 0.5 or b > c["fim"] + 0.5:
            continue
        a, b = snap_to_words(max(a, piso), min(b, c["fim"]), pals, duracao, max_lead=0.1, max_tail=0.2, janela=0.8)
        a, b = max(a, piso), min(b, c["fim"])
        if not (MOMENTO_MIN <= b - a <= MOMENTO_MAX) or any(a < y + 0.5 and b > x - 0.5 for x, y in out):
            continue
        out.append([round(a, 3), round(b, 3)])
        if len(out) == 2:
            break
    return sorted(out)


def _titulos_da_ia(titulos: Any, texto: str, trava: bool, max_chars: int) -> list[str]:
    """Os títulos da IA limpos: sem vazio, sem repetição, cortados no limite de caracteres e, com a trava
    ligada, os que prometem algo que aparece no clip vêm primeiro."""
    from ..titles import respeita_trava

    from .assuntos import prova_confere

    out: list[str] = []
    for t in titulos if isinstance(titulos, list) else []:
        if isinstance(t, dict):  # {"titulo", "prova"}: a prova tem de aparecer na fala do corte
            if texto and not prova_confere(str(t.get("prova") or ""), texto):
                continue
            t = str(t.get("titulo") or "")
        if not isinstance(t, str) or not t.strip():
            continue
        t = " ".join(t.split()).strip("\"'")
        if len(t) > max_chars + 10:  # a IA passou muito do limite: corta na palavra
            t = t[: max_chars - 1].rsplit(" ", 1)[0] + "…"
        if t.lower() not in {x.lower() for x in out}:
            out.append(t)
    if trava and texto:
        out.sort(key=lambda t: not respeita_trava(t, texto))
    return out[:5]


def _sem_titulo_repetido(cands: list[dict]) -> None:
    """Dois cortes não abrem com o mesmo título: o de nota menor passa a usar uma opção que ninguém usou."""
    usados: set[str] = set()
    for c in cands:
        tits = c.get("titulos") or []
        if not tits:
            continue
        novo = next((t for t in tits if t.lower() not in usados), None)
        if novo and novo != tits[0]:
            tits.remove(novo)
            tits.insert(0, novo)
        usados.add(tits[0].lower())


def _num(v: Any) -> float:
    try:
        x = float(v or 0)
    except (TypeError, ValueError):
        return 0.0
    return x if x == x else 0.0  # NaN vira 0


def sugerir_titulos(texto_clip: str, adapter: AdapterIA, contexto: str, titulos_meta: dict, trava: bool,
                    cache: CacheIA | None = None, cancelar: threading.Event | None = None) -> dict:
    """Botão "gerar outros": chamada curta só daquele clip."""
    prompt = "\n".join([
        "Sugira títulos para este clip de um canal de cortes. Responda só com o JSON do schema.",
        "", _regra_titulo(titulos_meta, trava),
        "Em cada título, `prova` é o trecho literal da fala do clip que sustenta a promessa. Título sem prova é descartado.",
        "", contexto, "", "## Transcrição do clip", texto_clip,
    ])
    r = chamar(adapter, prompt, SCHEMA_TITULOS, cache, cancelar)
    r = dict(r) if isinstance(r, dict) else {"titulos": [], "gancho": ""}
    r["titulos"] = _titulos_da_ia(r.get("titulos"), texto_clip, trava, int(titulos_meta.get("max_caracteres", 70) or 70))
    return r


# ---- cortes longos (8 a 20 min, 16:9) -----------------------------------------------------------
SCHEMA_LONGO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "nota": {"type": "integer", "minimum": 0, "maximum": 100},
        "titulos": TITULOS_COM_PROVA,
        "gancho": {"type": "string", "description": GANCHO_THUMB},
        "trecho_forte": {
            "type": "object",
            "properties": {
                "inicio": {"type": "number"},
                "fim": {"type": "number"},
                "frase": {"type": "string", "description": "A frase central do trecho forte"},
            },
            "required": ["inicio", "fim", "frase"],
        },
        "motivo": {"type": "string"},
    },
    "required": ["nota", "titulos", "gancho", "trecho_forte", "motivo"],
}

TRECHO_FORTE_MIN, TRECHO_FORTE_MAX = 6.0, 25.0
INICIO_MINIMO_FORTE = 0.1  # o trecho forte não sai dos primeiros 10% do corte, que o público vê logo depois


def _origem(meta: dict | None, ini: float, fim: float) -> str:
    """Título e canal do vídeo original e os capítulos que cruzam o corte: ajudam a IA a nomear quem fala."""
    meta = meta or {}
    linhas = []
    if meta.get("titulo"):
        linhas.append(f"Vídeo original: {meta['titulo']}" + (f" (canal {meta['canal']})" if meta.get("canal") else ""))
    caps = [c for c in meta.get("capitulos") or []
            if isinstance(c, dict) and c.get("titulo") and float(c.get("inicio") or 0) < fim
            and float(c.get("fim") or 1e9) > ini]
    if caps:
        linhas.append("Capítulos do original neste trecho: " + " · ".join(str(c["titulo"]) for c in caps[:6]))
    return "\n".join(linhas)


def prompt_longo(c: dict, texto: str, contexto: str, regra_titulo: str, origem: str = "") -> str:
    dur = c["fim"] - c["inicio"]
    return "\n".join([
        f"Você é o editor de um canal de cortes longos de podcast. Este corte de {dur / 60:.0f} min, horizontal, já",
        "está decidido. Responda só com o JSON do schema.",
        "",
        "O vídeo segue o padrão dos cortes longos que mais performam: abre com o TRECHO FORTE, a fala mais",
        "impactante do corte (perto de 15 s), e só então o corte começa do início e apresenta o assunto.",
        "trecho_forte: escolha pelos tempos [início-fim] das linhas. Frases completas e seguidas, de 10 a 20 s,",
        "que funcionam sozinhas (nada de começar com \"e\", \"mas\", \"porque\" ou depender do que veio antes) e",
        "deixam vontade de ver o resto: uma afirmação forte, uma previsão, uma revelação ou uma frase de efeito.",
        f"Não pegue dos primeiros {INICIO_MINIMO_FORTE:.0%} do corte (de {c['inicio']:.1f} a "
        f"{c['inicio'] + dur * INICIO_MINIMO_FORTE:.1f}), que o público vê logo em seguida.",
        "",
        regra_titulo,
        "Nos cortes longos o título nomeia quem fala (PROFESSOR, MÉDICO, EX-POLICIAL ou o nome, se for conhecido)",
        "e, quando o vídeo original deixa claro, termina com \" | Nome no Podcast\".",
        "O título, a thumb e o trecho forte contam a mesma promessa, e ela acontece dentro do corte.",
        "Em cada título, `prova` é o trecho literal da fala que sustenta a promessa. Título sem prova é descartado.",
        "nota: de 0 a 100, quanto esse corte prende o público do canal do começo ao fim.",
        "",
        contexto,
        "",
        origem,
        "",
        f"## Corte ({c['inicio']:.1f} a {c['fim']:.1f})",
        texto,
    ])


def analisar_longos(cands: list[dict], transcricao: dict, adapter: AdapterIA, regras: Regras, canal_md: str = "",
                    regras_md: str = "", titulos_md: str = "", titulos_meta: dict | None = None,
                    cache: CacheIA | None = None, cancelar: threading.Event | None = None,
                    metadados: dict | None = None, fio: str = "") -> list[dict]:
    """Uma chamada por corte longo: títulos no padrão dos canais de cortes, texto da thumb, nota e o trecho forte
    que abre o vídeo (c["ia"]["abertura"], em segundos do original). Corte sem resposta fica como estava."""
    from ..transcribe import palavras as _palavras

    titulos_meta = titulos_meta or {}
    if not cands:
        return cands
    pals = _palavras(transcricao)
    duracao = float(transcricao.get("duracao") or (pals[-1]["fim"] if pals else 0))
    contexto = _contexto_canal(canal_md, regras_md, titulos_md, regras, titulos_meta)
    if fio:
        contexto += "\n\n## O episódio (do mapa de assuntos)\n" + fio
    regra_t = _regra_titulo(titulos_meta, regras.trava_titulo)
    out = []
    for c in cands:
        c = dict(c)
        texto = pack.compactar(pals, c["inicio"], c["fim"])
        resp = chamar(adapter, prompt_longo(c, texto, contexto, regra_t, _origem(metadados, c["inicio"], c["fim"])),
                      SCHEMA_LONGO, cache, cancelar)
        if not isinstance(resp, dict):
            out.append(c)
            continue
        ia: dict[str, Any] = {"agente": adapter.nome, "motivo": str(resp.get("motivo") or ""),
                              "gancho": str(resp.get("gancho") or ""), "destaques": []}
        forte = trecho_forte(resp.get("trecho_forte"), c, pals, duracao)
        if forte:
            ia["abertura"] = [list(forte)]
            ia["frase_forte"] = str((resp.get("trecho_forte") or {}).get("frase") or "")
        c["ia"] = ia
        c["nota_local"] = c.get("nota_local", c["nota"])
        if resp.get("nota") is not None:
            c["nota"] = float(_num(resp.get("nota")))
        tits = _titulos_da_ia(resp.get("titulos"), c.get("texto", ""), regras.trava_titulo,
                              int(titulos_meta.get("max_caracteres", 70) or 70) + 30)  # cabe o " | Nome no Podcast"
        if tits:
            c["titulos"] = tits
        c["fonte"] = "local+ia"
        out.append(c)
    return out


def trecho_forte(r: Any, c: dict, pals: list[dict], duracao: float) -> tuple[float, float] | None:
    """O trecho forte da IA conferido: dentro do corte, fora dos primeiros 10% e com 6 a 25 s, encaixado em
    palavras inteiras. Fora disso, None (o render escolhe sozinho pela fala e pela energia)."""
    if not isinstance(r, dict):
        return None
    try:
        ini, fim = float(r["inicio"]), float(r["fim"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (ini == ini and fim == fim) or fim <= ini:
        return None
    piso = c["inicio"] + (c["fim"] - c["inicio"]) * INICIO_MINIMO_FORTE
    ini, fim = max(ini, piso), min(fim, c["fim"])
    ini, fim = snap_to_words(ini, fim, pals, duracao)
    ini, fim = max(ini, c["inicio"]), min(fim, c["fim"])
    if not (TRECHO_FORTE_MIN <= fim - ini <= TRECHO_FORTE_MAX):
        return None
    return round(ini, 3), round(fim, 3)
