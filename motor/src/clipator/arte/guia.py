"""A DA que guia o corte: o estilo escolhe a direção de arte, o canal ajusta só a marca.

Quem manda é o estilo. No cabeçalho dele, `arte:` diz qual DA usar:

    arte: documental                      # um predefinido (ou um predefinido pessoal)
    arte: canal                           # a DA própria do canal, em arte/direcao.yaml
    arte: {herda: manchete, cenas: {por_minuto: 8}}   # um predefinido com ajustes do próprio estilo

O canal não troca o jeito do estilo; ele só põe a marca por cima, num arquivo curto `arte/marca.yaml`:

    cores: {primaria: "#E4002B", destaque: "#FFC400"}
    fontes: {titulo: Anton, corpo: Inter}
    logo: marca/logo.png
    assinatura: "@meucanal"

Se a cor da marca não tiver contraste com o fundo da DA do estilo, ela é escurecida ou clareada só o
necessário (e isso é avisado), para o corte continuar legível.

Na geração do corte, a DA entra em três lugares:
1. `texto_para_ia`: o que a IA lê ao planejar as telas (tom, tipos de cena, ritmo, limites de texto, regras);
2. `filtrar_cenas`: o Clipator confere a resposta (tipos evitados, intervalo, teto por minuto, duração, texto);
3. o render: ficha das cenas, legenda e cartela com `da:`/`{da: true}`, tratamento de cor e carimbo.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from . import cores as C
from .carregar import (
    ARQUIVO,
    ErroDA,
    Resolvida,
    _ler_yaml,
    _mensagem_pydantic,
    achar_herdado,
    cadeia,
    mesclar,
    pasta_do_canal,
    resolver,
)
from .esquema import Posicao, _No

ARQUIVO_MARCA = "marca.yaml"
CORES_DA_MARCA = ("primaria", "secundaria", "destaque")
CONTRASTE_MARCA = 3.0  # primária e destaque sobre o fundo: o mínimo de grafismo e texto grande


class Marca(_No):
    """`arte/marca.yaml` do canal: o que o canal pode sobrepor à DA de qualquer estilo."""

    cores: dict[str, str] = Field(default_factory=dict, description="primaria, secundaria e destaque da marca (hex)")
    fontes: dict[str, str] = Field(default_factory=dict, description="papel → família (titulo, subtitulo, corpo, "
                                   "dados, legenda); 'corpo' vale também para dados e legenda se eles não vierem")
    logo: str | None = None
    assinatura: str | None = None
    posicao_logo: Posicao | None = None
    marca_dagua: bool | None = None
    opacidade_logo: float | None = Field(None, ge=0.05, le=1)
    respeitar_contraste: bool = Field(True, description="Ajusta a cor da marca se ela some no fundo do estilo")


# ---- de onde vem a DA ----------------------------------------------------------------------------------

def referencia_do_estilo(estilo: Any) -> Any:
    """O valor de `arte:` no estilo (None se ele não pede DA). `direcao.ficha: canal` conta como `arte: canal`."""
    extra = getattr(estilo, "model_extra", None) or {}
    ref = extra.get("arte")
    if ref in (None, "", False):
        direcao = getattr(estilo, "direcao", None)
        if getattr(direcao, "ficha", None) in ("canal", "da"):
            return "canal"
        if usa_tokens(estilo):  # `da:primaria` ou `legenda: {da: true}` sem dizer qual DA: a base
            return "base"
        return None
    return ref


def usa_tokens(estilo: Any) -> bool:
    try:
        texto = estilo.model_dump_json().replace(" ", "")
    except Exception:  # noqa: BLE001
        return False
    return '"da:' in texto or '"da":true' in texto


def ler_marca(canal_path: Path | None) -> Marca | None:
    if canal_path is None:
        return None
    arq = pasta_do_canal(canal_path) / ARQUIVO_MARCA
    if not arq.exists():
        return None
    try:
        return Marca.model_validate(_ler_yaml(arq) or {})
    except ValidationError as exc:
        raise ErroDA(f"{arq.name} do canal:\n" + _mensagem_pydantic(exc)) from exc


def _dados_da_referencia(ref: Any, canal_path: Path | None) -> tuple[dict[str, Any], list[str], Path | None]:
    if isinstance(ref, str):
        if ref == "canal":
            if canal_path is None:
                raise ErroDA("o estilo pede `arte: canal`, mas não há canal")
            arq = pasta_do_canal(canal_path) / ARQUIVO
            if not arq.exists():
                raise ErroDA("o estilo pede `arte: canal`, mas o canal ainda não tem arte/direcao.yaml "
                             "(`clipator arte criar CANAL --base <predefinido>`)")
        else:
            arq = achar_herdado(ref, pasta_do_canal(canal_path) if canal_path else None)
        dados, anc = cadeia(arq)
        return dados, anc, arq
    if isinstance(ref, dict):
        proprio = dict(ref)
        base = str(proprio.pop("herda", None) or "base")
        dados_base, anc = _dados_da_referencia(base, canal_path)[:2]
        return mesclar(dados_base, proprio), anc, None
    raise ErroDA("`arte:` no estilo é o nome de um predefinido, `canal` ou um mapa com `herda` e ajustes")


def _aplicar_marca(dados: dict[str, Any], marca: Marca) -> tuple[dict[str, Any], list[str]]:
    notas: list[str] = []
    paleta = dict((dados.get("cor") or {}).get("paleta") or {})
    fundo = paleta.get("fundo")
    for nome, hexa in marca.cores.items():
        if nome not in CORES_DA_MARCA:
            notas.append(f"marca.yaml: a cor “{nome}” não é da marca (só {', '.join(CORES_DA_MARCA)}); ignorada")
            continue
        if not C.e_hex(hexa):
            notas.append(f"marca.yaml: “{hexa}” não é hex; ignorada")
            continue
        hexa = C.normalizar_hex(hexa)
        if marca.respeitar_contraste and fundo and nome != "secundaria" and C.contraste(hexa, fundo) < CONTRASTE_MARCA:
            novo = C.ajustar_para_contraste(hexa, fundo, CONTRASTE_MARCA)
            notas.append(f"a cor “{nome}” da marca, {hexa}, quase some no fundo {fundo} deste estilo; "
                         f"usei {novo} (ΔE {C.delta_e(hexa, novo):.0f})")
            hexa = novo
        paleta[nome] = hexa
    ajuste: dict[str, Any] = {"cor": {"paleta": paleta}} if marca.cores else {}
    papeis_base = (dados.get("tipografia") or {}).get("papeis") or {}
    papeis: dict[str, Any] = {}
    for papel, familia in marca.fontes.items():
        if papel not in papeis_base:
            notas.append(f"marca.yaml: a DA não tem o papel “{papel}”; fonte ignorada")
            continue
        papeis[papel] = {"familia": familia}
    if "corpo" in marca.fontes:
        for papel in ("dados", "legenda"):
            if papel in papeis_base and papel not in marca.fontes:
                papeis[papel] = {"familia": marca.fontes["corpo"]}
    if papeis:
        ajuste["tipografia"] = {"papeis": papeis}
    m = {k: v for k, v in marca.model_dump().items()
         if k in ("logo", "assinatura", "posicao_logo", "marca_dagua", "opacidade_logo") and v is not None}
    if m:
        ajuste["marca"] = m
    return mesclar(dados, ajuste), notas


def da_do_estilo(estilo: Any, canal_path: Path | None = None) -> tuple[Resolvida | None, list[str]]:
    """(a DA que este estilo usa, já com a marca do canal; avisos). (None, []) se o estilo não pede DA."""
    ref = referencia_do_estilo(estilo)
    if ref is None:
        return None, []
    return da_da_referencia(ref, canal_path)


def da_da_referencia(ref: Any, canal_path: Path | None = None) -> tuple[Resolvida, list[str]]:
    """A DA de uma referência (`canal`, predefinido ou mapa), com a marca do canal por cima."""
    dados, anc, arq = _dados_da_referencia(ref, canal_path)
    notas: list[str] = []
    marca = ler_marca(canal_path)
    if marca is not None and ref != "canal":  # a DA do próprio canal já é a marca dele
        dados, notas = _aplicar_marca(dados, marca)
    dados.pop("herda", None)
    r = resolver(dados, arq if ref == "canal" else None, anc)
    if ref == "canal" and arq is not None:
        r.pasta = arq.parent
    return r, notas


# ---- o que a IA lê ao planejar as telas ---------------------------------------------------------------

_NOMES_CENA = {"titulo": "título", "numero": "número", "citacao": "citação", "lista": "lista",
               "comparacao": "comparação", "linha_do_tempo": "linha do tempo", "local": "local", "nome": "nome",
               "palavra": "palavra forte", "alerta": "alerta"}
_ENTRADAS = {"sobe": "sobe de leve", "desliza": "desliza de lado", "escala": "cresce do centro",
             "mascara": "é revelada por máscara", "fade": "aparece em fade", "digita": "é digitada letra a letra"}


def texto_para_ia(r: Resolvida, limite: int = 2200) -> str:
    """O guia da DA para o pedido das cenas: tom, tipos, ritmo e limites de texto. Sem hex: a IA não pinta."""
    da, ce = r.da, r.da.cenas
    ls = [f"Direção de arte deste estilo: {da.nome or 'sem nome'}."]
    if da.conceito.frase:
        ls.append(da.conceito.frase)
    if ce.tom:
        ls.append(f"Tom das telas: {ce.tom}")
    if da.conceito.palavras_chave:
        ls.append("Palavras-chave do visual: " + ", ".join(da.conceito.palavras_chave) + ".")
    if ce.preferir:
        ls.append("Prefira estes tipos de cena, nesta ordem: " + ", ".join(ce.preferir) + ".")
    if ce.evitar:
        ls.append("Não use estes tipos (serão descartados): " + ", ".join(ce.evitar) + ".")
    def n(x: float) -> str:
        return f"{x:g}".replace(".", ",")

    ls.append(f"Ritmo: no máximo {n(ce.por_minuto)} cenas por minuto e uma a cada {n(ce.intervalo)} s no mínimo; "
              f"cada cena dura de {n(ce.duracao[0])} a {n(ce.duracao[1])} s.")
    ls.append("A primeira cena é um título-gancho nos primeiros segundos." if ce.abrir_com_titulo
              else "Não abra com título-gancho; comece pelo contexto.")
    ls.append(f"Texto: título ou palavra até {ce.palavras_titulo} palavras; rótulo, citação ou alerta até "
              f"{ce.palavras_rotulo}; lista até {ce.itens_lista} itens de até {ce.palavras_item} palavras.")
    mov = f"Movimento: cada tela {_ENTRADAS.get(da.movimento.entrada, da.movimento.entrada)}"
    ls.append(mov + (". " + " ".join(da.movimento.principios[:2]) if da.movimento.principios else "."))
    if da.conceito.faca:
        ls.append("Faça: " + " ".join(f"• {x}" for x in da.conceito.faca[:4]))
    if da.conceito.nao_faca:
        ls.append("Não faça: " + " ".join(f"• {x}" for x in da.conceito.nao_faca[:4]))
    if ce.regras:
        ls.append("Regras deste estilo: " + " ".join(f"• {x}" for x in ce.regras[:6]))
    texto = "\n".join(ls)
    return texto if len(texto) <= limite else texto[: limite - 1].rsplit(" ", 1)[0] + "…"


# ---- o que o Clipator confere na resposta ---------------------------------------------------------------

def _palavras(s: Any) -> int:
    return len(str(s or "").split())


def _texto_longo(p: dict[str, Any], ce) -> str | None:
    tipo = p.get("cena")
    if tipo in ("titulo", "palavra") and _palavras(p.get("texto")) > ce.palavras_titulo:
        return f"{_NOMES_CENA.get(tipo, tipo)} com {_palavras(p.get('texto'))} palavras (máximo {ce.palavras_titulo})"
    for campo in ("rotulo", "texto") if tipo in ("numero", "citacao", "alerta", "nome", "local") else ("rotulo",):
        if _palavras(p.get(campo)) > ce.palavras_rotulo * (2 if tipo == "citacao" and campo == "texto" else 1):
            return f"{_NOMES_CENA.get(tipo, tipo)} com {campo} longo demais"
    return None


def filtrar_cenas(cenas: list[Any], r: Resolvida, dur: float) -> tuple[list[Any], list[str]]:
    """As cenas que respeitam a DA (copiadas, com duração e listas ajustadas) e o porquê de cada descarte.

    Funciona com `direcao.Cena` ou qualquer objeto com `inicio`, `fim` e `params` (com a chave `cena`).
    """
    ce = r.da.cenas
    descartes: list[str] = []
    candidatas = []
    for c in sorted(cenas, key=lambda c: c.inicio):
        p = dict(c.params or {})
        tipo = p.get("cena")
        if tipo in ce.evitar:
            descartes.append(f"{c.inicio:.1f}s: {_NOMES_CENA.get(tipo, tipo)} não combina com esta DA")
            continue
        motivo = _texto_longo(p, ce)
        if motivo:
            descartes.append(f"{c.inicio:.1f}s: {motivo}")
            continue
        if tipo in ("lista", "linha_do_tempo") and isinstance(p.get("itens"), list):
            p["itens"] = p["itens"][: ce.itens_lista]
        ini = max(0.0, float(c.inicio))
        fim = min(dur, max(float(c.fim), ini + ce.duracao[0]), ini + ce.duracao[1])
        if fim - ini < min(ce.duracao[0], 0.8):
            descartes.append(f"{c.inicio:.1f}s: sem tempo para a cena no fim do corte")
            continue
        candidatas.append((c, p, ini, fim))
    teto = max(1, math.floor(dur / 60 * ce.por_minuto + 0.5))
    # prioridade: o que a DA prefere, na ordem dela; depois a prioridade que veio de quem planejou
    ordem = {t: i for i, t in enumerate(ce.preferir)}

    def chave(item):
        c, p, ini, _ = item
        gancho = ce.abrir_com_titulo and p.get("cena") == "titulo" and ini < 3.0
        return (-1 if gancho else ordem.get(p.get("cena"), len(ordem)), -getattr(c, "prioridade", 0), ini)

    escolhidas: list[tuple] = []
    for item in sorted(candidatas, key=chave):
        _, _, ini, fim = item
        if len(escolhidas) >= teto:
            descartes.append(f"{ini:.1f}s: passa do teto de {ce.por_minuto:g} cenas por minuto")
            continue
        if any(abs(ini - e[2]) < ce.intervalo or (ini < e[3] and e[2] < fim) for e in escolhidas):
            descartes.append(f"{ini:.1f}s: perto demais de outra cena (mínimo {ce.intervalo:g} s)")
            continue
        escolhidas.append(item)
    out = []
    for c, p, ini, fim in sorted(escolhidas, key=lambda e: e[2]):
        if hasattr(c, "model_copy"):
            out.append(c.model_copy(update={"inicio": round(ini, 3), "fim": round(fim, 3), "params": p}))
        else:
            c.inicio, c.fim, c.params = round(ini, 3), round(fim, 3), p
            out.append(c)
    return out, descartes


def resumo(r: Resolvida, notas: list[str] | None = None) -> dict[str, Any]:
    """Para a CLI e o MCP: o que o estilo vai usar."""
    return {"da": r.da.nome, "primaria": r.cor("primaria"), "fundo": r.cor("fundo"),
            "fontes": {k: v.familia for k, v in r.da.tipografia.papeis.items()},
            "cenas": r.da.cenas.model_dump(), "guia_ia": texto_para_ia(r), "avisos": notas or []}
