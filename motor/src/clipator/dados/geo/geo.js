// Mapa do estilo Geo em Cena (Clipator, AGPL). Desenha os polígonos reais de window.GEO em canvas 2D, com o mesmo fator de escala
// nos dois eixos. Cada quadro é função do tempo: nada de relógio ou estado entre quadros, então buscar fora de ordem dá o mesmo
// quadro. A câmera enquadra dentro do retângulo livre do layout (M.geo.foco) e os rótulos nunca saem dele.
(function () {
  const M = window.GEO; if (!M || window.GEO3D) return; // com three.js e WebGL, quem desenha é o geo3d.js
  const cv = document.getElementById('geo2d'), g = cv.getContext('2d'), P = M.par || {};
  const W = cv.clientWidth, H = cv.clientHeight; cv.width = W; cv.height = H;
  const G = M.geo || { foco: { x: W * 0.05, y: H * 0.08, w: W * 0.9, h: H * 0.84 } };
  const F = G.foco, FX = F.x + F.w / 2, FY = F.y + F.h / 2, esc = M.geo ? Math.min(M.geo.largura, M.geo.altura) / 1080 : W / 1080;
  const css = getComputedStyle(document.documentElement), cor = (n) => css.getPropertyValue(n).trim() || '#888888';
  const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const mistura = (a, b, k) => { const x = rgb(a), y = rgb(b); return 'rgb(' + x.map((v, i) => Math.round(v + (y[i] - v) * k)).join(',') + ')'; };
  const alfa = (h, a) => 'rgba(' + rgb(h).join(',') + ',' + a + ')';
  const FUNDO = cor('--fundo'), TEXTO = cor('--texto'), PRIM = cor('--primaria'), DEST = cor('--destaque'), SUP = cor('--superficie');
  const TERRA = mistura(SUP, TEXTO, 0.14), BORDA = alfa(TEXTO, 0.42);
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), liso = (k) => { k = clamp(k); return k * k * (3 - 2 * k); };
  const MERC = P.projecao === 'mercator';
  const yDe = (lat) => { if (!MERC) return lat; const f = clamp(lat, -85, 85) * Math.PI / 180; return Math.asinh(Math.tan(f)) * 180 / Math.PI; };

  // ---- anéis: longitude contínua e y já projetado --------------------------------------------------------------------
  const anel = (a) => { const n = a.length / 2, x = new Float64Array(n), y = new Float64Array(n); let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (let i = 0; i < n; i++) { x[i] = a[2 * i]; y[i] = yDe(a[2 * i + 1]); x0 = Math.min(x0, x[i]); x1 = Math.max(x1, x[i]); y0 = Math.min(y0, y[i]); y1 = Math.max(y1, y[i]); }
    return { x, y, x0, x1, y0, y1 }; };
  const aneis = (l) => l.map(anel);
  const PAISES = M.paises.map((p) => ({ id: p.id, a: aneis(p.a) })), TUDO = PAISES.flatMap((p) => p.a);
  const PORPAIS = Object.fromEntries(PAISES.map((p) => [p.id, p.a]));
  const SUBS = Object.fromEntries(Object.entries(M.subdivisoes).map(([k, l]) => [k, l.map((s) => ({ id: s.id, a: aneis(s.a) }))]));
  const CONT = Object.fromEntries(Object.entries(M.continentes).map(([k, l]) => [k, aneis(l)]));
  const EV = M.eventos, alvo = (e) => (e.nivel === 'pais' ? PORPAIS[e.id] : e.nivel === 'continente' ? CONT[e.id] : (SUBS[e.pais].find((s) => s.id === e.id) || { a: [] }).a);

  // ---- câmera -------------------------------------------------------------------------------------------------------
  const giro = (d) => ((d + 180) % 360 + 360) % 360 - 180;
  const ajustar = (c, folga) => { const y0 = yDe(c[1]), y1 = yDe(c[3]), k = folga * (P.vizinhos || 1.4);
    // nunca mais que uma volta do mundo na tela
    return { cx: (c[0] + c[2]) / 2, cy: (y0 + y1) / 2, s: Math.max(W / 360, Math.min(F.w / (Math.max(c[2] - c[0], 0.6) * k), F.h / (Math.max(y1 - y0, 0.6) * k))) }; };
  const Q = M.quadros.map((q) => ({ t: q.t, cam: ajustar(q.c, 1) }));
  const INICIO = M.quadros.length ? ajustar(M.quadros[0].c, 2.6) : ajustar([-180, -58, 180, 85], 1 / (P.vizinhos || 1.4));
  const DUR = Math.max(0.05, P.aproximacao_s || 1.1);
  const camEm = (t) => { let c = INICIO;
    for (const q of Q) { if (q.t > t) break; const k = P.leve ? 1 : liso((t - q.t) / Math.max(0.25, Math.min(DUR, M.duracao - q.t - 0.15)));  // nome dito no fim do clip: a câmera chega antes de acabar
      c = { cx: c.cx + giro(q.cam.cx - c.cx) * k, cy: c.cy + (q.cam.cy - c.cy) * k, s: Math.exp(Math.log(c.s) + (Math.log(q.cam.s) - Math.log(c.s)) * k) }; }
    return c; };

  // ---- traçado: cada anel na volta do mundo em que aparece, sem esticar eixo nenhum --------------------------------------
  const tracar = (x, lista, c) => { const lo = c.cx - FX / c.s, hi = c.cx + (W - FX) / c.s, sul = c.cy - (H - FY) / c.s, norte = c.cy + FY / c.s;
    for (const r of lista) { if (r.y1 < sul || r.y0 > norte) continue;
      for (const k of [-360, 0, 360]) { if (r.x1 + k < lo || r.x0 + k > hi) continue;
        const n = r.x.length; let px = 1e9, py = 1e9;
        for (let i = 0; i < n; i++) { const a = FX + (r.x[i] + k - c.cx) * c.s, b = FY - (r.y[i] - c.cy) * c.s;
          if (i === 0) x.moveTo(a, b); else if (i === n - 1 || Math.abs(a - px) + Math.abs(b - py) > 0.7) x.lineTo(a, b); else continue;
          px = a; py = b; }
        x.closePath(); } } };
  const preencher = (x, lista, c, estilo) => { x.beginPath(); tracar(x, lista, c); x.fillStyle = estilo; x.fill('evenodd'); };
  const contornar = (lista, c, estilo, w) => { g.beginPath(); tracar(g, lista, c); g.strokeStyle = estilo; g.lineWidth = w; g.lineJoin = 'round'; g.stroke(); };
  const fora = document.createElement('canvas'); fora.width = W; fora.height = H; const o = fora.getContext('2d');
  const fino = 1.5 * esc * (P.escala_fronteiras || 1);

  const grade = (c) => { if (P.grade === false) return; const passo = [60, 30, 10, 5, 2, 1, 0.5].find((p) => p * c.s <= 260 * esc) || 0.5;
    g.strokeStyle = alfa(TEXTO, 0.07); g.lineWidth = Math.max(1, esc); g.beginPath();
    for (let v = Math.ceil((c.cx - FX / c.s) / passo) * passo; v <= c.cx + (W - FX) / c.s; v += passo) { const a = FX + (v - c.cx) * c.s; g.moveTo(a, 0); g.lineTo(a, H); }
    for (let v = -80; v <= 80; v += passo) { const b = FY - (yDe(v) - c.cy) * c.s; if (b >= 0 && b <= H) { g.moveTo(0, b); g.lineTo(W, b); } }
    g.stroke(); };
  const nivelDe = (e, t) => liso((t - e.t) / 0.35) * (1 - liso((t - e.tf) / 0.35));

  // ---- rótulos: âncora de texto, sempre dentro do retângulo livre -------------------------------------------------------
  const rot = document.getElementById('rotulos3d');
  const ROT = EV.map((e) => { const d = document.createElement('div'); d.className = 'rot3 foco'; const b = document.createElement('b'), s = document.createElement('small');
    b.textContent = e.nome; s.textContent = e.desc; d.append(b, s); d.style.opacity = 0; if (P.rotulos !== false) rot.appendChild(d); return d; });
  let credH = 0;
  if (P.credito !== false) { const d = document.createElement('div'); d.className = 'geo-credito'; d.textContent = 'Natural Earth · projeção ' + (MERC ? 'de Mercator' : 'equiretangular');
    rot.appendChild(d); credH = d.offsetHeight + 8 * esc; d.style.transform = `translate(${F.x}px,${F.y + F.h - d.offsetHeight}px)`; }
  const rotulos = (t, c) => { const postos = [], baixo = F.y + F.h - credH;
    EV.forEach((e, i) => { const k = nivelDe(e, t), d = ROT[i]; d.style.opacity = k; if (k <= 0.01 || P.rotulos === false) return;
      const ax = clamp(FX + giro(e.anc[0] - c.cx) * c.s, F.x + 12 * esc, F.x + F.w - 12 * esc), ay = clamp(FY - (yDe(e.anc[1]) - c.cy) * c.s, F.y + 12 * esc, baixo - 12 * esc);
      const w = d.offsetWidth, h = d.offsetHeight, vao = 46 * esc;
      const x = clamp(ax - w / 2, F.x, Math.max(F.x, F.x + F.w - w)); let y = ay - h - vao; if (y < F.y) y = ay + vao; y = clamp(y, F.y, Math.max(F.y, baixo - h));
      for (const p of postos) if (x < p.x + p.w && p.x < x + w && y < p.y + p.h + 8 * esc && p.y < y + h + 8 * esc) y = p.y + p.h + 10 * esc;
      y = clamp(y, F.y, Math.max(F.y, baixo - h)); postos.push({ x, y, w, h }); d.style.transform = `translate(${x}px,${y}px)`;
      g.globalAlpha = k; g.strokeStyle = TEXTO; g.lineWidth = 2.5 * esc; g.beginPath(); g.moveTo(ax, ay); g.lineTo(clamp(ax, x + 8, x + w - 8), y < ay ? y + h : y); g.stroke();
      g.fillStyle = TEXTO; g.beginPath(); g.arc(ax, ay, 6 * esc, 0, 7); g.fill(); g.globalAlpha = 1; }); };

  const desenhar = (t) => { const c = camEm(t);
    g.fillStyle = FUNDO; g.fillRect(0, 0, W, H); grade(c);
    preencher(g, TUDO, c, TERRA); contornar(TUDO, c, BORDA, fino);
    const ativos = EV.map((e) => [e, nivelDe(e, t)]).filter((x) => x[1] > 0);
    for (const pais of Object.keys(SUBS)) { const k = Math.max(0, ...EV.filter((e) => e.pais === pais).map((e) => nivelDe(e, t))); if (k <= 0) continue;
      const l = SUBS[pais].flatMap((s) => s.a); g.globalAlpha = k; preencher(g, l, c, mistura(TERRA, PRIM, 0.45)); contornar(l, c, alfa(TEXTO, 0.62), fino); g.globalAlpha = 1; }
    for (const [e, k] of ativos) { const l = alvo(e); g.globalAlpha = k;
      if (e.nivel === 'continente') { // grupos de ilhas incluem oceano: só a interseção com a terra acende
        o.globalCompositeOperation = 'source-over'; o.clearRect(0, 0, W, H); preencher(o, TUDO, c, DEST);
        o.globalCompositeOperation = 'destination-in'; preencher(o, l, c, '#000'); g.drawImage(fora, 0, 0);
      } else { preencher(g, l, c, DEST); contornar(l, c, mistura(DEST, TEXTO, 0.7), fino * 2); }
      g.globalAlpha = 1; }
    rotulos(t, c); };

  desenhar(0);
  let atual = 0;
  const tl = { duration: () => M.duracao, totalDuration: () => M.duracao, paused: () => true, pause: () => tl, play: () => tl,
    time: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)), totalTime: (v) => (v === undefined ? atual : (atual = v, desenhar(v), tl)),
    seek: (v) => (atual = v, desenhar(v), tl), progress: (v) => (v === undefined ? atual / M.duracao : (atual = v * M.duracao, desenhar(atual), tl)) };
  window.__timelines = window.__timelines || {}; window.__timelines['clipator-geo'] = tl;
  const rel = document.getElementById('relogio3d'); let visto = -1;
  const laco = () => { const v = parseFloat(getComputedStyle(rel).getPropertyValue('--t3')); if (!isNaN(v) && v !== visto) { visto = v; desenhar(v); } requestAnimationFrame(laco); };
  requestAnimationFrame(laco);
})();
