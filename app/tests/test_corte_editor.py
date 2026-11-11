"""Editor de corte (Frente B): combinar, forma de onda, rota da onda e o HTML novo."""
import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "ferramentas"))
sys.path.insert(0, str(APP / "interface"))
import corte_manual

(Path(__file__).resolve().parent / "_tmp").mkdir(exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="corte_editor-", dir=Path(__file__).resolve().parent / "_tmp"))   # única por execução, dentro do repo (a rota exige)


class Combinar(unittest.TestCase):
    def test_devolver_parte_um_corte(self):
        self.assertEqual(corte_manual.combinar([[1, 5]], [[2, 3]]), [[1, 2], [3, 5]])

    def test_une_trechos_que_se_tocam(self):
        self.assertEqual(corte_manual.combinar([[1, 2], [1.5, 4]], []), [[1, 4]])

    def test_devolver_tudo_e_trecho_minusculo(self):
        self.assertEqual(corte_manual.combinar([[1, 2]], [[0, 3]]), [])
        self.assertEqual(corte_manual.combinar([[1, 1.03], [4, 5]], []), [[4, 5]])


class Onda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TMP.mkdir(parents=True, exist_ok=True)
        cls.mp4 = TMP / "t.mp4"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2", "-shortest", "-pix_fmt", "yuv420p", str(cls.mp4)])
        if r.returncode:
            raise unittest.SkipTest("ffmpeg indisponível")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def test_picos(self):
        p = corte_manual.picos(self.mp4)
        self.assertTrue(90 <= len(p) <= 110, len(p))
        self.assertTrue(all(0 <= x <= 1 for x in p))
        self.assertGreater(max(p), 0.1)
        self.assertFalse((TMP / ".onda.json").exists())

    def test_rota_da_onda(self):
        from servidor import app
        c = app.test_client()
        rel = self.mp4.resolve().relative_to(APP.parent.resolve())
        r = c.get(f"/corte-manual/onda?video={rel}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("picos", r.get_json())
        self.assertEqual(c.get("/corte-manual/onda?video=../../etc/passwd").status_code, 404)


class Tela(unittest.TestCase):
    def test_rota_antiga_viva_e_html_novo(self):
        from servidor import app
        from flask import render_template
        c = app.test_client()
        self.assertEqual(c.get("/corte-manual/avulso/slug-que-nao-existe-xyz").status_code, 404)
        with app.test_request_context("/"):
            html = render_template("corte_manual.html", titulo="T", voltar="/", video="x.mp4", estado={}, ia=[[1, 2]], pronto=None)
        self.assertIn("Cortar daqui", html)
        self.assertIn("corte.js", html)


if __name__ == "__main__":
    unittest.main()
