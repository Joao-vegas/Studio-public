"""Faixa com cenas: punch-in nas pausas do João em tela cheia, sem tocar nas cenas (30-out-2026)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import camada
import conferir_video

RAIZ = Path(__file__).resolve().parents[2]


class FaixaPunch(unittest.TestCase):
    def _fala(self, d, dur=24):
        """Áudio: 1 s de tom, 0,3 s de silêncio, repetido (pausa de 0,3 s a cada 1,3 s); vídeo de teste com ruído em movimento."""
        arq = Path(d) / "j.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size=216x384:rate=15:duration={dur}",
                        "-f", "lavfi", "-i", f"aevalsrc='sin(440*2*PI*t)*lt(mod(t,1.3),1.0)':d={dur}:s=16000",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(arq)], check=True)
        return arq

    def test_pontos_so_nos_trechos_livres_e_sempre_pares(self):
        with tempfile.TemporaryDirectory() as t:
            v = self._fala(t)
            livres = [(0.0, 3.0), (6.0, 24.0)]   # o 1º é curto demais; o 2º é a tese
            pts = camada.pontos_punch(v, 24.0, livres)
        self.assertTrue(pts)
        self.assertEqual(len(pts) % 2, 0)
        self.assertTrue(all(6.0 <= p <= 24.0 for p in pts), pts)
        self.assertTrue(all(camada.PUNCH_MIN_S - 0.01 <= b - a <= camada.PUNCH_MAX_S + 0.01 for a, b in zip(pts, pts[1:])), pts)

    def test_sem_trecho_livre_nao_tem_punch(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(camada.pontos_punch(self._fala(t), 24.0, []), [])
            self.assertEqual(camada.pontos_punch(self._fala(t), 24.0, [(2.0, 4.0)]), [])

    def test_padrao_da_caixinha_nao_mudou(self):
        self.assertIn("0.28", camada.filtro_punch([5.0, 9.0]))
        self.assertIn("0.04", camada.filtro_punch([5.0, 9.0], rampa=0.04, nivel=0.12))
        self.assertIn("0.12*", camada.filtro_punch([5.0, 9.0], rampa=0.04, nivel=0.12))

    def test_punch_seco_conta_como_troca_na_conferencia(self):
        """16 s de câmera parada viram trocas visíveis quando o filtro seco entra (é o que a conferência G26 mede)."""
        with tempfile.TemporaryDirectory() as t:
            base = Path(t) / "base.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "mandelbrot=size=216x384:rate=15",
                            "-t", "18", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base)], check=True)
            pts = [4.0, 7.0, 10.0, 13.0]
            out = Path(t) / "punch.mp4"
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(base), "-vf",
                            camada.filtro_punch(pts, rampa=0.04, nivel=0.12).replace("1080", "216").replace("1920", "384").replace("(ih-216)", "(ih-384)"),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)], check=True)
            antes = conferir_video.medir_dinamismo(base)
            depois = conferir_video.medir_dinamismo(out)
        self.assertGreater(depois["trocas"], antes["trocas"])

    def test_os_dois_gerar_py_usam_o_punch_e_sao_iguais(self):
        a = (RAIZ / "clientes/Joao/vegasContent/modelos/faixa-com-cenas/gerar.py").read_text(encoding="utf-8")
        b = (RAIZ / "clientes/Avulso/avulsoContent/modelos/faixa-com-cenas/gerar.py").read_text(encoding="utf-8")
        self.assertEqual(a, b)
        self.assertIn("camada.pontos_punch(cam, D,", a)
        self.assertIn("rampa=0.04, nivel=0.12", a)


if __name__ == "__main__":
    unittest.main()
