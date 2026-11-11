// Peças comuns do formato mundo-3d: paleta, fontes e a curva de entrada. Troque a paleta por tema/cliente.
import {useEffect, useState} from 'react';
import {continueRender, delayRender, spring, staticFile} from 'remotion';

export const C = {vermelho: '#E21212', branco: '#FFFFFF', preto: '#0C0C0E', amarelo: '#FFD600', navy: '#090F1C', cinza: '#B9C0CC'};
const FONTES: [string, string][] = [['Anton', 'fontes/Anton-Regular.ttf'], ['InterB', 'fontes/Inter-Bold.otf']];

export const useFontes = () => {
  const [h] = useState(() => delayRender('fontes'));
  useEffect(() => {
    Promise.all(FONTES.map(([n, u]) => new FontFace(n, `url(${staticFile(u)})`).load().then((f) => { document.fonts.add(f); })))
      .then(() => continueRender(h)).catch(() => continueRender(h));
  }, [h]);
};

export const entra = (f: number, fps: number, atraso = 0) => spring({frame: f - atraso, fps, config: {damping: 200}, durationInFrames: 18});
