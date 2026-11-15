"""Duração dos cortes, ajuste da IA, títulos e legendas (motor de candidatos e de legendas)."""

from __future__ import annotations

import random
import re
import statistics

import pytest

from clipator import candidates, subtitles, titles
from clipator.ai import ranking
from clipator.models import Legenda, Regras
from clipator.timeline import Timeline
from clipator.transcribe import limpar_alucinacoes

ASSUNTOS = {
    "investimento": ["investimento", "ações", "bolsa", "dividendos", "corretora", "carteira", "juros", "inflação"],
    "futebol": ["futebol", "técnico", "jogador", "campeonato", "torcida", "clube", "contrato", "estádio"],
    "carreira": ["empresa", "chefe", "salário", "emprego", "entrevista", "currículo", "promoção", "demissão"],
}
ENCHE = ["eu", "acho", "que", "o", "a", "de", "um", "muito", "isso", "foi", "quando", "com", "para", "mais",
         "ele", "ela", "sempre", "tinha", "era", "vai", "fazer", "ver"]


def conversa(seed: int = 1, minutos: float = 12) -> dict:
    """Uma conversa sintética: frases de 4 a 22 palavras, ritmo e pausas variados, assunto que muda."""
    rnd = random.Random(seed)
    t, segs = 2.0, []
    assunto, troca = rnd.choice(list(ASSUNTOS)), 0.0
    while t < minutos * 60:
        if t > troca:
            assunto, troca = rnd.choice(list(ASSUNTOS)), t + rnd.uniform(90, 200)
        ws = [rnd.choice(ASSUNTOS[assunto]) if rnd.random() < 0.18 else rnd.choice(ENCHE) for _ in range(rnd.randint(4, 22))]
        ws[0] = ws[0].capitalize()
        ws[-1] += "?" if rnd.random() < 0.12 else "."
        passo, pals = 1 / rnd.uniform(2.2, 3.6), []
        for w in ws:
            pals.append({"texto": w, "inicio": round(t, 3), "fim": round(t + passo * 0.85, 3), "prob": 0.9})
            t += passo
        segs.append({"inicio": pals[0]["inicio"], "fim": pals[-1]["fim"], "texto": " ".join(p["texto"] for p in pals),
                     "palavras": pals})
        t += rnd.choice([0.15, 0.25, 0.35, 0.5, 0.7, 0.9, 1.3])
    return {"idioma": "pt", "duracao": t + 1, "segmentos": segs}


# o padrão antigo (Shorts de 20 a 60 s, até 90 s para fechar o assunto), alvo de 50 s
REGRAS_60 = Regras(duracao_min=20, duracao_max=60, duracao_max_fechamento=90, duracao_ideal=None)


# ---- duração dos cortes ------------------------------------------------------------------------
def test_alvo_curto_padrao_e_do_canal():
    r = Regras()  # o padrão segue o limite do YouTube Shorts: de 40 s a 3 min, mirando em 90 s
    assert (r.duracao_min, r.duracao_max, r.alvo_curto(), r.teto_curto()) == (40, 180, 90, 180)
    assert Regras(duracao_ideal=40).alvo_curto() == 40
    assert Regras(duracao_ideal=400).alvo_curto() == 180  # nunca passa da máxima
    assert Regras(duracao_min=30, duracao_max=90, duracao_ideal=None).alvo_curto() == pytest.approx(75)
    assert Regras(duracao_min=20, duracao_max=60, duracao_max_fechamento=90).teto_curto() == 90


def test_fator_duracao_pune_o_corte_curto_mais_que_o_longo():
    assert candidates.fator_duracao(50, 20, 60, 50) == pytest.approx(1.0)
    assert candidates.fator_duracao(20, 20, 60, 50) == pytest.approx(0.7)
    assert candidates.fator_duracao(60, 20, 60, 50) == pytest.approx(0.95)
    assert candidates.fator_duracao(35, 20, 60, 50) < candidates.fator_duracao(60, 20, 60, 50)


def test_cortes_locais_ficam_perto_da_duracao_alvo():
    duracoes = []
    for seed in range(1, 4):
        cs = candidates.gerar(conversa(seed), None, {}, REGRAS_60)
        duracoes += [c["duracao"] for c in cs[:8]]
    # antes desta mudança a mediana ficava em ~40 s (o meio da faixa) e havia cortes de 30 s no topo
    assert statistics.median(duracoes) >= 45
    assert min(duracoes) >= 30


def test_padrao_usa_o_tempo_do_youtube_shorts():
    duracoes = []
    for seed in range(1, 3):
        cs = candidates.gerar(conversa(seed), None, {}, Regras())
        duracoes += [c["duracao"] for c in cs[:8]]
    assert statistics.median(duracoes) >= 80
    assert min(duracoes) >= 40 and max(duracoes) <= 181


def test_duracao_ideal_do_canal_muda_os_cortes():
    trans = conversa(2)
    curtos = candidates.gerar(trans, None, {}, REGRAS_60.model_copy(update={"duracao_ideal": 25}))
    longos = candidates.gerar(trans, None, {}, REGRAS_60.model_copy(update={"duracao_ideal": 60}))
    med = lambda cs: statistics.median(c["duracao"] for c in cs[:8])  # noqa: E731
    assert med(longos) > med(curtos) + 10


# ---- ajuste da IA --------------------------------------------------------------------------------
class IAFalsa:
    nome = "falsa"

    def __init__(self, resposta):
        self.resposta = resposta
        self.prompt = ""

    def run_json(self, prompt, schema, cancelar=None):
        self.prompt = prompt
        return self.resposta(prompt)


def test_ia_ve_a_fala_em_volta_e_a_duracao_alvo():
    trans = conversa(3)
    regras = REGRAS_60
    cands = candidates.gerar(trans, None, {}, regras)
    ia = IAFalsa(lambda p: {"candidatos": []})
    ranking.ranquear(cands, trans, ia, regras)
    assert "antes do corte:" in ia.prompt and "depois do corte:" in ia.prompt
    assert "perto de 50 s" in ia.prompt
    assert "-30 a 5 s" in ia.prompt


def test_ia_nao_encurta_o_corte_abaixo_da_minima():
    trans = conversa(4)
    regras = REGRAS_60
    cands = candidates.gerar(trans, None, {}, regras)
    alvo = cands[0]
    # a IA tenta tirar 30 s do começo (ajuste_inicio só vai até +5) e 5 s do fim: o corte não fica abaixo de 20 s
    ia = IAFalsa(lambda p: {"candidatos": [{"id": alvo["id"], "nota": 90, "titulos": ["Título"], "gancho": "",
                                             "ajuste_inicio": 30, "ajuste_fim": -5, "fecha_assunto": True,
                                             "motivo": "", "destaques": []}]})
    out = {c["id"]: c for c in ranking.ranquear(cands, trans, ia, regras)}
    assert out[alvo["id"]]["duracao"] >= regras.duracao_min - 3


def test_ia_pode_estender_o_corte_para_pegar_o_contexto():
    trans = conversa(5)
    regras = REGRAS_60
    cands = candidates.gerar(trans, None, {}, regras)
    alvo = min(cands, key=lambda c: c["duracao"])
    ia = IAFalsa(lambda p: {"candidatos": [{"id": alvo["id"], "nota": 90, "titulos": ["Título"], "gancho": "",
                                             "ajuste_inicio": -25, "ajuste_fim": 0, "fecha_assunto": True,
                                             "motivo": "", "destaques": []}]})
    out = {c["id"]: c for c in ranking.ranquear(cands, trans, ia, regras)}
    c = out[alvo["id"]]
    assert alvo["inicio"] > 30 and alvo["duracao"] + 20 <= regras.teto_curto()  # o cenário do teste
    assert c["inicio"] < alvo["inicio"] - 10 and c["duracao"] > alvo["duracao"] + 10


def test_titulos_da_ia_nao_se_repetem_entre_cortes():
    trans = conversa(6)
    regras = REGRAS_60
    cands = candidates.gerar(trans, None, {}, regras)[:3]
    ia = IAFalsa(lambda p: {"candidatos": [
        {"id": c["id"], "nota": 90 - n, "titulos": ["O MESMO título", f"Outro {n}"], "gancho": "", "ajuste_inicio": 0,
         "ajuste_fim": 0, "fecha_assunto": True, "motivo": "", "destaques": []} for n, c in enumerate(cands)]})
    out = ranking.ranquear(cands, trans, ia, regras)
    primeiros = [c["titulos"][0] for c in out]
    assert len(set(primeiros)) == len(primeiros)
    assert primeiros[0] == "O MESMO título"


def test_ia_com_ajuste_invalido_nao_quebra():
    trans = conversa(7)
    regras = REGRAS_60
    cands = candidates.gerar(trans, None, {}, regras)
    ia = IAFalsa(lambda p: {"candidatos": [{"id": cands[0]["id"], "nota": 80, "titulos": [], "gancho": "",
                                             "ajuste_inicio": "muito", "ajuste_fim": None, "fecha_assunto": True,
                                             "motivo": "", "destaques": []}]})
    out = {c["id"]: c for c in ranking.ranquear(cands, trans, ia, regras)}
    assert out[cands[0]["id"]]["inicio"] == cands[0]["inicio"]


# ---- títulos ---------------------------------------------------------------------------------------
def test_tema_pega_a_expressao_inteira():
    assert titles.tema_do_trecho("O imposto de renda subiu. Declarar o imposto de renda é chato. Imposto alto.") == "imposto de renda"
    assert titles.tema_do_trecho("O mercado financeiro caiu. Quem está no mercado financeiro sofre. O mercado é cruel.") == "mercado financeiro"
    # aparece uma vez só: fica a palavra
    assert titles.tema_do_trecho("Eu perdi dinheiro. Dinheiro é tudo. O dinheiro some rápido.") == "dinheiro"


# ---- legendas ---------------------------------------------------------------------------------------
def test_tempos_das_palavras_sao_saneados():
    pals = [
        {"texto": "olha", "inicio": 0.0, "fim": 0.6},
        {"texto": "isso", "inicio": 0.4, "fim": 0.9},  # começa antes da anterior acabar
        {"texto": "aqui", "inicio": 1.0, "fim": 1.0},  # 0 s: nunca acendia
        {"texto": "agora.", "inicio": 1.2, "fim": 5.0},  # esticada por 3,8 s numa pausa
        {"texto": "  ", "inicio": 5.5, "fim": 5.6},
    ]
    out = subtitles.ajustar_tempos(pals)
    assert [w["texto"] for w in out] == ["olha", "isso", "aqui", "agora."]
    assert out[0]["fim"] <= out[1]["inicio"]
    assert out[2]["fim"] - out[2]["inicio"] >= subtitles.MIN_DURACAO_PALAVRA - 1e-9
    assert out[3]["fim"] - out[3]["inicio"] <= subtitles.MAX_DURACAO_PALAVRA + 1e-9
    assert all(a["fim"] <= b["inicio"] + 1e-9 for a, b in zip(out, out[1:]))


def _eventos(ass: str) -> list[tuple[float, float, str]]:
    out = []
    for ln in ass.splitlines():
        if ln.startswith("Dialogue: 0,"):
            _, ini, fim, *_, texto = ln.split(",", 9)
            seg = lambda s: sum(float(x) * m for x, m in zip(s.split(":"), (3600, 60, 1)))  # noqa: E731
            out.append((seg(ini), seg(fim), texto))
    return out


def _palavras(texto: str, passo: float = 0.5, pausa_em: dict | None = None) -> list[dict]:
    pals, t = [], 0.2
    for k, w in enumerate(texto.split()):
        pals.append({"texto": w, "inicio": round(t, 3), "fim": round(t + passo * 0.9, 3)})
        t += passo + (pausa_em or {}).get(k, 0.0)
    return pals


def test_legenda_quebra_pela_largura_e_nao_sai_da_tela(tmp_path):
    pals = _palavras("A responsabilidade financeira, sinceramente, é extraordinária e inacreditavelmente difícil.")
    leg = Legenda(tamanho=90, linhas=1, max_palavras_por_linha=3, caixa_alta=True)
    p = subtitles.gerar_ass(pals, Timeline.de_clip(0, 8), leg, 1080, 1920, tmp_path / "l.ass")
    util = 1080 - 2 * max(40, int(1080 * 0.06))
    for _, _, texto in _eventos(p.read_text(encoding="utf-8")):
        m = re.search(r"\\fs(\d+)", texto.split("}", 1)[0])
        fs = int(m.group(1)) if m else 90
        limpo = re.sub(r"\{[^}]*\}", "", texto)
        for linha in limpo.split("\\N"):
            assert subtitles.largura_estimada(linha, fs, True, leg.fonte) <= util * 1.02, linha
    # "A RESPONSABILIDADE FINANCEIRA" não cabe numa linha de 1080 px: virou dois blocos
    textos = {re.sub(r"\{[^}]*\}", "", t) for _, _, t in _eventos(p.read_text(encoding="utf-8"))}
    assert "A RESPONSABILIDADE FINANCEIRA" not in textos


def test_legenda_mede_com_a_fonte_do_clipator():
    larg_m = subtitles.largura_estimada("RESPONSABILIDADE", 100, True, "Montserrat ExtraBold")
    larg_b = subtitles.largura_estimada("RESPONSABILIDADE", 100, True, "Bebas Neue")
    assert larg_b < larg_m * 0.75  # a Bebas é bem mais estreita: a medida vem da fonte, não de uma média


def test_legenda_nao_pisca_entre_blocos(tmp_path):
    # pausa curta (0,2 s) entre as frases: o bloco espera o próximo; pausa longa (1,5 s): sai depois de um respiro
    pals = _palavras("Primeira frase aqui. Segunda frase agora. Terceira e última.", pausa_em={2: 0.2, 5: 1.5})
    leg = Legenda(max_palavras_por_linha=3)
    p = subtitles.gerar_ass(pals, Timeline.de_clip(0, 10), leg, 1080, 1920, tmp_path / "l.ass")
    ev = _eventos(p.read_text(encoding="utf-8"))
    fim_1 = max(f for _, f, t in ev if "Primeira" in t)
    ini_2 = min(i for i, _, t in ev if "Segunda" in t)
    assert fim_1 == pytest.approx(ini_2, abs=0.011)
    fim_2 = max(f for _, f, t in ev if "Segunda" in t)
    ini_3 = min(i for i, _, t in ev if "Terceira" in t)
    assert fim_2 < ini_3 - 0.5  # pausa longa: tela vazia de verdade


def test_legenda_tira_virgula_e_ponto(tmp_path):
    pals = _palavras("Olha, isso aqui: dinheiro. Sério? Sim!")
    p = subtitles.gerar_ass(pals, Timeline.de_clip(0, 5), Legenda(), 1080, 1920, tmp_path / "a.ass")
    limpo = " ".join(re.sub(r"\{[^}]*\}", "", t) for _, _, t in _eventos(p.read_text(encoding="utf-8")))
    assert "," not in limpo and ":" not in limpo and "." not in limpo
    assert "Sério?" in limpo and "Sim!" in limpo
    p = subtitles.gerar_ass(pals, Timeline.de_clip(0, 5), Legenda(remover_pontuacao=False), 1080, 1920, tmp_path / "b.ass")
    assert "Olha," in p.read_text(encoding="utf-8")


# ---- transcrição -------------------------------------------------------------------------------------
def _seg(texto: str, prob: float = 0.9) -> dict:
    ws = [{"texto": w, "inicio": k * 0.3, "fim": k * 0.3 + 0.2, "prob": prob} for k, w in enumerate(texto.split())]
    return {"inicio": 0.0, "fim": ws[-1]["fim"], "texto": texto, "palavras": ws}


def test_alucinacoes_do_whisper_saem_da_transcricao():
    out = limpar_alucinacoes([
        _seg("Legendas pela comunidade Amara.org"),
        _seg("Obrigado por assistir!", prob=0.3),
        _seg("Obrigado por assistir!"),  # dito com certeza: fica
        _seg("não não não não não sei"),
        _seg("eu vou eu vou eu vou eu vou lá"),
        _seg("é é isso"),  # repetição normal de fala: fica
    ])
    assert [s["texto"] for s in out] == ["Obrigado por assistir!", "não sei", "eu vou lá", "é é isso"]
