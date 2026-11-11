// Cenas 3D do grupo C do Short S001 (17/10/2026): "orbita" (Sistema Solar em 3D) e "mergulho" (do espaço até a estrada).
// Peças compartilhadas (Terra, Estrelas, Camera) vêm de ./Cenas3D (somente leitura aqui).
import React, {useMemo} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {Terra, Estrelas, Camera} from './Cenas3D';

const W = 1080, H = 1920;
const rad = (g: number) => (g * Math.PI) / 180;
const cl = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const suave = (a: number, b: number, x: number) => { const t = cl((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

// ---------- texturas pintadas por código ----------
const canvasTex = (w: number, h: number, pinta: (c: CanvasRenderingContext2D) => void, repete = false) => {
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  pinta(cv.getContext('2d')!);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace;
  if (repete) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  t.anisotropy = 8;
  return t;
};
const useHalo = () => useMemo(() => canvasTex(256, 256, (c) => {
  const g = c.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.25, 'rgba(255,255,255,0.55)'); g.addColorStop(0.6, 'rgba(255,255,255,0.12)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  c.fillStyle = g; c.fillRect(0, 0, 256, 256);
}), []);
const Halo: React.FC<{pos: [number, number, number]; tam: number; cor: string; op?: number}> = ({pos, tam, cor, op = 1}) => {
  const h = useHalo();
  return <sprite position={pos} scale={[tam, tam, 1]} renderOrder={5}><spriteMaterial map={h} color={cor} transparent opacity={op} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} /></sprite>;
};

// Rótulo desenhado na cena (sprite que sempre olha para a câmera).
const Etiqueta: React.FC<{pos: [number, number, number]; texto: string; cor?: string; alt: number; op?: number}> = ({pos, texto, cor = '#ffffff', alt, op = 1}) => {
  const {tex, asp} = useMemo(() => {
    const px = 120;
    const m = document.createElement('canvas').getContext('2d')!; m.font = `800 ${px}px "Helvetica Neue", Arial, sans-serif`;
    const w = Math.ceil(m.measureText(texto).width) + 60, h = Math.ceil(px * 1.45);
    const t = canvasTex(w, h, (c) => {
      c.font = `800 ${px}px "Helvetica Neue", Arial, sans-serif`; c.textAlign = 'center'; c.textBaseline = 'middle';
      c.lineJoin = 'round'; c.lineWidth = 18; c.strokeStyle = 'rgba(2,6,18,0.92)'; c.strokeText(texto, w / 2, h / 2 + 4);
      c.fillStyle = cor; c.fillText(texto, w / 2, h / 2 + 4);
    });
    return {tex: t, asp: w / h};
  }, [texto, cor]);
  return <sprite position={pos} scale={[alt * asp, alt, 1]} renderOrder={20}><spriteMaterial map={tex} transparent opacity={op} depthTest={false} depthWrite={false} toneMapped={false} /></sprite>;
};

// ============================================================
// CENA 8 · ÓRBITA (Sistema Solar)
// ============================================================
const UA = 10;                         // 1 au = 10 unidades; raio da Terra = 1 au
const RM = 1.524 * UA;                 // órbita de Marte
const PERI = 0.986, AFE = 1.664;       // JPL
const SA = (PERI + AFE) / 2, EX = (AFE - PERI) / (AFE + PERI);
const NU_FORA = Math.acos((SA * (1 - EX * EX) / 1.524 - 1) / EX);   // anomalia verdadeira em que a órbita do carro cruza Marte (~137°)

const kepler = (M: number) => { let E = M; for (let i = 0; i < 10; i++) E -= (E - EX * Math.sin(E) - M) / (1 - EX * Math.cos(E)); return E; };
const nuDe = (M: number) => { const E = kepler(M); return 2 * Math.atan2(Math.sqrt(1 + EX) * Math.sin(E / 2), Math.sqrt(1 - EX) * Math.cos(E / 2)); };
const posNu = (nu: number): [number, number, number] => { const r = SA * (1 - EX * EX) / (1 + EX * Math.cos(nu)) * UA; return [r * Math.cos(nu), 0, -r * Math.sin(nu)]; };
const posCarro = (voltas: number) => posNu(nuDe(2 * Math.PI * voltas));
const posCirc = (r: number, ang: number): [number, number, number] => [r * Math.cos(ang), 0, -r * Math.sin(ang)];

const tubo = (pts: THREE.Vector3[], r: number, fechada: boolean, seg = 400) => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, fechada, 'centripetal'), seg, r, 8, fechada);
const arcoPts = (n: number, f: (i: number) => [number, number, number]) => Array.from({length: n}, (_, i) => new THREE.Vector3(...f(i)));

const MarteTex = () => useMemo(() => canvasTex(256, 128, (c) => {
  c.fillStyle = '#c4572a'; c.fillRect(0, 0, 256, 128);
  let s = 3; const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 40; i++) { c.fillStyle = `rgba(${rnd() > 0.5 ? '90,35,20' : '240,150,90'},${0.12 + rnd() * 0.2})`; c.beginPath(); c.ellipse(rnd() * 256, rnd() * 128, 8 + rnd() * 30, 4 + rnd() * 12, rnd() * 3, 0, 7); c.fill(); }
  c.fillStyle = 'rgba(255,255,255,0.7)'; c.fillRect(0, 0, 256, 7); c.fillRect(0, 121, 256, 7);
}), []);

const CarroMini: React.FC<{dir: number}> = ({dir}) => {
  const m = useMemo(() => ({
    t: new THREE.MeshStandardMaterial({color: '#e21212', emissive: '#e21212', emissiveIntensity: 0.9, roughness: 0.4}),
    c: new THREE.MeshStandardMaterial({color: '#1a1d26', roughness: 0.3, metalness: 0.5}),
    r: new THREE.MeshStandardMaterial({color: '#050506'}),
  }), []);
  return (
    <group rotation={[0, dir, 0]}>
      <mesh material={m.t} position={[0, 0.28, 0]}><boxGeometry args={[2.6, 0.5, 1.2]} /></mesh>
      <mesh material={m.t} position={[0.95, 0.5, 0]} rotation={[0, 0, -0.2]}><boxGeometry args={[0.9, 0.2, 1.1]} /></mesh>
      <mesh material={m.c} position={[-0.25, 0.62, 0]}><boxGeometry args={[0.9, 0.34, 0.95]} /></mesh>
      {[[0.85, 0.65], [0.85, -0.65], [-0.85, 0.65], [-0.85, -0.65]].map(([x, z], i) => (
        <mesh key={i} material={m.r} position={[x, 0.2, z]} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[0.28, 0.28, 0.2, 14]} /></mesh>
      ))}
    </group>
  );
};

const DURACAO_8 = 10.3;
const CenaOrbita: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const u = f / fps;

  // geometrias fixas
  const g = useMemo(() => {
    const car = tubo(arcoPts(361, (i) => posNu((i / 360) * Math.PI * 2)), 0.17, true, 500);
    const terra = tubo(arcoPts(241, (i) => posCirc(UA, (i / 240) * Math.PI * 2)), 0.13, true, 300);
    const marteCheio = tubo(arcoPts(361, (i) => posCirc(RM, (i / 360) * Math.PI * 2)), 0.34, true, 500);
    const dashes: THREE.BufferGeometry[] = [];
    const N = 84;
    for (let k = 0; k < N; k++) {
      const a0 = (k / N) * Math.PI * 2, a1 = a0 + (Math.PI * 2 / N) * 0.58;
      dashes.push(tubo(arcoPts(6, (i) => posCirc(RM, lerp(a0, a1, i / 5))), 0.15, false, 6));
    }
    const fora = tubo(arcoPts(81, (i) => posNu(lerp(NU_FORA, 2 * Math.PI - NU_FORA, i / 80))), 0.36, false, 120);
    return {car, terra, marteCheio, dashes, fora};
  }, []);
  const marteTex = MarteTex();

  // movimento: o carro dá a volta devagar, depois o contador acelera 1 → 5
  const T_CONT = 32.8 - 24.9, DUR_CONT = 35.2 - 32.8;
  const x = cl((u - T_CONT) / DUR_CONT);
  const voltas = u < T_CONT ? 0.04 + (u / T_CONT) * 0.96 : 1 + 0.12 * (u - T_CONT) + (4.3 - 0.12 * DUR_CONT) * (x * x * (3 - 2 * x));
  const nVoltas = cl(Math.floor(voltas + 0.0001), 1, 5);
  const angTerra = rad(200) + 2 * Math.PI * 1.525 * voltas;
  const angMarte = rad(60) + 2 * Math.PI * 0.811 * voltas;
  const pCarro = posCarro(voltas), pDepois = posCarro(voltas + 0.003);
  const dirCarro = Math.atan2(-(pDepois[2] - pCarro[2]), pDepois[0] - pCarro[0]);
  const pTerra = posCirc(UA, angTerra), pMarte = posCirc(RM, angMarte);

  // fase "Marte acende": 28,3 → 32,8
  const env = suave(3.4, 3.9, u) * (1 - suave(7.6, 7.95, u));
  const pulso = 0.55 + 0.45 * Math.sin(u * 7.5);

  // câmera: órbita lenta + aproximação leve; segue um pouco o afélio na fase de Marte
  const az = rad(-8 + 36 * (u / DURACAO_8));
  const el = rad(lerp(57, 49, u / DURACAO_8));
  const d = lerp(126, 106, suave(0, DURACAO_8, u));
  const alvo: [number, number, number] = [lerp(-0.8, -1.8, env), 0, 7];
  const cam: [number, number, number] = [alvo[0] + d * Math.cos(el) * Math.sin(az), alvo[1] + d * Math.sin(el), alvo[2] + d * Math.cos(el) * Math.cos(az)];
  const FOV = 36;

  // contador na frente da câmera
  const cTex = useMemo(() => [1, 2, 3, 4, 5].map((n) => canvasTex(512, 640, (c) => {
    c.textAlign = 'center'; c.textBaseline = 'middle'; c.lineJoin = 'round';
    c.font = '900 440px "Helvetica Neue", Arial, sans-serif'; c.lineWidth = 34; c.strokeStyle = 'rgba(2,6,18,0.9)'; c.strokeText(String(n), 256, 270);
    c.fillStyle = '#ffffff'; c.fillText(String(n), 256, 270);
    c.font = '800 110px "Helvetica Neue", Arial, sans-serif'; c.lineWidth = 20; c.strokeText('LAPS', 256, 560);
    c.fillStyle = '#58c8ff'; c.fillText('LAPS', 256, 560);
  })), []);
  const vF = new THREE.Vector3(...alvo).sub(new THREE.Vector3(...cam)).normalize();
  const vR = new THREE.Vector3().crossVectors(vF, new THREE.Vector3(0, 1, 0)).normalize();
  const vU = new THREE.Vector3().crossVectors(vR, vF).normalize();
  const DC = 30, meiaH = DC * Math.tan(rad(FOV / 2));
  const pC = new THREE.Vector3(...cam).addScaledVector(vF, DC).addScaledVector(vU, meiaH * 0.62);
  const frac = voltas - Math.floor(voltas + 0.0001);
  const pop = 1 + 0.22 * Math.exp(-frac * 14) * (u > T_CONT + 0.05 ? 1 : 0);
  const opC = suave(T_CONT - 0.05, T_CONT + 0.25, u);
  const hC = meiaH * 2 * 0.2 * pop;

  // seta que aponta o trecho de fora de Marte
  const opSeta = suave(4.0, 4.5, u) * (1 - suave(7.6, 7.95, u));
  const bob = Math.sin(u * 6) * 0.5;
  const pAfelio = posNu(Math.PI);

  return (
    <ThreeCanvas width={W} height={H} style={{background: '#02030a'}}>
      <Camera pos={cam} alvo={alvo} fov={FOV} />
      <color attach="background" args={['#02030a']} />
      <ambientLight intensity={0.5} color="#9fb8ff" />
      <pointLight position={[0, 0, 0]} intensity={9000} decay={2} color="#fff0d0" />
      <Estrelas />

      {/* Sol */}
      <mesh><sphereGeometry args={[2.3, 48, 32]} /><meshBasicMaterial color="#ffd98a" toneMapped={false} /></mesh>
      <Halo pos={[0, 0, 0]} tam={13 + Math.sin(u * 3) * 0.5} cor="#ffb347" op={0.9} />
      <Halo pos={[0, 0, 0]} tam={34} cor="#ff9a3c" op={0.35} />

      {/* órbitas */}
      <mesh geometry={g.terra}><meshBasicMaterial color="#3d9bff" toneMapped={false} /></mesh>
      <mesh geometry={g.car}><meshBasicMaterial color="#e21212" toneMapped={false} /></mesh>
      {g.dashes.map((geo, i) => <mesh key={i} geometry={geo}><meshBasicMaterial color="#ff8a2a" toneMapped={false} /></mesh>)}
      {/* Marte "acende": brilho no círculo todo e trecho vermelho forte por fora */}
      <mesh geometry={g.marteCheio}><meshBasicMaterial color="#ff8a2a" transparent opacity={env * (0.25 + 0.45 * pulso)} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} /></mesh>
      <mesh geometry={g.fora}><meshBasicMaterial color={pulso > 0.7 ? '#ff6a4a' : '#ff2a1a'} transparent opacity={env} toneMapped={false} /></mesh>

      {/* Terra */}
      <Terra r={1.15} pos={pTerra} giro={u * 2.2} />
      <Etiqueta pos={[pTerra[0], 2.7, pTerra[2]]} texto="EARTH" cor="#8fd0ff" alt={1.9} />
      {/* Marte */}
      <mesh position={pMarte}><sphereGeometry args={[0.85, 32, 24]} /><meshStandardMaterial map={marteTex} roughness={0.9} emissive="#ff7a3a" emissiveMap={marteTex} emissiveIntensity={0.55} /></mesh>
      <Etiqueta pos={[pMarte[0], pMarte[1] + 2.5, pMarte[2]]} texto="MARS" cor="#ffa45c" alt={1.9} />
      <Etiqueta pos={[0, 4.6, 0]} texto="SUN" cor="#ffe2a0" alt={1.9} />
      {/* Roadster */}
      <group position={pCarro} scale={0.62}><CarroMini dir={dirCarro} /></group>
      <Halo pos={[pCarro[0], pCarro[1] + 0.3, pCarro[2]]} tam={4.2 + Math.sin(u * 8) * 0.5} cor="#ff2a2a" op={0.9} />
      <Etiqueta pos={[pCarro[0], pCarro[1] + 3.0, pCarro[2]]} texto="ROADSTER" cor="#ff5a4a" alt={1.9} />

      {/* seta (aponta para o afélio, fora de Marte) */}
      {opSeta > 0.01 && (
        <group position={[pAfelio[0], 0, pAfelio[2]]} scale={[opSeta, opSeta, opSeta]}>
          <mesh position={[0, 5.4 + bob, 0]}><cylinderGeometry args={[0.28, 0.28, 5, 12]} /><meshBasicMaterial color="#ff5a4a" toneMapped={false} /></mesh>
          <mesh position={[0, 1.3 + bob, 0]} rotation={[Math.PI, 0, 0]}><coneGeometry args={[0.95, 2.2, 20]} /><meshBasicMaterial color="#ff5a4a" toneMapped={false} /></mesh>
          <Etiqueta pos={[3.5, 9.6 + bob, 0]} texto="PAST MARS" cor="#ffd0c0" alt={1.9} />
        </group>
      )}

      {/* contador de voltas, dentro da cena */}
      {opC > 0.01 && (
        <sprite position={pC} scale={[hC * (512 / 640), hC, 1]} renderOrder={30}>
          <spriteMaterial map={cTex[nVoltas - 1]} transparent opacity={opC} depthTest={false} depthWrite={false} toneMapped={false} />
        </sprite>
      )}
    </ThreeCanvas>
  );
};

// ============================================================
// CENA 9 · MERGULHO (do espaço até a estrada)
// ============================================================
const R_TERRA = 300;
const CamC: React.FC<{pos: [number, number, number]; alvo: [number, number, number]; fov: number; near: number}> = ({pos, alvo, fov, near}) => {
  const {camera} = useThree(); const c = camera as THREE.PerspectiveCamera;
  c.fov = fov; c.near = near; c.far = 4000; c.position.set(...pos); c.up.set(0, 1, 0); c.lookAt(...alvo); c.updateProjectionMatrix();
  return null;
};

const FAIXAS: {x: number; dir: 1 | -1}[] = [{x: -5.5, dir: 1}, {x: -3.3, dir: 1}, {x: -1.1, dir: 1}, {x: 1.1, dir: -1}, {x: 3.3, dir: -1}, {x: 5.5, dir: -1}];
const CORES_CARROS = ['#e9edf2', '#e21212', '#2f6fe0', '#9aa3ad', '#1b1f2a', '#f0f0f0', '#3aa0d8', '#b8c0c8', '#c9ccd2', '#d83a3a', '#244a9c', '#f2f4f7'];
const rnd0 = (n: number) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };

const caixaArredondada = (larg: number, comp: number, alt: number, raio: number) => {
  const s = new THREE.Shape(); const w = larg / 2, h = comp / 2, r = raio;
  s.moveTo(-w + r, -h); s.lineTo(w - r, -h); s.quadraticCurveTo(w, -h, w, -h + r); s.lineTo(w, h - r); s.quadraticCurveTo(w, h, w - r, h);
  s.lineTo(-w + r, h); s.quadraticCurveTo(-w, h, -w, h - r); s.lineTo(-w, -h + r); s.quadraticCurveTo(-w, -h, -w + r, -h);
  const e = new THREE.ExtrudeGeometry(s, {depth: alt, bevelEnabled: true, bevelThickness: 0.1, bevelSize: 0.1, bevelSegments: 3, curveSegments: 8});
  e.rotateX(-Math.PI / 2); e.translate(0, 0, 0);   // comprimento vira eixo z
  return e;
};

const CenaMergulho: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const N = 81;
  const p = cl(f / (N - 1));
  const t = f / fps;

  const q = 0.62 * (p * p * (3 - 2 * p)) + 0.38 * p;
  const alt = Math.exp(lerp(Math.log(900), Math.log(0.7), q));
  const pitch = -1.45 * Math.pow(1 - q, 1.6) + 0.045;
  const zc = lerp(70, 14, q);
  const pos: [number, number, number] = [lerp(0, -0.35, q), alt, zc];
  const alvo: [number, number, number] = [pos[0], pos[1] + Math.sin(pitch) * 50, pos[2] - Math.cos(pitch) * 50];
  const near = Math.max(0.05, alt * 0.02);

  // transição: espaço → atmosfera → noite na cidade
  const fAtm = cl((260 - alt) / 180);
  const fogNear = Math.exp(lerp(Math.log(1e5), Math.log(14), fAtm)), fogFar = Math.exp(lerp(Math.log(2e5), Math.log(300), fAtm));
  const corCeu = new THREE.Color('#000000').lerp(new THREE.Color('#0a1a3a'), fAtm);
  const opChao = suave(170, 60, alt) > 0 ? 1 - suave(60, 170, alt) : 1;
  const opNuvem = (1 - suave(100, 260, alt)) * 0.9;

  const mat = useMemo(() => {
    const estrada = canvasTex(256, 512, (c) => {
      c.fillStyle = '#15171d'; c.fillRect(0, 0, 256, 512);
      for (let i = 0; i < 1400; i++) { c.fillStyle = `rgba(${90 + (i % 5) * 18},${90 + (i % 5) * 18},${100 + (i % 5) * 18},0.05)`; c.fillRect((i * 97) % 256, (i * 53) % 512, 2, 2); }
      const px = (x: number) => (x + 6.6) / 13.2 * 256;
      c.fillStyle = '#e8e8ea';
      c.fillRect(px(-0.12) - 2, 0, 3, 512); c.fillRect(px(0.12) - 1, 0, 3, 512);
      for (const x of [-4.4, -2.2, 2.2, 4.4]) for (let k = 0; k < 4; k++) c.fillRect(px(x) - 1.5, k * 128 + 8, 3, 56);
      c.fillRect(px(-6.45) - 1.5, 0, 3, 512); c.fillRect(px(6.45) - 1.5, 0, 3, 512);
    }, true);
    estrada.repeat.set(1, 80);
    const chao = canvasTex(512, 512, (c) => {
      c.fillStyle = '#080d1a'; c.fillRect(0, 0, 512, 512);
      c.strokeStyle = 'rgba(70,110,190,0.10)'; c.lineWidth = 2;
      for (let i = 0; i <= 512; i += 64) { c.beginPath(); c.moveTo(i, 0); c.lineTo(i, 512); c.stroke(); c.beginPath(); c.moveTo(0, i); c.lineTo(512, i); c.stroke(); }
      for (let i = 0; i < 700; i++) { const a = rnd0(i), b = rnd0(i + 1000); c.fillStyle = `rgba(255,${190 + (i % 3) * 20},${110 + (i % 4) * 30},${0.35 + rnd0(i + 5) * 0.5})`; c.fillRect(a * 512, b * 512, 3, 3); }
    }, true);
    chao.repeat.set(24, 24);
    const janelas = canvasTex(64, 128, (c) => {
      c.fillStyle = '#0c1226'; c.fillRect(0, 0, 64, 128);
      for (let y = 4; y < 124; y += 8) for (let x = 4; x < 60; x += 8) if (rnd0(x * 7 + y * 13) > 0.45) { c.fillStyle = rnd0(x + y) > 0.5 ? '#ffd88a' : '#9fd6ff'; c.fillRect(x, y, 4, 5); }
    }, true);
    const nuvem = canvasTex(512, 512, (c) => {
      c.clearRect(0, 0, 512, 512);
      for (let i = 0; i < 160; i++) { const x = rnd0(i) * 512, y = rnd0(i + 300) * 512, r = 30 + rnd0(i + 600) * 70; const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, 'rgba(210,225,255,0.5)'); g.addColorStop(1, 'rgba(210,225,255,0)'); c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, 7); c.fill(); }
    }, true);
    nuvem.repeat.set(3, 3);
    const ceu = canvasTex(8, 512, (c) => {
      const g = c.createLinearGradient(0, 0, 0, 512);
      g.addColorStop(0, '#02040f'); g.addColorStop(0.3, '#071233'); g.addColorStop(0.46, '#12295e'); g.addColorStop(0.5, '#244c96'); g.addColorStop(0.56, '#101c40'); g.addColorStop(1, '#05080f');
      c.fillStyle = g; c.fillRect(0, 0, 8, 512);
    });
    return {estrada, chao, janelas, nuvem, ceu};
  }, []);

  const geo = useMemo(() => ({
    corpo: caixaArredondada(1.9, 4.3, 0.62, 0.55).translate(0, 0.28, 0),
    cabine: caixaArredondada(1.62, 2.2, 0.5, 0.5).translate(0, 0.88, -0.25),
    farol: new THREE.BoxGeometry(0.42, 0.16, 0.08),
    pred: new THREE.BoxGeometry(1, 1, 1),
  }), []);
  const matC = useMemo(() => ({
    vidro: new THREE.MeshStandardMaterial({color: '#0b1220', roughness: 0.15, metalness: 0.6}),
    farol: new THREE.MeshBasicMaterial({color: '#fff6dc', toneMapped: false}),
    lant: new THREE.MeshBasicMaterial({color: '#ff1d1d', toneMapped: false}),
    poste: new THREE.MeshStandardMaterial({color: '#2a2f3c'}),
  }), []);
  const tintas = useMemo(() => CORES_CARROS.map((c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.35, metalness: 0.45})), []);

  const carros = useMemo(() => Array.from({length: 30}, (_, i) => {
    const fx = FAIXAS[i % 6]; const jit = rnd0(i + 40);
    return {x: fx.x, dir: fx.dir, z0: -230 + rnd0(i) * 250, v: 14 + jit * 12, cor: i % CORES_CARROS.length};
  }), []);
  const postes = useMemo(() => Array.from({length: 26}, (_, i) => ({z: -240 + i * 11, lado: i % 2 ? 1 : -1})), []);
  const predios = useMemo(() => Array.from({length: 46}, (_, i) => {
    const lado = i % 2 ? 1 : -1;
    return {x: lado * (16 + rnd0(i) * 38), z: -250 + rnd0(i + 90) * 290, w: 6 + rnd0(i + 7) * 12, h: 12 + rnd0(i + 21) * 46, d: 7 + rnd0(i + 33) * 12};
  }), []);

  const perto = alt < 320;
  return (
    <ThreeCanvas width={W} height={H} style={{background: '#000'}}>
      <CamC pos={pos} alvo={alvo} fov={40} near={near} />
      <color attach="background" args={[corCeu]} />
      <fog attach="fog" args={[new THREE.Color('#0b1a36'), fogNear, fogFar]} />
      <ambientLight intensity={0.5 + 0.6 * fAtm} color="#9fb8ff" />
      <directionalLight position={[-60, 90, 40]} intensity={1.6} color="#cfe0ff" />
      <hemisphereLight args={['#3b5fa8', '#10131f', 0.5 * fAtm]} />

      {fAtm < 0.7 && <Estrelas />}
      {alt > 40 && <Terra r={R_TERRA} pos={[0, -R_TERRA, 0]} giro={2.45} />}
      {fAtm > 0.03 && (
        <mesh><sphereGeometry args={[1500, 32, 24]} /><meshBasicMaterial map={mat.ceu} side={THREE.BackSide} transparent opacity={cl(fAtm * 1.4)} fog={false} depthWrite={false} toneMapped={false} /></mesh>
      )}

      {/* nuvens: camadas que a câmera atravessa */}
      {opNuvem > 0.02 && [95, 58, 34, 20].map((y, i) => (
        <mesh key={y} position={[(i - 1.5) * 9, y, -80]} rotation={[-Math.PI / 2, 0, i * 1.1]}>
          <planeGeometry args={[900, 900]} /><meshBasicMaterial map={mat.nuvem} transparent opacity={opNuvem * 0.38} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}

      {perto && (
        <group>
          {/* chão da cidade e estrada */}
          <mesh position={[0, 0.02, -100]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[700, 700]} /><meshBasicMaterial map={mat.chao} transparent opacity={opChao} toneMapped={false} /></mesh>
          <mesh position={[0, 0.05, -120]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[13.2, 600]} /><meshStandardMaterial map={mat.estrada} roughness={0.45} metalness={0.25} transparent opacity={opChao} /></mesh>
          {predios.map((b, i) => (
            <mesh key={i} position={[b.x, b.h / 2, b.z]}>
              <boxGeometry args={[b.w, b.h, b.d]} /><meshStandardMaterial color="#0d1428" emissive="#ffffff" emissiveMap={mat.janelas} emissiveIntensity={0.9} roughness={0.8} />
            </mesh>
          ))}
          {postes.map((s, i) => (
            <group key={i} position={[s.lado * 8.2, 0, s.z]}>
              <mesh material={matC.poste} position={[0, 3.6, 0]}><cylinderGeometry args={[0.07, 0.1, 7.2, 8]} /></mesh>
              <mesh material={matC.farol} position={[-s.lado * 0.5, 7.2, 0]}><boxGeometry args={[1.1, 0.12, 0.35]} /></mesh>
              <Halo pos={[-s.lado * 0.5, 7.1, 0]} tam={4.5} cor="#ffcf8a" op={0.5 * opChao} />
            </group>
          ))}
          {/* carrinhos */}
          {carros.map((c, i) => {
            const z = -230 + ((((c.z0 + 230) + c.dir * c.v * (t + 0.6)) % 270) + 270) % 270;
            return (
              <group key={i} position={[c.x, 0.05, z]} rotation={[0, c.dir === 1 ? 0 : Math.PI, 0]} visible={opChao > 0.01}>
                <mesh geometry={geo.corpo} material={tintas[c.cor]} />
                <mesh geometry={geo.cabine} material={matC.vidro} />
                <mesh geometry={geo.farol} material={matC.farol} position={[0.6, 0.5, 2.2]} />
                <mesh geometry={geo.farol} material={matC.farol} position={[-0.6, 0.5, 2.2]} />
                <mesh geometry={geo.farol} material={matC.lant} position={[0.6, 0.55, -2.2]} />
                <mesh geometry={geo.farol} material={matC.lant} position={[-0.6, 0.55, -2.2]} />
                <Halo pos={[0, 0.55, 2.7]} tam={3.2} cor="#fff0c8" op={0.85} />
                <Halo pos={[0, 0.55, -2.7]} tam={2.6} cor="#ff2a2a" op={0.8} />
              </group>
            );
          })}
        </group>
      )}
    </ThreeCanvas>
  );
};

export const CENAS_C: Record<string, React.FC> = {orbita: CenaOrbita, mergulho: CenaMergulho};
