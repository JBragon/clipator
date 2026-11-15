---
temperatura: auto
formulas: []
palavras_gatilho: []
nunca_usar: []
max_caracteres: 70
emojis: false
---
Títulos do canal. `temperatura: auto` usa a que mais rende no tema de cada vídeo; troque por
morno, quente ou fervendo para fixar. Suas `formulas` vêm antes das da base; use {tema}, {nome},
{numero} e {verbo}. `palavras_gatilho` e `nunca_usar` somam com as da base.

O título pode exagerar a emoção, mas o que ele promete tem que acontecer no clip.

<!-- GUIA DOS PARÂMETROS DO titulos.md

Esta parte é só para você ler: o Clipator apaga os comentários antes de mandar este texto para a
IA. Pode apagar o guia se quiser; ele não muda nada.

COMO ESTE ARQUIVO FUNCIONA
- O cabeçalho (entre as linhas com três tracinhos) é lido pelo motor; o texto abaixo dele só vai
  para a IA, junto com as regras de título.
- O Clipator completa este arquivo com a base de referência do tema de cada vídeo: o que você
  escreve vem primeiro e vale por cima.
- As mudanças valem nos próximos títulos gerados (nova análise, novos candidatos ou "sugerir
  títulos" num clip). Títulos já escolhidos não mudam.

temperatura (padrão auto; valores: auto, morno, quente, fervendo)
  O que é: o quanto o título provoca.
  Como mudar: temperatura: morno
  O que acontece:
  - auto: usa a temperatura do tema detectado no vídeo (por exemplo, humor fica fervendo e
    ciência fica morno).
  - morno: informativo e direto. Sem IA, usa só as fórmulas mornas; com IA, pede opções diretas
    e informativas em vez de sensacionalistas.
  - quente: gancho claro (conflito, revelação, número). Sem IA, usa as fórmulas quentes e depois
    as mornas.
  - fervendo: reação forte, confronto, choque. Sem IA, usa as fervendo e depois as quentes.
  A IA recebe a descrição da temperatura escolhida.

formulas (padrão lista vazia)
  O que é: os seus modelos de título, usados quando não há IA (e mostrados à IA como exemplo).
  Como mudar: uma por linha, com recuo de dois espaços e entre aspas:
    formulas:
      - "{nome} REVELOU o que pensa sobre {tema}"
      - "Ninguém esperava {numero} em {tema}"
  O que acontece: as suas fórmulas são tentadas antes das da base. O motor troca as variáveis:
  - {tema}: o assunto do trecho (a palavra mais específica da fala).
  - {nome}: um nome próprio citado no trecho. Sem nome, a fórmula é pulada.
  - {numero}: um número ou valor dito. Sem número, a fórmula é pulada.
  - {verbo}: hoje vira sempre FALA.
  Cada candidato começa por uma fórmula diferente, para os títulos não se repetirem.

formulas_por_temperatura (opcional; não vem no modelo)
  O que é: fórmulas que só entram numa temperatura.
  Como mudar:
    formulas_por_temperatura:
      quente:
        - "O dia em que {tema} deu ERRADO"
  O que acontece: elas somam com as da base naquela temperatura, depois das suas formulas.

palavras_gatilho (padrão lista vazia)
  O que é: palavras que costumam dar clique no seu público.
  Como mudar: palavras_gatilho: [REVELOU, CHOCANTE, VERDADE]
  O que acontece: vão para a IA com o aviso de que só podem ser usadas quando o clip mostra
  aquilo. Somam com as da base do tema. Sem IA, não têm efeito.

nunca_usar (padrão lista vazia)
  O que é: palavras ou frases que o canal não quer nos títulos.
  Como mudar: nunca_usar: ["você não vai acreditar", "inacreditável"]
  O que acontece: vão para a IA como proibidas, somadas às da base. Os títulos sem IA não são
  filtrados por esta lista; se uma fórmula sua tiver a frase, tire-a da fórmula.

max_caracteres (padrão 70)
  O que é: o tamanho máximo do título.
  Como mudar: max_caracteres: 60
  O que acontece: títulos sem IA são cortados na última palavra que cabe, com reticências. A IA
  recebe o limite; se ela passar mais de 10 caracteres dele, o título é cortado do mesmo jeito.

caixa_alta_total (opcional; valores: true ou false)
  O que é: título inteiro em CAIXA ALTA.
  Como mudar: caixa_alta_total: true
  O que acontece: os títulos sem IA saem todos em maiúsculas e a IA recebe a mesma regra. Sem a
  chave, vale o padrão do tema do vídeo.

palavras_caixa_alta (opcional; número; padrão 2 quando o tema não define)
  O que é: quantas palavras, no máximo, ficam em CAIXA ALTA quando o título não é todo em
  maiúsculas.
  Como mudar: palavras_caixa_alta: 1
  O que acontece: nos títulos sem IA, as palavras em maiúsculas além desse número voltam a ter
  só a primeira letra maiúscula. A IA recebe o mesmo limite. Sem a chave, vale o do tema.

emojis (padrão false)
  O que é: chave reservada. Hoje o motor não lê esta chave, então mudar não tem efeito. Se quiser
  emojis, peça no texto livre abaixo do cabeçalho (vale só com IA).

O TEXTO LIVRE (abaixo do cabeçalho)
  Vai para a IA junto com as regras de título, as fórmulas e a base do tema. Use para o tom do
  canal ("sempre cite o nome do convidado", "nada de palavrão"). Sem IA, não faz nada.
-->
