"""As cinco direções guiadas pela fala e os cinco layouts: geometria, plano pela fala, âncoras, persistência, cache e composição."""

from __future__ import annotations

import json
import re

import pytest

from clipator import artes, composicao, desenho, direcao, edicao, melhorar, plataformas, render
from clipator.artes import cortes
from clipator.models import Clip, DirecaoArte, Legenda, LayoutArte, Origem
from clipator.timeline import Timeline
from clipator.workspace import write_json

SLUGS = list(cortes.ACOES)
ZONA = plataformas.info("youtube-shorts", "9:16").zona
LEGENDA = Legenda(tamanho=60, posicao="baixo")


def fala(texto: str, passo: float = 0.3, inicio: float = 0.2) -> list[dict]:
    return [{"texto": p, "inicio": round(inicio + i * passo, 3), "fim": round(inicio + i * passo + passo * 0.8, 3)} for i, p in enumerate(texto.split())]


def exemplo(slug: str) -> tuple[list[dict], float]:
    ex = json.loads((artes._dados("artes") / "exemplos" / f"{slug}.json").read_text(encoding="utf-8"))
    return ex["palavras"], float(ex["duracao_s"])


def geo(canto: str | None = None, largura: int = 1080, altura: int = 1920, zona=ZONA) -> composicao.Geometria:
    da = DirecaoArte(layout="janela", janela_canto=canto, janela_escala=0.34) if canto else DirecaoArte(layout="em-cima", proporcao=0.5)
    return composicao.geometria(da, largura, altura, zona, LEGENDA)


def camada(slug: str, g: composicao.Geometria | None = None, pals: list[dict] | None = None, dur: float | None = None) -> str:
    p0, d0 = exemplo(slug)
    pals, dur = pals or p0, dur or d0
    cenas = artes.planejar_regras(slug, pals, dur, "x")
    for c in cenas:  # aqui se testa o motor de um mundo só (projetos sem o modo curta); o curta tem test_curta.py
        c["params"].pop("curta", None)
    lista = [{**c, "palavras": artes.palavras_da_cena(pals, c["inicio"], c["fim"])} for c in cenas]
    return direcao.compor_camada(lista, direcao.ficha(f"arte-{slug}"), 1080, 1920, dur, g.layout if g else "em-cima", 0.5, "T", 30, "", slug, ZONA, None, g, g.canto if g else None)


def plano_do(doc: str) -> dict:
    return json.loads(re.search(r"window\.CORTE = (\{.*?\});</script>", doc, re.S).group(1).replace("<\\/", "</"))


# ---- layouts ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("canto", composicao.CANTOS)
def test_janela_fica_no_canto_pedido_fora_da_legenda_e_na_area_segura(canto):
    g = geo(canto)
    v = g.video
    assert (v.x + v.w / 2 > 540) == canto.endswith("direito")
    assert (v.y + v.h / 2 > 960) == canto.startswith("inferior")
    assert v.y >= ZONA.topo * 1920 and v.y1 <= 1920 * (1 - ZONA.base)
    assert v.x >= ZONA.esquerda * 1080
    if v.y1 > 960:
        assert v.x1 <= 1080 * (1 - ZONA.direita), "os botões da plataforma cobrem a metade de baixo"
    assert v.y1 <= g.faixa[0] or v.y >= g.faixa[1]
    assert abs(v.w / v.h - composicao.PROPORCAO_JANELA) < 0.02, "o retângulo mantém a proporção"
    assert v.x % 2 == v.y % 2 == v.w % 2 == v.h % 2 == 0


@pytest.mark.parametrize("canto", [None, *composicao.CANTOS])
def test_foco_da_arte_nao_cruza_janela_nem_legenda(canto):
    g = geo(canto)
    assert g.foco.area > 0.25 * g.seguro.area
    assert g.seguro.contem(g.foco)
    for e in g.exclusoes:
        assert not g.foco.cruza(e)


def test_cada_layout_da_um_retangulo_proprio_para_a_camera():
    focos = {(g.foco.x, g.foco.y, g.foco.w, g.foco.h) for g in [geo(None), *(geo(c) for c in composicao.CANTOS)]}
    assert len(focos) >= 3
    assert geo(None).arte.h == 960 and geo("inferior-direito").arte.h == 1920


def test_outros_formatos_tambem_cabem():
    z = plataformas.info("youtube", "16:9").zona
    for c in composicao.CANTOS:
        g = geo(c, 1920, 1080, z)
        assert 0 <= g.video.x and g.video.x1 <= 1920 and g.video.y >= 0 and g.video.y1 <= 1080


def test_canto_invalido_e_recusado():
    with pytest.raises(ValueError):
        composicao.retangulo_janela(1080, 1920, 0.3, "centro")
    with pytest.raises(ValueError):
        LayoutArte.model_validate({"layout": "janela", "janela_canto": "meio"})


@pytest.mark.parametrize("canto", composicao.CANTOS)
def test_filtro_usa_o_retangulo_e_nao_deforma(canto):
    g = geo(canto)
    da = DirecaoArte(layout="janela", janela_canto=canto, janela_escala=0.34)
    partes = render.cadeia_mistura("janela", da, "#112233", 1080, 1920, 3, None, "nenhum", janela=g.video, rosto=(0.5, 0.3, 0.2))
    txt = ";".join(partes)
    assert f"overlay={g.video.x}:{g.video.y}" in txt
    sw, sh = map(int, re.search(r"\[vlay\]scale=(\d+):(\d+)", txt).groups())
    assert abs(sw / sh - 1080 / 1920) < 0.01, "a escala é igual nos dois eixos"
    cw, ch = map(int, re.search(r"crop=(\d+):(\d+)", txt).groups())
    pw, ph = map(int, re.search(r",scale=(\d+):(\d+):flags=lanczos,setsar", txt).groups())
    assert abs(cw / ch - pw / ph) < 0.02, "o recorte tem a proporção da janela"


def test_barras_mostram_o_quadro_inteiro():
    g = geo("superior-esquerdo")
    da = DirecaoArte(layout="janela", janela_canto="superior-esquerdo", janela_encaixe="barras")
    txt = ";".join(render.cadeia_mistura("janela", da, "#112233", 1080, 1920, 3, None, "nenhum", janela=g.video))
    assert "force_original_aspect_ratio=decrease" in txt and "crop=" not in txt


def test_clip_antigo_sem_canto_continua_na_posicao_de_antes():
    da = DirecaoArte(layout="janela")
    assert da.janela_canto is None
    txt = ";".join(render.cadeia_mistura("janela", da, "#112233", 1080, 1920, 3, None, "nenhum"))
    assert "overlay=W-w-" in txt


# ---- estilos ---------------------------------------------------------------------------------------------------
def test_cinco_estilos_com_nomes_e_presets(ws):
    nomes = {"encaixe-vivo": "Encaixe Vivo", "pixel-em-cena": "Pixel em Cena", "fluxo-facetado": "Fluxo Facetado", "rota-em-foco": "Rota em Foco", "terreno-vivo": "Terreno Vivo"}
    assert set(SLUGS) == set(nomes)
    for s, n in nomes.items():
        est = ws.carregar_estilo(f"arte-{s}")[0]
        assert est.nome == n and est.direcao.arte == s and est.direcao.janela_canto == "inferior-direito" and est.direcao.proporcao == 0.5 and not est.requer_ia


def test_motor_e_deterministico_e_nao_depende_de_fora():
    js = (artes._dados("cortes") / "motor.js").read_text(encoding="utf-8")
    for proibido in ("Math.random", "Date.now", "performance.now", "fetch(", "XMLHttpRequest", "http://", "https://", "Downloads"):
        assert proibido not in js.replace("http://www.w3.org/2000/svg", "")


def test_codigo_nao_aponta_para_o_pacote_de_referencia():
    for arq in [artes._dados("cortes") / "lexico.json", *(artes._dados("artes") / f"{s}.json" for s in SLUGS)]:
        assert "Downloads" not in arq.read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", SLUGS)
def test_exemplo_proprio_vira_acoes_com_objetos_ditos(slug):
    pals, dur = exemplo(slug)
    cenas = artes.planejar_regras(slug, pals, dur, "x")
    assert len(cenas) >= 3
    ditas = {t for w in pals for t in artes.tokens(w["texto"])}
    for c in cenas:
        ct = c["params"]["corte"]
        assert ct["acao"] in cortes.ACOES[slug]
        assert c["params"]["ancora"] and c["params"]["ocorrencia"] >= 1
        for o in ct["objetos"]:
            assert set(artes.tokens(o["nome"])) <= ditas and o["forma"] in cortes.formas()


SEGUNDA = {"encaixe-vivo": ("A base sustenta o foguete. O motor fica acima da base. O tanque guarda o combustível.", {"motor", "tanque"}, {"microscopio"}),
           "pixel-em-cena": ("A faroleira chega ao cais. Ela cruza a ponte até a torre. A lâmpada acende no alto.", {"faroleira", "ponte", "torre"}, {"telescopio"}),
           "fluxo-facetado": ("O grão entra no moedor. A balança mede o café. A comporta separa o caminho.", {"grao", "moedor", "comporta"}, {"esteira"}),
           "rota-em-foco": ("O barco sai do porto. A rota contorna o cabo. O navio chega à vila.", {"barco", "porto", "vila"}, {"abrigo"}),
           "terreno-vivo": ("O lote começa vazio. A torre sobe no centro. As árvores crescem perto da torre.", {"torre", "arvores"}, {"canteiros"})}


@pytest.mark.parametrize("slug", SLUGS)
def test_outra_fala_muda_objetos_e_nao_repete_o_exemplo(slug):
    texto, tem, nao_tem = SEGUNDA[slug]
    pals = fala(texto, 0.35)
    doc = camada(slug, geo("inferior-esquerdo"), pals, 12.0)
    p = plano_do(doc)
    ids = {o["id"] for a in p["acoes"] for o in a["objetos"]}
    assert tem <= ids, ids
    assert not (nao_tem & ids)
    assert p != plano_do(camada(slug, geo("inferior-esquerdo")))


@pytest.mark.parametrize("slug", SLUGS)
def test_mesmo_plano_em_todos_os_layouts_e_o_retangulo_muda(slug):
    planos = [plano_do(camada(slug, g)) for g in [geo(None), *(geo(c) for c in composicao.CANTOS)]]
    assert all(p["acoes"] == planos[0]["acoes"] for p in planos)
    assert len({json.dumps(p["geo"], sort_keys=True) for p in planos}) == 5


def test_trocar_o_canto_muda_o_documento_da_camada():
    a, b = camada("terreno-vivo", geo("inferior-direito")), camada("terreno-vivo", geo("superior-esquerdo"))
    assert a != b and camada("terreno-vivo", geo("inferior-direito")) == a


def test_objeto_nao_aparece_antes_de_ser_dito():
    pals = fala("Primeiro falamos do clima hoje. Depois a coluna entra aqui.", 0.4)
    cenas = artes.planejar_regras("encaixe-vivo", pals, 8.0, "x")
    lista = [{**c, "palavras": artes.palavras_da_cena(pals, c["inicio"], c["fim"])} for c in cenas]
    acoes = cortes.plano(lista)
    t_coluna = next(w["inicio"] for w in pals if w["texto"] == "coluna")
    o = next(o for a in acoes for o in a["objetos"] if o["nome"] == "coluna")
    assert abs(o["t"] - t_coluna) < 0.02


def test_ancora_repetida_e_corte_interno_movem_a_acao():
    pals = fala("A coluna sobe. Nada aqui ainda. A coluna sobe. Fim da conversa agora.", 0.4)
    cenas = artes.planejar_regras("encaixe-vivo", pals, 9.0, "t0")
    segunda = next(c for c in cenas if c["params"]["ocorrencia"] == 2)
    assert abs(segunda["inicio"] - (pals[6]["inicio"] - 0.1)) < 0.11
    itens = [edicao.Item(tipo="cena", **c) for c in cenas]
    depois = [dict(w, inicio=w["inicio"] - 2.0, fim=w["fim"] - 2.0) for w in pals[3:]]  # o começo foi cortado
    novos, avisos, mudou = artes.reancorar(itens, depois, 7.0, "t1")
    assert mudou and any("não está mais na fala" in a for a in avisos) or novos
    assert all(i.inicio >= 0 for i in novos)


def test_trecho_removido_tira_a_acao_e_o_objeto_some_do_plano():
    pals = fala("A coluna sobe aqui. A lente fica no alto.", 0.4)
    cenas = artes.planejar_regras("encaixe-vivo", pals, 6.0, "t0")
    itens = [edicao.Item(tipo="cena", **c) for c in cenas]
    novos, avisos, _ = artes.reancorar(itens, pals[:4], 2.0, "t1")
    assert avisos and all("lente" not in json.dumps(i.params) for i in novos)


# ---- IA --------------------------------------------------------------------------------------------------------
def test_ia_recebe_so_texto_do_estilo_e_devolve_json_conferido():
    roteiro = [{"inicio": 0, "fim": 3, "ancora": "A base mantém", "etiqueta": "", "descricao": "", "dado": ""}]
    p = artes.prompt_arte("encaixe-vivo", roteiro)
    assert "Encaixe Vivo" in p and "Pixel em Cena" not in p and "Terreno Vivo" not in p
    assert artes.schema_arte("encaixe-vivo")["properties"]["cenas"]["items"]["properties"]["acao"]["enum"] == list(cortes.ACOES["encaixe-vivo"])
    assert artes.schema_arte("anotacao-em-foco") is artes.SCHEMA_ARTE


def test_objeto_ou_numero_que_nao_foi_dito_nao_passa():
    pals = fala("A base mantém tudo firme.")
    roteiro = [{"inicio": 0.0, "fim": 2.0, "ancora": "A base mantém", "etiqueta": "", "descricao": ""}]
    resp = {"cenas": [{"indice": 0, "texto": "", "itens": [], "nota": "", "dado": "99%", "peca": "", "acao": "voar", "alvo": "dragão", "conjunto": "",
                       "objetos": [{"nome": "dragão", "forma": "bloco"}, {"nome": "base", "forma": "base"}]}]}
    c = artes.de_resposta_ia("encaixe-vivo", resp, roteiro, pals, "x")[0]["params"]
    assert [o["nome"] for o in c["corte"]["objetos"]] == ["base"]
    assert c["corte"]["acao"] == "montar" and "dado" not in c


def test_forma_desconhecida_vira_a_do_lexico_e_acao_vira_a_padrao():
    c = cortes.normalizar_corte("fluxo-facetado", {"acao": "explodir", "objetos": [{"nome": "sensor", "forma": "<script>"}]})
    assert c["acao"] == "mover" and c["objetos"][0]["forma"] == "sensor"


# ---- persistência e painel -------------------------------------------------------------------------------------
def _clip(ws, estilo="arte-terreno-vivo"):
    pals = fala("O terreno começa vazio. A água passa pelos canais. Os canteiros recebem as mudas.")
    canal = ws.criar_canal("L")
    p = canal.criar_projeto("x", Origem(tipo="arquivo", valor="v.mp4"))
    write_json(p.transcricao_path, {"idioma": "pt", "duracao": 8, "modelo": "t", "dispositivo": "cpu", "segmentos": [
        {"inicio": 0, "fim": 8, "texto": "x", "palavras": [{**w, "prob": 1.0} for w in pals]}]})
    clip = Clip(id="01-x", inicio=0.0, fim=8.0, titulo="T", formato="9:16", plataforma="youtube-shorts", estilo=estilo)
    p.salvar_clip(clip)
    _, pasta = p.clip("01-x")
    tl = Timeline.de_clip(0.0, 8.0, [])
    itens = [edicao.Item(tipo="cena", origem="heuristica", **c) for c in artes.planejar_regras("terreno-vivo", pals, 8.0, artes.assinatura_timeline(tl))]
    edicao.salvar(pasta, edicao.Edicao(itens=itens, cenas_planejadas=True), 8.0)
    return p, pasta


def test_canto_escolhido_persiste_reabre_e_volta_com_a_versao(ws):
    p, pasta = _clip(ws)
    v1 = artes.ajustar_layout(p, "01-x", {"layout": "janela", "janela_canto": "superior-esquerdo"})["versao"]
    assert edicao.carregar(pasta).layout_arte.janela_canto == "superior-esquerdo"
    r = desenho.resumo_do_clip(p, "01-x")["composicao"]
    assert r["layout"] == "janela" and r["janela_canto"] == "superior-esquerdo" and r["janela_escala"] == 0.34
    v2 = artes.ajustar_layout(p, "01-x", {"layout": "em-cima", "proporcao": 0.5})["versao"]
    assert v2 >= v1
    melhorar.usar(p, "01-x", 1)  # a versão de antes de qualquer escolha
    assert edicao.carregar(pasta).layout_arte is None
    assert desenho.resumo_do_clip(p, "01-x")["composicao"]["layout"] == "em-cima"


def test_voltar_a_versao_com_janela_recupera_o_canto_e_o_conteudo(ws):
    p, pasta = _clip(ws)
    v = artes.ajustar_layout(p, "01-x", {"layout": "janela", "janela_canto": "inferior-esquerdo"})["versao"]
    cenas = [i.params for i in edicao.carregar(pasta).itens]
    ver = melhorar.ler(pasta, v)
    assert ver["layout_arte"]["janela_canto"] == "inferior-esquerdo"
    d = edicao.carregar(pasta)
    edicao.salvar(pasta, d.model_copy(update={"layout_arte": LayoutArte(layout="em-cima"), "itens": []}), 8.0)
    melhorar.usar(p, "01-x", v)
    doc = edicao.carregar(pasta)
    assert doc.layout_arte.janela_canto == "inferior-esquerdo" and [i.params for i in doc.itens] == cenas


def test_estilo_recebe_a_composicao_do_clip_sem_mudar_o_preset(ws):
    est = ws.carregar_estilo("arte-rota-em-foco")[0]
    doc = edicao.Edicao(layout_arte=LayoutArte(layout="janela", janela_canto="superior-direito"))
    novo = edicao.estilo_com_layout(est, doc)
    assert novo.direcao.layout == "janela" and novo.direcao.janela_canto == "superior-direito" and novo.direcao.janela_escala == 0.34
    assert est.direcao.layout == "em-cima"


def test_ajuste_da_galeria_tambem_escolhe_o_canto(ws):
    est = ws.carregar_estilo("arte-pixel-em-cena", None, {"direcao": {"layout": "janela", "janela_canto": "superior-direito"}})[0]
    assert est.direcao.layout == "janela" and est.direcao.janela_canto == "superior-direito" and est.direcao.arte == "pixel-em-cena"


def test_painel_mostra_as_acoes_e_grava_a_acao_trocada(ws):
    p, pasta = _clip(ws)
    r = artes.resumo_painel("terreno-vivo", edicao.carregar(pasta).itens)
    assert r["acoes"] == list(cortes.ACOES["terreno-vivo"]) and r["cenas"][0]["acao"]
    alvo = r["cenas"][1]["id"]
    artes.ajustar(p, "01-x", [{"id": alvo, "acao": "segurar"}])
    assert next(i for i in edicao.carregar(pasta).itens if i.id == alvo).params["corte"]["acao"] == "segurar"


def test_rota_do_painel_recusa_canto_invalido_antes_da_fila(ws):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app

    from clipator.service import Servico

    p, _ = _clip(ws)
    srv = Servico(ws.root)
    enviados: list = []
    srv.fila.enviar = lambda tipo, dados: enviados.append((tipo, dados)) or "job1"
    c = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    url = f"/api/canais/{p.canal.slug}/projetos/{p.id}/clips/01-x/direcao-arte/ajustar"
    assert c.post(url, headers=h, json={"composicao": {"layout": "janela", "janela_canto": "meio"}}).status_code >= 400 and not enviados
    assert c.post(url, headers=h, json={"composicao": {"layout": "janela", "janela_canto": "superior-direito"}}).status_code == 200
    assert enviados[0][1]["composicao"]["janela_canto"] == "superior-direito"


def test_mcp_expoe_a_escolha_de_composicao():
    src = (artes._dados("cortes").parents[1] / "mcp_server.py").read_text(encoding="utf-8")
    assert "def escolher_composicao(" in src


def test_sem_three_fica_a_alternativa_e_os_nomes_ditos(monkeypatch):
    from clipator import maquete3d

    monkeypatch.setattr(maquete3d, "caminho_three", lambda: None)
    doc = camada("fluxo-facetado", geo("superior-direito"))
    assert "<canvas" not in doc and 'class="so-2d"' in doc and "sensor" in doc
