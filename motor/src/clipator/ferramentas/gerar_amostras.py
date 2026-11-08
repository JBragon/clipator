"""Gera as amostras prontas dos estilos que vêm com o Clipator (dados/amostras/).

    python -m clipator.ferramentas.gerar_amostras            # só as que faltam ou cujo estilo mudou
    python -m clipator.ferramentas.gerar_amostras --forcar   # todas de novo
    python -m clipator.ferramentas.gerar_amostras impacto    # só esse estilo

Roda num workspace temporário (só os estilos embutidos e os das skills embutidas) e grava
<estilo>.mp4, <estilo>.jpg e o indice.json com o hash de cada estilo. O app só lê esses arquivos;
um estilo com outro hash (editado, ajustado, de outra skill) tem a amostra gerada uma vez no cache.
Precisa do FFmpeg e, para os estilos animados, do HyperFrames.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LIMITE_BYTES = 880_000


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("estilos", nargs="*", help="só estes estilos (padrão: todos os embutidos)")
    ap.add_argument("--forcar", action="store_true", help="gera de novo mesmo com o hash igual")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="clipator-amostras-") as tmp:
        os.environ["CLIPATOR_AMOSTRAS"] = str(Path(tmp) / "cache")
        os.environ["CLIPATOR_SKILLS"] = str(Path(tmp) / "skills")  # nenhuma skill do usuário entra
        from clipator import amostras, media
        from clipator.workspace import Workspace

        ws = Workspace(Path(tmp) / "ws").init()
        destino = amostras.pasta_prontas()
        destino.mkdir(parents=True, exist_ok=True)
        indice = amostras.indice_prontas()
        nomes = args.estilos or sorted(ws.estilos(None))
        for nome in nomes:
            k = amostras.chave(ws, nome, None)
            atual = indice.get(nome)
            if not args.forcar and atual and atual.get("hash") == k and (destino / atual["arquivo"]).is_file():
                print(f"{nome}: em dia")
                continue
            t0 = time.time()
            # gera no cache temporário (achar() não acha a pronta porque o hash mudou ou falta o arquivo)
            indice.pop(nome, None)
            (destino / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
            p = amostras.gerar(ws, nome)
            shutil.copyfile(p, destino / f"{nome}.mp4")
            if (destino / f"{nome}.mp4").stat().st_size > LIMITE_BYTES:  # o mapa em voo pesa mais: a amostra da galeria tem de seguir leve
                leve = Path(tmp) / f"{nome}-leve.mp4"
                subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(p), "-c:v", "libx264", "-preset", "slow", "-crf", "27",
                                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(leve)], check=True, stdin=subprocess.DEVNULL)
                shutil.copyfile(leve, destino / f"{nome}.mp4")
            if p.with_suffix(".jpg").exists():
                shutil.copyfile(p.with_suffix(".jpg"), destino / f"{nome}.jpg")
            indice[nome] = {"arquivo": f"{nome}.mp4", "capa": f"{nome}.jpg", "hash": k}
            (destino / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{nome}: {round((destino / f'{nome}.mp4').stat().st_size / 1024)} KB em {time.time() - t0:.1f} s")
        for velho in set(indice) - set(ws.estilos(None)):
            indice.pop(velho)  # estilo que saiu do Clipator
        (destino / "indice.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        total = sum(f.stat().st_size for f in destino.iterdir() if f.is_file())
        print(f"{len(indice)} amostras, {total / 1e6:.1f} MB em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
