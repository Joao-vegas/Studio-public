// Explicador 3D · motor (a gramática do Desenho 3D com a cara de jogo antigo realista do Loaded Dice: PBR, sombra suave,
// luz de cinema quente/neon, profundidade de campo, glow, grade de cor, vinheta e grão; sem contorno de tinta). Lê window.PLANO (cenas.json planejado pelo render.py) e desenha o segundo t em seek(t). Nada de relógio.
// Gramática de movimento (medida na referência, ver COMO-FAZER): parado é parado (nada respira); gesto de ~5 quadros que
// termina 4 quadros ANTES da palavra e a cabeça termina 3 quadros depois da mão; rosto troca inteiro atrás de uma piscada
// (meio fechado, fechado, rosto novo: o novo entra 2 quadros antes da palavra); a câmera nunca para (creep, acelera na
// entrada do plano e o plano velho segue andando no dissolve de 6 quadros); número = objeto físico (objetos.js).
import * as THREE from 'three';
import { MUNDOS } from './mundos.js';
import { criarPessoa, POSES } from './gente.js';
import { OBJETOS, prop } from './objetos.js';
import { resolverElenco } from './elenco.js';

const P = window.PLANO;
const W = P.largura || 1080, H = P.altura || 1920, FPS = P.fps || 30, F = 1 / FPS;
const DISS = (P.estilo && P.estilo.dissolve) ?? 6 / 30;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const suave = x => { x = clamp(x); return x * x * (3 - 2 * x); };
const cubica = x => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const $ = id => document.getElementById(id);
const v3 = a => new THREE.Vector3(...a);

const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(1); renderer.setSize(W, H);
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.NoToneMapping;   // o tom (ACES) e o sRGB saem no acabamento
$('palco').prepend(renderer.domElement);
const EST = P.estilo || {};
const camera = new THREE.PerspectiveCamera(35, W / H, .05, 300);
function alvo() { const rt = new THREE.WebGLRenderTarget(W, H, { samples: 4, type: THREE.HalfFloatType });
  rt.depthTexture = new THREE.DepthTexture(W, H); rt.depthTexture.type = THREE.FloatType; return rt; }
const rtA = alvo(), rtB = alvo();

// ── acabamento: profundidade de campo (foco no alvo da câmera) + glow do que acende + ACES + grade de cinema
//    (sombra azulada, luz quente) + brilho de borda opcional (cena.brilho) + vinheta + grão. Dissolve = mistura A/B.
const post = new THREE.ShaderMaterial({
  uniforms: { tA: { value: rtA.texture }, tB: { value: rtB.texture }, dA: { value: rtA.depthTexture }, dB: { value: rtB.depthTexture },
    fA: { value: 3 }, fB: { value: 3 }, k: { value: 0 }, semente: { value: 0 }, res: { value: new THREE.Vector2(W, H) },
    perto: { value: .05 }, longe: { value: 300 }, desfoque: { value: EST.desfoque ?? 1 }, expo: { value: EST.exposicao ?? 1.05 },
    bA: { value: new THREE.Vector4(0, 0, 0, 0) }, bB: { value: new THREE.Vector4(0, 0, 0, 0) }, chic: { value: 0 }, flash: { value: 0 } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0., 1.); }',
  fragmentShader: `
    uniform sampler2D tA, tB, dA, dB; uniform float fA, fB, k, semente, perto, longe, desfoque, expo, chic, flash; uniform vec2 res; uniform vec4 bA, bB; varying vec2 vUv;
    float lin(float z){ return perto * longe / (longe - z * (longe - perto)); }
    float coc(float z, float f){ float d = lin(z); return clamp(abs(1. / max(d, .05) - 1. / max(f, .05)) * 26. * desfoque, 0., 8.); }   // em dioptria: foco longe = tudo nítido
    vec3 dof(sampler2D t, sampler2D dt, float f, vec2 uv){
      float c0 = coc(texture2D(dt, uv).r, f); vec3 soma = texture2D(t, uv).rgb; float w = 1.;
      if (c0 < .6) return soma;
      for (int i = 0; i < 20; i++) { float a = float(i) * 2.39996; float r = sqrt(float(i) + .5) / sqrt(20.) * c0;
        vec2 o = vec2(cos(a), sin(a)) * r / res; float ci = coc(texture2D(dt, uv + o).r, f);
        float wi = smoothstep(0., 1., ci / max(r, .5)); soma += texture2D(t, uv + o).rgb * wi; w += wi; }
      return soma / w; }
    vec3 brilho(sampler2D t, vec2 uv){ vec3 g = vec3(0.);
      for (int i = 0; i < 12; i++) { float a = float(i) / 12. * 6.2832;
        for (int j = 1; j <= 3; j++) { vec2 o = vec2(cos(a), sin(a)) * float(j * j) * 7. / res;
          vec3 s = texture2D(t, uv + o).rgb; g += s * smoothstep(1.0, 2.2, max(s.r, max(s.g, s.b))) / float(j); } }
      return g / 20.; }
    vec3 aces(vec3 x){ const float a = 2.51, b = .03, c = 2.43, d = .59, e = .14; return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0., 1.); }
    float hash(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32 + semente); return fract(p.x * p.y); }
    vec3 srgb(vec3 c){ c = max(c, 0.); return mix(c * 12.92, 1.055 * pow(c, vec3(1. / 2.4)) - .055, step(.0031308, c)); }
    vec3 borda(vec4 b, vec2 uv){ if (b.w <= 0.) return vec3(0.); vec2 q = min(uv, 1. - uv); float e = min(q.x * res.x / res.y, q.y);
      return b.rgb * b.w * pow(1. - smoothstep(0., .045, e), 2.); }
    void main(){
      vec3 a = dof(tA, dA, fA, vUv) + brilho(tA, vUv) * 1.1;
      if (chic > 0.) { vec3 m = vec3(0.); for (int i = -6; i <= 6; i++) m += texture2D(tA, vUv + vec2(float(i) * chic / 6. / res.x, 0.)).rgb; a = m / 13.; }
      vec3 c = a;
      if (k > 0.) { vec3 b = dof(tB, dB, fB, vUv) + brilho(tB, vUv) * 1.1; c = mix(a, b, k); }
      c += mix(borda(bA, vUv), borda(bB, vUv), k);
      c += vec3(flash);
      c = aces(c * expo);
      float l = dot(c, vec3(.2126, .7152, .0722));
      c = mix(c * vec3(.92, .98, 1.08), c * vec3(1.08, 1.0, .88), smoothstep(.15, .7, l));   // sombra fria, luz quente
      c = mix(vec3(l), c, 1.08);                                                               // um pouco mais de cor
      c = c * c * (3. - 2. * c) * .35 + c * .65;                                                // curva S leve
      vec3 s = srgb(c);
      float d = distance(vUv * vec2(1., res.y / res.x * .75), vec2(.5, .5 * res.y / res.x * .75));
      s *= mix(1., .62, smoothstep(.32, 1.0, d));
      s += (hash(vUv * res + semente) - .5) * .05;
      gl_FragColor = vec4(s, 1.);
    }`,
  depthTest: false, depthWrite: false,
});
const postCena = new THREE.Scene(); const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
postCena.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), post));

// ── elenco, mundos, pessoas, objetos
const ELENCO = resolverElenco(P.elenco || {});
const MUN = {};
// imagens do cliente (print, foto do produto) carregadas antes do 1º quadro: o seek(t) nunca espera rede
const _carga = new THREE.TextureLoader();
for (const op of Object.values(P.mundos || {})) for (const o of op.objetos || []) if (o.tipo === 'imagem' && o.arquivo) {
  try { o._tex = await _carga.loadAsync(o.url || o.arquivo); o._tex.colorSpace = THREE.SRGBColorSpace; } catch (e) { console.warn('imagem não abriu', o.arquivo); } }
for (const [id, op] of Object.entries(P.mundos || {})) {
  const tipo = op.tipo || id;
  if (!MUNDOS[tipo]) throw new Error(`mundo "${tipo}" não existe. Opções: ${Object.keys(MUNDOS).join(', ')}`);
  const cena = new THREE.Scene();
  const m = MUNDOS[tipo](cena, op);
  const gente = (op.gente || []).map(g => {
    const d = ELENCO[g.quem]; if (!d) throw new Error(`"${g.quem}" não está no elenco`);
    const p = criarPessoa({ ...d, ...(g.figurino || {}), _id: undefined });
    cena.add(p.raiz);
    return { ...g, id: g.id || g.quem, p, props: {} };
  });
  const objs = (op.objetos || []).map(o => {
    if (!OBJETOS[o.tipo]) throw new Error(`objeto "${o.tipo}" não existe. Opções: ${Object.keys(OBJETOS).join(', ')}`);
    const ob = OBJETOS[o.tipo](o);
    ob.raiz.position.set(...(o.pos || [0, 0, 0])); ob.raiz.rotation.y = (o.rot || 0) * Math.PI / 180;
    if (o.escala && o.tipo !== 'contador' && o.tipo !== 'balao' && o.tipo !== 'etiqueta') ob.raiz.scale.setScalar(o.escala);
    cena.add(ob.raiz);
    return { ...o, ob };
  });
  cena.traverse(o => { const mt = o.material; if (!mt || Array.isArray(mt) || mt.userData._hdr) return;
    if (mt.isMeshBasicMaterial && !mt.transparent) { mt.userData._hdr = 1; if (!mt.map) mt.color.multiplyScalar(EST.lampada ?? 2.6); }   // tela e print ficam na cor certa   // lâmpada, tela e neon passam de 1: glow
    if (o.isMesh && !o.userData.pessoa) { o.castShadow = o.castShadow !== false; }
    if (o.isHemisphereLight && !o.userData._luz) { o.userData._luz = 1; o.intensity *= EST.ambiente ?? .5; }          // menos luz chapada:
    if (o.isDirectionalLight && !o.userData._luz) { o.userData._luz = 1; o.intensity *= EST.chave ?? 1.25; o.shadow.radius = 4; }   // sombra de cinema
    if (o.isPointLight && !o.userData._luz) { o.userData._luz = 1; o.intensity *= EST.pratica ?? 1.6; o.decay = 1.6; } });
  const fill = new THREE.PointLight(EST.fill_cor || '#ffe9d6', EST.fill ?? 1.2, 7, 1.4); cena.add(fill);   // preenchimento que anda com a câmera (rosto legível)
  MUN[id] = { cena, m, gente, objs, fill };
}

// ── legenda: palavras com tempo da voz, blocos de até 3 palavras (quebra na pontuação e na pausa)
function blocos(c) {
  if (c.legenda === false || P.legenda === false) return [];
  const ps = c.palavras || [];
  const out = []; let cur = [];
  ps.forEach((p, i) => { cur.push(p); const prox = ps[i + 1];
    const fim = /[.,!?:;…]$/.test(p.w) || cur.length >= (c.max_palavras || 3) || !prox || prox.s - p.e > .25;
    if (fim) { out.push({ s: cur[0].s, e: cur[cur.length - 1].e, txt: cur.map(x => x.w).join(' ').replace(/[,;:]$/, '') }); cur = []; } });
  return out;
}
const CENAS = P.cenas.map(c => ({ ...c, _leg: blocos(c) }));
const TODAS = CENAS.flatMap(c => c._leg);

// ── câmera: creep constante, acelera na entrada do plano, continua depois do fim (pro dissolve); "saida" = transição especial
let camGiro = 0;
function cameraEm(c, l) {
  const D = Math.max(.2, c.ate - c.de), cam = c.cam || {};
  const B = cam.impulso ?? 1.4, tau = .32;
  const gq = x => x + B * tau * (1 - Math.exp(-x / tau));
  const f = gq(l) / gq(D);
  const o1 = v3(cam.olha || [0, 1.2, 0]), o2 = v3(cam.olha2 || cam.olha || [0, 1.2, 0]);
  const de = v3(cam.de || [0, 1.6, 5]);
  const para = cam.para ? v3(cam.para) : de.clone().lerp(o1, .05 * D);   // sem "para": aproxima 5% por segundo
  const pos = de.clone().lerp(para, f), alvo = o1.clone().lerp(o2, f);
  let fov = (cam.fov || 38) + ((cam.fov2 ?? cam.fov ?? 38) - (cam.fov || 38)) * f;
  for (const ps of (cam.passos || [])) {   // a câmera trabalha dentro do plano: desliza pro enquadramento novo na palavra (ps.em)
    const du = ps.dura ?? .42, k = cubica((l - (ps.em - du * .6)) / du); if (k <= 0) continue;
    const f2 = clamp((l - ps.em) / Math.max(.3, D - ps.em)); const pd = v3(ps.de), pp = ps.para ? pd.clone().lerp(v3(ps.para), f2) : pd;
    pos.lerp(pp, k); alvo.lerp(v3(ps.olha || ps.de), k); fov += ((ps.fov ?? fov) - fov) * k; }
  const sa = cam.saida;
  if (sa) { const du = sa.dura ?? .45, k = Math.pow(clamp((l - (D - du)) / (du + DISS)), 2.2);
    if (k > 0) { pos.lerp(v3(sa.para), k); alvo.lerp(v3(sa.olha || sa.para), Math.min(1, k * 1.4)); fov += ((sa.fov ?? fov) - fov) * k; } }
  camera.position.copy(pos); camera.fov = fov; camera.updateProjectionMatrix(); camera.lookAt(alvo);
  if (camGiro) camera.rotateY(camGiro * Math.PI / 180);
  if (cam.rolo) camera.rotation.z += cam.rolo * Math.PI / 180;
}

// ── pessoas: estado no instante l do plano. Gesto/rosto/cabeça presos ao "em" (o tempo da palavra, em s dentro do plano)
const GESTO_FIM = 4 * F, GESTO_DUR = 5 * F, CAB_FIM = 1 * F, CAB_DUR = 6 * F;
const POP = { alt: (EST.pop_alt ?? .052), sobe: (EST.pop_quadros ?? 3.5) };
const rad = x => x * Math.PI / 180;
function lerpPose(a, b, k) { return { E: a.E.map((v, i) => v + (b.E[i] - v) * k), D: a.D.map((v, i) => v + (b.D[i] - v) * k) }; }
function poseDe(n) { const p = typeof n === 'object' ? n : POSES[n]; if (!p) throw new Error(`pose "${n}" não existe. Opções: ${Object.keys(POSES).join(', ')}`); return p; }
function yawPara(mu, g, alvo, pos, rot) {
  let pt = null;
  if (Array.isArray(alvo)) pt = v3(alvo);
  else if (alvo === 'camera') pt = camera.position.clone();
  else if (typeof alvo === 'string') { const o = mu.gente.find(x => x.id === alvo); if (o) pt = new THREE.Vector3(o._x ?? o.pos[0], o.p.olhosY + (o._y || 0), o._z ?? o.pos[1]); }
  else if (typeof alvo === 'number') return [alvo, 0];
  if (!pt) return [0, 0];
  let dy = Math.atan2(pt.x - pos[0], pt.z - pos[1]) - rot; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
  const dist = Math.hypot(pt.x - pos[0], pt.z - pos[1]);
  const pitch = -Math.atan2(pt.y - (g.p.olhosY + (g._y || 0)), Math.max(.3, dist));
  return [clamp(dy * 180 / Math.PI, -75, 75), clamp(pitch * 180 / Math.PI, -25, 25)];
}
const hash = (s) => { let h = 2166136261; for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619); return ((h >>> 0) % 1000) / 1000; };
function pessoas(mu, c, l, t) {
  for (const g of mu.gente) {
    const id = g.id;
    const e = { pos: g.pos, y: g.y || 0, rot: g.rot || 0, pose: g.pose || 'neutro', rosto: g.rosto || 'neutro', olha: g.olha ?? 'camera',
      cab: g.cab || [0, 0, 0], senta: !!g.senta, fora: !!g.fora, venda: !!g.venda, props: g.props || {}, olhar: g.olhar || null, inclina: g.inclina || 0,
      ...((c.lugar || {})[id] ? { fora: false } : {}), ...((c.lugar || {})[id] || {}) };
    if (e.fora) { g.p.raiz.visible = false; continue; }
    g.p.raiz.visible = true;
    let pose = poseDe(e.pose), rot = e.rot, x = e.pos[0], z = e.pos[1], passo = 0, pulo = 0, cabOff = e.cab.slice();
    let rosto = e.rosto, olhoForca = null, olhar = e.olhar;
    let olhaDe = e.olha, olhaPara = e.olha, kOlha = 1;
    const acs = (c.acoes || []).filter(a => a.quem === id).sort((a, b) => a.em - b.em);
    let ultimaTroca = -99;
    for (const a of acs) {
      if (a.pose) { const fim = a.em - (a.antes ?? GESTO_FIM), ini = fim - (a.dura ?? GESTO_DUR);
        if (l >= ini) pose = l >= fim ? poseDe(a.pose) : lerpPose(pose, poseDe(a.pose), cubica((l - ini) / (fim - ini))); }
      if (a.rot != null) { const fim = a.em - 3 * F, ini = fim - (a.dura_rot ?? 8 * F);
        if (l >= ini) { let d = a.rot - rot; d = ((d + 540) % 360) - 180; rot = l >= fim ? rot + d : rot + d * cubica((l - ini) / (fim - ini)); } }
      if (a.olha !== undefined) { const fim = a.em - CAB_FIM, ini = fim - CAB_DUR;
        if (l >= ini) { olhaDe = olhaPara; olhaPara = a.olha; kOlha = l >= fim ? 1 : cubica((l - ini) / (fim - ini)); } }
      if (a.cab) { const fim = a.em - CAB_FIM, ini = fim - CAB_DUR; if (l >= ini) { const k = l >= fim ? 1 : cubica((l - ini) / (fim - ini)); cabOff = cabOff.map((v, i) => v + (a.cab[i] - v) * k); } }
      if (a.rosto) { const troca = a.em - 2 * F;
        if (l >= troca) { rosto = a.rosto; olhar = a.olhar ?? olhar; ultimaTroca = troca; }
        else if (l >= troca - 2 * F) { olhoForca = l >= troca - F ? 'piscando' : 'meio-fechado'; ultimaTroca = troca; } }
      if (a.anda) { const dura = a.anda.dura ?? 1, fim = a.em, ini = fim - dura;
        if (l >= ini) { const k = clamp((l - ini) / dura), kk = suave(k); const x0 = x, z0 = z; x = x0 + (a.anda.para[0] - x0) * kk; z = z0 + (a.anda.para[1] - z0) * kk;
          if (k < 1) { rot = Math.atan2(a.anda.para[0] - x0, a.anda.para[1] - z0) * 180 / Math.PI; passo = Math.hypot(x - x0, z - z0) * 7; }
          else if (a.anda.rot != null) rot = a.anda.rot; } }
      if (a.props !== undefined && l >= a.em - GESTO_FIM) e.props = a.props;
      if (a.pulo) { const n = a.pulo.n ?? 2, d = a.pulo.dura ?? .42, h = a.pulo.alt ?? .32, q = l - (a.em - .12);
        if (q >= 0 && q < n * d) { const u = (q % d) / d; pulo = Math.max(pulo, 4 * h * u * (1 - u)); } }
      // pop de reação (medido no Loaded Dice: KxEs8tTORWM q1657/q1666): na 1ª palavra a cabeça/corpo sobe ~20% da altura do
      // rosto em 3-4 quadros e volta com um quique leve até o 8º quadro. Vale em toda ação com rosto (reação/fala), pop:false desliga.
      if ((a.rosto || a.pop) && a.pop !== false && !a.pulo) { const q = (l - a.em) / F, A = (a.pop_alt ?? POP.alt) * (a.pop === 'grande' ? 3.5 : 1), nq = a.pop === 'grande' ? 8 : POP.sobe;
        let o = 0; if (q >= 0 && q < nq) o = A * Math.sin(q / nq * Math.PI / 2);
        else if (q >= nq && q < nq + 5) { const u = (q - nq) / 5; o = A * (Math.cos(u * Math.PI) * .5 + .5) - A * .14 * Math.sin(u * Math.PI); }
        pulo += o; }
    }
    g._x = x; g._z = z; g._y = e.y;
    // piscada natural (só olho, nunca perto de uma troca de rosto)
    if (!olhoForca && !e.venda) { const per = 3.1 + hash(id) * 1.4, fase = hash(id + 'f') * per, q = ((t + fase) % per);
      if (q < 2 * F && Math.abs(l - ultimaTroca) > 6 * F) olhoForca = q < F ? 'meio-fechado' : 'piscando'; }
    if (e.venda) olhoForca = 'nenhum';
    const r = rot * Math.PI / 180;
    const [y0, p0] = yawPara(mu, g, olhaDe, [x, z], r), [y1, p1] = yawPara(mu, g, olhaPara, [x, z], r);
    const cab = [y0 + (y1 - y0) * kOlha + cabOff[0], p0 + (p1 - p0) * kOlha + cabOff[1], cabOff[2]];
    g.p.raiz.position.set(x, 0, z); g.p.raiz.rotation.y = r;
    g.p.aplicar({ braco: pose, cab, rosto, olhoForca, olhar, senta: e.senta, venda: e.venda, passo, pulo, y: e.y, inclina: e.inclina });
    // objetos de mão
    for (const lado of ['E', 'D']) { const tipo = (e.props || {})[lado] || null;
      for (const [k, o] of Object.entries(g.props)) if (k.startsWith(lado + ':')) o.visible = false;
      if (tipo) { const k = lado + ':' + tipo; if (!g.props[k]) { g.props[k] = prop(tipo); g.p.mao(lado).add(g.props[k]); } g.props[k].visible = true; } }
  }
}
function pontoDe(mu, quem, parte) {
  const g = mu.gente.find(x => x.id === quem); if (!g) return null;
  const o = Object.values(g.props).find(p => p.visible && p.getObjectByName(parte));
  return o ? o.getObjectByName(parte).getWorldPosition(new THREE.Vector3()) : null;
}

function renderPlano(c, t, rt) {
  const mu = MUN[c.mundo]; if (!mu) throw new Error(`plano sem mundo válido: ${c.mundo}`);
  const l = t - c.de;
  mu.m.atualizar(t, l, c);
  cameraEm(c, l);
  mu.fill.position.copy(camera.position).add(new THREE.Vector3(.4, .3, 0));
  pessoas(mu, c, l, t);
  mu.cena.updateMatrixWorld(true);
  const ctx = { t, camera, ponto: (q, parte) => pontoDe(mu, q, parte) };
  for (const o of mu.objs) { const p = (c.obj || {})[o.id];
    const vis = p ? !p.fora : !o.fora; o.ob.raiz.visible = vis; if (!vis) continue;
    o.ob.raiz.position.set(...((p && p.pos) || o.pos || [0, 0, 0]));
    o.ob.atualizar(l, p || {}, ctx); }
  renderer.setRenderTarget(rt);
  renderer.setClearColor(0x000000, 1); renderer.clear();
  renderer.render(mu.cena, camera);
  return camera.position.distanceTo(new THREE.Vector3(...((c.cam && (c.cam.foco || c.cam.olha)) || [0, 1.2, 0])));
}

function legenda(t) {
  const b = TODAS.find((x, i) => t >= x.s - .02 && t < (TODAS[i + 1] ? Math.min(TODAS[i + 1].s - .02, x.e + .5) : x.e + .6));
  const el = $('leg'); const txt = b ? b.txt : '';
  if (el.textContent !== txt) el.textContent = txt;
}

// ── transições especiais (catálogo medido no Loaded Dice em estudo-quadros/TRANSICOES-E-POP.md). A troca acontece no MEIO
//    da janela (o objeto cobre a tela) e a palavra nova cai ali: moedas_caem, notas_sobem, wipe (objeto passa na frente),
//    chicote (câmera gira rápido com borrão), flash (branco). Duração em quadros (padrão medido) ou c.trans_q.
const TRQ = { moedas_caem: 14, notas_sobem: 14, wipe: 9, chicote: 10, flash: 6 };
const trCena = new THREE.Scene(); trCena.add(new THREE.HemisphereLight('#fff4dc', '#3a2410', 1.5));
const trLuz = new THREE.DirectionalLight('#ffe2a8', 3.2); trLuz.position.set(1.5, 2.5, 2); trCena.add(trLuz);
const trCam = new THREE.PerspectiveCamera(40, W / H, .05, 300);
const mOver = (o) => { o.depthTest = false; o.depthWrite = false; return o; };
const geoMoeda = new THREE.CylinderGeometry(.045, .045, .009, 22); geoMoeda.rotateX(Math.PI / 2);
const moedas = new THREE.InstancedMesh(geoMoeda, mOver(new THREE.MeshStandardMaterial({ color: '#e6b24a', metalness: .8, roughness: .32, emissive: '#2a1800' })), 320);
const notaTex = (() => { const c = document.createElement('canvas'); c.width = 256; c.height = 116; const g = c.getContext('2d');
  g.fillStyle = '#7fb38a'; g.fillRect(0, 0, 256, 116); g.strokeStyle = '#2f5a3a'; g.lineWidth = 6; g.strokeRect(6, 6, 244, 104);
  g.fillStyle = '#2f5a3a'; g.beginPath(); g.ellipse(128, 58, 30, 36, 0, 0, 7); g.fill(); g.font = '900 40px Arial'; g.fillText('100', 20, 50); g.fillText('100', 172, 100);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; })();
const notas = new THREE.InstancedMesh(new THREE.PlaneGeometry(.2, .09), mOver(new THREE.MeshStandardMaterial({ map: notaTex, side: THREE.DoubleSide, roughness: .8 })), 170);
const ficha = new THREE.Group(); { const f = new THREE.Mesh(new THREE.CylinderGeometry(.5, .5, .08, 40), mOver(new THREE.MeshStandardMaterial({ color: '#b3202c', roughness: .45 })));
  f.rotation.x = Math.PI / 2; ficha.add(f); for (let i = 0; i < 8; i++) { const b = new THREE.Mesh(new THREE.BoxGeometry(.12, .09, .085), mOver(new THREE.MeshStandardMaterial({ color: '#f2efe6' })));
    const a = i / 8 * Math.PI * 2; b.position.set(Math.cos(a) * .44, Math.sin(a) * .44, 0); b.rotation.z = a; ficha.add(b); } }
trCena.add(moedas, notas, ficha);
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _e = new THREE.Euler(), _p = new THREE.Vector3(), _s = new THREE.Vector3(1, 1, 1);
const rr = (i, k) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
function desenhaTrans(tipo, p) {
  moedas.visible = tipo === 'moedas_caem'; notas.visible = tipo === 'notas_sobem'; ficha.visible = tipo === 'wipe';
  if (tipo === 'moedas_caem' || tipo === 'notas_sobem') { const inst = tipo === 'moedas_caem' ? moedas : notas, n = inst.count, sobe = tipo === 'notas_sobem';
    for (let i = 0; i < n; i++) { const d = .55 + rr(i, 1) * .9, hh = d * Math.tan(20 * Math.PI / 180), hw = hh * W / H;
      const y0 = hh * (1.15 + rr(i, 2) * 1.5), v = 3.3 * (.85 + rr(i, 3) * .3); let y = y0 - p * v * hh; if (sobe) y = -y;
      _p.set((rr(i, 4) * 2 - 1) * hw * 1.15, y, -d); _e.set(p * 9 * (rr(i, 5) - .5) + rr(i, 6) * 6, p * 7 * (rr(i, 7) - .5) + rr(i, 8) * 6, rr(i, 9) * 6);
      _q.setFromEuler(_e); _m.compose(_p, _q, _s); inst.setMatrixAt(i, _m); }
    inst.instanceMatrix.needsUpdate = true; }
  if (tipo === 'wipe') { ficha.position.set(1.0 - 2.0 * p, -.05, -.62); ficha.rotation.set(.25, -.4 + p * .8, p * 1.5); }
}
function trJanela(c) { if (!c.trans || !TRQ[c.trans]) return null; const D = (c.trans_q || TRQ[c.trans]) * F; return { a: c.de - D / 2, b: c.de + D / 2, D }; }

window.seek = function (t) {
  let i = CENAS.findIndex(x => t >= x.de && t < x.ate); if (i < 0) i = t < CENAS[0].de ? 0 : CENAS.length - 1;
  // transição especial: a janela fica em volta do c.de do plano novo (o de antes segue até o meio)
  let esp = null; for (const j of [i, i + 1]) { const x = CENAS[j]; const w = x && CENAS[j - 1] && trJanela(x); if (w && t >= w.a && t < w.b) { esp = { c: x, ant: CENAS[j - 1], w, p: (t - w.a) / w.D }; break; } }
  if (esp) { const base = esp.p < .5 ? esp.ant : esp.c; const tipo = esp.c.trans;
    post.uniforms.k.value = 0; post.uniforms.chic.value = tipo === 'chicote' ? Math.sin(esp.p * Math.PI) * 26 : 0; post.uniforms.flash.value = tipo === 'flash' ? Math.sin(esp.p * Math.PI) * 2.6 : 0;
    camGiro = tipo === 'chicote' ? (esp.p < .5 ? esp.p : esp.p - 1) * 70 : 0;
    post.uniforms.fA.value = renderPlano(base, t, rtA); camGiro = 0; post.uniforms.bA.value = new THREE.Vector4(0, 0, 0, 0); post.uniforms.bB.value = post.uniforms.bA.value;
    if (['moedas_caem', 'notas_sobem', 'wipe'].includes(tipo)) { desenhaTrans(tipo, esp.p); renderer.autoClear = false; renderer.setRenderTarget(rtA); renderer.render(trCena, trCam); renderer.autoClear = true; }
    post.uniforms.semente.value = Math.round(t * FPS) % 97; renderer.setRenderTarget(null); renderer.render(postCena, postCam); legenda(t); return null; }
  post.uniforms.chic.value = 0; post.uniforms.flash.value = 0;
  const c = CENAS[i], ant = CENAS[i - 1];
  const dissolve = ant && c.trans !== 'corte' && !TRQ[c.trans] && t < c.de + DISS - 1e-6;
  const brilhoDe = (x, l) => { const b = x.brilho; if (!b) return new THREE.Vector4(0, 0, 0, 0); const cor = new THREE.Color(b.cor || '#ffd23a');
    const de = b.de ?? 0, ate = b.ate ?? 99; const f = Math.min(clamp((l - de) / .12), clamp((ate - l) / .2)); return new THREE.Vector4(cor.r, cor.g, cor.b, (b.forca ?? .6) * f); };
  if (dissolve) { post.uniforms.fA.value = renderPlano(ant, t, rtA); post.uniforms.fB.value = renderPlano(c, t, rtB); post.uniforms.k.value = clamp((t - c.de + F) / (DISS + F));
    post.uniforms.bA.value = brilhoDe(ant, t - ant.de); post.uniforms.bB.value = brilhoDe(c, t - c.de); }
  else { post.uniforms.fA.value = renderPlano(c, t, rtA); post.uniforms.k.value = 0; post.uniforms.bA.value = brilhoDe(c, t - c.de); post.uniforms.bB.value = post.uniforms.bA.value; }
  post.uniforms.semente.value = Math.round(t * FPS) % 97;
  renderer.setRenderTarget(null); renderer.render(postCena, postCam);
  legenda(t);
  return null;
};

await document.fonts.ready;
window.seek(0);
window.pronto = true;
