---
name: clipator-arte-camadas-do-terreno
description: "Cria cenas de camadas do terreno para geologia, cidade, ocupação do espaço e sistemas em camadas, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Camadas do terreno

Um bloco isométrico mostra solo, infraestrutura e superfície em camadas que podem deslizar para revelar o que existe entre elas.

## Direção visual

**Composição.** Bloco retangular com três níveis e um canto removível; legenda lateral associa cada cor a um nível. As faces têm diferença de luminosidade, não contorno preto de quadrinhos.

**Material e luz.** Superfície mineral fosca, camadas internas em argila suave e tubulações de contraste moderado. Árvores e casas simples são opcionais e têm escala consistente.

**Movimento.** A camada superior desliza para a esquerda, a intermediária para a direita e a base fica fixa. Um marcador desce atravessando os níveis e volta ao ponto inicial.

**Construção.** Modele cada nível como grupo com offset próprio. Corte visual deve corresponder à geometria, não à textura. Limite a quantidade de elementos por nível e sincronize rótulos com a projeção de seus centros.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Mostrar o bloco inteiro e a legenda.
2. Separar dois níveis sem girar a câmera.
3. Mover o marcador pela seção exposta.
4. Recompor os níveis e destacar a superfície.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Faces isométricas SVG com três faixas e offsets idênticos.

- A ordem das camadas continua visível durante o deslocamento.
- O marcador segue a seção exposta.
- A escala não muda entre antes e depois.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Transformação contínua de morro em mar sem relação com a fala e relevo tratado como dado científico sem fonte.


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

“Use Camadas do terreno para ilustrar a fala: A superfície esconde outras camadas. Vamos separá-las para observar o conjunto. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
