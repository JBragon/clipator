---
temas:
  geral:
    nome: Podcast, entrevista e história pessoal
    temperatura: quente
    caixa_alta_total: true
    palavras_caixa_alta: 4
  humor:
    nome: Humor e entretenimento
    temperatura: fervendo
    caixa_alta_total: true
    palavras_caixa_alta: 6
    palavras:
    - piada
    - piadas
    - kkk*
    - risada*
    - rir
    - rindo
    - zoeira
    - zoar
    - comedia
    - comediante
    - humor
    - humorista
    - engracad*
    - palhaco
    - standup
    - besteira*
    - imita*
    - resenha
    - bizarr*
    censurar:
    - merda
    - porra
    - caralho
    - puta
    - morreu
    - morte
    - matar
    - droga
  ciencia:
    nome: Ciência e curiosidades
    temperatura: quente
    caixa_alta_total: false
    palavras_caixa_alta: 4
    palavras:
    - ciencia
    - cientista*
    - universo
    - planeta*
    - galaxia*
    - nasa
    - espaco
    - astronom*
    - fisica
    - quimica
    - biologia
    - evolucao
    - dinossauro*
    - alien*
    - ovni*
    - ufo
    - misterio*
    - buraco*
    - estrela*
    - marte
    - lua
    - experiment*
    - teoria*
    - egito
    - piramide*
    - fossil*
    - atomo*
    - telescopio*
    - sacani
  negocios:
    nome: Negócios e finanças
    temperatura: morno
    caixa_alta_total: true
    palavras_caixa_alta: 4
    palavras:
    - dinheiro
    - empresa*
    - empresari*
    - investi*
    - acoes
    - bolsa
    - dolar
    - juros
    - inflacao
    - venda*
    - vender
    - cliente*
    - lucro
    - faturamento
    - negocio*
    - empreend*
    - milionari*
    - bilionari*
    - credito
    - divida*
    - salario
    - startup
    - marketing
    - economia
    - financ*
    - renda
    - patrimonio
  esporte:
    nome: Futebol e esportes
    temperatura: quente
    caixa_alta_total: true
    palavras_caixa_alta: 4
    palavras:
    - futebol
    - jogador*
    - gol
    - gols
    - campeonato
    - copa
    - selecao
    - tecnico
    - treinador
    - flamengo
    - corinthians
    - palmeiras
    - vasco
    - gremio
    - cruzeiro
    - botafogo
    - fluminense
    - libertadores
    - brasileirao
    - clube
    - zagueiro
    - atacante
    - goleiro
    - estadio
    - torcida
    - torcedor*
    - neymar
    - ronaldo
    - messi
    - ronaldinho
    - vampeta
    - nba
    - ufc
    - lutador*
    - olimpiad*
    - penalti*
    - chapecoense
  games:
    nome: Games e lives
    temperatura: fervendo
    caixa_alta_total: true
    palavras_caixa_alta: 6
    palavras:
    - game
    - games
    - gamer
    - stream*
    - minecraft
    - gta
    - fortnite
    - valorant
    - counter
    - console
    - playstation
    - xbox
    - nintendo
    - twitch
    - servidor
    - boss
    - personagem*
    - jogar
    - jogando
    - gameplay
    - speedrun
    - skin*
    - zerar
    - zerei
    censurar:
    - morreu
    - morte
    - matar
    - roubo
    - crime
    - favela
    - porra
  saude:
    nome: Fitness, saúde e mente
    temperatura: quente
    caixa_alta_total: false
    palavras_caixa_alta: 3
    palavras:
    - treino*
    - academia
    - musculacao
    - dieta
    - proteina
    - creatina
    - emagrec*
    - gordura
    - caloria*
    - medico*
    - doenca*
    - ansiedade
    - depressao
    - saude
    - sono
    - hormonio*
    - cardio
    - suplement*
    - nutri*
    - psiquiatr*
    - psicolog*
    - tdah
    - autismo
    - cerebro
    - remedio*
    - cancer
    - cirurgia*
    - bodybuilder*
    - cariani
    - balestrin
  politica:
    nome: Política e notícias
    temperatura: quente
    caixa_alta_total: true
    palavras_caixa_alta: 5
    palavras:
    - politic*
    - governo
    - presidente
    - lula
    - bolsonaro
    - moraes
    - stf
    - supremo
    - congresso
    - deputad*
    - senador*
    - senado
    - eleic*
    - eleitor*
    - voto
    - votos
    - votar
    - partido*
    - esquerda
    - direita
    - ministro*
    - ministerio
    - prefeit*
    - governador*
    - impeachment
    - corrupcao
    - cpi
    - democracia
    - golpe
    - trump
---
Base de referência do Clipator, montada com a pesquisa de 75 canais de cortes brasileiros (docs/pesquisa-titulos-e-thumbnails.md). Vale para todo canal: o Clipator detecta o tema de cada vídeo pela transcrição e usa a seção geral mais a do tema. As seções terminam com o id do tema entre parênteses.

`palavras` são os termos que identificam o tema na transcrição (com * no fim vale como prefixo).
`temperatura`, `caixa_alta_total` e `palavras_caixa_alta` são o que mais rende no tema e só valem
quando o titulos.md do canal não fixa esses valores. `censurar` são as palavras que os canais grandes
do tema escrevem com censura (M0RREU, P*RRADA) para não perder anúncios.
