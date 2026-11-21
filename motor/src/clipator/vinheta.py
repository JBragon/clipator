"""Vinheta do canal: o vídeo curto da marca que entra nos cortes longos (nunca nos Shorts).

O arquivo fica em canais/<canal>/assets/vinheta.<ext> e o canal.md guarda o caminho (`vinheta`) e onde ela entra
por padrão (`vinheta_posicao`: inicio ou depois-do-gancho). No passo 3 o usuário escolhe, para cada leva de cortes
longos, se a vinheta abre o vídeo ou se vem entre o gancho forte e o corte. Quem monta é abertura.montar, na
mesma passada dos ganchos, já no tamanho e no fps do clip.

Sem IA e offline: só FFmpeg.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import markdown as md
from . import media
from .workspace import CanalWS

EXT_VIDEO = (".mp4", ".mov", ".m4v", ".mkv", ".webm")
LIMITE = 80 * 1024 * 1024  # 80 MB
DURACAO_MAX = 30.0  # vinheta é curta: mais que isso atrasa demais a entrada do corte
POSICOES = ("inicio", "depois-do-gancho")
BASE = "vinheta"


class ErroVinheta(ValueError):
    pass


def _meta(canal: CanalWS) -> tuple[dict[str, Any], str]:
    doc = md.read(canal.path / "canal.md")
    return dict(doc.meta), doc.body


def _salvar_meta(canal: CanalWS, meta: dict[str, Any], corpo: str) -> None:
    md.write(canal.path / "canal.md", meta, corpo)


def arquivo(canal: CanalWS) -> Path | None:
    """O arquivo da vinheta, se o canal tem uma e ela está na pasta do canal."""
    info, _ = canal.info()
    if not info.vinheta:
        return None
    p = (canal.path / info.vinheta).resolve()
    if not p.is_relative_to(canal.path.resolve()) or not p.is_file():
        return None
    return p


def estado(canal: CanalWS) -> dict[str, Any]:
    info, _ = canal.info()
    p = arquivo(canal)
    duracao = None
    if p is not None:
        try:
            duracao = round(media.probe(p).duracao, 2)
        except Exception:  # noqa: BLE001 - arquivo estragado aparece como vinheta sem duração
            duracao = None
    return {"arquivo": info.vinheta if p is not None else None, "nome": p.name if p is not None else None,
            "duracao": duracao, "posicao": info.vinheta_posicao,
            "faltando": bool(info.vinheta) and p is None}


def salvar(canal: CanalWS, nome: str, dados: bytes) -> dict[str, Any]:
    """Grava a vinheta nova (troca a anterior) e aponta o canal.md para ela."""
    ext = Path(nome or "").suffix.lower()
    if ext not in EXT_VIDEO:
        raise ErroVinheta(f"A vinheta precisa ser um vídeo ({', '.join(EXT_VIDEO)}).")
    if not dados:
        raise ErroVinheta("O arquivo da vinheta veio vazio.")
    if len(dados) > LIMITE:
        raise ErroVinheta(f"A vinheta passa do limite de {LIMITE // (1024 * 1024)} MB.")
    pasta = canal.path / "assets"
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / f".{BASE}-envio{ext}"
    tmp.write_bytes(dados)
    try:
        info = media.probe(tmp)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise ErroVinheta("Não consegui ler esse vídeo. Tente exportar a vinheta de novo em MP4.") from exc
    if not info.tem_video or info.duracao <= 0.2:
        tmp.unlink(missing_ok=True)
        raise ErroVinheta("Esse arquivo não tem vídeo: a vinheta precisa de imagem.")
    if info.duracao > DURACAO_MAX:
        tmp.unlink(missing_ok=True)
        raise ErroVinheta(f"A vinheta tem {info.duracao:.0f} s. Use uma de até {DURACAO_MAX:.0f} s.")
    for velha in pasta.glob(f"{BASE}.*"):
        velha.unlink(missing_ok=True)
    final = pasta / f"{BASE}{ext}"
    media.substituir(tmp, final)
    meta, corpo = _meta(canal)
    meta["vinheta"] = f"assets/{final.name}"
    meta.setdefault("vinheta_posicao", "depois-do-gancho")
    _salvar_meta(canal, meta, corpo)
    return estado(canal)


def remover(canal: CanalWS) -> dict[str, Any]:
    """Tira a vinheta do canal (o arquivo e a linha do canal.md). Os cortes longos voltam a sair sem ela."""
    p = arquivo(canal)
    if p is not None and p.name.startswith(BASE + "."):  # só apaga o arquivo que o próprio app gravou
        p.unlink(missing_ok=True)
    meta, corpo = _meta(canal)
    meta.pop("vinheta", None)
    _salvar_meta(canal, meta, corpo)
    return estado(canal)


def definir_posicao(canal: CanalWS, posicao: str) -> dict[str, Any]:
    if posicao not in POSICOES:
        raise ErroVinheta("Use inicio ou depois-do-gancho.")
    meta, corpo = _meta(canal)
    meta["vinheta_posicao"] = posicao
    _salvar_meta(canal, meta, corpo)
    return estado(canal)
