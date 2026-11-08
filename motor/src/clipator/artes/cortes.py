"""As cinco direções guiadas pela fala: Encaixe Vivo, Pixel em Cena, Fluxo Facetado, Rota em Foco e Terreno Vivo.

A diferença para as outras direções: aqui cada cena é uma AÇÃO sobre OBJETOS citados na fala. O plano vem da transcrição
(regras e léxico sem IA; com IA, o adaptador recebe texto e devolve JSON que é conferido contra a fala) e guarda só palavras
ditas. O mundo inteiro do clip é montado por dados/cortes/motor.js a partir desse plano, com three.js: cada quadro é uma
função do tempo, sem estado entre quadros, e os tempos saem das palavras cronometradas depois dos cortes internos.

A identidade do estilo (material, câmera, perspectiva) mora no motor; objetos, ações e ordem mudam com a fala. A câmera e
os rótulos são calculados para o retângulo do layout (composicao.Geometria). Sem WebGL fica a alternativa em SVG desta página.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .. import maquete3d
from ..workspace import _dados
from . import tokens
from .kit import Ctx, g, linhas, retangulo, ajustar, ALTURA_LINHA
from .tres import caixa_iso

VERSAO = 1  # entra no hash das amostras destas cinco; o código do motor.js e o léxico entram também
MAX_OBJETOS = 4
ACOES: dict[str, tuple[str, ...]] = {
    "encaixe-vivo": ("montar", "destacar", "desmontar"),
    "pixel-em-cena": ("chegar", "caminhar", "usar", "apontar", "abrir", "observar"),
    "fluxo-facetado": ("entrar", "mover", "detectar", "abrir", "separar", "sair"),
    "rota-em-foco": ("enquadrar", "partir", "percorrer", "marcar", "chegar"),
    "terreno-vivo": ("mostrar", "abrir_canal", "erguer", "plantar", "segurar"),
}
ACAO_PADRAO = {"encaixe-vivo": "montar", "pixel-em-cena": "caminhar", "fluxo-facetado": "mover", "rota-em-foco": "percorrer", "terreno-vivo": "erguer"}
CONFIG = {
    "encaixe-vivo": {},
    "pixel-em-cena": {"pixel": True},
    "fluxo-facetado": {},
    "rota-em-foco": {},
    "terreno-vivo": {},
}
_VAZIAS = set("a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem que e ou mas se como mais muito "
              "ele ela eles elas eu voce isso isto esse essa este esta foi era ser ter tem ao aos ja nao sim so me te lhe seu sua "
              "fim agora depois antes aqui ali la entao vez novo nova mesmo mesma parte partes peca pecas cima baixo".split())


def eh_corte(slug: str | None) -> bool:
    return slug in ACOES or slug == "geo-em-cena"  # Geo em Cena: mesmo fluxo, com lugares reais no lugar de objetos (artes/geo.py)


@lru_cache(maxsize=1)
def vocabulario() -> dict[str, Any]:
    return json.loads((_dados("cortes") / "lexico.json").read_text(encoding="utf-8"))


def formas() -> dict[str, Any]:
    return vocabulario()["formas"]


def _formas_da_palavra(t: str) -> list[str]:
    """A palavra e os singulares possíveis (canais, árvores, sensores, balões)."""
    return [t] + [t[: -len(fim)] + novo for fim, novo in (("s", ""), ("oes", "ao"), ("aes", "ao"), ("is", "l"), ("es", "")) if t.endswith(fim) and len(t) > len(fim) + 2]


def forma_da_palavra(palavra: str) -> str | None:
    ts = tokens(palavra)
    if not ts:
        return None
    lex = vocabulario()["lexico"]
    return next((lex[s] for s in _formas_da_palavra(ts[0]) if s in lex), None)


def _limpa(s: Any, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def _ident(nome: str, forma: str) -> str:
    return re.sub(r"\W+", "-", " ".join(tokens(nome))) or forma


def normalizar_corte(slug: str, c: dict[str, Any]) -> dict[str, Any]:
    """Só o que o motor entende: ação da lista do estilo, forma da lista, no máximo quatro objetos."""
    if slug not in ACOES:
        from . import geo

        return geo.normalizar(c)
    fs = formas()
    objetos, vistos = [], set()
    for o in c.get("objetos") or []:
        if not isinstance(o, dict):
            continue
        nome = _limpa(o.get("nome"), 40)
        if not nome:
            continue
        forma = o.get("forma") if o.get("forma") in fs else (forma_da_palavra(nome) or "bloco")
        ident = _ident(nome, forma)
        if ident not in vistos:
            vistos.add(ident)
            objetos.append({"id": ident, "nome": nome, "forma": forma})
    objetos = objetos[:MAX_OBJETOS]
    acao = c.get("acao") if c.get("acao") in ACOES[slug] else ACAO_PADRAO[slug]
    alvo = _ident(_limpa(c.get("alvo"), 40), "") if c.get("alvo") else ""
    if alvo not in vistos:
        alvo = objetos[-1]["id"] if objetos else ""
    conj = c.get("conjunto") if c.get("conjunto") in vocabulario()["conjuntos"] else ""
    return {"acao": acao, "objetos": objetos, "alvo": alvo, "conjunto": conj, "ficticio": bool(c.get("ficticio"))}


def _acao_da_fala(slug: str, ts: list[str], tem_objeto: bool) -> str:
    verbos = sorted(vocabulario()["verbos"][slug].items(), key=lambda kv: -len(kv[0]))
    for t in ts:
        if t in _VAZIAS or forma_da_palavra(t):
            continue
        for raiz, acao in verbos:
            if t.startswith(raiz):
                return acao
    return ACAO_PADRAO[slug] if tem_objeto else ("segurar" if slug == "terreno-vivo" else ACOES[slug][0])


def da_fala(slug: str, pals: list[dict], anteriores: list[dict] | None = None) -> dict[str, Any]:
    """Sem IA: quem e o que aparecem, e a ação, tirados das palavras do trecho. Nome na tela é sempre a palavra dita."""
    if slug not in ACOES:
        from . import geo

        return geo.da_fala(pals, anteriores)
    objetos: list[dict[str, str]] = []
    ts: list[str] = []
    conj = ""
    voc = vocabulario()
    ficticio = False
    for w in pals:
        limpa = w["texto"].strip(" ,.;:!?\"'“”()")
        t = (tokens(limpa) or [""])[0]
        ts.append(t)
        if t.startswith(("fictici", "imaginari", "inventad")):
            ficticio = True
        ss = _formas_da_palavra(t)
        achado = next((s for s in ss if s in voc["conjuntos"]), "")
        if achado:
            conj = achado
            continue
        if any(s in voc["cenarios"] for s in ss):
            continue
        forma = forma_da_palavra(limpa)
        if forma:
            objetos.append({"nome": limpa, "forma": forma})
    if not objetos:  # frase sem objeto conhecido: fica o que já está em cena; uma palavra forte vira bloco só se o estilo monta peças
        fortes = [w["texto"].strip(" ,.;:!?\"'“”()") for w in pals if len((tokens(w["texto"]) or [""])[0]) > 4 and (tokens(w["texto"]) or [""])[0] not in _VAZIAS]
        if fortes and slug in ("encaixe-vivo", "fluxo-facetado") and _acao_da_fala(slug, ts, False) not in ("desmontar", "sair"):
            objetos.append({"nome": fortes[0], "forma": "bloco"})
    return normalizar_corte(slug, {"acao": _acao_da_fala(slug, ts, bool(objetos)), "objetos": objetos, "conjunto": conj, "ficticio": ficticio})


# ---- com IA: texto entra, JSON conferido sai -----------------------------------------------------------------
def schema(slug: str) -> dict[str, Any]:
    if slug not in ACOES:
        from . import geo

        return geo.schema()
    from . import curta

    return {"type": "object", "properties": {"cenas": {"type": "array", "items": {"type": "object", "properties": {
        "indice": {"type": "number"}, "texto": {"type": "string"}, "itens": {"type": "array", "items": {"type": "string"}},
        "nota": {"type": "string"}, "dado": {"type": "string"}, "peca": {"type": "string"},
        "acao": {"type": "string", "enum": list(ACOES[slug])}, "alvo": {"type": "string"},
        "conjunto": {"type": "string", "enum": ["", *vocabulario()["conjuntos"]]},
        "objetos": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "forma": {"type": "string", "enum": list(formas())}},
            "required": ["nome", "forma"], "additionalProperties": False}},
        "curta": curta.schema_item()},
        "required": ["indice", "texto", "itens", "nota", "dado", "peca", "acao", "alvo", "conjunto", "objetos", "curta"], "additionalProperties": False}}},
        "required": ["cenas"], "additionalProperties": False}


def prompt(slug: str, roteiro: list[dict], extra: str = "", fala: str = "") -> str:
    from . import texto_runtime

    if slug not in ACOES:
        from . import geo

        return geo.prompt(roteiro, extra)

    from . import curta

    cenas = json.dumps([{"indice": k, "ancora": c.get("ancora", ""), "duracao": round(c["fim"] - c["inicio"], 1), "etiqueta": c.get("etiqueta", ""),
                         "descricao": c.get("descricao", ""), "dado": c.get("dado", "")} for k, c in enumerate(roteiro)], ensure_ascii=False)
    desenhos = "; ".join(f"{k}: {v['desc']}" for k, v in formas().items())
    return (f"{texto_runtime(slug)}\n\nPara cada cena do roteiro devolva a animação que representa exatamente o que é dito naquele trecho: "
            f"'acao' (uma destas: {', '.join(ACOES[slug])}), 'objetos' (até {MAX_OBJETOS}, na ordem da fala; 'nome' é a palavra dita, sem trocar nem "
            "traduzir, e 'forma' é o desenho mais próximo da lista), 'alvo' (o nome do objeto em foco), 'conjunto' (o objeto maior que as partes "
            "formam, se estiver na lista, ou vazio), 'texto' (a frase da cena, tirada da fala), 'itens', 'nota', 'dado' (o número dito, ou vazio) e 'peca' vazio. "
            f"Desenhos: {desenhos}. Objeto que não foi dito não entra. Nada de número, citação ou fato que não esteja na fala.\n"
            + (f"{extra[:5000]}\n" if extra else "") + f"Cenas: {cenas}" + curta.instrucoes(fala or " ".join(c.get("ancora", "") for c in roteiro)))


def de_resposta(slug: str, c: dict[str, Any], pals: list[dict], i: int, j: int) -> dict[str, Any]:
    """Confere a resposta da IA: objeto cujo nome não foi dito naquele trecho sai. Sem resposta aproveitável, valem as regras."""
    if slug not in ACOES:
        from . import geo

        return geo.de_resposta(c, pals, i, j)
    base = da_fala(slug, pals[i:j + 1])
    ditas = {t for w in pals[i:j + 1] for t in tokens(w["texto"])}
    objetos = [o for o in (c.get("objetos") or []) if isinstance(o, dict) and tokens(str(o.get("nome") or "")) and set(tokens(str(o.get("nome")))) <= ditas]
    if not objetos:
        return base
    return normalizar_corte(slug, {"acao": c.get("acao") or base["acao"], "objetos": objetos, "alvo": c.get("alvo"),
                                   "conjunto": c.get("conjunto") or base["conjunto"], "ficticio": base["ficticio"]})


# ---- plano para o motor --------------------------------------------------------------------------------------
def _tempo_do_nome(nome: str, palavras: list[dict], inicio: float) -> float:
    """O segundo do clip em que o nome é dito dentro da cena: o objeto nunca aparece antes da palavra."""
    alvo = tokens(nome)
    ws = [(tokens(w["texto"]) or [""])[0] for w in palavras]
    for i in range(max(0, len(ws) - len(alvo) + 1)):
        if alvo and ws[i:i + len(alvo)] == alvo:
            return round(inicio + float(palavras[i]["inicio"]), 3)
    return round(inicio + 0.1, 3)


def plano(cenas: list[dict]) -> list[dict[str, Any]]:
    """As ações do clip em ordem de tempo, com o momento em que cada objeto é dito."""
    out = []
    for c in sorted((c for c in cenas if c["params"].get("cena") == "arte" and c["params"].get("corte")), key=lambda x: float(x["inicio"])):
        ct, ini = c["params"]["corte"], float(c["inicio"])
        pal = c.get("palavras") or []
        out.append({"t0": round(ini, 3), "t1": round(float(c["fim"]), 3), "acao": ct["acao"], "alvo": ct.get("alvo", ""), "conjunto": ct.get("conjunto", ""),
                    "ficticio": bool(ct.get("ficticio")),
                    "objetos": [{**o, "t": _tempo_do_nome(o["nome"], pal, ini)} for o in ct.get("objetos", [])]})
    return out


def _extras(camada: Any, cenas: list[dict]) -> tuple[str, str]:
    p = maquete3d.caminho_three()
    if p is None:
        return "", ""
    if any(camada.ctx(c["params"], 0, 1, 0, 1, [], None).leve for c in cenas if c["params"].get("cena") == "arte"):
        return "", ""  # a alternativa leve vale para o clip todo: o mundo é um só
    from . import curta

    if curta.ativo(cenas):  # modo curta: um plano por frase, com cenário, gente e montagem (artes/curta.py)
        return curta.extras(camada, cenas, p.read_text(encoding="utf-8"))
    par = camada.ctx({}, 0, 1, 0, 1, [], None).par
    acoes = plano(cenas)
    fs = formas()
    usadas = {o["forma"] for a in acoes for o in a["objetos"]}
    cfg = {"estilo": camada.slug, "acoes": acoes, "duracao": camada.duracao, "par": par, "semente": int(par.get("semente", 42)),
           "formas": {k: fs[k]["pecas"] for k in usadas}, "moveis": [k for k in usadas if fs[k].get("movel")],
           "conjuntos": vocabulario()["conjuntos"], "geo": camada.geo.para_js() if camada.geo is not None else None, **CONFIG[camada.slug]}
    dados = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    js = (_dados("cortes") / "motor.js").read_text(encoding="utf-8")
    return ('<canvas id="arte3d"></canvas><div id="rotulos3d"></div><div id="relogio3d"></div>',
            f"<script>{p.read_text(encoding='utf-8')}</script>\n<script>window.CORTE = {dados};</script>\n<script>{js}</script>")


CSS = """
#arte3d { position: absolute; left: 0; top: var(--topo); width: 100%; height: var(--alt); }
#rotulos3d { position: absolute; left: 0; top: var(--topo); width: 100%; height: var(--alt); overflow: hidden; pointer-events: none; }
#rotulos3d svg { position: absolute; inset: 0; width: 100%; height: 100%; }
#relogio3d { position: absolute; width: 1px; height: 1px; animation: relogio3d var(--duracao) linear both; }
@property --t3 { syntax: '<number>'; inherits: false; initial-value: 0; }
body.tres-d .so-2d { display: none; }
.rot3 { position: absolute; left: 0; top: 0; font-family: var(--f-corpo); font-size: calc(var(--u) * 38); line-height: 1.1; color: var(--texto); background: var(--fundo);
  border: calc(var(--u) * 3) solid var(--primaria); border-radius: calc(var(--u) * 8); padding: calc(var(--u) * 7) calc(var(--u) * 14); white-space: nowrap; }
.rot3.foco { border-color: var(--destaque); }
.rot3.pixel { border-radius: 0; border-width: calc(var(--u) * 4); }
.rot3.selo { font-size: calc(var(--u) * 30); opacity: .92; border-color: var(--texto); }
"""
from .curta import CSS as _CSS_CURTA  # noqa: E402

CSS += _CSS_CURTA


def cena(c: Ctx) -> str:
    """A alternativa sem WebGL: as mesmas ações em polígonos isométricos e a frase; some quando o 3D liga."""
    ct = c.p.get("corte") or {}
    objs = ct.get("objetos") or []
    ox, oy = c.W / 2, c.y0 + c.lh * 0.45
    pecas = ""
    for i, o in enumerate(objs):
        t = float(c.quando(o["nome"], 0.1))
        pecas += g(caixa_iso(ox, oy, -1.2 + 0.9 * i, -0.4, 0, 0.7, 0.7, 0.4 + 0.2 * (i % 3), "var(--destaque)" if o["id"] == ct.get("alvo") else "var(--primaria)"), t, "a-pop", 0.4)
    ls, tam = ajustar(" · ".join(o["nome"] for o in objs) or c.texto, c.fonte_corpo, c.lw - 40, 150, 2, 54, 36)
    h = len(ls) * tam * ALTURA_LINHA + 26
    y = c.y1 - h
    placa = g(retangulo(c.x0, y, c.lw, h, "var(--fundo)", 8, 'opacity=".94"') + linhas(c.x0 + 20, y + 8 + tam, ls, tam), 0.1, "a-sobe", 0.4)
    return f'<g class="so-2d">{pecas}{placa}</g>'


def fundo(c: Ctx) -> str:
    return retangulo(0, 0, c.W, c.H, "var(--fundo)")


class DirecaoCorte:
    """A direção guiada pela fala: `extras` monta o mundo do clip inteiro; `cena` é a alternativa em SVG."""

    tela_cheia = True

    def __init__(self) -> None:
        self.cena, self.fundo, self.css, self.extras = cena, fundo, CSS, _extras


DIRECOES = {slug: DirecaoCorte() for slug in ACOES}
