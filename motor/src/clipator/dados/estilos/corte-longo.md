---
nome: Corte longo
descricao: Vídeo horizontal de 8 a 20 min que abre com o trecho mais forte do corte, com marca d'água
objetivo: [corte-longo]
formato: "16:9"
reenquadramento: original
motor: ffmpeg
nivel_ia: fixo
corte_longo: true
legenda:
  modo: nenhuma
cartela:
  sugerida: false
logo: assets/logo.png
posicao_logo: topo-direita
abertura:
  ativa: true
  duracao: 15
  max_trechos: 1
  max_trecho: 20
  inicio_minimo: 0.1
  preto_e_branco: false
  contraste: 1.0
  transicao: flash
  duracao_flash: 0.3
vinheta: canal
---

Modelo dos canais de cortes grandes: o trabalho está no título, na thumbnail e nos primeiros segundos.

O vídeo abre com o trecho forte, perto de 15 s da fala mais impactante do próprio corte (a que a IA
apontou na análise ou, sem IA, a que a fala e a energia do áudio indicam). Depois entra a vinheta do
canal, se houver uma cadastrada, e o corte começa do início, apresentando o assunto. No passo 3 dá
para trocar o gancho para preto e branco, tirar o gancho e escolher se a vinheta abre o vídeo ou
vem depois do gancho. Os Shorts nunca recebem a vinheta.
