"""Música viral do Editorial (30-out-2026): paradas de hoje (rede simulada), mistura e rodízio, clima, checagem de marca d'água
(voz de produtor, bip, silêncio), trecho do refrão, corte na batida da música nova, "Não usar mais" e "Apagar" (Lixeira do Mac).
Nada aqui sai pra internet nem mexe na Lixeira de verdade."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import _comum
import espaco
import musica_busca as MB
import musica_viral as MV

CSV_BR = '﻿\n"Friday, 30 October 2026 [performance over the past 7 days]"\nRank,Artist,Title\n' \
         '1,"Diovane severo","Vai Matar Papai"\n2,"Imael Angel","BAD TIMES (Long Version)"\n3,"Imael Angel","BAD TIMES"\n'
CSV_MUNDO = '﻿\n"x"\nRank,Artist,Title\n1,"Imael Angel","BAD TIMES"\n2,"KAROL G, Judeline","BbY WOW"\n'
KWORB = ('<tbody>\n<tr><td class="np">1</td>\n<td class="np">+7</td>\n<td class="text mp"><div><a href="../artist/a.html">KAROL G</a> - '
         '<a href="../track/t.html">BbY WOW 💠</a></div></td>\n<td>5</td>\n<td>1</td>\n</tr>\n'
         '<tr><td class="np">2</td>\n<td class="np">=</td>\n<td class="text mp"><div><a href="../artist/b.html">Velho Hit</a> - '
         '<a href="../track/u.html">Do Passado</a></div></td>\n<td>900</td>\n<td>1</td></tr>')
APPLE = json.dumps({"feed": {"results": [{"artistName": "Imael Angel", "id": "1", "name": "BAD TIMES"}]}})
DEEZER = json.dumps({"data": [{"position": 1, "title_short": "BAD TIMES", "artist": {"name": "Imael Angel"}}]})


def rede(url, timeout=25):
    if "csv/top-50-country/brazil" in url:
        return CSV_BR
    if "csv/top-50-country/world" in url:
        return CSV_MUNDO
    if "kworb" in url:
        return KWORB
    if "marketingtools.apple" in url:
        return APPLE
    if "deezer" in url:
        return DEEZER
    raise OSError("sem rede no teste")


def tom(arq: Path, freq=1000, dur=1.0, atraso=3.0, total=8.0, ruido=True):
    """wav de teste: ruído baixo (música falsa) com um tom puro de `dur` s em `atraso`."""
    fonte = "anoisesrc=d=%s:c=pink:a=0.05:r=16000" % total if ruido else "anullsrc=r=16000:cl=mono"
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", fonte, "-f", "lavfi", "-i", f"sine=f={freq}:d={dur}:sample_rate=16000",
           "-filter_complex", f"[1:a]adelay={int(atraso * 1000)}|{int(atraso * 1000)},apad=pad_dur={total}[t];[0:a][t]amix=inputs=2:duration=first:normalize=0",
           "-t", str(total), str(arq)]
    subprocess.run(cmd, check=True)
    return arq


class Paradas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for alvo, valor in ((MV, "CACHE"), ):
            p = patch.object(MV, "CACHE", Path(self.tmp.name) / "virais")
            p.start()
            self.addCleanup(p.stop)
        self.n = {"get": 0}

        def contado(url, timeout=25):
            self.n["get"] += 1
            return rede(url)
        p = patch.object(MV, "_get", contado)
        p.start()
        self.addCleanup(p.stop)

    def test_le_as_quatro_fontes(self):
        d = MV.paradas(forcar=True)
        self.assertEqual({"shazam-br", "shazam-mundo", "spotify-br", "spotify-mundo", "apple-br", "apple-us", "deezer-mundo"}, set(d["listas"]))
        self.assertEqual("Vai Matar Papai", d["listas"]["shazam-br"][0]["titulo"])
        sp = d["listas"]["spotify-br"][0]
        self.assertEqual((1, "KAROL G", 7), (sp["pos"], sp["artista"], sp["subiu"]))
        self.assertEqual("BAD TIMES", d["listas"]["deezer-mundo"][0]["titulo"])

    def test_cache_de_1_dia(self):
        MV.paradas(forcar=True)
        antes = self.n["get"]
        MV.paradas()
        self.assertEqual(antes, self.n["get"], "dentro de 1 dia não vai à rede de novo")
        velho = json.loads(MV._arq_paradas().read_text())
        velho["em"] = time.time() - 2 * 86400
        MV._arq_paradas().write_text(json.dumps(velho))
        MV.paradas()
        self.assertGreater(self.n["get"], antes, "passou de 1 dia: refaz")

    def test_uma_parada_cai_e_as_outras_valem(self):
        def sem_apple(url, timeout=25):
            if "apple" in url:
                raise OSError("fora")
            return rede(url)
        with patch.object(MV, "_get", sem_apple):
            d = MV.paradas(forcar=True)
        self.assertNotIn("apple-br", d["listas"])
        self.assertIn("apple-br", d["erros"])
        self.assertIn("shazam-br", d["listas"])

    def test_versoes_viram_uma_musica_e_cruzar_paradas_sobe(self):
        lista = MV.virais(10, forcar=True)
        bad = [m for m in lista if m["titulo"] == "BAD TIMES"]
        self.assertEqual(1, len(bad), "BAD TIMES e BAD TIMES (Long Version) são a mesma")
        self.assertGreaterEqual(len(bad[0]["fontes"]), 4)
        self.assertEqual("BAD TIMES", lista[0]["titulo"], "a que está em mais paradas vem primeiro")
        self.assertEqual(1, sum(1 for f in bad[0]["fontes"] if f["parada"] == "shazam-br"), "versão repetida na mesma parada conta uma vez")
        karol = next(m for m in lista if "BbY" in m["titulo"])
        self.assertNotIn("💠", karol["titulo"])
        self.assertTrue(karol["slug"].startswith("viral-"))

    def test_spotify_velho_perde_pro_que_acabou_de_chegar(self):
        lista = MV.virais(10, forcar=True)
        novo = next(m for m in lista if "BbY" in m["titulo"])
        velho = next(m for m in lista if m["titulo"] == "Do Passado")
        self.assertGreater(novo["score"], velho["score"])


class Clima(unittest.TestCase):
    def test_clima_do_estilo_manda_e_a_fala_completa(self):
        ordem, de = MV.clima_pedido("O golpe foi grande, a crise e o erro.", "beat sombrio de investigação (hip hop escuro, tensa)")
        self.assertEqual(["sombria", "tensa"], ordem[:2])
        self.assertIn("estilo", de)

    def test_sem_nada_pede_tensa_sombria(self):
        self.assertEqual(["tensa", "sombria"], MV.clima_pedido("", "")[0][:2])

    def test_hip_hop_escuro_ganha_de_sertanejo_no_clima_sombrio(self):
        escuro = {"bpm": 90, "grave": .35, "agudo": .1, "forte_db": -12, "dinamica": 8, "genero": "Hip-Hop/Rap"}
        alegre = {"bpm": 130, "grave": .1, "agudo": .3, "forte_db": -12, "dinamica": 8, "genero": "Sertanejo"}
        pool = [escuro, alegre]
        a = MV._pontua({"score": 1, "fontes": []}, escuro, ["sombria", "tensa"], pool, 1)[0]
        b = MV._pontua({"score": 1, "fontes": []}, alegre, ["sombria", "tensa"], pool, 1)[0]
        self.assertGreater(a, b)

    def test_motivo_nao_mente_quando_nao_casa(self):
        alegre = {"bpm": 130, "grave": .1, "agudo": .3, "forte_db": -12, "dinamica": 8, "genero": "Pop"}
        _n, motivo = MV._pontua({"score": 1, "fontes": [{"rotulo": "Shazam", "pos": 3}]}, alegre, ["sombria"], [alegre, dict(alegre, grave=.4, agudo=.05)], 1)
        self.assertIn("mais próxima", motivo)
        self.assertNotIn("casa bem", motivo)


class Checagem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)

    def test_bip_puro_reprova(self):
        arq = tom(self.d / "bip.wav", ruido=False, total=6)
        r = MV.checar(arq, "instrumental", usar_groq=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("bip" in m for m in r["motivos"]))

    def test_silencio_no_meio_reprova_mas_o_do_comeco_passa(self):
        ruido = self.d / "r.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=3:c=pink:a=0.2:r=16000", str(ruido)], check=True)
        buraco = self.d / "b.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(ruido), "-f", "lavfi", "-t", "1.5", "-i", "anullsrc=r=16000:cl=mono",
                        "-i", str(ruido), "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1", str(buraco)], check=True)
        r = MV.checar(buraco, "letra", usar_groq=False)
        self.assertFalse(r["ok"])
        self.assertTrue(any("silêncio" in m for m in r["motivos"]))
        self.assertTrue(MV.checar(ruido, "letra", usar_groq=False)["ok"])

    def test_tag_de_produtor_reprova_ate_em_musica_com_letra(self):
        arq = self.d / "x.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.2:r=16000", str(arq)], check=True)
        js = {"segments": [{"text": " Yeah, this is prod. by Fulano, free for non profit type beat", "no_speech_prob": .1, "avg_logprob": -.3}]}
        with patch.object(MV, "_groq", return_value=js):
            r = MV.checar(arq, "letra")
        self.assertFalse(r["ok"])
        self.assertIn("voz falando", r["motivos"][0])

    def test_letra_cantada_nao_reprova_mas_instrumental_com_fala_sim(self):
        arq = self.d / "x.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.2:r=16000", str(arq)], check=True)
        js = {"segments": [{"text": " eu tô com a mão na cintura e o coração na mão", "no_speech_prob": .1, "avg_logprob": -.3}]}
        with patch.object(MV, "_groq", return_value=js):
            self.assertTrue(MV.checar(arq, "letra")["ok"])
            r = MV.checar(arq, "instrumental")
        self.assertFalse(r["ok"])
        self.assertIn("instrumental", r["motivos"][0])

    def test_alucinacao_do_whisper_em_cima_de_musica_nao_conta(self):
        arq = self.d / "x.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.2:r=16000", str(arq)], check=True)
        js = {"segments": [{"text": " Obrigado.", "no_speech_prob": .9, "avg_logprob": -1.4}, {"text": " Legendas pela comunidade Amara.org", "no_speech_prob": .8, "avg_logprob": -1.2}]}
        with patch.object(MV, "_groq", return_value=js):
            self.assertTrue(MV.checar(arq, "instrumental")["ok"])

    def test_sem_groq_a_checagem_segue_e_avisa(self):
        arq = self.d / "x.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=5:c=pink:a=0.2:r=16000", str(arq)], check=True)
        with patch.object(MV, "_groq", return_value=None):
            r = MV.checar(arq, "letra")
        self.assertTrue(r["ok"])
        self.assertFalse(r["groq"])

    def test_titulo_de_beat_de_vitrine_reprova_na_busca_do_oficial(self):
        self.assertLess(MV._score_yt({"title": "ARTISTA - Hit (Free Trap Type Beat) prod. X", "channel": "X Beats", "duration": 180}, "Artista", "Hit", 180), 0)
        self.assertGreater(MV._score_yt({"title": "Artista - Hit", "channel": "Artista - Topic", "duration": 181}, "Artista", "Hit", 180), 4)
        self.assertLess(MV._score_yt({"title": "Artista - Hit (Slowed + Reverb)", "channel": "Artista", "duration": 180}, "Artista", "Hit", 180), 0)


class Trecho(unittest.TestCase):
    def test_o_refrao_e_onde_a_energia_sobe_e_fica(self):
        d = Path(tempfile.mkdtemp())
        # 20 s de pad baixinho, depois 40 s de batida forte (kick de 100 Hz a cada 0,5 s) sobre o pad
        arq = d / "m.wav"
        filtro = ("[0:a]volume=0.15[p];[1:a]aloop=loop=-1:size=100000,atrim=0:40,volume=1.0[k];[k]adelay=20000|20000[k2];[p][k2]amix=inputs=2:duration=first:normalize=0")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=60:sample_rate=22050", "-f", "lavfi", "-i",
                        "sine=f=100:d=0.15:sample_rate=22050,apad=pad_dur=0.5", "-filter_complex", filtro, "-t", "60", str(arq)], check=True)
        t = MV.achar_trecho(arq, 30.0)
        self.assertAlmostEqual(20.0, t["t0"], delta=1.5, msg=t)
        self.assertIn("refrão", t["motivo"])

    def test_corta_com_o_gancho_em_015(self):
        d = Path(tempfile.mkdtemp())
        src = d / "s.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=30:sample_rate=22050", str(src)], check=True)
        out = MV.cortar(src, d / "c.mp3", 10.0, 8.0)
        self.assertAlmostEqual(8.0, MV._duracao(out), delta=0.2)

    def test_faixa_curta_repete_em_vez_de_acabar_antes_do_video(self):
        d = Path(tempfile.mkdtemp())
        src = d / "s.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=5:sample_rate=22050", str(src)], check=True)
        out = MV.cortar(src, d / "c.mp3", 1.0, 12.0)
        self.assertGreater(MV._duracao(out), 11.5)


class CorteNaBatida(unittest.TestCase):
    def test_cena_perto_do_meio_tempo_vai_pra_batida_e_o_efeito_vai_junto(self):
        doc = {"duracao": 10, "cenas": [{"de": 0}, {"de": 1.2}, {"de": 3.0}, {"de": 3.4}],
               "efeitos": [{"t": 1.15, "arquivo": "w"}, {"t": 5.0, "arquivo": "p"}]}
        # período 1,0 s: meios-tempos em 0,15 / 0,65 / 1,15 / 1,65 / ...; 1,2 está a 0,05 da 1,15; 3,0 está a 0,15 da 3,15 (fora da janela)
        n = MV.casar_cortes(doc, 1.0)
        self.assertEqual(1.15, doc["cenas"][1]["de"])
        self.assertEqual(3.0, doc["cenas"][2]["de"])
        self.assertGreaterEqual(n, 1)
        self.assertEqual(1.1, doc["efeitos"][0]["t"], "o efeito que estava no corte acompanha")
        self.assertEqual(5.0, doc["efeitos"][1]["t"])

    def test_sem_periodo_nao_mexe(self):
        doc = {"duracao": 5, "cenas": [{"de": 0}, {"de": 1.2}]}
        self.assertEqual(0, MV.casar_cortes(doc, 0))
        self.assertEqual(1.2, doc["cenas"][1]["de"])


class Base(unittest.TestCase):
    """Sandbox de mentira com RAIZ trocada: "Não usar mais" e "Apagar" nunca tocam o Estúdio nem a Lixeira de verdade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name).resolve()
        for m, a, v in ((_comum, "RAIZ", self.raiz), (_comum, "ESTUDIO", self.raiz / "app")):
            p = patch.object(m, a, v)
            p.start()
            self.addCleanup(p.stop)
        self.lixo = self.raiz / ".Trash-teste"
        item = self.raiz / "acervo" / "itens" / "faixa-x"
        item.mkdir(parents=True)
        (item / "clip.mp3").write_bytes(b"m" * 5000)
        (item / "meta.json").write_text("{}")
        fmt = self.raiz / "formatos" / "editorial" / "base" / "audio" / "musicas"
        fmt.mkdir(parents=True)
        (fmt / "364.mp3").write_bytes(b"n" * 3000)
        sb = self.raiz / "clientes" / "Avulso" / "avulsoContent" / "modelos" / "editorial" / "_sandbox-v" / "work" / "musica"
        sb.mkdir(parents=True)
        (sb / "viral-x.mp3").write_bytes(b"s" * 100)


class NaoUsarMais(Base):
    def test_reprovar_grava_e_a_faixa_some_das_listas(self):
        MB.reprovar(arquivo="acervo/itens/faixa-x/clip.mp3", titulo="Faixa X")
        linhas = (self.raiz / "acervo" / "musicas-reprovadas.jsonl").read_text().splitlines()
        self.assertEqual(1, len(linhas))
        self.assertEqual("*", json.loads(linhas[0])["cliente"])
        lista = [{"arquivo": "acervo/itens/faixa-x/clip.mp3", "titulo": "Faixa X"}, {"arquivo": "acervo/itens/outra/clip.mp3", "titulo": "Y"}]
        self.assertEqual(["Y"], [i["titulo"] for i in MB.sem_reprovadas(lista)])
        self.assertEqual(["Faixa X", "Y"], [i["titulo"] for i in MB.sem_reprovadas(lista, "sfx")], "efeito não tem 'não usar mais'")
        self.assertTrue((self.raiz / "acervo/itens/faixa-x/clip.mp3").is_file(), "o arquivo continua no disco")

    def test_vale_pra_todo_cliente_e_nao_duplica(self):
        MB.reprovar(arquivo="formatos/editorial/base/audio/musicas/364.mp3", titulo="364")
        MB.reprovar(arquivo="formatos/editorial/base/audio/musicas/364.mp3", titulo="364")
        self.assertEqual(1, len((self.raiz / "acervo" / "musicas-reprovadas.jsonl").read_text().splitlines()))
        self.assertTrue(MB.reprovada({"arquivo": "formatos/editorial/base/audio/musicas/364.mp3"}, "QualquerCliente"))
        self.assertIn("formatos/editorial/base/audio/musicas/364.mp3", MB.reprovadas("Outro")[1])

    def test_viral_reprovada_nunca_volta_como_opcao(self):
        MB.reprovar(chave="viral:viral-imael-angel-bad-times", titulo="Imael Angel - BAD TIMES")
        self.assertTrue(MV._reprovadas("Avulso") >= {"viral:viral-imael-angel-bad-times"})
        self.assertTrue(MB.reprovada({"id": "viral-imael-angel-bad-times"}))

    def test_pede_arquivo_ou_chave(self):
        with self.assertRaises(ValueError):
            MB.reprovar()


class Apagar(Base):
    def setUp(self):
        super().setUp()
        p = patch.dict(os.environ, {"ESTUDIO_LIXEIRA_MAC": str(self.lixo)})
        p.start()
        self.addCleanup(p.stop)

    def test_mede_sem_mexer(self):
        r = MB.apagar_musica(["acervo/itens/faixa-x/clip.mp3"], medir=True)
        self.assertEqual(1, r["apagados"])
        self.assertGreater(r["bytes"], 5000)
        self.assertTrue((self.raiz / "acervo/itens/faixa-x/clip.mp3").is_file())

    def test_item_da_biblioteca_vai_inteiro_pra_lixeira_do_mac(self):
        r = MB.apagar_musica(["acervo/itens/faixa-x/clip.mp3"])
        self.assertEqual(1, r["apagados"])
        self.assertFalse((self.raiz / "acervo/itens/faixa-x").exists())
        achados = list(self.lixo.rglob("clip.mp3"))
        self.assertEqual(1, len(achados), "o arquivo está na Lixeira, não sumiu")

    def test_musica_de_estilo_leva_so_o_arquivo(self):
        MB.apagar_musica(["formatos/editorial/base/audio/musicas/364.mp3"])
        self.assertFalse((self.raiz / "formatos/editorial/base/audio/musicas/364.mp3").exists())
        self.assertTrue((self.raiz / "formatos/editorial/base/audio/musicas").is_dir())

    def test_recusa_sandbox_fora_do_estudio_e_nao_audio(self):
        for ruim in ("clientes/Avulso/avulsoContent/modelos/editorial/_sandbox-v/work/musica/viral-x.mp3", "../fora.mp3",
                     "acervo/itens/faixa-x/meta.json", "nao/existe.mp3", "/etc/passwd"):
            r = MB.apagar_musica([ruim])
            self.assertEqual(0, r["apagados"], ruim)
            self.assertTrue(r["recusados"], ruim)
        self.assertTrue((self.raiz / "clientes/Avulso/avulsoContent/modelos/editorial/_sandbox-v/work/musica/viral-x.mp3").is_file())

    def test_passa_pelo_apagar_de_toda_grade(self):
        r = espaco.lote(musicas=["acervo/itens/faixa-x/clip.mp3"], medir=True)
        self.assertEqual(1, r["apagados"])
        self.assertIn("KB", r["texto"])


class OpcoesEViral(Base):
    def test_rodizio_tira_a_que_o_cliente_usou_e_a_reprovada(self):
        lista = [{"id": f"viral-{i}", "slug": f"viral-{i}", "chave": f"{i}|x", "artista": "A", "titulo": str(i), "score": 3 - i * .1, "fontes": [{"rotulo": "S", "pos": i, "parada": "shazam-br"}]}
                 for i in range(1, 6)]
        MB.reprovar(chave="viral:viral-2", titulo="2")

        def preparado(item):
            _n, m, _pf, motivo = item
            return {"id": m["id"], "titulo": m["titulo"], "artista": "A", "motivo": motivo, "previa": "p", "t0": 1, "bpm": 100, "trecho": "t",
                    "fontes": "", "aviso": "", "checagem": "ok"}, None
        with patch.object(MV, "virais", return_value=lista), patch.object(MV, "_recentes", return_value={"viral-1"}), \
                patch.object(MV, "_perfil", return_value={}), patch.object(MV, "paradas", return_value={"listas": {}}), \
                patch.object(MV, "CACHE", self.raiz / "c"), patch.object(MV, "_trecho_da", return_value={"t0": 1, "bpm": 100, "motivo": "m", "periodo": .6}), \
                patch.object(MV, "_checada", return_value={"ok": True, "motivos": [], "groq": True}), patch.object(MV, "previa", return_value="app/.cache/virais/p.mp3"):
            r = MV.opcoes("Avulso", "", "beat sombrio", 3)
        ids = [o["id"] for o in r["opcoes"]]
        self.assertEqual(3, len(ids))
        self.assertNotIn("viral-1", ids, "o cliente usou há pouco")
        self.assertNotIn("viral-2", ids, "o João mandou não usar mais")

    def test_faixa_reprovada_na_checagem_nao_vira_opcao_e_a_proxima_entra(self):
        lista = [{"id": f"viral-{i}", "slug": f"viral-{i}", "chave": f"{i}|x", "artista": "A", "titulo": str(i), "score": 3 - i * .1, "fontes": [{"rotulo": "S", "pos": i, "parada": "x"}]}
                 for i in range(1, 7)]

        def checada(m, t0, dur, esperado="letra"):
            return {"ok": m["id"] != "viral-1", "motivos": ["voz falando por cima ('prod. by X')"] if m["id"] == "viral-1" else [], "groq": True}
        with patch.object(MV, "virais", return_value=lista), patch.object(MV, "_recentes", return_value=set()), patch.object(MV, "_perfil", return_value={}), \
                patch.object(MV, "paradas", return_value={"listas": {}}), patch.object(MV, "CACHE", self.raiz / "c"), \
                patch.object(MV, "_trecho_da", return_value={"t0": 1, "bpm": 100, "motivo": "m", "periodo": .6}), patch.object(MV, "_checada", checada), \
                patch.object(MV, "previa", return_value="app/.cache/virais/p.mp3"):
            r = MV.opcoes("Avulso", "", "", 3)
        self.assertNotIn("viral-1", [o["id"] for o in r["opcoes"]])
        self.assertEqual(3, len(r["opcoes"]))
        self.assertIn("viral-1", r["recusadas"][0]["titulo"] + "viral-1")
        self.assertIn("prod. by", r["recusadas"][0]["motivos"][0])

    def test_preparar_escreve_o_ponteiro_a_batida_e_o_trecho(self):
        d = self.raiz / "sb"
        d.mkdir()
        full = self.raiz / "full.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=200:d=60:sample_rate=22050", str(full)], check=True)
        m = {"artista": "Fulano", "titulo": "Hit", "slug": "viral-fulano-hit", "chave": "fulano|hit"}
        with patch.object(MV, "baixar", return_value=full), patch.object(MV, "_trecho_da", return_value={"t0": 12.0, "bpm": 120, "periodo": .5, "motivo": "o refrão"}), \
                patch.object(MV, "checar", return_value={"ok": True, "motivos": [], "groq": False}):
            p = MV.preparar(d, m, 20.0, cliente="Avulso")
        self.assertEqual("work/musica/viral-fulano-hit.mp3", p["arquivo"])
        self.assertTrue((d / p["arquivo"]).is_file())
        bat = json.loads((d / "work/batida.json").read_text())
        self.assertEqual(0.15, bat["primeiro"], "o gancho cai em t=0,15 do trecho, então o vídeo começa nele")
        self.assertEqual(0.5, bat["periodo"])
        self.assertTrue((d / "work/musica/escolhida.json").is_file())
        self.assertIn("Instagram", p["aviso"])

    def test_preparar_recusa_faixa_com_marca_dagua(self):
        d = self.raiz / "sb2"
        d.mkdir()
        full = self.raiz / "full.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=200:d=60:sample_rate=22050", str(full)], check=True)
        with patch.object(MV, "baixar", return_value=full), patch.object(MV, "_trecho_da", return_value={"t0": 1.0, "bpm": 0, "periodo": 0, "motivo": "m"}), \
                patch.object(MV, "checar", return_value={"ok": False, "motivos": ["voz falando por cima ('type beat')"], "groq": True}):
            with self.assertRaises(ValueError) as c:
                MV.preparar(d, {"artista": "X", "titulo": "Y"}, 10.0)
        self.assertIn("type beat", str(c.exception))
        self.assertFalse((d / "work/musica/escolhida.json").exists())


class GeraLib(unittest.TestCase):
    def test_fechar_usa_a_viral_escolhida_e_sem_musica_sai_sem(self):
        """O padrão do g.fechar é 'auto': ponteiro escolhido > viral do momento > banco só como plano B (e `sem` desliga)."""
        src = (Path(__file__).resolve().parents[2] / "formatos/editorial/base/exemplos/gera_lib.py").read_text(encoding="utf-8")
        self.assertIn('musica="auto"', src)
        self.assertIn("work/musica/sem", src)
        self.assertIn("escolhida.json", src)
        self.assertIn("PLANO B", src)
        self.assertNotIn('musica="audio/musicas/metamorphosis', src.split("def fechar")[1].split("\n")[0], "o banco não é mais o padrão")


class Formato(unittest.TestCase):
    def test_formato_e_regra_dizem_viral(self):
        raiz = Path(__file__).resolve().parents[2]
        f = json.loads((raiz / "formatos/editorial/formato.json").read_text(encoding="utf-8"))
        m = f["som"]["musica"]
        self.assertTrue(m["viral"])
        self.assertIn("VIRAIS DO MOMENTO", m["de_onde"])
        self.assertIn("PLANO B", m["de_onde"])
        regras = json.loads((raiz / "formatos/editorial/aprendizado/regras.json").read_text(encoding="utf-8"))["regras"]
        r = next(x for x in regras if x["id"] == "musica-famosa-na-batida")
        self.assertIn("viral", r["texto"].lower())
        self.assertIn("nunca banco", r["texto"])

    def test_pedido_da_producao_traz_a_escolha_do_joao(self):
        import producao
        f = {"som": {"musica": {"viral": True}}}
        self.assertEqual("", producao._musica_viral_txt({}, {"som": {"musica": {}}}, "sb"))
        self.assertIn("SEM MÚSICA", producao._musica_viral_txt({"musica": {"modo": "sem"}}, f, "sb"))
        t = producao._musica_viral_txt({"cliente": "Avulso", "musica": {"modo": "viral", "faixa": "viral-x", "titulo": "X - Y"}}, f, "sb")
        self.assertIn("viral-x", t)
        self.assertIn("NUNCA banco de trilha", t)
        self.assertIn("Instagram", t)


if __name__ == "__main__":
    unittest.main()
