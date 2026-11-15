---
name: clipator-arte-jardim-de-luz
description: "Cria cenas de jardim de luz para respiro narrativo, histórias calmas, sustentabilidade e encerramento, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Jardim de luz

Um jardim noturno em planos de papel recebe pequenos pontos de luz que conduzem o olhar por um caminho.

## Direção visual

**Composição.** Três massas de folhagem recortada em volta de uma clareira, caminho em diagonal e um ponto de luz principal. Texto ocupa uma abertura do cenário, com fundo de contraste uniforme.

**Material e luz.** Papel de fibras largas em verdes acinzentados; bordas claras e sombra suave entre camadas. Luz âmbar pontual complementa uma iluminação de lua muito fraca.

**Movimento.** Folhas oscilam no máximo 2 graus; uma luz percorre o caminho com duas pausas sem piscar. A câmera se aproxima 3% ao longo da cena, mantendo o texto imóvel.

**Construção.** Gere massas de folhas com polígonos de semente fixa; cada grupo usa uma senoide de fase própria. Path da luz é uma curva com comprimento tabelado. Tempo de ambientação continua absoluto ao longo das cenas.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Revelar a clareira e o primeiro ponto de luz.
2. Conduzir a luz pela primeira curva.
3. Parar na clareira e mostrar a ideia central.
4. Atenuar a luz até o nível ambiente.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Paralaxe 2D com folhas SVG e gradiente radial; sem luz dinâmica nem sombras WebGL.

- A cena continua compreensível em tela escura de celular.
- Folhas não passam sobre a legenda.
- Não há pulsos rápidos de luminosidade.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Riacho ciano como única assinatura, céu cheio de partículas e ritmo acelerado de introdução.


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

“Use Jardim de luz para ilustrar a fala: O caminho atravessa o jardim. A luz para nesta clareira. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
