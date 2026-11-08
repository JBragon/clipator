"""Validador da DA: o que bloqueia (erro), o que pede uma decisão (aviso) e o que só informa (nota).

Cada achado diz onde está, o que está errado em números e como corrigir. Os limiares:

- Contraste (WCAG 2.x): texto sobre fundo e sobre superfície abaixo de 3:1 é erro; abaixo de 7:1, aviso (vídeo é
  visto no celular, muitas vezes ao sol). Texto suave abaixo de 4,5:1, aviso. Cor que carrega texto, 4,5:1.
- Legibilidade no celular: com o lado menor do quadro ocupando a largura da tela (390 pt), uma fração f rende
  f × 390 pt. Texto de apoio abaixo de 0,022 (≈ 8,6 pt) e legenda abaixo de 0,04 (≈ 15,6 pt) só se leem com zoom.
- Cores "quase idênticas": ΔE 2000 abaixo de 3 entre duas cores vivas da paleta é sobra de troca de cor.
- Zona segura: a faixa da legenda tem de caber na zona `uniao` (o pior caso de Shorts, Reels e TikTok), e a tarja
  não pode dividir o lugar com ela.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from . import cores as C
from . import zonas
from .carregar import Resolvida
from .tipos import arquivo_da_fonte, familias

Nivel = Literal["erro", "aviso", "nota"]
MINIMO_APOIO = 0.022
MINIMO_LEGENDA = 0.04
RECOMENDADO_LEGENDA = 0.052
QUASE_IDENTICAS = 3.0
SERIE_MINIMA = 6


@dataclass
class Achado:
    nivel: Nivel
    codigo: str
    onde: str
    mensagem: str
    como_corrigir: str = ""

    def linha(self) -> str:
        marca = {"erro": "ERRO ", "aviso": "AVISO", "nota": "NOTA "}[self.nivel]
        dica = f"\n        → {self.como_corrigir}" if self.como_corrigir else ""
        return f"  {marca} {self.onde}: {self.mensagem}{dica}"

    def para_dict(self) -> dict:
        return asdict(self)


def _fmt(x: float, casas: int = 2) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def validar(r: Resolvida, alterada_apos_aprovacao: bool = False, extras_fontes=None) -> list[Achado]:
    a: list[Achado] = []

    def add(nivel: Nivel, codigo: str, onde: str, msg: str, dica: str = "") -> None:
        a.append(Achado(nivel, codigo, onde, msg, dica))

    da = r.da
    p = da.cor.paleta

    # ---- tokens que não existem -----------------------------------------------------------------
    nomes = ", ".join(sorted(k for k in r.tokens if not k.startswith(("neutro-", "serie-"))))
    for campo, valor in r.erros_de_token:
        add("erro", "token.inexistente", campo, f"“{valor}” não é uma cor da paleta nem um hex",
            f"use um destes nomes: {nomes}, neutro-1…{len(da.cor.neutros)}, serie-1…{len(da.cor.serie)} ou #RRGGBB")
    for caminho in ("legenda.papel", "graficos.tarja.papel_nome", "graficos.tarja.papel_cargo", "graficos.selo.papel",
                    "graficos.credito.papel", "thumbnail.papel"):
        obj = da
        for parte in caminho.split("."):
            obj = getattr(obj, parte)
        if obj not in da.tipografia.papeis:
            add("erro", "papel.inexistente", caminho, f"o papel “{obj}” não existe em tipografia.papeis",
                "papéis disponíveis: " + ", ".join(da.tipografia.papeis))

    # ---- contraste ------------------------------------------------------------------------------
    def razao(c1: str, c2: str) -> float:
        return C.contraste(c1, c2)

    for sobre in ("fundo", "superficie"):
        k = razao(p["texto"], p[sobre])
        if k < 3:
            add("erro", "contraste.texto", f"cor.paleta.texto × {sobre}", f"contraste {_fmt(k)}:1 (mínimo 3:1)",
                f"tente {C.ajustar_para_contraste(p['texto'], p[sobre], 7)} para o texto")
        elif k < 7:
            add("aviso", "contraste.texto", f"cor.paleta.texto × {sobre}",
                f"contraste {_fmt(k)}:1; para celular mire em 7:1",
                f"tente {C.ajustar_para_contraste(p['texto'], p[sobre], 7)}")
    k = razao(p["texto_suave"], p["fundo"])
    if k < 4.5:
        add("aviso", "contraste.texto_suave", "cor.paleta.texto_suave × fundo", f"contraste {_fmt(k)}:1 (mire 4,5:1)",
            f"tente {C.ajustar_para_contraste(p['texto_suave'], p['fundo'], 4.5)}")
    k = razao(p["primaria"], p["fundo"])
    if k < 3:
        add("aviso", "contraste.primaria", "cor.paleta.primaria × fundo",
            f"contraste {_fmt(k)}:1: a primária só serve como bloco chapado com texto por cima, nunca como cor de texto",
            "se ela pinta palavras, escureça ou clareie: " + C.ajustar_para_contraste(p["primaria"], p["fundo"], 4.5))
    for nome in ("positivo", "negativo", "alerta"):
        k = razao(p[nome], p["fundo"])
        if k < 3:
            add("aviso", "contraste.semantica", f"cor.paleta.{nome} × fundo", f"contraste {_fmt(k)}:1 (mire 3:1 ou mais)",
                f"tente {C.ajustar_para_contraste(p[nome], p['fundo'], 3.5)}")
    if C.contraste(p["fundo"], p["superficie"]) > 2.2:
        add("nota", "superficie.distante", "cor.paleta.superficie",
            f"a superfície está a {_fmt(C.contraste(p['fundo'], p['superficie']))}:1 do fundo; o normal é 1,1 a 1,6:1 "
            "(um degrau acima, não outra cor)")

    # ---- cores quase idênticas ------------------------------------------------------------------
    vivas = {n: h for n, h in p.items() if n not in ("fundo", "superficie", "texto", "texto_suave") and C.croma(h) > 20}
    nomes_v = list(vivas)
    for i, n1 in enumerate(nomes_v):
        for n2 in nomes_v[i + 1:]:
            if vivas[n1] == vivas[n2]:
                continue  # igual de propósito (destaque = primária) não é sobra
            d = C.delta_e(vivas[n1], vivas[n2])
            if d < QUASE_IDENTICAS:
                add("aviso", "cor.quase_identicas", f"cor.paleta.{n1} e {n2}",
                    f"{vivas[n1]} e {vivas[n2]} são quase a mesma cor (ΔE {_fmt(d, 1)}); parece sobra de uma troca de cor",
                    "ou iguale as duas de propósito, ou afaste uma delas (ΔE ≥ 10)")
    vivas_tela = [h for n, h in vivas.items() if n in ("primaria", "destaque", "secundaria") and C.croma(h) > 45]
    if len({h for h in vivas_tela}) >= 3:
        add("nota", "cor.muitas_vivas", "cor.paleta",
            "primária, secundária e destaque são as três vivas: cuide para não usar as três na mesma tela")

    # ---- série dos gráficos ---------------------------------------------------------------------
    if len(da.cor.serie) < SERIE_MINIMA:
        add("erro", "serie.curta", "cor.serie", f"{len(da.cor.serie)} cores; gráficos pedem no mínimo {SERIE_MINIMA}",
            "complete com cores da paleta pelo nome (primaria, destaque, texto…) e hex afastados em matiz")
    vistos: dict[str, int] = {}
    for i, h in enumerate(r.serie_hex, 1):
        if h in vistos:
            add("erro", "serie.repetida", f"cor.serie[{i}]", f"{h} repete a cor {vistos[h]} da série",
                "cada série de gráfico precisa de uma cor própria")
        vistos.setdefault(h, i)
        k = razao(h, p["fundo"])
        if k < 3:
            add("aviso", "serie.contraste", f"cor.serie[{i}]", f"{h} a {_fmt(k)}:1 do fundo (mire 3:1)",
                f"tente {C.ajustar_para_contraste(h, p['fundo'], 3)}")
    for i in range(1, len(r.serie_hex)):
        d = C.delta_e(r.serie_hex[i - 1], r.serie_hex[i])
        if d < 10 and r.serie_hex[i - 1] != r.serie_hex[i]:
            add("aviso", "serie.vizinhas", f"cor.serie[{i}] e [{i + 1}]",
                f"barras vizinhas quase iguais (ΔE {_fmt(d, 1)})", "intercale uma cor clara e uma escura")
    for i, item in enumerate(da.cor.serie, 1):
        if C.e_hex(item):
            nome, _, d = C.mais_proxima(item, dict(p))
            if d < 6:
                add("aviso", "serie.hex_da_paleta", f"cor.serie[{i}]",
                    f"{C.normalizar_hex(item)} é quase a cor “{nome}” da paleta (ΔE {_fmt(d, 1)})",
                    f"escreva “{nome}” no lugar do hex: assim a série acompanha quando a paleta mudar")

    # ---- gradientes -----------------------------------------------------------------------------
    for nome, g in da.cor.gradientes.items():
        hexes = {r.cor(c) for c, _ in g.paradas}
        if len(hexes) == 1:
            add("aviso", "gradiente.chapado", f"cor.gradientes.{nome}", f"todas as paradas resolvem para {hexes.pop()}",
                "troque uma das paradas ou apague o gradiente")

    # ---- tipografia -----------------------------------------------------------------------------
    fams = familias(r)
    if len(fams) > 2:
        add("aviso", "tipografia.familias", "tipografia.papeis",
            f"{len(fams)} famílias ({', '.join(fams)}); o limite que funciona é duas (título/legenda e corpo/dados)")
    for fam in fams:
        if arquivo_da_fonte(fam, r, extras_fontes) is None:
            add("aviso", "tipografia.fonte_ausente", "tipografia.papeis",
                f"não achei o arquivo da fonte “{fam}” (procurei em arte/fontes, nas fontes do canal, nas baixadas e nas "
                "embutidas); a prancha e a thumbnail usam uma fonte reserva",
                "ponha o .ttf em arte/fontes/ (só fontes com licença livre, como OFL) ou rode `clipator preparar` "
                "para baixar o pacote de fontes")
    esc = da.tipografia.escala
    for degrau in ("display", "h1", "h2", "h3", "corpo", "nota"):
        if degrau not in esc:
            add("erro", "escala.falta", f"tipografia.escala.{degrau}", "degrau obrigatório ausente")
    ordem = [esc[d] for d in ("display", "h1", "h2", "h3", "corpo", "nota") if d in esc]
    if any(ordem[i] <= ordem[i + 1] for i in range(len(ordem) - 1)):
        add("aviso", "escala.ordem", "tipografia.escala", "os degraus não descem em ordem (display > h1 > h2 > h3 > "
            "corpo > nota)")
    if esc.get("corpo", 1) < 0.028:
        add("aviso", "legivel.corpo", "tipografia.escala.corpo",
            f"{_fmt(esc['corpo'], 3)} do lado menor ≈ {_fmt(zonas.pt_no_celular(esc['corpo']), 1)} pt no celular; "
            "abaixo de 0,028 o texto corrido cansa", "suba para 0,03")
    for caminho, valor in (("tipografia.escala.nota", esc.get("nota", 1)),
                           ("graficos.tarja.tamanho_cargo", da.graficos.tarja.tamanho_cargo),
                           ("graficos.credito.tamanho", da.graficos.credito.tamanho)):
        if valor < MINIMO_APOIO:
            add("aviso", "legivel.apoio", caminho,
                f"{_fmt(valor, 3)} do lado menor ≈ {_fmt(zonas.pt_no_celular(valor), 1)} pt no celular: só se lê com zoom",
                f"suba para {_fmt(MINIMO_APOIO, 3)} ou mais (recomendado 0,026)")

    # ---- legenda --------------------------------------------------------------------------------
    leg = da.legenda
    if leg.tamanho < MINIMO_LEGENDA:
        add("aviso", "legivel.legenda", "legenda.tamanho",
            f"{_fmt(leg.tamanho, 3)} ≈ {_fmt(zonas.pt_no_celular(leg.tamanho), 1)} pt no celular: pequena demais",
            f"suba para {_fmt(RECOMENDADO_LEGENDA, 3)} ou mais")
    cor_leg = r.campo("legenda.cor") or "#FFFFFF"
    if leg.caixa is not None:
        atras = r.campo("legenda.caixa.cor") or p["fundo"]
        k = razao(cor_leg, atras)
        if k < 4.5:
            add("erro" if k < 3 else "aviso", "legenda.contraste", "legenda.cor × legenda.caixa.cor",
                f"contraste {_fmt(k)}:1 dentro da caixa", f"tente {C.ajustar_para_contraste(cor_leg, atras, 7)}")
        if leg.caixa.alfa < 0.6:
            add("aviso", "legenda.caixa_transparente", "legenda.caixa.alfa",
                f"caixa a {int(leg.caixa.alfa * 100)}%: sobre vídeo claro a legenda some", "suba para 0,75 ou mais")
    elif leg.contorno is not None:
        k = razao(cor_leg, r.campo("legenda.contorno.cor") or "#000000")
        if k < 4.5:
            add("aviso", "legenda.contorno", "legenda.cor × legenda.contorno.cor",
                f"contraste {_fmt(k)}:1 entre a letra e o contorno: a legenda some sobre o vídeo",
                "contorno escuro com letra clara (ou o contrário)")
        if leg.contorno.espessura < 0.06:
            add("aviso", "legenda.contorno_fino", "legenda.contorno.espessura",
                f"{_fmt(leg.contorno.espessura)} do tamanho da fonte é fino para segurar a legenda sobre qualquer vídeo",
                "0,08 a 0,12 costuma bastar")
    else:
        add("aviso", "legenda.sem_protecao", "legenda",
            "sem contorno nem caixa: a legenda fica ilegível quando o vídeo atrás tem a mesma claridade",
            "ponha `contorno: {cor: neutro-1, espessura: 0.1}` ou uma `caixa`")
    destaque_leg = r.campo("legenda.cor_destaque")
    if destaque_leg and destaque_leg == cor_leg:
        add("aviso", "legenda.destaque_igual", "legenda.cor_destaque", "a palavra falada fica da mesma cor das outras")
    if leg.estilo != "bloco" and leg.max_palavras > 6:
        add("aviso", "legenda.palavras", "legenda.max_palavras", f"{leg.max_palavras} palavras por vez no estilo "
            f"{leg.estilo}: no vertical, 3 a 5 leem melhor")

    zona = zonas.zona_segura("uniao", "vertical")
    faixa = zonas.faixa_da_legenda(r, "vertical")
    if not zona.contem(faixa):
        add("aviso", "zona.legenda", "legenda.y_vertical",
            f"com {leg.max_linhas} linha(s) a legenda ocupa y {_fmt(faixa.y)}–{_fmt(faixa.y1)} e a zona livre de "
            f"Shorts, Reels e TikTok vai de {_fmt(zona.y)} a {_fmt(zona.y1)}",
            "aproxime y_vertical de 0,6, reduza o tamanho ou use menos linhas")
    if leg.largura_max > zona.w + 1e-6:
        add("nota", "zona.legenda_largura", "legenda.largura_max",
            f"no vertical a zona livre deixa só {_fmt(zona.w)} da largura; o Clipator quebra a linha antes de passar")
    livre = zonas.area_livre(r, "vertical")
    if livre.h < 0.2:
        add("aviso", "zona.sobra_pouco", "legenda", f"a faixa da legenda deixa só {int(livre.h * 100)}% da altura "
            "para tarja, títulos e gráficos")
    tarja = zonas.lugar_da_tarja(r, "vertical")
    if tarja.intersecao(faixa) > 0:
        add("aviso", "zona.tarja_legenda", "graficos.tarja.posicao", "no vertical a tarja e a legenda dividem o mesmo "
            "lugar", "troque a posição da tarja ou suba a legenda")

    # ---- grafismos ------------------------------------------------------------------------------
    t = da.graficos.tarja
    fundo_t = r.campo("graficos.tarja.cor_fundo") or p["fundo"]
    for campo in ("cor_nome", "cor_cargo"):
        h = r.campo(f"graficos.tarja.{campo}")
        if h and razao(h, fundo_t) < 4.5:
            add("aviso", "tarja.contraste", f"graficos.tarja.{campo}", f"{_fmt(razao(h, fundo_t))}:1 sobre o fundo da "
                "tarja (mire 4,5:1)", f"tente {C.ajustar_para_contraste(h, fundo_t, 4.5)}")
    if t.estilo != "linha" and t.alfa_fundo < 0.6:
        add("aviso", "tarja.transparente", "graficos.tarja.alfa_fundo",
            f"fundo da tarja a {int(t.alfa_fundo * 100)}%: o nome some sobre vídeo claro")
    s = da.graficos.selo
    if s.estilo == "chapado":
        k = razao(r.campo("graficos.selo.cor_texto") or "#000", r.campo("graficos.selo.cor_fundo") or "#FFF")
        if k < 4.5:
            add("aviso", "selo.contraste", "graficos.selo", f"texto do selo a {_fmt(k)}:1 do fundo dele")

    # ---- movimento ------------------------------------------------------------------------------
    mv = da.movimento
    for nome in ("entrada", "saida", "enfase", "suave"):
        if nome not in mv.curvas:
            add("erro", "movimento.curva_falta", f"movimento.curvas.{nome}", "curva obrigatória ausente")
    quicam = [n for n, c in mv.curvas.items() if c[1] > 1 or c[3] > 1 or c[1] < 0 or c[3] < 0]
    if quicam:
        add("nota", "movimento.overshoot", "movimento.curvas",
            f"{', '.join(quicam)} passa(m) do ponto e volta(m) (y fora de 0–1): o movimento “quica”")
    for nome in ("micro", "curta", "media", "longa"):
        if nome not in mv.duracoes:
            add("erro", "movimento.duracao_falta", f"movimento.duracoes.{nome}", "duração obrigatória ausente")
    d = [mv.duracoes.get(n, 0) for n in ("micro", "curta", "media", "longa")]
    if all(n in mv.duracoes for n in ("micro", "curta", "media", "longa")) and not (d[0] <= d[1] <= d[2] <= d[3]):
        add("aviso", "movimento.ordem", "movimento.duracoes", "as durações deveriam crescer: micro ≤ curta ≤ media ≤ longa")
    if mv.duracoes.get("media", 0.4) > 1.2:
        add("aviso", "movimento.lento", "movimento.duracoes.media",
            f"{_fmt(mv.duracoes['media'])} s para um bloco entrar é lento para vídeo curto (0,3–0,6 s)")
    if mv.transicao_padrao not in mv.transicoes:
        add("erro", "movimento.transicao", "movimento.transicao_padrao",
            f"“{mv.transicao_padrao}” não está em movimento.transicoes ({', '.join(mv.transicoes)})")
    if not mv.principios:
        add("nota", "movimento.principios", "movimento.principios", "sem princípios escritos; uma ou duas frases "
            "(“a forma entra antes do texto”) ajudam a IA a animar no estilo")

    # ---- tratamento -----------------------------------------------------------------------------
    tr = da.tratamento
    if tr.saturacao > 1.35:
        add("aviso", "tratamento.saturacao", "tratamento.saturacao", f"{_fmt(tr.saturacao)} deixa a pele laranja")
    if 0 < tr.saturacao < 0.5:
        add("nota", "tratamento.saturacao", "tratamento.saturacao", "quase preto e branco: confira a pele na prancha")
    if tr.contraste > 1.3:
        add("aviso", "tratamento.contraste", "tratamento.contraste", f"{_fmt(tr.contraste)} estoura as altas e afunda "
            "as sombras em vídeo comprimido (1,04–1,15 costuma bastar)")
    if tr.lut and r.pasta is not None and not (r.pasta / tr.lut).exists() and not (r.pasta / "luts" / tr.lut).exists():
        add("erro", "tratamento.lut", "tratamento.lut", f"não achei {tr.lut} em arte/ nem em arte/luts/")

    # ---- thumbnail ------------------------------------------------------------------------------
    th = da.thumbnail
    if th.max_palavras > 6:
        add("aviso", "thumb.palavras", "thumbnail.max_palavras", f"{th.max_palavras} palavras não leem numa miniatura "
            "de celular (3 a 4 é o que funciona)")
    if th.canto_reservado == "nenhum":
        add("nota", "thumb.canto", "thumbnail.canto_reservado", "sem canto reservado: o selo de duração do YouTube "
            "pode cobrir o texto no canto inferior direito")
    if th.tamanho < 0.1:
        add("aviso", "thumb.tamanho", "thumbnail.tamanho", "título da thumb pequeno demais para a miniatura")

    # ---- som ------------------------------------------------------------------------------------
    if not -18 <= da.som.loudness.alvo_lufs <= -9:
        add("nota", "som.loudness", "som.loudness.alvo_lufs", f"{_fmt(da.som.loudness.alvo_lufs, 1)} LUFS está longe "
            "do que as plataformas tocam (perto de −14)")

    # ---- conceito -------------------------------------------------------------------------------
    c = da.conceito
    if not c.frase.strip():
        add("aviso", "conceito.frase", "conceito.frase", "sem a frase da DA: escreva material + cor + tipografia + "
            "sensação numa frase")
    if len(c.faca) < 3 or len(c.nao_faca) < 3:
        add("nota", "conceito.regras", "conceito.faca / nao_faca", "menos de três regras em faça ou não faça: a IA "
            "anima melhor com regras concretas")
    if alterada_apos_aprovacao:
        add("aviso", "estado.alterada", "arte/direcao.yaml", "a DA mudou depois de aprovada",
            "rode `clipator arte revisar` e aprove de novo (`clipator arte aprovar`)")
    return a


def resumo(achados: list[Achado]) -> tuple[int, int, int]:
    return (sum(x.nivel == "erro" for x in achados), sum(x.nivel == "aviso" for x in achados),
            sum(x.nivel == "nota" for x in achados))


def texto(achados: list[Achado]) -> str:
    e, av, n = resumo(achados)
    if not achados:
        return "DA válida: nenhum erro, aviso ou nota."
    ordem = {"erro": 0, "aviso": 1, "nota": 2}
    corpo = "\n".join(x.linha() for x in sorted(achados, key=lambda x: ordem[x.nivel]))
    veredito = "REPROVADA" if e else "VÁLIDA"
    return f"{veredito}: {e} erro(s), {av} aviso(s), {n} nota(s)\n{corpo}"
