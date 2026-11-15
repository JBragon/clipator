"""Checagem de fatos do passo 4: o que a fala cita, o nome conferido e a fonte, e o uso disso na montagem."""

from __future__ import annotations

import json

import pytest

from clipator import checagem as ch
from clipator.models import Clip, Origem
from clipator.transcribe import palavras
from clipator.workspace import write_json

from .conftest import transcricao_falsa

FALA = ("Ontem eu li que o Iliasat Skiver saiu da OpenAI e foi morar no Brasil. Segundo o IBGE, 40% das pessoas ganham "
        "500 mil reais por ano. A Nvidia vale 3 trilhões de dólares. Porque ninguém fala disso?")


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    """Os testes nunca vão à internet: quem quiser o Wikidata passa um `abrir` falso."""
    def recusa(url, timeout):
        raise OSError("sem rede nos testes")

    monkeypatch.setattr("clipator.artes.pesquisa._abrir", recusa)


def _projeto(ws, texto: str = FALA):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    t = transcricao_falsa(texto, 20)
    write_json(p.transcricao_path, t)
    p.salvar_candidatos([{"id": "c1", "inicio": 0, "fim": 30, "duracao": 30, "nota": 80, "texto": texto}])
    return p


class IA:
    nome = "falsa"

    def __init__(self, resposta):
        self.resposta, self.pedidos = resposta, []

    def run_json(self, prompt, schema, cancelar=None):
        self.pedidos.append(prompt)
        return self.resposta


def _wikidata(itens: dict[str, tuple[str, str, str]]):
    """`abrir` falso: busca -> (qid, nome, descrição); o P31 é Q5 (gente) quando a descrição diz 'pessoa'."""
    import urllib.parse

    def abrir(url, timeout):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "search" in q:
            achado = itens.get(q["search"][0])
            return json.dumps({"search": [{"id": achado[0], "label": achado[1], "description": achado[2]}] if achado else []}).encode()
        qid = url.rsplit("/", 1)[-1].removesuffix(".json")
        nome, desc = next((n, d) for i, n, d in itens.values() if i == qid)
        p31 = "Q5" if "pessoa" in desc else "Q4830453"
        return json.dumps({"entities": {qid: {"labels": {"pt": {"value": nome}}, "descriptions": {"pt": {"value": desc}},
                                              "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": p31}}}}]}}}}).encode()

    return abrir


# ---- sem IA nem rede ------------------------------------------------------------------------------------------------
def test_regras_acham_nomes_lugares_siglas_e_numeros_com_a_fonte_citada():
    itens = {i.termo: i for i in ch.por_regras(palavras(transcricao_falsa(FALA, 20)), "c1")}
    assert itens["Brasil"].tipo == "lugar" and itens["Brasil"].fonte.origem == "natural-earth" and itens["Brasil"].fonte.descricao == "País"
    assert {"Iliasat Skiver", "OpenAI", "Nvidia"} <= set(itens) and itens["Iliasat Skiver"].tipo == "outro"
    assert itens["IBGE"].tipo == "organizacao"
    assert itens["40%"].tipo == "dado" and itens["40%"].fonte.titulo == "IBGE" and itens["40%"].fonte.origem == "fala"
    assert "500 mil reais" in itens and "3 trilhões de dólares" in itens
    assert itens["3 trilhões de dólares"].fonte.titulo == ""  # outra frase: o IBGE não vale para ela
    assert "Porque" not in itens and "Ontem" not in itens  # começo de frase não é nome
    assert itens["40%"].ocorrencias[0].candidato == "c1" and "IBGE" in itens["40%"].ocorrencias[0].trecho


def test_aplicar_troca_o_dito_pelo_conferido_mantendo_os_tempos():
    pals = palavras(transcricao_falsa(FALA, 20))
    itens = [ch.Item(id="a", termo="Iliasat Skiver", nome="Ilya Sutskever", status="corrigido"),
             ch.Item(id="b", termo="40%", nome="45%", tipo="dado", status="corrigido")]
    novas, trocas = ch.aplicar_nas_palavras(pals, itens)
    assert " ".join(w["texto"] for w in novas).startswith("Ontem eu li que o Ilya Sutskever saiu") and "45% das" in " ".join(w["texto"] for w in novas)
    assert [t["para"] for t in trocas] == ["Ilya Sutskever", "45%"] and trocas[0]["de"] == "Iliasat Skiver"
    assert len(novas) == len(pals) and [w["inicio"] for w in novas] == [w["inicio"] for w in pals]
    assert pals[5]["texto"] == "Iliasat"  # a lista de entrada não muda
    # número de palavras diferente: o nome divide o tempo do termo, uma palavra por vez, com a pontuação
    so = palavras(transcricao_falsa("Falei com o Skiver, ontem.", 4))
    novas, _ = ch.aplicar_nas_palavras(so, [ch.Item(id="c", termo="Skiver", nome="Ilya Sutskever")])
    assert [w["texto"] for w in novas] == ["Falei", "com", "o", "Ilya", "Sutskever,", "ontem."]
    assert novas[3]["inicio"] == so[3]["inicio"] and novas[4]["fim"] == so[3]["fim"] and novas[3]["fim"] == novas[4]["inicio"]


def test_identificar_sem_ia_e_sem_rede_salva_e_avisa(ws):
    p = _projeto(ws)
    r = ch.identificar(p, ["c1", "nao-existe"])
    assert r.candidatos == ["c1"] and not r.usou_ia and ch.caminho(p).exists()
    assert any("Wikidata" in a for a in r.avisos)
    assert all(i.status == "pendente" for i in r.itens) and ch.carregar(p).itens == r.itens
    with pytest.raises(ch.ErroChecagem):
        ch.identificar(p, ["nao-existe"])


def test_com_ia_e_wikidata_o_nome_e_a_fonte_vem_prontos(ws):
    p = _projeto(ws)
    ia = IA({"itens": [
        {"corte": "c1", "termo": "Iliasat Skiver", "tipo": "pessoa", "nome": "Ilya Sutskever", "fonte_citada": ""},
        {"corte": "c1", "termo": "OpenAI", "tipo": "empresa", "nome": "OpenAI", "fonte_citada": ""},
        {"corte": "c1", "termo": "Elon Musk", "tipo": "pessoa", "nome": "Elon Musk", "fonte_citada": ""},  # não foi dito
        {"corte": "c1", "termo": "40%", "tipo": "dado", "nome": "40%", "fonte_citada": "IBGE"}]})
    abrir = _wikidata({"Ilya Sutskever": ("Q21708200", "Ilya Sutskever", "pessoa, cientista da computação"),
                       "OpenAI": ("Q21708201", "OpenAI", "empresa de pesquisa em IA")})
    r = ch.identificar(p, ["c1"], ia, abrir=abrir)
    it = {i.termo: i for i in r.itens}
    assert r.usou_ia and "Iliasat Skiver" in ia.pedidos[0] and "[corte c1]" in ia.pedidos[0]
    assert it["Iliasat Skiver"].nome == "Ilya Sutskever" and it["Iliasat Skiver"].tipo == "pessoa"
    assert it["Iliasat Skiver"].fonte.url == "https://www.wikidata.org/wiki/Q21708200" and it["Iliasat Skiver"].fonte.origem == "wikidata"
    assert it["OpenAI"].fonte.descricao == "empresa de pesquisa em IA"
    assert "Elon Musk" not in it and it["40%"].fonte.titulo == "IBGE"
    assert "Brasil" in it and "Nvidia" not in it  # o lugar vem das regras; o nome solto que a IA não listou sai


def test_o_que_o_usuario_conferiu_fica_ao_identificar_de_novo(ws):
    p = _projeto(ws)
    r = ch.identificar(p, ["c1"])
    k = next(i.id for i in r.itens if i.termo == "Iliasat Skiver")
    novo = ch.atualizar_item(p, k, nome="Ilya Sutskever", fonte={"titulo": "Wikipédia", "url": "https://pt.wikipedia.org/wiki/Ilya_Sutskever"})
    assert novo.status == "corrigido" and novo.fonte.origem == "usuario" and novo.sugerido_nome == "Iliasat Skiver"
    brasil = next(i.id for i in r.itens if i.termo == "Brasil")
    assert ch.atualizar_item(p, brasil, status="confirmado").status == "confirmado"
    nvidia = next(i.id for i in r.itens if i.termo == "Nvidia")
    assert ch.atualizar_item(p, nvidia, status="ignorado").status == "ignorado"
    with pytest.raises(ch.ErroChecagem):
        ch.atualizar_item(p, k, nome="  ")
    with pytest.raises(ch.ErroChecagem):
        ch.atualizar_item(p, k, fonte={"url": "javascript:alert(1)"})
    r2 = ch.identificar(p, ["c1"])
    it = {i.termo: i for i in r2.itens}
    assert it["Iliasat Skiver"].nome == "Ilya Sutskever" and it["Iliasat Skiver"].status == "corrigido"
    assert it["Nvidia"].status == "ignorado"
    assert ch.resumo(r2)["corrigido"] == 1 and ch.resumo(r2)["confirmado"] == 1
    n = ch.confirmar_pendentes(p)
    assert n == ch.resumo(r2)["pendente"] and ch.resumo(ch.carregar(p))["pendente"] == 0


# ---- na montagem ----------------------------------------------------------------------------------------------------
def test_entidades_e_fontes_do_clip_seguem_a_checagem(ws):
    p = _projeto(ws)
    r = ch.identificar(p, ["c1"])
    k = next(i.id for i in r.itens if i.termo == "Iliasat Skiver")
    ch.atualizar_item(p, k, nome="Ilya Sutskever", tipo="pessoa",
                      fonte={"titulo": "Ilya Sutskever", "url": "https://www.wikidata.org/wiki/Q21708200", "origem": "wikidata", "id": "Q21708200"})
    ch.atualizar_item(p, next(i.id for i in r.itens if i.termo == "IBGE"), status="ignorado")
    pals, _ = ch.aplicar_nas_palavras(palavras(p.transcricao()), ch.revisados(p))
    ents = ch.entidades_do_clip(p, "c1", pals)
    assert ents == [{"termo": "Ilya Sutskever", "tipo": "pessoa", "busca": "Ilya Sutskever", "qid": "Q21708200"}]
    assert ch.entidades_do_clip(p, "outro-corte", pals) is None  # corte não checado: a IA decide como antes
    assert ch.fontes_do_texto(p, FALA) == "Fontes:\n- Ilya Sutskever: Ilya Sutskever (https://www.wikidata.org/wiki/Q21708200)"
    assert ch.fontes_do_texto(p, "outro assunto") == ""


def test_referencias_com_a_lista_conferida_nao_chamam_a_ia(tmp_path, monkeypatch):
    from clipator import referencias as rf

    pedidos = []
    monkeypatch.setattr("clipator.artes.pesquisa.imagens_reais", lambda ents, pasta, cancelar=None: (pedidos.append(ents) or [], []))
    pals = [{"texto": w, "inicio": i * 0.5, "fim": i * 0.5 + 0.4} for i, w in enumerate("o Ilya Sutskever saiu".split())]
    conf = [{"termo": "Ilya Sutskever", "tipo": "pessoa", "busca": "Ilya Sutskever", "qid": "Q21708200"}]
    assert rf.obter(tmp_path, pals, None, conferidas=conf) == []
    assert pedidos == [conf]
    assert rf.obter(tmp_path / "x", pals, None) == []  # sem IA e sem checagem: nada roda
    assert len(pedidos) == 1


def test_wikidata_usa_o_item_escolhido_sem_buscar():
    from clipator.artes import pesquisa

    urls = []

    def abrir(url, timeout):
        urls.append(url)
        return json.dumps({"entities": {"Q1": {"labels": {"pt": {"value": "Fulano"}}, "descriptions": {"pt": {"value": "pessoa"}},
                                               "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}}}}).encode()

    e = pesquisa._entidade("Fulano", "pessoa", abrir, 1, qid="Q1")
    assert e["qid"] == "Q1" and e["nome"] == "Fulano" and not any("wbsearchentities" in u for u in urls)


def test_descricao_da_postagem_leva_as_fontes(ws):
    from clipator import postagem

    p = _projeto(ws)
    r = ch.identificar(p, ["c1"])
    ch.atualizar_item(p, next(i.id for i in r.itens if i.termo == "40%"), status="confirmado")
    p.salvar_clip(Clip(id="01-x", candidato="c1", inicio=0, fim=30, titulo="t", formato="9:16"))
    _, pasta = p.clip("01-x")
    base = postagem._base(p, p.clip("01-x")[0], pasta, FALA)
    assert base["blocos"]["fontes"] == "Fontes:\n- 40%: IBGE"
    assert "Fontes:\n- 40%: IBGE" in postagem._descricao({"titulo": None, "blocos": base["blocos"], "hashtags": []})


def test_rotas_da_checagem(ws):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    p = _projeto(ws)
    srv = Servico(ws.root)
    enviados = []
    srv.fila.enviar = lambda tipo, dados: enviados.append((tipo, dados)) or "job1"
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    base = f"/api/canais/{p.canal.slug}/projetos/{p.id}/checagem"
    assert cl.get(base, headers=h).json()["resumo"]["total"] == 0
    assert cl.post(base, json={"candidatos": []}, headers=h).status_code == 400
    assert cl.post(base, json={"candidatos": ["c1"], "usar_ia": False}, headers=h).json() == {"job": "job1"}
    assert enviados == [("checagem", {"canal": p.canal.slug, "projeto": p.id, "candidatos": ["c1"], "usar_ia": False})]
    # o job, rodado aqui mesmo
    srv._job_checagem(enviados[0][1], type("Ctx", (), {"progresso": lambda *a: None, "cancelar": None, "log": lambda *a: None})())
    e = cl.get(base, headers=h).json()
    item = next(i for i in e["itens"] if i["termo"] == "Nvidia")
    r = cl.put(f"{base}/itens/{item['id']}", json={"nome": "NVIDIA", "fonte": {"titulo": "site da empresa", "url": "https://www.nvidia.com"}}, headers=h)
    assert r.json()["status"] == "corrigido" and r.json()["fonte"]["url"] == "https://www.nvidia.com"
    assert cl.put(f"{base}/itens/xyz", json={"status": "confirmado"}, headers=h).status_code == 400
    assert cl.post(f"{base}/confirmar-pendentes", headers=h).json()["confirmados"] == e["resumo"]["pendente"] - 1
    assert cl.get("/api/checagem/fontes", params={"busca": "Nvidia"}, headers=h).status_code == 502  # sem rede nos testes
