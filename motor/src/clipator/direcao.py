"""Direção de arte: cenas animadas que acompanham o que está sendo dito, misturadas com o vídeo matriz.

Três partes, todas daqui:

- **Ficha de direção de arte** (`Ficha`): paleta, duas fontes, jeito de entrar e sons. Vem de uma
  predefinição (neon, dossiê, editorial, laboratório) e o estilo ou o canal sobrescrevem o que quiserem.
  As cenas só usam as variáveis da ficha (nenhuma cor solta), então trocar a ficha troca o visual inteiro.
- **Planejador**: lê as palavras cronometradas do clip e propõe cenas com tempo: título, número em destaque,
  citação, lista, comparação, linha do tempo, local, nome (tarja), palavra gigante e alerta. Cada cena cita
  o trecho da fala que ilustra (`ancora`); o tempo vem de achar esse trecho na transcrição. Sem IA, por
  regras (números, anos, nomes, aspas, enumerações, ênfase); com IA, pelo adaptador (JSON por schema),
  e tudo o que a IA devolve é conferido contra a transcrição e a duração do clip.
- **Camada de cenas**: um documento HTML/CSS que o HyperFrames renderiza em vídeo (com fundo transparente
  para as cenas por cima do vídeo, ou com o fundo da ficha quando a animação ocupa a tela).

Os layouts que juntam a camada com o vídeo (animação em cima e vídeo embaixo, animação de fundo com a
pessoa recortada na frente, cenas por cima, vídeo na janela) ficam no render.
"""

from __future__ import annotations

import difflib
import html
import re
import threading
import unicodedata
from typing import Any

from pydantic import BaseModel, Field

# ---- ficha de direção de arte -----------------------------------------------------------------
ENTRADAS = ("sobe", "desliza", "escala", "mascara", "fade")


class Ficha(BaseModel):
    nome: str = "neon"
    fundo: str = "#0B0B12"
    superficie: str = "#181828"
    texto: str = "#FFFFFF"
    texto_suave: str = "#A9A9C2"
    primaria: str = "#FF2E88"
    destaque: str = "#2EE6FF"
    bom: str = "#3DDC84"  # o verde e o vermelho do certo e do errado (desenho animado)
    ruim: str = "#E5484D"
    fonte_titulo: str = "Anton"
    fonte_corpo: str = "Montserrat ExtraBold"
    entrada: str = "escala"
    sons: dict[str, str] = Field(default_factory=lambda: {"entrada": "whoosh", "enfase": "pop", "numero": "click",
                                                          "alerta": "impacto"})
    volume_sons: float = 0.45


FICHAS: dict[str, dict[str, Any]] = {
    "neon": {"nome": "neon"},
    "dossie": {"nome": "dossie", "fundo": "#141210", "superficie": "#221F1B", "texto": "#F3EDE2", "texto_suave": "#B5AC9C",
               "primaria": "#F5C518", "destaque": "#E24B3B", "fonte_titulo": "Bebas Neue", "fonte_corpo": "Special Elite",
               "entrada": "mascara", "sons": {"entrada": "swoosh-reverso", "enfase": "click", "numero": "click", "alerta": "impacto"}},
    "editorial": {"nome": "editorial", "fundo": "#F4EFE6", "superficie": "#FFFFFF", "texto": "#161616", "texto_suave": "#5B5B5B",
                  "primaria": "#D7263D", "destaque": "#1B4DDB", "fonte_titulo": "Bebas Neue", "fonte_corpo": "Montserrat ExtraBold",
                  "entrada": "sobe", "sons": {"entrada": "whoosh", "enfase": "pop", "numero": "click", "alerta": "ding"}},
    "laboratorio": {"nome": "laboratorio", "fundo": "#07131F", "superficie": "#0E2133", "texto": "#EAF6FF",
                    "texto_suave": "#8FB3C9", "primaria": "#38E1FF", "destaque": "#FFD23F",
                    "fonte_titulo": "Montserrat ExtraBold", "fonte_corpo": "Montserrat ExtraBold", "entrada": "desliza",
                    "sons": {"entrada": "whoosh", "enfase": "ding", "numero": "click", "alerta": "glitch"}},
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def ficha(nome: str | None = None, ajustes: dict[str, Any] | None = None) -> Ficha:
    """A ficha da predefinição com os ajustes do estilo ou do canal por cima (cor errada fica a da ficha)."""
    from .desenho import FICHAS_DESENHO

    if nome and nome.startswith("arte-"):  # as direções com renderizador próprio trazem a paleta na especificação
        from . import artes

        base = artes.ficha_base(nome[len("arte-"):])
    elif nome in FICHAS_DESENHO and nome not in FICHAS:  # fichas do desenho animado (cores bom/ruim e cenário ficam no desenho.py)
        base = {"nome": nome, **{k: v for k, v in FICHAS_DESENHO[nome].items() if k in Ficha.model_fields}}
    else:
        base = dict(FICHAS.get(nome or "neon", FICHAS["neon"]))
    for k, v in (ajustes or {}).items():
        if k in ("fundo", "superficie", "texto", "texto_suave", "primaria", "destaque", "bom", "ruim"):
            if isinstance(v, str) and _HEX.match(v):
                base[k] = v.upper()
        elif k in ("fonte_titulo", "fonte_corpo") and isinstance(v, str) and v.strip():
            base[k] = v.strip()[:60]
        elif k == "entrada" and v in ENTRADAS:
            base[k] = v
        elif k == "sons" and isinstance(v, dict):
            base["sons"] = {**Ficha().sons, **base.get("sons", {}), **{str(a): str(b) for a, b in v.items()}}
        elif k == "volume_sons":
            try:
                base[k] = max(0.0, min(1.5, float(v)))
            except (TypeError, ValueError):
                pass
    return Ficha.model_validate(base)


# ---- cenas ------------------------------------------------------------------------------------
CENAS: dict[str, dict[str, Any]] = {
    # tipo: duração padrão, som, nome na tela
    "titulo": {"dur": 2.8, "som": "entrada", "nome": "Título / gancho"},
    "numero": {"dur": 3.2, "som": "numero", "nome": "Número em destaque"},
    "citacao": {"dur": 4.5, "som": "entrada", "nome": "Citação"},
    "lista": {"dur": 4.5, "som": "enfase", "nome": "Lista de pontos"},
    "comparacao": {"dur": 4.0, "som": "entrada", "nome": "Comparação"},
    "linha_do_tempo": {"dur": 5.0, "som": "entrada", "nome": "Linha do tempo"},
    "local": {"dur": 3.2, "som": "enfase", "nome": "Local / mapa"},
    "nome": {"dur": 3.5, "som": "enfase", "nome": "Nome na tela"},
    "palavra": {"dur": 1.8, "som": "enfase", "nome": "Palavra gigante"},
    "alerta": {"dur": 2.6, "som": "alerta", "nome": "Alerta"},
}
PRIORIDADE = {"lista": 9, "linha_do_tempo": 9, "numero": 8, "citacao": 7, "comparacao": 7, "alerta": 6, "nome": 5,
              "local": 5, "titulo": 4, "palavra": 3}
CAMPOS_TEXTO = {"texto": 90, "valor": 16, "rotulo": 60, "autor": 40, "a": 30, "b": 30, "ancora": 140, "sobre": 40}


def normalizar_cena(p: dict[str, Any]) -> dict[str, Any]:
    """Os parâmetros de uma cena, limpos e dentro dos limites (vêm da tela, da IA ou das regras)."""
    if p.get("cena") == "desenho":
        from .desenho import normalizar_desenho

        return normalizar_desenho(p)
    if p.get("cena") == "arte":
        from . import artes

        if artes.existe(p.get("arte")):
            return artes.normalizar_arte(p)
    cena = p.get("cena") if p.get("cena") in CENAS else "palavra"
    out: dict[str, Any] = {"cena": cena}
    for k, lim in CAMPOS_TEXTO.items():
        v = p.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            out[k] = " ".join(str(v).split())[:lim]
    itens = p.get("itens")
    if isinstance(itens, list):
        limpos = [" ".join(str(x).split())[:48] for x in itens if str(x).strip()][:6]
        if limpos:
            out["itens"] = limpos
    if cena == "palavra" and "texto" not in out:
        out["texto"] = "TEXTO"
    return out


# ---- palavras e âncoras -----------------------------------------------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w%$]+", "", s)


def ancorar(ancora: str, pals: list[dict], desde: int = 0, minimo: float = 0.75) -> tuple[int, int, float] | None:
    """Acha o trecho da fala nas palavras do clip: (índice da primeira, da última, nota 0..1) ou None.

    Procura a partir de `desde` (para frases repetidas casarem na ocorrência certa) e aceita pequenas
    diferenças (o Whisper erra nome próprio): a nota é a semelhança entre as sequências de palavras.
    """
    alvo = [t for t in (_norm(x) for x in ancora.split()) if t]
    if not alvo or not pals:
        return None
    toks = [_norm(w["texto"]) for w in pals]
    n = len(alvo)
    melhor: tuple[int, int, float] | None = None
    for tam in sorted({n, max(1, n - 1), n + 1}):
        for i in range(desde, max(desde, len(toks) - tam + 1)):
            janela = toks[i:i + tam]
            if not janela or not janela[0] and tam > 1:
                continue
            nota = difflib.SequenceMatcher(None, alvo, janela).ratio()
            if nota == 1.0:
                return i, i + tam - 1, 1.0
            if melhor is None or nota > melhor[2] + 1e-9:
                melhor = (i, i + tam - 1, nota)
    return melhor if melhor and melhor[2] >= minimo else None


def _texto(pals: list[dict], i: int, j: int) -> str:
    return " ".join(w["texto"] for w in pals[i:j + 1]).strip()


def _limpo(s: str) -> str:
    return s.strip(" ,.;:!?\"'“”«»()")


class Cena(BaseModel):
    inicio: float
    fim: float
    params: dict[str, Any]
    motivo: str = ""
    prioridade: int = 0


def _selecionar(cands: list[Cena], dur: float, folga: float = 0.6) -> list[Cena]:
    """Sem sobreposição: as de maior prioridade primeiro, cada uma presa entre as vizinhas e dentro do clip."""
    escolhidas: list[Cena] = []
    for c in sorted(cands, key=lambda c: (-c.prioridade, c.inicio)):
        ini = max(0.0, c.inicio)
        fim = min(dur, c.fim)
        if fim - ini < 0.8:
            continue
        if any(e.inicio <= ini < e.fim + folga for e in escolhidas):
            continue  # começa em cima de outra cena
        # termina em cima da próxima: encurta se ainda sobrar tempo para ler
        seguinte = min((e.inicio for e in escolhidas if e.inicio > ini), default=dur + folga)
        if fim + folga > seguinte:
            fim = seguinte - folga
            if fim - ini < max(1.5, 0.45 * (c.fim - c.inicio)):
                continue
        escolhidas.append(c.model_copy(update={"inicio": round(ini, 3), "fim": round(fim, 3)}))
    return sorted(escolhidas, key=lambda c: c.inicio)


# ---- planejador sem IA --------------------------------------------------------------------------
_NUM = re.compile(r"^(R\$)?\d+(?:[.,]\d+)*(%|x|mil|k)?$", re.IGNORECASE)
_ANO = re.compile(r"^(19|20)\d\d$")
_GRANDEZA = {"mil", "milhao", "milhoes", "bilhao", "bilhoes", "trilhao", "trilhoes", "reais", "dolares", "por", "vezes",
             "pessoas", "anos", "dias", "horas", "minutos", "km", "quilos"}
_ORDINAIS = {"primeiro", "primeira", "segundo", "segunda", "terceiro", "terceira", "quarto", "quarta", "quinto", "quinta"}
_DISSE = {"disse", "falou", "afirmou", "declarou", "contou", "escreveu", "respondeu", "perguntou"}
_ALERTA = {"cuidado", "atencao", "urgente", "perigo", "alerta", "golpe", "proibido"}
_FORTES = re.compile(r"^(absurdo|incrivel|segredo|verdade|mentira|chocante|bizarro|polemic\w*|exclusiv\w*|"
                     r"inacreditavel|genial|historico|enorme|gigante|recorde|escandalo|bomba)$")
_PREP_LOCAL = {"em", "no", "na", "nos", "nas", "para", "pra", "de", "do", "da"}
_COMPARA = {"versus", "contra", "vs"}


def _maiuscula(w: str) -> bool:
    t = _limpo(w)
    return len(t) > 1 and t[0].isupper() and not t.isupper() or (len(t) > 2 and t.isupper() and t.isalpha())


def _apos(pals: list[dict], k: int, n: int = 4) -> tuple[str, int]:
    """Até n palavras depois de k, parando no fim da frase."""
    out, j = [], k
    if 0 <= k < len(pals) and pals[k]["texto"].rstrip().endswith((".", "!", "?")):
        return "", k  # a frase acabou aqui: o que vem depois é outro assunto
    for j in range(k + 1, min(len(pals), k + 1 + n)):
        out.append(pals[j]["texto"])
        if pals[j]["texto"].rstrip().endswith((".", "!", "?", ":", ";")):
            break
    return _limpo(" ".join(out)), j


def planejar_regras(pals: list[dict], dur: float, titulo: str = "", densidade: float = 3.0) -> list[Cena]:
    """Cenas por regras simples sobre as palavras do clip (tempo do clip)."""
    cands: list[Cena] = []
    toks = [_norm(w["texto"]) for w in pals]
    inicio_frase = {0} | {k + 1 for k, w in enumerate(pals) if w["texto"].rstrip().endswith((".", "!", "?"))}

    def cena(tipo: str, ini: float, params: dict, motivo: str, ancora: str, dur_c: float | None = None) -> None:
        d = dur_c or CENAS[tipo]["dur"]
        cands.append(Cena(inicio=ini, fim=ini + d, params=normalizar_cena({"cena": tipo, "ancora": ancora, **params}),
                          motivo=motivo, prioridade=PRIORIDADE[tipo]))

    if titulo.strip() and dur > 4:
        cena("titulo", 0.15, {"texto": titulo}, "Gancho no começo, com o título do clip",
             _texto(pals, 0, min(len(pals) - 1, 4)) if pals else titulo, min(3.0, dur * 0.3))

    anos: list[int] = []
    ordinais: list[int] = []
    for k, w in enumerate(pals):
        t = toks[k]
        bruto = _limpo(w["texto"])
        if _ANO.match(bruto):
            anos.append(k)
            continue
        if _NUM.match(bruto) or (t.isdigit() and t):
            grand = toks[k + 1] if k + 1 < len(toks) else ""
            valor = bruto + (" " + _limpo(pals[k + 1]["texto"]) if grand in _GRANDEZA and grand not in ("por", "vezes") else "")
            rotulo, _ = _apos(pals, k + (1 if grand in _GRANDEZA else 0), 5)
            if not rotulo:  # o número fecha a frase: o rótulo é o que veio antes dele
                ini_f = max([i for i in inicio_frase if i <= k] or [0])
                rotulo = _limpo(_texto(pals, max(ini_f, k - 4), k - 1)) if k > ini_f else ""
            cena("numero", w["inicio"] - 0.1, {"valor": valor, "rotulo": rotulo}, f"Número dito: “{valor}”",
                 _texto(pals, max(0, k - 2), min(len(pals) - 1, k + 2)))
            continue
        if t in _ORDINAIS:
            ordinais.append(k)
        if t in _DISSE and k + 1 < len(pals):
            frase, j = _apos(pals, k + (1 if toks[k + 1] in ("que", "assim") else 0), 12)
            autor = next((_limpo(pals[i]["texto"]) for i in range(k - 1, max(-1, k - 4), -1)
                          if _maiuscula(pals[i]["texto"]) and i not in inicio_frase), "")
            if len(frase.split()) >= 3:
                cena("citacao", w["inicio"], {"texto": frase, "autor": autor}, "Fala citada", _texto(pals, k, min(j, k + 6)),
                     min(6.0, max(3.0, pals[j]["fim"] - w["inicio"] + 1.2)))
            continue
        if t in _ALERTA:
            frase, j = _apos(pals, k, 5)
            cena("alerta", w["inicio"] - 0.05, {"texto": (bruto + " " + frase).strip()}, f"Alerta: “{bruto}”",
                 _texto(pals, k, min(len(pals) - 1, k + 3)))
            continue
        if t in _COMPARA or (t == "que" and k > 0 and toks[k - 1] == "do" and k >= 2):
            a = _limpo(" ".join(x["texto"] for x in pals[max(0, k - (2 if t == "que" else 1) - 2):k - (1 if t == "que" else 0)]))
            b, _ = _apos(pals, k, 3)
            if a and b:
                cena("comparacao", pals[max(0, k - 3)]["inicio"], {"a": a, "b": b}, "Comparação na fala",
                     _texto(pals, max(0, k - 3), min(len(pals) - 1, k + 3)))
            continue
        if _FORTES.match(t):
            cena("palavra", w["inicio"] - 0.05, {"texto": bruto.upper()}, f"Palavra forte: “{bruto}”", _texto(pals, max(0, k - 1), min(len(pals) - 1, k + 1)))
            continue
        # nomes próprios: duas ou mais palavras com maiúscula fora do começo da frase
        if _maiuscula(w["texto"]) and k not in inicio_frase and (k == 0 or not _maiuscula(pals[k - 1]["texto"])):
            j = k
            while (j + 1 < len(pals) and _maiuscula(pals[j + 1]["texto"]) and j - k < 3
                   and not pals[j]["texto"].rstrip().endswith((".", "!", "?", ",", ";", ":"))):
                j += 1
            nome = _limpo(_texto(pals, k, j))
            prep = toks[k - 1] if k > 0 else ""
            if prep in _PREP_LOCAL and j == k or prep in ("em", "no", "na"):
                cena("local", w["inicio"] - 0.1, {"texto": nome}, f"Lugar citado: “{nome}”", _texto(pals, max(0, k - 1), j))
            elif j > k:
                cena("nome", w["inicio"], {"texto": nome}, f"Nome citado: “{nome}”", _texto(pals, k, j))
    if len(anos) >= 2:
        marcos = []
        for k in anos[:5]:
            resto, _ = _apos(pals, k, 3)
            marcos.append(f"{_limpo(pals[k]['texto'])}: {resto}" if resto else _limpo(pals[k]["texto"]))
        ini = pals[anos[0]]["inicio"] - 0.2
        fim = pals[anos[min(4, len(anos) - 1)]]["fim"] + 1.8
        cena("linha_do_tempo", ini, {"itens": marcos}, "Datas em sequência", _texto(pals, anos[0], min(len(pals) - 1, anos[0] + 3)),
             max(3.5, fim - ini))
    elif anos:
        k = anos[0]
        resto, _ = _apos(pals, k, 4)
        cena("numero", pals[k]["inicio"] - 0.1, {"valor": _limpo(pals[k]["texto"]), "rotulo": resto}, "Ano citado",
             _texto(pals, max(0, k - 2), min(len(pals) - 1, k + 2)))
    if len(ordinais) >= 2:
        itens = [_apos(pals, k, 4)[0] for k in ordinais[:5]]
        ini = pals[ordinais[0]]["inicio"] - 0.2
        fim = pals[ordinais[-1]]["fim"] + 2.0
        cena("lista", ini, {"itens": [i for i in itens if i]}, "Enumeração na fala",
             _texto(pals, ordinais[0], min(len(pals) - 1, ordinais[0] + 3)), max(3.5, fim - ini))
    escolhidas = _selecionar(cands, dur, folga=densidade * 0.35)
    # densidade: no máximo uma cena a cada `densidade` segundos (fora o título)
    out: list[Cena] = []
    for c in escolhidas:
        if out and c.params["cena"] != "titulo" and c.inicio - out[-1].inicio < densidade and c.prioridade <= out[-1].prioridade:
            continue
        out.append(c)
    return out


# ---- planejador com IA ----------------------------------------------------------------------------
SCHEMA_CENAS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cenas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cena": {"type": "string", "enum": list(CENAS)},
                    "ancora": {"type": "string"},
                    "texto": {"type": "string"},
                    "itens": {"type": "array", "items": {"type": "string"}},
                    "valor": {"type": "string"},
                    "rotulo": {"type": "string"},
                    "autor": {"type": "string"},
                    "a": {"type": "string"},
                    "b": {"type": "string"},
                    "duracao": {"type": "number"},
                    "motivo": {"type": "string"},
                },
                "required": ["cena", "ancora", "texto", "itens", "valor", "rotulo", "autor", "a", "b", "duracao", "motivo"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cenas"],
    "additionalProperties": False,
}


def prompt_cenas(pals: list[dict], dur: float, titulo: str, canal_md: str = "", max_cenas: int | None = None,
                 extra: str = "", direcao: str = "") -> str:
    """`direcao`: a pré-produção (análise e roteiro, desenho.direcao_para_cenas) que as cenas têm de seguir."""
    linhas, atual, t0 = [], [], 0.0
    for w in pals:
        if not atual:
            t0 = w["inicio"]
        atual.append(w["texto"])
        if w["texto"].rstrip().endswith((".", "!", "?")) or len(atual) >= 14:
            linhas.append(f"[{t0:.1f}] {' '.join(atual)}")
            atual = []
    if atual:
        linhas.append(f"[{t0:.1f}] {' '.join(atual)}")
    n = max_cenas or max(2, int(dur // 4))
    return (
        "Você é diretor de arte de vídeos curtos. Planeje telas animadas que ilustrem o que a pessoa está dizendo.\n"
        f"Clip de {dur:.1f} s, título: “{titulo}”.\n"
        "Tipos: titulo (gancho no começo), numero (valor + rotulo curto), citacao (texto citado + autor), "
        "lista (itens, 2 a 5, curtos), comparacao (a contra b), linha_do_tempo (itens no formato 'data: fato'), "
        "local (texto = o lugar), nome (texto = nome da pessoa ou da empresa, rotulo = quem é), "
        "palavra (uma palavra forte em texto), alerta (texto curto).\n"
        "Regras: 'ancora' é o trecho da FALA, copiado da transcrição, 4 a 8 palavras seguidas, que a cena ilustra "
        "(a cena entra quando ele é dito). Use só o que foi dito: nada de número, nome ou citação que não esteja na fala. "
        f"No máximo {n} cenas, sem duas ao mesmo tempo, uma a cada 3 s no mínimo. 'duracao' em segundos (1,5 a 6). "
        "Campos que não se aplicam ficam vazios (texto '', itens []). Em 'motivo', uma frase.\n"
        + (f"Canal:\n{canal_md[:800]}\n" if canal_md else "")
        + (f"{extra[:6000]}\n" if extra else "")
        + ("Siga a direção abaixo: uma cena por item do roteiro, na mesma ordem, com a 'ancora' e a 'duracao' do item, e o tipo "
           f"que melhor mostra a 'descricao' dele. Não repita o título do clip nas cenas.\n{direcao}\n" if direcao else "")
        + "Transcrição (segundos do clip):\n" + "\n".join(linhas)
    )


def _na_fala(trecho: str, pals: list[dict], minimo: float = 0.6) -> bool:
    """O texto (ou os números dele) está mesmo na fala?"""
    toks = {_norm(w["texto"]) for w in pals}
    palavras = [t for t in (_norm(x) for x in trecho.split()) if t]
    if not palavras:
        return False
    digitos = [p for p in palavras if any(c.isdigit() for c in p)]
    if digitos and not all(any(d in t for t in toks) for d in (re.sub(r"\D", "", x) for x in digitos)):
        return False
    return sum(p in toks for p in palavras) / len(palavras) >= minimo


def _nos_tempos_do_roteiro(cands: list[Cena], roteiro: list[dict]) -> list[Cena]:
    """Cada cena fica com o tempo do item do roteiro que ela ilustra (o usuário pode ter mexido nele); um item, uma cena."""
    livres = list(roteiro)
    out = []
    for c in cands:
        alvo = _norm(str(c.params.get("ancora") or ""))
        r = next((x for x in livres if _norm(str(x.get("ancora") or "")) == alvo), None)
        r = r or next((x for x in livres if x["inicio"] - 0.3 <= c.inicio < x["fim"]), None)
        if r is None:
            out.append(c)
            continue
        livres.remove(r)
        out.append(c.model_copy(update={"inicio": r["inicio"], "fim": r["fim"]}))
    return out


def de_resposta_ia(resp: Any, pals: list[dict], dur: float, roteiro: list[dict] | None = None) -> list[Cena]:
    """Confere cada cena da IA contra a transcrição: âncora tem de existir, número e citação têm de ter sido ditos.

    Com `roteiro` (a pré-produção), as cenas ficam nos tempos dele, encostadas umas nas outras.
    """
    cenas = (resp or {}).get("cenas") if isinstance(resp, dict) else None
    if not isinstance(cenas, list):
        return []
    cands: list[Cena] = []
    desde = 0
    for c in cenas:
        if not isinstance(c, dict) or c.get("cena") not in CENAS:
            continue
        tipo = c["cena"]
        achou = ancorar(str(c.get("ancora") or ""), pals, desde) or ancorar(str(c.get("ancora") or ""), pals, 0)
        if achou is None:
            continue
        i, j, _ = achou
        desde = i
        p = normalizar_cena({**c, "ancora": _texto(pals, i, j)})
        if tipo == "numero" and not (p.get("valor") and _na_fala(p["valor"], pals, 0.5)):
            continue
        if tipo == "citacao" and not (p.get("texto") and _na_fala(p["texto"], pals, 0.7)):
            continue
        if tipo in ("nome", "local") and not (p.get("texto") and _na_fala(p["texto"], pals, 0.5)):
            continue
        if tipo in ("lista", "linha_do_tempo") and len(p.get("itens", [])) < 2:
            continue
        if tipo in ("palavra", "alerta", "titulo") and not p.get("texto"):
            continue
        if tipo == "comparacao" and not (p.get("a") and p.get("b")):
            continue
        try:
            d = float(c.get("duracao") or CENAS[tipo]["dur"])
        except (TypeError, ValueError):
            d = CENAS[tipo]["dur"]
        d = max(1.5, min(6.0, d))
        ini = pals[i]["inicio"] - 0.1
        cands.append(Cena(inicio=ini, fim=ini + d, params=p, motivo=str(c.get("motivo") or "")[:200],
                          prioridade=PRIORIDADE[tipo]))
    if roteiro:
        return _selecionar(_nos_tempos_do_roteiro(cands, roteiro), dur, folga=0.0)
    return _selecionar(cands, dur, folga=0.3)


def planejar_ia(pals: list[dict], dur: float, titulo: str, ad: Any, cache: Any = None, canal_md: str = "",
                cancelar: threading.Event | None = None, extra: str = "", relato: Any = None) -> list[Cena]:
    """`extra`: o texto das skills ativas do tipo "cenas" (skills.texto_para_ia). `relato`: relato.Relato do job."""
    from contextlib import nullcontext

    from .ai.adapter import chamar

    prompt = prompt_cenas(pals, dur, titulo, canal_md, extra=extra)
    if relato is not None:
        relato.passo(f"pedido das cenas pronto: {len(pals)} palavras, {dur:.0f} s de clip, {len(prompt)} caracteres")
    with (relato.ia(getattr(ad, "nome", "IA"), "planejando as cenas") if relato is not None else nullcontext()) as ev:
        r = chamar(ad, prompt, SCHEMA_CENAS, cache, cancelar, ev)
    cenas = de_resposta_ia(r, pals, dur)
    if relato is not None:
        propostas = len((r or {}).get("cenas") or []) if isinstance(r, dict) else 0
        relato.passo(f"conferindo com a fala: {len(cenas)} de {propostas} cena(s) aceitas"
                     + (f", {propostas - len(cenas)} descartada(s) (trecho que não está na fala, número ou citação não dita, "
                        "ou em cima de outra cena)" if propostas > len(cenas) else ""))
    return cenas


# ---- camada HTML/CSS (HyperFrames) ------------------------------------------------------------------
LAYOUTS = ("nenhum", "em-cima", "fundo", "sobreposto", "janela")


def area_das_cenas(layout: str, proporcao: float, canto: str | None = None) -> tuple[float, float]:
    """(topo, altura) em fração do quadro onde as cenas se desenham."""
    if layout == "janela" and canto and canto.startswith("superior"):
        return 0.40, 0.32  # a janela em cima: as cenas descem, sem chegar na legenda
    if layout == "em-cima":
        return 0.0, proporcao
    if layout == "fundo":
        return 0.06, 0.48
    if layout == "janela":
        return 0.05, 0.38
    return 0.12, 0.42  # sobreposto: cartões na metade de cima, longe da legenda


def _esc(s: Any) -> str:
    return html.escape(str(s or ""))


def _conteudo(p: dict[str, Any], dur: float = 4.0) -> str:
    tipo = p["cena"]
    if tipo == "desenho":
        from .desenho import cena_html

        return cena_html(p)
    if tipo == "titulo":
        sobre = f'<div class="sobre">{_esc(p.get("sobre"))}</div>' if p.get("sobre") else ""
        return f'{sobre}<div class="titulo">{_esc(p.get("texto"))}</div><div class="filete"></div>'
    if tipo == "numero":
        valor = str(p.get("valor") or "")
        m = re.search(r"\d+", valor.replace(".", ""))
        alvo = int(m.group(0)[:9]) if m else 0
        pre, _, pos = valor.partition(m.group(0)) if m else (valor, "", "")
        conta = (f'<span class="pre">{_esc(pre)}</span><span class="conta" style="--alvo:{alvo}"></span>'
                 f'<span class="pos">{_esc(pos)}</span>') if (m and len(m.group(0)) <= 9 and "," not in valor
                                                               and not _ANO.match(m.group(0))) else _esc(valor)  # ano não conta
        return f'<div class="valor">{conta}</div><div class="rotulo">{_esc(p.get("rotulo"))}</div>'
    if tipo == "citacao":
        autor = f'<div class="autor">— {_esc(p.get("autor"))}</div>' if p.get("autor") else ""
        return f'<div class="aspas">“</div><div class="frase-citada">{_esc(p.get("texto"))}</div>{autor}'
    if tipo in ("lista", "linha_do_tempo"):
        itens = p.get("itens") or []
        cab = f'<div class="cabeca">{_esc(p.get("texto"))}</div>' if p.get("texto") else ""
        passo = max(0.25, (dur - 1.2) / max(1, len(itens)))  # os itens entram um a um ao longo da cena
        lis = "".join(f'<li style="animation-delay:{0.25 + k * passo:.2f}s"><span class="marca">{k + 1 if tipo == "lista" else ""}</span>'
                      f'<span class="item">{_esc(x)}</span></li>' for k, x in enumerate(itens))
        return f'{cab}<ol class="itens" style="--n:{len(itens)}">{lis}</ol>'
    if tipo == "comparacao":
        return (f'<div class="lado a"><span>{_esc(p.get("a"))}</span></div><div class="vs">VS</div>'
                f'<div class="lado b"><span>{_esc(p.get("b"))}</span></div>')
    if tipo == "local":
        return ('<div class="mapa"><div class="grade"></div><div class="pino"><div class="onda"></div></div></div>'
                f'<div class="lugar">{_esc(p.get("texto"))}</div>')
    if tipo == "nome":
        rot = f'<div class="quem">{_esc(p.get("rotulo"))}</div>' if p.get("rotulo") else ""
        return f'<div class="tarja"><div class="barra"></div><div class="nome-txt">{_esc(p.get("texto"))}</div>{rot}</div>'
    if tipo == "alerta":
        return f'<div class="faixa-alerta"><span class="icone">!</span><span>{_esc(p.get("texto"))}</span></div>'
    return f'<div class="gigante">{_esc(p.get("texto"))}</div>'


def compor_camada(cenas: list[dict[str, Any]], f: Ficha, largura: int, altura: int, duracao: float, layout: str,
                  proporcao: float = 0.45, titulo: str = "", fps: int = 30, fontes_css: str = "", arte: str | None = None,
                  zona: Any = None, parametros: dict | None = None, geo: Any = None, canto: str | None = None) -> str:
    """O index.html da camada de cenas. `cenas`: [{inicio, fim, params}] em segundos do clip.

    `arte`: a direção com renderizador próprio (artes/); `zona` é a zona segura da plataforma e `parametros` os do estilo.

    Nos layouts em que a animação ocupa a tela (em-cima, fundo, janela) a camada é opaca, com o fundo
    da ficha se mexendo devagar quando nenhuma cena está no ar (só a maquete mostra o título do clip nesses
    vãos); em "sobreposto" o fundo é transparente e só os cartões aparecem.
    """
    topo, alt = area_das_cenas(layout, proporcao, canto)
    if arte and layout == "janela":
        from .artes import cortes as _cortes

        if _cortes.eh_corte(arte):  # a arte ocupa a tela toda; a janela entra por cima e a câmera desvia dela
            topo, alt = 0.0, 1.0
    opaca = layout in ("em-cima", "fundo", "janela")
    escala = min(largura, altura) / 1080
    clips = []
    cam = None
    if arte:
        from . import artes as _artes

        cam = _artes.Camada(arte, largura, altura, topo, alt, zona, duracao, parametros, f, geo)
    n_arte = sum(1 for c in cenas if c["params"].get("cena") == "arte")
    for k, c in enumerate(cenas):
        p = c["params"]
        ini, fim = max(0.0, float(c["inicio"])), min(duracao, float(c["fim"]))
        if fim - ini < 0.2:
            continue
        conteudo = (cam.cena(p, ini, fim, k, n_arte, c.get("palavras"), c.get("_midia")) if cam is not None and p["cena"] == "arte"
                    else _conteudo(p, fim - ini))
        clips.append(f'<div id="cena-{k + 1}" class="clip cena {p["cena"]}" data-start="{ini:.3f}" data-duration="{fim - ini:.3f}" '
                     f'data-track-index="{k % 4 + 2}" style="--dur:{fim - ini:.3f}s">{conteudo}</div>')
    repouso = ""
    if opaca and titulo and f.nome == "maquete":
        ocupado = sorted((max(0.0, float(c["inicio"])), min(duracao, float(c["fim"]))) for c in cenas)
        t, vaos = 0.0, []
        for a, b in ocupado + [(duracao, duracao)]:
            if a - t >= 1.2:
                vaos.append((t + (0.35 if t > 0 else 0.0), a))
            t = max(t, b)
        repouso = "".join(f'<div id="repouso-{k}" class="clip repouso" data-start="{a:.3f}" data-duration="{b - a:.3f}" '
                          f'data-track-index="1"><div class="repouso-txt">{_esc(titulo)}</div></div>'
                          for k, (a, b) in enumerate(vaos) if b - a >= 0.6)
    desenho = any(c["params"].get("cena") == "desenho" for c in cenas)
    palco, css_desenho, cores_desenho, scripts_3d = "", "", {}, ""
    if desenho:  # o desenho animado: cenário fixo atrás das cenas e as peças em <defs>
        from . import desenho as _des

        fd = _des.ficha_desenho(f.nome)
        palco = _des.fundo_html(fd["cenario"], fd.get("pecas", "traco"))
        css_desenho = _des.CSS_DESENHO
        cores_desenho = {"--bom": f.bom, "--ruim": f.ruim}
        if fd.get("pecas") == "maquete":
            from .maquete import CSS_MAQUETE

            css_desenho += CSS_MAQUETE + _des.CSS_HUD_MAQUETE
            cores_desenho.update({f"--lp-{k}": v for k, v in fd.get("lp", {}).items()})
            from . import maquete3d

            if maquete3d.disponivel():  # a maquete em 3D (three.js); sem WebGL, o script não liga e ficam as peças em SVG
                canvas, scripts_3d = maquete3d.camada(cenas, duracao)
                palco += canvas
                css_desenho += maquete3d.css(duracao)
    classe_body = ""
    if cam is not None:
        palco = cam.fundo()
        css_desenho += cam.css()
        canvas, scripts_3d = cam.extras(cenas)
        palco += canvas
        classe_body = " arte" + (" arte-leve" if cam.leve else "")
    fundo = (f'<div id="fundo" class="clip fundo-da{" com-desenho" if desenho else ""}{" com-arte" if cam is not None else ""}" data-start="0" data-duration="{duracao:.3f}" '
             f'data-track-index="0"><div class="malha"></div><div class="brilho"></div>{palco}</div>') if opaca else ""
    variaveis = {
        "--largura": f"{largura}px", "--altura": f"{altura}px", "--u": f"{escala:.4f}px",
        "--fundo": f.fundo, "--superficie": f.superficie, "--texto": f.texto, "--suave": f.texto_suave,
        "--primaria": f.primaria, "--destaque": f.destaque, "--f-titulo": f"'{f.fonte_titulo}', 'Anton', sans-serif",
        "--f-corpo": f"'{f.fonte_corpo}', 'Montserrat ExtraBold', sans-serif", "--topo": f"{topo * 100:.2f}%",
        "--alt": f"{alt * 100:.2f}%", "--duracao": f"{duracao:.3f}s", **cores_desenho,
    }
    raiz = ":root {\n" + "".join(f"  {k}: {v};\n" for k, v in variaveis.items()) + "}\n"
    return f"""<!doctype html>
<html lang="pt">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={largura}, height={altura}" />
<!-- Gerado pelo Clipator (direção de arte). Motor: HyperFrames (Apache 2.0). -->
<style>
{fontes_css}{raiz}{CSS_BASE}
{CSS_ENTRADAS[f.entrada]}
{css_desenho}
</style>
</head>
<body class="{'opaca' if opaca else 'transparente'} layout-{layout} ficha-{f.nome}{classe_body}">
<div id="root" data-composition-id="clipator-cenas" data-start="0" data-duration="{duracao:.3f}" data-width="{largura}" data-height="{altura}" data-fps="{fps}" data-no-timeline>
{fundo}
{repouso}
{chr(10).join(clips)}
</div>
{scripts_3d}
</body>
</html>
"""


# Tudo em função das variáveis da ficha; tamanhos em --u (1 px de um quadro de 1080 no lado menor).
CSS_BASE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: var(--largura); height: var(--altura); overflow: hidden; background: transparent; }
body.opaca { background: var(--fundo); }
#root { position: relative; width: 100%; height: 100%; color: var(--texto); font-family: var(--f-corpo); }
.fundo-da { position: absolute; inset: 0; background: radial-gradient(120% 80% at 30% 20%, var(--superficie), var(--fundo) 70%); }
.fundo-da .malha { position: absolute; inset: -10%; opacity: .16;
  background-image: linear-gradient(var(--suave) 1px, transparent 1px), linear-gradient(90deg, var(--suave) 1px, transparent 1px);
  background-size: calc(var(--u) * 90) calc(var(--u) * 90); animation: deriva var(--duracao) linear both; }
.fundo-da .brilho { position: absolute; width: 70%; height: 50%; left: 10%; top: 5%; border-radius: 50%;
  background: radial-gradient(closest-side, color-mix(in srgb, var(--primaria) 35%, transparent), transparent);
  filter: blur(calc(var(--u) * 60)); animation: pulsa 6s ease-in-out infinite alternate both; }
@keyframes deriva { from { transform: translate(0, 0); } to { transform: translate(calc(var(--u) * -90), calc(var(--u) * -45)); } }
@keyframes pulsa { from { opacity: .55; transform: scale(1); } to { opacity: .9; transform: scale(1.12); } }
.repouso { position: absolute; left: 7%; right: 7%; top: var(--topo); height: var(--alt); display: flex; align-items: center; justify-content: center; }
.repouso { animation: entra-repouso .6s ease-out both; }
@keyframes entra-repouso { from { opacity: 0; } to { opacity: 1; } }
.repouso-txt { font-family: var(--f-titulo); font-size: calc(var(--u) * 62); line-height: 1.05; text-align: center; color: var(--suave);
  text-transform: uppercase; opacity: .35; letter-spacing: .02em; }
.cena { position: absolute; left: 6%; right: 6%; top: var(--topo); height: var(--alt); display: flex; flex-direction: column;
  align-items: center; justify-content: center; text-align: center; gap: calc(var(--u) * 18);
  animation: entra .45s cubic-bezier(.2, .9, .2, 1) both, sai .3s ease-in calc(var(--dur) - .3s) forwards; }
body.opaca .cena { background: var(--fundo); }
body.transparente .cena { top: auto; height: auto; top: var(--topo); padding: calc(var(--u) * 34) calc(var(--u) * 40);
  background: color-mix(in srgb, var(--fundo) 88%, transparent); border-radius: calc(var(--u) * 26);
  box-shadow: 0 calc(var(--u) * 20) calc(var(--u) * 60) rgba(0, 0, 0, .45); }
body.transparente .cena.nome, body.transparente .cena.alerta, body.transparente .cena.palavra { background: none; box-shadow: none; }
@keyframes sai { to { opacity: 0; transform: translateY(calc(var(--u) * -18)); } }
.titulo { font-family: var(--f-titulo); font-size: calc(var(--u) * 96); line-height: 1.02; text-transform: uppercase; }
.sobre { font-size: calc(var(--u) * 30); color: var(--primaria); letter-spacing: .12em; text-transform: uppercase; }
.filete { width: 0; height: calc(var(--u) * 10); background: var(--primaria); animation: cresce .6s .25s cubic-bezier(.2, .9, .2, 1) forwards; }
@keyframes cresce { to { width: 40%; } }
@property --n { syntax: "<integer>"; initial-value: 0; inherits: false; }
.valor { font-family: var(--f-titulo); font-size: calc(var(--u) * 190); line-height: 1; color: var(--primaria); display: flex; align-items: baseline; gap: .08em; }
.valor .conta { counter-reset: n var(--n); animation: conta 1.1s cubic-bezier(.2, .8, .2, 1) .1s both; }
.valor .conta::after { content: counter(n); }
@keyframes conta { from { --n: 0; } to { --n: var(--alvo); } }
.valor .pre, .valor .pos { font-size: .45em; color: var(--texto); }
.rotulo { font-size: calc(var(--u) * 40); color: var(--texto); max-width: 90%; }
.aspas { font-family: var(--f-titulo); font-size: calc(var(--u) * 200); line-height: .6; color: var(--primaria); height: calc(var(--u) * 90); }
.frase-citada { font-size: calc(var(--u) * 52); line-height: 1.18; max-width: 92%; }
.autor { font-size: calc(var(--u) * 34); color: var(--suave); }
.cabeca { font-family: var(--f-titulo); font-size: calc(var(--u) * 60); text-transform: uppercase; color: var(--primaria); }
.itens { list-style: none; display: flex; flex-direction: column; gap: calc(var(--u) * 22); width: 88%; text-align: left; }
.itens li { display: flex; align-items: center; gap: calc(var(--u) * 22); font-size: calc(var(--u) * 44); line-height: 1.1;
  animation: item .45s cubic-bezier(.2, .9, .2, 1) both; }
@keyframes item { from { opacity: 0; transform: translateX(calc(var(--u) * -60)); } to { opacity: 1; transform: none; } }
.itens .marca { flex: none; width: calc(var(--u) * 64); height: calc(var(--u) * 64); border-radius: 50%; background: var(--primaria);
  color: var(--fundo); display: grid; place-items: center; font-family: var(--f-titulo); font-size: calc(var(--u) * 38); }
.linha_do_tempo .itens { border-left: calc(var(--u) * 8) solid var(--primaria); padding-left: calc(var(--u) * 30); }
.linha_do_tempo .marca { width: calc(var(--u) * 28); height: calc(var(--u) * 28); margin-left: calc(var(--u) * -48); }
.comparacao { flex-direction: row; gap: calc(var(--u) * 20); }
.lado { flex: 1; min-height: 44%; display: grid; place-items: center; padding: calc(var(--u) * 30); border-radius: calc(var(--u) * 24);
  font-family: var(--f-titulo); font-size: calc(var(--u) * 64); text-transform: uppercase; line-height: 1.05; }
.lado.a { background: var(--superficie); animation: entra-esq .5s cubic-bezier(.2, .9, .2, 1) both; }
.lado.b { background: var(--primaria); color: var(--fundo); animation: entra-dir .5s .15s cubic-bezier(.2, .9, .2, 1) both; }
.vs { font-family: var(--f-titulo); font-size: calc(var(--u) * 70); color: var(--destaque); animation: pop .4s .45s cubic-bezier(.2, 1.4, .4, 1) both; }
@keyframes entra-esq { from { opacity: 0; transform: translateX(-30%); } to { opacity: 1; transform: none; } }
@keyframes entra-dir { from { opacity: 0; transform: translateX(30%); } to { opacity: 1; transform: none; } }
@keyframes pop { from { opacity: 0; transform: scale(.3); } to { opacity: 1; transform: none; } }
.mapa { position: relative; width: 70%; aspect-ratio: 16 / 9; border-radius: calc(var(--u) * 24); overflow: hidden; background: var(--superficie); }
.mapa .grade { position: absolute; inset: 0; opacity: .35;
  background-image: linear-gradient(var(--suave) 1px, transparent 1px), linear-gradient(90deg, var(--suave) 1px, transparent 1px);
  background-size: calc(var(--u) * 46) calc(var(--u) * 46); animation: aproxima var(--dur) ease-out both; }
@keyframes aproxima { from { transform: scale(1.35); } to { transform: scale(1); } }
.pino { position: absolute; left: 50%; top: 50%; width: calc(var(--u) * 46); height: calc(var(--u) * 46); margin: calc(var(--u) * -46) 0 0 calc(var(--u) * -23);
  background: var(--primaria); border-radius: 50% 50% 50% 0; transform: rotate(-45deg); animation: cai .5s .2s cubic-bezier(.2, 1.4, .4, 1) both; }
.pino .onda { position: absolute; inset: -60%; border: calc(var(--u) * 5) solid var(--primaria); border-radius: 50%; animation: onda 1.2s .6s ease-out infinite both; }
@keyframes cai { from { opacity: 0; transform: translateY(-120%) rotate(-45deg); } to { opacity: 1; transform: rotate(-45deg); } }
@keyframes onda { from { opacity: .9; transform: scale(.3); } to { opacity: 0; transform: scale(1.6); } }
.lugar { font-family: var(--f-titulo); font-size: calc(var(--u) * 80); text-transform: uppercase; }
.nome { justify-content: flex-end; align-items: flex-start; }
.tarja { position: relative; padding: calc(var(--u) * 18) calc(var(--u) * 34) calc(var(--u) * 18) calc(var(--u) * 46); background: var(--superficie);
  text-align: left; animation: abre .45s cubic-bezier(.2, .9, .2, 1) both; clip-path: inset(0 0 0 0); }
.tarja .barra { position: absolute; left: 0; top: 0; bottom: 0; width: calc(var(--u) * 14); background: var(--primaria); }
.nome-txt { font-family: var(--f-titulo); font-size: calc(var(--u) * 62); text-transform: uppercase; line-height: 1.05; }
.quem { font-size: calc(var(--u) * 30); color: var(--suave); }
@keyframes abre { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
.faixa-alerta { display: flex; align-items: center; gap: calc(var(--u) * 24); padding: calc(var(--u) * 24) calc(var(--u) * 40);
  background: var(--destaque); color: var(--fundo); font-family: var(--f-titulo); font-size: calc(var(--u) * 60); text-transform: uppercase;
  transform: rotate(-2deg); animation: treme .5s ease-out both; }
.faixa-alerta .icone { width: calc(var(--u) * 70); height: calc(var(--u) * 70); border-radius: 50%; background: var(--fundo); color: var(--destaque);
  display: grid; place-items: center; animation: pisca .6s steps(2) infinite both; }
@keyframes treme { 0% { transform: rotate(-2deg) scale(1.3); opacity: 0; } 40% { transform: rotate(-4deg) scale(1); opacity: 1; }
  60% { transform: rotate(0deg); } 80% { transform: rotate(-3deg); } 100% { transform: rotate(-2deg); } }
@keyframes pisca { 50% { opacity: .35; } }
.gigante { font-family: var(--f-titulo); font-size: calc(var(--u) * 170); line-height: .95; text-transform: uppercase; color: var(--primaria);
  -webkit-text-stroke: calc(var(--u) * 3) var(--fundo); paint-order: stroke fill; animation: pop .35s cubic-bezier(.2, 1.4, .4, 1) both; }
"""
CSS_ENTRADAS = {
    "sobe": "@keyframes entra { from { opacity: 0; transform: translateY(calc(var(--u) * 60)); } to { opacity: 1; transform: none; } }",
    "desliza": "@keyframes entra { from { opacity: 0; transform: translateX(-12%); } to { opacity: 1; transform: none; } }",
    "escala": "@keyframes entra { from { opacity: 0; transform: scale(.82); } to { opacity: 1; transform: none; } }",
    "mascara": "@keyframes entra { from { clip-path: inset(0 0 100% 0); } to { clip-path: inset(0 0 0 0); } }",
    "fade": "@keyframes entra { from { opacity: 0; } to { opacity: 1; } }",
}


def eventos_de_som(cenas: list[dict[str, Any]], f: Ficha) -> list[tuple[str, float, str]]:
    """(chave, segundo, nome do efeito) de cada cena: a entrada de cada uma, com no máximo um som a cada 0,4 s."""
    out: list[tuple[str, float, str]] = []
    ultimo = -9.0
    for k, c in enumerate(cenas):
        papel = CENAS.get(c["params"].get("cena", ""), {}).get("som", "entrada")
        if c["params"].get("cena") == "arte" and k == len(cenas) - 1 and len(cenas) > 1:
            papel = "enfase"  # a última cena fecha a ideia
        nome = f.sons.get(papel) or f.sons.get("entrada")
        t = max(0.0, float(c["inicio"]))
        if nome and t - ultimo >= 0.4:
            out.append((f"cena-{k}", t, nome))
            ultimo = t
    return out
