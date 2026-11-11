"""casar_imagem: nota imagem×fala, melhor quadro dentro do vídeo e a conferência das cenas. O CLIP é simulado (cor da imagem = assunto,
palavra da frase = assunto): o teste não baixa nem carrega modelo nenhum."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import casar_imagem as C

ASSUNTOS = ["camera", "loja", "falencia", "pessoa"]
COR = {"camera": (230, 20, 20), "loja": (20, 200, 20), "falencia": (20, 20, 230), "pessoa": (230, 230, 20)}


def _vetor(assunto: str, ruido: float = 0.0):
    v = np.zeros(8)
    v[ASSUNTOS.index(assunto)] = 1.0
    v[4:] = 0.05 + ruido
    return v / np.linalg.norm(v)


def _emb_img(imgs):
    out = []
    for im in imgs:
        px = im.convert("RGB").getpixel((2, 2))
        nome = min(COR, key=lambda k: sum((a - b) ** 2 for a, b in zip(COR[k], px)))
        out.append(_vetor(nome))
    return np.array(out)


def _emb_txt(txts):
    out = []
    for t in txts:
        t = t.lower()
        nome = next((a for a, pal in (("camera", "câmera"), ("loja", "loja"), ("falencia", "falência"), ("pessoa", "engenheiro")) if pal in t), "pessoa")
        out.append(_vetor(nome, 0.01))
    return np.array(out)


def _foto(pasta: Path, nome: str, assunto: str) -> str:
    Image.new("RGB", (64, 64), COR[assunto]).save(pasta / nome)
    return nome


class Falso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        for alvo, f in (("_emb_imagens", _emb_img), ("_emb_textos", _emb_txt)):
            p = patch.object(C, alvo, f)
            p.start()
            self.addCleanup(p.stop)
        C._EMB.clear()

    def tearDown(self):
        self.tmp.cleanup()


class TestPontuar(Falso):
    def test_casa_e_nao_casa(self):
        _foto(self.pasta, "a.jpg", "camera")
        alta = C.pontuar(self.pasta / "a.jpg", "a primeira câmera digital")
        baixa = C.pontuar(self.pasta / "a.jpg", "uma loja na esquina")
        self.assertGreater(alta, 0.9)
        self.assertLess(baixa, 0.3)

    def test_avaliar_usa_as_outras_falas(self):
        _foto(self.pasta, "a.jpg", "camera")
        bom = C.avaliar(self.pasta / "a.jpg", "a câmera de 1975", ["uma loja", "a falência de 2012", "um engenheiro"])
        ruim = C.avaliar(self.pasta / "a.jpg", "a falência de 2012", ["a câmera de 1975", "a câmera digital nova", "uma loja"])
        self.assertTrue(bom["casa"])
        self.assertEqual(bom["posicao"], 0.0)
        self.assertFalse(ruim["casa"])
        self.assertGreater(ruim["posicao"], C.POSICAO_NAO_CASA)

    def test_png_transparente_nao_vira_preto(self):
        Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(self.pasta / "t.png")
        self.assertEqual(C._abrir(self.pasta / "t.png").getpixel((1, 1)), (235, 235, 235))


class TestMelhoresQuadros(Falso):
    def test_acha_o_quadro_e_separa_os_resultados(self):
        qs = [(t / 2, Image.new("RGB", (64, 64), COR["pessoa"])) for t in range(20)]
        for t in (6, 7, 8):   # a câmera aparece de 3,0 a 4,0 s
            qs[t] = (qs[t][0], Image.new("RGB", (64, 64), COR["camera"]))
        qs[15] = (qs[15][0], Image.new("RGB", (64, 64), COR["camera"]))
        with patch.object(C, "quadros_do_video", return_value=qs):
            r = C.melhores_quadros("x.mp4", "a câmera digital", n=2, separacao=2.0)
        self.assertEqual(len(r), 2)
        self.assertTrue(3.0 <= r[0]["t"] <= 4.0 or abs(r[0]["t"] - 7.5) < .1)
        self.assertGreaterEqual(abs(r[0]["t"] - r[1]["t"]), 2.0)   # não são 2 quadros do mesmo instante
        self.assertGreaterEqual(r[0]["nota"], r[1]["nota"])


class TestFala(unittest.TestCase):
    def test_segmentos_e_frase(self):
        ws = [{"w": w, "s": i * .4, "e": i * .4 + .3} for i, w in enumerate("Foi um engenheiro. O nome era Sasson.".split())]
        segs = C._segmentos(ws)
        self.assertEqual(segs, [(0, 2), (3, 6)])
        fala, k, frase = C._frase_de(ws, segs, 1.2, 2.0)
        self.assertEqual((k, frase), (1, "O nome era Sasson."))

    def test_frase_longa_parte_na_pausa(self):
        ws = [{"w": f"p{i}", "s": i * .3, "e": i * .3 + .2} for i in range(40)]
        self.assertGreater(len(C._segmentos(ws)), 1)


class TestConferirCenas(Falso):
    def _sandbox(self, cenas: list[dict], frases: list[tuple[str, float]]) -> Path:
        palavras = []
        for txt, t0 in frases:
            for i, w in enumerate(txt.split()):
                palavras.append({"word": w, "start": round(t0 + i * .3, 2), "end": round(t0 + i * .3 + .25, 2)})
        (self.pasta / "work").mkdir(exist_ok=True)
        (self.pasta / "work" / "words.json").write_text(json.dumps({"words": palavras}))
        (self.pasta / "cenas.json").write_text(json.dumps({"palavras": "work/words.json", "duracao": 12, "cenas": cenas}))
        return self.pasta

    def test_acha_a_imagem_que_nao_casa(self):
        a, b, c = _foto(self.pasta, "cam.jpg", "camera"), _foto(self.pasta, "loja.jpg", "loja"), _foto(self.pasta, "falencia.jpg", "falencia")
        sb = self._sandbox(
            [{"tipo": "foto", "de": 0, "imagem": a}, {"tipo": "foto", "de": 3, "imagem": b}, {"tipo": "foto", "de": 6, "imagem": c}],
            [("A câmera digital nasceu em 1975.", 0), ("A empresa pediu falência em 2012.", 3), ("Uma loja na esquina fechou.", 6)])
        r = C.conferir_cenas(sb)
        nao = [x for x in r["achados"] if x["tipo"] == "nao_casa"]
        self.assertEqual([x["cena"] for x in nao], [2, 3])   # a loja na fala da falência e a falência na fala da loja
        self.assertTrue(r["cenas"][0]["casa"])
        self.assertIn("Cena 2", nao[0]["texto"])
        self.assertTrue(nao[0]["conserto"])

    def test_mesma_imagem_na_cena_vizinha_mas_nao_dentro_da_mesma_frase(self):
        a = _foto(self.pasta, "cam.jpg", "camera")
        sb = self._sandbox(
            [{"tipo": "foto", "de": 0, "imagem": a}, {"tipo": "foto", "de": 1.2, "imagem": a},   # mesma frase: foto segurada
             {"tipo": "foto", "de": 4, "imagem": a}],                                           # frase nova: repetição
            [("A câmera digital nasceu em 1975.", 0), ("Outra câmera apareceu depois.", 4)])
        tipos = [(x["tipo"], x["cenas"]) for x in C.conferir_cenas(sb)["achados"] if x["tipo"] != "nao_casa"]
        self.assertIn(("mesma_imagem", [2, 3]), tipos)
        self.assertNotIn(("mesma_imagem", [1, 2]), tipos)   # as duas primeiras são a mesma frase: foto segurada

    def test_mesma_pessoa_vizinha_e_demais(self):
        fs = []
        for i in range(4):   # 4 fotos "diferentes" (arquivos distintos) com o mesmo assunto/rosto
            Image.new("RGB", (64, 64), COR["pessoa"]).save(self.pasta / f"p{i}.jpg")
            fs.append(f"p{i}.jpg")
        cenas = [{"tipo": "foto", "de": 3 * i, "imagem": f} for i, f in enumerate(fs)]
        sb = self._sandbox(cenas, [(f"O engenheiro número {i} falou.", 3 * i) for i in range(4)])
        with patch.object(C, "_rosto", return_value=np.ones(4)), patch.object(C, "MESMA_IMAGEM", 2.0):   # >1: só conta como pessoa, não como foto igual
            achados = C.conferir_cenas(sb)["achados"]
        self.assertTrue(any(a["tipo"] == "mesma_pessoa" for a in achados))
        demais = [a for a in achados if a["tipo"] == "pessoa_demais"]
        self.assertEqual(len(demais), 1)
        self.assertIn("4 cenas", demais[0]["texto"])

    def test_fala_sobre_ela_libera_a_pessoa(self):
        # o nome da pessoa na fala E no nome do arquivo: a imagem dela pode aparecer
        for i, nome in enumerate(["sasson-a.jpg", "sasson-b.jpg"]):
            Image.new("RGB", (64, 64), COR["pessoa"]).save(self.pasta / nome)
        sb = self._sandbox([{"tipo": "foto", "de": 0, "imagem": "sasson-a.jpg"}, {"tipo": "foto", "de": 3, "imagem": "sasson-b.jpg"}],
                           [("O engenheiro Sasson inventou.", 0), ("Sasson mostrou aos chefes.", 3)])
        with patch.object(C, "_rosto", return_value=np.ones(4)), patch.object(C, "MESMA_IMAGEM", 2.0):
            achados = C.conferir_cenas(sb)["achados"]
        self.assertFalse([a for a in achados if a["tipo"] in ("mesma_pessoa", "pessoa_demais")])

    def test_sem_rosto_nao_ha_mesma_pessoa(self):
        # fotos de objetos parecidas entre si (o CLIP acha parecidas) não são "a mesma pessoa": quem manda é o rosto
        fs = []
        for i in range(3):
            Image.new("RGB", (64, 64), COR["pessoa"]).save(self.pasta / f"o{i}.jpg")
            fs.append(f"o{i}.jpg")
        sb = self._sandbox([{"tipo": "foto", "de": 3 * i, "imagem": f} for i, f in enumerate(fs)], [(f"O engenheiro {i} falou.", 3 * i) for i in range(3)])
        with patch.object(C, "_rosto", return_value=None), patch.object(C, "MESMA_IMAGEM", 2.0):
            self.assertFalse([a for a in C.conferir_cenas(sb)["achados"] if a["tipo"] in ("mesma_pessoa", "pessoa_demais")])

    def test_rosto_sem_os_modelos_devolve_none(self):
        with patch.object(C, "FACE_DET", self.pasta / "nao-existe.onnx"):
            self.assertIsNone(C._rosto(Image.new("RGB", (32, 32))))

    def test_cena_de_texto_e_sem_foto_nao_entram(self):
        a = _foto(self.pasta, "cam.jpg", "camera")
        sb = self._sandbox([{"tipo": "texto", "de": 0, "imagem": a}, {"tipo": "pessoa", "de": 3, "video": "work/x.mp4"}],
                           [("A câmera digital nasceu.", 0), ("Depois veio a falência.", 3)])
        r = C.conferir_cenas(sb)
        self.assertEqual(r["achados"], [])
        self.assertTrue(all(c.get("bruta") is None for c in r["cenas"]))

    def test_sem_cenas_json(self):
        self.assertTrue(C.conferir_cenas(self.pasta).get("sem_cenas"))


class TestIntegracao(unittest.TestCase):
    def test_revisao_conhece_o_achado_de_imagem(self):
        import revisao
        self.assertIn("imagem_nao_casa", revisao.FALHAS)
        self.assertIn("imagem_repetida", revisao.FALHAS)

    def test_regra_g6_e_esteiras_citam_a_ferramenta(self):
        raiz = Path(__file__).resolve().parents[2]
        self.assertIn("casar_imagem", (raiz / "REGRAS.md").read_text(encoding="utf-8"))
        for slug in ("documentario", "editorial"):
            txt = (raiz / "formatos" / slug / "formato.json").read_text(encoding="utf-8")
            self.assertIn("casar_imagem", txt, slug)
            self.assertIn("casar_imagem", (raiz / "formatos" / slug / "COMO-FAZER.md").read_text(encoding="utf-8"), slug)
        import editor
        for slug in ("documentario", "editorial"):
            self.assertIn("casar_imagem", editor.MOTORES[slug]["dicas"], slug)


if __name__ == "__main__":
    unittest.main()
