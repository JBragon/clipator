"""Imagens reais do que a fala cita, em qualquer estilo (referencias.py)."""

from types import SimpleNamespace

from clipator import referencias as rf


def fala(texto: str, passo: float = 0.5) -> list[dict]:
    return [{"texto": w, "inicio": round(i * passo, 3), "fim": round(i * passo + passo * 0.9, 3)} for i, w in enumerate(texto.split())]


def test_so_entra_nome_dito_e_com_tipo_valido():
    pals = fala("o Iliasat Skiver saiu da OpenAI e a gente ficou sem saber")
    r = rf.de_resposta({"entidades": [{"termo": "Iliasat Skiver", "tipo": "pessoa", "busca": "Ilya Sutskever"},
                                      {"termo": "Anthropic", "tipo": "empresa", "busca": "Anthropic"},
                                      {"termo": "a gente", "tipo": "pessoa", "busca": "x"},
                                      {"termo": "OpenAI", "tipo": "lugar", "busca": "OpenAI"}]}, pals)
    assert r == [{"termo": "Iliasat Skiver", "tipo": "pessoa", "busca": "Ilya Sutskever"}]
    assert rf._tempo("Iliasat Skiver", pals) == 0.5 and rf._tempo("Anthropic", pals) is None
    assert "Ilya Sutskever" in rf.prompt(pals, "T") and rf.schema()["required"] == ["entidades"]


def test_janelas_seguram_o_cartao_e_o_proximo_nome_encurta_o_anterior():
    j = rf.janelas([{"t": 1.0}, {"t": 2.5}, {"t": 2.6}, {"t": 30}], 10)
    assert [(x["t0"], x["t1"]) for x in j] == [(0.85, 2.25), (2.35, 3.55), (3.65, 3.65 + rf.REFERENCIA)]  # o terceiro espera o segundo


def test_cartao_espera_a_cartela_de_titulo_sair():
    # react real: Tabata dita em 1.36 s e Janones em 4.54 s com o título no ar até 3 s; o cartão cobria o título
    j = rf.janelas([{"t": 1.36}, {"t": 4.54}, {"t": 0.5}], 20, livre_desde=3.0)
    assert [(x["t"], x["t0"]) for x in j] == [(0.5, 3.1), (1.36, 4.4), (4.54, 5.7)]  # na fila, depois do título
    assert rf.janelas([{"t": 0.5}], 20, livre_desde=6.0) == []  # o nome passou faz tempo demais: fica de fora
    assert rf.janelas([{"t": 1.36}], 20)[0]["t0"] == 1.21  # sem cartela, entra no nome


def test_visual_combina_com_o_estilo_e_o_cartao_fica_no_painel_ou_longe_da_legenda():
    sem = SimpleNamespace(ativa=False, layout="", arte=None, ficha=None)
    assert rf.visual_do_estilo(SimpleNamespace(direcao=sem), "dossie-investigativo") == "dossie"
    assert rf.visual_do_estilo(SimpleNamespace(direcao=sem), "gamer") == "hud"
    arte = SimpleNamespace(ativa=True, layout="em-cima", arte="revista-de-bancada", ficha="x", proporcao=0.5)
    assert rf.visual_do_estilo(SimpleNamespace(direcao=arte), "arte-revista-de-bancada") == "recorte"
    assert rf.visual_do_estilo(SimpleNamespace(direcao=sem), "qualquer-um") == "limpo"
    x, y, w, h, painel = rf.area(SimpleNamespace(direcao=arte), 1080, 1920)
    assert painel and y + h <= 1920 * 0.5
    leg = SimpleNamespace(altura_relativa=0.7, posicao="baixo")
    x, y, w, h, painel = rf.area(SimpleNamespace(direcao=sem, legenda=leg), 1080, 1920)
    assert not painel and y + h < 1920 * 0.7


def test_documento_tem_imagem_nome_contexto_e_credito(tmp_path):
    (tmp_path / "pesquisa" / "imagens").mkdir(parents=True)
    (tmp_path / "pesquisa" / "imagens" / "0123456789abcdef.png").write_bytes(b"\x89PNG\r\n\x1a\nxx")
    refs = rf.preparar([{"arquivo": "pesquisa/imagens/0123456789abcdef.png", "termo": "Nvidia", "nome": "Nvidia", "contexto": "fabricante de chips",
                         "logo": True, "credito": {"autor": "Fulano"}, "t0": 1, "t1": 3.6}], tmp_path, tmp_path / "camada")
    assert refs[0]["src"].startswith("midias/") and (tmp_path / "camada" / refs[0]["src"]).is_file()
    doc = rf.documento(refs, "dossie", 1080, 1920, 10, (54, 192, 500, 690, False), "#FFD400", "Anton")
    assert 'class="clip ref v-dossie logo"' in doc and 'data-start="1.000"' in doc and "fabricante de chips" in doc and "imagem: Fulano" in doc
