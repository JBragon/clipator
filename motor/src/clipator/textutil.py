"""Utilidades de texto: normalização, stopwords e termos relevantes (TF-IDF)."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

STOPWORDS = set(
    """
    a à às ao aos o os as um uma uns umas de da das do dos dum duma em na nas no nos num numa
    por pra pro pras pros para pelo pela pelos pelas com sem sob sobre entre até após desde
    e ou mas nem que se porque pois como quando onde quem qual quais cujo
    eu tu ele ela nós vós eles elas você vocês me te se nos vos lhe lhes meu minha meus minhas
    teu tua seu sua seus suas nosso nossa isso isto aquilo esse essa esses essas este esta
    estes estas aquele aquela aqueles aquelas aqui ali lá aí cá
    é ser sou era foi fui são estar está estou estava tá tô ter tem tinha tenho vai vou ia
    fazer faz fez fiz ficar fica ficou ver vi viu dizer diz disse falar falou fala
    não sim já ainda também só mais menos muito muita muitos muitas pouco tudo nada todo toda
    então aí né tipo assim cara mano coisa coisas gente bem bom boa mesmo
    the a an of to in on at for with without by from about into over under and or but nor so
    that this these those there here it its i you he she we they me him her us them my your
    his our their is are was were be been being am do does did done have has had
    not no yes just also only more less very much many all some any what which who whom
    when where why how if then than like really thing things get got go going gonna know
    yeah okay ok oh um uh well right
    """.split()
)

HESITACOES = {"é", "éé", "ééé", "hã", "hmm", "hum", "ahn", "tipo", "uh", "um", "uhm", "er", "erm", "ah"}


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


_WORD_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def tokens(texto: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(texto)]


def normalizar(palavra: str) -> str:
    return sem_acento(palavra.lower()).strip(".,!?;:\"'()[]…-–—")


def termos_relevantes(blocos: list[str], top: int = 30) -> list[tuple[str, float]]:
    """TF-IDF simples: termos que se destacam no vídeo inteiro."""
    docs = [[t for t in tokens(b) if t not in STOPWORDS and len(t) > 3 and not t.isdigit()] for b in blocos]
    n = len(docs) or 1
    df: Counter[str] = Counter()
    tf: Counter[str] = Counter()
    for d in docs:
        tf.update(d)
        df.update(set(d))
    scores = {t: c * math.log(1 + n / (1 + df[t])) for t, c in tf.items() if c >= 2}
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top]


def contem_termo(texto_norm: str, termo: str) -> bool:
    termo_n = normalizar(termo)
    if not termo_n:
        return False
    return re.search(rf"\b{re.escape(termo_n)}\b", texto_norm) is not None
