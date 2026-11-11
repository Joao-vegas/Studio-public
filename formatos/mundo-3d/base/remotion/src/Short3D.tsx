// MUNDO 3D (formato mundo-3d do Estúdio), 1080x1920, 30 fps.
// Cada cena é {"tipo":"3d","cena":"<nome>"} e renderiza REGISTRO_3D[nome] (Registro3D.tsx). Há também "img" (imagem parada com
// câmera andando) para o que não vale modelar. Sem chip de número no canto e sem rodapé: número só na voz, na legenda e DENTRO da
// cena 3D. Legenda palavra por palavra em y=1340. Props vêm do <sandbox>/.dados-props.json montado por short3d.py.
import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, staticFile, useCurrentFrame, Easing} from 'remotion';
import {C, useFontes} from './Comum';
import {REGISTRO_3D} from './Registro3D';

export type Palavra = {t: string; de: number; ate: number};
export type Cena3D = {de: number; ate: number; tipo: 'img' | '3d'; cena?: string; img?: string;
  mov?: 'in' | 'out' | 'esq' | 'dir' | 'sobe' | 'gira'};
export type Short3DProps = {fps: number; total: number; voz: string | null; musica: {src: string; vol: number} | null;
  cenas: Cena3D[]; legendas: Palavra[]};

export const defaultShort3D: Short3DProps = {fps: 30, total: 150, voz: null, musica: null, cenas: [], legendas: []};

const FADE = 8;          // quadros de fusão na entrada de cada cena
const LEGENDA_Y = 1340;  // regra: legenda em y≈1340 (fora do que a cena mostra e da zona do Instagram)

// ---------- Cena de imagem parada com câmera andando ----------
const MOV: Record<string, [number, number, number, number, number, number, number, number]> = {
  // escala ini, fim, x ini, x fim (%), y ini, y fim (%), rot ini, rot fim (graus)
  in: [1.05, 1.22, 0, 0, 0, 0, 0, 0], out: [1.22, 1.05, 0, 0, 0, 0, 0, 0],
  esq: [1.18, 1.18, 4, -4, 0, 0, 0, 0], dir: [1.18, 1.18, -4, 4, 0, 0, 0, 0],
  sobe: [1.15, 1.2, 0, 0, 4, -4, 0, 0], gira: [1.2, 1.28, 0, 0, 0, 0, -3, 3],
};
const CenaImg: React.FC<{c: Cena3D; dur: number}> = ({c, dur}) => {
  const f = useCurrentFrame();
  const m = MOV[c.mov || 'in'];
  const t = interpolate(f, [0, dur], [0, 1], {extrapolateRight: 'clamp', easing: Easing.inOut(Easing.quad)});
  const k = (a: number, b: number) => a + (b - a) * t;
  return (
    <AbsoluteFill style={{backgroundColor: '#000', overflow: 'hidden'}}>
      <Img src={staticFile(c.img!)} style={{width: '100%', height: '100%', objectFit: 'cover',
        transform: `scale(${k(m[0], m[1])}) translate(${k(m[2], m[3])}%, ${k(m[4], m[5])}%) rotate(${k(m[6], m[7])}deg)`}} />
    </AbsoluteFill>
  );
};

// ---------- Legenda palavra por palavra (até 3 palavras por vez; a atual e as ditas em branco pleno) ----------
const grupos = (ls: Palavra[]) => {
  const out: Palavra[][] = []; let cur: Palavra[] = [];
  ls.forEach((w, i) => {
    const ant = ls[i - 1];
    if (cur.length && ant && (cur.length >= 3 || /[.!?,:]$/.test(ant.t) || w.de - ant.ate > 10)) { out.push(cur); cur = []; }
    cur.push(w);
  });
  if (cur.length) out.push(cur);
  return out;
};
const Legenda: React.FC<{ls: Palavra[]}> = ({ls}) => {
  const f = useCurrentFrame();
  const gs = React.useMemo(() => grupos(ls), [ls]);
  const gi = gs.findIndex((g, i) => f >= g[0].de && f < Math.min(gs[i + 1]?.[0].de ?? Infinity, g[g.length - 1].ate + 12));
  if (gi < 0) return null;
  const g = gs[gi];
  return (
    <div style={{position: 'absolute', left: 70, right: 70, top: LEGENDA_Y, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', columnGap: 22}}>
      {g.map((w, i) => (
        <span key={i} style={{fontFamily: 'InterB', fontSize: 74, lineHeight: 1.2, color: C.branco, opacity: w.de <= f ? 1 : 0.35,
          textShadow: '0 4px 0 rgba(0,0,0,0.9), 0 8px 28px rgba(0,0,0,0.9)'}}>{w.t}</span>
      ))}
    </div>
  );
};

export const Short3D: React.FC<Short3DProps> = (p) => {
  useFontes();
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {p.cenas.map((c, i) => {
        const dur = c.ate - c.de + FADE;
        return (
          <Sequence key={i} from={c.de} durationInFrames={dur}>
            <AbsoluteFill style={{opacity: interpolate(f - c.de, [0, FADE], [i === 0 ? 1 : 0, 1], {extrapolateRight: 'clamp'})}}>
              {c.tipo === 'img' && <CenaImg c={c} dur={dur} />}
              {c.tipo === '3d' && (() => { const Z = REGISTRO_3D[c.cena || '']; return Z ? <Z /> : null; })()}
            </AbsoluteFill>
          </Sequence>
        );
      })}
      <Legenda ls={p.legendas} />
      {p.voz && <Audio src={staticFile(p.voz)} />}
      {p.musica && <Audio src={staticFile(p.musica.src)} volume={p.musica.vol} />}
    </AbsoluteFill>
  );
};
