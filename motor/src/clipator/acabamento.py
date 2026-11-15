"""Acabamento do passo 5: música de fundo e ajustes de imagem em cima do clip já gerado.

O clip gerado não muda (formato, estilo e edição ficam como estão). O acabamento é uma passada a mais
do FFmpeg sobre o vídeo pronto e vira uma versão do clip, igual às edições com IA:
clips/<id>/edicoes/<data-hora>-acabamento/ com saida-acabada.mp4, acabamento.json (os ajustes e o
vídeo de base) e notas.md (o resumo em texto). Ao terminar, essa versão passa a ser a saída do clip;
"Voltar ao original" e a lista de versões continuam funcionando como antes.

Refazer o acabamento parte sempre do vídeo de base guardado no acabamento.json, nunca de um vídeo
que já tem acabamento, para a música não entrar duas vezes.

Sem IA e offline: só FFmpeg. As músicas ficam no canal (canais/<canal>/assets/musicas/) para servirem
a todos os clips dele.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from . import media
from .edicao_ia import EXT_VIDEO, PASTA
from .workspace import ProjetoWS, slugify

SUFIXO = "-acabamento"
ARQUIVO = "acabamento.json"
VIDEO = "saida-acabada.mp4"
PASTA_MUSICAS = ("assets", "musicas")
EXT_MUSICA = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")
LIMITE_MUSICA = 60 * 1024 * 1024  # 60 MB


class ErroAcabamento(ValueError):
    pass


class Musica(BaseModel):
    arquivo: str = Field(description="Nome do arquivo em canais/<canal>/assets/musicas/")
    volume: float = Field(0.2, ge=0, le=1, description="Volume da música (0 a 1) em relação à fala")
    inicio: float = Field(0, ge=0, description="De que segundo da música começar")
    entrada: float = Field(1.0, ge=0, le=10, description="Fade in, em segundos")
    saida: float = Field(1.5, ge=0, le=10, description="Fade out no fim do clip, em segundos")
    abaixar_na_fala: bool = Field(True, description="Abaixa a música sozinha quando alguém fala")
    repetir: bool = Field(True, description="Repete a música se ela for mais curta que o clip")


class Imagem(BaseModel):
    brilho: float = Field(0, ge=-0.5, le=0.5)
    contraste: float = Field(1, ge=0.5, le=2)
    saturacao: float = Field(1, ge=0, le=2.5)
    temperatura: float = Field(0, ge=-1, le=1, description="-1 frio (azulado) a 1 quente (alaranjado)")
    nitidez: float = Field(0, ge=0, le=1.5)

    def neutra(self) -> bool:
        return self == Imagem()


class Acabamento(BaseModel):
    musica: Musica | None = None
    imagem: Imagem = Field(default_factory=Imagem)
    manter_som_original: float = Field(1.0, ge=0, le=1.5, description="Volume do som do clip (fala)")

    def vazio(self) -> bool:
        return self.musica is None and self.imagem.neutra() and abs(self.manter_som_original - 1) < 1e-6


# ---- músicas do canal -----------------------------------------------------------------
def pasta_musicas(pasta_canal: Path) -> Path:
    return pasta_canal.joinpath(*PASTA_MUSICAS)


def listar_musicas(pasta_canal: Path) -> list[dict[str, Any]]:
    d = pasta_musicas(pasta_canal)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in EXT_MUSICA:
            out.append({"arquivo": p.name, "nome": p.stem.replace("-", " "), "bytes": p.stat().st_size})
    return out


def salvar_musica(pasta_canal: Path, nome: str, dados: bytes) -> dict[str, Any]:
    """Grava uma música enviada pelo usuário. Um nome repetido ganha número no fim (não apaga a antiga)."""
    if not dados:
        raise ErroAcabamento("O arquivo está vazio.")
    if len(dados) > LIMITE_MUSICA:
        raise ErroAcabamento(f"O arquivo tem {len(dados) / 1e6:.0f} MB; o limite é {LIMITE_MUSICA // (1024 * 1024)} MB.")
    ext = Path(nome).suffix.lower()
    if ext not in EXT_MUSICA:
        raise ErroAcabamento(f"Formato não aceito. Use {', '.join(e[1:] for e in EXT_MUSICA)}.")
    d = pasta_musicas(pasta_canal)
    d.mkdir(parents=True, exist_ok=True)
    base = slugify(Path(nome).stem)
    alvo, n = d / f"{base}{ext}", 2
    while alvo.exists():
        alvo, n = d / f"{base}-{n}{ext}", n + 1
    alvo.write_bytes(dados)
    try:
        info = media.probe(alvo)
    except media.FFmpegError:
        info = None
    if info is not None and (not info.tem_audio or info.duracao <= 0):
        alvo.unlink(missing_ok=True)
        raise ErroAcabamento("Não achei áudio nesse arquivo.")
    return {"arquivo": alvo.name, "nome": alvo.stem.replace("-", " "), "duracao": info.duracao if info else None}


def caminho_musica(pasta_canal: Path, arquivo: str) -> Path:
    d = pasta_musicas(pasta_canal).resolve()
    p = (d / arquivo).resolve()
    if p.parent != d or not p.is_file() or p.suffix.lower() not in EXT_MUSICA:
        raise ErroAcabamento(f"Música não encontrada: {arquivo}")
    return p


# ---- vídeo de base e estado salvo ---------------------------------------------------------
def _ler(pasta_versao: Path) -> dict[str, Any] | None:
    try:
        return json.loads((pasta_versao / ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def base_do_clip(projeto: ProjetoWS, clip_id: str) -> tuple[str, dict[str, Any] | None]:
    """O vídeo onde o acabamento é aplicado (relativo à pasta do clip) e o acabamento em uso, se houver.

    Se a saída escolhida já é um acabamento, a base é a que ele guardou (assim a música não entra duas vezes).
    """
    clip, pasta = projeto.clip(clip_id)
    if clip.versao:
        v = pasta / clip.versao
        if v.parent.name.endswith(SUFIXO) and (salvo := _ler(v.parent)):
            base = str(salvo.get("base") or "saida.mp4")
            if (pasta / base).is_file():
                return base, salvo
        if v.is_file():
            return clip.versao, None
    if (pasta / "saida.mp4").is_file():
        return "saida.mp4", None
    raise ErroAcabamento("O clip ainda não foi gerado. Gere o clip antes do acabamento.")


def estado(projeto: ProjetoWS, clip_id: str) -> dict[str, Any]:
    """O que a tela do acabamento precisa: vídeo de base, ajustes em uso (ou padrão) e as músicas do canal."""
    base, salvo = base_do_clip(projeto, clip_id)
    _, pasta = projeto.clip(clip_id)
    ajustes = Acabamento.model_validate(salvo["ajustes"]) if salvo and salvo.get("ajustes") else Acabamento()
    return {
        "base": base,
        "base_caminho": (pasta / base).relative_to(projeto.ws.root).as_posix(),
        "ajustes": ajustes.model_dump(mode="json"),
        "em_uso": bool(salvo),
        "musicas": listar_musicas(projeto.canal.path),
        "pasta_musicas": pasta_musicas(projeto.canal.path).relative_to(projeto.ws.root).as_posix(),
    }


# ---- filtros do FFmpeg ----------------------------------------------------------------
def filtro_imagem(img: Imagem, filtros: set[str] | None = None) -> str | None:
    """Cadeia -vf para os ajustes de imagem (None se nada mudou)."""
    if img.neutra():
        return None
    filtros = media.filtros_ffmpeg() if filtros is None else filtros
    partes: list[str] = []
    if abs(img.brilho) > 1e-3 or abs(img.contraste - 1) > 1e-3 or abs(img.saturacao - 1) > 1e-3:
        partes.append(f"eq=brightness={img.brilho:.3f}:contrast={img.contraste:.3f}:saturation={img.saturacao:.3f}")
    if abs(img.temperatura) > 1e-3:
        if not filtros or "colortemperature" in filtros:
            # 6500 K é neutro; menos kelvin puxa para o laranja, mais para o azul
            k = 6500 - img.temperatura * 3000
            partes.append(f"colortemperature=temperature={k:.0f}:mix=1:pl=0.5")
        else:  # FFmpeg antigo (antes do 5.1): mesmo efeito, aproximado, pelos meios-tons
            q = 0.18 * img.temperatura
            partes.append(f"colorbalance=rm={q:.3f}:bm={-q:.3f}")
    if img.nitidez > 1e-3:
        partes.append(f"unsharp=5:5:{img.nitidez:.2f}:5:5:0")
    partes.append("format=yuv420p")
    return ",".join(partes)


def filtro_audio(m: Musica | None, duracao: float, tem_audio: bool, som_original: float = 1.0) -> str:
    """filter_complex do áudio: [0:a] é o som do clip, [1:a] a música. Sai em [a]."""
    voz = f"[0:a]volume={som_original:.3f}" if tem_audio else None
    if m is None:
        return f"{voz}[a]" if voz else "anullsrc=r=48000:cl=stereo[a]"
    fim = max(0.0, duracao - m.saida)
    mus = [f"atrim=0:{duracao:.3f}", "asetpts=PTS-STARTPTS", "aresample=48000", f"volume={m.volume:.3f}"]
    if m.entrada > 0:
        mus.append(f"afade=t=in:st=0:d={m.entrada:.2f}")
    if m.saida > 0:
        mus.append(f"afade=t=out:st={fim:.3f}:d={m.saida:.2f}")
    cadeia = [f"[1:a]{','.join(mus)}[mus]"]
    if not voz:
        return cadeia[0].replace("[mus]", "[a]")
    voz += ",aresample=48000"
    if m.abaixar_na_fala:
        # a fala comanda o compressor da música (ducking): fala alta, música baixa
        cadeia += [f"{voz},asplit=2[voz][sc]",
                   "[mus][sc]sidechaincompress=threshold=0.03:ratio=8:attack=30:release=500:makeup=1[musb]",
                   "[voz][musb]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[a]"]
    else:
        cadeia += [f"{voz}[voz]", "[voz][mus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[a]"]
    return ";".join(cadeia)


def montar_comando(entrada: Path, saida: Path, ac: Acabamento, duracao: float, tem_audio: bool,
                   musica: Path | None, filtros: set[str] | None = None) -> list[str]:
    """Argumentos do FFmpeg (sem o binário e as opções gerais, que o media.run_ffmpeg põe)."""
    args = ["-i", str(entrada)]
    if ac.musica is not None and musica is not None:
        if ac.musica.repetir:
            args += ["-stream_loop", "-1"]
        if ac.musica.inicio > 0:
            args += ["-ss", f"{ac.musica.inicio:.3f}"]
        args += ["-i", str(musica)]
    vf = filtro_imagem(ac.imagem, filtros)
    if vf:
        args += ["-filter_complex", f"[0:v]{vf}[v];{filtro_audio(ac.musica, duracao, tem_audio, ac.manter_som_original)}",
                 "-map", "[v]", "-map", "[a]", *media.video_encode_args("final")]
    else:  # imagem igual: copia o vídeo, só refaz o áudio (rápido)
        args += ["-filter_complex", filtro_audio(ac.musica, duracao, tem_audio, ac.manter_som_original),
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy"]
    args += ["-c:a", "aac", "-b:a", "192k", "-t", f"{duracao:.3f}", "-movflags", "+faststart", str(saida)]
    return args


def notas(ac: Acabamento) -> str:
    linhas = ["# Acabamento", ""]
    if ac.musica:
        m = ac.musica
        linhas.append(f"- Música: {m.arquivo} a {m.volume * 100:.0f}%"
                      + (f", a partir de {m.inicio:.1f} s" if m.inicio else "")
                      + (", abaixando na fala" if m.abaixar_na_fala else "")
                      + f", fade {m.entrada:.1f} s / {m.saida:.1f} s")
    if abs(ac.manter_som_original - 1) > 1e-6:
        linhas.append(f"- Som do clip a {ac.manter_som_original * 100:.0f}%")
    i = ac.imagem
    ajustes = [(n, v) for n, v, neutro in (("brilho", i.brilho, 0), ("contraste", i.contraste, 1), ("saturação", i.saturacao, 1),
                                          ("temperatura", i.temperatura, 0), ("nitidez", i.nitidez, 0)) if abs(v - neutro) > 1e-3]
    if ajustes:
        linhas.append("- Imagem: " + ", ".join(f"{n} {v:+.2f}" if n in ("brilho", "temperatura") else f"{n} {v:.2f}" for n, v in ajustes))
    return "\n".join(linhas) + "\n"


# ---- aplicar --------------------------------------------------------------------------
def aplicar(projeto: ProjetoWS, clip_id: str, ac: Acabamento, progresso: Callable[[float, str], None] | None = None,
            cancelar: threading.Event | None = None, agora: datetime | None = None) -> dict[str, Any]:
    """Gera a versão com acabamento e a escolhe como saída do clip. Acabamento vazio volta para a base."""
    clip, pasta = projeto.clip(clip_id)
    base, _ = base_do_clip(projeto, clip_id)
    if ac.vazio():
        clip.versao = None if base == "saida.mp4" else base
        projeto.salvar_clip(clip)
        return {"versao": clip.versao, "base": base, "vazio": True}
    entrada = pasta / base
    if entrada.suffix.lower() not in EXT_VIDEO:
        raise ErroAcabamento(f"Vídeo de base inválido: {base}")
    musica = caminho_musica(projeto.canal.path, ac.musica.arquivo) if ac.musica else None
    info = media.probe(entrada)
    if info.duracao <= 0:
        raise ErroAcabamento("Não consegui ler a duração do clip gerado.")
    nome = (agora or datetime.now()).strftime("%Y%m%d-%H%M%S") + SUFIXO
    destino = pasta / PASTA / nome
    destino.mkdir(parents=True, exist_ok=True)
    final = destino / VIDEO
    tmp = destino / ("parcial-" + VIDEO)
    try:
        media.run_ffmpeg(montar_comando(entrada, tmp, ac, info.duracao, info.tem_audio, musica), info.duracao,
                         progresso, cancelar, "acabamento")
        media.substituir(tmp, final)
    except BaseException:
        media.apagar_parcial(tmp)
        if not any(destino.iterdir()):
            destino.rmdir()
        raise
    (destino / ARQUIVO).write_text(json.dumps({"base": base, "ajustes": ac.model_dump(mode="json")}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    (destino / "notas.md").write_text(notas(ac), encoding="utf-8")
    clip, _ = projeto.clip(clip_id)
    clip.versao = final.relative_to(pasta).as_posix()
    projeto.salvar_clip(clip)
    return {"versao": clip.versao, "base": base, "pasta": destino.relative_to(projeto.ws.root).as_posix()}
