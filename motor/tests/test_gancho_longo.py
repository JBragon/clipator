"""Gancho forte nos cortes longos, a vinheta do canal (só nos longos) e a análise da IA no padrão dos cortes."""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest

from clipator import abertura, media, pipeline, vinheta
from clipator.ai import ranking
from clipator.candidates import CONECTIVOS_INICIO
from clipator.models import Abertura, Origem, Regras
from clipator.textutil import normalizar
from clipator.transcribe import palavras as _palavras

from .conftest import precisa_ffmpeg, transcricao_falsa


class IAFalsa:
    nome = "falsa"

    def __init__(self, resposta):
        self.resposta = resposta
        self.prompts: list[str] = []

    def run_json(self, prompt, schema, cancelar=None):
        self.prompts.append(prompt)
        return self.resposta(prompt)


def _cfg_longo(**kw) -> Abertura:
    return Abertura.model_validate({**abertura.ajustes_corte_longo("cor")["abertura"], **kw})


# ---- escolha do trecho forte sem IA -------------------------------------------------------------
def test_gancho_longo_e_um_trecho_corrido_de_frases_inteiras():
    pals = _palavras(transcricao_falsa(duracao=36.0, repetir=5))  # 180 s de fala
    dur = pals[-1]["fim"] + 0.5
    cfg = _cfg_longo()
    assert abertura.bloco_corrido(cfg)
    gs = abertura.escolher(pals, dur, cfg)
    assert len(gs) == 1
    g = gs[0]
    assert abertura.BLOCO_MIN - 0.3 <= g.fim - g.inicio <= cfg.max_trecho + 0.3
    assert g.inicio >= dur * cfg.inicio_minimo - abertura.PAD_ANTES
    assert normalizar(g.texto.split()[0]) not in CONECTIVOS_INICIO
    assert g.texto.rstrip().endswith((".", "?", "!", ":"))


def test_energia_puxa_o_trecho_forte():
    pals = _palavras(transcricao_falsa(duracao=36.0, repetir=5))
    dur = pals[-1]["fim"] + 0.5
    cfg = _cfg_longo()
    alvo = 150.0

    def energia(a: float, b: float) -> float:
        return 3.0 if a - 2 <= alvo <= b + 2 else -1.0

    g = abertura.escolher(pals, dur, cfg, energia)[0]
    assert g.inicio - 3 <= alvo <= g.fim + 3


def test_gancho_curto_continua_como_antes():
    cfg = Abertura(ativa=True, duracao=6, max_trechos=2)
    assert not abertura.bloco_corrido(cfg)


def test_ajustes_do_passo3_para_os_cortes_longos():
    cor = abertura.ajustes_corte_longo("cor", "depois-do-gancho")
    assert cor["abertura"]["ativa"] and cor["abertura"]["preto_e_branco"] is False
    assert cor["vinheta"] == "depois-do-gancho"
    pb = abertura.ajustes_corte_longo("preto-e-branco", "inicio")
    assert pb["abertura"]["preto_e_branco"] is True and pb["abertura"]["max_trechos"] == 1
    assert abertura.ajustes_corte_longo("nenhum", "nenhuma") == {"abertura": {"ativa": False}, "vinheta": "nenhuma"}
    Abertura.model_validate(pb["abertura"])  # cabe nos limites do modelo
    with pytest.raises(ValueError):
        abertura.ajustes_corte_longo("verde")
    with pytest.raises(ValueError):
        abertura.ajustes_corte_longo("cor", "fim")


def test_legenda_oculta_desconta_a_vinheta():
    pals = [{"texto": "a", "inicio": 1.0, "fim": 1.2}, {"texto": "b", "inicio": 5.0, "fim": 5.3}]
    g = [abertura.Gancho(4.9, 5.5, "b", 1.0)]
    # gancho (0,6 s), vinheta (3 s) e o corte
    depois = abertura.palavras_finais(pals, g, 3.0, vinheta_antes=False)
    assert depois[0]["inicio"] == pytest.approx(0.1)
    assert depois[1]["inicio"] == pytest.approx(0.6 + 3.0 + 1.0)
    # vinheta (3 s), gancho e o corte
    antes = abertura.palavras_finais(pals, g, 3.0, vinheta_antes=True)
    assert antes[0]["inicio"] == pytest.approx(3.1)
    assert antes[1]["inicio"] == pytest.approx(3.6 + 1.0)
    # sem gancho, a vinheta abre o vídeo mesmo pedindo depois do gancho
    so_vin = abertura.palavras_finais(pals, [], 3.0, vinheta_antes=False)
    assert so_vin[0]["inicio"] == pytest.approx(4.0)


# ---- IA: títulos no padrão e trecho forte -------------------------------------------------------
def _cand_longo(pals: list[dict]) -> dict:
    ini, fim = pals[0]["inicio"], pals[-1]["fim"]
    return {"id": "L01", "inicio": ini, "fim": fim, "duracao": fim - ini, "nota": 40.0, "modo": "longo",
            "texto": " ".join(w["texto"] for w in pals), "titulos": ["local"]}


def test_ia_le_o_corte_longo_e_aponta_o_trecho_forte():
    trans = transcricao_falsa(duracao=36.0, repetir=5)
    pals = _palavras(trans)
    c = _cand_longo(pals)
    alvo = next(w for w in pals if w["inicio"] > 100)
    ia = IAFalsa(lambda p: {"nota": 88, "titulos": ["EMPRESÁRIO FAZ ALERTA SOBRE O PIOR ERRO DA VIDA | Fulano no Podcast"],
                            "gancho": "FOI O PIOR ERRO DA MINHA VIDA",
                            "trecho_forte": {"inicio": alvo["inicio"], "fim": alvo["inicio"] + 14, "frase": "pior erro"},
                            "motivo": "promessa forte"})
    meta = {"titulo": "FULANO - Podcast #1", "canal": "Podcast",
            "capitulos": [{"inicio": 0, "fim": 500, "titulo": "O PIOR ERRO da vida"}]}
    out = ranking.analisar_longos([c], trans, ia, Regras(), metadados=meta)[0]
    p = ia.prompts[0]
    assert "TRECHO FORTE" in p and "FULANO - Podcast #1" in p and "O PIOR ERRO da vida" in p
    assert "exagere o tom, nunca o fato" in p
    assert out["nota"] == 88 and out["titulos"][0].startswith("EMPRESÁRIO FAZ ALERTA")
    (a, b), = out["ia"]["abertura"]
    assert c["inicio"] <= a < b <= c["fim"] and 6 <= b - a <= 25
    assert out["ia"]["gancho"] == "FOI O PIOR ERRO DA MINHA VIDA"


def test_trecho_forte_fora_do_corte_ou_no_comeco_e_descartado():
    pals = _palavras(transcricao_falsa(duracao=36.0, repetir=5))
    c = _cand_longo(pals)
    dur = c["fim"] + 1
    assert ranking.trecho_forte({"inicio": c["fim"] + 5, "fim": c["fim"] + 20}, c, pals, dur) is None
    assert ranking.trecho_forte({"inicio": c["inicio"], "fim": c["inicio"] + 2}, c, pals, dur) is None  # cai nos 10% iniciais
    assert ranking.trecho_forte({"inicio": 100, "fim": 160}, c, pals, dur) is None  # longo demais
    assert ranking.trecho_forte("x", c, pals, dur) is None
    ok = ranking.trecho_forte({"inicio": 100, "fim": 112}, c, pals, dur)
    assert ok is not None and 6 <= ok[1] - ok[0] <= 25


def test_ia_que_nao_responde_deixa_o_corte_longo_como_estava():
    trans = transcricao_falsa(duracao=36.0, repetir=5)
    c = _cand_longo(_palavras(trans))
    out = ranking.analisar_longos([c], trans, IAFalsa(lambda p: None), Regras())[0]
    assert out["titulos"] == ["local"] and "ia" not in out


def test_padrao_de_titulo_vale_tambem_para_os_shorts():
    assert "exagere o tom, nunca o fato" in ranking._regra_titulo({}, True)
    assert "exagere o tom" not in ranking._regra_titulo({"temperatura": "morno"}, True)


# ---- vinheta: cadastro e montagem ----------------------------------------------------------------
def _video_cor(caminho, cor: str, dur: float, audio: bool = True, tamanho: str = "320x240") -> bytes:
    args = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={cor}:size={tamanho}:rate=25:duration={dur}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=880:duration={dur}", "-c:a", "aac", "-shortest"]
    subprocess.run(args + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(caminho)], check=True)
    return caminho.read_bytes()


@precisa_ffmpeg
def test_cadastro_da_vinheta_no_canal(ws, tmp_path):
    c = ws.criar_canal("Teste")
    assert vinheta.estado(c)["arquivo"] is None
    with pytest.raises(vinheta.ErroVinheta):
        vinheta.salvar(c, "vinheta.txt", b"x")
    with pytest.raises(vinheta.ErroVinheta):
        vinheta.salvar(c, "longa.mp4", _video_cor(tmp_path / "longa.mp4", "red", vinheta.DURACAO_MAX + 2, audio=False))
    st = vinheta.salvar(c, "Minha Vinheta.mp4", _video_cor(tmp_path / "v.mp4", "red", 2.0))
    assert st["arquivo"] == "assets/vinheta.mp4" and st["duracao"] == pytest.approx(2.0, abs=0.2)
    assert st["posicao"] == "depois-do-gancho"
    info, _ = c.info()
    assert info.vinheta == "assets/vinheta.mp4"
    assert vinheta.definir_posicao(c, "inicio")["posicao"] == "inicio"
    with pytest.raises(vinheta.ErroVinheta):
        vinheta.definir_posicao(c, "meio")
    # trocar por um .mov apaga a anterior
    st = vinheta.salvar(c, "nova.mov", _video_cor(tmp_path / "n.mov", "blue", 1.0))
    assert st["arquivo"] == "assets/vinheta.mov" and not (c.path / "assets" / "vinheta.mp4").exists()
    st = vinheta.remover(c)
    assert st["arquivo"] is None and not (c.path / "assets" / "vinheta.mov").exists()


def _cor_media(video, t, pasta, nome):
    from PIL import Image

    q = media.extrair_quadro(video, t, pasta / nome, 160)
    return np.asarray(Image.open(q).convert("RGB")).astype(float).reshape(-1, 3).mean(axis=0)


@precisa_ffmpeg
@pytest.mark.parametrize("posicao", ["depois-do-gancho", "inicio"])
def test_corte_longo_com_gancho_e_vinheta(ws, video_teste, monkeypatch, tmp_path, posicao):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=12)))
    c = ws.criar_canal("Teste")
    md = c.arquivo("regras.md")
    md.write_text(md.read_text().replace("duracao_min: 40", "duracao_min: 5").replace("duracao_max: 180", "duracao_max: 13"))
    vinheta.salvar(c, "v.mp4", _video_cor(tmp_path / "v.mp4", "red", 1.5, audio=False, tamanho="320x320"))
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia", corte_longo=False)
    # um corte longo de mentira (o vídeo de teste tem 14 s): o gancho forte tem de caber nele
    longo = {**cands[0], "id": "L01", "modo": "longo", "inicio": 0.3, "fim": 13.5, "duracao": 13.2,
             "ia": {"abertura": [[6.0, 9.0]]}}
    p.salvar_candidatos([*cands, longo])
    curto = pipeline.selecionar(p, [cands[0]["id"]], longo={"gancho": "cor", "vinheta": posicao})[0]
    clip = pipeline.selecionar(p, ["L01"], longo={"gancho": "preto-e-branco", "vinheta": posicao})[0]
    assert "vinheta" not in curto.ajustes_estilo  # Short nunca recebe a vinheta
    assert clip.estilo == "corte-longo" and clip.formato == "16:9"
    assert clip.ajustes_estilo["abertura"]["preto_e_branco"] is True and clip.ajustes_estilo["vinheta"] == posicao
    r = pipeline.renderizar(p, clip.id, preview=True)
    pasta = p.clips_dir / clip.id
    dados = json.loads((pasta / "abertura.preview.json").read_text(encoding="utf-8"))
    assert dados["vinheta"]["posicao"] == posicao, r.aviso
    assert dados["ganchos"] and dados["ganchos"][0]["inicio"] == pytest.approx(6.0 - 0.3, abs=0.4)  # o trecho da IA
    g = dados["ganchos"][0]["fim"] - dados["ganchos"][0]["inicio"]
    assert dados["duracao"] == pytest.approx(g + 1.5, abs=0.15)
    info = media.probe(r.video)
    assert info.largura / info.altura == pytest.approx(16 / 9, abs=0.02)
    assert info.duracao == pytest.approx(13.2 + dados["duracao"], abs=0.4)
    t_vin = (g + 0.75) if posicao == "depois-do-gancho" else 0.75
    t_gancho = (g / 2) if posicao == "depois-do-gancho" else (1.5 + g / 2)
    r_, g_, b_ = _cor_media(r.video, t_vin, pasta, "vin.jpg")
    assert r_ > 120 and g_ < 80 and b_ < 80  # a vinheta vermelha, encaixada com barras pretas
    cor_g = _cor_media(r.video, t_gancho, pasta, "gancho.jpg")
    assert float(cor_g.max() - cor_g.min()) < 8  # o gancho em preto e branco


@precisa_ffmpeg
def test_short_nao_recebe_vinheta_mesmo_pedindo(ws, video_teste, monkeypatch, tmp_path):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=12)))
    c = ws.criar_canal("Teste")
    md = c.arquivo("regras.md")
    md.write_text(md.read_text().replace("duracao_min: 40", "duracao_min: 5").replace("duracao_max: 180", "duracao_max: 13"))
    vinheta.salvar(c, "v.mp4", _video_cor(tmp_path / "v.mp4", "red", 1.0, audio=False))
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia", corte_longo=False)
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", ajustes={"vinheta": "inicio"})[0]
    pipeline.renderizar(p, clip.id, preview=True)
    assert not (p.clips_dir / clip.id / "abertura.preview.json").exists()


# ---- Shorts: a abertura usa os momentos fortes que a IA apontou -----------------------------------
def test_ia_aponta_os_momentos_fortes_do_short():
    trans = transcricao_falsa(duracao=36.0)
    pals = _palavras(trans)
    c = {"id": "c01", "inicio": pals[0]["inicio"], "fim": pals[-1]["fim"], "duracao": pals[-1]["fim"] - pals[0]["inicio"],
         "nota": 50.0, "texto": " ".join(w["texto"] for w in pals), "titulos": []}
    m1, m2 = pals[30]["inicio"], pals[60]["inicio"]
    ia = IAFalsa(lambda p: {"candidatos": [{"id": "c01", "nota": 70, "titulos": [], "gancho": "", "ajuste_inicio": 0,
                                             "ajuste_fim": 0, "fecha_assunto": True, "motivo": "", "destaques": [],
                                             "momentos_fortes": [{"inicio": m2, "fim": m2 + 3}, {"inicio": m1, "fim": m1 + 2.5},
                                                                 {"inicio": 0.3, "fim": 3.0},  # no começo: cai
                                                                 {"inicio": m1 + 1, "fim": m1 + 3}]}]})  # sobrepõe: cai
    out = ranking.ranquear([c], trans, ia, Regras(duracao_min=5, duracao_max=40))[0]
    assert "momentos_fortes" in ia.prompts[0]
    ab = out["ia"]["abertura"]
    assert len(ab) == 2 and ab[0][0] < ab[1][0]
    assert all(1.0 <= b - a <= 5.0 and a >= c["inicio"] + 0.15 * c["duracao"] for a, b in ab)


@precisa_ffmpeg
def test_short_com_gancho_usa_os_momentos_da_ia(ws, video_teste, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=12)))
    c = ws.criar_canal("Teste")
    md = c.arquivo("regras.md")
    md.write_text(md.read_text().replace("duracao_min: 40", "duracao_min: 5").replace("duracao_max: 180", "duracao_max: 13"))
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia", corte_longo=False)
    cand = {**cands[0], "inicio": 0.3, "fim": 13.5, "ia": {"abertura": [[9.0, 11.0], [5.0, 7.0]]}}
    p.salvar_candidatos([cand, *cands[1:]])
    clip = pipeline.selecionar(p, [cand["id"]], formato="9:16", estilo="gancho-preto-e-branco")[0]
    pipeline.renderizar(p, clip.id, preview=True)
    dados = json.loads((p.clips_dir / clip.id / "abertura.preview.json").read_text(encoding="utf-8"))
    assert [round(g["inicio"]) for g in dados["ganchos"]] == [5, 9]  # tempo do clip: 5,3 e 9,3 menos o começo 0,3
    assert dados["vinheta"] is None
