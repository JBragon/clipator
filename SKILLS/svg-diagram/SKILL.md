---
name: svg-diagram
description: Generate professional SVG diagrams that render cleanly on GitHub and browsers. Architecture, flowchart, sequence, component and pipeline diagrams. Use for ANY request involving diagrams or visualizations.
---

> Skill de terceiro criada por pkt-lab, licenca MIT. Repositorio oficial: https://github.com/pkt-lab/svg-diagram

Este e o fallback offline. O download normal busca o SKILL.md completo e atualizado direto do repositorio oficial. Se voce esta lendo isso, o GitHub estava inacessivel na hora do download.

Resumo do metodo completo, que vive no repositorio oficial: planeje a grade antes de desenhar, inventarie caixas e conexoes, posicione em colunas e linhas com 200px e 120px de espacamento minimo, dimensione caixas pelo texto com 9px por caractere em fonte 14. Use estrutura em camadas, defs, background, containers, nodes, labels e connections por ultimo para setas nunca ficarem atrás de caixa. Setas saem e chegam na borda das caixas, nunca cruzam outra caixa ou texto, rotas ortogonais com path. Fonte Arial, 14 a 16px em caixas, 11 a 12px em anotacoes. Proibido foreignObject, script, image externa e JavaScript, GitHub remove tudo isso. Valide o SVG com scripts/validate_svg.py do repositorio e inspecione o PNG renderizado antes de entregar.