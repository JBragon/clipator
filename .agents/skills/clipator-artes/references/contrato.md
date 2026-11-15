# Contrato proposto `clipator-arte/1`

Esta proposta organiza a troca entre planejamento e render. O motor atual não lê esse
arquivo diretamente. A implementação pode mapear os dados para os modelos atuais em vez
de persistir um segundo documento. O schema fica em `plano.schema.json`.

## Espaço e tempo

- `duracao_s` é duração final do clip, depois dos cortes internos. `inicio_s` e `fim_s`
  são segundos nessa linha do tempo, nunca timestamps absolutos do arquivo original.
- `layout.proporcao` tem o significado do layout `em-cima` existente. A arte usa um
  retângulo local com origem no alto à esquerda; coordenadas visuais adicionais, se criadas,
  são frações desse retângulo. O schema não introduz posições arbitrárias de elementos.
- O modo `fala` usa `palavras` ordenadas, com texto e tempos locais. O modo `manual`
  exige cenas com `ancora: null` e tempos explicitamente escolhidos; não inventar âncoras.
- Cenas da mesma direção não se sobrepõem. Entrada/saída são fases dentro do intervalo
  da cena; não estendem sua duração. Uma cena pode ocupar o silêncio até a próxima frase.

## Resolver âncoras

Normalize Unicode NFC, caixa e pontuação apenas para busca; preserve o texto original na
tela. Faça correspondência de sequência contígua de tokens e conte ocorrências pela posição
inicial, inclusive quando o termo se repetir. A ocorrência é baseada em 1. Se houver dúvida,
peça correção no editor da direção em vez de escolher por similaridade frouxa.
`inicio_s` deve ser o início da primeira palavra do trecho encontrado. `fim_s` deve cobrir
até a última palavra da âncora e pode incluir um tempo de leitura antes da cena seguinte.
Os dois campos de tempo enviados pela IA são sugestões: o motor os deriva ou verifica.

Exemplo: “o processo” dito duas vezes precisa de `ocorrencia: 2` para escolher a segunda.
Se o usuário remove esse trecho por jump cut, a cena cai fora com aviso, não é movida para
um ponto qualquer do vídeo. Timestamps de transcrição com sobreposições legítimas podem
precisar de normalização pelo alinhador existente; não apagar palavras para satisfazer o schema.

## Mídia e objetos

`objetos` descreve entidades visuais locais de tipos permitidos: forma procedural, ícone
da biblioteca ou texto. Não aceita HTML, JavaScript, nome de classe a importar ou arquivo a
executar. Um renderer traduz ids e parâmetros por uma lista de operações conhecida.

`midias` usa id e caminho relativo à raiz de mídia do projeto, acompanhados de crédito e
licença informados. Impedir caminhos absolutos, `..`, esquemas remotos e fuga por symlink
ou junction após resolver o caminho. O schema verifica a estrutura; a trava de caminho é
obrigação adicional do host. Não inclua credenciais nem arquivos do usuário sem relação com a cena.

Fotos, mapas e camadas não são inferidos da transcrição. Sem mídia: usar a alternativa
declarada na especificação e registrar o motivo. Quando for imagem de teste, rotular a
amostra como sintética. Não afirmar identidade de pessoa, espécie ou lugar sem metadados.

## Parâmetros

`parametros` aceita valores JSON simples para os campos da direção escolhida. O schema
geral limita tamanho e nomes, mas **não** estabelece os limites visuais de cada renderer.
Na integração, derive uma allowlist tipada por id a partir da especificação e imponha limites
de amplitude, geometria, quantidade de imagens e textura antes de alocar memória. Chave
desconhecida deve ser recusada com mensagem, não virar atributo de objeto ou filtro FFmpeg.

## Saídas

Um render completo deve produzir MP4 final pelo pipeline atual, miniatura, três quadros de
conferência e registro da direção e da versão de edição. Guarde os intermediários na pasta
de trabalho do clip. Registre backend e fonte resolvidos, avisos, seed e parâmetros usados.

Não misture sucesso de schema com sucesso visual: JSON válido não prova texto legível,
render correto, sincronismo ou qualidade sonora. O validador deste pacote verifica exemplos
e a estrutura de skills; ainda é necessário testar a implementação no projeto.
