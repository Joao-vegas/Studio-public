#!/usr/bin/env node
// Gera imagem editorial pro slot fixo do template noticia-dividida.
//
// Uso:
//   node gerar-imagem.js "<prompt>" <out.png>

const fs = require('fs');
const {loadEnv} = require('../lib/load-env');

loadEnv();

const [promptUser, outPath] = process.argv.slice(2);

if (!promptUser || !outPath) {
  console.error('Uso: node gerar-imagem.js "<prompt>" <out.png>');
  process.exit(1);
}

const STYLE_PREFIX =
  'editorial photograph, photojournalism style, professional photography, cinematic lighting, depth of field, brazilian business context, ';
const STYLE_SUFFIX =
  ', high detail, magazine cover quality, no text, no readable signs, no logos, no watermark, no date stamp, no timestamp, no phone interface, no emoji stickers, no captions, no posters with writing';

const fullPrompt = `${STYLE_PREFIX}${promptUser}${STYLE_SUFFIX}`;

async function gerarOpenAI() {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY ausente');
  console.error('▶ Gerando imagem (OpenAI gpt-image-1.5)...');
  const model = 'gpt-image-1.5';

  const res = await fetch('https://api.openai.com/v1/images/generations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      prompt: fullPrompt,
      n: 1,
      size: '1536x1024',
      quality: 'high',
    }),
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`OpenAI HTTP ${res.status}: ${txt.slice(0, 200)}`);
  }
  const data = await res.json();
  const b64 = data.data?.[0]?.b64_json;
  if (!b64) throw new Error('OpenAI retornou sem b64_json');
  return {
    buf: Buffer.from(b64, 'base64'),
    meta: {provider: 'openai', model, size: '1536x1024', quality: 'high'},
  };
}

(async () => {
  console.error(`  prompt: ${promptUser.slice(0, 80)}${promptUser.length > 80 ? '...' : ''}`);
  const {buf, meta} = await gerarOpenAI();
  fs.writeFileSync(outPath, buf);
  fs.writeFileSync(
    `${outPath}.meta.json`,
    JSON.stringify(
      {
        ...meta,
        generatedAt: new Date().toISOString(),
        promptUser,
        promptFinal: fullPrompt,
      },
      null,
      2,
    ),
  );
  console.error(`✓ IA usada: ${meta.provider} / ${meta.model}`);
  console.error(`✓ Imagem salva: ${outPath} (${(buf.length / 1024).toFixed(0)}KB)`);
})().catch((e) => {
  console.error('✗', e.message);
  process.exit(1);
});
