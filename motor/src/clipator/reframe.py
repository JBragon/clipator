"""Reenquadramento: acha o rosto e calcula a trajetória da "câmera" no crop.

A ideia (analisar em baixa resolução, suavizar a trajetória e aplicar no
FFmpeg com sendcmd mudando o x do crop) segue openshorts/reframe_v2.py, MIT
License, Copyright (c) 2024 OpenShorts. O código aqui foi reescrito para o
Clipator. O detector principal é o YuNet do OpenCV (modelo do opencv_zoo, MIT
License, Copyright (c) 2020 Shiqi Yu), que acha rosto pequeno de plano aberto;
na falta dele, MediaPipe (Apache 2.0) e, por último, o Haar cascade do OpenCV.

A câmera segue o locutor como um operador faria: escolhe uma pessoa e só troca
com motivo (sumiu ou outra domina o quadro por um tempo), fica parada enquanto
o rosto está perto do centro, recentraliza com aceleração e freio suaves
(filtro gaussiano de fase zero, sem atraso) e corta seco em troca de cena ou
de pessoa. O x do crop muda a cada quadro de saída, sem degraus.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .media import Cancelado
from .timeline import Timeline

MODELO_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
YUNET_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
AMOSTRAS_POR_SEGUNDO = 8.0
LARGURA_ANALISE = 640


def pasta_modelos() -> Path:
    p = Path(os.environ.get("CLIPATOR_MODELOS", Path.home() / ".clipator" / "modelos"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _baixar(url: str, destino: Path, sha256: str | None = None) -> Path:
    """Baixa uma vez para a pasta de modelos (depois funciona offline); confere o hash quando ele é conhecido."""
    if destino.exists():
        return destino
    tmp = destino.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:  # noqa: S310 - URL fixa
        f.write(r.read())
    if sha256 and hashlib.sha256(tmp.read_bytes()).hexdigest() != sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"modelo baixado de {url} veio diferente do esperado")
    os.replace(tmp, destino)
    return destino


@dataclass
class Rosto:
    cx: float  # centro em fração da largura (0..1)
    cy: float
    area: float  # fração da área do quadro
    # quanto a boca mexeu desde a amostra anterior da mesma pessoa (None = sem como medir): ver amostrar_rostos
    fala: float | None = None
    boca: "np.ndarray | None" = field(default=None, repr=False, compare=False)  # recorte da boca, só durante a amostragem


class Detector:
    """YuNet (OpenCV) se der; senão MediaPipe; senão Haar cascade do OpenCV; senão nada (centro).

    O YuNet vem primeiro porque acha rosto pequeno (podcast em plano aberto, pessoa andando ao fundo), que o
    BlazeFace de curto alcance do MediaPipe perde: num plano aberto de teste ele achou rosto em 2 de 120 quadros,
    o YuNet em 120 de 120.
    """

    def __init__(self) -> None:
        self._yn = None
        self._lock = threading.Lock()
        self._mp = None
        self._haar = None
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.disponivel = False
            return
        self.disponivel = True
        if not os.environ.get("CLIPATOR_SEM_YUNET"):
            try:
                self._yn = self._carregar_yunet()
            except Exception:
                self._yn = None
        if self._yn is None:
            try:
                self._mp = self._carregar_mediapipe()
            except Exception:
                self._mp = None
        if self._yn is None and self._mp is None:
            import cv2

            path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            haar = cv2.CascadeClassifier(path) if os.path.exists(path) else None
            self._haar = haar if haar is not None and not haar.empty() else None

    @staticmethod
    def _carregar_yunet():
        import cv2

        modelo = _baixar(YUNET_URL, pasta_modelos() / "face_detection_yunet_2023mar.onnx", YUNET_SHA256)
        # limiar 0.6, NMS 0.3, até 50 rostos; o tamanho de entrada é ajustado a cada quadro
        return cv2.FaceDetectorYN.create(str(modelo), "", (LARGURA_ANALISE, LARGURA_ANALISE * 9 // 16), 0.6, 0.3, 50)

    @staticmethod
    def _carregar_mediapipe():
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions

        modelo = _baixar(MODELO_URL, pasta_modelos() / "blaze_face_short_range.tflite")
        opts = FaceDetectorOptions(base_options=BaseOptions(model_asset_path=str(modelo)), min_detection_confidence=0.5)
        return FaceDetector.create_from_options(opts)

    @property
    def nome(self) -> str:
        if self._yn is not None:
            return "yunet"
        return "mediapipe" if self._mp else ("opencv-haar" if self._haar is not None else "nenhum")

    def detectar(self, frame_bgr: np.ndarray) -> list[Rosto]:
        h, w = frame_bgr.shape[:2]
        out: list[Rosto] = []
        if self._yn is not None:
            with self._lock:  # o mesmo detector serve várias threads (render e thumbs) e guarda o tamanho de entrada
                self._yn.setInputSize((w, h))
                _, faces = self._yn.detect(np.ascontiguousarray(frame_bgr))
            cinza = None
            for f in faces if faces is not None else []:
                x, y, fw, fh = (float(v) for v in f[:4])
                x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(float(w), x + fw), min(float(h), y + fh)
                if x1 > x0 and y1 > y0:
                    if cinza is None:
                        import cv2

                        cinza = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
                    out.append(Rosto((x0 + x1) / 2 / w, (y0 + y1) / 2 / h, (x1 - x0) * (y1 - y0) / (w * h),
                                     boca=recorte_boca(cinza, [float(v) for v in f[4:14]])))
        elif self._mp is not None:
            import cv2
            import mediapipe as mp

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = self._mp.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            for d in res.detections:
                b = d.bounding_box
                out.append(Rosto((b.origin_x + b.width / 2) / w, (b.origin_y + b.height / 2) / h, b.width * b.height / (w * h)))
        elif self._haar is not None:
            import cv2

            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            for x, y, fw, fh in self._haar.detectMultiScale(gray, 1.15, 5, minSize=(max(24, w // 25), max(24, w // 25))):
                out.append(Rosto((x + fw / 2) / w, (y + fh / 2) / h, fw * fh / (w * h)))
        return out


def recorte_boca(cinza: np.ndarray, marcos: list[float]) -> np.ndarray | None:
    """A boca alinhada pelos marcos do YuNet (olhos e cantos da boca), num tamanho fixo e com o brilho normalizado.

    Alinhar pelos marcos tira o balanço da cabeça: o que muda entre duas amostras é a boca abrindo e fechando.
    """
    import cv2

    if len(marcos) < 10:
        return None
    olho_d, olho_e = np.array(marcos[0:2]), np.array(marcos[2:4])
    boca_d, boca_e = np.array(marcos[6:8]), np.array(marcos[8:10])
    olhos = float(np.hypot(*(olho_e - olho_d)))
    if olhos < 6:  # rosto pequeno demais para ver a boca
        return None
    cx, cy = (boca_d + boca_e) / 2
    x0, x1 = int(cx - 0.9 * olhos), int(cx + 0.9 * olhos)
    y0, y1 = int(cy - 0.36 * olhos), int(cy + 0.6 * olhos)
    if x0 < 0 or y0 < 0 or x1 > cinza.shape[1] or y1 > cinza.shape[0]:
        return None
    p = cv2.resize(cinza[y0:y1, x0:x1], (32, 24), interpolation=cv2.INTER_AREA)
    return (p - p.mean()) / (p.std() + 1e-3)


_detector: Detector | None = None
_det_lock = threading.Lock()


def detector() -> Detector:
    global _detector
    with _det_lock:
        if _detector is None:
            _detector = Detector()
            # O MediaPipe desliga o próprio executor no encerramento das threads, que roda antes
            # do atexit comum; registrar ali fecha o detector antes e evita um aviso no fim.
            registrar = getattr(threading, "_register_atexit", None)
            try:
                registrar(_fechar_detector) if registrar else atexit.register(_fechar_detector)
            except Exception:
                atexit.register(_fechar_detector)
        return _detector


def _fechar_detector() -> None:
    """Fecha o MediaPipe antes do interpretador desmontar os módulos (evita aviso no fim)."""
    global _detector
    if _detector is not None and _detector._mp is not None:
        try:
            _detector._mp.close()
        except Exception:
            pass
        _detector._mp = None


def amostrar_rostos(video: str | Path, tl: Timeline, cancelar: threading.Event | None = None,
                    por_segundo: float = AMOSTRAS_POR_SEGUNDO) -> list[tuple[float, list[Rosto]]]:
    """Lê quadros em sequência (sem seek repetido) e detecta rostos. Tempo = tempo do clip."""
    det = detector()
    if not det.disponivel:
        return []
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    passo = max(1, int(round(fps / por_segundo)))
    out: list[tuple[float, list[Rosto]]] = []
    acc = 0.0
    try:
        for s, e in tl.trechos:
            cap.set(cv2.CAP_PROP_POS_MSEC, s * 1000)
            idx = 0
            antes: list[Rosto] = []  # a amostra anterior, para medir quanto cada boca mexeu
            while True:
                if cancelar is not None and cancelar.is_set():
                    raise Cancelado()
                t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if t > e or t < 0:
                    break
                if idx % passo == 0:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    h, w = frame.shape[:2]
                    if w > LARGURA_ANALISE:
                        frame = cv2.resize(frame, (LARGURA_ANALISE, int(h * LARGURA_ANALISE / w)))
                    rostos = det.detectar(frame)
                    _medir_fala(rostos, antes)
                    out.append((acc + max(0.0, t - s), rostos))
                    for r in antes:
                        r.boca = None  # já serviu: não guarda um recorte por amostra do clip inteiro
                    antes = rostos
                else:
                    if not cap.grab():
                        break
                idx += 1
            acc += e - s
    finally:
        cap.release()
    for _, rs in out[-1:]:
        for r in rs:
            r.boca = None
    return out


def _medir_fala(rostos: list[Rosto], antes: list[Rosto]) -> None:
    """`fala` de cada rosto: diferença média entre a boca dele agora e a da mesma pessoa na amostra anterior."""
    for r in rostos:
        if r.boca is None:
            continue
        pares = [a for a in antes if a.boca is not None and _mesma_pessoa(r, a)]
        if pares:
            a = min(pares, key=lambda a: abs(a.cx - r.cx) + abs(a.cy - r.cy))
            r.fala = round(float(np.mean(np.abs(r.boca - a.boca))), 4)


# --- câmera que segue o locutor -------------------------------------------------------------------------------
FOLGA = 0.03  # o rosto balança até 3% da largura do crop sem mexer a câmera (não treme); passou disso, ela acompanha já
SUAVIZACAO_S = 0.45  # desvio do filtro gaussiano, em segundos: aceleração e freio suaves
MEDIANA_S = 0.7  # janela da mediana que tira falso positivo solto do detector
TROCA_AUSENTE_S = 0.8  # o locutor sumiu por esse tempo e há outro rosto: troca
TROCA_DOMINIO_S = 1.5  # outro rosto bem maior (o locutor com menos de 60% da área dele) por esse tempo: troca
CORTE_TROCA = 0.5  # troca de pessoa que anda mais que meia largura do crop vira corte seco, não panorâmica
# quem fala (duas pessoas na mesma imagem: react, podcast em plano aberto): a boca que mais mexe em volta da amostra
FALA_JANELA_S = 0.5  # média da `fala` de cada pessoa de 0.5 s antes a 0.5 s depois da amostra
FALA_MIN = 0.22  # abaixo disso ninguém está falando (boca parada; vídeo reagido pausado dá 0)
FALA_RAZAO = 1.5  # quem fala mexe a boca pelo menos 1.5 vez mais que o outro; menos que isso é empate e nada muda
TROCA_FALA_S = 1.0  # o outro falou por esse tempo: a câmera vai para ele (desde quando ele começou)

Ponto = tuple[float, float, "float | None"]  # (t, valor, pulo): pulo = instante do corte seco antes deste ponto


def _mesma_pessoa(a: Rosto, b: Rosto) -> bool:
    lado = float(np.sqrt(max(a.area, 1e-6)))
    return abs(a.cx - b.cx) < max(0.06, 1.2 * lado) and abs(a.cy - b.cy) < max(0.10, 1.5 * lado)


def quem_fala(amostras: list[tuple[float, list[Rosto]]]) -> list[Rosto | None]:
    """Em cada amostra com duas pessoas ou mais, o rosto de quem está falando, ou None (uma pessoa só, empate,
    ninguém falando ou sem medida da boca).

    Num react, o vídeo reagido de um lado e o locutor do outro estão sempre na imagem; o tamanho do rosto não diz
    quem fala. A boca diz: a de quem fala abre e fecha, a do outro fica quase parada (e o vídeo reagido pausado
    enquanto o locutor comenta fica parado de vez).
    """
    return _falas(amostras)[0]


def _falas(amostras: list[tuple[float, list[Rosto]]]) -> tuple[list[Rosto | None], list[Rosto | None]]:
    """(quem fala com certeza, quem mexe mais a boca mesmo sem certeza). O segundo diz onde a troca começou de fato:
    a fala de um vai crescendo enquanto a do outro some, e a certeza só chega no meio dessa passagem."""
    ts = [t for t, _ in amostras]
    validos = [_validos(rs) for _, rs in amostras]
    out: list[Rosto | None] = []
    inclina: list[Rosto | None] = []
    a = b = 0
    for i, t in enumerate(ts):
        while ts[a] < t - FALA_JANELA_S:
            a += 1
        while b + 1 < len(ts) and ts[b + 1] <= t + FALA_JANELA_S:
            b += 1
        rs = validos[i]
        if len(rs) < 2:
            out.append(None)
            inclina.append(None)
            continue
        notas = []
        for r in rs:
            vs = []
            for j in range(a, b + 1):
                par = [x for x in validos[j] if x.fala is not None and _mesma_pessoa(r, x)]
                if par:
                    vs.append(min(par, key=lambda x: abs(x.cx - r.cx) + abs(x.cy - r.cy)).fala)
            notas.append((float(np.mean(vs)) if len(vs) >= 2 else 0.0, r))
        notas.sort(key=lambda n: n[0], reverse=True)
        (n1, r1), (n2, _) = notas[0], notas[1]
        out.append(r1 if n1 >= FALA_MIN and n1 >= FALA_RAZAO * n2 else None)
        inclina.append(r1 if n1 >= FALA_MIN / 2 and n1 > 1.1 * n2 else None)
    return out, inclina


def _escolher_locutor(amostras: list[tuple[float, list[Rosto]]],
                      cenas: list[float]) -> tuple[list[Rosto | None], list[bool]]:
    """Quem a câmera segue em cada amostra (None = ninguém visto; a câmera segura) e onde houve troca de pessoa.

    Fica na mesma pessoa enquanto ela aparece; só troca se ela sumir por TROCA_AUSENTE_S, se outra pessoa falar por
    TROCA_FALA_S (quem_fala) ou, sem saber quem fala, se outro rosto dominar o quadro por TROCA_DOMINIO_S. Assim duas
    pessoas parecidas em tamanho não fazem a câmera ir e voltar, e num react a câmera vai para quem está falando.
    """
    falantes, inclina = _falas(amostras)
    alvo: Rosto | None = None
    faltou = dominio = falou = 0.0
    k_falta = k_dominio = k_fala = 0  # amostra em que o locutor sumiu / o outro passou a dominar / o outro começou a falar
    ci = 0
    out: list[Rosto | None] = []
    trocas: list[bool] = []
    t_ant = amostras[0][0] if amostras else 0.0

    def trocar(novo: Rosto, desde: int) -> None:
        """A troca vale desde quando o motivo começou, não de quando foi confirmada: a câmera não chega atrasada."""
        ref = novo
        for j in range(len(out) - 1, desde - 1, -1):
            rs_j = _validos(amostras[j][1]) or list(amostras[j][1])
            par = min(rs_j, key=lambda r: abs(r.cx - ref.cx) + abs(r.cy - ref.cy)) if rs_j else None
            par = par if par is not None and _mesma_pessoa(ref, par) else None
            out[j] = par
            trocas[j] = False
            ref = par or ref
        if desde < len(out):
            trocas[desde] = True

    for i, (t, rostos) in enumerate(amostras):
        dt, t_ant = max(0.0, t - t_ant), t
        while ci < len(cenas) and cenas[ci] <= t:
            ci += 1
            alvo, faltou, dominio, falou = None, 0.0, 0.0, 0.0  # cena nova: escolhe de novo
        rs = _validos(rostos) or list(rostos)
        maior = max(rs, key=lambda r: r.area) if rs else None
        fala = falantes[i]
        mesmo = None
        if alvo is not None and rs:
            perto = min(rs, key=lambda r: abs(r.cx - alvo.cx) + abs(r.cy - alvo.cy))
            mesmo = perto if _mesma_pessoa(alvo, perto) else None
        troca = False
        if mesmo is not None and fala is not None and fala is not mesmo:  # o outro está falando
            faltou = dominio = 0.0
            k_fala = i if falou == 0.0 else k_fala
            falou += dt if falou else 1e-9
            if falou >= TROCA_FALA_S:
                alvo, falou = fala, 0.0
                ult = max((j for j in range(len(trocas)) if trocas[j]), default=0)
                while k_fala - 1 > ult and inclina[k_fala - 1] is not None and _mesma_pessoa(fala, inclina[k_fala - 1]):
                    k_fala -= 1  # a fala dele já vinha ganhando antes da certeza: a câmera chega quando ela começou
                trocar(fala, k_fala)
                troca = k_fala >= i
            else:
                alvo = mesmo
            out.append(alvo)
        elif mesmo is not None:
            faltou = falou = 0.0
            if fala is mesmo:  # quem a câmera segue está falando: o tamanho do outro não tira ela dele
                dominio = 0.0
            elif maior is not mesmo and mesmo.area < 0.6 * maior.area:
                k_dominio = i if dominio == 0.0 else k_dominio
                dominio += dt if dominio else 1e-9
            else:
                dominio = 0.0
            if dominio >= TROCA_DOMINIO_S:
                alvo, dominio = maior, 0.0
                trocar(maior, k_dominio)
                troca = k_dominio >= i
            else:
                alvo = mesmo
            out.append(alvo)
        elif alvo is None:
            alvo = fala or maior
            out.append(alvo)
        else:
            falou = 0.0
            k_falta = i if faltou == 0.0 else k_falta
            faltou += dt if faltou else 1e-9
            if maior is not None and faltou >= TROCA_AUSENTE_S:
                alvo, faltou, dominio = maior, 0.0, 0.0
                trocar(maior, k_falta)
                troca = k_falta >= i
                out.append(alvo)
            else:
                out.append(None)
        trocas.append(troca)
    return out, trocas


def _gauss(v: np.ndarray, sigma: float) -> np.ndarray:
    """Filtro gaussiano de fase zero (não atrasa: o clip é analisado inteiro antes do render)."""
    if sigma <= 0.3 or len(v) < 3:
        return v
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(v, r, mode="edge"), k, mode="same")[r:-r]


def _mediana(v: np.ndarray, k: int) -> np.ndarray:
    if k < 1 or len(v) < 3:
        return v
    return np.array([np.median(v[max(0, i - k): i + k + 1]) for i in range(len(v))])


def _guia(v: np.ndarray, folga: float) -> np.ndarray:
    """Câmera presa ao alvo por uma corda de comprimento `folga`: parada enquanto ele balança dentro da corda e
    acompanhando no mesmo instante em que ele sai dela (sem esperar, sem degrau)."""
    if folga <= 0 or not len(v):
        return v
    out = np.empty_like(v)
    cam = float(v[0])
    for i, x in enumerate(v):
        if x - cam > folga:
            cam = float(x) - folga
        elif cam - x > folga:
            cam = float(x) + folga
        out[i] = cam
    return out


def suavizar_caminho(ts: list[float], valores: list[float | None], pulos: list[float | None], folga: float,
                     suavizacao: float = SUAVIZACAO_S, padrao: float = 0.5) -> list[float]:
    """Caminho suave de uma coordenada da câmera. `valores` None = segura a última posição; `pulos[i]` não None
    começa um trecho novo em i (corte seco). Cada trecho é suavizado sozinho, então nada desliza através de um corte."""
    n = len(ts)
    if n == 0:
        return []
    dt = float(np.median(np.diff(ts))) if n > 1 else 1.0
    dt = dt if dt > 0 else 1.0
    inicios = [0] + [i for i in range(1, n) if pulos[i] is not None] + [n]
    out: list[float] = []
    ultimo = next((v for v in valores if v is not None), padrao)
    for a, b in zip(inicios, inicios[1:]):
        seg = valores[a:b]
        atual = next((v for v in seg if v is not None), ultimo)
        cheio = []
        for v in seg:
            atual = v if v is not None else atual
            cheio.append(atual)
        arr = _mediana(np.array(cheio, dtype=float), int(round(MEDIANA_S / 2 / dt)))
        arr = _gauss(_guia(arr, folga), suavizacao / dt)
        out += [float(x) for x in arr]
        ultimo = cheio[-1]
    return out


def trajetoria(amostras: list[tuple[float, list[Rosto]]], cortes_cena: list[float] | None = None,
               largura_crop: float = 0.32, folga: float = FOLGA, suavizacao: float = SUAVIZACAO_S) -> list[Ponto]:
    """Centro x (0..1 da largura da fonte) da câmera em cada amostra: (t, cx, pulo).

    `largura_crop` = largura do crop em fração da fonte (a folga é medida nela). `pulo` não None = corte seco
    naquele instante, entre a amostra anterior e esta (corte de cena ou troca de pessoa longe).
    """
    if not amostras:
        return [(0.0, 0.5, None)]
    cenas = sorted(cortes_cena or [])
    ts = [t for t, _ in amostras]
    alvos, trocas = _escolher_locutor(amostras, cenas)
    valores = [a.cx if a is not None else None for a in alvos]
    pulos: list[float | None] = [None] * len(ts)
    ci = 0
    ultimo = None
    for i, t in enumerate(ts):
        corte = None
        while ci < len(cenas) and cenas[ci] <= t:
            corte = cenas[ci]
            ci += 1
        if i > 0 and corte is not None:
            pulos[i] = corte
        elif i > 0 and trocas[i] and ultimo is not None and valores[i] is not None and abs(valores[i] - ultimo) > CORTE_TROCA * largura_crop:
            pulos[i] = t
        if valores[i] is not None:
            ultimo = valores[i]
    xs = suavizar_caminho(ts, valores, pulos, folga * largura_crop, suavizacao)
    return [(round(t, 3), round(min(1.0, max(0.0, x)), 4), p) for t, x, p in zip(ts, xs, pulos)]


def _instante(t: float, fps: float) -> str:
    """Hora do comando no sendcmd: meio quadro antes do quadro dele. Com a hora exata arredondada (0.042 para o
    quadro de 0.041666 s), o comando caía no quadro seguinte junto com o próximo, e a câmera engasgava."""
    return f"{max(0.0, t - 0.5 / (fps if fps and fps > 0 else 30.0)):.4f}"


def _por_quadro(pontos: list[tuple[float, tuple[float, ...], float | None]], fps: float) -> list[tuple[float, tuple[float, ...]]]:
    """Valor em cada quadro de saída: curva Catmull-Rom entre as amostras (velocidade contínua, sem quinas de
    interpolação linear) e degrau só nos cortes secos."""
    if not pontos:
        return []
    fps = fps if fps and fps > 0 else 30.0
    out = []
    j = 0
    m = len(pontos)
    n = int(np.floor(pontos[-1][0] * fps)) + 1
    for f in range(n):
        t = f / fps
        while j + 1 < m and pontos[j + 1][0] <= t:
            j += 1
        t0, v0, _ = pontos[j]
        if t <= t0 or j + 1 >= m:
            out.append((t, v0))
            continue
        t1, v1, pulo = pontos[j + 1]
        if pulo is not None:
            out.append((t, v1 if t >= pulo else v0))
            continue
        va = pontos[j - 1][1] if j > 0 and pontos[j][2] is None else v0  # vizinhos do mesmo trecho
        vb = pontos[j + 2][1] if j + 2 < m and pontos[j + 2][2] is None else v1
        u = (t - t0) / max(t1 - t0, 1e-9)
        u2, u3 = u * u, u * u * u
        out.append((t, tuple(0.5 * (2 * b + (c - a) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (3 * b - a - 3 * c + d) * u3)
                             for a, b, c, d in zip(va, v0, v1, vb))))
    return out


def rosto_no_quadro(amostras: list[tuple[float, list[Rosto]]], traj: list[Ponto] | None, src_w: int, src_h: int,
                    cw: int, ch: int, x0: int) -> tuple[float, float, float] | None:
    """Onde o rosto do locutor fica no vídeo já enquadrado: (cx, cy, altura), frações do quadro de saída.

    Mediana do maior rosto de cada amostra (estável: não treme). `traj` é a câmera do seguir-rosto
    (alinhada com as amostras); sem ela, o crop fica parado em `x0`.
    """
    y0 = max(0, (src_h - ch) // 2)
    xs, ys, hs = [], [], []
    for k, (_, rostos) in enumerate(amostras):
        if not rostos:
            continue
        if traj and k < len(traj):
            cx0 = max(0.0, min(src_w - cw, traj[k][1] * src_w - cw / 2))
        else:
            cx0 = x0
        no_crop = [r for r in rostos if cx0 <= r.cx * src_w <= cx0 + cw]  # o locutor seguido, não quem ficou de fora
        r = max(no_crop or rostos, key=lambda r: r.area)
        xs.append((r.cx * src_w - cx0) / cw)
        ys.append((r.cy * src_h - y0) / ch)
        hs.append(float(np.sqrt(max(r.area, 1e-6) * src_w * src_h)) / ch)
    if len(xs) < 3:
        return None
    return (float(np.clip(np.median(xs), 0, 1)), float(np.clip(np.median(ys), 0, 1)), float(np.clip(np.median(hs), 0.02, 1)))


def topo_dos_rostos(amostras: list[tuple[float, list[Rosto]]], traj: list[Ponto] | None, src_w: int, src_h: int,
                    cw: int, ch: int, x0: int) -> float | None:
    """O alto da cabeça mais alta do corte, em fração do quadro enquadrado (perto do mínimo, sem um erro isolado).

    A mediana de rosto_no_quadro serve para o tamanho; esta serve para não cortar os olhos de quem aparece mais alto
    (num podcast com duas câmeras, o convidado costuma estar em outra altura que o apresentador).
    """
    y0 = max(0, (src_h - ch) // 2)
    topos = []
    for k, (_, rostos) in enumerate(amostras):
        if not rostos:
            continue
        cx0 = max(0.0, min(src_w - cw, traj[k][1] * src_w - cw / 2)) if traj and k < len(traj) else x0
        no_crop = [r for r in rostos if cx0 <= r.cx * src_w <= cx0 + cw]
        r = max(no_crop or rostos, key=lambda r: r.area)
        h = float(np.sqrt(max(r.area, 1e-6) * src_w * src_h))
        topos.append((r.cy * src_h - 0.8 * h - y0) / ch)  # a caixa do detector vai da testa ao queixo: o cabelo fica acima
    if len(topos) < 3:
        return None
    return float(np.clip(np.percentile(topos, 8), 0, 1))


ROSTO_MIN_AREA = 0.002  # rostos menores que isso (fundo, plateia, foto na parede) não contam como pessoa
DIVIDIDO_TODO = 0.97  # com os dois na tela em 97% do clip ou mais, empilha o clip inteiro
TRECHO_MIN = 1.5  # segundos: trechos mais curtos que isso não trocam de layout (evita piscar)


def _validos(rostos: list[Rosto]) -> list[Rosto]:
    """Rostos grandes o bastante, sem repetição: duas caixas no mesmo lugar (o Haar às vezes marca o rosto e,
    por fora, a cabeça inteira) são a mesma pessoa, e fica a menor."""
    out: list[Rosto] = []
    for r in sorted((r for r in rostos if r.area > ROSTO_MIN_AREA), key=lambda r: r.area):
        lado = float(np.sqrt(r.area))  # lado aproximado da caixa, em fração (média entre largura e altura)
        if not any(abs(r.cx - k.cx) < lado / 2 and abs(r.cy - k.cy) < lado / 2 for k in out):
            out.append(r)
    return out


def _dois_grupos(xs: list[float]) -> tuple[float, float] | None:
    """k-means 1D com k=2 nos centros x: (esquerda, direita), ou None se não há dois grupos claros."""
    if len(xs) < 6:
        return None
    xs_arr = np.sort(np.array(xs))
    c1, c2 = float(np.percentile(xs_arr, 25)), float(np.percentile(xs_arr, 75))
    for _ in range(20):
        g1 = xs_arr[np.abs(xs_arr - c1) <= np.abs(xs_arr - c2)]
        g2 = xs_arr[np.abs(xs_arr - c1) > np.abs(xs_arr - c2)]
        if len(g1) == 0 or len(g2) == 0:
            return None
        c1, c2 = float(g1.mean()), float(g2.mean())
    if abs(c2 - c1) < 0.2 or min(len(g1), len(g2)) < 0.2 * len(xs_arr):
        return None
    return (min(c1, c2), max(c1, c2))


def dois_rostos(amostras: list[tuple[float, list[Rosto]]]) -> tuple[float, float] | None:
    """Os centros x dos dois falantes mais frequentes."""
    return _dois_grupos([r.cx for _, rs in amostras for r in _validos(rs)])


@dataclass
class Caixa:
    """Recorte na fonte, em pixels."""

    x: int
    y: int
    w: int
    h: int


@dataclass
class Dividido:
    """Tela dividida: o recorte de cada pessoa e quando as duas estão na mesma imagem.

    `caixas` = (metade de cima, metade de baixo). `trechos` = intervalos do clip (em segundos) em que as duas
    aparecem juntas; fora deles a câmera da fonte está num close e o vídeo segue o rosto. Vazio = o clip todo.
    """

    caixas: tuple[Caixa, Caixa]
    trechos: list[tuple[float, float]]
    cobertura: float
    # canto de cima à esquerda de cada recorte ao longo do clip, (t, x, y, pulo), na ordem de `caixas`:
    # cada metade acompanha a própria pessoa. Vazio = recortes parados em `caixas`.
    trilhas: tuple[list[tuple[float, float, float, float | None]], ...] = field(default_factory=tuple)


def _caixa_pessoa(rostos: list[Rosto], src_w: int, src_h: int, aspecto: float, largura_max: float,
                  tamanho_rosto: float, y_rosto: float = 0.42, zoom_max: float = 2.5) -> Caixa:
    """Recorte parado com a proporção `aspecto` (largura/altura), o rosto com `tamanho_rosto` da altura."""
    cx = float(np.median([r.cx for r in rostos])) * src_w
    cy = float(np.median([r.cy for r in rostos])) * src_h
    rosto_px = float(np.sqrt(np.median([r.area for r in rostos]) * src_w * src_h))
    h = rosto_px / tamanho_rosto
    h = min(h, largura_max / aspecto)  # não deixa o recorte engolir a outra pessoa
    h = max(h, src_h / zoom_max)  # nem ampliar demais (o vídeo fica borrado)
    h = min(h, src_h, src_w / aspecto)
    w = h * aspecto
    w_i, h_i = int(w) - int(w) % 2, int(h) - int(h) % 2
    x = int(round(max(0.0, min(src_w - w_i, cx - w_i / 2))))
    y = int(round(max(0.0, min(src_h - h_i, cy - y_rosto * h_i))))
    return Caixa(x - x % 2, y - y % 2, w_i, h_i)


def _suavizar(flags: list[bool], k: int = 2) -> list[bool]:
    """Voto da maioria numa janela de 2k+1 amostras: tira as falhas soltas do detector."""
    out = []
    for i in range(len(flags)):
        janela = flags[max(0, i - k): i + k + 1]
        out.append(sum(janela) * 2 > len(janela))
    return out


def _trechos_duplos(amostras: list[tuple[float, list[Rosto]]], duracao: float,
                    cortes_cena: list[float] | None) -> list[tuple[float, float]]:
    """Intervalos do clip com duas pessoas na imagem. As bordas vão para o corte de cena mais próximo, se houver."""
    if not amostras:
        return []
    flags = _suavizar([len(_validos(rs)) >= 2 for _, rs in amostras])
    ts = [t for t, _ in amostras]
    cenas = sorted(cortes_cena or [])

    def borda(i: int) -> float:  # fronteira entre a amostra i-1 e a i
        a, b = ts[i - 1], ts[i]
        dentro = [c for c in cenas if a < c <= b]
        return dentro[0] if dentro else (a + b) / 2

    trechos: list[list[float]] = []
    for i, f in enumerate(flags):
        if not f:
            continue
        if i > 0 and flags[i - 1]:
            continue
        j = i
        while j + 1 < len(flags) and flags[j + 1]:
            j += 1
        ini = 0.0 if i == 0 else borda(i)
        fim = float(duracao) if j == len(flags) - 1 else borda(j + 1)
        trechos.append([ini, fim])
    # buracos curtos entre trechos duplos viram duplos; depois, trechos duplos curtos somem
    unidos: list[list[float]] = []
    for t in trechos:
        if unidos and t[0] - unidos[-1][1] < TRECHO_MIN:
            unidos[-1][1] = t[1]
        else:
            unidos.append(t)
    return [(round(a, 3), round(b, 3)) for a, b in unidos if b - a >= TRECHO_MIN]


def enquadramento_dividido(amostras: list[tuple[float, list[Rosto]]], src_w: int, src_h: int, out_w: int, meia_h: int,
                           duracao: float, em_cima: str = "esquerda", tamanho_rosto: float = 0.35,
                           cortes_cena: list[float] | None = None) -> Dividido | None:
    """Tela dividida com duas pessoas, uma em cada metade, cada uma com zoom no próprio rosto.

    Só conta as amostras com duas pessoas na mesma imagem, então podcast com câmeras separadas também funciona:
    nos closes o vídeo segue o rosto e, quando a câmera abre nas duas, empilha. Sem nenhum plano com as duas: None.
    """
    # em cada imagem com as duas pessoas, só os dois maiores rostos (um terceiro costuma ser engano ou plateia)
    pares = [sorted(_validos(rs), key=lambda r: r.area, reverse=True)[:2] for _, rs in amostras]
    duplas = [p for p in pares if len(p) == 2]
    if len(duplas) < 3:
        return None
    grupos = _dois_grupos([r.cx for par in duplas for r in par])
    if grupos is None:
        return None
    meio = (grupos[0] + grupos[1]) / 2
    por_amostra: list[tuple[Rosto, Rosto] | None] = []
    for par in pares:
        if len(par) == 2:
            e, d = (par[0], par[1]) if par[0].cx <= par[1].cx else (par[1], par[0])
            if e.cx < meio < d.cx:  # um de cada lado: senão é engano do detector
                por_amostra.append((e, d))
                continue
        por_amostra.append(None)
    esq = [p[0] for p in por_amostra if p]
    dir_ = [p[1] for p in por_amostra if p]
    if len(esq) < 3 or len(dir_) < 3:
        return None
    aspecto = out_w / meia_h
    largura_max = max(0.35, 1.1 * (grupos[1] - grupos[0])) * src_w
    c_esq = _caixa_pessoa(esq, src_w, src_h, aspecto, largura_max, tamanho_rosto)
    c_dir = _caixa_pessoa(dir_, src_w, src_h, aspecto, largura_max, tamanho_rosto)
    trilha_esq = _trilha_caixa(amostras, [p[0] if p else None for p in por_amostra], c_esq, src_w, src_h, cortes_cena)
    trilha_dir = _trilha_caixa(amostras, [p[1] if p else None for p in por_amostra], c_dir, src_w, src_h, cortes_cena)
    caixas = (c_dir, c_esq) if em_cima == "direita" else (c_esq, c_dir)
    trilhas = (trilha_dir, trilha_esq) if em_cima == "direita" else (trilha_esq, trilha_dir)
    trechos = _trechos_duplos(amostras, duracao, cortes_cena)
    if not trechos:
        return None
    cobertura = sum(b - a for a, b in trechos) / max(duracao, 1e-6)
    if cobertura >= DIVIDIDO_TODO:
        trechos = []
    return Dividido(caixas, trechos, round(min(1.0, cobertura), 3), trilhas)


def _trilha_caixa(amostras: list[tuple[float, list[Rosto]]], pessoa: list[Rosto | None], c: Caixa, src_w: int, src_h: int,
                  cortes_cena: list[float] | None, y_rosto: float = 0.42) -> list[tuple[float, float, float, float | None]]:
    """O recorte de uma pessoa da tela dividida acompanhando ela (mesma suavização da câmera de uma pessoa só).

    O zoom fica parado (o tamanho de `c`); o recorte anda no máximo 35% da largura e 25% da altura a partir da
    posição mediana, para não invadir o lado da outra pessoa.
    """
    ts = [t for t, _ in amostras]
    cenas = sorted(cortes_cena or [])
    pulos: list[float | None] = [None] * len(ts)
    ci = 0
    for i, t in enumerate(ts):
        while ci < len(cenas) and cenas[ci] <= t:
            pulos[i] = cenas[ci] if i > 0 else None
            ci += 1
    cx0, cy0 = (c.x + c.w / 2) / src_w, (c.y + y_rosto * c.h) / src_h
    xs = suavizar_caminho(ts, [p.cx if p else None for p in pessoa], pulos, FOLGA * c.w / src_w, padrao=cx0)
    ys = suavizar_caminho(ts, [p.cy if p else None for p in pessoa], pulos, FOLGA * c.h / src_h, padrao=cy0)
    out = []
    for t, cx, cy, p in zip(ts, xs, ys, pulos):
        x = float(np.clip(cx * src_w - c.w / 2, max(0, c.x - 0.35 * c.w), min(src_w - c.w, c.x + 0.35 * c.w)))
        y = float(np.clip(cy * src_h - y_rosto * c.h, max(0, c.y - 0.25 * c.h), min(src_h - c.h, c.y + 0.25 * c.h)))
        out.append((round(t, 3), round(x, 1), round(y, 1), p))
    return out


def tamanho_crop(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[int, int]:
    """Maior crop com a proporção da saída que cabe na fonte."""
    alvo = out_w / out_h
    if src_w / src_h > alvo:
        ch = src_h
        cw = int(round(ch * alvo))
    else:
        cw = src_w
        ch = int(round(cw / alvo))
    return cw - cw % 2, ch - ch % 2


def comandos_sendcmd(traj: list[Ponto], src_w: int, crop_w: int, alvo: str = "crop@cam", fps: float = 30.0) -> str:
    """sendcmd simples (x do crop na fonte, de 2 em 2 px) a cada quadro de saída. O render usa `Movel`, sem degrau."""
    linhas = []
    ultimo = None
    for t, (cx,) in _por_quadro([(t, (cx,), p) for t, cx, p in traj], fps):
        x = int(round(max(0.0, min(src_w - crop_w, cx * src_w - crop_w / 2))))
        x -= x % 2
        if x == ultimo:
            continue
        ultimo = x
        linhas.append(f"{_instante(t, fps)} {alvo} x {x};")
    return "\n".join(linhas) + "\n"


@dataclass
class Movel:
    """Crop que anda sem degrau.

    Cortar direto na fonte só anda de 2 em 2 px da fonte, que viram 3 a 7 px na saída depois de ampliar: a
    panorâmica lenta sai aos trancos (um quadro parado, um pulo). Aqui o recorte parado `e*` cobre todo o caminho
    da câmera, é ampliado `k` vezes e o crop móvel tira a saída dele de 1 em 1 px da saída.
    """

    ex: int
    ey: int
    ew: int
    eh: int
    k: float
    sw: int
    sh: int
    out_w: int
    out_h: int

    def xy(self, x: float, y: float) -> tuple[int, int]:
        """Canto do crop (pixels da fonte) para pixels do recorte ampliado."""
        return (int(min(self.sw - self.out_w, max(0, round((x - self.ex) * self.k)))),
                int(min(self.sh - self.out_h, max(0, round((y - self.ey) * self.k)))))

    def filtro(self, nome: str, x: float, y: float) -> str:
        x0, y0 = self.xy(x, y)
        return (f"crop={self.ew}:{self.eh}:{self.ex}:{self.ey},scale={self.sw}:{self.sh}:flags=bicubic,"
                f"crop@{nome}=w={self.out_w}:h={self.out_h}:x={x0}:y={y0}:exact=1")

    def comandos(self, pontos: list[tuple[float, tuple[float, float], float | None]], nome: str, fps: float) -> str:
        """sendcmd com x e y do crop móvel a cada quadro de saída (só quando mudam)."""
        linhas = []
        ultimo = None
        for t, (x, y) in _por_quadro(pontos, fps):
            xy = self.xy(x, y)
            if xy == ultimo:
                continue
            if ultimo is None or xy[1] == ultimo[1]:
                linhas.append(f"{_instante(t, fps)} crop@{nome} x {xy[0]};")
            else:
                linhas.append(f"{_instante(t, fps)} crop@{nome} x {xy[0]}, crop@{nome} y {xy[1]};")
            ultimo = xy
        return "\n".join(linhas) + "\n"


def movel(xs: list[float], ys: list[float], w: int, h: int, src_w: int, src_h: int, out_w: int, out_h: int) -> Movel:
    """O `Movel` para um crop `w`x`h` cujo canto passa por `xs`, `ys` (pixels da fonte) e sai em `out_w`x`out_h`."""
    def faixa(vs: list[float], tam: int, total: int) -> tuple[int, int]:
        a = max(0, int(np.floor(min(vs))) if vs else 0)
        b = min(total, int(np.ceil(max(vs) + tam)) if vs else tam)
        a -= a % 2
        b = min(total, b + (b - a) % 2)
        return a, max(b - a, min(tam, total))

    ex, ew = faixa(xs, w, src_w)
    ey, eh = faixa(ys, h, src_h)
    k = max(out_w / w, out_h / h)
    sw, sh = int(np.ceil(ew * k)), int(np.ceil(eh * k))
    sw, sh = max(sw + sw % 2, out_w), max(sh + sh % 2, out_h)
    return Movel(ex, ey, ew, eh, k, sw, sh, out_w, out_h)


def cantos_camera(traj: list[Ponto], src_w: int, crop_w: int) -> list[float]:
    """Canto esquerdo do crop (pixels da fonte) em cada ponto da trajetória."""
    return [max(0.0, min(src_w - crop_w, cx * src_w - crop_w / 2)) for _, cx, _ in traj]


def x_inicial(traj: list[Ponto], src_w: int, crop_w: int) -> int:
    cx = traj[0][1] if traj else 0.5
    x = int(round(cx * src_w - crop_w / 2))
    x = max(0, min(src_w - crop_w, x))
    return x - x % 2
