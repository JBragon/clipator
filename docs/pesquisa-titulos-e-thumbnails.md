# Pesquisa de títulos e thumbnails dos canais de cortes

Pesquisa que virou a base de referência embutida do Clipator (`motor/src/clipator/dados/base-virais/`), aplicada a
todo canal e a todo vídeo, sem o usuário escolher nicho.
Coleta de 08/11/2026 sobre os 75 itens de `canais-cortes-youtube-brasil.md`.

## Como foi feita

- **Canal**: busca de canais no YouTube pelo nome da lista; quando a busca errou, o canal foi corrigido à mão
  (MyNews, Galãs Feios, Pablo Marçal Cortes, Meio).
- **Títulos**: os 60 vídeos mais recentes, os 40 Shorts mais recentes e os vídeos do canal entre os 60 mais vistos da
  busca pelo nome dele (ordenada por visualizações). Cerca de 9 mil títulos no total.
- **Thumbnails**: as 12 dos cortes mais vistos e as 8 mais recentes de cada canal (1.385 imagens), lidas em folhas
  de contato.
- **Vídeos**: legendas automáticas dos 3 cortes mais vistos de cada canal; foram lidos os primeiros 35 segundos de
  207 vídeos, para ver como cada corte abre.
- A coleta foi feita com o yt-dlp, sem login, pelo script `pesquisa-canais/coletar.py`. Os dados brutos ficam em
  `pesquisa-canais/` (fora do git, cerca de 550 MB).

### Limites

- Visualizações são números acumulados, não crescimento. Nos vídeos recentes, a contagem que o YouTube mostra em
  português vem arredondada ("88 mil") e não foi usada para ranking; o ranking usa a busca por visualizações.
- Seis itens não deram um canal de cortes confiável (veja a tabela no fim). Itens 11 e 15 caíram no mesmo canal.
- Política: os picos de 2026 são dominados pela eleição; o formato que rende foi registrado, não o lado político.
  Os pacotes não tomam lado.

## O que os cortes mais vistos têm em comum

1. **Título e thumb fazem papéis diferentes.** O título conta o fato na terceira pessoa ("NEGUINHO DO KAXETA LEVOU 7
   TIROS!"); a thumb traz a fala do convidado na primeira pessoa, entre aspas, cortada antes do desfecho ("MEU CARRO
   LEVOU 24 TIROS, 7 PEGARAM EM MIM"). Por isso o `thumb.md` ganhou a opção `citacao`.
2. **A frase da thumb foi dita no vídeo.** Nas legendas, a frase da thumbnail aparece quase literal nos primeiros
   segundos (Podpah: "apanhei do meu pai por 40 minutos"). Isso confirma a regra de ouro do Clipator: a frase vem
   da transcrição do clip.
3. **O corte abre no meio da ação.** Os mais vistos começam na pergunta do apresentador ou no meio da história;
   nenhum começa em saudação. Os que abrem com vinheta, patrocinador ou "sejam bem-vindos" são episódios inteiros e
   lives, não cortes.
4. **CAIXA ALTA domina** em podcast, humor, futebol, games e política. Ciência e saúde usam caixa mista com 3 a 5
   palavras em maiúsculas. Por isso o `titulos.md` ganhou `caixa_alta_total`.
5. **Sujeito + verbo forte + fato concreto.** Verbos que se repetem: REVELA, CONTA, ABRE O JOGO, RELEMBRA, PERDE A
   PACIÊNCIA, DETONA, HUMILHA, ENCARA, RESPONDE, REAGE, EXPLICA, ENSINA.
6. **Pergunta que todo mundo tem**: "COMO SABER SE ALGUÉM ESTÁ MENTINDO?", "O QUE ACONTECEU COM O LUSQUINHA?",
   "ESTAMOS VIVENDO O FIM DOS TEMPOS?".
7. **Autoridade na frente**: PSIQUIATRA, NEUROCIENTISTA, EX-FREIRA, EX-VICIADO, JUÍZA.
8. **Número exato** quando existe: "7 TIROS", "6 TIROS", "47 SEGUNDOS", "15 SINTOMAS", "3 HORAS DE PIADAS".
9. **Censura com números e símbolos** em morte, crime, sexo e palavrão: M0RREU, M0RT3, SUIC***DAS, TR4NS4R, F@VEL4,
   P*RRADA. É o jeito dos canais grandes de manter anúncio; o Clipator já tem o censor (`censor_leetspeak`), e os
   pacotes de humor e games vêm com ele ligado.
10. **Marca no fim** ("| Cortes do Flow") e formato fixo antes dos dois pontos ("CASIMIRO REAGE:", "TENTE NÃO RIR")
    nos canais que viraram série.

## Temperatura do título

| Temperatura | Como é | Onde aparece |
|---|---|---|
| morno | diz o assunto e o ganho, sem exagero | PrimoCast, Os Sócios, PodPeople, Lutz |
| quente | conflito, revelação, pergunta ou número; 1 a 4 palavras de destaque | Flow, Vênus, Inteligência Ltda., Charla, Market Makers |
| fervendo | reação forte, confronto, choque, "KKKK", exclamações | Ticaracaticast, Modder Clips, Coringa, Plantão Brasil |

A base traz fórmulas nas três temperaturas para cada tema. Com `temperatura: auto` (o padrão do canal novo), vale a
do tema detectado no vídeo; o canal pode fixar a sua em `titulos.md`.

## Thumbnails por tema (resumo das folhas de contato)

- **Podcast e entrevistas**: rosto de um lado, fala entre aspas em 3 a 5 linhas do outro, 1 a 3 palavras na cor de
  destaque, foto pequena de quem é citado, fundo escuro e borda fina.
- **Humor**: bancada no auge da risada, manchete em faixa, fogo e cor saturada.
- **Ciência**: imagem do caso ou do objeto de um lado, especialista do outro, frase cortada com reticências.
- **Negócios**: manchete curta no pé ou frase entre aspas, uma palavra em vermelho, imagem do assunto atrás.
- **Futebol**: frase cortada no ponto de virada, branco e dourado, fundo azul-marinho, palavrão com asterisco; em
  react, o rosto reagindo ocupa metade.
- **Games**: arte ilustrada ou rosto do streamer exagerado dentro da cena, manchete de 2 palavras, emoji e seta.
- **Saúde**: especialista sério, pergunta em faixa colorida, número grande em lista de sintomas.
- **Política**: manchete de 2 a 4 palavras no topo com rostos tensos lado a lado, balão de fala com a frase dita, ou
  selo URGENTE.

## Onde isso foi parar no Clipator

Uma base única, sem nicho para escolher. O que a pesquisa achou por nicho virou **tema**: geral (podcast,
entrevista, história pessoal), humor, ciência, negócios, esporte, games, saúde e política.

- `motor/src/clipator/dados/base-virais/`:
  - `temas.md`: os temas, as palavras que identificam cada um na transcrição, a temperatura e a caixa alta que mais
    rendem e as palavras que os canais grandes censuram.
  - `cortes.md`: o que viraliza e como abrir e fechar o corte, por tema.
  - `titulos.md`: fórmulas nas três temperaturas, palavras-gatilho e o que nunca usar, por tema.
  - `thumbs.md`: o padrão das thumbnails, por tema, com exemplos dos canais.
  - `referencias.md`: os títulos reais mais vistos, por tema e por canal.
  - `modelo-canal/`: os arquivos com que todo canal novo começa a pasta `regras-e-textos/`.
- `motor/src/clipator/base_virais.py` detecta o tema de cada vídeo pela transcrição (até dois temas; um assunto
  citado de passagem não conta) e entrega:
  - aos títulos sem IA, as fórmulas do tema na temperatura do canal (ou na do tema, com `auto`);
  - à IA (ranking, títulos e frase da thumbnail), o trecho da base do tema mais o geral, como régua.
- O canal só guarda o que é dele, em `canais/<canal>/regras-e-textos/`: o que estiver lá vale por cima da base.
  Os arquivos da base são lidos a cada uso, então uma atualização do Clipator melhora também os canais antigos.

## Todos os itens da lista

| Item | Referência da lista | Canal analisado | Tema | Corte mais visto encontrado |
|---|---|---|---|---|
| can-01 | Cortes do Flow | Cortes do Flow [OFICIAL] | Podcast e entrevistas | SATANISMO É UM CAMINHO SEM VOLTA? / Cortes do Flow (6,7 mi) |
| can-02 | Cortes Podpah | Cortes Podpah [OFICIAL] | Podcast e entrevistas | JUKANALHA QUASE M0RREU (4,3 mi) |
| can-03 | Cortes Inteligência Ltda. | Cortes do Inteligência [OFICIAL] | Podcast e entrevistas | ESTAMOS VIVENDO O FIM DOS TEMPOS? - RODRIGO SILVA / Cortes do Inteligência Ltda. (7,6 mi) |
| can-04 | Cortes de Vênus | Cortes do Venus [OFICIAL] | Podcast e entrevistas | COMO SABER SE ALGUÉM ESTÁ MENTINDO? / Cortes do Venus (5,3 mi) |
| can-05 | Cortes À Deriva | À Deriva trechos [OFICIAL] | Podcast e entrevistas | Como saber se a pessoa é BOA ou RUIM? / À Deriva Cortes (3,5 mi) |
| can-06 | Cortes Ciência Sem Fim | Cortes do Ciência Sem Fim [OFICIAL] | Ciência e curiosidades | AVIÃO DA MALAYSIA QUE SUMIU  / Cortes do Ciência Sem Fim (4,4 mi) |
| can-07 | Cortes do Achismos | AchismosTV | Ciência e curiosidades | MARCOLA: A HISTÓRIA DO PODEROSO CHEFÃO DO PCC FT. JOEL PAVIOTTI / #ACHISMOS HIST (5,1 mi) |
| can-08 | Cortes PodDelas | Cortes PODDELAS [OFICIAL] | Podcast e entrevistas | FUI MANDADO EMBORA DO MC DONALDS! (2,1 mi) |
| can-09 | Cortes Podcats | Cortes Podcats | Podcast e entrevistas | TESTEMUNHO DE CAMILA LOURES! / DEIVE LEONARDO - Cortes PodCats (509 mil) |
| can-10 | Cortes Ticaracaticast | TICARACATICAST Cortes[OFICIAL] | Humor e entretenimento | ESSA HISTÓRIA É PRA PASSAR MAL DE TANTO RIR (5,0 mi) |
| can-11 | Cortes Não É Nada | CORTES - Leon e Nilce [Oficial] (a busca caiu no canal de cortes do Leon e Nilce (o "Não É Nada" não tem canal próprio de cortes)) | Games e lives | COLOCARAM A GENTE NO JOGO! - Connect the Stars (1,9 mi) |
| can-12 | Cortes Broxada Sinistra | Cortes do Broxada [OFICIAL] | Humor e entretenimento | RONALDINHO ENTREVISTA COMUNISTA JONES MANOEL (1,3 mi) |
| can-13 | Cortes Ben-Yur | Yuri Moraes (Cortes) | Humor e entretenimento | DANIEL MASTRAL CONTA PORQUE FOI ESCOLHIDO @ BEN-YUR CORTES (272 mil) |
| can-14 | Cortes Desce a Letra Show | DESCE A LETRA SHOW - CORTES | fora da análise | SANTINELI VS METAFORANDO: QUEM TÁ CERTO NESSA TRETA? (357 mil) |
| can-15 | Cortes Leon e Nilce | CORTES - Leon e Nilce [Oficial] | Games e lives | COLOCARAM A GENTE NO JOGO! - Connect the Stars (1,9 mi) |
| can-16 | Cortes Groselha Talk | Groselha Talk - Cortes [OFICIAL] | Podcast e entrevistas | COCIELO RINDO DA TRISTE HISTÓRIA DO PAI DO MUCA (1,9 mi) |
| can-17 | Cortes Planeta Podcast | PLANETA PODCAST [OFICIAL] | Humor e entretenimento | VANDINHA LOPES (MÉDIUM) / Planeta Podcast (Sobrenatural) Ep.52 (1,9 mi) |
| can-18 | Cortes Papagaio Falante | Cortes Podcast Papagaio Falante [OFICIAL] | Podcast e entrevistas | ELE FEZ DE TUDO PRA P3GAR A JULIANA PAES / RAUL GAZOLLA (4,9 mi) |
| can-19 | Cortes PodPeople | PodPeople - Ana Beatriz Barbosa | Fitness, saúde e mente | TDAH em Adultos: 15 Sintomas Para Não Deixar Passar (4,6 mi) |
| can-20 | Cortes de Lutz | Cortes do Lutz [OFICIAL] | Podcast e entrevistas | COMO TRANSFORMAR VÍCIOS E MAUS HÁBITOS (NEUROCIENTISTA)  / Lutz Podcast (2,3 mi) |
| can-21 | Cortes PrimoCast | PrimoCast | Negócios e finanças | A HISTÓRIA DE JÓ (Rodrigo Silva) / PrimoCast 241 (9,6 mi) |
| can-22 | Cortes Os Sócios | Os Sócios Podcast | Negócios e finanças | PABLO MARÇAL: HISTÓRIA, NEGÓCIOS E POLÍTICA / Os Sócios 198 (2,1 mi) |
| can-23 | Cortes Market Makers | Market Makers | Negócios e finanças | O MUNDO SE ENGANOU SOBRE O FUTURO DOS CARROS ELÉTRICOS? (2,7 mi) |
| can-24 | Cortes Stock Pickers | Cortes do Stock Pickers [OFICIAL] | Negócios e finanças | Como Zukerman conheceu o Tio Ricco? (57 mil) |
| can-25 | Cortes G4 Podcasts | G4 Podcasts | Negócios e finanças | “EU NÃO DOU AO GOVERNO O DIREITO DE DECIDIR MINHA RELIGIÃO” (269 mil) |
| can-26 | Cortes Joel Jota / Jota Jota Podcast | Joel Jota | Negócios e finanças | IRONMIND: DO QUE SERÁ QUE VOCÊ É CAPAZ? (PABLO MARÇAL E MARCOS PAULO) / JOTA JOT (3,1 mi) |
| can-27 | Cortes Flávio Augusto | O Conselho / Flávio Augusto | Negócios e finanças | VENDAS / COMO VENDER MAIS E MELHOR / O Conselho 01 (4,8 mi) |
| can-28 | Cortes Pablo Marçal | Pablo Marçal Cortes (canal só com Shorts) | Negócios e finanças | — |
| can-29 | Cortes Charla Podcast | Charla Podcast | Futebol e esportes | BASTIDORES INÉDITOS DA TRAGÉDI@ DA CHAPECOENSE (5,0 mi) |
| can-30 | Cortes Flow Sport Club | Cortes do Flow Sport Club [OFICIAL] | Futebol e esportes | DESASTRE AÉREO DA CHAPECOENSE / Cortes do Flow Sport Club (3,5 mi) |
| can-31 | Cortes Denílson Show | Denílson Show | Futebol e esportes | VAMPETA / Podcast Denílson Show #35 (3,1 mi) |
| can-32 | Cortes Podpah de Frente | Cortes Podpah [OFICIAL] | Futebol e esportes | JUKANALHA QUASE M0RREU (4,3 mi) |
| can-33 | Cortes Redação SporTV | Atenção Vascaínos! (canal de cortes do Redação SporTV não encontrado; a busca trouxe outro canal (fora da análise)) | fora da análise | JORNADA DO AV AO VIVO / VASCO DA GAMA X CORITIBA - BRASILEIRÃO 2026 (231 mil) |
| can-34 | Cortes Casimiro | Cortes do Casimito [OFICIAL] | Futebol e esportes | CASIMIRO REAGE A PESADELO NA COZINHA: MAMMA JÚLIA / Cortes do Casimito (17,7 mi) |
| can-35 | Cortes Gaules | Gaules | Games e lives | — |
| can-36 | Cortes Alanzoka | alanzoka | Games e lives | 🫵😂👍 - R.E.P.O COM OS AMIGOS (7,0 mi) |
| can-37 | Cortes Paulinho o Loko | Modder Clips [OFICIAL] | Games e lives | PAULINHO ESTÁ SENDO PROCURADO PELA CIDADE INTEIRA no GTA RP 😂 (Modder Clips) (4,7 mi) |
| can-38 | Cortes Coringa | Cortes LOUD Coringa | Games e lives | CORINGA REAGE: A PRISÃO MAIS SEGURA DO MUNDO, OS MAIS PERIGOSOS ESTÃO AQUI!!! (2,3 mi) |
| can-39 | Cortes Renato Cariani | CarianiTV | Fitness, saúde e mente | NATURAL SEM LIBIDO E TESTO BAIXA - MUZY RESPONDE (505 mil) |
| can-40 | Cortes Ironberg | Cortes Ironberg Podcast (poucos vídeos com contagem confiável) | Fitness, saúde e mente | — |
| pol-01 | Cortes 247 / TV 247 | Cortes 247 | Política e notícias | A GARGALHADA FOI GERAL: "QUE HUMILHAÇÃO", DISSE UM DEPUTADO NA HORA / Cortes 247 (2,6 mi) |
| pol-02 | Cortes do MBL | Cortes do MBL | Política e notícias | RENAN RESPONDE ANITTA AO SER SEGUIDO NO INSTAGRAM / Cortes do @mblivetv (271 mil) |
| pol-03 | ICL Notícias | Instituto Conhecimento Liberta | Política e notícias | ACOMPANHE EM TEMPO REAL A CHECAGEM DO ÚLTIMO DEBATE ENTRE LULA E FLÁVIO - 23/10, (8,4 mi) |
| pol-04 | TV Fórum | Cortes da TV Fórum [Oficial] | Política e notícias | Israelenses invadem praias da BA, agridem pessoas e agem como se fossem donos; e (89 mil) |
| pol-05 | Revista Oeste | Revista Oeste | Política e notícias | OESTE ELEIÇÕES 2026: APURAÇÃO E RESULTADOS AO VIVO / DOMINGO - 25/10 (4,1 mi) |
| pol-06 | Brasil Paralelo | Brasil Paralelo | Política e notícias | ELEIÇÃO 2026 - APURAÇÃO DOS VOTOS / 1º TURNO / AO VIVO (16,3 mi) |
| pol-07 | Os Pingos nos Is | Os Pingos nos Is | Política e notícias | JOVEM PAN CENSURADA - OS PINGOS NOS IS - 19/10/2022 (1,4 mi) |
| pol-08 | Pânico / Jovem Pan | Pânico Retrô | Política e notícias | Bolsonaro TRETANDO no Pânico -  MM #4 (5,9 mi) |
| pol-09 | Jovem Pan News | Jovem Pan News (canal oficial; os mais vistos incluem transmissões esportivas) | Política e notícias | JP ESPECIAL: ELEIÇÕES 2026 / VOTAÇÃO, APURAÇÃO E RESULTADOS AO VIVO - 04/10/26 (5,6 mi) |
| pol-10 | MyNews | MyNews | Política e notícias | DEBATE: DATENA PERDE A CALMA AO SER PROVOCADO POR MARÇAL E PROTAGONIZA CENA POLÊ (1,8 mi) |
| pol-11 | O Meio | Meio (canal oficial do Meio, sem contagem confiável) | Política e notícias | — |
| pol-12 | CNN Brasil | CNN Brasil | Política e notícias | APURAÇÃO: LULA É REELEITO PRESIDENTE DA REPÚBLICA NO 2º TURNO DAS ELEIÇÕES 2026  (16,5 mi) |
| pol-13 | UOL | UOL | Política e notícias | Debate na Globo: Lula x Bolsonaro, quem venceu? Colunistas do UOL analisam ao vi (8,8 mi) |
| pol-14 | GloboNews | globonews (canal oficial da GloboNews (não há canal de cortes separado)) | fora da análise | Lula e Flávio Bolsonaro debatem no bloco de tema livre da Globo (1,6 mi) |
| pol-15 | Poder360 | Poder360 | Política e notícias | Assista aos vídeos da operação policial contra o CV (2,5 mi) |
| pol-16 | Meteoro Brasil | Meteoro Brasil | Política e notícias | METEORO FAZ REACT DA ENTREVISTA DE LULA AO FLOW PODCAST (2,1 mi) |
| pol-17 | Galãs Feios | Galãs Feios | Política e notícias | O PASSADO SECRETO DE MICHELLE BOLSONARO / Galãs Feios (2,0 mi) |
| pol-18 | DCM TV | DCM TV | Política e notícias | Flávio Bolsonaro participa de sabatina na Globo, e DCM faz react; Lula faz live  (1,0 mi) |
| pol-19 | Opera Mundi | Opera Mundi | Política e notícias | Breno Altman DESTRÓI Argumento Olavista: Nazismo NUNCA Foi de Esquerda! (DEBATE  (996 mil) |
| pol-20 | Rede TVT | Rede TVT | Política e notícias | Flávio Bolsonaro chega aos Estados Unidos, diz aliado / Especial TVT News - 27/1 (2,5 mi) |
| pol-21 | Desce a Letra Show | DESCE A LETRA SHOW - CORTES | Política e notícias | SANTINELI VS METAFORANDO: QUEM TÁ CERTO NESSA TRETA? (357 mil) |
| pol-22 | História Pública / Ian Neves | Ian Neves - História Pública (sem contagem de visualizações confiável) | fora da análise | — |
| pol-23 | História Cabeluda / Gustavo Gaiofato | História Cabeluda / Gustavo Gaiofato | Política e notícias | COMUNISTA DEIXA CONSERVADOR SEM RESPOSTA (421 mil) |
| pol-24 | Jones Manoel | Farol Brasil (Jones Manoel) | Política e notícias | Guia de leitura de introdução ao marxismo, por Jones Manoel (127 mil) |
| pol-25 | João Carvalho | João Carvalho (poucos vídeos com contagem confiável) | fora da análise | NANDO Moura X Paulo KOGOS no INTELIGÊNCIA LTDA feat. Rafael MORDENTE / João Carv (234 mil) |
| pol-26 | Humberto Matos | Cortes - Humberto Matos | Política e notícias | MONARK DESCOBRE QUE NOS ESTADOS UNIDOS TUDO É FAKE / CORTE (83 mil) |
| pol-27 | Eduardo Moreira | Eduardo Moreira | Política e notícias | BRASIL VAI ÀS URNAS NO 2º TURNO DAS ELEIÇÕES 2026 - ESPECIAL ELEIÇÕES - ICL ELEI (1,5 mi) |
| pol-28 | José / Portal do José | Cortes do Jozão [OFICIAL] (a busca trouxe o "Cortes do Jozão", de futebol (fora da análise de política)) | fora da análise | Como o Brasil PERDEU uma Copa do mundo em 4 minutos (953 mil) |
| pol-29 | Plantão Brasil | Plantão Brasil (Thiago dos Reis) | Política e notícias | RENAN SANTOS CHAMA DIREITA PRA APOIAR LULA E MATA PLANO DE FLÁVIO BOLSONARO! REV (741 mil) |
| pol-30 | Kim Kataguiri | Cortes do Kim | Política e notícias | ERIKA HILTON FAZ SHOWZINHO E TOMA INVERTIDA DO KIM KATAGUIRI! (1,1 mi) |
| pol-31 | Arthur do Val / Mamãe Falei | Cortes do Mamãe Falei | Política e notícias | ARTHUR E MAURÍCIO MEIRELES DEBATEM LIBERDADE DE EXPRESSÃO / Cortes do @TVdoMBL (501 mil) |
| pol-32 | ANCAPSU | ANCAPSU | Política e notícias | ACOMPANHAMENTO da APURAÇÃO do 2o TURNO (1,4 mi) |
| pol-33 | Fernando Ulrich | Cortes do Ulrich / Oficial | Política e notícias | Aos poucos vão saindo do país / Cortes do Ulrich (92 mil) |
| pol-34 | Cláudio Dantas | Claudio Dantas | Política e notícias | O impacto da carta de Flávio, a divisão da direita e a nova temporada de caça ao (1,2 mi) |
| pol-35 | Caos MBL Cortes | Caos MBL Cortes | fora da análise | — |

