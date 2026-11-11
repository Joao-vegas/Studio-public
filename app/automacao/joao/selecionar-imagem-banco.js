#!/usr/bin/env node
// Seleciona uma imagem do banco de conteudo por proximidade simples de contexto.
//
// Uso:
//   node selecionar-imagem-banco.js <content_dir> "<contexto>" [--min-score 2]
//   node selecionar-imagem-banco.js <content_dir> --listar

const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const contentDir = args[0];
const listar = args.includes('--listar');
const minIdx = args.indexOf('--min-score');
const minScore = minIdx !== -1 ? Number(args[minIdx + 1]) : 2;

if (!contentDir) {
  console.error('Uso: node selecionar-imagem-banco.js <content_dir> "<contexto>" [--min-score 2]');
  process.exit(1);
}

const bancoPath = path.join(contentDir, 'banco-imagens', 'imagens.json');
if (!fs.existsSync(bancoPath)) {
  if (listar) process.exit(0);
  console.log('');
  process.exit(0);
}

const banco = JSON.parse(fs.readFileSync(bancoPath, 'utf8'));
const imagens = banco.imagens || [];

if (listar) {
  for (const img of imagens) {
    const abs = path.join(contentDir, 'banco-imagens', img.arquivo);
    const exists = fs.existsSync(abs);
    console.log(`${img.status || 'sem-status'} ${exists ? 'ok' : 'faltando'} ${img.id} - ${img.nome}`);
  }
  process.exit(0);
}

const contexto = (args[1] || '').toLowerCase();
if (!contexto) {
  console.log('');
  process.exit(0);
}

function scoreImagem(img) {
  if (img.status !== 'ativo') return -1;
  const abs = path.join(contentDir, 'banco-imagens', img.arquivo);
  if (!fs.existsSync(abs)) return -1;

  let score = 0;
  for (const kw of img.palavrasChave || []) {
    if (contexto.includes(String(kw).toLowerCase())) score += 2;
  }

  for (const word of contexto.split(/[^a-z0-9áàâãéêíóôõúç]+/i).filter(Boolean)) {
    if (word.length < 4) continue;
    if ((img.contexto || '').toLowerCase().includes(word)) score += 1;
    if ((img.usarQuando || '').toLowerCase().includes(word)) score += 1;
  }

  return score;
}

const ranked = imagens
  .map((img) => ({img, score: scoreImagem(img)}))
  .sort((a, b) => b.score - a.score);

const best = ranked[0];
if (!best || best.score < minScore) {
  console.log('');
  process.exit(0);
}

console.error(`✓ Banco de imagens: ${best.img.nome} (score ${best.score})`);
console.log(path.join(contentDir, 'banco-imagens', best.img.arquivo));
