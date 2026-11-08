"""Servidor MCP local (stdio) do Clipator, com o SDK oficial de MCP.

Rode com `clipator mcp`. Não abre porta na rede. Permite fazer tudo pelo
Claude Code, pelo Codex ou por qualquer cliente MCP, por exemplo:
"clipa esse link no canal do podcast, estilo impacto, 5 cortes".

A lista de ferramentas segue o documento de requisitos; a estrutura (um
servidor só, ferramentas finas sobre o motor) foi inspirada em
openshorts/mcp_server.py, MIT License, Copyright (c) 2024 OpenShorts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from . import __version__, markdown as md, pipeline, skills, thumbs, titles as titles_mod, transcribe
from .candidates import texto_do_trecho
from .models import Clip
from .service import Servico
from .workspace import WorkspaceError, slugify, write_json

INSTRUCOES = """Clipator transforma vídeos longos em clips curtos, tudo local.
Fluxo típico: listar_canais -> criar_projeto (link do YouTube/Twitch ou arquivo; já dispara a análise)
-> status_job até 'ok' -> listar_candidatos -> selecionar_cortes -> renderizar -> status_job.
Thumbnail: gerar_thumbnail (job) -> listar_thumbnails -> escolher_thumbnail.
Skills do usuário: listar_skills mostra as ativas; leia clipator://skills/<id> e siga as de fluxo.
Direção de arte: o estilo escolhe a DA (`arte:`), o canal põe a marca (arte_marca); arte_guia mostra o que o estilo usa.\nA DA própria do canal: arte_ler / arte_validar / arte_prancha; aprovar (arte_aprovar) só com o sim da pessoa.
Apagar qualquer coisa exige confirmar=true. Tudo fica dentro do workspace."""


def criar_servidor(servico: Servico | None = None) -> MCPServer:
    srv = servico or Servico(nome_fila="jobs-mcp")
    ws = srv.ws
    mcp = MCPServer("clipator", instructions=INSTRUCOES, version=__version__)

    @mcp.tool()
    def listar_canais() -> list[dict]:
        """Lista os canais do workspace com o número de projetos."""
        out = []
        for c in ws.canais():
            info, _ = c.info()
            out.append({"canal": c.slug, "nome": info.nome, "idioma": info.idioma,
                        "projetos": [p.id for p in c.projetos()]})
        return out

    @mcp.tool()
    def criar_canal(nome: str, idioma: str = "pt", palavras_chave: list[str] | None = None) -> dict:
        """Cria um canal: canal.md e a pasta regras-e-textos/ (regras, títulos, thumb e referências, editáveis).
        A base de referência dos cortes virais vale para todo canal: o tema é detectado a cada vídeo."""
        c = ws.criar_canal(nome, idioma, palavras_chave=palavras_chave or [])
        return {"canal": c.slug, "pasta": str(c.path), "regras_e_textos": str(c.textos_dir)}

    @mcp.tool()
    def temas_do_projeto(canal: str, projeto: str) -> dict:
        """Os temas detectados no vídeo pela transcrição e o trecho da base de referência que vale para ele
        (como cortar, padrões de título e de thumbnail, títulos reais mais vistos)."""
        from . import base_virais

        p = srv.projeto(canal, projeto)
        ids = p.temas()
        return {"temas": base_virais.nomes(ids) or ["geral"],
                "base": base_virais.para_ia(ids, ("cortes", "titulos", "thumbs", "referencias"), 16000)}

    @mcp.tool()
    def criar_projeto(canal: str, origem: str, titulo: str | None = None, analisar: bool = True,
                      modo_ia: str | None = None, corte_longo: bool = True) -> dict:
        """Cria um projeto a partir de um link (YouTube ou Twitch) ou caminho de arquivo e, por padrão,
        já dispara a análise (download, transcrição, sinais, candidatos e ranking). modo_ia: sem-ia,
        economico ou completo."""
        p = pipeline.criar_projeto(ws, ws.canal(canal), origem, titulo)
        job = srv.fila.enviar("analisar", {"canal": canal, "projeto": p.id, "modo_ia": modo_ia,
                                           "corte_longo": corte_longo}) if analisar else None
        return {"projeto": p.id, "job": job}

    @mcp.tool()
    def importar_video(canal: str, projeto: str, origem: str) -> dict:
        """Troca a origem de um projeto existente (link ou arquivo) e reanalisa."""
        p = srv.projeto(canal, projeto)
        meta = p.meta()
        novo = pipeline.criar_projeto(ws, p.canal, origem, meta.titulo).meta().origem
        meta.origem = novo
        p.salvar_meta(meta)
        for f in p.fonte_dir.glob("video.*"):
            f.unlink()
        job = srv.fila.enviar("analisar", {"canal": canal, "projeto": projeto})
        return {"job": job}

    @mcp.tool()
    def status_job(job: str | None = None) -> Any:
        """Status de um job (progresso, mensagem, erro). Sem id, lista os últimos jobs."""
        if job:
            j = srv.fila.obter(job)
            if j:
                j["log"] = (j.get("log") or "")[-2000:]
            return j or {"erro": "job não encontrado"}
        return srv.fila.listar(15)

    @mcp.tool()
    def cancelar_job(job: str) -> dict:
        """Cancela um job na fila ou rodando."""
        return {"ok": srv.fila.cancelar(job)}

    @mcp.tool()
    def ler_transcricao(canal: str, projeto: str, inicio: float | None = None, fim: float | None = None) -> str:
        """Transcrição compacta em frases [início-fim] (opcionalmente só um trecho, em segundos)."""
        from . import pack

        t = srv.projeto(canal, projeto).transcricao()
        if not t:
            return "Ainda sem transcrição"
        return pack.compactar(transcribe.palavras(t), inicio, fim)

    @mcp.tool()
    def corrigir_transcricao(canal: str, projeto: str, correcoes: dict[str, str]) -> dict:
        """Corrige o texto de segmentos da transcrição: {indice_do_segmento: novo_texto}."""
        p = srv.projeto(canal, projeto)
        t = p.transcricao()
        if not t:
            return {"erro": "Ainda sem transcrição"}
        write_json(p.transcricao_path, transcribe.corrigir(t, {int(k): v for k, v in correcoes.items()}))
        return {"ok": True}

    @mcp.tool()
    def listar_candidatos(canal: str, projeto: str, limite: int = 20) -> list[dict]:
        """Candidatos a corte com nota, motivo, títulos sugeridos e texto."""
        cands = srv.projeto(canal, projeto).candidatos()[:limite]
        return [{k: c.get(k) for k in ("id", "inicio", "fim", "duracao", "nota", "motivos", "titulos", "modo", "fonte", "texto")}
                for c in cands]

    @mcp.tool()
    def selecionar_cortes(canal: str, projeto: str, ids: list[str], formato: str | None = None,
                          estilo: str | None = None, cartela: bool | None = None) -> list[dict]:
        """Transforma candidatos em clips. formato: 9:16, 1:1, 4:5 ou 16:9."""
        clips = pipeline.selecionar(srv.projeto(canal, projeto), ids, formato, estilo, cartela)
        return [c.model_dump(mode="json") for c in clips]

    @mcp.tool()
    def ajustar_corte(canal: str, projeto: str, clip: str, inicio: float | None = None, fim: float | None = None,
                      titulo: str | None = None, estilo: str | None = None, formato: str | None = None,
                      cartela: bool | None = None, cortes_internos: list[list[float]] | None = None) -> dict:
        """Ajusta início, fim, título, estilo, formato, cartela ou cortes internos de um clip."""
        p = srv.projeto(canal, projeto)
        atual, _ = p.clip(clip)
        if inicio is not None or fim is not None:
            # mesmo caminho da tela "Editar duração": os itens do editor acompanham a fala
            from . import trecho

            atual = trecho.ajustar(p, clip, atual.inicio if inicio is None else inicio,
                                   atual.fim if fim is None else fim).clip
        dados = atual.model_dump(mode="json")
        for k, v in {"titulo": titulo, "estilo": estilo, "formato": formato,
                     "cartela": cartela, "cortes_internos": cortes_internos}.items():
            if v is not None:
                dados[k] = v
        novo = Clip.model_validate(dados)
        novo.status = "selecionado"
        p.salvar_clip(novo)
        return novo.model_dump(mode="json")

    @mcp.tool()
    def sugerir_titulos(canal: str, projeto: str, clip: str) -> dict:
        """Devolve o texto do clip e as fórmulas do canal para você (a IA) escrever 3 a 5 títulos.
        O título pode exagerar a emoção, mas o que ele promete precisa acontecer no clip."""
        p = srv.projeto(canal, projeto)
        c, _ = p.clip(clip)
        tmeta, tmd = p.titulos()
        regras, _ = p.canal.regras()
        extra = skills.texto_para_ia(ws, "titulos", p.canal.slug, p.id)
        return {"texto": texto_do_trecho(p.transcricao() or {}, c.inicio, c.fim), "formulas": titles_mod.formulas_do_canal(tmeta),
                "instrucoes": "\n\n".join(x for x in (tmd.strip(), p.base_para_ia(("titulos", "referencias")), extra) if x),
                "trava_titulo": regras.trava_titulo,
                "sugeridos": c.titulos_sugeridos}

    @mcp.tool()
    def listar_estilos(canal: str | None = None) -> list[dict]:
        """Estilos disponíveis (embutidos, do workspace e do canal)."""
        c = ws.canal(canal) if canal else None
        out = []
        for nome in ws.estilos(c):
            est, _, path = ws.carregar_estilo(nome, c)
            out.append({"id": nome, "nome": est.nome, "descricao": est.descricao, "formato": est.formato,
                        "motor": est.motor, "nivel_ia": est.nivel_ia, "caminho": str(path)})
        return out

    @mcp.tool()
    def criar_estilo(nome: str, descricao: str, base: str = "podcast-limpo", ajustes: dict | None = None,
                     instrucoes_ia: str = "", canal: str | None = None) -> dict:
        """Cria um estilo .md a partir de um estilo base e de ajustes no cabeçalho (ex.: {"legenda": {"cor": "#FFE600"}}).
        Use listar_estilos e leia um .md existente para ver os campos. O corpo (instrucoes_ia) vai para a IA no nível Assistido."""
        c = ws.canal(canal) if canal else None
        est, corpo, path = ws.carregar_estilo(base, c)
        meta = md.deep_merge(md.read(path).meta, ajustes or {})
        meta["nome"], meta["descricao"] = nome, descricao
        from .models import Estilo

        Estilo.model_validate(meta)
        destino = (c.path if c else ws.root) / "estilos" / f"{slugify(nome)}.md"
        md.write(destino, meta, instrucoes_ia or corpo)
        return {"estilo": destino.stem, "caminho": str(destino)}

    @mcp.tool()
    def ler_edicao(canal: str, projeto: str, clip: str) -> dict:
        """Lê a edição do clip no editor (edicao.json): itens com tipo, inicio, fim (segundos do clip) e params.

        Tipos: zoom, zoom-lento, tremor, flash, pb, sepia, contraste, saturacao, desfoque, vinheta, transicao,
        texto (params.texto, posicao, tamanho, cor, fundo), emoji (params.emoji, posicao, tamanho),
        sticker (params.ref, posicao, tamanho, rotacao, entrada, repetir; "cta:inscreva-se" e as outras chamadas
        aceitam texto, texto2, cor, cor_texto, idioma, preset e som) e som (params.nome, volume). Texto, emoji e
        sticker aceitam x, y (o centro, em fração do quadro), que valem no lugar da posicao.
        Também devolve a duração do clip e os padrões de cada tipo."""
        from . import edicao

        p = srv.projeto(canal, projeto)
        _, pasta = p.clip(clip)
        return {**edicao.carregar(pasta).model_dump(mode="json"), "duracao": edicao.duracao_do_clip(p, clip),
                "padrao": edicao.PADRAO}

    @mcp.tool()
    def aplicar_edicao(canal: str, projeto: str, clip: str, adicionar: list[dict] | None = None,
                       remover: list[str] | None = None, substituir_tudo: bool = False) -> dict:
        """Muda a edição do clip: adiciona itens ({tipo, inicio, fim, params, motivo}), remove pelo id ou,
        com substituir_tudo, troca a lista inteira por `adicionar`. O editor do app recarrega sozinho.
        Os tempos são validados contra a duração do clip. Depois, rode `renderizar` para ver o resultado."""
        from . import edicao

        p = srv.projeto(canal, projeto)
        _, pasta = p.clip(clip)
        atual = edicao.carregar(pasta)
        itens = [] if substituir_tudo else [i for i in atual.itens if i.id not in set(remover or [])]
        novos = [{**x, "origem": "ia"} for x in (adicionar or []) if isinstance(x, dict)]
        from . import melhorar

        melhorar.garantir_inicial(p, clip)
        ed = edicao.salvar(pasta, atual.model_copy(update={"itens": itens + novos}), edicao.duracao_do_clip(p, clip))
        n = melhorar.registrar(p, clip, "mcp")  # o usuário compara e desfaz no passo 4
        return {"revisao": ed.revisao, "itens": len(ed.itens), "versao": n}

    @mcp.tool()
    def escolher_composicao(canal: str, projeto: str, clip: str, layout: str, janela_canto: str | None = None,
                            janela_escala: float | None = None, proporcao: float | None = None, janela_encaixe: str | None = None) -> dict:
        """Escolhe como animação e vídeo dividem a tela neste clip. layout: em-cima (tela dividida; proporcao 0.5 é meio a meio) ou
        janela (animação na tela inteira e vídeo num canto). janela_canto: inferior-direito, inferior-esquerdo, superior-direito
        ou superior-esquerdo. janela_encaixe: enquadrar ou barras. Fica salvo na edição, vira uma versão; depois chame renderizar."""
        from . import artes

        return artes.ajustar_layout(srv.projeto(canal, projeto), clip, {
            "layout": layout, "janela_canto": janela_canto, "janela_escala": janela_escala, "proporcao": proporcao, "janela_encaixe": janela_encaixe})

    @mcp.tool()
    def renderizar(canal: str, projeto: str, clips: list[str], preview: bool = False) -> dict:
        """Renderiza clips (MP4, legenda ASS e postagem.txt). Devolve o id do job."""
        return {"job": srv.fila.enviar("renderizar", {"canal": canal, "projeto": projeto, "clips": clips, "preview": preview})}

    @mcp.tool()
    def gerar_thumbnail(canal: str, projeto: str, clip: str, linhas: list[str] | None = None,
                        por_imagem: bool = False) -> dict:
        """Gera variações de thumbnail 1280x720 (4 layouts x 3 quadros) por código. Devolve o id do job.
        linhas: a frase-gancho (2 a 4 linhas curtas); sem ela, a IA configurada ou o título montam a frase.
        por_imagem=true pede variações ao Codex ($imagegen, exige ChatGPT Plus) sobre o quadro real."""
        p = srv.projeto(canal, projeto)
        c, _ = p.clip(clip)
        if linhas:
            c.thumb_frase = [x.strip() for x in linhas if x.strip()]
            p.salvar_clip(c)
        tipo = "thumbnail_ia" if por_imagem else "thumbnail"
        return {"job": srv.fila.enviar(tipo, {"canal": canal, "projeto": projeto, "clip": clip})}

    @mcp.tool()
    def listar_thumbnails(canal: str, projeto: str, clip: str) -> dict:
        """Variações de thumbnail já geradas para o clip, com a pasta onde estão."""
        p = srv.projeto(canal, projeto)
        info = thumbs.listar(p, clip)
        info["pasta"] = str(p.clips_dir / clip / "thumbs")
        return info

    @mcp.tool()
    def escolher_thumbnail(canal: str, projeto: str, clip: str, arquivo: str) -> dict:
        """Copia a variação escolhida (ex.: rosto-frase-1.png) para clips/<clip>/thumb.png."""
        return {"thumb": str(thumbs.escolher(srv.projeto(canal, projeto), clip, arquivo))}

    @mcp.tool()
    def listar_skills(canal: str | None = None, projeto: str | None = None) -> dict:
        """Skills do usuário instaladas e as que valem neste canal/projeto. Leia clipator://skills/<id> para as instruções."""
        lista, erros = skills.listar(ws)
        ativas = {s.id for s in skills.ativas(ws, canal, projeto)}
        return {"skills": [{"id": s.id, "nome": s.manifesto.nome, "tipos": list(s.manifesto.tipos),
                            "descricao": s.manifesto.descricao, "ativa_aqui": s.id in ativas} for s in lista],
                "erros": erros}

    @mcp.tool()
    def ativar_skill(skill: str, escopo: str = "global", canal: str | None = None, projeto: str | None = None) -> dict:
        """Ativa uma skill instalada no workspace inteiro (global), num canal ou num projeto."""
        skills.ativar(ws, skill, escopo, canal, projeto)
        return {"ok": True}

    @mcp.tool()
    def abrir_preview(canal: str, projeto: str, clip: str, abrir: bool = False) -> dict:
        """Caminho do vídeo renderizado do clip; com abrir=true, abre no player do sistema."""
        p = srv.projeto(canal, projeto)
        _, pasta = p.clip(clip)
        alvo = next((x for x in (pasta / "saida.mp4", pasta / "preview.mp4") if x.exists()), None)
        if alvo is None:
            return {"erro": "Clip ainda não renderizado"}
        if abrir:
            if sys.platform.startswith("win"):
                os.startfile(str(alvo))  # type: ignore[attr-defined]  # noqa: S606
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(alvo)])  # noqa: S603
        return {"caminho": str(alvo)}

    @mcp.tool()
    def apagar_clip(canal: str, projeto: str, clip: str, confirmar: bool = False) -> dict:
        """Apaga a pasta de um clip. Exige confirmar=true."""
        if not confirmar:
            return {"erro": "Apagar exige confirmar=true. Pergunte ao usuário antes."}
        try:
            srv.projeto(canal, projeto).remover_clip(clip)
        except WorkspaceError as exc:
            return {"erro": str(exc)}
        return {"ok": True}

    # ---- direção de arte do canal ---------------------------------------------------
    def _arte(canal: str):
        return ws.canal(canal).path

    @mcp.tool()
    def arte_presets() -> list[dict]:
        """Predefinidos de direção de arte (de fábrica e pessoais), com a frase de cada um."""
        from .arte import servico as arte

        return arte.presets()

    @mcp.tool()
    def arte_criar(canal: str, base: str = "base", nome: str = "", forcar: bool = False) -> dict:
        """Cria arte/direcao.yaml do canal herdando de um predefinido. Não sobrescreve sem forcar=true."""
        from .arte import servico as arte

        return arte.criar(_arte(canal), base, nome, forcar)

    @mcp.tool()
    def arte_ler(canal: str) -> str:
        """A DA do canal resolvida, em Markdown: paleta, tipografia, legenda, movimento, situação e achados."""
        from .arte import servico as arte

        return arte.mostrar(_arte(canal))

    @mcp.tool()
    def arte_token(canal: str, caminho: str) -> Any:
        """Valor de um token (ex.: cor.paleta.primaria, legenda.tamanho ou só 'primaria')."""
        from .arte import servico as arte

        return arte.token(_arte(canal), caminho)

    @mcp.tool()
    def arte_validar(canal: str) -> dict:
        """Valida a DA: contraste WCAG, legibilidade no celular, zonas seguras, fontes, movimento. Devolve achados."""
        from .arte import servico as arte, validar as v

        _, achados = arte.validar(_arte(canal))
        e, a, n = v.resumo(achados)
        return {"erros": e, "avisos": a, "notas": n, "achados": [x.para_dict() for x in achados]}

    @mcp.tool()
    def arte_compilar(canal: str) -> dict:
        """Gera arte/build (da.css, da.resolvida.json) e arte/DA.md a partir do direcao.yaml."""
        from .arte import servico as arte

        return arte.compilar(_arte(canal))

    @mcp.tool()
    def arte_extrair_referencias(canal: str, arquivos: list[str] | None = None, quadros: int = 6) -> dict:
        """Lê imagens/vídeos de referência (padrão: arte/referencias) e propõe cores candidatas a token."""
        from pathlib import Path as _P

        from .arte import servico as arte

        return arte.extrair(_arte(canal), [_P(a) for a in arquivos] if arquivos else None, quadros)

    @mcp.tool()
    def arte_prancha(canal: str, referencia: str | None = None, estilo: str | None = None) -> dict:
        """Gera a prancha de estilo para a pessoa ver. Sem `estilo`: a DA do canal (arte/prancha.png, a que se
        aprova). Com `estilo`: a DA que esse estilo usa, com a marca do canal por cima. Mostre a imagem a ela."""
        from pathlib import Path as _P

        from .arte import servico as arte

        c = ws.canal(canal)
        est = ws.carregar_estilo(estilo, c)[0] if estilo else None
        return arte.prancha(c.path, _P(referencia) if referencia else None, est)

    @mcp.tool()
    def arte_guia(canal: str, estilo: str) -> dict:
        """A direção de arte que um estilo usa neste canal (com a marca do canal por cima) e o texto que a IA
        recebe ao planejar as cenas do corte: tom, tipos de cena, ritmo e limites de texto."""
        from .arte import servico as arte

        c = ws.canal(canal)
        return arte.guia_do_estilo(c.path, ws.carregar_estilo(estilo, c)[0])

    @mcp.tool()
    def arte_marca(canal: str, criar: bool = False) -> dict:
        """A marca do canal (arte/marca.yaml: cores da marca, fontes e logo), que vai por cima da DA de cada
        estilo. Com criar=true, escreve o modelo se ainda não existir."""
        from .arte import servico as arte

        return arte.marca(_arte(canal), criar)

    @mcp.tool()
    def arte_rotas(canal: str, acao: str = "listar", nome: str | None = None, base: str | None = None,
                   frase: str = "", primaria: str | None = None, ajustes: dict | None = None,
                   com_atual: bool = False) -> Any:
        """Rotas candidatas de DA. acao: criar (nome, base, frase, primaria, ajustes), listar, comparar
        (gera arte/rotas/comparacao.png) ou adotar (nome; só depois que a pessoa escolher)."""
        from .arte import rotas
        from .arte.carregar import pasta_do_canal

        pasta = pasta_do_canal(_arte(canal))
        if acao == "criar":
            if not nome:
                return {"erro": "Diga o nome da rota (ex.: rota-a)"}
            res = rotas.criar(pasta, nome, base, frase, primaria, ajustes)
            return {"arquivo": res["arquivo"], "achados": [a.para_dict() for a in res["achados"]]}
        if acao == "listar":
            return rotas.listar(pasta)
        if acao == "comparar":
            return {"imagem": str(rotas.comparar(pasta, [nome] if nome else None, com_atual))}
        if acao == "adotar":
            if not nome:
                return {"erro": "Diga qual rota adotar"}
            return rotas.adotar(pasta, nome)
        return {"erro": "acao: criar, listar, comparar ou adotar"}

    @mcp.tool()
    def arte_aprovar(canal: str, confirmar: bool = False, estrito: bool = False) -> dict:
        """Aprova a DA atual (registra o sha e carimba a prancha). Exige confirmar=true: só a pessoa aprova."""
        from .arte import servico as arte

        if not confirmar:
            return {"erro": "Aprovar exige confirmar=true. Mostre a prancha e pergunte à pessoa antes."}
        return arte.aprovar(_arte(canal), estrito, "mcp")

    @mcp.tool()
    def arte_revisar(canal: str, motivo: str = "") -> dict:
        """Abre uma nova revisão da DA (ela volta a precisar de aprovação)."""
        from .arte import servico as arte

        return arte.revisar(_arte(canal), motivo)

    @mcp.tool()
    def arte_conferir(canal: str) -> dict:
        """Conferência antes de publicar: DA válida e aprovada, estilos sem cor solta, clips com a DA atual."""
        from .arte import servico as arte

        return arte.conferir(_arte(canal), ws.estilos_dir)

    @mcp.tool()
    def arte_lint(canal: str, arquivos: list[str] | None = None) -> dict:
        """Procura cor e fonte escritas à mão nos estilos (deveriam ser tokens da DA)."""
        from pathlib import Path as _P

        from .arte import servico as arte

        res = arte.lint(_arte(canal), ws.estilos_dir, [_P(a) for a in arquivos] if arquivos else None)
        return {**res, "violacoes": [v.__dict__ for v in res["violacoes"]]}

    # ---- recursos ---------------------------------------------------------------
    @mcp.resource("clipator://canais/{canal}/canal.md")
    def recurso_canal(canal: str) -> str:
        return (ws.canal(canal).path / "canal.md").read_text(encoding="utf-8")

    @mcp.resource("clipator://canais/{canal}/regras.md")
    def recurso_regras(canal: str) -> str:
        c = ws.canal(canal)
        return (c._ler("regras.md") or c.arquivo("regras.md")).read_text(encoding="utf-8")

    @mcp.resource("clipator://canais/{canal}/titulos.md")
    def recurso_titulos(canal: str) -> str:
        c = ws.canal(canal)
        return (c._ler("titulos.md") or c.arquivo("titulos.md")).read_text(encoding="utf-8")

    @mcp.resource("clipator://canais/{canal}/referencias.md")
    def recurso_referencias(canal: str) -> str:
        return ws.canal(canal).referencias()

    @mcp.resource("clipator://estilos/{estilo}")
    def recurso_estilo(estilo: str) -> str:
        return ws.estilos()[estilo].read_text(encoding="utf-8")

    @mcp.resource("clipator://skills/{skill}")
    def recurso_skill(skill: str) -> str:
        s = skills.obter(ws, skill)
        return f"# {s.manifesto.nome}\n\n{s.instrucoes}"

    @mcp.resource("clipator://arte/metodo")
    def recurso_arte_metodo() -> str:
        from pathlib import Path as _P

        return (_P(__file__).parent / "dados" / "arte" / "metodo.md").read_text(encoding="utf-8")

    @mcp.resource("clipator://canais/{canal}/arte/DA.md")
    def recurso_arte_da(canal: str) -> str:
        from .arte import servico as arte

        return arte.mostrar(ws.canal(canal).path)

    @mcp.resource("clipator://canais/{canal}/projetos/{projeto}/candidatos.json")
    def recurso_candidatos(canal: str, projeto: str) -> str:
        p = srv.projeto(canal, projeto)
        return p.candidatos_path.read_text(encoding="utf-8") if p.candidatos_path.exists() else "[]"

    return mcp


def rodar(workspace: str | None = None) -> None:
    criar_servidor(Servico(workspace, nome_fila="jobs-mcp")).run("stdio")
