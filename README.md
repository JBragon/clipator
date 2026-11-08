# Clipator

App local, open-source e gratuito que transforma um vídeo longo (link ou upload) em clips curtos e cortes, para quem tem canal de cortes. Download, transcrição, análise, corte e renderização rodam na sua máquina. A IA (Claude Code ou Codex, com o seu login) é opcional e só recebe texto.

> Estado: versão 0.1, em construção. O motor (download, transcrição, candidatos, legendas, estilos, direção de arte, thumbnail, render, CLI, API e MCP), o app de desktop e o instalador de um comando já funcionam.

## O que ele faz

- Baixa do YouTube e da Twitch (yt-dlp) ou importa um arquivo de vídeo.
- Transcreve com o faster-whisper, com tempo por palavra e glossário do canal para os nomes próprios.
- Acha os melhores trechos sozinho: janelas que começam e terminam em frase completa, com nota de 0 a 100 e o motivo.
- Corta em 9:16, 1:1, 4:5 ou 16:9, segue o rosto e queima a legenda animada fora da zona que o app da plataforma cobre.
- Traz dezenas de estilos prontos, de legenda simples a estilos animados e direções de arte com cenas desenhadas por cima do vídeo ([docs/artes.md](docs/artes.md)).
- Gera thumbnails 1280x720, títulos e o pacote de postagem para Shorts, Reels e TikTok, conferido contra os limites de cada um.
- Funciona sem IA e offline depois do download do vídeo. Tudo vira arquivo num workspace que dá para versionar com git.

## Instalar

Um comando instala o motor, as dependências, os modelos e o app de desktop:

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/JBragon/clipator/main/install.ps1 | iex
```

```bash
# macOS e Linux
curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
```

O script instala o uv, o FFmpeg, o Deno, o Node.js, o motor, o HyperFrames e os modelos de transcrição e de rosto, cria o workspace em `~/Clipator`, registra o MCP no Claude Code e no Codex e baixa o app de desktop da última [release](https://github.com/JBragon/clipator/releases), quando houver uma. Rodar de novo atualiza tudo. De dentro de uma cópia do repositório, `./install.sh` ou `.\install.ps1` instalam o motor dessa cópia, o que serve para redes que bloqueiam o GitHub. Opções (`--sem-app`, `--sem-ia`, `--sem-modelos` e outras), manutenção e desinstalação estão em [docs/instalacao.md](docs/instalacao.md).

Quem só quer o app pode baixar o instalador na página de [Releases](https://github.com/JBragon/clipator/releases): `.exe` para Windows, `.dmg` para Mac (Intel e Apple Silicon) e `.AppImage` para Linux. O app precisa do motor, então o caminho recomendado continua sendo o script acima. Os pacotes ainda não são assinados: no Windows, o SmartScreen pode pedir "Executar assim mesmo"; no Mac, abra o `.dmg` baixado pelo navegador com clique direito e Abrir na primeira vez.

## Como funciona

1. Você cola um link do YouTube ou da Twitch, ou escolhe um arquivo de vídeo.
2. O Clipator baixa com o yt-dlp (se o YouTube pedir login, tenta sozinho com a conta do YouTube conectada num perfil do Chrome ou do Edge só do Clipator, depois com os cookies de um navegador ou de um cookies.txt das Configurações), transcreve com o faster-whisper (timestamp por palavra) e mede a energia da voz, os picos de reação e os cortes de cena. O glossário do canal (`glossario` no `canal.md`) ajuda o Whisper com os nomes próprios e corrige os que saírem errados.
3. Heurísticas locais montam janelas que começam e terminam em frase completa e dão uma nota de 0 a 100, com o motivo.
4. Se a IA estiver ligada, só o texto dos melhores candidatos vai para o Claude ou o Codex, que reordena e sugere títulos.
5. Você escolhe os cortes, o formato (9:16, 1:1, 4:5 ou 16:9) e o estilo.
6. O FFmpeg corta, segue o rosto, queima a legenda animada e a cartela de título fora da zona que o app da plataforma cobre (Shorts, Reels, TikTok), soma os efeitos sonoros do estilo (sintetizados no próprio computador) e entrega o MP4 com `legenda.srt`/`.vtt` e o pacote de postagem por plataforma em `postagem/`, conferido contra os limites de cada uma.

Tudo vira arquivo num workspace que dá para versionar com git: `canal.md`, `regras.md`, `titulos.md`, `thumb.md`, estilos em `.md`, transcrições e candidatos em JSON.

## IA (opcional)

O Clipator não usa API paga nem conta própria. Ele chama o Claude Code (`claude`) ou o Codex (`codex`) que já estão instalados e logados no seu computador, com a sua assinatura. A escolha fica em Configurações, e o instalador oferece instalar o Claude Code se você não tiver nenhum dos dois (`--sem-ia` pula essa parte).

- **Dentro do motor**, a IA só recebe texto (transcrição, títulos, regras do canal) e devolve JSON conferido por schema, sempre pelo mesmo adaptador ([motor/src/clipator/ai/adapter.py](motor/src/clipator/ai/adapter.py)). Ela reordena os candidatos, sugere títulos, frases de thumbnail e descrições, planeja as cenas da direção de arte e faz a revisão antes de publicar. Sem IA, cada etapa tem um caminho local.
- **No app**, o painel de conversa e o terminal abrem o Claude Code ou o Codex na pasta do projeto, sem flags que pulem as permissões. Você aprova cada comando.
- **Pelo MCP**, o Claude Code e o Codex controlam o Clipator inteiro. Depois do instalador, é só pedir: "clipa esse link no canal do podcast, estilo impacto, 5 cortes". Para registrar de novo, use `clipator mcp registrar`.

O Clipator vem com 13 skills embutidas (títulos, ranking, thumbnail, postagem, revisão, checagem de fatos, direção de arte, roteiro do curta e outras), ligadas por padrão: veja [docs/skills-embutidas.md](docs/skills-embutidas.md). Dá para instalar as suas ([docs/skills.md](docs/skills.md)):

```bash
clipator skill instalar https://github.com/autor/repo/tree/main/minha-skill   # ou uma pasta, ou um .zip
clipator skill ativar minha-skill --canal meu-podcast
clipator skill listar
```

## Placa de vídeo

Tudo funciona só na CPU. A placa de vídeo, quando existe, acelera o render, a detecção de cenas e, na NVIDIA, a transcrição:

| | NVIDIA | AMD | Intel | Mac |
| --- | --- | --- | --- | --- |
| Render (H.264) | NVENC | AMF (Windows, driver Adrenalin) | Quick Sync | VideoToolbox |
| Transcrição | CUDA 12 + cuDNN 9, modelo `large-v3-turbo` | CPU | CPU | CPU |

O encoder é escolhido sozinho e testado uma vez por sessão; se ele falhar no meio de um render, o clip é refeito no x264. Na CPU, a transcrição usa o modelo `small` e um vídeo de 1 hora leva uns 15 minutos. O suporte a AMF e Quick Sync ainda não foi testado em placa real; relatos de quem tem AMD ou Intel são bem-vindos. Detalhes e variáveis (`CLIPATOR_ENCODER`, `CLIPATOR_HWACCEL`) em [motor/README.md](motor/README.md#placa-de-vídeo). O `clipator doctor` mostra o que está em uso.

## Usar pela linha de comando

Depois do instalador, o comando `clipator` fica disponível.

```bash
clipator doctor                    # confere o que falta

clipator canal criar "Meu Podcast" --palavras-chave dinheiro investimento
clipator processar meu-podcast "https://www.youtube.com/watch?v=..."   # ou um arquivo .mp4
clipator candidatos meu-podcast <projeto>
clipator selecionar meu-podcast <projeto> c01 c03 --estilo impacto --cartela
clipator renderizar meu-podcast <projeto>
clipator estilos                   # lista os estilos
```

Os clips ficam em `~/Clipator/canais/<canal>/projetos/<projeto>/clips/`.

Thumbnail (1280x720, 4 layouts com a cor e a fonte do `thumb.md` do canal):

```bash
clipator thumb meu-podcast <projeto> <clip>              # por código, frase-gancho pela IA ou pelo título
clipator thumb meu-podcast <projeto> <clip> --por-imagem # variações com o $imagegen do Codex (ChatGPT Plus)
```

Direção de arte do canal (paleta, fontes, movimento, prancha e aprovação): `clipator arte --help` e [docs/direcao-de-arte.md](docs/direcao-de-arte.md).

Para instalar o motor à mão: Python 3.11+, FFmpeg com libass e, para o YouTube, o Deno (o yt-dlp precisa dele). Para os estilos animados, o Node.js 22+ e o HyperFrames ([docs/hyperframes.md](docs/hyperframes.md)); sem eles, esses estilos saem com a legenda simples.

```bash
uv tool install "clipator[visao] @ git+https://github.com/JBragon/clipator#subdirectory=motor"
clipator preparar                  # baixa os modelos para usar offline
```

## Rodar o app a partir do código

Requisitos: os mesmos do motor, mais o Node.js 22+ e o [uv](https://docs.astral.sh/uv/).

```bash
cd app
npm install
npm run dev        # abre o app e sobe o motor da pasta motor/ via uv
```

Com o `make` instalado, `make run` na raiz do repositório faz o mesmo: instala as dependências quando elas mudam e abre o app. No Windows, instale com `winget install ezwinports.make` e abra um terminal novo.

No PowerShell do Windows, se aparecer "a execução de scripts foi desabilitada", use `npm.cmd install` e `npm.cmd run dev`, ou libere uma vez com `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Numa rede que bloqueia o GitHub, defina antes `$env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"`, porque o Electron baixa o próprio binário de lá. Mais em [app/README.md](app/README.md).

## Estrutura do repositório

| Pasta | O que tem |
| --- | --- |
| `motor/` | Motor Python: CLI, API local (FastAPI), servidor MCP, pipeline de mídia, estilos, direções de arte e skills embutidas |
| `app/` | App de desktop (Electron + React + Monaco): explorador do workspace, editor de `.md`, player com linha do tempo, candidatos, estilos, thumbnails, postagem, jobs e conversa com a IA |
| `docs/` | Requisitos, arquitetura, instalação, estilos, skills e o mapa de código reaproveitável dos concorrentes |
| `SKILLS/` | Skills de referência de terceiros (design), que o app pode ler como pasta extra |
| `.claude/skills/` | Skills do Claude Code para quem desenvolve o Clipator (não fazem parte do produto) |
| `install.ps1`, `install.sh` | Instalador de um comando |

## Como contribuir

Issues e pull requests são bem-vindos, em português ou em inglês.

1. Leia [docs/requisitos-arquitetura.md](docs/requisitos-arquitetura.md) (decisões fechadas) e [docs/referencias-concorrentes.md](docs/referencias-concorrentes.md) antes de mexer num módulo. Se um projeto aberto já resolve o problema, adapte com atribuição no topo do arquivo e em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (a cópia em `motor/` tem que ficar igual).
2. Prepare o ambiente: `cd motor && uv venv && uv pip install -e ".[dev,visao]"` para o motor, e `cd app && npm install` para o app.
3. Antes de abrir o PR, rode `cd motor && pytest -q` e, se mexeu no app, `npm run typecheck` e `npm run build` em `app/`. Os testes não podem depender de internet. O CI roda os testes do motor em Windows, Mac e Linux, e o typecheck e o build do app no Linux.

As regras que valem para todo código:

- Tudo o que o usuário vê fica em português (mensagens, chaves de YAML, nomes de arquivo do workspace, CLI e ferramentas MCP).
- A IA só recebe texto e devolve JSON por schema, sempre pelo adaptador em `motor/src/clipator/ai/adapter.py`. Nada de API paga, conta ou nuvem no núcleo.
- O motor tem que funcionar sem IA e offline depois do download do vídeo.

Quem usa Claude Code ou Codex no repositório: as instruções para agentes estão em [AGENTS.md](AGENTS.md) e as skills de desenvolvimento em [.claude/skills/](.claude/skills/README.md).

## Licença

[AGPL-3.0-or-later](LICENSE). Código adaptado de outros projetos e fontes incluídas estão listados em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Use o Clipator só com vídeos que você tem direito de recortar.
