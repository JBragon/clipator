"""Achar, herdar e resolver a DA: do `arte/direcao.yaml` à DA resolvida (todo token de cor já em hex).

Onde as coisas ficam:

- DA do canal: `<canal>/arte/direcao.yaml` (+ `arte/referencias/`, `arte/rotas/`, `arte/build/`, `arte/estado.json`).
- Predefinidos do Clipator: `dados/arte/presets/<nome>.yaml` (AGPL, originais do Clipator).
- Predefinidos pessoais: `~/.clipator/arte-presets/<nome>/direcao.yaml` (ou `$CLIPATOR_ARTE_PRESETS`), com as
  fontes, LUTs e logos que o predefinido usa na mesma pasta.

`herda` aceita o nome de um predefinido pessoal (procurado primeiro), de um predefinido do Clipator ou um caminho
para outro `direcao.yaml` (relativo à pasta do arquivo que herda). A cadeia pode ter vários níveis
(predefinido -> canal -> rota); ciclo é erro.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from . import cores as _cores
from .esquema import CORES_OBRIGATORIAS, DA, PAPEIS_OBRIGATORIOS, campos_de_cor

PASTA = "arte"
ARQUIVO = "direcao.yaml"
MAX_NIVEIS = 8


class ErroDA(Exception):
    """A DA não pôde ser lida (arquivo ausente, YAML quebrado, esquema errado, herança impossível)."""


def pasta_presets() -> Path:
    return Path(__file__).resolve().parent.parent / "dados" / "arte" / "presets"


def pasta_presets_pessoais() -> Path:
    return Path(os.environ.get("CLIPATOR_ARTE_PRESETS") or Path.home() / ".clipator" / "arte-presets")


def listar_presets() -> list[dict[str, Any]]:
    """[{nome, origem, frase, arquivo}] dos predefinidos do Clipator e dos pessoais."""
    out = []
    for p in sorted(pasta_presets().glob("*.yaml")):
        dados = _ler_yaml(p)
        out.append({"nome": p.stem, "origem": "clipator", "titulo": dados.get("nome") or p.stem,
                    "frase": (dados.get("conceito") or {}).get("frase", ""), "arquivo": str(p)})
    pessoais = pasta_presets_pessoais()
    if pessoais.is_dir():
        for d in sorted(pessoais.iterdir()):
            if (d / ARQUIVO).exists():
                dados = _ler_yaml(d / ARQUIVO)
                out.append({"nome": d.name, "origem": "pessoal", "titulo": dados.get("nome") or d.name,
                            "frase": (dados.get("conceito") or {}).get("frase", ""), "arquivo": str(d / ARQUIVO)})
    return out


def _ler_yaml(p: Path) -> dict[str, Any]:
    try:
        dados = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        linha = getattr(getattr(exc, "problem_mark", None), "line", None)
        raise ErroDA(f"{p.name}: YAML inválido" + (f" na linha {linha + 1}" if linha is not None else "")
                     + f" ({getattr(exc, 'problem', exc)})") from exc
    except OSError as exc:
        raise ErroDA(f"não consegui ler {p}: {exc}") from exc
    if not isinstance(dados, dict):
        raise ErroDA(f"{p.name}: o arquivo precisa ser um mapa de chaves (seção: valores)")
    return dados


def achar_herdado(nome: str, de: Path | None) -> Path:
    """O arquivo que `herda: nome` aponta, visto a partir da pasta `de`."""
    if nome.endswith((".yaml", ".yml")) or "/" in nome or "\\" in nome:
        p = Path(nome)
        if not p.is_absolute() and de is not None:
            p = (de / p).resolve()
        if p.is_dir():
            p = p / ARQUIVO
        if p.exists():
            return p
        raise ErroDA(f"herda: o arquivo “{nome}” não existe ({p})")
    pessoal = pasta_presets_pessoais() / nome / ARQUIVO
    if pessoal.exists():
        return pessoal
    embutido = pasta_presets() / f"{nome}.yaml"
    if embutido.exists():
        return embutido
    nomes = ", ".join(p["nome"] for p in listar_presets())
    raise ErroDA(f"herda: não existe predefinido “{nome}”. Os que existem: {nomes}")


def mesclar(base: dict[str, Any], filho: dict[str, Any]) -> dict[str, Any]:
    """Mescla em cascata: mapas se juntam chave a chave, o filho vence, listas e valores substituem inteiros.

    `null` no filho apaga o que veio da base (útil para tirar a sombra ou o contorno herdados).
    """
    out = copy.deepcopy(base)
    for k, v in (filho or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = mesclar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def cadeia(arquivo: Path) -> tuple[dict[str, Any], list[str]]:
    """(dados mesclados, [arquivos da cadeia, do mais antigo ao próprio])."""
    vistos: list[Path] = []
    camadas: list[dict[str, Any]] = []
    atual: Path | None = arquivo.resolve()
    while atual is not None:
        if atual in vistos:
            raise ErroDA("herda: a herança dá uma volta e chega de novo em " + atual.name)
        if len(vistos) >= MAX_NIVEIS:
            raise ErroDA(f"herda: mais de {MAX_NIVEIS} níveis de herança")
        vistos.append(atual)
        dados = _ler_yaml(atual)
        camadas.append(dados)
        h = dados.get("herda")
        atual = achar_herdado(str(h), atual.parent) if h else None
    mesclado: dict[str, Any] = {}
    for dados in reversed(camadas):
        mesclado = mesclar(mesclado, {k: v for k, v in dados.items() if k != "herda"})
    mesclado["herda"] = camadas[0].get("herda")
    return mesclado, [str(p) for p in reversed(vistos)]


def _mensagem_pydantic(exc: ValidationError) -> str:
    linhas = []
    for e in exc.errors()[:12]:
        onde = ".".join(str(x) for x in e.get("loc", ()))
        msg = e.get("msg", "")
        if e.get("type") == "extra_forbidden":
            msg = "chave desconhecida (erro de digitação? anotações livres começam com x_)"
        elif e.get("type") == "missing":
            msg = "campo obrigatório ausente"
        linhas.append(f"  - {onde}: {msg}")
    return "\n".join(linhas)


@dataclass
class Resolvida:
    """A DA pronta para o uso: o modelo validado, os tokens de cor em hex e o resto que as peças consultam."""

    da: DA
    arquivo: Path | None
    pasta: Path | None  # a pasta arte/ (referências, fontes, LUTs, logos relativos a ela)
    ancestrais: list[str]
    tokens: dict[str, str]  # nome -> hex: paleta, neutro-N, serie-N
    serie_hex: list[str]
    gradientes_css: dict[str, str]
    campos: dict[str, str | None]  # "legenda.cor" -> hex (None quando o campo é opcional e está vazio)
    erros_de_token: list[tuple[str, str]] = field(default_factory=list)  # (campo, valor que não resolve)
    bruto: dict[str, Any] = field(default_factory=dict)

    # ---- consultas ----------------------------------------------------------------------------------
    def cor(self, valor: str | None, padrao: str = "#FF00FF") -> str:
        """Token ou hex -> hex. Desconhecido devolve `padrao` (magenta: aparece na prancha, de propósito)."""
        if valor is None:
            return padrao
        return resolver_cor(valor, self.tokens) or padrao

    def campo(self, caminho: str) -> str | None:
        return self.campos.get(caminho)

    def papel(self, nome: str):
        return self.da.tipografia.papeis.get(nome) or self.da.tipografia.papeis.get("corpo")

    def px(self, fracao: float, largura: int, altura: int) -> int:
        return max(1, round(fracao * min(largura, altura)))

    def fundo_thumb_css(self) -> str:
        f = self.da.thumbnail.fundo
        if f.startswith("gradiente:"):
            return self.gradientes_css.get(f.split(":", 1)[1], self.cor("fundo"))
        if f == "foto":
            return self.cor("fundo")
        return self.cor(f)


def resolver_cor(valor: str, tokens: dict[str, str]) -> str | None:
    v = str(valor).strip()
    if _cores.e_hex(v):
        return _cores.normalizar_hex(v)
    return tokens.get(v)


def _tokens(da: DA) -> tuple[dict[str, str], list[str], list[tuple[str, str]]]:
    tokens = dict(da.cor.paleta)
    for i, h in enumerate(da.cor.neutros, 1):
        tokens[f"neutro-{i}"] = h
    erros: list[tuple[str, str]] = []
    serie = []
    for i, item in enumerate(da.cor.serie, 1):
        h = resolver_cor(item, tokens)
        if h is None:
            erros.append((f"cor.serie[{i}]", str(item)))
            h = "#FF00FF"
        serie.append(h)
    for i, h in enumerate(serie, 1):
        tokens[f"serie-{i}"] = h
    return tokens, serie, erros


def _css_gradiente(g, tokens: dict[str, str], erros: list, nome: str) -> str:
    paradas = []
    for cor, pos in g.paradas:
        h = resolver_cor(cor, tokens)
        if h is None:
            erros.append((f"cor.gradientes.{nome}", str(cor)))
            h = "#FF00FF"
        paradas.append(f"{h} {pos * 100:g}%")
    if g.tipo == "radial":
        return f"radial-gradient(circle at 50% 35%, {', '.join(paradas)})"
    return f"linear-gradient({g.angulo:g}deg, {', '.join(paradas)})"


def _pegar(obj: Any, caminho: str) -> tuple[bool, Any]:
    atual = obj
    for parte in caminho.split("."):
        if atual is None:
            return False, None
        atual = getattr(atual, parte, None)
    return True, atual


def resolver(dados: dict[str, Any], arquivo: Path | None = None, ancestrais: list[str] | None = None) -> Resolvida:
    """Valida os dados mesclados e resolve os tokens. ErroDA com a lista do que está errado."""
    try:
        da = DA.model_validate(dados)
    except ValidationError as exc:
        raise ErroDA("a DA não passou no esquema:\n" + _mensagem_pydantic(exc)) from exc
    faltam = [c for c in CORES_OBRIGATORIAS if c not in da.cor.paleta]
    if faltam:
        raise ErroDA("cor.paleta: faltam as cores " + ", ".join(faltam) + " (herde de `base` para ganhar todas)")
    faltam = [p for p in PAPEIS_OBRIGATORIOS if p not in da.tipografia.papeis]
    if faltam:
        raise ErroDA("tipografia.papeis: faltam os papéis " + ", ".join(faltam))
    tokens, serie, erros = _tokens(da)
    grads = {n: _css_gradiente(g, tokens, erros, n) for n, g in da.cor.gradientes.items()}
    campos: dict[str, str | None] = {}
    for caminho in campos_de_cor():
        ok, valor = _pegar(da, caminho)
        if not ok or valor is None:
            campos[caminho] = None
            continue
        h = resolver_cor(valor, tokens)
        if h is None:
            erros.append((caminho, str(valor)))
        campos[caminho] = h
    fundo = da.thumbnail.fundo
    if fundo.startswith("gradiente:") and fundo.split(":", 1)[1] not in da.cor.gradientes or not fundo.startswith("gradiente:") and fundo != "foto" and resolver_cor(fundo, tokens) is None:
        erros.append(("thumbnail.fundo", fundo))
    pasta = arquivo.parent if arquivo is not None else None
    return Resolvida(da=da, arquivo=arquivo, pasta=pasta, ancestrais=ancestrais or [], tokens=tokens, serie_hex=serie,
                     gradientes_css=grads, campos=campos, erros_de_token=erros, bruto=dados)


def carregar_arquivo(arquivo: Path) -> Resolvida:
    if not arquivo.exists():
        raise ErroDA(f"não existe {arquivo}")
    dados, anc = cadeia(arquivo)
    return resolver(dados, arquivo, anc)


def carregar_preset(nome: str) -> Resolvida:
    return carregar_arquivo(achar_herdado(nome, None))


def pasta_do_canal(canal_path: Path) -> Path:
    return canal_path / PASTA


def arquivo_do_canal(canal_path: Path) -> Path:
    return pasta_do_canal(canal_path) / ARQUIVO


def do_canal(canal_path: Path) -> Resolvida | None:
    """A DA do canal, ou None se o canal ainda não tem uma (o render segue com as fichas dos estilos)."""
    arq = arquivo_do_canal(canal_path)
    if not arq.exists():
        return None
    return carregar_arquivo(arq)


def para_json(r: Resolvida) -> dict[str, Any]:
    """A resolvida inteira em JSON (vai para arte/build/da.resolvida.json e para o MCP)."""
    d = r.da.model_dump(mode="json")
    d["_resolvido"] = {"tokens": r.tokens, "serie": r.serie_hex, "gradientes": r.gradientes_css, "campos": r.campos,
                       "ancestrais": r.ancestrais, "fundo_thumbnail": r.fundo_thumb_css()}
    return d


def salvar_yaml(arquivo: Path, dados: dict[str, Any], cabecalho: str = "") -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    texto = yaml.safe_dump(dados, allow_unicode=True, sort_keys=False, width=110, default_flow_style=None)
    tmp = arquivo.with_suffix(arquivo.suffix + ".tmp")
    tmp.write_text((cabecalho.rstrip() + "\n" if cabecalho else "") + texto, encoding="utf-8")
    os.replace(tmp, arquivo)


def ler_json(p: Path) -> dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
