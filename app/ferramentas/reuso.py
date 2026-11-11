"""Usar um vídeo pronto em outro formato: cria um job novo do formato escolhido, do mesmo cliente, com uma CÓPIA do mp4
como bruto (o original em output/ fica intacto). Não gera nada pago e não dispara a IA: o job nasce parado e o João
manda montar o storyboard na página dele."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from _comum import clonar as _clonar
import formatos as _fmt
import producao as _prod
import saidas as _s


def opcoes(formato_atual: str = "") -> list[dict]:
    """A escolha curta: os formatos que recebem vídeo gravado (formato.json → entrada), menos o de onde o vídeo veio."""
    return [{"slug": f["slug"], "titulo": f["titulo"], "frase": f.get("frase", ""),
             "legenda": _fmt.legenda_do(f)["desligavel"]}
            for f in _fmt.aceitam_video() if f["slug"] != formato_atual]


def usar(caminho: str, slug: str, titulo_base: str = "") -> dict:
    it = _s.item(caminho)   # a trava de caminho: só o que está em output/ dos clientes
    if not it["video"]:
        raise ValueError("Esse vídeo ainda não tem o arquivo final (.mp4).")
    f = next((x for x in _fmt.aceitam_video() if x["slug"] == slug), None)
    if not f:
        raise ValueError("Esse formato não recebe vídeo gravado.")
    origem = _s._raiz() / it["video"]
    cli, mod = _fmt.usar(slug, it["cliente"])
    nome = (titulo_base or it["slug"]).strip()
    aviso = (f"REAPROVEITADO: o bruto é o vídeo já pronto \"{it['slug']}\" ({it['modelo'] or 'outro formato'}), editado antes. "
             "Pode trazer legenda, manchete ou cena queimadas: confira os quadros antes de pôr texto por cima.")
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / origem.name
        _clonar(origem, copia)   # o criar() move o arquivo que recebe: vai a cópia, nunca o original
        return _prod.criar(cli, mod, copia, f"{nome} (em {f['titulo']})", aviso, formato=slug)
