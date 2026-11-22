// Mapa 3D do estilo Geo em Cena (Clipator, AGPL), com three.js (MIT). A terra é uma maquete: os países citados sobem do chão,
// a luz do sol projeta a sombra deles no resto do mapa, e a câmera inclinada voa de um lugar a outro (sobe no meio do caminho e
// desce no destino). Os polígonos e a projeção são os mesmos do geo.js (Natural Earth, equiretangular ou Mercator).
// Cada quadro é função de t: nada de Timer, Clock, setAnimationLoop nem Math.random (o HyperFrames busca quadros fora de ordem).
// Sem three.js ou sem WebGL, este script não liga window.GEO3D e o geo.js desenha o mapa em canvas 2D, como antes.
(function () {
  const M = window.GEO, THREE = window.THREE; if (!M || !THREE) return;
  const P = M.par || {}; if (P.leve) return; // a alternativa leve continua sendo o mapa plano
  const cv = document.getElementById('geo3d'), ov = document.getElementById('geo2d');
  if (!cv || !ov) return;
  const W = cv.clientWidth, H = cv.clientHeight;
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true, preserveDrawingBuffer: true, alpha: false }); } catch (e) { return; }
  if (!renderer.getContext()) return;
  window.GEO3D = true;
  renderer.setPixelRatio(1); renderer.setSize(W, H, false);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  ov.width = W; ov.height = H; const g = ov.getContext('2d');

  const G = M.geo || { foco: { x: W * 0.05, y: H * 0.08, w: W * 0.9, h: H * 0.84 } };
  const F = G.foco, FX = F.x + F.w / 2, FY = F.y + F.h / 2, esc = M.geo ? Math.min(M.geo.largura, M.geo.altura) / 1080 : W / 1080;
  const css = getComputedStyle(document.documentElement), cor = (n) => css.getPropertyValue(n).trim() || '#888888';
  const C = (h) => new THREE.Color(h);
  const FUNDO = cor('--fundo'), TEXTO = cor('--texto'), PRIM = cor('--primaria'), DEST = cor('--destaque'), SUP = cor('--superficie');
  const TERRA = C(SUP).lerp(C(TEXTO), 0.14), SUBTOM = TERRA.clone().lerp(C(PRIM), 0.45);
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), liso = (k) => { k = clamp(k); return k * k * (3 - 2 * k); };
  const MERC = P.projecao === 'mercator';
  const yDe = (lat) => { if (!MERC) return lat; const f = clamp(lat, -85, 85) * Math.PI / 180; return Math.asinh(Math.tan(f)) * 180 / Math.PI; };
  const giro = (d) => ((d + 180) % 360 + 360) % 360 - 180;

  // ---- geometria: anéis -> formas (cada anel uma forma; o par/ímpar do 2D vira sobreposição da mesma cor) ----------------
  const pontos = (a) => { const v = []; for (let i = 0; i < a.length; i += 2) v.push(new THREE.Vector2(a[i], yDe(a[i + 1]))); return v; };
  const formas = (lista) => lista.filter((a) => a.length >= 6).map((a) => new THREE.Shape(pontos(a)));
  const juntar = (geos) => { // mescla sem o BufferGeometryUtils (o three.min.js não traz os addons)
    let n = 0, m = 0; for (const q of geos) { n += q.attributes.position.count; m += q.index ? q.index.count : q.attributes.position.count; }
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), idx = new Uint32Array(m); let o = 0, oi = 0;
    for (const q of geos) { const c = q.attributes.position.count; pos.set(q.attributes.position.array, o * 3);
      if (q.attributes.normal) nor.set(q.attributes.normal.array, o * 3);
      if (q.index) { for (let i = 0; i < q.index.count; i++) idx[oi + i] = q.index.array[i] + o; oi += q.index.count; }
      else { for (let i = 0; i < c; i++) idx[oi + i] = o + i; oi += c; }
      o += c; q.dispose(); }
    const r = new THREE.BufferGeometry(); r.setAttribute('position', new THREE.BufferAttribute(pos, 3)); r.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    r.setIndex(new THREE.BufferAttribute(idx, 1)); r.computeBoundingSphere(); return r; };
  const plano = (lista) => juntar(formas(lista).map((s) => new THREE.ShapeGeometry(s)));
  const bloco = (lista) => juntar(formas(lista).map((s) => new THREE.ExtrudeGeometry(s, { depth: 1, bevelEnabled: false })));
  const linhas = (lista) => { const v = []; for (const a of lista) { const n = a.length / 2; for (let i = 0; i < n; i++) { const j = (i + 1) % n;
    v.push(a[2 * i], yDe(a[2 * i + 1]), 0, a[2 * j], yDe(a[2 * j + 1]), 0); } }
    const r = new THREE.BufferGeometry(); r.setAttribute('position', new THREE.Float32BufferAttribute(v, 3)); return r; };

  const PAISES = Object.fromEntries(M.paises.map((p) => [p.id, p.a])), TUDO = M.paises.flatMap((p) => p.a);
  const SUBS = M.subdivisoes || {}, CONT = M.continentes || {}, EV = M.eventos;
  const dentro = (x, y, lista) => { let d = false; for (const a of lista) { const n = a.length / 2;
    for (let i = 0, j = n - 1; i < n; j = i++) { const xi = a[2 * i], yi = yDe(a[2 * i + 1]), xj = a[2 * j], yj = yDe(a[2 * j + 1]);
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) d = !d; } } return d; };
  const centro = (lista) => { let m = null, area = -1; for (const a of lista) { let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (let i = 0; i < a.length; i += 2) { x0 = Math.min(x0, a[i]); x1 = Math.max(x1, a[i]); y0 = Math.min(y0, yDe(a[i + 1])); y1 = Math.max(y1, yDe(a[i + 1])); }
    const ar = (x1 - x0) * (y1 - y0); if (ar > area) { area = ar; m = [(x0 + x1) / 2, (y0 + y1) / 2]; } } return m || [0, 0]; };
  // continente: os países cujo miolo cai dentro dele (grupos de ilhas incluem oceano, então o polígono não sobe sozinho)
  const alvoDe = (e) => { if (e.nivel === 'pais') return PAISES[e.id] || [];
    if (e.nivel === 'continente') { const l = CONT[e.id] || []; return M.paises.filter((p) => { const c = centro(p.a); return dentro(c[0], c[1], l); }).flatMap((p) => p.a); }
    return ((SUBS[e.pais] || []).find((s) => s.id === e.id) || { a: [] }).a; };

  // ---- cena ---------------------------------------------------------------------------------------------------------------
  const cena = new THREE.Scene(); cena.background = C(FUNDO);
  const cam = new THREE.PerspectiveCamera(30, W / H, 0.01, 4000); cam.up.set(0, 0, 1);
  cam.setViewOffset(W, H, W / 2 - FX, H / 2 - FY, W, H); // o ponto olhado fica no centro do retângulo livre do layout
  cena.add(new THREE.HemisphereLight(C(TEXTO), C(DEST).lerp(C(FUNDO), 0.5), 1.25));
  const sol = new THREE.DirectionalLight(0xffffff, 1.5); sol.castShadow = true; sol.shadow.mapSize.set(1024, 1024); sol.shadow.bias = -0.002; sol.shadow.normalBias = 0.02;
  cena.add(sol, sol.target);

  const MAT_TERRA = new THREE.MeshLambertMaterial({ color: TERRA, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  const MAT_BORDA = new THREE.LineBasicMaterial({ color: C(TEXTO), transparent: true, opacity: 0.42 });
  const GEO_TERRA = plano(TUDO), GEO_BORDA = linhas(TUDO);
  const copias = [-1, 0, 1].map(() => { const gr = new THREE.Group(); const t = new THREE.Mesh(GEO_TERRA, MAT_TERRA); t.receiveShadow = true;
    gr.add(t, new THREE.LineSegments(GEO_BORDA, MAT_BORDA)); cena.add(gr); return gr; });
  const subGrupos = Object.entries(SUBS).map(([pais, l]) => { const a = l.flatMap((s) => s.a);
    const mat = new THREE.MeshLambertMaterial({ color: SUBTOM, transparent: true, opacity: 0 }), lm = new THREE.LineBasicMaterial({ color: C(TEXTO), transparent: true, opacity: 0 });
    const gr = new THREE.Group(); const m = new THREE.Mesh(plano(a), mat); m.receiveShadow = true; m.position.z = 0.002; const b = new THREE.LineSegments(linhas(a), lm); b.position.z = 0.003;
    gr.add(m, b); cena.add(gr); return { pais, gr, mat, lm }; });
  const destaques = EV.map((e) => { const a = alvoDe(e); const mat = new THREE.MeshLambertMaterial({ color: C(DEST), emissive: C(DEST), emissiveIntensity: 0.18, transparent: true, opacity: 0 });
    const m = new THREE.Mesh(bloco(a), mat); m.castShadow = true; // as paredes não recebem sombra: sem listras de acne
    const topo = new THREE.LineSegments(linhas(a), new THREE.LineBasicMaterial({ color: C(DEST).lerp(C(TEXTO), 0.7), transparent: true, opacity: 0 }));
    const gr = new THREE.Group(); gr.add(m, topo); cena.add(gr); return { m, mat, topo, gr }; });
  const grades = [60, 30, 10, 5, 2, 1, 0.5].map((p) => { const v = []; for (let x = -540; x <= 540; x += p) v.push(x, yDe(-85), -0.001, x, yDe(85), -0.001);
    for (let y = -80; y <= 80; y += p) v.push(-540, yDe(y), -0.001, 540, yDe(y), -0.001);
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
    const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: C(TEXTO), transparent: true, opacity: 0.07 })); l.visible = false; cena.add(l); return { p, l }; });

  // ---- câmera: os mesmos quadros do 2D, agora com inclinação e voo -------------------------------------------------------
  const ajustar = (c, folga) => { const y0 = yDe(c[1]), y1 = yDe(c[3]), k = folga * (P.vizinhos || 1.4);
    return { cx: (c[0] + c[2]) / 2, cy: (y0 + y1) / 2, s: Math.max(W / 360, Math.min(F.w / (Math.max(c[2] - c[0], 0.6) * k), F.h / (Math.max(y1 - y0, 0.6) * k))) }; };
  const Q = M.quadros.map((q) => ({ t: q.t, cam: ajustar(q.c, 1) }));
  const INICIO = M.quadros.length ? ajustar(M.quadros[0].c, 2.6) : ajustar([-180, -58, 180, 85], 1 / (P.vizinhos || 1.4));
  const DUR = Math.max(0.05, (P.aproximacao_s || 1.1) * 1.25);
  const camEm = (t) => { let c = INICIO, voo = 0;
    for (const q of Q) { if (q.t > t) break; const k0 = clamp((t - q.t) / Math.max(0.25, Math.min(DUR, M.duracao - q.t - 0.15))), k = liso(k0);
      const dist = Math.hypot(giro(q.cam.cx - c.cx), q.cam.cy - c.cy) * Math.min(c.s, q.cam.s) / F.w; // quanto a tela anda, em larguras
      voo = Math.max(voo * (1 - k), Math.sin(Math.PI * k0) * clamp(dist * 0.6, 0, 0.9));
      c = { cx: c.cx + giro(q.cam.cx - c.cx) * k, cy: c.cy + (q.cam.cy - c.cy) * k, s: Math.exp(Math.log(c.s) + (Math.log(q.cam.s) - Math.log(c.s)) * k) }; }
    return { ...c, voo }; };
  const INCL = (P.inclinacao === undefined ? 34 : P.inclinacao) * Math.PI / 180;
  const nivelDe = (e, t) => liso((t - e.t) / 0.45) * (1 - liso((t - e.tf) / 0.35));

  // ---- rótulos: texto em HTML (igual com ou sem 3D), presos ao topo do lugar que subiu ------------------------------------
  const rot = document.getElementById('rotulos3d');
  const ROT = EV.map((e) => { const d = document.createElement('div'); d.className = 'rot3 foco'; const b = document.createElement('b'), s = document.createElement('small');
    b.textContent = e.nome; s.textContent = e.desc; d.append(b, s); d.style.opacity = 0; if (P.rotulos !== false) rot.appendChild(d); return d; });
  let credH = 0;
  if (P.credito !== false) { const d = document.createElement('div'); d.className = 'geo-credito'; d.textContent = 'Natural Earth · projeção ' + (MERC ? 'de Mercator' : 'equiretangular');
    rot.appendChild(d); credH = d.offsetHeight + 8 * esc; d.style.transform = `translate(${F.x}px,${F.y + F.h - d.offsetHeight}px)`; }
  const v3 = new THREE.Vector3();
  const tela = (x, y, z) => { v3.set(x, y, z).project(cam); return [(v3.x + 1) / 2 * W, (1 - v3.y) / 2 * H]; };
  const rotulos = (t, c, alturas) => { g.clearRect(0, 0, W, H); const postos = [], baixo = F.y + F.h - credH;
    EV.forEach((e, i) => { const k = nivelDe(e, t), d = ROT[i]; d.style.opacity = k; if (k <= 0.01 || P.rotulos === false) return;
      const lon = c.cx + giro(e.anc[0] - c.cx); const [px, py] = tela(lon, yDe(e.anc[1]), alturas[i]);
      const ax = clamp(px, F.x + 12 * esc, F.x + F.w - 12 * esc), ay = clamp(py, F.y + 12 * esc, baixo - 12 * esc);
      const w = d.offsetWidth, h = d.offsetHeight, vao = 46 * esc;
      const x = clamp(ax - w / 2, F.x, Math.max(F.x, F.x + F.w - w)); let y = ay - h - vao; if (y < F.y) y = ay + vao; y = clamp(y, F.y, Math.max(F.y, baixo - h));
      for (const p of postos) if (x < p.x + p.w && p.x < x + w && y < p.y + p.h + 8 * esc && p.y < y + h + 8 * esc) y = p.y + p.h + 10 * esc;
      y = clamp(y, F.y, Math.max(F.y, baixo - h)); postos.push({ x, y, w, h }); d.style.transform = `translate(${x}px,${y}px)`;
      g.globalAlpha = k; g.strokeStyle = TEXTO; g.lineWidth = 2.5 * esc; g.beginPath(); g.moveTo(ax, ay); g.lineTo(clamp(ax, x + 8, x + w - 8), y < ay ? y + h : y); g.stroke();
      g.fillStyle = TEXTO; g.beginPath(); g.arc(ax, ay, 6 * esc, 0, 7); g.fill(); g.globalAlpha = 1; }); };

  const desenhar = (t) => {
    const c = camEm(t), visto = H / c.s; // quantos graus cabem na altura da tela
    const D = (H / (2 * Math.tan(cam.fov * Math.PI / 360) * c.s)) * (1 + c.voo);
    cam.position.set(c.cx, c.cy - D * Math.sin(INCL), D * Math.cos(INCL)); cam.lookAt(c.cx, c.cy, 0);
    cam.near = D * 0.02; cam.far = D * 8; cam.updateProjectionMatrix();
    const base = Math.round(c.cx / 360) * 360, meia = (W / c.s) * (1 + c.voo) * 1.6 + 2; // só a volta do mundo que aparece entra no quadro
    copias.forEach((gr, k) => { gr.position.x = base + (k - 1) * 360; gr.visible = Math.abs(gr.position.x - c.cx) < 180 + meia; });
    const passo = (grades.find((q) => q.p * c.s <= 260 * esc) || grades[grades.length - 1]).p;
    grades.forEach((q) => { q.l.visible = P.grade !== false && q.p === passo; q.l.position.x = base; });
    const alto = visto * 0.05; // a altura de um lugar aceso, proporcional ao que a câmera mostra
    const alturas = EV.map((e, i) => { const k = nivelDe(e, t), d = destaques[i];
      d.gr.visible = k > 0.002; d.gr.position.x = base + Math.round((c.cx - base - e.anc[0]) / 360) * 360;
      const h = Math.max(1e-4, alto * (e.nivel === 'continente' ? 0.5 : 1) * liso(k)); d.m.scale.z = h; d.topo.position.z = h + 1e-4;
      d.mat.opacity = Math.min(1, k * 1.6); d.topo.material.opacity = k; return h; });
    subGrupos.forEach((s) => { const k = Math.max(0, ...EV.map((e, i) => (e.pais === s.pais ? nivelDe(e, t) : 0))); s.gr.visible = k > 0.002;
      s.gr.position.x = base; s.mat.opacity = k; s.lm.opacity = 0.62 * k; });
    sol.position.set(c.cx - visto * 0.35, c.cy + visto * 0.55, visto * 0.9); sol.target.position.set(c.cx, c.cy, 0);
    const sc = sol.shadow.camera; sc.left = -visto; sc.right = visto; sc.top = visto; sc.bottom = -visto; sc.near = 0.01; sc.far = visto * 4; sc.updateProjectionMatrix();
    renderer.render(cena, cam);
    rotulos(t, c, alturas); };

  desenhar(0);
  let atual = 0;
  const tl = { duration: () => M.duracao, totalDuration: () => M.duracao, paused: () => true, pause: () => tl, play: () => tl,
    time: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)), totalTime: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)),
    seek: (v) => (atual = v, desenhar(v), tl), progress: (v) => (v === undefined ? atual / M.duracao : (atual = v * M.duracao, desenhar(atual), tl)) };
  window.__timelines = window.__timelines || {}; window.__timelines['clipator-geo'] = tl;
  const rel = document.getElementById('relogio3d'); let ultimo = -1;
  const laco = () => { const v = parseFloat(getComputedStyle(rel).getPropertyValue('--t3')); if (!isNaN(v) && v !== ultimo) { ultimo = v; desenhar(v); } requestAnimationFrame(laco); };
  requestAnimationFrame(laco);
})();
