"""Efeitos sonoros sintetizados aqui mesmo, com numpy: sem internet, sem banco de sons, sem direito autoral.

Cada efeito é gerado do zero com uma semente fixa (sai sempre igual), normalizado para
pico de -3 dBFS e gravado uma vez em ~/.clipator/sons (ou $CLIPATOR_SONS).

No estilo, o campo `sons` liga um momento do clip a um efeito:

    sons:
      cartela: impacto       # quando a cartela de título entra
      corte: whoosh          # em cada corte interno (jump cut)
      destaque: pop          # nas palavras destacadas da legenda (no máximo uma a cada 2 s)
      inicio: riser          # no começo do clip
    volume_sons: 0.5

O valor é o nome de um efeito daqui ou o caminho de um .wav/.mp3 do canal (assets/).
"""

from __future__ import annotations

import os
import re
import wave
from pathlib import Path

import numpy as np

TAXA = 48000
VERSAO = "v1"  # muda quando a síntese muda, para não reaproveitar o arquivo antigo
PICO = 10 ** (-3 / 20)  # -3 dBFS
EVENTOS = ("inicio", "cartela", "corte", "destaque", "fim")
INTERVALO_DESTAQUE = 2.0
MAX_DESTAQUES = 6


def _t(dur: float) -> np.ndarray:
    return np.arange(int(TAXA * dur)) / TAXA


def _passa_baixa(x: np.ndarray, corte_hz: np.ndarray | float) -> np.ndarray:
    """Filtro de um polo com frequência de corte que pode variar no tempo."""
    corte = np.broadcast_to(np.asarray(corte_hz, dtype=np.float64), x.shape)
    a = np.exp(-2 * np.pi * corte / TAXA)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def _envelope(n: int, ataque: float, queda: float) -> np.ndarray:
    """Sobe em `ataque` (fração) e cai em curva até o fim."""
    t = np.linspace(0, 1, n)
    sobe = np.clip(t / max(ataque, 1e-3), 0, 1)
    desce = np.clip((1 - t) / max(1 - ataque, 1e-3), 0, 1) ** queda
    return sobe * desce


def _whoosh(rng: np.random.Generator) -> np.ndarray:
    t = _t(0.6)
    ruido = rng.standard_normal(len(t))
    corte = 300 + 5000 * np.sin(np.pi * t / t[-1]) ** 2  # abre e fecha o filtro: o "vento" passando
    return _passa_baixa(ruido, corte) * _envelope(len(t), 0.45, 1.6)


def _swoosh_reverso(rng: np.random.Generator) -> np.ndarray:
    x = _whoosh(rng)[: int(TAXA * 0.45)]
    x = x[::-1].copy()
    x[-int(TAXA * 0.01):] *= np.linspace(1, 0, int(TAXA * 0.01))
    return x


def _impacto(rng: np.random.Generator) -> np.ndarray:
    t = _t(0.9)
    freq = 45 + 75 * np.exp(-t * 9)  # cai de 120 Hz para 45 Hz
    corpo = np.sin(2 * np.pi * np.cumsum(freq) / TAXA) * np.exp(-t * 5)
    estalo = _passa_baixa(rng.standard_normal(len(t)), 1800) * np.exp(-t * 60)
    return corpo + 0.6 * estalo


def _riser(rng: np.random.Generator) -> np.ndarray:
    t = _t(1.5)
    freq = 200 * (6 ** (t / t[-1]))  # 200 Hz -> 1200 Hz
    fase = 2 * np.pi * np.cumsum(freq) / TAXA
    tom = 0.6 * np.sin(fase) + 0.25 * np.sin(2 * fase) + 0.12 * np.sin(3 * fase)
    ar = _passa_baixa(rng.standard_normal(len(t)), 400 + 6000 * (t / t[-1]) ** 2)
    env = (t / t[-1]) ** 2
    x = (tom + 0.8 * ar) * env
    x[-int(TAXA * 0.03):] *= np.linspace(1, 0, int(TAXA * 0.03))
    return x


def _pop(rng: np.random.Generator) -> np.ndarray:
    t = _t(0.15)
    freq = 300 + 400 * np.exp(-t * 40)
    return np.sin(2 * np.pi * np.cumsum(freq) / TAXA) * np.exp(-t * 35)


def _click(rng: np.random.Generator) -> np.ndarray:
    t = _t(0.05)
    ruido = rng.standard_normal(len(t))
    agudo = ruido - _passa_baixa(ruido, 2500)  # tira o grave: fica o estalo
    return _passa_baixa(agudo, 6000) * np.exp(-t * 120)


def _ding(rng: np.random.Generator) -> np.ndarray:
    t = _t(1.2)
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d)
            for f, a, d in ((1320, 1.0, 3.5), (2640, 0.45, 5.0), (3960, 0.2, 7.0), (1987, 0.15, 6.0)))
    x[: int(TAXA * 0.004)] *= np.linspace(0, 1, int(TAXA * 0.004))
    return x


def _glitch(rng: np.random.Generator) -> np.ndarray:
    pedaco = int(TAXA * 0.025)
    partes = []
    for k in range(16):
        tt = np.arange(pedaco) / TAXA
        if k % 4 == 3:
            partes.append(np.zeros(pedaco))  # buraco: o "engasgo"
            continue
        f = float(rng.choice([180, 340, 760, 1400, 2200]))
        quadrada = np.sign(np.sin(2 * np.pi * f * tt))
        partes.append(0.6 * quadrada + 0.4 * rng.standard_normal(pedaco))
    x = np.concatenate(partes)
    return _passa_baixa(x, 7000) * _envelope(len(x), 0.05, 0.7)


SINTESES = {
    "whoosh": _whoosh, "swoosh-reverso": _swoosh_reverso, "impacto": _impacto, "riser": _riser,
    "pop": _pop, "click": _click, "ding": _ding, "glitch": _glitch,
}
NOMES = tuple(SINTESES)


def sintetizar(nome: str) -> np.ndarray:
    """O efeito como float32 mono a 48 kHz, com pico de -3 dBFS. Sempre o mesmo para o mesmo nome."""
    if nome not in SINTESES:
        raise KeyError(f"Efeito sonoro desconhecido: {nome}. Tem: {', '.join(NOMES)}")
    semente = sum(ord(c) * (i + 1) for i, c in enumerate(nome))
    x = SINTESES[nome](np.random.default_rng(semente)).astype(np.float64)
    x -= x.mean()
    pico = float(np.max(np.abs(x))) or 1.0
    return (x / pico * PICO).astype(np.float32)


def pasta_sons() -> Path:
    p = Path(os.environ.get("CLIPATOR_SONS", Path.home() / ".clipator" / "sons"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def caminho(nome: str) -> Path:
    """O .wav do efeito, gerado na primeira vez e reaproveitado depois."""
    destino = pasta_sons() / f"{nome}-{VERSAO}.wav"
    if not destino.exists():
        x = sintetizar(nome)
        tmp = destino.with_suffix(".tmp")
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TAXA)
            wf.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        os.replace(tmp, destino)
    return destino


def resolver(valor: str, bases: list[Path]) -> Path | None:
    """Nome de efeito daqui ("whoosh", "sintetico:whoosh") ou arquivo do canal/workspace."""
    nome = valor.split(":", 1)[1] if valor.startswith("sintetico:") else valor
    if nome in SINTESES:
        return caminho(nome)
    for base in bases:
        p = base / valor
        if p.is_file():
            return p
    return None


def eventos(sons: dict[str, str], duracao: float, trechos: list[tuple[float, float]], palavras_clip: list[dict],
            destaque: re.Pattern | None, cartela: bool) -> list[tuple[str, float]]:
    """(evento, segundo do clip) de cada efeito que o estilo pede."""
    out: list[tuple[str, float]] = []
    if sons.get("inicio"):
        out.append(("inicio", 0.0))
    if sons.get("cartela") and cartela:
        out.append(("cartela", 0.0))
    if sons.get("corte") and len(trechos) > 1:
        acc = 0.0
        for s, e in trechos[:-1]:
            acc += e - s
            out.append(("corte", round(max(0.0, acc - 0.15), 3)))  # o whoosh começa um pouco antes da emenda
    if sons.get("destaque") and destaque is not None:
        ultimo, n = -99.0, 0
        for w in palavras_clip:
            if n >= MAX_DESTAQUES:
                break
            if destaque.search(w["texto"]) and w["inicio"] - ultimo >= INTERVALO_DESTAQUE:
                out.append(("destaque", round(w["inicio"], 3)))
                ultimo, n = w["inicio"], n + 1
    if sons.get("fim"):
        out.append(("fim", max(0.0, duracao - 1.0)))
    return [(ev, t) for ev, t in out if t < duracao]


def filtro_mix(eventos_t: list[tuple[str, float]], arquivos: dict[str, Path], primeiro_indice: int, voz: str,
               volume: float, saida: str = "[aout]") -> tuple[list[str], list[str]]:
    """Entradas extras do FFmpeg e o pedaço do grafo que soma os efeitos à voz.

    O limitador no fim segura o pico abaixo de -0,5 dBFS (a voz já vem do loudnorm)."""
    entradas, partes, rotulos = [], [], []
    for k, (ev, t) in enumerate(eventos_t):
        entradas += ["-i", str(arquivos[ev])]
        ms = int(round(t * 1000))
        partes.append(f"[{primeiro_indice + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                      f"adelay={ms}:all=1,volume={volume:.3f}[sfx{k}]")
        rotulos.append(f"[sfx{k}]")
    partes.append(f"{voz}{''.join(rotulos)}amix=inputs={len(rotulos) + 1}:duration=first:normalize=0,"
                  f"alimiter=limit=0.944[{saida.strip('[]')}]")
    return entradas, partes
