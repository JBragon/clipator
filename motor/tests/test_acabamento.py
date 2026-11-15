"""Acabamento do passo 5: música de fundo e ajustes de imagem no clip já gerado."""

from __future__ import annotations

import base64
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from clipator import acabamento as ac
from clipator.models import Clip, Origem

from .conftest import precisa_ffmpeg


def _projeto(ws):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=5, titulo="t", formato="9:16"))
    return p


def _gerar(saida: Path, extra: list[str], dur: float = 4) -> Path:
    saida.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *extra, "-t", str(dur), str(saida)], check=True)
    return saida


def _clip_gerado(ws):
    p = _projeto(ws)
    _, pasta = p.clip("01-x")
    # quadro cinza médio e um tom de "fala"
    _gerar(pasta / "saida.mp4", ["-f", "lavfi", "-i", "color=c=0x808080:size=320x568:rate=25", "-f", "lavfi", "-i",
                                 "sine=frequency=220", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", "-shortest"])
    return p, pasta


def _cor_media(video: Path, t: float = 2.0) -> tuple[int, int, int]:
    bruto = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                            "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return bruto[0], bruto[1], bruto[2]


# ---- sem FFmpeg: os filtros -------------------------------------------------------------
def test_imagem_neutra_nao_gera_filtro_e_ajustes_viram_eq_temperatura_e_nitidez():
    assert ac.filtro_imagem(ac.Imagem(), set()) is None
    vf = ac.filtro_imagem(ac.Imagem(brilho=0.1, saturacao=1.3, temperatura=0.5, nitidez=0.8), {"colortemperature"})
    assert vf.startswith("eq=brightness=0.100:contrast=1.000:saturation=1.300,")
    assert "colortemperature=temperature=5000" in vf and "unsharp=5:5:0.80" in vf and vf.endswith("format=yuv420p")
    # FFmpeg sem colortemperature cai no colorbalance
    antigo = ac.filtro_imagem(ac.Imagem(temperatura=-1), {"eq"})
    assert "colortemperature" not in antigo and "colorbalance=rm=-0.180:bm=0.180" in antigo


def test_audio_com_musica_abaixa_na_fala_e_faz_fade_no_fim():
    f = ac.filtro_audio(ac.Musica(arquivo="m.mp3", volume=0.25, entrada=1, saida=2), 30, True)
    assert "[1:a]atrim=0:30.000" in f and "volume=0.250" in f and "afade=t=out:st=28.000:d=2.00" in f
    assert "sidechaincompress" in f and "[voz][musb]amix" in f and f.endswith("[a]")
    sem_duck = ac.filtro_audio(ac.Musica(arquivo="m.mp3", abaixar_na_fala=False), 30, True)
    assert "sidechaincompress" not in sem_duck and "[voz][mus]amix" in sem_duck
    assert ac.filtro_audio(None, 30, True, 0.5) == "[0:a]volume=0.500[a]"
    assert ac.filtro_audio(ac.Musica(arquivo="m.mp3"), 30, False).endswith("[a]")  # clip sem som: só a música


def test_musica_enviada_fica_no_canal_sem_sobrescrever_e_recusa_caminho_fora(ws, tmp_path):
    p = _projeto(ws)
    with pytest.raises(ac.ErroAcabamento, match="Formato"):
        ac.salvar_musica(p.canal.path, "virus.exe", b"x")
    with pytest.raises(ac.ErroAcabamento, match="vazio"):
        ac.salvar_musica(p.canal.path, "a.mp3", b"")
    with pytest.raises(ac.ErroAcabamento, match="não encontrada"):
        ac.caminho_musica(p.canal.path, "../../canal.md")


def test_clip_sem_saida_nao_tem_acabamento(ws):
    p = _projeto(ws)
    with pytest.raises(ac.ErroAcabamento, match="ainda não foi gerado"):
        ac.estado(p, "01-x")


# ---- com FFmpeg -------------------------------------------------------------------------
@precisa_ffmpeg
def test_acabamento_vira_versao_e_refazer_parte_da_base(ws, tmp_path):
    from clipator import media

    p, pasta = _clip_gerado(ws)
    wav = _gerar(tmp_path / "trilha.wav", ["-f", "lavfi", "-i", "sine=frequency=660"], dur=1.5)
    m = ac.salvar_musica(p.canal.path, "Minha Trilha.wav", wav.read_bytes())
    assert m["arquivo"] == "minha-trilha.wav"
    assert ac.salvar_musica(p.canal.path, "Minha Trilha.wav", wav.read_bytes())["arquivo"] == "minha-trilha-2.wav"
    assert [x["arquivo"] for x in ac.listar_musicas(p.canal.path)] == ["minha-trilha-2.wav", "minha-trilha.wav"]

    e = ac.estado(p, "01-x")
    assert e["base"] == "saida.mp4" and not e["em_uso"] and e["ajustes"]["musica"] is None

    ajustes = ac.Acabamento(musica=ac.Musica(arquivo="minha-trilha.wav", volume=0.5), imagem=ac.Imagem(temperatura=1))
    r = ac.aplicar(p, "01-x", ajustes, agora=datetime(2026, 11, 10, 21, 0, 0))
    assert r["versao"] == "edicoes/20261110-210000-acabamento/saida-acabada.mp4" and r["base"] == "saida.mp4"
    final = pasta / r["versao"]
    info = media.probe(final)
    assert info.tem_audio and info.duracao == pytest.approx(4, abs=0.15)  # música curta repete até o fim
    rr, _, bb = _cor_media(final)
    r0, _, b0 = _cor_media(pasta / "saida.mp4")
    assert rr - bb > 20 and abs(r0 - b0) < 6  # mais quente: puxou para o laranja
    assert "minha-trilha.wav a 50%" in (final.parent / "notas.md").read_text(encoding="utf-8")
    assert p.clip("01-x")[0].versao == r["versao"]

    # a tela reabre com os ajustes em uso e a base original
    e = ac.estado(p, "01-x")
    assert e["em_uso"] and e["base"] == "saida.mp4" and e["ajustes"]["musica"]["volume"] == 0.5

    # refazer só com a imagem: parte do saida.mp4, então a música não fica
    r2 = ac.aplicar(p, "01-x", ac.Acabamento(imagem=ac.Imagem(brilho=0.2)), agora=datetime(2026, 11, 10, 21, 5, 0))
    assert r2["base"] == "saida.mp4" and r2["versao"].startswith("edicoes/20261110-210500-acabamento/")

    # a versão aparece na lista de versões do clip (a mesma das edições com IA)
    from clipator import edicao_ia

    ids = [v["id"] for v in edicao_ia.listar_versoes(p, "01-x")]
    assert ids[:2] == ["20261110-210500-acabamento", "20261110-210000-acabamento"]

    # tudo neutro: volta para o original
    assert ac.aplicar(p, "01-x", ac.Acabamento())["vazio"] and p.clip("01-x")[0].versao is None


@precisa_ffmpeg
def test_acabamento_sobre_versao_editada_pela_ia_mantem_ela_como_base(ws):
    p, pasta = _clip_gerado(ws)
    editada = pasta / "edicoes" / "20261101-100000" / "saida-editada.mp4"
    editada.parent.mkdir(parents=True)
    editada.write_bytes((pasta / "saida.mp4").read_bytes())
    clip, _ = p.clip("01-x")
    clip.versao = "edicoes/20261101-100000/saida-editada.mp4"
    p.salvar_clip(clip)
    r = ac.aplicar(p, "01-x", ac.Acabamento(manter_som_original=0.5))
    assert r["base"] == "edicoes/20261101-100000/saida-editada.mp4"
    assert ac.estado(p, "01-x")["base"] == "edicoes/20261101-100000/saida-editada.mp4"
    assert ac.aplicar(p, "01-x", ac.Acabamento())["versao"] == "edicoes/20261101-100000/saida-editada.mp4"


@precisa_ffmpeg
def test_rotas_do_acabamento(ws, tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    p, _ = _clip_gerado(ws)
    srv = Servico(ws.root)
    enviados = []
    srv.fila.enviar = lambda tipo, dados: enviados.append((tipo, dados)) or "job1"
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    canal = p.canal.slug
    wav = _gerar(tmp_path / "m.wav", ["-f", "lavfi", "-i", "sine=frequency=440"], dur=1)
    dados = "data:audio/wav;base64," + base64.b64encode(wav.read_bytes()).decode()
    assert cl.post(f"/api/canais/{canal}/musicas", json={"nome": "m.wav", "arquivo": dados}, headers=h).json()["arquivo"] == "m.wav"
    assert cl.post(f"/api/canais/{canal}/musicas", json={"nome": "m.txt", "arquivo": dados}, headers=h).status_code == 400
    assert [x["arquivo"] for x in cl.get(f"/api/canais/{canal}/musicas", headers=h).json()] == ["m.wav"]

    base = f"/api/canais/{canal}/projetos/{p.id}/clips/01-x/acabamento"
    e = cl.get(base, headers=h).json()
    assert e["base"] == "saida.mp4" and e["base_caminho"].endswith("clips/01-x/saida.mp4") and e["musicas"][0]["arquivo"] == "m.wav"
    assert cl.post(base, json={"musica": {"arquivo": "nao-existe.mp3"}}, headers=h).status_code == 409 and not enviados
    assert cl.post(base, json={"imagem": {"brilho": 9}}, headers=h).status_code == 422
    assert cl.post(base, json={"musica": {"arquivo": "m.wav", "volume": 0.3}}, headers=h).json() == {"job": "job1"}
    assert enviados[0][0] == "acabamento" and enviados[0][1]["ajustes"]["musica"]["volume"] == 0.3
