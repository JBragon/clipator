"""Edição de um clip no editor do passo 3: um documento não destrutivo (edicao.json na pasta do clip).

O documento tem itens na linha do tempo do clip (segundos do clip renderizado, não do original),
cada um numa faixa: efeito (zoom, tremor, flash, filtros de cor, desfoque, vinheta, transição),
texto (sobreposto), sticker (emoji) e som (efeito sonoro). Cortes, trecho, legenda e estilo
continuam no clip.yaml, então um clip antigo abre com o documento vazio e nada se perde.

O render lê o documento e monta os filtros do FFmpeg (`filtros_video` e `sons_da_edicao`).
As sugestões (`heuristica` e `sugerir_ia`) devolvem itens que o usuário aceita ou descarta;
todo tempo é validado contra a duração do clip.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import Estilo, LayoutArte
from .timeline import Timeline
from .workspace import ProjetoWS, fontes_dir

ARQUIVO = "edicao.json"
VERSAO = 1

Faixa = Literal["efeito", "texto", "sticker", "som", "cena"]
TIPOS: dict[str, Faixa] = {
    "zoom": "efeito", "zoom-lento": "efeito", "tremor": "efeito", "flash": "efeito", "pb": "efeito",
    "sepia": "efeito", "contraste": "efeito", "saturacao": "efeito", "desfoque": "efeito", "vinheta": "efeito",
    "transicao": "efeito",
    "texto": "texto",
    "emoji": "sticker",
    "sticker": "sticker",
    "som": "som",
    "cena": "cena",  # direção de arte (direcao.py): desenhada na camada de cenas, não nos filtros daqui
}
# duração padrão e parâmetros padrão de cada tipo (o editor usa os mesmos)
PADRAO: dict[str, tuple[float, dict[str, Any]]] = {
    "zoom": (1.2, {"escala": 1.25}),
    "zoom-lento": (3.0, {"escala": 1.15}),
    "tremor": (0.5, {"forca": 12}),
    "flash": (0.15, {"cor": "white"}),
    "pb": (2.0, {}),
    "sepia": (2.0, {}),
    "contraste": (2.0, {"valor": 1.35}),
    "saturacao": (2.0, {"valor": 1.6}),
    "desfoque": (1.0, {"forca": 8}),
    "vinheta": (3.0, {}),
    "transicao": (0.3, {"cor": "black"}),
    "texto": (2.0, {"texto": "TEXTO", "posicao": "topo", "tamanho": 0.07, "cor": "white", "fundo": True}),
    "emoji": (1.5, {"emoji": "🔥", "posicao": "topo-direita", "tamanho": 0.18}),
    "sticker": (2.0, {"ref": "pacote:fluent-animado/fire", "posicao": "topo-direita", "tamanho": 0.28, "rotacao": 0,
                      "entrada": "pop", "repetir": True}),
    "som": (0.5, {"nome": "whoosh", "volume": 0.8}),
    "cena": (3.0, {"cena": "palavra", "texto": "TEXTO"}),
}
ENTRADAS = ("nenhuma", "pop", "fade", "deslizar")
_REF = re.compile(r"^(pacote|canal|web|cta):[\w\-./ ]{1,160}$")
CAMPOS_CHAMADA = ("texto", "texto2", "cor", "cor_texto", "idioma", "preset")  # só para refs "cta:" (ver cta.py)
CHAMADA_AUTOMATICA = ("nenhuma", "inicio", "fim", "inicio-e-fim")
POSICOES = ("topo", "centro", "baixo", "topo-esquerda", "topo-direita", "baixo-esquerda", "baixo-direita")
CORES = {"white": "white", "black": "black", "yellow": "yellow", "red": "red", "branco": "white", "preto": "black",
         "amarelo": "yellow", "vermelho": "red"}
_COR_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Item(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    tipo: str
    inicio: float  # segundos do clip; validar() prende dentro do clip
    fim: float
    params: dict[str, Any] = Field(default_factory=dict)
    origem: Literal["usuario", "ia", "heuristica"] = "usuario"
    motivo: str = ""

    @property
    def faixa(self) -> Faixa:
        return TIPOS[self.tipo]


class Edicao(BaseModel):
    versao: int = VERSAO
    revisao: int = 0  # sobe a cada gravação: o editor recarrega quando outra pessoa (a IA) muda
    itens: list[Item] = Field(default_factory=list)
    cenas_planejadas: bool = False  # o render já propôs as cenas uma vez (apagar todas não faz voltar)
    destaques: list[str] = Field(default_factory=list)  # palavras que a legenda destaca (Melhorar com IA)
    layout_arte: LayoutArte | None = None  # a composição que o usuário escolheu: anda com as versões, como as cenas


def estilo_com_layout(estilo: Estilo, doc: "Edicao") -> Estilo:
    """O estilo com a composição escolhida no clip por cima (só o que o usuário definiu)."""
    if doc.layout_arte is None or not estilo.direcao.ativa:
        return estilo
    mudou = doc.layout_arte.model_dump(exclude_none=True)
    return estilo.model_copy(update={"direcao": estilo.direcao.model_copy(update=mudou)})


# ---- documento -----------------------------------------------------------------------------
def carregar(pasta_clip: Path) -> Edicao:
    """O documento do clip; um clip antigo (sem edicao.json) abre vazio."""
    p = pasta_clip / ARQUIVO
    if not p.exists():
        return Edicao()
    dados = json.loads(p.read_text(encoding="utf-8"))
    return Edicao.model_validate(dados)


def salvar(pasta_clip: Path, ed: Edicao, duracao: float | None = None) -> Edicao:
    if duracao is not None:
        ed = ed.model_copy(update={"itens": validar(ed.itens, duracao)})
    ed.revisao += 1
    tmp = pasta_clip / (ARQUIVO + ".tmp")
    tmp.write_text(json.dumps(ed.model_dump(mode="json"), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(pasta_clip / ARQUIVO)
    return ed


def _num(v: Any, padrao: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return padrao
    return max(lo, min(hi, x))


def _cor(v: Any, padrao: str) -> str:
    s = str(v or "").strip()
    if s in CORES:
        return CORES[s]
    return s if _COR_HEX.match(s) else padrao


def _posicao_livre(base: dict[str, Any], p: dict[str, Any]) -> None:
    """x, y: o centro do objeto em fração do quadro (arrastado na prévia); sem eles vale a `posicao`."""
    try:
        x, y = float(p["x"]), float(p["y"])
    except (KeyError, TypeError, ValueError):
        return
    if x == x and y == y:  # NaN fica de fora
        base["x"], base["y"] = round(min(1.0, max(0.0, x)), 4), round(min(1.0, max(0.0, y)), 4)


def normalizar_params(tipo: str, p: dict[str, Any]) -> dict[str, Any]:
    """Só os parâmetros conhecidos, dentro dos limites (o que vier da IA ou da tela passa por aqui)."""
    base = dict(PADRAO[tipo][1])
    if tipo == "cena":
        from .direcao import normalizar_cena

        return normalizar_cena(p if p.get("cena") else {**base, **p})
    if tipo in ("texto", "emoji", "sticker"):
        _posicao_livre(base, p)
    if tipo in ("zoom", "zoom-lento"):
        base["escala"] = _num(p.get("escala"), base["escala"], 1.02, 1.8)
    elif tipo == "tremor":
        base["forca"] = _num(p.get("forca"), base["forca"], 2, 40)
    elif tipo in ("flash", "transicao"):
        base["cor"] = _cor(p.get("cor"), base["cor"])
    elif tipo in ("contraste", "saturacao"):
        base["valor"] = _num(p.get("valor"), base["valor"], 0.2, 3.0)
    elif tipo == "desfoque":
        base["forca"] = _num(p.get("forca"), base["forca"], 1, 30)
    elif tipo == "texto":
        base["texto"] = str(p.get("texto", base["texto"]))[:120] or base["texto"]
        base["posicao"] = p.get("posicao") if p.get("posicao") in POSICOES else base["posicao"]
        base["tamanho"] = _num(p.get("tamanho"), base["tamanho"], 0.02, 0.2)
        base["cor"] = _cor(p.get("cor"), base["cor"])
        base["fundo"] = bool(p.get("fundo", base["fundo"]))
    elif tipo == "emoji":
        base["emoji"] = str(p.get("emoji") or base["emoji"])[:8]
        base["posicao"] = p.get("posicao") if p.get("posicao") in POSICOES else base["posicao"]
        base["tamanho"] = _num(p.get("tamanho"), base["tamanho"], 0.05, 0.5)
    elif tipo == "sticker":
        ref = str(p.get("ref") or "")
        base["ref"] = ref if _REF.match(ref) and ".." not in ref else base["ref"]
        base["posicao"] = p.get("posicao") if p.get("posicao") in POSICOES else base["posicao"]
        base["tamanho"] = _num(p.get("tamanho"), base["tamanho"], 0.05, 0.8)
        base["rotacao"] = _num(p.get("rotacao"), 0, -180, 180)
        if p.get("esticar") is not None and abs(_num(p.get("esticar"), 1.0, 0.25, 4.0) - 1) > 0.01:
            base["esticar"] = round(_num(p.get("esticar"), 1.0, 0.25, 4.0), 3)  # altura / largura em relação ao original
        base["entrada"] = p.get("entrada") if p.get("entrada") in ENTRADAS else base["entrada"]
        base["repetir"] = bool(p.get("repetir", base["repetir"]))
        if base["ref"].startswith("cta:"):
            for k in CAMPOS_CHAMADA:
                v = p.get(k)
                if isinstance(v, str) and v.strip():
                    base[k] = v.strip()[:40] if k in ("texto", "texto2") else v.strip()[:12]
            base["som"] = bool(p.get("som", True))
            if base["ref"] == "cta:texto":  # fonte e formatação do texto livre (cta.formato valida)
                from .cta import formato

                base.update(formato(p))
    elif tipo == "som":
        nome = str(p.get("nome") or base["nome"])
        base["nome"] = nome if re.fullmatch(r"[\w\-. ]{1,80}", nome) and ".." not in nome else base["nome"]
        base["volume"] = _num(p.get("volume"), base["volume"], 0.0, 2.0)
    return base


def validar(itens: list[Item] | list[dict], duracao: float) -> list[Item]:
    """Descarta tipos desconhecidos e prende os tempos dentro do clip (mínimo de 0,05 s)."""
    out: list[Item] = []
    vistos: set[str] = set()
    for bruto in itens:
        try:
            it = bruto if isinstance(bruto, Item) else Item.model_validate(bruto)
        except Exception:  # noqa: BLE001 - item malformado (da IA, por exemplo) só fica de fora
            continue
        if it.tipo not in TIPOS:
            continue
        if it.inicio >= duracao - 0.05:
            continue
        ini = max(0.0, it.inicio)
        fim = min(duracao, it.fim)
        if fim - ini < 0.05:
            continue
        if it.id in vistos:
            it = it.model_copy(update={"id": uuid.uuid4().hex[:8]})
        vistos.add(it.id)
        out.append(it.model_copy(update={"inicio": round(ini, 3), "fim": round(fim, 3),
                                          "params": normalizar_params(it.tipo, it.params)}))
    return sorted(out, key=lambda i: (i.inicio, i.tipo))


# ---- render: filtros do FFmpeg ---------------------------------------------------------------
def _entre(a: float, b: float, var: str = "t") -> str:
    return f"between({var},{a:.3f},{b:.3f})"


def _esc_expr(s: str) -> str:
    """Vírgulas dentro de expressões precisam de escape no grafo do FFmpeg."""
    return s.replace(",", "\\,")


def _escape_caminho(p: Path) -> str:
    from .media import escape_filter_path

    return escape_filter_path(p)


def _xy_item(params: dict[str, Any], w: str, h: str) -> tuple[str, str]:
    """Canto do objeto: pelo centro arrastado na prévia (x, y) ou pela posição fixa."""
    if "x" in params and "y" in params:
        return f"W*{float(params['x']):.4f}-{w}/2", f"H*{float(params['y']):.4f}-{h}/2"
    return _xy(params["posicao"], w, h)


def _xy(posicao: str, w: str, h: str) -> tuple[str, str]:
    m = "W*0.05"
    x = {"esquerda": m, "direita": f"W-{w}-{m}"}
    xs = next((v for k, v in x.items() if posicao.endswith(k)), f"(W-{w})/2")
    if posicao.startswith("topo"):
        ys = "H*0.12"
    elif posicao.startswith("baixo"):
        ys = f"H*0.72-{h}"
    else:
        ys = f"(H-{h})/2"
    return xs, ys


def _emoji_png(emoji: str, tamanho_px: int, pasta: Path) -> Path | None:
    """Desenha o emoji colorido num PNG (Pillow + a fonte de emoji do sistema). None se não houver fonte."""
    from PIL import Image, ImageDraw, ImageFont

    fontes = [Path("C:/Windows/Fonts/seguiemj.ttf"), Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
              Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"), Path("/usr/share/fonts/noto/NotoColorEmoji.ttf")]
    fonte = next((f for f in fontes if f.exists()), None)
    if fonte is None:
        return None
    nome = hashlib.sha1(f"{emoji}-{tamanho_px}".encode()).hexdigest()[:12]
    destino = pasta / f"emoji-{nome}.png"
    if destino.exists():
        return destino
    pasta.mkdir(parents=True, exist_ok=True)
    try:
        tam_fonte = 109 if "Noto" in fonte.name else 128  # a Noto colorida só tem 109 px
        f = ImageFont.truetype(str(fonte), tam_fonte)
        img = Image.new("RGBA", (tam_fonte * 2, tam_fonte * 2), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((tam_fonte // 2, tam_fonte // 2), emoji, font=f, embedded_color=True)
        caixa = img.getbbox()
        if not caixa:
            return None
        img = img.crop(caixa)
        lado = max(img.size)
        img = img.resize((max(1, round(img.width * tamanho_px / lado)), max(1, round(img.height * tamanho_px / lado))))
        img.save(destino)
        return destino
    except Exception:  # noqa: BLE001 - sem emoji colorido: o render segue sem o sticker
        return None


def filtros_video(ed: Edicao, entrada: str, out_w: int, out_h: int, fps: float, pasta_clip: Path,
                  primeiro_indice: int, pasta_canal: Path | None = None) -> tuple[list[str], list[str], str]:
    """(entradas extras, partes do grafo, rótulo de saída) com os efeitos visuais do documento.

    `entrada` é o rótulo do vídeo já reenquadrado (tempo 0 = início do clip).
    """
    itens = ed.itens
    partes: list[str] = []
    entradas: list[str] = []
    atual = entrada
    n = 0

    def rotulo() -> str:
        nonlocal n
        n += 1
        return f"ved{n}"

    # zoom, zoom lento e tremor numa passada só do zoompan (o tempo vem do número do quadro)
    zooms = [i for i in itens if i.tipo in ("zoom", "zoom-lento", "tremor")]
    if zooms:
        tq = f"(on/{fps:g})"
        termos, sx, sy = [], [], []
        for i in zooms:
            ent = _entre(i.inicio, i.fim, tq)
            if i.tipo == "zoom":
                termos.append(f"{i.params['escala'] - 1:.3f}*{ent}")
            elif i.tipo == "zoom-lento":
                termos.append(f"{i.params['escala'] - 1:.3f}*clip(({tq}-{i.inicio:.3f})/{max(0.05, i.fim - i.inicio):.3f},0,1)*{ent}")
            else:
                f = i.params["forca"]
                termos.append(f"{min(0.25, 2.5 * f / out_w):.4f}*{ent}")  # aproxima para o tremor não mostrar borda
                sx.append(f"{f:.1f}*sin(on*2.1)*{ent}")
                sy.append(f"{f * 0.7:.1f}*cos(on*1.7)*{ent}")
        z = "1+" + "+".join(termos)
        x = "(iw-iw/zoom)/2" + "".join(f"+{s}" for s in sx)
        y = "(ih-ih/zoom)/2" + "".join(f"+{s}" for s in sy)
        saida = rotulo()
        partes.append(f"[{atual}]zoompan=z='{_esc_expr(z)}':x='{_esc_expr(x)}':y='{_esc_expr(y)}':d=1:"
                      f"s={out_w}x{out_h}:fps={fps:g}[{saida}]")
        atual = saida

    filtros: list[str] = []
    for i in itens:
        ent = _esc_expr(_entre(i.inicio, i.fim))
        if i.tipo == "pb":
            filtros.append(f"hue=s=0:enable='{ent}'")
        elif i.tipo == "sepia":
            filtros.append(f"colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131:enable='{ent}'")
        elif i.tipo == "contraste":
            filtros.append(f"eq=contrast={i.params['valor']:.2f}:enable='{ent}'")
        elif i.tipo == "saturacao":
            filtros.append(f"eq=saturation={i.params['valor']:.2f}:enable='{ent}'")
        elif i.tipo == "desfoque":
            filtros.append(f"boxblur={int(i.params['forca'])}:enable='{ent}'")
        elif i.tipo == "vinheta":
            filtros.append(f"vignette=PI/4:enable='{ent}'")
        elif i.tipo in ("flash", "transicao"):
            # sobe e desce em dois degraus (o drawbox não varia a opacidade com o tempo)
            meio = (i.inicio + i.fim) / 2
            cor = i.params["cor"]
            forte = 0.85 if i.tipo == "flash" else 1.0
            filtros.append(f"drawbox=x=0:y=0:w=iw:h=ih:t=fill:color={cor}@{forte * 0.55:.2f}:enable='{_esc_expr(_entre(i.inicio, meio))}'")
            filtros.append(f"drawbox=x=0:y=0:w=iw:h=ih:t=fill:color={cor}@{forte:.2f}:enable='{_esc_expr(_entre(meio - 0.02, meio + 0.02))}'")
            filtros.append(f"drawbox=x=0:y=0:w=iw:h=ih:t=fill:color={cor}@{forte * 0.55:.2f}:enable='{_esc_expr(_entre(meio, i.fim))}'")
    textos = [i for i in itens if i.tipo == "texto"]
    if textos:
        pasta_txt = pasta_clip / "edicao-textos"
        pasta_txt.mkdir(parents=True, exist_ok=True)
        fonte = fontes_dir() / "Anton-Regular.ttf"
        for i in textos:
            # o texto vai num arquivo (textfile): nada do que o usuário digita entra no grafo
            arq = pasta_txt / f"{i.id}.txt"
            arq.write_text(i.params["texto"], encoding="utf-8")
            tam = max(10, int(out_h * i.params["tamanho"]))
            xs, ys = _xy_item(i.params, "text_w", "text_h")
            caixa = f":box=1:boxcolor=black@0.55:boxborderw={max(4, tam // 4)}" if i.params["fundo"] else ":borderw=3:bordercolor=black"
            filtros.append(f"drawtext=fontfile='{_escape_caminho(fonte)}':textfile='{_escape_caminho(arq)}':"
                           f"expansion=none:fontsize={tam}:fontcolor={i.params['cor']}{caixa}:x={_esc_expr(xs)}:y={_esc_expr(ys)}:"
                           f"enable='{_esc_expr(_entre(i.inicio, i.fim))}'")
    if filtros:
        saida = rotulo()
        partes.append(f"[{atual}]{','.join(filtros)}[{saida}]")
        atual = saida

    k = primeiro_indice
    for i in (x for x in itens if x.tipo == "sticker"):
        from . import stickers

        origem = stickers.resolver(i.params["ref"], pasta_canal, params=i.params)
        if origem is None:
            continue  # sticker que não existe mais (ou pacote não baixado): o render segue sem ele
        arq, animado = stickers.para_render(origem, pasta_clip / "edicao-stickers")
        repetir = animado and i.params["repetir"]
        entradas += (["-ignore_loop", "0", "-i", str(arq)] if repetir else ["-i", str(arq)] if animado
                     else ["-loop", "1", "-i", str(arq)])
        a, b = i.inicio, i.fim
        lado = max(16, int(out_w * i.params["tamanho"]) // 2 * 2)
        cadeia = [f"setpts=PTS-STARTPTS+{a:.3f}/TB", f"scale={lado}:-1", "format=rgba"]
        if i.params.get("esticar"):
            cadeia.insert(2, f"scale=iw:trunc(ih*{float(i.params['esticar']):.3f}/2)*2")
        rot = i.params["rotacao"]
        if abs(rot) >= 0.5:
            ang = f"{rot:.1f}*PI/180"
            cadeia.append(f"rotate={ang}:c=none:ow=rotw({ang}):oh=roth({ang})")
        if i.params["entrada"] in ("pop", "fade", "deslizar"):
            cadeia.append(f"fade=in:st={a:.3f}:d=0.25:alpha=1")
        rot_s = rotulo()
        partes.append(f"[{k}:v]{','.join(cadeia)}[{rot_s}]")
        xs, ys = _xy_item(i.params, "w", "h")
        prog = f"min(1,(t-{a:.3f})/0.3)"
        if i.params["entrada"] == "pop":
            ys = f"{ys}-H*0.04*sin(PI*{prog})"
        elif i.params["entrada"] == "deslizar":
            xs = f"{xs}+(1-{prog})*W*0.6"
        saida = rotulo()
        partes.append(f"[{atual}][{rot_s}]overlay=x={_esc_expr(xs)}:y={_esc_expr(ys)}:eof_action={'pass' if repetir else 'repeat'}:"
                      f"enable='{_esc_expr(_entre(a, b))}'[{saida}]")
        atual = saida
        k += 1
    for i in (x for x in itens if x.tipo == "emoji"):
        png = _emoji_png(i.params["emoji"], max(16, int(out_w * i.params["tamanho"])), pasta_clip / "edicao-stickers")
        if png is None:
            continue
        entradas += ["-loop", "1", "-i", str(png)]
        xs, ys = _xy_item(i.params, "w", "h")
        saida = rotulo()
        partes.append(f"[{atual}][{k}:v]overlay=x={_esc_expr(xs)}:y={_esc_expr(ys)}:shortest=0:eof_action=pass:"
                      f"enable='{_esc_expr(_entre(i.inicio, i.fim))}'[{saida}]")
        atual = saida
        k += 1
    return entradas, partes, atual


def sons_da_edicao(ed: Edicao, bases: list[Path]) -> tuple[list[tuple[str, float]], dict[str, Path]]:
    """Eventos (chave, segundo) e arquivos dos itens de som, no formato de sons.filtro_mix."""
    from . import sons

    from . import cta

    evs, arquivos = [], {}
    for i in ed.itens:
        if i.tipo == "sticker" and str(i.params.get("ref", "")).startswith("cta:") and i.params.get("som", True):
            m = cta.MODELOS.get(i.params["ref"][4:])  # o som da chamada, no momento do clique
            p = sons.resolver(m.som[0], bases) if m and m.som else None
            if p is not None and i.inicio + m.som[1] < i.fim:
                arquivos[f"edicao-{i.id}"] = p
                evs.append((f"edicao-{i.id}", i.inicio + m.som[1]))
            continue
        if i.tipo != "som":
            continue
        p = sons.resolver(i.params["nome"], bases)
        if p is None:
            continue
        chave = f"edicao-{i.id}"
        arquivos[chave] = p
        evs.append((chave, i.inicio))
    return evs, arquivos


# ---- sugestões ------------------------------------------------------------------------------
_PALAVRAS_FORTES = re.compile(
    r"\b(nunca|ningu[eé]m|sempre|absurdo|incr[ií]vel|segredo|verdade|mentira|erro|dinheiro|milh(ão|ões|oes)|"
    r"bilh(ão|ões|oes)|morreu|chocante|bizarro|pol[eê]mic\w*|exclusiv\w*|urgente|cuidado|aten[cç][aã]o|"
    r"nossa|caramba|meu deus|olha|gente)\b", re.IGNORECASE)
_EMOJI_POR_TEMA = [
    (re.compile(r"dinheiro|milh|bilh|reais|grana|pagou|lucro", re.I), "💰"),
    (re.compile(r"risada|kkk|rindo|engra[cç]ad", re.I), "😂"),
    (re.compile(r"absurdo|chocante|bizarro|meu deus|nossa", re.I), "😱"),
    (re.compile(r"verdade|segredo|exclusiv", re.I), "🤫"),
    (re.compile(r"erro|mentira|cuidado|aten[cç][aã]o", re.I), "⚠️"),
    (re.compile(r"fogo|quente|pol[eê]mic|briga", re.I), "🔥"),
]


def palavras_do_clip(projeto: ProjetoWS, tl: Timeline) -> list[dict]:
    from .subtitles import palavras_do_clip as _pc
    from .transcribe import palavras

    trans = projeto.transcricao() or {}
    return _pc(palavras(trans), tl) if trans else []


def _indice_stickers() -> dict[str, str]:
    """palavra em português -> ref do sticker instalado (para sugerir pelo que é falado)."""
    from . import stickers

    try:
        m = stickers.manifesto()
    except Exception:  # noqa: BLE001
        return {}
    pasta = stickers.pasta_pacote()
    out: dict[str, str] = {}
    for s in m["stickers"]:
        if not (pasta / s["arquivo"]).is_file():
            continue
        for p in s["palavras"]:
            out.setdefault(p.lower(), f"pacote:{s['id']}")
    return out


def _sem_acento(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def chamadas(dur: float, modo: str, idioma: str = "pt") -> list[Item]:
    """O "Inscreva-se" automático no começo e/ou no fim do clip, quando o canal pede (canal.md: chamada_automatica)."""
    from . import cta

    m = cta.MODELOS["inscreva-se"]
    if modo not in CHAMADA_AUTOMATICA or modo == "nenhuma" or dur < m.duracao + 2:
        return []
    params = {"ref": "cta:inscreva-se", "posicao": "baixo", "tamanho": 0.55, "entrada": "nenhuma", "repetir": False,
              "idioma": idioma if idioma in ("pt", "en") else "pt"}
    out = []
    if modo in ("inicio", "inicio-e-fim"):
        out.append(Item(tipo="sticker", inicio=1.0, fim=1.0 + m.duracao, params=dict(params), origem="heuristica",
                        motivo="Chamada para se inscrever logo no começo (ativada no canal)"))
    if modo in ("fim", "inicio-e-fim") and (modo == "fim" or dur >= 2 * m.duracao + 6):
        ini = max(0.0, dur - m.duracao - 0.3)
        out.append(Item(tipo="sticker", inicio=ini, fim=ini + m.duracao, params=dict(params), origem="heuristica",
                        motivo="Chamada para se inscrever no fim (ativada no canal)"))
    return out


def heuristica(pals: list[dict], tl: Timeline, sinais: dict | None = None, chamada: str = "nenhuma",
               idioma: str = "pt") -> list[Item]:
    """Sugestões sem IA: zoom nas palavras fortes, som nas emendas, sticker (ou emoji) no tema, zoom lento no começo."""
    indice = {_sem_acento(k): v for k, v in _indice_stickers().items() if len(k) >= 4}
    dur = tl.duracao
    out: list[Item] = [Item(tipo="zoom-lento", inicio=0, fim=min(3.0, dur), params={"escala": 1.12}, origem="heuristica",
                            motivo="Começo com movimento para segurar quem está rolando o feed")]
    ultimo_zoom, ultimo_emoji = -99.0, -99.0
    for w in pals:
        t = float(w["inicio"])
        if _PALAVRAS_FORTES.search(w["texto"]) and t - ultimo_zoom >= 4.0 and t > 1.0:
            out.append(Item(tipo="zoom", inicio=t, fim=min(dur, t + 1.0), params={"escala": 1.25}, origem="heuristica",
                            motivo=f"Palavra forte: “{w['texto'].strip()}”"))
            ultimo_zoom = t
        palavra = _sem_acento(re.sub(r"[^\w]", "", w["texto"]))
        if indice and palavra in indice and t - ultimo_emoji >= 5.0:
            out.append(Item(tipo="sticker", inicio=t, fim=min(dur, t + 2.0),
                            params={"ref": indice[palavra], "posicao": "topo-direita"}, origem="heuristica",
                            motivo=f"Sticker da palavra falada: “{w['texto'].strip()}”"))
            ultimo_emoji = t
            continue
        for re_, emoji in _EMOJI_POR_TEMA:
            if re_.search(w["texto"]) and t - ultimo_emoji >= 5.0:
                out.append(Item(tipo="emoji", inicio=t, fim=min(dur, t + 1.4), params={"emoji": emoji}, origem="heuristica",
                                motivo=f"Tema da fala: “{w['texto'].strip()}”"))
                ultimo_emoji = t
                break
    acc = 0.0
    for s, e in tl.trechos[:-1]:
        acc += e - s
        out.append(Item(tipo="som", inicio=max(0.0, acc - 0.15), fim=min(dur, acc + 0.4), params={"nome": "whoosh"},
                        origem="heuristica", motivo="Som na emenda de um corte interno"))
        out.append(Item(tipo="transicao", inicio=max(0.0, acc - 0.1), fim=min(dur, acc + 0.15), origem="heuristica",
                        motivo="Transição na emenda"))
    return validar(out + chamadas(dur, chamada, idioma), dur)


SCHEMA_EFEITOS = {
    "type": "object",
    "properties": {
        "efeitos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tipo": {"type": "string", "enum": sorted(TIPOS)},
                    "inicio": {"type": "number"},
                    "fim": {"type": "number"},
                    "texto": {"type": "string"},
                    "emoji": {"type": "string"},
                    "escala": {"type": "number"},
                    "som": {"type": "string"},
                    "sticker": {"type": "string"},
                    "motivo": {"type": "string"},
                },
                "required": ["tipo", "inicio", "fim", "texto", "emoji", "escala", "som", "sticker", "motivo"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["efeitos"],
    "additionalProperties": False,
}


def prompt_efeitos(pals: list[dict], dur: float, cortes: list[float], estilo_desc: str, canal_md: str,
                   stickers_disp: list[str] | None = None) -> str:
    stickers_disp = stickers_disp or []
    linhas = " ".join(f"[{w['inicio']:.2f}]{w['texto'].strip()}" for w in pals)[:14000]
    from . import sons

    return (
        "Você edita shorts de vídeo. Proponha efeitos para o clip abaixo, como um editor experiente: poucos e "
        "certeiros (no máximo 12), sem cobrir o rosto o tempo todo.\n"
        f"Duração do clip: {dur:.2f} s. Emendas de cortes internos em: {', '.join(f'{c:.2f}' for c in cortes) or 'nenhuma'}.\n"
        "Tipos: zoom (punch-in rápido na frase de impacto, escala 1.1–1.5), zoom-lento (escala 1.05–1.2), tremor, "
        "flash, pb, sepia, contraste, saturacao, desfoque, vinheta, transicao (nas emendas), texto (curto, em caixa "
        "alta, só para reforçar um número ou uma frase), sticker (animado, na palavra-chave; em 'sticker' ponha uma "
        f"destas palavras: {', '.join(stickers_disp[:80]) or 'nenhuma'}), emoji (só se nenhum sticker servir), "
        f"som (efeito sonoro; nomes: {', '.join(sons.NOMES)}).\n"
        "Use os tempos das palavras (segundos do clip, entre colchetes). Campos que não se aplicam ao tipo: "
        "texto, emoji, som e sticker vazios, escala 0. Em 'motivo', uma frase dizendo por quê.\n"
        f"Estilo do clip: {estilo_desc[:400]}\n"
        f"Canal: {canal_md[:1200]}\n\n"
        f"Transcrição com tempos:\n{linhas}"
    )


def de_resposta_ia(resp: Any, dur: float, indice: dict[str, str] | None = None) -> list[Item]:
    """Converte a resposta da IA em itens válidos (o que for inválido fica de fora).

    `indice` liga a palavra do sticker ao sticker instalado; sticker sem correspondência fica de fora.
    """
    indice = {_sem_acento(k): v for k, v in (indice or {}).items()}
    itens = []
    for e in (resp or {}).get("efeitos") or []:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS:
            continue
        tipo = e["tipo"]
        params: dict[str, Any] = {}
        if tipo == "texto":
            params["texto"] = e.get("texto") or ""
            if not params["texto"].strip():
                continue
        if tipo == "emoji":
            params["emoji"] = e.get("emoji") or ""
            if not params["emoji"].strip():
                continue
        if tipo in ("zoom", "zoom-lento") and e.get("escala"):
            params["escala"] = e["escala"]
        if tipo == "som":
            params["nome"] = e.get("som") or "whoosh"
        if tipo == "sticker":
            ref = indice.get(_sem_acento(str(e.get("sticker") or "")))
            if not ref:
                continue
            params["ref"] = ref
        try:
            ini, fim = float(e.get("inicio")), float(e.get("fim"))
        except (TypeError, ValueError):
            continue
        if not (0 <= ini < dur) or fim <= ini:
            continue
        itens.append(Item(tipo=tipo, inicio=ini, fim=fim, params=params, origem="ia", motivo=str(e.get("motivo") or "")[:200]))
    return validar(itens, dur)


def chamada_do_canal(projeto: ProjetoWS) -> tuple[str, str]:
    """(modo da chamada automática, idioma) do canal deste projeto."""
    try:
        info, _ = projeto.canal.info()
    except Exception:  # noqa: BLE001
        return "nenhuma", "pt"
    modo = str(getattr(info, "chamada_automatica", "nenhuma") or "nenhuma")
    return (modo if modo in CHAMADA_AUTOMATICA else "nenhuma"), (info.idioma if info.idioma in ("pt", "en") else "pt")


def cenas_sugeridas(projeto: ProjetoWS, clip: Any, tl: Timeline, pals: list[dict], ad: Any = None,
                    cancelar: threading.Event | None = None) -> tuple[list[Item], str | None]:
    """Cenas da direção de arte para as propostas do editor (só quando o estilo do clip tem direção de arte).

    Toda animação usa IA: sem ela não há proposta de cena, só o aviso. Com IA, nos estilos de arte as cenas saem da
    direção de vídeo do clip (desenho.gerar: análise, direção conferida e cenas); nos de cenas, do planejador do direcao.py.
    """
    from . import direcao

    try:
        est, _, _ = projeto.ws.carregar_estilo(clip.estilo, projeto.canal, clip.ajustes_estilo)
    except Exception:  # noqa: BLE001
        return [], None
    if not est.direcao.ativa:
        return [], None
    if ad is None:
        from .melhorar import MSG_SEM_IA

        return [], f"As animações deste estilo usam IA. {MSG_SEM_IA}"
    if est.direcao.modo == "arte" and est.direcao.arte:  # as cenas da direção saem da direção de vídeo do clip
        from . import desenho
        from .ai.adapter import ErroIA

        _, pasta = projeto.clip(clip.id)
        dd = desenho.ler(pasta)
        try:
            if not desenho.do_modo(dd, "arte") or dd.get("arte") != est.direcao.arte:
                dd = desenho.gerar(projeto, clip, tl, pals, est, ad, cancelar=cancelar)
        except (ErroIA, ValueError) as exc:
            return [], f"A IA não montou a direção de vídeo ({exc})."
        itens = [Item(**i) for i in desenho.para_itens(dd)]
        return itens, None if itens else "A IA não montou a direção de vídeo com a fala deste corte."
    cenas, aviso = [], None
    try:  # a DA que o estilo escolheu (com a marca do canal) guia a IA e confere as cenas
        from .arte.guia import da_do_estilo

        arte_estilo = da_do_estilo(est, projeto.canal.path)[0]
    except Exception:  # noqa: BLE001
        arte_estilo = None
    from .ai.adapter import CacheIA, ErroIA

    try:
        from . import skills

        extra = skills.texto_para_ia(projeto.ws, "cenas", projeto.canal.slug, projeto.id, excluir={"roteiro-do-curta"})
        if arte_estilo is not None:
            from .arte.guia import texto_para_ia

            extra = texto_para_ia(arte_estilo) + ("\n\n" + extra if extra else "")
        cenas = direcao.planejar_ia(pals, tl.duracao, clip.titulo, ad, CacheIA(projeto.analise_dir / "cache_ia"),
                                    projeto.canal.info()[1], cancelar, extra)
        origem = "ia"
    except ErroIA as exc:
        aviso = f"A IA não planejou as cenas ({exc})."
    if not cenas:
        return [], aviso or "A IA não montou as cenas com a fala deste corte."
    if arte_estilo is not None and cenas:
        from .arte.guia import filtrar_cenas

        cenas = filtrar_cenas(cenas, arte_estilo, tl.duracao)[0]
    return [Item(tipo="cena", inicio=c.inicio, fim=c.fim, params=c.params, origem=origem, motivo=c.motivo) for c in cenas], aviso


def sugerir_ia(projeto: ProjetoWS, clip_id: str, cancelar: threading.Event | None = None, esperar_login: Any = None) -> dict:
    """Propostas da IA (pelo adaptador: texto entra, JSON sai). Sem IA, cai para a heurística."""
    from .ai.adapter import CacheIA, ErroIA, adaptador_com_reserva, chamar

    clip, pasta = projeto.clip(clip_id)
    tl = Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos)
    pals = palavras_do_clip(projeto, tl)
    modo, idioma = chamada_do_canal(projeto)
    conf = projeto.ws.config()
    ad = adaptador_com_reserva(conf.ia.ranking, conf.ia.timeout_s, esperar_login=esperar_login)
    if not ad.disponivel():
        cenas, _ = cenas_sugeridas(projeto, clip, tl, pals)
        return {"propostas": [i.model_dump() for i in validar(heuristica(pals, tl, chamada=modo, idioma=idioma) + cenas, tl.duracao)],
                "fonte": "heuristica", "aviso": "Nenhuma IA instalada: usei as regras simples."}
    cortes, acc = [], 0.0
    for s, e in tl.trechos[:-1]:
        acc += e - s
        cortes.append(round(acc, 2))
    try:
        est, _, _ = projeto.ws.carregar_estilo(clip.estilo, projeto.canal)
        desc = est.descricao or est.nome
    except Exception:  # noqa: BLE001
        desc = clip.estilo
    _, canal_md = projeto.canal.info()
    try:
        indice = _indice_stickers()
        r = chamar(ad, prompt_efeitos(pals, tl.duracao, cortes, desc, canal_md, sorted(indice)), SCHEMA_EFEITOS,
                   CacheIA(projeto.analise_dir / "cache_ia"), cancelar)
    except ErroIA as exc:
        cenas, _ = cenas_sugeridas(projeto, clip, tl, pals)
        return {"propostas": [i.model_dump() for i in validar(heuristica(pals, tl, chamada=modo, idioma=idioma) + cenas, tl.duracao)],
                "fonte": "heuristica", "aviso": f"A IA não respondeu ({exc}); usei as regras simples."}
    cenas, aviso = cenas_sugeridas(projeto, clip, tl, pals, ad, cancelar)
    itens = de_resposta_ia(r, tl.duracao, indice) + chamadas(tl.duracao, modo, idioma) + cenas
    out = {"propostas": [i.model_dump() for i in validar(itens, tl.duracao)], "fonte": ad.nome}
    if aviso:
        out["aviso"] = aviso
    return out


def duracao_do_clip(projeto: ProjetoWS, clip_id: str) -> float:
    clip, _ = projeto.clip(clip_id)
    return Timeline.de_clip(clip.inicio, clip.fim, clip.cortes_internos).duracao
