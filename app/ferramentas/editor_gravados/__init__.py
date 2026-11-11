"""
editor_gravados — um módulo por estilo GRAVADO (ffmpeg + PIL) que o "Editar vídeo" (editor.py) sabe editar por cena.

Cada módulo (arquivo .py aqui, sem "_" no começo do nome) exporta  SPECS = {"<slug do formato>": spec}.  `carregar()` importa
todos e junta os SPECS; módulo que falha no import é pulado com uma linha no stderr e nunca quebra o editor.
O padrão de cada chave é o comportamento do Faixa com cenas (editor.py), que não muda.

CONTRATO DO SPEC GRAVADO (dict). Obrigatórios: fonte, ler, gravar, cmd. O resto tem padrão.

  gravado      True (o `carregar` põe sozinho).
  fonte        arquivo principal do vídeo, relativo à pasta (ex.: "PLANO.json", "camada.json"). É o que o `fonte(p)` devolve.
  arquivos     tudo que o `gravar` escreve ou que o render lê e muda com a edição: lista de caminhos relativos, ou função
               arquivos(p) -> lista. A versão (editor/versoes/vN) guarda e volta TODOS. Padrão: [fonte].
  precisa      arquivos que têm de existir pra editar (relativos à pasta ou absolutos), ou função precisa(p) -> lista. Padrão: ["work/joao.mp4"].
  achar(p)     opcional: True se a pasta é deste spec (pra pasta de um formato que não existe mais, ou sem slug próprio).
               O spec do formato certo (a chave = slug do formato do modelo) ganha sempre; `achar` só vale sem formato.
  ler(p)       -> doc: {"titulo", "saida" (mp4 final, caminho absoluto ou relativo à pasta), "duracao" (s), "palavras" (caminho
               do words.json relativo à pasta, se houver), "cenas": [{"de": segundo, "tipo": ..., ...}], + as chaves globais}.
               A cena termina onde a próxima começa; o "de" é da fala e não muda na edição.
  gravar(p, doc)  escreve o doc de volta nos `arquivos` (o inverso do `ler`; ler → gravar sem mexer não pode mudar nada).
  cmd(p)       -> (lista_do_comando, cwd) que REFAZ o vídeo inteiro; None se não dá (a pasta fica fora do editor). Use sys.executable
               pra Python. O Estúdio põe o python da venv na frente do PATH (zsh, python3 e ffmpeg resolvem sozinhos).
  cmd_txt(p)   o mesmo comando em texto, pro pedido à IA (padrão: a lista do cmd juntada).
  saida(p)     -> Path do mp4 final (padrão: clientes/<C>/<x>Content/output/<modelo>/<slug>.mp4).
  timeout      segundos máximos do render (padrão 3600).
  onde         texto do pedido à IA: o que é este vídeo e o que ela edita. Aceita {arq_ia} {pasta} {cmd}.
  conferir     texto do pedido: como a IA confere uma cena (padrão: tirar um quadro do clipe e olhar).
  Para a tela: rotulos {campo: rótulo}, tipos {tipo: rótulo}, tipo_padrao, juntos {campo: [campos que andam junto]},
  sempre (campos que dá pra pôr mesmo a cena não tendo), globais {elemento: [chaves do TOPO do doc]} (valem pro vídeo todo),
  sugestoes [textos], dicas (texto; aceita {base} {raiz}), nao_rodar (o que a IA nunca roda), etapas, narracao, material,
  motivo_narracao.
  livre        True só no modo livre (livre.py): a IA edita os arquivos da pasta; ver o módulo.

Ajudantes comuns em  editor_gravados._base  (duracao_video, saida_padrao, trechos_da_fala, palavras).
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path


def carregar() -> dict:
    """Junta os SPECS de todos os módulos deste pacote. Módulo quebrado é pulado (uma linha no stderr)."""
    out: dict = {}
    for m in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if m.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{m.name}")
            specs = getattr(mod, "SPECS", None) or {}
            for slug, spec in specs.items():
                spec.setdefault("gravado", True)
                out[slug] = spec
        except Exception as e:  # noqa: BLE001  (um estilo com defeito não derruba o editor)
            print(f"editor_gravados: pulei {m.name}: {type(e).__name__}: {e}", file=sys.stderr)
    return out
