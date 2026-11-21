<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/marca/clipator-horizontal-escuro.svg">
    <img alt="Clipator" src="docs/marca/clipator-horizontal-claro.svg" height="96">
  </picture>
</p>

App local, open-source e gratuito que transforma um vídeo longo (link ou upload) em clips curtos e cortes, para quem tem canal de cortes. Download, transcrição, análise, corte e renderização rodam na sua máquina. A IA (Claude Code ou Codex, com o seu login) é opcional e só recebe texto.

> Estado: versão 0.1, em construção. O motor (download, transcrição, candidatos, legendas, estilos, direção de arte, thumbnail, render, CLI, API e MCP), o app de desktop e o instalador de um comando já funcionam.

## O que ele faz

- Baixa do YouTube e da Twitch (yt-dlp) ou importa um arquivo de vídeo.
- Transcreve com o faster-whisper, com tempo por palavra e glossário do canal para os nomes próprios.
- Acha os melhores trechos sozinho: janelas que começam e terminam em frase completa, com nota de 0 a 100 e o motivo.
- Corta em 9:16, 1:1, 4:5 ou 16:9, segue o rosto e queima a legenda animada fora da zona que o app da plataforma cobre.
- Traz dezenas de estilos prontos, de legenda simples a estilos animados e direções de arte com cenas desenhadas por cima do vídeo ([docs/artes.md](docs/artes.md)).
- Gera thumbnails 1280x720, títulos e o pacote de postagem para Shorts, Reels e TikTok, conferido contra os limites de cada um.
- Modo remoto: com o PC ligado, você acompanha, aprova cortes e baixa os clips pelo celular, em casa ou na rua, pelo Tailscale e sem abrir portas no roteador ([docs/modo-remoto.md](docs/modo-remoto.md)).
- Funciona sem IA e offline depois do download do vídeo. Tudo vira arquivo num workspace que dá para versionar com git.

## Instalar

Um comando instala tudo: o motor, as dependências, os modelos e o app de desktop (a janela do Clipator). Não precisa saber programar, é só seguir os passos do seu sistema.

Antes de começar, confira se você tem uns 5 GB livres e uma internet razoável: o instalador baixa uns 3 GB e pode levar vários minutos.

### Windows 10 ou 11

1. Abra o menu Iniciar, digite `PowerShell` e abra o **Windows PowerShell**. Não precisa ser como administrador.
2. Copie a linha abaixo, cole no PowerShell (clique com o botão direito) e aperte Enter:

   ```powershell
   irm https://raw.githubusercontent.com/JBragon/clipator/main/install.ps1 | iex
   ```

3. Espere até aparecer **Pronto**. Se o instalador perguntar alguma coisa, responda com Enter para aceitar.
4. Abra o app pelo menu Iniciar (procure **Clipator**) ou pelo atalho na área de trabalho.

O FFmpeg, o Deno e o Node.js vêm pelo winget, que já vem no Windows 10 e 11 (é o "Instalador de Aplicativo" da Microsoft Store). Se o comando `clipator` não for encontrado depois, feche o PowerShell e abra outro.

### Mac

1. Instale o [Homebrew](https://brew.sh), se ainda não tiver: abra o site, copie o comando que aparece lá e rode no Terminal.
2. Abra o **Terminal** (procure "Terminal" no Spotlight, com Cmd+Espaço).
3. Copie a linha abaixo, cole no Terminal e aperte Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
   ```

4. Espere até aparecer **Pronto**.
5. Abra o app pelo Launchpad ou pelo Spotlight (procure **Clipator**). Ele fica na pasta Aplicativos.

### Linux

1. Abra o terminal.
2. Copie a linha abaixo, cole no terminal e aperte Enter:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
   ```

3. Digite a sua senha quando o instalador pedir. Ele usa o `sudo` só para instalar o FFmpeg.
4. Espere até aparecer **Pronto**.
5. Abra o app pelo menu de aplicativos (procure **Clipator**) ou rode `clipator-app` no terminal.

O app do Linux é um AppImage. No Ubuntu 22.04 ou mais novo, se ele não abrir, instale o FUSE com `sudo apt install libfuse2`.

### Se algo der errado

- **O app não foi instalado.** O fim da instalação avisa em amarelo. Baixe o instalador do app na página de [Releases](https://github.com/JBragon/clipator/releases) (`.exe` no Windows, `.dmg` no Mac, `.AppImage` no Linux) e abra. O motor já fica pronto, então não precisa rodar o comando de novo.
- **Alerta de segurança ao abrir o app baixado pelo navegador.** Os pacotes ainda não são assinados. No Windows, o SmartScreen mostra "O Windows protegeu o computador": clique em **Mais informações** e depois em **Executar assim mesmo**. No Mac, clique com o botão direito no app, escolha **Abrir** e confirme. Isso só acontece na primeira vez. Pelo comando de instalação, esses alertas normalmente não aparecem.
- **Algo parece faltando.** Rode `clipator doctor` no terminal. Ele diz o que falta e como resolver.
- **O comando `clipator` não é encontrado.** Feche o terminal e abra outro.

### Atualizar e outras opções

O app de desktop confere sozinho, toda vez que abre, se saiu uma versão nova no GitHub. Se saiu, ele pergunta "Atualizar agora" ou "Depois". Atualizar fecha o app e roda este mesmo instalador, na versão nova, numa janela do terminal: ele atualiza o app e o motor e abre o Clipator de novo no fim. Sem internet, o app abre normalmente e não pergunta nada. `CLIPATOR_SEM_ATUALIZACAO=1` desliga a checagem.

Para atualizar ou consertar a instalação, rode o mesmo comando de novo. A cada execução, ele confere cada peça (uv e Python, FFmpeg, Deno, Node.js, motor, HyperFrames, workspace, modelos, IA e app), instala só o que falta e mostra no fim uma lista "Verificação" com o estado de cada uma. O app só é baixado de novo quando sai uma versão nova (`--reinstalar-app` força o download). Tudo o que os comandos escrevem vai para `~/.clipator/instalacao.log`; `CLIPATOR_SIMPLES=1` mostra essa saída na tela, como antes.

Em detalhes, o script instala o uv, o FFmpeg, o Deno, o Node.js, o motor, o HyperFrames e os modelos de transcrição e de rosto, cria o workspace em `~/Clipator`, registra o MCP no Claude Code e no Codex e baixa o app de desktop da última [release](https://github.com/JBragon/clipator/releases). De dentro de uma cópia do repositório, `./install.sh` ou `.\install.ps1` instalam o motor dessa cópia, o que serve para redes que bloqueiam o GitHub. Opções (`--sem-app`, `--sem-ia`, `--sem-modelos` e outras), manutenção e desinstalação estão em [docs/instalacao.md](docs/instalacao.md).

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
