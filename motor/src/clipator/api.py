"""API HTTP local (FastAPI) + WebSocket de eventos, usada pelo app Electron.

Só escuta em 127.0.0.1 e exige o token que o app passa ao iniciar o motor,
para que nenhuma página aberta no navegador consiga chamar a API.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import __version__, acabamento, checagem, edicao_ia, gerenciar, hyperframes, ingest, markdown as md, media, pipeline, postagem, skills, sons, thumbs, transcribe, validacao
from .ai import detectar_agentes
from .ai.adapter import ErroIA, abrir_login
from .models import Clip, ConfigApp, PedidoIA
from .service import Servico
from .workspace import WorkspaceError, estilos_embutidos_dir, write_json

TAMANHO_MAX_TEXTO = 2_000_000
EXT_TEXTO = {".md", ".yaml", ".yml", ".json", ".txt", ".ass", ".css", ".html", ".js", ".srt"}
OCULTOS = {".git", "cache_ia", "__pycache__"}


class NovoCanal(BaseModel):
    nome: str
    idioma: str = "pt"
    palavras_chave: list[str] = []


class NovoProjeto(BaseModel):
    origem: str
    titulo: str | None = None
    analisar: bool = True
    modo_ia: str | None = None
    corte_longo: bool = True


class Selecao(BaseModel):
    ids: list[str]
    formato: str | None = None
    estilo: str | None = None
    cartela: bool | None = None
    pedido_ia: PedidoIA | None = None
    ajustes: dict[str, Any] | None = None


class PedidoAmostras(BaseModel):
    canal: str | None = None
    estilos: list[str] = []
    ajustes: dict[str, Any] | None = None
    formato: str | None = None


class PedidoAmostraVideo(BaseModel):
    estilo: str
    candidato: str
    ajustes: dict[str, Any] | None = None
    formato: str | None = None


class PedidoLote(BaseModel):
    clips: list[str]
    agente: str = "claude"
    modo: str = "abrir"
    destino: str = "terminal"


class Trecho(BaseModel):
    inicio: float
    fim: float
    renderizar: bool = True  # já tinha vídeo: gera de novo com o trecho novo


class PedidoChecagem(BaseModel):
    candidatos: list[str]
    usar_ia: bool = True


class MudancaItemChecagem(BaseModel):
    status: str | None = None
    nome: str | None = None
    tipo: str | None = None
    fonte: dict | None = None


class PedidoRender(BaseModel):
    clips: list[str]
    preview: bool = False


class Arquivo(BaseModel):
    caminho: str
    conteudo: str


class PedidoEdicao(BaseModel):
    agente: str = "claude"
    modo: str = "abrir"
    pedido: str = ""
    destino: str = "terminal"  # "app": só prepara, o app abre no terminal embutido


class UsarVersao(BaseModel):
    video: str | None = None


class Glossario(BaseModel):
    glossario: list[str]


class Correcoes(BaseModel):
    correcoes: dict[int, str]


class ImportarSkill(BaseModel):
    origem: str  # pasta, arquivo .zip ou link do GitHub
    substituir: bool = False


class AtivarSkill(BaseModel):
    escopo: str = "global"
    canal: str | None = None
    projeto: str | None = None


class ExportarSkill(BaseModel):
    destino: str


class PedidoThumb(BaseModel):
    usar_ia: bool = True
    linhas: list[str] | None = None


class EscolherThumb(BaseModel):
    arquivo: str


class PedidoRanking(BaseModel):
    modo_ia: str | None = None
    agente: str | None = None


def criar_app(servico: Servico | None = None, token: str | None = None) -> FastAPI:
    srv = servico or Servico()
    token = token if token is not None else (os.environ.get("CLIPATOR_TOKEN") or secrets.token_urlsafe(24))
    app = FastAPI(title="Clipator", version=__version__)
    app.state.servico = srv
    app.state.token = token
    # O app Electron carrega a interface de file:// ou do Vite em desenvolvimento.
    app.add_middleware(CORSMiddleware, allow_origins=["null", "http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["*"], allow_headers=["*"])

    def auth(request: Request, t: str | None = Query(default=None, alias="token")) -> None:
        if not token:
            return
        enviado = request.headers.get("x-clipator-token") or t
        if not enviado or not secrets.compare_digest(enviado, token):
            raise HTTPException(401, "Token inválido")

    dep = [Depends(auth)]

    @app.exception_handler(WorkspaceError)
    async def _ws_erro(_req: Request, exc: WorkspaceError):
        from fastapi.responses import JSONResponse

        status = 403 if "fora do workspace" in str(exc) else 404
        return JSONResponse({"detail": str(exc)}, status_code=status)
    ws = srv.ws

    def erro(exc: Exception) -> HTTPException:
        if isinstance(exc, (WorkspaceError, KeyError, FileNotFoundError)):
            return HTTPException(404, str(exc))
        return HTTPException(400, str(exc))

    def proj(canal: str, projeto: str):
        try:
            return srv.projeto(canal, projeto)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc

    # ---- geral -------------------------------------------------------------
    @app.get("/api/saude", dependencies=dep)
    def saude() -> dict:
        return {
            "versao": __version__,
            "workspace": str(ws.root),
            "ffmpeg": media.ffmpeg_disponivel(),  # acha também o FFmpeg do winget fora do PATH
            "hyperframes": hyperframes.comando() is not None,
            "gpu": transcribe.gpu_disponivel(),
        }

    @app.get("/api/agentes", dependencies=dep)
    def agentes() -> dict:
        return detectar_agentes()

    @app.post("/api/agentes/{nome}/login", dependencies=dep)
    def login_agente(nome: str) -> dict:
        """Abre o login da CLI num terminal; o job que espera o login continua sozinho depois."""
        if nome not in ("claude", "codex"):
            raise HTTPException(404, "IA desconhecida")
        try:
            abrir_login(nome)
        except ErroIA as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True}

    @app.get("/api/sons", dependencies=dep)
    def listar_sons() -> dict:
        return {"sons": list(sons.NOMES), "eventos": list(sons.EVENTOS)}

    @app.get("/api/sons/{nome}", dependencies=dep)
    def ouvir_som(nome: str) -> FileResponse:
        nome = nome.removesuffix(".wav")
        if nome not in sons.NOMES:
            raise HTTPException(404, "Efeito sonoro desconhecido")
        return FileResponse(sons.caminho(nome), media_type="audio/wav")

    @app.get("/api/config", dependencies=dep)
    def get_config() -> dict:
        return ws.config().model_dump(mode="json")

    @app.put("/api/config", dependencies=dep)
    def put_config(cfg: dict) -> dict:
        try:
            novo = ConfigApp.model_validate({**ws.config().model_dump(mode="json"), **cfg})
        except Exception as exc:
            raise erro(exc) from exc
        ws.salvar_config(novo)
        return novo.model_dump(mode="json")

    # ---- arquivos (explorador e editor) ---------------------------------
    @app.get("/api/arvore", dependencies=dep)
    def arvore(caminho: str = "") -> dict:
        base = ws.dentro(caminho or ".")

        def no(p: Path, prof: int) -> dict:
            rel = str(p.relative_to(ws.root)).replace("\\", "/") if p != ws.root else ""
            d: dict[str, Any] = {"nome": p.name or ws.root.name, "caminho": rel, "tipo": "pasta" if p.is_dir() else "arquivo"}
            if p.is_dir() and prof > 0:
                filhos = [c for c in p.iterdir() if c.name not in OCULTOS and not c.name.endswith(".tmp")]
                filhos.sort(key=lambda c: (c.is_file(), c.name.lower()))
                d["filhos"] = [no(c, prof - 1) for c in filhos]
            elif p.is_file():
                d["tamanho"] = p.stat().st_size
            return d

        return no(base, 6)

    @app.get("/api/arquivo", dependencies=dep)
    def ler_arquivo(caminho: str) -> dict:
        p = ws.dentro(caminho)
        if not p.is_file():
            raise HTTPException(404, "Arquivo não encontrado")
        if p.suffix.lower() not in EXT_TEXTO or p.stat().st_size > TAMANHO_MAX_TEXTO:
            raise HTTPException(415, "Arquivo não é de texto")
        conteudo = p.read_text(encoding="utf-8", errors="replace")
        return {"caminho": caminho, "conteudo": conteudo, "erros": validacao.validar(caminho, conteudo)}

    @app.put("/api/arquivo", dependencies=dep)
    def salvar_arquivo(arq: Arquivo) -> dict:
        p = ws.dentro(arq.caminho)
        if p.suffix.lower() not in EXT_TEXTO:
            raise HTTPException(415, "Só arquivos de texto podem ser editados aqui")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(arq.conteudo, encoding="utf-8")
        return {"ok": True, "erros": validacao.validar(arq.caminho, arq.conteudo)}

    @app.post("/api/validar", dependencies=dep)
    def validar(arq: Arquivo) -> dict:
        return {"erros": validacao.validar(arq.caminho, arq.conteudo)}

    @app.get("/api/midia", dependencies=dep)
    def midia(caminho: str) -> FileResponse:
        p = ws.dentro(caminho)
        if not p.is_file():
            raise HTTPException(404, "Arquivo não encontrado")
        return FileResponse(p)

    # ---- canais e projetos -----------------------------------------------
    @app.get("/api/canais", dependencies=dep)
    def canais() -> list[dict]:
        out = []
        for c in ws.canais():
            info, _ = c.info()
            out.append({"slug": c.slug, "nome": info.nome, "idioma": info.idioma, "projetos": len(c.projetos())})
        return out

    @app.post("/api/canais", dependencies=dep)
    def criar_canal(dados: NovoCanal) -> dict:
        try:
            c = ws.criar_canal(dados.nome, dados.idioma, palavras_chave=dados.palavras_chave)
        except Exception as exc:
            raise erro(exc) from exc
        return {"slug": c.slug}

    @app.get("/api/canais/{canal}/projetos", dependencies=dep)
    def projetos(canal: str) -> list[dict]:
        try:
            c = ws.canal(canal)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc
        out = []
        for p in c.projetos():
            m = p.meta()
            out.append({"id": p.id, "titulo": m.titulo, "criado_em": m.criado_em,
                        "etapas": {k: v.status for k, v in m.etapas.items()}, **gerenciar.status_projeto(p)})
        return out

    # ---- explorador: detalhes, renomear, mover, apagar ----
    def _sem_jobs(canal: str, projeto: str | None = None) -> None:
        ativos = gerenciar.jobs_ativos(srv.fila.listar(200), canal, projeto)
        if ativos:
            raise HTTPException(409, f"Espere terminar (ou cancele) o que está rodando: {ativos[0].get('tipo')}.")

    @app.get("/api/canais/{canal}/detalhes", dependencies=dep)
    def detalhes_canal(canal: str) -> dict:
        try:
            return gerenciar.detalhes_canal(ws.canal(canal))
        except Exception as exc:
            raise erro(exc) from exc

    @app.get("/api/canais/{canal}/textos", dependencies=dep)
    def textos_canal(canal: str) -> list[dict]:
        """Os arquivos de regras e textos do canal, para a pasta "Regras e textos" do explorador."""
        try:
            c = ws.canal(canal)
        except WorkspaceError as exc:
            raise HTTPException(404, str(exc)) from exc
        return [{"nome": a.name, "caminho": str(a.relative_to(ws.root)).replace("\\", "/")} for a in c.arquivos_textos()]

    @app.put("/api/canais/{canal}", dependencies=dep)
    def renomear_canal(canal: str, dados: dict) -> dict:
        try:
            c = ws.canal(canal)
            gerenciar.renomear_canal(c, str(dados.get("nome") or ""))
            return gerenciar.detalhes_canal(c)
        except Exception as exc:
            raise erro(exc) from exc

    @app.delete("/api/canais/{canal}", dependencies=dep)
    def apagar_canal(canal: str, confirmar: str = "", so_conferir: bool = False) -> dict:
        """Com so_conferir, só diz se pode (sem job rodando) e o que vai sumir; o app manda para a Lixeira."""
        try:
            c = ws.canal(canal)
        except Exception as exc:
            raise erro(exc) from exc
        _sem_jobs(canal)
        info = gerenciar.detalhes_canal(c)
        if so_conferir:
            return info
        if confirmar != c.slug:
            raise HTTPException(400, f"Para apagar, confirme com o nome do canal ({c.slug}).")
        gerenciar.apagar(c.path, ws)
        return {"apagado": c.slug}

    @app.get("/api/canais/{canal}/projetos/{projeto}/detalhes", dependencies=dep)
    def detalhes_projeto(canal: str, projeto: str) -> dict:
        try:
            return gerenciar.detalhes_projeto(proj(canal, projeto))
        except Exception as exc:
            raise erro(exc) from exc

    @app.put("/api/canais/{canal}/projetos/{projeto}", dependencies=dep)
    def renomear_projeto(canal: str, projeto: str, dados: dict) -> dict:
        try:
            p = proj(canal, projeto)
            gerenciar.renomear_projeto(p, str(dados.get("titulo") or ""))
            return gerenciar.detalhes_projeto(p)
        except Exception as exc:
            raise erro(exc) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/mover", dependencies=dep)
    def mover_projeto(canal: str, projeto: str, dados: dict) -> dict:
        _sem_jobs(canal, projeto)
        try:
            novo = gerenciar.mover_projeto(ws, proj(canal, projeto), str(dados.get("destino") or ""))
        except Exception as exc:
            raise erro(exc) from exc
        return {"canal": novo.canal.slug, "projeto": novo.id}

    @app.delete("/api/canais/{canal}/projetos/{projeto}", dependencies=dep)
    def apagar_projeto(canal: str, projeto: str, confirmar: bool = False, so_conferir: bool = False) -> dict:
        try:
            p = proj(canal, projeto)
        except Exception as exc:
            raise erro(exc) from exc
        _sem_jobs(canal, projeto)
        info = gerenciar.detalhes_projeto(p)
        if so_conferir:
            return info
        if not confirmar:
            raise HTTPException(400, "Apagar exige confirmar=true")
        gerenciar.apagar(p.path, ws)
        return {"apagado": p.id}

    @app.post("/api/canais/{canal}/projetos", dependencies=dep)
    def criar_projeto(canal: str, dados: NovoProjeto) -> dict:
        try:
            p = pipeline.criar_projeto(ws, ws.canal(canal), dados.origem, dados.titulo)
        except Exception as exc:
            raise erro(exc) from exc
        job = None
        if dados.analisar:
            job = srv.fila.enviar("analisar", {"canal": canal, "projeto": p.id, "modo_ia": dados.modo_ia,
                                               "corte_longo": dados.corte_longo})
        return {"id": p.id, "job": job}

    @app.get("/api/canais/{canal}/projetos/{projeto}", dependencies=dep)
    def detalhe_projeto(canal: str, projeto: str) -> dict:
        p = proj(canal, projeto)
        video = p.video_path()
        return {
            "meta": p.meta().model_dump(mode="json"),
            "metadados": p.metadados(),
            "video": str(video.relative_to(ws.root)).replace("\\", "/") if video else None,
            "clips": [{**c.model_dump(mode="json"), "pasta": str(d.relative_to(ws.root)).replace("\\", "/"),
                       "saida": (d / "saida.mp4").exists(), "preview": (d / "preview.mp4").exists()}
                      for c, d in p.clips()],
        }

    @app.post("/api/canais/{canal}/projetos/{projeto}/analisar", dependencies=dep)
    def analisar(canal: str, projeto: str, modo_ia: str | None = None, corte_longo: bool = True,
                 refazer: bool = False, cookies_navegador: str | None = None) -> dict:
        proj(canal, projeto)
        if cookies_navegador and cookies_navegador not in ingest.NAVEGADORES:
            raise HTTPException(400, f"Navegador desconhecido: {cookies_navegador}")
        return {"job": srv.fila.enviar("analisar", {"canal": canal, "projeto": projeto, "modo_ia": modo_ia,
                                                    "corte_longo": corte_longo, "refazer": refazer,
                                                    "cookies_navegador": cookies_navegador})}

    @app.get("/api/youtube/conta", dependencies=dep)
    def conta_youtube() -> dict:
        from . import contayt

        return contayt.estado()

    @app.post("/api/youtube/conta", dependencies=dep)
    def conectar_youtube(canal: str | None = None, projeto: str | None = None) -> dict:
        """Abre o navegador do Clipator para entrar; com canal e projeto, o download recomeça sozinho depois."""
        return {"job": srv.fila.enviar("conta_youtube", {"canal": canal, "projeto": projeto})}

    @app.post("/api/youtube/continuar", dependencies=dep)
    def continuar_youtube() -> dict:
        """O botão "Já entrei, continuar": fecha a janela de login e lê a conta."""
        from . import contayt

        contayt.continuar.set()
        return {"ok": True}

    @app.post("/api/youtube/firefox", dependencies=dep)
    def usar_firefox(canal: str | None = None, projeto: str | None = None) -> dict:
        return {"job": srv.fila.enviar("firefox_youtube", {"canal": canal, "projeto": projeto})}

    @app.delete("/api/youtube/conta", dependencies=dep)
    def desconectar_youtube() -> dict:
        from . import contayt

        contayt.desconectar()
        return contayt.estado()

    @app.get("/api/navegadores", dependencies=dep)
    def navegadores() -> dict:
        return {"instalados": ingest.navegadores_instalados(), "todos": list(ingest.NAVEGADORES),
                "nomes": ingest.NOMES_NAVEGADOR}

    @app.get("/api/canais/{canal}/projetos/{projeto}/transcricao", dependencies=dep)
    def get_transcricao(canal: str, projeto: str) -> dict:
        t = proj(canal, projeto).transcricao()
        if t is None:
            raise HTTPException(404, "Ainda sem transcrição")
        return t

    @app.post("/api/canais/{canal}/projetos/{projeto}/transcricao/corrigir-nomes", dependencies=dep)
    def corrigir_nomes(canal: str, projeto: str) -> dict:
        try:
            trocas = pipeline.corrigir_nomes(proj(canal, projeto))
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"trocas": trocas}

    @app.get("/api/canais/{canal}/glossario", dependencies=dep)
    def get_glossario(canal: str) -> dict:
        info, _ = ws.canal(canal).info()
        return {"glossario": info.glossario}

    @app.get("/api/canais/{canal}/chamada", dependencies=dep)
    def get_chamada(canal: str) -> dict:
        info, _ = ws.canal(canal).info()
        return {"chamada_automatica": info.chamada_automatica}

    @app.put("/api/canais/{canal}/chamada", dependencies=dep)
    def put_chamada(canal: str, dados: dict) -> dict:
        from .edicao import CHAMADA_AUTOMATICA

        modo = str(dados.get("chamada_automatica") or "")
        if modo not in CHAMADA_AUTOMATICA:
            raise HTTPException(400, "Use nenhuma, inicio, fim ou inicio-e-fim")
        c = ws.canal(canal)
        doc = md.read(c.path / "canal.md")
        meta = dict(doc.meta)
        meta["chamada_automatica"] = modo
        md.write(c.path / "canal.md", meta, doc.body)
        return {"chamada_automatica": modo}

    @app.put("/api/canais/{canal}/glossario", dependencies=dep)
    def put_glossario(canal: str, dados: Glossario) -> dict:
        c = ws.canal(canal)
        doc = md.read(c.path / "canal.md")
        meta = dict(doc.meta)
        meta["glossario"] = [t for t in (x.strip() for x in dados.glossario) if t]
        md.write(c.path / "canal.md", meta, doc.body)
        return {"glossario": meta["glossario"]}

    @app.put("/api/canais/{canal}/projetos/{projeto}/transcricao", dependencies=dep)
    def corrigir_transcricao(canal: str, projeto: str, dados: Correcoes) -> dict:
        p = proj(canal, projeto)
        t = p.transcricao()
        if t is None:
            raise HTTPException(404, "Ainda sem transcrição")
        write_json(p.transcricao_path, transcribe.corrigir(t, dados.correcoes))
        return {"ok": True}

    @app.get("/api/canais/{canal}/projetos/{projeto}/sinais", dependencies=dep)
    def get_sinais(canal: str, projeto: str) -> dict:
        return proj(canal, projeto).sinais() or {}

    @app.get("/api/canais/{canal}/projetos/{projeto}/candidatos", dependencies=dep)
    def get_candidatos(canal: str, projeto: str) -> list[dict]:
        return proj(canal, projeto).candidatos()

    @app.get("/api/canais/{canal}/projetos/{projeto}/candidatos/{cid}/estilo-sugerido", dependencies=dep)
    def estilo_sugerido(canal: str, projeto: str, cid: str) -> list[dict]:
        """Os estilos animados do mais ao menos indicado para o tema do corte (conta offline, sem IA)."""
        from . import sugestao_estilo

        p = proj(canal, projeto)
        cand = next((c for c in p.candidatos() if c.get("id") == cid), None)
        if cand is None:
            raise HTTPException(404, "Corte não encontrado.")
        return sugestao_estilo.do_candidato(cand, list(ws.estilos(ws.canal(canal))))

    @app.get("/api/canais/{canal}/projetos/{projeto}/candidatos/{cid}/quadros", dependencies=dep)
    def quadros_candidato(canal: str, projeto: str, cid: str) -> dict:
        p = proj(canal, projeto)
        try:
            qs = pipeline.quadros_candidato(p, cid)
        except KeyError:
            raise HTTPException(404, "Candidato não encontrado") from None
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None

        def rel(x: Path) -> str:
            return str(x.relative_to(ws.root)).replace("\\", "/")

        video = p.video_path()
        return {"video": rel(video) if video else None, "rosto_x": pipeline.centro_rosto(p, cid, qs),
                "quadros": [{**q, "imagem": rel(q["imagem"])} for q in qs]}

    @app.post("/api/canais/{canal}/projetos/{projeto}/candidatos", dependencies=dep)
    def regerar_candidatos(canal: str, projeto: str, modo: str = "curto") -> dict:
        proj(canal, projeto)
        return {"job": srv.fila.enviar("candidatos", {"canal": canal, "projeto": projeto, "modo": modo})}

    @app.post("/api/canais/{canal}/projetos/{projeto}/ranquear", dependencies=dep)
    def ranquear(canal: str, projeto: str, dados: PedidoRanking) -> dict:
        proj(canal, projeto)
        return {"job": srv.fila.enviar("ranquear", {"canal": canal, "projeto": projeto, **dados.model_dump()})}

    @app.post("/api/canais/{canal}/projetos/{projeto}/selecionar", dependencies=dep)
    def selecionar(canal: str, projeto: str, dados: Selecao) -> list[dict]:
        try:
            clips = pipeline.selecionar(proj(canal, projeto), dados.ids, dados.formato, dados.estilo, dados.cartela,
                                        dados.pedido_ia, dados.ajustes)
        except Exception as exc:
            raise erro(exc) from exc
        return [c.model_dump(mode="json") for c in clips]

    @app.put("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}", dependencies=dep)
    def atualizar_clip(canal: str, projeto: str, clip_id: str, dados: dict) -> dict:
        p = proj(canal, projeto)
        try:
            atual, pasta = p.clip(clip_id)
            novo = Clip.model_validate({**atual.model_dump(mode="json"), **dados, "id": clip_id})
            if (novo.inicio, novo.fim, novo.cortes_internos) != (atual.inicio, atual.fim, atual.cortes_internos):
                novo.status = "selecionado"
            p.salvar_clip(novo)
        except Exception as exc:
            raise erro(exc) from exc
        return novo.model_dump(mode="json")

    def render_do_clip(canal: str, projeto: str, clip_id: str) -> dict | None:
        return next((j for j in srv.fila.listar(200) if j["tipo"] == "renderizar"
                     and j["status"] in ("rodando", "na_fila") and j["params"].get("canal") == canal
                     and j["params"].get("projeto") == projeto and clip_id in (j["params"].get("clips") or [])), None)

    @app.put("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/trecho", dependencies=dep)
    def ajustar_trecho(canal: str, projeto: str, clip_id: str, dados: Trecho) -> dict:
        """Tela "Editar duração": novo início e fim no vídeo original; renderiza de novo se já tinha vídeo."""
        from . import trecho

        p = proj(canal, projeto)
        if render_do_clip(canal, projeto, clip_id):
            raise HTTPException(409, "Esse clip está renderizando agora. Espere terminar ou cancele o render.")
        try:
            r = trecho.ajustar(p, clip_id, dados.inicio, dados.fim)
        except Exception as exc:
            raise erro(exc) from exc
        job = None
        if r.renderizar and dados.renderizar:
            job = srv.fila.enviar("renderizar", {"canal": canal, "projeto": projeto, "clips": [clip_id], "preview": r.preview})
        return {"clip": r.clip.model_dump(mode="json"), "job": job, "itens_movidos": r.itens_movidos,
                "itens_removidos": r.itens_removidos}

    @app.put("/api/canais/{canal}/projetos/{projeto}/candidatos/{cid}/trecho", dependencies=dep)
    def ajustar_trecho_candidato(canal: str, projeto: str, cid: str, dados: Trecho) -> dict:
        """Passo 2: novo início e fim de um corte sugerido, antes de virar clip."""
        from . import trecho

        try:
            return {"candidato": trecho.ajustar_candidato(proj(canal, projeto), cid, dados.inicio, dados.fim)}
        except Exception as exc:
            raise erro(exc) from exc

    @app.delete("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}", dependencies=dep)
    def remover_clip(canal: str, projeto: str, clip_id: str, confirmar: bool = False) -> dict:
        if not confirmar:
            raise HTTPException(409, "Confirme para apagar (confirmar=true)")
        p = proj(canal, projeto)
        rodando = [j for j in srv.fila.listar(200) if j["tipo"] in ("renderizar", "thumbnail", "thumbnail_ia")
                   and j["status"] in ("rodando", "na_fila") and j["params"].get("canal") == canal
                   and j["params"].get("projeto") == projeto
                   and clip_id in (j["params"].get("clips") or [j["params"].get("clip")])]
        if rodando:
            raise HTTPException(409, "Esse clip está renderizando agora. Cancele o render e apague depois.")
        try:
            p.remover_clip(clip_id)
        except WorkspaceError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"ok": True}

    # ---- editar com a IA do usuário (fora do núcleo: abre a CLI interativa dele) ----------
    @app.get("/api/edicao-ia", dependencies=dep)
    def edicao_ia_info(mcp: bool = True) -> dict:
        return {"agentes": edicao_ia.detectar(mcp), "sugestoes": edicao_ia.SUGESTOES}

    @app.post("/api/edicao-ia/{agente}/registrar-mcp", dependencies=dep)
    def edicao_ia_registrar(agente: str) -> dict:
        if agente not in edicao_ia.AGENTES:
            raise HTTPException(404, "IA desconhecida")
        try:
            edicao_ia.registrar(agente)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "mcp": edicao_ia.mcp_registrado(agente)}

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/editar-ia", dependencies=dep)
    def editar_ia(canal: str, projeto: str, clip_id: str, dados: PedidoEdicao) -> dict:
        if dados.agente not in edicao_ia.AGENTES or dados.modo not in ("abrir", "continuar"):
            raise HTTPException(400, "Escolha Claude Code ou Codex e o modo abrir ou continuar")
        try:
            return edicao_ia.abrir(proj(canal, projeto), clip_id, dados.agente, dados.modo, dados.pedido,
                                   lancar=dados.destino != "app")
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/pedido-ia", dependencies=dep)
    def pedido_ia_lote(canal: str, projeto: str, dados: PedidoLote) -> dict:
        if dados.agente not in edicao_ia.AGENTES or dados.modo not in ("abrir", "continuar"):
            raise HTTPException(400, "Escolha Claude Code ou Codex e o modo abrir ou continuar")
        try:
            return edicao_ia.abrir_lote(proj(canal, projeto), dados.clips, dados.agente, dados.modo,
                                        lancar=dados.destino != "app")
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/editar-ia/prompt", dependencies=dep)
    def editar_ia_prompt(canal: str, projeto: str, clip_id: str, dados: PedidoEdicao) -> dict:
        try:
            destino, texto = edicao_ia.montar_pedido(proj(canal, projeto), clip_id, dados.pedido)
        except Exception as exc:
            raise erro(exc) from exc
        return {"pasta": str(destino), "texto": texto}

    # ---- stickers do editor ----
    def _pasta_canal(canal: str | None):
        if not canal:
            return None
        try:
            return ws.canal(canal).path
        except Exception as exc:
            raise erro(exc) from exc

    @app.get("/api/stickers", dependencies=dep)
    def listar_stickers(canal: str | None = None) -> dict:
        from . import stickers

        return stickers.listar(_pasta_canal(canal))

    @app.post("/api/stickers/instalar", dependencies=dep)
    def instalar_stickers() -> dict:
        return {"job": srv.fila.enviar("stickers", {})}

    @app.get("/api/stickers/arquivo", dependencies=dep)
    def arquivo_sticker(request: Request, ref: str, canal: str | None = None) -> FileResponse:
        from . import cta, stickers

        campos = ("texto", "texto2", "cor", "cor_texto", "idioma", "preset", "fonte", *cta.FORMATO_BOOL)
        params = {k: request.query_params.get(k, "") for k in campos}
        p = stickers.resolver(ref, _pasta_canal(canal), params=params)
        if p is None:
            raise HTTPException(404, "Sticker não encontrado (o pacote foi baixado?)")
        return FileResponse(p)

    @app.get("/api/stickers/web/buscar", dependencies=dep)
    def buscar_stickers_web(q: str, colecao: str | None = None) -> list[dict]:
        from . import stickers

        try:
            return stickers.buscar_web(q, colecao)
        except stickers.ErroSticker as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/stickers/web/svg", dependencies=dep)
    def svg_sticker_web(id: str) -> FileResponse:  # noqa: A002 - nome do parâmetro na URL
        from . import stickers

        try:
            return FileResponse(stickers.svg_web(id, ws.root / ".clipator" / "cache-stickers"), media_type="image/svg+xml")
        except stickers.ErroSticker as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/stickers/web/salvar", dependencies=dep)
    def salvar_sticker_web(dados: dict) -> dict:
        import base64

        from . import stickers

        try:
            png = base64.b64decode(str(dados.get("png") or "").split(",")[-1])
            return stickers.salvar_web(_pasta_canal(str(dados.get("canal") or "")), str(dados.get("id") or ""), png)
        except stickers.ErroSticker as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/fontes", dependencies=dep)
    def listar_fontes(canal: str | None = None) -> list[dict]:
        from . import cta

        pasta = _pasta_canal(canal)
        return cta.listar_fontes(pasta / "assets" / "fontes" if pasta else None)

    @app.post("/api/fontes/baixar", dependencies=dep)
    def baixar_fonte(dados: dict) -> dict:
        from . import fontes

        try:
            return fontes.baixar(str(dados.get("id") or ""))
        except fontes.ErroFonte as exc:
            raise HTTPException(502 if "baixar" in str(exc) else 400, str(exc)) from exc

    @app.post("/api/fontes/instalar", dependencies=dep)
    def instalar_fontes() -> dict:
        return {"job": srv.fila.enviar("fontes", {})}

    @app.get("/api/fontes/amostra", dependencies=dep)
    def amostra_fonte(id: str, canal: str | None = None) -> FileResponse:  # noqa: A002 - nome do parâmetro na URL
        from . import cta

        pasta = _pasta_canal(canal)
        p = cta.amostra_fonte(id, pasta / "assets" / "fontes" if pasta else None, ws.root / ".clipator" / "cache-fontes")
        if p is None:
            raise HTTPException(404, "Fonte não baixada")
        return FileResponse(p, media_type="image/png")

    @app.post("/api/fontes/enviar", dependencies=dep)
    def enviar_fonte(dados: dict) -> dict:
        import base64
        import binascii

        from . import cta

        pasta = _pasta_canal(str(dados.get("canal") or ""))
        if pasta is None:
            raise HTTPException(400, "Escolha o canal.")
        try:
            bruto = base64.b64decode(str(dados.get("arquivo") or "").split(",")[-1], validate=True)
            return cta.salvar_fonte(pasta / "assets" / "fontes", str(dados.get("nome") or ""), bruto)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/stickers/canal/enviar", dependencies=dep)
    def enviar_sticker_canal(dados: dict) -> dict:
        import base64
        import binascii

        from . import stickers

        pasta = _pasta_canal(str(dados.get("canal") or ""))
        if pasta is None:
            raise HTTPException(400, "Escolha o canal.")
        bruto = str(dados.get("png") or "").split(",")[-1]
        if len(bruto) > stickers.LIMITE_ENVIO * 4 // 3 + 8:
            raise HTTPException(400, "O arquivo passa do limite de 5 MB.")
        try:
            png = base64.b64decode(bruto, validate=True)
            return stickers.salvar_enviado(pasta, str(dados.get("nome") or ""), png)
        except (stickers.ErroSticker, binascii.Error, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    # ---- editor do passo 3 (edicao.json) ----
    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao/versoes", dependencies=dep)
    def versoes_da_edicao(canal: str, projeto: str, clip_id: str) -> dict:
        from . import melhorar

        try:
            return melhorar.listar(proj(canal, projeto), clip_id)
        except Exception as exc:
            raise erro(exc) from exc

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/revisao", dependencies=dep)
    def ler_revisao(canal: str, projeto: str, clip_id: str) -> dict:
        from . import revisao

        return {"revisao": revisao.ultima(proj(canal, projeto), clip_id)}

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/revisao", dependencies=dep)
    def pedir_revisao(canal: str, projeto: str, clip_id: str, usar_ia: bool = True) -> dict:
        proj(canal, projeto).clip(clip_id)
        return {"job": srv.fila.enviar("revisao", {"canal": canal, "projeto": projeto, "clip": clip_id, "usar_ia": usar_ia})}

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/direcao-arte", dependencies=dep)
    def direcao_do_clip(canal: str, projeto: str, clip_id: str) -> dict:
        from . import desenho

        try:
            return desenho.resumo_do_clip(proj(canal, projeto), clip_id)
        except Exception as exc:
            raise erro(exc) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/direcao-arte/refazer", dependencies=dep)
    def refazer_direcao(canal: str, projeto: str, clip_id: str, dados: dict) -> dict:
        from . import melhorar

        proj(canal, projeto).clip(clip_id)
        if melhorar.ia_do_workspace(ws) is None:
            raise HTTPException(409, melhorar.MSG_SEM_IA)
        return {"job": srv.fila.enviar("refazer_direcao", {"canal": canal, "projeto": projeto, "clip": clip_id,
                                                            "roteiro": dados.get("roteiro"), "cores": dados.get("cores"),
                                                            "tudo": bool(dados.get("tudo"))})}

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/direcao-arte/ajustar", dependencies=dep)
    def ajustar_direcao(canal: str, projeto: str, clip_id: str, dados: dict) -> dict:
        """Texto, ordem, parâmetros, cores e composição da direção: não precisa de IA, vira versão e renderiza de novo."""
        from . import artes
        from .models import LayoutArte

        p = proj(canal, projeto)
        try:
            est = p.ws.carregar_estilo(p.clip(clip_id)[0].estilo, p.canal)[0]
            if est.direcao.arte:  # recusa na hora, antes de entrar na fila
                artes.validar_parametros(est.direcao.arte, dados.get("parametros"), estrito=True)
            if dados.get("composicao"):
                LayoutArte.model_validate(dados["composicao"])
        except Exception as exc:
            raise erro(exc) from exc
        return {"job": srv.fila.enviar("ajustar_arte", {"canal": canal, "projeto": projeto, "clip": clip_id, "cenas": dados.get("cenas"),
                                                         "parametros": dados.get("parametros"), "cores": dados.get("cores"),
                                                         "composicao": dados.get("composicao")})}

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/melhorar", dependencies=dep)
    def melhorar_edicao(canal: str, projeto: str, clip_id: str, dados: dict) -> dict:
        from . import melhorar

        p = proj(canal, projeto)
        p.clip(clip_id)
        if melhorar.ia_do_workspace(ws) is None:
            raise HTTPException(409, melhorar.MSG_SEM_IA)
        return {"job": srv.fila.enviar("melhorar_edicao", {"canal": canal, "projeto": projeto, "clip": clip_id,
                                                            "feedback": str(dados.get("feedback") or "")[:600],
                                                            "previa": bool(dados.get("previa", True))})}

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao/versoes/{n}/usar", dependencies=dep)
    def usar_versao(canal: str, projeto: str, clip_id: str, n: int) -> dict:
        from . import melhorar

        try:
            return melhorar.usar(proj(canal, projeto), clip_id, n)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao/versoes/comparar", dependencies=dep)
    def comparar_versoes(canal: str, projeto: str, clip_id: str, a: int, b: int) -> dict:
        from . import melhorar

        try:
            return melhorar.comparar(proj(canal, projeto), clip_id, a, b)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao/versoes/{n}/previa", dependencies=dep)
    def previa_da_versao(canal: str, projeto: str, clip_id: str, n: int) -> dict:
        from . import melhorar

        _, pasta = proj(canal, projeto).clip(clip_id)
        try:
            melhorar.ler(pasta, n)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"job": srv.fila.enviar("renderizar", {"canal": canal, "projeto": projeto, "clips": [clip_id], "preview": True,
                                                      "versao": n})}

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao", dependencies=dep)
    def get_edicao(canal: str, projeto: str, clip_id: str) -> dict:
        from . import edicao

        try:
            p = proj(canal, projeto)
            _, pasta = p.clip(clip_id)
            return {**edicao.carregar(pasta).model_dump(mode="json"), "duracao": edicao.duracao_do_clip(p, clip_id),
                    "tipos": edicao.TIPOS, "padrao": edicao.PADRAO, "sons": list(sons.NOMES)}
        except Exception as exc:
            raise erro(exc) from exc

    @app.put("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao", dependencies=dep)
    def put_edicao(canal: str, projeto: str, clip_id: str, dados: dict) -> dict:
        from . import edicao

        try:
            p = proj(canal, projeto)
            _, pasta = p.clip(clip_id)
            atual = edicao.carregar(pasta)
            # quem gravou por último ganha, mas o editor manda a revisão que viu para avisar de conflito
            if dados.get("revisao") is not None and int(dados["revisao"]) != atual.revisao:
                raise HTTPException(409, "A edição mudou enquanto você editava (a IA mexeu?). Recarregue.")
            from . import melhorar

            novo = atual.model_copy(update={"itens": [edicao.Item.model_validate(i) for i in dados.get("itens") or []]})
            melhorar.garantir_inicial(p, clip_id)
            out = edicao.salvar(pasta, novo, edicao.duracao_do_clip(p, clip_id)).model_dump(mode="json")
            melhorar.registrar(p, clip_id, "manual")  # edição à mão também vira versão (seguidas, juntas)
            return out
        except HTTPException:
            raise
        except Exception as exc:
            raise erro(exc) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/edicao/sugerir", dependencies=dep)
    def sugerir_efeitos(canal: str, projeto: str, clip_id: str, usar_ia: bool = True) -> dict:
        proj(canal, projeto).clip(clip_id)
        return {"job": srv.fila.enviar("efeitos_ia", {"canal": canal, "projeto": projeto, "clip": clip_id, "usar_ia": usar_ia})}

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/quadros", dependencies=dep)
    def quadros_do_clip(canal: str, projeto: str, clip_id: str, n: int = 12) -> dict:
        """Miniaturas ao longo do clip (tempo do clip) para a tira do editor."""
        from .timeline import Timeline

        try:
            p = proj(canal, projeto)
            clip, pasta = p.clip(clip_id)
            video = p.video_path()
            if video is None:
                return {"quadros": []}
            tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
            n = max(2, min(40, n))
            destino = pasta / "quadros-editor"
            destino.mkdir(exist_ok=True)
            out = []
            for k in range(n):
                t = tl.duracao * (k + 0.5) / n
                orig = tl.para_original(t)
                arq = destino / f"q{orig:.2f}.jpg"
                if not arq.exists():
                    media.run_ffmpeg(["-ss", f"{orig:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=-2:120",
                                      "-q:v", "6", str(arq)], descricao="miniatura")
                out.append({"tempo": round(t, 3), "imagem": str(arq.relative_to(ws.root)).replace("\\", "/")})
            return {"quadros": out}
        except Exception as exc:
            raise erro(exc) from exc

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/versoes", dependencies=dep)
    def versoes(canal: str, projeto: str, clip_id: str) -> list[dict]:
        try:
            return edicao_ia.listar_versoes(proj(canal, projeto), clip_id)
        except Exception as exc:
            raise erro(exc) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/versoes/usar", dependencies=dep)
    def usar_versao_video(canal: str, projeto: str, clip_id: str, dados: UsarVersao) -> dict:
        try:
            edicao_ia.usar_versao(proj(canal, projeto), clip_id, dados.video)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    @app.delete("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/versoes/{versao_id}", dependencies=dep)
    def apagar_versao(canal: str, projeto: str, clip_id: str, versao_id: str, confirmar: bool = False) -> dict:
        if not confirmar:
            raise HTTPException(409, "Confirme para apagar (confirmar=true)")
        try:
            edicao_ia.apagar_versao(proj(canal, projeto), clip_id, versao_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"ok": True}

    # ---- checagem de fatos do passo 4 (o que a fala cita, o nome certo e a fonte) ----
    @app.get("/api/canais/{canal}/projetos/{projeto}/checagem", dependencies=dep)
    def ver_checagem(canal: str, projeto: str) -> dict:
        ch = checagem.carregar(proj(canal, projeto))
        return {**ch.model_dump(mode="json"), "resumo": checagem.resumo(ch)}

    @app.post("/api/canais/{canal}/projetos/{projeto}/checagem", dependencies=dep)
    def identificar_checagem(canal: str, projeto: str, dados: PedidoChecagem) -> dict:
        p = proj(canal, projeto)
        if not p.transcricao():
            raise HTTPException(409, "O vídeo ainda não tem transcrição. Rode a análise no passo 1.")
        if not dados.candidatos:
            raise HTTPException(400, "Nenhum corte para checar. Escolha os cortes no passo 2.")
        return {"job": srv.fila.enviar("checagem", {"canal": canal, "projeto": projeto, "candidatos": dados.candidatos,
                                                    "usar_ia": dados.usar_ia})}

    @app.put("/api/canais/{canal}/projetos/{projeto}/checagem/itens/{item_id}", dependencies=dep)
    def mudar_item_checagem(canal: str, projeto: str, item_id: str, dados: MudancaItemChecagem) -> dict:
        try:
            return checagem.atualizar_item(proj(canal, projeto), item_id, dados.status, dados.nome, dados.fonte,
                                           dados.tipo).model_dump(mode="json")
        except checagem.ErroChecagem as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/checagem/confirmar-pendentes", dependencies=dep)
    def confirmar_checagem(canal: str, projeto: str) -> dict:
        return {"confirmados": checagem.confirmar_pendentes(proj(canal, projeto))}

    @app.get("/api/checagem/fontes", dependencies=dep)
    def buscar_fontes(busca: str) -> list[dict]:
        """Outras fontes no Wikidata para o usuário escolher (precisa de rede)."""
        try:
            return checagem.opcoes_wikidata(busca)
        except Exception as exc:
            raise HTTPException(502, f"Não consegui buscar no Wikidata agora ({exc}). Escreva a fonte à mão.") from exc

    # ---- acabamento do passo 5 (música de fundo e ajustes de imagem no clip gerado) ----
    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/acabamento", dependencies=dep)
    def ver_acabamento(canal: str, projeto: str, clip_id: str) -> dict:
        try:
            return acabamento.estado(proj(canal, projeto), clip_id)
        except acabamento.ErroAcabamento as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise erro(exc) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/acabamento", dependencies=dep)
    def aplicar_acabamento(canal: str, projeto: str, clip_id: str, dados: acabamento.Acabamento) -> dict:
        p = proj(canal, projeto)
        try:
            acabamento.base_do_clip(p, clip_id)
            if dados.musica:
                acabamento.caminho_musica(p.canal.path, dados.musica.arquivo)
        except acabamento.ErroAcabamento as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise erro(exc) from exc
        return {"job": srv.fila.enviar("acabamento", {"canal": canal, "projeto": projeto, "clip": clip_id,
                                                      "ajustes": dados.model_dump(mode="json")})}

    @app.get("/api/canais/{canal}/musicas", dependencies=dep)
    def listar_musicas(canal: str) -> list[dict]:
        return acabamento.listar_musicas(_pasta_canal(canal))

    @app.post("/api/canais/{canal}/musicas", dependencies=dep)
    def enviar_musica(canal: str, dados: dict) -> dict:
        import base64
        import binascii

        pasta = _pasta_canal(canal)
        bruto = str(dados.get("arquivo") or "").split(",")[-1]
        if len(bruto) > acabamento.LIMITE_MUSICA * 4 // 3 + 8:
            raise HTTPException(400, f"O arquivo passa do limite de {acabamento.LIMITE_MUSICA // (1024 * 1024)} MB.")
        try:
            return acabamento.salvar_musica(pasta, str(dados.get("nome") or ""), base64.b64decode(bruto, validate=True))
        except (acabamento.ErroAcabamento, binascii.Error, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/postagem", dependencies=dep)
    def ver_postagem(canal: str, projeto: str, clip_id: str) -> dict:
        try:
            return postagem.carregar(proj(canal, projeto), clip_id)
        except Exception as exc:
            raise erro(exc) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/postagem", dependencies=dep)
    def gerar_postagem(canal: str, projeto: str, clip_id: str, usar_ia: bool = False) -> dict:
        try:
            proj(canal, projeto).clip(clip_id)
        except Exception as exc:
            raise erro(exc) from exc
        return {"job": srv.fila.enviar("postagem", {"canal": canal, "projeto": projeto, "clip": clip_id, "usar_ia": usar_ia})}

    @app.post("/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}/titulos", dependencies=dep)
    def gerar_titulos(canal: str, projeto: str, clip_id: str) -> dict:
        try:
            return pipeline.sugerir_titulos(proj(canal, projeto), clip_id)
        except ErroIA as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/canais/{canal}/projetos/{projeto}/renderizar", dependencies=dep)
    def renderizar(canal: str, projeto: str, dados: PedidoRender) -> dict:
        p = proj(canal, projeto)
        for cid in dados.clips:
            try:
                p.clip(cid)
            except WorkspaceError as exc:
                raise HTTPException(404, str(exc)) from exc
        return {"job": srv.fila.enviar("renderizar", {"canal": canal, "projeto": projeto, "clips": dados.clips,
                                                      "preview": dados.preview})}

    # ---- estilos -----------------------------------------------------------
    @app.get("/api/estilos", dependencies=dep)
    def estilos(canal: str | None = None) -> list[dict]:
        from . import amostras

        c = ws.canal(canal) if canal else None
        padrao = c.info()[0].estilo_padrao if c else None
        out = []
        visiveis = ws.estilos(c)  # uma varredura só: refazer a cada estilo era o que deixava a galeria lenta
        for nome, path in visiveis.items():
            try:
                est, corpo, _ = ws.carregar_estilo(nome, c, estilos=visiveis)
                amostra = amostras.achar(ws, nome, c, estilos=visiveis)
                origem = ("embutido" if path.parent == estilos_embutidos_dir() else
                          "canal" if c and c.path in path.parents else
                          "workspace" if ws.root in path.parents else "skill")
                out.append({"id": nome, "nome": est.nome or nome, "descricao": est.descricao, "objetivo": est.objetivo,
                            "formato": est.formato, "motor": est.motor, "nivel_ia": est.nivel_ia,
                            "caminho": str(path), "embutido": origem == "embutido", "skill": origem == "skill",
                            "origem": origem, "padrao": nome == padrao, "requer_ia": est.requer_ia,
                            "detalhes": {"legenda": est.legenda.model_dump(include={"fonte", "tamanho", "cor", "destaque",
                                                                                    "contorno", "posicao", "animacao",
                                                                                    "modo", "caixa_alta", "fundo"}),
                                         "cartela": est.cartela.sugerida, "zoom": est.zoom.enfase,
                                         "intensidade_zoom": est.zoom.intensidade, "jump_cuts": est.jump_cuts,
                                         "sons": est.sons, "volume_sons": est.volume_sons,
                                         "musica": bool(est.musica.arquivo), "logo": bool(est.logo),
                                         "reenquadramento": est.reenquadramento, "dividido": est.dividido.model_dump(),
                                         "direcao": est.direcao.layout, "ficha": est.direcao.ficha},
                            "amostra": amostra.name if amostra else None})
            except Exception as exc:  # estilo com erro aparece com a mensagem
                out.append({"id": nome, "nome": nome, "erro": str(exc), "caminho": str(path)})
        return out

    @app.post("/api/estilos/amostras", dependencies=dep)
    def pedir_amostras(dados: PedidoAmostras) -> dict:
        """Gera (num job) as amostras que ainda não estão em cache; devolve as prontas na hora."""
        from . import amostras

        c = ws.canal(dados.canal) if dados.canal else None
        prontas, faltam = {}, []
        visiveis = ws.estilos(c)
        for nome in dados.estilos or list(visiveis):
            try:
                p = amostras.achar(ws, nome, c, dados.ajustes, dados.formato, visiveis)
            except Exception:  # noqa: BLE001 - estilo com erro fica sem amostra
                continue
            if p is not None:
                prontas[nome] = p.name
            else:
                faltam.append(nome)
        job = srv.fila.enviar("amostras_estilo", {"canal": dados.canal, "estilos": faltam, "ajustes": dados.ajustes,
                                                  "formato": dados.formato}) if faltam else None
        return {"prontas": prontas, "faltam": faltam, "job": job}

    @app.get("/api/estilos/amostra/arquivo", dependencies=dep)
    def arquivo_amostra(nome: str) -> FileResponse:
        from . import amostras

        if not re.fullmatch(r"[\w\-]{1,140}\.(mp4|jpg)", nome):
            raise HTTPException(400, "Nome inválido")
        p = amostras.arquivo(nome)
        if p is None:
            raise HTTPException(404, "Amostra ainda não gerada")
        return FileResponse(p, media_type="video/mp4" if nome.endswith(".mp4") else "image/jpeg")

    @app.post("/api/canais/{canal}/projetos/{projeto}/amostra-estilo", dependencies=dep)
    def amostra_com_video(canal: str, projeto: str, dados: PedidoAmostraVideo) -> dict:
        proj(canal, projeto)
        return {"job": srv.fila.enviar("amostra_video", {"canal": canal, "projeto": projeto, **dados.model_dump()})}

    @app.put("/api/canais/{canal}/estilo-padrao", dependencies=dep)
    def definir_estilo_padrao(canal: str, dados: dict) -> dict:
        c = ws.canal(canal)
        nome = str(dados.get("estilo") or "")
        if nome not in ws.estilos(c):
            raise HTTPException(404, "Estilo não encontrado")
        doc = md.read(c.path / "canal.md")
        meta = dict(doc.meta)
        meta["estilo_padrao"] = nome
        md.write(c.path / "canal.md", meta, doc.body)
        return {"estilo_padrao": nome}

    @app.get("/api/estilos/embutido", dependencies=dep)
    def estilo_embutido(id: str) -> dict:
        p = estilos_embutidos_dir() / f"{id}.md"
        if not p.is_file() or p.parent != estilos_embutidos_dir():
            raise HTTPException(404, "Estilo embutido não encontrado")
        return {"id": id, "conteudo": p.read_text(encoding="utf-8")}

    # ---- thumbnails --------------------------------------------------------
    base_clip = "/api/canais/{canal}/projetos/{projeto}/clips/{clip_id}"

    @app.get(base_clip + "/thumbs", dependencies=dep)
    def listar_thumbs(canal: str, projeto: str, clip_id: str) -> dict:
        p = proj(canal, projeto)
        try:
            info = thumbs.listar(p, clip_id)
        except Exception as exc:
            raise erro(exc) from exc
        info["pasta"] = str(p.clips_dir.relative_to(ws.root) / clip_id).replace("\\", "/")
        return info

    @app.post(base_clip + "/thumbs", dependencies=dep)
    def gerar_thumbs(canal: str, projeto: str, clip_id: str, dados: PedidoThumb) -> dict:
        p = proj(canal, projeto)
        try:
            clip, _ = p.clip(clip_id)
        except Exception as exc:
            raise erro(exc) from exc
        if dados.linhas is not None:
            clip.thumb_frase = [x.strip() for x in dados.linhas if x.strip()]
            p.salvar_clip(clip)
        return {"job": srv.fila.enviar("thumbnail", {"canal": canal, "projeto": projeto, "clip": clip_id,
                                                     "usar_ia": dados.usar_ia})}

    @app.post(base_clip + "/thumbs/ia", dependencies=dep)
    def gerar_thumbs_ia(canal: str, projeto: str, clip_id: str) -> dict:
        proj(canal, projeto).clip(clip_id)
        return {"job": srv.fila.enviar("thumbnail_ia", {"canal": canal, "projeto": projeto, "clip": clip_id})}

    @app.post(base_clip + "/thumbs/escolher", dependencies=dep)
    def escolher_thumb(canal: str, projeto: str, clip_id: str, dados: EscolherThumb) -> dict:
        try:
            alvo = thumbs.escolher(proj(canal, projeto), clip_id, dados.arquivo)
        except Exception as exc:
            raise erro(exc) from exc
        return {"thumb": str(alvo.relative_to(ws.root)).replace("\\", "/")}

    # ---- skills ------------------------------------------------------------
    @app.get("/api/skills", dependencies=dep)
    def listar_skills() -> dict:
        lista, erros = skills.listar(ws)
        ativ = skills.ativacoes(ws)
        return {"skills": [s.para_json(ativ) for s in lista], "erros": erros, "pasta": str(skills.pasta_skills())}

    @app.post("/api/skills/importar", dependencies=dep)
    def importar_skill(dados: ImportarSkill) -> dict:
        origem = dados.origem.strip()
        try:
            if origem.startswith("https://"):
                novas = skills.instalar_github(origem, dados.substituir)
            elif origem.lower().endswith(".zip"):
                novas = skills.instalar_zip(Path(origem), dados.substituir)
            else:
                novas = [skills.instalar_pasta(Path(origem), dados.substituir)]
        except skills.SkillError as exc:
            raise HTTPException(400, str(exc)) from exc
        ativ = ws.config().skills
        return {"skills": [s.para_json(ativ) for s in novas]}

    @app.post("/api/skills/{sid}/ativar", dependencies=dep)
    def ativar_skill(sid: str, dados: AtivarSkill) -> dict:
        try:
            skills.ativar(ws, sid, dados.escopo, dados.canal, dados.projeto)
        except Exception as exc:
            raise erro(exc) from exc
        return {"ok": True}

    @app.post("/api/skills/{sid}/desativar", dependencies=dep)
    def desativar_skill(sid: str, dados: AtivarSkill | None = None) -> dict:
        d = dados or AtivarSkill(escopo="")
        skills.desativar(ws, sid, d.escopo or None, d.canal, d.projeto)
        return {"ok": True}

    @app.post("/api/skills/{sid}/exportar", dependencies=dep)
    def exportar_skill(sid: str, dados: ExportarSkill) -> dict:
        try:
            return {"arquivo": str(skills.exportar_zip(ws, sid, Path(dados.destino)))}
        except Exception as exc:
            raise erro(exc) from exc

    @app.delete("/api/skills/{sid}", dependencies=dep)
    def remover_skill(sid: str, confirmar: bool = False) -> dict:
        if not confirmar:
            raise HTTPException(409, "Confirme para remover (confirmar=true)")
        try:
            skills.remover(ws, sid)
        except Exception as exc:
            raise erro(exc) from exc
        return {"ok": True}

    # ---- jobs --------------------------------------------------------------
    @app.get("/api/jobs", dependencies=dep)
    def jobs() -> list[dict]:
        return srv.fila.listar()

    @app.get("/api/jobs/{jid}", dependencies=dep)
    def job(jid: str) -> dict:
        j = srv.fila.obter(jid)
        if not j:
            raise HTTPException(404, "Job não encontrado")
        return j

    @app.post("/api/jobs/{jid}/cancelar", dependencies=dep)
    def cancelar(jid: str) -> dict:
        return {"ok": srv.fila.cancelar(jid)}

    @app.post("/api/jobs/{jid}/usar-outra-ia", dependencies=dep)
    def usar_outra_ia(jid: str) -> dict:
        return {"ok": srv.fila.usar_outra_ia(jid)}

    @app.websocket("/api/eventos")
    async def eventos(sock: WebSocket) -> None:
        t = sock.query_params.get("token")
        if token and (not t or not secrets.compare_digest(t, token)):
            await sock.close(code=4401)
            return
        await sock.accept()
        loop = asyncio.get_running_loop()
        fila: asyncio.Queue = asyncio.Queue(maxsize=1000)

        def por(j: dict) -> None:
            if fila.full():  # o app parou de ler (aba em segundo plano): descarta o mais velho, não estoura
                fila.get_nowait()
            fila.put_nowait(j)

        def ouvinte(j: dict) -> None:
            try:
                loop.call_soon_threadsafe(por, j)
            except Exception:
                pass

        srv.fila.ouvintes.append(ouvinte)
        try:
            while True:
                j = await fila.get()
                await sock.send_json({"tipo": "job", "job": j})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if ouvinte in srv.fila.ouvintes:
                srv.fila.ouvintes.remove(ouvinte)

    return app


def _vigiar_stdin() -> None:
    """Fecha o motor quando o app que o abriu morre (o stdin chega ao fim)."""
    import sys
    import threading

    def vigia() -> None:
        try:
            while sys.stdin.read(1024):
                pass
        except Exception:
            pass
        os._exit(0)

    threading.Thread(target=vigia, daemon=True, name="clipator-vigia-stdin").start()


def rodar(host: str = "127.0.0.1", porta: int = 8765, workspace: str | None = None, token: str | None = None,
          vigiar_stdin: bool = False) -> None:
    import uvicorn

    if vigiar_stdin:
        _vigiar_stdin()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Por segurança o motor só escuta em 127.0.0.1")
    app = criar_app(Servico(workspace, limpar_erros=True), token)
    # O Electron lê esta linha para saber que o motor subiu.
    print(f"CLIPATOR_PRONTO porta={porta} token={app.state.token}", flush=True)
    uvicorn.run(app, host=host, port=porta, log_level="warning")

