"""Música e voz mais simples (30-out-2026): "Procurar" é a direção em palavras, sem voz cantada, sem o gênero que briga, "Outras 3",
música e efeitos em outros estilos (Documentário lê a escolha), "Meu áudio" na voz. Rede e Demucs simulados."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
sys.path.insert(0, str(RAIZ / "app" / "interface"))
import musica_viral as MV
import producao as P


class Direcao(unittest.TestCase):
    def test_entende_o_pedido_e_sem_voz_e_o_padrao(self):
        d = MV.entender_direcao("tensa de suspense, sem voz")
        self.assertEqual(d["climas"], ["tensa"])
        self.assertIn("suspense", d["termos_en"])
        self.assertTrue(d["sem_voz"])
        self.assertTrue(MV.entender_direcao("algo calmo")["sem_voz"])           # sem dizer nada: sem voz
        self.assertFalse(MV.entender_direcao("animada, com voz cantada")["sem_voz"])
        self.assertEqual(MV.entender_direcao("funk de baile")["generos"], ["funk"])

    def test_genero_que_briga_fica_de_fora_a_menos_que_o_roteiro_fale_dele(self):
        m = {"artista": "MC Fulano", "titulo": "Baile do Complexo"}
        pf = {"genero": "Funk"}
        self.assertEqual(MV.genero_briga(m, pf, "tensa de suspense", "o juiz proibiu o evento"), "funk")
        self.assertEqual(MV.genero_briga(m, pf, "", "como o funk virou negócio de milhões"), "")   # o roteiro fala do funk
        self.assertEqual(MV.genero_briga(m, pf, "funk de baile", ""), "")                          # ele pediu
        self.assertEqual(MV.genero_briga({"artista": "Sombr", "titulo": "back to friends"}, {"genero": "Alternative"}), "")
        self.assertEqual(MV.genero_briga({"artista": "Zé Neto & Cristiano", "titulo": "Cadeira"}, {"genero": "Sertanejo"}), "sertanejo")

    def test_voz_medida_acima_do_limite_tem_voz_e_a_calibracao_separa_as_duas(self):
        com, instr = MV.CALIBRACAO_VOZ["com_voz"], MV.CALIBRACAO_VOZ["instrumental"]
        self.assertTrue(all(c > MV.LIMITE_VOZ_DB for c in com))
        self.assertLess(instr, MV.LIMITE_VOZ_DB)
        with tempfile.TemporaryDirectory() as t, patch.object(MV, "CACHE", Path(t)), patch.object(MV, "_volume_db", return_value=-10.0), \
                patch("subprocess.run"):
            import midia_local
            with patch.object(midia_local, "so_voz", return_value={"rms_voz_db": -16.0}):
                r = MV.voz_na_faixa(Path(t) / "a.mp3", 5)
                self.assertTrue(r["tem_voz"])
                self.assertEqual(r["rel_db"], -6.0)
            with patch.object(midia_local, "so_voz", return_value={"rms_voz_db": -55.0}):
                self.assertFalse(MV.voz_na_faixa(Path(t) / "b.mp3", 5)["tem_voz"])

    def _fake(self, nomes_viral):
        virais = [{"id": f"viral-{i}", "slug": f"viral-{i}", "chave": f"c{i}", "artista": a, "titulo": t, "score": 5.0 - i, "fontes": {}, "ranks": {}}
                  for i, (a, t, _g) in enumerate(nomes_viral)]
        perfis = {f"viral-{i}": {"genero": g} for i, (_a, _t, g) in enumerate(nomes_viral)}
        return virais, perfis

    def test_por_direcao_tira_genero_que_briga_voz_cantada_e_completa_com_youtube_e_mixkit(self):
        virais, perfis = self._fake([("MC Zé", "Baile", "Funk"), ("Banda X", "Canção", "Alternative"), ("DJ Y", "Instrumental Hit", "Electronic")])
        medidas = []

        def avaliar(m, d, dur, fonte, motivo, medir_voz=True):
            medidas.append(m["id"])
            if m["id"] == "viral-1":
                return None, {"titulo": "Banda X - Canção", "motivos": ["tem voz cantada (voz -6 dB da mistura; o limite é -20)"]}
            return {"id": m["id"], "titulo": m["titulo"], "artista": m["artista"], "motivo": motivo, "fonte": fonte, "previa": "x.mp3", "t0": 1, "checagem": "ok"}, None

        yt = "\n".join(json.dumps({"title": t, "id": i, "duration": 200, "channel": "Canal", "webpage_url": f"https://www.youtube.com/watch?v={i}"})
                       for t, i in (("Tense Dark Suspense Music", "aaa"), ("Sound Effect tense", "bbb")))
        with patch.object(MV, "virais", return_value=virais), patch.object(MV, "_perfil", side_effect=lambda m: perfis[m["id"]]), \
                patch.object(MV, "_recentes", return_value=set()), patch.object(MV, "_reprovadas", return_value=set()), \
                patch.object(MV, "_avaliar", side_effect=avaliar), patch.object(MV, "_ytdlp", return_value=["yt"]), \
                patch.object(MV, "resumo_fontes", return_value="Shazam"), \
                patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=yt, stderr="")), \
                patch("musica_busca.buscar_mixkit", return_value={"itens": [{"titulo": "Echoes", "baixar": "https://ts.mixkit.co/music/188/188.mp3"}]}):
            r = MV.por_direcao("tensa de suspense, sem voz", cliente="Avulso", texto="o juiz proibiu o evento", clima_formato="tensa sombria")
            self.assertNotIn("viral-0", medidas)                                   # o funk nem foi medido
            self.assertEqual([o["fonte"] for o in r["opcoes"]], ["viral", "youtube", "mixkit"])
            self.assertEqual(r["opcoes"][0]["titulo"], "Instrumental Hit")
            self.assertNotIn("bbb", [o["id"].rsplit("=", 1)[-1] for o in r["opcoes"]])   # "Sound Effect" não é música
            self.assertTrue(any("funk" in x["titulo"] and "briga" in x["motivos"][0] for x in r["recusadas"]))
            self.assertTrue(any("voz cantada" in x["motivos"][0] for x in r["recusadas"]))
            ids = [o["id"] for o in r["opcoes"]]
            # "Outras 3": o que já apareceu não volta
            r2 = MV.por_direcao("tensa de suspense, sem voz", n=3, ignorar=tuple(ids), clima_formato="tensa sombria")
            self.assertFalse(set(ids) & {o["id"] for o in r2["opcoes"]})

    def test_viral_cantada_entra_pela_versao_instrumental_e_nao_cai_no_arquivo_da_original(self):
        m = {"id": "viral-1", "slug": "viral-banda-x-cancao", "chave": "c", "artista": "Banda X", "titulo": "Canção"}
        yt = "\n".join(json.dumps(x) for x in (
            {"title": "Banda X - Canção (Instrumental)", "id": "inst1", "duration": 200, "channel": "Stems", "webpage_url": "https://www.youtube.com/watch?v=inst1"},
            {"title": "Banda X - Canção (slowed + reverb)", "id": "slow", "duration": 200, "channel": "Z", "webpage_url": "https://www.youtube.com/watch?v=slow"},
            {"title": "Outra coisa - karaoke", "id": "outra", "duration": 200, "channel": "Z", "webpage_url": "https://www.youtube.com/watch?v=outra"}))
        vistas = []

        def avaliar(v, d, dur, fonte, motivo, medir_voz=True):
            vistas.append(v)
            return {"id": v["id"], "titulo": v["titulo"], "motivo": motivo, "fonte": fonte}, None

        with patch.object(MV, "_ytdlp", return_value=["yt"]), patch.object(MV, "_avaliar", side_effect=avaliar), \
                patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=yt, stderr="")):
            op, ruins = MV._versao_instrumental(m, {"sem_voz": True}, 75.0, "casa bem com tensa", set())
        self.assertEqual(op["fonte"], "viral-instrumental")
        self.assertIn("versão instrumental", op["motivo"])
        self.assertEqual(len(vistas), 1)                                  # slowed e outra música ficaram de fora
        self.assertNotEqual(vistas[0]["slug"], m["slug"])                 # slug próprio: não reusa o mp3 da original
        self.assertEqual(MV.genero_briga({"artista": "MC Ryan SP", "titulo": "Set"}, {}, "tensa", "um roteiro"), "funk")

    def test_link_colado_ainda_vale(self):
        with patch.object(MV, "_cand_link", return_value={"artista": "A", "titulo": "T", "slug": "s", "chave": "c", "id": "https://youtu.be/x"}), \
                patch.object(MV, "_avaliar", return_value=({"id": "https://youtu.be/x", "titulo": "T"}, None)):
            r = MV.por_direcao("https://youtu.be/x")
            self.assertEqual(r["entendi"], "link")
            self.assertEqual(len(r["opcoes"]), 1)


class Estilos(unittest.TestCase):
    def test_estilos_com_musica_mostram_a_opcao_e_os_gravados_comecam_sem(self):
        import novo_rotas
        for slug, viral in (("documentario", False), ("fala-com-cenas", False), ("chamada-na-tela", False), ("tela-dividida", False), ("editorial", True)):
            f = json.loads((RAIZ / "formatos" / slug / "formato.json").read_text(encoding="utf-8"))
            self.assertTrue(novo_rotas._tem_escolha_musica(f), slug)
        for slug in ("analise-de-tela", "caixinha-de-perguntas", "critica-ao-absurdo", "lista-de-estaticos"):
            f = json.loads((RAIZ / "formatos" / slug / "formato.json").read_text(encoding="utf-8"))
            self.assertFalse(novo_rotas._tem_escolha_musica(f), slug)   # esses são "só a voz": sem música por desenho

    def test_documentario_le_a_escolha_do_novo_video(self):
        spec = importlib.util.spec_from_file_location("render_doc", RAIZ / "formatos" / "documentario" / "base" / "render.py")
        R = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(RAIZ / "formatos" / "documentario" / "base"))
        spec.loader.exec_module(R)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            doc = {"musica": [{"arquivo": "audio/musicas/1154.mp3", "inicio_s": 0, "de": 0}], "efeitos": True}
            self.assertEqual(R.escolha_do_joao_som(dict(doc), p)["musica"], doc["musica"])   # sem escolha: o cenas.json manda
            (p / "work" / "musica").mkdir(parents=True)
            (p / "work" / "musica" / "viral-x.mp3").write_bytes(b"x")
            (p / "work" / "musica" / "escolhida.json").write_text(json.dumps({"arquivo": "work/musica/viral-x.mp3"}))
            r = R.escolha_do_joao_som(dict(doc), p)
            self.assertEqual(r["musica"], [{"arquivo": "work/musica/viral-x.mp3", "inicio_s": 0, "de": 0}])
            (p / "work" / "musica" / "sem").touch()
            (p / "work" / "efeitos").mkdir()
            (p / "work" / "efeitos" / "sem").touch()
            r = R.escolha_do_joao_som(dict(doc), p)
            self.assertIsNone(r["musica"])
            self.assertIs(r["efeitos"], False)
            self.assertTrue(R.escolha_da_tela(p)["sem_musica"] and R.escolha_da_tela(p)["sem_efeitos"])   # a conferência não reprova a falta

    def test_pedido_a_ia_marca_os_arquivos_e_fala_da_musica_e_dos_efeitos(self):
        f = json.loads((RAIZ / "formatos" / "documentario" / "formato.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as t:
            job = {"cliente": "Avulso", "musica": {"modo": "sem"}, "efeitos": {"modo": "sem"}}
            txt = P._musica_viral_txt(job, f, t)
            self.assertIn("SEM MÚSICA", txt)
            self.assertIn("EFEITOS SONOROS", txt)
            self.assertTrue((Path(t) / "work" / "musica" / "sem").is_file() and (Path(t) / "work" / "efeitos" / "sem").is_file())
            job = {"cliente": "Avulso", "musica": {"modo": "viral", "faixa": "viral-x", "titulo": "X - Y"}}
            self.assertIn("musica_viral.py escolher", P._musica_viral_txt(job, f, t))


class MeuAudio(unittest.TestCase):
    def test_audio_solto_vira_mp4_com_o_audio(self):
        import simples
        with tempfile.TemporaryDirectory() as t:
            mp3 = Path(t) / "voz.mp3"
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", str(mp3)], check=True)
            mp4 = simples._audio_para_video(mp3)
            self.assertEqual(mp4.suffix, ".mp4")
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True)
            self.assertIn("video", r.stdout)
            self.assertIn("audio", r.stdout)
            self.assertEqual(simples._audio_para_video(mp4), mp4)   # vídeo fica como está


class Telas(unittest.TestCase):
    def setUp(self):
        import servidor
        self.c = servidor.app.test_client()

    def test_novo_video_tem_meu_audio_e_efeitos_e_sem_os_botoes_confusos(self):
        r = self.c.get("/criar-agora")
        self.assertEqual(r.status_code, 200)
        h = r.get_data(as_text=True)
        self.assertIn("Só a minha voz (MP3)", h)   # o "Meu áudio" virou cartão de "O que você tem" (test_o_que_voce_tem.py)
        self.assertIn("nv-efeitos", h)
        self.assertNotIn("Refazer as 3", h)
        self.assertNotIn("Ver outras 3", h)
        js = (RAIZ / "app" / "interface" / "static" / "musica-viral.js").read_text(encoding="utf-8")
        self.assertIn("Outras 3", js)
        self.assertIn("Que tipo de música?", js)
        self.assertNotIn("Ver outras 3", js)

    def test_rota_da_direcao_responde_com_as_opcoes(self):
        fake = {"opcoes": [{"id": "a", "titulo": "T", "artista": "A", "motivo": "m"}], "clima": ["tensa"], "recusadas": [], "direcao": "q", "entendi": "tensa"}
        with patch.object(MV, "por_direcao", return_value=fake) as pd:
            r = self.c.get("/musica/viral/direcao?direcao=tensa+de+suspense&formato=documentario&ignorar=x,y")
            j = r.get_json()
            self.assertTrue(j["ok"])
            self.assertEqual(j["opcoes"][0]["id"], "a")
            self.assertEqual(pd.call_args[0][0], "tensa de suspense")
            self.assertEqual(pd.call_args[0][5], ("x", "y"))

    def test_volume_em_tres_opcoes_no_painel_do_editor(self):
        h = (RAIZ / "app" / "interface" / "templates" / "_editor_miolo.html").read_text(encoding="utf-8")
        for t in ("Começa no refrão (automático)", "Mais baixa", "Normal", "Mais alta", "ajustar"):
            self.assertIn(t, h)
        self.assertNotIn("quantos dB abaixo", h)


if __name__ == "__main__":
    unittest.main()
