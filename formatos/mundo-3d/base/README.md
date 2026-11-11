# Motor do Mundo 3D (Remotion + three.js)

Voz → tempo de cada palavra → `short3d.json` → cenas 3D → render. Quem junta tudo é o `short3d.py`; as cenas são componentes React em `remotion/src/`.

## Como rodar

- **Primeira vez:** as bibliotecas (`remotion/node_modules`, ~340 MB) NÃO ficam no catálogo. O `short3d.py` roda `npm install` sozinho na primeira execução (alguns minutos); ou faça à mão: `cd remotion && npm install`.
- **Pasta do vídeo (sandbox):** `short3d.json` (cenas em segundos), `audio/voz.wav` (a narração) e, se já tiver, `audio/palavras.json`. Sem `palavras.json` o whisper do Mac gera sozinho; idioma pela variável `MOTION_LINGUA` (padrão `en`; `pt` para português).
- **Storyboard (um quadro por cena):** `python3 base/short3d.py <pasta> --json short3d.json`
- **Um quadro só, para conferir UMA cena:** `python3 base/short3d.py <pasta> --json short3d.json --still 12.5` (sai `qa/still-012.5.jpg`; abra a imagem).
- **Render final:** `python3 base/short3d.py <pasta> --json short3d.json --final --saida short-final.mp4` (1080x1920, 30 fps, loudnorm -14 LUFS). `--ate S` renderiza só até o segundo S.
- **Um único render por vez.** Stills de grupos diferentes podem rodar em paralelo.
- Stills usam `--gl=angle`. Exemplo completo: `exemplo-s001/` (`short3d.json`, `palavras.json`, `roteiro.md`).

## short3d.json

```json
{"musica": null, "musica_vol": 0.09,
 "cenas": [{"de": 0.0, "tipo": "3d", "cena": "espaco"},
           {"de": 3.0, "tipo": "img", "img": "img/x.jpg", "mov": "in"}]}
```

O `de` é o início da palavra dita (veja `palavras.json`); o fim de uma cena é o início da seguinte. Um json por grupo de cenas (`--json outro.json`): cada um usa só as cenas dele.

## Acrescentar uma peça nova

1. Copie `remotion/src/CenaModelo.tsx` para `CenasE-<tema>.tsx` (um arquivo por grupo de cenas) e troque o nome do componente e o objeto.
2. Exporte um mapa `CENAS_E = {nome_da_peca: Componente}` e registre-o em `remotion/src/Registro3D.tsx` (só soma os grupos).
3. Use `"cena": "nome_da_peca"` no `short3d.json` e confira com `--still`.

Peças compartilhadas (`Cenas3D.tsx`, `Comum.tsx`, `CenasB-texto.tsx`) são só lidas pelos outros grupos: não edite sem avisar.

## Peças que já existem (nome exato no json)

| Nome | Arquivo | Tipo |
|---|---|---|
| `espaco` | Cenas3D | Exemplo Roadster: trocar o objeto e o planeta |
| `volante` | Cenas3D | Exemplo Roadster: trocar o objeto |
| `afastar` | CenasB | Genérica: muda a distância e o texto |
| `lateral` | CenasB | Exemplo Roadster: trocar o objeto |
| `foguete` | CenasB-foguete | Exemplo Roadster: só em assunto com lançamento |
| `carro_xray` | Cenas3D | Exemplo Roadster: trocar o objeto e a medida |
| `starman_close` | Cenas3D | Exemplo Roadster: trocar o personagem |
| `orbita` | CenasC | Genérica: órbitas, rótulos e contador (tem planetas do exemplo) |
| `mergulho` | CenasC | Genérica: origem e destino |
| `patios_2018`, `patios_2025` | CenasD | Exemplo Roadster: comparação A × B; trocar unidade e valores |
| `patios_pergunta` | CenasD | Genérica: interrogação 3D com o texto do rótulo |
| `final_espaco` | Cenas3D | Exemplo Roadster: trocar o objeto |
| `modelo` | CenaModelo | Genérica: cena em branco para copiar |

As regras que já custaram caro estão em `../aprendizado/regras.json`.
