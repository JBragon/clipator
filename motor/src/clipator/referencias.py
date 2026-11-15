"""Imagens reais do que a fala cita, para qualquer estilo: a foto da pessoa, o logo da empresa, a foto do produto.

Nos estilos de curta a imagem já entra no painel pelo roteiro (artes/curta.py). Nos outros, este módulo faz o caminho
inteiro e devolve uma camada transparente (HyperFrames) que vai por cima do clip:

1. **Quem é citado**: uma chamada curta à IA lê a fala do clip e lista as pessoas, empresas, produtos e tecnologias
   citadas pelo nome, com o termo como está na transcrição e o nome certo para buscar ("Iliasat Skiver" → Ilya
   Sutskever). O termo tem de estar na fala.
2. **A imagem**: Wikidata e Wikimedia Commons, só com licença livre (artes/pesquisa.py: imagens_reais), guardada na
   pasta do clip com o crédito.
3. **O cartão**: entra quando o nome é dito, com a imagem, o nome e uma linha de contexto, num visual que combina com o
   estilo (`VISUAIS`): recorte de revista, ficha de dossiê, terço inferior de documentário, ficha técnica, alfinete no
   mapa, polaroid de caderno, HUD de jogo ou cartão limpo. O lugar do cartão depende do layout: no painel da animação
   quando há um, senão no alto da tela, longe da legenda.

Sem IA, em prévia ou com CLIPATOR_PESQUISA=0, nada disso roda e o clip sai como antes.
"""

from __future__ import annotations

import hashlib
import html
import json
import shutil
import threading
from pathlib import Path
from typing import Any

REFERENCIA = 2.6  # segundos no ar
MIN_NO_AR = 1.2
MAX_REFS = 8

# o visual do cartão em cada estilo (id do estilo, ou a direção de arte / ficha dele)
VISUAIS: dict[str, str] = {
    # legenda animada
    "documentario": "documentario", "dossie-investigativo": "dossie", "plantao-urgente": "plantao", "recorte-de-revista": "recorte",
    "iceberg": "tecnico", "numeros-na-tela": "tecnico", "texto-grifado": "polaroid", "tres-faixas": "limpo",
    # só legenda
    "gamer": "hud", "impacto": "impacto", "minimalista": "limpo", "podcast-limpo": "limpo", "podcast-italico": "limpo",
    "uma-palavra": "impacto", "amarelo-condensado": "impacto", "reacao-dividida": "limpo", "corte-longo": "documentario",
    "gancho-preto-e-branco": "impacto",
    # direções de arte (pelo slug da arte)
    "revista-de-bancada": "recorte", "quadro-de-recortes": "recorte", "arquivo-em-camadas": "dossie", "anotacao-em-foco": "polaroid",
    "caderno-de-materiais": "polaroid", "gesto-de-papel": "polaroid", "tinta-em-etapas": "polaroid", "letras-de-oficina": "recorte",
    "acervo-natural": "polaroid", "mapa-de-ideias": "tecnico", "painel-de-variacoes": "tecnico", "atlas-de-percursos": "mapa",
    "geo-em-cena": "mapa", "camadas-do-terreno": "mapa", "cidade-de-bolso": "hud", "jardim-de-luz": "limpo",
    "janela-em-profundidade": "limpo", "mesa-em-profundidade": "polaroid", "oficina-modular": "tecnico", "mecanismo-facetado": "tecnico",
    "resina-em-movimento": "limpo", "terrario-tecnico": "tecnico",
    # fichas dos estilos de cenas e de desenho
    "dossie": "dossie", "neon": "hud", "editorial": "recorte", "laboratorio": "tecnico", "caderno": "polaroid", "quadro": "polaroid",
    "noite": "hud", "maquete": "tecnico",
}


def visual_do_estilo(estilo: Any, nome: str = "") -> str:
    d = getattr(estilo, "direcao", None)
    for chave in (nome, getattr(d, "arte", None) if d is not None and getattr(d, "ativa", False) else None,
                  getattr(d, "ficha", None) if d is not None and getattr(d, "ativa", False) else None):
        if chave and chave.removeprefix("arte-") in VISUAIS:
            return VISUAIS[chave.removeprefix("arte-")]
    return "limpo"


# ---- 1) quem é citado ----------------------------------------------------------------------------------------------
def schema() -> dict[str, Any]:
    from .artes.pesquisa import TIPOS_ENTIDADE

    return {"type": "object", "properties": {"entidades": {"type": "array", "items": {"type": "object", "properties": {
        "termo": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPOS_ENTIDADE)}, "busca": {"type": "string"}},
        "required": ["termo", "tipo", "busca"], "additionalProperties": False}}}, "required": ["entidades"], "additionalProperties": False}


def prompt(pals: list[dict], titulo: str = "") -> str:
    fala = " ".join(w["texto"].strip() for w in pals)[:6000]
    return ("Liste as pessoas, empresas, organizações, produtos e tecnologias conhecidas que esta fala cita pelo nome (até 8, na "
            "ordem em que aparecem). Delas vamos buscar uma imagem real (foto da pessoa, logo da empresa, foto do produto) para "
            "mostrar no vídeo no momento em que são ditas.\n"
            "- 'termo': copiado da fala exatamente como está na transcrição, mesmo que escrito errado.\n"
            "- 'busca': o nome certo e completo para achar na Wikipédia (\"Iliasat Skiver\" → \"Ilya Sutskever\", \"a Nvidia\" → "
            "\"Nvidia\", \"H100\" → \"Nvidia H100\").\n"
            "- Nada genérico (\"a IA\", \"o modelo\", \"a empresa\", \"placa de vídeo\"), nenhum pronome e nada que não foi dito. "
            "Se nada for citado pelo nome, devolva a lista vazia.\n\n"
            f"Título do corte: “{titulo}”\nFala: {fala}")


def de_resposta(resp: Any, pals: list[dict]) -> list[dict[str, str]]:
    from .artes.curta import _vazio_na_tela
    from .artes.pesquisa import TIPOS_ENTIDADE
    from .direcao import _na_fala

    out: list[dict[str, str]] = []
    for e in ((resp or {}).get("entidades") or [])[:MAX_REFS] if isinstance(resp, dict) else []:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS_ENTIDADE:
            continue
        termo = " ".join(str(e.get("termo") or "").split())[:60]
        busca = " ".join(str(e.get("busca") or "").split())[:80]
        if termo and busca and not _vazio_na_tela(termo) and _na_fala(termo, pals, 0.99) and termo not in [x["termo"] for x in out]:
            out.append({"termo": termo, "tipo": e["tipo"], "busca": busca})
    return out


# ---- 2) as imagens, presas no tempo do clip -------------------------------------------------------------------------
def _tempo(termo: str, pals: list[dict]) -> float | None:
    from .artes import tokens

    alvo = tokens(termo)
    ws = [(tokens(w["texto"]) or [""])[0] for w in pals]
    for i in range(max(0, len(ws) - len(alvo) + 1)):
        if alvo and ws[i:i + len(alvo)] == alvo:
            return round(float(pals[i]["inicio"]), 3)
    return None


def obter(pasta: Path, pals: list[dict], ad: Any, titulo: str = "", cancelar: threading.Event | None = None,
          passo: Any = None, cache: Any = None, conferidas: list[dict] | None = None) -> list[dict[str, Any]]:
    """As imagens reais do clip, cada uma com `t` (segundo do clip em que o nome é dito). Guardadas em referencias.json.

    `conferidas`: a lista da checagem de fatos (checagem.entidades_do_clip). Com ela a IA não é chamada: valem os nomes
    e as fontes que o usuário conferiu."""
    from .artes import pesquisa

    passo = passo or (lambda _t: None)
    if (ad is None and conferidas is None) or not pals or not pesquisa.ligada():
        return []
    chave = hashlib.sha1(" ".join(f"{w['inicio']:.2f}{w['texto']}" for w in pals).encode()
                         + (json.dumps(conferidas, sort_keys=True, ensure_ascii=False).encode() if conferidas is not None else b"")).hexdigest()[:16]
    arq = pasta / "referencias.json"
    try:
        salvo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    except ValueError:
        salvo = {}
    if salvo.get("chave") == chave:
        refs = salvo.get("referencias") or []
    else:
        if conferidas is not None:
            ents = conferidas[:MAX_REFS]
            if ents:
                passo("imagens reais: pela checagem de fatos, sem perguntar à IA")
        else:
            from .ai.adapter import chamar

            try:
                ents = de_resposta(chamar(ad, prompt(pals, titulo), schema(), cache, cancelar), pals)
            except Exception as exc:  # noqa: BLE001 - sem a lista, o clip sai sem imagens reais
                passo(f"imagens reais: a IA não listou os nomes citados ({exc})")
                ents = []
        refs = []
        if ents:
            passo("imagens reais: " + ", ".join(f"{e['busca']} ({e['tipo']})" for e in ents))
            achadas, avisos = pesquisa.imagens_reais(ents, pasta, cancelar=cancelar)
            for a in avisos:
                passo(a)
            for r in achadas:
                t = _tempo(r["termo"], pals)
                if t is not None:
                    refs.append({**r, "t": t})
        arq.write_text(json.dumps({"chave": chave, "referencias": refs}, ensure_ascii=False, indent=1), encoding="utf-8")
    refs = [r for r in refs if (pasta / str(r.get("arquivo") or "")).is_file()]
    if refs:
        passo(f"{len(refs)} imagem(ns) real(is) no vídeo: " + ", ".join(f"{r['nome']} em {r['t']:.1f} s" for r in refs))
    return refs


def janelas(refs: list[dict], dur: float) -> list[dict[str, Any]]:
    """Quando cada cartão fica no ar: do nome dito até REFERENCIA depois; o próximo nome encurta o anterior."""
    out: list[dict[str, Any]] = []
    for r in sorted(refs, key=lambda x: x["t"]):
        a = max(0.0, r["t"] - 0.15)
        if a >= dur - 0.5:
            continue
        if out and a < out[-1]["t1"] + 0.1:  # o próximo nome chegou: o anterior sai, mas fica no ar ao menos MIN_NO_AR
            a = max(a, out[-1]["t0"] + MIN_NO_AR + 0.1)
            if a > r["t"] + 1.5 or a >= dur - 0.5:
                continue  # atrasaria demais: o nome já passou
            out[-1]["t1"] = round(a - 0.1, 3)
        out.append({**r, "t0": round(a, 3), "t1": round(min(dur, a + REFERENCIA), 3)})
    return out


# ---- 3) a camada ----------------------------------------------------------------------------------------------------
def area(estilo: Any, w: int, h: int) -> tuple[float, float, float, float, bool]:
    """(x, y, largura, altura máxima do cartão, no painel?) em pixels, conforme o layout do estilo."""
    d = estilo.direcao
    if d.ativa and d.layout == "em-cima":
        alto = h * d.proporcao
        lw = w * 0.6
        return (w - lw) / 2, alto * 0.08, lw, alto * 0.84, True
    if d.ativa and d.layout == "janela":
        cima = not str(d.janela_canto or "inferior").startswith("superior")
        lw = w * 0.58
        return (w - lw) / 2, (h * 0.08 if cima else h * 0.52), lw, h * 0.4, True
    from .subtitles import POSICOES_Y

    leg = estilo.legenda
    y_leg = leg.altura_relativa if leg.altura_relativa is not None else POSICOES_Y.get(leg.posicao, 0.68)
    lw = w * 0.46
    if y_leg > 0.5:  # legenda embaixo: o cartão vai no alto, à esquerda (o rosto costuma estar no centro)
        return w * 0.05, h * 0.1, lw, h * 0.36, False
    return w * 0.05, h * 0.6, lw, h * 0.34, False  # legenda no alto: o cartão desce, abaixo do rosto


CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: var(--largura); height: var(--altura); overflow: hidden; background: transparent; }
#root { position: relative; width: 100%; height: 100%; }
.ref { position: absolute; left: var(--x); top: var(--y); width: var(--w); max-height: var(--hmax); display: flex; flex-direction: column;
  font-family: var(--fonte); color: #15171a; transform-origin: 50% 40%;
  animation: rf-entra .34s cubic-bezier(.2,1.35,.4,1) both, rf-sai .22s ease-in both; animation-delay: 0s, calc(var(--dur) - .22s); }
.ref .img { width: 100%; height: var(--himg); overflow: hidden; background: #fff; display: flex; align-items: center; justify-content: center; }
.ref .img img { width: 100%; height: 100%; object-fit: cover; object-position: 50% 25%; }
.ref.logo .img img { object-fit: contain; width: 80%; height: 70%; }
.ref .nome { font-size: calc(var(--u) * 46); line-height: 1.05; font-weight: 800; text-transform: uppercase; }
.ref .ctx { font-size: calc(var(--u) * 27); line-height: 1.15; margin-top: calc(var(--u) * 4); }
.ref .cred { font-size: calc(var(--u) * 15); opacity: .65; margin-top: calc(var(--u) * 6); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
@keyframes rf-entra { from { opacity: 0; transform: translateY(calc(var(--u) * 40)) rotate(var(--giro0)) scale(.86); } to { opacity: 1; transform: rotate(var(--giro)); } }
@keyframes rf-sai { from { opacity: 1; } to { opacity: 0; transform: rotate(var(--giro)) scale(.96); } }

/* limpo: cartão branco arredondado, sombra macia */
.ref.v-limpo { background: #fff; border-radius: calc(var(--u) * 22); padding: calc(var(--u) * 14); box-shadow: 0 calc(var(--u) * 16) calc(var(--u) * 40) rgba(0,0,0,.35); }
.ref.v-limpo .img { border-radius: calc(var(--u) * 14); }
.ref.v-limpo .nome { margin-top: calc(var(--u) * 12); color: var(--acento-escuro); }
/* polaroid: papel com fita adesiva e leve giro, letra de caderno */
.ref.v-polaroid { --giro: -2.5deg; --giro0: -9deg; background: #fbf8f1; padding: calc(var(--u) * 16) calc(var(--u) * 16) calc(var(--u) * 22);
  box-shadow: 0 calc(var(--u) * 10) calc(var(--u) * 24) rgba(0,0,0,.3); }
.ref.v-polaroid::before { content: ""; position: absolute; left: 36%; top: calc(var(--u) * -18); width: 28%; height: calc(var(--u) * 38);
  background: rgba(240, 220, 150, .75); transform: rotate(3deg); }
.ref.v-polaroid .nome { margin-top: calc(var(--u) * 14); text-transform: none; font-weight: 700; font-size: calc(var(--u) * 50); }
/* recorte: foto recortada de revista, borda serrilhada, nome numa tarja */
.ref.v-recorte { --giro: 2deg; --giro0: 8deg; background: #fff; padding: calc(var(--u) * 12);
  clip-path: polygon(0 2%, 4% 0, 9% 1.5%, 15% 0, 22% 1%, 30% 0, 38% 1.8%, 46% 0, 55% 1.2%, 63% 0, 71% 1.6%, 80% 0, 88% 1.4%, 95% 0, 100% 2%, 99% 50%,
    100% 98%, 94% 100%, 86% 98.5%, 77% 100%, 68% 98.6%, 58% 100%, 49% 98.4%, 40% 100%, 31% 98.8%, 22% 100%, 13% 98.5%, 5% 100%, 0 98%, 1% 50%);
  filter: drop-shadow(0 calc(var(--u) * 8) calc(var(--u) * 10) rgba(0,0,0,.35)); }
.ref.v-recorte .img img { filter: contrast(1.08) saturate(.85); }
.ref.v-recorte .nome { align-self: flex-start; margin-top: calc(var(--u) * 10); background: var(--acento); color: #fff; padding: 0 .25em; font-size: calc(var(--u) * 50); }
.ref.v-recorte .ctx { font-family: Georgia, serif; font-style: italic; }
/* dossiê: ficha de arquivo com clipe e carimbo */
.ref.v-dossie { --giro: -1.5deg; --giro0: -5deg; background: #efe6cf; padding: calc(var(--u) * 18); border: calc(var(--u) * 2) solid #b9a77c;
  font-family: 'Special Elite', 'Courier New', monospace; box-shadow: 0 calc(var(--u) * 12) calc(var(--u) * 24) rgba(0,0,0,.35); }
.ref.v-dossie .img img { filter: grayscale(1) contrast(1.15) sepia(.25); }
.ref.v-dossie::after { content: "ARQUIVO"; position: absolute; right: calc(var(--u) * 18); top: calc(var(--u) * 26); color: #b3261e; border: calc(var(--u) * 4) solid #b3261e;
  padding: 0 .3em; font-size: calc(var(--u) * 30); transform: rotate(-12deg); opacity: .85; }
.ref.v-dossie .nome { margin-top: calc(var(--u) * 12); font-weight: 400; }
/* documentário: terço inferior, foto quadrada à esquerda e linha fina */
.ref.v-documentario { flex-direction: row; align-items: center; gap: calc(var(--u) * 18); width: auto; max-width: 90%; background: rgba(12,12,14,.78);
  color: #fff; padding: calc(var(--u) * 14) calc(var(--u) * 24) calc(var(--u) * 14) calc(var(--u) * 14); border-left: calc(var(--u) * 8) solid var(--acento); }
.ref.v-documentario .img { width: calc(var(--u) * 170); height: calc(var(--u) * 170); flex: none; }
.ref.v-documentario .nome { font-size: calc(var(--u) * 42); letter-spacing: .04em; }
.ref.v-documentario .ctx { opacity: .85; }
/* plantão: caixa de telejornal com faixa da cor do estilo */
.ref.v-plantao { background: #fff; border-top: calc(var(--u) * 12) solid var(--acento); box-shadow: 0 calc(var(--u) * 12) calc(var(--u) * 30) rgba(0,0,0,.45); }
.ref.v-plantao .nome { background: #111; color: #fff; padding: calc(var(--u) * 8) calc(var(--u) * 14); }
.ref.v-plantao .ctx { padding: calc(var(--u) * 6) calc(var(--u) * 14); }
.ref.v-plantao .cred { padding: 0 calc(var(--u) * 14) calc(var(--u) * 10); }
/* técnico: ficha com cantoneiras e letra monoespaçada */
.ref.v-tecnico { background: rgba(14,20,26,.9); color: #e9f1f5; padding: calc(var(--u) * 16); border: calc(var(--u) * 2) solid var(--acento);
  font-family: 'JetBrains Mono', 'Consolas', monospace; }
.ref.v-tecnico::before { content: "REF."; position: absolute; left: calc(var(--u) * 16); top: calc(var(--u) * -30); font-size: calc(var(--u) * 22);
  color: var(--acento); letter-spacing: .2em; }
.ref.v-tecnico .nome { margin-top: calc(var(--u) * 12); color: var(--acento); font-size: calc(var(--u) * 40); }
/* mapa: foto presa por um alfinete, etiqueta de papel */
.ref.v-mapa { --giro: 1.5deg; --giro0: 6deg; background: #f6f1e4; padding: calc(var(--u) * 12); box-shadow: 0 calc(var(--u) * 8) calc(var(--u) * 18) rgba(0,0,0,.3); }
.ref.v-mapa::before { content: ""; position: absolute; left: 50%; top: calc(var(--u) * -16); width: calc(var(--u) * 34); height: calc(var(--u) * 34);
  margin-left: calc(var(--u) * -17); border-radius: 50%; background: var(--acento); box-shadow: 0 calc(var(--u) * 4) 0 rgba(0,0,0,.35); }
.ref.v-mapa .nome { margin-top: calc(var(--u) * 10); font-size: calc(var(--u) * 40); }
/* HUD: moldura de jogo, cantos em ângulo e brilho */
.ref.v-hud { background: rgba(8,10,24,.88); color: #fff; padding: calc(var(--u) * 14); border: calc(var(--u) * 3) solid var(--acento);
  clip-path: polygon(0 calc(var(--u) * 26), calc(var(--u) * 26) 0, 100% 0, 100% calc(100% - calc(var(--u) * 26)), calc(100% - calc(var(--u) * 26)) 100%, 0 100%);
  box-shadow: 0 0 calc(var(--u) * 30) var(--acento); }
.ref.v-hud .nome { margin-top: calc(var(--u) * 10); color: var(--acento); text-shadow: 0 0 calc(var(--u) * 14) var(--acento); }
/* impacto: borda grossa na cor de destaque, nome gigante, entrada com pancada */
.ref.v-impacto { background: #fff; border: calc(var(--u) * 10) solid var(--acento); box-shadow: calc(var(--u) * 14) calc(var(--u) * 14) 0 #000; }
.ref.v-impacto .nome { background: #000; color: #fff; padding: calc(var(--u) * 6) calc(var(--u) * 12); font-size: calc(var(--u) * 56); }
.ref.v-impacto .ctx, .ref.v-impacto .cred { padding: 0 calc(var(--u) * 12); }
.ref.v-impacto .cred { padding-bottom: calc(var(--u) * 8); }
"""
_GIRO = {"limpo": "0deg", "documentario": "0deg", "plantao": "0deg", "tecnico": "0deg", "hud": "0deg", "impacto": "-2deg"}


def documento(refs: list[dict], visual: str, w: int, h: int, dur: float, area_: tuple, acento: str, fonte: str, fps: int = 30) -> str:
    """O index.html da camada de imagens reais (HyperFrames, fundo transparente). `refs` já com t0/t1 e `src`."""
    x, y, lw, hmax, _ = area_
    u = min(w, h) / 1080
    himg = min(lw * 0.72, hmax * 0.66) if visual != "documentario" else 170 * u
    escuro = acento
    partes = []
    for k, r in enumerate(refs):
        cls = f"ref v-{visual}" + (" logo" if r.get("logo") else "")
        ctx = f'<div class="ctx">{html.escape(r.get("contexto") or "")}</div>' if r.get("contexto") else ""
        cred = (r.get("credito") or {}).get("autor") or (r.get("credito") or {}).get("fonte") or ""
        corpo = (f'<div class="img"><img src="{html.escape(r["src"])}" alt=""></div>'
                 + (f'<div><div class="nome">{html.escape(r.get("nome") or r["termo"])}</div>{ctx}'
                    + (f'<div class="cred">imagem: {html.escape(cred)}</div>' if cred else "") + "</div>"
                    if visual == "documentario" else
                    f'<div class="nome">{html.escape(r.get("nome") or r["termo"])}</div>{ctx}'
                    + (f'<div class="cred">imagem: {html.escape(cred)}</div>' if cred else "")))
        dur_k = max(0.5, r["t1"] - r["t0"])
        yy = (y + hmax - 210 * u) if visual == "documentario" and not area_[4] else y
        partes.append(f'<div id="ref-{k}" class="clip {cls}" data-start="{r["t0"]:.3f}" data-duration="{dur_k:.3f}" data-track-index="{k % 3 + 1}" '
                      f'style="--dur:{dur_k:.3f}s;--y:{yy:.0f}px">{corpo}</div>')
    giro = _GIRO.get(visual)
    raiz = (f":root {{ --largura:{w}px; --altura:{h}px; --u:{u:.4f}px; --x:{x:.0f}px; --y:{y:.0f}px; --w:{lw:.0f}px; --hmax:{hmax:.0f}px; "
            f"--himg:{himg:.0f}px; --acento:{acento}; --acento-escuro:{escuro}; --fonte:'{fonte}', 'Montserrat ExtraBold', 'Anton', sans-serif; "
            + (f"--giro:{giro}; --giro0:{giro}; " if giro else "") + "}\n")
    return f"""<!doctype html>
<html lang="pt"><head><meta charset="UTF-8" /><meta name="viewport" content="width={w}, height={h}" />
<!-- Gerado pelo Clipator: imagens reais do que a fala cita (Wikimedia Commons, licenças livres). -->
<style>{raiz}{CSS}</style></head>
<body><div id="root" data-composition-id="clipator-referencias" data-start="0" data-duration="{dur:.3f}" data-width="{w}" data-height="{h}" data-fps="{fps}" data-no-timeline>
{chr(10).join(partes)}
</div></body></html>
"""


def preparar(refs: list[dict], pasta_clip: Path, pasta_camada: Path) -> list[dict]:
    """Copia as imagens para a pasta da camada (midias/<hash>) e devolve as referências com `src`."""
    out = []
    for r in refs:
        orig = pasta_clip / r["arquivo"]
        if not orig.is_file():
            continue
        h = hashlib.sha1(orig.read_bytes()).hexdigest()[:16]
        dest = pasta_camada / "midias" / f"{h}{orig.suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(orig, dest)
        out.append({**r, "src": f"midias/{dest.name}"})
    return out
