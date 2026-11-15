# Aceite por direção

## Planejamento e versão

1. Uma transcrição de 6 s com duas ideias gera duas cenas com âncoras existentes.
2. Uma expressão repetida duas vezes escolhe a ocorrência certa; âncora removida pela
   edição produz aviso e omissão; fim nunca excede a duração final.
3. Número, citação e nome não fornecidos não são acrescentados como fato.
4. Ajustar cor, texto, parâmetro e ordem pelo painel salva uma versão nova; desfazer
   recupera os mesmos quadros, com o plano associado à versão usada.

## Render determinístico

1. Renderizar `t=2`, depois `t=0.5`, depois `t=2`: os quadros em 2 s são iguais no mesmo
   ambiente/backend, com a mesma seed. Não exigir igualdade binária entre GPUs diferentes.
2. Conferir entrada, meio, leitura e saída, além dos três quadros de entrega.
3. Em laço opcional, comparar os estados em `t=0` e `t=duracao`, incluindo luz e câmera.
   No MP4 o último quadro é `duracao-1/fps`, não `duracao`: avaliar a continuidade da
   emenda e usar envelope periódico. Não duplicar o primeiro quadro no fim por padrão.
4. Trocar a semente muda só a decoração permitida, nunca dados e ordem narrativa.
5. Rodar duas qualidades no mesmo conteúdo e confirmar a mesma leitura e sincronismo.

## Composição e mídia

1. Renderizar fixture com pessoa e áudio sintéticos em 9:16; depois 1:1 e 16:9 se a
   direção for anunciada nesses formatos. Tipografia, cards e labels cabem na área útil.
2. Texto comprido e acentos não vazam. Texto principal usa contraste de pelo menos 4,5:1.
3. A voz permanece com o mesmo conteúdo e duração; os sons não mascaram palavras.
   No silêncio, não surgir clique de emenda nem ruído fora da janela do efeito.
4. Mídia com alfa, mídia opaca e mídia ausente têm saídas explícitas. Caminho fora da
   raiz e fuga por link são recusados. Novo conteúdo no mesmo caminho invalida o cache.
5. Nenhum request de rede durante o render com dependências locais preparadas.

## Falhas e capacidades

1. WebGL indisponível usa a versão leve da direção; conferir que os rótulos continuam corretos.
2. Falta completa de HyperFrames segue a política de legenda ASS existente, com aviso
   de que a arte foi omitida; não gravar “render de arte concluído”.
3. Sem IA, estilos antigos continuam funcionando e plano de arte previamente salvo pode
   ser re-renderizado sem nova chamada. Planejamento novo, quando exigir IA, dá mensagem clara.
4. Cancelar um job interrompe a renderização e não promove arquivo parcial a resultado final.

## Entrega revisável

Para cada direção: preset validado, renderer integrado, parâmetros no painel, amostra real da
galeria, MP4 de teste, capturas e resultado dos testes. Medir duração do render, memória e
backend em máquina identificada. Não inventar metas de velocidade. Não ativar um estilo pela
mera presença de SKILL.md. Executar os checks do projeto e relatar limitações reais.
