# Código reaproveitável dos concorrentes

Levantamento de 01/11/2026. Os 8 repositórios foram clonados e lidos; a tabela aponta, para cada módulo do Clipator, o arquivo exato que já resolve o problema e o que fazer com ele.

**Regra para quem codifica (pessoa ou agente):** antes de escrever um módulo do Clipator, abra os arquivos listados para ele aqui, rode-os se possível e só então decida entre copiar, adaptar ou reescrever. Não reinvente o que já está resolvido e testado nesses repos.

## Como trazer o código

1. Clone os repos numa pasta `referencias/` na raiz do projeto, que fica no `.gitignore` (só leitura, nunca editar lá):

   ```bash
   mkdir -p referencias && cd referencias
   git clone --depth 1 https://github.com/mutonby/openshorts.git
   git clone --depth 1 https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator.git
   git clone --depth 1 https://github.com/browser-use/video-use.git
   git clone --depth 1 https://github.com/francozanardi/pycaps.git
   git clone --depth 1 https://github.com/heygen-com/hyperframes.git
   git clone --depth 1 https://github.com/FujiwaraChoki/supoclip.git
   git clone --depth 1 https://github.com/Aseiel/VideoHighlighter.git
   git clone --depth 1 https://github.com/calesthio/OpenMontage.git
   ```

2. Ao copiar ou adaptar um arquivo, mantenha no topo um comentário com origem, commit e licença, e registre a linha em `THIRD_PARTY_NOTICES.md`:

   ```python
   # Adaptado de openshorts/active_speaker.py (commit d97b809), MIT License,
   # Copyright (c) 2024 OpenShorts. Ver THIRD_PARTY_NOTICES.md.
   ```

3. Copie a lógica, não a infraestrutura deles: nada de billing, contas, e-mail, armazenamento em nuvem, Gemini ou APIs pagas. No Clipator, toda chamada de IA passa pelo adaptador único (Claude ou Codex).

## Licenças: o que pode ser copiado

| Repo | Licença | Commit lido | Pode copiar código? |
| --- | --- | --- | --- |
| [OpenShorts](https://github.com/mutonby/openshorts) | MIT, exceto a pasta `cloud/` (licença comercial própria) | d97b809 | Sim, com atribuição. Nunca a pasta `cloud/` |
| [AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) | MIT | 315ea8d | Sim, com atribuição |
| [video-use](https://github.com/browser-use/video-use) | MIT | 43cfc56 | Sim, com atribuição |
| [pycaps](https://github.com/francozanardi/pycaps) | MIT | e2d36ed | Sim; melhor usar como dependência |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache 2.0 | 5c57942 | Sim; usar como dependência e copiar componentes do registry com o NOTICE |
| [SupoClip](https://github.com/FujiwaraChoki/supoclip) | AGPL-3.0 | 4bc76f8 | Sim, com atribuição (o Clipator é AGPL-3.0) |
| [VideoHighlighter](https://github.com/Aseiel/VideoHighlighter) | AGPL-3.0 (+ licença comercial) | 87a8168 | Sim, com atribuição (o Clipator é AGPL-3.0) |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0 | 195eab2 | Sim, com atribuição (o Clipator é AGPL-3.0) |

O Clipator é AGPL-3.0 (decidido em 01/11/2026), então o código dos três repos AGPL também pode ser copiado, mantendo a atribuição. O código MIT e Apache copiado continua com o aviso de licença original em `THIRD_PARTY_NOTICES.md`.

## Mapa por módulo do Clipator

### 1. Ingestão (link ou upload)

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `openshorts/quality_probe.py` | Antes de começar, pergunta ao YouTube a resolução máxima do link e se os cookies valem, para não gastar 20 min num vídeo 360p | Copiar |
| `openshorts/yt_clients.py` | Clientes do yt-dlp que funcionam para YouTube | Estudar e adaptar |
| `openshorts/free_tools.py` (`fetch_transcript`, `choose_track`, `parse_json3`) | Lê a legenda que o vídeo já tem no YouTube, sem baixar mídia. Atalho grátis para pré-análise | Adaptar como "pré-análise rápida" |
| `AI-Youtube-Shorts-Generator/shorts_generator/local/downloader.py` | Download local simples com yt-dlp | Referência mínima |

### 2. Transcrição

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `openshorts/transcribe_backends.py` | Contrato único de transcrição (`transcribe_media` com texto, idioma, segmentos e palavras), Parakeet com fallback para faster-whisper, detecção de "sem áudio", correção de deriva | Copiar o contrato e o fallback |
| `openshorts/subtitles.py` (`merge_continuation_words`, `_normalize_subtitle_word`) | Limpeza de palavras quebradas do Whisper | Copiar |
| `pycaps/src/pycaps/transcriber/faster_whisper_audio_transcriber.py` | Wrapper enxuto do faster-whisper com timestamps por palavra | Referência |
| `video-use/helpers/pack_transcripts.py` | Agrupa palavras em frases (quebra em silêncio >= 0,5 s ou troca de falante) e gera um markdown compacto com `[início-fim]`. É exatamente o formato barato para mandar à IA | Copiar para o modo econômico |

### 3. Sinais locais e candidatos (pontos virais)

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `openshorts/clip_selection.py` | Só biblioteca padrão: janelas de transcrição, metas de quantidade, duração mínima e máxima, remoção de sobreposição, `snap_clip_to_words` (corte sempre em palavra inteira) | Copiar quase inteiro |
| `AI-Youtube-Shorts-Generator/shorts_generator/highlights.py` | Detecta tipo de conteúdo, divide vídeos longos em blocos sobrepostos, `dedupe_highlights` por nota, parser de JSON tolerante | Copiar `chunk_transcript`, `dedupe_highlights`, `_parse_json_loose` |
| `openshorts/scene_detection.py` | TransNetV2 (bem melhor que limiar) com fallback no PySceneDetect e fusão de cenas curtas | Copiar |
| `openshorts/active_speaker.py` | Quem está falando por movimento da boca + energia do áudio, sem diarização completa | Copiar; base da "cor por falante" do estilo Podcast itálico |
| `supoclip/backend/src/clip_openings.py` | Revisa os primeiros segundos do corte e pula enrolação ("é... então...") | Copiar |
| `VideoHighlighter/modules/audio/` (`reaction_bursts.py`, `loudness_bursts.py`, `vocal_signals.py`, `audio_peaks.py`) | Risadas, picos de volume, sinais vocais | Copiar |
| `VideoHighlighter/modules/report/highlight_report.py`, `signal_timeline_viewer.py` | Relatório "por que essa nota" e linha do tempo de sinais | Ideia para a interface |

### 4. Reenquadramento e layouts

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `openshorts/reframe_v2.py` | Motor de reenquadramento: análise em 640 px num passe só, trajetória de câmera suavizada, render nativo no FFmpeg com `sendcmd` | Copiar; é o núcleo do 9:16 seguindo o rosto |
| `openshorts/split_layout.py` | Layout de dois falantes empilhados | Copiar |
| `openshorts/camera_inset.py` | Acha a webcam no canto de gravação de tela ou live e monta tela em cima + rosto embaixo | Copiar; estilo Gamer |
| `openshorts/burned_subtitles.py` | Detecta legenda já queimada no vídeo original para não empilhar duas | Copiar |
| `openshorts/frame_sampler.py` | Amostra quadros sem seek repetido (89 s de CPU caem para 6 s num clip de 20 s) | Copiar |
| `openshorts/ffmpeg_utils.py` (`blurred_backdrop`, `cut_clip`, `video_encode_args`) | Fundo desfocado, corte e escolha de encoder x264 ou NVENC com fallback | Copiar |
| `openshorts/layout_picker.py` | Escolha de layout por vídeo. Hoje usa Gemini | Adaptar para Claude/Codex ou heurística |
| `AI-Youtube-Shorts-Generator/shorts_generator/local/clipper.py` | Versão mínima do crop vertical com OpenCV | Referência didática |

### 5. Legendas, gancho e efeitos

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `openshorts/subtitles.py` (`generate_ass`, `line_budget`, `burn_subtitles`) | ASS com cores, orçamento de palavras por linha, queima via FFmpeg | Copiar como base do estilo ASS |
| `openshorts/hook_placement.py` | Posiciona o texto de gancho fora do rosto (detecta cabeça e escolhe faixa livre) | Copiar |
| `openshorts/hooks.py` (`create_hook_image`, `_draw_pills`, emojis) | Cartela de gancho com fundo em pílula e emoji colorido | Copiar |
| `openshorts/edit_builder.py` | A IA devolve só uma lista de edições (o quê e quando); o módulo vira filtro FFmpeg seguro, com limite de zoom e sem cortar legenda | Copiar; é o formato do nível "Assistido" |
| `pycaps/` (pipeline, `tag/`, `renderer/`) | Legenda em CSS, marcação de palavras por regex, animações por palavra | Usar como dependência |
| `supoclip/backend/src/emoji_captions.py`, `caption_templates.py`, `font_registry.py` | Emoji contextual e destaque de palavras fortes; templates de legenda; registro de fontes | Copiar |
| `hyperframes/registry/components/` (239 componentes) | Prontos para estilos: `caption-pill-karaoke`, `caption-highlight`, `caption-kinetic-slam`, `caption-emoji-pop`, `caption-editorial-emphasis`, `marker-highlight`, `caption-glitch-rgb`, `titlecard-lockup`, `zoom-through-transition`, `cinematic-zoom`, `bar-chart-race` | Copiar para a biblioteca de blocos do Clipator |
| `hyperframes/registry/blocks/` (210 blocos) | Cenas prontas (contagem de números, carrosséis, HUD de câmera) | Base dos estilos Números na tela e Dossiê |

### 6. Render, cor e áudio

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `video-use/helpers/render.py` | Render a partir de uma EDL: extrai segmentos com fade de 30 ms, concatena sem perda, compõe legendas e overlays num grafo só, loudnorm em duas passadas | Copiar a ordem do pipeline |
| `openshorts/recut.py` | EDL por clip, caminho rápido (copy) e caminho completo, ajuste em palavras | Copiar para o "ajustar início e fim" |
| `video-use/helpers/grade.py` | Correção de cor automática por clip ou por preset | Copiar |
| `video-use/helpers/timeline_view.py` | Gera PNG com tira de quadros + forma de onda + palavras. Serve para a IA "ver" um trecho barato e para a prévia na interface | Copiar |
| `openshorts/gpu_render.py`, `gpu_decode.py` | Aceleração por GPU | Depois do MVP |
| `hyperframes/skills/media-use/` | Música, efeitos sonoros e mixagem dentro do HyperFrames | Ler antes do módulo de áudio |

### 7. IA, MCP e integração com agentes

| Arquivo | O que já resolve | Ação |
| --- | --- | --- |
| `openshorts/mcp_server.py` + `mcp_stdio.py` | MCP inteiro sem SDK: initialize, tools/list, tools/call; o mesmo servidor em HTTP e em stdio | Copiar a estrutura do `clipator mcp` |
| `openshorts/skills/openshorts/` e `.claude-plugin/plugin.json` | Skill e plugin para Claude Code | Modelo para a skill do Clipator |
| `openshorts/integrations/chatgpt-app/` | Plugin com MCP para ChatGPT | Modelo para o lado Codex/ChatGPT |
| `openshorts/llm_backend.py` | Saída JSON com formato forçado e fallback quando o servidor recusa o schema | Adaptar para `claude -p --json-schema` e `codex exec --output-schema` |
| `openshorts/hook_grounding.py` | Reescreve gancho e título olhando quadros quando o conteúdo está na tela | Adaptar (Claude lê imagem) |
| `hyperframes/skills/hyperframes/`, `hyperframes-cli`, `hyperframes-registry` | Skills que ensinam Claude Code e Codex a escrever composições | Instalar junto e citar na skill "criar-estilo" |
| `hyperframes/skills/reverse-any-video/` | Reconstrói um vídeo como projeto HyperFrames editável | Base do "criar estilo a partir de vídeo de referência" |
| `OpenMontage/pipeline_defs/clip-factory.yaml`, `podcast-repurpose.yaml`, `skills/pipelines/` | Pipelines em YAML + skills em .md guiando o agente, com portões de qualidade e controle de custo | Copiar o formato das skills e pipelines |
| `OpenMontage/tools/cost_tracker.py` | Rastreio de custo por ação | Ideia para o orçamento de tokens |
| `video-use/SKILL.md` | Fluxo conversacional: propor corte em texto, confirmar, executar, prévia, iterar | Base do comportamento do agente |

## Cuidados

- O HyperFrames tem um comando `usage` que reporta "uso do plano", e a skill `media-use` cita recursos da HeyGen. O render local é Apache 2.0 e gratuito, mas confirme no protótipo que nenhum passo do Clipator depende de serviço pago da HeyGen.
- Vários módulos do OpenShorts chamam Gemini (`gemini_worker.py`, `layout_picker.py`, `hook_grounding.py`). Copie só a parte local e troque a chamada pelo adaptador de IA do Clipator.
- Os commits acima são de 01/11/2026. Antes de copiar, atualize o clone e confira se o arquivo mudou.
