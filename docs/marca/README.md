# Marca do Clipator

O símbolo é um C amarelo com um recorte de play que se abre em dois cortes. Todos os arquivos saem de uma geometria só, em `gerar_marca.py`.

| Arquivo | Uso |
| --- | --- |
| `clipator-icone.svg` / `.png` | Ícone do app: ladrilho escuro com o C amarelo |
| `clipator-simbolo.svg` | Só o C amarelo, sem fundo |
| `clipator-horizontal-escuro.svg` | Ícone + nome em branco, para fundo escuro |
| `clipator-horizontal-claro.svg` | Ícone + nome em grafite, para fundo claro |
| `clipator-uma-cor-branco.svg` / `-preto.svg` | Versão de uma cor só |

Cores: amarelo `#ECEC2E`, grafite `#141518`. O nome usa a Montserrat ExtraBold (SIL OFL 1.1), a mesma que vem no motor, convertida em contorno.

Para regerar tudo, inclusive `app/resources/icon.png`, `app/resources/icon.ico` e o favicon do app:

```bash
uv run docs/marca/gerar_marca.py
```
