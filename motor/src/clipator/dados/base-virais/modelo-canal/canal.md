Descreva aqui o canal para a IA: quem é o público, que tipo de momento costuma viralizar e o que
nunca deve virar corte. Exemplo: "Cortes do podcast X. O público quer histórias pessoais fortes e
bastidores; nunca corte a leitura do patrocinador nem piada interna da bancada."

Se deixar assim, a IA usa a base de referência do Clipator para o tema de cada vídeo.

<!-- GUIA DOS PARÂMETROS DO canal.md

Esta parte é só para você ler: o Clipator apaga os comentários antes de mandar este texto para a
IA. Pode apagar o guia se quiser; ele não muda nada.

COMO ESTE ARQUIVO FUNCIONA
- O cabeçalho (entre as linhas com três tracinhos no topo) guarda a identidade do canal e é lido
  pelo motor. O texto abaixo dele vai para a IA, antes de ela escolher os cortes, editar e
  escrever títulos e postagem. É aqui que você descreve público, tom e o que evitar.
- Algumas chaves também mudam pelas telas do app (glossário, estilo padrão, chamada automática).
  O app regrava o cabeçalho quando você muda por lá, e este texto livre continua igual.
- Valor fora das opções faz o editor mostrar o erro na linha da chave.

nome (obrigatório)
  O que é: o nome do canal que aparece no app. A pasta do canal não muda quando você troca o nome
  aqui; para renomear a pasta, use o app.

idioma (padrão pt; valores: pt, en, auto)
  O que é: a língua falada nos vídeos.
  Como mudar: idioma: en
  O que acontece: a transcrição (Whisper) usa essa língua; com auto, vale o idioma das
  configurações do app (que também pode ser auto, e aí o Whisper detecta sozinho). O "Inscreva-se"
  automático sai em português ou inglês conforme o idioma. Só vale para vídeos transcritos depois
  da mudança.

palavras_chave (padrão lista vazia)
  O que é: os assuntos do canal.
  Como mudar: palavras_chave: [futebol, Flamengo, mercado da bola]
  O que acontece: trechos que falam desses termos ganham ponto na nota local (somam com as
  palavras_chave do regras.md), ajudam a escolher o assunto dos títulos sem IA e entram nas tags
  do texto de postagem.

glossario (padrão lista vazia)
  O que é: nomes próprios e termos que o Whisper costuma escrever errado.
  Como mudar: glossario: [Casimiro, Flow Podcast, Nubank]
  O que acontece: a transcrição recebe esses termos como dica e depois troca as grafias parecidas
  pela certa. Também entram nas tags da postagem. Para corrigir um vídeo já transcrito, use
  "corrigir nomes" no projeto; não precisa transcrever de novo.

estilo_padrao (padrão podcast-limpo)
  O que é: o estilo de edição usado quando você cria clips sem escolher um.
  Como mudar: estilo_padrao: amarelo-condensado (o nome de um arquivo da pasta estilos/, sem .md)
  O que acontece: os próximos clips curtos nascem com esse estilo. Os cortes longos usam o estilo
  corte-longo. Um nome que não existe dá erro ao criar o clip.

chamada_automatica (padrão nenhuma; valores: nenhuma, inicio, fim, inicio-e-fim)
  O que é: o sticker animado de "Inscreva-se" sugerido nos clips.
  Como mudar: chamada_automatica: fim
  O que acontece: os próximos clips já vêm com o sticker 1 s depois do começo, perto do fim, ou
  nos dois. Clips muito curtos para caber o sticker ficam sem ele. Você pode tirar na edição.

direcao_de_arte (padrão {} vazio)
  O que é: as cores e fontes da marca do canal, aplicadas por cima da ficha do estilo nas cenas
  animadas (direção de arte).
  Como mudar:
    direcao_de_arte:
      primaria: "#00C2FF"
      destaque: "#FFE600"
      fonte_titulo: Anton
  Chaves aceitas: fundo, superficie, texto, texto_suave, primaria, destaque, fonte_titulo e
  fonte_corpo.
  O que acontece: só muda clips cujo estilo usa direção de arte; os outros ficam iguais.

publico, tom, assuntos, evitar (padrão vazio)
formato_padrao (padrão 9:16)
  O que é: chaves reservadas. Hoje o motor não lê nenhuma delas no cabeçalho, então mudar não tem
  efeito. Escreva público, tom e o que evitar no texto livre, que é o que a IA lê. O formato do
  clip vem do estilo.

O TEXTO LIVRE (abaixo do cabeçalho)
  É a descrição do canal para a IA. Sem IA, não faz nada; a análise usa só a nota local.
-->
