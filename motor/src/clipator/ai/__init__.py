"""IA opcional: Claude Code (claude -p) e Codex (codex exec), usando o login do usuário.

A IA só recebe texto e devolve JSON validado por schema. Nenhum vídeo ou áudio
sai da máquina.
"""

from .adapter import AdapterIA, ClaudeCLI, CodexCLI, ErroIA, adaptador, detectar_agentes

__all__ = ["AdapterIA", "ClaudeCLI", "CodexCLI", "ErroIA", "adaptador", "detectar_agentes"]
