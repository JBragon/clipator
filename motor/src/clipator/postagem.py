"""Pacote de postagem de cada clip, por plataforma (YouTube Shorts, Reels, TikTok, YouTube).

Cada pacote tem título (onde a plataforma tem), descrição em blocos, hashtags, tags
(só YouTube), a legenda .srt e a thumbnail escolhida. Tudo é conferido contra os
limites de plataformas.py: o que passa é cortado e vira aviso.

Sem IA, o texto sai do título do clip, de uma frase dita no corte e das hashtags do
canal. Com IA, a resposta vem pelo adaptador (JSON por schema) e a frase de resumo
só entra se tiver prova literal na transcrição do corte (a mesma checagem das thumbs).

Salva em clips/<id>/postagem/<plataforma>.json e .txt. Não publica nada.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable

from . import plataformas, titles
from .models import Clip
from .plataformas import InfoPlataforma
from .textutil import normalizar
from .workspace import ProjetoWS

SCHEMA_POSTAGEM = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "resumo": {"type": "string"},
        "prova": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["titulo", "resumo", "prova", "hashtags", "tags"],
}


def _hashtag(t: str) -> str | None:
    """'Flávio Bolsonaro' -> '#FlávioBolsonaro'; descarta o que não vira hashtag."""
    t = re.sub(r"[^\w]", "", t.replace("#", ""), flags=re.UNICODE)
    return f"#{t}" if t and not t.isdigit() else None


def _unicos(itens: list[str], chave=normalizar) -> list[str]:
    vistos, out = set(), []
    for x in itens:
        k = chave(x)
        if x and k not in vistos:
            vistos.add(k)
            out.append(x)
    return out


def _cortar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    corte = texto[: limite - 1].rsplit(" ", 1)[0].rstrip(",;:-–—")
    return corte + "…"


def validar(info: InfoPlataforma, pacote: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Corta o pacote nos limites da plataforma e diz o que foi cortado."""
    lim = info.limites
    p = dict(pacote)
    avisos: list[str] = []
    if lim.titulo is None:
        p["titulo"] = None
    elif p.get("titulo") and len(p["titulo"]) > lim.titulo:
        avisos.append(f"Título com {len(p['titulo'])} caracteres; o {info.nome} aceita {lim.titulo}. Cortei.")
        p["titulo"] = _cortar(p["titulo"], lim.titulo)
    tags = _unicos([h for h in (_hashtag(x) for x in p.get("hashtags") or []) if h])
    fixas = {normalizar(f) for f in info.hashtags_fixas}
    tags = list(info.hashtags_fixas) + [t for t in tags if normalizar(t) not in fixas]  # as da plataforma vêm primeiro
    if len(tags) > lim.hashtags:
        avisos.append(f"{len(tags)} hashtags; o {info.nome} aceita até {lim.hashtags}. Fiquei com as primeiras.")
        tags = tags[: lim.hashtags]
    p["hashtags"] = tags
    if lim.tags_total is None:
        p["tags"] = []
    else:
        ok, total = [], 0
        for t in _unicos([str(x).strip() for x in p.get("tags") or [] if str(x).strip()]):
            if total + len(t) + (1 if ok else 0) > lim.tags_total:
                avisos.append(f"As tags passam de {lim.tags_total} caracteres no total; tirei as últimas.")
                break
            ok.append(t)
            total += len(t) + (1 if len(ok) > 1 else 0)
        p["tags"] = ok
    p["descricao"] = _descricao(p)
    if len(p["descricao"]) > lim.descricao:
        avisos.append(f"Descrição com {len(p['descricao'])} caracteres; o {info.nome} aceita {lim.descricao}. Cortei.")
        p["descricao"] = _cortar(p["descricao"], lim.descricao)
    return p, avisos


def _descricao(p: dict[str, Any]) -> str:
    """Junta os blocos: legenda curta (sem título: título no começo), resumo, contexto, link e hashtags."""
    blocos = p.get("blocos") or {}
    partes = []
    if p.get("titulo") is None and blocos.get("titulo"):
        partes.append(blocos["titulo"])
    for k in ("resumo", "contexto", "link", "creditos"):
        if blocos.get(k):
            partes.append(blocos[k])
    if p.get("hashtags"):
        partes.append(" ".join(p["hashtags"]))
    return "\n\n".join(partes).strip()


def _base(projeto: ProjetoWS, clip: Clip, pasta: Path, texto: str) -> dict[str, Any]:
    """O que é igual em todas as plataformas, sem IA."""
    from .thumbs import frases_locais

    canal, _ = projeto.canal.info()
    md = projeto.metadados()
    insight = next((f for f in frases_locais(texto, clip.titulo) if f.tipo == "insight" and f.prova), None)
    resumo = f"“{_cortar(insight.prova, 240)}”" if insight else ""
    contexto = f"Trecho de: {md['titulo']}" if md.get("titulo") else ""
    link = f"Vídeo completo: {md['url']}" if md.get("url") else ""
    nomes = list(canal.glossario)[:3]
    hashtags = [*canal.palavras_chave[:4], *nomes, "cortes"]
    tema = titles.tema_do_trecho(texto, canal.palavras_chave) if texto else ""
    tags = _unicos([*canal.palavras_chave, *canal.glossario, *([tema] if tema and tema != "isso" else [])])
    # stickers com licença que pede crédito (CC BY) entram na descrição sozinhos
    from . import edicao, stickers

    refs = [i.params.get("ref", "") for i in edicao.carregar(pasta).itens if i.tipo == "sticker"]
    creditos = stickers.creditos_do_clip(refs, projeto.canal.path) if refs else ""
    return {
        "titulo": clip.titulo or "",
        "blocos": {"titulo": clip.titulo or "", "resumo": resumo, "contexto": contexto, "link": link,
                   **({"creditos": creditos} if creditos else {})},
        "hashtags": hashtags,
        "tags": tags,
        "legenda": "legenda.srt" if (pasta / "legenda.srt").exists() else None,
        "thumb": "thumb.png" if (pasta / "thumb.png").exists() else None,
        "fonte": "local",
    }


def _com_ia(base: dict[str, Any], resposta: dict, texto: str, trava: bool, agente: str) -> tuple[dict[str, Any], list[str]]:
    """Mistura a resposta da IA na base, só com o que se sustenta no corte."""
    from .thumbs import FraseThumb, apoiada

    p = json.loads(json.dumps(base))
    avisos: list[str] = []
    titulo = str(resposta.get("titulo") or "").strip()
    if titulo and (not trava or titles.respeita_trava(titulo, texto)):
        p["titulo"] = titulo
        p["blocos"]["titulo"] = titulo
    elif titulo:
        avisos.append("O título da IA promete algo que não está no corte; mantive o título do clip.")
    resumo = str(resposta.get("resumo") or "").strip()
    if resumo and apoiada(FraseThumb("insight", [resumo], [], str(resposta.get("prova") or "")), texto):
        p["blocos"]["resumo"] = resumo
    elif resumo:
        avisos.append("O resumo da IA não tem prova no corte (ou cita número que não foi dito); usei uma frase dita no clip.")
    p["hashtags"] = _unicos([*[str(h) for h in resposta.get("hashtags") or []], *base["hashtags"]])
    p["tags"] = _unicos([*[str(t) for t in resposta.get("tags") or []], *base["tags"]])
    p["fonte"] = agente
    return p, avisos


def prompt_postagem(clip: Clip, texto: str, canal_md: str, extras: str) -> str:
    return "\n".join([
        "Você escreve o texto de postagem de um clip de um canal de cortes. Responda só com o JSON do schema.",
        "",
        "- titulo: até 90 caracteres, chamativo, mas tudo o que ele promete acontece no clip.",
        "- resumo: 1 ou 2 frases curtas que fazem a pessoa querer assistir. Tom de gente falando, sem clichê de",
        "  IA (nada de 'mergulhe', 'descubra', 'neste vídeo'), com nome e fato concreto do trecho.",
        "- prova: copie, sem mudar nenhuma palavra, o trecho da transcrição que sustenta o resumo.",
        "  Resumo sem prova literal é descartado. Não invente número, nome nem acontecimento.",
        "- hashtags: 3 a 6, sem espaço; a primeira é o assunto principal.",
        "- tags: 5 a 12 termos de busca do YouTube (palavras ou expressões curtas).",
        "",
        f"Título atual do clip: {clip.titulo}",
        "",
        "## Canal",
        canal_md.strip() or "(sem descrição)",
        extras.strip(),
        "",
        "## Transcrição do clip (só o trecho do corte)",
        texto[:4000],
    ])


def gerar(projeto: ProjetoWS, clip_id: str, usar_ia: bool = False, cancelar: threading.Event | None = None,
          esperar_login: Callable[[str], bool] | None = None) -> dict[str, dict[str, Any]]:
    """Monta, valida e salva os pacotes das plataformas do formato do clip. Devolve {plataforma: pacote}."""
    from . import skills
    from .ai.adapter import CacheIA, ErroIA, adaptador_com_reserva, chamar
    from .candidates import texto_do_trecho

    clip, pasta = projeto.clip(clip_id)
    regras, _ = projeto.canal.regras()
    _, canal_md = projeto.canal.info()
    texto = texto_do_trecho(projeto.transcricao() or {}, clip.inicio, clip.fim)
    base = _base(projeto, clip, pasta, texto)
    avisos_ia: list[str] = []
    if usar_ia:
        conf = projeto.ws.config()
        ad = adaptador_com_reserva(conf.ia.ranking, conf.ia.timeout_s, esperar_login=esperar_login)
        if ad.disponivel():
            extras = skills.texto_para_ia(projeto.ws, "postagem", projeto.canal.slug, projeto.id)
            try:
                r = chamar(ad, prompt_postagem(clip, texto, canal_md, extras), SCHEMA_POSTAGEM,
                           CacheIA(projeto.analise_dir / "cache_ia"), cancelar)
                base, avisos_ia = _com_ia(base, r or {}, texto, regras.trava_titulo, ad.nome)
            except ErroIA as exc:
                avisos_ia = [f"A IA não respondeu ({exc}); o texto saiu sem IA."]
        else:
            avisos_ia = ["Nenhuma IA instalada; o texto saiu sem IA."]
    if regras.trava_titulo and base["titulo"] and texto and not titles.respeita_trava(base["titulo"], texto):
        avisos_ia.append("Trava do título: o título promete algo que não aparece na transcrição do clip.")
    out: dict[str, dict[str, Any]] = {}
    destino = pasta / "postagem"
    destino.mkdir(exist_ok=True)
    for info in plataformas.para_formato(clip.formato):
        pacote, avisos = validar(info, base)
        pacote = {"plataforma": info.id, "nome": info.nome, **pacote, "avisos": avisos_ia + avisos}
        out[info.id] = pacote
        (destino / f"{info.id}.json").write_text(json.dumps(pacote, ensure_ascii=False, indent=1), encoding="utf-8")
        (destino / f"{info.id}.txt").write_text(texto_para_colar(pacote), encoding="utf-8")
    principal = out.get(plataformas.info(clip.plataforma, clip.formato).id) or next(iter(out.values()))
    (pasta / "postagem.txt").write_text(texto_para_colar(principal), encoding="utf-8")  # o arquivo de antes continua
    return out


def texto_para_colar(p: dict[str, Any]) -> str:
    linhas = [f"# {p['nome']}", ""]
    if p.get("titulo"):
        linhas += ["Título:", p["titulo"], ""]
    linhas += ["Descrição:", p.get("descricao", ""), ""]
    if p.get("tags"):
        linhas += ["Tags:", ", ".join(p["tags"]), ""]
    if p.get("legenda"):
        linhas.append(f"Legenda: {p['legenda']}")
    if p.get("thumb"):
        linhas.append(f"Thumbnail: {p['thumb']}")
    for a in p.get("avisos") or []:
        linhas.append(f"Aviso: {a}")
    return "\n".join(linhas).strip() + "\n"


def carregar(projeto: ProjetoWS, clip_id: str) -> dict[str, dict[str, Any]]:
    _, pasta = projeto.clip(clip_id)
    destino = pasta / "postagem"
    if not destino.exists():
        return {}
    out = {}
    for f in sorted(destino.glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return out
