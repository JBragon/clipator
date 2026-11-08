"""As direções de arte do Clipator: estilos com renderizador próprio, ligados à fala e editáveis.

Uma direção é um estilo normal (dados/estilos/arte-<id>.md, `direcao: {modo: arte, arte: <id>}`) cujas cenas são itens
"cena" do edicao.json com `params.cena == "arte"`: não existe outra linha do tempo. Aqui ficam o registro, a validação
dos parâmetros (allowlist tirada de dados/artes/<id>.json), as âncoras, o planejador sem IA, a ficha e a composição.
Os renderizadores (código nosso, sem nada vindo da IA além de texto) moram em editoriais.py, graficos.py, cenarios.py e
tres.py. O texto de runtime de cada direção (dados/artes/<id>.md) só entra no pedido quando ela é a escolhida.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from ..workspace import _dados
from . import kit  # noqa: F401
from .kit import CSS, T0, Ctx

VERSAO_RENDERER = 2  # muda quando o desenho de uma direção muda (entra na camada e, com ela, no cache)
PARAMETROS_COMUNS: dict[str, dict[str, Any]] = {
    "leve": {"tipo": "booleano"},  # a alternativa leve da direção, sem máscaras nem texturas
    "semente": {"tipo": "inteiro", "minimo": 0, "maximo": 4294967295},
}
CORES = ("fundo", "superficie", "texto", "texto_suave", "primaria", "destaque")
EXTENSOES_MIDIA = (".png", ".jpg", ".jpeg", ".webp")


# ---- registro --------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def especificacoes() -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted(_dados("artes").glob("*.json")):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def existe(slug: str | None) -> bool:
    return bool(slug) and slug in especificacoes()


def especificacao(slug: str) -> dict[str, Any]:
    try:
        return especificacoes()[slug]
    except KeyError:
        raise ValueError(f"Direção de arte desconhecida: {slug}") from None


def texto_runtime(slug: str) -> str:
    """A ficha curta desta direção para o planejamento (só a escolhida entra no pedido à IA)."""
    p = _dados("artes") / f"{slug}.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def renderizadores() -> dict[str, Any]:
    from . import cenarios, cortes, editoriais, geo, graficos, tres

    return {**editoriais.DIRECOES, **graficos.DIRECOES, **cenarios.DIRECOES, **tres.DIRECOES, **cortes.DIRECOES, **geo.DIRECOES}


# ---- parâmetros ------------------------------------------------------------------------------------------------
def limites(slug: str) -> dict[str, dict[str, Any]]:
    return {**especificacao(slug).get("limites_parametros", {}), **PARAMETROS_COMUNS}


def validar_parametros(slug: str, valores: Any, estrito: bool = True) -> dict[str, Any]:
    """Só as chaves da direção, nos limites dela. `estrito`: chave desconhecida é recusada com mensagem."""
    if not isinstance(valores, dict):
        return {}
    lim = limites(slug)
    out: dict[str, Any] = {}
    for k, v in valores.items():
        regra = lim.get(k)
        if regra is None:
            if estrito:
                raise ValueError(f"Parâmetro “{k}” não existe em {especificacao(slug)['nome']}.")
            continue
        tipo = regra.get("tipo")
        if tipo == "booleano":
            out[k] = bool(v)
        elif tipo == "texto":
            if v in regra.get("opcoes", []):
                out[k] = v
            elif estrito:
                raise ValueError(f"Valor inválido para {k}: {v}")
        else:
            try:
                n = float(v)
            except (TypeError, ValueError):
                if estrito:
                    raise ValueError(f"{k} precisa ser um número.") from None
                continue
            if n != n:
                continue
            n = max(float(regra["minimo"]), min(float(regra["maximo"]), n)) if "minimo" in regra else n
            out[k] = int(round(n)) if tipo == "inteiro" else round(n, 4)
    return out


def parametros_resolvidos(slug: str, *camadas: Any) -> dict[str, Any]:
    """O padrão da direção, depois cada camada (estilo, cena), já validadas."""
    out = dict(especificacao(slug).get("parametros_visuais", {}))
    for c in camadas:
        out.update(validar_parametros(slug, c, estrito=False))
    return out


# ---- cena ------------------------------------------------------------------------------------------------------
def _limpa(v: Any, lim: int) -> str:
    return " ".join(str(v or "").split())[:lim]


def normalizar_arte(p: dict[str, Any]) -> dict[str, Any]:
    """Os parâmetros de uma cena de arte (vêm da tela, da IA ou do planejador). Direção desconhecida vira erro."""
    slug = str(p.get("arte") or "")
    especificacao(slug)
    out: dict[str, Any] = {"cena": "arte", "arte": slug}
    for k, lim in (("texto", 120), ("nota", 40), ("dado", 16), ("etiqueta", 40), ("ancora", 200), ("tl", 16)):
        v = _limpa(p.get(k), lim)
        if v:
            out[k] = v
    if out.get("nota") and len(out["nota"].split()) > 4:
        out["nota"] = " ".join(out["nota"].split()[:4])
    try:
        out["ocorrencia"] = max(1, min(1000, int(p.get("ocorrencia") or 1)))
    except (TypeError, ValueError):
        out["ocorrencia"] = 1
    itens = p.get("itens")
    if isinstance(itens, list):
        limpos = [_limpa(x, 48) for x in itens if str(x).strip()][:6]
        if limpos:
            out["itens"] = limpos
    from ..desenho import PECAS

    if p.get("peca") in PECAS:
        out["peca"] = p["peca"]
    if isinstance(p.get("corte"), dict):  # as cinco direções guiadas pela fala: quem, o quê e qual ação
        from . import cortes

        if cortes.eh_corte(slug):
            out["corte"] = cortes.normalizar_corte(slug, p["corte"])
    if isinstance(p.get("curta"), dict):  # modo curta: lugar, gente, ação, situação e montagem do plano (artes/curta.py)
        from . import cortes

        if slug in cortes.ACOES:
            from . import curta

            out["curta"] = curta.normalizar(p["curta"])
    if isinstance(p.get("midia"), str) and p["midia"].strip():
        out["midia"] = p["midia"].strip()[:500]
    for k in ("credito", "licenca"):
        v = _limpa(p.get(k), 200)
        if v:
            out[k] = v
    cores = {k: v.upper() for k, v in (p.get("cores") or {}).items() if k in CORES and isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)} \
        if isinstance(p.get("cores"), dict) else {}
    if cores:
        out["cores"] = cores  # moram na cena para desfazer uma versão recuperar também as cores
    par = validar_parametros(slug, p.get("parametros"), estrito=False)
    if par:
        out["parametros"] = par
    return out


# ---- âncoras ---------------------------------------------------------------------------------------------------
def tokens(s: str) -> list[str]:
    """Busca sem caixa, acento nem pontuação (o texto na tela continua o original)."""
    n = unicodedata.normalize("NFD", unicodedata.normalize("NFC", s).lower())
    n = "".join(c for c in n if unicodedata.category(c) != "Mn")
    return [t for t in (re.sub(r"[^\w%$]+", "", x) for x in n.split()) if t]


def achar(ancora: str, ocorrencia: int, pals: list[dict]) -> tuple[int, int] | None:
    """(primeira, última palavra) da n-ésima ocorrência contígua do trecho; None se não existe (sem aproximar)."""
    alvo = tokens(ancora)
    ws = [(tokens(w["texto"]) or [""])[0] for w in pals]
    n = 0
    for i in range(max(0, len(ws) - len(alvo) + 1)):
        if alvo and ws[i:i + len(alvo)] == alvo:
            n += 1
            if n == ocorrencia:
                return i, i + len(alvo) - 1
    return None


def ocorrencia_em(pals: list[dict], i: int, j: int) -> int:
    """Qual ocorrência do trecho pals[i..j] é esta (contando do começo do clip)."""
    alvo = tokens(" ".join(w["texto"] for w in pals[i:j + 1]))
    ws = [(tokens(w["texto"]) or [""])[0] for w in pals]
    return sum(1 for k in range(i + 1) if ws[k:k + len(alvo)] == alvo) or 1


def assinatura_timeline(tl: Any) -> str:
    """Muda quando o clip muda de tempo (trecho ou cortes internos): é aí que as âncoras precisam ser refeitas."""
    return hashlib.sha1(json.dumps([[round(a, 3), round(b, 3)] for a, b in tl.trechos]).encode()).hexdigest()[:12]


def reancorar(itens: list[Any], pals: list[dict], dur: float, assinatura: str) -> tuple[list[Any], list[str], bool]:
    """Depois de mudar a edição: refaz o tempo das cenas pela âncora; trecho removido tira a cena, com aviso.

    Com a mesma timeline nada muda (o usuário pode ter movido a cena à mão). Devolve (itens, avisos, mudou).
    """
    avisos: list[str] = []
    out, mudou = [], False
    for it in itens:
        p = it.params
        if p.get("cena") != "arte" or not p.get("ancora") or p.get("tl") == assinatura:
            out.append(it)
            continue
        mudou = True
        par = achar(p["ancora"], int(p.get("ocorrencia") or 1), pals)
        if par is None:
            avisos.append(f"Cena omitida: o trecho “{p['ancora'][:60]}” não está mais na fala.")
            continue
        duracao = it.fim - it.inicio
        ini = max(0.0, pals[par[0]]["inicio"] - 0.1)
        fim = min(dur, max(ini + duracao, pals[par[1]]["fim"] + 0.2))
        out.append(it.model_copy(update={"inicio": round(ini, 3), "fim": round(fim, 3), "params": {**p, "tl": assinatura}}))
    for a, b in zip(out, out[1:]):  # sem duas ao mesmo tempo
        if a.params.get("cena") == "arte" and b.params.get("cena") == "arte" and a.fim > b.inicio:
            a.fim = b.inicio
    return [i for i in out if i.fim - i.inicio >= 0.5], avisos, mudou


# ---- planejador sem IA -----------------------------------------------------------------------------------------
_VAZIAS = set("a o as os um uma uns umas de do da dos das em no na nos nas por para pra com sem que e ou mas se como mais muito "
              "ele ela eles elas eu voce isso isto esse essa este esta foi era ser ter tem ao aos ja nao sim so me te lhe seu sua".split())
_NUMERO = re.compile(r"^(R\$)?\d+(?:[.,]\d+)*(%|x|mil|k)?$", re.IGNORECASE)


def _frases(pals: list[dict], max_pal: int = 14) -> list[tuple[int, int]]:
    out, ini = [], 0
    for k, w in enumerate(pals):
        fim_frase = w["texto"].rstrip().endswith((".", "!", "?"))
        if fim_frase or k - ini + 1 >= max_pal or k == len(pals) - 1:
            out.append((ini, k))
            ini = k + 1
    return out


def _peca_do_texto(texto: str) -> str | None:
    from ..desenho import PECAS

    ts = set(tokens(texto))
    for nome, (desc, _) in PECAS.items():
        chaves = {t for t in tokens(desc.replace(",", " ")) if len(t) > 3 and t not in _VAZIAS} | {nome}
        if ts & chaves:
            return nome
    return None


def conteudo_da_fala(pals: list[dict], i: int, j: int) -> dict[str, Any]:
    """Texto, itens, nota e dado de uma cena, só com palavras ditas no trecho."""
    ws = [w["texto"].strip() for w in pals[i:j + 1]]
    limpas = [w.strip(" ,.;:!?\"'“”()") for w in ws]
    texto = " ".join(ws).rstrip(" ,;:")
    partes, atual = [], []
    for w in ws:
        atual.append(w.strip(" ,.;:!?\"'“”()"))
        if w.endswith((",", ";", ":")) or len(atual) >= 4:
            partes.append(" ".join(atual))
            atual = []
    if atual:
        partes.append(" ".join(atual))
    dado = next((x for x in limpas if _NUMERO.match(x)), "")
    fortes = sorted((x for x in limpas if tokens(x) and tokens(x)[0] not in _VAZIAS), key=lambda x: (-len(x), limpas.index(x)))
    return {"texto": texto, "itens": [p for p in partes if p][:4], "nota": (fortes[0] if fortes else "")[:40], "dado": dado,
            "peca": _peca_do_texto(texto)}


def planejar_regras(slug: str, pals: list[dict], dur: float, assinatura: str = "", parametros: dict | None = None) -> list[dict]:
    """Sem IA: uma cena por frase, com o texto da própria fala. Só usa o que foi dito; os tempos vêm das palavras."""
    if not pals:
        return []
    grupos: list[list[int]] = []
    for a, b in _frases(pals):
        if grupos and (pals[b]["fim"] - pals[grupos[-1][0]]["inicio"] < 2.2):
            grupos[-1][1] = b  # frase curta demais para ler sozinha
        else:
            grupos.append([a, b])
    out = []
    for n, (a, b) in enumerate(grupos):
        ini = 0.0 if n == 0 else max(0.0, pals[a]["inicio"] - 0.1)
        prox = pals[grupos[n + 1][0]]["inicio"] - 0.1 if n + 1 < len(grupos) else dur
        ancora = " ".join(w["texto"] for w in pals[a:b + 1])
        params = {"cena": "arte", "arte": slug, "ancora": ancora, "ocorrencia": ocorrencia_em(pals, a, b), "tl": assinatura,
                  **conteudo_da_fala(pals, a, b)}
        from . import cortes

        if cortes.eh_corte(slug):
            params["corte"] = cortes.da_fala(slug, pals[a:b + 1], pals[:a])
            if slug == "geo-em-cena" and not (params["corte"]["lugares"] or params["corte"]["pendencias"]):
                continue  # frase sem lugar: o mapa segura o que já está aceso
            if slug in cortes.ACOES:
                from . import curta

                params["curta"] = curta.da_fala(pals[a:b + 1])
        if parametros:
            params["parametros"] = parametros
        out.append({"inicio": round(ini, 3), "fim": round(min(prox, dur), 3), "params": normalizar_arte(params),
                    "motivo": "Frase da fala"})
    return _montar_curta(slug, [c for c in out if c["fim"] - c["inicio"] >= 0.5])


def _montar_curta(slug: str, cenas: list[dict]) -> list[dict]:
    """Modo curta: a montagem olha a sequência inteira (continuidade do lugar, variação de plano, transições)."""
    from . import cortes, curta

    if slug not in cortes.ACOES or not any("curta" in c["params"] for c in cenas):
        return cenas
    com = [c for c in cenas if "curta" in c["params"]]
    for c, cu in zip(com, curta.encadear([c["params"]["curta"] for c in com], [any(curta._vale_objeto(o) for o in (c["params"].get("corte") or {}).get("objetos") or []) for c in com])):
        c["params"]["curta"] = curta.normalizar(cu)
    return cenas


def cenas_do_curta(slug: str, planos: list[dict], pals: list[dict], assinatura: str = "", parametros: dict | None = None) -> list[dict]:
    """Os planos do roteiro do curta (curta.de_roteiro) viram cenas de arte: âncora, texto da fala, corte e curta."""
    from . import cortes

    out = []
    for p in planos:
        ij = achar(p["ancora"], 1, pals)
        for n in range(2, 6):
            outra = achar(p["ancora"], n, pals)
            if outra and ij and abs(pals[outra[0]]["inicio"] - p["inicio"]) < abs(pals[ij[0]]["inicio"] - p["inicio"]):
                ij = outra
        if ij is None:
            continue
        i, j = ij
        fim = next((x for x in range(j, len(pals)) if pals[x]["inicio"] >= p["fim"]), len(pals)) - 1
        params = {"cena": "arte", "arte": slug, "ancora": " ".join(w["texto"] for w in pals[i:j + 1]), "ocorrencia": ocorrencia_em(pals, i, j),
                  "tl": assinatura, **conteudo_da_fala(pals, i, max(j, fim)), "corte": cortes.da_fala(slug, pals[i:max(j, fim) + 1], pals[:i]),
                  "curta": p["curta"]}
        if parametros:
            params["parametros"] = parametros
        out.append({"inicio": p["inicio"], "fim": p["fim"], "params": normalizar_arte(params), "motivo": p.get("descricao", "")[:200]})
    return _montar_curta(slug, out)


# ---- planejamento com IA ---------------------------------------------------------------------------------------
SCHEMA_ARTE: dict[str, Any] = {
    "type": "object",
    "properties": {"cenas": {"type": "array", "items": {"type": "object", "properties": {
        "indice": {"type": "number"}, "texto": {"type": "string"}, "itens": {"type": "array", "items": {"type": "string"}},
        "nota": {"type": "string"}, "dado": {"type": "string"}, "peca": {"type": "string"}},
        "required": ["indice", "texto", "itens", "nota", "dado", "peca"], "additionalProperties": False}}},
    "required": ["cenas"], "additionalProperties": False,
}


def schema_arte(slug: str) -> dict[str, Any]:
    """O formato de resposta que a IA recebe: o das cinco direções guiadas pela fala tem objetos e ação."""
    from . import cortes

    return cortes.schema(slug) if cortes.eh_corte(slug) else SCHEMA_ARTE


def prompt_arte(slug: str, roteiro: list[dict], extra: str = "", fala: str = "") -> str:
    from ..desenho import PECAS
    from . import cortes

    if cortes.eh_corte(slug):
        return cortes.prompt(slug, roteiro, extra, fala)

    cenas = json.dumps([{"indice": k, "ancora": c.get("ancora", ""), "duracao": round(c["fim"] - c["inicio"], 1), "etiqueta": c.get("etiqueta", ""),
                         "descricao": c.get("descricao", ""), "dado": c.get("dado", "")} for k, c in enumerate(roteiro)], ensure_ascii=False)
    return (f"{texto_runtime(slug)}\n\nPara cada cena do roteiro devolva o conteúdo da tela: 'texto' (a frase da cena, até 14 palavras, "
            "tirada da fala), 'itens' (até 4 rótulos curtos ditos na fala, na ordem da fala, ou []), 'nota' (até 4 palavras), 'dado' (o número "
            f"dito, ou vazio) e 'peca' (um destes desenhos, ou vazio: {', '.join(PECAS)}). Nada que não foi dito.\n"
            + (f"{extra[:3000]}\n" if extra else "") + f"Cenas: {cenas}")


def de_resposta_ia(slug: str, resp: Any, roteiro: list[dict], pals: list[dict], assinatura: str = "", parametros: dict | None = None) -> list[dict]:
    """Cada cena da IA conferida: número tem de ter sido dito; o que falta vem da própria fala do trecho."""
    from ..direcao import _na_fala

    por_indice = {}
    for c in (resp or {}).get("cenas") or [] if isinstance(resp, dict) else []:
        if isinstance(c, dict):
            try:
                por_indice[int(c.get("indice"))] = c
            except (TypeError, ValueError):
                continue
    out = []
    for k, r in enumerate(roteiro):
        ij = achar(r.get("ancora", ""), 1, pals)
        for n in range(2, 6):  # o roteiro traz o tempo: a ocorrência certa é a mais perto dele
            outra = achar(r.get("ancora", ""), n, pals)
            if outra and ij and abs(pals[outra[0]]["inicio"] - r["inicio"]) < abs(pals[ij[0]]["inicio"] - r["inicio"]):
                ij = outra
        if ij is None:
            continue
        i, j = ij
        fim_cena = next((x for x in range(j, len(pals)) if pals[x]["inicio"] >= r["fim"]), len(pals)) - 1
        base = conteudo_da_fala(pals, i, max(j, fim_cena))
        c = por_indice.get(k, {})
        texto = str(c.get("texto") or "").strip()
        if texto and not _na_fala(texto, pals, 0.6):
            texto = ""
        dado = str(c.get("dado") or "").strip()
        if dado and not _na_fala(dado, pals, 0.5):
            dado = ""
        itens = [x for x in (c.get("itens") or []) if isinstance(x, str) and _na_fala(x, pals, 0.5)]
        params = {"cena": "arte", "arte": slug, "ancora": " ".join(w["texto"] for w in pals[i:j + 1]), "ocorrencia": ocorrencia_em(pals, i, j),
                  "tl": assinatura, "texto": texto or base["texto"], "itens": itens or base["itens"],
                  "nota": str(c.get("nota") or "") or base["nota"], "dado": dado or base["dado"],
                  "etiqueta": r.get("etiqueta", ""), "peca": c.get("peca") or base["peca"]}
        from . import cortes

        if cortes.eh_corte(slug):
            params["corte"] = cortes.de_resposta(slug, c, pals, i, max(j, fim_cena))
            if slug in cortes.ACOES:
                from . import curta

                params["curta"] = curta.de_resposta(c.get("curta"), pals[i:max(j, fim_cena) + 1])
        if parametros:
            params["parametros"] = parametros
        out.append({"inicio": r["inicio"], "fim": r["fim"], "params": normalizar_arte(params), "motivo": r.get("descricao", "")[:200]})
    return _montar_curta(slug, out)


# ---- ficha, contraste e mídia ----------------------------------------------------------------------------------
def ficha_base(slug: str) -> dict[str, Any]:
    """A ficha da direção: paleta, fontes e sons moram no predefinido da DA (dados/arte/presets/<id>.yaml)."""
    from ..arte.compilar import para_ficha
    from ..arte.guia import da_da_referencia

    return {"nome": f"arte-{slug}", **para_ficha(da_da_referencia(slug)[0])}


def _lum(hexa: str) -> float:
    v = [int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, gr, b = (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v)
    return 0.2126 * r + 0.7152 * gr + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def ficha_legivel(f: Any) -> tuple[Any, list[str]]:
    """Depois da herança (preset, canal, clip): o texto precisa de 4,5:1 no fundo e na superfície. Corrige e avisa."""
    pior = min(contraste(f.texto, f.fundo), contraste(f.texto, f.superficie))
    if pior >= 4.5:
        return f, []
    melhor = max(("#111111", "#FFFFFF"), key=lambda c: min(contraste(c, f.fundo), contraste(c, f.superficie)))
    return f.model_copy(update={"texto": melhor}), [f"Cor do texto trocada por {melhor}: o contraste com o fundo ficava em {pior:.1f}:1."]


def resolver_midia(raiz: Path, relativo: str) -> Path:
    """O arquivo dentro da pasta de mídia do canal. Recusa caminho absoluto, '..', endereço remoto e fuga por link."""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", relativo) or relativo.startswith(("/", "\\")) or ".." in re.split(r"[\\/]", relativo):
        raise ValueError(f"Caminho de mídia recusado: {relativo}")
    base = raiz.resolve()
    p = (base / relativo).resolve()
    if base not in p.parents:
        raise ValueError(f"Caminho de mídia recusado: {relativo}")
    if p.suffix.lower() not in EXTENSOES_MIDIA:
        raise ValueError(f"Tipo de mídia não aceito: {p.suffix}")
    return p


def copiar_midias(cenas: list[dict], raiz: Path, pasta: Path) -> list[str]:
    """Copia as mídias das cenas para a pasta da camada com o hash no nome (arquivo novo no mesmo caminho muda o documento).

    Cada cena ganha `_midia` (o caminho local); sem o arquivo, fica a alternativa da direção e o aviso.
    """
    avisos: list[str] = []
    for c in cenas:
        rel = c["params"].get("midia")
        if c["params"].get("cena") != "arte" or not rel:
            continue
        try:
            p = resolver_midia(raiz, rel)
            if not p.is_file():
                raise FileNotFoundError(rel)
        except (ValueError, FileNotFoundError, OSError) as exc:
            avisos.append(f"Mídia não usada ({exc}): a cena saiu com a alternativa da direção.")
            continue
        h = hashlib.sha1(p.read_bytes()).hexdigest()[:16]
        destino = pasta / "midias" / f"{h}{p.suffix.lower()}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists():
            shutil.copyfile(p, destino)
        c["_midia"] = f"midias/{destino.name}"
    return avisos


def encostar(itens: list[Any], dur: float) -> list[Any]:
    """Cada cena fica no ar até a próxima: quando a DA tira uma cena pelo ritmo, a anterior segura a leitura."""
    ordem = sorted(itens, key=lambda i: i.inicio)
    return [i.model_copy(update={"fim": round(ordem[k + 1].inicio if k + 1 < len(ordem) else dur, 3)}) for k, i in enumerate(ordem)]


def palavras_da_cena(pals: list[dict], ini: float, fim: float) -> list[dict]:
    return [{"texto": w["texto"], "inicio": round(max(0.0, w["inicio"] - ini), 3), "fim": round(w["fim"] - ini, 3)}
            for w in pals if ini - 0.05 <= w["inicio"] < fim]


def ajustar_layout(projeto: Any, clip_id: str, layout: dict[str, Any]) -> dict[str, Any]:
    """Grava a composição escolhida (tela dividida ou janela num canto). Vale para qualquer estilo com animação."""
    from .. import edicao, melhorar
    from ..models import LayoutArte
    from ..timeline import Timeline

    clip, pasta = projeto.clip(clip_id)
    est = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)[0]
    if not est.direcao.ativa:
        raise ValueError("Este estilo não tem animação junto com o vídeo.")
    novo = LayoutArte.model_validate(layout)
    if novo.layout == "janela" and novo.janela_canto is None:
        novo = novo.model_copy(update={"janela_canto": est.direcao.janela_canto or "inferior-direito"})
    melhorar.garantir_inicial(projeto, clip_id)
    doc = edicao.carregar(pasta)
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    edicao.salvar(pasta, doc.model_copy(update={"layout_arte": novo}), tl.duracao)
    nome = "tela dividida" if novo.layout == "em-cima" else f"janela no canto {novo.janela_canto}"
    return {"versao": melhorar.registrar(projeto, clip_id, "manual", "composição do clip", [f"composição: {nome}"]),
            "layout": novo.model_dump(exclude_none=True)}


def ajustar(projeto: Any, clip_id: str, cenas: Any = None, parametros: Any = None, cores: Any = None, layout: Any = None) -> dict[str, Any]:
    """O painel da direção: texto, ordem, parâmetros, cores e composição, sem IA. Vira uma versão nova da edição.

    `cenas`: [{id, texto, nota, dado, itens}] na ordem desejada (a ordem troca as cenas de lugar nos mesmos horários).
    Parâmetro fora da lista da direção é recusado antes de gravar qualquer coisa.
    """
    from .. import edicao, melhorar

    if layout:
        r = ajustar_layout(projeto, clip_id, layout)
        if not cenas and parametros is None and cores is None:
            return {**r, "cenas": 0}
    clip, pasta = projeto.clip(clip_id)
    est = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)[0]
    slug = est.direcao.arte
    if est.direcao.modo != "arte" or not existe(slug):
        raise ValueError("Este clip não usa uma direção de arte com renderizador próprio.")
    par = validar_parametros(slug, parametros, estrito=True) if parametros is not None else None
    melhorar.garantir_inicial(projeto, clip_id)
    doc = edicao.carregar(pasta)
    atuais = [i for i in doc.itens if i.tipo == "cena" and i.params.get("cena") == "arte"]
    por_id = {i.id: i for i in atuais}
    ordem = [por_id[c["id"]] for c in cenas or [] if isinstance(c, dict) and c.get("id") in por_id]
    ordem += [i for i in atuais if i not in ordem]
    horarios = sorted((i.inicio, i.fim) for i in atuais)
    novos = {str(c.get("id")): c for c in cenas or [] if isinstance(c, dict)}
    resumo: list[str] = []
    saida = []
    for it, (ini, fim) in zip(ordem, horarios):
        p = dict(it.params)
        c = novos.get(it.id, {})
        for k in ("texto", "nota", "dado", "etiqueta", "itens"):
            if k in c:
                p[k] = c[k]
        if c.get("acao") and isinstance(p.get("corte"), dict):
            p["corte"] = {**p["corte"], "acao": c["acao"]}
        if c.get("escolha") and isinstance(p.get("corte"), dict) and slug == "geo-em-cena":  # a resposta a uma pendência de lugar
            from . import geo

            e = c["escolha"]
            p["corte"] = geo.escolher(p["corte"], str(e.get("falado")), str(e.get("nivel")), str(e.get("id")))
        if par is not None:
            p["parametros"] = {**(p.get("parametros") or {}), **par}
        if isinstance(cores, dict):
            p["cores"] = cores
        saida.append(it.model_copy(update={"inicio": ini, "fim": fim, "params": normalizar_arte(p)}))
    if cenas:
        resumo.append("texto e ordem das cenas")
    if par:
        resumo.append("parâmetros: " + ", ".join(f"{k}={v}" for k, v in par.items()))
    if isinstance(cores, dict):
        resumo.append("cores ajustadas")
    itens = [i for i in doc.itens if not (i.tipo == "cena" and i.params.get("cena") == "arte")] + saida
    from ..timeline import Timeline

    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    edicao.salvar(pasta, doc.model_copy(update={"itens": itens, "cenas_planejadas": True}), tl.duracao)
    return {"versao": melhorar.registrar(projeto, clip_id, "manual", "ajuste da direção de arte", resumo), "cenas": len(saida)}


def resumo_painel(slug: str, itens: list[Any]) -> dict[str, Any]:
    """O que o painel precisa saber da direção: limites dos parâmetros, valores em uso e as cenas editáveis."""
    e = especificacao(slug)
    cenas = [i for i in itens if i.tipo == "cena" and i.params.get("cena") == "arte"]
    par = parametros_resolvidos(slug, cenas[0].params.get("parametros") if cenas else None)
    return {"id": slug, "nome": e["nome"], "alternativa": e.get("alternativa_leve", ""), "limites": limites(slug), "parametros": par,
            "acoes": _acoes_do(slug),
            "cenas": [{"id": i.id, "inicio": i.inicio, "fim": i.fim, "texto": i.params.get("texto", ""), "nota": i.params.get("nota", ""),
                       "dado": i.params.get("dado", ""), "itens": i.params.get("itens", []), "ancora": i.params.get("ancora", ""),
                       **({"acao": i.params["corte"].get("acao", ""),
                           "objetos": [o.get("nome", "") for o in i.params["corte"].get("objetos", [])],
                           "lugares": [f"{x['falado']} ({x['descricao']})" for x in i.params["corte"].get("lugares", [])],
                           "pendencias": i.params["corte"].get("pendencias", [])} if i.params.get("corte") else {})} for i in cenas]}


def _acoes_do(slug: str) -> list[str]:
    from . import cortes, geo

    return list(geo.ACOES) if slug == geo.SLUG else list(cortes.ACOES.get(slug, ()))


# ---- composição ------------------------------------------------------------------------------------------------
class Camada:
    """O que uma camada de arte precisa: retângulo local, zona segura e o renderizador da direção."""

    def __init__(self, slug: str, largura: int, altura: int, topo: float, alt: float, zona: Any = None, duracao: float = 0.0,
                 parametros: dict | None = None, ficha: Any = None, geo: Any = None) -> None:
        self.slug, self.duracao, self.parametros, self.ficha, self.geo = slug, duracao, parametros or {}, ficha, geo
        self.render = renderizadores()[slug]
        self.W = 1000.0
        self.H = round(1000.0 * (altura * alt) / largura, 1)
        por_px = 1000.0 / largura
        margem = 40.0
        y0, y1 = margem, self.H - margem
        x0, x1 = margem + 10, self.W - margem - 10
        if zona is not None:
            y0 = max(y0, (zona.topo - topo) * altura * por_px)
            x0 = max(x0, zona.esquerda * 1000.0)
            if topo + alt > 0.6:  # os botões laterais só cobrem a metade de baixo da tela
                x1 = min(x1, 1000.0 * (1 - zona.direita))
            y1 = min(y1, (1 - zona.base - topo) * altura * por_px)
        if y1 - y0 < 200:  # formato muito baixo: mantém a arte legível em vez de encolher tudo
            y0, y1 = margem * 0.6, self.H - margem * 0.6
        self.seguro = (x0, y0, x1, y1)
        self.leve = bool(parametros_resolvidos(slug, parametros).get("leve"))

    def ctx(self, p: dict, ini: float, fim: float, k: int, total: int, palavras: list[dict] | None, midia: str | None) -> Ctx:
        par = parametros_resolvidos(self.slug, self.parametros, p.get("parametros"))
        semente = int(par.get("semente", especificacao(self.slug).get("amostra", {}).get("semente", 42)))
        f = self.ficha
        return Ctx(self.W, self.H, self.seguro, p, par, fim - ini, semente, k, total, bool(par.get("leve")) or self.leve, palavras or [],
                   midia, getattr(f, "fonte_titulo", "Bebas Neue"), getattr(f, "fonte_corpo", "Montserrat ExtraBold"),
                   {k: getattr(f, k) for k in CORES} if f is not None else ficha_base(self.slug))

    def cena(self, p: dict, ini: float, fim: float, k: int, total: int, palavras: list[dict] | None = None, midia: str | None = None) -> str:
        c = self.ctx(p, ini, fim, k, total, palavras, midia)
        marca = T0.set(ini)
        try:
            corpo = self.render.cena(c)
        finally:
            T0.reset(marca)
        return (f'<svg class="arte-palco arte-sai" style="--saida:{max(0.0, fim - 0.22):.3f}s" viewBox="0 0 {self.W:g} {self.H:g}" '
                f'preserveAspectRatio="xMidYMid meet">{corpo}</svg>')

    def fundo(self) -> str:
        c = self.ctx({}, 0.0, self.duracao, 0, 1, [], None)
        corpo = self.render.fundo(c) if hasattr(self.render, "fundo") else ""
        return (f'<svg class="arte-fundo" viewBox="0 0 {self.W:g} {self.H:g}" preserveAspectRatio="xMidYMid slice">{corpo}</svg>') if corpo else ""

    def css(self) -> str:
        relogio = f"@keyframes relogio3d {{ from {{ --t3: 0; }} to {{ --t3: {self.duracao:.3f}; }} }}\n" if hasattr(self.render, "extras") else ""
        return self._cores() + CSS + getattr(self.render, "css", "") + relogio + f"\n/* arte {self.slug} v{VERSAO_RENDERER} */\n"

    def _cores(self) -> str:
        """As cores de texto que dependem do fundo: medidas aqui, depois da herança, para nunca ficar abaixo de 4,5:1."""
        f = self.ficha
        if f is None:
            return ""
        acento = f.primaria if contraste(f.primaria, f.fundo) >= 4.5 else f.texto

        def sobre(cor: str) -> str:
            return max((f.fundo, f.texto, "#FFFFFF", "#111111"), key=lambda c: contraste(c, cor))

        return f":root {{ --acento: {acento}; --sobre-primaria: {sobre(f.primaria)}; --sobre-destaque: {sobre(f.destaque)}; }}\n"

    def extras(self, cenas: list[dict]) -> tuple[str, str]:
        """(HTML, scripts) de quem desenha com three.js; as outras direções não têm nada aqui."""
        fn: Callable | None = getattr(self.render, "extras", None)
        if fn is None or (self.leve and not getattr(self.render, "sempre", False)):
            return "", ""
        return fn(self, cenas)
