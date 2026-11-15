"""Testes com FFmpeg, fila de jobs, IA falsa, API e MCP."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
from pathlib import Path
import threading
import time

import pytest

from clipator import media, pipeline, signals
from clipator.ai.adapter import ClaudeCLI, CodexCLI, ErroIA, _schema_estrito, parse_json_loose
from clipator.jobs import FilaJobs
from clipator.media import Cancelado
from clipator.models import Clip, Origem
from clipator.workspace import write_json

from .conftest import precisa_ffmpeg, transcricao_falsa


# ---- IA -----------------------------------------------------------------------
def test_parse_json_loose():
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Claro! {"a": [1]} pronto') == {"a": [1]}
    with pytest.raises(ErroIA):
        parse_json_loose("nada")


def test_schema_estrito_para_codex():
    s = _schema_estrito({"type": "object", "properties": {"a": {"type": "object", "properties": {"b": {"type": "string"}}}}})
    assert s["additionalProperties"] is False and s["required"] == ["a"]
    assert s["properties"]["a"]["required"] == ["b"]


def _cli_falsa(tmp_path, nome: str, saida: dict) -> str:
    """Script que imita a CLI: lê o prompt do stdin e imprime JSON."""
    script = tmp_path / nome
    corpo = json.dumps(saida)
    if nome == "codex":
        # escreve no arquivo passado em -o
        code = (
            "import sys, json\nargs=sys.argv\nsys.stdin.read()\n"
            f"open(args[args.index('-o')+1],'w').write({corpo!r})\n"
        )
    else:
        code = f"import sys\nsys.stdin.read()\nprint({json.dumps({'type': 'result', 'is_error': False, 'structured_output': saida})!r})\n"
    script.write_text(f"#!{sys.executable}\n{code}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="script falso usa shebang")
def test_adaptadores_cli(tmp_path):
    claude = ClaudeCLI(binario=_cli_falsa(tmp_path, "claude", {"nota": 7}))
    assert claude.run_json("oi", {"type": "object"}) == {"nota": 7}
    codex = CodexCLI(binario=_cli_falsa(tmp_path, "codex", {"nota": 8}))
    assert codex.run_json("oi", {"type": "object", "properties": {"nota": {"type": "integer"}}}) == {"nota": 8}


def test_ranking_com_ia_falsa(ws, monkeypatch):
    from clipator.ai import ranking

    trans = transcricao_falsa(repetir=2)
    from clipator import candidates
    from clipator.models import Regras

    regras = Regras(duracao_min=10, duracao_max=25)
    cands = candidates.gerar(trans, None, {}, regras)

    class Falso:
        nome = "falso"

        def run_json(self, prompt, schema, cancelar=None):
            assert "c01" in prompt and "RUBRICA" not in prompt
            return {"candidatos": [{"id": cands[-1]["id"], "nota": 99, "titulos": ["T1", "T2", "T3"], "gancho": "G",
                                    "ajuste_inicio": 0, "ajuste_fim": 0, "motivo": "bom", "destaques": ["dinheiro"]}]}

    out = ranking.ranquear(cands, trans, Falso(), regras)
    assert out[0]["id"] == cands[-1]["id"] and out[0]["nota"] == 99 and out[0]["titulos"][0] == "T1"
    assert out[0]["ia"]["destaques"] == ["dinheiro"]


def test_login_expirado_vira_erro_de_login():
    from clipator.ai.adapter import ErroLoginIA, _checar_login

    with pytest.raises(ErroLoginIA, match="Rode claude no terminal e faça /login"):
        _checar_login("claude", "Failed to authenticate. API Error: 401 OAuth session expired")
    with pytest.raises(ErroLoginIA):
        _checar_login("codex", "Request failed with status 401")
    _checar_login("claude", "timeout de rede")  # outros erros não viram erro de login
    _checar_login("claude", "erro 4012 no servidor")  # 401 só como número inteiro


def test_ia_sem_login_cai_para_a_outra():
    from clipator.ai.adapter import AdapterComReserva, ErroLoginIA

    class SemLogin:
        nome = "claude"

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None):
            raise ErroLoginIA("O login do Claude Code expirou.")

    class Responde:
        nome = "codex"

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None):
            return {"ok": True}

    logs = []
    ad = AdapterComReserva(SemLogin(), ["codex"], log=logs.append, fabrica=lambda n, t: Responde(),
                           logado=lambda n: True)
    assert ad.run_json("p", {}) == {"ok": True}
    assert ad.nome == "codex" and logs == ["Claude sem login; usando o Codex"]

    sozinho = AdapterComReserva(SemLogin(), ["codex"], fabrica=lambda n, t: Responde(), logado=lambda n: False)
    with pytest.raises(ErroLoginIA, match="expirou"):
        sozinho.run_json("p", {})


def test_ia_reserva_nao_engole_outros_erros():
    from clipator.ai.adapter import AdapterComReserva

    class Quebra:
        nome = "claude"

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None):
            raise ErroIA("A IA não devolveu JSON válido")

    usados = []
    ad = AdapterComReserva(Quebra(), ["codex"], fabrica=lambda n, t: usados.append(n), logado=lambda n: True)
    with pytest.raises(ErroIA, match="JSON"):
        ad.run_json("p", {})
    assert usados == []


def _fila_com_login(tmp_path, logado, tempo=5.0):
    """Fila com um job que usa a IA com reserva: o Claude falso perde o login até `logado()` virar True."""
    from clipator.ai.adapter import AdapterComReserva, ErroLoginIA

    chamadas = []

    class Claude:
        nome = "claude"

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None):
            chamadas.append("claude")
            if not logado():
                raise ErroLoginIA("O login do Claude Code expirou.")
            return {"ia": "claude"}

    class Codex:
        nome = "codex"

        def disponivel(self):
            return True

        def run_json(self, prompt, schema, cancelar=None):
            chamadas.append("codex")
            return {"ia": "codex"}

    fila = FilaJobs(tmp_path / "j.sqlite3")
    fila.tempo_login, fila.intervalo_login = tempo, 0.02

    def job(params, ctx):
        ad = AdapterComReserva(Claude(), ["codex"], log=ctx.log, fabrica=lambda n, t: Codex(), logado=lambda n: True,
                               esperar_login=lambda nome: ctx.esperar_login(nome, logado))
        return ad.run_json("p", {})

    fila.registrar("ranking", job)
    return fila, chamadas


def _esperar_status(fila, jid, campo, valor, timeout=5):
    fim = time.time() + timeout
    while time.time() < fim:
        if fila.obter(jid).get(campo) == valor:
            return
        time.sleep(0.01)
    raise AssertionError(f"{campo} não virou {valor}")


def test_job_espera_login_e_continua_pelo_claude(tmp_path):
    estado = {"logado": False}
    fila, chamadas = _fila_com_login(tmp_path, lambda: estado["logado"])
    jid = fila.enviar("ranking")
    _esperar_status(fila, jid, "aguardando", "login_claude")
    assert "aguardando login do Claude" in fila.obter(jid)["mensagem"]
    estado["logado"] = True  # o usuário entrou no navegador
    j = fila.esperar(jid, 5)
    assert j["status"] == "ok" and j["resultado"] == {"ia": "claude"} and j["aguardando"] is None
    assert chamadas == ["claude", "claude"] and "login do Claude feito" in j["log"]
    fila.fechar()


def test_job_sem_login_cai_para_o_codex_no_tempo_ou_pelo_botao(tmp_path):
    fila, chamadas = _fila_com_login(tmp_path, lambda: False, tempo=0.1)
    j = fila.esperar(fila.enviar("ranking"), 5)
    assert j["resultado"] == {"ia": "codex"} and chamadas == ["claude", "codex"]
    assert "usando o Codex" in j["log"]
    fila.fechar()

    fila, chamadas = _fila_com_login(tmp_path / "b", lambda: False)
    jid = fila.enviar("ranking")
    _esperar_status(fila, jid, "aguardando", "login_claude")
    assert fila.usar_outra_ia(jid)
    assert fila.esperar(jid, 5)["resultado"] == {"ia": "codex"}
    fila.fechar()


def test_cancelar_durante_a_espera_do_login(tmp_path):
    fila, chamadas = _fila_com_login(tmp_path, lambda: False)
    jid = fila.enviar("ranking")
    _esperar_status(fila, jid, "aguardando", "login_claude")
    fila.cancelar(jid)
    j = fila.esperar(jid, 5)
    assert j["status"] == "cancelado" and chamadas == ["claude"]
    fila.fechar()


# ---- pacote de postagem -------------------------------------------------------------
def test_postagem_respeita_os_limites_de_cada_plataforma():
    from clipator import plataformas, postagem

    base = {
        "titulo": "X" * 130,
        "blocos": {"titulo": "Título curto", "resumo": "Resumo dito no corte.", "contexto": "Trecho de: Podcast"},
        "hashtags": [f"tema {i}" for i in range(20)] + ["#shorts"],
        "tags": [f"tag numero {i:03d}" for i in range(60)],
    }
    yt, avisos = postagem.validar(plataformas.PLATAFORMAS["youtube-shorts"], base)
    assert len(yt["titulo"]) <= 100 and yt["titulo"].endswith("…")
    assert len(yt["hashtags"]) == 15 and yt["hashtags"][0] == "#shorts" and "#tema0" in yt["hashtags"]
    assert sum(len(t) for t in yt["tags"]) + len(yt["tags"]) - 1 <= 500
    assert any("Título" in a for a in avisos) and any("hashtags" in a for a in avisos) and any("tags" in a for a in avisos)
    reels, avisos_r = postagem.validar(plataformas.PLATAFORMAS["instagram-reels"], base)
    assert reels["titulo"] is None and reels["tags"] == [] and len(reels["hashtags"]) == 5
    assert reels["descricao"].startswith("Título curto")  # sem campo de título: ele abre a legenda
    longo, _ = postagem.validar(plataformas.PLATAFORMAS["tiktok"], {**base, "blocos": {"resumo": "a " * 3000}})
    assert len(longo["descricao"]) <= 4000


def test_postagem_da_ia_sem_prova_no_corte_e_descartada():
    from clipator import postagem

    texto = "Eu perdi 500 mil reais em um ano investindo errado. Ninguém me avisou do risco da corretora."
    base = {"titulo": "O ERRO que custou caro", "blocos": {"titulo": "O ERRO que custou caro", "resumo": "“dito”"},
            "hashtags": ["dinheiro"], "tags": ["dinheiro"]}
    boa = {"titulo": "Perdeu 500 mil em um ano", "resumo": "Ele perdeu 500 mil em um ano investindo errado.",
           "prova": "perdi 500 mil reais em um ano", "hashtags": ["#investimento"], "tags": ["investir"]}
    p, avisos = postagem._com_ia(base, boa, texto, True, "claude")
    assert p["titulo"] == "Perdeu 500 mil em um ano" and p["blocos"]["resumo"].startswith("Ele perdeu")
    assert p["hashtags"][0] == "#investimento" and p["fonte"] == "claude" and not avisos
    inventada = {**boa, "resumo": "Ele perdeu 2 milhões e foi preso.", "prova": "foi preso pela polícia",
                 "titulo": "Preso pela Polícia Federal"}
    p, avisos = postagem._com_ia(base, inventada, texto, True, "claude")
    assert p["blocos"]["resumo"] == "“dito”" and p["titulo"] == "O ERRO que custou caro"
    assert len(avisos) == 2


@precisa_ffmpeg
def test_postagem_salva_um_pacote_por_plataforma(ws, video_teste, monkeypatch):
    from clipator import postagem, transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    _, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="podcast-limpo")[0]
    pipeline.renderizar(p, clip.id)
    pasta = p.clips_dir / clip.id
    assert (pasta / "legenda.srt").exists() and (pasta / "legenda.vtt").exists()
    pacotes = postagem.carregar(p, clip.id)
    assert set(pacotes) == {"youtube-shorts", "instagram-reels", "tiktok"}
    shorts = pacotes["youtube-shorts"]
    assert "#shorts" in shorts["hashtags"] and shorts["legenda"] == "legenda.srt"
    assert (pasta / "postagem" / "tiktok.txt").read_text(encoding="utf-8").startswith("# TikTok")
    assert (pasta / "postagem.txt").exists()

# ---- efeitos sonoros sintetizados -------------------------------------------------------
DURACOES_SONS = {"whoosh": 0.6, "swoosh-reverso": 0.45, "impacto": 0.9, "riser": 1.5, "pop": 0.15,
                 "click": 0.05, "ding": 1.2, "glitch": 0.4}


def test_sons_sintetizados_tem_a_duracao_e_nao_estouram(tmp_path, monkeypatch):
    import wave

    import numpy as np

    from clipator import sons

    monkeypatch.setenv("CLIPATOR_SONS", str(tmp_path / "sons"))
    assert set(sons.NOMES) == set(DURACOES_SONS)
    for nome, dur in DURACOES_SONS.items():
        x = sons.sintetizar(nome)
        assert abs(len(x) / sons.TAXA - dur) < 0.02, nome
        pico = float(np.max(np.abs(x)))
        assert 0.6 < pico <= sons.PICO + 1e-6, nome  # -3 dBFS, longe de estourar
        assert np.array_equal(x, sons.sintetizar(nome))  # sai sempre igual
        p = sons.caminho(nome)
        with wave.open(str(p), "rb") as wf:
            assert wf.getframerate() == 48000 and wf.getnchannels() == 1
            assert abs(wf.getnframes() / 48000 - dur) < 0.02
    antes = sons.caminho("pop").stat().st_mtime_ns
    assert sons.caminho("pop").stat().st_mtime_ns == antes  # cache: não regrava
    with pytest.raises(KeyError):
        sons.sintetizar("trovao")


def test_eventos_dos_sons_no_tempo_do_clip():
    import re as _re

    from clipator import sons

    pals = [{"texto": t, "inicio": i * 0.5, "fim": i * 0.5 + 0.4} for i, t in enumerate(
        "o ERRO foi grande e o ERRO de novo depois mais um ERRO".split())]
    evs = sons.eventos({"cartela": "impacto", "corte": "whoosh", "destaque": "pop", "fim": "ding"}, 20.0,
                       [(10.0, 15.0), (18.0, 30.0)], pals, _re.compile("ERRO"), cartela=True)
    assert ("cartela", 0.0) in evs and ("corte", 4.85) in evs and ("fim", 19.0) in evs
    destaques = [t for e, t in evs if e == "destaque"]
    assert destaques[0] == 0.5 and all(b - a >= sons.INTERVALO_DESTAQUE for a, b in zip(destaques, destaques[1:]))
    assert sons.eventos({"cartela": "impacto"}, 20.0, [(0, 20)], [], None, cartela=False) == []


@precisa_ffmpeg
def test_render_com_sons_do_estilo(ws, video_teste, monkeypatch, tmp_path):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setenv("CLIPATOR_SONS", str(tmp_path / "sons"))
    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    c, p = _projeto_com_video(ws, video_teste)
    (c.path / "estilos").mkdir(exist_ok=True)
    (c.path / "estilos" / "com-sons.md").write_text(
        "---\nnome: com sons\nsons:\n  cartela: impacto\n  corte: whoosh\n  destaque: pop\nvolume_sons: 0.6\n"
        "legenda:\n  palavras_destaque: [dinheiro]\n---\n", encoding="utf-8")
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="com-sons", cartela=True)[0]
    clip.cortes_internos = [(clip.inicio + 2.0, clip.inicio + 2.6)]
    p.salvar_clip(clip)
    r = pipeline.renderizar(p, clip.id, preview=True)
    info = media.probe(r.video)
    assert info.tem_audio and info.duracao == pytest.approx(clip.fim - clip.inicio - 0.6, abs=0.25)
    assert (tmp_path / "sons" / "impacto-v1.wav").exists() and (tmp_path / "sons" / "whoosh-v1.wav").exists()

# ---- editar com a IA do usuário (CLI interativa) -----------------------------------------
def _clip_para_editar(ws):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(p.transcricao_path, transcricao_falsa())
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=20, titulo="O ERRO que custou caro", formato="9:16",
                       plataforma="tiktok", cortes_internos=[(5.0, 6.0)]))
    return p


def test_pedido_de_edicao_tem_o_contexto_e_as_regras(ws):
    from datetime import datetime

    from clipator import edicao_ia

    p = _clip_para_editar(ws)
    pasta, texto = edicao_ia.montar_pedido(p, "01-x", "Adicione b-roll", agora=datetime(2026, 11, 2, 17, 0, 0))
    assert pasta == p.clips_dir / "01-x" / "edicoes" / "20261102-170000" and (pasta / "pedido.md").read_text(encoding="utf-8") == texto
    assert "Adicione b-roll" in texto and "NUNCA altere" in texto and "saida-editada.mp4" in texto and "notas.md" in texto
    assert str(pasta) in texto and "saida.mp4" in texto and "0:00:05–0:00:06" in texto
    assert "TikTok" in texto and "22% de baixo" in texto  # zona segura da plataforma do clip
    assert "a maioria das pessoas faz exatamente o contrário" in texto  # transcrição do trecho
    assert "renderizar" in texto and "clip: 01-x" in texto  # ferramentas do MCP


def test_comando_da_cli_sem_shell_e_sem_pular_permissoes(ws, monkeypatch):
    import subprocess

    from clipator import edicao_ia

    frase = "Leia o arquivo edicoes/x/pedido.md e siga o que ele pede."
    assert edicao_ia.comando("claude", "abrir", frase, "claude") == ["claude", frase]
    assert edicao_ia.comando("claude", "continuar", frase, "claude") == ["claude", "--continue", frase]
    assert edicao_ia.comando("codex", "abrir", frase, "codex") == ["codex", frase]
    assert edicao_ia.comando("codex", "continuar", frase, "codex") == ["codex", "resume", "--last", frase]
    for a in ("claude", "codex"):
        for m in ("abrir", "continuar"):
            args = " ".join(edicao_ia.comando(a, m, frase, a))
            assert not any(x in args for x in ("dangerously", "full-auto", "yolo", "bypass", "--yes"))

    p = _clip_para_editar(ws)
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: chamadas.append((cmd, kw)))
    monkeypatch.setattr(edicao_ia, "_binario", lambda a: f"C:/bin/{a}.exe")
    if sys.platform.startswith("linux"):  # o runner do CI não tem terminal gráfico instalado
        monkeypatch.setattr(edicao_ia.shutil, "which", lambda n: "/usr/bin/xterm" if n == "xterm" else None)
    maldoso = 'teste"; rm -rf / & calc.exe | del *'
    r = edicao_ia.abrir(p, "01-x", "claude", "abrir", maldoso)
    cmd, kw = chamadas[0]
    assert isinstance(cmd, list) and "shell" not in kw
    assert sys.platform != "win32" or not {"stdin", "stdout", "stderr"} & set(kw)  # o console é da CLI
    assert all("rm -rf" not in x and "calc" not in x for x in cmd)  # o texto do usuário não vai para a linha de comando
    assert maldoso in Path(r["pasta"], "pedido.md").read_text(encoding="utf-8")  # vai só para o arquivo
    assert cmd[-1].startswith("Leia o arquivo edicoes/") and kw["cwd"].endswith("01-x") or sys.platform != "win32"


def test_pedido_do_passo2_vira_um_lote_quando_o_render_termina(ws, monkeypatch):
    import subprocess
    from datetime import datetime

    from clipator import edicao_ia
    from clipator.jobs import ContextoJob
    from clipator.models import PedidoIA
    from clipator.service import Servico

    p = _clip_para_editar(ws)
    p.salvar_clip(Clip(id="02-y", inicio=30, fim=50, titulo="Segundo"))
    maldoso = 'deixe mais forte"; del *.* & calc'
    for cid in ("01-x", "02-y"):
        c, _ = p.clip(cid)
        c.pedido_ia = PedidoIA(agente="claude", texto=maldoso)
        p.salvar_clip(c)
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: chamadas.append((cmd, kw)))
    monkeypatch.setattr(edicao_ia, "_binario", lambda a: f"C:/bin/{a}.exe")
    monkeypatch.setenv("CLIPATOR_TERMINAL", "conhost")
    # o terminal de cada sistema tem teste próprio (lancador); aqui só importa o comando da CLI
    monkeypatch.setattr(edicao_ia, "lancador", lambda args, pasta, plataforma=None: (args, {"cwd": str(pasta)}))

    srv = Servico.__new__(Servico)
    logs = []
    ctx = ContextoJob.__new__(ContextoJob)
    ctx.log = logs.append  # type: ignore[method-assign]
    r = srv._conversa_do_lote(p, ["01-x", "02-y"], ctx)
    assert not chamadas  # o motor só prepara: quem abre a conversa é o app
    conversa = r["conversas_ia"][0]
    lote = Path(conversa["pasta"])
    assert lote.parent == p.path / "edicoes-ia" and conversa["cwd"] == str(p.path)
    frase = f"Leia o arquivo edicoes-ia/{lote.name}/pedido-lote.md e siga o que ele pede. Comece me mostrando o plano."
    assert conversa["frase"] == frase and conversa["clips"] == ["01-x", "02-y"]
    # o app abre (terminal externo) com o mesmo lote já preparado
    r2 = edicao_ia.abrir_lote(p, ["01-x", "02-y"], "claude")
    cmd, kw = chamadas[0]
    assert r2["lote"] == lote.name and kw["cwd"] == str(p.path) and cmd == ["C:/bin/claude.exe", frase]
    texto_lote = (lote / "pedido-lote.md").read_text(encoding="utf-8")
    assert f"clips/01-x/edicoes/{lote.name}/pedido.md" in texto_lote and "clips/02-y/edicoes" in texto_lote
    assert maldoso in (p.clips_dir / "02-y" / "edicoes" / lote.name / "pedido.md").read_text(encoding="utf-8")
    assert all(maldoso not in x for x in cmd)
    assert p.clip("01-x")[0].pedido_ia.enviado == lote.name

    # já preparado: o próximo render não prepara outro lote
    chamadas.clear()
    assert srv._conversa_do_lote(p, ["01-x", "02-y"], ctx) == {} and not chamadas
    # "Reabrir conversa": continua a última conversa da pasta do projeto, com o mesmo lote
    r = edicao_ia.abrir_lote(p, ["01-x", "02-y"], "claude", "continuar", agora=datetime(2030, 1, 1))
    assert r["lote"] == lote.name and chamadas[0][0][1] == "--continue"

    # sem a CLI: o erro fica no clip para o app mostrar, e o render não falha
    c, _ = p.clip("02-y")
    c.pedido_ia = PedidoIA(agente="codex", texto="x")
    p.salvar_clip(c)
    monkeypatch.setattr(edicao_ia, "_binario", lambda a: None)
    r = srv._conversa_do_lote(p, ["02-y"], ctx)
    assert "não está instalado" in r["erros_ia"][0] and "não está instalado" in p.clip("02-y")[0].pedido_ia.erro
    assert p.clip("02-y")[0].pedido_ia.enviado is None


def test_selecionar_guarda_o_pedido_para_a_ia(ws):
    from clipator.models import PedidoIA

    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(p.candidatos_path, [{"id": "c1", "inicio": 1.0, "fim": 20.0, "titulos": ["Um"], "nota": 50}])
    ped = PedidoIA(agente="codex", texto="legenda amarela", abrir_ao_terminar=False)
    clip = pipeline.selecionar(p, ["c1"], pedido_ia=ped)[0]
    assert p.clip(clip.id)[0].pedido_ia == ped
    ped2 = PedidoIA(texto="outro")
    pipeline.selecionar(p, ["c1"], pedido_ia=ped2)  # clip que já existe: atualiza o pedido
    assert p.clip(clip.id)[0].pedido_ia.texto == "outro"


def test_editar_ia_no_app_so_prepara(ws, monkeypatch):
    import subprocess

    from clipator import edicao_ia

    p = _clip_para_editar(ws)
    chamadas = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: chamadas.append((cmd, kw)))
    monkeypatch.setattr(edicao_ia, "_binario", lambda a: f"C:/bin/{a}.exe")
    r = edicao_ia.abrir(p, "01-x", "codex", "abrir", "corte mais curto", lancar=False)
    assert not chamadas and r["cwd"] == str(p.clips_dir / "01-x")
    assert r["frase"].startswith("Leia o arquivo edicoes/") and "corte mais curto" not in r["frase"]
    assert "corte mais curto" in Path(r["pasta"], "pedido.md").read_text(encoding="utf-8")


def test_terminal_de_cada_sistema(tmp_path, monkeypatch):
    import shutil as _shutil

    from clipator import edicao_ia

    args = ["/opt/bin/claude", "Leia o arquivo edicoes/x/pedido.md"]
    pasta = tmp_path / "pasta com espaço'e aspas"
    # Windows Terminal quando existe: nova aba na pasta, ";" escapado (o wt usa ";" para separar comandos)
    monkeypatch.setattr(_shutil, "which", lambda n: "C:/WindowsApps/wt.exe" if n == "wt" else None)
    cmd, kw = edicao_ia.lancador([*args, "a; b"], pasta, "win32")
    assert cmd == ["C:/WindowsApps/wt.exe", "-w", "new", "new-tab", "--title", "Clipator", "-d", str(pasta), *args, "a\\; b"]
    assert "stdin" not in kw and "stdout" not in kw  # nada redirecionado: senão a CLI desenha no pipe do motor
    monkeypatch.setenv("CLIPATOR_TERMINAL", "conhost")
    cmd, kw = edicao_ia.lancador(args, pasta, "win32")
    assert cmd == args and kw["cwd"] == str(pasta) and kw["creationflags"]  # console novo, sem cmd /c
    assert "stdin" not in kw and "stdout" not in kw
    cmd, kw = edicao_ia.lancador(args, pasta, "darwin")
    assert cmd[0] == "osascript" and "/opt/bin/claude 'Leia o arquivo edicoes/x/pedido.md'" in cmd[2]
    assert "do script" in cmd[2]
    monkeypatch.setattr(_shutil, "which", lambda n: "/usr/bin/x" if n == "gnome-terminal" else None)
    cmd, kw = edicao_ia.lancador(args, pasta, "linux")
    assert cmd == ["gnome-terminal", "--", *args] and kw["cwd"] == str(pasta)


def test_versoes_editadas_usar_e_apagar(ws):
    from clipator import edicao_ia

    p = _clip_para_editar(ws)
    pasta = p.clips_dir / "01-x"
    (pasta / "saida.mp4").write_bytes(b"original")
    v = pasta / "edicoes" / "20261102-170000"
    v.mkdir(parents=True)
    (v / "saida-editada.mp4").write_bytes(b"editado")
    (v / "notas.md").write_text("Tirei as pausas.", encoding="utf-8")
    vs = edicao_ia.listar_versoes(p, "01-x")
    assert vs[0]["id"] == "20261102-170000" and vs[0]["videos"] == ["edicoes/20261102-170000/saida-editada.mp4"]
    assert vs[0]["notas"] == "Tirei as pausas." and vs[0]["escolhido"] is None
    edicao_ia.usar_versao(p, "01-x", "edicoes/20261102-170000/saida-editada.mp4")
    assert p.clip("01-x")[0].versao == "edicoes/20261102-170000/saida-editada.mp4"
    assert (pasta / "saida.mp4").read_bytes() == b"original"  # o original fica
    assert edicao_ia.listar_versoes(p, "01-x")[0]["escolhido"]
    with pytest.raises(FileNotFoundError):
        edicao_ia.usar_versao(p, "01-x", "../01-x/clip.yaml")
    with pytest.raises(FileNotFoundError):
        edicao_ia.usar_versao(p, "01-x", "saida.mp4")  # só vídeos de edicoes/
    edicao_ia.apagar_versao(p, "01-x", "20261102-170000")
    assert not v.exists() and p.clip("01-x")[0].versao is None
    with pytest.raises(FileNotFoundError):
        edicao_ia.apagar_versao(p, "01-x", "..")


def test_mcp_registrado_no_codex(tmp_path, monkeypatch):
    from clipator import edicao_ia

    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    assert edicao_ia.mcp_registrado("codex") is False
    (tmp_path / "codex").mkdir()
    (tmp_path / "codex" / "config.toml").write_text('[mcp_servers.clipator]\ncommand = "clipator"\n', encoding="utf-8")
    assert edicao_ia.mcp_registrado("codex") is True

# ---- processos externos ------------------------------------------------------------
_NETO = """
import subprocess, sys, time
neto = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
open(sys.argv[1], "w").write(str(neto.pid))
time.sleep(60)
"""


def _vivo(pid: int) -> bool:
    if sys.platform == "win32":
        r = subprocess_run(["tasklist", "/FI", f"PID eq {pid}", "/NH"])
        return str(pid) in r
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def subprocess_run(cmd):
    import subprocess

    return subprocess.run(cmd, capture_output=True, text=True).stdout


def test_cancelar_mata_a_arvore_de_processos_sem_esperar_saida(tmp_path):
    """Um programa calado (como o HyperFrames travado) e o filho dele morrem logo ao cancelar."""
    arq = tmp_path / "neto.pid"
    cancelar = threading.Event()
    threading.Timer(1.0, cancelar.set).start()
    t0 = time.monotonic()
    with pytest.raises(Cancelado):
        media.rodar_processo([sys.executable, "-c", _NETO, str(arq)], cancelar=cancelar, descricao="teste")
    assert time.monotonic() - t0 < 8
    neto = int(arq.read_text())
    for _ in range(20):
        if not _vivo(neto):
            break
        time.sleep(0.25)
    assert not _vivo(neto)


def test_programa_calado_e_tratado_como_travado(tmp_path):
    t0 = time.monotonic()
    with pytest.raises(media.Travado, match="sem responder"):
        media.rodar_processo([sys.executable, "-c", "import time; time.sleep(30)"], sem_saida_s=1.0, descricao="O teste")
    assert time.monotonic() - t0 < 8


def test_processo_tem_stdin_fechado(tmp_path):
    linhas = []
    codigo = media.rodar_processo([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], linhas.append)
    assert codigo == 0 and [x.strip() for x in linhas] == ["''"]  # leu EOF na hora, não ficou esperando


def test_hyperframes_travado_cai_para_a_legenda_ass(tmp_path, monkeypatch):
    from clipator import hyperframes

    monkeypatch.setattr(hyperframes, "comando", lambda: [sys.executable, "-c", "import time; time.sleep(30)"])
    monkeypatch.setattr(hyperframes, "SEM_SAIDA_S", 1.0)
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    with pytest.raises(hyperframes.ErroHyperFrames, match="sem responder"):
        hyperframes.renderizar(tmp_path, tmp_path / "camada.webm")
    assert not list(tmp_path.glob("*.webm"))  # nada pela metade


def test_substituir_avisa_quando_o_video_esta_aberto(tmp_path, monkeypatch):
    destino = tmp_path / "saida.mp4"
    destino.write_bytes(b"velho")
    tmp = tmp_path / "saida.tmp.mp4"
    tmp.write_bytes(b"novo")
    media.substituir(tmp, destino)
    assert destino.read_bytes() == b"novo"

    tmp.write_bytes(b"de novo")

    def preso(self, alvo):
        raise PermissionError("em uso")

    monkeypatch.setattr(type(tmp), "replace", preso)
    with pytest.raises(media.FFmpegError, match="aberto em outro programa"):
        media.substituir(tmp, destino, tentativas=2, espera=0.01)
    assert not tmp.exists() and destino.read_bytes() == b"novo"


@precisa_ffmpeg
def test_renderizar_de_novo_o_mesmo_clip(ws, video_teste, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    c, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="podcast-limpo")[0]
    r1 = pipeline.renderizar(p, clip.id, preview=True)
    r2 = pipeline.renderizar(p, clip.id, preview=True)  # já existe: sobrescreve sem perguntar nem travar
    assert r1.video == r2.video and r2.video.exists()
    assert not list(r2.video.parent.glob("*.tmp.mp4"))


def test_apagar_clip_pela_api(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    app = criar_app(srv, token="t")
    cl = TestClient(app)
    h = {"x-clipator-token": "t"}
    p = srv.ws.criar_canal("Teste").criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=9, titulo="T"))
    pasta = p.clips_dir / "01-x"
    (pasta / "saida.mp4").write_bytes(b"v")
    (pasta / "thumbs").mkdir()
    (pasta / "thumbs" / "insight-1-moldura.png").write_bytes(b"p")
    base = f"/api/canais/teste/projetos/{p.id}/clips/01-x"
    assert cl.delete(base, headers=h).status_code == 409  # sem confirmar

    bloqueio = threading.Event()
    srv.fila.registrar("renderizar", lambda params, ctx: bloqueio.wait(5))
    jid = srv.fila.enviar("renderizar", {"canal": "teste", "projeto": p.id, "clips": ["01-x"]})
    r = cl.delete(base, params={"confirmar": "true"}, headers=h)
    assert r.status_code == 409 and "renderizando" in r.json()["detail"]
    bloqueio.set()
    srv.fila.esperar(jid, 5)

    assert cl.delete(base, params={"confirmar": "true"}, headers=h).json() == {"ok": True}
    assert not pasta.exists() and p.clips() == []
    assert cl.delete(base, params={"confirmar": "true"}, headers=h).status_code == 409  # já não existe
    srv.fila.fechar()



def test_corrigir_nomes_numa_transcricao_que_ja_existe(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    p = srv.ws.criar_canal("Teste").criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    trans = transcricao_falsa("Eu falei com o Vorcano sobre dinheiro. Ele riu muito da história toda.")
    write_json(p.transcricao_path, trans)
    write_json(p.candidatos_path, [{"id": "c01", "inicio": 0, "fim": 30, "texto": "velho"}])
    assert cl.put("/api/canais/teste/glossario", json={"glossario": [" Vorcaro ", ""]}, headers=h).json() == {"glossario": ["Vorcaro"]}
    assert cl.get("/api/canais/teste/glossario", headers=h).json() == {"glossario": ["Vorcaro"]}
    r = cl.post(f"/api/canais/teste/projetos/{p.id}/transcricao/corrigir-nomes", headers=h).json()
    assert [t["para"] for t in r["trocas"]] == ["Vorcaro"]
    assert "Vorcaro" in p.transcricao()["segmentos"][0]["texto"]
    assert "Vorcaro" in p.candidatos()[0]["texto"]
    assert (p.canal.path / "canal.md").read_text(encoding="utf-8").count("Vorcaro") == 1
    srv.fila.fechar()

def test_candidato_guarda_a_explicacao_da_nota():
    trans = transcricao_falsa(repetir=2)
    from clipator import candidates
    from clipator.models import Regras

    c = candidates.gerar(trans, None, {}, Regras(duracao_min=10, duracao_max=25))[0]
    assert set(c["pesos"]) >= {"gancho", "fechamento", "historia"} and 0 < c["fator_duracao"] <= 1
    assert c["fechamento"] and all(x[0] in "+−" for x in c["fechamento"])
    assert "fechamento" in c["sinais"]


# ---- fila de jobs -----------------------------------------------------------------
def test_fila_jobs(tmp_path):
    fila = FilaJobs(tmp_path / "j.sqlite3")
    eventos = []
    fila.ouvintes.append(eventos.append)

    def ok(params, ctx):
        ctx.progresso(0.5, "meio")
        ctx.log("linha")
        return {"dobro": params["x"] * 2}

    def lento(params, ctx):
        for _ in range(200):
            time.sleep(0.01)
            ctx.progresso(0.1, "esperando")
        return None

    def falha(params, ctx):
        raise ValueError("deu ruim")

    fila.registrar("ok", ok)
    fila.registrar("lento", lento)
    fila.registrar("falha", falha)
    j1 = fila.enviar("ok", {"x": 2})
    assert fila.esperar(j1, 5)["resultado"] == {"dobro": 4}
    assert "linha" in fila.obter(j1)["log"]
    j2 = fila.enviar("falha")
    assert fila.esperar(j2, 5)["erro"] == "deu ruim"
    j3 = fila.enviar("lento")
    time.sleep(0.1)
    fila.cancelar(j3)
    assert fila.esperar(j3, 5)["status"] == "cancelado"
    assert any(e["status"] == "rodando" for e in eventos)
    fila.fechar()



def test_fila_guarda_etapa_atual_e_inicio_dela(tmp_path):
    fila = FilaJobs(tmp_path / "j.sqlite3")
    passou = threading.Event()
    seguir = threading.Event()

    def job(params, ctx):
        ctx.progresso(0.1, "baixando", "ingestao", 0.4)
        ctx.progresso(0.3, "transcrevendo 0:10 de 1:00", "transcricao", 0.1)
        passou.set()
        seguir.wait(5)
        ctx.progresso(0.5, "transcrevendo 0:40 de 1:00", "transcricao", 0.6)
        seguir.clear()

    fila.registrar("analisar", job)
    jid = fila.enviar("analisar")
    assert passou.wait(5)
    j = fila.obter(jid)
    assert j["etapa"] == "transcricao" and j["progresso_etapa"] == pytest.approx(0.1)
    assert j["etapa_progresso_inicial"] == pytest.approx(0.3) and j["etapa_iniciado"] is not None
    inicio = j["etapa_iniciado"]
    seguir.set()
    j = fila.esperar(jid, 5)
    assert j["etapa_iniciado"] == inicio and j["etapa_progresso_inicial"] == pytest.approx(0.3)  # mesma etapa
    fila.fechar()

def test_fila_limpa_erros_e_logs_ao_subir(tmp_path):
    fila = FilaJobs(tmp_path / "j.sqlite3")
    fila.registrar("ok", lambda p, ctx: ctx.log("linha velha"))
    fila.registrar("falha", lambda p, ctx: (_ for _ in ()).throw(ValueError("deu ruim")))
    j_ok = fila.enviar("ok")
    fila.esperar(j_ok, 5)
    j_erro = fila.enviar("falha")
    fila.esperar(j_erro, 5)
    fila.fechar()

    mantida = FilaJobs(tmp_path / "j.sqlite3")  # o MCP não limpa
    assert mantida.obter(j_erro)["status"] == "erro"
    mantida.fechar()

    limpa = FilaJobs(tmp_path / "j.sqlite3", limpar=True)
    assert limpa.obter(j_erro) is None
    assert limpa.obter(j_ok)["status"] == "ok" and limpa.obter(j_ok)["log"] == ""
    limpa.fechar()


def test_servico_do_app_limpa_erros_das_etapas(tmp_path):
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    p = srv.ws.criar_canal("Teste").criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    p.marcar("ingestao", "ok")
    p.marcar("transcricao", "erro", "Library cublas64_12.dll is not found")
    srv.fila.fechar()

    srv = Servico(tmp_path / "ws", limpar_erros=True)
    etapas = p.meta().etapas
    assert etapas["transcricao"].status == "pendente" and etapas["transcricao"].erro is None
    assert etapas["ingestao"].status == "ok"
    srv.fila.fechar()


# ---- mídia e render -----------------------------------------------------------------
@precisa_ffmpeg
def test_probe_e_audio(video_teste, tmp_path):
    info = media.probe(video_teste)
    assert (info.largura, info.altura) == (640, 360) and info.tem_audio
    wav = media.extrair_audio(video_teste, tmp_path / "a.wav")
    s = signals.analisar(wav, video_teste)
    assert len(s["energia_db"]) == pytest.approx(14 / 0.25, abs=2)
    assert s["picos"] and 5.5 <= s["picos"][0][0] <= 7  # o trecho alto entre 6 e 7 s


@precisa_ffmpeg
def test_cancelar_ffmpeg(video_teste, tmp_path):
    ev = threading.Event()
    ev.set()
    with pytest.raises(Cancelado):
        media.run_ffmpeg(["-i", str(video_teste), "-f", "null", "-"], duracao=14, progresso=lambda f, m: None, cancelar=ev)


def _projeto_com_video(ws, video_teste):
    c = ws.criar_canal("Teste", palavras_chave=["dinheiro"])
    md_regras = c.arquivo("regras.md")
    md_regras.write_text(md_regras.read_text().replace("duracao_min: 40", "duracao_min: 5").replace("duracao_max: 180", "duracao_max: 12"))
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor=str(video_teste)))
    return c, p


@precisa_ffmpeg
def test_pipeline_ponta_a_ponta(ws, video_teste, whisper_falso, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    c, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    assert cands and all(5 <= x["duracao"] <= 14 for x in cands)
    etapas = {k: v.status for k, v in p.meta().etapas.items()}
    assert etapas["transcricao"] == "ok" and etapas["candidatos"] == "ok"
    clips = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="podcast-limpo", cartela=True)
    r = pipeline.renderizar(p, clips[0].id, preview=True)
    info = media.probe(r.video)
    assert (info.largura, info.altura) == (540, 960)
    assert info.duracao == pytest.approx(clips[0].fim - clips[0].inicio, abs=0.2)
    r = pipeline.renderizar(p, clips[0].id)
    assert (p.clips_dir / clips[0].id / "postagem.txt").exists()
    assert media.probe(r.video).altura == 1920



def test_refazer_analise_mantem_video_audio_transcricao_e_clips(ws, tmp_path):
    c = ws.criar_canal("Teste")
    p = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    p.fonte_dir.mkdir(parents=True, exist_ok=True)
    (p.fonte_dir / "video.mp4").write_bytes(b"v")
    p.analise_dir.mkdir(parents=True, exist_ok=True)
    p.audio_path.write_bytes(b"a")
    write_json(p.transcricao_path, transcricao_falsa())
    write_json(p.sinais_path, {"passo": 0.25})
    write_json(p.candidatos_path, [{"id": "c01"}])
    (p.analise_dir / "quadros").mkdir()
    (p.analise_dir / "quadros" / "c01_0.jpg").write_bytes(b"j")
    (p.analise_dir / "cache_ia").mkdir()
    (p.analise_dir / "cache_ia" / "x.json").write_text("{}", encoding="utf-8")
    p.salvar_clip(Clip(id="01-x", inicio=1, fim=9, titulo="T"))
    p.marcar("ingestao", "ok")
    p.marcar("transcricao", "ok")
    p.marcar("ranking", "erro", "login")

    p.limpar_analise()
    assert sorted(x.name for x in p.analise_dir.iterdir()) == ["audio.wav", "transcricao.json"]
    assert (p.fonte_dir / "video.mp4").exists() and [cl.id for cl, _ in p.clips()] == ["01-x"]
    etapas = p.meta().etapas
    assert etapas["ingestao"].status == "ok" and etapas["transcricao"].status == "ok"
    assert all(etapas[e].status == "pendente" and not etapas[e].erro for e in ("sinais", "candidatos", "ranking"))


@precisa_ffmpeg
def test_analise_informa_etapa_e_fracao(ws, video_teste, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    _, p = _projeto_com_video(ws, video_teste)
    p.audio_path.unlink(missing_ok=True)  # força a extração do áudio
    vistos = []
    pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia", etapa=lambda g, m, nome, f: vistos.append((g, nome, f)))
    nomes = list(dict.fromkeys(n for _, n, _ in vistos))
    assert nomes == ["ingestao", "audio", "transcricao", "sinais", "candidatos", "ranking"]
    assert all(0 <= f <= 1 and 0 <= g <= 1 for g, _, f in vistos)
    gerais = [g for g, _, _ in vistos]
    assert gerais == sorted(gerais)  # o progresso geral nunca volta

@precisa_ffmpeg
def test_quadros_do_candidato(ws, video_teste, monkeypatch):
    from clipator import transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    _, p = _projeto_com_video(ws, video_teste)
    c = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")[0]
    qs = pipeline.quadros_candidato(p, c["id"])
    assert [q["rotulo"] for q in qs] == ["começo", "meio", "fim"]
    assert qs[0]["tempo"] == pytest.approx(c["inicio"] + 0.5, abs=0.01)
    assert qs[2]["tempo"] == pytest.approx(c["fim"] - 0.5, abs=0.01)
    assert all(q["imagem"].exists() and q["imagem"].name == f"{c['id']}_{i}.jpg" for i, q in enumerate(qs))
    assert all(q["frase"] for q in qs) and qs[0]["frase"] != qs[2]["frase"]
    assert 0 <= pipeline.centro_rosto(p, c["id"], qs) <= 1  # vídeo de teste sem rosto: centro
    antes = qs[0]["imagem"].stat().st_mtime_ns
    pipeline.quadros_candidato(p, c["id"])  # usa o cache
    assert qs[0]["imagem"].stat().st_mtime_ns == antes
    with pytest.raises(KeyError):
        pipeline.quadros_candidato(p, "nao-existe")


@precisa_ffmpeg
@pytest.mark.parametrize("formato,estilo,esperado", [
    ("1:1", "minimalista", (1080, 1080)), ("4:5", "dossie-investigativo", (1080, 1350)), ("16:9", "corte-longo", (1920, 1080)),
])
def test_formatos(ws, video_teste, formato, estilo, esperado):
    c, p = _projeto_com_video(ws, video_teste)
    from clipator import ingest

    ingest.importar_arquivo(video_teste, p)
    write_json(p.transcricao_path, transcricao_falsa(duracao=13))
    clip = Clip(id="01-x", inicio=1, fim=6, titulo="Teste", formato=formato, estilo=estilo, cortes_internos=[(3, 3.5)])
    p.salvar_clip(clip)
    r = pipeline.renderizar(p, "01-x")
    info = media.probe(r.video)
    assert (info.largura, info.altura) == esperado
    assert info.duracao == pytest.approx(4.5, abs=0.2)


# ---- API --------------------------------------------------------------------------
def test_api(tmp_path, video_teste):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    app = criar_app(Servico(tmp_path / "ws"), token="segredo")
    cli = TestClient(app)
    assert cli.get("/api/canais").status_code == 401
    h = {"x-clipator-token": "segredo"}
    assert cli.post("/api/canais", json={"nome": "Meu Canal"}, headers=h).json() == {"slug": "meu-canal"}
    assert cli.get("/api/canais", headers=h).json()[0]["slug"] == "meu-canal"
    arv = cli.get("/api/arvore", headers=h).json()
    assert any(f["nome"] == "canais" for f in arv["filhos"])
    r = cli.get("/api/arquivo", params={"caminho": "canais/meu-canal/regras-e-textos/regras.md"}, headers=h).json()
    assert "duracao_max" in r["conteudo"] and r["erros"] == []
    r = cli.put("/api/arquivo", json={"caminho": "canais/meu-canal/regras-e-textos/regras.md", "conteudo": "---\nduracao_min: 2\n---\n"}, headers=h).json()
    assert r["erros"]
    assert cli.get("/api/arquivo", params={"caminho": "../../etc/passwd"}, headers=h).status_code >= 400
    estilos = cli.get("/api/estilos", headers=h).json()
    assert {"impacto", "podcast-limpo", "corte-longo"} <= {e["id"] for e in estilos}
    assert "motor:" in cli.get("/api/estilos/embutido", params={"id": "impacto"}, headers=h).json()["conteudo"]
    assert cli.get("/api/estilos/embutido", params={"id": "../../pyproject"}, headers=h).status_code == 404
    r = cli.post("/api/canais/meu-canal/projetos", json={"origem": str(video_teste), "analisar": False}, headers=h).json()
    assert r["job"] is None
    det = cli.get(f"/api/canais/meu-canal/projetos/{r['id']}", headers=h).json()
    assert det["meta"]["origem"]["tipo"] == "arquivo"
    assert cli.post("/api/canais/meu-canal/projetos", json={"origem": "https://vimeo.com/1"}, headers=h).status_code == 400


# ---- MCP --------------------------------------------------------------------------
def test_mcp_ferramentas(tmp_path):
    from clipator.mcp_server import criar_servidor
    from clipator.service import Servico

    srv = criar_servidor(Servico(tmp_path / "ws", nome_fila="jobs-mcp"))
    nomes = {t.name for t in asyncio.run(srv.list_tools())}
    exigidas = {"listar_canais", "criar_canal", "criar_projeto", "importar_video", "status_job", "ler_transcricao",
                "corrigir_transcricao", "listar_candidatos", "selecionar_cortes", "ajustar_corte", "sugerir_titulos",
                "listar_estilos", "criar_estilo", "renderizar", "gerar_thumbnail", "abrir_preview"}
    assert exigidas <= nomes
    asyncio.run(srv.call_tool("criar_canal", {"nome": "Podcast"}))
    res = asyncio.run(srv.call_tool("criar_estilo", {"nome": "Meu Amarelo", "descricao": "x", "base": "impacto",
                                                     "ajustes": {"legenda": {"cor": "#FFE600"}}, "canal": "podcast"}))
    assert not res.is_error
    assert (tmp_path / "ws" / "canais" / "podcast" / "estilos" / "meu-amarelo.md").exists()
    res = asyncio.run(srv.call_tool("apagar_clip", {"canal": "podcast", "projeto": "x", "clip": "y"}))
    assert "confirmar" in res.content[0].text


def test_cli_init_e_canal(tmp_path, capsys):
    from clipator.cli import main

    w = str(tmp_path / "ws")
    assert main(["-w", w, "init"]) == 0
    assert main(["-w", w, "canal", "criar", "Cortes Teste"]) == 0
    assert main(["-w", w, "canal", "listar"]) == 0
    assert "cortes-teste" in capsys.readouterr().out
    assert main(["-w", w, "estilos"]) == 0
    os.environ.pop("CLIPATOR_WORKSPACE", None)


def test_ffmpeg_tem_libass():
    # sem libass não sai legenda nenhuma; o doctor e o render avisam disso
    from clipator import media

    assert "subtitles" in media.filtros_ffmpeg()


def test_uvicorn_tem_websocket(tmp_path):
    # sem a lib de WebSocket o uvicorn devolve 404 em /api/eventos e o app fica sem progresso ao vivo
    import uvicorn

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    cfg = uvicorn.Config(criar_app(srv, "t"), ws="auto")
    cfg.load()
    assert cfg.ws_protocol_class is not None
    srv.fila.fechar()


# ---- YouTube pedindo login: cookies do navegador ou cookies.txt (yt-dlp falso, sem internet) ----
class _YDLFalso:
    """Imita o yt_dlp.YoutubeDL: guarda as opções de cada tentativa e falha como o YouTube manda."""

    chamadas: list = []
    ERRO_ROBO = "ERROR: [youtube] abc: Sign in to confirm you\u2019re not a bot. Use --cookies-from-browser or --cookies"
    erro_sem_cookies = ERRO_ROBO
    erro_com_cookies: str | None = None

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        _YDLFalso.chamadas.append({k: v for k, v in self.opts.items() if k in ("cookiesfrombrowser", "cookiefile")})
        tem = "cookiesfrombrowser" in self.opts or "cookiefile" in self.opts
        if not tem and self.erro_sem_cookies:
            raise RuntimeError(self.erro_sem_cookies)
        if tem and self.erro_com_cookies:
            raise RuntimeError(self.erro_com_cookies)
        return {"id": "abc", "title": "t", "duration": 10}

    def process_ie_result(self, info, download=True):
        destino = Path(self.opts["outtmpl"]).parent
        (destino / "video.mp4").write_bytes(b"x")


@pytest.fixture
def ydl_falso(monkeypatch):
    import yt_dlp

    from clipator import ingest

    _YDLFalso.chamadas = []
    _YDLFalso.erro_com_cookies = None
    _YDLFalso.erro_sem_cookies = _YDLFalso.ERRO_ROBO
    monkeypatch.setattr(yt_dlp, "YoutubeDL", _YDLFalso)
    monkeypatch.setattr(ingest, "navegadores_instalados", lambda: [])  # o Firefox desta máquina não entra no teste
    monkeypatch.setattr(ingest.media, "ffmpeg_disponivel", lambda: True)
    return _YDLFalso


def _projeto_link(ws):
    c = ws.criar_canal("Teste")
    return c.criar_projeto("v", Origem(tipo="link", valor="https://www.youtube.com/watch?v=abc"))


def test_youtube_pede_login_tenta_com_os_cookies_configurados(ws, ydl_falso):
    from clipator import ingest

    p = _projeto_link(ws)
    url = "https://www.youtube.com/watch?v=abc"
    # sem conta e sem cookies: o erro pede para entrar pelo Clipator
    with pytest.raises(ingest.PrecisaCookies) as e:
        ingest.baixar(url, p)
    assert str(e.value).startswith(ingest.AVISO_ROBO) and "Conecte a conta do YouTube no Clipator" in str(e.value)
    assert ydl_falso.chamadas == [{}]
    # com o Firefox configurado: sem cookies e então os cookies, que baixam
    ydl_falso.chamadas = []
    assert ingest.baixar(url, p, cookies=ingest.opcoes_cookies("firefox")).name == "video.mp4"
    assert ydl_falso.chamadas == [{}, {"cookiesfrombrowser": ("firefox",)}]
    # escolhido agora no aviso: já vai com os cookies
    ydl_falso.chamadas = []
    ingest.baixar(url, p, cookies=ingest.opcoes_cookies("edge"), cookies_primeiro=True)
    assert ydl_falso.chamadas == [{"cookiesfrombrowser": ("edge",)}]


def test_erros_de_cookies_no_windows_explicados(ws, ydl_falso, tmp_path):
    from clipator import ingest

    p = _projeto_link(ws)
    url = "https://www.youtube.com/watch?v=abc"
    ydl_falso.erro_com_cookies = "ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271"
    with pytest.raises(ingest.ErroCookies, match="trava o arquivo"):
        ingest.baixar(url, p, cookies=ingest.opcoes_cookies("chrome"), cookies_primeiro=True)
    ydl_falso.erro_com_cookies = "ERROR: Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927"
    with pytest.raises(ingest.ErroCookies, match="Conecte a conta do YouTube"):
        ingest.baixar(url, p, cookies=ingest.opcoes_cookies("edge"), cookies_primeiro=True)
    # mesmo com cookies o YouTube recusou: diz de qual navegador e o que fazer
    ydl_falso.erro_com_cookies = ydl_falso.erro_sem_cookies
    with pytest.raises(ingest.PrecisaCookies, match="cookies do Firefox"):
        ingest.baixar(url, p, cookies=ingest.opcoes_cookies("firefox"))
    # cookies.txt: vai como --cookies; o conteúdo do arquivo não aparece em lugar nenhum
    arq = tmp_path / "cookies.txt"
    arq.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSEGREDO\tvalor-secreto\n", encoding="utf-8")
    ydl_falso.erro_com_cookies = None
    ydl_falso.chamadas = []
    ingest.baixar(url, p, cookies=ingest.opcoes_cookies(arquivo=str(arq)))
    assert ydl_falso.chamadas[-1] == {"cookiefile": str(arq)}
    with pytest.raises(ingest.ErroCookies):
        ingest.opcoes_cookies("navegador-inventado")
    with pytest.raises(ingest.ErroCookies, match="não encontrado"):
        ingest.opcoes_cookies(arquivo=str(tmp_path / "nao-existe.txt"))


def test_navegadores_instalados_pelas_pastas_de_perfil(tmp_path, monkeypatch):
    from clipator import ingest

    monkeypatch.setattr(ingest, "_pastas_perfil", lambda n: [tmp_path / n])
    (tmp_path / "firefox").mkdir()
    (tmp_path / "brave").mkdir()
    assert ingest.navegadores_instalados() == ["firefox", "brave"]


def test_analise_usa_os_cookies_das_configuracoes(tmp_path, ydl_falso, monkeypatch):
    from clipator import pipeline as pl
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws")
    cfg = srv.ws.config()
    cfg.youtube.cookies_navegador = "firefox"
    from clipator.workspace import write_yaml

    write_yaml(srv.ws.config_path, cfg.model_dump(mode="json"))
    p = _projeto_link(srv.ws)
    visto = {}
    monkeypatch.setattr(pl, "analisar", lambda *a, **kw: visto.update(kw) or [])

    class Ctx:
        progresso = staticmethod(lambda *a: None)
        log = staticmethod(lambda *a: None)
        cancelar = None

    srv._esperar_login = lambda ctx: None
    srv._job_analisar({"canal": p.canal.slug, "projeto": p.id}, Ctx())
    assert visto["cookies"] == {"cookiesfrombrowser": ("firefox",)} and visto["cookies_primeiro"] is False
    srv._job_analisar({"canal": p.canal.slug, "projeto": p.id, "cookies_navegador": "edge"}, Ctx())
    assert visto["cookies"] == {"cookiesfrombrowser": ("edge",)} and visto["cookies_primeiro"] is True


# ---- editor do passo 3: documento de edição, filtros, sugestões ----------------------------
def test_edicao_documento_clip_antigo_e_validacao(tmp_path):
    from clipator import edicao

    assert edicao.carregar(tmp_path).itens == []  # clip antigo: abre vazio, o clip.yaml não muda
    itens = [
        {"tipo": "zoom", "inicio": -3, "fim": 2, "params": {"escala": 9}},           # começa antes: prende em 0; escala limitada
        {"tipo": "inexistente", "inicio": 1, "fim": 2},                             # tipo desconhecido: fora
        {"tipo": "texto", "inicio": 5, "fim": 99, "params": {"texto": "x" * 500, "posicao": "lua", "cor": "#ff0000"}},
        {"tipo": "som", "inicio": 9.99, "fim": 10.5, "params": {"nome": "../../segredo"}},  # sobra menos de 0,05 s: fora
        {"tipo": "flash", "inicio": 3, "fim": 3.01},                                # curto demais: fora
        "lixo",
    ]
    v = edicao.validar(itens, 10.0)
    assert [i.tipo for i in v] == ["zoom", "texto"]
    assert v[0].inicio == 0 and v[0].params["escala"] == 1.8
    assert v[1].fim == 10.0 and len(v[1].params["texto"]) == 120 and v[1].params["posicao"] == "topo"
    assert v[1].params["cor"] == "#ff0000"
    assert edicao.normalizar_params("som", {"nome": "../x"})["nome"] == "whoosh"
    ed = edicao.salvar(tmp_path, edicao.Edicao(itens=v), 10.0)
    ed2 = edicao.salvar(tmp_path, edicao.carregar(tmp_path), 10.0)
    assert ed.revisao == 1 and ed2.revisao == 2 and len(edicao.carregar(tmp_path).itens) == 2


def test_edicao_filtros_de_cada_efeito(tmp_path):
    from clipator import edicao

    def grafo(tipo, **params):
        ed = edicao.Edicao(itens=edicao.validar([{"tipo": tipo, "inicio": 1, "fim": 2, "params": params}], 10))
        ent, partes, saida = edicao.filtros_video(ed, "vlay", 540, 960, 30, tmp_path, 3)
        return ent, ";".join(partes), saida

    _, g, s = grafo("zoom", escala=1.3)
    assert "zoompan=z='1+0.300*between((on/30)\\,1.000\\,2.000)'" in g and g.startswith("[vlay]") and g.endswith(f"[{s}]")
    _, g, _ = grafo("zoom-lento", escala=1.1)
    assert "clip(" in g
    _, g, _ = grafo("tremor", forca=10)
    assert "sin(on*2.1)" in g and "cos(on*1.7)" in g
    assert "hue=s=0:enable='between(t\\,1.000\\,2.000)'" in grafo("pb")[1]
    assert "colorchannelmixer" in grafo("sepia")[1]
    assert "eq=contrast=1.50" in grafo("contraste", valor=1.5)[1]
    assert "eq=saturation=" in grafo("saturacao")[1]
    assert "boxblur=8" in grafo("desfoque")[1]
    assert "vignette=" in grafo("vinheta")[1]
    assert grafo("flash")[1].count("drawbox=") == 3 and "color=white@" in grafo("flash")[1]
    assert "color=black@" in grafo("transicao")[1]
    # texto: vai por arquivo (textfile), nunca dentro do grafo
    malicioso = "x'; rm -rf / ;[0:v]"
    _, g, _ = grafo("texto", texto=malicioso)
    assert "textfile=" in g and malicioso not in g
    assert next((tmp_path / "edicao-textos").glob("*.txt")).read_text(encoding="utf-8") == malicioso
    # sem itens: nada muda
    assert edicao.filtros_video(edicao.Edicao(), "vlay", 540, 960, 30, tmp_path, 3) == ([], [], "vlay")


def test_edicao_sticker_emoji_vira_entrada_extra(tmp_path, monkeypatch):
    from clipator import edicao

    png = tmp_path / "e.png"
    png.write_bytes(b"x")
    monkeypatch.setattr(edicao, "_emoji_png", lambda *a: png)
    ed = edicao.Edicao(itens=edicao.validar([{"tipo": "emoji", "inicio": 1, "fim": 2, "params": {"emoji": "🔥"}}], 10))
    ent, partes, saida = edicao.filtros_video(ed, "vlay", 540, 960, 30, tmp_path, 4)
    assert ent == ["-loop", "1", "-i", str(png)] and "[vlay][4:v]overlay=" in partes[0]


def test_edicao_heuristica_e_resposta_da_ia():
    from clipator import edicao
    from clipator.timeline import Timeline

    tl = Timeline.de_clip(0, 20, [(8, 9)])
    pals = [{"inicio": 0.5, "fim": 0.9, "texto": "olha"}, {"inicio": 3.0, "fim": 3.4, "texto": "dinheiro"},
            {"inicio": 3.5, "fim": 3.9, "texto": "absurdo"}, {"inicio": 12.0, "fim": 12.3, "texto": "verdade"}]
    h = edicao.heuristica(pals, tl)
    tipos = [i.tipo for i in h]
    assert "zoom-lento" in tipos and "zoom" in tipos and "emoji" in tipos and "som" in tipos and "transicao" in tipos
    assert all(0 <= i.inicio < i.fim <= tl.duracao and i.origem == "heuristica" and i.motivo for i in h)
    som = next(i for i in h if i.tipo == "som")
    assert som.inicio == pytest.approx(8 - 0.15)  # na emenda do corte interno
    resp = {"efeitos": [
        {"tipo": "zoom", "inicio": 3.0, "fim": 4.0, "texto": "", "emoji": "", "escala": 1.4, "som": "", "motivo": "punchline"},
        {"tipo": "emoji", "inicio": 5, "fim": 6, "texto": "", "emoji": "", "escala": 0, "som": "", "motivo": "sem emoji"},
        {"tipo": "texto", "inicio": 30, "fim": 31, "texto": "FORA", "emoji": "", "escala": 0, "som": "", "motivo": "depois do fim"},
        {"tipo": "som", "inicio": 7, "fim": 6, "texto": "", "emoji": "", "escala": 0, "som": "pop", "motivo": "fim antes"},
        {"tipo": "hack", "inicio": 1, "fim": 2},
        {"tipo": "texto", "inicio": 10, "fim": 12, "texto": "R$ 1 MILHÃO", "emoji": "", "escala": 0, "som": "", "motivo": "número"},
    ]}
    v = edicao.de_resposta_ia(resp, tl.duracao)
    assert [(i.tipo, i.origem) for i in v] == [("zoom", "ia"), ("texto", "ia")] and v[0].params["escala"] == 1.4
    assert edicao.de_resposta_ia(None, 10) == [] and edicao.de_resposta_ia({"efeitos": "x"}, 10) == []


@precisa_ffmpeg
def test_render_com_edicao(ws, video_teste, monkeypatch, tmp_path):
    from clipator import edicao, transcribe

    from .conftest import WhisperFalso

    monkeypatch.setenv("CLIPATOR_SONS", str(tmp_path / "sons"))
    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    c, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16")[0]
    pasta = p.clips_dir / clip.id
    itens = [{"tipo": t, "inicio": 0.5 + k * 0.4, "fim": 1.5 + k * 0.4, "params": pr} for k, (t, pr) in enumerate([
        ("zoom", {}), ("zoom-lento", {}), ("tremor", {}), ("flash", {}), ("pb", {}), ("sepia", {}), ("contraste", {}),
        ("saturacao", {}), ("desfoque", {}), ("vinheta", {}), ("transicao", {}), ("texto", {"texto": "TESTE: 100%"}),
        ("som", {"nome": "pop"})])]
    edicao.salvar(pasta, edicao.Edicao(itens=edicao.validar(itens, clip.fim - clip.inicio)))
    r = pipeline.renderizar(p, clip.id, preview=True)
    info = media.probe(r.video)
    assert info.tem_audio and info.duracao == pytest.approx(clip.fim - clip.inicio, abs=0.25)


def test_edicao_pela_api_e_pelo_mcp(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.mcp_server import criar_servidor
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws", nome_fila="jobs-edicao")
    c = srv.ws.criar_canal("Teste")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    pr.salvar_clip(Clip(id="01-x", inicio=10, fim=30, titulo="T", cortes_internos=[(15.0, 16.0)]))
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    base = f"/api/canais/{c.slug}/projetos/{pr.id}/clips/01-x/edicao"
    d = cl.get(base, headers=h).json()
    assert d["itens"] == [] and d["revisao"] == 0 and d["duracao"] == pytest.approx(19.0) and "zoom" in d["tipos"]
    r = cl.put(base, json={"revisao": 0, "itens": [{"tipo": "zoom", "inicio": 2, "fim": 99}]}, headers=h)
    assert r.status_code == 200 and r.json()["revisao"] == 1 and r.json()["itens"][0]["fim"] == pytest.approx(19.0)
    # quem editou com uma revisão velha recebe conflito (a IA mudou no meio)
    assert cl.put(base, json={"revisao": 0, "itens": []}, headers=h).status_code == 409
    # a IA da conversa muda pelo MCP; o editor vê a revisão nova
    mcp = criar_servidor(srv)
    nomes = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"ler_edicao", "aplicar_edicao"} <= nomes
    res = asyncio.run(mcp.call_tool("aplicar_edicao", {"canal": c.slug, "projeto": pr.id, "clip": "01-x",
                                                       "adicionar": [{"tipo": "texto", "inicio": 1, "fim": 3, "params": {"texto": "OI"}}]}))
    assert not res.is_error
    d = cl.get(base, headers=h).json()
    assert d["revisao"] == 2 and [i["tipo"] for i in d["itens"]] == ["texto", "zoom"] and d["itens"][0]["origem"] == "ia"
    zoom = next(i for i in d["itens"] if i["tipo"] == "zoom")
    asyncio.run(mcp.call_tool("aplicar_edicao", {"canal": c.slug, "projeto": pr.id, "clip": "01-x", "remover": [zoom["id"]]}))
    assert [i["tipo"] for i in cl.get(base, headers=h).json()["itens"]] == ["texto"]
    # sugestões viram um job (com IA desligada no teste: as regras simples)
    j = cl.post(base + "/sugerir", params={"usar_ia": "false"}, headers=h).json()["job"]
    assert j


# ---- stickers: pacote curado, stickers do canal, render animado ---------------------------
def _png(caminho, animado=False, cor=(255, 0, 0, 255)):
    from PIL import Image

    caminho.parent.mkdir(parents=True, exist_ok=True)
    q = [Image.new("RGBA", (32, 32), cor), Image.new("RGBA", (32, 32), (0, 0, 255, 255))]
    if animado:
        q[0].save(caminho, save_all=True, append_images=q[1:], duration=100, loop=0)
    else:
        q[0].save(caminho)
    return caminho


def _manifesto(stks):
    import hashlib

    return {"versao": 1, "pacotes": {"fluent-animado": {"nome": "Fluent", "autor": "Microsoft", "licenca": "MIT",
                                                        "repositorio": "https://github.com/x/y", "commit": "abc123"}},
            "stickers": [{"id": f"fluent-animado/{n}", "nome": n, "arquivo": f"{n}.png", "animado": True, "categoria": "reacoes",
                          "palavras": pal, "url": f"https://exemplo/abc123/{n}.png", "sha256": hashlib.sha256(dados).hexdigest(),
                          "bytes": len(dados), "pacote": "fluent-animado"} for n, pal, dados in stks]}


def test_manifesto_do_pacote_real_e_validacao():
    from clipator import stickers

    m = stickers.manifesto()  # o que vai no repositório
    assert len(m["stickers"]) >= 150 and {p["licenca"] for p in m["pacotes"].values()} == {"MIT"}
    assert sum(s["animado"] for s in m["stickers"]) >= 60
    assert all(s["palavras"] and s["categoria"] for s in m["stickers"])
    ruim = _manifesto([("x", ["x"], b"1")])
    ruim["stickers"][0]["url"] = "https://exemplo/main/x.png"  # sem o commit fixo
    with pytest.raises(stickers.ErroSticker, match="commit"):
        stickers.validar_manifesto(ruim)
    ruim = _manifesto([("x", ["x"], b"1"), ("x", ["x"], b"2")])
    with pytest.raises(stickers.ErroSticker, match="repetido"):
        stickers.validar_manifesto(ruim)
    ruim = _manifesto([("x", ["x"], b"1")])
    ruim["pacotes"]["fluent-animado"]["licenca"] = "CC BY-SA 4.0"
    with pytest.raises(stickers.ErroSticker, match="licença"):
        stickers.validar_manifesto(ruim)


def test_instalar_confere_sha_e_pula_o_que_ja_tem(tmp_path):
    from clipator import stickers

    bom = b"\x89PNG\r\n\x1a\nconteudo"
    m = _manifesto([("fogo", ["fogo"], bom), ("risada", ["risada"], bom + b"2")])
    chamadas = []

    def baixar(url):
        chamadas.append(url)
        return bom if "fogo" in url else b"adulterado"

    r = stickers.instalar(m=m, baixar=baixar)
    assert r["baixados"] == 1 and len(r["erros"]) == 1 and "sha256" in r["erros"][0]
    assert (stickers.pasta_pacote() / "fogo.png").read_bytes() == bom and not (stickers.pasta_pacote() / "risada.png").exists()
    chamadas.clear()
    stickers.instalar(m=m, baixar=baixar)
    assert chamadas == ["https://exemplo/abc123/risada.png"]  # o que já confere não baixa de novo


def test_biblioteca_com_stickers_do_canal_e_referencias(tmp_path):
    from clipator import stickers

    m = _manifesto([("fogo", ["fogo"], b"x")])
    _png(stickers.pasta_pacote() / "fogo.png", animado=True)
    canal = tmp_path / "canal"
    _png(canal / "stickers" / "meu-logo.png")
    _png(canal / "stickers" / "dancinha.gif", animado=True)
    (canal / "stickers" / "notas.txt").write_text("x")
    lib = stickers.listar(canal, m)
    refs = {s["ref"]: s for s in lib["stickers"] if not s["ref"].startswith("cta:")}
    assert set(refs) == {"pacote:fluent-animado/fogo", "canal:meu-logo.png", "canal:dancinha.gif"}
    assert refs["canal:dancinha.gif"]["animado"] and not refs["canal:meu-logo.png"]["animado"]
    assert stickers.resolver("canal:meu-logo.png", canal) == canal / "stickers" / "meu-logo.png"
    assert stickers.resolver("pacote:fluent-animado/fogo", canal, m).name == "fogo.png"
    for ruim in ("canal:../../segredo.png", "canal:x.exe", "outro:x", "pacote:nao-existe", "web:../x.png"):
        assert stickers.resolver(ruim, canal, m) is None
    # GIF animado vira APNG para o FFmpeg
    arq, anim = stickers.para_render(canal / "stickers" / "dancinha.gif", tmp_path / "cache")
    assert anim and arq.suffix == ".png" and b"acTL" in arq.read_bytes()[:200]


def test_filtro_do_sticker_animado_com_entrada_e_rotacao(tmp_path, monkeypatch):
    from clipator import edicao, stickers

    canal = tmp_path / "canal"
    _png(canal / "stickers" / "a.png", animado=True)
    _png(canal / "stickers" / "b.png")
    itens = edicao.validar([
        {"tipo": "sticker", "inicio": 1, "fim": 3, "params": {"ref": "canal:a.png", "rotacao": 20, "entrada": "deslizar"}},
        {"tipo": "sticker", "inicio": 4, "fim": 5, "params": {"ref": "canal:b.png", "entrada": "pop"}},
        {"tipo": "sticker", "inicio": 5, "fim": 6, "params": {"ref": "canal:sumiu.png"}},  # não existe: fica de fora
        {"tipo": "sticker", "inicio": 6, "fim": 7, "params": {"ref": "../../x", "entrada": "explodir"}},
    ], 10)
    assert itens[3].params["ref"] == edicao.PADRAO["sticker"][1]["ref"] and itens[3].params["entrada"] == "pop"
    ent, partes, saida = edicao.filtros_video(edicao.Edicao(itens=itens[:3]), "vlay", 540, 960, 30, tmp_path, 5, canal)
    assert ent == ["-ignore_loop", "0", "-i", str(canal / "stickers" / "a.png"), "-loop", "1", "-i", str(canal / "stickers" / "b.png")]
    g = ";".join(partes)
    assert "[5:v]setpts=PTS-STARTPTS+1.000/TB,scale=150:-1,format=rgba,rotate=20.0*PI/180" in g
    assert "fade=in:st=1.000:d=0.25:alpha=1" in g and "[6:v]setpts=PTS-STARTPTS+4.000/TB" in g
    assert "eof_action=pass" in g and "eof_action=repeat" in g and "sin(PI*" in g
    assert ent.count("-i") == 2


def test_ia_e_regras_propoem_stickers_pelas_palavras(tmp_path, monkeypatch):
    from clipator import edicao, stickers
    from clipator.timeline import Timeline

    m = _manifesto([("fogo", ["fogo", "polêmica"], b"x"), ("risada", ["risada", "kkk"], b"y")])
    monkeypatch.setattr(stickers, "manifesto", lambda caminho=None: m)
    _png(stickers.pasta_pacote() / "fogo.png", animado=True)  # só o fogo está instalado
    _png(stickers.pasta_pacote() / "risada.png", animado=True)
    (stickers.pasta_pacote() / "risada.png").unlink()
    tl = Timeline.de_clip(0, 20)
    h = edicao.heuristica([{"inicio": 2.0, "fim": 2.4, "texto": "Polêmica!"}, {"inicio": 9, "fim": 9.3, "texto": "risada"}], tl)
    stk = [i for i in h if i.tipo == "sticker"]
    assert [(i.inicio, i.params["ref"]) for i in stk] == [(2.0, "pacote:fluent-animado/fogo")]
    indice = edicao._indice_stickers()
    assert indice == {"fogo": "pacote:fluent-animado/fogo", "polêmica": "pacote:fluent-animado/fogo"}
    resp = {"efeitos": [
        {"tipo": "sticker", "inicio": 1, "fim": 2, "texto": "", "emoji": "", "escala": 0, "som": "", "sticker": "polemica", "motivo": "x"},
        {"tipo": "sticker", "inicio": 3, "fim": 4, "texto": "", "emoji": "", "escala": 0, "som": "", "sticker": "unicórnio", "motivo": "y"},
    ]}
    v = edicao.de_resposta_ia(resp, 20, indice)
    assert [(i.tipo, i.params["ref"]) for i in v] == [("sticker", "pacote:fluent-animado/fogo")]
    assert "sticker" in edicao.SCHEMA_EFEITOS["properties"]["efeitos"]["items"]["required"]


def test_credito_de_sticker_cc_by_vai_para_a_descricao(ws):
    from clipator import edicao, postagem, stickers

    c = ws.criar_canal("Teste")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    write_json(pr.transcricao_path, transcricao_falsa())
    pr.salvar_clip(Clip(id="01-x", inicio=1, fim=20, titulo="T"))
    png = _png(ws.root / "t.png").read_bytes()
    reg = stickers.salvar_web(c.path, "twemoji:fire", png)
    stickers.salvar_web(c.path, "noto:fire", png)
    with pytest.raises(stickers.ErroSticker):
        stickers.salvar_web(c.path, "openmoji:fire", png)  # CC BY-SA: fora da lista
    edicao.salvar(pr.clips_dir / "01-x", edicao.Edicao(itens=edicao.validar(
        [{"tipo": "sticker", "inicio": 1, "fim": 2, "params": {"ref": reg["ref"]}},
         {"tipo": "sticker", "inicio": 3, "fim": 4, "params": {"ref": "web:noto-fire.png"}}], 19)))
    pac = postagem.gerar(pr, "01-x")
    desc = next(iter(pac.values()))["descricao"]
    assert "Twemoji" in desc and "CC BY 4.0" in desc and "Noto" not in desc  # Apache 2.0 não exige crédito na descrição


def test_cadeia_automatica_com_a_conta_do_clipator(ws, ydl_falso, tmp_path, monkeypatch, capsys, caplog):
    from clipator import ingest

    p = _projeto_link(ws)
    url = "https://www.youtube.com/watch?v=abc"
    conta = tmp_path / "yt-cookies.txt"  # o caminho do conftest (CLIPATOR_YT_COOKIES)
    segredo = "valor-muito-secreto-123"
    conta.write_text(f"# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSAPISID\t{segredo}\n", encoding="utf-8")
    # o Chrome configurado não dá para ler (app-bound), mas a conta do Clipator vem antes e baixa
    logs = []
    assert ingest.baixar(url, p, cookies=ingest.opcoes_cookies("chrome"), log=logs.append).name == "video.mp4"
    assert ydl_falso.chamadas == [{}, {"cookiefile": str(conta)}]  # parou no que baixou
    assert any("conta do Clipator" in m for m in logs)
    # nada do conteúdo do arquivo aparece em log, saída ou erro
    saida = capsys.readouterr()
    assert all(segredo not in x for x in [*logs, saida.out, saida.err, caplog.text])
    # sem pedir login: nem chega nos cookies
    ydl_falso.chamadas = []
    ydl_falso.erro_sem_cookies = None
    ingest.baixar(url, p)
    assert ydl_falso.chamadas == [{}]
    ydl_falso.erro_sem_cookies = ydl_falso.ERRO_ROBO
    # a conta expirou e o Chrome não abre: o erro final pede para entrar de novo pelo Clipator
    ydl_falso.chamadas = []
    ydl_falso.erro_com_cookies = ydl_falso.ERRO_ROBO
    with pytest.raises(ingest.PrecisaCookies, match="expirou"):
        ingest.baixar(url, p)
    # Firefox instalado entra no fim da cadeia, sem o usuário configurar nada
    monkeypatch.setattr(ingest, "navegadores_instalados", lambda: ["firefox", "chrome"])
    nomes = [n for n, _ in ingest.cadeia_de_tentativas(ingest.opcoes_cookies("chrome"))]
    assert nomes == ["sem cookies", "conta do Clipator", "Configurações", "Firefox"]
    conta.unlink()
    assert [n for n, _ in ingest.cadeia_de_tentativas({})] == ["sem cookies", "Firefox"]


# ---- conta do YouTube do Clipator (perfil próprio do Chrome/Edge + protocolo de depuração) ----
_COOKIES_SEM_LOGIN = [{"domain": ".youtube.com", "path": "/", "secure": True, "expires": 1893456000.4, "name": "YSC", "value": "a"},
                      {"domain": ".exemplo.com", "path": "/", "secure": False, "expires": -1, "name": "X", "value": "b"}]
_SEGREDO = "valor-do-cookie-que-nao-pode-vazar"
_COOKIES_COM_LOGIN = _COOKIES_SEM_LOGIN + [
    {"domain": ".youtube.com", "path": "/", "secure": True, "expires": 1893456000, "name": "LOGIN_INFO", "value": _SEGREDO},
    {"domain": "accounts.google.com", "path": "/", "secure": True, "expires": -1, "name": "SID", "value": "c"}]


class _ProcFalso:
    def __init__(self):
        self.vivo = True

    def poll(self):
        return None if self.vivo else 0

    def wait(self, timeout=None):
        self.vivo = False

    def terminate(self):
        self.vivo = False

    kill = terminate


def test_conta_youtube_netscape_e_gravacao(tmp_path):
    from yt_dlp.cookies import YoutubeDLCookieJar

    from clipator import contayt

    assert not contayt.gravar(_COOKIES_SEM_LOGIN)  # sem conta: não grava nada
    assert not contayt.arquivo_cookies().exists()
    assert contayt.gravar(_COOKIES_COM_LOGIN)
    txt = contayt.arquivo_cookies().read_text(encoding="utf-8")
    linhas = [l.split("\t") for l in txt.splitlines() if l and not l.startswith("#")]
    assert {l[5] for l in linhas} == {"YSC", "LOGIN_INFO", "SID"}  # só youtube.com e google.com
    assert ["accounts.google.com", "FALSE", "/", "TRUE", "0", "SID", "c"] in linhas
    assert [".youtube.com", "TRUE", "/", "TRUE", "1893456000", "YSC", "a"] in linhas
    jar = YoutubeDLCookieJar(str(contayt.arquivo_cookies()))
    jar.load(ignore_discard=True, ignore_expires=True)  # o yt-dlp lê o arquivo
    assert len(list(jar)) == 3


def test_conta_youtube_entrar_sem_depuracao_e_depois_le_sem_janela(tmp_path, monkeypatch, capsys):
    import threading

    from clipator import contayt

    monkeypatch.setattr(contayt, "navegador", lambda: ("Chrome", tmp_path / "chrome.exe"))
    fechados_antes = []
    monkeypatch.setattr(contayt, "fechar_perfil", lambda perfil: fechados_antes.append(perfil))
    contayt.pasta_perfil().mkdir(parents=True)
    (contayt.pasta_perfil() / "sobra-da-tentativa-anterior").write_text("x")
    monkeypatch.setattr(contayt.time, "sleep", lambda s: None)
    janelas, fechadas = [], []

    def abrir_login(exe, perfil):
        janelas.append((exe, perfil))
        proc = _ProcFalso()
        threading.Timer(0.05, lambda: setattr(proc, "vivo", False)).start()  # o usuário fecha a janela
        return proc

    msgs = []
    r = contayt.entrar(lambda f, m: msgs.append(m), abrir_login=abrir_login,
                       exportar_=lambda: contayt.gravar(_COOKIES_COM_LOGIN))
    assert r == {"conectada": True, "navegador": "Chrome"} and janelas == [(tmp_path / "chrome.exe", contayt.pasta_perfil())]
    assert fechados_antes == [contayt.pasta_perfil()]  # fechou o que estava aberto com o perfil
    assert not (contayt.pasta_perfil() / "sobra-da-tentativa-anterior").exists()  # sem conta: perfil novo
    assert contayt.estado()["conectada"]
    assert all(_SEGREDO not in m for m in msgs) and _SEGREDO not in capsys.readouterr().out
    # a janela de login abre sem porta de depuração nem flags fora do comum
    chamadas = []
    monkeypatch.setenv("ELECTRON_RUN_AS_NODE", "1")
    monkeypatch.setattr(contayt.subprocess, "Popen", lambda args, **k: chamadas.append((args, k)) or _ProcFalso())
    contayt._abrir_para_login(tmp_path / "chrome.exe", tmp_path / "perfil")
    args, kw = chamadas[0]
    assert args[1:] == [f"--user-data-dir={tmp_path / 'perfil'}", "--no-first-run", contayt.URL_LOGIN]
    assert not any("debug" in a or "automation" in a or "user-agent" in a for a in args)
    assert not any(k.startswith(("ELECTRON_", "CLIPATOR_")) for k in kw["env"])  # ambiente limpo
    # "Já entrei, continuar": fecha a janela como o usuário fecharia e lê a conta
    proc = _ProcFalso()
    fechou = []
    monkeypatch.setattr(contayt, "_fechar_janela", lambda pr: fechou.append(pr) or setattr(pr, "vivo", False))

    def abrir2(exe, perfil):
        contayt.continuar.set()
        return proc

    r = contayt.entrar(abrir_login=abrir2, exportar_=lambda: False)
    assert fechou == [proc] and not r["conectada"] and "login não terminou" in r["motivo"]
    # desconectar apaga o perfil e o arquivo
    contayt.pasta_perfil().mkdir(parents=True, exist_ok=True)
    contayt.desconectar()
    assert not contayt.arquivo_cookies().exists() and not contayt.pasta_perfil().exists()


def test_firefox_como_ultimo_recurso(ws, monkeypatch, tmp_path):
    from clipator import contayt
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws2")
    ff = tmp_path / "firefox.exe"
    ff.write_text("x")
    monkeypatch.setattr(contayt, "firefox", lambda: ff)  # já instalado: não chama o winget
    monkeypatch.setattr(contayt.time, "sleep", lambda s: None)
    abertos = []

    def popen(args, **k):
        abertos.append(args)
        pr = _ProcFalso()
        pr.vivo = False  # o usuário fechou o Firefox depois de entrar
        return pr

    monkeypatch.setattr(contayt.subprocess, "Popen", popen)

    class Ctx:
        progresso = staticmethod(lambda *a: None)
        log = staticmethod(lambda *a: None)
        cancelar = None

    r = srv._job_firefox_youtube({}, Ctx())
    assert r == {"firefox": True} and abertos == [[str(ff), "https://www.youtube.com/"]]
    assert srv.ws.config().youtube.cookies_navegador == "firefox"


def test_conta_youtube_renova_sem_janela_quando_velha(tmp_path, monkeypatch):
    import os as _os

    from clipator import contayt

    monkeypatch.setattr(contayt, "navegador", lambda: ("Edge", tmp_path / "msedge.exe"))
    monkeypatch.setattr(contayt, "fechar", lambda ws, proc: None)
    aberturas = []

    def abrir(exe, perfil, sem_janela, url="about:blank"):
        aberturas.append(sem_janela)
        return _ProcFalso(), "ws://x"

    assert not contayt.renovar(abrir=abrir, ler=lambda ws: _COOKIES_COM_LOGIN)  # sem perfil ainda: nada
    contayt.pasta_perfil().mkdir(parents=True)
    assert contayt.renovar(abrir=abrir, ler=lambda ws: _COOKIES_COM_LOGIN) and aberturas == [True]  # sem janela
    assert contayt.renovar(abrir=abrir, ler=lambda ws: _COOKIES_COM_LOGIN) and aberturas == [True]  # novo: não abre
    velho = contayt.arquivo_cookies().stat().st_mtime - contayt.IDADE_MAX - 10
    _os.utime(contayt.arquivo_cookies(), (velho, velho))
    assert contayt.renovar(abrir=abrir, ler=lambda ws: _COOKIES_COM_LOGIN) and aberturas == [True, True]
    assert not contayt.renovar(forcar=True, abrir=abrir, ler=lambda ws: _COOKIES_SEM_LOGIN)  # a sessão caiu


def test_conta_youtube_le_cookies_de_um_devtools_falso():
    import asyncio
    import json
    import threading

    import websockets

    from clipator import contayt

    pedidos = []
    pronto = threading.Event()
    estado = {}

    async def atender(ws):
        async for msg in ws:
            m = json.loads(msg)
            pedidos.append(m["method"])
            res = {"cookies": _COOKIES_COM_LOGIN} if m["method"] == "Storage.getCookies" else {}
            await ws.send(json.dumps({"id": m["id"], "result": res}))

    def servir():
        async def main():
            async with websockets.serve(atender, "127.0.0.1", 0) as srv:
                estado["porta"] = srv.sockets[0].getsockname()[1]
                pronto.set()
                await asyncio.sleep(3)

        asyncio.run(main())

    t = threading.Thread(target=servir, daemon=True)
    t.start()
    assert pronto.wait(5)
    url = f"ws://127.0.0.1:{estado['porta']}/devtools/browser/abc"
    assert contayt.ler_cookies(url) == _COOKIES_COM_LOGIN
    contayt.fechar(url, _ProcFalso())
    assert pedidos == ["Storage.getCookies", "Browser.close"]


def test_cadeia_renova_a_conta_quando_o_youtube_recusa(ws, ydl_falso, monkeypatch):
    from clipator import contayt, ingest

    p = _projeto_link(ws)
    contayt.gravar(_COOKIES_COM_LOGIN)
    renovou = []

    def renovar(forcar=False, **k):
        renovou.append(forcar)
        if forcar:
            ydl_falso.erro_com_cookies = None  # cookies novos: o YouTube aceita
        return True

    monkeypatch.setattr(contayt, "renovar", renovar)
    ydl_falso.erro_com_cookies = ydl_falso.ERRO_ROBO
    assert ingest.baixar("https://www.youtube.com/watch?v=abc", p).name == "video.mp4"
    assert renovou == [False, True]
    conta = str(contayt.arquivo_cookies())
    assert ydl_falso.chamadas == [{}, {"cookiefile": conta}, {"cookiefile": conta}]


# ---- explorador: canais e vídeos (detalhes, renomear, mover, apagar) -----------------------
def test_explorador_detalhes_renomear_mover_apagar(tmp_path):
    from fastapi.testclient import TestClient

    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws", nome_fila="jobs-explorador")
    a = srv.ws.criar_canal("Canal A", glossario=["Flávio"])
    b = srv.ws.criar_canal("Canal B")
    pr = a.criar_projeto("Vídeo um", Origem(tipo="link", valor="https://www.youtube.com/watch?v=abc"))
    pr.salvar_clip(Clip(id="01-x", inicio=1, fim=9, titulo="T"))
    (pr.clips_dir / "01-x" / "saida.mp4").write_bytes(b"x" * 1000)
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    lista = cl.get(f"/api/canais/{a.slug}/projetos", headers=h).json()
    assert lista[0]["clips"] == 1 and lista[0]["fase"] == "pendente"
    d = cl.get(f"/api/canais/{a.slug}/detalhes", headers=h).json()
    assert d["videos"] == 1 and d["clips"] == 1 and d["bytes"] >= 1000 and d["glossario"] == ["Flávio"]
    assert any(x.endswith("canal.md") for x in d["arquivos"])
    # renomear muda o nome que aparece; a pasta (e o que aponta para ela) fica
    assert cl.put(f"/api/canais/{a.slug}", json={"nome": "Cortes do A"}, headers=h).json()["nome"] == "Cortes do A"
    assert cl.get("/api/canais", headers=h).json()[0]["nome"] == "Cortes do A" and a.path.exists()
    assert cl.put(f"/api/canais/{a.slug}", json={"nome": "  "}, headers=h).status_code == 400
    dv = cl.put(f"/api/canais/{a.slug}/projetos/{pr.id}", json={"titulo": "Novo nome"}, headers=h).json()
    assert dv["titulo"] == "Novo nome" and dv["origem"].endswith("abc") and dv["clips"] == 1
    # com job rodando no vídeo, não move nem apaga
    j = srv.fila.enviar("analisar", {"canal": a.slug, "projeto": pr.id})
    srv.fila._atualizar(j, status="rodando")
    assert cl.post(f"/api/canais/{a.slug}/projetos/{pr.id}/mover", json={"destino": b.slug}, headers=h).status_code == 409
    assert cl.delete(f"/api/canais/{a.slug}", params={"so_conferir": "true"}, headers=h).status_code == 409
    srv.fila._atualizar(j, status="ok")
    # mover para outro canal
    r = cl.post(f"/api/canais/{a.slug}/projetos/{pr.id}/mover", json={"destino": b.slug}, headers=h).json()
    assert r == {"canal": b.slug, "projeto": pr.id} and (b.projetos_dir / pr.id / "clips" / "01-x" / "clip.yaml").exists()
    assert not (a.projetos_dir / pr.id).exists()
    # apagar: só com a confirmação certa; o vídeo pede confirmar=true
    assert cl.delete(f"/api/canais/{b.slug}/projetos/{pr.id}", headers=h).status_code == 400
    assert cl.delete(f"/api/canais/{b.slug}/projetos/{pr.id}", params={"so_conferir": "true"}, headers=h).json()["clips"] == 1
    assert cl.delete(f"/api/canais/{b.slug}/projetos/{pr.id}", params={"confirmar": "true"}, headers=h).status_code == 200
    assert not (b.projetos_dir / pr.id).exists()
    assert cl.delete(f"/api/canais/{a.slug}", params={"confirmar": "errado"}, headers=h).status_code == 400
    assert cl.delete(f"/api/canais/{a.slug}", params={"confirmar": a.slug}, headers=h).json() == {"apagado": a.slug}
    assert not a.path.exists() and b.path.exists()


def test_apagar_so_dentro_do_workspace(tmp_path):
    from clipator import gerenciar
    from clipator.workspace import Workspace, WorkspaceError

    ws = Workspace(tmp_path / "ws").init()
    fora = tmp_path / "fora"
    fora.mkdir()
    with pytest.raises(WorkspaceError):
        gerenciar.apagar(fora, ws)
    with pytest.raises(WorkspaceError):
        gerenciar.apagar(ws.canais_dir, ws)  # a pasta de canais inteira, não
    assert fora.exists()


def test_chamada_animada_gera_apng_com_alfa_e_cache_por_texto_e_cor(tmp_path):
    from PIL import Image

    from clipator import cta

    a = cta.gerar("inscreva-se", {}, tmp_path, None)
    with Image.open(a) as img:
        assert img.format == "PNG" and getattr(img, "is_animated", False)
        total = 0
        for k in range(img.n_frames):
            img.seek(k)
            total += img.info.get("duration", 0)
        assert total / 1000 == pytest.approx(cta.MODELOS["inscreva-se"].duracao, abs=0.15)
        img.seek(int(img.n_frames * 0.3))  # no meio: botão opaco e cantos transparentes
        q = img.convert("RGBA")
        alfas = q.getchannel("A")
        assert alfas.getextrema() == (0, 255) and q.getpixel((0, 0))[3] == 0
        assert q.width % 2 == 0 and q.height % 2 == 0
        img.seek(img.n_frames - 1)  # a chamada sai de cena no fim
        assert img.convert("RGBA").getchannel("A").getextrema()[1] < 40
    assert cta.gerar("inscreva-se", {}, tmp_path, None) == a  # cache
    b = cta.gerar("inscreva-se", {"texto": "se inscreve aí", "preset": "neon"}, tmp_path, None)
    c = cta.gerar("inscreva-se", {"cor": "#123456", "cor_texto": "nada"}, tmp_path, None)
    assert len({a, b, c}) == 3
    assert cta.opcoes("inscreva-se", {"texto": "  se   inscreve aí  ", "preset": "neon"}) == {
        "texto": "SE INSCREVE AÍ", "texto2": "INSCRITO", "cor": "#39FF14", "cor_texto": "#0A0A0A"}
    assert cta.opcoes("inscreva-se", {"cor": "#123456", "cor_texto": "nada"})["cor_texto"] == "#FFFFFF"
    assert cta.opcoes("curtir", {"idioma": "en"})["texto"] == "LIKE THE VIDEO"
    assert cta.opcoes("comente", {"texto2": "ignorado"})["texto2"] == ""
    assert len(cta.opcoes("sininho", {"texto": "x" * 200})["texto"]) == 40
    with pytest.raises(KeyError):
        cta.gerar("nao-existe", {}, tmp_path, None)


@pytest.mark.parametrize("modelo", sorted(__import__("clipator.cta", fromlist=["MODELOS"]).MODELOS))
def test_cada_chamada_desenha_sem_icones(tmp_path, modelo):
    from PIL import Image

    from clipator import cta

    with Image.open(cta.gerar(modelo, {"idioma": "en"}, tmp_path, None)) as img:
        assert img.n_frames >= 10 and img.width >= 100 and img.height >= 60
        total = 0
        for k in range(img.n_frames):  # quadros iguais em sequência viram um só, mas a duração fica
            img.seek(k)
            total += img.info.get("duration", 0)
        if not cta.MODELOS[modelo].fixo:  # o texto só tem a entrada; `duracao` é a do item
            assert total / 1000 == pytest.approx(cta.MODELOS[modelo].duracao, abs=0.1)


def test_chamada_na_biblioteca_no_filtro_e_no_som(tmp_path, monkeypatch):
    from clipator import cta, edicao, stickers

    monkeypatch.setenv("CLIPATOR_SONS", str(tmp_path / "sons"))
    lib = stickers.listar(None, _manifesto([]))
    assert lib["categorias"][0] == "chamadas"
    chamadas = [s for s in lib["stickers"] if s["categoria"] == "chamadas"]
    assert [s["ref"] for s in chamadas] == [f"cta:{m}" for m in cta.MODELOS] and lib["stickers"][0]["ref"] == "cta:inscreva-se"
    assert chamadas[0]["duracao"] == 3.2 and chamadas[0]["chamada"]["textos"]["en"] == ["SUBSCRIBE", "SUBSCRIBED"]
    assert stickers.resolver("cta:nao-existe", None) is None and stickers.resolver("cta:../x", None) is None
    itens = edicao.validar([
        {"tipo": "sticker", "inicio": 1, "fim": 4.2, "params": {"ref": "cta:inscreva-se", "texto": "Se inscreve",
                                                               "cor": "#00FF00", "hack": 1, "repetir": False}},
        {"tipo": "sticker", "inicio": 5, "fim": 8, "params": {"ref": "cta:curtir", "som": False, "repetir": False}},
    ], 10)
    p0 = itens[0].params
    assert p0["texto"] == "Se inscreve" and p0["cor"] == "#00FF00" and "hack" not in p0 and p0["som"] is True
    ent, partes, _ = edicao.filtros_video(edicao.Edicao(itens=itens), "vlay", 540, 960, 30, tmp_path, 3, None)
    arqs = [ent[k + 1] for k, v in enumerate(ent) if v == "-i"]
    assert len(arqs) == 2 and all(Path(x).parent == stickers.pasta_pacote() / "chamadas" for x in arqs)
    assert ent[:2] == ["-i", arqs[0]]  # animação de uma vez só: sem -ignore_loop
    assert "[3:v]setpts=PTS-STARTPTS+1.000/TB" in ";".join(partes) and "eof_action=repeat" in ";".join(partes)
    assert arqs[0] == str(cta.gerar("inscreva-se", p0, stickers.pasta_pacote() / "chamadas", stickers.pasta_pacote()))
    evs, sons_ = edicao.sons_da_edicao(edicao.Edicao(itens=itens), [])
    assert evs == [(f"edicao-{itens[0].id}", pytest.approx(1 + 1.15))] and sons_[f"edicao-{itens[0].id}"].name.startswith("click")


def test_inscreva_se_automatico_quando_o_canal_ativa(tmp_path):
    from fastapi.testclient import TestClient

    from clipator import edicao
    from clipator.api import criar_app
    from clipator.service import Servico
    from clipator.timeline import Timeline

    tl = Timeline.de_clip(0, 40)
    assert not [i for i in edicao.heuristica([], tl) if i.tipo == "sticker"]
    ambos = [i for i in edicao.heuristica([], tl, chamada="inicio-e-fim", idioma="en") if i.tipo == "sticker"]
    assert [(i.inicio, i.params["ref"], i.params["idioma"]) for i in ambos] == [
        (1.0, "cta:inscreva-se", "en"), (pytest.approx(40 - 3.2 - 0.3), "cta:inscreva-se", "en")]
    assert all(i.fim <= 40 and i.params["repetir"] is False for i in ambos)
    assert edicao.chamadas(4, "inicio") == []  # clip curto demais
    assert len(edicao.chamadas(12, "inicio-e-fim")) == 1  # só cabe uma sem ficar repetitivo

    srv = Servico(tmp_path / "ws", nome_fila="jobs-chamada")
    c = srv.ws.criar_canal("Teste")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    assert cl.get(f"/api/canais/{c.slug}/chamada", headers=h).json() == {"chamada_automatica": "nenhuma"}
    assert cl.put(f"/api/canais/{c.slug}/chamada", json={"chamada_automatica": "sempre"}, headers=h).status_code == 400
    assert cl.put(f"/api/canais/{c.slug}/chamada", json={"chamada_automatica": "fim"}, headers=h).json()["chamada_automatica"] == "fim"
    assert edicao.chamada_do_canal(pr) == ("fim", "pt")
    r = cl.get("/api/stickers/arquivo", params={"ref": "cta:siga", "texto": "me segue"}, headers=h)
    assert r.status_code == 200 and r.content[1:4] == b"PNG" and b"acTL" in r.content[:400]


def test_posicao_livre_arrastada_na_previa_vai_igual_para_o_render(tmp_path):
    from clipator import edicao

    canal = tmp_path / "canal"
    _png(canal / "stickers" / "b.png")
    itens = edicao.validar([
        {"tipo": "sticker", "inicio": 1, "fim": 3, "params": {"ref": "canal:b.png", "x": 0.38, "y": 0.57, "esticar": 1.5,
                                                             "entrada": "nenhuma"}},
        {"tipo": "texto", "inicio": 1, "fim": 3, "params": {"texto": "OI", "x": 0.25, "y": 1.7}},
        {"tipo": "emoji", "inicio": 1, "fim": 3, "params": {"emoji": "🔥", "x": "nada", "y": 0.2}},
    ], 10)
    st, tx, em = (next(i for i in itens if i.tipo == t) for t in ("sticker", "texto", "emoji"))
    assert (st.params["x"], st.params["y"], st.params["esticar"]) == (0.38, 0.57, 1.5)
    assert (tx.params["x"], tx.params["y"]) == (0.25, 1.0)  # fora do quadro: preso na borda
    assert "x" not in em.params and "y" not in em.params  # inválido: fica a posição fixa
    assert "esticar" not in edicao.normalizar_params("sticker", {"esticar": 1.0})
    _, partes, _ = edicao.filtros_video(edicao.Edicao(itens=[st, tx]), "vlay", 540, 960, 30, tmp_path, 4, canal)
    g = ";".join(partes)
    assert "overlay=x=W*0.3800-w/2:y=H*0.5700-h/2" in g
    assert "scale=iw:trunc(ih*1.500/2)*2" in g
    assert "x=W*0.2500-text_w/2:y=H*1.0000-text_h/2" in g


def test_chave_da_amostra_muda_com_o_estilo_e_os_ajustes(ws):
    from clipator import amostras

    c = ws.criar_canal("Teste")
    k1 = amostras.chave(ws, "podcast-limpo", c)
    assert k1 == amostras.chave(ws, "podcast-limpo", c) and k1.startswith("podcast-limpo-")
    assert amostras.chave(ws, "podcast-limpo", c, {"legenda": {"cor": "#FF0000"}}) != k1
    assert amostras.chave(ws, "podcast-limpo", c, formato="1:1") != k1
    # uma cópia do estilo no workspace passa a valer; editar a cópia muda a chave
    from clipator.workspace import estilos_embutidos_dir

    copia = ws.root / "estilos" / "podcast-limpo.md"
    copia.parent.mkdir(parents=True, exist_ok=True)
    copia.write_text((estilos_embutidos_dir() / "podcast-limpo.md").read_text(encoding="utf-8"), encoding="utf-8")
    assert amostras.chave(ws, "podcast-limpo", c) == k1  # mesmo conteúdo: a amostra continua valendo
    copia.write_text(copia.read_text(encoding="utf-8") + "\n<!-- mudou -->\n", encoding="utf-8")
    assert amostras.chave(ws, "podcast-limpo", c) != k1
    assert amostras.caminho_amostra(ws, "podcast-limpo", c).parent == amostras.pasta_cache()
    t = amostras._transcricao()
    pals = [w for s in t["segmentos"] for w in s["palavras"]]
    assert pals and pals[-1]["fim"] <= amostras.DURACAO and all(a["fim"] <= b["inicio"] for a, b in zip(pals, pals[1:]))


@precisa_ffmpeg
def test_amostra_do_estilo_renderiza_uma_vez_e_fica_em_cache(ws, monkeypatch):
    from clipator import amostras, media

    c = ws.criar_canal("Teste")
    from clipator.workspace import estilos_embutidos_dir

    copia = ws.root / "estilos" / "podcast-limpo.md"  # o estilo editado pelo usuário: outro hash, sem amostra pronta
    copia.parent.mkdir(parents=True, exist_ok=True)
    copia.write_text((estilos_embutidos_dir() / "podcast-limpo.md").read_text(encoding="utf-8") + "\n<!-- meu -->\n", encoding="utf-8")
    assert amostras.achar(ws, "podcast-limpo", c) is None
    p = amostras.gerar(ws, "podcast-limpo", c)
    assert p.parent == amostras.pasta_cache() and amostras.achar(ws, "podcast-limpo", c) == p
    info = media.probe(p)
    assert p.exists() and p.with_suffix(".jpg").exists() and info.duracao == pytest.approx(amostras.DURACAO - 0.1, abs=0.4)
    assert (info.largura, info.altura) == (540, 960)  # meia resolução do 9:16
    chamadas = []
    monkeypatch.setattr(amostras, "_renderizar", lambda *a, **k: chamadas.append(1))
    assert amostras.gerar(ws, "podcast-limpo", c) == p and not chamadas  # do cache, sem renderizar de novo
    assert not (amostras.pasta_cache() / "trabalho").exists() or not any((amostras.pasta_cache() / "trabalho").iterdir())


def test_api_das_amostras_padrao_do_canal_e_ajustes_na_selecao(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clipator import amostras
    from clipator.api import criar_app
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws", nome_fila="jobs-amostras")
    c = srv.ws.criar_canal("Teste")
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    lista = cl.get("/api/estilos", params={"canal": c.slug}, headers=h).json()
    pl = next(e for e in lista if e["id"] == "podcast-limpo")
    assert pl["padrao"] and pl["origem"] == "embutido" and pl["amostra"] == "podcast-limpo.mp4"  # vem pronta com o Clipator
    assert pl["detalhes"]["legenda"]["fonte"] and "sons" in pl["detalhes"]
    # um estilo do canal (sem amostra pronta) já em cache aparece pronto; o que falta vira um job só
    (c.path / "estilos").mkdir(exist_ok=True)
    from clipator.workspace import estilos_embutidos_dir

    for nome in ("meu-impacto", "meu-gamer"):
        (c.path / "estilos" / f"{nome}.md").write_text((estilos_embutidos_dir() / "impacto.md").read_text(encoding="utf-8")
                                                        .replace("nome: Impacto", f"nome: {nome}"), encoding="utf-8")
    pronta = amostras.caminho_amostra(srv.ws, "meu-impacto", c)
    pronta.parent.mkdir(parents=True, exist_ok=True)
    pronta.write_bytes(b"mp4")
    enviados = []
    monkeypatch.setattr(srv.fila, "enviar", lambda tipo, p: enviados.append((tipo, p)) or "job1")
    r = cl.post("/api/estilos/amostras", json={"canal": c.slug, "estilos": ["impacto", "meu-impacto", "meu-gamer"]}, headers=h).json()
    assert r == {"prontas": {"impacto": "impacto.mp4", "meu-impacto": pronta.name}, "faltam": ["meu-gamer"], "job": "job1"}
    assert enviados == [("amostras_estilo", {"canal": c.slug, "estilos": ["meu-gamer"], "ajustes": None, "formato": None})]
    assert cl.get("/api/estilos/amostra/arquivo", params={"nome": pronta.name}, headers=h).content == b"mp4"
    assert cl.get("/api/estilos/amostra/arquivo", params={"nome": "impacto.mp4"}, headers=h).content[4:8] == b"ftyp"
    assert cl.get("/api/estilos/amostra/arquivo", params={"nome": "impacto.jpg"}, headers=h).status_code == 200
    assert cl.get("/api/estilos/amostra/arquivo", params={"nome": "../segredo.mp4"}, headers=h).status_code == 400
    assert cl.get("/api/estilos/amostra/arquivo", params={"nome": "nao-tem.mp4"}, headers=h).status_code == 404
    # padrão do canal
    assert cl.put(f"/api/canais/{c.slug}/estilo-padrao", json={"estilo": "nao-existe"}, headers=h).status_code == 404
    assert cl.put(f"/api/canais/{c.slug}/estilo-padrao", json={"estilo": "impacto"}, headers=h).json() == {"estilo_padrao": "impacto"}
    lista = cl.get("/api/estilos", params={"canal": c.slug}, headers=h).json()
    assert [e["id"] for e in lista if e["padrao"]] == ["impacto"]
    assert next(e for e in lista if e["id"] == "impacto")["amostra"] == "impacto.mp4"
    # os ajustes do passo 3 vão para o clip; trocar o estilo de um clip existente mantém só a altura da legenda
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    from clipator.workspace import write_json

    write_json(pr.analise_dir / "candidatos.json", [{"id": "c1", "inicio": 10.0, "fim": 30.0, "nota": 70, "texto": "x", "titulos": ["T"]}])
    base = f"/api/canais/{c.slug}/projetos/{pr.id}"
    clips = cl.post(f"{base}/selecionar", json={"ids": ["c1"], "estilo": "gamer", "ajustes": {"legenda": {"cor": "#FF0000"}}}, headers=h).json()
    assert clips[0]["estilo"] == "gamer" and clips[0]["ajustes_estilo"] == {"legenda": {"cor": "#FF0000"}}
    clip, _ = pr.clip(clips[0]["id"])
    clip.ajustes_estilo = {"legenda": {"cor": "#FF0000", "altura_relativa": 0.6}}
    pr.salvar_clip(clip)
    clips = cl.post(f"{base}/selecionar", json={"ids": ["c1"], "estilo": "impacto", "ajustes": {"zoom": {"enfase": True}}}, headers=h).json()
    assert clips[0]["estilo"] == "impacto" and clips[0]["ajustes_estilo"] == {"legenda": {"altura_relativa": 0.6}, "zoom": {"enfase": True}}
    assert cl.post(f"{base}/amostra-estilo", json={"estilo": "impacto", "candidato": "c1"}, headers=h).json() == {"job": "job1"}


# ---- direção de arte ------------------------------------------------------------------------------
def _fala(texto, t=0.2):
    pals = []
    for w in texto.split():
        pals.append({"texto": w, "inicio": round(t, 2), "fim": round(t + 0.3, 2)})
        t += 0.36 + (0.3 if w.endswith(".") else 0)
    return pals, t + 1


FALA_DA = ("Em 2019 a empresa faturou 30 milhões de reais. Em 2023 caiu para 5 milhões. O João Silva disse que isso é "
           "um absurdo total para todos. Primeiro, corte os gastos. Segundo, venda o carro. Terceiro, invista no Brasil. "
           "Cuidado com golpe na internet.")


def test_planejador_por_regras_segue_a_fala():
    from clipator import direcao

    pals, dur = _fala(FALA_DA)
    cenas = direcao.planejar_regras(pals, dur, "Como a empresa quebrou", 3.0)
    tipos = [c.params["cena"] for c in cenas]
    assert "linha_do_tempo" in tipos and "lista" in tipos and "citacao" in tipos
    lista = next(c for c in cenas if c.params["cena"] == "lista")
    assert lista.params["itens"] == ["corte os gastos", "venda o carro", "invista no Brasil"]
    cit = next(c for c in cenas if c.params["cena"] == "citacao")
    assert cit.params["texto"].startswith("isso é um absurdo") and cit.params["autor"] == "Silva"
    assert all(0 <= c.inicio < c.fim <= dur for c in cenas)
    assert all(a.fim <= b.inicio for a, b in zip(cenas, cenas[1:]))  # nunca duas ao mesmo tempo
    assert all(c.params.get("ancora") for c in cenas)
    # o número que fecha a frase pega o rótulo do que veio antes dele
    pals2, dur2 = _fala("Esse mês a gente vendeu 300 unidades. Foi muito.")
    num = direcao.planejar_regras(pals2, dur2, "", 3.0)[0]
    assert num.params["cena"] == "numero" and num.params["valor"] == "300" and num.params["rotulo"] == "unidades"


def test_ancora_acha_o_trecho_mesmo_com_erro_de_transcricao():
    from clipator import direcao

    pals, _ = _fala(FALA_DA)
    i, j, nota = direcao.ancorar("o joão silva disse que", pals)
    assert nota == 1.0 and pals[i]["texto"] == "O" and pals[j]["texto"] == "que"
    i, j, nota = direcao.ancorar("o joao silvo disse que isso", pals)  # nome errado: casa por aproximação
    assert pals[i]["texto"] == "O" and 0.75 <= nota < 1
    assert direcao.ancorar("nada disso foi dito aqui", pals) is None
    pals3, _ = _fala("Olha isso. Olha isso de novo.")
    assert direcao.ancorar("olha isso", pals3, desde=2)[0] == 2  # frase repetida: a partir de `desde`


def test_cenas_da_ia_sao_conferidas_contra_a_fala():
    from clipator import direcao

    pals, dur = _fala(FALA_DA)
    vazio = {"texto": "", "itens": [], "valor": "", "rotulo": "", "autor": "", "a": "", "b": "", "duracao": 3, "motivo": "x"}
    resp = {"cenas": [
        {**vazio, "cena": "numero", "ancora": "faturou 30 milhões de reais", "valor": "30 milhões", "rotulo": "faturamento"},
        {**vazio, "cena": "numero", "ancora": "caiu para 5 milhões", "valor": "80 milhões"},  # número que ninguém disse
        {**vazio, "cena": "citacao", "ancora": "disse que isso é um", "texto": "vou processar todo mundo"},  # citação inventada
        {**vazio, "cena": "palavra", "ancora": "trecho que não existe na fala", "texto": "X"},
        {**vazio, "cena": "lista", "ancora": "Primeiro, corte os gastos.", "itens": ["cortar gastos", "vender o carro"], "duracao": 4},
        {**vazio, "cena": "hack", "ancora": "Cuidado com golpe"},
    ]}
    cenas = direcao.de_resposta_ia(resp, pals, dur)
    assert [c.params["cena"] for c in cenas] == ["numero", "lista"]
    assert cenas[0].inicio == pytest.approx(pals[4]["inicio"] - 0.1) and cenas[0].params["ancora"].startswith("faturou")
    assert direcao.de_resposta_ia(None, pals, dur) == [] and direcao.de_resposta_ia({"cenas": "x"}, pals, dur) == []
    p = direcao.prompt_cenas(pals, dur, "Título")
    assert "ancora" in p and "[0.2]" in p and len(p) < 6000
    assert set(direcao.SCHEMA_CENAS["properties"]["cenas"]["items"]["required"]) >= {"cena", "ancora"}


def test_camada_de_cenas_e_ficha():
    from clipator import direcao

    f = direcao.ficha("dossie", {"primaria": "#00FF00", "texto": "vermelho", "fonte_titulo": "Anton", "entrada": "voar"})
    assert f.primaria == "#00FF00" and f.texto == direcao.FICHAS["dossie"]["texto"] and f.fonte_titulo == "Anton"
    assert f.entrada == "mascara"
    cenas = [{"inicio": 1.0, "fim": 4.0, "params": {"cena": "numero", "valor": "30 milhões", "rotulo": "<b>faturou</b>"}},
             {"inicio": 6.0, "fim": 9.0, "params": {"cena": "lista", "itens": ["a", "b", "c"]}}]
    doc = direcao.compor_camada(cenas, f, 540, 960, 12.0, "em-cima", 0.45, "Meu título")
    assert doc.count('class="clip cena') == 2 and 'data-start="1.000" data-duration="3.000"' in doc
    assert "--alvo:30" in doc and "&lt;b&gt;faturou&lt;/b&gt;" in doc and "<b>" not in doc  # texto sempre escapado
    assert 'body class="opaca layout-em-cima ficha-dossie"' in doc and "--primaria: #00FF00" in doc and "--alt: 45.00%" in doc
    assert 'class="clip repouso"' not in doc and "Meu título" not in doc  # sem título fixo: nos vãos fica o fundo da ficha
    maquete = direcao.compor_camada(cenas, direcao.ficha("maquete"), 540, 960, 12.0, "em-cima", 0.55, "Meu título")
    assert maquete.count('class="clip repouso"') == 2  # só a maquete: título nos vãos (0-1 s é curto demais; 4-6 e 9-12)
    transp = direcao.compor_camada(cenas, f, 540, 960, 12.0, "sobreposto")
    assert 'body class="transparente' in transp and 'class="clip repouso"' not in transp and 'id="fundo"' not in transp
    assert direcao.eventos_de_som(cenas, f) == [("cena-0", 1.0, f.sons["numero"]), ("cena-1", 6.0, f.sons["enfase"])]


def test_layouts_da_direcao_de_arte_no_grafo():
    from clipator.models import DirecaoArte
    from clipator.render import cadeia_mistura

    g = ";".join(cadeia_mistura("em-cima", DirecaoArte(layout="em-cima", proporcao=0.45), "#FF2E88", 540, 960, 3, None, "nenhum"))
    assert "[3:v]setpts=PTS-STARTPTS,scale=540:960" in g and "[vlay]crop=540:528:0:" in g and "overlay=0:432" in g
    assert "drawbox" in g and "0xFF2E88" in g and g.endswith("[vda]")
    g = ";".join(cadeia_mistura("fundo", DirecaoArte(layout="fundo", pessoa_escala=0.7), "#FFFFFF", 540, 960, 3, 4, "mascara"))
    assert "[4:v]setpts=PTS-STARTPTS,scale=540:960" in g and "alphamerge" in g and "scale=-2:672" in g and "y=H-h" in g
    g = ";".join(cadeia_mistura("fundo", DirecaoArte(layout="fundo"), "#FFFFFF", 540, 960, 3, None, "chroma", "chromakey=color=0x00FF00"))
    assert "[vlay]chromakey=color=0x00FF00" in g and "alphamerge" not in g
    g = ";".join(cadeia_mistura("janela", DirecaoArte(layout="janela", janela_escala=0.36), "#38E1FF", 540, 960, 3, None, "nenhum"))
    assert "[vlay]scale=194:-2,pad=" in g and "color=0x38E1FF" in g
    g = ";".join(cadeia_mistura("sobreposto", DirecaoArte(layout="sobreposto"), "#FFFFFF", 540, 960, 3, None, "nenhum"))
    assert "[vlay][cen]overlay=0:0:format=auto" in g


def test_deteccao_de_chroma_key():
    import numpy as np

    from clipator import recorte

    verde = np.zeros((90, 160, 3), np.uint8)
    verde[:] = (40, 200, 30)  # BGR: fundo verde
    verde[30:90, 60:100] = (90, 110, 160)  # a pessoa no meio
    ch = recorte.detectar_chroma([verde, verde.copy()])
    assert ch is not None and ch.canal == "green" and ch.cor.startswith("0x") and ch.fracao > 0.6
    assert "chromakey=color=" in recorte.filtro_chroma(ch) and "despill=type=green" in recorte.filtro_chroma(ch)
    normal = np.random.default_rng(1).integers(0, 255, (90, 160, 3), dtype=np.uint8)
    assert recorte.detectar_chroma([normal]) is None and recorte.detectar_chroma([]) is None


def test_mascara_suave_e_estavel():
    import numpy as np

    from clipator import recorte

    m = np.zeros((200, 200), np.float32)
    m[50:150, 50:150] = 1
    s1 = recorte.suavizar(m, None)
    assert s1[100, 100] == pytest.approx(1.0) and s1[0, 0] == 0.0 and 0 < s1[49, 100] < 1  # borda macia
    ruido = m.copy()
    ruido[0, 0] = 0.9  # um pixel solto num quadro só: não aparece
    assert recorte.suavizar(ruido, s1)[0, 0] < 0.2
    r = recorte.rampa_lateral(100, 10)
    assert r[0, 0] == 0 and r[0, 50] == 1 and r.shape == (10, 100)
    oval = recorte.mascara_oval(60, 100)
    assert oval[60, 30] == 1 and oval[2, 2] == 0


@precisa_ffmpeg
def test_gera_mascara_de_um_clip_sintetico_com_segmentador_falso(tmp_path):
    import numpy as np

    from clipator import media, recorte

    class Falso:
        nome = "falso"

        def mascara(self, rgb, t_ms):
            m = np.zeros(rgb.shape[:2], np.float32)
            m[:, rgb.shape[1] // 3: 2 * rgb.shape[1] // 3] = 1
            return m

        def fechar(self):
            pass

    cmd = [media.ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=64x112:r=10:d=1",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    saida = tmp_path / "recorte-x.mkv"
    p = recorte.gerar_mascara(cmd, 64, 112, 10, 1.0, saida, Falso())
    info = media.probe(p)
    assert p.exists() and (info.largura, info.altura) == (64, 112) and info.duracao == pytest.approx(1.0, abs=0.15)
    assert recorte.gerar_mascara(["nao-roda"], 64, 112, 10, 1.0, saida) == saida  # do cache
    cancelar = threading.Event()
    cancelar.set()
    with pytest.raises(media.Cancelado):
        recorte.gerar_mascara(cmd, 64, 112, 10, 1.0, tmp_path / "outra.mkv", Falso(), cancelar=cancelar)
    assert not (tmp_path / "outra.mkv").exists() and not list(tmp_path.glob("*.tmp.mkv"))


def test_cenas_no_editor_e_nas_propostas(ws):
    from clipator import edicao
    from clipator.timeline import Timeline

    item = edicao.validar([{"tipo": "cena", "inicio": 1, "fim": 4, "params": {"cena": "lista", "itens": ["a", " ", "b" * 90],
                                                                              "texto": "x" * 200, "hack": 1}}], 10)[0]
    assert item.faixa == "cena" and item.params["cena"] == "lista" and item.params["itens"] == ["a", "b" * 48]
    assert len(item.params["texto"]) == 90 and "hack" not in item.params
    assert edicao.normalizar_params("cena", {"cena": "nao-existe"})["cena"] == "palavra"
    c = ws.criar_canal("Teste")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    pr.salvar_clip(Clip(id="01-x", inicio=0, fim=25, titulo="Como a empresa quebrou", estilo="da-animacao-em-cima"))
    clip, _ = pr.clip("01-x")
    pals, _ = _fala(FALA_DA)
    tl = Timeline.de_clip(0, 25)
    cenas, aviso = edicao.cenas_sugeridas(pr, clip, tl, pals)  # o estilo usa IA: sem ela, nada (com o aviso)
    assert cenas == [] and "Claude Code" in aviso
    ia = IAFalsa({"cenas": [{"cena": "lista", "ancora": "Primeiro, corte os gastos.", "texto": "", "itens": ["cortar", "vender"],
                             "valor": "", "rotulo": "", "autor": "", "a": "", "b": "", "duracao": 4, "motivo": "enumeração"}]})
    cenas, aviso = edicao.cenas_sugeridas(pr, clip, tl, pals, ia)
    assert [(i.tipo, i.origem, i.params["cena"]) for i in cenas] == [("cena", "ia", "lista")] and aviso is None
    assert edicao.cenas_sugeridas(pr, clip.model_copy(update={"estilo": "podcast-limpo"}), tl, pals) == ([], None)
    est, _, _ = ws.carregar_estilo("da-animacao-de-fundo", c)
    assert est.direcao.layout == "fundo" and est.direcao.ficha == "dossie" and est.direcao.ativa
    for nome in ("da-animacao-em-cima", "da-cenas-por-cima", "da-video-na-janela"):
        assert ws.carregar_estilo(nome, c)[0].direcao.ativa


@precisa_ffmpeg
def test_render_com_direcao_de_arte_sem_hyperframes(ws, video_teste, monkeypatch):
    from clipator import edicao, hyperframes, transcribe

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    monkeypatch.setattr(hyperframes, "comando", lambda: None)
    c, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="da-video-na-janela")[0]
    from clipator import melhorar

    with pytest.raises(melhorar.SemIA, match="usa IA"):  # estilo com a etiqueta "Usa IA" e nenhuma IA instalada
        pipeline.renderizar(p, clip.id, preview=True)
    ia = IAFalsa({"cenas": []})  # a IA não achou cenas: o render usa as regras
    monkeypatch.setattr(melhorar, "ia_do_workspace", lambda ws, esperar_login=None: ia)
    r = pipeline.renderizar(p, clip.id, preview=True)
    assert ia.prompts and "ancora" in ia.prompts[0]
    info = media.probe(r.video)
    assert info.duracao == pytest.approx(clip.fim - clip.inicio, abs=0.25) and "HyperFrames" in (r.aviso or "")
    pasta = p.clips_dir / clip.id
    doc = edicao.carregar(pasta)
    assert doc.cenas_planejadas  # o render propôs as cenas uma vez e guardou no edicao.json
    edicao.salvar(pasta, doc.model_copy(update={"itens": [i for i in doc.itens if i.tipo != "cena"]}))
    pipeline.renderizar(p, clip.id, preview=True)
    assert not [i for i in edicao.carregar(pasta).itens if i.tipo == "cena"]  # apagou todas: não volta


def test_render_de_estilo_de_cenas_passa_pela_pre_producao(ws, video_teste, monkeypatch):
    from clipator import desenho, edicao, hyperframes, melhorar, transcribe
    from clipator.timeline import Timeline

    from .conftest import WhisperFalso

    monkeypatch.setattr(transcribe, "carregar_modelo", lambda *a, **k: WhisperFalso(transcricao_falsa(duracao=9)))
    monkeypatch.setattr(hyperframes, "comando", lambda: None)
    c, p = _projeto_com_video(ws, video_teste)
    cands = pipeline.analisar(p, lambda f, m: None, modo_ia="sem-ia")
    clip = pipeline.selecionar(p, [cands[0]["id"]], formato="9:16", estilo="da-video-na-janela")[0]
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    ancora = " ".join(w["texto"] for w in edicao.palavras_do_clip(p, tl)[:5])

    def resposta(prompt):
        if prompt.startswith("Analise este corte"):
            return {"tema": "O assunto", "ideias": []}
        if prompt.startswith("Escreva o roteiro"):
            return {"cenas": [{"ancora": ancora, "ate": "", "etiqueta": "o começo", "descricao": "A ideia", "dado": "", "balao": ""}]}
        return {"cenas": [{"cena": "palavra", "ancora": ancora, "texto": "IDEIA", "itens": [], "valor": "", "rotulo": "", "autor": "",
                           "a": "", "b": "", "duracao": 3, "motivo": "ilustra"}]}

    ia = IAFalsa(resposta)
    monkeypatch.setattr(melhorar, "ia_do_workspace", lambda ws, esperar_login=None: ia)
    pipeline.renderizar(p, clip.id, preview=True)
    assert len(ia.prompts) == 3 and "A ideia" in ia.prompts[2]
    pasta = p.clips_dir / clip.id
    doc = edicao.carregar(pasta)
    assert doc.cenas_planejadas and [i.params["texto"] for i in doc.itens if i.tipo == "cena"] == ["IDEIA"]
    assert desenho.ler(pasta)["analise"]["tema"] == "O assunto"
    pipeline.renderizar(p, clip.id, preview=True)
    assert len(ia.prompts) == 3  # o segundo render usa as cenas que já estão na edição


# ---- Melhorar com IA e versões --------------------------------------------------------------------
class IAFalsa:
    nome = "falsa"

    def __init__(self, resposta):
        self.resposta = resposta
        self.prompts = []

    def disponivel(self):
        return True

    def run_json(self, prompt, schema, cancelar=None):
        self.prompts.append(prompt)
        return self.resposta(prompt) if callable(self.resposta) else self.resposta


def _clip_com_fala(ws, estilo="da-animacao-em-cima"):
    from clipator import edicao
    from clipator.workspace import write_json

    c = ws.criar_canal("Teste")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    pals, dur = _fala(FALA_DA, t=0.2)
    # um silêncio de 2 s no meio (depois de "milhões.")
    for w in pals[15:]:
        w["inicio"] += 2.0
        w["fim"] += 2.0
    write_json(pr.transcricao_path, {"idioma": "pt", "duracao": dur + 3, "segmentos": [
        {"inicio": pals[0]["inicio"], "fim": pals[-1]["fim"], "texto": FALA_DA, "palavras": [dict(w, prob=0.9) for w in pals]}]})
    pr.salvar_clip(Clip(id="01-x", inicio=0, fim=dur + 2, titulo="Como a empresa quebrou", estilo=estilo))
    clip, pasta = pr.clip("01-x")
    edicao.salvar(pasta, edicao.Edicao(itens=[edicao.Item(id="z1", tipo="zoom", inicio=1, fim=2),
                                              edicao.Item(id="t1", tipo="texto", inicio=3, fim=4, params={"texto": "OLHA"})]))
    return c, pr, pals


def _plano(**extra):
    vazio = {"ancora": "", "cena": "", "texto": "", "itens": [], "valor": "", "rotulo": "", "autor": "", "a": "", "b": "",
             "sticker": "", "emoji": "", "som": "", "escala": 0, "posicao": "", "motivo": "x"}
    base = {"resumo": ["Mais cenas que seguem a fala", "Tirei o texto solto"], "manter": ["z1"], "destaques": ["absurdo", "inventada"],
            "pausas": [], "itens": [
                {**vazio, "tipo": "cena", "inicio": 0, "fim": 4, "cena": "lista", "ancora": "Primeiro, corte os gastos.",
                 "itens": ["cortar gastos", "vender o carro", "investir"]},
                {**vazio, "tipo": "cena", "inicio": 1, "fim": 3, "cena": "numero", "ancora": "faturou 30 milhões de reais",
                 "valor": "99 milhões"},  # número que ninguém disse
                {**vazio, "tipo": "sticker", "inicio": 2, "fim": 3, "sticker": "cta:inscreva-se"},
                {**vazio, "tipo": "sticker", "inicio": 2, "fim": 3, "sticker": "unicornio-voador"},
                {**vazio, "tipo": "som", "inicio": 5, "fim": 5.5, "som": "trombone"},
                {**vazio, "tipo": "texto", "inicio": 6, "fim": 7, "texto": "R$ 500 MIL"},  # número que não foi dito
                {**vazio, "tipo": "zoom", "inicio": 0, "fim": 1, "ancora": "o João Silva disse", "escala": 1.3},
            ]}
    base.update(extra)
    return base


def test_prompt_de_melhorar_tem_o_estilo_a_fala_e_a_edicao_atual(ws):
    from clipator import direcao, edicao, melhorar

    c, pr, pals = _clip_com_fala(ws)
    est, corpo, _ = ws.carregar_estilo("da-animacao-em-cima", c)
    f = direcao.ficha(est.direcao.ficha)
    txt = melhorar.resumo_do_estilo(est, corpo, f, "## Skill do usuário: X\n" + "regra " * 3000)
    assert len(txt) <= melhorar.LIMITE_ESTILO and '"layout": "em-cima"' in txt and f.primaria in txt and "Skill do usuário" in txt
    assert '"requer_ia"' not in txt
    clip, pasta = pr.clip("01-x")
    doc = edicao.carregar(pasta)
    from clipator.plataformas import info

    p = melhorar.prompt_melhorar(txt, pals, 20.0, doc, "mais dinâmico", info(None, "9:16").zona, [3.0, 9.5], [], ["fogo"])
    assert "mais dinâmico" in p and '"id": "t1"' in p and "[0.20]Em" in p and "cta:inscreva-se" in p and "9.5" in p
    assert set(melhorar.SCHEMA_MELHORAR["required"]) == {"resumo", "manter", "itens", "destaques", "pausas"}


def test_resposta_da_ia_e_conferida_e_os_descartes_tem_motivo(ws):
    from clipator import edicao, melhorar

    c, pr, pals = _clip_com_fala(ws)
    _, pasta = pr.clip("01-x")
    doc = edicao.carregar(pasta)
    a, b = round(pals[14]["fim"] + 0.1, 2), round(pals[15]["inicio"] - 0.1, 2)  # o silêncio de 2 s
    plano = _plano(pausas=[{"inicio": a, "fim": b}, {"inicio": 0.1, "fim": 0.9}])
    itens, destaques, pausas, resumo, desc = melhorar.validar_resposta(plano, pals, 30.0, doc, {"fogo": "pacote:x/fogo"})
    tipos = sorted((i.tipo, i.params.get("cena") or i.params.get("ref") or "") for i in itens)
    assert tipos == [("cena", "lista"), ("sticker", "cta:inscreva-se"), ("zoom", ""), ("zoom", "")]
    assert any(i.id == "z1" for i in itens) and not any(i.id == "t1" for i in itens)  # manteve só o que a IA pediu
    zoom_novo = next(i for i in itens if i.tipo == "zoom" and i.id != "z1")
    assert zoom_novo.inicio == pytest.approx(next(w for w in pals if w["texto"] == "O")["inicio"])  # foi para o trecho citado
    motivos = " | ".join(d["motivo"] for d in desc)
    assert "não bate com a fala" in motivos and "não existe na biblioteca" in motivos and "desconhecido" in motivos
    assert "número que não foi dito" in motivos and "tem fala dentro" in motivos
    assert destaques == ["absurdo"] and pausas == [(a, b)] and resumo[0].startswith("Mais cenas")
    assert melhorar.validar_resposta(None, pals, 30, doc, {})[4][0]["motivo"].startswith("a IA não")


def test_melhorar_cria_versoes_que_dao_para_usar_e_comparar(ws, monkeypatch):
    from clipator import edicao, melhorar

    c, pr, pals = _clip_com_fala(ws)
    clip, pasta = pr.clip("01-x")
    with pytest.raises(melhorar.SemIA):
        melhorar.melhorar(pr, "01-x", "mais dinâmico")
    a, b = round(pals[14]["fim"] + 0.1, 2), round(pals[15]["inicio"] - 0.1, 2)
    ia = IAFalsa(_plano(pausas=[{"inicio": a, "fim": b}]))
    r = melhorar.melhorar(pr, "01-x", "mais dinâmico", ad=ia)
    assert r["versao"] == 2 and any("Mais cenas" in x for x in r["resumo"]) and r["descartados"]
    lst = melhorar.listar(pr, "01-x")
    assert [v["n"] for v in lst["versoes"]] == [2, 1] and lst["atual"] == 2 and lst["versoes"][0]["origem"] == "ia"
    assert lst["versoes"][0]["feedback"] == "mais dinâmico" and lst["versoes"][0]["modelo"] == "falsa" and "mais dinâmico" in lst["chips"]
    clip, _ = pr.clip("01-x")
    assert len(clip.cortes_internos) == 1  # a pausa foi cortada
    doc = edicao.carregar(pasta)
    assert doc.destaques == ["absurdo"] and {i.tipo for i in doc.itens} >= {"cena", "sticker"}
    lista = next(i for i in doc.itens if i.tipo == "cena")
    assert lista.inicio == pytest.approx(next(w for w in pals if w["texto"] == "Primeiro,")["inicio"] - (b - a) - 0.1, abs=0.05)
    cmp_ = melhorar.comparar(pr, "01-x", 1, 2)
    assert cmp_["a"]["n"] == 1 and len(cmp_["b"]["itens"]) == len(doc.itens) and any("pausa" in d for d in cmp_["diferencas"])
    # voltar para a v1: a edição e os cortes de antes
    melhorar.usar(pr, "01-x", 1)
    clip, _ = pr.clip("01-x")
    doc = edicao.carregar(pasta)
    assert clip.cortes_internos == [] and sorted(i.id for i in doc.itens) == ["t1", "z1"] and doc.destaques == []
    assert melhorar.listar(pr, "01-x")["atual"] == 1
    with pytest.raises(KeyError):
        melhorar.usar(pr, "01-x", 9)
    # o pedido vai com o estilo e a edição atual dentro do limite
    assert "Estilo (YAML resumido)" in ia.prompts[0] and '"id": "z1"' in ia.prompts[0]


def test_edicao_a_mao_e_pelo_mcp_vira_versao(tmp_path):
    from fastapi.testclient import TestClient

    from clipator import edicao_ia, melhorar
    from clipator.api import criar_app
    from clipator.mcp_server import criar_servidor
    from clipator.service import Servico

    srv = Servico(tmp_path / "ws", nome_fila="jobs-versoes")
    c, pr, pals = _clip_com_fala(srv.ws)
    cl = TestClient(criar_app(srv, token="t"))
    h = {"x-clipator-token": "t"}
    base = f"/api/canais/{c.slug}/projetos/{pr.id}/clips/01-x"
    d = cl.get(f"{base}/edicao", headers=h).json()
    r = cl.put(f"{base}/edicao", json={"revisao": d["revisao"], "itens": d["itens"][:1]}, headers=h)
    assert r.status_code == 200
    r = cl.put(f"{base}/edicao", json={"revisao": r.json()["revisao"], "itens": []}, headers=h)
    v = cl.get(f"{base}/edicao/versoes", headers=h).json()
    assert [x["origem"] for x in v["versoes"]] == ["manual", "inicial"]  # duas gravações seguidas: uma versão só
    asyncio.run(criar_servidor(srv).call_tool("aplicar_edicao", {"canal": c.slug, "projeto": pr.id, "clip": "01-x",
                                                                  "adicionar": [{"tipo": "zoom", "inicio": 1, "fim": 2}]}))
    v = cl.get(f"{base}/edicao/versoes", headers=h).json()
    assert v["versoes"][0]["origem"] == "mcp" and v["atual"] == 3 and "+1: zoom" in v["versoes"][0]["resumo"]
    assert cl.post(f"{base}/edicao/versoes/1/usar", headers=h).json() == {"atual": 1}
    assert cl.get(f"{base}/edicao/versoes/comparar", params={"a": 1, "b": 3}, headers=h).json()["diferencas"]
    assert cl.post(f"{base}/edicao/versoes/9/previa", headers=h).status_code == 404
    assert cl.post(f"{base}/melhorar", json={"feedback": "x"}, headers=h).status_code == 409  # sem IA instalada
    lista = cl.get("/api/estilos", params={"canal": c.slug}, headers=h).json()
    assert next(e for e in lista if e["id"] == "da-animacao-de-fundo")["requer_ia"] is True
    assert next(e for e in lista if e["id"] == "podcast-limpo")["requer_ia"] is False
    # o pedido.md da conversa leva a ficha do estilo e o caminho pelo MCP
    _, texto = edicao_ia.montar_pedido(pr, "01-x", "deixa mais dinâmico")
    assert "## Estilo do clip" in texto and "aplicar_edicao" in texto and '"layout": "em-cima"' in texto


# ---- skills embutidas ------------------------------------------------------------------------------
def test_skills_embutidas_validas_dentro_do_limite_e_ligadas_por_padrao(ws):
    from clipator import skills

    pasta = skills.pasta_embutidas()
    ids = sorted(p.name for p in pasta.iterdir() if p.is_dir())
    assert len(ids) >= 12
    lista, erros = skills.listar(ws)
    assert not [e for e in erros if any(i in e for i in ids)]
    por_id = {s.id: s for s in lista}
    for sid in ids:
        s = por_id[sid]
        assert s.origem == "embutida" and s.manifesto.licenca == "AGPL-3.0-or-later" and s.manifesto.autor == "Clipator"
        assert s.manifesto.ativa_por_padrao and s.instrucoes and len(s.instrucoes) <= skills.LIMITE_TEXTO_IA
        assert not s.avisos, (sid, s.avisos)
    ativas = {s.id for s in skills.ativas(ws)}
    assert set(ids) <= ativas
    tipos = {t for s in por_id.values() if s.origem == "embutida" for t in s.manifesto.tipos}
    assert tipos >= {"estilo", "cenas", "titulos", "ranking", "thumbnail", "postagem", "revisao", "fluxo", "transcricao"}
    # desligar, ligar de novo e não apagar
    skills.desativar(ws, "decupagem")
    assert "decupagem" not in {s.id for s in skills.ativas(ws)} and "decupagem" in ws.config().skills_desligadas
    skills.ativar(ws, "decupagem")
    assert "decupagem" in {s.id for s in skills.ativas(ws)} and ws.config().skills == []
    with pytest.raises(skills.SkillError, match="não apagar"):
        skills.remover(ws, "decupagem")
    js = por_id["ranking-de-cortes"].para_json(skills.ativacoes(ws))
    assert js["origem"] == "embutida" and js["ativacoes"] == [{"skill": "ranking-de-cortes", "escopo": "global"}]
    # o estilo da skill de direção de arte aparece entre os estilos
    assert "da-dossie-em-cima" in ws.estilos(None)


def test_cada_tipo_de_skill_chega_no_seu_pedido(ws):
    from clipator import direcao, revisao, skills

    for tipo, sid in (("titulos", "ganchos-e-titulos"), ("ranking", "ranking-de-cortes"), ("thumbnail", "thumb-que-converte"),
                      ("postagem", "publicacao-por-plataforma"), ("revisao", "checagem-de-fatos"), ("cenas", "cenas-da-fala"),
                      ("fluxo", "decupagem")):
        txt = skills.texto_para_ia(ws, tipo)
        nome = skills.obter(ws, sid).manifesto.nome
        assert f"Skill do usuário: {nome}" in txt, tipo
    pals, dur = _fala(FALA_DA)
    p = direcao.prompt_cenas(pals, dur, "T", extra=skills.texto_para_ia(ws, "cenas"))
    assert "Cenas que seguem a fala" in p and len(p) < 20000
    p = revisao.prompt_revisao(pals, dur, "T", "YouTube Shorts", {"nota": 50}, skills.texto_para_ia(ws, "revisao"))
    assert "Revisão antes de publicar" in p and "Checagem de fatos" in p
    # transcrição: os termos do cabeçalho do SKILL.md juntam-se ao glossário
    import shutil

    destino = skills.pasta_skills() / "meus-termos"
    shutil.copytree(skills.pasta_embutidas() / "glossario-do-canal", destino)
    md = destino / "SKILL.md"
    md.write_text(md.read_text(encoding="utf-8").replace("termos: []", "termos: [Clipator, HyperFrames]"), encoding="utf-8")
    (destino / "clipator-skill.yaml").write_text((destino / "clipator-skill.yaml").read_text(encoding="utf-8")
                                                 .replace("id: glossario-do-canal", "id: meus-termos").replace("ativa_por_padrao: true", ""), encoding="utf-8")
    assert skills.termos_de_transcricao(ws) == []  # instalada, mas não ativada
    skills.ativar(ws, "meus-termos")
    assert skills.termos_de_transcricao(ws) == ["Clipator", "HyperFrames"]
    c = ws.criar_canal("Teste", glossario=["Vanato"])
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    assert pipeline._glossario(pr, c.info()[0]) == ["Vanato", "Clipator", "HyperFrames"]


def test_revisao_antes_de_publicar_sem_ia_e_com_ia(ws):
    from clipator import revisao

    c, pr, pals = _clip_com_fala(ws, "podcast-limpo")
    r = revisao.revisar(pr, "01-x", usar_ia=False)
    assert 0 <= r["nota"] <= 100 and r["fonte"] == "regras" and {c["nome"] for c in r["criterios"]} >= {"Gancho", "Ritmo", "Plataforma"}
    assert any("Pausa" in p["texto"] for p in r["problemas"]) and any(a["trecho"] == "2019" for a in r["alertas"])
    assert revisao.ultima(pr, "01-x")["nota"] == r["nota"]
    ia = IAFalsa({"nota": 140, "criterios": [{"nome": "Gancho", "nota": 20, "max": 25, "comentario": "bom"}],
                  "problemas": [{"segundo": 999, "texto": "fora do clip", "gravidade": "alta"}, {"segundo": 2, "texto": "", "gravidade": "x"}],
                  "alertas": [{"segundo": 1.0, "trecho": "30 milhões", "motivo": "fonte?"}]})
    r = revisao.revisar(pr, "01-x", ad=ia)
    assert r["nota"] == 100 and r["fonte"] == "falsa" and r["problemas"] == [{"segundo": None, "texto": "fora do clip", "gravidade": "alta"}]
    assert "Revisão antes de publicar" in ia.prompts[0] and "Medições do motor" in ia.prompts[0]
    assert revisao.validar("x", 10) is None


def test_galeria_usa_as_amostras_prontas_sem_renderizar(ws, monkeypatch):
    from clipator import amostras, render

    monkeypatch.setattr(render, "renderizar_clip", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia renderizar")))
    indice = amostras.indice_prontas()
    embutidos = set(ws.estilos(None))
    assert embutidos <= set(indice), embutidos - set(indice)  # todo estilo que vem com o Clipator tem a amostra pronta
    for nome, info in indice.items():
        p = amostras.pasta_prontas() / info["arquivo"]
        assert p.is_file() and (amostras.pasta_prontas() / info["capa"]).is_file() and p.stat().st_size < 900_000  # folhas se mexendo pesam mais
        assert info["hash"] == amostras.chave(ws, nome, None), f"amostra de {nome} desatualizada: rode gerar_amostras"
        assert amostras.gerar(ws, nome) == p  # sem render
    assert amostras.achar(ws, "podcast-limpo", None, {"legenda": {"cor": "#FF0000"}}) is None  # ajustado: outro hash
    total = sum(f.stat().st_size for f in amostras.pasta_prontas().iterdir())
    assert total < 22_000_000  # 58 estilos com amostra pronta


def test_previa_com_o_video_fica_em_cache_por_video_estilo_e_ajustes(ws, monkeypatch):
    from clipator import amostras, render
    from clipator.workspace import write_json

    c = ws.criar_canal("Teste")
    pr = c.criar_projeto("v", Origem(tipo="arquivo", valor="x.mp4"))
    (pr.fonte_dir).mkdir(parents=True, exist_ok=True)
    (pr.fonte_dir / "video.mp4").write_bytes(b"x")
    write_json(pr.analise_dir / "candidatos.json", [{"id": "c1", "inicio": 1.0, "fim": 20.0, "nota": 70, "texto": "x"}])
    chamadas = []

    class R:
        def __init__(self, video):
            self.video = video

    def falso(proj, clip, est, *a, **k):
        chamadas.append(est.legenda.cor)
        saida = proj.clips_dir / "amostra" / "preview.mp4"
        saida.parent.mkdir(parents=True, exist_ok=True)
        saida.write_bytes(b"mp4")
        return R(saida)

    monkeypatch.setattr(render, "renderizar_clip", falso)
    a = amostras.gerar_com_video(pr, "c1", "podcast-limpo")
    assert amostras.gerar_com_video(pr, "c1", "podcast-limpo") == a and len(chamadas) == 1  # do cache
    b = amostras.gerar_com_video(pr, "c1", "podcast-limpo", {"legenda": {"cor": "#FF0000"}})
    assert b != a and chamadas[-1] == "#FF0000" and len(chamadas) == 2
    assert amostras.gerar_com_video(pr, "c1", "impacto") not in (a, b) and len(chamadas) == 3


# ---- relato ao vivo da IA e do render --------------------------------------------------------------
_CLI_STREAM = r"""
import json, sys, time
args = sys.argv[1:]
if "--include-partial-messages" in args and "antiga" in sys.argv[0]:
    sys.stderr.write("error: unknown option '--include-partial-messages'")
    sys.exit(2)
sys.stdin.read()
if "dorme" in sys.argv[0]:
    time.sleep(30)
elif "stream-json" in args:
    for pedaco in ["Vou pôr ", "uma lista ", "na enumeração.\n", '{"cenas": []}']:
        print(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": pedaco}}}), flush=True)
        time.sleep(0.05)
    print(json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "Pensando na fala."}}}), flush=True)
    print(json.dumps({"type": "result", "structured_output": {"ok": True, "modo": "stream"}}), flush=True)
else:
    print(json.dumps({"structured_output": {"ok": True, "modo": "inteiro"}}))
"""


def _cli_falsa_stream(tmp_path, nome):
    py = tmp_path / f"{nome}.py"
    py.write_text(_CLI_STREAM, encoding="utf-8")
    if sys.platform == "win32":
        cmd = tmp_path / f"{nome}.cmd"
        cmd.write_text(f'@"{sys.executable}" "{py}" %*\r\n', encoding="utf-8")
        return str(cmd)
    sh = tmp_path / nome
    sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{py}" "$@"\n', encoding="utf-8")
    sh.chmod(0o755)
    return str(sh)


def test_claude_em_streaming_manda_o_texto_aos_poucos(tmp_path):
    from clipator.ai.adapter import ClaudeCLI, chamar

    eventos = []
    ad = ClaudeCLI(binario=_cli_falsa_stream(tmp_path, "claude-stream"), timeout=30)
    r = chamar(ad, "pedido", {"type": "object"}, None, None, lambda tipo, txt: eventos.append((tipo, txt)))
    assert r == {"ok": True, "modo": "stream"}
    assert "".join(x for t, x in eventos if t == "texto").startswith("Vou pôr uma lista na enumeração.")
    assert ("pensando", "Pensando na fala.") in eventos
    assert ad.run_json("pedido", {"type": "object"}) == {"ok": True, "modo": "inteiro"}  # sem relato: o jeito de antes
    # CLI antiga sem a opção de streaming: avisa e espera a resposta inteira
    eventos.clear()
    antiga = ClaudeCLI(binario=_cli_falsa_stream(tmp_path, "claude-antiga"), timeout=30)
    assert chamar(antiga, "pedido", {"type": "object"}, None, None, lambda tipo, txt: eventos.append((tipo, txt))) == {"ok": True, "modo": "inteiro"}
    assert eventos and eventos[0][0] == "aviso" and "não manda o texto aos poucos" in eventos[0][1]


def test_cancelar_mata_a_ia_no_meio(tmp_path):
    from clipator.ai.adapter import ClaudeCLI
    from clipator.media import Cancelado

    ad = ClaudeCLI(binario=_cli_falsa_stream(tmp_path, "claude-dorme"), timeout=60)
    cancelar = threading.Event()
    threading.Timer(0.6, cancelar.set).start()
    t0 = time.monotonic()
    with pytest.raises(Cancelado):
        ad.run_json("pedido", {"type": "object"}, cancelar, lambda *a: None)
    assert time.monotonic() - t0 < 10


def test_relato_junta_o_texto_em_linhas_e_mostra_o_tempo():
    from clipator import relato as rel_mod
    from clipator.relato import Relato

    linhas, mensagens = [], []
    rel = Relato(linhas.append, mensagens.append)
    rel.passo("pedido pronto")
    with rel.ia("claude", "planejando as cenas") as ev:
        for p in ["Vou ", "abrir com ", "o número.\nDepois ", "a lista"]:
            ev("texto", p)
        ev("pensando", "A fala cita três itens.")
        ev("aviso", "resposta do cache")
        time.sleep(1.3)
    assert linhas[0] == "• pedido pronto" and linhas[1] == "• Claude: planejando as cenas"
    assert "✎ Vou abrir com o número." in linhas and "✎ Depois a lista" in linhas
    assert "💭 A fala cita três itens." in linhas and "• resposta do cache" in linhas
    assert linhas[-1].startswith("• Claude respondeu em")
    assert any(m.startswith("Claude planejando as cenas… ") and "caracteres" in m for m in mensagens)
    assert rel_mod.INTERVALO_LOG >= 5


def test_previa_de_estilo_e_ia_nao_seguram_a_fila_do_render(tmp_path):
    from clipator.jobs import FilaJobs

    fila = FilaJobs(tmp_path / "jobs.sqlite3")
    solta = threading.Event()
    rodou = []
    fila.registrar("renderizar", lambda p, ctx: (solta.wait(10), rodou.append("render")))
    fila.registrar("amostra_video", lambda p, ctx: rodou.append("amostra"))
    fila.registrar("revisao", lambda p, ctx: rodou.append("revisao"))
    fila.enviar("renderizar", {})
    a = fila.enviar("amostra_video", {})
    b = fila.enviar("revisao", {})
    for _ in range(50):
        if fila.obter(a)["status"] == "ok" and fila.obter(b)["status"] == "ok":
            break
        time.sleep(0.1)
    assert fila.obter(a)["status"] == "ok" and fila.obter(b)["status"] == "ok" and "render" not in rodou
    solta.set()
    fila.fechar()


def test_recorte_que_trava_vira_erro_claro_e_nao_prende(tmp_path, monkeypatch):
    from clipator import recorte

    lento = tmp_path / "lento.py"
    lento.write_text("import sys, time\nsys.stdout.buffer.write(bytes(4*4*3)); sys.stdout.flush(); time.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr(recorte, "SEM_QUADRO_S", 1.0)

    class Falso:
        nome = "falso"

        def mascara(self, rgb, t):
            import numpy as np

            return np.ones(rgb.shape[:2], np.float32)

        def fechar(self):
            pass

    t0 = time.monotonic()
    with pytest.raises(recorte.RecorteTravou, match="parou de mandar quadros"):
        recorte.gerar_mascara([sys.executable, str(lento)], 4, 4, 10, 5.0, tmp_path / "m.mkv", Falso())
    assert time.monotonic() - t0 < 15 and not (tmp_path / "m.mkv").exists()


def test_melhorar_relata_os_passos(ws):
    from clipator import melhorar
    from clipator.relato import Relato

    c, pr, pals = _clip_com_fala(ws)
    linhas = []
    melhorar.melhorar(pr, "01-x", "mais dinâmico", ad=IAFalsa(_plano()), relato=Relato(linhas.append))
    txt = "\n".join(linhas)
    assert "pedido pronto: estilo Animação em cima" in txt and "falsa: refazendo a edição" in txt
    assert "conferindo com a fala:" in txt and "descartado:" in txt and "respondeu em" in txt


# ---- desenho animado: análise -> roteiro -> composição ----------------------------------------------
def _resposta_desenho(prompt):
    if prompt.startswith("Analise este corte"):
        return {"tema": "Empresa que quebrou", "ideias": [
            {"ancora": "a empresa faturou 30 milhões", "tipo": "dado", "resumo": "faturamento alto", "dado": "30 milhões"},
            {"ancora": "caiu para 5 milhões", "tipo": "dado", "resumo": "queda", "dado": "5 milhões"}]}
    if prompt.startswith("Escreva o roteiro"):
        return {"cenas": [
            {"ancora": "Em 2019 a empresa faturou", "ate": "", "etiqueta": "o faturamento", "descricao": "Um prédio com moedas subindo",
             "dado": "30 milhões", "balao": ""},
            {"ancora": "Em 2023 caiu para 5 milhões", "ate": "", "etiqueta": "a queda", "descricao": "Gráfico caindo", "dado": "5 milhões",
             "balao": ""},
            {"ancora": "frase que ninguém falou no vídeo", "ate": "", "etiqueta": "x", "descricao": "x", "dado": "", "balao": ""},
            {"ancora": "Primeiro, corte os gastos.", "ate": "invista no Brasil.", "etiqueta": "três passos", "descricao": "Lista",
             "dado": "", "balao": "Corta tudo!"}]}
    vazio = {"peca": "", "rotulo": "", "escala": 1, "entra": 0, "acao": "pop", "cor": "texto", "grafico": "nenhum", "valor": "",
             "valores": [], "rotulos": [], "quantos": 0}
    return {"cenas": [
        {"indice": 0, "camadas": [{**vazio, "tipo": "peca", "peca": "predio", "rotulo": "<script>x</script>", "x": 400, "y": 500},
                                  {**vazio, "tipo": "peca", "peca": "dragao", "x": 1, "y": 1},  # peça que não existe: cai fora
                                  {**vazio, "tipo": "dado", "grafico": "numero", "valor": "30 milhões", "x": 9999, "y": -5, "entra": 99}]},
        {"indice": 1, "camadas": [{**vazio, "tipo": "dado", "grafico": "barras", "valores": [30, 5], "rotulos": ["2019", "2023"],
                                   "valor": "-83%", "x": 500, "y": 500, "cor": "ruim"}]}]}


def test_desenho_faz_as_tres_etapas_e_prende_tudo_na_fala(ws):
    from clipator import desenho, direcao
    from clipator.relato import Relato

    c, pr, pals = _clip_com_fala(ws, "desenho-em-cima")
    clip, pasta = pr.clip("01-x")
    from clipator.timeline import Timeline
    from clipator import edicao

    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    est = ws.carregar_estilo("desenho-em-cima", c)[0]
    assert est.direcao.modo == "desenho" and est.requer_ia
    ia = IAFalsa(_resposta_desenho)
    linhas = []
    doc = desenho.gerar(pr, clip, tl, edicao.palavras_do_clip(pr, tl), est, ia, Relato(linhas.append))
    assert len(ia.prompts) == 3 and doc["analise"]["tema"] == "Empresa que quebrou"
    rot = doc["roteiro"]
    assert [r["etiqueta"] for r in rot] == ["O FATURAMENTO", "A QUEDA", "TRÊS PASSOS"]  # a cena sem âncora na fala caiu
    assert rot[0]["inicio"] == 0.0 and all(a["fim"] <= b["inicio"] + 1e-6 for a, b in zip(rot, rot[1:]))
    c0 = doc["camadas"][0]
    assert [x["tipo"] for x in c0] == ["peca", "dado"] and c0[1]["x"] == 1000 and c0[1]["y"] == 0
    assert c0[1]["entra"] <= rot[0]["fim"] - rot[0]["inicio"]
    assert doc["camadas"][2], "cena sem composição ganha a padrão"
    assert (pasta / "direcao-arte.json").exists() and desenho.ler(pasta)["ficha"] == "quadro"
    txt = "\n".join(linhas)
    assert "etapa 1 de 3" in txt and "etapa 2 de 3" in txt and "etapa 3 de 3" in txt and "composição padrão" in txt
    # vira itens "cena desenho" e o HTML escapa o texto da IA
    itens = desenho.para_itens(doc)
    assert all(i["params"]["cena"] == "desenho" for i in itens)
    lista = [{"inicio": i["inicio"], "fim": i["fim"], "params": direcao.normalizar_cena(i["params"])} for i in itens]
    f = direcao.ficha("quadro")
    assert f.fundo == "#1B0C0E"
    h = direcao.compor_camada(lista, f, 1080, 1920, tl.duracao, "em-cima", 0.5, clip.titulo)
    assert "<script>" not in h and "&lt;script&gt;" in h and 'href="#peca-predio"' in h and 'id="peca-predio"' in h
    assert "--bom: #3DDC84" in h and "palco-fixo" in h and "O FATURAMENTO" in h
    # roteiro editado: só a composição roda de novo
    ia2 = IAFalsa(_resposta_desenho)
    ed = [dict(r) for r in rot]
    ed[1]["descricao"] = "Uma balança pendendo para o lado ruim"
    doc2 = desenho.gerar(pr, clip, tl, edicao.palavras_do_clip(pr, tl), est, ia2, roteiro_editado=ed, analise_pronta=doc["analise"])
    assert len(ia2.prompts) == 1 and "balança pendendo" in ia2.prompts[0] and doc2["roteiro"][1]["descricao"].startswith("Uma balança")


def _resposta_cenas(prompt):
    """A IA falsa dos estilos de cenas: análise, roteiro e, por último, os cartões."""
    if prompt.startswith("Analise este corte"):
        return {"tema": "Empresa que quebrou", "ideias": [
            {"ancora": "Em 2019 a empresa faturou", "tipo": "dado", "resumo": "Faturamento alto", "dado": "30 milhões"}]}
    if prompt.startswith("Escreva o roteiro"):
        return {"cenas": [
            {"ancora": "Em 2019 a empresa faturou", "ate": "", "etiqueta": "o auge", "descricao": "O faturamento em destaque",
             "dado": "30 milhões", "balao": ""},
            {"ancora": "Em 2023 caiu para 5 milhões", "ate": "", "etiqueta": "a queda", "descricao": "A queda do faturamento",
             "dado": "5 milhões", "balao": ""},
            {"ancora": "Primeiro, corte os gastos.", "ate": "invista no Brasil.", "etiqueta": "três passos", "descricao": "Os passos",
             "dado": "", "balao": ""}]}
    vazio = {"texto": "", "itens": [], "valor": "", "rotulo": "", "autor": "", "a": "", "b": "", "duracao": 3, "motivo": "ilustra"}
    return {"cenas": [
        {**vazio, "cena": "numero", "ancora": "Em 2019 a empresa faturou", "valor": "30 milhões", "rotulo": "em 2019"},
        {**vazio, "cena": "numero", "ancora": "Em 2023 caiu para 5 milhões", "valor": "5 milhões", "rotulo": "em 2023"},
        {**vazio, "cena": "numero", "ancora": "Primeiro, corte os gastos.", "valor": "999", "rotulo": "nunca foi dito"}]}


def test_estilos_de_cenas_fazem_a_pre_producao_antes_das_cenas(ws):
    from clipator import desenho, direcao, edicao, melhorar
    from clipator.relato import Relato
    from clipator.timeline import Timeline

    c, pr, pals = _clip_com_fala(ws, "da-animacao-em-cima")
    clip, pasta = pr.clip("01-x")
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    est = ws.carregar_estilo("da-animacao-em-cima", c)[0]
    assert est.direcao.modo == "cenas"
    ia, linhas = IAFalsa(_resposta_cenas), []
    (pasta / desenho.ARQUIVO).write_text('{"cores": {"destaque": "#00FF00"}}', encoding="utf-8")
    doc = desenho.gerar(pr, clip, tl, edicao.palavras_do_clip(pr, tl), est, ia, Relato(linhas.append))
    assert len(ia.prompts) == 3 and "uma animação" in ia.prompts[0] and "desenho" not in ia.prompts[1]
    assert "Empresa que quebrou" in ia.prompts[2] and "O faturamento em destaque" in ia.prompts[2]  # as cenas seguem a direção
    assert doc["modo"] == "cenas" and doc["cores"] == {"destaque": "#00FF00"} and "etapa 3 de 3" in "\n".join(linhas)
    rot = doc["roteiro"]
    assert [x["params"]["valor"] for x in doc["cenas"]] == ["30 milhões", "5 milhões"]  # o número que não foi dito caiu
    assert [(x["inicio"], x["fim"]) for x in doc["cenas"]] == [(r["inicio"], r["fim"]) for r in rot[:2]]  # os tempos do roteiro
    itens = desenho.para_itens(doc)
    assert all(i["params"]["cena"] == "numero" and i["origem"] == "ia" for i in itens)
    assert desenho.do_modo(desenho.ler(pasta), "cenas") and not desenho.do_modo(desenho.ler(pasta), "desenho")
    assert "Siga a direção" not in direcao.prompt_cenas([], 10, "T")  # sem pré-produção, o pedido é o de sempre
    # refazer com o roteiro editado: só a última etapa, e os tempos editados valem
    ed = [dict(r) for r in rot]
    ed[1]["descricao"] = "Uma seta despencando"
    ed[1]["fim"] = ed[1]["fim"] - 0.5
    ia2 = IAFalsa(_resposta_cenas)
    r = desenho.refazer(pr, "01-x", ed, ad=ia2)
    assert len(ia2.prompts) == 1 and "seta despencando" in ia2.prompts[0] and r["modo"] == "cenas" and r["cenas"] == 2
    cenas = [i for i in edicao.carregar(pasta).itens if i.tipo == "cena"]
    assert cenas[1].fim == pytest.approx(ed[1]["fim"]) and edicao.carregar(pasta).cenas_planejadas
    assert "Cenas recompostas com o roteiro editado" in melhorar.ler(pasta, r["versao"])["resumo"]
    assert desenho.resumo_do_clip(pr, "01-x")["roteiro"][1]["descricao"] == "Uma seta despencando"
    ia3 = IAFalsa(_resposta_cenas)
    desenho.refazer(pr, "01-x", tudo=True, ad=ia3)
    assert len(ia3.prompts) == 3
    # a IA não montou nada: as cenas saem e o próximo render usa as regras
    r = desenho.refazer(pr, "01-x", tudo=True, ad=IAFalsa({"tema": "", "ideias": [], "cenas": []}))
    assert r["cenas"] == 0 and not edicao.carregar(pasta).cenas_planejadas
    assert not [i for i in edicao.carregar(pasta).itens if i.tipo == "cena"]


def test_melhorar_mantem_o_desenho_do_estilo(ws):
    from clipator import desenho, edicao, melhorar

    c, pr, pals = _clip_com_fala(ws, "desenho-em-cima")
    clip, pasta = pr.clip("01-x")
    doc = edicao.carregar(pasta)
    des = edicao.Item(id="d1", tipo="cena", inicio=0, fim=3, origem="ia",
                      params={"cena": "desenho", "etiqueta": "X", "camadas": []})
    edicao.salvar(pasta, doc.model_copy(update={"itens": doc.itens + [des]}))
    r = melhorar.melhorar(pr, "01-x", "mais cenas", ad=IAFalsa(_plano()))
    itens = edicao.carregar(pasta).itens
    assert any(i.id == "d1" for i in itens)
    assert not any(i.tipo == "cena" and i.params.get("cena") != "desenho" for i in itens)
    assert any("desenho animado" in d["motivo"] for d in r["descartados"])
    assert desenho.PECAS


def test_refazer_com_a_direcao_editada_cria_versao_nova(ws):
    from clipator import desenho, edicao, melhorar

    c, pr, pals = _clip_com_fala(ws, "desenho-em-cima")
    desenho.refazer(pr, "01-x", ad=IAFalsa(_resposta_desenho))  # a primeira vez: as três etapas
    _, pasta = pr.clip("01-x")
    doc = desenho.ler(pasta)
    ed = [dict(r) for r in doc["roteiro"]]
    ed[0]["descricao"] = "Um saco de dinheiro enorme"
    ia = IAFalsa(_resposta_desenho)
    r = desenho.refazer(pr, "01-x", ed, {"destaque": "#00ff00", "texto": "vermelho"}, ad=ia)
    assert len(ia.prompts) == 1 and "saco de dinheiro" in ia.prompts[0]
    assert r["modo"] == "desenho" and r["versao"] == max(melhorar.numeros(pasta))
    novo = desenho.ler(pasta)
    assert novo["cores"] == {"destaque": "#00FF00"} and novo["roteiro"][0]["descricao"] == "Um saco de dinheiro enorme"
    cenas = [i for i in edicao.carregar(pasta).itens if i.tipo == "cena"]
    assert len(cenas) == len(novo["roteiro"]) and all(i.params["cena"] == "desenho" for i in cenas)
    res = desenho.resumo_do_clip(pr, "01-x")
    assert res["modo"] == "desenho" and res["cores"]["destaque"] == "#00FF00" and "predio" in res["pecas"]
    assert "Desenho recomposto com o roteiro editado" in melhorar.ler(pasta, r["versao"])["resumo"]
    # "refazer tudo": as três etapas de novo
    ia3 = IAFalsa(_resposta_desenho)
    desenho.refazer(pr, "01-x", tudo=True, ad=ia3)
    assert len(ia3.prompts) == 3


def test_enquadramento_pelo_rosto_centraliza_o_locutor_fora_do_centro():
    from clipator import reframe, render

    # locutor no canto de cima à esquerda de um 16:9, crop parado no centro: o rosto cai fora do crop
    amostras = [(t / 2, [reframe.Rosto(cx=0.2, cy=0.25, area=0.02)]) for t in range(10)]
    cw, ch = reframe.tamanho_crop(1920, 1080, 1080, 1920)
    no_centro = reframe.rosto_no_quadro(amostras, None, 1920, 1080, cw, ch, (1920 - cw) // 2)
    assert no_centro[0] == 0.0  # fora (preso na borda)
    x0 = int(0.2 * 1920 - cw / 2)
    cx, cy, fh = reframe.rosto_no_quadro(amostras, None, 1920, 1080, cw, max(ch, 1), max(0, x0))
    assert abs(cx - 0.5) < 0.3 and 0.2 < cy < 0.3 and fh > 0.1
    # em cima: a metade de baixo tem o rosto com ~30% da altura e o centro a ~40% dela
    hb = 1920 - 960
    sw, sh, x, y = render.enquadrar_rosto((0.5, 0.6, 0.08), 1080, 1920, 1080, hb, *render.ROSTO_EM_CIMA)
    assert sw > 1080 and sh > 1920  # zoom (rosto pequeno)
    assert abs((0.6 * sh - y) / hb - 0.40) < 0.02 and 0 <= x <= sw - 1080
    # rosto grande demais: sem zoom; sem rosto: o recorte de antes
    assert render.enquadrar_rosto((0.5, 0.3, 0.6), 1080, 1920, 1080, hb, *render.ROSTO_EM_CIMA)[:2] == (1080, 1920)
    assert render.enquadrar_rosto(None, 1080, 1920, 1080, hb, *render.ROSTO_EM_CIMA)[:2] == (1080, 1920)
    da = render.DirecaoArte(layout="em-cima", proporcao=0.5)
    g = ";".join(render.cadeia_mistura("em-cima", da, "#FFFFFF", 1080, 1920, 1, None, "nenhum", rosto=(0.5, 0.6, 0.08)))
    assert f"scale={sw}:{sh}" in g and f"crop=1080:{hb}:{x}:{y}" in g


def test_maquete_low_poly_usa_as_pecas_facetadas_e_o_hud(ws, monkeypatch):
    from clipator import desenho, direcao, edicao, maquete, maquete3d
    from clipator.timeline import Timeline

    monkeypatch.setattr(maquete3d, "caminho_three", lambda: None)  # sem o three.js: as peças facetadas em SVG

    assert set(maquete.PECAS_MAQUETE) == set(desenho.PECAS)  # mesmos nomes: o roteiro da IA vale nas duas bibliotecas
    assert all('class="f1' in v for v in maquete.PECAS_MAQUETE.values())
    c, pr, pals = _clip_com_fala(ws, "maquete-low-poly")
    clip, _ = pr.clip("01-x")
    est = ws.carregar_estilo("maquete-low-poly", c)[0]
    assert est.requer_ia and est.direcao.modo == "desenho" and est.direcao.ficha == "maquete"
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    ia = IAFalsa(_resposta_desenho)
    doc = desenho.gerar(pr, clip, tl, edicao.palavras_do_clip(pr, tl), est, ia)
    assert doc["ficha"] == "maquete" and "maquete explicativa" in ia.prompts[1] and "maquete explicativa" in ia.prompts[2]
    itens = desenho.para_itens(doc)
    assert itens[0]["params"]["cabecalho"] == "EMPRESA QUE QUEBROU"
    lista = [{"inicio": i["inicio"], "fim": i["fim"], "params": direcao.normalizar_cena(i["params"])} for i in itens]
    f = direcao.ficha("maquete")
    h = direcao.compor_camada(lista, f, 1080, 1920, tl.duracao, "em-cima", 0.55, clip.titulo)
    assert "ficha-maquete" in h and "--lp-claro: #F1F3F7" in h and 'viewBox="12 10 76 76"' in h
    assert "PASSO A PASSO · EMPRESA QUE QUEBROU" in h and 'class="cartao-rot"' in h and 'class="painel-dado"' in h
    assert "<script" not in h
    # as outras fichas do desenho continuam no traço
    h2 = direcao.compor_camada(lista, direcao.ficha("quadro"), 1080, 1920, tl.duracao, "em-cima", 0.5, clip.titulo)
    assert "--lp-claro" not in h2 and 'viewBox="0 0 100 100"' in h2



def test_maquete_3d_poe_o_canvas_e_os_dados_das_cenas(tmp_path, monkeypatch):
    from clipator import direcao, maquete3d

    falso = tmp_path / "three.min.js"
    falso.write_text("window.THREE = {};", encoding="utf-8")
    monkeypatch.setenv("CLIPATOR_THREE", str(falso))
    assert maquete3d.disponivel()
    cenas = [{"inicio": 0, "fim": 3, "params": direcao.normalizar_cena({"cena": "desenho", "etiqueta": "A", "camadas": [
        {"tipo": "peca", "peca": "predio", "rotulo": "</script><b>", "x": 400, "y": 500, "escala": 1.5, "entra": 0.2, "acao": "cai",
         "cor": "destaque"}]})}]
    h = direcao.compor_camada(cenas, direcao.ficha("maquete"), 1080, 1920, 3.0, "em-cima", 0.55, "t")
    assert '<canvas id="maquete3d">' in h and "window.THREE = {};" in h and "window.__timelines" in h
    assert '"peca": "predio"' in h and "</script><b>" not in h  # o rótulo vai escapado no SVG e fora dos dados do script
    assert "--t3: 0; } to { --t3: 3.000; }" in h and 'data-k="0" data-x="400" data-y="500"' in h
    # outras fichas não levam o 3D
    assert "maquete3d" not in direcao.compor_camada(cenas, direcao.ficha("quadro"), 1080, 1920, 3.0, "em-cima", 0.5, "t")


def test_curta_tem_roteiro_fechado_pela_ia_com_skill_estilo_e_fala(ws, monkeypatch):
    from clipator import desenho, edicao
    from clipator.relato import Relato
    from clipator.timeline import Timeline

    monkeypatch.setenv("CLIPATOR_PESQUISA", "0")
    c, pr, pals = _clip_com_fala(ws, "arte-encaixe-vivo")
    clip, pasta = pr.clip("01-x")
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    est = ws.carregar_estilo("arte-encaixe-vivo", c)[0]

    def resp(prompt):
        if "Escreva o roteiro fechado" not in prompt:
            return {"tema": "Empresa que quebrou", "ideias": []}
        return {"assunto": "a empresa quebrou", "metafora": "uma loja que esvazia", "logline": "a loja cheia esvazia e o dono reage",
                "elenco": [{"id": "p1", "papel": "dono", "tipo": "pessoa", "nome": "João Silva"}],
                "planos": [{"ancora": "Em 2019 a empresa faturou", "ate": "", "descricao": "loja cheia", "cenario": "loja", "momento": "",
                            "clima": "", "elenco": [{"id": "p1", "acao": "comemorar"}], "situacao": "dinheiro", "plano": "geral",
                            "movimento": "fixo", "transicao": "corte", "objetos": [{"forma": "bloco", "rotulo": "30 milhões"}], "placa": ""},
                           {"ancora": "O João Silva disse que", "ate": "", "descricao": "o dono triste", "cenario": "loja", "momento": "",
                            "clima": "", "elenco": [{"id": "p1", "acao": "triste"}], "situacao": "tristeza", "plano": "close",
                            "movimento": "aproximar", "transicao": "corte", "objetos": [], "placa": "absurdo"}]}

    ia = IAFalsa(resp)
    linhas = []
    doc = desenho.gerar(pr, clip, tl, edicao.palavras_do_clip(pr, tl), est, ia, Relato(linhas.append))
    assert len(ia.prompts) == 2  # análise e roteiro do curta: a etapa cena a cena não roda
    p = ia.prompts[1]
    assert "peças plásticas" in p and "## Cenários" in p and "Escolha a metáfora" in p and "Como a empresa quebrou" in p
    assert doc["curta"]["metafora"] == "uma loja que esvazia" and len(doc["cenas"]) == 2
    a, b = (x["params"]["curta"] for x in doc["cenas"])
    assert a["roteiro"] and a["personagens"][0]["nome"] == "" and b["personagens"][0]["nome"] == "João Silva" and b["placa"] == "absurdo"
    assert (pasta / "direcao-arte.json").exists() and "metáfora: uma loja que esvazia" in "\n".join(linhas)
