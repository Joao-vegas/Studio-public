// Texto desenhado DENTRO da cena 3D (plano com textura de canvas, fonte Anton do projeto). Grupo B, S001.
import React, {useEffect, useState} from 'react';
import * as THREE from 'three';
import {continueRender, delayRender} from 'remotion';

const fontePronta = () => typeof document !== 'undefined' &&
  Array.from(document.fonts).some((f) => f.family.replace(/["']/g, '') === 'Anton' && f.status === 'loaded');

export type TextoPronto = {tex: THREE.CanvasTexture; cw: number; ch: number; larg: number};

// desenha(ctx) pinta no canvas cw x ch e devolve a largura em pixels ocupada pelo texto (para dimensionar no mundo).
export const useTexto = (cw: number, ch: number, desenha: (c: CanvasRenderingContext2D) => number): TextoPronto | null => {
  const [r, setR] = useState<TextoPronto | null>(null);
  const [h] = useState(() => delayRender('texto-3d'));
  useEffect(() => {
    let n = 0, vivo = true;
    const tick = () => {
      if (!vivo) return;
      if (fontePronta() || n++ > 80) {
        const cv = document.createElement('canvas'); cv.width = cw; cv.height = ch;
        const larg = desenha(cv.getContext('2d')!);
        const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
        setR({tex, cw, ch, larg});
        setTimeout(() => continueRender(h), 60);
      } else setTimeout(tick, 50);
    };
    tick();
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return r;
};

// Plano com o texto, revelado da esquerda para a direita (p = 0..1). s = unidades de mundo por pixel do canvas.
// x = borda esquerda do plano (o texto começa ~pad px depois), y = centro vertical, z = profundidade.
export const TextoRevelado: React.FC<{r: TextoPronto | null; s: number; x: number; y: number; z?: number; p: number; opacidade?: number}> = ({r, s, x, y, z = 0, p, opacidade = 1}) => {
  if (!r || p <= 0.002) return null;
  r.tex.repeat.set(Math.min(1, p), 1); r.tex.offset.set(0, 0);
  const w = Math.min(1, p) * r.cw * s;
  return (
    <mesh position={[x + w / 2, y, z]} scale={[w, r.ch * s, 1]} renderOrder={10}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={r.tex} transparent opacity={opacidade} toneMapped={false} depthWrite={false} />
    </mesh>
  );
};
