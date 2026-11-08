---
nome: Gancho em preto e branco
descricao: Abre com os momentos mais fortes do corte em preto e branco, clarão branco e o corte inteiro em cor
objetivo: [gancho, legenda]
formato: "9:16"
reenquadramento: seguir-rosto
motor: ffmpeg
nivel_ia: fixo
legenda:
  modo: uma-palavra
  fonte: Montserrat ExtraBold
  tamanho: 70
  cor: "#EFF445"
  destaque: "#EFF445"
  contorno: "#000000"
  espessura_contorno: 7
  sombra: 2
  posicao: centro-baixo
  altura_relativa: 0.65
  animacao: pop
  italico: true
  escala_destaque: 1.3
  destacar_chave: true
  destacar_numeros: true
cartela:
  sugerida: false
abertura:
  ativa: true
  duracao: 6
  max_trechos: 2
  max_trecho: 4.5
  inicio_minimo: 0.15
  preto_e_branco: true
  contraste: 1.12
  transicao: flash
  duracao_flash: 0.3
---

Formato dos cortes de podcast que prendem nos primeiros segundos: antes do corte, entram 4 a 8 s
das falas mais quentes dele mesmo (às vezes a troca entre os dois convidados), sem cor e com um
pouco mais de contraste. Um clarão branco some quando a cor volta e o corte passa do começo ao fim.

Os ganchos saem da energia do áudio e da fala (gatilhos de gancho, exclamação, pergunta, número e
palavras do assunto), nunca dos primeiros 15% do corte, que o público vê logo depois. Para fixar
os momentos à mão, ajuste no clip `abertura.trechos` com pares [início, fim] em segundos do vídeo
original.

A legenda é uma palavra por vez, amarela, itálica e com contorno preto grosso, um pouco abaixo do
meio da tela; as palavras do assunto e os números saem maiores.
