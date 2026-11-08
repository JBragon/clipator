"""A geografia real do estilo Geo em Cena: camadas Natural Earth locais, nomes, ids, país pai e enquadramento.

Adaptado de scripts/geografia.py e scripts/cartografia.py do pacote "mapa-geografico-real" (AGPL-3.0-or-later).
Nada aqui inventa geometria: o que não resolve para uma entidade da base vira erro explicado, nunca uma silhueta. Sem rede.
Os anéis ficam em longitude contínua (não saltam no antimeridiano); ilhas e buracos são preservados.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

from ..workspace import _dados

CAMADAS = ("paises", "subdivisoes", "continentes")
CONTINENTES = {"south-america": "América do Sul", "north-america": "América do Norte", "europe": "Europa", "africa": "África",
               "asia": "Ásia", "oceania": "Oceania", "antarctica": "Antártida"}
NIVEIS = {"pais": "pais", "estado": "subdivisao", "uf": "subdivisao", "subdivisao": "subdivisao", "provincia": "subdivisao", "continente": "continente"}
CIDADE = {"cidade", "municipio", "capital"}
SEM_CODIGO = ("-99", "-1")
TIPOS = {"State": "Estado", "Province": "Província", "Federal District": "Distrito federal", "Territory": "Território", "Prefecture": "Prefeitura",
         "Region": "Região", "Department": "Departamento", "Metropolitan department": "Departamento", "Overseas department": "Departamento ultramarino",
         "District": "Distrito", "Autonomous Region": "Região autônoma", "Autonomous region": "Região autônoma", "County": "Condado", "Municipality": "Município"}


class LugarNaoResolvido(ValueError):
    """`motivo`: ausente, ambiguo, confirmar (subdivisão sem contexto) ou cidade (não há camada municipal). `opcoes`: as entidades candidatas."""

    def __init__(self, mensagem: str, motivo: str, opcoes: list["Entidade"] | None = None) -> None:
        super().__init__(mensagem)
        self.motivo, self.opcoes = motivo, opcoes or []


def normalizar(s: Any) -> str:
    n = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", n).split())


@lru_cache(maxsize=None)
def camada(nome: str) -> tuple[dict, ...]:
    if nome not in CAMADAS:
        raise ValueError(f"Camada desconhecida: {nome}")
    return tuple(json.loads(gzip.decompress((_dados("geo") / f"{nome}.geojson.gz").read_bytes()))["features"])


@lru_cache(maxsize=1)
def fontes() -> dict[str, Any]:
    return json.loads((_dados("geo") / "FONTES.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def apelidos() -> dict[str, Any]:
    return json.loads((_dados("geo") / "apelidos.json").read_text(encoding="utf-8"))


def hash_dados() -> str:
    """Muda quando a base muda (entra na chave das amostras): os hashes declarados em FONTES.json mais os apelidos."""
    h = hashlib.sha256()
    for f in fontes()["fontes"]:
        h.update(f["sha256_incluido"].encode())
    h.update((_dados("geo") / "apelidos.json").read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


@dataclass(frozen=True, eq=False)
class Entidade:
    id: str
    nome: str
    nivel: str  # continente, pais ou subdivisao
    features: tuple[dict, ...]
    pais: str | None = None
    tipo: str = ""
    iso: str | None = None
    nomes: frozenset[str] = field(default_factory=frozenset)  # o que pode ser dito
    codigos: frozenset[str] = field(default_factory=frozenset)  # ids e ISO: só valem em busca explícita, nunca na fala

    def resumo(self) -> dict[str, Any]:
        return {"id": self.id, "nome": self.nome, "nivel": self.nivel, "pais": self.pais, "descricao": descricao(self)}


@lru_cache(maxsize=1)
def entidades() -> tuple[Entidade, ...]:
    ap = apelidos()
    out: list[Entidade] = []
    for id_, nome in CONTINENTES.items():
        fs = tuple(f for f in camada("continentes") if f["properties"]["continente"] == id_)
        out.append(Entidade(id_, nome, "continente", fs, nomes=frozenset({normalizar(nome), *map(normalizar, ap["continentes"].get(id_, []))}),
                            codigos=frozenset({normalizar(id_)})))
    # Convenção explícita: "América" sozinha é o conjunto Norte + Sul, não um oitavo continente.
    fs = tuple(f for f in camada("continentes") if f["properties"]["continente"] in ("north-america", "south-america"))
    out.append(Entidade("americas", "Américas (Norte e Sul)", "continente", fs, nomes=frozenset({"america", "americas"}), codigos=frozenset({"americas"})))
    for f in camada("paises"):
        a = f["properties"]
        nomes = {normalizar(a[k]) for k in ("nome", "nome_en") if a.get(k)} | {normalizar(s) for s in ap["paises"].get(a["id"], [])}
        cods = {normalizar(a[k]) for k in ("id", "iso2", "iso3") if a.get(k) and a[k] not in SEM_CODIGO}
        out.append(Entidade(a["id"], a["nome"], "pais", (f,), tipo=a.get("tipo_administrativo") or "", iso=a.get("iso3"), nomes=frozenset(nomes), codigos=frozenset(cods)))
    for f in camada("subdivisoes"):
        a = f["properties"]
        nomes = {normalizar(a[k]) for k in ("nome", "nome_original") if a.get(k)} | {normalizar(s) for s in (a.get("nome_alternativo") or "").split("|") if s.strip()}
        nomes |= {normalizar(s) for s in ap["subdivisoes"].get(a["id"], [])}
        cods = {normalizar(a[k]) for k in ("id", "iso") if a.get(k) and a[k] not in SEM_CODIGO}
        out.append(Entidade(a["id"], a["nome"], "subdivisao", (f,), pais=a["pais"], tipo=a.get("tipo") or "", iso=a.get("iso"), nomes=frozenset(nomes), codigos=frozenset(cods)))
    return tuple(out)


@lru_cache(maxsize=1)
def _indices() -> tuple[dict[str, list[Entidade]], dict[str, list[Entidade]], dict[tuple[str, str], Entidade]]:
    por_nome: dict[str, list[Entidade]] = {}
    por_codigo: dict[str, list[Entidade]] = {}
    ids: dict[tuple[str, str], Entidade] = {}
    for e in entidades():
        ids[(e.nivel, e.id)] = e
        for n in e.nomes:
            por_nome.setdefault(n, []).append(e)
        for n in e.codigos:
            por_codigo.setdefault(n, []).append(e)
    return por_nome, por_codigo, ids


def nomes_falados() -> dict[str, list[Entidade]]:
    return _indices()[0]


def por_id(nivel: str, id_: str) -> Entidade | None:
    return _indices()[2].get((nivel, id_))


def nome_do_pais(id_: str | None) -> str:
    e = por_id("pais", id_ or "")
    return e.nome if e else ""


def descricao(e: Entidade) -> str:
    """A linha sob o nome: diz o que aquele polígono é, para a UF nunca passar por município."""
    if e.nivel == "continente":
        return "Américas" if e.id == "americas" else "Continente"
    if e.nivel == "pais":
        return "País" if "ountry" in e.tipo else "Território"
    tipo = "Unidade federativa" if e.pais == "BRA" else TIPOS.get(e.tipo, "Subdivisão")
    return f"{tipo} · {nome_do_pais(e.pais)}"


def sem_homonimo_interno(ents: list[Entidade]) -> list[Entidade]:
    """México, o país, e México, o estado dentro dele: a menção sem contexto é o país. Geórgia não cai aqui, porque o estado é de outro país."""
    conts = [e for e in ents if e.nivel == "continente"]
    if len(conts) == 1:
        return conts  # Antártida: o continente e o território da camada política são o mesmo lugar
    paises = [e for e in ents if e.nivel == "pais"]
    if len(paises) == 1 and all(e.nivel == "subdivisao" and e.pais == paises[0].id for e in ents if e is not paises[0]):
        return paises
    return ents


def resolver(termo: str, nivel: str | None = None, pais: str | None = None) -> Entidade:
    """A entidade do nome, id ou código. Ausente, ambígua ou sem contexto levanta LugarNaoResolvido, com as opções."""
    n = None
    if nivel:
        chave = normalizar(nivel)
        if chave in CIDADE:
            raise LugarNaoResolvido(f"“{termo}” como cidade: não há camada municipal, então nenhum polígono é mostrado.", "cidade")
        n = NIVEIS.get(chave)
        if n is None:
            raise LugarNaoResolvido(f"Nível não suportado: {nivel}.", "ausente")
    pai = resolver(pais, "pais").id if pais else None
    chave = normalizar(termo)
    por_nome, por_codigo, _ = _indices()
    achados = list(dict.fromkeys([*por_nome.get(chave, []), *por_codigo.get(chave, [])]))
    achados = [e for e in achados if (n is None or e.nivel == n) and (pai is None or (e.nivel == "subdivisao" and e.pais == pai))]
    if not achados:
        raise LugarNaoResolvido(f"“{termo}” não está na base cartográfica (nível {n or 'qualquer'}, país {pai or 'qualquer'}).", "ausente")
    if n is None and pai is None:
        achados = sem_homonimo_interno(achados)
    if len(achados) > 1:
        raise LugarNaoResolvido(f"“{termo}” é ambíguo: " + "; ".join(f"{e.nome} ({descricao(e)})" for e in achados[:6]) + ".", "ambiguo", achados)
    e = achados[0]
    if e.nivel == "subdivisao" and n is None and pai is None and chave not in por_codigo:
        raise LugarNaoResolvido(f"“{termo}”: confirme que a fala é sobre a subdivisão de {nome_do_pais(e.pais)}, não sobre uma cidade de mesmo nome.", "confirmar", [e])
    return e


# ---- geometria -------------------------------------------------------------------------------------------------
def poligonos(geo: dict) -> list[list[list[list[float]]]]:
    if geo["type"] == "Polygon":
        return [geo["coordinates"]]
    if geo["type"] == "MultiPolygon":
        return geo["coordinates"]
    raise ValueError(f"Geometria não poligonal: {geo['type']}")


def continuo(anel: list[list[float]]) -> list[list[float]]:
    """O anel em longitude contínua: um salto de mais de 180° é a passagem pelo antimeridiano, não uma volta ao mundo."""
    out, off = [], 0.0
    ant = None
    for p in anel:
        if ant is not None:
            d = p[0] - ant
            if d > 180:
                off -= 360
            elif d < -180:
                off += 360
        ant = p[0]
        out.append([p[0] + off, p[1]])
    return out


def _area(anel: list[list[float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(anel, anel[1:]))) / 2


def _cobertura(intervalos: Iterable[tuple[float, float]]) -> tuple[float, float]:
    """(oeste, leste) do menor arco de longitude que cobre os intervalos: Fiji não vira uma faixa de 360°."""
    norm = sorted(((a + 180) % 360 - 180, b - a) for a, b in intervalos)
    if not norm:
        raise ValueError("Sem geometria para enquadrar.")
    grupos: list[list[float]] = []
    for a, w in norm + [(a + 360, w) for a, w in norm]:  # duas voltas: o arco pode atravessar o antimeridiano
        if grupos and a <= grupos[-1][1]:
            grupos[-1][1] = max(grupos[-1][1], a + w)
        else:
            grupos.append([a, a + w])
    vaos = [(h[0] - g[1], h[0]) for g, h in zip(grupos, grupos[1:]) if h[0] - g[1] > 0]
    if not vaos:
        return -180.0, 180.0  # cobre o mundo todo
    maior, oeste = max(vaos)
    while oeste >= 180:
        oeste -= 360
    return oeste, oeste + 360 - maior


def _caixas(features: Iterable[dict]) -> list[tuple[float, float, float, float, float]]:
    """(oeste, sul, leste, norte, área) de cada polígono, pelo anel externo."""
    out = []
    for f in features:
        for pol in poligonos(f["geometry"]):
            a = continuo(pol[0])
            xs, ys = [p[0] for p in a], [p[1] for p in a]
            out.append((min(xs), min(ys), max(xs), max(ys), _area(a)))
    return out


def juntar(caixas: Iterable[tuple[float, ...]]) -> tuple[float, float, float, float]:
    cs = list(caixas)
    o, l = _cobertura((c[0], c[2]) for c in cs)
    return o, min(c[1] for c in cs), l, max(c[3] for c in cs)


def enquadramento(e: Entidade) -> tuple[float, float, float, float]:
    """A caixa em que a câmera mostra a entidade. Espalhada pelo mundo (EUA, Oceania), vale o corpo principal; ilhas seguem pintadas onde estão."""
    # Os grupos de ilhas da camada física são polígonos que incluem oceano: não dizem onde está a terra do continente.
    corpo = [f for f in e.features if f["properties"].get("classe") != "Island group"] or list(e.features)
    cs = _caixas(corpo if e.nivel == "continente" else e.features)
    tudo = juntar(cs)
    if tudo[2] - tudo[0] <= 40:
        return tudo
    maior = max(c[4] for c in cs)
    return juntar(c for c in cs if c[4] >= maior * 0.5)


def _no_anel(a: list[list[float]], x: float, y: float) -> bool:
    d = False
    for p, q in zip(a, a[1:]):
        if (p[1] > y) != (q[1] > y) and x < (q[0] - p[0]) * (y - p[1]) / (q[1] - p[1]) + p[0]:
            d = not d
    return d


def contem(e: Entidade, lon: float, lat: float) -> bool:
    """O ponto está na área da entidade? Par-ímpar por polígono, com buracos e ilhas."""
    for f in e.features:
        for pol in poligonos(f["geometry"]):
            dentro = False
            for anel in pol:
                a = continuo(anel)
                if any(_no_anel(a, lon + k, lat) for k in (-360, 0, 360)):
                    dentro = not dentro
            if dentro:
                return True
    return False


def ancora(e: Entidade) -> tuple[float, float]:
    """Onde o rótulo se prende: o ponto de rótulo da base ou, nos continentes, o centro do maior polígono. O destaque é sempre o polígono."""
    r = e.features[0]["properties"].get("rotulo")
    if r:
        return float(r[0]), float(r[1])
    pol = max((continuo(p[0]) for f in e.features for p in poligonos(f["geometry"])), key=_area)
    xs, ys = [p[0] for p in pol], [p[1] for p in pol]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def aneis_planos(e: Entidade) -> list[list[float]]:
    """Todos os anéis (externos e buracos), [lon, lat, lon, lat, ...], com as coordenadas da base."""
    return [[v for p in continuo(anel) for v in p[:2]] for f in e.features for pol in poligonos(f["geometry"]) for anel in pol]
