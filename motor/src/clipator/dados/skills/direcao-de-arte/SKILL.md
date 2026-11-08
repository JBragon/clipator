---
name: direcao-de-arte
description: "Escolhe e ajusta a direção de arte de cada estilo (arte:), que guia a IA ao planejar o corte e o render; o canal só põe a marca (arte/marca.yaml). Também cria DAs novas com prancha e aprovação."
---
# Direção de arte

A direção de arte (DA) guia o corte. **Quem escolhe a DA é o estilo**: no cabeçalho dele, `arte: <predefinido>`
(`documental`, `manchete`, `caderno-de-aula`…), `arte: canal` (a DA própria do canal em `arte/direcao.yaml`) ou
`arte: {herda: manchete, cenas: {por_minuto: 8}}`. **O canal só ajusta a marca** em `arte/marca.yaml`: cores
primária, secundária e destaque, fontes e logo. Cor da marca que some no fundo do estilo é ajustada sozinha.

Ao gerar o corte, a DA do estilo vai para a IA que planeja as telas (tom, tipos de cena preferidos e evitados,
ritmo, limites de texto, faça e não faça), e o Clipator confere a resposta: descarta tipo evitado, cena perto
demais de outra, acima do teto por minuto ou com texto longo, e ajusta a duração e o tamanho das listas.
Depois, o render usa a mesma DA na ficha das cenas, na legenda e na cartela.

Você propõe, mostra e ajusta; **quem decide é a pessoa**. Nunca chame `arte_aprovar` sem o "sim" dela depois
de ver a prancha. O método completo está no recurso `clipator://arte/metodo`.

## Escolher a DA de um estilo
1. Veja o que o estilo usa hoje: `arte_guia canal=… estilo=…` (mostra a DA, a marca aplicada, os avisos e o
   texto exato que a IA recebe). Para ver, `arte_prancha estilo=…`.
2. Combine conteúdo e DA: investigação → `arquivo-confidencial`; notícia → `manchete`; aula → `caderno-de-aula`;
   finanças → `tela-de-dados`; conversa → `palco-noturno`; humor e games → `fliperama`; história →
   `documental`. Na dúvida, mostre duas pranchas e deixe a pessoa escolher.
3. Ajuste o ritmo no próprio estilo (`arte: {herda: …, cenas: {…}}`) em vez de criar outra DA.
4. Marca do canal: `arte_marca criar=true` escreve o modelo; preencha só o que a marca tem de fato.

## Criar uma DA nova (para o canal ou para virar predefinido)
1. Entenda o canal: `canal.md`, `arte_ler`. No máximo cinco perguntas de uma vez (público, três referências
   e o que agrada nelas, o que ela não quer, marca existente, tom em três adjetivos).
2. Referências em `arte/referencias/` + `arte_extrair_referencias`. Candidatos são proposta; de marca de
   terceiros tire o princípio, nunca a paleta inteira.
3. Duas ou três rotas (`arte_rotas acao=criar`), cada uma forte num eixo diferente (valor, material,
   tipografia, movimento, tratamento). `acao=comparar`; adote só a que a pessoa escolher.
4. Refine, `arte_validar`, `arte_prancha`, mostre. Com o sim: `arte_aprovar confirmar=true`. Para usar em
   vários canais: `clipator arte salvar-preset CANAL nome`, e os estilos passam a apontar `arte: nome`.

## Decisões que mais pesam
- **Cor:** dez papéis fixos (`fundo`, `superficie`, `texto`, `texto_suave`, `primaria`, `secundaria`,
  `destaque`, `positivo`, `negativo`, `alerta`). O nome é a função. Fundo domina, primária aparece pouco.
  Texto sobre fundo ≥ 4,5:1; texto grande e grafismo ≥ 3:1. `serie` com 6+ cores, vizinhas bem diferentes.
- **Tipografia:** duas famílias no máximo; `titulo`, `subtitulo`, `corpo`, `dados`, `legenda`. Caixa alta
  pequena pede espaçamento 0,06 a 0,15 em. Tamanhos são fração do lado menor: abaixo de 0,022 ninguém lê;
  legenda a partir de 0,04, confortável a partir de ~0,052. Só fontes com licença para vídeo (OFL).
- **Legenda:** `karaoke`, `palavra` ou `bloco`; sempre com contorno, sombra ou caixa; `y_vertical` ≈ 0,62
  (fora dos botões e da descrição); 2 linhas e 3 a 5 palavras por linha no máximo.
- **Movimento:** entrada desacelera no fim, saída acelera. Overshoot só em canal lúdico. Uma entrada por
  tela; a forma entra antes do texto e sai depois. Escalonamento 0,04 a 0,1 s.
- **Tratamento:** desligado por padrão. Se ligar, sutil (contraste 1,03–1,1, grão 3–6, vinheta ~0,3). A
  pele é o juiz.
- **Thumbnail:** até 4 palavras, grande, fora do canto da duração. **Som:** −14 LUFS, pico −1 dBTP, efeitos
  baixos.
- **Conceito:** uma `frase` de briefing, 4 a 8 `palavras_chave`, `faca`/`nao_faca` concretos e conferíveis.

## A seção `cenas` (o que guia o corte)
`tom`, `preferir` e `evitar` (titulo, numero, citacao, lista, comparacao, linha_do_tempo, local, nome, palavra,
alerta), `intervalo` (s entre cenas), `por_minuto`, `duracao` [mín, máx], `palavras_titulo`, `palavras_rotulo`,
`itens_lista`, `palavras_item`, `abrir_com_titulo` e `regras` (frases curtas para a IA). Escreva regras que se
conferem na tela ("número sempre com o que ele mede"), não desejos ("seja criativo").

## Tokens nos estilos
`cor: "da:texto"`, `destaque: "da:primaria"`, `fonte: "da:legenda"`; `legenda: {da: true}` e
`cartela: {da: true}` preenchem com a DA o que o estilo não escreveu. Em CSS: `var(--da-cor-texto)`,
`rgba(var(--da-cor-fundo-rgb), .85)`, `var(--da-fonte-titulo)`. Foto ou logo de terceiros: `/* da-livre */`.
`arte_lint` acha valor escrito à mão. Antes de publicar, `arte_conferir` checa se cada clip foi feito com a
versão atual da DA do estilo dele.

## Ritmo das cenas
- Uma ideia por tela. Pouco movimento: entra, fica o tempo de ler, sai. Respiro entre cenas.
- Texto curto: título até 6 palavras, rótulo até 8, item de lista até 5. A tela resume, não inventa.
- O destaque aparece no máximo uma vez por cena. Nada na zona que a plataforma cobre.

## Estilo sem DA
Sem `arte:`, o estilo segue como antes: a ficha (`neon`, `dossie`, `editorial`, `laboratorio`) e a chave
`direcao_de_arte` do `canal.md` ajustam as cenas, e os `da:` saem com os valores do predefinido `base`.
