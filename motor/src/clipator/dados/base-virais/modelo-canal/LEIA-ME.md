# Regras e textos do canal

Esta pasta guarda tudo o que você edita para o canal. O Clipator lê estes arquivos a cada análise,
então o que você mudar aqui vale já no próximo vídeo.

## A base de referência já vem embutida

O Clipator traz uma base montada com a pesquisa de 75 canais de cortes brasileiros (podcast, humor,
ciência, negócios, esporte, games, saúde e política). Você não escolhe nicho: a cada vídeo o
Clipator descobre o tema pela transcrição e usa o que funciona nesse tema para escolher os cortes,
escrever os títulos e montar a frase da thumbnail. Um canal que mistura assuntos recebe, em cada
vídeo, o padrão do assunto daquele vídeo.

O que você escreve nestes arquivos vale por cima da base. Deixe em branco o que não quiser mudar.

| Arquivo | Para que serve |
|---|---|
| `../canal.md` | Quem é o canal e o público. A IA lê antes de escolher os cortes. |
| `regras.md` | Como escolher os cortes: duração, pesos da nota, temas proibidos, censura de palavras. |
| `titulos.md` | Temperatura, suas fórmulas de título, palavras-gatilho e o que nunca usar. |
| `thumb.md` | Cores, fonte e layouts da thumbnail, e como escrever a frase-gancho. |
| `referencias.md` | Os títulos dos seus cortes que deram certo. A IA usa o tom, não copia. |

## Temperatura do título

Em `titulos.md`, a chave `temperatura` muda o quanto o título provoca:

- **auto** (o padrão): usa a temperatura que mais rende no tema do vídeo.
- **morno**: informativo e direto. Bom para ciência, finanças, notícia séria.
- **quente**: gancho claro (conflito, revelação, número), uma ou duas palavras em CAIXA ALTA.
- **fervendo**: reação forte, confronto, choque. Funciona em humor, treta e futebol, mas cansa rápido.

Em qualquer temperatura vale a trava: o que o título promete tem que acontecer no clip.
Para fixar a caixa alta, acrescente `caixa_alta_total: true` (título inteiro) ou
`palavras_caixa_alta: 2`. Sem essas chaves, vale o que mais rende no tema.

## Variáveis das fórmulas

As fórmulas são usadas quando não há IA. As suas (`formulas`) vêm primeiro e depois as da base.
O Clipator troca:

- `{tema}`: o assunto do trecho (a palavra mais específica da fala).
- `{nome}`: um nome próprio citado no trecho (a fórmula é pulada se não houver).
- `{numero}`: um número ou valor dito (a fórmula é pulada se não houver).
- `{verbo}`: um verbo de fala em caixa alta.

## Como melhorar com o tempo

1. Copie para `referencias.md` os títulos dos seus cortes que mais deram certo, com as visualizações.
2. Coloque thumbnails que funcionaram em `../thumbs/modelos/`: viram modelo para a IA de imagem.
3. Se um tipo de título cansou o público, coloque a frase em `nunca_usar` em `titulos.md`.
