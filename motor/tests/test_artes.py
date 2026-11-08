"""As 28 direções de arte: registro, parâmetros, âncoras, plano sem IA, resposta da IA, versões, cache e composição."""

from __future__ import annotations

import json
import re

import pytest

from clipator import artes, desenho, direcao, edicao, hyperframes, melhorar, plataformas
from clipator.artes import kit
from clipator.models import Clip, Origem
from clipator.timeline import Timeline
from clipator.workspace import write_json

from .conftest import precisa_ffmpeg

SLUGS = sorted(artes.especificacoes())
COM_SVG = [s for s in SLUGS if s != "geo-em-cena"]  # o mapa e seus rótulos são desenhados pelo geo.js, não em <text> (tests/test_geo.py)


def fala(texto: str, passo: float = 0.3, inicio: float = 0.2) -> list[dict]:
    return [{"texto": p, "inicio": round(inicio + i * passo, 3), "fim": round(inicio + i * passo + passo * 0.8, 3)} for i, p in enumerate(texto.split())]


PALAVRAS = fala("O processo começa aqui. Depois o processo muda tudo. São 30 pessoas no total, e o resultado aparece no fim da semana.")


def camada(slug: str, parametros: dict | None = None, largura: int = 1080, altura: int = 1920, proporcao: float = 0.5, semente: int | None = None,
           pals: list[dict] = PALAVRAS, dur: float = 8.0) -> str:
    if slug == "geo-em-cena" and pals is PALAVRAS:  # aqui só frase com lugar vira cena
        pals = fala("O Brasil começa aqui. Depois o Chile muda tudo. São 30 pessoas na Argentina, e o resultado aparece no fim da semana.")
    cenas = artes.planejar_regras(slug, pals, dur, "x", {**(parametros or {}), **({"semente": semente} if semente is not None else {})})
    lista = [{**c, "palavras": artes.palavras_da_cena(pals, c["inicio"], c["fim"])} for c in cenas]
    return direcao.compor_camada(lista, direcao.ficha(f"arte-{slug}"), largura, altura, dur, "em-cima", proporcao, "T", 30, "", slug,
                                 plataformas.info("youtube-shorts", "9:16").zona)


def test_sao_28_direcoes_com_renderizador_preset_e_ficha(ws):
    assert len(SLUGS) == 28
    assert set(SLUGS) == set(artes.renderizadores())
    estilos = ws.estilos(None)
    for s in SLUGS:
        est = ws.carregar_estilo(f"arte-{s}")[0]
        assert est.direcao.modo == "arte" and est.direcao.arte == s and est.direcao.layout == "em-cima"
        assert not est.requer_ia, "os estilos de arte funcionam sem IA"
        assert f"arte-{s}" in estilos


@pytest.mark.parametrize("slug", SLUGS)
def test_composicao_sem_rede_sem_codigo_de_fora_e_com_as_cenas(slug):
    doc = camada(slug)
    assert doc.count('class="clip cena arte"') >= 2
    corpo = re.sub(r"<script>.*?</script>", "", doc, flags=re.S)
    assert not re.search(r'(src|href)="https?:', corpo) and "url(http" not in corpo
    assert "<script" not in corpo and "javascript:" not in corpo


@pytest.mark.parametrize("slug", SLUGS)
def test_todo_parametro_da_direcao_muda_algo_no_renderizador(slug):
    """Parâmetro no painel que o renderizador ignora seria mentira."""
    lidos: set[str] = set()

    class Espia(dict):
        def __getitem__(self, k):
            lidos.add(k)
            return super().__getitem__(k)

        def get(self, k, d=None):
            lidos.add(k)
            return super().get(k, d)

    cam = artes.Camada(slug, 1080, 1920, 0.0, 0.5, None, 8.0)
    c = cam.ctx({"texto": "Uma frase curta para medir", "nota": "frase", "itens": ["um", "dois", "três"]}, 0, 4, 0, 2, fala("Uma frase curta para medir"), None)
    c.par = Espia(c.par)
    cam.render.cena(c)
    if hasattr(cam.render, "fundo"):
        cam.render.fundo(c)
    js = artes.tres.JS if slug in artes.tres.DIRECOES else ""
    if slug in artes.cortes.DIRECOES:
        js = (artes._dados("cortes") / "motor.js").read_text(encoding="utf-8").replace("P.", "par.")
        curta_js = (artes._dados("curta") / "curta.js").read_text(encoding="utf-8").replace("P.", "par.")
        faltam_curta = {k for k in artes.especificacao(slug)["parametros_visuais"] if f"par.{k}" not in curta_js}
        assert not faltam_curta, "o modo curta também precisa ler cada parâmetro da direção"
    if slug == "geo-em-cena":
        js = (artes._dados("geo") / "geo.js").read_text(encoding="utf-8").replace("P.", "par.")
    faltam = {k for k in artes.especificacao(slug)["parametros_visuais"] if k not in lidos and f"par.{k}" not in js}
    assert not faltam


def test_parametro_desconhecido_e_recusado_e_o_valor_fica_nos_limites():
    with pytest.raises(ValueError, match="não existe"):
        artes.validar_parametros("anotacao-em-foco", {"max_linhas": 2, "filtro_ffmpeg": "x"})
    assert artes.validar_parametros("anotacao-em-foco", {"max_linhas": 99, "opacidade_faixa": 0.01}) == {"max_linhas": 3, "opacidade_faixa": 0.2}
    assert artes.validar_parametros("anotacao-em-foco", {"lixo": 1}, estrito=False) == {}
    assert artes.validar_parametros("oficina-modular", {"modulos": 1e9})["modulos"] == 80


def test_frase_repetida_escolhe_a_ocorrencia_certa_e_nao_aproxima():
    a = artes.achar("o processo", 2, PALAVRAS)
    assert a is not None and PALAVRAS[a[0]]["inicio"] > PALAVRAS[0]["inicio"] + 1
    assert artes.achar("O Processo!", 1, PALAVRAS) == (0, 1), "caixa e pontuação não contam"
    assert artes.achar("o processo", 3, PALAVRAS) is None
    assert artes.achar("processo aproximado", 1, PALAVRAS) is None


def test_trecho_removido_tira_a_cena_com_aviso_e_o_resto_segue_a_fala():
    cenas = [edicao.Item(tipo="cena", inicio=c["inicio"], fim=c["fim"], params=c["params"]) for c in artes.planejar_regras("mapa-de-ideias", PALAVRAS, 8.0, "antes")]
    assert len(cenas) >= 2
    # o usuário cortou a primeira frase: as palavras dela saem e as outras chegam antes
    resto = fala(" ".join(w["texto"] for w in PALAVRAS[4:]))
    novas, avisos, mudou = artes.reancorar(cenas, resto, 7.0, "depois")
    assert mudou and len(novas) == len(cenas) - 1 and "não está mais na fala" in avisos[0]
    assert all(c.fim <= 7.0 for c in novas) and novas[0].inicio < cenas[1].inicio
    # mesma timeline: nada muda, nem a cena que o usuário moveu à mão
    iguais, avisos, mudou = artes.reancorar(novas, resto, 7.0, "depois")
    assert not mudou and not avisos and [c.inicio for c in iguais] == [c.inicio for c in novas]


def test_plano_sem_ia_so_usa_o_que_foi_dito():
    pal = fala("A primeira ideia organiza tudo. A segunda ideia mostra o resultado.", 0.32)
    dur = pal[-1]["fim"] + 0.3
    cenas = artes.planejar_regras("anotacao-em-foco", pal, dur, "x")
    assert len(cenas) == 2 and cenas[-1]["fim"] <= dur
    ditas = {artes.tokens(w["texto"])[0] for w in pal}
    for c in cenas:
        p = c["params"]
        assert set(artes.tokens(p["texto"] + " " + p.get("nota", "") + " " + " ".join(p.get("itens", [])))) <= ditas
        assert artes.achar(p["ancora"], p["ocorrencia"], pal) is not None


def test_resposta_da_ia_nao_acrescenta_numero_nem_frase_que_nao_foi_dita():
    roteiro = [{"inicio": 0.0, "fim": 2.0, "ancora": "O processo começa aqui.", "etiqueta": "COMEÇO", "descricao": "x"}]
    resp = {"cenas": [{"indice": 0, "texto": "O mercado cresceu noventa por cento", "itens": ["Elon Musk"], "nota": "uma nota de mais de quatro palavras aqui", "dado": "90%", "peca": "bomba"}]}
    c = artes.de_resposta_ia("anotacao-em-foco", resp, roteiro, PALAVRAS)[0]["params"]
    assert "90" not in c.get("dado", "") and "mercado" not in c["texto"] and "Elon Musk" not in c.get("itens", [])
    assert len(c["nota"].split()) <= 4 and "peca" not in c or c["peca"] != "bomba"


def test_pedido_a_ia_leva_so_a_ficha_da_direcao_escolhida():
    p = artes.prompt_arte("costura-viva", [{"inicio": 0, "fim": 2, "ancora": "a"}])
    assert "Costura viva" in p
    assert not any(artes.especificacao(s)["nome"] in p for s in SLUGS if s != "costura-viva")


def test_caminho_de_midia_fora_da_pasta_e_recusado(tmp_path):
    raiz = tmp_path / "assets" / "arte"
    raiz.mkdir(parents=True)
    (tmp_path / "fora.png").write_bytes(b"x")
    (raiz / "a.png").write_bytes(b"1")
    for ruim in ("../fora.png", "..\\fora.png", "C:\\fora.png", "/etc/passwd", "https://x.com/a.png", "a.exe"):
        with pytest.raises(ValueError):
            artes.resolver_midia(raiz, ruim)
    assert artes.resolver_midia(raiz, "a.png").name == "a.png"
    try:
        (raiz / "link.png").symlink_to(tmp_path / "fora.png")
    except OSError:
        return  # sem permissão para criar link neste sistema
    with pytest.raises(ValueError):
        artes.resolver_midia(raiz, "link.png")


def test_conteudo_novo_no_mesmo_caminho_muda_a_camada(tmp_path):
    raiz, pasta = tmp_path / "m", tmp_path / "c"
    raiz.mkdir()
    (raiz / "a.png").write_bytes(b"um")
    cena = {"inicio": 0, "fim": 2, "params": {"cena": "arte", "midia": "a.png"}}
    assert artes.copiar_midias([cena], raiz, pasta) == []
    antes = cena["_midia"]
    (raiz / "a.png").write_bytes(b"dois")
    artes.copiar_midias([cena], raiz, pasta)
    assert cena["_midia"] != antes and (pasta / cena["_midia"]).is_file()
    falta = {"inicio": 0, "fim": 2, "params": {"cena": "arte", "midia": "sumiu.png"}}
    assert "alternativa" in artes.copiar_midias([falta], raiz, pasta)[0] and "_midia" not in falta


@pytest.mark.parametrize("slug", SLUGS)
def test_paleta_tem_contraste_de_leitura(slug):
    f = direcao.ficha(f"arte-{slug}")
    assert artes.contraste(f.texto, f.fundo) >= 4.5 and artes.contraste(f.texto, f.superficie) >= 4.5
    assert "cores" not in artes.especificacao(slug), "a paleta mora na DA"


@pytest.mark.parametrize("slug", SLUGS)
def test_nenhum_texto_usa_cor_sem_contraste_medido(slug):
    doc = camada(slug)
    fills = set(re.findall(r'<text [^>]*fill="([^"]+)"', doc))
    assert fills <= {"var(--texto)", "var(--acento)", "var(--sobre-primaria)", "var(--sobre-destaque)", "var(--fundo)"}, fills
    f = direcao.ficha(f"arte-{slug}")
    vals = dict(re.findall(r"(--acento|--sobre-primaria|--sobre-destaque): (#\w+)", doc))
    assert artes.contraste(vals["--acento"], f.fundo) >= 4.5
    assert artes.contraste(vals["--sobre-primaria"], f.primaria) >= 3 and artes.contraste(vals["--sobre-destaque"], f.destaque) >= 3


def test_cor_do_canal_que_estraga_a_leitura_e_corrigida_com_aviso():
    f = direcao.ficha("arte-anotacao-em-foco", {"texto": "#E8E0D0"})
    g, avisos = artes.ficha_legivel(f)
    assert g.texto == "#111111" and avisos and artes.contraste(g.texto, g.fundo) >= 4.5


def test_texto_comprido_com_acento_cabe_na_largura():
    ls, tam = kit.ajustar("Educação pública é imprescindível à transformação socioeconômica das próximas gerações brasileiras", "Montserrat ExtraBold", 600, 300, 3, 80, 34)
    assert len(ls) <= 3 and tam >= 34
    assert all(kit.largura(x, "Montserrat ExtraBold", tam) <= 600 for x in ls)


@pytest.mark.parametrize("slug", COM_SVG)
@pytest.mark.parametrize("largura,altura,prop", [(1080, 1920, 0.5), (1080, 1080, 0.5), (1920, 1080, 0.5), (1080, 1920, 0.7)])
def test_texto_fica_dentro_do_retangulo_em_cada_formato(slug, largura, altura, prop):
    doc = camada(slug, largura=largura, altura=altura, proporcao=prop)
    h = 1000 * (altura * prop) / largura
    ys = [float(y) for y in re.findall(r'<text x="[\d.-]+" y="([\d.-]+)"', doc)]
    assert ys and min(ys) >= 0 and max(ys) <= h + 1


def test_semente_muda_a_decoracao_e_nunca_o_texto():
    a, b = camada("letras-de-oficina", semente=1), camada("letras-de-oficina", semente=2)
    assert a != b
    textos = lambda d: sorted(re.findall(r"<text[^>]*>([^<]*)</text>", d))  # noqa: E731
    assert textos(a) == textos(b)
    assert camada("letras-de-oficina", semente=1) == a, "a mesma semente repete o documento"


@pytest.mark.parametrize("slug", COM_SVG)
def test_alternativa_leve_mantem_o_texto_e_tira_o_3d(slug):
    doc = camada(slug, {"leve": True})
    assert "arte-leve" in doc and "<canvas" not in doc
    assert "<text" in doc


def test_sem_three_as_direcoes_3d_ficam_na_alternativa_svg(monkeypatch):
    from clipator import maquete3d

    monkeypatch.setattr(maquete3d, "caminho_three", lambda: None)
    doc = camada("oficina-modular")
    assert "<canvas" not in doc and 'class="so-2d"' in doc


def test_com_three_o_3d_liga_e_guarda_a_alternativa():
    doc = camada("oficina-modular")
    assert '<canvas id="arte3d">' in doc and 'class="so-2d"' in doc and "clipator-arte3d" in doc
    assert "Math.random" not in artes.tres.JS and "Date.now" not in artes.tres.JS and "performance.now" not in artes.tres.JS


@pytest.mark.parametrize("slug", ["cidade-de-bolso", "jardim-de-luz", "janela-em-profundidade", "mesa-em-profundidade"])
def test_hibridas_tem_3d_e_guardam_a_alternativa_2d(slug, monkeypatch):
    from clipator import maquete3d

    doc = camada(slug)
    assert '<canvas id="arte3d">' in doc and 'class="so-2d"' in doc and "<text" in doc
    monkeypatch.setattr(maquete3d, "caminho_three", lambda: None)
    sem = camada(slug)
    assert "<canvas" not in sem and "<text" in sem


def test_cena_com_foto_fica_fora_do_3d():
    cam = artes.Camada("janela-em-profundidade", 1080, 1920, 0.0, 0.5, None, 8.0, ficha=direcao.ficha("arte-janela-em-profundidade"))
    cenas = [{"inicio": 0, "fim": 4, "params": {"cena": "arte", "texto": "x"}, "_midia": "midias/a.png"}]
    assert cam.extras(cenas) == ("", "")
    corpo = cam.cena({"texto": "uma frase"}, 0, 4, 0, 1, [], "midias/a.png")
    assert 'href="midias/a.png"' in corpo and '<g class="so-2d" clip-path' not in corpo


def test_animacao_de_svg_usa_o_tempo_da_composicao():
    """O HyperFrames busca o SVG pelo tempo total: a segunda cena não pode ter atrasos contados dela mesma."""
    pal = fala("Primeira frase bem curta aqui. Segunda frase bem curta aqui agora.", 0.4)
    dur = pal[-1]["fim"] + 0.5
    cenas = artes.planejar_regras("anotacao-em-foco", pal, dur, "x")
    lista = [{**c, "palavras": artes.palavras_da_cena(pal, c["inicio"], c["fim"])} for c in cenas]
    doc = direcao.compor_camada(lista, direcao.ficha("arte-anotacao-em-foco"), 1080, 1920, dur, "em-cima", 0.5, "T", 30, "", "anotacao-em-foco")
    trecho = doc[doc.index('id="cena-2"'):]
    atrasos = [float(x) for x in re.findall(r"animation:a-\w[\w-]* [\d.]+s [^;\"]*? ([\d.]+)s both", trecho)]
    assert atrasos and min(atrasos) >= cenas[1]["inicio"]


def _clip_arte(ws, slug="anotacao-em-foco"):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(p.transcricao_path, {"idioma": "pt", "duracao": 9, "segmentos": [{"inicio": 0, "fim": 9, "texto": "x", "palavras": [{**w, "prob": 0.9} for w in PALAVRAS]}]})
    p.salvar_clip(Clip(id="01-x", inicio=0, fim=8, titulo="T", formato="9:16", estilo=f"arte-{slug}"))
    _, pasta = p.clip("01-x")
    itens = [edicao.Item(tipo="cena", inicio=x["inicio"], fim=x["fim"], params=x["params"]) for x in artes.planejar_regras(slug, PALAVRAS, 8.0, "x")]
    edicao.salvar(pasta, edicao.Edicao(itens=itens, cenas_planejadas=True), 8.0)
    return p, pasta


def test_painel_grava_versao_e_desfazer_recupera_texto_ordem_parametro_e_cor(ws):
    p, pasta = _clip_arte(ws)
    antes = json.loads((pasta / "edicao.json").read_text(encoding="utf-8"))["itens"]
    ids = [i["id"] for i in antes]
    painel = desenho.resumo_do_clip(p, "01-x")["arte"]
    assert painel["id"] == "anotacao-em-foco" and painel["limites"]["max_linhas"]["maximo"] == 3 and len(painel["cenas"]) == len(antes)
    r = artes.ajustar(p, "01-x", [{"id": ids[1], "texto": "Texto novo da cena"}, {"id": ids[0]}], {"opacidade_faixa": 0.3}, {"destaque": "#112233"})
    depois = edicao.carregar(pasta).itens
    cenas = sorted((i for i in depois if i.tipo == "cena"), key=lambda i: i.inicio)
    assert cenas[0].params["texto"] == "Texto novo da cena" and cenas[0].id == ids[1]
    assert cenas[0].params["parametros"]["opacidade_faixa"] == 0.3 and cenas[0].params["cores"]["destaque"] == "#112233"
    assert desenho.resumo_do_clip(p, "01-x")["cores"]["destaque"] == "#112233"
    assert r["versao"] >= 2 and any(v["origem"] == "manual" for v in melhorar.listar(p, "01-x")["versoes"])
    melhorar.usar(p, "01-x", 1)
    voltou = {i.id: i.params for i in edicao.carregar(pasta).itens}
    assert voltou[ids[1]] == next(i["params"] for i in antes if i["id"] == ids[1])


def test_painel_recusa_parametro_desconhecido_sem_gravar(ws):
    p, pasta = _clip_arte(ws)
    antes = (pasta / "edicao.json").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        artes.ajustar(p, "01-x", None, {"comando": "rm"})
    assert (pasta / "edicao.json").read_text(encoding="utf-8") == antes


def test_ia_nas_tres_etapas_recebe_so_texto_e_a_ficha_certa(ws, monkeypatch):
    from clipator.ai import adapter

    p, pasta = _clip_arte(ws, "costura-viva")
    pedidos = []

    def falsa(ad, prompt, schema, cache, cancelar=None, ev=None):
        pedidos.append(prompt)
        if "ideias" in schema["properties"]:
            return {"tema": "processo", "ideias": []}
        if "indice" in schema["properties"]["cenas"]["items"]["properties"]:
            return {"cenas": [{"indice": 0, "texto": "O processo começa aqui", "itens": [], "nota": "começa", "dado": "", "peca": ""}]}
        return {"cenas": [{"ancora": "O processo começa aqui.", "ate": "", "etiqueta": "INÍCIO", "descricao": "a", "dado": "", "balao": ""}]}

    monkeypatch.setattr(adapter, "chamar", falsa)
    clip, _ = p.clip("01-x")
    est = ws.carregar_estilo(clip.estilo)[0]
    tl = Timeline.de_clip(0, 8, [])
    doc = desenho.gerar(p, clip, tl, PALAVRAS, est, type("A", (), {"nome": "falsa"})(), novo=True)
    assert doc["modo"] == "arte" and doc["cenas"][0]["params"]["arte"] == "costura-viva"
    assert desenho.para_itens(doc)[0]["params"]["ancora"].startswith("O processo")
    assert any("Costura viva" in x for x in pedidos) and not any("Jardim de luz" in x for x in pedidos)


def test_estilo_antigo_continua_igual():
    doc = direcao.compor_camada([{"inicio": 0, "fim": 2, "params": {"cena": "palavra", "texto": "OI"}}], direcao.ficha("neon"), 1080, 1920, 3, "em-cima")
    assert "arte" not in re.findall(r'<body class="([^"]*)"', doc)[0]
    assert direcao.normalizar_cena({"cena": "arte", "arte": "nao-existe", "texto": "x"})["cena"] == "palavra"


@precisa_ffmpeg
@pytest.mark.skipif(hyperframes.comando() is None, reason="HyperFrames não instalado")
def test_amostra_real_passa_pelo_render(ws, tmp_path, monkeypatch):
    from clipator import amostras, media

    monkeypatch.setenv("CLIPATOR_AMOSTRAS", str(tmp_path / "cache"))
    monkeypatch.setattr(amostras, "indice_prontas", lambda: {})
    v = amostras.gerar(ws, "arte-anotacao-em-foco")
    info = media.probe(v)
    assert info.duracao == pytest.approx(5.5, abs=0.2) and info.altura == 960


def test_sem_hyperframes_avisa_que_a_arte_nao_foi_renderizada(ws, tmp_path, monkeypatch, video_teste):
    from clipator import render

    p, pasta = _clip_arte(ws)
    (p.fonte_dir).mkdir(parents=True, exist_ok=True)
    (p.fonte_dir / "video.mp4").write_bytes(video_teste.read_bytes())
    monkeypatch.setattr(hyperframes, "comando", lambda: None)
    clip, _ = p.clip("01-x")
    est = ws.carregar_estilo(clip.estilo)[0]
    r = render.renderizar_clip(p, clip, est, preview=True, exigir_ia=False)
    assert r.video.exists() and "HyperFrames não instalado" in (r.aviso or "")


def test_rota_do_painel_recusa_parametro_antes_de_entrar_na_fila(ws):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    p, _ = _clip_arte(ws)
    srv = Servico(ws.root)
    enviados = []
    srv.fila.enviar = lambda tipo, dados: enviados.append((tipo, dados)) or "job1"
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    base = f"/api/canais/{p.canal.slug}/projetos/{p.id}/clips/01-x/direcao-arte"
    assert cl.get(base, headers=h).json()["arte"]["id"] == "anotacao-em-foco"
    assert cl.post(f"{base}/ajustar", json={"parametros": {"xss": 1}}, headers=h).status_code == 400 and not enviados
    r = cl.post(f"{base}/ajustar", json={"parametros": {"max_linhas": 2}}, headers=h)
    assert r.json() == {"job": "job1"} and enviados[0][0] == "ajustar_arte"
