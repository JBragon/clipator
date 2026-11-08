"""Skills do usuário: pacotes com SKILL.md e clipator-skill.yaml.

Uma skill é uma pasta:

  minha-skill/
    SKILL.md               instruções (vão para a IA nas etapas que a skill declara)
    clipator-skill.yaml    nome, autor, versão, licença, preço e tipos
    estilos/*.md           opcional: estilos que a skill adiciona

As skills instaladas ficam em ~/.clipator/skills/ (ou $CLIPATOR_SKILLS), fora do
workspace e do repositório do Clipator. As embutidas vêm com o Clipator (dados/skills/, AGPL) e
valem em todo lugar até o usuário desligar (`ativa_por_padrao`). Pastas extras (por exemplo a SKILLS/ do
repo) entram só para leitura pelas configurações. A ativação diz onde cada skill
vale: no workspace inteiro, num canal ou num projeto.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, ValidationError

from . import markdown as md
from .models import AtivacaoSkill, Estilo, _Base

if TYPE_CHECKING:
    from .workspace import CanalWS, Workspace

MANIFESTO = "clipator-skill.yaml"
TIPOS = ("estilo", "titulos", "ranking", "thumbnail", "postagem", "fluxo", "cenas", "revisao", "transcricao")
TipoSkill = Literal["estilo", "titulos", "ranking", "thumbnail", "postagem", "fluxo", "cenas", "revisao", "transcricao"]
LIMITE_ZIP = 200 * 1024 * 1024  # 200 MB descompactados
LIMITE_TEXTO_IA = 6000  # caracteres de cada SKILL.md que vão para o prompt

DESCRICAO_TIPO = {
    "estilo": "adiciona estilos de vídeo",
    "titulos": "entra no pedido de títulos para a IA",
    "ranking": "entra no pedido de ranking dos cortes para a IA",
    "thumbnail": "entra no pedido da frase e do prompt da thumbnail",
    "postagem": "orienta o texto de postagem",
    "fluxo": "fica disponível para o Claude Code e o Codex pelo MCP",
    "cenas": "entra no pedido das cenas da direção de arte para a IA",
    "revisao": "entra na revisão antes de publicar (nota e o que corrigir)",
    "transcricao": "junta os termos do campo termos ao glossário da transcrição",
}
Origem = Literal["instalada", "pasta-extra", "embutida"]


class SkillError(Exception):
    pass


class Manifesto(_Base):
    id: str | None = None
    nome: str
    autor: str = ""
    versao: str = "0.0.0"
    licenca: str = ""
    preco: Literal["gratis", "pago"] = "gratis"
    link_compra: str | None = None
    tipos: list[TipoSkill] = Field(default_factory=lambda: ["fluxo"])
    descricao: str = ""
    ativa_por_padrao: bool = Field(False, description="Só nas embutidas: vale em todo lugar até ser desligada")


@dataclass
class Skill:
    id: str
    pasta: Path
    manifesto: Manifesto
    instrucoes: str
    origem: Origem = "instalada"
    estilos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)  # o cabeçalho do SKILL.md (ex.: termos da transcrição)

    def resumo(self) -> list[str]:
        """O que a skill muda, em frases curtas, para mostrar antes de ativar."""
        out = []
        for t in self.manifesto.tipos:
            if t == "estilo" and self.estilos:
                out.append(f"Adiciona {len(self.estilos)} estilo(s): {', '.join(self.estilos)}")
            elif t != "estilo":
                out.append(DESCRICAO_TIPO[t][0].upper() + DESCRICAO_TIPO[t][1:])
        return out

    def para_json(self, ativacoes: list[AtivacaoSkill] | None = None) -> dict[str, Any]:
        m = self.manifesto
        return {
            "id": self.id, "nome": m.nome, "autor": m.autor, "versao": m.versao, "licenca": m.licenca,
            "preco": m.preco, "link_compra": m.link_compra, "tipos": list(m.tipos), "descricao": m.descricao,
            "origem": self.origem, "pasta": str(self.pasta), "estilos": self.estilos, "avisos": self.avisos,
            "resumo": self.resumo(),
            "ativacoes": [a.model_dump(mode="json", exclude_none=True) for a in (ativacoes or []) if a.skill == self.id],
        }


def pasta_embutidas() -> Path:
    from .workspace import _dados

    return _dados("skills")


def pasta_skills() -> Path:
    env = os.environ.get("CLIPATOR_SKILLS")
    return Path(env).expanduser() if env else Path.home() / ".clipator" / "skills"


def _slug(texto: str) -> str:
    from .workspace import slugify

    return slugify(texto) or "skill"


def _skill_md(pasta: Path) -> Path | None:
    for nome in ("SKILL.md", "skill.md", "Skill.md"):
        if (pasta / nome).is_file():
            return pasta / nome
    return None


def ler_skill(pasta: Path, origem: Origem = "instalada") -> Skill:
    """Lê e valida uma pasta de skill. Levanta SkillError com a explicação se não der."""
    pasta = Path(pasta)
    smd = _skill_md(pasta)
    if smd is None:
        raise SkillError(f"{pasta.name}: falta o SKILL.md")
    try:
        doc = md.read(smd)
    except md.FrontMatterError as exc:
        raise SkillError(f"{pasta.name}/SKILL.md: {exc}") from exc
    avisos: list[str] = []
    mpath = pasta / MANIFESTO
    if mpath.is_file():
        try:
            import yaml

            dados = yaml.safe_load(mpath.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise SkillError(f"{pasta.name}/{MANIFESTO}: YAML inválido ({exc})") from exc
        if not isinstance(dados, dict):
            raise SkillError(f"{pasta.name}/{MANIFESTO}: esperava um mapa de chaves")
        try:
            man = Manifesto.model_validate(dados)
        except ValidationError as exc:
            erros = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
            raise SkillError(f"{pasta.name}/{MANIFESTO}: {erros}") from exc
    else:
        # Skill comum do Claude Code (só SKILL.md com name/description): entra como fluxo.
        tipos: list[str] = ["fluxo"] + (["estilo"] if (pasta / "estilos").is_dir() else [])
        man = Manifesto(nome=str(doc.meta.get("name") or doc.meta.get("nome") or pasta.name),
                        descricao=str(doc.meta.get("description") or doc.meta.get("descricao") or ""),
                        licenca=str(doc.meta.get("license") or doc.meta.get("licenca") or ""), tipos=tipos)
        avisos.append(f"Sem {MANIFESTO}: entra como skill de fluxo, sem autor nem licença declarados.")
    if man.preco == "pago" and not man.link_compra:
        avisos.append("Skill paga sem link_compra.")
    sid = _slug(man.id or pasta.name)
    estilos: list[str] = []
    if "estilo" in man.tipos:
        d = pasta / "estilos"
        if not d.is_dir():
            raise SkillError(f"{pasta.name}: declara o tipo estilo mas não tem a pasta estilos/")
        for p in sorted(d.glob("*.md")):
            try:
                e = md.read(p)
                Estilo.model_validate({"nome": p.stem, **e.meta})
            except Exception as exc:
                raise SkillError(f"{pasta.name}/estilos/{p.name}: {exc}") from exc
            estilos.append(p.stem)
        if not estilos:
            raise SkillError(f"{pasta.name}: a pasta estilos/ está vazia")
    if not doc.body.strip() and set(man.tipos) - {"estilo"}:
        avisos.append("O SKILL.md não tem instruções no corpo.")
    return Skill(sid, pasta, man, doc.body.strip(), origem, estilos, avisos, dict(doc.meta))


def _candidatas(raiz: Path, profundidade: int = 2) -> list[Path]:
    """Pastas com SKILL.md até `profundidade` níveis abaixo de raiz (inclusive a própria)."""
    if not raiz.is_dir():
        return []
    if _skill_md(raiz):
        return [raiz]
    out: list[Path] = []
    if profundidade > 0:
        for p in sorted(raiz.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                out += _candidatas(p, profundidade - 1)
    return out


# ---- catálogo ---------------------------------------------------------------
# listar() roda a cada estilo carregado (a galeria chama isso centenas de vezes): só relê do disco a
# skill cujos arquivos mudaram. O que vale aqui é a data e o tamanho, então uma edição aparece na hora.
_lidas: dict[tuple[Path, str], tuple[tuple, Skill | SkillError]] = {}


def _assinatura(pasta: Path) -> tuple:
    estilos = pasta / "estilos"
    tem_estilos = estilos.is_dir()
    arquivos = [pasta / "SKILL.md", pasta / "skill.md", pasta / "Skill.md", pasta / MANIFESTO]
    out: list[Any] = [tem_estilos]
    for p in arquivos + (sorted(estilos.glob("*.md")) if tem_estilos else []):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append((p.name, st.st_mtime_ns, st.st_size))
    return tuple(out)


def _ler_com_memoria(pasta: Path, origem: Origem) -> Skill:
    chave, assinatura = (pasta, origem), _assinatura(pasta)
    guardada = _lidas.get(chave)
    if guardada is None or guardada[0] != assinatura:
        try:
            lida: Skill | SkillError = ler_skill(pasta, origem)
        except SkillError as exc:
            lida = exc
        guardada = _lidas[chave] = (assinatura, lida)
    if isinstance(guardada[1], SkillError):
        raise guardada[1]
    return guardada[1]


def listar(ws: "Workspace") -> tuple[list[Skill], list[str]]:
    """Skills instaladas e das pastas extras, mais os erros de leitura (uma linha cada)."""
    skills: dict[str, Skill] = {}
    erros: list[str] = []
    fontes: list[tuple[Path, Origem]] = [(pasta_skills(), "instalada"), (pasta_embutidas(), "embutida")]
    try:
        fontes += [(Path(p).expanduser(), "pasta-extra") for p in ws.config().pastas_skills]
    except Exception:
        pass
    for raiz, origem in fontes:
        for pasta in _candidatas(raiz, 1 if origem != "pasta-extra" else 2):
            if pasta == raiz and origem != "pasta-extra":
                continue
            try:
                s = _ler_com_memoria(pasta, origem)
            except SkillError as exc:
                erros.append(str(exc))
                continue
            skills.setdefault(s.id, s)  # a instalada ganha da embutida, que ganha da pasta extra
    return sorted(skills.values(), key=lambda s: s.manifesto.nome.lower()), erros


def obter(ws: "Workspace", sid: str) -> Skill:
    for s in listar(ws)[0]:
        if s.id == sid:
            return s
    raise SkillError(f"Skill não encontrada: {sid}")


def ativacoes(ws: "Workspace") -> list[AtivacaoSkill]:
    """As ativações do config mais as das embutidas ligadas por padrão (como se fossem globais)."""
    try:
        cfg = ws.config()
    except Exception:
        return []
    out = list(cfg.skills)
    for s in listar(ws)[0]:
        if s.origem == "embutida" and s.manifesto.ativa_por_padrao and s.id not in cfg.skills_desligadas:
            a = AtivacaoSkill(skill=s.id, escopo="global")
            if a not in out:
                out.append(a)
    return out


def ativas(ws: "Workspace", canal: str | None = None, projeto: str | None = None, tipo: str | None = None) -> list[Skill]:
    """Skills que valem aqui: as globais (com as embutidas ligadas), as do canal e as do projeto."""
    ativ = ativacoes(ws)
    if not ativ:
        return []
    ids = []
    for a in ativ:
        if a.escopo == "global" or (a.escopo == "canal" and canal and a.canal == canal) or (
                a.escopo == "projeto" and canal and projeto and a.canal == canal and a.projeto == projeto):
            if a.skill not in ids:
                ids.append(a.skill)
    por_id = {s.id: s for s in listar(ws)[0]}
    out = [por_id[i] for i in ids if i in por_id]
    return [s for s in out if tipo is None or tipo in s.manifesto.tipos]


def texto_para_ia(ws: "Workspace", tipo: str, canal: str | None = None, projeto: str | None = None,
                  excluir: set[str] | frozenset[str] = frozenset()) -> str:
    """O texto das skills ativas deste tipo para o pedido à IA. `excluir`: ids que não se aplicam a este pedido."""
    partes = []
    for s in ativas(ws, canal, projeto, tipo):
        if s.instrucoes and s.id not in excluir:
            partes.append(f"## Skill do usuário: {s.manifesto.nome}\n{s.instrucoes[:LIMITE_TEXTO_IA]}")
    return "\n\n".join(partes)


def pastas_de_estilos(ws: "Workspace", canal: "CanalWS | None" = None) -> list[Path]:
    return [s.pasta / "estilos" for s in ativas(ws, canal.slug if canal else None, None, "estilo")]


def ativar(ws: "Workspace", sid: str, escopo: str = "global", canal: str | None = None, projeto: str | None = None) -> None:
    obter(ws, sid)
    if escopo in ("canal", "projeto") and not canal:
        raise SkillError("Diga o canal")
    if escopo == "projeto" and not projeto:
        raise SkillError("Diga o projeto")
    a = AtivacaoSkill(skill=sid, escopo=escopo, canal=canal if escopo != "global" else None,
                      projeto=projeto if escopo == "projeto" else None)
    cfg = ws.config()
    mudou = False
    if escopo == "global" and sid in cfg.skills_desligadas:  # embutida desligada: liga de novo
        cfg.skills_desligadas = [x for x in cfg.skills_desligadas if x != sid]
        mudou = True
    if a not in cfg.skills and not (escopo == "global" and _embutida_padrao(ws, sid)):
        cfg.skills.append(a)
        mudou = True
    if mudou:
        ws.salvar_config(cfg)


def _embutida_padrao(ws: "Workspace", sid: str) -> bool:
    try:
        s = obter(ws, sid)
    except SkillError:
        return False
    return s.origem == "embutida" and s.manifesto.ativa_por_padrao


def desativar(ws: "Workspace", sid: str, escopo: str | None = None, canal: str | None = None, projeto: str | None = None) -> None:
    """Sem escopo, tira a skill de todos os lugares. Embutida ligada por padrão: fica desligada no workspace."""
    cfg = ws.config()
    cfg.skills = [a for a in cfg.skills if not (a.skill == sid and (escopo is None or (
        a.escopo == escopo and a.canal == (canal if escopo != "global" else None)
        and a.projeto == (projeto if escopo == "projeto" else None))))]
    if escopo in (None, "global") and _embutida_padrao(ws, sid) and sid not in cfg.skills_desligadas:
        cfg.skills_desligadas.append(sid)
    ws.salvar_config(cfg)


def termos_de_transcricao(ws: "Workspace", canal: str | None = None, projeto: str | None = None) -> list[str]:
    """Termos que as skills de transcrição juntam ao glossário (campo `termos` do SKILL.md)."""
    out: list[str] = []
    for s in ativas(ws, canal, projeto, "transcricao"):
        t = s.meta.get("termos")
        if isinstance(t, list):
            out += [str(x).strip() for x in t if str(x).strip()]
    return list(dict.fromkeys(out))


# ---- instalar, exportar, remover --------------------------------------------
def instalar_pasta(origem: Path, substituir: bool = False) -> Skill:
    s = ler_skill(Path(origem))
    destino = pasta_skills() / s.id
    if destino.exists():
        if not substituir:
            raise SkillError(f"A skill '{s.id}' já está instalada")
        shutil.rmtree(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(origem, destino, ignore=shutil.ignore_patterns(".git", "__pycache__", ".DS_Store"))
    return ler_skill(destino)


def _extrair_zip(arquivo: Path, destino: Path) -> None:
    """Extrai recusando caminho absoluto, '..', links e zip-bomba."""
    with zipfile.ZipFile(arquivo) as z:
        total = 0
        for info in z.infolist():
            nome = PurePosixPath(info.filename.replace("\\", "/"))
            if nome.is_absolute() or ".." in nome.parts or re.match(r"^[A-Za-z]:", info.filename):
                raise SkillError(f"Caminho inseguro dentro do .zip: {info.filename}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise SkillError(f"O .zip tem um link simbólico: {info.filename}")
            total += info.file_size
            if total > LIMITE_ZIP:
                raise SkillError("O .zip passa de 200 MB descompactado")
        z.extractall(destino)


def instalar_zip(arquivo: Path, substituir: bool = False, subpasta: str = "") -> list[Skill]:
    try:
        with tempfile.TemporaryDirectory(prefix="clipator-skill-") as tmp:
            _extrair_zip(Path(arquivo), Path(tmp))
            raiz = Path(tmp)
            filhos = [p for p in raiz.iterdir() if p.name != "__MACOSX"]
            if len(filhos) == 1 and filhos[0].is_dir() and not _skill_md(raiz):
                raiz = filhos[0]  # o zip do GitHub e o "comprimir pasta" põem tudo numa pasta só
            if subpasta:
                raiz = raiz / subpasta
                if not raiz.is_dir():
                    raise SkillError(f"Pasta não encontrada no pacote: {subpasta}")
            pastas = _candidatas(raiz, 2)
            if not pastas:
                raise SkillError("Não achei nenhum SKILL.md no pacote")
            return [instalar_pasta(p, substituir) for p in pastas]
    except zipfile.BadZipFile as exc:
        raise SkillError("Arquivo .zip inválido") from exc


_GITHUB = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.+?))?)?/?$")


def ler_link_github(url: str) -> tuple[str, str, str | None, str]:
    """owner, repo, ref (ou None para o branch padrão), subpasta."""
    m = _GITHUB.match(url.strip())
    if not m:
        raise SkillError("Use um link do GitHub como https://github.com/autor/repo ou .../tree/main/pasta")
    return m.group(1), m.group(2), m.group(3), m.group(4) or ""


def instalar_github(url: str, substituir: bool = False) -> list[Skill]:
    dono, repo, ref, sub = ler_link_github(url)
    api = f"https://api.github.com/repos/{dono}/{repo}/zipball" + (f"/{ref}" if ref else "")
    req = urllib.request.Request(api, headers={"User-Agent": "clipator", "Accept": "application/vnd.github+json"})
    with tempfile.TemporaryDirectory(prefix="clipator-gh-") as tmp:
        alvo = Path(tmp) / "repo.zip"
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(alvo, "wb") as f:  # noqa: S310 - só https do GitHub
                lido = 0
                while bloco := r.read(1 << 16):
                    lido += len(bloco)
                    if lido > LIMITE_ZIP:
                        raise SkillError("O repositório passa de 200 MB")
                    f.write(bloco)
        except SkillError:
            raise
        except Exception as exc:
            raise SkillError(f"Não consegui baixar {dono}/{repo} do GitHub: {exc}") from exc
        return instalar_zip(alvo, substituir, sub)


def exportar_zip(ws: "Workspace", sid: str, destino: Path) -> Path:
    s = obter(ws, sid)
    destino = Path(destino)
    if destino.is_dir():
        destino = destino / f"{s.id}-{s.manifesto.versao}.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(s.pasta.rglob("*")):
            rel = p.relative_to(s.pasta)
            if p.is_file() and not p.is_symlink() and not any(x in (".git", "__pycache__") for x in rel.parts):
                z.write(p, f"{s.id}/{rel.as_posix()}")
    return destino


def remover(ws: "Workspace", sid: str) -> None:
    s = obter(ws, sid)
    if s.origem == "embutida":
        raise SkillError("Essa skill vem com o Clipator: dá para desligar, não apagar")
    if s.origem != "instalada":
        raise SkillError("Essa skill vem de uma pasta extra; tire a pasta nas configurações")
    shutil.rmtree(s.pasta)
    desativar(ws, sid)

