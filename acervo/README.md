# acervo — biblioteca compartilhada (b-roll, música, efeito)

- `acervo/itens/<slug>/` — um item: `clip.mp4|png|mp3`, `thumb.jpg`, `meta.json` (título, tags, fonte, autor,
  licença/evidência, checklist de verificação, usos por cliente/modelo/job).
- `acervo/busca/` — projeto da skill **get-brolls** usado pela busca do Estúdio (ledger, candidatos,
  prévias, clipes). Cache: pode ser apagado; o que importa já foi copiado pro `acervo/itens/`.
- `acervo/indice.json` — índice da busca pelo sentido (semantica.py).

Alimentar: pelo Estúdio (aba Acervo / Biblioteca) ou `python3 app/ferramentas/acervo.py add|url|list`.
Música e efeito: `app/ferramentas/musica_busca.py` (do cliente → acervo → Mixkit/SoundCloud/Jamendo; Freesound só efeito).
Os `.mp4` não vão pro git (gitignore global); `meta.json` e `thumb.jpg` vão.
