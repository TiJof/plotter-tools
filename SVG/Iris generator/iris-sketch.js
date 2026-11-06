/* =====================================================================
   IRIS GENERATOR — p5.js → SVG
   ---------------------------------------------------------------------
   Run it:  paste into https://editor.p5js.org  (sketch.js)  and press ▶
   Output:  a live SVG preview + a "Download SVG" button.

   How it works
   • p5.js provides the seeded randomness, Perlin noise and the control panel.
   • The SVG is written directly as clean, named layers (#iris-base,
     #fibres-main, #collarette, #pupil …) so it opens nicely in
     Inkscape / Illustrator / Figma.
   • EVERY setting lives in SCHEMA below. Add / remove / retune a line and the
     control panel updates by itself.  PRESETS at the bottom are just
     overrides of the defaults.
   ===================================================================== */

// ---------------------------------------------------------------------
// 1. SETTINGS  [key, label, type, default, min|options, max, step]
// ---------------------------------------------------------------------
const fibreSection = (title, k, d) => ({ title, params: [
  [k + 'Count',   'Count',         'range', d.count, 0, 3000, 10],
  [k + 'Width',   'Width',         'range', d.width, 0.5, 60, 0.1],
  [k + 'Length',  'Length',        'range', d.length, 0.05, 1, 0.01],
  [k + 'Start',   'Start spread',  'range', d.start, 0, 1, 0.01],
  [k + 'Taper',   'Taper',         'range', d.taper, 0, 1, 0.01],
  [k + 'Wander',  'Waviness',      'range', d.wander, 0, 1.5, 0.01],
  [k + 'ColorA',  'Color A',       'color', d.a],
  [k + 'ColorB',  'Color B',       'color', d.b],
  [k + 'Jitter',  'Color jitter',  'range', d.jitter, 0, 1, 0.01],
  [k + 'Opacity', 'Opacity',       'range', d.opacity, 0, 1, 0.01],
  [k + 'Blur',    'Blur',          'range', d.blur, 0, 20, 0.1],
]});

const SCHEMA = [
  { title: 'General', params: [
    ['seed',       'Seed',               'range', 7, 0, 9999, 1],
    ['size',       'Output size (px)',   'range', 800, 200, 2400, 10],
    ['bgMode',     'Background',         'select', 'transparent', ['transparent', 'solid']],
    ['bgColor',    'Background color',   'color', '#0d0d12'],
    ['noiseScale', 'Fibre noise scale',  'range', 1.5, 0.2, 8, 0.1],
    ['grain',      'Grain amount',       'range', 0.25, 0, 1, 0.01],
    ['grainScale', 'Grain size',         'range', 0.9, 0.1, 2, 0.05],
    ['fibreDetail','Fibre smoothness',   'range', 7, 3, 14, 1],
  ]},
  { title: 'Iris — shape & base colors', params: [
    ['irisW',      'Half-width',         'range', 400, 100, 480, 1],
    ['irisH',      'Half-height',        'range', 400, 100, 480, 1],
    ['irisRot',    'Rotation (°)',       'range', 0, -90, 90, 1],
    ['irisSquare', 'Squareness',         'range', 2, 1.2, 5, 0.05],
    ['irisIrreg',  'Edge irregularity',  'range', 0.015, 0, 0.12, 0.001],
    ['colInner',   'Inner color',        'color', '#b07a2c'],
    ['colMid',     'Middle color',       'color', '#6d7a35'],
    ['colOuter',   'Outer color',        'color', '#3d5645'],
    ['midPos',     'Middle position',    'range', 0.55, 0.1, 0.95, 0.01],
  ]},
  { title: 'Pupil & pupillary ruff', params: [
    ['pupilW',      'Half-width',        'range', 105, 5, 400, 1],
    ['pupilH',      'Half-height',       'range', 105, 5, 400, 1],
    ['pupilRot',    'Rotation (°)',      'range', 0, -90, 90, 1],
    ['pupilSquare', 'Squareness',        'range', 2, 1.2, 5, 0.05],
    ['pupilIrreg',  'Irregularity',      'range', 0.02, 0, 0.2, 0.001],
    ['pupilColor',  'Color',             'color', '#050505'],
    ['pupilBlur',   'Edge softness',     'range', 1, 0, 20, 0.1],
    ['ruffWidth',   'Ruff width',        'range', 9, 0, 40, 0.5],
    ['ruffColor',   'Ruff color',        'color', '#2a1a0a'],
    ['ruffOpacity', 'Ruff opacity',      'range', 0.7, 0, 1, 0.01],
    ['ruffShadow',  'Shadow opacity',    'range', 0.6, 0, 1, 0.01],
    ['ruffGlow',    'Shadow spread',     'range', 16, 0, 60, 0.5],
  ]},
  fibreSection('Fibres — deep (dark, soft)',   'deep', { count: 120, width: 26,  length: 0.9,  start: 0.15, taper: 0.5, wander: 0.30, a: '#2a1a0a', b: '#6d7a35', jitter: 0.25, opacity: 0.35, blur: 6 }),
  fibreSection('Fibres — main (body color)',   'main', { count: 520, width: 7,   length: 0.8,  start: 0.35, taper: 0.6, wander: 0.22, a: '#d29a40', b: '#7d9150', jitter: 0.30, opacity: 0.55, blur: 0.6 }),
  fibreSection('Fibres — fine (light detail)', 'fine', { count: 900, width: 2.2, length: 0.55, start: 0.8,  taper: 0.7, wander: 0.18, a: '#f1deaa', b: '#d29a40', jitter: 0.35, opacity: 0.45, blur: 0 }),
  { title: 'Collarette & pupillary zone', params: [
    ['collT',       'Position',          'range', 0.36, 0.1, 0.9, 0.01],
    ['collAmp',     'Zigzag depth',      'range', 0.045, 0, 0.3, 0.005],
    ['collTeeth',   'Zigzag teeth',      'range', 22, 3, 80, 1],
    ['collWidth',   'Line width',        'range', 2.5, 0, 20, 0.1],
    ['collColor',   'Line color',        'color', '#2a1a0a'],
    ['collOpacity', 'Line opacity',      'range', 0.5, 0, 1, 0.01],
    ['collBlur',    'Line blur',         'range', 1, 0, 15, 0.1],
    ['zoneColor',   'Zone color',        'color', '#c28a2e'],
    ['zoneOpacity', 'Zone opacity',      'range', 0.4, 0, 1, 0.01],
    ['zoneBlur',    'Zone blur',         'range', 5, 0, 30, 0.1],
  ]},
  { title: 'Crypts (dark almond pits)', params: [
    ['cryptCount',   'Count',            'range', 26, 0, 120, 1],
    ['cryptT',       'Position',         'range', 0.5, 0.05, 0.95, 0.01],
    ['cryptSpread',  'Spread',           'range', 0.2, 0, 0.5, 0.01],
    ['cryptSize',    'Length',           'range', 26, 4, 120, 1],
    ['cryptWidth',   'Width / length',   'range', 0.35, 0.05, 1, 0.01],
    ['cryptTangent', 'Sideways tilt',    'range', 0.15, 0, 1, 0.01],
    ['cryptColor',   'Color',            'color', '#2a1a0a'],
    ['cryptOpacity', 'Opacity',          'range', 0.5, 0, 1, 0.01],
    ['cryptBlur',    'Blur',             'range', 1.5, 0, 15, 0.1],
  ]},
  { title: 'Contraction furrows (arcs)', params: [
    ['furrowCount',   'Count',           'range', 5, 0, 40, 1],
    ['furrowT',       'Position',        'range', 0.8, 0.1, 0.97, 0.01],
    ['furrowSpread',  'Spread',          'range', 0.12, 0, 0.5, 0.01],
    ['furrowSpan',    'Arc length (rad)','range', 1.4, 0.2, 6, 0.05],
    ['furrowWidth',   'Width',           'range', 2.2, 0.3, 20, 0.1],
    ['furrowColor',   'Color',           'color', '#2a1a0a'],
    ['furrowOpacity', 'Opacity',         'range', 0.28, 0, 1, 0.01],
    ['furrowBlur',    'Blur',            'range', 1.2, 0, 15, 0.1],
  ]},
  { title: 'Pigment spots (freckles)', params: [
    ['spotCount',   'Count',             'range', 14, 0, 150, 1],
    ['spotT',       'Position',          'range', 0.55, 0.05, 0.95, 0.01],
    ['spotSpread',  'Spread',            'range', 0.4, 0, 0.5, 0.01],
    ['spotMin',     'Min size',          'range', 3, 0.5, 40, 0.5],
    ['spotMax',     'Max size',          'range', 11, 0.5, 60, 0.5],
    ['spotColor',   'Color',             'color', '#5a3410'],
    ['spotOpacity', 'Opacity',           'range', 0.5, 0, 1, 0.01],
    ['spotBlur',    'Blur',              'range', 1.5, 0, 15, 0.1],
  ]},
  { title: 'Limbal ring (outer edge)', params: [
    ['limbalWidth',   'Fade width',      'range', 0.22, 0.01, 0.8, 0.01],
    ['limbalColor',   'Color',           'color', '#1c1a10'],
    ['limbalOpacity', 'Opacity',         'range', 0.85, 0, 1, 0.01],
    ['limbalEdge',    'Hard edge (px)',  'range', 3, 0, 30, 0.5],
  ]},
  { title: 'Highlight (reflection)', params: [
    ['hlShape',   'Shape',               'select', 'window', ['window', 'round', 'none']],
    ['hlX',       'X position',          'range', -0.3, -0.9, 0.9, 0.01],
    ['hlY',       'Y position',          'range', -0.32, -0.9, 0.9, 0.01],
    ['hlSize',    'Size',                'range', 80, 10, 300, 1],
    ['hlColor',   'Color',               'color', '#ffffff'],
    ['hlOpacity', 'Opacity',             'range', 0.85, 0, 1, 0.01],
    ['hlBlur',    'Blur',                'range', 1.5, 0, 30, 0.1],
  ]},
];

const DEFAULTS = {};
SCHEMA.forEach(s => s.params.forEach(p => (DEFAULTS[p[0]] = p[3])));

// ---------------------------------------------------------------------
// 2. PRESETS (anything not listed falls back to DEFAULTS = "Hazel")
// ---------------------------------------------------------------------
const pal = c => ({
  colInner: c.inner, colMid: c.mid, colOuter: c.outer,
  deepColorA: c.dark, deepColorB: c.mid,
  mainColorA: c.warm, mainColorB: c.cool,
  fineColorA: c.light, fineColorB: c.warm,
  zoneColor: c.zone, collColor: c.dark, ruffColor: c.dark, cryptColor: c.dark,
  furrowColor: c.dark, limbalColor: c.limb, spotColor: c.spot,
});

const PRESETS = {
  Hazel: {},
  Blue: pal({ inner: '#8fb3d1', mid: '#3f78ad', outer: '#1f4a7a', dark: '#0d2238', warm: '#a9cbe4', cool: '#2d6aa3', light: '#e8f3fb', zone: '#a9bfcf', limb: '#0b1a2b', spot: '#6b4a2a' }),
  Green: pal({ inner: '#a8a23c', mid: '#4f8a4a', outer: '#27553f', dark: '#10261a', warm: '#9ab85a', cool: '#3f8a63', light: '#e2f0b8', zone: '#b0a43e', limb: '#0f2018', spot: '#5a4a1a' }),
  'Dark brown': pal({ inner: '#6a3f1a', mid: '#4a2a12', outer: '#2b170a', dark: '#120804', warm: '#8a5524', cool: '#5a3516', light: '#c58a4a', zone: '#7a4a1e', limb: '#0a0503', spot: '#1c0e05' }),
  Grey: pal({ inner: '#aab3b8', mid: '#6f7b83', outer: '#3f4c55', dark: '#1b2328', warm: '#b5bec2', cool: '#5d6b75', light: '#eef2f4', zone: '#aab3b6', limb: '#12181c', spot: '#4a4a4a' }),
  'Cat (slit)': Object.assign(pal({ inner: '#e6cf3a', mid: '#a9b82c', outer: '#4a6a22', dark: '#1d2a0a', warm: '#e0c040', cool: '#7fa02a', light: '#f7f0a8', zone: '#e8d040', limb: '#141a08', spot: '#5a4a10' }),
    { irisW: 430, irisH: 390, pupilW: 28, pupilH: 250, pupilSquare: 1.6, hlShape: 'round', hlSize: 60, zoneOpacity: 0.25 }),
  'Goat (bar)': Object.assign(pal({ inner: '#e0a21a', mid: '#c98a12', outer: '#7a5a10', dark: '#2a1a05', warm: '#f0b830', cool: '#a8700e', light: '#fbe9a0', zone: '#e8b020', limb: '#1c1405', spot: '#5a3a08' }),
    { pupilW: 240, pupilH: 52, pupilSquare: 3.2, irisW: 420, irisH: 400, hlShape: 'round', hlSize: 50 }),
};

// ---------------------------------------------------------------------
// 3. GEOMETRY + SVG BUILDER
// ---------------------------------------------------------------------
const f  = n => Math.round(n * 10) / 10;
const f2 = n => Math.round(n * 100) / 100;
const clampN = (v, a, b) => Math.min(b, Math.max(a, v));
const lerpN = (a, b, t) => a + (b - a) * t;
// Builds a string from n calls of fn(i). Uses Array.from instead of a `for` loop on purpose:
// the p5 editor's infinite-loop protection times every `for` and cuts it off after ~100 ms,
// which long fibre loops can exceed (slow machine, first run, big counts).
const times = (n, fn) => Array.from({ length: Math.max(0, Math.floor(n)) }, (_, i) => fn(i)).join('');

const hex2rgb = h => { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const rgb2hex = (r, g, b) => '#' + [r, g, b].map(v => clampN(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('');
const mixHex = (a, b, t) => { const A = hex2rgb(a), B = hex2rgb(b); return rgb2hex(...A.map((v, i) => lerpN(v, B[i], t))); };
function jitterColor(hex, amt) {
  const k = 1 + random(-1, 1) * amt * 0.45;           // shared brightness shift
  return rgb2hex(...hex2rgb(hex).map(v => v * k * (1 + random(-1, 1) * amt * 0.12)));
}

// Superellipse outline with noisy edge: returns radius along direction `th`.
function makeShape(w, h, rot, n, irreg, so) {
  const c = Math.cos(rot), s = Math.sin(rot);
  return th => {
    const x = Math.cos(th), y = Math.sin(th);
    const lx = x * c + y * s, ly = -x * s + y * c;
    const r = Math.pow(Math.pow(Math.abs(lx) / w, n) + Math.pow(Math.abs(ly) / h, n), -1 / n);
    const wob = (noise(x * 1.5 + so, y * 1.5 + so) - 0.5) * 2 + (noise(x * 4 + so, y * 4 + so) - 0.5);
    return r * (1 + irreg * wob);
  };
}

// Each layer has its own random stream (seed + id) and is cached on only the settings that
// shape it. So: changing colour/blur/opacity-of-a-group never rebuilds geometry (fast sliders),
// and changing one layer never reshuffles another.
const GEO = ['seed', 'irisW', 'irisH', 'irisRot', 'irisSquare', 'irisIrreg', 'pupilW', 'pupilH', 'pupilRot', 'pupilSquare', 'pupilIrreg'];
const memo = {};
function layer(c, name, id, keys, build) {
  const key = GEO.concat(keys).map(k => c[k]).join('|');
  if (!memo[name] || memo[name].key !== key) {
    randomSeed(c.seed * 97 + id);
    memo[name] = { key, val: build() };
  }
  return memo[name].val;
}

function generateSVG(c) {
  noiseSeed(c.seed);

  const V = Math.max(c.irisW, c.irisH) * 1.12;          // half-extent of the viewBox
  const defs = [];
  let fid = 0;
  const blur = sd => {                                   // registers a blur filter, returns the attribute
    if (sd < 0.05) return '';
    const id = 'blur' + fid++;
    defs.push(`<filter id="${id}" filterUnits="userSpaceOnUse" x="${f(-V)}" y="${f(-V)}" width="${f(2 * V)}" height="${f(2 * V)}"><feGaussianBlur stdDeviation="${sd}"/></filter>`);
    return ` filter="url(#${id})"`;
  };

  // --- shapes: P(angle, t) → point; t = 0 at pupil edge, 1 at iris edge
  const iris  = makeShape(c.irisW, c.irisH, c.irisRot * Math.PI / 180, c.irisSquare, c.irisIrreg, 10);
  const pup0  = makeShape(c.pupilW, c.pupilH, c.pupilRot * Math.PI / 180, c.pupilSquare, c.pupilIrreg, 30);
  const pupil = th => Math.min(pup0(th), iris(th) * 0.92);
  const P = (th, t) => { const r = lerpN(pupil(th), iris(th), t); return [Math.cos(th) * r, Math.sin(th) * r]; };
  const ring = (t, steps = 120) => {
    let d = '';
    for (let i = 0; i < steps; i++) { const p = P(i / steps * TAU, t); d += (i ? 'L' : 'M') + f(p[0]) + ' ' + f(p[1]); }
    return d + 'Z';
  };
  const irisD = ring(1), pupilD = ring(0);

  // --- fibres: tapered, curved, noise-driven strands from pupil to limbus
  const fibres = (k, id) => layer(c, 'fibres-' + k, id, ['noiseScale', 'fibreDetail'].concat(
    ['Count', 'Width', 'Length', 'Start', 'Taper', 'Wander', 'ColorA', 'ColorB', 'Jitter', 'Opacity'].map(s => k + s)), () => {
    const n = c[k + 'Count'];
    if (!n) return '';
    const S = Math.max(3, Math.round(c.fibreDetail)), ns = c.noiseScale, w0 = c[k + 'Width'], tp = c[k + 'Taper'], wd = c[k + 'Wander'], oz = random(100);
    return times(n, () => {
      const th = random(TAU), t0 = random() * c[k + 'Start'];
      const t1 = Math.min(1.05, t0 + c[k + 'Length'] * random(0.5, 1));
      const bias = random(-1, 1) * wd * 0.5, w = w0 * random(0.6, 1.4), pts = [];
      for (let j = 0; j < S; j++) {
        const s = j / (S - 1);
        const a = th + (noise(Math.cos(th) * ns + 20, Math.sin(th) * ns + 20, s * ns * 0.7 + oz) - 0.5) * 4 * wd + bias * s;
        pts.push(P(a, lerpN(t0, t1, s)));
      }
      const L = [], R = [];
      for (let j = 0; j < S; j++) {
        const a = pts[Math.max(0, j - 1)], b = pts[Math.min(S - 1, j + 1)];
        const dx = b[0] - a[0], dy = b[1] - a[1], d = Math.hypot(dx, dy) || 1;
        const hw = w * (1 - tp * j / (S - 1)) / 2, nx = -dy / d * hw, ny = dx / d * hw;
        L.push(f(pts[j][0] + nx) + ' ' + f(pts[j][1] + ny));
        R.push(f(pts[j][0] - nx) + ' ' + f(pts[j][1] - ny));
      }
      const col = jitterColor(mixHex(c[k + 'ColorA'], c[k + 'ColorB'], random()), c[k + 'Jitter']);
      return `<path fill="${col}" fill-opacity="${f2(c[k + 'Opacity'] * random(0.5, 1))}" d="M${L.join('L')}L${R.reverse().join('L')}Z"/>`;
    });
  });

  // --- collarette (zigzag ring) + pupillary zone fill
  const collD = layer(c, 'coll', 4, ['collT', 'collAmp', 'collTeeth'], () => {
  const teeth = Math.max(3, Math.round(c.collTeeth)), cp = [];
  for (let i = 0; i < teeth * 2; i++) {
    const th = (i + random(-0.25, 0.25)) / (teeth * 2) * TAU;
    const t = c.collT + (i % 2 ? 1 : -1) * c.collAmp * random(0.5, 1.2) + (noise(Math.cos(th) * 2 + 40, Math.sin(th) * 2 + 40) - 0.5) * 0.08;
    cp.push(P(th, clampN(t, 0.02, 0.98)));
  }
  return 'M' + cp.map(p => f(p[0]) + ' ' + f(p[1])).join('L') + 'Z';
  });

  // --- crypts
  const crypts = layer(c, 'crypts', 5, ['cryptCount', 'cryptT', 'cryptSpread', 'cryptSize', 'cryptWidth', 'cryptTangent'], () => times(c.cryptCount, () => {
    const th = random(TAU), t = clampN(c.cryptT + random(-1, 1) * c.cryptSpread, 0.03, 0.97), p = P(th, t);
    const a = th + c.cryptTangent * Math.PI / 2 + random(-0.35, 0.35);
    const len = c.cryptSize * random(0.5, 1.3), wid = len * c.cryptWidth;
    const ux = Math.cos(a) * len / 2, uy = Math.sin(a) * len / 2, vx = -Math.sin(a) * wid, vy = Math.cos(a) * wid;
    return `<path d="M${f(p[0] - ux)} ${f(p[1] - uy)}Q${f(p[0] + vx)} ${f(p[1] + vy)} ${f(p[0] + ux)} ${f(p[1] + uy)}Q${f(p[0] - vx)} ${f(p[1] - vy)} ${f(p[0] - ux)} ${f(p[1] - uy)}Z"/>`;
  }));

  // --- contraction furrows
  const furrows = layer(c, 'furrows', 6, ['furrowCount', 'furrowT', 'furrowSpread', 'furrowSpan', 'furrowWidth'], () => times(c.furrowCount, i => {
    const t0 = clampN(c.furrowT + random(-1, 1) * c.furrowSpread, 0.05, 0.97), span = c.furrowSpan * random(0.4, 1.2), th0 = random(TAU);
    const steps = Math.max(4, Math.ceil(span / 0.06));
    let d = '';
    for (let j = 0; j <= steps; j++) {
      const s = j / steps, p = P(th0 + (s - 0.5) * span, clampN(t0 + (noise(i * 3.1 + s * 2, 50) - 0.5) * 0.05, 0.02, 1));
      d += (j ? 'L' : 'M') + f(p[0]) + ' ' + f(p[1]);
    }
    return `<path d="${d}" stroke-width="${f(c.furrowWidth * random(0.6, 1.4))}"/>`;
  }));

  // --- pigment spots
  const spots = layer(c, 'spots', 7, ['spotCount', 'spotT', 'spotSpread', 'spotMin', 'spotMax'], () => times(c.spotCount, () => {
    const p = P(random(TAU), clampN(c.spotT + random(-1, 1) * c.spotSpread, 0.03, 0.97));
    const rx = random(c.spotMin, Math.max(c.spotMin, c.spotMax)), ry = rx * random(0.55, 1);
    return `<ellipse cx="${f(p[0])}" cy="${f(p[1])}" rx="${f(rx)}" ry="${f(ry)}" transform="rotate(${f(random(360))} ${f(p[0])} ${f(p[1])})"/>`;
  }));

  // --- highlight
  let hl = '';
  if (c.hlShape !== 'none' && c.hlOpacity > 0) {
    const cx = c.hlX * c.irisW, cy = c.hlY * c.irisH, S = c.hlSize;
    let shape = '';
    if (c.hlShape === 'round') shape = `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(S / 2)}"/>`;
    else {
      const g = S * 0.07, p = (S - g) / 2;
      for (let i = 0; i < 2; i++) {
        for (let j = 0; j < 2; j++) {
          shape += `<rect x="${f(cx - S / 2 + i * (p + g))}" y="${f(cy - S / 2 + j * (p + g))}" width="${f(p)}" height="${f(p)}" rx="${f(p * 0.22)}"/>`;
        }
      }
    }
    hl = `<g id="highlight" fill="${c.hlColor}" fill-opacity="${c.hlOpacity}"${blur(c.hlBlur)}>${shape}</g>`;
  }

  // --- gradients, clip, grain
  const pr = clampN(Math.sqrt(c.pupilW * c.pupilH) / Math.sqrt(c.irisW * c.irisH), 0, 0.8);
  defs.push(`<radialGradient id="base"><stop offset="0" stop-color="${c.colInner}"/><stop offset="${f2(pr)}" stop-color="${c.colInner}"/><stop offset="${f2(Math.max(c.midPos, pr + 0.02))}" stop-color="${c.colMid}"/><stop offset="1" stop-color="${c.colOuter}"/></radialGradient>`);
  const lw = clampN(c.limbalWidth, 0.01, 0.9);
  defs.push(`<radialGradient id="limbal"><stop offset="${f2(1 - lw)}" stop-color="${c.limbalColor}" stop-opacity="0"/><stop offset="${f2(1 - lw * 0.4)}" stop-color="${c.limbalColor}" stop-opacity="${f2(c.limbalOpacity * 0.3)}"/><stop offset="1" stop-color="${c.limbalColor}" stop-opacity="${c.limbalOpacity}"/></radialGradient>`);
  defs.push(`<clipPath id="irisClip"><path d="${irisD}"/></clipPath>`);

  let grain = '';
  if (c.grain > 0) {
    defs.push(`<filter id="grain" color-interpolation-filters="sRGB" filterUnits="userSpaceOnUse" x="${f(-V)}" y="${f(-V)}" width="${f(2 * V)}" height="${f(2 * V)}"><feTurbulence type="fractalNoise" baseFrequency="${c.grainScale}" numOctaves="2" seed="${c.seed}"/><feColorMatrix type="matrix" values="0.33 0.33 0.33 0 0 0.33 0.33 0.33 0 0 0.33 0.33 0.33 0 0 0 0 0 0 1"/></filter>`);
    grain = `<rect id="grain" x="${f(-V)}" y="${f(-V)}" width="${f(2 * V)}" height="${f(2 * V)}" filter="url(#grain)" opacity="${c.grain}" style="mix-blend-mode:overlay"/>`;
  }

  // --- assemble (back → front). `defs` is read last, after every blur() call.
  const body =
    (c.bgMode === 'solid' ? `<rect id="background" x="${f(-V)}" y="${f(-V)}" width="${f(2 * V)}" height="${f(2 * V)}" fill="${c.bgColor}"/>` : '') +
    `<g id="iris" clip-path="url(#irisClip)">` +
      `<path id="iris-base" d="${irisD}" fill="url(#base)"/>` +
      `<g id="fibres-deep"${blur(c.deepBlur)}>${fibres('deep', 1)}</g>` +
      `<g id="fibres-main"${blur(c.mainBlur)}>${fibres('main', 2)}</g>` +
      `<path id="pupillary-zone" d="${collD}${pupilD}" fill-rule="evenodd" fill="${c.zoneColor}" fill-opacity="${c.zoneOpacity}"${blur(c.zoneBlur)}/>` +
      `<path id="collarette" d="${collD}" fill="none" stroke="${c.collColor}" stroke-width="${c.collWidth}" stroke-opacity="${c.collOpacity}" stroke-linejoin="round"${blur(c.collBlur)}/>` +
      `<g id="fibres-fine"${blur(c.fineBlur)}>${fibres('fine', 3)}</g>` +
      `<g id="crypts" fill="${c.cryptColor}" fill-opacity="${c.cryptOpacity}"${blur(c.cryptBlur)}>${crypts}</g>` +
      `<g id="furrows" fill="none" stroke="${c.furrowColor}" stroke-opacity="${c.furrowOpacity}" stroke-linecap="round" stroke-linejoin="round"${blur(c.furrowBlur)}>${furrows}</g>` +
      `<g id="spots" fill="${c.spotColor}" fill-opacity="${c.spotOpacity}"${blur(c.spotBlur)}>${spots}</g>` +
      grain +
      `<path id="limbal-ring" d="${irisD}" fill="url(#limbal)"/>` +
    `</g>` +
    (c.limbalEdge > 0 ? `<path id="limbal-edge" d="${irisD}" fill="none" stroke="${c.limbalColor}" stroke-opacity="${c.limbalOpacity}" stroke-width="${c.limbalEdge}"/>` : '') +
    `<g id="pupil">` +
      (c.ruffShadow > 0 ? `<path id="ruff-shadow" d="${pupilD}" fill="none" stroke="${c.ruffColor}" stroke-width="${f(c.ruffWidth * 2 + c.ruffGlow * 0.8)}" stroke-opacity="${c.ruffShadow}"${blur(c.ruffGlow)}/>` : '') +
      (c.ruffWidth > 0 ? `<path id="ruff" d="${pupilD}" fill="none" stroke="${c.ruffColor}" stroke-width="${f(c.ruffWidth * 2)}" stroke-opacity="${c.ruffOpacity}" stroke-linejoin="round"/>` : '') +
      `<path id="pupil-hole" d="${pupilD}" fill="${c.pupilColor}"${blur(c.pupilBlur)}/>` +
    `</g>` + hl;

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${c.size}" height="${c.size}" viewBox="${f(-V)} ${f(-V)} ${f(2 * V)} ${f(2 * V)}"><defs>${defs.join('')}</defs>${body}</svg>`;
}

// ---------------------------------------------------------------------
// 4. UI (built automatically from SCHEMA with p5 DOM)
// ---------------------------------------------------------------------
let cfg = {}, svgHolder, lastSVG = '', queued = false;
const setters = {};

const STYLE = `
html,body{margin:0;height:100%;background:#0e0e12;font:12px/1.3 system-ui,sans-serif}
#app{display:flex;height:100vh}
#stage{flex:1;min-width:0;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;
  background:conic-gradient(#1b1b22 25%,#15151a 0 50%,#1b1b22 0 75%,#15151a 0) 0 0/24px 24px}
#preview{width:100%;display:flex;justify-content:center}
#preview svg{width:min(100%,calc(100vh - 32px));height:auto;aspect-ratio:1}
#panel{width:340px;overflow-y:auto;background:#17171d;color:#d6d6dc;padding:0 12px 12px;box-sizing:border-box}
.bar{display:flex;flex-wrap:wrap;gap:6px;position:sticky;top:0;background:#17171d;padding:10px 0;z-index:2}
details{border-top:1px solid #2a2a33;padding:4px 0}
summary{cursor:pointer;font-weight:600;padding:6px 0}
.row{display:grid;grid-template-columns:104px 1fr 42px;align-items:center;gap:6px;margin:3px 0}
.val{text-align:right;color:#8a8a96;font-variant-numeric:tabular-nums}
input[type=range]{width:100%;margin:0}
input[type=color]{width:100%;height:22px;padding:0;border:0;background:none}
:focus-visible{outline:2px solid #7aa7ff;outline-offset:2px}
@media(max-width:760px){#app{flex-direction:column;height:auto;min-height:100vh}#stage{padding:8px}#preview svg{width:100%}#panel{width:100%}}
button,select{background:#262630;color:#ddd;border:1px solid #3a3a46;border-radius:6px;padding:4px 8px;font:inherit;cursor:pointer}
`;

function setup() {
  noCanvas();
  createElement('style', STYLE);
  const app = createDiv().id('app');
  const stage = createDiv().id('stage').parent(app);
  svgHolder = createDiv().id('preview').parent(stage);
  const panel = createDiv().id('panel').parent(app);

  const bar = createDiv().class('bar').parent(panel);
  const presetSel = createSelect().parent(bar);
  Object.keys(PRESETS).forEach(n => presetSel.option(n));
  presetSel.changed(() => loadPreset(presetSel.value()));
  createButton('New seed').parent(bar).mousePressed(() => setValue('seed', Math.floor(Math.random() * 10000)));
  createButton('Random colors').parent(bar).mousePressed(randomColors);
  createButton('Download SVG').parent(bar).mousePressed(downloadSVG);
  createButton('Copy settings').parent(bar).mousePressed(copySettings);
  createButton('Load settings').parent(bar).mousePressed(loadSettings);

  SCHEMA.forEach((sec, i) => {
    const det = createElement('details').parent(panel);
    if (i < 3) det.attribute('open', '');
    createElement('summary', sec.title).parent(det);
    sec.params.forEach(p => addControl(det, ...p));
  });

  loadPreset('Hazel');
}

function addControl(parent, key, label, type, def, a, b, step) {
  const row = createDiv().class('row').parent(parent);
  createSpan(label).parent(row);
  if (type === 'range') {
    const el = createSlider(a, b, def, step).parent(row);
    const out = createSpan('').class('val').parent(row);
    setters[key] = v => { el.value(v); out.html(String(v)); };
    el.input(() => { cfg[key] = Number(el.value()); out.html(String(cfg[key])); changed(); });
  } else if (type === 'color') {
    const el = createColorPicker(def).parent(row);
    setters[key] = v => el.value(v);
    el.input(() => { cfg[key] = el.value(); changed(); });
  } else {
    const el = createSelect().parent(row);
    a.forEach(o => el.option(o));
    setters[key] = v => el.selected(v);
    el.changed(() => { cfg[key] = el.value(); changed(); });
  }
}

function loadPreset(name) {
  const seed = cfg.seed;
  cfg = Object.assign({}, DEFAULTS, PRESETS[name]);
  if (seed !== undefined) cfg.seed = seed;
  Object.keys(cfg).forEach(k => setters[k] && setters[k](cfg[k]));
  render();
}
function setValue(key, v) { cfg[key] = v; setters[key](v); render(); }
function changed() { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; render(); }); }
function render() { lastSVG = generateSVG(cfg); svgHolder.html(lastSVG); }

function downloadSVG() {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lastSVG], { type: 'image/svg+xml' }));
  a.download = `iris-${cfg.seed}.svg`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// Copies only the values that differ from DEFAULTS — paste them into PRESETS to keep a look.
function copySettings() {
  const diff = {};
  Object.keys(cfg).forEach(k => { if (cfg[k] !== DEFAULTS[k]) diff[k] = cfg[k]; });
  const txt = JSON.stringify(diff, null, 2);
  console.log(txt);
  const fallback = () => prompt('Copy your settings (Ctrl/Cmd+C):', txt);
  if (navigator.clipboard) navigator.clipboard.writeText(txt).catch(fallback); else fallback();
}

function loadSettings() {
  const txt = prompt('Paste settings JSON:');
  if (!txt) return;
  try {
    Object.assign(cfg, JSON.parse(txt));
    Object.keys(cfg).forEach(k => setters[k] && setters[k](cfg[k]));
    render();
  } catch (e) { alert('That is not valid settings JSON.'); }
}

function hsl2hex(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const a = s * Math.min(l, 1 - l), k = n => (n + h / 30) % 12;
  const ch = n => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return rgb2hex(ch(0) * 255, ch(8) * 255, ch(4) * 255);
}

// New random palette: a main hue, with a warmer/shifted hue near the pupil.
function randomColors() {
  const h = Math.random() * 360, w = h + Math.random() * 70 - 35, col = hsl2hex;
  const p = pal({
    inner: col(w, 0.6, 0.55), mid: col(h, 0.5, 0.4), outer: col(h - 10, 0.5, 0.22), dark: col(h, 0.5, 0.08),
    warm: col(w, 0.55, 0.6), cool: col(h, 0.5, 0.35), light: col(w, 0.4, 0.88), zone: col(w, 0.55, 0.5),
    limb: col(h, 0.5, 0.06), spot: col(w, 0.6, 0.2),
  });
  Object.assign(cfg, p);
  Object.keys(p).forEach(k => setters[k](p[k]));
  render();
}
