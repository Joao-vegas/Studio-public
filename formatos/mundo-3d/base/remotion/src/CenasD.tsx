// Cenas 3D do grupo D do Short S001 (17/10/2026): pátios TESLA x BYD vistos de cima, em planta técnica.
// Cada carrinho = 10 mil carros. Cenas: patios_2018, patios_2025, patios_pergunta.
// Peças compartilhadas (Camera) vêm de ./Cenas3D (somente leitura aqui).
import React, {useMemo} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import {Camera} from './Cenas3D';

const W = 1080, H = 1920;
const rad = (g: number) => (g * Math.PI) / 180;
const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const suave = (x: number) => { const k = clamp(x); return k * k * (3 - 2 * k); };
const saltoOut = (k: number) => { const c1 = 2.2, c3 = c1 + 1; const x = clamp(k); return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };

const COR_BG = '#050f24';
const COR_TESLA = '#cfd5dc';
const COR_BYD = '#E21212';
const AZUL_LINHA = '#58c8ff';

// ---------- medidas do pátio (unidades de mundo) ----------
const SLOT_X = 1.0, SLOT_Z = 1.85;   // espaço de cada vaga
const GAP = 4.0;                      // vão entre os dois pátios

// ---------- carrinho: caixa arredondada + cabine + 4 rodas, uma malha só (3 materiais por grupo) ----------
const caixaArredondada = (w: number, l: number, h: number, r: number, bisel: number) => {
  const s = new THREE.Shape();
  const x = -w / 2, z = -l / 2;
  s.moveTo(x + r, z); s.lineTo(x + w - r, z); s.quadraticCurveTo(x + w, z, x + w, z + r);
  s.lineTo(x + w, z + l - r); s.quadraticCurveTo(x + w, z + l, x + w - r, z + l);
  s.lineTo(x + r, z + l); s.quadraticCurveTo(x, z + l, x, z + l - r);
  s.lineTo(x, z + r); s.quadraticCurveTo(x, z, x + r, z);
  const g = new THREE.ExtrudeGeometry(s, {depth: h, bevelEnabled: true, bevelThickness: bisel, bevelSize: bisel, bevelSegments: 2, curveSegments: 5});
  g.rotateX(Math.PI / 2);          // extrusão passa a apontar para baixo (y negativo)
  g.translate(0, h, 0);            // base em y = 0, topo em y = h
  return g.toNonIndexed();
};

const useCarroGeo = () => useMemo(() => {
  const corpo = caixaArredondada(0.8, 1.55, 0.26, 0.18, 0.04);
  const cabine = caixaArredondada(0.6, 0.8, 0.18, 0.14, 0.04); cabine.translate(0, 0.3, -0.05);
  const rodas: THREE.BufferGeometry[] = [];
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    const c = new THREE.CylinderGeometry(0.17, 0.17, 0.13, 14); c.rotateZ(Math.PI / 2); c.translate(sx * 0.4, 0.17, sz * 0.5); rodas.push(c.toNonIndexed());
  }
  const rodasM = mergeGeometries(rodas)!;
  // posição 0 = corpo, 1 = cabine, 2 = rodas (ordem dos grupos)
  const g = mergeGeometries([corpo, cabine, rodasM], true)!;
  return g;
}, []);

const useMats = () => useMemo(() => {
  const mk = (cor: string, rug = 0.45, met = 0.15) => new THREE.MeshStandardMaterial({color: cor, roughness: rug, metalness: met});
  const vidro = mk('#16202e', 0.2, 0.4), roda = mk('#0b0d12', 0.8, 0);
  return {
    tesla: [mk(COR_TESLA, 0.4, 0.2), vidro, roda] as THREE.Material[],
    byd: [mk(COR_BYD, 0.35, 0.25), vidro, roda] as THREE.Material[],
  };
}, []);

// ---------- texto em textura (plano) ----------
const useTexto = (txt: string, cor: string, peso = 800, larg = 1024, alt = 256) => useMemo(() => {
  const cv = document.createElement('canvas'); cv.width = larg; cv.height = alt;
  const c = cv.getContext('2d')!;
  c.clearRect(0, 0, larg, alt);
  let px = alt * 0.78;
  c.font = `${peso} ${px}px "Helvetica Neue", Arial, sans-serif`;
  const m = c.measureText(txt).width;
  if (m > larg * 0.96) { px = px * (larg * 0.96) / m; c.font = `${peso} ${px}px "Helvetica Neue", Arial, sans-serif`; }
  c.textAlign = 'center'; c.textBaseline = 'middle';
  c.fillStyle = cor; c.fillText(txt, larg / 2, alt / 2 + px * 0.04);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}, [txt, cor, peso, larg, alt]);

// Texto deitado na planta (ou inclinado para a câmera, via rotX). largura em unidades de mundo.
const Texto: React.FC<{txt: string; cor?: string; pos: [number, number, number]; larg: number; esc?: number; rotX?: number; peso?: number; opac?: number; razao?: number}> =
  ({txt, cor = '#ffffff', pos, larg, esc = 1, rotX = -Math.PI / 2, peso = 800, opac = 1, razao = 4}) => {
    const tex = useTexto(txt, cor, peso, 1024, Math.round(1024 / razao));
    if (esc <= 0.001) return null;
    return (
      <mesh position={pos} rotation={[rotX, 0, 0]} scale={[esc, esc, 1]} renderOrder={5}>
        <planeGeometry args={[larg, larg / razao]} />
        <meshBasicMaterial map={tex} transparent opacity={opac} toneMapped={false} depthWrite={false} />
      </mesh>
    );
  };

// ---------- chão: papel milimetrado de projeto ----------
const useGrade = () => useMemo(() => {
  const N = 640, cv = document.createElement('canvas'); cv.width = N; cv.height = N;
  const c = cv.getContext('2d')!;
  c.fillStyle = '#071733'; c.fillRect(0, 0, N, N);
  const cel = N / 5;
  c.strokeStyle = 'rgba(88,200,255,0.16)'; c.lineWidth = 2;
  for (let i = 0; i <= 5; i++) { c.beginPath(); c.moveTo(i * cel, 0); c.lineTo(i * cel, N); c.moveTo(0, i * cel); c.lineTo(N, i * cel); c.stroke(); }
  c.strokeStyle = 'rgba(88,200,255,0.4)'; c.lineWidth = 4;
  c.strokeRect(0, 0, N, N);
  const t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(60, 60); t.anisotropy = 16; t.colorSpace = THREE.SRGBColorSpace; return t;
}, []);

const Chao: React.FC = () => {
  const g = useGrade();
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 20]}>
      <planeGeometry args={[300, 300]} />
      <meshBasicMaterial map={g} toneMapped={false} />
    </mesh>
  );
};

// ---------- linhas (contorno do pátio, cruzes de canto) ----------
const Linhas: React.FC<{pts: number[]; cor?: string; opac?: number}> = ({pts, cor = AZUL_LINHA, opac = 0.9}) => {
  const geo = useMemo(() => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(pts), 3)); return g; }, [pts.join(',')]);
  return <lineSegments geometry={geo}><lineBasicMaterial color={cor} transparent opacity={opac} /></lineSegments>;
};

// Base do pátio: laje levemente mais clara + contorno + cruzes nos cantos + marcações das vagas.
const Laje: React.FC<{cx: number; cols: number; linhas: number; z0: number; cor: string; crescer?: number}> = ({cx, cols, linhas, z0, cor, crescer = 1}) => {
  const w = cols * SLOT_X, l = linhas * SLOT_Z * crescer;
  const x0 = cx - w / 2, x1 = cx + w / 2, z1 = z0 + l;
  const y = 0.01;
  const pts: number[] = [];
  const seg = (ax: number, az: number, bx: number, bz: number) => pts.push(ax, y, az, bx, y, bz);
  seg(x0, z0, x1, z0); seg(x1, z0, x1, z1); seg(x1, z1, x0, z1); seg(x0, z1, x0, z0);
  // marcações das colunas
  for (let i = 1; i < cols; i++) seg(x0 + i * SLOT_X, z0, x0 + i * SLOT_X, z1);
  // cruzes de canto
  const k = 0.7;
  for (const [px, pz] of [[x0, z0], [x1, z0], [x0, z1], [x1, z1]]) { seg(px - k, pz, px + k, pz); seg(px, pz - k, px, pz + k); }
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[cx, 0, z0 + l / 2]}>
        <planeGeometry args={[w, Math.max(0.01, l)]} />
        <meshBasicMaterial color={cor} transparent opacity={0.16} depthWrite={false} />
      </mesh>
      <Linhas pts={pts} opac={0.55} />
    </>
  );
};

// Régua lateral: um traço por fileira, rótulo a cada "rotEvery" fileiras. unidade: carros x 10 mil.
const Regua: React.FC<{x: number; z0: number; linhas: number; cols: number; rotEvery: number; lado: 1 | -1}> = ({x, z0, linhas, cols, rotEvery, lado}) => {
  const pts: number[] = [];
  const y = 0.012;
  const z1 = z0 + linhas * SLOT_Z;
  pts.push(x, y, z0, x, y, z1);
  const rotulos: {z: number; txt: string}[] = [];
  for (let i = 0; i <= linhas; i++) {
    const z = z0 + i * SLOT_Z;
    const grande = i % rotEvery === 0;
    const len = grande ? 0.9 : 0.4;
    pts.push(x, y, z, x - lado * len, y, z);
    if (grande && i > 0) {
      const k = i * cols * 10;   // milhares de carros
      rotulos.push({z, txt: k >= 1000 ? `${(k / 1000).toFixed(1)}M` : `${k}K`});
    }
  }
  return (
    <>
      <Linhas pts={pts} opac={0.8} />
      {rotulos.map((r, i) => <Texto key={i} txt={r.txt} pos={[x - lado * 1.7, 0.02, r.z - 0.35]} larg={2.1} cor="#8fd8ff" peso={600} razao={4} />)}
    </>
  );
};

// ---------- um carrinho que salta para dentro ----------
const Carrinho: React.FC<{geo: THREE.BufferGeometry; mats: THREE.Material[]; x: number; z: number; p: number; giro: number}> = ({geo, mats, x, z, p, giro}) => {
  if (p <= 0) return null;
  const e = saltoOut(p);
  const queda = (1 - suave(p * 1.15)) * 6;     // cai de cima
  const esc = clamp(e, 0, 1.25);
  return <mesh geometry={geo} material={mats} position={[x, queda, z]} scale={[esc, esc, esc]} rotation={[0, giro * (1 - p), 0]} />;
};

// ---------- pátio: lista de carrinhos com tempo de entrada ----------
type Item = {x: number; z: number; t0: number};
const layout = (n: number, cols: number, cx: number, z0: number, tempo: (j: number) => number): Item[] => {
  const r: Item[] = [];
  for (let j = 0; j < n; j++) {
    const col = j % cols, lin = Math.floor(j / cols);
    r.push({x: cx - (cols * SLOT_X) / 2 + SLOT_X * (col + 0.5), z: z0 + SLOT_Z * (lin + 0.5), t0: tempo(j)});
  }
  return r;
};

const Patio: React.FC<{itens: Item[]; geo: THREE.BufferGeometry; mats: THREE.Material[]; t: number}> = ({itens, geo, mats, t}) => (
  <>
    {itens.map((it, i) => {
      const p = clamp((t - it.t0) / 0.5);
      return <Carrinho key={i} geo={geo} mats={mats} x={it.x} z={it.z} p={p} giro={0.6 * (i % 2 ? 1 : -1)} />;
    })}
  </>
);

const Luz: React.FC = () => (
  <>
    <ambientLight intensity={1.15} color="#b8d4ff" />
    <directionalLight position={[-12, 30, 10]} intensity={2.6} color="#ffffff" />
    <directionalLight position={[14, 18, -20]} intensity={0.9} color="#58c8ff" />
  </>
);

// Câmera de cima com inclinação leve: alvo no plano, afastada d, inclinada "incl" graus em relação à vertical.
const CamTopo: React.FC<{alvo: [number, number, number]; d: number; incl: number; lado?: number; rolar?: number}> = ({alvo, d, incl, lado = 0, rolar = 0}) => {
  const a = rad(incl), l = rad(lado);
  return <Camera pos={[alvo[0] + Math.sin(l) * d * Math.cos(a) , alvo[1] + Math.cos(a) * d, alvo[2] + Math.sin(a) * d]} alvo={alvo} fov={40} rolar={rolar} />;
};

const fmt = (carros: number, alvoCarros: number, valorFinal: number) => {
  const v = (carros / alvoCarros) * valorFinal;
  return v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : `${Math.round(v / 1000)}K`;
};

const Canvas: React.FC<{children: React.ReactNode}> = ({children}) => (
  <ThreeCanvas width={W} height={H} style={{background: COR_BG}} gl={{antialias: true}}>
    <color attach="background" args={[COR_BG]} />
    {children}
  </ThreeCanvas>
);

// ======================================================================
// CENA 10 · 2018: 25 carrinhos Tesla x 10 BYD, entram um a um com a voz
// ======================================================================
const Patios2018: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const geo = useCarroGeo(); const mats = useMats();
  const cols = 5, cxT = -(cols * SLOT_X) / 2 - GAP / 2, cxB = (cols * SLOT_X) / 2 + GAP / 2, z0 = 0;
  const tesla = useMemo(() => layout(25, cols, cxT, z0, (j) => 0.5 + j * 0.195), []);
  const byd = useMemo(() => layout(10, cols, cxB, z0, (j) => 6.0 + j * 0.17), []);
  // câmera: travelling lento + aproximação, inclinação aumenta
  const alvo: [number, number, number] = [-0.2 + t * 0.1, 0, 4.6 + t * 0.05];
  const d = 56 - t * 1.3, incl = 9 + t * 1.4;
  const popT = suave((t - 5.5) / 0.4), popB = suave((t - 7.6) / 0.4), popR = suave((t - 8.0) / 0.35);
  return (
    <Canvas>
      <CamTopo alvo={alvo} d={d} incl={incl} lado={4 * Math.sin(t * 0.35)} rolar={rad(-1.5 + t * 0.35)} />
      <Luz />
      <Chao />
      <Laje cx={cxT} cols={cols} linhas={5} z0={z0} cor="#cfd5dc" />
      <Laje cx={cxB} cols={cols} linhas={5} z0={z0} cor={COR_BYD} />
      <Regua x={cxT - cols / 2 - 0.5} z0={z0} linhas={5} cols={cols} rotEvery={2} lado={1} />
      <Regua x={cxB + cols / 2 + 0.5} z0={z0} linhas={5} cols={cols} rotEvery={2} lado={-1} />
      <Patio itens={tesla} geo={geo} mats={mats.tesla} t={t} />
      <Patio itens={byd} geo={geo} mats={mats.byd} t={t} />
      <Texto txt="ALL-ELECTRIC CARS SOLD · 2018" pos={[0, 0.02, -9]} larg={15.5} cor="#8fd8ff" peso={700} razao={9} />
      <Texto txt="TESLA" pos={[cxT, 0.02, -2.2]} larg={5} cor={COR_TESLA} />
      <Texto txt="BYD" pos={[cxB, 0.02, -2.2]} larg={5} cor="#ff4a4a" />
      <Texto txt="245K" pos={[cxT, 0.02, -5.7]} larg={5.2} esc={popT} cor="#ffffff" razao={3} />
      <Texto txt="103K" pos={[cxB, 0.02, -5.7]} larg={5.2} esc={popB} cor="#ff6a6a" razao={3} />
      <Texto txt="2.4×" pos={[0, 0.02, 15.8]} larg={7} esc={popR} cor="#ffffff" razao={3} />
      <Texto txt="TESLA SOLD 2.4 TIMES MORE" pos={[0, 0.02, 18.4]} larg={13} esc={popR} cor="#8fd8ff" peso={600} razao={10} />
    </Canvas>
  );
};

// ======================================================================
// CENA 11 · 2025: os pátios crescem em ondas; a BYD passa a Tesla
// ======================================================================
const COLS25 = 10, N_T = 164, N_B = 226, Z0_25 = 0;
const POS_T_X = -(COLS25 * SLOT_X) / 2 - GAP / 2, POS_B_X = (COLS25 * SLOT_X) / 2 + GAP / 2;
const tempoT25 = (j: number) => j < 25 ? -1 : (() => { const k = j - 25; return 0.4 + (Math.floor(k / 6) * 6 / 139) * 7.4 + (k % 6) * 0.03; })();
const tempoB25 = (j: number) => j < 10 ? -1 : (() => { const k = j - 10; return 0.8 + (Math.floor(k / 9) * 9 / 216) * 4.8 + (k % 9) * 0.02; })();

const contagem = (itens: Item[], t: number) => itens.reduce((s, it) => s + (t >= it.t0 + 0.2 ? 1 : 0), 0);

const CenarioCheio: React.FC<{t: number; geo: THREE.BufferGeometry; mats: ReturnType<typeof useMats>; tesla: Item[]; byd: Item[]; ano: string; linhasT: number; linhasB: number}> =
  ({t, geo, mats, tesla, byd, ano, linhasT, linhasB}) => {
    const cT = contagem(tesla, t), cB = contagem(byd, t);
    return (
      <>
        <Luz />
        <Chao />
        <Laje cx={POS_T_X} cols={COLS25} linhas={linhasT} z0={Z0_25} cor="#cfd5dc" />
        <Laje cx={POS_B_X} cols={COLS25} linhas={linhasB} z0={Z0_25} cor={COR_BYD} />
        <Regua x={POS_T_X - COLS25 / 2 - 0.6} z0={Z0_25} linhas={linhasT} cols={COLS25} rotEvery={5} lado={1} />
        <Regua x={POS_B_X + COLS25 / 2 + 0.6} z0={Z0_25} linhas={linhasB} cols={COLS25} rotEvery={5} lado={-1} />
        <Patio itens={tesla} geo={geo} mats={mats.tesla} t={t} />
        <Patio itens={byd} geo={geo} mats={mats.byd} t={t} />
        <Texto txt={`ALL-ELECTRIC CARS SOLD · ${ano}`} pos={[0, 0.02, -13.5]} larg={23} cor="#8fd8ff" peso={700} razao={12} />
        <Texto txt="TESLA" pos={[POS_T_X, 0.02, -2.6]} larg={7.5} cor={COR_TESLA} />
        <Texto txt="BYD" pos={[POS_B_X, 0.02, -2.6]} larg={7.5} cor="#ff4a4a" />
        <Texto txt={fmt(cT, N_T, 1636129)} pos={[POS_T_X, 0.02, -7.8]} larg={9} cor="#ffffff" razao={3} />
        <Texto txt={fmt(cB, N_B, 2256714)} pos={[POS_B_X, 0.02, -7.8]} larg={9} cor="#ff6a6a" razao={3} />
      </>
    );
  };

const LIN_T = Math.ceil(N_T / COLS25), LIN_B = Math.ceil(N_B / COLS25);

const Patios2025: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const geo = useCarroGeo(); const mats = useMats();
  const tesla = useMemo(() => layout(N_T, COLS25, POS_T_X, Z0_25, tempoT25), []);
  const byd = useMemo(() => layout(N_B, COLS25, POS_B_X, Z0_25, tempoB25), []);
  const cB = contagem(byd, t), cT = contagem(tesla, t);
  const linhas = Math.max(cB, cT) / COLS25;
  const zFim = Math.max(8, linhas * SLOT_Z);
  const alvo: [number, number, number] = [0.5 * Math.sin(t * 0.3), 0, (-14 + zFim + 2) / 2 + 0.6 * t];
  const d = 66 + Math.min(18, zFim * 0.32) + t * 0.6;
  return (
    <Canvas>
      <CamTopo alvo={alvo} d={d} incl={8 + t * 0.9} lado={-3 + t * 0.6} rolar={rad(1.2 - t * 0.3)} />
      <CenarioCheio t={t} geo={geo} mats={mats} tesla={tesla} byd={byd} ano="2025" linhasT={Math.max(2.5, cT / COLS25)} linhasB={Math.max(1, cB / COLS25)} />
    </Canvas>
  );
};

// ======================================================================
// CENA 12 · pergunta: pátios cheios + interrogação amarela enorme
// ======================================================================
const useInterrogacao = () => useMemo(() => {
  const pts: THREE.Vector3[] = [];
  for (let a = 165; a >= -50; a -= 15) pts.push(new THREE.Vector3(2.4 * Math.cos(rad(a)), 4 + 2.4 * Math.sin(rad(a)), 0));
  pts.push(new THREE.Vector3(1.1, 1.3, 0), new THREE.Vector3(0.2, 0.3, 0), new THREE.Vector3(0, -0.9, 0));
  const curva = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.5);
  return {gancho: new THREE.TubeGeometry(curva, 80, 0.62, 24, false), ponto: new THREE.SphereGeometry(0.82, 28, 20)};
}, []);

const PatiosPergunta: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const geo = useCarroGeo(); const mats = useMats(); const q = useInterrogacao();
  const tesla = useMemo(() => layout(N_T, COLS25, POS_T_X, Z0_25, () => -9), []);
  const byd = useMemo(() => layout(N_B, COLS25, POS_B_X, Z0_25, () => -9), []);
  const mat = useMemo(() => new THREE.MeshStandardMaterial({color: '#FFD600', emissive: '#c79a00', emissiveIntensity: 0.55, roughness: 0.3, metalness: 0.15}), []);
  const incl = 14 + t * 2.2;
  const alvo: [number, number, number] = [0, 0, 20.5 - t * 0.4];
  const d = 80 + t * 7;
  const entra = suave(t / 0.5);
  const esc = 2.15 * saltoOut(clamp(t / 0.6));
  const elev = rad(90 - incl);
  return (
    <Canvas>
      <CamTopo alvo={alvo} d={d} incl={incl} lado={2 * Math.sin(t * 0.8)} rolar={rad(Math.sin(t * 0.7) * 0.8)} />
      <CenarioCheio t={9} geo={geo} mats={mats} tesla={tesla} byd={byd} ano="2025" linhasT={LIN_T} linhasB={LIN_B} />
      <Texto txt="WHY? THE NUMBERS DON'T SAY" pos={[0, 0.02, 47.5]} larg={25} cor="#FFD600" peso={800} razao={10} esc={entra} />
      <pointLight position={[0, 14, 24]} intensity={900} color="#FFD600" distance={60} />
      <group position={[0, 8 + Math.sin(t * 2.2) * 0.3, 21]} rotation={[-elev, Math.sin(t * 1.4) * 0.25, 0]} scale={[esc, esc, esc]}>
        <mesh geometry={q.gancho} material={mat} />
        <mesh geometry={q.ponto} material={mat} position={[0, -2.4, 0]} />
      </group>
    </Canvas>
  );
};

export const CENAS_D: Record<string, React.FC> = {
  patios_2018: Patios2018,
  patios_2025: Patios2025,
  patios_pergunta: PatiosPergunta,
};
