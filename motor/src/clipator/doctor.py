"""clipator doctor: confere tudo e diz o que falta."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .ai import detectar_agentes


def _versao(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        linhas = (r.stdout or r.stderr).strip().splitlines()
        return linhas[0] if r.returncode == 0 and linhas else None
    except Exception:
        return None


def verificar(workspace: Path | None = None) -> list[dict]:
    """Cada item: {nome, ok, detalhe, obrigatorio, dica}."""
    itens: list[dict] = []

    def add(nome: str, ok: bool, detalhe: str, obrigatorio: bool, dica: str = "") -> None:
        itens.append({"nome": nome, "ok": ok, "detalhe": detalhe, "obrigatorio": obrigatorio, "dica": dica})

    add("Python", sys.version_info >= (3, 11), sys.version.split()[0], True, "Use Python 3.11 ou mais novo (o instalador usa o uv).")
    from .media import DICA_LIBASS, ffmpeg_bin, ffprobe_bin, filtros_ffmpeg

    for nome, b in (("ffmpeg", ffmpeg_bin()), ("ffprobe", ffprobe_bin())):
        v = _versao([b, "-version"]) if shutil.which(b) else None
        add(nome, v is not None, v or "não encontrado", True,
            "Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg-full · Linux: apt install ffmpeg")
    if shutil.which(ffmpeg_bin()):
        ok = "subtitles" in filtros_ffmpeg()
        add("FFmpeg com libass (legendas)", ok, "ok" if ok else "sem o filtro subtitles", True, DICA_LIBASS)
    deno = _versao(["deno", "--version"]) if shutil.which("deno") else None
    add("Deno (yt-dlp/YouTube)", deno is not None, deno or "não encontrado", False,
        "O yt-dlp precisa de um runtime JavaScript para o YouTube. Windows: winget install DenoLand.Deno · Mac: brew install deno")
    node = _versao(["node", "--version"]) if shutil.which("node") else None
    add("Node.js (HyperFrames)", node is not None, node or "não encontrado", False, "Instale o Node.js 22 ou mais novo.")
    from . import hyperframes

    hf = hyperframes.versao() if hyperframes.comando() else None
    add("HyperFrames (estilos animados)", hf is not None, hf or "não instalado", False,
        f"npm install --prefix {hyperframes.pasta_instalacao()} hyperframes  (sem ele, esses estilos usam a legenda ASS)")
    for mod, nome, obrig in (("yt_dlp", "yt-dlp", True), ("faster_whisper", "faster-whisper", True),
                             ("mediapipe", "MediaPipe (rostos)", False), ("cv2", "OpenCV", False), ("mcp", "MCP SDK", True)):
        ok = importlib.util.find_spec(mod) is not None
        add(nome, ok, "instalado" if ok else "não instalado", obrig, f"uv tool install 'clipator[visao]' (ou pip install {nome.split()[0].lower()})")
    from .transcribe import cuda_utilizavel, escolher_modelo, gpu_disponivel

    gpu = gpu_disponivel()
    modelo, dev, _ = escolher_modelo()
    if gpu and not cuda_utilizavel():
        add("GPU NVIDIA", False, f"encontrada, mas sem CUDA 12/cuDNN 9; usando CPU com {modelo}", False,
            "Para usar a GPU: uv pip install nvidia-cublas-cu12 \"nvidia-cudnn-cu12==9.*\" no ambiente do motor "
            "(ou instale o CUDA 12 e o cuDNN 9 da NVIDIA).")
    else:
        from .transcribe import threads_cpu

        add("GPU NVIDIA", gpu, f"transcrição com {modelo} em {dev}" + ("" if gpu else f" ({threads_cpu()} threads)"), False,
            "Sem GPU NVIDIA a transcrição roda na CPU (o faster-whisper só acelera com CUDA, então placa AMD ou Intel "
            "não entra aqui). Funciona normal, só demora mais: um vídeo de 1 h leva uns 15 min com o modelo small.")
    if shutil.which(ffmpeg_bin()) or os.path.isfile(ffmpeg_bin()):
        from .media import encoder_em_uso

        enc = encoder_em_uso()
        nomes = {"nvenc": "NVIDIA NVENC", "amf": "AMD AMF", "qsv": "Intel Quick Sync", "videotoolbox": "Apple VideoToolbox",
                 "x264": "x264 na CPU"}
        add("Encoder de vídeo", enc != "x264", nomes.get(enc, enc), False,
            "Nenhum encoder de placa de vídeo respondeu; o render usa a CPU (mais lento, mesma qualidade). "
            "Atualize o driver da placa (NVIDIA, AMD Adrenalin ou Intel) ou force com CLIPATOR_ENCODER=nvenc|amf|qsv|x264.")
    agentes = detectar_agentes()
    for nome, info in agentes.items():
        if info["instalado"]:
            det = f"{info['versao'] or 'instalado'}" + (" · logado" if info["logado"] else " · não logado" if info["logado"] is False else "")
        else:
            det = "não instalado"
        add(f"IA: {nome}", bool(info["instalado"] and info["logado"] is not False), det, False,
            "Opcional. Instale o Claude Code ou o Codex e faça login para ranking, títulos e estilos por IA.")
    if workspace is not None:
        livre = shutil.disk_usage(workspace if workspace.exists() else Path.home()).free / 1e9
        add("Espaço em disco", livre > 10, f"{livre:.0f} GB livres", False, "Vídeos de 4 h ocupam alguns GB; deixe pelo menos 10 GB livres.")
    return itens


def imprimir(itens: list[dict]) -> int:
    falta_obrig = 0
    for i in itens:
        marca = "✔" if i["ok"] else ("✖" if i["obrigatorio"] else "•")
        print(f" {marca} {i['nome']}: {i['detalhe']}")
        if not i["ok"] and i["dica"]:
            print(f"     {i['dica']}")
        if not i["ok"] and i["obrigatorio"]:
            falta_obrig += 1
    print()
    print("Tudo pronto." if not falta_obrig else f"Faltam {falta_obrig} item(ns) obrigatório(s).")
    return 1 if falta_obrig else 0
