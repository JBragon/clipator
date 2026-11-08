"""Gerenciar canais e vídeos (projetos) pelo explorador: detalhes, renomear, mover e apagar.

A pasta de um canal ou de um vídeo não muda de nome ao renomear (o nome que aparece fica no
`canal.md` e no `projeto.yaml`): assim nada que aponta para a pasta quebra (jobs, MCP, conversas).
Mover um vídeo para outro canal muda só a pasta-mãe. Apagar exige que não haja job rodando ali; o
app manda para a Lixeira quando pode e só pede ao motor para apagar de vez quando não pode.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import markdown as md
from .workspace import CanalWS, ProjetoWS, Workspace, WorkspaceError, read_yaml, write_yaml

ATIVOS = ("rodando", "na_fila")


def tamanho(p: Path) -> int:
    total = 0
    for f in p.rglob("*") if p.exists() else []:
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def jobs_ativos(jobs: list[dict], canal: str, projeto: str | None = None) -> list[dict]:
    """Jobs na fila ou rodando para o canal (ou só para aquele vídeo)."""
    return [j for j in jobs if j.get("status") in ATIVOS and (j.get("params") or {}).get("canal") == canal
            and (projeto is None or (j.get("params") or {}).get("projeto") == projeto)]


def status_projeto(p: ProjetoWS) -> dict[str, Any]:
    """Resumo para o explorador: em que pé está, quantos cortes e clips, e uma miniatura se houver."""
    m = p.meta()
    etapas = {k: v.status for k, v in m.etapas.items()}
    clips = p.clips()
    if any(s == "erro" for s in etapas.values()):
        fase = "erro"
    elif etapas.get("ingestao") != "ok":
        fase = "baixando" if etapas.get("ingestao") == "rodando" else "pendente"
    elif etapas.get("candidatos") != "ok" or etapas.get("ranking") == "rodando":
        fase = "analisando"
    elif clips:
        fase = "clips"
    else:
        fase = "cortes"
    thumb = next((d / "thumb.png" for _, d in clips if (d / "thumb.png").exists()), None)
    return {"fase": fase, "clips": len(clips), "cortes": len(p.candidatos()),
            "thumb": str(thumb.relative_to(p.ws.root)).replace("\\", "/") if thumb else None}


def detalhes_canal(c: CanalWS) -> dict[str, Any]:
    info, _ = c.info()
    projetos = c.projetos()
    return {"slug": c.slug, "nome": info.nome, "idioma": info.idioma, "pasta": str(c.path),
            "videos": len(projetos), "clips": sum(len(p.clips()) for p in projetos), "bytes": tamanho(c.path),
            "glossario": info.glossario, "palavras_chave": info.palavras_chave, "estilo_padrao": info.estilo_padrao,
            "arquivos": [str(a.relative_to(c.ws.root)).replace("\\", "/") for a in c.arquivos_textos()]}


def detalhes_projeto(p: ProjetoWS) -> dict[str, Any]:
    m = p.meta()
    md_ = p.metadados()
    return {"id": p.id, "titulo": m.titulo, "canal": p.canal.slug, "pasta": str(p.path), "criado_em": m.criado_em,
            "origem": m.origem.valor if m.origem else None, "tipo_origem": m.origem.tipo if m.origem else None,
            "duracao": (md_.get("midia") or {}).get("duracao") or md_.get("duracao"),
            "titulo_original": md_.get("titulo"), "etapas": {k: v.status for k, v in m.etapas.items()},
            "bytes": tamanho(p.path), **status_projeto(p)}


def renomear_canal(c: CanalWS, nome: str) -> None:
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("O nome não pode ficar vazio.")
    doc = md.read(c.path / "canal.md")
    meta = dict(doc.meta)
    meta["nome"] = nome[:120]
    md.write(c.path / "canal.md", meta, doc.body)


def renomear_projeto(p: ProjetoWS, titulo: str) -> None:
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("O nome não pode ficar vazio.")
    dados = read_yaml(p.path / "projeto.yaml")
    dados["titulo"] = titulo[:200]
    write_yaml(p.path / "projeto.yaml", dados)


def mover_projeto(ws: Workspace, p: ProjetoWS, destino: str) -> ProjetoWS:
    c2 = ws.canal(destino)
    if c2.slug == p.canal.slug:
        return p
    c2.projetos_dir.mkdir(parents=True, exist_ok=True)
    alvo = c2.projetos_dir / p.id
    n = 2
    while alvo.exists():
        alvo = c2.projetos_dir / f"{p.id}-{n}"
        n += 1
    shutil.move(str(p.path), str(alvo))
    novo = ProjetoWS(c2, alvo)
    if alvo.name != p.id:
        dados = read_yaml(alvo / "projeto.yaml")
        dados["id"] = alvo.name
        write_yaml(alvo / "projeto.yaml", dados)
    return novo


def apagar(pasta: Path, ws: Workspace) -> None:
    """Apaga de vez (o app usa a Lixeira; isto é para o modo web, o CLI e o MCP)."""
    pasta = pasta.resolve()
    raiz = ws.canais_dir.resolve()
    if raiz not in pasta.parents:
        raise WorkspaceError("Só dá para apagar canais e vídeos dentro do workspace.")
    shutil.rmtree(pasta)
