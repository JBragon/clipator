"""Legenda editada à mão depois do render (passo 5)."""

from __future__ import annotations

import pytest

from clipator import legenda_editada as le
from clipator.models import Clip, Origem
from clipator.timeline import Timeline
from clipator.workspace import write_json

from .conftest import precisa_ffmpeg, transcricao_falsa


def _projeto(ws, cortes=None):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(p.transcricao_path, transcricao_falsa())
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=12, titulo="t", formato="9:16", cortes_internos=cortes or []))
    return p


# ---- sem FFmpeg ---------------------------------------------------------------------------------
def test_mesmo_numero_de_palavras_mantem_os_tempos_e_estica_para_o_novo_intervalo():
    f = le.Frase(inicio=1.0, fim=3.0, texto="um DOIS três",
                 palavras=[le.Palavra(texto="um", inicio=1.0, fim=1.4), le.Palavra(texto="dois", inicio=1.5, fim=2.0),
                           le.Palavra(texto="tres", inicio=2.2, fim=3.0)])
    assert [(w["texto"], w["inicio"], w["fim"]) for w in le.palavras_da_frase(f)] == [
        ("um", 1.0, 1.4), ("DOIS", 1.5, 2.0), ("três", 2.2, 3.0)]
    # a frase foi puxada meio segundo para frente e encurtada: as palavras acompanham
    g = f.model_copy(update={"inicio": 0.5, "fim": 1.5})
    ws = le.palavras_da_frase(g)
    assert ws[0]["inicio"] == 0.5 and ws[-1]["fim"] == 1.5 and ws[1]["inicio"] == pytest.approx(0.75)


def test_outro_numero_de_palavras_divide_o_tempo_pelo_tamanho():
    f = le.Frase(inicio=0, fim=2, texto="aa bbbbbb", palavras=[le.Palavra(texto="x", inicio=0, fim=2)])
    ws = le.palavras_da_frase(f)
    assert [w["texto"] for w in ws] == ["aa", "bbbbbb"]
    assert ws[0]["fim"] == pytest.approx(0.5) and ws[1]["fim"] == pytest.approx(2.0)
    assert le.palavras_da_frase(le.Frase(inicio=0, fim=1, texto="   ")) == []


def test_normalizar_ordena_tira_vazias_prende_ao_clip_e_desfaz_sobreposicao():
    leg = le.LegendaEditada(frases=[
        le.Frase(inicio=5, fim=7, texto="  segunda   frase "),
        le.Frase(inicio=0, fim=6, texto="primeira"),
        le.Frase(inicio=8, fim=9, texto=""),
        le.Frase(inicio=9.5, fim=30, texto="última"),
    ])
    out = le.normalizar(leg, 10.0).frases
    assert [f.texto for f in out] == ["primeira", "segunda frase", "última"]
    assert out[0].fim == 5 and out[1].inicio == 5  # a anterior termina quando a próxima começa
    assert out[-1].fim == 10.0


def test_aplicar_troca_so_o_trecho_do_clip_e_volta_ao_tempo_do_original():
    tl = Timeline.de_clip(10, 20, [(12, 14)])  # 8 s de clip; o tempo 2 do clip é o 14 do original
    pals = [{"texto": "antes", "inicio": 5, "fim": 5.5}, {"texto": "velha", "inicio": 10.5, "fim": 11},
            {"texto": "depois", "inicio": 21, "fim": 21.5}]
    leg = le.LegendaEditada(frases=[le.Frase(inicio=0.5, fim=1.0, texto="nova"), le.Frase(inicio=3, fim=4, texto="outra")])
    out = le.aplicar(pals, leg, tl)
    assert [w["texto"] for w in out] == ["antes", "nova", "outra", "depois"]
    assert out[1]["inicio"] == 10.5 and out[2]["inicio"] == 15.0
    # e o render, que volta ao tempo do clip, vê exatamente o que foi editado
    from clipator import subtitles

    clip = subtitles.palavras_do_clip(out, tl)
    assert [(w["texto"], w["inicio"]) for w in clip] == [("nova", 0.5), ("outra", 3.0)]


def test_estado_parte_da_transcricao_e_a_edicao_salva_vale_so_para_o_mesmo_corte(ws):
    p = _projeto(ws, cortes=[(4.0, 5.0)])
    e = le.estado(p, "01-x")
    assert not e["editada"] and not e["desatualizada"] and e["duracao"] == pytest.approx(10.0)
    assert e["frases"] and "dinheiro" in e["frases"][0]["texto"]
    frases = [le.Frase.model_validate(f) for f in e["frases"]]
    frases[0] = frases[0].model_copy(update={"texto": frases[0].texto.replace("dinheiro", "DINHEIRO")})
    le.salvar(p, "01-x", le.LegendaEditada(frases=frases))
    e2 = le.estado(p, "01-x")
    assert e2["editada"] and "DINHEIRO" in e2["frases"][0]["texto"]
    pals = le.palavras_da_transcricao(p)
    clip, _ = p.clip("01-x")
    tl = le.timeline_do_clip(clip)
    novas = le.aplicar_no_render(p, clip, pals, tl)
    assert any(w["texto"].startswith("DINHEIRO") for w in novas)
    assert not any(w["texto"].startswith("dinheiro") and tl.inicio <= w["inicio"] < tl.fim for w in novas)
    # mudou o corte: a edição fica de lado e a tela avisa
    clip.fim = 11
    p.salvar_clip(clip)
    avisos = []
    assert le.aplicar_no_render(p, clip, pals, le.timeline_do_clip(clip), avisos.append) is pals
    assert avisos and "outro trecho" in avisos[0]
    e3 = le.estado(p, "01-x")
    assert not e3["editada"] and e3["desatualizada"]
    assert le.descartar(p, "01-x") and not le.estado(p, "01-x")["desatualizada"]


def test_legenda_vazia_e_recusada(ws):
    p = _projeto(ws)
    with pytest.raises(le.ErroLegenda, match="vazia"):
        le.salvar(p, "01-x", le.LegendaEditada(frases=[le.Frase(inicio=0, fim=1, texto=" ")]))


def test_sem_transcricao_nao_ha_o_que_editar(ws):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=5))
    with pytest.raises(le.ErroLegenda, match="transcrição"):
        le.estado(p, "01-x")


def test_api_salva_descarta_e_pede_o_render(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    p = _projeto(srv.ws)
    base = f"/api/canais/teste/projetos/{p.id}/clips/01-x/legenda"
    e = cl.get(base, headers=h).json()
    frases = e["frases"]
    frases[0]["texto"] = "Texto corrigido"
    e2 = cl.put(base, json={"frases": frases}, headers=h).json()
    assert e2["editada"] and e2["frases"][0]["texto"] == "Texto corrigido"
    assert cl.put(base, json={"frases": []}, headers=h).status_code == 400

    pedidos = []
    srv.fila.registrar("renderizar", lambda params, ctx: pedidos.append(params))
    jid = cl.post(f"{base}/renderizar", json={"frases": frases}, headers=h).json()["job"]
    srv.fila.esperar(jid, 5)
    assert pedidos == [{"canal": "teste", "projeto": p.id, "clips": ["01-x"], "legenda_editada": True}]

    assert cl.delete(base, headers=h).json()["editada"] is False


# ---- com FFmpeg: o vídeo sai de novo com a legenda corrigida ---------------------------------------
@precisa_ffmpeg
def test_gerar_de_novo_usa_a_legenda_editada_e_refaz_o_acabamento(ws, video_teste, monkeypatch):
    from clipator import acabamento, pipeline, transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    c = ws.criar_canal("Teste", palavras_chave=["dinheiro"])
    regras = c.arquivo("regras.md")
    regras.write_text(regras.read_text().replace("duracao_min: 20", "duracao_min: 5").replace("duracao_max: 60", "duracao_max: 12"))
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="podcast-limpo")[0]
    pipeline.renderizar(p, clip.id)
    pasta = p.clips_dir / clip.id
    assert "PALAVRA-TROCADA" not in (pasta / "legenda.srt").read_text(encoding="utf-8")

    # acabamento em uso antes da edição: tem que voltar depois do render novo
    acabamento.aplicar(p, clip.id, acabamento.Acabamento(imagem=acabamento.Imagem(saturacao=0.5)))
    assert p.clip(clip.id)[0].versao.endswith(acabamento.VIDEO)

    e = le.estado(p, clip.id)
    frases = [le.Frase.model_validate(f) for f in e["frases"]]
    frases[0] = frases[0].model_copy(update={"texto": "PALAVRA-TROCADA " + frases[0].texto})
    le.salvar(p, clip.id, le.LegendaEditada(frases=frases))
    logs: list[str] = []
    r = le.renderizar(p, clip.id, log=logs.append)

    assert "PALAVRA-TROCADA" in (pasta / "legenda.srt").read_text(encoding="utf-8")
    assert "PALAVRA-TROCADA" in (pasta / "legenda.ass").read_text(encoding="utf-8")
    assert r["acabamento"] and p.clip(clip.id)[0].versao == r["acabamento"]
    assert any("legenda editada" in x for x in logs) and any("acabamento foi refeito" in x for x in logs)
