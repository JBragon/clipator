# Clipator (app de desktop)

App de desktop do [Clipator](https://github.com/JBragon/clipator), em Electron + React + Monaco. Ele abre o motor sozinho (`clipator serve`, só em 127.0.0.1, com um token por sessão) e fecha junto com ele.

O que tem na tela:

- Explorador do workspace e editor dos `.md` do canal (`canal.md`, `regras.md`, `titulos.md`, `thumb.md`, estilos).
- Projeto em passos: importar o vídeo, escolher os candidatos, ajustar o corte na linha do tempo, escolher o estilo e a direção de arte, thumbnails, postagem e revisão antes de publicar.
- Galeria de estilos com amostras, glossário do canal, biblioteca de stickers, skills e fila de jobs.
- Conversa e terminal com o Claude Code ou o Codex do usuário, na pasta do projeto, sem flags que pulem as permissões (`src/main/chat.ts`, `src/main/terminal.ts`).
- Interface em português e em inglês (`src/renderer/src/i18n.ts`).

## Instalar

Os instaladores (`.exe`, `.dmg` e `.AppImage`) ficam na página de [Releases](https://github.com/JBragon/clipator/releases), e o [instalador de um comando](https://github.com/JBragon/clipator#instalar) já baixa o app junto com o motor.

## Rodar a partir do código

Requisitos: Node.js 22+, o [uv](https://docs.astral.sh/uv/) e os requisitos do motor (FFmpeg, Deno).

```bash
npm install
npm run dev          # abre o app e sobe o motor da pasta ../motor via uv
```

Para usar outro motor, defina `CLIPATOR_MOTOR`, por exemplo `CLIPATOR_MOTOR="clipator"` para o comando instalado. `CLIPATOR_CLAUDE` e `CLIPATOR_CODEX` apontam para os executáveis da IA quando eles não estão no PATH.

No PowerShell do Windows, se aparecer "a execução de scripts foi desabilitada", use `npm.cmd` no lugar de `npm`. Numa rede que bloqueia o GitHub, defina antes `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`.

| Script | O que faz |
| --- | --- |
| `npm run dev` | App em modo de desenvolvimento |
| `npm run typecheck` | Confere os tipos (o CI roda) |
| `npm run build` | Build do Electron (o CI roda) |
| `npm test` | Testes de unidade do renderer (`node --test`) |
| `npm run web` | Só a interface no navegador, via Vite |
| `npm run dist` | Build e pacote local com o electron-builder |

A release oficial sai pelo workflow `release` quando uma tag `v*` é enviada; veja [docs/instalacao.md](../docs/instalacao.md#publicar-o-app).

Licença: AGPL-3.0-or-later.
