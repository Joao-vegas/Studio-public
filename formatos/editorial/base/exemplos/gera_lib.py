# Biblioteca do gera.py do Editorial: o que é igual em todo vídeo (tempo por palavra, cursor da fala, clipe com som,
# plano longo vira dois, corte na batida, efeitos, cenas.json). O gera.py de cada vídeo só lista as cenas (ver gera-modelo.py).
import difflib, json, re, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
norm = lambda s: re.sub(r"[^\wçãõáéíóúâêô]", "", s.lower())


class G:
    def __init__(self, arquivo):
        self.aqui = Path(arquivo).resolve().parent
        # entrada por VÍDEO (Editorial falado): a voz e o tempo das palavras são os dele, em work/fala/ (preparar-fala.py); senão, os da narração
        self.falado = (self.aqui / "work/fala/words.json").is_file()
        self.voz, self.pal = ("work/fala/voz.wav", "work/fala/words.json") if self.falado else ("work/voz.wav", "work/words.json")
        self.W = json.loads((self.aqui / self.pal).read_text())["words"]
        self.cur = 0.0

    # ── tempo ──
    def t(self, palavra, apos=0.0, n=1):
        """início da n-ésima palavra igual a `palavra` depois do segundo `apos` (a voz às vezes troca palavra: usa a mais parecida e avisa)"""
        for w in self.W:
            if w["start"] >= apos - .01 and norm(w["word"]) == norm(palavra):
                n -= 1
                if n == 0:
                    return round(w["start"], 3)
        cand = [w for w in self.W if w["start"] >= apos - .01][:12]
        if not cand:
            raise SystemExit(f"palavra não achada: {palavra} depois de {apos}")
        m = max(cand, key=lambda w: difflib.SequenceMatcher(None, norm(w["word"]), norm(palavra)).ratio())
        print(f"aviso: \"{palavra}\" não está na fala depois de {apos:.1f} s; usei \"{m['word']}\" em {m['start']:.2f} s", file=sys.stderr)
        return round(m["start"], 3)

    def a(self, palavra):
        """próxima palavra igual na ordem da fala (o cursor anda): o tempo vem da voz, nunca de estimativa"""
        x = self.t(palavra, self.cur)
        self.cur = x + .01
        return x

    def volta(self, t):
        """põe o cursor de volta em t (pra pegar palavras de uma frase já passada)"""
        self.cur = t + .01

    def tempos(self, texto, de):
        out, ap = [], de
        for p in texto.split():
            x = self.t(p, ap); out.append(x); ap = x + .01
        return out

    # ── cenas ──
    def texto(self, de, txt, forte=(), **k):
        return {"tipo": "texto", "de": de, "texto": txt, "forte": list(forte), "tempos": self.tempos(txt, de), **k}

    def clipe(self, de, nome, som=.32, desde=0, **k):
        """vídeo real: quadros em clipes/q-<nome>/, o som dele entra baixo por baixo da voz (clipe.py baixa)"""
        return {"tipo": "clipe", "de": de, "quadros_de": f"clipes/q-{nome}", "inicio": desde, "_som": (nome, som, desde), **k}

    def fala(self, de, modo="cheia", **k):
        """o João aparecendo (só na entrada por vídeo): `modo` "cheia" (tela cheia, legenda forte) ou "canto" (no cantinho em cima de
        `imagem`, um print ou foto). O vídeo dele sai de work/fala/fala.mp4 no tempo da cena (render.py). `forte`: palavras em vermelho."""
        if not self.falado:
            raise SystemExit("g.fala só vale na entrada por vídeo (rode preparar-fala.py antes)")
        return {"tipo": "fala", "de": de, "modo": modo, **k}

    def foto(self, de, imagem, **k):
        return {"tipo": "foto", "de": de, "imagem": imagem, "mov": k.pop("mov", "in"), **k}

    # ── fechamento ──
    def _musica(self, musica, DUR):
        """A música de fundo do vídeo: (arquivo relativo à sandbox, aviso, meta). `musica="auto"` (padrão): `work/musica/sem` = sem música;
        `work/musica/escolhida.json` = a que o João escolheu no Criar (ou que o musica_viral.py já preparou); senão a 1ª VIRAL DO MOMENTO
        que passa na checagem de marca d'água. Só sem internet cai no banco de trilha (plano B, com aviso). Caminho explícito = esse arquivo."""
        aqui = self.aqui
        if musica != "auto":
            return musica, "", {}
        if (aqui / "work/musica/sem").is_file():
            return None, "", {}
        ptr = aqui / "work/musica/escolhida.json"
        if not ptr.is_file():
            raiz = BASE.parents[2]
            py = raiz / "app/.venv/bin/python"
            cmd = [str(py if py.is_file() else sys.executable), str(raiz / "app/ferramentas/musica_viral.py"), "escolher", str(aqui),
                   "--dur", str(DUR), "--formato", "editorial", "--cliente", aqui.parts[aqui.parts.index("clientes") + 1] if "clientes" in aqui.parts else ""]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode or not ptr.is_file():
                print("aviso: sem viral agora (" + ((r.stderr or r.stdout).strip().splitlines() or ["sem internet?"])[-1][:120] + "): usei o banco de trilha, PLANO B", file=sys.stderr)
                return "audio/musicas/metamorphosis-interworld.mp3", "plano B", {}
        p = json.loads(ptr.read_text())
        return p["arquivo"], "", p

    def fechar(self, c, titulo, saida, musica="auto", marca=None, volume=.08, sfx_vol=1.0):
        W, aqui = self.W, self.aqui
        DUR = round(W[-1]["end"] + .8, 2)
        musica, plano_b, meta = self._musica(musica, DUR)
        mus = next((p for p in (aqui / musica, BASE / musica) if p.is_file()), None) if musica else None
        if musica and not mus:
            raise SystemExit(f"música não encontrada: {musica}")
        bat_p = aqui / "work/batida.json"
        if mus and (plano_b or not bat_p.is_file() or (meta and json.loads(bat_p.read_text()).get("viral") != meta.get("slug"))):
            subprocess.run([sys.executable, str(Path(__file__).with_name("batida.py")), str(mus), str(bat_p)], check=True)
        BAT = json.loads(bat_p.read_text()) if mus else {"periodo": 0, "primeiro": .15}
        INI = BAT["primeiro"] - .15                              # o drop (ou o refrão da viral) cai em t=0,15 do vídeo
        fim = lambda i: c[i + 1]["de"] if i + 1 < len(c) else DUR
        # plano longo vira dois (régua: mediana ~0,5-0,8 s), na palavra mais perto do meio
        novos = []
        for i, x in enumerate(c):
            novos.append(x)
            d = fim(i) - x["de"]
            if x["tipo"] in ("foto", "cartao", "print") and d > 1.15 and not x.get("texto"):
                meio = x["de"] + d / 2
                cand = [w["start"] for w in W if x["de"] + .45 < w["start"] < fim(i) - .45]
                if cand:
                    m = min(cand, key=lambda v: abs(v - meio))
                    fo = x.get("foco", [.5, .5])
                    novos.append(dict(x, de=round(m, 3), mov={"in": "out", "out": "in", "esq": "dir", "dir": "esq"}.get(x.get("mov"), "in"),
                                      foco=[min(.8, max(.2, fo[0] + (.18 if i % 2 else -.18))), fo[1]], forca=1.3, entrada="corte"))
        c = novos
        # corte na batida: cena que começa até 0,12 s depois ou 0,06 s antes de um meio-tempo da música vai pra ele
        meio_tempo = (BAT["periodo"] or 1.0) / 2
        grade = [.15 + k * meio_tempo for k in range(int(DUR / meio_tempo) + 2)]
        for i, x in enumerate(c[1:], 1):
            b = min(grade, key=lambda g: abs(g - x["de"]))
            if mus and -.12 <= b - x["de"] <= .06 and b > c[i - 1]["de"] + .3:
                x["de"] = round(b, 3)
        na_batida = sum(1 for x in c if min(abs(g - x["de"]) for g in grade) < .02) if mus else 0
        # efeitos: só na ação que aparece; o som do clipe do tamanho do plano
        fx = []
        for i, x in enumerate(c):
            so = x.pop("_som", None)
            if so:
                nome, vol, _ = so
                n_q = len(list((aqui / x["quadros_de"]).glob("*.jpg")))
                dur = min(fim(i) - x["de"], (n_q - x["inicio"]) / 30)
                fx.append({"t": x["de"], "arquivo": f"clipes/som-{nome}.mp3", "volume": vol, "dur": round(dur, 2)})
            if x.get("entrada") in ("negativo", "flash", "zoom", "chicote"):
                fx.append({"t": max(0, x["de"] - .05), "arquivo": "audio/sfx/whoosh-short.mp3", "volume": .22})
            if x["tipo"] == "chips":
                fx += [{"t": it["t"], "arquivo": "audio/sfx/pop.mp3", "volume": .18} for it in x["itens"]]
            if x["tipo"] == "colagem":
                fx.append({"t": x["de"], "arquivo": "audio/sfx/pop.mp3", "volume": .18})
            if x["tipo"] == "contador":
                fx.append({"t": x["de"] + .9, "arquivo": "audio/sfx/tique.mp3", "volume": .25})
            if x["tipo"] == "zap":
                fx += [{"t": m["t"], "arquivo": "audio/sfx/notificacao.mp3", "volume": .14} for m in x["msgs"] if not m.get("imagem")]
            if x["tipo"] == "icone":
                fx.append({"t": x["de"], "arquivo": "audio/sfx/click-soft.mp3", "volume": .22})
            if x["tipo"] == "recorte":
                fx += [{"t": x["de"] + p.get("t", 0), "arquivo": "audio/sfx/whoosh-short.mp3", "volume": .14} for p in x["pessoas"]]
        doc = {"titulo": titulo, "saida": saida, "largura": 1080, "altura": 1920, "fps": 30, "voz": self.voz, "palavras": self.pal,
               "duracao": DUR, **({"marca": marca} if marca else {}), **({"fala": "work/fala/fala.mp4"} if self.falado else {}),
               "musica": ({"arquivo": musica, "volume": volume, "inicio_s": round(INI, 3),
                           **({"titulo": meta["titulo"], "artista": meta["artista"], "fonte": "viral", "chave": meta["chave"], "t0": meta["t0"], "aviso": meta["aviso"]} if meta else {})}
                          if mus else {"volume": volume}), "efeitos": fx, "cenas": c}
        (aqui / "cenas.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        # dinamismo (João, 29/10: "tem coisas muito paradas, as pessoas querem dopamina"): número de trocas e o plano mais longo
        ds = sorted((fim(i) - x["de"]) for i, x in enumerate(c))
        longos = [(round(fim(i) - x["de"], 1), x["tipo"], round(x["de"], 1)) for i, x in enumerate(c) if fim(i) - x["de"] > 1.8]
        print(f"{len(c)} cenas · {len(fx)} efeitos · {DUR} s · {na_batida} cortes na batida · {len(c) * 60 / DUR:.0f} trocas/min · "
              f"mediana {ds[len(ds) // 2]:.2f} s · maior {ds[-1]:.1f} s · {len({x['tipo'] for x in c})} tipos de peça")
        if longos:
            print("PARADO? planos acima de 1,8 s (duração, peça, início): ", longos, "-> divida (outra peça, outro enquadramento, clipe, rajada)", file=sys.stderr)
        return doc
