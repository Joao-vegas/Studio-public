// Cenas em 3D de verdade (three.js via @remotion/three), desde 17/10/2026. Tudo modelado aqui no código
// (nenhum modelo de terceiro): roadster esportivo conversível sem marca + boneco de traje espacial (Starman).
// A Terra usa public/mapas/terra.jpg (textura da NASA, domínio público), com o oceano realçado em azul vivo.
// GRUPO A: dono de Carro, Starman, Terra, Estrelas, Camera, Luzes, Mundo, P, Seg (os grupos B, C e D só importam).
// Cenas do grupo A: "espaco", "volante", "carro_xray", "starman_close", "final_espaco".
import React, {createContext, useContext, useEffect, useMemo, useState} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {continueRender, delayRender, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';

const W = 1080, H = 1920;
const rad = (g: number) => (g * Math.PI) / 180;
const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const suave = (x: number) => { const k = clamp(x); return k * k * (3 - 2 * k); };

// ---------- texturas pintadas por código ----------
const canvasTex = (w: number, h: number, pinta: (c: CanvasRenderingContext2D) => void) => {
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  pinta(cv.getContext('2d')!);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
};
const blob = (c: CanvasRenderingContext2D, x: number, y: number, r: number, cor: string) => {
  const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, cor); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
};

// Ambiente (reflexo na pintura e no vidro): espaço preto, um Sol duro e a luz azul da Terra.
const useAmbiente = () => useMemo(() => {
  const t = canvasTex(1024, 512, (c) => {
    c.fillStyle = '#02030a'; c.fillRect(0, 0, 1024, 512);
    blob(c, 180, 360, 220, 'rgba(70,140,255,0.95)');   // Terra, azul grande e baixa
    blob(c, 700, 150, 60, 'rgba(255,248,230,1)');       // Sol
    blob(c, 700, 150, 170, 'rgba(255,240,210,0.35)');
    blob(c, 520, 470, 260, 'rgba(40,80,170,0.35)');
  });
  t.mapping = THREE.EquirectangularReflectionMapping; return t;
}, []);

// Ambiente só do visor espelhado do Starman: metade de baixo é a Terra azul com nuvens, um Sol duro no alto.
const useAmbienteVisor = () => useMemo(() => {
  const t = canvasTex(1024, 512, (c) => {
    const g = c.createLinearGradient(0, 0, 0, 512);
    g.addColorStop(0, '#010208'); g.addColorStop(0.46, '#03060f'); g.addColorStop(0.52, '#9fd0ff'); g.addColorStop(0.62, '#3b88ea'); g.addColorStop(1, '#0b3a8c');
    c.fillStyle = g; c.fillRect(0, 0, 1024, 512);
    c.fillStyle = 'rgba(255,255,255,0.32)';
    for (let i = 0; i < 22; i++) { c.beginPath(); c.ellipse((i * 173) % 1024, 290 + ((i * 53) % 200), 40 + (i % 5) * 16, 5 + (i % 4) * 2, 0.1, 0, 7); c.fill(); }
    c.fillStyle = 'rgba(40,110,40,0.55)'; c.beginPath(); c.ellipse(330, 400, 130, 46, 0.3, 0, 7); c.fill();
    c.beginPath(); c.ellipse(760, 330, 90, 28, -0.2, 0, 7); c.fill();
    for (const [x, y] of [[620, 60], [250, 120]]) { blob(c, x, y, 120, 'rgba(255,248,225,0.55)'); blob(c, x, y, 38, 'rgba(255,255,250,1)'); }
  });
  t.mapping = THREE.EquirectangularReflectionMapping; return t;
}, []);

// ---------- modo raio-X: todas as peças viram malha azul-clara transparente + arestas ----------
type Xray = {fill: THREE.Material; hi: THREE.Material; line: THREE.Material; lineHi: THREE.Material};
const XrayCtx = createContext<Xray | null>(null);
const arestasCache = new WeakMap<THREE.BufferGeometry, THREE.BufferGeometry>();
const arestas = (g: THREE.BufferGeometry) => {
  let e = arestasCache.get(g);
  if (!e) { const liso = /Sphere|Capsule|Torus|Cylinder/.test(g.type); e = new THREE.EdgesGeometry(g, liso ? 6 : 28); arestasCache.set(g, e); }
  return e;
};
const useXrayMats = (): Xray => useMemo(() => ({
  fill: new THREE.MeshBasicMaterial({color: '#58c8ff', transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending}),
  hi: new THREE.MeshBasicMaterial({color: '#58c8ff', transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending}),
  line: new THREE.LineBasicMaterial({color: '#a8ecff', transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending}),
  lineHi: new THREE.LineBasicMaterial({color: '#c8f4ff', transparent: true, opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending}),
}), []);

// ---------- peça com sombra ----------
export type Mat = THREE.Material;
export const P: React.FC<{geo: THREE.BufferGeometry; mat: Mat; pos?: [number, number, number]; rot?: [number, number, number]; esc?: [number, number, number]; vis?: boolean; xr?: 'fill' | 'hi'}> =
  ({geo, mat, pos = [0, 0, 0], rot = [0, 0, 0], esc = [1, 1, 1], vis = true, xr = 'fill'}) => {
    const x = useContext(XrayCtx);
    if (x) {
      if (!vis) return null;
      return (
        <group position={pos} rotation={rot} scale={esc}>
          <mesh geometry={geo} material={xr === 'hi' ? x.hi : x.fill} renderOrder={1} />
          <lineSegments geometry={arestas(geo)} material={xr === 'hi' ? x.lineHi : x.line} renderOrder={2} />
        </group>
      );
    }
    return <mesh geometry={geo} material={mat} position={pos} rotation={rot} scale={esc} castShadow receiveShadow visible={vis} />;
  };

// Segmento (cápsula) entre dois pontos: braços e pernas do Starman.
export const Seg: React.FC<{a: [number, number, number]; b: [number, number, number]; r: number; mat: Mat}> = ({a, b, r, mat}) => {
  const x = useContext(XrayCtx);
  const va = new THREE.Vector3(...a), vb = new THREE.Vector3(...b);
  const len = va.distanceTo(vb);
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), vb.clone().sub(va).normalize());
  const geo = useMemo(() => new THREE.CapsuleGeometry(r, Math.max(0.001, len - 2 * r), 8, 16), [r, len]);
  const mid = va.clone().add(vb).multiplyScalar(0.5);
  if (x) return <mesh geometry={geo} material={x.fill} position={mid} quaternion={q} renderOrder={1} />;
  return <mesh geometry={geo} material={mat} position={mid} quaternion={q} castShadow receiveShadow />;
};

// Mangueira (tubo ao longo de pontos).
const Tubo: React.FC<{pts: [number, number, number][]; r: number; mat: Mat}> = ({pts, r, mat}) => {
  const x = useContext(XrayCtx);
  const geo = useMemo(() => new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p))), 40, r, 10, false), [pts, r]);
  if (x) return <mesh geometry={geo} material={x.fill} renderOrder={1} />;
  return <mesh geometry={geo} material={mat} castShadow receiveShadow />;
};

// ---------- carro: roadster esportivo conversível, baixo e largo, vermelho, sem marca ----------
// x = para a frente, y = para cima, z = lado direito (o motorista fica no lado esquerdo, z negativo).
const RAIO_ARCO = 0.54, EIXO_F = 1.28, EIXO_T = -1.2, SILL = 0.28;
// "rail" = as laterais com os arcos de roda e a crista dos paralamas (mais altas que o capô).
const perfilLateral = () => {
  const s = new THREE.Shape();
  s.moveTo(-2.0, SILL);
  s.lineTo(EIXO_T - RAIO_ARCO, SILL); s.absarc(EIXO_T, SILL, RAIO_ARCO, Math.PI, 0, true);
  s.lineTo(EIXO_F - RAIO_ARCO, SILL); s.absarc(EIXO_F, SILL, RAIO_ARCO, Math.PI, 0, true);
  s.lineTo(1.98, SILL);
  s.quadraticCurveTo(2.17, SILL + 0.01, 2.17, 0.44);
  s.quadraticCurveTo(2.14, 0.62, 1.9, 0.7);
  s.bezierCurveTo(1.7, 0.78, 1.45, 0.88, 1.2, 0.9);   // crista do paralama dianteiro
  s.lineTo(0.42, 0.94);
  s.lineTo(-0.95, 0.94);                                // linha da porta
  s.bezierCurveTo(-1.3, 0.97, -1.6, 0.98, -1.85, 0.92);   // paralama traseiro
  s.quadraticCurveTo(-2.14, 0.84, -2.14, 0.62);
  s.quadraticCurveTo(-2.14, 0.4, -2.0, SILL);
  return s;
};
// miolo (capô, cabine aberta, tampa traseira), sem arcos de roda
const perfilMiolo = () => {
  const s = new THREE.Shape();
  s.moveTo(-2.0, SILL); s.lineTo(1.98, SILL);
  s.quadraticCurveTo(2.19, SILL + 0.01, 2.19, 0.42);
  s.quadraticCurveTo(2.16, 0.58, 1.95, 0.64);
  s.bezierCurveTo(1.5, 0.74, 1.0, 0.8, 0.62, 0.86);   // capô mais baixo que os paralamas
  s.lineTo(0.42, 0.9);
  s.lineTo(0.38, 0.8); s.lineTo(0.3, 0.58); s.lineTo(-0.82, 0.58); s.lineTo(-0.9, 0.8); s.lineTo(-0.95, 0.9);   // cabine aberta
  s.bezierCurveTo(-1.3, 0.92, -1.6, 0.92, -1.85, 0.86);
  s.quadraticCurveTo(-2.14, 0.8, -2.14, 0.6);
  s.quadraticCurveTo(-2.14, 0.4, -2.0, SILL);
  return s;
};

export const Roda: React.FC<{lado: 1 | -1; pneu: Mat; aro: Mat; freio: Mat}> = ({lado, pneu, aro, freio}) => {
  const g = useMemo(() => {
    const pts = [[0.2, -0.14], [0.29, -0.15], [0.355, -0.125], [0.385, -0.065], [0.392, 0], [0.385, 0.065], [0.355, 0.125], [0.29, 0.15], [0.2, 0.14]]
      .map(([r, y]) => new THREE.Vector2(r, y));
    return {
      pneu: new THREE.LatheGeometry(pts, 48),
      barril: new THREE.LatheGeometry([[0.2, -0.12], [0.235, -0.125], [0.245, -0.1], [0.245, 0.1], [0.235, 0.125], [0.2, 0.12]].map(([r, y]) => new THREE.Vector2(r, y)), 40),
      raio: new THREE.BoxGeometry(0.2, 0.03, 0.045),
      disco: new THREE.CylinderGeometry(0.17, 0.17, 0.03, 32),
      cubo: new THREE.CylinderGeometry(0.055, 0.055, 0.05, 20),
    };
  }, []);
  return (
    <group rotation={[Math.PI / 2, 0, 0]} scale={[1, lado, 1]}>
      <P geo={g.pneu} mat={pneu} />
      <P geo={g.barril} mat={aro} />
      <P geo={g.disco} mat={freio} pos={[0, -0.04, 0]} />
      {Array.from({length: 10}).map((_, i) => (
        <group key={i} rotation={[0, (i / 10) * Math.PI * 2, 0]}>
          <P geo={g.raio} mat={aro} pos={[0.11, 0.115, 0]} />
        </group>
      ))}
      <P geo={g.cubo} mat={freio} pos={[0, 0.115, 0]} />
    </group>
  );
};

// materiais do Starman (traje branco), separados para o Carro e o Starman poderem ser usados juntos ou sozinhos
const useMatsStarman = () => {
  const ambV = useAmbienteVisor();
  return useMemo(() => ({
    traje: new THREE.MeshStandardMaterial({color: '#eceef2', roughness: 0.72, metalness: 0.02, envMapIntensity: 0.4}),
    trajeSombra: new THREE.MeshStandardMaterial({color: '#bcc1cb', roughness: 0.82}),
    metal: new THREE.MeshStandardMaterial({color: '#c3c8d2', roughness: 0.4, metalness: 0.5, envMapIntensity: 0.9}),
    cinto: new THREE.MeshStandardMaterial({color: '#3b4250', roughness: 0.6, metalness: 0.2}),
    mangueira: new THREE.MeshStandardMaterial({color: '#aab0ba', roughness: 0.55, metalness: 0.15}),
    capacete: new THREE.MeshPhysicalMaterial({color: '#f4f5f8', roughness: 0.22, metalness: 0.08, clearcoat: 0.9, clearcoatRoughness: 0.1}),
    viseira: new THREE.MeshStandardMaterial({color: '#dfe6f2', roughness: 0.03, metalness: 1, envMap: ambV, envMapIntensity: 2.1}),
    luva: new THREE.MeshStandardMaterial({color: '#d4d8df', roughness: 0.7, envMapIntensity: 0.3}),
    bota: new THREE.MeshStandardMaterial({color: '#c8ccd4', roughness: 0.75}),
    sola: new THREE.MeshStandardMaterial({color: '#1c1d22', roughness: 0.8}),
    btVerm: new THREE.MeshStandardMaterial({color: '#ff2a1a', emissive: '#ff1408', emissiveIntensity: 1.6}),
    btAzul: new THREE.MeshStandardMaterial({color: '#3a8bff', emissive: '#2a6cff', emissiveIntensity: 1.6}),
    btBranco: new THREE.MeshStandardMaterial({color: '#ffffff', emissive: '#e8f0ff', emissiveIntensity: 1.2}),
    painel: new THREE.MeshStandardMaterial({color: '#6f7683', roughness: 0.6, metalness: 0.4}),
  }), [ambV]);
};

const ZM = -0.36;   // linha de centro do banco do motorista
// Starman: sentado no banco do motorista. Origem do grupo = pelve (-0.55, 0.72, ZM); esc cresce a partir da pelve.
export const Starman: React.FC<{pov?: boolean; esc?: number}> = ({pov = false, esc = 1}) => {
  const m = useMatsStarman();
  const g = useMemo(() => {
    const mang: [number, number, number][][] = [1, -1].map((s) => [
      [0.21, 0.4, s * 0.1], [0.27, 0.34, s * 0.1], [0.28, 0.22, s * 0.11], [0.22, 0.1, s * 0.15],
    ]);
    return {
      peito: new THREE.CapsuleGeometry(0.17, 0.26, 10, 20),
      abdomen: new THREE.CapsuleGeometry(0.15, 0.1, 8, 16),
      mochila: new THREE.BoxGeometry(0.13, 0.3, 0.32),
      cabeca: new THREE.SphereGeometry(0.2, 48, 36),
      visor: new THREE.SphereGeometry(0.208, 48, 28, Math.PI - 1.2, 2.4, 0.9, 1.1),
      anelCap: new THREE.TorusGeometry(0.165, 0.013, 12, 48),
      pescoco: new THREE.CylinderGeometry(0.1, 0.12, 0.1, 20),
      anelPesc: new THREE.TorusGeometry(0.11, 0.016, 12, 32),
      cinto: new THREE.TorusGeometry(0.17, 0.022, 10, 40),
      fivela: new THREE.BoxGeometry(0.03, 0.06, 0.09),
      painel: new THREE.BoxGeometry(0.035, 0.1, 0.17),
      botao: new THREE.CylinderGeometry(0.014, 0.014, 0.02, 14),
      conector: new THREE.CylinderGeometry(0.03, 0.03, 0.04, 14),
      ombro: new THREE.SphereGeometry(0.043, 20, 16),
      cotovelo: new THREE.SphereGeometry(0.034, 16, 12),
      punho: new THREE.TorusGeometry(0.038, 0.011, 8, 18),
      luva: new THREE.SphereGeometry(0.037, 20, 16),
      polegar: new THREE.SphereGeometry(0.016, 12, 10),
      joelho: new THREE.SphereGeometry(0.07, 16, 12),
      bota: new THREE.BoxGeometry(0.25, 0.1, 0.125),
      sola: new THREE.BoxGeometry(0.26, 0.025, 0.13),
      canoBota: new THREE.TorusGeometry(0.056, 0.015, 8, 18),
      mang,
    };
  }, []);
  const lean = 0.3;
  const v = (x: number, y: number, z: number): [number, number, number] => [x, y, z];
  return (
    <group position={[-0.55, 0.72, ZM]} scale={esc}>
      {/* tronco */}
      <group visible={!pov}>
        <P geo={g.abdomen} mat={m.traje} pos={v(-0.01, 0.08, 0)} rot={[0, 0, lean * 0.8]} esc={[0.95, 1, 1.25]} />
        <P geo={g.peito} mat={m.traje} pos={v(0.05, 0.3, 0)} rot={[0, 0, lean]} esc={[0.95, 1, 1.22]} />
        <P geo={g.cinto} mat={m.cinto} pos={v(0.02, 0.15, 0)} rot={[Math.PI / 2, 0, 0]} esc={[1.02, 1.28, 1]} />
        <P geo={g.fivela} mat={m.metal} pos={v(0.19, 0.14, 0)} rot={[0, 0, lean]} />
        {/* painel de controle no peito com botões */}
        <group position={v(0.2, 0.4, 0)} rotation={[0, 0, lean]}>
          <P geo={g.painel} mat={m.painel} />
          <P geo={g.botao} mat={m.btVerm} pos={v(0.02, 0.025, -0.05)} rot={[0, 0, Math.PI / 2]} />
          <P geo={g.botao} mat={m.btAzul} pos={v(0.02, 0.025, 0)} rot={[0, 0, Math.PI / 2]} />
          <P geo={g.botao} mat={m.btBranco} pos={v(0.02, 0.025, 0.05)} rot={[0, 0, Math.PI / 2]} />
          <P geo={g.botao} mat={m.btBranco} pos={v(0.02, -0.02, -0.03)} rot={[0, 0, Math.PI / 2]} esc={[0.8, 0.8, 0.8]} />
          <P geo={g.botao} mat={m.btVerm} pos={v(0.02, -0.02, 0.03)} rot={[0, 0, Math.PI / 2]} esc={[0.8, 0.8, 0.8]} />
          <P geo={g.conector} mat={m.metal} pos={v(0.01, 0.0, -0.1)} rot={[0, 0, Math.PI / 2]} />
          <P geo={g.conector} mat={m.metal} pos={v(0.01, 0.0, 0.1)} rot={[0, 0, Math.PI / 2]} />
        </group>
        {/* alças do arnês, do ombro ao cinto */}
        {/* mangueiras do traje */}
        {g.mang.map((pts, i) => <Tubo key={i} pts={pts} r={0.017} mat={m.mangueira} />)}
        {/* mochila de suporte de vida */}
        <P geo={g.mochila} mat={m.trajeSombra} pos={v(-0.14, 0.3, 0)} rot={[0, 0, lean]} />
        <P geo={g.conector} mat={m.metal} pos={v(-0.2, 0.42, -0.08)} rot={[0, 0, lean + 1.4]} />
        <P geo={g.conector} mat={m.metal} pos={v(-0.2, 0.42, 0.08)} rot={[0, 0, lean + 1.4]} />
        {/* pescoço, capacete e visor */}
        <P geo={g.anelPesc} mat={m.metal} pos={v(0.02, 0.6, 0)} rot={[Math.PI / 2, 0, 0.0]} />
        <P geo={g.pescoco} mat={m.trajeSombra} pos={v(0.03, 0.64, 0)} rot={[0, 0, 0.1]} />
        <P geo={g.anelCap} mat={m.metal} pos={v(0.05, 0.7, 0)} rot={[Math.PI / 2, 0, 0.0]} />
        <P geo={g.cabeca} mat={m.capacete} pos={v(0.07, 0.86, 0)} />
        <P geo={g.visor} mat={m.viseira} pos={v(0.07, 0.86, 0)} />
      </group>
      {/* braços finos e articulados: ombro, braço, cotovelo, antebraço, punho e luva no volante */}
      {[1, -1].map((s) => {
        const ombro = v(0.06, 0.5, s * 0.2), cot = v(0.31, 0.27, s * 0.25), pun = v(0.6, 0.3, s * 0.17), luva = v(0.64, 0.31, s * 0.17), cuf = v(0.54, 0.296, s * 0.172);
        return (
          <group key={s}>
            {!pov && <>
              <P geo={g.ombro} mat={m.traje} pos={ombro} />
              <Seg a={ombro} b={cot} r={0.026} mat={m.traje} />
            </>}
            <P geo={g.cotovelo} mat={m.trajeSombra} pos={cot} />
            <Seg a={cot} b={cuf} r={0.023} mat={m.traje} />
            <Seg a={cuf} b={pun} r={0.03} mat={m.trajeSombra} />
            <P geo={g.luva} mat={m.luva} pos={luva} esc={[1.15, 0.85, 1.0]} />
            <P geo={g.polegar} mat={m.luva} pos={v(0.63, 0.345, s * 0.158)} />
          </group>
        );
      })}
      {/* pernas: coxa, joelho, canela, bota com sola */}
      {!pov && [1, -1].map((s) => {
        const quad = v(0.0, 0.0, s * 0.11), joe = v(0.55, 0.0, s * 0.12), tor = v(0.93, -0.14, s * 0.12);
        return (
          <group key={s}>
            <Seg a={quad} b={joe} r={0.08} mat={m.traje} />
            <P geo={g.joelho} mat={m.trajeSombra} pos={joe} />
            <Seg a={joe} b={tor} r={0.058} mat={m.traje} />
            <P geo={g.canoBota} mat={m.cinto} pos={v(0.88, -0.12, s * 0.12)} rot={[0, 0, 1.2]} />
            <P geo={g.bota} mat={m.bota} pos={v(1.0, -0.16, s * 0.12)} />
            <P geo={g.sola} mat={m.sola} pos={v(1.0, -0.215, s * 0.12)} />
          </group>
        );
      })}
    </group>
  );
};

export const Carro: React.FC<{pov?: boolean; xray?: boolean; starman?: boolean; starmanEsc?: number}> = ({pov = false, xray = false, starman = true, starmanEsc = 1.12}) => {
  const xm = useXrayMats();
  const m = useMemo(() => ({
    tinta: new THREE.MeshPhysicalMaterial({color: '#c4101c', roughness: 0.28, metalness: 0.35, clearcoat: 1, clearcoatRoughness: 0.08, envMapIntensity: 1.3}),
    preto: new THREE.MeshStandardMaterial({color: '#08080a', roughness: 0.95, metalness: 0.0}),
    grade: new THREE.MeshStandardMaterial({color: '#3a1015', roughness: 0.5, metalness: 0.3}),
    couro: new THREE.MeshStandardMaterial({color: '#18181c', roughness: 0.6, metalness: 0.05}),
    pneu: new THREE.MeshStandardMaterial({color: '#0a0a0b', roughness: 0.9}),
    aro: new THREE.MeshStandardMaterial({color: '#c9ced6', roughness: 0.22, metalness: 0.95, envMapIntensity: 1.2}),
    freio: new THREE.MeshStandardMaterial({color: '#2a2c31', roughness: 0.5, metalness: 0.7}),
    vidro: new THREE.MeshPhysicalMaterial({color: '#a9bdd2', roughness: 0.05, metalness: 0, transparent: true, opacity: 0.1, envMapIntensity: 1.5, side: THREE.DoubleSide, depthWrite: false}),
    farol: new THREE.MeshStandardMaterial({color: '#fff', emissive: '#e8f2ff', emissiveIntensity: 2.6, roughness: 0.1}),
    lanterna: new THREE.MeshStandardMaterial({color: '#ff1a1a', emissive: '#ff0a0a', emissiveIntensity: 2.2, roughness: 0.3}),
    mostrador: new THREE.MeshStandardMaterial({color: '#aee4ff', emissive: '#6fd0ff', emissiveIntensity: 1.6}),
  }), []);

  const g = useMemo(() => {
    const ext = (sh: THREE.Shape, depth: number, bev = 0.04) => {
      const e = new THREE.ExtrudeGeometry(sh, {depth, bevelEnabled: true, bevelThickness: bev, bevelSize: bev, bevelSegments: 6, curveSegments: 32});
      e.translate(0, 0, -depth / 2); return e;
    };
    return {
      lado: ext(perfilLateral(), 0.3),
      miolo: ext(perfilMiolo(), 1.5),
      piso: new THREE.BoxGeometry(1.2, 0.05, 1.1),
      portaInt: new THREE.BoxGeometry(1.2, 0.42, 0.04),
      parabrisa: new THREE.BoxGeometry(0.025, 0.3, 1.5),
      moldura: new THREE.BoxGeometry(0.05, 0.035, 1.55),
      pilar: new THREE.BoxGeometry(0.04, 0.32, 0.04),
      farol: new THREE.SphereGeometry(1, 28, 18),
      lanterna: new THREE.BoxGeometry(0.05, 0.075, 0.36),
      grade: new THREE.BoxGeometry(0.05, 0.1, 0.9),
      frisoBaixo: new THREE.BoxGeometry(0.05, 0.03, 1.2),
      saia: new THREE.BoxGeometry(2.2, 0.05, 0.08),
      assento: new THREE.BoxGeometry(0.5, 0.1, 0.4),
      encosto: new THREE.BoxGeometry(0.1, 0.55, 0.4),
      painel: new THREE.BoxGeometry(0.34, 0.42, 1.24),
      coluna: new THREE.CylinderGeometry(0.025, 0.025, 0.3, 12),
      volante: new THREE.TorusGeometry(0.17, 0.021, 14, 40),
      raioVol: new THREE.BoxGeometry(0.012, 0.02, 0.32),
      mostr: new THREE.CylinderGeometry(0.05, 0.05, 0.02, 24),
      capsulaCabeca: new THREE.CapsuleGeometry(0.1, 0.28, 8, 16),
      espelho: new THREE.BoxGeometry(0.07, 0.05, 0.1),
      bateria: new THREE.BoxGeometry(2.3, 0.1, 1.05),
      motor: new THREE.CylinderGeometry(0.16, 0.16, 0.5, 24),
      eixo: new THREE.CylinderGeometry(0.03, 0.03, 1.6, 12),
      quadro: new THREE.BoxGeometry(0.06, 0.06, 1.1),
    };
  }, []);

  const corpo = (
    <group>
      {/* carroceria: laterais (com a crista dos paralamas) sobrepostas ao miolo, sem frisos escuros no encontro */}
      <P geo={g.lado} mat={m.tinta} pos={[0, 0, 0.77]} />
      <P geo={g.lado} mat={m.tinta} pos={[0, 0, -0.77]} />
      <P geo={g.miolo} mat={m.tinta} />
      <P geo={g.piso} mat={m.couro} pos={[-0.25, 0.52, 0]} />
      {[1, -1].map((s) => <P key={`pp${s}`} geo={g.portaInt} mat={m.couro} pos={[-0.25, 0.74, 0.605 * s]} />)}
      {/* saias e entrada de ar baixa, em tom de vinho escuro e bem pequena */}
      <P geo={g.saia} mat={m.preto} pos={[0.02, 0.26, 0.93]} />
      <P geo={g.saia} mat={m.preto} pos={[0.02, 0.26, -0.93]} />
      <P geo={g.grade} mat={m.grade} pos={[2.22, 0.4, 0]} />
      <P geo={g.frisoBaixo} mat={m.grade} pos={[2.17, 0.3, 0]} />
      {/* faróis e lanternas (sem marca) */}
      {[1, -1].map((s) => (
        <group key={s}>
          <P geo={g.farol} mat={m.preto} pos={[1.95, 0.73, 0.68 * s]} rot={[0, 0.25 * s, -0.28]} esc={[0.15, 0.06, 0.14]} />
          <P geo={g.farol} mat={m.farol} pos={[1.985, 0.73, 0.68 * s]} rot={[0, 0.25 * s, -0.28]} esc={[0.145, 0.055, 0.135]} />
          <P geo={g.lanterna} mat={m.lanterna} pos={[-2.2, 0.68, 0.6 * s]} />
          <P geo={g.espelho} mat={m.tinta} pos={[0.4, 1.0, 0.9 * s]} />
        </group>
      ))}
      {/* parabrisa baixo */}
      <group position={[0.44, 0.93, 0]} rotation={[0, 0, 0.62]}>
        <P geo={g.parabrisa} mat={m.vidro} pos={[0, 0.15, 0]} />
        <P geo={g.moldura} mat={m.preto} pos={[0, 0.31, 0]} />
        <P geo={g.pilar} mat={m.preto} pos={[0, 0.16, 0.77]} />
        <P geo={g.pilar} mat={m.preto} pos={[0, 0.16, -0.77]} />
      </group>
      {/* encostos de cabeça aerodinâmicos atrás dos bancos */}
      {[1, -1].map((s) => (
        <P key={s} geo={g.capsulaCabeca} mat={m.tinta} pos={[-1.0, 0.98, 0.36 * s]} rot={[0, 0, Math.PI / 2 - 0.12]} esc={[1, 1, 1.15]} />
      ))}
      {/* bancos */}
      {[1, -1].map((s) => (
        <group key={s}>
          <P geo={g.assento} mat={m.couro} pos={[-0.4, 0.6, 0.36 * s]} />
          <P geo={g.encosto} mat={m.couro} pos={[-0.66, 0.84, 0.36 * s]} rot={[0, 0, -0.22]} />
        </group>
      ))}
      {/* painel e instrumentos */}
      <P geo={g.painel} mat={m.preto} pos={[0.3, 0.73, 0]} rot={[0, 0, -0.12]} />
      <P geo={g.mostr} mat={m.mostrador} pos={[0.25, 0.9, ZM + 0.1]} rot={[0, 0, -1.6]} />
      <P geo={g.mostr} mat={m.mostrador} pos={[0.25, 0.9, ZM - 0.1]} rot={[0, 0, -1.6]} />
      {/* volante */}
      <group position={[0.1, 1.02, ZM]}>
        <P geo={g.coluna} mat={m.preto} pos={[0.1, -0.1, 0]} rot={[0, 0, -1.15]} />
        <group rotation={[0, 0, -0.35]}>
          <P geo={g.volante} mat={m.couro} rot={[0, Math.PI / 2, 0]} />
          <P geo={g.raioVol} mat={m.couro} rot={[Math.PI / 2, 0, 0]} esc={[1, 1, 0.6]} />
        </group>
      </group>
      {/* rodas */}
      {[[EIXO_F, 1], [EIXO_F, -1], [EIXO_T, 1], [EIXO_T, -1]].map(([x, s], i) => (
        <group key={i} position={[x, 0.39, 0.8 * s]} scale={1.08}><Roda lado={s as 1 | -1} pneu={m.pneu} aro={m.aro} freio={m.freio} /></group>
      ))}
      {/* só no raio-X: bateria sob o piso, motor traseiro, eixos e subquadros */}
      {xray && <>
        <P geo={g.bateria} mat={m.preto} pos={[-0.1, 0.36, 0]} xr="hi" />
        <P geo={g.motor} mat={m.preto} pos={[EIXO_T, 0.37, 0]} rot={[Math.PI / 2, 0, 0]} xr="hi" />
        <P geo={g.eixo} mat={m.preto} pos={[EIXO_F, 0.37, 0]} rot={[Math.PI / 2, 0, 0]} />
        <P geo={g.eixo} mat={m.preto} pos={[EIXO_T, 0.37, 0]} rot={[Math.PI / 2, 0, 0]} />
        <P geo={g.quadro} mat={m.preto} pos={[1.7, 0.42, 0]} />
        <P geo={g.quadro} mat={m.preto} pos={[-1.85, 0.42, 0]} />
      </>}
    </group>
  );
  const boneco = starman ? <Starman pov={pov} esc={starmanEsc} /> : null;
  return xray ? <XrayCtx.Provider value={xm}>{corpo}{boneco}</XrayCtx.Provider> : <group>{corpo}{boneco}</group>;
};

// ---------- Terra com textura da NASA (oceano realçado) + atmosfera ----------
// A textura original tem oceano quase preto; aqui os pixels de água ganham azul vivo e as nuvens/gelo/terra ficam como estão.
const useTexturaTerra = (arq: string) => {
  const [t, setT] = useState<THREE.Texture | null>(null);
  const [h] = useState(() => delayRender(`tex ${arq}`));
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const w = 4096, hh = 2048;
      const cv = document.createElement('canvas'); cv.width = w; cv.height = hh;
      const c = cv.getContext('2d')!; c.drawImage(img, 0, 0, w, hh);
      const d = c.getImageData(0, 0, w, hh), p = d.data;
      for (let i = 0; i < p.length; i += 4) {
        const r = p[i], g = p[i + 1], b = p[i + 2];
        const agua = suave((b - r - 8) / 22) * suave((b - g + 6) / 14) * (1 - suave((r - 70) / 40)) * (1 - suave((Math.min(r, g, b) - 130) / 40));
        if (agua <= 0) continue;
        const k = clamp((b - 28) / 70);                      // fundo (0) → raso (1)
        const nr = 8 + 44 * k, ng = 70 + 95 * k, nb = 185 + 60 * k;
        p[i] = r + (nr - r) * agua; p[i + 1] = g + (ng - g) * agua; p[i + 2] = b + (nb - b) * agua;
      }
      c.putImageData(d, 0, 0);
      const tx = new THREE.CanvasTexture(cv); tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 8; setT(tx);
    };
    img.onerror = (e) => { console.error('ERRO textura', arq, String(e)); continueRender(h); };
    img.src = staticFile(arq);
  }, [arq, h]);
  useEffect(() => { if (t) { const id = requestAnimationFrame(() => requestAnimationFrame(() => continueRender(h))); return () => cancelAnimationFrame(id); } }, [t, h]);
  return t;
};
const atmoVert = 'varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }';
const glowFrag = 'varying vec3 vN; void main(){ float i = pow(max(0.0, 0.72 - dot(vN, vec3(0.0,0.0,1.0))), 3.2); gl_FragColor = vec4(0.25,0.5,0.95,1.0) * i * 1.1; }';
const rimFrag = 'varying vec3 vN; void main(){ float i = pow(1.0 - max(0.0, dot(vN, vec3(0.0,0.0,1.0))), 3.5); gl_FragColor = vec4(0.4,0.66,1.0,1.0) * i * 0.6; }';
export const Terra: React.FC<{r: number; pos: [number, number, number]; giro: number}> = ({r, pos, giro}) => {
  const tex = useTexturaTerra('mapas/terra.jpg');
  return (
    <group position={pos}>
      <mesh rotation={[0.1, giro, 0]} receiveShadow><sphereGeometry args={[r, 128, 96]} /><meshStandardMaterial key={tex ? 'com' : 'sem'} color="#c8dcff" map={tex ?? undefined} emissive="#ffffff" emissiveMap={tex ?? undefined} emissiveIntensity={1.15} roughness={0.85} metalness={0} /></mesh>
      <mesh scale={1.012}><sphereGeometry args={[r, 96, 64]} /><shaderMaterial vertexShader={atmoVert} fragmentShader={rimFrag} transparent blending={THREE.AdditiveBlending} depthWrite={false} /></mesh>
      <mesh scale={1.14}><sphereGeometry args={[r, 96, 64]} /><shaderMaterial vertexShader={atmoVert} fragmentShader={glowFrag} side={THREE.BackSide} transparent blending={THREE.AdditiveBlending} depthWrite={false} /></mesh>
    </group>
  );
};

// ---------- estrelas: camada fina densa, camada média, estrelas brilhantes e uma faixa de Via Láctea ----------
const pontoMole = () => canvasTex(64, 64, (c) => { blob(c, 32, 32, 32, 'rgba(255,255,255,1)'); });
export const Estrelas: React.FC<{centro?: [number, number, number]}> = ({centro = [0, 0, 0]}) => {
  const mats = useMemo(() => {
    const mk = (size: number, soft: number, k: number) => new THREE.ShaderMaterial({
      uniforms: {size: {value: size}, soft: {value: soft}, k: {value: k}},
      vertexShader: 'attribute vec3 color; varying vec3 vC; uniform float size; void main(){ vC = color; gl_PointSize = size; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'varying vec3 vC; uniform float soft; uniform float k; void main(){ float d = length(gl_PointCoord - 0.5) * 2.0; float a = 1.0 - smoothstep(soft, 1.0, d); if (a < 0.01) discard; gl_FragColor = vec4(vC * k, a); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    return {fina: mk(3.4, 0.3, 1.5), via: mk(2.6, 0.2, 0.9), nuvem: mk(64, 0.0, 0.03), media: mk(6, 0.2, 1.5), forte: mk(14, 0.0, 1.2)};
  }, []);
  const camadas = useMemo(() => {
    let s = 7;
    const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
    const faz = (n: number, faixa: boolean, nev = false) => {
      const p = new Float32Array(n * 3), cor = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        let u: number, th: number;
        if (faixa) {                               // Via Láctea: banda inclinada com concentração gaussiana
          const lon = rnd() * Math.PI * 2, lat = (rnd() + rnd() + rnd() - 1.5) * 0.28;
          const x = Math.cos(lat) * Math.cos(lon), y = Math.sin(lat), z = Math.cos(lat) * Math.sin(lon);
          const inc = 0.6, yy = y * Math.cos(inc) - z * Math.sin(inc), zz = y * Math.sin(inc) + z * Math.cos(inc);
          u = yy; th = Math.atan2(zz, x);
        } else { u = rnd() * 2 - 1; th = rnd() * Math.PI * 2; }
        const rr = 900, q = Math.sqrt(1 - u * u);
        p[i * 3] = rr * q * Math.cos(th); p[i * 3 + 1] = rr * u; p[i * 3 + 2] = rr * q * Math.sin(th);
        const b = faixa ? 0.3 + rnd() * 0.5 : 0.5 + rnd() * 0.5, tom = rnd();
        if (nev) { const q2 = rnd(); cor[i * 3] = q2 > 0.6 ? 0.55 : 0.3; cor[i * 3 + 1] = q2 > 0.6 ? 0.4 : 0.5; cor[i * 3 + 2] = 1; }
        else { cor[i * 3] = b * (tom > 0.8 ? 1 : 0.85); cor[i * 3 + 1] = b * 0.9; cor[i * 3 + 2] = b * (tom < 0.3 ? 1 : 0.97); }
      }
      const gg = new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.BufferAttribute(p, 3)); gg.setAttribute('color', new THREE.BufferAttribute(cor, 3)); return gg;
    };
    return {fina: faz(9000, false), media: faz(1600, false), forte: faz(80, false), via: faz(9000, true), nuvem: faz(8000, true, true)};
  }, []);
  return (
    <group position={centro}>
      <points geometry={camadas.nuvem} material={mats.nuvem} />
      <points geometry={camadas.fina} material={mats.fina} />
      <points geometry={camadas.via} material={mats.via} />
      <points geometry={camadas.media} material={mats.media} />
      <points geometry={camadas.forte} material={mats.forte} />
    </group>
  );
};

// ---------- câmera controlada pelo quadro ----------
export const Camera: React.FC<{pos: [number, number, number]; alvo: [number, number, number]; fov?: number; rolar?: number}> = ({pos, alvo, fov = 40, rolar = 0}) => {
  const {camera} = useThree();
  const c = camera as THREE.PerspectiveCamera;
  c.fov = fov; c.near = 0.05; c.far = 20000;
  c.position.set(...pos);
  c.up.set(Math.sin(rolar), Math.cos(rolar), 0);
  c.lookAt(...alvo);
  c.updateProjectionMatrix();
  return null;
};

// ---------- luzes: Sol duro de um lado, azul da Terra de preenchimento, contra-luz (rim) ----------
export const Luzes: React.FC<{azSol: number}> = ({azSol}) => {
  const env = useAmbiente();
  const sol = (az: number, el: number, d: number): [number, number, number] => [Math.cos(rad(el)) * Math.cos(rad(az)) * d, Math.sin(rad(el)) * d, Math.cos(rad(el)) * Math.sin(rad(az)) * d];
  return (
    <>
      <primitive object={env} attach="environment" />
      <ambientLight intensity={0.22} color="#8fb4ff" />
      <directionalLight position={sol(azSol, 28, 40)} intensity={4.6} color="#fff3e0" castShadow
        shadow-mapSize-width={2048} shadow-mapSize-height={2048} shadow-bias={-0.001} shadow-normalBias={0.07}
        shadow-camera-left={-4} shadow-camera-right={4} shadow-camera-top={4} shadow-camera-bottom={-4} shadow-camera-near={1} shadow-camera-far={90} />
      <directionalLight position={sol(azSol + 200, -18, 40)} intensity={0.8} color="#5a98ff" />
      <directionalLight position={sol(azSol + 150, 35, 40)} intensity={1.1} color="#b9d4ff" />
    </>
  );
};

// ---------- mundo: carro flutuando, Terra grande ao fundo ----------
// Direção média da câmera na cena 1 (a Terra fica do lado oposto, atrás do carro e abaixo).
const AZ_MEDIO = -50;
export const Mundo: React.FC<{t: number; pov?: boolean; azSol: number; terra?: boolean; starmanEsc?: number; centroEstrelas?: [number, number, number]}> = ({t, pov, azSol, terra = true, starmanEsc, centroEstrelas}) => {
  const dir = [Math.cos(rad(AZ_MEDIO)), Math.sin(rad(AZ_MEDIO))];
  return (
    <>
      <Luzes azSol={azSol} />
      <Estrelas centro={centroEstrelas} />
      {terra && <Terra r={34} pos={[-dir[0] * 62 - 4, -34, -dir[1] * 62]} giro={t * 0.03 + 1.2} />}
      <group position={[0, Math.sin(t * 1.1) * 0.05, 0]} rotation={[Math.sin(t * 0.8) * 0.02, 0, Math.sin(t * 0.9 + 1) * 0.025]}>
        <Carro pov={pov} starmanEsc={starmanEsc} />
      </group>
    </>
  );
};

// ---------- Cena 1 (0 a 3 s): câmera orbitando devagar em volta do carro, Terra azul atrás, Starman grande ----------
export const CenaEspaco: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const az = rad(-28 - t * 17);                      // órbita lenta
  const d = 11.4 + t * 0.7, alt = 1.9 + t * 0.12;
  return (
    <ThreeCanvas width={W} height={H} shadows style={{background: '#000'}}>
      <Camera pos={[Math.cos(az) * d, alt, Math.sin(az) * d]} alvo={[0.1, 0.15, 0]} fov={40} rolar={rad(-2 + t * 1.2)} />
      <Mundo t={t} azSol={-95} starmanEsc={1.5} />
    </ThreeCanvas>
  );
};

// ---------- Cena 2 (3 a 5,3 s): câmera no banco do motorista, volante com a luva e estrelas além do para-brisa ----------
export const CenaVolante: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const px = -0.92 + t * 0.035;
  return (
    <ThreeCanvas width={W} height={H} shadows style={{background: '#000'}}>
      <Camera pos={[px, 1.5 + Math.sin(t * 1.3) * 0.008, ZM + 0.02 + Math.sin(t * 0.7) * 0.015]} alvo={[3, 0.98 + Math.sin(t * 0.9) * 0.03, ZM + 0.02]} fov={64} rolar={rad(Math.sin(t * 0.6) * 0.8)} />
      <Mundo t={t} pov azSol={-150} terra={false} />
    </ThreeCanvas>
  );
};

// ---------- Cena 6 (17,7 a 20,7 s): carro em RAIO-X girando devagar, câmera orbitando, régua e peso ----------
const Rotulo: React.FC<{pos: [number, number, number]; yaw: number; texto: string; sub?: string; w?: number}> = ({pos, yaw, texto, sub, w = 2.6}) => {
  const tex = useMemo(() => canvasTex(1024, 256, (c) => {
    c.clearRect(0, 0, 1024, 256);
    c.textAlign = 'center'; c.fillStyle = '#d8f6ff'; c.font = '700 120px Inter, Arial, sans-serif'; c.fillText(texto, 512, sub ? 130 : 160);
    if (sub) { c.fillStyle = 'rgba(168,236,255,0.85)'; c.font = '600 54px Inter, Arial, sans-serif'; c.fillText(sub, 512, 215); }
  }), [texto, sub]);
  return (
    <mesh position={pos} rotation={[0, yaw, 0]}>
      <planeGeometry args={[w, w / 4]} />
      <meshBasicMaterial map={tex} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </mesh>
  );
};
export const CenaCarroXray: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const az = rad(-62 + t * 24);
  const d = 11.4 - t * 0.35, alt = 3.0 - t * 0.2;
  const cam: [number, number, number] = [Math.cos(az) * d, alt, Math.sin(az) * d];
  const yaw = Math.atan2(cam[0] - 0, cam[2] - 0);
  const ticks = useMemo(() => new THREE.BoxGeometry(0.012, 0.09, 0.012), []);
  const linha = useMemo(() => new THREE.BoxGeometry(4.4, 0.01, 0.01), []);
  const anel = useMemo(() => new THREE.RingGeometry(3.0, 3.015, 120), []);
  const anel2 = useMemo(() => new THREE.RingGeometry(4.4, 4.41, 120), []);
  const mat = useMemo(() => new THREE.MeshBasicMaterial({color: '#58c8ff', transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false}), []);
  const matAnel = useMemo(() => new THREE.MeshBasicMaterial({color: '#58c8ff', transparent: true, opacity: 0.18, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false}), []);
  return (
    <ThreeCanvas width={W} height={H} style={{background: '#020712'}}>
      <color attach="background" args={['#020712']} />
      <Camera pos={cam} alvo={[0, 0.55, 0]} fov={42} rolar={rad(-1.5)} />
      <group rotation={[0, t * 0.42, 0]}><Carro xray starmanEsc={1.12} /></group>
      {/* piso holográfico e régua de comprimento (3,95 m) abaixo do carro */}
      <mesh geometry={anel} material={matAnel} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} />
      <mesh geometry={anel2} material={matAnel} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} />
      <group position={[0, -0.02, 1.55]}>
        <mesh geometry={linha} material={mat} />
        {Array.from({length: 9}).map((_, i) => <mesh key={i} geometry={ticks} material={mat} position={[-2.0 + i * 0.5, 0.04, 0]} />)}
      </group>
      <Rotulo pos={[0, 0.34, 1.55]} yaw={yaw} texto="4.0 m" w={1.6} />
      <Rotulo pos={[0, 2.6, 0]} yaw={yaw} texto="2,800 LB" sub="≈ 1,270 KG" w={2.8} />
    </ThreeCanvas>
  );
};

// ---------- Cena 7 (20,7 a 24,9 s): close do Starman, travelling lento, Sol duro + contraluz ----------
export const CenaStarmanClose: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const k = t / 4.2;
  // travelling: da frente-esquerda para a frente-direita, sempre se aproximando um pouco
  const az = rad(-38 + k * 52);                       // 0 = olhando de frente para o Starman
  const d = 3.0 - k * 0.55;
  const alvo: [number, number, number] = [-0.4, 1.3 - k * 0.03, ZM];
  const cam: [number, number, number] = [alvo[0] + Math.cos(az) * d, 2.05 + k * 0.1, alvo[2] + Math.sin(az) * d];
  const env = useAmbiente();
  return (
    <ThreeCanvas width={W} height={H} shadows style={{background: '#000'}}>
      <Camera pos={cam} alvo={alvo} fov={30} rolar={rad(1.5 - k * 3)} />
      <primitive object={env} attach="environment" />
      <ambientLight intensity={0.16} color="#7fa8ff" />
      {/* Sol duro vindo de cima e de trás do lado esquerdo do quadro; contraluz atrás dele; azul da Terra de frente */}
      <directionalLight position={[10, 15, -16]} intensity={5.4} color="#fff1da" castShadow
        shadow-mapSize-width={2048} shadow-mapSize-height={2048} shadow-bias={-0.001} shadow-normalBias={0.05}
        shadow-camera-left={-3} shadow-camera-right={3} shadow-camera-top={3} shadow-camera-bottom={-3} shadow-camera-near={1} shadow-camera-far={80} />
      <directionalLight position={[-18, 8, 10]} intensity={6} color="#ffd9b0" />
      <directionalLight position={[16, -3, 4]} intensity={1.1} color="#4c8dff" />
      <Estrelas />
      <Terra r={46} pos={[-64, -56, 24]} giro={t * 0.03 + 0.6} />
      <Carro starmanEsc={1.12} />
    </ThreeCanvas>
  );
};

// ---------- Cena 13 (58,2 s ao fim): volta ao carro girando; a câmera se afasta até ele virar um ponto e sumir ----------
export const CenaFinalEspaco: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const az = rad(-30 - t * 11);
  const d = 11 * Math.pow(10, 0.27 * t);               // recuo exponencial: 11 m → ~3 km em 9 s
  const alt = 1.8 + d * 0.12;
  const cam: [number, number, number] = [Math.cos(az) * d, alt, Math.sin(az) * d];
  const esc = 1 - suave((t - 6.3) / 2.0);              // o carro encolhe até sumir
  const ponto = suave((t - 5.2) / 1.2) * (1 - suave((t - 8.3) / 1.4));
  const pontoGeo = useMemo(() => new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(new Float32Array([0, 0.6, 0]), 3)), []);
  const mole = useMemo(pontoMole, []);
  return (
    <ThreeCanvas width={W} height={H} shadows style={{background: '#000'}}>
      <Camera pos={cam} alvo={[0, 0.2, 0]} fov={40} rolar={rad(-2 + t * 0.8)} />
      <Luzes azSol={-95} />
      <Estrelas centro={cam} />
      {<Terra r={34} pos={[-Math.cos(rad(-50)) * 62 - 4, -34, -Math.sin(rad(-50)) * 62]} giro={t * 0.03 + 1.2} />}
      <group scale={Math.max(0.0001, esc)}>
        <group position={[0, Math.sin(t * 1.1) * 0.05, 0]} rotation={[Math.sin(t * 0.8) * 0.02, t * 0.5, Math.sin(t * 0.9 + 1) * 0.025]}>
          <Carro starmanEsc={1.2} />
        </group>
      </group>
      <points geometry={pontoGeo}><pointsMaterial color="#ff5a4a" size={4.5} sizeAttenuation={false} transparent opacity={ponto} map={mole} depthWrite={false} /></points>
    </ThreeCanvas>
  );
};

export const CenaCarroEspaco = CenaEspaco;
export const Teste3D: React.FC<{xray?: boolean}> = () => <CenaEspaco />;
export const CENAS_3D: Record<string, React.FC> = {
  espaco: CenaEspaco, volante: CenaVolante, carro_xray: CenaCarroXray, starman_close: CenaStarmanClose, final_espaco: CenaFinalEspaco,
};
