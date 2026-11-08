"""Qual estilo animado combina com o tema do corte: uma conta offline, sem IA, pelo que a fala e o título dizem.

Cada estilo de curta tem um perfil de assuntos (raízes de palavras). A nota é quantas vezes a fala toca nesse perfil,
com peso maior para o título e o tema; o motivo mostra as palavras que pesaram. Serve para o passo 3 marcar o estilo
sugerido. Empate ou fala sem nada do perfil: o Encaixe Vivo, que funciona para qualquer assunto.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# raízes (prefixos sem acento) dos assuntos em que cada estilo conta melhor a história
PERFIS: dict[str, dict[str, Any]] = {
    "arte-encaixe-vivo": {"motivo": "fala de produto, peça, hardware ou de montar algo", "raizes": (
        "peca", "placa", "chip", "hardware", "gpu", "processador", "computador", "maquina", "montar", "monta", "constru", "produto",
        "componente", "fabric", "industri", "engenh", "startup", "empresa", "negocio", "loja", "venda", "vender", "preco", "custa",
        "robo", "brinquedo", "projeto", "ferramenta")},
    "arte-pixel-em-cena": {"motivo": "fala de jogo, internet, código, IA ou cultura digital", "raizes": (
        "jogo", "game", "gamer", "joga", "videogame", "internet", "online", "codigo", "program", "softwar", "app", "aplicativo",
        "modelo", "llm", "inteligencia", "artificial", "ia", "chatgpt", "algoritm", "hacker", "nerd", "pixel", "digital", "rede",
        "bot", "streamer", "youtube", "aleatori", "temperatura", "treinad", "dados")},
    "arte-fluxo-facetado": {"motivo": "fala de processo, ciência, natureza ou de como algo funciona por dentro", "raizes": (
        "process", "fluxo", "funciona", "ciencia", "cientist", "pesquis", "natureza", "energia", "corpo", "cerebro", "mente",
        "saude", "biolog", "quimic", "fisic", "evolu", "transform", "sistema", "ciclo", "etapa", "cadeia", "economia", "mercado",
        "inflacao", "juros")},
    "arte-rota-em-foco": {"motivo": "fala de caminho, estratégia, carreira ou de para onde algo vai", "raizes": (
        "caminho", "rota", "viagem", "viajar", "estrada", "destino", "plano", "estrateg", "carreira", "futuro", "passo", "trajet",
        "direcao", "objetivo", "meta", "decis", "escolh", "beco", "saida", "chegar", "logistic", "entrega", "percurso", "mapa",
        "pesquisador", "aposta", "rumo")},
    "arte-terreno-vivo": {"motivo": "fala de lugar, território, construção, cidade, agro ou meio ambiente", "raizes": (
        "terreno", "terra", "lugar", "cidade", "constru", "obra", "predio", "imove", "casa", "bairro", "agro", "fazenda", "plant",
        "colheita", "soja", "gado", "clima", "ambiente", "ecolog", "floresta", "agua", "rio", "energia", "eletric", "infraestrutura",
        "data center", "datacenter", "territorio", "regiao", "campo", "solo")},
    "arte-geo-em-cena": {"motivo": "cita países, estados e cidades reais: mostra no mapa", "raizes": (
        "pais", "paises", "estados unidos", "brasil", "china", "europa", "japao", "india", "russia", "africa", "america", "islandia",
        "groenlandia", "argentina", "mexico", "canada", "alemanha", "franca", "inglaterra", "geopolit", "fronteira", "continente",
        "mapa", "regiao", "estado", "capital")},
}
PADRAO = "arte-encaixe-vivo"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _toques(texto: str, raizes: tuple[str, ...]) -> dict[str, int]:
    t = _norm(texto)
    palavras = re.findall(r"[a-z0-9]+", t)
    junto = " " + " ".join(palavras) + " "
    out: dict[str, int] = {}
    for r in raizes:
        n = junto.count(" " + r + " ") if " " in r else sum(1 for p in palavras if p.startswith(r) and (len(r) > 2 or p == r))
        if n:
            out[r] = n
    return out


def sugerir(texto: str, titulo: str = "", tema: str = "", visiveis: list[str] | None = None) -> list[dict[str, Any]]:
    """[{estilo, nota (0..1), motivo, palavras}] do mais ao menos indicado, só com os estilos visíveis."""
    res = []
    for estilo, perfil in PERFIS.items():
        if visiveis is not None and estilo not in visiveis:
            continue
        corpo = _toques(texto, perfil["raizes"])
        topo = _toques(f"{titulo} {tema}", perfil["raizes"])
        pontos = sum(min(3, n) for n in corpo.values()) + 2.5 * sum(min(2, n) for n in topo.values())
        palavras = sorted({**corpo, **topo}, key=lambda r: -(corpo.get(r, 0) + 3 * topo.get(r, 0)))[:4]
        res.append({"estilo": estilo, "pontos": pontos, "motivo": perfil["motivo"], "palavras": palavras})
    if not res:
        return []
    maximo = max(r["pontos"] for r in res) or 1.0
    res.sort(key=lambda r: (-r["pontos"], r["estilo"] != PADRAO))
    return [{"estilo": r["estilo"], "nota": round(r["pontos"] / maximo, 2), "motivo": r["motivo"], "palavras": r["palavras"]} for r in res]


def do_candidato(cand: dict[str, Any], visiveis: list[str] | None = None) -> list[dict[str, Any]]:
    titulos = cand.get("titulos") or []
    return sugerir(str(cand.get("texto") or ""), str(titulos[0] if titulos else ""), str(cand.get("tema") or cand.get("motivo") or ""), visiveis)
