// Explicador 3D · objetos (vieram do Desenho 3D; com material PBR e glow ficam com cara de jogo realista). "Fato é objeto": todo número falado vira um evento físico NO QUADRO DA PALAVRA.
// Cada fábrica devolve { raiz, atualizar(l, p, ctx) }: l = segundos dentro do plano, p = parâmetros do plano (c.obj[id]),
// ctx = { t, camera, ponto(pessoa, parte) }. Tudo é função do tempo (seek), nada de relógio.
import * as THREE from 'three';
import { toon } from './gente.js';

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const suave = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const saida = x => 1 - Math.pow(1 - clamp(x), 3);
const mola = x => { x = clamp(x); return 1 + Math.pow(2, -10 * x) * Math.sin((x * 10 - .75) * (2 * Math.PI / 3)); };   // elástico: passa e volta
const malha = (geo, m) => { const o = new THREE.Mesh(geo, typeof m === 'string' ? toon(m) : m); o.castShadow = o.receiveShadow = true; return o; };
const caixa = (w, h, d, m) => malha(new THREE.BoxGeometry(w, h, d), m);
const cil = (rt, rb, h, s, m) => malha(new THREE.CylinderGeometry(rt, rb, h, s), m);
const semOutline = m => { m.userData.outlineParameters = { visible: false }; return m; };
const basica = (map, extra = {}) => semOutline(new THREE.MeshBasicMaterial({ map, toneMapped: false, ...extra }));
function rnd(n) { let a = n >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
export function canvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return { c, g: c.getContext('2d'), t }; }
export function placaTexto(linhas, { w = 512, h = 256, fundo = '#fff', cor = '#151018', fonte = '900 90px "Arial Black", Impact, sans-serif', borda = '#151018', bw = 14, raio = 30, gap = 1.12 } = {}) {
  const { g, t } = canvas(w, h);
  if (fundo) { g.fillStyle = fundo; g.beginPath(); g.roundRect(bw / 2, bw / 2, w - bw, h - bw, raio); g.fill(); if (borda) { g.lineWidth = bw; g.strokeStyle = borda; g.stroke(); } }
  g.fillStyle = cor; g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = fonte;
  const tam = parseInt(fonte.match(/(\d+)px/)[1]);
  linhas.forEach((l, i) => { let f = fonte; g.font = f; let k = 1; while (g.measureText(l).width > w - bw * 3 && k > .4) { k -= .05; g.font = f.replace(/\d+px/, Math.round(tam * k) + 'px'); }
    g.fillText(l, w / 2, h / 2 + (i - (linhas.length - 1) / 2) * tam * gap); });
  t.needsUpdate = true; return t;
}
// janela de evento: pop com mola terminando em "em" (aparece já no tamanho cheio no quadro da palavra)
const pop = (l, em, d = .22) => l < em - d ? 0 : mola((l - (em - d)) / d * .55 + .45 * clamp((l - (em - d)) / d));

// ── 7 segmentos (LED)
const SEG = { 0: 'abcdef', 1: 'bc', 2: 'abdeg', 3: 'abcdg', 4: 'bcfg', 5: 'acdfg', 6: 'acdefg', 7: 'abc', 8: 'abcdefg', 9: 'abcdfg' };
function digito(g, x, y, w, h, d, cor, apagado) {
  const t = w * .16, pos = { a: [x + t, y, w - 2 * t, t], d: [x + t, y + h - t, w - 2 * t, t], g: [x + t, y + h / 2 - t / 2, w - 2 * t, t],
    f: [x, y + t * .6, t, h / 2 - t * .9], b: [x + w - t, y + t * .6, t, h / 2 - t * .9], e: [x, y + h / 2 + t * .3, t, h / 2 - t * .9], c: [x + w - t, y + h / 2 + t * .3, t, h / 2 - t * .9] };
  for (const s of 'abcdefg') { const on = d != null && SEG[d].includes(s); g.fillStyle = on ? cor : apagado; const [a, b, c, e] = pos[s]; g.beginPath(); g.roundRect(a, b, c, e, t / 2); g.fill(); }
}

// contador LED: rola e PARA no número no quadro da palavra (p: {de, para, em, dura, rotulo}). Odômetro: o dígito de baixo gira.
function contador(op) {
  const nd = op.digitos || 3, cor = op.cor || '#ff3a2e';
  const W = .34 * nd + .7, Hh = .62;
  const g = new THREE.Group();
  const caixaM = toon(op.caixa || '#2b2d36');
  g.add(caixa(W, Hh, .22, caixaM));
  const borda = caixa(W + .08, Hh + .08, .16, toon('#ffd23a')); borda.position.z = -.04; g.add(borda);
  const tela = canvas(128 * nd + 256, 256);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(W - .1, Hh - .12), basica(tela.t)); scr.material.color.setScalar(1.7); scr.position.z = .112; g.add(scr);
  let rot = null;
  if (op.rotulo !== undefined) { const tt = placaTexto([op.rotulo || ''], { w: 512, h: 160, fundo: '#ffd23a', fonte: '900 96px "Arial Black", sans-serif' });
    rot = new THREE.Mesh(new THREE.PlaneGeometry(W * .7, W * .7 * 160 / 512), toon('#fff', { map: tt })); rot.position.set(0, Hh / 2 + W * .7 * 80 / 512 + .03, .05); g.add(rot); }
  for (const s of [-1, 1]) { const p = cil(.04, .04, op.haste ?? 0, 8, '#4a4d57'); p.position.set(s * W * .35, -Hh / 2 - (op.haste ?? 0) / 2, -.02); g.add(p); }
  let ultimo = '';
  const desenhar = (v, brilho, apagado = false) => {
    const k = `${v.toFixed(3)}|${brilho.toFixed(2)}|${op.sufixo}|${apagado}`; if (k === ultimo) return; ultimo = k;
    const { c, g: x } = tela; x.fillStyle = '#120708'; x.fillRect(0, 0, c.width, c.height);
    if (apagado) { for (let i = 0; i < nd; i++) digito(x, 24 + i * 128, 33, 104, 190, null, '#000', '#2a1214'); tela.t.needsUpdate = true; return; }
    const cw = 104, ch = 190, y0 = 33, x0 = 24;
    const on = brilho > .5 ? cor : '#ff8f7a';
    for (let i = 0; i < nd; i++) {
      const casa = nd - 1 - i, pv = v / Math.pow(10, casa);
      const dg = Math.floor(pv) % 10;
      let fr = casa === 0 ? pv - Math.floor(pv) : suave(((v / Math.pow(10, casa - 1)) % 10 - 9));   // odômetro
      if (Math.abs(v - Math.round(v)) < 1e-6) fr = 0;
      const vazio = Math.floor(pv) === 0 && casa > 0;   // sem zero à esquerda
      x.save(); x.beginPath(); x.rect(x0 + i * (cw + 24) - 6, y0 - 6, cw + 12, ch + 12); x.clip();
      digito(x, x0 + i * (cw + 24), y0 - fr * ch * 1.1, cw, ch, vazio && fr === 0 ? null : dg, on, '#2a1214');
      if (fr > 0) digito(x, x0 + i * (cw + 24), y0 + (1 - fr) * ch * 1.1, cw, ch, (dg + 1) % 10, on, '#2a1214');
      x.restore();
    }
    x.fillStyle = on; x.font = '900 70px "Arial Black", sans-serif'; x.textAlign = 'left'; x.textBaseline = 'middle';
    x.fillText(op.sufixo ?? 'MIL', x0 + nd * (cw + 24) + 6, c.height / 2 + 30);
    tela.t.needsUpdate = true;
  };
  return { raiz: g, atualizar(l, p = {}) {
    const de = p.de ?? op.valor ?? 0, para = p.para ?? de, em = p.em ?? 0, dura = p.dura ?? .75;
    let v = l >= em ? para : l <= em - dura ? de : de + (para - de) * saida((l - (em - dura)) / dura);
    if (p.trava) v = para + (Math.sin(l * 31) > .7 ? 0 : 0);
    const flash = l >= em && l < em + .25 ? 1 : 0;
    desenhar(v, 1 - flash * .6 * (Math.sin((l - em) * 60) > 0 ? 1 : 0), p.acende != null && l < p.acende);
    const k = p.cresce ? pop(l, p.cresce) : 1; g.scale.setScalar(Math.max(.001, k) * (op.escala || 1));
  } };
}

// pilha de moedas (barra do gráfico): p {n, n0, em, dura}. Moedas caem uma a uma e a última assenta no quadro da palavra.
function pilha(op) {
  const max = op.max || 18, g = new THREE.Group(), r = rnd(op.semente || 7);
  const ouro = toon('#f2c230'), ouro2 = toon('#d99a1a');
  const moedas = [];
  for (let i = 0; i < max; i++) { const m = new THREE.Group(); const c = cil(.13, .13, .045, 22, ouro); m.add(c);
    const aro = malha(new THREE.TorusGeometry(.13, .012, 6, 22), ouro2); aro.rotation.x = Math.PI / 2; m.add(aro);
    m.userData.base = [(r() - .5) * .025, .03 + i * .05, (r() - .5) * .025, (r() - .5) * .5]; g.add(m); moedas.push(m); }
  if (op.rotulo) { const tt = placaTexto([op.rotulo], { w: 512, h: 160, fundo: '#fdfaf6', fonte: '900 92px "Arial Black", sans-serif' });
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(.42, .13), toon('#fff', { map: tt })); pl.position.set(0, .07, .2); pl.rotation.x = -.5; g.add(pl);
    const ap = caixa(.46, .02, .2, '#3a2a1e'); ap.position.set(0, .01, .12); g.add(ap); }
  return { raiz: g, atualizar(l, p = {}) {
    const n = p.n ?? op.n ?? 0, n0 = p.n0 ?? n, em = p.em ?? 0, dura = p.dura ?? .7;
    moedas.forEach((m, i) => { const [bx, by, bz, br] = m.userData.base; m.rotation.y = br;
      if (i >= Math.max(n, n0)) { m.visible = false; return; }
      m.visible = true; m.position.set(bx, by, bz); m.rotation.z = 0;
      if (n > n0 && i >= n0) {   // cai do alto
        const ti = em - dura + dura * (i - n0 + 1) / (n - n0), q = (l - (ti - .16)) / .16;
        if (q < 0) { m.visible = false; return; }
        m.position.y = by + (1 - clamp(q)) * (1 - clamp(q)) * .9; }
      if (n < n0 && i >= n) {   // sai voando (a pilha cai)
        const ti = em - dura + dura * (n0 - i) / (n0 - n), q = (l - ti) / .35;
        if (q > 0) { m.position.x = bx + q * .5 * (i % 2 ? 1 : -1); m.position.y = by + q * .4 - q * q * 1.6; m.rotation.z = q * 4; if (q > 1) m.visible = false; } }
    });
  } };
}

// medidor com ponteiro (p {de, para 0..1, em}): chega no valor no quadro da palavra e passa um pouco (overshoot leve)
function medidor(op) {
  const g = new THREE.Group();
  const { g: x, t } = canvas(512, 512);
  x.fillStyle = '#fdfaf6'; x.beginPath(); x.arc(256, 256, 248, 0, Math.PI * 2); x.fill();
  const arco = (a0, a1, cor) => { x.strokeStyle = cor; x.lineWidth = 46; x.beginPath(); x.arc(256, 300, 180, a0, a1); x.stroke(); };
  arco(Math.PI * 1.0, Math.PI * 1.45, '#5cc46a'); arco(Math.PI * 1.45, Math.PI * 1.7, '#ffd23a'); arco(Math.PI * 1.7, Math.PI * 2.0, '#e8423a');
  x.strokeStyle = '#151018'; x.lineWidth = 6; for (let i = 0; i <= 10; i++) { const a = Math.PI + i / 10 * Math.PI; x.beginPath();
    x.moveTo(256 + Math.cos(a) * 150, 300 + Math.sin(a) * 150); x.lineTo(256 + Math.cos(a) * 205, 300 + Math.sin(a) * 205); x.stroke(); }
  x.fillStyle = '#151018'; x.font = '900 64px "Arial Black", sans-serif'; x.textAlign = 'center'; x.fillText(op.rotulo || '', 256, 420);
  x.lineWidth = 16; x.beginPath(); x.arc(256, 256, 248, 0, Math.PI * 2); x.stroke();
  const corpo = cil(.5, .5, .12, 40, '#2b2d36'); corpo.rotation.x = Math.PI / 2; g.add(corpo);
  const face = new THREE.Mesh(new THREE.CircleGeometry(.46, 48), toon('#fff', { map: t })); face.position.z = .065; g.add(face);
  const pont = new THREE.Group(); pont.position.set(0, -.08, .09); g.add(pont);
  const agulha = caixa(.03, .38, .02, '#e8302a'); agulha.position.y = .19; pont.add(agulha);
  const eixo = cil(.05, .05, .05, 16, '#151018'); eixo.rotation.x = Math.PI / 2; pont.add(eixo);
  return { raiz: g, atualizar(l, p = {}) {
    const de = p.de ?? 0, para = p.para ?? de, em = p.em ?? 0;
    const tau = l - (em - .112); const v = tau <= 0 ? de : para + (de - para) * Math.exp(-tau * 9) * Math.cos(tau * 14);
    pont.rotation.z = Math.PI / 2 - clamp(v, -.05, 1.08) * Math.PI;
  } };
}

// calendário de mesa (p {de, para, em, dura}): as folhas viram uma a uma e a última assenta no quadro da palavra
const MESES = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];
const _folhas = {};
function folhaMes(m) { if (_folhas[m]) return _folhas[m];
  const { g: x, t } = canvas(512, 512); x.fillStyle = '#fdfaf6'; x.fillRect(0, 0, 512, 512); x.fillStyle = '#d8323a'; x.fillRect(0, 0, 512, 150);
  x.fillStyle = '#fff'; x.font = '900 110px "Arial Black", sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle'; x.fillText(m, 256, 80);
  x.fillStyle = '#151018'; x.font = '900 200px "Arial Black", sans-serif'; x.fillText('1', 256, 330);
  x.strokeStyle = '#151018'; x.lineWidth = 16; x.strokeRect(8, 8, 496, 496); return (_folhas[m] = t); }
function calendario(op) {
  const g = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CylinderGeometry(.06, .06, .5, 3), toon('#2c3e50')); base.rotation.z = Math.PI / 2; base.rotation.x = Math.PI / 6; base.position.y = .05; g.add(base);
  const geo = new THREE.PlaneGeometry(.46, .46); geo.translate(0, -.23, 0);
  const atras = new THREE.Mesh(geo, toon('#fff', { map: folhaMes('JAN') })); atras.position.set(0, .5, -.005); atras.rotation.x = -.18; g.add(atras);
  const vira = new THREE.Mesh(geo, toon('#fff', { map: folhaMes('JAN'), side: THREE.DoubleSide })); vira.position.set(0, .5, .002); g.add(vira);
  for (let i = -3; i <= 3; i++) { const a = malha(new THREE.TorusGeometry(.022, .006, 6, 12), toon('#9aa3ad')); a.position.set(i * .06, .5, 0); a.rotation.y = Math.PI / 2; g.add(a); }
  return { raiz: g, atualizar(l, p = {}) {
    const i0 = MESES.indexOf(p.de || op.mes || 'JAN'), i1 = MESES.indexOf(p.para || p.de || op.mes || 'JAN'), em = p.em ?? 0;
    const dura = p.dura ?? Math.min(1.2, .16 * Math.max(1, i1 - i0));
    const m = i1 === i0 ? i0 : l >= em ? i1 : l <= em - dura ? i0 : i0 + (i1 - i0) * ((l - (em - dura)) / dura);
    const cur = Math.floor(m + 1e-6), fr = m - cur;
    atras.material.map = folhaMes(MESES[Math.min(i1, cur + (fr > 0 ? 1 : 0))]); atras.material.needsUpdate = true;
    vira.material.map = folhaMes(MESES[cur]); vira.material.needsUpdate = true;
    vira.rotation.x = -.18 - suave(fr) * Math.PI * .95; vira.visible = fr > 0 || m === cur;
    if (fr === 0) { vira.rotation.x = -.18; }
  } };
}

// placa de entrada da cidade (p {acende}): as lâmpadas correm e o "12.000 hab." acende no quadro da palavra
function placa(op) {
  const g = new THREE.Group();
  for (const s of [-1, 1]) { const p = cil(.07, .07, 2.6, 10, '#6b4a33'); p.position.set(s * 1.25, 1.3, 0); g.add(p); }
  const tt = placaTexto(['BEM-VINDO A', op.nome || 'VILA SERENA'], { w: 1024, h: 420, fundo: '#2f7d5b', cor: '#fdfaf6', borda: '#fdfaf6', bw: 20, fonte: '900 120px "Arial Black", sans-serif' });
  const pl = new THREE.Mesh(new THREE.BoxGeometry(2.9, 1.2, .1), [toon('#235e45'), toon('#235e45'), toon('#235e45'), toon('#235e45'), toon('#fff', { map: tt }), toon('#235e45')]);
  pl.position.y = 2.25; pl.castShadow = true; g.add(pl);
  const numOff = placaTexto([op.numero || '12.000 hab.'], { w: 1024, h: 260, fundo: '#2a2026', cor: '#6b5a40', borda: '#151018', fonte: '900 150px "Arial Black", sans-serif' });
  const numOn = placaTexto([op.numero || '12.000 hab.'], { w: 1024, h: 260, fundo: '#ffd23a', cor: '#151018', borda: '#151018', fonte: '900 150px "Arial Black", sans-serif' });
  const nm = basica(numOff); nm.color.setScalar(1.25); const num = new THREE.Mesh(new THREE.PlaneGeometry(2.3, .58), nm); num.position.set(0, 1.25, .06); g.add(num);
  const fundoN = caixa(2.45, .7, .08, '#151018'); fundoN.position.set(0, 1.25, 0); g.add(fundoN);
  const lamps = [];
  for (let i = 0; i < 16; i++) { const a = i / 16; let x, y; const per = 2 * (2.45 + .7), s = a * per;
    if (s < 2.45) { x = -1.225 + s; y = 1.62; } else if (s < 3.15) { x = 1.225; y = 1.62 - (s - 2.45); } else if (s < 5.6) { x = 1.225 - (s - 3.15); y = .92; } else { x = -1.225; y = .92 + (s - 5.6); }
    const m = semOutline(new THREE.MeshBasicMaterial({ color: '#5a4a30', toneMapped: false }));
    const b = new THREE.Mesh(new THREE.SphereGeometry(.05, 10, 8), m); b.position.set(x, y, .07); g.add(b); lamps.push(b); }
  return { raiz: g, atualizar(l, p = {}) {
    const em = p.acende ?? (p.aceso ? -99 : 99);
    num.material.map = l >= em ? numOn : numOff; num.material.needsUpdate = true;
    lamps.forEach((b, i) => { const ti = em - .3 + i / 16 * .3; const on = l >= ti; b.material.color.set(on ? (i % 2 ? '#fff3b0' : '#ffd23a') : '#5a4a30');
      if (on) b.material.color.multiplyScalar(l < em + .2 ? 2.2 : 1.5); });
  } };
}

// celular (p {msgs: [{texto, lado: in|out, em}], titulo}): balões pipocando na tela no quadro da palavra
function celular(op) {
  const g = new THREE.Group(); const E = op.escala || 1;
  const corpo = malha(new THREE.BoxGeometry(.4 * E, .8 * E, .05 * E), toon('#1d1f27')); g.add(corpo);
  const tl = canvas(512, 1024); const scr = new THREE.Mesh(new THREE.PlaneGeometry(.36 * E, .72 * E), basica(tl.t)); scr.material.color.setScalar(.82); scr.material.userData._hdr = 1; scr.position.z = .026 * E; g.add(scr);   // tela sem estourar (passava de 1 e o glow lavava)
  let ult = '';
  return { raiz: g, atualizar(l, p = {}) {
    const msgs = p.msgs || op.msgs || [];
    const k = msgs.map(m => Math.round(clamp((l - (m.em - .2)) / .22) * 20)).join(',') + (p.titulo || '');
    if (k === ult) return; ult = k;
    const { g: x, c } = tl; x.fillStyle = '#ffffff'; x.fillRect(0, 0, 512, 1024);
    x.fillStyle = '#f2f2f5'; x.fillRect(0, 0, 512, 150); x.fillStyle = '#151018'; x.font = '700 40px Helvetica, Arial'; x.textAlign = 'left';
    x.beginPath(); x.arc(70, 92, 34, 0, Math.PI * 2); x.fillStyle = '#d6336c'; x.fill(); x.fillStyle = '#151018'; x.fillText(p.titulo || op.titulo || 'Direct', 124, 106);
    let y = 200;
    for (const m of msgs) {
      const q = l < m.em - .2 ? 0 : mola(clamp((l - (m.em - .2)) / .22)); if (q <= 0) continue;
      x.font = '700 46px Helvetica, Arial'; const w = Math.min(420, x.measureText(m.texto).width + 60), h = 96;
      const xx = m.lado === 'out' ? 512 - 24 - w : 24;
      x.save(); x.translate(xx + (m.lado === 'out' ? w : 0), y + h); x.scale(q, q); x.translate(-(xx + (m.lado === 'out' ? w : 0)), -(y + h));
      x.fillStyle = m.lado === 'out' ? '#7b4dff' : '#efeff4'; x.beginPath(); x.roundRect(xx, y, w, h, 44); x.fill();
      x.fillStyle = m.lado === 'out' ? '#fff' : '#151018'; x.fillText(m.texto, xx + 30, y + 64); x.restore();
      y += h + 26;
    }
    tl.t.needsUpdate = true;
  } };
}

// gaveta: arquivo de aço; a gaveta de cima abre (p.abre) e transborda papel de orçamento
function gaveta(op) {
  const g = new THREE.Group(); const aco = toon('#8d9aa6'), aco2 = toon('#6f7c88');
  const corpo = caixa(.8, 1.5, .75, aco); corpo.position.y = .75; g.add(corpo);
  const gavs = [];
  for (let i = 0; i < 3; i++) { const gv = new THREE.Group(); const fr = caixa(.72, .42, .06, aco2); gv.add(fr);
    const pux = caixa(.2, .05, .06, '#d9dee3'); pux.position.set(0, .05, .05); gv.add(pux);
    const et = new THREE.Mesh(new THREE.PlaneGeometry(.18, .08), toon('#fdfaf6')); et.position.set(0, .14, .032); gv.add(et);
    gv.position.set(0, 1.25 - i * .47, .38); g.add(gv); gavs.push(gv); }
  const dentro = caixa(.66, .36, .7, '#59646f'); dentro.position.set(0, 0, -.38); gavs[0].add(dentro);
  const papelTex = placaTexto(['ORÇAMENTO', '———', '———'], { w: 256, h: 320, fundo: '#fdfaf6', cor: '#2c3e50', bw: 6, raio: 6, fonte: '900 34px Arial, sans-serif', gap: 1.6 });
  const pm = toon('#fff', { map: papelTex, side: THREE.DoubleSide });
  const monte = new THREE.Group(); gavs[0].add(monte);
  for (let i = 0; i < 26; i++) { const pp = new THREE.Mesh(new THREE.PlaneGeometry(.21, .28), pm); pp.castShadow = true; const r = rnd(i * 13 + 5);
    pp.position.set((r() - .5) * .45, .1 + r() * .25, -.38 + (r() - .5) * .5); pp.rotation.set(-1.2 + r() * .8, r() * 3, (r() - .5) * .8); monte.add(pp); }
  const voam = [];
  for (let i = 0; i < 40; i++) { const r = rnd(i * 7 + 99); const pp = new THREE.Mesh(new THREE.PlaneGeometry(.21, .28), pm); pp.castShadow = true;
    pp.userData = { vx: (r() - .5) * 2.2, vy: 1.6 + r() * 2.2, vz: .4 + r() * 1.4, rx: (r() - .5) * 9, rz: (r() - .5) * 9, atraso: r() * .5, chao: r() * .06 };
    g.add(pp); voam.push(pp); }
  return { raiz: g, atualizar(l, p = {}) {
    const ab = p.abre ?? 99, k = saida((l - (ab - .18)) / .18);
    gavs[0].position.z = .38 + k * .55; monte.visible = k > 0; monte.position.y = k * .12;
    const ex = p.transborda ?? (p.abre != null ? ab + .05 : 99);
    voam.forEach(pp => { const u = pp.userData, q = l - ex - u.atraso;
      if (q < 0 || p.transborda === false) { pp.visible = false; return; } pp.visible = true;
      let y = 1.35 + u.vy * q - 4.9 * q * q; const x = u.vx * q, z = .9 + u.vz * q;
      if (y < .01 + u.chao) { y = .01 + u.chao; pp.rotation.set(-Math.PI / 2, u.rz, 0); } else pp.rotation.set(u.rx * q, 0, u.rz * q);
      pp.position.set(x, y, z); });
  } };
}

// aquário: tanque de vidro cheio de peixe nadando (vivo: os peixes e as bolhas são a vida do quadro)
function aquario(op) {
  const g = new THREE.Group(); const W = op.w || 3.2, H = op.h || 1.7, D = op.d || 1.3;
  const base = caixa(W + .2, .5, D + .2, '#2c3e50'); base.position.y = .25; g.add(base);
  const agua = new THREE.Mesh(new THREE.BoxGeometry(W, H * .9, D), semOutline(new THREE.MeshToonMaterial({ color: '#4fc3e8', transparent: true, opacity: .32, depthWrite: false })));
  agua.position.y = .5 + H * .45; agua.renderOrder = 3; g.add(agua);
  const sup = new THREE.Mesh(new THREE.PlaneGeometry(W, D), semOutline(new THREE.MeshBasicMaterial({ color: '#bff0ff', transparent: true, opacity: .45, depthWrite: false })));
  sup.rotation.x = -Math.PI / 2; sup.position.y = .5 + H * .9; g.add(sup);
  const vidroM = toon('#bfe9f5', { transparent: true, opacity: .12, depthWrite: false }); vidroM.userData.outlineParameters = { thickness: .004, color: [0.1, 0.2, 0.25] };
  const vidro = new THREE.Mesh(new THREE.BoxGeometry(W + .04, H, D + .04), vidroM); vidro.position.y = .5 + H / 2; g.add(vidro);
  for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { const q = caixa(.05, H, .05, '#151018'); q.position.set(x * W / 2, .5 + H / 2, z * D / 2); g.add(q); }
  const areia = caixa(W - .02, .14, D - .02, '#f1d79a'); areia.position.y = .57; g.add(areia);
  const r = rnd(op.semente || 3);
  const algas = [];
  for (let i = 0; i < 14; i++) { const a = new THREE.Group(); const h = .4 + r() * .7; const c = toon(['#3fae5a', '#2f8f4a', '#5cc46a'][i % 3]);
    for (let j = 0; j < 4; j++) { const s = malha(new THREE.ConeGeometry(.05 - j * .008, h / 4 + .05, 6), c); s.position.y = j * h / 4 + h / 8; a.add(s); }
    a.position.set((r() - .5) * (W - .3), .62, (r() - .5) * (D - .3) - .1); g.add(a); algas.push([a, r() * 6]); }
  for (let i = 0; i < 7; i++) { const pd = malha(new THREE.DodecahedronGeometry(.1 + r() * .12), toon(['#9aa3ad', '#7a8591', '#c9b28a'][i % 3])); pd.position.set((r() - .5) * (W - .4), .66, (r() - .5) * (D - .3)); g.add(pd); }
  const peixes = []; const cores = ['#ff8a2a', '#ffd23a', '#e8423a', '#7b4dff', '#2ec4e8', '#ff6fae', '#5cc46a'];
  for (let i = 0; i < (op.peixes || 26); i++) { const f = new THREE.Group(); const c = toon(cores[i % cores.length]); const s = .7 + r() * .6;
    const corpo = malha(new THREE.SphereGeometry(.09, 16, 12), c); corpo.scale.set(1.5, 1, .6); f.add(corpo);
    const rabo = malha(new THREE.ConeGeometry(.07, .12, 4), c); rabo.rotation.z = Math.PI / 2; rabo.position.x = -.17; rabo.scale.z = .3; f.add(rabo);
    for (const zz of [-1, 1]) { const o = malha(new THREE.SphereGeometry(.022, 8, 6), toon('#fff')); o.position.set(.08, .025, zz * .045); f.add(o);
      const pu = new THREE.Mesh(new THREE.SphereGeometry(.012, 6, 5), semOutline(new THREE.MeshBasicMaterial({ color: '#151018' }))); pu.position.set(.095, .025, zz * .058); f.add(pu); }
    f.scale.setScalar(s); g.add(f);
    peixes.push({ f, a: (W / 2 - .3) * (.5 + r() * .5), b: (D / 2 - .2) * (.4 + r() * .6), y: .8 + r() * (H * .9 - .55), w: (.25 + r() * .35) * (r() < .5 ? 1 : -1), ph: r() * 6, rabo }); }
  const bolhas = []; for (let i = 0; i < 18; i++) { const b = new THREE.Mesh(new THREE.SphereGeometry(.025, 8, 6), semOutline(new THREE.MeshBasicMaterial({ color: '#e8fbff', transparent: true, opacity: .8 })));
    g.add(b); bolhas.push([b, r() * 4, (r() - .5) * W * .8, (r() - .5) * D * .6]); }
  // linha e anzol (p.linha: [x,y,z] do ponto da vara no mundo; o anzol fica parado na água, sem peixe)
  const lm = new THREE.LineBasicMaterial({ color: '#151018' }); const lgeo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
  const linha = new THREE.Line(lgeo, lm); linha.frustumCulled = false; g.add(linha);
  const anzol = malha(new THREE.TorusGeometry(.04, .008, 6, 12, Math.PI * 1.4), toon('#9aa3ad')); g.add(anzol);
  const boia = malha(new THREE.SphereGeometry(.05, 12, 10), toon('#e8423a')); g.add(boia);
  const tmp = new THREE.Vector3();
  return { raiz: g, atualizar(l, p = {}, ctx = {}) {
    const t = ctx.t || l;
    for (const q of peixes) { const ang = t * q.w + q.ph; q.f.position.set(Math.cos(ang) * q.a, q.y + Math.sin(t * 1.3 + q.ph) * .05, Math.sin(ang) * q.b);
      q.f.rotation.y = -ang - Math.PI / 2 * Math.sign(q.w); q.rabo.rotation.y = Math.sin(t * 9 + q.ph) * .5; }
    for (const [a, ph] of algas) { a.rotation.z = Math.sin(t * 1.4 + ph) * .12; a.rotation.x = Math.cos(t * 1.1 + ph) * .08; }
    for (const [b, ph, x, z] of bolhas) { const y = ((t * .5 + ph) % 1.6); b.position.set(x + Math.sin(t * 3 + ph) * .03, .65 + y, z); b.visible = y < H * .85 - .1; }
    const vara = p.vara && ctx.ponto ? ctx.ponto(p.vara, 'ponta') : null;
    linha.visible = anzol.visible = boia.visible = !!vara;
    if (vara) { const ini = g.worldToLocal(tmp.copy(vara)); const fim = new THREE.Vector3(...(p.anzol || [.2, .5 + H * .5, .1]));
      const pos = lgeo.attributes.position; pos.setXYZ(0, ini.x, ini.y, ini.z); pos.setXYZ(1, fim.x, fim.y, fim.z); pos.needsUpdate = true;
      anzol.position.copy(fim); boia.position.set(fim.x, .5 + H * .9, fim.z); }
  } };
}

// balão de fala ou pensamento: sempre virado pra câmera, pipoca no quadro da palavra (p {texto, em, ate})
function balao(op) {
  const g = new THREE.Group(); let ult = '', mesh = null;
  const desenhar = (texto, tipo) => {
    const { g: x, t } = canvas(768, 420); x.lineWidth = 14; x.strokeStyle = '#151018'; x.fillStyle = '#fff';
    if (tipo === 'pensa') { for (const [cx, cy, r] of [[150, 200, 110], [300, 140, 130], [470, 140, 130], [610, 200, 110], [470, 260, 120], [300, 260, 120]]) { x.beginPath(); x.arc(cx, cy, r, 0, Math.PI * 2); x.stroke(); }
      for (const [cx, cy, r] of [[150, 200, 110], [300, 140, 130], [470, 140, 130], [610, 200, 110], [470, 260, 120], [300, 260, 120]]) { x.beginPath(); x.arc(cx, cy, r - 7, 0, Math.PI * 2); x.fill(); }
      for (const [cx, cy, r] of [[150, 365, 22], [100, 400, 12]]) { x.beginPath(); x.arc(cx, cy, r, 0, Math.PI * 2); x.fill(); x.stroke(); } }
    else { x.beginPath(); x.roundRect(20, 20, 728, 300, 80); x.moveTo(170, 316); x.lineTo(120, 405); x.lineTo(270, 316); x.fill(); x.stroke();
      x.fillStyle = '#fff'; x.fillRect(176, 300, 88, 24); }
    x.fillStyle = '#151018'; x.textAlign = 'center'; x.textBaseline = 'middle'; let tam = 92; x.font = `900 ${tam}px "Arial Black", sans-serif`;
    while (x.measureText(texto).width > 600 && tam > 40) { tam -= 4; x.font = `900 ${tam}px "Arial Black", sans-serif`; }
    x.fillText(texto, 384, tipo === 'pensa' ? 200 : 172);
    if (mesh) { g.remove(mesh); }
    mesh = new THREE.Mesh(new THREE.PlaneGeometry(1.28, .7), semOutline(new THREE.MeshBasicMaterial({ map: t, transparent: true, toneMapped: false, depthTest: op.frente ? false : true })));
    mesh.position.set(.5, .3, 0); mesh.renderOrder = 10; g.add(mesh);
  };
  return { raiz: g, atualizar(l, p = {}, ctx = {}) {
    const texto = p.texto ?? op.texto ?? '', tipo = p.tipo || op.tipo || 'fala';
    if (texto + tipo !== ult) { desenhar(texto, tipo); ult = texto + tipo; }
    const em = p.em ?? 99, ate = p.ate ?? 99;
    const k = l < ate ? pop(l, em) : 1 - clamp((l - ate) / .12);
    g.visible = k > .001; g.scale.setScalar(Math.max(.001, k) * (op.escala || p.escala || 1));
    if (ctx.camera) g.quaternion.copy(ctx.camera.quaternion);
  } };
}

// etiqueta pendurada (p {texto, em}): pipoca com mola no quadro da palavra; vira pra câmera só no eixo Y
function etiqueta(op) {
  const g = new THREE.Group(); const cor = op.cor || '#ffd23a';
  const tt = placaTexto(op.linhas || [op.texto || ''], { w: 768, h: op.linhas?.length > 1 ? 340 : 220, fundo: cor, fonte: '900 88px "Arial Black", sans-serif', bw: 16, raio: 40 });
  const h = op.linhas?.length > 1 ? .62 : .4;
  const pl = new THREE.Mesh(new THREE.BoxGeometry(1.4, h, .04), [toon(cor), toon(cor), toon(cor), toon(cor), toon('#fff', { map: tt }), toon(cor)]); g.add(pl);
  const fio = cil(.008, .008, .3, 6, '#151018'); fio.position.y = h / 2 + .15; g.add(fio);
  return { raiz: g, atualizar(l, p = {}, ctx = {}) {
    const em = p.em ?? 99; const k = pop(l, em); g.visible = k > .001; g.scale.setScalar(Math.max(.001, k) * (op.escala || 1));
    g.rotation.z = (1 - clamp((l - em) / .4)) * Math.sin(l * 18) * .12;
  } };
}

// urna (eleição): bipa e mostra FIM no quadro da palavra (p.fim)
function urna(op) {
  const g = new THREE.Group();
  g.add(caixa(.7, .2, .5, '#e9e2cf'));
  const tampa = caixa(.7, .32, .06, '#e9e2cf'); tampa.position.set(0, .26, -.22); tampa.rotation.x = -.35; g.add(tampa);
  const fimT = placaTexto(['FIM'], { w: 256, h: 160, fundo: '#e8fbe8', cor: '#151018', fonte: '900 100px Arial, sans-serif', bw: 4, raio: 4 });
  const vazioT = placaTexto([''], { w: 256, h: 160, fundo: '#cfe3ef', bw: 4, raio: 4 });
  const tela = new THREE.Mesh(new THREE.PlaneGeometry(.38, .22), basica(vazioT)); tela.position.set(-.08, .27, -.185); tela.rotation.x = -.35; g.add(tela);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) { const b = caixa(.05, .02, .04, i === 3 && j === 2 ? '#3fae5a' : '#151018'); b.position.set(.17 + j * .06, .11, -.12 + i * .06); g.add(b); }
  return { raiz: g, atualizar(l, p = {}) { const on = l >= (p.fim ?? 99); tela.material.map = on ? fimT : vazioT; tela.material.needsUpdate = true; } };
}

// confete / chuva de moedas (p {em, dura}): cai do alto a partir do quadro da palavra
function confete(op) {
  const g = new THREE.Group(); const r = rnd(op.semente || 21); const ps = [];
  const cores = op.moedas ? ['#f2c230'] : ['#e8423a', '#ffd23a', '#2ec4e8', '#5cc46a', '#7b4dff', '#ff6fae'];
  const geo = op.moedas ? new THREE.CylinderGeometry(.07, .07, .02, 14) : new THREE.PlaneGeometry(.06, .1);
  for (let i = 0; i < (op.n || 120); i++) { const m = new THREE.Mesh(geo, op.moedas ? toon(cores[0]) : semOutline(toon(cores[i % cores.length], { side: THREE.DoubleSide })));
    m.userData = { x: (r() - .5) * (op.w || 4), z: (r() - .5) * (op.d || 2), y0: (op.h || 3) + r() * 1.5, v: .8 + r() * 1.2, ph: r() * 6, at: r() * .6 }; g.add(m); ps.push(m); }
  return { raiz: g, atualizar(l, p = {}) {
    const em = p.em ?? 99;
    for (const m of ps) { const u = m.userData, q = l - em - u.at; if (q < 0) { m.visible = false; continue; } m.visible = true;
      const y = Math.max(.02, u.y0 - q * u.v * (op.moedas ? 1.8 : 1)); m.position.set(u.x + Math.sin(q * 3 + u.ph) * .15, y, u.z);
      m.rotation.set(q * 5 + u.ph, q * 3, q * 4); if (y <= .02) m.rotation.set(op.moedas ? 0 : -Math.PI / 2, u.ph, 0); }
  } };
}

// ondas do grito (megafone): anéis que saem do ponto (p {de, ate})
function ondas(op) {
  const g = new THREE.Group(); const an = [];
  for (let i = 0; i < 5; i++) { const m = semOutline(new THREE.MeshBasicMaterial({ color: op.cor || '#ffd23a', transparent: true, toneMapped: false }));
    const a = new THREE.Mesh(new THREE.TorusGeometry(.3, .03, 6, 32, Math.PI * .7), m); a.rotation.z = Math.PI * .65; g.add(a); an.push(a); }
  return { raiz: g, atualizar(l, p = {}) {
    const de = p.de ?? 99, ate = p.ate ?? 99;
    an.forEach((a, i) => { const q = ((l - de) * 1.6 + i / 5) % 1; const on = l >= de && l < ate + .6 && (l - de) * 1.6 + i / 5 >= 0 && !(l > ate && q < .3);
      a.visible = on; a.scale.setScalar(.4 + q * 3); a.position.z = q * 1.2; a.material.opacity = 1 - q; });
  } };
}

// holofote: cone de luz que acende no quadro da palavra (p.em)
function holofote(op) {
  const g = new THREE.Group();
  const cone = new THREE.Mesh(new THREE.ConeGeometry(.75, 3.4, 32, 1, true), semOutline(new THREE.MeshBasicMaterial({ color: '#fff3b0', transparent: true, opacity: .22, depthWrite: false, side: THREE.DoubleSide, toneMapped: false })));
  cone.position.y = 1.7; g.add(cone);
  const disco = new THREE.Mesh(new THREE.CircleGeometry(.75, 32), semOutline(new THREE.MeshBasicMaterial({ color: '#fff3b0', transparent: true, opacity: .5, depthWrite: false, toneMapped: false })));
  disco.rotation.x = -Math.PI / 2; disco.position.y = .015; g.add(disco);
  const sp = new THREE.SpotLight('#ffe6a8', 0, 6, .42, .5, 1.2); sp.position.set(0, 3.6, 0); sp.target.position.set(0, 0, 0); sp.castShadow = true; g.add(sp, sp.target);
  return { raiz: g, atualizar(l, p = {}) { const on = l >= (p.em ?? 99); g.visible = on; const k = clamp((l - (p.em ?? 0)) / .08); cone.material.opacity = .08 * k; disco.material.opacity = .22 * k; sp.intensity = 9 * k; } };
}

// imagem: print ou foto do produto (material do cliente) num quadro dentro da cena, que aparece com mola na palavra (p.em).
// op.arquivo (relativo ao cenas.json); o motor carrega antes do 1º quadro (op._tex). op.moldura: cor da borda; op.w: largura (m).
function imagem(op) {
  const g = new THREE.Group(); const t = op._tex; const asp = t && t.image ? t.image.height / t.image.width : 1.3; const w = op.w || .6, h = w * asp;
  const fundo = caixa(w + .05, h + .05, .03, op.moldura || '#151018'); g.add(fundo);
  const tela = new THREE.Mesh(new THREE.PlaneGeometry(w, h), semOutline(new THREE.MeshBasicMaterial({ map: t || null, color: t ? '#ffffff' : '#888888' }))); tela.material.userData._hdr = 1; tela.position.z = .017; g.add(tela);
  return { raiz: g, atualizar(l, p = {}) { const k = p.em == null ? 1 : pop(l, p.em); g.scale.setScalar(Math.max(.001, k)); } };
}

export const OBJETOS = { imagem, contador, pilha, medidor, calendario, placa, celular, gaveta, aquario, balao, etiqueta, urna, confete, ondas, holofote };

// props de mão (o motor prende na mão do personagem): celular, megafone, vara, papel
export function prop(tipo) {
  const g = new THREE.Group();
  if (tipo === 'celular') { const c = caixa(.09, .17, .016, '#1d1f27'); c.position.set(0, -.04, .06); c.rotation.x = -.3; g.add(c);
    const tl = new THREE.Mesh(new THREE.PlaneGeometry(.078, .15), semOutline(new THREE.MeshBasicMaterial({ color: '#cfe0ff' }))); tl.position.set(0, -.04, .07); tl.rotation.x = -.3; g.add(tl); }
  if (tipo === 'megafone') { const c = cil(.035, .13, .32, 20, toon('#e8423a')); c.rotation.x = Math.PI / 2; c.position.set(0, .02, .2); g.add(c);
    const b = cil(.13, .13, .02, 20, toon('#fdfaf6')); b.rotation.x = Math.PI / 2; b.position.set(0, .02, .36); g.add(b);
    const p = caixa(.04, .12, .04, '#151018'); p.position.set(0, -.04, .06); g.add(p); }
  if (tipo === 'vara') { const v = cil(.012, .02, 1.8, 8, toon('#8a5428')); v.rotation.x = Math.PI / 2 - .5; v.position.set(0, .4, .75); g.add(v);
    const m = cil(.04, .04, .05, 12, toon('#9aa3ad')); m.rotation.z = Math.PI / 2; m.position.set(.05, 0, .08); g.add(m);
    const ponta = new THREE.Object3D(); ponta.position.set(0, .82, 1.53); ponta.name = 'ponta'; g.add(ponta); }
  if (tipo === 'papel') { const p = new THREE.Mesh(new THREE.PlaneGeometry(.21, .28), toon('#fff', { map: placaTexto(['ORÇAMENTO', '———', '———'], { w: 256, h: 320, fundo: '#fdfaf6', cor: '#2c3e50', bw: 6, raio: 6, fonte: '900 34px Arial, sans-serif', gap: 1.6 }), side: THREE.DoubleSide }));
    p.position.set(0, .02, .1); p.rotation.x = -.4; g.add(p); }
  return g;
}
