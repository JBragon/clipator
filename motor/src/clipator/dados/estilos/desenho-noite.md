---
nome: Desenho animado neon
descricao: Um desenho animado em traço ilustra o que a pessoa fala, em cima; a pessoa embaixo, enquadrada pelo rosto. Noite azul com traço que brilha, bonequinhos e gráficos em neon
objetivo: [abertura, numeros]
formato: "9:16"
reenquadramento: seguir-rosto
motor: ffmpeg
nivel_ia: assistido
requer_ia: true
legenda:
  modo: palavra-a-palavra
  fonte: Montserrat ExtraBold
  tamanho: 60
  cor: "#FFFFFF"
  destaque: "#3AA0FF"
  espessura_contorno: 5
  posicao: centro
  animacao: pop
  max_palavras_por_linha: 3
cartela:
  sugerida: false
direcao:
  layout: em-cima
  modo: desenho
  ficha: noite
  proporcao: 0.5
---

A IA faz três etapas antes do render: analisa o corte (tema e ideias com tempo),
escreve o roteiro do desenho (uma cena a cada poucos segundos, presa à fala) e
compõe cada cena com as peças da biblioteca do Clipator (bonequinhos, objetos,
setas, check e X), balões e dados grandes (número, quadradinhos, barras). Depois
do render, a direção de arte do clip aparece no passo 4 para ajustar e refazer.
