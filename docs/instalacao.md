# Instalação

Um comando instala tudo, só para o seu usuário. Não há Docker nem Python do sistema envolvido.

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/JBragon/clipator/main/install.ps1 | iex
```

```bash
# macOS e Linux
curl -fsSL https://raw.githubusercontent.com/JBragon/clipator/main/install.sh | bash
```

Se o GitHub estiver bloqueado na sua rede, baixe o repositório de outro jeito (um .zip, um pendrive) e rode o script de dentro da pasta. Ele instala o motor dessa cópia:

```powershell
.\install.ps1          # Windows
```

```bash
./install.sh           # macOS e Linux
```

## O que o script faz

1. Confere o sistema, a GPU e o espaço livre (uns 3 GB entre modelos e o Chrome do HyperFrames).
2. Instala o [uv](https://docs.astral.sh/uv/), que traz um Python 3.12 isolado.
3. Instala o que faltar entre FFmpeg (com libass, para as legendas), Deno (o yt-dlp precisa dele para o YouTube) e Node.js 22+ (para o HyperFrames):
   - Windows: winget (`Gyan.FFmpeg`, `DenoLand.Deno`, `OpenJS.NodeJS.LTS`), ou o Chocolatey se não houver winget.
   - Mac: Homebrew (`ffmpeg-full`, `deno`, `node`). O Homebrew precisa estar instalado antes.
   - Linux: o FFmpeg pelo apt, dnf, pacman ou zypper, que pede a senha. O Deno vai para `~/.clipator/deno` e o Node.js para `~/.clipator/node`, sem sudo.
4. Instala o comando `clipator` com `uv tool install`.
5. Instala o HyperFrames em `~/.clipator/hyperframes`.
6. Cria o workspace em `~/Clipator`, com um canal de exemplo.
7. Roda `clipator preparar`, que baixa o modelo de transcrição certo para o seu hardware, o modelo de rosto e o Chrome do HyperFrames. Depois disso, o Clipator funciona offline.
8. Se você não tiver o Claude Code nem o Codex, oferece instalar o Claude Code (ou o Codex). Depois registra o servidor MCP nos dois com `clipator mcp registrar`.
9. Baixa e instala o app de desktop da última release do GitHub, se houver uma. Se essa versão já estiver instalada, pula o download. No Mac, o app vai para `/Applications` (ou `~/Applications`, sem permissão); no Linux, para `~/.local/bin/clipator-app`, com uma entrada no menu de aplicativos.
10. Roda `clipator doctor`.

Rodar o script de novo atualiza o motor e conserta o que estiver faltando.

## Opções

| Bash | PowerShell | O que faz |
| --- | --- | --- |
| `--sim` | `-Sim` | Não pergunta nada. Também não instala o Claude Code nem o Codex, só registra o MCP nos que já existem |
| `--sem-app` | `-SemApp` | Não baixa o app de desktop |
| `--reinstalar-app` | `-ReinstalarApp` | Baixa e instala o app de novo, mesmo que a versão seja a mesma |
| `--sem-hyperframes` | `-SemHyperFrames` | Não instala o Node.js nem o HyperFrames. Os estilos animados saem com a legenda simples |
| `--sem-modelos` | `-SemModelos` | Não baixa os modelos agora. Eles vêm no primeiro uso |
| `--sem-ia` | `-SemIA` | Não mexe no Claude Code nem no Codex |

Pelo `irm | iex` não dá para passar opções. Use as variáveis equivalentes antes do comando: `$env:CLIPATOR_SIM = "1"`, `CLIPATOR_SEM_APP`, `CLIPATOR_SEM_HYPERFRAMES`, `CLIPATOR_SEM_MODELOS` e `CLIPATOR_SEM_IA`. A variável `CLIPATOR_FONTE` troca a origem do motor, por exemplo para uma branch, e `CLIPATOR_WORKSPACE` troca a pasta do workspace.

## Comandos de manutenção

```bash
clipator doctor                 # confere tudo e diz o que falta
clipator preparar               # baixa de novo os modelos e o Chrome do HyperFrames
clipator mcp registrar          # registra o MCP no Claude Code e no Codex
clipator mcp remover            # tira o registro
clipator desinstalar            # tira o MCP, o HyperFrames e o Node.js do Clipator (--modelos apaga os modelos)
uv tool uninstall clipator      # tira o próprio comando
```

O `desinstalar` nunca apaga o workspace nem as skills em `~/.clipator/skills`. O modelo de transcrição fica no cache do Hugging Face (`~/.cache/huggingface`), que outros programas podem usar também.

## Windows: "a execução de scripts foi desabilitada"

A política padrão do Windows bloqueia arquivos `.ps1`. O `irm | iex` funciona assim mesmo, e o instalador chama o `npm.cmd` para não esbarrar nisso. Para rodar o `.\install.ps1` de uma cópia local, use `powershell -ExecutionPolicy Bypass -File .\install.ps1`. No dia a dia, `npm.cmd` no lugar de `npm` resolve, ou libere uma vez só para o seu usuário com `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## GPU

Com uma NVIDIA e o CUDA 12 com cuDNN 9 instalados, a transcrição usa a GPU e o modelo `large-v3-turbo`. Sem isso, ela roda na CPU com o `small`. Um vídeo de 1 hora leva uns 15 minutos na CPU. Se a GPU falhar, o Clipator volta para a CPU sozinho.

## Publicar o app

A release do app sai pelo workflow `release`: crie uma tag `v*` (por exemplo `git tag v0.1.0 && git push --tags`). Ele gera o `.exe` do Windows, o `.dmg` do Mac (Intel e Apple Silicon) e o `.AppImage` do Linux, e publica tudo numa release do GitHub. O instalador baixa dali.

Os pacotes ainda não são assinados. No Windows, o SmartScreen pode pedir "Executar assim mesmo". No Mac, o app instalado pelo script abre normalmente, mas um `.dmg` baixado pelo navegador precisa de clique direito e Abrir na primeira vez.
