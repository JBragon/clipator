"""Transcrição compactada em frases com [início-fim], o formato barato para mandar à IA.

Adaptado de video-use/helpers/pack_transcripts.py (group_into_phrases), MIT
License, Copyright (c) 2026 Browser Use. Ver THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations


def frases(palavras: list[dict], pausa: float = 0.5) -> list[dict]:
    """Quebra em pausa >= `pausa` s ou troca de falante."""
    out: list[dict] = []
    atual: list[dict] = []
    for w in palavras:
        if atual:
            gap = w["inicio"] - atual[-1]["fim"]
            troca = w.get("falante") is not None and w.get("falante") != atual[-1].get("falante")
            if gap >= pausa or troca:
                out.append(_fechar(atual))
                atual = []
        atual.append(w)
    if atual:
        out.append(_fechar(atual))
    return out


def _fechar(ws: list[dict]) -> dict:
    texto = " ".join(w["texto"] for w in ws)
    for p in (" ,", " .", " ?", " !"):
        texto = texto.replace(p, p.strip())
    return {"inicio": ws[0]["inicio"], "fim": ws[-1]["fim"], "texto": texto, "falante": ws[0].get("falante")}


def compactar(palavras: list[dict], inicio: float | None = None, fim: float | None = None, pausa: float = 0.5) -> str:
    sel = [w for w in palavras if (inicio is None or w["inicio"] >= inicio - 0.01) and (fim is None or w["inicio"] < fim)]
    linhas = []
    for f in frases(sel, pausa):
        quem = f"S{f['falante']} " if f.get("falante") is not None else ""
        linhas.append(f"[{f['inicio']:.1f}-{f['fim']:.1f}] {quem}{f['texto']}")
    return "\n".join(linhas)


def blocos(duracao: float, tamanho: float = 1200.0, sobreposicao: float = 60.0) -> list[tuple[float, float]]:
    """Blocos sobrepostos para o modo completo em vídeos longos.

    Mesma ideia de chunk_transcript em AI-Youtube-Shorts-Generator (MIT).
    """
    out, ini = [], 0.0
    while ini < duracao:
        fim = min(duracao, ini + tamanho)
        out.append((ini, fim))
        if fim >= duracao:
            break
        ini = fim - sobreposicao
    return out
