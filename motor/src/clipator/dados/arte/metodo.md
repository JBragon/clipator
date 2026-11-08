# Direção de arte do canal: o método completo

A direção de arte (DA) é a fonte de verdade visual do canal. Ela mora em `canais/<canal>/arte/direcao.yaml`
e todo o resto lê dela: legenda, cartela, cenas animadas, thumbnail e o tratamento de cor do vídeo. Quem
muda a DA muda tudo de uma vez; quem escreve cor ou fonte à mão num estilo cria um clip órfão.

Seu papel aqui é o de um diretor de arte que trabalha com a pessoa: você propõe, mostra, ouve e ajusta.
**Quem decide e aprova é a pessoa.** Nunca chame `arte_aprovar` (ou `clipator arte aprovar`) sem um "sim"
dela depois de ver a prancha.

Tudo funciona pela CLI (`clipator arte …`) e pelo MCP (ferramentas `arte_*`). Os nomes abaixo citam os dois.
O resumo que vai no prompt de cada clip é a skill `direcao-de-arte`; este é o texto inteiro.

---

## 0. Quem escolhe a DA

O estilo escolhe a DA (`arte:` no cabeçalho dele) e ela guia a IA ao planejar o corte; o canal só põe a marca
por cima (`arte/marca.yaml`: cores da marca, fontes, logo). Na maior parte das vezes o trabalho é **escolher**
o predefinido certo para o estilo e ajustar a seção `cenas` dele, não criar uma DA do zero. Use
`arte_guia` para ver o que um estilo usa e o texto exato que a IA recebe. Os passos abaixo valem quando a
pessoa quer uma DA nova: própria do canal (`arte: canal`) ou salva como predefinido pessoal.

## 1. Antes de mexer: entenda o canal

Leia `canal.md` e, se existir, `arte/DA.md` (`arte_ler`). Depois faça à pessoa no máximo cinco perguntas,
de uma vez, e só as que o canal não responde sozinho:

1. Sobre o que é o canal e quem assiste (idade, celular ou TV, de dia ou de noite)?
2. Três canais, filmes, revistas ou marcas cujo visual ela admira, e o que exatamente ela gosta em cada um.
3. Algo que ela não quer de jeito nenhum (uma cor, um clichê do nicho, um tipo de letra).
4. Já existe marca: logo, cor, fonte? Ela é intocável ou pode evoluir?
5. O tom em três adjetivos (ex.: "sério, investigativo, urgente" ou "leve, curioso, didático").

Se a pessoa tiver pressa, pule para o passo 3 com o predefinido mais próximo e diga qual escolheu e por quê.

## 2. Referências: olhe antes de inventar

Peça imagens (prints de vídeos, capas, pôsteres) e guarde em `arte/referencias/`. Vídeos também servem.
Rode `arte_extrair_referencias` (ou `clipator arte extrair CANAL`). Ele devolve, por imagem:

- as cores dominantes e a fração da área de cada uma (agrupadas em Lab, que é como o olho agrupa);
- os acentos: cores saturadas que ocupam pouco espaço mas chamam o olho;
- o valor médio (escuro, médio, claro), a temperatura e uma estimativa de grão;
- uma folha `referencias_folha.png` com tudo lado a lado.

**Os candidatos são proposta, não regra.** Use a leitura para conversar: "as três referências são escuras
com um único acento quente; quer seguir por aí?". Nunca copie a paleta de uma marca de terceiros inteira;
tire dela o princípio (valor, contraste, quantidade de acento), não os hex.

Anote em `conceito.referencias` o que tirar de cada uma (`nota: "o vermelho de carimbo, só nos números"`).

## 3. Rotas: duas ou três DAs realmente diferentes

Escolher entre extremos é muito mais fácil do que avaliar uma proposta só. Crie de duas a três rotas
(`arte_rotas acao=criar` / `clipator arte rotas CANAL criar rota-a --base <predefinido>`) que variem
**um eixo forte cada**:

| Eixo | Exemplo de rota A | Exemplo de rota B |
| --- | --- | --- |
| Valor | escura, acento neon | clara, papel e tinta |
| Material | arquivo, carimbo, papel | painel, dados, grade |
| Tipografia | condensada e alta | arredondada e larga |
| Movimento | seco, cortes, sem passar do ponto | elástico, com overshoot |
| Tratamento | grão e vinheta, foto lavada | limpo, saturado |

Uma rota que difere da outra só no tom de azul não é rota, é ajuste. Dê a cada uma uma `conceito.frase`
que um motion designer entenderia sem imagem ("Arquivo vazado: papel envelhecido, carimbo vermelho, texto
batido à máquina").

Gere a comparação (`arte_rotas acao=comparar com_atual=true`) e mostre `arte/rotas/comparacao.png`.
Quando a pessoa escolher, `arte_rotas acao=adotar nome=rota-b`: a DA anterior vira backup
(`direcao.yaml.bak-<data>`) e abre-se uma nova revisão.

Os predefinidos de partida (`arte_presets`): `base`, `arquivo-confidencial`, `palco-noturno`, `manchete`,
`fliperama`, `caderno-de-aula`, `tela-de-dados`, `documental`. A pessoa pode salvar a DA do canal como
predefinido pessoal (`clipator arte salvar-preset CANAL nome`) e usá-la em outros canais.

## 4. Refine o direcao.yaml

O arquivo só precisa ter o que difere do predefinido em `herda`. O dicionário completo dos tokens está em
`docs/direcao-de-arte.md`. As decisões que mais pesam, na ordem:

### Cor
- Dez cores obrigatórias com papel fixo: `fundo`, `superficie`, `texto`, `texto_suave`, `primaria`,
  `secundaria`, `destaque`, `positivo`, `negativo`, `alerta`. O nome é o **papel**, não a cor: `primaria`
  é "o que o espectador precisa lembrar", seja vermelho ou verde.
- Regra 60-30-10 como ponto de partida: o fundo domina, a superfície organiza, a primária aparece pouco.
  Se tudo é primária, nada é.
- Contraste mínimo (o validador cobra): texto sobre fundo 4,5:1; texto grande, legenda com contorno e
  grafismo 3:1. A legenda pede mais, porque passa por cima de vídeo que você não controla.
- Primária e destaque precisam ser distinguíveis (ΔE ≥ 3, e de preferência bem mais). Duas cores quase
  iguais com nomes diferentes confundem quem edita.
- `serie` (gráficos): seis cores ou mais, vizinhas bem diferentes entre si e legíveis sobre o fundo.
  Ordene da mais importante para a menos; a primeira linha de um gráfico é a que a pessoa lê primeiro.
- Gradiente só com paradas realmente diferentes; um gradiente entre dois tons quase iguais é ruído.

### Tipografia
- Duas famílias no máximo. Um título com personalidade e um corpo que se lê em 0,3 s no celular.
- Os papéis `titulo`, `subtitulo`, `corpo`, `dados`, `legenda` são obrigatórios. Números e preços ficam
  em `dados` (prefira uma fonte com algarismos de largura igual, para contadores não "dançarem").
- Caixa alta pequena pede espaçamento positivo (0,06 a 0,15 em). Caixa alta grande e condensada, quase zero.
- A escala é fração do lado menor. No celular, abaixo de ~0,022 (≈ 9 pt) ninguém lê; a legenda não deve
  ficar abaixo de 0,04 e o confortável é a partir de ~0,052.
- A fonte precisa existir em `arte/fontes/`, `assets/fontes/` do canal ou na pasta de fontes do Clipator.
  O validador avisa quando não acha. Use só fontes com licença que permita uso em vídeo (OFL é o caso comum).

### Legenda
- `estilo`: `karaoke` (a palavra falada acende), `palavra` (uma palavra por vez) ou `bloco` (frase inteira).
- Proteção é obrigatória: contorno, sombra ou caixa. Sem nenhum, o validador avisa (e com razão: vídeo claro apaga a legenda).
- `y_vertical` padrão 0,62: acima da faixa de botões e da descrição das plataformas. O validador confere
  contra a zona segura do pior caso (Shorts, Reels e TikTok juntos) e contra a tarja de nome.
- Máximo de 2 linhas e 3 a 5 palavras por linha. Legenda longa vira leitura, e leitura tira o olho do rosto.

### Movimento
- Curvas `entrada`, `saida`, `enfase`, `suave` e durações `micro`, `curta`, `media`, `longa` são obrigatórias.
- Entrada desacelera no fim (sai rápido, chega devagar); saída acelera (sai sem cerimônia).
- Overshoot (passar do ponto e voltar) é personalidade: combina com canal lúdico, atrapalha canal sério.
- Uma entrada por tela. A forma entra antes do texto e sai depois dele. Escalonamento de 0,04 a 0,1 s.
- Escreva `principios` como frases que dá para conferir num quadro ("nada gira", "texto nunca pisca").

### Tratamento do vídeo
- Desligado por padrão (`aplicar_nos_clips: false`). Ligue só quando a pessoa quiser que o vídeo da fonte
  ganhe a cara do canal. Seja sutil: contraste 1,03 a 1,1, saturação 0,85 a 1,1, grão 3 a 6, vinheta 0,3.
- Um LUT `.cube` em `arte/luts/` com `intensidade_lut` abaixo de 1 costuma ser melhor que o LUT cheio.
- Pele é o juiz: se o rosto ficou laranja, verde ou cinza, volte.

### Thumbnail
- Até 4 palavras, num papel de título, grande (0,15 a 0,22 da altura).
- O canto do selo de duração fica livre (`canto_reservado`). O validador e a prancha mostram essa área.

### Som
- `loudness` alvo −14 LUFS e pico −1 dBTP servem às três plataformas. Efeitos baixos (`volume_efeitos`
  0,3 a 0,5): o som marca a entrada, não compete com a voz.

### Conceito
- `frase`, 4 a 8 `palavras_chave`, `faca` e `nao_faca` concretos. "Ser moderno" não é regra; "nenhum
  cartão com sombra; profundidade só por cor" é.

## 5. Valide, compile e mostre

1. `arte_validar` / `clipator arte validar CANAL`. Erro bloqueia; aviso merece conversa; nota é dica.
   Cada achado vem com "como corrigir": em contraste, ele sugere o hex mais próximo que passa.
2. `arte_compilar`: gera `arte/build/da.css` (variáveis `--da-*` e classes `.da-titulo`, `.da-corpo`…),
   `arte/build/da.resolvida.json` e `arte/DA.md`.
3. `arte_prancha` / `clipator arte prancha CANAL [--referencia quadro.png]`: gera `arte/prancha.png` com
   paleta, série, gradientes, tipografia e escala, um quadro 9:16 com zonas seguras, legenda e tarja, um
   1:1, as curvas de movimento, a thumbnail com o canto reservado e as regras. Com `--referencia`, a
   legenda e a tarja aparecem sobre um quadro real do vídeo: é o teste mais honesto.

**Mostre a prancha à pessoa** e pergunte o que ela sente, não só se aprova. Ajuste e gere de novo.

## 6. Aprovação e revisões

- Só depois do "sim": `arte_aprovar confirmar=true` (`clipator arte aprovar CANAL`, `--estrito` recusa se
  houver avisos). A aprovação grava a identidade da DA (um sha de tudo que muda o visual, inclusive os
  arquivos de fonte, LUT e logo) em `arte/estado.json` e carimba a prancha.
- Mudou a DA depois de aprovada? `validar` e `conferir` acusam. Abra uma revisão (`arte_revisar motivo=…`),
  gere a prancha e aprove de novo. O histórico fica em `estado.json`.
- Anotações em chaves `x_…` ou `_…` não mudam a identidade: use para lembretes.

## 7. Aplicar nos estilos e nas cenas

- Num estilo (`.md` com cabeçalho YAML), escreva `da:<token>` no lugar do valor:
  `cor: "da:texto"`, `destaque: "da:primaria"`, `fonte: "da:legenda"` (papel vira família).
  Vale para campos de cor e de fonte; tamanhos saem da DA com `legenda: {da: true}`.
- `legenda: {da: true}` preenche com a DA tudo o que o estilo não escreveu (fonte, tamanho, cores, contorno,
  sombra, caixa, posição, modo). O mesmo vale para `cartela: {da: true}`. O que o estilo escreveu vence.
- Nas cenas animadas, `direcao.ficha: canal` usa a DA do canal como ficha (cores e fontes das cenas). Se o
  estilo não ajustou cores, a DA do canal já entra por cima da ficha escolhida.
- Em HTML/CSS de templates, use as variáveis: `color: var(--da-cor-texto)`,
  `background: rgba(var(--da-cor-fundo-rgb), .85)`, `font-family: var(--da-fonte-titulo)`.
- Cor de foto, logo de terceiros ou print? Marque a linha com `/* da-livre */` (ou `<!-- da-livre -->`).
- `arte_lint` / `clipator arte lint CANAL` acha cor e fonte escritas à mão e sugere o token mais perto (com ΔE).

Cada render feito com a DA deixa ao lado do vídeo um carimbo `<saida>.arte.json` com a revisão e o sha.

## 8. Antes de publicar

`arte_conferir` / `clipator arte conferir CANAL`: DA válida e aprovada, estilos sem valor solto e clips
renderizados com a DA atual. Clip feito com uma DA diferente é erro; clip sem carimbo é aviso. Rode de novo
o render dos que ficaram para trás.

## Ritmo das cenas (continua valendo)

- Uma ideia por tela. Se a frase tem duas ideias, são duas cenas ou uma lista.
- Pouco movimento: a cena entra, fica parada o tempo de ler e sai. Movimento contínuo cansa.
- Texto curto: título até 6 palavras, rótulo até 8, item de lista até 5. A tela resume, não inventa.
- O destaque aparece no máximo uma vez por cena.
- Nada na zona que a plataforma cobre (botões à direita, legenda e nome embaixo).

## Atalho sem DA

Canal sem `arte/direcao.yaml` continua funcionando como antes: a ficha do estilo (`neon`, `dossie`,
`editorial`, `laboratorio`) e a chave `direcao_de_arte` do `canal.md` (`primaria`, `destaque`,
`fonte_titulo`…) ajustam as cenas. Os `da:<token>` de um estilo usado nesse canal saem com os valores do
predefinido `base`.
