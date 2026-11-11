"""Criar com vídeo + "Cortar antes de editar" + roteiro: o roteiro fica no job e chega no corte (work/roteiro.txt)."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_grupo_3_tela_m_sica_tela as G
import corte
P, simples = G.P, G.simples


class CortarComRoteiro(G.Base):
    def criar(self, **extra):
        self.formato("simples")
        with patch.object(simples._fmt, "usar", return_value=("Teste", "estilo")):
            return self.client.post("/criar", data={"formato": "simples", "cliente": "Teste", "titulo": "Corte",
                                                    "videos": (io.BytesIO(b"raw"), "raw.mp4"), **extra})

    def test_roteiro_chega_no_corte(self):
        r = self.criar(cortar="1", roteiro="Você paga alguém pro Instagram e nada vem de lá.")
        self.assertEqual(r.status_code, 302)
        j = P.carregar("Teste", "corte")
        self.assertTrue(j["cortar_bruto"])
        self.assertEqual(j["entrada"], "video")
        work = P.RAIZ / j["sandbox"] / "work"
        self.assertEqual(corte.ler_roteiro(work), "Você paga alguém pro Instagram e nada vem de lá.")
        self.assertTrue(j["roteiro_corte"].endswith("work/roteiro.txt"))

    def test_video_gravado_sempre_leva_o_roteiro_pro_corte(self):
        # desde 23-out-2026 todo vídeo gravado entra cortado: o roteiro colado vira o gabarito mesmo sem a antiga caixa
        self.criar(roteiro="texto")
        j = P.carregar("Teste", "corte")
        self.assertTrue((P.RAIZ / j["sandbox"] / "work" / "roteiro.txt").exists())

    def test_campo_aparece_com_a_caixa_de_corte(self):
        t = self.client.get("/criar").get_data(as_text=True)
        self.assertIn("comCorte", t)
        self.assertIn("cxCorte.addEventListener('change',prepara)", t)


if __name__ == "__main__":
    unittest.main()
