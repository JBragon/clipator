"""CLI do Clipator.

  clipator init [pasta]                      cria um workspace
  clipator canal criar "Nome" [--idioma pt]
  clipator canal listar
  clipator processar CANAL LINK_OU_ARQUIVO   baixa, transcreve, acha candidatos e ranqueia
  clipator candidatos CANAL PROJETO
  clipator selecionar CANAL PROJETO c01 c02 [--formato 9:16 --estilo impacto --cartela]
  clipator renderizar CANAL PROJETO [CLIP ...] [--preview]
  clipator thumb CANAL PROJETO CLIP [--sem-ia] [--por-imagem]
  clipator skill listar | instalar ORIGEM | ativar ID [--canal C] | desativar ID | exportar ID DESTINO | remover ID
  clipator estilos
  clipator arte ACAO CANAL ...               direção de arte do canal (presets, criar, validar, prancha, aprovar…)
  clipator serve                             motor HTTP local para o app
  clipator mcp [registrar|remover]           servidor MCP (stdio), ou registra no Claude Code e no Codex
  clipator preparar                          baixa os modelos, o Chrome do HyperFrames e os stickers
  clipator doctor
  clipator desinstalar [--modelos]           tira os registros e componentes (o workspace fica)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _ws(args):
    from .service import workspace_padrao
    from .workspace import Workspace

    ws = Workspace(args.workspace or workspace_padrao())
    if not ws.existe():
        ws.init()
    return ws


class _Barra:
    """Barra de progresso simples no terminal."""

    def __init__(self) -> None:
        self.ultimo = ""

    def __call__(self, frac: float, msg: str) -> None:
        linha = f"\r[{'#' * int(frac * 30):<30}] {frac * 100:5.1f}% {msg[:60]:<60}"
        if linha != self.ultimo:
            sys.stderr.write(linha)
            sys.stderr.flush()
            self.ultimo = linha

    def fim(self) -> None:
        sys.stderr.write("\n")


def cmd_init(args) -> int:
    from .workspace import Workspace

    ws = Workspace(args.pasta or args.workspace or Path.home() / "Clipator").init()
    print(f"Workspace pronto em {ws.root}")
    if not ws.canais():
        c = ws.criar_canal("Meu canal")
        print(f"Canal de exemplo criado: {c.slug}")
    return 0


def cmd_canal(args) -> int:
    ws = _ws(args)
    if args.acao == "criar":
        c = ws.criar_canal(args.nome, args.idioma, palavras_chave=args.palavras_chave or [])
        print(c.slug)
    else:
        for c in ws.canais():
            info, _ = c.info()
            print(f"{c.slug}\t{info.nome}\t{len(c.projetos())} projeto(s)")
    return 0


def cmd_processar(args) -> int:
    from . import pipeline

    ws = _ws(args)
    canal = ws.canal(args.canal)
    proj = pipeline.criar_projeto(ws, canal, args.origem, args.titulo)
    print(f"Projeto: {proj.id}", file=sys.stderr)
    barra = _Barra()
    try:
        cands = pipeline.analisar(proj, barra, modo_ia=args.modo_ia, log=lambda m: None, corte_longo=args.corte_longo)
    finally:
        barra.fim()
    _imprimir_candidatos(cands[: args.mostrar])
    print(f"\nPróximo passo: clipator selecionar {canal.slug} {proj.id} <ids>", file=sys.stderr)
    return 0


def _imprimir_candidatos(cands: list[dict]) -> None:
    for c in cands:
        titulo = (c.get("titulos") or [""])[0]
        print(f"{c['id']}\t{c['nota']:5.1f}\t{_hms(c['inicio'])}-{_hms(c['fim'])}\t{c['duracao']:.0f}s\t{titulo}")
        for m in c.get("motivos", [])[:2]:
            print(f"\t\t· {m}")


def _hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def cmd_candidatos(args) -> int:
    ws = _ws(args)
    p = ws.canal(args.canal).projeto(args.projeto)
    cands = p.candidatos()
    if args.json:
        print(json.dumps(cands, ensure_ascii=False, indent=1))
    else:
        _imprimir_candidatos(cands)
    return 0


def cmd_selecionar(args) -> int:
    from . import pipeline

    ws = _ws(args)
    p = ws.canal(args.canal).projeto(args.projeto)
    for c in pipeline.selecionar(p, args.ids, args.formato, args.estilo, args.cartela):
        print(f"{c.id}\t{c.formato}\t{c.estilo}\t{c.titulo}")
    return 0


def cmd_renderizar(args) -> int:
    from . import pipeline

    ws = _ws(args)
    p = ws.canal(args.canal).projeto(args.projeto)
    ids = args.clips or [c.id for c, _ in p.clips()]
    if not ids:
        print("Nenhum clip selecionado. Use 'clipator selecionar' antes.", file=sys.stderr)
        return 1
    for cid in ids:
        barra = _Barra()
        try:
            r = pipeline.renderizar(p, cid, args.preview, lambda f, m: barra(f, f"{cid}: {m}"))
        finally:
            barra.fim()
        print(r.video)
    return 0


def cmd_thumb(args) -> int:
    from . import thumbs

    ws = _ws(args)
    p = ws.canal(args.canal).projeto(args.projeto)
    barra = _Barra()
    try:
        if args.por_imagem:
            nomes = thumbs.gerar_com_imagem(p, args.clip, 2, barra)
        else:
            nomes = thumbs.gerar(p, args.clip, not args.sem_ia, barra)["variacoes"]
    finally:
        barra.fim()
    pasta = p.clips_dir / args.clip / "thumbs"
    for n in nomes:
        print(pasta / n)
    return 0


def cmd_skill(args) -> int:
    from pathlib import Path as P

    from . import skills

    ws = _ws(args)
    if args.acao == "listar":
        lista, erros = skills.listar(ws)
        ativas = {a.skill for a in ws.config().skills}
        for s in lista:
            print(f"{s.id:<28}{'ativa' if s.id in ativas else '-':<7}{','.join(s.manifesto.tipos):<22}{s.manifesto.nome}")
        for e in erros:
            print(f"Erro: {e}", file=sys.stderr)
        return 0
    if not args.alvo:
        print("Diga a skill (ou a origem, para instalar).", file=sys.stderr)
        return 1
    if args.acao == "instalar":
        o = args.alvo
        novas = (skills.instalar_github(o, args.substituir) if o.startswith("https://")
                 else skills.instalar_zip(P(o), args.substituir) if o.lower().endswith(".zip")
                 else [skills.instalar_pasta(P(o), args.substituir)])
        for s in novas:
            print(f"Instalada: {s.id} ({s.manifesto.nome})")
            for linha in s.resumo():
                print(f"  · {linha}")
            for a in s.avisos:
                print(f"  ! {a}")
    elif args.acao == "ativar":
        escopo = "projeto" if args.projeto else "canal" if args.canal else "global"
        skills.ativar(ws, args.alvo, escopo, args.canal, args.projeto)
    elif args.acao == "desativar":
        skills.desativar(ws, args.alvo)
    elif args.acao == "exportar":
        print(skills.exportar_zip(ws, args.alvo, P(args.destino or ".")))
    elif args.acao == "remover":
        skills.remover(ws, args.alvo)
    return 0


def cmd_estilos(args) -> int:
    ws = _ws(args)
    for nome in ws.estilos():
        est, _, _ = ws.carregar_estilo(nome)
        print(f"{nome:<22}{est.formato:<6}{est.motor:<12}{est.nivel_ia:<10}{est.descricao}")
    return 0


def cmd_serve(args) -> int:
    from .api import rodar

    rodar(porta=args.porta, workspace=args.workspace, token=args.token, vigiar_stdin=args.vigiar_stdin)
    return 0


def cmd_mcp(args) -> int:
    if args.acao == "registrar":
        from .instalacao import registrar_mcp

        erros = registrar_mcp(workspace=args.workspace)
        for e in erros:
            print(f"Erro: {e}", file=sys.stderr)
        return 1 if erros else 0
    if args.acao == "remover":
        from .instalacao import remover_mcp

        remover_mcp()
        return 0
    from .mcp_server import rodar

    rodar(args.workspace)
    return 0


def cmd_preparar(args) -> int:
    from .instalacao import preparar

    cfg = _ws(args).config().whisper
    erros = preparar(whisper=not args.sem_whisper, rosto=not args.sem_rosto, navegador=not args.sem_navegador,
                     modelo=cfg.modelo, dispositivo=cfg.dispositivo, stickers=not args.sem_stickers)
    for e in erros:
        print(f"Aviso: {e}", file=sys.stderr)
    if not erros:
        print("Tudo pronto para trabalhar offline.")
    return 0


def cmd_desinstalar(args) -> int:
    from .instalacao import desinstalar

    if not args.sim:
        resp = input("Remover os registros do MCP e os componentes do Clipator? O workspace fica. [s/N] ")
        if resp.strip().lower() not in ("s", "sim", "y", "yes"):
            print("Nada foi removido.")
            return 0
    desinstalar(apagar_modelos=args.modelos)
    return 0


def cmd_doctor(args) -> int:
    from .doctor import imprimir, verificar
    from .service import workspace_padrao

    return imprimir(verificar(Path(args.workspace or workspace_padrao())))


def _saida_utf8() -> None:
    """No Windows, a saída redirecionada (pipe, arquivo, PowerShell) usa a página de código
    do sistema, que não tem ✔ e às vezes nem acentos. Força UTF-8 e nunca quebra por isso."""
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if enc != "utf8" and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _saida_utf8()
    from .media import completar_path_windows

    completar_path_windows()  # FFmpeg, Deno e Node.js instalados depois que o terminal ou o app abriu
    ap = argparse.ArgumentParser(prog="clipator", description="Clips curtos de vídeos longos, tudo local.")
    ap.add_argument("--version", action="version", version=f"clipator {__version__}")
    ap.add_argument("-w", "--workspace", help="Pasta do workspace (padrão: ~/Clipator ou $CLIPATOR_WORKSPACE)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Cria um workspace")
    s.add_argument("pasta", nargs="?")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("canal", help="Cria ou lista canais")
    s.add_argument("acao", choices=["criar", "listar"])
    s.add_argument("nome", nargs="?")
    s.add_argument("--idioma", default="pt", choices=["pt", "en", "auto"])
    s.add_argument("--palavras-chave", nargs="*")
    s.set_defaults(fn=cmd_canal)

    s = sub.add_parser("processar", help="Baixa/importa, transcreve, acha e ranqueia candidatos")
    s.add_argument("canal")
    s.add_argument("origem", help="Link do YouTube/Twitch ou caminho de um arquivo de vídeo")
    s.add_argument("--titulo")
    s.add_argument("--modo-ia", choices=["sem-ia", "economico", "completo"])
    s.add_argument("--corte-longo", action="store_true", help="Também procura cortes longos 16:9 de 8 a 20 min")
    s.add_argument("--mostrar", type=int, default=15)
    s.set_defaults(fn=cmd_processar)

    s = sub.add_parser("candidatos", help="Lista os candidatos de um projeto")
    s.add_argument("canal")
    s.add_argument("projeto")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_candidatos)

    s = sub.add_parser("selecionar", help="Transforma candidatos em clips")
    s.add_argument("canal")
    s.add_argument("projeto")
    s.add_argument("ids", nargs="+")
    s.add_argument("--formato", choices=["9:16", "1:1", "4:5", "16:9"])
    s.add_argument("--estilo")
    s.add_argument("--cartela", action=argparse.BooleanOptionalAction, default=None)
    s.set_defaults(fn=cmd_selecionar)

    s = sub.add_parser("renderizar", help="Renderiza clips")
    s.add_argument("canal")
    s.add_argument("projeto")
    s.add_argument("clips", nargs="*")
    s.add_argument("--preview", action="store_true")
    s.set_defaults(fn=cmd_renderizar)

    s = sub.add_parser("thumb", help="Gera as thumbnails de um clip")
    s.add_argument("canal")
    s.add_argument("projeto")
    s.add_argument("clip")
    s.add_argument("--sem-ia", action="store_true", help="Frase-gancho só pelo título, sem chamar a IA")
    s.add_argument("--por-imagem", action="store_true", help="Variações por imagem com o Codex ($imagegen)")
    s.set_defaults(fn=cmd_thumb)

    s = sub.add_parser("skill", help="Skills do usuário: listar, instalar, ativar, exportar")
    s.add_argument("acao", choices=["listar", "instalar", "ativar", "desativar", "exportar", "remover"])
    s.add_argument("alvo", nargs="?", help="Id da skill, ou pasta/.zip/link do GitHub para instalar")
    s.add_argument("destino", nargs="?", help="Pasta ou arquivo .zip (exportar)")
    s.add_argument("--canal")
    s.add_argument("--projeto")
    s.add_argument("--substituir", action="store_true")
    s.set_defaults(fn=cmd_skill)

    s = sub.add_parser("estilos", help="Lista os estilos")
    s.set_defaults(fn=cmd_estilos)

    from .arte.cli import registrar as registrar_arte

    registrar_arte(sub)

    s = sub.add_parser("serve", help="Motor HTTP local para o app")
    s.add_argument("--porta", type=int, default=8765)
    s.add_argument("--token")
    s.add_argument("--vigiar-stdin", action="store_true", help="Encerra quando o stdin fecha (usado pelo app)")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("mcp", help="Servidor MCP via stdio, ou registrar/remover no Claude Code e no Codex")
    s.add_argument("acao", nargs="?", default="servir", choices=["servir", "registrar", "remover"])
    s.set_defaults(fn=cmd_mcp)

    s = sub.add_parser("preparar", help="Baixa os modelos e o Chrome do HyperFrames para usar offline")
    s.add_argument("--sem-whisper", action="store_true")
    s.add_argument("--sem-rosto", action="store_true")
    s.add_argument("--sem-navegador", action="store_true")
    s.add_argument("--sem-stickers", action="store_true", help="Não baixa o pacote de stickers (cerca de 170 MB)")
    s.set_defaults(fn=cmd_preparar)

    s = sub.add_parser("desinstalar", aliases=["uninstall"], help="Remove registros e componentes (o workspace fica)")
    s.add_argument("--modelos", action="store_true", help="Também apaga os modelos baixados")
    s.add_argument("-s", "--sim", action="store_true", help="Não pergunta antes")
    s.set_defaults(fn=cmd_desinstalar)

    s = sub.add_parser("doctor", help="Confere as dependências")
    s.set_defaults(fn=cmd_doctor)

    args = ap.parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # mensagem curta para o usuário; --debug fica para depois
        if args.cmd == "serve" or (args.cmd == "mcp" and args.acao == "servir"):
            raise
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
