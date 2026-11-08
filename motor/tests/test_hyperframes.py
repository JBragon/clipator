"""Motor HyperFrames: composição (sem o CLI) e queda para o ASS."""

from __future__ import annotations

import pytest

from clipator import hyperframes, pipeline
from clipator.models import Clip, Estilo, Origem
from clipator.timeline import Timeline
from clipator.workspace import write_json

from .conftest import TEXTO, precisa_ffmpeg, transcricao_falsa


def _palavras():
    from clipator.transcribe import palavras

    return palavras(transcricao_falsa(TEXTO.replace("quinhentos", "500"), duracao=13))


def test_compor_tem_frases_numeros_cartela_e_fontes():
    from clipator import markdown as md
    from clipator.workspace import estilos_embutidos_dir

    meta = md.read(estilos_embutidos_dir() / "numeros-na-tela.md").meta
    est = Estilo.model_validate(meta)
    comp = hyperframes.compor(_palavras(), Timeline.de_clip(0.5, 8.5, []), est, 540, 960, "O ERRO que custou 500 mil",
                              usar_cartela=True)
    h = comp.html
    assert 'data-composition-id="clipator"' in h and "data-no-timeline" in h
    assert 'class="clip frase"' in h and 'class="clip numero"' in h and "--alvo:500" in h
    assert 'class="clip cartela"' in h and "O ERRO QUE CUSTOU 500 MIL" in h
    assert "@property --n" in h  # CSS do template numeros-na-tela
    assert "cdn" not in h.lower() and "gsap" not in h.lower()  # offline
    assert any(f.name == "Anton-Regular.ttf" for f in comp.fontes)


def test_template_de_cada_estilo_embutido_existe():
    from clipator import markdown as md
    from clipator.workspace import estilos_embutidos_dir

    for p in estilos_embutidos_dir().glob("*.md"):
        est = Estilo.model_validate({"nome": p.stem, **md.read(p).meta})
        if est.motor == "hyperframes":
            css, _ = hyperframes._css_template(est, p.parent)
            assert css, f"{p.name} sem template HyperFrames"


def test_html_escapa_texto():
    est = Estilo()
    pals = [{"texto": "<script>x</script>", "inicio": 0.1, "fim": 0.5}]
    h = hyperframes.compor(pals, Timeline.de_clip(0, 2, []), est, 540, 960, "a & b", usar_cartela=True).html
    corpo = h[h.index('<div id="root"'):]
    assert "<script>" not in corpo and "&lt;script&gt;" in corpo and "A &amp; B" in corpo


@precisa_ffmpeg
def test_sem_hyperframes_cai_para_ass(ws, video_teste, monkeypatch):
    monkeypatch.setattr(hyperframes, "comando", lambda: None)
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    from clipator import ingest

    ingest.importar_arquivo(video_teste, p)
    write_json(p.transcricao_path, transcricao_falsa(duracao=13))
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=4, titulo="Teste", estilo="texto-grifado", formato="9:16"))
    r = pipeline.renderizar(p, "01-x", preview=True)
    assert r.motor == "ffmpeg" and r.aviso and "HyperFrames" in r.aviso
    assert r.legenda is not None and r.legenda.exists()


@precisa_ffmpeg
@pytest.mark.skipif(hyperframes.comando() is None, reason="HyperFrames não instalado")
def test_render_com_hyperframes(ws, video_teste):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    from clipator import ingest, media

    ingest.importar_arquivo(video_teste, p)
    write_json(p.transcricao_path, transcricao_falsa(duracao=13))
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=4, titulo="Teste", estilo="plantao-urgente", formato="9:16", cartela=True))
    r = pipeline.renderizar(p, "01-x", preview=True)
    assert r.motor == "hyperframes", r.aviso
    assert media.probe(r.video).duracao == pytest.approx(3, abs=0.2)
