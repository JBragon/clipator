---
name: clipator-arte-terrario-tecnico
description: "Cria cenas de terrário técnico para processos urbanos, energia, logística e funcionamento de serviços, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Terrário técnico

Uma infraestrutura em miniatura aparece numa bandeja hexagonal com uma janela lateral que revela seu funcionamento.

## Direção visual

**Composição.** Bandeja hexagonal com base rasa, três zonas funcionais e um corte lateral em janela. A informação principal usa o espaço livre à esquerda, ligada a uma peça por uma linha fina.

**Material e luz.** Pintura acetinada com vidro fosco só na janela. Miniaturas sem detalhes minúsculos; pisos e tubulações têm contraste de valor. Luz lateral e ambiente moderado.

**Movimento.** A câmera descreve um arco de no máximo 12 graus. Um percurso luminoso leva a atenção da entrada à saída; a tampa desliza para revelar o corte e retorna ao fim.

**Construção.** Separe cenário estático, componentes ativos e tampa. Projete os pontos de ancoragem 3D no HUD a cada seek; desvie cartões que colidirem. Animar o percurso por comprimento acumulado, mantendo a velocidade uniforme.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Mostrar o conjunto e o ponto de entrada.
2. Abrir a janela e percorrer o processo.
3. Destacar o componente que explica o resultado.
4. Fechar a janela e segurar uma vista limpa.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Planta isométrica em SVG com janela de corte e percurso em traço; retirar vidro e volumes complexos.

- O caminho não some atrás de peças opacas durante a explicação.
- Rótulos permanecem dentro da área útil quando a câmera gira.
- Não há pessoas minúsculas usadas para representar dados não fornecidos.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Estratos de terreno decorativos em toda cena, câmera que atravessa a geometria e maquete sem função explicativa.


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

“Use Terrário técnico para ilustrar a fala: A entrada recebe o material. A saída mostra o processo completo. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
