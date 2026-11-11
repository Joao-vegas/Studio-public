"""
Narração do motion: VoiceStudio (grátis) ou ElevenLabs via voz.py. O Gemini TTS (`--motor gemini`, voz Puck) ficou só neste arquivo: o Estúdio não chama mais.

Até ~4 min de fala vai numa chamada só (soa menos robô que frase a frase). Roteiro maior é
dividido nos parágrafos (linha em branco) em blocos de até --max-chars, cada bloco numa
chamada, e tudo é colado com 0,4 s de respiro. Uma chamada devolve no máximo ~10 min.

(Só no `--motor gemini`, que o Estúdio não chama: chaves em rodízio no app/.env, ver gemini.py.)
Direção de voz (só Gemini): <projeto>/direcao.txt se existir (quem fala, tom); senão a padrão do João.

Uso:
  python3 ~/Projetos/Skill/Estúdio/app/ferramentas/motion/narracao_tts.py --pasta <projeto>
      lê <projeto>/roteiro.txt e grava <projeto>/audio/voz-bruta.wav
  opções: --voz Puck · --modelo gemini-3.8-flash-tts · --max-chars 1100 (~1 min por bloco)
"""
from __future__ import annotations

import argparse
import base64
import subprocess
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemini  # noqa: E402
import audio  # noqa: E402
from audio import inicio_do_texto  # noqa: E402

try:
    sys.path.append("/Users/joaomarcospiki/Cerebro/scripts")
    from limpar_runtime import registrar_cleanup_no_atexit
except ImportError:
    registrar_cleanup_no_atexit = lambda: None  # noqa: E731

SCRIPT_LABEL = "motion/narracao_tts"
# Reserva com cota própria. Nunca o 2.5: o João rejeitou a voz ("fora do tom, pouco firme", regra V2).
RESERVA = "gemini-3.8-flash-lite-tts"
MESMO_TOM = ("Mantenha exatamente a mesma voz, o mesmo tom, o mesmo ritmo e a mesma energia do começo ao fim, "
             "inclusive depois de qualquer pausa e na última frase. Não interprete personagens: exemplos de mensagem, "
             "falas de cliente ou de vendedor e diálogos são lidos com a mesma voz do narrador, sem mudar timbre, idade ou emoção.")

DIRECAO = (
    "Leia o texto abaixo em português do Brasil, sotaque paulista. Quem fala é um empreendedor de 25 anos "
    "explicando uma ideia pra um amigo, numa conversa. Tom natural, próximo e confiante, com um sorriso na voz "
    "nas partes engraçadas, ritmo de conversa real (acelera um pouco nas listas, respira nas reticências). "
    "Nada de locutor, nada de propaganda, nada de leitura pausada. "
    "Mantenha a mesma voz, o mesmo tom e a mesma energia do começo ao fim, inclusive no final: "
    "não fique mais animado nem mais alto quando se apresentar ou fizer a proposta.\n\n"
)


def blocos(texto: str, maximo: int) -> list[str]:
    paras = [p.strip() for p in texto.split("\n\n") if p.strip()]
    out, atual = [], ""
    for p in paras:
        if atual and len(atual) + len(p) > maximo:
            out.append(atual); atual = ""
        atual = f"{atual}\n\n{p}".strip()
    if atual:
        out.append(atual)
    return out


def pcm_para_wav(pcm: bytes, taxa: str, saida: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", taxa, "-ac", "1", "-i", "-",
                    "-ar", "48000", str(saida)], input=pcm, check=True)
    audio.limpar_cauda_arquivo(saida)  # G10: estalo de "TV falhando" no fim de cada pedido/bloco


def main() -> None:
    registrar_cleanup_no_atexit()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True, type=Path)
    ap.add_argument("--voz", default="Puck")
    ap.add_argument("--motor", default="auto", choices=["auto", "voicestudio", "gemini"])  # auto = o padrão de Configurações (voz.py)
    ap.add_argument("--modelo", default="gemini-3.8-flash-tts")
    ap.add_argument("--max-chars", type=int, default=1100)   # ~1 min de fala: depois de ~1:20 a voz perde o tom (V6)
    a = ap.parse_args()

    texto = (a.pasta / "roteiro.txt").read_text()
    if a.motor != "gemini":   # o Estúdio nunca chama --motor gemini (saiu em 29-out-2026); o código fica só aqui
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import voz as _voz
        # VoiceStudio (grátis, local) ou, só com chave e voz, ElevenLabs; fora do ar sem reserva: erro claro. Saída: audio/voz-bruta.wav
        (a.pasta / "audio").mkdir(exist_ok=True)
        mp3 = a.pasta / "audio" / "voz-bruta.mp3"
        voz_vs = a.voz if a.voz not in ("", "Puck") else None
        print("Voz do Estúdio (VoiceStudio, grátis, ou ElevenLabs): gerando, leva uns minutos")
        try:
            import emocao as _emocao   # emocoes.json ao lado do roteiro.txt: cada frase com a variação da voz daquela emoção
            linhas_emo = _emocao.ler(a.pasta, texto) if (a.pasta / "emocoes.json").is_file() else []
            if a.motor == "voicestudio":
                import voicestudio
                if not voicestudio.no_ar(): raise ValueError(_voz.MSG_VS_FECHADO)
                vid = voz_vs or _voz.status()["voicestudio"]["voz"]
                if linhas_emo: _emocao.narrar(linhas_emo, vid, mp3)
                else: voicestudio.falar(texto, mp3, vid)
            elif linhas_emo and _voz.motor_escolhido() == "voicestudio":
                import voicestudio
                if not voicestudio.no_ar(): raise ValueError(_voz.MSG_VS_FECHADO)
                _emocao.narrar(linhas_emo, voz_vs or _voz.status()["voicestudio"]["voz"], mp3)
            else:
                mp3 = _voz.falar(texto, mp3, voz_vs)
        except ValueError as e:
            sys.exit(str(e))
        saida = a.pasta / "audio" / "voz-bruta.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(saida)], check=True)
        mp3.unlink()
        audio.limpar_cauda_arquivo(saida)
        print(f"ok: {saida}")
        return
    # V7: aspas fazem o TTS interpretar personagem e trocar a voz no meio; a voz lê sem aspas
    for q in '“”"«»': texto = texto.replace(q, '')
    arq_dir = a.pasta / "direcao.txt"
    direcao = arq_dir.read_text().strip() + "\n\n" if arq_dir.exists() else DIRECAO
    # V3: tom único. Direção que pede tom por trecho faz o TTS mudar de voz no meio (v10: escureceu depois de 1:03)
    if arq_dir.exists() and re.search(r"(no come[çc]o|na virada|na proposta|no final|no fim|[úu]ltima frase|mais (baixo|baixa|alto|alta|lento|lenta))", direcao, re.I):
        raise SystemExit("direcao.txt pede tom diferente por trecho (regra V3). Descreva um tom só pro vídeo inteiro.")
    mesmo_tom = MESMO_TOM if audio.LINGUA == "pt" else ("Keep exactly the same voice, tone, pace and energy from start to finish, "
                                                         "including after any pause and on the last sentence.")
    direcao = direcao.rstrip() + " " + mesmo_tom + "\n\n"
    (a.pasta / "audio").mkdir(exist_ok=True)
    tmp = a.pasta / "audio" / "_blocos"
    tmp.mkdir(exist_ok=True)
    partes = blocos(texto, a.max_chars)
    modelos = [a.modelo] + ([RESERVA] if a.modelo != RESERVA else [])
    print(f"{len(partes)} bloco(s), voz {a.voz}")

    arquivos, ref = [], None  # ref = tom (Hz) do 1º bloco: os outros têm que soar iguais
    for k, bloco in enumerate(partes, 1):
        print(f"bloco {k}/{len(partes)} ({len(bloco)} caracteres)")
        wav = tmp / f"{k:02d}.wav"
        if wav.exists() and wav.stat().st_size > 0:  # bloco pronto de uma tentativa anterior (a API caiu no meio)
            print("  já existe, reaproveitando")
            arquivos.append(wav)
            ref = ref or (audio.tom_mediano(wav) if len(partes) > 1 else None)
            continue
        corpo = {
            "contents": [{"parts": [{"text": direcao + bloco}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": a.voz}}}},
        }
        melhor = None  # (desvio, arquivo)
        for tentativa in range(1, 4 if len(partes) > 1 else 2):   # até 2 refações por bloco (conta paga desde 01-out)
            dados, _ = gemini.gerar(corpo, modelos, SCRIPT_LABEL, "tts_roteiro")
            parte = dados["candidates"][0]["content"]["parts"][0]["inlineData"]
            taxa = parte.get("mimeType", "").split("rate=")[1].split(";")[0] if "rate=" in parte.get("mimeType", "") else "24000"
            novo = tmp / f"{k:02d}-novo{tentativa}.wav"  # só vira NN.wav depois de limpo: reaproveitar nunca pega bloco pela metade
            pcm_para_wav(base64.b64decode(parte["data"]), taxa, novo)
            if len(partes) == 1:
                melhor = (0.0, novo)
                break
            # em bloco: a direção lida em voz alta sai no começo, e o estalo de "TV falhando" sai no fim
            corte, fim = inicio_do_texto(novo, bloco), audio.fim_do_texto(novo, bloco)
            if corte or fim:
                limpo = tmp / f"{k:02d}-limpo.wav"
                filtro = f"atrim=0:{fim - corte},afade=t=out:st={max(0.0, fim - corte - 0.08)}:d=0.08" if fim else "anull"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(corte), "-i", str(novo), "-af", filtro, str(limpo)], check=True)
                limpo.replace(novo)
            tom = audio.tom_mediano(novo)
            desvio = abs(tom - ref) / ref if ref else 0.0
            print(f"  tom {tom:.0f} Hz" + (f" (1º bloco {ref:.0f} Hz, desvio {desvio:.0%})" if ref else ""))
            # S5d: duração fora do esperado = leu a direção em voz alta no meio, repetiu ou cortou o fim.
            # Fala do narrador ~16 caracteres por segundo; fora de 0,75-1,3 x o esperado, refaz.
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(novo)],
                                       capture_output=True, text=True).stdout or 0)
            razao = dur / (len(bloco) / 16.0)
            if not 0.75 <= razao <= 1.3:
                print(f"  duração {dur:.0f}s fora do esperado ({razao:.2f}x): direção lida, repetição ou corte, gerando de novo")
                desvio = max(desvio, 1.0 + abs(razao - 1))
            if melhor is None or desvio < melhor[0]:
                melhor = (desvio, novo)
            if desvio <= 0.06:  # mesma voz: aceita (V6: blocos de 1 min já evitam a deriva)
                break
            print("  voz diferente do 1º bloco, gerando de novo")
        melhor[1].replace(wav)
        ref = ref or (audio.tom_mediano(wav) if len(partes) > 1 else None)
        arquivos.append(wav)

    # O 1º bloco é a régua de tom; se ele mesmo saiu fora do padrão (The Binge Files 005: 177 Hz contra ~147 Hz do resto),
    # todos os outros são refeitos à toa e o gancho fica com outra voz. Confere contra a mediana dos demais e refaz só o 1º.
    if len(arquivos) > 2:
        tons = sorted(audio.tom_mediano(w) for w in arquivos[1:])
        mediana = tons[len(tons) // 2]
        t1 = audio.tom_mediano(arquivos[0])
        if abs(t1 - mediana) / mediana > 0.06:
            print(f"1º bloco {t1:.0f} Hz fora da mediana dos outros ({mediana:.0f} Hz): refazendo o 1º bloco")
            bloco = partes[0]
            corpo = {"contents": [{"parts": [{"text": direcao + bloco}]}],
                     "generationConfig": {"responseModalities": ["AUDIO"],
                                          "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": a.voz}}}}}
            melhor = (abs(t1 - mediana) / mediana, arquivos[0])
            for tentativa in range(1, 4):
                dados, _ = gemini.gerar(corpo, modelos, SCRIPT_LABEL, "tts_roteiro")
                parte = dados["candidates"][0]["content"]["parts"][0]["inlineData"]
                taxa = parte.get("mimeType", "").split("rate=")[1].split(";")[0] if "rate=" in parte.get("mimeType", "") else "24000"
                novo = tmp / f"01-ref{tentativa}.wav"
                pcm_para_wav(base64.b64decode(parte["data"]), taxa, novo)
                corte, fim = inicio_do_texto(novo, bloco), audio.fim_do_texto(novo, bloco)
                if corte or fim:
                    limpo = tmp / "01-limpo.wav"
                    filtro = f"atrim=0:{fim - corte},afade=t=out:st={max(0.0, fim - corte - 0.08)}:d=0.08" if fim else "anull"
                    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(corte), "-i", str(novo), "-af", filtro, str(limpo)], check=True)
                    limpo.replace(novo)
                dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(novo)],
                                           capture_output=True, text=True).stdout or 0)
                if not 0.75 <= dur / (len(bloco) / 16.0) <= 1.3:
                    continue
                desvio = abs(audio.tom_mediano(novo) - mediana) / mediana
                print(f"  tentativa {tentativa}: desvio {desvio:.0%}")
                if desvio < melhor[0]:
                    melhor = (desvio, novo)
                if desvio <= 0.06:
                    break
            if melhor[1] != arquivos[0]:
                melhor[1].replace(arquivos[0])

    saida = a.pasta / "audio" / "voz-bruta.wav"
    if len(arquivos) == 1:
        arquivos[0].replace(saida)
    else:
        respiro = tmp / "respiro.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                        "-t", "0.4", str(respiro)], check=True)
        lista = tmp / "lista.txt"
        seq = [x for w in arquivos for x in (w, respiro)][:-1]
        lista.write_text("".join(f"file '{p.name}'\n" for p in seq))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
                        "-c", "copy", str(saida)], check=True)
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    print(f"ok: {saida}")


if __name__ == "__main__":
    main()
