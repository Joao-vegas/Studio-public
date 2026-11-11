# Motor do formato (nasce do _modelo)

TROQUE: o que cada tipo de cena deste formato desenha e os campos que ele lê do `cenas.json`.

- **Já funciona:** o `render.py` é o motor genérico do Estúdio (o genérico do motor do Documentário). Ele serve a
  pasta, abre o `index.html` no Playwright, chama `seek(t)` quadro a quadro e junta com ffmpeg, com o som.
  O formato troca o **visual** no `index.html` e põe as medidas dele em `checar()` do `render.py`.
- **Teste na hora:** `python3 render.py --storyboard --cenas cenas-modelo.json` (storyboard.jpg) e
  `python3 render.py --cenas cenas-modelo.json --ate 2` (teste.mp4).
- **Comandos que o Estúdio usa** (sem `esteira.comandos` valem estes): `render.py --storyboard --cenas cenas.json`,
  `render.py --cenas cenas.json`, `render.py --conferir --cenas cenas.json` (folha lado a lado com o exemplo
  principal em `qa/folha-comparacao.jpg`), `render.py --quadro 5.2 --cenas cenas.json`.
- O motor é do formato: conserto aqui chega sozinho na cópia do cliente e na sandbox. Nunca edite o motor pra um
  vídeo: o ajuste é no `cenas.json`. Vídeo gravado não tem `base/` (a base é o modelo do cliente).

## cenas.json

```json
{"saida": "video.mp4", "largura": 1080, "altura": 1920, "fps": 30,
 "voz": "work/voz.mp3", "duracao": 30,
 "musica": {"arquivo": "audio/musica.mp3", "volume": 0.12, "inicio_s": 0},
 "efeitos": [{"t": 2.0, "arquivo": "audio/sfx/whoosh.mp3", "volume": 0.3}],
 "cenas": [{"tipo": "frase", "de": 0, "texto": "Na tela", "fala": "o que a pessoa fala", "imagem": "fotos/x.jpg"}]}
```

Cada cena vai do `de` dela até o `de` da próxima (ou `ate`); a última, até a voz ou `duracao`. `imagem` e `video`
viram endereço que a página abre. Sem `voz`, `musica` e `efeitos` o vídeo sai mudo.
