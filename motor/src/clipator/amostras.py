"""Amostras dos estilos: alguns segundos renderizados de verdade com cada estilo, para o passo 3 mostrar.

O vídeo de base é sintetizado aqui (gradiente animado do FFmpeg, sem som e sem direito autoral) com
uma fala de exemplo cronometrada palavra a palavra. Cada amostra passa pelo mesmo render dos clips
(legenda, cartela, zoom, sons, HyperFrames) em meia resolução.

As amostras dos estilos que vêm com o Clipator já vêm prontas em dados/amostras/ (geradas uma vez com
`python -m clipator.ferramentas.gerar_amostras`), com o hash do estilo no indice.json: abrir a galeria só
lê os arquivos. Estilo do usuário, editado, ajustado (cor, fonte) ou vindo de skill tem outro hash e a
amostra é gerada uma vez e guardada em ~/.clipator/amostras (ou $CLIPATOR_AMOSTRAS) com o hash no nome.

"Prévia com este vídeo" usa o mesmo caminho com o vídeo do projeto: os primeiros segundos de um corte.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import media
from .workspace import _dados
from .models import Clip
from .workspace import CanalWS, ProjetoWS, Workspace

VERSAO = "v2"  # muda quando o vídeo de base, a fala ou as cenas de exemplo mudam
DURACAO = 5.6
FALA = ("Olha só como fica o seu corte com este estilo. A legenda acompanha cada palavra, "
        "o destaque cai nas palavras fortes e o resto do vídeo segue igual.")
DESTAQUES = ["corte", "estilo", "destaque", "fortes"]
TITULO = "Assim fica o seu corte"
# o que as amostras da direção de arte mostram (cenas fixas: no app, elas vêm da fala de cada corte)
CENAS_EXEMPLO = [
    (0.1, 1.7, {"cena": "titulo", "texto": "Assim fica o seu corte"}),
    (1.8, 3.6, {"cena": "numero", "valor": "87%", "rotulo": "das cenas seguem a fala"}),
    (3.7, 5.5, {"cena": "lista", "itens": ["Número na hora certa", "Lista que entra item a item", "Tudo na ficha do canal"]}),
]


def pasta_cache() -> Path:
    return Path(os.environ.get("CLIPATOR_AMOSTRAS") or Path.home() / ".clipator" / "amostras")


def pasta_prontas() -> Path:
    """As amostras que vêm com o Clipator (estilos embutidos), já renderizadas."""
    return _dados("amostras")


def indice_prontas() -> dict:
    p = pasta_prontas() / "indice.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _transcricao(duracao: float = DURACAO) -> dict:
    """A fala de exemplo com tempo por palavra (só a parte que cabe na amostra)."""
    tokens = FALA.split()
    passo = (duracao - 0.4) / len(tokens) * 1.35  # só o começo da fala cabe; o ritmo fica natural
    segs, atual, t = [], [], 0.2
    for p in tokens:
        if t + passo * 0.8 > duracao:
            break
        atual.append({"texto": p, "inicio": round(t, 3), "fim": round(t + passo * 0.8, 3), "prob": 0.95})
        t += passo
        if p.endswith("."):
            segs.append({"inicio": atual[0]["inicio"], "fim": atual[-1]["fim"], "texto": " ".join(w["texto"] for w in atual),
                         "palavras": atual})
            atual = []
            t += 0.25
    if atual:
        segs.append({"inicio": atual[0]["inicio"], "fim": atual[-1]["fim"], "texto": " ".join(w["texto"] for w in atual),
                     "palavras": atual})
    return {"idioma": "pt", "duracao": duracao, "modelo": "amostra", "dispositivo": "cpu", "segmentos": segs}


def _silhueta(destino: Path) -> Path:
    """Um apresentador estilizado (cabeça, pescoço e ombros), desenhado aqui: dá corpo à amostra sem imagem de ninguém."""
    from PIL import Image, ImageDraw, ImageFilter

    if destino.exists():
        return destino
    s = 2
    img = Image.new("RGBA", (1280 * s, 720 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pele, roupa = (205, 168, 140, 255), (52, 58, 78, 255)
    d.rounded_rectangle((640 * s - 230 * s, 470 * s, 640 * s + 230 * s, 820 * s), radius=150 * s, fill=roupa)  # ombros
    d.rectangle((640 * s - 42 * s, 360 * s, 640 * s + 42 * s, 480 * s), fill=pele)  # pescoço
    d.ellipse((640 * s - 95 * s, 170 * s, 640 * s + 95 * s, 400 * s), fill=pele)  # cabeça
    d.chord((640 * s - 100 * s, 160 * s, 640 * s + 100 * s, 330 * s), 180, 360, fill=(48, 36, 30, 255))  # cabelo
    img = img.resize((1280, 720), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.6))
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.save(destino)
    return destino


def video_base(destino: Path, duracao: float = DURACAO, verde: bool = False) -> Path:
    """Vídeo 16:9 neutro gerado pelo FFmpeg, sem som: um fundo que se mexe devagar e um apresentador estilizado.

    `verde`: o fundo é um chroma key (para a amostra da animação de fundo mostrar o recorte de verdade).
    """
    if destino.exists():
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".tmp.mp4")
    fonte = (f"color=c=0x00B140:s=1280x720:r=30:d={duracao}" if verde else
             f"gradients=s=1280x720:r=30:d={duracao}:n=4:speed=0.012:seed=7:c0=0x23395b:c1=0x406e8e:c2=0x8ea8c3:c3=0xcbf7ed")
    pessoa = _silhueta(destino.parent / f"silhueta-{VERSAO}.png")
    # a pessoa respira de leve (sobe e desce 4 px), como quem está falando
    grafo = ("[0:v]" + ("" if verde else "vignette=PI/5,") + "format=yuv420p[f];"
             "[2:v]format=rgba[p];[f][p]overlay=x=0:y='4*sin(2*PI*t/2.4)':format=auto,format=yuv420p[v]")
    tmp.unlink(missing_ok=True)  # sobra de uma vez que travou ou foi fechada no meio

    def rodar(fonte: str) -> None:
        cmd = [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "lavfi", "-i", fonte, "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={duracao}",
               "-loop", "1", "-t", f"{duracao}", "-i", str(pessoa), "-filter_complex", grafo, "-map", "[v]", "-map", "1:a",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-shortest", str(tmp)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=90, stdin=subprocess.DEVNULL)  # stdin aberto trava o FFmpeg no Windows

    try:
        rodar(fonte)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # FFmpeg sem o filtro "gradients" (versões antigas) ou que travou: um fundo liso no lugar
        tmp.unlink(missing_ok=True)
        rodar(f"color=c=0x{'00B140' if verde else '2C4A6B'}:s=1280x720:r=30:d={duracao}")
    tmp.replace(destino)
    return destino


class _ProjetoAmostra:
    """O mínimo de um projeto que o render usa: vídeo, transcrição, sinais, pasta dos clips e o canal."""

    def __init__(self, ws: Workspace, canal: CanalWS, video: Path, trans: dict, pasta: Path,
                 sinais: dict | None = None) -> None:
        self.ws, self.canal, self._video, self._trans, self.clips_dir, self._sinais = ws, canal, video, trans, pasta, sinais

    def video_path(self) -> Path:
        return self._video

    def transcricao(self) -> dict:
        return self._trans

    def sinais(self) -> dict:
        return self._sinais or {}


def _arquivos_do_estilo(caminho: Path) -> list[Path]:
    """O .md do estilo e, se ele mora numa pasta própria (estilos/<nome>/estilo.md), o resto dela (CSS, HTML)."""
    if caminho.name == "estilo.md":
        return sorted(p for p in caminho.parent.rglob("*") if p.is_file())
    return [caminho]


def chave(ws: Workspace, nome: str, canal: CanalWS | None, ajustes: dict | None = None, formato: str | None = None,
          estilos: dict[str, Path] | None = None) -> str:
    """Muda quando o estilo (arquivo ou pasta), os ajustes, o formato ou a versão do Clipator mudam."""
    est, _, caminho = ws.carregar_estilo(nome, canal, ajustes, estilos)
    h = hashlib.sha1()
    # a versão do Clipator não entra: atualizar o app não refaz amostra nenhuma (VERSAO muda quando a base ou a fala mudam)
    h.update(json.dumps([VERSAO, nome, formato or est.formato, ajustes or {}], sort_keys=True).encode())
    if est.direcao.modo == "arte":  # o desenho mora no código da direção, não no .md
        from .artes import VERSAO_ARTE, VERSAO_RENDERER
        from .workspace import _dados

        h.update(str(VERSAO_RENDERER).encode())
        if est.direcao.arte in VERSAO_ARTE:
            h.update(f"{est.direcao.arte}-{VERSAO_ARTE[est.direcao.arte]}".encode())
        h.update((_dados("arte") / "presets" / f"{est.direcao.arte}.yaml").read_bytes().replace(b"\r\n", b"\n"))
        from .artes import cortes

        if cortes.eh_corte(est.direcao.arte):  # estas cinco desenham no motor.js, a partir do léxico e do exemplo próprio
            h.update(str(cortes.VERSAO).encode())
            from .artes import curta

            h.update(f"curta-{curta.VERSAO}".encode())
            for arq in (_dados("cortes") / "motor.js", _dados("cortes") / "lexico.json", _dados("artes") / "exemplos" / f"{est.direcao.arte}.json",
                        _dados("curta") / "curta.js", _dados("curta") / "lexico.json"):
                h.update(arq.read_bytes().replace(b"\r\n", b"\n"))
            if est.direcao.arte == "geo-em-cena":  # o mapa depende do desenho e da base, pelos hashes de FONTES.json
                from .artes import geo, geografia

                h.update(f"{geo.VERSAO}-{geografia.hash_dados()}".encode())
                for js in ("geo.js", "geo3d.js"):
                    h.update((_dados("geo") / js).read_bytes().replace(b"\r\n", b"\n"))
    for p in _arquivos_do_estilo(caminho):
        h.update(p.name.encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))  # mesmo hash com o checkout em CRLF (Windows) ou LF
    return f"{nome}-{h.hexdigest()[:14]}"


def achar(ws: Workspace, nome: str, canal: CanalWS | None, ajustes: dict | None = None, formato: str | None = None,
          estilos: dict[str, Path] | None = None) -> Path | None:
    """A amostra que já existe: a pronta do Clipator (mesmo hash) ou a do cache; None se ainda não tem."""
    k = chave(ws, nome, canal, ajustes, formato, estilos)
    pronta = indice_prontas().get(nome)
    if pronta and pronta.get("hash") == k and (pasta_prontas() / pronta["arquivo"]).is_file():
        return pasta_prontas() / pronta["arquivo"]
    p = pasta_cache() / f"{k}.mp4"
    return p if p.exists() else None


def arquivo(nome: str) -> Path | None:
    """O arquivo servido para a galeria (cache primeiro, depois as prontas); nome sem pasta."""
    for base in (pasta_cache(), pasta_prontas()):
        p = base / nome
        if p.is_file():
            return p
    return None


def caminho_amostra(ws: Workspace, nome: str, canal: CanalWS | None, ajustes: dict | None = None,
                    formato: str | None = None) -> Path:
    return pasta_cache() / f"{chave(ws, nome, canal, ajustes, formato)}.mp4"


def _renderizar(ws: Workspace, canal: CanalWS, nome: str, ajustes: dict | None, formato: str | None, video: Path,
                trans: dict, clip: Clip, pasta: Path, destino: Path, centralizar: bool, sinais: dict | None,
                progresso: Callable[[float, str], None] | None, cancelar: threading.Event | None) -> Path:
    from . import render

    est, _, est_path = ws.carregar_estilo(nome, canal, ajustes)
    if centralizar and est.reenquadramento in ("seguir-rosto", "dividido"):
        est = est.model_copy(update={"reenquadramento": "centro"})  # no vídeo neutro não há rosto para seguir
    clip = clip.model_copy(update={"formato": formato or est.formato, "cartela": est.cartela.sugerida})
    if est.abertura.ativa and not est.abertura.trechos:  # a fala de exemplo é curta demais para a escolha automática
        a = clip.inicio + (clip.fim - clip.inicio) * 0.45
        est = est.model_copy(update={"abertura": est.abertura.model_copy(update={"trechos": [(round(a, 3), round(a + 1.6, 3))]})})
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True, exist_ok=True)
    if centralizar and est.direcao.ativa:
        from . import edicao

        if est.direcao.modo == "arte":  # as cenas saem da fala de exemplo, pelo mesmo planejador sem IA dos clips
            from . import artes, subtitles
            from .timeline import Timeline
            from .transcribe import palavras

            tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
            cenas = [(c["inicio"], c["fim"], c["params"]) for c in artes.planejar_regras(
                est.direcao.arte or "", subtitles.palavras_do_clip(palavras(trans), tl), tl.duracao, artes.assinatura_timeline(tl),
                est.direcao.parametros)]
        elif est.direcao.modo == "desenho":
            from .desenho import CENAS_EXEMPLO, CENAS_EXEMPLO_MAQUETE

            exemplo = CENAS_EXEMPLO_MAQUETE if est.direcao.ficha == "maquete" else CENAS_EXEMPLO
            cenas = [(a, b, {"cena": "desenho", **p}) for a, b, p in exemplo]
        else:
            cenas = CENAS_EXEMPLO
        edicao.salvar(pasta, edicao.Edicao(itens=[edicao.Item(tipo="cena", inicio=a, fim=b, params=p) for a, b, p in cenas],
                                           cenas_planejadas=True))
    proj = _ProjetoAmostra(ws, canal, video, trans, pasta.parent, sinais)
    r = render.renderizar_clip(proj, clip, est, True, progresso, cancelar, DESTAQUES if centralizar else None,  # type: ignore[arg-type]
                               est_path.parent, exigir_ia=not centralizar, enquadrar_rosto=not centralizar)  # o boneco desenhado não é rosto
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.stem + ".tmp.mp4")
    shutil.copyfile(r.video, tmp)
    tmp.replace(destino)
    capa = destino.with_suffix(".jpg")
    subprocess.run([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-ss", "2.2", "-i", str(destino),
                    "-frames:v", "1", "-q:v", "4", str(capa)], check=False, capture_output=True, stdin=subprocess.DEVNULL)
    shutil.rmtree(pasta, ignore_errors=True)
    return destino


def _exemplo_da_direcao(est: Any) -> tuple[float, dict] | None:
    """(duração, transcrição) do exemplo próprio de uma direção guiada pela fala; None nas outras."""
    from .artes import cortes
    from .workspace import _dados

    if est.direcao.modo != "arte" or not cortes.eh_corte(est.direcao.arte):
        return None
    ex = json.loads((_dados("artes") / "exemplos" / f"{est.direcao.arte}.json").read_text(encoding="utf-8"))
    ps = ex["palavras"]
    return float(ex["duracao_s"]), {"idioma": "pt", "duracao": float(ex["duracao_s"]), "segmentos": [
        {"inicio": ps[0]["inicio"], "fim": ps[-1]["fim"], "texto": " ".join(w["texto"] for w in ps), "palavras": [{**w, "prob": 1.0} for w in ps]}]}


def gerar(ws: Workspace, nome: str, canal: CanalWS | None = None, ajustes: dict | None = None, formato: str | None = None,
          progresso: Callable[[float, str], None] | None = None, cancelar: threading.Event | None = None) -> Path:
    """A amostra do estilo no vídeo neutro; devolve o cache se já existir."""
    pronta = achar(ws, nome, canal, ajustes, formato)
    if pronta is not None:
        return pronta
    destino = caminho_amostra(ws, nome, canal, ajustes, formato)
    base = pasta_cache()
    est, _, _ = ws.carregar_estilo(nome, canal, ajustes)
    verde = est.direcao.layout == "fundo"  # a animação de fundo mostra o chroma key de verdade
    canal = canal or CanalWS(ws, base / "canal-neutro")  # sem canal: sem logo nem fontes do canal
    exemplo = _exemplo_da_direcao(est)
    if exemplo is not None:  # as direções guiadas pela fala mostram o exemplo próprio, porque a animação é a fala
        dur, trans = exemplo
        video = video_base(base / f"base-{VERSAO}-{dur:g}.mp4", dur)
        clip = Clip(id="amostra", inicio=0.0, fim=dur, titulo=TITULO, cartela=True)
    else:
        trans = _transcricao()
        video = video_base(base / f"base-{VERSAO}{'-verde' if verde else ''}.mp4", verde=verde)
        clip = Clip(id="amostra", inicio=0.0, fim=DURACAO, titulo=TITULO, cartela=True, cortes_internos=[(2.9, 3.0)])
    trabalho = base / "trabalho" / f"{destino.stem}-{os.getpid()}-{threading.get_ident()}" / "amostra"
    try:
        return _renderizar(ws, canal, nome, ajustes, formato, video, trans, clip, trabalho, destino, True, None,
                           progresso, cancelar)
    finally:
        shutil.rmtree(trabalho.parent, ignore_errors=True)


def gerar_com_video(projeto: ProjetoWS, candidato: str, nome: str, ajustes: dict | None = None, formato: str | None = None,
                    segundos: float = 6.0, progresso: Callable[[float, str], None] | None = None,
                    cancelar: threading.Event | None = None, log: Callable[[str], None] | None = None) -> Path:
    """Prévia exata: os primeiros segundos de um corte do projeto com o estilo (fica na pasta de análise)."""
    cand = next((c for c in projeto.candidatos() if c["id"] == candidato), None)
    if cand is None:
        raise KeyError(f"Candidato não encontrado: {candidato}")
    video = projeto.video_path()
    if video is None:
        raise FileNotFoundError("O projeto ainda não tem vídeo")
    ini = float(cand["inicio"])
    fim = min(float(cand["fim"]), ini + segundos)
    titulos = cand.get("titulos") or []
    clip = Clip(id="amostra", inicio=ini, fim=fim, titulo=titulos[0] if titulos else TITULO, cartela=True)
    h = hashlib.sha1(json.dumps([candidato, ajustes or {}, formato], sort_keys=True).encode()).hexdigest()[:8]
    destino = projeto.analise_dir / "amostras-estilo" / f"{chave(projeto.ws, nome, projeto.canal, ajustes, formato)}-{h}.mp4"
    if destino.exists():
        if log:
            log("• prévia deste corte com este estilo já feita antes: aproveitada")
        return destino
    trabalho = projeto.analise_dir / "amostras-estilo" / "trabalho" / "amostra"
    destaques = ((cand.get("ia") or {}).get("destaques")) or None
    try:
        from . import render

        est, _, est_path = projeto.ws.carregar_estilo(nome, projeto.canal, ajustes)
        clip = clip.model_copy(update={"formato": formato or est.formato, "cartela": est.cartela.sugerida})
        shutil.rmtree(trabalho, ignore_errors=True)
        trabalho.mkdir(parents=True, exist_ok=True)
        proj = _ProjetoAmostra(projeto.ws, projeto.canal, video, projeto.transcricao() or {}, trabalho.parent, projeto.sinais())
        r = render.renderizar_clip(proj, clip, est, True, progresso, cancelar, destaques, est_path.parent, log=log)  # type: ignore[arg-type]
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(r.video, destino)
    finally:
        shutil.rmtree(trabalho.parent / "trabalho", ignore_errors=True)
    return destino


def limpar_antigas(ws: Workspace, canal: CanalWS | None = None) -> int:
    """Apaga do cache as amostras de versões antigas dos estilos (as chaves atuais ficam)."""
    base = pasta_cache()
    if not base.is_dir():
        return 0
    atuais = set()
    for nome in ws.estilos(canal):
        try:
            atuais.add(chave(ws, nome, canal))
        except Exception:  # noqa: BLE001 - estilo com erro não tem amostra
            continue
    n = 0
    for p in base.glob("*.mp4"):
        if p.stem.startswith("base-") or p.stem in atuais:
            continue
        nome = p.stem.rsplit("-", 1)[0]
        if nome in ws.estilos(canal):  # só limpa o que é de um estilo conhecido (de outro canal fica)
            p.unlink(missing_ok=True)
            p.with_suffix(".jpg").unlink(missing_ok=True)
            n += 1
    return n
