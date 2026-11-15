"""Títulos sem IA (fórmulas do titulos.md), trava do título e censor leetspeak."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Collection, Mapping

from .textutil import STOPWORDS, contem_termo, normalizar, tokens

LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5"}
_NUM_RE = re.compile(r"(R\$\s?)?\d[\d.,]*\s?(mil|milh[õo]es|bilh[õo]es|%|reais|k)?", re.IGNORECASE)
_NOME_RE = re.compile(r"\b([A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõç]+(?:\s[A-ZÁÉÍÓÚÂÊÔÃÕ][a-záéíóúâêôãõç]+)?)\b")


# palavras de fala que passam pelas stopwords mas não servem de tema de título
TEMA_FRACO = {
    "pode", "posso", "podia", "olha", "sabe", "sabia", "vamos", "vai", "dele", "dela", "deles", "delas", "contra",
    "pessoas", "pessoa", "mundo", "coisa", "coisas", "gente", "aqui", "assim", "entao", "então", "porque", "tava",
    "estava", "fazer", "falar", "falou", "tudo", "nada", "muito", "muita", "agora", "hoje", "sempre", "nunca", "outro",
    "outra", "mesmo", "mesma", "acho", "achei", "cara", "tipo", "fica", "ficou", "quer", "queria", "dizer", "disse",
    "fala", "falando", "verdade", "certo", "claro", "teve", "tinha", "foram", "seria", "isso", "essa", "esse",
    "caras", "meio", "qualquer", "algum", "alguma", "nenhum", "nenhuma", "todos", "todas", "cada", "vezes", "parte",
}


TEMPERATURAS = ("morno", "quente", "fervendo")
DESCRICAO_TEMPERATURA = {
    "morno": "informativo e direto: diz o assunto e o ganho, sem exagero nem caixa alta de emoção",
    "quente": "gancho claro: conflito, revelação ou número que surpreende, com uma ou duas palavras em CAIXA ALTA",
    "fervendo": "no limite do clickbait honesto: reação forte, confronto, choque; tudo o que promete acontece no clip",
}


def formulas_do_canal(tmeta: Mapping) -> list[str]:
    """As fórmulas do titulos.md na ordem de uso: as do usuário (formulas), depois as da temperatura
    escolhida e a vizinha mais fria (fervendo puxa quente; quente puxa morno)."""
    out: list[str] = list(tmeta.get("formulas") or [])
    por = tmeta.get("formulas_por_temperatura") or {}
    temp = str(tmeta.get("temperatura") or "quente")
    if temp in TEMPERATURAS and isinstance(por, Mapping):
        i = TEMPERATURAS.index(temp)
        for t in (temp, TEMPERATURAS[i - 1] if i else None):
            if t:
                out += [f for f in (por.get(t) or []) if isinstance(f, str)]
    vistos: set[str] = set()
    return [f for f in out if not (f in vistos or vistos.add(f))]


def frequencias(blocos: list[str]) -> tuple[Counter, int]:
    """Em quantos blocos (segmentos) do vídeo cada termo aparece, para pesar o quanto ele é específico."""
    df: Counter[str] = Counter()
    for b in blocos:
        df.update({t for t in tokens(b) if t not in STOPWORDS and len(t) > 3 and not t.isdigit()})
    return df, len(blocos)


def _grafia(texto: str, termo: str) -> str:
    """O termo com a grafia que aparece no texto (Flávio, não flávio)."""
    alvo = normalizar(termo)
    for p in texto.split():
        if normalizar(p) == alvo:
            return p.strip(".,!?;:\"'()[]…-–—")
    return termo


def tema_do_trecho(texto: str, extras: list[str] | None = None, df: Mapping[str, int] | None = None,
                   n_blocos: int = 0, evitar: Collection[str] = ()) -> str:
    """O assunto do trecho: o termo que mais aparece nele e menos no resto do vídeo (tf-idf).

    `evitar` tira termos que estão em quase todos os candidatos (o nome do convidado, por exemplo),
    para os títulos não saírem todos iguais.
    """
    evitar_n = {normalizar(e) for e in evitar} | TEMA_FRACO

    def idf(t: str) -> float:
        return math.log(1 + n_blocos / (1 + df.get(t, 0))) if df and n_blocos else 1.0

    cont = Counter(t for t in tokens(texto) if t not in STOPWORDS and len(t) > 3 and not t.isdigit()
                   and normalizar(t) not in evitar_n)
    texto_n = " " + " ".join(normalizar(t) for t in texto.split()) + " "
    presentes = [e for e in (extras or []) if contem_termo(texto_n, e) and normalizar(e) not in evitar_n]
    if presentes:
        return _grafia(texto, max(presentes, key=lambda e: texto_n.count(normalizar(e)) * idf(e.lower())))
    if not cont:
        return "isso"
    melhor = max(cont, key=lambda t: cont[t] * idf(t))
    return _expressao(texto, melhor, evitar_n) or _grafia(texto, melhor)


_LIGA = {"de", "do", "da", "dos", "das", "of"}
_PONTUACAO = ".,!?;:\"'()[]…-–—"


def _expressao(texto: str, termo: str, evitar_n: Collection[str] = ()) -> str | None:
    """O termo dentro da expressão em que ele aparece de novo e de novo ("mercado financeiro",
    "Copa do Mundo"): um título sobre "mercado" diz menos que um sobre "mercado financeiro".

    Vale a expressão de duas palavras de conteúdo (com "de/do/da" no meio ou não) que se repete pelo
    menos duas vezes no trecho, sem pontuação entre elas.
    """
    alvo = normalizar(termo)
    palavras = texto.split()

    def conteudo(p: str) -> bool:
        n = normalizar(p)
        return len(n) > 3 and n not in STOPWORDS and n not in evitar_n and not n.isdigit()

    cont: Counter[tuple[str, ...]] = Counter()
    grafia: dict[tuple[str, ...], str] = {}
    for i in range(len(palavras) - 1):
        for tam in (2, 3):
            pedaco = palavras[i:i + tam]
            if len(pedaco) < tam or any(p[-1:] in _PONTUACAO for p in pedaco[:-1]):
                continue
            if tam == 3 and normalizar(pedaco[1]) not in _LIGA:
                continue
            a, b = pedaco[0], pedaco[-1]
            if not (conteudo(a) and conteudo(b)) or alvo not in (normalizar(a), normalizar(b)):
                continue
            chave = tuple(normalizar(p) for p in pedaco)
            cont[chave] += 1
            grafia.setdefault(chave, " ".join(p.strip(_PONTUACAO) for p in pedaco))
    if not cont:
        return None
    chave, n = cont.most_common(1)[0]
    return grafia[chave] if n >= 2 else None


def termos_comuns(textos: list[str], fracao: float = 0.5) -> set[str]:
    """Termos presentes em mais de `fracao` dos trechos: não distinguem um corte do outro."""
    if len(textos) < 3:
        return set()
    cont: Counter[str] = Counter()
    for tx in textos:
        cont.update({normalizar(t) for t in tokens(tx) if t not in STOPWORDS and len(t) > 3})
    return {t for t, c in cont.items() if c > fracao * len(textos)}


def numero_do_trecho(texto: str) -> str | None:
    m = _NUM_RE.search(texto)
    return m.group(0).strip() if m else None


def nome_do_trecho(texto: str) -> str | None:
    # ignora a primeira palavra de cada frase (maiúscula por pontuação)
    frases = re.split(r"[.!?]\s+", texto)
    for f in frases:
        partes = f.split(maxsplit=1)
        if len(partes) < 2:
            continue
        m = _NOME_RE.search(partes[1])
        if m and normalizar(m.group(1)) not in STOPWORDS:
            return m.group(1)
    return None


def _caixa_alta(titulo: str, n: int) -> str:
    """Garante no máximo n palavras em CAIXA ALTA (as das fórmulas)."""
    palavras = titulo.split()
    caps = [i for i, p in enumerate(palavras) if len(p) > 1 and p.isupper()]
    for i in caps[n:]:
        palavras[i] = palavras[i].capitalize()
    return " ".join(palavras)


def censurar(texto: str, palavras: list[str]) -> str:
    """Censor leetspeak opcional: VIOLÊNCIA -> VIOL3NCIA."""
    out = texto
    for p in palavras:
        if not p.strip():
            continue

        def troca(m: re.Match) -> str:
            w = m.group(0)
            # troca uma vogal só, de preferência o E (VIOLÊNCIA -> VIOL3NCIA)
            for alvo in ("e", "a", "o", "i", "s"):
                for i, ch in enumerate(w):
                    if i > 0 and normalizar(ch) == alvo:
                        return w[:i] + LEET[alvo] + w[i + 1 :]
            return w

        out = re.sub(rf"\b{re.escape(p)}\b", troca, out, flags=re.IGNORECASE)
    return out


def titulos_locais(texto: str, formulas: list[str], palavras_chave: list[str] | None = None,
                   max_caracteres: int = 70, palavras_caixa_alta: int = 2, quantidade: int = 5,
                   inicio: int = 0, df: Mapping[str, int] | None = None, n_blocos: int = 0,
                   evitar: Collection[str] = (), ja_usados: Collection[str] = (),
                   caixa_alta_total: bool = False) -> list[str]:
    """Títulos pelas fórmulas do titulos.md.

    `caixa_alta_total` (chave do titulos.md) põe o título inteiro em CAIXA ALTA, o padrão de muitos
    canais de cortes; senão, no máximo `palavras_caixa_alta` palavras ficam em maiúsculas.

    `inicio` gira as fórmulas (o candidato i começa pela fórmula i) e `ja_usados` são os títulos
    principais de outros candidatos: o primeiro título nunca repete um deles quando há alternativa.
    """
    tema = tema_do_trecho(texto, palavras_chave, df, n_blocos, evitar)
    numero = numero_do_trecho(texto)
    nome = nome_do_trecho(texto)
    if nome and normalizar(nome) in {normalizar(e) for e in evitar}:
        nome = None
    out: list[str] = []
    k = inicio % len(formulas) if formulas else 0
    for f in formulas[k:] + formulas[:k]:
        if "{numero}" in f and not numero:
            continue
        if "{nome}" in f and (not nome or ("{tema}" in f and normalizar(nome) == normalizar(tema))):
            continue
        t = f.format(tema=tema, numero=numero or "", nome=nome or "", verbo="FALA")
        t = re.sub(r"\s+", " ", t).strip()
        t = t.upper() if caixa_alta_total else _caixa_alta(t, palavras_caixa_alta)
        t = t[:1].upper() + t[1:]
        if len(t) > max_caracteres:
            t = t[: max_caracteres - 1].rsplit(" ", 1)[0] + "…"
        if t not in out:
            out.append(t)
        if len(out) >= quantidade:
            break
    if not out:
        t = f"{tema.upper()}: o que ninguém te conta"
        out.append(t.upper() if caixa_alta_total else _caixa_alta(t, palavras_caixa_alta))
    novo = next((t for t in out if t not in ja_usados), None)
    if novo and novo != out[0]:
        out.remove(novo)
        out.insert(0, novo)
    return out


def respeita_trava(titulo: str, texto_clip: str) -> bool:
    """Trava do título: algo concreto que o título promete precisa aparecer no clip.

    Heurística local: pelo menos uma palavra de conteúdo do título (ou o número
    citado) aparece na transcrição do clip.
    """
    conteudo = [t for t in tokens(titulo) if t not in STOPWORDS and len(t) > 3]
    if not conteudo:
        return True
    texto_n = " " + " ".join(normalizar(t) for t in tokens(texto_clip)) + " "
    if any(f" {normalizar(t)} " in texto_n for t in conteudo):
        return True
    num = numero_do_trecho(titulo)
    return bool(num and re.sub(r"\D", "", num) and re.sub(r"\D", "", num) in re.sub(r"\D", "", texto_clip))
