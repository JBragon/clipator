"""Workspace em disco: canais, projetos, estilos e clips como pastas e arquivos.

meu-workspace/
  .clipator/config.yaml
  estilos/
  canais/<canal>/canal.md, estilos/, assets/, thumbs/modelos/, projetos/
  canais/<canal>/regras-e-textos/LEIA-ME.md, regras.md, titulos.md, thumb.md, referencias.md
  canais/<canal>/projetos/<projeto>/projeto.yaml, fonte/, analise/, clips/
"""

from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, Iterator

import yaml

from . import markdown as md
from .models import Canal, Clip, ConfigApp, Estilo, Etapa, Origem, Projeto, Regras, Thumb

ETAPAS = ("ingestao", "transcricao", "sinais", "candidatos", "ranking", "render")


class WorkspaceError(Exception):
    pass


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(texto: str, max_len: int = 60) -> str:
    norm = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return (slug[:max_len].rstrip("-")) or "sem-nome"


def _dados(*partes: str) -> Path:
    return Path(str(resources.files("clipator").joinpath("dados", *partes)))


def estilos_embutidos_dir() -> Path:
    return _dados("estilos")


def fontes_dir() -> Path:
    return _dados("fontes")


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise WorkspaceError(f"{path} precisa ser um mapa YAML")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


CANAL_MD = """Descreva aqui o canal para a IA: quem é o público, que tipo de momento
costuma viralizar e o que nunca deve virar corte.
"""

REGRAS_MD = """Regras livres para a IA ao julgar cortes. Exemplo: prefira momentos com
história completa, evite trechos que dependem de contexto anterior.
"""

TITULOS_MD = """Fórmulas de título. Use {tema}, {numero}, {nome} e {verbo}.
O título pode exagerar a emoção, mas o que ele promete tem que acontecer no clip.
"""

THUMB_MD = """Regras da thumbnail para a IA: o que a frase-gancho deve prometer, onde fica o
rosto, o que evitar. Coloque thumbnails de referência em thumbs/modelos/.
Regra de ouro: o rosto nunca é redesenhado; a thumbnail é montada sobre o quadro real do vídeo.
"""

FORMULAS_PADRAO = [
    "NINGUÉM te conta isso sobre {tema}",
    "Ele revelou {tema} ao vivo",
    "Isso muda TUDO sobre {tema}",
    "O erro que custou {numero}",
    "{nome} FALOU sobre {tema}",
    "{tema}: a verdade que ninguém quer ouvir",
]


PASTA_TEXTOS = "regras-e-textos"
# arquivos que moram em regras-e-textos/ (canais antigos tinham os três primeiros na raiz do canal)
ARQUIVOS_TEXTOS = ("regras.md", "titulos.md", "thumb.md", "referencias.md")


def modelo_canal_dir() -> Path:
    """Os arquivos com que todo canal novo começa a pasta regras-e-textos/ (dados/base-virais/modelo-canal/)."""
    return _dados("base-virais", "modelo-canal")


def referencias_para_ia(texto: str, limite: int = 4000) -> str:
    """O referencias.md do canal (os cortes do próprio canal que deram certo), cortado num tamanho que não
    pesa no prompt. Linhas de exemplo "(cole aqui...)" não contam. A base embutida vai à parte (base_virais)."""
    linhas = [l for l in texto.strip().splitlines() if "(cole aqui" not in l]
    if not any(l.lstrip().startswith("- ") for l in linhas):
        return ""
    texto = "\n".join(linhas).strip()
    if len(texto) > limite:
        texto = texto[:limite].rsplit("\n", 1)[0] + "\n(…)"
    return "## Referências do canal (régua de tom, não copie)\n" + texto


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()

    # ---- estrutura -------------------------------------------------------
    @property
    def config_path(self) -> Path:
        return self.root / ".clipator" / "config.yaml"

    @property
    def canais_dir(self) -> Path:
        return self.root / "canais"

    @property
    def estilos_dir(self) -> Path:
        return self.root / "estilos"

    def existe(self) -> bool:
        return self.config_path.exists()

    def init(self) -> "Workspace":
        self.root.mkdir(parents=True, exist_ok=True)
        self.canais_dir.mkdir(exist_ok=True)
        self.estilos_dir.mkdir(exist_ok=True)
        if not self.config_path.exists():
            write_yaml(self.config_path, ConfigApp().model_dump(mode="json"))
        gi = self.root / ".gitignore"
        if not gi.exists():
            gi.write_text(
                "# Vídeos e áudios são grandes; versione só as regras e os resultados leves\n"
                "**/fonte/\n**/*.wav\n**/saida*.mp4\n**/preview*.mp4\n**/camada*.webm\n**/hyperframes*/fontes/\n.clipator/cache/\n",
                encoding="utf-8",
            )
        return self

    def config(self) -> ConfigApp:
        return ConfigApp.model_validate(read_yaml(self.config_path))

    def salvar_config(self, cfg: ConfigApp) -> None:
        write_yaml(self.config_path, cfg.model_dump(mode="json"))

    def dentro(self, path: str | Path) -> Path:
        """Resolve um caminho relativo ao workspace e recusa sair dele."""
        p = (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if p != self.root and self.root not in p.parents:
            raise WorkspaceError(f"Caminho fora do workspace: {path}")
        return p

    # ---- canais ----------------------------------------------------------
    def canais(self) -> list["CanalWS"]:
        if not self.canais_dir.exists():
            return []
        return [CanalWS(self, p) for p in sorted(self.canais_dir.iterdir()) if (p / "canal.md").exists()]

    def canal(self, slug: str) -> "CanalWS":
        p = self.canais_dir / slugify(slug)
        if not (p / "canal.md").exists():
            raise WorkspaceError(f"Canal não encontrado: {slug}")
        return CanalWS(self, p)

    def criar_canal(self, nome: str, idioma: str = "pt", **extra: Any) -> "CanalWS":
        """Cria a pasta do canal com regras-e-textos/ (regras, títulos, thumb e referências, todos editáveis).
        Não há nicho a escolher: a base de referência embutida (base_virais.py) detecta o tema de cada vídeo."""
        slug = slugify(nome)
        p = self.canais_dir / slug
        if (p / "canal.md").exists():
            raise WorkspaceError(f"O canal '{slug}' já existe")
        canal = Canal(nome=nome, idioma=idioma, **extra)
        for sub in ("estilos", "assets/musicas", "assets/sfx", "assets/fontes", "thumbs/modelos", "projetos", PASTA_TEXTOS):
            (p / sub).mkdir(parents=True, exist_ok=True)
        modelo = modelo_canal_dir()
        md.write(p / "canal.md", canal.model_dump(mode="json", exclude_none=True), _corpo(modelo / "canal.md", CANAL_MD))
        textos = p / PASTA_TEXTOS
        # regras e thumb: o modelo completo (todos os campos, com os padrões) e o texto do modelo do canal
        for nome_arq, classe, corpo in (("regras.md", Regras, REGRAS_MD), ("thumb.md", Thumb, THUMB_MD)):
            doc = md.read(modelo / nome_arq) if (modelo / nome_arq).exists() else md.MarkdownDoc()
            md.write(textos / nome_arq, classe.model_validate(doc.meta).model_dump(mode="json"), doc.body or corpo)
        tit = md.read(modelo / "titulos.md") if (modelo / "titulos.md").exists() else md.MarkdownDoc()
        meta_tit = tit.meta or {"temperatura": "auto", "formulas": [], "max_caracteres": 70, "emojis": False}
        md.write(textos / "titulos.md", meta_tit, tit.body or TITULOS_MD)
        for nome_arq in ("LEIA-ME.md", "referencias.md"):
            if (modelo / nome_arq).exists():
                shutil.copyfile(modelo / nome_arq, textos / nome_arq)
        return CanalWS(self, p)

    # ---- estilos ---------------------------------------------------------
    def estilos(self, canal: "CanalWS | None" = None) -> dict[str, Path]:
        """Todos os estilos visíveis, do mais geral ao mais específico."""
        found: dict[str, Path] = {}
        from .skills import pastas_de_estilos

        dirs = [estilos_embutidos_dir(), *pastas_de_estilos(self, canal), self.estilos_dir]
        if canal is not None:
            dirs.append(canal.path / "estilos")
        for d in dirs:
            if not d.exists():
                continue
            for p in sorted(d.iterdir()):
                if p.suffix == ".md":
                    found[p.stem] = p
                elif p.is_dir() and (p / "estilo.md").exists():
                    found[p.name] = p / "estilo.md"
        return found

    def carregar_estilo(self, nome: str, canal: "CanalWS | None" = None, ajustes: dict | None = None,
                        estilos: dict[str, Path] | None = None) -> tuple[Estilo, str, Path]:
        """`estilos`: o resultado de estilos(canal), para quem carrega vários e não quer varrer as pastas a cada um."""
        estilos = self.estilos(canal) if estilos is None else estilos
        if nome not in estilos:
            raise WorkspaceError(f"Estilo não encontrado: {nome}")
        doc = md.read(estilos[nome])
        meta = md.deep_merge(doc.meta, ajustes or {})
        meta.setdefault("nome", nome)
        return Estilo.model_validate(meta), doc.body, estilos[nome]


def _corpo(path: Path, padrao: str) -> str:
    return md.read(path).body if path.exists() else padrao


class CanalWS:
    def __init__(self, ws: Workspace, path: Path):
        self.ws = ws
        self.path = path
        self.slug = path.name
        self._migrar_textos()

    @property
    def textos_dir(self) -> Path:
        """regras-e-textos/: tudo o que o usuário edita para o canal fica junto, num lugar só."""
        return self.path / PASTA_TEXTOS

    def arquivo(self, nome: str) -> Path:
        return self.textos_dir / nome

    def arquivos_textos(self) -> list[Path]:
        """canal.md e os arquivos de regras-e-textos/, na ordem em que o usuário costuma abrir."""
        out = [self.path / "canal.md"]
        if self.textos_dir.exists():
            fixos = [self.textos_dir / n for n in ("LEIA-ME.md", *ARQUIVOS_TEXTOS)]
            out += [f for f in fixos if f.exists()]
            out += sorted(f for f in self.textos_dir.iterdir() if f.is_file() and f.suffix == ".md" and f not in fixos)
        return out

    def _migrar_textos(self) -> None:
        """Canais criados antes da pasta regras-e-textos/: leva regras.md, titulos.md e thumb.md para lá."""
        antigos = [n for n in ARQUIVOS_TEXTOS if (self.path / n).is_file()]
        if not antigos or not (self.path / "canal.md").exists():
            return
        self.textos_dir.mkdir(exist_ok=True)
        for n in antigos:
            destino = self.textos_dir / n
            if destino.exists():
                continue  # os dois existem: vale o da pasta nova e o antigo fica onde está
            try:
                os.replace(self.path / n, destino)
            except OSError:
                pass  # arquivo aberto em outro programa (Windows): tenta de novo na próxima leitura
        for nome_arq in ("LEIA-ME.md", "referencias.md"):
            origem = modelo_canal_dir() / nome_arq
            if origem.exists() and not (self.textos_dir / nome_arq).exists():
                shutil.copyfile(origem, self.textos_dir / nome_arq)

    def _ler(self, nome: str) -> Path | None:
        """O arquivo em regras-e-textos/ ou, se a migração não conseguiu mover, o antigo na raiz."""
        for p in (self.arquivo(nome), self.path / nome):
            if p.exists():
                return p
        return None

    def info(self) -> tuple[Canal, str]:
        doc = md.read(self.path / "canal.md")
        meta = dict(doc.meta)
        meta.setdefault("nome", self.slug)
        return Canal.model_validate(meta), md.sem_comentarios(doc.body)

    def regras(self) -> tuple[Regras, str]:
        global_doc = md.read(self.ws.root / "regras.md") if (self.ws.root / "regras.md").exists() else md.MarkdownDoc()
        p = self._ler("regras.md")
        doc = md.read(p) if p else md.MarkdownDoc()
        meta = md.deep_merge(global_doc.meta, doc.meta)
        body = "\n\n".join(b for b in (md.sem_comentarios(global_doc.body).strip(), md.sem_comentarios(doc.body).strip()) if b)
        return Regras.model_validate(meta), body

    def titulos(self) -> tuple[dict[str, Any], str]:
        p = self._ler("titulos.md")
        if p is None:
            return {"formulas": FORMULAS_PADRAO}, ""
        doc = md.read(p)
        return doc.meta, md.sem_comentarios(doc.body)

    def thumb(self) -> tuple[Thumb, str]:
        p = self._ler("thumb.md")
        if p is None:
            return Thumb(), THUMB_MD
        doc = md.read(p)
        return Thumb.model_validate(doc.meta), md.sem_comentarios(doc.body)

    def referencias(self) -> str:
        """referencias.md: os cortes do próprio canal que deram certo (régua de tom para a IA)."""
        p = self._ler("referencias.md")
        return md.sem_comentarios(md.read(p).body) if p else ""

    @property
    def projetos_dir(self) -> Path:
        return self.path / "projetos"

    def projetos(self) -> list["ProjetoWS"]:
        if not self.projetos_dir.exists():
            return []
        return [ProjetoWS(self, p) for p in sorted(self.projetos_dir.iterdir()) if (p / "projeto.yaml").exists()]

    def projeto(self, pid: str) -> "ProjetoWS":
        p = self.projetos_dir / pid
        if not (p / "projeto.yaml").exists():
            raise WorkspaceError(f"Projeto não encontrado: {pid}")
        return ProjetoWS(self, p)

    def criar_projeto(self, titulo: str, origem: Origem | None = None) -> "ProjetoWS":
        data = datetime.now().strftime("%Y-%m-%d")
        base = f"{data}-{slugify(titulo, 40)}"
        pid, n = base, 2
        while (self.projetos_dir / pid).exists():
            pid, n = f"{base}-{n}", n + 1
        p = self.projetos_dir / pid
        for sub in ("fonte", "analise", "clips"):
            (p / sub).mkdir(parents=True, exist_ok=True)
        proj = Projeto(
            id=pid,
            titulo=titulo,
            criado_em=agora(),
            origem=origem,
            etapas={e: Etapa() for e in ETAPAS},
        )
        write_yaml(p / "projeto.yaml", proj.model_dump(mode="json", exclude_none=True))
        return ProjetoWS(self, p)


class ProjetoWS:
    def __init__(self, canal: CanalWS, path: Path):
        self.canal = canal
        self.ws = canal.ws
        self.path = path
        self.id = path.name

    # caminhos padronizados
    @property
    def fonte_dir(self) -> Path:
        return self.path / "fonte"

    @property
    def analise_dir(self) -> Path:
        return self.path / "analise"

    @property
    def clips_dir(self) -> Path:
        return self.path / "clips"

    @property
    def audio_path(self) -> Path:
        return self.analise_dir / "audio.wav"

    @property
    def transcricao_path(self) -> Path:
        return self.analise_dir / "transcricao.json"

    @property
    def sinais_path(self) -> Path:
        return self.analise_dir / "sinais.json"

    @property
    def candidatos_path(self) -> Path:
        return self.analise_dir / "candidatos.json"

    @property
    def metadados_path(self) -> Path:
        return self.fonte_dir / "metadados.json"

    def video_path(self) -> Path | None:
        if not self.fonte_dir.exists():
            return None
        for p in sorted(self.fonte_dir.iterdir()):
            if p.stem == "video" and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}:
                return p
        return None

    def meta(self) -> Projeto:
        return Projeto.model_validate(read_yaml(self.path / "projeto.yaml"))

    def salvar_meta(self, proj: Projeto) -> None:
        write_yaml(self.path / "projeto.yaml", proj.model_dump(mode="json", exclude_none=True))

    def marcar(self, etapa: str, status: str, erro: str | None = None) -> None:
        proj = self.meta()
        proj.etapas[etapa] = Etapa(status=status, atualizado_em=agora(), erro=erro)
        self.salvar_meta(proj)

    def limpar_analise(self) -> None:
        """Apaga o que a análise gerou (sinais, candidatos, quadros, cache da IA) para refazê-la.

        Ficam o vídeo baixado, o áudio, a transcrição (a parte mais demorada) e os clips do usuário.
        """
        manter = {self.audio_path, self.transcricao_path}
        if self.analise_dir.exists():
            for item in self.analise_dir.iterdir():
                if item in manter:
                    continue
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
        proj = self.meta()
        etapas = ("sinais", "candidatos", "ranking") if self.transcricao_path.exists() else ("transcricao", "sinais", "candidatos", "ranking")
        for etapa in etapas:
            proj.etapas[etapa] = Etapa(atualizado_em=agora())
        self.salvar_meta(proj)

    def limpar_erros(self) -> None:
        """Volta para pendente as etapas em erro ou canceladas; não mexe nas ok nem nas rodando."""
        try:
            proj = self.meta()
        except Exception:  # noqa: BLE001 - projeto.yaml quebrado não impede o app de subir
            return
        sujas = [k for k, v in proj.etapas.items() if v.status in ("erro", "cancelado")]
        for k in sujas:
            proj.etapas[k] = Etapa(atualizado_em=agora())
        if sujas:
            self.salvar_meta(proj)

    # dados de análise
    def transcricao(self) -> dict | None:
        return read_json(self.transcricao_path)

    def temas(self) -> list[str]:
        """Os temas do vídeo para a base de referência (base_virais.detectar), pela transcrição.
        Guardados em memória enquanto a transcrição não muda."""
        from . import base_virais

        try:
            chave = self.transcricao_path.stat().st_mtime_ns
        except OSError:
            return []
        if getattr(self, "_temas", None) and self._temas[0] == chave:
            return list(self._temas[1])
        ids = base_virais.detectar(base_virais.texto_da_transcricao(self.transcricao()))
        self._temas = (chave, ids)
        return list(ids)

    def titulos(self) -> tuple[dict[str, Any], str]:
        """O titulos.md do canal completado pela base de referência nos temas deste vídeo."""
        from . import base_virais

        tmeta, tmd = self.canal.titulos()
        return base_virais.titulos_efetivos(tmeta, self.temas()), tmd

    def base_para_ia(self, partes: tuple[str, ...] = ("cortes", "titulos", "referencias"), limite: int = 9000) -> str:
        """A base de referência (temas deste vídeo) e as referências do próprio canal, para a IA."""
        from . import base_virais

        return "\n\n".join(x for x in (referencias_para_ia(self.canal.referencias()),
                                         base_virais.para_ia(self.temas(), partes, limite)) if x)

    def sinais(self) -> dict | None:
        return read_json(self.sinais_path)

    def candidatos(self) -> list[dict]:
        return read_json(self.candidatos_path, []) or []

    def salvar_candidatos(self, cands: list[dict]) -> None:
        write_json(self.candidatos_path, cands)

    def metadados(self) -> dict:
        return read_json(self.metadados_path, {}) or {}

    # clips
    def clips(self) -> list[tuple[Clip, Path]]:
        out = []
        if not self.clips_dir.exists():
            return out
        for p in sorted(self.clips_dir.iterdir()):
            if (p / "clip.yaml").exists():
                out.append((Clip.model_validate(read_yaml(p / "clip.yaml")), p))
        return out

    def clip(self, cid: str) -> tuple[Clip, Path]:
        p = self.clips_dir / cid
        if not (p / "clip.yaml").exists():
            raise WorkspaceError(f"Clip não encontrado: {cid}")
        return Clip.model_validate(read_yaml(p / "clip.yaml")), p

    def salvar_clip(self, clip: Clip) -> Path:
        p = self.clips_dir / clip.id
        p.mkdir(parents=True, exist_ok=True)
        write_yaml(p / "clip.yaml", clip.model_dump(mode="json"))
        return p

    def novo_clip_id(self, titulo: str) -> str:
        n = len(list(self.clips_dir.glob("*/clip.yaml"))) + 1
        while True:
            cid = f"{n:02d}-{slugify(titulo or 'clip', 40)}"
            if not (self.clips_dir / cid).exists():
                return cid
            n += 1

    def remover_clip(self, cid: str, tentativas: int = 10, espera: float = 0.3) -> None:
        """Apaga a pasta do clip (vídeo, prévia, thumbs, legendas). No Windows, um arquivo aberto
        (a prévia tocando) segura a pasta por um instante: tenta de novo e depois avisa."""
        import time

        p = self.clips_dir / cid
        if not p.exists() or self.clips_dir not in p.resolve().parents:
            raise WorkspaceError(f"Clip não encontrado: {cid}")
        for k in range(tentativas):
            try:
                shutil.rmtree(p)
                return
            except PermissionError:
                if k == tentativas - 1:
                    raise WorkspaceError(f"Não consegui apagar o clip {cid}: algum arquivo dele está aberto "
                                         "(feche a prévia do vídeo e tente de novo).") from None
                time.sleep(espera)


def iter_projetos(ws: Workspace) -> Iterator[ProjetoWS]:
    for c in ws.canais():
        yield from c.projetos()


def localizar_projeto(ws: Workspace, canal: str, projeto: str) -> ProjetoWS:
    return ws.canal(canal).projeto(projeto)
