---
name: cenas-da-fala
description: "Diz ao planejador de cenas qual tela usar para cada tipo de fala."
---
# Cenas que seguem a fala

Cada cena ilustra um trecho que a pessoa diz; a âncora é copiada da fala, nunca do texto da tela.

## Qual cena para qual fala
- Diz um número, valor, porcentagem ou grandeza → `numero` (valor + rótulo curto do que é).
- Diz duas ou mais datas em sequência → `linha_do_tempo`, um item por data ("2019: abriu a loja").
- Enumera ("primeiro…", "segundo…", "são três coisas") → `lista`, com os itens na ordem dita.
- Conta o que alguém disse ("ele falou que…", aspas) → `citacao` com o autor, só com palavras ditas.
- Coloca uma coisa contra outra ("antes e depois", "isso ou aquilo", "mais do que") → `comparacao`.
- Cita uma pessoa ou empresa pela primeira vez → `nome` (tarja), com o rótulo de quem é se foi dito.
- Cita um lugar → `local`.
- Muda de assunto ou abre o clip → `titulo` (gancho curto).
- Solta uma palavra muito forte → `palavra` (uma palavra só).
- Avisa de um risco ("cuidado", "golpe", "atenção") → `alerta`.

## Regras
- Uma cena a cada 3 segundos no máximo; nunca duas ao mesmo tempo.
- A cena entra quando o trecho começa a ser dito e dura o tempo de ler (1,5 a 6 s).
- Sem fato novo: nome, número e citação só se foram ditos no clip.
- Na dúvida entre duas cenas, a mais simples ganha.
