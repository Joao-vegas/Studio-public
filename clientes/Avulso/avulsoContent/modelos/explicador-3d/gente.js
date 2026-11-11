// Explicador 3D · gente "jogo antigo realista feio" (a cara do Loaded Dice): proporção humana (cabeça ~1/7), corpo
// low-poly de poucas faces, roupa com textura de pano, e o ROSTO pintado num canvas como uma FOTO meio esquisita colada
// na frente da cabeça (pele com poro e sombra, olho de verdade com íris e brilho, sobrancelha de fio, dente, ruga).
// Expressão exagerada: olho arregalado, sorrisão de dente, grito. O rosto nunca morfa: troca inteiro atrás de uma
// piscada (o motor faz). Parado = parado: nada respira nem balança.
// Mesma interface do Desenho 3D (criarPessoa, POSES, EXPRESSOES, toon): os planos dos dois formatos são intercambiáveis.
import * as THREE from 'three';

// ── material PBR com textura de sujeira/grão (o "toon" do desenho virou isto: o resto do motor continua chamando toon)
function semente(n) { let a = n >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const GRAO = (() => { const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'); const r = semente(7);
  g.fillStyle = '#e9e9e9'; g.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 9000; i++) { const v = 200 + Math.floor(r() * 55); g.fillStyle = `rgb(${v},${v},${v})`; g.fillRect(r() * 256, r() * 256, 1 + r() * 2, 1 + r() * 2); }
  for (let i = 0; i < 40; i++) { g.fillStyle = `rgba(90,80,70,${.008 + r() * .015})`; g.beginPath(); g.ellipse(r() * 256, r() * 256, 8 + r() * 30, 6 + r() * 20, r() * 3, 0, 7); g.fill(); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t; })();
const _mats = new Map();
export function toon(cor, extra = {}) {
  const k = cor + JSON.stringify(Object.keys(extra).filter(x => x !== 'map').map(x => [x, String(extra[x])]));
  if (!extra.map && _mats.has(k)) return _mats.get(k);
  const { gradientMap, ...resto } = extra;   // eslint-disable-line no-unused-vars
  const { grao, ...r2 } = resto;   // grão só quando pedido (em parede grande ele estica e vira mancha)
  const m = new THREE.MeshStandardMaterial({ color: cor, roughness: .74, metalness: .02, ...(grao ? { map: GRAO } : {}), ...r2, ...(extra.map ? { map: extra.map } : {}) });
  if (!extra.map) _mats.set(k, m);
  return m;
}
export const GRADIENTE = null;
const malha = (geo, m) => { const o = new THREE.Mesh(geo, typeof m === 'string' ? toon(m) : m); o.castShadow = true; o.receiveShadow = true; return o; };
const tom = (hex, f) => '#' + new THREE.Color(hex).multiplyScalar(f).getHexString();
function canvasTex(w, h, desenho) { const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); desenho(g, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; }

// ── pano: cor + trama + dobras (+ estampa); "frente" desenhada no meio da textura (u = .5 é a frente do corpo)
const _panos = new Map();
function pano(cor, op = {}) {
  const k = cor + JSON.stringify(op); if (_panos.has(k)) return _panos.get(k);
  const r = semente(op.semente || 3);
  const t = canvasTex(512, 512, (g, W, H) => {
    g.fillStyle = cor; g.fillRect(0, 0, W, H);
    for (let y = 0; y < H; y += 3) { g.fillStyle = `rgba(0,0,0,${.025 + r() * .03})`; g.fillRect(0, y, W, 1); }
    for (let x = 0; x < W; x += 3) { g.fillStyle = `rgba(255,255,255,${.015 + r() * .02})`; g.fillRect(x, 0, 1, H); }
    for (let i = 0; i < 14; i++) { const x = r() * W, y = r() * H; const gr = g.createLinearGradient(x - 30, y, x + 30, y + 80);
      gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(.5, 'rgba(0,0,0,.10)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr;
      g.beginPath(); g.ellipse(x, y, 10 + r() * 14, 50 + r() * 60, (r() - .5) * .6, 0, 7); g.fill(); }
    if (op.estampa === 'florida') { const cs = ['#f4d03f', '#e74c3c', '#ffffff', '#1abc9c', '#ff7ab8'];
      for (let i = 0; i < 70; i++) { g.fillStyle = cs[i % 5]; const x = r() * W, y = r() * H, rr = 6 + r() * 12;
        for (let p = 0; p < 5; p++) { g.beginPath(); g.ellipse(x + Math.cos(p * 1.26) * rr, y + Math.sin(p * 1.26) * rr, rr * .6, rr * .35, p * 1.26, 0, 7); g.fill(); }
        g.fillStyle = '#2e7d32'; g.beginPath(); g.ellipse(x + rr * 1.4, y + rr, rr * .9, rr * .3, .6, 0, 7); g.fill(); } }
    else if (op.estampa === 'xadrez') { g.fillStyle = 'rgba(0,0,0,.22)'; for (let i = 0; i < W; i += 32) { g.fillRect(i, 0, 12, H); g.fillRect(0, i, W, 12); } }
    else if (op.estampa === 'listra') { g.fillStyle = 'rgba(255,255,255,.4)'; for (let i = 0; i < H; i += 26) g.fillRect(0, i, W, 8); }
    else if (op.estampa) { g.fillStyle = op.estampa; g.beginPath(); g.arc(W * .5, H * .38, 40, 0, 7); g.fill(); }
    if (op.jaleco) {   // jaleco: abertura no meio, lapela, bolso com caneta, botões, bordado
      g.strokeStyle = 'rgba(60,70,80,.55)'; g.lineWidth = 3; g.beginPath(); g.moveTo(W * .5, H * .18); g.lineTo(W * .5, H); g.stroke();
      g.fillStyle = 'rgba(80,90,100,.18)'; g.beginPath(); g.moveTo(W * .5, H * .18); g.lineTo(W * .40, 0); g.lineTo(W * .46, 0); g.lineTo(W * .5, H * .12); g.fill();
      g.beginPath(); g.moveTo(W * .5, H * .18); g.lineTo(W * .60, 0); g.lineTo(W * .54, 0); g.lineTo(W * .5, H * .12); g.fill();
      if (op.cor2) { g.fillStyle = op.cor2; g.beginPath(); g.moveTo(W * .44, 0); g.lineTo(W * .5, H * .14); g.lineTo(W * .56, 0); g.fill(); }
      for (const y of [.32, .48, .64, .8]) { g.fillStyle = '#c9ced4'; g.beginPath(); g.arc(W * .52, H * y, 6, 0, 7); g.fill(); }
      g.strokeStyle = 'rgba(60,70,80,.4)'; g.lineWidth = 2; g.strokeRect(W * .58, H * .28, W * .08, H * .1);
      g.fillStyle = '#1e5fbf'; g.fillRect(W * .6, H * .22, 5, H * .09);
      g.fillStyle = 'rgba(30,90,140,.8)'; g.font = 'bold 16px Arial'; g.fillText('Dr.', W * .37, H * .3);
    }
    if (op.terno) { g.fillStyle = op.camisaCor || '#f2f2f2'; g.beginPath(); g.moveTo(W * .43, 0); g.lineTo(W * .5, H * .42); g.lineTo(W * .57, 0); g.fill();
      if (op.gravata) { g.fillStyle = op.gravata; g.beginPath(); g.moveTo(W * .485, H * .03); g.lineTo(W * .515, H * .03); g.lineTo(W * .525, H * .36); g.lineTo(W * .5, H * .42); g.lineTo(W * .475, H * .36); g.fill(); }
      g.strokeStyle = 'rgba(0,0,0,.4)'; g.lineWidth = 3; g.beginPath(); g.moveTo(W * .43, 0); g.lineTo(W * .5, H * .42); g.lineTo(W * .57, 0); g.stroke(); }
    else if (op.gravata) { g.fillStyle = op.gravata; g.beginPath(); g.moveTo(W * .485, H * .02); g.lineTo(W * .515, H * .02); g.lineTo(W * .528, H * .5); g.lineTo(W * .5, H * .56); g.lineTo(W * .472, H * .5); g.fill(); }
    if (op.abertura) { g.strokeStyle = 'rgba(60,70,80,.55)'; g.lineWidth = 3; g.beginPath(); g.moveTo(W * .5, 0); g.lineTo(W * .5, H); g.stroke();
      g.strokeStyle = 'rgba(60,70,80,.35)'; g.lineWidth = 2; g.strokeRect(W * .36, H * .2, W * .09, H * .16); }
    if (op.capuz) {   // moletom de capuz: bolso canguru, barra canelada e o "braço" do cordão
      g.fillStyle = 'rgba(0,0,0,.16)'; g.fillRect(0, H * .92, W, H * .08);
      g.strokeStyle = 'rgba(0,0,0,.45)'; g.lineWidth = 4; g.beginPath(); g.moveTo(W * .36, H * .62); g.lineTo(W * .64, H * .62);
      g.lineTo(W * .68, H * .9); g.lineTo(W * .32, H * .9); g.closePath(); g.stroke();
      g.fillStyle = 'rgba(0,0,0,.10)'; g.fill();
      g.strokeStyle = 'rgba(255,255,255,.7)'; g.lineWidth = 3; for (const x of [.47, .53]) { g.beginPath(); g.moveTo(W * x, H * .06); g.lineTo(W * x, H * .3); g.stroke(); } }
    if (op.ziper) { g.strokeStyle = '#9aa0a6'; g.lineWidth = 4; g.beginPath(); g.moveTo(W * .5, 0); g.lineTo(W * .5, H); g.stroke(); }
    if (op.gola) { g.fillStyle = 'rgba(0,0,0,.18)'; g.beginPath(); g.ellipse(W * .5, 0, W * .09, H * .06, 0, 0, 7); g.fill(); }
  });
  t.wrapS = THREE.RepeatWrapping;
  const m = new THREE.MeshStandardMaterial({ map: t, roughness: .88, metalness: 0 });
  _panos.set(k, m); return m;
}

// ── ROSTO pintado como foto: canvas 512x640 na calota da frente da cabeça. Olhos em y≈262, boca em y≈470.
const FACE = { phiL: Math.PI * .86, thS: Math.PI * .24, thL: Math.PI * .58 };
export const EXPRESSOES = {
  neutro:      { ab: 1, sob: [0, 0], boca: 'neutra' },
  feliz:       { ab: .8, sob: [-4, -2], boca: 'sorriso', boch: .6 },
  sorrisao:    { ab: .55, sob: [-10, -4], boca: 'sorrisao', boch: 1, rugaOlho: 1 },
  presuncoso:  { ab: .62, sob: [-14, 8], boca: 'presuncoso', torto: 1 },
  surpreso:    { ab: 1.5, sob: [-26, -6], boca: 'o', testa: 1 },
  panico:      { ab: 1.7, sob: [-22, -16], boca: 'grito', testa: 1, suor: 1, pupila: .55 },
  bravo:       { ab: .7, sob: [8, 22], boca: 'dentes', franze: 1 },
  triste:      { ab: .75, sob: [-6, -18], boca: 'triste', lagrima: 1 },
  tonto:       { ab: 1.15, sob: [-12, 0], boca: 'ondulada', vesgo: 1 },
  apaixonado:  { ab: 1.3, sob: [-20, -6], boca: 'sorrisao', boch: 1, brilho: 1, rubor: 1 },
  coracao:     { ab: 1.2, sob: [-18, -6], boca: 'sorriso', rubor: 1, brilho: 1 },
  desconfiado: { ab: .45, sob: [6, 10], boca: 'torta', torto: 1 },
  aliviado:    { ab: .2, sob: [-6, -12], boca: 'sorriso', suor: 1 },
  pensativo:   { ab: .85, sob: [-10, 6], boca: 'lado', olhar: [.6, .55], torto: 1 },
  preocupado:  { ab: 1.1, sob: [-12, -16], boca: 'ondulada', suor: 1, testa: 1 },
  decidido:    { ab: .8, sob: [4, 12], boca: 'sorriso' },
  falando:     { ab: 1, sob: [-4, 0], boca: 'aberta' },
  gritando:    { ab: 1.35, sob: [6, 20], boca: 'grito', franze: 1, testa: 0 },
  vendado:     { ab: 1, sob: [-10, -4], boca: 'sorriso' },
};

const CORES_OLHO = { castanho: '#5a3a22', azul: '#4a7fb0', verde: '#5d8a4a', escuro: '#2a1a10', mel: '#8a5a20' };
function pele(g, d, W, H, r) {
  const p = d.pele || '#d9a37e';
  g.fillStyle = p; g.fillRect(0, 0, W, H);
  // volume: luz na testa, maçãs e nariz; sombra nas bordas, embaixo do queixo e nas têmporas
  let gr = g.createRadialGradient(W * .5, H * .42, 40, W * .5, H * .48, W * .62);
  gr.addColorStop(0, 'rgba(255,240,225,.22)'); gr.addColorStop(.55, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(40,15,5,.42)'); g.fillStyle = gr; g.fillRect(0, 0, W, H);
  gr = g.createLinearGradient(0, H * .82, 0, H); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(40,15,5,.35)'); g.fillStyle = gr; g.fillRect(0, H * .82, W, H * .18);
  for (const x of [W * .3, W * .7]) { gr = g.createRadialGradient(x, H * .58, 5, x, H * .58, 70); gr.addColorStop(0, 'rgba(220,90,80,.16)'); gr.addColorStop(1, 'rgba(220,90,80,0)'); g.fillStyle = gr; g.fillRect(0, 0, W, H); }
  // poros e manchas (textura de foto barata)
  for (let i = 0; i < 9000; i++) { const a = .04 + r() * .09; g.fillStyle = r() < .55 ? `rgba(60,25,10,${a})` : `rgba(255,235,215,${a})`; g.fillRect(r() * W, r() * H, 1 + r() * 2.5, 1 + r() * 2.5); }
  for (let i = 0; i < 14; i++) { const x = r() * W, y = r() * H, rr = 12 + r() * 40; const gr = g.createRadialGradient(x, y, 1, x, y, rr);   // manchas: pele crua, foto barata
    gr.addColorStop(0, `rgba(${r() < .5 ? '170,60,50' : '90,50,25'},${.08 + r() * .1})`); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(x - rr, y - rr, rr * 2, rr * 2); }
  g.strokeStyle = 'rgba(70,30,18,.22)'; g.lineWidth = 2; for (const s of [-1, 1]) { g.beginPath(); g.moveTo(W * .5 + s * 46, H * .5); g.quadraticCurveTo(W * .5 + s * 80, H * .6, W * .5 + s * 70, H * .7); g.stroke(); }
  if (!d.mulher && d.barba !== 'nenhuma') { gr = g.createLinearGradient(0, H * .62, 0, H); gr.addColorStop(0, 'rgba(40,30,25,0)'); gr.addColorStop(1, `rgba(40,30,25,${d.barba === 'barbuda' ? .88 : d.barba ? .5 : .22})`);
    g.fillStyle = gr; g.beginPath(); g.ellipse(W * .5, H * .86, W * .36, H * .2, 0, 0, 7); g.fill();
    if (d.barba === 'barbuda') { gr = g.createLinearGradient(0, H * .5, 0, H * .8); gr.addColorStop(0, 'rgba(40,30,25,0)'); gr.addColorStop(1, 'rgba(40,30,25,.55)'); g.fillStyle = gr; g.beginPath(); g.ellipse(W * .5, H * .7, W * .4, H * .22, 0, 0, 7); g.fill(); }   // barbuda: sobe até a bochecha
    for (let i = 0; i < (d.barba === 'barbuda' ? 5200 : d.barba ? 2600 : 900); i++) { const a = r() * Math.PI, rr = r(); const x = W * .5 + Math.cos(a) * W * .34 * rr * 1.1, y = H * .74 + Math.sin(a) * H * .2 * rr;
      g.fillStyle = `rgba(30,20,15,${(d.barba === 'barbuda' ? .3 : .12) + r() * .2})`; g.fillRect(x, y, 1.5, 2.5); } }
  if (d.idade === 'velho') { g.strokeStyle = 'rgba(70,35,20,.28)'; g.lineWidth = 2;
    for (const s of [-1, 1]) { g.beginPath(); g.moveTo(W * .5 + s * 70, H * .55); g.quadraticCurveTo(W * .5 + s * 105, H * .66, W * .5 + s * 92, H * .78); g.stroke(); } }
}
function olho(g, x, y, e, lado, gz, d, forca, r) {
  const ab = forca === 'piscando' ? 0 : forca === 'meio-fechado' ? .38 : forca === 'nenhum' ? -1 : (e.ab ?? 1);
  if (ab < 0) return;
  const rx = 46, ry = 21 * Math.max(.06, ab);
  // cavidade e pálpebra (sombra)
  let gr = g.createRadialGradient(x, y - 4, 10, x, y, 70); gr.addColorStop(0, 'rgba(70,30,20,.25)'); gr.addColorStop(1, 'rgba(70,30,20,0)'); g.fillStyle = gr; g.fillRect(x - 80, y - 60, 160, 120);
  if (ab < .1) {   // fechado: linha de cílio curva
    g.strokeStyle = '#2a1810'; g.lineWidth = 4; g.beginPath(); g.moveTo(x - rx, y); g.quadraticCurveTo(x, y + 12, x + rx, y); g.stroke();
    g.strokeStyle = 'rgba(60,25,15,.4)'; g.lineWidth = 2; g.beginPath(); g.moveTo(x - rx + 4, y - 14); g.quadraticCurveTo(x, y - 6, x + rx - 4, y - 14); g.stroke(); return;
  }
  const forma = () => { g.beginPath(); g.moveTo(x - rx, y + 2); g.bezierCurveTo(x - rx * .5, y - ry * 1.5, x + rx * .45, y - ry * 1.55, x + rx, y - 1);
    g.bezierCurveTo(x + rx * .5, y + ry * 1.25, x - rx * .5, y + ry * 1.3, x - rx, y + 2); g.closePath(); };
  g.save(); forma(); g.clip();
  gr = g.createLinearGradient(x - rx, y, x + rx, y); gr.addColorStop(0, '#d9b8a8'); gr.addColorStop(.25, '#f6efe8'); gr.addColorStop(.75, '#f6efe8'); gr.addColorStop(1, '#d9b0a0');
  g.fillStyle = gr; g.fillRect(x - rx, y - 40, rx * 2, 80);
  const ir = 13.5 * (e.vesgo ? .95 : 1), ix = x + gz[0] * 16 + (e.vesgo ? -lado * 9 : 0), iy = y - gz[1] * 7;
  gr = g.createRadialGradient(ix, iy, 2, ix, iy, ir); const ci = CORES_OLHO[d.olhos] || CORES_OLHO.castanho;
  gr.addColorStop(0, tom(ci, .5)); gr.addColorStop(.45, ci); gr.addColorStop(.85, tom(ci, .75)); gr.addColorStop(1, '#1a0f08');
  g.fillStyle = gr; g.beginPath(); g.arc(ix, iy, ir, 0, 7); g.fill();
  g.strokeStyle = 'rgba(255,255,255,.12)'; g.lineWidth = 1; for (let k = 0; k < 18; k++) { const a = k / 18 * 6.283; g.beginPath(); g.moveTo(ix + Math.cos(a) * 5, iy + Math.sin(a) * 5); g.lineTo(ix + Math.cos(a) * ir * .9, iy + Math.sin(a) * ir * .9); g.stroke(); }
  g.fillStyle = '#080404'; g.beginPath(); g.arc(ix, iy, 6.2 * (e.pupila || 1), 0, 7); g.fill();
  g.fillStyle = 'rgba(255,255,255,.95)'; g.beginPath(); g.arc(ix - 5, iy - 6, 3.6, 0, 7); g.fill();
  if (e.brilho) { g.beginPath(); g.arc(ix + 5, iy + 3, 2.2, 0, 7); g.fill(); }
  gr = g.createLinearGradient(0, y - ry * 1.4, 0, y); gr.addColorStop(0, 'rgba(60,25,15,.45)'); gr.addColorStop(1, 'rgba(60,25,15,0)'); g.fillStyle = gr; g.fillRect(x - rx, y - 40, rx * 2, 40);
  g.restore();
  // cílio de cima grosso, pálpebra de baixo, vinco
  g.strokeStyle = '#1e120c'; g.lineWidth = 4.5; g.beginPath(); g.moveTo(x - rx, y + 2); g.bezierCurveTo(x - rx * .5, y - ry * 1.5, x + rx * .45, y - ry * 1.55, x + rx, y - 1); g.stroke();
  g.strokeStyle = 'rgba(90,40,30,.45)'; g.lineWidth = 2; g.beginPath(); g.moveTo(x - rx + 6, y + 4); g.bezierCurveTo(x - rx * .4, y + ry * 1.3 + 3, x + rx * .4, y + ry * 1.3 + 3, x + rx - 4, y + 2); g.stroke();
  g.strokeStyle = 'rgba(80,35,22,.35)'; g.lineWidth = 2.5; g.beginPath(); g.moveTo(x - rx * .85, y - ry * 1.2 - 10); g.quadraticCurveTo(x, y - ry * 1.8 - 14, x + rx * .85, y - ry * 1.2 - 12); g.stroke();
  // olheira
  gr = g.createLinearGradient(0, y + 8, 0, y + 34); gr.addColorStop(0, 'rgba(90,45,40,.22)'); gr.addColorStop(1, 'rgba(90,45,40,0)'); g.fillStyle = gr; g.beginPath(); g.ellipse(x, y + 20, rx * .8, 14, 0, 0, 7); g.fill();
  if (e.rugaOlho) { g.strokeStyle = 'rgba(80,35,22,.35)'; g.lineWidth = 2; for (let k = 0; k < 3; k++) { g.beginPath(); g.moveTo(x + lado * (rx + 4), y - 6 + k * 9); g.lineTo(x + lado * (rx + 22), y - 12 + k * 13); g.stroke(); } }
}
function sobrancelha(g, x, y, e, lado, cor, r) {
  const [sobe, inc] = e.sob || [0, 0];
  const pts = []; for (let k = 0; k <= 12; k++) { const u = k / 12; const px = x + lado * (-44 + u * 96); const curva = -Math.sin(u * Math.PI) * 10;
    const incl = (1 - u) * inc;   // inc > 0 desce a ponta de dentro (bravo); < 0 sobe a de dentro (triste)
    pts.push([px, y + sobe + curva + incl * .9 + (e.torto && lado > 0 ? -10 : 0)]); }
  g.lineCap = 'round';
  for (let k = 0; k < 160; k++) { const u = r(), i = Math.min(11, Math.floor(u * 12)), f = u * 12 - i;
    const px = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, py = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f + (r() - .5) * 12 * (1 - Math.abs(u - .35));
    g.strokeStyle = `rgba(${cor},${.35 + r() * .45})`; g.lineWidth = 1.6 + r() * 1.6; g.beginPath(); g.moveTo(px, py); g.lineTo(px + lado * (6 + r() * 6), py - 3 - r() * 4); g.stroke(); }
}
function nariz(g, W, H) {
  const x = W * .5, y = H * .58;
  let gr = g.createLinearGradient(x - 40, 0, x + 40, 0); gr.addColorStop(0, 'rgba(60,25,12,.0)'); gr.addColorStop(.3, 'rgba(60,25,12,.2)'); gr.addColorStop(.5, 'rgba(255,240,225,.18)');
  gr.addColorStop(.7, 'rgba(60,25,12,.22)'); gr.addColorStop(1, 'rgba(60,25,12,0)'); g.fillStyle = gr; g.beginPath(); g.moveTo(x - 14, H * .4); g.lineTo(x + 14, H * .4); g.lineTo(x + 40, y + 20); g.lineTo(x - 40, y + 20); g.fill();
  gr = g.createRadialGradient(x, y + 4, 4, x, y + 4, 34); gr.addColorStop(0, 'rgba(255,225,205,.35)'); gr.addColorStop(1, 'rgba(255,225,205,0)'); g.fillStyle = gr; g.beginPath(); g.arc(x, y + 4, 34, 0, 7); g.fill();
  g.fillStyle = 'rgba(40,12,8,.75)'; for (const s of [-1, 1]) { g.beginPath(); g.ellipse(x + s * 16, y + 24, 9, 5, s * .4, 0, 7); g.fill(); }
  g.strokeStyle = 'rgba(70,30,18,.35)'; g.lineWidth = 2.5; for (const s of [-1, 1]) { g.beginPath(); g.arc(x + s * 24, y + 14, 14, s > 0 ? -1.2 : Math.PI + 1.2 - 2.4, s > 0 ? 1.2 : Math.PI + 1.2); g.stroke(); }
}
function boca(g, W, H, e, d) {
  const x = W * .5, y = H * .735, tipo = e.boca;
  const labio = d.mulher ? '#b5505a' : tom(d.pele || '#d9a37e', .72);
  const escuro = '#2a0a0a', dente = '#f1ead8';
  const sulco = (k) => { g.strokeStyle = `rgba(80,35,20,${.25 + .25 * k})`; g.lineWidth = 3; for (const s of [-1, 1]) { g.beginPath(); g.moveTo(x + s * 50, H * .62); g.quadraticCurveTo(x + s * (78 + 18 * k), y - 10, x + s * (70 + 20 * k), y + 30); g.stroke(); } };
  const aberta = (path, cima = true, baixo = false, lingua = true) => {
    g.save(); g.beginPath(); path(); g.closePath(); g.fillStyle = escuro; g.fill(); g.clip();
    if (cima) { g.fillStyle = dente; g.fillRect(x - 120, y - 70, 240, 0); g.beginPath(); g.ellipse(x, y - 34, 70, 22, 0, 0, 7); g.fill();
      g.strokeStyle = 'rgba(120,100,80,.6)'; g.lineWidth = 1.5; for (let k = -4; k <= 4; k++) { g.beginPath(); g.moveTo(x + k * 15, y - 50); g.lineTo(x + k * 15.5, y - 16); g.stroke(); } }
    if (baixo) { g.fillStyle = tom(dente, .9); g.beginPath(); g.ellipse(x, y + 40, 60, 16, 0, 0, 7); g.fill(); }
    if (lingua) { const gr = g.createRadialGradient(x, y + 40, 4, x, y + 40, 50); gr.addColorStop(0, '#d0606a'); gr.addColorStop(1, '#7a2228'); g.fillStyle = gr; g.beginPath(); g.ellipse(x, y + 48, 44, 22, 0, 0, 7); g.fill(); }
    g.restore(); g.strokeStyle = labio; g.lineWidth = 9; g.beginPath(); path(); g.closePath(); g.stroke(); };
  const linha = (pts, larg = 6) => { g.strokeStyle = labio; g.lineWidth = larg; g.lineCap = 'round'; g.beginPath(); g.moveTo(...pts[0]); g.bezierCurveTo(...pts[1], ...pts[2], ...pts[3]); g.stroke();
    g.strokeStyle = 'rgba(40,10,8,.7)'; g.lineWidth = 2.5; g.stroke(); };
  switch (tipo) {
    case 'neutra': linha([[x - 46, y], [x - 15, y + 4], [x + 15, y + 4], [x + 46, y]], 10); break;
    case 'sorriso': sulco(.5); linha([[x - 60, y - 14], [x - 25, y + 20], [x + 25, y + 20], [x + 60, y - 14]], 10); break;
    case 'triste': linha([[x - 52, y + 16], [x - 20, y - 10], [x + 20, y - 10], [x + 52, y + 16]], 10); break;
    case 'torta': linha([[x - 44, y + 8], [x - 10, y + 6], [x + 20, y], [x + 46, y - 10]], 9); break;
    case 'lado': linha([[x - 20, y + 4], [x + 5, y + 8], [x + 30, y + 4], [x + 50, y - 10]], 9); break;
    case 'presuncoso': sulco(.4); linha([[x - 48, y + 6], [x, y + 16], [x + 30, y + 6], [x + 62, y - 24]], 10); break;
    case 'ondulada': g.strokeStyle = labio; g.lineWidth = 9; g.beginPath(); for (let i = 0; i <= 24; i++) g.lineTo(x - 52 + i * 4.3, y + Math.sin(i * .8) * 6); g.stroke(); break;
    case 'o': aberta(() => g.ellipse(x, y + 10, 28, 40, 0, 0, 7), false, false, true); break;
    case 'aberta': aberta(() => { g.moveTo(x - 54, y - 6); g.quadraticCurveTo(x, y - 18, x + 54, y - 6); g.quadraticCurveTo(x + 36, y + 46, x, y + 48); g.quadraticCurveTo(x - 36, y + 46, x - 54, y - 6); }, true); break;
    case 'sorrisao': sulco(1); aberta(() => { g.moveTo(x - 92, y - 30); g.quadraticCurveTo(x, y - 30, x + 92, y - 30); g.quadraticCurveTo(x + 70, y + 66, x, y + 70); g.quadraticCurveTo(x - 70, y + 66, x - 92, y - 30); }, true, true, false); break;
    case 'grito': sulco(.8); aberta(() => { g.moveTo(x - 64, y - 34); g.quadraticCurveTo(x, y - 50, x + 64, y - 34); g.quadraticCurveTo(x + 74, y + 92, x, y + 100); g.quadraticCurveTo(x - 74, y + 92, x - 64, y - 34); }, true, true, true); break;
    case 'dentes': { g.fillStyle = dente; g.beginPath(); g.roundRect(x - 62, y - 18, 124, 40, 14); g.fill(); g.strokeStyle = 'rgba(110,90,70,.6)'; g.lineWidth = 1.5;
      g.beginPath(); g.moveTo(x - 62, y + 2); g.lineTo(x + 62, y + 2); for (let k = -3; k <= 3; k++) { g.moveTo(x + k * 17, y - 18); g.lineTo(x + k * 17, y + 22); } g.stroke();
      g.strokeStyle = labio; g.lineWidth = 9; g.beginPath(); g.roundRect(x - 62, y - 18, 124, 40, 14); g.stroke(); sulco(.6); break; }
  }
}
function extras(g, W, H, e, r) {
  if (e.testa) { g.strokeStyle = 'rgba(80,35,20,.3)'; g.lineWidth = 2.5; for (let k = 0; k < 3; k++) { g.beginPath(); g.moveTo(W * .3, H * (.14 + k * .045)); g.quadraticCurveTo(W * .5, H * (.12 + k * .045), W * .7, H * (.14 + k * .045)); g.stroke(); } }
  if (e.franze) { g.strokeStyle = 'rgba(80,35,20,.4)'; g.lineWidth = 3; for (const s of [-1, 1]) { g.beginPath(); g.moveTo(W * .5 + s * 10, H * .3); g.lineTo(W * .5 + s * 14, H * .38); g.stroke(); } }
  if (e.rubor) for (const x of [W * .26, W * .74]) { const gr = g.createRadialGradient(x, H * .6, 4, x, H * .6, 60); gr.addColorStop(0, 'rgba(230,70,80,.35)'); gr.addColorStop(1, 'rgba(230,70,80,0)'); g.fillStyle = gr; g.fillRect(0, 0, W, H); }
  if (e.suor) for (const [x, y, s] of [[W * .82, H * .2, 1], [W * .2, H * .28, .7]]) { const gr = g.createRadialGradient(x - 3 * s, y - 4 * s, 1, x, y, 14 * s);
    gr.addColorStop(0, 'rgba(255,255,255,.95)'); gr.addColorStop(.4, 'rgba(200,225,240,.55)'); gr.addColorStop(1, 'rgba(120,150,170,.0)'); g.fillStyle = gr;
    g.beginPath(); g.moveTo(x, y - 22 * s); g.quadraticCurveTo(x + 14 * s, y + 4 * s, x, y + 14 * s); g.quadraticCurveTo(x - 14 * s, y + 4 * s, x, y - 22 * s); g.fill(); }
  if (e.lagrima) for (const x of [W * .33, W * .67]) { const gr = g.createLinearGradient(0, H * .44, 0, H * .66); gr.addColorStop(0, 'rgba(210,235,255,.85)'); gr.addColorStop(1, 'rgba(210,235,255,0)');
    g.fillStyle = gr; g.beginPath(); g.roundRect(x - 5, H * .44, 10, H * .2, 5); g.fill(); }
}
const _rostos = new Map();
export function texturaRosto(d, nome, olhoForca = null, olhar = null) {
  const e = { ...(EXPRESSOES[nome] || EXPRESSOES.neutro) };
  const gz = olhar || e.olhar || [0, 0];
  const k = `${d._id}|${nome}|${olhoForca}|${gz[0]},${gz[1]}`;
  if (_rostos.has(k)) return _rostos.get(k);
  const c = document.createElement('canvas'); c.width = 512; c.height = 640; const g = c.getContext('2d'); const W = 512, H = 640;
  const r = semente((d.semente || 1) * 7919 + 11);
  pele(g, d, W, H, r);
  const corSob = (() => { const cc = new THREE.Color(d.cabelo?.cor || '#3a2618').multiplyScalar(.8); return `${Math.round(cc.r * 255)},${Math.round(cc.g * 255)},${Math.round(cc.b * 255)}`; })();
  nariz(g, W, H);
  const ass = semente((d.semente || 1) * 31 + 3); const assim = [ass() * .3 - .05, ass() * 10 - 5, ass() * 14 - 7];   // assimetria fixa da pessoa (olho maior, olho mais baixo)
  const eF = { ...e, ab: (e.ab ?? 1) * (d.arregalado ?? 1.18) };
  for (const [x, lado] of [[W * .5 - 82, -1], [W * .5 + 82, 1]]) olho(g, x + (lado > 0 ? assim[2] : 0), H * .41 + (lado > 0 ? assim[1] : 0), lado > 0 ? { ...eF, ab: eF.ab * (1 + assim[0]) } : eF, lado, gz, d, e.olho || olhoForca || (nome === 'vendado' ? 'nenhum' : null), r);
  for (const [x, lado] of [[W * .5 - 84, -1], [W * .5 + 84, 1]]) sobrancelha(g, x, H * .325, e, lado, corSob, semente(lado + 5 + (d.semente || 1)));
  if (d.bigode) { g.fillStyle = d.cabelo?.cor || '#3a2618'; const grosso = d.bigode === 'grosso'; for (let i = 0; i < (grosso ? 1500 : 700); i++) { const u = r() * 2 - 1; const x = W * .5 + u * (grosso ? 82 : 66), y = H * .68 + Math.abs(u) * (grosso ? 16 : 10) + r() * (grosso ? 24 : 16);
    g.globalAlpha = (grosso ? .7 : .4) + r() * .5; g.fillRect(x, y, grosso ? 3 : 2, grosso ? 9 : 6); } g.globalAlpha = 1; }
  boca(g, W, H, e, d);
  extras(g, W, H, e, r);
  if (d.oculos) { g.strokeStyle = d.oculos === 'escuro' ? '#111' : '#2a2a2a'; g.lineWidth = 7;
    for (const s of [-1, 1]) { g.beginPath(); g.roundRect(W * .5 + s * 82 - 62, H * .41 - 40, 124, 82, 18); g.stroke();
      if (d.oculos === 'escuro') { g.fillStyle = 'rgba(10,10,15,.85)'; g.fill(); } }
    g.beginPath(); g.moveTo(W * .5 - 20, H * .4); g.quadraticCurveTo(W * .5, H * .38, W * .5 + 20, H * .4); g.stroke(); }
  // acabamento de "foto colada": leve desfoque e contraste, borda que some na cor da cabeça
  const c2 = document.createElement('canvas'); c2.width = W; c2.height = H; const g2 = c2.getContext('2d');
  g2.fillStyle = d.pele || '#d9a37e'; g2.fillRect(0, 0, W, H);
  g2.filter = 'blur(.6px) contrast(1.16) saturate(1.12)'; g2.translate(W / 2, H / 2); g2.rotate(((d.semente || 1) % 5 - 2) * .012); g2.translate(-W / 2, -H / 2); g2.drawImage(c, 0, 0); g2.setTransform(1, 0, 0, 1, 0, 0); g2.filter = 'none';
  const gr = g2.createRadialGradient(W * .5, H * .5, W * .36, W * .5, H * .5, W * .62); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(30,10,5,.25)'); g2.fillStyle = gr; g2.fillRect(0, 0, W, H);
  const t = new THREE.CanvasTexture(c2); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  _rostos.set(k, t); return t;
}

// ── cabelo low-poly (icosaedro facetado + textura de fio)
const _cab = new Map();
function matCabelo(cor) { if (_cab.has(cor)) return _cab.get(cor);
  const r = semente(9); const t = canvasTex(256, 256, (g, W, H) => { g.fillStyle = cor; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 1400; i++) { const x = r() * W, y = r() * H; g.strokeStyle = r() < .5 ? 'rgba(0,0,0,.25)' : 'rgba(255,255,255,.12)'; g.lineWidth = 1; g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - .5) * 6, y + 10 + r() * 20); g.stroke(); } });
  const m = new THREE.MeshStandardMaterial({ map: t, roughness: .65, flatShading: true }); _cab.set(cor, m); return m; }
function cabelo(cab, d, sx, sy, sz) {
  const c = d.cabelo || {}; const est = c.estilo || 'curto'; if (est === 'careca' && !d.bone) { return; }
  const m = matCabelo(c.cor || '#3a2618'); const g = new THREE.Group();
  const casca = (s = 1.06, corte = .46, y = 0, z = -.004) => { const geo = new THREE.SphereGeometry(1, 10, 7, 0, Math.PI * 2, 0, Math.PI * corte);
    const o = malha(geo, m); o.scale.set(sx * s, sy * s, sz * s * 1.02); o.position.set(0, y, z); o.rotation.x = -.32; return o; };
  if (est !== 'careca') g.add(casca(1.07, est === 'longo' ? .5 : .42, .006));
  if (est === 'topete') { const q = malha(new THREE.IcosahedronGeometry(1, 1), m); q.scale.set(sx * .8, sy * .35, sz * .5); q.position.set(0, sy * .82, sz * .45); g.add(q); }
  if (est === 'franja') { const q = malha(new THREE.IcosahedronGeometry(1, 1), m); q.scale.set(sx * .95, sy * .22, sz * .4); q.position.set(-sx * .1, sy * .62, sz * .62); q.rotation.z = .2; g.add(q); }
  if (est === 'espetado') for (let i = 0; i < 10; i++) { const a = i / 10 * Math.PI * 2; const p = malha(new THREE.ConeGeometry(sx * .2, sy * .55, 4), m);
    p.position.set(Math.cos(a) * sx * .45, sy * .9, Math.sin(a) * sz * .45); p.rotation.set(Math.sin(a) * .7, 0, -Math.cos(a) * .7); g.add(p); }
  if (est === 'coque') { const b = malha(new THREE.IcosahedronGeometry(sx * .42, 1), m); b.position.set(0, sy * 1.0, -sz * .45); g.add(b); }
  if (est === 'rabo') { const b = malha(new THREE.IcosahedronGeometry(1, 1), m); b.scale.set(sx * .3, sy * .75, sz * .3); b.position.set(0, -sy * .1, -sz * 1.05); b.rotation.x = .35; g.add(b); }
  if (est === 'longo') { const b = malha(new THREE.IcosahedronGeometry(1, 1), m); b.scale.set(sx * 1.12, sy * 1.25, sz * .55); b.position.set(0, -sy * .45, -sz * .55); g.add(b); }
  if (est === 'cacheado') for (let i = 0; i < 18; i++) { const a = i / 18 * Math.PI * 2, yy = sy * (.35 + (i % 3) * .2);
    const b = malha(new THREE.IcosahedronGeometry(sx * .32, 0), m); b.position.set(Math.cos(a) * sx * .78, yy, Math.sin(a) * sz * .78 - sz * .12); if (b.position.z > sz * .45) b.position.y += sy * .3; g.add(b); }
  if (d.bone) { const b = malha(new THREE.SphereGeometry(1, 12, 6, 0, Math.PI * 2, 0, Math.PI * .42), toon(d.bone)); b.scale.set(sx * 1.1, sy * 1.08, sz * 1.1); g.add(b);
    const aba = malha(new THREE.CylinderGeometry(sx * .7, sx * .7, .012, 12, 1, false, -Math.PI / 2, Math.PI), toon(d.bone)); aba.position.set(0, sy * .55, sz * .8); aba.rotation.x = .1; g.add(aba); }
  cab.add(g);
}

// ── POSES dos braços: [frente, abre, cotovelo, torção] em graus (E = esquerdo do personagem, D = direito). Mesmas do Desenho 3D.
export const POSES = {
  neutro:   { E: [0, 7, 10, 0], D: [0, 7, 10, 0] },
  aponta:   { E: [0, 7, 10, 0], D: [82, 12, 4, 0] },
  aponta_e: { E: [82, 12, 4, 0], D: [0, 7, 10, 0] },
  mostra:   { E: [32, 38, 38, 0], D: [32, 38, 38, 0] },
  mostra_d: { E: [0, 7, 10, 0], D: [40, 42, 30, 0] },
  pensa:    { E: [28, -14, 92, 0], D: [52, -24, 138, 0] },
  comemora: { E: [168, 26, 24, 0], D: [168, 26, 24, 0] },
  punho:    { E: [0, 7, 10, 0], D: [160, 18, 40, 0] },
  panico:   { E: [150, 44, 140, 0], D: [150, 44, 140, 0] },
  ombros:   { E: [22, 54, 84, 0], D: [22, 54, 84, 0] },
  cruzado:  { E: [52, -18, 116, 0], D: [46, -26, 112, 0] },
  celular:  { E: [44, -12, 88, 0], D: [60, -8, 92, 0] },
  celular1: { E: [0, 7, 10, 0], D: [58, -10, 100, 0] },
  megafone: { E: [56, -22, 74, 0], D: [86, -8, 70, 0] },
  vara:     { E: [58, -6, 44, 0], D: [50, -18, 52, 0] },
  grita:    { E: [72, -28, 118, 0], D: [72, -28, 118, 0] },
  acena:    { E: [0, 7, 10, 0], D: [150, 34, 46, 0] },
  digita:   { E: [48, -10, 52, 0], D: [48, -10, 52, 0] },
  segura:   { E: [50, -4, 40, 0], D: [50, -4, 40, 0] },
  maos_rosto:{ E: [124, -8, 152, 0], D: [124, -8, 152, 0] },
  apoia:    { E: [0, 7, 10, 0], D: [60, 30, 120, 0] },
  orbita:   { E: [10, 20, 30, 0], D: [10, 20, 30, 0] },
};

// ── tronco: lathe de 8 lados (silhueta de jogo antigo) com o perfil de gente
function tronco(perfil, alt, larg, prof, m, seg = 8) {
  const pts = perfil.map(([y, rr]) => new THREE.Vector2(Math.max(.002, rr * larg), y * alt));
  const geo = new THREE.LatheGeometry(pts, seg); geo.rotateY(Math.PI); geo.scale(1, 1, prof);
  return malha(geo, m);
}
function membro(r1, r2, h, m, seg = 7) { const g = new THREE.CylinderGeometry(r1, r2, h, seg); g.translate(0, -h / 2, 0); return malha(g, m); }

let _n = 0;
export function criarPessoa(d) {
  d._id = d._id || `p${++_n}`;
  d.semente = d.semente || _n;
  const A = .985 * (d.alt || 1), L = d.larg || 1, gordo = d.corpo === 'gordo' ? 1.3 : d.corpo === 'forte' ? 1.12 : d.corpo === 'magro' ? .9 : 1;
  const mulher = !!d.mulher || ['saia'].includes(d.calca?.tipo) || ['coque', 'rabo', 'longo'].includes(d.cabelo?.estilo);
  d.mulher = mulher;
  const raiz = new THREE.Group();
  const pe = new THREE.MeshStandardMaterial({ color: d.pele || '#d9a37e', roughness: .58 });
  const ct = d.camisa || {}, cl = d.calca || {};
  const jaleco = ct.tipo === 'jaleco', terno = ct.tipo === 'terno' || (ct.gravata && !jaleco && ct.tipo !== 'camisa_gravata');
  const camisa = pano(ct.cor || '#3a6ea5', { estampa: ct.estampa, jaleco, cor2: ct.cor2, terno, gravata: ct.gravata, camisaCor: ct.cor3, ziper: ct.tipo === 'moletom' && !ct.capuz, capuz: ct.tipo === 'moletom' && !!ct.capuz, gola: ct.tipo === 'gola' || !!ct.gola, semente: d.semente });
  const calca = pano(cl.cor || '#2b3550', { estampa: cl.estampa, semente: d.semente + 1 });
  const QUAD = .86 * A, COXA = .43 * A, CANELA = .40 * A, TR = .52 * A;
  const rnd = semente((d.semente || 1) * 97 + 1); const TORTO = { ombro: (rnd() - .5) * .03, cab: (rnd() - .5) * 10, incl: 2 + rnd() * 3 };   // desengonçado fixo (não balança)
  // pernas: quadril → joelho → pé
  const pernas = [];
  const curta = cl.tipo === 'bermuda' || cl.tipo === 'saia';
  for (const s of [-1, 1]) {
    const q = new THREE.Group(); q.position.set(s * .095 * L * gordo, QUAD, 0);
    q.add(membro(.075 * gordo, .058, COXA, cl.tipo === 'saia' ? pe : calca));
    if (cl.tipo === 'bermuda') { const b = membro(.085 * gordo, .07, COXA * .55, calca); q.add(b); }
    const j = new THREE.Group(); j.position.y = -COXA; q.add(j);
    j.add(membro(.055, .042, CANELA, curta ? pe : calca));
    const sap = malha(new THREE.BoxGeometry(.1, .075, .25), toon(d.sapato || '#1d1f27', { roughness: .45 })); sap.position.set(0, -CANELA - .02, .05); j.add(sap);
    raiz.add(q); pernas.push({ q, j });
  }
  // pelve + tronco (8 lados) + saia
  const corpo = new THREE.Group(); corpo.position.y = QUAD; raiz.add(corpo);
  const bacia = tronco([[-.12, .0], [-.1, .2], [0, .21], [.09, .2]], 1, L * gordo, .7, calca); corpo.add(bacia);
  const perfil = [[.06, .19 * gordo], [.22, .2 * gordo * (mulher ? .92 : 1)], [.42, .2 * (mulher ? 1.02 : 1.06)], [.6, .21 * (mulher ? .95 : 1.08)], [.8, .21 * (mulher ? .9 : 1.05)], [.94, .16], [1.0, .07]];
  const peito = tronco(perfil, TR, L, .62, camisa); corpo.add(peito);
  if (jaleco) { const aba = tronco([[-.38, .245 * gordo], [-.1, .235 * gordo], [.12, .215 * gordo]], 1, L, .74, pano(ct.cor || '#eef2f5', { abertura: true, semente: d.semente })); corpo.add(aba); }
  if (cl.tipo === 'saia') { const sa = tronco([[-.4, .25], [-.15, .22], [.05, .2]], 1, L * gordo, .7, calca); corpo.add(sa); }
  const pescoco = membro(.048, .056, .1 * A, pe, 8); pescoco.position.y = TR + .075 * A; corpo.add(pescoco);
  const capuz = ct.tipo === 'moletom' && !!ct.capuz;
  if (capuz) {   // capuz caído: rolo grosso em volta do pescoço + o saco nas costas
    const mc = toon(tom(ct.cor || '#3a6ea5', .86), { roughness: .9 });
    const rolo = malha(new THREE.TorusGeometry(.088, .036, 8, 18), mc); rolo.rotation.x = Math.PI / 2; rolo.position.y = TR + .0; corpo.add(rolo);
    const saco = malha(new THREE.SphereGeometry(1, 10, 8), mc); saco.scale.set(.1, .085, .05); saco.position.set(0, TR - .05 * A, -.1 * L); corpo.add(saco);
  }
  if (ct.tipo === 'gola') {   // gola alta (tipo "gola" de propósito; o ct.gola das camisas prontas continua só a sombra)
    const golaMesh = malha(new THREE.CylinderGeometry(.062, .07, .09 * A, 12, 1, true), toon(tom(ct.cor || '#3a6ea5', .93), { side: THREE.DoubleSide, roughness: .85 }));
    golaMesh.position.y = TR + .085 * A; corpo.add(golaMesh);
  }
  // braços
  const manga = ct.manga === 'curta' && !jaleco;
  const bracos = {};
  for (const [lado, s] of [['E', 1], ['D', -1]]) {
    const ombro = new THREE.Group(); ombro.position.set(s * .2 * L * (gordo > 1.1 ? 1.08 : 1), QUAD + TR * .9 + (s > 0 ? TORTO.ombro : 0), 0); ombro.rotation.order = 'YXZ';
    const ombroBola = malha(new THREE.IcosahedronGeometry(.047, 1), camisa); ombro.add(ombroBola);
    ombro.add(membro(.055, .047, .31 * A, camisa));
    if (manga) { const b = membro(.046, .042, .2 * A, pe); b.position.y = -.1 * A; ombro.add(b); }
    const cot = new THREE.Group(); cot.position.y = -.31 * A; ombro.add(cot);
    cot.add(membro(.045, .036, .28 * A, manga ? pe : camisa));
    if (capuz) { const punho = membro(.041, .041, .055 * A, toon(tom(ct.cor || '#3a6ea5', .8), { roughness: .9 })); punho.position.y = -.235 * A; cot.add(punho); }
    const mao = new THREE.Group(); mao.position.y = -.29 * A; cot.add(mao);
    const palma = malha(new THREE.BoxGeometry(.075, .095, .032), pe); palma.position.y = -.045; mao.add(palma);
    const ded = malha(new THREE.BoxGeometry(.068, .05, .026), pe); ded.position.set(0, -.11, .006); ded.rotation.x = .3; mao.add(ded);
    const pol = malha(new THREE.BoxGeometry(.022, .05, .022), pe); pol.position.set(-s * .045, -.04, .02); pol.rotation.z = s * .5; mao.add(pol);
    raiz.add(ombro); bracos[lado] = { ombro, cot, mao, s };
  }
  // cabeça: elipsoide de poucas faces + rosto pintado colado na frente + orelha + nariz
  const CB = d.cabeca || (1.1 + rnd() * .14);   // cabeça um pouco grande, como no jogo antigo (rosto legível no plano médio)
  const SX = .082 * CB * (d.cabeca_larga || (.94 + rnd() * .14)), SY = .118 * CB, SZ = .098 * CB;
  const cab = new THREE.Group(); cab.position.y = QUAD + TR + .045 * A; raiz.add(cab);
  const cabeca = malha(new THREE.SphereGeometry(1, 12, 9), pe); cabeca.scale.set(SX, SY, SZ); cabeca.position.y = SY * .95; cab.add(cabeca);
  const rostoMat = new THREE.MeshStandardMaterial({ map: texturaRosto(d, 'neutro'), roughness: .55, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const rosto = new THREE.Mesh(new THREE.SphereGeometry(1.012, 40, 30, Math.PI / 2 - FACE.phiL / 2, FACE.phiL, FACE.thS, FACE.thL), rostoMat);
  rosto.scale.set(SX, SY, SZ); rosto.position.y = SY * .95; rosto.renderOrder = 2; cab.add(rosto);
  const nz = malha(new THREE.ConeGeometry(.018, .05, 4), pe); nz.rotation.x = Math.PI / 2 + .35; nz.position.set(0, SY * .95 - SY * .14, SZ * 1.02); nz.material = pe; nz.visible = true; cab.add(nz);
  for (const s of [-1, 1]) { const o = malha(new THREE.SphereGeometry(1, 6, 5), pe); o.scale.set(.012, .03, .02); o.position.set(s * SX * .98, SY * .95, -SZ * .05); cab.add(o); }
  cabelo(cab, d, SX, SY, SZ); if (cab.children.at(-1).type === 'Group') cab.children.at(-1).position.y = SY * .95;
  const venda = malha(new THREE.CylinderGeometry(SX * 1.1, SX * 1.1, SY * .3, 16, 1, true), toon('#1f2a44', { side: THREE.DoubleSide }));
  venda.scale.z = SZ / SX * 1.05; venda.position.y = SY * 1.12; venda.visible = false; cab.add(venda);
  raiz.traverse(o => { o.userData.pessoa = d._id; });

  const rad = x => x * Math.PI / 180;
  let rostoAtual = '';
  return {
    raiz, cab, bracos, d, altura: cab.position.y + SY * 1.95, olhosY: cab.position.y + SY * .95 + SY * .12,
    mao: lado => bracos[lado].mao,
    aplicar(e) {
      for (const lado of ['E', 'D']) { const b = bracos[lado], a = e.braco[lado];
        b.ombro.rotation.set(-rad(a[0]), rad(a[3] || 0) * b.s, rad(a[1]) * b.s);
        b.cot.rotation.set(-rad(a[2]), 0, 0); }
      cab.rotation.set(rad(e.cab?.[1] || 0), rad(e.cab?.[0] || 0), rad((e.cab?.[2] || 0) + TORTO.cab));
      const k = `${e.rosto}|${e.olhoForca}|${e.olhar}`;
      if (k !== rostoAtual) { rostoMat.map = texturaRosto(d, e.rosto || 'neutro', e.olhoForca, e.olhar); rostoMat.needsUpdate = true; rostoAtual = k; }
      venda.visible = !!e.venda;
      const ps = e.passo || 0, sentado = !!e.senta;
      pernas.forEach(({ q, j }, i) => {
        if (sentado) { q.rotation.x = -Math.PI / 2; j.rotation.x = Math.PI / 2; }
        else { q.rotation.x = Math.sin(ps) * .5 * (i ? 1 : -1); j.rotation.x = Math.max(0, -Math.sin(ps) * (i ? 1 : -1)) * .6; }
      });
      corpo.rotation.x = rad((e.inclina || 0) + TORTO.incl);
      raiz.position.y = (e.y || 0) + (sentado ? -QUAD + .06 : 0) + (e.pulo || 0) + (ps ? Math.abs(Math.sin(ps)) * .02 : 0);
    },
  };
}
