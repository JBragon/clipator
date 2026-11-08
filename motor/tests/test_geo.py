"""Geo em Cena: base real, resolvedor, plano pela fala, avisos, enquadramento, layouts, persistência e cache."""

from __future__ import annotations

import gzip
import hashlib
import json
import re

import pytest

from clipator import artes, composicao, direcao, edicao, plataformas
from clipator.artes import geo, geografia as gg
from clipator.models import Clip, DirecaoArte, Legenda, LayoutArte, Origem
from clipator.timeline import Timeline

ZONA = plataformas.info("youtube-shorts", "9:16").zona
LEGENDA = Legenda(tamanho=60, posicao="baixo")
UFS = {  # cidades reais, em geral a capital (lon, lat; no litoral e em ilha a base generalizada corta a costa, então cidades do interior): cada ponto tem de cair no polígono da UF
    "AC": (-67.81, -9.97), "AL": (-35.74, -9.65), "AM": (-60.02, -3.10), "AP": (-51.07, 0.03), "BA": (-38.50, -12.97), "CE": (-38.54, -3.73), "DF": (-47.88, -15.79),
    "ES": (-40.63, -19.54), "GO": (-49.26, -16.68), "MA": (-44.30, -2.53), "MG": (-43.94, -19.92), "MS": (-54.62, -20.45), "MT": (-56.10, -15.60), "PA": (-49.12, -5.37),
    "PB": (-34.88, -7.12), "PE": (-35.98, -8.28), "PI": (-42.80, -5.09), "PR": (-49.27, -25.43), "RJ": (-43.21, -22.91), "RN": (-35.21, -5.79), "RO": (-63.90, -8.76),
    "RR": (-60.67, 2.82), "RS": (-51.23, -30.03), "SC": (-50.33, -27.82), "SE": (-37.07, -10.91), "SP": (-46.63, -23.55), "TO": (-48.33, -10.18)}


def fala(texto: str, passo: float = 0.4, inicio: float = 0.2) -> list[dict]:
    return [{"texto": p, "inicio": round(inicio + i * passo, 3), "fim": round(inicio + i * passo + passo * 0.8, 3)} for i, p in enumerate(texto.split())]


def plano_de(texto: str, dur: float = 20.0) -> list[dict]:
    pals = fala(texto)
    cenas = artes.planejar_regras(geo.SLUG, pals, dur, "x")
    return [{**c, "palavras": artes.palavras_da_cena(pals, c["inicio"], c["fim"])} for c in cenas]


def lugares(texto: str) -> list[str]:
    return [x["id"] for c in plano_de(texto) for x in c["params"]["corte"]["lugares"]]


def pendencias(texto: str) -> list[dict]:
    return [p for c in plano_de(texto) for p in c["params"]["corte"]["pendencias"]]


def camada(pals: list[dict], dur: float, g: composicao.Geometria | None) -> str:
    cenas = artes.planejar_regras(geo.SLUG, pals, dur, "x")
    lista = [{**c, "palavras": artes.palavras_da_cena(pals, c["inicio"], c["fim"])} for c in cenas]
    return direcao.compor_camada(lista, direcao.ficha(f"arte-{geo.SLUG}"), 1080, 1920, dur, g.layout if g else "em-cima", 0.5, "T", 30, "", geo.SLUG, ZONA, None, g, g.canto if g else None)


def dados(doc: str) -> dict:
    return json.loads(re.search(r"window\.GEO = (\{.*?\});</script>", doc, re.S).group(1).replace("<\\/", "</"))


# ---- a base ----------------------------------------------------------------------------------------------------
def test_base_incluida_bate_com_os_hashes_de_fontes_e_com_as_contagens():
    f = gg.fontes()
    assert "naturalearthdata.com" in f["termos"]
    for x in f["fontes"]:
        assert x["licenca_dados"] == "dominio-publico" and x["fonte"] == "Natural Earth"
        nome = x["arquivo"].rsplit("/", 1)[1]
        bruto = gzip.decompress((gg._dados("geo") / nome).read_bytes())
        assert hashlib.sha256(bruto).hexdigest() == x["sha256_incluido"]
        assert len(json.loads(bruto)["features"]) == x["feicoes_incluidas"]


def test_a_base_nao_carrega_estatistica():
    for nome in gg.CAMADAS:
        chaves = {k for f in gg.camada(nome) for k in f["properties"]}
        assert not {k for k in chaves if re.search(r"pop|gdp|pib|econ", k, re.I)}


# ---- UFs -------------------------------------------------------------------------------------------------------
def test_sao_27_ufs_e_o_df_nao_e_chamado_de_estado():
    ufs = [e for e in gg.entidades() if e.nivel == "subdivisao" and e.pais == "BRA"]
    assert sorted(e.iso for e in ufs) == sorted(f"BR-{k}" for k in UFS)
    assert all("Unidade federativa" in gg.descricao(e) for e in ufs)


@pytest.mark.parametrize("uf", sorted(UFS))
def test_cada_uf_resolve_e_contem_a_propria_capital_e_nao_a_das_outras(uf):
    e = gg.resolver(f"BR-{uf}")
    assert e.pais == "BRA" and e.iso == f"BR-{uf}"
    assert gg.resolver(e.nome, "estado", "Brasil") is e
    assert gg.contem(e, *UFS[uf])
    fora = [k for k, p in UFS.items() if k != uf and gg.contem(e, *p)]
    assert fora == []


def test_sao_paulo_fora_de_minas_e_minas_fora_de_sao_paulo():
    sp, mg = gg.resolver("BR-SP"), gg.resolver("BR-MG")
    assert gg.contem(sp, -46.63, -23.55) and not gg.contem(mg, -46.63, -23.55)
    assert gg.contem(mg, -43.94, -19.92) and not gg.contem(sp, -43.94, -19.92)


# ---- nomes -----------------------------------------------------------------------------------------------------
def test_georgia_sem_contexto_e_ambigua_e_com_contexto_resolve():
    with pytest.raises(gg.LugarNaoResolvido) as e:
        gg.resolver("Geórgia")
    assert e.value.motivo == "ambiguo" and {o.id for o in e.value.opcoes} == {"GEO", "USA-3543"}
    assert gg.resolver("Geórgia", "pais").id == "GEO"
    assert gg.resolver("Geórgia", None, "Estados Unidos").id == "USA-3543"
    assert gg.resolver("Geórgia", "estado", "EUA").pais == "USA"


def test_sao_paulo_como_uf_e_como_cidade():
    assert gg.resolver("São Paulo", "uf").iso == "BR-SP"
    with pytest.raises(gg.LugarNaoResolvido) as e:
        gg.resolver("São Paulo")
    assert e.value.motivo == "confirmar"
    with pytest.raises(gg.LugarNaoResolvido) as e:
        gg.resolver("São Paulo", "cidade")
    assert e.value.motivo == "cidade" and not e.value.opcoes


@pytest.mark.parametrize("termo,nivel,pais", [("Atlântida", "pais", None), ("-99", None, None), ("XX-ZZ", None, None), ("BR-SP", "estado", "Portugal"), ("ZZZ", None, None)])
def test_codigo_ou_nome_inexistente_e_recusado(termo, nivel, pais):
    with pytest.raises(gg.LugarNaoResolvido) as e:
        gg.resolver(termo, nivel, pais)
    assert e.value.motivo == "ausente"


def test_codigo_ausente_da_base_nao_vira_iso():
    assert not any("99" in c for e in gg.entidades() if e.nivel == "pais" for c in e.codigos)
    assert gg.resolver("Somalilândia").id == "SOL"


@pytest.mark.parametrize("nome,id_,ponto", [("Japão", "JPN", (139.7, 35.7)), ("Quênia", "KEN", (36.8, -1.3)), ("Alemanha", "DEU", (13.4, 52.5)), ("Canadá", "CAN", (-75.7, 45.4)),
                                            ("Austrália", "AUS", (149.1, -35.3)), ("Argentina", "ARG", (-58.4, -34.6)), ("Vietnã", "VNM", (105.8, 21.0))])
def test_paises_de_continentes_diferentes_batem_com_a_camada(nome, id_, ponto):
    e = gg.resolver(nome)
    assert e.id == id_ and e.nivel == "pais" and gg.contem(e, *ponto)


def test_homonimo_dentro_do_proprio_pais_fica_com_o_pais():
    assert gg.resolver("México").id == "MEX"
    assert gg.resolver("México", "estado").nivel == "subdivisao"


# ---- continente físico x país político --------------------------------------------------------------------------
def test_continente_e_camada_fisica_e_nao_soma_de_paises():
    eu, asia, russia, turquia = gg.resolver("Europa"), gg.resolver("Ásia"), gg.resolver("Rússia"), gg.resolver("Turquia")
    assert gg.contem(russia, 37.6, 55.8) and gg.contem(eu, 37.6, 55.8)
    assert gg.contem(russia, 104.3, 52.3) and gg.contem(asia, 104.3, 52.3) and not gg.contem(eu, 104.3, 52.3)
    assert gg.contem(turquia, 32.9, 39.9) and gg.contem(asia, 32.9, 39.9) and not gg.contem(eu, 32.9, 39.9)
    assert gg.contem(gg.resolver("França"), -53.0, 4.0) and gg.contem(gg.resolver("América do Sul"), -53.0, 4.0) and not gg.contem(eu, -53.0, 4.0)
    assert gg.resolver("Austrália").nivel == "pais" and gg.resolver("Oceania").nivel == "continente"


def test_america_sozinha_e_o_conjunto_norte_e_sul():
    e = gg.resolver("América")
    assert e.id == "americas" and {f["properties"]["continente"] for f in e.features} == {"north-america", "south-america"}
    assert gg.resolver("África do Sul").id == "ZAF" and lugares("A África do Sul fica longe.") == ["ZAF"]


# ---- ilhas, antimeridiano e buracos -----------------------------------------------------------------------------
def test_buraco_de_poligono_lesoto_nao_e_africa_do_sul():
    zaf, lso = gg.resolver("África do Sul"), gg.resolver("Lesoto")
    assert gg.contem(lso, 28.2, -29.6) and not gg.contem(zaf, 28.2, -29.6)
    assert gg.contem(zaf, 28.0, -26.2)
    assert sum(len(p) > 1 for p in gg.poligonos(zaf.features[0]["geometry"])) >= 1


def test_goias_tem_o_df_como_buraco():
    go = gg.resolver("BR-GO")
    assert not gg.contem(go, -47.88, -15.79) and gg.contem(gg.resolver("BR-DF"), -47.88, -15.79)


def test_fiji_e_russia_nao_viram_faixa_de_360_graus():
    o, _, l, _ = gg.enquadramento(gg.resolver("Fiji"))
    assert l - o < 15 and o < 180 < l, "Fiji atravessa o antimeridiano"
    o, _, l, _ = gg.enquadramento(gg.resolver("Rússia"))
    assert l - o < 200


def test_uniao_de_lugares_dos_dois_lados_do_antimeridiano_pega_o_arco_curto():
    o, _, l, _ = gg.juntar([(170.0, -20.0, 178.0, -10.0), (-179.0, -20.0, -170.0, -10.0)])
    assert l - o == pytest.approx(20) and o == 170


def test_anel_continuo_nao_salta_e_preserva_as_coordenadas():
    assert gg.continuo([[179.0, 0.0], [-179.0, 1.0], [-178.0, 0.0]]) == [[179.0, 0.0], [181.0, 1.0], [182.0, 0.0]]
    assert gg.continuo([[10.0, 1.0], [11.0, 2.0]]) == [[10.0, 1.0], [11.0, 2.0]]


def test_ilhas_multipolygon_inteiras_e_anel_externo_mais_buracos_no_dado():
    jp = gg.resolver("Japão")
    assert len(gg.poligonos(jp.features[0]["geometry"])) > 3
    assert gg.contem(jp, 141.35, 43.06) and gg.contem(jp, 130.4, 33.6)
    zaf = gg.resolver("África do Sul")
    assert len(gg.aneis_planos(zaf)) == sum(len(p) for p in gg.poligonos(zaf.features[0]["geometry"]))


def test_estados_unidos_enquadram_o_corpo_principal_mas_desenham_tudo():
    e = gg.resolver("Estados Unidos")
    o, _, l, _ = gg.enquadramento(e)
    assert o > -130 and l < -60
    assert gg.contem(e, -157.8, 21.3), "o Havaí continua pintado onde está"


# ---- a fala escolhe o lugar ---------------------------------------------------------------------------------------
def test_a_fala_do_exemplo_vira_continente_pais_e_ufs():
    ex = json.loads((artes._dados("artes") / "exemplos" / "geo-em-cena.json").read_text(encoding="utf-8"))
    ids = [x["id"] for c in artes.planejar_regras(geo.SLUG, ex["palavras"], ex["duracao_s"], "x") for x in c["params"]["corte"]["lugares"]]
    assert ids == ["south-america", "BRA", gg.resolver("BR-SP").id, gg.resolver("BR-MG").id]


def test_outra_fala_nao_traz_o_exemplo():
    ids = lugares("Agora olhe para a Ásia. O Japão aparece neste canto do mapa. Dentro do Japão, veja Hokkaido.")
    assert ids[:2] == ["asia", "JPN"] or ids[0] == "asia"
    assert "BRA" not in ids and all(not i.startswith("BRA-") for i in ids)
    assert gg.por_id("subdivisao", ids[-1]).pais == "JPN"


def test_palavra_comum_nao_vira_lugar_nem_codigo():
    assert lugares("Como eu disse para ele, a Guarda fica no norte. Se a gente vai de carro, o SP e o MG ficam para depois.") == []
    assert pendencias("Como eu disse para ele, o Sul e o Norte não importam agora.") == []


def test_acento_separa_para_de_para_o_estado():
    assert lugares("O Brasil é grande. O Pará fica ao norte do país.")[-1] == gg.resolver("BR-PA").id


def test_georgia_na_fala():
    p = pendencias("A Geórgia aparece na tela agora.")
    assert p and p[0]["motivo"] == "ambiguo" and {o["id"] for o in p[0]["opcoes"]} == {"GEO", "USA-3543"}
    assert lugares("A Geórgia aparece na tela agora.") == []
    assert lugares("A Geórgia, nos Estados Unidos, aparece agora.") == ["USA-3543"]
    assert lugares("O país da Geórgia aparece agora.") == ["GEO"]
    assert lugares("O estado da Geórgia aparece agora.") == ["USA-3543"]


def test_sao_paulo_na_fala():
    sp = gg.resolver("BR-SP").id
    assert lugares("O estado de São Paulo aparece agora.") == [sp]
    assert lugares("Dentro do Brasil, veja São Paulo.") == [sp], "o país da frase é contexto"
    assert lugares("Eu moro em São Paulo há muitos anos.") == [] and pendencias("Eu moro em São Paulo há muitos anos.")[0]["motivo"] == "confirmar"
    assert lugares("O Brasil é enorme mesmo. Eu moro em São Paulo há muitos anos.") == ["BRA"], "homônimo de cidade pede contexto na própria frase"
    cid = pendencias("A cidade de São Paulo no Brasil cresceu rápido.")
    assert cid[0]["motivo"] == "cidade" and not cid[0]["opcoes"]
    assert lugares("A cidade de São Paulo no Brasil cresceu rápido.") == ["BRA"]


def test_cidade_sem_camada_avisa_e_nao_desenha():
    p = pendencias("A cidade de Campinas cresceu bastante depois daquilo.")
    assert p and p[0]["motivo"] == "cidade" and p[0]["falado"] == "Campinas"


def test_subdivisao_usa_o_pais_ja_citado_e_nome_composto_nao_precisa():
    assert lugares("O Brasil é enorme mesmo. A Bahia fica no litoral.")[-1] == gg.resolver("BR-BA").id
    assert lugares("A Bahia fica no litoral do país.") == [] and pendencias("A Bahia fica no litoral do país.")[0]["motivo"] == "confirmar"
    assert lugares("E aqui está Minas Gerais.") == [gg.resolver("BR-MG").id]


def test_frase_sem_lugar_nao_vira_cena():
    assert plano_de("Hoje eu quero falar de uma coisa bem diferente de tudo aquilo.") == []


def test_cena_guarda_ancora_literal_e_ocorrencia():
    c = plano_de("O Brasil é grande e bonito. Depois disso o Chile aparece. O Brasil é grande e bonito.")
    assert c[-1]["params"]["ancora"].startswith("O Brasil") and c[-1]["params"]["ocorrencia"] == 2


# ---- IA ----------------------------------------------------------------------------------------------------------
def test_ia_so_devolve_nomes_e_o_schema_nao_tem_coordenada():
    txt = json.dumps(geo.schema())
    assert not re.search(r"lat|lon|coord|geometr", txt, re.I) and artes.schema_arte(geo.SLUG) == geo.schema()
    p = artes.prompt_arte(geo.SLUG, [{"ancora": "O Chile", "inicio": 0, "fim": 2}])
    assert "nunca coordenadas" in p and "O Chile" in p


def test_resposta_da_ia_e_conferida_com_a_fala_e_com_a_base():
    pals = fala("O Chile e a Geórgia e Atlantis aparecem agora.")
    r = geo.de_resposta({"acao": "destacar", "lugares": [
        {"nome": "Chile", "nivel": "pais", "pais": ""}, {"nome": "Peru", "nivel": "pais", "pais": ""},  # Peru não foi dito
        {"nome": "Geórgia", "nivel": "", "pais": ""}, {"nome": "Atlantis", "nivel": "pais", "pais": ""}]}, pals, 0, len(pals) - 1)
    assert [x["id"] for x in r["lugares"]] == ["CHL"] and r["acao"] == "destacar"
    assert {p["motivo"] for p in r["pendencias"]} == {"ambiguo", "ausente"}


def test_ia_nao_injeta_lugar_nem_coordenada_pelo_plano():
    r = geo.normalizar({"lugares": [{"id": "ZZZ", "nivel": "pais", "falado": "Wakanda", "coordenadas": [[0, 0]]}, {"id": "CHL", "nivel": "pais", "falado": "Chile", "anc": [1, 1], "nome": "Outro"}]})
    assert [x["nome"] for x in r["lugares"]] == ["Chile"] and "anc" not in r["lugares"][0] and "coordenadas" not in json.dumps(r)
    assert r["pendencias"][0]["motivo"] == "ausente"


# ---- plano do mapa -------------------------------------------------------------------------------------------------
def test_lugar_acende_na_palavra_e_apaga_na_proxima_cena():
    cs = plano_de("Olhe bem para a França agora mesmo. Depois disso veja bem a Espanha aqui.")
    pl = geo.plano(cs, 20.0)
    fr, es = pl["eventos"]
    pals = fala("Olhe bem para a França agora mesmo. Depois disso veja bem a Espanha aqui.")
    assert fr["t"] == pytest.approx(next(w["inicio"] for w in pals if w["texto"] == "França"), abs=0.01)
    assert es["t"] == pytest.approx(next(w["inicio"] for w in pals if w["texto"] == "Espanha"), abs=0.01)
    assert fr["tf"] == es["t"] and [q["t"] for q in pl["quadros"]] == [fr["t"], es["t"]]


def test_varios_lugares_na_frase_ficam_todos_enquadrados():
    pl = geo.plano(plano_de("O Chile e a Argentina dividem a cordilheira aqui."), 20.0)
    assert len(pl["eventos"]) == 2
    c = pl["quadros"][-1]["c"]
    for n in ("Chile", "Argentina"):
        o, s, l, nt = gg.enquadramento(gg.resolver(n))
        assert c[0] <= o and c[2] >= l and c[1] <= s and c[3] >= nt


def test_continente_cede_ao_pais_dentro_da_mesma_cena():
    pl = geo.plano(plano_de("A África tem o Egito ao norte dela."), 20.0)
    a, e = pl["eventos"]
    assert a["tf"] == e["t"] and pl["quadros"][-1]["c"] == gg.enquadramento(gg.resolver("Egito"))


def test_acao_destacar_nao_fecha_a_camera():
    cs = plano_de("Olhe bem para a França agora mesmo. Depois disso veja bem a Espanha aqui.")
    cs[-1]["params"]["corte"]["acao"] = "destacar"
    q = geo.plano(cs, 20.0)["quadros"]
    assert q[1]["c"][2] >= gg.enquadramento(gg.resolver("França"))[2]


def test_nome_que_saiu_num_corte_interno_some_com_aviso():
    cs = plano_de("Olhe bem para a França agora mesmo.")
    cs[0]["palavras"] = [w for w in cs[0]["palavras"] if w["texto"] != "França"]
    pl = geo.plano(cs, 20.0)
    assert not pl["eventos"] and "França" in pl["avisos"][0]


def test_tempo_segue_a_timeline_depois_do_corte_interno():
    pals = fala("Olhe bem para a França agora mesmo e veja a cena.")
    cenas = [edicao.Item(tipo="cena", **c) for c in artes.planejar_regras(geo.SLUG, pals, 10.0, "velha")]
    depois = [{**w, "inicio": w["inicio"] - 1.0, "fim": w["fim"] - 1.0} for w in pals[3:]]
    novas, avisos, mudou = artes.reancorar(cenas, depois, 9.0, "nova")
    assert mudou
    assert not novas and "não está mais" in avisos[0], "a âncora perdeu as palavras cortadas"


def test_corte_de_pausa_adianta_o_lugar_para_a_palavra_na_timeline_nova():
    pals = fala("Olhe bem para a França agora. Depois disso veja bem a Espanha aqui.")
    itens = [edicao.Item(tipo="cena", **c) for c in artes.planejar_regras(geo.SLUG, pals, 12.0, "velha")]
    depois = pals[:6] + [{**w, "inicio": round(w["inicio"] - 1.0, 3), "fim": round(w["fim"] - 1.0, 3)} for w in pals[6:]]
    novas, avisos, mudou = artes.reancorar(itens, depois, 11.0, "nova")
    assert mudou and not avisos and len(novas) == 2
    lista = [{"inicio": i.inicio, "fim": i.fim, "params": i.params, "palavras": artes.palavras_da_cena(depois, i.inicio, i.fim)} for i in novas]
    es = geo.plano(lista, 11.0)["eventos"][-1]
    assert es["nome"] == "Espanha" and es["t"] == pytest.approx(next(w["inicio"] for w in depois if w["texto"] == "Espanha"), abs=0.01)


def test_pendencia_vira_aviso_do_render():
    assert any("Geórgia" in a for a in geo.avisos(plano_de("A Geórgia aparece na tela agora."), 20.0))


def test_escolha_so_aceita_opcao_da_pendencia():
    c = plano_de("A Geórgia aparece na tela agora.")[0]["params"]["corte"]
    with pytest.raises(ValueError, match="Opção inválida"):
        geo.escolher(c, "Geórgia", "pais", "BRA")
    r = geo.escolher(c, "Geórgia", "pais", "GEO")
    assert [x["id"] for x in r["lugares"]] == ["GEO"] and not r["pendencias"]


def test_mesmo_plano_gera_o_mesmo_documento_e_a_fala_muda_o_documento():
    a = fala("Olhe bem para a França agora mesmo.")
    b = fala("Olhe bem para a Itália agora mesmo.")
    assert camada(a, 6.0, None) == camada(a, 6.0, None) != camada(b, 6.0, None)


# ---- composição ---------------------------------------------------------------------------------------------------
def geom(canto: str | None) -> composicao.Geometria:
    da = DirecaoArte(layout="janela", janela_canto=canto, janela_escala=0.34) if canto else DirecaoArte(layout="em-cima", proporcao=0.5)
    return composicao.geometria(da, 1080, 1920, ZONA, LEGENDA)


@pytest.mark.parametrize("canto", [None, *composicao.CANTOS])
def test_cinco_layouts_passam_o_retangulo_livre_ao_mapa(canto):
    g = geom(canto)
    doc = camada(fala("Olhe bem para a França agora mesmo."), 6.0, g)
    d = dados(doc)
    assert d["geo"]["layout"] == g.layout and d["geo"]["canto"] == canto
    foco = composicao.Ret(g.foco.x, g.foco.y, g.foco.w, g.foco.h)
    assert not foco.cruza(g.video) and g.seguro.contem(foco)
    if canto is None:
        assert g.video.h == g.arte.h == 960 and "--alt: 50.00%" in doc
    else:
        assert "--alt: 100.00%" in doc


def test_mapa_nao_usa_rede_e_escala_e_uma_so():
    doc = camada(fala("Olhe bem para a França agora mesmo."), 6.0, None)
    js = (gg._dados("geo") / "geo.js").read_text(encoding="utf-8")
    assert not re.search(r"https?://|fetch\(|XMLHttpRequest|tile", js)
    assert "Math.min(F.w /" in js, "um fator só: nunca F.w e F.h independentes"
    corpo = re.sub(r"<script>.*?</script>", "", doc, flags=re.S)
    assert not re.search(r'(src|href)="https?:', corpo)


def test_so_vao_junto_as_subdivisoes_do_pais_citado():
    d = dados(camada(fala("O Brasil é enorme mesmo e bonito. A Bahia fica no litoral do país."), 8.0, None))
    assert set(d["subdivisoes"]) == {"BRA"} and len(d["subdivisoes"]["BRA"]) == 27 and len(d["paises"]) == 242


def test_leve_mantem_o_mapa_real():
    pals = fala("Olhe bem para a França agora mesmo.")
    cenas = [{**c, "palavras": pals} for c in artes.planejar_regras(geo.SLUG, pals, 6.0, "x", {"leve": True})]
    doc = direcao.compor_camada(cenas, direcao.ficha(f"arte-{geo.SLUG}"), 1080, 1920, 6.0, "em-cima", 0.5, "T", 30, "", geo.SLUG, ZONA, {"leve": True})
    assert "arte-leve" in doc and '<canvas id="geo2d"' in doc and dados(doc)["par"]["leve"] is True


@pytest.mark.parametrize("canto", composicao.CANTOS)
def test_cada_recorte_e_um_estilo_da_galeria_com_o_canto_certo(ws, canto):
    est = ws.carregar_estilo(f"arte-{geo.SLUG}-{canto}")[0]
    assert est.direcao.arte == geo.SLUG and est.direcao.layout == "janela" and est.direcao.janela_canto == canto
    assert f"arte-{geo.SLUG}-{canto}" in ws.estilos(None)


def test_parametros_ficam_na_allowlist():
    with pytest.raises(ValueError, match="não existe"):
        artes.validar_parametros(geo.SLUG, {"url": "http://x"})
    with pytest.raises(ValueError, match="Valor inválido"):
        artes.validar_parametros(geo.SLUG, {"projecao": "javascript:1"})
    assert artes.validar_parametros(geo.SLUG, {"vizinhos": 99, "projecao": "mercator"}) == {"vizinhos": 3.5, "projecao": "mercator"}


def test_canto_escolhido_persiste_na_edicao_e_a_escolha_de_lugar_vira_versao(ws):
    canal = ws.criar_canal("Geo")
    p = canal.criar_projeto("p", Origem(tipo="arquivo", valor="a.mp4"))
    clip = Clip(id="01", inicio=0.0, fim=8.0, titulo="t", formato="9:16", plataforma="youtube-shorts", estilo=f"arte-{geo.SLUG}")
    p.salvar_clip(clip)
    _, pasta = p.clip(clip.id)
    pals = fala("A Geórgia aparece na tela agora.")
    itens = [edicao.Item(tipo="cena", **c) for c in artes.planejar_regras(geo.SLUG, pals, 8.0, artes.assinatura_timeline(Timeline.de_clip(0.0, 8.0, [])))]
    edicao.salvar(pasta, edicao.Edicao(itens=itens, cenas_planejadas=True), 8.0)
    artes.ajustar(p, clip.id, layout={"layout": "janela", "janela_canto": "superior-esquerdo"})
    doc = edicao.carregar(pasta)
    assert doc.layout_arte == LayoutArte(layout="janela", janela_canto="superior-esquerdo") or doc.layout_arte.janela_canto == "superior-esquerdo"
    painel = artes.resumo_painel(geo.SLUG, doc.itens)
    assert painel["acoes"] == list(geo.ACOES) and painel["cenas"][0]["pendencias"][0]["falado"] == "Geórgia"
    it = next(i for i in doc.itens if i.tipo == "cena")
    artes.ajustar(p, clip.id, cenas=[{"id": it.id, "escolha": {"falado": "Geórgia", "nivel": "subdivisao", "id": "USA-3543"}}])
    c = next(i for i in edicao.carregar(pasta).itens if i.tipo == "cena")
    assert [x["id"] for x in c.params["corte"]["lugares"]] == ["USA-3543"] and not c.params["corte"]["pendencias"]
    assert edicao.carregar(pasta).layout_arte.janela_canto == "superior-esquerdo"
