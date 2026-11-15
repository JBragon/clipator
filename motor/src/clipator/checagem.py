"""Checagem de fatos (passo 4): o que a fala cita, o que o Clipator entendeu e a fonte que vai usar.

Antes de montar os clips, o usuário vê cada pessoa, empresa, organização, produto, lugar e dado (número) citado nos
cortes escolhidos, com o nome que o Clipator identificou e a fonte. Ele confirma, corrige o nome e/ou a fonte, ou manda
ignorar. O que foi conferido vale na montagem:

- **Texto na tela**: a palavra dita ("Iliasat Skiver", "40 %") é trocada pelo nome conferido ("Ilya Sutskever",
  "45%") nas palavras que o render usa. Legenda, cenas, cartões, roteiro da IA e imagens reais leem essas palavras, então
  todos saem com o nome certo, nos mesmos tempos.
- **Imagens reais** (referencias.py): com a checagem feita, a lista conferida substitui a chamada à IA, e a fonte
  escolhida no Wikidata é a que dá a imagem e a linha de contexto.
- **Descrição da postagem**: as fontes conferidas entram num bloco "Fontes".

Identificação em duas camadas, como o resto do Clipator:

1. **Sem IA, offline**: nomes próprios (palavras com maiúscula no meio da frase, artes/pesquisa.termos), lugares da base
   cartográfica local (Natural Earth, artes/geografia) e números com a unidade ("500 mil reais", "40%"), com a fonte
   citada na própria fala ("segundo o IBGE").
2. **Com a IA configurada (opcional)**: uma chamada curta lê só o texto dos cortes e devolve, por schema, o termo como
   está na transcrição, o tipo e o nome certo. O termo tem de estar na fala.

A fonte de pessoas, empresas e produtos vem do Wikidata (grátis, sem conta). Sem rede, ou com CLIPATOR_PESQUISA=0, o
item fica sem fonte e o usuário pode escrever uma. Nada disso é obrigatório: sem checagem, o render sai como antes.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .textutil import STOPWORDS, sem_acento

Tipo = Literal["pessoa", "empresa", "organizacao", "produto", "lugar", "dado", "outro"]
Status = Literal["pendente", "confirmado", "corrigido", "ignorado"]
TIPOS: tuple[str, ...] = ("pessoa", "empresa", "organizacao", "produto", "lugar", "dado", "outro")
REVISADOS = ("confirmado", "corrigido")
MAX_POR_CORTE = 14
MAX_ITENS = 60
ARQUIVO = "checagem.json"

Progresso = Callable[[float, str], None]


class Fonte(BaseModel):
    titulo: str = ""
    url: str = ""
    descricao: str = ""
    origem: str = ""  # wikidata, natural-earth, fala, usuario ou vazio (sem fonte)
    id: str = ""  # Q-id do Wikidata ou id da base cartográfica


class Ocorrencia(BaseModel):
    candidato: str
    inicio: float = 0.0
    trecho: str = ""


class Item(BaseModel):
    id: str
    termo: str  # como está na transcrição
    tipo: Tipo = "outro"
    nome: str  # o que vai para o vídeo
    fonte: Fonte = Field(default_factory=Fonte)
    sugerido_nome: str = ""
    sugerido_fonte: Fonte = Field(default_factory=Fonte)
    ocorrencias: list[Ocorrencia] = Field(default_factory=list)
    origem: str = "regras"  # regras ou ia
    status: Status = "pendente"


class Checagem(BaseModel):
    candidatos: list[str] = Field(default_factory=list)
    itens: list[Item] = Field(default_factory=list)
    usou_ia: bool = False
    avisos: list[str] = Field(default_factory=list)
    atualizado_em: str = ""


class ErroChecagem(ValueError):
    pass


# ---- arquivo --------------------------------------------------------------------------------------------------------
def caminho(projeto: Any) -> Path:
    return Path(projeto.analise_dir) / ARQUIVO


def carregar(projeto: Any) -> Checagem:
    arq = caminho(projeto)
    if not arq.exists():
        return Checagem()
    try:
        return Checagem.model_validate_json(arq.read_text(encoding="utf-8"))
    except ValueError:
        return Checagem()


def salvar(projeto: Any, ch: Checagem) -> Checagem:
    ch = ch.model_copy(update={"atualizado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    arq = caminho(projeto)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(ch.model_dump_json(indent=1), encoding="utf-8")
    return ch


def resumo(ch: Checagem) -> dict[str, int]:
    n = {s: 0 for s in ("pendente", "confirmado", "corrigido", "ignorado")}
    for i in ch.itens:
        n[i.status] += 1
    return {"total": len(ch.itens), **n}


# ---- texto ----------------------------------------------------------------------------------------------------------
def _chave(s: str) -> str:
    return " ".join(re.sub(r"[^\w%$]+", " ", sem_acento(str(s)).lower()).split())


def id_do_termo(termo: str) -> str:
    return hashlib.sha1(_chave(termo).encode()).hexdigest()[:10]


_PONT = " ,.;:!?\"'“”()[]…"


def _limpa(w: str) -> str:
    return str(w).strip().strip(_PONT)


def palavras_do_corte(pals: list[dict], inicio: float, fim: float) -> list[dict]:
    return [w for w in pals if w["fim"] > inicio + 0.02 and w["inicio"] < fim - 0.02]


def _achar(termo: str, pals: list[dict]) -> int | None:
    """Índice da primeira palavra em que o termo começa (sem caixa, acento nem pontuação)."""
    alvo = _chave(termo).split()
    ws = [_chave(w["texto"]) for w in pals]
    for i in range(max(0, len(ws) - len(alvo) + 1)):
        if alvo and ws[i:i + len(alvo)] == alvo:
            return i
    return None


def _trecho(pals: list[dict], i: int, n: int = 1, lado: int = 6) -> str:
    return " ".join(w["texto"].strip() for w in pals[max(0, i - lado):i + n + lado])


# ---- camada 1: regras, sem IA e sem rede ----------------------------------------------------------------------------
_NUM = re.compile(r"^(r\$|us\$|\$)?\d+([.,]\d+)*(%|º|ª)?$", re.IGNORECASE)
_GRANDEZA = {"mil", "milhao", "milhoes", "bilhao", "bilhoes", "trilhao", "trilhoes", "%", "porcento", "reais", "real", "dolares",
             "dolar", "euros", "euro", "pessoas", "anos", "vezes", "mortos", "casos", "habitantes", "km", "quilometros", "metros",
             "toneladas", "quilos", "graus", "votos", "empregos", "usuarios", "seguidores", "inscritos"}
_POR_CENTO = ("por", "cento")
_CITA = re.compile(r"(?i:\b(segundo|conforme|de acordo com|dados d[oae]s?|pesquisa d[oae]s?|levantamento d[oae]s?|relat[oó]rio d[oae]s?|"
                   r"estudo d[oae]s?|n[uú]meros d[oae]s?)\s+(?:(?:o|a|os|as)\s+)?)((?:[A-ZÀ-Ý][\wÀ-ÿ.&-]*\s*){1,4})")
_SIGLA = re.compile(r"^[A-ZÀ-Ý]{2,6}$")
_NAO_SIGLA = {"OK", "TV", "EU", "UM", "AI", "NE", "TA", "SO", "LA", "AH", "OH"}
_NAO_NOME = set("a o as os um uma eu ele ela nos voce mas e entao ai depois quando todo toda agora isso esse essa este esta la aqui so "
                "sim nao ne tipo cara mano gente deus senhor senhora".split())


def _numeros(pals: list[dict]) -> list[tuple[int, int, str]]:
    """(índice, nº de palavras, termo) de cada número dito com a grandeza colada ("500 mil reais", "40 por cento")."""
    out = []
    i = 0
    while i < len(pals):
        w = _limpa(pals[i]["texto"])
        if not _NUM.match(w):
            i += 1
            continue
        j = i + 1
        while j < len(pals) and j <= i + 3:
            t = _chave(pals[j]["texto"])
            if t in _GRANDEZA or (t == "por" and j + 1 < len(pals) and _chave(pals[j + 1]["texto"]) == "cento"):
                j += 2 if t == "por" else 1
                continue
            if t in ("de",) and j + 1 < len(pals) and _chave(pals[j + 1]["texto"]) in _GRANDEZA - {"mil", "milhao", "milhoes", "bilhao",
                                                                                                    "bilhoes", "trilhao", "trilhoes"}:
                j += 2  # "2 milhões de pessoas"
                continue
            break
        termo = " ".join(_limpa(x["texto"]) for x in pals[i:j])
        sozinho = j == i + 1
        # número solto de um dígito ("2", "3") quase nunca é dado: só entra com grandeza
        if not (sozinho and re.fullmatch(r"\d", w)):
            out.append((i, j - i, termo))
        i = j
    return out


def _fonte_citada(pals: list[dict], i: int) -> Fonte:
    """A fonte que a própria fala cita perto do número ("segundo o IBGE", "dados da OMS")."""
    a = i
    while a > 0 and i - a < 20 and not pals[a - 1]["texto"].strip().endswith((".", "!", "?")):
        a -= 1
    b = i
    while b < len(pals) - 1 and b - i < 20 and not pals[b]["texto"].strip().endswith((".", "!", "?")):
        b += 1
    texto = " ".join(w["texto"].strip() for w in pals[a:b + 1])  # só a frase do número
    m = _CITA.search(texto)
    if not m:
        return Fonte()
    nome = m.group(2).strip().strip(_PONT)
    if not nome or _chave(nome) in _NAO_NOME:
        return Fonte()
    return Fonte(titulo=nome[:80], descricao="citada na própria fala", origem="fala")


def _lugares(pals: list[dict]) -> list[tuple[int, int, str, Any]]:
    """Lugares da base cartográfica local ditos com maiúscula (país, estado, continente)."""
    try:
        from .artes import geografia
    except Exception:  # noqa: BLE001 - sem a base, os lugares ficam para a IA
        return []
    try:
        nomes = geografia.nomes_falados()
    except Exception:  # noqa: BLE001
        return []
    out = []
    i = 0
    while i < len(pals):
        achou = False
        for n in (4, 3, 2, 1):
            janela = pals[i:i + n]
            if len(janela) < n:
                continue
            ws = [_limpa(w["texto"]) for w in janela]
            if not ws[0][:1].isupper():
                continue
            termo = " ".join(ws)
            if geografia.normalizar(termo) not in nomes:
                continue
            try:
                e = geografia.resolver(termo)
            except geografia.LugarNaoResolvido as exc:
                e = exc.opcoes[0] if exc.opcoes else None
            if e is None:
                continue
            out.append((i, n, termo, e))
            i += n
            achou = True
            break
        if not achou:
            i += 1
    return out


def por_regras(pals: list[dict], candidato: str) -> list[Item]:
    """Os itens que dá para achar sem IA nem rede."""
    from .artes import pesquisa

    itens: dict[str, Item] = {}

    def add(termo: str, tipo: str, nome: str, fonte: Fonte, i: int, n: int) -> None:
        k = id_do_termo(termo)
        if not _chave(termo) or k in itens:
            return
        oc = Ocorrencia(candidato=candidato, inicio=round(float(pals[i]["inicio"]), 2), trecho=_trecho(pals, i, n))
        itens[k] = Item(id=k, termo=termo, tipo=tipo, nome=nome, fonte=fonte, sugerido_nome=nome, sugerido_fonte=fonte,
                        ocorrencias=[oc], origem="regras")

    lugares = _lugares(pals)
    ocupado = {k for i, n, _, _ in lugares for k in range(i, i + n)}
    for i, n, termo, e in lugares:
        from .artes import geografia

        add(termo, "lugar", e.nome, Fonte(titulo=e.nome, descricao=geografia.descricao(e), origem="natural-earth", id=f"{e.nivel}:{e.id}"), i, n)
    for nome in pesquisa.termos(pals, maximo=MAX_POR_CORTE):
        if not nome[:1].isupper() or _chave(nome) in _NAO_NOME or all(t in STOPWORDS for t in _chave(nome).split()):
            continue
        i = _achar(nome, pals)
        if i is None or i in ocupado:
            continue
        add(nome, "outro", nome, Fonte(), i, len(nome.split()))
    for i, w in enumerate(pals):  # siglas (IBGE, OMS, NASA): o nome próprio em caixa alta não passa nos nomes acima
        x = _limpa(w["texto"])
        if _SIGLA.match(x) and x not in _NAO_SIGLA and i not in ocupado:
            add(x, "organizacao", x, Fonte(), i, 1)
    for i, n, termo in _numeros(pals):
        add(termo, "dado", termo, _fonte_citada(pals, i), i, n)
    return list(itens.values())[:MAX_POR_CORTE * 2]


# ---- camada 2: IA (opcional) ----------------------------------------------------------------------------------------
def schema() -> dict[str, Any]:
    return {"type": "object", "properties": {"itens": {"type": "array", "items": {"type": "object", "properties": {
        "corte": {"type": "string"}, "termo": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPOS)},
        "nome": {"type": "string"}, "fonte_citada": {"type": "string"}},
        "required": ["corte", "termo", "tipo", "nome", "fonte_citada"], "additionalProperties": False}}},
        "required": ["itens"], "additionalProperties": False}


def prompt(cortes: list[tuple[str, list[dict]]]) -> str:
    blocos = "\n\n".join(f"[corte {cid}]\n" + " ".join(w["texto"].strip() for w in pals)[:5000] for cid, pals in cortes)
    return ("Você ajuda a checar fatos antes de montar cortes de vídeo. Liste o que estas falas citam e que pode sair errado na tela: "
            "pessoas, empresas, organizações, produtos ou tecnologias e lugares (país, estado, continente) citados pelo nome, e dados "
            "(números, porcentagens, valores, estatísticas) ditos como fato. Até 12 por corte, na ordem em que aparecem.\n"
            "- 'corte': o id entre colchetes do corte em que aparece.\n"
            "- 'termo': copiado da fala exatamente como está na transcrição, mesmo que escrito errado.\n"
            "- 'nome': o nome certo e completo (\"Iliasat Skiver\" → \"Ilya Sutskever\", \"a Nvídia\" → \"Nvidia\"). Para dado, o "
            "valor como deve aparecer na tela (\"quarenta por cento\" → \"40%\"), sem corrigir o valor que a pessoa disse.\n"
            "- 'fonte_citada': só se a fala disser de onde vem (\"segundo o IBGE\" → \"IBGE\"); senão, vazio. Não invente fonte.\n"
            "- Nada genérico (\"a IA\", \"o governo\", \"a empresa\"), nenhum pronome e nada que não foi dito.\n\n" + blocos)


def de_resposta(resp: Any, cortes: dict[str, list[dict]]) -> list[Item]:
    from .direcao import _na_fala

    out: dict[str, Item] = {}
    for e in ((resp or {}).get("itens") or []) if isinstance(resp, dict) else []:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS:
            continue
        pals = cortes.get(str(e.get("corte") or ""))
        termo = " ".join(str(e.get("termo") or "").split())[:80]
        nome = " ".join(str(e.get("nome") or "").split())[:80] or termo
        if pals is None or not termo or not _na_fala(termo, pals, 0.99):
            continue
        i = _achar(termo, pals)
        k = id_do_termo(termo)
        if i is None or k in out:
            continue
        cit = " ".join(str(e.get("fonte_citada") or "").split())[:80]
        fonte = Fonte(titulo=cit, descricao="citada na própria fala", origem="fala") if cit else Fonte()
        out[k] = Item(id=k, termo=termo, tipo=e["tipo"], nome=nome, fonte=fonte, sugerido_nome=nome, sugerido_fonte=fonte,
                      ocorrencias=[Ocorrencia(candidato=str(e["corte"]), inicio=round(float(pals[i]["inicio"]), 2),
                                              trecho=_trecho(pals, i, len(termo.split())))], origem="ia")
    return list(out.values())


# ---- fonte: Wikidata (grátis, sem conta) ----------------------------------------------------------------------------
_EMPRESA = {"Q4830453", "Q891723", "Q6881511", "Q783794", "Q167037", "Q1058914", "Q210167", "Q18388277"}
_ORGANIZACAO = {"Q43229", "Q163740", "Q484652", "Q7278", "Q327333", "Q2659904", "Q245065", "Q15911314", "Q3918", "Q875538"}
_PRODUTO = {"Q2424752", "Q7397", "Q166142", "Q9135", "Q1172284", "Q17517", "Q7889", "Q11446", "Q3966", "Q431289"}
_LUGAR = {"Q6256", "Q3624078", "Q5107", "Q35657", "Q107390", "Q515", "Q1549591"}


def _tipo_wikidata(p31: set[str]) -> str:
    if "Q5" in p31:
        return "pessoa"
    if p31 & _EMPRESA:
        return "empresa"
    if p31 & _LUGAR:
        return "lugar"
    if p31 & _PRODUTO:
        return "produto"
    if p31 & _ORGANIZACAO:
        return "organizacao"
    return "outro"


def opcoes_wikidata(busca: str, abrir: Any = None, timeout: float = 8.0, limite: int = 5) -> list[dict[str, str]]:
    """Os itens do Wikidata para a busca, com nome, descrição e link (para o usuário escolher a fonte)."""
    from .artes import pesquisa

    busca = " ".join(str(busca).split())[:80]
    if not busca:
        return []
    abrir = abrir or pesquisa._abrir
    q = {"action": "wbsearchentities", "search": busca, "language": "pt", "uselang": "pt", "format": "json",
         "limit": str(limite), "type": "item"}
    achados = json.loads(abrir(pesquisa.WIKIDATA + "?" + urllib.parse.urlencode(q), timeout)).get("search") or []
    out = []
    for a in achados[:limite]:
        qid = str(a.get("id") or "")
        if re.fullmatch(r"Q\d+", qid):
            out.append({"id": qid, "titulo": str(a.get("label") or busca)[:80], "descricao": str(a.get("description") or "")[:140],
                        "url": f"https://www.wikidata.org/wiki/{qid}", "origem": "wikidata"})
    return out


def _detalhe_wikidata(qid: str, abrir: Any, timeout: float) -> tuple[str, str, set[str]]:
    """(nome em português, descrição em português, P31) do item."""
    from .artes import pesquisa

    e = json.loads(abrir(pesquisa.ENTIDADE.format(qid), timeout))["entities"][qid]
    return pesquisa._lingua(e, "labels"), pesquisa._lingua(e, "descriptions"), pesquisa._ids(e.get("claims") or {}, "P31")


def fonte_wikidata(nome: str, tipo: str, abrir: Any = None, timeout: float = 8.0) -> tuple[Fonte, str, str]:
    """(fonte, tipo, nome) do primeiro item que combina com o tipo; Fonte() se nada combinar."""
    from .artes import pesquisa

    abrir = abrir or pesquisa._abrir
    for op in opcoes_wikidata(nome, abrir, timeout, 4)[:3]:
        try:
            rotulo, desc, p31 = _detalhe_wikidata(op["id"], abrir, timeout)
        except Exception:  # noqa: BLE001
            continue
        if p31 & {"Q4167410", "Q22808320"}:  # página de desambiguação
            continue
        achado = _tipo_wikidata(p31)
        if tipo == "pessoa" and achado != "pessoa":
            continue
        if tipo in ("empresa", "organizacao", "produto") and achado == "pessoa":
            continue
        tipo_final = achado if tipo == "outro" else tipo
        titulo = rotulo or op["titulo"]
        return (Fonte(titulo=titulo, url=op["url"], descricao=desc or op["descricao"], origem="wikidata", id=op["id"]),
                tipo_final, titulo)
    return Fonte(), tipo, nome


# ---- juntar tudo ----------------------------------------------------------------------------------------------------
def _juntar(itens: list[Item]) -> list[Item]:
    """O mesmo termo em vários cortes vira um item só, com todas as ocorrências."""
    out: dict[str, Item] = {}
    for it in itens:
        if it.id in out:
            ja = out[it.id]
            vistos = {(o.candidato, o.inicio) for o in ja.ocorrencias}
            ja.ocorrencias += [o for o in it.ocorrencias if (o.candidato, o.inicio) not in vistos]
        else:
            out[it.id] = it.model_copy(deep=True)
    return list(out.values())


def identificar(projeto: Any, candidatos: list[str], ad: Any = None, progresso: Progresso | None = None,
                cancelar: threading.Event | None = None, abrir: Any = None, cache: Any = None) -> Checagem:
    """Monta (ou refaz) a checagem dos cortes. O que o usuário já conferiu fica como ele deixou."""
    from .artes import pesquisa
    from .transcribe import palavras

    prog = progresso or (lambda _f, _m: None)
    trans = projeto.transcricao()
    if not trans:
        raise ErroChecagem("O vídeo ainda não tem transcrição. Rode a análise no passo 1.")
    pals_all = palavras(trans)
    todos = {c["id"]: c for c in projeto.candidatos()}
    ids = [c for c in dict.fromkeys(candidatos) if c in todos]
    if not ids:
        raise ErroChecagem("Nenhum corte para checar. Escolha os cortes no passo 2.")
    cortes = {cid: palavras_do_corte(pals_all, float(todos[cid]["inicio"]), float(todos[cid]["fim"])) for cid in ids}
    avisos: list[str] = []

    prog(0.05, "procurando nomes, lugares e números na fala")
    regras: list[Item] = []
    for cid, pals in cortes.items():
        regras += por_regras(pals, cid)

    ia: list[Item] = []
    usou_ia = False
    if ad is not None:
        prog(0.2, f"perguntando ao {getattr(ad, 'nome', 'IA')} o que a fala cita")
        try:
            from .ai.adapter import chamar

            ia = de_resposta(chamar(ad, prompt(list(cortes.items())), schema(), cache, cancelar), cortes)
            usou_ia = True
        except Exception as exc:  # noqa: BLE001 - sem a IA, valem as regras
            avisos.append(f"A IA não respondeu ({exc}); a lista veio só das regras locais.")
    # a IA manda no que ela achou; as regras completam (lugares e números que ela deixou passar)
    da_ia = {i.id for i in ia}
    tirados_pela_ia = {id_do_termo(p) for i in ia for p in i.termo.split()} if ia else set()
    itens = _juntar(ia + [r for r in regras if r.id not in da_ia and not (r.tipo == "outro" and r.id in tirados_pela_ia)])
    if usou_ia:  # nome solto que a IA viu e não listou costuma ser começo de frase ou palavra comum
        itens = [i for i in itens if i.origem == "ia" or i.tipo != "outro"]

    # a fonte: o que o usuário já conferiu fica; o resto busca no Wikidata
    antigo = {i.id: i for i in carregar(projeto).itens}
    a_buscar = [i for i in itens if i.tipo not in ("lugar", "dado") and not i.fonte.url
                and not (i.id in antigo and antigo[i.id].status != "pendente")]
    if a_buscar and pesquisa.ligada():
        falhas = 0
        for k, it in enumerate(a_buscar):
            if cancelar is not None and cancelar.is_set():
                break
            prog(0.45 + 0.5 * k / max(1, len(a_buscar)), f"buscando a fonte de “{it.nome}”")
            try:
                fonte, tipo, nome = fonte_wikidata(it.nome, it.tipo, abrir)
            except Exception:  # noqa: BLE001 - sem rede: o item fica sem fonte
                falhas += 1
                if falhas >= 2:
                    avisos.append("Sem acesso ao Wikidata agora: os itens restantes ficaram sem fonte. Dá para escrever a fonte à mão.")
                    break
                continue
            if fonte.url:
                it.fonte, it.sugerido_fonte, it.tipo = fonte, fonte, tipo  # type: ignore[assignment]
                if it.origem == "regras":  # sem IA, o nome do Wikidata é a melhor sugestão de grafia
                    it.nome = it.sugerido_nome = nome
    elif a_buscar:
        avisos.append("Busca de fontes desligada (CLIPATOR_PESQUISA=0): os itens ficaram sem fonte.")

    final: list[Item] = []
    for it in itens:
        velho = antigo.get(it.id)
        if velho is not None and velho.status != "pendente":
            final.append(velho.model_copy(update={"ocorrencias": it.ocorrencias}))
        else:
            final.append(it)
    # itens conferidos de cortes que não estão nesta rodada continuam valendo para eles
    final += [v for k, v in antigo.items() if k not in {i.id for i in final} and v.status != "pendente"
              and any(o.candidato not in ids for o in v.ocorrencias)]
    final.sort(key=lambda i: (ids.index(i.ocorrencias[0].candidato) if i.ocorrencias and i.ocorrencias[0].candidato in ids else 99,
                              i.ocorrencias[0].inicio if i.ocorrencias else 0))
    prog(1.0, f"{len(final)} item(ns) para checar")
    ch = Checagem(candidatos=ids, itens=final[:MAX_ITENS], usou_ia=usou_ia, avisos=avisos)
    return salvar(projeto, ch)


def atualizar_item(projeto: Any, item_id: str, status: str | None = None, nome: str | None = None,
                   fonte: dict | None = None, tipo: str | None = None) -> Item:
    """Confirmar, corrigir (nome, fonte, tipo) ou ignorar um item. Mudar o nome ou a fonte marca como corrigido."""
    ch = carregar(projeto)
    it = next((i for i in ch.itens if i.id == item_id), None)
    if it is None:
        raise ErroChecagem("Item não encontrado. Rode a identificação de novo.")
    upd: dict[str, Any] = {}
    if nome is not None:
        nome = " ".join(str(nome).split())[:80]
        if not nome:
            raise ErroChecagem("O nome não pode ficar vazio. Para não mexer no que foi dito, use Ignorar.")
        upd["nome"] = nome
    if fonte is not None:
        f = Fonte.model_validate({**fonte})
        if f.url and not re.match(r"^https?://", f.url):
            raise ErroChecagem("O link da fonte tem de começar com http:// ou https://.")
        upd["fonte"] = f.model_copy(update={"titulo": f.titulo[:120], "descricao": f.descricao[:200], "url": f.url[:400],
                                            "origem": f.origem or "usuario"})
    if tipo is not None:
        if tipo not in TIPOS:
            raise ErroChecagem(f"Tipo desconhecido: {tipo}.")
        upd["tipo"] = tipo
    novo = it.model_copy(update=upd)
    if status is not None:
        if status not in ("pendente", "confirmado", "corrigido", "ignorado"):
            raise ErroChecagem(f"Situação desconhecida: {status}.")
        novo.status = status  # type: ignore[assignment]
    elif upd:
        novo.status = "confirmado"  # type: ignore[assignment]
    if novo.status in REVISADOS:  # corrigido é quando algo ficou diferente do sugerido
        mudou = novo.nome != novo.sugerido_nome or novo.fonte != novo.sugerido_fonte or (tipo is not None and tipo != it.tipo)
        novo.status = "corrigido" if mudou else "confirmado"  # type: ignore[assignment]
    ch.itens = [novo if i.id == item_id else i for i in ch.itens]
    salvar(projeto, ch)
    return novo


def confirmar_pendentes(projeto: Any) -> int:
    ch = carregar(projeto)
    n = 0
    for i in ch.itens:
        if i.status == "pendente":
            i.status = "confirmado"
            n += 1
    salvar(projeto, ch)
    return n


# ---- na montagem ----------------------------------------------------------------------------------------------------
def revisados(projeto: Any) -> list[Item]:
    return [i for i in carregar(projeto).itens if i.status in REVISADOS]


def _partes(p: str) -> tuple[str, str, str]:
    m = re.match(r"^([\"'“(\[]*)(.*?)([\"'”)\].,;:!?…]*)$", p)
    return (m.group(1), m.group(2), m.group(3)) if m else ("", p, "")


def aplicar_nas_palavras(pals: list[dict], itens: list[Item]) -> tuple[list[dict], list[dict[str, Any]]]:
    """Troca o termo dito pelo nome conferido. Devolve (palavras novas, trocas). As palavras de entrada não mudam.

    Com o mesmo número de palavras, cada uma mantém o seu tempo; senão as palavras do nome dividem o tempo do termo
    inteiro. A palavra original fica em "original"."""
    out = [dict(w) for w in pals]
    alvos = sorted(((_chave(i.termo).split(), i) for i in itens if _chave(i.termo) and i.nome.strip() and i.nome.strip() != i.termo.strip()),
                   key=lambda x: -len(x[0]))
    if not alvos:
        return out, []
    trocas: list[dict[str, Any]] = []
    res: list[dict] = []
    k = 0
    chaves = [_chave(w["texto"]) for w in out]
    while k < len(out):
        feito = False
        for alvo, it in alvos:
            n = len(alvo)
            if chaves[k:k + n] != alvo:
                continue
            janela = out[k:k + n]
            de = " ".join(x["texto"].strip() for x in janela)
            pre, _, _ = _partes(janela[0]["texto"].strip())
            _, _, pos = _partes(janela[-1]["texto"].strip())
            novas = it.nome.split()
            espaco = " " if janela[0]["texto"].startswith(" ") else ""
            if len(novas) == n:
                for j, (w, nv) in enumerate(zip(janela, novas)):
                    w.setdefault("original", w["texto"])
                    w["texto"] = espaco * (j == 0) + (pre if j == 0 else "") + nv + (pos if j == n - 1 else "")
                    res.append(w)
            else:  # o nome ocupa o tempo do termo inteiro, dividido pelo tamanho de cada palavra
                ini, fim = float(janela[0]["inicio"]), float(janela[-1]["fim"])
                total = sum(len(x) for x in novas) or 1
                t = ini
                for j, nv in enumerate(novas):
                    d = (fim - ini) * len(nv) / total
                    res.append({**janela[0], "inicio": round(t, 3), "fim": round(t + d, 3), "original": de if j == 0 else "",
                                "texto": espaco * (j == 0) + (pre if j == 0 else "") + nv + (pos if j == len(novas) - 1 else "")})
                    t += d
            trocas.append({"de": de, "para": it.nome, "inicio": janela[0]["inicio"], "tipo": it.tipo})
            k += n
            feito = True
            break
        if not feito:
            res.append(out[k])
            k += 1
    return res, trocas


def entidades_do_clip(projeto: Any, candidato: str | None, pals_clip: list[dict]) -> list[dict[str, str]] | None:
    """As entidades para as imagens reais (referencias.py), pela checagem; None se o corte não foi checado.

    Já com as palavras trocadas: o termo de cada item conferido é o nome conferido."""
    from .artes.pesquisa import TIPOS_ENTIDADE

    ch = carregar(projeto)
    if not candidato or candidato not in ch.candidatos:
        return None
    out = []
    for it in ch.itens:
        if it.status == "ignorado" or not any(o.candidato == candidato for o in it.ocorrencias):
            continue
        tipo = it.tipo if it.tipo in TIPOS_ENTIDADE else ("empresa" if it.tipo == "outro" and it.fonte.origem == "wikidata" else None)
        if tipo is None:
            continue
        termo = it.nome if it.status in REVISADOS else it.termo
        if _achar(termo, pals_clip) is None:
            continue
        busca = it.fonte.titulo if it.fonte.origem == "wikidata" and it.fonte.titulo else it.nome
        out.append({"termo": termo, "tipo": tipo, "busca": busca, "qid": it.fonte.id if it.fonte.origem == "wikidata" else ""})
    return out


def fontes_do_texto(projeto: Any, texto: str) -> str:
    """O bloco "Fontes" da descrição: as fontes conferidas do que aparece no texto do clip."""
    alvo = f" {_chave(texto)} "
    linhas = []
    for it in revisados(projeto):
        f = it.fonte
        if not (f.titulo or f.url):
            continue
        if f" {_chave(it.termo)} " not in alvo and f" {_chave(it.nome)} " not in alvo:
            continue
        linhas.append(f"- {it.nome}: {f.titulo or f.url}" + (f" ({f.url})" if f.url and f.titulo else ""))
    return ("Fontes:\n" + "\n".join(dict.fromkeys(linhas))) if linhas else ""
