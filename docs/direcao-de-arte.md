# Direção de arte

A direção de arte (DA) guia o corte: o estilo escolhe qual DA usar e o canal põe só a marca por cima
(veja a próxima seção). Uma DA é um arquivo `direcao.yaml` (um predefinido do Clipator, um predefinido
pessoal ou a DA própria de um canal) com paleta, tipografia, layout, movimento, tratamento de cor, legenda,
grafismos, thumbnail, som, marca e a seção `cenas`, que diz à IA como planejar as telas do corte. Estilos,
cenas animadas e thumbnails leem os tokens dela em vez de escrever cor ou fonte à mão.

Tudo roda offline e sem IA. A skill embutida `direcao-de-arte` ensina à IA o método de trabalho (briefing,
referências, rotas, refino, prancha, aprovação); este documento é a referência técnica.

O código fica em `motor/src/clipator/arte/`:

| Arquivo | O que faz |
| --- | --- |
| `esquema.py` | O esquema do `direcao.yaml` (pydantic; chave desconhecida é erro) |
| `carregar.py` | Herança, mescla, resolução dos tokens para hex, predefinidos |
| `cores.py` | Contraste WCAG, CIELAB, ΔE (CIEDE2000), ajuste de cor até um contraste alvo |
| `zonas.py` | Zonas seguras (de `plataformas.py`), faixa da legenda, posição da tarja, canto da thumb |
| `validar.py` | O validador: erro, aviso e nota, cada um com "como corrigir" |
| `compilar.py` | CSS `--da-*`, filtro FFmpeg do tratamento, ponte para ficha, legenda e cartela, `DA.md` |
| `identidade.py` | sha da DA, aprovação, revisões, carimbo dos renders e conferência |
| `referencias.py` | Leitura de imagens e vídeos de referência (cores dominantes, acentos, grão) |
| `prancha.py` | A prancha de estilo (PNG) e o cartão de comparação das rotas |
| `rotas.py` | Rotas candidatas: criar, listar, comparar, adotar |
| `lint.py` | Acha cor e fonte literais nos estilos |
| `importar.py` | Especificação de direção visual (`especificacao.json`) → DA, com o contraste corrigido |
| `guia.py` | A DA do estilo com a marca do canal, o guia da IA e a conferência das cenas |
| `servico.py` | As operações num lugar só (a CLI e o MCP chamam daqui) |
| `cli.py` | `clipator arte …` |

## A DA no corte: o estilo manda, o canal ajusta

- **O estilo escolhe a DA** no cabeçalho: `arte: documental` (predefinido ou predefinido pessoal),
  `arte: canal` (a DA própria do canal, `arte/direcao.yaml`) ou `arte: {herda: manchete, cenas: {por_minuto: 8}}`
  (predefinido com ajustes do próprio estilo). Estilo sem `arte:` segue como antes, pela ficha.
- **O canal só põe a marca**, em `arte/marca.yaml` (`clipator arte marca CANAL --criar`): `cores` (primaria,
  secundaria, destaque), `fontes` (papel → família; `corpo` vale também para dados e legenda), `logo`,
  `assinatura`, `posicao_logo`, `marca_dagua`, `opacidade_logo`. Se a primária ou o destaque da marca não
  chegam a 3:1 sobre o fundo da DA do estilo, a cor é escurecida ou clareada só o necessário, com aviso
  (`respeitar_contraste: false` desliga).
- **Ao planejar as telas do corte**, a IA recebe o guia da DA (`arte/guia.py`, `texto_para_ia`): conceito, tom,
  tipos de cena preferidos e evitados, ritmo, limites de texto, movimento, faça e não faça, regras. Sem hex.
- **A resposta é conferida** (`filtrar_cenas`): sai tipo evitado, texto acima do limite, cena perto demais de
  outra ou acima do teto por minuto (fica o título-gancho do começo e, depois, os tipos na ordem de
  `preferir`); a duração é presa entre a mínima e a máxima e as listas são cortadas no limite. O relato do
  render diz o que saiu e por quê. Vale no render e nas sugestões de cenas do editor.
- **No render**, a mesma DA vira a ficha das cenas, o CSS `--da-*`, a legenda e a cartela (`da:` e
  `{da: true}`), o tratamento de cor (se ligado) e o carimbo `<saida>.arte.json`, que guarda qual `arte:` o
  estilo usou.
- `clipator arte guia CANAL ESTILO` mostra a DA que o estilo usa, com a marca aplicada, os avisos e o texto
  exato da IA. `clipator arte prancha CANAL --estilo ESTILO` gera a prancha dela em `arte/build/prancha-<estilo>.png`.

### A seção `cenas`
| Campo | O que é |
| --- | --- |
| `tom` | Como as telas falam, numa frase |
| `preferir`, `evitar` | Tipos: titulo, numero, citacao, lista, comparacao, linha_do_tempo, local, nome, palavra, alerta |
| `intervalo` | Segundos mínimos entre o começo de duas cenas |
| `por_minuto` | Teto de cenas por minuto de corte |
| `duracao` | [mínima, máxima] de cada cena, em segundos |
| `palavras_titulo`, `palavras_rotulo`, `itens_lista`, `palavras_item` | Limites de texto |
| `abrir_com_titulo` | Abre com um título-gancho nos primeiros segundos |
| `regras` | Frases curtas que a IA segue |

## A pasta `arte/` do canal

```
canais/<canal>/arte/
  marca.yaml            cores da marca, fontes e logo, por cima da DA de qualquer estilo
  direcao.yaml          a DA própria do canal (opcional; os estilos usam com `arte: canal`)
  estado.json           revisão, aprovação, sha aprovado, histórico
  DA.md                 a DA em texto (gerado; a IA recebe como contexto)
  prancha.png           a prancha de estilo (gerada)
  referencias/          imagens e vídeos de referência + referencias_analise.json e referencias_folha.png
  fontes/  luts/  marca/
  rotas/<nome>/direcao.yaml   rotas candidatas; rotas/comparacao.png
  build/da.css  build/da.resolvida.json  build/prancha.json   (gerados)
```

## Convenções

- **Tamanhos são frações do lado menor do quadro.** `0.06` é 65 px num 1080×1920 e também num 1920×1080.
  Assim a mesma DA serve ao 9:16, ao 1:1 e ao 16:9. Quando a fração é de altura ou largura, o campo diz.
  Para ter ideia no celular: pt ≈ fração × 390.
- **Campo de cor aceita nome ou hex.** Nomes válidos: qualquer cor da `paleta` (`primaria`, `texto`…),
  `neutro-N` (da lista `neutros`, a partir de 1) e `serie-N`. Na `paleta` só entra hex.
- **Anotações:** chave que começa com `x_` ou `_` é guardada e ignorada, e não muda a identidade da DA.
- **Herança:** `herda` aponta para um predefinido, um predefinido pessoal ou um caminho relativo. O arquivo
  filho vence; mapas mesclam recursivamente; listas substituem a lista herdada inteira; `null` apaga a chave.

## Predefinidos

`clipator arte presets` lista os de fábrica (em `motor/src/clipator/dados/arte/presets/`) e os pessoais
(`~/.clipator/arte-presets/<nome>/direcao.yaml`, ou a pasta em `$CLIPATOR_ARTE_PRESETS`).

| Nome | Ideia |
| --- | --- |
| `base` | Grafite, texto claro e azul de sinal. Todos os outros herdam deste |
| `arquivo-confidencial` | Carvão, papel de processo e vermelho de carimbo; texto de máquina de escrever |
| `palco-noturno` | Azul de estúdio e coral de refletor; conversa, entrevista, podcast |
| `manchete` | Fundo claro de jornal, vermelho de plantão, legenda em caixa |
| `fliperama` | Roxo, ciano e amarelo; curvas com overshoot; games e humor |
| `caderno-de-aula` | Papel claro, azul de caneta, grifo coral; educação |
| `tela-de-dados` | Painel escuro, ouro para o valor que importa; finanças e números |
| `documental` | Preto de cinema, âmbar de tungstênio, fades longos |

As 22 direções visuais do pacote `clipator-artes-originais` também viram predefinidos, importados de cada
`especificacao.json` por `arte/importar.py` (a cor original e o que foi corrigido ficam nas anotações
`x_direcao` e `x_contraste_corrigido`): `acervo-natural`, `anotacao-em-foco`, `arquivo-em-camadas`,
`atlas-de-percursos`, `caderno-de-materiais`, `camadas-do-terreno`, `cidade-de-bolso`, `costura-viva`,
`gesto-de-papel`, `janela-em-profundidade`, `jardim-de-luz`, `letras-de-oficina`, `mapa-de-ideias`,
`mecanismo-facetado`, `mesa-em-profundidade`, `oficina-modular`, `painel-de-variacoes`, `quadro-de-recortes`,
`resina-em-movimento`, `revista-de-bancada`, `terrario-tecnico`, `tinta-em-etapas`. Um estilo `arte-*` aponta
para a dele com `arte: <nome>`; o renderizador da direção lê os tokens e as anotações. Na importação, o texto
suave vai a 4,5:1, a primária e o destaque a 3:1 (o destaque original fica como `realce`, para fundo de grifo),
o texto busca 7:1 também sobre a superfície e o selo escolhe a cor de texto que mais contrasta.
`clipator arte importar especificacao.json [--nome N]` faz o mesmo com qualquer especificação nova e grava um
predefinido pessoal.

Os predefinidos são originais do Clipator. Um predefinido pessoal nasce de `clipator arte salvar-preset
CANAL NOME`, que grava a DA com a herança aplicada e copia `fontes/`, `luts/` e `marca/`.

## Dicionário dos tokens

### `conceito`
| Campo | O que é |
| --- | --- |
| `frase` | A DA numa frase, como briefing para um motion designer |
| `palavras_chave` | 4 a 8 palavras do tom |
| `referencias` | `[{arquivo, nota}]`: imagem em `arte/referencias/` e o que tirar dela |
| `faca`, `nao_faca` | Regras concretas que a máquina não confere |

### `cor`
| Campo | O que é |
| --- | --- |
| `paleta` | Cores com nome (hex). Obrigatórias: `fundo`, `superficie`, `texto`, `texto_suave`, `primaria`, `secundaria`, `destaque`, `positivo`, `negativo`, `alerta`. Extras viram tokens |
| `neutros` | Preto e branco de sombra e brilho: `neutro-1`, `neutro-2`… |
| `serie` | Cores dos gráficos em ordem (`serie-1`…), no mínimo 6 |
| `gradientes` | `{nome: {tipo: linear\|radial, angulo, paradas: [[cor, 0–1], …]}}` |

### `tipografia`
`papeis` (obrigatórios `titulo`, `subtitulo`, `corpo`, `dados`, `legenda`), cada um com `familia`, `reserva`,
`peso` (100–1000), `italico`, `caixa_alta`, `espacamento` (em), `entrelinha`, `condensar` (escala horizontal).
`escala` com os degraus `display`, `h1`, `h2`, `h3`, `corpo`, `nota` (fração do lado menor, decrescentes).

### `layout`
`colunas`, `margem`, `calha`, `raio` (0 = tudo reto), `traco`, `sombra {dx, dy, desfoque, cor, alfa}`,
`densidade` (`arejada`, `media`, `densa`).

### `movimento`
| Campo | O que é |
| --- | --- |
| `curvas` | cubic-bezier `[x1, y1, x2, y2]`; obrigatórias `entrada`, `saida`, `enfase`, `suave` |
| `duracoes` | segundos; obrigatórias `micro`, `curta`, `media`, `longa` (em ordem crescente) |
| `escalonamento` | atraso entre itens de uma sequência |
| `entrada` | `sobe`, `desliza`, `escala`, `mascara`, `fade`, `digita` |
| `saida` | `fade`, `desce`, `mascara`, `corte` |
| `transicao_padrao`, `transicoes` | `corte`, `fade`, `empurra`, `mascara`, `desliza`, `zoom` (a padrão tem de estar na lista) |
| `principios` | regras de animação em frases verificáveis |

### `tratamento` (cor do vídeo)
`aplicar_nos_clips` (padrão `false`), `contraste`, `saturacao`, `gama`, `brilho`, `temperatura` (−100 fria a
100 quente), `grao`, `vinheta` (rad), `nitidez`, `lut` (arquivo `.cube` em `arte/luts/`), `intensidade_lut`,
`encaixe` (`desfocado`, `recorte`, `faixas`). Vira uma cadeia FFmpeg `eq`, `colortemperature`, `lut3d`,
`unsharp`, `noise`, `vignette`, aplicada no fim da cadeia do vídeo quando ligada.

### `legenda`
| Campo | O que é |
| --- | --- |
| `estilo` | `karaoke`, `palavra`, `bloco` |
| `papel` | papel tipográfico (padrão `legenda`) |
| `tamanho` | fração do lado menor (mínimo legível 0,04; confortável a partir de ~0,052) |
| `cor`, `cor_destaque`, `cor_falada` | cores do texto, da palavra destacada e da palavra já falada |
| `contorno {cor, espessura}` | espessura em fração do tamanho da fonte |
| `sombra {dx, dy, desfoque, cor, alfa}`, `caixa {cor, alfa, raio, respiro}` | proteções alternativas |
| `y_vertical`, `y_horizontal` | centro do bloco (fração da altura) no 9:16 e no 16:9 |
| `largura_max`, `max_linhas`, `max_palavras`, `animacao` (`pop`, `fade`, `nenhuma`) | |

### `graficos`
`tarja` (nome de quem fala: `estilo`, `posicao`, papéis, tamanhos e cores de nome, cargo, fundo e acento),
`selo` (faixa "AO VIVO"), `credito` (fonte do dado), `icones` (`traco` ou `cheio`), `eixo`, `grade`.

### `thumbnail`
`max_palavras`, `papel`, `tamanho` (fração da altura), `cor`, `cor_destaque`, `contorno`, `fundo` (cor,
`gradiente:<nome>` ou `foto`), `borda`, `canto_reservado` (onde a plataforma põe a duração), `reserva`
`[largura, altura]`, `tratamento_foto`.

### `som` e `marca`
`som`: `identidade`, `loudness {alvo_lufs, pico_dbtp}`, `efeitos {entrada, enfase, numero, alerta}`,
`volume_efeitos`, `musica {clima, bpm}`. `marca`: `assinatura`, `logo`, `posicao_logo`, `marca_dagua`,
`opacidade_logo`.

### `formatos`
Quadros nomeados (`vertical`, `horizontal`, `quadrado`, `retrato`, `thumbnail`) com `largura`, `altura`, `fps`.

## O validador

`clipator arte validar CANAL [--json]` devolve achados em três níveis: **erro** (a DA não pode ser usada
assim), **aviso** (provável problema de leitura ou de coerência) e **nota** (dica). Cada achado tem código,
onde, mensagem e "como corrigir". Principais conferências:

- tokens que apontam para cor ou papel inexistente;
- contraste WCAG de texto e texto suave sobre fundo e superfície, de primária e semânticas, de tarja e selo
  (com sugestão do hex mais próximo que passa);
- cores quase idênticas (ΔE < 3), série curta, repetida, com vizinhas parecidas ou sem contraste;
- gradiente chapado; mais de duas famílias; fonte que não está instalada; escala fora de ordem ou ilegível;
- legenda sem proteção, contorno fino, destaque igual ao texto, fora da zona segura, em cima da tarja;
- curvas e durações obrigatórias, transição padrão fora da lista, overshoot (nota);
- tratamento exagerado, LUT ausente, thumb com texto pequeno ou longo, loudness fora do comum;
- DA alterada depois de aprovada.

A zona segura é a união do pior caso de Shorts, Reels e TikTok, tirada de `plataformas.py`.

## Prancha, rotas e aprovação

- `clipator arte prancha CANAL [--referencia quadro.png]` gera `arte/prancha.png`: cabeçalho e conceito,
  referências, paleta com contraste, série, gradientes, tipografia e escala, quadro 9:16 com zonas, legenda e
  tarja (sobre o quadro de referência, se houver), faixa 1:1, curvas de movimento, thumbnail com o canto
  reservado hachurado e as regras.
- `clipator arte rotas CANAL criar NOME [--base P] [--frase F] [--primaria #HEX]` cria uma rota em
  `arte/rotas/NOME/`. Sem `--base`, ela herda da DA atual. `listar`, `comparar [--com-atual]` (gera
  `rotas/comparacao.png`) e `adotar NOME` (a rota vira a DA, gravada só com o que difere do predefinido; a
  anterior fica em `direcao.yaml.bak-<data>`; abre nova revisão).
- `clipator arte aprovar CANAL [--estrito]` grava o sha da DA em `estado.json` e regenera a prancha com o
  carimbo. O sha cobre tudo que muda o visual, inclusive o conteúdo dos arquivos de fonte, LUT e logo, e
  ignora `nome`, `conceito`, `herda`, `versao` e as anotações.
- `clipator arte revisar CANAL --motivo "..."` abre uma revisão nova (a DA volta a precisar de aprovação).

## Usar a DA nos estilos e nas cenas

- **Tokens no estilo:** qualquer valor `"da:<token>"` no cabeçalho de um estilo é trocado na hora do render.
  Vale em campos de cor e de fonte: nomes de cor (`da:primaria`, `da:serie-2`), papéis (`da:titulo` vira a
  família) e caminhos de campos de cor (`da:legenda.cor_destaque`,
  `da:graficos.tarja.cor_acento`). Token que não existe não é trocado: confira o nome com `clipator arte token CANAL <nome>`.
- **`legenda: {da: true}`** preenche a legenda com a DA (fonte, tamanho, cores, contorno, sombra, caixa,
  posição, modo, animação, palavras por linha). O que o estilo escreveu vence. O mesmo vale para
  `cartela: {da: true}`. Um estilo que só tem `legenda: {da: true}` e `cartela: {da: true}` segue a DA inteira.
- **Cenas:** `direcao.ficha: canal` usa a DA como ficha. Com outra ficha e sem cores no estilo, as cores e
  fontes da DA entram por baixo dos ajustes do `canal.md` e do clip.
- **HTML/CSS:** `arte/build/da.css` entra nas cenas e nos templates HyperFrames. Variáveis:
  `--da-cor-<nome>` e `--da-cor-<nome>-rgb`, `--da-gradiente-<nome>`, `--da-fonte-<papel>`,
  `--da-peso-<papel>`, `--da-espacamento-<papel>`, `--da-entrelinha-<papel>`, `--da-escala-<degrau>`,
  `--da-curva-<nome>`, `--da-dur-<nome>`, `--da-margem`, `--da-raio`, `--da-traco`; classes
  `.da-<papel>` com família, peso, caixa e espaçamento prontos.
- **Sem DA:** um canal sem `arte/direcao.yaml` funciona como antes; os `da:` saem com os valores do `base`.
- **Carimbo:** cada render final com DA grava `<saida>.arte.json` com revisão, sha e se a DA estava aprovada.

## Lint e conferência

- `clipator arte lint CANAL [ARQUIVOS…]` lê `.css`, `.html`, `.js`, `.svg` e o cabeçalho dos `.md` de estilo
  (padrão: `estilos/` do canal e do workspace) e acusa hex, `rgb()`/`hsl()`, nomes de cor do CSS e
  `font-family` com nome de fonte, sugerindo o token mais perto com o ΔE. `rgba(var(--da-cor-x-rgb), .5)` é
  aceito. Exceções: `/* da-livre */` na linha, `da-livre-arquivo` nas 10 primeiras linhas.
- `clipator arte conferir CANAL`: a marca válida; a DA própria do canal, se existir, sem erro e aprovada (e não
  alterada depois); lint dos estilos; e cada clip de `projetos/` conferido contra a versão atual da DA que o
  estilo dele usou (com a marca de agora). Clip feito com outra versão é erro.

## Comandos

```
clipator arte presets
clipator arte criar CANAL [--base fliperama] [--nome "Meu canal"] [--forcar]
clipator arte validar CANAL [--json]
clipator arte compilar CANAL
clipator arte mostrar CANAL
clipator arte token CANAL cor.paleta.primaria      (ou --preset NOME no lugar do canal)
clipator arte extrair CANAL [ARQUIVOS…] [--quadros 6]
clipator arte prancha CANAL [--referencia quadro.png] [--estilo ESTILO]
clipator arte guia CANAL ESTILO
clipator arte marca CANAL [--criar]
clipator arte importar especificacao.json [--nome N] [--substituir]
clipator arte aprovar CANAL [--estrito]
clipator arte revisar CANAL [--motivo "..."]
clipator arte lint CANAL [ARQUIVOS…]
clipator arte rotas CANAL criar NOME [--base P] [--frase F] [--primaria #HEX]
clipator arte rotas CANAL listar | comparar [--com-atual] | adotar NOME
clipator arte salvar-preset CANAL NOME [--substituir]
clipator arte conferir CANAL
```

Saída: 0 ok, 1 reprovado (validação, lint ou conferência), 2 o canal não tem DA, 64 uso errado.

No MCP: `arte_presets`, `arte_criar`, `arte_ler`, `arte_token`, `arte_validar`, `arte_compilar`,
`arte_extrair_referencias`, `arte_prancha` (com `estilo`), `arte_guia`, `arte_marca`, `arte_rotas`, `arte_aprovar` (exige `confirmar=true`),
`arte_revisar`, `arte_conferir`, `arte_lint`.
