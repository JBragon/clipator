"""Recorte da pessoa para pôr a animação atrás dela (layout "animação de fundo").

Dois caminhos:

- **Chroma key**, quando o vídeo foi gravado em fundo verde (ou azul): `detectar_chroma` olha alguns
  quadros e, se boa parte deles é de uma cor de croma, o render usa `chromakey` + `despill` do FFmpeg.
- **Segmentação**: o segmentador de selfie do MediaPipe (Apache 2.0) acha a pessoa quadro a quadro. A
  máscara é suavizada no tempo (sem tremer), tem a borda amaciada e vira um vídeo cinza que o FFmpeg usa
  com `alphamerge`. Fica em cache na pasta do clip: o mesmo trecho com o mesmo enquadramento não é
  processado de novo.

Sem o MediaPipe (ou sem o modelo), o recorte cai para uma máscara oval com a borda suave.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import media
from .media import Cancelado

MODELO_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/"
              "selfie_segmenter.tflite")
VERSAO = "v2"
LARGURA_MASCARA = 288  # a máscara é calculada pequena e ampliada no render (a borda fica suave de qualquer jeito)
SEM_QUADRO_S = 90.0  # tanto tempo sem quadro novo do FFmpeg = travou (o render segue com a máscara oval)


class RecorteTravou(RuntimeError):
    pass


@dataclass
class Chroma:
    cor: str  # 0xRRGGBB para o filtro do FFmpeg
    fracao: float  # quanto do quadro é a cor de fundo
    canal: str  # "green" ou "blue" (para o despill)


def detectar_chroma(quadros_bgr: list[np.ndarray], minimo: float = 0.28) -> Chroma | None:
    """Fundo verde ou azul? Olha a borda e o quadro inteiro: a cor de croma tem de dominar a borda."""
    if not quadros_bgr:
        return None
    import cv2

    fracs, cores, canais = [], [], []
    for q in quadros_bgr:
        hsv = cv2.cvtColor(q, cv2.COLOR_BGR2HSV)
        h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
        viva = (s > 90) & (v > 60)
        verde = viva & (h >= 35) & (h <= 85)
        azul = viva & (h >= 95) & (h <= 130)
        borda = np.zeros(verde.shape, bool)
        b = max(2, min(q.shape[:2]) // 12)
        borda[:b, :] = borda[-b:, :] = borda[:, :b] = borda[:, -b:] = True
        for masc, nome in ((verde, "green"), (azul, "blue")):
            f_borda = masc[borda].mean()
            f_tudo = masc.mean()
            if f_borda > 0.6 and f_tudo > minimo:
                fracs.append(f_tudo)
                cores.append(np.median(q[masc], axis=0))
                canais.append(nome)
                break
    if len(fracs) < max(1, (len(quadros_bgr) + 1) // 2):
        return None
    bgr = np.median(np.array(cores), axis=0).astype(int)
    canal = max(set(canais), key=canais.count)
    return Chroma(cor=f"0x{bgr[2]:02X}{bgr[1]:02X}{bgr[0]:02X}", fracao=float(np.mean(fracs)), canal=canal)


def filtro_chroma(c: Chroma) -> str:
    """Tira o fundo e o reflexo da cor na pessoa; a borda fica suave."""
    return f"chromakey=color={c.cor}:similarity=0.16:blend=0.08,despill=type={c.canal}:mix=0.6:expand=0.1"


# ---- segmentação ---------------------------------------------------------------------------------
class Segmentador:
    """Máscara de pessoa por quadro (0..1). MediaPipe se der; senão, uma oval fixa."""

    def __init__(self) -> None:
        self.nome = "oval"
        self._seg = None
        try:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import ImageSegmenter, ImageSegmenterOptions, RunningMode

            from .reframe import pasta_modelos

            modelo = pasta_modelos() / "selfie_segmenter.tflite"
            if not modelo.exists():
                tmp = modelo.with_suffix(".part")
                urllib.request.urlretrieve(MODELO_URL, tmp)  # noqa: S310 - URL fixa do Google (modelo Apache 2.0)
                os.replace(tmp, modelo)
            opts = ImageSegmenterOptions(base_options=BaseOptions(model_asset_path=str(modelo)), running_mode=RunningMode.VIDEO,
                                         output_confidence_masks=True, output_category_mask=False)
            self._seg = ImageSegmenter.create_from_options(opts)
            self.nome = "mediapipe"
        except Exception:  # noqa: BLE001 - sem MediaPipe ou sem internet na primeira vez: oval
            self._seg = None

    def mascara(self, rgb: np.ndarray, t_ms: int) -> np.ndarray:
        h, w = rgb.shape[:2]
        if self._seg is None:
            return mascara_oval(w, h)
        import mediapipe as mp

        r = self._seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)), t_ms)
        m = r.confidence_masks[0].numpy_view()
        return np.asarray(m, dtype=np.float32).reshape(h, w)

    def fechar(self) -> None:
        """Fecha o MediaPipe sem prender o render (em algumas máquinas o close demora ou trava)."""
        if self._seg is not None:
            seg, self._seg = self._seg, None
            t = threading.Thread(target=seg.close, daemon=True)
            t.start()
            t.join(5)


def mascara_oval(w: int, h: int) -> np.ndarray:
    """Busto oval na metade de baixo, borda suave (quando não há segmentação)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy, rx, ry = w * 0.5, h * 0.62, w * 0.42, h * 0.52
    d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    return np.clip((1.15 - d) / 0.3, 0, 1)


def suavizar(m: np.ndarray, anterior: np.ndarray | None, peso: float = 0.55) -> np.ndarray:
    """Estabilidade no tempo (média com o quadro anterior) e borda macia (desfoque + curva)."""
    import cv2

    if anterior is not None and anterior.shape == m.shape:
        # onde mudou muito (a pessoa se mexeu) segue o quadro novo; onde mudou pouco, segura o anterior
        mudanca = np.abs(m - anterior)
        p = np.clip(peso - mudanca, 0.1, peso)
        m = p * anterior + (1 - p) * m
    k = max(5, (min(m.shape) // 40) | 1)
    m = cv2.GaussianBlur(m, (k, k), 0)
    return np.clip((m - 0.25) / 0.5, 0, 1).astype(np.float32)


def rampa_lateral(w: int, h: int, largura: float = 0.14) -> np.ndarray:
    """Some aos poucos nas laterais: o corpo cortado pela borda do quadro não vira uma caixa reta na animação."""
    x = np.linspace(0, 1, w, dtype=np.float32)
    r = np.clip(np.minimum(x, 1 - x) / largura, 0, 1)
    r = r * r * (3 - 2 * r)  # suave
    return np.broadcast_to(r, (h, w))


def chave_mascara(video: Path, trechos: list[tuple[float, float]], cadeia: str, w: int, h: int) -> str:
    st = video.stat()
    return hashlib.sha1(json.dumps([VERSAO, str(video), st.st_size, int(st.st_mtime), trechos, cadeia, w, h]).encode()).hexdigest()[:14]


def gerar_mascara(cmd_quadros: list[str], w: int, h: int, fps: float, duracao: float, saida: Path,
                  segmentador: Segmentador | None = None, progresso: Callable[[float, str], None] | None = None,
                  cancelar: threading.Event | None = None) -> Path:
    """Lê quadros RGB (w×h) da saída do `cmd_quadros` (FFmpeg com -f rawvideo -), segmenta e grava a máscara.

    A máscara sai num vídeo cinza sem perdas (FFV1) com o mesmo fps; `saida` só aparece quando termina.
    """
    if saida.exists():
        return saida
    saida.parent.mkdir(parents=True, exist_ok=True)
    tmp = saida.with_name(saida.stem + ".tmp.mkv")
    seg = segmentador or Segmentador()
    leitor = subprocess.Popen(cmd_quadros, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    escritor = subprocess.Popen([media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                                 "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-", "-c:v", "ffv1",
                                 "-pix_fmt", "gray", str(tmp)], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    tam = w * h * 3
    total = max(1, int(duracao * fps))
    anterior = None
    rampa = rampa_lateral(w, h)
    k = 0
    import queue

    quadros: "queue.Queue[bytes | None]" = queue.Queue(maxsize=16)

    def ler() -> None:  # numa thread: a leitura bloqueante não impede o cancelar nem o vigia
        assert leitor.stdout is not None
        try:
            while True:
                buf = leitor.stdout.read(tam)
                if len(buf) < tam:
                    break
                quadros.put(buf)
        finally:
            quadros.put(None)

    threading.Thread(target=ler, daemon=True).start()
    try:
        assert escritor.stdin is not None
        ultimo = time.monotonic()
        while True:
            if cancelar is not None and cancelar.is_set():
                raise Cancelado()
            try:
                buf = quadros.get(timeout=0.5)
            except queue.Empty:
                if time.monotonic() - ultimo > SEM_QUADRO_S:
                    raise RecorteTravou(f"o FFmpeg parou de mandar quadros para o recorte (no quadro {k} de {total})")
                continue
            ultimo = time.monotonic()
            if buf is None:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            m = suavizar(seg.mascara(rgb, int(k * 1000 / fps)), anterior)
            anterior = m
            escritor.stdin.write((m * rampa * 255).astype(np.uint8).tobytes())
            k += 1
            if progresso and k % 15 == 0:
                progresso(min(1.0, k / total), f"recortando a pessoa ({seg.nome})")
        escritor.stdin.close()
        try:
            codigo = escritor.wait(timeout=120)
        except subprocess.TimeoutExpired as exc:
            raise RecorteTravou("o FFmpeg não terminou de gravar a máscara") from exc
        if codigo != 0 or k == 0:
            raise RuntimeError("Não consegui gravar a máscara do recorte")
    except BaseException:
        for p in (leitor, escritor):
            if p.poll() is None:
                p.kill()
        media.apagar_parcial(tmp)
        raise
    finally:
        if segmentador is None:
            seg.fechar()
        if leitor.poll() is None:
            leitor.kill()
    tmp.replace(saida)
    return saida


def visao_disponivel() -> bool:
    """OpenCV vem do extra 'visao'; sem ele o render cai para a máscara oval em vez de quebrar."""
    import importlib.util

    return importlib.util.find_spec("cv2") is not None


def quadros_de_amostra(video: Path, tempos: list[float], largura: int = 320) -> list[np.ndarray]:
    """Alguns quadros (BGR, pequenos) para a detecção de chroma."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    out = []
    try:
        for t in tempos:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, q = cap.read()
            if ok and q is not None:
                h, w = q.shape[:2]
                out.append(cv2.resize(q, (largura, max(2, int(h * largura / w)))))
    finally:
        cap.release()
    return out
