"""conferir_video: cartão de texto escuro (Documentário) não é 'tela preta' nem 'imagem parada'; preta de verdade continua pega (30-out-2026)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import conferir_video as cv


def video(arq: Path, com_texto: bool, claro: bool = False):
    fundo = "drawbox=x=0:y=0:w=iw:h=ih:color=" + ("0xF2F2EE" if claro else "black") + ":t=fill:enable='between(t,3,5)'"
    letras = ",drawbox=x=40:y=190:w=180:h=14:color=" + ("0x203A9E" if claro else "white") + ":t=fill:enable='between(t,3,5)'" \
             ",drawbox=x=40:y=230:w=140:h=14:color=" + ("0x203A9E" if claro else "white") + ":t=fill:enable='between(t,3,5)'" if com_texto else ""
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=270x480:rate=15:duration=10",
                    "-vf", fundo + letras, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(arq)], check=True)


class TelaPretaCartao(unittest.TestCase):
    def test_cartao_escuro_com_texto_nao_e_tela_preta(self):
        with tempfile.TemporaryDirectory() as t:
            v = Path(t) / "a.mp4"
            video(v, com_texto=True)
            self.assertEqual(cv.checar_tela(v, 10.0), [])

    def test_cartao_claro_parado_com_texto_nao_e_imagem_parada(self):
        with tempfile.TemporaryDirectory() as t:
            v = Path(t) / "b.mp4"
            video(v, com_texto=True, claro=True)
            self.assertEqual(cv.checar_tela(v, 10.0), [])

    def test_preta_de_verdade_continua_acusada(self):
        with tempfile.TemporaryDirectory() as t:
            v = Path(t) / "c.mp4"
            video(v, com_texto=False)
            self.assertTrue(any(a.startswith("Tela preta em 3") for a in cv.checar_tela(v, 10.0)))


if __name__ == "__main__":
    unittest.main()
