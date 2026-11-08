"""Tela dividida: duas pessoas empilhadas, cada uma com zoom no próprio rosto."""

from __future__ import annotations

import types

import pytest

from clipator import media, pipeline, reframe, render
from clipator.models import Estilo

from .conftest import precisa_ffmpeg, transcricao_falsa

R = reframe.Rosto
ABERTO = [R(0.28, 0.40, 0.012), R(0.72, 0.42, 0.010)]  # plano aberto: as duas pessoas
CLOSE = [R(0.50, 0.40, 0.08)]  # close numa pessoa só


def _amostras(plano, inicio=0.0, fim=12.0, por_s=3):
    n = int((fim - inicio) * por_s)
    return [(inicio + i / por_s, list(plano(inicio + i / por_s))) for i in range(n)]


def test_plano_aberto_o_clip_todo_empilha_com_zoom_em_cada_rosto():
    d = reframe.enquadramento_dividido(_amostras(lambda t: ABERTO), 1920, 1080, 1080, 960, 12.0)
    assert d is not None and d.trechos == [] and d.cobertura == 1.0
    cima, baixo = d.caixas
    assert cima.x + cima.w / 2 < 960 < baixo.x + baixo.w / 2  # a pessoa da esquerda fica em cima
    for c, r in ((cima, ABERTO[0]), (baixo, ABERTO[1])):
        assert abs(c.w / c.h - 1080 / 960) < 0.02  # proporção da metade
        assert c.h < 1080 * 0.6  # zoom: bem menor que a fonte inteira
        assert c.x <= r.cx * 1920 <= c.x + c.w and c.y <= r.cy * 1080 <= c.y + c.h  # o rosto dentro
        assert c.x % 2 == c.y % 2 == c.w % 2 == c.h % 2 == 0
    inv = reframe.enquadramento_dividido(_amostras(lambda t: ABERTO), 1920, 1080, 1080, 960, 12.0, em_cima="direita")
    assert inv.caixas == (baixo, cima)


def test_closes_seguem_o_rosto_e_o_plano_aberto_empilha():
    am = _amostras(lambda t: CLOSE if 4 <= t < 8 else ABERTO)
    d = reframe.enquadramento_dividido(am, 1920, 1080, 1080, 960, 12.0, cortes_cena=[4.0, 8.0])
    assert d.trechos == [(0.0, 4.0), (8.0, 12.0)]  # bordas no corte de cena
    assert d.cobertura == pytest.approx(2 / 3, abs=0.01)
    # falha solta do detector (uma amostra) não troca o layout
    am2 = [(t, CLOSE if i == 10 else rs) for i, (t, rs) in enumerate(_amostras(lambda t: ABERTO))]
    assert reframe.enquadramento_dividido(am2, 1920, 1080, 1080, 960, 12.0).trechos == []


def test_sem_as_duas_pessoas_juntas_nao_divide():
    assert reframe.enquadramento_dividido(_amostras(lambda t: CLOSE), 1920, 1080, 1080, 960, 12.0) is None
    assert reframe.enquadramento_dividido([], 1920, 1080, 1080, 960, 12.0) is None
    # caixa repetida no mesmo rosto (o Haar marca rosto e cabeça) é uma pessoa só
    dupla = [R(0.5, 0.4, 0.01), R(0.5, 0.41, 0.09)]
    assert reframe.enquadramento_dividido(_amostras(lambda t: dupla), 1920, 1080, 1080, 960, 12.0) is None


def test_terceiro_rosto_e_caixa_por_fora_nao_estragam_o_zoom():
    ruido = [*ABERTO, R(0.72, 0.42, 0.10), R(0.5, 0.9, 0.003)]
    d = reframe.enquadramento_dividido(_amostras(lambda t: ruido), 1920, 1080, 1080, 960, 12.0)
    limpo = reframe.enquadramento_dividido(_amostras(lambda t: ABERTO), 1920, 1080, 1080, 960, 12.0)
    assert d.caixas == limpo.caixas


def test_cadeia_do_ffmpeg(tmp_path):
    d = reframe.enquadramento_dividido(_amostras(lambda t: ABERTO), 1920, 1080, 1080, 960, 12.0)
    g = render._cadeia_layout(Estilo(), "dividido", 1920, 1080, 1080, 1920, None, 0, d)
    assert "vstack=inputs=2[vlay]" in g and "overlay" not in g
    d.trechos = [(0.0, 4.0), (8.0, 12.0)]
    cmd = tmp_path / "camera.cmd"
    g = render._cadeia_layout(Estilo(), "dividido", 1920, 1080, 1080, 1920, cmd, 100, d)
    assert "sendcmd" in g and "enable='between(t,0.000,4.000)+between(t,8.000,12.000)'[vlay]" in g
    # detector indisponível: vídeo inteiro com fundo desfocado (mostra as duas pessoas de qualquer jeito)
    assert "overlay=(W-w)/2:(H-h)/2[vlay]" in render._cadeia_layout(Estilo(), "dividido", 1920, 1080, 1080, 1920, None, 0, None)


def test_ajustes_do_estilo_no_clip(ws):
    est = Estilo.model_validate({"reenquadramento": "dividido", "dividido": {"em_cima": "direita"}})
    assert est.dividido.em_cima == "direita" and est.dividido.tamanho_rosto == 0.35
    with pytest.raises(Exception):
        Estilo.model_validate({"dividido": {"em_cima": "meio"}})
    est, _, _ = ws.carregar_estilo("podcast-limpo", None, {"reenquadramento": "dividido", "dividido": {"tamanho_rosto": 0.5}})
    assert est.reenquadramento == "dividido" and est.dividido.tamanho_rosto == 0.5


def _render_dividido(ws, video_teste, monkeypatch, plano, nome_detector="mediapipe"):
    from clipator import transcribe

    from .conftest import WhisperFalso
    from .test_integracao import _projeto_com_video

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    monkeypatch.setattr(reframe, "amostrar_rostos", lambda video, tl, cancelar=None, **k: _amostras(plano, 0, tl.duracao))
    monkeypatch.setattr(reframe, "detector", lambda: types.SimpleNamespace(nome=nome_detector))
    c, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="reacao-dividida")[0]
    return clip, pipeline.renderizar(p, clip.id, preview=True)


@precisa_ffmpeg
def test_render_com_closes_no_meio(ws, video_teste, monkeypatch):
    clip, r = _render_dividido(ws, video_teste, monkeypatch, lambda t: CLOSE if 2 <= t < 4 else ABERTO)
    info = media.probe(r.video)
    assert r.layout == "dividido" and (info.largura, info.altura) == (540, 960)
    assert info.duracao == pytest.approx(clip.fim - clip.inicio, abs=0.25)
    assert r.video.with_name("camera.preview.cmd").exists()  # os closes seguem o rosto


@precisa_ffmpeg
def test_render_sem_duas_pessoas_segue_o_rosto_e_avisa(ws, video_teste, monkeypatch):
    _, r = _render_dividido(ws, video_teste, monkeypatch, lambda t: CLOSE)
    assert r.layout == "seguir-rosto" and "duas pessoas" in (r.aviso or "")
