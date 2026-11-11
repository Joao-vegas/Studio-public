# Como fazer: Crítica ao absurdo

**Quando usar:** você rejeitando um comportamento que as pessoas normalizaram. Em cima, alguém falando o absurdo (entrevista
de rua, podcast, vídeo viral); embaixo, a sua cara reagindo, parada; no fim, a sua resposta. Não é a Tela dividida (lá é
você falando em cima com cenas embaixo).
**Régua:** exemplo-1 (CONTRATO, item 6).
**A tela (1080x1920):** vídeo absurdo em cima, 1080x1046, cortado pra preencher (foco ajustável); FOTO fixa embaixo,
1080x874, a mesma do 1º ao último quadro do trecho. Legenda do trecho com 1 a 3 palavras, Roboto Black 50 px em caixa
roxa (#6D28D9), texto branco e palavra forte em amarelo (#FFE500), centro y=960 (logo acima da divisão). Depois, a
resposta do João em tela cheia, sem legenda.
**Motor:** ffmpeg + PIL no modelo do cliente (`build.py`, chamado pelo `../gerar.sh` de dentro da `_sandbox-<slug>/`).
**Som:** sem música nem efeito; o áudio do trecho e a resposta nivelados (loudnorm -16 LUFS).

## Passo a passo (o mesmo da esteira do formato.json, na mesma ordem)

1. **Trazer o vídeo e a foto.** `work/absurdo.mp4` = o vídeo inteiro (pode ter 3 min; link → yt-dlp na maior
   resolução). Foto: a do briefing em `work/foto.<ext>`, senão a padrão (`assets/foto-padrao.png`, a sua foto reagindo).
   Resposta (opcional): `work/joao.mp4` já cortada.
2. **Escolher o trecho.** O de/até do João, exato. Sem trecho: transcrever, propor 2 ou 3 trechos de 20 a 30 s com o
   absurdo mais claro e parar pro João escolher.
3. **Prévia (para pro João aprovar).** `zsh ../gerar.sh --dir . --de <DE> --ate <ATE> --previa` → `storyboard.jpg`.
   Rosto de quem fala na metade de cima (`--foco-x`, `--foco-y`); vídeo que já tem legenda → `--sem-legenda`.
4. **Renderizar.** O mesmo comando sem `--previa` (`--sem-resposta` = só o trecho). Saída em
   `output/critica-ao-absurdo/<slug>.mp4`. Ao terminar: `andamento.py pronto ... --video <mp4> --pasta <sandbox>`.
   Valores das escolhas da tela: "Sem legenda (o vídeo já tem)" = `--sem-legenda`; "Só o trecho com a foto" = `--sem-resposta`;
   "Vou mandar outra foto" = `work/foto.<ext>` ou `--foto`.
5. **Conferência.** `/watch` e a folha (`formatos.py folha-video`) ao lado da do exemplo: foto parada no mesmo lugar,
   legenda sincronizada e sem dobrar, volume parelho entre o trecho e a resposta.

## Regras

Ficam em `aprendizado/regras.json`. Correção do João vira regra pela REGRA Nº 2 do `CLAUDE.md`.

## Som e cena de apoio

**Música:** não usa (sempre).

**Efeitos:** não usa (sempre).

**Cena de apoio:** não usa (sempre: o vídeo absurdo é o conteúdo; sem b-roll).
