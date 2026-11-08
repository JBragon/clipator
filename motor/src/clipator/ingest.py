"""Ingestão: baixa por link (yt-dlp) ou importa um arquivo, e extrai o áudio.

A validação de "link de um vídeo só" foi adaptada de openshorts/yt_clients.py
(youtube_non_video_reason), MIT License, Copyright (c) 2024 OpenShorts.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import media
from .media import Cancelado, Progress
from .workspace import ProjetoWS, write_json

DURACAO_MAXIMA = 4 * 3600  # decisão 7: vídeos de até 4 horas
EXTENSOES_VIDEO = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".ts", ".flv"}

_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}
_TWITCH_HOSTS = {"twitch.tv", "www.twitch.tv", "m.twitch.tv", "clips.twitch.tv"}
_YT_ONE_VIDEO_PREFIXES = ("shorts", "live", "embed", "v", "e", "clip")


class IngestaoError(Exception):
    pass


class PrecisaCookies(IngestaoError):
    """O YouTube pediu login ("confirme que você não é um robô"): só com os cookies de um navegador."""


class ErroCookies(IngestaoError):
    """Não deu para ler os cookies do navegador escolhido."""


# Começo fixo da mensagem: o app reconhece por ele e oferece escolher o navegador.
AVISO_ROBO = "O YouTube pediu para confirmar que você não é um robô."
NAVEGADORES = ("firefox", "edge", "chrome", "brave", "opera", "vivaldi", "chromium")
NOMES_NAVEGADOR = {"firefox": "Firefox", "edge": "Edge", "chrome": "Chrome", "brave": "Brave", "opera": "Opera",
                   "vivaldi": "Vivaldi", "chromium": "Chromium"}


def _pastas_perfil(nav: str) -> list[Path]:
    """Onde cada navegador guarda o perfil (é lá que o yt-dlp lê os cookies)."""
    casa = Path.home()
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", casa / "AppData" / "Local"))
        roam = Path(os.environ.get("APPDATA", casa / "AppData" / "Roaming"))
        return {
            "firefox": [roam / "Mozilla" / "Firefox" / "Profiles"],
            "edge": [local / "Microsoft" / "Edge" / "User Data"],
            "chrome": [local / "Google" / "Chrome" / "User Data"],
            "brave": [local / "BraveSoftware" / "Brave-Browser" / "User Data"],
            "opera": [roam / "Opera Software" / "Opera Stable"],
            "vivaldi": [local / "Vivaldi" / "User Data"],
            "chromium": [local / "Chromium" / "User Data"],
        }[nav]
    if sys.platform == "darwin":
        sup = casa / "Library" / "Application Support"
        return {
            "firefox": [sup / "Firefox" / "Profiles"], "edge": [sup / "Microsoft Edge"], "chrome": [sup / "Google" / "Chrome"],
            "brave": [sup / "BraveSoftware" / "Brave-Browser"], "opera": [sup / "com.operasoftware.Opera"],
            "vivaldi": [sup / "Vivaldi"], "chromium": [sup / "Chromium"],
        }[nav]
    cfg = casa / ".config"
    return {
        "firefox": [casa / ".mozilla" / "firefox", casa / "snap" / "firefox" / "common" / ".mozilla" / "firefox"],
        "edge": [cfg / "microsoft-edge"], "chrome": [cfg / "google-chrome"], "brave": [cfg / "BraveSoftware" / "Brave-Browser"],
        "opera": [cfg / "opera"], "vivaldi": [cfg / "vivaldi"], "chromium": [cfg / "chromium"],
    }[nav]


def navegadores_instalados() -> list[str]:
    return [n for n in NAVEGADORES if any(p.is_dir() for p in _pastas_perfil(n))]


def cookies_da_conta() -> Path | None:
    """O cookies.txt da conta do YouTube conectada no Clipator (perfil do navegador do Clipator, ver contayt).

    O conteúdo nunca é lido aqui: só o caminho vai para o yt-dlp.
    """
    from .contayt import arquivo_cookies

    p = arquivo_cookies()
    return p if p.is_file() and p.stat().st_size > 0 else None


def cadeia_de_tentativas(configurados: dict[str, Any] | None, cookies_primeiro: bool = False) -> list[tuple[str, dict[str, Any]]]:
    """Em que ordem tentar quando o YouTube pede login: sem cookies, a conta do YouTube conectada no
    Clipator, o que estiver nas Configurações e, por fim, o Firefox se estiver instalado."""
    configurados = configurados or {}
    if cookies_primeiro and configurados:
        return [("escolhido", configurados)]
    out: list[tuple[str, dict[str, Any]]] = [("sem cookies", {})]
    from . import contayt

    contayt.renovar()  # cookies com mais de algumas horas: regrava do perfil do Clipator, sem janela
    conta = cookies_da_conta()
    if conta:
        out.append(("conta do Clipator", {"cookiefile": str(conta)}))
    if configurados and configurados != {"cookiefile": str(conta)}:
        out.append(("Configurações", configurados))
    if configurados.get("cookiesfrombrowser", ("",))[0] != "firefox" and "firefox" in navegadores_instalados():
        out.append(("Firefox", {"cookiesfrombrowser": ("firefox",)}))
    return out


def opcoes_cookies(navegador: str | None = None, arquivo: str | None = None) -> dict[str, Any]:
    """Opções do yt-dlp para usar cookies. O conteúdo dos cookies nunca passa pelo Clipator."""
    if arquivo:
        p = Path(arquivo).expanduser()
        if not p.is_file():
            raise ErroCookies(f"Arquivo de cookies não encontrado: {p}")
        return {"cookiefile": str(p)}
    if navegador:
        if navegador not in NAVEGADORES:
            raise ErroCookies(f"Navegador desconhecido: {navegador}")
        return {"cookiesfrombrowser": (navegador,)}
    return {}


def _origem_cookies(opts: dict[str, Any]) -> str:
    if opts.get("cookiefile"):
        return "do arquivo cookies.txt"
    nav = (opts.get("cookiesfrombrowser") or ("",))[0]
    return f"do {NOMES_NAVEGADOR.get(nav, nav)}"


def _erro_do_download(msg: str, cookies: dict[str, Any]) -> IngestaoError:
    """Traduz os erros do yt-dlp que o usuário consegue resolver."""
    baixo = msg.lower()
    nav = NOMES_NAVEGADOR.get((cookies.get("cookiesfrombrowser") or ("",))[0], "navegador")
    if cookies.get("cookiesfrombrowser") and "could not copy" in baixo and "cookie" in baixo:
        return ErroCookies(f"Não consegui ler os cookies do {nav}: com ele aberto, o Windows trava o arquivo de cookies. "
                           "Conecte a conta do YouTube no Clipator (uma vez só) e o download segue sozinho.")
    if cookies.get("cookiesfrombrowser") and ("dpapi" in baixo or "app-bound" in baixo or "app bound" in baixo
                                               or "failed to decrypt" in baixo):
        return ErroCookies(f"Não consegui decifrar os cookies do {nav}: as versões novas do Chrome e do Edge no Windows "
                           "protegem os cookies e outros programas não conseguem ler. Conecte a conta do YouTube no "
                           "Clipator (uma vez só) e o download segue sozinho.")
    if "sign in to confirm" in baixo or "not a bot" in baixo:
        if cookies.get("cookiefile") and cookies_da_conta() and cookies["cookiefile"] == str(cookies_da_conta()):
            return PrecisaCookies(f"{AVISO_ROBO} A conta do YouTube conectada no Clipator expirou: conecte de novo "
                                  "(botão abaixo) e o download segue sozinho.")
        if cookies:
            return PrecisaCookies(f"{AVISO_ROBO} Mesmo com os cookies {_origem_cookies(cookies)} ele recusou. Conecte "
                                  "a conta do YouTube no Clipator (uma vez só) e o download segue sozinho.")
        return PrecisaCookies(f"{AVISO_ROBO} Conecte a conta do YouTube no Clipator (uma vez só) e o download segue sozinho.")
    return IngestaoError(f"Falha ao baixar: {msg}")


def eh_link(valor: str) -> bool:
    return valor.strip().lower().startswith(("http://", "https://"))


def plataforma(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host in _YT_HOSTS:
        return "youtube"
    if host in _TWITCH_HOSTS:
        return "twitch"
    return None


def validar_link(url: str) -> str:
    """Aceita só um vídeo do YouTube ou da Twitch (decisão 6). Devolve a plataforma."""
    plat = plataforma(url)
    if plat is None:
        raise IngestaoError("Por enquanto o Clipator aceita links do YouTube e da Twitch. Para outros sites, baixe o vídeo e faça upload.")
    parts = urlparse(url)
    if plat == "youtube":
        host = (parts.hostname or "").lower()
        segs = [s for s in parts.path.split("/") if s]
        if host.endswith("youtu.be"):
            if not segs:
                raise IngestaoError("Link do YouTube sem vídeo")
            return plat
        if segs[:1] == ["watch"]:
            if not parse_qs(parts.query).get("v"):
                raise IngestaoError("Link do YouTube sem o parâmetro v=")
            return plat
        if segs and segs[0] in _YT_ONE_VIDEO_PREFIXES and len(segs) >= 2:
            return plat
        raise IngestaoError("Esse link do YouTube não é de um vídeo (é playlist, canal ou busca). Abra o vídeo e cole o link dele.")
    if plat == "twitch":
        segs = [s for s in parts.path.split("/") if s]
        host = (parts.hostname or "").lower()
        if host == "clips.twitch.tv" or "videos" in segs or "clip" in segs:
            return plat
        raise IngestaoError("Cole o link de um VOD (twitch.tv/videos/...) ou de um clip da Twitch; lives em andamento não são suportadas.")
    return plat


def _opcoes_ytdlp(destino: Path, progresso: Progress | None, cancelar: threading.Event | None, extra: dict | None) -> dict[str, Any]:
    def hook(d: dict) -> None:
        if cancelar is not None and cancelar.is_set():
            raise Cancelado()
        if d.get("status") == "downloading" and progresso:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            if total:
                progresso(min(0.99, done / total), "baixando vídeo")

    opts: dict[str, Any] = {
        "outtmpl": str(destino / "video.%(ext)s"),
        "format": "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "writeinfojson": False,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
    }
    if extra:
        opts.update(extra)
    return opts


def _resumo_info(info: dict) -> dict:
    """Guarda só o que o Clipator usa: título, canal, capítulos e o mapa de mais repetidos."""
    return {
        "id": info.get("id"),
        "titulo": info.get("title"),
        "canal": info.get("channel") or info.get("uploader"),
        "duracao": info.get("duration"),
        "url": info.get("webpage_url"),
        "plataforma": info.get("extractor_key"),
        "data": info.get("upload_date"),
        "descricao": (info.get("description") or "")[:4000],
        "capitulos": [
            {"inicio": c.get("start_time"), "fim": c.get("end_time"), "titulo": c.get("title")}
            for c in (info.get("chapters") or [])
        ],
        "mais_repetidos": [
            {"inicio": h.get("start_time"), "fim": h.get("end_time"), "valor": h.get("value")}
            for h in (info.get("heatmap") or [])
        ],
        "idioma": info.get("language"),
    }


def baixar(
    url: str,
    projeto: ProjetoWS,
    progresso: Progress | None = None,
    cancelar: threading.Event | None = None,
    opcoes_extra: dict | None = None,
    cookies: dict | None = None,
    cookies_primeiro: bool = False,
    log: Callable[[str], None] | None = None,
) -> Path:
    """Baixa o vídeo. Se o YouTube pedir login, tenta de novo com `cookies` (opcoes_cookies), quando houver.

    `cookies_primeiro` usa os cookies já na primeira tentativa (o usuário escolheu o navegador agora).
    """
    validar_link(url)
    try:
        import yt_dlp  # noqa: F401 - só confere que está instalado
    except ImportError as exc:  # pragma: no cover
        raise IngestaoError("yt-dlp não está instalado") from exc

    # O yt-dlp junta vídeo e áudio com o FFmpeg; sem ele, o erro dele não diz o que fazer.
    if not media.ffmpeg_disponivel():
        raise IngestaoError(media.DICA_FFMPEG)
    destino = projeto.fonte_dir
    destino.mkdir(parents=True, exist_ok=True)
    # cadeia automática: segue para a próxima quando o YouTube pede login ou os cookies não dão para ler;
    # para no primeiro que baixar. O erro final é o mais útil (o da conta do Clipator, se houver).
    ultimo: IngestaoError | None = None
    for nome, extra in cadeia_de_tentativas(cookies, cookies_primeiro):
        if log and nome != "sem cookies":
            log(f"o YouTube pediu login; tentando de novo ({nome})")
        try:
            return _baixar_uma_vez(url, projeto, destino, progresso, cancelar, {**(opcoes_extra or {}), **extra}, extra)
        except (PrecisaCookies, ErroCookies) as exc:
            if nome == "conta do Clipator" and isinstance(exc, PrecisaCookies):
                # a conta pode só ter girado os cookies: regrava do perfil e tenta mais uma vez
                from . import contayt

                if contayt.renovar(forcar=True):
                    try:
                        return _baixar_uma_vez(url, projeto, destino, progresso, cancelar,
                                               {**(opcoes_extra or {}), **extra}, extra)
                    except (PrecisaCookies, ErroCookies) as exc2:
                        exc = exc2
            if ultimo is None or not isinstance(exc, ErroCookies) or isinstance(ultimo, ErroCookies):
                ultimo = exc
    assert ultimo is not None
    raise ultimo


def _baixar_uma_vez(url: str, projeto: ProjetoWS, destino: Path, progresso: Progress | None,
                    cancelar: threading.Event | None, extra: dict, cookies: dict) -> Path:
    import yt_dlp

    opts = _opcoes_ytdlp(destino, progresso, cancelar, extra)
    # Usa o mesmo FFmpeg do resto do motor (ffmpeg-full do Homebrew, CLIPATOR_FFMPEG, PATH do registro).
    opts.setdefault("ffmpeg_location", media.ffmpeg_bin())
    try:
        with yt_dlp.YoutubeDL({**opts, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            raise IngestaoError("Esse link é uma lista de vídeos; cole o link de um vídeo só.")
        if info.get("is_live"):
            raise IngestaoError("Essa live ainda está no ar. Espere terminar e use o link do VOD.")
        dur = float(info.get("duration") or 0)
        if dur > DURACAO_MAXIMA:
            raise IngestaoError(f"O vídeo tem {dur / 3600:.1f} h; o limite é 4 h.")
        write_json(projeto.metadados_path, _resumo_info(info))
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.process_ie_result(info, download=True)
    except Cancelado:
        raise
    except IngestaoError:
        raise
    except Exception as exc:
        raise _erro_do_download(str(exc), cookies) from exc

    video = projeto.video_path()
    if video is None:
        raise IngestaoError("O download terminou mas o arquivo de vídeo não apareceu em fonte/")
    return video


def importar_arquivo(arquivo: str | Path, projeto: ProjetoWS, mover: bool = False) -> Path:
    src = Path(arquivo).expanduser().resolve()
    if not src.exists():
        raise IngestaoError(f"Arquivo não encontrado: {src}")
    if src.suffix.lower() not in EXTENSOES_VIDEO:
        raise IngestaoError(f"Formato não suportado: {src.suffix}. Use {', '.join(sorted(EXTENSOES_VIDEO))}.")
    info = media.probe(src)
    if not info.tem_video:
        raise IngestaoError("O arquivo não tem vídeo")
    if info.duracao > DURACAO_MAXIMA:
        raise IngestaoError(f"O vídeo tem {info.duracao / 3600:.1f} h; o limite é 4 h.")
    projeto.fonte_dir.mkdir(parents=True, exist_ok=True)
    dest = projeto.fonte_dir / f"video{src.suffix.lower()}"
    if dest.exists():
        dest.unlink()
    if mover:
        shutil.move(str(src), dest)
    else:
        try:
            os.link(src, dest)  # hard link: instantâneo e sem ocupar espaço extra
        except OSError:
            shutil.copy2(src, dest)
    write_json(projeto.metadados_path, {"titulo": src.stem, "arquivo_original": str(src), "duracao": info.duracao,
                                        "capitulos": [], "mais_repetidos": []})
    return dest
