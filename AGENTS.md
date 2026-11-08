# Instruções para agentes (Claude Code, Codex)

- Leia `docs/requisitos-arquitetura.md` (decisões fechadas) e `docs/referencias-concorrentes.md` antes de codificar um módulo. Se um concorrente já resolve o problema, copie ou adapte com atribuição no topo do arquivo e em `THIRD_PARTY_NOTICES.md` (mantenha a cópia em `motor/` igual à da raiz).
- Tudo que o usuário vê fica em português (mensagens, chaves de YAML, nomes de arquivo do workspace, CLI e ferramentas MCP). Identificadores internos podem ficar em português ou inglês, mas siga o arquivo em que está mexendo.
- A IA só recebe texto e devolve JSON por schema, sempre pelo adaptador em `motor/src/clipator/ai/adapter.py`. Nada de APIs pagas, contas ou nuvem no núcleo.
- O motor tem que funcionar sem IA e offline depois do download do vídeo.
- Rode `cd motor && pytest -q` antes de abrir PR. Os testes não podem depender de internet.
- Nunca faça commit (nem push, amend ou rebase) sem autorização explícita do mantenedor para aquele commit. Deixe as mudanças no working tree, diga quais arquivos mudaram e espere ele pedir. Um "pode commitar" vale só para o que foi mostrado, não para o resto da sessão.
