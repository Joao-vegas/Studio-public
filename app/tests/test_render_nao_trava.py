"""Render que não prende o Estúdio: o OpenCL do OpenCV fica desligado em todo filho (no Mac ele roda no Metal e o Python
chegou a ficar em UE na saída) e `rodar_com_limite` abandona quem não termina dentro do limite (30-out-2026)."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import _comum  # noqa: E402

PY = sys.executable
LER = "import os; print(os.environ.get('OPENCV_OPENCL_RUNTIME'))"


class SemOpenCL(unittest.TestCase):
    def test_variavel_chega_no_filho_pelo_com_venv(self):
        base = {k: v for k, v in os.environ.items() if k != "OPENCV_OPENCL_RUNTIME"}
        r = subprocess.run([PY, "-c", LER], env=_comum.com_venv(base), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), "disabled")

    def test_variavel_chega_no_filho_que_herda_o_ambiente(self):
        # importar o _comum já basta: todo processo aberto pelo Estúdio sem env explícito herda
        r = subprocess.run([PY, "-c", LER], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), "disabled")

    def test_opencv_respeita_a_variavel(self):
        try:
            import cv2
        except ImportError:
            self.skipTest("opencv não instalado")
        r = subprocess.run([PY, "-c", "import cv2; print(cv2.ocl.useOpenCL())"], env=_comum.com_venv(),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "False")

    def test_motores_que_importam_cv2_no_topo_desligam_o_opencl(self):
        raiz = Path(__file__).resolve().parents[2]
        for f in ("formatos/documentario/base/render.py", "formatos/lista-de-estaticos/base/render_lista.py"):
            with self.subTest(arquivo=f):
                self.assertIn("OPENCV_OPENCL_RUNTIME", (raiz / f).read_text(encoding="utf-8"))


class RodarComLimite(unittest.TestCase):
    def test_devolve_como_o_run(self):
        r = _comum.rodar_com_limite([PY, "-c", "import sys; print('oi'); sys.stderr.write('x'); sys.exit(3)"], 30,
                                    capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip(), r.stderr.strip()), (3, "oi", "x"))

    def test_abandona_quem_nao_termina(self):
        t = time.time()
        with self.assertRaises(_comum.RenderTravou) as c:
            _comum.rodar_com_limite(["sleep", "60"], 1, espera_morte=5, capture_output=True, text=True)
        self.assertLess(time.time() - t, 8)
        self.assertIsInstance(c.exception, subprocess.TimeoutExpired)   # os `except TimeoutExpired` de antes seguem valendo
        self.assertIn("o render travou e foi abandonado", str(c.exception))

    def test_mata_os_netos_junto(self):
        # o filho abre um neto que segura o pipe: sem matar o grupo inteiro o communicate ficaria esperando
        t = time.time()
        with self.assertRaises(_comum.RenderTravou):
            _comum.rodar_com_limite(["zsh", "-c", "sleep 60 & sleep 60"], 1, espera_morte=5, capture_output=True, text=True)
        self.assertLess(time.time() - t, 8)


class UpscaleNaoTrava(unittest.TestCase):
    """A GPU do Mac (Real-ESRGAN) às vezes trava e não morre nem com kill -9: o upscale tem limite e cai pro processador."""

    def _rodar(self, corpo: str, limite: float = 1.0):
        import midia_local as ml
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            falso = t / "realesrgan-ncnn-vulkan"
            falso.write_text("#!/bin/sh\n" + corpo + "\n")
            falso.chmod(0o755)
            foto = t / "foto.jpg"
            Image.new("RGB", (500, 300), (90, 140, 200)).save(foto)
            ini = time.time()
            with patch.object(ml, "ESRGAN", falso), patch.object(ml, "TRAVOU", t / ".travou"), \
                    patch.object(ml, "_limite_esrgan", lambda w, h: limite):
                r = ml.upscale(foto, t / "saida.jpg", 1400)
                dt = time.time() - ini
                marca = (t / ".travou").exists()
                with Image.open(t / "saida.jpg") as im:
                    larg = im.width
                # segunda foto: com a marca de travou nem chama o binário
                r2 = ml.upscale(foto, t / "saida2.jpg", 1400) if marca else None
            return r, dt, marca, larg, r2

    def test_binario_que_nao_termina_cai_pro_processador(self):
        r, dt, marca, larg, r2 = self._rodar("sleep 120")
        self.assertEqual(r["motor"], "cpu")
        self.assertIn("travou", r["motivo"])
        self.assertTrue(r["ampliada"])
        self.assertGreaterEqual(larg, 1400)
        self.assertLess(dt, 20)
        self.assertTrue(marca)                                   # lembra que a GPU travou
        self.assertEqual(r2["motor"], "cpu")
        self.assertIn("nem tentei", r2["motivo"])

    def test_binario_que_falha_cai_pro_processador(self):
        r, dt, marca, larg, _ = self._rodar("echo erro >&2; exit 3")
        self.assertEqual(r["motor"], "cpu")
        self.assertGreaterEqual(larg, 1400)
        self.assertFalse(marca)                                  # falha comum não trava as próximas

    def test_limite_cresce_com_a_foto(self):
        import midia_local as ml
        self.assertEqual(ml._limite_esrgan(1000, 800), 120)
        self.assertGreater(ml._limite_esrgan(2000, 1500), 120)
        self.assertLessEqual(ml._limite_esrgan(9000, 9000), 300)

    def test_demucs_e_esrgan_passam_pelo_rodar_com_limite(self):
        src = (Path(__file__).resolve().parents[1] / "ferramentas" / "midia_local.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess.run([str(ESRGAN)", src)
        self.assertNotIn("subprocess.run([demucs", src)


class SemGPUNoPython(unittest.TestCase):
    """O CLIP e o índice do acervo rodam no processador: nada de MPS/Metal dentro do Python do Estúdio."""

    def test_casar_imagem_carrega_em_cpu(self):
        import types
        import casar_imagem as ci
        vistos = []

        class Falso:
            def __init__(self, nome, **kw):
                vistos.append((nome, kw.get("device")))

        modulo = types.ModuleType("sentence_transformers")
        modulo.SentenceTransformer = Falso
        with patch.dict(sys.modules, {"sentence_transformers": modulo}), patch.object(ci, "_MODELOS", None):
            ci._carregar()
        self.assertEqual(len(vistos), 2)
        self.assertTrue(all(d == "cpu" for _, d in vistos), vistos)
        self.assertEqual(ci.DEVICE, "cpu")

    def test_semantica_carrega_em_cpu(self):
        src = (Path(__file__).resolve().parents[1] / "ferramentas" / "semantica.py").read_text(encoding="utf-8")
        self.assertIn("device='cpu'", src)


if __name__ == "__main__":
    unittest.main()
