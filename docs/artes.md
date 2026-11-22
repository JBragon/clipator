# Direções de arte

São 28 estilos com renderizador próprio (`dados/estilos/arte-<id>.md`, `direcao: {modo: arte, arte: <id>}`). Cada cena ilustra uma frase da fala e o vídeo original continua embaixo, no layout `em-cima`. Exigem a IA integrada: antes das cenas, a IA escreve e o motor confere a direção de vídeo do clip (`direcao_video.py`: história, elenco fixo, cenários, posições, câmera e continuidade, com uma rodada de correção). O render continua local e sem rede depois que o HyperFrames está instalado. O planejador por frases (`planejar_regras`) ficou só para as amostras da galeria e as demos.

## Como funciona

| Parte | Onde |
| --- | --- |
| Registro, parâmetros, âncoras, plano sem IA, ficha, painel | `motor/src/clipator/artes/__init__.py` |
| Medição de texto e pedaços de SVG | `artes/kit.py` |
| Renderizadores | `artes/editoriais.py`, `graficos.py` (2D), `cenarios.py` (as quatro híbridas, com alternativa 2D) e `tres.py` (o script three.js das dez com canvas e a alternativa SVG das seis 3D) |
| Parâmetros e ficha curta de cada direção | `dados/artes/<id>.json` e `<id>.md` |
| Paleta, fontes, sons, ritmo e marca do canal | a DA do estilo (`arte: <id>`, `dados/arte/presets/<id>.yaml`, ver [direcao-de-arte.md](direcao-de-arte.md)) |

As cenas são itens `cena` do `edicao.json` com `params.cena == "arte"`, então moram na mesma linha do tempo das outras e entram nas versões da edição: texto, ordem, parâmetros e cores voltam junto ao desfazer. O contrato `clipator-arte/1` do pacote de autoria foi adaptado para esses itens; não existe um segundo documento.

**Plano.** Sem IA, uma cena por frase, só com as palavras ditas. Com IA, a mesma pré-produção dos outros estilos (análise e roteiro) e uma terceira etapa que preenche texto, itens, nota e dado. Número ou frase que não foi dito é descartado. Só a ficha da direção escolhida entra no pedido. A prévia nunca chama a IA.

**Âncoras.** Cada cena guarda o trecho literal e a ocorrência. Se o tempo do clip muda (corte interno ou trecho), o render refaz o tempo pela âncora; trecho removido tira a cena com aviso. Com o mesmo tempo, nada é mexido, para respeitar a cena movida à mão.

**Parâmetros.** A allowlist vem de `limites_parametros` da especificação. Chave desconhecida é recusada e o valor é preso aos limites antes de gerar qualquer coisa. Todo parâmetro listado é lido pelo renderizador (há um teste para isso). `leve` e `semente` valem para todas.

**Texto e cor.** As linhas são medidas com a fonte real (Pillow). Texto só usa `--texto`, `--fundo` ou as cores calculadas depois da herança (`--acento`, `--sobre-primaria`, `--sobre-destaque`), e o texto principal é corrigido com aviso se ficar abaixo de 4,5:1.

**Mídia.** A cena pode ter `midia`, um caminho relativo a `<canal>/assets/arte/`. Caminho absoluto, `..`, endereço remoto e fuga por link são recusados. O arquivo vai para a camada com o hash no nome, então conteúdo novo no mesmo caminho refaz a camada. Sem mídia, a cena usa a alternativa desenhada e diz isso no aviso. Ainda não há tela para escolher a mídia: o campo existe no `edicao.json`.

## Cinco direções guiadas pela fala

Encaixe Vivo, Pixel em Cena, Fluxo Facetado, Rota em Foco e Terreno Vivo (`artes/cortes.py`, `dados/cortes/motor.js`, `dados/cortes/lexico.json`). A família visual é fixa; quem aparece, a ação e a ordem saem da transcrição. Cada cena é uma ação (`params.corte`: `acao`, `objetos`, `alvo`, `conjunto`) presa a uma âncora literal com ocorrência. O objeto entra no segundo em que a palavra é dita, já na linha do tempo depois dos cortes internos, e trecho removido tira a ação.

**Plano.** Sem IA, um léxico liga palavra a forma e verbo a ação; palavra fora do léxico só vira bloco genérico nos estilos de peças. Com IA, o adaptador recebe o texto da ficha e devolve o JSON de `cortes.schema`; objeto cujo nome não foi dito sai, e a ação fora da lista vira a padrão. O nome na tela é sempre a palavra dita.

**Motor.** Um mundo só por clip, em three.js, recalculado a cada quadro a partir do tempo, sem estado entre quadros. Os exemplos em `dados/artes/exemplos/` são a amostra da galeria, nunca um modelo de conteúdo. Rota em Foco nunca desenha um lugar real: a tela diz "Mapa fictício" quando a fala diz, e "Esquema ilustrativo, sem escala" nos outros casos. Sem WebGL ou com `leve`, fica a alternativa em SVG.

## Modo curta: cada frase é um plano

Nas cinco direções guiadas pela fala, o clip deixou de ser um diorama só. Cada cena guarda `params.curta` (`artes/curta.py`, motor em `dados/curta/curta.js`, vocabulário em `dados/curta/lexico.json`) e vira um plano de um curta-metragem:

| Campo | O que faz |
| --- | --- |
| `cenario` | Um de 24 lugares montados no material do estilo: cidade, casa, cozinha, quarto, escritório, escola, loja, restaurante, hospital, fábrica, laboratório, parque, floresta, campo, praia, mar, montanha, deserto, espaço, estrada, palco, estádio, aeroporto e o palco neutro do estilo |
| `lugar` | A palavra do lugar como foi dita (vira a placa na tela). Verbo que só sugere o lugar ("acordei", "comprar") escolhe o cenário mas nunca vira rótulo |
| `personagens` | Até três, com uma de 13 ações animadas em poses: parado, andar, correr, falar, pensar, comemorar, cair, trabalhar, apontar, sentar, dormir, triste, pular |
| `situacao` | O sentido da frase em efeito: festa, ideia, dúvida, dinheiro, tempo, perigo, amor, conversa, sucesso, tristeza, raiva, sono, crescimento, queda, multidão |
| `momento`, `clima` | Dia, manhã, tarde, noite; chuva ou neve. Mudam céu, luz e janelas |
| `plano`, `movimento`, `transicao` | Geral, conjunto, médio, close, detalhe, aéreo; câmera fixa, aproximando, afastando, panorâmica ou travelling; corte, fade, cortina ou zoom |
| `aderecos`, `tons`, `nota_visual` | Objetos de cena sem rótulo, até três cores da pesquisa, e uma frase para quem revisa |

**Montagem.** `curta.encadear` olha a sequência: o curta abre no primeiro lugar citado, lugar novo entra com plano geral e transição, frase sem lugar mantém o anterior e troca o plano (médio, close, detalhe...), como num filme. Chuva dita num lugar fechado corta para a rua. O lugar novo se monta peça a peça (no Encaixe Vivo, pela `duracao_montagem`).

**Identidade.** O estilo continua sendo o estilo: Encaixe Vivo em peças plásticas com pinos, Pixel em Cena pixelado com textura nearest, Fluxo Facetado em polígonos chapados (`facetas`), Rota em Foco em maquete de papel vista do alto com grade e a rota no chão (`espessura_rota`), Terreno Vivo em corte isométrico com camadas de solo (`tamanho_lote`, `altura_corte`, `hachura`). Todo parâmetro da direção é lido também pelo `curta.js` (há teste).

**Sem IA.** O léxico lê a frase: o último lugar dito pelo nome (é para onde a ação vai), a ação mais específica (andar perde para qualquer outra), pessoas (pronome nunca vira nome na tela), situação, hora e clima.

**Com IA: o roteiro fechado.** Nessas cinco direções a pré-produção não escolhe cena por cena. Depois da análise (etapa 1), a IA recebe numa chamada só a transcrição com tempos, o título, o tema e as ideias do corte, a descrição visual do estilo (`curta.VISUAL`), tudo o que o motor sabe desenhar (cenários, ações, situações, planos, movimentos, transições e objetos, com descrição), as referências pesquisadas, a direção de arte e a skill embutida `roteiro-do-curta` (`dados/skills/roteiro-do-curta/SKILL.md`). Ela devolve o curta inteiro (`curta.schema_roteiro`): o assunto, uma metáfora concreta mantida do começo ao fim (fala abstrata, como "temperatura do modelo", vira uma história: um cozinheiro e o fogo do fogão), a logline, o elenco (até três, `pessoa` ou `robo`, com ids) e um plano a cada 2 a 5 segundos, cada um com âncora copiada da fala, descrição do que se vê e por quê, cenário, quem está em cena e fazendo o quê, situação, câmera, transição, objetos e placa.

`curta.de_roteiro` confere tudo: prende cada plano na fala pela âncora, troca os ids do elenco por atores (o mesmo personagem tem o mesmo visual em todos os planos; robô tem corpo de metal, antena e rosto de tela), e apaga rótulo, placa e nome que não foram ditos no trecho do plano. Palavra de quem fala ("a gente", "eu", "você", "isso") nunca vira texto na tela. A placa do plano é só a que o roteiro escolheu; sem placa, não aparece texto. `artes.cenas_do_curta` transforma os planos em cenas, e o documento `direcao-arte.json` guarda a metáfora, a logline e o elenco em `curta`. A skill de roteiro vai só para essa chamada (as outras etapas e a edição não recebem). Com o roteiro já editado à mão, a etapa 3 antiga continua: a IA devolve `curta` em cada cena, e o que não foi dito é apagado do mesmo jeito.

**Pesquisa de referências** (`artes/pesquisa.py`). Antes do roteiro do curta, a direção de arte pesquisa os nomes próprios (palavra com maiúscula só por começar a frase, como "Porque" ou "Eles", não conta) e os lugares ditos na Wikipédia (resumo) e no Wikimedia Commons (descrição e miniatura de até duas imagens de domínio público ou Creative Commons). O texto vai para a IA como contexto, nunca para a tela; as miniaturas são lidas em CIELAB e viram até três `tons` no plano que cita o termo (chão, água ou céu, acento), puxados para a paleta do estilo. A imagem não é usada nem guardada: só a cor e o crédito (`direcao-arte.json` → `pesquisa.creditos`). As duas fontes são gratuitas e sem conta. Roda só na pré-produção com IA; sem rede, ou com `CLIPATOR_PESQUISA=0`, segue sem referências e o relato diz isso. O render e o plano sem IA nunca usam a rede. Cada termo fica em cache na pasta do clip.

**Montagem do short: vídeo em tela cheia, painel e destaque** (`curta.montagem`, `render.cadeia_montagem`). Nos layouts `em-cima` e `janela`, o clip não fica dividido do começo ao fim. Cada plano tem `tela`: `dividida` (vídeo e animação) ou `video` (só a pessoa, em tela cheia, até a próxima ilustração). Com o roteiro da IA, ela escolhe; sem IA, frase sem lugar, objeto, placa, efeito ou ação fica em `video`. O clip abre com a pessoa (`GANCHO`, 1,4 s), trecho com menos de `MIN_TRECHO` (1,2 s) assume a tela do vizinho para não piscar, e um trecho de vídeo sim, outro não, entra com o rosto mais perto (`ZOOM_VIDEO`, o corte seco dos shorts). A mistura de vídeo e animação entra deslizando de cima em `TRANSICAO` (0,3 s) e sai subindo. O `destaque` é o momento forte do plano (o número, valor ou percentual dito, ou a palavra-chave): a camada de cenas cobre a tela inteira por 0,9 a 2 s, o número sobe contando até o valor dito e a frase que o explica (`destaque_sub`) aparece palavra por palavra. Sem IA, o destaque é o primeiro número dito no plano. Destaque, como placa, só com palavras ditas no trecho. A mesma conta (`curta.montagem`) alimenta o `curta.js` e o grafo do FFmpeg, então os dois sempre concordam.

**Imagens reais do que a fala cita** (`pesquisa.imagens_reais`, `curta.ligar_referencias`). No roteiro, a IA lista as `entidades`: pessoa, empresa, organização, produto ou tecnologia citada pelo nome, com o `termo` como está na transcrição (mesmo escrito errado) e a `busca` com o nome certo ("Iliasat Skiver" → "Ilya Sutskever"). O Wikidata dá o nome, o tipo e uma linha de contexto em português (sem ela, a descrição da Wikipédia), e a imagem vem do Wikimedia Commons, só com licença livre: foto para pessoa, logo para empresa e produto. Produto sem imagem livre tenta a foto mais relevante do Commons e, depois, o logo de quem faz ("Nvidia B300" → logo da Nvidia). A imagem fica na pasta do clip (`pesquisa/imagens/`, com cache), vai para a cena em que o termo é dito pela primeira vez e o crédito vai para `direcao-arte.json`. No vídeo, um cartão com a imagem, o nome e o contexto entra no painel da arte quando o nome é dito, por `REFERENCIA` (2,6 s); a montagem força a tela dividida nesse trecho. A busca de imagens do Google não é usada: não é aberta a programas, muda sem aviso e devolve imagem sem licença. Para usar uma imagem própria, a mídia do canal (`assets/arte`) continua valendo.

**Estilo sugerido pelo tema** (`sugestao_estilo.py`, rota `.../candidatos/{id}/estilo-sugerido`). Uma conta offline, sem IA: cada estilo de curta tem um perfil de assuntos (produto e hardware no Encaixe Vivo, jogo, código e IA no Pixel em Cena, processo e ciência no Fluxo Facetado, caminho e estratégia na Rota em Foco, lugar, construção e agro no Terreno Vivo, países no Geo em Cena), e a fala e o título do corte somam pontos. O passo 3 mostra o mais indicado, com o motivo e as palavras que pesaram, e um botão para usar.

**Projetos antigos.** Cena sem `curta` continua no motor de um mundo só (`dados/cortes/motor.js`).

## Geo em Cena: mapas reais

Na galeria são cinco recortes da mesma direção, cada um com sua amostra: `arte-geo-em-cena` (tela dividida) e `arte-geo-em-cena-<canto>` (mapa em tela inteira com a janela naquele canto). Só muda o `direcao` do estilo; o painel do clip troca o recorte depois.

`artes/geo.py`, `artes/geografia.py`, `dados/geo/geo.js` e a base Natural Earth em `dados/geo/` (procedência e hashes em `FONTES.json`). Usa o mesmo fluxo das cinco acima, mas cada cena guarda `params.corte` com `lugares` e `pendencias` em vez de objetos.

**Resolvedor.** Nome, id ou código viram uma entidade da base, com nível (continente, país, subdivisão) e país pai. Na fala só contam nomes, com maiúscula; códigos nunca. Sem contexto, subdivisão de uma palavra só e nome que também é cidade ficam pendentes; "estado de", o país na mesma frase ou (fora os homônimos de cidade) o país já citado no clip resolvem. "Cidade de" dá aviso, porque não há camada municipal. Continente é a camada física, nunca soma de países; "América" sozinha é Norte + Sul.

**IA.** Devolve nomes e níveis pelo adaptador, sem coordenadas nem ids. Nome não dito sai, e tudo passa pelo resolvedor. O plano só aceita id que exista na base, e a geometria nunca sai do plano.

**Pendências.** Lugar ambíguo, ausente ou cidade não desenha nada: vira aviso no render e no painel, onde o usuário escolhe entre as opções daquela pendência.

**Mapa.** Em 3D por padrão (`geo3d.js`, three.js): a terra é uma maquete com luz do sol, o lugar citado sobe do chão (bloco extrudado) e projeta sombra, e a câmera inclinada voa de um lugar ao outro, subindo no meio do caminho. Sem three.js, sem WebGL ou com `leve`, o `geo.js` desenha o mesmo mapa em canvas 2D (e `leve` corta a câmera em vez de voar). Os dois são função do tempo e sem rede. O lugar acende na palavra (depois dos cortes internos) e apaga na próxima cena com lugar. A câmera enquadra no `foco` do layout com um fator só para os dois eixos (no 3D, `setViewOffset` põe o ponto olhado no centro do foco), e os rótulos ficam dentro dele. Anéis em longitude contínua, com cópia a ±360°, cuidam do antimeridiano; destaque de continente é a interseção com a terra no 2D e, no 3D, os países cujo miolo fica dentro do continente. Projeção equiretangular ou Mercator, dita na tela. Custo medido sem placa de vídeo: a prévia em meia resolução leva cerca de 3 vezes o tempo do mapa 2D.

## Composição

`composicao.py` calcula uma vez a janela, a faixa da legenda, a área segura e o maior retângulo livre (`foco`). O FFmpeg usa esse retângulo para a janela e o motor usa o mesmo para enquadrar a câmera e posicionar os rótulos, então prévia e exportação não divergem. A janela tem proporção fixa de 3:4, recorta pelo rosto ou mostra o quadro com barras (`janela_encaixe`), com a mesma escala nos dois eixos.

A escolha mora em `layout_arte` no `edicao.json` e entra nas versões da edição. Vem do painel do clip, da galeria (`ajustes.direcao`), da rota `direcao-arte/ajustar` (`composicao`) ou da ferramenta MCP `escolher_composicao`. O canto nunca muda sozinho. `janela_canto` vazio é a posição dos clips antigos, que continuam iguais.

## Tempo das animações

O HyperFrames busca pelo tempo do clip só os elementos HTML. Os de SVG ele busca pelo tempo da composição inteira. Por isso `kit.an()` soma o início da cena (`kit.T0`) ao atraso de toda animação. Quem escrever um renderizador novo deve usar `an()`, `g()` e `traco()`, ou somar `T0` à mão.

O 3D segue o caminho da maquete: relógio CSS (`--t3`) e `window.__timelines`. Cada quadro é recalculado do zero a partir do tempo.

## Conferir

```bash
cd motor && pytest -q tests/test_artes.py
python -m clipator.ferramentas.gerar_amostras arte-anotacao-em-foco   # amostra da galeria
python -m clipator.ferramentas.gerar_demos_artes <pasta>              # clip completo de cada direção, com relatorio.json
python -m clipator.ferramentas.gerar_demos_cortes <pasta> --quadros --videos --segunda  # as cinco guiadas pela fala nos cinco layouts
pytest -q tests/test_curta.py                                         # modo curta e pesquisa (rede simulada)
```

Mudou o desenho de uma direção: suba `VERSAO_RENDERER` em `artes/__init__.py` e gere as amostras de novo. Nas cinco guiadas pela fala, o hash da amostra já inclui o `motor.js` e o léxico: basta gerar de novo. No Geo em Cena, inclui o `geo.js`, o `geo3d.js` e os hashes da base.

## Atlas de percursos em 3D

Com three.js, o atlas vira um mapa de mesa (`atlas-de-percursos` no `tres.JS`): terreno em relevo com água nos vales (ruído de senos pela semente da cena, sem `Math.random`), a rota em tubo que se desenha pelo comprimento, o cursor que chega a cada marco no mesmo segundo em que a nota dele abre e a câmera que acompanha o cursor. As notas numeradas ficam em SVG na lateral (`.so-3d`), e o desenho plano continua como alternativa leve (`.so-2d`). Os tempos saem de `_atlas_rota`, o mesmo cálculo do SVG.
