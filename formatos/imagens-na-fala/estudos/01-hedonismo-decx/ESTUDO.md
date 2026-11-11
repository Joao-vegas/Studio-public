# A tragédia do Hedonismo (@felipemustafanunes), a régua do formato

Reel DecxbwzBRru, 49,4 s, 1080x1920 a 30 fps. Pessoa em tela cheia, título fixo amarelo, legenda pequena e 3 cartões de gravura antiga na tela por vez.

Números dos 25 cartões, do título e da legenda: tabela em `COMO-FAZER.md` (raiz do formato). Os dados crus estão aqui: `cartoes.json` (entra, sai, duração e caixa em % de cada cartão), `eventos.json` (quadro de cada corte por posição), `grade-slots.jpg` (grade de 10% sobre 4 quadros), `COMPARACAO-generica-r1.md` (a régua genérica do estudo_quadros contra o render r1; as linhas de plano e câmera não se aplicam a este estilo, que não corta a pessoa).

Reproduzir a medida em qualquer vídeo: `app/.venv/bin/python clientes/Joao/vegasContent/modelos/imagens-na-fala/medir_cartoes.py <video> --saida <pasta>` (acha 25 cartões, 30,4 por minuto, mediana 4,62 s nesta referência).

Números quadro a quadro (planos, câmera, som, fala): `estudo-quadros/ESTUDO-QUADROS.md`.
