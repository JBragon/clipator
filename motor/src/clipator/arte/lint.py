"""Lint dos estilos: acha cor e fonte escritas à mão onde deveria haver um token da DA.

Lê .css, .html, .js, .svg e o cabeçalho YAML dos .md de estilo. Acusa hex, `rgb()/rgba()/hsl()`, nomes de cor do
CSS e `font-family` com nome de fonte, e sugere o token mais próximo (com a diferença ΔE). Exceções:

- `/* da-livre */` (ou `<!-- da-livre -->`, `# da-livre`) na linha: foto, logo de terceiros, captura de tela.
- `da-livre-arquivo` nas 10 primeiras linhas: o arquivo inteiro fica de fora.
- `var(--…)`, `currentColor`, `transparent`, `inherit` e `da:<token>` são sempre aceitos.

Arquivo que o lint não sabe ler sai como "não conferido": não é sinal verde.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import cores as C
from .carregar import Resolvida

EXTENSOES = (".css", ".html", ".htm", ".js", ".mjs", ".svg", ".md")
_HEX = re.compile(r"(?<![\w&])#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F\w])")
_FUNC = re.compile(r"\b(rgba?|hsla?)\(\s*([^)]*)\)", re.IGNORECASE)
_FAMILIA = re.compile(r"font-family\s*:\s*([^;}\n]+)", re.IGNORECASE)
_NOMES_CSS = {
    "black": "#000000", "white": "#FFFFFF", "red": "#FF0000", "green": "#008000", "blue": "#0000FF",
    "yellow": "#FFFF00", "orange": "#FFA500", "purple": "#800080", "pink": "#FFC0CB", "gray": "#808080",
    "grey": "#808080", "cyan": "#00FFFF", "magenta": "#FF00FF", "lime": "#00FF00", "navy": "#000080",
    "gold": "#FFD700", "silver": "#C0C0C0", "maroon": "#800000", "teal": "#008080", "olive": "#808000",
    "coral": "#FF7F50", "crimson": "#DC143C", "tomato": "#FF6347", "violet": "#EE82EE", "indigo": "#4B0082",
}
_NOME_COR = re.compile(r"(?:color|background(?:-color)?|fill|stroke|border(?:-\w+)?-?color?|outline-color)\s*:\s*"
                       r"([a-zA-Z]+)\b")
_LIVRE = re.compile(r"da-livre(?!-arquivo)")
_GENERICAS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "inherit", "initial", "unset"}


@dataclass
class Violacao:
    arquivo: str
    linha: int
    coluna: int
    tipo: str
    valor: str
    sugestao: str

    def texto(self) -> str:
        return f"  {self.arquivo}:{self.linha}:{self.coluna}  {self.tipo} “{self.valor}”  → {self.sugestao}"


def _sugerir(hexa: str, r: Resolvida, md: bool = False) -> str:
    cand = {k: v for k, v in r.tokens.items()}
    nome, h, d = C.mais_proxima(hexa, cand)
    css = f"da:{nome}" if md else f"var(--da-cor-{nome.replace('_', '-')})"
    return f"{css} ({nome} {h}, ΔE {d:.1f})" if d >= 1 else f"{css} (é a mesma cor de “{nome}”)"


def _cabecalho_md(texto: str) -> tuple[str, int]:
    """Só o cabeçalho YAML de um .md (o corpo é prosa: pode citar cores à vontade)."""
    if not texto.startswith("---"):
        return "", 0
    fim = texto.find("\n---", 3)
    return (texto[: fim] if fim > 0 else ""), 0


def conferir_arquivo(p: Path, r: Resolvida, raiz: Path | None = None) -> tuple[list[Violacao], bool]:
    """(violações, conferido?)."""
    try:
        texto = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [], False
    if any("da-livre-arquivo" in ln for ln in texto.splitlines()[:10]):
        return [], True
    if p.suffix.lower() == ".md":
        texto, _ = _cabecalho_md(texto)
    nome = str(p.relative_to(raiz)) if raiz and p.is_relative_to(raiz) else str(p)
    out: list[Violacao] = []
    e_md = p.suffix.lower() == ".md"
    familias = {pp.familia.lower() for pp in r.da.tipografia.papeis.values()}
    for i, linha in enumerate(texto.splitlines(), 1):
        if _LIVRE.search(linha):
            continue
        sem_var = re.sub(r"var\([^)]*\)", lambda m: " " * len(m.group(0)), linha)  # mantém as colunas
        for m in _HEX.finditer(sem_var):
            if p.suffix.lower() == ".md" and re.search(r"da:\w", linha):
                continue
            h = C.normalizar_hex(m.group(0))
            out.append(Violacao(nome, i, m.start() + 1, "cor literal", m.group(0), _sugerir(h, r, e_md)))
        for m in _FUNC.finditer(linha):
            if "var(" in m.group(2):  # rgba(var(--da-cor-x-rgb), .5): é o jeito certo
                continue
            nums = re.findall(r"[\d.]+%?", m.group(2))
            if m.group(1).lower().startswith("rgb") and len(nums) >= 3 and not any(n.endswith("%") for n in nums[:3]):
                h = C.rgb_hex(tuple(float(n) for n in nums[:3]))
                out.append(Violacao(nome, i, m.start() + 1, "cor literal", m.group(0), _sugerir(h, r, e_md)))
            elif m.group(2).strip():
                out.append(Violacao(nome, i, m.start() + 1, "cor literal", m.group(0),
                                    "use um token: rgba(var(--da-cor-<nome>-rgb), alfa)"))
        for m in _NOME_COR.finditer(sem_var):
            v = m.group(1).lower()
            if v in _NOMES_CSS:
                out.append(Violacao(nome, i, m.start(1) + 1, "nome de cor", m.group(1), _sugerir(_NOMES_CSS[v], r, e_md)))
        for m in _FAMILIA.finditer(linha):
            valor = m.group(1).strip()
            if valor.startswith("var("):
                continue
            primeira = valor.split(",")[0].strip().strip("'\"").lower()
            if primeira and primeira not in _GENERICAS:
                papel = next((n for n, pp in r.da.tipografia.papeis.items() if pp.familia.lower() == primeira), None)
                sug = (f"var(--da-fonte-{papel})" if papel else
                       "use var(--da-fonte-<papel>)" + ("" if primeira in familias else
                                                       f"; “{primeira}” nem é uma fonte da DA"))
                out.append(Violacao(nome, i, m.start(1) + 1, "fonte literal", valor, sug))
    return out, True


def conferir(caminhos: list[Path], r: Resolvida, raiz: Path | None = None) -> dict:
    """{violacoes: [...], conferidos: n, nao_conferidos: [...]} de arquivos e pastas."""
    arquivos: list[Path] = []
    for c in caminhos:
        if c.is_dir():
            arquivos += sorted(p for p in c.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSOES
                               and "build" not in p.parts and not p.name.startswith("_"))
        elif c.is_file():
            arquivos.append(c)
    viol: list[Violacao] = []
    nao: list[str] = []
    n = 0
    for p in arquivos:
        v, ok = conferir_arquivo(p, r, raiz)
        if ok:
            n += 1
            viol += v
        else:
            nao.append(str(p))
    return {"violacoes": viol, "conferidos": n, "nao_conferidos": nao}


def texto(res: dict) -> str:
    v, n, nao = res["violacoes"], res["conferidos"], res["nao_conferidos"]
    if n == 0:
        return "NÃO CONFERIDO: nenhum arquivo lido. Isto não é sinal verde."
    cab = f"{len(v)} valor(es) fora da DA em {n} arquivo(s) conferido(s)" if v else f"{n} arquivo(s) conferido(s), tudo pela DA"
    corpo = "\n".join(x.texto() for x in v[:200])
    extra = ("\nNão conferidos: " + ", ".join(nao)) if nao else ""
    return cab + ("\n" + corpo if corpo else "") + extra
