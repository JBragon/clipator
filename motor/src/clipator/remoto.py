"""Modo remoto: uma página leve para o celular, servida pelo próprio motor numa segunda porta.

Todo o processamento continua no PC. O celular só mostra a interface: acompanha os jobs, aprova
cortes, cola o link de um vídeo novo e assiste ou baixa o clip pronto.

Segurança, de fora para dentro:
- Desligado por padrão. Só liga pelo app do PC (API local em 127.0.0.1).
- A porta remota só atende endereços da rede de casa ou do Tailscale (IPs privados, 100.64.0.0/10 e
  fd7a:115c:a1e0::/48). Quem abrir a porta no roteador continua barrado.
- Cada celular entra uma vez com um código de pareamento de uso único, que vale 10 minutos e é
  mostrado em QR code no app do PC. Ele vira um cookie HttpOnly e SameSite=Strict; o motor guarda
  só o hash. Dá para tirar o acesso de cada aparelho no app do PC.
- A API remota é outra, bem menor que a do app: não lê nem grava arquivos, não muda configuração
  e não apaga nada. Pedidos que mudam algo exigem o cabeçalho x-clipator, que outro site não
  consegue mandar sem a permissão de CORS que esta API nunca dá.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PORTA_PADRAO = 8766
VALIDADE_CODIGO = 10 * 60  # segundos
TENTATIVAS_MAX = 8  # erros de código antes de invalidar o código atual
COOKIE = "clipator_aparelho"
WEB_DIR = Path(__file__).with_name("remoto_web")

_CGNAT = ipaddress.ip_network("100.64.0.0/10")  # Tailscale usa essa faixa no IPv4
_TAILSCALE_V6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def endereco_permitido(host: str | None) -> bool:
    """Só a rede de casa, o próprio PC e o Tailscale. Um IP público (porta aberta no roteador) fica de fora."""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_loopback or ip.is_link_local:
        return True
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in _CGNAT or ip.is_private and not ip.is_unspecified and not ip.is_reserved
    return ip in _TAILSCALE_V6 or ip in ipaddress.ip_network("fc00::/7")


def eh_tailscale(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a in _CGNAT if isinstance(a, ipaddress.IPv4Address) else a in _TAILSCALE_V6


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _agora() -> float:
    return time.time()


# ---- endereços do PC ----------------------------------------------------------------------------
def _ip_da_rede() -> str | None:
    """O IP do PC na rede de casa. O UDP connect não manda pacote nenhum, só escolhe a interface."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") or eh_tailscale(ip) else ip


def _comando_tailscale() -> str | None:
    achado = shutil.which("tailscale")
    if achado:
        return achado
    for p in (r"C:\Program Files\Tailscale\tailscale.exe", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if os.path.exists(p):
            return p
    return None


def info_tailscale() -> dict[str, Any]:
    """IP e nome do PC no Tailscale, se ele estiver instalado e conectado. Nada aqui usa internet."""
    out: dict[str, Any] = {"instalado": False, "ip": None, "nome": None}
    cmd = _comando_tailscale()
    if cmd:
        out["instalado"] = True
        try:
            r = subprocess.run([cmd, "status", "--json"], capture_output=True, text=True, timeout=4,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            st = json.loads(r.stdout or "{}")
            eu = st.get("Self") or {}
            ips = [i for i in eu.get("TailscaleIPs") or [] if ":" not in i]
            out["ip"] = ips[0] if ips else None
            out["nome"] = (eu.get("DNSName") or "").rstrip(".") or None
            if st.get("BackendState") not in (None, "Running"):
                out["ip"] = None  # instalado mas desconectado
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    if not out["ip"]:  # sem a CLI: procura um IP da faixa do Tailscale nas interfaces
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = str(info[4][0])
                if eh_tailscale(ip):
                    out["ip"] = ip
                    break
        except OSError:
            pass
    return out


def enderecos(porta: int, ts: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Os endereços que o celular pode abrir. O do Tailscale vem primeiro: ele funciona em casa e na rua."""
    ts = ts if ts is not None else info_tailscale()
    out = []
    if ts.get("ip"):
        out.append({"tipo": "tailscale", "url": f"http://{ts['ip']}:{porta}"})
    lan = _ip_da_rede()
    if lan:
        out.append({"tipo": "wifi", "url": f"http://{lan}:{porta}"})
    return out


def qr_svg(texto: str) -> str:
    """QR code em SVG, como data URI para um <img> (segno, BSD-3). Escuro sobre branco, que todo leitor entende."""
    import segno

    return segno.make(texto, error="m").svg_data_uri(scale=6, border=2, dark="#111", light="#fff")


# ---- aparelhos e pareamento ---------------------------------------------------------------------
@dataclass
class _Codigo:
    valor: str
    expira: float
    erros: int = 0


@dataclass
class Remoto:
    """Estado do modo remoto. Fica em .clipator/remoto.json (só hashes, nunca o token)."""

    arquivo: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _codigo: _Codigo | None = field(default=None, repr=False)
    _servidor: Any = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    erro: str | None = None
    host: str = "0.0.0.0"  # todas as interfaces: Wi-Fi e Tailscale; o filtro de endereço barra o resto

    # -- arquivo
    def _ler(self) -> dict[str, Any]:
        try:
            d = json.loads(self.arquivo.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gravar(self, d: dict[str, Any]) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.arquivo)

    @property
    def porta(self) -> int:
        return int(self._ler().get("porta") or PORTA_PADRAO)

    @property
    def quer_ligado(self) -> bool:
        return bool(self._ler().get("ligado"))

    @property
    def ligado(self) -> bool:
        return self._servidor is not None and self._thread is not None and self._thread.is_alive()

    def aparelhos(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in a.items() if k != "hash"} for a in self._ler().get("aparelhos", [])]

    # -- pareamento
    def novo_codigo(self) -> tuple[str, float]:
        """Um código de uso único. Pedir outro invalida o anterior."""
        with self._lock:
            self._codigo = _Codigo(secrets.token_urlsafe(9), _agora() + VALIDADE_CODIGO)
            return self._codigo.valor, self._codigo.expira

    def parear(self, codigo: str, nome: str = "") -> tuple[str, dict[str, Any]] | None:
        """Troca o código por um token de aparelho. Devolve None se o código não vale."""
        with self._lock:
            c = self._codigo
            if c is None or _agora() > c.expira:
                self._codigo = None
                return None
            if not secrets.compare_digest(codigo.strip(), c.valor):
                c.erros += 1
                if c.erros >= TENTATIVAS_MAX:
                    self._codigo = None
                return None
            self._codigo = None
            token = secrets.token_urlsafe(32)
            ap = {"id": secrets.token_hex(4), "nome": (nome or "Celular").strip()[:60] or "Celular",
                  "criado_em": int(_agora()), "ultimo_acesso": int(_agora()), "hash": _hash(token)}
            d = self._ler()
            d.setdefault("aparelhos", []).append(ap)
            self._gravar(d)
            return token, {k: v for k, v in ap.items() if k != "hash"}

    def validar(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        h = _hash(token)
        with self._lock:
            d = self._ler()
            for a in d.get("aparelhos", []):
                if secrets.compare_digest(a.get("hash", ""), h):
                    if _agora() - a.get("ultimo_acesso", 0) > 60:  # não grava o arquivo a cada pedido
                        a["ultimo_acesso"] = int(_agora())
                        self._gravar(d)
                    return {k: v for k, v in a.items() if k != "hash"}
        return None

    def remover(self, aid: str) -> bool:
        with self._lock:
            d = self._ler()
            antes = len(d.get("aparelhos", []))
            d["aparelhos"] = [a for a in d.get("aparelhos", []) if a.get("id") != aid]
            self._gravar(d)
            return len(d["aparelhos"]) < antes

    # -- servidor
    def ligar(self, app_remoto: Any, porta: int | None = None) -> None:
        """Sobe o servidor da página do celular numa thread. Lembra que ficou ligado para a próxima vez."""
        import uvicorn

        self.desligar(lembrar=False)
        porta = int(porta or self.porta)
        self.erro = None
        cfg = uvicorn.Config(app_remoto, host=self.host, port=porta, log_level="warning", access_log=False)
        srv = uvicorn.Server(cfg)
        pronto = threading.Event()

        def rodar() -> None:
            try:
                srv.run()
            except BaseException as exc:  # porta ocupada vira SystemExit no uvicorn
                self.erro = f"Não deu para abrir a porta {porta}: {exc}"
            finally:
                pronto.set()

        t = threading.Thread(target=rodar, daemon=True, name="clipator-remoto")
        t.start()
        fim = _agora() + 5
        while _agora() < fim and not srv.started and t.is_alive():
            time.sleep(0.05)
        if not srv.started:
            srv.should_exit = True
            self.erro = self.erro or f"Não deu para abrir a porta {porta}. Outro programa pode estar usando."
            raise OSError(self.erro)
        self._servidor, self._thread = srv, t
        d = self._ler()
        d.update({"ligado": True, "porta": porta})
        self._gravar(d)

    def desligar(self, lembrar: bool = True) -> None:
        srv, t = self._servidor, self._thread
        self._servidor = self._thread = None
        with self._lock:
            self._codigo = None
        if srv is not None:
            srv.should_exit = True
            if t is not None:
                t.join(timeout=5)
        if lembrar:
            d = self._ler()
            d["ligado"] = False
            self._gravar(d)

    def estado(self, com_enderecos: bool = True) -> dict[str, Any]:
        ts = info_tailscale() if com_enderecos else {}
        return {"ligado": self.ligado, "porta": self.porta, "erro": self.erro, "aparelhos": self.aparelhos(),
                "tailscale": ts, "enderecos": enderecos(self.porta, ts) if com_enderecos and self.ligado else []}
