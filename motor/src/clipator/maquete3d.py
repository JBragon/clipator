"""Maquete low-poly em 3D: as peças da "Maquete explicativa" modeladas e iluminadas com three.js (MIT).

A camada de cenas (direcao.compor_camada) continua desenhando o HUD em SVG (cabeçalho, chip da etapa,
cartões com fio, painel do dado, carimbo); aqui entra só a maquete: um <canvas> atrás das cenas onde o
script abaixo monta, para cada cena, as peças pedidas pela IA (mesmos nomes da biblioteca 2D), com luz,
sombra no chão e uma câmera ortográfica que passeia e chega perto ao longo de cada etapa. Os cartões dos
rótulos seguem as peças na tela.

O tempo vem do HyperFrames: o script registra uma "timeline" em window.__timelines que ele busca quadro a
quadro (e, por garantia, lê a variável CSS --t de um elemento animado). Nada de Math.random nem relógio de
parede, então o render é determinístico. Sem WebGL (ou sem o three.js), o script não faz nada e a camada
fica com as peças facetadas em SVG (maquete.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def caminho_three() -> Path | None:
    """O three.min.js: CLIPATOR_THREE, ou o do app (dependência npm do Clipator)."""
    env = os.environ.get("CLIPATOR_THREE")
    candidatos = [Path(env)] if env else []
    raiz = Path(__file__).resolve().parents[3]  # .../clipator (repositório)
    candidatos += [raiz / "app" / "node_modules" / "three" / "build" / "three.min.js",
                   Path(__file__).resolve().parent / "dados" / "vendor" / "three.min.js"]  # a cópia que vai no pacote do motor
    return next((p for p in candidatos if p.is_file()), None)


def disponivel() -> bool:
    return caminho_three() is not None


def camada(cenas: list[dict[str, Any]], duracao: float) -> tuple[str, str]:
    """(HTML do canvas, scripts) para a camada de cenas. Vazio se o three.js não estiver instalado."""
    p = caminho_three()
    if p is None:
        return "", ""
    dados = [{"inicio": round(float(c["inicio"]), 3), "fim": round(float(c["fim"]), 3),
              "camadas": [{k: v for k, v in x.items() if k in ("tipo", "peca", "x", "y", "escala", "entra", "acao", "cor", "quantos")}
                          for x in (c["params"].get("camadas") or [])]}
             for c in cenas if c["params"].get("cena") == "desenho"]
    html = '<canvas id="maquete3d"></canvas><div id="relogio3d"></div>'
    # o JSON vai dentro de <script>: "</" nunca pode aparecer
    js_dados = json.dumps({"cenas": dados, "duracao": duracao}, ensure_ascii=False).replace("</", "<\\/")
    script = (f"<script>{p.read_text(encoding='utf-8')}</script>\n"
              f"<script>window.MAQUETE = {js_dados};</script>\n<script>{JS}</script>")
    return html, script


def css(duracao: float) -> str:
    return CSS.replace("DURACAO_N", f"{duracao:.3f}")


CSS = """
#maquete3d { position: absolute; left: 0; top: var(--topo); width: 100%; height: var(--alt); }
#relogio3d { position: absolute; width: 1px; height: 1px; animation: relogio3d var(--duracao) linear both; }
@property --t3 { syntax: '<number>'; inherits: false; initial-value: 0; }
@keyframes relogio3d { from { --t3: 0; } to { --t3: DURACAO_N; } }
body.tres-d .palco .peca-use, body.tres-d .palco .sombra-2d { display: none; }
body.tres-d .cena.desenho .palco { animation: none !important; }
"""

# O script da maquete (nosso). Unidades: 1 unidade do mundo = 1 unidade do palco (1000 × 860) com zoom 1.
JS = r"""
(function () {
  const M = window.MAQUETE; if (!M || !window.THREE) return;
  const T = THREE, cv = document.getElementById('maquete3d');
  let r;
  try { r = new T.WebGLRenderer({ canvas: cv, antialias: true, alpha: true, preserveDrawingBuffer: true }); } catch (e) { return; }
  if (!r.getContext()) return;
  document.body.classList.add('tres-d');
  const css = getComputedStyle(document.documentElement), cor = (n) => new T.Color(css.getPropertyValue(n).trim() || '#ffffff');
  const W = cv.clientWidth, H = cv.clientHeight;
  r.setPixelRatio(1); r.setSize(W, H, false); r.shadowMap.enabled = true; r.shadowMap.type = T.PCFSoftShadowMap;
  r.outputColorSpace = T.SRGBColorSpace;
  const PW = 1000, PH = 860, s = Math.min(W / PW, H / PH), hw = W / s / 2, hh = H / s / 2;
  const cena = new T.Scene();
  const cam = new T.OrthographicCamera(-hw, hw, hh, -hh, 1, 8000);
  cena.add(new T.HemisphereLight(0xffffff, cor('--fundo').getHex(), 0.85));
  const sol = new T.DirectionalLight(0xffffff, 2.6); sol.castShadow = true;
  sol.shadow.mapSize.set(2048, 2048); Object.assign(sol.shadow.camera, { left: -900, right: 900, top: 900, bottom: -900, near: 10, far: 6000 });
  sol.shadow.radius = 6; sol.shadow.bias = -0.0008; cena.add(sol); cena.add(sol.target);
  const chao = new T.Mesh(new T.PlaneGeometry(6000, 6000), new T.ShadowMaterial({ opacity: 0.38 }));
  chao.rotation.x = -Math.PI / 2; chao.receiveShadow = true; cena.add(chao);

  // ---- materiais e primitivas (foscas, facetadas) ----
  const cache = {};
  const mat = (c) => { const k = c && c.isColor ? c.getHexString() : String(c); return cache[k] || (cache[k] = new T.MeshStandardMaterial({ color: c, roughness: 0.86, metalness: 0, flatShading: true })); };
  const CLARO = mat(cor('--lp-claro')), MEDIO = mat(cor('--lp-meio')), ESCURO = mat(cor('--lp-escuro'));
  const malha = (g, m, x, y, z) => { const o = new T.Mesh(g, m); o.position.set(x || 0, y || 0, z || 0); o.castShadow = true; o.receiveShadow = true; return o; };
  const caixa = (w, h, d, m, x, y, z) => malha(new T.BoxGeometry(w, h, d), m, x, (y || 0) + h / 2, z);
  const cil = (rt, rb, h, n, m, x, y, z) => malha(new T.CylinderGeometry(rt, rb, h, n), m, x, (y || 0) + h / 2, z);
  const bola = (rad, m, x, y, z, det) => malha(new T.IcosahedronGeometry(rad, det || 0), m, x, y, z);
  const placa = (pts, prof, m, buracos) => {  // forma 2D em pé, de frente para a câmera, com espessura
    const sh = new T.Shape(pts.map(([a, b]) => new T.Vector2(a, b)));
    (buracos || []).forEach((h) => sh.holes.push(new T.Path(h.map(([a, b]) => new T.Vector2(a, b)))));
    const g = new T.ExtrudeGeometry(sh, { depth: prof, bevelEnabled: true, bevelSize: 0.02, bevelThickness: 0.02, bevelSegments: 1, curveSegments: 3 });
    g.translate(0, 0, -prof / 2); return malha(g, m);
  };
  const barra = (x1, y1, x2, y2, e) => { const dx = x2 - x1, dy = y2 - y1, n = Math.hypot(dx, dy) || 1, ox = -dy / n * e / 2, oy = dx / n * e / 2;
    return [[x1 + ox, y1 + oy], [x2 + ox, y2 + oy], [x2 - ox, y2 - oy], [x1 - ox, y1 - oy]]; };
  const ngono = (cx, cy, rad, n, g0) => Array.from({ length: n }, (_, i) => [cx + rad * Math.cos((g0 || Math.PI / 2) + 2 * Math.PI * i / n), cy + rad * Math.sin((g0 || Math.PI / 2) + 2 * Math.PI * i / n)]);
  const icone = (partes, A, prof) => { const g = new T.Group(); partes.forEach(([pts, m]) => g.add(placa(pts, prof || 0.22, m || A))); g.userData.icone = true; return g; };

  // ---- as peças (mesmos nomes da biblioteca 2D); cada uma cabe em ~1 × 1.4, com a base em y = 0 ----
  const pessoa = (A, bracos, cheia) => { const g = new T.Group(); const rc = cheia ? 0.24 : 0.2;
    g.add(caixa(0.1, 0.42, 0.1, MEDIO, -0.08, 0, 0), caixa(0.1, 0.42, 0.1, MEDIO, 0.08, 0, 0), cil(rc * 0.85, rc, 0.46, 6, A, 0, 0.42, 0));
    if (bracos) g.add(caixa(0.08, 0.36, 0.08, CLARO, -0.27, 0.78, 0), caixa(0.08, 0.36, 0.08, CLARO, 0.27, 0.78, 0));
    else g.add(caixa(0.08, 0.36, 0.08, CLARO, -0.27, 0.5, 0), caixa(0.08, 0.36, 0.08, CLARO, 0.27, 0.5, 0));
    g.add(bola(0.21, CLARO, 0, 1.12, 0)); return g; };
  const P = {
    boneco: (A) => pessoa(A), boneco_bracos: (A) => pessoa(A, true), pessoa: (A) => pessoa(A, false, true),
    casa: (A) => { const g = new T.Group(); g.add(caixa(0.9, 0.55, 0.7, CLARO));
      const tel = malha(new T.CylinderGeometry(0.5, 0.5, 1.0, 3), A, 0, 0.55 + 0.25, 0); tel.rotation.z = Math.PI / 2; tel.scale.set(1, 1, 0.9); tel.position.y = 0.8; g.add(tel);
      g.add(caixa(0.18, 0.32, 0.02, ESCURO, 0.12, 0, 0.36)); return g; },
    predio: (A) => { const g = new T.Group(); g.add(caixa(0.6, 1.45, 0.6, CLARO), caixa(0.24, 0.14, 0.24, A, 0, 1.45, 0));
      for (let j = 0; j < 5; j++) for (let i = 0; i < 2; i++) g.add(caixa(0.12, 0.13, 0.02, ESCURO, -0.13 + i * 0.26, 0.2 + j * 0.24, 0.305)); return g; },
    predios: (A) => { const g = new T.Group(); [[-0.35, -0.3, 0.85, CLARO], [0.32, -0.34, 1.25, A], [-0.3, 0.33, 0.62, CLARO], [0.34, 0.3, 0.95, MEDIO]]
      .forEach(([x, z, h, m]) => g.add(caixa(0.4, h, 0.4, m, x, 0, z))); return g; },
    loja: (A) => { const g = new T.Group(); g.add(caixa(0.9, 0.6, 0.65, CLARO)); const t = caixa(0.96, 0.05, 0.3, A, 0, 0.6, 0.42); t.rotation.x = 0.35; g.add(t);
      g.add(caixa(0.2, 0.36, 0.02, ESCURO, -0.18, 0, 0.33)); return g; },
    celular: (A) => { const g = new T.Group(); g.add(caixa(0.62, 1.15, 0.12, CLARO), caixa(0.52, 0.98, 0.02, A, 0, 0.09, 0.07)); return g; },
    computador: (A) => { const g = new T.Group(); g.add(caixa(0.7, 0.05, 0.45, MEDIO), caixa(0.12, 0.25, 0.08, MEDIO, 0, 0.05, -0.05),
      caixa(0.95, 0.6, 0.08, CLARO, 0, 0.3, -0.05), caixa(0.85, 0.5, 0.02, A, 0, 0.35, 0.0)); return g; },
    moeda: (A) => { const g = new T.Group(); const m = cil(0.42, 0.42, 0.1, 10, A, 0, 0.42, 0); m.rotation.x = Math.PI / 2; m.position.y = 0.45; g.add(m);
      const c = cil(0.22, 0.22, 0.03, 10, CLARO); c.rotation.x = Math.PI / 2; c.position.set(0, 0.45, 0.055); g.add(c); return g; },
    nota: (A) => { const g = new T.Group(); for (let i = 0; i < 3; i++) { const n = caixa(0.95, 0.05, 0.5, i === 2 ? A : CLARO, 0, i * 0.05, 0); n.rotation.y = i * 0.12; g.add(n); } return g; },
    saco_dinheiro: (A) => { const g = new T.Group(); const b = bola(0.42, A, 0, 0.42, 0, 1); b.scale.y = 0.95; g.add(b, cil(0.06, 0.16, 0.22, 6, A, 0, 0.8, 0)); return g; },
    balanca: (A) => { const g = new T.Group(); g.add(caixa(0.5, 0.08, 0.3, MEDIO), caixa(0.07, 0.95, 0.07, CLARO, 0, 0.08, 0), caixa(1.2, 0.06, 0.07, A, 0, 1.0, 0));
      [-0.55, 0.55].forEach((x, i) => { g.add(caixa(0.012, 0.42, 0.012, ESCURO, x, 0.6 - i * 0.08, 0), cil(0.22, 0.17, 0.06, 8, CLARO, x, 0.55 - i * 0.08, 0)); }); return g; },
    grafico_sobe: (A) => { const g = new T.Group(); g.add(caixa(1.3, 0.05, 0.4, MEDIO)); [0.3, 0.55, 0.85, 1.2].forEach((h, i) => g.add(caixa(0.22, h, 0.22, i === 3 ? A : CLARO, -0.45 + i * 0.3, 0.05, 0))); return g; },
    grafico_desce: (A) => { const g = new T.Group(); g.add(caixa(1.3, 0.05, 0.4, MEDIO)); [1.2, 0.85, 0.55, 0.3].forEach((h, i) => g.add(caixa(0.22, h, 0.22, i === 3 ? A : CLARO, -0.45 + i * 0.3, 0.05, 0))); return g; },
    seta: (A) => icone([[[[-0.6, 0.12], [0.1, 0.12], [0.1, 0.32], [0.6, 0], [0.1, -0.32], [0.1, -0.12], [-0.6, -0.12]]]], A),
    balao: (A) => icone([[ngono(0, 0.1, 0.5, 12)], [[[-0.3, -0.28], [-0.05, -0.36], [-0.42, -0.62]], CLARO]], CLARO),
    check: (A) => icone([[barra(-0.5, 0, -0.15, -0.38, 0.22)], [barra(-0.23, -0.38, 0.55, 0.45, 0.22)]], A),
    x: (A) => icone([[barra(-0.45, -0.45, 0.45, 0.45, 0.24)], [barra(-0.45, 0.45, 0.45, -0.45, 0.24)]], A),
    interrogacao: (A) => icone([[barra(-0.3, 0.3, -0.12, 0.52, 0.18)], [barra(-0.15, 0.52, 0.2, 0.52, 0.18)], [barra(0.18, 0.54, 0.32, 0.3, 0.18)],
      [barra(0.32, 0.32, 0.03, 0.0, 0.18)], [barra(0.03, 0.02, 0.03, -0.2, 0.18)], [ngono(0.03, -0.45, 0.11, 6)]], A),
    exclamacao: (A) => icone([[barra(0, 0.6, 0, -0.15, 0.24)], [ngono(0, -0.45, 0.13, 6)]], A),
    relogio: (A) => { const g = icone([[ngono(0, 0, 0.55, 12)]], CLARO, 0.16); const p = icone([[barra(0, 0, 0, 0.38, 0.07)], [barra(0, 0, 0.26, -0.12, 0.07)]], A, 0.2); p.position.z = 0.06; g.add(p); return g; },
    calendario: (A) => { const g = new T.Group(); g.add(caixa(0.85, 0.85, 0.14, CLARO), caixa(0.85, 0.2, 0.16, A, 0, 0.66, 0));
      for (let j = 0; j < 2; j++) for (let i = 0; i < 3; i++) g.add(caixa(0.14, 0.12, 0.02, MEDIO, -0.24 + i * 0.24, 0.16 + j * 0.22, 0.08)); return g; },
    globo: (A) => { const g = new T.Group(); g.add(caixa(0.4, 0.06, 0.4, MEDIO), caixa(0.06, 0.2, 0.06, MEDIO, 0, 0.06, 0));
      const b = bola(0.5, CLARO, 0, 0.78, 0, 1); g.add(b); [[0.3, 0.95, 0.3], [-0.35, 0.7, 0.25], [0.1, 0.55, 0.45]].forEach(([x, y, z]) => g.add(bola(0.17, A, x * 0.8, y, z * 0.8, 0))); return g; },
    lupa: (A) => { const anel = new T.Group(); anel.add(placa(ngono(-0.12, 0.12, 0.42, 12), 0.14, CLARO, [ngono(-0.12, 0.12, 0.3, 12).reverse()]));
      anel.add(placa(barra(0.18, -0.18, 0.55, -0.55, 0.16), 0.18, A)); anel.userData.icone = true; return anel; },
    trofeu: (A) => { const g = new T.Group(); g.add(caixa(0.5, 0.12, 0.5, MEDIO), caixa(0.12, 0.3, 0.12, CLARO, 0, 0.12, 0), cil(0.42, 0.16, 0.5, 8, A, 0, 0.42, 0)); return g; },
    coracao: (A) => icone([[[[0, -0.6], [-0.55, -0.05], [-0.58, 0.28], [-0.4, 0.5], [-0.15, 0.5], [0, 0.3], [0.15, 0.5], [0.4, 0.5], [0.58, 0.28], [0.55, -0.05]]]], A),
    alerta: (A) => { const g = icone([[[[0, 0.62], [0.62, -0.5], [-0.62, -0.5]]]], A); const p = icone([[barra(0, 0.3, 0, -0.08, 0.12)], [ngono(0, -0.27, 0.07, 6)]], ESCURO, 0.3); g.add(p); return g; },
    cadeado: (A) => { const g = new T.Group(); g.add(caixa(0.8, 0.62, 0.3, A));
      const arco = malha(new T.TorusGeometry(0.24, 0.07, 6, 10, Math.PI), CLARO, 0, 0.62, 0); g.add(arco, caixa(0.14, 0.12, 0.14, CLARO, -0.24, 0.56, 0), caixa(0.14, 0.12, 0.14, CLARO, 0.24, 0.56, 0)); return g; },
    carro: (A) => { const g = new T.Group(); g.add(caixa(1.15, 0.3, 0.55, A, 0, 0.1, 0), caixa(0.6, 0.26, 0.5, CLARO, -0.05, 0.4, 0));
      [[-0.35, 0.28], [0.35, 0.28], [-0.35, -0.28], [0.35, -0.28]].forEach(([x, z]) => { const rd = cil(0.14, 0.14, 0.1, 8, ESCURO, x, 0, z); rd.rotation.x = Math.PI / 2; rd.position.y = 0.14; g.add(rd); }); return g; },
    barco: (A) => { const g = new T.Group(); const c = cil(0.42, 0.32, 0.25, 4, A, 0, 0, 0); c.scale.set(1.7, 1, 0.7); c.rotation.y = Math.PI / 4; g.add(c);
      g.add(caixa(0.5, 0.22, 0.4, CLARO, -0.1, 0.25, 0), caixa(0.32, 0.18, 0.3, CLARO, -0.1, 0.47, 0), caixa(0.04, 0.8, 0.04, MEDIO, 0.35, 0.25, 0)); return g; },
    lampada: (A) => { const g = new T.Group(); g.add(cil(0.16, 0.14, 0.25, 6, MEDIO), cil(0.2, 0.16, 0.08, 6, MEDIO, 0, 0.25, 0), bola(0.38, A, 0, 0.68, 0, 1)); return g; },
    megafone: (A) => { const g = new T.Group(); const c = cil(0.42, 0.14, 0.75, 8, A); c.rotation.z = -Math.PI / 2; c.position.set(0.1, 0.5, 0); g.add(c);
      g.add(caixa(0.12, 0.3, 0.12, CLARO, -0.2, 0.15, 0)); return g; },
    livro: (A) => { const g = new T.Group(); g.add(caixa(0.9, 0.06, 0.65, A), caixa(0.84, 0.16, 0.6, CLARO, 0.02, 0.06, 0), caixa(0.9, 0.06, 0.65, A, 0, 0.22, 0)); return g; },
    raio: (A) => icone([[[[0.15, 0.7], [-0.4, -0.05], [-0.05, -0.05], [-0.2, -0.7], [0.42, 0.12], [0.06, 0.12]]]], A),
    estrela: (A) => icone([[Array.from({ length: 10 }, (_, i) => { const rr = i % 2 ? 0.25 : 0.62, a = Math.PI / 2 + i * Math.PI / 5; return [rr * Math.cos(a), rr * Math.sin(a)]; })]], A),
    documento: (A) => { const g = new T.Group(); g.add(caixa(0.7, 0.95, 0.06, CLARO)); for (let i = 0; i < 4; i++) g.add(caixa(0.48, 0.04, 0.02, MEDIO, 0, 0.18 + i * 0.13, 0.035));
      g.add(caixa(0.16, 0.16, 0.03, A, 0.2, 0.74, 0.035)); return g; },
    porta: (A) => { const g = new T.Group(); g.add(caixa(0.75, 1.2, 0.14, CLARO), caixa(0.52, 1.0, 0.04, A, 0, 0, 0.07), bola(0.04, CLARO, 0.16, 0.5, 0.1)); return g; },
  };
  P.predio.alto = true;

  // ---- câmera de referência (isométrica, de lado a 45°) e a posição de cada peça no chão ----
  const DIST = 3000, ELEV = Math.atan(1 / Math.SQRT2);
  const pos = (az, zoom) => { cam.position.set(DIST * Math.cos(ELEV) * Math.sin(az), DIST * Math.sin(ELEV), DIST * Math.cos(ELEV) * Math.cos(az));
    cam.zoom = zoom; cam.lookAt(0, 0, 0); cam.updateProjectionMatrix(); cam.updateMatrixWorld(); };
  const AZ0 = Math.PI / 4; pos(AZ0, 1);
  const ray = new T.Raycaster(), plano = new T.Plane(new T.Vector3(0, 1, 0), 0), aux = new T.Vector3();
  const noChao = (x, y, altura) => {  // o ponto do palco (x, y) é o centro da peça: acha a base dela no chão
    ray.setFromCamera(new T.Vector2((x - PW / 2) / hw, (PH / 2 - y) / hh), cam);
    plano.constant = -altura / 2; ray.ray.intersectPlane(plano, aux); return new T.Vector3(aux.x, 0, aux.z);
  };
  const corCamada = { texto: '--texto', primaria: '--primaria', destaque: '--destaque', bom: '--bom', ruim: '--ruim', suave: '--suave' };
  const cenas = M.cenas.map((c, ci) => {
    const grupo = new T.Group(); grupo.visible = false; cena.add(grupo);
    const itens = [];
    c.camadas.forEach((l, li) => {
      if (l.tipo !== 'peca' && l.tipo !== 'multidao') return;
      const fab = P[l.peca]; if (!fab) return;
      const A = mat(cor(corCamada[l.cor] || '--destaque').getHex() === cor('--texto').getHex() ? cor('--lp-claro') : cor(corCamada[l.cor] || '--destaque'));
      const tam = 170 * l.escala * 0.78;
      const n = l.tipo === 'multidao' ? Math.min(40, l.quantos || 12) : 1;
      const raiz = new T.Group(), base = noChao(l.x, l.y, tam * 1.1);
      raiz.position.copy(base); grupo.add(raiz);
      for (let i = 0; i < n; i++) {
        const o = fab(A); const sc = n > 1 ? tam * 0.38 : tam; o.scale.setScalar(sc);
        if (n > 1) { const lin = Math.min(n, 8); o.position.set((i % lin - (lin - 1) / 2) * sc * 0.75, 0, Math.floor(i / lin) * sc * 0.75); }
        if (o.userData.icone) { o.position.y += sc * 0.65; o.rotation.y = AZ0; }
        raiz.add(o);
      }
      itens.push({ raiz, l, li, ancora: new T.Vector3(base.x, tam * 0.55, base.z), seed: ci * 7 + li });
    });
    return { c, ci, grupo, itens };
  });

  // ---- tempo: cada quadro mostra a cena ativa e anima as peças ----
  const ease = (k) => 1 - Math.pow(1 - k, 3), back = (k) => { const c1 = 1.5; return 1 + (c1 + 1) * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
  const clamp = (v) => Math.max(0, Math.min(1, v));
  const proj = new T.Vector3();
  let ultimo = -1;
  function desenhar(t) {
    if (Math.abs(t - ultimo) < 1e-6) return; ultimo = t;
    let ativa = null;
    for (const s of cenas) { const on = t >= s.c.inicio && t < s.c.fim; s.grupo.visible = on; if (on) ativa = s; }
    if (ativa) {
      const dur = Math.max(0.5, ativa.c.fim - ativa.c.inicio), p = clamp((t - ativa.c.inicio) / dur), lt = t - ativa.c.inicio;
      const lado = ativa.ci % 2 ? -1 : 1;
      pos(AZ0 + lado * (0.16 * ease(p) - 0.08), 1.1 - 0.1 * ease(p));  // a câmera passeia e chega perto
      cv.style.filter = `blur(${(5 * (1 - clamp(p / 0.12))).toFixed(2)}px)`;
      for (const it of ativa.itens) {
        const k = clamp((lt - it.l.entra) / 0.55), e = ease(k); let sx = 1, sy = 1, dy = 0, dx = 0, rz = 0;
        switch (it.l.acao) {
          case 'pop': sx = sy = k ? back(k) : 0; break;
          case 'cai': dy = (1 - e) * 420; sx = sy = k ? 1 : 0; break;
          case 'cresce': sy = e; sx = k ? 1 : 0; break;
          case 'desliza': dx = -(1 - e) * 260; sx = sy = k ? 1 : 0; break;
          case 'desenha': sx = sy = e; it.raiz.rotation.y = (1 - e) * 1.6; break;
          case 'pulsa': sx = sy = (k ? back(k) : 0) * (1 + 0.05 * Math.sin(lt * 4.5)); break;
          case 'treme': sx = sy = k ? 1 : 0; rz = k >= 1 ? 0.08 * Math.sin(lt * 22) * Math.max(0, 1 - (lt - it.l.entra - 0.55) / 1.2) : 0; break;
          default: sx = sy = 1;
        }
        it.raiz.scale.set(Math.max(1e-3, sx), Math.max(1e-3, sy), Math.max(1e-3, sx));
        it.raiz.position.y = dy; it.raiz.rotation.z = rz;
        it.raiz.children.forEach((o, i) => { o.position.y = (o.userData.icone ? 0.65 * o.scale.x : 0) + Math.sin(lt * 1.6 + i + it.seed) * 4; });
      }
      // os cartões dos rótulos e as outras camadas do HUD seguem a câmera
      const el = document.getElementById('cena-' + (ativa.ci + 1));
      const zoom = cam.zoom;
      if (el) el.querySelectorAll('.palco > g[data-k]').forEach((g) => {
        const k = +g.dataset.k, it = ativa.itens.find((x) => x.li === k);
        let px, py;
        if (it) { proj.copy(it.ancora); proj.project(cam); px = PW / 2 + proj.x * hw; py = PH / 2 - proj.y * hh; }
        else { px = PW / 2 + (+g.dataset.x - PW / 2) * zoom; py = PH / 2 + (+g.dataset.y - PH / 2) * zoom; }
        g.setAttribute('transform', `translate(${px.toFixed(1)} ${py.toFixed(1)})`);
      });
    }
    sol.position.set(cam.position.x * 0.4 - 600, 1800, cam.position.z * 0.4 + 300);
    r.render(cena, cam);
  }
  desenhar(0);
  // o HyperFrames busca as timelines registradas quadro a quadro; o relógio CSS é a garantia
  let atual = 0;
  const tl = { duration: () => M.duracao, totalDuration: () => M.duracao, paused: () => true, pause: () => tl, play: () => tl,
    time: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)), totalTime: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)),
    seek: (v) => (atual = v, desenhar(v), tl), progress: (v) => (v === undefined ? atual / M.duracao : (atual = v * M.duracao, desenhar(atual), tl)) };
  window.__timelines = window.__timelines || {}; window.__timelines['clipator-maquete'] = tl;
  const rel = document.getElementById('relogio3d');
  const laco = () => { const v = parseFloat(getComputedStyle(rel).getPropertyValue('--t3')); if (!isNaN(v)) desenhar(v); requestAnimationFrame(laco); };
  requestAnimationFrame(laco);
})();
"""
