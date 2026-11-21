"""Abertura com ganchos: os momentos mais fortes do próprio corte, em preto e branco, antes do corte inteiro.

É o formato dos cortes de podcast que abrem com 4 a 8 s das falas mais quentes (às vezes a troca entre os
dois convidados) sem cor, viram para a cor com um clarão branco e então mostram o corte do começo ao fim.

Nos cortes longos (16:9) o gancho segue o padrão dos canais de cortes grandes: um trecho corrido de 10 a 20 s,
a fala mais forte do corte, em cor ou em preto e branco, e só depois o corte desde o começo. Entre os dois pode
entrar a vinheta do canal (canal.md: vinheta), ou ela abre o vídeo antes de tudo. Quando a IA leu o corte longo
na análise, o trecho que ela apontou vem nos `trechos`; sem IA, `escolher_bloco` acha o trecho pela fala e pela
energia.

Tudo local e sem IA: os momentos saem da energia do áudio (sinais.json) e da fala (gatilhos de gancho,
exclamação, pergunta, número, palavras destacadas). O estilo pode fixar os trechos à mão
(`abertura.trechos`, em segundos do vídeo original).

A abertura é montada numa segunda passada sobre o clip já renderizado: assim os ganchos já vêm
reenquadrados, com legenda e áudio normalizado, iguais ao trecho que aparece depois, e o render
principal não precisa mudar. Cada gancho é lido com busca na entrada (-ss antes do -i), sem segurar
o vídeo inteiro na memória.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import media
from .candidates import CONECTIVOS_INICIO, _GANCHO_RE, _NUM_RE, montar_frases
from .models import Abertura
from .textutil import normalizar
from .timeline import Timeline

PAD_ANTES = 0.08
PAD_DEPOIS = 0.15
DURACAO_MIN_TRECHO = 1.0
FOLGA_ENTRE = 1.0  # dois ganchos colados viram um só; separados, precisam de 1 s entre eles
BLOCO_MIN = 8.0  # gancho corrido (cortes longos): no mínimo 8 s de fala seguida
FOLGA_BLOCO = 1.2  # pausa maior que isso entre duas frases quebra o bloco: o gancho é uma fala só, sem emenda


GANCHOS_LONGO = ("nenhum", "cor", "preto-e-branco")
VINHETAS = ("nenhuma", "canal", "inicio", "depois-do-gancho")
# o gancho forte dos cortes longos: um trecho corrido de 10 a 20 s, perto de 15 s, tirado dos 90% finais do corte
ABERTURA_LONGA = {"ativa": True, "duracao": 15.0, "max_trechos": 1, "max_trecho": 20.0, "inicio_minimo": 0.1}


def ajustes_corte_longo(gancho: str = "cor", vinheta: str = "canal") -> dict:
    """Os ajustes de estilo que o passo 3 aplica só nos cortes longos: o gancho forte (em cor, em preto e branco
    ou nenhum) e onde entra a vinheta do canal. Valor desconhecido dá ValueError."""
    if gancho not in GANCHOS_LONGO:
        raise ValueError(f"Gancho dos cortes longos: use {', '.join(GANCHOS_LONGO)}")
    if vinheta not in VINHETAS:
        raise ValueError(f"Vinheta dos cortes longos: use {', '.join(VINHETAS)}")
    if gancho == "nenhum":
        ab: dict = {"ativa": False}
    else:
        pb = gancho == "preto-e-branco"
        ab = {**ABERTURA_LONGA, "preto_e_branco": pb, "contraste": 1.12 if pb else 1.0}
    return {"abertura": ab, "vinheta": vinheta}


@dataclass
class Gancho:
    inicio: float  # tempo do clip
    fim: float
    texto: str
    nota: float


def energia_do_clip(sinais: dict | None, tl: Timeline) -> Callable[[float, float], float] | None:
    """Função (a, b) em tempo do clip -> energia relativa (z) do trecho, pela energia do vídeo original."""
    if not sinais or not sinais.get("energia_db"):
        return None
    db = np.asarray(sinais["energia_db"], dtype=np.float32)
    passo = float(sinais.get("passo", 0.25)) or 0.25

    def amostras(a: float, b: float) -> np.ndarray:
        ts = np.arange(a, max(a + passo, b), passo)
        idx = [int(tl.para_original(float(t)) / passo) for t in ts]
        idx = [i for i in idx if 0 <= i < len(db)]
        return db[idx] if idx else np.zeros(0, dtype=np.float32)

    todo = amostras(0.0, tl.duracao)
    voz = todo[todo > -60] if len(todo) else todo  # silêncio não puxa a média para baixo
    if len(voz) < 4:
        return None
    mu, sd = float(voz.mean()), float(voz.std()) or 1.0

    def z(a: float, b: float) -> float:
        x = amostras(a, b)
        x = x[x > -60]
        if not len(x):
            return -2.0
        topo = np.sort(x)[len(x) // 2:]  # a metade mais alta: o grito pesa mais que a respiração
        return float(np.clip((topo.mean() - mu) / sd, -2.0, 3.0))

    return z


def nota_fala(texto: str, n_palavras: int, dur: float, destaque: re.Pattern | None) -> float:
    s = 0.0
    if _GANCHO_RE.search(texto):
        s += 0.8
    if "!" in texto:
        s += 0.5
    if "?" in texto:
        s += 0.4
    if _NUM_RE.search(texto):
        s += 0.3
    if destaque is not None:
        s += min(0.9, 0.3 * sum(1 for p in texto.split() if destaque.match(p)))
    primeira = normalizar(texto.split()[0]) if texto.split() else ""
    if primeira in CONECTIVOS_INICIO:
        s -= 0.4
    if dur > 0 and n_palavras / dur > 3.2:  # fala acelerada costuma ser fala exaltada
        s += 0.2
    return s


def bloco_corrido(cfg: Abertura) -> bool:
    """Um momento só e mais longo que uma frase: o gancho dos cortes longos, um trecho corrido de várias frases."""
    return cfg.max_trechos == 1 and cfg.max_trecho > BLOCO_MIN


def escolher(pals_clip: list[dict], duracao: float, cfg: Abertura,
             energia: Callable[[float, float], float] | None = None,
             destaque: re.Pattern | None = None) -> list[Gancho]:
    """Os momentos da abertura, em ordem cronológica, em tempo do clip. Vazio se o corte não tem fala que sirva."""
    if not pals_clip or duracao < cfg.duracao + 4:
        return []
    if bloco_corrido(cfg):
        return escolher_bloco(pals_clip, duracao, cfg, energia, destaque)
    frases = montar_frases(pals_clip, pausa_quebra=0.5, max_frase=cfg.max_trecho)
    lim = duracao * cfg.inicio_minimo
    cands: list[Gancho] = []
    for f in frases:
        dur = f.fim - f.inicio
        if dur < DURACAO_MIN_TRECHO or f.n_palavras < 3 or f.inicio < lim:
            continue
        nota = nota_fala(f.texto, f.n_palavras, dur, destaque) + (energia(f.inicio, f.fim) if energia else 0.0)
        cands.append(Gancho(f.inicio, f.fim, f.texto, nota))
    if not cands:
        return []
    alvo = cfg.duracao
    escolhidos: list[Gancho] = []
    total = 0.0
    for c in sorted(cands, key=lambda g: g.nota, reverse=True):
        if len(escolhidos) >= cfg.max_trechos:
            break
        dur = c.fim - c.inicio
        if total + dur > alvo * 1.35 and escolhidos:
            continue
        if any(c.inicio < e.fim + FOLGA_ENTRE and c.fim > e.inicio - FOLGA_ENTRE for e in escolhidos):
            continue
        escolhidos.append(c)
        total += dur
        if total >= alvo:
            break
    escolhidos.sort(key=lambda g: g.inicio)
    # folga para não comer o começo nem o fim da palavra
    out = []
    for g in escolhidos:
        a = max(0.0, g.inicio - PAD_ANTES)
        b = min(duracao, g.fim + PAD_DEPOIS)
        out.append(Gancho(round(a, 3), round(b, 3), g.texto, round(g.nota, 3)))
    return out


def escolher_bloco(pals_clip: list[dict], duracao: float, cfg: Abertura,
                   energia: Callable[[float, float], float] | None = None,
                   destaque: re.Pattern | None = None) -> list[Gancho]:
    """O melhor trecho corrido de BLOCO_MIN a `cfg.max_trecho` s, perto de `cfg.duracao`: frases seguidas, sem
    pausa longa no meio, que começa numa frase nova (não num "e", "mas", "porque") e termina com a frase fechada.
    A nota junta a média das frases, o pico (a frase mais forte puxa o bloco) e a energia do áudio."""
    frases = montar_frases(pals_clip, pausa_quebra=0.5, max_frase=BLOCO_MIN)
    if not frases:
        return []
    lim = duracao * cfg.inicio_minimo
    notas = [nota_fala(f.texto, f.n_palavras, max(0.1, f.fim - f.inicio), destaque) for f in frases]
    minimo = min(max(BLOCO_MIN, cfg.duracao * 0.6), cfg.max_trecho)
    melhor: Gancho | None = None
    for i, fi in enumerate(frases):
        if fi.inicio < lim:
            continue
        primeira = normalizar(fi.texto.split()[0]) if fi.texto.split() else ""
        soma, pico = 0.0, -9.0
        for j in range(i, len(frases)):
            fj = frases[j]
            if j > i and fj.inicio - frases[j - 1].fim > FOLGA_BLOCO:
                break
            dur = fj.fim - fi.inicio
            if dur > cfg.max_trecho:
                break
            soma += notas[j]
            pico = max(pico, notas[j])
            if dur < minimo:
                continue
            nota = soma / (j - i + 1) + 0.5 * pico
            nota -= 0.6 if primeira in CONECTIVOS_INICIO else 0.0
            nota += 0.3 if fj.pontuada or fj.pausa_depois >= 0.6 else -0.5  # termina com a ideia fechada
            nota -= 0.3 * abs(dur - cfg.duracao) / max(cfg.duracao, 1.0)
            if energia:
                nota += energia(fi.inicio, fj.fim)
            if melhor is None or nota > melhor.nota:
                texto = " ".join(f.texto for f in frases[i:j + 1])
                melhor = Gancho(fi.inicio, fj.fim, texto, nota)
    if melhor is None:
        return []
    a = max(0.0, melhor.inicio - PAD_ANTES)
    b = min(duracao, melhor.fim + PAD_DEPOIS)
    return [Gancho(round(a, 3), round(b, 3), melhor.texto, round(melhor.nota, 3))]


def manuais(cfg: Abertura, tl: Timeline) -> list[Gancho]:
    """Os trechos fixados no estilo (segundos do original), convertidos para o tempo do clip."""
    out = []
    for a, b in cfg.trechos:
        iv = tl.mapear_intervalo(float(a), float(b))
        if iv and iv[1] - iv[0] >= 0.3:
            out.append(Gancho(round(iv[0], 3), round(iv[1], 3), "", 0.0))
    return sorted(out, key=lambda g: g.inicio)


def vinheta_primeiro(ganchos: list[Gancho], vinheta_antes: bool) -> bool:
    """A vinheta abre o vídeo quando o canal pediu assim ou quando não há gancho para vir antes dela."""
    return vinheta_antes or not ganchos


def palavras_finais(pals_clip: list[dict], ganchos: list[Gancho], vinheta: float = 0.0,
                    vinheta_antes: bool = False) -> list[dict]:
    """As palavras no tempo do vídeo final (vinheta, ganchos e corte), para a legenda oculta .srt/.vtt.
    `vinheta` é a duração dela (0 = sem vinheta); a vinheta não tem fala do corte."""
    primeiro = vinheta_primeiro(ganchos, vinheta_antes)
    out, t0 = [], vinheta if primeiro else 0.0
    for g in ganchos:
        for w in pals_clip:
            if w["inicio"] >= g.inicio and w["fim"] <= g.fim:
                out.append({**w, "inicio": t0 + w["inicio"] - g.inicio, "fim": t0 + w["fim"] - g.inicio})
        t0 += g.fim - g.inicio
    if not primeiro:
        t0 += vinheta
    out += [{**w, "inicio": t0 + w["inicio"], "fim": t0 + w["fim"]} for w in pals_clip]
    return out


def montar(video: Path, saida: Path, ganchos: list[Gancho], cfg: Abertura, tem_audio: bool, fps: float,
           preview: bool = False, som: Path | None = None, volume_som: float = 0.5,
           progresso: Callable[[float, str], None] | None = None,
           cancelar: threading.Event | None = None, vinheta: Path | None = None,
           vinheta_antes: bool = False) -> float:
    """Escreve em `saida` os ganchos seguidos do clip inteiro e, se vier, a vinheta do canal (no começo ou entre
    os ganchos e o corte). Devolve quanto tempo vem antes do corte (ganchos + vinheta, em s)."""
    info = media.probe(video)
    w, h = info.largura, info.altura
    info_vin = media.probe(vinheta) if vinheta is not None else None
    entradas: list[str] = []
    partes: list[str] = []
    rot_v, rot_a = [], []
    cor = []
    if cfg.preto_e_branco:
        cor.append("hue=s=0")
    if abs(cfg.contraste - 1.0) > 1e-3:
        cor.append(f"eq=contrast={cfg.contraste:.2f}")
    filtro_cor = ("," + ",".join(cor)) if cor else ""
    aformat = "aformat=sample_rates=48000:channel_layouts=stereo"
    n_in = 0
    ordem: list[str] = []  # "g" gancho, "v" vinheta: o que vem antes do corte, na ordem

    def por_vinheta() -> None:
        nonlocal n_in
        assert vinheta is not None and info_vin is not None
        d = info_vin.duracao
        entradas.extend(["-i", str(vinheta)])
        k = n_in
        n_in += 1
        partes.append(f"[{k}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:"
                      f"color=black,setsar=1,fps={fps:g},setpts=PTS-STARTPTS,format=yuv420p[vin]")
        rot_v.append("[vin]")
        if tem_audio:
            if info_vin.tem_audio:
                partes.append(f"[{k}:a:0]asetpts=PTS-STARTPTS,{aformat},apad,atrim=0:{d:.3f}[vina]")
            else:  # vinheta muda: silêncio do tamanho dela, para o concat casar vídeo e áudio
                entradas.extend(["-f", "lavfi", "-t", f"{d:.3f}", "-i", "anullsrc=r=48000:cl=stereo"])
                partes.append(f"[{n_in}:a]{aformat}[vina]")
                n_in += 1
            rot_a.append("[vina]")
        ordem.append("v")

    abertura = 0.0
    if vinheta is not None and vinheta_primeiro(ganchos, vinheta_antes):
        por_vinheta()
    for g in ganchos:
        d = g.fim - g.inicio
        k = n_in
        entradas += ["-ss", f"{g.inicio:.3f}", "-t", f"{d:.3f}", "-i", str(video)]
        n_in += 1
        partes.append(f"[{k}:v:0]fps={fps:g},setpts=PTS-STARTPTS{filtro_cor},setsar=1,format=yuv420p[g{k}]")
        rot_v.append(f"[g{k}]")
        if tem_audio:
            fora = max(0.0, d - 0.06)
            partes.append(f"[{k}:a:0]asetpts=PTS-STARTPTS,{aformat},"
                          f"afade=t=in:d=0.03,afade=t=out:st={fora:.3f}:d=0.06[ga{k}]")
            rot_a.append(f"[ga{k}]")
        abertura += d
        ordem.append("g")
    fim_ganchos = abertura + (info_vin.duracao if info_vin is not None and ordem and ordem[0] == "v" else 0.0)
    if vinheta is not None and not vinheta_primeiro(ganchos, vinheta_antes):
        por_vinheta()
    if info_vin is not None:
        abertura += info_vin.duracao
    n = len(rot_v)
    k_corpo = n_in
    entradas += ["-i", str(video)]
    n_in += 1
    # o clarão branco só quando o corte vem logo depois de um gancho (a vinheta tem as transições dela)
    flash = (f",fade=t=in:st=0:d={cfg.duracao_flash:.2f}:color=white"
             if cfg.transicao == "flash" and ordem and ordem[-1] == "g" else "")
    partes.append(f"[{k_corpo}:v:0]fps={fps:g},setpts=PTS-STARTPTS{flash},setsar=1,format=yuv420p[corpo]")
    rot_v.append("[corpo]")
    if tem_audio:
        partes.append(f"[{k_corpo}:a:0]asetpts=PTS-STARTPTS,{aformat}[corpoa]")
        rot_a.append("[corpoa]")
        pares = "".join(v + a for v, a in zip(rot_v, rot_a))
        partes.append(f"{pares}concat=n={n + 1}:v=1:a=1[vout][acat]")
        if som is not None and ganchos:
            entradas += ["-i", str(som)]
            ms = max(0, int(round((fim_ganchos - 0.15) * 1000)))  # o efeito começa um pouco antes da virada
            partes.append(f"[{n_in}:a]{aformat},adelay={ms}:all=1,"
                          f"volume={volume_som:.3f}[sfx]")
            partes.append("[acat][sfx]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.944[aout]")
        else:
            partes.append("[acat]anull[aout]")
    else:
        partes.append(f"{''.join(rot_v)}concat=n={n + 1}:v=1:a=0[vout]")
    total = abertura + info.duracao
    args = entradas + ["-filter_complex", ";".join(partes), "-map", "[vout]"]
    if tem_audio:
        args += ["-map", "[aout]", "-c:a", "aac", "-b:a", "96k" if preview else "192k", "-ar", "48000"]
    args += media.video_encode_args("preview" if preview else "final")
    args += ["-t", f"{total:.3f}", str(saida)]
    media.run_ffmpeg(args, duracao=total, progresso=progresso, cancelar=cancelar,
                     descricao="montando a abertura" + (" com a vinheta" if vinheta is not None else ""))
    return abertura
