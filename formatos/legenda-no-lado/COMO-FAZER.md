# Como fazer: Legenda no lado

**Quando usar:** vídeo gravado de lado dentro do carro (horizontal 16:9) em que a pessoa fala sem parar e o bruto tem pausa, falso começo e o volante aparecendo.
**Régua:** o reel de referência DfPYxlRx4Lv (carro, pessoa de um lado, 2 a 3 palavras em maiúscula do outro, sem caixa) e o 1º vídeo do formato, `clientes/Joao/vegasContent/output/legenda-no-lado/carro-0411.mp4` (CONTRATO, item 6).
**Motor:** vídeo gravado, `lado.py` do modelo: ffmpeg decodifica só os quadros mantidos, Python (PIL) desenha a legenda, ffmpeg codifica (libx264 crf 18).
**Som:** só a voz do João, nivelada em -14 LUFS (afftdn leve tira o ruído de estrada). Sem música nem efeito.

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Preparar a entrada.** `app/.venv/bin/python app/ferramentas/corte.py transcrever <bruto> <sandbox>/work --cliente <Nome> --groq`; depois `python3 ../legenda.py --dir . --inicio S --fim S [--corrige correcoes.json]` monta `work/legenda.json`. Leia a frase inteira: o Whisper erra verbo, nome e a ordem de palavras curtas. Bruto linkado em `work/joao.mp4`.
2. **Cortar silêncio e começo errado.** O `lado.py` mede a energia (piso do ruído + 3 dB) e tira pausa de 0,26 s ou mais; o falso começo sai por `--inicio`, o fim sem frase por `--fim` (G23). Confira o `work/plano.json`: pausas, trechos e duração final.
3. **Storyboard (para pro João aprovar).** `zsh ../gerar.sh --dir . --quadro 6` grava `storyboard.jpg`: volante fora, pessoa à esquerda, texto do lado direito, rosto livre.
4. **Vídeo.** `zsh ../gerar.sh --dir .` (~1 min para 45 s em 4K). `--sem-legenda` desliga o texto.
5. **Conferência.** `python3 app/ferramentas/conferir_video.py <mp4> --sandbox <sandbox> --formato legenda-no-lado` + folha de quadros (1 a cada 3 s) + transcrever o vídeo final e comparar com a legenda (média dentro de 0,05 s).

## Regras

Ficam em `aprendizado/regras.json`. Correção do João vira regra pela REGRA Nº 2 do `CLAUDE.md`.

## Som e cena de apoio

**Música:** não usa (sempre). **Efeitos:** não usa (sempre). **Cena de apoio:** não usa (sempre): o corte seco e a palavra dourada seguram o ritmo.
