"""Desenho animado em cima do vídeo: a IA analisa o corte, escreve o roteiro do desenho e compõe as cenas.

Três etapas, todas pelo adaptador (texto entra, JSON por schema sai), conferidas aqui:

1. **Análise**: o tema do trecho e as ideias com tempo (dado, comparação, exemplo, pergunta, negação…),
   cada uma presa ao trecho da fala que a sustenta.
2. **Roteiro**: as cenas do desenho, uma por ideia: o que aparece, a etiqueta do tema, o dado em destaque
   e a frase de um balão, sempre ligadas à fala.
3. **Composição**: cada cena vira camadas sobre um palco fixo (1000×860): peças da biblioteca (desenhos de
   traço feitos aqui, com rótulo), textos, balões e gráficos de dados, cada uma com posição, cor, o
   segundo em que entra e o jeito de entrar. A IA decide a composição; o desenho é nosso.

O resultado fica em clips/<id>/direcao-arte.json (análise, roteiro, composição, ficha) e as cenas viram
itens "cena" do tipo "desenho" no edicao.json, que a camada de cenas (direcao.py) desenha em SVG com
animação CSS, renderizada pelo HyperFrames. O usuário pode editar o roteiro e refazer.

Os estilos de cenas (`direcao: {modo: cenas}`) passam pela mesma pré-produção: análise e roteiro iguais, e na
terceira etapa a IA transforma cada cena do roteiro num dos cartões do direcao.py, em vez de camadas de desenho.
"""

from __future__ import annotations

import html
import json
import re
import threading
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

ARQUIVO = "direcao-arte.json"
PALCO = (1000, 860)  # o palco de cada cena (a metade de cima de um 9:16), em unidades do SVG
COR_CAMADA = ("texto", "primaria", "destaque", "bom", "ruim", "suave")
ACOES = ("pop", "desenha", "desliza", "cai", "cresce", "pulsa", "treme", "nenhuma")
GRAFICOS = ("numero", "grade", "barras", "linha", "nenhum")
TIPOS_IDEIA = ("dado", "comparacao", "exemplo", "pergunta", "negacao", "lista", "emocao", "historia")

# ---- biblioteca de peças (traço próprio do Clipator; viewBox 0 0 100 100, cor pela variável do item) ----------
_P = 'fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"'
PECAS: dict[str, tuple[str, str]] = {
    # nome: (descrição para a IA, desenho)
    "boneco": ("pessoa em traço (palito)", f'<g {_P}><circle cx="50" cy="18" r="11"/><path d="M50 29v36M50 40l-18 14M50 40l18 14M50 65l-14 26M50 65l14 26"/></g>'),
    "boneco_bracos": ("pessoa com os braços para cima (comemorando, surpresa)", f'<g {_P}><circle cx="50" cy="20" r="11"/><path d="M50 31v34M50 42l-16-20M50 42l16-20M50 65l-14 26M50 65l14 26"/></g>'),
    "pessoa": ("bonequinho com corpo cheio (público, multidão, estatística)", '<g fill="currentColor"><circle cx="50" cy="22" r="13"/><path d="M28 92V56a22 22 0 0 1 44 0v36z"/></g>'),
    "casa": ("casa", f'<g {_P}><path d="M14 48 50 16l36 32M22 42v44h56V42"/><path d="M43 86V62h14v24"/></g>'),
    "predio": ("prédio, empresa", f'<g {_P}><rect x="24" y="10" width="52" height="80" rx="2"/><path d="M36 24h8M56 24h8M36 40h8M56 40h8M36 56h8M56 56h8M44 90V74h12v16"/></g>'),
    "loja": ("loja", f'<g {_P}><path d="M14 40h72v48H14zM10 40l10-24h60l10 24"/><path d="M44 88V64h14v24M22 52h14v12H22z"/></g>'),
    "celular": ("celular", f'<g {_P}><rect x="28" y="8" width="44" height="84" rx="7"/><path d="M44 80h12"/></g>'),
    "computador": ("computador", f'<g {_P}><rect x="12" y="16" width="76" height="50" rx="4"/><path d="M38 84h24M50 66v18"/></g>'),
    "moeda": ("moeda de dinheiro", f'<g {_P}><circle cx="50" cy="50" r="36"/><path d="M60 36c-4-5-20-6-20 4 0 11 22 7 22 18 0 11-18 10-23 4M50 26v8M50 66v8"/></g>'),
    "nota": ("nota de dinheiro", f'<g {_P}><rect x="10" y="28" width="80" height="44" rx="4"/><circle cx="50" cy="50" r="11"/><path d="M20 38v24M80 38v24"/></g>'),
    "saco_dinheiro": ("saco de dinheiro, fortuna", f'<g {_P}><path d="M38 22h24l-6 12c18 6 26 22 26 34 0 14-14 22-32 22S18 82 18 68c0-12 8-28 26-34z"/><path d="M56 52c-3-4-14-4-14 2 0 7 15 4 15 11 0 6-12 6-16 2M50 46v4M50 70v4"/></g>'),
    "balanca": ("balança (comparar, justiça)", f'<g {_P}><path d="M50 14v72M30 86h40M18 30h64M18 30 8 56h20zM82 30l-10 26h20z"/><circle cx="50" cy="14" r="4"/></g>'),
    "grafico_sobe": ("gráfico subindo", f'<g {_P}><path d="M12 88h78M12 88V12"/><path d="M20 74l20-18 14 10 26-32"/><path d="M70 34h10v10"/></g>'),
    "grafico_desce": ("gráfico caindo", f'<g {_P}><path d="M12 88h78M12 88V12"/><path d="M20 30l20 18 14-10 26 32"/><path d="M70 70h10V60"/></g>'),
    "seta": ("seta para a direita", f'<g {_P}><path d="M12 50h70M62 30l20 20-20 20"/></g>'),
    "balao": ("balão de fala vazio", f'<g {_P}><path d="M14 18h72v46H44L28 82V64H14z"/></g>'),
    "check": ("certo, confirmado", f'<g {_P}><path d="M18 52l20 20 44-46"/></g>'),
    "x": ("errado, não, negação", f'<g {_P}><path d="M22 22l56 56M78 22 22 78"/></g>'),
    "interrogacao": ("dúvida, pergunta", f'<g {_P}><path d="M34 34c0-12 8-20 18-20s18 7 18 17c0 14-18 14-18 30"/><circle cx="52" cy="82" r="2"/></g>'),
    "exclamacao": ("atenção, surpresa", f'<g {_P}><path d="M50 14v50"/><circle cx="50" cy="82" r="2"/></g>'),
    "relogio": ("relógio, tempo, horário", f'<g {_P}><circle cx="50" cy="52" r="36"/><path d="M50 30v22l16 10M40 10h20"/></g>'),
    "calendario": ("calendário, data", f'<g {_P}><rect x="14" y="18" width="72" height="68" rx="4"/><path d="M14 38h72M32 10v16M68 10v16M30 54h8M46 54h8M62 54h8M30 70h8M46 70h8"/></g>'),
    "globo": ("mundo, internet, global", f'<g {_P}><circle cx="50" cy="50" r="38"/><path d="M12 50h76M50 12c-14 16-14 60 0 76M50 12c14 16 14 60 0 76"/></g>'),
    "lupa": ("lupa, investigar, procurar", f'<g {_P}><circle cx="42" cy="42" r="24"/><path d="M60 60l26 26"/></g>'),
    "trofeu": ("troféu, vitória", f'<g {_P}><path d="M30 14h40v20a20 20 0 0 1-40 0zM30 22H16c0 14 8 20 16 20M70 22h14c0 14-8 20-16 20M50 54v16M34 86h32l-4-16H38z"/></g>'),
    "coracao": ("coração, amor, gostar", f'<g {_P}><path d="M50 84S12 60 12 34c0-12 10-20 20-20 8 0 14 5 18 12 4-7 10-12 18-12 10 0 20 8 20 20 0 26-38 50-38 50z"/></g>'),
    "alerta": ("alerta, perigo", f'<g {_P}><path d="M50 12 90 84H10z"/><path d="M50 38v22"/><circle cx="50" cy="72" r="2"/></g>'),
    "cadeado": ("cadeado, preso, bloqueado", f'<g {_P}><rect x="22" y="44" width="56" height="44" rx="6"/><path d="M34 44V32a16 16 0 0 1 32 0v12M50 62v10"/></g>'),
    "carro": ("carro", f'<g {_P}><path d="M10 62l8-22h64l8 22v14H10z"/><circle cx="28" cy="78" r="8"/><circle cx="72" cy="78" r="8"/><path d="M26 40l6-14h36l6 14"/></g>'),
    "barco": ("barco, iate, luxo", f'<g {_P}><path d="M8 62h84L78 82H22zM24 62V46h40l14 16M34 46V34h20v12"/></g>'),
    "lampada": ("ideia, lâmpada", f'<g {_P}><path d="M36 64c-8-6-14-14-14-26a28 28 0 0 1 56 0c0 12-6 20-14 26v10H36z"/><path d="M40 84h20M44 92h12"/></g>'),
    "megafone": ("anúncio, falar alto", f'<g {_P}><path d="M14 40v20h14l36 18V22L28 40z"/><path d="M28 60l6 22h10l-4-20M74 38c6 6 6 18 0 24"/></g>'),
    "livro": ("livro, estudo", f'<g {_P}><path d="M50 22c-10-6-24-8-38-6v64c14-2 28 0 38 6 10-6 24-8 38-6V16c-14-2-28 0-38 6zM50 22v64"/></g>'),
    "raio": ("energia, rápido, impacto", f'<g {_P}><path d="M56 8 22 56h24l-6 36 36-50H52z"/></g>'),
    "estrela": ("destaque, especial", f'<g {_P}><path d="M50 12l11 24 26 3-19 18 5 26-23-13-23 13 5-26-19-18 26-3z"/></g>'),
    "documento": ("documento, contrato, papel", f'<g {_P}><path d="M24 10h36l16 16v64H24z"/><path d="M60 10v16h16M34 44h32M34 56h32M34 68h20"/></g>'),
    "porta": ("porta, entrada", f'<g {_P}><rect x="28" y="12" width="44" height="78" rx="2"/><circle cx="62" cy="52" r="3"/></g>'),
    "predios": ("cidade pequena", f'<g {_P}><path d="M8 90V50h20v40M28 90V24h26v66M54 90V40h18v50M72 90V58h20v32"/></g>'),
}

# ---- fichas do desenho -------------------------------------------------------------------------------------
FICHAS_DESENHO = {
    # nome: cores, fonte, cenário (fundo fixo do palco)
    "quadro": {"fundo": "#1B0C0E", "superficie": "#2A1316", "texto": "#F4EEE6", "texto_suave": "#B9A9A4", "primaria": "#F2B632",
               "destaque": "#F2B632", "bom": "#3DDC84", "ruim": "#E5484D", "fonte_titulo": "Montserrat ExtraBold",
               "fonte_corpo": "Montserrat ExtraBold", "cenario": "cidade", "entrada": "escala",
               "sons": {"entrada": "pop", "enfase": "click", "numero": "click", "alerta": "impacto"}},
    "noite": {"fundo": "#070A14", "superficie": "#0E1426", "texto": "#E8F1FF", "texto_suave": "#7E8BB3", "primaria": "#3AA0FF",
             "destaque": "#FFC24A", "bom": "#3BF57E", "ruim": "#FF3B5C", "fonte_titulo": "Anton", "fonte_corpo": "Montserrat ExtraBold",
             "cenario": "cidade-neon", "entrada": "escala", "sons": {"entrada": "whoosh", "enfase": "pop", "numero": "click", "alerta": "impacto"}},
    "caderno": {"fundo": "#F4EFE4", "superficie": "#FFFFFF", "texto": "#2B2B2B", "texto_suave": "#7A746A", "primaria": "#3F7D58",
                "destaque": "#E3B23C", "bom": "#3F7D58", "ruim": "#B23A48", "fonte_titulo": "Montserrat ExtraBold",
                "fonte_corpo": "Montserrat ExtraBold", "cenario": "caderno", "entrada": "sobe",
                "sons": {"entrada": "click", "enfase": "pop", "numero": "click", "alerta": "ding"}},
    # maquete low-poly: peças facetadas (maquete.py), poeira desfocada no fundo, cabeçalho, rótulos com fio e carimbo
    "maquete": {"fundo": "#0B1221", "superficie": "#141F36", "texto": "#F3F5F9", "texto_suave": "#8794AE", "primaria": "#FF8A3D",
                "destaque": "#FF8A3D", "bom": "#45D483", "ruim": "#FF5A5F", "fonte_titulo": "Montserrat ExtraBold",
                "fonte_corpo": "Montserrat ExtraBold", "cenario": "poeira", "pecas": "maquete", "entrada": "fade",
                "lp": {"claro": "#F1F3F7", "medio": "#C9D0DC", "meio": "#AEB7C6", "escuro": "#7F8AA0"},
                "sons": {"entrada": "whoosh", "enfase": "click", "numero": "click", "alerta": "impacto"}},
}
DICAS_FICHA = {
    "maquete": ("Formato maquete explicativa: uma maquete 3D low-poly (objetos simples, brancos e cinza, com um detalhe colorido) "
                "explica o assunto em etapas. Cada cena é uma etapa com 'etiqueta' curta (o nome da etapa, ex.: A ORIGEM, O PROBLEMA, "
                "O RESULTADO), a peça principal grande no centro, um rótulo curto preso a ela, e quando houver número, um painel "
                "com o dado. A última cena fecha com um carimbo de conclusão (camada texto)."),
}


def ficha_desenho(nome: str | None, ajustes: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(FICHAS_DESENHO.get(nome or "quadro", FICHAS_DESENHO["quadro"]))
    for k, v in (ajustes or {}).items():
        if k in base and isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            base[k] = v.upper()
    return base


# ---- validação das camadas ---------------------------------------------------------------------------------
def _num(v: Any, padrao: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return padrao
    return padrao if x != x else max(lo, min(hi, x))


def _txt(v: Any, lim: int) -> str:
    return " ".join(str(v or "").split())[:lim]


def normalizar_camada(c: Any) -> dict[str, Any] | None:
    """Uma camada da cena, dentro dos limites; None se não serve."""
    if not isinstance(c, dict):
        return None
    tipo = c.get("tipo") if c.get("tipo") in ("peca", "texto", "balao", "dado", "multidao") else "peca"
    out: dict[str, Any] = {"tipo": tipo, "x": round(_num(c.get("x"), 500, 0, 1000)), "y": round(_num(c.get("y"), 430, 0, PALCO[1])),
                           "escala": round(_num(c.get("escala"), 1.0, 0.3, 3.0), 2), "entra": round(_num(c.get("entra"), 0.0, 0.0, 8.0), 2),
                           "acao": c.get("acao") if c.get("acao") in ACOES else "pop",
                           "cor": c.get("cor") if c.get("cor") in COR_CAMADA else "texto"}
    if tipo in ("peca", "multidao"):
        if c.get("peca") not in PECAS:
            return None
        out["peca"] = c["peca"]
        if tipo == "multidao":
            out["quantos"] = int(_num(c.get("quantos"), 12, 2, 40))
    rot = _txt(c.get("rotulo") or c.get("texto"), 60)
    if tipo in ("texto", "balao") and not rot:
        return None
    if rot:
        out["rotulo"] = rot
    if tipo == "dado":
        g = c.get("grafico") if c.get("grafico") in GRAFICOS else "numero"
        out["grafico"] = g
        out["valor"] = _txt(c.get("valor"), 16)
        if not out["valor"] and g != "barras":
            return None
        vals = c.get("valores")
        if isinstance(vals, list):
            out["valores"] = [round(_num(x, 0, 0, 1e12), 2) for x in vals][:6]
        rots = c.get("rotulos")
        if isinstance(rots, list):
            out["rotulos"] = [_txt(x, 20) for x in rots][:6]
    return out


def normalizar_desenho(p: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"cena": "desenho"}
    for k, lim in (("etiqueta", 40), ("ancora", 140), ("descricao", 240), ("texto", 90), ("cabecalho", 48)):
        if p.get(k):
            out[k] = _txt(p[k], lim)
    camadas = [x for x in (normalizar_camada(c) for c in (p.get("camadas") or [])[:16]) if x]
    out["camadas"] = camadas
    return out


# ---- as três etapas ---------------------------------------------------------------------------------------
SCHEMA_ANALISE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tema": {"type": "string"},
        "ideias": {"type": "array", "items": {"type": "object", "properties": {
            "ancora": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPOS_IDEIA)},
            "resumo": {"type": "string"}, "dado": {"type": "string"}},
            "required": ["ancora", "tipo", "resumo", "dado"], "additionalProperties": False}},
    },
    "required": ["tema", "ideias"], "additionalProperties": False,
}
SCHEMA_ROTEIRO: dict[str, Any] = {
    "type": "object",
    "properties": {"cenas": {"type": "array", "items": {"type": "object", "properties": {
        "ancora": {"type": "string"}, "ate": {"type": "string"}, "etiqueta": {"type": "string"}, "descricao": {"type": "string"},
        "dado": {"type": "string"}, "balao": {"type": "string"}},
        "required": ["ancora", "ate", "etiqueta", "descricao", "dado", "balao"], "additionalProperties": False}}},
    "required": ["cenas"], "additionalProperties": False,
}
_CAMADA_SCHEMA = {"type": "object", "properties": {
    "tipo": {"type": "string", "enum": ["peca", "texto", "balao", "dado", "multidao"]},
    "peca": {"type": "string"}, "rotulo": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"},
    "escala": {"type": "number"}, "entra": {"type": "number"}, "acao": {"type": "string", "enum": list(ACOES)},
    "cor": {"type": "string", "enum": list(COR_CAMADA)}, "grafico": {"type": "string", "enum": list(GRAFICOS)},
    "valor": {"type": "string"}, "valores": {"type": "array", "items": {"type": "number"}},
    "rotulos": {"type": "array", "items": {"type": "string"}}, "quantos": {"type": "number"}},
    "required": ["tipo", "peca", "rotulo", "x", "y", "escala", "entra", "acao", "cor", "grafico", "valor", "valores", "rotulos", "quantos"],
    "additionalProperties": False}
SCHEMA_COMPOSICAO: dict[str, Any] = {
    "type": "object",
    "properties": {"cenas": {"type": "array", "items": {"type": "object", "properties": {
        "indice": {"type": "number"}, "camadas": {"type": "array", "items": _CAMADA_SCHEMA}},
        "required": ["indice", "camadas"], "additionalProperties": False}}},
    "required": ["cenas"], "additionalProperties": False,
}


def _fala_com_tempos(pals: list[dict], limite: int = 9000) -> str:
    return " ".join(f"[{w['inicio']:.1f}]{w['texto'].strip()}" for w in pals)[:limite]


def prompt_analise(pals: list[dict], dur: float, titulo: str, extra: str = "", forma: str = "um desenho animado") -> str:
    return (
        f"Analise este corte de vídeo curto para {forma} que vai ilustrar o que a pessoa fala.\n"
        f"Duração: {dur:.1f} s. Título: “{titulo}”.\n"
        "Em 'tema', o assunto em até 6 palavras. Em 'ideias', cada ideia que dá para desenhar, na ordem em que é dita: "
        f"'tipo' ({', '.join(TIPOS_IDEIA)}), 'resumo' (uma frase), 'dado' (o número ou valor dito, se houver; vazio se não) e "
        "'ancora' (4 a 8 palavras COPIADAS da fala, onde a ideia aparece). Só o que foi dito.\n"
        + (f"{extra[:3000]}\n" if extra else "")
        + f"Fala com tempos: {_fala_com_tempos(pals)}"
    )


def prompt_roteiro(analise: dict, pals: list[dict], dur: float, ficha: str) -> str:
    return (
        "Escreva o roteiro de um desenho animado curto, em traço simples, que fica em cima do vídeo e ilustra o que a pessoa diz "
        "(estilo explicativo: objetos e bonequinhos do que é falado, dados grandes, check e X, balanças, gráficos simples).\n"
        f"Clip de {dur:.1f} s, ficha visual '{ficha}'. {DICAS_FICHA.get(ficha, '')}\n"
        f"Análise: {json.dumps(analise, ensure_ascii=False)[:3500]}\n"
        "Uma cena a cada 2 a 5 s, cobrindo o clip inteiro sem buracos grandes. Para cada cena: 'ancora' (4 a 8 palavras COPIADAS "
        "da fala, onde a cena começa), 'ate' (o trecho onde ela termina, ou vazio), 'etiqueta' (o tema da cena em até 4 palavras, "
        "caixa alta), 'descricao' (o que aparece e o que acontece, em uma ou duas frases concretas: objetos, pessoas, setas, "
        "o que muda quando ele fala), 'dado' (o número dito a destacar, ou vazio) e 'balao' (uma frase curta de alguém citado, "
        "ou vazio). Nada que não foi dito.\n"
        f"Fala com tempos: {_fala_com_tempos(pals, 6000)}"
    )


LAYOUTS_CENAS = {
    "em-cima": "as cenas ocupam a parte de cima da tela e a pessoa fica embaixo",
    "fundo": "as cenas ficam atrás da pessoa recortada, na parte de cima da tela",
    "sobreposto": "as cenas são cartões por cima do vídeo, que continua aparecendo",
    "janela": "a animação ocupa a tela e a pessoa fica numa janela no canto",
}


def prompt_roteiro_cenas(analise: dict, pals: list[dict], dur: float, layout: str, ficha: str) -> str:
    return (
        "Escreva o roteiro da animação de um clip curto: telas animadas (números, citações, listas, comparações, linha do tempo, "
        "mapa, nomes e palavras fortes) que acompanham e explicam o que a pessoa diz, ligadas ao contexto do assunto.\n"
        f"Clip de {dur:.1f} s, ficha visual '{ficha}': {LAYOUTS_CENAS.get(layout, LAYOUTS_CENAS['em-cima'])}.\n"
        f"Análise: {json.dumps(analise, ensure_ascii=False)[:3500]}\n"
        "Uma cena a cada 3 a 6 s, cobrindo o clip inteiro sem buracos grandes, e cada cena mostra uma ideia nova do trecho. "
        "Para cada cena: 'ancora' (4 a 8 palavras COPIADAS da fala, onde a cena começa), 'ate' (o trecho onde ela termina, ou "
        "vazio), 'etiqueta' (o tema da cena em até 4 palavras, caixa alta), 'descricao' (o que aparece na tela e por que, em uma "
        "ou duas frases concretas), 'dado' (o número dito a destacar, ou vazio) e 'balao' (a frase de alguém citado, ou vazio). "
        "Nada que não foi dito.\n"
        f"Fala com tempos: {_fala_com_tempos(pals, 6000)}"
    )


def direcao_para_cenas(analise: dict | None, roteiro: list[dict]) -> str:
    """A pré-produção como texto para a terceira etapa dos estilos de cenas (direcao.prompt_cenas)."""
    cenas = [{"ancora": c.get("ancora", ""), "duracao": round(c["fim"] - c["inicio"], 1), "etiqueta": c.get("etiqueta", ""),
              "descricao": c.get("descricao", ""), "dado": c.get("dado", ""), "citacao": c.get("balao", "")} for c in roteiro]
    return (f"Tema do trecho: {(analise or {}).get('tema') or '—'}.\n"
            f"Roteiro da animação: {json.dumps(cenas, ensure_ascii=False)[:6000]}")


def prompt_composicao(roteiro: list[dict], ficha: str) -> str:
    pecas = ", ".join(f"{k} ({v[0]})" for k, v in PECAS.items())
    cenas = json.dumps([{"indice": k, "duracao": round(c["fim"] - c["inicio"], 1), "etiqueta": c.get("etiqueta", ""),
                         "descricao": c.get("descricao", ""), "dado": c.get("dado", ""), "balao": c.get("balao", "")}
                        for k, c in enumerate(roteiro)], ensure_ascii=False)
    return (
        f"Componha cada cena deste roteiro de desenho animado num palco de {PALCO[0]} (largura) por {PALCO[1]} (altura), origem "
        f"em cima à esquerda. {DICAS_FICHA.get(ficha, '')} Ficha '{ficha}'. Use só estas peças: {pecas}.\n"
        "Cada cena tem de 2 a 8 camadas: 'tipo' peca (uma peça com 'rotulo' curto embaixo, opcional), multidao (a peça repetida "
        "'quantos' vezes, para estatística e grupos), texto (palavra ou frase curta em 'rotulo'), balao (frase em 'rotulo') ou "
        "dado ('grafico' numero, grade (quadradinhos, 'valor' em %), barras ('valores' e 'rotulos') ou linha, e 'valor' o "
        "número). 'x','y' = centro da camada no palco; 'escala' 0.5 a 2.5 (1 = 170 unidades); 'entra' = segundos depois do "
        f"começo da cena (a cena se monta aos poucos, no ritmo da fala); 'acao' ({', '.join(ACOES)}); 'cor' "
        f"({', '.join(COR_CAMADA)}: bom = verde, ruim = vermelho, destaque = dourado). Deixe o topo (y < 90) livre para a "
        "etiqueta. Composição limpa, poucas coisas grandes, nada sobreposto. Campos que não se aplicam: vazios, 0 ou [].\n"
        f"Cenas: {cenas}"
    )


def _ancorar_cenas(roteiro: Any, pals: list[dict], dur: float) -> list[dict]:
    """Prende cada cena do roteiro à fala (âncora e "até") e acerta os tempos para não haver buracos nem sobras."""
    from .direcao import ancorar

    cenas = (roteiro or {}).get("cenas") if isinstance(roteiro, dict) else None
    if not isinstance(cenas, list):
        return []
    out, desde = [], 0
    for c in cenas:
        if not isinstance(c, dict):
            continue
        achou = ancorar(str(c.get("ancora") or ""), pals, desde)
        if achou is None:
            continue
        i, j, _ = achou
        desde = i
        ini = max(0.0, pals[i]["inicio"] - 0.15)
        fim = None
        if c.get("ate"):
            a2 = ancorar(str(c["ate"]), pals, i)
            if a2 is not None:
                fim = pals[a2[1]]["fim"] + 0.2
        out.append({"inicio": round(ini, 2), "fim": round(fim, 2) if fim else None, "ancora": " ".join(w["texto"] for w in pals[i:j + 1]),
                    "etiqueta": _txt(c.get("etiqueta"), 40).upper(), "descricao": _txt(c.get("descricao"), 240),
                    "dado": _txt(c.get("dado"), 16), "balao": _txt(c.get("balao"), 90)})
    out.sort(key=lambda c: c["inicio"])
    # cada cena vai até a próxima (máximo 6 s); a primeira começa no início do clip
    for k, c in enumerate(out):
        prox = out[k + 1]["inicio"] if k + 1 < len(out) else dur
        fim = c["fim"] if c["fim"] and c["fim"] <= prox else prox
        c["fim"] = round(min(fim, c["inicio"] + 6.0, dur), 2)
    if out:
        out[0]["inicio"] = 0.0
    return [c for c in out if c["fim"] - c["inicio"] >= 1.0]


def _composicao(resp: Any, roteiro: list[dict]) -> list[list[dict]]:
    camadas: list[list[dict]] = [[] for _ in roteiro]
    for c in (resp or {}).get("cenas") or [] if isinstance(resp, dict) else []:
        if not isinstance(c, dict):
            continue
        k = int(_num(c.get("indice"), -1, -1, 999))
        if 0 <= k < len(roteiro):
            dur = roteiro[k]["fim"] - roteiro[k]["inicio"]
            cs = [x for x in (normalizar_camada(x) for x in (c.get("camadas") or [])[:16]) if x]
            for x in cs:
                x["entra"] = min(x["entra"], max(0.0, dur - 0.6))
            camadas[k] = cs
    return camadas


def composicao_padrao(cena: dict) -> list[dict]:
    """Quando a IA não compôs uma cena: o dado grande, o balão e uma peça que combine com a descrição."""
    out: list[dict] = []
    desc = (cena.get("descricao", "") + " " + cena.get("etiqueta", "")).lower()
    peca = next((p for p, (d, _) in PECAS.items() if any(w and w in desc for w in [p.replace("_", " ")] + d.split(", ")[:1])), "boneco")
    if cena.get("dado"):
        out.append({"tipo": "dado", "grafico": "numero", "valor": cena["dado"], "x": 500, "y": 460, "escala": 1.4, "entra": 0.2,
                    "acao": "pop", "cor": "primaria"})
    else:
        out.append({"tipo": "peca", "peca": peca, "x": 500, "y": 500, "escala": 1.8, "entra": 0.1, "acao": "desenha", "cor": "texto"})
    if cena.get("balao"):
        out.append({"tipo": "balao", "rotulo": cena["balao"], "x": 640, "y": 220, "escala": 1.0, "entra": 0.8, "acao": "pop", "cor": "texto"})
    return [x for x in (normalizar_camada(c) for c in out) if x]


def _descricao_estilo(est: Any, modo: str, ficha_nome: str) -> str:
    """O que o estilo sabe desenhar, para a direção de vídeo escrever um filme que ele consegue mostrar."""
    from .artes import cortes as _cortes

    if modo == "desenho":
        pecas = ", ".join(PECAS)
        return (f"{est.nome}: desenho animado em traço simples sobre o vídeo (explicador com bonequinhos, objetos, dados grandes, "
                f"check e X, balanças, gráficos simples). Ficha '{ficha_nome}'. {DICAS_FICHA.get(ficha_nome, '')} "
                f"Peças que existem: {pecas}. Personagens viram bonecos de traço; a posição vale no palco.")
    if modo == "arte":
        from . import artes

        slug = est.direcao.arte or ""
        curta = (" Curta animado em three.js: cenário 3D, personagens com poses e câmera de cinema."
                 if slug in _cortes.ACOES else "")
        return (f"{est.nome} ({artes.especificacao(slug)['nome']}), {LAYOUTS_CENAS.get(est.direcao.layout, LAYOUTS_CENAS['em-cima'])}."
                f"{curta}\n{artes.texto_runtime(slug)}")
    return (f"{est.nome}: telas animadas (números, citações, listas, comparações, linha do tempo, mapa, nomes) ligadas ao contexto; "
            f"{LAYOUTS_CENAS.get(est.direcao.layout, LAYOUTS_CENAS['em-cima'])}. Ficha '{ficha_nome}'. Quando o assunto não tem "
            "personagens, o elenco pode ficar vazio e os planos descrevem o que a tela mostra.")


def _pesquisar(pals: list[dict], pasta: Path, cancelar: Any, passo: Any) -> dict[str, Any]:
    from .artes import pesquisa

    termos = pesquisa.termos(pals) if pesquisa.ligada() else []
    if not termos:
        return {}
    passo(f"pesquisa de referências (Wikipédia e Wikimedia Commons): {', '.join(termos)}")
    refs, avisos = pesquisa.pesquisar(termos, pasta / "pesquisa", cancelar=cancelar)
    for a in avisos:
        passo(a)
    if refs:
        passo(f"referências lidas: {', '.join(refs)}")
    return refs


def _gerar_curta(projeto: Any, clip: Any, tl: Any, pals: list[dict], est: Any, ad: Any, analise: dict, extra: str, cache: Any,
                 cancelar: Any, ctx: Any, passo: Any, pasta: Path, nome: str, chamar: Any, dv: dict | None = None) -> dict[str, Any]:
    """Estilos que viram curta: a direção de vídeo já conferida, a pesquisa, e a IA fecha o roteiro do curta seguindo a direção."""
    from . import direcao_video
    from . import artes
    from .artes import curta, pesquisa

    slug = est.direcao.arte or ""
    refs = _pesquisar(pals, pasta, cancelar, passo)
    passo("etapa 3 de 3: roteiro do curta (efeitos, objetos e montagem) seguindo a direção")
    extra_dv = (direcao_video.texto(dv) + "\nPlanos da direção (mantenha as mesmas âncoras, cenários, elenco, posições e câmera): "
                + json.dumps(direcao_video.roteiro(dv), ensure_ascii=False)[:9000]) if dv and dv.get("planos") else ""
    with ctx("escrevendo o roteiro do curta") as ev:
        r = chamar(ad, curta.prompt_roteiro(slug, pals, tl.duracao, clip.titulo, analise, extra_dv + ("\n\n" + extra if extra else ""),
                                            pesquisa.texto_para_ia(refs)), curta.schema_roteiro(), cache, cancelar, ev)
    planos, resumo = curta.de_roteiro(r, pals, tl.duracao)
    if resumo.get("metafora"):
        passo(f"metáfora: {resumo['metafora']}")
    if resumo.get("logline"):
        passo(f"história: {resumo['logline']}")
    cenas_arte = artes.cenas_do_curta(slug, planos, pals, artes.assinatura_timeline(tl), est.direcao.parametros)
    if refs:
        curta.aplicar_tons(cenas_arte, refs)
    reais: list[dict] = []
    if resumo.get("entidades") and pesquisa.ligada():  # foto, logo ou produto de verdade do que a fala cita pelo nome
        passo("imagens reais: " + ", ".join(f"{e['busca']} ({e['tipo']})" for e in resumo["entidades"]))
        reais, avs = pesquisa.imagens_reais(resumo["entidades"], pasta, cancelar=cancelar)
        for a in avs:
            passo(a)
        n = curta.ligar_referencias(cenas_arte, reais, pals)
        if reais:
            passo(f"{n} imagem(ns) real(is) no vídeo: " + ", ".join(f"{r['nome']} ({'logo' if r['logo'] else 'foto'})" for r in reais))
    passo(f"{len(cenas_arte)} plano(s) presos à fala")
    for c in cenas_arte[:14]:
        cu = c["params"]["curta"]
        passo(f"{c['inicio']:.1f} s · {cu['cenario']} · {cu['plano']}" + (f" · {cu['nota_visual']}" if cu.get("nota_visual") else ""))
    roteiro = [{"inicio": p["inicio"], "fim": p["fim"], "ancora": p["ancora"], "etiqueta": p["curta"]["cenario"].upper(),
                "descricao": p["descricao"], "dado": "", "balao": ""} for p in planos]
    doc = {"versao": 1, "criado": datetime.now().isoformat(timespec="seconds"), "estilo": clip.estilo, "modo": "arte",
           "ficha": est.direcao.ficha, "analise": analise or {}, "roteiro": roteiro, "modelo": nome, "arte": slug,
           "curta": resumo, "cenas": cenas_arte}
    if dv:
        doc["direcao_video"] = dv
    cores = (ler(pasta) or {}).get("cores")
    if cores:
        doc["cores"] = cores
    if refs or reais:
        doc["pesquisa"] = {"termos": list(refs), "creditos": pesquisa.creditos(refs)
                           + [{"termo": r["termo"], "nome": r["nome"], **r["credito"]} for r in reais]}
    if cenas_arte:
        _gravar(pasta, doc)
    return doc


def do_modo(doc: dict | None, modo: str) -> bool:
    """O documento tem um roteiro feito para este modo? (Documento antigo, sem "modo", é de desenho.)"""
    return bool(doc and doc.get("roteiro") and (doc.get("modo") or "desenho") == modo)


def gerar(projeto: Any, clip: Any, tl: Any, pals: list[dict], est: Any, ad: Any, relato: Any = None,
          cancelar: threading.Event | None = None, roteiro_editado: list[dict] | None = None,
          analise_pronta: dict | None = None, novo: bool = False) -> dict[str, Any]:
    """As três etapas (ou só a última, se o roteiro já veio editado). Grava direcao-arte.json e devolve o documento.

    Se a IA não montar a direção, o documento volta sem cenas e nada é gravado: quem chamou avisa (toda animação usa IA).
    """
    from .ai.adapter import CacheIA, chamar
    from . import direcao, direcao_video, skills

    _, pasta = projeto.clip(clip.id)
    cache = None if novo else CacheIA(projeto.analise_dir / "cache_ia")  # "refazer tudo" pede uma resposta nova
    modo = est.direcao.modo
    ficha_nome = est.direcao.ficha if modo != "desenho" or est.direcao.ficha in FICHAS_DESENHO else "quadro"
    nome = getattr(ad, "nome", "IA")
    ctx = (lambda tarefa: relato.ia(nome, tarefa)) if relato is not None else (lambda tarefa: nullcontext())
    passo = relato.passo if relato is not None else (lambda t: None)
    analise = analise_pronta
    from .artes import cortes as _cortes

    eh_curta = modo == "arte" and (est.direcao.arte or "") in _cortes.ACOES  # os estilos que viram curta têm roteiro próprio
    extra = skills.texto_para_ia(projeto.ws, "cenas", projeto.canal.slug, projeto.id,
                                 excluir={"cenas-da-fala"} if eh_curta else {"roteiro-do-curta"})
    try:  # a direção de arte que o estilo escolheu (`arte:`) guia a IA: tom, tipos de cena, ritmo e limites
        from .arte.guia import da_do_estilo, texto_para_ia

        arte_estilo = da_do_estilo(est, projeto.canal.path)[0]
        if arte_estilo is not None:
            extra = texto_para_ia(arte_estilo) + ("\n\n" + extra if extra else "")
    except Exception:  # noqa: BLE001 - DA com erro não impede a pré-produção
        pass
    dv: dict[str, Any] | None = None
    if roteiro_editado is None:
        passo(f"etapa 1 de 3: análise do corte ({len(pals)} palavras, {tl.duracao:.0f} s)")
        forma = "um desenho animado" if modo == "desenho" else "uma animação"
        with ctx("analisando o corte") as ev:
            r1 = chamar(ad, prompt_analise(pals, tl.duracao, clip.titulo, extra, forma), SCHEMA_ANALISE, cache, cancelar, ev)
        analise = {"tema": _txt((r1 or {}).get("tema"), 60), "ideias": [
            {k: _txt(i.get(k), 200) for k in ("ancora", "tipo", "resumo", "dado")} for i in ((r1 or {}).get("ideias") or [])[:20]
            if isinstance(i, dict)]}
        passo(f"tema: {analise['tema'] or '—'}; {len(analise['ideias'])} ideia(s) para ilustrar")
        # etapa 2: a direção de vídeo (história, elenco, cenários, posições, câmera), conferida e corrigida
        passo("etapa 2 de 3: direção de vídeo (história, elenco, cenários, posições e câmera)")
        dv = direcao_video.dirigir(ad, pals, tl.duracao, clip.titulo, analise, _descricao_estilo(est, modo, ficha_nome), chamar,
                                   cache, cancelar, ctx, passo, "2 a 5" if modo == "desenho" or eh_curta else "3 a 6", extra)
        if eh_curta:
            return _gerar_curta(projeto, clip, tl, pals, est, ad, analise, extra, cache, cancelar, ctx, passo, pasta, nome, chamar, dv)
        roteiro = direcao_video.roteiro(dv)
        passo(f"roteiro: {len(roteiro)} cena(s) da direção, presas à fala")
        for c in roteiro[:12]:
            passo(f"{c['inicio']:.1f}–{c['fim']:.1f} s · {c['etiqueta'] or '—'}: {c['descricao']}")
    else:
        roteiro = [dict(c) for c in roteiro_editado]
        passo(f"usando o roteiro editado ({len(roteiro)} cena(s))")
    base = {"versao": 1, "criado": datetime.now().isoformat(timespec="seconds"), "estilo": clip.estilo, "modo": modo,
            "ficha": ficha_nome, "analise": analise or {}, "roteiro": roteiro, "modelo": nome}
    if dv is None and roteiro_editado is not None:  # roteiro editado: a direção de antes continua valendo (história e elenco)
        dv = (ler(pasta) or {}).get("direcao_video")
    if dv:
        base["direcao_video"] = dv
        extra = direcao_video.texto(dv) + ("\n\n" + extra if extra else "")
    cores = (ler(pasta) or {}).get("cores")  # as cores ajustadas no painel continuam valendo
    if cores:
        base["cores"] = cores
    if modo == "arte":
        from . import artes

        slug = est.direcao.arte or ""
        if not roteiro:
            passo("a IA não montou o roteiro com a fala deste corte")
            return {**base, "cenas": []}
        refs: dict[str, Any] = {}
        extra3 = extra
        if eh_curta:  # roteiro editado à mão: a etapa 3 de sempre, com a pesquisa de referências
            from .artes import pesquisa

            refs = _pesquisar(pals, pasta, cancelar, passo)
            texto_refs = pesquisa.texto_para_ia(refs)
            extra3 = texto_refs + ("\n\n" + extra if extra else "") if texto_refs else extra
        passo(f"etapa 3 de 3: conteúdo das cenas de {artes.especificacao(slug)['nome']}")
        with ctx("montando as cenas") as ev:
            r3 = chamar(ad, artes.prompt_arte(slug, roteiro, extra3, " ".join(w["texto"] for w in pals)), artes.schema_arte(slug), cache, cancelar, ev)
        cenas_arte = artes.de_resposta_ia(slug, r3, roteiro, pals, artes.assinatura_timeline(tl), est.direcao.parametros)
        passo(f"{len(cenas_arte)} de {len(roteiro)} cena(s) conferidas com a fala")
        if refs:
            from .artes import curta, pesquisa

            curta.aplicar_tons(cenas_arte, refs)
        for c in cenas_arte[:12]:
            cu = c["params"].get("curta")
            if cu:
                passo(f"{c['inicio']:.1f} s · {cu['cenario']} · {cu['plano']} · {cu['situacao']}" + (f" · {cu['nota_visual']}" if cu.get("nota_visual") else ""))
        doc = {**base, "arte": slug, "cenas": cenas_arte}
        if refs:
            doc["pesquisa"] = {"termos": list(refs), "creditos": pesquisa.creditos(refs)}
        _gravar(pasta, doc)
        return doc
    if modo != "desenho":
        if not roteiro:
            passo("a IA não montou o roteiro com a fala deste corte")
            return {**base, "cenas": []}
        canal_md = ""
        try:
            canal_md = projeto.canal.info()[1]
        except Exception:  # noqa: BLE001
            pass
        passo("etapa 3 de 3: composição das cenas")
        p3 = direcao.prompt_cenas(pals, tl.duracao, clip.titulo, canal_md, len(roteiro), extra, direcao_para_cenas(analise, roteiro))
        with ctx("montando as cenas") as ev:
            r3 = chamar(ad, p3, direcao.SCHEMA_CENAS, cache, cancelar, ev)
        cenas = direcao.de_resposta_ia(r3, pals, tl.duracao, roteiro)
        passo(f"composição: {len(cenas)} de {len(roteiro)} cena(s) do roteiro conferidas com a fala")
        doc = {**base, "cenas": [c.model_dump(include={"inicio", "fim", "params", "motivo"}) for c in cenas]}
        _gravar(pasta, doc)
        return doc
    if not roteiro:
        raise ValueError("A IA não conseguiu montar o roteiro do desenho com a fala deste corte.")
    passo("etapa 3 de 3: composição das cenas")
    with ctx("desenhando as cenas") as ev:
        r3 = chamar(ad, prompt_composicao(roteiro, ficha_nome), SCHEMA_COMPOSICAO, cache, cancelar, ev)
    camadas = _composicao(r3, roteiro)
    vazias = sum(1 for c in camadas if not c)
    for k, c in enumerate(camadas):
        if not c:
            camadas[k] = composicao_padrao(roteiro[k])
    passo(f"composição: {len(roteiro) - vazias} cena(s) da IA" + (f", {vazias} com a composição padrão" if vazias else ""))
    doc = {**base, "camadas": camadas}
    _gravar(pasta, doc)
    return doc


def para_itens(doc: dict) -> list[dict]:
    """As cenas do documento como itens do edicao.json (tipo "cena"; no desenho, cena "desenho")."""
    if doc.get("modo") in ("cenas", "arte"):
        return [{"tipo": "cena", "inicio": c["inicio"], "fim": c["fim"], "origem": "ia", "motivo": c.get("motivo", "")[:200],
                 "params": c["params"]} for c in doc.get("cenas") or []]
    out = []
    tema = ((doc.get("analise") or {}).get("tema") or "").upper()
    for c, camadas in zip(doc.get("roteiro", []), doc.get("camadas", [])):
        out.append({"tipo": "cena", "inicio": c["inicio"], "fim": c["fim"], "origem": "ia", "motivo": c.get("descricao", "")[:200],
                    "params": normalizar_desenho({"etiqueta": c.get("etiqueta"), "ancora": c.get("ancora"), "cabecalho": tema,
                                                  "descricao": c.get("descricao"), "camadas": camadas})})
    return out


def ler(pasta_clip: Path) -> dict | None:
    p = pasta_clip / ARQUIVO
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


# ---- o desenho em SVG/HTML --------------------------------------------------------------------------------------
def simbolos(biblioteca: str = "traco") -> str:
    """As peças como <symbol> (vão uma vez no documento): o traço daqui ou as facetadas da maquete."""
    if biblioteca == "maquete":
        from .maquete import PECAS_MAQUETE

        return "".join(f'<symbol id="peca-{k}" viewBox="12 10 76 76" overflow="visible">{v}</symbol>' for k, v in PECAS_MAQUETE.items())
    return "".join(f'<symbol id="peca-{k}" viewBox="0 0 100 100">{v[1]}</symbol>' for k, v in PECAS.items())


def cenario(nome: str) -> str:
    """O fundo fixo do palco (desenhado aqui): cidade em silhueta, cidade neon, folha de caderno ou poeira desfocada."""
    if nome == "poeira":  # partículas de luz desfocadas, em três profundidades, que derivam devagar
        bolas = []
        for i in range(34):
            x, y = (i * 263 + 71) % 1000, (i * 151 + 37) % 860
            camada = i % 3
            r = (3, 7, 14)[camada]
            cor = "var(--destaque)" if i % 9 == 4 else "var(--texto)"
            bolas.append(f'<circle class="po po{camada}" cx="{x}" cy="{y}" r="{r}" fill="{cor}" opacity="{(.5, .28, .16)[camada]}"/>')
        return (f'<rect width="1000" height="860" fill="url(#luz-maquete)"/>'
                f'<g filter="url(#desfoque)">{"".join(bolas)}</g>')
    if nome == "caderno":
        linhas = "".join(f'<path d="M0 {y}H1000"/>' for y in range(60, 560, 34))
        predios = "M0 560V430h60v-60h50v90h40v-130h70v130h50v-80h60v80h40v-150h80v150h50v-90h60v90h60v-60h70v60h60v-120h70v120h50v-70h80v70"
        return (f'<g class="cenario" stroke="var(--suave)" stroke-width="1.2" fill="none" opacity=".45">{linhas}</g>'
                f'<path class="cenario" d="{predios}" fill="none" stroke="var(--suave)" stroke-width="2" opacity=".5"/>')
    janelas = "".join(f'<rect x="{x}" y="{y}" width="6" height="8"/>' for x in range(30, 1000, 46) for y in (420, 450, 480, 510)
                      if (x * 7 + y) % 5 < 2)
    predios = ("M0 560V400h70v-50h60v80h40v-120h80v120h50v-70h70v70h40v-140h90v140h50v-80h60v80h70v-50h80v50h60v-110h70v110"
               "h60v-60h60v60h40v-90h60V560z")
    brilho = 'filter="url(#brilho)"' if nome == "cidade-neon" else ""
    traco = 'stroke="var(--primaria)" stroke-width="2"' if nome == "cidade-neon" else 'stroke="none"'
    return (f'<path class="cenario" d="{predios}" fill="var(--superficie)" {traco} {brilho} opacity=".95"/>'
            f'<g class="cenario" fill="var(--destaque)" opacity=".35">{janelas}</g>')


def _cor(c: str) -> str:
    return {"texto": "var(--texto)", "primaria": "var(--primaria)", "destaque": "var(--destaque)", "bom": "var(--bom)",
            "ruim": "var(--ruim)", "suave": "var(--suave)"}.get(c, "var(--texto)")


def _camada_svg(c: dict, k: int) -> str:
    x, y, e, cor = c["x"], c["y"], c["escala"], _cor(c["cor"])
    atraso = f"animation-delay:{c['entra']:.2f}s"
    classe = f"camada acao-{c['acao']}"
    rot = html.escape(c.get("rotulo", ""))
    if c["tipo"] == "peca":
        lado = 170 * e
        corpo = (f'<use class="peca-use" href="#peca-{c["peca"]}" x="{-lado / 2:.0f}" y="{-lado / 2:.0f}" width="{lado:.0f}" '
                 f'height="{lado:.0f}"/>')
        if rot:
            corpo += f'<text class="rotulo rotulo-simples" y="{lado / 2 + 36:.0f}">{rot}</text>'
            # maquete: cartão escuro preso à peça por um fio (o CSS da ficha escolhe qual aparece)
            ax, ay = lado * 0.18, -lado * 0.22
            bx, by = lado * 0.48 + 40, -lado * 0.5 - 20
            larg = max(120, len(rot) * 16 + 44)
            corpo += (f'<g class="cartao-rot" style="animation-delay:{c["entra"] + 0.45:.2f}s"><circle cx="{ax:.0f}" cy="{ay:.0f}" r="5"/>'
                      f'<path class="fio" d="M{ax:.0f} {ay:.0f}L{bx:.0f} {by:.0f}h12"/>'
                      f'<rect x="{bx + 12:.0f}" y="{by - 24:.0f}" width="{larg:.0f}" height="48" rx="10"/>'
                      f'<circle class="ponto" cx="{bx + 32:.0f}" cy="{by:.0f}" r="6"/>'
                      f'<text x="{bx + 46:.0f}" y="{by + 1:.0f}">{rot}</text></g>')
    elif c["tipo"] == "multidao":
        n = c.get("quantos", 12)
        por_linha = min(n, 10)
        lado = 64 * e
        corpo = "".join(f'<use href="#peca-{c["peca"]}" x="{(i % por_linha - por_linha / 2) * lado * 0.9:.0f}" '
                        f'y="{(i // por_linha) * lado * 0.95 - lado / 2:.0f}" width="{lado:.0f}" height="{lado:.0f}" '
                        f'class="pop-item peca-use" style="animation-delay:{c["entra"] + i * 0.04:.2f}s"/>' for i in range(n))
        if rot:
            corpo += f'<text class="rotulo" y="{(n // por_linha + 1) * lado + 10:.0f}">{rot}</text>'
    elif c["tipo"] == "texto":
        fs = 64 * e
        larg = max(160, len(rot) * fs * 0.62 + 50)
        corpo = (f'<rect class="carimbo" x="{-larg / 2:.0f}" y="{-fs * 0.85:.0f}" width="{larg:.0f}" height="{fs * 1.6:.0f}" rx="8"/>'
                 f'<text class="texto-grande" style="font-size:{fs:.0f}px">{rot}</text>')
    elif c["tipo"] == "balao":
        largura = max(240, min(820, len(rot) * 21 * e))
        corpo = (f'<g class="balao-fala"><path d="M{-largura / 2:.0f} -58h{largura:.0f}v100H{-largura / 2 + 90:.0f}l-34 34v-34'
                 f'H{-largura / 2:.0f}z"/><text y="-8" style="font-size:{36 * e:.0f}px">{rot}</text></g>')
    else:  # dado
        g = c.get("grafico", "numero")
        valor = html.escape(c.get("valor", ""))
        if g == "grade":
            pct = int(_num(re.sub(r"[^\d.]", "", c.get("valor", "")) or 0, 0, 0, 100))
            lado = 30 * e
            quad = "".join(f'<rect x="{(i % 10 - 5) * lado * 1.15:.0f}" y="{(i // 10 - 5) * lado * 1.15:.0f}" width="{lado:.0f}" '
                           f'height="{lado:.0f}" rx="3" class="{"cheio" if i < pct else "vazio"} pop-item" '
                           f'style="animation-delay:{c["entra"] + i * 0.012:.2f}s"/>' for i in range(100))
            corpo = (f'<g class="grade">{quad}</g><text class="valor-grande" y="{-lado * 7.6:.0f}" '
                     f'style="font-size:{90 * e:.0f}px">{valor}</text>')
        elif g in ("barras", "linha"):
            vals = c.get("valores") or []
            if not vals:
                vals = [1, 2, 3]
            mx = max(vals) or 1
            w, h = 520 * e, 320 * e
            if g == "barras":
                lb = w / len(vals)
                corpo = "".join(
                    f'<rect x="{-w / 2 + i * lb + lb * 0.15:.0f}" y="{h / 2 - h * v / mx:.0f}" width="{lb * 0.7:.0f}" '
                    f'height="{h * v / mx:.0f}" class="barra" style="animation-delay:{c["entra"] + i * 0.15:.2f}s"/>'
                    + (f'<text class="rotulo" x="{-w / 2 + i * lb + lb / 2:.0f}" y="{h / 2 + 30:.0f}">'
                       f'{html.escape((c.get("rotulos") or [""] * 6)[i] if i < len(c.get("rotulos") or []) else "")}</text>')
                    for i, v in enumerate(vals))
            else:
                pts = " ".join(f"{-w / 2 + i * w / max(1, len(vals) - 1):.0f},{h / 2 - h * v / mx:.0f}" for i, v in enumerate(vals))
                corpo = (f'<path d="M{-w / 2:.0f} {h / 2:.0f}H{w / 2:.0f}M{-w / 2:.0f} {h / 2:.0f}V{-h / 2:.0f}" class="eixo"/>'
                         f'<polyline points="{pts}" class="linha-dado" pathLength="1"/>')
            if valor:
                corpo += f'<text class="valor-grande" y="{-h / 2 - 20:.0f}" style="font-size:{80 * e:.0f}px">{valor}</text>'
        else:  # o número grande (texto de SVG não conta; ele entra com a ação da camada)
            fs = 150 * e
            larg = max(220, len(valor) * fs * 0.6 + 70)
            corpo = (f'<rect class="painel-dado" x="{-larg / 2:.0f}" y="{-fs * 0.8:.0f}" width="{larg:.0f}" height="{fs * 1.6:.0f}" rx="18"/>'
                     f'<text class="valor-grande" style="font-size:{fs:.0f}px">{valor}</text>')
    # data-k/x/y: a maquete 3D (maquete3d.py) reposiciona a camada quando a câmera passeia
    return (f'<g transform="translate({x} {y})" data-k="{k}" data-x="{x}" data-y="{y}" style="color:{cor}">'
            f'<g class="{classe}" style="{atraso}">{corpo}</g></g>')


def cena_html(p: dict) -> str:
    """O conteúdo de uma cena "desenho" para a camada de cenas (direcao.compor_camada)."""
    etiqueta = f'<div class="etiqueta-tema"><span class="ponto"></span>{html.escape(p.get("etiqueta", ""))}</div>' if p.get("etiqueta") else ""
    if p.get("cabecalho"):
        etiqueta = f'<div class="cabecalho-tema">PASSO A PASSO · {html.escape(p["cabecalho"])}</div>' + etiqueta
    camadas = "".join(_camada_svg(c, k) for k, c in enumerate(p.get("camadas") or []))
    return f'{etiqueta}<svg class="palco" viewBox="0 0 {PALCO[0]} {PALCO[1]}" preserveAspectRatio="xMidYMid meet">{camadas}</svg>'


def fundo_html(nome_cenario: str, biblioteca: str = "traco") -> str:
    """O palco fixo (cenário) atrás das cenas, com as peças em <defs>."""
    defs = ('<defs><filter id="brilho" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/>'
            '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
            '<filter id="desfoque" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>'
            '<radialGradient id="luz-maquete" cx="50%" cy="45%" r="70%"><stop offset="0" stop-color="var(--superficie)"/>'
            f'<stop offset="1" stop-color="var(--fundo)"/></radialGradient>{simbolos(biblioteca)}</defs>')
    return (f'<svg class="palco-fixo" viewBox="0 0 {PALCO[0]} {PALCO[1]}" preserveAspectRatio="xMidYMax slice">{defs}'
            f'{cenario(nome_cenario)}</svg>')


CSS_DESENHO = """
.fundo-da.com-desenho .malha { display: none; }
.cartao-rot, .carimbo, .painel-dado, .cabecalho-tema, .etiqueta-tema .ponto { display: none; }
.palco-fixo { position: absolute; left: 0; right: 0; top: var(--topo); height: var(--alt); width: 100%; }
.cena.desenho { background: none !important; padding: 0; left: 0; right: 0; gap: 0; justify-content: flex-start; }
.cena.desenho .palco { width: 100%; height: 100%; overflow: visible; }
.etiqueta-tema { position: absolute; top: calc(var(--u) * 18); left: 0; right: 0; margin: 0 auto; width: max-content; z-index: 2;
  background: var(--destaque); color: var(--fundo); font-family: var(--f-titulo); font-size: calc(var(--u) * 30); letter-spacing: .04em;
  padding: calc(var(--u) * 6) calc(var(--u) * 20); border-radius: calc(var(--u) * 8); text-transform: uppercase; white-space: nowrap;
  animation: d-pop .35s cubic-bezier(.2, 1.4, .4, 1) both; }
.palco text { fill: currentColor; font-family: var(--f-corpo); text-anchor: middle; dominant-baseline: middle; }
.palco .rotulo { font-size: 30px; fill: var(--texto); letter-spacing: .06em; text-transform: uppercase; }
.palco .texto-grande { font-family: var(--f-titulo); text-transform: uppercase; }
.palco .valor-grande { font-family: var(--f-titulo); }
.palco .balao-fala path { fill: var(--superficie); stroke: var(--texto); stroke-width: 3; }
.palco .balao-fala text { fill: var(--texto); }
.palco .grade rect.cheio { fill: var(--bom); } .palco .grade rect.vazio { fill: none; stroke: var(--suave); stroke-width: 2; }
.palco .barra { fill: currentColor; transform-box: fill-box; transform-origin: bottom; animation: cresce-barra .6s cubic-bezier(.2, .9, .2, 1) both; }
.palco .eixo { stroke: var(--suave); stroke-width: 3; fill: none; }
.palco .linha-dado { fill: none; stroke: currentColor; stroke-width: 7; stroke-linecap: round; stroke-dasharray: 1; stroke-dashoffset: 1;
  animation: traca 1.2s ease-out .2s forwards; }
.camada { transform-box: fill-box; transform-origin: center; animation-duration: .5s; animation-fill-mode: both; animation-timing-function: cubic-bezier(.2, 1.3, .4, 1); }
.acao-pop { animation-name: d-pop; } .acao-desenha { animation-name: d-desenha; animation-duration: .8s; animation-timing-function: ease-out; }
.acao-desliza { animation-name: d-desliza; } .acao-cai { animation-name: d-cai; } .acao-cresce { animation-name: d-cresce; }
.acao-pulsa { animation-name: d-pop, d-pulsa; animation-duration: .5s, 1.4s; animation-iteration-count: 1, infinite; }
.acao-treme { animation-name: d-pop, d-treme; animation-duration: .4s, .5s; animation-iteration-count: 1, 3; }
.acao-nenhuma { animation: none; }
.pop-item { transform-box: fill-box; transform-origin: center; animation: d-pop .3s cubic-bezier(.2, 1.4, .4, 1) both; }
@keyframes d-pop { from { opacity: 0; transform: scale(.3); } to { opacity: 1; transform: none; } }
@keyframes d-desenha { from { opacity: 0; clip-path: inset(0 100% 0 0); } to { opacity: 1; clip-path: inset(0 0 0 0); } }
@keyframes d-desliza { from { opacity: 0; transform: translateX(-60px); } to { opacity: 1; transform: none; } }
@keyframes d-cai { from { opacity: 0; transform: translateY(-90px); } to { opacity: 1; transform: none; } }
@keyframes d-cresce { from { opacity: 0; transform: scaleY(0); } to { opacity: 1; transform: none; } }
@keyframes d-pulsa { 50% { transform: scale(1.08); } }
@keyframes d-treme { 25% { transform: rotate(-4deg); } 75% { transform: rotate(4deg); } }
@keyframes cresce-barra { from { transform: scaleY(0); } to { transform: none; } }
@keyframes traca { to { stroke-dashoffset: 0; } }
"""

# cenas fixas das amostras do passo 3 (a fala de exemplo da amostra; no app elas vêm da IA)
CENAS_EXEMPLO = [
    (0.0, 1.9, {"etiqueta": "O SEU CORTE", "camadas": [
        {"tipo": "peca", "peca": "celular", "x": 330, "y": 500, "escala": 1.9, "entra": 0.1, "acao": "desenha", "cor": "texto"},
        {"tipo": "balao", "rotulo": "Olha só como fica!", "x": 660, "y": 280, "escala": 1.0, "entra": 0.6, "acao": "pop", "cor": "texto"}]}),
    (1.9, 3.8, {"etiqueta": "A REGRA", "camadas": [
        {"tipo": "dado", "grafico": "grade", "valor": "87%", "x": 500, "y": 520, "escala": 1.0, "entra": 0.1, "acao": "nenhuma", "cor": "bom"}]}),
    (3.8, 5.6, {"etiqueta": "UM CASO SÓ", "camadas": [
        {"tipo": "peca", "peca": "balanca", "x": 500, "y": 520, "escala": 2.2, "entra": 0.0, "acao": "pop", "cor": "destaque"},
        {"tipo": "peca", "peca": "check", "x": 800, "y": 300, "escala": 1.1, "entra": 0.7, "acao": "pop", "cor": "bom"},
        {"tipo": "peca", "peca": "x", "x": 200, "y": 300, "escala": 1.1, "entra": 1.0, "acao": "treme", "cor": "ruim"}]}),
]


# ---- a direção de arte do clip: ver, ajustar e refazer ------------------------------------------------------
CORES_EDITAVEIS = ("fundo", "superficie", "texto", "texto_suave", "primaria", "destaque", "bom", "ruim")


def cores_limpas(cores: Any) -> dict[str, str]:
    if not isinstance(cores, dict):
        return {}
    return {k: v.upper() for k, v in cores.items() if k in CORES_EDITAVEIS and isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)}


def roteiro_limpo(roteiro: Any, dur: float) -> list[dict]:
    """O roteiro que veio da tela (o usuário editou): tempos dentro do clip, em ordem e sem sobreposição."""
    out = []
    for c in roteiro if isinstance(roteiro, list) else []:
        if not isinstance(c, dict):
            continue
        ini = _num(c.get("inicio"), 0, 0, dur)
        fim = _num(c.get("fim"), ini + 3, 0, dur)
        if fim - ini < 0.5:
            continue
        out.append({"inicio": round(ini, 2), "fim": round(fim, 2), "ancora": _txt(c.get("ancora"), 140),
                    "etiqueta": _txt(c.get("etiqueta"), 40).upper(), "descricao": _txt(c.get("descricao"), 240),
                    "dado": _txt(c.get("dado"), 16), "balao": _txt(c.get("balao"), 90)})
    out.sort(key=lambda c: c["inicio"])
    for a, b in zip(out, out[1:]):
        a["fim"] = min(a["fim"], b["inicio"])
    return [c for c in out[:30] if c["fim"] - c["inicio"] >= 0.5]


def _gravar(pasta: Path, doc: dict) -> None:
    (pasta / ARQUIVO).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def refazer(projeto: Any, clip_id: str, roteiro: Any = None, cores: Any = None, tudo: bool = False, ad: Any = None,
            relato: Any = None, cancelar: threading.Event | None = None) -> dict[str, Any]:
    """"Refazer com esta direção": o desenho (ou as cenas) do clip de novo, numa versão nova da edição.

    Com o roteiro editado só a composição roda de novo; `tudo` refaz as três etapas. Nos estilos de cenas, se a IA
    não montar nenhuma cena, as cenas saem e o próximo render pede a direção de novo à IA.
    """
    from . import edicao, melhorar
    from .timeline import Timeline

    ad = ad or melhorar.ia_do_workspace(projeto.ws)
    if ad is None:
        raise melhorar.SemIA(melhorar.MSG_SEM_IA)
    clip, pasta = projeto.clip(clip_id)
    est = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)[0]
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    melhorar.garantir_inicial(projeto, clip_id)
    doc_ed = edicao.carregar(pasta)
    anterior = ler(pasta)
    cores_novas = cores_limpas(cores) if cores is not None else (anterior or {}).get("cores", {})
    modo = est.direcao.modo
    pals = edicao.palavras_do_clip(projeto, tl)
    editado = None
    if not tudo and do_modo(anterior, modo):
        editado = roteiro_limpo(roteiro, tl.duracao) if roteiro is not None else anterior["roteiro"]
    doc = gerar(projeto, clip, tl, pals, est, ad, relato, cancelar, editado or None, (anterior or {}).get("analise"), novo=tudo)
    doc["cores"] = cores_novas
    _gravar(pasta, doc)
    novos = [edicao.Item(**i) for i in para_itens(doc)]
    if modo == "desenho":
        itens = [i for i in doc_ed.itens if not (i.tipo == "cena" and i.params.get("cena") == "desenho")] + novos
        resumo = ["Desenho refeito do zero (análise, roteiro e composição)" if not editado
                  else "Desenho recomposto com o roteiro editado", f"{len(novos)} cena(s) de desenho"]
    else:
        itens = [i for i in doc_ed.itens if i.tipo != "cena"] + novos
        resumo = ["Cenas refeitas do zero (análise, roteiro e composição)" if not editado
                  else "Cenas recompostas com o roteiro editado", f"{len(novos)} cena(s)"]
        if not novos:
            resumo = ["A IA não montou as cenas: o próximo render pede a direção de novo"]
    edicao.salvar(pasta, doc_ed.model_copy(update={"itens": itens, "cenas_planejadas": bool(novos) or modo == "desenho"}), tl.duracao)
    if cores is not None:
        resumo.append("cores ajustadas")
    n = melhorar.registrar(projeto, clip_id, "ia", "refazer a direção de arte", resumo, getattr(ad, "nome", ""))
    return {"versao": n, "modo": modo, "cenas": len(novos)}


def resumo_do_clip(projeto: Any, clip_id: str) -> dict[str, Any]:
    """O que o painel "Direção de arte do clip" mostra: o documento do desenho (ou as cenas), a ficha e as cores."""
    from . import direcao, edicao

    clip, pasta = projeto.clip(clip_id)
    est = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)[0]
    ed = edicao.carregar(pasta)
    est = edicao.estilo_com_layout(est, ed)
    da = est.direcao
    doc = ler(pasta) or {}
    itens = ed.itens
    cores_cena = next((i.params["cores"] for i in itens if i.tipo == "cena" and i.params.get("cores")), {})
    f = direcao.ficha(da.ficha, {**da.cores, **da.fontes, **(doc.get("cores") or {}), **cores_cena})
    cenas = [{"inicio": i.inicio, "fim": i.fim, "cena": i.params.get("cena"),
              "texto": i.params.get("etiqueta") or i.params.get("texto") or i.params.get("valor") or ", ".join(i.params.get("itens") or [])}
             for i in itens if i.tipo == "cena"]
    arte = None
    if da.modo == "arte" and da.arte:
        from . import artes

        arte = artes.resumo_painel(da.arte, itens)
    return {"arte": arte, "ativa": da.ativa, "modo": da.modo, "layout": da.layout, "ficha": f.nome, "estilo": est.nome,
            "composicao": {"layout": da.layout, "proporcao": da.proporcao, "janela_canto": da.janela_canto, "janela_escala": da.janela_escala,
                           "janela_encaixe": da.janela_encaixe},
            "cores": {k: getattr(f, k) for k in CORES_EDITAVEIS}, "analise": doc.get("analise"), "direcao_video": doc.get("direcao_video"), "roteiro": doc.get("roteiro"),
            "camadas": doc.get("camadas"), "modelo": doc.get("modelo"), "criado": doc.get("criado"), "cenas": cenas,
            "pecas": sorted({c.get("peca") for cs in doc.get("camadas") or [] for c in cs if c.get("peca")}),
            "nomes_pecas": {k: v[0] for k, v in PECAS.items()}}


# ficha "maquete": o HUD (cabeçalho, chip da etapa, cartões presos por fio, painel do dado, carimbo) e a câmera que se aproxima
CSS_HUD_MAQUETE = """
body.ficha-maquete .fundo-da { background: var(--fundo); }
body.ficha-maquete .fundo-da .brilho { opacity: .35; }
body.ficha-maquete .po0 { animation: deriva-po 14s linear infinite alternate; }
body.ficha-maquete .po1 { animation: deriva-po 22s linear infinite alternate-reverse; }
body.ficha-maquete .po2 { animation: deriva-po 30s linear infinite alternate; }
@keyframes deriva-po { from { transform: translate(0, 0); } to { transform: translate(-40px, -24px); } }
body.ficha-maquete .cabecalho-tema { display: block; position: absolute; top: calc(var(--u) * 26); left: calc(var(--u) * 40); z-index: 2;
  font-family: var(--f-corpo); font-size: calc(var(--u) * 19); letter-spacing: .32em; color: var(--suave); white-space: nowrap; }
body.ficha-maquete .etiqueta-tema { top: calc(var(--u) * 62); left: calc(var(--u) * 40); right: auto; margin: 0; display: flex;
  align-items: center; gap: calc(var(--u) * 12); background: color-mix(in srgb, var(--fundo) 82%, black); color: var(--texto);
  border: 1px solid color-mix(in srgb, var(--texto) 18%, transparent); font-family: var(--f-corpo); font-size: calc(var(--u) * 24);
  letter-spacing: .14em; padding: calc(var(--u) * 9) calc(var(--u) * 20); border-radius: 999px; }
body.ficha-maquete .etiqueta-tema .ponto { display: inline-block; width: calc(var(--u) * 13); height: calc(var(--u) * 13);
  border-radius: 50%; background: var(--destaque); box-shadow: 0 0 calc(var(--u) * 10) var(--destaque); }
body.ficha-maquete .rotulo-simples { display: none; }
body.ficha-maquete .cartao-rot { display: inline; animation: d-pop .35s cubic-bezier(.2, 1.3, .4, 1) both; }
body.ficha-maquete .cartao-rot rect { fill: color-mix(in srgb, var(--fundo) 86%, black); stroke: color-mix(in srgb, var(--texto) 22%, transparent); stroke-width: 1.5; }
body.ficha-maquete .cartao-rot .fio { fill: none; stroke: var(--texto); stroke-width: 2; opacity: .8; }
body.ficha-maquete .cartao-rot circle { fill: var(--texto); }
body.ficha-maquete .cartao-rot .ponto { fill: currentColor; }
body.ficha-maquete .cartao-rot text { fill: var(--texto); text-anchor: start; font-size: 24px; letter-spacing: .04em; }
body.ficha-maquete .painel-dado { display: inline; fill: color-mix(in srgb, var(--fundo) 86%, black); stroke: currentColor; stroke-width: 2.5; }
body.ficha-maquete .carimbo { display: inline; fill: var(--destaque); }
body.ficha-maquete .camada:has(.carimbo) { rotate: -4deg; }
body.ficha-maquete .camada:has(.carimbo) .texto-grande { fill: var(--fundo); }
body.ficha-maquete .rotulo { fill: var(--suave); }
body.ficha-maquete .cena.desenho .palco { animation: camera-maquete var(--dur) cubic-bezier(.3, 0, .3, 1) both; transform-origin: 50% 55%; }
@keyframes camera-maquete { from { transform: scale(1.08) translateY(1.5%); filter: blur(5px); } 12% { filter: blur(0); } to { transform: scale(1); } }
"""


# a amostra do passo 3 na maquete (a fala de exemplo da amostra; no app as cenas vêm da IA)
CENAS_EXEMPLO_MAQUETE = [
    (0.0, 1.9, {"etiqueta": "O SEU CORTE", "cabecalho": "O SEU CORTE", "camadas": [
        {"tipo": "peca", "peca": "celular", "rotulo": "Vídeo curto", "x": 360, "y": 470, "escala": 2.2, "entra": 0.1, "acao": "cai", "cor": "destaque"},
        {"tipo": "peca", "peca": "boneco", "rotulo": "", "x": 640, "y": 520, "escala": 1.6, "entra": 0.4, "acao": "pop", "cor": "destaque"}]}),
    (1.9, 3.8, {"etiqueta": "A REGRA", "cabecalho": "O SEU CORTE", "camadas": [
        {"tipo": "peca", "peca": "grafico_sobe", "rotulo": "Retenção", "x": 330, "y": 500, "escala": 2.3, "entra": 0.0, "acao": "cresce", "cor": "bom"},
        {"tipo": "dado", "grafico": "numero", "valor": "87%", "x": 720, "y": 330, "escala": 0.8, "entra": 0.6, "acao": "pop", "cor": "destaque"}]}),
    (3.8, 5.6, {"etiqueta": "O RESULTADO", "cabecalho": "O SEU CORTE", "camadas": [
        {"tipo": "peca", "peca": "trofeu", "rotulo": "Mais alcance", "x": 430, "y": 500, "escala": 2.4, "entra": 0.0, "acao": "cai", "cor": "destaque"},
        {"tipo": "texto", "rotulo": "FEITO!", "x": 660, "y": 720, "escala": 1.0, "entra": 0.8, "acao": "pop", "cor": "destaque"}]}),
]
