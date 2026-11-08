"""Ler referências visuais em números: paleta por área, cores de acento, claridade, contraste, temperatura e grão.

Uma referência é uma imagem (print, capa, quadro) ou um vídeo (amostramos alguns quadros com o FFmpeg). A análise
roda em CIELAB, que separa claridade (L*) de cor (a*, b*), com um k-means simples em numpy. Duas leituras de cor
diferentes, porque respondem perguntas diferentes:

- **Paleta por área**: de que a imagem é feita (o fundo, a superfície, a pele). A cor de assinatura quase nunca
  aparece aqui: um marca-texto que ocupa 1 % do quadro some na média.
- **Acentos**: as cores vivas (croma alto) a partir de uma área pequena, uma por família de matiz, lidas nos pixels
  mais puros. É daqui que costuma sair a `primaria`.

Os candidatos a token são uma proposta para conversar, não uma regra.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import cores as C

IMAGENS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEOS = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
LADO_ANALISE = 240
CROMA_ACENTO = 45.0
AREA_ACENTO = 0.003
SAIDAS = ("referencias_analise.json", "referencias_folha.png")


@dataclass
class Leitura:
    nome: str
    paleta: list[dict[str, Any]] = field(default_factory=list)
    acentos: list[dict[str, Any]] = field(default_factory=list)
    L_medio: float = 0.0
    L_p5: float = 0.0
    L_p95: float = 0.0
    saturacao_media: float = 0.0
    b_medio: float = 0.0
    grao: float = 0.0


def _srgb_lab_np(rgb):
    import numpy as np

    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    d = 6 / 29
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def _kmeans(x, k: int, iteracoes: int = 20):
    """k-means determinístico: sementes pelo método farthest-point a partir do pixel mais escuro."""
    import numpy as np

    k = max(1, min(k, len(x)))
    centros = [x[int(np.argmin(x[:, 0]))]]
    dist = np.full(len(x), np.inf)
    for _ in range(1, k):
        dist = np.minimum(dist, ((x - centros[-1]) ** 2).sum(1))
        centros.append(x[int(np.argmax(dist))])
    c = np.array(centros)
    rotulos = np.zeros(len(x), dtype=int)
    for it in range(iteracoes):
        d = ((x[:, None, :] - c[None, :, :]) ** 2).sum(2)
        novos = d.argmin(1)
        if (novos == rotulos).all() and it > 0:
            break
        rotulos = novos
        for i in range(k):
            sel = x[rotulos == i]
            if len(sel):
                c[i] = sel.mean(0)
    return c, rotulos


def _lab_hex(lab) -> str:
    return C.rgb_hex(C.lab_rgb((float(lab[0]), float(lab[1]), float(lab[2]))))


def analisar_imagem(img, nome: str, k: int = 8) -> Leitura:
    """`img`: PIL.Image. Devolve a Leitura (paleta, acentos e números do quadro)."""
    import numpy as np

    im = img.convert("RGB")
    im.thumbnail((LADO_ANALISE, LADO_ANALISE))
    arr = np.asarray(im)
    lab = _srgb_lab_np(arr).reshape(-1, 3)
    n = len(lab)
    centros, rot = _kmeans(lab, k)
    paleta = []
    for i, c in enumerate(centros):
        area = float((rot == i).sum()) / n
        if area < 0.004:
            continue
        paleta.append({"hex": _lab_hex(c), "area": round(area, 4), "L": round(float(c[0]), 1),
                       "croma": round(float(math.hypot(c[1], c[2])), 1)})
    paleta.sort(key=lambda p: -p["area"])
    # acentos: pixels de croma alto, agrupados por faixa de matiz de 30°, lidos no quartil mais puro
    cr = np.hypot(lab[:, 1], lab[:, 2])
    hue = (np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) + 360) % 360
    vivos = cr >= CROMA_ACENTO
    acentos = []
    for faixa in range(12):
        sel = vivos & (hue >= faixa * 30) & (hue < faixa * 30 + 30)
        area = float(sel.sum()) / n
        if area < AREA_ACENTO:
            continue
        px = lab[sel]
        corte = np.quantile(cr[sel], 0.75)
        puros = px[cr[sel] >= corte]
        cor = np.median(puros, axis=0)
        acentos.append({"hex": _lab_hex(cor), "area": round(area, 4), "croma": round(float(math.hypot(cor[1], cor[2])), 1)})
    acentos.sort(key=lambda a: -(a["area"] * a["croma"]))
    # grão: desvio do que sobra depois de um desfoque 3x3 na claridade
    L = lab[:, 0].reshape(arr.shape[:2])
    if min(L.shape) >= 3:
        media = sum(np.roll(np.roll(L, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
        resid = (L - media)[1:-1, 1:-1]
        grao = float(np.median(np.abs(resid)) * 1.4826)
    else:
        grao = 0.0
    return Leitura(nome=nome, paleta=paleta, acentos=acentos[:5], L_medio=round(float(L.mean()), 1),
                   L_p5=round(float(np.percentile(L, 5)), 1), L_p95=round(float(np.percentile(L, 95)), 1),
                   saturacao_media=round(float(cr.mean()) / 100, 3), b_medio=round(float(lab[:, 2].mean()), 2),
                   grao=round(grao, 2))


def quadros_de_video(video: Path, n: int = 6) -> list:
    """N quadros espalhados pelo vídeo (pula os 5 % do começo e do fim)."""
    from PIL import Image

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        return []
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "default=nw=1:nk=1", str(video)], capture_output=True, text=True,
                                   timeout=60).stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError):
        return []
    if dur <= 0:
        return []
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            t = dur * (0.05 + 0.9 * (i + 0.5) / n)
            alvo = Path(tmp) / f"q{i}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                            "-vf", f"scale={LADO_ANALISE * 2}:-2", str(alvo)], capture_output=True, timeout=120,
                           stdin=subprocess.DEVNULL)
            if alvo.exists():
                with Image.open(alvo) as im:
                    out.append(im.copy())
    return out


def coletar(caminhos: list[Path], quadros: int = 6) -> list[tuple[str, Any]]:
    """[(nome, PIL.Image)] de imagens, pastas (tudo o que há nelas) e vídeos."""
    from PIL import Image

    arquivos: list[Path] = []
    for c in caminhos:
        if c.is_dir():
            arquivos += sorted(p for p in c.iterdir() if p.suffix.lower() in IMAGENS + VIDEOS and p.name not in SAIDAS)
        elif c.exists():
            arquivos.append(c)
    out = []
    for p in arquivos:
        if p.suffix.lower() in IMAGENS:
            try:
                with Image.open(p) as im:
                    out.append((p.name, im.copy()))
            except OSError:
                continue
        elif p.suffix.lower() in VIDEOS:
            for i, im in enumerate(quadros_de_video(p, quadros), 1):
                out.append((f"{p.name} · quadro {i}", im))
    return out


def candidatos(leituras: list[Leitura]) -> dict[str, dict[str, Any]]:
    """Proposta de fundo, superfície, texto e primária a partir do conjunto."""
    juntas: dict[str, float] = {}
    for l in leituras:
        for p in l.paleta:
            juntas[p["hex"]] = juntas.get(p["hex"], 0) + p["area"] / max(1, len(leituras))
    if not juntas:
        return {}
    neutras = {h: a for h, a in juntas.items() if C.croma(h) < 18}
    base = neutras or juntas
    escuras = {h: a for h, a in base.items() if C.rgb_lab(h)[0] < 35}
    claras = {h: a for h, a in base.items() if C.rgb_lab(h)[0] > 75}
    if sum(escuras.values()) >= sum(claras.values()) and escuras:
        fundo = max(escuras, key=escuras.get)
        motivo_f = f"cor escura dominante ({sum(escuras.values()) * 100:.0f}% da área)"
    elif claras:
        fundo = max(claras, key=claras.get)
        motivo_f = f"cor clara dominante ({sum(claras.values()) * 100:.0f}% da área)"
    else:
        fundo = max(base, key=base.get)
        motivo_f = "cor de maior área"
    L = C.rgb_lab(fundo)[0]
    if L < 4:  # preto puro vira “preto de tela”
        fundo = C.deslocar_luminosidade(fundo, 4 - L)
    elif L > 97:
        fundo = C.deslocar_luminosidade(fundo, 97 - L)
    escuro = C.luminancia(fundo) < 0.18
    superficie = C.deslocar_luminosidade(fundo, 9 if escuro else -6)
    opcoes = sorted(juntas, key=lambda h: -C.contraste(h, fundo))
    texto = opcoes[0] if opcoes and C.contraste(opcoes[0], fundo) >= 7 else ("#F4F2EE" if escuro else "#16171A")
    out = {"fundo": {"hex": fundo, "motivo": motivo_f},
           "superficie": {"hex": superficie, "motivo": "o fundo um degrau acima (L* ± 6 a 9)"},
           "texto": {"hex": texto, "motivo": f"maior contraste com o fundo ({C.contraste(texto, fundo):.1f}:1)"}}
    acentos: dict[str, float] = {}
    for l in leituras:
        for a in l.acentos:
            acentos[a["hex"]] = acentos.get(a["hex"], 0) + a["area"] * a["croma"]
    if acentos:
        prim = max(acentos, key=acentos.get)
        prim = C.saturar(prim, 1.08)  # compressão e tela de celular tiram um pouco de cor
        k = C.contraste(prim, fundo)
        motivo = f"acento: a cor viva mais presente (croma {C.croma(prim):.0f}); contraste {k:.1f}:1 com o fundo"
        if k < 3:
            motivo += " — baixo: use em bloco chapado com texto por cima, não como cor de texto"
        out["primaria"] = {"hex": prim, "motivo": motivo}
    else:
        viva = max(juntas, key=lambda h: C.croma(h))
        out["primaria"] = {"hex": viva, "motivo": "NENHUMA cor de acento nas referências: esta é só a mais viva por "
                           "área (pode ser pele, madeira ou luz). A primária deve vir do briefing ou de uma referência "
                           "de design (cartela, capa, print)"}
    return out


def leitura_texto(l: Leitura) -> list[str]:
    linhas = []
    linhas.append(f"claridade média L* {l.L_medio:.0f} de 100 ("
                  + ("escura" if l.L_medio < 35 else "clara" if l.L_medio > 65 else "média") + ")")
    amp = l.L_p95 - l.L_p5
    linhas.append(f"contraste {'alto' if amp > 70 else 'baixo' if amp < 35 else 'médio'} (L* de {l.L_p5:.0f} a "
                  f"{l.L_p95:.0f} entre os percentis 5 e 95)")
    linhas.append(f"saturação {'alta' if l.saturacao_media > 0.35 else 'baixa' if l.saturacao_media < 0.15 else 'média'}"
                  f" (croma médio {l.saturacao_media * 100:.0f})")
    linhas.append(f"temperatura {C.temperatura_rotulo(l.b_medio)} (b* médio {l.b_medio:.1f})")
    sugestao = max(0.0, min(12.0, (l.grao - 0.6) * 3))
    linhas.append(f"grão {'limpo' if l.grao < 1 else 'leve' if l.grao < 2.5 else 'forte'} (desvio {l.grao:.1f}); "
                  f"tratamento.grao ≈ {sugestao:.0f}")
    return linhas


def extrair(caminhos: list[Path], saida: Path | None = None, quadros: int = 6, k: int = 8) -> dict[str, Any]:
    """Analisa as referências; com `saida` (uma pasta), grava a análise em JSON e a folha em PNG."""
    imagens = coletar(caminhos, quadros)
    if not imagens:
        raise FileNotFoundError("nenhuma imagem ou vídeo legível nas referências")
    leituras = [analisar_imagem(im, nome, k) for nome, im in imagens]
    cand = candidatos(leituras)
    resultado = {"referencias": [l.__dict__ for l in leituras], "candidatos": cand,
                 "leitura": {l.nome: leitura_texto(l) for l in leituras}}
    if saida is not None:
        saida.mkdir(parents=True, exist_ok=True)
        (saida / SAIDAS[0]).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        folha(imagens, leituras, cand).save(saida / SAIDAS[1])
        resultado["arquivos"] = [str(saida / s) for s in SAIDAS]
    return resultado


def folha(imagens, leituras: list[Leitura], cand: dict[str, dict[str, Any]]):
    """Folha de contato: miniatura, paleta e acentos de cada referência, e os candidatos a token no fim."""
    from PIL import Image, ImageDraw, ImageFont

    W, linha_h, mini = 1600, 210, 300
    altura = 90 + linha_h * len(imagens) + 70 + 70 * max(1, len(cand))
    img = Image.new("RGB", (W, altura), "#16171A")
    d = ImageDraw.Draw(img)
    f_t, f, f_p = (ImageFont.load_default(32), ImageFont.load_default(20), ImageFont.load_default(16))
    d.text((40, 28), "Referências: paleta por área, acentos e leitura", fill="#F2F2F2", font=f_t)
    y = 90
    for (nome, im), l in zip(imagens, leituras):
        t = im.convert("RGB")
        t.thumbnail((mini, linha_h - 30))
        img.paste(t, (40, y))
        d.text((360, y), nome[:70], fill="#F2F2F2", font=f)
        x = 360
        for p in l.paleta[:8]:
            d.rectangle((x, y + 34, x + 90, y + 94), fill=p["hex"])
            d.text((x, y + 98), f"{p['hex']} {p['area'] * 100:.1f}%", fill="#BBBBBB", font=f_p)
            x += 100
        x = 360
        for a in l.acentos[:5]:
            d.ellipse((x, y + 126, x + 36, y + 162), fill=a["hex"])
            d.text((x + 44, y + 134), f"acento {a['hex']} {a['area'] * 100:.1f}%", fill="#BBBBBB", font=f_p)
            x += 230
        y += linha_h
    d.text((40, y + 20), "Candidatos a token (proposta para conversar)", fill="#F2F2F2", font=f_t)
    y += 70
    for nome, c in cand.items():
        d.rectangle((40, y, 130, y + 50), fill=c["hex"])
        d.text((150, y + 4), f"{nome}  {c['hex']}", fill="#F2F2F2", font=f)
        d.text((150, y + 28), c["motivo"][:150], fill="#BBBBBB", font=f_p)
        y += 70
    return img
