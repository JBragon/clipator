"""Conta do YouTube do Clipator: um perfil do Chrome (ou do Edge) só do Clipator.

O Google não deixa entrar na conta dentro de apps embutidos nem num navegador com a porta de
depuração aberta, e o Windows protege os cookies do Chrome e do Edge do dia a dia. Então:

1. o login acontece no navegador instalado, de verdade e sem depuração nenhuma, com um perfil próprio
   (`~/.clipator/navegador-youtube`): o usuário entra e fecha a janela (ou clica em "Já entrei");
2. depois, o mesmo perfil abre sem janela, numa página em branco, com a porta de depuração em
   127.0.0.1 (porta aleatória), só para ler os cookies do YouTube e do Google e gravar o cookies.txt
   que o yt-dlp usa (`ingest.cookies_da_conta`). Antes de um download, se o arquivo estiver velho,
   o mesmo passo 2 se repete.

Nada de disfarce: sem trocar o navegador, sem flags de automação. Os valores dos cookies só vão para
o arquivo, nunca para log ou tela.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

DOMINIOS = ("youtube.com", "google.com")
DE_LOGIN = ("LOGIN_INFO", "SAPISID", "__Secure-3PAPISID")
IDADE_MAX = 6 * 3600  # depois disso, renova antes de baixar


class ErroConta(Exception):
    pass


def pasta_perfil() -> Path:
    return Path(os.environ.get("CLIPATOR_YT_PERFIL") or (Path.home() / ".clipator" / "navegador-youtube"))


def arquivo_cookies() -> Path:
    return Path(os.environ.get("CLIPATOR_YT_COOKIES") or (Path.home() / ".clipator" / "youtube-cookies.txt"))


def navegador() -> tuple[str, Path] | None:
    """(nome, executável) do Chrome instalado; o Edge se não houver Chrome."""
    if os.environ.get("CLIPATOR_YT_NAVEGADOR"):
        p = Path(os.environ["CLIPATOR_YT_NAVEGADOR"])
        return ("Navegador", p) if p.exists() else None
    if sys.platform == "win32":
        pf, pf86, local = (os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"))
        candidatos = [("Chrome", Path(b) / "Google" / "Chrome" / "Application" / "chrome.exe") for b in (pf, pf86, local) if b]
        candidatos += [("Edge", Path(b) / "Microsoft" / "Edge" / "Application" / "msedge.exe") for b in (pf86, pf) if b]
    elif sys.platform == "darwin":
        candidatos = [("Chrome", Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")),
                      ("Edge", Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"))]
    else:
        candidatos = [(n, Path(p)) for n, c in (("Chrome", "google-chrome"), ("Chrome", "chromium"), ("Edge", "microsoft-edge"))
                      if (p := shutil.which(c))]
    return next(((n, p) for n, p in candidatos if p.exists()), None)


def para_netscape(cookies: list[dict[str, Any]]) -> str:
    """Cookies do protocolo de depuração (Storage.getCookies) no formato Netscape do yt-dlp."""
    linhas = ["# Netscape HTTP Cookie File", "# Gerado pelo Clipator a partir da conta do YouTube conectada nele. Não compartilhe.", ""]
    for c in cookies:
        dom = str(c.get("domain") or "")
        sub = "TRUE" if dom.startswith(".") else "FALSE"
        expira = int(c["expires"]) if c.get("expires") and float(c["expires"]) > 0 else 0
        linhas.append("\t".join([dom, sub, str(c.get("path") or "/"), "TRUE" if c.get("secure") else "FALSE",
                                 str(expira), str(c.get("name") or ""), str(c.get("value") or "")]))
    return "\n".join(linhas) + "\n"


def _do_youtube(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cookies if str(c.get("domain") or "").lstrip(".").endswith(DOMINIOS)]


def tem_login(cookies: list[dict[str, Any]]) -> bool:
    return any(c.get("name") in DE_LOGIN and "youtube.com" in str(c.get("domain")) for c in cookies)


def gravar(cookies: list[dict[str, Any]], destino: Path | None = None) -> bool:
    """Grava o cookies.txt só se a conta estiver conectada (só o dono lê, quando o sistema permite)."""
    yt = _do_youtube(cookies)
    if not tem_login(yt):
        return False
    destino = destino or arquivo_cookies()
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(para_netscape(yt))
    tmp.replace(destino)
    return True


# ---- o navegador e o protocolo de depuração -----------------------------------------------
def _abrir(exe: Path, perfil: Path, sem_janela: bool, url: str = "about:blank") -> tuple[subprocess.Popen, str]:
    perfil.mkdir(parents=True, exist_ok=True)
    porta_arq = perfil / "DevToolsActivePort"
    porta_arq.unlink(missing_ok=True)
    args = [str(exe), f"--user-data-dir={perfil}", "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
            "--no-first-run", "--no-default-browser-check"]
    if sem_janela:
        args.append("--headless=new")
    proc = subprocess.Popen([*args, url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    for _ in range(150):
        if porta_arq.exists():
            partes = porta_arq.read_text(encoding="utf-8", errors="replace").split()
            if len(partes) >= 2:
                return proc, f"ws://127.0.0.1:{int(partes[0])}{partes[1]}"
        if proc.poll() is not None and not porta_arq.exists():
            break
        time.sleep(0.2)
    _matar(proc)
    raise ErroConta("O navegador não abriu a conexão local (talvez o perfil do Clipator já esteja aberto noutra janela).")


def _matar(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()


async def _chamar(ws_url: str, metodos: list[tuple[str, dict]]) -> list[dict]:
    import websockets

    out = []
    async with websockets.connect(ws_url, max_size=50_000_000, open_timeout=10) as ws:
        for n, (metodo, params) in enumerate(metodos, 1):
            await ws.send(json.dumps({"id": n, "method": metodo, "params": params}))
            while True:
                r = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if r.get("id") == n:
                    out.append(r.get("result") or {})
                    break
    return out


def ler_cookies(ws_url: str) -> list[dict[str, Any]]:
    return asyncio.run(_chamar(ws_url, [("Storage.getCookies", {})]))[0].get("cookies") or []


def fechar(ws_url: str, proc: subprocess.Popen) -> None:
    try:
        asyncio.run(_chamar(ws_url, [("Browser.close", {})]))
    except Exception:  # noqa: BLE001 - fechou antes de responder
        pass
    try:
        proc.wait(timeout=8)
    except Exception:  # noqa: BLE001
        _matar(proc)


# ---- o que o resto do Clipator usa ---------------------------------------------------------
def estado() -> dict[str, Any]:
    arq = arquivo_cookies()
    nav = navegador()
    return {"conectada": arq.is_file() and arq.stat().st_size > 0, "navegador": nav[0] if nav else None,
            "atualizada_em": arq.stat().st_mtime if arq.is_file() else None}


URL_LOGIN = "https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F"
continuar = threading.Event()  # "Já entrei, continuar" na tela


def _ambiente_limpo() -> dict[str, str]:
    """O ambiente do usuário sem o que o Electron, o Python ou um navegador de teste põem."""
    fora = ("ELECTRON_", "CHROME_", "PYTHON", "CLIPATOR_", "NODE_", "VIRTUAL_ENV", "UV_")
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(fora)}


def processos_do_perfil(perfil: Path) -> list[int]:
    """PIDs dos processos principais do navegador que estão usando o perfil do Clipator."""
    alvo = str(perfil).lower().rstrip("\\/")
    try:
        if sys.platform == "win32":
            cmd = ["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -ne $null } | "
                   "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"]
        else:
            cmd = ["ps", "-eo", "pid=,args="]
        saida = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=30).stdout  # noqa: S603
    except Exception:  # noqa: BLE001
        return []
    pids = []
    for linha in saida.splitlines():
        pid, _, args = linha.strip().replace("\t", " ", 1).partition(" ")
        baixo = args.lower()
        if f"--user-data-dir={alvo}" in baixo.replace('"', "") and "--type=" not in baixo and pid.isdigit():
            pids.append(int(pid))
    return pids


def fechar_perfil(perfil: Path) -> None:
    """Fecha o navegador que estiver aberto com o perfil do Clipator (senão o novo vira só uma aba dele)."""
    for pid in processos_do_perfil(perfil):
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)  # noqa: S603,S607
        else:
            subprocess.run(["kill", str(pid)], capture_output=True)  # noqa: S603,S607
    for _ in range(20):
        if not processos_do_perfil(perfil):
            return
        time.sleep(0.5)
    for pid in processos_do_perfil(perfil):
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)  # noqa: S603,S607
        else:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True)  # noqa: S603,S607


def _abrir_para_login(exe: Path, perfil: Path) -> subprocess.Popen:
    """O navegador como qualquer pessoa abriria: só o perfil do Clipator, sem depuração nem outras flags,
    fora da árvore de processos do app e com o ambiente limpo."""
    perfil.mkdir(parents=True, exist_ok=True)
    args = [str(exe), f"--user-data-dir={perfil}", "--no-first-run", URL_LOGIN]
    kw: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                          "env": _ambiente_limpo(), "close_fds": True}
    if sys.platform == "win32":
        destacado = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            return subprocess.Popen(args, creationflags=destacado | 0x01000000, **kw)  # noqa: S603 - + CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            return subprocess.Popen(args, creationflags=destacado, **kw)  # noqa: S603
    return subprocess.Popen(args, start_new_session=True, **kw)  # noqa: S603


def _fechar_janela(proc: subprocess.Popen) -> None:
    """Fecha como o usuário fecharia (o navegador grava os cookies no disco ao sair)."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True)  # noqa: S603,S607 - sem /F
    else:
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except Exception:  # noqa: BLE001
        _matar(proc)


def exportar(abrir: Callable[..., tuple[Any, str]] = _abrir, ler: Callable[[str], list[dict]] = ler_cookies) -> bool:
    """Abre o perfil sem janela, numa página em branco, lê os cookies, grava se a conta estiver conectada e fecha."""
    nav = navegador()
    if nav is None:
        return False
    proc, ws = abrir(nav[1], pasta_perfil(), True)
    try:
        return gravar(ler(ws))
    finally:
        fechar(ws, proc)


def entrar(progresso: Callable[[float, str], None] | None = None, cancelar: threading.Event | None = None,
           limite_s: float = 900, abrir_login: Callable[..., Any] = _abrir_para_login,
           exportar_: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Abre o navegador do Clipator no login do YouTube e espera o usuário entrar e fechar a janela
    (ou clicar em "Já entrei, continuar"); depois lê os cookies sem janela."""
    nav = navegador()
    if nav is None:
        raise ErroConta("Não achei o Chrome nem o Edge neste computador.")
    continuar.clear()
    # um navegador já aberto com o perfil (de uma tentativa anterior) receberia o login como aba nova
    fechar_perfil(pasta_perfil())
    if not estado()["conectada"]:
        shutil.rmtree(pasta_perfil(), ignore_errors=True)  # sem conta ainda: perfil novo, limpo
    proc = abrir_login(nav[1], pasta_perfil())
    inicio = time.monotonic()
    while proc.poll() is None:
        if cancelar is not None and cancelar.is_set():
            _fechar_janela(proc)
            return {"conectada": False, "cancelado": True}
        if continuar.is_set():
            _fechar_janela(proc)
            break
        if time.monotonic() - inicio > limite_s:
            _fechar_janela(proc)
            break
        if progresso:
            progresso(min(0.9, (time.monotonic() - inicio) / limite_s),
                      f"entre na sua conta na janela do {nav[0]} e feche a janela (ou clique em Já entrei)")
        time.sleep(1)
    time.sleep(1)  # o navegador termina de gravar o perfil
    if progresso:
        progresso(0.95, "lendo a conta conectada")
    try:
        ok = (exportar_ or exportar)()
    except ErroConta as exc:
        return {"conectada": False, "motivo": str(exc)}
    if ok:
        return {"conectada": True, "navegador": nav[0]}
    return {"conectada": False, "motivo": f"Não vi a conta conectada no {nav[0]} do Clipator: o login não terminou. "
                                          "Tente de novo e entre até aparecer o YouTube."}


def renovar(forcar: bool = False, abrir: Callable[..., tuple[Any, str]] = _abrir,
            ler: Callable[[str], list[dict]] = ler_cookies) -> bool:
    """Regrava o cookies.txt a partir do perfil do Clipator, sem janela. False se não deu (sem conta, perfil aberto…)."""
    arq = arquivo_cookies()
    if not pasta_perfil().is_dir():
        return False
    if not forcar and arq.is_file() and time.time() - arq.stat().st_mtime < IDADE_MAX:
        return True
    nav = navegador()
    if nav is None:
        return False
    if processos_do_perfil(pasta_perfil()):
        return False  # a janela do perfil está aberta (o usuário entrando): não mexe
    try:
        return exportar(abrir, ler)
    except Exception:  # noqa: BLE001 - perfil aberto noutra janela, navegador fechou…
        return False


# ---- último recurso: o Firefox (os cookies dele outros programas conseguem ler) ---------------
def firefox() -> Path | None:
    if sys.platform == "win32":
        bases = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("LOCALAPPDATA", "")]
        cand = [Path(b) / "Mozilla Firefox" / "firefox.exe" for b in bases if b]
    elif sys.platform == "darwin":
        cand = [Path("/Applications/Firefox.app/Contents/MacOS/firefox")]
    else:
        cand = [Path(p) for p in [shutil.which("firefox") or ""] if p]
    return next((p for p in cand if p.exists()), None)


def instalar_firefox(progresso: Callable[[float, str], None] | None = None) -> Path:
    """Instala o Firefox pelo winget (Windows). Só roda quando o usuário clica em "Usar o Firefox"."""
    if firefox():
        return firefox()  # type: ignore[return-value]
    if sys.platform != "win32" or not shutil.which("winget"):
        raise ErroConta("Instale o Firefox pelo site oficial (firefox.com) e tente de novo.")
    if progresso:
        progresso(0.1, "instalando o Firefox pelo winget (pode levar alguns minutos)")
    r = subprocess.run(["winget", "install", "--id", "Mozilla.Firefox", "-e", "--silent",  # noqa: S603,S607
                        "--accept-package-agreements", "--accept-source-agreements"],
                       capture_output=True, text=True, errors="replace", timeout=900)
    p = firefox()
    if p is None:
        raise ErroConta(f"O winget não conseguiu instalar o Firefox: {(r.stdout or r.stderr).strip()[-300:]}")
    return p


def usar_firefox(progresso: Callable[[float, str], None] | None = None, cancelar: threading.Event | None = None,
                 limite_s: float = 900) -> dict[str, Any]:
    """Instala o Firefox se faltar e abre o YouTube nele para o usuário entrar uma vez."""
    exe = instalar_firefox(progresso)
    continuar.clear()
    proc = subprocess.Popen([str(exe), "https://www.youtube.com/"], stdin=subprocess.DEVNULL,  # noqa: S603
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    inicio = time.monotonic()
    while proc.poll() is None and not continuar.is_set() and time.monotonic() - inicio < limite_s:
        if cancelar is not None and cancelar.is_set():
            return {"firefox": True, "cancelado": True}
        if progresso:
            progresso(0.5, "entre na sua conta do YouTube no Firefox e clique em Já entrei")
        time.sleep(1)
    return {"firefox": True}


def desconectar() -> None:
    arquivo_cookies().unlink(missing_ok=True)
    shutil.rmtree(pasta_perfil(), ignore_errors=True)
