// CENA-MODELO EM BRANCO do formato mundo-3d. Copie este arquivo para CenasX-<tema>.tsx, troque o nome e registre
// o componente no CENAS_<grupo> (Registro3D.tsx). Regras que já custaram caro (aprendizado/regras.json):
//  - câmera SEMPRE em movimento (a posição depende do quadro); cena de 3 a 5 s presa à palavra dita;
//  - número/rótulo DENTRO da cena, em plano voltado para a câmera (nunca de lado), com TextoRevelado;
//  - nada importante entre y=1280 e y=1480 (a legenda fica em y=1340); sem logo nem marca.
import React from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Camera, Luzes, Estrelas} from './Cenas3D';
import {TextoRevelado, useTexto} from './CenasB-texto';

export const CenaModelo: React.FC = () => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;                                   // segundos desde o início da cena
  const az = -0.5 - t * 0.25;                          // órbita lenta (a câmera nunca para)
  const num = useTexto(900, 240, (c) => {              // rótulo "42 UNIDADE" pintado em canvas (Anton)
    c.font = '200px Anton'; c.fillStyle = '#fff'; c.textBaseline = 'middle';
    c.fillText('42', 20, 120); return c.measureText('42').width + 40;
  });
  return (
    <ThreeCanvas width={1080} height={1920} shadows style={{background: '#000'}}>
      <Camera pos={[Math.cos(az) * 8, 2.2, Math.sin(az) * 8]} alvo={[0, 0.4, 0]} fov={40} />
      <Luzes azSol={-95} />
      <Estrelas />
      {/* TROQUE: o objeto principal do tema */}
      <mesh position={[0, 0.4, 0]} castShadow>
        <boxGeometry args={[2, 1, 1]} />
        <meshStandardMaterial color="#cfd5dc" metalness={0.4} roughness={0.35} />
      </mesh>
      <TextoRevelado r={num} s={0.006} x={-2.4} y={2.2} z={0} p={Math.min(1, t / 0.6)} />
    </ThreeCanvas>
  );
};
