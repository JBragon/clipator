# Skills embutidas

O Clipator vem com 12 skills próprias em `motor/src/clipator/dados/skills/`, com a licença do
repositório (AGPL-3.0-or-later). Elas foram escritas do zero para o motor do Clipator: o texto de cada
`SKILL.md` vai para a IA nas etapas do tipo dela (até 6000 caracteres), a resposta volta em JSON pelo
adaptador e, onde o motor já tem um caminho sem IA, ele continua funcionando sem elas.

Aparecem na aba Skills com a etiqueta **Embutida** e ficam ligadas em todo o workspace. Dá para desligar
(o "×" da ativação; vai para `skills_desligadas` no `.clipator/config.yaml`) e ligar de novo, mas não
apagar. Uma skill instalada com o mesmo id ganha da embutida.

| skill | tipo | o que faz |
|---|---|---|
| `direcao-de-arte` | estilo, cenas | o método da direção de arte do canal (briefing, referências, rotas, validação, prancha, aprovação, tokens `da:`, conferência), as regras de ritmo das cenas e o estilo "Dossiê em cima"; o método inteiro fica em `clipator://arte/metodo` |
| `cenas-da-fala` | cenas | qual cena usar para cada tipo de fala (número, datas, enumeração, citação, comparação, nome, lugar…) |
| `ganchos-e-titulos` | titulos | títulos curtos que prometem o que o clip entrega, calibrados pelo `titulos.md` |
| `ranking-de-cortes` | ranking | a régua da nota dos cortes (gancho, história completa, emoção, tema, clareza) |
| `thumb-que-converte` | thumbnail | frase curta e composição da thumbnail, calibradas pelo `thumb.md` |
| `publicacao-por-plataforma` | postagem | descrição, hashtags e chamada certos para Shorts, Reels e TikTok |
| `revisao-antes-de-publicar` | revisao | a checklist com nota de 0 a 100 do passo 5 |
| `checagem-de-fatos` | revisao | aponta número, citação e acusação que precisam de fonte |
| `decupagem` | fluxo | tirar pausas mortas, retomadas e repetições (entra no "Melhorar com IA" e na conversa) |
| `retencao-abertura` | fluxo | os primeiros segundos: gancho na frente, movimento, nada de introdução |
| `glossario-do-canal` | transcricao | termos do campo `termos` entram como dica do Whisper e correção automática |
| `texto-sem-cara-de-ia` | postagem, titulos | títulos e descrições concretos, sem clichê |

## Tipos novos

- **cenas**: o texto vai para o planejador de cenas da direção de arte (com IA) e para o "Melhorar com IA".
- **revisao**: o texto vira a régua da "Revisão antes de publicar" do passo 5 (com IA). Sem IA, a
  revisão usa as regras do motor: gancho, pausas, fechamento da frase, duração da plataforma, título,
  chamada e números ditos.
- **transcricao**: os termos do campo `termos` do cabeçalho do `SKILL.md` juntam-se ao glossário de cada
  canal (dica do Whisper e correção pelo som), sem IA.

## Calibrar por canal (sem perguntas interativas)

As skills não fazem perguntas: elas leem a calibração dos arquivos do canal.

- `canal.md`: público, tom, assuntos, palavras-chave, o que evitar, `glossario`, `direcao_de_arte`
  (cores e fontes da ficha) e `chamada_automatica`.
- `regras.md`: pesos da nota dos cortes, duração mínima e máxima.
- `titulos.md`: os títulos que deram certo e o que nunca usar.
- `thumb.md`: fontes, cores, posição do texto e frases que funcionaram.

Para mudar uma skill embutida só num canal, copie a pasta dela para `~/.clipator/skills/` com outro id,
edite o `SKILL.md`, ative no canal e desligue a embutida.

## Como foram feitas

Sala limpa: as ideias de partida vieram de descrições de skills de terceiros (problema, entrada, saída e
passos), anotadas fora do repositório; o texto, a estrutura e os exemplos daqui foram escritos do zero,
sem copiar frases, prompts, tabelas, arquivos de referência, scripts nem nomes de frameworks deles.
