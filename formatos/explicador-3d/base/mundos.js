// Explicador 3D · mundos (cenários) com cara de jogo antigo realista: material PBR com textura (piso, reboco, madeira,
// asfalto, grama), luz de cinema (cidade no entardecer com poste e letreiro aceso, consultório com painel de luz, escritório
// noir de abajur), janela acesa e cenário DENSO. Mesmos mundos e coordenadas do Desenho 3D (os planos servem nos dois). Mundo novo: uma função aqui, registrada em MUNDOS.
// Os objetos de número (contador, pilha, calendário...) entram pelo cenas.json (mundos.<id>.objetos), não aqui.
import * as THREE from 'three';
import { toon } from './gente.js';
import { placaTexto, canvas } from './objetos.js';

const malha = (geo, m) => { const o = new THREE.Mesh(geo, typeof m === 'string' ? toon(m) : m); o.castShadow = o.receiveShadow = true; return o; };
const caixa = (w, h, d, m) => malha(new THREE.BoxGeometry(w, h, d), m);
const cil = (rt, rb, h, s, m) => malha(new THREE.CylinderGeometry(rt, rb, h, s), m);
const esf = (r, m, sx = 1, sy = 1, sz = 1) => { const o = malha(new THREE.SphereGeometry(r, 20, 14), m); o.scale.set(sx, sy, sz); return o; };
const em = (o, x, y, z, ry = 0) => { o.position.set(x, y, z); o.rotation.y = ry; return o; };
const semOutline = m => { m.userData.outlineParameters = { visible: false }; return m; };
function semente(n) { let a = n >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

function ceu(cena, topo, baixo) {
  const { c, g, t } = canvas(4, 256); const gr = g.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, topo); gr.addColorStop(1, baixo);
  g.fillStyle = gr; g.fillRect(0, 0, 4, 256); t.needsUpdate = true; cena.background = t;
}
function luz(cena, { sol = '#ffe2b0', forca = 2.4, pos = [6, 10, 8], alvo = [0, 0, 0], area = 10, ceu = '#cfe6ff', chao = '#c9a66b', amb = 1.3 } = {}) {
  cena.add(new THREE.HemisphereLight(ceu, chao, amb));
  const s = new THREE.DirectionalLight(sol, forca); s.position.set(...pos); s.target.position.set(...alvo);
  s.castShadow = true; s.shadow.mapSize.set(2048, 2048); s.shadow.bias = -.0005; s.shadow.normalBias = .03;
  Object.assign(s.shadow.camera, { left: -area, right: area, top: area, bottom: -area, near: .5, far: 80 });
  cena.add(s, s.target); return s;
}
function plano(texto, w, h, op = {}) { const t = placaTexto(Array.isArray(texto) ? texto : [texto], op); return malha(new THREE.PlaneGeometry(w, h), toon('#fff', { map: t })); }
function quadroTex(desenho, w = 256, h = 256) { const { g, t } = canvas(w, h); desenho(g, w, h); t.needsUpdate = true; return t; }
// texturas de material (procedurais, sem arquivo): repetem pelo tamanho da peça
const _tex = {};
function textura(nome, desenho, n = 256) { if (!_tex[nome]) { const t = quadroTex(desenho, n, n); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.NearestFilter; t.anisotropy = 1; _tex[nome] = t; } return _tex[nome]; }   // pixel de jogo antigo de perto
function rep(t, rx, ry) { const c = t.clone(); c.repeat.set(rx, ry); c.needsUpdate = true; return c; }
const ruido = (x, W, H, n, a, cor = '0,0,0') => { const r = semente(n); for (let i = 0; i < W * H / 18; i++) { x.fillStyle = `rgba(${cor},${a * r()})`; x.fillRect(r() * W, r() * H, 1 + r() * 2, 1 + r() * 2); } };
const TX = {
  reboco: () => textura('reboco', (x, W, H) => { x.fillStyle = '#d8d8d8'; x.fillRect(0, 0, W, H); ruido(x, W, H, 1, .06); ruido(x, W, H, 2, .05, '255,255,255');
    const gr = x.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, 'rgba(0,0,0,.06)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); x.fillStyle = gr; x.fillRect(0, 0, W, H); }),
  madeira: () => textura('madeira', (x, W, H) => { const r = semente(4); x.fillStyle = '#b07a48'; x.fillRect(0, 0, W, H);
    for (let y = 0; y < H; y += 2) { x.fillStyle = `rgba(60,30,10,${.05 + .12 * Math.abs(Math.sin(y * .09 + Math.sin(y * .02) * 3))})`; x.fillRect(0, y, W, 2); }
    for (let i = 0; i < 4; i++) { x.fillStyle = 'rgba(40,20,5,.5)'; x.fillRect(0, i * H / 4, W, 2); } ruido(x, W, H, 5, .1); }),
  asfalto: () => textura('asfalto', (x, W, H) => { x.fillStyle = '#6a6a6e'; x.fillRect(0, 0, W, H); ruido(x, W, H, 6, .5); ruido(x, W, H, 7, .25, '255,255,255');
    const r = semente(8); for (let i = 0; i < 5; i++) { x.strokeStyle = 'rgba(20,20,20,.35)'; x.lineWidth = 1.5; x.beginPath(); let px = r() * W, py = r() * H; x.moveTo(px, py); for (let k = 0; k < 6; k++) { px += (r() - .5) * 40; py += (r() - .5) * 40; x.lineTo(px, py); } x.stroke(); } }),
  grama: () => textura('grama', (x, W, H) => { x.fillStyle = '#6a8a48'; x.fillRect(0, 0, W, H); const r = semente(9);
    for (let i = 0; i < 5000; i++) { x.fillStyle = `rgba(${r() < .5 ? '40,70,25' : '150,170,90'},${.3 * r()})`; x.fillRect(r() * W, r() * H, 1, 3); } }),
  calcada: () => textura('calcada', (x, W, H) => { x.fillStyle = '#c9c1b2'; x.fillRect(0, 0, W, H); ruido(x, W, H, 10, .25); x.strokeStyle = 'rgba(70,60,50,.45)'; x.lineWidth = 2;
    for (let i = 0; i <= 4; i++) { x.beginPath(); x.moveTo(i * W / 4, 0); x.lineTo(i * W / 4, H); x.moveTo(0, i * H / 4); x.lineTo(W, i * H / 4); x.stroke(); } }),
  piso: () => textura('piso', (x, W, H) => { x.fillStyle = '#e8e4dc'; x.fillRect(0, 0, W, H); ruido(x, W, H, 11, .12); const gr = x.createRadialGradient(W * .3, H * .3, 5, W * .5, H * .5, W * .8);
    gr.addColorStop(0, 'rgba(255,255,255,.15)'); gr.addColorStop(1, 'rgba(0,0,0,.08)'); x.fillStyle = gr; x.fillRect(0, 0, W, H); x.strokeStyle = 'rgba(90,85,75,.6)'; x.lineWidth = 3; x.strokeRect(0, 0, W, H); }),
  tijolo: () => textura('tijolo', (x, W, H) => { x.fillStyle = '#8a4a36'; x.fillRect(0, 0, W, H); for (let y = 0; y < H; y += 32) for (let xx = (y / 32) % 2 ? -32 : 0; xx < W; xx += 64) {
      x.fillStyle = `rgba(${120 + (xx * 7 + y) % 40},${60 + (xx + y * 3) % 20},45,1)`; x.fillRect(xx + 2, y + 2, 60, 28); } ruido(x, W, H, 12, .25); }),
};
const texMat = (nome, rx, ry, cor = '#ffffff', extra = {}) => toon(cor, { map: rep(TX[nome](), rx, ry), roughness: .85, ...extra });

// ── peças
export function arvore(rnd, s = 1) {
  const g = new THREE.Group(); const tr = cil(.1 * s, .16 * s, 1.6 * s, 6, '#4a3424'); tr.position.y = .8 * s; g.add(tr);
  const v = ['#3c5a2c', '#33502a', '#476a32'];
  for (let i = 0; i < 4; i++) { const b = malha(new THREE.IcosahedronGeometry((.75 + rnd() * .35) * s, 0), toon(v[i % 3], { flatShading: true, roughness: .9 }));
    b.position.set((rnd() - .5) * .8 * s, (1.9 + rnd() * .8) * s, (rnd() - .5) * .6 * s); b.rotation.set(rnd() * 3, rnd() * 3, 0); g.add(b); }
  return g;
}
function nuvem(rnd) { const g = new THREE.Group(); for (let i = 0; i < 5; i++) { const b = esf(1.6 + rnd() * 1.4, toon('#ffffff')); b.position.set(i * 1.8 - 3.6, rnd() * .9, rnd() * .6); b.scale.y = .7; g.add(b); } return g; }
function vaso(cor = '#c8643c') { const g = new THREE.Group(); const v = cil(.16, .12, .3, 12, cor); v.position.y = .15; g.add(v);
  for (let i = 0; i < 6; i++) { const f = malha(new THREE.ConeGeometry(.06, .5, 5), '#4f9e40'); f.position.set(Math.sin(i) * .06, .5, Math.cos(i) * .06); f.rotation.set(Math.sin(i * 2) * .5, 0, Math.cos(i * 3) * .5); g.add(f); }
  return g; }
function cadeira(cor = '#3a6ea5') { const g = new THREE.Group(); const a = caixa(.48, .08, .46, cor); a.position.y = .46; g.add(a); const c = caixa(.48, .5, .07, cor); c.position.set(0, .76, -.2); g.add(c);
  for (const x of [-.2, .2]) for (const z of [-.18, .18]) { const p = cil(.02, .02, .46, 6, '#2b2d36'); p.position.set(x, .23, z); g.add(p); } return g; }
function relogio(t0) { const g = new THREE.Group(); const c = cil(.28, .28, .06, 28, '#fdfaf6'); c.rotation.x = Math.PI / 2; g.add(c);
  const aro = malha(new THREE.TorusGeometry(.28, .03, 8, 28), '#151018'); g.add(aro);
  const h = caixa(.03, .14, .02, '#151018'); h.geometry.translate(0, .07, 0); h.position.z = .04; g.add(h);
  const m = caixa(.02, .22, .02, '#e8423a'); m.geometry.translate(0, .11, 0); m.position.z = .05; g.add(m);
  return { g, mover(t) { m.rotation.z = -t * 1.2 - (t0 || 0); h.rotation.z = -t * .1 - 1; } }; }
function janela(w, h, paisagem = true) {
  const g = new THREE.Group();
  const t = quadroTex((x, W, H) => { const gr = x.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, paisagem === 'acesa' ? '#ffcf7a' : '#33416e'); gr.addColorStop(1, paisagem === 'acesa' ? '#c9722e' : '#ff9a5a'); x.fillStyle = gr; x.fillRect(0, 0, W, H);
    if (paisagem === 'acesa') { x.fillStyle = 'rgba(90,30,20,.55)'; x.fillRect(0, 0, W * .22, H); x.fillRect(W * .78, 0, W * .22, H); x.fillStyle = 'rgba(40,15,10,.5)'; x.fillRect(W * .35, H * .55, W * .3, H * .45); paisagem = false; }
    if (paisagem) { x.fillStyle = '#2b3a2a'; x.beginPath(); x.ellipse(W * .3, H * 1.05, W * .6, H * .35, 0, 0, Math.PI * 2); x.fill(); x.fillStyle = '#243024'; x.beginPath(); x.ellipse(W * .85, H * 1.1, W * .5, H * .3, 0, 0, Math.PI * 2); x.fill();
      for (let i = 0; i < 4; i++) { x.fillStyle = ['#f6c6a0', '#f9e3a6', '#bfe0d6', '#f2b4b4'][i]; x.fillRect(W * (.08 + i * .23), H * .62, W * .17, H * .22); x.fillStyle = '#c8643c'; x.beginPath(); x.moveTo(W * (.06 + i * .23), H * .63); x.lineTo(W * (.165 + i * .23), H * .5); x.lineTo(W * (.27 + i * .23), H * .63); x.fill(); } } }, 256, 256);
  const v = new THREE.Mesh(new THREE.PlaneGeometry(w, h), semOutline(new THREE.MeshBasicMaterial({ map: t }))); g.add(v);
  const mol = toon('#fdfaf6');
  for (const [x, y, ww, hh] of [[0, h / 2, w + .12, .08], [0, -h / 2, w + .2, .1], [-w / 2, 0, .08, h], [w / 2, 0, .08, h], [0, 0, .05, h]]) { const b = caixa(ww, hh, .08, mol); b.position.set(x, y, .03); g.add(b); }
  return g;
}
function casa(rnd, w, h, cor, op = {}) {
  const g = new THREE.Group(); const d = 5;
  const c = caixa(w, h, d, cor); c.position.y = h / 2; g.add(c);
  const tel = op.telhado || ['#c8643c', '#b4532c', '#a8473a', '#8a5a3a'][Math.floor(rnd() * 4)];
  const t = malha(new THREE.ConeGeometry(Math.hypot(w, d) / 2 * 1.06, 1.6, 4), tel); t.rotation.y = Math.PI / 4; t.scale.set(1, 1, d / w); t.position.y = h + .8; g.add(t);
  const porta = caixa(.95, 2.05, .1, op.porta || ['#6b4a33', '#2c3e50', '#2f7d5b', '#a33b2c'][Math.floor(rnd() * 4)]); porta.position.set(op.portaX ?? -w * .22, 1.03, d / 2 + .03); g.add(porta);
  const mac = esf(.05, '#ffd23a'); mac.position.set((op.portaX ?? -w * .22) + .32, 1.0, d / 2 + .1); g.add(mac);
  const deg = caixa(1.3, .14, .5, '#cfc6b4'); deg.position.set(op.portaX ?? -w * .22, .07, d / 2 + .25); g.add(deg);
  const jx = op.portaX != null ? -op.portaX * .9 : w * .2;
  for (const y of h > 4 ? [1.55, 4.3] : [1.55]) for (const x of (y > 3 ? [-w * .22, w * .2] : [jx])) {
    const j = janela(1.1, 1.0, rnd() < .6 ? 'acesa' : true); j.position.set(x, y, d / 2 + .02); g.add(j);
    const cor2 = ['#2f7d5b', '#2c3e50', '#b4232c', '#3a6ea5'][Math.floor(rnd() * 4)];
    for (const s of [-1, 1]) { const ven = caixa(.36, 1.05, .05, cor2); ven.position.set(x + s * .78, y, d / 2 + .05); g.add(ven); }
    const flor = caixa(1.2, .2, .3, '#8a5a3a'); flor.position.set(x, y - .62, d / 2 + .15); g.add(flor);
    for (let k = 0; k < 5; k++) { const f = esf(.09, ['#ff6fae', '#ffd23a', '#e8423a'][k % 3]); f.position.set(x - .45 + k * .22, y - .44, d / 2 + .17); g.add(f); }
  }
  if (op.toldo) { const tl = caixa(w * .8, .1, 1.3, op.toldo); tl.position.set(0, 2.55, d / 2 + .6); tl.rotation.x = .25; g.add(tl);
    for (let i = 0; i < 6; i++) { const lis = caixa(w * .8 / 12, .11, 1.31, '#fdfaf6'); lis.position.set(-w * .4 + (i * 2 + 1.5) * w * .8 / 12, 2.55, d / 2 + .6); lis.rotation.x = .25; g.add(lis); } }
  if (op.letreiro) { const p = plano(op.letreiro, w * .75, .55, { w: 1024, h: 220, fundo: op.letreiroFundo || '#fdfaf6', cor: op.letreiroCor || '#151018', fonte: '900 120px "Arial Black", sans-serif', bw: 16 });
    p.material = semOutline(new THREE.MeshBasicMaterial({ map: p.material.map })); p.position.set(0, h - .55, d / 2 + .06); g.add(p);
    const pl = new THREE.PointLight(op.letreiroFundo || '#2ec4e8', 4, 6, 1.6); pl.position.set(0, h - .55, d / 2 + 1); g.add(pl); }
  return g;
}
function poste() { const g = new THREE.Group(); const p = cil(.06, .08, 4.2, 8, '#2b2d36'); p.position.y = 2.1; g.add(p);
  const b = caixa(.08, .08, .7, '#2b2d36'); b.position.set(0, 4.1, .3); g.add(b);
  const l = esf(.16, semOutline(new THREE.MeshBasicMaterial({ color: '#ffd28a' }))); l.position.set(0, 3.95, .6); g.add(l);
  const pl = new THREE.PointLight('#ffb15a', 6, 12, 1.6); pl.position.set(0, 3.7, .6); g.add(pl); return g; }
function carro(cor) { const g = new THREE.Group(); const c1 = malha(new THREE.CapsuleGeometry(.6, 2.6, 6, 16), cor); c1.rotation.z = Math.PI / 2; c1.scale.set(1, 1, 1.4); c1.position.y = .62; g.add(c1);
  const c2 = esf(.9, cor, 1.15, .55, .75); c2.position.set(-.1, 1.05, 0); g.add(c2);
  const vid = esf(.86, toon('#bfe3f5'), 1.12, .5, .78); vid.position.set(-.1, 1.06, 0); vid.scale.set(1.0, .48, .8); g.add(vid);
  for (const x of [-1.1, 1.1]) for (const z of [-.72, .72]) { const r = cil(.32, .32, .22, 16, '#1d1f27'); r.rotation.x = Math.PI / 2; r.position.set(x, .32, z); g.add(r); }
  return g; }
function bandeirolas(de, ate, n, alt) {
  const g = new THREE.Group(); const cores = ['#e8423a', '#ffd23a', '#2ec4e8', '#5cc46a', '#7b4dff', '#ff6fae'];
  const pts = []; for (let i = 0; i <= n; i++) { const k = i / n; pts.push(new THREE.Vector3(de[0] + (ate[0] - de[0]) * k, alt - Math.sin(k * Math.PI) * .5, de[1] + (ate[1] - de[1]) * k)); }
  g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: '#151018' })));
  for (let i = 0; i < n; i++) { const a = pts[i], b = pts[i + 1]; const f = malha(new THREE.ConeGeometry(.16, .32, 3), cores[i % cores.length]);
    f.rotation.x = Math.PI; f.position.set((a.x + b.x) / 2, (a.y + b.y) / 2 - .18, (a.z + b.z) / 2); f.scale.z = .2; f.rotation.y = Math.atan2(b.x - a.x, b.z - a.z) + Math.PI / 2; g.add(f); }
  return g;
}
function cartaz(linhas, cor, w = 1.2, h = 1.6) {
  const t = quadroTex((x, W, H) => { x.fillStyle = cor; x.fillRect(0, 0, W, H); x.fillStyle = '#fdfaf6'; x.beginPath(); x.arc(W / 2, H * .34, W * .2, 0, Math.PI * 2); x.fill();
    x.fillStyle = '#151018'; x.beginPath(); x.arc(W * .44, H * .32, 8, 0, 7); x.arc(W * .56, H * .32, 8, 0, 7); x.fill(); x.lineWidth = 6; x.strokeStyle = '#151018'; x.beginPath(); x.arc(W / 2, H * .36, 22, .3, Math.PI - .3); x.stroke();
    x.fillStyle = '#fdfaf6'; x.textAlign = 'center'; x.font = '900 52px "Arial Black", sans-serif'; linhas.forEach((l, i) => x.fillText(l, W / 2, H * .66 + i * 60));
    x.lineWidth = 12; x.strokeRect(0, 0, W, H); }, 256, 340);
  return malha(new THREE.PlaneGeometry(w, h), toon('#fff', { map: t }));
}
function dente(s = 1) { const g = new THREE.Group(); const c = esf(.3 * s, '#fdfaf6', 1, .85, .8); c.position.y = .3 * s; g.add(c);
  for (const x of [-.13, .13]) { const r = malha(new THREE.ConeGeometry(.12 * s, .35 * s, 10), '#fdfaf6'); r.rotation.x = Math.PI; r.position.set(x * s, .02 * s, 0); g.add(r); } return g; }

// ── CIDADE pequena: rua ao longo de x (z=0), casas atrás (z<-5), placa de entrada, praça com coreto, consultório em x=0
function cidade(cena, op) {
  const rnd = semente(op.semente || 12);
  ceu(cena, '#1c2244', '#ff8a4c'); cena.fog = new THREE.Fog('#c8704a', 30, 105);
  luz(cena, { sol: '#ffa060', forca: 2.6, pos: [-22, 7, 14], area: 26, ceu: '#6a78b8', chao: '#4a3020', amb: 1.2 });
  const chao = caixa(160, .1, 120, texMat('grama', 80, 60)); chao.position.set(0, -.05, -20); cena.add(chao);
  const rua = caixa(160, .04, 6, texMat('asfalto', 40, 1.5)); rua.position.set(0, .02, 0); cena.add(rua);
  for (let x = -78; x < 80; x += 4) { const f = caixa(2, .01, .18, '#ffd23a'); f.position.set(x, .045, 0); cena.add(f); }
  for (const z of [-4, 4]) { const c = caixa(160, .16, 2, texMat('calcada', 80, 1)); c.position.set(0, .08, z); cena.add(c);
    const m = caixa(160, .18, .14, '#bfb29c'); m.position.set(0, .09, z - Math.sign(z)); cena.add(m); }
  for (let x = -78; x < 80; x += 1.2) for (const z of [-4, 4]) { const j = caixa(.02, .005, 2, '#cbbfa8'); j.position.set(x, .162, z); cena.add(j); }
  const cores = ['#f6c6a0', '#f9e3a6', '#bfe0d6', '#f2b4b4', '#cfe0f6', '#f4d4e8', '#fdfaf6', '#d7efc4'];
  // casas atrás e na frente (lado da câmera, mais longe pra não tampar)
  // consultório no meio (x 0), casas dos dois lados
  const cons = casa(rnd, 7, 3.8, '#fdfaf6', { letreiro: op.letreiro || 'CONSULTÓRIO', letreiroFundo: '#2c8fa0', letreiroCor: '#fdfaf6', toldo: '#2c8fa0', portaX: -1.6, porta: '#2c8fa0' });
  cons.position.set(0, 0, -8.6); cena.add(cons); const dt = dente(1.1); dt.position.set(2.3, 4.0, -6); cena.add(dt);
  for (const lado of [-1, 1]) { let x = 3.9;
    while (x < 46) { const w = 5 + rnd() * 3, h = rnd() < .35 ? 5.6 : 3.4;
      const c = casa(rnd, w, h, cores[Math.floor(rnd() * cores.length)], { toldo: rnd() < .3 ? ['#e8423a', '#2f7d5b', '#3a6ea5'][Math.floor(rnd() * 3)] : null });
      if (lado < 0 && x + w > 7.5 && x < 22.5) { x = 22.5; continue; }   // a praça fica em x -8..-22
      c.position.set(lado * (x + w / 2), 0, -8.6); cena.add(c); x += w + .4; } }
  let x;
  x = -46; while (x < 46) { const w = 5 + rnd() * 3, h = 3.4 + rnd() * 2.2; const c = casa(rnd, w, h, cores[Math.floor(rnd() * cores.length)], {}); c.rotation.y = Math.PI; c.position.set(x + w / 2, 0, 9.2); cena.add(c); x += w + 1.2; }
  // igreja ao fundo (torre) e morros
  const ig = new THREE.Group(); const nave = caixa(7, 6, 10, '#fdfaf6'); nave.position.y = 3; ig.add(nave);
  const tor = caixa(2.6, 11, 2.6, '#fdfaf6'); tor.position.set(0, 5.5, 5); ig.add(tor);
  const tt = malha(new THREE.ConeGeometry(2, 3.4, 4), '#3a6ea5'); tt.rotation.y = Math.PI / 4; tt.position.set(0, 12.7, 5); ig.add(tt);
  const cr = caixa(.15, 1.2, .15, '#ffd23a'); cr.position.set(0, 15, 5); ig.add(cr); const cr2 = caixa(.7, .15, .15, '#ffd23a'); cr2.position.set(0, 15.1, 5); ig.add(cr2);
  const rel = relogio(); rel.g.position.set(0, 9, 6.33); ig.add(rel.g);
  ig.position.set(6, 0, -24); cena.add(ig);
  for (let i = 0; i < 9; i++) { const m = esf(14 + rnd() * 10, ['#3a4a3a', '#33433a', '#41513f'][i % 3], 1.6, .55, 1); m.position.set(-70 + i * 18, -2, -55 - rnd() * 10); cena.add(m); }
  for (let i = 0; i < 26; i++) { const lz = esf(.12, semOutline(new THREE.MeshBasicMaterial({ color: ['#ffd28a', '#ff8a5a', '#9fd8ff'][i % 3] })));   // luzes da cidade ao longe (bokeh)
    lz.position.set(-60 + rnd() * 120, 1 + rnd() * 5, -38 - rnd() * 14); cena.add(lz); }
  for (let xx = -40; xx < 42; xx += 7 + rnd() * 3) { const a = arvore(rnd, .9 + rnd() * .3); a.position.set(xx, 0, -5.4 - rnd() * .3); if (Math.abs(xx) > 2.5) cena.add(a); }
  for (let xx = -38; xx < 40; xx += 12) { const p = poste(); p.position.set(xx, 0, -3.3); cena.add(p); }
  for (let i = 0; i < 4; i++) { const c = carro(['#e8423a', '#3a6ea5', '#ffd23a', '#5cc46a'][i]); c.position.set([-38, -27, 25, 36][i], 0, i % 2 ? 1.5 : -1.5); cena.add(c); }
  // placa de entrada fica no cenas.json (objeto "placa"); aqui o morrinho e a cerca onde ela fica (x 15)
  for (let i = 0; i < 10; i++) { const p = caixa(.12, .9, .12, '#8a5a3a'); p.position.set(18 + i * 1.1, .45, 5.6); cena.add(p); }
  const tab = caixa(11, .1, .06, '#8a5a3a'); tab.position.set(23, .7, 5.6); cena.add(tab);
  for (let i = 0; i < 12; i++) { const f = esf(.18, ['#ff6fae', '#ffd23a', '#e8423a', '#fdfaf6'][i % 4]); f.position.set(13.5 + (i % 6) * .5, .18, 5.2 + Math.floor(i / 6) * .5); cena.add(f); }
  // praça (x -14): coreto, bancos, chafariz, caixote do megafone
  const pr = new THREE.Group(); const piso = cil(6, 6, .12, 40, '#e9d8b4'); piso.position.y = .06; pr.add(piso);
  const cor = new THREE.Group(); const base = cil(2.2, 2.3, .6, 8, '#fdfaf6'); base.position.y = .3; cor.add(base);
  for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2; const c = cil(.08, .08, 2.6, 8, '#fdfaf6'); c.position.set(Math.cos(a) * 2, 1.9, Math.sin(a) * 2); cor.add(c); }
  const tc = malha(new THREE.ConeGeometry(2.6, 1.4, 8), '#e8423a'); tc.position.y = 3.9; cor.add(tc); cor.position.set(-3, 0, -2.6); pr.add(cor);
  for (const [bx, bz, br] of [[2.5, 1.5, -.6], [-.5, 3.2, 0], [3.5, -1.8, -1.6]]) { const b = new THREE.Group(); const as = caixa(1.6, .08, .45, '#8a5a3a'); as.position.y = .45; b.add(as);
    const co = caixa(1.6, .4, .06, '#8a5a3a'); co.position.set(0, .75, -.2); b.add(co); for (const sx of [-.7, .7]) { const p = caixa(.08, .45, .4, '#2b2d36'); p.position.set(sx, .22, 0); b.add(p); } b.position.set(bx, 0, bz); b.rotation.y = br; pr.add(b); }
  const ch = cil(1, 1.1, .5, 20, '#cfc6b4'); ch.position.set(2.8, .25, -3.4); pr.add(ch); const agua = cil(.9, .9, .05, 20, toon('#6fd0f0')); agua.position.set(2.8, .5, -3.4); pr.add(agua);
  for (let i = 0; i < 5; i++) { const a = arvore(rnd, 1.1); const ang = i / 5 * Math.PI * 2 + .4; a.position.set(Math.cos(ang) * 5.4, 0, Math.sin(ang) * 5.4 - 1); pr.add(a); }
  const cx = caixa(.7, .45, .55, '#a8743a'); cx.position.set(.6, .22, .9); pr.add(cx);
  pr.position.set(-16, 0, -10.5); cena.add(pr); cena.userData.caixote = [-15.4, .45, -9.6];
  // eleição: bandeirolas, cartazes e mesa da urna (op.eleicao)
  const elei = new THREE.Group(); cena.add(elei);
  for (let xx = -24; xx < 16; xx += 8) elei.add(bandeirolas([xx, -5.3], [xx + 8, 5.3], 14, 5));
  const cart = [['VOTE', 'CONSCIENTE'], ['ELEIÇÕES', '2026'], ['VOTE', 'CONSCIENTE'], ['ELEIÇÕES', '2026']];
  [-10, -4.6, 7, 12.4].forEach((xx, i) => { const c = cartaz(cart[i], ['#2c3e50', '#b4232c', '#2f7d5b', '#7b4dff'][i]); c.position.set(xx, 1.9, -6.07); elei.add(c); });
  const mesa = caixa(1.4, .06, .8, '#fdfaf6'); mesa.position.set(-7.6, .78, -4.1); elei.add(mesa); const toalha = caixa(1.44, .7, .84, '#3a6ea5'); toalha.position.set(-7.6, .4, -4.1); elei.add(toalha);
  elei.visible = !!op.eleicao;
  return { atualizar(t) { rel.mover(t); } };
}

// ── CONSULTÓRIO: parede do fundo em z=-3; cadeira em (1.6, -1.1); mesa com o placar em x -2.2; sala de espera à esquerda (x<-3)
function consultorio(cena, op) {
  ceu(cena, '#2a3550', '#1a2030');
  luz(cena, { sol: '#ffe6c0', forca: 1.7, pos: [-3, 7, 6], area: 7, ceu: '#dfefff', chao: '#6a7a78', amb: 1.3 });
  const pt = new THREE.PointLight('#fff1d6', 6, 7); pt.position.set(1.6, 2.6, -.4); cena.add(pt);
  const pt2 = new THREE.PointLight('#ffb070', 5, 6); pt2.position.set(-2.4, 2.4, -1.4); cena.add(pt2);
  const pt3 = new THREE.PointLight('#7fd8e8', 3, 6); pt3.position.set(-5.5, 2.6, .5); cena.add(pt3);
  for (const [px, pz] of [[-4.5, 0], [-1.5, -1], [1.6, -.6], [3.8, 1]]) { const pn = new THREE.Mesh(new THREE.PlaneGeometry(1.1, .5), semOutline(new THREE.MeshBasicMaterial({ color: '#fff6e6' })));
    pn.rotation.x = Math.PI / 2; pn.position.set(px, 3.94, pz); cena.add(pn); }
  for (let x = -7; x < 6; x++) for (let z = -3; z < 5; z++) { const p = caixa(.98, .05, .98, texMat('piso', 1, 1, (x + z) % 2 ? '#f4f1ea' : '#ddd6ca', { roughness: .35 })); p.position.set(x + .5, -.025, z + .5); cena.add(p); }
  const fundo = caixa(14, 4, .2, texMat('reboco', 7, 2, '#bfe0d8')); fundo.position.set(-.5, 2, -3.1); cena.add(fundo);
  const rod = caixa(14, .9, .22, '#2c8fa0'); rod.position.set(-.5, .45, -3.08); cena.add(rod);
  const fai = caixa(14, .08, .24, '#fdfaf6'); fai.position.set(-.5, .92, -3.07); cena.add(fai);
  const esq = caixa(.2, 4, 9, texMat('reboco', 4, 2, '#c6e2dc')); esq.position.set(-7.2, 2, 1.4); cena.add(esq);
  const dir = caixa(.2, 4, 9, texMat('reboco', 4, 2, '#c6e2dc')); dir.position.set(5.2, 2, 1.4); cena.add(dir);
  const teto = caixa(14, .1, 9, '#fdfaf6'); teto.position.set(-.5, 4, 1.4); cena.add(teto);
  const jan = janela(1.8, 1.4); jan.position.set(3.4, 2.1, -2.98); cena.add(jan);
  // cadeira de dentista (azul petróleo), refletor, mocho e bandeja
  const cad = new THREE.Group(); const az = toon('#2c8fa0');
  const pe = cil(.2, .32, .45, 14, '#e9ecec'); pe.position.y = .22; cad.add(pe);
  const as = malha(new THREE.CapsuleGeometry(.3, .8, 6, 14), az); as.rotation.x = Math.PI / 2; as.scale.set(1.15, 1, .5); as.position.set(0, .6, 0); cad.add(as);
  const enc = malha(new THREE.CapsuleGeometry(.28, .6, 6, 14), az); enc.position.set(0, 1.0, -.62); enc.rotation.x = -.55; enc.scale.z = .5; cad.add(enc);
  const enc2 = esf(.18, az, 1.2, .8, .7); enc2.position.set(0, 1.45, -.9); cad.add(enc2);
  const pern = malha(new THREE.CapsuleGeometry(.24, .5, 6, 14), az); pern.rotation.x = Math.PI / 2 + .45; pern.scale.set(1.1, 1, .5); pern.position.set(0, .48, .7); cad.add(pern);
  const haste = cil(.035, .035, 1.9, 8, '#cfd6d6'); haste.position.set(-.55, 1.2, -.75); cad.add(haste);
  const brac = cil(.03, .03, 1, 8, '#cfd6d6'); brac.rotation.z = Math.PI / 2 - .2; brac.position.set(-.1, 2.15, -.6); cad.add(brac);
  const lum = cil(.28, .2, .14, 16, '#e9ecec'); lum.position.set(.38, 2.0, -.45); lum.rotation.x = .7; cad.add(lum);
  const lumL = cil(.2, .2, .02, 16, semOutline(new THREE.MeshBasicMaterial({ color: '#fffbe8' }))); lumL.position.set(.38, 1.95, -.41); lumL.rotation.x = .7; cad.add(lumL);
  const band = caixa(.5, .04, .35, '#cfd6d6'); band.position.set(.62, 1.1, .1); cad.add(band); const bh = cil(.02, .02, 1.1, 6, '#cfd6d6'); bh.position.set(.62, .55, .1); cad.add(bh);
  for (let i = 0; i < 4; i++) { const f = cil(.012, .012, .2, 6, '#9aa3ad'); f.rotation.z = Math.PI / 2; f.position.set(.62, 1.14, .0 + i * .07); cad.add(f); }
  cad.position.set(1.6, 0, -1.1); cad.rotation.y = -.35; cena.add(cad);
  const moc = new THREE.Group(); const ma = cil(.22, .22, .1, 14, az); ma.position.y = .55; moc.add(ma); const mp = cil(.04, .04, .5, 8, '#cfd6d6'); mp.position.y = .27; moc.add(mp); moc.position.set(.55, 0, -.2); cena.add(moc);
  // armário com pia na parede do fundo (direita)
  const arm = caixa(2.2, .9, .6, '#fdfaf6'); arm.position.set(3.6, .45, -2.65); cena.add(arm); const tp = caixa(2.3, .06, .66, '#2c8fa0'); tp.position.set(3.6, .93, -2.65); cena.add(tp);
  for (let i = 0; i < 3; i++) { const p = caixa(.66, .7, .02, '#e9ecec'); p.position.set(2.85 + i * .73, .45, -2.34); cena.add(p); }
  const tor = cil(.03, .03, .35, 8, '#cfd6d6'); tor.position.set(4.2, 1.12, -2.8); cena.add(tor); for (let i = 0; i < 3; i++) { const fr = cil(.06, .06, .18, 10, ['#ff6fae', '#2ec4e8', '#ffd23a'][i]); fr.position.set(3.0 + i * .2, 1.05, -2.75); cena.add(fr); }
  // diplomas, cartaz do dente, raio-x e relógio
  const dip = new THREE.Group(); for (let i = 0; i < 2; i++) { const d = plano(['DIPLOMA', '★'], .55, .7, { w: 256, h: 330, fundo: '#fdfaf6', cor: '#2c3e50', fonte: '900 44px Arial, sans-serif', bw: 14, raio: 4 }); d.position.set(i * .7, 0, 0); dip.add(d); }
  dip.position.set(.4, 2.55, -2.99); cena.add(dip);
  const cdente = new THREE.Group(); const cd = caixa(1, 1.3, .03, '#ffd23a'); cdente.add(cd); const dd = dente(.9); dd.position.set(0, -.25, .05); dd.scale.z = .3; cdente.add(dd); cdente.position.set(5.08, 2.2, -.5); cdente.rotation.y = -Math.PI / 2; cena.add(cdente);
  const rel = relogio(1.5); rel.g.position.set(-4.4, 3.1, -2.98); cena.add(rel.g);
  for (const [vx, vz] of [[4.6, -2.2], [-6.6, -2.4], [-.6, -2.6]]) { const v = vaso(); v.scale.setScalar(1.6); v.position.set(vx, 0, vz); cena.add(v); }
  // mesa do doutor com computador (o placar e as pilhas entram como objeto do cenas.json, em cima dela)
  const mesa = new THREE.Group(); const tm = caixa(2.4, .08, 1, '#a8743a'); tm.position.y = .78; mesa.add(tm);
  for (const sx of [-1.1, 1.1]) for (const sz of [-.4, .4]) { const p = caixa(.08, .78, .08, '#7a5230'); p.position.set(sx, .39, sz); mesa.add(p); }
  const mon = caixa(.55, .36, .04, '#1d1f27'); mon.position.set(.75, 1.1, -.3); mesa.add(mon); const ms = cil(.03, .05, .2, 8, '#1d1f27'); ms.position.set(.75, .9, -.3); mesa.add(ms);
  const tela = new THREE.Mesh(new THREE.PlaneGeometry(.5, .3), semOutline(new THREE.MeshBasicMaterial({ color: '#9fd8ff' }))); tela.position.set(.75, 1.1, -.277); mesa.add(tela);
  const lp = new THREE.Group(); const lb = cil(.08, .1, .03, 12, '#2b2d36'); lp.add(lb); const lh = cil(.015, .015, .45, 6, '#2b2d36'); lh.position.set(0, .22, 0); lh.rotation.z = .3; lp.add(lh);
  const lc = malha(new THREE.ConeGeometry(.1, .14, 12, 1, true), toon('#ffd23a', { side: THREE.DoubleSide })); lc.position.set(-.1, .45, 0); lc.rotation.z = .9; lp.add(lc); lp.position.set(-1.0, .82, -.3); mesa.add(lp);
  mesa.position.set(-2.2, 0, -2.2); cena.add(mesa);
    // sala de espera (esquerda): fileira de cadeiras vazias, mesinha com revista, porta
  for (let i = 0; i < 4; i++) { const c = cadeira('#e8423a'); c.position.set(-6.6, 0, -1.2 + i * .62); c.rotation.y = Math.PI / 2; cena.add(c); }
  const mz = caixa(.6, .4, .6, '#a8743a'); mz.position.set(-5.8, .2, 1.6); cena.add(mz); const rv = caixa(.3, .03, .4, '#ff6fae'); rv.position.set(-5.8, .42, 1.6); rv.rotation.y = .4; cena.add(rv);
  const porta = new THREE.Group(); const pf = caixa(1.1, 2.3, .1, '#2c8fa0'); pf.position.y = 1.15; porta.add(pf);
  const pv = new THREE.Mesh(new THREE.PlaneGeometry(.6, .7), semOutline(new THREE.MeshBasicMaterial({ color: '#bfe9ff' }))); pv.position.set(0, 1.6, .06); porta.add(pv);
  const pm = esf(.05, '#ffd23a'); pm.position.set(.4, 1.1, .08); porta.add(pm); porta.position.set(-4.2, 0, -3.0); cena.add(porta);
  const rec = plano(['RECEPÇÃO'], 1.3, .32, { w: 512, h: 128, fundo: '#2c8fa0', cor: '#fdfaf6', fonte: '900 70px "Arial Black", sans-serif', bw: 8 }); rec.position.set(-5.6, 2.9, -2.99); cena.add(rec);
  return { atualizar(t) { rel.mover(t); } };
}

// ── ESCRITÓRIO pequeno com o arquivo de gaveta (objeto "gaveta" do cenas.json em x 0,6)
function escritorio(cena, op) {
  ceu(cena, '#1a1a24', '#2a2030');
  luz(cena, { sol: '#ffcf90', forca: 1.8, pos: [4, 7, 6], area: 6, ceu: '#8a8aa8', chao: '#4a3020', amb: .9 });
  const pt = new THREE.PointLight('#ffb560', 7, 6); pt.position.set(-1.1, 1.5, -1.2); cena.add(pt);
  const pt2 = new THREE.PointLight('#6a8aff', 3, 7); pt2.position.set(-1.8, 2.6, -1.2); cena.add(pt2);
  for (let x = -5; x < 5; x++) for (let z = -2; z < 5; z++) { const p = caixa(.98, .05, .98, texMat('madeira', 1, 1, '#c89a6a', { roughness: .5 })); p.position.set(x + .5, -.025, z + .5); cena.add(p);
    const l = caixa(.98, .052, .03, '#9a6a3c'); l.position.set(x + .5, -.024, z + .02); cena.add(l); }
  const fundo = caixa(10, 4, .2, texMat('madeira', 3, 4, '#a8794c')); fundo.position.set(0, 2, -2.1); cena.add(fundo);
  for (let x = -5; x <= 5; x += .5) { const r = caixa(.04, 4, .05, '#e8cfae'); r.position.set(x, 2, -1.98); cena.add(r); }
  const esq = caixa(.2, 4, 7, '#ecd4b6'); esq.position.set(-3.6, 2, 1.2); cena.add(esq);
  const rod = caixa(10, .3, .24, '#7a5230'); rod.position.set(0, .15, -1.98); cena.add(rod);
  const jan = janela(1.4, 1.2, false); jan.position.set(-1.8, 2.3, -1.98); cena.add(jan);
  // estante com pastas e livros
  const est = new THREE.Group(); const ex = caixa(1.4, 2.4, .4, '#7a5230'); ex.position.y = 1.2; est.add(ex);
  const cs = ['#b4232c', '#2c3e50', '#d4af37', '#2f7d5b', '#3a6ea5', '#7b4dff'];
  for (let y = .35; y < 2.3; y += .55) { const pr = caixa(1.3, .04, .38, '#5a3c22'); pr.position.set(0, y, .03); est.add(pr);
    let xx = -.6; let k = 0; while (xx < .58) { const w = .07 + (k * 37 % 5) * .02; const b = caixa(w, .4, .3, cs[(k + Math.round(y * 7)) % 6]); b.position.set(xx + w / 2, y + .22, .06); est.add(b); xx += w + .012; k++; } }
  est.position.set(2.3, 0, -1.75); cena.add(est);
  // quadro de cortiça com post-its, relógio, mesa com abajur e papelada
  const cort = caixa(1.4, .9, .04, '#c9955a'); cort.position.set(-.1, 2.55, -1.98); cena.add(cort);
  for (let i = 0; i < 7; i++) { const p = caixa(.2, .2, .01, ['#ffd23a', '#ff6fae', '#7cc4ff', '#5cc46a'][i % 4]); p.position.set(-.6 + (i % 4) * .33, 2.4 + Math.floor(i / 4) * .3, -1.95); p.rotation.z = (i - 3) * .06; cena.add(p); }
  const rel = relogio(); rel.g.position.set(1.0, 3.3, -1.97); cena.add(rel.g);
  const mesa = new THREE.Group(); const tm = caixa(1.7, .07, .8, '#6b4a33'); tm.position.y = .76; mesa.add(tm); const lat = caixa(.06, .76, .75, '#5a3c22'); lat.position.set(-.8, .38, 0); mesa.add(lat); const lat2 = lat.clone(); lat2.position.x = .8; mesa.add(lat2);
  for (let i = 0; i < 4; i++) { const p = caixa(.3, .02 + i * .015, .38, '#fdfaf6'); p.position.set(-.45 + i * .05, .8 + i * .012, .05); p.rotation.y = i * .2; mesa.add(p); }
  const ab = new THREE.Group(); const abb = cil(.1, .12, .04, 12, '#2f7d5b'); ab.add(abb); const abh = cil(.015, .015, .5, 6, '#2f7d5b'); abh.position.y = .25; ab.add(abh);
  const abc = malha(new THREE.ConeGeometry(.16, .2, 14, 1, true), toon('#2f7d5b', { side: THREE.DoubleSide })); abc.position.y = .5; ab.add(abc);
  const abl = esf(.06, semOutline(new THREE.MeshBasicMaterial({ color: '#fff3b0' }))); abl.position.y = .44; ab.add(abl); ab.position.set(.5, .8, -.15); mesa.add(ab);
  const cx = caixa(.3, .12, .2, '#d4af37'); cx.position.set(.1, .86, -.25); mesa.add(cx);
  mesa.position.set(-1.6, 0, -1.2); cena.add(mesa);
  const cd = cadeira('#2c3e50'); cd.position.set(-1.6, 0, -.4); cd.rotation.y = Math.PI; cena.add(cd);
  const v = vaso('#2c3e50'); v.scale.setScalar(1.8); v.position.set(-3.1, 0, -1.5); cena.add(v);
  // caixas de arquivo empilhadas ao lado do arquivo
  for (let i = 0; i < 3; i++) { const b = caixa(.5, .32, .38, '#c9955a'); b.position.set(1.45, .16 + i * .33, -1.45 + (i % 2) * .06); b.rotation.y = (i - 1) * .1; cena.add(b);
    const et = caixa(.2, .1, .01, '#fdfaf6'); et.position.set(1.45, .18 + i * .33, -1.25 + (i % 2) * .06); cena.add(et); }
  return { atualizar(t) { rel.mover(t); } };
}

// ── AQUÁRIO: sala azul escura com o tanque gigante (objeto "aquario" do cenas.json em (0,0,-1.6)) e um degrau pro pescador
function aquarioSala(cena, op) {
  ceu(cena, '#1d3557', '#2a5f8a');
  luz(cena, { sol: '#cfefff', forca: 1.7, pos: [2, 8, 6], area: 6, ceu: '#9fd8ff', chao: '#284a6a', amb: 1.4 });
  const pt = new THREE.PointLight('#7fe3ff', 10, 7); pt.position.set(0, 3.4, -1.6); cena.add(pt);
  const pt2 = new THREE.PointLight('#ffd9a0', 6, 6); pt2.position.set(2.6, 2.4, 1.4); cena.add(pt2);
  for (let x = -6; x < 6; x++) for (let z = -4; z < 5; z++) { const p = caixa(.98, .05, .98, (x + z) % 2 ? '#3a6ea5' : '#33608f'); p.position.set(x + .5, -.025, z + .5); cena.add(p); }
  const fundo = caixa(12, 5, .2, '#24476b'); fundo.position.set(0, 2.5, -3.2); cena.add(fundo);
  for (let i = 0; i < 9; i++) { const o = malha(new THREE.TorusGeometry(.3 + (i % 3) * .1, .04, 6, 20), toon('#3f7fb0')); o.position.set(-5 + i * 1.25, 3.5 + (i % 2) * .5, -3.08); cena.add(o); }
  const placa2 = plano(['AQUÁRIO'], 1.6, .4, { w: 512, h: 128, fundo: '#ffd23a', cor: '#151018', fonte: '900 80px "Arial Black", sans-serif', bw: 10 }); placa2.position.set(0, 4.0, -3.08); cena.add(placa2);
  const deg = caixa(.9, .45, .7, '#a8743a'); deg.position.set(2.2, .22, .1); cena.add(deg);
  const balde = cil(.22, .18, .35, 14, '#e8423a'); balde.position.set(2.95, .17, .65); cena.add(balde);
  for (const [vx, vz] of [[-4.5, -2.4], [4.4, -2.5]]) { const v = vaso('#2c3e50'); v.scale.setScalar(2); v.position.set(vx, 0, vz); cena.add(v); }
  for (let i = 0; i < 2; i++) { const b = new THREE.Group(); const as = caixa(1.6, .1, .5, '#d4af37'); as.position.y = .45; b.add(as); for (const sx of [-.7, .7]) { const p = caixa(.1, .45, .45, '#2b2d36'); p.position.set(sx, .22, 0); b.add(p); }
    b.position.set(-3.6 + i * 7.2, 0, 1.4); b.rotation.y = i ? -.5 : .5; cena.add(b); }
  return { atualizar() {} };
}


// ── peças de enchimento (cenário cheio, cara de jogo antigo)
function cartazParede(rnd, w = .7, h = .9) { const cs = ['#b4232c', '#2c3e50', '#d4af37', '#2f7d5b', '#3a6ea5', '#7b4dff'];
  const t = quadroTex((x, W, H) => { x.fillStyle = cs[Math.floor(rnd() * 6)]; x.fillRect(0, 0, W, H); x.fillStyle = 'rgba(255,255,255,.85)'; x.fillRect(W * .1, H * .1, W * .8, H * .45);
    x.fillStyle = cs[Math.floor(rnd() * 6)]; x.beginPath(); x.arc(W * .5, H * .33, W * .18, 0, 7); x.fill(); x.fillStyle = '#fff'; for (let i = 0; i < 3; i++) x.fillRect(W * .15, H * (.65 + i * .1), W * (.7 - i * .15), H * .05); }, 128, 160);
  return malha(new THREE.PlaneGeometry(w, h), toon('#fff', { map: t })); }
function lixeira() { const g = new THREE.Group(); const b = cil(.18, .15, .5, 8, '#3a4a3a'); b.position.y = .25; g.add(b); return g; }
function prateleira(rnd, w = 1.6, h = 2) { const g = new THREE.Group(); const f = caixa(w, h, .4, texMat('madeira', 1, 2, '#8a6040')); f.position.y = h / 2; g.add(f);
  const cs = ['#e8423a', '#ffd23a', '#2ec4e8', '#5cc46a', '#ff6fae', '#f2efe6', '#7b4dff'];
  for (let y = .3; y < h - .1; y += .45) { let x = -w / 2 + .08; while (x < w / 2 - .12) { const bw = .1 + rnd() * .12, bh = .15 + rnd() * .2;
      const b = caixa(bw, bh, .25, cs[Math.floor(rnd() * cs.length)]); b.position.set(x + bw / 2, y + bh / 2, .1); g.add(b); x += bw + .03; } }
  return g; }
function luminaria(cor = '#ffcf8a', y = 3.2) { const g = new THREE.Group(); const fio = cil(.008, .008, .8, 4, '#222'); fio.position.y = y + .4; g.add(fio);
  const cup = malha(new THREE.ConeGeometry(.25, .22, 10, 1, true), toon('#2a4a3a', { side: THREE.DoubleSide })); cup.position.y = y; g.add(cup);
  const l = esf(.08, semOutline(new THREE.MeshBasicMaterial({ color: cor }))); l.position.y = y - .06; g.add(l); const pl = new THREE.PointLight(cor, 4, 5, 1.6); pl.position.y = y - .2; g.add(pl); return g; }
function salaBase(cena, op, { piso = 'piso', pisoCor = '#e8e4dc', parede = 'reboco', paredeCor = '#c8b8a0', ceu1 = '#1a1a24', ceu2 = '#2a2030', w = 12, d = 9 } = {}) {
  ceu(cena, ceu1, ceu2);
  luz(cena, { sol: '#ffd9a8', forca: 1.6, pos: [3, 7, 6], area: 7, ceu: '#a8a8c8', chao: '#4a3020', amb: 1.0 });
  const ch = caixa(w, .06, d, texMat(piso, w / (piso === 'madeira' ? 2 : 1), d / (piso === 'madeira' ? 2 : 1), pisoCor, { roughness: .45 })); ch.position.set(0, -.03, d / 2 - 3); cena.add(ch);
  const fundo = caixa(w, 4, .2, texMat(parede, w / 2, 2, paredeCor)); fundo.position.set(0, 2, -3.1); cena.add(fundo);
  for (const sx of [-1, 1]) { const l = caixa(.2, 4, d, texMat(parede, d / 2, 2, paredeCor)); l.position.set(sx * w / 2, 2, d / 2 - 3); cena.add(l); }
  const teto = caixa(w, .1, d, '#e8e4dc'); teto.position.set(0, 4, d / 2 - 3); cena.add(teto);
  const rod = caixa(w, .25, .22, '#5a3c22'); rod.position.set(0, .12, -2.98); cena.add(rod);
}

// ── CASA: sala com sofá, TV, mesinha, estante, janela de noite. Marcas: sofa, tv, porta, janela
function casa_(cena, op) {
  const rnd = semente(op.semente || 41); salaBase(cena, op, { piso: 'madeira', pisoCor: '#b07a48', paredeCor: '#d8c09a' });
  const sofa = new THREE.Group(); const as = caixa(2.2, .45, .9, '#7a3a2a'); as.position.y = .25; sofa.add(as); const co = caixa(2.2, .7, .25, '#7a3a2a'); co.position.set(0, .6, -.35); sofa.add(co);
  for (const sx of [-1.05, 1.05]) { const b = caixa(.2, .6, .9, '#6a3020'); b.position.set(sx, .35, 0); sofa.add(b); } for (let i = 0; i < 3; i++) { const al = caixa(.6, .14, .7, '#8a4a3a'); al.position.set(-.7 + i * .7, .52, .05); sofa.add(al); }
  sofa.position.set(-.5, 0, -2.2); cena.add(sofa);
  const rack = caixa(1.8, .5, .45, texMat('madeira', 1, 1, '#5a3c22')); rack.position.set(-.5, .25, 2.6); cena.add(rack);
  const tv = caixa(1.3, .8, .08, '#111'); tv.position.set(-.5, 1.0, 2.6); cena.add(tv); const tvt = new THREE.Mesh(new THREE.PlaneGeometry(1.22, .72), semOutline(new THREE.MeshBasicMaterial({ color: '#4a8ad0' }))); tvt.position.set(-.5, 1.0, 2.55); tvt.rotation.y = Math.PI; cena.add(tvt);
  const pl = new THREE.PointLight('#6aa0ff', 3, 5); pl.position.set(-.5, 1.1, 2.2); cena.add(pl);
  const mz = caixa(1.0, .4, .6, texMat('madeira', 1, 1, '#8a6040')); mz.position.set(-.5, .2, -1.2); cena.add(mz);
  for (let i = 0; i < 3; i++) { const c = caixa(.12, .15, .12, ['#e8423a', '#fdfaf6', '#ffd23a'][i]); c.position.set(-.8 + i * .3, .48, -1.2); cena.add(c); }
  const est = prateleira(rnd, 1.4, 2.2); est.position.set(3.2, 0, -2.8); cena.add(est);
  const jan = janela(1.6, 1.3, false); jan.position.set(-3.5, 2.1, -2.98); cena.add(jan);
  cena.add(em(luminaria('#ffc070', 3.1), -.5, 0, -1.2));
  for (let i = 0; i < 3; i++) { const q = cartazParede(rnd, .55, .45); q.position.set(1.0 + i * .7, 2.5, -2.99); cena.add(q); }
  const v = vaso('#a8473a'); v.scale.setScalar(1.8); v.position.set(1.8, 0, -2.5); cena.add(v);
  return { atualizar() {} };
}
// ── LOJA: balcão com caixa registradora, prateleiras cheias, vitrine. Marcas: balcao (atrás), cliente (na frente), porta
function loja(cena, op) {
  const rnd = semente(op.semente || 43); salaBase(cena, op, { paredeCor: '#e8e0c8', pisoCor: '#d8d0c0' });
  for (let i = 0; i < 4; i++) { const pr = prateleira(rnd, 1.6, 2.4); pr.position.set(-4.5 + i * 1.75, 0, -2.75); cena.add(pr); }
  const bal = caixa(2.6, 1.0, .7, texMat('madeira', 2, 1, '#9a6a40')); bal.position.set(.5, .5, -.4); cena.add(bal);
  const tampo = caixa(2.7, .06, .8, '#3a3a3a'); tampo.position.set(.5, 1.03, -.4); cena.add(tampo);
  const reg = caixa(.45, .3, .4, '#2a2a2e'); reg.position.set(1.2, 1.2, -.45); cena.add(reg); const vis = new THREE.Mesh(new THREE.PlaneGeometry(.3, .1), semOutline(new THREE.MeshBasicMaterial({ color: '#3cff6a' }))); vis.position.set(1.2, 1.3, -.24); cena.add(vis);
  for (let i = 0; i < 6; i++) { const c = caixa(.3, .25, .3, ['#c9955a', '#d4af37', '#e8423a'][i % 3]); c.position.set(3.6 + (i % 2) * .35, .13 + Math.floor(i / 2) * .26, 1.5); cena.add(c); }
  const placa = plano(['ABERTO'], 1.1, .35, { w: 512, h: 160, fundo: '#b4232c', cor: '#fdfaf6', fonte: '900 90px "Arial Black", sans-serif', bw: 8 }); placa.material = semOutline(new THREE.MeshBasicMaterial({ map: placa.material.map }));
  placa.position.set(-3.5, 3.2, -2.97); cena.add(placa);
  cena.add(em(luminaria('#fff0d0', 3.2), -1, 0, 0), em(luminaria('#fff0d0', 3.2), 2, 0, 0));
  cena.add(em(lixeira(), 3.4, 0, -2.2));
  return { atualizar() {} };
}
// ── RESTAURANTE: mesas com toalha xadrez, cadeiras, balcão, luminárias quentes. Marcas: mesa1 (0,0), mesa2, balcao
function restaurante(cena, op) {
  const rnd = semente(op.semente || 47); salaBase(cena, op, { piso: 'piso', pisoCor: '#c8a880', parede: 'tijolo', paredeCor: '#ffffff' });
  const toalha = (() => { const t = quadroTex((x, W, H) => { x.fillStyle = '#f2efe6'; x.fillRect(0, 0, W, H); x.fillStyle = 'rgba(180,30,40,.75)'; for (let i = 0; i < 8; i++) { x.fillRect(i * W / 8, 0, W / 16, H); x.fillRect(0, i * H / 8, W, H / 16); } }, 64, 64); return toon('#fff', { map: t }); })();
  for (const [mx, mz] of [[0, 0], [-2.6, -1.2], [2.6, -1.2], [-2.4, 1.6], [2.4, 1.8]]) { const m = new THREE.Group(); const tp = caixa(1.1, .06, 1.1, toalha); tp.position.y = .76; m.add(tp);
    const pe = cil(.05, .05, .76, 6, '#2a2a2a'); pe.position.y = .38; m.add(pe);
    for (const [cx, cz, r] of [[0, .75, Math.PI], [0, -.75, 0]]) { const c = cadeira('#6a3a22'); c.position.set(cx, 0, cz); c.rotation.y = r; m.add(c); }
    for (let i = 0; i < 2; i++) { const pr = cil(.13, .1, .02, 14, '#fdfaf6'); pr.position.set(i ? .22 : -.22, .8, 0); m.add(pr); }
    m.position.set(mx, 0, mz); cena.add(m); cena.add(em(luminaria('#ffb860', 2.9), mx, 0, mz)); }
  const bal = caixa(3.5, 1.05, .6, texMat('madeira', 3, 1, '#7a4a2a')); bal.position.set(1.5, .52, -2.5); cena.add(bal);
  for (let i = 0; i < 7; i++) { const gf = cil(.05, .05, .3, 8, ['#2f7d5b', '#8a3a2a', '#d4af37'][i % 3]); gf.position.set(.2 + i * .4, 1.22, -2.6); cena.add(gf); }
  const menu = plano(['CARDÁPIO', 'PF  R$ 25', 'SUCO R$ 8'], 1.2, .9, { w: 384, h: 288, fundo: '#151515', cor: '#fdfaf6', fonte: '700 44px Arial, sans-serif', bw: 10, raio: 6 }); menu.position.set(-2.5, 2.4, -2.98); cena.add(menu);
  return { atualizar() {} };
}
// ── BANCO: guichês com vidro, fila com corda, placa de senha, cofre. Marcas: guiche1 (atrás do vidro), fila
function banco(cena, op) {
  const rnd = semente(op.semente || 53); salaBase(cena, op, { piso: 'piso', pisoCor: '#d8d8d0', paredeCor: '#b8c0c8', ceu1: '#20242c', ceu2: '#30343c' });
  for (let i = 0; i < 3; i++) { const g = new THREE.Group(); const b = caixa(1.6, 1.1, .6, texMat('madeira', 1, 1, '#4a3a2a')); b.position.y = .55; g.add(b);
    const v = new THREE.Mesh(new THREE.PlaneGeometry(1.5, .9), toon('#bfe3f5', { transparent: true, opacity: .25 })); v.position.set(0, 1.55, .25); g.add(v);
    const n = plano([`CAIXA ${i + 1}`], .7, .22, { w: 256, h: 80, fundo: '#1f3a6a', cor: '#fdfaf6', fonte: '900 44px Arial, sans-serif', bw: 4 }); n.position.set(0, 2.15, .26); g.add(n);
    g.position.set(-2.4 + i * 2.4, 0, -1.8); cena.add(g); }
  for (let i = 0; i < 5; i++) { const p = cil(.04, .05, .95, 8, '#c9a040'); p.position.set(-3 + i * 1.2, .47, .8); cena.add(p); }
  const corda = cil(.025, .025, 4.8, 6, '#8a1a2a'); corda.rotation.z = Math.PI / 2; corda.position.set(-.6, .82, .8); cena.add(corda);
  const senha = plano(['SENHA', '047'], 1.2, .7, { w: 384, h: 220, fundo: '#111', cor: '#ff4040', fonte: '900 70px Arial, sans-serif', bw: 6 }); senha.material = semOutline(new THREE.MeshBasicMaterial({ map: senha.material.map }));
  senha.position.set(3.4, 3.0, -2.97); cena.add(senha);
  const cofre = cil(.6, .6, .2, 24, '#7a7a80'); cofre.rotation.x = Math.PI / 2; cofre.position.set(4.6, 1.4, -2.9); cena.add(cofre);
  cena.add(em(luminaria('#fff0e0', 3.3), -2.4, 0, -.5), em(luminaria('#fff0e0', 3.3), 2.4, 0, -.5));
  return { atualizar() {} };
}
// ── CASSINO: mesas verdes com fichas, caça-níqueis acesos, lustres, carpete vermelho. Marcas: mesa (0,0), slots
function cassino(cena, op) {
  const rnd = semente(op.semente || 59); salaBase(cena, op, { piso: 'piso', pisoCor: '#7a1a2a', parede: 'madeira', paredeCor: '#6a3a2a', ceu1: '#120a10', ceu2: '#1a1018', w: 14, d: 10 });
  for (const [mx, mz] of [[0, 0], [-3.4, -1], [3.4, -1]]) { const m = new THREE.Group(); const tp = malha(new THREE.CylinderGeometry(1.2, 1.2, .1, 16), toon('#1f6a3a')); tp.position.y = .8; tp.scale.z = .65; m.add(tp);
    const bd = malha(new THREE.TorusGeometry(1.2, .06, 6, 20), toon('#5a2a1a')); bd.rotation.x = Math.PI / 2; bd.scale.y = .65; bd.position.y = .85; m.add(bd);
    const pe = cil(.25, .35, .8, 8, '#3a2018'); pe.position.y = .4; m.add(pe);
    for (let i = 0; i < 6; i++) { const pil = cil(.05, .05, .04 + rnd() * .15, 12, ['#e8423a', '#2e6ae8', '#151515', '#f2efe6'][i % 4]); pil.position.set(-.5 + i * .2, .9, (rnd() - .5) * .4); m.add(pil); }
    m.position.set(mx, 0, mz); cena.add(m); cena.add(em(luminaria('#ffd890', 3.0), mx, 0, mz)); }
  for (let i = 0; i < 6; i++) { const s = new THREE.Group(); const c = caixa(.7, 1.7, .6, '#2a2a3a'); c.position.y = .85; s.add(c);
    const t = new THREE.Mesh(new THREE.PlaneGeometry(.55, .45), semOutline(new THREE.MeshBasicMaterial({ color: ['#ff40a0', '#40c0ff', '#ffd040'][i % 3] }))); t.position.set(0, 1.25, .31); s.add(t);
    s.position.set(-5.5 + i * 2.2, 0, -2.6); cena.add(s); }
  const pl = new THREE.PointLight('#ff3a8a', 3, 8); pl.position.set(-4, 2.5, -2); cena.add(pl); const pl2 = new THREE.PointLight('#3ac0ff', 3, 8); pl2.position.set(4, 2.5, -2); cena.add(pl2);
  return { atualizar() {} };
}

// Marcas de posição por cenário ([x, z], + y e rot quando precisa): "pos": "@balcao" na decupagem.
// Marcas de posição de cada cenário: marcas.json (o gerar.py troca "@marca" pela posição).


export const MUNDOS = { cidade, consultorio, escritorio, aquario: aquarioSala, casa: casa_, loja, restaurante, banco, cassino };
