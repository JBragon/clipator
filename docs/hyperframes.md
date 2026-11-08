# Motor HyperFrames

Os estilos com `motor: hyperframes` desenham a legenda e os motion graphics em HTML/CSS, e o [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache 2.0) renderiza isso como vídeo.

## Como o render funciona

1. O Clipator monta `clips/<id>/hyperframes/index.html`. Ele traz só a camada de cima, sobre fundo transparente: legenda palavra a palavra, cartela, números e palavras-chave.
2. `hyperframes render --format webm` gera `camada.webm` com alfa.
3. O FFmpeg corta e reenquadra o vídeo como nos outros estilos e põe a camada por cima. O vídeo do usuário nunca passa pelo navegador.

Se o HyperFrames não estiver instalado ou falhar, o clip sai mesmo assim com a legenda ASS, e o job registra um aviso.

As animações são só CSS (`@keyframes`), sem GSAP e sem CDN, então funcionam offline. A telemetria do HyperFrames fica desligada (`HYPERFRAMES_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`).

## Instalar

O [instalador do Clipator](instalacao.md) já instala o Node.js e o HyperFrames. Para fazer à mão:

```bash
npm install --prefix ~/.clipator/hyperframes hyperframes@0.8.229   # Node.js 22+
clipator doctor                                                     # deve mostrar "HyperFrames"
```

Na primeira renderização, o HyperFrames baixa o próprio Chrome headless. Para usar um navegador já instalado, defina `HYPERFRAMES_BROWSER_PATH`. Para usar outro CLI, defina `CLIPATOR_HYPERFRAMES`.

## Escrever um template

Um template é um `.css` em `motor/src/clipator/dados/hyperframes/` ou ao lado do estilo. Ele pode vir com um `.html` de mesmo nome, com a decoração fixa. O estilo escolhe o template com `template: nome`.

Para um estilo em pasta (`estilos/<nome>/estilo.md`), o template pode ficar em `estilos/<nome>/composicao.css`. É ali que a IA escreve no nível Autoral.

Marcação que o Clipator gera, para o CSS estilizar:

| Elemento | O que é |
| --- | --- |
| `.frase` (clip) | Um bloco de legenda. Contém `.linha` > `.p` (uma palavra) |
| `.p` | A palavra. `--t` é o início e `--d` a duração, em segundos, contados do início da frase. `--i` é a posição no bloco |
| `.p.destaque` | Palavra destacada: a lista do estilo, os destaques da IA e os números, se `destacar_numeros` |
| `.numero` (clip) | Aparece quando alguém fala um número. Contém `.valor` (com `--alvo`) e `.sufixo` ("mil", "%"…). Fica escondido no `base.css` |
| `.chave` (clip) | Uma palavra-chave destacada, em caixa alta. Fica escondida no `base.css` |
| `.cartela` (clip) | O título nos primeiros segundos, com `data-posicao` e `.caixa` |

Variáveis em `:root`, vindas do `.md` do estilo: `--fonte`, `--tamanho`, `--cor`, `--destaque`, `--contorno`, `--espessura`, `--sombra`, `--y`, `--fonte-cartela`, `--tamanho-cartela`, `--cor-cartela`, `--fundo-cartela`, `--destaque-cartela`, `--duracao`, `--largura`, `--altura` e `--escala`.

No `.html` de decoração, `$titulo` e `$duracao` são substituídos. Todo elemento com tempo precisa de `class="clip"`, `data-start`, `data-duration` e `data-track-index`.

Uma regra importante: o HyperFrames busca as animações dos elementos HTML pelo tempo do clip e as de SVG pelo tempo da composição inteira (ver [artes.md](artes.md)). Para um elemento HTML, ele busca pelo tempo daquele elemento. Animação em `::before` e `::after` não segue esse tempo, então use elementos de verdade ou `background`.
