"""Análise por assuntos (modo completo): a IA entende a conversa inteira e acha os assuntos fortes.

Em vez de reordenar janelas que o motor achou, a IA lê a transcrição na ordem, em blocos de 20 min, como um
editor de canal de cortes assistindo ao episódio:

1. Mapa: cada bloco recebe o "fio da conversa" dos blocos anteriores (quem é o convidado, o que já foi dito, o
   que ficou prometido para depois), o título, a descrição e os capítulos do vídeo original. A IA devolve os
   assuntos do bloco: onde a conversa sobre aquilo começa e termina, a tese mais forte nas palavras da pessoa,
   o ângulo que prende (conflito, revelação, previsão, contradição, história, número), o contexto de que o
   público precisa, o melhor Short dentro do assunto, o trecho forte que abre o corte longo, títulos e a thumb.
2. Editor-chefe: uma chamada curta, só com o resumo dos assuntos (sem transcrição), compara o episódio inteiro,
   dá a nota final e junta assuntos vizinhos em cortes longos de 8 a 20 min.

Criativo, mas fiel: cada título vem com a `prova`, o trecho da fala que sustenta a promessa. Título cuja prova
não aparece no corte é descartado (prova_confere). O resultado fica em analise/assuntos.json para a tela e para
as próximas etapas; os candidatos saem no mesmo formato dos locais.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from .. import pack
from ..candidates import ajustar_a_frases, dedupe_overlapping, montar_frases, snap_to_words, texto_do_trecho
from ..models import Regras
from ..textutil import normalizar, tokens
from .adapter import AdapterIA, CacheIA, chamar

ANGULOS = ["conflito", "revelacao", "previsao", "contradicao", "historia", "numero", "polemica", "conselho",
           "bastidor", "humor", "emocao"]
FIO_MAX = 1500  # caracteres do fio da conversa passados ao bloco seguinte

_TITULOS_COM_PROVA = {
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
_INTERVALO = {"type": "object", "properties": {"inicio": {"type": "number"}, "fim": {"type": "number"}}, "required": ["inicio", "fim"]}

SCHEMA_MAPA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fio": {"type": "string", "description": "O fio da conversa até o fim deste bloco, para o próximo bloco"},
        "convidado": {"type": "string", "description": "Quem fala e o que faz (ex.: Professor Hoc, historiador e geopolítico)"},
        "assuntos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "number"},
                    "fim": {"type": "number"},
                    "assunto": {"type": "string"},
                    "tese": {"type": "string", "description": "A afirmação mais forte que a pessoa faz, nas palavras dela"},
                    "angulo": {"type": "string", "description": "Por que isso prende quem está rolando o feed"},
                    "gatilhos": {"type": "array", "items": {"type": "string", "enum": ANGULOS}},
                    "contexto": {"type": "string", "description": "O que o público precisa saber para entender; vazio se nada"},
                    "nota": {"type": "integer", "minimum": 0, "maximum": 100},
                    "short": _INTERVALO,
                    "trecho_forte": {"type": "object", "properties": {"inicio": {"type": "number"}, "fim": {"type": "number"},
                                                                     "frase": {"type": "string"}},
                                     "required": ["inicio", "fim", "frase"]},
                    "titulos": _TITULOS_COM_PROVA,
                    "thumb": {"type": "string", "description": "Texto da thumb: a frase mais forte, quase literal, 2 a 4 linhas"},
                },
                "required": ["inicio", "fim", "assunto", "tese", "angulo", "gatilhos", "contexto", "nota", "short",
                             "trecho_forte", "titulos", "thumb"],
            },
        },
    },
    "required": ["fio", "convidado", "assuntos"],
}

SCHEMA_EDITOR: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assuntos": {
            "type": "array",
            "items": {"type": "object", "properties": {"id": {"type": "string"}, "nota": {"type": "integer", "minimum": 0, "maximum": 100},
                                                       "motivo": {"type": "string"}},
                      "required": ["id", "nota", "motivo"]},
        },
        "longos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "de": {"type": "string", "description": "id do primeiro assunto"},
                    "ate": {"type": "string", "description": "id do último assunto (pode ser o mesmo)"},
                    "nota": {"type": "integer", "minimum": 0, "maximum": 100},
                    "titulos": _TITULOS_COM_PROVA,
                    "thumb": {"type": "string"},
                    "motivo": {"type": "string"},
                },
                "required": ["de", "ate", "nota", "titulos", "thumb", "motivo"],
            },
        },
    },
    "required": ["assuntos", "longos"],
}

OLHO_DE_EDITOR = """Leia como o editor de um canal de cortes que cresce rápido. Procure os assuntos fortes da conversa:
- conflito (a pessoa discorda, critica, acusa, desmente);
- revelação ou bastidor (algo que o público não sabia);
- previsão ou alerta (o que vai acontecer, o que vai dar errado);
- contradição (alguém defende uma coisa e faz outra);
- história pessoal com virada, número chocante, conselho prático que muda algo;
- a frase de efeito que viraria thumb.
Use o contexto da conversa inteira: uma fala que parece morna pode ser forte por causa do que veio antes (a
pergunta, a provocação, a história que ela fecha). Ignore conversa de abertura, patrocínio, piada interna e
assunto que não se conclui."""

CRIATIVO_FIEL = """Seja criativo no ângulo, nunca no fato. Os títulos podem ser sensacionalistas na medida certa: escolha a leitura
mais forte que a fala sustenta, dê nome a quem fala (PROFESSOR, MÉDICO, EX-POLICIAL ou o nome) e o que ele faz
(FAZ ALERTA, REVELA, DETONA, ABRE O JOGO, EXPLICA), mas tudo o que o título promete precisa estar na fala.
Em cada título, `prova` é o trecho literal da fala que sustenta a promessa. Sem prova, sem título."""


def prova_confere(prova: str, texto: str, minimo: float = 0.75) -> bool:
    """A prova do título aparece no corte: pelo menos `minimo` das palavras de conteúdo dela estão no texto, numa
    janela do tamanho da prova (a transcrição muda uma letra aqui e ali; a ordem não precisa ser exata)."""
    conteudo = [normalizar(t) for t in tokens(prova) if len(t) > 2]
    if len(conteudo) < 3:
        return False
    alvo = [normalizar(t) for t in tokens(texto)]
    if not alvo:
        return False
    n = len(conteudo)
    janela = max(n * 2, n + 6)
    precisa = set(conteudo)
    for i in range(0, max(1, len(alvo) - n + 1)):
        trecho = set(alvo[i:i + janela])
        if len(precisa & trecho) >= minimo * len(precisa):
            return True
    return False


def titulos_com_prova(titulos: Any, texto: str, max_chars: int) -> list[str]:
    """Os títulos cuja prova confere com a fala do corte, limpos e sem repetição."""
    out: list[str] = []
    for t in titulos if isinstance(titulos, list) else []:
        if not isinstance(t, dict):
            continue
        titulo = " ".join(str(t.get("titulo") or "").split()).strip("\"'")
        if not titulo or not prova_confere(str(t.get("prova") or ""), texto):
            continue
        if len(titulo) > max_chars + 10:
            titulo = titulo[: max_chars - 1].rsplit(" ", 1)[0] + "…"
        if titulo.lower() not in {x.lower() for x in out}:
            out.append(titulo)
    return out[:5]


def _origem(meta: dict | None) -> str:
    meta = meta or {}
    linhas = []
    if meta.get("titulo"):
        linhas.append(f"Vídeo original: {meta['titulo']}" + (f" (canal {meta['canal']})" if meta.get("canal") else ""))
    desc = str(meta.get("descricao") or "").strip()
    if desc:
        linhas.append("Descrição do original (pode ter propaganda; use só o que ajuda a entender o episódio):\n" + desc[:900])
    caps = [c for c in meta.get("capitulos") or [] if isinstance(c, dict) and c.get("titulo")]
    if caps:
        linhas.append("Capítulos do original:\n" + "\n".join(f"[{float(c.get('inicio') or 0):.0f}] {c['titulo']}" for c in caps[:40]))
    return "\n\n".join(linhas)


def prompt_mapa(n: int, total: int, a: float, b: float, texto: str, fio: str, contexto: str, origem: str,
                regras: Regras, regra_titulo: str) -> str:
    return "\n".join([
        f"Você está assistindo a um episódio longo (bloco {n} de {total}, de {a:.0f} a {b:.0f} s) para achar os assuntos",
        "fortes que viram cortes. Responda só com o JSON do schema.",
        "",
        OLHO_DE_EDITOR,
        "",
        "Para cada assunto forte deste bloco:",
        "- inicio/fim: onde a conversa sobre aquilo começa (inclua a pergunta ou a provocação que abre) e onde se",
        "  conclui. Use os tempos [início-fim] das linhas. Pode passar de um bloco para o outro só se a conversa",
        "  continuar; o fim nunca para no meio de uma frase.",
        "- tese: a afirmação mais forte, nas palavras da pessoa. contexto: o que o público precisa saber antes.",
        f"- short: o melhor momento de {regras.duracao_min:.0f} a {regras.teto_curto():.0f} s dentro do assunto, perto de "
        f"{regras.alvo_curto():.0f} s, que se entende sozinho e fecha a ideia.",
        "- trecho_forte: 10 a 20 s de frases seguidas, a fala mais impactante, que abriria o corte como gancho.",
        "- nota: de 0 a 100, quanto o assunto prende o público do canal.",
        "Só assuntos com algo forte; prefira 2 a 6 por bloco a uma lista de tudo o que foi falado.",
        "fio: resuma para o próximo bloco quem fala, o que já foi dito, as teses e o que ficou para depois.",
        "",
        regra_titulo,
        CRIATIVO_FIEL,
        "",
        contexto,
        "",
        origem,
        "",
        "## Fio da conversa até aqui",
        fio or "(começo do episódio)",
        "",
        "## Transcrição do bloco",
        texto,
    ])


def prompt_editor(assuntos: list[dict], fio: str, convidado: str, contexto: str, regras: Regras) -> str:
    linhas = [
        "Você é o editor-chefe de um canal de cortes. A equipe mapeou os assuntos de um episódio inteiro. Compare",
        "todos e responda só com o JSON do schema.",
        "",
        "assuntos: dê a nota final de cada um (0 a 100) pensando no episódio inteiro: o que é mais forte, o que",
        "se repete (fique com a melhor versão e baixe as outras) e o que só funciona com contexto.",
        f"longos: proponha os cortes longos (horizontais, de {regras.corte_longo_min / 60:.0f} a {regras.corte_longo_max / 60:.0f} min)",
        "juntando assuntos vizinhos que formam uma história só (de = primeiro id, ate = último). Um corte longo",
        "tem uma promessa clara; não junte assuntos sem ligação só para dar o tempo. Títulos e thumb no mesmo",
        "padrão, e a prova de cada título tem de vir da tese ou das falas dos assuntos incluídos.",
        "",
        CRIATIVO_FIEL,
        "",
        contexto,
        "",
        f"Quem fala: {convidado}" if convidado else "",
        "## O episódio",
        fio,
        "",
        "## Assuntos",
    ]
    for s in assuntos:
        linhas.append(f"### {s['id']} ({s['inicio']:.0f}-{s['fim']:.0f} s, {(s['fim'] - s['inicio']) / 60:.1f} min, nota {s['nota']})")
        linhas.append(f"assunto: {s['assunto']}")
        linhas.append(f"tese: {s['tese']}")
        linhas.append(f"ângulo: {s['angulo']}")
        if s.get("contexto"):
            linhas.append(f"contexto: {s['contexto']}")
        if s.get("titulos"):
            linhas.append("títulos da equipe: " + " · ".join(s["titulos"][:3]))
        linhas.append("")
    return "\n".join(linhas)


def _num(v: Any, padrao: float | None = None) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return padrao
    return x if x == x else padrao


def mapear(transcricao: dict, adapter: AdapterIA, regras: Regras, contexto: str, regra_titulo: str,
           metadados: dict | None = None, cache: CacheIA | None = None, cancelar: threading.Event | None = None,
           progresso: Callable[[float, str], None] | None = None, max_chars: int = 70) -> dict:
    """Passo 1: os assuntos de cada bloco, na ordem, com o fio da conversa passando de um bloco para o outro."""
    from ..transcribe import palavras as _palavras

    pals = _palavras(transcricao)
    duracao = float(transcricao.get("duracao") or (pals[-1]["fim"] if pals else 0))
    origem = _origem(metadados)
    bl = pack.blocos(duracao)
    fio, convidado = "", ""
    assuntos: list[dict] = []
    for n, (a, b) in enumerate(bl, start=1):
        if progresso:
            progresso((n - 1) / max(1, len(bl)), f"IA entendendo a conversa: bloco {n} de {len(bl)}")
        prompt = prompt_mapa(n, len(bl), a, b, pack.compactar(pals, a, b), fio, contexto, origem, regras, regra_titulo)
        resp = chamar(adapter, prompt, SCHEMA_MAPA, cache, cancelar)
        if not isinstance(resp, dict):
            continue
        fio = str(resp.get("fio") or fio)[:FIO_MAX]
        convidado = str(resp.get("convidado") or convidado)
        for s in resp.get("assuntos") or []:
            item = _assunto_valido(s, pals, duracao, a, b, max_chars)
            if item:
                assuntos.append(item)
    # blocos se sobrepõem em 60 s: o mesmo assunto pode vir duas vezes
    assuntos = dedupe_overlapping([{**s, "nota": float(s["nota"])} for s in assuntos], ratio=0.6)
    assuntos.sort(key=lambda s: s["inicio"])
    for k, s in enumerate(assuntos, start=1):
        s["id"] = f"a{k:02d}"
    return {"fio": fio, "convidado": convidado, "assuntos": assuntos}


def _assunto_valido(s: Any, pals: list[dict], duracao: float, a: float, b: float, max_chars: int) -> dict | None:
    if not isinstance(s, dict):
        return None
    ini, fim = _num(s.get("inicio")), _num(s.get("fim"))
    if ini is None or fim is None or fim - ini < 10:
        return None
    ini, fim = max(0.0, ini), min(duracao, fim)
    if fim <= a or ini >= b + 300:  # fora do bloco (a conversa pode seguir um pouco além dele)
        return None
    ini, fim = snap_to_words(ini, fim, pals, duracao)
    texto = " ".join(w["texto"] for w in pals if ini - 0.01 <= w["inicio"] < fim - 0.01)
    if not texto:
        return None
    out = {
        "inicio": ini, "fim": fim, "assunto": str(s.get("assunto") or "").strip(), "tese": str(s.get("tese") or "").strip(),
        "angulo": str(s.get("angulo") or "").strip(),
        "gatilhos": [g for g in s.get("gatilhos") or [] if g in ANGULOS],
        "contexto": str(s.get("contexto") or "").strip(), "nota": int(max(0, min(100, _num(s.get("nota"), 50) or 0))),
        "thumb": str(s.get("thumb") or "").strip(),
        "titulos": titulos_com_prova(s.get("titulos"), texto, max_chars),
    }
    sh = s.get("short")
    if isinstance(sh, dict):
        si, sf = _num(sh.get("inicio")), _num(sh.get("fim"))
        if si is not None and sf is not None and sf > si:
            out["short"] = [max(ini, si), min(fim, sf)]
    tf = s.get("trecho_forte")
    if isinstance(tf, dict):
        ti, tfim = _num(tf.get("inicio")), _num(tf.get("fim"))
        if ti is not None and tfim is not None and 6 <= tfim - ti <= 25 and ini <= ti and tfim <= fim + 1:
            out["trecho_forte"] = [round(ti, 3), round(min(tfim, fim), 3)]
            out["frase_forte"] = str(tf.get("frase") or "")
    return out


def editar(mapa: dict, adapter: AdapterIA, regras: Regras, contexto: str, cache: CacheIA | None = None,
           cancelar: threading.Event | None = None) -> dict:
    """Passo 2: o editor-chefe compara o episódio inteiro (nota final) e junta assuntos em cortes longos."""
    assuntos = mapa.get("assuntos") or []
    if not assuntos:
        return {"assuntos": [], "longos": []}
    resp = chamar(adapter, prompt_editor(assuntos, mapa.get("fio", ""), mapa.get("convidado", ""), contexto, regras),
                  SCHEMA_EDITOR, cache, cancelar)
    return resp if isinstance(resp, dict) else {"assuntos": [], "longos": []}


def candidatos(mapa: dict, editor: dict, transcricao: dict, regras: Regras, adapter_nome: str,
               max_chars: int = 70) -> tuple[list[dict], list[dict]]:
    """Os Shorts e os cortes longos que saem dos assuntos, no formato dos candidatos locais."""
    from ..transcribe import palavras as _palavras

    pals = _palavras(transcricao)
    duracao = float(transcricao.get("duracao") or (pals[-1]["fim"] if pals else 0))
    frases = montar_frases(pals)
    notas = {str(r.get("id")): r for r in editor.get("assuntos") or [] if isinstance(r, dict)}
    por_id = {s["id"]: s for s in mapa.get("assuntos") or []}
    dur_ext = regras.teto_curto()
    curtos: list[dict] = []
    for s in por_id.values():
        r = notas.get(s["id"], {})
        nota = float(_num(r.get("nota"), s["nota"]) or 0)
        ini, fim = s.get("short") or (s["inicio"], s["fim"])
        ini, fim = ajustar_a_frases(ini, fim, frases, dur_ext, max(5.0, regras.duracao_min - 3))
        ini, fim = snap_to_words(ini, fim, pals, duracao)
        if not (regras.duracao_min - 3 <= fim - ini <= dur_ext + 1):
            continue
        texto = texto_do_trecho(transcricao, ini, fim)
        curtos.append(_cand(ini, fim, nota, texto, "curto", s, titulos_com_prova(_com_prova(s), texto, max_chars),
                            adapter_nome, str(r.get("motivo") or "")))
    longos: list[dict] = []
    ids = [s["id"] for s in sorted(por_id.values(), key=lambda s: s["inicio"])]
    for lg in editor.get("longos") or []:
        if not isinstance(lg, dict) or lg.get("de") not in por_id or lg.get("ate") not in por_id:
            continue
        i, j = ids.index(lg["de"]), ids.index(lg["ate"])
        if j < i:
            i, j = j, i
        partes = [por_id[x] for x in ids[i:j + 1]]
        ini, fim = snap_to_words(partes[0]["inicio"], partes[-1]["fim"], pals, duracao)
        if not (regras.corte_longo_min - 60 <= fim - ini <= regras.corte_longo_max + 60):
            continue
        texto = texto_do_trecho(transcricao, ini, fim)
        forte = max((p for p in partes if p.get("trecho_forte")), key=lambda p: p["nota"], default=None)
        base = {**forte, "thumb": str(lg.get("thumb") or (forte or {}).get("thumb") or "")} if forte else {
            "assunto": partes[0]["assunto"], "tese": partes[0]["tese"], "angulo": partes[0]["angulo"],
            "contexto": partes[0].get("contexto", ""), "thumb": str(lg.get("thumb") or "")}
        base["assunto"] = " + ".join(p["assunto"] for p in partes)
        tits = titulos_com_prova(lg.get("titulos"), texto, max_chars + 30) or [t for p in partes for t in p["titulos"]][:5]
        c = _cand(ini, fim, float(_num(lg.get("nota"), 60) or 0), texto, "longo", base, tits, adapter_nome,
                  str(lg.get("motivo") or ""))
        if forte:
            c["ia"]["abertura"] = [forte["trecho_forte"]]
            c["ia"]["frase_forte"] = forte.get("frase_forte", "")
        longos.append(c)
    return curtos, dedupe_overlapping(longos, ratio=0.5)


def _com_prova(s: dict) -> list[dict]:
    """Os títulos do assunto já passaram pela prova contra o assunto inteiro; para o Short, a prova é o próprio
    título contra o texto menor (a tese entra como prova de reserva)."""
    return [{"titulo": t, "prova": s.get("tese") or t} for t in s.get("titulos") or []]


def _cand(ini: float, fim: float, nota: float, texto: str, modo: str, s: dict, titulos: list[str], agente: str,
          motivo_editor: str) -> dict:
    motivo = " ".join(x for x in (s.get("angulo", ""), motivo_editor) if x).strip()
    return {
        "inicio": ini, "fim": fim, "duracao": round(fim - ini, 2), "nota": nota, "sinais": {},
        "motivos": [motivo] if motivo else [], "texto": texto, "modo": modo, "fonte": "ia-assuntos",
        "titulos": titulos,
        "ia": {"agente": agente, "motivo": motivo, "gancho": s.get("thumb", ""), "destaques": [],
               "assunto": s.get("assunto", ""), "tese": s.get("tese", ""), "contexto": s.get("contexto", ""),
               "gatilhos": s.get("gatilhos", []), "fecha_assunto": True},
    }
