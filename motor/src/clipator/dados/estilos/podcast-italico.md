---
nome: Podcast itálico
descricao: Legenda itálica em 2 linhas, cor por quem fala e punch-in a cada 3 a 6 s
objetivo: [legenda]
formato: "9:16"
reenquadramento: seguir-rosto
motor: ffmpeg
nivel_ia: fixo
legenda:
  modo: palavra-a-palavra
  fonte: Montserrat ExtraBold
  tamanho: 60
  cor: "#FFFFFF"
  destaque: "#FFE600"
  posicao: centro-baixo
  altura_relativa: 0.6
  animacao: nenhuma
  italico: true
  max_palavras_por_linha: 4
  linhas: 2
  cores_falantes: ["#FFFFFF", "#FFE600", "#4FC3F7"]
zoom:
  enfase: true
  intensidade: 1.1
  intervalo: [3, 6]
---

Inspirado nos cortes de podcast mais vistos. A cor por falante depende da
identificação de quem fala.
