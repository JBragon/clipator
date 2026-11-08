# Clipator

App local, open-source e gratuito que transforma um vídeo longo (link ou upload) em clips curtos e cortes, para quem tem canal de cortes. Download, transcrição, análise, corte e renderização rodam na sua máquina. A IA (Claude Code ou Codex, com o seu login) é opcional e só recebe texto.

> Estado: em construção. O motor (download, transcrição, candidatos, legendas, render, CLI, API e MCP), o app de desktop e o instalador de um comando já funcionam.

## Instalar

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/JBragon/clipator/main/install.ps1 | iex
```

```bash
# macOS e Linux
curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
```

O script instala o uv, o FFmpeg, o Deno, o Node.js, o motor, o HyperFrames e os modelos, cria o workspace e registra o MCP no Claude Code e no Codex. De dentro de uma cópia do repositório, `./install.sh` ou `.\install.ps1` instalam o motor dessa cópia. Detalhes e opções em [docs/instalacao.md](docs/instalacao.md).

## Como funciona

1. Você cola um link do YouTube ou da Twitch, ou escolhe um arquivo de vídeo.
2. O Clipator baixa com o yt-dlp (se o YouTube pedir login, tenta sozinho com a conta do YouTube conectada num perfil do Chrome ou do Edge só do Clipator, depois com os cookies de um navegador ou de um cookies.txt das Configurações), transcreve com o faster-whisper (timestamp por palavra) e mede a energia da voz, os picos de reação e os cortes de cena. O glossário do canal (`glossario` no `canal.md`) ajuda o Whisper com os nomes próprios e corrige os que saírem errados.
3. Heurísticas locais montam janelas que começam e terminam em frase completa e dão uma nota de 0 a 100, com o motivo.
4. Se a IA estiver ligada, só o texto dos melhores candidatos vai para o Claude ou o Codex, que reordena e sugere títulos.
5. Você escolhe os cortes, o formato (9:16, 1:1, 4:5 ou 16:9) e o estilo.
6. O FFmpeg corta, segue o rosto, queima a legenda animada e a cartela de título fora da zona que o app da plataforma cobre (Shorts, Reels, TikTok), soma os efeitos sonoros do estilo (sintetizados no próprio computador) e entrega o MP4 com `legenda.srt`/`.vtt` e o pacote de postagem por plataforma em `postagem/`, conferido contra os limites de cada uma.

Tudo vira arquivo num workspace que dá para versionar com git: `canal.md`, `regras.md`, `titulos.md`, estilos em `.md`, transcrições e candidatos em JSON.

## Usar pela linha de comando

Depois do instalador, o comando `clipator` fica disponível. Para instalar à mão: Python 3.11+, FFmpeg e, para o YouTube, o Deno (o yt-dlp precisa dele). Para os estilos animados (texto grifado, dossiê, plantão urgente e outros), o Node.js 22+ e o HyperFrames; veja [docs/hyperframes.md](docs/hyperframes.md). Sem eles, esses estilos saem com a legenda simples.

```bash
cd motor
uv tool install ".[visao]"        # só para instalar à mão; o instalador já faz isso
clipator doctor                    # confere o que falta

clipator canal criar "Meu Podcast" --palavras-chave dinheiro investimento
clipator processar meu-podcast "https://www.youtube.com/watch?v=..."   # ou um arquivo .mp4
clipator selecionar meu-podcast <projeto> c01 c03 --estilo impacto --cartela
clipator renderizar meu-podcast <projeto>
```

Os clips ficam em `~/Clipator/canais/<canal>/projetos/<projeto>/clips/`.

Thumbnail (1280x720, 4 layouts com a cor e a fonte do `thumb.md` do canal):

```bash
clipator thumb meu-podcast <projeto> <clip>              # por código, frase-gancho pela IA ou pelo título
clipator thumb meu-podcast <projeto> <clip> --por-imagem # variações com o $imagegen do Codex (ChatGPT Plus)
```

O Clipator já vem com 12 skills embutidas (títulos, ranking, thumbnail, postagem, revisão antes de publicar, direção de arte, cenas e outras), ligadas por padrão: veja [docs/skills-embutidas.md](docs/skills-embutidas.md).

Skills próprias (veja [docs/skills.md](docs/skills.md)):

```bash
clipator skill instalar https://github.com/autor/repo/tree/main/minha-skill   # ou uma pasta, ou um .zip
clipator skill ativar minha-skill --canal meu-podcast
clipator skill listar
```

Para usar pelo Claude Code ou pelo Codex, o instalador já registra o servidor MCP. Para registrar de novo:

```bash
clipator mcp registrar
```

Depois é só pedir: "clipa esse link no canal do podcast, estilo impacto, 5 cortes".

## Rodar o app de desktop

Requisitos: os mesmos do motor, mais o Node.js 20+ e o [uv](https://docs.astral.sh/uv/).

```bash
cd app
npm install
npm run dev        # abre o app e sobe o motor da pasta motor/ via uv
```

Com o `make` instalado, `make run` na raiz do repositório faz o mesmo: instala as dependências quando elas mudam e abre o app. No Windows, instale com `winget install ezwinports.make` e abra um terminal novo.

No PowerShell do Windows, se aparecer "a execução de scripts foi desabilitada", use `npm.cmd install` e `npm.cmd run dev`, ou libere uma vez com `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Numa rede que bloqueia o GitHub, defina antes `$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"`, porque o Electron baixa o próprio binário de lá.

O app abre o motor sozinho (`clipator serve`, só em 127.0.0.1, com um token por sessão) e fecha junto com ele. Para usar outro motor, defina `CLIPATOR_MOTOR`, por exemplo `CLIPATOR_MOTOR="clipator"`.

## Estrutura do repositório

| Pasta | O que tem |
| --- | --- |
| `motor/` | Motor Python: CLI, API local (FastAPI), servidor MCP, pipeline de mídia e estilos embutidos |
| `app/` | App de desktop (Electron + React + Monaco): explorador do workspace, editor de `.md`, player com linha do tempo, candidatos e jobs |
| `docs/` | Requisitos, arquitetura e o mapa de código reaproveitável dos concorrentes |

## Licença

[AGPL-3.0](LICENSE). Código adaptado de outros projetos e fontes incluídas estão listados em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Use o Clipator só com vídeos que você tem direito de recortar.
