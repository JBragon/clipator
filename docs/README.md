# Documentação do Clipator

Fase atual: implementação do MVP. O motor fica em `motor/`.

| Arquivo | O que tem |
| --- | --- |
| [requisitos-arquitetura.md](requisitos-arquitetura.md) | Documento principal: visão, fluxo, stack, detecção de virais, estilos, títulos, multiagente, MCP local, instalação, integração das skills e perguntas em aberto |
| [instalacao.md](instalacao.md) | Instalador de um comando (Windows, Mac e Linux), opções, manutenção, desinstalação e como publicar o app |
| [hyperframes.md](hyperframes.md) | Motor HyperFrames dos estilos animados: como renderiza, como instalar e como escrever um template |
| [artes.md](artes.md) | As 28 direções de arte com renderizador próprio: plano, âncoras, parâmetros, mídia e como conferir |
| [direcao-de-arte.md](direcao-de-arte.md) | Direção de arte do canal (`arte/direcao.yaml`): dicionário dos tokens, predefinidos, validador, prancha, rotas, aprovação, uso nos estilos e comandos `clipator arte` |
| [skills.md](skills.md) | Formato do pacote de skill (`SKILL.md` + `clipator-skill.yaml`), tipos, escopo, importação e exportação |
| [referencias-concorrentes.md](referencias-concorrentes.md) | Mapa do código reaproveitável dos 8 concorrentes open-source, arquivo por arquivo, por módulo do Clipator, com licença e o que fazer. Leitura obrigatória antes de codificar cada módulo |
| [pesquisa-titulos-e-thumbnails.md](pesquisa-titulos-e-thumbnails.md) | Pesquisa de títulos e thumbnails de 75 canais de cortes brasileiros: método, achados, temperatura do título, padrões de thumb por tema e como isso virou a base de referência embutida (`dados/base-virais/`), aplicada a todo canal |

A versão viva do documento principal, com comentários, fica em https://claude.ai/artifact/5FHWsd3oBYnzMyki5RjahX. Este arquivo .md é uma cópia exportada em 01/11/2026.

Os vídeos de amostra, quadros e thumbnails baixados na pesquisa ficaram fora do repo de propósito (conteúdo de terceiros, 190 MB). Eles estão em `C:\workspace\clipator-pesquisa\`.
