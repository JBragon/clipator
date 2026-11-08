"""`clipator arte …`: a direção de arte do canal pelo terminal.

  clipator arte presets
  clipator arte criar CANAL [--base fliperama] [--nome "Meu canal"] [--forcar]
  clipator arte validar CANAL [--json]
  clipator arte compilar CANAL
  clipator arte mostrar CANAL
  clipator arte token CANAL cor.paleta.primaria       (ou --preset NOME no lugar do canal)
  clipator arte extrair CANAL [ARQUIVOS…] [--quadros 6]
  clipator arte prancha CANAL [--referencia quadro.png] [--estilo ESTILO]
  clipator arte guia CANAL ESTILO           (a DA que o estilo usa, com a marca do canal, e o texto da IA)
  clipator arte marca CANAL [--criar]       (arte/marca.yaml: cores, fontes e logo do canal)
  clipator arte importar especificacao.json [--nome N] [--substituir]   (direção visual → predefinido pessoal)
  clipator arte aprovar CANAL [--estrito]
  clipator arte revisar CANAL [--motivo "..."]
  clipator arte lint CANAL [ARQUIVOS…]
  clipator arte rotas CANAL criar NOME [--base P] [--frase F] [--primaria #HEX]
  clipator arte rotas CANAL listar | comparar [--com-atual] | adotar NOME
  clipator arte salvar-preset CANAL NOME [--substituir]
  clipator arte conferir CANAL

Códigos de saída: 0 ok · 1 reprovado (erro de validação, lint ou conferência) · 2 o canal não tem DA · 64 uso errado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SEM_DA = 2
USO = 64


def registrar(sub) -> None:
    s = sub.add_parser("arte", help="Direção de arte do canal: paleta, tipografia, movimento, prancha e aprovação")
    s.add_argument("acao", choices=["presets", "criar", "validar", "compilar", "mostrar", "token", "extrair", "prancha",
                                    "aprovar", "revisar", "lint", "rotas", "salvar-preset", "conferir", "guia", "marca", "importar"])
    s.add_argument("canal", nargs="?")
    s.add_argument("resto", nargs="*", help="Argumentos da ação (token, arquivos, subação das rotas…)")
    s.add_argument("--base", help="Predefinido de partida (criar, rotas criar)")
    s.add_argument("--nome")
    s.add_argument("--forcar", action="store_true")
    s.add_argument("--json", action="store_true")
    s.add_argument("--preset", help="token: lê de um predefinido em vez do canal")
    s.add_argument("--quadros", type=int, default=6)
    s.add_argument("--referencia", help="prancha: quadro do vídeo para as amostras")
    s.add_argument("--estrito", action="store_true")
    s.add_argument("--motivo", default="")
    s.add_argument("--frase", default="")
    s.add_argument("--primaria")
    s.add_argument("--com-atual", action="store_true")
    s.add_argument("--substituir", action="store_true")
    s.add_argument("--estilo", help="prancha: a DA que este estilo usa, com a marca do canal")
    s.add_argument("--criar", action="store_true", help="marca: escreve o modelo de arte/marca.yaml")
    s.set_defaults(fn=executar)


def _canal(args):
    from ..cli import _ws

    if not args.canal:
        print("Diga o canal: clipator arte " + args.acao + " CANAL", file=sys.stderr)
        raise SystemExit(USO)
    ws = _ws(args)
    return ws, ws.canal(args.canal)


def _imprimir(obj, como_json: bool) -> None:
    if como_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    elif isinstance(obj, str):
        print(obj)
    else:
        for k, v in (obj.items() if isinstance(obj, dict) else enumerate(obj)):
            print(f"{k}: {v}")


def executar(args) -> int:
    from ..workspace import WorkspaceError
    from . import servico
    from . import validar as _val
    from .carregar import ErroDA

    try:
        if args.acao == "presets":
            for p in servico.presets():
                print(f"{p['nome']:<22}{p['origem']:<10}{p['frase']}")
            return 0
        if args.acao == "importar":
            if not args.canal:
                print("Diga o arquivo: clipator arte importar especificacao.json", file=sys.stderr)
                return USO
            _imprimir(servico.importar(Path(args.canal), args.nome, args.substituir), True)
            return 0
        if args.acao == "token" and args.preset:
            if not args.canal and not args.resto:
                return USO
            caminho = args.resto[0] if args.resto else args.canal
            _imprimir(servico.token(None, caminho, args.preset), args.json or True)
            return 0
        ws, canal = _canal(args)
        cp = canal.path
        if args.acao == "criar":
            _imprimir(servico.criar(cp, args.base or "base", args.nome or "", args.forcar), args.json)
            return 0
        if args.acao == "validar":
            r, achados = servico.validar(cp)
            if args.json:
                _imprimir([a.para_dict() for a in achados], True)
            else:
                print(_val.texto(achados))
            return 1 if _val.resumo(achados)[0] else 0
        if args.acao == "compilar":
            res = servico.compilar(cp)
            _imprimir(res, args.json)
            return 1 if res["erros"] else 0
        if args.acao == "mostrar":
            print(servico.mostrar(cp))
            return 0
        if args.acao == "token":
            if not args.resto:
                print("Diga o token: clipator arte token CANAL cor.paleta.primaria", file=sys.stderr)
                return USO
            _imprimir(servico.token(cp, args.resto[0]), True)
            return 0
        if args.acao == "extrair":
            res = servico.extrair(cp, [Path(x) for x in args.resto] or None, args.quadros)
            if args.json:
                _imprimir(res, True)
            else:
                for nome, linhas in res["leitura"].items():
                    print(nome)
                    for ln in linhas:
                        print("  · " + ln)
                print("Candidatos a token (proposta, não regra):")
                for k, c in res["candidatos"].items():
                    print(f"  {k:<11}{c['hex']}  — {c['motivo']}")
                for a in res.get("arquivos", []):
                    print("gravado: " + a)
            return 0
        if args.acao == "prancha":
            est = ws.carregar_estilo(args.estilo, canal)[0] if args.estilo else None
            _imprimir(servico.prancha(cp, Path(args.referencia) if args.referencia else None, est), args.json)
            return 0
        if args.acao == "guia":
            if not args.resto:
                print("Diga o estilo: clipator arte guia CANAL ESTILO", file=sys.stderr)
                return USO
            res = servico.guia_do_estilo(cp, ws.carregar_estilo(args.resto[0], canal)[0])
            if args.json or res.get("arte") is None:
                _imprimir(res, True)
            else:
                print(f"Estilo {res['estilo']}: DA “{res['da']}” (arte: {res['arte']}), primária {res['primaria']}, "
                      f"fundo {res['fundo']}")
                print("Fontes: " + ", ".join(f"{k} {v}" for k, v in res["fontes"].items()))
                for a in res["avisos"]:
                    print("  AVISO " + a)
                for a in res["achados"]:
                    print(f"  {a['nivel'].upper():<5} {a['mensagem']}")
                print("\nO que a IA recebe ao planejar as cenas:\n" + res["guia_ia"])
            return 0
        if args.acao == "marca":
            _imprimir(servico.marca(cp, args.criar), True)
            return 0
        if args.acao == "aprovar":
            e = servico.aprovar(cp, args.estrito)
            print(f"DA aprovada: revisão {e['revisao']}, {e.get('aprovada_em', '')}")
            return 0
        if args.acao == "revisar":
            e = servico.revisar(cp, args.motivo)
            print(f"Revisão {e['revisao']} aberta; a DA precisa de nova aprovação.")
            return 0
        if args.acao == "lint":
            from .lint import texto

            res = servico.lint(cp, ws.estilos_dir, [Path(x) for x in args.resto] or None)
            if args.json:
                _imprimir({**res, "violacoes": [v.__dict__ for v in res["violacoes"]]}, True)
            else:
                print(texto(res))
            return 1 if res["violacoes"] or not res["conferidos"] else 0
        if args.acao == "rotas":
            return _rotas(args, cp)
        if args.acao == "salvar-preset":
            if not args.resto:
                print("Diga o nome do predefinido: clipator arte salvar-preset CANAL NOME", file=sys.stderr)
                return USO
            _imprimir(servico.salvar_preset(cp, args.resto[0], args.substituir), args.json)
            return 0
        if args.acao == "conferir":
            res = servico.conferir(cp, ws.estilos_dir)
            if args.json:
                _imprimir(res, True)
            else:
                print("APROVADO" if res["ok"] else "REPROVADO")
                for e in res["erros"]:
                    print("  ERRO  " + e)
                for a in res["avisos"]:
                    print("  AVISO " + a)
                print(f"  {len(res['clips'])} clip(s) conferido(s); lint: {res['lint']['conferidos']} arquivo(s)")
            return 0 if res["ok"] else 1
    except ErroDA as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return SEM_DA if "ainda não tem direção de arte" in str(exc) else 1
    except WorkspaceError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return USO


def _rotas(args, cp: Path) -> int:
    from . import rotas
    from . import validar as _val
    from .carregar import pasta_do_canal

    pasta = pasta_do_canal(cp)
    sub = args.resto[0] if args.resto else "listar"
    if sub == "criar":
        if len(args.resto) < 2:
            print("Diga o nome da rota: clipator arte rotas CANAL criar rota-a --base fliperama", file=sys.stderr)
            return USO
        res = rotas.criar(pasta, args.resto[1], args.base, args.frase, args.primaria)
        print(f"Rota criada: {res['arquivo']}")
        print(_val.texto(res["achados"]))
        return 0
    if sub == "listar":
        for item in rotas.listar(pasta):
            if "erro" in item:
                print(f"{item['nome']:<16} ERRO {item['erro']}")
            else:
                print(f"{item['nome']:<16} herda {item['herda'] or '—':<22} primária {item['primaria']}  "
                      f"{item['erros']} erro(s), {item['avisos']} aviso(s)  {item['frase'][:60]}")
        return 0
    if sub == "comparar":
        print(f"Comparação: {rotas.comparar(pasta, args.resto[1:] or None, args.com_atual)}")
        return 0
    if sub == "adotar":
        if len(args.resto) < 2:
            print("Diga a rota: clipator arte rotas CANAL adotar rota-b", file=sys.stderr)
            return USO
        res = rotas.adotar(pasta, args.resto[1])
        print(f"Rota adotada: {res['arquivo']} (revisão {res['revisao']}; anterior em {res['backup'] or '—'}). "
              "Gere a prancha e aprove de novo.")
        return 0
    print("Subações das rotas: criar, listar, comparar, adotar", file=sys.stderr)
    return USO
