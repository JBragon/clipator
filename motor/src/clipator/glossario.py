"""Glossário do canal: nomes próprios que o Whisper costuma errar.

Duas partes, as duas locais e sem IA:

1. Antes de transcrever, os termos vão para o faster-whisper como `hotwords`
   (valem em toda janela de 30 s, ao contrário do initial_prompt).
2. Depois, uma passada troca palavras que SOAM como um termo do glossário
   ("Vorcano" -> "Vorcaro", "flavio" -> "Flávio"), mantendo os tempos de cada
   palavra e registrando cada troca. A palavra original fica em "original".

A chave fonética é uma simplificação do português feita aqui (dígrafos, c/s/z,
k/q, h mudo, letras dobradas); não é um algoritmo publicado.
"""

from __future__ import annotations

import re
from typing import Any

from .textutil import STOPWORDS, normalizar

# o hotwords entra no prompt do Whisper, que tem por volta de 224 tokens: fica bem abaixo disso
LIMITE_HOTWORDS = 220  # caracteres
_PONTUACAO = ".,!?:;\"'()…-–—"


def termos(glossario: list[str] | None) -> list[str]:
    """Termos limpos, sem repetição, na ordem em que o usuário escreveu (os primeiros pesam mais)."""
    vistos, out = set(), []
    for t in glossario or []:
        t = re.sub(r"\s+", " ", str(t)).strip()
        if t and normalizar(t) not in vistos:
            vistos.add(normalizar(t))
            out.append(t)
    return out


def hotwords(glossario: list[str] | None, limite: int = LIMITE_HOTWORDS) -> str | None:
    """Os termos que cabem no limite, separados por vírgula, para o faster-whisper."""
    partes: list[str] = []
    for t in termos(glossario):
        if len(", ".join(partes + [t])) > limite:
            break
        partes.append(t)
    return ", ".join(partes) or None


def chave_fonetica(palavra: str) -> str:
    """Como a palavra soa, de forma aproximada, em português."""
    s = normalizar(palavra).replace("ç", "s")
    s = re.sub(r"[^a-z]", "", s)
    if not s:
        return ""
    for de, para in (("ph", "f"), ("ch", "x"), ("sh", "x"), ("lh", "li"), ("nh", "ni"), ("qu", "k"), ("gu", "g"),
                     ("ck", "k"), ("th", "t"), ("y", "i"), ("w", "v"), ("k", "k")):
        s = s.replace(de, para)
    s = re.sub(r"c(?=[ei])", "s", s)
    s = s.replace("c", "k").replace("q", "k").replace("z", "s")
    s = re.sub(r"^h", "", s)
    s = s.replace("h", "")
    s = re.sub(r"(.)\1+", r"\1", s)  # letras dobradas
    s = re.sub(r"m$", "n", s)  # "ão"/"am" no fim soam igual
    return s


def _distancia(a: str, b: str) -> int:
    if a == b:
        return 0
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def parecido(palavra: str, termo: str) -> bool:
    """A palavra soa como o termo? Palavras curtas precisam soar igual; longas aceitam 1 ou 2 letras."""
    a, b = chave_fonetica(palavra), chave_fonetica(termo)
    if not a or not b or a[0] != b[0]:
        return False
    if a == b:
        return True
    n = max(len(a), len(b))
    if n <= 5:
        return False  # "luta" não vira "Lula"
    limite = 1 if n <= 8 else 2
    return abs(len(a) - len(b)) <= limite and _distancia(a, b) <= limite


def _limpa(p: str) -> tuple[str, str, str]:
    """(pontuação antes, palavra, pontuação depois)."""
    m = re.match(rf"^([{re.escape(_PONTUACAO)}]*)(.*?)([{re.escape(_PONTUACAO)}]*)$", p)
    return (m.group(1), m.group(2), m.group(3)) if m else ("", p, "")


def corrigir_palavras(palavras: list[dict], glossario: list[str] | None) -> list[dict[str, Any]]:
    """Troca no lugar as palavras (ou sequências) que soam como um termo. Devolve as trocas feitas."""
    lista = termos(glossario)
    if not lista or not palavras:
        return []
    # termos com várias palavras ("Flávio Bolsonaro") primeiro; cada palavra longa do termo também vale sozinha
    candidatos: list[list[str]] = []
    for t in sorted(lista, key=lambda x: -len(x.split())):
        partes = t.split()
        candidatos.append(partes)
        if len(partes) > 1:
            candidatos += [[p] for p in partes if len(normalizar(p)) >= 5]
    trocas: list[dict[str, Any]] = []
    i = 0
    while i < len(palavras):
        feito = False
        for partes in candidatos:
            n = len(partes)
            janela = palavras[i: i + n]
            if len(janela) < n:
                continue
            pedacos = [_limpa(w["texto"]) for w in janela]
            nucleos = [p[1] for p in pedacos]
            if any(not x or normalizar(x) in STOPWORDS or len(normalizar(x)) < 3 for x in nucleos):
                continue
            if all(x == alvo for x, alvo in zip(nucleos, partes)):
                break  # já está certo
            if not all(parecido(x, alvo) for x, alvo in zip(nucleos, partes)):
                continue
            antes = " ".join(w["texto"] for w in janela)
            for w, (pre, _, pos), alvo in zip(janela, pedacos, partes):
                w.setdefault("original", w["texto"])
                w["texto"] = f"{pre}{alvo}{pos}"
            trocas.append({"de": antes, "para": " ".join(w["texto"] for w in janela), "inicio": janela[0]["inicio"]})
            i += n
            feito = True
            break
        if not feito:
            i += 1
    return trocas


def corrigir_transcricao(transcricao: dict, glossario: list[str] | None) -> tuple[dict, list[dict[str, Any]]]:
    """Aplica o glossário em todos os segmentos e refaz o texto de cada um. Os tempos não mudam."""
    trocas_total: list[dict[str, Any]] = []
    for seg in transcricao.get("segmentos", []):
        pals = seg.get("palavras") or []
        trocas = corrigir_palavras(pals, glossario)
        if trocas:
            seg.setdefault("texto_original", seg.get("texto", ""))
            seg["texto"] = " ".join(w["texto"] for w in pals)
            trocas_total += trocas
    transcricao["correcoes_nomes"] = (transcricao.get("correcoes_nomes") or []) + trocas_total
    return transcricao, trocas_total
