---
name: clipator-artes
description: "Integra e mantém a coleção de 22 direções visuais próprias do Clipator, criando renderizadores locais, presets, amostras e edição sincronizada à fala. Use para implementar a coleção ou escolher uma direção para um clip."
license: AGPL-3.0-or-later
---
# Artes do Clipator

Implemente a coleção por fatias funcionais: uma direção aparece na galeria somente depois
de renderer, edição e amostra real funcionarem juntos. Para produzir um clip com um estilo já
implementado, use o renderer existente e a skill específica, sem reiniciar a implementação.

## Descobrir e escolher

Leia [references/catalogo.json](references/catalogo.json). Escolha uma direção que explique a
fala e abra apenas o `SKILL.md` dessa direção, irmão desta pasta. Caminhos `skill` do catálogo
são relativos à raiz do pacote de entrega; na instalação `.Codex/skills`, procure o id como
pasta irmã. Não carregue todos os 22 textos no prompt de cada clip.

Se o pedido for implementar a coleção inteira, siga a ordem de entrega da
[integração](references/integracao.md). Não peça uma seleção de estilo quando ela já foi feita.

## Verificar a versão do projeto

Leia AGENTS.md, AGENTS.md, docs/requisitos-arquitetura.md, docs/referencias-concorrentes.md,
docs/skills.md e docs/hyperframes.md. O mapa de integração foi escrito a partir de uma leitura
local do projeto em 04/11/2026; confirme nomes e assinaturas no checkout atual antes de editar.
Preserve o trabalho existente. Não faça commit nem push sem a autorização exigida pelo projeto.

O manifesto das skills deste pacote é `fluxo`: são ferramentas de autoria. Não mude todas para
`cenas` nem injete seu texto de implementação no planejador de runtime. Gere instruções curtas
de runtime, separadas e selecionadas pelo id do estilo, quando o renderer correspondente existir.

## Contrato e render

Leia [references/contrato.md](references/contrato.md). O schema
[references/plano.schema.json](references/plano.schema.json) é uma proposta de intercâmbio;
não é uma API que o Clipator já ofereça. Adapte ao documento de edição existente ou implemente
um adaptador versionado com validação explícita. Não criar uma segunda linha do tempo concorrente.

A IA do motor recebe só texto e retorna JSON pelo adaptador atual. Objetos, materiais,
fotografias e mapas são desenhados/combinados localmente com parâmetros validados.
Codex como desenvolvedor pode inspecionar quadros locais para conferir o código; isso não
autoriza uma API do produto que envie mídia dos usuários à IA.

Mantenha a camada de vídeo e o áudio originais; a arte ocupa um retângulo de layout existente.
Use tempos do clip após jump cuts e recalcule âncoras quando a edição mudar. Sem IA, renderizar
um plano previamente salvo deve continuar local; o planejamento novo pode continuar exigindo
IA se esse for o comportamento declarado. Preserve o modo sem IA dos estilos antigos.

Renderize em tempo absoluto com semente fixa. Reutilize CSS e timelines do HyperFrames local,
Three.js já disponível e alternativas SVG. Não adicione Remotion, serviços pagos, CDN ou
um motor próprio de captura para esta coleção. Não prometa desempenho ou compatibilidade
de GPU sem medir. Registre a alternativa realmente utilizada no resultado.

## Critério de entrega

Siga [references/aceite.md](references/aceite.md). Cada direção precisa de amostra real,
quadros de conferência, parâmetros editáveis, hash de cache correto e prova de fallback.
Teste schema, âncoras repetidas, busca de quadro fora de ordem, mistura com vídeo e preservação
do áudio. Use fixtures sintéticas locais, não os vídeos de referência de terceiros.

Informe o que foi implementado, as verificações executadas, o que está pendente e os arquivos
alterados. Não descreva mockups ou especificações como vídeos já renderizados.
