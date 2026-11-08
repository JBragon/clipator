"""Gerador de thumbnail no formato do clip (1280x720 no 16:9, 1080x1920 no Shorts).

Por código, sem IA: escolhe os quadros do clip com rosto grande, nítido e num
momento de voz alta; monta a frase-gancho (da IA, se houver, ou das palavras do
título) e desenha 4 layouts com a identidade do thumb.md do canal.

Com o Codex conectado, também gera variações por imagem ($imagegen) a partir dos
modelos em thumbs/modelos/ e do quadro real. Regra de ouro (skill
briefing-thumbnail): o rosto nunca é redesenhado; a montagem é sobre o quadro real.

Saída em clips/<id>/thumbs/ (variações e quadros) e clips/<id>/thumb.png (a escolhida).
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import media
from .models import Clip, Thumb
from .textutil import STOPWORDS, normalizar, tokens
from .workspace import ProjetoWS, fontes_dir

TAMANHOS = {"16:9": (1280, 720), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
W, H = TAMANHOS["16:9"]
SEGURO_TOPO, SEGURO_BASE = 0.10, 0.18  # faixas que a interface do Shorts cobre (fração da altura)
Progress = Callable[[float, str], None]


def _nada(*_a, **_k) -> None:
    return None


# ---- quadros ----------------------------------------------------------------
@dataclass
class Quadro:
    tempo: float  # segundos do vídeo original
    nota: float
    rosto: tuple[float, float, float] | None  # cx, cy, área (frações)


def _nitidez(cinza: np.ndarray) -> float:
    g = cinza.astype(np.float32)
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def _energia_em(sinais: dict | None, t: float) -> float:
    if not sinais or not sinais.get("energia_db"):
        return 0.0
    passo = float(sinais.get("passo") or 0.25)
    db = sinais["energia_db"]
    i = int(t / passo)
    janela = db[max(0, i - 2): i + 3] or [sinais.get("media_db", -30)]
    mu, sd = float(sinais.get("media_db") or -30), float(sinais.get("desvio_db") or 6) or 6
    return max(0.0, min(1.0, (max(janela) - mu) / (2 * sd) + 0.5))


def _rosto_principal(rgb: np.ndarray) -> tuple[float, float, float] | None:
    from .reframe import detector

    det = detector()
    if not det.disponivel:
        return None
    rostos = det.detectar(np.ascontiguousarray(rgb[:, :, ::-1]))
    if not rostos:
        return None
    r = max(rostos, key=lambda x: x.area)
    return (r.cx, r.cy, r.area)


def escolher_quadros(projeto: ProjetoWS, clip: Clip, n: int = 3, por_segundo: float = 2.0,
                     cancelar: threading.Event | None = None) -> list[Quadro]:
    """Os n melhores quadros do clip, com pelo menos 1,5 s entre eles."""
    from PIL import Image

    video = projeto.video_path()
    if video is None:
        raise FileNotFoundError("O projeto ainda não tem vídeo")
    sinais = projeto.sinais()
    cortes = sorted(clip.cortes_internos)
    dur = clip.fim - clip.inicio
    with tempfile.TemporaryDirectory(prefix="clipator-quadros-") as tmp:
        media.run_ffmpeg(["-ss", f"{clip.inicio:.3f}", "-t", f"{dur:.3f}", "-i", str(video), "-an",
                          "-vf", f"fps={por_segundo},scale=640:-2", "-q:v", "4", str(Path(tmp) / "q_%05d.jpg")],
                         duracao=dur, cancelar=cancelar, descricao="lendo quadros")
        brutos = []
        for k, p in enumerate(sorted(Path(tmp).glob("q_*.jpg"))):
            t = clip.inicio + (k + 0.5) / por_segundo
            if any(a <= t < b for a, b in cortes):
                continue
            with Image.open(p) as im:
                rgb = np.asarray(im.convert("RGB"))
            cinza = rgb.mean(axis=2)
            brilho = float(cinza.mean())
            if brilho < 18 or brilho > 245:  # quadro preto ou estourado
                continue
            brutos.append((t, _nitidez(cinza), _rosto_principal(rgb), _energia_em(sinais, t)))
    if not brutos:
        return [Quadro(clip.inicio + min(dur / 2, 3.0), 0.0, None)]
    nit_max = max(b[1] for b in brutos) or 1.0
    quadros = []
    for t, nit, rosto, en in brutos:
        nota = (nit / nit_max) + en
        if rosto:
            nota += 1.5 + min(1.0, rosto[2] * 8)
        quadros.append(Quadro(round(t, 2), round(nota, 3), rosto))
    quadros.sort(key=lambda q: -q.nota)
    escolhidos: list[Quadro] = []
    for q in quadros:
        if all(abs(q.tempo - e.tempo) >= 1.5 for e in escolhidos):
            escolhidos.append(q)
        if len(escolhidos) == n:
            break
    return escolhidos


def extrair_quadro(video: Path, t: float, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    media.run_ffmpeg(["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-an", str(destino)], descricao="quadro")
    return destino


# ---- frase-gancho ------------------------------------------------------------
def reequilibrar(palavras: list[str], n: int) -> list[str]:
    """Divide as palavras em até n linhas com a linha mais longa a menor possível."""
    n = max(1, min(n, len(palavras)))
    tam = [len(p) for p in palavras]

    def custo(i: int, j: int) -> int:
        return sum(tam[i:j]) + (j - i - 1)

    # programação dinâmica: melhor[k][j] = menor máximo usando k linhas para as j primeiras palavras
    inf = 10**9
    melhor = [[inf] * (len(palavras) + 1) for _ in range(n + 1)]
    corte = [[0] * (len(palavras) + 1) for _ in range(n + 1)]
    melhor[0][0] = 0
    for k in range(1, n + 1):
        for j in range(1, len(palavras) + 1):
            for i in range(k - 1, j):
                v = max(melhor[k - 1][i], custo(i, j))
                if v < melhor[k][j]:
                    melhor[k][j], corte[k][j] = v, i
    linhas, j = [], len(palavras)
    for k in range(n, 0, -1):
        i = corte[k][j]
        linhas.append(" ".join(palavras[i:j]))
        j = i
    return [ln for ln in reversed(linhas) if ln]


def frase_local(titulo: str, texto: str = "", linhas_max: int = 4) -> tuple[list[str], list[str]]:
    """Quebra o título em 2 a 4 linhas curtas e destaca as palavras mais fortes."""
    base = re.sub(r"\s+", " ", titulo or "").strip() or " ".join(texto.split()[:8])
    palavras = [p for p in base.split(" ") if p]
    if not palavras:
        return [], []
    alvo = max(2, min(linhas_max, (len(palavras) + 2) // 3))
    linhas = reequilibrar(palavras, alvo)
    # destaque: palavras já em caixa alta no título, números e o termo mais repetido no trecho
    destaques = [p for p in palavras if (p.isupper() and len(p) > 2) or any(c.isdigit() for c in p)]
    if texto:
        freq: dict[str, int] = {}
        for t in tokens(texto):
            if t not in STOPWORDS and len(t) > 3:
                freq[t] = freq.get(t, 0) + 1
        for p in palavras:
            if normalizar(p.strip(".,!?:;\"'")) in freq and freq[normalizar(p.strip(".,!?:;\"'"))] >= 2:
                destaques.append(p)
    if not destaques:
        destaques = [max(palavras, key=len)]
    vistos: list[str] = []
    for d in destaques:
        if d not in vistos:
            vistos.append(d)
    return linhas, vistos[:3]


# ---- frases das variações ------------------------------------------------------
# Toda frase sai do que é dito no trecho do clip: os "insights" repetem o que foi falado e os
# "sensacionalistas" só mudam o tom (caixa alta, pergunta, chamada), nunca o fato.
SUPERLATIVOS = {
    "nunca", "sempre", "ninguem", "todo", "todos", "tudo", "maior", "menor", "pior", "melhor", "absurdo",
    "absurda", "verdade", "mentira", "segredo", "erro", "grave", "crime", "escandalo", "inacreditavel", "chocante",
    "jamais", "impossivel", "historico", "historica", "primeira", "primeiro", "ultimo", "ultima", "milhao", "milhoes",
    "bilhao", "bilhoes", "perdeu", "ganhou", "preso", "presa", "morte", "morreu", "proibido", "revelou", "confessou",
}
_FRASE_RE = re.compile(r"(?<=[.!?…])\s+")
_NUM_RE = re.compile(r"\d[\d.,]*")
_PONTUACAO = ".,!?:;\"'()…"


@dataclass
class FraseThumb:
    tipo: str  # "insight", "sensacionalista" ou "sua" (a frase que o usuário escreveu)
    linhas: list[str]
    destaques: list[str]
    prova: str = ""  # trecho da transcrição do clip que sustenta a frase


def como_citacao(linhas: list[str]) -> list[str]:
    """A fala vira citação: aspas em volta e reticências quando a frase não terminou ("ELE DISSE QUE...")."""
    if not linhas or linhas[0].startswith('"'):
        return linhas
    out = list(linhas)
    ultima = out[-1].rstrip()
    if not ultima.endswith((".", "!", "?", "…")):
        ultima = ultima.rstrip(",;:") + "..."
    out[0] = '"' + out[0]
    out[-1] = (ultima if len(out) > 1 else '"' + ultima.lstrip('"')) + '"'
    if len(out) == 1:
        out[0] = out[-1]
    return out


def _norm_texto(texto: str) -> str:
    return " ".join(n for n in (normalizar(t) for t in re.split(r"\s+", texto or "")) if n)


def _numeros(texto: str) -> set[str]:
    return {re.sub(r"\D", "", m) for m in _NUM_RE.findall(texto or "") if re.sub(r"\D", "", m)}


def apoiada(frase: FraseThumb, texto_clip: str) -> bool:
    """A frase se sustenta no clip: a prova é um trecho literal da fala, os números dela foram ditos
    e pelo menos uma palavra de conteúdo dela aparece no trecho."""
    clip_n = _norm_texto(texto_clip)
    prova_n = _norm_texto(frase.prova)
    if not prova_n or prova_n not in clip_n:
        return False
    tudo = " ".join(frase.linhas)
    if not _numeros(tudo) <= _numeros(texto_clip):
        return False
    # pela raiz (4 letras), para "perdeu" casar com "perdi" e "corretoras" com "corretora"
    conteudo = {normalizar(t)[:4] for t in tokens(tudo) if t not in STOPWORDS and len(t) > 3}
    raizes_clip = {p[:4] for p in clip_n.split()}
    return not conteudo or bool(conteudo & raizes_clip)


def _frases_do_trecho(texto: str) -> list[str]:
    return [f.strip() for f in _FRASE_RE.split(texto or "") if len(f.split()) >= 4]


_UNIDADES = {"mil", "milhao", "milhoes", "bilhao", "bilhoes", "reais", "dolares", "anos", "dias", "vezes", "%"}


def _pontos(frase: str, tema: str, freq: dict[str, int] | None = None) -> tuple[float, str]:
    """Nota da frase como gancho e a palavra que a puxa, nesta ordem de força:
    número (com a unidade dita depois, "500 mil"), superlativo, nome próprio e o tema do trecho.
    Entre dois nomes, vale o mais citado no corte (`freq`)."""
    palavras = frase.split()
    freq = freq or {}
    nota = 0.0
    chaves: dict[int, list[str]] = {}
    for i, p in enumerate(palavras):
        limpa = p.strip(_PONTUACAO)
        n = normalizar(limpa)
        if _NUM_RE.fullmatch(limpa):
            nota += 3
            seguinte = palavras[i + 1].strip(_PONTUACAO) if i + 1 < len(palavras) else ""
            chaves.setdefault(0, []).append(f"{limpa} {seguinte}" if normalizar(seguinte) in _UNIDADES else limpa)
        elif n in SUPERLATIVOS:
            nota += 2
            chaves.setdefault(1, []).append(limpa)
        elif i > 0 and limpa[:1].isupper() and n not in STOPWORDS and len(n) > 2:
            nota += 1.5
            chaves.setdefault(2, []).append(limpa)
        if tema and n == normalizar(tema):
            nota += 1
            chaves.setdefault(3, []).append(limpa)
    if chaves:
        grupo = chaves[min(chaves)]
        return nota, max(grupo, key=lambda c: freq.get(normalizar(c.split()[0]), 0))
    return nota, max(palavras, key=len).strip(_PONTUACAO)


def _janela(frase: str, chave: str, n: int = 8) -> list[str]:
    """Até n palavras em volta da palavra-chave, começando na oração dela (depois da vírgula anterior)."""
    palavras = [p.strip("\"'()") for p in frase.split()]
    alvo = normalizar(chave.split()[0]) if chave else ""
    i = next((k for k, p in enumerate(palavras) if normalizar(p.strip(_PONTUACAO)) == alvo), 0)
    ini = i
    while ini > 0 and i - ini < 4 and not palavras[ini - 1].endswith((",", ";", ":")):
        ini -= 1
    ini = max(0, min(ini, len(palavras) - 4))
    trecho = palavras[ini: ini + n]
    while len(trecho) > 3 and normalizar(trecho[-1].strip(_PONTUACAO)) in STOPWORDS:
        trecho.pop()
    while len(trecho) > 3 and normalizar(trecho[0].strip(_PONTUACAO)) in STOPWORDS:
        trecho.pop(0)
    return [p.strip(",;:") for p in trecho] or palavras[:n]


def frases_locais(texto: str, titulo: str = "", linhas_max: int = 4, quantidade: int = 3) -> list[FraseThumb]:
    """Sem IA: os melhores ganchos ditos no trecho (insights) e versões sensacionalistas deles."""
    from .titles import tema_do_trecho

    candidatas = _frases_do_trecho(texto)
    if not candidatas:
        linhas, dest = frase_local(titulo, texto, linhas_max)
        return [FraseThumb("insight", linhas, dest, "")] if linhas else []
    tema = tema_do_trecho(texto)
    freq: dict[str, int] = {}
    for t in tokens(texto):
        freq[normalizar(t)] = freq.get(normalizar(t), 0) + 1
    pontuadas = sorted(((*_pontos(f, tema, freq), f) for f in candidatas), key=lambda x: -x[0])
    insights: list[FraseThumb] = []
    sensac: list[FraseThumb] = []
    vistas: set[str] = set()
    for _nota, chave, frase in pontuadas:
        trecho = _janela(frase, chave)
        assinatura = " ".join(trecho).lower()
        if len(trecho) < 4 or assinatura in vistas:
            continue
        vistas.add(assinatura)
        alvo = max(2, min(linhas_max, (len(trecho) + 2) // 3))
        destaque = list(dict.fromkeys(chave.split()[:1] + [p for p in trecho if _NUM_RE.fullmatch(p.strip(_PONTUACAO))]))
        insights.append(FraseThumb("insight", reequilibrar(trecho, alvo), destaque[:3], frase))
        curto = trecho[:5]
        if _NUM_RE.fullmatch(chave.split()[0]):
            # o número fica na frase dita; o tom muda (caixa alta e espanto), o fato não
            fala = " ".join(trecho[:7]).rstrip(".,!?;:…") + "?!"
            linhas = reequilibrar(fala.upper().split(), 2)
        elif normalizar(chave) in SUPERLATIVOS:
            linhas = ["OLHA O QUE", "FOI DITO:"] + reequilibrar(curto, 2)
        else:
            linhas = ["NINGUÉM TE CONTA", f"ISSO SOBRE {chave.upper()}"]
        if all(f.linhas != linhas[:linhas_max] for f in sensac):
            sensac.append(FraseThumb("sensacionalista", linhas[:linhas_max], chave.split()[:1], frase))
        if len(insights) >= quantidade:
            break
    return insights + sensac[:quantidade]


SCHEMA_FRASES = {
    "type": "object",
    "properties": {
        "frases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": ["insight", "sensacionalista"]},
                    "linhas": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 4},
                    "destaques": {"type": "array", "items": {"type": "string"}},
                    "prova": {"type": "string"},
                },
                "required": ["tipo", "linhas", "destaques", "prova"],
            },
        },
        "prompt_imagem": {"type": "string"},
    },
    "required": ["frases", "prompt_imagem"],
}


def prompt_frases(titulo: str, texto: str, cfg: Thumb, thumb_md: str, extras: str, tamanho: tuple[int, int]) -> str:
    return "\n".join([
        "Você faz thumbnails para um canal de cortes do YouTube. Responda só com o JSON do schema.",
        "",
        f"- frases: 6 frases para a thumbnail, cada uma em 1 a {cfg.linhas_max} linhas de no máximo 4 palavras:",
        "  - 3 com tipo \"insight\": o que de mais forte é dito no clip (um número, uma afirmação, uma citação).",
        *(["    O canal usa citação: escreva o insight na primeira pessoa de quem fala, como foi dito, e corte",
           "    antes do desfecho para criar curiosidade (o Clipator põe as aspas e as reticências)."]
          if cfg.citacao else []),
        "  - 3 com tipo \"sensacionalista\": tom de chamada, caixa alta, palavras fortes, até exagerado.",
        "    Pode exagerar a emoção, nunca o fato: nada de números, nomes ou acontecimentos que não estejam no clip.",
        "  - destaques: 1 a 3 palavras das linhas que levam a cor de destaque.",
        "  - prova: copie, sem mudar nenhuma palavra, o trecho da transcrição abaixo que sustenta a frase.",
        "    Frases sem prova literal são descartadas.",
        f"- prompt_imagem: prompt em português para um gerador de imagem montar a thumbnail {tamanho[0]}x{tamanho[1]}",
        "  sobre o quadro real do vídeo (anexado). Nunca redesenhe o rosto; só componha texto, fundo e moldura.",
        "",
        f"Título escolhido: {titulo}",
        "",
        "## Regras do canal para thumbnail",
        thumb_md.strip() or "(nenhuma)",
        extras.strip(),
        "",
        "## Transcrição do clip (só o trecho do corte)",
        texto[:3000],
    ])


def frases_da_ia(resposta: dict, texto: str, linhas_max: int) -> list[FraseThumb]:
    """As frases da IA que se sustentam no clip; as outras são descartadas."""
    out = []
    for f in resposta.get("frases") or []:
        if not isinstance(f, dict):
            continue
        frase = FraseThumb(
            "sensacionalista" if f.get("tipo") == "sensacionalista" else "insight",
            [str(x) for x in (f.get("linhas") or []) if str(x).strip()][:linhas_max],
            [str(x) for x in (f.get("destaques") or [])],
            str(f.get("prova") or ""),
        )
        if frase.linhas and apoiada(frase, texto):
            out.append(frase)
    return out


def completar(frases: list[FraseThumb], locais: list[FraseThumb], por_grupo: int = 3) -> list[FraseThumb]:
    """Até `por_grupo` frases de cada tipo, completando com as locais quando a IA trouxe menos."""
    out = []
    for tipo in ("insight", "sensacionalista"):
        grupo = [f for f in frases if f.tipo == tipo][:por_grupo]
        textos = {" ".join(f.linhas).lower() for f in grupo}
        for f in locais:
            if len(grupo) >= por_grupo:
                break
            if f.tipo == tipo and " ".join(f.linhas).lower() not in textos:
                grupo.append(f)
        out += grupo
    return out


def _hex(c: str, padrao: str = "#FFFFFF") -> tuple[int, int, int]:
    c = (c or padrao).lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return _hex(padrao)


def caminho_fonte(nome: str, extras: list[Path] | None = None) -> Path | None:
    alvo = re.sub(r"[^a-z0-9]", "", nome.lower())
    for pasta in [*(extras or []), fontes_dir()]:
        if not pasta.is_dir():
            continue
        arquivos = sorted(p for p in pasta.iterdir() if p.suffix.lower() in (".ttf", ".otf"))
        for p in arquivos:
            if re.sub(r"[^a-z0-9]", "", p.stem.lower()) in (alvo, alvo + "regular"):
                return p
        for p in arquivos:
            if re.sub(r"[^a-z0-9]", "", p.stem.lower()).startswith(alvo):
                return p
    return None


def _fonte(caminho: Path | None, tamanho: int):
    from PIL import ImageFont

    if caminho:
        return ImageFont.truetype(str(caminho), tamanho)
    return ImageFont.load_default(tamanho)


def _cobrir(img, w: int, h: int, cx: float = 0.5, cy: float = 0.5, zoom: float = 1.0):
    """Recorta e escala para w x h, centrado em (cx, cy) do original."""
    from PIL import Image

    iw, ih = img.size
    escala = max(w / iw, h / ih) * zoom
    cw, ch = w / escala, h / escala
    x0 = min(max(cx * iw - cw / 2, 0), iw - cw)
    y0 = min(max(cy * ih - ch / 2, 0), ih - ch)
    return img.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((w, h), Image.LANCZOS)


def _texto(draw, caixa: tuple[int, int, int, int], linhas: list[str], destaques: list[str], cfg: Thumb,
           fonte: Path | None, alinhamento: str = "esquerda") -> None:
    """Desenha as linhas no maior tamanho que cabe na caixa, com contorno e palavras destacadas."""
    x, y, w, h = caixa
    if cfg.maiusculas:
        linhas = [ln.upper() for ln in linhas]
    if not linhas:
        return
    dest = {normalizar(d.strip(".,!?:;\"'")) for d in destaques}
    tamanho = 160
    while tamanho > 24:
        f = _fonte(fonte, tamanho)
        alturas = [draw.textbbox((0, 0), ln, font=f)[3] - draw.textbbox((0, 0), ln, font=f)[1] for ln in linhas]
        largura = max(draw.textlength(ln, font=f) for ln in linhas)
        total = sum(alturas) + int(tamanho * 0.18) * (len(linhas) - 1)
        if largura <= w and total <= h:
            break
        tamanho -= 4
    f = _fonte(fonte, tamanho)
    espaco = draw.textlength(" ", font=f)
    contorno = max(2, tamanho // 14)
    alturas = [draw.textbbox((0, 0), ln, font=f)[3] - draw.textbbox((0, 0), ln, font=f)[1] for ln in linhas]
    total = sum(alturas) + int(tamanho * 0.18) * (len(linhas) - 1)
    cy = y + (h - total) // 2
    cor, cor_d = _hex(cfg.cor_texto), _hex(cfg.cor_destaque)
    for ln, alt in zip(linhas, alturas):
        largura = draw.textlength(ln, font=f)
        cx = x + (w - largura) / 2 if alinhamento == "centro" else x
        topo = cy - draw.textbbox((0, 0), ln, font=f)[1]
        for palavra in ln.split(" "):
            c = cor_d if normalizar(palavra.strip(".,!?:;\"'")) in dest else cor
            draw.text((cx, topo), palavra, font=f, fill=c, stroke_width=contorno, stroke_fill=(0, 0, 0))
            cx += draw.textlength(palavra, font=f) + espaco
        cy += alt + int(tamanho * 0.18)


def tamanho_thumb(formato: str | None) -> tuple[int, int]:
    """A thumbnail segue o formato do vídeo: 9:16 vertical, 16:9 no padrão do YouTube."""
    return TAMANHOS.get(formato or "16:9", TAMANHOS["16:9"])


def _borda(img, cfg: Thumb) -> None:
    from PIL import ImageDraw

    w, h = img.size
    if cfg.espessura_borda > 0:
        ImageDraw.Draw(img).rectangle((0, 0, w - 1, h - 1), outline=_hex(cfg.cor_borda), width=cfg.espessura_borda)


def _vertical(tamanho: tuple[int, int]) -> bool:
    return tamanho[1] > tamanho[0] * 1.1


def desenhar(layout: str, quadro, rosto: tuple[float, float, float] | None, linhas: list[str],
             destaques: list[str], cfg: Thumb, fonte: Path | None = None, tamanho: tuple[int, int] = (W, H),
             zona: tuple[float, float] | None = None):
    """Uma thumbnail (PIL.Image) no layout e no tamanho pedidos (o tamanho segue o formato do clip).

    Na vertical (Shorts), o texto fica entre as faixas que a interface do app cobre: o topo
    e, principalmente, a parte de baixo, onde ficam título, botões e legenda.
    """
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    w, h = tamanho
    cx, cy = (rosto[0], rosto[1]) if rosto else (0.5, 0.4)
    fundo = _hex(cfg.cor_fundo, "#111111")
    palavras = " ".join(linhas).split()
    estreitas = reequilibrar(palavras, cfg.linhas_max) if palavras else []  # para caixas de texto estreitas
    direita = cfg.lado_rosto == "direita"
    vertical = _vertical(tamanho)
    seguro_topo, seguro_base = zona if zona is not None else (SEGURO_TOPO, SEGURO_BASE)
    topo, base = (int(h * seguro_topo), int(h * (1 - seguro_base))) if vertical else (0, h)
    if layout == "rosto-frase":
        img = Image.new("RGB", (w, h), fundo)
        if vertical:
            fh = int(h * 0.52)
            img.paste(_cobrir(quadro, w, fh, cx, cy), (0, 0))
            grad = Image.linear_gradient("L").resize((w, 200))  # funde a foto na cor de fundo
            img.paste(Image.new("RGB", (w, 200), fundo), (0, fh - 200), grad)
            draw = ImageDraw.Draw(img)
            _texto(draw, (60, fh + 10, w - 120, base - fh - 10), estreitas, destaques, cfg, fonte, "centro")
        else:
            lw = int(w * 0.6)
            foto = _cobrir(quadro, lw, h, cx, cy)
            px = w - lw if direita else 0
            img.paste(foto, (px, 0))
            # degradê da cor de fundo sobre a borda interna da foto
            grad = Image.new("L", (lw, 1))
            for i in range(lw):
                d = i if direita else lw - 1 - i
                grad.putpixel((i, 0), max(0, 255 - int(255 * d / 220)) if d < 220 else 0)
            img.paste(Image.new("RGB", (lw, h), fundo), (px, 0), grad.resize((lw, h)))
            draw = ImageDraw.Draw(img)
            tx = 48 if direita else w - int(w * 0.46) - 48 + 40
            _texto(draw, (tx, 60, int(w * 0.46), h - 120), estreitas, destaques, cfg, fonte)
    elif layout == "frase-gancho":
        img = ImageEnhance.Brightness(_cobrir(quadro, w, h, cx, cy)).enhance(0.55)
        sombra = Image.linear_gradient("L").resize((w, h))  # escurece mais embaixo
        img = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), img, sombra.point(lambda v: int(v * 0.6)))
        draw = ImageDraw.Draw(img)
        caixa = (60, int(h * 0.36), w - 120, int(h * 0.32)) if vertical else (60, int(h * 0.38), w - 120, int(h * 0.56))
        _texto(draw, caixa, estreitas if vertical else linhas, destaques, cfg, fonte, "centro")
    elif layout == "moldura":
        img = _cobrir(quadro, w, h, cx, cy).filter(ImageFilter.GaussianBlur(18))
        img = ImageEnhance.Brightness(img).enhance(0.45)
        if vertical:
            fw = int(w * 0.8)
            fh = fw  # foto quadrada, recortada no rosto
        else:
            fw, fh = int(w * 0.5), int(w * 0.5 * 9 / 16)
        foto = _cobrir(quadro, fw, fh, cx, cy)
        moldura = Image.new("RGB", (fw + 24, fh + 24), (255, 255, 255))
        moldura.paste(foto, (12, 12))
        moldura = moldura.convert("RGBA").rotate(-4 if direita else 4, expand=True, resample=Image.BICUBIC)
        draw = None
        if vertical:
            img.paste(moldura, ((w - moldura.width) // 2, topo), moldura)
            draw = ImageDraw.Draw(img)
            ty = topo + moldura.height + 30
            _texto(draw, (60, ty, w - 120, base - ty), estreitas, destaques, cfg, fonte, "centro")
        else:
            mx = w - moldura.width - 40 if direita else 40
            img.paste(moldura, (mx, (h - moldura.height) // 2), moldura)
            draw = ImageDraw.Draw(img)
            tx = 44 if direita else w - int(w * 0.4) - 36
            _texto(draw, (tx, 70, int(w * 0.4), h - 140), estreitas, destaques, cfg, fonte)
    elif layout == "rosto-grande":
        img = _cobrir(quadro, w, h, cx, cy, zoom=1.6 if rosto and rosto[2] < 0.08 else 1.15)
        duas = reequilibrar(palavras, 2) if len(linhas) > 2 else linhas  # a barra cabe 2 linhas
        if vertical:
            bh = int(h * 0.2)
            by = base - bh  # a barra fica acima da faixa que a interface do Shorts cobre
        else:
            bh = int(h * 0.36)
            by = h - bh
        img.paste(Image.new("RGB", (w, bh), fundo), (0, by))
        draw = ImageDraw.Draw(img)
        _texto(draw, (50, by + 20, w - 100, bh - 40), duas, destaques, cfg, fonte, "centro")
    else:
        raise ValueError(f"Layout de thumbnail desconhecido: {layout}")
    _borda(img, cfg)
    return img


# ---- orquestração ------------------------------------------------------------
def pasta_thumbs(pasta_clip: Path) -> Path:
    return pasta_clip / "thumbs"


def gerar(projeto: ProjetoWS, clip_id: str, usar_ia: bool = True, progresso: Progress = _nada,
          cancelar: threading.Event | None = None, esperar_login: Callable[[str], bool] | None = None) -> dict:
    """Gera as variações por código, no formato do clip (9:16 dá thumb vertical).

    As frases vêm só do trecho do clip: insights e sensacionalistas (pela IA, filtradas pela prova
    na transcrição, ou locais). Devolve {variacoes, detalhes, frases, quadros, linhas, destaques,
    fonte_frase, prompt_imagem, tamanho}.
    """
    from PIL import Image

    from . import skills
    from .ai.adapter import CacheIA, ErroIA, adaptador_com_reserva, chamar
    from .candidates import texto_do_trecho

    clip, pasta = projeto.clip(clip_id)
    cfg, thumb_md = projeto.canal.thumb()
    video = projeto.video_path()
    if video is None:
        raise FileNotFoundError("O projeto ainda não tem vídeo")
    tamanho = tamanho_thumb(clip.formato)
    from .plataformas import info as info_plataforma

    z = info_plataforma(clip.plataforma, clip.formato).zona
    zona = (max(SEGURO_TOPO, z.topo), max(SEGURO_BASE, z.base))  # o texto da thumb fica fora do que o app cobre
    saida = pasta_thumbs(pasta)
    saida.mkdir(parents=True, exist_ok=True)
    for velha in saida.glob("*.png"):  # variações de uma geração anterior (outro formato ou outras frases)
        if not velha.name.startswith("ia-"):
            velha.unlink()
    progresso(0.05, "escolhendo quadros")
    quadros = escolher_quadros(projeto, clip, 3, cancelar=cancelar)
    texto = texto_do_trecho(projeto.transcricao() or {}, clip.inicio, clip.fim)

    prompt_img, fonte_frase = "", "local"
    if clip.thumb_frase:
        frases = [FraseThumb("sua", list(clip.thumb_frase), frase_local(" ".join(clip.thumb_frase), texto, cfg.linhas_max)[1])]
        fonte_frase = "clip"
    else:
        locais = frases_locais(texto, clip.titulo or clip.gancho, cfg.linhas_max)
        da_ia: list[FraseThumb] = []
        if usar_ia:
            conf = projeto.ws.config()
            ad = adaptador_com_reserva(conf.ia.ranking, conf.ia.timeout_s, esperar_login=esperar_login)
            if ad.disponivel():
                progresso(0.2, f"frases da thumbnail com o {ad.nome}")
                extras = "\n\n".join(x for x in (
                    projeto.base_para_ia(("thumbs", "referencias"), 5000),
                    skills.texto_para_ia(projeto.ws, "thumbnail", projeto.canal.slug, projeto.id)) if x)
                try:
                    r = chamar(ad, prompt_frases(clip.titulo, texto, cfg, thumb_md, extras, tamanho), SCHEMA_FRASES,
                               CacheIA(projeto.analise_dir / "cache_ia"), cancelar)
                    da_ia = frases_da_ia(r, texto, cfg.linhas_max)
                    prompt_img = str(r.get("prompt_imagem") or "")
                    if da_ia:
                        fonte_frase = ad.nome
                except ErroIA:
                    da_ia = []
        frases = completar(da_ia, locais) or locais
    if not frases:
        linhas, dest = frase_local(clip.titulo or clip.gancho, texto, cfg.linhas_max)
        frases = [FraseThumb("insight", linhas, dest, "")]
    for f in frases:
        if not f.destaques:
            f.destaques = frase_local(" ".join(f.linhas), texto, cfg.linhas_max)[1]
        if cfg.citacao and f.tipo == "insight":
            f.linhas = como_citacao(f.linhas)

    fonte = caminho_fonte(cfg.fonte, [projeto.canal.path / "assets" / "fontes"])
    arquivos_quadros, bases = [], []
    for k, q in enumerate(quadros, 1):
        qpath = extrair_quadro(video, q.tempo, saida / f"quadro-{k}.png")
        arquivos_quadros.append({"arquivo": qpath.name, "tempo": q.tempo, "rosto": q.rosto is not None})
        with Image.open(qpath) as im:
            base = im.convert("RGB")
        rosto = _rosto_principal(np.asarray(base.resize((640, max(2, int(640 * base.height / base.width)))))) or q.rosto
        bases.append((k, base, rosto))
    variacoes, detalhes = [], {}
    total = len(frases) * len(cfg.layouts) or 1
    feito = 0
    contagem: dict[str, int] = {}
    for i, f in enumerate(frases):
        contagem[f.tipo] = contagem.get(f.tipo, 0) + 1
        k, base, rosto = bases[i % len(bases)] if bases else (0, None, None)
        if base is None:
            break
        for layout in cfg.layouts:
            if cancelar is not None and cancelar.is_set():
                raise media.Cancelado()
            nome = f"{f.tipo}-{contagem[f.tipo]}-{layout}.png"
            desenhar(layout, base, rosto, f.linhas, f.destaques, cfg, fonte, tamanho, zona).save(saida / nome, optimize=True)
            variacoes.append(nome)
            detalhes[nome] = {"tipo": f.tipo, "linhas": f.linhas, "prova": f.prova, "layout": layout, "quadro": k}
            feito += 1
            progresso(0.3 + 0.7 * feito / total, f"thumbnail {feito}/{total}")
    info = {"variacoes": variacoes, "detalhes": detalhes, "frases": [asdict(f) for f in frases],
            "quadros": arquivos_quadros, "linhas": frases[0].linhas, "destaques": frases[0].destaques,
            "fonte_frase": fonte_frase, "prompt_imagem": prompt_img, "tamanho": list(tamanho)}
    (saida / "thumbs.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    escolhida = pasta / "thumb.png"
    if variacoes and (not escolhida.exists() or _tamanho_png(escolhida) != tamanho):
        shutil.copyfile(saida / variacoes[0], escolhida)
    return info


def _tamanho_png(p: Path) -> tuple[int, int] | None:
    from PIL import Image

    try:
        with Image.open(p) as im:
            return im.size
    except Exception:  # noqa: BLE001 - arquivo quebrado conta como ausente
        return None


def escolher(projeto: ProjetoWS, clip_id: str, arquivo: str) -> Path:
    _, pasta = projeto.clip(clip_id)
    origem = pasta_thumbs(pasta) / Path(arquivo).name
    if not origem.is_file() or origem.suffix.lower() != ".png":
        raise FileNotFoundError(f"Variação não encontrada: {arquivo}")
    shutil.copyfile(origem, pasta / "thumb.png")
    return pasta / "thumb.png"


def listar(projeto: ProjetoWS, clip_id: str) -> dict:
    _, pasta = projeto.clip(clip_id)
    p = pasta_thumbs(pasta) / "thumbs.json"
    info = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"variacoes": [], "quadros": []}
    info["variacoes"] = [v for v in info.get("variacoes", []) if (pasta_thumbs(pasta) / v).exists()]
    info["ia"] = sorted(x.name for x in pasta_thumbs(pasta).glob("ia-*.png")) if pasta_thumbs(pasta).exists() else []
    info["escolhida"] = (pasta / "thumb.png").exists()
    return info


# ---- variações por imagem com o Codex ($imagegen) ----------------------------
def gerar_com_imagem(projeto: ProjetoWS, clip_id: str, quantidade: int = 2, progresso: Progress = _nada,
                     cancelar: threading.Event | None = None) -> list[str]:
    """Pede ao Codex variações por imagem, com o quadro real e os modelos do canal como referência.

    Exige o Codex logado num plano com geração de imagem. Experimental: se o Codex não
    salvar os arquivos, o erro diz o que ele respondeu.
    """
    from .ai.adapter import ErroIA, _rodar

    conf = projeto.ws.config()
    binario = shutil.which("codex") if conf.ia.imagens == "codex" else None
    if not binario:
        raise ErroIA("A thumbnail por imagem precisa do Codex instalado e logado (ChatGPT Plus ou superior).")
    clip, pasta = projeto.clip(clip_id)
    saida = pasta_thumbs(pasta)
    if not (saida / "thumbs.json").exists():
        gerar(projeto, clip_id, True, lambda f, m: progresso(f * 0.3, m), cancelar)
    info = json.loads((saida / "thumbs.json").read_text(encoding="utf-8"))
    cfg, thumb_md = projeto.canal.thumb()
    modelos = sorted(p for p in (projeto.canal.path / "thumbs" / "modelos").glob("*")
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))[:3]
    quadro = saida / "quadro-1.png"
    tw, th = tamanho_thumb(clip.formato)
    prompt = info.get("prompt_imagem") or (
        f"Thumbnail de YouTube {tw}x{th} com a frase \"{' / '.join(info.get('linhas') or [clip.titulo])}\", "
        f"palavras {', '.join(info.get('destaques') or [])} em {cfg.cor_destaque}, borda {cfg.cor_borda}.")
    pedido = "\n".join([
        prompt, "",
        "Use $imagegen. Monte sobre a primeira imagem anexada (quadro real do vídeo); nunca redesenhe o rosto.",
        "As outras imagens anexadas são modelos de thumbnail do canal: siga a composição e as cores." if modelos else "",
        thumb_md.strip(), "",
        f"Gere {quantidade} variações em {tw}x{th} e salve na pasta atual como ia-1.png, ia-2.png e assim por diante.",
    ])
    with tempfile.TemporaryDirectory(prefix="clipator-imagegen-") as tmp:
        imgs = ",".join(str(p) for p in [quadro, *modelos])
        cmd = [binario, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "-C", tmp, "-i", imgs, "-"]
        progresso(0.35, "gerando imagens no Codex")
        resposta = _rodar(cmd, pedido, conf.ia.timeout_s, cancelar, cwd=tmp)
        geradas = sorted(p for p in Path(tmp).rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
        if not geradas:
            raise ErroIA("O Codex não salvou nenhuma imagem. Resposta: " + resposta.strip()[-400:])
        existentes = len(list(saida.glob("ia-*.png")))
        out = []
        from PIL import Image

        for k, p in enumerate(geradas[:quantidade], existentes + 1):
            with Image.open(p) as im:
                _cobrir(im.convert("RGB"), tw, th).save(saida / f"ia-{k}.png")
            out.append(f"ia-{k}.png")
    (saida / f"ia-prompt-{existentes + 1}.txt").write_text(pedido, encoding="utf-8")
    progresso(1.0, "imagens prontas")
    return out

