"""Direção de vídeo: a conferência sem IA, a rodada de correção e a trava de IA em todo estilo animado."""

from __future__ import annotations

import pytest

from clipator import direcao_video as dv
from clipator.models import Estilo

FALA = ("A Maria abriu uma padaria no centro da cidade. No primeiro mês vendeu 300 pães por dia. "
        "Depois o João, que era vizinho, abriu outra padaria do lado. As vendas da Maria caíram pela metade.")


def _pals():
    pals, t = [], 0.2
    for w in FALA.split():
        pals.append({"texto": w, "inicio": round(t, 2), "fim": round(t + 0.35, 2)})
        t += 0.45
    return pals, round(t + 0.3, 2)


def _pessoa(i, pos, acao="falar", olha=""):
    return {"id": i, "posicao": pos, "acao": acao, "olha_para": olha}


def _plano(ancora, cen="c1", em_cena=(), plano="medio", transicao="corte", dado="", balao=""):
    return {"ancora": ancora, "ate": "", "etiqueta": "x", "o_que_mostra": "o que se vê", "cenario": cen, "em_cena": list(em_cena),
            "plano": plano, "movimento": "fixo", "transicao": transicao, "dado": dado, "balao": balao}


def _direcao(planos, elenco=None, cenarios=None):
    return {"historia": {"assunto": "padaria", "metafora": "duas vitrines", "logline": "Maria perde clientes para o vizinho",
                         "comeco": "abre", "meio": "concorrência", "fim": "queda"},
            "elenco": elenco if elenco is not None else [
                {"id": "p1", "papel": "dona da padaria", "tipo": "pessoa", "nome": "Maria", "visual": "avental azul"},
                {"id": "p2", "papel": "vizinho", "tipo": "pessoa", "nome": "Carlos", "visual": "boné vermelho"}],
            "cenarios": cenarios if cenarios is not None else [
                {"id": "c1", "lugar": "loja", "descricao": "padaria"}, {"id": "c2", "lugar": "cidade", "descricao": "rua"}],
            "planos": planos}


def test_direcao_boa_passa_sem_problemas_e_vira_roteiro():
    pals, dur = _pals()
    r = _direcao([_plano("A Maria abriu uma padaria", em_cena=[_pessoa("p1", "centro", "comemorar", "camera")]),
                  _plano("No primeiro mês vendeu 300", em_cena=[_pessoa("p1", "esquerda", "andar")], dado="300"),
                  _plano("Depois o João, que era", cen="c2", em_cena=[_pessoa("p1", "esquerda", "parado", "p2"),
                                                                     _pessoa("p2", "direita", "falar", "p1")], transicao="fade"),
                  _plano("As vendas da Maria caíram", em_cena=[_pessoa("p1", "centro", "triste")], plano="close")])
    d, probs = dv.conferir(r, pals, dur)
    assert dv.criticos(probs) == []
    assert [p["inicio"] for p in d["planos"]][0] == 0.0 and d["planos"][-1]["fim"] == dur
    assert all(a["fim"] == b["inicio"] for a, b in zip(d["planos"], d["planos"][1:]))
    assert d["elenco"][0]["nome"] == "Maria" and d["elenco"][1]["nome"] == ""  # "Carlos" não foi dito
    assert d["planos"][1]["dado"] == "300"
    rot = dv.roteiro(d)
    assert len(rot) == 4 and "Cenário: loja" in rot[0]["descricao"] and "Maria (avental azul)" in rot[0]["descricao"]
    assert rot[2]["direcao"]["em_cena"][1]["posicao"] == "direita"
    t = dv.texto(d)
    assert "Maria perde clientes" in t and "p2 = vizinho" in t


def test_conferencia_acha_os_erros_de_continuidade():
    pals, dur = _pals()
    r = _direcao([
        _plano("A Maria abriu uma padaria", em_cena=[_pessoa("p1", "esquerda"), _pessoa("p2", "esquerda", olha="p9")]),
        _plano("frase que ninguém disse no vídeo"),
        _plano("No primeiro mês vendeu 300", em_cena=[_pessoa("p1", "direita", "parado"), _pessoa("p3", "centro")], dado="999"),
        _plano("Depois o João, que era", cen="c9"),
    ])
    d, probs = dv.conferir(r, pals, dur)
    txt = "\n".join(probs)
    assert "mesma posição (esquerda)" in txt
    assert "olha para “p9”" in txt
    assert "não está na fala" in txt
    assert "“p3” está em cena mas não está no elenco" in txt
    assert "pula de esquerda para direita sem andar" in txt
    assert "cenário “c9” não foi declarado" in txt
    assert d["planos"][1]["dado"] == ""  # 999 não foi dito: sai sozinho, sem precisar da IA
    assert len(d["planos"]) == 3


def test_ancora_fora_de_ordem_e_resposta_invalida():
    pals, dur = _pals()
    d, probs = dv.conferir(_direcao([_plano("As vendas da Maria caíram"), _plano("A Maria abriu uma padaria")]), pals, dur)
    assert any("fora da ordem" in p for p in probs) and len(d["planos"]) == 1
    d, probs = dv.conferir("isso não é json", pals, dur)
    assert d["planos"] == [] and probs


def test_dirigir_pede_a_correcao_uma_vez_e_fica_com_a_melhor():
    pals, dur = _pals()
    ruim = _direcao([_plano("A Maria abriu uma padaria", em_cena=[_pessoa("p1", "centro"), _pessoa("p2", "centro")])])
    boa = _direcao([_plano("A Maria abriu uma padaria", em_cena=[_pessoa("p1", "esquerda"), _pessoa("p2", "direita")]),
                    _plano("As vendas da Maria caíram", em_cena=[_pessoa("p1", "centro", "triste")], plano="close")])
    pedidos, linhas = [], []

    def chamar(ad, prompt, schema, cache, cancelar, ev):
        pedidos.append(prompt)
        assert set(schema["required"]) == {"historia", "elenco", "cenarios", "planos"}
        return ruim if len(pedidos) == 1 else boa

    d = dv.dirigir(None, pals, dur, "A padaria", {"tema": "concorrência", "ideias": []}, "Estilo de teste", chamar, passo=linhas.append)
    assert len(pedidos) == 2 and "mesma posição (centro)" in pedidos[1] and "Direção anterior" in pedidos[1]
    assert len(d["planos"]) == 2 and dv.criticos(d["rodadas"][1]["problemas"]) == []
    assert any("pedindo a correção" in x for x in linhas) and any("história:" in x for x in linhas)
    # sem problema nenhum, não há segunda chamada
    pedidos.clear()
    dv.dirigir(None, pals, dur, "A padaria", None, "Estilo", lambda *a: (pedidos.append(a[1]), boa)[1])
    assert len(pedidos) == 1


def test_todo_estilo_animado_exige_ia(ws):
    assert Estilo(direcao={"layout": "em-cima", "modo": "arte", "arte": "geo-em-cena"}).requer_ia
    assert Estilo(motor="hyperframes", template="numeros-na-tela").requer_ia
    assert Estilo(motor="hyperframes", template="iceberg").requer_ia
    assert not Estilo(motor="hyperframes", template="marca-texto").requer_ia and not Estilo().requer_ia
    animados = [n for n in ws.estilos(None) if ws.carregar_estilo(n)[0].animado]
    assert len(animados) >= 40
    assert all(ws.carregar_estilo(n)[0].requer_ia for n in animados)
    assert not ws.carregar_estilo("podcast-limpo")[0].requer_ia


def test_sem_ia_o_editor_nao_propoe_animacao(ws):
    from clipator import edicao
    from clipator.models import Clip, Origem
    from clipator.timeline import Timeline

    c = ws.criar_canal("Trava")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    pr.salvar_clip(Clip(id="01-x", inicio=0, fim=12, titulo="A padaria", estilo="arte-encaixe-vivo"))
    clip, _ = pr.clip("01-x")
    pals, _ = _pals()
    cenas, aviso = edicao.cenas_sugeridas(pr, clip, Timeline.de_clip(0, 12), pals, None)
    assert cenas == [] and "usam IA" in aviso


@pytest.mark.parametrize("estilo", ["arte-geo-em-cena", "arte-mapa-de-ideias", "desenho-caderno", "numeros-na-tela"])
def test_sem_ia_o_render_recusa_o_estilo_animado(ws, estilo, monkeypatch):
    from clipator import melhorar, render
    from clipator.models import Clip, Origem

    monkeypatch.setattr(melhorar, "ia_do_workspace", lambda ws, esperar_login=None: None)
    c = ws.criar_canal("Trava render")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    pr.salvar_clip(Clip(id="01-x", inicio=0, fim=12, titulo="A padaria", estilo=estilo))
    clip, _ = pr.clip("01-x")
    est = ws.carregar_estilo(estilo)[0]
    with pytest.raises(melhorar.SemIA):
        render.renderizar_clip(pr, clip, est, True)
