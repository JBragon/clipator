"""Prova das cinco direções guiadas pela fala, pelo render de verdade: quadros dos cinco layouts, vídeos e uma segunda fala.

    python -m clipator.ferramentas.gerar_demos_cortes <pasta> [ids...] [--quadros] [--videos] [--segunda]

A fala do exemplo sai de dados/artes/exemplos/; a segunda fala, com outros objetos, está aqui. A voz é um tom sintetizado por
palavra, para conferir que o áudio do corte sai igual. Sem IA e sem rede. Precisa do FFmpeg e do HyperFrames.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from .gerar_demos_artes import TAXA, audio_do_video, energia, voz

LAYOUTS = {
    "metade-superior": {"layout": "em-cima", "proporcao": 0.5},
    "inferior-direito": {"layout": "janela", "janela_canto": "inferior-direito"},
    "inferior-esquerdo": {"layout": "janela", "janela_canto": "inferior-esquerdo"},
    "superior-direito": {"layout": "janela", "janela_canto": "superior-direito"},
    "superior-esquerdo": {"layout": "janela", "janela_canto": "superior-esquerdo"},
}
SEGUNDA = {
    "encaixe-vivo": "A base sustenta o foguete. O motor fica acima da base. O tanque guarda o combustível. A ponta fecha o foguete.",
    "pixel-em-cena": "A faroleira chega ao cais. Ela cruza a ponte até a torre. A lâmpada acende no alto. A porta se abre para a noite.",
    "fluxo-facetado": "O grão entra no moedor. A balança mede o café. A comporta separa o caminho. O pacote segue para a doca.",
    "rota-em-foco": "O barco sai do porto. A rota contorna o cabo. O percurso cruza a enseada. O navio chega à vila.",
    "terreno-vivo": "O lote começa vazio. A torre sobe no centro. A vala abre o caminho da água. As árvores crescem perto da torre.",
    "geo-em-cena": "Agora olhe para a Ásia. O Japão aparece neste canto do mapa. Dentro do Japão, veja Hokkaido. Depois a viagem segue até Fiji.",
}


def palavras_de(texto: str, dur: float = 10.0) -> list[dict]:
    frases = [f.strip() + "." for f in texto.split(".") if f.strip()]
    passo, out = dur / len(frases), []
    for k, f in enumerate(frases):
        ws = f.split()
        d = (passo - 0.4) / len(ws)
        out += [{"texto": w, "inicio": round(k * passo + i * d, 4), "fim": round(k * passo + (i + 0.9) * d, 4)} for i, w in enumerate(ws)]
    return out


def renderizar(ws, canal, slug: str, nome: str, pals: list[dict], dur: float, layout: dict, trabalho: Path, destino: Path, preview: bool = False) -> dict:
    from clipator import amostras, artes, edicao, media, render
    from clipator.models import Clip, LayoutArte, Origem
    from clipator.timeline import Timeline
    from clipator.workspace import write_json

    ffmpeg = media.ffmpeg_bin()
    p = canal.criar_projeto(nome, Origem(tipo="arquivo", valor="sintetico.mp4"))
    base = amostras.video_base(trabalho / f"base-{dur}.mp4", dur)
    wav = trabalho / f"{nome}.wav"
    original = voz(pals, dur, wav)
    p.fonte_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(base), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", str(p.fonte_dir / "video.mp4")], check=True, stdin=subprocess.DEVNULL, capture_output=True)
    write_json(p.transcricao_path, {"idioma": "pt", "duracao": dur, "modelo": "sintetico", "dispositivo": "cpu", "segmentos": [
        {"inicio": pals[0]["inicio"], "fim": pals[-1]["fim"], "texto": " ".join(w["texto"] for w in pals), "palavras": [{**w, "prob": 1.0} for w in pals]}]})
    clip = Clip(id="01-demo", inicio=0.0, fim=dur, titulo=slug, formato="9:16", plataforma="youtube-shorts", estilo=f"arte-{slug}")
    p.salvar_clip(clip)
    _, dir_clip = p.clip(clip.id)
    tl = Timeline.de_clip(0.0, dur, [])
    itens = [edicao.Item(tipo="cena", origem="heuristica", **c) for c in artes.planejar_regras(slug, pals, dur, artes.assinatura_timeline(tl))]
    edicao.salvar(dir_clip, edicao.Edicao(itens=itens, cenas_planejadas=True, layout_arte=LayoutArte.model_validate(layout)), dur)
    est = ws.carregar_estilo(clip.estilo, canal)[0].model_copy(update={"reenquadramento": "centro"})  # a silhueta desenhada não é rosto
    t0 = time.time()
    r = render.renderizar_clip(p, clip, est, preview, exigir_ia=False, enquadrar_rosto=False)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(r.video.read_bytes())
    final = audio_do_video(destino, ffmpeg)
    a, b = energia(original), energia(final)
    n = min(len(a), len(b))
    info = media.probe(destino)
    return {"estilo": slug, "video": destino.name, "render_s": round(time.time() - t0, 1), "duracao_s": round(info.duracao, 3), "largura": info.largura, "altura": info.altura,
            "cenas": len(itens), "acoes": [[i.params["corte"]["acao"], [o.get("nome") or o["falado"] for o in i.params["corte"].get("objetos") or i.params["corte"].get("lugares", [])]] for i in itens], "aviso": r.aviso,
            "audio_correlacao": round(float(np.corrcoef(a[:n], b[:n])[0, 1]), 4), "audio_duracao_diferenca_s": round(abs(len(final) - len(original)) / TAXA, 3)}


def quadro(video: Path, t: float, destino: Path) -> None:
    from clipator import media

    destino.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(destino)],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pasta")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--quadros", action="store_true", help="um quadro de cada estilo em cada layout")
    ap.add_argument("--videos", action="store_true", help="um MP4 dividido e um em janela por estilo")
    ap.add_argument("--segunda", action="store_true", help="a segunda fala, com outros objetos")
    args = ap.parse_args(argv)
    from clipator import artes
    from clipator.artes import cortes
    from clipator.workspace import Workspace

    pasta = Path(args.pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / "relatorio.json"
    rel = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}

    def anotar(chave: str, r: dict) -> None:
        rel[chave] = r
        print(chave, json.dumps({k: r[k] for k in ("render_s", "aviso", "audio_correlacao")}, ensure_ascii=False), flush=True)
        arq.write_text(json.dumps(rel, ensure_ascii=False, indent=1), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="clipator-cortes-", ignore_cleanup_errors=True) as tmp:
        ws = Workspace(Path(tmp) / "ws").init()
        trabalho = Path(tmp) / "trabalho"
        trabalho.mkdir()
        for slug in args.ids or [*cortes.ACOES, "geo-em-cena"]:
            ex = json.loads((artes._dados("artes") / "exemplos" / f"{slug}.json").read_text(encoding="utf-8"))
            dur, pals = float(ex["duracao_s"]), [dict(w) for w in ex["palavras"]]
            canal = ws.criar_canal(f"Demo {slug}")
            if args.quadros:
                for nome, lay in LAYOUTS.items():
                    v = trabalho / f"{slug}-{nome}.mp4"
                    r = renderizar(ws, canal, slug, f"q-{nome}", pals, dur, lay, trabalho, v, preview=True)
                    anotar(f"quadro/{slug}/{nome}", r)
                    quadro(v, dur * 0.62, pasta / "quadros" / f"{slug}--{nome}.jpg")
            if args.videos:
                for nome in ("metade-superior", "inferior-direito"):
                    v = pasta / "videos" / f"{slug}--{nome}.mp4"
                    anotar(f"video/{slug}/{nome}", renderizar(ws, canal, slug, f"v-{nome}", pals, dur, LAYOUTS[nome], trabalho, v))
            if args.segunda:
                v = pasta / "segunda-fala" / f"{slug}.mp4"
                anotar(f"segunda/{slug}", renderizar(ws, canal, slug, "segunda", palavras_de(SEGUNDA[slug]), 10.0, LAYOUTS["inferior-esquerdo"], trabalho, v))
                quadro(v, 6.2, pasta / "segunda-fala" / f"{slug}.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
