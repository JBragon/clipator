"""Sinais locais: energia do áudio, picos, silêncios e cortes de cena.

Tudo roda sem IA e sem internet. Formato de analise/sinais.json:
{
  "passo": 0.25,                 # segundos por amostra de energia
  "energia_db": [-30.1, ...],    # RMS em dBFS por janela
  "picos": [[t_ini, t_fim], ...],# trechos bem acima da média (risadas, gritos)
  "cenas": [12.3, 40.1, ...],    # instantes de corte de cena
  "media_db": -24.0, "desvio_db": 6.0
}
"""

from __future__ import annotations

import re
import threading
import wave
from pathlib import Path

import numpy as np

from . import media
from .media import Cancelado, Progress

PASSO = 0.25


def energia(wav_path: str | Path, passo: float = PASSO, cancelar: threading.Event | None = None) -> np.ndarray:
    """RMS em dBFS por janela de `passo` segundos, lendo o WAV em blocos."""
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        if sw != 2:
            raise ValueError("Esperado WAV PCM 16 bits")
        hop = int(sr * passo)
        out: list[float] = []
        bloco = hop * 240  # ~1 min por leitura
        resto = np.zeros(0, dtype=np.float32)
        while True:
            if cancelar is not None and cancelar.is_set():
                raise Cancelado()
            raw = wf.readframes(bloco)
            if not raw:
                break
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if ch > 1:
                x = x.reshape(-1, ch).mean(axis=1)
            x = np.concatenate([resto, x])
            n = len(x) // hop
            if n:
                frames = x[: n * hop].reshape(n, hop)
                rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
                out.extend((20 * np.log10(rms)).tolist())
            resto = x[n * hop :]
        if len(resto) > hop // 4:
            rms = float(np.sqrt(np.mean(resto ** 2) + 1e-12))
            out.append(20 * np.log10(rms))
    return np.clip(np.array(out, dtype=np.float32), -90, 0)


def picos(db: np.ndarray, passo: float = PASSO, z: float = 2.0, min_dur: float = 0.5) -> list[list[float]]:
    """Trechos em que o volume fica `z` desvios acima da média por pelo menos `min_dur`."""
    if len(db) == 0:
        return []
    voz = db[db > -60]
    if len(voz) < 10:
        return []
    mu, sd = float(voz.mean()), float(voz.std() or 1)
    alto = db > mu + z * sd
    out, ini = [], None
    for i, a in enumerate(alto):
        if a and ini is None:
            ini = i
        elif not a and ini is not None:
            if (i - ini) * passo >= min_dur:
                out.append([round(ini * passo, 2), round(i * passo, 2)])
            ini = None
    if ini is not None and (len(alto) - ini) * passo >= min_dur:
        out.append([round(ini * passo, 2), round(len(alto) * passo, 2)])
    return out


_PTS_RE = re.compile(r"pts_time:([0-9.]+)")


def cenas(video: str | Path, limiar: float = 0.35, cancelar: threading.Event | None = None,
          progresso: Progress | None = None) -> list[float]:
    """Cortes de cena com o filtro de cena do FFmpeg, em baixa resolução e 4 fps.

    PySceneDetect/TransNetV2 ficam para depois; o filtro do FFmpeg já evita
    cortar no meio de uma transição e não exige dependência extra.
    """
    info = media.probe(video)
    if not info.tem_video:
        return []
    # "-skip_frame nokey" não serve (o filtro de cena compara quadros vizinhos); o que pesa é decodificar
    # o vídeo inteiro, e isso a placa de vídeo faz (NVIDIA, AMD ou Intel), com volta para a CPU.
    cmd = [media.ffmpeg_bin(), "-hide_banner", "-nostdin", *media.hwaccel_args(), "-i", str(video), "-an", "-sn", "-dn",
           "-vf", f"fps=4,scale=160:-2,select='gt(scene\\,{limiar})',showinfo", "-f", "null", "-"]
    out: list[float] = []

    def ler(line: str) -> None:
        if "showinfo" in line:
            m = _PTS_RE.search(line)
            if m:
                t = float(m.group(1))
                out.append(round(t, 2))
                if progresso and info.duracao:
                    progresso(min(0.99, t / info.duracao), "detectando cenas")

    # rodar_processo confere o cancelar a cada 0,25 s (o showinfo só escreve quando há corte, então
    # ler o stderr linha a linha deixava o cancelar esperando minutos num plano longo) e mata a árvore.
    codigo = media.rodar_processo(cmd, ler, cancelar, sem_saida_s=None, descricao="detectar cenas")
    if codigo != 0 and not out and media.hwaccel_args():
        # decodificação pela placa recusada (driver velho, codec que ela não tem): repete na CPU
        cmd = [c for c in cmd if c not in media.hwaccel_args()]
        media.rodar_processo(cmd, ler, cancelar, sem_saida_s=None, descricao="detectar cenas")
    return out


def analisar(wav: str | Path, video: str | Path | None = None, cancelar: threading.Event | None = None,
             progresso: Progress | None = None, detectar_cenas: bool = True) -> dict:
    if progresso:
        progresso(0.0, "medindo energia do áudio")
    db = energia(wav, cancelar=cancelar)
    voz = db[db > -60]
    mu = float(voz.mean()) if len(voz) else -30.0
    sd = float(voz.std()) if len(voz) else 6.0
    resultado = {
        "passo": PASSO,
        "energia_db": [round(float(x), 1) for x in db],
        "media_db": round(mu, 2),
        "desvio_db": round(sd, 2),
        "picos": picos(db),
        "cenas": [],
    }
    if detectar_cenas and video is not None:
        def _p(frac: float, msg: str) -> None:
            if progresso:
                progresso(0.3 + 0.7 * frac, msg)
        resultado["cenas"] = cenas(video, cancelar=cancelar, progresso=_p)
    if progresso:
        progresso(1.0, "sinais prontos")
    return resultado
