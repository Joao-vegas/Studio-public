import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import camada


class Camada(unittest.TestCase):
    def test_limpar_segura_os_limites(self):
        p = camada.limpar({"texto": " oi ", "tamanho": 999, "y": -5, "cor_caixa": "zzz", "fonte": "Comic"})
        self.assertEqual((p["texto"], p["tamanho"], p["y"], p["cor_caixa"], p["fonte"]), ("oi", 140, 200, "#000000", "Barlow SemiBold"))

    def test_caixa_cresce_com_o_texto_e_fica_na_altura(self):
        if "Barlow SemiBold" not in camada.fontes():
            self.skipTest("fonte não instalada")
        curto = camada.caixa_png({"texto": "Oi", "y": 470}).getbbox()
        longo = camada.caixa_png({"texto": "Empreender é contar com o ovo que não saiu da galinha", "y": 470}).getbbox()
        self.assertLess(curto[2] - curto[0], longo[2] - longo[0])
        self.assertAlmostEqual((longo[1] + longo[3]) / 2, 470, delta=3)

    def test_sem_caixa_so_texto(self):
        if "Barlow SemiBold" not in camada.fontes():
            self.skipTest("fonte não instalada")
        im = camada.caixa_png({"texto": "Oi", "cor_caixa": "transparente", "cor_texto": "#FF0000"})
        self.assertTrue(all(px[3] == 0 or px[0] > 0 for px in im.crop(im.getbbox()).getdata()))


if __name__ == "__main__":
    unittest.main()
