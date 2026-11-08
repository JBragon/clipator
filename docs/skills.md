# Skills do Clipator

Uma skill é uma pasta que muda o jeito como o Clipator (e a IA que você conectou) trabalha num canal. Você importa pela aba **Skills** do app, pela CLI (`clipator skill instalar`) ou pelo Claude Code/Codex via MCP.

## Formato do pacote

```
minha-skill/
  SKILL.md               instruções em Markdown (o corpo vai para a IA)
  clipator-skill.yaml    ficha da skill
  estilos/*.md           opcional: estilos de vídeo que a skill traz
```

`clipator-skill.yaml`:

```yaml
nome: Títulos de 4 palavras
id: titulo-4-palavras        # opcional; padrão é o nome da pasta
autor: Seu Nome
versao: 1.0.0
licenca: MIT
preco: gratis                # ou pago
link_compra: https://...     # obrigatório se for paga
tipos: [titulos, ranking]    # o que a skill faz
descricao: Uma frase sobre o que ela muda.
```

Tipos:

| Tipo | Onde entra |
| --- | --- |
| `titulos` | No pedido de títulos para a IA (ranking, "gerar outros títulos" e MCP) |
| `ranking` | No pedido de ranking dos cortes |
| `thumbnail` | No pedido da frase-gancho e do prompt da thumbnail |
| `estilo` | Os `.md` de `estilos/` aparecem na lista de estilos onde a skill estiver ativa |
| `postagem` | No pedido do texto de postagem para a IA ("Gerar com IA" no passo 5, Publicação). O resumo só entra se tiver prova no corte |
| `fluxo` | Fica disponível para o Claude Code e o Codex em `clipator://skills/<id>` |

Uma skill comum do Claude Code (só `SKILL.md` com `name` e `description`) também é aceita: entra como `fluxo`, com um aviso de que falta a ficha.

## Onde ficam e onde valem

- Instaladas: `~/.clipator/skills/` (ou `$CLIPATOR_SKILLS`). Nunca vão para o workspace nem para este repositório.
- Pastas extras, só leitura: Configurações > "Pastas extras de skills" (por exemplo a `SKILLS/` deste repositório).
- Ativação: no workspace inteiro, num canal ou num projeto. Fica em `.clipator/config.yaml` do workspace, na chave `skills`.

Antes de ativar, o app mostra o que a skill muda (os tipos e os estilos que ela traz). Skills de terceiros não são revisadas pelo projeto.

## Importar e exportar

- Pasta: copia para `~/.clipator/skills/<id>/`.
- `.zip`: aceita a pasta na raiz do zip ou várias skills dentro dele. Recusa caminhos com `..`, links simbólicos e pacotes acima de 200 MB.
- GitHub: `https://github.com/autor/repo` ou `https://github.com/autor/repo/tree/main/pasta`. Baixa o zip do repositório pela API pública do GitHub (é o único momento em que a skill usa a internet).
- Exportar: gera `<id>-<versao>.zip`, pronto para vender ou compartilhar. O Clipator não cobra nem processa pagamento; a venda é direta entre quem cria e quem compra.

## Efeitos sonoros nos estilos

Um estilo (ou o `estilo.md` de uma skill) pode ligar momentos do clip a efeitos sonoros:

```yaml
sons:
  cartela: impacto     # quando a cartela de título entra
  corte: whoosh        # em cada corte interno
  destaque: pop        # nas palavras destacadas da legenda (no máximo uma a cada 2 s)
  inicio: riser
  fim: ding
volume_sons: 0.5
```

Os nomes `whoosh`, `swoosh-reverso`, `impacto`, `riser`, `pop`, `click`, `ding` e `glitch` são sintetizados pelo motor (sem internet e sem direito autoral) e ficam em cache em `~/.clipator/sons`. No lugar do nome, dá para usar o caminho de um arquivo de áudio do canal (`assets/sons/meu-efeito.wav`). Para ouvir antes, o passo 4 tem os botões em "Efeitos sonoros".

## Passos da tela do vídeo

1. **Vídeo:** download, transcrição e análise, com a transcrição embaixo do player.
2. **Cortes sugeridos:** marque os cortes e clique em "Escolher estilo →".
3. **Estilo:** a galeria de todos os estilos (embutidos, do workspace, do canal e das skills), cada um com uma amostra de verdade: alguns segundos renderizados pelo próprio render dos clips num vídeo neutro sintetizado pelo FFmpeg (gradiente animado, sem som e sem direito autoral) com uma fala de exemplo. A amostra toca ao passar o mouse; o cartão mostra formato, motor (ASS ou HyperFrames), nível de IA, sons, cartela e zoom. Clicar abre a prévia grande (com som, se quiser), a ficha do estilo e os ajustes para estes clips: cor do texto e do destaque, fonte, posição da legenda, caixa alta, zoom nas palavras fortes e a intensidade, volume dos efeitos sonoros. "Ver amostra com os ajustes" renderiza de novo; "Prévia com este vídeo" renderiza os primeiros segundos do primeiro corte escolhido, com o rosto e a fala de verdade. "Definir como padrão do canal" grava o `estilo_padrao` no `canal.md`. As amostras dos estilos que vêm com o Clipator já vêm prontas (`motor/src/clipator/dados/amostras/`, com o hash de cada estilo no `indice.json`), então abrir a galeria não renderiza nada. Quem mexe nos estilos embutidos gera de novo com `python -m clipator.ferramentas.gerar_amostras` (só as que mudaram; `--forcar` refaz todas). Estilo do usuário, do canal, de skill, editado ou com ajustes tem outro hash: a amostra é gerada uma vez e fica em cache em `~/.clipator/amostras` (ou `CLIPATOR_AMOSTRAS`). A "Prévia com este vídeo" também fica em cache por corte, estilo e ajustes. Formato, cartela e o "Pedido para a IA" também ficam aqui, e daqui saem os clips ("Criar clips" ou "Renderizar N clips"); os ajustes vão para `ajustes_estilo` no `clip.yaml`.
4. **Clips gerados:** antes do render, cada clip tem o editor de vídeo, título, formato, estilo e o render. Depois de gerado, o formato e o estilo ficam fixos (para mudar, volte ao passo 3 e gere outro clip) e só aparecem o vídeo, o título com "Gerar outros títulos", as thumbnails e a área "Edição com IA": "Melhorar com IA" com as versões, a "Direção de arte do clip", "Editar com IA" e "Renderizar a versão em uso". A edição com IA mantém o estilo e só ajusta. O editor manual continua no código, só fica escondido no clip gerado.
5. **Publicação:** textos e envio.

O botão "Estilos" do topo abre a mesma galeria, para conhecer e editar os arquivos dos estilos.

## Direção de arte (cenas que seguem a fala)

Quatro estilos embutidos misturam o vídeo matriz com cenas animadas que entram quando cada coisa é dita (`direcao.py`):

| estilo | layout | ficha |
|---|---|---|
| Animação em cima | `em-cima`: cenas na parte de cima (altura em `proporcao`), o vídeo seguindo o rosto embaixo | neon |
| Animação de fundo | `fundo`: a pessoa recortada na frente e a animação atrás (`pessoa_escala`, `pessoa_x`) | dossiê |
| Cenas por cima | `sobreposto`: o vídeo inteiro com cartões por cima, longe da legenda | editorial |
| Vídeo na janela | `janela`: a animação ocupa a tela e o vídeo fica numa janela no canto (`janela_escala`) | laboratório |

- **Cenas:** título/gancho, número em destaque (conta até o valor), citação, lista de pontos, comparação (A × B), linha do tempo, local (mapa esquemático), nome na tela (tarja), palavra gigante e alerta. Cada uma cita o trecho da fala que ilustra (`ancora`) e entra quando ele é dito.
- **Planejador:** sem IA, por regras (números e grandezas, anos em sequência, "primeiro, segundo…", "disse que…", nomes próprios, lugares depois de "em/no/na", palavras de alerta e de ênfase), sem duas cenas ao mesmo tempo e com um intervalo mínimo (`densidade`). Com IA, os quatro estilos passam pela mesma pré-produção do desenho animado (análise do corte, roteiro da animação e só então as cenas, seguindo o roteiro e com os tempos dele), e o resultado fica em `direcao-arte.json`. Tudo pelo adaptador (JSON por schema); cada cena devolvida é conferida: a âncora tem de existir na transcrição, número e citação têm de ter sido ditos, nomes e lugares também. Se a IA não montar nada, as regras assumem. Na primeira renderização o planejador põe as cenas no `edicao.json`; depois elas são do usuário (faixa "Cenas" do editor: tipo, texto, itens e tempo de cada uma; apagar todas não faz voltar). "Efeitos com IA" também propõe cenas.
- **Ficha:** paleta (fundo, superfície, texto, texto suave, primária, destaque), duas fontes, o jeito de entrar e os sons de cada tipo de cena (dos efeitos sintetizados de `sons.py`). No estilo: `direcao: {layout, ficha, cores, fontes, ...}`; no canal, `direcao_de_arte:` no `canal.md` sobrescreve as cores e as fontes da ficha em todos os clips do canal.
- **Camada:** as cenas são HTML/CSS renderizado pelo HyperFrames (fundo da ficha quando a animação ocupa a tela, transparente nos cartões por cima). Nos vãos entre as cenas fica só o fundo animado da ficha; o título do clip nesses vãos aparece apenas na Maquete low-poly. Sem HyperFrames, o layout sai só com o fundo e um aviso.
- **Enquadramento do locutor:** nos layouts em cima, de fundo e na janela, o render acha o rosto (MediaPipe, o mesmo do seguir-rosto) e usa a mediana dele no clip: em cima, o vídeo ganha zoom até o rosto ter cerca de 30% da altura da metade de baixo, com o centro a 40% dela; na janela, o mesmo dentro da janela; no fundo, é o rosto (e não a caixa do vídeo) que vai para `pessoa_x`. Com o enquadramento parado no centro, o crop vai para onde o locutor está. A câmera do seguir-rosto continua suavizada (zona morta e mediana móvel); o zoom e a altura não tremem porque usam a mediana. Sem rosto, fica o enquadramento de antes.
- **Recorte (layout de fundo):** se o vídeo foi gravado em fundo verde ou azul, o Clipator detecta e usa `chromakey` + `despill`; senão, recorta a pessoa com o segmentador de selfie do MediaPipe (modelo Apache 2.0, baixado na primeira vez), com a máscara suavizada no tempo e na borda e somindo nas laterais. A máscara fica em cache na pasta do clip (`recorte-*.mkv`); `recorte: oval` usa uma máscara oval fixa.

## Desenho animado (estilos "Desenho animado")

Três estilos embutidos (`direcao: {modo: desenho}`, layout em cima) põem um desenho animado em traço que ilustra o que a pessoa fala, na metade de cima, com a pessoa embaixo: **Desenho animado em cima** (ficha `quadro`: fundo vinho escuro com a cidade em silhueta, etiqueta dourada), **Desenho animado neon** (`noite`: azul com o traço brilhando) e **Desenho animado no caderno** (`caderno`: folha pautada clara). Usam IA (`requer_ia`), em três etapas pelo adaptador (`desenho.py`), cada uma mostrada em "O que está acontecendo":

1. **Análise do corte:** o tema e as ideias que dá para desenhar (dado, comparação, exemplo, pergunta, negação…), cada uma presa ao trecho da fala.
2. **Roteiro do desenho:** uma cena a cada 2 a 5 s, com a etiqueta do tema, o que aparece e acontece, o dado em destaque e a frase de um balão. Cena cuja âncora não está na fala cai fora; os tempos vêm da fala.
3. **Composição:** cada cena vira camadas num palco de 1000 × 860: peças da biblioteca (38 desenhos de traço feitos para o Clipator: pessoa, multidão, casa, prédio, celular, dinheiro, balança, gráficos, check e X, relógio, troféu, alerta…), texto, balão e dados (número grande, grade de quadradinhos em %, barras, linha), com posição, cor (texto, principal, destaque, certo, errado), o segundo em que entra e o jeito (pop, desenha, desliza, cai, cresce, pulsa, treme). A IA só escolhe e posiciona; o desenho é SVG gerado aqui, com todo texto escapado, e o HyperFrames renderiza. Cena sem composição ganha uma padrão.

**Maquete low-poly** (ficha `maquete`, mesmo caminho das três etapas): as mesmas 38 peças em versão facetada, em perspectiva isométrica (`maquete.py`: topo claro, lados em dois cinzas e a parte de destaque na cor da camada, com sombra no chão), sobre um fundo escuro com poeira de luz desfocada que deriva devagar. Cada cena é uma etapa da explicação: uma linha de cabeçalho com o tema ("PASSO A PASSO · …"), o chip com o nome da etapa, os rótulos em cartões presos às peças por um fio, o número num painel escuro e, no fim, um carimbo de conclusão levemente girado. A cada etapa a câmera chega perto devagar e o quadro entra desfocado e ganha foco. Com o three.js instalado (dependência do app), a maquete é 3D de verdade (`maquete3d.py`): as peças são modeladas em low-poly, com material fosco, luz, sombra no chão e uma câmera ortográfica que passeia uns graus e chega perto a cada etapa, com os cartões dos rótulos seguindo as peças. Tudo isso renderiza no HyperFrames com WebGL, quadro a quadro, pelo tempo do HyperFrames. O HUD continua em SVG. Sem o three.js ou sem WebGL, ficam as peças facetadas em SVG.

Tudo fica em `clips/<id>/direcao-arte.json` e as cenas viram itens `cena` do tipo `desenho` no `edicao.json`. No passo 4, depois do render, o painel **Direção de arte do clip** mostra a análise, o roteiro cena a cena (editável: tempo, etiqueta, descrição, dado, balão, tirar cena), as peças de cada cena e as cores. **Refazer com esta direção** recompõe as cenas com o roteiro e as cores do painel (só a etapa 3 roda de novo), cria uma versão nova da edição e renderiza o vídeo; **Refazer do zero** roda as três etapas sem cache. Nos outros estilos de direção de arte, o painel mostra a análise e o roteiro da animação, editáveis do mesmo jeito, além das cenas e das cores; num clip antigo, sem roteiro, refazer roda as três etapas. "Melhorar com IA" mantém o desenho (as cenas comuns que a IA propuser ficam de fora, com o motivo).

## Melhorar com IA e versões (passo 4)

Cada clip do passo 4 tem a caixa "Melhorar com IA": chips de pedidos rápidos (mais dinâmico, menos texto, cenas maiores, seguir mais a fala, mais calmo, mais cenas) e um campo livre. Uma rodada (`melhorar.py`) manda para a IA, pelo adaptador (texto entra, JSON sai): o estilo do clip resumido dentro de 6000 caracteres (legenda, cartela, zoom, sons, a ficha e o layout da direção de arte, o texto do estilo) e as skills ativas de estilo, cenas e fluxo; a fala com o tempo de cada palavra; os momentos de mais energia; as emendas; a zona segura da plataforma; a edição atual e o pedido. A IA devolve o plano inteiro: o que manter, itens novos (cenas citando a fala, efeitos, stickers e chamadas, textos, sons), palavras para a legenda destacar e pausas mortas para cortar. Tudo é conferido: trecho que não está na fala, número ou citação que não foi dito, sticker que não existe, som desconhecido e pausa com fala dentro ficam de fora, com o motivo na lista de versões. As pausas aceitas viram cortes internos do clip, com os tempos dos itens puxados.

Cada rodada vira uma versão (`clips/<id>/versoes-edicao/vN.json`, com o pedido, o resumo do que mudou, o modelo e a hora) e a prévia renderizada fica junto (`vN-previa.mp4`). Edição à mão no editor (gravações seguidas viram uma versão só) e mudança feita pela conversa (MCP `aplicar_edicao`) também viram versão. Na lista: prévia, "Comparar" (as duas lado a lado com o que mudou), "Usar esta versão" e "Voltar para a versão anterior". O render final usa a versão em uso. O `pedido.md` da conversa com o Claude Code ou o Codex leva a ficha do estilo e pede para mudar a edição pelo MCP, então as skills instaladas na CLI do usuário também podem editar o clip.

**Etiqueta "Usa IA":** os quatro estilos de direção de arte (`requer_ia: true` no estilo) e o "Melhorar com IA" só funcionam com a IA integrada. Sem Claude Code nem Codex, eles aparecem desabilitados com a dica e um atalho para as Configurações, e o motor recusa o render com uma mensagem clara, em vez de cair nas regras. Os outros estilos continuam funcionando offline e sem IA. As amostras do passo 3 desses estilos são renderizadas com cenas de exemplo, só para mostrar o visual.

## Editor de vídeo (passo 4)

Cada clip do passo 4 (Clips gerados) tem o botão "🎬 Editor": prévia em cima, biblioteca de efeitos à esquerda, propriedades à direita e a linha do tempo embaixo, com as faixas Vídeo (miniaturas e emendas dos cortes internos), Áudio (forma de onda), Legenda (palavras), Efeitos, Texto, Stickers e Sons.

- A edição fica em `clips/<id>/edicao.json`, um documento não destrutivo: itens com `tipo`, `inicio`, `fim` (segundos do clip) e `params`. Trecho, cortes internos, legenda e estilo continuam no `clip.yaml`; um clip antigo abre com a edição vazia.
- Efeitos: zoom (punch-in), zoom lento, tremor, flash, preto e branco, sépia, contraste, saturação, desfoque, vinheta, transição (mergulho nas emendas), texto sobreposto, emoji (sticker colorido) e efeitos sonoros (`sons.py`). O render monta os filtros do FFmpeg a partir do documento (`edicao.py`), por baixo da legenda e do logo; o texto vai por arquivo (`textfile`), nunca dentro do grafo.
- Clique num efeito para pôr no cursor da linha do tempo, ou arraste até a faixa; passe o mouse para ver na prévia. Arraste os itens para mover, puxe as bordas para mudar a duração (encaixa nas palavras, nas emendas e no cursor). Atalhos: Espaço, J/K/L, S (dividir), Del, Ctrl+Z / Ctrl+Y, setas. Salva sozinho.
- **Efeitos com IA:** a IA configurada (pelo adaptador, texto entra e JSON sai) lê as palavras com os tempos e propõe efeitos; **Sugerir sem IA** faz o mesmo com regras simples (zoom nas palavras fortes, emoji pelo tema, som e transição nas emendas). As propostas aparecem numa lista para aceitar todas, algumas ou descartar; todo tempo é validado contra a duração do clip.
- **Conversa:** a IA da conversa ao lado pode mudar a edição pelas ferramentas MCP `ler_edicao` e `aplicar_edicao`; o editor recarrega sozinho (e avisa se você estava editando ao mesmo tempo).
- **Stickers:** a categoria Stickers da biblioteca tem busca por palavra em português (risada, fogo, dinheiro…), categorias e filtro por pacote. O pacote curado tem 166 stickers do Fluent Emoji da Microsoft (MIT): 68 animados e 98 em 3D, cerca de 170 MB, baixados uma vez por `clipator preparar` (ou pelo botão "Baixar stickers"; `--sem-stickers` pula) para `~/.clipator/stickers`, conferindo o sha256 de cada arquivo; depois disso funciona sem internet. Arquivos em `canais/<canal>/stickers/` (PNG, APNG, WebP ou GIF) entram na biblioteca também. "Buscar na internet" (só ao clicar) procura no Iconify, só em coleções livres (Fluent Emoji, Noto e Twemoji); o que for baixado fica em `canais/<canal>/stickers/web/` com a licença, e o crédito das licenças CC BY entra sozinho na descrição do clip. Propriedades: posição, tamanho, rotação, entrada (pop, surgir, deslizar) e repetir a animação. O render sobrepõe o APNG animado com o FFmpeg (WebP e GIF viram APNG antes). As regras simples e os efeitos com IA também sugerem stickers pelas palavras ditas.
- **Chamadas animadas:** a categoria "Chamadas" fica no topo da biblioteca de stickers: Inscreva-se (o botão aparece, o cursor clica, vira "Inscrito ✓" e o sino balança), Curtir, Ative o sininho, Comente, Compartilhe, Salve o vídeo, Siga, Link na bio, Parte 2 / Continua, Assista até o fim e Curta · Comente · Inscreva-se. São desenhos do próprio Clipator (`cta.py`, Pillow), sem logo nem botão oficial de plataforma, gerados como APNG transparente para cada texto e cor e guardados em `~/.clipator/stickers/chamadas`. No painel: texto (e o texto depois do clique), cores com predefinições (vermelho, preto, branco, neon), idioma (português ou inglês) e o som do clique, que sai sincronizado no render. A prévia desenha a animação quadro a quadro no tempo do item. "Inscreva-se automático" (por canal, `chamada_automatica` no `canal.md`: no começo, no fim ou nos dois) faz as sugestões do editor, com e sem IA, incluírem a chamada.
- **Mover na prévia:** texto, emoji e sticker se arrastam direto no vídeo. Os cantos mudam o tamanho (Shift estica o sticker), a bolinha de cima gira o sticker, as setas do teclado empurram o objeto selecionado (Shift anda mais), há guias de centro e de borda (Alt solta) e a "zona segura" mostra onde a interface das plataformas cobre o vídeo. A posição vai para o `edicao.json` como `x`, `y` (o centro em fração do quadro), com desfazer, e o render usa os mesmos números.
- A prévia ao vivo é aproximada (CSS no navegador; o enquadramento segue o centro, o render segue o rosto). "Prévia renderizada" faz um render rápido em meia resolução e mostra o resultado exato.

## Editar com IA (fora do núcleo)

No passo 4, "Editar com IA" passa um clip para o **seu** Claude Code ou Codex, numa conversa no terminal. É diferente da IA que o motor usa sozinho:

| | IA do motor (ranking, títulos, thumbs, postagem) | Editar com IA |
| --- | --- | --- |
| Quem chama | o motor, pelo adaptador (`ai/adapter.py`) | você, no terminal que o app abre |
| Formato | texto entra, JSON por schema sai, uma chamada | conversa livre; suas skills valem |
| Sem IA | o motor funciona igual (heurísticas locais) | o botão só não aparece |
| Permissões | nenhuma ação no disco | você aprova cada ação no terminal; o Clipator não usa flags que pulem permissões |

Como funciona: o motor cria `clips/<id>/edicoes/<data-hora>/pedido.md` com o contexto do clip (caminhos do `saida.mp4` e do vídeo original, trecho, transcrição, legenda, estilo, plataforma e zona segura, regras do canal, ferramentas do MCP) e as regras: nunca sobrescrever o original nem os arquivos do projeto, gravar o resultado como `saida-editada.mp4` e um `notas.md` nessa pasta. A CLI recebe só uma frase fixa mandando ler esse arquivo, então o texto que você digita nunca passa pela linha de comando.

- **Abrir conversa:** `claude "<frase>"` ou `codex "<frase>"`, na pasta do clip, no painel "Conversa com a IA" do passo 4.
- **Continuar a última conversa:** `claude --continue` ou `codex resume --last` (os dois retomam a conversa mais recente daquela pasta).
- **Copiar prompt:** copia o pedido inteiro para colar onde quiser.

**Conversa dentro do app:** no passo 4 o vídeo original e a transcrição saem da tela e a coluna da direita vira o painel "Conversa com a IA", uma conversa formatada como a extensão do VS Code: balões, markdown com blocos de código, cartões das ferramentas (com o diff das edições), raciocínio recolhível, cartões de permissão com Aprovar / Recusar / Sempre nesta conversa, tokens e custo, e uma caixa de mensagem (Enter envia, Shift+Enter quebra a linha) com chips para anexar o clip, o pedido.md e a legenda.

- **Claude Code:** `claude -p --input-format stream-json --output-format stream-json --verbose --include-partial-messages` (mais `--continue` e `--model`, se escolhidos). Os pedidos de permissão chegam pelo mesmo canal (`control_request` "can_use_tool", com `--permission-prompts host`, o padrão) e o app responde com o clique do usuário. O texto do usuário vai pelo stdin, como JSON.
- **Codex:** `codex app-server` (JSON-RPC por stdin/stdout, o protocolo da extensão do Codex no VS Code), com `approvalPolicy: on-request` e `sandbox: workspace-write`. Os pedidos de aprovação de comando e de arquivo esperam o usuário no chat.
- **Modo terminal:** uma caixa no topo do painel troca para o terminal de verdade (xterm.js na tela e node-pty no processo principal do Electron) rodando a sua CLI interativa, com as suas skills e os pedidos de permissão dela. No topo: a IA, o clip (ou o lote do passo 3), "Nova conversa", "Continuar", "Parar" (encerra a CLI e tudo o que ela abriu) e "Abrir no terminal externo". A barra vertical à esquerda do painel muda a largura (duplo clique volta ao padrão; a largura fica salva) e o painel pode ser recolhido. A conversa continua rodando quando o painel é recolhido ou quando você troca de clip ou de passo; ao voltar, a tela é reposta. Fechar o app encerra todas. O processo principal só aceita `claude` ou `codex` (o executável do PATH ou de `CLIPATOR_CLAUDE` / `CLIPATOR_CODEX`), a frase fixa do motor e uma pasta dentro do workspace. Fora do Electron (`npm run web`) o painel mostra um aviso e o botão do terminal externo.

**Terminal externo:** no Windows é uma aba nova do Windows Terminal (`wt.exe new-tab -d <pasta>`) quando ele existe, ou um console novo (`CLIPATOR_TERMINAL=conhost` força o console). O motor não redireciona a entrada nem a saída da CLI: com elas redirecionadas, a CLI desenhava a tela no pipe do motor e a janela ficava preta.

**Pedido no passo 3 (lote):** no passo 3 (Estilo), ao lado do estilo, "Pedido para a IA" guarda um pedido (`pedido_ia` no `clip.yaml`) nos clips criados. Com "Abrir a conversa quando o render terminar" marcado, quando o render do lote acaba o motor escreve um `pedido.md` por clip e um `edicoes-ia/<data-hora>/pedido-lote.md` na pasta do projeto, e o app abre **uma** conversa para o lote, na pasta do projeto, no painel do passo 4 (um aviso ao lado dos passos leva até ela; o passo não muda sozinho). No passo 4 o clip mostra o pedido, com "Reabrir conversa" (retoma a última conversa da pasta do projeto) ou "Abrir conversa" se ainda não foi aberta; se a conversa não abriu, o motivo aparece ali.

As versões gravadas em `edicoes/` aparecem embaixo do clip. "Usar esta versão" marca o vídeo editado como a saída do clip (`versao` no `clip.yaml`), sem apagar o `saida.mp4`. Se o MCP do Clipator não estiver registrado naquela CLI, o diálogo oferece registrar.
