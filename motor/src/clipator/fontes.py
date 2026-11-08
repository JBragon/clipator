"""Pacote de fontes do texto livre: 70 famílias do Google Fonts (OFL ou Apache 2.0).

`dados/fontes/pacote.json` lista cada fonte com a URL presa a um commit do repositório google/fonts,
o sha256, a categoria e, nas fontes variáveis, o peso usado (normal e negrito). Nada vem junto com o
instalador: cada fonte é baixada uma vez quando o usuário escolhe ela no editor (ou todas de uma vez) e
fica em `~/.clipator/fontes` (ou CLIPATOR_FONTES). Depois disso funciona sem internet; uma fonte que
não foi baixada cai na Montserrat no render.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from .workspace import _dados

MANIFESTO = "fontes/pacote.json"
LICENCAS = ("OFL", "Apache 2.0")
CATEGORIAS = ("impacto", "manuscrita", "retro", "terror", "pixel", "elegante")
_ARQ = re.compile(r"^[\w\-.]{1,120}\.ttf$")


class ErroFonte(Exception):
    pass


def pasta() -> Path:
    return Path(os.environ.get("CLIPATOR_FONTES") or (Path.home() / ".clipator" / "fontes"))


def validar_manifesto(m: dict[str, Any]) -> None:
    commit = m["fonte"]["commit"]
    vistos: set[str] = set()
    for f in m["fontes"]:
        if f["id"] in vistos or not re.fullmatch(r"[a-z0-9-]{2,60}", f["id"]):
            raise ErroFonte(f"id inválido ou repetido: {f['id']}")
        vistos.add(f["id"])
        if f["licenca"] not in LICENCAS or f["categoria"] not in CATEGORIAS:
            raise ErroFonte(f"licença ou categoria desconhecida: {f['id']}")
        for k in ("normal", "italico"):
            a = f.get(k)
            if a is None:
                continue
            if not a["url"].startswith(f"https://raw.githubusercontent.com/google/fonts/{commit}/"):
                raise ErroFonte(f"URL sem o commit fixo: {f['id']}")
            if not re.fullmatch(r"[0-9a-f]{64}", a["sha256"]) or not _ARQ.match(a["arquivo"]):
                raise ErroFonte(f"arquivo inválido: {f['id']}")


_cache: dict[str, Any] = {}


def manifesto(caminho: Path | None = None) -> dict[str, Any]:
    p = caminho or _dados(*MANIFESTO.split("/"))
    if caminho is None and "m" in _cache:
        return _cache["m"]
    m = json.loads(p.read_text(encoding="utf-8"))
    validar_manifesto(m)
    if caminho is None:
        _cache["m"] = m
    return m


def info(id_: str, m: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return next((f for f in (m or manifesto())["fontes"] if f["id"] == id_), None)


def instalada(f: dict[str, Any]) -> bool:
    return (pasta() / f["normal"]["arquivo"]).is_file()


def caminho(id_: str, italico: bool, m: dict[str, Any] | None = None) -> tuple[Path, bool, list[int] | None] | None:
    """(arquivo, já é itálica?, [peso normal, peso negrito] das variáveis) de uma fonte baixada; None se não está."""
    f = info(id_, m)
    if f is None or not instalada(f):
        return None
    if italico and f.get("italico") and (pasta() / f["italico"]["arquivo"]).is_file():
        return pasta() / f["italico"]["arquivo"], True, f.get("peso")
    return pasta() / f["normal"]["arquivo"], False, f.get("peso")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _baixar_padrao(url: str) -> bytes:
    from .stickers import ErroSticker, _baixar

    try:
        return _baixar(url, limite=8 * 1024 * 1024)
    except ErroSticker as exc:
        raise ErroFonte(str(exc)) from exc


def baixar(id_: str, m: dict[str, Any] | None = None, baixar_url: Callable[[str], bytes] = _baixar_padrao) -> dict[str, Any]:
    """Baixa uma fonte do pacote (e a versão itálica, se tiver), conferindo o sha256."""
    f = info(id_, m)
    if f is None:
        raise ErroFonte(f"Fonte desconhecida: {id_}")
    destino_dir = pasta()
    destino_dir.mkdir(parents=True, exist_ok=True)
    for k in ("normal", "italico"):
        a = f.get(k)
        if a is None:
            continue
        destino = destino_dir / a["arquivo"]
        if destino.is_file() and _sha(destino) == a["sha256"]:
            continue
        dados = baixar_url(a["url"])
        if hashlib.sha256(dados).hexdigest() != a["sha256"]:
            raise ErroFonte(f"O arquivo baixado não confere (sha256): {f['nome']}")
        tmp = destino.with_suffix(".tmp")
        tmp.write_bytes(dados)
        tmp.replace(destino)
    return {"id": f["id"], "instalada": True}


def status(m: dict[str, Any] | None = None) -> dict[str, Any]:
    m = m or manifesto()
    total = sum(f["normal"]["bytes"] + (f.get("italico") or {}).get("bytes", 0) for f in m["fontes"])
    return {"instaladas": sum(instalada(f) for f in m["fontes"]), "total": len(m["fontes"]), "bytes": total,
            "pasta": str(pasta())}


def instalar(progresso: Callable[[float, str], None] | None = None, m: dict[str, Any] | None = None,
             baixar_url: Callable[[str], bytes] = _baixar_padrao) -> dict[str, Any]:
    """Baixa todas as que faltam (job "fontes")."""
    m = m or manifesto()
    erros = []
    n = len(m["fontes"])
    for k, f in enumerate(m["fontes"]):
        try:
            baixar(f["id"], m, baixar_url)
        except ErroFonte as exc:
            erros.append(str(exc))
        if progresso:
            progresso((k + 1) / n, f"fontes: {k + 1}/{n}")
    return {**status(m), "erros": erros}


def listar(m: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    m = m or manifesto()
    return [{"id": f["id"], "nome": f["nome"], "categoria": f["categoria"], "licenca": f["licenca"],
             "italico": "italico" in f, "instalada": instalada(f), "origem": "google",
             "bytes": f["normal"]["bytes"] + (f.get("italico") or {}).get("bytes", 0)} for f in m["fontes"]]
