# clipator (motor)

Motor local do [Clipator](https://github.com/JBragon/clipator): CLI, API HTTP local, servidor MCP e o pipeline de mídia (yt-dlp, faster-whisper, FFmpeg, MediaPipe, legendas ASS).

```bash
uv tool install "clipator[visao]"
clipator doctor
clipator --help
```

## Placa de vídeo

Tudo funciona só na CPU. A placa de vídeo, quando existe, acelera duas coisas:

| Etapa | NVIDIA | AMD | Intel | Mac |
| --- | --- | --- | --- | --- |
| Render (encoder H.264) | NVENC | AMF (driver Adrenalin) | Quick Sync | VideoToolbox |
| Detecção de cenas (decodificação) | `-hwaccel auto` (CUDA/D3D11VA) | D3D11VA no Windows, VAAPI no Linux | D3D11VA/VAAPI | VideoToolbox |
| Transcrição (faster-whisper) | CUDA 12 + cuDNN 9 | CPU | CPU | CPU |

O encoder é testado uma vez por sessão com os parâmetros do render; se ele falhar no meio de um render, o clip é refeito no x264 e a placa sai da lista até o motor reiniciar. O `clipator doctor` mostra qual encoder está em uso.

| Variável | Efeito |
| --- | --- |
| `CLIPATOR_ENCODER` | `auto` (padrão), `nvenc`, `amf`, `qsv`, `videotoolbox` ou `x264` |
| `CLIPATOR_HWACCEL` | `0` desliga a decodificação pela placa |
| `CLIPATOR_WHISPER_THREADS` | Threads do Whisper na CPU (padrão: cerca dos núcleos físicos, de 4 a 16) |

## Desenvolvimento

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,visao]"
pytest
```

Os testes não baixam nada da internet: a transcrição usa um Whisper falso e o FFmpeg gera os vídeos de teste.

| Módulo | Função |
| --- | --- |
| `workspace.py`, `models.py`, `markdown.py` | Pastas do workspace e schemas dos `.md`/`.yaml` |
| `ingest.py` | Download por link (yt-dlp) e importação de arquivo |
| `transcribe.py` | faster-whisper com timestamp por palavra e correção de texto |
| `signals.py` | Energia do áudio, picos de reação e cortes de cena |
| `candidates.py` | Janelas de frase completa e nota local de 0 a 100 |
| `ai/` | Adaptador Claude/Codex por CLI, ranking, títulos, cache |
| `titles.py` | Títulos por fórmula, trava do título e censor leetspeak |
| `subtitles.py`, `reframe.py`, `render.py` | Legenda ASS, rosto e render FFmpeg |
| `jobs.py`, `service.py`, `api.py`, `mcp_server.py`, `cli.py` | Fila de jobs, API, MCP e CLI |
| `dados/estilos/` | Os 16 estilos do MVP e o corte longo |

Licença: AGPL-3.0-or-later.
