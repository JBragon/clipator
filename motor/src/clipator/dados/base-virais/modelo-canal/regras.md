---
{}
---
Regras livres para a IA ao julgar cortes do seu canal. A base de referência do Clipator já ensina
o que viraliza em cada tema e como abrir o corte (na pergunta ou no meio da história, nunca na
saudação ou no patrocinador). Escreva aqui só o que for diferente no seu canal.

<!-- GUIA DOS PARÂMETROS DO regras.md

Esta parte é só para você ler: o Clipator apaga os comentários (tudo entre os sinais de abrir e
fechar comentário) antes de mandar este texto para a IA. Pode apagar o guia se quiser; ele não
muda nada.

COMO ESTE ARQUIVO FUNCIONA
- O bloco entre as duas linhas com três tracinhos no topo é o cabeçalho. O motor aplica cada
  chave dele direto, com ou sem IA. Escreva no formato "chave: valor", uma por linha.
- O texto depois do cabeçalho é a regra livre: só vai para a IA, quando ela está ligada.
- Chave que você não escrever fica no padrão. Se o cabeçalho tiver só {}, vale tudo no padrão.
- As mudanças valem na próxima análise (ou ao gerar os candidatos de novo). Cortes já
  analisados não mudam sozinhos.
- Se existir um regras.md na raiz do workspace, ele vale para todos os canais e este, do canal,
  vale por cima dele, chave a chave.
- Valor fora dos limites abaixo faz o editor mostrar o erro na linha da chave, e a análise do
  canal para até você corrigir.

DURAÇÃO DOS SHORTS (cortes verticais)

duracao_min (padrão 40; de 5 a 600 segundos)
  O que é: o tamanho mínimo de um Short.
  Como mudar: duracao_min: 30
  O que acontece: trechos mais curtos que isso nem viram candidato. Na nota, um corte exatamente
  na mínima perde 30% em relação a um que está na duração ideal. Com IA, ela também não pode
  encurtar um corte para menos que isso (tolerância de 3 s).

duracao_max (padrão 180; de 10 a 1200 segundos; precisa ser pelo menos 5 s maior que a mínima)
  O que é: o tamanho máximo de um Short. 180 s é o limite do YouTube Shorts.
  Como mudar: duracao_max: 60 (por exemplo, para TikTok ou Reels mais curtos)
  O que acontece: o motor para de alongar o corte nesse ponto. Entre a ideal e a máxima o corte
  perde só até 5% da nota. A IA recebe essa faixa no pedido.

duracao_ideal (padrão 90; de 5 a 1200 segundos; ou vazio)
  O que é: a duração que os cortes tentam atingir.
  Como mudar: duracao_ideal: 60. Para deixar automático, escreva duracao_ideal: null; aí o alvo
  fica a 75% do caminho entre a mínima e a máxima (com 40 e 180, isso dá 145 s).
  O que acontece: cortes perto desse valor ganham a nota cheia; abaixo dele a nota cai mais rápido
  do que acima (corte curto demais deixa a ideia pela metade). Um valor fora da faixa
  mínima-máxima é puxado para dentro dela.

duracao_max_fechamento (padrão vazio; de 10 a 1500 segundos)
  O que é: quanto um Short pode passar da duração máxima, só para fechar o assunto.
  Como mudar: duracao_max_fechamento: 200. Vazio (null) ou menor que a máxima desliga.
  O que acontece: o motor aceita um corte maior que duracao_max só quando o fim dele fecha bem o
  assunto (conclusão, sem pergunta no ar). Esse corte perde até 12% da nota por passar do máximo.
  A IA também pode estender o corte até esse teto.

CORTE LONGO (vídeo 16:9 de vários minutos)

corte_longo_min (padrão 480; no mínimo 120 segundos)
corte_longo_max (padrão 1200; no máximo 3600 segundos)
  O que é: a faixa de duração dos cortes longos (8 a 20 min no padrão).
  Como mudar: corte_longo_min: 300 e corte_longo_max: 900
  O que acontece: os cortes longos só são gerados quando a análise pede corte longo. Eles juntam
  blocos inteiros de assunto que caibam nessa faixa, e o alvo é o meio dela. Nos cortes longos o
  gancho pesa menos (40% do peso) e as palavras-chave pesam mais (150%).

QUANTIDADE E IA

quantidade (padrão 8; de 1 a 50)
  O que é: quantos cortes você quer por vídeo.
  Como mudar: quantidade: 12
  O que acontece: a lista de candidatos curtos guarda o triplo disso (no mínimo 15), para você ter
  opções. Os cortes longos guardam esse número (no mínimo 3).

modo_ia (padrão economico; valores: sem-ia, economico, completo)
  O que é: quanto a IA participa da escolha dos cortes.
  Como mudar: modo_ia: sem-ia
  O que acontece:
  - sem-ia: só a nota local do motor. Nada vai para a IA; funciona offline.
  - economico: o motor escolhe os candidatos e a IA só reordena os melhores (veja
    candidatos_para_ia), dá nota, ajusta o começo e o fim e escreve os títulos.
  - completo: a IA lê a transcrição inteira em blocos, propõe trechos próprios, e depois faz o
    mesmo do econômico. Gasta bem mais uso da IA.
  O modo escolhido na tela de análise, quando há um, vale por cima deste.

candidatos_para_ia (padrão 20; de 1 a 60)
  O que é: quantos dos melhores candidatos locais a IA recebe para avaliar.
  Como mudar: candidatos_para_ia: 30
  O que acontece: mais candidatos dão mais chance de a IA achar um bom corte que a nota local
  subestimou, mas o pedido fica maior e mais lento. Os que ficam de fora mantêm a nota local.

nivel_ia (padrão assistido; valores: fixo, assistido, autoral)
revisao_cruzada (padrão false)
  O que é: chaves reservadas. Hoje o motor não lê nenhuma das duas no regras.md, então
  mudar não tem efeito. (O nivel_ia que muda a edição é o do estilo, não este.)

PESOS DA NOTA LOCAL

pesos (um bloco com oito números)
  O que é: quanto cada sinal conta na nota de 0 a 100 de cada candidato. Os pesos são relativos:
  o motor divide pela soma, então dobrar todos não muda nada; o que importa é a proporção.
  Como mudar: escreva o bloco com recuo de dois espaços e mude só o que quiser:
    pesos:
      gancho: 30
      reacoes: 0
  Peso 0 desliga o sinal. Os que você não escrever ficam no padrão.
  Os sinais:
  - gancho (padrão 20): o começo do corte prende (pergunta, revelação, frase forte nos primeiros
    segundos).
  - energia (padrão 15): a voz está mais intensa que a média do vídeo.
  - reacoes (padrão 10): picos de som sem fala por cima, como risadas e gritos.
  - ritmo (padrão 15): fala densa, sem pausas longas nem enrolação.
  - historia (padrão 20): começa e termina em frase completa.
  - palavras_chave (padrão 10): fala das palavras-chave do canal e dos termos que mais se
    destacam no vídeo.
  - plataforma (padrão 10): sinais do YouTube, como o trecho mais repetido e o início de capítulo.
  - fechamento (padrão 25): o corte termina numa conclusão, sem pergunta no ar, antes de mudar de
    assunto.
  O que acontece: os candidatos são reordenados na próxima geração. Sem dados da plataforma, o
  peso de plataforma é ignorado; sem análise de áudio, energia e reacoes também.

FILTROS E TEXTOS

palavras_chave (padrão lista vazia)
  O que é: termos do seu canal que valem ponto quando aparecem na fala.
  Como mudar: palavras_chave: [investimento, bitcoin, renda fixa]
  O que acontece: cada aparição conta em dobro no sinal palavras_chave e aparece nos motivos do
  corte ("Fala de: ..."). Os termos também ajudam a escolher o assunto dos títulos sem IA. Somam
  com as palavras_chave do canal.md.

temas_proibidos (padrão lista vazia)
  O que é: palavras ou expressões que nunca podem estar num corte.
  Como mudar: temas_proibidos: [patrocinador, cupom de desconto]
  O que acontece: todo candidato cuja fala contém um desses termos (palavra inteira, sem ligar
  para acento nem maiúscula) é descartado antes do ranking. A lista também vai para a IA.

trava_titulo (padrão true; valores: true ou false)
  O que é: a regra de que o título pode exagerar a emoção, mas tudo o que ele promete precisa
  acontecer no clip.
  Como mudar: trava_titulo: false
  O que acontece: ligada, a regra vai no pedido para a IA, os títulos da IA que citam algo dito no
  clip vêm primeiro, e o texto de postagem avisa quando o título promete algo que não aparece na
  transcrição. Desligada, nada disso acontece.

censor_leetspeak (padrão false; valores: true ou false)
palavras_censuradas (padrão lista vazia)
  O que é: troca uma letra das palavras sensíveis por número nos títulos (VIOLÊNCIA vira
  VIOL3NCIA), para fugir de filtro de plataforma.
  Como mudar: as duas juntas:
    censor_leetspeak: true
    palavras_censuradas: [morreu, violência, arma]
  O que acontece: os títulos locais, os da IA e os sugeridos para um clip passam pela troca.
  Só funciona com as duas chaves preenchidas. Não mexe na legenda nem no áudio.

O TEXTO LIVRE (abaixo do cabeçalho)
  Vai para a IA como "Regras do canal" no ranking e na edição. Use para o que não cabe numa
  chave, como "prefira histórias com começo, meio e fim" ou "nunca corte a leitura de
  comentários". Sem IA, o texto livre não faz nada.
-->
