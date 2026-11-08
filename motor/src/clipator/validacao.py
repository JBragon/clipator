"""Validação dos arquivos do workspace, para o editor mostrar erros como uma IDE."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from . import markdown as md
from .models import Canal, Clip, ConfigApp, Estilo, Projeto, Regras, Thumb


def tipo_arquivo(caminho: str) -> str | None:
    p = PurePosixPath(caminho.replace("\\", "/"))
    nome = p.name
    if nome == "canal.md":
        return "canal"
    if nome == "regras.md":
        return "regras"
    if nome == "titulos.md":
        return "titulos"
    if nome == "thumb.md":
        return "thumb"
    if nome == "estilo.md" or (p.suffix == ".md" and "estilos" in p.parts):
        return "estilo"
    if nome == "clip.yaml":
        return "clip"
    if nome == "projeto.yaml":
        return "projeto"
    if nome == "config.yaml" and ".clipator" in p.parts:
        return "config"
    return None


_MODELOS: dict[str, type[BaseModel]] = {
    "canal": Canal, "regras": Regras, "estilo": Estilo, "clip": Clip, "projeto": Projeto, "config": ConfigApp,
    "thumb": Thumb,
}


def _linha_da_chave(texto: str, loc: tuple[Any, ...], deslocamento: int) -> int:
    """Linha (1-based) onde a primeira chave do caminho aparece."""
    if not loc:
        return 1 + deslocamento
    chave = str(loc[-1]) if not isinstance(loc[-1], int) else str(loc[-2]) if len(loc) > 1 else ""
    for i, ln in enumerate(texto.splitlines(), start=1):
        if ln.strip().startswith(f"{chave}:"):
            return i + deslocamento
    return 1 + deslocamento


def validar(caminho: str, conteudo: str) -> list[dict]:
    """Lista de {linha, mensagem}. Vazia quando está tudo certo."""
    tipo = tipo_arquivo(caminho)
    if tipo is None:
        return []
    erros: list[dict] = []
    if caminho.endswith(".md"):
        try:
            doc = md.loads(conteudo)
        except md.FrontMatterError as exc:
            return [{"linha": exc.line or 1, "mensagem": str(exc)}]
        dados, texto_yaml, desloc = doc.meta, conteudo, 0
    else:
        try:
            dados = yaml.safe_load(conteudo) or {}
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            return [{"linha": (mark.line + 1) if mark else 1, "mensagem": f"YAML inválido: {exc}"}]
        texto_yaml, desloc = conteudo, 0
    if tipo == "titulos":
        f = dados.get("formulas")
        if f is not None and not (isinstance(f, list) and all(isinstance(x, str) for x in f)):
            erros.append({"linha": _linha_da_chave(texto_yaml, ("formulas",), desloc), "mensagem": "formulas precisa ser uma lista de textos"})
        return erros
    modelo = _MODELOS[tipo]
    if tipo == "canal":
        dados = {"nome": "canal", **dados}
    try:
        modelo.model_validate(dados)
    except ValidationError as exc:
        for e in exc.errors():
            loc = tuple(e.get("loc", ()))
            campo = ".".join(str(x) for x in loc)
            erros.append({"linha": _linha_da_chave(texto_yaml, loc, desloc), "mensagem": f"{campo}: {e.get('msg')}"})
    return erros
