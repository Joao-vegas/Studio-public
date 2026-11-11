# Clientes

Cada cliente é uma pasta aqui dentro, com a identidade visual e os modelos de vídeo dele:

```
clientes/<Nome>/
  identidade.json              cores, papéis das cores, fontes e palavras do cliente (o mesmo formato do Avulso)
  <nome>Content/
    modelos/<estilo>/          o modelo de cada estilo: scripts, aprendizado/regras.json, ficha.json, README.md
    output/                    os vídeos prontos (fora do git)
```

**`clientes/Avulso` vem pronto**: é um cliente neutro, sem marca, com todos os modelos (tela dividida, chamada na tela,
documentário, editorial, explicador 3D, faixa com cenas, caixinha de perguntas e outros). Use-o direto ou copie a pasta
com o nome do seu cliente e troque o `identidade.json`.

Pelo app (http://localhost:7655) também dá para criar um cliente novo: ele monta a pasta e porta os modelos que você escolher.

O `.gitignore` deste repositório não sobe nenhum cliente além do Avulso: as pastas dos seus clientes ficam só no seu Mac.
