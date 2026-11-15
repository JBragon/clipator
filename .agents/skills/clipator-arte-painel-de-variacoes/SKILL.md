---
name: clipator-arte-painel-de-variacoes
description: "Cria cenas de painel de variações para comparar tratamentos, explicar alternativas e mostrar uma transformação visual, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Painel de variações

Uma foto própria vira uma matriz de estudos visuais; uma faixa diagonal percorre as células e revela diferenças controladas.

## Direção visual

**Composição.** Grade 3x3 com enquadramento idêntico em todas as células e uma legenda externa curta por linha. A célula principal ocupa duas posições quando for necessário ler detalhes.

**Material e luz.** Quatro tratamentos próprios: monocromia suave, duotone quente, contorno e retícula. Nunca combinar todos ao mesmo tempo na mesma célula.

**Movimento.** Uma varredura diagonal troca apenas uma célula por vez com máscara de 180 ms. Segurar o painel completo por pelo menos 1,5 s para comparação; reduzir movimento remove a varredura.

**Construção.** Cachear os quatro tratamentos da imagem local por hash de conteúdo. Calcular ordem por linha+coluna e desempatar por índice estável. Todas as células compartilham crop e âncora facial fornecida localmente.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Mostrar a imagem única de partida.
2. Dividir a área em nove células sem mudar o crop.
3. Aplicar os tratamentos na diagonal.
4. Manter o painel e marcar a alternativa escolhida.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Painel estático com quatro tratamentos e sem trocas.

- As células mostram a mesma região da foto.
- O tratamento não altera o significado documental sem indicação.
- Uma troca não dispara flash em toda a tela.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Mosaico estroboscópico, imagem de pessoa diferente por célula e filtros que inventam detalhes da foto.


## Aplicação no Clipator

Esta é uma skill de autoria para Codex: produza cenas ou implemente o estilo quando solicitado.
Seu manifesto é `fluxo`; instalar a skill ainda não adiciona um renderizador à galeria.
Leia a especificação em [references/especificacao.json](references/especificacao.json) e o
[exemplo de plano](references/exemplo.json) para os dados do estilo. Esses JSON são uma proposta
de contrato `clipator-arte/1`, ainda não um formato aceito pelo motor.

Ao implementar, leia o AGENTS.md do projeto e reutilize a composição de `direcao.py`,
`desenho.py`, `hyperframes.py` e `maquete3d.py` conforme a versão encontrada. A IA do motor
só planeja com texto pelo adaptador existente; o renderizador calcula o visual localmente.
Não envie vídeo ou imagem à IA nem crie serviços externos. Escolha apenas esta direção por
clip; regras de arte dos outros 21 estilos não devem entrar juntas no mesmo prompt.

Para cada cena, associe uma âncora literal à fala e uma ocorrência específica. Os tempos são
segundos do clip depois dos cortes internos; se o trecho não existir, omita a cena e registre o motivo.
O exemplo sintético não serve como informação para um clip real. Não invente dados, nomes ou fontes.
Sem fala, aceite tempos explícitos fornecidos pelo usuário e registre o modo manual.

Use o layout já suportado `em-cima` como padrão, com animação nos 50% superiores e pessoa
abaixo; respeite a zona segura que o Clipator fornecer e a área reservada para legendas.
As posições da arte são locais ao retângulo da animação. Sem clip ou layout definido,
faça uma vinheta isolada de 6 s em 1080x1920, 30 fps. Não altere nem estique o áudio original.
Ajuste a sequência à duração disponível; o tempo de leitura tem prioridade sobre os efeitos.

Calcule o quadro a partir de `(tempo, parametros, semente)`; sem relógio de parede,
aleatoriedade não semeada ou física cumulativa. Respeite o mecanismo de seek da versão local
do HyperFrames; não invente uma API de integração. Use fontes locais com licença registrada,
começando por Montserrat ExtraBold e Bebas Neue já presentes no projeto. Não copie fontes,
scripts, prompts, mídia, modelos ou exemplos dos pacotes usados como referência estética.

Entregue uma amostra renderizada, quadros de entrada/meio/saída e os parâmetros editáveis.
Para implementação, acrescente renderer, registro, integração com a edição, amostra da galeria e
teste de render/seek; só anuncie o estilo pronto após um MP4 real. Sem HyperFrames ou WebGL,
registre a alternativa leve escolhida; se o backend de animação faltar por completo, mantenha a
política existente de legenda ASS e avise que a arte não foi renderizada.

## Pedido de exemplo

“Use Painel de variações para ilustrar a fala: A imagem continua a mesma. O tratamento muda nossa leitura. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
