// Cenas 3D do grupo B do Short S001 (17/10/2026): 3 "afastar", 4 "lateral", 5 "foguete".
// Peças compartilhadas (Carro, Terra, Estrelas, Camera, Luzes, P, Seg) vêm de ./Cenas3D (somente leitura aqui).
import React, {useMemo} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {Carro, Terra, Estrelas, Camera, Luzes} from './Cenas3D';
import {TextoRevelado, useTexto} from './CenasB-texto';
import {CenaFoguete} from './CenasB-foguete';

const rad = (g: number) => (g * Math.PI) / 180;
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

const glowTex = () => {
  const cv = document.createElement('canvas'); cv.width = cv.height = 128;
  const c = cv.getContext('2d')!;
  const g = c.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, 'rgba(255,60,60,1)'); g.addColorStop(0.18, 'rgba(255,40,40,0.85)'); g.addColorStop(0.5, 'rgba(226,18,18,0.25)'); g.addColorStop(1, 'rgba(226,18,18,0)');
  c.fillStyle = g; c.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(cv);
};

// ---------- Cena 3: o carro vira um ponto vermelho; régua tracejada até a Terra e o texto "~62M MILES" ----------
const DUR3 = 2.8;
export const CenaAfastar: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  const u0 = clamp(t / DUR3);
  const u = 0.55 * (u0 * u0 * (3 - 2 * u0)) + 0.45 * u0;           // acelera e segue mexendo até o fim
  // coordenadas: carro na origem (a sombra do Sol é calculada em volta dele); Terra acima
  const TERRA_Y = 92, TERRA_R = 27;
  const w = Math.pow(u, 2.4);
  const alvo: [number, number, number] = [lerp(0, 22, w), lerp(1, 32, w), 0];
  const d = 13 * Math.pow(300 / 13, u) * (1 + 0.04 * t);
  const az = rad(lerp(-38, 0, u)), el = rad(lerp(9, 0, u));
  const pos: [number, number, number] = [alvo[0] + Math.sin(az) * Math.cos(el) * d, alvo[1] + Math.sin(el) * d, Math.cos(az) * Math.cos(el) * d];

  const glow = useMemo(glowTex, []);
  const texto = useTexto(1100, 300, (c) => {
    c.font = '270px Anton'; c.textBaseline = 'alphabetic'; c.lineJoin = 'round';
    const a = '~62M', b = ' MILES';
    const wa = c.measureText(a).width; c.font = '130px Anton'; const wb = c.measureText(b).width;
    const x0 = 16, y0 = 255;
    const pinta = (txt: string, fonte: string, x: number, cor: string) => {
      c.font = fonte; c.lineWidth = 14; c.strokeStyle = 'rgba(0,8,24,0.85)'; c.strokeText(txt, x, y0); c.fillStyle = cor; c.fillText(txt, x, y0);
    };
    pinta(a, '270px Anton', x0, '#ffffff'); pinta(b, '130px Anton', x0 + wa, '#58c8ff');
    return x0 + wa + wb + 16;
  });
  const rot = useTexto(520, 120, (c) => {
    c.font = '84px Anton'; c.lineJoin = 'round'; const w = c.measureText('ROADSTER').width;
    c.lineWidth = 10; c.strokeStyle = 'rgba(0,8,24,0.85)'; c.strokeText('ROADSTER', 12, 92); c.fillStyle = '#ff5a5a'; c.fillText('ROADSTER', 12, 92);
    return w + 24;
  });

  // régua: da Terra para o carro, traços aparecem de baixo para cima
  const N = 26, y0 = 7, y1 = TERRA_Y - TERRA_R - 2;
  const pr = clamp((t - 0.8) / 1.3);
  const tp = clamp((t - 1.55) / 0.85);
  const mat = <meshBasicMaterial color="#a8ecff" toneMapped={false} />;
  const sTxt = 56 / (texto ? texto.larg : 800);            // texto com ~56 unidades de largura
  const dotA = clamp((u - 0.35) / 0.4);

  return (
    <ThreeCanvas width={1080} height={1920} shadows style={{background: '#000'}}>
      <Camera pos={pos} alvo={alvo} fov={40} rolar={rad(lerp(-2, 0, u))} />
      <Luzes azSol={-95} />
      <Estrelas />
      <Terra r={TERRA_R} pos={[0, TERRA_Y, -2]} giro={t * 0.05 + 3.6} />
      <group rotation={[0, rad(-4 * t), 0]}><Carro /></group>
      {/* ponto vermelho (brilho) no lugar do carro quando está longe */}
      <sprite position={[0, 0.9, 0]} scale={[d * 0.13, d * 0.13, 1]} renderOrder={6}>
        <spriteMaterial map={glow} transparent opacity={dotA} blending={THREE.AdditiveBlending} depthWrite={false} />
      </sprite>
      {/* régua tracejada com travas nas pontas */}
      {Array.from({length: N}).map((_, i) => {
        const vis = (i + 0.5) / N <= pr;
        return <mesh key={i} position={[0, lerp(y0, y1, (i + 0.5) / N), 0.3]} scale={[0.5, ((y1 - y0) / N) * 0.58, 0.1]} visible={vis}><boxGeometry args={[1, 1, 1]} />{mat}</mesh>;
      })}
      {pr > 0.02 && <mesh position={[0, y0 - 0.6, 0.3]} scale={[4.6, 0.5, 0.1]}><boxGeometry args={[1, 1, 1]} />{mat}</mesh>}
      {pr > 0.98 && <mesh position={[0, y1 + 0.6, 0.3]} scale={[4.6, 0.5, 0.1]}><boxGeometry args={[1, 1, 1]} />{mat}</mesh>}
      <TextoRevelado r={texto} s={sTxt} x={5.5} y={lerp(y0, y1, 0.5) + 1} z={0.4} p={tp} />
      <TextoRevelado r={rot} s={0.0002067 * d} x={3.0 + 0.004 * d} y={-0.0113 * d - 0.6} z={0.4} p={clamp((t - 0.5) / 0.7) * dotA} />
    </ThreeCanvas>
  );
};

// ---------- Cena 4: o carro de lado em travelling lento, Terra curva embaixo, Sol duro ----------
export const CenaLateral: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = Math.min(f / fps, 4.6);
  const u = clamp(t / 4.3);
  const tx = lerp(-1.9, 2.0, u);                              // alvo anda do rabo para a frente
  const az = rad(lerp(-9, 5, u)), d = 16.5 - u * 1.3;
  const alvo: [number, number, number] = [tx, lerp(0.95, 1.1, u), 0];
  const pos: [number, number, number] = [tx - 0.5 + Math.sin(az) * d, lerp(0.85, 1.7, u), Math.cos(az) * d];
  return (
    <ThreeCanvas width={1080} height={1920} shadows style={{background: '#000'}}>
      <Camera pos={pos} alvo={alvo} fov={35} rolar={rad(lerp(-9, -5, u))} />
      <Luzes azSol={52} />
      <Estrelas />
      <Terra r={26} pos={[6, -31, -16]} giro={t * 0.04 + 2.1} />
      <group position={[0, Math.sin(t * 1.1) * 0.03, 0]} rotation={[Math.sin(t * 0.8) * 0.012, 0, Math.sin(t * 0.9 + 1) * 0.015]}><Carro /></group>
    </ThreeCanvas>
  );
};

export const CENAS_B: Record<string, React.FC> = {afastar: CenaAfastar, lateral: CenaLateral, foguete: CenaFoguete};
