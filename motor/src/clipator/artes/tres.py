"""As seis direções em 3D, com three.js (MIT) e alternativa em SVG isométrico.

O texto fica sempre em SVG, fora do canvas: a leitura é igual com ou sem WebGL. O canvas (e o script) só entra quando o
three.js está disponível e a cena não pediu a alternativa leve; se o WebGL falhar na hora, o script não liga a classe
`tres-d` e continuam valendo os desenhos `.so-2d`, com os mesmos rótulos. O tempo vem do HyperFrames, pelo mesmo caminho da
maquete: uma timeline em window.__timelines e o relógio CSS. Cada quadro é calculado do zero a partir de t, sem acumular.
"""

from __future__ import annotations

import json
from typing import Any

from .. import maquete3d
from .kit import ALTURA_LINHA, Ctx, ajustar, g, largura, linhas, retangulo, traco, txt

ESC = 130.0  # um cubo isométrico de 1 unidade do mundo, na alternativa SVG


# ---- alternativa SVG: faces isométricas com a mesma geometria ----------------------------------------------------
def iso(x: float, y: float, z: float) -> tuple[float, float]:
    return (x - y) * 0.866 * ESC, (x + y) * 0.5 * ESC - z * ESC


def caixa_iso(ox: float, oy: float, x: float, y: float, z: float, w: float, d: float, h: float, cor: str) -> str:
    """Três faces de uma caixa, com diferença de luminosidade (sem contorno de quadrinhos)."""
    def p(a: float, b: float, c: float) -> str:
        u, v = iso(a, b, c)
        return f"{ox + u:.1f},{oy + v:.1f}"
    topo = " ".join(p(*q) for q in ((x, y, z + h), (x + w, y, z + h), (x + w, y + d, z + h), (x, y + d, z + h)))
    esq = " ".join(p(*q) for q in ((x, y + d, z + h), (x + w, y + d, z + h), (x + w, y + d, z), (x, y + d, z)))
    dire = " ".join(p(*q) for q in ((x + w, y, z + h), (x + w, y + d, z + h), (x + w, y + d, z), (x + w, y, z)))
    return (f'<polygon points="{topo}" fill="{cor}"/><polygon points="{esq}" fill="color-mix(in srgb, {cor} 78%, #000)"/>'
            f'<polygon points="{dire}" fill="color-mix(in srgb, {cor} 60%, #000)"/>')


def _placa(c: Ctx, y: float, h: float, t: float, cor: str = "var(--fundo)") -> str:
    """A frase da cena: sempre em SVG, com o fundo que garante o contraste."""
    ls, tam = ajustar(c.texto, c.fonte_corpo, c.lw - 40, h - 26, 3, 52, 36)
    alt = len(ls) * tam * ALTURA_LINHA + 26
    return g(retangulo(c.x0, y + h - alt, c.lw, alt, cor, 8, 'opacity=".94"') + linhas(c.x0 + 20, y + h - alt + 8 + tam, ls, tam), t, "a-sobe", 0.4)


def _rotulo(c: Ctx, s: str, x: float, y: float, t: float, cor: str = "var(--primaria)") -> str:
    ls, tam = ajustar(s, c.fonte_corpo, c.lw * 0.42, 100, 2, 38, 34)


    w = max(largura(q, c.fonte_corpo, tam) for q in ls) + 30
    h = len(ls) * tam * ALTURA_LINHA + 14
    x = min(max(x, c.x0), c.x1 - w)
    return g(retangulo(x, y, w, h, "var(--fundo)", 6, f'stroke="{cor}" stroke-width="3"') + linhas(x + 15, y + 6 + tam, ls, tam), t, "a-sobe", 0.3)


def _base(c: Ctx, modo2d: str, rotulos: list[str], fases: list[float]) -> str:
    """O desenho leve (fica escondido quando há 3D), os rótulos e a placa da frase."""
    placa_h = min(190.0, c.lh * 0.3)
    ys = [c.y0 + 8, c.y0 + 8]  # uma coluna de rótulos de cada lado, empilhados pela altura real
    rot = ""
    for i, s in enumerate(rotulos[:4]):
        lado = i % 2
        rot += _rotulo(c, s, c.x0 if lado == 0 else c.x1 - c.lw * 0.42, ys[lado], fases[min(i + 1, len(fases) - 1)])
        ys[lado] += len(ajustar(s, c.fonte_corpo, c.lw * 0.42, 100, 2, 38, 34)[0]) * 46 + 26
    return f'<g class="so-2d">{modo2d}</g>{rot}{_placa(c, c.y1 - placa_h, placa_h, fases[0])}'


def _centro(c: Ctx) -> tuple[float, float]:
    return c.W / 2, c.y0 + (c.lh - min(190.0, c.lh * 0.3)) * 0.52


# ---- 1 · Oficina modular -----------------------------------------------------------------------------------------
def _oficina(c: Ctx) -> str:
    fs = c.fases(4, leitura=1.4)
    ox, oy = _centro(c)
    # o peso de `modulos` na leve: seis módulos, na mesma ordem de montagem
    n = min(6, max(4, int(c.par["modulos"]) // 3))
    elev, recuo = float(c.par["elevacao_relativa"]), float(c.par["recuo_relativo"])
    _ = c.par["ordem"]
    chao = caixa_iso(ox, oy + 60, -1.1, -0.9, -0.12, 2.2, 1.8, 0.12, "var(--superficie)")
    pecas = ""
    for i in range(n):
        cor = "var(--primaria)" if i == n - 1 else ("var(--destaque)" if i % 2 else "var(--texto)")
        desce = (elev + 0.08) * 160
        pecas += g(caixa_iso(ox, oy + 60, -0.45 + (i % 2) * 0.05, -0.45 + (i % 2) * 0.05, 0.3 * i - recuo, 0.9, 0.9, 0.28, cor),
                   fs[0] + i * max(0.12, (fs[2] - fs[0]) / n), "a-assenta", 0.4, css=f"--dx:-90px;--dy:{-desce:.0f}px;--r:0deg")
    return _base(c, chao + pecas, c.itens(2), fs)


# ---- 3 · Costura viva --------------------------------------------------------------------------------------------
def _costura(c: Ctx) -> str:
    fs = c.fases(4, leitura=1.4)
    ox, oy = _centro(c)
    deforma = float(c.par["deformacao_maxima"])
    atraso = float(c.par["atraso_membros_s"])
    trama = int(c.par["densidade_trama"])
    expr = int(c.par["expressoes"])
    boca = ["M-30 26Q0 50 30 26", "M-28 34H28", "M-26 40Q0 16 26 40", "M-20 30Q0 54 20 30", "M-18 34Q0 28 18 34"][c.k % expr]
    pad = f'<pattern id="tr{c.k}" width="{640 / trama:.1f}" height="{640 / trama:.1f}" patternUnits="userSpaceOnUse"><path d="M0 0L{640 / trama:.1f} {640 / trama:.1f}" stroke="#000" stroke-opacity=".07" stroke-width="2"/></pattern>'
    corpo = (f'<g transform="translate({ox:.0f} {oy:.0f})"><g class="an" style="transform-box:fill-box;transform-origin:50% 100%;--d:{1 + deforma:.3f};--e:{1 - deforma * 0.8:.3f};animation:a-acena 1.4s ease-in-out {fs[1]:.3f}s 1 both">'
             f'<ellipse cx="0" cy="40" rx="118" ry="130" fill="var(--primaria)"/><ellipse cx="0" cy="40" rx="118" ry="130" fill="url(#tr{c.k})"/>'
             f'<ellipse cx="0" cy="40" rx="104" ry="116" fill="none" stroke="var(--fundo)" stroke-width="4" stroke-dasharray="12 10"/>'
             f'<ellipse cx="-92" cy="-68" rx="30" ry="52" fill="var(--primaria)" transform="rotate(-22 -92 -68)"/>'
             f'<ellipse cx="92" cy="-68" rx="30" ry="52" fill="var(--primaria)" transform="rotate(22 92 -68)"/>'
             f'<circle cx="-38" cy="-8" r="9" fill="var(--texto)"/><circle cx="38" cy="-8" r="9" fill="var(--texto)"/>'
             f'<path d="{boca}" fill="none" stroke="var(--texto)" stroke-width="6" stroke-linecap="round"/></g></g>')
    braco = (f'<g class="an" style="animation:a-sobe .35s ease-out {fs[1] + atraso:.3f}s both"><ellipse cx="{ox + 150:.0f}" cy="{oy + 40:.0f}" rx="24" ry="58" fill="var(--primaria)" transform="rotate(38 {ox + 150:.0f} {oy + 40:.0f})"/></g>')
    return f"<defs>{pad}</defs>" + _base(c, corpo + braco, [c.nota] if c.nota else [], fs)


# ---- 4 · Terrário técnico ----------------------------------------------------------------------------------------
def _terrario(c: Ctx) -> str:
    fs = c.fases(4, leitura=1.4)
    ox, oy = _centro(c)
    zonas = int(c.par["zonas"])
    arco = float(c.par["arco_camera_graus"])
    base_h = float(c.par["altura_base_relativa"])
    vel = float(c.par["velocidade_percurso"])
    bandeja = caixa_iso(ox, oy + 50, -1.2, -1.0, -base_h, 2.4, 2.0, base_h, "var(--superficie)")
    casas = "".join(caixa_iso(ox, oy + 50, -0.9 + 0.65 * i, -0.3, 0, 0.42, 0.42, 0.3 + 0.24 * (i % 2), "var(--destaque)" if i % 2 else "var(--texto)")
                    for i in range(min(zonas, 3)))
    x0, y0 = iso(-1.0, 0.45, 0.05)
    x1, y1 = iso(1.0, 0.45, 0.05)
    rota = traco(f"M{ox + x0:.0f} {oy + 50 + y0:.0f}L{ox + x1:.0f} {oy + 50 + y1:.0f}", "var(--primaria)", 8, fs[1], max(0.4, 1.2 / vel))
    _ = arco
    return _base(c, bandeja + casas + rota, c.itens(2), fs)


# ---- 5 · Resina em movimento -------------------------------------------------------------------------------------
def _resina(c: Ctx) -> str:
    fs = c.fases(4, leitura=1.4)
    ox, oy = _centro(c)
    amp = float(c.par["amplitude_relativa"])
    amort = float(c.par["amortecimento"])
    freq = float(c.par["frequencia_hz"])
    trans = float(c.par["transmissao"])
    dur = min(1.2, 3 / max(amort, 1))
    gr = (f'<radialGradient id="res{c.k}" cx=".4" cy=".35" r=".75"><stop offset="0" stop-color="var(--destaque)" stop-opacity="{1 - trans * 0.4:.2f}"/>'
          f'<stop offset="1" stop-color="var(--primaria)" stop-opacity="{1 - trans * 0.5:.2f}"/></radialGradient>')
    forma = (f'<g transform="translate({ox:.0f} {oy:.0f})"><g class="an" style="transform-box:fill-box;transform-origin:50% 100%;--a:{1 + amp:.3f};--b:{1 - amp * 0.8:.3f};'
             f'animation:a-onda {1 / freq * 2:.2f}s ease-out {fs[1]:.3f}s {max(1, int(dur * freq / 2))} both">'
             f'<ellipse cx="0" cy="0" rx="170" ry="150" fill="url(#res{c.k})"/><path d="M-110 -70Q-60 -130 30 -120" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="10" stroke-linecap="round"/>'
             f'<rect x="-34" y="-34" width="68" height="68" rx="12" fill="var(--texto)"/></g></g>')
    pedestal = f'<ellipse cx="{ox:.0f}" cy="{oy + 168:.0f}" rx="190" ry="26" fill="var(--superficie)"/>'
    leve = txt(c.x1, c.y0 + 34, "versão leve", 30, "var(--texto)", "t", "end")
    return f"<defs>{gr}</defs>" + _base(c, pedestal + forma + leve, [c.nota] if c.nota else [], fs)


# ---- 8 · Mecanismo facetado --------------------------------------------------------------------------------------
def _mecanismo(c: Ctx) -> str:
    fs = c.fases(4, leitura=1.4)
    ox, oy = _centro(c)
    n = int(c.par["componentes"])
    exp = float(c.par["explosao_relativa"])
    ap = float(c.par["aproximacao_maxima"])
    ds = float(c.par["duracao_separacao_s"])
    corpo = ""
    for i in range(n):
        cor = "var(--primaria)" if i == n // 2 else "var(--superficie)"
        d = (i - (n - 1) / 2) * exp * 170
        corpo += g(caixa_iso(ox, oy + 70, -0.5, -0.5, 0.24 * i, 1.0, 1.0, 0.2, cor), fs[1], "a-assenta", ds, css=f"--dx:0px;--dy:{d:.0f}px;--r:0deg")
    _ = ap
    return _base(c, corpo, c.itens(3), fs)


# ---- 18 · Camadas do terreno -------------------------------------------------------------------------------------
def _terreno(c: Ctx) -> str:
    fs = c.fases(4, leitura=1.4)
    ox, oy = _centro(c)
    n = int(c.par["niveis"])
    sep = float(c.par["separacao_relativa"])
    canto = float(c.par["canto_removivel"])
    _ = c.par["angulo_camera_graus"]
    cores = ["var(--suave)", "var(--primaria)", "var(--destaque)", "var(--superficie)"]
    corpo = ""
    for i in range(n):
        d = (0 if i == 0 else (-1) ** i) * sep * 420
        corpo += g(caixa_iso(ox, oy + 70, -0.9, -0.9, 0.36 * i, 1.8 - canto, 1.8, 0.34, cores[i % 4]), fs[1], "a-assenta", 0.7, css=f"--dx:{d:.0f}px;--dy:0px;--r:0deg")
    return _base(c, corpo, c.itens(n)[:3], fs)


def _fundo_liso(c: Ctx) -> str:
    return retangulo(0, 0, c.W, c.H, "var(--fundo)")


_CSS = """
#arte3d { position: absolute; left: 0; top: var(--topo); width: 100%; height: var(--alt); }
#relogio3d { position: absolute; width: 1px; height: 1px; animation: relogio3d var(--duracao) linear both; }
@property --t3 { syntax: '<number>'; inherits: false; initial-value: 0; }
body.tres-d .so-2d { display: none; }
@keyframes a-acena { 0% { transform: none; } 20% { transform: scale(var(--e), var(--d)); } 50% { transform: rotate(4deg); } 100% { transform: none; } }
@keyframes a-onda { 0%, 100% { transform: none; } 30% { transform: scale(var(--a), var(--b)); } 65% { transform: scale(var(--b), var(--a)); } }
"""


def _extras(camada: Any, cenas: list[dict]) -> tuple[str, str]:
    """(canvas, scripts) da cena 3D. Vazio sem three.js: fica a alternativa SVG."""
    p = maquete3d.caminho_three()
    if p is None:
        return "", ""

    render = camada.render
    dados = []
    for k, c in enumerate(cenas):
        if c["params"].get("cena") != "arte":
            continue
        ctx = camada.ctx(c["params"], float(c["inicio"]), float(c["fim"]), k, len(cenas), c.get("palavras"), None)
        if ctx.leve or c.get("_midia"):  # a cena pediu a alternativa leve, ou tem foto: fica no SVG
            continue
        dados.append({"inicio": round(float(c["inicio"]), 3), "fim": round(float(c["fim"]), 3), "par": ctx.par, "fases": ctx.fases(4, leitura=1.4),
                      "semente": ctx.semente, "indice": k, **(render.dados(ctx) if render.dados else {})})
    if not dados:
        return "", ""
    cfg = {"direcao": camada.slug, "cenas": dados, "duracao": camada.duracao, "W": camada.W, "H": camada.H,
           "alvoY": (_centro(camada.ctx({}, 0, 1, 0, 1, [], None))[1]) / camada.H, **render.cfg}
    js_dados = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return ('<canvas id="arte3d"></canvas><div id="relogio3d"></div>',
            f"<script>{p.read_text(encoding='utf-8')}</script>\n<script>window.ARTE3D = {js_dados};</script>\n<script>{JS}</script>")


class Direcao3D:
    """Uma direção com canvas. `cfg`: o que vale para a camada toda; `dados(ctx)`: o que o script precisa de cada cena."""

    def __init__(self, cena: Any, fundo: Any = _fundo_liso, css: str = "", cfg: dict | None = None, dados: Any = None) -> None:
        self.cena, self.fundo, self.css, self.cfg, self.dados = cena, fundo, _CSS + css, cfg or {}, dados
        self.extras = _extras


JS = r"""
(function () {
  const M = window.ARTE3D; if (!M || !window.THREE) return;
  const T = THREE, cv = document.getElementById('arte3d');
  let r;
  try { r = new T.WebGLRenderer({ canvas: cv, antialias: !M.pixel, alpha: true, preserveDrawingBuffer: true }); } catch (e) { return; }
  if (!r.getContext()) return;
  document.body.classList.add('tres-d');
  const css = getComputedStyle(document.documentElement), cor = (n) => new T.Color(css.getPropertyValue(n).trim() || '#ffffff');
  const W = cv.clientWidth, H = cv.clientHeight;
  r.setPixelRatio(1); if (M.pixel) { r.setSize(M.pixel, Math.round(M.pixel * H / W), false); cv.style.imageRendering = 'pixelated'; } else r.setSize(W, H, false);
  r.shadowMap.enabled = true; r.shadowMap.type = T.PCFSoftShadowMap; r.outputColorSpace = T.SRGBColorSpace;
  const cena = new T.Scene(), asp = W / H, S = 3.1;
  const cam = M.perspectiva ? new T.PerspectiveCamera(M.perspectiva, asp, 0.1, 120) : new T.OrthographicCamera(-S * asp / 2, S * asp / 2, S / 2, -S / 2, 0.1, 80);
  cena.add(new T.HemisphereLight(0xffffff, cor('--fundo').getHex(), M.noite ? 0.5 : 1.1));
  const sol = new T.DirectionalLight(M.noite ? 0x9fb4d8 : 0xffffff, M.noite ? 0.35 : 2.4); sol.position.set(-5, 9, 6); sol.castShadow = true; sol.shadow.mapSize.set(1024, 1024);
  Object.assign(sol.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5, near: 1, far: 30 }); sol.shadow.bias = -0.0006; sol.shadow.radius = 5; cena.add(sol);
  const sombra = new T.Mesh(new T.PlaneGeometry(30, 30), new T.ShadowMaterial({ opacity: 0.32 })); sombra.rotation.x = -Math.PI / 2; sombra.position.y = -0.01; sombra.receiveShadow = true; sombra.visible = !M.semChao; cena.add(sombra);
  const clamp = (v, a, b) => Math.max(a === undefined ? 0 : a, Math.min(b === undefined ? 1 : b, v));
  const liso = (k) => { k = clamp(k); return k * k * (3 - 2 * k); };
  const cache = {};
  const mat = (c, extra) => { const k = (c.getHexString ? c.getHexString() : c) + JSON.stringify(extra || {}); return cache[k] || (cache[k] = new T.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.82, metalness: 0.02, flatShading: true }, extra || {}))); };
  const malha = (g, m, x, y, z) => { const o = new T.Mesh(g, m); o.position.set(x || 0, y || 0, z || 0); o.castShadow = true; o.receiveShadow = true; return o; };
  const caixa = (w, h, d, m, x, y, z) => malha(new T.BoxGeometry(w, h, d), m, x, (y || 0) + h / 2, z);
  const PRIM = mat(cor('--primaria')), DEST = mat(cor('--destaque')), SUP = mat(cor('--superficie')), TXT = mat(cor('--texto')), SUA = mat(cor('--suave'));
  const rng = (s) => () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const camera = (az, el, zoom) => { const d = 20; cam.position.set(d * Math.cos(el) * Math.sin(az), d * Math.sin(el), d * Math.cos(el) * Math.cos(az)); cam.zoom = zoom; cam.lookAt(0, 0.4, 0); cam.updateProjectionMatrix(); };
  const ISO = Math.atan(1 / Math.SQRT2), AZ = Math.PI / 4;

  // Cada direção monta um grupo e devolve atualizar(lt): recalcula tudo a partir do tempo da cena
  const D = {
    'oficina-modular': (c, g) => {
      const n = Math.min(80, Math.max(4, c.par.modulos)), lado = Math.max(2, Math.round(Math.cbrt(n))), s = 1.5 / lado, r = rng(c.semente);
      const bancada = caixa(3, 0.08, 2.4, SUP, 0, -0.08, 0); g.add(bancada); g.add(caixa(0.6, 0.05, 1.6, TXT, -1.4, 0, 0));
      const mods = [];
      for (let i = 0; i < n; i++) { // de baixo para cima: cada módulo só desce depois dos de baixo (dependências)
        const nv = Math.floor(i / (lado * lado)), resto = i % (lado * lado), ix = resto % lado, iz = Math.floor(resto / lado);
        const m = i === n - 1 ? PRIM : (i % 3 === 0 ? DEST : TXT);
        const o = caixa(s * 0.94, s * 0.9, s * 0.94, m, 0, 0, 0); g.add(o);
        mods.push({ o, destino: new T.Vector3((ix - (lado - 1) / 2) * s, nv * s * 0.94, (iz - (lado - 1) / 2) * s), origem: new T.Vector3(-1.4, 0.05, (r() - 0.5) * 1.2) });
      }
      const t0 = c.fases[0], t1 = Math.max(c.fases[2], t0 + 0.8), passo = (t1 - t0) / n, viagem = Math.max(0.28, passo * 3);
      return (lt) => { mods.forEach((m, i) => { const k = liso((lt - t0 - i * passo) / viagem);
        const voa = Math.sin(k * Math.PI) * c.par.elevacao_relativa * 1.2, enc = k >= 1 ? 0 : -c.par.recuo_relativo * Math.sin(k * Math.PI) * s;
        m.o.visible = lt >= t0 + i * passo; m.o.position.lerpVectors(m.origem, m.destino, k); m.o.position.y += voa + enc + s * 0.45; });
        camera(AZ, ISO, 1); };
    },
    'costura-viva': (c, g) => {
      const tam = 256, cn = document.createElement('canvas'); cn.width = cn.height = tam; const x = cn.getContext('2d'), base = '#' + cor('--primaria').getHexString(), r = rng(c.semente);
      x.fillStyle = base; x.fillRect(0, 0, tam, tam); const dn = c.par.densidade_trama, p = tam / dn;
      for (let i = 0; i < dn; i++) for (let j = 0; j < dn; j++) { x.fillStyle = `rgba(${(i + j) % 2 ? '255,255,255' : '0,0,0'},${0.05 + r() * 0.09})`; x.fillRect(i * p, j * p, p * 0.9, p * 0.9); }
      const tx = new T.CanvasTexture(cn); tx.wrapS = tx.wrapT = T.RepeatWrapping; tx.repeat.set(3, 3); tx.colorSpace = T.SRGBColorSpace;
      const tecido = new T.MeshStandardMaterial({ map: tx, roughness: 0.96 }), linha = mat(cor('--fundo'), { flatShading: false }), olho = mat(cor('--texto'), { flatShading: false });
      const elip = (rx, ry, rz, m) => { const o = malha(new T.SphereGeometry(1, 40, 28), m); o.scale.set(rx, ry, rz); return o; };
      g.add(caixa(3.2, 0.06, 2.2, SUP, 0, -0.06, 0));
      const carretel = malha(new T.CylinderGeometry(0.16, 0.16, 0.3, 18), DEST, -1.1, 0.15, 0.5); g.add(carretel);
      const corpo = new T.Group(); g.add(corpo); const tronco = elip(0.62, 0.72, 0.5, tecido); tronco.position.y = 0.72; corpo.add(tronco);
      const cabeca = new T.Group(); cabeca.position.y = 1.32; corpo.add(cabeca); cabeca.add(elip(0.48, 0.42, 0.42, tecido));
      const oe = elip(0.16, 0.26, 0.12, tecido), od = elip(0.16, 0.26, 0.12, tecido); oe.position.set(-0.32, 0.42, 0); od.position.set(0.32, 0.42, 0); cabeca.add(oe, od);
      const olhos = [-0.17, 0.17].map((a) => { const o = elip(0.05, 0.05, 0.03, olho); o.position.set(a, 0.06, 0.41); cabeca.add(o); return o; });
      const boca = malha(new T.TorusGeometry(0.11, 0.014, 8, 24, Math.PI), olho); boca.rotation.z = Math.PI; boca.position.set(0, -0.08, 0.41); cabeca.add(boca);
      const costura = malha(new T.TorusGeometry(0.61, 0.012, 6, 60), linha); costura.rotation.x = Math.PI / 2; costura.position.y = 0.72; corpo.add(costura);
      const braco = new T.Group(); braco.position.set(0.55, 1.02, 0); corpo.add(braco); const bm = elip(0.13, 0.34, 0.13, tecido); bm.position.y = -0.3; braco.add(bm);
      const bracoE = new T.Group(); bracoE.position.set(-0.55, 1.02, 0); corpo.add(bracoE); const be = elip(0.13, 0.34, 0.13, tecido); be.position.y = -0.3; bracoE.add(be);
      const dm = c.par.deformacao_maxima, at = c.par.atraso_membros_s;
      return (lt) => { const prep = liso((lt - c.fases[1] + 0.12) / 0.12), ges = liso((lt - c.fases[1]) / 0.4) - liso((lt - c.fases[2] - 0.4) / 0.5), acom = liso((lt - c.fases[3]) / 0.5);
        const ges2 = liso((lt - c.fases[1] - at) / 0.4) - liso((lt - c.fases[2] - 0.4 - at) / 0.5);
        const sq = dm * (prep - ges * 0.5) * (1 - acom); corpo.scale.set(1 + sq, 1 - sq, 1 + sq); corpo.rotation.z = -0.1 * ges; cabeca.rotation.x = -0.18 * liso(lt / 0.5) * (1 - acom); cabeca.rotation.z = 0.08 * ges2;
        braco.rotation.z = 1.6 * ges2; bracoE.rotation.z = -0.15 * ges; olhos.forEach((o) => { o.scale.y = 0.05 * (Math.sin(lt * 1.1) > 0.97 ? 0.2 : 1); });
        boca.rotation.z = Math.PI * (Math.floor(c.fases[0]) % c.par.expressoes === 1 ? 0 : 1); camera(0.32, 0.34, 1.05); };
    },
    'terrario-tecnico': (c, g) => {
      const base = c.par.altura_base_relativa, n = Math.min(5, c.par.zonas);
      const b = malha(new T.CylinderGeometry(1.6, 1.72, base, 6), SUP, 0, base / 2 - 0.1, 0); g.add(b);
      const pts = [], cores = [DEST, TXT, PRIM, DEST, TXT];
      for (let i = 0; i < n; i++) { const a = -Math.PI * 0.9 + i * (Math.PI * 1.8 / Math.max(1, n - 1)), x = 1.02 * Math.cos(a), z = 1.02 * Math.sin(a) * 0.85; pts.push(new T.Vector3(x, 0.14, z));
        g.add(caixa(0.42, 0.34 + (i % 3) * 0.26, 0.42, cores[i], x, 0, z)); if (i % 2 === 0) g.add(malha(new T.CylinderGeometry(0.12, 0.16, 0.5, 8), SUA, x + 0.34, 0.25, z - 0.2)); }
      const tubo = new T.CatmullRomCurve3(pts.length > 1 ? pts : [new T.Vector3(-1, 0.14, 0), new T.Vector3(1, 0.14, 0)]);
      g.add(malha(new T.TubeGeometry(tubo, 80, 0.035, 8, false), SUA));
      const luz = malha(new T.SphereGeometry(0.09, 16, 12), mat(cor('--primaria'), { emissive: cor('--primaria'), emissiveIntensity: 1.2, flatShading: false })); g.add(luz);
      const tampa = caixa(2.2, 0.05, 1.7, mat(cor('--destaque'), { transparent: true, opacity: 0.32 }), 0.1, 1.15, 0); g.add(tampa);
      const arco = c.par.arco_camera_graus * Math.PI / 180, vel = c.par.velocidade_percurso;
      return (lt) => { const d = Math.max(1, c.fim - c.inicio), p = lt / d, k = clamp((lt - c.fases[1]) * vel / Math.max(0.8, d - c.fases[1] - 1));
        luz.position.copy(tubo.getPointAt(liso(k))); luz.position.y += 0.06; const ab = liso((lt - c.fases[1]) / 0.6) - liso((lt - d + 0.9) / 0.6); tampa.position.x = 0.1 + ab * 2.6;
        camera(AZ + arco * (liso(p) - 0.5), ISO, 1); };
    },
    'resina-em-movimento': (c, g) => {
      const raio = 0.92, geo = new T.IcosahedronGeometry(raio, 18), orig = geo.attributes.position.array.slice();
      const res = new T.MeshPhysicalMaterial({ color: cor('--destaque'), roughness: 0.28, metalness: 0, transparent: true, opacity: 1 - c.par.transmissao * 0.55, clearcoat: 0.5, emissive: cor('--primaria'), emissiveIntensity: 0.3 });
      const forma = malha(geo, res, 0, 1.0, 0); g.add(forma); forma.castShadow = true;
      const nucleo = malha(new T.IcosahedronGeometry(0.34, 0), PRIM, 0, 1.0, 0); g.add(nucleo);
      g.add(malha(new T.CylinderGeometry(0.85, 0.95, 0.12, 40), SUP, 0, 0.02, 0));
      const A = c.par.amplitude_relativa * raio, am = c.par.amortecimento, w = c.par.frequencia_hz * 2 * Math.PI, ts = c.fases[1], pos = geo.attributes.position;
      return (lt) => { const t = Math.max(0, lt - ts), env = lt < ts ? 0 : A * Math.exp(-am * t);
        for (let i = 0; i < pos.count; i++) { const x = orig[i * 3], y = orig[i * 3 + 1], z = orig[i * 3 + 2], d = Math.hypot(x - 0.3, y - 0.8, z - 0.3), f = env * Math.sin(w * t - d * 4);
          const k = 1 + f / raio * (1 - y / raio * 0.25); pos.setXYZ(i, x * k, y * (1 - f / raio * 0.6), z * k); }
        pos.needsUpdate = true; geo.computeVertexNormals(); forma.rotation.y = 0.2; camera(0.5, 0.34, 0.92); };
    },
    'mecanismo-facetado': (c, g) => {
      const n = c.par.componentes, pecas = [], base = malha(new T.CylinderGeometry(1.55, 1.6, 0.1, 10), SUP, 0, -0.05, 0); g.add(base);
      g.add(malha(new T.CylinderGeometry(0.05, 0.05, 2.2, 6), SUA, 0, 1.1, 0));
      for (let i = 0; i < n; i++) { const m = i === Math.floor(n / 2) ? PRIM : (i % 2 ? SUP : TXT), rr = 0.72 - (i % 2) * 0.16;
        const o = malha(i % 2 ? new T.CylinderGeometry(rr, rr * 1.1, 0.22, 7) : new T.CylinderGeometry(rr * 0.8, rr, 0.26, 6), m, 0, 0, 0); g.add(o); pecas.push(o); }
      const exp = c.par.explosao_relativa, ds = c.par.duracao_separacao_s, ap = c.par.aproximacao_maxima;
      return (lt) => { const fimc = c.fim - c.inicio - ds - 0.25, sep = liso((lt - c.fases[1]) / ds) - liso((lt - fimc) / ds);
        pecas.forEach((o, i) => { o.position.y = 0.2 + i * 0.28 + sep * exp * 1.4 * i; o.rotation.y = i * 0.3 + sep * 0.4; });
        camera(AZ, ISO * 0.8, 0.82 + ap * liso((lt - c.fases[1]) / 1.6) - 0.04 * sep); };
    },
    'atlas-de-percursos': (c, g) => {
      // um atlas de mesa: terreno em relevo (ruído de senos com a semente da cena), água no vale, a rota em tubo que se desenha,
      // o cursor que chega a cada marco no segundo em que a nota dele abre, e a câmera que acompanha o cursor
      const rr = rng(c.semente + 3), fases = [0, 1, 2, 3].map(() => [rr() * 6.28, rr() * 6.28, 0.6 + rr() * 0.9]);
      const altura = (x, z) => fases.reduce((h, [a, b, f], i) => h + Math.sin(x * f * (i + 1) * 0.7 + a) * Math.cos(z * f * (i + 1) * 0.8 + b) * 0.2 / (i + 1), 0.08);
      const geo = new T.PlaneGeometry(9, 6.4, 72, 52); geo.rotateX(-Math.PI / 2); const pos = geo.attributes.position, cores = [];
      const baixo = cor('--superficie'), alto = cor('--superficie').clone().lerp(cor('--texto'), 0.35), agua = cor('--fundo').clone().lerp(cor('--texto'), 0.16), NIVEL = 0.0;
      for (let i = 0; i < pos.count; i++) { const x = pos.getX(i), z = pos.getZ(i), h = altura(x, z), borda = Math.min(1, Math.min(4.5 - Math.abs(x), 3.2 - Math.abs(z)) / 0.5);
        pos.setY(i, Math.max(NIVEL - 0.02, h) * borda); const k = clamp((h - NIVEL) / 0.35), ka = clamp((NIVEL + 0.03 - h) / 0.08); const cc = baixo.clone().lerp(alto, k).lerp(agua, ka); cores.push(cc.r, cc.g, cc.b); }
      geo.setAttribute('color', new T.Float32BufferAttribute(cores, 3)); geo.computeVertexNormals();
      const terreno = malha(geo, new T.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, flatShading: true })); terreno.castShadow = false; g.add(terreno);
      sol.shadow.normalBias = 0.05; sol.shadow.bias = -0.003; // relevo recebe a sombra dos marcos sem listras de acne
      g.add(caixa(9.1, 0.3, 6.5, mat(cor('--fundo').clone().lerp(cor('--superficie'), 0.4)), 0, -0.32, 0));
      const n = Math.max(2, c.marcos), sobre = (x, z) => Math.max(NIVEL, altura(x, z)) + 0.07;
      const lado = (i) => (c.lados[i] === undefined ? (i % 2 ? 1 : -1) : c.lados[i]); // um marco só vira origem e destino
      const marcos = []; for (let i = 0; i < n; i++) { const x = -3.4 + 6.8 * i / (n - 1), z = lado(i) * (0.55 + rr() * 0.75); marcos.push(new T.Vector3(x, sobre(x, z), z)); }
      // a rota passa pelos marcos rente ao relevo: amostra a curva no plano e põe cada ponto em cima do terreno
      const plana = new T.CatmullRomCurve3(marcos.map((v) => new T.Vector3(v.x, 0, v.z)), false, 'centripetal'), amostras = plana.getSpacedPoints(160).map((v) => new T.Vector3(v.x, sobre(v.x, v.z), v.z));
      const rota = new T.CatmullRomCurve3(amostras), SEG = 320, raio = 0.018 * c.par.espessura_rota_px;
      const tubo = malha(new T.TubeGeometry(rota, SEG, raio, 10, false), mat(cor('--primaria'), { emissive: cor('--primaria'), emissiveIntensity: 0.25 })); g.add(tubo);
      const POR_SEG = tubo.geometry.index.count / SEG;
      // o parâmetro u (0..1, por comprimento) de cada marco na rota 3D
      const us = marcos.map((m) => { let melhor = 0, d0 = 1e9; for (let k = 0; k <= 400; k++) { const d = rota.getPointAt(k / 400).distanceTo(m); if (d < d0) { d0 = d; melhor = k / 400; } } return melhor; });
      us[0] = 0; us[n - 1] = 1;
      const cursor = malha(new T.SphereGeometry(raio * 3.2, 20, 14), mat(cor('--destaque'), { emissive: cor('--destaque'), emissiveIntensity: 0.6, flatShading: false })); g.add(cursor);
      const pinos = marcos.map((m) => { const p = new T.Group(); p.add(malha(new T.CylinderGeometry(0.025, 0.025, 0.5, 8), TXT, 0, 0.25, 0));
        p.add(malha(new T.SphereGeometry(0.11, 18, 12), mat(cor('--fundo').clone().lerp(cor('--texto'), 0.9)), 0, 0.55, 0)); p.position.copy(m); p.scale.setScalar(0.001); g.add(p); return p; });
      const ch = c.chegadas.length >= n ? c.chegadas : [...c.chegadas, ...Array(n - c.chegadas.length).fill(0).map((_, k) => c.chegadas[c.chegadas.length - 1] + 0.6 * (k + 1))];
      const uEm = (lt) => { if (lt <= ch[0]) return 0; for (let i = 0; i < n - 1; i++) if (lt < ch[i + 1]) return us[i] + (us[i + 1] - us[i]) * liso((lt - ch[i]) / Math.max(0.05, ch[i + 1] - ch[i])); return 1; };
      const alvo = new T.Vector3();
      return (lt) => { const u = uEm(lt); tubo.geometry.setDrawRange(0, Math.max(0, Math.floor(u * SEG) * POR_SEG)); cursor.position.copy(rota.getPointAt(u)); cursor.position.y += raio;
        cursor.visible = lt >= ch[0] - 0.2;
        pinos.forEach((p, i) => p.scale.setScalar(Math.max(0.001, liso((lt - ch[i] + 0.05) / 0.35) * (1 + 0.25 * Math.sin(Math.PI * clamp((lt - ch[i]) / 0.35))))));
        const fimc = c.fim - c.inicio, abre = liso((fimc - lt) / 0.9), segue = liso((lt - c.t_ini) / 0.8) * abre;
        alvo.set(cursor.position.x * 0.35 * segue, 0.1, cursor.position.z * 0.25 * segue);
        const az = -0.22 + 0.16 * (lt / Math.max(1, fimc)), el = 0.92 - 0.12 * segue, d = 12.5 - 2.2 * segue;
        cam.position.set(alvo.x + d * Math.cos(el) * Math.sin(az), alvo.y + d * Math.sin(el), alvo.z + d * Math.cos(el) * Math.cos(az)); cam.lookAt(alvo);
        sol.position.set(alvo.x - 4, 8, alvo.z + 3); sol.target.position.copy(alvo); sol.target.updateMatrixWorld(); };
    },
    'cidade-de-bolso': (c, g, ci) => {
      // o mundo é 3D, mas desenhado num buffer pequeno e ampliado sem suavizar: pixels quadrados com volume de verdade
      const rr = rng(c.semente + 11), base = cor('--superficie'), luz = '#' + cor('--primaria').getHexString(), escuro = cor('--fundo').clone().lerp(base, 0.55);
      const fachada = (cc, s) => { const q = rng(s), cn = document.createElement('canvas'); cn.width = 32; cn.height = 64; const x = cn.getContext('2d');
        x.fillStyle = '#' + cc.getHexString(); x.fillRect(0, 0, 32, 64); for (let j = 4; j < 60; j += 8) for (let i = 3; i < 28; i += 7) if (q() < 0.55) { x.fillStyle = luz; x.fillRect(i, j, 4, 4); }
        const tx = new T.CanvasTexture(cn); tx.magFilter = tx.minFilter = T.NearestFilter; tx.colorSpace = T.SRGBColorSpace; return new T.MeshStandardMaterial({ map: tx, roughness: 1 }); };
      const lateral = (cc) => new T.MeshStandardMaterial({ color: cc.clone().multiplyScalar(0.62), roughness: 1 });
      const fila = (z, cc, hMin, hMax, d) => { let x = -9; while (x < 40) { const w = 1.3 + rr() * 1.2, h = hMin + rr() * (hMax - hMin), f = fachada(cc, c.semente + Math.round(x * 31 + z * 7)), l = lateral(cc);
        const o = malha(new T.BoxGeometry(w, h, d), [l, l, l, l, f, f], x + w / 2, h / 2, z); g.add(o); x += w + rr() * 0.12; } };
      fila(-7, escuro, 3.2, 6.2, 2.2); fila(-2.6, base, 1.3, 3.0, 1.8);
      const chao = malha(new T.PlaneGeometry(70, 12), mat(cor('--fundo').clone().lerp(base, 0.3)), 15, 0, 3); chao.rotation.x = -Math.PI / 2; chao.castShadow = false; g.add(chao);
      g.add(caixa(70, 0.04, 0.1, DEST, 15, 0, -1.5)); for (let x = -8; x < 40; x += 1.3) g.add(caixa(0.6, 0.02, 0.09, SUA, x, 0, 1.0));
      const P = c.par.poses, sc = document.createElement('canvas'); sc.width = 18 * P; sc.height = 26; const q = sc.getContext('2d'), pele = '#e9c7a0', roupa = luz, sapato = '#' + cor('--fundo').getHexString();
      for (let p = 0; p < P; p++) { const x = p * 18, f = Math.sin(2 * Math.PI * p / P), pe = Math.round(f * 3); q.fillStyle = pele; q.fillRect(x + 6, 1, 7, 7); q.fillStyle = sapato; q.fillRect(x + 6, 1, 7, 2); q.fillStyle = roupa; q.fillRect(x + 5, 8, 9, 10);
        q.fillStyle = sapato; q.fillRect(x + 7 + pe, 18, 2, 7); q.fillRect(x + 10 - pe, 18, 2, 7); q.fillStyle = pele; q.fillRect(x + 3, 9 + (f > 0 ? 1 : 0), 2, 7); }
      const st = new T.CanvasTexture(sc); st.magFilter = st.minFilter = T.NearestFilter; st.colorSpace = T.SRGBColorSpace; st.repeat.x = 1 / P;
      const pers = new T.Mesh(new T.PlaneGeometry(0.72, 1.04), new T.MeshBasicMaterial({ map: st, transparent: true, alphaTest: 0.5 })); g.add(pers);
      const mov = c.par.deslocamento_camera * 40, parada = Math.max(0.3, c.fases[2]), x0 = ci * mov;
      return (lt) => { const k = liso(lt / parada), x = x0 + mov * k; st.offset.x = lt < parada ? (Math.floor(lt * c.par.fps_sprite) % P) / P : 0;
        pers.position.set(x - 2.4, 0.5, 0.2); cam.position.set(x + 1.6, 2.6, 15); cam.lookAt(x, 2.0, -2); };
    },
    'jardim-de-luz': (c, g) => {
      const rr = rng(c.semente + 5), n = c.par.camadas, forma = new T.Shape(); forma.moveTo(-0.5, 0); forma.quadraticCurveTo(0, 0.2, 0.5, 0); forma.quadraticCurveTo(0, -0.2, -0.5, 0);
      const folha = new T.ShapeGeometry(forma, 6), grupos = [], aux = new T.Object3D(), tom = (k) => cor('--fundo').clone().lerp(cor('--destaque'), 0.34 + 0.46 * k);
      for (let k = 0; k < n; k++) { const gr = new T.Group(), prof = n > 1 ? k / (n - 1) : 1, N = 105, m = new T.InstancedMesh(folha, new T.MeshStandardMaterial({ color: tom(prof), side: T.DoubleSide, roughness: 0.9 }), N);
        for (let i = 0; i < N; i++) { let x, y; do { x = (rr() - 0.5) * 11; y = (rr() - 0.5) * 9.5; } while ((x * x) / 8.5 + (y * y) / 6 < 1 + 0.4 * (1 - prof));
          aux.position.set(x, y, -prof * 2.4 + rr() * 0.3); aux.rotation.set((rr() - 0.5) * 0.7, (rr() - 0.5) * 0.7, Math.atan2(y, x) + (rr() - 0.5)); aux.scale.setScalar(0.75 + rr() * 0.75); aux.updateMatrix(); m.setMatrixAt(i, aux.matrix); }
        m.castShadow = true; m.receiveShadow = true; gr.add(m); g.add(gr); grupos.push({ gr, w: 0.7 + rr() * 0.5, f: rr() * 6 }); }
      const fundo = malha(new T.PlaneGeometry(24, 18), new T.MeshStandardMaterial({ color: cor('--superficie'), roughness: 1 }), 0, 0, -3.2); fundo.castShadow = false; g.add(fundo);
      const luz = new T.PointLight(cor('--primaria').getHex(), 26, 11, 1.5); luz.castShadow = true; luz.shadow.mapSize.set(512, 512); luz.shadow.bias = -0.004; g.add(luz);
      const brilho = document.createElement('canvas'); brilho.width = brilho.height = 64; const q = brilho.getContext('2d'), gd = q.createRadialGradient(32, 32, 2, 32, 32, 32), pc = '#' + cor('--primaria').getHexString(); gd.addColorStop(0, pc); gd.addColorStop(1, pc + '00'); q.fillStyle = gd; q.fillRect(0, 0, 64, 64);
      const sp = new T.SpriteMaterial({ map: new T.CanvasTexture(brilho), transparent: true, depthWrite: false, blending: T.AdditiveBlending }), ponto = new T.Sprite(sp); ponto.scale.setScalar(1.3); g.add(ponto);
      for (let i = 0; i < c.par.luzes; i++) { const s = new T.Sprite(sp); s.scale.setScalar(0.22 + rr() * 0.2); const a = rr() * 6.28; s.position.set(Math.cos(a) * (2.6 + rr() * 2), Math.sin(a) * (2 + rr() * 1.6), 0.5); g.add(s); }
      const via = new T.CatmullRomCurve3([new T.Vector3(-4.2, -3.6, 1), new T.Vector3(-2.4, -1.4, 1.1), new T.Vector3(0.8, -2.8, 1), new T.Vector3(0, -1.75, 1.2)]);
      const bal = c.par.balanco_graus * Math.PI / 180, dur = Math.max(1, c.fim - c.inicio), t0 = c.fases[0], t1 = Math.max(c.fases[2], t0 + 0.8);
      return (lt) => { const p = clamp((lt - t0) / (t1 - t0)), k = 0.46 * liso(p / 0.42) + 0.54 * liso((p - 0.56) / 0.44), abs = c.inicio + lt; // duas pausas, com a ambientação no tempo absoluto
        grupos.forEach((o) => { o.gr.rotation.z = bal * Math.sin(abs * o.w + o.f); }); via.getPointAt(k, luz.position); ponto.position.copy(luz.position);
        luz.intensity = 26 * (1 - 0.55 * liso((lt - c.fases[3]) / Math.max(0.5, dur - c.fases[3]))); cam.position.set(0, 0, 11.6 * (1 - c.par.aproximacao_relativa * lt / dur)); cam.lookAt(0, 0, 0); };
    },
    'janela-em-profundidade': (c, g) => {
      const rr = rng(c.semente + 21), n = c.par.camadas, largo = 14 * (1 + c.par.folga_borda * 4), ceu = cor('--texto').clone().lerp(cor('--primaria'), 0.55);
      const fundo = new T.Mesh(new T.PlaneGeometry(90, 50), new T.MeshBasicMaterial({ color: ceu, fog: false })); fundo.position.z = -22; g.add(fundo);
      const astro = new T.Mesh(new T.CircleGeometry(1.9, 40), new T.MeshBasicMaterial({ color: cor('--texto'), fog: false })); astro.position.set(3.4, 4.2, -21); g.add(astro);
      for (let k = 0; k < n; k++) { const prof = n > 1 ? k / (n - 1) : 1, z = -16 + prof * 16, base = 3.4 - prof * 5.2, sh = new T.Shape(); sh.moveTo(-largo, -14); let x = -largo;
        while (x < largo) { sh.lineTo(x, base + (rr() - 0.5) * (1.4 + prof * 1.3)); x += 1.2 + rr() * 2.4; } sh.lineTo(largo, -14); sh.lineTo(-largo, -14);
        const cc = (k % 2 ? cor('--destaque') : cor('--primaria')).clone().lerp(cor('--fundo'), prof * 0.75);
        const o = malha(new T.ExtrudeGeometry(sh, { depth: 0.9, bevelEnabled: false }), new T.MeshStandardMaterial({ color: cc, roughness: 1, flatShading: true }), 0, 0, z); g.add(o); }
      const folha = (lado) => { const pivo = new T.Group(), hl = M.janelaMeia; pivo.position.set(lado * hl, 1.4, 4.2); const f = malha(new T.BoxGeometry(hl, 9, 0.12), mat(cor('--fundo')), -lado * hl / 2, 0, 0); pivo.add(f); g.add(pivo); return pivo; };
      const fe = folha(-1), fd = folha(1), m = c.par.paralaxe_maxima * 40, dur = Math.max(1, c.fim - c.inicio); cena.fog = new T.Fog(ceu.getHex(), 14, 58 - c.par.desfoque_maximo_px * 10);
      return (lt) => { const k = liso((lt - c.fases[0]) / 0.7), p = liso(lt / dur), x = m * (p - 0.5); fe.rotation.y = 1.75 * k; fd.rotation.y = -1.75 * k; cam.position.set(x, 1.4, 14.5); cam.lookAt(x * 0.6, 1.4, 0); };
    },
    'mesa-em-profundidade': (c, g, ci) => {
      const n = c.n, w = 3.1, h = 2.0, tampo = malha(new T.BoxGeometry(16, 0.12, 11), SUP, 0, -0.06, -2); tampo.castShadow = false; g.add(tampo);
      const r0 = rng(c.semente + 9), cards = [];
      for (let i = 0; i < n; i++) { const o = new T.Group(), corpo = caixa(w, h, 0.09, mat(cor('--superficie').clone().lerp(cor('--texto'), 0.1)), 0, 0, 0), borda = caixa(w + 0.1, 0.06, 0.1, i === 0 ? PRIM : DEST, 0, -0.03, 0); o.add(corpo, borda); o.rotation.y = (r0() - 0.5) * c.par.rotacao_maxima_graus * Math.PI / 90; g.add(o); cards.push(o); }
      const el = document.getElementById('cena-' + (c.indice + 1)), sv = el ? [...el.querySelectorAll('[data-cartao]')] : [], v = new T.Vector3(), av = c.par.avanco_relativo * 7, dur = Math.max(1, c.fim - c.inicio), ts = c.ts.concat([dur]);
      const px = (a) => { a.project(cam); return [(a.x + 1) / 2 * M.W, (1 - a.y) / 2 * M.H]; };
      return (lt) => { const camX = c.par.paralaxe_maxima * 8 * (lt / dur - 0.5); cam.position.set(camX + 1.0, 3.0, 11.5); cam.lookAt(camX * 0.5 + 0.9, 0.35, -1); cam.updateMatrixWorld();
        let ativa = 0; ts.slice(0, n).forEach((t, i) => { if (lt >= t) ativa = i; });
        cards.forEach((o, i) => { const fim = ts[i + 1] ?? dur, ultima = i === n - 1, ida = liso((lt - ts[i]) / 0.45), volta = ultima ? 0 : liso((lt - fim + 0.45) / 0.45), k = ida - volta; o.position.set(i * 1.25 - 0.4 + (0.85 - i * 1.25) * k, 0, -i * 1.7 + (i * 1.7 + 1.2 + av) * k); o.updateMatrixWorld();
          const g2 = sv.find((e) => +e.dataset.cartao === i); if (!g2) return; const a = px(v.set(-w / 2, h, 0).applyMatrix4(o.matrixWorld)), b = px(v.set(w / 2, h, 0).applyMatrix4(o.matrixWorld)), e = (b[0] - a[0]) / c.wc;
          g2.setAttribute('transform', `translate(${a[0].toFixed(1)} ${a[1].toFixed(1)}) scale(${e.toFixed(4)})`); g2.style.opacity = i === ativa ? 1 : 0; }); };
    },
    'camadas-do-terreno': (c, g) => {
      const n = c.par.niveis, cores = [SUA, PRIM, DEST, SUP], nv = [], lado = 2.1, alt = 0.36, canto = c.par.canto_removivel * lado;
      for (let i = 0; i < n; i++) { const b = new T.Group(); b.add(caixa(lado, alt, lado - canto, cores[i % 4], 0, 0, -canto / 2)); b.add(caixa(lado - canto, alt, canto, cores[i % 4], -canto / 2, 0, lado / 2 - canto / 2));
        b.position.y = i * (alt + 0.01); g.add(b); nv.push(b); }
      const topo = nv[n - 1]; [[-0.5, -0.4], [0.3, 0.1], [-0.2, 0.5]].forEach(([x, z], i) => topo.add(caixa(0.18, 0.2 + i * 0.1, 0.18, TXT, x, alt, z)));
      const marca = malha(new T.ConeGeometry(0.09, 0.26, 12), mat(cor('--texto'), { emissive: cor('--primaria'), emissiveIntensity: 0.6 }), 0, 0, 0); marca.rotation.x = Math.PI; g.add(marca);
      const sep = c.par.separacao_relativa * lado, el = c.par.angulo_camera_graus * Math.PI / 180, alto = n * alt + 0.5;
      return (lt) => { const fimc = c.fim - c.inicio - 0.95, k = liso((lt - c.fases[1]) / 0.7) - liso((lt - fimc) / 0.7), desce = liso((lt - c.fases[2]) / 0.9) - liso((lt - fimc) / 0.6);
        nv.forEach((b, i) => { const lado2 = i === 0 ? 0 : (i % 2 ? 1 : -1); b.position.x = lado2 * sep * k; });
        marca.position.set(lado * 0.3, alto - desce * (alto - 0.3), lado * 0.34); camera(AZ, el, 1); };
    },
  };

  const fab = D[M.direcao]; if (!fab) return;
  const cenas = M.cenas.map((c, ci) => { const g = new T.Group(); g.visible = false; if (!M.perspectiva) g.position.y = -0.35; cena.add(g); return { c, g, atualizar: fab(c, g, ci) }; });
  // o objeto fica no meio da área livre: acima da placa de texto
  if (!M.perspectiva) cam.setViewOffset(W, H, 0, Math.round((0.5 - M.alvoY) * H * 0.6 + H * 0.0), W, H);
  let ultimo = -1;
  function desenhar(t) {
    if (Math.abs(t - ultimo) < 1e-6) return; ultimo = t;
    let rc = null;
    for (const s of cenas) { const on = t >= s.c.inicio && t < s.c.fim; s.g.visible = on; if (on) { s.atualizar(t - s.c.inicio); rc = s.c.recorte || null; } }
    const bw = r.domElement.width, bh = r.domElement.height;
    r.setScissorTest(!!rc); r.setClearColor(0x000000, 0); r.clear();
    if (rc) r.setScissor(rc[0] * bw, (1 - rc[1] - rc[3]) * bh, rc[2] * bw, rc[3] * bh);
    r.render(cena, cam);
  }
  camera(AZ, ISO, 1); desenhar(0);
  let atual = 0;
  const tl = { duration: () => M.duracao, totalDuration: () => M.duracao, paused: () => true, pause: () => tl, play: () => tl,
    time: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)), totalTime: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)),
    seek: (v) => (atual = v, desenhar(v), tl), progress: (v) => (v === undefined ? atual / M.duracao : (atual = v * M.duracao, desenhar(atual), tl)) };
  window.__timelines = window.__timelines || {}; window.__timelines['clipator-arte3d'] = tl;
  const rel = document.getElementById('relogio3d');
  const laco = () => { const v = parseFloat(getComputedStyle(rel).getPropertyValue('--t3')); if (!isNaN(v)) desenhar(v); requestAnimationFrame(laco); };
  requestAnimationFrame(laco);
})();
"""

DIRECOES = {
    "oficina-modular": Direcao3D(_oficina),
    "costura-viva": Direcao3D(_costura),
    "terrario-tecnico": Direcao3D(_terrario),
    "resina-em-movimento": Direcao3D(_resina),
    "mecanismo-facetado": Direcao3D(_mecanismo),
    "camadas-do-terreno": Direcao3D(_terreno),
}
