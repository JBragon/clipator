---
citacao: true
---
Regras da thumbnail para a IA. O padrão dos canais de cortes mais vistos já vem da base:

- **Título**: terceira pessoa, o que acontece ("FULANO LEVOU 7 TIROS!").
- **Thumb**: a fala de quem aparece, na primeira pessoa e entre aspas, cortada antes do desfecho
  com reticências ("MEU CARRO LEVOU 24 TIROS, 7 PEGARAM EM MIM..."). É o que `citacao: true` faz.
- Rosto grande num lado com a emoção da fala; do outro, 3 a 5 linhas curtas em caixa alta com 1 a 3
  palavras na cor de destaque. Fundo escuro e liso e o logo pequeno num canto.

Escreva aqui o que for próprio do seu canal (cores, onde fica o rosto, o que evitar).
Coloque thumbnails de referência em ../thumbs/modelos/.
Regra de ouro: o rosto nunca é redesenhado; a thumbnail é montada sobre o quadro real do vídeo.

<!-- GUIA DOS PARÂMETROS DO thumb.md

Esta parte é só para você ler: o Clipator apaga os comentários antes de mandar este texto para a
IA. Pode apagar o guia se quiser; ele não muda nada.

COMO ESTE ARQUIVO FUNCIONA
- O cabeçalho (entre as linhas com três tracinhos) é aplicado direto pelo motor ao desenhar as
  thumbnails, com ou sem IA. O texto abaixo dele só vai para a IA, quando ela escreve as frases.
- As mudanças valem na próxima vez que você gerar as thumbnails de um clip. As já geradas não
  mudam. Cores são escritas em hexadecimal entre aspas, como "#FFE600".
- Valor fora dos limites faz o editor mostrar o erro na linha da chave.

layouts (padrão: rosto-frase, frase-gancho, moldura, rosto-grande)
  O que é: quais modelos de thumbnail o Clipator desenha para cada frase.
  Como mudar: layouts: [rosto-frase, rosto-grande]
  O que acontece: cada layout da lista vira uma variação para você escolher; tirar layouts deixa
  a geração mais rápida e a lista menor.
  - rosto-frase: foto de um lado (ou em cima, no vertical) e a frase do outro, sobre a cor de fundo.
  - frase-gancho: o quadro inteiro escurecido, com a frase grande no meio.
  - moldura: a foto numa moldura branca inclinada sobre o quadro desfocado, com a frase ao lado.
  - rosto-grande: o rosto bem de perto, com a frase numa barra de até 2 linhas.

fonte (padrão Anton)
  O que é: a fonte da frase.
  Como mudar: fonte: Bebas Neue. Embutidas: Anton, Bebas Neue, Bangers, Montserrat ExtraBold e
  Special Elite. Para usar outra, coloque o .ttf ou .otf em ../assets/fontes/ e escreva o nome
  do arquivo (sem a extensão).
  O que acontece: o motor procura primeiro nas fontes do canal e depois nas embutidas. Se não
  achar, usa a fonte padrão do sistema de desenho, bem mais simples.

cor_texto (padrão "#FFFFFF")
  O que é: a cor das palavras da frase.
cor_destaque (padrão "#FFE600")
  O que é: a cor das 1 a 3 palavras destacadas da frase. A IA também recebe essa cor.
cor_fundo (padrão "#111111")
  O que é: a cor lisa atrás do texto no layout rosto-frase.
  Como mudar as três: cor_destaque: "#FF3B30"
  O que acontece: as próximas thumbnails saem com as cores novas.

cor_borda (padrão "#FFE600")
espessura_borda (padrão 14; de 0 a 60 pixels)
  O que é: a moldura em volta de toda a thumbnail.
  Como mudar: espessura_borda: 0 tira a borda; cor_borda: "#FFFFFF" troca a cor.
  O que acontece: a borda é desenhada por cima de todos os layouts.

lado_rosto (padrão direita; valores: direita ou esquerda)
  O que é: de que lado fica a foto nos layouts rosto-frase e moldura, no formato deitado (16:9).
  Como mudar: lado_rosto: esquerda
  O que acontece: a foto vai para o lado escolhido e o texto para o outro.

maiusculas (padrão true; valores: true ou false)
  O que é: a frase em CAIXA ALTA.
  Como mudar: maiusculas: false
  O que acontece: com false, a frase sai como foi escrita.

linhas_max (padrão 4; de 1 a 6)
  O que é: em quantas linhas, no máximo, a frase é quebrada.
  Como mudar: linhas_max: 3
  O que acontece: frases mais longas são cortadas nesse número de linhas, e a IA é pedida a
  escrever frases que caibam nele. Menos linhas deixam a letra maior.

citacao (padrão do modelo: true; valores: true ou false)
  O que é: a frase dita no clip vai entre aspas e, se foi cortada no meio, termina em
  reticências ("EU NÃO QUERIA FAZER ISSO..."), o padrão dos canais de cortes de podcast.
  Como mudar: citacao: false
  O que acontece: com false, a frase sai sem aspas nem reticências. Frases que você mesmo
  escreveu para o clip nunca ganham aspas.

O TEXTO LIVRE (abaixo do cabeçalho)
  Vai para a IA quando ela escreve as frases da thumbnail. Use para o tom ("frase sempre na
  primeira pessoa", "nunca cite valores"). Sem IA, as frases saem das palavras do título e da
  fala, e o texto livre não faz nada.
-->
