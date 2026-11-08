# clipator (motor)

Motor local do [Clipator](https://github.com/JBragon/clipator): CLI, API HTTP local, servidor MCP e o pipeline de mídia (yt-dlp, faster-whisper, FFmpeg, MediaPipe, legendas ASS, HyperFrames). Funciona sem IA e offline depois do download do vídeo.

O jeito mais fácil de instalar é o [instalador de um comando](https://github.com/JBragon/clipator#instalar), que também traz o FFmpeg, o Deno, o HyperFrames e os modelos. Para instalar só o motor:

```bash
uv tool install "clipator[visao] @ git+https://github.com/JBragon/clipator#subdirectory=motor"
clipator preparar      # baixa os modelos de transcrição e de rosto e o Chrome do HyperFrames
clipator doctor        # confere o que falta
clipator --help
```

Precisa de Python 3.11+, FFmpeg com libass e, para o YouTube, do Deno. O extra `visao` (MediaPipe e OpenCV) liga o enquadramento que segue o rosto.

## Comandos

| Comando | O que faz |
| --- | --- |
| `clipator init`, `clipator canal` | Cria o workspace e os canais |
| `clipator processar CANAL LINK_OU_ARQUIVO` | Baixa ou importa, transcreve, mede os sinais e acha e ranqueia os candidatos |
| `clipator candidatos`, `selecionar`, `renderizar` | Lista os candidatos, transforma em clips e renderiza |
| `clipator thumb` | Gera as thumbnails de um clip |
| `clipator estilos` | Lista os estilos |
| `clipator arte` | Direção de arte do canal (predefinidos, criar, validar, prancha, aprovar) |
| `clipator skill` | Skills do usuário: listar, instalar, ativar, exportar |
| `clipator serve` | API HTTP para o app, só em 127.0.0.1 e com token |
| `clipator mcp` | Servidor MCP por stdio; `mcp registrar` e `mcp remover` no Claude Code e no Codex |
| `clipator preparar`, `doctor`, `desinstalar` | Manutenção |

## IA

A IA é opcional e só recebe texto. Toda chamada passa por [`ai/adapter.py`](src/clipator/ai/adapter.py), que roda o `claude -p` ou o `codex exec` já logados no computador (sem API paga nem chave) e pede a resposta num JSON Schema (`--json-schema` no Claude, `--output-schema` no Codex). Um pedido igual a um anterior sai do cache, sem chamar a IA. Se a CLI não existir, estiver sem login ou falhar, a etapa segue pelo caminho local (nota por heurística, título por fórmula, revisão por regras).

## Placa de vídeo

Tudo funciona só na CPU. A placa de vídeo, quando existe, acelera três coisas:

| Etapa | NVIDIA | AMD | Intel | Mac |
| --- | --- | --- | --- | --- |
| Render (encoder H.264) | NVENC | AMF (Windows, driver Adrenalin) | Quick Sync | VideoToolbox |
| Detecção de cenas (decodificação) | `-hwaccel auto` (CUDA/D3D11VA) | D3D11VA no Windows, VAAPI no Linux | D3D11VA/VAAPI | VideoToolbox |
| Transcrição (faster-whisper) | CUDA 12 + cuDNN 9 | CPU | CPU | CPU |

Os encoders tentados são NVENC, AMF e Quick Sync no Windows, NVENC e Quick Sync no Linux e VideoToolbox no Mac. O encoder é testado uma vez por sessão com os parâmetros do render; se ele falhar no meio de um render, o clip é refeito no x264 e a placa sai da lista até o motor reiniciar. O `clipator doctor` mostra qual encoder está em uso. Com CUDA, a transcrição usa o modelo `large-v3-turbo`; na CPU, o `small`.

AMF e Quick Sync só foram testados de forma simulada (`tests/test_gpu.py`). Se você tem uma placa AMD ou Intel, um relato do `clipator doctor` e de um render ajuda muito.

| Variável | Efeito |
| --- | --- |
| `CLIPATOR_ENCODER` | `auto` (padrão), `nvenc`, `amf`, `qsv`, `videotoolbox` ou `x264` |
| `CLIPATOR_HWACCEL` | `0` desliga a decodificação pela placa |
| `CLIPATOR_WHISPER_THREADS` | Threads do Whisper na CPU (padrão: cerca dos núcleos físicos, de 4 a 16) |

## Desenvolvimento

```bash
uv venv && source .venv/bin/activate      # no Windows: .venv\Scripts\activate
uv pip install -e ".[dev,visao]"
pytest -q
```

Os testes não baixam nada da internet: a transcrição usa um Whisper falso e o FFmpeg gera os vídeos de teste. O CI roda `ruff check src --select F,E9` e `pytest -q` em Windows, Mac e Linux.

| Módulo | Função |
| --- | --- |
| `workspace.py`, `models.py`, `markdown.py` | Pastas do workspace e schemas dos `.md`/`.yaml` |
| `pipeline.py` | As etapas, cada uma gravando seu resultado em arquivo |
| `ingest.py`, `contayt.py` | Download por link (yt-dlp), conta do YouTube e importação de arquivo |
| `transcribe.py`, `glossario.py` | faster-whisper com timestamp por palavra e correção pelo glossário |
| `signals.py` | Energia do áudio, picos de reação e cortes de cena |
| `candidates.py` | Janelas de frase completa e nota local de 0 a 100 |
| `ai/` | Adaptador Claude/Codex por CLI, ranking, cache |
| `titles.py` | Títulos por fórmula, trava do título e censor leetspeak |
| `subtitles.py`, `reframe.py`, `render.py`, `media.py` | Legenda ASS, rosto, render FFmpeg e escolha do encoder |
| `hyperframes.py` | Estilos animados em HTML/CSS renderizados pelo HyperFrames |
| `direcao.py`, `artes/`, `arte/` | Cenas por cima da fala, as direções de arte e a direção de arte do canal (`arte/direcao.yaml`) |
| `thumbs.py`, `postagem.py`, `revisao.py` | Thumbnail, pacote de postagem por plataforma e revisão antes de publicar |
| `sons.py` | Efeitos sonoros sintetizados com numpy |
| `skills.py` | Skills embutidas e do usuário |
| `jobs.py`, `service.py`, `api.py`, `mcp_server.py`, `cli.py` | Fila de jobs, API, MCP e CLI |
| `doctor.py`, `instalacao.py` | `clipator doctor`, `preparar` e `desinstalar` |
| `dados/estilos/` | Os estilos embutidos, um `.md` por estilo |
| `dados/skills/` | As 13 skills embutidas |
| `ferramentas/` | Scripts de quem desenvolve (gerar as amostras da galeria), fora do app |

Licença: AGPL-3.0-or-later.
