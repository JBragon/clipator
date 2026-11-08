"""Stickers do editor: pacote curado (Fluent Emoji da Microsoft, MIT), stickers do canal e, como extra
opcional, a busca online do Iconify.

- Pacote: `dados/stickers/pacote.json` lista cada sticker (URL presa a um commit, sha256, palavras em
  português, categoria). `instalar()` baixa uma vez para `~/.clipator/stickers` (ou CLIPATOR_STICKERS),
  confere o sha256 e pula o que já existe. Depois disso tudo funciona sem internet.
- Canal: arquivos em `canais/<canal>/stickers/` (PNG, APNG, WebP ou GIF) entram na biblioteca. O usuário
  sobe a marca dele (ou qualquer PNG) pelo editor; `salvar_enviado()` confere tamanho e imagem antes de gravar.
- Busca online (só quando o usuário clica): Fluent Emoji e Fluent Flat (MIT), Noto (Apache 2.0) e
  Twemoji (CC BY 4.0, com crédito). O PNG baixado vai para `canais/<canal>/stickers/web/` com o crédito.

Um sticker é referenciado no documento de edição por `ref`: "pacote:<id>", "canal:<arquivo>" ou
"web:<arquivo>". `resolver()` converte a referência num arquivo dentro das pastas permitidas.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .workspace import _dados

MANIFESTO = "stickers/pacote.json"
EXT = (".png", ".apng", ".webp", ".gif")
_ARQ = re.compile(r"^[\w\-. ]{1,120}$")


class ErroSticker(Exception):
    pass


def pasta_pacote() -> Path:
    return Path(os.environ.get("CLIPATOR_STICKERS") or (Path.home() / ".clipator" / "stickers"))


def manifesto(caminho: Path | None = None) -> dict[str, Any]:
    p = caminho or _dados(*MANIFESTO.split("/"))
    dados = json.loads(p.read_text(encoding="utf-8"))
    validar_manifesto(dados)
    return dados


def validar_manifesto(m: dict[str, Any]) -> None:
    """Cada sticker tem id único, arquivo simples, URL https de um commit fixo, sha256 e licença conhecida."""
    pacotes = m.get("pacotes") or {}
    vistos: set[str] = set()
    for s in m.get("stickers") or []:
        if s["id"] in vistos:
            raise ErroSticker(f"id repetido no pacote: {s['id']}")
        vistos.add(s["id"])
        if s["pacote"] not in pacotes:
            raise ErroSticker(f"pacote desconhecido: {s['pacote']}")
        commit = pacotes[s["pacote"]]["commit"]
        if not s["url"].startswith("https://") or commit not in s["url"]:
            raise ErroSticker(f"URL sem o commit fixo: {s['id']}")
        if not re.fullmatch(r"[0-9a-f]{64}", s["sha256"]) or not _ARQ.match(s["arquivo"]) or "/" in s["arquivo"]:
            raise ErroSticker(f"sticker inválido: {s['id']}")
    for p in pacotes.values():
        if p["licenca"] not in ("MIT", "Apache 2.0", "CC BY 4.0"):
            raise ErroSticker(f"licença não aceita: {p['licenca']}")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _baixar(url: str, timeout: int = 60, limite: int = 8 * 1024 * 1024) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Clipator (+https://github.com/JBragon/clipator)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - URLs do manifesto ou do Iconify
            return r.read(limite)
    except Exception as exc:  # noqa: BLE001
        raise ErroSticker(f"Não consegui baixar (sem internet?): {exc}") from exc


def status(m: dict[str, Any] | None = None) -> dict[str, Any]:
    m = m or manifesto()
    pasta = pasta_pacote()
    feitos = [s for s in m["stickers"] if (pasta / s["arquivo"]).is_file()]
    return {"instalados": len(feitos), "total": len(m["stickers"]), "bytes": sum(s["bytes"] for s in m["stickers"]),
            "pasta": str(pasta)}


def instalar(progresso: Callable[[float, str], None] | None = None, m: dict[str, Any] | None = None,
             baixar: Callable[[str], bytes] = _baixar) -> dict[str, Any]:
    """Baixa o que falta do pacote, conferindo o sha256 (arquivo que não confere é apagado e baixado de novo)."""
    m = m or manifesto()
    pasta = pasta_pacote()
    pasta.mkdir(parents=True, exist_ok=True)
    baixados, erros = 0, []
    total = len(m["stickers"])
    for n, s in enumerate(m["stickers"]):
        destino = pasta / s["arquivo"]
        if destino.is_file() and _sha(destino) == s["sha256"]:
            continue
        try:
            dados = baixar(s["url"])
            if hashlib.sha256(dados).hexdigest() != s["sha256"]:
                raise ErroSticker(f"o arquivo baixado não confere (sha256): {s['id']}")
            tmp = destino.with_suffix(".tmp")
            tmp.write_bytes(dados)
            tmp.replace(destino)
            baixados += 1
        except ErroSticker as exc:
            erros.append(str(exc))
        if progresso:
            progresso((n + 1) / total, f"stickers: {n + 1}/{total}")
    return {**status(m), "baixados": baixados, "erros": erros}


def _animado(p: Path) -> bool:
    try:
        cab = p.read_bytes()[:256] if p.stat().st_size < 64 * 1024 * 1024 else b""
    except OSError:
        return False
    if cab.startswith(b"\x89PNG"):
        return b"acTL" in cab
    if cab.startswith(b"GIF8"):
        return True
    if cab[:4] == b"RIFF" and cab[8:12] == b"WEBP":
        return b"ANIM" in cab
    return False


def listar(pasta_canal: Path | None, m: dict[str, Any] | None = None) -> dict[str, Any]:
    """A biblioteca: o pacote (com a indicação do que está instalado), os do canal e os baixados da web."""
    from . import cta

    m = m or manifesto()
    pasta = pasta_pacote()
    out = cta.listar()  # as chamadas (Inscreva-se, curtir…) vêm primeiro
    for s in m["stickers"]:
        pac = m["pacotes"][s["pacote"]]
        out.append({"ref": f"pacote:{s['id']}", "nome": s["nome"], "categoria": s["categoria"], "palavras": s["palavras"],
                    "animado": s["animado"], "pacote": pac["nome"], "licenca": pac["licenca"], "credito": False,
                    "instalado": (pasta / s["arquivo"]).is_file()})
    if pasta_canal is not None:
        creditos = {c["arquivo"]: c for c in _creditos_web(pasta_canal)}
        base = pasta_canal / "stickers"
        for p in sorted(base.glob("*")) if base.is_dir() else []:
            if p.suffix.lower() in EXT and p.is_file():
                out.append({"ref": f"canal:{p.name}", "nome": p.stem.replace("-", " "), "categoria": "canal",
                            "palavras": p.stem.lower().replace("-", " ").split(), "animado": _animado(p),
                            "pacote": "Canal", "licenca": "do canal", "credito": False, "instalado": True})
        web = base / "web"
        for p in sorted(web.glob("*.png")) if web.is_dir() else []:
            c = creditos.get(p.name, {})
            out.append({"ref": f"web:{p.name}", "nome": c.get("nome") or p.stem, "categoria": "internet",
                        "palavras": (c.get("nome") or p.stem).lower().split(), "animado": False,
                        "pacote": c.get("colecao", "Internet"), "licenca": c.get("licenca", "?"),
                        "credito": bool(c.get("credito")), "instalado": True})
    return {"stickers": out, "categorias": ["chamadas"] + sorted({s["categoria"] for s in out} - {"chamadas"}),
            "status": status(m)}


def resolver(ref: str, pasta_canal: Path | None, m: dict[str, Any] | None = None,
             params: dict[str, Any] | None = None) -> Path | None:
    """O arquivo de um sticker; None se não existe ou se a referência sair das pastas permitidas.

    As chamadas ("cta:inscreva-se") são geradas aqui com o texto e as cores de `params` (e ficam em cache).
    """
    tipo, _, nome = (ref or "").partition(":")
    if tipo == "cta":
        from . import cta

        if nome not in cta.MODELOS:
            return None
        fontes = pasta_canal / "assets" / "fontes" if pasta_canal is not None else None
        return cta.gerar(nome, params, pasta_pacote() / "chamadas", pasta_pacote(), fontes)
    if tipo == "pacote":
        m = m or manifesto()
        s = next((x for x in m["stickers"] if x["id"] == nome), None)
        p = pasta_pacote() / s["arquivo"] if s else None
    elif tipo in ("canal", "web") and pasta_canal is not None and _ARQ.match(nome) and "/" not in nome and ".." not in nome:
        base = pasta_canal / "stickers" / ("web" if tipo == "web" else "")
        p = base / nome
        if p.suffix.lower() not in EXT:
            return None
    else:
        return None
    return p if p and p.is_file() else None


LIMITE_ENVIO = 5 * 1024 * 1024  # 5 MB
LADO_MIN, LADO_MAX = 32, 4096


def salvar_enviado(pasta_canal: Path, nome: str, dados: bytes) -> dict[str, Any]:
    """Grava um PNG enviado pelo usuário (a marca do canal, por exemplo) em `canais/<canal>/stickers/`.

    Confere: até 5 MB, PNG de verdade (APNG também), imagem que abre inteira e lados entre 32 e 4096 px.
    Um nome que já existe ganha um número no fim, para não apagar o sticker antigo.
    """
    if not dados:
        raise ErroSticker("O arquivo está vazio.")
    if len(dados) > LIMITE_ENVIO:
        raise ErroSticker(f"O arquivo tem {len(dados) / 1e6:.1f} MB; o limite é {LIMITE_ENVIO // (1024 * 1024)} MB.")
    if not dados.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ErroSticker("Envie uma imagem PNG.")
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(dados)) as img:
            img.verify()
        with Image.open(io.BytesIO(dados)) as img:
            larg, alt = img.size
            img.load()  # decodifica de verdade (o verify não pega todo arquivo cortado)
    except Exception as exc:  # noqa: BLE001
        raise ErroSticker("A imagem está corrompida ou não é um PNG válido.") from exc
    if min(larg, alt) < LADO_MIN or max(larg, alt) > LADO_MAX:
        raise ErroSticker(f"A imagem tem {larg}x{alt} px; use entre {LADO_MIN} e {LADO_MAX} px de lado.")
    from .workspace import slugify

    base = slugify(Path(nome or "").stem or "sticker", 60) or "sticker"
    pasta = pasta_canal / "stickers"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo, n = f"{base}.png", 2
    while (pasta / arquivo).exists():
        arquivo, n = f"{base}-{n}.png", n + 1
    (pasta / arquivo).write_bytes(dados)
    return {"ref": f"canal:{arquivo}", "arquivo": arquivo, "largura": larg, "altura": alt, "animado": _animado(pasta / arquivo)}


def para_render(p: Path, cache: Path) -> tuple[Path, bool]:
    """(arquivo que o FFmpeg lê, animado?). WebP e GIF animados viram APNG (o FFmpeg lê APNG com alfa)."""
    anim = _animado(p)
    if p.suffix.lower() in (".webp", ".gif"):
        from PIL import Image

        cache.mkdir(parents=True, exist_ok=True)
        destino = cache / f"{hashlib.sha1(str(p).encode() + str(p.stat().st_mtime).encode()).hexdigest()[:12]}.png"
        if not destino.exists():
            with Image.open(p) as img:
                if getattr(img, "is_animated", False):
                    quadros, duracoes = [], []
                    for i in range(img.n_frames):
                        img.seek(i)
                        quadros.append(img.convert("RGBA"))
                        duracoes.append(img.info.get("duration", 80))
                    quadros[0].save(destino, save_all=True, append_images=quadros[1:], duration=duracoes, loop=0)
                    anim = True
                else:
                    img.convert("RGBA").save(destino)
                    anim = False
        return destino, anim
    return p, anim


def creditos_do_clip(refs: list[str], pasta_canal: Path) -> str:
    """Linhas de crédito para a descrição (só as licenças que pedem crédito, como a CC BY do Twemoji)."""
    creditos = {c["arquivo"]: c for c in _creditos_web(pasta_canal)}
    linhas = []
    for ref in refs:
        tipo, _, nome = ref.partition(":")
        c = creditos.get(nome) if tipo == "web" else None
        if c and c.get("credito"):
            linha = f"Stickers: {c['colecao']} ({c['autor']}), licença {c['licenca']} – {c['fonte']}"
            if linha not in linhas:
                linhas.append(linha)
    return "\n".join(linhas)


# ---- busca online (extra opcional) ----------------------------------------------------------
API = "https://api.iconify.design"
COLECOES: dict[str, dict[str, Any]] = {
    "fluent-emoji": {"nome": "Fluent Emoji", "licenca": "MIT", "autor": "Microsoft",
                     "url": "https://github.com/microsoft/fluentui-emoji", "credito": False},
    "fluent-emoji-flat": {"nome": "Fluent Emoji Flat", "licenca": "MIT", "autor": "Microsoft",
                          "url": "https://github.com/microsoft/fluentui-emoji", "credito": False},
    "noto": {"nome": "Noto Emoji", "licenca": "Apache 2.0", "autor": "Google",
             "url": "https://github.com/googlefonts/noto-emoji", "credito": False},
    "twemoji": {"nome": "Twemoji", "licenca": "CC BY 4.0", "autor": "Twitter / jdecked",
                "url": "https://github.com/jdecked/twemoji", "credito": True},
}
_NOME_WEB = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def _separar(id_: str) -> tuple[str, str]:
    prefixo, _, nome = id_.partition(":")
    if prefixo not in COLECOES or not _NOME_WEB.match(nome):
        raise ErroSticker(f"Sticker desconhecido: {id_}")
    return prefixo, nome


def buscar_web(termo: str, colecao: str | None = None, limite: int = 60, baixar: Callable[[str], bytes] = _baixar) -> list[dict[str, Any]]:
    termo = (termo or "").strip()[:60]
    if not termo:
        return []
    prefixos = [colecao] if colecao in COLECOES else list(COLECOES)
    q = urllib.parse.urlencode({"query": termo, "prefixes": ",".join(prefixos), "limit": max(10, min(200, limite))})
    dados = json.loads(baixar(f"{API}/search?{q}").decode("utf-8") or "{}")
    out = []
    for id_ in dados.get("icons") or []:
        try:
            prefixo, nome = _separar(str(id_))
        except ErroSticker:
            continue  # coleção fora da lista (OpenMoji, por exemplo): não entra
        info = COLECOES[prefixo]
        out.append({"id": f"{prefixo}:{nome}", "nome": nome.replace("-", " "), "colecao": info["nome"],
                    "licenca": info["licenca"], "credito": info["credito"]})
    return sorted(out, key=lambda x: x["credito"])  # primeiro os que não pedem crédito


def svg_web(id_: str, cache: Path, baixar: Callable[[str], bytes] = _baixar) -> Path:
    prefixo, nome = _separar(id_)
    destino = cache / prefixo / f"{nome}.svg"
    if not destino.exists():
        dados = baixar(f"{API}/{prefixo}/{nome}.svg?height=256")
        if b"<svg" not in dados[:500]:
            raise ErroSticker("O banco de stickers não devolveu uma imagem.")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
    return destino


def _creditos_web(pasta_canal: Path) -> list[dict[str, Any]]:
    p = pasta_canal / "stickers" / "web" / "creditos.json"
    try:
        return [c for c in json.loads(p.read_text(encoding="utf-8")) if isinstance(c, dict)] if p.exists() else []
    except json.JSONDecodeError:
        return []


def salvar_web(pasta_canal: Path, id_: str, png: bytes) -> dict[str, Any]:
    """Grava o PNG (desenhado pela tela a partir do SVG) no canal, com o crédito e a licença."""
    prefixo, nome = _separar(id_)
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 4 * 1024 * 1024:
        raise ErroSticker("Imagem inválida.")
    pasta = pasta_canal / "stickers" / "web"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = f"{prefixo}-{nome}.png"
    (pasta / arquivo).write_bytes(png)
    info = COLECOES[prefixo]
    reg = {"arquivo": arquivo, "id": id_, "nome": nome.replace("-", " "), "colecao": info["nome"], "licenca": info["licenca"],
           "autor": info["autor"], "fonte": info["url"], "credito": info["credito"],
           "baixado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    regs = [c for c in _creditos_web(pasta_canal) if c.get("arquivo") != arquivo] + [reg]
    (pasta / "creditos.json").write_text(json.dumps(regs, ensure_ascii=False, indent=1), encoding="utf-8")
    return {**reg, "ref": f"web:{arquivo}"}
