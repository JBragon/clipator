"""Camada 1 da detecção de pontos virais: candidatos e nota local, sem IA.

As janelas começam em início de frase e terminam em fim de frase; cada uma
recebe uma nota de 0 a 100, soma ponderada dos sinais com os pesos do
regras.md do canal.

dedupe_overlapping e snap_clip_to_words foram adaptados de
openshorts/clip_selection.py, MIT License, Copyright (c) 2024 OpenShorts.
Ver THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .models import Regras
from .textutil import STOPWORDS, contem_termo, normalizar, termos_relevantes, tokens

# ---- ganchos -----------------------------------------------------------------
GANCHOS = [
    # português
    r"ningu[eé]m (te )?(conta|fala|sabe)", r"o segredo", r"a verdade", r"voc[eê] (sabia|n[aã]o sabe)",
    r"nunca", r"jamais", r"o maior", r"o pior", r"o melhor", r"o erro", r"cuidado", r"aten[cç][aã]o",
    r"olha (s[oó]|isso)", r"isso (aqui )?muda", r"ningu[eé]m", r"por que", r"porqu[eê]", r"como (eu|voc[eê])",
    r"deixa eu (te )?(contar|falar)", r"vou (te )?(contar|falar)", r"sabe o que", r"imagina", r"pol[eê]mic",
    r"absurd", r"inacredit[aá]vel", r"chocante", r"revel", r"confess", r"n[aã]o acredit", r"mentira",
    r"dinheiro", r"milh[aãõo]+", r"bilh[aãõo]+", r"reais", r"r\$",
    # inglês
    r"nobody (tells|talks|knows)", r"the secret", r"the truth", r"did you know", r"never", r"the biggest",
    r"the worst", r"the best", r"the mistake", r"here'?s (why|how|what)", r"this changes", r"why ",
    r"let me tell you", r"crazy", r"insane", r"unbelievable", r"million", r"billion",
]
_GANCHO_RE = re.compile("|".join(f"(?:{g})" for g in GANCHOS), re.IGNORECASE)
_NUM_RE = re.compile(r"\d|\b(um|dois|tr[eê]s|quatro|cinco|dez|cem|mil|one|two|three|ten|hundred|thousand)\b", re.I)

CONECTIVOS_INICIO = {
    "e", "mas", "então", "entao", "aí", "ai", "porque", "pq", "que", "né", "ne", "tipo", "ou", "daí", "dai", "só", "so",
    "and", "but", "because", "or", "that", "which", "also",
}

FIM_FRASE = re.compile(r"[.!?…]$")

# frases que fecham uma ideia ("por isso…", "ou seja…", "é isso")
MARCADORES_CONCLUSAO = re.compile(
    r"\b(ent[aã]o|ou seja|por isso|resumindo|em resumo|[eé] isso|entendeu|a li[cç][aã]o|no final|no fim|enfim|"
    r"portanto|conclus[aã]o|moral da hist[oó]ria|foi isso|e pronto|acabou|so that'?s|in the end|the lesson)\b",
    re.IGNORECASE)
# frases que já abrem o próximo assunto: o corte não deve terminar nelas
MARCADORES_TRANSICAO = re.compile(
    r"\b(mudando de assunto|outro assunto|outra coisa|vamos para|vamos pra|agora vamos|bora pra|pr[oó]ximo (assunto|tema|t[oó]pico)|"
    r"falando nisso|aproveitando|let'?s move on|moving on|next topic)\b",
    re.IGNORECASE)


@dataclass
class Frase:
    inicio: float
    fim: float
    texto: str
    n_palavras: int
    pausa_depois: float
    pontuada: bool
    hits_chave: int = 0
    termos: list[str] = field(default_factory=list)


def montar_frases(palavras: list[dict], pausa_quebra: float = 0.7, max_frase: float = 25.0) -> list[Frase]:
    """Agrupa palavras em frases: quebra em pontuação final ou pausa longa."""
    frases: list[Frase] = []
    atual: list[dict] = []

    def fechar(prox_inicio: float | None) -> None:
        if not atual:
            return
        texto = " ".join(w["texto"] for w in atual)
        fim = atual[-1]["fim"]
        pausa = (prox_inicio - fim) if prox_inicio is not None else 2.0
        frases.append(Frase(atual[0]["inicio"], fim, texto, len(atual), max(0.0, pausa), bool(FIM_FRASE.search(texto))))
        atual.clear()

    for i, w in enumerate(palavras):
        atual.append(w)
        prox = palavras[i + 1]["inicio"] if i + 1 < len(palavras) else None
        gap = (prox - w["fim"]) if prox is not None else 99
        longa = w["fim"] - atual[0]["inicio"] >= max_frase
        if FIM_FRASE.search(w["texto"]) or gap >= pausa_quebra or longa:
            fechar(prox)
    fechar(None)
    return frases


# ---- notas dos sinais (0 a 1) -------------------------------------------------
def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def nota_gancho(texto_inicio: str) -> tuple[float, str | None]:
    if not texto_inicio:
        return 0.0, None
    s = 0.0
    m = _GANCHO_RE.search(texto_inicio)
    if m:
        s += 0.6
    if "?" in texto_inicio:
        s += 0.3
    if _NUM_RE.search(texto_inicio):
        s += 0.2
    primeira = normalizar(texto_inicio.split()[0]) if texto_inicio.split() else ""
    if primeira in CONECTIVOS_INICIO:
        s -= 0.3
    return max(0.0, min(1.0, s)), (m.group(0) if m else None)


def nota_ritmo(n_palavras: int, dur: float, pausas_longas: float) -> float:
    if dur <= 0:
        return 0.0
    wps = n_palavras / dur
    # Fala densa em PT/EN fica entre 2,3 e 3,8 palavras por segundo.
    base = math.exp(-((wps - 3.0) ** 2) / (2 * 0.8 ** 2))
    return max(0.0, base - min(0.5, pausas_longas / dur * 2))


def nota_historia(primeira: Frase, ultima: Frase) -> float:
    s = 0.0
    if ultima.pausa_depois >= 0.5:
        s += 0.45
    if ultima.pontuada and not ultima.texto.endswith("?"):
        s += 0.3
    p = normalizar(primeira.texto.split()[0]) if primeira.texto.split() else ""
    if p not in CONECTIVOS_INICIO:
        s += 0.25
    return min(1.0, s)


def termina_bem(f: Frase, ultima: bool = False) -> bool:
    """Um corte pode terminar nesta frase: acabou de verdade (pontuação ou pausa) e não é pergunta no ar."""
    if ultima:
        return True
    if f.texto.rstrip().endswith("?"):
        return False
    return f.pontuada or f.pausa_depois >= 0.6


def nota_fechamento(ctx: "Contexto", i: int, j: int) -> float:
    return explicar_fechamento(ctx, i, j)[0]


def explicar_fechamento(ctx: "Contexto", i: int, j: int) -> tuple[float, list[str]]:
    """0 a 1: o quanto o corte fecha o assunto, e por quê (cada frase com o sinal + ou −).

    Sobe com frase final completa, pausa depois, marcador de conclusão ("por isso", "ou seja"),
    mudança de assunto logo em seguida e próxima frase que não continua a ideia ("e", "mas", "porque").
    Cai se a última frase é pergunta (a resposta ficou de fora) ou se o corte começa logo depois de
    uma pergunta que ele responde.
    """
    fr = ctx.frases
    ult = fr[j]
    tem_proxima = j + 1 < len(fr)
    if ult.texto.rstrip().endswith("?") and tem_proxima:
        return 0.0, ["− termina numa pergunta e a resposta fica de fora"]
    s = 0.0
    por_que: list[str] = []
    if ult.pontuada:
        s += 0.25
        por_que.append("+ termina com a frase completa")
    if ult.pausa_depois >= 0.6:
        s += 0.2
        por_que.append(f"+ pausa de {ult.pausa_depois:.1f} s depois do fim")
    m = MARCADORES_CONCLUSAO.search(ult.texto) or (MARCADORES_CONCLUSAO.search(fr[j - 1].texto) if j > i else None)
    if m:
        s += 0.25
        por_que.append(f"+ tem conclusão (“{m.group(0)}”)")
    t = MARCADORES_TRANSICAO.search(ult.texto)
    if t:  # a última frase já puxa o próximo assunto
        s -= 0.4
        por_que.append(f"− a última frase já puxa outro assunto (“{t.group(0)}”)")
    if tem_proxima:
        palavras = fr[j + 1].texto.split()
        primeira = normalizar(palavras[0]) if palavras else ""
        if primeira in CONECTIVOS_INICIO:
            s -= 0.25
            por_que.append(f"− a frase seguinte continua a ideia (começa com “{palavras[0]}”)")
        else:
            s += 0.15
            por_que.append("+ a frase seguinte não continua a ideia")
        if ctx.muda_de_assunto(j):
            s += 0.15
            por_que.append("+ logo depois o assunto muda")
    else:
        s += 0.3
        por_que.append("+ vai até o fim do vídeo")
    if i > 0 and fr[i - 1].texto.rstrip().endswith("?"):
        s -= 0.3
        por_que.append("− começa logo depois de uma pergunta que responde")
    return max(0.0, min(1.0, s)), por_que


def ajustar_a_frases(ini: float, fim: float, frases: list[Frase], dur_max: float, dur_min: float = 5.0) -> tuple[float, float]:
    """Leva início e fim propostos (pela IA) para fronteiras de frase: começa onde uma frase começa e
    termina numa frase que fecha; se não couber em dur_max, mantém o que veio."""
    if not frases:
        return ini, fim
    i = min(range(len(frases)), key=lambda k: abs(frases[k].inicio - ini))
    finais = [k for k in range(i, len(frases)) if termina_bem(frases[k], k == len(frases) - 1)]
    if not finais:
        return ini, fim
    # a frase onde o fim proposto cai: se é uma pergunta, o corte vai até a resposta
    k_fim = max((k for k in range(i, len(frases)) if frases[k].inicio <= fim), default=i)
    depois = [k for k in finais if k > k_fim]
    if frases[k_fim].texto.rstrip().endswith("?") and depois:
        j = depois[0]
    else:
        # a frase que fecha mais perto do fim proposto; voltar custa mais que avançar, para o ajuste
        # não comer a conclusão que a IA quis incluir
        j = min(finais, key=lambda k: (fim - frases[k].fim) * 1.5 if frases[k].fim < fim else frases[k].fim - fim)
    a, b = frases[i].inicio, frases[j].fim
    if not (dur_min <= b - a <= dur_max):
        return ini, fim
    return a, b


# ---- contexto pré-calculado --------------------------------------------------
class Contexto:
    def __init__(self, transcricao: dict, sinais: dict | None, metadados: dict | None, regras: Regras,
                 palavras_chave_canal: list[str]):
        from .transcribe import palavras as _palavras

        self.palavras = _palavras(transcricao)
        self.duracao = float(transcricao.get("duracao") or (self.palavras[-1]["fim"] if self.palavras else 0))
        self.frases = montar_frases(self.palavras)
        self.regras = regras
        self.inicios_palavras = [w["inicio"] for w in self.palavras]

        # termos: palavras-chave do canal + termos que se destacam no vídeo
        blocos = self._blocos_texto(60.0)
        self.termos_video = [t for t, _ in termos_relevantes(blocos, 25)]
        self.palavras_chave = [k for k in (palavras_chave_canal + list(regras.palavras_chave)) if k.strip()]
        kw_norm = [normalizar(k) for k in self.palavras_chave]
        termos_norm = set(self.termos_video)
        for f in self.frases:
            tn = " " + " ".join(normalizar(t) for t in f.texto.split()) + " "
            hits = [k for k, kn in zip(self.palavras_chave, kw_norm) if kn and contem_termo(tn, kn)]
            vid = [t for t in tokens(f.texto) if t in termos_norm]
            f.hits_chave = len(hits) * 2 + len(vid)
            f.termos = hits + vid

        # somas acumuladas por frase
        self.cum_palavras = np.cumsum([0] + [f.n_palavras for f in self.frases])
        self.cum_hits = np.cumsum([0] + [f.hits_chave for f in self.frases])
        gaps = [0.0]
        for a, b in zip(self.frases, self.frases[1:]):
            g = b.inicio - a.fim
            gaps.append(g if g > 1.0 else 0.0)
        self.cum_pausas = np.cumsum([0.0] + gaps)

        # energia em z-score com soma acumulada
        sinais = sinais or {}
        self.passo = float(sinais.get("passo") or 0.25)
        db = np.array(sinais.get("energia_db") or [], dtype=np.float32)
        if len(db):
            mu, sd = float(sinais.get("media_db", db.mean())), float(sinais.get("desvio_db", db.std()) or 1.0)
            z = np.clip((db - mu) / max(sd, 1e-3), -3, 3)
            z[db < -60] = -1.0  # silêncio não conta como energia
            self.cum_z = np.concatenate([[0.0], np.cumsum(z)])
        else:
            self.cum_z = None

        # picos de reação sem fala transcrita por cima
        self.reacoes: list[float] = []
        for a, b in sinais.get("picos", []) or []:
            coberto = self._cobertura_fala(a, b)
            if coberto < 0.5:
                self.reacoes.append((a + b) / 2)
        self.reacoes.sort()

        meta = metadados or {}
        self.capitulos = sorted(float(c["inicio"]) for c in meta.get("capitulos", []) if c.get("inicio") is not None)
        heat = meta.get("mais_repetidos") or []
        self.heat = [(float(h["inicio"]), float(h["fim"]), float(h.get("valor") or 0)) for h in heat if h.get("inicio") is not None]
        self.temas_proibidos = [normalizar(t) for t in regras.temas_proibidos if t.strip()]
        # raízes das palavras de conteúdo de cada frase, para ver quando o assunto muda
        self.conteudo = [{normalizar(t)[:5] for t in tokens(f.texto) if t not in STOPWORDS and len(t) > 3}
                         for f in self.frases]

    def muda_de_assunto(self, j: int) -> bool:
        """As frases depois de j falam de outra coisa (pouca palavra em comum com as de antes)."""
        antes = set().union(*self.conteudo[max(0, j - 2): j + 1])
        depois = set().union(*self.conteudo[j + 1: j + 4])
        if not antes or not depois:
            return True
        return len(antes & depois) / len(antes | depois) < 0.1

    def _blocos_texto(self, tam: float) -> list[str]:
        blocos: list[str] = []
        atual, ini = [], 0.0
        for w in self.palavras:
            if w["inicio"] - ini > tam and atual:
                blocos.append(" ".join(atual))
                atual, ini = [], w["inicio"]
            atual.append(w["texto"])
        if atual:
            blocos.append(" ".join(atual))
        return blocos

    def _cobertura_fala(self, a: float, b: float) -> float:
        i = bisect.bisect_left(self.inicios_palavras, a - 2)
        coberto = 0.0
        while i < len(self.palavras) and self.palavras[i]["inicio"] < b:
            w = self.palavras[i]
            coberto += max(0.0, min(b, w["fim"]) - max(a, w["inicio"]))
            i += 1
        return coberto / max(b - a, 1e-3)

    def energia_media(self, a: float, b: float) -> float | None:
        if self.cum_z is None:
            return None
        n = len(self.cum_z) - 1
        i, j = int(a / self.passo), int(math.ceil(b / self.passo))
        i, j = max(0, min(i, n)), max(0, min(j, n))
        if j <= i:
            return None
        return float((self.cum_z[j] - self.cum_z[i]) / (j - i))

    def n_reacoes(self, a: float, b: float) -> int:
        return bisect.bisect_left(self.reacoes, b) - bisect.bisect_left(self.reacoes, a)

    def plataforma(self, a: float, b: float) -> tuple[float, str | None]:
        s, motivo = 0.0, None
        if self.heat:
            tot, peso = 0.0, 0.0
            for hs, he, v in self.heat:
                ov = min(b, he) - max(a, hs)
                if ov > 0:
                    tot += v * ov
                    peso += ov
            if peso:
                media = tot / peso
                s = max(s, min(1.0, media))
                if media > 0.5:
                    motivo = "Trecho entre os mais repetidos do YouTube"
        for c in self.capitulos:
            if abs(c - a) <= 5:
                s = max(s, 0.6)
                motivo = motivo or "Começa no início de um capítulo"
                break
        return s, motivo

    def proibido(self, texto: str) -> bool:
        if not self.temas_proibidos:
            return False
        tn = " " + " ".join(normalizar(t) for t in texto.split()) + " "
        return any(contem_termo(tn, t) for t in self.temas_proibidos)

    def texto_inicio(self, a: float, segundos: float = 3.0) -> str:
        i = bisect.bisect_left(self.inicios_palavras, a - 0.01)
        out = []
        while i < len(self.palavras) and self.palavras[i]["inicio"] < a + segundos:
            out.append(self.palavras[i]["texto"])
            i += 1
        return " ".join(out)


MOTIVOS = {
    "gancho": "Começa com gancho",
    "energia": "Voz mais intensa que a média do vídeo",
    "reacoes": "Tem picos de reação (risadas, gritos)",
    "ritmo": "Fala densa, sem enrolação",
    "historia": "Começa e termina em frase completa",
    "palavras_chave": "Fala de assuntos do canal",
    "plataforma": "Sinal da plataforma",
    "fechamento": "Fecha o assunto (termina numa conclusão)",
}


def _pontuar(ctx: Contexto, i: int, j: int, modo: str, fechamento: float | None = None) -> dict[str, Any] | None:
    fr = ctx.frases
    a, b = fr[i].inicio, fr[j].fim
    dur = b - a
    n_pal = int(ctx.cum_palavras[j + 1] - ctx.cum_palavras[i])
    pausas = float(ctx.cum_pausas[j + 1] - ctx.cum_pausas[i + 1]) if j > i else 0.0
    hits = int(ctx.cum_hits[j + 1] - ctx.cum_hits[i])

    gancho, trecho_gancho = nota_gancho(ctx.texto_inicio(a))
    e = ctx.energia_media(a, b)
    energia = _sig((e or 0.0) * 2.0) if e is not None else 0.5
    nr = ctx.n_reacoes(a, b)
    reacoes = min(1.0, nr / max(1.0, dur / 30))
    ritmo = nota_ritmo(n_pal, dur, pausas)
    historia = nota_historia(fr[i], fr[j])
    densidade = hits / max(1, n_pal) * 25
    palavras_chave = min(1.0, densidade)
    plat, motivo_plat = ctx.plataforma(a, b)

    fech, por_que_fecha = explicar_fechamento(ctx, i, j)
    if fechamento is not None:
        fech = fechamento
    sinais = {"gancho": gancho, "energia": energia, "reacoes": reacoes, "ritmo": ritmo,
              "historia": historia, "palavras_chave": palavras_chave, "plataforma": plat, "fechamento": fech}
    pesos = ctx.regras.pesos.model_dump()
    if modo == "longo":  # num corte longo o gancho pesa menos e o tema mais
        pesos = {**pesos, "gancho": pesos["gancho"] * 0.4, "palavras_chave": pesos["palavras_chave"] * 1.5}
    if not ctx.heat and not ctx.capitulos:
        pesos["plataforma"] = 0  # sem dado de plataforma, o sinal não entra na média
    if e is None:
        pesos["energia"] = 0
        pesos["reacoes"] = 0
    total_peso = sum(pesos.values()) or 1
    nota = 100 * sum(pesos[k] * v for k, v in sinais.items()) / total_peso
    nota_sinais = nota

    # preferência pela duração-alvo: abaixo dela o corte perde mais (ideia pela metade) do que acima
    if modo == "curto":
        lo, hi, alvo = ctx.regras.duracao_min, ctx.regras.duracao_max, ctx.regras.alvo_curto()
    else:
        lo, hi = ctx.regras.corte_longo_min, ctx.regras.corte_longo_max
        alvo = (lo + hi) / 2
    nota *= fator_duracao(dur, lo, hi, alvo)
    if modo == "curto" and dur > hi:  # passou do máximo para fechar o assunto: vale, mas custa um pouco
        ext = max(hi + 1, ctx.regras.teto_curto())
        nota *= 1 - 0.12 * min(1.0, (dur - hi) / (ext - hi))

    contrib = sorted(((pesos[k] * v, k) for k, v in sinais.items() if v > 0.3), reverse=True)
    motivos = []
    for _, k in contrib[:3]:
        if k == "gancho" and trecho_gancho:
            motivos.append(f"Começa com gancho (“{trecho_gancho}”)")
        elif k == "reacoes" and nr:
            motivos.append(f"{nr} pico(s) de reação, como risada ou grito")
        elif k == "ritmo":
            motivos.append(f"Fala densa: {n_pal / max(dur, 1):.1f} palavras/s")
        elif k == "palavras_chave":
            termos = []
            for f in fr[i : j + 1]:
                for t in f.termos:
                    if t not in termos:
                        termos.append(t)
            motivos.append("Fala de: " + ", ".join(termos[:4]) if termos else MOTIVOS[k])
        elif k == "plataforma" and motivo_plat:
            motivos.append(motivo_plat)
        else:
            motivos.append(MOTIVOS[k])

    return {
        "inicio": a, "fim": b, "duracao": round(dur, 2), "nota": round(nota, 1),
        "sinais": {k: round(v, 3) for k, v in sinais.items()}, "motivos": motivos,
        # para a interface explicar a nota: pesos usados, ajuste pela duração e como o fim foi escolhido
        "pesos": {k: round(float(p), 2) for k, p in pesos.items()},
        "fator_duracao": round(nota / nota_sinais, 3) if nota_sinais else 1.0,
        "fechamento": por_que_fecha,
    }


PENALIDADE_CURTO = 0.3  # um corte na duração mínima perde 30% da nota; na duração-alvo, nada
PENALIDADE_LONGO = 0.05  # entre o alvo e a máxima, só 5%


def fator_duracao(dur: float, lo: float, hi: float, alvo: float) -> float:
    """Multiplicador da nota pela duração (1 no alvo).

    Antes a nota preferia o meio da faixa com só 10% de diferença, e os sinais médios (energia, densidade
    de palavras-chave) sobem em janelas curtas: o corte de 20 a 30 s ganhava do corte que contava a
    história inteira. Agora o curto perde até 30% e o longo, até a máxima, quase nada.
    """
    alvo = max(lo, min(hi, alvo))
    if dur < alvo:
        return 1 - PENALIDADE_CURTO * min(1.0, (alvo - dur) / max(1.0, alvo - lo))
    return 1 - PENALIDADE_LONGO * min(1.0, (min(dur, hi) - alvo) / max(1.0, hi - alvo))


def _sobreposicao(a: dict, b: dict) -> float:
    ov = min(a["fim"], b["fim"]) - max(a["inicio"], b["inicio"])
    if ov <= 0:
        return 0.0
    return ov / max(1e-6, min(a["fim"] - a["inicio"], b["fim"] - b["inicio"]))


def dedupe_overlapping(cands: list[dict], ratio: float = 0.25, limite: int | None = None) -> list[dict]:
    """Mantém o de maior nota quando dois candidatos dividem mais de `ratio` do menor."""
    kept: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["nota"]):
        if all(_sobreposicao(c, k) < ratio for k in kept):
            kept.append(c)
            if limite and len(kept) >= limite:
                break
    return kept


def snap_to_words(inicio: float, fim: float, palavras: list[dict], duracao: float,
                  max_lead: float = 0.35, max_tail: float = 0.45, janela: float = 1.5) -> tuple[float, float]:
    """Encaixa início e fim em palavras inteiras, com um respiro de silêncio."""
    if not palavras:
        return round(inicio, 3), round(fim, 3)
    starts = [w["inicio"] for w in palavras]
    ends = [w["fim"] for w in palavras]
    ns, ne = inicio, fim
    cands = [s for s in starts if abs(s - inicio) <= janela]
    if cands:
        ws = min(cands, key=lambda s: abs(s - inicio))
        k = bisect.bisect_left(starts, ws)
        gap = ws - ends[k - 1] if k > 0 else max_lead * 2
        ns = max(0.0, ws - min(max_lead, max(0.0, gap) / 2))
    cands = [e for e in ends if abs(e - fim) <= janela]
    if cands:
        we = min(cands, key=lambda e: abs(e - fim))
        k = bisect.bisect_right(starts, we)
        gap = starts[k] - we if k < len(starts) else max_tail * 2
        ne = min(duracao or we + max_tail, we + min(max_tail, max(0.0, gap) / 2))
    if ne <= ns:
        return round(inicio, 3), round(fim, 3)
    return round(ns, 3), round(ne, 3)


def _janelas_curtas(ctx: Contexto) -> list[dict]:
    lo, hi = ctx.regras.duracao_min, ctx.regras.duracao_max
    ext = ctx.regras.teto_curto()
    fr = ctx.frases
    out = []
    for i in range(len(fr)):
        for j in range(i, len(fr)):
            dur = fr[j].fim - fr[i].inicio
            if dur > ext:
                break
            if dur < lo:
                continue
            # só termina onde a frase acaba de verdade, e nunca numa pergunta cuja resposta vem depois
            if not termina_bem(fr[j], j + 1 == len(fr)):
                continue
            fech = nota_fechamento(ctx, i, j)
            if dur > hi and fech < 0.7:  # passa do máximo só se for para fechar o assunto
                continue
            c = _pontuar(ctx, i, j, "curto", fech)
            if c:
                out.append(c)
    return out


def _temas(ctx: Contexto, bloco: float = 60.0) -> list[tuple[int, int]]:
    """Divide as frases em temas: capítulos, se houver, ou quebras de assunto (TextTiling simplificado)."""
    fr = ctx.frases
    if not fr:
        return []
    if len(ctx.capitulos) >= 2:
        cortes = ctx.capitulos
    else:
        # vetores de palavras por bloco de ~60 s
        blocos: list[tuple[int, int]] = []
        ini = 0
        for k, f in enumerate(fr):
            if f.fim - fr[ini].inicio >= bloco:
                blocos.append((ini, k))
                ini = k + 1
        if ini < len(fr):
            blocos.append((ini, len(fr) - 1))
        vocab: dict[str, int] = {}
        vecs = []
        for a, b in blocos:
            cnt: dict[int, float] = {}
            for f in fr[a : b + 1]:
                for t in tokens(f.texto):
                    if t in STOPWORDS or len(t) <= 3:
                        continue
                    idx = vocab.setdefault(t, len(vocab))
                    cnt[idx] = cnt.get(idx, 0) + 1
            vecs.append(cnt)

        def cos(u: dict, v: dict) -> float:
            num = sum(u[k] * v.get(k, 0) for k in u)
            den = math.sqrt(sum(x * x for x in u.values())) * math.sqrt(sum(x * x for x in v.values()))
            return num / den if den else 0.0

        sims = []
        for k in range(1, len(vecs)):
            esq: dict[int, float] = {}
            dir_: dict[int, float] = {}
            for v in vecs[max(0, k - 2) : k]:
                for t, c in v.items():
                    esq[t] = esq.get(t, 0) + c
            for v in vecs[k : k + 2]:
                for t, c in v.items():
                    dir_[t] = dir_.get(t, 0) + c
            sims.append(cos(esq, dir_))
        cortes = []
        if sims:
            arr = np.array(sims)
            lim = arr.mean() - 0.5 * arr.std()
            for k, s in enumerate(sims, start=1):
                vizinhos = sims[max(0, k - 2) : k + 1]
                if s <= lim and s == min(vizinhos):
                    cortes.append(fr[blocos[k][0]].inicio)
    # converte instantes em faixas de frases
    temas, ini = [], 0
    for c in sorted(cortes):
        k = next((n for n, f in enumerate(fr) if f.inicio >= c - 0.01), None)
        if k is None or k <= ini:
            continue
        temas.append((ini, k - 1))
        ini = k
    temas.append((ini, len(fr) - 1))
    return temas


def _janelas_longas(ctx: Contexto) -> list[dict]:
    lo, hi = ctx.regras.corte_longo_min, ctx.regras.corte_longo_max
    temas = _temas(ctx)
    fr = ctx.frases
    out = []
    for a in range(len(temas)):
        for b in range(a, len(temas)):
            i, j = temas[a][0], temas[b][1]
            dur = fr[j].fim - fr[i].inicio
            if dur > hi:
                break
            if dur >= lo:
                c = _pontuar(ctx, i, j, "longo")
                if c:
                    out.append(c)
    if not out and ctx.duracao >= lo:
        # sem quebras de tema boas: janelas por frases mesmo, passo de ~2 min
        i = 0
        while i < len(fr):
            j = i
            while j + 1 < len(fr) and fr[j + 1].fim - fr[i].inicio <= hi:
                j += 1
            if fr[j].fim - fr[i].inicio >= lo:
                out.append(_pontuar(ctx, i, j, "longo"))
            prox = next((k for k in range(i + 1, len(fr)) if fr[k].inicio >= fr[i].inicio + 120), None)
            if prox is None:
                break
            i = prox
    return [c for c in out if c]


def gerar(transcricao: dict, sinais: dict | None, metadados: dict | None, regras: Regras,
          palavras_chave_canal: list[str] | None = None, modo: str = "curto", limite: int | None = None) -> list[dict]:
    """Gera candidatos ordenados pela nota local.

    modo: "curto" (Shorts, entre duracao_min e duracao_max) ou "longo" (corte
    16:9 de 8 a 20 min por padrão).
    """
    ctx = Contexto(transcricao, sinais, metadados, regras, palavras_chave_canal or [])
    if not ctx.frases:
        return []
    brutas = _janelas_curtas(ctx) if modo == "curto" else _janelas_longas(ctx)
    brutas = [c for c in brutas if not ctx.proibido(_texto(ctx, c["inicio"], c["fim"]))]
    if limite is None:
        limite = max(regras.quantidade * 3, 15) if modo == "curto" else max(3, regras.quantidade)
    escolhidos = dedupe_overlapping(brutas, ratio=0.25, limite=limite)
    encaixados = []
    for c in escolhidos:
        ini, fim = snap_to_words(c["inicio"], c["fim"], ctx.palavras, ctx.duracao)
        encaixados.append({**c, "inicio": ini, "fim": fim})
    # encaixar nas palavras alarga um pouco os cortes: confere a sobreposição de novo
    escolhidos = dedupe_overlapping(encaixados, ratio=0.25)
    out = []
    prefixo = "c" if modo == "curto" else "l"
    for n, c in enumerate(escolhidos, start=1):
        ini, fim = c["inicio"], c["fim"]
        out.append({
            "id": f"{prefixo}{n:02d}",
            **c,
            "inicio": ini,
            "fim": fim,
            "duracao": round(fim - ini, 2),
            "texto": _texto(ctx, c["inicio"], c["fim"]),
            "modo": modo,
            "fonte": "local",
        })
    return out


def _texto(ctx: Contexto, a: float, b: float) -> str:
    i = bisect.bisect_left(ctx.inicios_palavras, a - 0.01)
    out = []
    while i < len(ctx.palavras) and ctx.palavras[i]["inicio"] < b - 0.01:
        out.append(ctx.palavras[i]["texto"])
        i += 1
    return " ".join(out)


def texto_do_trecho(transcricao: dict, a: float, b: float) -> str:
    from .transcribe import palavras as _palavras

    return " ".join(w["texto"] for w in _palavras(transcricao) if a - 0.01 <= w["inicio"] < b - 0.01)
