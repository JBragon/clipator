"""Importa a especificação de uma direção visual (`especificacao.json`, contrato proposto `clipator-arte/1`) como DA.

Assim a direção ganha o que toda DA tem: validador de contraste, prancha, marca do canal por cima, guia da IA
e conferência das cenas. O renderizador da direção continua sendo dela; aqui só entram os tokens.

O que a especificação traz e onde vai parar:

  cores (fundo, superficie, texto, texto_suave, primaria, destaque) → cor.paleta, com o contraste corrigido
      (texto suave a 4,5:1, primária e destaque a 3:1; a cor original fica no comentário e, se o destaque
      precisou mudar, ela continua disponível como `realce`, para fundo de grifo com texto escuro por cima)
  fontes (titulo, corpo)               → tipografia.papeis
  conceito, usar_em, familia           → conceito.frase e palavras_chave
  composicao, material_e_luz           → conceito.faca;   evitar → conceito.nao_faca
  movimento                            → movimento.entrada e principios
  fases, criterios, usar_em            → cenas (tom, regras); complexidade → ritmo
  som                                  → som.efeitos e volume
  backend, layout, proporção, alternativa leve, construção → anotações `x_` (para quem implementa o render)

As cores que faltam (secundária, positivo, negativo, alerta) saem da própria paleta ou de valores seguros para
fundo claro ou escuro, sempre com contraste conferido.
"""

from __future__ import annotations

import re
from typing import Any

from . import cores as C

_SEMANTICAS_ESCURO = {"positivo": "#3ECF8E", "negativo": "#FF5D6C", "alerta": "#FFA94D"}
_SEMANTICAS_CLARO = {"positivo": "#1E7F4F", "negativo": "#B3261E", "alerta": "#A85A00"}
_RITMO = {"baixa": (3.0, 12.0), "media": (4.0, 10.0), "alta": (5.0, 8.0)}


def id_curto(id_: str) -> str:
    return re.sub(r"^clipator-arte-", "", id_)


def _frases(texto: str, limite: int = 4) -> list[str]:
    partes = [p.strip() for p in re.split(r"(?<=[.!?])\s+", texto or "") if p.strip()]
    partes = [p[0].upper() + p[1:] for p in partes]
    return [p if p.endswith((".", "!", "?")) else p + "." for p in partes][:limite]


def _itens(texto: str) -> list[str]:
    """“A, B e C.” → ["A.", "B.", "C."]"""
    t = (texto or "").strip().rstrip(".")
    if not t:
        return []
    partes = re.split(r",\s+|\s+e\s+(?=[^,]*$)", t)
    return [p.strip()[0].upper() + p.strip()[1:] + "." for p in partes if p.strip()]


def _entrada(movimento: str) -> str:
    m = (movimento or "").lower()
    for chaves, nome in ((("revel", "máscara", "mascara", "desenh", "traç"), "mascara"),
                         (("travelling", "desliz", "corre", "atravess", "percorr"), "desliza"),
                         (("separ", "cresc", "escala", "infl", "expand", "monta"), "escala"),
                         (("digit", "escrev"), "digita"), (("fade", "esmaec", "dissolv"), "fade")):
        if any(c in m for c in chaves):
            return nome
    return "sobe"


def _contraste(nome: str, cor: str, fundo: str, alvo: float, notas: list[str]) -> str:
    cor = C.normalizar_hex(cor)
    if C.contraste(cor, fundo) >= alvo:
        return cor
    novo = C.ajustar_para_contraste(cor, fundo, alvo)
    notas.append(f"{nome} {cor} → {novo} ({C.contraste(cor, fundo):.1f}:1 → {C.contraste(novo, fundo):.1f}:1)")
    return novo


def de_especificacao(spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """(dados da DA prontos para salvar como predefinido, notas do que foi corrigido)."""
    notas: list[str] = []
    cores = {k: C.normalizar_hex(v) for k, v in (spec.get("cores") or {}).items() if C.e_hex(str(v))}
    faltam = [k for k in ("fundo", "superficie", "texto", "texto_suave", "primaria", "destaque") if k not in cores]
    if faltam:
        raise ValueError("a especificação não traz as cores: " + ", ".join(faltam))
    fundo = cores["fundo"]
    claro = C.luminancia(fundo) > 0.4
    paleta = dict(cores)
    paleta["texto"] = _contraste("texto", cores["texto"], fundo, 7.0 if C.contraste(cores["texto"], fundo) >= 7 else 4.5,
                                 notas)
    paleta["texto_suave"] = _contraste("texto_suave", cores["texto_suave"], fundo, 4.5, notas)
    paleta["primaria"] = _contraste("primaria", cores["primaria"], fundo, 3.0, notas)
    paleta["destaque"] = _contraste("destaque", cores["destaque"], fundo, 3.0, notas)
    if C.contraste(paleta["texto"], paleta["superficie"]) < 7:  # texto em cartão: no celular, mire em 7:1
        melhor = C.ajustar_para_contraste(paleta["texto"], paleta["superficie"], 7.0)
        if C.delta_e(melhor, paleta["texto"]) < 12 and C.contraste(melhor, fundo) >= C.contraste(paleta["texto"], fundo) * 0.9:
            notas.append(f"texto {paleta['texto']} → {melhor} (7:1 também sobre a superfície)")
            paleta["texto"] = melhor
    if C.delta_e(paleta["destaque"], cores["destaque"]) >= 10:
        paleta["realce"] = cores["destaque"]  # a cor original serve de fundo de grifo, com texto escuro por cima
    secundaria = C.misturar(paleta["primaria"], fundo, 0.55)
    if C.delta_e(secundaria, paleta["superficie"]) < 6:
        secundaria = C.deslocar_luminosidade(secundaria, -12 if claro else 12)
    paleta["secundaria"] = secundaria
    for nome, hexa in (_SEMANTICAS_CLARO if claro else _SEMANTICAS_ESCURO).items():
        paleta[nome] = _contraste(nome, hexa, fundo, 3.0, [])
    fontes = spec.get("fontes") or {}
    titulo = fontes.get("titulo") or "Bebas Neue"
    corpo = fontes.get("corpo") or "Montserrat ExtraBold"
    condensada = any(x in titulo.lower() for x in ("bebas", "anton", "oswald", "condensed"))
    papeis = {
        "titulo": {"familia": titulo, "reserva": "Impact", "peso": 400, "caixa_alta": condensada,
                   "espacamento": 0.02 if condensada else 0.0, "entrelinha": 1.0},
        "subtitulo": {"familia": titulo, "reserva": "Impact", "peso": 400, "caixa_alta": True,
                      "espacamento": 0.08, "entrelinha": 1.05},
        "corpo": {"familia": corpo, "peso": 800, "entrelinha": 1.25},
        "dados": {"familia": corpo, "peso": 800, "entrelinha": 1.1},
        "legenda": {"familia": corpo, "peso": 800, "caixa_alta": True, "entrelinha": 1.08},
    }
    intervalo, por_minuto = _RITMO.get(str(spec.get("complexidade") or "media"), _RITMO["media"])
    usar_em = str(spec.get("usar_em") or "")
    palavras = [str(spec.get("familia") or "").lower()] + [p.strip() for p in re.split(r",\s*|\s+e\s+", usar_em)]
    palavras = [p for p in dict.fromkeys(palavras) if p and len(p.split()) <= 3][:8]
    som = spec.get("som") or {}
    regras = [f"Sequência de cada cena: {'; '.join(spec.get('fases') or [])}."] if spec.get("fases") else []
    regras += list(spec.get("criterios") or [])
    dados: dict[str, Any] = {
        "herda": "base",
        "nome": spec.get("nome") or id_curto(str(spec.get("id") or "")),
        "conceito": {
            "frase": spec.get("conceito") or "",
            "palavras_chave": palavras,
            "faca": (_frases(spec.get("composicao", ""), 2) + _frases(spec.get("material_e_luz", ""), 2))[:4],
            "nao_faca": _itens(spec.get("evitar", ""))[:6],
        },
        "cor": {"paleta": paleta},
        "tipografia": {"papeis": papeis},
        "movimento": {"entrada": _entrada(spec.get("movimento", "")),
                      "principios": _frases(spec.get("movimento", ""), 3)},
        "cenas": {"tom": f"Para {usar_em}." if usar_em else "", "intervalo": intervalo, "por_minuto": por_minuto,
                  "duracao": [2.0, 6.0], "regras": regras[:6]},
        "som": {"efeitos": {"entrada": som.get("entrada") or "click", "enfase": som.get("conclusao") or "ding",
                            "numero": "click", "alerta": "impacto"},
                "volume_efeitos": round(min(1.0, max(0.1, float(som.get("volume_relativo") or 0.3) * 2)), 2)},
        "x_direcao": {k: spec.get(k) for k in ("id", "backend_sugerido", "complexidade", "layout_padrao",
                                                "proporcao_animacao", "alternativa_leve", "construcao",
                                                "parametros_visuais") if spec.get(k) is not None},
    }
    # selo chapado na primária: o texto dele é o que mais contrasta com ela
    opcoes = {"fundo": fundo, "texto": paleta["texto"], "neutro-1": "#000000", "neutro-2": "#FFFFFF"}
    melhor_selo = max(opcoes, key=lambda k: C.contraste(opcoes[k], paleta["primaria"]))
    if melhor_selo != "fundo":
        dados["graficos"] = {"selo": {"cor_texto": melhor_selo}}
    if notas:
        dados["x_contraste_corrigido"] = notas
    return dados, notas
