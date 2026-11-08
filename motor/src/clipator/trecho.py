"""Trecho de um clip no vídeo original: aumentar ou diminuir o corte para dar mais ou menos contexto.

A tela "Editar duração" do app (e a ferramenta `ajustar_corte` do MCP) mudam só `inicio` e `fim` do
clip.yaml, ou de um corte sugerido no passo 2 (`ajustar_candidato`), antes de virar clip. O que já foi feito no clip continua valendo: os itens do editor (edicao.json, em segundos
do clip) andam junto com a fala a que estavam presos, e os que caem fora do novo trecho saem.
Depois disso o clip volta a "selecionado" e, se já tinha vídeo, é renderizado de novo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Clip
from .timeline import Timeline
from .workspace import ProjetoWS

DURACAO_MIN = 1.0  # um corte mais curto que isso não vira vídeo


class TrechoInvalido(ValueError):
    """Início ou fim fora do vídeo, ou corte curto demais (a API responde 400)."""


@dataclass
class Resultado:
    clip: Clip
    itens_movidos: int  # itens do editor que mudaram de tempo para continuar no mesmo ponto da fala
    itens_removidos: int  # itens que ficaram fora do novo trecho
    renderizar: bool  # o clip já tinha vídeo: quem chamou deve mandar renderizar de novo
    preview: bool  # só havia a prévia: renderizar a prévia, não o vídeo final


def duracao_do_video(projeto: ProjetoWS) -> float | None:
    """Duração do vídeo pai (metadados da ingestão; sem eles, a da transcrição)."""
    try:
        d = (projeto.metadados().get("midia") or {}).get("duracao")
    except Exception:  # noqa: BLE001 - metadados ilegíveis: tenta a transcrição
        d = None
    if not d:
        d = (projeto.transcricao() or {}).get("duracao")
    return float(d) if d else None


def remapear_itens(itens: list[Any], antes: Timeline, depois: Timeline) -> tuple[list[Any], int, int]:
    """Leva cada item do tempo do clip antigo para o do clip novo, preso ao mesmo instante do original."""
    out, movidos, removidos = [], 0, 0
    for it in itens:
        a, b = antes.para_original(it.inicio), antes.para_original(it.fim)
        novo = depois.mapear_intervalo(a, b)
        if novo is None or novo[1] - novo[0] < 0.05:
            removidos += 1
            continue
        ini, fim = round(novo[0], 3), round(novo[1], 3)
        if (ini, fim) != (round(it.inicio, 3), round(it.fim, 3)):
            movidos += 1
        out.append(it.model_copy(update={"inicio": ini, "fim": fim}))
    return out, movidos, removidos


def _validar(projeto: ProjetoWS, inicio: float, fim: float) -> tuple[float, float]:
    """Arredonda e confere o trecho contra o vídeo pai; devolve (inicio, fim) prontos para gravar."""
    inicio, fim = round(float(inicio), 3), round(float(fim), 3)
    total = duracao_do_video(projeto)
    if inicio < 0:
        raise TrechoInvalido("O início não pode ser antes do começo do vídeo")
    if total and fim > total + 0.05:
        raise TrechoInvalido(f"O fim passa do fim do vídeo ({total:.1f} s)")
    if total:
        fim = min(fim, round(total, 3))
    if fim - inicio < DURACAO_MIN:
        raise TrechoInvalido(f"O corte precisa ter pelo menos {DURACAO_MIN:.0f} s")
    return inicio, fim


def ajustar_candidato(projeto: ProjetoWS, cid: str, inicio: float, fim: float) -> dict:
    """Passo 2: muda o trecho de um corte sugerido antes de virar clip (duração e texto acompanham).

    A nota e os títulos ficam como estavam; `ajuste_usuario` guarda o trecho que a análise tinha sugerido.
    """
    from .candidates import texto_do_trecho

    cands = projeto.candidatos()
    c = next((c for c in cands if c.get("id") == cid), None)
    if c is None:
        raise KeyError(f"Corte sugerido não encontrado: {cid}")
    inicio, fim = _validar(projeto, inicio, fim)
    if (inicio, fim) != (round(float(c["inicio"]), 3), round(float(c["fim"]), 3)):
        c.setdefault("ajuste_usuario", {"inicio_sugerido": c["inicio"], "fim_sugerido": c["fim"]})
        c.update(inicio=inicio, fim=fim, duracao=round(fim - inicio, 3),
                 texto=texto_do_trecho(projeto.transcricao() or {}, inicio, fim) or c.get("texto", ""))
        projeto.salvar_candidatos(cands)
    return c


def ajustar(projeto: ProjetoWS, clip_id: str, inicio: float, fim: float) -> Resultado:
    """Grava o novo trecho do clip (segundos do vídeo original) e acompanha a edição do clip."""
    from . import edicao

    atual, pasta = projeto.clip(clip_id)
    inicio, fim = _validar(projeto, inicio, fim)
    try:
        antes = Timeline.de_clip(atual.inicio, atual.fim, atual.cortes_internos)
        depois = Timeline.de_clip(inicio, fim, atual.cortes_internos)
    except ValueError as exc:
        raise TrechoInvalido(str(exc)) from exc

    mudou = (inicio, fim) != (round(atual.inicio, 3), round(atual.fim, 3))
    movidos = removidos = 0
    if mudou and (pasta / edicao.ARQUIVO).exists():
        doc = edicao.carregar(pasta)
        itens, movidos, removidos = remapear_itens(doc.itens, antes, depois)
        if movidos or removidos:
            edicao.salvar(pasta, doc.model_copy(update={"itens": itens}), depois.duracao)

    tinha_saida = (pasta / "saida.mp4").exists() or bool(atual.versao)
    tinha_previa = (pasta / "preview.mp4").exists()
    novo = atual.model_copy(update={"inicio": inicio, "fim": fim})
    if mudou:
        # a versão editada escolhida e o vídeo antigo são do trecho velho: o clip volta a ser gerado
        novo = novo.model_copy(update={"status": "selecionado", "versao": None})
    projeto.salvar_clip(Clip.model_validate(novo.model_dump(mode="json")))
    return Resultado(clip=novo, itens_movidos=movidos, itens_removidos=removidos,
                     renderizar=mudou and (tinha_saida or tinha_previa), preview=not tinha_saida)
