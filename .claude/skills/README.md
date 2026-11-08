# Skills de desenvolvimento

Skills do Claude Code para quem desenvolve o Clipator. Elas não fazem parte do produto: as skills que o usuário final ativa ficam em `SKILLS/` e não se misturam com estas.

Cada pasta veio de um projeto aberto, copiada sem alterações (só o `uv.lock` do `supply-chain-risk-auditor` ficou de fora, porque o repositório ignora `uv.lock`). A licença de cada uma está no `LICENSE.txt` da pasta, e os créditos estão em [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).

| Skill | Para que serve no Clipator | Origem |
| --- | --- | --- |
| `systematic-debugging` | Achar a causa raiz antes de corrigir (render, transcrição, FFmpeg) | obra/superpowers |
| `test-driven-development` | Escrever o teste que falha antes do código, no motor e no app | obra/superpowers |
| `verification-before-completion` | Rodar testes e build antes de dizer que terminou ou de commitar | obra/superpowers |
| `receiving-code-review` | Avaliar sugestões de revisão com rigor antes de aplicar | obra/superpowers |
| `modern-python` | uv, ruff, pytest e segurança de CI no motor | trailofbits/skills |
| `property-based-testing` | Testes com Hypothesis para cortes, legendas e parsers | trailofbits/skills |
| `supply-chain-risk-auditor` | Auditar as dependências npm e PyPI | trailofbits/skills |
| `mcp-builder` | Evoluir o servidor MCP local do motor | anthropics/skills |
| `webapp-testing` | Testar a interface com Playwright | anthropics/skills |
| `clipator-artes` e `clipator-arte-*` | Autoria das 22 direções de arte (`docs/artes.md`) | escritas para o Clipator, AGPL-3.0-or-later |

As regras do projeto valem mais que as das skills. Em especial: o `uv.lock` continua fora do git (a `modern-python` sugere versioná-lo), o trabalho fica na `main` local, sem worktree nem PR, e nenhum commit é feito sem autorização do mantenedor (ver `AGENTS.md`).

Além destas pastas, `.claude/settings.json` liga plugins oficiais da Anthropic (marketplace `claude-plugins-official`, Apache 2.0): `security-guidance` (avisos ao editar e revisão de segurança do diff a cada turno), `claude-security` (varredura profunda com `/claude-security`), `pr-review-toolkit`, `mcp-server-dev`, `typescript-lsp` e `pyright-lsp`. As regras específicas do Clipator para a revisão de segurança estão em `.claude/claude-security-guidance.md`. Os dois LSPs precisam dos servidores instalados: `npm install -g typescript-language-server typescript pyright`.
