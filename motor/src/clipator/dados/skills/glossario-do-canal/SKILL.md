---
name: glossario-do-canal
description: "Nomes e termos que a transcrição erra entram como dica para o Whisper e como correção automática."
termos: []
---
# Glossário do canal

Esta skill junta os termos do campo `termos` (no topo deste arquivo) ao glossário de cada canal: eles
entram como dica para o Whisper e corrigem palavras parecidas depois da transcrição (pelo som e pela
grafia), sem IA e sem internet.

## Como usar
- O glossário principal fica no `canal.md` (campo `glossario`) ou na caixa "Glossário do canal" do passo 1.
- Ponha aqui só os termos que valem para todos os canais (marcas, nomes do seu nicho, gírias).
- Um termo por item, do jeito certo de escrever: `["Clipator", "HyperFrames", "Whindersson"]`.
- Evite palavras comuns: elas trocariam palavras certas por engano.

Modelo do `canal.md`:

```yaml
glossario: [Vanato, Flow Podcast, CQC]
```
