// Motor das cinco direções guiadas pela fala (Clipator, AGPL). Monta o mundo do clip a partir do plano em window.CORTE e
// desenha cada quadro como função do tempo: nada de relógio, sorteio solto ou estado entre quadros, então buscar fora de
// ordem dá o mesmo quadro. Câmera e rótulos são calculados para o retângulo que o layout deu à arte (M.geo).
(function () {
  const M = window.CORTE; if (!M || !window.THREE) return;
  const T = THREE, cv = document.getElementById('arte3d'), P = M.par || {};
  let r;
  try { r = new T.WebGLRenderer({ canvas: cv, antialias: !M.pixel, preserveDrawingBuffer: true }); } catch (e) { return; }
  if (!r.getContext()) return;
  document.body.classList.add('tres-d');
  const W = cv.clientWidth, H = cv.clientHeight;
  const pxl = M.pixel ? Math.max(2, (P.tamanho_pixel || 4) * W / 1080) : 1;
  r.setPixelRatio(1); r.setSize(Math.round(W / pxl), Math.round(H / pxl), false);
  if (M.pixel) cv.style.imageRendering = 'pixelated';
  r.shadowMap.enabled = true; r.shadowMap.type = M.pixel ? T.BasicShadowMap : T.PCFSoftShadowMap; r.outputColorSpace = T.SRGBColorSpace;
  const css = getComputedStyle(document.documentElement), hexv = (n) => css.getPropertyValue(n).trim() || '#888888', cor = (n) => new T.Color(hexv(n));
  const PAL = [cor('--primaria'), cor('--destaque'), cor('--superficie'), cor('--texto'), cor('--texto')];
  const FUNDO = cor('--fundo');
  const cena = new T.Scene(); cena.background = FUNDO.clone();
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), liso = (k) => { k = clamp(k); return k * k * (3 - 2 * k); }, mix = (a, b, k) => a + (b - a) * k;
  const rng = (s) => () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };

  // ---- geometria da tela: tudo relativo ao retângulo da arte -------------------------------------------------------
  const G = M.geo || { layout: 'em-cima', exclusoes: [], foco: { x: W * 0.05, y: H * 0.08, w: W * 0.9, h: H * 0.84 }, seguro: { x: W * 0.04, y: H * 0.04, w: W * 0.92, h: H * 0.92 } };
  const esc = M.geo ? Math.min(M.geo.largura, M.geo.altura) / 1080 : W / 1080, F = G.foco, S = G.seguro;
  const FX = F.x + F.w / 2, FY = F.y + F.h / 2;

  // ---- o plano: objetos na ordem em que são ditos -------------------------------------------------------------------
  const AC = M.acoes, UNICA = M.estilo === 'pixel-em-cena' || M.estilo === 'terreno-vivo';
  const OBJ = [], porId = {};
  AC.forEach((a, i) => { a.i = i; a.ids = []; a.objetos.forEach((o) => {
    const k = UNICA ? o.forma : o.id; let x = porId[k];
    if (!x) { x = porId[k] = { id: k, nome: o.nome, forma: o.forma, t: o.t, ordem: OBJ.length, g: new T.Group(), acoes: [] }; OBJ.push(x); }
    x.acoes.push(a); a.ids.push({ o: x, t: o.t, nome: o.nome });
    if (o.id === a.alvo) a.foco = x; });
    if (!a.foco && a.ids.length) a.foco = a.ids[a.ids.length - 1].o; });
  const acaoEm = (t) => { let k = -1; for (const a of AC) if (a.t0 <= t) k = a.i; return k; };
  const conjunto = (AC.find((a) => a.conjunto) || {}).conjunto;

  // ---- materiais e peças --------------------------------------------------------------------------------------------
  const PEC = (f) => M.formas[f] || [];
  const altura = (f) => PEC(f).reduce((m, p) => Math.max(m, p[2] + p[5]), 0.2);
  const geoDe = (p, seg) => { const [k, , , , w, h, d] = p; if (k === 'c') { const b = new T.BoxGeometry(w, h, d); b.translate(0, h / 2, 0); return b; }
    if (k === 'r') { const b = new T.CylinderGeometry(w / 2, w / 2, h, seg); b.translate(0, h / 2, 0); return b; }
    if (k === 'p') { const b = new T.ConeGeometry(w / 2, h, seg); b.translate(0, h / 2, 0); return b; }
    const b = new T.SphereGeometry(0.5, seg, Math.max(4, Math.round(seg * 0.7))); b.scale(w, h, d); b.translate(0, h / 2, 0); return b; };
  const malha = (geo, m, x, y, z) => { const o = new T.Mesh(geo, m); o.position.set(x || 0, y || 0, z || 0); o.castShadow = true; o.receiveShadow = true; return o; };
  const lamb = (c, extra) => new T.MeshStandardMaterial(Object.assign({ color: c, roughness: 0.85, metalness: 0 }, extra || {}));

  // ---- câmera: enquadra uma caixa do mundo no retângulo livre -------------------------------------------------------
  const cam = new T.OrthographicCamera(-1, 1, 1, -1, 0.1, 400);
  const eixoR = new T.Vector3(), eixoU = new T.Vector3();
  const apontar = (az, el) => { cam.position.set(100 * Math.cos(el) * Math.sin(az), 100 * Math.sin(el), 100 * Math.cos(el) * Math.cos(az)); cam.lookAt(0, 0, 0); cam.updateMatrixWorld(); eixoR.setFromMatrixColumn(cam.matrixWorld, 0); eixoU.setFromMatrixColumn(cam.matrixWorld, 1); };
  const enquadrar = (b, folga) => { const q = [b.min, b.max]; let u0 = 1e9, u1 = -1e9, v0 = 1e9, v1 = -1e9; const p = new T.Vector3();
    for (const x of q) for (const y of q) for (const z of q) { p.set(x.x, y.y, z.z); const u = p.dot(eixoR), v = p.dot(eixoU); u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
    const f = folga || 1.12, du = (u1 - u0) * f, dv = (v1 - v0) * f; return { cu: (u0 + u1) / 2, cv: (v0 + v1) / 2, s: Math.min(F.w / Math.max(du, 0.01), F.h / Math.max(dv, 0.01)) }; };
  const aplicar = (q) => { const L = q.cu - FX / q.s, Tp = q.cv + FY / q.s; cam.left = L; cam.right = L + W / q.s; cam.top = Tp; cam.bottom = Tp - H / q.s; cam.updateProjectionMatrix(); };
  let QUADROS = [];
  const quadroEm = (t) => { let q = QUADROS[0]; for (let i = 1; i < QUADROS.length; i++) { const n = QUADROS[i]; if (n.t > t) break; const k = liso((t - n.t) / 0.7);
      q = { cu: mix(q.cu, n.cu, k), cv: mix(q.cv, n.cv, k), s: Math.exp(mix(Math.log(q.s), Math.log(n.s), k)) }; } return q; };

  // ---- rótulos: posição fixa por ação, calculada com a câmera já assentada; o fio segue o objeto ---------------------
  let atualizar = () => {};
  const camada = document.getElementById('rotulos3d');
  const NS = 'http://www.w3.org/2000/svg', svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`); camada.appendChild(svg);
  const cruza = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const proj = (v) => { const p = v.clone().project(cam); return { x: (p.x + 1) / 2 * W, y: (1 - p.y) / 2 * H }; };
  const fs = 38 * esc;
  const ROT = [];
  const retTela = (o) => { const b = o.caixa, q = [b.min, b.max]; let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9; for (const a of q) for (const c of q) for (const d of q) { const p = proj(new T.Vector3(a.x, c.y, d.z)); x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); } return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }; };
  const ancora = (o) => { const b = o.caixa; if (b.isEmpty()) return new T.Vector3(); return new T.Vector3((b.min.x + b.max.x) / 2, b.max.y, (b.min.z + b.max.z) / 2); };
  const novoRotulo = (texto, a, o, t) => { const d = document.createElement('div'); d.className = 'rot3' + (M.pixel ? ' pixel' : '') + (a.foco === o ? ' foco' : ''); d.textContent = texto; d.style.opacity = 0; camada.appendChild(d);
    const l = document.createElementNS(NS, 'path'); l.setAttribute('fill', 'none'); l.setAttribute('stroke', hexv(a.foco === o ? '--destaque' : '--primaria')); l.setAttribute('stroke-width', 3 * esc); l.setAttribute('opacity', 0); svg.appendChild(l);
    return { d, l, o, a, t, texto, w: texto.length * fs * 0.62 + 34 * esc, h: fs * 1.1 + 22 * esc }; };
  const assentar = (grupo, a) => { const ocup = G.exclusoes.slice(); const ts = Math.min(a.t1, a.t0 + 0.9); atualizar(ts); aplicar(quadroEm(ts)); cam.updateMatrixWorld();
    const corpos = OBJ.filter((o) => !o.caixa.isEmpty() && o.t <= ts).map(retTela);
    grupo.forEach((R) => { const p = proj(ancora(R.o)); let melhor = { x: S.x, y: S.y, w: R.w, h: R.h }, nota = 1e9;
      for (const [dx, dy] of [[0, -1.5], [1, -1], [-1, -1], [1.2, 0], [-1.2, 0], [1, 1], [-1, 1], [0, 1.5], [0, -3], [1.6, -2.4], [-1.6, -2.4]]) {
        const b = { x: p.x + dx * (R.w * 0.62) - R.w / 2, y: p.y + dy * (R.h * 1.4) - R.h / 2, w: R.w, h: R.h };
        b.x = clamp(b.x, S.x, S.x + S.w - b.w); b.y = clamp(b.y, S.y, S.y + S.h - b.h);
        const n = ocup.filter((e) => cruza(b, e)).length * 1000 + corpos.filter((e) => cruza(b, e)).length * 50 + Math.hypot(b.x + b.w / 2 - p.x, b.y + b.h / 2 - p.y) * 0.01;
        if (n < nota) { nota = n; melhor = b; } }
      R.b = melhor; ocup.push(melhor); R.d.style.transform = `translate(${melhor.x.toFixed(1)}px,${melhor.y.toFixed(1)}px)`; }); };
  const criarRotulos = () => { AC.forEach((a) => { const g = a.ids.filter((x) => porId[x.o.id]).map((x) => { const R = novoRotulo(x.nome, a, x.o, x.t); ROT.push(R); return R; }); if (g.length) assentar(g, a); }); };
  const desenharRotulos = (t) => { ROT.forEach((R) => { const fim = R.a.t1, k = liso((t - R.t) / 0.25) * (1 - liso((t - fim + 0.2) / 0.2));
    R.d.style.opacity = k.toFixed(3); R.l.setAttribute('opacity', k.toFixed(3));
    if (k > 0 && R.b) { const p = proj(ancora(R.o)), b = R.b, ex = clamp(p.x, b.x + 6, b.x + b.w - 6), ey = p.y < b.y ? b.y : (p.y > b.y + b.h ? b.y + b.h : b.y + b.h / 2); R.l.setAttribute('d', `M${ex.toFixed(1)} ${ey.toFixed(1)}L${ex.toFixed(1)} ${mix(ey, p.y, 0.5).toFixed(1)}L${p.x.toFixed(1)} ${p.y.toFixed(1)}`); } }); };

  // ---- trilho comum: uma figura (item ou personagem) passa pelos objetos na hora em que cada um é dito -----------------
  const trilho = (pontos) => (t) => { let i = 0; while (i + 1 < pontos.length && pontos[i + 1].t - 0.7 <= t) i++; const a = pontos[i], b = pontos[Math.min(i + 1, pontos.length - 1)];
    if (a === b) return a.p.clone(); const k = liso((t - (b.t - 0.7)) / 0.7); return a.p.clone().lerp(b.p, k); };

  const caixaDe = (g) => { g.updateMatrixWorld(true); return new T.Box3().setFromObject(g); };
  const caixaDe2 = (lista) => { const b = new T.Box3(); lista.forEach((o) => b.union(o.caixa)); return b; };

  // ================= Encaixe Vivo: peças plásticas com pinos que se montam por função ================================
  function encaixe() {
    apontar(0.72, 0.56);
    cena.add(new T.HemisphereLight(0xffffff, FUNDO.getHex(), 1.5));
    const sol = new T.DirectionalLight(0xffffff, 2.2); sol.position.set(-4, 9, 6); sol.castShadow = true; sol.shadow.mapSize.set(2048, 2048); Object.assign(sol.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: 1, far: 30 }); sol.shadow.bias = -0.0005; sol.shadow.radius = 4; cena.add(sol);
        const U = P.tamanho_bloco || 0.2, R = rng(M.semente), pinoG = new T.CylinderGeometry(U * 0.3, U * 0.3, U * 0.2, 12); const pos = {}; let topo = 0;
    const cj = conjunto ? M.conjuntos[conjunto] : null;
    OBJ.forEach((o, i) => { const c = cj && cj[o.forma]; if (c) o.pos = new T.Vector3(c[0], c[1], c[2]); else { o.pos = new T.Vector3(0, topo, 0); topo += altura(o.forma); } if (c) topo = Math.max(topo, c[1] + altura(o.forma)); });
    const todas = [];
    OBJ.forEach((o) => { o.pecas = []; o.mats = PAL.map((c) => new T.MeshStandardMaterial({ color: c, roughness: 0.32, metalness: 0, emissive: c, emissiveIntensity: 0 }));
      PEC(o.forma).forEach((p) => { const [k, x, y, z, w, h, d, ci] = p, n = Math.max(1, Math.round(h / (U * 0.9))), lh = h / n;
        for (let l = 0; l < n; l++) { const raio = k === 'p' ? (1 - l / n) : (k === 'e' ? Math.sqrt(Math.max(0.05, 1 - Math.pow(2 * (l + 0.5) / n - 1, 2))) : 1), ww = Math.max(U, w * raio), dd = Math.max(U, d * raio);
          const redondo = k !== 'c', nx = redondo ? 1 : Math.max(1, Math.round(ww / (U * 2.2))), nz = redondo ? 1 : Math.max(1, Math.round(dd / (U * 3)));
          for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) { const bw = ww / nx, bd = dd / nz, gg = new T.Group();
            const corpo = malha(redondo ? new T.CylinderGeometry(bw / 2 - 0.006, bw / 2 - 0.006, lh - 0.012, 20) : new T.BoxGeometry(bw - 0.014, lh - 0.012, bd - 0.014), o.mats[ci], 0, lh / 2, 0); gg.add(corpo);
            if (l === n - 1) { const qx = Math.max(1, Math.floor(bw / U)), qz = Math.max(1, Math.floor(bd / U)); for (let a = 0; a < qx; a++) for (let b = 0; b < qz; b++) gg.add(malha(pinoG, o.mats[ci], (a + 0.5) * bw / qx - bw / 2, lh + U * 0.08, (b + 0.5) * bd / qz - bd / 2)); }
            gg.userData.d = new T.Vector3(x + (i + 0.5) * bw - ww / 2, y + l * lh, z + (j + 0.5) * bd - dd / 2).add(o.pos);
            gg.userData.o = new T.Vector3(gg.userData.d.x + (R() - 0.5) * 3 + 1.5, gg.userData.d.y + 1.6 + R(), gg.userData.d.z + (R() - 0.5) * 3 + 1);
            const an = R() * 6.28, ra = 1.6 + R() * 1.5; gg.userData.c = new T.Vector3(Math.cos(an) * ra, 0, Math.sin(an) * ra); gg.userData.ry = R() * 3;
            o.g.add(gg); o.pecas.push(gg); todas.push(gg); gg.position.copy(gg.userData.d); } } });
      cena.add(o.g); o.caixa = caixaDe(o.g); });
    const tudo = caixaDe2(OBJ.length ? OBJ : [{ caixa: new T.Box3(new T.Vector3(-1, 0, -1), new T.Vector3(1, 1, 1)) }]);
    const raio = Math.max(1.5, Math.hypot(tudo.max.x - tudo.min.x, tudo.max.z - tudo.min.z) * 0.85);
    const mesa = malha(new T.CylinderGeometry(raio, raio, 0.1, 64), lamb(FUNDO.clone().multiplyScalar(0.9)), 0, -0.05, 0); mesa.castShadow = false; cena.add(mesa);
    todas.forEach((p) => p.userData.c.multiplyScalar(raio / 3.1 * 0.8));
    const soltas = []; for (let i = 0; i < (P.pecas_soltas || 0); i++) { const m = malha(new T.BoxGeometry(U * 2, U * 0.9, U), lamb(PAL[i % 2 ? 2 : 4], { roughness: 0.32 }), 0, 0, 0); const an = R() * 6.28, ra = raio * (0.76 + R() * 0.2); m.position.set(Math.cos(an) * ra, U * 0.45, Math.sin(an) * ra); m.rotation.y = R() * 3; cena.add(m); soltas.push(m); }
    const inicio = (o, i) => o.t + i * Math.min(0.05, (P.duracao_montagem || 1) / Math.max(1, o.pecas.length));
    const des = AC.filter((a) => a.acao === 'desmontar');
    const b0 = tudo.clone(); b0.union(new T.Box3(new T.Vector3(-raio * 0.72, 0, -raio * 0.72), new T.Vector3(raio * 0.72, 0.1, raio * 0.72)));
    QUADROS = [{ t: 0, ...enquadrar(b0, 0.82) }];
    AC.forEach((a) => { if (a.acao === 'destacar' && a.foco) { const b = a.foco.caixa.clone(); b.expandByScalar(0.3 + 0.8 * (0.6 - (P.aproximacao === undefined ? 0.3 : P.aproximacao))); QUADROS.push({ t: a.t0, ...enquadrar(b, 1.1) }); } else if (a.foco) QUADROS.push({ t: a.t0, ...enquadrar(b0, 0.82) }); });
    return (t) => { const am = 1 - (P.amortecimento || 0.5) * 0.8;
      OBJ.forEach((o) => { const n = o.pecas.length; const ac = AC[acaoEm(t)], foco = ac && ac.foco === o && ac.acao !== 'desmontar';
        o.mats.forEach((m) => { m.emissiveIntensity = foco ? 0.16 + 0.1 * Math.sin((t - ac.t0) * 5) : 0; });
        const d = des.find((a) => !a.ids.length || a.ids.some((x) => x.o === o) || a.ids.every((x) => !porId[x.o.id]) || true);
        o.pecas.forEach((p, i) => { const u = p.userData, t0 = inicio(o, i), k = clamp((t - t0) / 0.42);
          if (k <= 0) { p.visible = false; return; } p.visible = true;
          const e = liso(k), salto = Math.exp(-6 * k) * Math.sin(k * 14) * 0.08 * am * (k > 0.7 ? 1 : 0);
          p.position.lerpVectors(u.o, u.d, e); p.position.y += Math.sin(e * Math.PI) * 0.5 + salto; p.rotation.y = (1 - e) * u.ry;
          if (d && t >= d.t0) { const q = liso((t - d.t0 - (n - i) * Math.min(0.03, 0.9 / n)) / 0.5); if (q > 0) { p.position.lerpVectors(u.d, u.c, q); p.position.y = mix(u.d.y, 0.02, q) + Math.sin(q * Math.PI) * 0.7; p.rotation.y = q * u.ry; } } }); }); };
  }

  // ================= Fluxo Facetado: operação em etapas, com causa e efeito visíveis =================================
  function fluxo() {
    apontar(0.5, 0.62);
    cena.add(new T.HemisphereLight(0xcfe6ff, FUNDO.getHex(), 1.0));
    const sol = new T.DirectionalLight(0xffffff, 2.4); sol.position.set(-5, 10, 6); sol.castShadow = true; sol.shadow.mapSize.set(2048, 2048); Object.assign(sol.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 1, far: 40 }); sol.shadow.bias = -0.0005; cena.add(sol);
    const seg = P.facetas || 6, R = rng(M.semente + 3);
    const facetado = (geo) => { const q = geo.toNonIndexed(), a = q.attributes.position; for (let i = 0; i < a.count; i++) { const h = Math.sin(a.getX(i) * 12.9 + a.getY(i) * 78.2 + a.getZ(i) * 37.7) * 43758.5; a.setY(i, a.getY(i) + (h - Math.floor(h) - 0.5) * 0.012); } q.computeVertexNormals(); return q; };
    const mapa = (c) => lamb(c, { flatShading: true, roughness: 0.92 });
    const item = OBJ.find((o) => M.moveis.includes(o.forma) && o.forma !== 'pessoa') || OBJ.find((o) => M.moveis.includes(o.forma)) || OBJ[0];
    const postos = OBJ.filter((o) => o !== item && o.forma !== 'esteira'), trilhos = OBJ.filter((o) => o.forma === 'esteira');
    const sep = AC.find((a) => a.acao === 'separar'), idxSep = sep && sep.foco ? postos.indexOf(sep.foco) : -1;
    const passo = 2.1, x0 = -(postos.length) * passo / 2;
    const pts = [new T.Vector3(x0 - 1.2, 0.2, 0)];
    postos.forEach((o, i) => { const desvia = idxSep >= 0 && i > idxSep; o.pos = new T.Vector3(x0 + (i + 0.5) * passo, 0, desvia ? 1.5 : 0); pts.push(new T.Vector3(o.pos.x, 0.2, o.pos.z)); });
    const fimX = pts[pts.length - 1].x + 1.2, fimZ = pts[pts.length - 1].z; pts.push(new T.Vector3(fimX, 0.2, fimZ));
    const piso = malha(new T.BoxGeometry(120, 0.16, 120), mapa(FUNDO.clone().lerp(PAL[2], 0.5)), 0, -0.18, 0); piso.castShadow = false; cena.add(piso); cena.background = FUNDO.clone().lerp(PAL[2], 0.35);
    for (let i = 0; i + 1 < pts.length; i++) { const a = pts[i], b = pts[i + 1], L = a.distanceTo(b), m = malha(facetado(new T.BoxGeometry(L + 0.1, 0.16, 0.7)), mapa(PAL[4].clone().lerp(FUNDO, 0.35)), (a.x + b.x) / 2, 0.02, (a.z + b.z) / 2); m.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x); cena.add(m); }
    if (idxSep >= 0) { const a = pts[idxSep + 1], m = malha(new T.BoxGeometry(2.4, 0.16, 0.7), mapa(PAL[4].clone().lerp(FUNDO, 0.6)), a.x + 1.3, 0.02, a.z); cena.add(m); }
    const faz = (o) => { o.mats = PAL.map((c) => lamb(c, { flatShading: true, roughness: 0.92, emissive: c, emissiveIntensity: 0 })); o.movel = new T.Group();
      PEC(o.forma).forEach((p) => { const m = malha(facetado(geoDe(p, seg)), o.mats[p[7]], p[1], p[2], p[3]); (p[8] ? o.movel : o.g).add(m); }); o.g.add(o.movel); };
    OBJ.forEach((o) => { faz(o); o.pos = o.pos || new T.Vector3(); o.g.position.copy(o.pos); cena.add(o.g); o.caixa = caixaDe(o.g); });
    trilhos.forEach((o, i) => { o.g.position.set(pts[0].x + 0.6 + i, 0.1, 0); o.caixa = caixaDe(o.g); });
    const tIni = item ? item.t : 0, chegou = [{ t: tIni, p: pts[0] }]; postos.forEach((o, i) => chegou.push({ t: Math.max(o.t + 0.25, chegou[chegou.length - 1].t + 0.3), p: pts[i + 1] }));
    const fim = AC.find((a) => a.acao === 'sair'); chegou.push({ t: Math.max(fim ? fim.t0 + 1.2 : M.duracao, chegou[chegou.length - 1].t + 0.5), p: pts[pts.length - 1] });
    const anda = trilho(chegou);
    const b0 = new T.Box3(new T.Vector3(x0 - 1.4, 0, -0.8), new T.Vector3(fimX + 0.4, 1.6, idxSep >= 0 ? 2.3 : 0.8));
    QUADROS = [{ t: 0, ...enquadrar(b0, 1.1) }];
    const zoom = 1 - (P.aproximacao || 0.3) * 0.5;
    AC.forEach((a) => { const o = a.foco; if (!o || o === item) { QUADROS.push({ t: a.t0, ...enquadrar(b0, 1.1) }); return; } const b = new T.Box3().copy(o.caixa).expandByScalar(1.2 / zoom); QUADROS.push({ t: a.t0, ...enquadrar(b, 1.2) }); });
    return (t) => { if (item) { const p = anda(t); item.g.position.copy(p); item.g.visible = t >= item.t; item.caixa = caixaDe(item.g); }
      OBJ.forEach((o) => { if (o === item) return; const k = liso((t - o.t) / 0.45); o.g.visible = k > 0; o.g.scale.setScalar(Math.max(0.001, 0.85 + 0.15 * k)); const pa = liso((t - o.t) / 0.45); o.g.position.y = (1 - pa) * 0.6;
        const ac = AC[acaoEm(t)], at = ac && ac.foco === o ? 1 : 0; o.mats.forEach((m, i) => { m.emissiveIntensity = at * (i === 1 ? 0.5 + 0.3 * Math.sin(t * 8) : 0.08); });
        const mv = o.acoes.find((a) => a.acao === 'separar' || a.acao === 'abrir'); if (mv && o.movel) { const q = liso((t - mv.t0 - 0.2) / 0.5); o.movel.rotation.y = q * 0.7; } }); };
  }

  // ================= Pixel em Cena: mundo em volumes com textura de pixels e personagem em sprite ======================
  function pixel() {
    apontar(0.34, 0.5);
    const noite = P.noite !== false; cena.add(new T.HemisphereLight(noite ? 0x8fa7d8 : 0xffffff, FUNDO.getHex(), noite ? 0.9 : 1.5));
    const sol = new T.DirectionalLight(noite ? 0xbfd0ff : 0xfff2d8, noite ? 1.3 : 2.2); sol.position.set(-5, 8, 4); sol.castShadow = true; sol.shadow.mapSize.set(512, 512); Object.assign(sol.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 1, far: 30 }); cena.add(sol);
    const R = rng(M.semente + 5);
    const ceu = document.createElement('canvas'); ceu.width = Math.round(W / pxl); ceu.height = Math.round(H / pxl); { const x = ceu.getContext('2d'); x.fillStyle = hexv('--fundo'); x.fillRect(0, 0, ceu.width, ceu.height); if (noite) { x.fillStyle = hexv('--texto'); for (let i = 0; i < ceu.width * ceu.height / 700; i++) x.fillRect(Math.floor(R() * ceu.width), Math.floor(R() * ceu.height), 1, 1); } }
    const tc = new T.CanvasTexture(ceu); tc.magFilter = tc.minFilter = T.NearestFilter; tc.colorSpace = T.SRGBColorSpace; cena.background = tc;
    const textura = (c, s) => { const q = rng(s), n = document.createElement('canvas'); n.width = n.height = 16; const x = n.getContext('2d'); x.fillStyle = '#' + c.getHexString(); x.fillRect(0, 0, 16, 16); for (let i = 0; i < 26; i++) { x.fillStyle = q() < 0.5 ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.09)'; x.fillRect(Math.floor(q() * 8) * 2, Math.floor(q() * 8) * 2, 2, 2); } const tx = new T.CanvasTexture(n); tx.wrapS = tx.wrapT = T.RepeatWrapping; tx.magFilter = tx.minFilter = T.NearestFilter; tx.colorSpace = T.SRGBColorSpace; return tx; };
    const mats = PAL.map((c, i) => new T.MeshLambertMaterial({ map: textura(c, M.semente + i), color: 0xffffff }));
    const pessoa = OBJ.find((o) => o.forma === 'pessoa'), locais = OBJ.filter((o) => o.forma !== 'pessoa' && o.forma !== 'plataforma'), plat = OBJ.find((o) => o.forma === 'plataforma');
    const passo = 2.5, x0 = -Math.max(1, locais.length - 1) * passo / 2;
    locais.forEach((o, i) => { o.pos = new T.Vector3(x0 + i * passo, 0.3, -0.5); });
    const L = Math.max(1, locais.length - 1) * passo + 4.6;
    const chaoM = new T.MeshLambertMaterial({ map: textura(PAL[2].clone().lerp(PAL[4], 0.3), M.semente + 9) }); chaoM.map.repeat.set(L, 3); const chao = malha(new T.BoxGeometry(L, 0.3, 3.2), chaoM, 0, 0.15, 0); cena.add(chao);
    if (plat) { plat.pos = new T.Vector3(0, 0.3, 0.9); plat.g.visible = false; plat.caixa = new T.Box3(new T.Vector3(-1, 0.3, 0.5), new T.Vector3(1, 0.4, 1.3)); }
    locais.forEach((o) => { o.movel = new T.Group(); PEC(o.forma).forEach((p) => { const m = malha(geoDe(p, 8), mats[p[7]], p[1], p[2], p[3]); (p[8] ? o.movel : o.g).add(m); }); o.g.add(o.movel); o.g.position.copy(o.pos); cena.add(o.g); o.caixa = caixaDe(o.g); });
    const luz = new T.PointLight(hexv('--destaque'), 0, 6); cena.add(luz);
    // sprite próprio em 16x24: poses desenhadas aqui, com cores derivadas da paleta
    const POSES = { parado: 0, passo1: 1, passo2: 2, aponta: 3 }, cn = document.createElement('canvas'); cn.width = 64; cn.height = 24; { const x = cn.getContext('2d'), Z = (c, a, b, w, h, o) => { x.fillStyle = c; x.fillRect(a + o * 16, b, w, h); };
      for (let o = 0; o < 4; o++) { const pele = '#E6B48C', cab = '#5A3A2A', roupa = hexv('--destaque'), calca = hexv('--primaria');
        Z(cab, 5, 1, 6, 3, o); Z(pele, 5, 4, 6, 4, o); Z('#222', 6, 5, 1, 1, o); Z('#222', 9, 5, 1, 1, o); Z(roupa, 4, 8, 8, 7, o); Z(pele, 3, 9, 1, 5, o);
        if (o === 3) Z(pele, 12, 7, 3, 2, o); else Z(pele, 12, 9, 1, 5, o);
        const pe = o === 1 ? [4, 9] : o === 2 ? [6, 7] : [5, 8]; Z(calca, pe[0], 15, 3, 7, o); Z(calca, pe[1], 15, 3, 7, o); Z('#222', pe[0], 22, 3, 2, o); Z('#222', pe[1], 22, 3, 2, o); } }
    const sp = new T.CanvasTexture(cn); sp.magFilter = sp.minFilter = T.NearestFilter; sp.colorSpace = T.SRGBColorSpace; sp.repeat.set(0.25, 1);
    const fig = new T.Mesh(new T.PlaneGeometry(1.1, 1.65), new T.MeshBasicMaterial({ map: sp, transparent: true, alphaTest: 0.5, side: T.DoubleSide })); fig.castShadow = true; cena.add(fig);
    const sombra = new T.Mesh(new T.CircleGeometry(0.3, 10), new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.4 })); sombra.rotation.x = -Math.PI / 2; cena.add(sombra);
    const tem = !!pessoa || locais.length > 0, t0 = pessoa ? pessoa.t : (AC[0] ? AC[0].t0 : 0);
    const inicio = new T.Vector3(x0 - 1.6, 0.3, 0.75), ponto = [{ t: t0, p: inicio }]; locais.forEach((o) => { const a = AC.find((q) => q.ids.some((x) => x.o === o)); ponto.push({ t: Math.max(o.t + 0.5, ponto[ponto.length - 1].t + 0.8), p: new T.Vector3(o.pos.x + 0.1, 0.3, 0.75) }); });
    const anda = trilho(ponto);
    if (pessoa) { pessoa.caixa = new T.Box3().setFromCenterAndSize(new T.Vector3(inicio.x, 1.0, inicio.z), new T.Vector3(0.6, 1.3, 0.3)); }
    const b0 = new T.Box3(new T.Vector3(-L / 2, 0, -1.6), new T.Vector3(L / 2, 1.8, 1.6)); QUADROS = [{ t: 0, ...enquadrar(b0, 0.92) }];
    const zoom = P.aproximacao || 0.3;
    AC.forEach((a) => { const o = a.foco; if (!o || o === pessoa || o === plat || !zoom) { QUADROS.push({ t: a.t0, ...enquadrar(b0, 0.92) }); return; } const b = o.caixa.clone().expandByVector(new T.Vector3(1.9 - zoom * 2, 0.5, 1.2)); QUADROS.push({ t: a.t0, ...enquadrar(b, 1.0) }); });
    return (t) => { fig.visible = tem && t >= t0; sombra.visible = fig.visible; const p = anda(t), q = anda(t - 0.08); const movendo = p.distanceTo(q) > 0.004;
      fig.position.set(p.x, p.y + 0.82, p.z); fig.quaternion.copy(cam.quaternion); sombra.position.set(p.x, 0.31, p.z); if (pessoa) pessoa.caixa.setFromCenterAndSize(new T.Vector3(p.x, 1.1, p.z), new T.Vector3(0.7, 1.6, 0.3));
      const ac = AC[acaoEm(t)], gesto = ac && (ac.acao === 'apontar' || ac.acao === 'usar' || ac.acao === 'abrir' || ac.acao === 'observar');
      const quadro = movendo ? 1 + Math.floor(t / (P.passo_sprite_s || 0.16)) % 2 : (gesto ? POSES.aponta : POSES.parado); sp.offset.x = quadro * 0.25; fig.scale.x = q.x > p.x + 0.002 ? -1 : 1;
      locais.forEach((o) => { const k = liso((t - o.t) / 0.4); o.g.visible = k > 0; o.g.scale.setScalar(Math.max(0.001, k * 1.35)); const mv = o.acoes.find((a) => a.acao === 'abrir' || a.acao === 'apontar' || a.acao === 'usar');
        if (mv) { const q2 = liso((t - mv.t0 - 0.25) / 0.7); if (mv.acao === 'abrir') { o.movel.position.y = q2 * 0.5; o.movel.position.z = q2 * 0.4; } else { o.movel.rotation.z = -q2 * 0.65; o.movel.position.y = -q2 * 0.05; } }
        if (ac && ac.foco === o) { luz.position.set(o.pos.x, 1.8, 0.6); luz.intensity = 6 * liso((t - ac.t0) / 0.4); } });
      if (ac && (!ac.foco || !locais.includes(ac.foco))) luz.intensity = 0; };
  }

  // ================= Rota em Foco: relevo, rota e chamadas sobre um mapa =================================================
  function rota() {
    apontar(0.12, 1.02);
    cena.add(new T.HemisphereLight(0xffffff, 0x223344, 1.1));
    const sol = new T.DirectionalLight(0xffffff, 1.8); sol.position.set(-7, 7, 2); cena.add(sol);
    const R = rng(M.semente + 9), N = 256, Lm = 14; const ruido = (x, y) => { const f = (a, b) => { const h = Math.sin((a + M.semente) * 127.1 + b * 311.7) * 43758.5453; return h - Math.floor(h); }, i = Math.floor(x), j = Math.floor(y), u = liso(x - i), v = liso(y - j); return mix(mix(f(i, j), f(i + 1, j), u), mix(f(i, j + 1), f(i + 1, j + 1), u), v); };
    const relevo = (x, z) => { const d = Math.hypot(x / (Lm * 0.42), z / (Lm * 0.36)), n = ruido(x * 0.5 + 7, z * 0.5 + 3) * 0.6 + ruido(x * 1.3, z * 1.3) * 0.3 + ruido(x * 3, z * 3) * 0.1; return n * 1.25 - d * d * 0.9 - 0.12; };
    const cn = document.createElement('canvas'); cn.width = cn.height = 1024; const x = cn.getContext('2d'), im = x.createImageData(1024, 1024), mar = new T.Color(hexv('--fundo')), terra = cor('--superficie'), alto = cor('--suave');
    for (let j = 0; j < 1024; j++) for (let i = 0; i < 1024; i++) { const wx = (i / 1024 - 0.5) * Lm, wz = (j / 1024 - 0.5) * Lm, h = relevo(wx, wz); const nivel = Math.floor(clamp(h, 0, 0.99) * 6) / 6, c = h < -0.05 ? mar.clone() : (h < 0 ? mar.clone().lerp(terra, 0.28) : terra.clone().lerp(alto, nivel * 1.2 + 0.1)); const curva = h > 0.008 && Math.abs((h * 6) % 1) < 0.03, costa = Math.abs(h) < 0.008, o = (j * 1024 + i) * 4, m = costa ? 1.5 : (curva ? 0.8 : 1); c.convertLinearToSRGB(); im.data[o] = Math.min(255, c.r * 255 * m); im.data[o + 1] = Math.min(255, c.g * 255 * m); im.data[o + 2] = Math.min(255, c.b * 255 * m); im.data[o + 3] = 255; }
    x.putImageData(im, 0, 0); if (P.grade !== false) { x.strokeStyle = 'rgba(255,255,255,.08)'; x.lineWidth = 1; for (let i = 0; i <= 16; i++) { x.beginPath(); x.moveTo(i * 64, 0); x.lineTo(i * 64, 1024); x.moveTo(0, i * 64); x.lineTo(1024, i * 64); x.stroke(); } }
    const tx = new T.CanvasTexture(cn); tx.colorSpace = T.SRGBColorSpace; tx.anisotropy = 4;
    const pg = new T.PlaneGeometry(Lm, Lm, N, N); pg.rotateX(-Math.PI / 2); const ap = pg.attributes.position, uv = pg.attributes.uv, rel = P.relevo === undefined ? 0.6 : P.relevo;
    for (let i = 0; i < ap.count; i++) { const wx = ap.getX(i), wz = ap.getZ(i); ap.setY(i, Math.max(0, relevo(wx, wz)) * rel); uv.setXY(i, wx / Lm + 0.5, 0.5 - wz / Lm); }
    tx.wrapS = tx.wrapT = T.ClampToEdgeWrapping; pg.computeVertexNormals(); const chapa = new T.MeshStandardMaterial({ map: tx, roughness: 1 }); cena.add(new T.Mesh(pg, chapa));
    const oceano = new T.Mesh(new T.PlaneGeometry(200, 200), new T.MeshStandardMaterial({ color: mar, roughness: 1 })); oceano.rotation.x = -Math.PI / 2; oceano.position.y = -0.02; cena.add(oceano); cena.background = mar.clone();
    const altura3 = (a, b) => Math.max(0, relevo(a, b)) * rel;
    const lugares = OBJ.filter((o) => o.forma !== 'pessoa' && !M.moveis.includes(o.forma)), viajante = OBJ.find((o) => M.moveis.includes(o.forma));
    const n = Math.max(2, lugares.length); const pts = [];
    lugares.forEach((o, i) => { const a = -2.6 + i * 3.4 / (n - 1); let raio = 3.6 - 2.0 * i / (n - 1), px = 0, pz = 0; for (let q = 0; q < 14; q++) { px = Math.cos(a) * raio * 1.1; pz = -Math.sin(a) * raio * 0.9; if (relevo(px, pz) > 0.04) break; raio *= 0.86; } o.pos = new T.Vector3(px, altura3(px, pz), pz); pts.push(o.pos.clone()); });
    if (viajante && !viajante.pos) { viajante.pos = pts[0] ? pts[0].clone() : new T.Vector3(); }
    const esp = (P.espessura_rota || 1) * 0.055;
    let curva = null, tubo = null; if (pts.length >= 2) { const dens = []; for (let i = 0; i + 1 < pts.length; i++) { const a = pts[i], b = pts[i + 1], dx = b.x - a.x, dz = b.z - a.z; for (let k = 0; k < 6; k++) { const q = k / 6, wig = Math.sin(q * Math.PI) * 0.34 * (i % 2 ? 1 : -1), xx = a.x + dx * q - dz * wig * 0.3, zz = a.z + dz * q + dx * wig * 0.3; dens.push(new T.Vector3(xx, altura3(xx, zz) + 0.05, zz)); } } const u = pts[pts.length - 1]; dens.push(new T.Vector3(u.x, u.y + 0.05, u.z)); curva = new T.CatmullRomCurve3(dens); const tg = new T.TubeGeometry(curva, 240, esp, 8, false); tubo = new T.Mesh(tg, new T.MeshBasicMaterial({ color: PAL[1] })); cena.add(tubo); }
    const marcas = lugares.map((o) => { const g = o.g; const pin = malha(new T.ConeGeometry(0.17, 0.5, 12), new T.MeshBasicMaterial({ color: PAL[1] }), 0, 0.3, 0); pin.rotation.x = Math.PI; g.add(pin); const an = new T.Mesh(new T.RingGeometry(0.22, 0.28, 32), new T.MeshBasicMaterial({ color: PAL[3], side: T.DoubleSide, transparent: true })); an.rotation.x = -Math.PI / 2; an.position.y = 0.03; g.add(an); g.position.copy(o.pos); cena.add(g); o.caixa = new T.Box3().setFromCenterAndSize(o.pos.clone().add(new T.Vector3(0, 0.3, 0)), new T.Vector3(0.5, 0.6, 0.5)); return { o, an, pin }; });
    const ponta = new T.Mesh(new T.SphereGeometry(0.15, 16, 12), new T.MeshBasicMaterial({ color: PAL[3] })); cena.add(ponta);
    if (viajante) { viajante.caixa = new T.Box3().setFromCenterAndSize(viajante.pos.clone(), new T.Vector3(0.4, 0.4, 0.4)); }
    OBJ.forEach((o) => { if (!o.caixa) o.caixa = new T.Box3().setFromCenterAndSize(new T.Vector3(), new T.Vector3(0.4, 0.4, 0.4)); });
    const quando = [{ t: lugares[0] ? lugares[0].t : 0, k: 0 }]; lugares.slice(1).forEach((o, i) => quando.push({ t: Math.max(o.t + 0.2, quando[quando.length - 1].t + 0.4), k: (i + 1) / (lugares.length - 1) }));
    const prog = (t) => { let i = 0; while (i + 1 < quando.length && quando[i + 1].t - 1.1 <= t) i++; const a = quando[i], b = quando[Math.min(i + 1, quando.length - 1)]; return a === b ? a.k : mix(a.k, b.k, liso((t - (b.t - 1.1)) / 1.1)); };
    const b0 = new T.Box3(new T.Vector3(-Lm * 0.42, 0, -Lm * 0.34), new T.Vector3(Lm * 0.42, 0.6, Lm * 0.36)); QUADROS = [{ t: 0, ...enquadrar(b0, 0.94) }];
    const aprox = 1 - (P.aproximacao || 0.3) * 0.5;
    AC.forEach((a) => { const os = a.ids.map((q) => q.o).filter((o) => lugares.includes(o)); if (!os.length) return; const b = caixaDe2(os); const i = lugares.indexOf(os[0]); if (i > 0) b.union(lugares[i - 1].caixa); b.expandByVector(new T.Vector3(2.4 / aprox, 0.5, 2.0 / aprox)); QUADROS.push({ t: a.t0, ...enquadrar(b, 1.1) }); });
    const fic = AC.some((a) => a.ficticio), selo = document.createElement('div'); selo.className = 'rot3 selo'; selo.textContent = fic ? 'Mapa fictício' : 'Esquema ilustrativo, sem escala'; selo.style.transform = `translate(${(S.x + 8).toFixed(0)}px,${(S.y + 8).toFixed(0)}px)`;
    { const w = selo.textContent.length * 30 * esc * 0.62 + 34 * esc, h = 56 * esc, candidatos = [[S.x + 8, S.y + 8], [S.x + S.w - w - 8, S.y + 8], [S.x + 8, S.y + S.h - h - 8], [S.x + S.w - w - 8, S.y + S.h - h - 8]]; const c = candidatos.find(([a, b]) => !G.exclusoes.some((e) => cruza({ x: a, y: b, w, h }, e))) || candidatos[0]; selo.style.transform = `translate(${c[0].toFixed(0)}px,${c[1].toFixed(0)}px)`; G.exclusoes.push({ x: c[0], y: c[1], w, h }); }
    camada.appendChild(selo);
    return (t) => { const k = prog(t); if (tubo) { tubo.visible = t >= quando[0].t; tubo.geometry.setDrawRange(0, Math.floor(tubo.geometry.index.count * k / 6) * 6); const p = curva.getPointAt(k); ponta.position.copy(p); ponta.position.y += 0.06; ponta.visible = tubo.visible; } else ponta.visible = false;
      marcas.forEach((m) => { const q = liso((t - m.o.t) / 0.35); m.o.g.visible = q > 0; m.pin.scale.setScalar(Math.max(0.001, q)); const pulso = ((t - m.o.t) % 1.6) / 1.6; m.an.scale.setScalar(1 + pulso * 1.6); m.an.material.opacity = (1 - pulso) * q; }); };
  }

  // ================= Terreno Vivo: o mesmo lote se transforma, em corte isométrico ========================================
  function terreno() {
    apontar(Math.PI / 4, Math.atan(1 / Math.SQRT2));
    cena.add(new T.AmbientLight(0xffffff, 1.3));
    const sol = new T.DirectionalLight(0xffffff, 2.0); sol.position.set(-4, 9, 3); sol.castShadow = true; sol.shadow.mapSize.set(2048, 2048); Object.assign(sol.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: 1, far: 30 }); sol.shadow.bias = -0.0008; cena.add(sol);
    const degr = (() => { const n = document.createElement('canvas'); n.width = 4; n.height = 1; const x = n.getContext('2d'); ['#777', '#aaa', '#ddd', '#fff'].forEach((c, i) => { x.fillStyle = c; x.fillRect(i, 0, 1, 1); }); const q = new T.CanvasTexture(n); q.minFilter = q.magFilter = T.NearestFilter; return q; })();
    const toon = (c, extra) => new T.MeshToonMaterial(Object.assign({ color: c, gradientMap: degr }, extra || {}));
    const tinta = new T.MeshBasicMaterial({ color: FUNDO.clone().multiplyScalar(0.28), side: T.BackSide });
    const contorno = (m, e) => { const o = new T.Mesh(m.geometry, tinta); o.scale.setScalar(1 + (e || 0.03)); m.add(o); return m; };
    const n = P.tamanho_lote || 8, Lx = n, Lz = n * 0.75, ha = P.altura_corte || 1.4, R = rng(M.semente + 2);
    const hach = (() => { const c = document.createElement('canvas'); c.width = c.height = 64; const x = c.getContext('2d'); const base = PAL[4].clone().lerp(new T.Color('#6b4a2e'), 0.65); x.fillStyle = '#' + base.getHexString(); x.fillRect(0, 0, 64, 64); if (P.hachura !== false) { x.strokeStyle = 'rgba(0,0,0,.28)'; x.lineWidth = 2; for (let i = -64; i < 128; i += 10) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i + 40, 64); x.stroke(); } } x.fillStyle = 'rgba(255,255,255,.14)'; for (let i = 0; i < 30; i++) { x.beginPath(); x.arc(R() * 64, R() * 64, 1.5 + R() * 2, 0, 7); x.fill(); } const q = new T.CanvasTexture(c); q.wrapS = q.wrapT = T.RepeatWrapping; q.repeat.set(4, 1); q.colorSpace = T.SRGBColorSpace; return q; })();
    const solo = contorno(malha(new T.BoxGeometry(Lx, ha, Lz), [toon(0xffffff, { map: hach }), toon(0xffffff, { map: hach }), toon(PAL[2].clone().lerp(new T.Color('#b08a5a'), 0.55)), toon(0xffffff), toon(0xffffff, { map: hach }), toon(0xffffff, { map: hach })], 0, -ha / 2, 0), 0.012); cena.add(solo);
    const estrato = malha(new T.BoxGeometry(Lx + 0.01, ha * 0.34, Lz + 0.01), toon(PAL[4].clone().lerp(new T.Color('#4a3524'), 0.7)), 0, -ha * 0.83, 0); estrato.castShadow = false; cena.add(estrato);
    const canais = OBJ.filter((o) => o.forma === 'canal'), beds = OBJ.filter((o) => o.forma === 'canteiro'), mudas = OBJ.filter((o) => o.forma === 'muda'), outros = OBJ.filter((o) => !['canal', 'canteiro', 'muda', 'plataforma', 'pessoa'].includes(o.forma));
    OBJ.forEach((o) => { if (o.forma === 'plataforma' || o.forma === 'pessoa') o.caixa = new T.Box3(new T.Vector3(-Lx * 0.3, -0.1, Lz * 0.2), new T.Vector3(-Lx * 0.2, 0.1, Lz * 0.3)); });
    const aguaT = (() => { const c = document.createElement('canvas'); c.width = 64; c.height = 16; const x = c.getContext('2d'); x.fillStyle = '#' + PAL[0].getHexString(); x.fillRect(0, 0, 64, 16); x.strokeStyle = 'rgba(255,255,255,.7)'; x.lineWidth = 2; for (let i = 0; i < 64; i += 16) { x.beginPath(); x.moveTo(i, 4); x.quadraticCurveTo(i + 4, 1, i + 8, 4); x.stroke(); x.beginPath(); x.moveTo(i + 8, 11); x.quadraticCurveTo(i + 12, 8, i + 16, 11); x.stroke(); } const q = new T.CanvasTexture(c); q.wrapS = q.wrapT = T.RepeatWrapping; q.repeat.set(4, 1); q.colorSpace = T.SRGBColorSpace; return q; })();
    const ruas = [-Lz * 0.26, Lz * 0.26], fases = [];
    if (canais.length) { const o = canais[0]; o.lista = ruas.map((z) => { const v = malha(new T.BoxGeometry(Lx - 0.4, 0.06, 0.5), toon(FUNDO.clone().lerp(new T.Color('#3a2a1c'), 0.8)), 0, 0.005, z); v.castShadow = false; cena.add(v); const w = malha(new T.BoxGeometry(Lx - 0.5, 0.05, 0.36), new T.MeshBasicMaterial({ map: aguaT }), 0, 0.02, z); w.castShadow = false; w.geometry.translate((Lx - 0.5) / 2, 0, 0); w.position.x = -(Lx - 0.5) / 2; cena.add(w); return { v, w }; }); o.caixa = new T.Box3(new T.Vector3(-Lx / 2, 0, ruas[0] - 0.3), new T.Vector3(Lx / 2, 0.1, ruas[1] + 0.3)); }
    const colunas = 3, leitos = []; beds.forEach((o) => { o.lista = []; for (let i = 0; i < colunas; i++) for (const z of [-Lz * 0.02, Lz * 0.42 - 0.2]) { const b = contorno(malha(new T.BoxGeometry(Lx / 4.2, 0.28, 0.82), toon(PAL[2].clone().lerp(new T.Color('#7a5230'), 0.7)), (i - 1) * Lx / 3.4, 0.14, z - 0.1), 0.03); const tp = malha(new T.BoxGeometry(Lx / 4.2 - 0.14, 0.04, 0.68), toon(new T.Color('#3d2b1c')), 0, 0.15, 0); b.add(tp); cena.add(b); o.lista.push(b); leitos.push(b); } o.caixa = new T.Box3(new T.Vector3(-Lx * 0.46, 0, -Lz * 0.2), new T.Vector3(Lx * 0.46, 0.4, Lz * 0.42)); });
    const planta = (x, z, y) => { const g = new T.Group(); const c = PAL[0].clone().lerp(new T.Color('#4f9d4a'), 0.75); g.add(malha(new T.CylinderGeometry(0.02, 0.03, 0.2, 5), toon(new T.Color('#4a7a3a')), 0, 0.1, 0)); [[0.08, 0.2, 0], [-0.08, 0.22, 0.03], [0, 0.28, -0.05]].forEach(([a, b2, c2]) => g.add(contorno(malha(new T.IcosahedronGeometry(0.1, 0), toon(c), a, b2, c2), 0.06))); g.position.set(x, y, z); cena.add(g); return g; };
    mudas.forEach((o) => { o.lista = []; const fontes = leitos.length ? leitos : [null]; fontes.forEach((b) => { for (let i = 0; i < (b ? 5 : 16); i++) { const x = b ? b.position.x + (i - 2) * Lx / 26 : (R() - 0.5) * Lx * 0.8, z = b ? b.position.z + (i % 2 ? 0.14 : -0.14) : (R() - 0.5) * Lz * 0.7; o.lista.push(planta(x, z, b ? 0.3 : 0.01)); } }); o.caixa = new T.Box3(new T.Vector3(-Lx * 0.3, 0.1, -0.2), new T.Vector3(Lx * 0.3, 0.7, Lz * 0.3)); });
    outros.forEach((o, i) => { o.mats = PAL.map((c) => toon(c)); PEC(o.forma).forEach((p) => o.g.add(contorno(malha(geoDe(p, 10), o.mats[p[7]], p[1], p[2], p[3]), 0.03))); const a = -Lx * 0.32 + (i % 3) * Lx * 0.32, b = i < 3 ? -Lz * 0.34 : Lz * 0.34; o.g.position.set(a, 0, b); cena.add(o.g); o.caixa = caixaDe(o.g); });
    const b0 = new T.Box3(new T.Vector3(-Lx / 2, -ha, -Lz / 2), new T.Vector3(Lx / 2, 1.2, Lz / 2)); QUADROS = [{ t: 0, ...enquadrar(b0, 1.05) }];
    const quando = (o) => { const a = o.acoes[0]; return o.t; };
    return (t) => { aguaT.offset.x = -(t * (P.velocidade_agua || 0.6)) % 1;
      canais.forEach((o) => { const k = liso((t - quando(o)) / 0.5), w = liso((t - quando(o) - 0.3) / 1.1); o.lista.forEach(({ v, w: a }) => { v.visible = k > 0; v.scale.x = Math.max(0.001, k); a.visible = w > 0; a.scale.x = Math.max(0.001, w); }); });
      beds.forEach((o) => { o.lista.forEach((b, i) => { const k = liso((t - quando(o) - i * 0.07) / 0.4); b.visible = k > 0; b.scale.y = Math.max(0.001, k); }); });
      mudas.forEach((o) => { const q = o.lista.length; o.lista.forEach((g, i) => { const k = liso((t - quando(o) - (i / q) * 0.9) / 0.35); g.visible = k > 0; g.scale.setScalar(Math.max(0.001, k * (1 + 0.15 * Math.sin(k * Math.PI)))); }); });
      outros.forEach((o) => { const k = liso((t - quando(o)) / 0.45); o.g.visible = k > 0; o.g.scale.set(1, Math.max(0.001, k), 1); }); };
  }

  atualizar = ({ 'encaixe-vivo': encaixe, 'fluxo-facetado': fluxo, 'pixel-em-cena': pixel, 'rota-em-foco': rota, 'terreno-vivo': terreno })[M.estilo]();
  const desenhar = (t) => { atualizar(t); aplicar(quadroEm(t)); cam.updateMatrixWorld(); desenharRotulos(t); r.render(cena, cam); };
  OBJ.forEach((o) => { if (!o.caixa) o.caixa = caixaDe(o.g); });
  criarRotulos(); desenhar(0);
  let atual = 0;
  const tl = { duration: () => M.duracao, totalDuration: () => M.duracao, paused: () => true, pause: () => tl, play: () => tl,
    time: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)), totalTime: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)),
    seek: (v) => (atual = v, desenhar(v), tl), progress: (v) => (v === undefined ? atual / M.duracao : (atual = v * M.duracao, desenhar(atual), tl)) };
  window.__timelines = window.__timelines || {}; window.__timelines['clipator-corte3d'] = tl;
  const rel = document.getElementById('relogio3d');
  const laco = () => { const v = parseFloat(getComputedStyle(rel).getPropertyValue('--t3')); if (!isNaN(v)) desenhar(v); requestAnimationFrame(laco); };
  requestAnimationFrame(laco);
})();
