#!/usr/bin/env python3
"""
corte — ETAPA 0 do vídeo: transcreve o bruto e monta o corte (o "rough cut") sozinho.

O João grava corrido: erra, repete o take, para, recomeça, enrola no meio. Antes de pensar em beat,
alguém tem que escolher o que fica. Isto faz esse trabalho e devolve uma proposta pra ele aprovar.

Fluxo:
  1. `transcrever`  VERBATIM pelo Scribe (ElevenLabs, via helper do video-use) quando a chave existe;
                    senão GROQ whisper-large-v3. A diferença importa: o Whisper LIMPA o gaguejo, o
                    Scribe deixa ele escrito — e não dá pra cortar o que não aparece. → work/words.json
                    🔴 Os SEGMENTOS são remontados AQUI, a partir das PALAVRAS (nunca os do whisper):
                    o whisper gruda dois takes num segmento só (e às vezes engole letra), e aí o corte
                    não tem como separar a fala repetida da boa. Segmento = fala entre duas pausas reais.
  2. `medir`        espaço morto (auto-editor — github.com/WyattBlue/auto-editor, um cortador puro:
                    mede sonoridade e devolve o mapa; silencedetect fica só de reserva) e
                    repetições de frase (similaridade + n-grama)
  3. `propor_auto`  DETERMINÍSTICO, sem IA e sem gastar cota: marca take refeito, falso começo e erro
                    assumido usando a evidência medida. É o padrão.
                    🔴 Se houver ROTEIRO (work/roteiro.txt), ele é o GABARITO: a fala é alinhada com
                    o escrito, o que casa fica PROTEGIDO (o roteiro repete de propósito — era aí que
                    o corte comia a fala boa) e o que sobra sem par é tropeço. Take refeito se resolve
                    sozinho: o alinhamento casa uma das versões e deixa a outra sem par.
     `propor(..., com_ia=True)` manda a proposta pro Claude só quando o João pedir ajuda.
  4. `aplicar`      corta e concatena com ffmpeg, com micro-fade de áudio nas emendas.
                    Aqui também acontece o APERTO: pausa morta DENTRO de um trecho mantido é encurtada
                    (é o "muito fôlego" que o João ouve) — escolher o take não basta pro vídeo fluir.

CLI:
  corte.py transcrever <video> <pasta-work> [--cliente Joao] [--refazer] [--groq]
  corte.py medir <video> <pasta-work>
  corte.py verificar <pasta-work>               (sai 1 se sobrou repetição ou emenda gaguejando no corte)
  corte.py avulso-criar <video> [--titulo "..."] [--cliente Joao]   (cria a pasta do corte avulso, como a tela Só cortar)
  corte.py auto <video> <pasta-work> [--cliente Joao] [--briefing "..."] [--roteiro roteiro.txt] [--ia] [--refazer]
  corte.py propor <video> <pasta-work> ...      (mesmo que `auto`, em segundo plano)
  corte.py aplicar <video> <pasta-work>/CORTE.json <saida.mp4> [--respiro 0.3] [--aperto 0.7]
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import clonar as _clonar  # noqa: E402  (cópia que não gasta espaço no APFS)
from _comum import RAIZ, ensure, erro_simples, ffprobe, gravar_json, ler_json, now_slug

# Erro assumido. FORTES valem em qualquer lugar; FRACAS só num trecho curto — "espera" é interjeição
# em "peraí, espera" e é CONTEÚDO em "entre uma etapa e outra existe uma espera" (essa confusão já
# derrubou o take bom uma vez). Sempre casadas com limite de palavra, nunca como pedaço de palavra.
MARCADORES_FORTES = ["deixa eu começar de novo", "comecar de novo", "errei", "eu errei", "corta isso",
                     "corta essa", "de novo entao", "vamo de novo", "vamos de novo", "me perdi"]
MARCADORES_FRACOS = ["de novo", "pera", "perai", "espera", "caraca", "putz", "desculpa"]
MARCADORES = MARCADORES_FORTES + MARCADORES_FRACOS

# ── parâmetros do motor (todos em segundos) ──────────────────────────────────────────────────
PAUSA_SEG = 0.45      # pausa entre palavras que separa um segmento do outro
DUR_MAX_SEG = 8.0     # segmento nunca passa disso (senão vira bloco impossível de aprovar)
RESPIRO = 0.16        # pausa TOTAL na emenda, distribuída entre saída e entrada
APERTO = 0.55         # pausa confirmada acima disso é encurtada
APERTO_ALVO = 0.18    # preserva uma pausa curta, sem juntar sílabas
ENTRADA = 0.08        # proteção da consoante inicial, limitada ao intervalo livre
VERSAO_MOTOR = 'fala-fiel-2'


from _comum import _norm  # noqa: E402  (uma cópia só)

def _limpo(s: str) -> str:
    return re.sub(r"\s+", " ", _norm(s)).strip()


def _tem_marcador(texto: str) -> bool:
    """Marcador de erro assumido, com limite de palavra. Os fracos só contam em trecho curto."""
    t = _limpo(texto)
    if t in ('errei','eu errei','corta isso','corta essa','pera','perai'):return True
    if len(t.split())>12:return False
    return bool(re.match(r'^(?:(?:pera|perai|errei|eu errei)\s+)?(?:deixa eu comecar de novo|vamos de novo|vamo de novo|comecar de novo|de novo entao)(?:\s|$)',t))


def _cobertura(pa: list[str], pb: list[str]) -> float:
    """Quanto da fala `pa` reaparece, na ordem, dentro de `pb` (0 a 1) — comparando PALAVRAS.

    Comparar caractere a caractere não pega take refeito com outras palavras no meio
    ("ele avalia se a função contribuiu" → "avalia se a função QUE VOCÊ EXERCIA contribuiu").
    Por palavra, a segunda versão cobre a primeira e dá pra saber que é a mesma fala refeita.
    """
    if not pa:
        return 0.0
    casadas = sum(b.size for b in difflib.SequenceMatcher(None, pa, pb).get_matching_blocks())
    return casadas / len(pa)


def _parou_no_meio(video, js) -> bool:
    """A transcrição acabou mais de 3 s antes do fim do áudio (grupo-por-crenca-v2, 29-out-2026: parou em 27 s de 50)."""
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    try:
        dur = float(r.stdout.strip())
    except ValueError:
        return False
    ws = [w for w in js.get("words") or [] if str(w.get("word", "")).strip()]
    reais = [w for w in ws if w.get("end", 0) - w.get("start", 0) > .05] or ws
    if not reais:
        return False
    fim = float(reais[-1].get("end", 0))
    # a invenção do Groq tem cara: palavra(s) quase sem duração no fim, depois de um buraco (v3: "5 Campanhas" em 60,2 s
    # com a fala parada em 55,9 s e o áudio indo até 58,5 s)
    inventada = len(ws) > len(reais) and ws[-1] is not reais[-1] and float(ws[-1].get("start", 0)) - fim > 1.5
    return inventada or dur - fim > 3


def chave_groq(cliente: str = "Joao") -> str:
    """GROQ_API_KEY: app/.env > ambiente (cliente não tem .env; as chaves moram só em app/.env)."""
    import chaves
    return chaves.chave("GROQ_API_KEY", cliente, RAIZ)


# ───────────────────────────── transcrição fiel ─────────────────────────────

def _segmentar(palavras: list[dict], pausa: float = PAUSA_SEG, dur_max: float = DUR_MAX_SEG) -> list[dict]:
    """Segmento = fala entre duas pausas REAIS, montado palavra a palavra.

    🔴 Por que não usar os segmentos do whisper: ele junta dois takes num bloco só (aconteceu com
    "entre uma etapa e outra existe uma espera", dita duas vezes dentro do MESMO segmento de 17s).
    Quando isso acontece o corte não tem escolha: ou mantém a repetição, ou joga fora a fala boa
    junto. Cortando na pausa, cada take vira um segmento próprio e dá pra manter só o último.
    """
    grupos: list[list[dict]] = []
    atual: list[dict] = []
    for w in palavras:
        if atual:
            gap = w["t0"] - atual[-1]["t1"]
            dur = atual[-1]["t1"] - atual[0]["t0"]
            fim_de_frase = bool(re.search(r"[.!?…]$", atual[-1]["p"])) and dur >= 2.0
            if gap >= pausa or dur >= dur_max or fim_de_frase:
                grupos.append(atual); atual = []
        atual.append(w)
    if atual:
        grupos.append(atual)
    segs = []
    for i, g in enumerate(grupos):
        antes = round(g[0]["t0"] - grupos[i - 1][-1]["t1"], 2) if i else round(g[0]["t0"], 2)
        depois = round(grupos[i + 1][0]["t0"] - g[-1]["t1"], 2) if i + 1 < len(grupos) else None
        fim = g[-1]["t1"]
        if i + 1 < len(grupos):
            fim = min(fim, grupos[i + 1][0]["t0"])
        segs.append({"i": i, "t0": round(g[0]["t0"], 2), "t1": round(max(fim, g[0]["t0"] + 0.05), 2),
                     "texto": " ".join(w["p"] for w in g).strip(),
                     "palavras": len(g), "pausa_antes": max(0.0, antes),
                     "pausa_depois": (max(0.0, depois) if depois is not None else None)})
    return segs


# ── transcrição VERBATIM (ElevenLabs Scribe, pelo helper do video-use) ───────────────────────
# O GROQ Whisper NORMALIZA o gaguejo: o "é…", o "hum", a sílaba repetida somem do texto. Medido no
# bruto do Cliente3 (IMG_9961): ZERO ocorrência de vício de linguagem em 209 palavras de 138s. E não
# dá pra cortar o que não aparece escrito — por isso a caça a take refeito aqui compara frases
# inteiras, nunca a gagueira em si. O Scribe transcreve verbatim e o tropeço aparece.
# Quem fala com a ElevenLabs é o helper do video-use (github.com/browser-use/video-use), não a gente.

VIDEO_USE = Path.home() / "Developer" / "video-use"


def _scribe_ligado() -> bool:
    """"Transcrição verbatim paga" (config.json → transcricao_verbatim_paga) vem desligada: o padrão da 2.0 é só o GROQ."""
    try:
        from _comum import ESTUDIO
        return bool((ler_json(ESTUDIO / "config.json", {}) or {}).get("transcricao_verbatim_paga"))
    except Exception:
        return False


def scribe_pronto() -> bool:
    """Scribe ligado em Configurações E video-use instalado E chave da ElevenLabs? Sem isso o corte transcreve com o GROQ (grátis)."""
    return _scribe_ligado() and ((VIDEO_USE / "helpers" / "transcribe.py").exists()
            and ((VIDEO_USE / ".env").exists() or bool(os.environ.get("ELEVENLABS_API_KEY"))))


def _scribe(video: Path, work: Path) -> dict | None:
    """Roda o helper do video-use e devolve as palavras no formato do corte, ou None se não deu."""
    if not scribe_pronto():
        return None
    py = VIDEO_USE / ".venv" / "bin" / "python"
    saida_dir = ensure(work / "scribe")
    try:
        r = subprocess.run([str(py if py.exists() else sys.executable),
                            str(VIDEO_USE / "helpers" / "transcribe.py"), str(video),
                            "--edit-dir", str(saida_dir)],
                           capture_output=True, text=True, timeout=1800)
        arq = saida_dir / "transcripts" / f"{video.stem}.json"
        if r.returncode or not arq.exists():
            return None
        js = json.loads(arq.read_text() or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    # O Scribe intercala type=word com type=spacing (e audio_event). Só a palavra tem conteúdo.
    palavras = [{"word": w.get("text", ""), "start": w.get("start"), "end": w.get("end")}
                for w in js.get("words", [])
                if w.get("type") == "word" and w.get("start") is not None and w.get("text", "").strip()]
    if len(palavras) < 5:
        return None
    return {"words": palavras, "motor": "scribe-verbatim",
            "idioma": js.get("language_code"), "duracao_audio_s": js.get("audio_duration_secs")}


def _fonte(video: Path) -> dict:
    """De qual vídeo é a transcrição: nome e tamanho (o mesmo arquivo movido de pasta continua valendo)."""
    try:
        return {"arquivo": Path(video).name, "bytes": Path(video).stat().st_size}
    except OSError:
        return {"arquivo": Path(video).name}


def _de_outro_video(words_p: Path, video: Path) -> str:
    """'' se o words.json guardado é deste vídeo (ou não dá pra saber); senão, de qual ele é. Com "fonte" (gravado daqui
    em diante) compara nome e tamanho; sem ela (transcrição antiga), compara a duração do áudio com a do vídeo."""
    js = ler_json(words_p, {}) or {}
    if not isinstance(js, dict) or not Path(video).is_file():
        return ""
    f = js.get("fonte")
    if isinstance(f, dict) and f.get("arquivo"):
        agora = _fonte(video)
        if f.get("arquivo") != agora.get("arquivo") or (f.get("bytes") and agora.get("bytes") and f["bytes"] != agora["bytes"]):
            return str(f.get("arquivo"))
        return ""
    dur = js.get("duracao_audio_s") or js.get("duration")
    try:
        dv = float(ffprobe(video).get("duracao") or 0)
        if dur and dv and abs(float(dur) - dv) > max(3.0, .05 * dv):   # folga larga: só pega vídeo de outro tamanho
            return f"um vídeo de {float(dur):.1f} s (este tem {dv:.1f} s)"
    except (TypeError, ValueError):
        pass
    return ""


def transcrever(video: Path, work: Path, cliente: str = "Joao", refazer: bool = False, motor: str = "") -> list[dict]:
    """Palavras com tempo. Scribe verbatim se der; GROQ senão (motor="groq" força o GROQ). Reaproveita (--refazer ignora o cache).

    Guarda words.json (palavras, a fonte da verdade, com "fonte": de qual vídeo), segmentos-whisper.json (o que o whisper
    achou, só pra conferência) e segmentos.json (o nosso, remontado pelas pausas — é o que o corte usa).
    A transcrição guardada de OUTRO vídeo nunca é devolvida como se fosse desta (o vídeo cortado na mesma pasta work/
    devolvia a fala do bruto, com os tempos errados): sem corte na pasta, ela vai pra _transcricao-anterior-<data>/ e
    transcreve de novo; com CORTE.json (o corte do bruto é dessa transcrição), para com erro em vez de estragar o corte.
    """
    work = ensure(work)
    segs_p, words_p = work / "segmentos.json", work / "words.json"
    if refazer:
        for p in (segs_p, words_p, work / "medidas.json", work / "segmentos-whisper.json", work / "CORTE.json"):
            p.unlink(missing_ok=True)
    outro = _de_outro_video(words_p, video) if words_p.exists() else ""
    if outro:
        if (work / "CORTE.json").exists():
            raise RuntimeError(f"A transcrição em {work} é de outro vídeo ({outro}) e o corte dessa pasta depende dela. "
                               f"Transcreva {Path(video).name} em outra pasta (ex.: {work}/fala) ou use --refazer.")
        guarda = ensure(work / f"_transcricao-anterior-{now_slug()}")
        for p in (segs_p, words_p, work / "medidas.json", work / "segmentos-whisper.json"):
            if p.exists():
                shutil.move(str(p), str(guarda / p.name))
    if segs_p.exists():
        return ler_json(segs_p, [])
    if not words_p.exists() and motor != "groq":
        verbatim = _scribe(video, work)
        if verbatim:
            gravar_json(words_p, {**verbatim, "fonte": _fonte(video)})
    if not words_p.exists():
        chave = chave_groq(cliente)
        if not chave:
            raise RuntimeError("GROQ_API_KEY não encontrada no app/.env")
        import vocabulario
        from fala import groq_transcrever
        dica = vocabulario.prompt(cliente)   # identidade.json -> "palavras": nome próprio certo na transcrição (G5)
        js = groq_transcrever(video, chave, dica)
        if dica and _parou_no_meio(video, js):   # com a lista de palavras no prompt o Groq às vezes inventa ("5 Campanhas") e para no meio
            js = groq_transcrever(video, chave, "")
        vocabulario.corrigir_lista(js.get("words") or [], vocabulario.palavras(cliente))   # "black" → "Black"
        js["motor"] = "groq-whisper"
        js["fonte"] = _fonte(video)
        gravar_json(words_p, js)
    js = ler_json(words_p, {}) or {}
    gravar_json(work / "segmentos-whisper.json",
                [{"i": i, "t0": round(s["start"], 2), "t1": round(s["end"], 2), "texto": s["text"].strip()}
                 for i, s in enumerate(js.get("segments", []) if isinstance(js,dict) else [])])
    segs = _segmentar(_palavras(work))
    if not segs:                                  # sem palavra com tempo: cai pro whisper
        segs = [{"i": i, "t0": round(s["start"], 2), "t1": round(s["end"], 2), "texto": s["text"].strip(),
                 "palavras": len(s["text"].split()), "pausa_antes": 0.0, "pausa_depois": None}
                for i, s in enumerate(js.get("segments", []) if isinstance(js,dict) else [])]
    gravar_json(segs_p, segs)
    return segs


def _palavras(work: Path) -> list[dict]:
    """Lista de palavras com tempo (do words.json do GROQ), pra cortar exato onde a fala começa."""
    js = ler_json(Path(work) / "words.json", {}) or {}
    rows=js.get('words',[]) if isinstance(js,dict) else js
    ws=[]
    for w in rows:
        try:
            a=float(w.get('start',w.get('t0')));b=float(w.get('end',w.get('t1',a)))
            text=str(w.get('word') or w.get('p') or w.get('text') or '').strip()
            if text and 0<=a<=b<1e9:ws.append({'t0':a,'t1':b,'p':text})
        except (TypeError,ValueError):continue
    return sorted(ws,key=lambda w:(w['t0'],w['t1']))


# ───────────────────────────── medição (evidência objetiva) ─────────────────────────────

def repeticoes_palavra(palavras: list[dict], n: int = 5, janela: float = 45.0) -> list[dict]:
    """Acha take refeito comparando SEQUÊNCIAS DE PALAVRAS, não segmentos.

    A comparação por segmento falha quando a frase repetida cai em blocos diferentes da transcrição
    (o caso em que o corte deixava duplicata passar). Aqui varre n-gramas de `n` palavras: se a mesma
    sequência reaparece dentro de `janela` segundos, é quase sempre take refeito ou falso começo.
    """
    ws = [w for w in palavras if w.get("t0") is not None and _limpo(w.get("p", ""))]
    if len(ws) < n * 2:
        return []
    chaves: dict[str, list[int]] = {}
    for i in range(len(ws) - n + 1):
        k = " ".join(_limpo(w["p"]) for w in ws[i:i + n])
        chaves.setdefault(k, []).append(i)
    brutos = []
    for k, pos in chaves.items():
        if len(pos) < 2:
            continue
        for a, b in zip(pos, pos[1:]):
            if 0 < ws[b]["t0"] - ws[a]["t0"] <= janela:
                brutos.append({"a0": ws[a]["t0"], "a1": ws[min(a + n - 1, len(ws) - 1)]["t1"],
                               "b0": ws[b]["t0"], "b1": ws[min(b + n - 1, len(ws) - 1)]["t1"],
                               "texto": k, "ia": a, "ib": b})
    brutos.sort(key=lambda x: (x["ia"], x["ib"]))
    # funde n-gramas vizinhos (uma frase repetida gera vários n-gramas em sequência)
    fund: list[dict] = []
    for r in brutos:
        f = fund[-1] if fund else None
        if f and r["ia"] <= f["ia_fim"] + n and r["ib"] <= f["ib_fim"] + n and abs((r["ib"] - r["ia"]) - (f["ib"] - f["ia"])) <= n:
            f["a1"] = max(f["a1"], r["a1"]); f["b1"] = max(f["b1"], r["b1"])
            f["ia_fim"], f["ib_fim"] = r["ia"], r["ib"]
            f["palavras"] += 1
        else:
            fund.append({**r, "ia_fim": r["ia"], "ib_fim": r["ib"], "palavras": n})
    saida = []
    for f in fund:
        if f["palavras"] < n:
            continue
        saida.append({"primeira_vez": [round(f["a0"], 2), round(f["a1"], 2)],
                      "segunda_vez": [round(f["b0"], 2), round(f["b1"], 2)],
                      "palavras": f["palavras"],
                      "intervalo_s": round(f["b0"] - f["a0"], 1),
                      "texto": f["texto"]})
    saida.sort(key=lambda x: -x["palavras"])
    return saida[:40]


def verificar(work: Path, corte: dict | None = None) -> dict:
    """Rede de segurança: depois da proposta, checa se SOBROU duplicata nos trechos mantidos."""
    work = Path(work)
    d = corte or ler_json(work / "CORTE.json", {}) or {}
    palavras = _palavras(work)
    mantidos = [s for s in d.get("segmentos", []) if s.get("manter")]
    dentro = []
    for w in palavras:
        if any(s["t0"] - 0.05 <= w["t0"] <= s["t1"] + 0.05 for s in mantidos):
            dentro.append(w)
    rep = repeticoes_palavra(dentro, n=4, janela=60.0)
    from corte_qualidade import continuidade
    emendas = emendas_gaguejando(sorted(mantidos, key=lambda x: x["t0"]), palavras)
    base = continuidade(d)
    # O gaguejo sai no render, não no `manter` do trecho. Se o texto da tela ignorar isso, ele lê
    # "Com um profissional, com um profissional" e reprova um corte que no vídeo está limpo.
    gag = ler_json(work / "gaguejos.json", []) or []
    if gag:
        sobrou = [w for w in dentro
                  if not any(g["t0"] - 0.03 <= (w["t0"] + w["t1"]) / 2 <= g["t1"] + 0.03 for g in gag)]
        segundos = round(sum(g["t1"] - g["t0"] for g in gag), 1)
        base = {**base, "roteiro": " ".join(w["p"] for w in sobrou),
                "nota": f"{base.get('nota') or ''} Já sem o gaguejo: "
                        f"{len(gag)} tropeço(s), {segundos}s.".strip()}
    return {**base, "duplicatas_restantes": rep, "n": len(rep), "emendas": emendas,
            "duracao_mantida_s": round(sum(s["t1"] - s["t0"] for s in mantidos), 1)}


# ── espaço morto: quem mede é o auto-editor ──────────────────────────────────────────────────
# github.com/WyattBlue/auto-editor. Ele é SÓ um cortador: analisa a sonoridade e devolve o mapa do
# "dead space", sem tocar em transcrição, take repetido, beat ou render. Fica com a parte que o gate
# fixo de -32dB fazia pior — perdia respiro baixo e às vezes partia um buraco em dois. Escolher o
# take, aparar gaguejo e emendar continua sendo daqui.
AE_LIMIAR = "4%"      # --edit audio:threshold — abaixo disso é espaço morto


def _auto_editor() -> str | None:
    """Executável do auto-editor, ou None — sem ele o corte cai no silencedetect e segue rodando."""
    exe = shutil.which("auto-editor")
    if exe:
        return exe
    for c in sorted(Path.home().glob("Library/Python/*/bin/auto-editor")) + [Path.home() / ".local/bin/auto-editor"]:
        if c.exists():
            return str(c)
    return None


def _silencios_ae(video: Path, minimo: float) -> list[dict] | None:
    """Mapa de espaço morto pelo auto-editor (`--export v1`: [frame0, frame1, velocidade])."""
    exe = _auto_editor()
    fps = float(ffprobe(video).get("fps") or 0)
    if not exe or not fps:
        return None
    # --margin 0s de propósito: aqui se quer o buraco CRU. A margem de cortesia quem dá é o `alvo`
    # do aperto, que já preserva uma pausa curta e é protegido pelos intervalos das palavras.
    with tempfile.TemporaryDirectory() as td:
        saida = Path(td) / "ae.json"
        try:
            r = subprocess.run([exe, str(video), "--edit", f"audio:threshold={AE_LIMIAR}",
                                "--margin", "0s", "--export", "v1", "-o", str(saida)],
                               capture_output=True, text=True, timeout=900)
            if r.returncode or not saida.exists():
                return None
            chunks = (json.loads(saida.read_text() or "{}") or {}).get("chunks") or []
        except Exception:
            return None
    return sil_de_chunks(chunks, fps, minimo)


def sil_de_chunks(chunks: list, fps: float, minimo: float = 0.25) -> list[dict]:
    """Chunks do auto-editor → silêncios em segundos. Velocidade 1.0 é fala; 99999 é espaço morto."""
    sil = []
    for pedaco in chunks or []:
        try:
            f0, f1, vel = float(pedaco[0]), float(pedaco[1]), float(pedaco[2])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if vel < 99999 or not fps:
            continue
        t0, t1 = f0 / fps, f1 / fps
        if t1 - t0 < minimo:
            continue
        sil.append({"t0": round(t0, 2), "t1": round(t1, 2), "duracao": round(t1 - t0, 2)})
    return sil


def silencios(video: Path, minimo: float = 0.25) -> list[dict]:
    """Todos os silêncios do bruto (não só os longos) — o aperto precisa dos curtos também."""
    ae = _silencios_ae(video, minimo)
    if ae is not None:
        return ae
    return _silencios_ffmpeg(video, minimo)


def _silencios_ffmpeg(video: Path, minimo: float = 0.25) -> list[dict]:
    """Reserva, pra máquina sem auto-editor instalado."""
    r = subprocess.run(["ffmpeg", "-nostdin", "-i", str(video), "-af", f"silencedetect=n=-32dB:d={minimo}",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    sil, ini = [], None
    for l in (r.stderr or "").splitlines():
        a = re.search(r"silence_start: (-?[\d.]+)", l)
        b = re.search(r"silence_end: ([\d.]+).*silence_duration: ([\d.]+)", l)
        if a:
            ini = float(a.group(1))
        elif b and ini is not None:
            sil.append({"t0": round(max(0, ini), 2), "t1": round(float(b.group(1)), 2),
                        "duracao": round(float(b.group(2)), 2)})
            ini = None
    return sil


def medir(video: Path, work: Path, segs: list[dict] | None = None) -> dict:
    """Silêncios longos e frases repetidas — evidência objetiva pra decidir sem chutar."""
    segs = segs if segs is not None else ler_json(work / "segmentos.json", [])
    sil = silencios(video)
    repet = []
    for i, s in enumerate(segs):
        a = _limpo(s["texto"])
        if len(a.split()) < 4:
            continue
        for j in range(i + 1, min(i + 12, len(segs))):
            b = _limpo(segs[j]["texto"])
            if len(b.split()) < 4:
                continue
            r2 = difflib.SequenceMatcher(None, a, b).ratio()
            if r2 > 0.72:
                repet.append({"primeiro": i, "segundo": j, "semelhanca": round(r2, 2),
                              "texto": s["texto"][:110]})
                break
    marcados = [{"i": s["i"], "t0": s["t0"], "texto": s["texto"]} for s in segs if _tem_marcador(s["texto"])]
    d = {"silencios": sil[:400],
         "silencios_longos": [x for x in sil if x["duracao"] >= 1.0][:60],
         "repeticoes": repet[:40], "marcadores_de_erro": marcados[:30],
         "repeticoes_palavra": repeticoes_palavra(_palavras(work)),
         "duracao_s": ffprobe(video).get("duracao"), "n_segmentos": len(segs)}
    gravar_json(work / "medidas.json", d)
    return d


# ───────────────────────── proposta determinística (sem IA, sem cota) ─────────────────────────

def _fora_por_repeticao(segs: list[dict], janela_s: float = 95.0, adiante: int = 18) -> dict[int, str]:
    """Take refeito e falso começo: fica a ÚLTIMA versão, sai a anterior.

    Duas checagens no mesmo par (i, j): texto quase igual (take refeito) e texto de i sendo o começo
    de j (falso começo — ele parou no meio e recomeçou a mesma frase completando).
    """
    fora: dict[int, str] = {}
    for i, a in enumerate(segs):
        ta = _limpo(a["texto"])
        pa = ta.split()
        if len(pa) < 3:
            continue
        for j in range(i + 1, min(i + adiante, len(segs))):
            b = segs[j]
            if b["t0"] - a["t1"] > janela_s:
                break
            tb = _limpo(b["texto"])
            if len(tb.split()) < 3:
                continue
            pb = tb.split()
            if _tem_marcador(b['texto']):continue  # a última versão também pode estar errada
            # Negação, quantidade e condição mudam o sentido: "não é do dia pra noite" e "é do dia
            # pra noite" são parecidíssimas e dizem o contrário. Só compara quem tem a mesma assinatura.
            protegidas={'nao','nunca','jamais','sem','nenhum','ninguem','so','sempre','talvez','se'}
            assinatura=lambda ps:[p for p in ps if p in protegidas or p.isdigit()]
            if assinatura(pa)!=assinatura(pb):continue
            # Repetição comprovada SAI. Ele grava corrido e refaz o take sem avisar "errei", e a
            # segunda versão costuma vir 10-20s depois: exigir marcador falado ou vizinhança deixava
            # o corte inteiro passar (21 de 21 trechos ficando, com 7 repetições na cara).
            if ta == tb or difflib.SequenceMatcher(None, ta, tb).ratio() > 0.75:
                fora[i] = f"take refeito — ele repete essa fala em {b['t0']}s; fica a última versão"
                break
            if len(pa) >= 4 and _cobertura(pa, pb) >= 0.7:
                fora[i] = f"tentativa refeita — ele diz isso tudo de novo, mais completo, em {b['t0']}s"
                break
            if len(pb) > len(pa) and pb[:len(pa)] == pa and not re.search(r'[.!?]$', a['texto'].strip()):
                fora[i] = f"falso começo — ele para no meio e completa a frase em {b['t0']}s"
                break
    return fora


# ═════════════════ O ROTEIRO COMO GABARITO ═════════════════
# Cortar "frase repetida" sem gabarito é chute. O roteiro REPETE DE PROPÓSITO ("você não precisa de
# X. Você não precisa de Y.") e era aí que o corte comia a fala boa. Com o roteiro na mão dá pra
# separar as duas coisas, e são perguntas diferentes:
#
#   1. ELE REPETIU PORQUE ESTAVA ESCRITO?  Conta quantas vezes a frase aparece no ROTEIRO. Duas ou
#      mais → a repetição é do texto, não é take refeito: a regra de repetição não derruba.
#      Uma só → ele gravou duas vezes o que estava escrito uma: é take refeito mesmo, e sai.
#   2. ISSO ESTAVA ESCRITO EM ALGUM LUGAR?   Alinha a fala com o roteiro (alinhamento de diff). O que
#      sobra sem par não é roteiro nenhum — é gaguejo, fragmento solto e enrolação, e sai.
#
# A cobertura do alinhamento NÃO serve pra proteger: num falso começo ("Primeira, se o serviço…" /
# "Primeira, se o serviço que você fazia…") o alinhamento casa a PRIMEIRA versão e deixa a cauda da
# segunda sem par — proteger por cobertura salvaria justamente o falso começo. Quem protege é a
# contagem no roteiro (1), que não depende de qual das versões o alinhador escolheu.

FORA_ROTEIRO = 0.20      # cobertura abaixo disso não é roteiro nenhum — é tropeço
CONFIA_ROTEIRO = 0.60    # o roteiro precisa aparecer tanto assim no bruto pra mandar em alguma coisa
IGUAL_ROTEIRO = 0.75     # semelhança que conta como "essa frase está no roteiro" (mesma da repetição)


def _tokens(texto: str) -> list[str]:
    return [t for t in _limpo(texto).split() if t]


def vezes_no_roteiro(texto: str, escrito: list[str], limiar: float = IGUAL_ROTEIRO) -> int:
    """Quantas vezes essa fala aparece no roteiro — é o que separa anáfora de take refeito."""
    pa = _tokens(texto)
    if len(pa) < 3 or len(escrito) < len(pa):
        return 0
    alvo = " ".join(pa)
    achados, k = 0, 0
    while k <= len(escrito) - len(pa):
        if difflib.SequenceMatcher(None, alvo, " ".join(escrito[k:k + len(pa)])).ratio() > limiar:
            achados += 1
            k += len(pa)      # não conta a mesma ocorrência deslizando de uma palavra
        else:
            k += 1
    return achados


def conferir_roteiro(palavras: list[dict], segs: list[dict], roteiro: str) -> dict:
    """Alinha a fala com o roteiro e devolve, por trecho, quanto dele estava escrito.

    `confiavel` é a trava de segurança: se o roteiro colado não aparece no bruto (roteiro errado,
    outro vídeo, transcrição ruim), ele não manda em nada e o corte segue só com a medição.
    """
    falado = [_limpo(w.get("p") or w.get("word") or "") for w in palavras]
    escrito = _tokens(roteiro)
    vazio = {"confiavel": False, "cobertura": 0.0, "por_segmento": {},
             "n_roteiro": len(escrito), "tokens": escrito}
    if len(escrito) < 8 or not falado:
        return vazio

    # autojunk=False: com fala longa o heurístico de "palavra popular demais" do difflib descarta
    # justamente os artigos e preposições que costuram a frase, e o alinhamento desanda.
    casadas: set[int] = set()
    cobertas = 0
    for a, _b, n in difflib.SequenceMatcher(None, falado, escrito,
                                            autojunk=False).get_matching_blocks():
        if not n:
            continue
        casadas.update(range(a, a + n))
        cobertas += n
    cobertura = cobertas / len(escrito)

    por_seg: dict[int, float] = {}
    for s in segs:
        idx = [k for k, w in enumerate(palavras)
               if s["t0"] - 0.05 <= (w["t0"] + w.get("t1", w["t0"])) / 2 <= s["t1"] + 0.02]
        if idx:
            por_seg[s["i"]] = round(sum(1 for k in idx if k in casadas) / len(idx), 2)
    return {"confiavel": cobertura >= CONFIA_ROTEIRO, "cobertura": round(cobertura, 2),
            "por_segmento": por_seg, "n_roteiro": len(escrito), "tokens": escrito}


def ler_roteiro(work: Path, roteiro: str = "") -> str:
    """Guarda o roteiro na work (ou lê o que já estava lá) — o corte roda de novo sem recolar."""
    alvo = work / "roteiro.txt"
    if roteiro and roteiro.strip():
        p = Path(roteiro)
        try:
            texto = p.read_text() if (len(roteiro) < 400 and p.is_file()) else roteiro
        except OSError:
            texto = roteiro
        alvo.write_text(texto.strip())
        return texto.strip()
    return alvo.read_text().strip() if alvo.exists() else ""


# ═════════════════ GAGUEJO NO NÍVEL DA PALAVRA ═════════════════
# O que o João descreveu: "ele fala três palavras, erra, e volta a repetir"; "embala numa frase só e
# erra no final, aí tem que voltar". Isso acontece DENTRO de um trecho, e a regra de repetição de
# segmento é cega pra isso — ela compara trechos inteiros, então "Com um profissional, com um
# profissional indicado" passa batido porque é tudo um segmento só.
#
# Aqui a comparação é palavra a palavra, e o que sai é a tentativa ABORTADA (fica sempre a última,
# que é a completa). Duas evidências:
#   • palavra cortada no meio — o Scribe marca com "--" ("afas--", "fu--"). É gaguejo, ponto.
#   • um punhado de palavras repetido logo em seguida ("Depois a," → "depois a ação ela é preparada").
#
# 🔴 A âncora (mesma palavra inicial nas duas pontas) não é detalhe: sem ela o casamento escorrega e
# come a cauda da frase boa anterior — na primeira versão isso comeu "de fato perdida." inteiro.
# 🔴 A janela é CURTA (poucas palavras e poucos segundos entre uma versão e outra). É ela que separa
# gaguejo de anáfora: no roteiro, "Você não precisa de X / Você não precisa de Y" tem uma frase
# inteira no meio e fica fora da janela.

GAG_GAP = 5          # quantas palavras podem aparecer entre a tentativa e a repetição (perto)
GAG_MIN = 2          # repetição de menos palavras que isso é ruído
GAG_MAX = 14
GAG_LIMIAR = 0.80    # semelhança entre as duas sequências de palavras
GAG_ANCORA = 0.80    # semelhança exigida da PRIMEIRA palavra das duas
GAG_SEG = 3.5        # segundos no máximo entre a tentativa e a repetição (perto)
GAG_LONGE_MIN = 5    # na janela larga, só sequência LONGA conta — curta ali é coincidência
GAG_LONGE_SEG = 75.0 # ele refaz o take meio minuto depois; 3,5s não alcança isso

TRUNCADA = re.compile(r"-{1,2}\s*$")


def _tok(w: dict) -> str:
    return _norm(w.get("p") or w.get("word") or "").replace(" ", "")


def _enumeracao(a: list[str], b: list[str], fim_a: float, ini_b: float) -> bool:
    """A termina numa palavra inteira diferente da de B (uma não é começo da outra) com pausa < 0,3 s: é enumeração, não gaguejo."""
    if not a or not b:
        return False
    x, y = a[-1], b[-1]
    if not x or not y or x == y or x.startswith(y) or y.startswith(x):
        return False
    return (ini_b - fim_a) < 0.3


def _perto(W: list[dict], T: list[str], gap: int, n_min: int, n_max: int,
           limiar: float, ancora: float, seg: float, protegido=None) -> list[dict]:
    """Gaguejo colado: ele fala, tropeça e recomeça na mesma respirada."""
    fora, i = [], 0
    while i < len(W):
        texto = str(W[i].get("p") or W[i].get("word") or "")
        if TRUNCADA.search(texto):                    # palavra cortada no meio: sai sozinha
            fora.append({"t0": round(W[i]["t0"], 3), "t1": round(W[i]["t1"], 3),
                         "texto": texto, "motivo": "palavra cortada no meio"})
            i += 1
            continue
        achou = False
        for n in range(min(n_max, len(W) - i), n_min - 1, -1):
            a = T[i:i + n]
            if sum(len(x) for x in a) < 3:
                continue
            for j in range(i + n, min(i + n + gap + 1, len(W) - n + 1)):
                if W[j]["t0"] - W[i + n - 1]["t1"] > seg:
                    break
                if difflib.SequenceMatcher(None, T[i], T[j]).ratio() < ancora:
                    continue
                b = T[j:j + n]
                # Duas leituras da mesma comparação. Palavra a palavra é a boa quando ele repete
                # igual; mas quando a tentativa morre no meio da palavra ("históricos de afas--" vs
                # "histórico de afastamento") nenhuma das duas últimas casa e o par escapa — aí vale
                # a comparação por letra, que enxerga o pedaço. A âncora segura as duas.
                if (difflib.SequenceMatcher(None, a, b).ratio() >= limiar
                        or difflib.SequenceMatcher(None, "".join(a), "".join(b)).ratio() >= limiar):
                    if _enumeracao(T[i:j], T[j:j + (j - i)], W[j - 1]["t1"], W[j]["t0"]):   # "é uma reação X, é uma reação Y": repetição de propósito
                        continue
                    if not _refeito(T, i, j, por_letra=True):   # o que sai tem que voltar logo depois
                        continue
                    if protegido and protegido(i, j, n):
                        i, achou = j, True       # estava no roteiro: pula sem cortar
                        break
                    dito = " ".join(str(x.get("p") or x.get("word") or "") for x in W[i:j])
                    fora.append({"t0": round(W[i]["t0"], 3), "t1": round(W[j - 1]["t1"], 3),
                                 "texto": dito, "motivo": "ele recomeça essa fala logo em seguida"})
                    i, achou = j, True
                    break
            if achou:
                break
        if not achou:
            i += 1
    return fora


GAG_LONGE_COBRE = 0.6  # parte do trecho cortado que precisa reaparecer no take refeito


def _refeito(T: list[str], i: int, j: int, por_letra: bool = False) -> bool:
    """O trecho T[i:j] foi mesmo refeito a partir de j? Mede quanto dele reaparece, em ordem, logo depois.
    por_letra: a tentativa pode morrer no meio da palavra ("afas--" → "afastamento"), então compara as letras."""
    sai = T[i:j]
    volta = T[j:j + len(sai) + 10]
    if por_letra:
        sai, volta = "".join(sai), "".join(volta)[:len("".join(sai)) + 12]
    casou = sum(b.size for b in difflib.SequenceMatcher(None, sai, volta, autojunk=False).get_matching_blocks())
    return casou >= GAG_LONGE_COBRE * len(sai)


def _longe(W: list[dict], T: list[str], n_min: int, n_max: int, limiar: float,
           seg: float, protegido=None) -> list[dict]:
    """Take refeito: ele erra no fim da frase, para, e refaz a passagem INTEIRA meio minuto depois.

    A regra de segmento é cega pra isso quando o refeito não bate com a fronteira do trecho — foi o
    que deixou passar "Com um profissional… indicado pela Justiça" e "Achar que parou quando está…".
    Aqui a âncora é palavra EXATA (na janela larga não dá pra ser tolerante) e a sequência tem que
    ser longa; o índice por primeira palavra é o que mantém isso rápido em vídeo comprido.
    """
    onde: dict[str, list[int]] = {}
    for k, t in enumerate(T):
        onde.setdefault(t, []).append(k)
    fora, i = [], 0
    while i < len(W) - n_min:
        achou = False
        for n in range(min(n_max, len(W) - i), n_min - 1, -1):
            a = T[i:i + n]
            if sum(len(x) for x in a) < 12:
                continue
            for j in onde.get(T[i], []):
                if j < i + n:
                    continue
                if W[j]["t0"] - W[i + n - 1]["t1"] > seg:
                    break
                if j + n > len(W):
                    continue
                if difflib.SequenceMatcher(None, a, T[j:j + n]).ratio() < limiar:
                    continue
                # 🔴 Expressão comum não é take refeito: "cê vai ter que contar…" (2s) e "cê vai ter que
                # entender…" (65s) casavam 4 de 5 e o corte comeu 62s de fala boa. O que sai tem que
                # voltar a ser dito, em boa parte, logo depois de j.
                if not _refeito(T, i, j):
                    continue
                if protegido and protegido(i, j, n):
                    i, achou = j, True           # estava no roteiro: pula sem cortar
                    break
                dito = " ".join(str(x.get("p") or x.get("word") or "") for x in W[i:j])
                fora.append({"t0": round(W[i]["t0"], 3), "t1": round(W[j - 1]["t1"], 3),
                             "texto": dito, "motivo": f"ele refaz essa passagem em {W[j]['t0']:.0f}s"})
                i, achou = j, True
                break
            if achou:
                break
        if not achou:
            i += 1
    return fora


def _do_roteiro(W: list[dict], T: list[str], i: int, j: int, n: int, escrito: list[str]) -> bool:
    """A repetição estava escrita? Compara o COMEÇO COMUM das duas versões com o roteiro.

    É esse pedaço que a anáfora repete de propósito: em "Você não precisa de mais seguidor…" /
    "Você não precisa de mais tráfego…" o que volta é "Você não precisa de mais" — as frases
    INTEIRAS aparecem uma vez cada, então testar a frase toda não protege nada. Já num gaguejo o
    começo comum ("com um profissional") aparece uma vez só no roteiro, e aí não protege — certo,
    porque ali ele repetiu sem querer.
    """
    if not escrito:
        return False
    k = 0
    while k < n and i + k < len(T) and j + k < len(T) and T[i + k] == T[j + k]:
        k += 1
    if k < 2:
        return False
    comum = " ".join(str(x.get("p") or x.get("word") or "") for x in W[i:i + k])
    return vezes_no_roteiro(comum, escrito) >= 2


def _juntar(spans: list[dict]) -> list[dict]:
    """Funde intervalos que se encostam — perto e longe podem achar o mesmo tropeço."""
    out: list[dict] = []
    for g in sorted(spans, key=lambda x: (x["t0"], x["t1"])):
        if out and g["t0"] <= out[-1]["t1"] + 0.01:
            if g["t1"] > out[-1]["t1"]:
                out[-1] = {**out[-1], "t1": g["t1"]}
        else:
            out.append(dict(g))
    return out


def gaguejos(palavras: list[dict], roteiro: str = "", gap: int = GAG_GAP, n_min: int = GAG_MIN,
             n_max: int = GAG_MAX, limiar: float = GAG_LIMIAR, ancora: float = GAG_ANCORA,
             seg: float = GAG_SEG) -> list[dict]:
    """Tentativas abortadas no nível da palavra. Devolve os intervalos que devem SAIR.

    Duas passadas, porque são dois defeitos diferentes: o gaguejo colado (recomeça na mesma
    respirada) e o take refeito (refaz a passagem inteira meio minuto depois).
    """
    W = palavras
    if len(W) < 4:
        return []
    T = [_tok(w) for w in W]
    # 🔴 Na janela larga é o ROTEIRO que separa "ele refez" de "o texto repete de propósito".
    # Sem roteiro a passada larga continua valendo — é a mesma aposta que a regra de segmento já
    # faz hoje —, mas com roteiro ela para de errar na anáfora.
    escrito = _tokens(roteiro) if roteiro else []
    protege = ((lambda i, j, n: _do_roteiro(W, T, i, j, n, escrito))
               if len(escrito) >= 8 else None)
    return _juntar(_perto(W, T, gap, n_min, n_max, limiar, ancora, seg, protege)
                   + _longe(W, T, GAG_LONGE_MIN, n_max, limiar, GAG_LONGE_SEG, protege))


def _tirar(blocos: list[dict], spans: list[dict], folga: float = 0.03) -> list[dict]:
    """Subtrai os intervalos de gaguejo dos blocos mantidos, partindo o bloco quando cai no meio."""
    if not spans:
        return blocos
    out = []
    for b in blocos:
        pedacos = [(b["t0"], b["t1"])]
        for g in spans:
            g0, g1 = g["t0"] - folga, g["t1"] + folga
            novos = []
            for a, c in pedacos:
                if g1 <= a or g0 >= c:
                    novos.append((a, c)); continue
                if a < g0:
                    novos.append((a, g0))
                if g1 < c:
                    novos.append((g1, c))
            pedacos = novos
        out.extend({"t0": round(a, 3), "t1": round(c, 3)} for a, c in pedacos if c - a > 0.12)
    return out


def _palavras_de(seg: dict, palavras: list[dict]) -> list[dict]:
    """Palavras do trecho pelo MEIO da palavra — assim, aparar o t1 realmente tira a última."""
    return [w for w in palavras
            if seg["t0"] - 0.05 <= (w["t0"] + w.get("t1", w["t0"])) / 2 <= seg["t1"] + 0.02]


def emendas_gaguejando(mantidos: list[dict], palavras: list[dict], limite: int = 5) -> list[dict]:
    """Fim de um trecho repetindo o começo do seguinte — o gaguejo que sobra DEPOIS de escolher take.

    Ele começa a frase, para, e recomeça do zero: "…olha as duas coisas, tá? Primeira" emenda com
    "Primeira, se o serviço que você fazia…". Como os textos inteiros são diferentes, nenhuma regra
    de segmento pega — mas no vídeo a palavra aparece duas vezes e a emenda trava. Aqui a comparação
    é PALAVRA a palavra nas pontas, e quem sai é a cauda do primeiro (fica sempre a versão completa).
    """
    achados = []
    for a, b in zip(mantidos, mantidos[1:]):
        wa, wb = _palavras_de(a, palavras), _palavras_de(b, palavras)
        if not wa or not wb:
            continue
        ta = [_limpo(w["p"]) for w in wa]
        tb = [_limpo(w["p"]) for w in wb]
        for k in range(min(limite, len(ta), len(tb)), 0, -1):
            if ta[-k:] != tb[:k]:
                continue
            repetido = " ".join(tb[:k])
            if k < len(ta) and round(wa[-k - 1]["t1"] + 0.06, 2) >= a["t1"] - 0.005:
                break                              # cauda já aparada (30-out-2026): o aviso saía mesmo sem nada pra aparar
            if k == len(ta):                       # o trecho inteiro é o falso começo do próximo
                achados.append({"i": a["i"], "j": b["i"], "palavras": k, "texto": repetido,
                                "novo_t1": None, "t0": a["t0"], "t1": a["t1"]})
            else:
                achados.append({"i": a["i"], "j": b["i"], "palavras": k, "texto": repetido,
                                "novo_t1": round(wa[-k - 1]["t1"] + 0.06, 2), "t0": a["t0"], "t1": a["t1"]})
            break
    return achados


def _aparar_emendas(lista: list[dict], palavras: list[dict]) -> int:
    """Apara as caudas repetidas. Mexe em t1 (tempo de palavra), não joga o trecho bom fora."""
    por_i = {s["i"]: s for s in lista}
    n = 0
    for e in emendas_gaguejando([s for s in lista if s.get("manter")], palavras):
        s = por_i.get(e["i"])
        if not s:
            continue
        if e["novo_t1"] is None or e["novo_t1"] <= s["t0"] + 0.2:
            s["manter"] = False
            s["motivo"] = f"falso começo — só repete “{e['texto']}”, que o trecho seguinte já diz"
        else:
            s["t1"] = e["novo_t1"]
            s["texto"] = " ".join(w["p"] for w in _palavras_de(s, palavras)).strip() or s["texto"]
            s["motivo"] = (s.get("motivo") or "fala boa") + \
                f" · cauda aparada: ele já tinha começado “{e['texto']}” e recomeçou"
        n += 1
    return n


def _marcar_corte_no_fim(segs: list[dict], fora: dict, duracao) -> None:
    """Último trecho sem ponto final que vai até o fim do bruto: a pessoa foi cortada no meio da frase, não entra como fala boa."""
    try:
        dur = float(duracao or 0)
    except (TypeError, ValueError):
        return
    if not segs or dur <= 0:
        return
    u = segs[-1]
    if u["i"] in fora or str(u.get("texto", "")).rstrip().endswith((".", "!", "?", "…")):
        return
    # 09-nov-2026: o transcritor não põe ponto na última frase quando o bruto acaba colado na fala. Se o trecho de antes
    # também está sem ponto, este é o FECHO da frase dele ("uma imagem | do que você não é"): tirar deixava o vídeo
    # terminando no meio (G23). Furou 2 vídeos seguidos (video-1 e vídeo 2 do João).
    ant = [s for s in segs[:-1] if s["i"] not in fora]
    if ant and not str(ant[-1].get("texto", "")).rstrip().endswith((".", "!", "?", "…")):
        return
    if dur - float(u["t1"]) <= 0.15:
        fora[u["i"]] = "frase cortada no fim do bruto"


def propor_auto(video: Path, work: Path, briefing: str = "", cliente: str = "Joao",
                refazer: bool = False, roteiro: str = "", motor: str = "") -> dict:
    """Monta o CORTE.json sem IA nenhuma: take refeito, falso começo e erro assumido são medidos.

    O que a máquina NÃO julga: enrolação e fuga de assunto. Isso fica pro João desmarcar na tela
    (ou pra revisão com IA, quando ele pedir). Trocar cota de nuvem por uma decisão que já era
    objetiva não fazia sentido — e era o que mais gastava.
    """
    work = ensure(work)
    segs = transcrever(video, work, cliente, refazer=refazer, motor=motor)
    med = medir(video, work, segs)
    fora = _fora_por_repeticao(segs)
    conf = conferir_roteiro(_palavras(work), segs, ler_roteiro(work, roteiro))
    if conf["confiavel"]:
        # 🔴 O roteiro manda: se a frase está DUAS vezes no texto escrito, ele repetiu porque estava
        # escrito. Não é take refeito, e a regra de repetição não pode derrubar.
        texto_de = {s["i"]: s["texto"] for s in segs}
        for i, motivo in list(fora.items()):
            if "refeit" in motivo or "falso começo" in motivo:
                if vezes_no_roteiro(texto_de.get(i, ""), conf["tokens"]) >= 2:
                    fora.pop(i)
    for m in med.get("marcadores_de_erro", []):
        fora.setdefault(m["i"], "erro assumido na fala (\"errei\"/\"de novo\")")
    if conf["confiavel"]:
        # O que sobrou sem par no roteiro é tropeço: gaguejo, take refeito e enrolação.
        # A guarda de "não apagar palavra curta" nasceu do medo de comer uma negação; com gabarito
        # esse medo acaba — se o "não" estivesse na fala escrita, ele teria casado. Mas alinhamento
        # de UMA palavra é ruidoso, então trecho de 1-2 palavras só sai com ZERO de roteiro.
        for seg in segs:
            c = conf["por_segmento"].get(seg["i"])
            if c is None:
                continue
            if c <= (FORA_ROTEIRO if seg.get("palavras", 0) >= 3 else 0.0):
                fora.setdefault(seg["i"], f"fora do roteiro — {int(c * 100)}% dessa fala estava escrita")
    # Uma palavra curta pode ser a negação, resposta ou ligação da frase. Não
    # apagar conteúdo apenas por duração ou quantidade de palavras.
    _marcar_corte_no_fim(segs, fora, med.get("duracao_s"))
    lista = [{**s, "manter": s["i"] not in fora,
              "motivo": fora.get(s["i"], "fala boa")} for s in segs]
    aparadas = _aparar_emendas(lista, _palavras(work))
    gag = gaguejos(_palavras(work), ler_roteiro(work))
    gravar_json(work / "gaguejos.json", gag)
    mantidos = [s for s in lista if s["manter"]]
    d = {"resumo": (" ".join(s["texto"] for s in mantidos[:3]))[:400],
         "duracao_estimada_s": round(sum(s["t1"] - s["t0"] for s in mantidos), 1),
         "motor": "automatico",
         "briefing": briefing,
         "roteiro": {k: conf[k] for k in ("confiavel", "cobertura", "n_roteiro")},
         "transcricao": (ler_json(work / "words.json", {}) or {}).get("motor", "groq-whisper"),
         "segmentos": lista,
         "emendas_aparadas": aparadas,
         "gaguejos": len(gag),
         "gaguejo_s": round(sum(g["t1"] - g["t0"] for g in gag), 1),
         "observacoes": f"Corte automático: {len(mantidos)} de {len(lista)} trechos ficam"
                        + (f", {aparadas} emenda(s) aparada(s). " if aparadas else ". ") +
                        f"A máquina tira take refeito, falso começo e erro assumido — "
                        f"enrolação e fuga de assunto você tira desmarcando aqui."
                        + (f" Conferido contra o roteiro ({int(conf['cobertura'] * 100)}% dele "
                           f"aparece no bruto): fala escrita fica protegida."
                           if conf["confiavel"] else
                           (" O roteiro colado quase não aparece no bruto, então não mandou em nada."
                            if conf["n_roteiro"] else ""))}
    gravar_json(work / "CORTE.json", d)
    return d


def _resumo_log(work: Path, d: dict) -> str:
    ver = verificar(work, d)
    fora = [s for s in d.get("segmentos", []) if not s.get("manter")]
    linhas = [f"Corte montado automaticamente (sem IA, sem gastar cota).",
              f"Ficam {len(d['segmentos']) - len(fora)} de {len(d['segmentos'])} trechos · "
              f"{d.get('duracao_estimada_s')}s de fala.", ""]
    if fora:
        linhas.append("Saem:")
        linhas += [f"  [{s['i']}] {s['t0']}s  {s['texto'][:70]}  → {s['motivo']}" for s in fora]
    if ver["n"]:
        linhas += ["", f"⚠ Ainda há {ver['n']} repetição(ões) nos trechos mantidos — confira na lista."]
    return "\n".join(linhas) + "\n"


# ───────────────────────────── blocos, aperto e render ─────────────────────────────

def _blocos(d: dict, med: dict, respiro: float = RESPIRO, entrada: float = ENTRADA,
            palavras: list[dict] | None = None) -> list[dict]:
    """Preserva trechos consecutivos; emendas só recebem silêncio livre de palavras."""
    segs=sorted(d.get('segmentos',[]),key=lambda s:s['t0'])
    mantidos=[(i,s) for i,s in enumerate(segs) if s.get('manter')]
    dur=med.get('duracao_s') or max((s['t1'] for s in segs),default=0)
    ws=palavras or []
    out=[]
    for k,(i,s) in enumerate(mantidos):
        a,b=float(s['t0']),float(s['t1'])
        anteriores=[w['t1'] for w in ws if w['t1']<=a+0.001]
        posteriores=[w['t0'] for w in ws if w['t0']>=b-0.001]
        anterior=max(anteriores,default=segs[i-1]['t1'] if i else 0)
        posterior=min(posteriores,default=segs[i+1]['t0'] if i+1<len(segs) else dur)
        pad_in=min(entrada,max(0,respiro)/2) if k else 0.04
        pad_out=max(0,respiro)/2 if k+1<len(mantidos) else 0.06
        a=max(0,a-min(pad_in,max(0,a-anterior)*0.5))
        b=min(dur,b+min(pad_out,max(0,posterior-b)*0.5))
        # Uma palavra desmarcada nunca volta pela união de blocos vizinhos.
        consecutivo=k>0 and mantidos[k-1][0]==i-1
        if out and consecutivo:out[-1]['t1']=max(out[-1]['t1'],round(b,3))
        else:out.append({'t0':round(a,3),'t1':round(b,3)})
    return [x for x in out if x['t1']>x['t0']]


def _buracos(b: dict, palavras: list[dict], sil: list[dict], limite: float) -> list[tuple]:
    """Encurta silêncio medido, protegido pelos intervalos de TODAS as palavras.

    Uma lacuna do transcritor sozinha não comprova silêncio: pode ser uma palavra
    que ele não reconheceu. A união das duas fontes cortava sílabas e fala baixa.
    """
    livres=[]
    for x in sil:
        partes=[(max(x['t0'],b['t0']),min(x['t1'],b['t1']))]
        for w in palavras:
            inicio,fim=w['t0']-0.04,w['t1']+0.06
            novas=[]
            for a,c in partes:
                if fim<=a or inicio>=c:novas.append((a,c));continue
                if a<inicio:novas.append((a,inicio))
                if fim<c:novas.append((fim,c))
            partes=novas
        livres.extend((a,c) for a,c in partes if c-a>limite)
    livres.sort();junto=[]
    for a,c in livres:
        if junto and a<=junto[-1][1]:junto[-1]=(junto[-1][0],max(junto[-1][1],c))
        else:junto.append((a,c))
    return junto


def _apertar(blocos: list[dict], palavras: list[dict], sil: list[dict],
             limite: float = APERTO, alvo: float = APERTO_ALVO) -> list[dict]:
    """Encurta a pausa MORTA dentro de um trecho mantido — é o "muito fôlego" que trava o vídeo.

    Escolher o take certo não faz o vídeo fluir: dentro de um take bom ele ainda segura 1,5s
    procurando a palavra. Aqui cada buraco de silêncio maior que `limite` vira um corte, deixando só
    `alvo` de pausa. Buraco pequeno demais não vira corte — não vale o salto na imagem por 0,2s.
    """
    if limite <= 0:
        return blocos
    out: list[dict] = []
    for b in blocos:
        cur = b["t0"]
        pedacos: list[dict] = []
        for a, c in _buracos(b, palavras, sil, limite):
            corte0 = max(cur + 0.3, a + alvo * 0.6)
            corte1 = c - alvo * 0.4
            if corte1 - corte0 < 0.25:
                continue
            pedacos.append({"t0": round(cur, 3), "t1": round(corte0, 3)})
            cur = corte1
        if b["t1"] > cur:
            pedacos.append({"t0": round(cur, 3), "t1": round(b["t1"], 3)})
        # Não eliminar palavras aprovadas por serem curtas. Até um “não” muda
        # o sentido; o aperto altera apenas os intervalos sem fala.
        out.extend(pedacos)
    return out


def assinatura(d: dict) -> str:
    """Impressão digital das escolhas — pra saber se o mp4 na tela é o corte atual ou um velho."""
    base = [[s.get("i"), bool(s.get("manter")), s.get("t0"), s.get("t1")] for s in d.get("segmentos", [])]
    base.append(["roteiro", (d.get("roteiro") or {}).get("cobertura")])
    return hashlib.sha1(json.dumps(base, sort_keys=True).encode()).hexdigest()[:12]


def desatualizado(d: dict | None, tem_video: bool = False) -> bool:
    """O mp4 que está na tela ainda é o corte atual? (proposta nova ou escolhas mudadas = não)"""
    if not d:
        return False
    ap = d.get("aplicado")
    if not ap:
        return tem_video          # proposta refeita depois do render: o vídeo é de outro corte
    return ap.get("assinatura") != assinatura(d) or ap.get('motor') != VERSAO_MOTOR


def aplicar(video: Path, corte_json: Path, saida: Path, fade: float = 0.015,
            respiro: float = RESPIRO, aperto: float = APERTO) -> Path:
    """Corta e junta num ÚNICO passe de ffmpeg (trim+concat no filtro) — sem emenda picotada.

    Concatenar arquivos separados com `-c copy` estraga a emenda quando o corte não cai num keyframe
    (é o 'bugado' que aparecia). Aqui tudo é reencodado de uma vez, frame a frame, e o áudio ganha um
    micro-fade de 15ms em cada emenda pra não estalar.
    """
    d = ler_json(corte_json, {}) or {}
    work = Path(corte_json).parent
    from corte_qualidade import validar
    original=ler_json(work/'segmentos.json',None)
    if original is None:raise ValueError('A transcrição original não está disponível para conferir o corte.')
    validar(d,original)
    if not 0<=respiro<=1 or not 0<=aperto<=5:raise ValueError('Escolha valores válidos para o ritmo do corte.')
    med = ler_json(work / "medidas.json", {}) or {}
    if not med.get("duracao_s"):
        med["duracao_s"] = ffprobe(video).get("duracao")
    palavras = _palavras(work)
    sil = med.get("silencios") or med.get("silencios_longos") or []
    blocos = _blocos(d, med, respiro=respiro, palavras=palavras)
    if not blocos:
        raise ValueError("nenhum segmento marcado pra manter")
    brutos = len(blocos)
    # O gaguejo sai ANTES do aperto: são cortes de fala, não de silêncio, e partir o bloco aqui
    # deixa o aperto trabalhar já em cima do que de fato vai pro vídeo.
    blocos = _tirar(blocos, ler_json(work / "gaguejos.json", []) or [])
    blocos = _apertar(blocos, palavras, sil, limite=aperto)
    ensure(saida.parent)
    partes, mapa = [], []
    for i, b in enumerate(blocos):
        dur = b["t1"] - b["t0"]
        fo = max(0.0, dur - fade)
        partes.append(f"[0:v]trim=start={b['t0']:.3f}:end={b['t1']:.3f},setpts=PTS-STARTPTS[v{i}];"
                      f"[0:a]atrim=start={b['t0']:.3f}:end={b['t1']:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:st=0:d={fade},afade=t=out:st={fo:.3f}:d={fade}[a{i}]")
        mapa.append(f"[v{i}][a{i}]")
    filtro = ";".join(partes) + ";" + "".join(mapa) + f"concat=n={len(blocos)}:v=1:a=1[v][a]"
    fil = saida.parent / f".filtro-{now_slug()}.txt"
    fil.write_text(filtro, encoding="utf-8")
    temporario=saida.with_name(saida.stem+'.renderizando'+saida.suffix)
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(video),
                        "-/filter_complex", str(fil), "-map", "[v]", "-map", "[a]",
                        "-c:v", "h264_videotoolbox", "-b:v", "16M", "-allow_sw", "1", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temporario)],
                       capture_output=True, text=True, timeout=3600)
    if r.returncode or not temporario.exists():   # sem o chip do Mac: libx264 (bem mais lento)
        r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(video),
                            "-/filter_complex", str(fil), "-map", "[v]", "-map", "[a]",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temporario)],
                           capture_output=True, text=True, timeout=3600)
    fil.unlink(missing_ok=True)
    if r.returncode or not temporario.exists() or not temporario.stat().st_size:
        temporario.unlink(missing_ok=True)
        raise RuntimeError((r.stderr or "")[-800:] or "ffmpeg falhou no corte")   # o log guarda o original; a tela mostra erro_simples
    temporario.replace(saida)
    d["blocos_aplicados"] = blocos
    d["aplicado"] = {"assinatura": assinatura(d), "motor": VERSAO_MOTOR, "respiro_s": respiro, "aperto_s": aperto,
                     "blocos": len(blocos), "pausas_apertadas": len(blocos) - brutos,
                     "duracao_s": round(sum(b["t1"] - b["t0"] for b in blocos), 2)}
    d["respiro_s"] = respiro
    gravar_json(Path(corte_json), d)
    return saida


def marcar_etapa(work: Path, texto: str) -> None:
    (Path(work) / ".etapa").write_text(texto, encoding="utf-8")
    if texto and os.environ.get("ESTUDIO_JOB"):   # corte de um vídeo da tela: o passo aparece na aba Em andamento
        _andamento("passo", texto.rstrip("…. "))


def _andamento(acao: str, texto: str) -> None:
    if not os.environ.get("ESTUDIO_JOB"):
        return
    try:
        import andamento
        getattr(andamento, acao)("", "", texto, etapa="preparar")
    except Exception:
        pass


def etapa(work: Path) -> str:
    p = Path(work) / ".etapa"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def rodando(work: Path) -> bool:
    try:
        os.kill(int((Path(work) / ".runner.pid").read_text().strip()), 0)
        return True
    except Exception:
        return False


# ───────────────────────────── disparo (segundo plano) ─────────────────────────────

def propor(video: Path, work: Path, cliente: str = "Joao", briefing: str = "",
           com_ia: bool = False, refazer: bool = False, roteiro: str = "", job_id: str = "",
           aplicar: bool = False) -> None:
    """Dispara o corte em segundo plano. Sem IA por padrão — só liga o Claude se `com_ia`."""
    work = ensure(work)
    (work / ".log").unlink(missing_ok=True)
    ler_roteiro(work, roteiro)   # fica na work: o processo de trás lê de lá, sem passar por argv
    cmd = [sys.executable, str(Path(__file__)), "auto", str(video), str(work),
           "--cliente", cliente, "--briefing", briefing or ""]
    if com_ia:
        cmd.append("--ia")
    if refazer:
        cmd.append("--refazer")
    marcar_etapa(work, "Começando o corte…")
    env = {**os.environ, **({"ESTUDIO_JOB": job_id} if job_id else {}),
           **({"ESTUDIO_APLICAR": "1"} if aplicar and job_id else {})}   # corte automático: já aplica e segue   # aba Em andamento: os passos caem no vídeo certo
    proc = subprocess.Popen(cmd, cwd=str(RAIZ), start_new_session=True, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    # pid anotado AQUI (igual ao avulso): se esperasse o filho, a tela recarregava antes e mostrava os botões
    # de novo, sem "rodando" e sem se atualizar, como se o clique não tivesse feito nada.
    (work / ".runner.pid").write_text(str(proc.pid))


def _auto(video: Path, work: Path, cliente: str, briefing: str, com_ia: bool, refazer: bool, motor: str = "") -> int:
    work = ensure(work)
    pid_file = work / ".runner.pid"
    log = work / ".log"
    pid_file.write_text(str(os.getpid()))
    try:
        marcar_etapa(work, "Transcrevendo e montando o corte…")
        with log.open("a", encoding="utf-8") as out:
            quem = "Scribe da ElevenLabs, verbatim" if scribe_pronto() and motor != "groq" else "GROQ whisper"
            out.write(f"Transcrevendo ({quem}) e remontando os segmentos pelas pausas…\n"); out.flush()
            d = propor_auto(video, work, briefing, cliente, refazer=refazer, motor=motor)
            out.write(_resumo_log(work, d)); out.flush()
        marcar_etapa(work, "Pedindo ajuda da IA…" if com_ia else "")
        code = 0
        if com_ia:
            import ia
            pf = work / ".prompt-corte.txt"
            pf.write_text(prompt_propor(video, work, briefing), encoding="utf-8")
            code = executar_revisao(pf,work)
        if os.environ.get("ESTUDIO_APLICAR") and not code:
            marcar_etapa(work, "Aplicando o corte…")
            _aplicar_no_video(os.environ["ESTUDIO_JOB"])
            marcar_etapa(work, "")
            return 0
        _andamento("espera", "Corte pronto: confira os trechos e aplique" if not code
                   else "Corte pronto, mas a revisão da IA falhou: confira os trechos")
        return code
    except Exception as e:
        (work / ".log").open("a", encoding="utf-8").write(f"\n✖ Falhou: {e}\n")
        _andamento("erro", f"O corte falhou: {erro_simples(e)[:160]}")
        return 1
    finally:
        pid_file.unlink(missing_ok=True)


def _aplicar_no_video(job_id: str) -> None:
    """Fim do corte automático: aplica (work/joao.mp4) e, se o João já pediu o storyboard, dispara ele."""
    import producao as _p
    cli, slug = job_id.split("/", 1)
    _p.aplicar_corte(cli, slug, avisar=False)
    job = _p.carregar(cli, slug)
    depois = job.pop("analisar_depois", None)
    _p.salvar(job)
    # sem parar pra aprovar um corte que o João nem pediu: segue direto pro storyboard (ajustar o corte fica no Corrigir o corte)
    _andamento("passo", "Corte feito sozinho. Montando o storyboard")
    # este processo ainda segura o .runner.pid (só solta no finally): sem soltar aqui, analisar() acha que o corte "ainda roda",
    # guarda "analisar_depois" e ninguém nunca consome: o vídeo ficava parado em "cortado" (bug de 29-out-2026, job Teste fluxo faixa)
    (_p.RAIZ / job['sandbox'] / "work" / ".runner.pid").unlink(missing_ok=True)
    _p.analisar(cli, slug, depois if isinstance(depois, str) else "")


def _bloco_roteiro(work: Path) -> str:
    """O roteiro no prompt da IA — sem ele a IA desmarca justamente a fala que o gabarito protegeu."""
    texto = ler_roteiro(work)
    if not texto:
        return "ROTEIRO: (não veio roteiro; julgue só pelo sentido da fala)"
    return ("ROTEIRO ESCRITO (é o GABARITO — fala que está aqui NÃO sai, mesmo parecendo repetida;\n"
            "o roteiro repete de propósito. Só tire o que não está escrito aqui):\n" + texto.strip()[:6000])


def prompt_propor(video: Path, work: Path, briefing: str = "") -> str:
    """Prompt da AJUDA DA IA: ela não monta do zero, ela REVISA o corte automático (custa menos)."""
    segs = ler_json(work / "segmentos.json", [])
    med = ler_json(work / "medidas.json", {})
    d = ler_json(work / "CORTE.json", {}) or {}
    marca = {s["i"]: s for s in d.get("segmentos", [])}
    linhas = "\n".join(
        f"[{s['i']}] {s['t0']}–{s['t1']}s {'FICA ' if marca.get(s['i'], {}).get('manter', True) else 'SAI  '}"
        f" {s['texto']}   ({marca.get(s['i'], {}).get('motivo', '')})" for s in segs)
    from corte_qualidade import DIRETRIZES
    return DIRETRIZES + f"""Você está no repositório producao-reels. ETAPA 0 de um vídeo: REVISAR O CORTE do bruto.

O corte automático (determinístico) já rodou e marcou take refeito, falso começo e erro assumido.
Sua missão é só o julgamento que a máquina não faz: ENROLAÇÃO, fuga de assunto e ordem das ideias.
Não refaça o que já está certo. Mexa só no que estiver errado.

BRUTO: {video}   ({med.get('duracao_s')}s, {med.get('n_segmentos')} segmentos)
BRIEFING: {briefing or '(sem briefing)'}
{_bloco_roteiro(work)}
PASTA: {work}   (CORTE.json, segmentos.json, words.json, medidas.json)

CORTE ATUAL (índice, tempo, fica/sai, texto, motivo):
{linhas}

EVIDÊNCIA JÁ MEDIDA (confira o áudio quando houver dúvida de palavra ou emenda):
- repetições de sequência de palavras: {json.dumps(med.get('repeticoes_palavra', [])[:12], ensure_ascii=False)}
- marcadores de erro: {json.dumps(med.get('marcadores_de_erro', [])[:10], ensure_ascii=False)}

REGRAS APRENDIDAS COM O JOÃO (valem acima de tudo):
{_regras_texto()}

REGRAS:
1. Escolha o take completo que preserva a ideia. Não suponha que a última versão está correta.
2. Corte enrolação que não acrescenta e conversa fora do assunto. Na dúvida, MANTENHA.
3. NÃO mexa em t0/t1: os tempos vêm das palavras e a pausa interna é apertada no render.
4. Os segmentos são unidades entre pausas; uma frase pode continuar no próximo trecho. Não invente índice novo
   (nada de "9a"/"9b"): se precisar separar duas falas, elas já são segmentos diferentes.

EDITE {work}/CORTE.json mudando APENAS o campo `manter` (e o `motivo` do que você mudou), e escreva
em `observacoes` uma linha com o que você mexeu. Mantenha todos os segmentos, na ordem. JSON válido.
Não mexa em nenhum outro arquivo. Não peça confirmação. Seja curto: nada de relatório.
"""


def main():
    if len(sys.argv)>1 and sys.argv[1]=="revisar-arquivo":
        code=executar_revisao(Path(sys.argv[2]),Path(sys.argv[3]))
        _andamento("espera","Corte revisado: confira e aplique" if not code else "A revisão do corte falhou: confira os trechos")
        sys.exit(code)
    ap = argparse.ArgumentParser(description="Corte automático do bruto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("transcrever", "medir", "propor", "auto"):
        p = sub.add_parser(nome); p.add_argument("video"); p.add_argument("work")
        p.add_argument("--cliente", default="Joao"); p.add_argument("--briefing", default="")
        p.add_argument("--ia", action="store_true"); p.add_argument("--refazer", action="store_true")
        p.add_argument("--roteiro", default="", help="roteiro escrito (texto ou caminho de arquivo)")
    for nome in ("transcrever", "auto"):
        sub.choices[nome].add_argument("--groq", action="store_true", help="transcreve com o GROQ mesmo com o Scribe ligado")
    vf = sub.add_parser("verificar", help="confere o corte da pasta: sai 1 se sobrou repetição ou emenda gaguejando")
    vf.add_argument("work")
    ac = sub.add_parser("avulso-criar", help="cria a pasta do corte avulso (app/cortes/<slug>/) a partir de um vídeo do Mac")
    ac.add_argument("video"); ac.add_argument("--titulo", default=""); ac.add_argument("--cliente", default="Joao")
    rv = sub.add_parser("render-avulso"); rv.add_argument("slug")
    rv.add_argument("--respiro", type=float, default=RESPIRO); rv.add_argument("--aperto", type=float, default=APERTO)
    a = sub.add_parser("aplicar"); a.add_argument("video"); a.add_argument("corte"); a.add_argument("saida")
    a.add_argument("--respiro", type=float, default=RESPIRO)
    a.add_argument("--aperto", type=float, default=APERTO)
    args = ap.parse_args()
    if args.cmd == "transcrever":
        segs = transcrever(Path(args.video), Path(args.work), args.cliente, refazer=args.refazer,
                           motor="groq" if args.groq else "")
        print(f"{len(segs)} segmentos")
    elif args.cmd == "verificar":
        res = verificar(Path(args.work))
        ruim = bool(res.get("n") or res.get("emendas"))
        print(json.dumps({"ok": not ruim, "repeticoes": res.get("n"), "emendas_gaguejando": len(res.get("emendas") or []),
                          "duracao_mantida_s": res.get("duracao_mantida_s"),
                          "duplicatas_restantes": res.get("duplicatas_restantes"), "emendas": res.get("emendas")},
                         ensure_ascii=False, indent=2)[:4000])
        print("REPROVADO: sobrou repetição ou emenda gaguejando no corte" if ruim else "APROVADO: corte sem repetição")
        sys.exit(1 if ruim else 0)
    elif args.cmd == "avulso-criar":
        c = avulso_criar_do_mac(args.video, args.titulo, args.cliente)
        print(f"ok · app/cortes/{c['slug']}/ (slug {c['slug']})")
    elif args.cmd == "medir":
        print(json.dumps(medir(Path(args.video), Path(args.work)), ensure_ascii=False, indent=2)[:2000])
    elif args.cmd == "render-avulso":
        sys.exit(_render_avulso(args.slug, args.respiro, args.aperto))
    elif args.cmd == "auto":
        ler_roteiro(ensure(Path(args.work)), args.roteiro)
        sys.exit(_auto(Path(args.video), Path(args.work), args.cliente, args.briefing, args.ia, args.refazer,
                       motor="groq" if args.groq else ""))
    elif args.cmd == "propor":
        propor(Path(args.video), Path(args.work), args.cliente, args.briefing, args.ia, args.refazer,
               roteiro=args.roteiro)
        print("corte rodando; acompanhe", Path(args.work) / ".log")
    else:
        print(aplicar(Path(args.video), Path(args.corte), Path(args.saida),
                      respiro=args.respiro, aperto=args.aperto))


# ═════════════════ APRENDIZADO DO CORTE (separado do aprendizado dos modelos) ═════════════════
# O corte tem erros próprios: deixou duplicata, cortou no meio da palavra, tirou uma pausa que era
# ênfase. Isso não é regra de modelo — é regra de COMO CORTAR. Vive em app/aprendizado/corte/.

from _comum import ESTUDIO as _EST, agora as _agora, hoje as _hoje, append_jsonl as _append

APRENDIZADO = _EST / "aprendizado" / "corte"


def regras() -> dict:
    return ler_json(APRENDIZADO / "regras.json", {"regras": []}) or {"regras": []}


def historico(n: int = 40) -> list[dict]:
    p = APRENDIZADO / "historico.jsonl"
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if l.strip():
            try:
                out.append(json.loads(l))
            except Exception:
                pass
    return out[-n:]


def _regras_texto() -> str:
    rs = regras().get("regras", [])
    if not rs:
        return "(ainda não há regras aprendidas — é o primeiro corte)"
    rs = sorted(rs, key=lambda r: -(r.get("peso") or 5))
    return "\n".join(f"  [{r.get('categoria','geral')}] {r.get('texto','')}"
                     + (f"  🚫 EVITAR: {r['evitar']}" if r.get("evitar") else "") for r in rs)


def registrar_feedback(texto: str, work: Path | None = None, origem: str = "usuario") -> None:
    _append(APRENDIZADO / "historico.jsonl",
            {"tipo": "feedback", "texto": texto, "origem": origem, "createdAt": _hoje(),
             "em": _agora(), "corte": str(work) if work else None})


def prompt_revisar(video: Path, work: Path, feedback: str) -> str:
    med = ler_json(work / "medidas.json", {})
    ver = verificar(work)
    d = ler_json(work / "CORTE.json", {}) or {}
    mantidos = [s for s in d.get("segmentos", []) if s.get("manter")]
    linha_mant = "\n".join(f"[{s['i']}] {s['t0']}–{s['t1']}s  {s['texto']}" for s in mantidos)
    ap = (d.get("aplicado") or {})
    from corte_qualidade import DIRETRIZES
    return DIRETRIZES + f"""Você está no repositório producao-reels. O João REVISOU um corte e apontou erro.

BRUTO: {video}
PASTA: {work}   (CORTE.json, segmentos.json, words.json, medidas.json)
RENDER ATUAL: respiro {ap.get('respiro_s')}s · aperto de pausa interna {ap.get('aperto_s')}s

O QUE O JOÃO DISSE:
\"\"\"{feedback}\"\"\"

⚠ Os segundos que ele cita são do VÍDEO CORTADO, não do bruto. Converta usando blocos_aplicados do
CORTE.json (os blocos entram em sequência: o segundo X do corte cai no bloco que acumula X segundos).

TRECHOS QUE ESTÃO FICANDO HOJE:
{linha_mant}

BLOCOS APLICADOS (tempo no bruto, na ordem): {json.dumps(d.get('blocos_aplicados', [])[:40], ensure_ascii=False)}

CHECAGEM AUTOMÁTICA (n-gramas repetidos que SOBRARAM nos trechos mantidos):
{json.dumps(ver.get('duplicatas_restantes', [])[:15], ensure_ascii=False, indent=1)}

O QUE FAZER:
1. Converta o segundo que ele citou pro tempo do bruto e vá exatamente lá no words.json.
2. Se ele reclamou de FÔLEGO/TRAVA: a pausa interna é apertada no render (`aperto`), não no JSON —
   a correção é baixar o aperto, não desmarcar segmento. Diga isso na observação.
   Se reclamou de REPETIÇÃO: compare as versões no contexto e preserve a mais completa e correta.
3. Corrija o CORTE.json mudando `manter` (e `motivo`). NÃO invente índice novo, NÃO mexa em t0/t1.
4. Varra o resto do corte procurando o MESMO tipo de erro — se errou uma vez, errou de novo.
5. APRENDIZADO — A REGRA É O PRODUTO, o histórico é só recibo. Analise POR QUE errou (a causa, não o
   sintoma). Depois:
   - uma linha em {APRENDIZADO}/historico.jsonl:
     {{"tipo":"correcao","texto":"<causa em uma frase>","regra":"<id da regra criada/aprimorada>","origem":"ia","createdAt":"{_hoje()}"}}
   - em {APRENDIZADO}/regras.json: procure a regra existente do mesmo assunto e APRIMORE. Só crie
     nova se o assunto for outro. Formato:
     {{"regras":[{{"id":"kebab-case","categoria":"duplicata|borda|pausa|ritmo|erro-assumido|geral","peso":1-10,
                   "texto":"a regra, com o número/critério concreto","evitar":"o que não fazer","desde":"{_hoje()}"}}]}}
5b. Toda correção TEM que terminar numa regra, nem que seja específica deste cliente.
6. Escreva no CORTE.json "revisao": {{"em":"{_agora()}","pedido":"<o que ele pediu>","mudou":"<o que você mudou>"}}.
7. Só esses arquivos. JSON válido. Sem pedir confirmação. Resposta curta, sem relatório.
"""


def executar_revisao(prompt_file: Path, work: Path) -> int:
    import ia
    from corte_qualidade import validar
    original=ler_json(work/'segmentos.json',[]) or []
    before=(work/'CORTE.json').read_bytes()
    fontes={name:(work/name).read_bytes() for name in ('segmentos.json','words.json') if (work/name).exists()}
    try:
        code=ia.executar(prompt_file.read_text(),work/'.log',work/'.raw.jsonl',work/'.runner.pid')
        if code:raise ValueError('A revisão da IA foi interrompida.')
        if any(not (work/name).exists() or (work/name).read_bytes()!=data for name,data in fontes.items()):
            raise ValueError('A revisão alterou a transcrição original. As fontes foram restauradas.')
        validar(ler_json(work/'CORTE.json',{}),original)
        return 0
    except Exception as e:
        # Uma resposta incompleta não substitui a última seleção válida.
        (work/'CORTE.json').write_bytes(before)
        for name,data in fontes.items():(work/name).write_bytes(data)
        with (work/'.log').open('a') as log:log.write('\nRevisão não aplicada: '+str(e)+'\n')
        return 1


def revisar(video: Path, work: Path, feedback: str, job_id: str = "") -> None:
    """Dispara a revisão do corte com o feedback do João (e o aprendizado)."""
    work = ensure(Path(work))
    if rodando(work):raise ValueError('Aguarde a revisão em andamento antes de pedir outra.')
    ensure(APRENDIZADO)
    registrar_feedback(feedback, work)
    pf = work / ".prompt-revisar.txt"
    pf.write_text(prompt_revisar(video, work, feedback), encoding="utf-8")
    marcar_etapa(work, "A IA está revisando o corte com o seu pedido…")
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "revisar-arquivo", str(pf), str(work)],
                            cwd=str(RAIZ), start_new_session=True, env={**os.environ, **({"ESTUDIO_JOB": job_id} if job_id else {})},
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    (work / ".runner.pid").write_text(str(proc.pid))


# ═════════════════ CORTE AVULSO (era cortes.py) ═════════════════
# Mesmo motor, outra porta de entrada: aqui o João só quer ARRUMAR um vídeo, sem produzir reel nenhum.
# Ele manda o bruto, o Estúdio propõe o que fica, ele aprova na tela e baixa o vídeo limpo.
#
# Cada corte vive em app/cortes/<slug>/:
#     original.<ext>   o arquivo enviado
#     work/            transcrição, medidas, CORTE.json, log
#     cortado.mp4      o resultado
#     corte.json       metadados (título, status, datas)

import shutil
from _comum import ESTUDIO, agora, make_slug, now_slug as _now_slug, rel, thumb_cache

CORTES = ESTUDIO / "cortes"



def avulso_pasta(slug: str) -> Path:
    return CORTES / slug


def avulso_criar(arquivo: Path, titulo: str = "", cliente: str = "Joao") -> dict:
    base = make_slug(titulo or Path(arquivo).stem) or now_slug()
    slug, n = base, 2
    while avulso_pasta(slug).exists():
        slug = f"{base}-{n}"; n += 1
    d = ensure(avulso_pasta(slug))
    ensure(d / "work")
    destino = d / f"original{Path(arquivo).suffix.lower()}"
    shutil.move(str(arquivo), str(destino))
    info = ffprobe(destino)
    meta = {"slug": slug, "titulo": titulo or Path(arquivo).stem, "cliente": cliente,
            "original": rel(destino), "criado_em": agora(), "status": "novo", "media": info}
    gravar_json(d / "corte.json", meta)
    return avulso_carregar(slug)


def avulso_carregar(slug: str) -> dict | None:
    d = avulso_pasta(slug)
    m = ler_json(d / "corte.json")
    if not m:
        return None
    m["pasta"] = d
    m["work"] = d / "work"
    m["proposta"] = ler_json(d / "work" / "CORTE.json")
    m["rodando"] = rodando(d / "work")
    m["etapa"] = etapa(d / "work")
    saida = d / "cortado.mp4"
    m["cortado"] = rel(saida) if saida.exists() else None
    # o mp4 na tela pode ser de ANTES da última mudança nas escolhas — avisar em vez de enganar
    m["desatualizado"] = False if m.get("manual") else desatualizado(m["proposta"], saida.exists())   # cortado na mão: o mp4 É a última escolha dele
    m["thumb"] = rel(thumb_cache(saida if saida.exists() else (RAIZ / m["original"])) or Path()) or None
    log = d / "work" / ".log"
    m["log"] = log.read_text(encoding="utf-8", errors="replace")[-6000:] if log.exists() else ""
    # status real: o arquivo guarda a intenção, o disco diz o que de fato existe
    if m["rodando"]:
        m["status"] = "analisando"
    elif m["cortado"]:
        m["status"] = "cortado"
    elif m["proposta"]:
        m["status"] = "proposto"
    elif m["status"] == "analisando":
        m["status"] = "erro"
    return m


def avulso_listar() -> list[dict]:
    if not CORTES.is_dir():
        return []
    out = [avulso_carregar(p.name) for p in sorted(CORTES.iterdir(), reverse=True) if p.is_dir()]
    return [c for c in out if c]


def avulso_montar(slug: str, briefing: str = "", com_ia: bool = False, refazer: bool = False,
                  roteiro: str = "") -> dict:
    """Monta o corte. Sem IA por padrão (determinístico e instantâneo); com_ia só quando ele pedir."""
    m = avulso_carregar(slug)
    if not m or m["rodando"]:
        return m
    m2 = ler_json(m["pasta"] / "corte.json", {})
    m2["status"] = "analisando"; gravar_json(m["pasta"] / "corte.json", m2)
    propor(RAIZ / m["original"], m["work"], m.get("cliente", "Joao"), briefing,
              com_ia=com_ia, refazer=refazer, roteiro=roteiro)
    return avulso_carregar(slug)


def avulso_roteiro(slug: str) -> str:
    """O roteiro que está valendo nesse corte (a tela mostra pra ele conferir/editar)."""
    m = avulso_carregar(slug)
    return ler_roteiro(m["work"]) if m else ""


def avulso_salvar(slug: str, manter: list[str], obs: str = "") -> dict:
    m = avulso_carregar(slug)
    d = m.get("proposta") or {}
    ids = {str(x) for x in manter}
    for s in d.get("segmentos", []):
        s["manter"] = str(s.get("i")) in ids
    d["observacoes_joao"] = obs
    gravar_json(m["work"] / "CORTE.json", d)
    return avulso_carregar(slug)


def avulso_render(slug: str, respiro: float = RESPIRO, aperto: float = APERTO) -> dict:
    """Dispara o corte em segundo plano — o ffmpeg reencoda o vídeo inteiro e isso demora."""
    m = avulso_carregar(slug)
    if not m or m["rodando"]:
        return m
    marcar_etapa(m["work"], "Cortando o vídeo com o ffmpeg — pode demorar um pouco.")
    proc = subprocess.Popen([sys.executable, str(Path(__file__)), "render-avulso", slug,
                             "--respiro", str(respiro), "--aperto", str(aperto)],
                            cwd=str(RAIZ), start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    # o pid é anotado AQUI: se esperasse o filho escrever, a tela recarregava antes e mostrava
    # "nada rodando" no primeiro segundo, justo depois do clique.
    (m["work"] / ".runner.pid").write_text(str(proc.pid))
    return avulso_carregar(slug)


def _render_avulso(slug: str, respiro: float, aperto: float) -> int:
    m = avulso_carregar(slug)
    if not m:
        return 1
    pid_file = m["work"] / ".runner.pid"
    pid_file.write_text(str(os.getpid()))
    try:
        _avulso_render_agora(m, respiro, aperto)
        marcar_etapa(m["work"], "")
        return 0
    except Exception as e:
        (m["work"] / ".log").open("a", encoding="utf-8").write(f"\n✖ Falhou ao cortar: {e}\n")
        marcar_etapa(m["work"], f"✖ falhou: {e}")
        return 1
    finally:
        pid_file.unlink(missing_ok=True)


def _avulso_render_agora(m: dict, respiro: float = RESPIRO, aperto: float = APERTO) -> dict:
    saida = m["pasta"] / "cortado.mp4"
    aplicar(RAIZ / m["original"], m["work"] / "CORTE.json", saida, respiro=respiro, aperto=aperto)
    d = m.get("proposta") or {}
    m2 = ler_json(m["pasta"] / "corte.json", {})
    m2.update({"status": "cortado", "cortado_em": agora(),
               "mantidos": sum(1 for s in d.get("segmentos", []) if s.get("manter")),
               "total": len(d.get("segmentos", [])),
               "duracao_final": ffprobe(saida).get("duracao") if saida.exists() else None,
               "aperto_s": aperto, "respiro_s": respiro})
    gravar_json(m["pasta"] / "corte.json", m2)
    return avulso_carregar(m["slug"])


def avulso_remover(slug: str) -> bool:
    d = avulso_pasta(slug)
    if d.is_dir() and d.parent == CORTES:
        import espaco
        espaco.para_lixeira_mac([d], "corte-" + slug)      # Lixeira do Mac: recuperável pelo Finder até ser esvaziada
        return True
    return False


# ───────── escolher vídeo sem arrastar: lista o que está em Downloads/Desktop/Movies ─────────
PASTAS_ORIGEM = [Path.home() / "Downloads", Path.home() / "Desktop", Path.home() / "Movies"]
EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def avulso_videos_do_mac(limite: int = 40) -> list[dict]:
    """Vídeos recentes nas pastas do João, pra ele escolher com um clique."""
    achados = []
    for base in PASTAS_ORIGEM:
        if not base.is_dir():
            continue
        try:
            for p in base.iterdir():
                if p.is_file() and p.suffix.lower() in EXTS and not p.name.startswith("."):
                    achados.append(p)
        except PermissionError:
            continue
    achados.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in achados[:limite]:
        st = p.stat()
        out.append({"caminho": str(p), "nome": p.name, "pasta": p.parent.name,
                    "mb": round(st.st_size / 1e6), "quando": __import__("datetime").datetime
                    .fromtimestamp(st.st_mtime).strftime("%d/%m %H:%M")})
    return out


def avulso_criar_do_mac(caminho: str, titulo: str = "", cliente: str = "Joao") -> dict:
    """Usa um arquivo que já está no Mac — COPIA (não move, pra não sumir da pasta dele)."""
    src = Path(caminho).expanduser()
    if not src.is_file() or src.suffix.lower() not in EXTS:
        raise ValueError("arquivo inválido")
    tmp = ensure(ESTUDIO / ".uploads") / f"{now_slug()}-{src.name}"
    _clonar(str(src), str(tmp))
    return avulso_criar(tmp, titulo or src.stem, cliente)


def avulso_escolher_no_finder(titulo: str = "Escolha o vídeo") -> str | None:
    """Abre o Finder DE VERDADE (diálogo nativo do macOS) e devolve o caminho escolhido.

    O Estúdio roda na máquina do João, então dá pra abrir o seletor do sistema pelo servidor —
    sem depender do seletor do navegador, que às vezes não abre. Retorna None se ele cancelar.
    """
    script = ('tell application "Finder" to activate\n'
              f'set f to choose file with prompt "{titulo}" '
              'of type {"public.movie", "public.audiovisual-content"}\n'
              'return POSIX path of f')
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=300)
    except Exception:
        return None
    caminho = (r.stdout or "").strip()
    return caminho if r.returncode == 0 and caminho else None


if __name__ == "__main__":
    main()
