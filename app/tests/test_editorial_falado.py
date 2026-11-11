"""Editorial falado (PLANO-2.0 item 20, 30-out-2026): o Editorial aceita o vídeo gravado do João (entrada por vídeo), ele aparece ou não
(`job["aparecer"]`) e dá pra misturar as referências de outro estilo (`job["estilo_refs"]` com o estilo de cada uma)."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
sys.path.insert(0, str(RAIZ / "app" / "interface"))
EX = RAIZ / "formatos" / "editorial" / "base" / "exemplos"


def _carrega(nome, caminho):
    s = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(s)
    sys.argv = ["x"]
    s.loader.exec_module(m)
    return m


class EntradaPorVideo(unittest.TestCase):
    def test_editorial_aceita_video_e_roteiro(self):
        import formatos as F
        import novo_rotas
        f = F.carregar("editorial")
        self.assertEqual(f["entrada"], "video-ou-roteiro")
        self.assertIn("editorial", [x["slug"] for x in F.aceitam_video()])
        tags = novo_rotas.tags_estilo(f)
        self.assertIn("gravado", tags)
        self.assertIn("narracao", tags)
        self.assertTrue(novo_rotas._estilo(f)["aparecer"])        # a escolha "Você aparece no vídeo?" é do Editorial

    def test_esteira_tem_a_receita_de_video(self):
        import formatos as F
        est = F.esteira(F.carregar("editorial"))
        fv = {e["id"]: e.get("faz_video", "") for e in est["etapas"]}
        self.assertIn("preparar-fala.py", fv["preparar"])
        self.assertIn("g.fala", fv["cenas"])
        self.assertIn("work/fala/words.json", fv["conferir"])

    def test_pedido_da_producao_usa_a_receita_de_video_e_a_escolha(self):
        import producao as P
        job = {"slug": "x", "titulo": "x", "cliente": "Avulso", "modelo": "editorial", "formato": "editorial", "entrada": "video",
               "bruto": "bruto/x.mp4", "sandbox": "clientes/Avulso/avulsoContent/modelos/editorial/_sandbox-x", "aparecer": "nao",
               "saida_esperada": "clientes/Avulso/avulsoContent/output/editorial/x.mp4", "briefing": "", "materiais": []}
        for aparecer, frase in (("nao", "NÃO, só a voz dele"), ("sim", "SIM, nos momentos fortes")):
            p = P.prompt_esteira(dict(job, aparecer=aparecer), "ate_aprovacao")
            self.assertIn("preparar-fala.py", p)
            self.assertIn(frase, p)
            self.assertNotIn("transcrever", p.split("ESTEIRA")[0])   # a transcrição é do preparar-fala.py, não do cabeçalho


class PreparaFala(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _carrega("preparar_fala", EX / "preparar-fala.py")

    def _ws(self, txt, passo=.4):
        return [{"word": w, "start": round(i * passo, 2), "end": round(i * passo + .35, 2)} for i, w in enumerate(txt.split())]

    def test_sugere_gancho_virada_e_fecho_em_ordem(self):
        ws = self._ws(" ".join(["Você já parou pra pensar nisso hoje? Sim parou sim."] * 1 + ["Muita gente grava todo dia e ninguém vê nada ali, é triste."] * 3
                               + ["Só que tem um detalhe que muda tudo isso aqui agora mesmo."] + ["Cada vídeo precisa de uma ideia só pra funcionar bem."] * 3
                               + ["Então comenta aqui embaixo que eu te mostro como fazer isso."]))
        fr = self.m.frases_de(ws)
        sug = self.m.sugerir(fr, ws[-1]["end"])
        self.assertEqual(sug["gancho"]["de"], 0)
        self.assertGreaterEqual(sug["gancho"]["ate"], 3)
        self.assertLess(sug["gancho"]["ate"], sug["fecho"]["de"])
        self.assertAlmostEqual(sug["fecho"]["ate"], ws[-1]["end"], places=1)
        if "virada" in sug:
            self.assertGreater(sug["virada"]["de"], sug["gancho"]["ate"])
            self.assertLess(sug["virada"]["ate"], sug["fecho"]["de"] + .01)
            self.assertLessEqual(sug["virada"]["ate"] - sug["virada"]["de"], 6.5)

    def test_frase_longa_sem_ponto_se_parte(self):
        ws = self._ws("um dois três quatro cinco seis sete oito nove dez, onze doze treze quatorze quinze dezesseis dezessete dezoito dezenove vinte", .5)
        fr = self.m.frases_de(ws)
        self.assertGreater(len(fr), 1)
        self.assertTrue(all(f["ate"] - f["de"] <= 6.6 for f in fr))

    def test_roteiro_corrige_nome_e_lista_o_que_faltou(self):
        ws = self._ws("o Theranos de Elizabeth Homes foi pra cadeia")
        conf = self.m.conferir_roteiro(ws, "o Theranos de Elizabeth Holmes foi pra cadeia por fraude")
        self.assertIn("Holmes", " ".join(w["word"] for w in ws))      # a grafia do roteiro entrou no words.json
        self.assertTrue(conf["corrigidas"])
        self.assertIn("fraude", conf["faltou_no_video"])


class MotorFala(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _carrega("render_editorial_fala", RAIZ / "formatos/editorial/base/render.py")

    def test_quadros_da_cena_vem_do_video_dele_no_tempo_certo(self):
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t)
            (pasta / "work/fala").mkdir(parents=True)
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=30", "-t", "3",
                            "-pix_fmt", "yuv420p", str(pasta / "work/fala/fala.mp4")], check=True)
            doc = {"duracao": 3, "fala": "work/fala/fala.mp4", "cenas": [{"tipo": "fala", "de": 0, "modo": "cheia"}, {"tipo": "fala", "de": 1.0, "modo": "canto"}]}
            plano = self.r.planejar(doc, pasta)
            c = plano["cenas"][1]
            qs = self.r._quadros_fala(c, plano, pasta)
            self.assertEqual(len(qs), 60)                               # 2 s a 30 fps
            self.assertEqual(len(self.r._quadros_fala(c, plano, pasta)), 60)   # o cache não extrai de novo
            r, a = self.r.checar_dinamismo(plano["cenas"])
            self.assertEqual(r, [])

    def test_card_de_uma_palavra_parado_avisa_no_storyboard(self):
        cenas = [{"n": 1, "tipo": "texto", "de": 0, "ate": 1.7, "texto": "Previsibilidade.", "tempos": [0.1]}]
        self.assertTrue(self.r.checar_dinamismo(cenas)[1])
        cenas[0].update(texto="Eles pedem volume agora mesmo.", tempos=[0, .3, .6, .9, 1.2])
        self.assertFalse(self.r.checar_dinamismo(cenas)[1])

    def test_fala_longa_demais_reprova(self):
        cenas = [{"n": 1, "tipo": "fala", "de": 0, "ate": 11}]
        self.assertTrue(self.r.checar_dinamismo(cenas)[0])
        cenas[0]["ate"] = 8
        self.assertTrue(self.r.checar_dinamismo(cenas)[1])


class EditorVeAFala(unittest.TestCase):
    def test_cena_fala_aparece_como_voce_falando(self):
        import editor
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "_sandbox-x"
            (p / "work/fala").mkdir(parents=True)
            (p / "work/fala/words.json").write_text(json.dumps({"words": [{"word": "oi", "start": 0.1, "end": .3}]}))
            (p / "cenas.json").write_text(json.dumps({"duracao": 4, "palavras": "work/fala/words.json", "cenas": [
                {"tipo": "fala", "de": 0, "modo": "cheia"}, {"tipo": "fala", "de": 2, "modo": "canto", "imagem": "a.jpg"}]}))
            cs = editor.cenas(p)
            self.assertEqual(cs[0]["tipo_rotulo"], "Você falando")
            self.assertIn("Posição do João", [e["rotulo"] for e in cs[0]["elementos"]])
            self.assertIn("Imagem", [e["rotulo"] for e in cs[1]["elementos"]])
            # trocar de cheia pra canto leva a imagem junto; o resto da cena não mexe
            antes = json.loads((p / "cenas.json").read_text())
            depois = json.loads(json.dumps(antes))
            depois["cenas"][0].update(modo="canto", imagem="b.jpg", lado="esq", forte=["x"])
            ok, _ = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "modo"})
            self.assertEqual((ok["cenas"][0]["modo"], ok["cenas"][0]["imagem"], ok["cenas"][0]["lado"]), ("canto", "b.jpg", "esq"))
            # a voz dele não se troca neste vídeo
            self.assertFalse(editor.narracao(p)["pode"])


class MisturarEstilos(unittest.TestCase):
    def test_referencias_de_outro_estilo(self):
        import formatos as F
        refs = F.referencias_mistura("faixa-com-cenas")
        self.assertTrue(refs)
        self.assertTrue(F.ref_caminho("faixa-com-cenas", refs[0]["nome"]).startswith("formatos/faixa-com-cenas/"))
        self.assertTrue(F.ref_caminho("editorial", F.referencias_mistura("editorial")[0]["nome"]).startswith("formatos/editorial/estudos/"))
        self.assertIsNone(F.ref_caminho("faixa-com-cenas", "nao-existe"))

    def test_prompt_explica_a_mistura(self):
        import formatos as F
        import producao as P
        e = F.referencias_mistura("editorial")[0]["nome"]
        m = F.referencias_mistura("faixa-com-cenas")[0]["nome"]
        job = {"formato": "editorial", "modelo": "editorial", "cliente": "Avulso",
               "estilo_refs": [{"nome": e, "peso": 70, "formato": "editorial"}, {"nome": m, "peso": 30, "formato": "faixa-com-cenas"}]}
        t = P.camadas_de_regra(job)
        self.assertIn("MISTURA DE ESTILOS", t)
        self.assertIn("30% formatos/faixa-com-cenas/", t)
        self.assertIn("70% formatos/editorial/estudos/", t)
        self.assertIn("nunca copie", t.lower())
        # sem mistura o texto não aparece
        self.assertNotIn("MISTURA DE ESTILOS", P.camadas_de_regra(dict(job, estilo_refs=[{"nome": e, "peso": 100}])))

    def test_post_grava_o_estilo_de_cada_referencia(self):
        import servidor
        import formatos as F
        import producao as P
        c = servidor.app.test_client()
        e = F.referencias_mistura("editorial")[0]["nome"]
        m = F.referencias_mistura("faixa-com-cenas")[0]["nome"]
        criados = []
        orig = P.criar
        def falso(cli, mod, bruto, titulo, *a, **k):
            j = {"slug": "t", "titulo": titulo, "cliente": cli, "modelo": mod, "entrada": "video" if bruto else "roteiro", "bruto": "x", "sandbox": "s",
                 "formato": k.get("formato", "")}
            criados.append(j)
            return j
        salvos = []
        P.criar, orig_salvar = falso, P.salvar
        P.salvar = lambda j: salvos.append(json.loads(json.dumps(j)))
        orig_analisar = P.analisar
        P.analisar = lambda *a, **k: None
        try:
            c.post("/criar", data={"formato": "editorial", "cliente": "", "titulo": "t", "roteiro": "Uma frase.\nOutra frase.", "direto_campo": "1",
                                   f"ref_peso__{e}": "70", "mix_estilo": "faixa-com-cenas", f"mix_peso__{m}": "30"})
        finally:
            P.criar, P.salvar, P.analisar = orig, orig_salvar, orig_analisar
        refs = next((s["estilo_refs"] for s in salvos if s.get("estilo_refs")), [])
        self.assertEqual({(r["formato"], r["nome"]) for r in refs}, {("editorial", e), ("faixa-com-cenas", m)})
        self.assertEqual(sum(r["peso"] for r in refs), 100)


if __name__ == "__main__":
    unittest.main()
