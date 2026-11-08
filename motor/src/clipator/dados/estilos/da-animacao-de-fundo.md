---
nome: Animação de fundo
descricao: A pessoa recortada (ou no chroma key) na frente e a direção de arte animada atrás
objetivo: [abertura, gancho]
formato: "9:16"
reenquadramento: seguir-rosto
motor: ffmpeg
nivel_ia: assistido
requer_ia: true
legenda:
  modo: palavra-a-palavra
  fonte: Bebas Neue
  tamanho: 74
  cor: "#F3EDE2"
  destaque: "#F5C518"
  espessura_contorno: 5
  posicao: centro-baixo
  animacao: pop
  caixa_alta: true
  max_palavras_por_linha: 3
cartela:
  sugerida: false
direcao:
  layout: fundo
  ficha: dossie
  pessoa_escala: 0.72
  recorte: auto
---

A pessoa vai na frente da animação: se o vídeo foi gravado em fundo verde, o
Clipator usa o chroma key; senão, recorta a pessoa com a segmentação do
MediaPipe (a máscara fica em cache no clip). As cenas aparecem atrás, na metade
de cima, com a ficha "dossiê" (preto de arquivo e amarelo de marca-texto).
