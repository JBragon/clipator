"""Modo curta das cinco direções guiadas pela fala: cada frase vira um PLANO de um curta-metragem.

Antes, o clip inteiro era um mundo só (um diorama no vazio) e as frases só acrescentavam peças. Agora cada cena tem:

- **cenário**: o lugar de que a fala trata (cidade, cozinha, escola, praia, espaço...), montado em three.js com o material
  do estilo. Sem lugar novo na frase, o lugar anterior continua e o plano muda, como num filme;
- **personagens** com uma **ação** (andar, correr, falar, pensar, comemorar, cair...), animada em poses;
- **situação** (festa, ideia, dúvida, dinheiro, tempo, perigo, amor...), um efeito que dá sentido ao que é dito;
- **momento** e **clima** (noite, chuva, neve) quando a fala diz;
- **plano**, **movimento** de câmera e **transição** (corte, fade, cortina, zoom) para a montagem.

Sem IA, um léxico (dados/curta/lexico.json) lê a frase e o encadeamento varia os planos. Com IA, o adaptador lê a fala
inteira, as notas da pesquisa de referências (artes/pesquisa.py) e devolve esses campos por schema, só com valores das
listas. A interpretação (o lugar, a situação) pode ir além da palavra dita, mas texto na tela continua sendo só o que foi
dito: o nome do lugar e dos objetos sai da fala, nunca da IA. Os tons da pesquisa ajustam o cenário ao lugar real dentro
da paleta do estilo. Cena sem `curta` (projeto antigo) segue no motor de um mundo só (cortes.py/motor.js).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from ..workspace import _dados
from . import tokens

VERSAO = 3  # entra no hash das amostras destas cinco, junto com curta.js e o léxico
MAX_PERSONAGENS = 3
CAMPOS = ("cenario", "lugar", "momento", "clima", "personagens", "situacao", "plano", "movimento", "transicao", "aderecos", "tons", "nota_visual",
          "objetos", "placa", "roteiro", "tela", "destaque", "destaque_sub")
TELAS = ("dividida", "video")  # o plano ilustrado (vídeo + animação) ou só o vídeo em tela cheia, quando não há o que mostrar
TIPOS_ATOR = ("pessoa", "robo")
TIPOS_ENTIDADE = ("pessoa", "empresa", "produto", "tecnologia", "organizacao")  # o mesmo de artes/pesquisa.py
# palavras que nunca viram placa nem nome na tela: dizem quem fala, não o que se vê
_VAZIAS_TELA = set("eu tu ele ela nos vos eles elas voce voces gente agente isso isto aquilo esse essa este esta aqui ali la coisa coisas "
                   "cara pessoal galera mano tipo ne entao ai dai assim".split())


def _vazio_na_tela(texto: str) -> bool:
    ts = [t for t in tokens(texto) if t not in ("a", "o", "as", "os", "um", "uma")]
    return not ts or all(t in _VAZIAS_TELA for t in ts)
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ARQ_REF = re.compile(r"^pesquisa/imagens/[0-9a-f]{16}\.(png|jpg)$")


def _referencia(r: Any) -> dict[str, Any] | None:
    """Imagem real de algo citado (artes/pesquisa.py: imagens_reais): só arquivo da pasta de pesquisa do clip."""
    if not isinstance(r, dict) or not _ARQ_REF.match(str(r.get("arquivo") or "")) or not str(r.get("termo") or "").strip():
        return None
    cr = r.get("credito") if isinstance(r.get("credito"), dict) else {}
    return {"termo": " ".join(str(r["termo"]).split())[:60], "tipo": str(r.get("tipo") or "")[:20], "nome": " ".join(str(r.get("nome") or "").split())[:40],
            "contexto": " ".join(str(r.get("contexto") or "").split())[:90], "arquivo": r["arquivo"], "logo": bool(r.get("logo")),
            "credito": {k: " ".join(str(cr.get(k) or "").split())[:120] for k in ("fonte", "licenca", "autor", "pagina")}}


@lru_cache(maxsize=1)
def vocabulario() -> dict[str, Any]:
    return json.loads((_dados("curta") / "lexico.json").read_text(encoding="utf-8"))


def listas() -> dict[str, list[str]]:
    v = vocabulario()
    return {"cenario": list(v["cenarios"]), "acao": list(v["acoes"]), "situacao": list(v["situacoes"]),
            "momento": ["", *v["momentos"]], "clima": ["", *v["climas"]], "plano": list(v["planos"]),
            "movimento": list(v["movimentos"]), "transicao": list(v["transicoes"])}


# ---- leitura da fala ---------------------------------------------------------------------------------------------
def _casa(raiz: str, ts: list[str], frase: str) -> int:
    """Posição (em palavras) da primeira palavra que casa com a raiz, ou -1. 'x=' é palavra exata; 'a b' é expressão."""
    raiz = raiz.lstrip("~")
    if " " in raiz.strip("="):
        alvo = raiz.rstrip("=")
        k = f" {frase} ".find(f" {alvo}")
        return -1 if k < 0 else f" {frase} "[:k].count(" ")
    exata = raiz.endswith("=")
    r = raiz.rstrip("=")
    for i, t in enumerate(ts):
        if (t == r) if exata else t.startswith(r):
            return i
    return -1


def _achados(dic: dict[str, Any], ts: list[str], frase: str) -> list[tuple[int, str, bool, int]]:
    """(posição, chave, implícita, tamanho da raiz) de cada chave do dicionário que aparece na frase."""
    out = []
    for chave, v in dic.items():
        melhor = None
        for raiz in (v["raizes"] if isinstance(v, dict) else v):
            p = _casa(raiz, ts, frase)
            if p >= 0 and (melhor is None or p < melhor[0]):
                melhor = (p, chave, raiz.startswith("~"), len(raiz))
        if melhor:
            out.append(melhor)
    return sorted(out)


def _primeiro(dic: dict[str, Any], ts: list[str], frase: str) -> tuple[str, int]:
    a = _achados(dic, ts, frase)
    return (a[0][1], a[0][0]) if a else ("", -1)


def _lugar(ts: list[str], frase: str) -> tuple[str, int]:
    """O lugar da frase: o último dito pelo nome (é para onde a ação vai: "acordei e fui pra cozinha"); sem nome, o sugerido."""
    a = _achados(vocabulario()["cenarios"], ts, frase)
    ditos = [x for x in a if not x[2]]
    if ditos:
        return ditos[-1][1], ditos[-1][0]
    return (a[-1][1], -1) if a else ("", -1)


def _acao(ts: list[str], frase: str) -> str:
    """Andar é o verbo mais comum e o menos informativo: qualquer outra ação dita na frase vence."""
    a = [x[1] for x in _achados(vocabulario()["acoes"], ts, frase)]
    fortes = [x for x in a if x != "andar"]
    return fortes[0] if fortes else (a[0] if a else "")


def _palavra_em(pals: list[dict], pos: int) -> str:
    if 0 <= pos < len(pals):
        return pals[pos]["texto"].strip(" ,.;:!?\"'“”()")
    return ""


def da_fala(pals: list[dict]) -> dict[str, Any]:
    """Sem IA: o que a frase diz de lugar, gente, ação, situação, hora e clima. Campos vazios o encadeamento completa."""
    v = vocabulario()
    ts = [(tokens(w["texto"]) or [""])[0] for w in pals]
    frase = " ".join(ts)
    cenario, pos = _lugar(ts, frase)
    acao = _acao(ts, frase)
    situacao, _ = _primeiro(v["situacoes"], ts, frase)
    momento, _ = _primeiro(v["momentos"], ts, frase)
    clima, _ = _primeiro(v["climas"], ts, frase)
    gente = [i for i, t in enumerate(ts) if any(_casa(r, [t], t) == 0 for r in v["pessoas"])]
    dois = any(_casa(r, ts, frase) >= 0 for r in v["duas_pessoas"])
    n = 0
    if gente or acao:
        n = 2 if dois or len({ts[i] for i in gente}) >= 2 else 1
    if situacao == "conversa":
        n = max(n, 2)
    acao = acao or ("parado" if n else "")
    pers = []
    for k in range(n):
        a = acao
        if k > 0 and acao in ("falar",) and situacao == "conversa":
            a = "parado"
        nome = _palavra_em(pals, gente[k]) if k < len(gente) else ""
        pers.append({"nome": "" if " ".join(tokens(nome)) in v["pronomes"] else nome, "acao": a})
    return normalizar({"cenario": cenario, "lugar": _palavra_em(pals, pos) if cenario else "", "momento": momento, "clima": clima,
                       "personagens": pers, "situacao": situacao or "nenhuma", "plano": "", "movimento": "", "transicao": ""})


def normalizar(c: Any) -> dict[str, Any]:
    """Só valores das listas: o que a IA ou a tela inventar fora delas vira vazio (o encadeamento completa)."""
    c = c if isinstance(c, dict) else {}
    L = listas()
    out: dict[str, Any] = {}
    for k in ("cenario", "momento", "clima", "situacao", "plano", "movimento", "transicao"):
        val = c.get(k)
        out[k] = val if isinstance(val, str) and val in L[k] else ""
    out["situacao"] = out["situacao"] or "nenhuma"
    out["lugar"] = " ".join(str(c.get("lugar") or "").split())[:40]
    if _vazio_na_tela(out["lugar"]):
        out["lugar"] = ""
    pers = []
    for k, p in enumerate((c.get("personagens") or [])[:MAX_PERSONAGENS]):
        if isinstance(p, dict):
            a = p.get("acao") if p.get("acao") in L["acao"] else "parado"
            nome = " ".join(str(p.get("nome") or "").split())[:30]
            try:
                ator = max(0, min(MAX_PERSONAGENS - 1, int(p.get("ator", k))))
            except (TypeError, ValueError):
                ator = k
            pers.append({"nome": "" if _vazio_na_tela(nome) else nome, "acao": a, "ator": ator,
                         "tipo": p.get("tipo") if p.get("tipo") in TIPOS_ATOR else "pessoa"})
    out["personagens"] = pers
    from . import cortes

    objs = []
    for o in (c.get("objetos") or [])[:3]:
        if isinstance(o, dict) and o.get("forma") in cortes.formas() and o.get("forma") not in ("pessoa",):
            rot = " ".join(str(o.get("rotulo") or "").split())[:30]
            objs.append({"forma": o["forma"], "rotulo": "" if _vazio_na_tela(rot) else rot})
    out["objetos"] = objs
    placa = " ".join(str(c.get("placa") or "").split())[:40]
    out["placa"] = "" if _vazio_na_tela(placa) else placa
    out["aderecos"] = [f for f in (c.get("aderecos") or []) if isinstance(f, str) and f in cortes.formas() and f != "pessoa"][:3]
    out["tons"] = [x.upper() for x in (c.get("tons") or []) if isinstance(x, str) and _HEX.match(x)][:3]
    out["nota_visual"] = " ".join(str(c.get("nota_visual") or "").split())[:160]
    out["tela"] = c.get("tela") if c.get("tela") in TELAS else ""
    dq = " ".join(str(c.get("destaque") or "").split())[:28]
    out["destaque"] = "" if _vazio_na_tela(dq) else dq
    out["destaque_sub"] = " ".join(str(c.get("destaque_sub") or "").split())[:48] if out["destaque"] else ""
    out["referencias"] = [r for r in (_referencia(x) for x in (c.get("referencias") or [])[:4]) if r]
    out["roteiro"] = c.get("roteiro") is True  # plano escrito pelo roteiro do curta: objetos e placa vêm dele, não do léxico
    return out


INTERNOS = {"casa", "cozinha", "quarto", "escritorio", "escola", "loja", "restaurante", "hospital", "fabrica", "laboratorio", "palco"}
_CICLO_PLANOS = ("medio", "close", "conjunto", "detalhe", "aereo", "medio", "conjunto")
_CICLO_MOV = ("travelling", "aproximar", "panoramica", "afastar", "aproximar", "fixo")
_TRANS_NOVO = ("fade", "cortina", "zoom")


def encadear(lista: list[dict[str, Any]], tem_objeto: list[bool] | None = None) -> list[dict[str, Any]]:
    """A montagem: lugar novo abre com plano geral e transição; o mesmo lugar troca o plano a cada frase, como num filme."""
    tem_objeto = tem_objeto or [False] * len(lista)
    primeiro = next((c.get("cenario") for c in lista if c.get("cenario")), "")  # o curta abre já no primeiro lugar citado
    lista = [dict(c, cenario=primeiro) if not c.get("cenario") and k < next((i for i, x in enumerate(lista) if x.get("cenario")), 0) else c
             for k, c in enumerate(lista)]
    out: list[dict[str, Any]] = []
    atual, momento, clima, gente = "", "", "", 0
    ciclo, novos = 0, 0
    for k, c in enumerate(lista):
        c = dict(c)
        novo = bool(c.get("cenario")) and c["cenario"] != atual
        if not c.get("cenario"):
            c["cenario"] = atual or "palco_vazio"
        momento = c.get("momento") or momento
        if c.get("clima") and c["clima"] != clima and not c.get("lugar") and c["cenario"] in INTERNOS:
            c["cenario"], novo = "cidade", True  # "chegando lá, estava chovendo": corta para fora, onde se vê o tempo
        clima = c.get("clima") if c.get("clima") else (clima if not novo else "")
        c["momento"], c["clima"] = momento, clima
        if not c.get("personagens") and gente:  # quem estava em cena continua, parado ou andando
            c["personagens"] = [{"nome": "", "acao": "parado" if j else ("andar" if novo else "parado")} for j in range(gente)]
        gente = len(c["personagens"]) or gente
        if not c.get("plano"):
            if k == 0 or novo:
                c["plano"] = "geral"
            elif c["situacao"] in ("festa", "multidao", "conversa"):
                c["plano"] = "conjunto"
            elif tem_objeto[k] and (not out or out[-1].get("plano") != "detalhe"):
                c["plano"] = "detalhe"
            else:
                c["plano"] = _CICLO_PLANOS[ciclo % len(_CICLO_PLANOS)]
                ciclo += 1
                if not c["personagens"] and c["plano"] in ("medio", "close"):
                    c["plano"] = "conjunto"
        if not c.get("movimento"):
            c["movimento"] = "aproximar" if c["plano"] == "geral" else _CICLO_MOV[(k + ciclo) % len(_CICLO_MOV)]
        if not c.get("transicao"):
            if k == 0:
                c["transicao"] = "fade"
            elif novo:
                c["transicao"] = _TRANS_NOVO[novos % len(_TRANS_NOVO)]
            else:
                c["transicao"] = "corte"
        novos += 1 if novo else 0
        atual = c["cenario"]
        out.append(c)
    return out


# ---- com IA ------------------------------------------------------------------------------------------------------
def schema_item() -> dict[str, Any]:
    L = listas()
    from . import cortes

    return {"type": "object", "properties": {
        "cenario": {"type": "string", "enum": L["cenario"]}, "lugar": {"type": "string"},
        "momento": {"type": "string", "enum": L["momento"]}, "clima": {"type": "string", "enum": L["clima"]},
        "personagens": {"type": "array", "items": {"type": "object", "properties": {
            "nome": {"type": "string"}, "acao": {"type": "string", "enum": L["acao"]}}, "required": ["nome", "acao"], "additionalProperties": False}},
        "situacao": {"type": "string", "enum": L["situacao"]}, "plano": {"type": "string", "enum": L["plano"]},
        "movimento": {"type": "string", "enum": L["movimento"]}, "transicao": {"type": "string", "enum": L["transicao"]},
        "aderecos": {"type": "array", "items": {"type": "string", "enum": [f for f in cortes.formas() if f != "pessoa"]}},
        "nota_visual": {"type": "string"}},
        "required": ["cenario", "lugar", "momento", "clima", "personagens", "situacao", "plano", "movimento", "transicao", "aderecos", "nota_visual"],
        "additionalProperties": False}


def instrucoes(fala: str) -> str:
    """O pedaço do pedido que transforma o roteiro num curta: a IA lê a fala inteira para interpretar cada frase."""
    v = vocabulario()
    descr = lambda d: "; ".join(f"{k}: {x['desc']}" for k, x in d.items())  # noqa: E731
    return ("\n\nModo curta-metragem: cada cena é um plano de um curta que dá sentido ao que é dito. Leia a fala inteira para entender a "
            "história e preencha 'curta' em cada cena. 'cenario' é o lugar onde a frase acontece: se a fala cita um lugar, use-o; se só sugere "
            "(\"fui comprar pão\" é uma loja), interprete; se não há lugar, repita o da cena anterior para manter a continuidade. 'lugar' é a "
            "palavra do lugar exatamente como foi dita naquela frase, ou vazio. 'personagens' (até 3): quem age na frase, com 'nome' igual à "
            "palavra dita (ou vazio) e 'acao' entre as da lista. 'situacao' traduz o sentido da frase num efeito. 'momento' e 'clima' só se a "
            "fala disser ou o lugar pedir (vazio mantém). Varie 'plano' e 'movimento' como um diretor: lugar novo abre com plano geral; no "
            "mesmo lugar, alterne médio, close e detalhe; 'transicao' corte dentro do mesmo lugar e fade, cortina ou zoom ao trocar de lugar. "
            "'aderecos' (até 3) são objetos de cena sem rótulo que ajudam a reconhecer o lugar ou a ação. 'nota_visual' é uma frase curta para "
            "quem revisa, dizendo o que o plano mostra.\n"
            f"Cenários: {descr(v['cenarios'])}.\nAções: {descr(v['acoes'])}.\nSituações: {descr(v['situacoes'])}.\n"
            f"Planos: {'; '.join(f'{k}: {d}' for k, d in v['planos'].items())}.\n"
            f"Fala inteira do corte: {fala[:4000]}")


def de_resposta(c: Any, pals: list[dict]) -> dict[str, Any]:
    """A resposta da IA conferida: valores fora das listas saem; nome e lugar só ficam se foram ditos no trecho."""
    base = da_fala(pals)
    if not isinstance(c, dict):
        return base
    ditas = {t for w in pals for t in tokens(w["texto"])}
    n = normalizar(c)
    if n["lugar"] and not set(tokens(n["lugar"])) <= ditas:
        n["lugar"] = base["lugar"] if base["cenario"] == n["cenario"] else ""
    for p in n["personagens"]:
        if p["nome"] and not set(tokens(p["nome"])) <= ditas:
            p["nome"] = ""
    if not n["cenario"]:
        n["cenario"], n["lugar"] = base["cenario"], n["lugar"] or base["lugar"]
    if not n["personagens"]:
        n["personagens"] = base["personagens"]
    return n


def aplicar_tons(cenas: list[dict], pesquisa: dict[str, Any]) -> None:
    """Os tons da pesquisa entram na cena cuja fala cita o termo pesquisado (ou o lugar), sem mexer em quem já tem tons."""
    if not pesquisa:
        return
    for c in cenas:
        cu = (c.get("params") or {}).get("curta")
        if not isinstance(cu, dict) or cu.get("tons"):
            continue
        fala = " ".join(tokens(str(c["params"].get("ancora") or "") + " " + str(c["params"].get("texto") or "")))
        for termo, r in pesquisa.items():
            if r.get("tons") and " ".join(tokens(termo)) in fala:
                cu["tons"] = list(r["tons"])[:3]
                break


# ---- plano para o curta.js ---------------------------------------------------------------------------------------
def plano(cenas: list[dict]) -> list[dict[str, Any]]:
    from .cortes import _tempo_do_nome

    out = []
    for c in sorted((c for c in cenas if c["params"].get("cena") == "arte" and c["params"].get("curta")), key=lambda x: float(x["inicio"])):
        cu, ct, ini = c["params"]["curta"], c["params"].get("corte") or {}, float(c["inicio"])
        pal = c.get("palavras") or []
        if cu.get("roteiro") or cu.get("objetos") or cu.get("placa"):  # o roteiro do curta escolheu objetos e placa: o léxico não entra
            objs = []
            for k, o in enumerate(cu.get("objetos") or []):
                t = _tempo_do_nome(o["rotulo"], pal, ini) if o.get("rotulo") else round(ini + 0.25 + 0.35 * k, 3)
                objs.append({"id": f"o{k}", "nome": o.get("rotulo") or "", "forma": o["forma"], "t": t})
            nomes: list[str] = []
        else:
            objs = [{**o, "t": _tempo_do_nome(o["nome"], pal, ini)} for o in ct.get("objetos", [])]
            nomes = [o["nome"] for o in objs if o["forma"] == "pessoa" and not _vazio_na_tela(o["nome"])]
            objs = [o for o in objs if _vale_objeto(o)]
        lugar_t = _tempo_do_nome(cu["lugar"], pal, ini) if cu.get("lugar") else ini
        placa_t = _tempo_do_nome(cu["placa"], pal, ini) if cu.get("placa") else ini
        item = {"t0": round(ini, 3), "t1": round(float(c["fim"]), 3), **{k: cu.get(k) for k in CAMPOS if k != "nota_visual"},
                "lugar_t": lugar_t, "placa_t": placa_t, "objetos": objs, "nomes": nomes, "ficticio": bool(ct.get("ficticio"))}
        if not cu.get("roteiro") and not item.get("destaque"):  # sem roteiro: o número dito é o destaque do plano
            item["destaque"], item["destaque_sub"] = numero_dito(pal)
        if not item.get("tela"):
            item["tela"] = "dividida" if cu.get("roteiro") or _tem_o_que_mostrar(item) else "video"
        item["destaque_t"] = _tempo_do_nome(item["destaque"], pal, ini) if item.get("destaque") else ini
        srcs = c.get("_refs") or {}
        item["referencias"] = [{**{k: r[k] for k in ("termo", "tipo", "nome", "contexto", "logo")}, "src": srcs[r["arquivo"]],
                                "t": _tempo_do_nome(r["termo"], pal, ini), "credito": r["credito"].get("autor") or r["credito"].get("fonte")}
                               for r in cu.get("referencias") or [] if r["arquivo"] in srcs]
        out.append(item)
    return out


def _tem_o_que_mostrar(p: dict) -> bool:
    """Sem roteiro: o plano ilustra quando a frase tem lugar, objeto, placa, efeito ou alguém fazendo algo."""
    gente = any(x.get("acao") not in ("parado", "falar", "") for x in p.get("personagens") or [])
    return bool(p.get("lugar") or p.get("objetos") or p.get("placa") or p.get("nomes") or gente
                or (p.get("situacao") or "nenhuma") != "nenhuma")


_UNIDADES = set("% por cento mil milhao milhoes bilhao bilhoes trilhao trilhoes anos ano dias meses horas minutos segundos reais dolares "
                "pessoas vezes metros km quilos toneladas graus".split())
_NUM = re.compile(r"^(r\$)?\d+([.,]\d+)*%?$", re.I)


def numero_dito(pal: list[dict]) -> tuple[str, str]:
    """O primeiro número dito no trecho, com a unidade que vem colada ("40%", "150 anos"), e até 4 palavras depois dele."""
    ws = [str(w["texto"]).strip(" ,.;:!?\"'“”()") for w in pal]
    for i, w in enumerate(ws):
        if not _NUM.match(w):
            continue
        j = i + 1
        while j < len(ws) and j <= i + 2 and " ".join(tokens(ws[j])) in _UNIDADES:
            j += 1
        resto = [x for x in ws[j:j + 4] if x]
        while resto and (_vazio_na_tela(resto[-1]) or len(resto[-1]) <= 2):
            resto.pop()
        return " ".join(ws[i:j]), " ".join(resto)
    return "", ""


# ---- a montagem: quando o vídeo divide a tela, quando fica sozinho e quando o destaque toma a tela -----------------
GANCHO = 1.4  # o clip abre com a pessoa falando, em tela cheia
MIN_TRECHO = 1.2  # trecho mais curto que isso não troca a tela: piscaria
TRANSICAO = 0.3  # o painel entra e sai deslizando
DESTAQUE = (0.9, 2.0)  # duração mínima e máxima do destaque em tela cheia
REFERENCIA = 2.6  # quanto tempo a imagem real fica no painel
ZOOM_VIDEO = 1.12  # um trecho de vídeo sim, outro não, com o rosto mais perto (o corte seco dos shorts)


def montagem(cenas: list[dict], dur: float) -> dict[str, Any]:
    """A montagem do clip, calculada só dos planos: a mesma conta no curta.js (destaques) e no FFmpeg (telas e zoom).

    `trechos`: [{t0, t1, tela}] cobrindo 0..dur, tela "dividida" ou "video"; `destaques`: [{t0, t1, texto, sub}];
    `zooms`: [{t0, t1, escala}] nos trechos de vídeo.
    """
    pls = plano(cenas)
    segs: list[list] = []
    t = 0.0
    for p in pls:
        a, b = max(t, p["t0"]), min(dur, p["t1"])
        if a > t + 0.05:
            segs.append([t, a, "video"])
        if b > a:
            segs.append([a, b, p["tela"]])
        t = max(t, b)
    if dur > t + 0.05:
        segs.append([t, dur, "video"])
    refs = []
    for r in sorted((r for p in pls for r in p.get("referencias") or []), key=lambda r: r["t"]):
        a = max(0.0, r["t"] - 0.15)
        if refs and a < refs[-1]["t1"] + 0.1:  # o próximo nome chegou: a imagem anterior sai antes (no mínimo 1,2 s no ar)
            a = max(a, refs[-1]["t0"] + 1.3)
            if a > r["t"] + 1.5:
                continue  # atrasaria demais: o nome já passou
            refs[-1]["t1"] = round(a - 0.1, 3)
        refs.append({**r, "t0": round(a, 3), "t1": round(min(dur, a + REFERENCIA), 3)})
    for r in refs:  # a imagem real aparece no painel: o trecho dela é sempre dividido
        segs = _forcar(segs, r["t0"] - TRANSICAO, r["t1"], "dividida")
    if (segs and segs[0][2] == "dividida" and segs[0][0] < 0.3 and segs[0][1] - segs[0][0] > GANCHO + MIN_TRECHO
            and not any(r["t0"] < GANCHO + TRANSICAO for r in refs)):
        segs[0][0] = GANCHO
        segs.insert(0, [0.0, GANCHO, "video"])
    segs = _juntar(segs)
    while True:  # trecho curto demais assume a tela do vizinho mais longo (a ilustração vence o empate)
        curtos = [k for k, s in enumerate(segs) if s[1] - s[0] < MIN_TRECHO and len(segs) > 1]
        if not curtos:
            break
        k = min(curtos, key=lambda i: segs[i][1] - segs[i][0])
        viz = [segs[i] for i in (k - 1, k + 1) if 0 <= i < len(segs)]
        segs[k][2] = max(viz, key=lambda s: (s[1] - s[0], s[2] == "dividida"))[2]
        segs = _juntar(segs)
    trechos = [{"t0": round(a, 3), "t1": round(b, 3), "tela": tela} for a, b, tela in segs]
    destaques: list[dict[str, Any]] = []
    for k, p in enumerate(pls):
        if not p.get("destaque"):
            continue
        a = max(p["t0"], p["destaque_t"] - 0.08)
        proximo = [q["destaque_t"] - 0.08 for q in pls[k + 1:] if q.get("destaque")][:1]
        fim = min(p["t1"] + 0.6, dur, a + DESTAQUE[1], *proximo)
        if destaques and a < destaques[-1]["t1"] + 0.4:
            continue
        if fim - a >= DESTAQUE[0]:
            destaques.append({"t0": round(a, 3), "t1": round(fim, 3), "texto": p["destaque"], "sub": p.get("destaque_sub") or ""})
    zooms, n = [], 0
    for s in trechos:
        if s["tela"] == "video":
            if n % 2 == 1:
                zooms.append({"t0": s["t0"], "t1": s["t1"], "escala": ZOOM_VIDEO})
            n += 1
    destaques = [d for d in destaques if not any(d["t0"] < r["t1"] and r["t0"] < d["t1"] for r in refs)]  # a imagem vence o número
    return {"trechos": trechos, "destaques": destaques, "zooms": zooms, "referencias": refs}


def _forcar(segs: list[list], a: float, b: float, tela: str) -> list[list]:
    out: list[list] = []
    for s0, s1, tl in segs:
        if s1 <= a or s0 >= b:
            out.append([s0, s1, tl])
            continue
        if s0 < a:
            out.append([s0, a, tl])
        out.append([max(s0, a), min(s1, b), tela])
        if s1 > b:
            out.append([b, s1, tl])
    return _juntar(out)


def copiar_referencias(cenas: list[dict], pasta_clip: Any, pasta_camada: Any) -> list[str]:
    """As imagens reais das cenas vão para a pasta da camada (midias/<hash>); cada cena ganha `_refs` {arquivo: src}."""
    import hashlib
    import shutil

    avisos = []
    for c in cenas:
        cu = (c.get("params") or {}).get("curta")
        if not isinstance(cu, dict) or not cu.get("referencias"):
            continue
        refs = {}
        for r in cu["referencias"]:
            if not _ARQ_REF.match(str(r.get("arquivo") or "")):
                continue
            orig = pasta_clip / r["arquivo"]
            if not orig.is_file():
                avisos.append(f"imagem de “{r.get('nome') or r.get('termo')}” não está mais na pasta do clip: saiu do vídeo")
                continue
            h = hashlib.sha1(orig.read_bytes()).hexdigest()[:16]
            dest = pasta_camada / "midias" / f"{h}{orig.suffix}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copyfile(orig, dest)
            refs[r["arquivo"]] = f"midias/{dest.name}"
        c["_refs"] = refs
    return avisos


def ligar_referencias(cenas: list[dict], imagens: list[dict], pals: list[dict]) -> int:
    """Cada imagem real entra na cena em que o termo é dito pela primeira vez. Devolve quantas entraram."""
    from ..direcao import _na_fala

    n = 0
    usados: set[str] = set()
    for c in sorted(cenas, key=lambda x: float(x["inicio"])):
        cu = c["params"].get("curta")
        if not isinstance(cu, dict):
            continue
        trecho = [w for w in pals if float(c["inicio"]) - 0.05 <= w["inicio"] < float(c["fim"])]
        refs = []
        for r in imagens:
            if r["termo"] in usados or not trecho or not _na_fala(r["termo"], trecho, 0.99):
                continue
            ok = _referencia(r)
            if ok:
                refs.append(ok)
                usados.add(r["termo"])
        if refs:
            cu["referencias"] = refs[:4]
            n += len(refs[:4])
    return n


def _juntar(segs: list[list]) -> list[list]:
    out: list[list] = []
    for s in segs:
        if out and out[-1][2] == s[2]:
            out[-1][1] = s[1]
        else:
            out.append(list(s))
    return out


def _vale_objeto(o: dict) -> bool:
    """Objeto que entra no plano: nem pessoa (vira personagem), nem o bloco genérico de palavra solta, nem o próprio lugar."""
    return o.get("forma") not in ("pessoa", "bloco") and not _e_lugar(str(o.get("nome") or ""))


def _e_lugar(nome: str) -> bool:
    """"Fábrica", "casa", "escola": o nome já é o cenário inteiro, não vira peça solta dentro dele."""
    ts = tokens(nome)
    return bool(ts) and _lugar(ts, " ".join(ts))[1] >= 0


def ativo(cenas: list[dict]) -> bool:
    return any(c["params"].get("cena") == "arte" and c["params"].get("curta") for c in cenas)


def extras(camada: Any, cenas: list[dict], three: str) -> tuple[str, str]:
    from . import cortes

    par = camada.ctx({}, 0, 1, 0, 1, [], None).par
    acoes = plano(cenas)
    fs = cortes.formas()
    usadas = {o["forma"] for a in acoes for o in a["objetos"]} | {f for a in acoes for f in a.get("aderecos") or []}
    cfg = {"estilo": camada.slug, "planos": acoes, "duracao": camada.duracao, "par": par, "semente": int(par.get("semente", 42)),
           "montagem": montagem(cenas, camada.duracao),
           "formas": {k: fs[k]["pecas"] for k in usadas}, "geo": camada.geo.para_js() if camada.geo is not None else None}
    dados = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    js = (_dados("curta") / "curta.js").read_text(encoding="utf-8")
    return ('<canvas id="arte3d"></canvas><div id="rotulos3d"></div><div id="transicao3d"></div><div id="destaques3d"></div><div id="relogio3d"></div>',
            f"<script>{three}</script>\n<script>window.CURTA = {dados};</script>\n<script>{js}</script>")


CSS = """
#transicao3d { position: absolute; left: 0; top: var(--topo); width: 100%; height: var(--alt); pointer-events: none; opacity: 0; background: var(--fundo); }
.placa3 { position: absolute; left: 0; top: 0; font-family: var(--f-titulo, var(--f-corpo)); font-size: calc(var(--u) * 44); line-height: 1.05; color: var(--sobre-primaria, var(--texto));
  background: var(--primaria); border-radius: calc(var(--u) * 10); padding: calc(var(--u) * 10) calc(var(--u) * 20); white-space: nowrap; opacity: 0;
  box-shadow: 0 calc(var(--u) * 6) 0 rgba(0,0,0,.18); text-transform: uppercase; letter-spacing: .02em; }
.placa3.pixel { border-radius: 0; }
#destaques3d { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; }
.destaque3 { position: absolute; inset: 0; opacity: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden;
  background: var(--fundo); }
.destaque3 .dq-grade { position: absolute; inset: -10%; opacity: 1;
  background-image: linear-gradient(color-mix(in srgb, var(--texto) 9%, transparent) 2px, transparent 2px),
    linear-gradient(90deg, color-mix(in srgb, var(--texto) 9%, transparent) 2px, transparent 2px);
  background-size: calc(var(--u) * 72) calc(var(--u) * 72); }
.destaque3 .dq-txt { position: relative; font-family: var(--f-titulo, var(--f-corpo)); font-size: calc(var(--u) * 190); line-height: .95; color: var(--primaria);
  text-transform: uppercase; text-align: center; max-width: 90%; letter-spacing: -.01em; text-shadow: 0 calc(var(--u) * 10) 0 rgba(0,0,0,.18); }
.destaque3 .dq-sub { position: relative; margin-top: calc(var(--u) * 28); font-family: var(--f-titulo, var(--f-corpo)); font-size: calc(var(--u) * 52);
  color: var(--texto); text-transform: uppercase; text-align: center; max-width: 84%; min-height: 1.1em; }
.destaque3 .dq-barra { position: relative; width: calc(var(--u) * 140); height: calc(var(--u) * 14); margin-top: calc(var(--u) * 26); background: var(--destaque);
  border-radius: calc(var(--u) * 7); transform-origin: center; }
.destaque3.pixel .dq-txt, .destaque3.pixel .dq-sub { text-shadow: calc(var(--u) * 8) calc(var(--u) * 8) 0 rgba(0,0,0,.35); }
.destaque3.pixel .dq-barra { border-radius: 0; }
.real3 { position: absolute; left: 0; top: 0; opacity: 0; display: flex; flex-direction: column; align-items: center; transform-origin: center;
  background: var(--fundo); border: calc(var(--u) * 5) solid var(--primaria); border-radius: calc(var(--u) * 22); padding: calc(var(--u) * 16);
  box-shadow: 0 calc(var(--u) * 18) calc(var(--u) * 40) rgba(0,0,0,.35); box-sizing: border-box; }
.real3 .rl-moldura { width: 100%; border-radius: calc(var(--u) * 12); overflow: hidden; background: #fff; display: flex; align-items: center; justify-content: center; }
.real3 .rl-moldura img { width: 100%; height: 100%; object-fit: cover; object-position: center 25%; }
.real3.logo .rl-moldura img { object-fit: contain; width: 82%; height: 72%; }
.real3 .rl-nome { margin-top: calc(var(--u) * 14); font-family: var(--f-titulo, var(--f-corpo)); font-size: calc(var(--u) * 54); line-height: 1.05; color: var(--primaria);
  text-transform: uppercase; text-align: center; }
.real3 .rl-ctx { margin-top: calc(var(--u) * 6); font-family: var(--f-corpo); font-size: calc(var(--u) * 30); line-height: 1.15; color: var(--texto); text-align: center; }
.real3 .rl-cred { margin-top: calc(var(--u) * 8); font-family: var(--f-corpo); font-size: calc(var(--u) * 17); color: var(--texto); opacity: .6; text-align: center;
  max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.real3.pixel, .real3.pixel .rl-moldura { border-radius: 0; }
.real3.pixel .rl-moldura img { image-rendering: pixelated; }
"""


# ---- o roteiro fechado do curta (pré-produção com IA) ---------------------------------------------------------------
# A IA recebe a fala inteira, o contexto, a direção de arte, a skill de roteiro, o que o estilo sabe desenhar e as
# referências, e escreve o curta inteiro de uma vez: metáfora, elenco e planos presos à fala. Depois o Clipator confere.
VISUAL = {
    "encaixe-vivo": "tudo é feito de peças plásticas de montar com pinos, cores lisas e brilho suave; os lugares se montam peça "
                    "a peça quando aparecem; personagens de bloco com cabeça quadrada; câmera em três quartos, com perspectiva",
    "pixel-em-cena": "mundo 3D com textura de pixels grossos e personagens de bloco pixelados, como um jogo de aventura; noite "
                     "por padrão, com luz quente; câmera baixa e próxima, com perspectiva",
    "fluxo-facetado": "polígonos chapados (low poly) com faces visíveis e cores foscas; personagens facetados; câmera em três "
                      "quartos, com perspectiva",
    "rota-em-foco": "maquete de papel vista quase de cima, como um mapa, com grade fina no chão; quando alguém anda ou corre, uma "
                    "rota é desenhada no chão; selo 'Esquema ilustrativo'; câmera ortográfica do alto",
    "terreno-vivo": "diorama isométrico flutuando no fundo do estilo, recortado mostrando as camadas de solo; ambientes internos "
                    "aparecem como sala em corte; câmera isométrica fixa",
}
MAX_PLANOS = 40


def schema_roteiro() -> dict[str, Any]:
    L = listas()
    from . import cortes

    plano_ = {"type": "object", "properties": {
        "ancora": {"type": "string"}, "ate": {"type": "string"}, "descricao": {"type": "string"},
        "cenario": {"type": "string", "enum": L["cenario"]}, "momento": {"type": "string", "enum": L["momento"]},
        "clima": {"type": "string", "enum": L["clima"]},
        "elenco": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "acao": {"type": "string", "enum": L["acao"]}}, "required": ["id", "acao"], "additionalProperties": False}},
        "situacao": {"type": "string", "enum": L["situacao"]}, "plano": {"type": "string", "enum": L["plano"]},
        "movimento": {"type": "string", "enum": L["movimento"]}, "transicao": {"type": "string", "enum": L["transicao"]},
        "objetos": {"type": "array", "items": {"type": "object", "properties": {
            "forma": {"type": "string", "enum": [f for f in cortes.formas() if f != "pessoa"]}, "rotulo": {"type": "string"}},
            "required": ["forma", "rotulo"], "additionalProperties": False}},
        "placa": {"type": "string"}, "tela": {"type": "string", "enum": list(TELAS)},
        "destaque": {"type": "string"}, "destaque_sub": {"type": "string"}},
        "required": ["ancora", "ate", "descricao", "tela", "cenario", "momento", "clima", "elenco", "situacao", "plano", "movimento",
                     "transicao", "objetos", "placa", "destaque", "destaque_sub"], "additionalProperties": False}
    return {"type": "object", "properties": {
        "assunto": {"type": "string"}, "metafora": {"type": "string"}, "logline": {"type": "string"},
        "elenco": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "papel": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPOS_ATOR)},
            "nome": {"type": "string"}}, "required": ["id", "papel", "tipo", "nome"], "additionalProperties": False}},
        "planos": {"type": "array", "items": plano_},
        "entidades": {"type": "array", "items": {"type": "object", "properties": {
            "termo": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPOS_ENTIDADE)}, "busca": {"type": "string"}},
            "required": ["termo", "tipo", "busca"], "additionalProperties": False}}},
        "required": ["assunto", "metafora", "logline", "elenco", "planos", "entidades"], "additionalProperties": False}


def prompt_roteiro(slug: str, pals: list[dict], dur: float, titulo: str, analise: dict | None, extra: str = "", refs: str = "") -> str:
    from . import cortes, especificacao

    v = vocabulario()
    lista = lambda d: "\n".join(f"- {k}: {x['desc'] if isinstance(x, dict) else x}" for k, x in d.items())  # noqa: E731
    formas = "\n".join(f"- {k}: {f['desc']}" for k, f in cortes.formas().items() if k != "pessoa")
    fala = " ".join(f"[{w['inicio']:.1f}]{w['texto'].strip()}" for w in pals)[:9000]
    return (
        f"Você é o diretor de um curta animado de {dur:.0f} segundos que passa por cima de um corte de vídeo e dá sentido ao que a "
        f"pessoa fala. Escreva o roteiro fechado do curta inteiro.\n\n"
        f"## O corte\nTítulo: “{titulo}”. Tema: {(analise or {}).get('tema') or '—'}.\n"
        f"Ideias do trecho: {json.dumps((analise or {}).get('ideias') or [], ensure_ascii=False)[:2500]}\n\n"
        f"## O estilo: {especificacao(slug)['nome']}\n{VISUAL.get(slug, '')}. O visual é fixo: você escolhe só o que aparece "
        "e o que acontece. Não existe nada além das listas abaixo; o que não está nelas não pode ser desenhado.\n\n"
        f"## Cenários\n{lista(v['cenarios'])}\n\n## Ações dos personagens\n{lista(v['acoes'])}\n\n"
        f"## Situações (um efeito por plano)\n{lista(v['situacoes'])}\n\n## Planos de câmera\n{lista(v['planos'])}\n\n"
        f"## Movimentos\n{lista(v['movimentos'])}\n\n## Transições\n{lista(v['transicoes'])}\n\n"
        f"## Objetos (até 3 por plano)\n{formas}\n\n"
        + (f"## Referências pesquisadas\n{refs}\n\n" if refs else "")
        + (f"## Direção de arte e método\n{extra[:14000]}\n\n" if extra else "")
        + "## O que devolver\n"
        "'assunto' (uma frase), 'metafora' (a situação concreta que conta o assunto, mantida no curta todo), 'logline' (a "
        "história do curta em uma frase, com começo, meio e fim) e 'elenco' (até 3: 'id' curto como p1, 'papel' na história, "
        "'tipo' pessoa ou robo, 'nome' só se a fala disser o nome, senão vazio).\n"
        f"'planos': um a cada 2 a 5 s, cobrindo de 0 a {dur:.0f} s na ordem da fala, no máximo {MAX_PLANOS}. Em cada um: "
        "'ancora' (4 a 8 palavras COPIADAS da fala, onde o plano começa), 'ate' (vazio), 'descricao' (o que o público vê e por "
        "que isso diz o que a frase quer dizer: quem, faz o quê, onde, com o quê), 'cenario', 'momento' e 'clima' (vazio mantém), "
        "'elenco' (quem está em cena, pelos ids, com a ação de cada um), 'situacao', 'plano', 'movimento', 'transicao', "
        "'objetos' ('rotulo' só com palavras ditas naquele trecho, senão vazio) e 'placa' (vazia na maioria; quando houver, "
        "palavras ditas naquele trecho que nomeiam algo importante; nunca pronome), 'tela' e 'destaque'.\n\n"
        "## Montagem (o ritmo de um short)\n"
        "Nem todo trecho precisa de desenho. 'tela' = 'dividida' quando o plano mostra algo que ajuda a entender a frase (o vídeo "
        "divide a tela com a animação); 'tela' = 'video' quando a frase é opinião, reação, piada, transição ou repete o que já foi "
        "mostrado: aí só a pessoa aparece, em tela cheia, até a próxima ilustração. Um bom curta alterna: algo entre um quarto e "
        "metade do tempo em 'video', nunca trechos de 'video' com menos de 1,5 s, e o primeiro plano costuma ser 'video' (o gancho é "
        "a pessoa falando). Plano 'video' ainda precisa de cenário e elenco (para a animação continuar coerente), mas não de objetos, "
        "placa nem efeito.\n"
        "'destaque' é o momento forte do plano, em tela cheia por 1 a 2 s: um número, valor ou percentual dito (\"40%\", \"150 anos\", "
        "\"R$ 2 mil\") ou, no máximo duas ou três vezes no curta, a palavra-chave que resume a ideia. Copie da fala, exatamente como "
        "foi dita no trecho; vazio na maioria dos planos. 'destaque_sub' (opcional) são até 5 palavras ditas logo depois que "
        "explicam o destaque (\"da produção global\"), senão vazio.\n\n"
        "## Coisas reais citadas\n"
        "'entidades': cada pessoa, empresa, organização, produto ou tecnologia conhecida que a fala cita pelo nome (até 8, na "
        "ordem em que aparecem). Delas o Clipator busca uma imagem real (a foto da pessoa, o logo da empresa, a foto do produto) e "
        "mostra no momento em que são ditas. 'termo' é copiado da fala exatamente como está na transcrição, mesmo que escrito "
        "errado; 'busca' é o nome certo e completo para achar na Wikipédia (\"Iliasat Skiver\" → \"Ilya Sutskever\", "
        "\"a Nvidia\" → \"Nvidia\", \"H100\" → \"Nvidia H100\"). Nada genérico (\"a IA\", \"o modelo\", \"placa de vídeo\"), "
        "nada que não foi dito e nenhum pronome.\n\n"
        f"## Fala com tempos\n{fala}"
    )


def de_roteiro(resp: Any, pals: list[dict], dur: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Os planos presos à fala, com o curta de cada um conferido, e o resumo do roteiro (assunto, metáfora, elenco)."""
    from ..desenho import _ancorar_cenas, _txt
    from ..direcao import _na_fala

    if not isinstance(resp, dict):
        return [], {}
    elenco = [e for e in (resp.get("elenco") or []) if isinstance(e, dict)][:MAX_PERSONAGENS]
    ids = {str(e.get("id") or f"p{k + 1}"): k for k, e in enumerate(elenco)}
    planos = [p for p in (resp.get("planos") or []) if isinstance(p, dict)][:MAX_PLANOS]
    presos = _ancorar_cenas({"cenas": [{**p, "etiqueta": p.get("cenario", ""), "dado": "", "balao": ""} for p in planos]}, pals, dur)
    por_ancora = {}
    for p in planos:
        por_ancora.setdefault(" ".join(tokens(str(p.get("ancora") or ""))), p)
    out = []
    for r in presos:
        p = por_ancora.get(" ".join(tokens(r["ancora"]))) or {}
        trecho = [w for w in pals if r["inicio"] - 0.05 <= w["inicio"] < r["fim"]]
        dito = lambda x: bool(x) and bool(trecho) and _na_fala(x, trecho, 0.99)  # noqa: E731
        pers = []
        for e in (p.get("elenco") or [])[:MAX_PERSONAGENS]:
            if isinstance(e, dict) and str(e.get("id")) in ids:
                k = ids[str(e.get("id"))]
                nome = str(elenco[k].get("nome") or "")
                pers.append({"nome": nome if dito(nome) else "", "acao": e.get("acao"), "ator": k, "tipo": elenco[k].get("tipo")})
        objs = [{"forma": o.get("forma"), "rotulo": o.get("rotulo") if dito(str(o.get("rotulo") or "")) else ""}
                for o in (p.get("objetos") or []) if isinstance(o, dict)]
        placa = str(p.get("placa") or "")
        dq, dqs = str(p.get("destaque") or ""), str(p.get("destaque_sub") or "")
        cu = normalizar({**p, "personagens": pers, "objetos": objs, "placa": placa if dito(placa) else "", "lugar": "", "roteiro": True,
                         "nota_visual": _txt(p.get("descricao"), 160), "destaque": dq if dito(dq) else "",
                         "destaque_sub": dqs if dito(dqs) else ""})
        out.append({"inicio": r["inicio"], "fim": r["fim"], "ancora": r["ancora"], "descricao": r["descricao"], "curta": cu})
    resumo = {k: _txt(resp.get(k), 300) for k in ("assunto", "metafora", "logline")}
    ents = []
    for e in (resp.get("entidades") or [])[:8]:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS_ENTIDADE:
            continue
        termo, busca = _txt(e.get("termo"), 60), _txt(e.get("busca"), 80)
        if termo and busca and not _vazio_na_tela(termo) and _na_fala(termo, pals, 0.99) and termo not in [x["termo"] for x in ents]:
            ents.append({"termo": termo, "tipo": e["tipo"], "busca": busca})
    resumo["entidades"] = ents
    resumo["elenco"] = [{"id": str(e.get("id") or ""), "papel": _txt(e.get("papel"), 80), "tipo": e.get("tipo") if e.get("tipo") in TIPOS_ATOR else "pessoa"}
                        for e in elenco]
    return out, resumo
