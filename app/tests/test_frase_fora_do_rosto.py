"""Faixa com cenas: com o João em tela cheia a frase nunca cobre o rosto (30-out-2026, print do João: "fica cortando eu")."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import camada
import texto_fora_do_rosto as T

RAIZ = Path(__file__).resolve().parents[2]
SB = RAIZ / "clientes/Avulso/avulsoContent/modelos/faixa-com-cenas/_sandbox-teste-fluxo-faixa"


def rosto(y, h, t=0.0, x=300):
    return {"t": t, "x": x, "y": y, "w": h, "h": h}


class Decisao(unittest.TestCase):
    ALT = 214   # 3 linhas de 64 px

    def test_rosto_pequeno_e_alto_mantem_a_posicao_de_sempre(self):
        d = T.decidir([rosto(500, 350)], self.ALT)   # queixo em ~870: o peito em 1180 está livre
        self.assertEqual((d["onde"], d["y"]), ("padrao", T.PADRAO_Y))

    def test_rosto_grande_vai_pro_peito_abaixo_do_queixo(self):
        """O caso do João (rosto grande, cabelo alto demais pra caber a frase em cima); a frase em 1180 cobria boca e queixo."""
        d = T.decidir([rosto(640, 700)], self.ALT)
        self.assertEqual(d["onde"], "peito")
        topo = d["y"] - self.ALT // 2
        self.assertGreaterEqual(topo, 640 + T.QUEIXO * 700 + T.FOLGA_BAIXO - 1)
        self.assertTrue(d["cabe"])

    def test_com_espaco_em_cima_vai_pra_cima_da_cabeca(self):
        d = T.decidir([rosto(900, 400)], self.ALT)   # queixo ~1320 cobre o 1180; cabelo em ~760: sobra 500 px em cima
        self.assertEqual(d["onde"], "cima")
        base = d["y"] + self.ALT // 2
        self.assertLessEqual(base, 900 - T.CABELO * 400 - T.FOLGA_CIMA + 1)
        self.assertGreaterEqual(d["y"] - self.ALT // 2, T.TOPO_SEGURO)

    def test_pior_quadro_do_trecho_manda(self):
        """Em qualquer posição escolhida, a frase fica fora do rosto de TODOS os quadros do trecho."""
        for rs in ([rosto(700, 450, t=1.0), rosto(800, 650, t=2.0)], [rosto(560, 650, t=1.0), rosto(700, 720, t=2.0)]):
            d = T.decidir(rs, self.ALT)
            topo, base = d["y"] - self.ALT // 2, d["y"] - self.ALT // 2 + self.ALT
            for r in rs:
                olhos, boca = r["y"] + T.OLHOS * r["h"], r["y"] + 0.9 * r["h"]
                self.assertTrue(base <= olhos or topo >= boca, (d["onde"], topo, base, r))

    def test_sem_rosto_achado_fica_como_sempre(self):
        d = T.decidir([], self.ALT)
        self.assertEqual((d["onde"], d["y"], d["rosto"]), ("padrao", T.PADRAO_Y, False))

    def test_zoom_do_punch_desce_o_rosto(self):
        r = T.com_zoom([rosto(600, 500, t=5.0), rosto(600, 500, t=20.0)], [(4.0, 9.0)])
        self.assertGreater(r[0]["y"] + r[0]["h"], 600 + 500)   # dentro do punch: o rosto cresce e o queixo desce
        self.assertEqual(r[1]["y"], 600)                        # fora: igual
        self.assertEqual(r[0]["h"], int(500 * (1 + T.PUNCH_NIVEL)))

    def test_legenda_so_desce_se_o_queixo_pedir(self):
        self.assertEqual(T.y_legenda([rosto(500, 400)]), 1420)
        y = T.y_legenda([rosto(800, 650)])
        self.assertGreaterEqual(y, 800 + T.QUEIXO * 650 + T.FOLGA_BAIXO - 10)

    def test_punch_com_ancora_no_meio_nao_muda_o_padrao_da_caixinha(self):
        self.assertIn("(ih-1920)*0.85", camada.filtro_punch([5.0, 9.0]))
        self.assertNotIn("(ih-1920)*0.85", camada.filtro_punch([5.0, 9.0], rampa=0.04, nivel=0.12, ancora_y=0.5))


def _quadro(y_faixa):
    """Quadro 540x960 cinza com a frase de 3 linhas (branca, vermelha, branca) a partir de y_faixa."""
    import numpy as np
    q = np.full((960, 540, 3), 60, np.uint8)
    for i, (cor, larg) in enumerate([((255, 255, 255), 300), ((222, 28, 33), 340), ((255, 255, 255), 220)]):
        y0 = y_faixa + i * 36
        x0 = (540 - larg) // 2
        q[y0:y0 + 36, x0:x0 + larg] = cor
        q[y0 + 10:y0 + 26, x0 + 30:x0 + larg - 30:6] = (17, 17, 17) if cor[1] > 100 else (255, 255, 255)   # letras
    return q


class AchaAFaixa(unittest.TestCase):
    def test_acha_a_caixa_da_frase(self):
        fx = T.faixa_no_quadro(_quadro(500))
        self.assertIsNotNone(fx)
        self.assertAlmostEqual(fx[0], 500, delta=4)
        self.assertAlmostEqual(fx[1], 608, delta=4)

    def test_quadro_sem_frase_nao_acha(self):
        import numpy as np
        self.assertIsNone(T.faixa_no_quadro(np.full((960, 540, 3), 90, np.uint8)))

    def test_vermelho_solto_sem_faixa_branca_nao_conta(self):
        import numpy as np
        q = np.full((960, 540, 3), 60, np.uint8)
        q[300:340, 100:400] = (222, 28, 33)   # livro vermelho
        self.assertIsNone(T.faixa_no_quadro(q))


class ConferenciaSintetica(unittest.TestCase):
    """Vídeo de 6 s com a frase parada e um 'rosto' fixo (o detector é trocado por um falso: o Haar não acha rosto desenhado)."""

    def _video(self, d, y_faixa):
        import numpy as np
        from PIL import Image
        q = np.asarray(Image.fromarray(_quadro(y_faixa // 2)).resize((1080, 1920), Image.NEAREST))
        png = Path(d) / "q.png"
        Image.fromarray(q).save(png)
        v = Path(d) / "v.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1", "-i", str(png), "-t", "6", "-r", "10", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(v)], check=True)
        sb = Path(d) / "sb"
        sb.mkdir()
        (sb / "PLANO.json").write_text(json.dumps({"estilo": "frase-fixa", "frase": "A|B|C", "janelas": [[0, 1, "S", "x.mp4", 0]]}))
        return v, sb

    def _falso(self):
        import numpy as np
        casc = mock.Mock()
        casc.detectMultiScale.return_value = np.array([[100, 150, 160, 160]])   # em 360x640 -> 1080x1920: y=450..930, h=480
        return mock.patch("cv2.CascadeClassifier", return_value=casc)

    def test_faixa_abaixo_do_rosto_passa(self):
        with tempfile.TemporaryDirectory() as d, self._falso():
            v, sb = self._video(d, 1000)   # rosto: olhos em 570, boca até ~880; faixa de 1000 a 1216 não cobre
            av, _ = T.checar(v, sb, 6.0)
        self.assertEqual(av, [])

    def test_faixa_em_cima_do_rosto_reprova(self):
        with tempfile.TemporaryDirectory() as d, self._falso():
            v, sb = self._video(d, 700)    # faixa de 700 a 916: em cima da boca
            av, num = T.checar(v, sb, 6.0)
        self.assertTrue(av and "Texto em cima do rosto" in av[0], av)
        self.assertGreater(num["quadros_cobrindo"], 0)

    def test_so_o_queixo_encostando_passa(self):
        with tempfile.TemporaryDirectory() as d, self._falso():
            v, sb = self._video(d, 880)    # boca (0,9h = 882) termina onde a faixa começa
            av, _ = T.checar(v, sb, 6.0)
        self.assertEqual(av, [])

    def test_sem_plano_de_faixa_nao_confere(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(T.checar(Path(d) / "x.mp4", Path(d), 5.0), ([], {}))


class NoVideoReal(unittest.TestCase):
    """O teste da Faixa que o João reprovou: a versão antiga (guardada em editor/versoes/v1) tem de reprovar e a nova passar."""

    def test_antes_reprova_e_depois_passa(self):
        antes = SB / "editor/versoes/v1/video-v1.mp4"
        depois = RAIZ / "clientes/Avulso/avulsoContent/output/faixa-com-cenas/teste-fluxo-faixa.mp4"
        if not (antes.is_file() and depois.is_file() and (SB / "PLANO.json").is_file()):
            self.skipTest("vídeo de teste da Faixa não está nesta máquina")
        av, _ = T.checar(antes, SB, 74.0)
        self.assertTrue(av, "a versão antiga (frase em cima da boca) tinha de reprovar")
        av2, _ = T.checar(depois, SB, 74.0)
        self.assertEqual(av2, [], av2)

    def test_exemplos_do_formato_passam(self):
        for ex, sbx in (("exemplo-1.mp4", "_sandbox-12-anos"), ("exemplo-2.mp4", "_sandbox-video-2")):
            v = RAIZ / "formatos/faixa-com-cenas" / ex
            sb = RAIZ / "clientes/Joao/vegasContent/modelos/faixa-com-cenas" / sbx
            if not (v.is_file() and (sb / "PLANO.json").is_file()):
                self.skipTest("exemplos não estão nesta máquina")
            d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(v)]))
            av, _ = T.checar(v, sb, d)
            self.assertEqual(av, [], (ex, av))


class OsDoisGerarPy(unittest.TestCase):
    def test_iguais_e_usam_a_posicao_fora_do_rosto(self):
        a = (RAIZ / "clientes/Joao/vegasContent/modelos/faixa-com-cenas/gerar.py").read_text(encoding="utf-8")
        b = (RAIZ / "clientes/Avulso/avulsoContent/modelos/faixa-com-cenas/gerar.py").read_text(encoding="utf-8")
        self.assertEqual(a, b)
        for trecho in ("texto_fora_do_rosto", "tfr.decidir", "texto-posicao.json", "ancora_y=0.5"):
            self.assertIn(trecho, a)
        self.assertNotIn("faixa-peito", a)


if __name__ == "__main__":
    unittest.main()
