# Letras de oficina — planejamento de cenas

Use somente quando o host tiver selecionado o id `clipator-arte-letras-de-oficina` e fornecido seu schema de resposta.
Esta referência orienta o planejamento; não solicita código nem instalação.

Ideia visual: Letras em suportes diferentes se encaixam em uma régua de composição, formando uma frase curta.
Composição: Uma linha de base constante, cartões de letras com três materiais e uma palavra final em tinta escura. A frase ocupa até 72% da largura útil, com altura de reserva para acentos.
Movimento permitido: Uma letra por vez chega de uma borda diferente, encosta na régua e é corrigida em 2 px. Quando a palavra fecha, só um cartão troca de material; nada de alternância rápida de todas as letras.

Planeje uma ideia por cena, ancorada em trecho literal da fala e ocorrência específica.
Use as palavras cronometradas e os cortes finais fornecidos pelo host; não invente tempos
absolutos do arquivo original. O host valida ou deriva o intervalo de cada cena.
Mantenha texto curto, dados e nomes já presentes na entrada. Se o campo não couber no schema
recebido, não acrescente uma chave nova. Não retorne HTML, scripts ou comandos.

A paleta e as fontes resolvidas vêm do host. A decoração não muda o conteúdo narrativo.
Não procure mídia na web. Sem mídia necessária, descreva a alternativa disponível:
Cartões de palavras inteiras em vez de letras; manter a régua, os materiais e a leitura.
Se ela não estiver implementada, omita a cena com motivo em campo de aviso suportado.
Evite: Cópias de manchetes de jornais, colagem com texto alheio e efeito estroboscópico de palavra a 10 Hz.
