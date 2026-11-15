"""Legenda editada à mão depois do render (passo 5).

A legenda é queimada no vídeo, então corrigir uma palavra ou um tempo quer dizer gerar o clip de novo.
Este módulo guarda a correção em clips/<id>/legenda-editada.json, no tempo do clip (o que o usuário vê
no player), e o render troca as palavras da transcrição dentro do corte pelas palavras editadas. Assim a
legenda animada (ASS ou HyperFrames), a legenda oculta (.srt/.vtt), os destaques e os sons seguem o texto
corrigido sem mudar a transcrição do vídeo inteiro.

A edição é por frase (as mesmas frases da legenda oculta): texto, início e fim. Com o mesmo número de
palavras, cada palavra mantém o seu tempo (esticado para o novo início e fim); com outro número, as
palavras dividem o tempo da frase pelo tamanho de cada uma, como na correção de transcrição do passo 1.

A edição vale para o corte em que foi feita: se o início, o fim ou os cortes internos do clip mudarem,
ela fica de lado (o render volta à transcrição) e a tela avisa.

Sem IA e offline.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from . import subtitles
from .timeline import Timeline
from .workspace import ProjetoWS, write_json

ARQUIVO = "legenda-editada.json"
DURACAO_MIN = 0.1  # uma frase fica pelo menos isso na tela
_TOKEN = re.compile(r"\S+")


class ErroLegenda(ValueError):
    pass


class Palavra(BaseModel):
    texto: str
    inicio: float
    fim: float


class Frase(BaseModel):
    inicio: float = Field(ge=0, description="Segundos no tempo do clip")
    fim: float = Field(ge=0, description="Segundos no tempo do clip")
    texto: str = ""
    palavras: list[Palavra] = Field(default_factory=list, description="Palavras de antes da edição (para manter os tempos)")


class LegendaEditada(BaseModel):
    frases: list[Frase] = Field(default_factory=list)


# ---- corte e palavras de partida ----------------------------------------------------------
def assinatura(clip: Any) -> dict[str, Any]:
    """O corte em que a edição foi feita: se mudar, a edição não vale mais."""
    return {"inicio": round(float(clip.inicio), 3), "fim": round(float(clip.fim), 3),
            "cortes": [[round(float(a), 3), round(float(b), 3)] for a, b in sorted(clip.cortes_internos or [])]}


def timeline_do_clip(clip: Any) -> Timeline:
    return Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)


def palavras_da_transcricao(projeto: ProjetoWS) -> list[dict]:
    """Palavras do vídeo inteiro como o render usa: transcrição com a checagem de fatos aplicada."""
    from .transcribe import palavras as _palavras

    trans = projeto.transcricao() or {}
    pals = _palavras(trans) if trans else []
    if pals:
        try:
            from . import checagem

            fatos = checagem.revisados(projeto)
            if fatos:
                pals, _ = checagem.aplicar_nas_palavras(pals, fatos)
        except Exception:  # noqa: BLE001 - igual ao render: checagem com problema não atrapalha
            pass
    return pals


def frases_da_transcricao(pals: list[dict], tl: Timeline) -> list[Frase]:
    """As frases do clip (as da legenda oculta) com as palavras de cada uma, no tempo do clip."""
    pals_clip = subtitles.palavras_do_clip(pals, tl)
    frases: list[Frase] = []
    k = 0
    for a, b, linhas in subtitles.cues_de_frases(pals_clip):
        ws: list[Palavra] = []
        while k < len(pals_clip) and pals_clip[k]["inicio"] < b + 1e-6:
            w = pals_clip[k]
            if w["inicio"] >= a - 1e-6:
                ws.append(Palavra(texto=str(w["texto"]).strip(), inicio=round(w["inicio"], 3), fim=round(w["fim"], 3)))
            k += 1
        frases.append(Frase(inicio=a, fim=b, texto=" ".join(linhas), palavras=ws))
    return frases


# ---- arquivo ---------------------------------------------------------------------------------
def caminho(pasta_clip: Path) -> Path:
    return pasta_clip / ARQUIVO


def _ler(pasta_clip: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(caminho(pasta_clip).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def carregar(projeto: ProjetoWS, clip_id: str) -> LegendaEditada | None:
    """A edição salva, se ela ainda vale para o corte atual do clip."""
    clip, pasta = projeto.clip(clip_id)
    d = _ler(pasta)
    if not d or d.get("assinatura") != assinatura(clip):
        return None
    try:
        return LegendaEditada.model_validate(d)
    except ValueError:
        return None


def normalizar(leg: LegendaEditada, duracao: float) -> LegendaEditada:
    """Ordena, prende ao tamanho do clip e tira sobreposição. Frase sem texto sai."""
    frases = sorted((f for f in leg.frases if f.texto.strip()), key=lambda f: (f.inicio, f.fim))
    out: list[Frase] = []
    for i, f in enumerate(frases):
        a = max(0.0, min(float(f.inicio), duracao - DURACAO_MIN))
        b = max(a + DURACAO_MIN, min(float(f.fim), duracao))
        if out and a < out[-1].fim:  # encostou na anterior: a anterior termina antes desta começar
            ant = out[-1]
            if a - ant.inicio >= DURACAO_MIN:
                out[-1] = ant.model_copy(update={"fim": round(a, 3)})
            else:
                a = ant.fim
                b = max(b, a + DURACAO_MIN)
        if a >= duracao:
            continue
        out.append(f.model_copy(update={"inicio": round(a, 3), "fim": round(min(b, duracao), 3),
                                        "texto": " ".join(_TOKEN.findall(f.texto))}))
    return LegendaEditada(frases=out)


def salvar(projeto: ProjetoWS, clip_id: str, leg: LegendaEditada) -> LegendaEditada:
    clip, pasta = projeto.clip(clip_id)
    tl = timeline_do_clip(clip)
    leg = normalizar(leg, tl.duracao)
    if not leg.frases:
        raise ErroLegenda("A legenda ficou vazia. Para voltar ao texto da transcrição, use “Voltar à transcrição”.")
    write_json(caminho(pasta), {"assinatura": assinatura(clip), **leg.model_dump(mode="json")})
    return leg


def descartar(projeto: ProjetoWS, clip_id: str) -> bool:
    _, pasta = projeto.clip(clip_id)
    p = caminho(pasta)
    if p.exists():
        p.unlink()
        return True
    return False


# ---- palavras para o render ----------------------------------------------------------------
def palavras_da_frase(f: Frase) -> list[dict]:
    """As palavras de uma frase editada, no tempo do clip."""
    tokens = _TOKEN.findall(f.texto)
    if not tokens:
        return []
    a, b = float(f.inicio), float(f.fim)
    antigas = f.palavras
    if antigas and len(antigas) == len(tokens):
        a0, b0 = antigas[0].inicio, antigas[-1].fim
        escala = (b - a) / (b0 - a0) if b0 - a0 > 1e-6 else 0.0

        def m(t: float) -> float:
            return a + (t - a0) * escala if escala else a

        out = []
        for w, tx in zip(antigas, tokens):
            ini, fim = m(w.inicio), m(w.fim)
            out.append({"texto": tx, "inicio": round(ini, 3), "fim": round(max(fim, ini + 0.02), 3), "editada": True})
        return out
    total = sum(len(t) for t in tokens) or 1
    out, t = [], a
    for tx in tokens:
        d = (b - a) * len(tx) / total
        out.append({"texto": tx, "inicio": round(t, 3), "fim": round(t + d, 3), "editada": True})
        t += d
    return out


def aplicar(pals: list[dict], leg: LegendaEditada, tl: Timeline) -> list[dict]:
    """Troca as palavras do original que caem no corte pelas editadas (levadas de volta ao tempo do original)."""
    fora = [w for w in pals if w["fim"] <= tl.inicio or w["inicio"] >= tl.fim]
    novas = []
    for f in leg.frases:
        for w in palavras_da_frase(f):
            ini = tl.para_original(w["inicio"])
            fim = tl.para_original(w["fim"])
            if fim - ini < 0.02:  # caiu inteira na emenda de um corte interno
                fim = ini + 0.02
            novas.append({**w, "inicio": round(ini, 3), "fim": round(fim, 3)})
    return sorted(fora + novas, key=lambda w: w["inicio"])


def aplicar_no_render(projeto: ProjetoWS, clip: Any, pals: list[dict], tl: Timeline,
                      log: Callable[[str], None] | None = None) -> list[dict]:
    """Usado pelo render: devolve as palavras com a legenda editada do clip, se houver uma que valha."""
    pasta = projeto.clips_dir / clip.id
    d = _ler(pasta)
    if not d:
        return pals
    if d.get("assinatura") != assinatura(clip):
        if log:
            log("a legenda editada foi feita para outro trecho do clip e ficou de fora; edite de novo no passo 5")
        return pals
    try:
        leg = LegendaEditada.model_validate(d)
    except ValueError:
        return pals
    if log:
        log(f"legenda editada à mão: {len(leg.frases)} frase(s)")
    return aplicar(pals, leg, tl)


# ---- estado para a tela -----------------------------------------------------------------------
def _deslocamento(pasta: Path) -> float:
    """A abertura com ganchos vem antes do corte: o tempo do clip começa depois dela no vídeo final."""
    try:
        return float(json.loads((pasta / "abertura.json").read_text(encoding="utf-8")).get("duracao") or 0)
    except (OSError, ValueError, AttributeError):
        return 0.0


def estado(projeto: ProjetoWS, clip_id: str) -> dict[str, Any]:
    clip, pasta = projeto.clip(clip_id)
    tl = timeline_do_clip(clip)
    d = _ler(pasta)
    salva = carregar(projeto, clip_id)
    pals = palavras_da_transcricao(projeto)
    if salva is None and not pals:
        raise ErroLegenda("Este projeto não tem transcrição: não há legenda para editar.")
    frases = salva.frases if salva is not None else frases_da_transcricao(pals, tl)
    return {
        "frases": [f.model_dump(mode="json") for f in frases],
        "editada": salva is not None,
        "desatualizada": bool(d) and salva is None,  # editada para outro corte: ficou de lado
        "duracao": round(tl.duracao, 3),
        "deslocamento": round(_deslocamento(pasta), 3),
        "gerado": clip.status == "renderizado",
    }


# ---- gerar de novo ------------------------------------------------------------------------------
def renderizar(projeto: ProjetoWS, clip_id: str, progresso: Callable[[float, str], None] | None = None,
               cancelar: threading.Event | None = None, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Gera o clip de novo com a legenda editada. O acabamento em uso é refeito em cima do vídeo novo;
    uma versão editada com IA continua na lista de versões, mas a saída passa a ser o vídeo novo."""
    from . import acabamento, pipeline

    clip, pasta = projeto.clip(clip_id)
    ajustes = None
    try:
        _, salvo = acabamento.base_do_clip(projeto, clip_id)
        if salvo and salvo.get("ajustes"):
            ajustes = acabamento.Acabamento.model_validate(salvo["ajustes"])
    except acabamento.ErroAcabamento:
        pass
    versao_antes = clip.versao
    tem_acab = ajustes is not None and not ajustes.vazio()
    peso = 0.85 if tem_acab else 1.0

    def prog(f: float, m: str) -> None:
        if progresso:
            progresso(peso * f, m)

    r = pipeline.renderizar(projeto, clip_id, False, prog, cancelar, log=log)
    clip, _ = projeto.clip(clip_id)
    clip.versao = None
    projeto.salvar_clip(clip)
    out: dict[str, Any] = {"saida": r.video.relative_to(projeto.ws.root).as_posix(), "aviso": r.aviso}
    if tem_acab:
        if progresso:
            progresso(peso, "refazendo o acabamento")
        res = acabamento.aplicar(projeto, clip_id, ajustes,
                                 lambda f, m: progresso(peso + (1 - peso) * f, m) if progresso else None, cancelar)
        out["acabamento"] = res.get("versao")
        if log:
            log("o acabamento foi refeito em cima do vídeo com a legenda nova")
    elif versao_antes and log:
        log("a versão editada que estava em uso continua guardada na lista de versões; a saída agora é o vídeo novo")
    return out
