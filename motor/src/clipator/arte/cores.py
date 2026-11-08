"""Contas de cor da direção de arte: contraste WCAG, CIELAB, diferença perceptual (CIEDE2000) e ajustes.

Tudo em Python puro (o numpy só entra na análise de imagens, em referencias.py). As fórmulas são as públicas:
luminância relativa e razão de contraste da WCAG 2.x, conversão sRGB -> XYZ (D65) -> CIELAB e a diferença de cor
CIEDE2000 (Sharma, Wu e Dalal, 2005).
"""

from __future__ import annotations

import math
import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
_HEX3 = re.compile(r"^#?([0-9a-fA-F]{3})$")

RGB = tuple[int, int, int]
LAB = tuple[float, float, float]


def e_hex(valor: object) -> bool:
    return isinstance(valor, str) and bool(_HEX.match(valor.strip()) or _HEX3.match(valor.strip()))


def normalizar_hex(valor: str) -> str:
    """'#abc', 'abc', '#AABBCC' -> '#AABBCC'. ValueError se não for cor."""
    v = valor.strip()
    m = _HEX.match(v)
    if m:
        return "#" + m.group(1).upper()
    m = _HEX3.match(v)
    if m:
        return "#" + "".join(c * 2 for c in m.group(1)).upper()
    raise ValueError(f"“{valor}” não é uma cor em hex (#RRGGBB)")


def hex_rgb(valor: str) -> RGB:
    h = normalizar_hex(valor)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in rgb)


# ---- WCAG ---------------------------------------------------------------------------------------------
def _canal_linear(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(cor: str | RGB) -> float:
    r, g, b = hex_rgb(cor) if isinstance(cor, str) else cor
    return 0.2126 * _canal_linear(r) + 0.7152 * _canal_linear(g) + 0.0722 * _canal_linear(b)


def contraste(a: str | RGB, b: str | RGB) -> float:
    """Razão de contraste WCAG (1 a 21)."""
    la, lb = luminancia(a), luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def nivel_wcag(razao: float) -> str:
    """Rótulo curto para a prancha: AAA (≥ 7), AA (≥ 4,5), AA grande (≥ 3, texto grande ou elemento gráfico), falha."""
    if razao >= 7:
        return "AAA"
    if razao >= 4.5:
        return "AA"
    if razao >= 3:
        return "AA grande"
    return "falha"


# ---- CIELAB -------------------------------------------------------------------------------------------
_BRANCO_D65 = (0.95047, 1.0, 1.08883)


def rgb_lab(cor: str | RGB) -> LAB:
    r, g, b = hex_rgb(cor) if isinstance(cor, str) else cor
    rl, gl, bl = _canal_linear(r), _canal_linear(g), _canal_linear(b)
    x = (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / _BRANCO_D65[0]
    y = (0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl) / _BRANCO_D65[1]
    z = (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) / _BRANCO_D65[2]

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_rgb(lab: LAB) -> RGB:
    L, a, b = lab
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    def finv(t: float) -> float:
        return t ** 3 if t > 6 / 29 else 3 * (6 / 29) ** 2 * (t - 4 / 29)

    x, y, z = finv(fx) * _BRANCO_D65[0], finv(fy) * _BRANCO_D65[1], finv(fz) * _BRANCO_D65[2]
    rl = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    gl = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bl = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z

    def gama(c: float) -> int:
        c = max(0.0, min(1.0, c))
        v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return max(0, min(255, round(v * 255)))

    return gama(rl), gama(gl), gama(bl)


def croma(cor: str | RGB) -> float:
    _, a, b = rgb_lab(cor)
    return math.hypot(a, b)


def matiz(cor: str | RGB) -> float:
    """Ângulo de matiz em graus (0–360) no plano a*b*."""
    _, a, b = rgb_lab(cor)
    return math.degrees(math.atan2(b, a)) % 360


def delta_e(c1: str | RGB, c2: str | RGB) -> float:
    """Diferença perceptual CIEDE2000. < 1: igual a olho nu; < 3: quase idênticas; > 10: claramente outras."""
    L1, a1, b1 = rgb_lab(c1)
    L2, a2, b2 = rgb_lab(c2)
    C1, C2 = math.hypot(a1, b1), math.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7))) if Cm else 0.0
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if C1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if C2p else 0.0
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lpm = (L1 + L2) / 2
    Cpm = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hpm = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hpm = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hpm = (h1p + h2p + 360) / 2
    else:
        hpm = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hpm - 30)) + 0.24 * math.cos(math.radians(2 * hpm))
         + 0.32 * math.cos(math.radians(3 * hpm + 6)) - 0.20 * math.cos(math.radians(4 * hpm - 63)))
    dtheta = 30 * math.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7)) if Cpm else 0.0
    Sl = 1 + (0.015 * (Lpm - 50) ** 2) / math.sqrt(20 + (Lpm - 50) ** 2)
    Sc = 1 + 0.045 * Cpm
    Sh = 1 + 0.015 * Cpm * T
    Rt = -math.sin(math.radians(2 * dtheta)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


# ---- ajustes ------------------------------------------------------------------------------------------
def misturar(a: str, b: str, t: float) -> str:
    """t = 0 -> a, t = 1 -> b, interpolado em sRGB (é o que o navegador faz num gradiente)."""
    ra, rb = hex_rgb(a), hex_rgb(b)
    return rgb_hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def deslocar_luminosidade(cor: str, delta_L: float) -> str:
    """Mesma matiz e croma, L* somado de delta_L (o croma encolhe se a cor sair do gamut)."""
    L, a, b = rgb_lab(cor)
    novo = max(0.0, min(100.0, L + delta_L))
    for fator in (1.0, 0.9, 0.8, 0.65, 0.5, 0.3, 0.0):
        rgb = lab_rgb((novo, a * fator, b * fator))
        if abs(rgb_lab(rgb)[0] - novo) < 1.5:
            return rgb_hex(rgb)
    return rgb_hex(lab_rgb((novo, 0, 0)))


def saturar(cor: str, fator: float) -> str:
    """Multiplica o croma (1 = igual). Útil para a primária: vídeo comprimido e tela de celular dessaturam."""
    L, a, b = rgb_lab(cor)
    for f in (fator, fator * 0.95, fator * 0.9, (1 + fator) / 2, 1.0):
        rgb = lab_rgb((L, a * f, b * f))
        Lr, ar, br = rgb_lab(rgb)
        if abs(Lr - L) < 1.5 and abs(math.hypot(ar, br) - math.hypot(a, b) * f) < 3:  # coube no sRGB
            return rgb_hex(rgb)
    return normalizar_hex(cor)


def ajustar_para_contraste(cor: str, fundo: str, alvo: float) -> str:
    """A cor mais parecida com `cor` (mesma matiz, L* mudado) que dá `alvo`:1 sobre `fundo`.

    Vai para o lado que o fundo pede (fundo escuro -> clareia; claro -> escurece). Se nem o extremo bastar,
    devolve o extremo (branco ou preto da mesma matiz).
    """
    cor = normalizar_hex(cor)
    if contraste(cor, fundo) >= alvo:
        return cor
    clarear = luminancia(fundo) < 0.18
    passo = 1.0 if clarear else -1.0
    atual = cor
    for _ in range(100):
        atual = deslocar_luminosidade(atual, passo)
        if contraste(atual, fundo) >= alvo:
            return atual
    return "#FFFFFF" if clarear else "#000000"


def mais_proxima(cor: str, candidatas: dict[str, str]) -> tuple[str, str, float]:
    """(nome, hex, ΔE) da candidata mais próxima de `cor`."""
    melhor = min(candidatas.items(), key=lambda kv: delta_e(cor, kv[1]))
    return melhor[0], melhor[1], delta_e(cor, melhor[1])


def temperatura_rotulo(b_medio: float) -> str:
    if b_medio > 6:
        return "quente"
    if b_medio < -6:
        return "fria"
    return "neutra"
