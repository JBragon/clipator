"""Análise por assuntos (modo completo): a IA entende a conversa inteira e os títulos vêm com prova na fala."""

from __future__ import annotations

from clipator import pipeline
from clipator.ai import assuntos, ranking
from clipator.models import Origem, Regras
from clipator.transcribe import palavras as _palavras

from .conftest import precisa_ffmpeg, transcricao_falsa

REGRAS = Regras(duracao_min=15, duracao_max=40, corte_longo_min=120, corte_longo_max=600)


class IAFalsa:
    nome = "falsa"

    def __init__(self, resposta):
        self.resposta = resposta
        self.prompts: list[str] = []

    def run_json(self, prompt, schema, cancelar=None):
        self.prompts.append(prompt)
        return self.resposta(prompt, schema)


def _trans():
    return transcricao_falsa(duracao=36.0, repetir=8)  # ~290 s de conversa


def _resposta(trans):
    pals = _palavras(trans)

    def t(x):  # o começo da palavra mais perto de x
        return min(pals, key=lambda w: abs(w["inicio"] - x))["inicio"]

    def r(prompt, schema):
        if schema is assuntos.SCHEMA_EDITOR:
            return {"assuntos": [{"id": "a01", "nota": 91, "motivo": "o mais forte do episódio"},
                                 {"id": "a02", "nota": 40, "motivo": "repete o a01"}],
                    "longos": [{"de": "a01", "ate": "a02", "nota": 88, "thumb": "FOI O PIOR ERRO DA MINHA VIDA",
                                "motivo": "uma história só",
                                "titulos": [{"titulo": "EMPRESÁRIO REVELA COMO PERDEU MEIO MILHÃO | Fulano no Podcast",
                                             "prova": "Eu perdi quinhentos mil reais em um ano investindo errado"},
                                            {"titulo": "EMPRESÁRIO COMPROU UMA FERRARI", "prova": "comprei uma ferrari vermelha ontem"}]}]}
        if schema is assuntos.SCHEMA_MAPA:
            return {"fio": "Fulano, empresário, conta como perdeu dinheiro.", "convidado": "Fulano, empresário",
                    "assuntos": [
                        {"inicio": t(5), "fim": t(140), "assunto": "o prejuízo de meio milhão", "tese": "foi o pior erro da minha vida",
                         "angulo": "história pessoal com número chocante", "gatilhos": ["historia", "numero", "inventado"],
                         "contexto": "", "nota": 85, "short": {"inicio": t(40), "fim": t(75)},
                         "trecho_forte": {"inicio": t(60), "fim": t(74), "frase": "pior erro"},
                         "titulos": [{"titulo": "EMPRESÁRIO PERDEU 500 MIL EM UM ANO", "prova": "Eu perdi quinhentos mil reais em um ano"},
                                     {"titulo": "EMPRESÁRIO GANHOU NA LOTERIA", "prova": "ganhei na loteria duas vezes seguidas"}],
                         "thumb": "PERDI MEIO MILHÃO"},
                        {"inicio": t(150), "fim": t(280), "assunto": "a lição", "tese": "nunca coloque tudo num lugar só",
                         "angulo": "conselho prático", "gatilhos": ["conselho"], "contexto": "depois do prejuízo", "nota": 60,
                         "short": {"inicio": t(180), "fim": t(210)}, "trecho_forte": {"inicio": t(190), "fim": t(203), "frase": "x"},
                         "titulos": [{"titulo": "NUNCA COLOQUE TUDO NUM LUGAR SÓ", "prova": "nunca coloque tudo num lugar só"}],
                         "thumb": "NUNCA FAÇA ISSO"},
                        {"inicio": 9999, "fim": 10100, "assunto": "fora do vídeo", "tese": "", "angulo": "", "gatilhos": [],
                         "contexto": "", "nota": 99, "short": {"inicio": 0, "fim": 1}, "trecho_forte": {"inicio": 0, "fim": 1, "frase": ""},
                         "titulos": [], "thumb": ""},
                    ]}
        return None
    return r


def test_prova_confere_com_a_fala():
    texto = "Pois é. Eu perdi quinhentos mil reais em um ano investindo errado. O segredo é simples."
    assert assuntos.prova_confere("eu perdi quinhentos mil reais em um ano", texto)
    assert assuntos.prova_confere("perdi 500... quinhentos mil reais num ano investindo errado", texto)  # transcrição imperfeita
    assert not assuntos.prova_confere("comprei uma ferrari vermelha ontem", texto)
    assert not assuntos.prova_confere("perdi", texto)  # curta demais para provar algo


def test_mapa_leva_o_fio_de_um_bloco_para_o_outro():
    trans = transcricao_falsa(duracao=36.0, repetir=40)  # ~24 min: dois blocos
    vistos = []

    def r(prompt, schema):
        vistos.append(prompt)
        return {"fio": f"FIO-DO-BLOCO-{len(vistos)}", "convidado": "Fulano", "assuntos": []}

    meta = {"titulo": "FULANO - Podcast #1", "canal": "Podcast", "descricao": "Episódio sobre dinheiro",
            "capitulos": [{"inicio": 0, "fim": 600, "titulo": "O PIOR ERRO da vida"}]}
    mapa = assuntos.mapear(trans, IAFalsa(r), REGRAS, "## Canal\nx", "regra", meta)
    assert len(vistos) == 2
    assert "(começo do episódio)" in vistos[0] and "FIO-DO-BLOCO-1" in vistos[1]
    assert "FULANO - Podcast #1" in vistos[0] and "[0] O PIOR ERRO da vida" in vistos[0]
    assert "Sem prova, sem título" in vistos[0] and "contradição" in vistos[0]
    assert mapa["fio"] == "FIO-DO-BLOCO-2" and mapa["convidado"] == "Fulano"


def test_assuntos_viram_shorts_e_cortes_longos_com_titulos_provados():
    trans = _trans()
    ia = IAFalsa(_resposta(trans))
    mapa = assuntos.mapear(trans, ia, REGRAS, "", "regra")
    assert [s["id"] for s in mapa["assuntos"]] == ["a01", "a02"]  # o de fora do vídeo caiu
    a01 = mapa["assuntos"][0]
    assert a01["titulos"] == ["EMPRESÁRIO PERDEU 500 MIL EM UM ANO"]  # o da loteria não tem prova
    assert a01["gatilhos"] == ["historia", "numero"] and a01["trecho_forte"]
    editor = assuntos.editar(mapa, ia, REGRAS, "")
    assert "a01" in ia.prompts[-1] and "foi o pior erro da minha vida" in ia.prompts[-1]
    curtos, longos = assuntos.candidatos(mapa, editor, trans, REGRAS, "falsa")
    assert len(curtos) == 2
    c1 = next(c for c in curtos if c["ia"]["assunto"] == "o prejuízo de meio milhão")
    assert c1["nota"] == 91 and REGRAS.duracao_min - 3 <= c1["duracao"] <= REGRAS.teto_curto() + 1
    assert c1["ia"]["gancho"] == "PERDI MEIO MILHÃO" and c1["fonte"] == "ia-assuntos"
    assert len(longos) == 1
    lg = longos[0]
    assert lg["modo"] == "longo" and lg["inicio"] <= a01["inicio"] + 1 and lg["fim"] >= mapa["assuntos"][1]["fim"] - 1
    assert lg["titulos"] == ["EMPRESÁRIO REVELA COMO PERDEU MEIO MILHÃO | Fulano no Podcast"]  # a Ferrari caiu
    assert lg["ia"]["abertura"] == [a01["trecho_forte"]]


def test_ranking_descarta_titulo_sem_prova_e_ve_o_assunto():
    trans = _trans()
    pals = _palavras(trans)
    c = {"id": "c01", "inicio": pals[0]["inicio"], "fim": pals[60]["fim"], "duracao": pals[60]["fim"] - pals[0]["inicio"],
         "nota": 80.0, "texto": " ".join(w["texto"] for w in pals[:61]), "titulos": ["DO MAPA"],
         "ia": {"assunto": "o prejuízo", "tese": "foi o pior erro", "contexto": ""}}
    ia = IAFalsa(lambda p, s: {"candidatos": [{"id": "c01", "nota": 60, "gancho": "", "ajuste_inicio": 0, "ajuste_fim": 0,
                                                "fecha_assunto": True, "motivo": "m", "destaques": [],
                                                "titulos": [{"titulo": "ELE PERDEU MEIO MILHÃO", "prova": "Eu perdi quinhentos mil reais em um ano"},
                                                            {"titulo": "ELE FICOU RICO", "prova": "fiquei rico com bitcoin em uma semana"}]}]})
    out = ranking.ranquear([c], trans, ia, REGRAS, fio="Fulano, empresário")[0]
    assert "assunto: o prejuízo | tese: foi o pior erro" in ia.prompts[0] and "Fulano, empresário" in ia.prompts[0]
    assert out["titulos"] == ["ELE PERDEU MEIO MILHÃO", "DO MAPA"]
    assert out["nota"] == 70.0 and out["ia"]["assunto"] == "o prejuízo"


@precisa_ffmpeg
def test_modo_completo_no_pipeline_guarda_o_mapa_e_mantem_os_clips(ws, video_teste, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    trans = _trans()
    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(trans))
    c = ws.criar_canal("Teste")
    md = c.arquivo("regras.md")
    md.write_text(md.read_text().replace("duracao_min: 40", "duracao_min: 15").replace("corte_longo_min: 480", "corte_longo_min: 120")
                  .replace("duracao_max: 180", "duracao_max: 40"))
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia", corte_longo=False)
    assert c.regras()[0].corte_longo_min == 120
    clip = pipeline.selecionar(p, [cands[0]["id"]])[0]
    resposta = _resposta(trans)

    def r(prompt, schema):
        if schema is ranking.SCHEMA_RANKING:
            return {"candidatos": []}
        if schema is ranking.SCHEMA_LONGO:
            return None
        return resposta(prompt, schema)

    ia = IAFalsa(r)
    ia.disponivel = lambda: True
    monkeypatch.setattr(pipeline, "adaptador_com_reserva", lambda *a, **k: ia)
    out = pipeline.ranquear(p, modo_ia="completo")
    assert (p.analise_dir / "assuntos.json").exists()
    assert any(x.get("fonte") == "ia-assuntos" for x in out)
    assert any(x.get("modo") == "longo" and (x.get("ia") or {}).get("abertura") for x in out)
    assert clip.candidato in {x["id"] for x in out}  # o clip continua achando o corte dele
    assert len({x["id"] for x in out}) == len(out)
    # o ranking seguinte, mesmo no econômico, recebe o resumo do episódio
    pipeline.ranquear(p, modo_ia="economico")
    assert "Fulano, empresário" in ia.prompts[-1]
