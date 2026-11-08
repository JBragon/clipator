"""Geometria da tela: zona segura por plataforma, faixa da legenda, área livre, lugar da tarja e canto da thumb.

Tudo em frações do quadro (x e largura da largura; y e altura da altura), num retângulo `Ret`. As margens de cada
app vêm de `clipator.plataformas` (um lugar só para ajustar quando os apps mudam); a zona `uniao` é o pior caso
das plataformas verticais, a que serve quando ninguém diz onde o corte vai sair.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import plataformas as _plat
from .carregar import Resolvida

VERTICAIS = ("youtube-shorts", "instagram-reels", "tiktok")
RESPIRO = 0.012  # entre a faixa da legenda e o resto


@dataclass(frozen=True)
class Ret:
    x: float
    y: float
    w: float
    h: float

    @property
    def x1(self) -> float:
        return self.x + self.w

    @property
    def y1(self) -> float:
        return self.y + self.h

    def px(self, largura: int, altura: int) -> tuple[int, int, int, int]:
        return round(self.x * largura), round(self.y * altura), round(self.x1 * largura), round(self.y1 * altura)

    def contem(self, outro: Ret, folga: float = 1e-6) -> bool:
        return (outro.x >= self.x - folga and outro.y >= self.y - folga and outro.x1 <= self.x1 + folga
                and outro.y1 <= self.y1 + folga)

    def intersecao(self, outro: Ret) -> float:
        """Área em comum (em fração do quadro)."""
        w = min(self.x1, outro.x1) - max(self.x, outro.x)
        h = min(self.y1, outro.y1) - max(self.y, outro.y)
        return max(0.0, w) * max(0.0, h)


def formato_de(largura: int, altura: int) -> str:
    if altura > largura * 1.05:
        return "vertical"
    if largura > altura * 1.05:
        return "horizontal"
    return "quadrado"


def zona_segura(plataforma: str = "uniao", formato: str = "vertical") -> Ret:
    """A área que nenhum botão, nome de canal ou barra de progresso cobre."""
    if formato == "horizontal":
        # 5 % de margem de gráfico (o “title safe” da TV) e, embaixo, o que o player do YouTube cobre
        z = _plat.PLATAFORMAS["youtube"].zona if "youtube" in _plat.PLATAFORMAS else None
        m = 0.05
        esq, topo = max(m, z.esquerda if z else 0), max(m, z.topo if z else 0)
        dir_, base = max(m, z.direita if z else 0), max(0.08, z.base if z else 0)
        return Ret(esq, topo, 1 - esq - dir_, 1 - topo - base)
    if formato == "quadrado":
        return Ret(0.05, 0.06, 0.9, 0.82)
    if plataforma in ("uniao", "", None):
        zs = [_plat.PLATAFORMAS[p].zona for p in VERTICAIS if p in _plat.PLATAFORMAS]
        topo = max(z.topo for z in zs)
        base = max(z.base for z in zs)
        dir_ = max(z.direita for z in zs)
        esq = max(z.esquerda for z in zs)
    else:
        z = _plat.PLATAFORMAS[plataforma].zona
        topo, base, dir_, esq = z.topo, z.base, z.direita, z.esquerda
    return Ret(esq, topo, 1 - esq - dir_, 1 - topo - base)


def faixa_da_legenda(r: Resolvida, formato: str = "vertical", largura: int = 1080, altura: int = 1920,
                     plataforma: str = "uniao") -> Ret:
    """O retângulo que a legenda pode ocupar no pior caso (todas as linhas, contorno ou caixa e sombra)."""
    leg = r.da.legenda
    papel = r.papel(leg.papel)
    lado = min(largura, altura)
    tam = leg.tamanho * lado
    linhas = 1 if leg.estilo == "palavra" else leg.max_linhas
    h = linhas * tam * (papel.entrelinha if papel else 1.1)
    if leg.caixa:
        h += 2 * leg.caixa.respiro[1] * tam
    elif leg.contorno:
        h += 2 * leg.contorno.espessura * tam
    if leg.sombra:
        h += max(0.0, leg.sombra.dy) * tam + leg.sombra.desfoque * tam
    hf = h / altura
    y = leg.y_vertical if formato != "horizontal" else leg.y_horizontal
    zona = zona_segura(plataforma, formato)
    w = min(leg.largura_max, zona.w)
    cx = zona.x + zona.w / 2
    return Ret(cx - w / 2, y - hf / 2, w, hf)


def area_livre(r: Resolvida, formato: str = "vertical", largura: int = 1080, altura: int = 1920,
               plataforma: str = "uniao") -> Ret:
    """A zona segura menos a faixa da legenda: onde tarja, títulos, gráficos e crédito podem ficar.

    Fica o lado maior (acima ou abaixo da faixa). No horizontal sem legenda queimada a zona inteira é livre.
    """
    zona = zona_segura(plataforma, formato)
    faixa = faixa_da_legenda(r, formato, largura, altura, plataforma)
    acima = faixa.y - RESPIRO - zona.y
    abaixo = zona.y1 - (faixa.y1 + RESPIRO)
    if acima <= 0 and abaixo <= 0:
        return zona
    if acima >= abaixo:
        return Ret(zona.x, zona.y, zona.w, max(0.0, acima))
    return Ret(zona.x, faixa.y1 + RESPIRO, zona.w, max(0.0, abaixo))


def posicionar(caixa_w: float, caixa_h: float, posicao: str, dentro: Ret) -> Ret:
    """Uma caixa de tamanho (w, h) numa das sete posições, dentro de um retângulo."""
    if posicao.startswith("superior"):
        y = dentro.y
    elif posicao.startswith("inferior"):
        y = dentro.y1 - caixa_h
    else:
        y = dentro.y + (dentro.h - caixa_h) / 2
    if posicao.endswith("esquerda"):
        x = dentro.x
    elif posicao.endswith("direita"):
        x = dentro.x1 - caixa_w
    else:
        x = dentro.x + (dentro.w - caixa_w) / 2
    return Ret(x, y, caixa_w, caixa_h)


def lugar_da_tarja(r: Resolvida, formato: str = "vertical", largura: int = 1080, altura: int = 1920,
                   plataforma: str = "uniao", reservar_legenda: bool | None = None) -> Ret:
    """Onde o nome e o cargo de quem fala ficam (estimativa do bloco, para validar e para a prancha)."""
    t = r.da.graficos.tarja
    lado = min(largura, altura)
    h = (t.tamanho_nome * 1.15 + t.tamanho_cargo * 1.35) * lado + 2 * 0.018 * lado
    reservar = formato != "horizontal" if reservar_legenda is None else reservar_legenda
    dentro = area_livre(r, formato, largura, altura, plataforma) if reservar else zona_segura(plataforma, formato)
    w = min(dentro.w, 0.62 if formato == "vertical" else 0.42)
    return posicionar(w, min(h / altura, dentro.h), t.posicao, dentro)


def canto_reservado_thumb(r: Resolvida) -> Ret | None:
    th = r.da.thumbnail
    if th.canto_reservado == "nenhum":
        return None
    w, h = th.reserva
    x = 1 - w if th.canto_reservado.endswith("direito") else 0.0
    y = 1 - h if th.canto_reservado.startswith("inferior") else 0.0
    return Ret(x, y, w, h)


def pt_no_celular(fracao: float, largura_tela_pt: float = 390) -> float:
    """Quantos pontos uma fração do lado menor rende numa tela de celular de 390 pt de largura (em pé, 9:16)."""
    return fracao * largura_tela_pt
