"""Linha do tempo de um clip: trechos mantidos do vídeo original.

Um clip é [inicio, fim] menos os cortes internos. Este módulo converte tempos
do vídeo original para tempos do clip renderizado e vice-versa.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Timeline:
    trechos: tuple[tuple[float, float], ...]

    @classmethod
    def de_clip(cls, inicio: float, fim: float, cortes: list[tuple[float, float]] | None = None) -> "Timeline":
        trechos = [(inicio, fim)]
        for a, b in sorted(cortes or []):
            a, b = max(a, inicio), min(b, fim)
            if b <= a:
                continue
            novos = []
            for s, e in trechos:
                if b <= s or a >= e:
                    novos.append((s, e))
                    continue
                if a > s:
                    novos.append((s, a))
                if b < e:
                    novos.append((b, e))
            trechos = novos
        trechos = [(round(s, 3), round(e, 3)) for s, e in trechos if e - s >= 0.05]
        if not trechos:
            raise ValueError("Os cortes internos removem o clip inteiro")
        return cls(tuple(trechos))

    @property
    def duracao(self) -> float:
        return sum(e - s for s, e in self.trechos)

    @property
    def inicio(self) -> float:
        return self.trechos[0][0]

    @property
    def fim(self) -> float:
        return self.trechos[-1][1]

    def para_clip(self, t: float) -> float | None:
        """Tempo do original -> tempo do clip; None se cai num trecho cortado."""
        acc = 0.0
        for s, e in self.trechos:
            if s <= t <= e:
                return acc + (t - s)
            if t < s:
                return None
            acc += e - s
        return None

    def para_original(self, t: float) -> float:
        acc = 0.0
        for s, e in self.trechos:
            d = e - s
            if t <= acc + d:
                return s + (t - acc)
            acc += d
        return self.fim

    def mapear_intervalo(self, a: float, b: float) -> tuple[float, float] | None:
        """Intervalo do original -> intervalo do clip (recortado aos trechos mantidos)."""
        ca = cb = None
        acc = 0.0
        for s, e in self.trechos:
            lo, hi = max(a, s), min(b, e)
            if hi > lo:
                if ca is None:
                    ca = acc + (lo - s)
                cb = acc + (hi - s)
            acc += e - s
        if ca is None or cb is None or cb <= ca:
            return None
        return ca, cb
