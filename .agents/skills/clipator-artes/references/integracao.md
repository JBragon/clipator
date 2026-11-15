# Integração com o checkout do Clipator

## O que foi observado e o que está sendo proposto

Observado em 04/11/2026: motor Python, Electron/React, estilos em Markdown, `DirecaoArte`
com modos `cenas` e `desenho`, layouts `em-cima`, `fundo`, `sobreposto`, `janela` e `nenhum`.
O app já declara Three.js 0.160.1; o código da maquete busca a biblioteca local. Não assumir
APIs de uma versão mais nova e não atualizar dependências sem necessidade demonstrada.

`direcao.py` cria cartões e liga as cenas à fala. `desenho.py` faz análise, roteiro e composição
com JSON por schema, salva `direcao-arte.json` e acrescenta cenas ao `edicao.json`.
`maquete.py` e `maquete3d.py` oferecem alternativas facetadas SVG e WebGL. `hyperframes.py`
compõe HTML/CSS, renderiza a camada e entrega ao FFmpeg. Leia `render.py` para confirmar a
composição e o fallback real antes de alterar o despacho.

Proposta: acrescentar identificadores de direção próprios e registro de renderizadores, sem
alterar o significado dos modos antigos. O campo `estilo` de `clipator-arte/1` é do contrato
proposto, não um atributo existente de `DirecaoArte`. Escolha a menor extensão compatível
após inspecionar `models.py` e o documento de edição. As chaves internas novas também ficam
em português quando expostas em arquivo/UI, conforme AGENTS.md.

## Pontos de extensão

| Parte | Arquivos observados | Resultado esperado |
|---|---|---|
| Validação e modelos | `motor/src/clipator/models.py`, `edicao.py`, `desenho.py` | Registro de id, versão e parâmetros limitados; planos antigos continuam válidos |
| Planejamento | `desenho.py`, `direcao.py`, `ai/adapter.py` | Apenas a ficha selecionada e a transcrição entram; JSON não contém código |
| Renderizadores | `direcao.py`, `maquete.py`, `maquete3d.py`, `hyperframes.py` | Cena parametrizada desenhada por código confiável do projeto |
| Composição e áudio | `render.py`, `timeline.py`, `sons.py`, `plataformas.py` | Mesmo vídeo, mesmos cortes, legenda legível e voz preservada |
| Presets | `motor/src/clipator/dados/estilos/` | Um `.md` por estilo pronto, com ids sem colisão e formato validado |
| Galeria e direção | `GaleriaEstilos.tsx`, `DirecaoDoClip.tsx`, `PassoEstilo.tsx` | Nome, amostra real, escolha, parâmetros suportados e alternativa visível |
| Cache e amostras | `amostras.py`, `ferramentas/gerar_amostras.py` | Cache muda com fonte, mídia, estilo, parâmetros, formato e versão do renderer |
| Empacotamento | `motor/pyproject.toml`, instaladores e build do app | Assets e código local disponíveis também na instalação distribuída |

Caminhos de componentes acima são relativos a `app/src/renderer/src/components/`.

## Entregas em sequência

1. Implemente `anotacao-em-foco` de ponta a ponta como fatia inicial. Ela exige texto medido,
âncora, máscara e integração, mas não depende de mídia externa. Renderize uma amostra e um clip
sintético com áudio antes de generalizar a arquitetura.
2. Extraia só o que a segunda direção precisar reutilizar: medição de texto, paleta semântica,
retângulo de arte, assets locais, envelope de animação, semente e registro do renderer.
3. Faça as demais direções 2D: arquivo-em-camadas, letras-de-oficina, acervo-natural,
mapa-de-ideias, quadro-de-recortes, painel-de-variacoes, atlas-de-percursos,
revista-de-bancada, gesto-de-papel, caderno-de-materiais e tinta-em-etapas.
4. Faça as híbridas: cidade-de-bolso, jardim-de-luz, janela-em-profundidade e
mesa-em-profundidade. A alternativa 2D entra na mesma fatia funcional, sem depender de GPU.
5. Faça as seis 3D: oficina-modular, costura-viva, terrario-tecnico,
resina-em-movimento, mecanismo-facetado e camadas-do-terreno. Em cada uma, implemente e
teste a alternativa SVG junto. Limite geometria e textura por qualidade, liberando recursos.
6. Gere as 22 amostras finais com o pipeline real, atualize os hashes do índice e confira o build
instalável. Registre qualquer estilo ainda incompleto sem anunciar a coleção toda pronta.

## Renderizar sem introduzir outro motor

Para 2D use SVG e CSS dentro da composição atual do HyperFrames. Elementos temporais
precisam da marcação temporal exigida pela versão instalada; o projeto já usa `class="clip"`,
`data-start`, `data-duration`, `data-track-index`. Não suponha que `::before` e `::after`
obedeçam ao seek: prefira elementos concretos para partes animadas.

Para Three.js confira a implementação real de timeline em `maquete3d.py`: a versão observada
registra uma timeline procurável pelo HyperFrames. Todo seek deve restaurar o estado completo
e desenhar um quadro, mesmo se for chamado antes do primeiro quadro ou depois da saída.
Um `requestAnimationFrame` independente não pode ser a fonte do tempo de exportação.
Use geometrias instanciadas quando fizer sentido, limite pixel ratio e descarte recursos.

Mantenha o vídeo fora do navegador, como no pipeline atual. O FFmpeg compõe a camada de arte
no retângulo escolhido, preservando a cor e o áudio do clip. Formato, fps, duração e alfa da
camada devem bater com o projeto. Não crie URLs remotas ou `eval` para desenhar conteúdo da IA.

## Cor, texto e layout

As seis cores têm papéis estáveis: fundo, superfície, texto, texto suave, primária e destaque.
Herança: preset, depois canal e depois ajuste explícito do clip. Validar hex e contraste após
resolver a herança. Fonte ausente usa fonte local registrada e gera aviso no relatório.

Cada renderer recebe bounds locais da arte, não coordenadas absolutas de toda a tela.
Adapte às proporções existentes. Calcule a interseção com a zona segura atual da plataforma
fornecida pelo motor e desconte legenda, janela do vídeo e recorte da pessoa quando existirem.
Se faltar espaço: reduzir decoração, quebrar texto por palavras, dividir a cena ou omiti-la com
motivo; não aceitar texto minúsculo nem cobrir a pessoa para preservar decoração.

## Cache e persistência

Chave de cache: id e versão do renderer, plano validado, palavras, cortes internos, preset
resolvido, fontes reais e hashes de mídias, formato, fps, backend e qualidade. Não usar só
o caminho ou mtime da foto. Arquivo novo no mesmo caminho precisa invalidar o cache.
Salve a direção junto da versão de edição; desfazer uma versão recupera plano e parâmetros.
Se a edição altera a transcrição ou o tempo, resolva âncoras novamente e invalide o render.

## Verificações no repositório

Rode os testes offline relevantes durante cada fatia e `cd motor && pytest -q` ao concluir,
conforme AGENTS.md. Se tocar o app: `npm run typecheck`, `npm test` e `npm run build`,
usando `npm.cmd` no PowerShell quando necessário. Gere amostras pelo comando já existente
após verificar seu `--help`; não recrie testes que apenas conferem a redação dos presets.
