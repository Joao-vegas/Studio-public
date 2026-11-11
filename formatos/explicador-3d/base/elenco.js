// Explicador 3D · biblioteca de ELENCO: gente variada (profissão, idade, corpo, pele) com rosto em código "feio esquisito".
// No cenas.json/decupagem: "elenco": {"dono": "comerciante"} (pega daqui) ou {"dono": {"base": "comerciante", "camisa": {...}}} (troca o
// figurino). Os campos são os do gente.js. Protagonista do roteiro sai daqui também (dentista, advogado, corretor...).
export const ELENCO = {
  dentista:    { pele: '#dcaa86', cabelo: { estilo: 'topete', cor: '#3a2416' }, olhos: 'verde', camisa: { tipo: 'jaleco', cor: '#eef2f5', cor2: '#2ec4b6' }, calca: { cor: '#26303f' }, sapato: '#1d1f27', semente: 11 },
  medica:      { pele: '#c98f68', mulher: true, cabelo: { estilo: 'rabo', cor: '#2a1a10' }, camisa: { tipo: 'jaleco', cor: '#f2f4f6', cor2: '#d04a6a' }, calca: { cor: '#3a3f52' }, semente: 21 },
  paciente:    { pele: '#9a5f3c', mulher: true, cabelo: { estilo: 'cacheado', cor: '#1a120c' }, camisa: { cor: '#e8b23a', manga: 'curta', estampa: 'florida' }, calca: { tipo: 'saia', cor: '#5a3a8a' }, sapato: '#a8322a', semente: 4 },
  aposentado:  { pele: '#c98f68', idade: 'velho', corpo: 'gordo', cabelo: { estilo: 'careca', cor: '#8a7a6a' }, bigode: true, camisa: { cor: '#4a8a52', manga: 'curta', estampa: 'xadrez' }, calca: { cor: '#6b5a45' }, semente: 3 },
  vovo:        { pele: '#f0cdb2', mulher: true, idade: 'velho', cabelo: { estilo: 'coque', cor: '#cfcfcf' }, oculos: true, camisa: { cor: '#c8507a' }, calca: { tipo: 'saia', cor: '#2c3e50' }, sapato: '#6b4a33', semente: 9 },
  estudante:   { pele: '#e8b896', cabelo: { estilo: 'espetado', cor: '#c99a3a' }, olhos: 'azul', camisa: { cor: '#2e8fb8', tipo: 'moletom' }, calca: { cor: '#3a3f46' }, sapato: '#e8e8e8', semente: 7 },
  executivo:   { pele: '#6e4429', cabelo: { estilo: 'curto', cor: '#111111' }, camisa: { tipo: 'terno', cor: '#22252e', gravata: '#b4232c' }, calca: { cor: '#22252e' }, barba: 'curta', semente: 8 },
  comerciante: { pele: '#d9a37e', corpo: 'gordo', cabelo: { estilo: 'curto', cor: '#3a2618' }, bigode: true, camisa: { cor: '#f2efe6', manga: 'curta' }, calca: { cor: '#4a4030' }, semente: 13 },
  vendedora:   { pele: '#b8784e', mulher: true, cabelo: { estilo: 'longo', cor: '#3a1a10' }, camisa: { cor: '#d0303a', gola: true }, calca: { cor: '#1f2533' }, semente: 15 },
  motoboy:     { pele: '#8a5a3a', corpo: 'magro', cabelo: { estilo: 'curto', cor: '#111' }, bone: '#1f6fb0', camisa: { cor: '#f0c020', tipo: 'moletom' }, calca: { cor: '#2a3a5a' }, sapato: '#222', semente: 17 },
  pedreiro:    { pele: '#a8693e', corpo: 'forte', cabelo: { estilo: 'curto', cor: '#2a1a10' }, camisa: { cor: '#e07a2a', manga: 'curta' }, calca: { cor: '#5a6a7a' }, barba: 'cheia', semente: 19 },
  garcom:      { pele: '#e0b090', corpo: 'magro', cabelo: { estilo: 'franja', cor: '#1a1a1a' }, camisa: { tipo: 'terno', cor: '#b3202c', gravata: '#151515', cor3: '#f2f2f2' }, calca: { cor: '#151515' }, semente: 23 },
  gerente:     { pele: '#f0c8a8', mulher: true, cabelo: { estilo: 'franja', cor: '#d8b060' }, camisa: { tipo: 'terno', cor: '#3a4a6a', cor3: '#f2f2f2' }, calca: { tipo: 'saia', cor: '#3a4a6a' }, oculos: true, semente: 25 },
  influencer:  { pele: '#e8b896', cabelo: { estilo: 'topete', cor: '#d8c060' }, camisa: { cor: '#ff5ab0', estampa: 'florida', manga: 'curta' }, calca: { tipo: 'bermuda', cor: '#3a8ab0' }, oculos: 'escuro', semente: 27 },
  policial:    { pele: '#7a4a2a', corpo: 'forte', cabelo: { estilo: 'careca', cor: '#111' }, bone: '#1a2a4a', camisa: { cor: '#2a3a5a', gola: true }, calca: { cor: '#1a2a4a' }, semente: 29 },
  agricultor:  { pele: '#b07850', idade: 'velho', corpo: 'magro', cabelo: { estilo: 'curto', cor: '#9a9a9a' }, bone: '#c8a040', camisa: { cor: '#7a6a4a', estampa: 'xadrez' }, calca: { cor: '#3a4a6a' }, barba: 'curta', semente: 31 },
  menina:      { pele: '#c68a62', mulher: true, cabelo: { estilo: 'rabo', cor: '#3a2618' }, camisa: { cor: '#b8323a', manga: 'curta' }, calca: { cor: '#3b5b8c' }, sapato: '#e8e8e8', semente: 5 },
};
export function resolverElenco(el) {   // "nome" | {base, ...troca} | {campos completos}
  const out = {};
  for (const [id, v] of Object.entries(el || {})) {
    if (typeof v === 'string') { if (!ELENCO[v]) throw new Error(`elenco "${v}" não existe. Opções: ${Object.keys(ELENCO).join(', ')}`); out[id] = { ...ELENCO[v] }; }
    else if (v && v.base) { if (!ELENCO[v.base]) throw new Error(`elenco "${v.base}" não existe`); const { base, ...r } = v; out[id] = { ...ELENCO[base], ...r }; }
    else out[id] = { ...v };
  }
  return out;
}
