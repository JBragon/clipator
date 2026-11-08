---
name: clipator-arte-mecanismo-facetado
description: "Cria cenas de mecanismo facetado para como funciona, fluxo, componentes, dependência e comparação técnica, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Mecanismo facetado

Peças de um mecanismo facetado se separam em uma vista explodida para explicar causa e resultado.

## Direção visual

**Composição.** Até cinco componentes sobre uma base circular fosca, com um eixo comum de montagem. Um rótulo curto por componente e uma pequena faixa de entrada e saída.

**Material e luz.** Sólidos facetados de tons minerais, arestas limpas e um componente em destaque quente. Sem textura granulada; luz principal grande evita que as faces pareçam plástico brilhante.

**Movimento.** Separar componentes ao longo do eixo em 0,6 s, percorrer a transformação com um pulso lento e remontar. A câmera muda a aproximação no máximo 8%, sem orbitar durante rótulos.

**Construção.** Defina transformações base e deslocamentos explodidos por peça; interpole os dois estados. Conexões aparecem só quando as peças estão separadas. Especifique uma entrada, uma operação e uma saída por cena.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Identificar o conjunto montado.
2. Separar as peças e revelar suas funções.
3. Percorrer entrada, transformação e saída.
4. Remontar com o componente responsável destacado.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Polígonos isométricos SVG com a mesma separação por eixo e o mesmo percurso.

- A vista explodida não troca a ordem das peças.
- O percurso explica a fala, em vez de só enfeitar o mecanismo.
- Rótulos têm uma única peça de destino.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Maquete urbana genérica para qualquer tema, partículas excessivas e HUD que não corresponde às peças.


## Aplicação no Clipator

Esta é uma skill de autoria para Claude Code: produza cenas ou implemente o estilo quando solicitado.
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

“Use Mecanismo facetado para ilustrar a fala: Estas partes trabalham juntas. Separadas, suas funções ficam visíveis. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
