"""Camada 2 da detecção (opcional): a IA reordena os candidatos e sugere títulos.

Uma única chamada recebe os melhores candidatos (texto, duração, nota local e o
corpo do regras.md) e devolve JSON: nota, títulos, gancho, ajuste de início e
fim e o motivo. No modo completo, a IA lê a transcrição inteira em blocos e
pode propor trechos que as heurísticas perderam.
"""

from __future__ import annotations

import threading
from typing import Any

from .. import pack
from ..candidates import ajustar_a_frases, dedupe_overlapping, montar_frases, snap_to_words, texto_do_trecho
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
                    "titulos": {"type": "array", "items": {"type": "string"}},
                    "gancho": {"type": "string", "description": "Frase de gancho de até 40 caracteres por linha, 2 linhas"},
                    "ajuste_inicio": {"type": "number", "description": "Segundos para somar ao início (negativo antecipa)"},
                    "ajuste_fim": {"type": "number", "description": "Segundos para somar ao fim"},
                    "fecha_assunto": {"type": "boolean", "description": "Com o ajuste, o trecho fecha a ideia"},
                    "motivo": {"type": "string"},
                    "destaques": {"type": "array", "items": {"type": "string"}, "description": "Palavras do trecho para destacar na legenda"},
                },
                "required": ["id", "nota", "titulos", "gancho", "ajuste_inicio", "ajuste_fim", "fecha_assunto", "motivo",
                             "destaques"],
            },
        }
    },
    "required": ["candidatos"],
}

SCHEMA_COMPLETO: dict[str, Any] = {
    "type": "object",
    "properties": {
        "trechos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio": {"type": "number"},
                    "fim": {"type": "number"},
                    "nota": {"type": "integer", "minimum": 0, "maximum": 100},
                    "titulos": {"type": "array", "items": {"type": "string"}},
                    "gancho": {"type": "string"},
                    "motivo": {"type": "string"},
                },
                "required": ["inicio", "fim", "nota", "titulos", "gancho", "motivo"],
            },
        }
    },
    "required": ["trechos"],
}

SCHEMA_TITULOS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titulos": {"type": "array", "items": {"type": "string"}},
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
    return r


def prompt_ranking(cands: list[dict], contexto: str, regra_titulo: str, dur_max: float = 60, dur_ext: float = 90) -> str:
    linhas = [
        "Você é o editor de um canal de cortes. Avalie os trechos candidatos de um vídeo longo e",
        "responda só com o JSON do schema.",
        "",
        RUBRICA,
        "",
        regra_titulo,
        "",
        "ajuste_inicio e ajuste_fim: o corte precisa FECHAR O ASSUNTO. Comece no início de uma frase e inclua",
        "a pergunta ou o contexto de que o trecho depende (ajuste_inicio de -15 a 5 s). Termine depois da",
        "conclusão da ideia, nunca no meio de uma frase nem numa pergunta cuja resposta vem logo depois",
        f"(ajuste_fim de -5 a {dur_ext - dur_max:.0f} s). Um Short tem até {dur_max:.0f} s; pode ir até {dur_ext:.0f} s",
        "só se for para fechar o assunto. Use 0 se já estiver bom.",
        "fecha_assunto: true se, com o ajuste, o trecho tem começo, meio e fim (a ideia se conclui).",
        "",
        contexto,
        "",
        "## Candidatos",
    ]
    for c in cands:
        linhas.append(f"### {c['id']} ({c['duracao']:.0f} s, nota local {c['nota']:.0f})")
        linhas.append(c.get("texto_compacto") or c.get("texto", ""))
        linhas.append("")
    return "\n".join(linhas)


def ranquear(cands: list[dict], transcricao: dict, adapter: AdapterIA, regras: Regras, canal_md: str = "",
             regras_md: str = "", titulos_md: str = "", titulos_meta: dict | None = None, cache: CacheIA | None = None,
             cancelar: threading.Event | None = None) -> list[dict]:
    """Modo econômico: a IA só vê os N melhores candidatos locais."""
    from ..transcribe import palavras as _palavras

    titulos_meta = titulos_meta or {}
    pals = _palavras(transcricao)
    top = sorted(cands, key=lambda c: -c["nota"])[: regras.candidatos_para_ia]
    for c in top:
        c["texto_compacto"] = pack.compactar(pals, c["inicio"], c["fim"])
    contexto = _contexto_canal(canal_md, regras_md, titulos_md, regras, titulos_meta)
    dur_ext = max(regras.duracao_max, regras.duracao_max_fechamento)
    prompt = prompt_ranking(top, contexto, _regra_titulo(titulos_meta, regras.trava_titulo), regras.duracao_max, dur_ext)
    frases = montar_frases(pals)
    resp = chamar(adapter, prompt, SCHEMA_RANKING, cache, cancelar)
    por_id = {r.get("id"): r for r in (resp or {}).get("candidatos", []) if isinstance(r, dict)}
    duracao = float(transcricao.get("duracao") or 0)
    out = []
    for c in cands:
        c = dict(c)
        c.pop("texto_compacto", None)
        r = por_id.get(c["id"])
        if r:
            longo = c.get("modo") == "longo"
            teto = regras.corte_longo_max if longo else dur_ext
            ai = max(-15.0, min(5.0, float(r.get("ajuste_inicio") or 0)))
            af = max(-5.0, min(max(0.0, teto - c["duracao"]), float(r.get("ajuste_fim") or 0)))
            if ai or af:
                # o ajuste da IA vai para fronteiras de frase: começa numa frase e termina numa que fecha
                ini, fim = ajustar_a_frases(c["inicio"] + ai, c["fim"] + af, frases, teto)
                ini, fim = snap_to_words(ini, fim, pals, duracao)
                if 5 <= fim - ini <= teto + 1:
                    c["ajuste_ia"] = {"inicio": round(ini - c["inicio"], 2), "fim": round(fim - c["fim"], 2)}
                    c["inicio"], c["fim"], c["duracao"] = ini, fim, round(fim - ini, 2)
                    c["texto"] = texto_do_trecho(transcricao, ini, fim)
            c["nota_local"] = c["nota"]
            c["nota"] = float(r.get("nota", c["nota"]))
            c["ia"] = {"agente": adapter.nome, "motivo": r.get("motivo", ""), "gancho": r.get("gancho", ""),
                       "destaques": r.get("destaques", []), "fecha_assunto": bool(r.get("fecha_assunto", True))}
            if r.get("fecha_assunto") is False:  # a própria IA diz que a ideia ficou aberta
                c["nota"] = max(0.0, c["nota"] - 8)
            if r.get("titulos"):
                c["titulos"] = [t for t in r["titulos"] if isinstance(t, str) and t.strip()][:5]
            c["fonte"] = "local+ia"
        out.append(c)
    out.sort(key=lambda c: -c["nota"])
    return out


def completo(transcricao: dict, cands_locais: list[dict], adapter: AdapterIA, regras: Regras, canal_md: str = "",
             regras_md: str = "", titulos_md: str = "", titulos_meta: dict | None = None, cache: CacheIA | None = None,
             cancelar: threading.Event | None = None, progresso=None) -> list[dict]:
    """Modo completo: a IA lê a transcrição inteira em blocos e propõe trechos."""
    from ..transcribe import palavras as _palavras

    titulos_meta = titulos_meta or {}
    pals = _palavras(transcricao)
    duracao = float(transcricao.get("duracao") or (pals[-1]["fim"] if pals else 0))
    contexto = _contexto_canal(canal_md, regras_md, titulos_md, regras, titulos_meta)
    regra_t = _regra_titulo(titulos_meta, regras.trava_titulo)
    frases = montar_frases(pals)
    dur_ext = max(regras.duracao_max, regras.duracao_max_fechamento)
    novos: list[dict] = []
    bl = pack.blocos(duracao)
    for n, (a, b) in enumerate(bl):
        if progresso:
            progresso(n / len(bl), f"IA lendo bloco {n + 1} de {len(bl)}")
        prompt = "\n".join([
            "Você é o editor de um canal de cortes. Leia este trecho da transcrição e proponha os melhores",
            f"momentos para clips de {regras.duracao_min:.0f} a {regras.duracao_max:.0f} s. Use os tempos [início-fim]",
            "das linhas; cada clip começa e termina em frase completa e FECHA O ASSUNTO: inclui a pergunta ou o",
            "contexto de que depende e termina depois da conclusão, nunca numa pergunta sem a resposta. Pode",
            f"passar de {regras.duracao_max:.0f} s até {dur_ext:.0f} s só para fechar a ideia. Responda só com o JSON do schema.",
            "", RUBRICA, "", regra_t, "", contexto, "", "## Transcrição", pack.compactar(pals, a, b),
        ])
        resp = chamar(adapter, prompt, SCHEMA_COMPLETO, cache, cancelar)
        for t in (resp or {}).get("trechos", []):
            try:
                ini, fim = float(t["inicio"]), float(t["fim"])
            except (KeyError, TypeError, ValueError):
                continue
            ini, fim = ajustar_a_frases(ini, fim, frases, dur_ext)
            ini, fim = snap_to_words(ini, fim, pals, duracao)
            if not (regras.duracao_min - 3 <= fim - ini <= dur_ext + 1):
                continue
            novos.append({
                "inicio": ini, "fim": fim, "duracao": round(fim - ini, 2), "nota": float(t.get("nota", 50)),
                "sinais": {}, "motivos": [t.get("motivo", "")], "texto": texto_do_trecho(transcricao, ini, fim),
                "modo": "curto", "fonte": "ia", "titulos": [x for x in t.get("titulos", []) if isinstance(x, str)][:5],
                "ia": {"agente": adapter.nome, "motivo": t.get("motivo", ""), "gancho": t.get("gancho", ""), "destaques": []},
            })
    todos = dedupe_overlapping(novos + [dict(c) for c in cands_locais], ratio=0.25)
    for n, c in enumerate(todos, start=1):
        c["id"] = f"c{n:02d}"
    return todos


def sugerir_titulos(texto_clip: str, adapter: AdapterIA, contexto: str, titulos_meta: dict, trava: bool,
                    cache: CacheIA | None = None, cancelar: threading.Event | None = None) -> dict:
    """Botão "gerar outros": chamada curta só daquele clip."""
    prompt = "\n".join([
        "Sugira títulos para este clip de um canal de cortes. Responda só com o JSON do schema.",
        "", _regra_titulo(titulos_meta, trava), "", contexto, "", "## Transcrição do clip", texto_clip,
    ])
    return chamar(adapter, prompt, SCHEMA_TITULOS, cache, cancelar)
