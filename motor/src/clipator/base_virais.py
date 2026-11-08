"""Base de referência dos cortes virais: o que a pesquisa de 75 canais de cortes brasileiros ensinou
(docs/pesquisa-titulos-e-thumbnails.md), embutido no Clipator e aplicado a todo canal.

Nada aqui depende de o usuário escolher um nicho. O tema de cada vídeo é detectado pela transcrição
(palavras de temas.md) e o motor usa a seção geral mais as dos temas encontrados:

- títulos sem IA: as fórmulas do tema na temperatura do canal (ou na do tema, se o canal deixa `auto`);
- IA: como cortar, padrões de título e de thumbnail e títulos reais mais vistos, como régua de tom;
- o que o canal fixa nos arquivos de regras-e-textos/ sempre vale por cima da base.

Os arquivos ficam em dados/base-virais/ e são lidos a cada uso, então uma atualização do Clipator
melhora todos os canais, inclusive os antigos.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import markdown as md
from .textutil import sem_acento, tokens

GERAL = "geral"
_SECAO = re.compile(r"^## (.+?)\s*\((\w[\w-]*)\)\s*$", re.MULTILINE)
# temperatura "auto" (ou ausente) no titulos.md do canal: vale a do tema do vídeo
AUTO = "auto"


def base_dir() -> Path:
    from .workspace import _dados

    return _dados("base-virais")


@lru_cache(maxsize=8)
def _ler(nome: str) -> md.MarkdownDoc:
    p = base_dir() / nome
    return md.read(p) if p.exists() else md.MarkdownDoc()


def temas() -> dict[str, dict[str, Any]]:
    """id -> {nome, temperatura, caixa_alta_total, palavras_caixa_alta, palavras, censurar}."""
    return dict(_ler("temas.md").meta.get("temas") or {})


def secoes(nome: str) -> dict[str, str]:
    """As seções `## Título (id)` de um arquivo da base, juntadas por id (pode haver mais de uma)."""
    corpo = _ler(nome).body
    marcas = list(_SECAO.finditer(corpo))
    out: dict[str, str] = {}
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(corpo)
        texto = corpo[m.start():fim].strip()
        out[m.group(2)] = (out[m.group(2)] + "\n\n" + texto) if m.group(2) in out else texto
    return out


def _bate(token: str, palavra: str) -> bool:
    return token.startswith(palavra[:-1]) if palavra.endswith("*") else token == palavra


def detectar(texto: str, maximo: int = 2) -> list[str]:
    """Os temas do texto (mais forte primeiro), pelas palavras de temas.md. Lista vazia = só o geral.

    Um tema entra com pelo menos 5 ocorrências e 2 a cada mil palavras; o segundo só entra se tiver
    pelo menos metade das ocorrências do primeiro (um vídeo de política que cita futebol uma vez continua
    sendo de política)."""
    toks = [sem_acento(t) for t in tokens(texto)]
    if not toks:
        return []
    cont = Counter(toks)
    pontos: dict[str, int] = {}
    for tid, t in temas().items():
        palavras = [sem_acento(str(p).lower()) for p in t.get("palavras") or []]
        if not palavras:
            continue
        exatas = {p for p in palavras if not p.endswith("*")}
        prefixos = [p for p in palavras if p.endswith("*")]
        n = sum(c for tok, c in cont.items() if tok in exatas or any(_bate(tok, p) for p in prefixos))
        if n >= 5 and n * 1000 / len(toks) >= 2:
            pontos[tid] = n
    ordem = sorted(pontos, key=lambda k: -pontos[k])
    return [k for k in ordem[:maximo] if pontos[k] * 2 >= pontos[ordem[0]]]


def texto_da_transcricao(trans: Mapping | None) -> str:
    return " ".join(str(s.get("texto", "")) for s in (trans or {}).get("segmentos", []))


def nomes(ids: Iterable[str]) -> list[str]:
    t = temas()
    return [str(t.get(i, {}).get("nome") or i) for i in ids]


def _unicos(itens: Iterable[Any]) -> list[Any]:
    vistos: set[str] = set()
    out = []
    for x in itens:
        chave = str(x).strip().lower()
        if chave and chave not in vistos:
            vistos.add(chave)
            out.append(x)
    return out


def titulos_efetivos(tmeta_canal: Mapping, ids: list[str]) -> dict[str, Any]:
    """O titulos.md do canal completado pela base nos temas do vídeo.

    - `temperatura`: a do canal; se for `auto` (ou faltar), a do primeiro tema, senão a do geral.
    - `caixa_alta_total` e `palavras_caixa_alta`: as do canal quando ele fixa; senão as do tema.
    - fórmulas: as do canal primeiro, depois as dos temas e as do geral (as 10 fórmulas genéricas
      que os canais antigos receberam vão para o fim, para não abafar as da base).
    - `palavras_gatilho` e `nunca_usar`: as do canal somadas às da base.
    """
    from .workspace import FORMULAS_PADRAO

    t = temas()
    ordem = [i for i in ids if i in t and i != GERAL] + ([GERAL] if GERAL in t else [])
    principal = t.get(ordem[0], {}) if ordem else {}
    out: dict[str, Any] = dict(tmeta_canal)

    temp = str(tmeta_canal.get("temperatura") or AUTO)
    if temp == AUTO:
        out["temperatura"] = str(principal.get("temperatura") or "quente")
    for chave in ("caixa_alta_total", "palavras_caixa_alta"):
        if chave not in tmeta_canal and chave in principal:
            out[chave] = principal[chave]

    proprias = list(tmeta_canal.get("formulas") or [])
    genericas: list[str] = []
    if proprias == FORMULAS_PADRAO:
        proprias, genericas = [], proprias
    out["formulas"] = proprias

    meta_base = _ler("titulos.md").meta
    por_tema = meta_base.get("formulas") or {}
    por: dict[str, list[str]] = {}
    for fonte in [tmeta_canal.get("formulas_por_temperatura") or {}] + [por_tema.get(i) or {} for i in ordem]:
        for temperatura, lista in (fonte or {}).items():
            por.setdefault(str(temperatura), []).extend(f for f in lista or [] if isinstance(f, str))
    if genericas:
        por.setdefault("morno", []).extend(genericas)
    out["formulas_por_temperatura"] = {k: _unicos(v) for k, v in por.items()}

    gat = meta_base.get("palavras_gatilho") or {}
    out["palavras_gatilho"] = _unicos(list(tmeta_canal.get("palavras_gatilho") or [])
                                      + [g for i in ordem for g in gat.get(i) or []])
    out["nunca_usar"] = _unicos(list(tmeta_canal.get("nunca_usar") or []) + list(meta_base.get("nunca_usar") or []))
    out["temas"] = nomes(ordem)
    return out


def _cortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit("\n", 1)[0] + "\n(…)"


PARTES = {
    "cortes": ("cortes.md", "Como escolher e abrir o corte"),
    "titulos": ("titulos.md", "Padrões dos títulos mais vistos"),
    "thumbs": ("thumbs.md", "Padrões das thumbnails mais vistas"),
    "referencias": ("referencias.md", "Títulos reais mais vistos (régua de tom, não copie)"),
}


def para_ia(ids: list[str], partes: Iterable[str] = ("cortes", "titulos", "referencias"), limite: int = 9000) -> str:
    """O trecho da base que vai para a IA: as seções dos temas do vídeo e a do geral, parte por parte.
    O limite é dividido entre as partes para nenhuma engolir as outras."""
    t = temas()
    ordem = [i for i in ids if i in t and i != GERAL] + [GERAL]
    partes = [p for p in partes if p in PARTES]
    if not partes:
        return ""
    cada = max(800, limite // len(partes))
    blocos = []
    for p in partes:
        arquivo, titulo = PARTES[p]
        sec = secoes(arquivo)
        texto = "\n\n".join(_SECAO.sub(r"### \1", sec[i]) for i in ordem if i in sec)
        if texto.strip():
            blocos.append(f"## {titulo}\n{_cortar(texto.strip(), cada)}")
    if not blocos:
        return ""
    cab = ("# Base de referência do Clipator (pesquisa de 75 canais de cortes)\n"
           f"Tema detectado no vídeo: {', '.join(nomes(ordem))}. Use como régua; o que o canal define vale por cima.")
    cens = censuradas(ordem)
    if cens:
        cab += "\nNo título e na thumb, os canais grandes do tema censuram: " + ", ".join(cens) + " (M0RREU, P*RRA)."
    return "\n\n".join([cab, *blocos])


def censuradas(ids: list[str]) -> list[str]:
    """Palavras que os canais grandes dos temas escrevem com censura (para a IA e para o LEIA-ME)."""
    t = temas()
    return _unicos(p for i in ids for p in t.get(i, {}).get("censurar") or [])
