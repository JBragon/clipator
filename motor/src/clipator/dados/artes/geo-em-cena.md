# Geo em Cena — planejamento de cenas

Use somente quando o host escolheu esta direção e forneceu o schema de resposta.

Ideia visual: O mapa aproxima de continentes para países e subdivisões reais, destacando somente os lugares mencionados na fala.
Ação: cada cena marca os lugares citados naquele trecho; o mapa acende o polígono real e aproxima no segundo em que o nome é dito.

Os mapas vêm de uma base local. Você só devolve os nomes como foram ditos, o nível (continente, país, subdivisão ou cidade) e o país pai: nunca coordenadas, contornos ou ids. São Paulo pode ser cidade ou estado: se a fala não permitir saber, deixe o nível vazio. Geórgia pode ser o país ou o estado dos EUA: não escolha por semelhança. O exemplo do estilo não é modelo de conteúdo: nunca repita Brasil, São Paulo ou Minas Gerais se a fala não os citar. Cada cena fica presa a um trecho literal e à ocorrência dele. Não acrescente número, população, evento, rota ou fato que não foi dito. Não retorne HTML, scripts ou comandos.
