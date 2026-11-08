"""Peças low-poly da "Maquete explicativa": objetos facetados em perspectiva isométrica, desenhados em SVG.

Cada peça é montada com primitivas daqui (caixa, prisma, cone, gema e placa extrudada), projetadas em
isometria num viewBox 0 0 100 100 com o chão em (50, 72). As faces têm tons fixos: topo claro (f1), frente
esquerda média (f2), lado direito escuro (f3) e um tom intermediário (f4) nas faces inclinadas. A parte de
destaque de cada peça leva a classe "a" e pega a cor da camada (a IA escolhe: principal, certo, errado…);
o resto fica no branco e cinza da ficha. Os nomes são os mesmos da biblioteca de traço (desenho.py), então o
roteiro e a composição da IA valem para as duas.
"""

from __future__ import annotations

import math

Ponto = tuple[float, float, float]
_C = (50.0, 72.0)


def _iso(x: float, y: float, z: float) -> tuple[float, float]:
    return _C[0] + (x - y) * 0.866, _C[1] + (x + y) * 0.5 - z


def _poly(pts: list[tuple[float, float]], cls: str) -> str:
    return f'<polygon class="{cls}" points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>'


def _face(pts3: list[Ponto], cls: str) -> str:
    return _poly([_iso(*p) for p in pts3], cls)


class Peca:
    """Junta as partes e desenha de trás para frente (pela profundidade x + y)."""

    def __init__(self) -> None:
        self.partes: list[tuple[float, int, str]] = []

    def _add(self, prof: float, svg: str) -> None:
        self.partes.append((prof, len(self.partes), svg))

    def sombra(self, x: float, y: float, r: float) -> "Peca":
        cx, cy = _iso(x, y, 0)
        self._add(-999, f'<ellipse class="sombra" cx="{cx:.1f}" cy="{cy:.1f}" rx="{r * 1.25:.1f}" ry="{r * 0.62:.1f}"/>')
        return self

    def caixa(self, x: float, y: float, z: float, w: float, d: float, h: float, a: bool = False, frente: str = "") -> "Peca":
        x0, x1, y0, y1, z0, z1 = x - w / 2, x + w / 2, y - d / 2, y + d / 2, z, z + h
        k = " a" if a else ""
        svg = (_face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], "f1" + k)
               + _face([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], "f2" + k)
               + _face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], "f3" + k) + frente)
        self._add(x + y + z * 0.02, svg)
        return self

    def prisma(self, x: float, y: float, z: float, r: float, h: float, n: int = 6, a: bool = False, giro: float = 0.0) -> "Peca":
        """Prisma de n lados em pé (cilindro facetado)."""
        k = " a" if a else ""
        angs = [giro + 2 * math.pi * i / n for i in range(n)]
        base = [(x + r * math.cos(t), y + r * math.sin(t)) for t in angs]
        lados = []
        for i in range(n):
            (ax, ay), (bx, by) = base[i], base[(i + 1) % n]
            mid = giro + 2 * math.pi * (i + 0.5) / n
            nx, ny = math.cos(mid), math.sin(mid)
            if nx + ny <= 0.05:  # face virada para trás
                continue
            cls = "f2" if ny - nx > 0.5 else "f3" if nx - ny > 0.5 else "f4"
            lados.append((nx + ny, _face([(ax, ay, z), (bx, by, z), (bx, by, z + h), (ax, ay, z + h)], cls + k)))
        topo = _face([(px, py, z + h) for px, py in base], "f1" + k)
        self._add(x + y + z * 0.02, "".join(s for _, s in sorted(lados)) + topo)
        return self

    def cone(self, x: float, y: float, z: float, r: float, h: float, n: int = 6, a: bool = False, giro: float = 0.0) -> "Peca":
        """Pirâmide/cone facetado com a ponta para cima (h < 0: ponta para baixo)."""
        k = " a" if a else ""
        topo = (x, y, z + h)
        angs = [giro + 2 * math.pi * i / n for i in range(n)]
        base = [(x + r * math.cos(t), y + r * math.sin(t), z) for t in angs]
        faces = []
        for i in range(n):
            mid = giro + 2 * math.pi * (i + 0.5) / n
            nx, ny = math.cos(mid), math.sin(mid)
            if h > 0 and nx + ny < -0.6:
                continue
            cls = "f1" if nx + ny < 0 else "f2" if ny - nx > 0.4 else "f3" if nx - ny > 0.4 else "f4"
            faces.append((nx + ny, _face([base[i], base[(i + 1) % n], topo], cls + k)))
        if h < 0:  # ponta para baixo: a boca (em cima) aparece
            faces.append((99, _face(base, "f1" + k)))
        self._add(x + y + z * 0.02, "".join(s for _, s in sorted(faces)))
        return self

    def gema(self, x: float, y: float, z: float, r: float, n: int = 8, a: bool = False, acentos: tuple[int, ...] = ()) -> "Peca":
        """Esfera low-poly: um leque de triângulos com o brilho em cima à esquerda."""
        cx, cy = _iso(x, y, z)
        luz = (cx - r * 0.28, cy - r * 0.3)
        borda = [(cx + r * math.cos(2 * math.pi * i / n - math.pi / 2), cy + r * math.sin(2 * math.pi * i / n - math.pi / 2))
                 for i in range(n)]
        aneis = [(cx + r * 0.55 * math.cos(2 * math.pi * (i + 0.5) / n - math.pi / 2),
                  cy + r * 0.55 * math.sin(2 * math.pi * (i + 0.5) / n - math.pi / 2)) for i in range(n)]
        svg = []
        for i in range(n):
            mid = 2 * math.pi * (i + 0.5) / n - math.pi / 2
            lx, ly = math.cos(mid), math.sin(mid)
            tom = "f1" if lx + ly < -0.4 else "f2" if lx + ly < 0.5 else "f3"
            tom_in = "f1" if lx + ly < 0.3 else "f4"
            k = " a" if (a or i in acentos) else ""
            svg.append(_poly([borda[i], borda[(i + 1) % n], aneis[i]], tom + k))
            svg.append(_poly([aneis[i], borda[(i + 1) % n], aneis[(i + 1) % n]], tom_in + k))
            svg.append(_poly([luz, aneis[i], aneis[(i + 1) % n]], ("f1" if lx + ly < 0.6 else "f4") + k))
        self._add(x + y + z * 0.02, "".join(svg))
        return self

    def placa(self, partes: list[list[tuple[float, float]]], prof: float = 4.0, a: bool = True, z: float = 99) -> "Peca":
        """Forma plana (em coordenadas da tela) com espessura para trás: ícones como check, X, seta, estrela."""
        k = " a" if a else ""
        dx, dy = prof * 0.62, prof * 0.42
        fundo, frente = [], []
        for pts in partes:
            for s in range(1, 4):
                f = s / 3
                fundo.append(_poly([(px + dx * f, py + dy * f) for px, py in pts], "f3" + k))
            cx = sum(p[0] for p in pts) / len(pts) - 1.5
            cy = sum(p[1] for p in pts) / len(pts) - 1.5
            for i in range(len(pts)):
                p1, p2 = pts[i], pts[(i + 1) % len(pts)]
                mx, my = (p1[0] + p2[0]) / 2 - cx, (p1[1] + p2[1]) / 2 - cy
                tom = "f1" if mx + my < 0 else "f4" if abs(mx + my) < 6 else "f2"
                frente.append(_poly([(cx, cy), p1, p2], tom + k))
        self._add(z, "".join(fundo) + "".join(frente))
        return self

    def svg(self) -> str:
        return "".join(s for _, _, s in sorted(self.partes))


def _barra(x1: float, y1: float, x2: float, y2: float, e: float) -> list[tuple[float, float]]:
    """Retângulo de espessura e entre dois pontos da tela (para montar ícones com placas)."""
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy) or 1
    ox, oy = -dy / n * e / 2, dx / n * e / 2
    return [(x1 + ox, y1 + oy), (x2 + ox, y2 + oy), (x2 - ox, y2 - oy), (x1 - ox, y1 - oy)]


def _ngono(cx: float, cy: float, r: float, n: int, giro: float = -math.pi / 2) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(giro + 2 * math.pi * i / n), cy + r * math.sin(giro + 2 * math.pi * i / n)) for i in range(n)]


def _pessoa(bracos: bool = False, cheia: bool = False) -> str:
    p = Peca().sombra(0, 0, 12)
    p.caixa(-2.5, 2.5, 0, 4, 4, 15).caixa(2.5, -2.5, 0, 4, 4, 15)
    p.prisma(0, 0, 15, 9 if cheia else 7.5, 17, 6, a=True)
    if bracos:
        p.caixa(-8, 8, 25, 3, 3, 14).caixa(8, -8, 25, 3, 3, 14)
    else:
        p.caixa(-7.5, 7.5, 18, 3, 3, 12).caixa(7.5, -7.5, 18, 3, 3, 12)
    return p.gema(0, 0, 41, 8.5).svg()


def _pecas() -> dict[str, str]:
    j = "f3"  # janelas e detalhes escuros
    pc: dict[str, str] = {}
    pc["boneco"] = _pessoa()
    pc["boneco_bracos"] = _pessoa(bracos=True)
    pc["pessoa"] = _pessoa(cheia=True)
    casa = Peca().sombra(0, 0, 24).caixa(0, 0, 0, 30, 24, 18)
    telhado = (_face([(-17, -14, 18), (17, -14, 18), (17, 0, 32), (-17, 0, 32)], "f4 a")
               + _face([(-17, 0, 32), (17, 0, 32), (17, 14, 18), (-17, 14, 18)], "f2 a")
               + _face([(17, -14, 18), (17, 14, 18), (17, 0, 32)], "f3"))
    casa._add(50, telhado)
    casa._add(60, _face([(-3, 12.1, 0), (5, 12.1, 0), (5, 12.1, 11), (-3, 12.1, 11)], j))
    pc["casa"] = casa.svg()
    pr = Peca().sombra(0, 0, 18).caixa(0, 0, 0, 22, 22, 52)
    janelas = "".join(_face([(xa, 11.1, z), (xa + 4, 11.1, z), (xa + 4, 11.1, z + 5), (xa, 11.1, z + 5)], j)
                      for xa in (-8, 0) for z in range(8, 48, 9))
    pr._add(40, janelas)
    pc["predio"] = pr.caixa(0, 0, 52, 8, 8, 5, a=True).svg()
    pc["predios"] = (Peca().sombra(0, 0, 30).caixa(-12, -10, 0, 14, 14, 30).caixa(10, -12, 0, 14, 14, 44, a=True)
                     .caixa(-10, 12, 0, 14, 14, 22).caixa(12, 10, 0, 12, 12, 34).svg())
    loja = Peca().sombra(0, 0, 24).caixa(0, 0, 0, 30, 22, 20)
    loja._add(40, _face([(-16, 11, 20), (16, 11, 20), (16, 18, 14), (-16, 18, 14)], "f4 a")
              + _face([(-4, 11.1, 0), (4, 11.1, 0), (4, 11.1, 12), (-4, 11.1, 12)], j))
    pc["loja"] = loja.svg()
    pc["celular"] = _celular()
    comp = Peca().sombra(0, 0, 20).caixa(0, 0, 0, 26, 16, 3).caixa(0, -2, 3, 5, 5, 8)
    comp.caixa(0, -2, 11, 32, 4, 22)
    comp._add(60, _face([(-14, 0.1, 14), (14, 0.1, 14), (14, 0.1, 31), (-14, 0.1, 31)], "f1 a"))
    pc["computador"] = comp.svg()
    pc["moeda"] = Peca().sombra(0, 0, 16).prisma(0, 0, 0, 17, 5, 10, a=True).prisma(0, 0, 5, 9, 1.5, 10).svg()
    pc["nota"] = (Peca().sombra(0, 0, 20).caixa(0, 0, 0, 38, 20, 2.5, a=True).caixa(0, 0, 2.5, 30, 14, 1)
                  .prisma(0, 0, 3.5, 4, 1, 6, a=True).svg())
    pc["saco_dinheiro"] = Peca().sombra(0, 0, 16).gema(0, 0, 16, 16, 9, a=True).cone(0, 0, 30, 5, 8, 5, a=True).svg()
    bal = Peca().sombra(0, 0, 22).caixa(0, 0, 0, 20, 12, 4).caixa(0, 0, 4, 4, 4, 34)
    bal.caixa(0, 0, 38, 46, 4, 3, a=True)
    bal.prisma(-20, 0, 18, 9, 2, 8).prisma(20, 0, 22, 9, 2, 8)
    pc["balanca"] = bal.svg()
    pc["grafico_sobe"] = (Peca().sombra(0, 0, 26).caixa(0, 0, 0, 44, 16, 2).caixa(-15, 0, 2, 8, 8, 10).caixa(-5, 0, 2, 8, 8, 20)
                          .caixa(5, 0, 2, 8, 8, 31).caixa(15, 0, 2, 8, 8, 44, a=True).svg())
    pc["grafico_desce"] = (Peca().sombra(0, 0, 26).caixa(0, 0, 0, 44, 16, 2).caixa(-15, 0, 2, 8, 8, 44).caixa(-5, 0, 2, 8, 8, 30)
                           .caixa(5, 0, 2, 8, 8, 19).caixa(15, 0, 2, 8, 8, 9, a=True).svg())
    pc["seta"] = Peca().placa([[(14, 44), (54, 44), (54, 32), (82, 52), (54, 72), (54, 60), (14, 60)]]).svg()
    pc["balao"] = Peca().placa([_ngono(50, 44, 30, 10, 0), [(30, 62), (44, 68), (24, 84)]], a=False).svg()
    pc["check"] = Peca().placa([_barra(18, 50, 40, 72, 13), _barra(36, 72, 82, 24, 13)]).svg()
    pc["x"] = Peca().placa([_barra(22, 22, 78, 78, 14), _barra(78, 22, 22, 78, 14)]).svg()
    pc["interrogacao"] = Peca().placa([_barra(30, 30, 42, 16, 11), _barra(40, 17, 62, 17, 11), _barra(60, 16, 70, 32, 11),
                                        _barra(70, 30, 52, 50, 11), _barra(52, 48, 52, 62, 11), _ngono(52, 80, 7, 6)]).svg()
    pc["exclamacao"] = Peca().placa([_barra(50, 14, 50, 62, 15), _ngono(50, 80, 8, 6)]).svg()
    rel = Peca().placa([_ngono(48, 48, 34, 12)], a=False)
    rel.placa([_barra(48, 48, 48, 26, 5), _barra(48, 48, 64, 56, 5)], prof=1.5, z=200)
    pc["relogio"] = rel.svg()
    cal = Peca().sombra(0, 0, 18).caixa(0, 0, 0, 30, 6, 32)
    cal._add(40, _face([(-14, 3.1, 24), (14, 3.1, 24), (14, 3.1, 31), (-14, 3.1, 31)], "f1 a")
             + "".join(_face([(xa, 3.1, z), (xa + 4, 3.1, z), (xa + 4, 3.1, z + 4), (xa, 3.1, z + 4)], "f4")
                       for xa in (-11, -3, 5) for z in (6, 14)))
    pc["calendario"] = cal.svg()
    pc["globo"] = Peca().sombra(0, 0, 18).caixa(0, 0, 0, 16, 16, 3).caixa(0, 0, 3, 3, 3, 8).gema(0, 0, 32, 22, 10, acentos=(1, 2, 5, 8)).svg()
    lupa = Peca().placa([_barra(62, 62, 84, 84, 10)])
    anel = _ngono(42, 42, 26, 10)
    lupa.placa([[*anel]], a=False, z=150)
    lupa._add(160, _poly(_ngono(42, 42, 17, 10), "f3"))
    pc["lupa"] = lupa.svg()
    pc["trofeu"] = (Peca().sombra(0, 0, 16).caixa(0, 0, 0, 20, 20, 5).caixa(0, 0, 5, 5, 5, 12)
                    .cone(0, 0, 40, 15, -23, 8, a=True).svg())
    pc["coracao"] = Peca().placa([[(50, 84), (16, 50), (14, 32), (24, 18), (40, 18), (50, 30), (60, 18), (76, 18), (86, 32), (84, 50)]]).svg()
    al = Peca().placa([[(50, 12), (90, 82), (10, 82)]])
    al.placa([_barra(50, 34, 50, 60, 9), _ngono(50, 72, 5, 6)], a=False, prof=1.5, z=200)
    pc["alerta"] = al.svg()
    cad = Peca().placa([_barra(34, 46, 34, 26, 8), _barra(34, 26, 46, 16, 8), _barra(46, 16, 58, 26, 8), _barra(58, 26, 58, 46, 8)], a=False)
    cad.placa([[(22, 44), (72, 44), (72, 86), (22, 86)]], z=150)
    pc["cadeado"] = cad.svg()
    carro = Peca().sombra(0, 0, 26).caixa(0, 0, 4, 40, 18, 11, a=True).caixa(-2, 0, 15, 22, 16, 9)
    for xr in (-12, 12):
        carro.gema(xr, 9, 4, 5, 6)
    pc["carro"] = carro.svg()
    barco = Peca().sombra(0, 0, 26).caixa(0, 0, 0, 40, 16, 8, a=True).caixa(-4, 0, 8, 18, 12, 8).caixa(-4, 0, 16, 12, 9, 6)
    pc["barco"] = barco.caixa(8, 0, 8, 2, 2, 26).svg()
    pc["lampada"] = Peca().sombra(0, 0, 10).prisma(0, 0, 0, 7, 12, 6).prisma(0, 0, 12, 9, 3, 6).gema(0, 0, 32, 16, 9, a=True).svg()
    meg = Peca().placa([[(18, 40), (34, 40), (80, 18), (80, 82), (34, 60), (18, 60)]])
    meg.placa([_barra(34, 62, 40, 80, 8)], a=False, z=50)
    pc["megafone"] = meg.svg()
    livro = Peca().sombra(0, 0, 20).caixa(0, 0, 0, 30, 24, 3, a=True).caixa(0.5, 0, 3, 28, 22, 5).caixa(0, 0, 8, 30, 24, 3, a=True)
    pc["livro"] = livro.svg()
    pc["raio"] = Peca().placa([[(58, 8), (24, 54), (46, 54), (40, 92), (76, 42), (54, 42)]]).svg()
    estrela = [(50 + (34 if i % 2 == 0 else 14) * math.cos(-math.pi / 2 + i * math.pi / 5),
                50 + (34 if i % 2 == 0 else 14) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]
    pc["estrela"] = Peca().placa([estrela]).svg()
    doc = Peca().sombra(0, 0, 16).caixa(0, 0, 0, 24, 4, 34)
    doc._add(40, "".join(_face([(-9, 2.1, z), (9, 2.1, z), (9, 2.1, z + 2), (-9, 2.1, z + 2)], "f4") for z in (6, 11, 16, 21))
             + _face([(4, 2.1, 27), (11, 2.1, 27), (11, 2.1, 33), (4, 2.1, 33)], "f1 a"))
    pc["documento"] = doc.svg()
    porta = Peca().sombra(0, 0, 16).caixa(0, 0, 0, 24, 6, 42)
    porta._add(40, _face([(-8, 3.1, 0), (8, 3.1, 0), (8, 3.1, 36), (-8, 3.1, 36)], "f2 a") + _face([(4, 3.2, 17), (6, 3.2, 17), (6, 3.2, 20), (4, 3.2, 20)], "f1"))
    pc["porta"] = porta.svg()
    return pc


def _celular() -> str:
    p = Peca().sombra(0, 0, 13).caixa(0, 0, 0, 22, 5, 42)
    p._add(40, _face([(-9, 2.6, 4), (9, 2.6, 4), (9, 2.6, 38), (-9, 2.6, 38)], "f1 a"))
    return p.svg()


PECAS_MAQUETE: dict[str, str] = _pecas()

CSS_MAQUETE = """
/* peças facetadas: os tons das faces vêm da ficha; a parte de destaque pega a cor da camada */
.palco .f1, .palco-fixo .f1, symbol .f1 { fill: var(--lp-claro); }
.palco .f2, symbol .f2 { fill: var(--lp-medio); }
.palco .f4, symbol .f4 { fill: var(--lp-meio); }
.palco .f3, symbol .f3 { fill: var(--lp-escuro); }
.palco .a.f1, symbol .a.f1 { fill: color-mix(in srgb, currentColor 92%, white); }
.palco .a.f4, symbol .a.f4 { fill: color-mix(in srgb, currentColor 84%, black); }
.palco .a.f2, symbol .a.f2 { fill: currentColor; }
.palco .a.f3, symbol .a.f3 { fill: color-mix(in srgb, currentColor 62%, black); }
symbol polygon { stroke: rgba(0, 0, 0, .08); stroke-width: .25; stroke-linejoin: round; }
symbol .sombra { fill: #000; opacity: .32; }
"""
