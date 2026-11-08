"""Encoder de vídeo por placa (NVIDIA, AMD, Intel, Mac) com volta para a CPU, e o Whisper sem CUDA."""

from __future__ import annotations

import threading
import types

import pytest

from clipator import media, signals, transcribe


@pytest.fixture
def encoders(monkeypatch):
    """Finge quais encoders a placa tem, sem rodar o FFmpeg."""
    tem: set[str] = set()
    monkeypatch.setattr(media, "_hw_ok", {})
    monkeypatch.setattr(media, "_testar_encoder", lambda nome: nome in tem)
    monkeypatch.delenv("CLIPATOR_ENCODER", raising=False)
    return tem


def test_amd_no_windows_usa_amf(encoders, monkeypatch):
    monkeypatch.setattr(media.sys, "platform", "win32")
    encoders.add("amf")
    assert media.encoder_em_uso() == "amf"
    assert media.video_encode_args()[:2] == ["-c:v", "h264_amf"]


def test_nvidia_tem_preferencia(encoders, monkeypatch):
    monkeypatch.setattr(media.sys, "platform", "win32")
    encoders.update({"nvenc", "amf", "qsv"})
    assert media.encoder_em_uso() == "nvenc"


def test_sem_placa_usa_x264(encoders, monkeypatch):
    monkeypatch.setattr(media.sys, "platform", "linux")
    assert media.encoder_em_uso() == "x264"
    assert media.video_encode_args("preview")[:2] == ["-c:v", "libx264"]


def test_variavel_forca_encoder(encoders, monkeypatch):
    encoders.update({"nvenc", "amf"})
    monkeypatch.setenv("CLIPATOR_ENCODER", "amf")
    assert media.encoder_em_uso() == "amf"
    monkeypatch.setenv("CLIPATOR_ENCODER", "cpu")
    assert media.encoder_em_uso() == "x264"
    monkeypatch.setenv("CLIPATOR_ENCODER", "qsv")  # pedido, mas a placa não tem: CPU
    assert media.encoder_em_uso() == "x264"


def test_troca_por_x264_mantem_o_resto():
    args = ["-i", "a.mp4", *media._HW["amf"]["final"], "-t", "3", "o.mp4"]
    novo = media._trocar_por_x264(args)
    assert novo == ["-i", "a.mp4", *media._X264["final"], "-t", "3", "o.mp4"]
    assert media._trocar_por_x264(["-i", "a.mp4", *media._X264["final"]]) is None


def test_render_refaz_na_cpu_quando_o_encoder_da_placa_falha(monkeypatch):
    chamadas: list[list[str]] = []

    def rodar(cmd, linha, cancelar, sem_saida_s, descricao, stderr):
        chamadas.append(list(cmd))
        if "h264_amf" in cmd:
            stderr.write("[h264_amf @ 0x1] AMF failed to initialise\n")
            return 1
        return 0

    monkeypatch.setattr(media, "rodar_processo", rodar)
    monkeypatch.setattr(media, "_hw_ok", {"amf": True})
    msgs = []
    media.run_ffmpeg(["-i", "a.mp4", *media._HW["amf"]["final"], "o.mp4"], progresso=lambda f, m: msgs.append(m))
    assert len(chamadas) == 2 and "libx264" in chamadas[1]
    assert media._hw_ok["amf"] is False
    assert any("refazendo na CPU" in m for m in msgs)


def test_erro_que_nao_e_do_encoder_nao_repete(monkeypatch):
    chamadas = []

    def rodar(cmd, linha, cancelar, sem_saida_s, descricao, stderr):
        chamadas.append(cmd)
        stderr.write("a.mp4: No such file or directory\n")
        return 1

    monkeypatch.setattr(media, "rodar_processo", rodar)
    with pytest.raises(media.FFmpegError):
        media.run_ffmpeg(["-i", "a.mp4", *media._HW["nvenc"]["final"], "o.mp4"])
    assert len(chamadas) == 1


def test_hwaccel_desligavel(monkeypatch):
    monkeypatch.delenv("CLIPATOR_HWACCEL", raising=False)
    assert media.hwaccel_args() == ["-hwaccel", "auto"]
    monkeypatch.setenv("CLIPATOR_HWACCEL", "0")
    assert media.hwaccel_args() == []


def test_cenas_repete_sem_hwaccel_se_a_placa_recusar(monkeypatch):
    monkeypatch.setattr(media, "probe", lambda v: media.InfoMidia(10, 320, 240, 30, True, True))
    cmds = []

    def rodar(cmd, linha, cancelar, sem_saida_s, descricao):
        cmds.append(cmd)
        if "-hwaccel" in cmd:
            return 1
        linha("[Parsed_showinfo_3 @ 0] n:0 pts:10 pts_time:4.5 ...")
        return 0

    monkeypatch.setattr(media, "rodar_processo", rodar)
    monkeypatch.delenv("CLIPATOR_HWACCEL", raising=False)
    assert signals.cenas("v.mp4") == [4.5]
    assert "-hwaccel" in cmds[0] and "-hwaccel" not in cmds[1]


def test_falha_ao_carregar_na_gpu_cai_para_cpu_sem_travar(monkeypatch, tmp_path):
    """A volta para a CPU chamava carregar_modelo de novo dentro do mesmo Lock: o processo travava."""
    from .conftest import WhisperFalso

    def carregar(nome, dev, compute, pasta=None):
        if dev == "cuda":
            raise RuntimeError("CUDA failed with error out of memory")
        return WhisperFalso()

    monkeypatch.setattr(transcribe, "carregar_modelo", carregar)
    monkeypatch.setattr(transcribe, "_cuda_ok", None)
    resultado = {}
    t = threading.Thread(target=lambda: resultado.update(transcribe.transcrever(tmp_path / "a.wav", "large-v3-turbo", "cuda")))
    t.start()
    t.join(10)
    assert not t.is_alive()
    assert resultado["dispositivo"] == "cpu" and resultado["modelo"] == "small"
    monkeypatch.setattr(transcribe, "_cuda_ok", None)


def test_carregar_modelo_real_nao_trava_e_guarda_um_so(monkeypatch):
    criados = []

    class Falso:
        def __init__(self, modelo, device, compute_type, download_root=None, **kw):
            criados.append((modelo, device, kw))

    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Falso))
    monkeypatch.setattr(transcribe, "_modelos", {})
    transcribe.carregar_modelo("small", "cpu", "int8")
    transcribe.carregar_modelo("small", "cpu", "int8")
    transcribe.carregar_modelo("base", "cpu", "int8")
    assert len(criados) == 2 and list(transcribe._modelos) == [("base", "cpu", "int8")]
    assert criados[0][2]["cpu_threads"] >= 4


def test_threads_cpu(monkeypatch):
    monkeypatch.setenv("CLIPATOR_WHISPER_THREADS", "3")
    assert transcribe.threads_cpu() == 3
    monkeypatch.delenv("CLIPATOR_WHISPER_THREADS")
    monkeypatch.setattr(transcribe.os, "cpu_count", lambda: 16)
    assert transcribe.threads_cpu() == 8
    monkeypatch.setattr(transcribe.os, "cpu_count", lambda: 2)
    assert transcribe.threads_cpu() == 4


def test_carregar_audio_estereo(tmp_path):
    import wave

    import numpy as np

    wav = tmp_path / "e.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.array([16384, 0, -16384, -16384], dtype=np.int16).tobytes())
    x = transcribe.carregar_audio(wav)
    assert x.dtype == np.float32 and x.tolist() == [0.25, -0.5]
