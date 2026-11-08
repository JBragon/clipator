"""Operações da DA de um canal, num lugar só: a CLI (`clipator arte …`) e o MCP chamam daqui.

Fluxo completo (o mesmo que a skill de direção de arte ensina à IA):

  criar (de um predefinido) -> referências em arte/referencias + extrair -> rotas (2 ou 3) -> comparar -> adotar
  -> refinar o direcao.yaml -> validar -> compilar -> prancha -> aprovar -> (renders carimbados) -> conferir
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import compilar as _comp
from . import identidade as _id
from . import validar as _val
from .carregar import (
    ARQUIVO,
    ErroDA,
    Resolvida,
    achar_herdado,
    arquivo_do_canal,
    carregar_arquivo,
    listar_presets,
    para_json,
    pasta_do_canal,
    pasta_presets_pessoais,
    salvar_yaml,
)

PASTAS = ("referencias", "fontes", "luts", "marca", "rotas", "build")
CABECALHO = """# Direção de arte do canal. Só o que difere do predefinido em `herda` precisa estar aqui.
# Dicionário dos tokens: docs/direcao-de-arte.md. Depois de editar: clipator arte validar && clipator arte prancha
"""


def carregar(canal_path: Path) -> Resolvida:
    arq = arquivo_do_canal(canal_path)
    if not arq.exists():
        raise ErroDA("este canal ainda não tem direção de arte: crie com `clipator arte criar CANAL --base <predefinido>` "
                     "(os predefinidos: `clipator arte presets`)")
    return carregar_arquivo(arq)


def criar(canal_path: Path, base: str = "base", nome: str = "", forcar: bool = False) -> dict[str, Any]:
    """Cria arte/direcao.yaml herdando de um predefinido, e as pastas de trabalho. Não sobrescreve sem `forcar`."""
    achar_herdado(base, None)  # erro claro se o predefinido não existe
    pasta = pasta_do_canal(canal_path)
    arq = pasta / ARQUIVO
    for p in PASTAS:
        (pasta / p).mkdir(parents=True, exist_ok=True)
    if arq.exists() and not forcar:
        return {"arquivo": str(arq), "criado": False, "aviso": "a DA já existia; nada foi sobrescrito (use --forcar)"}
    if arq.exists():
        shutil.copy2(arq, arq.with_name(ARQUIVO + ".bak"))
    dados: dict[str, Any] = {"herda": base}
    if nome:
        dados["nome"] = nome
    dados["conceito"] = {"referencias": []}
    salvar_yaml(arq, dados, CABECALHO)
    r = carregar_arquivo(arq)
    estado = _id.ler_estado(pasta)
    estado["base"] = base
    _id.gravar_estado(pasta, estado)
    _comp.escrever_build(r, _val.validar(r), _id.situacao(r))
    return {"arquivo": str(arq), "criado": True, "base": base}


def validar(canal_path: Path, extras_fontes: list[Path] | None = None) -> tuple[Resolvida, list[_val.Achado]]:
    r = carregar(canal_path)
    return r, _val.validar(r, _id.alterada_apos_aprovacao(r), extras_fontes or [canal_path / "assets" / "fontes"])


def compilar(canal_path: Path) -> dict[str, Any]:
    r, achados = validar(canal_path)
    build = _comp.escrever_build(r, achados, _id.situacao(r))
    e, a, n = _val.resumo(achados)
    return {"build": str(build), "erros": e, "avisos": a, "notas": n, "sha": _id.sha(r)}


def mostrar(canal_path: Path) -> str:
    r, achados = validar(canal_path)
    return _comp.resumo_md(r, achados, _id.situacao(r))


def token(canal_path: Path | None, caminho: str, preset: str | None = None) -> Any:
    """Valor de um token pelo caminho (`cor.paleta.primaria`, `legenda.tamanho`) ou pelo nome de cor (`primaria`)."""
    from .carregar import carregar_preset

    r = carregar_preset(preset) if preset else carregar(canal_path)  # type: ignore[arg-type]
    if caminho in r.tokens:
        return r.tokens[caminho]
    if caminho in r.campos:
        return r.campos[caminho]
    atual: Any = para_json(r)
    for parte in caminho.split("."):
        if isinstance(atual, dict) and parte in atual:
            atual = atual[parte]
        elif isinstance(atual, list) and parte.isdigit() and int(parte) < len(atual):
            atual = atual[int(parte)]
        else:
            raise ErroDA(f"token “{caminho}” não existe")
    return atual


def extrair(canal_path: Path, caminhos: list[Path] | None = None, quadros: int = 6) -> dict[str, Any]:
    from .referencias import extrair as _extrair

    pasta = pasta_do_canal(canal_path) / "referencias"
    return _extrair(caminhos or [pasta], pasta, quadros)


def prancha(canal_path: Path, referencia: Path | None = None, estilo: Any = None) -> dict[str, Any]:
    """A prancha da DA do canal ou, com `estilo`, da DA que esse estilo usa com a marca do canal por cima
    (gravada em arte/build/prancha-<estilo>.png)."""
    from .prancha import gerar, info

    if estilo is not None:
        from . import guia

        r, notas = guia.da_do_estilo(estilo, canal_path)
        if r is None:
            raise ErroDA(f"o estilo “{estilo.nome}” não usa direção de arte (falta `arte:` no cabeçalho dele)")
        destino = pasta_do_canal(canal_path) / "build" / f"prancha-{estilo.nome}.png"
        destino.parent.mkdir(parents=True, exist_ok=True)
        res = info(gerar(r, saida=destino, referencia=referencia))
        return {**res, "avisos": notas}
    r = carregar(canal_path)
    p = gerar(r, referencia=referencia)
    _comp.escrever_build(r, _val.validar(r), _id.situacao(r))
    return info(p)


MODELO_MARCA = """# Marca do canal: o que o canal põe por cima da direção de arte de qualquer estilo.
# O estilo escolhe a DA (`arte:` no cabeçalho dele); aqui ficam só as cores da marca, as fontes e o logo.
# Apague o que não usar. Cor que some no fundo do estilo é ajustada sozinha (respeitar_contraste).
cores:
  primaria: "#3DA9FC"
  # secundaria: "#2C3E5C"
  # destaque: "#FFC857"
# fontes:
#   titulo: Anton
#   corpo: Montserrat ExtraBold     # vale também para dados e legenda se eles não vierem
# logo: marca/logo.png
# assinatura: "@meucanal"
# posicao_logo: superior_direita
respeitar_contraste: true
"""


def marca(canal_path: Path, criar: bool = False) -> dict[str, Any]:
    """Mostra arte/marca.yaml do canal; com `criar`, escreve o modelo se ele não existir."""
    from . import guia

    arq = pasta_do_canal(canal_path) / guia.ARQUIVO_MARCA
    if criar and not arq.exists():
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(MODELO_MARCA, encoding="utf-8")
    if not arq.exists():
        return {"arquivo": str(arq), "existe": False}
    m = guia.ler_marca(canal_path)
    return {"arquivo": str(arq), "existe": True, "marca": m.model_dump(exclude_none=True) if m else {}}


def guia_do_estilo(canal_path: Path, estilo: Any) -> dict[str, Any]:
    """O que o estilo usa: a DA, a marca aplicada, os avisos e o texto que a IA recebe ao planejar as cenas."""
    from . import guia

    r, notas = guia.da_do_estilo(estilo, canal_path)
    if r is None:
        return {"estilo": estilo.nome, "arte": None,
                "aviso": "este estilo não usa direção de arte; ponha `arte: <predefinido>` no cabeçalho dele"}
    achados = [a.para_dict() for a in _val.validar(r) if a.nivel != "nota"]
    return {"estilo": estilo.nome, "arte": guia.referencia_do_estilo(estilo), **guia.resumo(r, notas),
            "achados": achados}


def aprovar(canal_path: Path, estrito: bool = False, quem: str = "") -> dict[str, Any]:
    from .prancha import gerar

    r = carregar(canal_path)
    e = _id.aprovar(r, estrito, quem)
    gerar(r)  # a prancha de registro sai com o carimbo de aprovada
    _comp.escrever_build(r, _val.validar(r), _id.situacao(r))
    return e


def revisar(canal_path: Path, motivo: str = "") -> dict[str, Any]:
    return _id.revisar(carregar(canal_path), motivo)


def lint(canal_path: Path, ws_estilos: Path | None = None, caminhos: list[Path] | None = None,
         base: Resolvida | None = None) -> dict[str, Any]:
    """Cor e fonte à mão nos estilos. Sugere tokens da DA do canal (ou, sem ela, do predefinido base)."""
    from .carregar import carregar_preset
    from .lint import conferir

    r = base or (carregar(canal_path) if arquivo_do_canal(canal_path).exists() else carregar_preset("base"))
    alvos = caminhos or [canal_path / "estilos"] + ([ws_estilos] if ws_estilos else [])
    return conferir([a for a in alvos if a.exists()], r, canal_path)


def salvar_preset(canal_path: Path, nome: str, substituir: bool = False) -> dict[str, Any]:
    """Guarda a DA do canal (com a herança aplicada e as fontes/LUTs/logos) como predefinido pessoal."""
    from .carregar import cadeia

    r = carregar(canal_path)
    destino = pasta_presets_pessoais() / nome
    if destino.exists() and not substituir:
        raise ErroDA(f"já existe o predefinido pessoal “{nome}” (use --substituir)")
    dados, _ = cadeia(r.arquivo)  # type: ignore[arg-type]
    dados.pop("herda", None)
    dados["nome"] = dados.get("nome") or nome
    salvar_yaml(destino / ARQUIVO, dados, f"# Predefinido pessoal “{nome}”, salvo do canal {canal_path.name}.")
    for sub in ("fontes", "luts", "marca"):
        origem = pasta_do_canal(canal_path) / sub
        if origem.is_dir() and any(origem.iterdir()):
            shutil.copytree(origem, destino / sub, dirs_exist_ok=True)
    return {"arquivo": str(destino / ARQUIVO)}


def conferir(canal_path: Path, ws_estilos: Path | None = None) -> dict[str, Any]:
    """A conferência antes de publicar: a marca e a DA do canal (se houver) válidas, a DA do canal aprovada,
    estilos sem cor solta e cada clip feito com a versão atual da DA do estilo que o gerou."""
    from . import guia

    erros: list[str] = []
    avisos: list[str] = []
    s: dict[str, Any] = {}
    r = None
    if arquivo_do_canal(canal_path).exists():
        r, achados = validar(canal_path)
        s = _id.situacao(r)
        e, _, _ = _val.resumo(achados)
        if e:
            erros.append(f"a DA do canal tem {e} erro(s) de validação (`clipator arte validar`)")
        if not s["aprovada"]:
            erros.append("a DA do canal não foi aprovada (`clipator arte prancha` e depois `clipator arte aprovar`)")
        elif s["alterada_apos_aprovacao"]:
            erros.append("a DA do canal mudou depois de aprovada (`clipator arte revisar` e aprove de novo)")
    try:
        guia.ler_marca(canal_path)
    except ErroDA as exc:
        erros.append(str(exc))
    lt = lint(canal_path, ws_estilos, base=r)
    if lt["violacoes"]:
        avisos.append(f"{len(lt['violacoes'])} cor(es) ou fonte(s) escritas à mão nos estilos (`clipator arte lint`)")
    carimbos = _id.conferir_carimbos(r, [canal_path / "projetos"],
                                     lambda ref: guia.da_da_referencia(ref, canal_path)[0])
    for c in carimbos:
        if c["veredito"] == "DA diferente":
            erros.append(f"{Path(c['arquivo']).name}: feito com outra versão da DA “{c.get('da') or c.get('arte')}”"
                         " (renderize de novo)")
        elif c["veredito"] == "DA não aprovada":
            avisos.append(f"{Path(c['arquivo']).name}: feito com a DA do canal ainda não aprovada")
    return {"ok": not erros, "erros": erros, "avisos": avisos, "situacao": s, "clips": carimbos,
            "lint": {"conferidos": lt["conferidos"], "violacoes": len(lt["violacoes"])}}


def importar(arquivo: Path, nome: str | None = None, substituir: bool = False) -> dict[str, Any]:
    """Importa um `especificacao.json` de direção visual como predefinido pessoal (com o contraste corrigido)."""
    import json

    from .importar import de_especificacao, id_curto

    spec = json.loads(Path(arquivo).read_text(encoding="utf-8"))
    try:
        dados, notas = de_especificacao(spec)
    except ValueError as exc:
        raise ErroDA(str(exc)) from exc
    nome = nome or id_curto(str(spec.get("id") or Path(arquivo).parent.parent.name))
    destino = pasta_presets_pessoais() / nome / ARQUIVO
    if destino.exists() and not substituir:
        raise ErroDA(f"já existe o predefinido pessoal “{nome}” (use --substituir)")
    salvar_yaml(destino, dados, f"# Importado de {Path(arquivo).name} por `clipator arte importar`.")
    r = carregar_arquivo(destino)
    e, a, _ = _val.resumo(_val.validar(r))
    return {"nome": nome, "arquivo": str(destino), "contraste_corrigido": notas, "erros": e, "avisos": a}


def presets() -> list[dict[str, Any]]:
    return listar_presets()
