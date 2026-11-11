"""Corrigir o corte: cada Aplicar guarda o corte de antes e o "Voltar ao corte anterior" volta um passo, sem apagar nada."""
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import corte_manual as cm  # noqa: E402


def _espera(pasta):
    for _ in range(200):
        if not cm.estado(pasta).get("rodando"):
            return cm.estado(pasta)
        time.sleep(0.1)
    raise AssertionError("o corte não terminou")


class TestCorteDesfazer(unittest.TestCase):
    def test_voltar_um_passo(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            orig, saida = t / "orig.mp4", t / "cortado.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=160x90:r=15:d=6", "-f", "lavfi",
                            "-i", "sine=d=6", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(orig)], check=True)
            with self.assertRaises(ValueError):
                cm.voltar(saida, t)   # nada pra voltar ainda
            cm.disparar(orig, saida, [[1, 2]], t)
            e1 = _espera(t)
            self.assertTrue(e1["ok"])
            self.assertEqual(e1["historico"], [])   # o 1º Aplicar não tem corte de antes
            cm.disparar(orig, saida, [[1, 2], [3, 4]], t)
            e2 = _espera(t)
            self.assertEqual(len(e2["historico"]), 1)
            self.assertEqual(e2["historico"][0]["remover"], [[1, 2]])
            cm.voltar(saida, t)
            e3 = cm.estado(t)
            self.assertEqual(e3["remover"], [[1, 2]])
            self.assertEqual(e3["historico"], [])
            self.assertTrue(saida.exists())
            nomes = [p.name for p in t.iterdir()]
            self.assertTrue(any("-antes-" in n for n in nomes))     # nada apagado
            self.assertTrue(any("-desfeito-" in n for n in nomes))


class TestTelaCorte(unittest.TestCase):
    def test_template_tem_voltar_e_sair(self):
        html = (Path(__file__).resolve().parents[1] / "interface" / "templates" / "corte_manual.html").read_text(encoding="utf-8")
        self.assertIn("Voltar ao corte anterior", html)
        self.assertIn("sair sem mudar nada", html)


if __name__ == "__main__":
    unittest.main()
