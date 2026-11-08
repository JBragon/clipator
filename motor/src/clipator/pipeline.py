"""As etapas do Clipator, cada uma gravando seu resultado em arquivo.

Etapas: ingestao -> transcricao -> sinais -> candidatos -> ranking (opcional)
-> seleção pelo usuário -> render. Cada etapa pula se o resultado já existe no
disco (a menos que forcar=True), então dá para refazer só a que mudou.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from . import candidates, glossario, ingest, media, render, signals, skills, titles, transcribe
from .ai.adapter import CacheIA, ErroIA, adaptador_com_reserva
from .ai import ranking as ia_ranking
from .media import Cancelado, Progress
from .models import Clip, Origem, PedidoIA
from .textutil import termos_relevantes
from .workspace import CanalWS, ProjetoWS, Workspace, read_json, write_json

Log = Callable[[str], None]


def _nada(*_a, **_k) -> None:
    return None


class Etapa:
    """Marca o status da etapa no projeto.yaml, inclusive em erro e cancelamento."""

    def __init__(self, projeto: ProjetoWS, nome: str):
        self.projeto, self.nome = projeto, nome

    def __enter__(self) -> "Etapa":
        self.projeto.marcar(self.nome, "rodando")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is None:
            self.projeto.marcar(self.nome, "ok")
        elif isinstance(exc, Cancelado):
            self.projeto.marcar(self.nome, "cancelado")
        else:
            self.projeto.marcar(self.nome, "erro", str(exc)[:1000])
        return False


def criar_projeto(ws: Workspace, canal: CanalWS, origem: str, titulo: str | None = None) -> ProjetoWS:
    if ingest.eh_link(origem):
        ingest.validar_link(origem)
        o = Origem(tipo="link", valor=origem)
    else:
        o = Origem(tipo="arquivo", valor=origem)
    return canal.criar_projeto(titulo or ("vídeo" if o.tipo == "link" else origem.rsplit("/", 1)[-1].rsplit(".", 1)[0]), o)


def ingerir(projeto: ProjetoWS, progresso: Progress = _nada, cancelar: threading.Event | None = None,
            forcar: bool = False, opcoes_ytdlp: dict | None = None, cookies: dict | None = None,
            cookies_primeiro: bool = False, log: Log | None = None) -> None:
    meta = projeto.meta()
    if meta.origem is None:
        raise ingest.IngestaoError("O projeto não tem origem (link ou arquivo)")
    if projeto.video_path() is not None and projeto.audio_path.exists() and not forcar:
        return
    with Etapa(projeto, "ingestao"):
        if projeto.video_path() is None or forcar:
            if meta.origem.tipo == "link":
                ingest.baixar(meta.origem.valor, projeto, lambda f, m: progresso(0.85 * f, m), cancelar, opcoes_ytdlp,
                              cookies, cookies_primeiro, log)
            else:
                ingest.importar_arquivo(meta.origem.valor, projeto)
        video = projeto.video_path()
        assert video is not None
        info = media.probe(video)
        md = projeto.metadados()
        if md.get("titulo") and meta.titulo in ("vídeo", ""):
            meta = projeto.meta()
            meta.titulo = md["titulo"]
            projeto.salvar_meta(meta)
        md.update({"midia": info.as_dict()})
        write_json(projeto.metadados_path, md)
        media.extrair_audio(video, projeto.audio_path, progresso=lambda f, m: progresso(0.85 + 0.15 * f, m), cancelar=cancelar)


def transcrever(projeto: ProjetoWS, progresso: Progress = _nada, cancelar: threading.Event | None = None,
                forcar: bool = False, modelo: str | None = None, idioma: str | None = None) -> dict:
    if projeto.transcricao_path.exists() and not forcar:
        return projeto.transcricao() or {}
    cfg = projeto.ws.config()
    canal, _ = projeto.canal.info()
    lang = idioma or (canal.idioma if canal.idioma != "auto" else cfg.whisper.idioma)
    with Etapa(projeto, "transcricao"):
        t = transcribe.transcrever(projeto.audio_path, modelo or cfg.whisper.modelo, cfg.whisper.dispositivo,
                                   lang, progresso, cancelar, hotwords=glossario.hotwords(_glossario(projeto, canal)))
        t, _ = glossario.corrigir_transcricao(t, _glossario(projeto, canal))
        write_json(projeto.transcricao_path, t)
    return t


def corrigir_nomes(projeto: ProjetoWS) -> list[dict]:
    """Passa o glossário do canal numa transcrição que já existe, sem transcrever de novo.

    O texto dos candidatos é refeito com os nomes certos (os tempos não mudam).
    """
    trans = projeto.transcricao()
    if not trans:
        raise RuntimeError("Transcreva o vídeo antes de corrigir os nomes")
    canal, _ = projeto.canal.info()
    trans, trocas = glossario.corrigir_transcricao(trans, _glossario(projeto, canal))
    if trocas:
        write_json(projeto.transcricao_path, trans)
        cands = projeto.candidatos()
        for c in cands:
            c["texto"] = candidates.texto_do_trecho(trans, c["inicio"], c["fim"])
        if cands:
            projeto.salvar_candidatos(cands)
    return trocas


def analisar_sinais(projeto: ProjetoWS, progresso: Progress = _nada, cancelar: threading.Event | None = None,
                    forcar: bool = False, cenas: bool = True) -> dict:
    if projeto.sinais_path.exists() and not forcar:
        return projeto.sinais() or {}
    with Etapa(projeto, "sinais"):
        s = signals.analisar(projeto.audio_path, projeto.video_path() if cenas else None, cancelar, progresso, cenas)
        write_json(projeto.sinais_path, s)
    return s


def gerar_candidatos(projeto: ProjetoWS, modo: str = "curto", forcar: bool = True) -> list[dict]:
    trans = projeto.transcricao()
    if not trans:
        raise RuntimeError("Transcreva o vídeo antes de gerar candidatos")
    regras, _ = projeto.canal.regras()
    canal, _ = projeto.canal.info()
    tmeta, _ = projeto.titulos()  # o do canal completado pela base de referência no tema do vídeo
    with Etapa(projeto, "candidatos"):
        cands = candidates.gerar(trans, projeto.sinais(), projeto.metadados(), regras, canal.palavras_chave, modo=modo)
        blocos = [s.get("texto", "") for s in trans.get("segmentos", [])]
        termos = canal.palavras_chave + list(regras.palavras_chave) + [t for t, _ in termos_relevantes(blocos, 40)]
        df, n_blocos = titles.frequencias(blocos)
        comuns = titles.termos_comuns([c["texto"] for c in cands])
        usados: set[str] = set()
        for i, c in enumerate(cands):
            c["titulos"] = titles.titulos_locais(
                c["texto"], titles.formulas_do_canal(tmeta), termos,
                tmeta.get("max_caracteres", 70), tmeta.get("palavras_caixa_alta", 2),
                inicio=i, df=df, n_blocos=n_blocos, evitar=comuns, ja_usados=usados,
                caixa_alta_total=bool(tmeta.get("caixa_alta_total")),
            )
            usados.add(c["titulos"][0])
            if regras.censor_leetspeak and regras.palavras_censuradas:
                c["titulos"] = [titles.censurar(t, regras.palavras_censuradas) for t in c["titulos"]]
        if modo == "longo":
            # corte longo convive com os candidatos curtos no mesmo arquivo
            existentes = [c for c in projeto.candidatos() if c.get("modo") != "longo"]
            cands = existentes + cands
        else:
            existentes = [c for c in projeto.candidatos() if c.get("modo") == "longo"]
            cands = cands + existentes
        projeto.salvar_candidatos(cands)
    return cands


ROTULOS_QUADROS = ("começo", "meio", "fim")


def _frase(palavras: list[str], onde: str, n: int = 10) -> str:
    if len(palavras) <= n:
        return " ".join(palavras)
    if onde == "começo":
        return " ".join(palavras[:n]) + " …"
    if onde == "fim":
        return "… " + " ".join(palavras[-n:])
    m = len(palavras) // 2
    return "… " + " ".join(palavras[max(0, m - n // 2): m + n - n // 2]) + " …"


def quadros_candidato(projeto: ProjetoWS, cid: str, largura: int = 320) -> list[dict]:
    """Começo, meio e fim de um candidato: um JPG de cada (em cache) e a frase falada ali."""
    c = next((c for c in projeto.candidatos() if c["id"] == cid), None)
    if c is None:
        raise KeyError(cid)
    video = projeto.video_path()
    if video is None:
        raise FileNotFoundError("O projeto ainda não tem vídeo")
    ini, fim = float(c["inicio"]), float(c["fim"])
    tempos = (min(ini + 0.5, fim), (ini + fim) / 2, max(fim - 0.5, ini))
    pasta = projeto.analise_dir / "quadros"
    cand_path = projeto.analise_dir / "candidatos.json"
    referencia = cand_path.stat().st_mtime if cand_path.exists() else 0
    trans = projeto.transcricao() or {}
    pals = [w["texto"] for w in transcribe.palavras(trans) if ini - 0.01 <= w["inicio"] < fim - 0.01]
    terco = max(1, len(pals) // 3)
    partes = {"começo": pals[:terco], "meio": pals[terco: len(pals) - terco] or pals, "fim": pals[-terco:]}
    out = []
    for k, (rotulo, t) in enumerate(zip(ROTULOS_QUADROS, tempos)):
        jpg = pasta / f"{cid}_{k}.jpg"
        if not jpg.exists() or jpg.stat().st_mtime < referencia:  # candidatos regerados mudam os tempos
            media.extrair_quadro(video, t, jpg, largura=largura)
        out.append({"rotulo": rotulo, "tempo": round(t, 3), "imagem": jpg,
                    "frase": _frase(partes[rotulo], rotulo)})
    return out


def centro_rosto(projeto: ProjetoWS, cid: str, quadros: list[dict]) -> float:
    """Onde fica o rosto (0 a 1 na largura) nos quadros do candidato, para recortar a prévia vertical.

    Usa o mesmo detector do reenquadramento; sem rosto ou sem detector, devolve o centro.
    O resultado fica em cache ao lado dos quadros.
    """
    cache = projeto.analise_dir / "quadros" / f"{cid}_rosto.json"
    jpg = quadros[0]["imagem"] if quadros else None
    if cache.exists() and jpg is not None and cache.stat().st_mtime >= jpg.stat().st_mtime:
        return float((read_json(cache) or {}).get("x", 0.5))
    x = 0.5
    try:
        import cv2

        from . import reframe

        det = reframe.detector()
        xs = []
        for q in quadros:
            img = cv2.imread(str(q["imagem"]))
            rostos = det.detectar(img) if det.disponivel and img is not None else []
            if rostos:
                xs.append(max(rostos, key=lambda r: r.area).cx)
        if xs:
            x = float(sorted(xs)[len(xs) // 2])
    except Exception:  # noqa: BLE001 - prévia sem rosto não pode quebrar a tela
        x = 0.5
    write_json(cache, {"x": round(x, 3)})
    return x


def ranquear(projeto: ProjetoWS, modo_ia: str | None = None, agente: str | None = None,
             progresso: Progress = _nada, cancelar: threading.Event | None = None, log: Log = _nada,
             esperar_login: Callable[[str], bool] | None = None) -> list[dict]:
    regras, regras_md = projeto.canal.regras()
    modo = modo_ia or regras.modo_ia
    cands = projeto.candidatos()
    if modo == "sem-ia" or not cands:
        projeto.marcar("ranking", "ok")
        return cands
    cfg = projeto.ws.config()
    adapter = adaptador_com_reserva(agente or cfg.ia.ranking, cfg.ia.timeout_s, log, esperar_login)
    if not adapter.disponivel():
        raise ErroIA(f"A IA '{adapter.nome}' não está instalada. Instale e faça login, ou use o modo sem IA.")
    canal_md, tmeta, tmd = _contexto_com_skills(projeto)
    cache = CacheIA(projeto.analise_dir / "cache_ia")
    trans = projeto.transcricao() or {}
    with Etapa(projeto, "ranking"):
        curtos = [c for c in cands if c.get("modo") != "longo"]
        longos = [c for c in cands if c.get("modo") == "longo"]
        progresso(0.05, f"perguntando ao {adapter.nome}")
        if modo == "completo":
            curtos = ia_ranking.completo(trans, curtos, adapter, regras, canal_md, regras_md, tmd, tmeta, cache, cancelar, progresso)
        curtos = ia_ranking.ranquear(curtos, trans, adapter, regras, canal_md, regras_md, tmd, tmeta, cache, cancelar)
        if regras.censor_leetspeak and regras.palavras_censuradas:
            for c in curtos:
                c["titulos"] = [titles.censurar(t, regras.palavras_censuradas) for t in c.get("titulos", [])]
        out = curtos + longos
        projeto.salvar_candidatos(out)
        progresso(1.0, "ranking pronto")
    return out


def _contexto_com_skills(projeto: ProjetoWS, partes: tuple[str, ...] = ("cortes", "titulos", "referencias")
                         ) -> tuple[str, dict, str]:
    """canal.md, titulos.md (completado pela base de referência no tema do vídeo), a base de referência
    e o referencias.md do canal, acrescidos das skills ativas de ranking e de títulos."""
    _, canal_md = projeto.canal.info()
    tmeta, tmd = projeto.titulos()
    c, p = projeto.canal.slug, projeto.id
    extra_rank = skills.texto_para_ia(projeto.ws, "ranking", c, p)
    extra_tit = skills.texto_para_ia(projeto.ws, "titulos", c, p)
    base = projeto.base_para_ia(partes)
    return ("\n\n".join(x for x in (canal_md.strip(), extra_rank) if x),
            tmeta, "\n\n".join(x for x in (tmd.strip(), base, extra_tit) if x))


def sugerir_titulos(projeto: ProjetoWS, clip_id: str, cancelar: threading.Event | None = None) -> dict:
    """Títulos para um clip: pela IA configurada ou, sem ela, pelas fórmulas locais."""
    clip, _ = projeto.clip(clip_id)
    regras, regras_md = projeto.canal.regras()
    canal_md, tmeta, tmd = _contexto_com_skills(projeto, ("titulos", "referencias"))
    texto = candidates.texto_do_trecho(projeto.transcricao() or {}, clip.inicio, clip.fim)
    cfg = projeto.ws.config()
    ad = adaptador_com_reserva(cfg.ia.ranking, cfg.ia.timeout_s)
    if not ad.disponivel():
        canal_info, _ = projeto.canal.info()
        tits = titles.titulos_locais(texto, titles.formulas_do_canal(tmeta), canal_info.palavras_chave,
                                     tmeta.get("max_caracteres", 70), tmeta.get("palavras_caixa_alta", 2),
                                     caixa_alta_total=bool(tmeta.get("caixa_alta_total")))
        return {"titulos": tits, "fonte": "local"}
    ctx = ia_ranking._contexto_canal(canal_md, regras_md, tmd, regras, tmeta)
    r = ia_ranking.sugerir_titulos(texto, ad, ctx, tmeta, regras.trava_titulo, None, cancelar)
    if regras.censor_leetspeak and regras.palavras_censuradas:
        r["titulos"] = [titles.censurar(t, regras.palavras_censuradas) for t in r.get("titulos", [])]
    return {**r, "fonte": ad.nome}


def analisar(projeto: ProjetoWS, progresso: Progress = _nada, cancelar: threading.Event | None = None,
             modo_ia: str | None = None, log: Log = _nada, corte_longo: bool = True,
             esperar_login: Callable[[str], bool] | None = None,
             etapa: Callable[[float, str, str, float], None] | None = None,
             cookies: dict | None = None, cookies_primeiro: bool = False) -> list[dict]:
    """Do link ao ranking: tudo que roda antes da seleção pelo usuário.

    `etapa(geral, msg, nome, fração)` recebe, além do progresso geral, a etapa atual e quanto dela foi;
    o download e a extração do áudio aparecem separados ("ingestao" e "audio").
    """
    projeto.limpar_erros()  # o erro de uma análise anterior não fica na tela durante a nova
    passos = [
        ("ingestao", 0.25, lambda p: ingerir(projeto, p, cancelar, cookies=cookies, cookies_primeiro=cookies_primeiro, log=log)),
        ("transcricao", 0.45, lambda p: transcrever(projeto, p, cancelar)),
        ("sinais", 0.12, lambda p: analisar_sinais(projeto, p, cancelar)),
        ("candidatos", 0.03, lambda p: (gerar_candidatos(projeto, "curto"),
                                        gerar_candidatos(projeto, "longo") if corte_longo else None)),
        ("ranking", 0.15, lambda p: _ranking_tolerante(projeto, modo_ia, p, cancelar, log, esperar_login)),
    ]
    base = 0.0
    for nome, peso, fn in passos:
        log(f"etapa {nome}")
        if etapa is not None:
            etapa(base, "", nome, 0.0)

        def sub(f: float, msg: str, base=base, peso=peso, nome=nome) -> None:
            f = max(0.0, min(1.0, f))
            geral = base + peso * f
            if etapa is None:
                progresso(geral, msg)
            elif nome == "ingestao":  # ingerir: 0 a 0,85 é o download, o resto é o áudio
                etapa(geral, msg, *(("audio", min(1.0, (f - 0.85) / 0.15)) if f >= 0.85 else ("ingestao", f / 0.85)))
            else:
                etapa(geral, msg, nome, f)

        fn(sub)
        base += peso
    progresso(1.0, "candidatos prontos")
    return projeto.candidatos()


def _ranking_tolerante(projeto: ProjetoWS, modo_ia: str | None, progresso: Progress, cancelar, log: Log,
                       esperar_login: Callable[[str], bool] | None = None) -> None:
    """Se a IA falhar, o app continua com a nota local (funciona sem IA)."""
    try:
        ranquear(projeto, modo_ia, progresso=progresso, cancelar=cancelar, log=log, esperar_login=esperar_login)
    except ErroIA as exc:
        log(f"IA indisponível, seguindo só com a nota local: {exc}")
        projeto.marcar("ranking", "erro", str(exc))


def selecionar(projeto: ProjetoWS, ids: list[str], formato: str | None = None, estilo: str | None = None,
               cartela: bool | None = None, pedido_ia: PedidoIA | None = None,
               ajustes: dict[str, Any] | None = None) -> list[Clip]:
    """Transforma candidatos em clips (pastas em clips/). `pedido_ia` fica guardado em cada clip.

    `ajustes` (cores, fonte, posição da legenda, sons…) sobrescreve o estilo nos clips criados agora; um clip
    que já existia só troca de estilo e de ajustes se `estilo` vier preenchido.
    """
    canal, _ = projeto.canal.info()
    por_id = {c["id"]: c for c in projeto.candidatos()}
    existentes = {c.candidato: c for c, _ in projeto.clips()}
    out = []
    for cid in ids:
        if cid not in por_id:
            raise KeyError(f"Candidato não encontrado: {cid}")
        if cid in existentes:
            clip = existentes[cid]
            mudou = False
            if pedido_ia:
                clip.pedido_ia = pedido_ia.model_copy()
                mudou = True
            if estilo:
                projeto.ws.carregar_estilo(estilo, projeto.canal)  # confere que existe
                clip.estilo, clip.ajustes_estilo = estilo, {**_sem_legenda_posicao(clip.ajustes_estilo), **(ajustes or {})}
                mudou = True
            if formato:
                clip.formato = formato  # type: ignore[assignment]
                mudou = True
            if mudou:
                projeto.salvar_clip(clip)
            out.append(clip)
            continue
        c = por_id[cid]
        longo = c.get("modo") == "longo"
        est_nome = estilo or ("corte-longo" if longo else canal.estilo_padrao)
        est, _, _ = projeto.ws.carregar_estilo(est_nome, projeto.canal)
        titulos_c = c.get("titulos") or []
        titulo = titulos_c[0] if titulos_c else ""
        clip = Clip(
            id=projeto.novo_clip_id(titulo or cid), candidato=cid, inicio=c["inicio"], fim=c["fim"], titulo=titulo,
            titulos_sugeridos=titulos_c, gancho=(c.get("ia") or {}).get("gancho", ""),
            formato=formato or ("16:9" if longo else est.formato), estilo=est_nome,
            cartela=est.cartela.sugerida if cartela is None else cartela,
            pedido_ia=pedido_ia.model_copy() if pedido_ia else None,
            ajustes_estilo=dict(ajustes or {}),
        )
        projeto.salvar_clip(clip)
        out.append(clip)
    return out


def _glossario(projeto: ProjetoWS, canal: Any) -> list[str]:
    """O glossário do canal mais os termos das skills de transcrição ativas."""
    return list(dict.fromkeys([*canal.glossario, *skills.termos_de_transcricao(projeto.ws, projeto.canal.slug, projeto.id)]))


def renderizar(projeto: ProjetoWS, clip_id: str, preview: bool = False, progresso: Progress = _nada,
               cancelar: threading.Event | None = None, versao: int | None = None,
               log: Callable[[str], None] | None = None) -> render.ResultadoRender:
    """`versao`: prévia de uma versão guardada da edição (vai para versoes-edicao/vN-previa.mp4, sem mexer no clip)."""
    from . import edicao as _edicao, melhorar

    clip, pasta = projeto.clip(clip_id)
    doc_versao, saida = None, None
    if versao is not None:
        v = melhorar.ler(pasta, versao)
        doc_versao = _edicao.Edicao(itens=v["itens"], destaques=v.get("destaques", []), cenas_planejadas=True)
        clip = clip.model_copy(update={"cortes_internos": [tuple(c) for c in v.get("cortes", [])]})
        saida, preview = melhorar.caminho_previa(pasta, versao), True
    est, _, est_path = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)
    regras, _ = projeto.canal.regras()
    cand = next((c for c in projeto.candidatos() if c["id"] == clip.candidato), None)
    destaques = ((cand or {}).get("ia") or {}).get("destaques") or []
    destaques = list(destaques) + list((doc_versao or _edicao.carregar(pasta)).destaques)
    with Etapa(projeto, "render"):
        r = render.renderizar_clip(projeto, clip, est, preview, progresso, cancelar, destaques, est_path.parent,
                                   doc_versao, saida, log=log)
    if versao is None and preview:  # a prévia da versão em uso fica guardada com ela
        n = melhorar._indice(pasta).get("atual")
        if n and r.video.exists():
            import shutil

            shutil.copyfile(r.video, melhorar.caminho_previa(pasta, n))
    if not preview:
        clip.status = "renderizado"
        projeto.salvar_clip(clip)
        _texto_postagem(projeto, clip, pasta, regras.trava_titulo)
    return r


def _sem_legenda_posicao(ajustes: dict[str, Any]) -> dict[str, Any]:
    """Ao trocar de estilo, só a altura da legenda ajustada à mão no clip continua valendo."""
    leg = (ajustes or {}).get("legenda") or {}
    return {"legenda": {"altura_relativa": leg["altura_relativa"]}} if "altura_relativa" in leg else {}


def _texto_postagem(projeto: ProjetoWS, clip: Clip, pasta, trava: bool) -> None:
    """Pacote de postagem sem IA para as plataformas do formato (postagem/ e postagem.txt)."""
    from . import postagem

    postagem.gerar(projeto, clip.id, usar_ia=False)
