"""A geometria da tela com animação e vídeo: um cálculo só, usado pela prévia, pelo render e pelo renderizador da arte.

Daqui saem o retângulo da janela do vídeo (no canto que o usuário escolheu), a faixa da legenda, a área segura da
plataforma e o maior retângulo livre, que é onde a arte põe o foco da explicação. Quem desenha nunca recalcula isso.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, get_args

from .models import CantoJanela, DirecaoArte, Legenda

CANTOS: tuple[str, ...] = get_args(CantoJanela)
PROPORCAO_JANELA = 0.75  # largura / altura: retrato, cabe o rosto com folga em qualquer canto
ALTURA_MAX_JANELA = 0.32  # fração da altura do quadro
MARGEM = 0.04  # fração da largura


def _par(v: float) -> int:
    v = int(round(v))
    return v - v % 2


@dataclass(frozen=True)
class Ret:
    x: int
    y: int
    w: int
    h: int

    @property
    def x1(self) -> int:
        return self.x + self.w

    @property
    def y1(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return max(0, self.w) * max(0, self.h)

    def cruza(self, o: "Ret") -> bool:
        return self.x < o.x1 and o.x < self.x1 and self.y < o.y1 and o.y < self.y1

    def contem(self, o: "Ret") -> bool:
        return self.x <= o.x and self.y <= o.y and o.x1 <= self.x1 and o.y1 <= self.y1

    def corte(self, o: "Ret") -> "Ret":
        x, y = max(self.x, o.x), max(self.y, o.y)
        return Ret(x, y, max(0, min(self.x1, o.x1) - x), max(0, min(self.y1, o.y1) - y))

    def recuo(self, m: int) -> "Ret":
        return Ret(self.x + m, self.y + m, max(0, self.w - 2 * m), max(0, self.h - 2 * m))


def faixa_legenda(legenda: Legenda | None, out_w: int, out_h: int, zona: Any) -> tuple[int, int] | None:
    """(topo, base) em pixels da faixa que a legenda ocupa; None quando o estilo não tem legenda."""
    if legenda is None or legenda.modo == "nenhuma":
        return None
    from .plataformas import y_seguro
    from .subtitles import POSICOES_Y

    fs = legenda.tamanho * min(out_w, out_h) / 1080
    alto = max(1, legenda.linhas) * fs * 1.25 * 1.5  # uma folga para a linha que quebra e para o pop da palavra
    y = legenda.altura_relativa if legenda.altura_relativa is not None else POSICOES_Y.get(legenda.posicao, 0.68)
    if zona is not None:
        y = y_seguro(y, alto / out_h, zona)
    return int(y * out_h - alto / 2), int(y * out_h + alto / 2)


def retangulo_janela(out_w: int, out_h: int, escala: float, canto: str, zona: Any = None, faixa: tuple[int, int] | None = None) -> Ret:
    """A janela do vídeo no canto pedido, dentro da zona segura e fora da legenda. O canto nunca muda sozinho."""
    if canto not in CANTOS:
        raise ValueError(f"Canto inválido: {canto}")
    m = _par(out_w * MARGEM)
    embaixo, direita = canto.startswith("inferior"), canto.endswith("direito")
    topo = max(m, int(zona.topo * out_h)) if zona is not None else m
    base = out_h - (max(m, int(zona.base * out_h)) if zona is not None else m)
    if faixa is not None:
        if embaixo and faixa[0] < base and faixa[1] > out_h * 0.4:
            base = faixa[0] - m // 2  # a janela fica acima da legenda
        elif not embaixo and faixa[1] > topo and faixa[0] < out_h * 0.4:
            topo = faixa[1] + m // 2
    w = out_w * escala
    h = min(w / PROPORCAO_JANELA, out_h * ALTURA_MAX_JANELA, max(out_h * 0.1, base - topo))
    w = h * PROPORCAO_JANELA
    w, h = _par(w), _par(h)
    esquerda = max(m, int(zona.esquerda * out_w)) if zona is not None else m
    y = _par(base - h - 1) if embaixo else _par(topo + 1)  # arredonda para dentro da área segura
    fim_direita = out_w - m
    if zona is not None and y + h > out_h * 0.5:  # os botões da plataforma só cobrem a metade de baixo
        fim_direita = min(fim_direita, int(out_w * (1 - zona.direita)))
    x = _par(fim_direita - w - 1) if direita else _par(esquerda + 1)
    return Ret(x, y, w, h)


def maior_livre(area: Ret, ocupados: list[Ret], largura_min: int = 0) -> Ret:
    """O maior retângulo dentro de `area` que não cruza nenhum dos `ocupados` (busca nas linhas formadas pelas bordas)."""
    xs = sorted({area.x, area.x1, *(v for o in ocupados for v in (o.x, o.x1) if area.x < v < area.x1)})
    ys = sorted({area.y, area.y1, *(v for o in ocupados for v in (o.y, o.y1) if area.y < v < area.y1)})
    melhor = Ret(area.x, area.y, 0, 0)
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1:]:
            if x1 - x0 < largura_min:
                continue
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1:]:
                    r = Ret(x0, y0, x1 - x0, y1 - y0)
                    if r.area > melhor.area and not any(r.cruza(o) for o in ocupados):
                        melhor = r
    return melhor


@dataclass
class Geometria:
    """Tudo em pixels do quadro. `exclusoes`: onde a arte não pode pôr foco nem rótulo."""

    layout: str
    largura: int
    altura: int
    arte: Ret
    seguro: Ret
    foco: Ret
    video: Ret | None = None
    faixa: tuple[int, int] | None = None
    canto: str | None = None
    exclusoes: list[Ret] = field(default_factory=list)

    def para_js(self) -> dict[str, Any]:
        """Os retângulos relativos à arte: é neles que o script calcula câmera e rótulos."""
        def rel(r: Ret) -> dict[str, int]:
            return {"x": r.x - self.arte.x, "y": r.y - self.arte.y, "w": r.w, "h": r.h}

        return {"layout": self.layout, "canto": self.canto, "largura": self.largura, "altura": self.altura, "arte": asdict(self.arte),
                "seguro": rel(self.seguro), "foco": rel(self.foco), "exclusoes": [rel(e) for e in self.exclusoes]}


def geometria(da: DirecaoArte, out_w: int, out_h: int, zona: Any = None, legenda: Legenda | None = None) -> Geometria:
    """A composição do layout escolhido. Em `em-cima` a arte é a parte de cima; em `janela`, a tela inteira."""
    faixa = faixa_legenda(legenda, out_w, out_h, zona)
    m = _par(out_w * MARGEM)
    topo = max(m, int(zona.topo * out_h)) if zona is not None else m
    esq = max(m, int(zona.esquerda * out_w)) if zona is not None else m
    base = out_h - (max(m, int(zona.base * out_h)) if zona is not None else m)
    canto = None
    if da.layout == "em-cima":
        h = _par(out_h * da.proporcao)
        arte, video = Ret(0, 0, out_w, h), Ret(0, h, out_w, out_h - h)
        direita = out_w - m
        ocupados = [video]
    else:
        arte = Ret(0, 0, out_w, out_h)
        canto = da.janela_canto or "inferior-direito"
        video = retangulo_janela(out_w, out_h, da.janela_escala, canto, zona, faixa)
        direita = out_w - (max(m, int(zona.direita * out_w)) if zona is not None else m)
        ocupados = [video]
    seguro = Ret(esq, topo, direita - esq, min(base, arte.y1 - m) - topo).corte(arte)
    if faixa is not None and da.layout != "em-cima":
        ocupados.append(Ret(0, faixa[0], out_w, faixa[1] - faixa[0]))
    folga = _par(out_w * 0.02)
    exp = [Ret(o.x - folga, o.y - folga, o.w + 2 * folga, o.h + 2 * folga) for o in ocupados]
    foco = maior_livre(seguro, exp, int(seguro.w * 0.45))
    return Geometria(da.layout, out_w, out_h, arte, seguro, foco, video, faixa, canto, exp)
