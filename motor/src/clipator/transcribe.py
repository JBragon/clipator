"""Transcrição local com faster-whisper e timestamp por palavra.

merge_continuation_words foi adaptado de openshorts/subtitles.py, MIT License,
Copyright (c) 2024 OpenShorts. Ver THIRD_PARTY_NOTICES.md.

Formato de analise/transcricao.json:
{
  "idioma": "pt", "duracao": 123.4, "modelo": "small", "dispositivo": "cpu",
  "segmentos": [{"inicio": 0.0, "fim": 3.2, "texto": "...",
                 "palavras": [{"texto": "Olá", "inicio": 0.0, "fim": 0.4, "prob": 0.98}]}]
}
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any

from .media import Cancelado, Progress

PARAMS_PADRAO = {
    "beam_size": 5,
    "vad_filter": True,
    "condition_on_previous_text": False,
    "word_timestamps": True,
}


def gpu_disponivel() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


_LIBS_CUDA = {
    "win32": [("cublas64_12.dll",), ("cudnn_ops64_9.dll", "cudnn64_9.dll")],
    "linux": [("libcublas.so.12",), ("libcudnn_ops.so.9", "libcudnn.so.9")],
}
_cuda_ok: bool | None = None


def _pastas_dll_nvidia() -> None:
    """No Windows, deixa visíveis as DLLs dos pacotes pip nvidia-cublas-cu12 / nvidia-cudnn-cu12."""
    if sys.platform != "win32":
        return
    import site

    for base in [*site.getsitepackages(), site.getusersitepackages()]:
        for pasta in Path(base).glob("nvidia/*/bin"):
            try:
                os.add_dll_directory(str(pasta))
                os.environ["PATH"] = f"{pasta}{os.pathsep}{os.environ.get('PATH', '')}"
            except OSError:
                pass


def _carregar_lib(nome: str) -> None:
    if sys.platform == "win32":
        ctypes.WinDLL(nome)
    else:
        ctypes.CDLL(nome)


def cuda_utilizavel() -> bool:
    """GPU NVIDIA com o CUDA 12 e o cuDNN 9 que o CTranslate2 carrega na hora de transcrever.

    Sem as bibliotecas, o modelo carrega em cuda e só falha no primeiro segmento.
    """
    global _cuda_ok
    if _cuda_ok is None:
        _cuda_ok = gpu_disponivel() and _libs_cuda_carregam()
    return _cuda_ok


def _libs_cuda_carregam() -> bool:
    libs = _LIBS_CUDA.get(sys.platform)
    if libs is None:
        return True
    _pastas_dll_nvidia()
    for opcoes in libs:
        for nome in opcoes:
            try:
                _carregar_lib(nome)
                break
            except OSError:
                continue
        else:
            return False
    return True


def _erro_de_cuda(e: BaseException) -> bool:
    msg = str(e).lower()
    return any(s in msg for s in ("cublas", "cudnn", "cuda", "cannot be loaded"))


def escolher_modelo(modelo: str = "auto", dispositivo: str = "auto") -> tuple[str, str, str]:
    """Devolve (modelo, dispositivo, compute_type).

    Decisão 2: roda em CPU com um Whisper menor; GPU só acelera.
    """
    dev = dispositivo
    if dev == "auto":
        dev = "cuda" if cuda_utilizavel() else "cpu"
    if modelo == "auto":
        modelo = "large-v3-turbo" if dev == "cuda" else "small"
    compute = "float16" if dev == "cuda" else "int8"
    return modelo, dev, compute


def estimar_tempo(duracao_s: float, modelo: str, dispositivo: str) -> float:
    """Estimativa grosseira (segundos) para o aviso de tempo na CPU."""
    fator_cpu = {"tiny": 0.06, "base": 0.1, "small": 0.25, "medium": 0.6, "large-v3-turbo": 0.5, "large-v3": 1.2}
    fator = fator_cpu.get(modelo, 0.4)
    if dispositivo == "cuda":
        fator /= 8
    return duracao_s * fator


_modelos: dict[tuple[str, str, str], Any] = {}
_lock = threading.Lock()


def threads_cpu() -> int:
    """Threads do CTranslate2 na CPU. O padrão dele são 4, o que deixa metade de um Ryzen ou Core
    de 8+ núcleos parada justo em quem não tem CUDA (AMD, Intel, Mac). CLIPATOR_WHISPER_THREADS força."""
    try:
        n = int(os.environ.get("CLIPATOR_WHISPER_THREADS", "0"))
    except ValueError:
        n = 0
    if n > 0:
        return n
    logicos = os.cpu_count() or 4
    return max(4, min(16, logicos // 2 if logicos >= 8 else logicos))  # ~núcleos físicos


def carregar_modelo(modelo: str, dispositivo: str, compute: str, pasta_modelos: str | None = None):
    """Carrega (ou reaproveita) o Whisper. Fica só um modelo na memória: trocar de modelo ou de
    dispositivo solta o anterior (um large-v3-turbo ocupa ~1,6 GB de VRAM e outro tanto de RAM)."""
    from faster_whisper import WhisperModel

    key = (modelo, dispositivo, compute)
    with _lock:
        if key not in _modelos:
            liberar_modelos_sem_lock()
            extra = {"cpu_threads": threads_cpu()} if dispositivo == "cpu" else {}
            _modelos[key] = WhisperModel(modelo, device=dispositivo, compute_type=compute, download_root=pasta_modelos, **extra)
        return _modelos[key]


def liberar_modelos_sem_lock() -> None:
    _modelos.clear()
    import gc

    gc.collect()  # o CTranslate2 solta a VRAM quando o objeto morre


def liberar_modelos() -> None:
    with _lock:
        liberar_modelos_sem_lock()


def merge_continuation_words(words: list[dict]) -> list[dict]:
    """Junta fragmentos sem espaço inicial à palavra anterior ("YouTube" + "-Kanal.")."""
    merged: list[dict] = []
    for word in words:
        text = word.get("word", "")
        if merged and isinstance(text, str) and text and not text.startswith(" "):
            prev = merged[-1]
            prev["word"] = f"{prev.get('word', '')}{text}"
            if word.get("end") is not None:
                prev["end"] = word["end"]
        else:
            merged.append(dict(word))
    return merged


def carregar_audio(audio: str | Path) -> Any:
    """Lê o WAV PCM 16 bits a 16 kHz que o pipeline extrai, como float32 mono.

    Passar o array evita o decode_audio do faster-whisper, que chama av.open com
    metadata_errors, argumento que o PyAV 15+ não aceita mais. Fora desse formato,
    devolve o caminho e deixa o faster-whisper decodificar.
    """
    import wave

    import numpy as np

    try:
        with wave.open(str(audio), "rb") as wf:
            if wf.getsampwidth() != 2 or wf.getframerate() != 16000:
                return str(audio)
            ch = wf.getnchannels()
            # Em blocos, direto no array final: 4 h de áudio são ~920 MB em float32; ler tudo de uma vez
            # juntava os bytes, o int16 convertido e a divisão, mais que o dobro disso no pico.
            total = wf.getnframes()
            x = np.empty(total, dtype=np.float32)
            pos, bloco = 0, 16000 * 60
            while pos < total:
                q = np.frombuffer(wf.readframes(bloco), dtype=np.int16)
                if not len(q):
                    break
                q = q.reshape(-1, ch).mean(axis=1, dtype=np.float32) if ch > 1 else q.astype(np.float32)
                x[pos:pos + len(q)] = q
                pos += len(q)
    except (wave.Error, EOFError, OSError, ValueError):
        return str(audio)
    x = x[:pos]
    x *= 1.0 / 32768.0
    return x


def transcrever(
    audio: str | Path,
    modelo: str = "auto",
    dispositivo: str = "auto",
    idioma: str | None = None,
    progresso: Progress | None = None,
    cancelar: threading.Event | None = None,
    pasta_modelos: str | None = None,
    hotwords: str | None = None,
) -> dict:
    """`hotwords`: nomes do glossário do canal, para o Whisper acertar a grafia (ver glossario.py)."""
    nome, dev, compute = escolher_modelo(modelo, dispositivo)
    if progresso:
        progresso(0.0, f"carregando modelo {nome} ({dev})")
    lang = None if idioma in (None, "", "auto") else idioma
    entrada = carregar_audio(audio)
    carregou = False
    try:
        model = carregar_modelo(nome, dev, compute, pasta_modelos)
        carregou = True
        return _transcrever_com(model, entrada, lang, nome, dev, progresso, cancelar, hotwords)
    except Cancelado:
        raise
    except Exception as e:  # noqa: BLE001
        # Na GPU, qualquer falha ao carregar (driver ausente, VRAM cheia) ou CUDA 12/cuDNN 9 faltando, que o
        # CTranslate2 só acusa ao decodificar, vira transcrição na CPU. Na CPU, o erro é do usuário ver.
        if dev != "cuda" or (carregou and not _erro_de_cuda(e)):
            raise
    global _cuda_ok
    _cuda_ok = False
    liberar_modelos()  # solta a VRAM do modelo que não serviu
    nome = "small" if nome.startswith("large") else nome
    if progresso:
        progresso(0.0, "GPU sem CUDA; transcrevendo na CPU")
    model = carregar_modelo(nome, "cpu", "int8", pasta_modelos)
    return _transcrever_com(model, entrada, lang, nome, "cpu", progresso, cancelar, hotwords)


def _transcrever_com(model, entrada, lang, nome, dev, progresso, cancelar, hotwords: str | None = None) -> dict:
    extra = {"hotwords": hotwords} if hotwords else {}
    segments, info = model.transcribe(entrada, language=lang, **PARAMS_PADRAO, **extra)
    duracao = float(getattr(info, "duration", 0) or 0)
    segs: list[dict] = []
    for seg in segments:
        if cancelar is not None and cancelar.is_set():
            raise Cancelado()
        raw = [{"word": w.word, "start": w.start, "end": w.end, "probability": w.probability} for w in (seg.words or [])]
        palavras = []
        for w in merge_continuation_words(raw):
            texto = (w["word"] or "").strip()
            if not texto:
                continue
            palavras.append({"texto": texto, "inicio": round(float(w["start"]), 3), "fim": round(float(w["end"]), 3),
                             "prob": round(float(w.get("probability") or 0), 3)})
        texto = (seg.text or "").strip()
        if not texto:
            continue
        segs.append({"inicio": round(float(seg.start), 3), "fim": round(float(seg.end), 3), "texto": texto, "palavras": palavras})
        if progresso and duracao:
            progresso(min(0.99, float(seg.end) / duracao), f"transcrevendo {_hms(float(seg.end))} de {_hms(duracao)}")
    segs = limpar_alucinacoes(segs)
    return {
        "idioma": getattr(info, "language", lang) or lang,
        "duracao": round(duracao, 3),
        "modelo": nome,
        "dispositivo": dev,
        "segmentos": segs,
    }


# Frases que o Whisper inventa em silêncio ou música (vêm das legendas com que foi treinado)
ALUCINACOES_SEMPRE = re.compile(
    r"amara\.?org|legendas? (pela|por|da) comunidade|legendado por|legendagem por|subt[ií]tulos? (realizados|por)|"
    r"transcri[cç][aã]o (e legendas|por)|subtitles by|captions by",
    re.IGNORECASE)
# ...e as que alguém pode dizer de verdade: só saem quando o Whisper estava inseguro
ALUCINACOES_DUVIDOSAS = re.compile(
    r"^\W*(obrigad[oa] por (assistir|ver)|inscreva-se( no canal)?|thanks? (you )?for watching|tchau,? tchau)\W*$",
    re.IGNORECASE)
PROB_DUVIDOSA = 0.5


def _norm(t: str) -> str:
    return re.sub(r"[^\w]", "", t.lower())


def _sem_loops(palavras: list[dict]) -> list[dict]:
    """Corta os loops do Whisper ("não não não não não", a mesma frase 5 vezes): de um trecho de 1 a 6
    palavras repetido em seguida (4+ vezes uma palavra, 3+ vezes uma frase), fica uma cópia só."""
    out: list[dict] = []
    i = 0
    norm = [_norm(w["texto"]) for w in palavras]
    while i < len(palavras):
        pulou = False
        for n in range(6, 0, -1):
            alvo = norm[i:i + n]
            if len(alvo) < n or not any(alvo):
                continue
            k = 1
            while norm[i + k * n:i + (k + 1) * n] == alvo:
                k += 1
            if k >= (4 if n == 1 else 3):
                out.extend(palavras[i:i + n])
                i += k * n
                pulou = True
                break
        if not pulou:
            out.append(palavras[i])
            i += 1
    return out


def limpar_alucinacoes(segmentos: list[dict]) -> list[dict]:
    """Tira da transcrição o que o Whisper inventa: créditos de legenda, "obrigado por assistir" dito com
    pouca certeza e loops de repetição. Sem isso, essas frases viravam legenda e entravam nos candidatos."""
    out = []
    for seg in segmentos:
        texto = seg.get("texto", "")
        pals = seg.get("palavras") or []
        if ALUCINACOES_SEMPRE.search(texto):
            continue
        prob = sum(w.get("prob", 1.0) for w in pals) / len(pals) if pals else 1.0
        if prob < PROB_DUVIDOSA and ALUCINACOES_DUVIDOSAS.search(texto):
            continue
        if pals:
            limpas = _sem_loops(pals)
            if len(limpas) != len(pals):
                seg = {**seg, "palavras": limpas, "texto": " ".join(w["texto"] for w in limpas),
                       "inicio": limpas[0]["inicio"], "fim": limpas[-1]["fim"]}
        out.append(seg)
    return out


def _hms(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def palavras(transcricao: dict) -> list[dict]:
    """Lista plana de palavras, ordenada por início."""
    out = [w for s in transcricao.get("segmentos", []) for w in s.get("palavras", [])]
    out.sort(key=lambda w: w["inicio"])
    return out


_TOKEN_RE = re.compile(r"\S+")


def corrigir_segmento(segmento: dict, novo_texto: str) -> dict:
    """Aplica uma correção de texto a um segmento mantendo os tempos.

    Com o mesmo número de palavras, cada palavra herda o tempo da antiga. Se o
    número mudar, os tempos são redistribuídos proporcionalmente ao tamanho das
    palavras dentro do intervalo do segmento.
    """
    tokens = _TOKEN_RE.findall(novo_texto.strip())
    antigas = segmento.get("palavras", [])
    seg = dict(segmento)
    seg["texto"] = " ".join(tokens)
    if not tokens:
        seg["palavras"] = []
        return seg
    if len(tokens) == len(antigas):
        seg["palavras"] = [{**w, "texto": t} for w, t in zip(antigas, tokens)]
        return seg
    ini = antigas[0]["inicio"] if antigas else segmento["inicio"]
    fim = antigas[-1]["fim"] if antigas else segmento["fim"]
    total = sum(len(t) for t in tokens) or 1
    cursor, novas = ini, []
    for t in tokens:
        dur = (fim - ini) * len(t) / total
        novas.append({"texto": t, "inicio": round(cursor, 3), "fim": round(cursor + dur, 3), "prob": 1.0})
        cursor += dur
    seg["palavras"] = novas
    return seg


def corrigir(transcricao: dict, correcoes: dict[int, str]) -> dict:
    """correcoes: {indice_do_segmento: novo_texto}."""
    out = dict(transcricao)
    segs = list(transcricao.get("segmentos", []))
    for idx, texto in correcoes.items():
        if 0 <= int(idx) < len(segs):
            segs[int(idx)] = corrigir_segmento(segs[int(idx)], texto)
    out["segmentos"] = segs
    out["corrigida"] = True
    return out
