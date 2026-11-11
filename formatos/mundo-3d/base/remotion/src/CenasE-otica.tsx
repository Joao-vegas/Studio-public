// Cenas 3D do grupo E (Cliente2, OL32 "Ótica por dentro", 18/10/2026): uma ótica feita por código numa rua com mais três.
// Tudo modelado aqui (caixas, toros, cápsulas); nenhum logo. Cores vêm do identidade.json do cliente, copiado para a sandbox
// (staticFile('v/identidade.json')); os valores abaixo são só o reserva se o arquivo faltar.
// Peças: otica_gancho, otica_mergulho, otica_rua, otica_cartaz, otica_enche, otica_vizinha, otica_ciclo, otica_xray,
// otica_fichas, otica_rotulos, otica_volta, otica_quatro, otica_orbita, otica_pack, otica_preco, otica_final.
// Peças compartilhadas (Camera) vêm de ./Cenas3D, só leitura.
import React, {useEffect, useMemo, useState} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {Camera} from './Cenas3D';

type V3 = [number, number, number];
const W = 1080, H = 1920;
const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const sm = (x: number) => { const k = clamp(x); return k * k * (3 - 2 * k); };
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const salto = (x: number) => { const c1 = 2.0, c3 = c1 + 1; const k = clamp(x); return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); };
const rad = (g: number) => (g * Math.PI) / 180;

// ---------- paleta (identidade.json do cliente) ----------
const PAL = {fundo: '#0b1512', texto: '#ffffff', destaque: '#00ffff', oferta: '#ffc000', dor: '#ff2a1f', preco: '#27e36a'};
let palCarregada = false;
const fontePronta = () => typeof document !== 'undefined' &&
  Array.from(document.fonts).some((f) => f.family.replace(/["']/g, '') === 'Anton' && f.status === 'loaded');

// Espera a fonte Anton e a paleta; devolve true quando pode pintar texto.
const usePronto = () => {
  const [ok, setOk] = useState(false);
  const [h] = useState(() => delayRender('otica-pronto'));
  useEffect(() => {
    let vivo = true, n = 0;
    const id = palCarregada ? Promise.resolve(null) : fetch(staticFile('v/identidade.json')).then((r) => r.json()).catch(() => null);
    const tick = async () => {
      if (!vivo) return;
      if (fontePronta() || n++ > 100) {
        const j = await id;
        if (j && j.papeis) { Object.assign(PAL, {fundo: j.papeis.fundo_card, texto: j.papeis.texto, destaque: j.papeis.destaque, oferta: j.papeis.oferta, dor: j.papeis.dor, preco: j.papeis.preco}); palCarregada = true; }
        setOk(true); setTimeout(() => continueRender(h), 80);
      } else setTimeout(tick, 50);
    };
    tick();
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return ok;
};

const useT = () => { const f = useCurrentFrame(); const {fps} = useVideoConfig(); return f / fps; };

// ---------- texto: placa pintada em canvas, sempre voltada para a câmera ----------
type Linha = {txt: string; cor?: string; px: number; peso?: string};
const virado = (pos: V3, cam: V3) => {
  const m = new THREE.Matrix4().lookAt(new THREE.Vector3(...cam), new THREE.Vector3(...pos), new THREE.Vector3(0, 1, 0));
  return new THREE.Quaternion().setFromRotationMatrix(m);
};
const Placa: React.FC<{pos: V3; cam: V3; linhas: Linha[]; larg: number; fundo?: string | null; borda?: string | null; op?: number; esc?: number; frente?: boolean; cw?: number; inclina?: number}> =
  ({pos, cam, linhas, larg, fundo = null, borda = null, op = 1, esc = 1, frente = true, cw = 1024, inclina = 0}) => {
    const pad = fundo || borda ? 46 : 10;
    const ch = Math.round(linhas.reduce((s, l) => s + l.px * 1.08, 0) + pad * 2);
    const {cv, tex} = useMemo(() => {
      const c = document.createElement('canvas'); c.width = cw; c.height = ch;
      const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
      return {cv: c, tex: t};
    }, [cw, ch]);
    const g = cv.getContext('2d')!;
    g.clearRect(0, 0, cw, ch);
    if (fundo || borda) {
      g.beginPath(); (g as any).roundRect(6, 6, cw - 12, ch - 12, 28);
      if (fundo) { g.fillStyle = fundo; g.fill(); }
      if (borda) { g.lineWidth = 10; g.strokeStyle = borda; g.stroke(); }
    }
    let y = pad;
    for (const l of linhas) {
      let px = l.px;
      g.font = `${px}px Anton`;
      const maxW = cw - pad * 2 - 10;
      const w0 = g.measureText(l.txt).width;
      if (w0 > maxW) { px = Math.floor(px * maxW / w0); g.font = `${px}px Anton`; }
      g.fillStyle = l.cor || PAL.texto; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.shadowColor = 'rgba(0,0,0,0.55)'; g.shadowBlur = fundo ? 0 : 18;
      g.fillText(l.txt, cw / 2, y + l.px * 0.56);
      y += l.px * 1.08;
    }
    g.shadowBlur = 0;
    tex.needsUpdate = true;
    if (op <= 0.01 || esc <= 0.01) return null;
    const q = virado(pos, cam);
    const roll = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), inclina);
    q.multiply(roll);
    return (
      <mesh position={pos} quaternion={q} scale={[larg * esc, (larg * ch / cw) * esc, 1]} renderOrder={frente ? 20 : 5}>
        <planeGeometry args={[1, 1]} />
        <meshBasicMaterial map={tex} transparent opacity={op} toneMapped={false} depthWrite={false} depthTest={!frente} side={THREE.DoubleSide} />
      </mesh>
    );
  };

// ---------- cenário: chão, calçada, rua, luzes ----------
const Cenario: React.FC<{fog?: [number, number]}> = ({fog = [30, 90]}) => {
  const grade = useMemo(() => {
    const c = document.createElement('canvas'); c.width = 512; c.height = 512;
    const g = c.getContext('2d')!;
    g.fillStyle = '#0d1916'; g.fillRect(0, 0, 512, 512);
    g.strokeStyle = 'rgba(0,255,255,0.10)'; g.lineWidth = 3;
    for (let i = 0; i <= 512; i += 128) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 512); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(512, i); g.stroke(); }
    const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(60, 60); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
    return t;
  }, []);
  return (
    <>
      <color attach="background" args={['#081210']} />
      <fog attach="fog" args={['#081210', fog[0], fog[1]]} />
      <hemisphereLight args={['#bfefff', '#0b1512', 0.9]} />
      <ambientLight intensity={0.25} />
      <directionalLight position={[-14, 22, 16]} intensity={2.4} color="#fff6ea" castShadow
        shadow-mapSize-width={2048} shadow-mapSize-height={2048} shadow-bias={-0.0008}
        shadow-camera-left={-30} shadow-camera-right={30} shadow-camera-top={30} shadow-camera-bottom={-30} shadow-camera-near={1} shadow-camera-far={90} />
      <directionalLight position={[18, 8, -10]} intensity={0.9} color="#6fe8ff" />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[240, 240]} />
        <meshStandardMaterial map={grade} roughness={0.95} />
      </mesh>
      {/* calçada e rua na frente das lojas (as lojas olham para +z) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 3.0]} receiveShadow>
        <planeGeometry args={[120, 2.4]} /><meshStandardMaterial color="#1f2c29" roughness={0.9} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.015, 7.0]} receiveShadow>
        <planeGeometry args={[120, 5.6]} /><meshStandardMaterial color="#0a1110" roughness={0.9} />
      </mesh>
      {Array.from({length: 30}).map((_, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={[-58 + i * 4, 0.03, 7.0]}>
          <planeGeometry args={[1.6, 0.12]} /><meshBasicMaterial color="#3b4a46" />
        </mesh>
      ))}
    </>
  );
};

// ---------- óculos na vitrine ----------
const Oculos: React.FC<{pos: V3; cor: string; esc?: number}> = ({pos, cor, esc = 1}) => {
  const aro = useMemo(() => new THREE.TorusGeometry(0.12, 0.022, 8, 28), []);
  const ponte = useMemo(() => new THREE.BoxGeometry(0.07, 0.02, 0.02), []);
  const mat = useMemo(() => new THREE.MeshStandardMaterial({color: cor, roughness: 0.35, metalness: 0.3}), [cor]);
  return (
    <group position={pos} scale={esc}>
      <mesh geometry={aro} material={mat} position={[-0.155, 0, 0]} />
      <mesh geometry={aro} material={mat} position={[0.155, 0, 0]} />
      <mesh geometry={ponte} material={mat} position={[0, 0.03, 0]} />
    </group>
  );
};
const CORES_OCULOS = ['#111111', '#ffc000', '#00c8ff', '#e8e8e8', '#7a4a2a', '#2a7a5a'];

// ---------- a ótica ----------
// Frente em z = +1.8 (olha para +z). Largura 4, altura 3, fundo 3.6. Porta à direita, vitrine à esquerda.
type LojaP = {x?: number; z?: number; nossa?: boolean; nome?: string; cartaz?: string | null; cartazEsc?: number; cartazCai?: number;
  xray?: number; gaveta?: number; abre?: number; sobe?: number; cam: V3; corToldo?: string; dentro?: number; luz?: number; brilho?: number};
const Loja: React.FC<LojaP> = ({x = 0, z = 0, nossa = false, nome, cartaz = null, cartazEsc = 1, cartazCai = 0, xray = 0, gaveta = 0, abre = 0, sobe = 1, cam, corToldo, dentro = 0, luz = 1, brilho = 0}) => {
  const fachadaCor = nossa ? PAL.fundo : '#26302d';
  const neon = nossa ? PAL.destaque : '#d9e2df';
  const toldoCor = corToldo || (nossa ? PAL.destaque : '#d97a3a');
  const op = 1 - 0.86 * xray;
  const mats = useMemo(() => ({
    casca: new THREE.MeshStandardMaterial({color: fachadaCor, roughness: 0.6, metalness: 0.1, transparent: true}),
    parede: new THREE.MeshStandardMaterial({color: nossa ? '#13201d' : '#3a4542', roughness: 0.8, transparent: true}),
    vidro: new THREE.MeshPhysicalMaterial({color: '#9fe9ff', roughness: 0.05, metalness: 0, transparent: true, opacity: 0.18, depthWrite: false}),
    neon: new THREE.MeshBasicMaterial({color: neon, toneMapped: false, transparent: true}),
    piso: new THREE.MeshStandardMaterial({color: '#d8dcd9', roughness: 0.7}),
    balcao: new THREE.MeshStandardMaterial({color: '#e9ecea', roughness: 0.4}),
    tampo: new THREE.MeshStandardMaterial({color: nossa ? PAL.destaque : '#9aa6a2', roughness: 0.3, emissive: nossa ? PAL.destaque : '#000', emissiveIntensity: nossa ? 0.25 : 0}),
    prateleira: new THREE.MeshStandardMaterial({color: '#c9cfcc', roughness: 0.5}),
    arquivo: new THREE.MeshStandardMaterial({color: '#6b5a3e', roughness: 0.6}),
    gaveta: new THREE.MeshStandardMaterial({color: '#8a7552', roughness: 0.5, emissive: PAL.oferta, emissiveIntensity: 0}),
    linha: new THREE.LineBasicMaterial({color: PAL.destaque, transparent: true, opacity: 0, toneMapped: false}),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [nossa]);
  mats.casca.opacity = op; mats.parede.opacity = op; mats.casca.depthWrite = op > 0.9; mats.parede.depthWrite = op > 0.9;
  mats.neon.opacity = Math.max(0.35, op);
  mats.linha.opacity = 0.85 * xray;
  mats.gaveta.emissiveIntensity = 1.6 * gaveta;
  // toldo listrado e placa com o nome
  const toldoTex = useMemo(() => {
    const c = document.createElement('canvas'); c.width = 256; c.height = 64;
    const g = c.getContext('2d')!;
    for (let i = 0; i < 8; i++) { g.fillStyle = i % 2 ? '#f4f6f5' : toldoCor; g.fillRect(i * 32, 0, 32, 64); }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  }, [toldoCor]);
  const placaTex = useMemo(() => {
    const c = document.createElement('canvas'); c.width = 1024; c.height = 160;
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return {c, t};
  }, []);
  {
    const g = placaTex.c.getContext('2d')!;
    g.fillStyle = nossa ? '#06100e' : '#1b2321'; g.fillRect(0, 0, 1024, 160);
    g.font = '118px Anton'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.shadowColor = neon; g.shadowBlur = nossa ? 30 : 0; g.fillStyle = neon;
    g.fillText(nome || (nossa ? 'SUA ÓTICA' : 'ÓTICA'), 512, 86); g.shadowBlur = 0;
    placaTex.t.needsUpdate = true;
  }
  const cartazTex = useMemo(() => {
    const c = document.createElement('canvas'); c.width = 512; c.height = 640;
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return {c, t};
  }, []);
  if (cartaz) {
    const g = cartazTex.c.getContext('2d')!;
    g.fillStyle = PAL.dor; g.fillRect(0, 0, 512, 640);
    g.fillStyle = '#fff'; g.fillRect(18, 18, 476, 604);
    g.fillStyle = PAL.dor; g.fillRect(34, 34, 444, 572);
    g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = '96px Anton'; g.fillText('PROMOÇÃO', 256, 120);
    g.font = '250px Anton'; g.fillText(cartaz, 256, 360);
    g.font = '70px Anton'; g.fillText('SÓ HOJE', 256, 545);
    cartazTex.t.needsUpdate = true;
  }
  const box = (w: number, h: number, d: number) => new THREE.BoxGeometry(w, h, d);
  const geos = useMemo(() => ({
    teto: box(4.2, 0.25, 3.9), fundo: box(4, 3, 0.15), lado: box(0.15, 3, 3.6), topo: box(4, 0.9, 0.2), soleira: box(2.4, 0.35, 0.2),
    pilarE: box(0.2, 2.1, 0.2), pilarM: box(0.15, 2.1, 0.2), pilarD: box(0.35, 2.1, 0.2), bandeira: box(0.9, 0.1, 0.2),
    vidroV: new THREE.PlaneGeometry(2.4, 1.75), vidroP: new THREE.PlaneGeometry(0.9, 2.0),
    balcao: box(2.2, 0.95, 0.6), tampo: box(2.3, 0.06, 0.7), prat: box(2.2, 0.05, 0.35), pratL: box(0.35, 0.05, 2.6),
    arquivo: box(1.0, 1.5, 0.6), gav: box(0.86, 0.36, 0.56), puxador: box(0.3, 0.05, 0.05), piso: new THREE.PlaneGeometry(3.7, 3.4),
    neonL: box(4.25, 0.05, 0.05), placa: new THREE.PlaneGeometry(3.6, 0.56), toldo: new THREE.PlaneGeometry(4.1, 0.9),
  }), []);
  const arestas = useMemo(() => {
    const out: {g: THREE.BufferGeometry; p: V3}[] = [];
    const add = (g: THREE.BufferGeometry, p: V3) => out.push({g: new THREE.EdgesGeometry(g), p});
    add(geos.teto, [0, 3.1, 0]); add(geos.fundo, [0, 1.5, -1.75]); add(geos.lado, [-1.95, 1.5, 0]); add(geos.lado, [1.95, 1.5, 0]);
    add(geos.topo, [0, 2.55, 1.8]); add(geos.soleira, [-0.8, 0.175, 1.8]);
    return out;
  }, [geos]);
  const sombra = xray < 0.5;
  const Pc: React.FC<{g: THREE.BufferGeometry; m: THREE.Material; p: V3; r?: V3}> = ({g, m, p, r = [0, 0, 0]}) =>
    <mesh geometry={g} material={m} position={p} rotation={r} castShadow={sombra} receiveShadow />;
  const sObe = sm(sobe);
  // gaveta de cima desliza para fora (abre 0..1)
  const yg = [0.42, 0.82, 1.22];
  return (
    <group position={[x, (sObe - 1) * 3.4, z]} scale={[1, Math.max(0.001, sObe), 1]}>
      {/* casca */}
      <Pc g={geos.teto} m={mats.casca} p={[0, 3.1, 0]} />
      <Pc g={geos.fundo} m={mats.parede} p={[0, 1.5, -1.75]} />
      <Pc g={geos.lado} m={mats.parede} p={[-1.95, 1.5, 0]} />
      <Pc g={geos.lado} m={mats.parede} p={[1.95, 1.5, 0]} />
      <Pc g={geos.topo} m={mats.casca} p={[0, 2.55, 1.8]} />
      <Pc g={geos.soleira} m={mats.casca} p={[-0.8, 0.175, 1.8]} />
      <Pc g={geos.pilarE} m={mats.casca} p={[-1.9, 1.05, 1.8]} />
      <Pc g={geos.pilarM} m={mats.casca} p={[0.475, 1.05, 1.8]} />
      <Pc g={geos.pilarD} m={mats.casca} p={[1.825, 1.05, 1.8]} />
      <Pc g={geos.bandeira} m={mats.casca} p={[1.0, 2.05, 1.8]} />
      <mesh geometry={geos.vidroV} material={mats.vidro} position={[-0.8, 1.225, 1.82]} />
      <mesh geometry={geos.vidroP} material={mats.vidro} position={[1.0, 1.0, 1.82]} />
      {/* placa com o nome e neon do teto */}
      <mesh geometry={geos.placa} position={[0, 2.62, 1.92]}>
        <meshBasicMaterial map={placaTex.t} toneMapped={false} transparent opacity={Math.max(0.4, op)} />
      </mesh>
      <mesh geometry={geos.neonL} material={mats.neon} position={[0, 3.24, 1.96]} />
      {nossa && <mesh geometry={geos.neonL} material={mats.neon} position={[0, 2.08, 1.93]} scale={[0.98, 1, 1]} />}
      {/* toldo */}
      <mesh geometry={geos.toldo} position={[0, 2.08, 2.2]} rotation={[-0.95, 0, 0]} castShadow={sombra}>
        <meshStandardMaterial map={toldoTex} roughness={0.7} transparent opacity={Math.max(0.15, op)} side={THREE.DoubleSide} />
      </mesh>
      {/* interior */}
      <mesh geometry={geos.piso} material={mats.piso} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]} receiveShadow />
      <Pc g={geos.balcao} m={mats.balcao} p={[0.3, 0.48, -0.2]} />
      <Pc g={geos.tampo} m={mats.tampo} p={[0.3, 0.98, -0.2]} />
      {[0.75, 1.35].map((yy, i) => <Pc key={i} g={geos.prat} m={mats.prateleira} p={[-0.8, yy, 1.45]} />)}
      {[0.75, 1.35].flatMap((yy, i) => [-1.6, -1.05, -0.5, 0.05].map((xx, k) =>
        <Oculos key={`${i}-${k}`} pos={[xx + 0.04, yy + 0.16, 1.5]} cor={CORES_OCULOS[(i * 4 + k) % CORES_OCULOS.length]} esc={1.05} />))}
      {[1.2, 1.9].map((yy, i) => <Pc key={i} g={geos.pratL} m={mats.prateleira} p={[1.7, yy, -0.2]} />)}
      {[1.2, 1.9].flatMap((yy, i) => [-1.2, -0.5, 0.2, 0.9].map((zz, k) =>
        <group key={`L${i}-${k}`} position={[1.65, yy + 0.15, zz]} rotation={[0, -Math.PI / 2, 0]}><Oculos pos={[0, 0, 0]} cor={CORES_OCULOS[(k + 2 + i) % 6]} esc={0.9} /></group>))}
      {/* o arquivo de fichas (a gaveta que ninguém abre), no fundo à esquerda */}
      <group position={[-1.2, 0, -1.35]}>
        <Pc g={geos.arquivo} m={mats.arquivo} p={[0, 0.75, 0]} />
        {yg.map((yy, i) => (
          <group key={i} position={[0, yy, 0.04 + (i === 2 ? abre * 0.55 : 0)]}>
            <Pc g={geos.gav} m={mats.gaveta} p={[0, 0, 0]} />
            <mesh geometry={geos.puxador} position={[0, 0, 0.3]}><meshBasicMaterial color="#e8e0c8" /></mesh>
          </group>
        ))}
        {gaveta > 0.01 && <pointLight position={[0, 1.4, 0.8]} color={PAL.oferta} intensity={12 * gaveta} distance={4} />}
      </group>
      {luz > 0 && <pointLight position={[0, 2.5, 0.4]} color={nossa ? '#dffcff' : '#fff1dc'} intensity={6 * luz} distance={6} />}
      {brilho > 0 && <pointLight position={[0, 1.6, 3.2]} color={PAL.destaque} intensity={10 * brilho} distance={7} />}
      {/* arestas do raio-X */}
      {xray > 0.01 && arestas.map((a, i) => <lineSegments key={i} geometry={a.g} material={mats.linha} position={a.p} />)}
      {/* cartaz de desconto colado na vitrine */}
      {cartaz && cartazEsc > 0.01 && (
        <mesh position={[-0.8, 1.25 - cartazCai * 1.0, 1.9 + cartazCai * 0.6]} rotation={[-cartazCai * 1.2, 0, rad(-5) + cartazCai * 0.8]}
          scale={[cartazEsc * 1.5, cartazEsc * 1.875, 1]}>
          <planeGeometry args={[1, 1]} />
          <meshBasicMaterial map={cartazTex.t} toneMapped={false} transparent opacity={1 - clamp(cartazCai * 1.2 - 0.2)} side={THREE.DoubleSide} />
        </mesh>
      )}
      {dentro > 0 && <Gente n={Math.round(dentro)} area={[-1.5, 1.3, -0.8, 1.1]} seed={x * 7 + 3} />}
    </group>
  );
};

// ---------- bonecos ----------
const CORES_GENTE = ['#ff8a3d', '#3db5ff', '#f2d43b', '#7bd36b', '#ffffff', '#b07cff', '#ff5a4a', '#41e0c8', '#e7b58a', '#8fa3ff'];
const geoGente = {corpo: new THREE.CapsuleGeometry(0.17, 0.42, 6, 12), cabeca: new THREE.SphereGeometry(0.15, 16, 12), perna: new THREE.CapsuleGeometry(0.065, 0.3, 4, 8)};
const matsGente = new Map<string, THREE.Material>();
const matG = (c: string) => { if (!matsGente.has(c)) matsGente.set(c, new THREE.MeshStandardMaterial({color: c, roughness: 0.55})); return matsGente.get(c)!; };
const matPele = new THREE.MeshStandardMaterial({color: '#f0c9a0', roughness: 0.6});
const matCalca = new THREE.MeshStandardMaterial({color: '#28303a', roughness: 0.7});
const Boneco: React.FC<{p: V3; cor: string; fase: number; dir?: number; esc?: number}> = ({p, cor, fase, dir = 0, esc = 1}) => {
  if (esc <= 0.01) return null;
  const s = Math.sin(fase) * 0.5;
  return (
    <group position={p} rotation={[0, dir, 0]} scale={esc}>
      <mesh geometry={geoGente.perna} material={matCalca} position={[-0.08, 0.24, 0]} rotation={[s, 0, 0]} castShadow />
      <mesh geometry={geoGente.perna} material={matCalca} position={[0.08, 0.24, 0]} rotation={[-s, 0, 0]} castShadow />
      <mesh geometry={geoGente.corpo} material={matG(cor)} position={[0, 0.72, 0]} castShadow />
      <mesh geometry={geoGente.cabeca} material={matPele} position={[0, 1.18, 0]} castShadow />
    </group>
  );
};
const rnd = (s: number) => { const x = Math.sin(s * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
// gente parada (ou mexendo de leve) numa área [x0,x1,z0,z1]
const Gente: React.FC<{n: number; area: [number, number, number, number]; seed?: number; t?: number}> = ({n, area, seed = 1, t = 0}) => (
  <>
    {Array.from({length: n}).map((_, i) => {
      const x = lerp(area[0], area[1], rnd(seed + i * 3.1)), z = lerp(area[2], area[3], rnd(seed + i * 5.7));
      return <Boneco key={i} p={[x, 0, z]} cor={CORES_GENTE[Math.floor(rnd(seed + i) * CORES_GENTE.length)]} fase={t * 3 + i} dir={rnd(seed + i * 9) * 6} />;
    })}
  </>
);
// caminhante: segue os pontos pts no tempo u (0..1); some quando u >= 1 se sumir
const anda = (pts: V3[], u: number): {p: V3; dir: number} => {
  const k = clamp(u) * (pts.length - 1);
  const i = Math.min(pts.length - 2, Math.floor(k)), f = k - i;
  const a = pts[i], b = pts[i + 1];
  return {p: [lerp(a[0], b[0], f), 0, lerp(a[2], b[2], f)], dir: Math.atan2(b[0] - a[0], b[2] - a[2])};
};
// fluxo: n bonecos indo da rua até a porta (x da loja) entre t0 e t1 (cada um com atraso)
const Fluxo: React.FC<{n: number; t: number; t0: number; dur: number; de: (i: number) => V3; ate: V3; meio?: (i: number) => V3; seed?: number; ficar?: boolean}> = ({n, t, t0, dur, de, ate, meio, seed = 5, ficar = false}) => (
  <>
    {Array.from({length: n}).map((_, i) => {
      const atraso = rnd(seed + i * 1.7) * dur * 0.7;
      const u = (t - t0 - atraso) / (dur * 0.55);
      if (u >= 1 && !ficar) return null;
      const pts = meio ? [de(i), meio(i), ate] : [de(i), ate];
      const {p, dir} = anda(pts, u);
      return <Boneco key={i} p={p} cor={CORES_GENTE[(i + seed) % CORES_GENTE.length]} fase={t * 9 + i} dir={dir} esc={u >= 0.96 && !ficar ? 0 : 1} />;
    })}
  </>
);

// ---------- contador de clientes (número dentro da cena) ----------
const Contador: React.FC<{pos: V3; cam: V3; n: number; titulo?: string; cor?: string; larg?: number; op?: number; esc?: number}> = ({pos, cam, n, titulo = 'CLIENTES NA LOJA', cor, larg = 2.6, op = 1, esc = 1}) => (
  <Placa pos={pos} cam={cam} larg={larg} op={op} esc={esc} fundo="rgba(6,16,14,0.88)" borda={cor || PAL.destaque}
    linhas={[{txt: titulo, px: 74, cor: '#cfe9e4'}, {txt: String(Math.round(n)), px: 250, cor: cor || PAL.destaque}, {txt: 'simulação', px: 40, cor: '#7f9a94'}]} />
);

const RUA_X = [-4.8, 0, 4.8, 9.6];   // nossa ótica é a 2ª (x = 0); a vizinha que baixa mais é a 3ª
const Rua: React.FC<{cam: V3; sobe?: number[]; cartazes?: (string | null)[]; brilho?: number; nossa?: Partial<LojaP>}> = ({cam, sobe = [1, 1, 1, 1], cartazes = [null, null, null, null], brilho = 0, nossa = {}}) => (
  <>
    {RUA_X.map((x, i) => i === 1
      ? <Loja key={i} x={x} nossa cam={cam} cartaz={cartazes[i]} sobe={sobe[i]} brilho={brilho} {...nossa} />
      : <Loja key={i} x={x} cam={cam} cartaz={cartazes[i]} sobe={sobe[i]} corToldo={['#d97a3a', '', '#8c9a96', '#c9a23a'][i]} />)}
  </>
);

// ===================== CENAS =====================

// 1. Gancho (0 a 3,6 s): a ótica com o cartaz gigante; o desconto sobe e o contador de clientes despenca; câmera voando em volta.
export const OticaGancho: React.FC = () => {
  usePronto(); const t = useT();
  const az = rad(28 - t * 16), d = 10.5 - t * 0.5;
  const cam: V3 = [Math.sin(az) * d, 3.4 + t * 0.25, Math.cos(az) * d];
  const desc = t < 1.0 ? '-30%' : t < 2.0 ? '-50%' : '-70%';
  const n = Math.round(lerp(48, 3, sm(t / 3.2)));
  const barras = [9, 7.5, 6, 4.4, 2.8, 1.4, 0.6];
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0.3, 2.4, 0]} fov={46} />
      <Cenario />
      <Loja nossa cam={cam} cartaz={desc} cartazEsc={1.0 + 0.06 * Math.sin(t * 6)} brilho={0.4} />
      <Loja x={-4.8} cam={cam} corToldo="#d97a3a" />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" />
      {/* gente saindo da loja e indo embora */}
      <Fluxo n={9} t={t} t0={-1.2} dur={4.2} de={() => [1.0, 0, 2.3]} meio={(i) => [1.0 + (i % 3) * 0.4, 0, 4.2]} ate={[9, 0, 6.5]} seed={11} />
      {/* contador e gráfico caindo, acima da loja */}
      <Contador pos={[-0.2, 5.6, 0.6]} cam={cam} n={n} cor={n < 20 ? PAL.dor : PAL.destaque} larg={2.9} />
      {barras.map((h, i) => {
        const k = sm((t - i * 0.32) / 0.4);
        const hh = Math.max(0.05, (h / 9) * 2.2 * k);
        return (
          <mesh key={i} position={[2.25 + i * 0.32, 3.35 + hh / 2, 0.8]} castShadow>
            <boxGeometry args={[0.24, hh, 0.24]} />
            <meshStandardMaterial color={i < 3 ? PAL.destaque : PAL.dor} emissive={i < 3 ? PAL.destaque : PAL.dor} emissiveIntensity={0.5} />
          </mesh>
        );
      })}
    </ThreeCanvas>
  );
};

// 2. "Parece errado. Mas olha por dentro." (3,6 a 5,9 s): a câmera mergulha na vitrine e a loja vira raio-X.
export const OticaMergulho: React.FC = () => {
  usePronto(); const t = useT();
  const k = sm((t - 0.5) / 1.7);
  const cam: V3 = [lerp(3.0, 0.4, k), lerp(3.2, 1.9, k), lerp(11, 3.0, k)];
  const xr = sm((t - 0.9) / 0.9);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[lerp(0, -0.3, k), lerp(2.0, 1.2, k), lerp(0, -1.0, k)]} fov={lerp(44, 60, k)} rolar={rad(lerp(0, -4, k))} />
      <Cenario />
      <Loja nossa cam={cam} cartaz="-50%" cartazEsc={1 - xr} xray={xr} dentro={xr > 0.3 ? 2 : 0} />
      <Loja x={-4.8} cam={cam} xray={xr * 0.6} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" xray={xr * 0.6} />
    </ThreeCanvas>
  );
};

// 3. "Essa é uma ótica comum, numa rua com mais três." (5,9 a 8,7 s): plano alto da rua, as 3 vizinhas brotam do chão.
export const OticaRua: React.FC = () => {
  usePronto(); const t = useT();
  const cam: V3 = [lerp(-3, 4, sm(t / 2.8)), 9.5 - t * 0.4, 15 - t * 0.3];
  const s = (a: number) => sm((t - a) / 0.45);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[2.2, 1.2, 0]} fov={50} />
      <Cenario />
      <Rua cam={cam} sobe={[s(1.35), 1, s(1.65), s(1.95)]} brilho={0.5} />
      <Gente n={6} area={[-6, 12, 5, 8.5]} seed={4} t={t} />
      <Placa pos={[0, 4.6, 1.2]} cam={cam} larg={2.4} linhas={[{txt: 'SUA ÓTICA', px: 150, cor: PAL.destaque}]} op={sm(t / 0.4)} />
      <Placa pos={[7.2, 5.0, 1.2]} cam={cam} larg={2.4} linhas={[{txt: '+3 NA RUA', px: 150, cor: '#ffffff'}]} op={s(2.0)} />
    </ThreeCanvas>
  );
};

// 4. "Na segunda, ela cola um cartaz de cinquenta por cento." (8,7 a 11,3 s): o cartaz bate na vitrine.
export const OticaCartaz: React.FC = () => {
  usePronto(); const t = useT();
  const az = rad(-18 + t * 9);
  const cam: V3 = [Math.sin(az) * 7.6, 2.9, Math.cos(az) * 7.6];
  const bate = salto((t - 1.4) / 0.4);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[-0.3, 2.3, 0]} fov={48} />
      <Cenario />
      <Loja nossa cam={cam} cartaz="-50%" cartazEsc={bate * 1.25} brilho={0.3} />
      <Loja x={-4.8} cam={cam} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" />
      <Placa pos={[-0.3, 5.2, 1.0]} cam={cam} larg={2.5} fundo="rgba(6,16,14,0.88)" borda="#cfe9e4" linhas={[{txt: 'SEGUNDA-FEIRA', px: 120, cor: '#ffffff'}]} />
    </ThreeCanvas>
  );
};

// 5. "Em dois dias, a loja enche." (11,3 a 13,9 s): gente entrando, contador sobe.
export const OticaEnche: React.FC = () => {
  usePronto(); const t = useT();
  const cam: V3 = [lerp(5.5, 3.5, t / 2.7), 5.2, 11.5 - t * 0.4];
  const n = Math.round(lerp(4, 41, sm((t - 0.2) / 2.2)));
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0, 2.4, 0.8]} fov={48} />
      <Cenario />
      <Loja nossa cam={cam} cartaz="-50%" cartazEsc={1.25} dentro={lerp(2, 12, sm(t / 2.4))} brilho={0.5} />
      <Loja x={-4.8} cam={cam} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" />
      <Fluxo n={22} t={t} t0={-0.6} dur={3.4} de={(i) => [-8 + rnd(i) * 18, 0, 5 + rnd(i + 9) * 4]} ate={[1.0, 0, 1.4]} meio={(i) => [lerp(-1, 2.5, rnd(i * 2)), 0, 3.4]} seed={21} />
      <Contador pos={[0, 5.9, 0.6]} cam={cam} n={n} larg={2.6} />
      <Placa pos={[3.2, 5.5, 0.6]} cam={cam} larg={1.7} fundo="rgba(6,16,14,0.88)" borda="#cfe9e4" linhas={[{txt: t < 1.3 ? 'DIA 1' : 'DIA 2', px: 140}]} />
    </ThreeCanvas>
  );
};

// 6. "No terceiro, a vizinha baixa mais. E o movimento vai junto." (13,9 a 17,7 s)
export const OticaVizinha: React.FC = () => {
  usePronto(); const t = useT();
  const cam: V3 = [lerp(1.0, 4.0, sm(t / 3.8)), 6.8, 13.5 - t * 0.3];
  const viz = salto((t - 1.25) / 0.4);
  const migra = sm((t - 2.3) / 1.4);
  const nossa = Math.round(lerp(41, 6, migra)), dela = Math.round(lerp(8, 44, migra));
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[2.4, 2.4, 0.5]} fov={50} />
      <Cenario />
      <Loja nossa cam={cam} cartaz="-50%" cartazEsc={1.25} dentro={lerp(12, 1, migra)} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" cartaz="-60%" cartazEsc={viz * 1.25} dentro={lerp(1, 12, migra)} luz={1.4} />
      <Loja x={-4.8} cam={cam} />
      <Fluxo n={16} t={t} t0={2.1} dur={1.9} de={(i) => [lerp(0.2, 1.6, rnd(i)), 0, 2.4 + rnd(i + 3) * 1.4]} meio={(i) => [2.4 + rnd(i * 5) * 0.8, 0, 3.6 + rnd(i) * 1.2]} ate={[5.8, 0, 1.4]} seed={31} />
      <Placa pos={[2.4, 7.4, 0.6]} cam={cam} larg={2.0} fundo="rgba(6,16,14,0.88)" borda="#cfe9e4" linhas={[{txt: 'DIA 3', px: 140}]} />
      <Contador pos={[-0.1, 5.3, 0.6]} cam={cam} n={nossa} larg={2.2} titulo="SUA ÓTICA" cor={migra > 0.5 ? PAL.dor : PAL.destaque} />
      <Contador pos={[4.9, 5.3, 0.6]} cam={cam} n={dela} larg={2.2} titulo="A VIZINHA" cor="#ffffff" />
    </ThreeCanvas>
  );
};

// 7. "Cada desconto traz um cliente que só volta com outro desconto." (17,7 a 21,1 s): o cliente anda em roda entre cartazes.
export const OticaCiclo: React.FC = () => {
  usePronto(); const t = useT();
  const az = rad(30 + t * 14);
  const cam: V3 = [2.4 + Math.sin(az) * 9, 6.0, 4 + Math.cos(az) * 9];
  const alvo: V3 = [2.4, 1.6, 4.0];
  const tags = ['-50%', '-60%', '-70%', '-80%'];
  const R = 2.6;
  const ang = t * 1.6;
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={alvo} fov={48} />
      <Cenario />
      <Loja nossa cam={cam} cartaz="-50%" cartazEsc={1.25} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" cartaz="-60%" cartazEsc={1.25} />
      {/* trilha circular no chão */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[2.4, 0.05, 4.0]}>
        <ringGeometry args={[R - 0.06, R + 0.06, 96]} /><meshBasicMaterial color={PAL.dor} transparent opacity={0.8} toneMapped={false} />
      </mesh>
      {tags.map((tg, i) => {
        const a = (i / tags.length) * Math.PI * 2;
        const p: V3 = [2.4 + Math.cos(a) * R, 1.6, 4.0 + Math.sin(a) * R];
        const perto = Math.cos(ang - a);
        return <Placa key={i} pos={p} cam={cam} larg={1.25} fundo={PAL.dor} linhas={[{txt: tg, px: 170, cor: '#ffffff'}]} esc={1 + 0.25 * clamp(perto)} frente={false} />;
      })}
      {[0, 1, 2].map((k) => {
        const a = ang + k * 2.1;
        return <Boneco key={k} p={[2.4 + Math.cos(a) * R, 0, 4.0 + Math.sin(a) * R]} cor={CORES_GENTE[k + 1]} fase={t * 9 + k} dir={-a} />;
      })}
    </ThreeCanvas>
  );
};

// 8. "Só que dentro dessa ótica tem uma gaveta que ninguém abre." (21,1 a 24,2 s): raio-X, a gaveta acende no fundo.
export const OticaXray: React.FC = () => {
  usePronto(); const t = useT();
  const az = rad(35 - t * 12);
  const d = 8.6 - t * 1.1;
  const cam: V3 = [Math.sin(az) * d, 4.2 - t * 0.35, Math.cos(az) * d];
  const acende = sm((t - 1.6) / 0.6);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[-0.8, 1.2, -0.7]} fov={46} />
      <Cenario />
      <Loja nossa cam={cam} xray={1} gaveta={acende * (0.8 + 0.2 * Math.sin(t * 8))} luz={0.4} />
      <Placa pos={[-1.2, 2.5, -1.2]} cam={cam} larg={1.9} op={acende} fundo="rgba(6,16,14,0.9)" borda={PAL.oferta}
        linhas={[{txt: 'NINGUÉM ABRE', px: 120, cor: PAL.oferta}]} />
    </ThreeCanvas>
  );
};

// ficha de cliente (cartão branco com faixa ciano)
const useFichaTex = () => useMemo(() => {
  const c = document.createElement('canvas'); c.width = 256; c.height = 160;
  const g = c.getContext('2d')!;
  g.fillStyle = '#f7f6ef'; g.fillRect(0, 0, 256, 160);
  g.fillStyle = '#00b8c8'; g.fillRect(0, 0, 256, 30);
  g.fillStyle = '#9aa3a0'; for (let i = 0; i < 4; i++) g.fillRect(18, 50 + i * 24, 140 + ((i * 37) % 70), 9);
  g.strokeStyle = '#c9c4b2'; g.lineWidth = 4; g.strokeRect(2, 2, 252, 156);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}, []);

// 9. "As fichas de todo mundo que já comprou ali." (24,2 a 26,5 s): a gaveta abre e as fichas sobem em leque.
export const OticaFichas: React.FC = () => {
  usePronto(); const t = useT();
  const tex = useFichaTex();
  const abre = sm(t / 0.5);
  const cam: V3 = [lerp(1.6, 0.6, t / 2.3), lerp(2.2, 3.0, t / 2.3), lerp(2.6, 3.2, t / 2.3)];
  const base: V3 = [-1.2, 1.25, -0.8];
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[-1.1, 2.1, -1.2]} fov={55} />
      <Cenario />
      <Loja nossa cam={cam} xray={0.85} gaveta={0.9} abre={abre} luz={0.5} />
      {Array.from({length: 46}).map((_, i) => {
        const u = clamp((t - 0.3 - i * 0.035) / 1.4);
        if (u <= 0) return null;
        const a = rnd(i) * Math.PI * 2, r = 0.2 + u * (0.8 + rnd(i + 4) * 1.4);
        const p: V3 = [base[0] + Math.cos(a) * r * 0.9, base[1] + u * (1.2 + rnd(i + 8) * 2.4), base[2] + Math.sin(a) * r * 0.5 + u * 0.6];
        return (
          <mesh key={i} position={p} rotation={[rnd(i + 1) * 0.6 - 0.3 + t, a, rnd(i + 2) * 0.6]} scale={[0.42, 0.26, 1]}>
            <planeGeometry args={[1, 1]} /><meshBasicMaterial map={tex} side={THREE.DoubleSide} toneMapped={false} />
          </mesh>
        );
      })}
    </ThreeCanvas>
  );
};

// 10. "Gente com a receita vencendo. Orçamento que ninguém cobrou. Família que nunca foi chamada." (26,5 a 32,2 s)
export const OticaRotulos: React.FC = () => {
  usePronto(); const t = useT();
  const tex = useFichaTex();
  const cam: V3 = [Math.sin(t * 0.12) * 1.2, 0.2 + t * 0.06, 9 - t * 0.25];
  const itens = [
    {de: 1.05, txt: 'RECEITA VENCENDO', y: 3.3, cor: PAL.destaque},
    {de: 2.2, txt: 'ORÇAMENTO PARADO', y: 1.25, cor: PAL.oferta},
    {de: 3.9, txt: 'FAMÍLIA NUNCA CHAMADA', y: -0.8, cor: '#ffffff'},
  ];
  return (
    <ThreeCanvas width={W} height={H}>
      <color attach="background" args={['#081210']} />
      <fog attach="fog" args={['#081210', 8, 40]} />
      <Camera pos={cam} alvo={[0, 1.1, 0]} fov={50} />
      <ambientLight intensity={1} />
      {/* fichas ao fundo, flutuando */}
      {Array.from({length: 60}).map((_, i) => {
        const p: V3 = [(rnd(i) - 0.5) * 16, (rnd(i + 3) - 0.5) * 14 + 1 + ((t * 0.5 + rnd(i + 6) * 10) % 10) - 5, -4 - rnd(i + 9) * 14];
        return (
          <mesh key={i} position={p} rotation={[rnd(i + 1) + t * 0.4, rnd(i + 2) * 3, 0]} scale={[0.9, 0.56, 1]}>
            <planeGeometry args={[1, 1]} /><meshBasicMaterial map={tex} side={THREE.DoubleSide} transparent opacity={0.55} toneMapped={false} />
          </mesh>
        );
      })}
      {itens.map((it, i) => {
        const k = salto((t - it.de) / 0.45);
        if (k <= 0.01) return null;
        const p: V3 = [lerp(-4, 0, sm((t - it.de) / 0.45)), it.y, 0];
        return (
          <group key={i}>
            <Placa pos={p} cam={cam} larg={4.6} esc={k} frente={false} fundo="#f7f6ef" borda={it.cor === '#ffffff' ? '#9aa3a0' : it.cor}
              linhas={[{txt: 'FICHA DO CLIENTE', px: 56, cor: '#55605c'}, {txt: it.txt, px: 120, cor: '#0b1512'}]} />
          </group>
        );
      })}
    </ThreeCanvas>
  );
};

// 11. "É dali que a loja enche. Sem mexer no preço." (32,2 a 35,2 s): fichas viram gente entrando; o cartaz cai.
export const OticaVolta: React.FC = () => {
  usePronto(); const t = useT();
  const tex = useFichaTex();
  const cam: V3 = [lerp(4.5, 2.5, t / 3), 4.6, 11 - t * 0.5];
  const cai = sm((t - 1.6) / 0.9);
  const n = Math.round(lerp(3, 46, sm((t - 0.3) / 2.6)));
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0, 2.3, 0.8]} fov={50} />
      <Cenario />
      <Loja nossa cam={cam} cartaz="-50%" cartazEsc={1.25} cartazCai={cai} dentro={lerp(1, 13, sm(t / 2.8))} brilho={0.6} gaveta={0.6} />
      <Loja x={-4.8} cam={cam} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" />
      {/* fichas saem pela porta e voam até a rua */}
      {Array.from({length: 18}).map((_, i) => {
        const u = clamp((t - i * 0.08) / 1.1);
        if (u <= 0 || u >= 1) return null;
        const alvo: V3 = [-6 + rnd(i) * 14, 0.4, 5.5 + rnd(i + 2) * 3];
        const p: V3 = [lerp(1.0, alvo[0], u), 1.6 + Math.sin(u * Math.PI) * 2.4, lerp(1.6, alvo[2], u)];
        return (
          <mesh key={i} position={p} rotation={[t * 3 + i, i, 0]} scale={[0.5, 0.32, 1]}>
            <planeGeometry args={[1, 1]} /><meshBasicMaterial map={tex} side={THREE.DoubleSide} toneMapped={false} />
          </mesh>
        );
      })}
      <Fluxo n={24} t={t} t0={0.6} dur={2.6} de={(i) => [-6 + rnd(i) * 14, 0, 5.5 + rnd(i + 2) * 3]} meio={(i) => [lerp(-0.5, 2.5, rnd(i * 3)), 0, 3.4]} ate={[1.0, 0, 1.4]} seed={41} />
      <Contador pos={[0, 5.9, 0.6]} cam={cam} n={n} larg={2.6} />
      <Placa pos={[3.2, 5.3, 0.6]} cam={cam} larg={1.9} op={cai} fundo="rgba(6,16,14,0.9)" borda={PAL.preco} linhas={[{txt: 'PREÇO', px: 70, cor: '#cfe9e4'}, {txt: 'O MESMO', px: 120, cor: PAL.preco}]} />
    </ThreeCanvas>
  );
};

// 12. "O Cliente2 tem quatro óticas e usa cinco campanhas pra chamar essa gente de volta." (35,2 a 39,5 s)
export const OticaQuatro: React.FC = () => {
  usePronto(); const t = useT();
  const cam: V3 = [lerp(-2, 3, sm(t / 4.3)), 13 - t * 0.6, 17 - t * 0.5];
  const s = (a: number) => sm((t - a) / 0.4);
  const xs: [number, number][] = [[-3.0, -3.0], [3.0, -3.0], [-3.0, 3.6], [3.0, 3.6]];
  const cinco = sm((t - 2.0) / 0.5);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0, 1.5, 0.3]} fov={50} />
      <Cenario fog={[40, 110]} />
      {xs.map(([x, z], i) => <Loja key={i} x={x} z={z} nossa nome="ÓTICA" cam={cam} sobe={s(0.15 + i * 0.18)} dentro={6} brilho={0.4} />)}
      <Placa pos={[0, 8.6, 0]} cam={cam} larg={5.2} op={s(0.6)} linhas={[{txt: 'AS 4 ÓTICAS', px: 170, cor: '#ffffff'}, {txt: 'DO CLIENTE2', px: 110, cor: PAL.destaque}]} />
      {Array.from({length: 5}).map((_, i) => {
        const a = t * 0.9 + (i / 5) * Math.PI * 2;
        const p: V3 = [Math.cos(a) * 6.2, 5.0 + Math.sin(a * 2) * 0.2, Math.sin(a) * 6.2 + 0.3];
        return (
          <mesh key={i} position={p} rotation={[t, t * 1.3 + i, 0]} scale={salto((t - 2.0 - i * 0.1) / 0.4) * 0.85}>
            <boxGeometry args={[1, 1, 1]} /><meshStandardMaterial color={PAL.oferta} emissive={PAL.oferta} emissiveIntensity={0.6} />
          </mesh>
        );
      })}
      <Placa pos={[0, 6.4, 0]} cam={cam} larg={4.2} op={cinco} linhas={[{txt: '5 CAMPANHAS', px: 170, cor: PAL.oferta}]} />
    </ThreeCanvas>
  );
};

// 13. "Reativação de clientes. Resgate de orçamento. Indicação premiada. Parceria com empresa. E anúncio nas redes." (39,5 a 45,8 s)
const CAMPANHAS = [
  {de: 0.0, txt: 'REATIVAÇÃO DE CLIENTES'}, {de: 1.28, txt: 'RESGATE DE ORÇAMENTO'}, {de: 2.74, txt: 'INDICAÇÃO PREMIADA'},
  {de: 3.96, txt: 'PARCERIA COM EMPRESA'}, {de: 5.38, txt: 'ANÚNCIO NAS REDES'},
];
export const OticaOrbita: React.FC = () => {
  usePronto(); const t = useT();
  const az = rad(-20 + t * 7);
  const cam: V3 = [Math.sin(az) * 15, 7.5, Math.cos(az) * 15];
  const ativa = CAMPANHAS.reduce((a, c, i) => (t >= c.de - 0.05 ? i : a), 0);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0, 4.6, 0]} fov={50} />
      <Cenario />
      <Loja nossa cam={cam} dentro={lerp(4, 12, t / 6)} brilho={0.6} />
      <Loja x={-4.8} cam={cam} /><Loja x={4.8} cam={cam} corToldo="#8c9a96" />
      {/* anel de órbita */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 3.6, 0]}>
        <ringGeometry args={[4.48, 4.54, 128]} /><meshBasicMaterial color={PAL.destaque} transparent opacity={0.45} toneMapped={false} side={THREE.DoubleSide} />
      </mesh>
      {CAMPANHAS.map((c, i) => {
        const k = salto((t - c.de) / 0.4);
        if (k <= 0.01) return null;
        // cada cartão fica num degrau (não se cobrem) e gira devagar em volta da loja
        const a = rad(-80 + i * 0) + t * 0.0;
        const y = 8.4 - i * 1.05;
        const ang = az + rad(-26 + (i % 2 ? 1 : -1) * 6) + Math.sin(t * 0.9 + i) * 0.05 + a * 0;
        const p: V3 = [Math.sin(ang) * 2.2, y, Math.cos(ang) * 2.2];
        const on = i === ativa;
        return <Placa key={i} pos={p} cam={cam} larg={6.4} esc={k * (on ? 1.0 : 0.86)} fundo={on ? 'rgba(6,16,14,0.95)' : 'rgba(6,16,14,0.75)'} borda={on ? PAL.destaque : '#4f6b65'}
          linhas={[{txt: `${i + 1}. ${c.txt}`, px: 92, cor: on ? PAL.destaque : '#d7e6e2'}]} cw={1400} />;
      })}
    </ThreeCanvas>
  );
};

// pacote 3D do Pack (caixa preto-esverdeada com neon ciano; nome só em texto)
const usePackTex = () => {
  const r = useMemo(() => {
    const c = document.createElement('canvas'); c.width = 600; c.height = 760;
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return {c, t};
  }, []);
  const g = r.c.getContext('2d')!;
  g.fillStyle = PAL.fundo; g.fillRect(0, 0, 600, 760);
  g.strokeStyle = PAL.destaque; g.lineWidth = 12; g.shadowColor = PAL.destaque; g.shadowBlur = 24; g.strokeRect(24, 24, 552, 712); g.shadowBlur = 0;
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillStyle = '#ffffff'; g.font = '150px Anton'; g.fillText('PACK', 300, 170);
  g.shadowColor = PAL.destaque; g.shadowBlur = 20; g.fillStyle = PAL.destaque; g.font = '118px Anton'; g.fillText('MARCA', 300, 330); g.fillText('EXEMPLO', 300, 460); g.shadowBlur = 0;
  g.fillStyle = PAL.oferta; g.font = '66px Anton'; g.fillText('5 CAMPANHAS', 300, 620);
  r.t.needsUpdate = true;
  return r.t;
};
const Pack: React.FC<{pos: V3; rotY: number; esc?: number}> = ({pos, rotY, esc = 1}) => {
  const frente = usePackTex();
  const mats = useMemo(() => {
    const lado = new THREE.MeshStandardMaterial({color: '#0e1d19', roughness: 0.5, metalness: 0.3, emissive: '#00ffff', emissiveIntensity: 0.04});
    const f = new THREE.MeshBasicMaterial({map: frente, toneMapped: false});
    return [lado, lado, lado, lado, f, lado];
  }, [frente]);
  const geo = useMemo(() => new THREE.BoxGeometry(3.0, 3.8, 0.8), []);
  const ar = useMemo(() => new THREE.EdgesGeometry(geo), [geo]);
  return (
    <group position={pos} rotation={[0, rotY, 0]} scale={esc}>
      <mesh geometry={geo} material={mats} castShadow />
      <lineSegments geometry={ar}><lineBasicMaterial color={PAL.destaque} toneMapped={false} /></lineSegments>
    </group>
  );
};

// 14. "Estão no Pack Marca3, prontas pra copiar e colar." (45,8 a 49,3 s): os 5 cartões entram no pacote.
export const OticaPack: React.FC = () => {
  usePronto(); const t = useT();
  const cam: V3 = [Math.sin(t * 0.25) * 3, 3.6, 10.5 - t * 0.5];
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0, 3.3, 0]} fov={46} />
      <Cenario />
      <Loja x={0} z={-7} nossa cam={cam} dentro={8} brilho={0.5} />
      <Pack pos={[0, 3.4 + Math.sin(t * 2) * 0.08, 1.5]} rotY={Math.sin(t * 0.8) * 0.35 - 0.1} esc={sm(t / 0.35) * 0.3 + 0.7} />
      {CAMPANHAS.map((c, i) => {
        const u = sm((t - 0.15 - i * 0.22) / 0.8);
        if (u >= 1) return null;
        const de: V3 = [(i - 2) * 1.6, 7.6 - (i % 2) * 0.5, 2.0];
        const p: V3 = [lerp(de[0], 0, u), lerp(de[1], 3.4, u), lerp(de[2], 1.5, u)];
        return <Placa key={i} pos={p} cam={cam} larg={2.6} esc={1 - u * 0.85} fundo="rgba(6,16,14,0.95)" borda={PAL.destaque} linhas={[{txt: c.txt, px: 92, cor: PAL.destaque}]} cw={1400} />;
      })}
    </ThreeCanvas>
  );
};

// 15. "Por trinta e sete reais." (49,3 a 50,8 s): o número grande dentro da cena, sobre o pacote.
export const OticaPreco: React.FC = () => {
  usePronto(); const t = useT();
  const cam: V3 = [Math.sin(t * 0.5) * 1.5 + 1.2, 4.0, 9.0 - t * 0.6];
  const k = salto((t - 0.35) / 0.4);
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0, 4.0, 0]} fov={46} />
      <Cenario />
      <Loja x={0} z={-7} nossa cam={cam} dentro={8} brilho={0.5} />
      <Pack pos={[0, 2.4, 1.0]} rotY={-0.25 + t * 0.15} esc={0.8} />
      <pointLight position={[0, 6.5, 3]} color={PAL.oferta} intensity={18 * k} distance={9} />
      <Placa pos={[0, 6.0, 2.2]} cam={cam} larg={5.2} esc={k} linhas={[{txt: 'R$ 37', px: 330, cor: PAL.oferta}]} />
    </ThreeCanvas>
  );
};

// 16. Fecho: "A ótica cheia não é a mais barata. É a que lembra do cliente primeiro." (50,8 s ao fim): a ótica do gancho, cheia, sem cartaz.
export const OticaFinal: React.FC = () => {
  usePronto(); const t = useT();
  const az = rad(-24 + t * 7);
  const d = 8.6 - t * 0.35;
  const cam: V3 = [Math.sin(az) * d, 3.2 + t * 0.06, Math.cos(az) * d];
  return (
    <ThreeCanvas width={W} height={H} shadows>
      <Camera pos={cam} alvo={[0.2, 2.2, 0.6]} fov={46} />
      <Cenario />
      <Loja nossa cam={cam} dentro={16} brilho={0.9} gaveta={0.5} />
      <Loja x={-4.8} cam={cam} cartaz="-70%" cartazEsc={1.1} />
      <Loja x={4.8} cam={cam} corToldo="#8c9a96" cartaz="-60%" cartazEsc={1.1} />
      <Gente n={14} area={[-1.6, 2.6, 2.3, 4.6]} seed={61} t={t} />
      <Fluxo n={10} t={t} t0={-1} dur={5} de={(i) => [-7 + rnd(i) * 16, 0, 6 + rnd(i + 2) * 3]} ate={[1.0, 0, 3.0]} seed={71} ficar />
      <Contador pos={[0, 5.5, 0.6]} cam={cam} n={58} larg={2.6} />
    </ThreeCanvas>
  );
};

export const CENAS_E: Record<string, React.FC> = {
  otica_gancho: OticaGancho, otica_mergulho: OticaMergulho, otica_rua: OticaRua, otica_cartaz: OticaCartaz,
  otica_enche: OticaEnche, otica_vizinha: OticaVizinha, otica_ciclo: OticaCiclo, otica_xray: OticaXray,
  otica_fichas: OticaFichas, otica_rotulos: OticaRotulos, otica_volta: OticaVolta, otica_quatro: OticaQuatro,
  otica_orbita: OticaOrbita, otica_pack: OticaPack, otica_preco: OticaPreco, otica_final: OticaFinal,
};
