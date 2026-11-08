"""Plataformas de publicação: zona segura da tela e limites do texto de postagem.

As margens são frações da tela que a interface de cada app cobre (botões, nome do
canal, legenda do post, barra de progresso). São valores APROXIMADOS, tirados das
orientações públicas de cada plataforma e de medições em tela; mudam quando os apps
mudam, então ficam aqui num lugar só para ajustar.

Os limites de texto também são aproximados (conferidos em 2026); a validação avisa
e corta, mas quem publica deve conferir no app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Plataforma = Literal["youtube-shorts", "instagram-reels", "tiktok", "youtube"]


@dataclass(frozen=True)
class Zona:
    topo: float  # fração da altura coberta em cima
    base: float  # fração da altura coberta embaixo
    direita: float  # fração da largura coberta à direita (botões de curtir, comentar)
    esquerda: float = 0.04


@dataclass(frozen=True)
class Limites:
    titulo: int | None  # caracteres; None = a plataforma não tem campo de título
    descricao: int
    hashtags: int  # quantas no máximo
    tags_total: int | None  # soma dos caracteres das tags (só YouTube)


@dataclass(frozen=True)
class InfoPlataforma:
    id: Plataforma
    nome: str
    vertical: bool
    zona: Zona
    limites: Limites
    hashtags_fixas: tuple[str, ...] = ()


PLATAFORMAS: dict[str, InfoPlataforma] = {
    "youtube-shorts": InfoPlataforma(
        "youtube-shorts", "YouTube Shorts", True,
        Zona(topo=0.10, base=0.20, direita=0.14),
        Limites(titulo=100, descricao=5000, hashtags=15, tags_total=500), ("#shorts",)),
    "instagram-reels": InfoPlataforma(
        "instagram-reels", "Instagram Reels", True,
        Zona(topo=0.12, base=0.24, direita=0.13),
        # o Instagram passou a limitar as hashtags do post a poucas (5 desde o fim de 2025)
        Limites(titulo=None, descricao=2200, hashtags=5, tags_total=None)),
    "tiktok": InfoPlataforma(
        "tiktok", "TikTok", True,
        Zona(topo=0.09, base=0.22, direita=0.15),
        Limites(titulo=None, descricao=4000, hashtags=10, tags_total=None)),
    "youtube": InfoPlataforma(
        "youtube", "YouTube (16:9)", False,
        Zona(topo=0.0, base=0.08, direita=0.0, esquerda=0.0),  # barra de progresso e legendas do player
        Limites(titulo=100, descricao=5000, hashtags=15, tags_total=500)),
}


def padrao_para(formato: str | None) -> Plataforma:
    """9:16 vai para os Shorts; o resto, para o YouTube normal."""
    return "youtube-shorts" if formato == "9:16" else "youtube"


def info(plataforma: str | None, formato: str | None = None) -> InfoPlataforma:
    return PLATAFORMAS.get(plataforma or "", PLATAFORMAS[padrao_para(formato)])


def para_formato(formato: str | None) -> list[InfoPlataforma]:
    """Onde um clip desse formato costuma ser publicado."""
    if formato == "9:16":
        return [PLATAFORMAS["youtube-shorts"], PLATAFORMAS["instagram-reels"], PLATAFORMAS["tiktok"]]
    return [PLATAFORMAS["youtube"]]


def y_seguro(y_rel: float, altura_rel: float, zona: Zona) -> float:
    """Centro vertical (0 a 1) mais próximo de y_rel em que um bloco de altura_rel fica fora da zona coberta."""
    minimo = zona.topo + altura_rel / 2
    maximo = 1 - zona.base - altura_rel / 2
    if minimo > maximo:  # bloco maior que o espaço livre: centraliza no que sobra
        return (zona.topo + 1 - zona.base) / 2
    return max(minimo, min(maximo, y_rel))
