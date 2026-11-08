"""Base de referência dos cortes virais (dados/base-virais/), pasta regras-e-textos/ e temperatura dos títulos."""

from __future__ import annotations

from clipator import base_virais, titles
from clipator import markdown as md
from clipator.models import Regras, Thumb
from clipator.workspace import (
    ARQUIVOS_TEXTOS,
    FORMULAS_PADRAO,
    PASTA_TEXTOS,
    referencias_para_ia,
    write_json,
)

FUTEBOL = ("O Flamengo perdeu nos pênaltis e o goleiro falou do técnico. A torcida no estádio cantou contra o time, "
           "o atacante perdeu o gol e o campeonato acabou. O jogador do Flamengo disse que a seleção ") * 3
POLITICA = ("O presidente Lula falou com o ministro do STF e o deputado do partido pediu CPI no Congresso. "
            "A eleição e o voto do senador ") * 3


def test_canal_novo_tem_a_pasta_regras_e_textos(ws):
    c = ws.criar_canal("Meu Canal")
    pasta = c.path / PASTA_TEXTOS
    for nome in ("LEIA-ME.md", *ARQUIVOS_TEXTOS):
        assert (pasta / nome).exists(), nome
    for nome in ARQUIVOS_TEXTOS:
        assert not (c.path / nome).exists()  # nada solto na raiz do canal
    tmeta, _ = c.titulos()
    assert tmeta["temperatura"] == "auto" and tmeta["formulas"] == []
    assert c.thumb()[0].citacao is True
    nomes = [a.name for a in c.arquivos_textos()]
    assert nomes[:2] == ["canal.md", "LEIA-ME.md"] and "referencias.md" in nomes
    assert referencias_para_ia(c.referencias()) == ""  # só o exemplo "(cole aqui...)": nada vai para a IA


def test_a_base_e_valida():
    temas = base_virais.temas()
    assert base_virais.GERAL in temas and len(temas) >= 8
    meta = md.read(base_virais.base_dir() / "titulos.md").meta
    for tid, t in temas.items():
        assert t["nome"] and t["temperatura"] in titles.TEMPERATURAS
        assert tid == base_virais.GERAL or t["palavras"], tid
        formulas = [f for lista in meta["formulas"][tid].values() for f in lista]
        assert len(formulas) >= 5, tid
        for f in formulas:  # só as variáveis que o motor conhece
            f.format(tema="x", nome="y", numero="1", verbo="FALA")
        for arq in ("cortes.md", "titulos.md", "thumbs.md", "referencias.md"):
            assert tid in base_virais.secoes(arq), f"{arq}: {tid}"
    for arq in ("regras.md", "thumb.md"):
        doc = md.read(base_virais.base_dir() / "modelo-canal" / arq)
        (Regras if arq == "regras.md" else Thumb).model_validate(doc.meta)


def test_detecta_o_tema_pela_fala():
    assert base_virais.detectar(FUTEBOL)[0] == "esporte"
    assert base_virais.detectar(POLITICA)[0] == "politica"
    assert base_virais.detectar("Oi gente, tudo bem? Hoje a conversa é boa.") == []
    # um tema citado de passagem não entra
    assert base_virais.detectar(POLITICA * 3 + " o Flamengo ganhou") == ["politica"]


def test_titulos_efetivos_seguem_o_tema_e_o_canal_manda():
    ef = base_virais.titulos_efetivos({"temperatura": "auto", "formulas": ["minha {tema}"]}, ["humor"])
    assert ef["temperatura"] == "fervendo" and ef["caixa_alta_total"] is True
    formulas = titles.formulas_do_canal(ef)
    assert formulas[0] == "minha {tema}" and len(formulas) > 10
    assert ef["temas"][0].startswith("Humor") and ef["nunca_usar"]
    fixo = base_virais.titulos_efetivos({"temperatura": "morno", "caixa_alta_total": False}, ["humor"])
    assert fixo["temperatura"] == "morno" and fixo["caixa_alta_total"] is False
    # canal antigo: as 10 fórmulas genéricas vão para o fim
    antigo = titles.formulas_do_canal(base_virais.titulos_efetivos({"formulas": FORMULAS_PADRAO, "temperatura": "morno"}, []))
    assert antigo[0] not in FORMULAS_PADRAO and FORMULAS_PADRAO[0] in antigo


def test_projeto_usa_a_base_do_tema_do_video(ws):
    c = ws.criar_canal("Misto")
    p = c.criar_projeto("Jogo")
    write_json(p.transcricao_path, {"segmentos": [{"inicio": 0, "fim": 60, "texto": FUTEBOL}]})
    assert p.temas() == ["esporte"]
    tmeta, _ = p.titulos()
    assert tmeta["temperatura"] == "quente" and "Futebol" in tmeta["temas"][0]
    texto = p.base_para_ia()
    assert "Base de referência do Clipator" in texto and "(esporte)" not in texto
    assert "Futebol e esportes" in texto and "Podcast, entrevista" in texto
    tits = titles.titulos_locais(FUTEBOL, titles.formulas_do_canal(tmeta))
    assert tits and all(len(t) <= 70 for t in tits)


def test_canal_antigo_migra_os_arquivos_para_a_pasta(ws):
    c = ws.criar_canal("Antigo")
    for nome in ("regras.md", "titulos.md", "thumb.md", "referencias.md", "LEIA-ME.md"):
        (c.path / PASTA_TEXTOS / nome).unlink()
    (c.path / "regras.md").write_text("---\nduracao_max: 45\n---\nregra minha\n", encoding="utf-8")
    c2 = ws.canal("antigo")
    assert (c2.path / PASTA_TEXTOS / "regras.md").exists() and not (c2.path / "regras.md").exists()
    assert (c2.path / PASTA_TEXTOS / "LEIA-ME.md").exists() and (c2.path / PASTA_TEXTOS / "referencias.md").exists()
    regras, corpo = c2.regras()
    assert regras.duracao_max == 45 and "regra minha" in corpo


def test_migracao_nao_sobrescreve_o_que_ja_esta_na_pasta(ws):
    c = ws.criar_canal("Dois")
    (c.path / "regras.md").write_text("---\nduracao_max: 30\n---\n", encoding="utf-8")
    c2 = ws.canal("dois")
    assert (c2.path / "regras.md").exists()  # ficou onde estava
    assert c2.regras()[0].duracao_max == 60  # vale o da pasta nova


def test_temperatura_ordena_as_formulas():
    tmeta = {"formulas": ["minha {tema}"], "temperatura": "fervendo",
             "formulas_por_temperatura": {"morno": ["m {tema}"], "quente": ["q {tema}"], "fervendo": ["f {tema}"]}}
    assert titles.formulas_do_canal(tmeta) == ["minha {tema}", "f {tema}", "q {tema}"]
    tmeta["temperatura"] = "morno"
    assert titles.formulas_do_canal(tmeta) == ["minha {tema}", "m {tema}"]
    assert titles.formulas_do_canal({"formulas": ["a", "a"]}) == ["a"]


def test_contexto_da_ia_leva_tema_temperatura_e_gatilhos():
    from clipator.ai.ranking import _contexto_canal

    ctx = _contexto_canal("", "", "", Regras(), {"temperatura": "quente", "formulas": ["X {tema}"], "temas": ["Humor"],
                                                 "palavras_gatilho": ["REVELA"], "nunca_usar": ["você não vai acreditar"]})
    assert "Temperatura dos títulos: quente" in ctx and "REVELA" in ctx and "você não vai acreditar" in ctx
    assert "Tema do vídeo: Humor" in ctx


def test_api_lista_os_textos_do_canal(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    cli = TestClient(criar_app(Servico(tmp_path / "ws"), token="t"))
    h = {"x-clipator-token": "t"}
    r = cli.post("/api/canais", json={"nome": "Futebol"}, headers=h)
    assert r.status_code == 200, r.text
    textos = cli.get("/api/canais/futebol/textos", headers=h).json()
    assert [t["nome"] for t in textos][:2] == ["canal.md", "LEIA-ME.md"]
    assert any(t["caminho"] == "canais/futebol/regras-e-textos/titulos.md" for t in textos)
