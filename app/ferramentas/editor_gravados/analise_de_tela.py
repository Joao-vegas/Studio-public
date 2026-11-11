"""Análise de tela: em cima a gravação de tela (work/tela.mp4), embaixo o João falando (work/joao.mp4, segue o rosto) e a frase fixa nas
faixas branca e vermelha o vídeo inteiro. O render é o gerar.sh do modelo:
    zsh ../gerar.sh --dir . --titulo "<FRASE>" [--tela-modo cover|fit] [--tela-x 0..1] [--tela-zoom Z] [--tela-atraso S] [--corte Y] ...

A verdade é o comando.sh que a esteira grava (a linha do gerar.sh). O editor lê os flags de lá e, ao editar, reescreve só essa linha:
o que ele não conhece (--faixa-ate, --legenda, --sobre, --trocas...) fica como estava.
Cenas: trechos da fala (words.json). Elementos do vídeo todo: a frase da faixa, o enquadramento da tela, a emenda (corte) e a câmera.
Vídeo montado à mão (montar.sh/montar.py por vídeo) não passa por aqui: cai no modo livre.
"""
from __future__ import annotations

from pathlib import Path

from . import _base

BOOL = ("--previa", "--rosto-fixo")
# doc → flag (e o padrão do gerar.sh, pra mostrar o valor de hoje mesmo quando o comando não diz)
CAMPOS = {"frase": ("--titulo", ""), "tela_modo": ("--tela-modo", "cover"), "tela_x": ("--tela-x", 0.5), "tela_zoom": ("--tela-zoom", 1.0),
          "tela_atraso": ("--tela-atraso", 0.0), "corte": ("--corte", 960), "cam_zoom": ("--cam-zoom", 1.0), "cam_y": ("--cam-y", 0.3)}


def _comando(p: Path) -> dict | None:
    f = Path(p) / "comando.sh"
    return _base.ler_comando(f.read_text(encoding="utf-8", errors="ignore"), BOOL) if f.is_file() else None


def _num(v, padrao):
    try:
        x = float(v)
        return int(x) if isinstance(padrao, int) and x == int(x) else x
    except (TypeError, ValueError):
        return padrao


def _palavras_rel(p: Path) -> str:
    return next((r for r in ("work/words.json", "work/legenda/words.json") if (Path(p) / r).is_file()), "")


def _ler(p: Path) -> dict:
    p = Path(p)
    cm = _comando(p)
    fl = cm["flags"] if cm else {}
    dur = _base.duracao_video(p / "work" / "joao.mp4")
    ate = _num(fl.get("--ate"), None)
    atraso = _num(fl.get("--tela-atraso"), 0.0)
    if atraso and atraso > 0:
        dur -= atraso
    if ate:
        dur = min(dur, ate) + .35
    pal = _palavras_rel(p)
    cortes = _base.trechos_da_fala(_base.palavras(p / pal) if pal else [], dur)
    doc = {"titulo": str(fl.get("--titulo") or p.name).replace("|", " ").capitalize()[:80], "saida": str(_base.saida_padrao(p)),
           "duracao": round(dur, 3), "cenas": [{"de": t, "tipo": "dividido"} for t in cortes],
           "rosto_fixo": "--rosto-fixo" in fl}
    for k, (flag, padrao) in CAMPOS.items():
        v = fl.get(flag)
        doc[k] = str(v) if k in ("frase", "tela_modo") and v is not None else (padrao if v is None else _num(v, padrao))
    if pal:
        doc["palavras"] = pal
    return doc


def _gravar(p: Path, doc: dict) -> None:
    p = Path(p)
    cm = _comando(p)
    if not cm:
        raise ValueError("Sem comando.sh com o gerar.sh: não sei refazer este vídeo.")
    atual = _ler(p)
    if all(doc.get(k) == atual.get(k) for k in (*CAMPOS, "rosto_fixo")):
        return   # nada mudou: o comando.sh fica como a esteira gravou
    if doc.get("tela_modo") not in ("cover", "fit"):
        raise ValueError("tela_modo: cover ou fit.")
    fl = dict(cm["flags"])
    for k, (flag, padrao) in CAMPOS.items():
        if doc.get(k) != atual.get(k):
            fl[flag] = doc[k]
    if doc.get("rosto_fixo"):
        fl["--rosto-fixo"] = True
    else:
        fl.pop("--rosto-fixo", None)
    _base.escrever_comando(p / "comando.sh", cm, fl)


def _cmd(p: Path):
    p = Path(p)
    cm = _comando(p)
    if not cm or not (p.parent / "gerar.sh").is_file() or not (cm["flags"].get("--titulo")):
        return None
    fl = {k: v for k, v in cm["flags"].items() if k not in ("--previa", "--dir", "--saida")}
    return _base.montar_comando({"--dir": ".", **fl, "--saida": str(_base.saida_padrao(p))}, "zsh", "../gerar.sh"), p


SPEC = {
    "gravado": True, "fonte": "comando.sh", "arquivos": ["comando.sh"], "precisa": ["work/joao.mp4", "work/tela.mp4"],
    "achar": lambda p: _cmd(p) is not None and (Path(p) / "work" / "tela.mp4").is_file(),
    "ler": _ler, "gravar": _gravar, "cmd": _cmd, "saida": _base.saida_padrao, "tempo_fixo": True, "timeout": 3600,
    "rotulos": {"frase": "Frase da faixa", "tela": "Enquadramento da tela", "corte": "Altura da emenda", "camera": "Câmera do João"},
    "globais": {"frase": ["frase"], "tela": ["tela_modo", "tela_x", "tela_zoom", "tela_atraso"], "corte": ["corte"],
                "camera": ["cam_zoom", "cam_y", "rosto_fixo"]},
    "tipos": {"dividido": "Tela em cima, João embaixo"}, "tipo_padrao": "dividido", "juntos": {}, "sempre": (),
    "sugestoes": ["Troca a frase da faixa", "Mostra a tela inteira (sem cortar as laterais)", "Aproxima a tela",
                  "Aumenta a tela e diminui o João"],
    "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "gerar.sh e os build-*.py",
    "motivo_narracao": "Neste formato a voz é o João gravado: a fala só muda trocando o bruto (a câmera cortada).",
    "onde": ("O vídeo é a gravação de tela (work/tela.mp4) em cima e o João falando (work/joao.mp4) embaixo, com a frase nas faixas branca "
             "e vermelha, montado pelo gerar.sh do modelo a partir do comando.sh. Você NÃO mexe no comando.sh: edite só {arq_ia}. As cenas só "
             "marcam o tempo da fala; o que muda mora nos campos do TOPO do arquivo."),
    "conferir": "O vídeo todo é refeito pelo Estúdio depois. Pra conferir um enquadramento, tire um quadro de work/tela.mp4 "
                "(`ffmpeg -ss <s> -i work/tela.mp4 -frames:v 1 q.jpg`) e OLHE a imagem.",
    "dicas": ("Campos do topo: \"frase\" (as linhas da faixa separadas por \"|\", em caixa-alta, até 3 linhas curtas), \"tela_modo\" (\"cover\" "
              "enche o bloco cortando as laterais, \"fit\" mostra a tela inteira com fundo desfocado), \"tela_x\" (0 a 1, foco horizontal no "
              "cover), \"tela_zoom\" (1 = normal), \"tela_atraso\" (segundos que a tela começa depois da câmera; negativo = antes; acerta o "
              "sincronismo), \"corte\" (altura da emenda em pixels: maior = tela maior e câmera menor; 960 é o padrão), \"cam_zoom\", \"cam_y\" "
              "(0 a 1, só vale com \"rosto_fixo\" true; sem ele a câmera segue o rosto). Não mexa em \"palavras\" nem no \"de\" das cenas."),
}
SPECS = {"analise-de-tela": SPEC}
