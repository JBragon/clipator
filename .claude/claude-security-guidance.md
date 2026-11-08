# Regras de segurança do Clipator

O Clipator é um app desktop local: Electron + TypeScript em `app/`, motor Python em `motor/` (FastAPI e websockets em localhost, FFmpeg, yt-dlp, faster-whisper, HyperFrames) e um servidor MCP local. Quem chega de fora são links de vídeo, arquivos de mídia, ZIPs de skills, YAML de estilos e canais, e respostas de IA.

## Electron (`app/src/main`, `app/src/preload`)
- A janela mantém `contextIsolation: true`, `sandbox: true` e `nodeIntegration: false`. Qualquer mudança nisso é uma falha.
- O preload expõe só funções nomeadas pelo `contextBridge`, nunca `ipcRenderer` inteiro.
- Todo `ipcMain.handle` valida tipo e formato dos argumentos. Caminhos vindos do renderer (`shell:abrir`, `shell:mostrar`, `workspace:definir`, `dialogo:salvar`) precisam ser resolvidos e ficar dentro do workspace ou ter vindo de um diálogo do sistema.
- `shell.openExternal` só aceita `https://`. `shell.openPath` nunca abre executáveis ou scripts.
- Nada de `innerHTML` ou `dangerouslySetInnerHTML` com texto de transcrição, título de vídeo ou resposta de IA.

## Motor (`motor/src/clipator`)
- Processos externos (FFmpeg, yt-dlp, deno, claude, codex, hyperframes) rodam com lista de argumentos, nunca `shell=True` nem string montada. Um link ou nome de arquivo começando com `-` não pode virar opção.
- A API e o websocket escutam só em `127.0.0.1`, exigem o token que o app passa ao iniciar o motor e não abrem o CORS além das origens já listadas em `api.py`. Rota nova sem checar o token é uma falha.
- Tudo o que o motor grava, lê ou apaga fica dentro do workspace: resolva o caminho e confira o prefixo antes (path traversal com `..`, links simbólicos, caminhos absolutos).
- ZIPs de skills são extraídos sem sair da pasta de destino (zip slip) e com limite de tamanho.
- YAML só com `yaml.safe_load`. Nada de `pickle`, `eval` ou `exec` sobre dados do usuário ou da IA.
- A resposta da IA é dado não confiável: passa pelo schema do adaptador em `ai/adapter.py` antes de ser usada, e nunca vira comando, caminho fora do workspace ou código.
- Tokens e chaves de IA nunca vão para logs, mensagens de erro, arquivos do workspace ou URLs.

## MCP local (`mcp_server.py`)
- Ferramentas que apagam exigem `confirmar=true`. Ferramentas não aceitam caminhos fora do workspace.

## GitHub Actions (`.github/workflows`)
- `permissions` mínimas por job, actions de terceiros fixadas por SHA, nada de `pull_request_target` com checkout do código do PR, e nenhuma expressão `${{ github.event.* }}` direto dentro de `run:`.
