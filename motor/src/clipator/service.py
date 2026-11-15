"""Serviço do Clipator: o workspace mais a fila de jobs, usado pela API, pelo MCP e pela CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import edicao_ia, ingest, pipeline, postagem, thumbs
from .ai.adapter import logado_na_cli
from .jobs import ContextoJob, FilaJobs
from .workspace import ProjetoWS, Workspace


def workspace_padrao() -> Path:
    env = os.environ.get("CLIPATOR_WORKSPACE")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Clipator"


class Servico:
    def __init__(self, raiz: str | Path | None = None, workers: int = 1, nome_fila: str = "jobs",
                 limpar_erros: bool = False):
        """limpar_erros: só o motor do app usa, ao subir. Apaga os jobs com erro e os logs da fila
        e volta para pendente as etapas que ficaram em erro nos projetos."""
        self.ws = Workspace(raiz or workspace_padrao())
        if not self.ws.existe():
            self.ws.init()
        if limpar_erros:
            for canal in self.ws.canais():
                for proj in canal.projetos():
                    proj.limpar_erros()
        self.fila = FilaJobs(self.ws.root / ".clipator" / f"{nome_fila}.sqlite3", workers=workers, limpar=limpar_erros)
        self.fila.registrar("analisar", self._job_analisar)
        self.fila.registrar("renderizar", self._job_renderizar)
        self.fila.registrar("ranquear", self._job_ranquear)
        self.fila.registrar("transcrever", self._job_transcrever)
        self.fila.registrar("candidatos", self._job_candidatos)
        self.fila.registrar("thumbnail", self._job_thumbnail)
        self.fila.registrar("postagem", self._job_postagem)
        self.fila.registrar("efeitos_ia", self._job_efeitos_ia)
        self.fila.registrar("stickers", self._job_stickers)
        self.fila.registrar("fontes", self._job_fontes)
        self.fila.registrar("amostras_estilo", self._job_amostras_estilo)
        self.fila.registrar("melhorar_edicao", self._job_melhorar_edicao)
        self.fila.registrar("refazer_direcao", self._job_refazer_direcao)
        self.fila.registrar("ajustar_arte", self._job_ajustar_arte)
        self.fila.registrar("revisao", self._job_revisao)
        self.fila.registrar("amostra_video", self._job_amostra_video)
        self.fila.registrar("conta_youtube", self._job_conta_youtube)
        self.fila.registrar("firefox_youtube", self._job_firefox_youtube)
        self.fila.registrar("thumbnail_ia", self._job_thumbnail_ia)
        self.fila.registrar("acabamento", self._job_acabamento)
        self.fila.registrar("checagem", self._job_checagem)

    def projeto(self, canal: str, projeto: str) -> ProjetoWS:
        return self.ws.canal(canal).projeto(projeto)

    @staticmethod
    def _esperar_login(ctx: ContextoJob):
        """Quando a IA perde o login no meio de um job, ele espera o usuário entrar em vez de trocar de IA."""
        return lambda nome: ctx.esperar_login(nome, lambda: bool(logado_na_cli(nome)))

    # ---- handlers ---------------------------------------------------------------
    def _job_analisar(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        if p.get("refazer"):
            ctx.log("refazendo a análise (o vídeo baixado, a transcrição e os clips ficam)")
            proj.limpar_analise()
        # cookies do YouTube: o navegador escolhido agora no aviso vale já na 1ª tentativa; o das
        # Configurações só entra se o YouTube pedir login
        escolhido = p.get("cookies_navegador")
        cfg = self.ws.config().youtube
        try:
            cookies = (ingest.opcoes_cookies(escolhido) if escolhido
                       else ingest.opcoes_cookies(cfg.cookies_navegador or None, cfg.cookies_arquivo or None))
        except ingest.ErroCookies as exc:
            if escolhido:
                raise
            ctx.log(f"cookies das Configurações ignorados: {exc}")
            cookies = {}
        cands = pipeline.analisar(proj, ctx.progresso, ctx.cancelar, p.get("modo_ia"), ctx.log, bool(p.get("corte_longo", True)),
                                  esperar_login=self._esperar_login(ctx),
                                  etapa=lambda g, m, nome, f: ctx.progresso(g, m, nome, f),
                                  cookies=cookies, cookies_primeiro=bool(escolhido))
        return {"candidatos": len(cands)}

    def _job_transcrever(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        pipeline.transcrever(proj, ctx.progresso, ctx.cancelar, forcar=bool(p.get("forcar")), modelo=p.get("modelo"))
        return {"ok": True}

    def _job_candidatos(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        cands = pipeline.gerar_candidatos(proj, p.get("modo", "curto"))
        return {"candidatos": len(cands)}

    def _job_ranquear(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        cands = pipeline.ranquear(proj, p.get("modo_ia"), p.get("agente"), ctx.progresso, ctx.cancelar, ctx.log,
                                  self._esperar_login(ctx))
        return {"candidatos": len(cands)}

    def _job_renderizar(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        ids = p.get("clips") or [p["clip"]]
        saidas = []
        for n, cid in enumerate(ids):
            ctx.log(f"renderizando {cid}")

            ultima = {"m": ""}

            def prog(f: float, m: str, n=n, cid=cid) -> None:
                # cada etapa nova entra no log (a tela mostra a lista); o contador "pensando… 12 s" só na mensagem
                base = m.split("…")[0].split(" (")[0]
                if base and base != ultima["m"] and "pensando" not in m and "…" not in m:
                    ultima["m"] = base
                    ctx.log(f"• {m}")
                ctx.progresso((n + f) / len(ids), f"{cid}: {m}", cid, f)

            r = pipeline.renderizar(proj, cid, bool(p.get("preview")), prog, ctx.cancelar, p.get("versao"), ctx.log)
            if r.aviso:
                ctx.log(r.aviso)
            saidas.append(str(r.video.relative_to(self.ws.root)))
        out: dict[str, Any] = {"saidas": saidas}
        if not p.get("preview"):
            out.update(self._conversa_do_lote(proj, ids, ctx))
        return out

    def _conversa_do_lote(self, proj: ProjetoWS, ids: list[str], ctx: ContextoJob) -> dict[str, Any]:
        """Clips com pedido para a IA marcado "abrir quando o render terminar": um lote por CLI.

        O motor só prepara o lote; quem abre a conversa é o app (terminal embutido ou externo).
        """
        por_agente: dict[str, list[str]] = {}
        for cid in ids:
            clip, _ = proj.clip(cid)
            ped = clip.pedido_ia
            if ped and ped.abrir_ao_terminar and not ped.enviado:
                por_agente.setdefault(ped.agente, []).append(cid)
        out: dict[str, Any] = {}
        for agente, cids in por_agente.items():
            try:
                r = edicao_ia.abrir_lote(proj, cids, agente, lancar=False)
                ctx.log(f"pedido para o {edicao_ia.NOMES[agente]} pronto para {len(cids)} clip(s): {r['pasta']}")
                out.setdefault("conversas_ia", []).append(r)
            except Exception as exc:  # noqa: BLE001 - o render deu certo; a falha fica no clip e no log
                ctx.log(f"não consegui abrir o {edicao_ia.NOMES.get(agente, agente)}: {exc}")
                out.setdefault("erros_ia", []).append(str(exc))
        return out

    def _job_conta_youtube(self, p: dict, ctx: ContextoJob) -> Any:
        """Abre o navegador do Clipator para o usuário entrar no YouTube; ao conectar, retoma o download pedido."""
        from . import contayt

        r = contayt.entrar(ctx.progresso, ctx.cancelar)
        if r.get("conectada") and p.get("canal") and p.get("projeto"):
            r["job"] = self.fila.enviar("analisar", {"canal": p["canal"], "projeto": p["projeto"]})
            ctx.log("conta do YouTube conectada; o download recomeçou")
        return r

    def _job_firefox_youtube(self, p: dict, ctx: ContextoJob) -> Any:
        """Último recurso: instala o Firefox se faltar, abre o YouTube nele e passa a usar os cookies dele."""
        from . import contayt
        from .workspace import write_yaml

        r = contayt.usar_firefox(ctx.progresso, ctx.cancelar)
        if r.get("cancelado"):
            return r
        cfg = self.ws.config()
        cfg.youtube.cookies_navegador = "firefox"
        write_yaml(self.ws.config_path, cfg.model_dump(mode="json"))
        if p.get("canal") and p.get("projeto"):
            r["job"] = self.fila.enviar("analisar", {"canal": p["canal"], "projeto": p["projeto"], "cookies_navegador": "firefox"})
        return r

    def _job_acabamento(self, p: dict, ctx: ContextoJob) -> Any:
        """Música de fundo e ajustes de imagem em cima do clip gerado (vira uma versão do clip)."""
        from . import acabamento

        ac = acabamento.Acabamento.model_validate(p.get("ajustes") or {})
        ctx.progresso(0.02, "aplicando o acabamento")
        return acabamento.aplicar(self.projeto(p["canal"], p["projeto"]), p["clip"], ac, ctx.progresso, ctx.cancelar)

    def _job_checagem(self, p: dict, ctx: ContextoJob) -> Any:
        """Checagem de fatos (passo 4): o que os cortes citam e a fonte de cada um. A IA é opcional."""
        from . import checagem
        from .ai.adapter import CacheIA
        from .melhorar import ia_do_workspace

        proj = self.projeto(p["canal"], p["projeto"])
        ad = ia_do_workspace(self.ws, self._esperar_login(ctx)) if p.get("usar_ia", True) else None
        ch = checagem.identificar(proj, list(p.get("candidatos") or []), ad, ctx.progresso, ctx.cancelar,
                                  cache=CacheIA(proj.analise_dir / "cache_ia"))
        for a in ch.avisos:
            ctx.log(a)
        return checagem.resumo(ch)

    def _job_revisao(self, p: dict, ctx: ContextoJob) -> Any:
        """Revisão antes de publicar (nota e o que corrigir); sem IA, pelas regras."""
        from . import revisao

        ctx.progresso(0.1, "revisando o clip")
        return revisao.revisar(self.projeto(p["canal"], p["projeto"]), p["clip"], usar_ia=bool(p.get("usar_ia", True)),
                               cancelar=ctx.cancelar)

    def _job_melhorar_edicao(self, p: dict, ctx: ContextoJob) -> Any:
        """Melhorar com IA: uma versão nova da edição do clip (a IA segue o estilo e o pedido)."""
        from . import melhorar

        proj = self.projeto(p["canal"], p["projeto"])
        ctx.progresso(0.1, "pedindo a edição à IA")
        from .relato import Relato

        rel = Relato(ctx.log, lambda m: ctx.progresso(0.3, m))
        r = melhorar.melhorar(proj, p["clip"], str(p.get("feedback") or ""), cancelar=ctx.cancelar,
                              esperar_login=self._esperar_login(ctx), relato=rel)
        if p.get("previa", True):
            rel.passo(f"versão v{r['versao']} gravada; renderizando a prévia")
            ctx.progresso(0.6, "renderizando a prévia da versão nova")
            pipeline.renderizar(proj, p["clip"], True, lambda f, m: ctx.progresso(0.6 + 0.4 * f, m), ctx.cancelar, log=ctx.log)
            rel.passo("prévia pronta")
        return r

    def _job_refazer_direcao(self, p: dict, ctx: ContextoJob) -> Any:
        """"Refazer com esta direção": o desenho (ou as cenas) de novo numa versão nova, e o vídeo renderizado com ela."""
        from . import desenho
        from .relato import Relato

        proj = self.projeto(p["canal"], p["projeto"])
        rel = Relato(ctx.log, lambda m: ctx.progresso(0.2, m))
        ctx.progresso(0.05, "refazendo a direção de arte")
        r = desenho.refazer(proj, p["clip"], p.get("roteiro"), p.get("cores"), bool(p.get("tudo")), relato=rel, cancelar=ctx.cancelar,
                            ad=None)
        rel.passo(f"versão v{r['versao']} gravada; renderizando o vídeo com a direção nova")
        res = pipeline.renderizar(proj, p["clip"], False, lambda f, m: ctx.progresso(0.5 + 0.5 * f, m), ctx.cancelar, log=ctx.log)
        rel.passo("vídeo pronto")
        return {**r, "saida": str(res.video.relative_to(self.ws.root))}

    def _job_ajustar_arte(self, p: dict, ctx: ContextoJob) -> Any:
        """O painel da direção de arte: grava a versão e renderiza o vídeo com ela. Sem IA."""
        from . import artes

        proj = self.projeto(p["canal"], p["projeto"])
        ctx.progresso(0.05, "gravando a direção de arte")
        r = artes.ajustar(proj, p["clip"], p.get("cenas"), p.get("parametros"), p.get("cores"), p.get("composicao"))
        ctx.log(f"versão v{r['versao']} gravada; renderizando o vídeo")
        res = pipeline.renderizar(proj, p["clip"], False, lambda f, m: ctx.progresso(0.1 + 0.9 * f, m), ctx.cancelar, log=ctx.log)
        return {**r, "saida": str(res.video.relative_to(self.ws.root))}

    def _job_amostras_estilo(self, p: dict, ctx: ContextoJob) -> Any:
        """Amostras dos estilos no vídeo neutro, uma depois da outra (as que já estão em cache passam direto)."""
        from . import amostras

        c = self.ws.canal(p["canal"]) if p.get("canal") else None
        nomes = p.get("estilos") or list(self.ws.estilos(c))
        prontas, erros = {}, {}
        for k, nome in enumerate(nomes):
            if ctx.cancelar.is_set():
                break
            ctx.progresso(k / max(1, len(nomes)), f"amostra do estilo {nome}")
            try:
                prontas[nome] = amostras.gerar(self.ws, nome, c, p.get("ajustes"), p.get("formato"), cancelar=ctx.cancelar).name
            except Exception as exc:  # noqa: BLE001 - um estilo quebrado não para os outros
                erros[nome] = str(exc)[:300]
                ctx.log(f"amostra de {nome}: {exc}")
        return {"prontas": prontas, "erros": erros}

    def _job_amostra_video(self, p: dict, ctx: ContextoJob) -> Any:
        """Prévia exata do estilo com alguns segundos de um corte do projeto."""
        from . import amostras

        proj = self.projeto(p["canal"], p["projeto"])
        ctx.progresso(0.05, f"prévia com o estilo {p['estilo']}")
        caminho = amostras.gerar_com_video(proj, p["candidato"], p["estilo"], p.get("ajustes"), p.get("formato"),
                                           progresso=lambda f, m: ctx.progresso(0.05 + 0.9 * f, m), cancelar=ctx.cancelar,
                                           log=ctx.log)
        return {"caminho": caminho.relative_to(self.ws.root).as_posix(), "estilo": p["estilo"]}

    def _job_stickers(self, p: dict, ctx: ContextoJob) -> Any:
        """Baixa o pacote de stickers (só o que falta; confere o sha256 de cada arquivo)."""
        from . import stickers

        return stickers.instalar(lambda f, m: ctx.progresso(f, m))

    def _job_fontes(self, p: dict, ctx: ContextoJob) -> Any:
        """Baixa todas as fontes do pacote do Google Fonts que faltam (confere o sha256)."""
        from . import fontes

        return fontes.instalar(lambda f, m: ctx.progresso(f, m))

    def _job_efeitos_ia(self, p: dict, ctx: ContextoJob) -> Any:
        """Propostas de efeitos para o editor (a IA pelo adaptador; sem IA, as regras simples)."""
        from . import edicao

        proj = self.projeto(p["canal"], p["projeto"])
        ctx.progresso(0.1, "pedindo os efeitos à IA" if p.get("usar_ia", True) else "aplicando as regras")
        if not p.get("usar_ia", True):
            clip, _ = proj.clip(p["clip"])
            from .timeline import Timeline

            tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
            modo, idioma = edicao.chamada_do_canal(proj)
            pals = edicao.palavras_do_clip(proj, tl)
            itens = edicao.heuristica(pals, tl, chamada=modo, idioma=idioma) + edicao.cenas_sugeridas(proj, clip, tl, pals)[0]
            itens = edicao.validar(itens, tl.duracao)
            return {"propostas": [i.model_dump() for i in itens],
                    "fonte": "heuristica"}
        return edicao.sugerir_ia(proj, p["clip"], ctx.cancelar, self._esperar_login(ctx))

    def _job_postagem(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        ctx.progresso(0.1, "escrevendo a postagem" + (" com a IA" if p.get("usar_ia") else ""))
        pacotes = postagem.gerar(proj, p["clip"], bool(p.get("usar_ia")), ctx.cancelar, self._esperar_login(ctx))
        return {"plataformas": list(pacotes)}

    def _job_thumbnail(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        info = thumbs.gerar(proj, p["clip"], bool(p.get("usar_ia", True)), ctx.progresso, ctx.cancelar,
                            self._esperar_login(ctx))
        return {"variacoes": len(info["variacoes"]), "frase": info["linhas"]}

    def _job_thumbnail_ia(self, p: dict, ctx: ContextoJob) -> Any:
        proj = self.projeto(p["canal"], p["projeto"])
        return {"imagens": thumbs.gerar_com_imagem(proj, p["clip"], int(p.get("quantidade", 2)), ctx.progresso, ctx.cancelar)}
