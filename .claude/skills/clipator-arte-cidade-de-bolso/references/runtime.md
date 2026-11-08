# Cidade de bolso — planejamento de cenas

Use somente quando o host tiver selecionado o id `clipator-arte-cidade-de-bolso` e fornecido seu schema de resposta.
Esta referência orienta o planejamento; não solicita código nem instalação.

Ideia visual: Uma rua de pixels é apresentada como um pequeno palco com planos de profundidade e placas editoriais.
Composição: Quatro planos: céu, fachadas, chão e personagem lateral. A placa de informação é desenhada em resolução normal; o mundo usa uma grade de baixa resolução.
Movimento permitido: Travelling lateral curto que passa por três marcos; o personagem anda com quatro poses discretas e pausa quando o dado aparece. O primeiro plano se move 1,5 vez mais rápido que o cenário distante.

Planeje uma ideia por cena, ancorada em trecho literal da fala e ocorrência específica.
Use as palavras cronometradas e os cortes finais fornecidos pelo host; não invente tempos
absolutos do arquivo original. O host valida ou deriva o intervalo de cada cena.
Mantenha texto curto, dados e nomes já presentes na entrada. Se o campo não couber no schema
recebido, não acrescente uma chave nova. Não retorne HTML, scripts ou comandos.

A paleta e as fontes resolvidas vêm do host. A decoração não muda o conteúdo narrativo.
Não procure mídia na web. Sem mídia necessária, descreva a alternativa disponível:
Camadas 2D Canvas com o mesmo buffer, sprites e paralaxe; retirar volumes 3D.
Se ela não estiver implementada, omita a cena com motivo em campo de aviso suportado.
Evite: Sprites de jogos existentes, profundidade de campo que apaga a informação e transições aleatórias de cenário.
