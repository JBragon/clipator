"""Chamadas ao FFmpeg e ao ffprobe, com progresso e cancelamento.

Partes adaptadas de openshorts/ffmpeg_utils.py (video_encode_args, blurred_backdrop,
_probe_nvenc), MIT License, Copyright (c) 2024 OpenShorts. Ver THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

Progress = Callable[[float, str], None]


class FFmpegError(RuntimeError):
    pass


class Travado(RuntimeError):
    """Um programa externo (FFmpeg, HyperFrames) ficou tempo demais sem dar sinal de vida."""


class Cancelado(Exception):
    """Levantada quando o usuário cancela um job."""


# O `ffmpeg` do Homebrew vem sem libass (sem legendas); o completo é o
# `ffmpeg-full`, que fica fora do PATH. Se ele existir, tem preferência.
_HOMEBREW_FULL = ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin")


# Pacotes "portáteis" do winget (zip) ficam em WinGet\Packages. Quando o winget não consegue
# criar o atalho em WinGet\Links, eles não entram no PATH, nem no registro.
WINGET_EXES = {"Gyan.FFmpeg": "ffmpeg.exe", "DenoLand.Deno": "deno.exe"}


def pastas_winget(local: str) -> list[str]:
    import glob

    base = os.path.join(local, "Microsoft", "WinGet", "Packages")
    achadas: list[str] = []
    for pacote, exe in WINGET_EXES.items():
        for caminho in sorted(glob.glob(os.path.join(base, pacote + "*", "**", exe), recursive=True), reverse=True):
            achadas.append(os.path.dirname(caminho))
            break
    return achadas


def completar_path_windows() -> None:
    """No Windows, o PATH do processo é o de quando o terminal (ou o app) abriu. O que o
    winget instalou depois (FFmpeg, Deno, Node.js) só aparece no registro. Junta os dois."""
    if os.name != "nt":
        return
    extras: list[str] = []
    try:
        import winreg

        for raiz, chave in ((winreg.HKEY_CURRENT_USER, r"Environment"),
                            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(raiz, chave) as k:
                    valor, _ = winreg.QueryValueEx(k, "Path")
                extras += [os.path.expandvars(d) for d in str(valor).split(";")]
            except OSError:
                pass
    except ImportError:  # pragma: no cover
        pass
    local = os.environ.get("LOCALAPPDATA")
    if local:
        extras.append(os.path.join(local, "Microsoft", "WinGet", "Links"))
        extras += pastas_winget(local)
    atual = [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    vistos = {d.lower().rstrip("\\") for d in atual}
    novos = []
    for d in extras:
        chave = d.lower().rstrip("\\")
        if d and chave not in vistos and os.path.isdir(d):
            novos.append(d)
            vistos.add(chave)
    if novos:
        os.environ["PATH"] = os.pathsep.join(atual + novos)
        _FILTROS.clear()


def _binario(nome: str, env: str) -> str:
    if os.environ.get(env):
        return os.environ[env]
    for pasta in _HOMEBREW_FULL:
        p = os.path.join(pasta, nome)
        if os.path.isfile(p):
            return p
    achado = shutil.which(nome)
    if not achado and os.name == "nt":
        completar_path_windows()
        achado = shutil.which(nome)
    return achado or nome


def ffmpeg_disponivel() -> bool:
    b = ffmpeg_bin()
    return os.path.isabs(b) and os.path.isfile(b) or shutil.which(b) is not None


DICA_FFMPEG = ("FFmpeg não encontrado. Rode o instalador do Clipator (install.ps1 ou install.sh) ou instale à mão "
               "(Windows: winget install Gyan.FFmpeg · Mac: brew install ffmpeg-full · Linux: apt install ffmpeg) "
               "e depois feche e abra o app.")


def ffmpeg_bin() -> str:
    return _binario("ffmpeg", "CLIPATOR_FFMPEG")


def ffprobe_bin() -> str:
    return _binario("ffprobe", "CLIPATOR_FFPROBE")


_FILTROS: dict[str, set[str]] = {}


def filtros_ffmpeg() -> set[str]:
    """Nomes dos filtros que o FFmpeg instalado conhece (vazio se não rodar)."""
    b = ffmpeg_bin()
    if b not in _FILTROS:
        try:
            r = subprocess.run([b, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
            nomes = {ln.split()[1] for ln in r.stdout.splitlines() if len(ln.split()) > 2 and ln.startswith(" ")}
        except Exception:
            nomes = set()
        _FILTROS[b] = nomes
    return _FILTROS[b]


DICA_LIBASS = ("Este FFmpeg foi compilado sem libass e não desenha legendas. "
               "Mac: brew install ffmpeg-full · Windows: winget install Gyan.FFmpeg · Linux: apt install ffmpeg")


@dataclass
class InfoMidia:
    duracao: float
    largura: int
    altura: int
    fps: float
    tem_audio: bool
    tem_video: bool

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def probe(path: str | Path) -> InfoMidia:
    cmd = [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120, stdin=subprocess.DEVNULL).stdout
    except FileNotFoundError as exc:
        raise FFmpegError("ffprobe não encontrado. Rode 'clipator doctor'.") from exc
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(f"ffprobe falhou em {path}: {exc.stderr.strip()[-500:]}") from exc
    data = json.loads(out)
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float(data.get("format", {}).get("duration") or (v or a or {}).get("duration") or 0)
    fps = 30.0
    if v:
        rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "30/1"
        try:
            num, den = rate.split("/")
            fps = float(num) / float(den) if float(den) else 30.0
        except (ValueError, ZeroDivisionError):
            fps = 30.0
        if fps <= 0 or fps > 240:
            fps = 30.0
    w, h = (int(v.get("width", 0)), int(v.get("height", 0))) if v else (0, 0)
    rot = 0
    if v:
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot = int((v.get("tags") or {}).get("rotate", rot) or rot)
    if abs(rot) % 180 == 90:
        w, h = h, w
    return InfoMidia(duracao=dur, largura=w, altura=h, fps=fps, tem_audio=a is not None, tem_video=v is not None)


_TIME_RE = re.compile(r"out_time_us=(\d+)")
SEM_SAIDA_FFMPEG = 300.0  # o -progress escreve a cada 0,5 s; 5 min calado é travamento


# ---- processos externos ----------------------------------------------------------
def _criacao_grupo() -> dict:
    """Cada programa externo abre seu próprio grupo de processos, para matar a árvore inteira depois."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def matar_arvore(proc: subprocess.Popen) -> None:
    """Mata o processo e todos os filhos (no Windows, o node do HyperFrames abre outros processos)."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001 - se o taskkill falhar, ainda tenta o kill comum
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass


def rodar_processo(cmd: Sequence[str], linha: Callable[[str], None] | None = None,
                   cancelar: threading.Event | None = None, sem_saida_s: float | None = None,
                   timeout_s: float | None = None, descricao: str = "processo", **popen) -> int:
    """Roda um programa lendo a saída linha a linha, sem depender dela para ver o cancelamento.

    - stdin sempre fechado (o motor do app tem o stdin ligado ao Electron);
    - cancelar e os limites de tempo são conferidos a cada 0,25 s;
    - `sem_saida_s`: se o programa ficar esse tempo sem escrever nada, é considerado travado;
    - ao cancelar ou travar, mata a árvore inteira de processos.
    Devolve o código de saída.
    """
    proc = subprocess.Popen(list(cmd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=popen.pop("stderr", subprocess.STDOUT),
                            text=True, encoding="utf-8", errors="replace", **_criacao_grupo(), **popen)
    fila: queue.Queue = queue.Queue()

    def ler() -> None:
        assert proc.stdout is not None
        for ln in proc.stdout:
            fila.put(ln)
        fila.put(None)

    threading.Thread(target=ler, daemon=True).start()
    inicio = ultimo = time.monotonic()
    acabou_saida = False
    try:
        while True:
            if cancelar is not None and cancelar.is_set():
                matar_arvore(proc)
                raise Cancelado()
            try:
                ln = fila.get(timeout=0.25)
            except queue.Empty:
                ln = ""
            agora = time.monotonic()
            if ln is None:
                acabou_saida = True
            elif ln:
                ultimo = agora
                if linha:
                    linha(ln)
            if acabou_saida and proc.poll() is not None:
                break
            if acabou_saida:
                try:
                    proc.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    pass
                if proc.poll() is not None:
                    break
            if sem_saida_s is not None and agora - ultimo > sem_saida_s:
                matar_arvore(proc)
                raise Travado(f"{descricao} ficou {sem_saida_s:.0f} s sem responder e foi interrompido.")
            if timeout_s is not None and agora - inicio > timeout_s:
                matar_arvore(proc)
                raise Travado(f"{descricao} passou de {timeout_s:.0f} s e foi interrompido.")
    except BaseException:
        matar_arvore(proc)
        raise
    return proc.returncode


def apagar_parcial(p: Path, tentativas: int = 20, espera: float = 0.1) -> None:
    """Apaga um arquivo pela metade. No Windows o processo morto ainda segura o arquivo por um
    instante; se não sair, fica para a próxima vez (nunca troca o erro original por este)."""
    for _ in range(tentativas):
        try:
            p.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(espera)


def substituir(tmp: Path, destino: Path, tentativas: int = 20, espera: float = 0.25) -> None:
    """Troca o arquivo final pelo novo. No Windows, se o vídeo estiver aberto (a prévia do app
    tocando), espera um pouco e avisa com uma mensagem clara em vez de travar."""
    for k in range(tentativas):
        try:
            tmp.replace(destino)
            return
        except PermissionError:
            if k == tentativas - 1:
                apagar_parcial(tmp)
                raise FFmpegError(f"Não consegui trocar {destino.name}: o arquivo está aberto em outro programa "
                                  "(feche a prévia do vídeo e renderize de novo).") from None
            time.sleep(espera)


def run_ffmpeg(
    args: Sequence[str],
    duracao: float | None = None,
    progresso: Progress | None = None,
    cancelar: threading.Event | None = None,
    descricao: str = "ffmpeg",
) -> None:
    """Roda o FFmpeg lendo o progresso de -progress pipe:1 (por rodar_processo: cancelar mata na hora).

    O stderr vai para um arquivo temporário para não travar o pipe.
    """
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1", *args]
    stderr_chunks: list[str] = []
    erros = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")

    def ao_ler(line: str) -> None:
        m = _TIME_RE.match(line.strip())
        if m and duracao and progresso:
            frac = min(1.0, int(m.group(1)) / 1e6 / max(duracao, 1e-3))
            progresso(frac, descricao)

    try:
        try:
            codigo = rodar_processo(cmd, ao_ler, cancelar, sem_saida_s=SEM_SAIDA_FFMPEG, descricao=descricao, stderr=erros)
        except FileNotFoundError as exc:
            raise FFmpegError(DICA_FFMPEG) from exc
        erros.seek(0)
        stderr_chunks.append(erros.read()[-4000:])
    finally:
        erros.close()
    if codigo != 0:
        tail = "".join(stderr_chunks)[-1500:]
        if "No such filter: 'subtitles'" in tail or "No such filter: 'ass'" in tail:
            raise FFmpegError(DICA_LIBASS)
        alternativa = _trocar_por_x264(args)
        enc = _encoder_de(args)
        if alternativa is not None and enc and (enc in tail or "encoder" in tail.lower()):
            # O encoder de hardware passou no teste mas falhou aqui (sessões simultâneas esgotadas, driver
            # reiniciado, resolução que a placa não aceita): refaz no x264 e não usa mais a placa nesta sessão.
            with _lock:
                _hw_ok[next((k for k, v in _HW.items() if v["final"][1] == enc), enc)] = False
            if progresso:
                progresso(0.0, f"{descricao}: o encoder da placa de vídeo falhou, refazendo na CPU")
            run_ffmpeg(alternativa, duracao, progresso, cancelar, descricao)
            return
        raise FFmpegError(f"{descricao} falhou (código {codigo}): {tail.strip()}")
    if progresso:
        progresso(1.0, descricao)


def extrair_audio(video: str | Path, wav: str | Path, **kw) -> Path:
    """WAV 16 kHz mono, o formato que o Whisper e a análise de áudio usam."""
    wav = Path(wav)
    wav.parent.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    if not info.tem_audio:
        raise FFmpegError("O vídeo não tem trilha de áudio")
    tmp = wav.with_name(wav.stem + ".tmp.wav")
    run_ffmpeg(["-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)],
               duracao=info.duracao, descricao="extrair áudio", **kw)
    os.replace(tmp, wav)
    return wav


# ---- encoder --------------------------------------------------------------
_X264 = {
    "final": ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    "preview": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
}
# Encoders de hardware, na ordem em que o modo "auto" tenta. Cada um é testado uma vez com os mesmos
# parâmetros do render (um parâmetro que a placa não aceita reprova o encoder no teste, não no render).
_FIM = ["-movflags", "+faststart"]
_HW: dict[str, dict[str, list[str]]] = {
    # NVIDIA (GeForce GTX 600 em diante)
    "nvenc": {
        "final": ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-pix_fmt", "yuv420p", *_FIM],
        "preview": ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr", "-cq", "30", "-b:v", "0", "-pix_fmt", "yuv420p", *_FIM],
    },
    # AMD Radeon (VCE/VCN), pelo AMF do driver Adrenalin
    "amf": {
        "final": ["-c:v", "h264_amf", "-usage", "transcoding", "-quality", "quality", "-rc", "cqp",
                  "-qp_i", "20", "-qp_p", "22", "-qp_b", "24", "-pix_fmt", "yuv420p", *_FIM],
        "preview": ["-c:v", "h264_amf", "-usage", "transcoding", "-quality", "speed", "-rc", "cqp",
                    "-qp_i", "28", "-qp_p", "30", "-qp_b", "32", "-pix_fmt", "yuv420p", *_FIM],
    },
    # Intel Quick Sync (integrada ou Arc); o QSV pede nv12, que também é 4:2:0
    "qsv": {
        "final": ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "22", "-pix_fmt", "nv12", *_FIM],
        "preview": ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "30", "-pix_fmt", "nv12", *_FIM],
    },
    # Mac (Apple Silicon e Intel com T2)
    "videotoolbox": {
        "final": ["-c:v", "h264_videotoolbox", "-b:v", "10M", "-maxrate", "16M", "-bufsize", "20M", "-pix_fmt", "yuv420p", *_FIM],
        "preview": ["-c:v", "h264_videotoolbox", "-b:v", "4M", "-pix_fmt", "yuv420p", *_FIM],
    },
}
_ORDEM_HW = {"win32": ("nvenc", "amf", "qsv"), "darwin": ("videotoolbox",), "linux": ("nvenc", "qsv")}
_hw_ok: dict[str, bool] = {}
_lock = threading.Lock()


def _testar_encoder(nome: str) -> bool:
    """Codifica 3 quadros com os parâmetros do render final. Falha de driver, placa sem o encoder ou
    parâmetro recusado: o encoder fica de fora nesta sessão."""
    with _lock:
        if nome not in _hw_ok:
            cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=320x240:r=30:d=0.1",
                   "-frames:v", "3", *[a for a in _HW[nome]["final"] if a not in _FIM], "-f", "null", "-"]
            try:
                _hw_ok[nome] = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                              timeout=30, **_sem_janela()).returncode == 0
            except Exception:
                _hw_ok[nome] = False
        return _hw_ok[nome]


def _sem_janela() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def nvenc_disponivel() -> bool:
    return _testar_encoder("nvenc")


def encoder_em_uso() -> str:
    """'nvenc', 'amf', 'qsv', 'videotoolbox' ou 'x264'. CLIPATOR_ENCODER força um (ou 'x264'/'cpu')."""
    modo = os.environ.get("CLIPATOR_ENCODER", "auto").strip().lower()
    if modo in ("x264", "cpu", "libx264", "software"):
        return "x264"
    candidatos = (modo,) if modo in _HW else _ORDEM_HW.get(sys.platform, ("nvenc", "qsv"))
    for nome in candidatos:
        if _testar_encoder(nome):
            return nome
    return "x264"


def video_encode_args(nivel: str = "final") -> list[str]:
    enc = encoder_em_uso()
    return list(_HW[enc][nivel] if enc in _HW else _X264[nivel])


def hwaccel_args() -> list[str]:
    """Decodificação pela placa de vídeo para leituras longas (análise de cenas). O "auto" escolhe o que
    houver (CUDA, D3D11VA/DXVA2 no Windows com AMD, NVIDIA ou Intel, VAAPI no Linux, VideoToolbox no Mac)
    e o próprio FFmpeg volta para a CPU se a placa não decodificar o codec. CLIPATOR_HWACCEL=0 desliga."""
    if os.environ.get("CLIPATOR_HWACCEL", "auto").strip().lower() in ("0", "nao", "não", "off", "cpu", "none"):
        return []
    return ["-hwaccel", "auto"]


def _encoder_de(args: Sequence[str]) -> str | None:
    """O codec de vídeo de hardware em `args` (ex.: 'h264_amf'), ou None."""
    a = list(args)
    hw = {v["final"][1] for v in _HW.values()}
    for i, x in enumerate(a[:-1]):
        if x == "-c:v" and a[i + 1] in hw:
            return a[i + 1]
    return None


def _trocar_por_x264(args: Sequence[str]) -> list[str] | None:
    """Se `args` usa um encoder de hardware, devolve os mesmos args com o x264 no lugar (senão None)."""
    a = list(args)
    for enc in _HW.values():
        for nivel, trecho in enc.items():
            n = len(trecho)
            for i in range(len(a) - n + 1):
                if a[i:i + n] == trecho:
                    return a[:i] + _X264[nivel] + a[i + n:]
    return None


# O loudnorm guarda 3 s de áudio (a 192 kHz) antes de soltar o primeiro quadro e devolve esses 3 s com os
# carimbos de tempo embolados: no .mp4 os pacotes de AAC do começo ficam com duração de 1 amostra e depois
# vem um buraco de ~2 s. O player do Clipator e o TikTok tocam os pacotes em sequência e soa normal, mas o
# YouTube e o Facebook respeitam os carimbos: o áudio acelera, fica mudo e volta. Por isso voltamos a 48 kHz e
# refazemos os carimbos pela contagem de amostras (o loudnorm não perde nem cria amostras, então a sincronia fica).
LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,asetpts=N/SR/TB"


def blurred_backdrop(out_w: int, out_h: int, sigma: float = 40) -> str:
    """Fundo desfocado barato: borra em 1/4 do tamanho e amplia."""
    small_w = max(2, out_w // 4 - (out_w // 4) % 2)
    small_h = max(2, out_h // 4 - (out_h // 4) % 2)
    return (
        f"scale={small_w}:{small_h}:force_original_aspect_ratio=increase,"
        f"crop={small_w}:{small_h},gblur=sigma={sigma / 4:g},scale={out_w}:{out_h}"
    )


def escape_filter_path(path: str | Path) -> str:
    """Escapa um caminho para usar dentro de um filtro (ex.: subtitles=...)."""
    s = str(Path(path).resolve()).replace("\\", "/")
    for ch in (":", "'", "[", "]", ",", ";"):
        s = s.replace(ch, "\\" + ch)
    return s


def extrair_quadro(video: str | Path, t: float, saida: str | Path, largura: int = 1280) -> Path:
    saida = Path(saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={largura}:-2", "-q:v", "3", str(saida)],
               descricao="extrair quadro")
    return saida
