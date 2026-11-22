"""Prévia de um corte no celular, do jeito que o short vai sair.

O celular não renderiza nada: ele recebe o vídeo original e aqui só monta o que falta para imitar o clip
no navegador. Vai o enquadramento vertical no rosto (o mesmo cálculo da prévia do app do PC), as palavras
faladas no trecho com o tempo de cada uma e o visual da legenda e da cartela do estilo escolhido.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import media, pipeline, transcribe
from .workspace import ProjetoWS, fontes_dir

ALTURA_POSICAO = {"topo": 0.16, "centro": 0.5, "centro-baixo": 0.66, "terco-inferior": 0.72, "baixo": 0.84}
LARGURA_QUADRO = 960  # 16:9 em 960x540 dá um recorte 9:16 de 304x540, nítido no cartão do celular


def _candidato(p: ProjetoWS, cid: str) -> dict:
    c = next((c for c in p.candidatos() if c.get("id") == cid), None)
    if c is None:
        raise KeyError(cid)
    return c


def rosto_x(p: ProjetoWS, cid: str) -> float:
    """Onde está o rosto (0 a 1 na largura). Usa os quadros e o cache do app do PC."""
    try:
        return pipeline.centro_rosto(p, cid, pipeline.quadros_candidato(p, cid))
    except (KeyError, FileNotFoundError, OSError, RuntimeError):
        return 0.5


def quadro_vertical(p: ProjetoWS, cid: str) -> Path:
    """Um quadro do meio do corte recortado em 9:16 em volta do rosto (fica em cache)."""
    from PIL import Image

    c = _candidato(p, cid)
    video = p.video_path()
    if video is None:
        raise FileNotFoundError("O projeto ainda não tem vídeo")
    pasta = p.analise_dir / "quadros"
    pasta.mkdir(parents=True, exist_ok=True)
    saida = pasta / f"{cid}_vertical.jpg"
    ref = p.candidatos_path.stat().st_mtime if p.candidatos_path.exists() else 0
    if saida.exists() and saida.stat().st_mtime >= ref:
        return saida
    bruto = pasta / f"{cid}_vertical_bruto.jpg"
    media.extrair_quadro(video, (float(c["inicio"]) + float(c["fim"])) / 2, bruto, largura=LARGURA_QUADRO)
    x = rosto_x(p, cid)
    with Image.open(bruto) as img:
        w, h = img.size
        cw = min(w, round(h * 9 / 16))
        esq = min(max(0, round(x * w - cw / 2)), w - cw)
        img.crop((esq, 0, esq + cw, h)).convert("RGB").save(saida, "JPEG", quality=82)
    bruto.unlink(missing_ok=True)
    return saida


def arquivo_fonte(nome: str) -> Path | None:
    """O .ttf embutido para o nome de fonte do estilo ("Montserrat ExtraBold" → Montserrat-ExtraBold.ttf)."""
    chave = re.sub(r"[^a-z0-9]", "", (nome or "").lower())
    if not chave:
        return None
    for f in sorted(fontes_dir().glob("*.[to]tf")):
        stem = re.sub(r"[^a-z0-9]", "", f.stem.lower())
        if stem == chave or stem == chave + "regular":
            return f
    return None


def dados(p: ProjetoWS, cid: str, estilo: str | None = None) -> dict[str, Any]:
    c = _candidato(p, cid)
    ws = p.ws
    canal_info, _ = p.canal.info()
    nome_estilo = estilo or ("corte-longo" if c.get("modo") == "longo" else canal_info.estilo_padrao)
    try:
        est, _, _ = ws.carregar_estilo(nome_estilo, p.canal)
    except Exception:  # noqa: BLE001 - estilo com erro: prévia com a legenda padrão
        from .models import Estilo

        est = Estilo()
    ini, fim = float(c["inicio"]), float(c["fim"])
    trans = p.transcricao() or {}
    palavras = [{"t": w["texto"], "i": round(w["inicio"], 3), "f": round(w["fim"], 3)}
                for w in transcribe.palavras(trans) if ini - 0.01 <= w["inicio"] < fim - 0.01]
    leg = est.legenda
    altura = leg.altura_relativa if leg.altura_relativa is not None else ALTURA_POSICAO.get(leg.posicao, 0.66)
    fontes = {n: f.name for n in {leg.fonte, est.cartela.fonte} if (f := arquivo_fonte(n))}
    return {
        "id": cid, "inicio": ini, "fim": fim, "vertical": c.get("modo") != "longo",
        "rosto_x": rosto_x(p, cid) if c.get("modo") != "longo" else 0.5,
        "titulo": (c.get("titulos") or [""])[0], "estilo": nome_estilo, "estilo_nome": est.nome or nome_estilo,
        "palavras": palavras, "fontes": fontes,
        "legenda": {"modo": leg.modo, "fonte": leg.fonte, "tamanho": leg.tamanho, "cor": leg.cor,
                    "destaque": leg.destaque, "contorno": leg.contorno, "espessura": leg.espessura_contorno,
                    "fundo": leg.fundo, "opacidade_fundo": leg.opacidade_fundo, "altura": altura,
                    "por_linha": leg.max_palavras_por_linha, "linhas": leg.linhas, "caixa_alta": leg.caixa_alta,
                    "italico": leg.italico, "sem_pontuacao": leg.remover_pontuacao},
        "cartela": {"mostrar": bool(est.cartela.sugerida and (c.get("titulos") or [""])[0]),
                    "duracao": est.cartela.duracao, "fonte": est.cartela.fonte, "tamanho": est.cartela.tamanho,
                    "cor": est.cartela.cor, "fundo": est.cartela.fundo, "posicao": est.cartela.posicao,
                    "caixa_alta": est.cartela.caixa_alta},
    }
