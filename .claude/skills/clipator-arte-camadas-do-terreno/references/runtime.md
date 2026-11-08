# Camadas do terreno — planejamento de cenas

Use somente quando o host tiver selecionado o id `clipator-arte-camadas-do-terreno` e fornecido seu schema de resposta.
Esta referência orienta o planejamento; não solicita código nem instalação.

Ideia visual: Um bloco isométrico mostra solo, infraestrutura e superfície em camadas que podem deslizar para revelar o que existe entre elas.
Composição: Bloco retangular com três níveis e um canto removível; legenda lateral associa cada cor a um nível. As faces têm diferença de luminosidade, não contorno preto de quadrinhos.
Movimento permitido: A camada superior desliza para a esquerda, a intermediária para a direita e a base fica fixa. Um marcador desce atravessando os níveis e volta ao ponto inicial.

Planeje uma ideia por cena, ancorada em trecho literal da fala e ocorrência específica.
Use as palavras cronometradas e os cortes finais fornecidos pelo host; não invente tempos
absolutos do arquivo original. O host valida ou deriva o intervalo de cada cena.
Mantenha texto curto, dados e nomes já presentes na entrada. Se o campo não couber no schema
recebido, não acrescente uma chave nova. Não retorne HTML, scripts ou comandos.

A paleta e as fontes resolvidas vêm do host. A decoração não muda o conteúdo narrativo.
Não procure mídia na web. Sem mídia necessária, descreva a alternativa disponível:
Faces isométricas SVG com três faixas e offsets idênticos.
Se ela não estiver implementada, omita a cena com motivo em campo de aviso suportado.
Evite: Transformação contínua de morro em mar sem relação com a fala e relevo tratado como dado científico sem fonte.
