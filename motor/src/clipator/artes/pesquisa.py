"""Pesquisa de referências do modo curta: o que a fala cita, lido na Wikipédia e visto no Wikimedia Commons.

A direção de arte precisa saber como é o lugar ou a situação de que a pessoa fala ("Lençóis Maranhenses" são dunas
brancas com lagoas azuis, não um deserto amarelo). Para cada termo da fala (nomes próprios e lugares ditos):

- **texto**: o resumo da Wikipédia em português e as descrições das imagens do Commons. Vai para a IA como contexto,
  para ela interpretar o cenário, a situação e a ação de cada plano. Nunca vai para a tela.
- **tons**: até três cores lidas nas miniaturas das imagens (artes/referencias.py, em CIELAB). Entram no cenário do plano
  que cita o termo, puxadas para a paleta do estilo (o chão, o céu ou a água e um acento).

As duas fontes são gratuitas, sem conta e sem chave. Só entram imagens de domínio público ou Creative Commons, e a imagem
nunca é usada nem guardada: só a leitura de cor e o crédito (autor, licença, página) ficam em `pesquisa.json`. Roda só na
pré-produção com IA, que já precisa de rede; sem rede, ou com CLIPATOR_PESQUISA=0, o curta segue sem referências e diz
isso no relato. O render e o plano sem IA nunca usam a rede.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from . import tokens

UA = "Clipator/1.0 (https://github.com/JBragon/clipator; ferramenta livre de cortes)"
WIKI = "https://pt.wikipedia.org/api/rest_v1/page/summary/{}"
COMMONS = "https://commons.wikimedia.org/w/api.php"
LICENCAS = re.compile(r"^(cc0|cc[ -]by(?:[ -]sa)?(?: [\d.]+)?|public domain|pd\b.*|domínio público)", re.IGNORECASE)
MAX_TERMOS = 6
MAX_IMAGEM = 3 * 1024 * 1024
_LIGA = {"de", "do", "da", "dos", "das", "e"}
_NAO_NOME = set("a o as os um uma eu ele ela nos voce mas e entao ai depois quando todo toda agora isso esse essa este esta la aqui so".split())

Abrir = Callable[[str, float], bytes]


def ligada() -> bool:
    return os.environ.get("CLIPATOR_PESQUISA", "1").strip().lower() not in ("0", "nao", "não", "false", "off")


def _abrir(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, image/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - só https fixos acima
        return r.read(MAX_IMAGEM + 1)


def termos(pals: list[dict], maximo: int = MAX_TERMOS) -> list[str]:
    """Nomes próprios da fala ("São Paulo", "Lençóis Maranhenses") e, depois, os lugares ditos pelo nome."""
    from .curta import vocabulario, _casa

    out: list[str] = []
    atual: list[str] = []
    inicio_frase = True
    incerto = False  # a sequência começou no início da frase: "Porque", "Eles" e "Posso" também começam com maiúscula

    def _limpa(w: dict) -> str:
        return w["texto"].strip().strip(" ,.;:!?\"'“”()")

    def _maiuscula(x: str) -> bool:
        return bool(x) and x[0].isupper() and len(x) > 1 and not x.isupper()

    # palavras que aparecem com maiúscula no meio de alguma frase: essas são nome próprio também no começo
    no_meio: set[str] = set()
    ini = True
    for w in pals:
        x = _limpa(w)
        if not ini and _maiuscula(x):
            no_meio.add(x)
        ini = w["texto"].strip().endswith((".", "!", "?"))

    def fecha() -> None:
        nonlocal incerto
        while atual and atual[-1].lower() in _LIGA:
            atual.pop()
        if atual and not (incerto and len(atual) == 1):
            nome = " ".join(atual)
            if nome not in out and not (len(atual) == 1 and " ".join(tokens(nome)) in _NAO_NOME):
                out.append(nome)
        atual.clear()
        incerto = False

    for w in pals:
        bruto = w["texto"].strip()
        limpa = _limpa(w)
        if _maiuscula(limpa) and (not inicio_frase or atual or " ".join(tokens(limpa)) not in _NAO_NOME):
            if not atual and inicio_frase:
                incerto = limpa not in no_meio
            atual.append(limpa)
        elif atual and limpa.lower() in _LIGA:
            atual.append(limpa.lower())
        else:
            fecha()
        if bruto.endswith((".", "!", "?", ",", ";", ":")):
            fecha()
        inicio_frase = bruto.endswith((".", "!", "?"))
    fecha()
    # lugares ditos pelo nome (não os sugeridos por um verbo): servem de referência de cor
    ts = [(tokens(w["texto"]) or [""])[0] for w in pals]
    frase = " ".join(ts)
    for chave, v in vocabulario()["cenarios"].items():
        for raiz in v["raizes"]:
            if raiz.startswith("~"):
                continue
            p = _casa(raiz, ts, frase)
            if p >= 0:
                palavra = pals[p]["texto"].strip(" ,.;:!?\"'“”()").lower()
                if palavra and palavra not in [x.lower() for x in out]:
                    out.append(palavra)
                break
    return out[:maximo]


def _sem_html(s: Any, n: int) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(s or ""))).split())[:n]


def _wiki(termo: str, abrir: Abrir, timeout: float) -> dict[str, str]:
    try:
        d = json.loads(abrir(WIKI.format(urllib.parse.quote(termo.replace(" ", "_"))), timeout))
    except Exception:  # noqa: BLE001 - sem verbete, sem resumo
        return {}
    if not isinstance(d, dict) or d.get("type") == "disambiguation" or not d.get("extract"):
        return {}
    return {"resumo": _sem_html(d.get("extract"), 420), "descricao": _sem_html(d.get("description"), 120),
            "pagina": str(((d.get("content_urls") or {}).get("desktop") or {}).get("page") or "")[:300]}


def _commons(termo: str, abrir: Abrir, timeout: float, n: int) -> list[dict[str, str]]:
    q = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{termo} filetype:bitmap", "gsrnamespace": "6",
         "gsrlimit": str(n * 3), "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": "320"}
    try:
        d = json.loads(abrir(COMMONS + "?" + urllib.parse.urlencode(q), timeout))
    except Exception:  # noqa: BLE001
        return []
    paginas = sorted(((d.get("query") or {}).get("pages") or {}).values(), key=lambda p: p.get("index", 0)) if isinstance(d, dict) else []
    out = []
    for p in paginas:
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = _sem_html((meta.get("LicenseShortName") or {}).get("value"), 60)
        url = str(ii.get("thumburl") or "")
        if not url.startswith("https://upload.wikimedia.org/") or not LICENCAS.match(lic):
            continue
        out.append({"miniatura": url, "pagina": str(ii.get("descriptionurl") or "")[:300], "licenca": lic,
                    "autor": _sem_html((meta.get("Artist") or {}).get("value"), 120),
                    "descricao": _sem_html((meta.get("ImageDescription") or {}).get("value"), 200) or _sem_html(p.get("title"), 120)})
        if len(out) >= n:
            break
    return out


def _tons(imagens: list[bytes]) -> list[str]:
    """Até três tons: as duas áreas maiores das imagens e o acento mais vivo (a cor que dá identidade ao lugar)."""
    from PIL import Image

    from ..arte import referencias

    areas: dict[str, float] = {}
    acentos: list[tuple[float, str]] = []
    for b in imagens:
        try:
            l = referencias.analisar_imagem(Image.open(io.BytesIO(b)), "ref", k=6)
        except Exception:  # noqa: BLE001 - imagem que não abre não conta
            continue
        for c in l.paleta:
            areas[c["hex"]] = areas.get(c["hex"], 0.0) + float(c.get("area", 0))
        for c in l.acentos[:1]:
            acentos.append((float(c.get("croma", 0)), c["hex"]))
    tons = [h for h, _ in sorted(areas.items(), key=lambda kv: -kv[1])][:2]
    if acentos:
        tons.append(max(acentos)[1])
    return [t.upper() for t in tons if re.fullmatch(r"#[0-9A-Fa-f]{6}", t)][:3]


def pesquisar(ts: list[str], pasta: Path | None = None, abrir: Abrir | None = None, timeout: float = 8.0, imagens: int = 2,
              cancelar: threading.Event | None = None) -> tuple[dict[str, Any], list[str]]:
    """{termo: {resumo, descricao, pagina, imagens: [crédito], tons}} e os avisos. Cada termo fica em cache na pasta."""
    abrir = abrir or _abrir
    res: dict[str, Any] = {}
    avisos: list[str] = []
    falhas = 0
    for termo in ts[:MAX_TERMOS]:
        if cancelar is not None and cancelar.is_set():
            break
        arq = pasta / f"{hashlib.sha1(termo.lower().encode()).hexdigest()[:16]}.json" if pasta else None
        if arq is not None and arq.exists():
            try:
                res[termo] = json.loads(arq.read_text(encoding="utf-8"))
                continue
            except ValueError:
                pass
        w = _wiki(termo, abrir, timeout)
        fotos = _commons(termo, abrir, timeout, imagens)
        brutos = []
        for f in fotos:
            try:
                b = abrir(f["miniatura"], timeout)
                if len(b) <= MAX_IMAGEM:
                    brutos.append(b)
            except Exception:  # noqa: BLE001
                continue
        if not w and not fotos:
            falhas += 1
            continue
        r = {**w, "imagens": [{k: f[k] for k in ("pagina", "licenca", "autor", "descricao")} for f in fotos], "tons": _tons(brutos) if brutos else []}
        res[termo] = r
        if arq is not None:
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    if falhas:
        avisos.append(f"pesquisa de referências: nada encontrado (ou sem rede) para {falhas} de {len(ts[:MAX_TERMOS])} termo(s)")
    return res, avisos


def texto_para_ia(res: dict[str, Any]) -> str:
    if not res:
        return ""
    linhas = ["Referências pesquisadas na Wikipédia e no Wikimedia Commons sobre o que a fala cita. Use para interpretar como é o "
              "lugar, a situação e a ação de cada plano (escolha de cenário, momento, clima, adereços). Não escreva nada disto na tela."]
    for termo, r in res.items():
        partes = [x for x in (r.get("descricao"), r.get("resumo")) if x]
        fotos = "; ".join(i["descricao"] for i in r.get("imagens") or [] if i.get("descricao"))
        if fotos:
            partes.append(f"o que as fotos mostram: {fotos}")
        if partes:
            linhas.append(f"- {termo}: " + " | ".join(partes))
    return "\n".join(linhas)[:3500] if len(linhas) > 1 else ""


def creditos(res: dict[str, Any]) -> list[dict[str, str]]:
    """O que foi consultado, para a descrição do vídeo ou a revisão (as imagens não aparecem no vídeo)."""
    out = []
    for termo, r in res.items():
        if r.get("pagina"):
            out.append({"termo": termo, "fonte": "Wikipédia", "pagina": r["pagina"], "licenca": "CC BY-SA 4.0"})
        for i in r.get("imagens") or []:
            out.append({"termo": termo, "fonte": "Wikimedia Commons", **i})
    return out


# ---- imagens reais do que é citado (pessoa, empresa, produto, tecnologia) --------------------------------------------
# A IA aponta no roteiro quem e o quê a fala cita pelo nome, com o nome certo para buscar ("Iliasat Skiver" na transcrição
# é Ilya Sutskever). O Wikidata diz o que é a coisa, o nome e uma linha de contexto em português; a imagem vem do
# Wikimedia Commons (foto da pessoa, logo da empresa ou do produto, foto do produto), só com licença livre, e o crédito vai
# junto. Nada de busca de imagens do Google: ela não é aberta a programas, muda sem aviso e devolve imagem sem licença.
WIKIDATA = "https://www.wikidata.org/w/api.php"
ENTIDADE = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
TIPOS_ENTIDADE = ("pessoa", "empresa", "produto", "tecnologia", "organizacao")
LICENCAS_LIVRES = re.compile(r"(cc0|cc[ -]by|public domain|pd\b|domínio público|apache|mit\b|gfdl|gpl|bsd)", re.IGNORECASE)
MAX_ENTIDADES = 8
_HOSTS_IMAGEM = ("https://upload.wikimedia.org/", "https://thumb.wikimedia.org/")
_DESAMBIGUACAO = {"Q4167410", "Q22808320"}


def _valor(claims: dict, prop: str) -> str:
    for c in claims.get(prop) or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, str) and v:
            return v
    return ""


def _ids(claims: dict, prop: str) -> set[str]:
    out = set()
    for c in claims.get(prop) or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.add(v["id"])
    return out


def _lingua(d: dict, chave: str) -> str:
    for lg in ("pt-br", "pt"):
        v = ((d.get(chave) or {}).get(lg) or {}).get("value")
        if v:
            return str(v)
    return ""


def _arquivo_commons(nome: str, abrir: Abrir, timeout: float, largura: int = 720) -> dict[str, str]:
    q = {"action": "query", "format": "json", "titles": f"File:{nome}", "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": str(largura)}
    try:
        d = json.loads(abrir(COMMONS + "?" + urllib.parse.urlencode(q), timeout))
        p = next(iter(((d.get("query") or {}).get("pages") or {}).values()))
        ii = (p.get("imageinfo") or [{}])[0]
    except Exception:  # noqa: BLE001
        return {}
    meta = ii.get("extmetadata") or {}
    lic = _sem_html((meta.get("LicenseShortName") or {}).get("value"), 60)
    url = str(ii.get("thumburl") or ii.get("url") or "")
    if not url.startswith(_HOSTS_IMAGEM) or not LICENCAS_LIVRES.search(lic):
        return {}
    return {"url": url, "pagina": str(ii.get("descriptionurl") or "")[:300], "licenca": lic,
            "autor": _sem_html((meta.get("Artist") or {}).get("value"), 120)}


def _entidade(busca: str, tipo: str, abrir: Abrir, timeout: float) -> dict[str, Any]:
    """O item do Wikidata para a busca: nome, contexto e o arquivo de imagem (logo para empresa e produto, foto para pessoa)."""
    q = {"action": "wbsearchentities", "search": busca, "language": "pt", "uselang": "pt", "format": "json", "limit": "5", "type": "item"}
    try:
        achados = json.loads(abrir(WIKIDATA + "?" + urllib.parse.urlencode(q), timeout)).get("search") or []
    except Exception:  # noqa: BLE001
        return {}
    for a in achados[:3]:
        qid = str(a.get("id") or "")
        if not re.fullmatch(r"Q\d+", qid):
            continue
        try:
            e = json.loads(abrir(ENTIDADE.format(qid), timeout))["entities"][qid]
        except Exception:  # noqa: BLE001
            continue
        cl = e.get("claims") or {}
        tipos = _ids(cl, "P31")
        if tipos & _DESAMBIGUACAO:
            continue
        humano = "Q5" in tipos
        if (tipo == "pessoa") != humano:
            continue  # "pessoa" tem de ser gente; empresa, produto e tecnologia não podem ser
        foto, logo = _valor(cl, "P18"), _valor(cl, "P154")
        arquivo = foto if humano else (logo or foto)
        return {"qid": qid, "nome": _lingua(e, "labels") or str(a.get("label") or busca), "contexto": _lingua(e, "descriptions"),
                "arquivo": arquivo, "logo": bool(not humano and logo and arquivo == logo)}
    return {}


def imagens_reais(entidades: list[dict], pasta: Path, abrir: Abrir | None = None, timeout: float = 8.0,
                  cancelar: threading.Event | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Para cada {termo, tipo, busca}: {termo, tipo, nome, contexto, arquivo (relativo à pasta do clip), logo, credito}.

    A imagem fica em `pasta/pesquisa/imagens/` (cache por busca); sem imagem livre, a entidade sai e o aviso diz.
    """
    abrir = abrir or _abrir
    out: list[dict[str, Any]] = []
    faltou: list[str] = []
    dest = pasta / "pesquisa" / "imagens"
    for ent in entidades[:MAX_ENTIDADES]:
        if cancelar is not None and cancelar.is_set():
            break
        busca = " ".join(str(ent.get("busca") or ent.get("termo") or "").split())[:80]
        tipo = ent.get("tipo") if ent.get("tipo") in TIPOS_ENTIDADE else "empresa"
        if not busca:
            continue
        chave = hashlib.sha1(f"{tipo}|{busca.lower()}".encode()).hexdigest()[:16]
        meta = dest / f"{chave}.json"
        r: dict[str, Any] | None = None
        if meta.exists():
            try:
                r = json.loads(meta.read_text(encoding="utf-8"))
            except ValueError:
                r = None
        if r is None:
            r = {}
            e = _entidade(busca, tipo, abrir, timeout)
            img = _arquivo_commons(e["arquivo"], abrir, timeout) if e.get("arquivo") else {}
            if not img and tipo in ("produto", "tecnologia"):  # produto sem imagem no Wikidata: a foto livre mais citada no Commons
                fotos = _commons(busca, abrir, timeout, 1)
                if fotos:
                    img = {"url": fotos[0]["miniatura"].replace("/320px-", "/720px-"), **{k: fotos[0][k] for k in ("pagina", "licenca", "autor")}}
            if not img and tipo in ("produto", "tecnologia") and len(busca.split()) > 1:  # "Nvidia B300": o logo de quem faz
                marca = _entidade(busca.split()[0], "empresa", abrir, timeout)
                img = _arquivo_commons(marca["arquivo"], abrir, timeout) if marca.get("arquivo") else {}
                if img:
                    e = {"nome": busca, "contexto": f"produto da {marca['nome']}", "logo": marca.get("logo"), "qid": marca.get("qid", "")}
            if img:
                try:
                    b = abrir(img["url"], timeout)
                except Exception:  # noqa: BLE001
                    b = b""
                ext = ".png" if b[:8] == b"\x89PNG\r\n\x1a\n" else (".jpg" if b[:3] == b"\xff\xd8\xff" else "")
                if b and ext and len(b) <= MAX_IMAGEM and not e.get("contexto") and e.get("nome"):  # sem linha em português no
                    e = {**e, "contexto": _wiki(e["nome"], abrir, timeout).get("descricao", "")}  # Wikidata: a da Wikipédia
                if b and ext and len(b) <= MAX_IMAGEM:
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / f"{chave}{ext}").write_bytes(b)
                    r = {"nome": (e.get("nome") or busca)[:40], "contexto": (e.get("contexto") or "")[:90], "logo": bool(e.get("logo")),
                         "arquivo": f"pesquisa/imagens/{chave}{ext}", "qid": e.get("qid", ""),
                         "credito": {"fonte": "Wikimedia Commons", "pagina": img.get("pagina", ""), "licenca": img.get("licenca", ""),
                                     "autor": img.get("autor", "")}}
            dest.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if r.get("arquivo") and (pasta / r["arquivo"]).is_file():
            out.append({"termo": str(ent.get("termo") or busca)[:60], "tipo": tipo, **r})
        else:
            faltou.append(busca)
    avisos = [f"imagens reais: nada livre encontrado para {', '.join(faltou[:5])}"] if faltou else []
    return out, avisos
