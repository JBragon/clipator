"""Leitura e escrita de arquivos .md com cabeçalho YAML (front matter).

Cada regra do Clipator é um .md com duas partes: o cabeçalho YAML, que o motor
aplica direto, e o corpo em texto livre, que só vai para a IA quando ela está
ligada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DELIM = "---"


class FrontMatterError(ValueError):
    """Cabeçalho YAML inválido, com a linha do erro quando o YAML informa."""

    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


@dataclass
class MarkdownDoc:
    meta: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    def dumps(self) -> str:
        return dumps(self.meta, self.body)


def loads(text: str) -> MarkdownDoc:
    """Separa cabeçalho e corpo. Um .md sem cabeçalho vira só corpo."""
    text = text.lstrip("﻿")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIM:
        return MarkdownDoc({}, text)
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIM:
            raw = "".join(lines[1:i])
            body = "".join(lines[i + 1 :]).lstrip("\n")
            try:
                meta = yaml.safe_load(raw) or {}
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                line = mark.line + 2 if mark is not None else None
                raise FrontMatterError(f"YAML inválido no cabeçalho: {exc}", line) from exc
            if not isinstance(meta, dict):
                raise FrontMatterError("O cabeçalho precisa ser um mapa de chave: valor", 2)
            return MarkdownDoc(meta, body)
    raise FrontMatterError("Cabeçalho aberto com '---' mas nunca fechado", 1)


def dumps(meta: dict[str, Any], body: str = "") -> str:
    if not meta:
        return body
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip("\n")
    body = body.lstrip("\n")
    return f"{_DELIM}\n{head}\n{_DELIM}\n\n{body}" if body else f"{_DELIM}\n{head}\n{_DELIM}\n"


def read(path: str | Path) -> MarkdownDoc:
    return loads(Path(path).read_text(encoding="utf-8"))


def write(path: str | Path, meta: dict[str, Any], body: str = "") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(meta, body), encoding="utf-8")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Mescla em cascata: o mais específico sobrescreve chave a chave."""
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out
