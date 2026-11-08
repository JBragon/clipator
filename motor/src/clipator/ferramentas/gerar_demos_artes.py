"""Gera um clip sintético completo de cada direção de arte: vídeo, voz, legenda, arte e sons, pelo render de verdade.

    python -m clipator.ferramentas.gerar_demos_artes <pasta> [ids...]

A fala é a do exemplo da direção (dados/artes/exemplos/); a voz é um tom modulado por palavra, sintetizado aqui, para
conferir que o áudio sai igual sem depender de gravação nenhuma. Grava <id>.mp4, <id>.jpg, três quadros e relatorio.json com
tempo de render, backend e a comparação do áudio. Não usa IA nem rede. Precisa do FFmpeg e do HyperFrames.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

TAXA = 48000


def voz(palavras: list[dict], dur: float, destino: Path) -> np.ndarray:
    """Um tom com harmônicos, com envelope em cada palavra e silêncio entre elas."""
    t = np.arange(int(dur * TAXA)) / TAXA
    tom = sum(np.sin(2 * np.pi * 150 * k * t) / k for k in (1, 2, 3, 5))
    env = np.zeros_like(t)
    for w in palavras:
        a, b = int(w["inicio"] * TAXA), min(len(t), int(w["fim"] * TAXA))
        if b > a:
            env[a:b] = np.hanning(b - a)
    x = (0.3 * tom * env).astype(np.float32)
    with wave.open(str(destino), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(TAXA)
        f.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return x


def energia(x: np.ndarray, janela: float = 0.05) -> np.ndarray:
    n = int(TAXA * janela)
    m = len(x) // n
    return np.sqrt((x[: m * n].reshape(m, n) ** 2).mean(axis=1))


def audio_do_video(video: Path, ffmpeg: str) -> np.ndarray:
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video), "-ac", "1", "-ar", str(TAXA), "-f", "f32le", "-"],
                       capture_output=True, check=True, stdin=subprocess.DEVNULL)
    return np.frombuffer(r.stdout, dtype="<f4")


def demo(ws, slug: str, pasta: Path, trabalho: Path) -> dict:
    from clipator import amostras, artes, edicao, media, render
    from clipator.models import Clip, Origem
    from clipator.timeline import Timeline
    from clipator.workspace import write_json

    ex = json.loads((artes._dados("artes") / "exemplos" / f"{slug}.json").read_text(encoding="utf-8"))
    dur = float(ex["duracao_s"])
    pals = [dict(w) for w in ex["palavras"]]
    canal = ws.criar_canal(f"Demo {slug}")
    p = canal.criar_projeto(slug, Origem(tipo="arquivo", valor="sintetico.mp4"))
    ffmpeg = media.ffmpeg_bin()
    base = amostras.video_base(trabalho / f"base-{dur}.mp4", dur)
    wav = trabalho / f"{slug}.wav"
    original = voz(pals, dur, wav)
    p.fonte_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", str(p.fonte_dir / "video.mp4")], check=True, stdin=subprocess.DEVNULL, capture_output=True)
    write_json(p.transcricao_path, {"idioma": "pt", "duracao": dur, "modelo": "sintetico", "dispositivo": "cpu", "segmentos": [
        {"inicio": pals[0]["inicio"], "fim": pals[-1]["fim"], "texto": " ".join(w["texto"] for w in pals), "palavras": [{**w, "prob": 1.0} for w in pals]}]})
    clip = Clip(id="01-demo", inicio=0.0, fim=dur, titulo=ex["estilo"], formato="9:16", plataforma="youtube-shorts", estilo=f"arte-{slug}")
    p.salvar_clip(clip)
    _, dir_clip = p.clip(clip.id)
    tl = Timeline.de_clip(0.0, dur, [])
    itens = [edicao.Item(tipo="cena", origem="heuristica", **c) for c in artes.planejar_regras(slug, pals, dur, artes.assinatura_timeline(tl))]
    edicao.salvar(dir_clip, edicao.Edicao(itens=itens, cenas_planejadas=True), dur)
    est = ws.carregar_estilo(clip.estilo, canal)[0].model_copy(update={"reenquadramento": "centro"})  # a silhueta desenhada não é rosto
    t0 = time.time()
    r = render.renderizar_clip(p, clip, est, False, exigir_ia=False, enquadrar_rosto=False)
    tempo = time.time() - t0
    saida = pasta / f"{slug}.mp4"
    saida.write_bytes(r.video.read_bytes())
    for nome, t in (("entrada", dur * 0.12), ("meio", dur * 0.5), ("saida", dur * 0.92)):
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(saida), "-frames:v", "1", "-q:v", "3", str(pasta / f"{slug}-{nome}.jpg")],
                       check=True, stdin=subprocess.DEVNULL, capture_output=True)
    (pasta / f"{slug}.jpg").write_bytes((pasta / f"{slug}-meio.jpg").read_bytes())
    final = audio_do_video(saida, ffmpeg)
    a, b = energia(original), energia(final)
    n = min(len(a), len(b))
    info = media.probe(saida)
    html = (dir_clip / "cenas" / "index.html").read_text(encoding="utf-8")
    return {"id": slug, "render_s": round(tempo, 1), "duracao_s": round(info.duracao, 3), "largura": info.largura, "altura": info.altura,
            "cenas": len(itens), "backend": "three" if "<canvas" in html else "svg", "aviso": r.aviso,
            "audio_correlacao": round(float(np.corrcoef(a[:n], b[:n])[0, 1]), 4), "audio_duracao_diferenca_s": round(abs(len(final) - len(original)) / TAXA, 3),
            "mb": round(saida.stat().st_size / 1e6, 2)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pasta")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args(argv)
    from clipator import artes
    from clipator.workspace import Workspace

    pasta = Path(args.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / "relatorio.json"
    relatorio = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    with tempfile.TemporaryDirectory(prefix="clipator-demos-") as tmp:
        ws = Workspace(Path(tmp) / "ws").init()
        trabalho = Path(tmp) / "trabalho"
        trabalho.mkdir()
        for slug in args.ids or sorted(artes.especificacoes()):
            relatorio[slug] = demo(ws, slug, pasta, trabalho)
            print(json.dumps(relatorio[slug], ensure_ascii=False), flush=True)
            arq.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
