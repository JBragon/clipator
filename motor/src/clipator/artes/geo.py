"""Geo em Cena: mapas geográficos reais guiados pela fala, para cortes que citam continentes, países e estados.

Quem aparece sai da transcrição: cada nome dito é resolvido para uma entidade da base Natural Earth (artes/geografia.py), com
tipo e país pai. Sem IA, por regras; com IA, o adaptador recebe texto e devolve nomes e níveis, nunca coordenadas, e tudo passa
de novo pelo resolvedor. Ambiguidade ou lugar ausente fica como pendência com aviso, e nenhum polígono é desenhado no lugar.
A cena guarda a âncora literal; o segundo de cada lugar sai das palavras depois dos cortes internos. O mapa do clip inteiro é
desenhado por dados/geo/geo3d.js em three.js (países citados sobem do chão, com luz, sombra e a câmera inclinada que voa de um lugar
ao outro) e, sem three.js, WebGL ou na alternativa leve, por dados/geo/geo.js em canvas 2D. Os dois são função do tempo e
enquadram dentro do retângulo livre calculado por composicao.py.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ..workspace import _dados
from . import geografia as gg
from .cortes import CSS as CSS_CORTES
from .. import maquete3d
from .kit import Ctx, retangulo

SLUG = "geo-em-cena"
VERSAO = 2  # 2: o mapa em 3D (geo3d.js, three.js). Entra no hash da amostra, junto com geo.js, o exemplo e os hashes da base
ACOES = ("aproximar", "destacar")  # aproximar: a câmera vai ao lugar; destacar: ele acende e a câmera só abre o bastante para mostrá-lo
ACAO_PADRAO = "aproximar"
MAX_LUGARES = 6
MAX_PALAVRAS_NOME = 8
NIVEIS_IA = ("", "continente", "pais", "subdivisao", "cidade")
_LIGA = {"de", "do", "da", "dos", "das"}
_DICA_SUB = {"estado", "provincia", "uf", "departamento", "prefeitura"}
_DICA_CIDADE = {"cidade", "municipio", "capital"}


# ---- nomes na fala ---------------------------------------------------------------------------------------------
def _limpa(s: Any, n: int) -> str:
    return " ".join(str(s or "").split())[:n]


def _nu(w: dict) -> str:
    return w["texto"].strip(" ,.;:!?\"'“”()")


def _tokens(pals: list[dict]) -> tuple[list[str], list[int]]:
    """Os pedaços normalizados da fala e a palavra de cada um ("Guiné-Bissau" dá dois pedaços da mesma palavra)."""
    ts: list[str] = []
    ws: list[int] = []
    for k, w in enumerate(pals):
        for t in gg.normalizar(w["texto"]).split():
            ts.append(t)
            ws.append(k)
    return ts, ws


@lru_cache(maxsize=1)
def _nao_lugar() -> frozenset[str]:
    return frozenset(s.casefold() for s in gg.apelidos()["nao_lugar"])


@lru_cache(maxsize=1)
def _homonimos() -> frozenset[str]:
    return frozenset(gg.normalizar(s) for s in gg.apelidos()["cidades_homonimas"])


def mencoes(pals: list[dict]) -> list[dict[str, Any]]:
    """Os nomes da base ditos no trecho, do mais longo para o mais curto em cada ponto (África do Sul antes de África).

    Nome próprio vem com maiúscula na transcrição; palavra comum que por acaso é nome de subdivisão (“Como”, “Para”) não conta.
    A comparação dessa lista guarda o acento: “Pará” passa, “Para” não. Códigos (SP, BR, IT) nunca valem na fala.
    """
    nomes = gg.nomes_falados()
    ts, ws = _tokens(pals)
    out: list[dict[str, Any]] = []
    p = 0
    while p < len(ts):
        achou = 0
        for n in range(min(MAX_PALAVRAS_NOME, len(ts) - p), 0, -1):
            chave = " ".join(ts[p:p + n])
            if chave not in nomes:
                continue
            i, j = ws[p], ws[p + n - 1]
            primeira = _nu(pals[i])
            if not primeira[:1].isupper() or (i == j and primeira.casefold() in _nao_lugar()):
                continue
            out.append({"i": i, "j": j, "chave": chave, "falado": " ".join(_nu(w) for w in pals[i:j + 1]), "ents": nomes[chave]})
            achou = n
            break
        p += achou or 1
    return out


def _dica(pals: list[dict], m: dict) -> str:
    """O que a fala diz do tipo do lugar logo antes (ou depois) do nome: subdivisao, pais, cidade ou nada."""
    antes = [gg.normalizar(w["texto"]) for w in pals[max(0, m["i"] - 2):m["i"]]]
    if antes and antes[-1] in _LIGA:
        antes = antes[:-1]
    ultima = antes[-1] if antes else ""
    depois = gg.normalizar(pals[m["j"] + 1]["texto"]) if m["j"] + 1 < len(pals) else ""
    if ultima in _DICA_CIDADE or depois == "capital":
        return "cidade"
    if ultima in _DICA_SUB:
        return "subdivisao"
    return "pais" if ultima == "pais" else ""


def _so_pais(m: dict) -> str | None:
    c = gg.sem_homonimo_interno(list(m["ents"]))
    return c[0].id if len(c) == 1 and c[0].nivel == "pais" else None


def _pendencia(falado: str, motivo: str, mensagem: str, opcoes: list[gg.Entidade] | None = None) -> dict[str, Any]:
    return {"falado": _limpa(falado, 60), "motivo": motivo, "mensagem": _limpa(mensagem, 240), "opcoes": [e.resumo() for e in (opcoes or [])[:8]]}


def _lugar(e: gg.Entidade, falado: str, ocorrencia: int = 1) -> dict[str, Any]:
    return {"id": e.id, "nivel": e.nivel, "nome": e.nome, "pais": e.pais, "descricao": gg.descricao(e), "falado": _limpa(falado, 60), "ocorrencia": ocorrencia}


def _decidir(m: dict, pals: list[dict], na_frase: set[str], antes: set[str]) -> gg.Entidade | dict[str, Any]:
    """A entidade da menção, ou a pendência. Nunca escolhe por semelhança: precisa de dica na fala ou de um país que a separe."""
    falado, chave = m["falado"], m["chave"]
    dica = _dica(pals, m)
    if dica == "cidade":
        return _pendencia(falado, "cidade", f"“{falado}” é citada como cidade. Não há camada municipal, então o polígono do estado não é usado.")
    ents = [e for e in m["ents"] if e.nivel == dica] if dica else gg.sem_homonimo_interno(list(m["ents"]))
    if not ents:
        return _pendencia(falado, "ausente", f"“{falado}” não existe na base nesse nível.")
    if len(ents) > 1:
        sem_pais = not any(e.nivel == "pais" for e in ents)  # Amazonas depois de citar o Brasil resolve; Geórgia, que também é país, não
        filhos = [e for e in ents if e.nivel == "subdivisao" and (e.pais in na_frase or ((dica or sem_pais) and e.pais in antes))]
        if len(filhos) == 1:
            return filhos[0]
        return _pendencia(falado, "ambiguo", f"“{falado}” pode ser mais de um lugar. Escolha um; até lá, nada é desenhado.", ents)
    e = ents[0]
    if e.nivel != "subdivisao" or dica or e.pais in na_frase:
        return e
    homonimo = chave in _homonimos()
    if not homonimo and (e.pais in antes or " " in chave):
        return e  # Minas Gerais não tem outra leitura; “Bahia” sozinha só vale depois de a fala citar o Brasil
    motivo = "A base tem só a UF, não o município." if homonimo else "Falta o país na fala."
    return _pendencia(falado, "confirmar", f"“{falado}”: confirme que a fala é sobre {e.nome} ({gg.descricao(e)}). {motivo}", [e])


def _cidades_soltas(pals: list[dict], ms: list[dict]) -> list[dict[str, Any]]:
    """“a cidade de Campinas”: a fala pediu uma cidade que a base não tem; vira aviso em vez de silêncio."""
    ocupadas = {k for m in ms for k in range(m["i"], m["j"] + 1)}
    out = []
    for k, w in enumerate(pals[:-1]):
        if gg.normalizar(w["texto"]) not in ("cidade", "municipio"):
            continue
        a = k + 2 if gg.normalizar(pals[k + 1]["texto"]) in _LIGA else k + 1
        b = a
        while b < len(pals) and _nu(pals[b])[:1].isupper():
            b += 1
        if b > a and a not in ocupadas:
            nome = " ".join(_nu(x) for x in pals[a:b])
            out.append(_pendencia(nome, "cidade", f"“{nome}” é uma cidade. Não há camada municipal, então nada é desenhado."))
    return out


def da_fala(pals: list[dict], anteriores: list[dict] | None = None) -> dict[str, Any]:
    """Sem IA: os lugares do trecho, resolvidos. `anteriores`: o que já foi dito no clip, para achar o país das subdivisões."""
    ms = mencoes(pals)
    na_frase = {p for p in map(_so_pais, ms) if p}
    antes = {p for p in map(_so_pais, mencoes(anteriores or [])) if p}
    lugares: list[dict[str, Any]] = []
    pendencias = _cidades_soltas(pals, ms)
    for m in ms:
        r = _decidir(m, pals, na_frase, antes)
        if isinstance(r, dict):
            pendencias.append(r)
        else:
            lugares.append(_lugar(r, m["falado"]))
    filhos = {x["pais"] for x in lugares if x["nivel"] == "subdivisao"}
    if filhos:  # “Dentro do Brasil, veja São Paulo”: o país é contexto, o destaque é a subdivisão
        lugares = [x for x in lugares if not (x["nivel"] == "pais" and x["id"] in filhos)]
    return normalizar({"acao": ACAO_PADRAO, "lugares": lugares, "pendencias": pendencias})


def normalizar(c: dict[str, Any]) -> dict[str, Any]:
    """Só entra o que a base conhece: id e nível são conferidos, e o resto do lugar sai dela, não do plano."""
    lugares, vistos = [], set()
    pendencias: list[dict[str, Any]] = []
    for x in c.get("lugares") or []:
        if not isinstance(x, dict):
            continue
        e = gg.por_id(str(x.get("nivel") or ""), str(x.get("id") or ""))
        falado = _limpa(x.get("falado"), 60)
        if e is None:
            pendencias.append(_pendencia(falado or str(x.get("id"))[:60], "ausente", f"O lugar “{falado or x.get('id')}” não está na base: nada é desenhado."))
            continue
        if (e.nivel, e.id) in vistos or not falado:
            continue
        vistos.add((e.nivel, e.id))
        try:
            oc = max(1, min(100, int(x.get("ocorrencia") or 1)))
        except (TypeError, ValueError):
            oc = 1
        lugares.append(_lugar(e, falado, oc))
    for x in c.get("pendencias") or []:
        if not isinstance(x, dict) or x.get("motivo") not in ("ausente", "ambiguo", "confirmar", "cidade"):
            continue
        ops = [gg.por_id(str(o.get("nivel")), str(o.get("id"))) for o in x.get("opcoes") or [] if isinstance(o, dict)]
        pendencias.append(_pendencia(x.get("falado"), x["motivo"], x.get("mensagem"), [o for o in ops if o is not None]))
    return {"acao": c.get("acao") if c.get("acao") in ACOES else ACAO_PADRAO, "lugares": lugares[:MAX_LUGARES], "pendencias": pendencias[:MAX_LUGARES]}


def escolher(corte: dict[str, Any], falado: str, nivel: str, id_: str) -> dict[str, Any]:
    """A resposta do usuário a uma pendência. Só vale uma das opções daquela pendência, então a tela não cria lugar novo."""
    pend = next((p for p in corte.get("pendencias", []) if p["falado"] == falado), None)
    if pend is None or not any(o["id"] == id_ and o["nivel"] == nivel for o in pend["opcoes"]):
        raise ValueError(f"Opção inválida para “{falado}”.")
    return normalizar({**corte, "lugares": [*corte.get("lugares", []), {"id": id_, "nivel": nivel, "falado": falado}],
                       "pendencias": [p for p in corte["pendencias"] if p is not pend]})


# ---- com IA: texto entra, JSON conferido sai -----------------------------------------------------------------
def schema() -> dict[str, Any]:
    return {"type": "object", "properties": {"cenas": {"type": "array", "items": {"type": "object", "properties": {
        "indice": {"type": "number"}, "texto": {"type": "string"}, "itens": {"type": "array", "items": {"type": "string"}},
        "nota": {"type": "string"}, "dado": {"type": "string"}, "peca": {"type": "string"}, "acao": {"type": "string", "enum": list(ACOES)},
        "lugares": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "nivel": {"type": "string", "enum": list(NIVEIS_IA)}, "pais": {"type": "string"}},
            "required": ["nome", "nivel", "pais"], "additionalProperties": False}}},
        "required": ["indice", "texto", "itens", "nota", "dado", "peca", "acao", "lugares"], "additionalProperties": False}}},
        "required": ["cenas"], "additionalProperties": False}


def prompt(roteiro: list[dict], extra: str = "") -> str:
    from . import texto_runtime

    cenas = json.dumps([{"indice": k, "ancora": c.get("ancora", ""), "duracao": round(c["fim"] - c["inicio"], 1), "descricao": c.get("descricao", "")}
                        for k, c in enumerate(roteiro)], ensure_ascii=False)
    return (f"{texto_runtime(SLUG)}\n\nPara cada cena do roteiro devolva 'lugares': os continentes, países e subdivisões citados naquele trecho, na ordem da fala. "
            "'nome' é exatamente o que foi dito; 'nivel' é continente, pais, subdivisao ou cidade, ou vazio se a fala não permitir saber; 'pais' é o país da "
            "subdivisão, ou vazio. Não devolva coordenadas, contornos nem ids. 'acao': aproximar ou destacar. 'texto' é a frase da cena, tirada da fala; "
            "'itens', 'nota', 'dado' e 'peca' ficam vazios. Lugar que não foi dito não entra. Nada de número, evento ou fato que não esteja na fala.\n"
            + (f"{extra[:3000]}\n" if extra else "") + f"Cenas: {cenas}")


def _trecho(nome: str, pals: list[dict]) -> str | None:
    """O nome tal como foi dito no trecho; None se ele não foi dito."""
    alvo = gg.normalizar(nome).split()
    ts, ws = _tokens(pals)
    for p in range(len(ts) - len(alvo) + 1):
        if alvo and ts[p:p + len(alvo)] == alvo:
            return " ".join(_nu(w) for w in pals[ws[p]:ws[p + len(alvo) - 1] + 1])
    return None


def de_resposta(c: dict[str, Any], pals: list[dict], i: int, j: int) -> dict[str, Any]:
    """Confere a IA: nome que não foi dito sai; o resto passa pelo resolvedor. Sem resposta aproveitável, valem as regras."""
    trecho = pals[i:j + 1]
    base = da_fala(trecho, pals[:i])
    lugares, pendencias = [], []
    for x in c.get("lugares") or []:
        if not isinstance(x, dict):
            continue
        falado = _trecho(str(x.get("nome") or ""), trecho)
        if falado is None:
            continue
        try:
            lugares.append(_lugar(gg.resolver(falado, str(x.get("nivel") or "") or None, str(x.get("pais") or "") or None), falado))
        except gg.LugarNaoResolvido as exc:
            pendencias.append(_pendencia(falado, exc.motivo, str(exc), exc.opcoes))
    if not lugares and not pendencias:
        return base
    return normalizar({"acao": c.get("acao") or ACAO_PADRAO, "lugares": lugares, "pendencias": pendencias})


# ---- plano para o mapa ---------------------------------------------------------------------------------------
def _tempo(lugar: dict, palavras: list[dict], inicio: float) -> float | None:
    """O segundo do clip em que o nome é dito; None se o trecho saiu num corte interno."""
    alvo = gg.normalizar(lugar["falado"]).split()
    ts, ws = _tokens(palavras)
    n = 0
    for p in range(len(ts) - len(alvo) + 1):
        if alvo and ts[p:p + len(alvo)] == alvo:
            n += 1
            if n == int(lugar.get("ocorrencia") or 1):
                return round(inicio + float(palavras[ws[p]]["inicio"]), 3)
    return None


def _cenas_de_arte(cenas: list[dict]) -> list[dict]:
    return sorted((c for c in cenas if c["params"].get("cena") == "arte" and c["params"].get("corte")), key=lambda x: float(x["inicio"]))


def plano(cenas: list[dict], duracao: float) -> dict[str, Any]:
    """Os eventos (quando cada lugar acende e apaga), os quadros da câmera e os avisos do clip."""
    eventos: list[dict[str, Any]] = []
    avisos: list[str] = []
    for n, c in enumerate(_cenas_de_arte(cenas)):
        ct, ini = c["params"]["corte"], float(c["inicio"])
        avisos += [p["mensagem"] for p in ct.get("pendencias", [])]
        for x in ct.get("lugares", []):
            e = gg.por_id(x["nivel"], x["id"])
            t = _tempo(x, c["palavras"], ini) if "palavras" in c else round(ini + 0.1, 3)
            if e is None or t is None:
                avisos.append(f"“{x['falado']}” saiu do mapa: o nome não está mais na fala do corte.")
                continue
            eventos.append({"t": t, "tf": duracao + 1.0, "cena": n, "acao": ct.get("acao", ACAO_PADRAO), "id": e.id, "nivel": e.nivel, "pais": e.pais,
                            "nome": x["falado"], "desc": x.get("descricao") or gg.descricao(e), "anc": gg.ancora(e), "_caixa": gg.enquadramento(e)})
    eventos.sort(key=lambda v: v["t"])
    for k, e in enumerate(eventos):  # um lugar fica aceso até a próxima cena com lugar; o continente cede ao que é citado dentro dele
        prox = next((o["t"] for o in eventos[k + 1:] if o["cena"] != e["cena"] or (e["nivel"] == "continente" and o["nivel"] != "continente")), None)
        if prox is not None:
            e["tf"] = prox
    quadros: list[dict[str, Any]] = []
    for e in eventos:
        ativos = [o["_caixa"] for o in eventos if o["t"] <= e["t"] < o["tf"]]
        if e["acao"] == "destacar" and quadros:
            ativos.append(quadros[-1]["c"])
        quadros.append({"t": e["t"], "c": gg.juntar(ativos)})
    for e in eventos:
        del e["_caixa"], e["cena"], e["acao"]
    return {"eventos": eventos, "quadros": quadros, "avisos": list(dict.fromkeys(avisos))}


def avisos(cenas: list[dict], duracao: float) -> list[str]:
    return plano(cenas, duracao)["avisos"]


@lru_cache(maxsize=1)
def _paises() -> tuple[dict, ...]:
    return tuple({"id": e.id, "a": gg.aneis_planos(e)} for e in gg.entidades() if e.nivel == "pais")


def _dados_mapa(eventos: list[dict]) -> dict[str, Any]:
    """Só vai junto o que a câmera pode precisar: a terra toda, as subdivisões dos países citados e os continentes citados."""
    pais_das_subs = sorted({e["pais"] for e in eventos if e["nivel"] == "subdivisao"})
    subs = {p: [{"id": e.id, "a": gg.aneis_planos(e)} for e in gg.entidades() if e.nivel == "subdivisao" and e.pais == p] for p in pais_das_subs}
    conts = {i: gg.aneis_planos(gg.por_id("continente", i)) for i in sorted({e["id"] for e in eventos if e["nivel"] == "continente"})}
    return {"paises": list(_paises()), "subdivisoes": subs, "continentes": conts}


def _extras(camada: Any, cenas: list[dict]) -> tuple[str, str]:
    arte = [c for c in cenas if c["params"].get("cena") == "arte"]
    par = camada.ctx(arte[0]["params"] if arte else {}, 0, 1, 0, 1, [], None).par
    pl = plano(cenas, camada.duracao)
    cfg = {"estilo": SLUG, "duracao": camada.duracao, "par": par, "geo": camada.geo.para_js() if camada.geo is not None else None,
           "eventos": pl["eventos"], "quadros": pl["quadros"], **_dados_mapa(pl["eventos"])}
    dados = json.dumps(cfg, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    js = (_dados("geo") / "geo.js").read_text(encoding="utf-8")
    three = maquete3d.caminho_three()
    if three is None or par.get("leve"):  # sem three.js, ou a alternativa leve: o mapa plano em canvas 2D
        return ('<canvas id="geo2d"></canvas><div id="rotulos3d"></div><div id="relogio3d"></div>', f"<script>window.GEO = {dados};</script>\n<script>{js}</script>")
    js3d = (_dados("geo") / "geo3d.js").read_text(encoding="utf-8")
    return ('<canvas id="geo3d"></canvas><canvas id="geo2d"></canvas><div id="rotulos3d"></div><div id="relogio3d"></div>',
            f"<script>window.GEO = {dados};</script>\n<script>{three.read_text(encoding='utf-8')}</script>\n<script>{js3d}</script>\n<script>{js}</script>")


CSS = CSS_CORTES + """
#geo2d, #geo3d { position: absolute; left: 0; top: var(--topo); width: 100%; height: var(--alt); }
.rot3 b { display: block; font-weight: inherit; text-transform: uppercase; }
.rot3 small { display: block; font-size: .56em; line-height: 1.25; color: var(--suave); }
.geo-credito { position: absolute; left: 0; top: 0; font-family: var(--f-corpo); font-size: calc(var(--u) * 19); color: var(--suave); white-space: nowrap; }
"""


def cena(c: Ctx) -> str:
    return ""  # o mapa é um só para o clip inteiro: a cena marca o tempo, quem desenha é o geo.js


def fundo(c: Ctx) -> str:
    return retangulo(0, 0, c.W, c.H, "var(--fundo)")


class DirecaoGeo:
    """`sempre`: o mapa não tem versão sem ele; em `leve`, o geo.js só corta a câmera em vez de voar."""

    tela_cheia = True
    sempre = True

    def __init__(self) -> None:
        self.cena, self.fundo, self.css, self.extras = cena, fundo, CSS, _extras


DIRECOES = {SLUG: DirecaoGeo()}
