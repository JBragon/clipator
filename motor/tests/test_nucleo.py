"""Testes das partes puras: markdown, workspace, timeline, candidatos, títulos, legendas e validação."""

from __future__ import annotations

import types

import pytest

from clipator import candidates, markdown as md, subtitles, titles, transcribe, validacao
from clipator.ingest import IngestaoError, validar_link
from clipator.models import Cartela, Estilo, Legenda, Regras
from clipator.timeline import Timeline

from .conftest import transcricao_falsa


# ---- markdown ---------------------------------------------------------------
def test_markdown_ida_e_volta():
    doc = md.loads(md.dumps({"formato": "9:16", "legenda": {"cor": "#FFF"}}, "Corpo livre.\n"))
    assert doc.meta["legenda"]["cor"] == "#FFF"
    assert doc.body.strip() == "Corpo livre."


def test_markdown_sem_cabecalho():
    assert md.loads("só texto").meta == {}


def test_markdown_erro_tem_linha():
    with pytest.raises(md.FrontMatterError) as e:
        md.loads("---\na: [1, 2\n---\n")
    assert e.value.line is not None


def test_deep_merge_cascata():
    assert md.deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


# ---- workspace ----------------------------------------------------------------
def test_workspace_canal_projeto(ws):
    c = ws.criar_canal("Podcast do Jordan", palavras_chave=["dinheiro"])
    assert c.slug == "podcast-do-jordan"
    info, _ = c.info()
    assert info.palavras_chave == ["dinheiro"]
    regras, _ = c.regras()
    assert regras.duracao_max == 180 and regras.trava_titulo is True and regras.censor_leetspeak is False
    p = c.criar_projeto("Ep 12")
    assert p.meta().etapas["transcricao"].status == "pendente"
    p2 = c.criar_projeto("Ep 12")
    assert p2.id != p.id
    with pytest.raises(Exception):
        ws.criar_canal("Podcast do Jordan")


def test_workspace_recusa_sair_da_pasta(ws):
    with pytest.raises(Exception):
        ws.dentro("../fora.txt")


def test_estilos_embutidos_validos(ws):
    estilos = ws.estilos()
    assert len(estilos) >= 17  # 16 do MVP + corte longo
    for nome in estilos:
        est, corpo, _ = ws.carregar_estilo(nome)
        assert isinstance(est, Estilo)
        assert est.descricao, nome
        assert corpo.strip(), nome


def test_estilo_do_canal_sobrescreve(ws):
    c = ws.criar_canal("X")
    md.write(c.path / "estilos" / "impacto.md", {"nome": "Meu impacto", "formato": "1:1"}, "corpo")
    est, _, _ = ws.carregar_estilo("impacto", c)
    assert est.formato == "1:1"
    est, _, _ = ws.carregar_estilo("impacto", c, {"legenda": {"cor": "#00FF00"}})
    assert est.legenda.cor == "#00FF00"


# ---- timeline ------------------------------------------------------------------
def test_timeline_cortes_internos():
    tl = Timeline.de_clip(10, 30, [(15, 17), (20, 21)])
    assert tl.trechos == ((10, 15), (17, 20), (21, 30))
    assert tl.duracao == pytest.approx(17)
    assert tl.para_clip(16) is None
    assert tl.para_clip(18) == pytest.approx(6)
    assert tl.para_original(6) == pytest.approx(18)
    assert tl.mapear_intervalo(14, 18) == pytest.approx((4, 6))


def test_timeline_corte_total_falha():
    with pytest.raises(ValueError):
        Timeline.de_clip(10, 20, [(5, 25)])


# ---- candidatos -----------------------------------------------------------------
def test_frases_quebram_em_pontuacao():
    pals = transcribe.palavras(transcricao_falsa())
    frases = candidates.montar_frases(pals)
    assert frases[0].texto.startswith("Ninguém te conta")
    assert frases[0].pontuada


def _transcricao_de(frases: list[tuple[str, float]], wps: float = 2.6) -> dict:
    """Transcrição com tempos por palavra a partir de (frase, pausa depois em segundos)."""
    segs, t = [], 0.5
    for texto, pausa in frases:
        palavras = []
        for w in texto.split():
            palavras.append({"texto": w, "inicio": round(t, 3), "fim": round(t + 0.8 / wps, 3), "prob": 0.9})
            t += 1 / wps
        segs.append({"inicio": palavras[0]["inicio"], "fim": palavras[-1]["fim"], "texto": texto, "palavras": palavras})
        t += pausa
    return {"idioma": "pt", "duracao": round(t + 1, 3), "segmentos": segs}


HISTORIA = [
    ("Eu vou te contar a história de como eu quase quebrei com a minha primeira empresa de tecnologia.", 0.3),
    ("A gente tinha cinco funcionários e um único cliente grande que pagava quase todas as contas.", 0.3),
    ("Durante dois anos eu achei que estava tudo bem porque o dinheiro entrava todo mês sem atraso.", 0.3),
    ("Os sócios falavam que era arriscado mas eu sempre respondia que o cliente era fiel demais.", 0.3),
    ("Até que numa segunda feira chegou um email cancelando o contrato inteiro de uma vez.", 0.3),
    ("E sabe qual foi o maior erro que eu cometi naquela época toda?", 0.4),
    ("O erro foi colocar a empresa inteira na mão de um cliente só, sem nenhum plano para o dia ruim.", 0.3),
    ("Por isso hoje eu digo para todo mundo: nunca dependa de um cliente só, nem que ele seja o maior.", 1.3),
    ("Mudando de assunto, ontem eu fui ao mercado e o preço do café estava um absurdo completo.", 0.3),
    ("O quilo do café passou de quarenta reais e a fila do caixa estava enorme naquela tarde.", 0.3),
    ("A moça do caixa disse que o café vai subir mais ainda até o fim do ano que vem.", 0.3),
    ("Eu comprei só um pacote pequeno e fui embora pensando no preço das coisas hoje em dia.", 1.0),
]


def _frase_final(c: dict, trans: dict) -> str:
    return next(s["texto"] for s in trans["segmentos"] if abs(s["palavras"][-1]["fim"] - c["fim"]) < 0.6)


def test_corte_inclui_a_resposta_da_pergunta():
    trans = _transcricao_de(HISTORIA)
    regras = Regras(duracao_min=15, duracao_max=30, duracao_max_fechamento=45)
    cands = candidates.gerar(trans, None, {}, regras, ["erro", "cliente"])
    assert cands
    for c in cands:
        assert not c["texto"].rstrip().endswith("?"), c["texto"][-80:]  # nunca termina na pergunta
        if "maior erro que eu cometi" in c["texto"]:
            assert "colocar a empresa inteira" in c["texto"]  # a resposta vem junto


def test_corte_termina_na_conclusao_e_antes_de_mudar_de_assunto():
    trans = _transcricao_de(HISTORIA)
    regras = Regras(duracao_min=15, duracao_max=30, duracao_max_fechamento=45)
    cands = candidates.gerar(trans, None, {}, regras, ["erro", "cliente"])
    da_historia = [c for c in cands if "cliente" in c["texto"] and "café" not in c["texto"]]
    assert da_historia
    melhor = max(da_historia, key=lambda c: c["nota"])
    assert _frase_final(melhor, trans).startswith("Por isso hoje eu digo")
    assert melhor["sinais"]["fechamento"] >= 0.7
    assert not any("cliente" in c["texto"] and "Mudando de assunto" in c["texto"] for c in cands[:3])


def test_corte_nunca_termina_no_meio_da_frase():
    trans = _transcricao_de([(t, 0.15) for t, _ in HISTORIA[:8]] + [("Fim da história.", 1.0)])
    regras = Regras(duracao_min=10, duracao_max=25, duracao_max_fechamento=40)
    for c in candidates.gerar(trans, None, {}, regras):
        ultima = _frase_final(c, trans)
        assert ultima.rstrip()[-1] in ".!…", ultima


def test_short_passa_do_maximo_so_para_fechar_o_assunto():
    trans = _transcricao_de(HISTORIA)
    regras = Regras(duracao_min=15, duracao_max=30, duracao_max_fechamento=45)
    cands = candidates.gerar(trans, None, {}, regras)
    assert all(c["duracao"] <= 45 + 1 for c in cands)
    assert all(c["sinais"]["fechamento"] >= 0.7 for c in cands if c["duracao"] > 30 + 1)


def test_ajuste_da_ia_vai_para_fronteira_de_frase():
    trans = _transcricao_de(HISTORIA)
    frases = candidates.montar_frases(transcribe.palavras(trans))
    pergunta = next(f for f in frases if f.texto.endswith("?"))
    resposta = frases[frases.index(pergunta) + 1]
    ini, fim = candidates.ajustar_a_frases(frases[2].inicio + 1.3, pergunta.fim + 0.2, frases, 60)
    assert ini == frases[2].inicio  # começo de frase
    assert fim in (resposta.fim, frases[frases.index(resposta) + 1].fim)  # não para na pergunta


# ---- glossário do canal -------------------------------------------------------
def test_glossario_corrige_nome_e_mantem_os_tempos():
    from clipator import glossario

    trans = _transcricao_de([("O flavio bolssonaro falou com o Vorcano ontem.", 0.5),
                             ("E a luta continua, disse o Renam.", 1.0)])
    tempos = [(w["inicio"], w["fim"]) for s in trans["segmentos"] for w in s["palavras"]]
    trans, trocas = glossario.corrigir_transcricao(trans, ["Flávio Bolsonaro", "Vorcaro", "Lula", "Renan"])
    textos = [s["texto"] for s in trans["segmentos"]]
    assert textos[0] == "O Flávio Bolsonaro falou com o Vorcaro ontem."
    assert textos[1] == "E a luta continua, disse o Renan."  # "luta" não vira "Lula"
    assert [(w["inicio"], w["fim"]) for s in trans["segmentos"] for w in s["palavras"]] == tempos
    assert {t["para"] for t in trocas} == {"Flávio Bolsonaro", "Vorcaro", "Renan."}
    assert trans["segmentos"][0]["texto_original"].startswith("O flavio bolssonaro")
    assert any(w.get("original") == "Vorcano" for w in trans["segmentos"][0]["palavras"])
    _, de_novo = glossario.corrigir_transcricao(trans, ["Flávio Bolsonaro", "Vorcaro", "Renan"])
    assert de_novo == []  # já corrigido: nada muda


def test_glossario_vira_hotwords_dentro_do_limite():
    from clipator import glossario

    termos = [f"Nome{i:02d} Sobrenome" for i in range(40)]
    h = glossario.hotwords(["Vorcaro", "vorcaro", *termos])
    assert h.startswith("Vorcaro, Nome00") and len(h) <= glossario.LIMITE_HOTWORDS
    assert glossario.hotwords([]) is None


# ---- legenda oculta e zona segura -----------------------------------------------
def test_srt_vtt_no_tempo_do_corte(tmp_path):
    trans = _transcricao_de([("Primeira frase do trecho que fica antes do corte.", 0.4),
                             ("Esta parte some no corte interno do clip.", 0.4),
                             ("E aqui termina a ideia com uma conclusão clara.", 1.0)])
    pals = transcribe.palavras(trans)
    seg = trans["segmentos"]
    ini, fim = seg[0]["inicio"], seg[2]["fim"]
    corte = (seg[1]["inicio"] - 0.1, seg[1]["fim"] + 0.1)
    tl = Timeline.de_clip(ini, fim, [corte])
    srt, vtt = subtitles.gerar_srt_vtt(pals, tl, tmp_path)
    texto = srt.read_text(encoding="utf-8")
    assert texto.startswith("1\n00:00:00,000 --> ")
    assert "some no corte" not in texto  # o trecho cortado não aparece
    blocos = texto.strip().split("\n\n")
    assert len(blocos) == 2
    inicio_2 = blocos[1].splitlines()[1].split(" --> ")[0]
    esperado = (corte[0] - ini) + (seg[2]["palavras"][0]["inicio"] - corte[1])
    _, m, resto = inicio_2.split(":")
    assert abs(float(resto.replace(",", ".")) + 60 * int(m) - esperado) < 0.3  # tempo do clip, já sem o corte
    assert all(len(linha) <= 42 for b in blocos for linha in b.splitlines()[2:])
    assert vtt.read_text(encoding="utf-8").startswith("WEBVTT\n\n00:00:00.000 --> ")


def test_legenda_fica_fora_da_zona_coberta(tmp_path):
    import re as _re

    from clipator import plataformas

    trans = _transcricao_de([("Uma frase curta para a legenda.", 1.0)])
    pals = transcribe.palavras(trans)
    tl = Timeline.de_clip(0, trans["duracao"])
    zona = plataformas.PLATAFORMAS["tiktok"].zona
    ass = subtitles.gerar_ass(pals, tl, Legenda(posicao="baixo"), 1080, 1920, tmp_path / "l.ass", zona=zona)
    texto = ass.read_text(encoding="utf-8")
    posicoes = [(int(x), int(y)) for x, y in _re.findall(r"\\pos\((\d+),(\d+)\)", texto)]
    assert posicoes and max(y for _, y in posicoes) <= 1920 * (1 - zona.base)  # "baixo" (88%) sobe para a área livre
    assert posicoes[0][0] < 540  # centro da área livre: os botões ficam à direita
    assert plataformas.info(None, "9:16").id == "youtube-shorts"
    assert plataformas.info(None, "16:9").id == "youtube"

def test_candidatos_respeitam_regras():
    trans = transcricao_falsa(repetir=4)
    regras = Regras(duracao_min=10, duracao_max=25, quantidade=3)
    cands = candidates.gerar(trans, None, {}, regras, ["dinheiro"])
    assert cands
    for c in cands:
        assert 9 <= c["duracao"] <= 27
        assert 0 <= c["nota"] <= 100
        assert c["motivos"]
    notas = [c["nota"] for c in cands]
    assert notas == sorted(notas, reverse=True)
    # sem sobreposição relevante
    for i, a in enumerate(cands):
        for b in cands[i + 1 :]:
            assert candidates._sobreposicao(a, b) < 0.25


def test_candidato_com_gancho_ganha_nota():
    s, trecho = candidates.nota_gancho("Ninguém te conta isso sobre dinheiro")
    s2, _ = candidates.nota_gancho("e aí a gente foi lá")
    assert s > s2 and trecho


def test_temas_proibidos_somem():
    trans = transcricao_falsa(repetir=3)
    regras = Regras(duracao_min=10, duracao_max=25, temas_proibidos=["dinheiro", "empresa", "segredo", "erro", "mercado", "pessoas", "Pois"])
    cands = candidates.gerar(trans, None, {}, regras)
    for c in cands:
        assert "dinheiro" not in c["texto"].lower()


def test_sinais_entram_na_nota():
    trans = transcricao_falsa()
    regras = Regras(duracao_min=10, duracao_max=25)
    n = int(40 / 0.25)
    sinais = {"passo": 0.25, "energia_db": [-30.0] * n, "media_db": -30.0, "desvio_db": 3.0, "picos": [], "cenas": []}
    base = candidates.gerar(trans, sinais, {}, regras)
    alto = [-30.0] * n
    for i in range(int(20 / 0.25), int(36 / 0.25)):
        alto[i] = -18.0
    sinais2 = {**sinais, "energia_db": alto}
    com = candidates.gerar(trans, sinais2, {}, regras)
    assert com[0]["inicio"] >= 15  # o trecho mais intenso sobe
    assert base and com


def test_heatmap_do_youtube():
    trans = transcricao_falsa(repetir=2)
    regras = Regras(duracao_min=10, duracao_max=25)
    meta = {"mais_repetidos": [{"inicio": 40, "fim": 60, "valor": 1.0}], "capitulos": []}
    cands = candidates.gerar(trans, None, meta, regras)
    melhor = cands[0]
    assert melhor["sinais"]["plataforma"] > 0.5
    assert melhor["fim"] > 40 and melhor["inicio"] < 60


def test_corte_longo():
    trans = transcricao_falsa(duracao=36, repetir=40)  # ~24 min
    regras = Regras(duracao_min=10, duracao_max=25)
    cands = candidates.gerar(trans, None, {}, regras, modo="longo")
    assert cands
    for c in cands:
        assert c["modo"] == "longo"
        assert regras.corte_longo_min - 1 <= c["duracao"] <= regras.corte_longo_max + 1


def test_snap_em_palavras():
    pals = [{"texto": "a", "inicio": 1.0, "fim": 1.3}, {"texto": "b", "inicio": 2.0, "fim": 2.4}, {"texto": "c", "inicio": 3.0, "fim": 3.2}]
    ini, fim = candidates.snap_to_words(1.9, 2.6, pals, 10)
    assert 1.6 <= ini < 2.0 and 2.4 < fim <= 2.75


# ---- títulos --------------------------------------------------------------------
def test_titulos_locais():
    ts = titles.titulos_locais("Eu perdi 500 mil reais com dinheiro mal investido", ["O erro que custou {numero}", "NINGUÉM te conta isso sobre {tema}"], ["dinheiro"])
    assert "O erro que custou 500 mil" in ts[0]
    assert any("dinheiro" in t for t in ts)



def test_titulos_nao_repetem_com_nome_no_video_todo():
    from clipator.workspace import FORMULAS_PADRAO

    assuntos = ["imposto de renda imposto aumentou", "campanha eleitoral campanha cresceu",
                "apartamento comprado apartamento caro", "aposentadoria cortada aposentadoria baixa"]
    trechos = [f"Então o Flávio disse que o {a}. O Flávio repetiu." for a in assuntos]
    blocos = trechos + ["O Flávio chegou cedo.", "Bom dia, Flávio.", "Flávio, obrigado."]
    df, n = titles.frequencias(blocos)
    comuns = titles.termos_comuns(trechos)
    assert "flavio" in comuns
    usados, principais = set(), []
    for i, tx in enumerate(trechos):
        ts = titles.titulos_locais(tx, FORMULAS_PADRAO, ["Flávio"], inicio=i, df=df, n_blocos=n,
                                   evitar=comuns, ja_usados=usados)
        usados.add(ts[0])
        principais.append(ts[0])
    assert len(set(principais)) == len(principais)
    assert not any("Flávio" in t for t in principais)
    assert "imposto" in principais[0] and "campanha" in principais[1].lower()

def test_censor_leetspeak():
    assert titles.censurar("A VIOLÊNCIA no jogo", ["violência"]) == "A VIOL3NCIA no jogo"


def test_trava_do_titulo():
    assert titles.respeita_trava("Ele PERDEU 500 mil", "eu perdi 500 mil reais")
    assert not titles.respeita_trava("Ele comprou uma Ferrari", "eu perdi 500 mil reais")


# ---- legendas ---------------------------------------------------------------------
def test_ass_karaoke_e_cartela(tmp_path):
    pals = [{"texto": "Olá", "inicio": 10.0, "fim": 10.4}, {"texto": "mundo", "inicio": 10.5, "fim": 11.0},
            {"texto": "cortado", "inicio": 12.0, "fim": 12.4}, {"texto": "fim.", "inicio": 13.0, "fim": 13.5}]
    tl = Timeline.de_clip(10, 14, [(11.8, 12.6)])
    leg = Legenda(caixa_alta=True, animacao="pop", palavras_destaque=["mundo"])
    out = subtitles.gerar_ass(pals, tl, leg, 1080, 1920, tmp_path / "x.ass", titulo="NINGUÉM te conta", cartela=Cartela(), usar_cartela=True)
    txt = out.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in txt and "PlayResY: 1920" in txt
    assert "OLÁ" in txt and "CORTADO" not in txt
    assert "Style: Cartela" in txt and "NINGUÉM TE CONTA" in txt
    assert "\\fscx110" in txt  # pop
    # a palavra depois do corte começa 0,8 s antes no clip
    assert "0:00:02.20" in txt


def test_ass_cor_bgr():
    assert subtitles.ass_color("#FF8000") == "&H000080FF"
    assert subtitles.ass_inline("#FF8000") == "&H0080FF&"


# ---- transcrição ------------------------------------------------------------------
def test_merge_continuacao():
    out = transcribe.merge_continuation_words([{"word": " You", "end": 1}, {"word": "Tube", "end": 2}, {"word": " é", "end": 3}])
    assert [w["word"] for w in out] == [" YouTube", " é"]


def test_corrigir_segmento_mesmo_tamanho_e_diferente():
    seg = {"inicio": 0, "fim": 2, "texto": "ola mundo", "palavras": [{"texto": "ola", "inicio": 0, "fim": 1}, {"texto": "mundo", "inicio": 1, "fim": 2}]}
    a = transcribe.corrigir_segmento(seg, "Olá mundo")
    assert a["palavras"][0]["texto"] == "Olá" and a["palavras"][1]["inicio"] == 1
    b = transcribe.corrigir_segmento(seg, "Olá meu mundo")
    assert len(b["palavras"]) == 3 and b["palavras"][-1]["fim"] == pytest.approx(2)


def test_transcrever_com_modelo_falso(whisper_falso, tmp_path):
    t = transcribe.transcrever(tmp_path / "a.wav", "small", "cpu")
    assert t["segmentos"] and t["segmentos"][0]["palavras"][0]["texto"] == "Ninguém"


def test_transcrever_cai_para_cpu_sem_cublas(monkeypatch, tmp_path):
    from .conftest import WhisperFalso

    class WhisperSemCublas:
        def transcribe(self, audio, language=None, **kw):
            def segs():
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                yield

            return segs(), types.SimpleNamespace(duration=10, language="pt")

    carregados = []

    def carregar(nome, dev, compute, pasta=None):
        carregados.append((nome, dev, compute))
        return WhisperSemCublas() if dev == "cuda" else WhisperFalso()

    monkeypatch.setattr(transcribe, "carregar_modelo", carregar)
    monkeypatch.setattr(transcribe, "_cuda_ok", None)
    msgs = []
    t = transcribe.transcrever(tmp_path / "a.wav", "large-v3-turbo", "cuda", progresso=lambda f, m: msgs.append(m))
    assert t["dispositivo"] == "cpu" and t["modelo"] == "small" and t["segmentos"]
    assert carregados[-1] == ("small", "cpu", "int8")
    assert "GPU sem CUDA; transcrevendo na CPU" in msgs


def test_transcrever_nao_engole_outros_erros(monkeypatch, tmp_path):
    class WhisperQuebrado:
        def transcribe(self, audio, language=None, **kw):
            raise RuntimeError("outra falha")

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperQuebrado())
    with pytest.raises(RuntimeError, match="outra falha"):
        transcribe.transcrever(tmp_path / "a.wav", "small", "cuda")


def test_cuda_utilizavel_falso_sem_dll(monkeypatch):
    def falha(nome):
        raise OSError(f"{nome} não encontrada")

    monkeypatch.setattr(transcribe, "_cuda_ok", None)
    monkeypatch.setattr(transcribe, "gpu_disponivel", lambda: True)
    monkeypatch.setattr(transcribe, "_pastas_dll_nvidia", lambda: None)
    monkeypatch.setattr(transcribe, "_carregar_lib", falha)
    monkeypatch.setattr(transcribe.sys, "platform", "win32")
    assert transcribe.cuda_utilizavel() is False
    assert transcribe.escolher_modelo() == ("small", "cpu", "int8")
    monkeypatch.setattr(transcribe, "_cuda_ok", None)


def test_carregar_audio_le_wav_16k(tmp_path):
    import wave

    import numpy as np

    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(np.array([0, 16384, -16384], dtype=np.int16).tobytes())
    x = transcribe.carregar_audio(wav)
    assert x.dtype == np.float32 and x.tolist() == [0.0, 0.5, -0.5]
    assert transcribe.carregar_audio(tmp_path / "nao-existe.mp4") == str(tmp_path / "nao-existe.mp4")


def test_escolher_modelo_cpu():
    assert transcribe.escolher_modelo("auto", "cpu") == ("small", "cpu", "int8")


# ---- ingestão ---------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=pS3TNsN7N3M", "https://youtu.be/pS3TNsN7N3M", "https://youtube.com/shorts/abc",
    "https://www.twitch.tv/videos/123456", "https://clips.twitch.tv/AbcDef",
])
def test_links_validos(url):
    assert validar_link(url) in ("youtube", "twitch")


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/playlist?list=x", "https://www.youtube.com/@canal", "https://vimeo.com/123",
    "https://www.twitch.tv/canal", "https://www.youtube.com/results?search_query=x",
])
def test_links_invalidos(url):
    with pytest.raises(IngestaoError):
        validar_link(url)



def test_baixar_sem_ffmpeg_explica(ws, monkeypatch):
    from clipator import ingest, media

    monkeypatch.setenv("CLIPATOR_FFMPEG", "/nao/existe/ffmpeg")
    assert media.ffmpeg_disponivel() is False
    proj = ws.criar_canal("Teste").criar_projeto("Ep 1")
    with pytest.raises(IngestaoError, match="FFmpeg não encontrado"):
        ingest.baixar("https://www.youtube.com/watch?v=pS3TNsN7N3M", proj)


def test_ytdlp_usa_o_ffmpeg_do_motor(ws, monkeypatch):
    import sys
    import types

    from clipator import ingest, media

    usadas: list[dict] = []

    class FakeYDL:
        def __init__(self, opts):
            usadas.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            return {"id": "x", "title": "t", "duration": 10}

        def process_ie_result(self, info, download=True):
            (proj.fonte_dir / "video.mp4").write_bytes(b"0")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYDL))
    monkeypatch.setattr(media, "ffmpeg_disponivel", lambda: True)
    monkeypatch.setattr(media, "ffmpeg_bin", lambda: "/opt/ff/bin/ffmpeg")
    proj = ws.criar_canal("Teste").criar_projeto("Ep 1")
    ingest.baixar("https://www.youtube.com/watch?v=pS3TNsN7N3M", proj)
    assert usadas and all(o["ffmpeg_location"] == "/opt/ff/bin/ffmpeg" for o in usadas)


def test_completar_path_windows_nao_mexe_fora_do_windows(monkeypatch):
    from clipator import media

    monkeypatch.setattr(media.os, "name", "posix")
    antes = media.os.environ.get("PATH")
    media.completar_path_windows()
    assert media.os.environ.get("PATH") == antes


# ---- validação do editor ------------------------------------------------------------
def test_validacao_estilo():
    erros = validacao.validar("estilos/x.md", "---\nformato: 7:3\nlegenda:\n  tamanho: 5\n---\n")
    assert len(erros) == 2
    assert {e["linha"] for e in erros} == {2, 4}
    assert validacao.validar("estilos/x.md", "---\nformato: '9:16'\n---\n") == []


def test_validacao_regras_e_yaml_quebrado():
    assert validacao.validar("canais/a/regras.md", "---\nduracao_min: 30\nduracao_max: 20\n---\n")
    assert validacao.validar("canais/a/projetos/p/clips/c/clip.yaml", "id: [")[0]["linha"] >= 1
    assert validacao.validar("qualquer.txt", "x") == []


def test_avisos_de_terceiros_em_sincronia():
    from pathlib import Path

    motor = Path(__file__).resolve().parents[1]
    raiz = motor.parent
    if (raiz / "THIRD_PARTY_NOTICES.md").exists():
        assert (raiz / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8") == (motor / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")


def test_pastas_winget(tmp_path):
    from clipator import media

    ff = tmp_path / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe" / "ffmpeg-9.0.2-full_build" / "bin"
    ff.mkdir(parents=True)
    (ff / "ffmpeg.exe").write_bytes(b"")
    dn = tmp_path / "Microsoft" / "WinGet" / "Packages" / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe"
    dn.mkdir(parents=True)
    (dn / "deno.exe").write_bytes(b"")
    assert media.pastas_winget(str(tmp_path)) == [str(ff), str(dn)]
