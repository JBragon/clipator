# Atlas de percursos — planejamento de cenas

Use somente quando o host tiver selecionado o id `clipator-arte-atlas-de-percursos` e fornecido seu schema de resposta.
Esta referência orienta o planejamento; não solicita código nem instalação.

Ideia visual: Um atlas claro mostra trajetos e relações entre regiões com um cursor de percurso e notas laterais.
Composição: Mapa vetorial simplificado com no máximo cinco marcos e dois rótulos simultâneos. A escala e o norte só aparecem se a projeção e os dados forem conhecidos.
Movimento permitido: A câmera enquadra os marcos ativos com margem, percorre a rota e pausa antes de abrir cada nota. Regiões mudam de preenchimento por fade, sem piscar.

Planeje uma ideia por cena, ancorada em trecho literal da fala e ocorrência específica.
Use as palavras cronometradas e os cortes finais fornecidos pelo host; não invente tempos
absolutos do arquivo original. O host valida ou deriva o intervalo de cada cena.
Mantenha texto curto, dados e nomes já presentes na entrada. Se o campo não couber no schema
recebido, não acrescente uma chave nova. Não retorne HTML, scripts ou comandos.

A paleta e as fontes resolvidas vêm do host. A decoração não muda o conteúdo narrativo.
Não procure mídia na web. Sem mídia necessária, descreva a alternativa disponível:
Diagrama de pontos e setas com a etiqueta “trajeto esquemático”, sem fronteiras inventadas.
Se ela não estiver implementada, omita a cena com motivo em campo de aviso suportado.
Evite: Território inventado, fronteira como afirmação política automática e expansão de mancha vermelha para insinuar eventos não ditos.
