// Modo curta das cinco direções guiadas pela fala (Clipator, AGPL). Cada frase é um PLANO: um cenário montado no material
// do estilo, personagens com uma ação, um efeito de situação, câmera com plano e movimento, e transição entre planos.
// Cada quadro é função do tempo (sem relógio, sorteio solto ou estado entre quadros): buscar fora de ordem dá o mesmo
// quadro. A câmera enquadra no retângulo que o layout deu à arte (M.geo), como no motor de um mundo só.
(function () {
  const M = window.CURTA; if (!M || !window.THREE || !M.planos || !M.planos.length) return;
  const T = THREE, cv = document.getElementById('arte3d'), P = M.par || {}, E = M.estilo;
  const PIX = E === 'pixel-em-cena', ISO = E === 'terreno-vivo', MAPA = E === 'rota-em-foco', FAC = E === 'fluxo-facetado', BLOCO = E === 'encaixe-vivo';
  let r;
  try { r = new T.WebGLRenderer({ canvas: cv, antialias: !PIX, preserveDrawingBuffer: true }); } catch (e) { return; }
  if (!r.getContext()) return;
  document.body.classList.add('tres-d');
  const W = cv.clientWidth, H = cv.clientHeight;
  const pxl = PIX ? Math.max(2, (P.tamanho_pixel || 4) * W / 1080) : 1;
  r.setPixelRatio(1); r.setSize(Math.round(W / pxl), Math.round(H / pxl), false);
  if (PIX) cv.style.imageRendering = 'pixelated';
  r.shadowMap.enabled = true; r.shadowMap.type = PIX ? T.BasicShadowMap : T.PCFSoftShadowMap; r.outputColorSpace = T.SRGBColorSpace;
  const css = getComputedStyle(document.documentElement), hexv = (n) => css.getPropertyValue(n).trim() || '#888888', cor = (n) => new T.Color(hexv(n));
  const PAL = { pri: cor('--primaria'), des: cor('--destaque'), sup: cor('--superficie'), txt: cor('--texto'), fun: cor('--fundo') };
  const cena = new T.Scene();
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), liso = (k) => { k = clamp(k); return k * k * (3 - 2 * k); }, mix = (a, b, k) => a + (b - a) * k;
  const rng = (s) => () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  const G = M.geo || { layout: 'em-cima', exclusoes: [], foco: { x: W * 0.05, y: H * 0.08, w: W * 0.9, h: H * 0.84 }, seguro: { x: W * 0.04, y: H * 0.04, w: W * 0.92, h: H * 0.92 } };
  const esc = M.geo ? Math.min(M.geo.largura, M.geo.altura) / 1080 : W / 1080, F = G.foco, S = G.seguro;
  const FX = F.x + F.w / 2, FY = F.y + F.h / 2;
  const SEG = FAC ? Math.max(3, Math.round(P.facetas || 6)) : (PIX ? 8 : 20);
  const aprox = 1 - ((P.aproximacao === undefined ? 0.3 : P.aproximacao) - 0.3) * 0.8;
  const amort = P.amortecimento === undefined ? 0.5 : P.amortecimento;
  const agua_v = P.velocidade_agua === undefined ? 0.6 : P.velocidade_agua;

  // ---- cores: o tom natural de cada coisa puxado para a paleta do estilo ----------------------------------------------
  const NAT = { grama: '#6FAF4E', folha: '#3F8F45', pinho: '#2F6E3E', tronco: '#7A5232', areia: '#E9D49B', agua: '#3E8FCB', ceu: '#A5D8F3', concreto: '#A3A4A8',
    asfalto: '#46484F', madeira: '#A0703F', parede: '#EDE4D3', piso: '#C9B79C', pedra: '#8E8B86', neve: '#F3F6FA', metal: '#B8BEC6', vermelho: '#D9534F',
    amarelo: '#F2C14E', branco: '#F7F7F2', preto: '#2A2A2E', ouro: '#E8B931', terra: '#8A5A36', tela: '#7FD6F5', verde: '#2E7D4F', rosa: '#E86A92', azul: '#3D6FD1' };
  const tom = (n, puxa) => (NAT[n] ? new T.Color(NAT[n]) : PAL[n].clone()).lerp(PAL.sup, puxa === undefined ? 0.16 : puxa);
  const PELES = ['#E6B48C', '#C68A5E', '#8D5A3B', '#F1C9A5'], CABELOS = ['#3B2A20', '#1E1A18', '#7A4B2A', '#C9A15A'];

  // ---- materiais: aqui mora a identidade de cada estilo --------------------------------------------------------------
  const degr = (() => { const n = document.createElement('canvas'); n.width = 4; n.height = 1; const x = n.getContext('2d'); ['#777', '#aaa', '#ddd', '#fff'].forEach((c, i) => { x.fillStyle = c; x.fillRect(i, 0, 1, 1); }); const q = new T.CanvasTexture(n); q.minFilter = q.magFilter = T.NearestFilter; return q; })();
  const texPix = (c, s) => { const q = rng(s), n = document.createElement('canvas'); n.width = n.height = 16; const x = n.getContext('2d'); x.fillStyle = '#' + c.getHexString(); x.fillRect(0, 0, 16, 16); for (let i = 0; i < 26; i++) { x.fillStyle = q() < 0.5 ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.1)'; x.fillRect(Math.floor(q() * 8) * 2, Math.floor(q() * 8) * 2, 2, 2); } const tx = new T.CanvasTexture(n); tx.wrapS = tx.wrapT = T.RepeatWrapping; tx.magFilter = tx.minFilter = T.NearestFilter; tx.colorSpace = T.SRGBColorSpace; return tx; };
  const MAT = {};
  const mat = (c) => { const k = c.getHexString(); if (MAT[k]) return MAT[k]; let m;
    if (PIX) m = new T.MeshLambertMaterial({ map: texPix(c, parseInt(k, 16) % 9973), color: 0xffffff });
    else if (FAC) m = new T.MeshStandardMaterial({ color: c, roughness: 0.92, flatShading: true });
    else if (BLOCO) m = new T.MeshStandardMaterial({ color: c, roughness: 0.3 });
    else if (ISO) m = new T.MeshToonMaterial({ color: c, gradientMap: degr });
    else m = new T.MeshStandardMaterial({ color: c, roughness: 1 });
    return (MAT[k] = m); };
  const brilho = (c) => new T.MeshBasicMaterial({ color: c });
  const malha = (geo, m, x, y, z) => { const o = new T.Mesh(geo, m); o.position.set(x || 0, y || 0, z || 0); o.castShadow = true; o.receiveShadow = true; return o; };
  const U = (P.tamanho_bloco || 0.2), pinoG = new T.CylinderGeometry(U * 0.3, U * 0.3, U * 0.2, 12);
  const pinos = (m, w, h, d, c) => { const nx = Math.floor(w / U), nz = Math.floor(d / U); if (!nx || !nz || nx * nz > 24) return; for (let a = 0; a < nx; a++) for (let b = 0; b < nz; b++) m.add(malha(pinoG, mat(c), (a + 0.5) * w / nx - w / 2, h / 2 + U * 0.08, (b + 0.5) * d / nz - d / 2)); };
  const caixa = (g, w, h, d, x, y, z, c, ry) => { const m = malha(new T.BoxGeometry(w, h, d), mat(c), x, y + h / 2, z); if (ry) m.rotation.y = ry; if (BLOCO) pinos(m, w, h, d, c); g.add(m); return m; };
  const cil = (g, r1, r2, h, x, y, z, c, seg) => { const m = malha(new T.CylinderGeometry(r1, r2, h, seg || SEG), mat(c), x, y + h / 2, z); g.add(m); return m; };
  const bola = (g, rr, x, y, z, c, sy) => { const m = malha(new T.SphereGeometry(rr, SEG, Math.max(4, Math.round(SEG * 0.7))), mat(c), x, y, z); if (sy) m.scale.y = sy; g.add(m); return m; };
  const luzinha = (g, w, h, d, x, y, z, c) => { const m = new T.Mesh(new T.BoxGeometry(w, h, d), brilho(c)); m.position.set(x, y, z); g.add(m); return m; };
  const arvore = (g, x, z, s, tipo) => { s = s || 1; cil(g, 0.08 * s, 0.11 * s, 0.7 * s, x, 0, z, tom('tronco')); if (tipo === 'pinho') { cone(g, 0.55 * s, 1.0 * s, x, 0.55 * s, z, tom('pinho')); cone(g, 0.42 * s, 0.8 * s, x, 1.05 * s, z, tom('pinho')); } else bola(g, 0.55 * s, x, 1.05 * s, z, tom('folha'), 0.9); };
  const cone = (g, rr, h, x, y, z, c, seg) => { const m = malha(new T.ConeGeometry(rr, h, seg || SEG), mat(c), x, y + h / 2, z); g.add(m); return m; };
  const textura = (desenho, w, h, rep) => { const n = document.createElement('canvas'); n.width = w; n.height = h; desenho(n.getContext('2d')); const q = new T.CanvasTexture(n); q.wrapS = q.wrapT = T.RepeatWrapping; if (rep) q.repeat.set(rep[0], rep[1]); if (PIX) q.magFilter = q.minFilter = T.NearestFilter; q.colorSpace = T.SRGBColorSpace; return q; };
  const AGUAS = [];
  const agua = (g, w, d, x, y, z, c) => { const tx = textura((x2) => { x2.fillStyle = '#' + c.getHexString(); x2.fillRect(0, 0, 64, 32); x2.strokeStyle = 'rgba(255,255,255,.55)'; x2.lineWidth = 2; for (let i = 0; i < 64; i += 16) { x2.beginPath(); x2.moveTo(i, 8); x2.quadraticCurveTo(i + 4, 4, i + 8, 8); x2.stroke(); x2.beginPath(); x2.moveTo(i + 8, 24); x2.quadraticCurveTo(i + 12, 20, i + 16, 24); x2.stroke(); } }, 64, 32, [w / 2, d / 2]); AGUAS.push(tx);
    const m = new T.Mesh(new T.PlaneGeometry(w, d), new T.MeshStandardMaterial({ map: tx, roughness: 0.4 })); m.rotation.x = -Math.PI / 2; m.position.set(x, y, z); m.receiveShadow = true; g.add(m); return m; };

  // ---- chão: diorama no vazio (Terreno Vivo, Rota em Foco) ou chão até o horizonte (as outras três) ------------------
  const LX = ISO ? Math.max(6, P.tamanho_lote || 8) * 1.25 : 10, LZ = ISO ? LX * 0.62 : 6.4;
  const hc = ISO ? (P.altura_corte || 1.4) * 0.8 : 0.6;
  const chao = (g, c, R) => {
    if (ISO) { const camadas = [tom('terra', 0.3), tom('terra', 0.1).multiplyScalar(0.8), tom('pedra', 0.2)]; let y = 0; camadas.forEach((cc, i) => { const h = hc * [0.35, 0.35, 0.3][i]; y -= h; const m = malha(new T.BoxGeometry(LX, h, LZ), mat(cc), 0, y + h / 2, 0); g.add(m);
        if (P.hachura !== false) for (let k = 0; k < 7; k++) { const l = luzinha(g, LX * 1.002, 0.012, 0.012, 0, y + h * (k + 0.5) / 7, LZ / 2 + 0.005, cc.clone().multiplyScalar(0.75)); l.material = brilho(cc.clone().multiplyScalar(0.75)); } }); }
    const tam = (ISO || MAPA) ? [LX, LZ] : [80, 80];
    let m;
    if (MAPA) { const N = 64, pg = new T.PlaneGeometry(LX + 2, LZ + 2, N, N); pg.rotateX(-Math.PI / 2); const ap = pg.attributes.position, rel = P.relevo === undefined ? 0.6 : P.relevo;
      for (let i = 0; i < ap.count; i++) { const x = ap.getX(i), z = ap.getZ(i), borda = Math.max(Math.abs(x) / (LX / 2 + 1), Math.abs(z) / (LZ / 2 + 1)); const fora = clamp((borda - 0.72) / 0.28); ap.setY(i, (Math.sin(x * 1.3 + R() * 0.01) * Math.cos(z * 1.7) * 0.5 + 0.5) * rel * 0.5 * fora - fora * 0.3); }
      pg.computeVertexNormals();
      const tx = textura((x) => { x.fillStyle = '#' + c.getHexString(); x.fillRect(0, 0, 256, 256); for (let i = 0; i < 900; i++) { x.fillStyle = `rgba(0,0,0,${0.02 + (i % 5) * 0.008})`; x.fillRect((i * 97) % 256, (i * 57) % 256, 2, 2); } if (P.grade !== false) { x.strokeStyle = 'rgba(255,255,255,.18)'; x.lineWidth = 1; for (let i = 0; i <= 8; i++) { x.beginPath(); x.moveTo(i * 32, 0); x.lineTo(i * 32, 256); x.moveTo(0, i * 32); x.lineTo(256, i * 32); x.stroke(); } } }, 256, 256, [2, 1.3]);
      m = new T.Mesh(pg, new T.MeshStandardMaterial({ map: tx, roughness: 1 })); }
    else { m = new T.Mesh(new T.BoxGeometry(tam[0], 0.04, tam[1]), mat(c)); m.position.y = -0.02; }
    m.receiveShadow = true; g.add(m); return m; };
  const parede = (g, c, alt) => { alt = alt || 3.2; caixa(g, LX, alt, 0.2, 0, 0, -LZ / 2 + 0.1, c); caixa(g, 0.2, alt, LZ * 0.7, -LX / 2 + 0.1, 0, -LZ * 0.15, c.clone().multiplyScalar(0.92)); caixa(g, LX, 0.14, 0.24, 0, 0, -LZ / 2 + 0.2, c.clone().multiplyScalar(0.7)); };
  const janela = (g, x, y, z, w, h, noite) => { caixa(g, w + 0.16, h + 0.16, 0.06, x, y - 0.08, z, tom('branco')); luzinha(g, w, h, 0.04, x, y + h / 2, z + 0.04, noite ? new T.Color('#1E2A55') : tom('ceu', 0.05)); caixa(g, 0.05, h, 0.03, x, y, z + 0.06, tom('branco')); };
  const quadro = (g, x, y, z, w, h, c) => { caixa(g, w + 0.1, h + 0.1, 0.05, x, y - 0.05, z, tom('madeira')); luzinha(g, w, h, 0.03, x, y + h / 2, z + 0.03, c); };
  const cadeira = (g, x, z, c, ry) => { const q = new T.Group(); caixa(q, 0.45, 0.06, 0.45, 0, 0.42, 0, c); caixa(q, 0.45, 0.5, 0.06, 0, 0.48, -0.2, c); [[-0.19, -0.19], [0.19, -0.19], [-0.19, 0.19], [0.19, 0.19]].forEach(([a, b]) => caixa(q, 0.05, 0.42, 0.05, a, 0, b, c)); q.position.set(x, 0, z); q.rotation.y = ry || 0; g.add(q); return q; };
  const mesa = (g, x, z, w, d, c) => { caixa(g, w, 0.07, d, x, 0.72, z, c); [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(([a, b]) => caixa(g, 0.07, 0.72, 0.07, x + a * (w / 2 - 0.08), 0, z + b * (d / 2 - 0.08), c.clone().multiplyScalar(0.8))); };
  const predio = (g, x, z, w, h, d, c, noite, R) => { caixa(g, w, h, d, x, 0, z, c); for (let yy = 0.5; yy < h - 0.3; yy += 0.6) for (let xx = -w / 2 + 0.3; xx < w / 2 - 0.15; xx += 0.42) { const acesa = noite ? R() < 0.55 : false; luzinha(g, 0.22, 0.3, 0.02, x + xx + 0.05, yy + 0.15, z + d / 2 + 0.011, acesa ? tom('amarelo', 0) : (noite ? new T.Color('#24304F') : tom('tela', 0.4))); } };
  const pessoaPequena = (g, x, z, c, R) => { cil(g, 0.13, 0.15, 0.4, x, 0, z, c); bola(g, 0.11, x, 0.53, z, new T.Color(PELES[Math.floor(R() * 4)])); };

  // ---- os cenários: cada um devolve onde ficam as pessoas, os objetos e o centro de interesse --------------------------
  const INTERNOS = new Set(['casa', 'cozinha', 'quarto', 'escritorio', 'escola', 'loja', 'restaurante', 'hospital', 'fabrica', 'laboratorio', 'palco']);
  const CEN = {
    cidade(g, a, R) { chao(g, a.chao || tom('concreto'), R); caixa(g, LX * 1.6, 0.03, 1.8, 0, 0, 0.9, tom('asfalto')); for (let x = -LX * 0.7; x < LX * 0.7; x += 1.1) caixa(g, 0.5, 0.035, 0.08, x, 0, 0.9, tom('branco'));
      const cs = [tom('parede'), PAL.pri.clone().lerp(tom('branco'), 0.4), tom('concreto'), PAL.des.clone().lerp(tom('branco'), 0.5), tom('pedra')]; for (let i = 0; i < 6; i++) { const w = 1.3 + R() * 0.6, h = 2.2 + R() * 2.8; predio(g, -LX / 2 + 0.8 + i * (LX / 5.6), -2.2 - R() * 0.4, w, h, 1.2, a.acento && i % 3 === 1 ? a.acento : cs[i % 5], a.noite, R); }
      [-3.2, 0.4, 3.6].forEach((x) => { cil(g, 0.04, 0.05, 2.2, x, 0, 2.05, tom('metal')); const l = bola(g, 0.12, x, 2.25, 2.05, tom('amarelo', 0)); if (a.noite) l.material = brilho(tom('amarelo', 0)); });
      return { gente: [[-0.6, 2.3], [0.7, 2.3], [-1.8, 2.4]], obj: [[1.8, 2.2], [2.6, 2.4], [-2.8, 2.3]], centro: [0, 1.4, -0.4] }; },
    casa(g, a, R) { chao(g, a.chao || tom('madeira'), R); parede(g, a.parede || PAL.sup.clone().lerp(tom('parede'), 0.6)); janela(g, 1.8, 1.0, -LZ / 2 + 0.22, 1.4, 1.2, a.noite); quadro(g, -1.6, 1.4, -LZ / 2 + 0.22, 1.0, 0.7, PAL.des);
      const s = PAL.pri.clone().lerp(tom('branco'), 0.15); caixa(g, 2.4, 0.45, 0.9, -1.6, 0, -1.9, s); caixa(g, 2.4, 0.6, 0.25, -1.6, 0.4, -2.3, s); caixa(g, 0.25, 0.65, 0.9, -2.85, 0, -1.9, s); caixa(g, 0.25, 0.65, 0.9, -0.35, 0, -1.9, s);
      caixa(g, 2.6, 0.02, 1.8, 0, 0, 0.3, PAL.des.clone().lerp(tom('branco'), 0.5)); cil(g, 0.04, 0.04, 1.5, 3.4, 0, -2.0, tom('metal')); cone(g, 0.3, 0.35, 3.4, 1.45, -2.0, tom('amarelo'), 12); cil(g, 0.22, 0.17, 0.4, -3.9, 0, -2.2, tom('terra')); bola(g, 0.35, -3.9, 0.7, -2.2, tom('folha'));
      return { gente: [[0, 0.6], [1.2, 0.5], [-1.1, 0.7]], obj: [[1.9, 0.4], [-2.2, 0.6], [2.7, 0.9]], centro: [0, 1.2, -1.2] }; },
    cozinha(g, a, R) { chao(g, a.chao || tom('piso'), R); parede(g, a.parede || tom('parede')); const mv = PAL.pri.clone().lerp(tom('branco'), 0.3);
      caixa(g, 5.5, 0.9, 0.8, -0.8, 0, -2.6, mv); caixa(g, 5.6, 0.06, 0.86, -0.8, 0.9, -2.6, tom('pedra')); caixa(g, 1.0, 0.9, 0.8, 1.2, 0, -2.6, tom('metal')); [[-0.22, -0.18], [0.22, -0.18], [-0.22, 0.18], [0.22, 0.18]].forEach(([x, z]) => cil(g, 0.12, 0.12, 0.03, 1.2 + x, 0.96, -2.6 + z, tom('preto')));
      cil(g, 0.2, 0.2, 0.22, 1.0, 0.99, -2.5, PAL.des); caixa(g, 1.0, 2.2, 0.85, 3.3, 0, -2.5, tom('branco')); caixa(g, 0.05, 0.5, 0.05, 2.9, 1.2, -2.05, tom('metal'));
      for (let i = 0; i < 4; i++) caixa(g, 1.2, 0.7, 0.4, -3.0 + i * 1.3, 1.9, -2.8, mv); mesa(g, 0, 0.2, 1.6, 1.0, tom('madeira')); cadeira(g, -1.2, 0.3, tom('madeira'), Math.PI / 2);
      return { gente: [[-0.4, -1.4], [1.0, 1.3], [-1.6, 1.2]], obj: [[0, 0.2, 0.79], [0.5, 0.1, 0.79], [-0.5, 0.3, 0.79]], centro: [0, 1.1, -1.4] }; },
    quarto(g, a, R) { chao(g, a.chao || tom('madeira'), R); parede(g, a.parede || PAL.sup.clone().lerp(tom('rosa'), 0.15)); janela(g, -2.2, 1.1, -LZ / 2 + 0.22, 1.2, 1.1, a.noite || true);
      caixa(g, 2.0, 0.45, 2.6, 0.8, 0, -1.6, tom('madeira')); caixa(g, 1.9, 0.25, 2.5, 0.8, 0.45, -1.6, tom('branco')); caixa(g, 2.0, 0.08, 1.6, 0.8, 0.7, -1.1, PAL.des); caixa(g, 0.9, 0.18, 0.4, 0.8, 0.72, -2.6, tom('branco')); caixa(g, 2.0, 1.1, 0.12, 0.8, 0, -2.95, tom('madeira'));
      caixa(g, 0.6, 0.6, 0.5, 2.4, 0, -2.6, tom('madeira')); cil(g, 0.04, 0.04, 0.4, 2.4, 0.6, -2.6, tom('metal')); const ab = cone(g, 0.2, 0.25, 2.4, 0.95, -2.6, tom('amarelo'), 12); ab.material = brilho(tom('amarelo', 0)); caixa(g, 2.2, 0.02, 1.4, -1.2, 0, 0.4, PAL.pri.clone().lerp(tom('branco'), 0.4));
      return { gente: [[-0.9, 0.5], [0.4, 0.9], [-2.0, 0.8]], obj: [[2.4, -1.2], [-2.2, 0.3], [1.6, 0.8]], centro: [0, 1.0, -1.4], cama: [0.8, 0.75, -1.5] }; },
    escritorio(g, a, R) { chao(g, a.chao || tom('concreto', 0.3), R); parede(g, a.parede || tom('parede')); caixa(g, 2.6, 1.3, 0.05, -1.5, 1.0, -LZ / 2 + 0.22, tom('branco')); for (let i = 0; i < 4; i++) caixa(g, 0.4 + R() * 1.4, 0.04, 0.02, -2.2 + R() * 0.6, 1.3 + i * 0.25, -LZ / 2 + 0.26, i % 2 ? PAL.pri : PAL.des);
      [[-1.8, -1.3], [1.6, -1.3]].forEach(([x, z]) => { mesa(g, x, z, 1.8, 0.9, tom('branco', 0.3)); caixa(g, 0.8, 0.5, 0.05, x, 0.86, z - 0.25, tom('preto')); luzinha(g, 0.72, 0.42, 0.01, x, 1.11, z - 0.22, tom('tela', 0.2)); cadeira(g, x, z + 0.75, tom('preto', 0.3), Math.PI); });
      janela(g, 2.6, 1.0, -LZ / 2 + 0.22, 1.8, 1.4, a.noite); cil(g, 0.25, 0.2, 0.5, 3.9, 0, -0.5, tom('terra')); bola(g, 0.45, 3.9, 0.9, -0.5, tom('folha'));
      return { gente: [[0, 0.6], [1.1, 0.8], [-1.2, 0.8]], obj: [[-1.4, -1.2, 0.79], [1.9, -1.2, 0.79], [0, 1.6]], centro: [0, 1.1, -1.2] }; },
    escola(g, a, R) { chao(g, a.chao || tom('madeira', 0.3), R); parede(g, a.parede || PAL.sup.clone().lerp(tom('parede'), 0.5)); caixa(g, 4.4, 1.6, 0.08, -0.4, 0.9, -LZ / 2 + 0.24, tom('madeira')); luzinha(g, 4.2, 1.4, 0.02, -0.4, 1.7, -LZ / 2 + 0.29, new T.Color('#2F4F3A'));
      for (let i = 0; i < 5; i++) luzinha(g, 0.5 + R() * 1.6, 0.03, 0.01, -2.0 + R() * 1.5, 1.3 + i * 0.22, -LZ / 2 + 0.31, tom('branco', 0)); cil(g, 0.25, 0.25, 0.05, 2.7, 2.2, -LZ / 2 + 0.24, tom('branco')).rotation.x = Math.PI / 2;
      mesa(g, 2.5, -1.9, 1.5, 0.7, tom('madeira')); for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) { mesa(g, -2.2 + i * 1.8, 0.2 + j * 1.3, 0.9, 0.55, tom('madeira', 0.3)); cadeira(g, -2.2 + i * 1.8, 0.65 + j * 1.3, PAL.pri, Math.PI); }
      return { gente: [[1.5, -1.3], [-1.3, -1.0], [0.4, -1.0]], obj: [[2.5, -1.9, 0.79], [-0.4, -2.3, 1.0], [2.0, -1.8, 0.79]], centro: [0, 1.2, -1.2] }; },
    loja(g, a, R) { chao(g, a.chao || tom('piso', 0.3), R); parede(g, a.parede || tom('parede')); const cs = [PAL.pri, PAL.des, tom('vermelho'), tom('verde'), tom('amarelo'), tom('azul')];
      [-2.8, -0.6].forEach((x) => { caixa(g, 2.0, 2.4, 0.6, x, 0, -2.7, tom('madeira')); for (let p = 0; p < 4; p++) for (let k = 0; k < 5; k++) caixa(g, 0.28, 0.32, 0.3, x - 0.8 + k * 0.4, 0.2 + p * 0.56, -2.4, cs[(p * 5 + k + Math.floor(R() * 3)) % 6]); });
      caixa(g, 2.2, 1.0, 0.8, 2.4, 0, -1.0, PAL.pri.clone().lerp(tom('branco'), 0.3)); caixa(g, 0.5, 0.3, 0.4, 2.8, 1.0, -1.0, tom('preto')); caixa(g, 3.0, 0.5, 0.08, 1.5, 2.4, -LZ / 2 + 0.24, PAL.des);
      return { gente: [[0.6, 0.4], [2.4, -0.2], [-1.0, 0.8]], obj: [[2.0, -1.0, 1.0], [-0.6, 0.6], [1.0, 1.0]], centro: [0, 1.1, -1.3] }; },
    restaurante(g, a, R) { chao(g, a.chao || tom('madeira'), R); parede(g, a.parede || PAL.des.clone().lerp(tom('parede'), 0.7)); [[-2.6, -1.4], [0, -0.6], [2.6, -1.4]].forEach(([x, z]) => { cil(g, 0.6, 0.6, 0.05, x, 0.72, z, tom('branco')); cil(g, 0.06, 0.08, 0.72, x, 0, z, tom('metal')); cadeira(g, x - 0.85, z, tom('madeira'), Math.PI / 2); cadeira(g, x + 0.85, z, tom('madeira'), -Math.PI / 2); cil(g, 0.02, 0.02, 0.8, x, 2.5, z, tom('preto')); const l = cone(g, 0.25, 0.2, x, 2.4, z, tom('amarelo'), 12); if (a.noite) l.material = brilho(tom('amarelo', 0)); });
      caixa(g, 3.0, 1.0, 0.6, 1.5, 0, -2.6, tom('madeira')); quadro(g, -2.0, 1.4, -LZ / 2 + 0.22, 1.4, 0.9, PAL.pri);
      return { gente: [[-0.9, 0.6], [0.9, 0.6], [-2.0, 0.8]], obj: [[0, -0.6, 0.77], [-2.6, -1.4, 0.77], [2.6, -1.4, 0.77]], centro: [0, 1.0, -1.0] }; },
    hospital(g, a, R) { chao(g, a.chao || tom('branco', 0.3), R); parede(g, a.parede || tom('tela', 0.65)); caixa(g, 0.8, 0.24, 0.24, -2.4, 1.9, -LZ / 2 + 0.24, tom('vermelho')); caixa(g, 0.24, 0.8, 0.24, -2.4, 1.62, -LZ / 2 + 0.24, tom('vermelho'));
      caixa(g, 1.1, 0.6, 2.4, 0.4, 0, -1.6, tom('metal')); caixa(g, 1.0, 0.2, 2.3, 0.4, 0.6, -1.6, tom('branco')); caixa(g, 0.6, 0.12, 0.4, 0.4, 0.8, -2.55, tom('branco')); cil(g, 0.03, 0.03, 1.6, 2.2, 0, -2.2, tom('metal')); caixa(g, 0.6, 0.45, 0.1, 2.2, 1.6, -2.2, tom('preto')); luzinha(g, 0.5, 0.02, 0.01, 2.2, 1.82, -2.14, tom('verde', 0));
      for (let i = 0; i < 6; i++) cil(g, 0.12, 0.12, 2.2, 3.4 + (i % 2) * 0.1, 0, -2.3 + i * 0.3, tom('tela', 0.5));
      return { gente: [[-1.4, -0.4], [1.6, 0.2], [-0.4, 0.7]], obj: [[2.2, -1.6], [-1.6, 0.5], [0.8, 0.8]], centro: [0, 1.0, -1.2], cama: [0.4, 0.85, -1.6] }; },
    fabrica(g, a, R) { chao(g, a.chao || tom('concreto'), R); parede(g, a.parede || tom('pedra', 0.4), 3.6); caixa(g, 7.0, 0.7, 0.9, -0.5, 0, -1.6, tom('preto', 0.3)); a.esteira = []; for (let i = 0; i < 6; i++) a.esteira.push(caixa(g, 0.5, 0.4, 0.5, -3.5 + i * 1.2, 0.72, -1.6, tom('madeira')));
      caixa(g, 1.4, 1.8, 1.2, 3.6, 0, -1.8, PAL.pri); cil(g, 0.4, 0.4, 0.3, 3.6, 1.0, -1.15, tom('metal')).rotation.x = Math.PI / 2; for (let i = 0; i < 8; i++) caixa(g, 0.4, 0.06, 0.06, -3.8 + i * 0.5, 0, 0.6, i % 2 ? tom('amarelo', 0) : tom('preto'));
      a.engrenagem = cil(g, 0.5, 0.5, 0.12, -3.6, 1.6, -LZ / 2 + 0.3, tom('metal'), FAC ? 8 : 12); a.engrenagem.rotation.x = Math.PI / 2;
      return { gente: [[0, -0.6], [1.6, -0.4], [-1.6, -0.5]], obj: [[1.0, 0.8], [-2.4, 0.8], [2.6, 0.6]], centro: [0, 1.1, -1.3] }; },
    laboratorio(g, a, R) { chao(g, a.chao || tom('branco', 0.3), R); parede(g, a.parede || tom('tela', 0.7)); caixa(g, 6.0, 0.9, 0.9, -0.6, 0, -2.5, tom('branco')); caixa(g, 6.1, 0.06, 0.95, -0.6, 0.9, -2.5, tom('preto', 0.3));
      a.frascos = []; [PAL.des, tom('verde', 0), tom('azul', 0), tom('rosa', 0)].forEach((c, i) => { const x = -2.8 + i * 0.7; const v = cil(g, 0.13, 0.18, 0.35, x, 0.96, -2.5, c); v.material = brilho(c); a.frascos.push(v); cil(g, 0.05, 0.05, 0.15, x, 1.31, -2.5, tom('branco')); });
      caixa(g, 0.4, 0.08, 0.35, 1.2, 0.96, -2.5, tom('preto')); cil(g, 0.05, 0.05, 0.5, 1.2, 1.04, -2.6, tom('preto')); cil(g, 0.07, 0.06, 0.4, 1.2, 1.4, -2.45, tom('metal')).rotation.x = 0.4;
      for (let p = 0; p < 3; p++) for (let k = 0; k < 6; k++) cil(g, 0.1, 0.1, 0.25, 2.2 + k * 0.28, 1.4 + p * 0.45, -LZ / 2 + 0.3, [PAL.pri, PAL.des, tom('verde')][(p + k) % 3]);
      return { gente: [[-0.6, -1.4], [0.8, -1.0], [-1.8, -0.8]], obj: [[1.2, -2.4, 0.96], [-1.0, -2.4, 0.96], [0.2, -2.4, 0.96]], centro: [0, 1.1, -1.6] }; },
    parque(g, a, R) { chao(g, a.chao || tom('grama'), R); caixa(g, LX * 2, 0.03, 1.1, 0, 0, 0.6, tom('areia')); [[-3.6, -1.6], [-1.6, -2.6], [2.0, -2.2], [3.8, -1.2], [0.3, -3.4]].forEach(([x, z]) => arvore(g, x, z, 0.9 + R() * 0.6));
      caixa(g, 1.6, 0.08, 0.5, -0.9, 0.42, -0.6, tom('madeira')); caixa(g, 1.6, 0.4, 0.06, -0.9, 0.5, -0.85, tom('madeira')); caixa(g, 0.08, 0.42, 0.4, -1.6, 0, -0.6, tom('preto')); caixa(g, 0.08, 0.42, 0.4, -0.2, 0, -0.6, tom('preto'));
      for (let i = 0; i < 14; i++) bola(g, 0.07, -4 + R() * 8, 0.08, 1.4 + R() * 1.2, [tom('rosa', 0), tom('amarelo', 0), tom('vermelho', 0), PAL.des][i % 4]);
      return { gente: [[0.4, 0.6], [1.5, 0.7], [-0.9, -0.5]], obj: [[2.2, 0.7], [-2.4, 0.9], [3.2, 1.4]], centro: [0, 1.2, -0.8], banco: [-0.9, 0.46, -0.6] }; },
    floresta(g, a, R) { chao(g, a.chao || tom('folha', 0.25), R); caixa(g, 1.2, 0.03, LZ * 3, 0.3, 0, 0, tom('terra')); for (let i = 0; i < 22; i++) { const x = -5 + R() * 10, z = -3.4 + R() * 3.0; if (Math.abs(x - 0.3) < 1.1) continue; arvore(g, x, z, 0.8 + R() * 0.9, R() < 0.5 ? 'pinho' : ''); }
      for (let i = 0; i < 5; i++) { const x = -3 + R() * 6; if (Math.abs(x - 0.3) > 0.9) { cil(g, 0.03, 0.04, 0.12, x, 0, 1.0 + R() * 1.0, tom('branco')); bola(g, 0.1, x, 0.14, 1.0, tom('vermelho'), 0.5); } } bola(g, 0.3, -2.0, 0.1, 1.2, tom('pedra'), 0.6); bola(g, 0.22, 2.6, 0.08, 1.6, tom('pedra'), 0.6);
      return { gente: [[0.3, 0.4], [0.9, 1.0], [-0.4, 1.1]], obj: [[1.6, 1.2], [-1.4, 1.4], [2.4, 0.9]], centro: [0, 1.4, -1.0] }; },
    campo(g, a, R) { chao(g, a.chao || tom('grama'), R); for (let i = 0; i < 6; i++) caixa(g, LX * 0.55, 0.14, 0.3, 2.4, 0, -2.8 + i * 0.55, tom('terra')), [0, 1, 2, 3, 4, 5, 6, 7].forEach((k) => bola(g, 0.12, 0.2 + k * 0.6, 0.22, -2.8 + i * 0.55, tom('folha')));
      caixa(g, 2.0, 1.5, 1.6, -3.0, 0, -2.2, tom('vermelho')); const tel = cone(g, 1.55, 0.9, -3.0, 1.5, -2.2, tom('pedra'), 4); tel.rotation.y = Math.PI / 4; tel.scale.z = 0.8; caixa(g, 0.6, 0.9, 0.04, -3.0, 0, -1.39, tom('branco'));
      cil(g, 0.5, 0.5, 2.4, -1.5, 0, -2.6, tom('metal')); bola(g, 0.5, -1.5, 2.4, -2.6, tom('metal')); for (let i = 0; i < 9; i++) caixa(g, 0.08, 0.6, 0.08, -4.6 + i * 1.15, 0, 1.6, tom('madeira')); caixa(g, 9.4, 0.06, 0.05, 0, 0.45, 1.6, tom('madeira')); caixa(g, 9.4, 0.06, 0.05, 0, 0.25, 1.6, tom('madeira'));
      return { gente: [[0.2, 0.4], [1.2, 0.6], [-1.0, 0.6]], obj: [[2.2, 0.5], [-2.0, 0.6], [3.0, 0.8]], centro: [0, 1.0, -1.2] }; },
    praia(g, a, R) { chao(g, a.chao || tom('areia'), R); agua(g, 80, 30, 0, 0.02, -17.0, a.mar || tom('agua')); caixa(g, 80, 0.02, 0.4, 0, 0.0, -2.1, tom('branco'));
      let x = -3.2, y = 0; for (let i = 0; i < 6; i++) { cil(g, 0.1, 0.12, 0.45, x + i * 0.08, y, -1.0, tom('tronco')); y += 0.42; } for (let i = 0; i < 6; i++) { const f = cone(g, 0.18, 1.3, -2.72, y - 0.1, -1.0, tom('folha'), 4); f.rotation.z = Math.PI / 2 + 0.4; f.rotation.y = i * Math.PI / 3; f.geometry.translate(0, -0.65, 0); }
      cil(g, 0.03, 0.03, 1.7, 2.6, 0, 0.2, tom('branco')); cone(g, 0.95, 0.4, 2.6, 1.5, 0.2, PAL.des, 8); caixa(g, 0.8, 0.02, 1.6, 1.6, 0, 0.6, PAL.pri);
      return { gente: [[0.2, 0.8], [1.1, 1.1], [-1.0, 1.0]], obj: [[1.6, 0.6], [-1.8, 1.2], [2.6, 1.4]], centro: [0, 1.2, -1.0] }; },
    mar(g, a, R) { agua(g, 90, 90, 0, 0, 0, a.mar || tom('agua')); const b = new T.Group(); caixa(b, 2.6, 0.6, 1.2, 0, 0, 0, tom('madeira')); const p = cone(b, 0.6, 1.0, 1.75, 0.3, 0, tom('madeira'), 4); p.rotation.z = -Math.PI / 2; p.position.y = 0.3; caixa(b, 2.4, 0.1, 1.0, 0, 0.6, 0, tom('branco'));
      cil(b, 0.04, 0.04, 2.2, -0.2, 0.6, 0, tom('madeira')); const v = cone(b, 0.75, 1.6, 0.3, 1.0, 0, tom('branco'), 3); v.scale.z = 0.08; b.position.set(0, 0, -0.6); g.add(b); a.barco = b;
      bola(g, 1.6, -3.6, -0.6, -6.0, tom('areia'), 0.45); arvore(g, -3.6, -6.0, 0.8);
      return { gente: [[-0.3, -0.6, 0.62], [0.6, -0.6, 0.62], [-0.8, -0.5, 0.62]], obj: [[0.9, -0.5, 0.62], [-1.0, -0.6, 0.62], [0.3, -0.4, 0.62]], centro: [0, 1.0, -0.8], navega: true }; },
    montanha(g, a, R) { chao(g, a.chao || tom('grama'), R); [[-3.0, -3.6, 2.4, 3.6], [0.6, -4.4, 3.0, 4.8], [3.6, -3.4, 2.2, 3.2]].forEach(([x, z, rr, h]) => { cone(g, rr, h, x, 0, z, tom('pedra'), FAC ? 5 : 9); cone(g, rr * 0.36, h * 0.36, x, h * 0.64, z, tom('neve'), FAC ? 5 : 9); });
      for (let i = 0; i < 9; i++) arvore(g, -4.5 + R() * 9, -1.4 + R() * 1.2, 0.6 + R() * 0.4, 'pinho'); caixa(g, 0.9, 0.03, 4, 0.3, 0, 1.0, tom('terra'));
      return { gente: [[0.3, 0.8], [1.1, 1.0], [-0.6, 1.1]], obj: [[1.8, 1.0], [-1.8, 1.2], [2.6, 1.4]], centro: [0, 1.6, -1.6] }; },
    deserto(g, a, R) { chao(g, a.chao || tom('areia', 0.1), R); for (let i = 0; i < 6; i++) bola(g, 1.6 + R() * 1.4, -5 + i * 2.2, -0.6, -3.5 - R() * 2, tom('areia', 0.05).multiplyScalar(0.95), 0.35);
      const cacto = (x, z, s) => { cil(g, 0.14 * s, 0.16 * s, 1.4 * s, x, 0, z, tom('verde')); cil(g, 0.08 * s, 0.08 * s, 0.5 * s, x + 0.3 * s, 0.6 * s, z, tom('verde')); caixa(g, 0.3 * s, 0.12 * s, 0.12 * s, x + 0.15 * s, 0.6 * s, z, tom('verde')); }; cacto(-2.6, -1.0, 1.1); cacto(3.0, -1.6, 0.9); cacto(1.8, 1.4, 0.6);
      bola(g, 0.4, -1.4, 0.15, 1.3, tom('pedra'), 0.5);
      return { gente: [[0.2, 0.6], [1.2, 0.8], [-1.0, 0.9]], obj: [[1.8, 0.6], [-1.8, 0.9], [2.6, 1.4]], centro: [0, 1.2, -1.0] }; },
    espaco(g, a, R) { chao(g, a.chao || tom('pedra', 0.25), R); for (let i = 0; i < 9; i++) bola(g, 0.3 + R() * 0.5, -4.5 + R() * 9, 0.0, -2.5 + R() * 4, tom('pedra', 0.25).multiplyScalar(0.75), 0.15);
      const pl = bola(g, 2.4, 3.0, 4.6, -12, a.acento || PAL.des); pl.castShadow = false; const an = new T.Mesh(new T.TorusGeometry(3.6, 0.18, 4, 48), brilho(PAL.txt.clone().lerp(PAL.des, 0.3))); an.position.copy(pl.position); an.rotation.x = 1.25; an.rotation.y = 0.3; g.add(an); a.planeta = an;
      bola(g, 0.7, -4.2, 3.8, -10, tom('azul', 0)).castShadow = false; cil(g, 0.32, 0.32, 1.6, -2.6, 0, -1.6, tom('branco')); cone(g, 0.32, 0.7, -2.6, 1.6, -1.6, tom('vermelho')); [0, 2.1, 4.2].forEach((r2) => { const f = caixa(g, 0.05, 0.5, 0.4, -2.6 + Math.sin(r2) * 0.32, 0, -1.6 + Math.cos(r2) * 0.32, tom('vermelho')); f.rotation.y = r2; });
      return { gente: [[0.2, 0.6], [1.2, 0.8], [-0.8, 0.9]], obj: [[1.8, 0.6], [-1.4, 1.0], [2.6, 1.2]], centro: [0, 1.4, -1.0], noite: true }; },
    estrada(g, a, R) { chao(g, a.chao || tom('grama'), R); caixa(g, 90, 0.03, 2.2, 0, 0, -0.2, tom('asfalto')); a.faixas = []; for (let x = -12; x < 12; x += 1.4) a.faixas.push(caixa(g, 0.7, 0.035, 0.1, x, 0, -0.2, tom('amarelo', 0)));
      const carro = new T.Group(); caixa(carro, 1.8, 0.5, 0.9, 0, 0.2, 0, PAL.des); caixa(carro, 1.0, 0.38, 0.8, -0.1, 0.7, 0, PAL.des.clone().lerp(tom('branco'), 0.3)); luzinha(carro, 0.9, 0.28, 0.82, -0.1, 0.9, 0, tom('tela', 0.3)); [[-0.55, 0.45], [0.55, 0.45], [-0.55, -0.45], [0.55, -0.45]].forEach(([x, z]) => { const rd = cil(carro, 0.2, 0.2, 0.12, x, 0, z, tom('preto')); rd.rotation.x = Math.PI / 2; rd.position.y = 0.2; }); carro.position.set(-1.6, 0, -0.5); g.add(carro); a.carro = carro;
      [-3.6, 3.2].forEach((x) => { cil(g, 0.04, 0.04, 1.4, x, 0, 1.3, tom('metal')); caixa(g, 0.7, 0.45, 0.04, x, 1.2, 1.3, tom('verde')); }); for (let i = 0; i < 8; i++) arvore(g, -5 + i * 1.4 + R() * 0.4, -2.6 - R() * 0.8, 0.7 + R() * 0.5); if (!(ISO || MAPA)) [[-2, -9, 3, 3.6], [3, -10, 4, 4.4]].forEach(([x, z, rr, h]) => cone(g, rr, h, x, 0, z, tom('pedra', 0.4), FAC ? 5 : 9));
      return { gente: [[0.4, 1.1], [1.3, 1.2], [-0.5, 1.2]], obj: [[2.0, 1.2], [-2.4, 1.3], [2.8, 1.4]], centro: [0, 1.0, -0.6] }; },
    palco(g, a, R) { chao(g, a.chao || tom('preto', 0.3), R); caixa(g, 7.0, 0.5, 3.2, 0, 0, -1.4, tom('madeira')); for (let i = 0; i < 9; i++) { cil(g, 0.22, 0.22, 3.4, -3.6 + i * 0.22, 0.5, -2.9, tom('vermelho')); cil(g, 0.22, 0.22, 3.4, 3.6 - i * 0.22, 0.5, -2.9, tom('vermelho')); }
      caixa(g, 7.6, 0.6, 0.4, 0, 3.6, -2.9, tom('vermelho')); a.focos = [-2, 0, 2].map((x, i) => { const c = new T.Mesh(new T.ConeGeometry(0.9, 3.4, 20, 1, true), new T.MeshBasicMaterial({ color: [PAL.des, tom('branco', 0), PAL.pri][i], transparent: true, opacity: 0.18, depthWrite: false, side: T.DoubleSide })); c.position.set(x, 2.2, -1.2); g.add(c); return c; });
      cil(g, 0.03, 0.03, 1.4, 0.8, 0.5, -0.6, tom('preto')); bola(g, 0.07, 0.8, 1.95, -0.6, tom('metal')); caixa(g, 0.7, 1.0, 0.6, -3.0, 0.5, -2.0, tom('preto')); caixa(g, 0.7, 1.0, 0.6, 3.0, 0.5, -2.0, tom('preto'));
      for (let i = 0; i < 16; i++) pessoaPequena(g, -4 + (i % 8) * 1.1 + R() * 0.3, 1.4 + Math.floor(i / 8) * 0.8, [PAL.pri, PAL.des, tom('preto', 0.3)][i % 3], R);
      return { gente: [[0, -0.9, 0.5], [1.2, -0.8, 0.5], [-1.2, -0.8, 0.5]], obj: [[2.0, -1.0, 0.5], [-2.0, -1.0, 0.5], [0.9, -1.6, 0.5]], centro: [0, 1.5, -1.2], noite: true }; },
    estadio(g, a, R) { chao(g, a.chao || tom('grama'), R); for (let i = 0; i < 6; i++) caixa(g, 1.2, 0.012, 9, -5 + i * 2.4, 0, -1, tom('grama', 0.1).multiplyScalar(0.92)); caixa(g, 0.06, 0.015, 9, 0, 0, -1, tom('branco')); const cc = new T.Mesh(new T.TorusGeometry(1.0, 0.03, 4, 40), brilho(tom('branco'))); cc.rotation.x = Math.PI / 2; cc.position.y = 0.02; g.add(cc);
      [[3.9, 1], [-3.9, -1]].forEach(([x, s]) => { cil(g, 0.05, 0.05, 1.2, x, 0, -1.9, tom('branco')); cil(g, 0.05, 0.05, 1.2, x, 0, -0.1, tom('branco')); caixa(g, 0.1, 0.1, 1.9, x, 1.15, -1.0, tom('branco')); });
      for (let k = 0; k < 4; k++) { caixa(g, 14, 0.4, 0.8, 0, k * 0.4, -3.6 - k * 0.8, tom('concreto')); for (let i = 0; i < 26; i++) bola(g, 0.13, -6.5 + i * 0.52 + R() * 0.1, k * 0.4 + 0.55, -3.6 - k * 0.8, [PAL.pri, PAL.des, tom('branco'), tom('vermelho')][Math.floor(R() * 4)]); }
      bola(g, 0.16, 1.4, 0.16, 0.2, tom('branco'));
      return { gente: [[0.4, 0.4], [-0.8, 0.0], [1.6, -0.2]], obj: [[1.4, 0.2], [-2.0, 0.4], [2.6, 0.2]], centro: [0, 1.0, -1.2], bola: [1.4, 0.16, 0.2] }; },
    aeroporto(g, a, R) { chao(g, a.chao || tom('grama'), R); caixa(g, 90, 0.03, 3.0, 0, 0, -1.4, tom('asfalto')); for (let x = -12; x < 12; x += 1.6) caixa(g, 0.9, 0.035, 0.12, x, 0, -1.4, tom('branco'));
      const av = new T.Group(); const fu = cil(av, 0.42, 0.42, 4.2, 0, 0, 0, tom('branco')); fu.rotation.z = Math.PI / 2; fu.position.set(0, 0, 0); const na = bola(av, 0.42, 2.1, 0, 0, tom('branco')); na.scale.x = 1.4; caixa(av, 1.2, 0.08, 5.2, 0.1, -0.05, 0, tom('metal')); caixa(av, 0.6, 0.06, 1.8, -1.9, 0.1, 0, tom('metal')); caixa(av, 0.7, 1.0, 0.06, -1.9, 0.2, 0, PAL.des);
      for (let i = 0; i < 8; i++) luzinha(av, 0.14, 0.12, 0.84, -1.2 + i * 0.36, 0.12, 0, tom('tela', 0.2)); av.position.set(0.6, 0.85, -1.6); g.add(av); a.aviao = av; [[0.0, -1.3], [1.2, -1.3], [-1.3, -1.3]].forEach(([x, z]) => cil(g, 0.08, 0.08, 0.5, 0.6 + x, 0, -1.6 + z * 0, tom('preto')));
      cil(g, 0.35, 0.45, 3.4, -3.8, 0, -3.6, tom('concreto')); cil(g, 0.75, 0.6, 0.7, -3.8, 3.4, -3.6, tom('tela', 0.3)); cil(g, 0.8, 0.8, 0.12, -3.8, 4.1, -3.6, tom('concreto'));
      return { gente: [[0.2, 0.9], [1.2, 1.0], [-0.9, 1.0]], obj: [[2.2, 0.9], [-2.2, 1.1], [3.0, 1.2]], centro: [0, 1.4, -1.4] }; },
    palco_vazio(g, a, R) { const raio = 3.6; if (ISO || MAPA) chao(g, a.chao || PAL.sup, R); else { const m = malha(new T.CylinderGeometry(raio, raio, 0.12, BLOCO ? 64 : SEG * 3), mat(PAL.fun.clone().multiplyScalar(0.9)), 0, -0.06, 0); m.castShadow = false; g.add(m); }
      for (let i = 0; i < (P.pecas_soltas || 0); i++) { const an = R() * 6.28, ra = raio * (0.7 + R() * 0.2); caixa(g, U * 2, U * 0.9, U, Math.cos(an) * ra, 0, Math.sin(an) * ra, i % 2 ? PAL.sup : PAL.pri, R() * 3); }
      return { gente: [[0, 0.3], [1.1, 0.4], [-1.1, 0.4]], obj: [[1.6, -0.6], [-1.6, -0.6], [0, -1.4]], centro: [0, 1.0, 0], vazio: true }; },
  };

  // ---- personagens: corpo articulado no material do estilo; as poses saem da ação --------------------------------------
  const quadrado = PIX || BLOCO || FAC;
  // i é o ator do elenco: o mesmo índice dá o mesmo visual em todos os planos; robo troca pele e cabelo por metal e tela
  function boneco(i, robo) {
    const g = new T.Group(), pele = robo ? tom('metal', 0.1) : new T.Color(PELES[(i + M.semente) % 4]), roupa = robo ? tom('metal', 0.25).multiplyScalar(0.85) : [PAL.des, PAL.pri, tom('verde', 0.3), tom('rosa', 0.2)][i % 4],
      calca = robo ? tom('preto', 0.25) : [PAL.pri.clone().multiplyScalar(0.6), tom('azul', 0.3).multiplyScalar(0.7), tom('preto', 0.2)][i % 3];
    const quadril = new T.Group(); quadril.position.y = 0.82; g.add(quadril); const corpo = new T.Group(); quadril.add(corpo);
    caixa(corpo, 0.5, 0.62, 0.28, 0, 0, 0, roupa); const cab = new T.Group(); cab.position.y = 0.66; corpo.add(cab);
    if (quadrado) caixa(cab, 0.4, 0.4, 0.36, 0, 0, 0, pele); else bola(cab, 0.22, 0, 0.21, 0, pele);
    const zf = quadrado ? 0.185 : 0.2;
    if (robo) { cil(cab, 0.015, 0.015, 0.18, 0, 0.4, 0, tom('metal', 0)); luzinha(cab, 0.07, 0.07, 0.07, 0, 0.6, 0, PAL.des); luzinha(cab, 0.32, 0.28, 0.02, 0, 0.18, zf - 0.002, tom('preto', 0)); luzinha(corpo, 0.18, 0.1, 0.02, 0, 0.42, 0.145, tom('tela', 0)); }
    else { const cb = new T.Color(CABELOS[(i * 3 + M.semente) % 4]); if (quadrado) caixa(cab, 0.42, 0.13, 0.38, 0, 0.36, -0.01, cb); else bola(cab, 0.225, 0, 0.27, -0.03, cb, 0.75); }
    [-0.08, 0.08].forEach((x) => luzinha(cab, 0.05, 0.06, 0.02, x, 0.24, zf + 0.005, robo ? tom('tela', 0) : tom('preto', 0)));
    const boca = luzinha(cab, 0.12, 0.03, 0.02, 0, 0.12, zf + 0.005, robo ? tom('tela', 0) : new T.Color('#7A2E2E'));
    const braco = (x) => { const o = new T.Group(); o.position.set(x, 0.56, 0); corpo.add(o); const b = caixa(o, 0.13, 0.52, 0.13, 0, -0.52, 0, roupa); if (quadrado) caixa(o, 0.12, 0.12, 0.12, 0, -0.64, 0, pele); else bola(o, 0.07, 0, -0.6, 0, pele); return o; };
    const perna = (x) => { const o = new T.Group(); o.position.set(x, 0, 0); quadril.add(o); caixa(o, 0.17, 0.74, 0.17, 0, -0.78, 0, calca); caixa(o, 0.19, 0.08, 0.27, 0, -0.82, 0.04, tom('preto', 0.1)); return o; };
    const b = { g, quadril, corpo, cab, boca, bE: braco(-0.33), bD: braco(0.33), pE: perna(-0.13), pD: perna(0.13) };
    g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
    return b;
  }
  const passo_s = P.passo_sprite_s || 0.16;
  function pose(b, acao, u, t, dur) {
    const tq = PIX ? Math.floor(t / passo_s) * passo_s : t;
    b.g.rotation.set(0, b.g.rotation.y, 0); b.g.position.y = b.base || 0; b.quadril.position.y = 0.82; b.corpo.rotation.set(0, 0, 0); b.cab.rotation.set(0, 0, 0);
    [b.bE, b.bD, b.pE, b.pD].forEach((o) => o.rotation.set(0, 0, 0)); b.bE.rotation.z = -0.08; b.bD.rotation.z = 0.08; b.boca.scale.y = 1;
    const resp = Math.sin(t * 2.1) * 0.012; b.corpo.scale.y = 1 + resp;
    if (acao === 'andar' || acao === 'correr') { const vel = acao === 'correr' ? 12 : 7, amp = acao === 'correr' ? 0.9 : 0.55, f = Math.sin(tq * vel);
      b.pE.rotation.x = f * amp; b.pD.rotation.x = -f * amp; b.bE.rotation.x = -f * amp * 0.9; b.bD.rotation.x = f * amp * 0.9; b.quadril.position.y = 0.82 + Math.abs(Math.cos(tq * vel)) * (acao === 'correr' ? 0.08 : 0.035); if (acao === 'correr') b.corpo.rotation.x = 0.25; }
    else if (acao === 'falar') { b.bD.rotation.x = -1.1 + 0.3 * Math.sin(tq * 4.5); b.bD.rotation.z = 0.35; b.bE.rotation.x = -0.4 + 0.15 * Math.sin(tq * 3.1 + 1); b.cab.rotation.y = 0.18 * Math.sin(tq * 2.3); b.cab.rotation.x = 0.06 * Math.sin(tq * 5); b.boca.scale.y = 0.6 + 2.6 * Math.abs(Math.sin(tq * 11)); }
    else if (acao === 'pensar') { b.bD.rotation.x = -2.35; b.bD.rotation.z = 0.55; b.bE.rotation.x = -0.9; b.bE.rotation.z = -0.7; b.cab.rotation.z = 0.16 + 0.04 * Math.sin(tq * 1.5); b.cab.rotation.x = -0.12; }
    else if (acao === 'comemorar' || acao === 'pular') { const s = acao === 'comemorar' ? 6.5 : 5; b.bE.rotation.z = -2.6 - 0.25 * Math.sin(tq * s * 2); b.bD.rotation.z = 2.6 + 0.25 * Math.sin(tq * s * 2); b.g.position.y = (b.base || 0) + Math.abs(Math.sin(tq * s)) * (acao === 'pular' ? 0.5 : 0.32); b.pE.rotation.x = -0.25 * Math.abs(Math.sin(tq * s)); b.pD.rotation.x = -0.25 * Math.abs(Math.sin(tq * s)); b.boca.scale.y = 2.6; }
    else if (acao === 'cair') { const k = liso((u - 0.25) / 0.45), q = Math.exp(-7 * clamp(u - 0.7, 0, 9)) * Math.sin(clamp(u - 0.7, 0, 9) * 18) * 0.05 * amort; b.g.rotation.x = k * 1.5 + q; b.g.position.y = (b.base || 0) + k * 0.12; b.bE.rotation.z = -1.2 * k - 0.1; b.bD.rotation.z = 1.2 * k + 0.1; b.bE.rotation.x = -2 * k; b.bD.rotation.x = -2 * k; b.pE.rotation.x = 0.4 * k; b.boca.scale.y = 1 + 2 * (1 - k); }
    else if (acao === 'trabalhar') { const f = Math.sin(tq * 9); b.bE.rotation.x = -1.2 + 0.35 * f; b.bD.rotation.x = -1.2 - 0.35 * f; b.corpo.rotation.x = 0.18; b.cab.rotation.x = 0.25; }
    else if (acao === 'apontar') { const k = liso(u / 0.35); b.bD.rotation.x = -1.5 * k; b.bD.rotation.z = -0.15; b.cab.rotation.y = -0.25 * k; b.corpo.rotation.y = -0.2 * k; }
    else if (acao === 'sentar') { b.quadril.position.y = 0.5; b.pE.rotation.x = -1.45; b.pD.rotation.x = -1.45; b.bE.rotation.x = -0.5; b.bD.rotation.x = -0.5; b.cab.rotation.y = 0.1 * Math.sin(tq * 0.9); }
    else if (acao === 'dormir') { b.g.rotation.x = -Math.PI / 2; b.g.position.y = (b.base || 0) + 0.16; b.bE.rotation.z = -0.15; b.bD.rotation.z = 0.15; b.corpo.scale.y = 1 + Math.sin(t * 1.4) * 0.03; b.boca.scale.y = 0.5; }
    else if (acao === 'triste') { b.cab.rotation.x = 0.5; b.corpo.rotation.x = 0.2; b.bE.rotation.z = 0.1; b.bD.rotation.z = -0.1; b.quadril.position.y = 0.8 + Math.sin(tq * 0.8) * 0.01; b.boca.scale.y = 0.6; }
  }

  // ---- efeitos de situação e clima -----------------------------------------------------------------------------------
  const spriteTexto = (txt, c, fundo, px) => { px = px || 128; const n = document.createElement('canvas'); n.width = n.height = PIX ? 32 : px; const x = n.getContext('2d'), s = n.width;
    if (fundo) { x.fillStyle = fundo; x.beginPath(); x.ellipse(s / 2, s / 2, s * 0.46, s * 0.36, 0, 0, Math.PI * 2); x.fill(); }
    x.fillStyle = c; x.font = `bold ${Math.round(s * (fundo ? 0.42 : 0.8))}px sans-serif`; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(txt, s / 2, s / 2 + s * 0.04);
    const tx = new T.CanvasTexture(n); tx.colorSpace = T.SRGBColorSpace; if (PIX) tx.magFilter = tx.minFilter = T.NearestFilter; const sp = new T.Sprite(new T.SpriteMaterial({ map: tx, transparent: true, depthWrite: false })); return sp; };
  const DES = '#' + PAL.des.getHexString(), TXT = '#' + PAL.txt.getHexString(), FUN = '#' + PAL.fun.getHexString();
  function efeito(nome, g, cabecas, centro, R) {
    const f = []; const add = (o) => { g.add(o); return o; };
    const sobre = (k) => cabecas[k % Math.max(1, cabecas.length)] || (() => new T.Vector3(centro[0], 1.6, centro[2]));
    if (nome === 'festa') { const cs = [PAL.des, PAL.pri, tom('amarelo', 0), tom('rosa', 0), tom('azul', 0)]; const pc = []; for (let i = 0; i < 70; i++) { const m = new T.Mesh(new T.PlaneGeometry(0.09, 0.05), new T.MeshBasicMaterial({ color: cs[i % 5], side: T.DoubleSide })); m.userData = { x: centro[0] + (R() - 0.5) * 7, z: centro[2] + (R() - 0.5) * 3 + 0.8, o: R() * 4, v: 0.6 + R() * 0.6, r: R() * 6 }; add(m); pc.push(m); }
      const fio = []; for (let i = 0; i < 12; i++) { const b = cone(g, 0.14, 0.24, -3.3 + i * 0.6, 2.55 - Math.sin(i / 11 * Math.PI) * 0.35, -1.6, cs[i % 5], 3); b.rotation.x = Math.PI; fio.push(b); }
      f.push((t, u) => pc.forEach((m) => { const d = m.userData; m.position.set(d.x + Math.sin(t * 2 + d.r) * 0.15, 3.2 - ((u * d.v + d.o) % 3.4), d.z); m.rotation.set(t * 3 + d.r, t * 2 + d.r, 0); })); }
    if (nome === 'ideia') { const l = new T.Group(); const bulbo = bola(l, 0.2, 0, 0.22, 0, PAL.des); bulbo.material = brilho(tom('amarelo', 0)); cil(l, 0.08, 0.08, 0.12, 0, -0.02, 0, tom('metal')); const raios = []; for (let i = 0; i < 8; i++) { const r2 = luzinha(l, 0.03, 0.14, 0.03, Math.cos(i * 0.785) * 0.36, 0.22 + Math.sin(i * 0.785) * 0.36, 0, tom('amarelo', 0)); r2.rotation.z = i * 0.785 - Math.PI / 2; raios.push(r2); } add(l);
      f.push((t, u) => { const p = sobre(0)(); l.position.set(p.x, p.y + 0.55, p.z); const k = liso(u / 0.35); l.scale.setScalar(Math.max(0.001, k * (1 + 0.08 * Math.sin(t * 8)))); raios.forEach((r2) => { r2.visible = u > 0.3; }); }); }
    const flutua = (txt, cfund, n, k0, sobe) => { const ss = []; for (let i = 0; i < n; i++) { const s = add(spriteTexto(txt, cfund ? TXT : DES, cfund)); s.userData = { o: i / n, k: k0 + i, x: (R() - 0.5) * 0.6 }; ss.push(s); }
      f.push((t, u) => ss.forEach((s) => { const p = sobre(s.userData.k)(), q = ((u * 0.45 + s.userData.o) % 1); s.position.set(p.x + s.userData.x + Math.sin(t * 2 + s.userData.o * 6) * 0.08, p.y + 0.35 + (sobe ? q * 1.1 : 0.2), p.z); const a = sobe ? Math.sin(q * Math.PI) : liso(u / 0.3); s.material.opacity = a; s.scale.setScalar(0.42 * (sobe ? 0.7 + q * 0.5 : 1)); })); };
    if (nome === 'duvida') flutua('?', null, 3, 0, true);
    if (nome === 'amor') flutua('♥', null, 5, 0, true);
    if (nome === 'sono') flutua('Z', null, 3, 0, true);
    if (nome === 'conversa') { const bs = cabecas.slice(0, 2).map((h, i) => { const s = add(spriteTexto(i ? '!' : '...', '#' + PAL.fun.getHexString(), TXT)); s.userData.h = h; return s; });
      f.push((t, u) => bs.forEach((s, i) => { const p = s.userData.h(), on = Math.floor(u / 0.9) % 2 === i; s.position.set(p.x + (i ? 0.3 : -0.3), p.y + 0.55, p.z); s.scale.setScalar(on ? 0.62 : 0.001); })); }
    if (nome === 'dinheiro' || nome === 'sucesso') { const ms = []; for (let i = 0; i < 26; i++) { const m = nome === 'dinheiro' ? malha(new T.CylinderGeometry(0.1, 0.1, 0.025, PIX ? 8 : 16), mat(tom('ouro', 0)), 0, 0, 0) : add(spriteTexto('★', DES)); if (nome === 'dinheiro') add(m); m.userData = { x: centro[0] + (R() - 0.5) * 4, z: centro[2] + 1.0 + (R() - 0.5) * 1.6, o: R() * 3, r: R() * 6 }; ms.push(m); }
      if (nome === 'sucesso') { const tr = new T.Group(); cil(tr, 0.16, 0.22, 0.12, 0, 0, 0, tom('ouro', 0)); cil(tr, 0.04, 0.04, 0.22, 0, 0.12, 0, tom('ouro', 0)); cil(tr, 0.26, 0.12, 0.34, 0, 0.32, 0, tom('ouro', 0)); add(tr); f.push((t, u) => { const p = sobre(0)(); tr.position.set(p.x + 0.55, p.y - 0.3, p.z + 0.2); tr.scale.setScalar(Math.max(0.001, liso(u / 0.4)) * 1.2); tr.rotation.y = t; }); }
      f.push((t, u) => ms.forEach((m) => { const d = m.userData; if (nome === 'dinheiro') { m.position.set(d.x, 3.0 - ((u * 1.3 + d.o) % 3.2), d.z); m.rotation.set(t * 4 + d.r, 0, t * 3); } else { const q = (u * 0.7 + d.o) % 1; m.position.set(d.x, 1.2 + q * 2.0, d.z); m.material.opacity = Math.sin(q * Math.PI); m.scale.setScalar(0.25 + 0.2 * Math.sin(t * 6 + d.r)); } })); }
    if (nome === 'tempo') { const rel = new T.Group(); const d = malha(new T.CylinderGeometry(0.42, 0.42, 0.06, 32), mat(tom('branco', 0)), 0, 0, 0); d.rotation.x = Math.PI / 2; rel.add(d); const aro = new T.Mesh(new T.TorusGeometry(0.42, 0.05, 6, 32), mat(PAL.des)); rel.add(aro);
      const p1 = new T.Group(), p2 = new T.Group(); luzinha(p1, 0.04, 0.3, 0.02, 0, 0.15, 0.05, tom('preto', 0)); luzinha(p2, 0.04, 0.22, 0.02, 0, 0.11, 0.05, tom('vermelho', 0)); rel.add(p1); rel.add(p2); add(rel);
      f.push((t, u) => { const p = sobre(0)(); rel.position.set(p.x + 0.75, p.y + 0.45, p.z); rel.scale.setScalar(Math.max(0.001, liso(u / 0.3))); p1.rotation.z = -t * 6; p2.rotation.z = -t * 0.6; rel.quaternion.copy(cam.quaternion); }); }
    if (nome === 'perigo') { const s = add(spriteTexto('!', '#FFFFFF', '#D9534F')); const l = add(new T.PointLight(0xff3030, 0, 9)); f.push((t, u) => { const p = sobre(0)(); s.position.set(p.x, p.y + 0.62, p.z); const pis = Math.sin(t * 10) > 0 ? 1 : 0.35; s.scale.setScalar(0.6 * pis); l.position.set(p.x, p.y + 1.2, p.z + 1); l.intensity = 14 * pis * liso(u / 0.2); }); }
    if (nome === 'tristeza') { const nv = new T.Group(); [[-0.2, 0], [0.15, 0.05], [0, 0.12]].forEach(([x, y]) => bola(nv, 0.24, x, y, 0, tom('pedra', 0.3))); add(nv); const gotas = []; for (let i = 0; i < 10; i++) { const m = luzinha(g, 0.025, 0.12, 0.025, 0, 0, 0, tom('agua', 0)); m.userData.o = R(); m.userData.x = (R() - 0.5) * 0.5; gotas.push(m); }
      f.push((t, u) => { const p = sobre(0)(); nv.position.set(p.x, p.y + 0.9, p.z); gotas.forEach((m) => { const q = (u * 1.4 + m.userData.o) % 1; m.position.set(p.x + m.userData.x, p.y + 0.8 - q * 0.9, p.z); }); }); }
    if (nome === 'raiva') { const fu = []; for (let i = 0; i < 6; i++) { const m = bola(g, 0.12, 0, 0, 0, tom('pedra', 0.2)); m.userData.o = i / 6; m.userData.l = i % 2 ? 1 : -1; fu.push(m); } const s = add(spriteTexto('#!', '#FFFFFF', '#D9534F'));
      f.push((t, u) => { const p = sobre(0)(); fu.forEach((m) => { const q = (u * 0.9 + m.userData.o) % 1; m.position.set(p.x + m.userData.l * (0.2 + q * 0.3), p.y + 0.35 + q * 0.6, p.z); m.scale.setScalar(Math.max(0.001, 0.5 + q)); }); s.position.set(p.x + 0.4, p.y + 0.6, p.z); s.scale.setScalar(0.4 + 0.08 * Math.sin(t * 14)); }); }
    if (nome === 'crescimento' || nome === 'queda') { const sobe = nome === 'crescimento', gr = new T.Group(); const bs = [0, 1, 2, 3].map((i) => { const gb = new T.BoxGeometry(0.28, 1, 0.28); gb.translate(0, 0.5, 0); const m = malha(gb, mat(i === 3 ? (sobe ? tom('verde', 0) : tom('vermelho', 0)) : PAL.pri), i * 0.4, 0, 0); gr.add(m); return m; }); const seta = cone(gr, 0.18, 0.36, 1.2, 0, 0, sobe ? tom('verde', 0) : tom('vermelho', 0)); add(gr);
      const alvo = sobe ? [0.4, 0.7, 1.0, 1.5] : [1.5, 1.1, 0.7, 0.35]; gr.position.set(centro[0] + 1.8, 0, centro[2] + 1.0);
      f.push((t, u) => { bs.forEach((b, i) => { const k = liso((u - i * 0.18) / 0.4); b.scale.y = Math.max(0.001, k * alvo[i]); }); const k = liso((u - 0.8) / 0.4); seta.position.set(1.4, (sobe ? 1.7 : 0.2) + (sobe ? 1 : -1) * 0.1 * Math.sin(t * 5), 0); seta.rotation.z = sobe ? 0 : Math.PI; seta.scale.setScalar(Math.max(0.001, k)); }); }
    return (t, u) => f.forEach((fn) => fn(t, u));
  }

  // ---- os planos do curta ---------------------------------------------------------------------------------------------
  const sol = new T.DirectionalLight(0xffffff, 2.0); sol.castShadow = true; sol.shadow.mapSize.set(PIX ? 512 : 2048, PIX ? 512 : 2048); Object.assign(sol.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 1, far: 40 }); sol.shadow.bias = -0.0006; cena.add(sol); cena.add(sol.target);
  const hemi = new T.HemisphereLight(0xffffff, 0x444444, 1.2); cena.add(hemi);
  const estrelas = (() => { const n = 500, p = new Float32Array(n * 3), q = rng(M.semente + 3); for (let i = 0; i < n; i++) { const a = q() * 6.28, e = 0.05 + q() * 1.3, rr = 120; p[i * 3] = Math.cos(e) * Math.sin(a) * rr; p[i * 3 + 1] = Math.sin(e) * rr; p[i * 3 + 2] = Math.cos(e) * Math.cos(a) * rr; } const gg = new T.BufferGeometry(); gg.setAttribute('position', new T.BufferAttribute(p, 3)); const o = new T.Points(gg, new T.PointsMaterial({ color: 0xffffff, size: PIX ? 2 : 1.6, sizeAttenuation: false })); cena.add(o); return o; })();
  const chuvaG = new T.BufferGeometry(), NCH = 260, chP = new Float32Array(NCH * 6); chuvaG.setAttribute('position', new T.BufferAttribute(chP, 3)); const chuva = new T.LineSegments(chuvaG, new T.LineBasicMaterial({ color: 0xcfe3ff, transparent: true, opacity: 0.6 })); chuva.frustumCulled = false; cena.add(chuva);
  const neveG = new T.BufferGeometry(), neP = new Float32Array(NCH * 3); neveG.setAttribute('position', new T.BufferAttribute(neP, 3)); const neve = new T.Points(neveG, new T.PointsMaterial({ color: 0xffffff, size: PIX ? 3 : 4 * esc, sizeAttenuation: false })); neve.frustumCulled = false; cena.add(neve);
  const SETS = {};
  const VIS = BLOCO ? { az: 0.6, el: 0.36 } : FAC ? { az: -0.45, el: 0.32 } : PIX ? { az: 0.3, el: 0.3 } : MAPA ? { az: 0.12, el: 0.95 } : { az: Math.PI / 4, el: Math.atan(1 / Math.SQRT2) };
  const camada = document.getElementById('rotulos3d');
  const PL = M.planos.map((s, i) => {
    const R = rng(M.semente * 31 + i * 7);
    const momento = s.momento || ((PIX && P.noite !== false) ? 'noite' : 'dia');
    const tn = s.tons || [];
    const chave = `${s.cenario}|${momento}|${tn.join(',')}`;
    if (!SETS[chave]) { const g = new T.Group(), a = { noite: momento === 'noite' }; if (tn[0]) a.chao = new T.Color(tn[0]).lerp(PAL.sup, 0.25); if (tn[2]) a.acento = new T.Color(tn[2]); if (tn[1]) a.mar = new T.Color(tn[1]);
      const info = (CEN[s.cenario] || CEN.palco_vazio)(g, a, rng(M.semente + s.cenario.length * 13)); g.visible = false; cena.add(g); g.traverse((o) => { if (o.isMesh && o.material && o.material.isMeshBasicMaterial) o.castShadow = false; });
      const filhos = g.children.slice(); SETS[chave] = { g, a, info, filhos, interno: INTERNOS.has(s.cenario), momento, tn }; }
    const set = SETS[chave], info = set.info;
    const extra = new T.Group(); extra.visible = false; cena.add(extra);
    const nomes = (s.personagens || []).map((p) => p.nome).filter(Boolean).concat(s.nomes || []);
    const pers = (s.personagens || []).slice(0, 3);
    if (!pers.length && (s.nomes || []).length) pers.push({ nome: s.nomes[0], acao: 'andar' });
    if (s.situacao === 'multidao') for (let k = 0; k < 8; k++) { const q = R(); const b = boneco(k + 3); b.g.scale.setScalar(0.85); b.g.position.set(info.centro[0] + (q - 0.5) * 6, 0, info.centro[2] - 0.6 - R() * 1.2); b.g.rotation.y = (R() - 0.5) * 0.6; extra.add(b.g); b.multi = true; b.fase = R() * 6; (s.multi = s.multi || []).push(b); }
    const bs = pers.map((p, k) => { const b = boneco(Number.isInteger(p.ator) ? p.ator : k, p.tipo === 'robo'); const sp = info.gente[k % info.gente.length]; b.x0 = sp[0]; b.z0 = sp[1]; b.base = sp[2] || 0; b.acao = p.acao; b.nome = p.nome;
      if (p.acao === 'sentar') { const banco = info.banco; if (banco && k === 0) { b.x0 = banco[0]; b.z0 = banco[2] + 0.05; b.base = 0; } else { const q = new T.Group(); caixa(q, 0.5, 0.42, 0.45, 0, 0, -0.05, tom('madeira')); q.position.set(b.x0, b.base, b.z0); extra.add(q); } }
      if (p.acao === 'dormir' && info.cama && k === 0) { b.x0 = info.cama[0]; b.z0 = info.cama[2] + 1.0; b.base = info.cama[1]; }
      extra.add(b.g); return b; });
    const cabecas = bs.map((b) => () => b.g.position.clone().add(new T.Vector3(0, b.acao === 'dormir' ? 0.45 : (b.acao === 'sentar' ? 1.3 : 1.65), b.acao === 'dormir' ? -1.5 : 0)));
    const objs = (s.objetos || []).slice(0, 3).map((o, k) => { const og = new T.Group(); (M.formas[o.forma] || []).forEach((p) => { const [tp, x, y, z, w, h, d, ci] = p; const c = [PAL.pri, PAL.des, PAL.sup, PAL.txt, PAL.txt][ci] || PAL.pri;
        if (tp === 'c') caixa(og, w, h, d, x, y, z, c); else if (tp === 'r') cil(og, w / 2, w / 2, h, x, y, z, c); else if (tp === 'p') cone(og, w / 2, h, x, y, z, c); else { const m = bola(og, 0.5, x, y + h / 2, z, c); m.scale.set(w, h, d); } });
      const sp = info.obj[k % info.obj.length]; og.position.set(sp[0], sp[2] || 0, sp[1]); og.scale.setScalar(0.75); extra.add(og); return { g: og, t: o.t, nome: o.nome }; });
    (s.aderecos || []).forEach((f, k) => { const og = new T.Group(); (M.formas[f] || []).forEach((p) => { const [tp, x, y, z, w, h, d, ci] = p; const c = [PAL.pri, PAL.des, PAL.sup, PAL.txt, PAL.txt][ci] || PAL.pri; if (tp === 'c') caixa(og, w, h, d, x, y, z, c); else if (tp === 'r') cil(og, w / 2, w / 2, h, x, y, z, c); else if (tp === 'p') cone(og, w / 2, h, x, y, z, c); else { const m = bola(og, 0.5, x, y + h / 2, z, c); m.scale.set(w, h, d); } });
      const sp = info.obj[(k + objs.length) % info.obj.length]; og.position.set(-sp[0] * 0.9, sp[2] || 0, sp[1] + 0.3); og.scale.setScalar(0.6); extra.add(og); });
    const ef = efeito(s.situacao, extra, cabecas, info.centro, R);
    // rota desenhada no chão quando alguém anda ou corre (o traço do estilo Rota em Foco)
    let rota = null; if (MAPA && bs.some((b) => b.acao === 'andar' || b.acao === 'correr')) { const b = bs[0]; const pts = []; for (let k = 0; k <= 20; k++) { const q = k / 20; pts.push(new T.Vector3(b.x0 - 1.8 + q * 3.6, 0.04, b.z0 + Math.sin(q * Math.PI * 2) * 0.25)); } const cv2 = new T.CatmullRomCurve3(pts); rota = new T.Mesh(new T.TubeGeometry(cv2, 80, (P.espessura_rota || 1) * 0.04, 6, false), brilho(PAL.des)); extra.add(rota); }
    // placa: no roteiro do curta, a placa escolhida (palavras ditas no plano); sem roteiro, as palavras ditas do lugar e dos objetos
    const ditos = s.roteiro ? [s.placa].filter(Boolean) : [s.lugar, ...objs.map((o) => o.nome), ...nomes].filter(Boolean).filter((x, k, l) => l.indexOf(x) === k).slice(0, 3);
    let placa = null; if (ditos.length) { placa = document.createElement('div'); placa.className = 'placa3' + (PIX ? ' pixel' : ''); placa.textContent = ditos.join(' · '); camada.appendChild(placa);
      const fs = 44 * esc, w = placa.textContent.length * fs * 0.64 + 44 * esc, h = fs * 1.05 + 22 * esc; const cand = [[F.x + 12 * esc, F.y + 12 * esc], [F.x + F.w - w - 12 * esc, F.y + 12 * esc], [F.x + 12 * esc, F.y + F.h - h - 12 * esc], [S.x + 8, S.y + 8]];
      const cruza = (a2, b2) => a2.x < b2.x + b2.w && b2.x < a2.x + a2.w && a2.y < b2.y + b2.h && b2.y < a2.y + a2.h; const c = cand.find(([x, y]) => !G.exclusoes.some((e) => cruza({ x, y, w, h }, e))) || cand[0];
      placa.style.transform = `translate(${c[0].toFixed(0)}px,${c[1].toFixed(0)}px)`; }
    const novo = i === 0 || M.planos[i - 1].cenario !== s.cenario || (M.planos[i - 1].tons || []).join() !== tn.join();
    return { s, i, set, extra, bs, objs, ef, placa, novo, rota, momento, az0: VIS.az + (ISO ? 0 : (R() - 0.5) * 0.7), lugar_t: s.lugar_t || s.t0, primeiro: s.roteiro ? (ditos.length ? Math.max(s.t0, (s.placa_t || s.t0) - 0.1) : s.t0) : ditos.length ? Math.min(s.lugar ? s.lugar_t : 1e9, ...objs.map((o) => o.t), s.t0 + 0.2) : s.t0 };
  });
  if (MAPA) { const selo = document.createElement('div'); selo.className = 'rot3 selo'; selo.textContent = M.planos.some((p) => p.ficticio) ? 'Mapa fictício' : 'Esquema ilustrativo, sem escala'; selo.style.transform = `translate(${(S.x + 8).toFixed(0)}px,${(S.y + S.h - 64 * esc).toFixed(0)}px)`; camada.appendChild(selo); }
  // a montagem de um lugar novo: as peças sobem do chão em sequência (no Encaixe Vivo, com a duração da montagem)
  const montagem = BLOCO ? (P.duracao_montagem || 1) : 0.6;

  // ---- câmera: plano e movimento viram alvo, tamanho e ângulo; o enquadramento usa o retângulo livre -----------------
  const persp = !(ISO || MAPA);
  const cam = persp ? new T.PerspectiveCamera(30, W / H, 0.05, 600) : new T.OrthographicCamera(-1, 1, 1, -1, 0.1, 600);
  const olhar = (alvo, hw, hh, az, el) => {
    const halfH = Math.max(hh * H / F.h, hw * H / F.w), dir = new T.Vector3(Math.cos(el) * Math.sin(az), Math.sin(el), Math.cos(el) * Math.cos(az));
    if (persp) { const d = halfH / Math.tan(cam.fov * Math.PI / 360); cam.position.copy(alvo).addScaledVector(dir, d); cam.near = Math.max(0.05, d * 0.05); cam.far = d * 40 + 200; }
    else { cam.position.copy(alvo).addScaledVector(dir, 60); const hw2 = halfH * W / H; cam.left = -hw2; cam.right = hw2; cam.top = halfH; cam.bottom = -halfH; }
    cam.lookAt(alvo); cam.setViewOffset(W, H, W / 2 - FX, H / 2 - FY, W, H); cam.updateProjectionMatrix(); cam.updateMatrixWorld(); };
  const posDo = (b, t, s) => { const u = t - s.t0, dur = Math.max(0.5, s.t1 - s.t0); if (b.acao === 'andar' || b.acao === 'correr') { const v = b.acao === 'correr' ? 3.6 : 2.2, q = clamp(u / dur); return new T.Vector3(b.x0 - v / 2 + v * q, b.base, b.z0); } return new T.Vector3(b.x0, b.base, b.z0); };
  const ACIMA = new Set(['ideia', 'duvida', 'amor', 'sono', 'conversa', 'perigo', 'raiva', 'tristeza', 'tempo']);
  function camDo(p, t) {
    const s = p.s, u = t - s.t0, dur = Math.max(0.6, s.t1 - s.t0), k = liso(u / dur), info = p.set.info, c = info.centro;
    let alvo = new T.Vector3(c[0], c[1], c[2]), hw = 4.6, hh = 2.4, az = p.az0, el = VIS.el;
    const b0 = p.bs[0]; const pb = b0 ? b0.g.position : null;
    const plano = (!b0 && (s.plano === 'medio' || s.plano === 'close')) ? 'conjunto' : (s.plano === 'detalhe' && !p.objs.length && !b0 ? 'conjunto' : s.plano);
    if (plano === 'conjunto' && p.bs.length) { const bx = new T.Box3(); p.bs.forEach((b) => bx.expandByPoint(b.g.position)); const cc = bx.getCenter(new T.Vector3()); alvo.set(cc.x, (b0.base || 0) + 1.0, cc.z); hw = Math.max(1.8, (bx.max.x - bx.min.x) / 2 + 1.2); hh = 1.5; }
    else if (plano === 'conjunto') { hw = 3.2; hh = 1.8; }
    else if (plano === 'medio' && pb) { alvo.set(pb.x, (b0.base || 0) + (b0.acao === 'dormir' ? 0.3 : 1.2), pb.z); hw = 0.95; hh = 0.85; el = persp ? 0.14 : el; }
    else if (plano === 'close' && pb) { alvo.set(pb.x, (b0.base || 0) + (b0.acao === 'sentar' ? 1.3 : (b0.acao === 'dormir' ? 0.4 : 1.62)), pb.z + (b0.acao === 'dormir' ? -1.5 : 0)); hw = 0.55; hh = 0.5; el = persp ? 0.06 : el; if (ACIMA.has(s.situacao)) { alvo.y += 0.28; hh = 0.78; hw = 0.7; } }
    else if (plano === 'detalhe') { const o = p.objs[0]; if (o) { alvo.copy(o.g.position).add(new T.Vector3(0, 0.35, 0)); hw = 0.9; hh = 0.7; el = persp ? 0.42 : el; } else if (pb) { alvo.set(pb.x, 1.0, pb.z); hw = 1.1; hh = 0.9; } }
    else if (plano === 'aereo') { hw = 4.8; hh = 3.0; el = persp ? 1.25 : Math.min(1.45, el + 0.4); alvo.set(c[0], 0.4, c[2] + 0.4); }
    else { el = persp ? (info.vazio ? 0.4 : 0.26) : el; }
    if (ISO || MAPA) { hw = Math.max(hw, plano === 'geral' || plano === 'aereo' ? LX * 0.56 : hw * 1.6); hh = Math.max(hh, plano === 'geral' ? LZ * 0.5 + hc * 0.5 : hh * 1.6); }
    hw *= aprox; hh *= aprox;
    const mv = s.movimento; let z = 1;
    if (mv === 'aproximar') z = mix(1.18, 0.9, k); else if (mv === 'afastar') z = mix(0.9, 1.15, k); else if (mv === 'panoramica') az += mix(-0.32, 0.32, k); else if (mv === 'travelling') alvo.x += mix(-0.5, 0.5, k) * (plano === 'close' || plano === 'medio' ? 0.3 : 1);
    if (s.transicao === 'zoom' && p.i > 0) z *= mix(0.3, 1, liso(u / 0.5));
    const prox = PL[p.i + 1]; if (prox && prox.s.transicao === 'zoom' && s.t1 - t < 0.3) z *= mix(1, 0.35, liso(1 - (s.t1 - t) / 0.3));
    olhar(alvo, hw * z, hh * z, az, el);
  }

  // ---- céu, luz e clima de cada plano -------------------------------------------------------------------------------
  const CEUS = {};
  const ceu = (p) => { const k = p.set.interno ? 'i' + p.momento : p.momento + (p.s.clima || '') + (p.set.tn[1] || '') + p.s.cenario; if (CEUS[k]) return CEUS[k];
    if (ISO || MAPA || p.set.info.vazio) return (CEUS[k] = PAL.fun.clone().lerp(p.momento === 'noite' ? new T.Color('#0E1530') : PAL.fun, 0.5));
    let a = tom('ceu', 0.1), b = tom('branco', 0.2);
    if (p.momento === 'noite' || p.s.cenario === 'espaco') { a = new T.Color('#070B1E'); b = new T.Color('#1A2350'); } else if (p.momento === 'tarde') { a = new T.Color('#3B4A8C'); b = new T.Color('#F4A35E'); } else if (p.momento === 'manha') { a = new T.Color('#8EC5E8'); b = new T.Color('#FBE3B8'); }
    if (p.s.clima === 'chuva') { a = a.lerp(new T.Color('#4A5563'), 0.7); b = b.lerp(new T.Color('#8A94A0'), 0.7); } if (p.s.clima === 'neve') { a = a.lerp(new T.Color('#B9C6D3'), 0.5); b = b.lerp(new T.Color('#EEF2F6'), 0.6); }
    if (p.s.cenario === 'deserto' && p.momento === 'dia') b = new T.Color('#FBE7B5'); if (p.set.tn[1] && p.momento === 'dia') a = a.lerp(new T.Color(p.set.tn[1]), 0.5);
    a.lerp(PAL.fun, 0.12); b.lerp(PAL.fun, 0.12);
    return (CEUS[k] = textura((x) => { const gr = x.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, '#' + a.getHexString()); gr.addColorStop(0.75, '#' + b.getHexString()); gr.addColorStop(1, '#' + b.getHexString()); x.fillStyle = gr; x.fillRect(0, 0, 4, 256); }, 4, 256)); };
  const luzes = (p) => { const noite = p.momento === 'noite' || p.s.cenario === 'espaco', interno = p.set.interno;
    hemi.color.set(noite ? 0x8fa7d8 : 0xffffff); hemi.groundColor.copy(PAL.fun); hemi.intensity = interno ? 1.45 : (noite ? 0.75 : 1.35);
    sol.color.set(noite ? (interno ? 0xffe2b0 : 0xbfd0ff) : (p.momento === 'tarde' ? 0xffb070 : 0xfff2d8)); sol.intensity = noite ? (interno ? 1.5 : 1.0) : (p.s.clima ? 1.2 : 2.3);
    sol.position.set(-4, 9, 5); sol.target.position.set(0, 0, 0); estrelas.visible = noite && !interno && persp; };
  const climaEm = (p, t) => { const c = p.s.clima, area = 10; chuva.visible = c === 'chuva' && !p.set.interno; neve.visible = c === 'neve' && !p.set.interno; if (!chuva.visible && !neve.visible) return; const q = rng(77), cx = cam.position.x * 0.3;
    for (let i = 0; i < NCH; i++) { const x = cx + (q() - 0.5) * area * 1.6, z = (q() - 0.5) * area * 0.7 + 0.5, o = q() * 6;
      if (chuva.visible) { const y = 6 - ((t * 9 + o) % 6.2); chP.set([x, y, z, x - 0.04, y + 0.32, z], i * 6); } else { const y = 6 - ((t * 0.8 + o) % 6.2); neP.set([x + Math.sin(t + o) * 0.25, y, z], i * 3); } }
    chuvaG.attributes.position.needsUpdate = true; neveG.attributes.position.needsUpdate = true; };

  // ---- transições: um véu sobre a arte (cor do estilo), calculado do tempo ------------------------------------------
  const veu = document.getElementById('transicao3d');
  // onde o painel entra deslizando depois do vídeo em tela cheia (artes/curta.py: montagem): ali a entrada já é a transição,
  // então o véu do plano não passa (somava as duas) e o painel já chega mostrando o plano novo
  const TR = (M.montagem || {}).trechos || [], ENTRADAS = TR.filter((x, k) => k > 0 && x.tela === 'dividida' && TR[k - 1].tela === 'video').map((x) => x.t0);
  const naEntrada = (tb) => ENTRADAS.some((e) => Math.abs(tb - e) < 0.6);
  const transicao = (t) => { let op = 0, clip = 'none', fundo = FUN;
    for (let i = 0; i < PL.length; i++) { const p = PL[i], tb = p.s.t0, tr = p.s.transicao; if (Math.abs(t - tb) > 0.4 || naEntrada(tb)) continue;
      if (tr === 'fade' || (i === 0 && tr !== 'corte')) { const k = t < tb ? liso((t - (tb - 0.3)) / 0.3) : 1 - liso((t - tb) / 0.35); if (i === 0) op = Math.max(op, t < tb ? 1 : 1 - liso((t - tb) / 0.4)); else op = Math.max(op, k); }
      // cortina só entre planos de verdade: nunca colada no começo do clip (somava com o fade de entrada e deixava uma faixa
      // da cor do estilo na lateral) nem num plano curto demais; e sem a fresta de 1% no começo e no fim da passada
      else if (tr === 'cortina' && i > 0 && tb >= 0.9 && p.s.t1 - tb >= 0.8) { const k = t < tb ? liso((t - (tb - 0.28)) / 0.28) : liso((t - tb) / 0.3);
        if ((t < tb && k > 0.02) || (t >= tb && k < 0.98)) { fundo = '#' + PAL.pri.getHexString(); op = 1; clip = t < tb ? `inset(0 ${((1 - k) * 100).toFixed(1)}% 0 0)` : `inset(0 0 0 ${(k * 100).toFixed(1)}%)`; } }
      else if (tr === 'zoom' && i > 0 && t >= tb) { fundo = '#FFFFFF'; op = Math.max(op, 0.75 * (1 - liso((t - tb) / 0.3))); } }
    veu.style.opacity = op.toFixed(3); veu.style.background = fundo; veu.style.clipPath = clip; };

  // ---- destaque: o momento forte (número ou palavra dita) toma a tela inteira por 1 a 2 s ------------------------------
  // O FFmpeg mostra esta camada sozinha nesses intervalos (artes/curta.py: montagem); o número sobe contando até o valor dito.
  const caixaDq = document.getElementById('destaques3d');
  const NUMERO = /^(R\$\s?)?(\d+(?:[.,]\d+)?)(\s?%|\s.*)?$/i;
  const DQ = ((M.montagem || {}).destaques || []).map((d) => { const el = document.createElement('div'); el.className = 'destaque3' + (PIX ? ' pixel' : '');
    el.innerHTML = '<div class="dq-grade"></div><div class="dq-txt"></div><div class="dq-barra"></div><div class="dq-sub"></div>';
    const txt = el.querySelector('.dq-txt'); if (caixaDq) caixaDq.appendChild(el);
    // o destaque ocupa a largura da tela: mede com o texto final e ajusta o corpo (no máximo 16% da altura)
    const LW = document.body.clientWidth || W, LH = document.body.clientHeight || H; txt.textContent = d.texto; txt.style.whiteSpace = 'nowrap'; txt.style.fontSize = '200px';
    const larg = txt.scrollWidth || 1, fs = Math.min(LH * 0.16, 200 * LW * 0.86 / larg); txt.style.fontSize = `${fs.toFixed(0)}px`;
    el.querySelector('.dq-sub').style.fontSize = `${Math.max(LW * 0.045, Math.min(fs * 0.32, LW * 0.07)).toFixed(0)}px`;
    return { d, el, txt, grade: el.querySelector('.dq-grade'), barra: el.querySelector('.dq-barra'), sub: el.querySelector('.dq-sub'), num: NUMERO.exec(d.texto) }; });
  const destaqueEm = (t) => DQ.forEach((q) => { const d = q.d, on = t >= d.t0 && t < d.t1; q.el.style.opacity = on ? '1' : '0'; if (!on) return;
    const u = t - d.t0, k = liso(u / 0.2), pop = 1 + Math.exp(-8 * u) * Math.sin(u * 20) * 0.1 * (0.5 + amort);
    const passo = PIX ? (x) => Math.round(x * 6) / 6 : (x) => x;
    q.txt.style.transform = `translateY(${((1 - k) * 60 * esc).toFixed(1)}px) scale(${(passo(0.55 + 0.45 * k) * pop).toFixed(4)})`;
    if (q.num && u < 0.55) { const s = q.num[2], dec = (s.split(/[.,]/)[1] || '').length, v = parseFloat(s.replace(',', '.')) * liso(u / 0.55);
      q.txt.textContent = (q.num[1] || '') + v.toFixed(dec).replace('.', s.includes(',') ? ',' : '.') + (q.num[3] || ''); } else q.txt.textContent = d.texto;
    q.barra.style.transform = `scaleX(${liso((u - 0.15) / 0.3).toFixed(3)})`;
    const ws = (d.sub || '').split(' ').filter(Boolean); q.sub.textContent = ws.slice(0, Math.ceil(clamp((u - 0.3) / 0.45) * ws.length)).join(' ');
    q.grade.style.transform = `scale(${(1 + u * 0.04).toFixed(4)})`; });

  // ---- imagem real do que a fala cita (foto da pessoa, logo da empresa, foto do produto), no painel da arte -----------
  // Entra quando o nome é dito, com o nome certo e uma linha de contexto do Wikidata; o crédito da imagem fica no canto.
  const REFS = ((M.montagem || {}).referencias || []).map((r) => { const el = document.createElement('div'); el.className = 'real3' + (PIX ? ' pixel' : '') + (r.logo ? ' logo' : '');
    const tam = Math.min(F.w * 0.72, F.h * 0.64); el.style.width = `${(tam / 0.62 * 0.7).toFixed(0)}px`;
    el.innerHTML = `<div class="rl-moldura" style="height:${tam.toFixed(0)}px"><img src="${r.src}" alt=""></div><div class="rl-nome"></div><div class="rl-ctx"></div><div class="rl-cred"></div>`;
    el.querySelector('.rl-nome').textContent = r.nome || r.termo; el.querySelector('.rl-ctx').textContent = r.contexto || ''; el.querySelector('.rl-cred').textContent = r.credito ? `imagem: ${r.credito}` : '';
    camada.appendChild(el); const w = el.offsetWidth || tam, h = el.offsetHeight || tam * 1.4;
    const s = Math.min(1, (F.h * 0.94) / Math.max(1, h)); return { r, el, w, h, s }; });
  const realEm = (t) => REFS.forEach((q, k) => { const r = q.r, u = t - r.t0, on = t >= r.t0 && t < r.t1; if (!on) { q.el.style.opacity = '0'; return; }
    const ent = liso(u / 0.28), sai = 1 - liso((t - (r.t1 - 0.25)) / 0.25), pop = 1 + Math.exp(-7 * u) * Math.sin(u * 16) * 0.06 * (0.5 + amort);
    const lado = k % 2 ? 1 : -1, x = FX - q.w / 2 + lado * (1 - ent) * F.w * 0.35, y = FY - q.h / 2 + (1 - ent) * 30 * esc;
    q.el.style.opacity = Math.min(ent * 1.6, sai).toFixed(3);
    q.el.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) rotate(${(lado * (2.2 - 1.6 * ent)).toFixed(2)}deg) scale(${(q.s * (0.9 + 0.1 * ent) * pop).toFixed(4)})`; });

  // ---- um quadro --------------------------------------------------------------------------------------------------
  const planoEm = (t) => { const e = ENTRADAS.find((x) => t >= x - 0.35 && t < x); if (e !== undefined) t = e; let k = 0; for (let i = 0; i < PL.length; i++) if (PL[i].s.t0 <= t + 1e-4) k = i; return PL[k]; };
  let ativo = null;
  const desenhar = (t) => {
    const p = planoEm(t), s = p.s, u = Math.max(0, t - s.t0), dur = Math.max(0.5, s.t1 - s.t0);
    if (ativo !== p) { Object.values(SETS).forEach((x) => { x.g.visible = false; }); PL.forEach((q) => { q.extra.visible = false; }); p.set.g.visible = true; p.extra.visible = true; ativo = p; }
    // montagem do lugar novo
    const ini = p.novo ? s.t0 : -1e9; p.set.filhos.forEach((o, k) => { if (!o.userData.e) o.userData.e = o.scale.clone(); const q = liso((t - ini - (k / Math.max(1, p.set.filhos.length)) * montagem * 0.7) / Math.max(0.15, montagem * 0.35)); const b = Math.exp(-6 * q) * Math.sin(q * 12) * 0.12 * amort * (q > 0.5 ? 1 : 0); o.scale.set(o.userData.e.x, o.userData.e.y * Math.max(0.001, q + b), o.userData.e.z); });
    const a = p.set.a; AGUAS.forEach((tx) => { tx.offset.x = -(t * agua_v * 0.15) % 1; tx.offset.y = (t * agua_v * 0.05) % 1; });
    if (a.esteira) a.esteira.forEach((m, k) => { m.position.x = -3.5 + ((k * 1.2 + t * 0.8) % 7.2); }); if (a.engrenagem) a.engrenagem.rotation.y = t * 1.5; if (a.barco) { a.barco.position.y = Math.sin(t * 1.6) * 0.06; a.barco.rotation.z = Math.sin(t * 1.3) * 0.04; }
    if (a.faixas) a.faixas.forEach((m, k) => { m.position.x = -12 + ((k * 1.4 - t * 3) % 24 + 24) % 24; }); if (a.carro) a.carro.position.x = -1.6 + Math.sin(t * 0.5) * 0.15; if (a.focos) a.focos.forEach((f, k) => { f.rotation.z = Math.sin(t * 1.1 + k * 2) * 0.35; });
    if (a.frascos) a.frascos.forEach((f, k) => { f.scale.y = 1 + 0.06 * Math.sin(t * 3 + k); }); if (a.planeta) a.planeta.rotation.z = t * 0.2; if (a.aviao) a.aviao.position.y = 0.85 + Math.sin(t * 0.8) * 0.03;
    // personagens
    const cp = new T.Vector3(); p.bs.forEach((b, k) => { const pos = posDo(b, t, s); b.g.position.copy(pos); const ac = b.acao; pose(b, ac, u, t + k * 0.37, dur);
      let ry = 0; if (ac === 'andar' || ac === 'correr') ry = Math.PI / 2 - 0.5; else if (s.situacao === 'conversa' && p.bs.length > 1) ry = k === 0 ? 0.9 : -0.9; b.g.rotation.y = ry + (persp ? p.az0 * (ac === 'andar' || ac === 'correr' ? 0.3 : 1) : VIS.az * 0.5);
      if (b.g.rotation.x === 0 && ac === 'dormir') b.g.rotation.x = -Math.PI / 2; });
    (s.multi || []).forEach((b, k) => { pose(b, k % 3 === 0 ? 'comemorar' : (k % 3 === 1 ? 'pular' : 'parado'), u, t + b.fase, dur); });
    p.objs.forEach((o) => { const q = liso((t - o.t) / 0.35), bq = Math.exp(-6 * q) * Math.sin(q * 12) * 0.2 * amort * (q > 0.5 ? 1 : 0); o.g.visible = q > 0; o.g.scale.setScalar(Math.max(0.001, 0.75 * (q + bq))); o.g.rotation.y = Math.sin(t * 0.8) * 0.2; });
    if (p.rota) p.rota.geometry.setDrawRange(0, Math.floor(p.rota.geometry.index.count * clamp(u / dur) / 3) * 3);
    luzes(p); camDo(p, t); p.ef(t, u); climaEm(p, t);
    cena.background = ceu(p);
    PL.forEach((q) => { if (!q.placa) return; const on = q === p ? liso((t - q.primeiro) / 0.25) * (1 - liso((t - (q.s.t1 - 0.2)) / 0.2)) : 0; q.placa.style.opacity = on.toFixed(3); });
    transicao(t); destaqueEm(t); realEm(t); r.render(cena, cam); };

  desenhar(0);
  let atual = 0;
  const tl = { duration: () => M.duracao, totalDuration: () => M.duracao, paused: () => true, pause: () => tl, play: () => tl,
    time: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)), totalTime: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)),
    seek: (v) => (atual = v, desenhar(v), tl), progress: (v) => (v === undefined ? atual / M.duracao : (atual = v * M.duracao, desenhar(atual), tl)) };
  window.__timelines = window.__timelines || {}; window.__timelines['clipator-curta3d'] = tl;
  const rel = document.getElementById('relogio3d');
  const laco = () => { const v = parseFloat(getComputedStyle(rel).getPropertyValue('--t3')); if (!isNaN(v)) desenhar(v); requestAnimationFrame(laco); };
  requestAnimationFrame(laco);
})();
