"""Identidade, revisão e aprovação da DA, e o carimbo que cada clip renderizado leva.

- **Identidade** (`sha`): o hash de tudo o que muda pixel ou som — os tokens com a herança aplicada e os arquivos
  de fonte, LUT e logo que eles apontam. Ficam de fora o `nome`, o `conceito` (frase, referências, faça e não faça)
  e as anotações `x_`: reescrever o texto não envelhece os clips.
- **Estado** (`arte/estado.json`): revisão, aprovada ou não, quando, o sha aprovado e o histórico. Fica fora do
  `direcao.yaml` para o arquivo que a pessoa edita não ser reescrito pela máquina.
- **Carimbo** (`<saida>.arte.json` ao lado do vídeo): o sha, a revisão e se a DA estava aprovada no render. A
  conferência lista os clips feitos com outra versão da DA.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .carregar import Resolvida, ler_json
from .tipos import arquivo_da_fonte

ESTADO = "estado.json"
SUFIXO_CARIMBO = ".arte.json"


def _agora() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _sha_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def conteudo_da_identidade(r: Resolvida) -> dict[str, Any]:
    d = r.da.model_dump(mode="json")
    for fora in ("nome", "conceito", "herda", "versao"):
        d.pop(fora, None)
    arquivos: dict[str, str] = {}
    for fam in dict.fromkeys(p.familia for p in r.da.tipografia.papeis.values()):
        arq = arquivo_da_fonte(fam, r)
        if arq is not None:
            arquivos[f"fonte:{fam}"] = _sha_arquivo(arq)
    t = r.da.tratamento
    if t.lut and r.pasta is not None:
        for cand in (r.pasta / t.lut, r.pasta / "luts" / t.lut):
            if cand.exists():
                arquivos["lut"] = _sha_arquivo(cand)
                break
    if r.da.marca.logo and r.pasta is not None:
        for cand in (r.pasta / r.da.marca.logo, r.pasta / "marca" / r.da.marca.logo):
            if cand.exists():
                arquivos["logo"] = _sha_arquivo(cand)
                break
    d["_arquivos"] = arquivos
    return d


def sha(r: Resolvida) -> str:
    canon = json.dumps(conteudo_da_identidade(r), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---- estado -------------------------------------------------------------------------------------------
def ler_estado(pasta: Path) -> dict[str, Any]:
    e = ler_json(pasta / ESTADO)
    e.setdefault("revisao", 1)
    e.setdefault("aprovada", False)
    e.setdefault("historico", [])
    return e


def gravar_estado(pasta: Path, estado: dict[str, Any]) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    tmp = pasta / (ESTADO + ".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, pasta / ESTADO)


def alterada_apos_aprovacao(r: Resolvida, estado: dict[str, Any] | None = None) -> bool:
    if r.pasta is None:
        return False
    e = estado if estado is not None else ler_estado(r.pasta)
    return bool(e.get("aprovada")) and e.get("sha_aprovado") != sha(r)


def situacao(r: Resolvida) -> dict[str, Any]:
    """Revisão, aprovação e se as peças de aprovação (prancha) estão em dia com a DA atual."""
    if r.pasta is None:
        return {"revisao": 1, "aprovada": False, "sha": sha(r), "alterada_apos_aprovacao": False}
    e = ler_estado(r.pasta)
    atual = sha(r)
    prancha = ler_json(r.pasta / "build" / "prancha.json")
    return {
        "revisao": e["revisao"], "aprovada": e["aprovada"], "aprovada_em": e.get("aprovada_em"), "sha": atual,
        "sha_aprovado": e.get("sha_aprovado"), "alterada_apos_aprovacao": alterada_apos_aprovacao(r, e),
        "prancha_em_dia": prancha.get("sha") == atual and (r.pasta / "prancha.png").exists(),
    }


class ErroAprovacao(Exception):
    pass


def aprovar(r: Resolvida, estrito: bool = False, quem: str = "") -> dict[str, Any]:
    """Marca a DA atual como aprovada. Com `estrito`, recusa sem prancha em dia ou com erro de validação."""
    from .validar import resumo, validar

    if r.pasta is None:
        raise ErroAprovacao("um predefinido não se aprova; crie a DA do canal com `clipator arte criar`")
    e = ler_estado(r.pasta)
    erros, _, _ = resumo(validar(r))
    if erros:
        raise ErroAprovacao(f"a DA tem {erros} erro(s) de validação; corrija antes de aprovar (`clipator arte validar`)")
    if alterada_apos_aprovacao(r, e):
        raise ErroAprovacao("a DA mudou depois da última aprovação: rode `clipator arte revisar` antes de aprovar de novo")
    s = situacao(r)
    if estrito and not s["prancha_em_dia"]:
        raise ErroAprovacao("a prancha está ausente ou foi feita com outra versão da DA: gere com `clipator arte prancha`")
    atual = sha(r)
    if e.get("aprovada") and e.get("sha_aprovado") == atual:
        return e  # idempotente
    e.update({"aprovada": True, "aprovada_em": _agora(), "sha_aprovado": atual})
    e["historico"].append({"evento": "aprovada", "revisao": e["revisao"], "sha": atual, "em": e["aprovada_em"],
                           **({"por": quem} if quem else {})})
    gravar_estado(r.pasta, e)
    return e


def revisar(r: Resolvida, motivo: str = "") -> dict[str, Any]:
    """Abre uma nova revisão: N -> N+1, aprovação zerada (os clips antigos continuam marcados com a revisão deles)."""
    if r.pasta is None:
        raise ErroAprovacao("um predefinido não tem revisão")
    e = ler_estado(r.pasta)
    e["revisao"] = int(e.get("revisao", 1)) + 1
    e["aprovada"] = False
    e.pop("aprovada_em", None)
    e.pop("sha_aprovado", None)
    e["historico"].append({"evento": "revisao", "revisao": e["revisao"], "em": _agora(),
                           **({"motivo": motivo} if motivo else {})})
    gravar_estado(r.pasta, e)
    return e


# ---- carimbo dos renders ------------------------------------------------------------------------------
def carimbar(saida: Path, r: Resolvida, ferramenta: str = "render", parametros: dict | None = None,
             arte: Any = "canal") -> Path:
    """Grava `<saida>.arte.json`. `arte` é a referência que o estilo usou (`canal`, um predefinido ou um mapa);
    só a DA do canal passa por aprovação, então nas outras `aprovada` fica null."""
    s = situacao(r)
    aprovada = (bool(s["aprovada"]) and not s["alterada_apos_aprovacao"]) if arte == "canal" else None
    carimbo = {"sha": s["sha"], "revisao": s["revisao"], "aprovada": aprovada, "arte": arte,
               "da": r.da.nome, "ferramenta": ferramenta, "em": _agora(), "arquivo": saida.name,
               "parametros": parametros or {}}
    p = saida.with_name(saida.name + SUFIXO_CARIMBO)
    p.write_text(json.dumps(carimbo, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def conferir_carimbos(r: Resolvida | None, pastas: list[Path], resolver=None) -> list[dict[str, Any]]:
    """Cada .mp4 das pastas com o veredito: em dia, DA diferente, sem carimbo ou feito com a DA não aprovada.

    `r` é a DA do canal (para os clips feitos com `arte: canal`); `resolver(ref)` devolve a DA atual de outra
    referência (o predefinido do estilo com a marca do canal por cima), ou None se ela não existe mais.
    """
    atual = sha(r) if r is not None else None
    cache: dict[str, Any] = {}

    def sha_de(ref: Any) -> str | None:
        if ref in (None, "canal"):
            return atual
        if resolver is None:
            return None
        k = json.dumps(ref, sort_keys=True, ensure_ascii=False)
        if k not in cache:
            try:
                ra = resolver(ref)
                cache[k] = sha(ra) if ra is not None else None
            except Exception:  # noqa: BLE001 - referência que sumiu: o clip fica como “DA diferente”
                cache[k] = None
        return cache[k]

    out = []
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for v in sorted(pasta.rglob("*.mp4")):
            if v.name.endswith((".tmp.mp4",)) or v.name.startswith("_") or v.name == "preview.mp4":
                continue
            c = ler_json(v.with_name(v.name + SUFIXO_CARIMBO))
            if not c:
                veredito = "sem carimbo"
            elif c.get("sha") != sha_de(c.get("arte", "canal")):
                veredito = "DA diferente"
            elif c.get("aprovada") is False:
                veredito = "DA não aprovada"
            else:
                veredito = "em dia"
            out.append({"arquivo": str(v), "veredito": veredito, "revisao": c.get("revisao"),
                        "arte": c.get("arte", "canal") if c else None, "da": c.get("da") if c else None})
    return out
