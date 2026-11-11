#!/usr/bin/env python3
"""
editor — editar um vídeo de motor (cenas.json + render.py) cena por cena, com o Claude mexendo SÓ no que o João marcou.

    python3 editor.py cenas <pasta>                       # lista as cenas (tempo, fala, elementos)
    python3 editor.py rodar <pasta> <pedido-id>           # roda um pedido gravado em editor/pedidos/ (a tela chama)

A fidelidade não depende da IA obedecer: depois que ela termina, o Estúdio compara o cenas.json com a versão de antes e
só aceita a mudança no alcance marcado (o elemento, a cena ou o vídeo todo); o resto volta sozinho. Toda mudança vira
versão nova em editor/versoes/ (v1, v2...) e nenhuma é apagada. PLANO-2.0.md, item 1.

Vídeo GRAVADO (ffmpeg + PIL, ex.: Faixa com cenas): a "cena" é cada trecho do PLANO.json. O editor lê o PLANO como uma lista
de cenas (`_ler_faixa`: janelas + os trechos só do João no meio) e grava de volta no PLANO.json (`_gravar_faixa`) sem mudar o
jeito que o gerar.py lê. A miniatura é um quadro do vídeo pronto; o render é o gerar.py do modelo.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import RAIZ, com_venv, gravar_json, ler_json, rodar_com_limite  # noqa: E402
import editor_gravados  # noqa: E402  (um módulo por estilo gravado: ver o contrato no __init__.py)

ROTULOS = {"imagem": "Imagem", "imagens": "Imagens", "texto": "Texto na tela", "pessoas": "Pessoas recortadas",
           "quadros_de": "Vídeo (clipe)", "itens": "Pílulas", "msgs": "Mensagens", "marcos": "Linha do tempo",
           "rotulos": "Rótulos", "simbolo": "Ícone", "rotulo": "Rótulo", "etiqueta": "Etiqueta", "nota": "Nota",
           "mov": "Movimento", "entrada": "Transição", "de_n": "Número", "ate_n": "Número", "modo": "Posição do João",
           "musica": "Música"}
TIPOS = {"foto": "Foto", "titulo": "Foto com frase", "cartao": "Cartão", "rajada": "Rajada de fotos", "print": "Print",
         "colagem": "Colagem", "texto": "Texto que acende", "icone": "Ícone", "venn": "Venn", "chips": "Pílulas",
         "dividido": "Dividido", "contador": "Contador", "zap": "Conversa", "linha": "Linha do tempo",
         "clipe": "Vídeo real", "recorte": "Pessoas recortadas", "fala": "Você falando"}
JUNTOS = {"texto": ["forte", "tempos", "tam", "y"], "imagem": ["foco", "pb", "ponto", "escuro", "logo", "simbolo", "cor"], "imagens": ["pb", "quadros"],
          "quadros_de": ["inicio", "vel"], "msgs": ["grupo", "membros"], "de_n": ["ate_n", "ano", "prefixo", "sufixo"],
          "simbolo": ["cor"], "rotulo": ["forte"], "etiqueta": ["nota"], "mov": ["forca", "foco"],
          "modo": ["lado", "imagem", "pb", "escuro", "foco", "mov", "y", "forte"]}   # a cena "fala" (o João): cheia ↔ no cantinho sobre uma imagem   # campo que anda junto
SUGESTOES = ["Deixa esta cena mais forte", "Troca a imagem por uma que case mais com a fala",
             "O texto da tela está grande demais", "Põe uma transição na entrada"]

# ───────────────────────── uma camada pequena por formato de motor ─────────────────────────
# Tudo que muda de um formato pra outro mora aqui: os rótulos dos elementos, o que anda junto, o que a IA pode usar, quais
# etapas existem e se a narração/o material dá pra trocar sem o chat. Formato que não está aqui usa o do Editorial.
# "render": "pasta" (render.py dentro do vídeo) ou "base" (formatos/<slug>/base/render.py); sempre com --cenas e --quadro.

EXPLICADOR_ROTULOS = {"mundo": "Lugar", "lugar": "Personagens", "acoes": "Ação", "cam": "Câmera", "obj": "Objetos e números",
                      "trans": "Transição", "brilho": "Brilho"}
EXPLICADOR_CENARIOS = {"cidade": "Cidade", "consultorio": "Consultório", "escritorio": "Escritório", "aquario": "Aquário",
                       "casa": "Casa", "loja": "Loja", "restaurante": "Restaurante", "banco": "Banco", "cassino": "Cassino"}
DOCUMENTARIO_ROTULOS = {"texto": "Texto na tela", "titulo": "Título", "itens": "Lista", "nome": "Nome", "cargo": "Cargo",
                        "imagem": "Imagem", "video": "Vídeo (b-roll)", "plano": "Enquadramento", "destaque": "Palavra em destaque",
                        "dor": "Palavra de dor", "fundo": "Fundo", "quadro_s": "Quadro escolhido", "giro": "Giro",
                        "circulo": "Círculo", "rotulos": "Rótulos", "topo": "Frase no topo", "de_hora": "Relógio",
                        "etiqueta_x": "Etiqueta", "legenda_y": "Altura da legenda"}
DOCUMENTARIO_TIPOS = {"frase": "Frase", "pessoa": "Pessoa falando", "recorte": "Silhueta", "relogio": "Relógio",
                      "polaroid": "Polaroid", "caderno": "Caderno", "traco": "Bifurcação", "jornal": "Jornal", "filme": "Cena de filme"}


def _tipo_explicador(c: dict, doc: dict) -> str:
    m = (doc.get("mundos") or {}).get(c.get("mundo"), {})
    t = str(m.get("tipo") or c.get("mundo") or "")
    return EXPLICADOR_CENARIOS.get(t, t.capitalize() or "Cena")


# ───────────────────────── vídeo gravado: o PLANO.json do Faixa com cenas vira uma lista de cenas ─────────────────────────

FAIXA_ROTULOS = {"tipo": "Tela", "clipe": "Cena de cima / tela", "inicio": "Ponto do clipe", "frase": "Frase da faixa",
                 "crop_y_fixo": "Enquadramento do João"}
FAIXA_TIPOS = {"dividido": "Dividido", "cheia": "Cena em tela cheia", "joao": "Só o João"}
FAIXA_MODO = {"S": "dividido", "C": "cheia"}   # o modo da janela no PLANO.json
FAIXA_DERIVADAS = ("titulo", "duracao", "saida", "palavras", "cenas")   # existem só na lista de cenas, nunca vão pro PLANO.json


def _duracao_video(f: Path) -> float:
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1",
                                              str(f)], text=True, timeout=30))
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def _saida_faixa(p: Path) -> Path:
    """Onde o gerar.py do modelo grava o vídeo: <x>Content/output/<modelo>/<slug>.mp4."""
    return p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def _ler_faixa(p: Path) -> dict:
    """PLANO.json → lista de cenas. Cada janela [início, fim, S|C, clipe, início-no-clipe] vira uma cena; o que sobra entre elas
    (e antes/depois) vira uma cena "joao" (João em tela cheia). O fim de cada cena é o início da seguinte, então o tempo é da fala."""
    plano = json.loads((p / "PLANO.json").read_text(encoding="utf-8"))
    cs, t = [], 0.0
    for j in plano.get("janelas") or []:
        s, e, modo, clipe = float(j[0]), float(j[1]), j[2], j[3]
        if s - t > 1e-6:
            cs.append({"de": t, "tipo": "joao"})
        cs.append({"de": s, "tipo": FAIXA_MODO.get(modo, "cheia"), "clipe": clipe, "inicio": j[4] if len(j) > 4 else 0})
        t = e
    dur = max(_duracao_video(p / "work" / "joao.mp4"), t)
    if dur - t > 1e-6:
        cs.append({"de": t, "tipo": "joao"})
    doc = {k: v for k, v in plano.items() if k != "janelas"}
    doc.update(titulo=str(plano.get("frase", p.name)).replace("|", " ").capitalize(), duracao=dur, saida=str(_saida_faixa(p)))
    if (p / "work" / "cortado" / "words.json").is_file():
        doc["palavras"] = "work/cortado/words.json"
    doc["cenas"] = cs
    return doc


def _gravar_faixa(p: Path, doc: dict) -> None:
    """Lista de cenas → PLANO.json (só as cenas com tela dividida ou cheia e clipe viram janela). O resto do PLANO fica como estava."""
    f = p / "PLANO.json"
    antigo = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    cs = doc.get("cenas") or []
    modo = {v: k for k, v in FAIXA_MODO.items()}
    janelas = []
    for i, c in enumerate(cs):
        if c.get("tipo") not in modo or not c.get("clipe"):
            continue
        fim = float(cs[i + 1]["de"]) if i + 1 < len(cs) else float(doc.get("duracao") or c["de"])
        janelas.append([float(c["de"]), fim, modo[c["tipo"]], c["clipe"], c.get("inicio", 0)])
    novo = {}
    for k in antigo:
        if k == "janelas":
            novo[k] = janelas
        elif k in doc and k not in FAIXA_DERIVADAS:
            novo[k] = doc[k]
    for k, v in doc.items():
        if k not in novo and k not in FAIXA_DERIVADAS:
            novo[k] = v
    novo.setdefault("janelas", janelas)
    f.write_text(json.dumps(novo, ensure_ascii=False, indent=1), encoding="utf-8")


MOTORES = {
    "editorial": {"render": "pasta", "rotulos": ROTULOS, "tipos": TIPOS, "juntos": JUNTOS, "sugestoes": SUGESTOES,
                  "globais": {"musica": ["musica"]}, "musica": True,   # "Música (vale pro vídeo todo)": a tela troca a faixa, a entrada e o volume (trocar_musica)
                  "etapas": ["voz", "palavras", "cenas", "video"], "narracao": True, "material": True, "mini_max": .6,
                  "nao_rodar": "gera.py", "tipo_padrao": "foto",
                  "prompt_ia": ("Foto realista de fotojornalismo, vertical 9:16, luz natural, o assunto da fala literal e bem claro, "
                                "pessoas e lugares reais e comuns (nada de ator posando), sem texto, sem logotipo, sem marca d'água."),
                  "dicas": ("Imagem nova: real e do assunto (foto do Commons com {base}/exemplos/commons.py, print de matéria com Playwright, "
                            "clipe com yt-dlp). Nunca banco com ator posando, nunca Wikipédia. Salve em fotos/, prints/ ou clipes/ desta pasta. "
                            "A imagem mostra o que a fala da cena diz (o objeto, a ação ou o lugar citado), não a pessoa nem o tema geral: ache o quadro DENTRO de um "
                            "vídeo real com `{raiz}/app/.venv/bin/python {raiz}/app/ferramentas/casar_imagem.py melhores <vídeo> \"<fala>\" -n 5` (descreva o que se VÊ) e "
                            "confira com `... casar_imagem.py pontuar <imagem> \"<fala>\" --outras \"<fala da cena vizinha>\"` antes de fechar; a mesma pessoa nunca em "
                            "2 cenas vizinhas. Ação = vídeo da ação: se a fala descreve uma ação (mandar dinheiro, pagar, digitar, ligar, assinar, rir...), a cena "
                            "leva um CLIPE real de quem faz aquilo (`{base}/exemplos/clipe.py busca` e `baixa`), não foto parada. Real e viral, nunca clichê: "
                            "o momento real do caso (notícia, vídeo oficial, foto da pessoa ou do lugar), depois clipe viral ou famoso, e só então banco; "
                            "banco com ator posando, pilha de dinheiro genérica e gente sorrindo pra câmera reprovam (`casar_imagem.py cliche <imagem>` abaixo de 0,05). "
                            "Nada repetido: nem a mesma foto nem outra quase igual perto no tempo. Rode `casar_imagem.py conferir` no fim. "
                            "Cena \"icone\": NUNCA emoji (\"simbolo\" reprova na conferência): troque por \"imagem\" com a LOGO REAL da marca (site oficial, press kit, "
                            "Wikimedia Commons ou {raiz}/app/ferramentas/fontes_gratis.py; PNG com transparência, salvo em fotos/) ou a foto real da coisa citada, "
                            "apague o \"simbolo\" e olhe o quadro: a logo entra colorida sobre um disco (\"logo\": true força). Peça sem foto (texto, ícone, contador...) "
                            "já ganha o fundo desfocado da cena vizinha sozinha; nunca ponha \"fundo\": \"liso\" sem o João pedir. "
                            "Cena \"fala\" = o João aparecendo (só nos vídeos feitos a partir do vídeo gravado dele): \"modo\" \"cheia\" (tela cheia, legenda "
                            "forte) ou \"canto\" (no cantinho em cima de \"imagem\", um print ou foto real; \"lado\" esq|dir). O vídeo dele sai sozinho "
                            "do work/fala/fala.mp4 no tempo da cena: nunca mexa na voz nem em work/fala/. Pra TIRAR o João de uma cena, troque o \"tipo\" por "
                            "uma peça do Editorial (foto, print, clipe...) com imagem real do assunto e apague \"modo\"/\"lado\"; pra PÔR, tipo \"fala\".")},
    "explicador-3d": {"render": "base", "rotulos": EXPLICADOR_ROTULOS, "tipos": {}, "tipo_de": _tipo_explicador,
                      "juntos": {"mundo": ["lugar", "cam", "obj", "acoes"], "lugar": ["acoes"], "trans": ["trans_q"]},
                      "sugestoes": ["Deixa a câmera mais próxima do rosto", "Troca a ação do personagem por uma mais forte",
                                    "Muda o personagem desta cena", "Põe uma transição na entrada"],
                      "etapas": ["video"], "narracao": False, "material": False, "mini_max": 1.2, "nao_rodar": "gera.py e gerar.py",
                      "sempre": ("mundo", "lugar", "acoes", "cam"), "tipo_padrao": "cena",   # elemento que dá pra pôr mesmo a cena não tendo
                      "aditivos": ("elenco", "mundos"),   # personagem novo entra no elenco/mundo; o que já existe não muda
                      "motivo_narracao": "A narração do Explicador 3D nasce do roteiro e da decupagem inteiros (muda todas as cenas): troca pelo chat.",
                      "dicas": ("Use só o que o motor conhece: personagens do \"elenco\" do cenas.json (ou da biblioteca {base}/elenco.js), poses e rostos "
                                "de {base}/gente.js, cenários de {base}/mundos.js, posições de {base}/marcas.json, objetos de {base}/objetos.js. "
                                "O \"em\" de cada ação é em segundos DENTRO da cena (a partir do \"de\" dela). NÃO mexa em \"fala\" nem em "
                                "\"palavras\" (são a narração). Câmera: de, para, olha, fov (\"de\" e \"para\" diferentes: a câmera nunca para).")},
    "faixa-com-cenas": {"gravado": True, "fonte": "PLANO.json", "ler": _ler_faixa, "gravar": _gravar_faixa,
                        "rotulos": FAIXA_ROTULOS, "tipos": FAIXA_TIPOS, "tipo_padrao": "joao",
                        "juntos": {"clipe": ["inicio"]}, "sempre": ("tipo", "clipe"),   # até a cena só do João pode ganhar um clipe
                        "globais": {"frase": ["frase"], "crop_y_fixo": ["crop_y_fixo"]},   # valem pro vídeo todo: só no elemento marcado
                        "sugestoes": ["Troca a cena de cima por uma que case mais com a fala", "Deixa essa cena em tela cheia",
                                      "Volta pro João sozinho nesse trecho", "Troca a frase da faixa"],
                        "etapas": ["video"], "narracao": False, "material": False, "nao_rodar": "gerar.py e gerar.sh",
                        "motivo_narracao": "Neste formato a voz é o João gravado: a fala só muda trocando o bruto (a câmera cortada).",
                        "dicas": ("Cada cena é um trecho do vídeo. \"tipo\": \"dividido\" (cena em cima e o João embaixo), \"cheia\" (cena em tela "
                                  "cheia) ou \"joao\" (só o João). \"clipe\" é o caminho de um vídeo mudo (do acervo, {raiz}/acervo/itens/*/clip.mp4, ou "
                                  "achado com a skill get-brolls: real e do assunto, nunca banco de imagem posando) e \"inicio\" é o segundo do clipe onde a "
                                  "cena começa. Cena \"joao\" não leva clipe. \"frase\" (no topo) são as linhas da faixa separadas por \"|\", em caixa-alta, "
                                  "até 3 linhas curtas. \"crop_y_fixo\" (no topo, número de 0 a 960) fixa a altura do recorte do João embaixo; sem ele o "
                                  "recorte segue o rosto. Pra conferir um clipe, tire um quadro dele "
                                  "(`ffmpeg -ss <inicio> -i <clipe> -frames:v 1 q.jpg`) e OLHE a imagem.")},
    "documentario": {"render": "pasta", "rotulos": DOCUMENTARIO_ROTULOS, "tipos": DOCUMENTARIO_TIPOS,
                     "juntos": {"video": ["inicio_s", "corte", "origem", "quadro_s"], "imagem": ["corte", "origem", "quadro_s"],
                                "texto": ["destaque", "dor"], "nome": ["cargo"], "titulo": ["itens"], "de_hora": ["ate_hora"],
                                "etiqueta_x": ["etiqueta_y"]},
                     "sugestoes": ["Deixa esta cena mais forte", "Troca o b-roll por um que case mais com a fala",
                                   "O texto da tela está grande demais", "Destaca outra palavra"],
                     "etapas": ["video"], "narracao": False, "material": False, "mini_max": .6, "nao_rodar": "gera.py",
                     "tipo_padrao": "frase",
                     "motivo_narracao": "O Documentário usa o vídeo gravado da pessoa como voz: a fala dele só muda trocando o bruto.",
                     "dicas": ("Os tipos e campos de cada cena estão em {base}/README.md. B-roll novo: real e do assunto, do acervo/ ou de "
                               "filme/matéria (campo \"origem\" dizendo de onde veio); banco de imagem reprova. Salve em brolls/ desta pasta. "
                               "A imagem mostra o que a fala da cena diz (o objeto, a ação ou o lugar citado), não a pessoa nem comercial de outra época: ache o quadro "
                               "DENTRO de um vídeo real (ex. o oficial da empresa) com `{raiz}/app/.venv/bin/python {raiz}/app/ferramentas/casar_imagem.py melhores "
                               "<vídeo> \"<fala>\" -n 5` (descreva o que se VÊ) e confira com `... casar_imagem.py pontuar <imagem> \"<fala>\" --outras \"<fala da cena "
                               "vizinha>\"` antes de fechar; a mesma pessoa nunca em 2 cenas vizinhas. Ação = vídeo da ação: se a fala descreve uma ação "
                               "(mandar dinheiro, pagar, assinar, correr...), a cena usa um clipe real de quem faz aquilo, não foto parada. Real e viral, nunca clichê: "
                               "o momento real do caso, depois clipe viral ou famoso, só então banco (ator posando e pilha de dinheiro genérica reprovam: "
                               "`casar_imagem.py cliche <imagem>` abaixo de 0,05). Nada repetido, nem quase igual (outro quadro do mesmo clipe conta).")},
}
MOTORES.update(editor_gravados.carregar())   # Tela dividida, Fala com cenas, Caixinha, Crítica, Análise de tela... + o modo livre


def formato_da_pasta(p: Path) -> str:
    """O formato do modelo dono da pasta (clientes/<C>/<x>Content/modelos/<modelo>/_sandbox-...). Modelo de um formato que não
    existe mais (ex.: frase-fixa): "editorial" se a pasta tem cenas.json (motor), senão "" (gravado: o `achar` dos módulos decide)."""
    try:
        import formatos
        f = formatos.de_modelo(p.parent.name)
        if f:
            return f["slug"]
    except Exception:  # noqa: BLE001
        pass
    return "editorial" if (Path(p) / "cenas.json").is_file() or not (Path(p) / "work").is_dir() else ""


def _achar(p: Path, livre: bool) -> dict | None:
    """Spec que reconhece a pasta pelo `achar` (formato removido ou sem slug próprio). Os do estilo antes, o modo livre por último."""
    for k, sp in MOTORES.items():
        if bool(sp.get("livre")) is livre and sp.get("achar"):
            try:
                if sp["achar"](p):
                    return sp
            except Exception:  # noqa: BLE001
                continue
    return None


def _fonte_de(p: Path, s: dict) -> str:
    f = s.get("fonte")
    return (f(p) if callable(f) else f) or "cenas.json"


def _serve(p: Path, s: dict) -> bool:
    """O spec gravado dá conta desta pasta? (tem o arquivo das cenas e, se ele diz o comando, o comando.)"""
    try:
        return (Path(p) / _fonte_de(p, s)).is_file() and (not s.get("cmd") or bool(s["cmd"](p)))
    except Exception:  # noqa: BLE001
        return False


def spec(p: Path) -> dict:
    """A camada do formato desta pasta; sem formato conhecido, o spec que a reconhece (`achar`), o modo livre e, no fim, o do Editorial."""
    s = MOTORES.get(formato_da_pasta(p))
    if s and not s.get("livre"):
        if not s.get("gravado") or _serve(p, s):
            return s
        return _achar(p, True) or s   # o spec do estilo não entende esta pasta (montada à mão): o modo livre, se der
    return _achar(p, False) or _achar(p, True) or MOTORES["editorial"]


def gravado(p: Path) -> bool:
    """Vídeo gravado (ffmpeg): a cena é um trecho do PLANO.json (ou do camada.json...) do modelo, não uma peça do cenas.json."""
    return bool(spec(p).get("gravado"))


def fonte(p: Path) -> Path:
    """O arquivo que guarda as cenas deste vídeo: cenas.json (motor) ou o `fonte` do spec gravado (PLANO.json, camada.json...)."""
    return p / _fonte_de(p, spec(p)) if gravado(p) else p / "cenas.json"


def arquivos(p: Path) -> list[str]:
    """Tudo que a edição muda e a versão guarda (relativo à pasta). Motor: o cenas.json. Gravado: o `arquivos` do spec ou a fonte."""
    s = spec(p)
    a = s.get("arquivos")
    a = a(p) if callable(a) else a
    return list(a) if a else [_fonte_de(p, s)]


def _precisa(p: Path) -> list[str]:
    a = spec(p).get("precisa")
    a = a(p) if callable(a) else a
    return list(a) if a is not None else ["work/joao.mp4"]


def _saida(p: Path) -> Path:
    h = spec(p).get("saida")
    return Path(h(p)) if h else _saida_faixa(p)


def _cmd_gravado(p: Path) -> tuple[list[str], Path] | None:
    """(comando, cwd) que refaz o vídeo gravado inteiro; None se não dá. Padrão (Faixa): o gerar.py do modelo."""
    s = spec(p)
    if s.get("cmd"):
        r = s["cmd"](p)
        return (list(r[0]), Path(r[1])) if r else None
    g = p.parent / "gerar.py"
    return ([sys.executable, str(g), "--dir", ".", "--saida", str(_saida(p))], p) if g.is_file() else None


def render_de(p: Path) -> Path | None:
    """O render.py que desenha este vídeo: o da própria pasta ou o da base do formato (Explicador 3D). Gravado: o gerar.py do modelo
    (spec com `cmd`: a própria pasta, só pra dizer que existe comando)."""
    if gravado(p):
        if spec(p).get("cmd"):
            return p if _cmd_gravado(p) else None
        g = p.parent / "gerar.py"
        return g if g.is_file() else None
    if (p / "render.py").is_file():
        return p / "render.py"
    fmt = formato_da_pasta(p)
    if fmt in MOTORES and MOTORES[fmt]["render"] == "base":
        b = RAIZ / "formatos" / fmt / "base" / "render.py"
        return b if b.is_file() else None
    return None


def _cmd(p: Path, *args: str) -> list[str]:
    """O comando que chama o render.py deste vídeo (rode com cwd=p). Gravado: o que refaz o vídeo inteiro (sem --quadro; o cwd
    certo vem de `_cmd_gravado`)."""
    if gravado(p):
        return _cmd_gravado(p)[0]
    return [sys.executable, str(render_de(p)), "--cenas", "cenas.json", *args]


def _cmd_txt(p: Path) -> str:
    """O mesmo comando, pra escrever no pedido da IA."""
    if gravado(p) and spec(p).get("cmd_txt"):
        return spec(p)["cmd_txt"](p)
    r = render_de(p)
    if gravado(p):
        c = _cmd_gravado(p)
        return f"python3 {r} --dir {p}" if not spec(p).get("cmd") else " ".join(c[0]).replace(sys.executable, "python3", 1)
    return "python3 render.py --cenas cenas.json" if r == p / "render.py" else f"python3 {r} --cenas {p / 'cenas.json'}"


def _refazer_video(p: Path) -> subprocess.CompletedProcess:
    """Refaz o vídeo agora (o render do motor, ou o comando do gravado), com o python da venv no PATH."""
    if gravado(p):
        cmd, cwd = _cmd_gravado(p)
        return rodar_com_limite(cmd, spec(p).get("timeout", 3600), cwd=cwd, capture_output=True, text=True, env=com_venv())
    return rodar_com_limite(_cmd(p), 3600, cwd=p, capture_output=True, text=True, env=com_venv())


def _entende_quadro(p: Path) -> bool:
    r = render_de(p)
    return bool(r) and "--quadro" in r.read_text(encoding="utf-8", errors="ignore")


def pasta(rel: str | None) -> Path | None:
    """A pasta do vídeo (relativa à raiz) se tem cenas.json e um render.py (o dela ou o da base do formato) e está dentro do Estúdio."""
    if not rel:
        return None
    p = (RAIZ / rel).resolve()
    if RAIZ.resolve() not in p.parents or not render_de(p):
        return None
    if not (fonte(p).is_file() and (not gravado(p) or all((p / x).exists() for x in _precisa(p)))):
        return None
    return p


def rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(RAIZ.resolve()))


def _doc(p: Path) -> dict:
    if gravado(p):
        return spec(p)["ler"](p)
    return json.loads((p / "cenas.json").read_text(encoding="utf-8"))


def _gravar(p: Path, doc: dict) -> None:
    """Grava as cenas no arquivo do vídeo (cenas.json, ou o PLANO.json por tradução)."""
    if gravado(p):
        spec(p)["gravar"](p, doc)
    else:
        (p / "cenas.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def _arq_ia(p: Path, doc: dict) -> Path:
    """O arquivo que a IA edita: o próprio cenas.json; no gravado, a lista de cenas em editor/cenas.json (o PLANO.json ela nem vê)."""
    if not gravado(p):
        return p / "cenas.json"
    f = p / "editor" / "cenas.json"
    gravar_json(f, doc)
    return f


def _palavras(p: Path, doc: dict) -> list[dict]:
    f = p / str(doc.get("palavras") or "work/words.json")
    if not f.is_file():
        return []
    d = json.loads(f.read_text(encoding="utf-8"))
    return [w for w in (d.get("words", d) if isinstance(d, dict) else d) if isinstance(w, dict)]


def _video(p: Path, doc: dict) -> Path:
    return p / str(doc.get("saida") or "video.mp4")


def cenas(p: Path) -> list[dict]:
    """Cada cena com n (1..), de, ate, fala do trecho, tipo legível e os elementos que dá pra mudar sozinhos."""
    doc = _doc(p)
    m = spec(p)
    cs = doc.get("cenas") or []
    ws = _palavras(p, doc)
    dur = float(doc.get("duracao") or (cs[-1]["de"] + 2 if cs else 0))
    out = []
    for i, c in enumerate(cs):
        de, ate = float(c.get("de", 0)), float(cs[i + 1]["de"]) if i + 1 < len(cs) else dur
        fala = " ".join(w.get("word", "").strip() for w in ws if de - .02 <= float(w.get("start", 0)) < ate - .02)
        if not fala and isinstance(c.get("fala"), str):   # Explicador 3D: a fala já vem escrita em cada cena
            fala = c["fala"]
        els = []
        for k in m["rotulos"]:
            if k in m.get("globais", {}):
                els.append({"campo": k, "rotulo": m["rotulos"][k] + " (vale pro vídeo todo)"})
            elif (k in c or k in m.get("sempre", ())) and not (k == "ate_n" and "de_n" in c):
                els.append({"campo": k, "rotulo": m["rotulos"][k]})
        tipo = c.get("tipo", m.get("tipo_padrao", "foto"))
        rot = m["tipo_de"](c, doc) if m.get("tipo_de") else m["tipos"].get(tipo, tipo)
        out.append({"n": i + 1, "de": round(de, 2), "ate": round(ate, 2), "tipo": tipo, "tipo_rotulo": rot,
                    "fala": fala, "elementos": els})
    return out


# ───────────────────────── miniaturas (um quadro do meio de cada cena) ─────────────────────────

def miniaturas(p: Path) -> list[str]:
    """editor/mini/NNN.jpg de cada cena, refeitas só quando o cenas.json muda. Devolve os caminhos relativos."""
    from PIL import Image
    cs = cenas(p)
    d = p / "editor" / "mini"
    d.mkdir(parents=True, exist_ok=True)
    marca = d / ".cenas.mtime"
    vid = _video(p, _doc(p)) if gravado(p) else None
    atual = str(fonte(p).stat().st_mtime) + (f"-{vid.stat().st_mtime}" if vid and vid.is_file() else "")   # gravado: muda com o vídeo novo também
    faltam = not marca.exists() or marca.read_text() != atual or any(not (d / f"{c['n']:03d}.jpg").exists() for c in cs)
    if faltam and cs and gravado(p):
        _mini_gravado(p, cs, d, vid)
        marca.write_text(atual)
    elif faltam and cs:
        mx = spec(p).get("mini_max", .6)
        ts = [round(c["de"] + min(mx, (c["ate"] - c["de"]) * .6), 2) for c in cs]
        rodar_com_limite(_cmd(p, "--quadro", ",".join(f"{t:.2f}" for t in ts)), 1200, cwd=p, capture_output=True, text=True, env=com_venv())
        for c, t in zip(cs, ts):
            png = p / "quadros" / f"{t:06.2f}.png"
            if png.exists():
                im = Image.open(png).convert("RGB")
                im.thumbnail((216, 384))
                im.save(d / f"{c['n']:03d}.jpg", quality=82)
        marca.write_text(atual)
    return [rel(d / f"{c['n']:03d}.jpg") for c in cs]


def miniaturas_prontas(p: Path) -> bool:
    """As miniaturas de editor/mini estão em dia (sem gerar nada)? É o que a tela olha antes de pedir pra preparar em segundo plano."""
    try:
        cs = cenas(p)
        d = p / "editor" / "mini"
        marca = d / ".cenas.mtime"
        vid = _video(p, _doc(p)) if gravado(p) else None
        atual = str(fonte(p).stat().st_mtime) + (f"-{vid.stat().st_mtime}" if vid and vid.is_file() else "")
        return bool(cs) and marca.exists() and marca.read_text() == atual and all((d / f"{c['n']:03d}.jpg").exists() for c in cs)
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return False


def _mini_gravado(p: Path, cs: list[dict], d: Path, vid: Path | None) -> None:
    """Vídeo gravado: a miniatura é o quadro do meio da cena, tirado do próprio vídeo pronto (sem render)."""
    if not vid or not vid.is_file():
        return
    for c in cs:
        t = c["de"] + (c["ate"] - c["de"]) * .5
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(vid), "-frames:v", "1",
                        "-vf", "scale=216:-2", "-q:v", "4", str(d / f"{c['n']:03d}.jpg")], capture_output=True, timeout=120)


# ───────────────────────── versões (nunca apaga) ─────────────────────────

def versoes(p: Path) -> list[dict]:
    d = p / "editor" / "versoes"
    if not d.is_dir():
        return []
    out = []
    for v in sorted(d.iterdir(), key=lambda x: int(x.name[1:]) if x.name[1:].isdigit() else 0):
        meta = ler_json(v / "meta.json", {}) or {}
        vid = next(iter(sorted(v.glob("*.mp4"))), None)
        out.append({"v": v.name, "n": int(v.name[1:]), "o_que": meta.get("o_que", ""), "quando": meta.get("quando", ""),
                    "video": rel(vid) if vid else ""})
    return out


def guardar_versao(p: Path, o_que: str) -> str:
    """Copia o cenas.json (ou os `arquivos` do gravado) e o vídeo de agora pra editor/versoes/vN. A 1ª chamada guarda o original como v1."""
    d = p / "editor" / "versoes"
    d.mkdir(parents=True, exist_ok=True)
    n = max([x["n"] for x in versoes(p)] + [0]) + 1
    v = d / f"v{n}"
    v.mkdir()
    for a in arquivos(p):
        if (p / a).is_file():
            _clonar(p / a, v / a)
    doc = _doc(p)
    if _video(p, doc).is_file():
        _clonar(_video(p, doc), v / f"video-v{n}.mp4")
    gravar_json(v / "meta.json", {"o_que": o_que, "quando": time.strftime("%d/%m %H:%M")})
    return v.name


def voltar(p: Path, nome: str) -> str:
    """Volta pra versão `nome`: os arquivos e o vídeo dela viram a versão nova (a de agora continua guardada)."""
    v = p / "editor" / "versoes" / nome
    if not v.is_dir() or not any((v / a).is_file() for a in arquivos(p)):
        raise ValueError("Versão não encontrada.")
    for f in sorted(v.rglob("*")):   # tudo que a versão guardou volta pro lugar (o modo livre guarda arquivos que o spec não lista)
        r = f.relative_to(v)
        if f.is_file() and str(r) != "meta.json" and not (len(r.parts) == 1 and r.name.startswith("video-v")):
            _clonar(f, p / r)
    vid = next(iter(sorted(v.glob("*.mp4"))), None)
    if vid:
        _clonar(vid, _video(p, _doc(p)))
    n = guardar_versao(p, f"voltou pra {nome}")
    av = entregar(p)
    _estado(p, avisos=[av] if av else [])
    return n


# ───────────────────────── o vídeo entregue do job ─────────────────────────
# O motor (Editorial, Documentário, Explicador 3D) refaz o vídeo na pasta de trabalho; o que a tela mostra no "Ficou bom?", no Esperando
# você e na página do vídeo é o `job["saida"]`. Sem esta entrega o João edita e continua vendo o vídeo antigo. Vídeo gravado grava
# direto no job["saida"] (mesmo arquivo): aí não há o que fazer. 30-out-2026.

ENTREGA_ABERTA = ("concluido", "aprovado")


def job_da_pasta(p: Path) -> dict | None:
    """O job da tela dono desta pasta: app/jobs/<cliente>/<slug>/job.json com job["sandbox"] == rel(p). Sem job (feito pelo chat): None."""
    import producao as _prod
    try:
        alvo = rel(p)
        cli = Path(p).resolve().relative_to((RAIZ / "clientes").resolve()).parts[0]
    except (ValueError, IndexError):
        return None
    try:
        j = _prod.carregar(cli, Path(p).name.removeprefix("_sandbox-"))
    except ValueError:
        j = None
    if j and str(Path(j.get("sandbox") or "")) == alvo:
        return j
    return next((j for j in _prod.listar(cli) if str(Path(j.get("sandbox") or "")) == alvo), None)


def _preparar(p: Path, saida: Path) -> None:
    """Capa e miniaturas das cenas nascem agora, em segundo plano (preparar.py): a tela abre já com elas."""
    try:
        import preparar
        preparar.depois(video=saida, pasta=p)
    except Exception:  # noqa: BLE001
        pass


def entregar(p: Path) -> str:
    """Depois de um vídeo novo na pasta: ele vira o `job["saida"]`, tratado como o runner trata o final da esteira (`checar_cauda.fechar`,
    `conferir_pos_render`). O entregue de antes vira versão (`guardar_final_anterior`); vídeo aprovado volta pro "Ficou bom?" (job
    "concluido" + Em andamento "pronto" de novo: a aprovação antiga fica mais velha que o vídeo). Exportado/arquivado não é tocado.
    Devolve o aviso pro João ('' = nada a dizer). Nunca derruba a edição."""
    try:
        job = job_da_pasta(p)
        novo = _video(p, _doc(p))
        if not job or not job.get("saida") or not novo.is_file():
            return ""
        saida = RAIZ / job["saida"]
        if saida.resolve() == novo.resolve():
            _preparar(p, saida)
            return ""   # o render já grava no entregue (vídeo gravado)
        if job.get("status") in ("exportado", "arquivado"):
            return "Esta edição ficou só aqui: o vídeo já tinha sido exportado."
        if job.get("rodando") or job.get("status") not in ENTREGA_ABERTA:
            return "Esta edição ficou só aqui: o Estúdio está mexendo neste vídeo agora."
        import producao as _prod
        if saida.is_file() and not _prod.guardar_final_anterior(job, "antes de editar o vídeo"):
            return "Esta edição ficou só aqui: não consegui guardar o vídeo anterior, então não troquei o entregue."
        _clonar(novo, saida)
        os.utime(saida, None)   # o clone herda a data do arquivo de origem: miniatura e cache do navegador pedem "mais novo que o último"
        try:   # ruído nos últimos 0,2 s (G10): fade-out e silêncio no fim, igual ao runner
            import checar_cauda
            checar_cauda.fechar(saida, RAIZ / job["sandbox"] / "qa" / "antes-cauda.mp4")
        except Exception as e:  # noqa: BLE001
            print(f"(cauda do áudio não conferida: {e})", file=sys.stderr)
        job.pop("edicao_alterada", None)
        job["status"] = "concluido"
        _prod.conferir_pos_render(job)   # sem conferência aprovada o Em andamento mostra os avisos, não "Vídeo pronto"
        _prod.salvar(job)
        import andamento as _and
        d = next((r for r in _and.registros() if r["cliente"] == job["cliente"] and r["slug"] == job["slug"]), None)
        if d and d.get("estado") == "pronto":   # volta pro "Ficou bom?" e pro Esperando você com o vídeo novo
            _and.pronto(job["cliente"], job["slug"], "Vídeo editado: assista e aprove", video=str(saida))
        _preparar(p, saida)
        return ""
    except Exception as e:  # noqa: BLE001
        print(f"(entrega do vídeo editado: {e})", file=sys.stderr)
        return "O vídeo novo saiu na pasta, mas não consegui trocar o entregue: " + str(e)[:160]


# ───────────────────────── o pedido ─────────────────────────

def estado(p: Path) -> dict:
    return ler_json(p / "editor" / "estado.json", {}) or {}


def _estado(p: Path, **kw) -> None:
    e = estado(p)
    e.update(kw, atualizado=time.strftime("%H:%M:%S"))
    gravar_json(p / "editor" / "estado.json", e)


def novo_pedido(p: Path, escopo: str, n: int | None, campo: str, texto: str, print_rel: str = "",
                modelo: str = "", esforco: str = "", n_fim: int | None = None) -> str:
    if estado(p).get("rodando"):
        raise ValueError("Já tem um pedido rodando neste vídeo. Espere terminar.")
    if not texto.strip():
        raise ValueError("Escreva o que mudar.")
    if escopo == "cena" and n and n_fim and n_fim != n:   # Shift+clique na linha do tempo: um trecho de cenas seguidas
        escopo, n, n_fim = "trecho", min(n, n_fim), max(n, n_fim)
    if escopo in ("cena", "elemento") and not n:
        raise ValueError("Clique numa cena primeiro.")
    if escopo == "elemento" and not campo:
        raise ValueError("Escolha o elemento da cena.")
    d = p / "editor" / "pedidos"
    d.mkdir(parents=True, exist_ok=True)
    pid = time.strftime("%Y%m%d-%H%M%S")
    gravar_json(d / f"{pid}.json", {"escopo": escopo, "n": n, "n_fim": n_fim if escopo == "trecho" else None, "campo": campo,
                                    "texto": texto.strip(), "print": print_rel,
                                    "modelo": modelo, "esforco": esforco})
    _estado(p, rodando=True, pedido=pid, fase="Claude lendo a cena", erro="", resumo="")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "rodar", rel(p), pid], cwd=RAIZ,
                     stdout=subprocess.DEVNULL, stderr=open(d / f"{pid}.err", "w"), start_new_session=True, env=com_venv())
    return pid


def prompt(p: Path, ped: dict) -> str:
    doc = _doc(p)
    cs = cenas(p)
    fmt = formato_da_pasta(p)
    m = spec(p)
    rotulos = m["rotulos"]
    cmd = _cmd_txt(p)
    if m.get("prompt"):   # modo livre: o pedido inteiro é do módulo
        return m["prompt"](p, ped, cs, doc, cmd)
    base = (RAIZ / "formatos" / fmt / "base").resolve()
    arq_ia = fonte(p) if not gravado(p) else p / "editor" / "cenas.json"
    alvo = ""
    if ped["escopo"] == "trecho":
        a_, b_ = cs[ped["n"] - 1], cs[ped["n_fim"] - 1]
        alvo = (f"ALCANCE: SÓ as cenas {ped['n']} a {ped['n_fim']} (índices {ped['n'] - 1} a {ped['n_fim'] - 1} da lista \"cenas\", de "
                f"{a_['de']} a {b_['ate']} s). Pode mudar o que quiser dentro delas, menos o \"de\" de cada uma.\n"
                f"A fala do trecho: \"{' '.join(c['fala'] for c in cs[ped['n'] - 1:ped['n_fim']])}\"\n"
                + (_conferir(p) if gravado(p) else f"Pra conferir: `{cmd} --quadro "
                + ",".join(f"{round(c['de'] + (c['ate'] - c['de']) * .6, 2)}" for c in cs[ped['n'] - 1:ped['n_fim']]) + "` e OLHE os PNG."))
    elif ped["escopo"] in ("cena", "elemento"):
        c = cs[ped["n"] - 1]
        i = ped["n"] - 1
        meio = [round(c["de"] + (c["ate"] - c["de"]) * f, 2) for f in (.25, .75)]
        glob = ped["escopo"] == "elemento" and ped["campo"] in m.get("globais", {})
        alvo = (f"ALCANCE: SÓ a cena {ped['n']} (índice {i} da lista \"cenas\" do {arq_ia.name}, de {c['de']} a {c['ate']} s"
                + ((f"), e SÓ o campo \"{ped['campo']}\" ({rotulos.get(ped['campo'], ped['campo'])}), que fica no TOPO do arquivo "
                    "e vale pro vídeo todo (não dentro da cena)." if glob else
                    f"), e dentro dela SÓ o campo \"{ped['campo']}\" ({rotulos.get(ped['campo'], ped['campo'])}).") if ped["escopo"] == "elemento" else ").")
                + f"\nA fala dessa cena: \"{c['fala']}\"\nA cena hoje: {json.dumps(doc['cenas'][i], ensure_ascii=False)}\n"
                + (_conferir(p) if gravado(p) else f"Pra conferir: `{cmd} --quadro {meio[0]},{meio[1]}` e OLHE os PNG em quadros/."))
    else:
        alvo = ("ALCANCE: o vídeo todo, mas mude só o que o pedido pede. Não mexa no \"de\" das cenas, na voz "
                + ("na música nem no corte do João. " + _conferir(p) if gravado(p) else
                   f"na música se o pedido não falar disso. Confira com `{cmd} --storyboard` e olhe o storyboard.jpg."))
    pr = (f"\nO João anexou um print: {RAIZ / ped['print']}. Abra a imagem (Read) antes: ela mostra o que ele quer mudar."
          if ped.get("print") else "")
    if gravado(p):
        onde = (m["onde"] if m.get("onde") else
                f"O vídeo é a câmera do João cortada (work/joao.mp4) com cenas por cima, montado pelo {render_de(p)} a partir do PLANO.json. "
                f"Você NÃO mexe no PLANO.json: edite só {{arq_ia}}, a lista de cenas (cada cena é um trecho do vídeo, com \"de\" = segundo em que começa; "
                f"ela termina onde a próxima começa).").replace("{arq_ia}", str(arq_ia)).replace("{pasta}", str(p)).replace("{cmd}", cmd)
        passos = (f'1. Edite o {arq_ia.name} direto ({arq_ia}). Nunca rode {m["nao_rodar"]} (refaz o vídeo inteiro) nem mexa em outro arquivo da pasta.\n'
                  '2. O tempo (\"de\") é da fala do João: não mude.')
    else:
        onde = f"O vídeo é desenhado pelo render.py ({render_de(p)}) a partir do cenas.json (peças e campos: {base}/README.md)."
        passos = (f'1. Edite o cenas.json direto. Nunca rode {m["nao_rodar"]} (refaz tudo e apaga outras edições).\n'
                  '2. Mudou o texto de uma cena "texto"? Pode deixar o "tempos": o Estúdio recalcula pela fala.')
    sem_imagem = ""
    if spec(p).get("material", True) and not gravado(p):
        sem_imagem = (f"\n\nSEM IMAGEM BOA pra uma cena (não achou foto/print/clipe real e exato do assunto)? NÃO gere imagem, NÃO use banco de imagem e NÃO invente: "
                      f"escreva em {p / 'editor' / 'sugestao_ia.json'} uma lista [{{\"n\": <número da cena>, \"o_que\": \"<prompt detalhado da imagem>\", \"motivo\": \"<por que não achou>\"}}] "
                      "(a lista inteira, sem repetir cena) e siga com a melhor opção que tiver. O João vê o custo e só ele permite gerar com IA.")
    return f"""Você é o editor de um vídeo do Estúdio. Trabalhe SÓ dentro da pasta {p}.
{onde}
Regras do formato: {RAIZ}/formatos/{fmt or p.parent.name}/aprendizado/regras.json. Do cliente: {p.parent}/aprendizado/regras.json. Gerais: {RAIZ}/REGRAS.md.

PEDIDO DO JOÃO: {ped['texto']}{pr}

{alvo}

Como trabalhar:
{passos}
3. {m["dicas"].format(base=base, raiz=RAIZ)}
4. Confira olhando os quadros. Não ficou como o pedido? Corrija e olhe de novo (até 3 vezes).
5. NÃO renderize o vídeo inteiro: o Estúdio faz isso depois.
6. Termine com UMA frase dizendo o que mudou (é o que o João vai ler).{sem_imagem}"""


def _conferir(p: Path) -> str:
    return spec(p).get("conferir") or _conferir_gravado()


def _conferir_gravado() -> str:
    return ("Pra conferir uma cena nova, tire um quadro do clipe com ffmpeg (-ss <inicio> -i <clipe> -frames:v 1) e OLHE a imagem; "
            "o vídeo todo é feito pelo Estúdio depois.")


def _aditivo(antes, depois):
    """Do `depois` só o que é NOVO: chave nova, item novo (de lista com "id" ou "quem"). O que já existia fica como era."""
    if isinstance(antes, dict) and isinstance(depois, dict):
        out = dict(antes)
        for k, v in depois.items():
            out[k] = _aditivo(antes[k], v) if k in antes else v
        return out
    if isinstance(antes, list) and isinstance(depois, list):
        chave = lambda x: (x.get("id") or x.get("quem")) if isinstance(x, dict) else None
        tem = {chave(x) for x in antes if chave(x)}
        return antes + [x for x in depois if chave(x) and chave(x) not in tem]
    return antes


def _fiel(antes: dict, depois: dict, ped: dict, juntos: dict | None = None, aditivos: tuple = (),
          globais: dict | None = None, tempo_fixo: bool = False) -> tuple[dict, list[str]]:
    """O cenas.json aceito: só o alcance marcado vem do `depois`; o resto volta do `antes`. Devolve (doc, avisos).
    `juntos` = os campos que andam com cada elemento no formato (padrão: os do Editorial). `aditivos` = chaves do topo do
    cenas.json (o elenco e os mundos do Explicador 3D) onde a IA pode ACRESCENTAR (personagem novo) mas nunca mudar o que já existe.
    `globais` = campos do TOPO do doc que um elemento pode mudar (a frase da faixa vale pro vídeo todo): {elemento: [chaves do topo]}.
    `tempo_fixo` = o "de" das cenas é da fala (vídeo gravado): nem o pedido de vídeo todo muda."""
    if ped["escopo"] == "video":
        if tempo_fixo:
            dc = depois.get("cenas") or []
            if len(dc) != len(antes.get("cenas") or []):
                return antes, ["A IA mudou o número de cenas (o tempo é da fala); nada mudou."]
            ok = copy.deepcopy(depois)
            ok["cenas"] = [dict(c, de=a["de"]) for c, a in zip(dc, antes["cenas"])]
            return ok, []
        return depois, []
    if ped["escopo"] == "elemento" and ped.get("campo") in (globais or {}):
        ok = copy.deepcopy(antes)
        chaves = globais[ped["campo"]]
        for k in chaves:
            if k in depois:
                ok[k] = depois[k]
            else:
                ok.pop(k, None)
        mexeu = [j + 1 for j, (a, b) in enumerate(zip(antes.get("cenas") or [], depois.get("cenas") or [])) if a != b]
        if mexeu or len(depois.get("cenas") or []) != len(antes.get("cenas") or []):
            return ok, ["A IA mexeu nas cenas também; só ficou o campo que você marcou (" + ", ".join(chaves) + ")."]
        outros = sorted(k for k in set(antes) | set(depois) if k not in chaves and k != "cenas" and antes.get(k) != depois.get(k))
        if outros:   # campo do topo de outro elemento: volta, mas o João fica sabendo
            return ok, ["A IA mexeu em " + ", ".join(outros) + " também; só ficou o que você marcou (" + ", ".join(chaves) + ")."]
        return ok, []
    ok, avisos = _fiel_cenas(antes, depois, ped, JUNTOS if juntos is None else juntos)
    ok = copy.deepcopy(ok)
    for k in aditivos:
        if k in depois and k in ok and depois[k] != antes.get(k):
            novo = _aditivo(antes.get(k), depois[k])
            if novo != antes.get(k):
                ok[k] = novo
            else:
                avisos.append(f"A IA mexeu em \"{k}\" (o que já existia); voltei como estava.")
    return ok, avisos


def _fiel_cenas(antes: dict, depois: dict, ped: dict, JUNTOS_: dict) -> tuple[dict, list[str]]:
    avisos = []
    if ped["escopo"] == "trecho":
        ok = copy.deepcopy(antes)
        faixa = range(ped["n"] - 1, ped["n_fim"])
        dc = depois.get("cenas") or []
        if len(dc) != len(antes.get("cenas") or []):
            avisos.append("A IA mudou o número de cenas; só aceitei as cenas do trecho, uma por uma.")
        for j in faixa:
            if j < len(dc) and isinstance(dc[j], dict):
                ok["cenas"][j] = dict(dc[j], de=antes["cenas"][j]["de"])
        fora = [j + 1 for j, (a_, b_) in enumerate(zip(antes.get("cenas") or [], dc)) if j not in faixa and a_ != b_]
        if fora:
            avisos.append("A IA mexeu fora do trecho (" + ", ".join(map(str, fora[:6])) + "); voltei como estava.")
        return ok, avisos
    i = ped["n"] - 1
    ok = copy.deepcopy(antes)
    nova = (depois.get("cenas") or [None] * (i + 1))[i] if len(depois.get("cenas") or []) > i else None
    if not isinstance(nova, dict):
        return antes, ["A IA apagou a cena: nada mudou."]
    if ped["escopo"] == "elemento":
        k = ped["campo"]
        for x in [k] + JUNTOS_.get(k, []):
            if x in nova:
                ok["cenas"][i][x] = nova[x]
            elif x in ok["cenas"][i] and x != k and x in JUNTOS_.get(k, []):
                ok["cenas"][i].pop(x)
        outros = [x for x in set(nova) | set(antes["cenas"][i]) if x not in [k] + JUNTOS_.get(k, [])
                  and nova.get(x) != antes["cenas"][i].get(x)]
        if outros:
            avisos.append("A IA mexeu em " + ", ".join(sorted(outros)) + " também; só ficou o que você marcou.")
    else:
        nova = dict(nova, de=antes["cenas"][i]["de"])   # o tempo da cena é da fala
        ok["cenas"][i] = nova
    mexeu = [j + 1 for j, (a, b) in enumerate(zip(antes.get("cenas") or [], depois.get("cenas") or [])) if j != i and a != b]
    if mexeu or len(depois.get("cenas") or []) != len(antes.get("cenas") or []):
        avisos.append("A IA mexeu em outra cena (" + ", ".join(map(str, mexeu[:6])) + "); voltei ela como estava.")
    return ok, avisos


def _tempos(p: Path, doc: dict) -> None:
    """Cena 'texto': um tempo por palavra, tirado da fala (o texto mudou de tamanho → as palavras acendem na hora certa)."""
    import re
    norm = lambda w: re.sub(r"[^\w]", "", str(w).lower())
    ws = _palavras(p, doc)
    cs = doc.get("cenas") or []
    for i, c in enumerate(cs):
        if c.get("tipo") != "texto" or not c.get("texto"):
            continue
        pal = str(c["texto"]).split()
        if isinstance(c.get("tempos"), list) and len(c["tempos"]) == len(pal):
            continue
        de, ate = float(c["de"]), float(cs[i + 1]["de"]) if i + 1 < len(cs) else float(doc.get("duracao") or c["de"] + 2)
        janela = [w for w in ws if de - .05 <= float(w.get("start", 0)) < ate]
        out, cur = [], 0
        for k, w in enumerate(pal):
            ach = next((j for j in range(cur, len(janela)) if norm(janela[j].get("word")) == norm(w)), None)
            if ach is not None:
                out.append(round(float(janela[ach]["start"]), 3)); cur = ach + 1
            else:   # palavra que não foi falada: entre a anterior e o fim, sem passar da cena
                base = out[-1] if out else de
                out.append(round(min(ate - .05, base + .12), 3))
        c["tempos"] = out


def _foto(p: Path) -> dict:
    """Os bytes de cada arquivo que a edição pode mudar (gravado): pra voltar tudo como estava se o vídeo novo não sair."""
    out = {}
    for a in arquivos(p):
        f = p / a
        out[a] = f.read_bytes() if f.is_file() else None
    return out


def _restaurar_foto(p: Path, foto: dict) -> None:
    for a, b in foto.items():
        f = p / a
        if b is None:
            f.unlink(missing_ok=True)
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b)


def _desfazer(p: Path, antes: dict, foto: dict | None) -> None:
    if foto is not None:
        _restaurar_foto(p, foto)
    else:
        _gravar(p, antes)


def rodar(p: Path, pid: str) -> int:
    import ia
    d = p / "editor" / "pedidos"
    ped = ler_json(d / f"{pid}.json", {})
    if not estado(p).get("base"):   # o original vira v1 antes da 1ª mudança
        _estado(p, base=guardar_versao(p, "original"))
    (p / "editor" / "sugestao_ia.json").unlink(missing_ok=True)   # cartões "gerar com IA" do pedido anterior já não valem
    antes = _doc(p)
    foto = _foto(p) if gravado(p) else None
    livre = bool(spec(p).get("livre"))
    arq = None if livre else _arq_ia(p, antes)
    prep = spec(p)["livre_antes"](p) if livre else None   # o modo livre guarda os arquivos e o vídeo antes de a IA mexer
    s = ia.para_alteracao(modelo=ped.get("modelo", ""), esforco=ped.get("esforco", ""))
    log, raw = d / f"{pid}.log", d / f"{pid}.raw.jsonl"
    _estado(p, fase="Claude mexendo na cena e conferindo os quadros", log=rel(log))
    try:
        code = ia.executar(prompt(p, ped), log, raw, d / f"{pid}.pid", s=s, tipo="feedback")
    except Exception as e:  # noqa: BLE001
        _desfazer(p, antes, foto)
        _estado(p, rodando=False, fase="", erro=f"O Claude não rodou: {e}")
        return 1
    avisos: list[str] = []
    if livre:
        mexeu = bool(spec(p)["livre_mudou"](p, prep))   # a IA mexeu em algum arquivo da pasta (ou criou um)
        aceito = None
    else:
        try:
            depois = json.loads(arq.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            depois = antes
        aceito, avisos = _fiel(antes, depois, ped, spec(p)["juntos"], tuple(spec(p).get("aditivos", ())),
                               spec(p).get("globais"), gravado(p) and spec(p).get("tempo_fixo", True))
        _tempos(p, aceito)
        _gravar(p, aceito)
        mexeu = aceito != antes
    if not mexeu:
        _estado(p, rodando=False, fase="", erro=("Nada mudou. " + " ".join(avisos)).strip() if code == 0 else
                "O Claude parou com erro e nada mudou. Veja o registro.")
        return 1
    _estado(p, fase="Gerando o vídeo novo (uns segundos por minuto de vídeo)")
    try:
        r = _refazer_video(p)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess([], 1, "", "o vídeo passou do tempo máximo")
    if r.returncode:
        if livre:
            spec(p)["livre_voltar"](p, prep)
        else:
            _desfazer(p, antes, foto)
        _estado(p, rodando=False, fase="", erro="O vídeo não saiu com a mudança; voltei como estava. " + (r.stderr or r.stdout)[-300:])
        return 1
    if livre:   # o vídeo novo só vale se mudou a cena marcada e o resto ficou igual
        msg = spec(p)["livre_conferir"](p, prep, ped, cenas(p))
        if msg:
            spec(p)["livre_voltar"](p, prep)
            _estado(p, rodando=False, fase="", erro=msg)
            return 1
    else:
        _anotar_edicao(p, ped, aceito)
    resumo = _resumo(raw)
    v = guardar_versao(p, (f"cenas {ped['n']}-{ped['n_fim']}: " if ped.get("n_fim") else f"cena {ped['n']}: " if ped.get("n") else "vídeo: ") + (resumo or ped["texto"])[:160])
    av = entregar(p)
    _estado(p, rodando=False, fase="", erro="", resumo=resumo, avisos=avisos + ([av] if av else []), versao=v)
    return 0


def _anotar_edicao(p: Path, ped: dict, doc: dict) -> None:
    """editor/edicoes.json: o que o João mudou cena por cena, pra voltar a valer quando a narração for refeita."""
    if ped["escopo"] == "trecho":
        for n in range(ped["n"], ped["n_fim"] + 1):
            _anotar_edicao(p, dict(ped, escopo="cena", n=n), doc)
        return
    if ped["escopo"] not in ("cena", "elemento"):
        return
    i = ped["n"] - 1
    c = doc["cenas"][i]
    juntos = spec(p)["juntos"]
    campos = {k: c[k] for k in ([ped["campo"]] + juntos.get(ped["campo"], [])) if k in c} if ped["escopo"] == "elemento" \
        else {k: v for k, v in c.items() if k not in ("de", "tempos")}
    f = p / "editor" / "edicoes.json"
    eds = [e for e in (ler_json(f, []) or []) if not (e["n"] == ped["n"] and ped["escopo"] == "cena")]
    eds.append({"n": ped["n"], "escopo": ped["escopo"], "campos": campos, "pedido": ped["texto"][:200]})
    gravar_json(f, eds)


def _reaplicar(p: Path, doc: dict) -> list[str]:
    """Depois de refazer as cenas pela fala nova, as edições do João voltam pra mesma cena (pela ordem)."""
    eds = ler_json(p / "editor" / "edicoes.json", []) or []
    avisos = []
    for e in eds:
        i = e["n"] - 1
        if i >= len(doc.get("cenas") or []):
            avisos.append(f"A cena {e['n']} não existe mais; a edição \"{e['pedido'][:40]}\" ficou de fora.")
            continue
        doc["cenas"][i].update(e["campos"])
    return avisos


def narracao(p: Path) -> dict:
    """A voz e o roteiro desta pasta (editor/narracao.json; sem ele, a voz do cliente)."""
    n = ler_json(p / "editor" / "narracao.json", {}) or {}
    if not n.get("voz"):
        try:
            import voz as _voz
            cli = p.parts[p.parts.index("clientes") + 1]
            n["voz"] = (_voz.voz_do_cliente(cli) or {}).get("id") or _voz.status()["voicestudio"]["voz"]
        except (ValueError, IndexError):
            n["voz"] = "default"
    r = p / "roteiro.txt"
    n["roteiro"] = r.read_text(encoding="utf-8") if r.is_file() else ""
    try:   # a emoção de cada frase (emocoes.json) pro painel da narração: [{texto, emocao}] e as opções
        import emocao as _emo
        n["emocoes"] = _emo.ler(p, n["roteiro"]) if n["roteiro"].strip() else []
        n["emocoes_opcoes"] = [{"slug": k, "rotulo": _emo.ROTULOS[k]} for k in _emo.TODAS]
        n["voz_tem_emocao"] = _emo.tem_variacao(n["voz"])
    except Exception:  # noqa: BLE001
        n["emocoes"], n["emocoes_opcoes"], n["voz_tem_emocao"] = [], [], False
    n["pode"] = bool(spec(p).get("narracao", True)) and r.is_file() and (p / "gera.py").is_file()   # só refaz sozinho quem tem roteiro e o gerador das cenas
    n["motivo"] = spec(p).get("motivo_narracao") or "Este vídeo não tem roteiro.txt e gera.py na pasta. A narração dele só troca pelo chat."
    if (p / "work" / "fala" / "voz.wav").is_file():   # Editorial falado: a voz é a gravação do João, não dá pra trocar por outra voz
        n["pode"], n["motivo"] = False, "Neste vídeo a voz é a sua gravação (Editorial falado): a fala só muda trocando o vídeo gravado."
    return n


def trocar_narracao(p: Path, voz: str, roteiro: str | None = None, emocoes: list[str] | None = None) -> None:
    if estado(p).get("rodando"):
        raise ValueError("Já tem um pedido rodando neste vídeo. Espere terminar.")
    if not narracao(p)["pode"]:
        raise ValueError(narracao(p)["motivo"])
    if roteiro is not None and roteiro.strip():
        (p / "roteiro.txt").write_text(roteiro.strip() + "\n", encoding="utf-8")
    if emocoes or (p / "emocoes.json").is_file():   # trocar a emoção de uma frase refaz só a voz e o tempo (o resto do pipeline já faz isso)
        import emocao as _emo
        if emocoes:
            _emo.trocar(p, emocoes)
        else:
            _emo.gravar(p, _emo.ler(p))   # o roteiro mudou: guarda as emoções já alinhadas com as frases novas
    gravar_json(p / "editor" / "narracao.json", {"voz": voz or narracao(p)["voz"]})
    _estado(p, rodando=True, fase="Gerando a narração nova (leva uns minutos)", erro="", resumo="", log="")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "narracao", rel(p)], cwd=RAIZ,
                     stdout=subprocess.DEVNULL, stderr=open(p / "editor" / "narracao.err", "w"), start_new_session=True,
                     env=com_venv())


ETAPAS = [("voz", "Voz"), ("palavras", "Tempo das palavras"), ("cenas", "Cenas"), ("video", "Vídeo")]


def etapas(p: Path) -> list[dict]:
    """O pipeline da pasta, com o que já existe (✓) e se dá pra refazer daqui."""
    doc = _doc(p)
    w = p / "work"
    tem = {"voz": (p / str(doc.get("voz") or "work/voz.wav")).is_file(), "palavras": (p / str(doc.get("palavras") or "work/words.json")).is_file(),
           "cenas": bool(doc.get("cenas")),
           "video": _video(p, doc).is_file()}
    gera = (p / "gera.py").is_file()
    pode = {"voz": narracao(p)["pode"], "palavras": gera and tem["voz"], "cenas": gera and tem["palavras"], "video": True}
    if (w / "fala" / "voz.wav").is_file():   # Editorial falado: voz e palavras são a gravação dele (preparar-fala.py), não se refazem daqui
        pode["voz"] = pode["palavras"] = False
    ids = spec(p).get("etapas") or [k for k, _ in ETAPAS]
    return [{"id": k, "rotulo": r, "feito": tem[k], "pode": pode[k]} for k, r in ETAPAS if k in ids]


def refazer(p: Path, desde: str) -> None:
    """Refaz do passo `desde` em diante (voz → palavras → cenas → vídeo), mantendo as edições por cena."""
    if estado(p).get("rodando"):
        raise ValueError("Já tem um pedido rodando neste vídeo. Espere terminar.")
    e = next((x for x in etapas(p) if x["id"] == desde), None)
    if not e or not e["pode"]:
        raise ValueError("Este passo não dá pra refazer daqui neste vídeo.")
    _estado(p, rodando=True, fase=f"Refazendo a partir de: {e['rotulo']}", erro="", resumo="", log="")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "narracao", rel(p), desde], cwd=RAIZ,
                     stdout=subprocess.DEVNULL, stderr=open(p / "editor" / "narracao.err", "w"), start_new_session=True,
                     env=com_venv())


def _rodar_narracao(p: Path, desde: str = "voz") -> int:
    import voicestudio
    n = narracao(p)
    passos = [k for k, _ in ETAPAS]
    faz = set(passos[passos.index(desde):]) if desde in passos else set(passos)
    if not estado(p).get("base"):
        _estado(p, base=guardar_versao(p, "original"))
    antes = fonte(p).read_text(encoding="utf-8")
    w = p / "work"
    w.mkdir(exist_ok=True)
    avisos = []
    try:
      if "voz" in faz:
        import emocao
        emocao.narrar_pasta(p, n["voz"], w / "voz-cru.mp3")   # cada frase com a variação da voz da emoção dela (emocoes.json); sem ele, a voz de sempre
      if "palavras" in faz:
        _estado(p, fase="Apertando as pausas e marcando o tempo de cada palavra")
        apertar = RAIZ / "formatos" / formato_da_pasta(p) / "base" / "exemplos" / "apertar.py"
        if "voz" in faz or not (w / "voz.wav").is_file():
            if apertar.is_file():
                subprocess.run([sys.executable, str(apertar), str(w / "voz-cru.mp3"), str(w / "voz.wav")], check=True, capture_output=True)
            else:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w / "voz-cru.mp3"), str(w / "voz.wav")], check=True)
        for f in ("words.json", "segmentos.json", "segmentos-whisper.json"):
            (w / f).unlink(missing_ok=True)
        r = subprocess.run([sys.executable, str(RAIZ / "app/ferramentas/corte.py"), "transcrever", str(w / "voz.wav"), str(w), "--groq"],
                           capture_output=True, text=True, timeout=900)
        if r.returncode or not (w / "words.json").is_file():
            raise RuntimeError("a transcrição não saiu: " + (r.stderr or r.stdout)[-200:])
        if n["roteiro"]:
            avisos = _conferir_fala(n["roteiro"], w / "words.json")
      if "cenas" in faz:
        _estado(p, fase="Refazendo as cenas no tempo da fala")
        g = subprocess.run([sys.executable, "gera.py"], cwd=p, capture_output=True, text=True, timeout=300)
        if g.returncode:
            raise RuntimeError("o gerador das cenas parou: " + (g.stderr or g.stdout)[-300:])
        doc = _doc(p)
        avisos += _reaplicar(p, doc)
        _tempos(p, doc)
        (p / "cenas.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
      if True:
        _estado(p, fase="Gerando o vídeo novo")
        rr = _refazer_video(p)
        if rr.returncode:
            raise RuntimeError("o vídeo não saiu: " + (rr.stderr or rr.stdout)[-300:])
    except Exception as e:  # noqa: BLE001
        fonte(p).write_text(antes, encoding="utf-8")
        _estado(p, rodando=False, fase="", erro=f"A narração nova não deu certo ({e}). O vídeo ficou como estava.")
        return 1
    nome = next((v["nome"] for v in _vozes() if v["id"] == n["voz"]), n["voz"])
    o_que = {"voz": f"narração nova: {nome}", "palavras": "tempo das palavras refeito", "cenas": "cenas refeitas",
             "video": "vídeo gerado de novo"}.get(desde, "refeito")
    v = guardar_versao(p, o_que)
    av = entregar(p)
    _estado(p, rodando=False, fase="", erro="", resumo=o_que[0].upper() + o_que[1:] + (
            "; as suas edições por cena voltaram." if desde in ("voz", "palavras", "cenas") else "."), avisos=avisos + ([av] if av else []), versao=v)
    return 0


def _vozes() -> list[dict]:
    try:
        import vozes
        return vozes.lista()
    except Exception:  # noqa: BLE001
        return []


def _conferir_fala(roteiro: str, words: Path) -> list[str]:
    """A voz engole palavra no começo do bloco (OmniVoice): avisa quando a fala tem bem menos palavras que o roteiro."""
    import re
    norm = lambda t: re.findall(r"\w+", t.lower())
    esp = norm(roteiro)
    ws = json.loads(words.read_text(encoding="utf-8"))
    got = norm(" ".join(x.get("word", "") for x in (ws.get("words", ws) if isinstance(ws, dict) else ws)))
    falta = len(esp) - len(got)
    return [f"A narração tem {falta} palavra(s) a menos que o roteiro: ouça o começo de cada frase."] if falta > max(2, len(esp) * .03) else []


GRUPOS = [("fotos", "Fotos"), ("fotos2", "Fotos"), ("prints", "Prints de fonte"), ("recortes", "Pessoas recortadas"), ("clipes", "Vídeos reais")]


def material(p: Path) -> list[dict]:
    """O que a pasta já tem pra usar nas cenas, por fonte: [{grupo, itens: [{arquivo, mini, campo, origem}]}]."""
    orig = {}
    for f in p.glob("*/origem.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for k, v in d.items():
            orig[f"{f.parent.name}/{k}"] = (v.get("pagina") or v.get("fonte") or "") if isinstance(v, dict) else str(v)
    grupos: dict[str, list] = {}
    for pasta_, rotulo in GRUPOS:
        d = p / pasta_
        if not d.is_dir():
            continue
        if pasta_ == "clipes":
            for q in sorted(d.glob("q-*")):
                prim = next(iter(sorted(q.glob("*.jpg"))), None)
                if prim:
                    grupos.setdefault(rotulo, []).append({"arquivo": f"clipes/{q.name}", "mini": rel(prim), "campo": "quadros_de",
                                                          "origem": q.name[2:]})
            continue
        for f in sorted(d.glob("*")):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                k = f"{pasta_}/{f.name}"
                if pasta_ == "prints" and (not orig.get(k) or "wiki" in (k + orig.get(k, "")).lower()):
                    continue   # print sem fonte anotada ou da Wikipédia não é oferecido (REGRAS.md G25)
                grupos.setdefault(rotulo, []).append({"arquivo": k, "mini": rel(f), "campo": "imagem", "origem": orig.get(k, "")})
    try:
        import gerar_ia
        gerados = gerar_ia.itens(p)
        if gerados:
            grupos["Gerados por IA"] = gerados
    except Exception:  # noqa: BLE001  (o material continua sem o que foi gerado)
        pass
    return [{"grupo": g, "itens": i} for g, i in grupos.items()]


def usar_material(p: Path, n: int, arquivo: str) -> None:
    """Troca a imagem (ou o clipe) da cena n pelo material escolhido, sem IA: grava, guarda a edição e gera o vídeo."""
    if estado(p).get("rodando"):
        raise ValueError("Já tem um pedido rodando neste vídeo. Espere terminar.")
    if not spec(p).get("material", True):
        raise ValueError("O material deste formato não troca por aqui: peça pelo Claude.")
    item = next((i for g in material(p) for i in g["itens"] if i["arquivo"] == arquivo), None)
    doc = _doc(p)
    if not item or not (1 <= n <= len(doc.get("cenas") or [])):
        raise ValueError("Escolha uma cena e um material da lista.")
    c = doc["cenas"][n - 1]
    campo = item["campo"]
    if campo == "imagem" and c.get("tipo") in ("clipe", "texto", "icone", "venn", "zap", "linha", "chips") and "imagem" not in c:
        c["tipo"] = "foto"   # cena sem foto que recebe foto vira foto (o texto dela, se tiver, fica por cima)
    if campo == "quadros_de":
        c.update(tipo="clipe", inicio=0)
        c.pop("imagem", None)
    c[campo] = arquivo
    if not estado(p).get("base"):
        _estado(p, base=guardar_versao(p, "original"))
    (p / "cenas.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    _anotar_edicao(p, {"escopo": "cena", "n": n, "campo": "", "texto": f"material: {arquivo}"}, doc)
    _estado(p, rodando=True, fase="Gerando o vídeo com o material novo", erro="", resumo="", log="")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "narracao", rel(p), "video"], cwd=RAIZ,
                     stdout=subprocess.DEVNULL, stderr=open(p / "editor" / "narracao.err", "w"), start_new_session=True,
                     env=com_venv())


def _resumo(raw: Path) -> str:
    """A última fala do Claude (o 'o que mudou')."""
    ult = ""
    for l in raw.read_text(encoding="utf-8", errors="ignore").splitlines() if raw.exists() else []:
        try:
            ev = json.loads(l)
        except ValueError:
            continue
        if ev.get("type") == "result" and ev.get("result"):
            ult = str(ev["result"])
    return ult.strip().splitlines()[-1][:300] if ult.strip() else ""


def ainda_nao() -> list[str]:
    """Títulos dos formatos gravados que ainda não têm edição por cena (a lista do /editar avisa, sem quebrar)."""
    try:
        import formatos
        return [f["titulo"] for f in formatos.listar() if f.get("tipo") == "gravado" and f["slug"] not in MOTORES]
    except Exception:  # noqa: BLE001
        return []


ESTILOS_QUE_SAIRAM = {"frase-fixa": "Frase fixa"}   # estilo removido do catálogo que ainda tem vídeo: o nome certo na lista


def titulo_do_estilo(p: Path) -> str:
    """O nome do estilo desta pasta pra mostrar ("Frase fixa" mesmo com o estilo fora do catálogo)."""
    try:
        import formatos
        f = formatos.de_modelo(p.parent.name)
        if f and f.get("titulo"):
            return f["titulo"]
    except Exception:  # noqa: BLE001
        pass
    return ESTILOS_QUE_SAIRAM.get(p.parent.name) or p.parent.name.replace("-", " ").capitalize()


def _entrada(p: Path, doc: dict | None, **extra) -> dict:
    vid = _video(p, doc) if doc else _saida(p)
    sb = p / "storyboard.jpg"
    f = fonte(p)
    return {"pasta": rel(p), "titulo": (doc or {}).get("titulo") or p.name.replace("_sandbox-", ""), "cliente": p.parents[3].name,
            "nome": p.name.replace("_sandbox-", ""), "arquivo": vid.name, "modelo": p.parent.name, "formato": formato_da_pasta(p) or p.parent.name, "formato_titulo": titulo_do_estilo(p),
            "video": rel(vid) if vid.is_file() else "", "capa": rel(sb) if sb.is_file() else "", "pode": True, "motivo": "",
            "quando": vid.stat().st_mtime if vid.is_file() else (f.stat().st_mtime if f.is_file() else p.stat().st_mtime), **extra}


def motivo_sem_edicao(p: Path) -> str:
    """Por que este vídeo pronto não edita por cena, em português simples ("" = edita)."""
    if (p / "cenas.json").is_file() and not gravado(p):   # (spec gravado com fonte cenas.json, como a Lista de estáticos, segue pelo gravado)
        return "" if _entende_quadro(p) else "O motor deste vídeo não desenha uma cena sozinha, então não dá pra mudar por cena."
    if not gravado(p):
        return "Montado à mão, sem o comando que refaz o vídeo."
    if not _cmd_gravado(p):
        return "Montado à mão, sem o comando que refaz o vídeo."
    if not fonte(p).is_file():
        return f"Falta o arquivo das cenas ({fonte(p).name})."
    falta = [Path(x).name if Path(x).is_absolute() else x for x in _precisa(p) if not (p / x).exists()]
    if falta:
        return "Faltam arquivos de trabalho: " + ", ".join(falta) + "."
    return ""


def videos() -> list[dict]:
    """Os vídeos que dá pra editar por cena: motor (cenas.json + render.py que aceita --quadro) e gravado (o spec reconhece a pasta,
    tem as fontes e o comando que refaz o vídeo); o mais novo primeiro. Vídeo pronto que NÃO dá pra editar entra na lista com
    `pode` False e o `motivo` em português (sem botão de editar)."""
    out = []
    for p in sorted((RAIZ / "clientes").glob("*/*Content/modelos/*/_sandbox-*")):
        if not p.is_dir() or p.is_symlink():
            continue
        try:
            motivo = motivo_sem_edicao(p)
            doc = _doc(p) if not motivo else None
        except (ValueError, OSError, IndexError, KeyError, TypeError):
            motivo, doc = "Não consegui ler as cenas deste vídeo.", None
        if not motivo:
            out.append(_entrada(p, doc))
        elif (p / "cenas.json").is_file() and "desenha" in motivo:
            continue   # motor antigo: nem aparece (como sempre foi)
        elif _saida(p).is_file():   # pronto, mas sem edição: aparece com o motivo
            out.append(_entrada(p, None, pode=False, motivo=motivo))
    return sorted(out, key=lambda x: (not x["pode"], -x["quando"]))

# ───────────────────────── a música de fundo (vale pro vídeo todo) ─────────────────────────
# O elemento "Música (vale pro vídeo todo)" do Editorial: troca a faixa (virais do momento, ou uma que o João procura), o ponto
# de entrada e o volume, e refaz o vídeo. Não passa pelo Claude: o Estúdio baixa, confere marca d'água, corta o refrão, refaz a
# grade da batida e encaixa os cortes nela (musica_viral.casar_cortes). 30-out-2026.

def _cliente_da_pasta(p: Path) -> str:
    try:
        return Path(p).resolve().relative_to((RAIZ / "clientes").resolve()).parts[0]
    except (ValueError, IndexError):
        return ""


def musica(p: Path) -> dict:
    """A música de agora e se dá pra trocar: {pode, motivo, atual: {titulo, artista, fonte, t0, abaixo_db, aviso, sem}, clima, texto, dur}."""
    s = spec(p)
    if not s.get("musica"):
        return {"pode": False, "motivo": "Este estilo não tem música de fundo."}
    doc = _doc(p)
    m = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    ponteiro = ler_json(p / "work" / "musica" / "escolhida.json", {}) or {}
    arq = str(m.get("arquivo") or "")
    atual = {"sem": not arq, "arquivo": arq, "titulo": m.get("titulo") or ponteiro.get("titulo") or (Path(arq).stem if arq else ""),
             "artista": m.get("artista") or ponteiro.get("artista") or "", "fonte": m.get("fonte") or ("viral" if arq.startswith("work/musica/viral-") else "banco"),
             "t0": m.get("t0"), "abaixo_db": m.get("abaixo_db"), "aviso": m.get("aviso") or ponteiro.get("aviso") or "",
             "previa": arq if arq and (p / arq).is_file() else ""}
    atual["previa_rel"] = rel(p / arq) if atual["previa"] else ""
    fala = " ".join(w.get("word", "") for w in _palavras(p, doc))
    clima = ""
    try:
        f = ler_json(RAIZ / "formatos" / formato_da_pasta(p) / "formato.json", {}) or {}
        clima = ((f.get("som") or {}).get("musica") or {}).get("clima", "")
    except Exception:  # noqa: BLE001
        pass
    return {"pode": True, "motivo": "", "atual": atual, "clima": clima, "texto": fala[:1500], "dur": float(doc.get("duracao") or 0),
            "cliente": _cliente_da_pasta(p), "rodando": bool(estado(p).get("rodando"))}


def trocar_musica(p: Path, faixa: str = "", entrada: float | None = None, abaixo_db: float | None = None, sem: bool = False) -> None:
    """Começa a troca em segundo plano (baixar, checar, cortar e refazer o vídeo leva uns minutos). `faixa` = id de `opcoes` ou link
    do YouTube; sem faixa nova só muda a entrada/o volume da que já toca (entrada pede a faixa de novo: usa a atual)."""
    if estado(p).get("rodando"):
        raise ValueError("Já tem um pedido rodando neste vídeo. Espere terminar.")
    if not musica(p)["pode"]:
        raise ValueError(musica(p)["motivo"])
    atual = musica(p)["atual"]
    if not sem and not faixa:
        if atual["sem"]:
            raise ValueError("Escolha uma música.")
        if entrada is None and abaixo_db is None:
            raise ValueError("Nada mudou: escolha outra música, outro ponto de entrada ou outro volume.")
    if abaixo_db is not None and not 8 <= float(abaixo_db) <= 30:
        raise ValueError("O volume da música fica entre 8 e 30 dB abaixo da voz.")
    (p / "editor").mkdir(exist_ok=True)
    gravar_json(p / "editor" / "musica-pedido.json", {"faixa": faixa, "entrada": entrada, "abaixo_db": abaixo_db, "sem": bool(sem)})
    _estado(p, rodando=True, fase="Trocando a música (baixa, confere se tem marca d'água, corta o refrão e refaz o vídeo)", erro="", resumo="", log="")
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "musica", rel(p)], cwd=RAIZ,
                     stdout=subprocess.DEVNULL, stderr=open(p / "editor" / "musica.err", "w"), start_new_session=True, env=com_venv())


def _rodar_musica(p: Path) -> int:
    import musica_viral as mv
    ped = ler_json(p / "editor" / "musica-pedido.json", {}) or {}
    if not estado(p).get("base"):
        _estado(p, base=guardar_versao(p, "original"))
    antes = fonte(p).read_text(encoding="utf-8")
    doc = _doc(p)
    velho = doc.get("musica") if isinstance(doc.get("musica"), dict) else {}
    cli = _cliente_da_pasta(p)
    try:
        dur = float(doc.get("duracao") or 75)
        if ped.get("sem"):
            doc["musica"] = {"volume": velho.get("volume", .08)}
            o_que = "sem música de fundo"
            nome = ""
        else:
            faixa = ped.get("faixa")
            if not faixa:   # só entrada/volume: a faixa que já toca
                faixa = {"artista": velho.get("artista", ""), "titulo": velho.get("titulo", ""), "slug": Path(str(velho.get("arquivo") or "")).stem,
                         "chave": mv.chave_musica(velho.get("artista", ""), velho.get("titulo", ""))}
            _estado(p, fase="Baixando a faixa e achando o refrão")
            pt = mv.preparar(p, faixa, dur, entrada=ped.get("entrada"), cliente=cli)
            m = {"arquivo": pt["arquivo"], "volume": velho.get("volume", .08), "inicio_s": 0, "titulo": pt["titulo"], "artista": pt["artista"],
                 "fonte": "viral", "chave": pt["chave"], "t0": pt["t0"], "aviso": pt["aviso"]}
            ab = ped.get("abaixo_db") if ped.get("abaixo_db") is not None else velho.get("abaixo_db")
            if ab is not None:
                m["abaixo_db"] = float(ab)
            doc["musica"] = m
            bat = ler_json(p / "work" / "batida.json", {}) or {}
            movidas = mv.casar_cortes(doc, float(bat.get("periodo") or 0))
            nome = f"{pt['artista']} - {pt['titulo']}"
            o_que = f"música: {nome} (entra em {pt['t0']:.0f} s da faixa; {movidas} cortes na batida nova)"
        _gravar(p, doc)
        _estado(p, fase="Gerando o vídeo novo")
        rr = _refazer_video(p)
        if rr.returncode:
            raise RuntimeError("o vídeo não saiu: " + (rr.stderr or rr.stdout)[-300:])
    except Exception as e:  # noqa: BLE001
        fonte(p).write_text(antes, encoding="utf-8")
        _estado(p, rodando=False, fase="", erro=f"A música nova não deu certo ({str(e)[:260]}). O vídeo ficou como estava.")
        return 1
    v = guardar_versao(p, o_que)
    av = entregar(p)
    try:
        import uso_midia as _uso
        j = job_da_pasta(p) or {}
        _uso.registrar_entrega(cli, formato_da_pasta(p), p.parent.name, j.get("slug") or p.name.removeprefix("_sandbox-"), p)
    except Exception:  # noqa: BLE001
        pass
    _estado(p, rodando=False, fase="", erro="", resumo=o_que[0].upper() + o_que[1:], avisos=[av] if av else [], versao=v)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["cenas"] and len(a) == 2:
        print(json.dumps(cenas(pasta(a[1]) or Path(a[1])), ensure_ascii=False, indent=1))
    elif a[:1] == ["narracao"] and len(a) in (2, 3):
        sys.exit(_rodar_narracao(pasta(a[1]), a[2] if len(a) == 3 else "voz"))
    elif a[:1] == ["musica"] and len(a) == 2:
        sys.exit(_rodar_musica(pasta(a[1])))
    elif a[:1] == ["rodar"] and len(a) == 3:
        sys.exit(rodar(pasta(a[1]), a[2]))
    else:
        print(__doc__)
