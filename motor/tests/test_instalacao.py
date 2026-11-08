"""Registro do MCP no Codex e no Claude Code, e comandos do instalador. Sem internet."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from clipator import instalacao
from clipator.cli import main

CONFIG_EXISTENTE = """model = "gpt-5"

[mcp_servers.outro]
command = "outro"

[mcp_servers.clipator]
command = "/velho/clipator"
args = ["mcp"]

[mcp_servers.clipator.env]
X = "1"

[profiles.rapido]
model = "mini"
"""


@pytest.fixture
def codex_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    return tmp_path / "codex"


def test_sem_secao_codex_preserva_o_resto():
    out = instalacao._sem_secao_codex(CONFIG_EXISTENTE)
    assert "clipator" not in out
    assert 'X = "1"' not in out
    assert "[mcp_servers.outro]" in out and "[profiles.rapido]" in out and 'model = "gpt-5"' in out


def test_registrar_codex_cria_e_substitui(codex_home):
    cfg = instalacao.registrar_codex("/novo/clipator")
    assert cfg == codex_home / "config.toml"
    assert cfg.read_text(encoding="utf-8") == '[mcp_servers.clipator]\ncommand = "/novo/clipator"\nargs = ["mcp"]\n'

    cfg.write_text(CONFIG_EXISTENTE, encoding="utf-8")
    instalacao.registrar_codex("C:\\Users\\Ana\\clipator.exe", workspace=str(codex_home))
    texto = cfg.read_text(encoding="utf-8")
    assert texto.count("[mcp_servers.clipator]") == 1
    assert "/velho/clipator" not in texto and "[mcp_servers.clipator.env]" not in texto
    assert 'command = "C:\\\\Users\\\\Ana\\\\clipator.exe"' in texto
    assert '"-w"' in texto and texto.rstrip().endswith('"mcp"]')
    assert "[profiles.rapido]" in texto

    if sys.version_info >= (3, 11):
        import tomllib

        dados = tomllib.loads(texto)
        assert dados["mcp_servers"]["clipator"]["command"] == "C:\\Users\\Ana\\clipator.exe"
        assert dados["mcp_servers"]["clipator"]["args"][-1] == "mcp"
        assert dados["profiles"]["rapido"]["model"] == "mini"


def test_remover_codex(codex_home):
    assert instalacao.remover_codex() is False
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(CONFIG_EXISTENTE, encoding="utf-8")
    assert instalacao.remover_codex() is True
    assert "clipator" not in (codex_home / "config.toml").read_text(encoding="utf-8")
    assert instalacao.remover_codex() is False


@pytest.mark.skipif(os.name == "nt", reason="claude falso em shell script")
def test_registrar_claude_chama_o_cli(tmp_path, monkeypatch):
    log = tmp_path / "chamadas.txt"
    falso = tmp_path / "claude"
    falso.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n', encoding="utf-8")
    falso.chmod(falso.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CLIPATOR_CLAUDE", str(falso))

    assert instalacao.registrar_claude("/bin/clipator") is True
    linhas = log.read_text().splitlines()
    assert linhas[0] == "mcp remove -s user clipator"
    assert linhas[1] == "mcp add -s user clipator -- /bin/clipator mcp"
    assert instalacao.remover_claude() is True


def test_registrar_mcp_sem_claude_nem_codex(tmp_path, monkeypatch, codex_home):
    monkeypatch.setenv("CLIPATOR_CLAUDE", "nao-existe-claude")
    monkeypatch.setenv("CLIPATOR_CODEX", "nao-existe-codex")
    msgs: list[str] = []
    assert instalacao.registrar_mcp(msgs.append) == []
    assert any("Claude Code não encontrado" in m for m in msgs)
    assert any("Codex não encontrado" in m for m in msgs)
    assert not codex_home.exists()


def test_cli_mcp_registrar_e_remover(tmp_path, monkeypatch, codex_home):
    monkeypatch.setenv("CLIPATOR_CLAUDE", "nao-existe-claude")
    codex_home.mkdir()  # Codex "instalado": a pasta existe
    assert main(["mcp", "registrar"]) == 0
    assert "[mcp_servers.clipator]" in (codex_home / "config.toml").read_text(encoding="utf-8")
    assert main(["mcp", "remover"]) == 0
    assert "clipator" not in (codex_home / "config.toml").read_text(encoding="utf-8")


def test_desinstalar_preserva_workspace_e_skills(tmp_path, monkeypatch, codex_home):
    monkeypatch.setenv("CLIPATOR_CLAUDE", "nao-existe-claude")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    base = tmp_path / ".clipator"
    for sub in ("hyperframes/node_modules", "node/bin", "modelos", "skills/minha"):
        (base / sub).mkdir(parents=True)
    ws = tmp_path / "Clipator"
    ws.mkdir()

    assert main(["desinstalar", "--sim"]) == 0
    assert not (base / "hyperframes").exists() and not (base / "node").exists()
    assert (base / "modelos").exists() and (base / "skills" / "minha").exists() and ws.exists()

    assert main(["uninstall", "-s", "--modelos"]) == 0
    assert not (base / "modelos").exists() and (base / "skills" / "minha").exists()


def test_preparar_sem_nada(monkeypatch):
    msgs: list[str] = []
    monkeypatch.setenv("CLIPATOR_HYPERFRAMES", "")
    monkeypatch.setattr("clipator.hyperframes.comando", lambda: None)
    assert instalacao.preparar(msgs.append, whisper=False, rosto=False, stickers=False) == []
    assert any("HyperFrames não instalado" in m for m in msgs)


def test_node_do_instalador(tmp_path, monkeypatch):
    from clipator import hyperframes

    monkeypatch.setenv("CLIPATOR_NODE_DIR", str(tmp_path))
    monkeypatch.setattr(hyperframes.shutil, "which", lambda nome: None)
    assert hyperframes.node_bin() is None
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "node").write_text("")
    assert hyperframes.node_bin() == str(tmp_path / "bin" / "node")
    assert hyperframes._env()["PATH"].startswith(str(tmp_path / "bin"))


def test_saida_utf8_em_console_cp1252(monkeypatch):
    import io

    from clipator import cli

    buf = io.BytesIO()
    falso = io.TextIOWrapper(buf, encoding="cp1252")
    monkeypatch.setattr(cli.sys, "stdout", falso)
    cli._saida_utf8()
    print("✔ não encontrado", file=cli.sys.stdout)
    falso.flush()
    assert buf.getvalue().decode("utf-8").startswith("✔ não")
