"""Rotas: duas ou três DAs candidatas, realmente diferentes, para a pessoa escolher comparando extremos.

Cada rota mora em `arte/rotas/<nome>/direcao.yaml`, herda de um predefinido (ou da DA atual do canal) e só
sobrescreve o que a diferencia. Varie o eixo entre elas: material (arquivo, painel, revista), valor (escuro ou
claro), família tipográfica, jeito de mexer, textura. `adotar` grava a rota escolhida, já com a herança
aplicada, como a DA do canal (guardando a anterior) e abre uma nova revisão.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import cores as C
from .carregar import (
    ARQUIVO,
    ErroDA,
    achar_herdado,
    cadeia,
    carregar_arquivo,
    salvar_yaml,
)
from .identidade import gravar_estado, ler_estado, revisar
from .validar import resumo, validar

_NOME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def diferenca(base: dict[str, Any], alvo: dict[str, Any]) -> dict[str, Any]:
    """O mínimo que, mesclado sobre `base`, dá `alvo` (mapas recursivos; listas e valores inteiros)."""
    out: dict[str, Any] = {}
    for k, v in alvo.items():
        if k not in base:
            out[k] = v
        elif isinstance(v, dict) and isinstance(base[k], dict):
            sub = diferenca(base[k], v)
            if sub:
                out[k] = sub
        elif v != base[k]:
            out[k] = v
    return out


def pasta_rotas(pasta_arte: Path) -> Path:
    return pasta_arte / "rotas"


def criar(pasta_arte: Path, nome: str, base: str | None = None, frase: str = "", primaria: str | None = None,
          ajustes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cria a rota e devolve {arquivo, achados}. Sem `base`, herda da DA atual do canal."""
    if not _NOME.match(nome):
        raise ErroDA("nome de rota: letras minúsculas, números e hífen (ex.: rota-a)")
    destino = pasta_rotas(pasta_arte) / nome / ARQUIVO
    if destino.exists():
        raise ErroDA(f"a rota “{nome}” já existe ({destino})")
    if base is None:
        if not (pasta_arte / ARQUIVO).exists():
            raise ErroDA("o canal ainda não tem DA: diga de qual predefinido a rota parte (--base)")
        herda = f"../../{ARQUIVO}"
    else:
        herda = base
    dados: dict[str, Any] = {"herda": herda}
    if frase:
        dados["conceito"] = {"frase": frase}
    if primaria:
        dados["cor"] = {"paleta": {"primaria": C.normalizar_hex(primaria)}}
    for k, v in (ajustes or {}).items():
        dados[k] = v
    salvar_yaml(destino, dados, f"# Rota “{nome}”: só o que a diferencia da base. Edite e rode `clipator arte rotas listar`.")
    r = carregar_arquivo(destino)
    return {"arquivo": str(destino), "achados": validar(r)}


def listar(pasta_arte: Path) -> list[dict[str, Any]]:
    out = []
    pr = pasta_rotas(pasta_arte)
    if not pr.is_dir():
        return out
    for d in sorted(pr.iterdir()):
        arq = d / ARQUIVO
        if not arq.exists():
            continue
        try:
            r = carregar_arquivo(arq)
            e, a, n = resumo(validar(r))
            out.append({"nome": d.name, "herda": r.da.herda, "primaria": r.cor("primaria"), "frase": r.da.conceito.frase,
                        "erros": e, "avisos": a, "notas": n, "arquivo": str(arq)})
        except ErroDA as exc:
            out.append({"nome": d.name, "erro": str(exc), "arquivo": str(arq)})
    return out


def comparar(pasta_arte: Path, nomes: list[str] | None = None, com_atual: bool = False) -> Path:
    from .prancha import comparar as _comparar

    escolhidas = []
    if com_atual and (pasta_arte / ARQUIVO).exists():
        escolhidas.append(("atual", carregar_arquivo(pasta_arte / ARQUIVO)))
    for item in listar(pasta_arte):
        if "erro" in item or (nomes and item["nome"] not in nomes):
            continue
        escolhidas.append((item["nome"], carregar_arquivo(Path(item["arquivo"]))))
    if not escolhidas:
        raise ErroDA("nenhuma rota para comparar: crie com `clipator arte rotas criar`")
    return _comparar(escolhidas, pasta_rotas(pasta_arte) / "comparacao.png")


def adotar(pasta_arte: Path, nome: str) -> dict[str, Any]:
    """A rota vira a DA do canal: herança aplicada até o primeiro predefinido, cópia da anterior, nova revisão."""
    arq = pasta_rotas(pasta_arte) / nome / ARQUIVO
    if not arq.exists():
        raise ErroDA(f"não existe a rota “{nome}”")
    r = carregar_arquivo(arq)
    erros, _, _ = resumo(validar(r))
    if erros:
        raise ErroDA(f"a rota tem {erros} erro(s) de validação; corrija antes de adotar")
    dados, anc = cadeia(arq)
    # A DA adotada herda do mesmo predefinido da cadeia (se houver) e grava o resto já mesclado: o arquivo do
    # canal fica completo e não depende da pasta da rota.
    atual = pasta_arte / ARQUIVO
    predefinido = None
    for a in anc:
        if Path(a).parent.name == "presets" or "arte-presets" in Path(a).parts:
            predefinido = Path(a).stem if Path(a).parent.name == "presets" else Path(a).parent.name
    dados.pop("herda", None)
    if predefinido:  # grava só o que difere do predefinido: o arquivo fica curto e legível
        base_dados, _ = cadeia(achar_herdado(predefinido, None))
        base_dados.pop("herda", None)
        dados = {"herda": predefinido, **diferenca(base_dados, dados)}
    backup = None
    if atual.exists():
        backup = atual.with_name(f"direcao.yaml.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(atual, backup)
    estado_antes = ler_estado(pasta_arte)
    salvar_yaml(atual, dados, f"# DA do canal (rota “{nome}” adotada em {datetime.now():%d/%m/%Y}).")
    # fontes que a rota trazia na pasta dela vêm junto
    fontes_rota = arq.parent / "fontes"
    if fontes_rota.is_dir():
        (pasta_arte / "fontes").mkdir(exist_ok=True)
        for f in fontes_rota.iterdir():
            if f.is_file():
                shutil.copy2(f, pasta_arte / "fontes" / f.name)
    nova = carregar_arquivo(atual)
    if estado_antes.get("aprovada") or estado_antes.get("historico"):
        e = revisar(nova, f"rota {nome} adotada")
    else:
        e = estado_antes
        e["historico"] = e.get("historico", []) + [{"evento": "rota adotada", "rota": nome}]
        gravar_estado(pasta_arte, e)
    e = ler_estado(pasta_arte)
    e["rota_adotada"] = nome
    gravar_estado(pasta_arte, e)
    return {"arquivo": str(atual), "backup": str(backup) if backup else None, "revisao": e["revisao"]}

