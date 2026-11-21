from __future__ import annotations

import shutil
import subprocess
import types
from pathlib import Path

import pytest

TEM_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
precisa_ffmpeg = pytest.mark.skipif(not TEM_FFMPEG, reason="FFmpeg não instalado")

TEXTO = (
    "Ninguém te conta isso sobre dinheiro. Eu perdi quinhentos mil reais em um ano investindo errado. "
    "O segredo é simples: nunca coloque tudo num lugar só. Você sabia que a maioria das pessoas faz exatamente o contrário? "
    "Pois é. Agora deixa eu te contar a história completa, porque ela é absurda. Eu tinha vinte e dois anos e "
    "achei que sabia tudo sobre o mercado. Coloquei todo o dinheiro numa única empresa. Três meses depois, a empresa "
    "quebrou. Foi o pior erro da minha vida, mas foi também a maior lição."
)


def transcricao_falsa(texto: str = TEXTO, duracao: float = 36.0, inicio: float = 0.3, repetir: int = 1) -> dict:
    """Transcrição com tempos por palavra, pausas de 0,4 s no fim de cada frase."""
    palavras = (texto + " ") * repetir
    tokens = palavras.split()
    passo = duracao * repetir / (len(tokens) * 1.08)
    segs, atual, t = [], [], inicio
    for p in tokens:
        atual.append({"texto": p, "inicio": round(t, 3), "fim": round(t + passo * 0.85, 3), "prob": 0.9})
        t += passo
        if p.endswith((".", "?", ":")):
            t += 0.4
            segs.append({"inicio": atual[0]["inicio"], "fim": atual[-1]["fim"], "texto": " ".join(w["texto"] for w in atual), "palavras": atual})
            atual = []
    if atual:
        segs.append({"inicio": atual[0]["inicio"], "fim": atual[-1]["fim"], "texto": " ".join(w["texto"] for w in atual), "palavras": atual})
    return {"idioma": "pt", "duracao": round(t + 0.5, 3), "modelo": "falso", "dispositivo": "cpu", "segmentos": segs}


class _W:
    def __init__(self, w: dict):
        self.word, self.start, self.end, self.probability = " " + w["texto"], w["inicio"], w["fim"], w["prob"]


class _S:
    def __init__(self, s: dict):
        self.words = [_W(w) for w in s["palavras"]]
        self.start, self.end, self.text = s["inicio"], s["fim"], " " + s["texto"]


class WhisperFalso:
    def __init__(self, trans: dict | None = None):
        self.trans = trans or transcricao_falsa()

    def transcribe(self, audio, language=None, **kw):
        return iter(_S(s) for s in self.trans["segmentos"]), types.SimpleNamespace(duration=self.trans["duracao"], language="pt")


@pytest.fixture
def whisper_falso(monkeypatch):
    from clipator import transcribe

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso())


@pytest.fixture(scope="session")
def video_teste(tmp_path_factory) -> Path:
    """Vídeo 16:9 de 14 s com tom de áudio que varia de volume."""
    if not TEM_FFMPEG:
        pytest.skip("FFmpeg não instalado")
    p = tmp_path_factory.mktemp("midia") / "video.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=14",
         "-f", "lavfi", "-i", "sine=frequency=330:duration=14", "-af", "volume='if(between(t,6,7),1.0,0.2)':eval=frame",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(p)],
        check=True,
    )
    return p


@pytest.fixture
def ws(tmp_path):
    from clipator.workspace import Workspace

    return Workspace(tmp_path / "ws").init()


@pytest.fixture(autouse=True)
def _isolar_skills(tmp_path, monkeypatch):
    """Skills instaladas vão para uma pasta temporária, nunca para ~/.clipator.

    As CLIs de IA reais nunca rodam nos testes (sem internet): quem precisa usa uma falsa.
    """
    monkeypatch.setenv("CLIPATOR_SKILLS", str(tmp_path / "skills-instaladas"))
    monkeypatch.setenv("CLIPATOR_CLAUDE", str(tmp_path / "sem-claude"))
    monkeypatch.setenv("CLIPATOR_CODEX", str(tmp_path / "sem-codex"))
    monkeypatch.setenv("CLIPATOR_SONS", str(tmp_path / "sons"))
    monkeypatch.setenv("CLIPATOR_STICKERS", str(tmp_path / "stickers"))  # nunca o pacote do usuário
    monkeypatch.setenv("CLIPATOR_FONTES", str(tmp_path / "fontes-pacote"))  # nem as fontes baixadas dele
    monkeypatch.setenv("CLIPATOR_AMOSTRAS", str(tmp_path / "amostras"))  # amostras dos estilos fora do cache real
    monkeypatch.setenv("CLIPATOR_YT_COOKIES", str(tmp_path / "yt-cookies.txt"))  # nunca a conta do usuário
    monkeypatch.setenv("CLIPATOR_YT_PERFIL", str(tmp_path / "perfil-yt"))  # nem o perfil do navegador dele


# ---- direção de vídeo nas IAs falsas -------------------------------------------------------------------------------
def e_pedido_de_direcao(prompt: str) -> bool:
    return prompt.startswith("Você é o diretor de uma animação") or prompt.startswith("Esta é a direção de vídeo")


def direcao_de_roteiro(resp) -> dict:
    """Converte o roteiro antigo ({"cenas": [...]}) das IAs falsas na direção de vídeo, sem elenco, num cenário só."""
    from clipator.artes import curta

    lugar = curta.listas()["cenario"][0]
    cenas = (resp or {}).get("cenas") or [] if isinstance(resp, dict) else []
    return {"historia": {"assunto": "o assunto", "metafora": "", "logline": "a história do corte", "comeco": "", "meio": "", "fim": ""},
            "elenco": [], "cenarios": [{"id": "c1", "lugar": lugar, "descricao": ""}],
            "planos": [{"ancora": c.get("ancora", ""), "ate": c.get("ate", ""), "etiqueta": c.get("etiqueta", ""),
                        "o_que_mostra": c.get("descricao", ""), "cenario": "c1", "em_cena": [], "plano": "medio", "movimento": "fixo",
                        "transicao": "corte", "dado": c.get("dado", ""), "balao": c.get("balao", "")} for c in cenas if isinstance(c, dict)]}


def com_direcao(resposta):
    """Embrulha a resposta de uma IA falsa: o pedido de direção é respondido com o roteiro que ela daria."""
    def r(prompt):
        if e_pedido_de_direcao(prompt):
            if callable(resposta):
                propria = resposta(prompt)
                if isinstance(propria, dict) and "historia" in propria:
                    return propria
            base = resposta("Escreva o roteiro") if callable(resposta) else resposta
            return base if isinstance(base, dict) and "planos" in base else direcao_de_roteiro(base)
        return resposta(prompt) if callable(resposta) else resposta
    return r
