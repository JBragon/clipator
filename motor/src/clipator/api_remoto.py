"""API e página do modo remoto (celular). Ver remoto.py para as regras de segurança.

É uma API à parte da do app: tudo aqui fica em /m/api e só existe o que o celular precisa.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import __version__, gerenciar, ingest, pipeline
from .remoto import COOKIE, WEB_DIR, Remoto, endereco_permitido
from .service import Servico
from .workspace import WorkspaceError

ATIVOS = ("na_fila", "rodando")
TIPOS_WEB = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
             ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
             ".webmanifest": "application/manifest+json"}


class Pareamento(BaseModel):
    codigo: str
    nome: str = ""


class NovoVideo(BaseModel):
    link: str
    titulo: str | None = None


class Aprovacao(BaseModel):
    ids: list[str]
    estilo: str | None = None


def resumo_job(j: dict) -> dict:
    p = j.get("params") or {}
    return {k: j.get(k) for k in ("id", "tipo", "status", "progresso", "mensagem", "erro", "etapa", "aguardando",
                                  "criado", "iniciado", "terminado")} | {"canal": p.get("canal"),
                                                                          "projeto": p.get("projeto")}


def criar_app_remoto(srv: Servico, remoto: Remoto) -> FastAPI:
    ws = srv.ws
    app = FastAPI(title="Clipator remoto", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def so_rede_de_casa(request: Request, call_next):
        host = request.client.host if request.client else None
        if not endereco_permitido(host):
            return JSONResponse({"detail": "O modo remoto só atende aparelhos da sua rede de casa ou do Tailscale."},
                                status_code=403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    def aparelho(request: Request) -> dict[str, Any]:
        ap = remoto.validar(request.cookies.get(COOKIE))
        if ap is None:
            raise HTTPException(401, "Este celular não está pareado. Leia o QR code no app do PC.")
        # pedidos que mudam algo precisam do cabeçalho: outro site não consegue mandá-lo (sem CORS aqui)
        if request.method not in ("GET", "HEAD") and request.headers.get("x-clipator") != "1":
            raise HTTPException(403, "Pedido recusado.")
        return ap

    dep = [Depends(aparelho)]

    def proj(canal: str, projeto: str):
        try:
            return srv.projeto(canal, projeto)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc

    # ---- página -----------------------------------------------------------------------------
    def estatico(nome: str) -> FileResponse:
        p = WEB_DIR / nome
        if not p.is_file():
            raise HTTPException(404, "Não encontrado")
        return FileResponse(p, media_type=TIPOS_WEB.get(p.suffix, "application/octet-stream"),
                            headers={"Cache-Control": "no-cache"})

    @app.get("/")
    def inicio() -> FileResponse:
        r = estatico("index.html")
        r.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; media-src 'self'; "
                                                "style-src 'self'; script-src 'self'; connect-src 'self'; "
                                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return r

    @app.get("/{nome}")
    def arquivo_web(nome: str) -> FileResponse:
        if nome not in {p.name for p in WEB_DIR.iterdir() if p.suffix in TIPOS_WEB and p.name != "index.html"}:
            raise HTTPException(404, "Não encontrado")
        return estatico(nome)

    # ---- pareamento -------------------------------------------------------------------------
    @app.post("/m/api/parear")
    def parear(dados: Pareamento, request: Request, response: Response) -> dict:
        if request.headers.get("x-clipator") != "1":
            raise HTTPException(403, "Pedido recusado.")
        r = remoto.parear(dados.codigo, dados.nome)
        if r is None:
            raise HTTPException(401, "Código inválido ou vencido. Gere outro no app do PC.")
        token, ap = r
        response.set_cookie(COOKIE, token, max_age=400 * 24 * 3600, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https", path="/")
        return {"aparelho": ap}

    @app.post("/m/api/sair", dependencies=dep)
    def sair(response: Response, ap: dict = Depends(aparelho)) -> dict:
        remoto.remover(ap["id"])
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # ---- leitura ----------------------------------------------------------------------------
    @app.get("/m/api/estado", dependencies=dep)
    def estado(ap: dict = Depends(aparelho)) -> dict:
        jobs = srv.fila.listar(30)
        return {"versao": __version__, "pc": socket.gethostname(), "aparelho": ap,
                "idioma": ws.config().idioma_interface,
                "ativos": [resumo_job(j) for j in jobs if j.get("status") in ATIVOS],
                "recentes": [resumo_job(j) for j in jobs if j.get("status") not in ATIVOS][:10]}

    @app.get("/m/api/canais", dependencies=dep)
    def canais() -> list[dict]:
        out = []
        for c in ws.canais():
            info, _ = c.info()
            out.append({"slug": c.slug, "nome": info.nome, "projetos": len(c.projetos()),
                        "estilo_padrao": info.estilo_padrao})
        return out

    @app.get("/m/api/canais/{canal}/projetos", dependencies=dep)
    def projetos(canal: str) -> list[dict]:
        try:
            c = ws.canal(canal)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc
        out = []
        for p in c.projetos():
            st = gerenciar.status_projeto(p)
            out.append({"id": p.id, "titulo": p.meta().titulo, "criado_em": p.meta().criado_em, "fase": st["fase"],
                        "cortes": st["cortes"], "clips": st["clips"]})
        out.sort(key=lambda x: x["criado_em"] or "", reverse=True)
        return out

    @app.get("/m/api/canais/{canal}/estilos", dependencies=dep)
    def estilos(canal: str) -> list[dict]:
        try:
            c = ws.canal(canal)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc
        padrao = c.info()[0].estilo_padrao
        visiveis = ws.estilos(c)
        out = []
        for nome in visiveis:
            try:
                est, _, _ = ws.carregar_estilo(nome, c, estilos=visiveis)
            except Exception:
                continue
            out.append({"id": nome, "nome": est.nome or nome, "padrao": nome == padrao})
        return out

    @app.get("/m/api/canais/{canal}/projetos/{projeto}", dependencies=dep)
    def projeto(canal: str, projeto: str) -> dict:
        p = proj(canal, projeto)
        m = p.meta()
        clips = p.clips()
        por_cand = {c.candidato: c.id for c, _ in clips if c.candidato}
        cands = [{"id": c["id"], "inicio": c["inicio"], "fim": c["fim"], "duracao": c.get("duracao"),
                  "nota": c.get("nota"), "modo": c.get("modo", "curto"), "titulo": (c.get("titulos") or [""])[0],
                  "texto": (c.get("texto") or "")[:280], "motivo": (c.get("ia") or {}).get("motivo", ""),
                  "clip": por_cand.get(c["id"])} for c in p.candidatos()]
        return {"id": p.id, "titulo": m.titulo, "fase": gerenciar.status_projeto(p)["fase"],
                "etapas": {k: v.status for k, v in m.etapas.items()}, "candidatos": cands,
                "clips": [{"id": c.id, "titulo": c.titulo, "status": c.status, "formato": c.formato,
                           "estilo": c.estilo, "duracao": round(c.fim - c.inicio, 1),
                           "saida": (d / "saida.mp4").exists(), "preview": (d / "preview.mp4").exists()}
                          for c, d in clips]}

    @app.get("/m/api/canais/{canal}/projetos/{projeto}/candidatos/{cid}/quadro", dependencies=dep)
    def quadro(canal: str, projeto: str, cid: str) -> FileResponse:
        """O quadro do meio do corte, para o cartão no celular (o mesmo cache do app)."""
        p = proj(canal, projeto)
        try:
            qs = pipeline.quadros_candidato(p, cid, largura=240)
        except (KeyError, FileNotFoundError, OSError, RuntimeError):
            raise HTTPException(404, "Sem imagem") from None
        img = Path(qs[len(qs) // 2]["imagem"]) if qs else None
        if not img or not img.is_file():
            raise HTTPException(404, "Sem imagem")
        return FileResponse(img, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})

    @app.get("/m/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/video", dependencies=dep)
    def video(canal: str, projeto: str, clip_id: str, baixar: bool = False) -> FileResponse:
        p = proj(canal, projeto)
        try:
            clip, pasta = p.clip(clip_id)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc
        arq = next((pasta / n for n in ("saida.mp4", "preview.mp4") if (pasta / n).is_file()), None)
        if arq is None:
            raise HTTPException(404, "Este clip ainda não tem vídeo.")
        nome = f"{clip_id}.mp4"
        return FileResponse(arq, media_type="video/mp4", filename=nome if baixar else None,
                            content_disposition_type="attachment" if baixar else "inline")

    @app.get("/m/api/jobs", dependencies=dep)
    def jobs() -> list[dict]:
        return [resumo_job(j) for j in srv.fila.listar(30)]

    # ---- ações ------------------------------------------------------------------------------
    @app.post("/m/api/canais/{canal}/projetos", dependencies=dep)
    def novo_video(canal: str, dados: NovoVideo) -> dict:
        """Só por link: o celular não escolhe arquivos do PC."""
        link = dados.link.strip()
        if not ingest.eh_link(link):
            raise HTTPException(400, "Cole o link de um vídeo do YouTube ou da Twitch.")
        try:
            c = ws.canal(canal)
            p = pipeline.criar_projeto(ws, c, link, (dados.titulo or "").strip()[:120] or None)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        job = srv.fila.enviar("analisar", {"canal": canal, "projeto": p.id, "modo_ia": None, "corte_longo": True})
        return {"id": p.id, "job": job}

    @app.post("/m/api/canais/{canal}/projetos/{projeto}/aprovar", dependencies=dep)
    def aprovar(canal: str, projeto: str, dados: Aprovacao) -> dict:
        """Os cortes aprovados viram clips com o estilo escolhido (ou o do canal) e já vão para a fila."""
        if not dados.ids:
            raise HTTPException(400, "Escolha pelo menos um corte.")
        p = proj(canal, projeto)
        try:
            clips = pipeline.selecionar(p, dados.ids, None, dados.estilo or None, None)
        except Exception as exc:
            raise HTTPException(400 if not isinstance(exc, KeyError) else 404, str(exc)) from exc
        job = srv.fila.enviar("renderizar", {"canal": canal, "projeto": projeto, "clips": [c.id for c in clips],
                                             "preview": False})
        return {"clips": [c.id for c in clips], "job": job}

    @app.post("/m/api/jobs/{jid}/cancelar", dependencies=dep)
    def cancelar(jid: str) -> dict:
        return {"ok": srv.fila.cancelar(jid)}

    return app
