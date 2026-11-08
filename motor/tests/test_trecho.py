"""Tela "Editar duração": aumentar ou diminuir o trecho de um clip no vídeo original."""

from __future__ import annotations

import pytest

from clipator import edicao, trecho
from clipator.models import Clip, Origem
from clipator.timeline import Timeline
from clipator.workspace import write_json

from .conftest import transcricao_falsa


def _projeto(ws, duracao: float = 120.0):
    p = ws.criar_canal("Teste").criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(p.metadados_path, {"midia": {"duracao": duracao}})
    p.salvar_clip(Clip(id="01-x", inicio=20, fim=50, titulo="T", formato="16:9"))
    return p


def _itens(pasta, *tempos):
    doc = edicao.Edicao(itens=[edicao.Item(id=f"i{k}", tipo="zoom", inicio=a, fim=b) for k, (a, b) in enumerate(tempos)])
    edicao.salvar(pasta, doc)


def test_comecar_antes_leva_os_itens_junto_com_a_fala(ws):
    p = _projeto(ws)
    _, pasta = p.clip("01-x")
    _itens(pasta, (2, 3), (28, 29.5))
    r = trecho.ajustar(p, "01-x", 15, 50)  # 5 s a mais de contexto no começo
    assert (r.clip.inicio, r.clip.fim) == (15, 50) and r.clip.status == "selecionado"
    itens = {i.id: (i.inicio, i.fim) for i in edicao.carregar(pasta).itens}
    assert itens == {"i0": (7, 8), "i1": (33, 34.5)}  # continuam no mesmo instante do vídeo original
    assert r.itens_movidos == 2 and r.itens_removidos == 0
    assert p.clip("01-x")[0].inicio == 15


def test_encurtar_tira_o_que_ficou_fora_e_recorta_o_que_ficou_na_borda(ws):
    p = _projeto(ws)
    _, pasta = p.clip("01-x")
    _itens(pasta, (1, 3), (9, 12), (27, 29))
    r = trecho.ajustar(p, "01-x", 30, 45)  # tira 10 s do começo e 5 s do fim
    itens = {i.id: (i.inicio, i.fim) for i in edicao.carregar(pasta).itens}
    assert itens == {"i1": (0, 2)}
    assert r.itens_removidos == 2


def test_arrastar_a_faixa_inteira_mantem_a_duracao(ws):
    p = _projeto(ws)
    r = trecho.ajustar(p, "01-x", 60, 90)
    assert r.clip.fim - r.clip.inicio == 30 and not r.renderizar  # nunca foi gerado: só grava


def test_cortes_internos_continuam_no_lugar_do_original():
    antes = Timeline.de_clip(20, 50, [(30, 32)])
    depois = Timeline.de_clip(10, 50, [(30, 32)])
    it = edicao.Item(tipo="zoom", inicio=11, fim=12)  # 11 s do clip antigo = 33 s do original (depois do corte)
    out, movidos, _ = trecho.remapear_itens([it], antes, depois)
    assert (out[0].inicio, out[0].fim) == (21, 22) and movidos == 1


@pytest.mark.parametrize("ini,fim,msg", [(-1, 30, "começo"), (20, 130, "fim do vídeo"), (20, 20.5, "pelo menos")])
def test_recusa_trecho_fora_do_video_ou_curto_demais(ws, ini, fim, msg):
    p = _projeto(ws)
    with pytest.raises(trecho.TrechoInvalido, match=msg):
        trecho.ajustar(p, "01-x", ini, fim)
    assert p.clip("01-x")[0].inicio == 20


def test_sem_metadados_usa_a_duracao_da_transcricao(ws):
    p = ws.criar_canal("Teste").criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(p.transcricao_path, transcricao_falsa(duracao=36))
    p.salvar_clip(Clip(id="01-x", inicio=2, fim=10))
    assert trecho.duracao_do_video(p) == pytest.approx(transcricao_falsa(duracao=36)["duracao"])
    with pytest.raises(trecho.TrechoInvalido):
        trecho.ajustar(p, "01-x", 2, 300)


def test_rota_salva_e_renderiza_de_novo_o_clip_que_ja_tinha_video(ws):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    p = _projeto(ws)
    _, pasta = p.clip("01-x")
    (pasta / "saida.mp4").write_bytes(b"v")
    c = p.clip("01-x")[0].model_copy(update={"status": "renderizado", "versao": "edicoes/1/video.mp4"})
    p.salvar_clip(c)
    srv = Servico(ws.root)
    enviados: list = []
    srv.fila.enviar = lambda tipo, dados: enviados.append((tipo, dados)) or "job1"
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    url = f"/api/canais/{p.canal.slug}/projetos/{p.id}/clips/01-x/trecho"

    assert cl.put(url, headers=h, json={"inicio": 20, "fim": 500}).status_code == 400 and not enviados
    r = cl.put(url, headers=h, json={"inicio": 12.5, "fim": 55}).json()
    assert r["job"] == "job1" and enviados == [("renderizar", {"canal": p.canal.slug, "projeto": p.id, "clips": ["01-x"], "preview": False})]
    novo = p.clip("01-x")[0]
    assert (novo.inicio, novo.fim, novo.status, novo.versao) == (12.5, 55, "selecionado", None)
    assert cl.put(url.replace("01-x", "99-y"), headers=h, json={"inicio": 1, "fim": 9}).status_code == 404
    srv.fila.fechar()


def test_rota_recusa_enquanto_o_clip_renderiza(ws):
    import threading

    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    p = _projeto(ws)
    srv = Servico(ws.root)
    bloqueio = threading.Event()
    srv.fila.registrar("renderizar", lambda params, ctx: bloqueio.wait(5))
    jid = srv.fila.enviar("renderizar", {"canal": p.canal.slug, "projeto": p.id, "clips": ["01-x"]})
    cl = TestClient(criar_app(srv, token="t"))
    url = f"/api/canais/{p.canal.slug}/projetos/{p.id}/clips/01-x/trecho"
    r = cl.put(url, headers={"x-clipator-token": "t"}, json={"inicio": 10, "fim": 40})
    assert r.status_code == 409
    bloqueio.set()
    srv.fila.esperar(jid, 5)
    srv.fila.fechar()


def test_passo2_muda_o_corte_sugerido_e_o_clip_sai_com_o_trecho_novo(ws):
    from clipator import pipeline

    p = ws.criar_canal("Teste").criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    trans = transcricao_falsa(duracao=36)
    write_json(p.transcricao_path, trans)
    p.salvar_candidatos([{"id": "c01", "inicio": 5.0, "fim": 15.0, "duracao": 10.0, "nota": 70, "texto": "velho",
                          "titulos": ["Título"], "motivos": [], "modo": "curto", "fonte": "local"}])
    c = trecho.ajustar_candidato(p, "c01", 2.0, 20.0)
    assert (c["inicio"], c["fim"], c["duracao"]) == (2.0, 20.0, 18.0)
    assert c["ajuste_usuario"] == {"inicio_sugerido": 5.0, "fim_sugerido": 15.0}
    assert c["texto"] != "velho" and c["nota"] == 70
    trecho.ajustar_candidato(p, "c01", 3.0, 20.0)  # editar de novo guarda a sugestão original da análise
    assert p.candidatos()[0]["ajuste_usuario"]["inicio_sugerido"] == 5.0
    clip = pipeline.selecionar(p, ["c01"], formato="9:16", estilo="podcast-limpo")[0]
    assert (clip.inicio, clip.fim) == (3.0, 20.0)
    with pytest.raises(trecho.TrechoInvalido):
        trecho.ajustar_candidato(p, "c01", 3.0, 3.5)
    with pytest.raises(KeyError):
        trecho.ajustar_candidato(p, "c99", 1, 9)


def test_rota_do_passo2(ws):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    p = _projeto(ws)
    p.salvar_candidatos([{"id": "c01", "inicio": 5.0, "fim": 15.0, "duracao": 10.0, "texto": "x"}])
    srv = Servico(ws.root)
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    url = f"/api/canais/{p.canal.slug}/projetos/{p.id}/candidatos/c01/trecho"
    r = cl.put(url, headers=h, json={"inicio": 4, "fim": 30})
    assert r.status_code == 200 and r.json()["candidato"]["fim"] == 30
    assert cl.put(url, headers=h, json={"inicio": 4, "fim": 999}).status_code == 400
    assert cl.put(url.replace("c01", "c99"), headers=h, json={"inicio": 4, "fim": 30}).status_code == 404
    srv.fila.fechar()
