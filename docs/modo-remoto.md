# Modo remoto: o Clipator no celular

Deixe o PC ligado com o Clipator aberto e acompanhe pelo celular, em casa ou na rua. Pelo celular você:

- vê o que está rodando no PC (e cancela, se quiser);
- cola o link de um vídeo novo para o PC analisar;
- aprova os cortes sugeridos, com o estilo do canal ou outro;
- assiste e baixa o clip pronto.

**Todo o processamento continua no PC.** O celular só mostra a interface: nenhum vídeo é enviado para a nuvem, e o celular não precisa de nada instalado além do navegador (e do Tailscale, para usar fora de casa).

## Como funciona

O motor do Clipator serve uma página leve numa segunda porta do PC (8766). O celular abre essa página no navegador.

- **Em casa**, o celular acha o PC pelo Wi-Fi.
- **Fora de casa**, ele acha o PC pelo [Tailscale](https://tailscale.com), um programa grátis que cria uma rede privada e criptografada só entre os seus aparelhos. Com ele você **não precisa mexer no roteador**: nada de NAT, redirecionamento de porta ou IP fixo.

O endereço do Tailscale funciona nos dois casos, então é o que recomendamos: você pareia o celular uma vez e ele funciona em casa e na rua.

## Passo a passo

### 1. Instale o Tailscale no PC

1. Baixe em [tailscale.com/download](https://tailscale.com/download) e instale (Windows, Mac ou Linux).
2. Abra o Tailscale e entre com uma conta Google, Microsoft, GitHub ou Apple. O plano pessoal é grátis.
3. Confira que ele está conectado: no Windows e no Mac, o ícone perto do relógio mostra "Connected". No Linux, rode `tailscale status`.

> No Linux, depois de instalar, rode `sudo tailscale up` e abra o link que aparecer para entrar na conta.

### 2. Instale o Tailscale no celular

1. Instale o app **Tailscale** pela Play Store (Android) ou App Store (iPhone).
2. Entre com **a mesma conta** que usou no PC.
3. Ative a conexão. O celular pede para criar uma VPN: aceite. O Tailscale só manda por ela o tráfego entre os seus aparelhos; o resto da internet do celular continua igual.

Na lista de aparelhos do app você deve ver o nome do seu PC.

### 3. Ligue o modo remoto no Clipator

1. No app do Clipator no PC, abra **Configurações** e desça até **Modo remoto (celular)**.
2. Clique em **Ligar o modo remoto**. Deve aparecer "Ligado na porta 8766" e, embaixo, "Tailscale conectado".
3. **No Windows**, na primeira vez o Firewall pergunta se o Clipator pode usar a rede. Marque **Redes privadas** e clique em **Permitir acesso**. Se você fechou a janela sem permitir, veja [Problemas comuns](#problemas-comuns).

O modo remoto continua ligado quando você fecha e abre o Clipator, até você clicar em **Desligar**.

### 4. Conecte o celular

1. Ainda em Configurações, clique em **Conectar um celular**. Aparece um QR code.
2. Se houver duas abas, escolha **Tailscale (em casa e fora)**.
3. No celular, com o Tailscale ativo, abra a câmera e aponte para o QR code. Toque no link que aparecer.
4. A página do Clipator abre já conectada. No PC, o celular aparece em **Celulares conectados**.

Sem câmera? Abra no navegador do celular o endereço que aparece embaixo do QR code (algo como `http://100.101.102.103:8766`) e digite o **código** mostrado no PC.

O código vale **uma vez só** e por **10 minutos**. Se vencer, clique em **Gerar outro código**.

### 5. Deixe a página como um app (opcional)

No navegador do celular, use **Adicionar à tela inicial** (Android: menu ⋮; iPhone: botão de compartilhar do Safari). A página vira um ícone e abre em tela cheia, como um app.

## Usando no dia a dia

- O PC precisa estar **ligado, com o Clipator aberto** e com o Tailscale conectado. Configure o PC para não entrar em suspensão enquanto você quiser acessar de fora (no Windows: Configurações → Sistema → Energia → "Colocar em suspensão" → Nunca, na tomada).
- No celular, o Tailscale precisa estar **ativo** quando você abrir a página fora de casa.
- A página se atualiza sozinha: a cada 3 segundos quando algo está rodando, a cada 10 quando o PC está parado.
- Dentro de um vídeo, os cortes ficam nas abas **Shorts** e **Longos 16:9**, do de nota mais alta para o de nota mais baixa. Toque na imagem de um corte para ver a **prévia** (o trecho do vídeo original) e em **Selecionar** para escolher. Depois escolha o estilo na barra de baixo e toque em **Aprovar**.
- Para baixar um clip, abra o vídeo, vá na aba **Clips**, e toque em **Baixar**.

## Segurança

O modo remoto foi feito para ficar fechado por padrão:

- **Desligado até você ligar.** Ele só liga pelo app do PC.
- **Só a sua rede.** A página só atende aparelhos da rede de casa, do próprio PC e do seu Tailscale. Um IP da internet é recusado, mesmo que alguém abra a porta no roteador.
- **Pareamento por QR code.** Cada celular entra uma vez com um código de uso único, que vence em 10 minutos e é cancelado depois de 8 tentativas erradas. O PC guarda só um resumo (hash) da chave de cada celular, em `.clipator/remoto.json` no workspace.
- **Acesso limitado.** O celular não lê nem grava arquivos do PC, não muda configurações, não apaga nada e só aceita links do YouTube e da Twitch (nunca um caminho de arquivo do PC).
- **Você tira o acesso quando quiser.** Em Configurações → Modo remoto → Celulares conectados, clique em **Tirar acesso**. Pelo celular, use **Desconectar este celular** no fim da página inicial.

Se perder o celular, tire o acesso dele no PC e, se quiser, remova o aparelho também no painel do Tailscale ([login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines)).

## HTTPS com `tailscale serve` (opcional, avançado)

A página funciona por `http://` porque o próprio Tailscale já criptografa a conexão entre os aparelhos. Se quiser um endereço com `https://` (e o modo offline da página adicionada à tela inicial), o Tailscale pode servir o Clipator com certificado:

1. No painel do Tailscale, em **DNS**, ative **MagicDNS** e **HTTPS Certificates**.
2. No PC, rode:
   ```bash
   tailscale serve --bg 8766
   ```
   O comando mostra o endereço, algo como `https://meu-pc.tail1234.ts.net`.
3. No celular, abra esse endereço e digite o código de pareamento que o Clipator mostra no PC (o QR code aponta para o endereço `http://`, então aqui o código é digitado).

Para desfazer: `tailscale serve reset`. Use `serve`, **nunca** `tailscale funnel`: o funnel publica a porta na internet aberta.

## Problemas comuns

**"O PC não respondeu" no celular.**
Confira, nesta ordem: o PC está ligado e não suspenso; o Clipator está aberto; o modo remoto está ligado; o Tailscale está conectado no PC e ativo no celular, com a mesma conta.

**O painel diz "O Tailscale está instalado mas desconectado".**
Abra o Tailscale no PC e entre na conta (no Linux, `sudo tailscale up`). Depois clique em **Gerar outro código**.

**A aba Tailscale não aparece, só Wi-Fi.**
O Clipator não achou o Tailscale conectado. Confira o passo 1. Se instalou agora, desligue e ligue o modo remoto.

**Funciona em casa, mas não na rua.**
Você provavelmente pareou pelo endereço do Wi-Fi. Gere outro código e leia o QR da aba **Tailscale**. O celular guarda o acesso por endereço, então cada endereço pede um pareamento.

**No Windows, o celular não conecta nem em casa.**
O Firewall bloqueou o Clipator. Abra "Permitir um aplicativo pelo Firewall do Windows", procure o Python ou o Clipator e marque **Privada**. Confira também se a sua rede Wi-Fi está marcada como **Rede privada** nas configurações de rede do Windows.

**"Não deu para abrir a porta 8766".**
Outro programa já usa essa porta. Desligue o modo remoto, feche o Clipator, abra o arquivo `.clipator/remoto.json` dentro do seu workspace (por padrão `~/Clipator`) e troque `"porta": 8766` por outra, como `8770`. Abra o Clipator e ligue o modo remoto de novo.

**"Código inválido ou vencido".**
O código vale 10 minutos e uma vez só. Clique em **Gerar outro código** no PC.

## Para desenvolvedores

- Motor: `motor/src/clipator/remoto.py` (pareamento, endereços, servidor) e `motor/src/clipator/api_remoto.py` (a API do celular, em `/m/api`).
- Página: `motor/src/clipator/remoto_web/`, HTML, CSS e JS sem build.
- App: `app/src/renderer/src/components/ModoRemoto.tsx`.
- Testes: `motor/tests/test_remoto.py`.
- A API do app continua só em `127.0.0.1`. Detalhes de arquitetura em [requisitos-arquitetura.md](requisitos-arquitetura.md#modo-remoto-celular).
