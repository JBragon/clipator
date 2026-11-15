---
name: clipator-arte-revista-de-bancada
description: "Cria cenas de revista de bancada para perfil de pessoa, contextualização de assunto e explicação com fotografia, ou implementa esse estilo no Clipator quando solicitado."
license: AGPL-3.0-or-later
---
# Revista de bancada

Uma página editorial combina retrato recortado, coluna de contexto e pequenas notas presas à grade.

## Direção visual

**Composição.** Retrato em um lado, coluna de informação no outro, filete vertical e um único bloco de destaque. Rodapé pode ter fonte da imagem quando fornecida.

**Material e luz.** Fotos com tons naturais levemente reduzidos, filete verde e cartão cobre. Recorte sem contorno colorido espesso; sombra curta separa foto do papel.

**Movimento.** A página abre pela coluna, o retrato sobe 18 px e uma nota lateral desliza até o filete. O título fica fixo enquanto a pessoa fala.

**Construção.** Layout por duas colunas com larguras 58/42 e colisão de caixas. Detecte se a foto tem alfa; sem recorte, use moldura retangular e mantenha a imagem inteira. O nome vem dos dados, não de reconhecimento facial.

Use as cores por função do JSON; o canal pode substituí-las se preservar contraste e materiais.
O texto principal deve ter contraste de pelo menos 4,5:1 com seu fundo efetivo. Decoração usa
primária e destaque; texto longo usa `texto`, nunca uma cor de acento sem medir contraste.

## Sequência sugerida

1. Abrir o filete e o título curto.
2. Revelar retrato e nome fornecido.
3. Apresentar a nota que contextualiza a fala.
4. Manter retrato e resumo numa página limpa.

Para 6 s, distribua as fases em 0–0,9 s, 0,9–2,4 s, 2,4–4,5 s e 4,5–6 s.
No clip, derive os inícios das âncoras e simplifique as fases quando a fala for rápida.
Não acelere o vídeo matriz para caber nessa sequência.

## Alternativa leve e conferência

Foto retangular e duas colunas sem sombra ou recorte automático.

- A foto não corta o rosto ao mudar de formato.
- Nome e atribuição têm origem explícita.
- A nota não vira uma segunda legenda corrida.
- Em movimento reduzido, retire oscilação e travelling; use entrada simples e leitura estável.
- Evite: Borda azul recortada como assinatura obrigatória, título sobre rosto e atribuição inventada de pessoa.


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

“Use Revista de bancada para ilustrar a fala: Esta imagem apresenta o assunto. A nota ao lado traz contexto. Preserve a pessoa embaixo, gere 6 s de amostra e mostre os quadros de conferência.”

Ao preparar instruções de runtime para o motor, use a versão compacta em [references/runtime.md](references/runtime.md), somente para esta direção.
