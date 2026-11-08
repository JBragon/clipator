"""Relato ao vivo do que está acontecendo num job, para a tela mostrar passo a passo.

`Relato.passo("...")` grava uma linha no log do job. `with relato.ia("Claude", "planejando as cenas") as ev:`
mostra "Claude pensando… 12 s" na mensagem do job enquanto a IA trabalha e passa `ev` para o adaptador
(`chamar(..., ao_evento=ev)`): o texto que a IA vai escrevendo entra no log em linhas (o raciocínio
marcado à parte), sem uma linha por pedaço.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

NOMES = {"claude": "Claude", "codex": "Codex"}
INTERVALO_LOG = 15.0  # de quanto em quanto tempo "ainda pensando" vira linha no log


class Relato:
    def __init__(self, log: Callable[[str], None] | None = None, mensagem: Callable[[str], None] | None = None) -> None:
        self._log = log or (lambda linha: None)
        self._mensagem = mensagem or (lambda msg: None)
        self._lock = threading.Lock()

    def passo(self, texto: str) -> None:
        self._log(f"• {texto}")

    @contextmanager
    def ia(self, nome: str, tarefa: str) -> Iterator[Callable[[str, str], None]]:
        quem = NOMES.get(nome, nome or "IA")
        self.passo(f"{quem}: {tarefa}")
        t0 = time.monotonic()
        fim = threading.Event()
        buf = {"texto": "", "pensando": ""}
        chegou = {"n": 0}

        def descarregar(tipo: str, tudo: bool = False) -> None:
            texto = buf[tipo]
            while texto:
                corte = max(texto.rfind("\n", 0, 220), texto.rfind(". ", 0, 220))
                if corte < 0:
                    if len(texto) < 220 and not tudo:
                        break
                    corte = min(len(texto), 220) - 1
                linha, texto = texto[: corte + 1].strip(), texto[corte + 1:]
                if linha:
                    self._log(("💭 " if tipo == "pensando" else "✎ ") + linha)
            buf[tipo] = texto

        def evento(tipo: str, texto: str) -> None:
            with self._lock:
                if tipo == "aviso":
                    self.passo(texto)
                    return
                chave = "pensando" if tipo == "pensando" else "texto"
                buf[chave] += texto
                chegou["n"] += len(texto)
                descarregar(chave)

        def batida() -> None:
            ultimo = 0.0
            while not fim.wait(1.0):
                s = time.monotonic() - t0
                extra = f" · {chegou['n']} caracteres" if chegou["n"] else ""
                self._mensagem(f"{quem} {tarefa}… {s:.0f} s{extra}")
                if s - ultimo >= INTERVALO_LOG:
                    ultimo = s
                    if not chegou["n"]:
                        self.passo(f"{quem} ainda pensando ({s:.0f} s)")

        th = threading.Thread(target=batida, daemon=True)
        th.start()
        try:
            yield evento
        finally:
            fim.set()
            with self._lock:
                descarregar("pensando", True)
                descarregar("texto", True)
            self.passo(f"{quem} respondeu em {time.monotonic() - t0:.0f} s")
