"""Estudo quadro a quadro (estudo_quadros.py): corte seco e dissolve medidos no quadro certo, números falados (algarismo e
por extenso, PT e EN), regras com quadro de prova e a régua ref × nosso. Vídeo sintético, sem rede (fala passada pronta)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
import estudo_quadros as E  # noqa: E402


def _video(dst: Path) -> None:
    """2 s vermelho → dissolve de 6 quadros (0,2 s) pro azul → 2 s → corte seco pro verde, 2 s. 30 fps, com som."""
    fc = ("[0:v][1:v]xfade=transition=fade:duration=0.2:offset=1.9[a];[a][2:v]concat=n=2:v=1:a=0[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=180x320:r=30:d=2.1",
                    "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=2.1",
                    "-f", "lavfi", "-i", "color=c=green:s=180x320:r=30:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-filter_complex", fc, "-map", "[v]", "-map", "3:a", "-shortest", "-pix_fmt", "yuv420p", str(dst)], check=True)


class EstudoQuadros(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.t = Path(cls.tmp.name)
        cls.video = cls.t / "ref.mp4"
        _video(cls.video)
        words = {"words": [{"word": "Você", "start": 0.1, "end": 0.4}, {"word": "vende", "start": 0.4, "end": 0.8},
                           {"word": "157", "start": 0.8, "end": 1.3}, {"word": "mil.", "start": 1.3, "end": 1.6},
                           {"word": "Then", "start": 2.2, "end": 2.4}, {"word": "twenty", "start": 2.4, "end": 2.8},
                           {"word": "thousand", "start": 2.8, "end": 3.3}, {"word": "um", "start": 3.5, "end": 3.7},
                           {"word": "paciente.", "start": 3.7, "end": 4.2}]}
        cls.words = cls.t / "words.json"
        cls.words.write_text(json.dumps(words), encoding="utf-8")
        cls.est = E.estudar([cls.video], cls.t / "estudo", "teste", transcrever_fala=False,
                            words={str(cls.video): str(cls.words)})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_transicoes_no_quadro_certo(self):
        m = self.est["videos"][0]
        tipos = [(t["tipo"], t["q"]) for t in m["transicoes"]]
        diss = [t for t in m["transicoes"] if t["tipo"] == "dissolve"]
        corte = [t for t in m["transicoes"] if t["tipo"] == "corte"]
        self.assertEqual(len(diss), 1, tipos)
        self.assertTrue(55 <= diss[0]["q"] <= 60 and 4 <= diss[0]["quadros"] <= 7, diss)
        self.assertEqual(len(corte), 1, tipos)
        self.assertTrue(119 <= corte[0]["q"] <= 122, corte)
        self.assertEqual(m["planos"]["n"], 3)

    def test_numeros_pt_en_sem_artigo(self):
        nums = [x["texto"] for x in self.est["videos"][0]["numeros"]]
        self.assertEqual(nums, ["157 mil.", "twenty thousand"])   # "um paciente" é artigo, não número
        self.assertEqual(self.est["videos"][0]["numeros"][0]["q"], 24)

    def test_arquivos_e_regras_com_prova(self):
        d = self.t / "estudo"
        self.assertTrue((d / "estudo.json").is_file() and (d / "ESTUDO-QUADROS.md").is_file())
        self.assertTrue(any(p.name.endswith("-geral.jpg") for p in (d / "folhas").iterdir()))
        self.assertTrue(any("-transicao-" in p.name for p in (d / "folhas").iterdir()))
        md = (d / "ESTUDO-QUADROS.md").read_text(encoding="utf-8")
        self.assertIn("Prova:", md)
        self.assertIn("Estilo × conteúdo", md)
        for r in self.est["regras"]:
            self.assertTrue(r["prova"] and r["texto"])

    def test_comparar_grava_regua(self):
        r = E.comparar(self.t / "estudo", self.video, self.t / "cmp", words=str(self.words), transcrever_fala=False)
        self.assertTrue((self.t / "cmp" / "COMPARACAO.md").is_file())
        self.assertEqual(r["fora"], 0)   # o mesmo vídeo contra ele mesmo: tudo dentro
        self.assertIn("| Plano: mediana |", r["tabela_md"])

    def test_base_sugerida(self):
        self.assertEqual(E.sugerir_base({"lisura": .3, "ruido": 3, "saturacao": 70, "rosto_pct": 100})["base"], "gravado")
        self.assertEqual(E.sugerir_base({"lisura": .54, "ruido": 2, "saturacao": 87, "rosto_pct": 12})["base"], "")
        self.assertEqual(E.sugerir_base({"lisura": .38, "ruido": 2, "saturacao": 137, "rosto_pct": 30})["base"], "formatos/explicador-3d/base")


if __name__ == "__main__":
    unittest.main()
