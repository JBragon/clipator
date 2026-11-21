# Avisos de terceiros

O Clipator é distribuído sob a [GNU Affero General Public License v3.0](LICENSE). Partes do código foram copiadas ou adaptadas de projetos abertos, e alguns arquivos de terceiros acompanham o repositório. Cada arquivo adaptado diz no topo de onde veio. Esta lista reúne as origens e as licenças.

## Código adaptado

| Origem | Commit lido | Licença | Onde no Clipator |
| --- | --- | --- | --- |
| [OpenShorts](https://github.com/mutonby/openshorts) (núcleo, nunca a pasta `cloud/`) | cf0810f | MIT, Copyright (c) 2024 OpenShorts | `candidates.py` (dedupe_overlapping, snap_clip_to_words), `subtitles.py` (técnica de karaokê em ASS), `transcribe.py` (merge_continuation_words), `media.py` (encoder, fundo desfocado), `ingest.py` (validação de link), `reframe.py` (ideia da trajetória com sendcmd), `mcp_server.py` (estrutura) |
| [AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) | 315ea8d | MIT, Copyright (c) 2026 Anil Chandra Naidu Matcha | `ai/adapter.py` (parse_json_loose), `pack.py` (blocos sobrepostos) |
| [video-use](https://github.com/browser-use/video-use) | 43cfc56 | MIT, Copyright (c) 2026 Browser Use | `pack.py` (frases com [início-fim]), `render.py` (ordem do pipeline de render) |

Texto da licença MIT, que vale para os três projetos acima com o respectivo aviso de copyright:

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Fontes incluídas (`motor/src/clipator/dados/fontes/`)

| Fonte | Licença | Arquivo de licença |
| --- | --- | --- |
| Montserrat ExtraBold e ExtraBold Italic (Julieta Ulanovsky e colaboradores) | SIL Open Font License 1.1 | `OFL-Montserrat.txt` |
| Anton (Vernon Adams) | SIL Open Font License 1.1 | `OFL-anton.txt` |
| Bangers (Vernon Adams) | SIL Open Font License 1.1 | `OFL-bangers.txt` |
| Bebas Neue (Dharma Type) | SIL Open Font License 1.1 | `OFL-bebasneue.txt` |
| Special Elite (Astigmatic) | Apache License 2.0 | `LICENSE-SpecialElite.txt` |

## Dados cartográficos incluídos (`motor/src/clipator/dados/geo/`)

| Dados | Licença | Onde |
| --- | --- | --- |
| [Natural Earth](https://www.naturalearthdata.com/): países 1:50m, subdivisões 1:10m e regiões físicas 1:110m, pelo repositório [natural-earth-vector](https://github.com/nvkelso/natural-earth-vector) | Domínio público ([termos de uso](https://www.naturalearthdata.com/about/terms-of-use/)) | `paises.geojson.gz`, `subdivisoes.geojson.gz`, `continentes.geojson.gz`; fonte, data de acesso e hashes em `FONTES.json` |

As coordenadas não foram alteradas. Os limites são os de facto do Natural Earth, generalizados para visualização, e não são definição oficial de fronteira. O código de `artes/geografia.py` e `dados/geo/geo.js` foi adaptado do pacote de autoria "mapa-geografico-real" (AGPL-3.0-or-later).

## Dependências principais (não copiadas, instaladas pelo gerenciador de pacotes)

FFmpeg (LGPL/GPL, conforme a build), yt-dlp (Unlicense), faster-whisper (MIT), CTranslate2 (MIT), MediaPipe (Apache 2.0) e o modelo BlazeFace baixado do Google na primeira execução (Apache 2.0), OpenCV (Apache 2.0) e o modelo de rosto YuNet do [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), baixado na primeira execução (MIT, Copyright (c) 2020 Shiqi Yu), FastAPI (MIT), Uvicorn (BSD), websockets (BSD), Pydantic (MIT), PyYAML (MIT), NumPy (BSD), Pillow (MIT-CMU), segno (BSD-3, QR code do pareamento do modo remoto), SDK oficial de MCP (MIT). O HyperFrames (Apache 2.0, HeyGen) é instalado à parte pelo npm e chamado pelo CLI; os templates em `motor/src/clipator/dados/hyperframes/` são do Clipator. Os scripts `install.sh` e `install.ps1` também instalam, pelos canais oficiais, o uv (MIT ou Apache 2.0), o Deno (MIT) e o Node.js (MIT).

## Skills

A pasta `SKILLS/` reúne skills de terceiros, versionadas como estão por decisão do mantenedor. Créditos a **Jonny Viccari** pelas skills de criação de conteúdo, e aos autores indicados em cada `SKILL.md`. Cada skill mantém a licença declarada nela; as que não declaram licença continuam sendo de seus autores.

### Skills de desenvolvimento (`.claude/skills/`)

Skills do Claude Code usadas por quem desenvolve o Clipator, separadas das skills do produto. Foram copiadas sem alterações, e cada pasta traz o texto da licença em `LICENSE.txt`.

| Origem | Commit lido | Licença | Skills |
| --- | --- | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | 2ce8aa1 | MIT, Copyright (c) 2025 Jesse Vincent | `systematic-debugging`, `test-driven-development`, `verification-before-completion`, `receiving-code-review` |
| [trailofbits/skills](https://github.com/trailofbits/skills) | 2be6433 | Creative Commons Attribution-ShareAlike 4.0, Trail of Bits | `modern-python`, `property-based-testing`, `supply-chain-risk-auditor` (sem o `uv.lock` dos scripts) |
| [anthropics/skills](https://github.com/anthropics/skills) | ca45fc4 | Apache License 2.0, Anthropic | `mcp-builder`, `webapp-testing` |
| [CloudAI-X/threejs-skills](https://github.com/CloudAI-X/threejs-skills) | 0e18186 | MIT, Copyright (c) 2026 CloudAI-X | as 13 `threejs-*` (fundamentals, geometry, materials, lighting, textures, animation, loaders, shaders, postprocessing, interaction, performance, react-three-fiber, asset-pipeline) |

As skills da Trail of Bits seguem sob CC BY-SA 4.0: quem as modificar e redistribuir precisa manter o crédito e a mesma licença nessas pastas.

O `.claude/settings.json` também liga plugins oficiais da Anthropic do marketplace [claude-plugins-official](https://github.com/anthropics/claude-plugins-official) (Apache License 2.0): `security-guidance`, `claude-security`, `pr-review-toolkit`, `mcp-server-dev`, `typescript-lsp` e `pyright-lsp`. Eles não são copiados para o repositório; o Claude Code baixa cada um ao abrir o projeto.

## Stickers do editor (baixados, não incluídos no repositório)

O repositório guarda só a lista em `motor/src/clipator/dados/stickers/pacote.json` (URL presa a um commit e sha256 de cada arquivo). `clipator preparar` ou o botão "Baixar stickers" do editor baixam as imagens para `~/.clipator/stickers`.

| Origem | Commit | Licença | O que é usado |
| --- | --- | --- | --- |
| [microsoft/fluentui-emoji-animated](https://github.com/microsoft/fluentui-emoji-animated) | daa0365 | MIT, Copyright (c) Microsoft Corporation | 68 emoji animados (APNG 256×256) |
| [microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji) | 1ffb34c | MIT, Copyright (c) Microsoft Corporation | 98 emoji 3D (PNG 256×256) |

A busca online do editor (só quando o usuário clica) usa a API pública do [Iconify](https://iconify.design) e aceita apenas estas coleções: Fluent Emoji e Fluent Emoji Flat (MIT, Microsoft), Noto Emoji (Apache 2.0, Google) e Twemoji (CC BY 4.0, Twitter/jdecked). Cada sticker baixado fica em `canais/<canal>/stickers/web/` com a licença e o autor em `creditos.json`; os de licença CC BY entram sozinhos nos créditos da descrição do clip.

## Fontes do texto livre (baixadas, não incluídas no repositório)

O repositório guarda só a lista em `motor/src/clipator/dados/fontes/pacote.json` (URL presa ao commit 2fe1e8c de [google/fonts](https://github.com/google/fonts) e sha256 de cada arquivo). Cada fonte é baixada para `~/.clipator/fontes` quando o usuário escolhe ela no editor, ou todas pelo botão "Baixar as fontes que faltam". As licenças de cada família ficam na pasta dela no repositório google/fonts.

| Licença | Fontes |
| --- | --- |
| SIL Open Font License 1.1 | Abril Fatface, Alfa Slab One, Amatic SC, Archivo, Archivo Black, Audiowide, Bagel Fat One, Baloo 2, Barlow Condensed, Black Ops One, Boogaloo, Bowlby One SC, Bungee, Bungee Shade, Carter One, Caveat, Coiny, Creepster, Dancing Script, Dela Gothic One, Eater, Faster One, Fredoka, Frijole, Gloria Hallelujah, Great Vibes, Inter, Kanit, Knewave, League Gothic, Leckerli One, Lilita One, Lobster, Monoton, Montserrat Alternates, Nosifer, Nunito, Oleo Script, Orbitron, Oswald, Pacifico, Passion One, Patua One, Playfair Display, Poppins, Press Start 2P, Racing Sans One, Raleway, Righteous, Rubik, Rubik Glitch, Rubik Mono One, Rubik Wet Paint, Russo One, Saira Stencil One, Shadows Into Light, Shrikhand, Sigmar One, Silkscreen, Staatliches, Teko, Titan One, VT323 |
| Apache License 2.0 | Chewy, Luckiest Guy, Permanent Marker, Rock Salt, Satisfy, Ultra, Yellowtail |

## Referências de ideias (sem código copiado)

SupoClip, VideoHighlighter e OpenMontage (AGPL-3.0), HyperFrames (Apache 2.0) e pycaps (MIT) inspiraram partes do desenho. Quando código deles for copiado, ele entra nesta lista.

## three.js (maquete 3D)

A maquete low-poly em 3D usa o [three.js](https://threejs.org) 0.160.1 (MIT, Copyright © 2010-2023 three.js authors), instalado pelo npm como dependência do app (`app/package.json`). O arquivo `three.min.js` vai sem alterações dentro da camada de cenas renderizada pelo HyperFrames, e o app instalado o leva junto com a licença em `resources/three/`. As peças, a câmera e as animações da maquete são código do Clipator (`motor/src/clipator/maquete3d.py`). O motor leva uma cópia sem alterações em `motor/src/clipator/dados/vendor/three.min.js`, com a licença ao lado, para o comando `clipator` funcionar sem o app. As direções 3D (`motor/src/clipator/artes/tres.py`) usam a mesma biblioteca.
