"""Polimento v2, volta 4 (22-out-2026): Frase fixa (cliente pelo caminho, texto queimado no bruto), editor de corte sem CORTE.json."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))

RAIZ = Path(__file__).resolve().parents[2]
BUILD = RAIZ / "clientes/Avulso/avulsoContent/modelos/frase-fixa/build-caixa.py"


def carregar_build():
    spec = importlib.util.spec_from_file_location("build_caixa_teste", BUILD)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class FraseFixa(unittest.TestCase):
    def test_cliente_vem_do_caminho_nunca_joao_fixo(self):
        b = carregar_build()
        self.assertEqual(b.cliente_do_caminho(Path("/x/clientes/X/xContent/modelos/frase-fixa/_sandbox-a")), "X")
        self.assertEqual(b.cliente_do_caminho(Path("/qualquer/lugar")), "Avulso")

    def test_camada_json_dos_testes_do_avulso_aponta_pro_avulso(self):
        import json
        achou = list((RAIZ / "clientes/Avulso/avulsoContent/modelos/frase-fixa").glob("_sandbox-*/camada.json"))
        if not achou:   # os vídeos de teste do Avulso foram pra Lixeira a pedido do João (30-out-2026)
            self.skipTest("sem vídeo de teste da Frase fixa no Avulso")
        for arq in achou:
            self.assertEqual(json.loads(arq.read_text())["andamento"][0], "Avulso")

    def test_caixa_nova_cobre_o_texto_queimado_do_bruto(self):
        b = carregar_build()
        quadro = np.full((b.H, b.W), 120, dtype=np.uint8)
        quadro[420:560, :] = 5          # caixa preta de 3 linhas (140 px) no bruto
        for y0 in (430, 475, 520):
            quadro[y0:y0 + 25, 400:660] = 250   # as 3 linhas de texto branco
        blocos = b.blocos_do_quadro(quadro)
        self.assertEqual(len(blocos), 1)
        achado = b.escolher_bloco([blocos, blocos, []])
        self.assertTrue(achado and achado[0] <= 431 and achado[1] >= 544)
        p = b.cam.limpar({"texto": "frase curta", "y": 470})
        q = b.cobrir_bloco(p, achado)
        h = b.altura_caixa(q)
        self.assertLessEqual(q["y"] - h / 2, achado[0] - 28 + 1)
        self.assertGreaterEqual(q["y"] + h / 2, achado[1] + 28 - 1)

    def test_bloco_so_num_quadro_nao_conta(self):
        b = carregar_build()
        self.assertIsNone(b.escolher_bloco([[(100, 300)], [], []]))


class EditorDeCorte(unittest.TestCase):
    def _app(self):
        from flask import Flask
        import corte_rotas
        app = Flask(__name__)
        corte_rotas.register(app)
        return app

    def test_tem_corte_vale_com_work_joao_mp4_sem_corte_json(self):
        import producao
        app = self._app()
        with tempfile.TemporaryDirectory() as td:
            sb = Path(td) / "sb"
            (sb / "work").mkdir(parents=True)
            (sb / "work/joao.mp4").write_bytes(b"x")
            job = {"sandbox": str(sb)}
            with mock.patch.object(producao, "carregar", return_value=job), \
                 mock.patch.object(producao, "corte_json", return_value=None), \
                 mock.patch("corte_rotas.RAIZ", Path("/")):
                job["sandbox"] = str(sb).lstrip("/")
                self.assertTrue(app.jinja_env.globals["tem_corte"]("Avulso", "x"))
                (sb / "work/joao.mp4").unlink()
                self.assertFalse(app.jinja_env.globals["tem_corte"]("Avulso", "x"))


if __name__ == "__main__":
    unittest.main()
