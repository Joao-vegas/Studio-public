"""Caixinha de perguntas (e Frase fixa, que usa o mesmo camada.json): o texto é uma CAMADA por cima do vídeo limpo.
A verdade é o camada.json (o que está no vídeo, não o comando.sh, que pode estar velho); o render é `camada.py renderizar <pasta>`.

Cenas: trechos da fala (work/words.json, cortando em pausa ou fim de frase, 3 a 8 s). Elementos do vídeo todo: a pergunta, o título
de cima e a altura (Caixinha); a frase, a altura e o tamanho (Frase fixa). Por cena (só Caixinha): o zoom (punch): "sim" ou "nao";
as cenas sem zoom viram camada.json → punch_livres (os trechos onde o quadro pode aproximar; ausente = o vídeo todo, como sempre).
"""
from __future__ import annotations

import sys
from pathlib import Path

from _comum import RAIZ, ler_json, gravar_json

from . import _base

CAMADA = RAIZ / "app" / "ferramentas" / "camada.py"
TAIL = 0.3   # o camada.py acrescenta 0,3 s de silêncio no fim


def _c(p: Path) -> dict:
    return ler_json(Path(p) / "camada.json", {}) or {}


def _caixinha(p: Path) -> bool:
    return _c(p).get("tipo") == "caixinha"


def _video(p: Path) -> Path:
    return RAIZ / (_c(p).get("video") or "work/joao.mp4")


def _saida(p: Path) -> Path:
    s = _c(p).get("saida")
    return RAIZ / s if s else _base.saida_padrao(Path(p))


def _precisa(p: Path) -> list[str]:
    return [str(_video(p))]


def _palavras_rel(p: Path) -> str:
    return next((r for r in ("work/words.json", "work/cortado/words.json") if (Path(p) / r).is_file()), "")


def _zoom(c: dict, de: float, ate: float) -> str:
    livres = c.get("punch_livres")
    if livres is None:
        return "sim"
    return "sim" if any(float(a) < ate - .05 and float(b) > de + .05 for a, b in livres) else "nao"


def _ler(p: Path) -> dict:
    c = _c(p)
    dur = _base.duracao_video(_video(p))
    cortes = _base.trechos_da_fala(_base.palavras(Path(p) / _palavras_rel(p)) if _palavras_rel(p) else [], dur)
    fim = lambda i: cortes[i + 1] if i + 1 < len(cortes) else dur
    cx = _caixinha(p)
    cenas = [{"de": t, "tipo": "fala", **({"zoom": _zoom(c, t, fim(i))} if cx else {})} for i, t in enumerate(cortes)]
    doc = {"titulo": str(c.get("texto") or Path(p).name)[:80], "saida": str(_saida(p)), "duracao": round(dur + TAIL, 3), "cenas": cenas}
    if _palavras_rel(p):
        doc["palavras"] = _palavras_rel(p)
    if cx:
        doc.update(pergunta=c.get("texto", ""), titulo_caixa=c.get("titulo", ""), y=c.get("y", 255))
    else:
        doc.update(frase=c.get("texto", ""), y=c.get("y", 1430), tamanho=c.get("tamanho", 60))
    return doc


def _gravar(p: Path, doc: dict) -> None:
    import camada
    c = _c(p)
    novo = dict(c)
    if _caixinha(p):
        novo.update(texto=doc.get("pergunta", c.get("texto", "")), titulo=doc.get("titulo_caixa", c.get("titulo", "")), y=doc.get("y", c.get("y")))
    else:
        novo.update(texto=doc.get("frase", c.get("texto", "")), y=doc.get("y", c.get("y")), tamanho=doc.get("tamanho", c.get("tamanho")))
    novo.update(camada.limpar(novo))   # nada fora dos limites chega no desenho
    if _caixinha(p):
        cs = doc.get("cenas") or []
        dur = float(doc.get("duracao") or 0) - TAIL
        janelas = []
        for i, x in enumerate(cs):
            if x.get("zoom", "sim") != "nao":
                de, ate = float(x["de"]), float(cs[i + 1]["de"]) if i + 1 < len(cs) else dur
                if janelas and abs(janelas[-1][1] - de) < 1e-6:
                    janelas[-1][1] = ate
                else:
                    janelas.append([de, ate])
        if len(janelas) == 1 and janelas[0][0] <= 1e-6 and abs(janelas[0][1] - dur) < .05:
            novo.pop("punch_livres", None)   # o vídeo todo com zoom é o padrão: sem a chave
        else:
            novo["punch_livres"] = [[round(a, 3), round(b, 3)] for a, b in janelas]
    if novo != c:
        gravar_json(Path(p) / "camada.json", novo)


def _cmd(p: Path):
    return [sys.executable, str(CAMADA), "renderizar", str(p)], RAIZ


_COMUM = {"gravado": True, "fonte": "camada.json", "arquivos": ["camada.json"], "precisa": _precisa, "ler": _ler, "gravar": _gravar,
          "cmd": _cmd, "saida": _saida, "tempo_fixo": True, "etapas": ["video"], "narracao": False, "material": False,
          "nao_rodar": "camada.py e gerar.sh", "tipos": {"fala": "Você falando"}, "tipo_padrao": "fala",
          "motivo_narracao": "Neste formato a voz é o João gravado: a fala só muda trocando o bruto (a câmera cortada).",
          "onde": ("O vídeo é o João falando, já cortado (work/joao.mp4), com uma caixa de texto fixa por cima, queimada pelo camada.py "
                   "a partir do camada.json. Você NÃO mexe no camada.json nem no vídeo: edite só {arq_ia}, a lista de cenas e os campos "
                   "do topo (cada cena é um trecho da fala, com \"de\" = segundo em que começa; ela termina onde a próxima começa)."),
          "conferir": ("Você não precisa renderizar: o Estúdio refaz o vídeo depois. A caixa é a mesma do vídeo (camada.py); o que vale é o "
                       "texto e a altura que você puser no arquivo.")}

# Caixinha de perguntas: pergunta, título e altura valem pro vídeo todo; o zoom é por cena
CAIXINHA = {**_COMUM,
            "rotulos": {"pergunta": "Pergunta", "titulo_caixa": "Título de cima", "y": "Altura da caixa", "zoom": "Zoom da cena"},
            "globais": {"pergunta": ["pergunta"], "titulo_caixa": ["titulo_caixa"], "y": ["y"]},
            "juntos": {}, "sempre": ("zoom",),
            "sugestoes": ["Troca a pergunta", "Muda o título de cima", "Desce a caixa um pouco", "Tira o zoom desta cena"],
            "dicas": ("Campos do topo do arquivo: \"pergunta\" (o texto da caixa, até 400 caracteres, a pergunta que o seguidor fez; ela tem de "
                      "casar com o que o João responde), \"titulo_caixa\" (a faixa escura de cima, ex.: \"O que você quer saber?\") e \"y\" "
                      "(altura da caixa em pixels de 200 a 1720; 255 = em cima, perto de 1000 = no peito). Em cada cena, \"zoom\" é \"sim\" ou "
                      "\"nao\": se o quadro pode aproximar um pouco (punch) enquanto a cena passa. Não mexa em \"palavras\" nem no \"de\".")}

# Frase fixa: a frase, a altura e o tamanho valem pro vídeo todo; as cenas só marcam o tempo
FRASE_FIXA = {**_COMUM, "achar": lambda p: bool(_c(p)) and not _caixinha(p),
              "rotulos": {"frase": "Frase", "y": "Altura da caixa", "tamanho": "Tamanho da letra"},
              "globais": {"frase": ["frase"], "y": ["y"], "tamanho": ["tamanho"]},
              "juntos": {}, "sempre": (),
              "sugestoes": ["Troca a frase", "Sobe a caixa um pouco", "Aumenta a letra"],
              "dicas": ("Campos do topo do arquivo: \"frase\" (o texto da caixa, até 400 caracteres), \"y\" (altura do centro da caixa de 200 a "
                        "1720, 1430 = no peito) e \"tamanho\" (da letra, de 28 a 140). Não mexa em \"palavras\" nem no \"de\".")}

SPECS = {"caixinha-de-perguntas": CAIXINHA, "frase-fixa": FRASE_FIXA}
CAIXINHA["achar"] = lambda p: _caixinha(p)
