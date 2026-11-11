#!/usr/bin/env python3
"""Passo PADRÃO do dividido-mascara (regra 'revisar-transcricao-groq').

1) Corta alucinação de cauda do whisper (créditos tipo "Legenda por ...", palavra
   com start além da duração real do áudio).
2) Capitalização: só fica maiúscula a 1ª palavra do vídeo, a palavra depois de
   '.'/'?'/'!' e siglas conhecidas. Qualquer outra maiúscula do meio vira minúscula.

Uso: normaliza-words.py words.json [--dur 59.5]
"""
import json, re, sys, argparse

SIGLAS = {"IA", "ADM", "CPF", "CNPJ", "CEO", "IG", "SP", "RJ", "US", "EUA"}
LIXO = re.compile(r"legenda por|amara\.org|subtitl|revis[aã]o", re.I)

ap = argparse.ArgumentParser()
ap.add_argument("arquivo")
ap.add_argument("--dur", type=float, default=None)
a = ap.parse_args()

d = json.load(open(a.arquivo))
ws = d["words"]

# 1) cauda alucinada
if a.dur:
    ws = [w for w in ws if float(w["start"]) <= a.dur + 0.2]
txt_tail = " ".join(w["word"] for w in ws[-6:])
if LIXO.search(txt_tail):
    while ws and LIXO.search(" ".join(x["word"] for x in ws[-6:])):
        ws.pop()

# 2) capitalização
prev_end_sentence = True
mudou = []
for w in ws:
    t = w["word"].strip()
    core = t.strip(" .,!?;:")
    if core and core[0].isupper() and core.upper() not in SIGLAS and not prev_end_sentence:
        novo = t[0].lower() + t[1:]
        if novo != t:
            mudou.append((t, novo))
        w["word"] = novo
    prev_end_sentence = t.endswith((".", "?", "!"))

d["words"] = ws
d["text"] = " ".join(w["word"].strip() for w in ws)
json.dump(d, open(a.arquivo, "w"), ensure_ascii=False)
print(f"palavras={len(ws)}  minusculizadas={len(mudou)} -> {[m[0] for m in mudou]}")
