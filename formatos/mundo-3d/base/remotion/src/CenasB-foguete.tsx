// Cena 5 do S001 (grupo B): foguete de três corpos (genérico, sem logo nem bandeira) subindo de uma costa simples.
// Unidade do mundo = 1 metro. Tudo modelado por código. Pad na origem; câmera do lado +z; mar ao fundo (-z).
import React, {useMemo} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {Camera} from './Cenas3D';

const rad = (g: number) => (g * Math.PI) / 180;
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const suave = (a: number, b: number, v: number) => { const x = clamp((v - a) / (b - a)); return x * x * (3 - 2 * x); };
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;
const semente = (s0: number) => { let s = s0; return () => ((s = (s * 16807) % 2147483647) / 2147483647); };

const canvasTex = (w: number, h: number, pinta: (c: CanvasRenderingContext2D) => void, rep?: [number, number]) => {
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
  pinta(cv.getContext('2d')!);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  if (rep) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...rep); }
  return t;
};

// ---------- dimensões do foguete (metros) ----------
const R = 1.83, HC = 42, HI = 4, HB = 40.5, LNOSE = 6.5, RF = 2.6, XB = 3.75;
const BASE_Y = 4.4;            // altura da base do foguete sobre o chão no início (mesa de lançamento)
const T_SOLTA = 0.55;          // segundos até soltar
const ACEL = 17;               // m/s² (média da subida)
const subida = (t: number) => (t < T_SOLTA ? 0 : 0.5 * ACEL * (t - T_SOLTA) ** 2 + 2.2 * (t - T_SOLTA) ** 1.5);

// textura do corpo: branco com seções, fuligem na base
const useCorpoTex = (h: number, soot = 6) => useMemo(() => canvasTex(128, 1024, (c) => {
  c.fillStyle = '#f2f2ef'; c.fillRect(0, 0, 128, 1024);
  const g = c.createLinearGradient(0, 0, 128, 0); g.addColorStop(0, 'rgba(0,0,0,0.10)'); g.addColorStop(0.35, 'rgba(255,255,255,0.08)'); g.addColorStop(0.7, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,0.16)');
  c.fillStyle = g; c.fillRect(0, 0, 128, 1024);
  const my = (m: number) => 1024 - (m / h) * 1024;
  c.strokeStyle = 'rgba(70,72,78,0.55)'; c.lineWidth = 2;
  for (let m = 7; m < h - 2; m += 8.4) { c.beginPath(); c.moveTo(0, my(m)); c.lineTo(128, my(m)); c.stroke(); }
  c.fillStyle = 'rgba(40,42,48,0.35)'; c.fillRect(30, 0, 3, 1024);     // costura vertical
  const s = c.createLinearGradient(0, my(0), 0, my(soot)); s.addColorStop(0, 'rgba(18,18,20,0.97)'); s.addColorStop(0.55, 'rgba(30,30,32,0.55)'); s.addColorStop(1, 'rgba(30,30,32,0)');
  c.fillStyle = s; c.fillRect(0, my(soot), 128, my(0) - my(soot));
  const top = c.createLinearGradient(0, 0, 0, 90); top.addColorStop(0, 'rgba(0,0,0,0.12)'); top.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = top; c.fillRect(0, 0, 128, 90);
}), [h, soot]);

const ogiva = (r: number, L: number, n = 28) => {
  const pts: THREE.Vector2[] = [];
  for (let i = 0; i <= n; i++) { const s = i / n; pts.push(new THREE.Vector2(Math.max(0.1, r * Math.pow(Math.cos((s * Math.PI) / 2), 0.78)), L * s)); }
  return new THREE.LatheGeometry(pts, 40);
};

const useGeos = () => useMemo(() => ({
  bocal: new THREE.LatheGeometry([[0.2, 0.8], [0.24, 0.55], [0.32, 0.15], [0.43, -0.4], [0.5, -0.9]].map(([r, y]) => new THREE.Vector2(r, y)), 20, 0, Math.PI * 2),
  cone: new THREE.ConeGeometry(1, 1, 18, 1, true),
  cil: new THREE.CylinderGeometry(1, 1, 1, 36),
  caixa: new THREE.BoxGeometry(1, 1, 1),
  esf: new THREE.SphereGeometry(1, 14, 10),
  noseB: ogiva(R, LNOSE),
  fair: ogiva(RF, 13.5),
}), []);

type Geos = ReturnType<typeof useGeos>;

// chama de um bocal (cones aditivos, comprimento tremendo)
const Chama: React.FC<{g: Geos; t: number; i: number; k: number; mats: {ext: THREE.Material; int: THREE.Material}}> = ({g, t, i, k, mats}) => {
  const fl = 1 + 0.12 * Math.sin(t * 61 + i * 2.1) + 0.07 * Math.sin(t * 37 + i);
  const Lx = 17 * k * fl, Li = 8 * k * fl;
  return (
    <>
      <mesh geometry={g.cone} material={mats.ext} position={[0, -0.9 - Lx / 2, 0]} rotation={[Math.PI, 0, 0]} scale={[0.95, Lx, 0.95]} />
      <mesh geometry={g.cone} material={mats.int} position={[0, -0.9 - Li / 2, 0]} rotation={[Math.PI, 0, 0]} scale={[0.5, Li, 0.5]} />
    </>
  );
};

const Corpo: React.FC<{g: Geos; x: number; boost: boolean; t: number; k: number; mats: any; tex: THREE.Texture}> = ({g, x, boost, t, k, mats, tex}) => {
  const hb = boost ? HB : HC;
  const matCorpo = useMemo(() => new THREE.MeshStandardMaterial({map: tex, roughness: 0.42, metalness: 0.12}), [tex]);
  const motores = useMemo(() => {
    const p: [number, number][] = [[0, 0]];
    for (let i = 0; i < 8; i++) p.push([Math.cos((i / 8) * Math.PI * 2) * 1.1, Math.sin((i / 8) * Math.PI * 2) * 1.1]);
    return p;
  }, []);
  return (
    <group position={[x, 0, 0]}>
      <mesh geometry={g.cil} material={matCorpo} position={[0, hb / 2, 0]} scale={[R, hb, R]} castShadow />
      {boost ? (
        <mesh geometry={g.noseB} material={mats.nariz} position={[0, hb, 0]} />
      ) : (
        <>
          <mesh geometry={g.cil} material={mats.interest} position={[0, HC + HI / 2, 0]} scale={[R * 1.005, HI, R * 1.005]} />
          <mesh geometry={g.cil} material={mats.branco} position={[0, HC + HI + 5, 0]} scale={[RF, 10, RF]} />
          <mesh geometry={g.fair} material={mats.branco} position={[0, HC + HI + 10, 0]} />
          <mesh geometry={g.cil} material={mats.cinza} position={[0, HC + HI + 10.1, 0]} scale={[RF * 1.003, 0.35, RF * 1.003]} />
        </>
      )}
      {/* saia do motor */}
      <mesh geometry={g.cil} material={mats.escuro} position={[0, 0.9, 0]} scale={[R * 1.01, 1.8, R * 1.01]} />
      {/* 9 motores */}
      {motores.map(([px, pz], i) => (
        <group key={i} position={[px, 0, pz]}>
          <mesh geometry={g.bocal} material={mats.bocal} />
          {k > 0.02 && <Chama g={g} t={t} i={i + (x > 0 ? 9 : x < 0 ? 18 : 0)} k={k} mats={mats} />}
        </group>
      ))}
      {/* pernas de pouso recolhidas (só nos laterais) e aletas de grade perto do topo */}
      {boost && [45, 135, 225, 315].map((a) => (
        <group key={a} rotation={[0, rad(a), 0]}>
          <mesh geometry={g.caixa} material={mats.perna} position={[R + 0.12, 6.6, 0]} rotation={[0, 0, -0.045]} scale={[0.34, 11.5, 0.7]} />
          <mesh geometry={g.caixa} material={mats.perna} position={[R + 0.1, 12.5, 0]} scale={[0.5, 0.7, 1.0]} />
          <mesh geometry={g.caixa} material={mats.perna} position={[R + 0.5, 0.9, 0]} rotation={[0, 0, -0.2]} scale={[0.4, 1.8, 0.9]} />
        </group>
      ))}
      {boost && [0, 90, 180, 270].map((a) => (
        <group key={a} rotation={[0, rad(a + 45), 0]}>
          <mesh geometry={g.caixa} material={mats.perna} position={[R + 0.25, HB - 2.6, 0]} scale={[0.1, 0.8, 1.1]} />
        </group>
      ))}
      {/* calha de cabos */}
      <mesh geometry={g.caixa} material={mats.cinza} position={[0, hb / 2, -R - 0.05]} scale={[0.35, hb - 3, 0.18]} />
    </group>
  );
};

const Foguete: React.FC<{t: number; disp: number; k: number; g: Geos; mats: any; tex42: THREE.Texture; tex40: THREE.Texture}> = ({t, disp, k, g, mats, tex42, tex40}) => (
  <group position={[0, BASE_Y + disp, 0]}>
    <Corpo g={g} x={0} boost={false} t={t} k={k} mats={mats} tex={tex42} />
    <Corpo g={g} x={-XB} boost t={t} k={k} mats={mats} tex={tex40} />
    <Corpo g={g} x={XB} boost t={t} k={k} mats={mats} tex={tex40} />
  </group>
);

// ---------- chão: grama, areia, mar, espuma ----------
const Costa: React.FC<{t: number}> = ({t}) => {
  const grama = useMemo(() => canvasTex(512, 512, (c) => {
    c.fillStyle = '#5b8a34'; c.fillRect(0, 0, 512, 512);
    const r = semente(11);
    for (let i = 0; i < 1400; i++) { const v = r(); c.fillStyle = v < 0.5 ? 'rgba(52,96,30,0.28)' : v < 0.8 ? 'rgba(112,150,60,0.22)' : 'rgba(150,170,80,0.16)'; c.beginPath(); c.arc(r() * 512, r() * 512, 3 + r() * 16, 0, 7); c.fill(); }
  }, [220, 30]), []);
  const areia = useMemo(() => canvasTex(512, 128, (c) => {
    c.fillStyle = '#e6d6a6'; c.fillRect(0, 0, 512, 128);
    const r = semente(5);
    for (let i = 0; i < 700; i++) { c.fillStyle = r() < 0.5 ? 'rgba(200,180,130,0.3)' : 'rgba(255,245,215,0.3)'; c.beginPath(); c.arc(r() * 512, r() * 128, 1 + r() * 4, 0, 7); c.fill(); }
  }, [60, 1]), []);
  const mar = useMemo(() => canvasTex(16, 512, (c) => {
    const g = c.createLinearGradient(0, 512, 0, 0);       // base do canvas = perto da praia
    g.addColorStop(0, '#6fe3d6'); g.addColorStop(0.03, '#35c6c8'); g.addColorStop(0.12, '#1b9fc4'); g.addColorStop(0.4, '#106fae'); g.addColorStop(1, '#0a3f86');
    c.fillStyle = g; c.fillRect(0, 0, 16, 512);
  }), []);
  const arbustos = useMemo(() => {
    const r = semente(23); const lista: {p: [number, number, number]; s: number; c: number}[] = [];
    while (lista.length < 140) {
      const x = (r() - 0.5) * 900, z = -70 + r() * 260;
      if (Math.abs(x) < 70 && z > -50 && z < 70) continue;
      lista.push({p: [x, 0, z], s: 2.5 + r() * 7, c: Math.floor(r() * 3)});
    }
    return lista;
  }, []);
  const cores = useMemo(() => ['#2f5d22', '#3d7228', '#4d8030'].map((c) => new THREE.MeshStandardMaterial({color: c, roughness: 0.95})), []);
  const geoB = useMemo(() => new THREE.IcosahedronGeometry(1, 1), []);
  const pulso = 0.55 + 0.25 * Math.sin(t * 1.7);
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 220]}><planeGeometry args={[2400, 600]} /><meshStandardMaterial map={grama} roughness={1} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, -104]}><planeGeometry args={[2400, 52]} /><meshStandardMaterial map={areia} roughness={1} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.9, -1380]}><planeGeometry args={[6000, 2500]} /><meshStandardMaterial map={mar} roughness={0.32} metalness={0.15} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.6, -133]}><planeGeometry args={[2400, 6]} /><meshBasicMaterial color="#ffffff" transparent opacity={pulso} depthWrite={false} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.7, -142]}><planeGeometry args={[2400, 3]} /><meshBasicMaterial color="#d8fbff" transparent opacity={pulso * 0.7} depthWrite={false} /></mesh>
      {arbustos.map((a, i) => <mesh key={i} geometry={geoB} material={cores[a.c]} position={[a.p[0], a.s * 0.3, a.p[2]]} scale={[a.s * 1.4, a.s * 0.6, a.s * 1.2]} />)}
    </>
  );
};

// ---------- plataforma, torre e anexos ----------
const Plataforma: React.FC<{g: Geos}> = ({g}) => {
  const m = useMemo(() => ({
    concreto: new THREE.MeshStandardMaterial({color: '#8d8e90', roughness: 0.95}),
    escuro: new THREE.MeshStandardMaterial({color: '#2b2c31', roughness: 0.7, metalness: 0.4}),
    torre: new THREE.MeshStandardMaterial({color: '#aeb2ba', roughness: 0.6, metalness: 0.5}),
    tanque: new THREE.MeshStandardMaterial({color: '#e8eaee', roughness: 0.4, metalness: 0.3}),
    vermelho: new THREE.MeshStandardMaterial({color: '#c4271f', roughness: 0.6}),
  }), []);
  const niveis = Array.from({length: 11}, (_, i) => 6 + i * 7.4);
  return (
    <group>
      <mesh geometry={g.caixa} material={m.concreto} position={[0, 0.3, 0]} scale={[90, 0.6, 90]} receiveShadow />
      <mesh geometry={g.caixa} material={m.concreto} position={[0, 1.6, 0]} scale={[22, 2.4, 22]} />
      <mesh geometry={g.caixa} material={m.escuro} position={[0, 3.3, 0]} scale={[17, 1.2, 17]} />
      {[[-6, -6], [6, -6], [-6, 6], [6, 6]].map(([x, z], i) => <mesh key={i} geometry={g.caixa} material={m.escuro} position={[x, 4.4, z]} scale={[1.6, 1.4, 1.6]} />)}
      {/* torre de serviço (treliça) */}
      <group position={[-27, 0, -3]}>
        {[[-2.8, -2.8], [2.8, -2.8], [-2.8, 2.8], [2.8, 2.8]].map(([x, z], i) => <mesh key={i} geometry={g.caixa} material={m.torre} position={[x, 41, z]} scale={[0.9, 82, 0.9]} />)}
        {niveis.map((y, i) => (
          <group key={i} position={[0, y, 0]}>
            <mesh geometry={g.caixa} material={m.torre} scale={[6.4, 0.35, 0.35]} position={[0, 0, 2.8]} />
            <mesh geometry={g.caixa} material={m.torre} scale={[6.4, 0.35, 0.35]} position={[0, 0, -2.8]} />
            <mesh geometry={g.caixa} material={m.torre} scale={[0.35, 0.35, 6.4]} position={[2.8, 0, 0]} />
            <mesh geometry={g.caixa} material={m.torre} scale={[0.35, 0.35, 6.4]} position={[-2.8, 0, 0]} />
            <mesh geometry={g.caixa} material={m.torre} scale={[0.25, 8.2, 0.25]} position={[0, 3.7, 2.8]} rotation={[0, 0, 0.74]} />
          </group>
        ))}
        <mesh geometry={g.caixa} material={m.vermelho} position={[13, 44, 0]} scale={[22, 1.4, 2.6]} />
        <mesh geometry={g.caixa} material={m.vermelho} position={[13, 64, 0]} scale={[22, 1.4, 2.6]} />
      </group>
      {/* para-raios */}
      {[[-70, -45], [75, -40], [0, -75]].map(([x, z], i) => <mesh key={i} geometry={g.cil} material={m.torre} position={[x, 60, z]} scale={[0.5, 120, 0.5]} />)}
      {/* tanques */}
      {[[32, -42], [44, -42]].map(([x, z], i) => <mesh key={i} geometry={g.cil} material={m.tanque} position={[x, 5, z]} rotation={[0, 0, Math.PI / 2]} scale={[4.5, 24, 4.5]} />)}
      <mesh geometry={g.esf} material={m.tanque} position={[-45, 8, -38]} scale={[8, 8, 8]} />
    </group>
  );
};

// ---------- fumaça e nuvem de fogo (sprites macios com sombreado pintado) ----------
const usePuffs = () => useMemo(() => [101, 202, 303].map((sd) => canvasTex(256, 256, (c) => {
  const r = semente(sd);
  const blob = (x: number, y: number, rr: number, cor: string, a: number) => {
    const g = c.createRadialGradient(x, y, 0, x, y, rr); g.addColorStop(0, cor.replace('A', String(a))); g.addColorStop(0.6, cor.replace('A', String(a * 0.55))); g.addColorStop(1, cor.replace('A', '0'));
    c.fillStyle = g; c.beginPath(); c.arc(x, y, rr, 0, 7); c.fill();
  };
  const pts = Array.from({length: 16}, () => { const a = r() * 6.28, d = Math.sqrt(r()) * 70; return [128 + Math.cos(a) * d, 128 + Math.sin(a) * d, 32 + r() * 30]; });
  pts.forEach(([x, y, rr]) => blob(x + 7, y + 9, rr, 'rgba(120,122,132,A)', 0.55));   // sombra (baixo-direita)
  pts.forEach(([x, y, rr]) => blob(x - 4, y - 6, rr * 0.9, 'rgba(255,255,255,A)', 0.85));  // luz (cima-esquerda)
  // borda suave
  const m = c.createRadialGradient(128, 128, 70, 128, 128, 128); m.addColorStop(0, 'rgba(0,0,0,0)'); m.addColorStop(1, 'rgba(0,0,0,1)');
  c.globalCompositeOperation = 'destination-out'; c.fillStyle = m; c.fillRect(0, 0, 256, 256);
})), []);

const Fumaca: React.FC<{t: number}> = ({t}) => {
  const tex = usePuffs();
  const trilha = useMemo(() => {
    const r = semente(41);
    return Array.from({length: 250}, (_, i) => {
      const tb = T_SOLTA - 0.1 + i / 46;
      return {tb, j: [r() - 0.5, r() - 0.5, r() - 0.5] as [number, number, number], r0: 3 + r() * 1.5, v: Math.floor(r() * 3), rot: r() * 6.28, o: [r() * 2 - 1, r() * 2 - 1, r() * 2 - 1]};
    });
  }, []);
  const chao = useMemo(() => {
    const r = semente(77);
    return Array.from({length: 95}, (_, i) => {
      const a = r() * Math.PI * 2;
      return {tb: -2.4 + i * 0.058, a, v: 14 + r() * 22, r0: 5 + r() * 4, h: 1 + r() * 4, v2: Math.floor(r() * 3), rot: r() * 6.28};
    });
  }, []);
  const fria = new THREE.Color('#f4f2ec'), quente = new THREE.Color('#ffb05c'), cinza = new THREE.Color('#bdbab5');
  const out: React.ReactNode[] = [];
  chao.forEach((c, i) => {
    const age = t - c.tb; if (age <= 0 || age > 9) return;
    const dist = (c.v * (1 - Math.exp(-age * 0.42))) / 0.42 + 8;
    const rr = c.r0 + 4.2 * Math.pow(age, 0.82);
    const op = clamp(age * 3) * Math.pow(clamp(1 - age / 9), 1.3) * 0.85;
    const col = quente.clone().lerp(fria, clamp(age / 0.6)).lerp(cinza, clamp((age - 2) / 7) * 0.4);
    out.push(<sprite key={`c${i}`} position={[Math.cos(c.a) * dist + 3 * age, c.h + rr * 0.45 + age * 1.0, Math.sin(c.a) * dist]} scale={[rr * 2.2, rr * 2.2, 1]} renderOrder={2}>
      <spriteMaterial map={tex[c.v2]} color={col} transparent opacity={op} depthWrite={false} rotation={c.rot + age * 0.05} />
    </sprite>);
  });
  trilha.forEach((p, i) => {
    const age = t - p.tb; if (age <= 0 || age > 8) return;
    const yb = BASE_Y + subida(p.tb) - 2;
    const rr = p.r0 + 5.4 * Math.pow(age, 0.78);
    const op = clamp(age * 5) * Math.pow(clamp(1 - age / 8), 1.1) * 0.8;
    const col = quente.clone().lerp(fria, clamp(age / 0.5)).lerp(cinza, clamp((age - 1.5) / 6) * 0.35);
    out.push(<sprite key={`t${i}`} position={[p.j[0] * 5 + 5.5 * age + p.o[0] * rr * 0.3, yb - age * 1.5 + p.o[1] * rr * 0.2, p.j[2] * 5 + p.o[2] * rr * 0.3]} scale={[rr * 2.3, rr * 2.3, 1]} renderOrder={2}>
      <spriteMaterial map={tex[p.v]} color={col} transparent opacity={op} depthWrite={false} rotation={p.rot + age * 0.15} />
    </sprite>);
  });
  return <>{out}</>;
};

// nuvens
const Nuvens: React.FC = () => {
  const tex = useMemo(() => canvasTex(256, 128, (c) => {
    const r = semente(3);
    for (let i = 0; i < 26; i++) {
      const x = 40 + r() * 176, y = 50 + r() * 28, rr = 18 + r() * 26;
      const g = c.createRadialGradient(x, y, 0, x, y, rr); g.addColorStop(0, 'rgba(255,255,255,0.55)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      c.fillStyle = g; c.beginPath(); c.arc(x, y, rr, 0, 7); c.fill();
    }
  }), []);
  const lista = useMemo(() => {
    const r = semente(9);
    return [...Array.from({length: 22}, () => ({p: [(r() - 0.5) * 2200, 120 + r() * 520, -700 - r() * 900] as [number, number, number], s: 280 + r() * 380})),
      ...Array.from({length: 16}, (_, i) => ({p: [(r() - 0.5) * 520, 90 + i * 34 + r() * 40, -70 - r() * 200] as [number, number, number], s: 110 + r() * 170}))];
  }, []);
  return <>{lista.map((n, i) => (
    <sprite key={i} position={n.p} scale={[n.s, n.s * 0.42, 1]}><spriteMaterial map={tex} transparent opacity={0.85} depthWrite={false} /></sprite>
  ))}</>;
};

const vertCeu = 'varying float vy; void main(){ vy = normalize(position).y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }';
const fragCeu = 'varying float vy; void main(){ float k = pow(clamp(vy, 0.0, 1.0), 0.55); vec3 c = mix(vec3(0.83,0.92,0.97), vec3(0.14,0.42,0.82), k); gl_FragColor = vec4(c,1.0); }';

const Glow: React.FC<{pos: [number, number, number]; r: number; op: number}> = ({pos, r, op}) => {
  const tex = useMemo(() => canvasTex(128, 128, (c) => {
    const g = c.createRadialGradient(64, 64, 0, 64, 64, 64); g.addColorStop(0, 'rgba(255,240,200,1)'); g.addColorStop(0.3, 'rgba(255,170,70,0.7)'); g.addColorStop(1, 'rgba(255,100,20,0)');
    c.fillStyle = g; c.fillRect(0, 0, 128, 128);
  }), []);
  return <sprite position={pos} scale={[r, r, 1]} renderOrder={5}><spriteMaterial map={tex} transparent opacity={op} blending={THREE.AdditiveBlending} depthWrite={false} /></sprite>;
};

export const CenaFoguete: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = Math.min(f / fps, 5.9);
  const g = useGeos();
  const tex42 = useCorpoTex(HC, 6), tex40 = useCorpoTex(HB, 7);
  const chamaTex = useMemo(() => canvasTex(8, 128, (c) => {
    const g = c.createLinearGradient(0, 0, 0, 128); g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.5, 'rgba(255,255,255,0.35)'); g.addColorStop(1, 'rgba(255,255,255,1)');
    c.fillStyle = g; c.fillRect(0, 0, 8, 128);
  }), []);
  const mats = useMemo(() => ({
    branco: new THREE.MeshStandardMaterial({color: '#f1f1ee', roughness: 0.4, metalness: 0.1}),
    cinza: new THREE.MeshStandardMaterial({color: '#6a6c72', roughness: 0.5, metalness: 0.4}),
    interest: new THREE.MeshStandardMaterial({color: '#1d1e22', roughness: 0.6, metalness: 0.3}),
    escuro: new THREE.MeshStandardMaterial({color: '#25262a', roughness: 0.7, metalness: 0.4}),
    nariz: new THREE.MeshStandardMaterial({color: '#e3e4e1', roughness: 0.4, metalness: 0.15}),
    perna: new THREE.MeshStandardMaterial({color: '#303238', roughness: 0.55, metalness: 0.5}),
    bocal: new THREE.MeshStandardMaterial({color: '#4a4b50', roughness: 0.4, metalness: 0.8, side: THREE.DoubleSide, emissive: '#ff7a1a', emissiveIntensity: 0.25}),
    ext: new THREE.MeshBasicMaterial({map: chamaTex, color: '#ff8a22', transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false}),
    int: new THREE.MeshBasicMaterial({map: chamaTex, color: '#fff1c4', transparent: true, opacity: 0.6, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false}),
  }), [chamaTex]);

  const disp = subida(t);
  const k = clamp(0.5 + t * 0.5, 0, 1) * (t < T_SOLTA ? 0.75 : 1) * (1 - 0.35 * suave(3.5, 5.9, t));  // chama encurta com a altitude
  const yb = BASE_Y + disp;

  // câmera: A (de lado, acompanhando) -> B (do chão, olhando para cima)
  const mB = suave(2.15, 3.7, t);
  const ya = 36 + 0.8 * disp;
  const camA: [number, number, number] = [lerp(-14, 16, t / 5.9), ya + 16, 150 - t * 3];
  const camB: [number, number, number] = [28 - t * 1.2, 3.5 + disp * 0.2, 60 - t * 2.5];
  const mid = yb + 30;
  const alvoA: [number, number, number] = [0, ya - 8, 0];
  const alvoB: [number, number, number] = [-1, mid + 6 + 0.1 * disp, 0];
  const tr = 0.12 + 0.55 * suave(0, 1.2, t) * (1 - 0.5 * suave(4, 5.9, t));          // intensidade do tremor
  const sh = (s: number, a: number, b: number) => Math.sin(t * a + s) * 0.6 + Math.sin(t * b + s * 2.3) * 0.4;
  const lerp3 = (a: number[], b: number[], k2: number) => a.map((v, i) => lerp(v, b[i], k2)) as [number, number, number];
  const pos = lerp3(camA, camB, mB);
  const alvo = lerp3(alvoA, alvoB, mB);
  const dist = Math.hypot(pos[0] - alvo[0], pos[1] - alvo[1], pos[2] - alvo[2]);
  const sc = tr * (0.05 + 0.02 * (dist / 100));
  pos[0] += sh(1, 47, 29) * sc * 1.4; pos[1] += sh(2, 53, 31) * sc;
  alvo[0] += sh(3, 41, 23) * sc * 2.2; alvo[1] += sh(4, 59, 27) * sc * 2.2;
  const fov = lerp(40, 60, mB) - 20 * suave(3.5, 5.9, t);

  return (
    <ThreeCanvas width={1080} height={1920} style={{background: '#87b9e8'}}>
      <Camera pos={pos} alvo={alvo} fov={fov} rolar={rad(sh(5, 33, 21) * tr * 0.5 - mB * 1.2)} />
      <fog attach="fog" args={['#cfe4ef', 700, 2700]} />
      <mesh scale={2800} renderOrder={-10}><sphereGeometry args={[1, 32, 20]} /><shaderMaterial vertexShader={vertCeu} fragmentShader={fragCeu} side={THREE.BackSide} depthWrite={false} fog={false} /></mesh>
      <hemisphereLight args={['#bfe0ff', '#6f7c52', 1.15]} />
      <directionalLight position={[-120, 200, 160]} intensity={3.1} color="#fff1da" />
      <pointLight position={[0, Math.max(5, yb - 4), 0]} intensity={4200} distance={170} decay={1.6} color="#ff9a3c" />
      <Nuvens />
      <Costa t={t} />
      <Plataforma g={g} />
      <Foguete t={t} disp={disp} k={k} g={g} mats={mats} tex42={tex42} tex40={tex40} />
      <Glow pos={[0, yb - 2.5, 0]} r={46 * k + 6} op={0.85} />
      <Fumaca t={t} />
    </ThreeCanvas>
  );
};
