---
name: clipator-arte-acervo-natural
description: "Cria cenas de acervo natural para comparação de espécies, objetos, materiais e exemplares de uma coleção, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Acervo natural

Uma prancheta de acervo apresenta exemplares em pares e destaca uma característica de cada um.

## Direção visual

**Composição.** Duas áreas de amostra de tamanhos iguais, etiqueta com nome e um campo de observação. Escala só aparece quando houver medida conhecida; sem ela, declarar “imagens sem escala”.

**Material e luz.** Fundo verde muito claro sem textura pesada; fotos ou ilustrações locais recortadas têm sombra sutil e bordas naturais. Texto em cartões que não tocam o objeto.

**Movimento.** O par anterior desliza para uma gaveta e o novo ocupa o centro. Uma lupa circular amplia somente a característica mencionada, com duração suficiente para leitura.

**Construção.** Normalize a caixa visível do alfa para ocupar 75% da célula. Gere enquadramento por bounds do objeto, não pelo tamanho do arquivo. Associe cada detalhe a uma caixa de recorte fornecida, sem identificar espécies automaticamente.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Abrir a prancheta com dois exemplares.
2. Destacar a característica do primeiro.
3. Mover a lupa para o detalhe do segundo.
4. Fechar com os dois exemplares e uma observação curta.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Silhuetas próprias e etiquetas quando a imagem não estiver disponível; informar a falta de mídia.

- Não distorcer a proporção dos exemplares.
- Identificações e escala vêm dos metadados fornecidos.
- A lupa não mascara o campo de observação.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Sequência de dezenas de fotos por segundo, nomes científicos inventados e imagens retiradas de busca sem licença.


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

“Use Acervo natural para ilustrar a fala: Vamos comparar estas duas formas. Observe o detalhe em cada uma. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
