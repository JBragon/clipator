"""Modo curta: cada frase vira um plano com lugar, gente, ação, situação e montagem; a pesquisa de referências é opcional."""

from __future__ import annotations

import io
import json
import re

import pytest

from clipator import artes
from clipator.artes import cortes, curta, pesquisa

SLUGS = list(cortes.ACOES)


def fala(texto: str, passo: float = 0.4) -> list[dict]:
    return [{"texto": w, "inicio": round(i * passo, 3), "fim": round(i * passo + passo * 0.9, 3)} for i, w in enumerate(texto.split())]


def plano(texto: str, slug: str = "pixel-em-cena") -> list[dict]:
    pals = fala(texto)
    return [c["params"]["curta"] for c in artes.planejar_regras(slug, pals, pals[-1]["fim"] + 0.5, "x")]


HISTORIA = ("Eu acordei de madrugada e fui pra cozinha. Abri a geladeira e não tinha nada. Aí tive uma ideia. "
            "Fui correndo pro mercado comprar pão. Chegando lá, estava chovendo muito. Paguei dez reais e voltei pra casa feliz.")


def test_cada_frase_vira_um_plano_e_o_lugar_muda_com_a_fala():
    ps = plano(HISTORIA)
    assert [p["cenario"] for p in ps] == ["cozinha", "cozinha", "cozinha", "loja", "cidade", "casa"]
    assert ps[0]["momento"] == "noite" and all(p["momento"] == "noite" for p in ps)  # "madrugada" vale até a fala mudar
    assert ps[4]["clima"] == "chuva"  # chovendo na loja (interior): o plano corta para fora, onde a chuva aparece
    assert ps[2]["situacao"] == "ideia" and ps[5]["situacao"] == "dinheiro"
    assert ps[3]["personagens"][0]["acao"] == "correr"  # "fui correndo": correr vence andar
    assert ps[5]["personagens"][0]["acao"] == "comemorar"


def test_montagem_abre_lugar_novo_com_plano_geral_e_varia_o_plano_no_mesmo_lugar():
    ps = plano(HISTORIA)
    assert ps[0]["plano"] == "geral" and ps[0]["transicao"] == "fade"
    assert ps[1]["transicao"] == ps[2]["transicao"] == "corte"
    assert ps[1]["plano"] != ps[2]["plano"] and "geral" not in (ps[1]["plano"], ps[2]["plano"])
    assert ps[3]["plano"] == "geral" and ps[3]["transicao"] in ("fade", "cortina", "zoom")
    assert {p["transicao"] for p in ps[3:]} - {"corte"}, "troca de lugar tem transição"


def test_rotulo_do_lugar_e_so_a_palavra_dita_e_verbo_nao_vira_rotulo():
    ps = plano("Eu acordei cedo. Depois fui pra escola.")
    assert [p["cenario"] for p in ps] == ["quarto", "escola"]  # "acordei" sugere o quarto
    assert ps[0]["lugar"] == "" and ps[1]["lugar"] == "escola"
    ps = plano("Isso mudou tudo pra mim. Depois fui pra escola.")
    assert [p["cenario"] for p in ps] == ["escola", "escola"]  # o curta abre no primeiro lugar citado
    ps = plano("Ontem eu dormi muito.")
    assert ps[0]["cenario"] == "quarto" and ps[0]["lugar"] == ""  # "dormi" sugere o quarto, mas não é o nome dele


def test_pronome_nao_vira_nome_na_tela_e_conversa_tem_duas_pessoas():
    p = plano("O chefe chamou ela pra uma reunião.")[0]
    assert p["cenario"] == "escritorio"
    assert p["situacao"] == "conversa" and len(p["personagens"]) == 2
    assert p["personagens"][0]["nome"] == "chefe" and p["personagens"][1]["nome"] == ""
    assert plano("Eu fui andando.")[0]["personagens"][0]["nome"] == ""


def test_frase_sem_lugar_segura_o_lugar_anterior_e_sem_lugar_nenhum_fica_o_palco_do_estilo():
    ps = plano("A gente chegou na praia. Ficou ali o dia inteiro.")
    assert [p["cenario"] for p in ps] == ["praia", "praia"]
    assert plano("Isso é muito importante.")[0]["cenario"] == "palco_vazio"


@pytest.mark.parametrize("slug", SLUGS)
def test_as_cinco_direcoes_guiadas_pela_fala_ganham_o_curta(slug):
    cs = artes.planejar_regras(slug, fala(HISTORIA), 20.0, "x")
    assert cs and all("curta" in c["params"] for c in cs)
    assert all(c["params"]["corte"]["acao"] in cortes.ACOES[slug] for c in cs)  # o corte de antes continua


def test_geo_em_cena_nao_ganha_curta():
    cs = artes.planejar_regras("geo-em-cena", fala("Agora olhe para o Japão."), 4.0, "x")
    assert cs and all("curta" not in c["params"] for c in cs)


def test_normalizar_recusa_valor_fora_das_listas():
    n = curta.normalizar({"cenario": "<script>", "plano": "macro", "situacao": "x", "personagens": [{"nome": "a" * 99, "acao": "voar"}] * 5,
                          "tons": ["#123456", "red", "#zzzzzz"], "aderecos": ["pessoa", "mesa", "nada"]})
    assert n["cenario"] == "" and n["plano"] == "" and n["situacao"] == "nenhuma"
    assert len(n["personagens"]) == curta.MAX_PERSONAGENS and n["personagens"][0]["acao"] == "parado" and len(n["personagens"][0]["nome"]) <= 30
    assert n["tons"] == ["#123456"] and n["aderecos"] == ["mesa"]


def test_resposta_da_ia_interpreta_o_lugar_mas_o_texto_na_tela_e_so_o_dito():
    pals = fala("Fui comprar pão bem cedinho.")
    r = curta.de_resposta({"cenario": "loja", "lugar": "padaria", "momento": "manha", "clima": "", "personagens": [{"nome": "padeiro", "acao": "andar"}],
                           "situacao": "nenhuma", "plano": "geral", "movimento": "aproximar", "transicao": "fade", "aderecos": ["caixa"],
                           "nota_visual": "fachada da padaria de manhã"}, pals)
    assert r["cenario"] == "loja" and r["momento"] == "manha"  # interpretação aceita
    assert r["lugar"] == "" and r["personagens"][0]["nome"] == ""  # "padaria" e "padeiro" não foram ditos
    assert curta.de_resposta("lixo", pals)["cenario"] == "loja"  # sem resposta aproveitável, valem as regras ("comprar")


def test_schema_e_pedido_da_ia_levam_o_curta_e_a_fala_inteira():
    sc = artes.schema_arte("encaixe-vivo")["properties"]["cenas"]["items"]
    assert "curta" in sc["required"] and sc["properties"]["curta"]["properties"]["cenario"]["enum"] == curta.listas()["cenario"]
    roteiro = [{"inicio": 0.0, "fim": 2.0, "ancora": "Fui pra praia", "etiqueta": "", "descricao": "", "dado": ""}]
    p = artes.prompt_arte("encaixe-vivo", roteiro, "", "Fui pra praia com a minha avó.")
    assert "curta-metragem" in p and "Fala inteira do corte: Fui pra praia com a minha avó." in p


def test_de_resposta_ia_monta_o_curta_e_completa_o_que_a_ia_deixou_vazio():
    pals = fala("Cheguei no estádio lotado. O time fez o gol.")
    roteiro = [{"inicio": 0.0, "fim": 1.9, "ancora": "Cheguei no estádio lotado.", "descricao": ""},
               {"inicio": 1.9, "fim": 4.0, "ancora": "O time fez o gol.", "descricao": ""}]
    resp = {"cenas": [{"indice": 0, "texto": "", "itens": [], "nota": "", "dado": "", "peca": "", "acao": "montar", "alvo": "", "conjunto": "", "objetos": [],
                       "curta": {"cenario": "estadio", "lugar": "estádio", "momento": "", "clima": "", "personagens": [], "situacao": "multidao",
                                 "plano": "", "movimento": "", "transicao": "", "aderecos": [], "nota_visual": ""}}]}
    cs = artes.de_resposta_ia("encaixe-vivo", resp, roteiro, pals, "x")
    assert [c["params"]["curta"]["cenario"] for c in cs] == ["estadio", "estadio"]
    assert cs[0]["params"]["curta"]["lugar"] == "estádio" and cs[0]["params"]["curta"]["plano"] == "geral"
    assert cs[1]["params"]["curta"]["situacao"] == "sucesso" and cs[1]["params"]["curta"]["plano"] != "geral"


def test_cena_antiga_sem_curta_segue_no_motor_de_um_mundo_so():
    cs = artes.planejar_regras("encaixe-vivo", fala("A base sustenta o foguete."), 3.0, "x")
    assert curta.ativo(cs)
    for c in cs:
        c["params"].pop("curta")
    assert not curta.ativo(cs)
    assert all("curta" not in artes.normalizar_arte(c["params"]) for c in cs)


def test_plano_para_o_motor_tira_o_lugar_da_lista_de_objetos_e_marca_o_tempo_do_lugar():
    pals = fala("Minha mãe trabalhava numa fábrica com uma esteira.")
    cs = artes.planejar_regras("fluxo-facetado", pals, 4.0, "x")
    for c in cs:
        c["palavras"] = pals
    p = curta.plano(cs)[0]
    assert p["cenario"] == "fabrica" and p["lugar"] == "fábrica"
    assert "fábrica" not in [o["nome"] for o in p["objetos"]]
    assert p["lugar_t"] == pals[4]["inicio"]


def test_motor_tem_desenho_para_cada_valor_das_listas():
    js = (artes._dados("curta") / "curta.js").read_text(encoding="utf-8")
    bloco = js[js.index("const CEN = {"):js.index("// ---- personagens")]
    for c in curta.listas()["cenario"]:
        assert re.search(rf"\n    {c}\(g, a, R\)", bloco), c
    for a in curta.listas()["acao"]:
        assert a == "parado" or f"'{a}'" in js, a
    for s in curta.listas()["situacao"]:
        assert s == "nenhuma" or f"'{s}'" in js, s
    for t in curta.listas()["transicao"]:
        assert f"'{t}'" in js, t
    assert "fetch(" not in js and "XMLHttpRequest" not in js and "http" not in js.replace("http://www.w3.org", "")  # sem rede no render


def test_aplicar_tons_so_na_cena_que_cita_o_termo():
    cs = artes.planejar_regras("terreno-vivo", fala("Fomos pros Lençóis Maranhenses. Depois voltamos pra casa."), 6.0, "x")
    curta.aplicar_tons(cs, {"Lençóis Maranhenses": {"tons": ["#F2EFE6", "#3FA7C9", "#E0B04A"]}})
    assert cs[0]["params"]["curta"]["tons"] == ["#F2EFE6", "#3FA7C9", "#E0B04A"]
    assert cs[-1]["params"]["curta"]["tons"] == []


# ---- pesquisa de referências -------------------------------------------------------------------------------------
def test_termos_sao_nomes_proprios_e_lugares_ditos():
    ts = pesquisa.termos(fala("Ano passado eu fui pros Lençóis Maranhenses com a minha família. Depois a gente foi pra praia em São Luís."))
    assert ts[:2] == ["Lençóis Maranhenses", "São Luís"] and "praia" in ts
    assert "Ano" not in ts and "Depois" not in ts


def _png(rgb: tuple[int, int, int]) -> bytes:
    from PIL import Image

    im = Image.new("RGB", (60, 40), rgb)
    for x in range(60):
        for y in range(28, 40):
            im.putpixel((x, y), (40, 120, 200))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


class Rede:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.urls.append(url)
        if "wikipedia.org" in url:
            return json.dumps({"type": "standard", "extract": "Parque nacional com <b>dunas</b> brancas e lagoas.", "description": "parque",
                               "content_urls": {"desktop": {"page": "https://pt.wikipedia.org/wiki/X"}}}).encode()
        if "commons.wikimedia.org" in url:
            info = lambda n, lic: {"index": n, "title": f"File:{n}.jpg", "imageinfo": [{"thumburl": f"https://upload.wikimedia.org/{n}.jpg",  # noqa: E731
                                   "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{n}.jpg", "extmetadata": {
                                       "LicenseShortName": {"value": lic}, "Artist": {"value": "<a>Fulana</a>"}, "ImageDescription": {"value": "Dunas e lagoa"}}}]}
            return json.dumps({"query": {"pages": {"1": info(1, "CC BY-SA 4.0"), "2": info(2, "Fair use"), "3": info(3, "Public domain")}}}).encode()
        if url.startswith("https://upload.wikimedia.org/"):
            return _png((236, 230, 214))
        raise OSError("sem rede")


def test_pesquisa_le_resumo_e_tons_so_de_imagem_livre_e_guarda_em_cache(tmp_path):
    rede = Rede()
    res, avisos = pesquisa.pesquisar(["Lençóis Maranhenses"], tmp_path, abrir=rede)
    r = res["Lençóis Maranhenses"]
    assert not avisos and "dunas brancas" in r["resumo"] and "<b>" not in r["resumo"]
    assert [i["licenca"] for i in r["imagens"]] == ["CC BY-SA 4.0", "Public domain"] and r["imagens"][0]["autor"] == "Fulana"
    assert not any("2.jpg" in u for u in rede.urls), "imagem sem licença livre nem é baixada"
    assert 1 <= len(r["tons"]) <= 3 and all(re.fullmatch(r"#[0-9A-F]{6}", t) for t in r["tons"])
    n = len(rede.urls)
    res2, _ = pesquisa.pesquisar(["Lençóis Maranhenses"], tmp_path, abrir=rede)
    assert res2 == res and len(rede.urls) == n, "a segunda vez sai do cache, sem rede"
    txt = pesquisa.texto_para_ia(res)
    assert "Não escreva nada disto na tela" in txt and "Dunas e lagoa" in txt
    assert {c["fonte"] for c in pesquisa.creditos(res)} == {"Wikipédia", "Wikimedia Commons"}


def test_sem_rede_a_pesquisa_vira_aviso_e_o_curta_segue(tmp_path):
    def sem_rede(url: str, timeout: float) -> bytes:
        raise OSError("sem rede")

    res, avisos = pesquisa.pesquisar(["São Paulo", "praia"], tmp_path, abrir=sem_rede)
    assert res == {} and avisos and "2 de 2" in avisos[0]
    assert pesquisa.texto_para_ia(res) == ""


def test_pesquisa_pode_ser_desligada(monkeypatch):
    monkeypatch.setenv("CLIPATOR_PESQUISA", "0")
    assert not pesquisa.ligada()
    monkeypatch.delenv("CLIPATOR_PESQUISA")
    assert pesquisa.ligada()


# ---- roteiro fechado do curta (a IA escreve o curta inteiro; o Clipator confere) ---------------------------------------
TEMPERATURA = ("A temperatura do modelo controla o quanto ele arrisca. Com temperatura baixa ele repete a receita. "
               "Com temperatura alta ele inventa pratos novos e às vezes erra feio.")


def _resposta() -> dict:
    return {"assunto": "temperatura do modelo", "metafora": "um robô cozinheiro e o fogo do fogão",
            "logline": "o robô cozinha com fogo baixo, aumenta o fogo e se arrisca",
            "elenco": [{"id": "p1", "papel": "cozinheiro", "tipo": "robo", "nome": "Joca"},
                       {"id": "p2", "papel": "cliente", "tipo": "pessoa", "nome": ""}],
            "planos": [
                {"ancora": "A temperatura do modelo controla", "ate": "", "descricao": "o robô diante do fogão", "cenario": "cozinha",
                 "momento": "", "clima": "", "elenco": [{"id": "p1", "acao": "trabalhar"}, {"id": "zz", "acao": "andar"}],
                 "situacao": "ideia", "plano": "medio", "movimento": "fixo", "transicao": "corte",
                 "objetos": [{"forma": "bloco", "rotulo": "temperatura"}, {"forma": "bloco", "rotulo": "pizza"}], "placa": "ele"},
                {"ancora": "Com temperatura alta ele inventa", "ate": "", "descricao": "o fogo sobe e o cliente estranha",
                 "cenario": "restaurante", "momento": "", "clima": "", "elenco": [{"id": "p1", "acao": "comemorar"}, {"id": "p2", "acao": "pensar"}],
                 "situacao": "duvida", "plano": "close", "movimento": "aproximar", "transicao": "fade", "objetos": [],
                 "placa": "pratos novos"}]}


def test_schema_do_roteiro_pede_metafora_elenco_e_planos_das_listas():
    s = curta.schema_roteiro()
    assert s["required"] == ["assunto", "metafora", "logline", "elenco", "planos", "entidades"]
    p = s["properties"]["planos"]["items"]["properties"]
    assert p["cenario"]["enum"] == curta.listas()["cenario"] and "pessoa" not in p["objetos"]["items"]["properties"]["forma"]["enum"]
    assert s["properties"]["elenco"]["items"]["properties"]["tipo"]["enum"] == ["pessoa", "robo"]


def test_prompt_do_roteiro_explica_estilo_cenarios_metodo_e_traz_a_fala():
    pals = fala(TEMPERATURA)
    p = curta.prompt_roteiro("rota-em-foco", pals, 12, "Temperatura", {"tema": "IA", "ideias": ["arriscar"]}, extra="MÉTODO DO ROTEIRO", refs="REFS")
    for trecho in ("maquete de papel", "## Cenários", "- cozinha", "## Ações", "## Situações", "## Planos de câmera", "## Transições",
                   "## Objetos", "MÉTODO DO ROTEIRO", "REFS", "metafora", "[0.0]A", "Temperatura", "IA"):
        assert trecho in p, trecho


def test_de_roteiro_prende_os_planos_na_fala_e_tira_o_que_nao_foi_dito():
    pals = fala(TEMPERATURA)
    planos, resumo = curta.de_roteiro(_resposta(), pals, pals[-1]["fim"] + 0.3)
    assert len(planos) == 2 and planos[0]["inicio"] == 0 and abs(planos[1]["inicio"] - pals[16]["inicio"]) < 0.3
    a, b = planos[0]["curta"], planos[1]["curta"]
    assert a["roteiro"] and a["cenario"] == "cozinha" and b["cenario"] == "restaurante"
    assert a["personagens"] == [{"nome": "", "acao": "trabalhar", "ator": 0, "tipo": "robo"}]  # id desconhecido sai; "Joca" não foi dito
    assert [p["ator"] for p in b["personagens"]] == [0, 1] and b["personagens"][1]["tipo"] == "pessoa"
    assert [o["rotulo"] for o in a["objetos"]] == ["temperatura", ""]  # "pizza" não foi dita: o objeto fica, sem rótulo
    assert a["placa"] == "" and b["placa"] == "pratos novos"  # pronome nunca vira placa
    assert a["nota_visual"] == "o robô diante do fogão"
    assert resumo["metafora"].startswith("um robô") and [e["tipo"] for e in resumo["elenco"]] == ["robo", "pessoa"]


def test_cenas_do_curta_viram_planos_do_curta_js_sem_o_lexico():
    pals = fala(TEMPERATURA)
    planos, _ = curta.de_roteiro(_resposta(), pals, pals[-1]["fim"] + 0.3)
    cenas = artes.cenas_do_curta("encaixe-vivo", planos, pals)
    assert [c["params"]["cena"] for c in cenas] == ["arte", "arte"] and cenas[0]["params"]["ancora"].startswith("A temperatura")
    for c in cenas:
        c["palavras"] = [{**w, "inicio": w["inicio"] - c["inicio"]} for w in pals if c["inicio"] <= w["inicio"] < c["fim"]]
    ps = curta.plano(cenas)
    assert ps[0]["roteiro"] and [o["nome"] for o in ps[0]["objetos"]] == ["temperatura", ""] and ps[0]["nomes"] == []
    assert ps[1]["placa"] == "pratos novos" and ps[1]["placa_t"] == pytest.approx(pals[21]["inicio"])
    js = (curta._dados("curta") / "curta.js").read_text(encoding="utf-8")
    assert "s.roteiro" in js and "p.ator" in js and "'robo'" in js and "placa_t" in js


def test_palavras_de_quem_fala_nunca_viram_rotulo():
    for x in ("A gente", "eu", "VOCÊ", "isso aí", "ele"):
        assert curta._vazio_na_tela(x), x
    assert not curta._vazio_na_tela("São Paulo")
    n = curta.normalizar({"lugar": "a gente", "personagens": [{"nome": "Eu", "acao": "falar"}], "placa": "você",
                          "objetos": [{"forma": "bloco", "rotulo": "nós"}]})
    assert n["lugar"] == "" and n["personagens"][0]["nome"] == "" and n["placa"] == "" and n["objetos"][0]["rotulo"] == ""


def test_pesquisa_ignora_palavra_maiuscula_so_por_comecar_a_frase():
    pals = fala("Porque a gente foi pra São Paulo. Eles disseram que sim. Posso falar do Google? O Google ajuda. Lençóis Maranhenses é lindo.")
    assert pesquisa.termos(pals)[:3] == ["São Paulo", "Google", "Lençóis Maranhenses"]
    assert not {"Porque", "Eles", "Posso"} & set(pesquisa.termos(pals))


def test_skill_de_roteiro_vai_so_para_o_curta(ws):
    from clipator import skills

    com = skills.texto_para_ia(ws, "cenas")
    sem = skills.texto_para_ia(ws, "cenas", excluir={"roteiro-do-curta"})
    assert "metáfora" in com.lower() and len(sem) < len(com)


# ---- montagem: vídeo em tela cheia entre as ilustrações, destaques e zoom ------------------------------------------
def _cena_plano(t0: float, t1: float, pals: list[dict], **cu) -> dict:
    base = {"cenario": "cozinha", "situacao": "nenhuma", "roteiro": True}
    return {"inicio": t0, "fim": t1, "palavras": [{**w, "inicio": w["inicio"] - t0} for w in pals if t0 <= w["inicio"] < t1],
            "params": {"cena": "arte", "curta": curta.normalizar({**base, **cu})}}


def test_montagem_abre_no_video_alterna_telas_e_absorve_trecho_curto():
    pals = fala("um dois três quatro cinco seis sete oito nove dez " * 4, 0.5)
    cenas = [_cena_plano(0, 6, pals, tela="dividida"), _cena_plano(6, 10, pals, tela="video"),
             _cena_plano(10, 10.6, pals, tela="dividida"), _cena_plano(10.6, 14, pals, tela="video"), _cena_plano(14, 20, pals, tela="dividida")]
    m = curta.montagem(cenas, 20)
    assert [(s["t0"], s["t1"], s["tela"]) for s in m["trechos"]] == [
        (0, curta.GANCHO, "video"), (curta.GANCHO, 6, "dividida"), (6, 14, "video"), (14, 20, "dividida")]
    assert m["zooms"] == [{"t0": 6, "t1": 14, "escala": curta.ZOOM_VIDEO}]  # um trecho de vídeo sim, outro não
    assert m["destaques"] == []


def test_destaque_e_o_numero_dito_e_so_entra_quando_e_dito():
    pals = fala("o Brasil produz 40% da produção global de soja e isso é muito", 0.5)
    cenas = [_cena_plano(0, 7, pals, roteiro=False)]
    assert curta.numero_dito(cenas[0]["palavras"]) == ("40%", "da produção global")  # "de" solto no fim sai
    m = curta.montagem(cenas, 7)
    d = m["destaques"][0]
    assert d["texto"] == "40%" and d["t0"] == pytest.approx(1.5 - 0.08) and d["t1"] - d["t0"] == pytest.approx(curta.DESTAQUE[1])
    # no roteiro da IA, destaque que não foi dito no trecho sai
    resp = _resposta()
    resp["planos"][1].update(destaque="pratos novos", destaque_sub="Joca", tela="video")
    resp["planos"][0].update(destaque="99%", destaque_sub="", tela="dividida")
    planos, _ = curta.de_roteiro(resp, fala(TEMPERATURA), 20)
    assert planos[0]["curta"]["destaque"] == "" and planos[1]["curta"]["destaque"] == "pratos novos"
    assert planos[1]["curta"]["destaque_sub"] == "" and planos[1]["curta"]["tela"] == "video"


def test_sem_roteiro_frase_sem_nada_para_mostrar_fica_no_video():
    assert curta._tem_o_que_mostrar({"situacao": "nenhuma", "personagens": [{"acao": "parado"}]}) is False
    assert curta._tem_o_que_mostrar({"situacao": "ideia"}) and curta._tem_o_que_mostrar({"objetos": [{"forma": "caixa"}]})


def test_schema_e_prompt_do_roteiro_pedem_tela_e_destaque():
    p = curta.schema_roteiro()["properties"]["planos"]["items"]
    assert p["properties"]["tela"]["enum"] == ["dividida", "video"] and {"tela", "destaque", "destaque_sub"} <= set(p["required"])
    texto = curta.prompt_roteiro("encaixe-vivo", fala(TEMPERATURA), 12, "T", {})
    assert "## Montagem" in texto and "tela cheia" in texto


def test_grafo_da_montagem_poe_o_video_por_baixo_e_desliza_a_mistura():
    from clipator.render import cadeia_montagem

    partes = ["[3:v]setpts=PTS-STARTPTS,scale=1080:1920,format=yuva420p[cen]", "[vlay]crop=1080:1056:0:0[vbaixo]",
              "[cen][vbaixo]overlay=0:864[vm]", "[vm]drawbox=x=0:y=861:w=iw:h=6:color=0xFF0000@1:t=fill[vda]"]
    mont = {"trechos": [{"t0": 0, "t1": 1.4, "tela": "video"}, {"t0": 1.4, "t1": 6, "tela": "dividida"}, {"t0": 6, "t1": 9, "tela": "video"}],
            "destaques": [{"t0": 3, "t1": 4.5, "texto": "40%", "sub": ""}], "zooms": [{"t0": 6, "t1": 9, "escala": 1.12}]}
    g = ";".join(cadeia_montagem(partes, mont, 1080, 1920))
    assert g.startswith("[vlay]split=2[vlaym][vfull0]") and "[vlaym]crop" in g and g.count("[vlay]") == 1
    assert "[cen0]split=2[cen][cenx]" in g and "eval=frame" in g and "between(t,6.000,9.000)*0.120" in g
    assert "[vfull][vmix]overlay=x=0:y='-1920*(" in g and "enable='between(t,1.100,6.000)'" in g
    assert "[vmo][cenx]overlay=0:0:enable='between(t,3.000,4.499)'" in g and g.endswith("[vda]")
    # tudo dividido e sem destaque: o grafo fica como estava
    so = {"trechos": [{"t0": 0, "t1": 9, "tela": "dividida"}], "destaques": [], "zooms": []}
    assert cadeia_montagem(partes, so, 1080, 1920) == partes


# ---- imagens reais do que a fala cita ---------------------------------------------------------------------------------
_PNG1 = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _abrir_falso(chamadas: list[str]):
    def abrir(url: str, timeout: float) -> bytes:
        chamadas.append(url)
        if "wbsearchentities" in url:
            if "Ilya" in url:
                return json.dumps({"search": [{"id": "Q99", "label": "Ilya Sutskever"}]}).encode()
            return json.dumps({"search": [{"id": "Q1", "label": "desamb"}, {"id": "Q182477", "label": "Nvidia"}]}).encode()
        if "EntityData/Q1.json" in url:
            return json.dumps({"entities": {"Q1": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q4167410"}}}}]}}}}).encode()
        if "EntityData/Q182477.json" in url:
            return json.dumps({"entities": {"Q182477": {"labels": {"pt": {"value": "Nvidia"}}, "descriptions": {"pt": {"value": "fabricante de chips"}},
                                                        "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q4830453"}}}}],
                                                                   "P18": [{"mainsnak": {"datavalue": {"value": "Sede.jpg"}}}],
                                                                   "P154": [{"mainsnak": {"datavalue": {"value": "NVIDIA logo.svg"}}}]}}}}).encode()
        if "EntityData/Q99.json" in url:  # achou uma empresa para "pessoa": não serve
            return json.dumps({"entities": {"Q99": {"claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q4830453"}}}}]}}}}).encode()
        if "commons.wikimedia.org/w/api.php" in url and "NVIDIA" in url:
            return json.dumps({"query": {"pages": {"1": {"imageinfo": [{"thumburl": "https://upload.wikimedia.org/x/logo.png", "descriptionurl": "https://c/x",
                                                                         "extmetadata": {"LicenseShortName": {"value": "Public domain"}}}]}}}}).encode()
        if url == "https://upload.wikimedia.org/x/logo.png":
            return _PNG1
        return b"{}"
    return abrir


def test_imagens_reais_pegam_o_logo_da_empresa_com_credito_e_recusam_tipo_errado(tmp_path):
    chamadas: list[str] = []
    ents = [{"termo": "Nvidia", "tipo": "empresa", "busca": "Nvidia"}, {"termo": "Iliasat Skiver", "tipo": "pessoa", "busca": "Ilya Sutskever"}]
    out, avisos = pesquisa.imagens_reais(ents, tmp_path, abrir=_abrir_falso(chamadas))
    assert [r["nome"] for r in out] == ["Nvidia"] and out[0]["logo"] and out[0]["contexto"] == "fabricante de chips"
    assert (tmp_path / out[0]["arquivo"]).read_bytes() == _PNG1 and out[0]["credito"]["licenca"] == "Public domain"
    assert "Ilya Sutskever" in avisos[0]
    n = len(chamadas)
    out2, _ = pesquisa.imagens_reais(ents, tmp_path, abrir=_abrir_falso(chamadas))  # cache na pasta do clip
    assert out2 == out and len(chamadas) == n


def test_imagem_real_entra_na_cena_em_que_e_dita_e_forca_o_painel(tmp_path):
    pals = fala("a gente comprou da Nvidia um monte de placa e depois a Nvidia subiu o preço de novo", 0.5)
    cenas = [_cena_plano(0, 4, pals, tela="video"), _cena_plano(4, 9, pals, tela="video")]
    (tmp_path / "pesquisa" / "imagens").mkdir(parents=True)
    arq = "pesquisa/imagens/0123456789abcdef.png"
    (tmp_path / arq).write_bytes(_PNG1)
    img = [{"termo": "Nvidia", "tipo": "empresa", "nome": "Nvidia", "contexto": "fabricante de chips", "arquivo": arq, "logo": True,
            "credito": {"fonte": "Wikimedia Commons", "licenca": "Public domain", "autor": "", "pagina": ""}}]
    assert curta.ligar_referencias(cenas, img, pals) == 1
    assert cenas[0]["params"]["curta"]["referencias"][0]["nome"] == "Nvidia" and not cenas[1]["params"]["curta"].get("referencias")
    assert curta.normalizar(cenas[0]["params"]["curta"])["referencias"] == cenas[0]["params"]["curta"]["referencias"]
    assert curta.normalizar({"referencias": [{**img[0], "arquivo": "../../segredo.png"}]})["referencias"] == []
    camada = tmp_path / "cenas"
    assert curta.copiar_referencias(cenas, tmp_path, camada) == [] and cenas[0]["_refs"][arq].startswith("midias/")
    m = curta.montagem(cenas, 9)
    r = m["referencias"][0]
    assert r["src"] == cenas[0]["_refs"][arq] and r["t0"] == pytest.approx(2.0 - 0.15) and r["t1"] - r["t0"] == pytest.approx(curta.REFERENCIA)
    assert any(s["tela"] == "dividida" and s["t0"] <= r["t0"] and s["t1"] >= r["t1"] for s in m["trechos"])


def test_roteiro_so_aceita_entidade_dita_e_prompt_pede_o_nome_certo():
    resp = _resposta()
    resp["entidades"] = [{"termo": "temperatura", "tipo": "tecnologia", "busca": "Temperatura (IA)"},
                         {"termo": "OpenAI", "tipo": "empresa", "busca": "OpenAI"}, {"termo": "ele", "tipo": "pessoa", "busca": "x"}]
    _, resumo = curta.de_roteiro(resp, fala(TEMPERATURA), 20)
    assert resumo["entidades"] == [{"termo": "temperatura", "tipo": "tecnologia", "busca": "Temperatura (IA)"}]
    assert "Ilya Sutskever" in curta.prompt_roteiro("encaixe-vivo", fala(TEMPERATURA), 12, "T", {})
