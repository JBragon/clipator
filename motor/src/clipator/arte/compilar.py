"""Da DA resolvida para o que as peças consomem: CSS, cadeia de filtros do FFmpeg, ficha das cenas e legenda.

- `css(r)`: variáveis `--da-*` (cores com o irmão `-rgb` para usar com alfa, fontes, escala, curvas, durações,
  grade, gradientes) e classes utilitárias `.da-<papel>`. Entra na camada de cenas e nos templates HyperFrames.
- `filtro_tratamento(r)`: a correção de cor do vídeo (eq, colortemperature, lut3d, unsharp, noise, vignette).
- `para_ficha(r)`: ajustes para a `Ficha` das cenas animadas (direcao.py).
- `para_legenda(r, formato)` e `para_cartela(r)`: campos do estilo (models.Legenda/Cartela) tirados da DA.
- `aplicar_no_estilo(estilo, r)`: troca os valores `da:<token>` de um estilo e, com `da: true` na legenda ou na
  cartela, preenche o que o estilo não disse.
- `escrever_build(r)`: grava arte/build/{da.resolvida.json, da.css, DA.md}.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from . import cores as C
from .carregar import Resolvida, para_json

ENTRADA_FICHA = {"sobe": "sobe", "desliza": "desliza", "escala": "escala", "mascara": "mascara", "fade": "fade",
                 "digita": "fade"}


def _rgb(h: str) -> str:
    r, g, b = C.hex_rgb(h)
    return f"{r}, {g}, {b}"


def _bezier(c) -> str:
    return "cubic-bezier(" + ", ".join(f"{v:g}" for v in c) + ")"


def variaveis(r: Resolvida) -> dict[str, str]:
    da = r.da
    v: dict[str, str] = {"--da-lado": "min(var(--largura, 100vw), var(--altura, 100vh))"}
    for nome, h in r.tokens.items():
        k = nome.replace("_", "-")
        v[f"--da-cor-{k}"] = h
        v[f"--da-cor-{k}-rgb"] = _rgb(h)
    for nome, css in r.gradientes_css.items():
        v[f"--da-gradiente-{nome.replace('_', '-')}"] = css
    for nome, p in da.tipografia.papeis.items():
        k = nome.replace("_", "-")
        v[f"--da-fonte-{k}"] = f"'{p.familia}', {p.reserva}"
        v[f"--da-peso-{k}"] = str(p.peso)
        v[f"--da-espacamento-{k}"] = f"{p.espacamento:g}em"
        v[f"--da-entrelinha-{k}"] = f"{p.entrelinha:g}"
    for nome, f in da.tipografia.escala.items():
        v[f"--da-escala-{nome}"] = f"calc(var(--da-lado) * {f:g})"
    for nome, c in da.movimento.curvas.items():
        v[f"--da-curva-{nome}"] = _bezier(c)
    for nome, d in da.movimento.duracoes.items():
        v[f"--da-dur-{nome}"] = f"{d:g}s"
    v["--da-escalonamento"] = f"{da.movimento.escalonamento:g}s"
    lay = da.layout
    v["--da-margem"] = f"calc(var(--da-lado) * {lay.margem:g})"
    v["--da-calha"] = f"calc(var(--da-lado) * {lay.calha:g})"
    v["--da-raio"] = f"calc(var(--da-lado) * {lay.raio:g})"
    v["--da-traco"] = f"max(1px, calc(var(--da-lado) * {lay.traco:g}))"
    v["--da-colunas"] = str(lay.colunas)
    if lay.sombra:
        s = lay.sombra
        v["--da-sombra"] = (f"calc(var(--da-lado) * {s.dx:g}) calc(var(--da-lado) * {s.dy:g}) "
                            f"calc(var(--da-lado) * {s.desfoque:g}) rgba({_rgb(r.cor(s.cor))}, {s.alfa:g})")
    else:
        v["--da-sombra"] = "none"
    leg = da.legenda
    v["--da-legenda-tamanho"] = f"calc(var(--da-lado) * {leg.tamanho:g})"
    for campo in ("cor", "cor_destaque", "cor_falada"):
        h = r.campo(f"legenda.{campo}")
        if h:
            v[f"--da-legenda-{campo.replace('_', '-')}"] = h
    return v


def css(r: Resolvida) -> str:
    """O bloco CSS da DA: `:root` com as variáveis e as classes de papel tipográfico."""
    v = variaveis(r)
    raiz = ":root {\n" + "".join(f"  {k}: {val};\n" for k, val in v.items()) + "}\n"
    classes = []
    for nome, p in r.da.tipografia.papeis.items():
        k = nome.replace("_", "-")
        regras = [f"font-family: var(--da-fonte-{k})", f"font-weight: {p.peso}", f"letter-spacing: {p.espacamento:g}em",
                  f"line-height: {p.entrelinha:g}"]
        if p.italico:
            regras.append("font-style: italic")
        if p.caixa_alta:
            regras.append("text-transform: uppercase")
        if p.condensar != 1:
            regras.append(f"transform: scaleX({p.condensar:g}); transform-origin: left center")
        classes.append(f".da-{k} {{ {'; '.join(regras)}; }}")
    return f"/* direção de arte: {r.da.nome or 'sem nome'} */\n{raiz}" + "\n".join(classes) + "\n"


def filtro_tratamento(r: Resolvida) -> str | None:
    """Cadeia de filtros do FFmpeg para o vídeo (None se tudo está neutro)."""
    t = r.da.tratamento
    partes: list[str] = []
    if t.lut and r.pasta is not None:
        lut = r.pasta / t.lut if (r.pasta / t.lut).exists() else r.pasta / "luts" / t.lut
        if lut.exists():
            from ..media import escape_filter_path

            caminho = escape_filter_path(lut)
            if t.intensidade_lut >= 0.999:
                partes.append(f"lut3d=file='{caminho}'")
            else:
                partes.append(f"split[_a][_b];[_b]lut3d=file='{caminho}'[_l];[_a][_l]blend=all_opacity="
                              f"{t.intensidade_lut:.3f}")
    eq = []
    if abs(t.contraste - 1) > 1e-3:
        eq.append(f"contrast={t.contraste:.3f}")
    if abs(t.brilho) > 1e-3:
        eq.append(f"brightness={t.brilho:.3f}")
    if abs(t.saturacao - 1) > 1e-3:
        eq.append(f"saturation={t.saturacao:.3f}")
    if abs(t.gama - 1) > 1e-3:
        eq.append(f"gamma={t.gama:.3f}")
    if eq:
        partes.append("eq=" + ":".join(eq))
    if abs(t.temperatura) > 0.5:
        kelvin = 6500 - 30 * t.temperatura  # 100 -> 3500 K (quente); -100 -> 9500 K (fria)
        partes.append(f"colortemperature=temperature={kelvin:.0f}:mix={min(1.0, abs(t.temperatura) / 100):.2f}:pl=1")
    if t.nitidez > 1e-3:
        partes.append(f"unsharp=5:5:{t.nitidez:.2f}:5:5:0")
    if t.grao > 0.5:
        partes.append(f"noise=c0s={t.grao:.0f}:c0f=t+u")
    if t.vinheta > 1e-3:
        partes.append(f"vignette=angle={t.vinheta:.3f}")
    return ",".join(partes) if partes else None


def para_ficha(r: Resolvida) -> dict[str, Any]:
    """Os ajustes da `direcao.Ficha` (cenas animadas) tirados da DA."""
    p = r.da.cor.paleta
    da = r.da
    return {
        "fundo": p["fundo"], "superficie": p["superficie"], "texto": p["texto"], "texto_suave": p["texto_suave"],
        "primaria": p["primaria"], "destaque": p["destaque"], "bom": p["positivo"], "ruim": p["negativo"],
        "fonte_titulo": da.tipografia.papeis["titulo"].familia, "fonte_corpo": da.tipografia.papeis["corpo"].familia,
        "entrada": ENTRADA_FICHA.get(da.movimento.entrada, "sobe"), "sons": dict(da.som.efeitos),
        "volume_sons": da.som.volume_efeitos,
    }


def para_legenda(r: Resolvida, formato: str = "9:16") -> dict[str, Any]:
    """Campos de models.Legenda (tamanhos em px num quadro de 1080 no lado menor, como o resto do estilo)."""
    leg = r.da.legenda
    papel = r.papel(leg.papel)
    tam = max(10, round(leg.tamanho * 1080))
    out: dict[str, Any] = {
        "modo": {"karaoke": "palavra-a-palavra", "palavra": "uma-palavra", "bloco": "frase"}[leg.estilo],
        "fonte": papel.familia, "tamanho": tam, "cor": r.campo("legenda.cor") or "#FFFFFF",
        "destaque": r.campo("legenda.cor_destaque") or r.cor("primaria"),
        "caixa_alta": papel.caixa_alta, "italico": papel.italico,
        "linhas": max(1, min(3, 1 if leg.estilo == "palavra" else leg.max_linhas)),
        "max_palavras_por_linha": max(1, math.ceil(leg.max_palavras / max(1, leg.max_linhas))),
        "altura_relativa": leg.y_horizontal if formato == "16:9" else leg.y_vertical,
        "animacao": "pop" if leg.animacao == "pop" else "nenhuma",
    }
    if leg.contorno:
        out["contorno"] = r.campo("legenda.contorno.cor") or "#000000"
        out["espessura_contorno"] = round(min(20.0, leg.contorno.espessura * tam), 1)
    else:
        out["espessura_contorno"] = 0
    out["sombra"] = round(min(10.0, (leg.sombra.dy + leg.sombra.desfoque / 2) * tam), 1) if leg.sombra else 0
    if leg.caixa:
        out["fundo"] = r.campo("legenda.caixa.cor")
        out["opacidade_fundo"] = leg.caixa.alfa
    return out


def para_cartela(r: Resolvida) -> dict[str, Any]:
    papel = r.papel("titulo")
    return {"fonte": papel.familia, "tamanho": max(10, round(r.da.tipografia.escala.get("h2", 0.06) * 1080)),
            "cor": r.cor("texto"), "fundo": r.cor("superficie"), "destaque": r.cor("primaria"),
            "caixa_alta": papel.caixa_alta}


def _trocar_tokens(valor: Any, r: Resolvida, chave: str = "") -> Any:
    if isinstance(valor, dict):
        return {k: _trocar_tokens(v, r, k) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_trocar_tokens(v, r, chave) for v in valor]
    if isinstance(valor, str) and valor.startswith("da:"):
        token = valor[3:].strip()
        if "fonte" in chave and token in r.da.tipografia.papeis:
            return r.da.tipografia.papeis[token].familia
        if token in r.da.tipografia.papeis and token not in r.tokens:
            return r.da.tipografia.papeis[token].familia
        if token in r.tokens:
            return r.tokens[token]
        if r.campos.get(token):  # caminho de um campo de cor: da:legenda.cor
            return r.campos[token]
        return valor
    return valor


def aplicar_no_estilo(estilo, r: Resolvida | None):
    """O estilo com os tokens `da:` trocados pelos valores da DA (sem DA, os do predefinido base).

    `legenda: {da: true}` (e o mesmo na cartela) preenche com a DA tudo o que o estilo não escreveu.
    """
    from ..models import Estilo

    if r is None:
        from .carregar import carregar_preset

        try:
            r = carregar_preset("base")
        except Exception:  # noqa: BLE001
            return estilo
    dados = estilo.model_dump()
    leg_extra = (estilo.legenda.model_extra or {}) if hasattr(estilo.legenda, "model_extra") else {}
    if leg_extra.get("da") is True:
        explicitos = estilo.legenda.model_fields_set
        dados["legenda"] = {**{k: v for k, v in para_legenda(r, estilo.formato).items() if k not in explicitos},
                            **{k: v for k, v in dados["legenda"].items() if k in explicitos}}
    cart_extra = (estilo.cartela.model_extra or {}) if hasattr(estilo.cartela, "model_extra") else {}
    if cart_extra.get("da") is True:
        explicitos = estilo.cartela.model_fields_set
        dados["cartela"] = {**{k: v for k, v in para_cartela(r).items() if k not in explicitos},
                            **{k: v for k, v in dados["cartela"].items() if k in explicitos}}
    dados = _trocar_tokens(dados, r)
    return Estilo.model_validate(dados)


def resumo_md(r: Resolvida, achados=None, estado: dict | None = None) -> str:
    """DA.md: a DA em texto, para a pessoa ler e para a IA receber como contexto."""
    da = r.da
    p = da.cor.paleta
    linhas = [f"# Direção de arte: {da.nome or 'sem nome'}", ""]
    if estado:
        st = "APROVADA em " + estado.get("aprovada_em", "")[:10] if estado.get("aprovada") else "RASCUNHO, não aprovada"
        linhas += [f"Revisão {estado.get('revisao', 1)} · {st}", ""]
    if da.conceito.frase:
        linhas += [f"> {da.conceito.frase}", ""]
    if da.conceito.palavras_chave:
        linhas += ["Palavras-chave: " + ", ".join(da.conceito.palavras_chave), ""]
    linhas += ["## Cores", "", "| token | hex | contraste com o fundo |", "|---|---|---|"]
    for nome, h in p.items():
        k = C.contraste(h, p["fundo"])
        linhas.append(f"| `{nome}` | {h} | {k:.2f}:1 ({C.nivel_wcag(k)}) |".replace(".", ",", 1))
    linhas += ["", "Série dos gráficos: " + ", ".join(f"`serie-{i}` {h}" for i, h in enumerate(r.serie_hex, 1)), ""]
    linhas += ["## Tipografia", "", "| papel | família | peso | caixa alta | espaçamento | entrelinha |", "|---|---|---|---|---|---|"]
    for nome, pp in da.tipografia.papeis.items():
        linhas.append(f"| `{nome}` | {pp.familia} | {pp.peso} | {'sim' if pp.caixa_alta else 'não'} | {pp.espacamento:g} em "
                      f"| {pp.entrelinha:g} |")
    linhas += ["", "Escala (fração do lado menor → px em 1080): " + ", ".join(
        f"{n} {f:g} → {round(f * 1080)} px" for n, f in da.tipografia.escala.items()), ""]
    mv = da.movimento
    linhas += ["## Movimento", "", f"Entrada `{mv.entrada}`, saída `{mv.saida}`, transição padrão `{mv.transicao_padrao}` "
               f"(permitidas: {', '.join(mv.transicoes)}).",
               "Durações: " + ", ".join(f"{n} {d:g} s" for n, d in mv.duracoes.items()) + f"; escalonamento {mv.escalonamento:g} s.",
               "Curvas: " + ", ".join(f"{n} {_bezier(c)}" for n, c in mv.curvas.items()) + "."]
    for pr in mv.principios:
        linhas.append(f"- {pr}")
    leg = da.legenda
    linhas += ["", "## Legenda", "", f"Estilo `{leg.estilo}`, papel `{leg.papel}`, tamanho {leg.tamanho:g} "
               f"({round(leg.tamanho * 1080)} px em 1080), cor {r.campo('legenda.cor')}, palavra falada "
               f"{r.campo('legenda.cor_destaque')}, até {leg.max_palavras} palavras em {leg.max_linhas} linha(s), centro em "
               f"y {leg.y_vertical:g} no vertical."]
    t = da.graficos.tarja
    linhas += ["", "## Grafismos", "", f"Tarja `{t.estilo}` em `{t.posicao}`; selo `{da.graficos.selo.estilo}`; "
               f"crédito “{da.graficos.credito.prefixo.strip()} …” em {da.graficos.credito.tamanho:g}."]
    th = da.thumbnail
    linhas += ["", "## Thumbnail", "", f"Até {th.max_palavras} palavras em `{th.papel}` ({th.tamanho:g} da altura), cor "
               f"{r.campo('thumbnail.cor')}, palavra-chave {r.campo('thumbnail.cor_destaque')}, fundo `{th.fundo}`; canto "
               f"reservado: {th.canto_reservado.replace('_', ' ')}."]
    filtro = filtro_tratamento(r)
    linhas += ["", "## Tratamento do vídeo", "", (f"`{filtro}`" if filtro else "neutro") +
               (" (aplicado nos clips do canal)" if da.tratamento.aplicar_nos_clips else " (não aplicado nos clips)")]
    linhas += ["", "## Som", "", da.som.identidade or "—",
               "Efeitos: " + ", ".join(f"{k} → {v}" for k, v in da.som.efeitos.items()) +
               f"; loudness {da.som.loudness.alvo_lufs:g} LUFS."]
    if da.conceito.faca:
        linhas += ["", "## Faça", ""] + [f"- {x}" for x in da.conceito.faca]
    if da.conceito.nao_faca:
        linhas += ["", "## Não faça", ""] + [f"- {x}" for x in da.conceito.nao_faca]
    if achados:
        from .validar import texto as _texto

        linhas += ["", "## Validação", "", "```", _texto(achados), "```"]
    return "\n".join(linhas) + "\n"


def escrever_build(r: Resolvida, achados=None, estado: dict | None = None) -> Path:
    if r.pasta is None:
        raise ValueError("a DA não tem pasta (é um predefinido): nada a gravar")
    build = r.pasta / "build"
    build.mkdir(parents=True, exist_ok=True)
    (build / "da.resolvida.json").write_text(json.dumps(para_json(r), ensure_ascii=False, indent=2), encoding="utf-8")
    (build / "da.css").write_text(css(r), encoding="utf-8")
    (r.pasta / "DA.md").write_text(resumo_md(r, achados, estado), encoding="utf-8")
    return build
