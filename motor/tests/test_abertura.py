"""Abertura com ganchos em preto e branco (abertura.py) e a legenda com palavra destacada maior."""

from __future__ import annotations

import re

import numpy as np
import pytest

from clipator import abertura, media, pipeline, subtitles
from clipator.models import Abertura, Legenda
from clipator.timeline import Timeline
from clipator.transcribe import palavras as _palavras

from .conftest import precisa_ffmpeg, transcricao_falsa


def _pals(duracao: float = 36.0) -> list[dict]:
    return _palavras(transcricao_falsa(duracao=duracao))


def test_escolhe_ganchos_fora_do_comeco_e_em_ordem():
    pals = _pals()
    cfg = Abertura(ativa=True, duracao=6, max_trechos=2)
    gs = abertura.escolher(pals, 36.0, cfg)
    assert 1 <= len(gs) <= 2
    assert all(g.inicio >= 36.0 * cfg.inicio_minimo - abertura.PAD_ANTES for g in gs)
    assert [g.inicio for g in gs] == sorted(g.inicio for g in gs)
    total = sum(g.fim - g.inicio for g in gs)
    assert total <= cfg.duracao * 1.35 + 2 * (abertura.PAD_ANTES + abertura.PAD_DEPOIS) + cfg.max_trecho
    for a, b in zip(gs, gs[1:]):  # não se sobrepõem
        assert b.inicio >= a.fim


def test_energia_pesa_na_escolha():
    pals = _pals()
    cfg = Abertura(ativa=True, duracao=3, max_trechos=1)
    alvo = abertura.escolher(pals, 36.0, cfg)[-1].inicio + 8  # um trecho que a fala sozinha não escolheria
    alvo = min(alvo, 30.0)

    def energia(a: float, b: float) -> float:
        return 3.0 if a <= alvo <= b + 2 else -1.0

    g = abertura.escolher(pals, 36.0, cfg, energia)[0]
    assert g.inicio - 2 <= alvo <= g.fim + 2


def test_corte_curto_ou_sem_fala_fica_sem_abertura():
    cfg = Abertura(ativa=True, duracao=6)
    assert abertura.escolher([], 40.0, cfg) == []
    assert abertura.escolher(_pals(), 8.0, cfg) == []


def test_trechos_manuais_vao_para_o_tempo_do_clip():
    tl = Timeline.de_clip(10.0, 40.0, [(15.0, 16.0)])
    gs = abertura.manuais(Abertura(ativa=True, trechos=[(30.0, 33.0), (5.0, 9.0)]), tl)
    assert len(gs) == 1  # o segundo está fora do clip
    assert gs[0].inicio == pytest.approx(19.0) and gs[0].fim == pytest.approx(22.0)


def test_legenda_oculta_inclui_os_ganchos_na_frente():
    pals = [{"texto": "a", "inicio": 1.0, "fim": 1.2}, {"texto": "b", "inicio": 5.0, "fim": 5.3}]
    fin = abertura.palavras_finais(pals, [abertura.Gancho(4.9, 5.5, "b", 1.0)])
    assert [w["texto"] for w in fin] == ["b", "a", "b"]
    assert fin[0]["inicio"] == pytest.approx(0.1)
    assert fin[1]["inicio"] == pytest.approx(0.6 + 1.0)


def test_palavra_destacada_sai_maior(tmp_path):
    pals = [{"texto": "Argentina", "inicio": 0.2, "fim": 0.6}, {"texto": "hoje", "inicio": 0.7, "fim": 1.0}]
    leg = Legenda(modo="uma-palavra", animacao="pop", palavras_destaque=["argentina"], escala_destaque=1.3)
    ass = subtitles.gerar_ass(pals, Timeline.de_clip(0, 2), leg, 1080, 1920, tmp_path / "l.ass").read_text(encoding="utf-8")
    linhas = [ln for ln in ass.splitlines() if ln.startswith("Dialogue")]
    assert "fscx114" in linhas[0] and "fscx143" in linhas[0]  # 88 e 110 vezes 1,3
    assert "fscx114" not in linhas[1]


def test_palavras_chave_sem_ia():
    pals = _palavras(transcricao_falsa(repetir=2))
    chave = subtitles.palavras_chave(subtitles.palavras_do_clip(pals, Timeline.de_clip(0, 80)))
    assert chave and all(re.compile(c) for c in chave)
    assert any(c.lower().startswith("dinheiro") for c in chave)


@precisa_ffmpeg
def test_render_com_abertura_em_preto_e_branco(ws, video_teste, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=12)))
    c = ws.criar_canal("Teste", palavras_chave=["dinheiro"])
    md = c.arquivo("regras.md")
    md.write_text(md.read_text().replace("duracao_min: 40", "duracao_min: 5").replace("duracao_max: 180", "duracao_max: 13"))
    from clipator.models import Origem

    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    (c.path / "estilos").mkdir(exist_ok=True)
    (c.path / "estilos" / "gancho-teste.md").write_text(
        "---\nnome: gancho teste\nreenquadramento: centro\nlegenda:\n  modo: uma-palavra\n"
        "abertura:\n  ativa: true\n  duracao: 2\n  max_trechos: 1\n  max_trecho: 2.5\n  inicio_minimo: 0.2\n  som: whoosh\n---\n",
        encoding="utf-8")
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="gancho-teste")[0]
    clip.inicio, clip.fim = 0.5, 13.0
    p.salvar_clip(clip)
    r = pipeline.renderizar(p, clip.id, preview=True)
    pasta = p.clips_dir / clip.id
    meta = (pasta / "abertura.preview.json")
    assert meta.exists(), r.aviso
    import json

    dados = json.loads(meta.read_text(encoding="utf-8"))
    dur_ab = dados["duracao"]
    assert 1.0 <= dur_ab <= 4.0
    info = media.probe(r.video)
    assert info.tem_audio and info.duracao == pytest.approx(12.5 + dur_ab, abs=0.3)
    # o gancho sai sem cor e o corte, depois do clarão, com cor (o testsrc2 é colorido)
    q1 = media.extrair_quadro(r.video, dur_ab / 2, pasta / "q1.jpg", 320)
    q2 = media.extrair_quadro(r.video, dur_ab + 2.0, pasta / "q2.jpg", 320)
    from PIL import Image

    def sat(pth):
        a = np.asarray(Image.open(pth).convert("RGB")).astype(int)
        return float((a.max(axis=2) - a.min(axis=2)).mean())

    assert sat(q1) < 8 < sat(q2)


@precisa_ffmpeg
def test_loudnorm_nao_embola_os_carimbos_do_audio(tmp_path):
    """O loudnorm devolvia os 3 s iniciais com carimbos embolados (pacotes de 1 amostra e depois um buraco).
    O player local tocava normal, mas YouTube e Facebook aceleravam, emudeciam e voltavam nesse trecho."""
    import subprocess

    saida = tmp_path / "ln.mp4"
    # como no render: trechos emendados pelo concat e depois o loudnorm
    media.run_ffmpeg(["-f", "lavfi", "-t", "4", "-i", "sine=f=440:r=48000",
                      "-f", "lavfi", "-t", "4", "-i", "sine=f=330:r=48000",
                      "-filter_complex", f"[0:a][1:a]concat=n=2:v=0:a=1[c];[c]asetpts=PTS-STARTPTS,{media.LOUDNORM}[a]",
                      "-map", "[a]", "-c:a", "aac", "-ar", "48000", str(saida)])
    pts = [int(x.strip(",")) for x in subprocess.run(
        [media.ffprobe_bin(), "-v", "error", "-select_streams", "a", "-show_entries", "packet=pts",
         "-of", "csv=p=0", str(saida)], capture_output=True, text=True, check=True).stdout.split()]
    passos = {b - a for a, b in zip(pts, pts[1:])}
    assert passos == {1024}
