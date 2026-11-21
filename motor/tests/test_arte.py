"""Direção de arte do canal (clipator.arte): cores, herança, validação, compilação, identidade, lint, rotas e CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clipator.arte import cores as C
from clipator.arte import servico
from clipator.arte.carregar import (
    ErroDA,
    carregar_arquivo,
    carregar_preset,
    listar_presets,
    salvar_yaml,
)
from clipator.arte.validar import resumo, validar


@pytest.fixture(autouse=True)
def _presets_pessoais(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPATOR_ARTE_PRESETS", str(tmp_path / "presets-pessoais"))


@pytest.fixture
def canal(ws):
    c = ws.criar_canal("Teste Arte")
    servico.criar(c.path, "base", "Canal de teste")
    return c


def _editar(canal_path: Path, **secoes) -> None:
    import yaml

    arq = canal_path / "arte" / "direcao.yaml"
    dados = yaml.safe_load(arq.read_text(encoding="utf-8"))
    for k, v in secoes.items():
        dados[k] = v
    salvar_yaml(arq, dados)


# ---- cores ----------------------------------------------------------------------------------------------

def test_contraste_wcag_conhecido():
    assert C.contraste("#000000", "#FFFFFF") == pytest.approx(21, abs=0.01)
    assert C.contraste("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.02)
    assert C.nivel_wcag(C.contraste("#000000", "#FFFFFF")) == "AAA"


def test_delta_e_e_lab_ida_e_volta():
    assert C.delta_e("#3DA9FC", "#3DA9FC") == pytest.approx(0, abs=1e-6)
    assert C.delta_e("#FF0000", "#00FF00") > 50
    assert C.lab_rgb(C.rgb_lab((12, 200, 99))) == pytest.approx((12, 200, 99), abs=1)
    assert C.normalizar_hex("#abc") == "#AABBCC"


def test_ajustar_para_contraste_atinge_o_alvo():
    cor = C.ajustar_para_contraste("#777777", "#FFFFFF", 4.5)
    assert C.contraste(cor, "#FFFFFF") >= 4.5
    assert C.delta_e(cor, "#777777") < 15


# ---- predefinidos e herança -----------------------------------------------------------------------------

def test_todos_os_predefinidos_validam_sem_erro_nem_aviso():
    nomes = [p["nome"] for p in listar_presets()]
    assert {"base", "manchete", "fliperama", "documental"} <= set(nomes)
    for nome in nomes:
        r = carregar_preset(nome)
        e, a, _ = resumo(validar(r))
        assert (e, a) == (0, 0), f"{nome}: {[x.linha() for x in validar(r) if x.nivel != 'nota']}"


def test_heranca_mescla_e_lista_substitui(tmp_path):
    arq = tmp_path / "direcao.yaml"
    salvar_yaml(arq, {"herda": "base", "cor": {"paleta": {"primaria": "#ff0055"}, "serie": [
        "primaria", "destaque", "texto", "positivo", "negativo", "#8844FF"]}})
    r = carregar_arquivo(arq)
    assert r.cor("primaria") == "#FF0055"
    assert r.cor("fundo") == carregar_preset("base").cor("fundo")  # herdado
    assert r.serie_hex[0] == "#FF0055" and r.serie_hex[-1] == "#8844FF"


def test_chave_desconhecida_e_erro(tmp_path):
    arq = tmp_path / "direcao.yaml"
    salvar_yaml(arq, {"herda": "base", "legenda": {"tamanhoo": 0.05}, "x_nota": "anotação livre"})
    with pytest.raises(ErroDA):
        carregar_arquivo(arq)


# ---- validador ------------------------------------------------------------------------------------------

def test_validador_pega_contraste_e_sugere(tmp_path):
    arq = tmp_path / "direcao.yaml"
    salvar_yaml(arq, {"herda": "base", "cor": {"paleta": {"texto": "#2A2D33"}}})
    achados = validar(carregar_arquivo(arq))
    ruins = [a for a in achados if a.codigo == "contraste.texto" and a.nivel == "erro"]
    assert ruins and "#" in ruins[0].como_corrigir


def test_validador_pega_legenda_pequena_e_serie_curta(tmp_path):
    arq = tmp_path / "direcao.yaml"
    salvar_yaml(arq, {"herda": "base", "legenda": {"tamanho": 0.025}, "cor": {"serie": ["primaria", "destaque"]}})
    codigos = {a.codigo for a in validar(carregar_arquivo(arq))}
    assert "legivel.legenda" in codigos and "serie.curta" in codigos


def test_validador_pega_token_inexistente(tmp_path):
    arq = tmp_path / "direcao.yaml"
    salvar_yaml(arq, {"herda": "base", "legenda": {"cor": "roxo_que_nao_existe"}})
    assert any(a.codigo == "token.inexistente" for a in validar(carregar_arquivo(arq)))


# ---- compilação e uso nos estilos -----------------------------------------------------------------------

def test_css_e_build(canal):
    res = servico.compilar(canal.path)
    assert res["erros"] == 0
    css = (canal.path / "arte" / "build" / "da.css").read_text(encoding="utf-8")
    assert "--da-cor-primaria:" in css and "--da-cor-primaria-rgb:" in css and ".da-titulo" in css
    assert (canal.path / "arte" / "DA.md").exists()
    js = json.loads((canal.path / "arte" / "build" / "da.resolvida.json").read_text(encoding="utf-8"))
    assert js


def test_filtro_de_tratamento(tmp_path):
    from clipator.arte.compilar import filtro_tratamento

    arq = tmp_path / "direcao.yaml"
    salvar_yaml(arq, {"herda": "base", "tratamento": {"aplicar_nos_clips": True, "contraste": 1.08,
                                                       "temperatura": 20, "grao": 4, "vinheta": 0.35}})
    f = filtro_tratamento(carregar_arquivo(arq))
    assert "eq=" in f and "colortemperature" in f and "noise" in f and "vignette" in f


def test_estilo_com_tokens_da(canal):
    from clipator.arte.compilar import aplicar_no_estilo
    from clipator.models import Estilo

    _editar(canal.path, cor={"paleta": {"primaria": "#22CC88"}})
    r = servico.carregar(canal.path)
    e = Estilo.model_validate({"nome": "x", "descricao": "y",
                               "legenda": {"da": True, "animacao": "nenhuma", "fonte": "da:titulo"},
                               "cartela": {"cor": "da:texto", "destaque": "da:primaria"}})
    out = aplicar_no_estilo(e, r)
    assert out.legenda.destaque == r.campos["legenda.cor_destaque"]
    assert out.legenda.animacao == "nenhuma"  # o que o estilo escreveu vence
    assert out.legenda.fonte == r.da.tipografia.papeis["titulo"].familia
    assert out.cartela.destaque == "#22CC88"
    assert out.cartela.cor == r.cor("texto")


def test_estilo_so_com_da_sem_canal_usa_o_base():
    from clipator.models import Estilo
    from clipator.render import _estilo_com_da

    est = Estilo.model_validate({"nome": "x", "descricao": "y", "legenda": {"da": True}, "cartela": {"da": True}})
    out = _estilo_com_da(est, None)  # sem DA: valores do predefinido base
    assert out.legenda.cor == carregar_preset("base").campos["legenda.cor"]


def test_para_ficha_vira_ficha_valida(canal):
    from clipator import direcao
    from clipator.arte.compilar import para_ficha

    r = servico.carregar(canal.path)
    f = direcao.ficha("canal", para_ficha(r))
    assert f.primaria == r.cor("primaria")


# ---- identidade ---------------------------------------------------------------------------------------

def test_aprovar_revisar_e_sha(canal):
    from clipator.arte import identidade as I

    r = servico.carregar(canal.path)
    assert not I.situacao(r)["aprovada"]
    servico.aprovar(canal.path)
    r = servico.carregar(canal.path)
    s = I.situacao(r)
    assert s["aprovada"] and not s["alterada_apos_aprovacao"]
    sha_antes = I.sha(r)
    _editar(canal.path, x_lembrete="não muda a identidade")
    assert I.sha(servico.carregar(canal.path)) == sha_antes
    _editar(canal.path, cor={"paleta": {"primaria": "#FF3366"}})
    r = servico.carregar(canal.path)
    assert I.situacao(r)["alterada_apos_aprovacao"]
    assert not servico.conferir(canal.path)["ok"]
    e = servico.revisar(canal.path, "nova primária")
    assert e["revisao"] == 2 and not e["aprovada"]


def test_carimbo_e_conferencia(canal):
    from clipator.arte import identidade as I

    servico.aprovar(canal.path)
    r = servico.carregar(canal.path)
    pasta = canal.path / "projetos" / "p" / "clips" / "c"
    pasta.mkdir(parents=True)
    video = pasta / "saida.mp4"
    video.write_bytes(b"\x00")
    assert I.conferir_carimbos(r, [canal.path / "projetos"])[0]["veredito"] == "sem carimbo"
    I.carimbar(video, r)
    assert I.conferir_carimbos(r, [canal.path / "projetos"])[0]["veredito"] == "em dia"
    assert servico.conferir(canal.path)["ok"]


# ---- lint ---------------------------------------------------------------------------------------------

def test_lint(tmp_path):
    r = carregar_preset("base")
    from clipator.arte.lint import conferir

    p = tmp_path / "x.css"
    p.write_text(".a{color:rgba(var(--da-cor-texto-rgb), .5); background:#123456; border-color: red}\n"
                 ".b{font-family: 'Comic Sans', sans-serif}\n"
                 ".c{color:#FF0000} /* da-livre */\n", encoding="utf-8")
    res = conferir([tmp_path], r, tmp_path)
    tipos = sorted(v.tipo for v in res["violacoes"])
    assert tipos == ["cor literal", "fonte literal", "nome de cor"]
    hexa = next(v for v in res["violacoes"] if v.valor == "#123456")
    assert hexa.coluna == p.read_text().splitlines()[0].index("#123456") + 1
    assert "var(--da-cor-" in hexa.sugestao


def test_lint_sem_arquivos_nao_e_verde(tmp_path):
    from clipator.arte.lint import conferir, texto

    assert "NÃO CONFERIDO" in texto(conferir([], carregar_preset("base")))


# ---- rotas e predefinido pessoal ------------------------------------------------------------------------

def test_rotas_criar_listar_adotar(canal):
    from clipator.arte import rotas
    from clipator.arte.carregar import pasta_do_canal

    pasta = pasta_do_canal(canal.path)
    rotas.criar(pasta, "rota-a", "manchete", "Jornal claro")
    rotas.criar(pasta, "rota-b", "fliperama", "Fliperama", "#00E5FF")
    assert [x["nome"] for x in rotas.listar(pasta)] == ["rota-a", "rota-b"]
    with pytest.raises(ErroDA):
        rotas.criar(pasta, "Rota Ruim")
    res = rotas.adotar(pasta, "rota-b")
    assert res["backup"]
    r = servico.carregar(canal.path)
    assert r.da.herda == "fliperama" and r.cor("primaria") == "#00E5FF"


def test_diferenca_minima():
    from clipator.arte.rotas import diferenca

    assert diferenca({"a": {"b": 1, "c": 2}, "d": [1]}, {"a": {"b": 1, "c": 3}, "d": [1]}) == {"a": {"c": 3}}


def test_salvar_preset_pessoal(canal, tmp_path):
    _editar(canal.path, cor={"paleta": {"primaria": "#AA33FF"}})
    servico.salvar_preset(canal.path, "meu-roxo")
    assert any(p["nome"] == "meu-roxo" for p in listar_presets())
    assert carregar_preset("meu-roxo").cor("primaria") == "#AA33FF"
    with pytest.raises(ErroDA):
        servico.salvar_preset(canal.path, "meu-roxo")


# ---- referências e prancha (imagem sintética, sem internet) ---------------------------------------------

def test_extrair_referencias_de_imagem_sintetica(canal):
    from PIL import Image, ImageDraw

    ref = canal.path / "arte" / "referencias" / "ref.png"
    im = Image.new("RGB", (320, 320), "#101418")
    ImageDraw.Draw(im).rectangle((20, 20, 60, 60), fill="#FF2244")
    im.save(ref)
    res = servico.extrair(canal.path)
    assert res["candidatos"]["fundo"]["hex"]
    assert any(C.delta_e(c["hex"], "#FF2244") < 12 for c in res["candidatos"].values())


def test_prancha_e_comparacao(canal):
    from PIL import Image

    from clipator.arte import rotas
    from clipator.arte.carregar import pasta_do_canal

    info = servico.prancha(canal.path)
    p = Path(info["arquivo"]) if "arquivo" in info else canal.path / "arte" / "prancha.png"
    with Image.open(p) as im:
        assert im.width >= 1200 and im.height > im.width
    pasta = pasta_do_canal(canal.path)
    rotas.criar(pasta, "rota-a", "documental")
    assert rotas.comparar(pasta, com_atual=True).exists()


# ---- CLI e MCP ----------------------------------------------------------------------------------------

def test_cli_arte(tmp_path, capsys):
    from clipator.cli import main

    w = str(tmp_path / "ws")
    assert main(["-w", w, "init"]) == 0
    assert main(["-w", w, "canal", "criar", "Outro Canal"]) == 0
    assert main(["-w", w, "arte", "validar", "outro-canal"]) == 2  # ainda sem DA
    assert main(["-w", w, "arte", "criar", "outro-canal", "--base", "palco-noturno"]) == 0
    assert main(["-w", w, "arte", "validar", "outro-canal"]) == 0
    capsys.readouterr()
    assert main(["-w", w, "arte", "token", "outro-canal", "primaria"]) == 0
    assert "#" in capsys.readouterr().out
    assert main(["-w", w, "arte", "conferir", "outro-canal"]) == 1  # não aprovada
    assert main(["-w", w, "arte", "aprovar", "outro-canal"]) == 0
    assert main(["-w", w, "arte", "conferir", "outro-canal"]) == 0
    with pytest.raises(SystemExit) as exc:
        main(["-w", w, "arte", "token"])
    assert exc.value.code == 64


def test_mcp_arte(tmp_path, monkeypatch):
    import asyncio

    from clipator.mcp_server import criar_servidor
    from clipator.service import Servico

    monkeypatch.setenv("CLIPATOR_WORKSPACE", str(tmp_path / "ws"))
    srv = Servico(nome_fila="jobs-teste")
    srv.ws.criar_canal("Podcast")
    mcp = criar_servidor(srv)
    res = asyncio.run(mcp.call_tool("arte_criar", {"canal": "podcast", "base": "manchete"}))
    assert not res.is_error
    res = asyncio.run(mcp.call_tool("arte_validar", {"canal": "podcast"}))
    assert '"erros": 0' in res.content[0].text or "'erros': 0" in res.content[0].text
    res = asyncio.run(mcp.call_tool("arte_aprovar", {"canal": "podcast"}))
    assert "confirmar" in res.content[0].text
    metodo = asyncio.run(mcp.read_resource("clipator://arte/metodo"))
    assert "Rotas" in str(metodo)


# ---- a DA do estilo guiando o corte ----------------------------------------------------------------------

def _estilo(**extra):
    from clipator.models import Estilo

    return Estilo.model_validate({"nome": "teste", "descricao": "x", **extra})


def test_estilo_sem_arte_nao_usa_da():
    from clipator.arte import guia

    assert guia.da_do_estilo(_estilo(), None) == (None, [])
    assert guia.referencia_do_estilo(_estilo(legenda={"da": True})) == "base"  # usa token: cai na base


def test_estilo_escolhe_a_da_e_o_canal_so_ajusta_a_marca(canal):
    from clipator.arte import guia

    salvar_yaml(canal.path / "arte" / "marca.yaml", {"cores": {"primaria": "#E4002B", "fundo": "#000000"},
                                                     "fontes": {"corpo": "Inter"}, "assinatura": "@teste"})
    r, avisos = guia.da_do_estilo(_estilo(arte="documental"), canal.path)
    doc = carregar_preset("documental")
    assert r.da.nome == doc.da.nome and r.cor("fundo") == doc.cor("fundo")  # o estilo manda
    assert r.da.cenas.intervalo == doc.da.cenas.intervalo
    assert r.cor("primaria") == "#E4002B"  # a marca do canal
    assert r.da.tipografia.papeis["legenda"].familia == "Inter" and r.da.marca.assinatura == "@teste"
    assert any("fundo" in a for a in avisos)  # “fundo” não é cor da marca: ignorada com aviso


def test_cor_da_marca_sem_contraste_e_ajustada(canal):
    from clipator.arte import guia

    salvar_yaml(canal.path / "arte" / "marca.yaml", {"cores": {"destaque": "#FFE45C"}})
    r, avisos = guia.da_do_estilo(_estilo(arte="manchete"), canal.path)  # manchete tem fundo claro
    assert C.contraste(r.cor("destaque"), r.cor("fundo")) >= 3
    assert avisos and "destaque" in avisos[0]


def test_estilo_com_ajustes_proprios_e_arte_canal(canal):
    from clipator.arte import guia

    r, _ = guia.da_do_estilo(_estilo(arte={"herda": "fliperama", "cenas": {"por_minuto": 5}}), canal.path)
    assert r.da.nome == "Fliperama" and r.da.cenas.por_minuto == 5
    r2, _ = guia.da_do_estilo(_estilo(arte="canal"), canal.path)
    assert r2.da.nome == "Canal de teste"
    with pytest.raises(ErroDA):
        guia.da_do_estilo(_estilo(arte="nao-existe"), canal.path)


def test_texto_para_ia_tem_o_guia_e_nao_tem_hex():
    from clipator.arte import guia

    t = guia.texto_para_ia(carregar_preset("caderno-de-aula"))
    assert "Prefira" in t and "lista" in t and "Não use" in t and "alerta" in t
    assert "#" not in t and len(t) <= 2200


def test_filtrar_cenas_pela_da():
    from clipator.arte import guia
    from clipator.direcao import Cena

    r = carregar_preset("caderno-de-aula")  # evita alerta; intervalo 4 s; lista até 3 itens
    cenas = [Cena(inicio=0.5, fim=3, params={"cena": "titulo", "texto": "Como montar a planilha"}),
             Cena(inicio=2, fim=5, params={"cena": "lista", "itens": ["a", "b", "c", "d", "e"]}),
             Cena(inicio=8, fim=9, params={"cena": "alerta", "texto": "cuidado"}),
             Cena(inicio=12, fim=30, params={"cena": "lista", "itens": ["a", "b", "c", "d"]}),
             Cena(inicio=20, fim=22, params={"cena": "titulo", "texto": "um título comprido demais para a tela"})]
    ok, fora = guia.filtrar_cenas(cenas, r, 40)
    assert [c.params["cena"] for c in ok] == ["titulo", "lista"]
    assert ok[0].inicio == 0.5  # o título-gancho do começo tem prioridade
    assert ok[1].fim - ok[1].inicio <= r.da.cenas.duracao[1] and len(ok[1].params["itens"]) == 3
    assert len(fora) == 3 and any("alerta" in f for f in fora)


def test_filtrar_respeita_teto_por_minuto():
    from clipator.arte import guia
    from clipator.direcao import Cena

    r = carregar_preset("documental")  # 6 por minuto, intervalo 6 s
    cenas = [Cena(inicio=t, fim=t + 4, params={"cena": "local", "texto": "Recife"}) for t in range(0, 60, 6)]
    ok, _ = guia.filtrar_cenas(cenas, r, 30)
    assert len(ok) == 3


def test_carimbo_de_estilo_e_conferencia(canal):
    from clipator.arte import guia
    from clipator.arte import identidade as I

    r, _ = guia.da_do_estilo(_estilo(arte="tela-de-dados"), canal.path)
    pasta = canal.path / "projetos" / "p" / "clips" / "c"
    pasta.mkdir(parents=True)
    video = pasta / "saida.mp4"
    video.write_bytes(b"\x00")
    I.carimbar(video, r, arte="tela-de-dados")
    res = I.conferir_carimbos(None, [canal.path / "projetos"], lambda ref: guia.da_da_referencia(ref, canal.path)[0])
    assert res[0]["veredito"] == "em dia"
    salvar_yaml(canal.path / "arte" / "marca.yaml", {"cores": {"primaria": "#22AA55"}})  # a marca mudou
    res = I.conferir_carimbos(None, [canal.path / "projetos"], lambda ref: guia.da_da_referencia(ref, canal.path)[0])
    assert res[0]["veredito"] == "DA diferente"


def test_conferir_canal_sem_da_propria(ws):
    c = ws.criar_canal("Sem DA")
    res = servico.conferir(c.path)
    assert res["ok"] and res["situacao"] == {}


def test_cli_guia_e_marca(tmp_path, capsys):
    from clipator.cli import main

    w = str(tmp_path / "ws")
    assert main(["-w", w, "init"]) == 0
    assert main(["-w", w, "canal", "criar", "Guia"]) == 0
    assert main(["-w", w, "arte", "marca", "guia", "--criar"]) == 0
    assert (tmp_path / "ws" / "canais" / "guia" / "arte" / "marca.yaml").exists()
    estilos = tmp_path / "ws" / "canais" / "guia" / "estilos"
    estilos.mkdir(parents=True, exist_ok=True)
    (estilos / "com-da.md").write_text("---\nnome: com-da\ndescricao: x\narte: manchete\nlegenda:\n  da: true\n---\n",
                                       encoding="utf-8")
    capsys.readouterr()
    assert main(["-w", w, "arte", "guia", "guia", "com-da"]) == 0
    out = capsys.readouterr().out
    assert "Manchete" in out and "O que a IA recebe" in out
    assert main(["-w", w, "arte", "prancha", "guia", "--estilo", "com-da"]) == 0
    assert (tmp_path / "ws" / "canais" / "guia" / "arte" / "build" / "prancha-com-da.png").exists()
    assert main(["-w", w, "arte", "guia", "guia", "nao-existe"]) == 1


def test_editor_planeja_com_o_guia_da_da_e_filtra(ws):
    from clipator import edicao
    from clipator.models import Clip, Origem
    from clipator.timeline import Timeline

    class IA:
        nome = "falsa"

        def __init__(self, resposta):
            self.resposta, self.prompts = resposta, []

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None, *a, **k):
            self.prompts.append(prompt)
            return self.resposta

    fala = "Primeiro, corte os gastos. Segundo, venda o carro. Cuidado com golpe na internet agora mesmo."
    pals, t = [], 0.2
    for w in fala.split():
        pals.append({"texto": w, "inicio": round(t, 2), "fim": round(t + 0.3, 2)})
        t += 0.4
    c = ws.criar_canal("Guiado")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    pr.salvar_clip(Clip(id="01-x", inicio=0, fim=20, titulo="Corte de gastos", estilo="da-animacao-em-cima",
                        ajustes_estilo={"arte": "caderno-de-aula"}))
    clip, _ = pr.clip("01-x")
    vazio = {"texto": "", "itens": [], "valor": "", "rotulo": "", "autor": "", "a": "", "b": "", "motivo": "x"}
    ia = IA({"cenas": [{**vazio, "cena": "lista", "ancora": "Primeiro, corte os gastos.", "itens": ["cortar", "vender"],
                        "duracao": 4},
                       {**vazio, "cena": "alerta", "ancora": "Cuidado com golpe na internet", "texto": "golpe",
                        "duracao": 3}]})
    cenas, aviso = edicao.cenas_sugeridas(pr, clip, Timeline.de_clip(0, 20), pals, ia)
    assert ia.prompts and "Caderno de aula" in ia.prompts[0] and "Não use" in ia.prompts[0]
    assert [i.params["cena"] for i in cenas] == ["lista"]  # o alerta não combina com o caderno de aula


def test_render_final_usa_a_da_do_estilo_e_carimba(ws, video_teste, monkeypatch):
    if not __import__("shutil").which("ffmpeg"):
        pytest.skip("FFmpeg não instalado")
    from clipator import hyperframes, melhorar, pipeline, transcribe
    from clipator.models import Origem

    from .conftest import WhisperFalso, transcricao_falsa

    class IA:
        nome = "falsa"

        def __init__(self):
            self.prompts = []

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None, *a, **k):
            from .conftest import direcao_de_roteiro, e_pedido_de_direcao

            self.prompts.append(prompt)
            if prompt.startswith("Analise este corte"):
                return {"tema": "dinheiro", "ideias": []}
            if e_pedido_de_direcao(prompt):
                primeira = prompt.split("## Fala com tempos\n")[-1].split()[:4]
                self.ancora = " ".join(w.split("]", 1)[-1] for w in primeira)
            ancora = getattr(self, "ancora", "")
            if e_pedido_de_direcao(prompt):
                return direcao_de_roteiro({"cenas": [{"ancora": ancora, "etiqueta": "o dado", "descricao": "o número"}]})
            return {"cenas": [{"cena": "lista", "ancora": ancora, "texto": "", "itens": ["segredo", "simples"], "valor": "", "rotulo": "",
                               "autor": "", "a": "", "b": "", "duracao": 3, "motivo": "ilustra"}]}

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    monkeypatch.setattr(hyperframes, "comando", lambda: None)
    ia = IA()
    monkeypatch.setattr(melhorar, "ia_do_workspace", lambda ws, esperar_login=None: ia)
    c = ws.criar_canal("Render DA", palavras_chave=["dinheiro"])
    regras = c.arquivo("regras.md")
    regras.write_text(regras.read_text().replace("duracao_min: 40", "duracao_min: 5").replace("duracao_max: 180", "duracao_max: 12"))
    salvar_yaml(c.path / "arte" / "marca.yaml", {"cores": {"primaria": "#E4002B"}})
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="da-video-na-janela")[0]
    p.salvar_clip(clip.model_copy(update={"ajustes_estilo": {"arte": "tela-de-dados"}}))
    r = pipeline.renderizar(p, clip.id, preview=False)
    assert ia.prompts and "Tela de dados" in ia.prompts[0]
    carimbo = json.loads(r.video.with_name(r.video.name + ".arte.json").read_text(encoding="utf-8"))
    assert carimbo["arte"] == "tela-de-dados" and carimbo["da"] == "Tela de dados" and carimbo["aprovada"] is None
    assert servico.conferir(c.path)["ok"]
    salvar_yaml(c.path / "arte" / "marca.yaml", {"cores": {"primaria": "#2255EE"}})  # a marca mudou depois
    assert not servico.conferir(c.path)["ok"]


# ---- importar especificações de direção visual ------------------------------------------------------------

SPEC = {
    "id": "clipator-arte-teste-importada", "nome": "Teste importada", "familia": "Texto editorial",
    "usar_em": "definições, argumento central e conclusão", "complexidade": "baixa",
    "conceito": "Uma frase aparece numa folha clara.",
    "composicao": "Bloco de até três linhas; margem para nota. A linha ativa ganha faixa.",
    "material_e_luz": "Papel claro e tinta uniforme.",
    "movimento": "Revelar por grupos e depois desenhar o colchete.",
    "fases": ["Revelar", "Marcar"], "criterios": ["A faixa não reduz o contraste."],
    "evitar": "Parágrafo longo, tarja sem função e legenda duplicada.",
    "cores": {"fundo": "#F3EEDF", "superficie": "#E0D8C5", "texto": "#263938", "texto_suave": "#8A9894",
              "primaria": "#D9A090", "destaque": "#B5C876"},
    "fontes": {"titulo": "Bebas Neue", "corpo": "Montserrat ExtraBold"},
    "som": {"entrada": "click", "conclusao": "ding", "volume_relativo": 0.2},
    "backend_sugerido": "svg",
}


def test_importar_corrige_contraste_e_guarda_anotacoes(tmp_path):
    from clipator.arte.importar import de_especificacao

    dados, notas = de_especificacao(SPEC)
    assert notas  # texto suave, primária e destaque precisaram de ajuste
    salvar_yaml(tmp_path / "direcao.yaml", dados)
    r = carregar_arquivo(tmp_path / "direcao.yaml")
    p = r.da.cor.paleta
    assert C.contraste(p["texto_suave"], p["fundo"]) >= 4.5 and C.contraste(p["primaria"], p["fundo"]) >= 3
    assert p["realce"] == "#B5C876"  # a cor original do destaque segue disponível para o grifo
    assert r.da.movimento.entrada == "mascara" and r.da.cenas.intervalo == 3.0
    assert r.da.conceito.nao_faca == ["Parágrafo longo.", "Tarja sem função.", "Legenda duplicada."]
    assert dados["x_direcao"]["backend_sugerido"] == "svg"
    e, a, _ = resumo(validar(r))
    assert (e, a) == (0, 0)


def test_cli_importar(tmp_path):
    from clipator.cli import main

    arq = tmp_path / "especificacao.json"
    arq.write_text(json.dumps(SPEC, ensure_ascii=False), encoding="utf-8")
    assert main(["-w", str(tmp_path / "ws"), "arte", "importar", str(arq)]) == 0
    assert carregar_preset("teste-importada").da.nome == "Teste importada"
    assert main(["-w", str(tmp_path / "ws"), "arte", "importar", str(arq)]) == 1  # já existe


def test_as_22_direcoes_viraram_predefinidos():
    nomes = {p["nome"] for p in listar_presets()}
    for n in ("anotacao-em-foco", "oficina-modular", "cidade-de-bolso", "tinta-em-etapas", "atlas-de-percursos"):
        assert n in nomes
    r = carregar_preset("anotacao-em-foco")
    assert r.da.tipografia.papeis["titulo"].familia == "Bebas Neue"
