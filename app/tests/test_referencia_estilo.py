"""Melhoria geral, Frente A (22-out-2026): referência e exemplo são estilo, nunca molde.

O pedido à IA não manda copiar; a regra de estilo aparece uma vez por pedido; ANALISE.md antigo com "Copiado:"
ainda passa na conferência. Tudo em pasta temporária (test_esteira.Base): nada pago."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import test_referencia_obriga as ro
from test_referencia_obriga import P, SECAO

RAIZ = Path(__file__).resolve().parents[2]


class ReferenciaEstilo(ro.ReferenciaObriga):
    """Herda o ambiente (formato e job falsos), mas roda só os testes daqui."""
    def run(self, result=None):
        if self._testMethodName.startswith("test_estilo"):
            return super().run(result)
        return None

    def test_estilo_instrucao_nao_manda_copiar(self):
        txt = P.instrucao_referencia(self.com_referencia())
        self.assertIn("Estilo aproveitado:", txt)
        self.assertNotIn("Copiado:", txt)
        self.assertNotIn("copiar", txt.lower())

    def test_estilo_pedido_da_esteira(self):
        txt = P.prompt_esteira(self.com_referencia(), "ate_aprovacao")
        self.assertNotIn("o que copiou", txt)
        self.assertNotIn("copie o resto", txt)
        self.assertEqual(txt.count(P.REGRA_ESTILO), 1)

    def test_estilo_briefing_da_conversa(self):
        from unittest.mock import patch
        b = {"objetivo": "vender", "referencia": {"video": "material/ref.mp4", "segundo": 3.5, "o_que_copiar": "o corte seco"}}
        with patch.object(P, "briefing_do_job", return_value=b):
            txt = P.secao_briefing(self.j)
        self.assertIn("estilo a aproveitar: o corte seco", txt)
        self.assertIn("só estilo", txt)
        self.assertNotIn(": copiar ", txt)

    def test_estilo_briefing_do_criar_sem_copiar(self):
        src = (RAIZ / "app/interface/simples.py").read_text(encoding="utf-8")
        self.assertNotIn("copie o jeito", src)
        self.assertNotIn("copiando o jeito", src)
        novo = ("REFERÊNCIA DESTE VÍDEO: material/ref.mp4, no segundo 3.5. Estilo a aproveitar: o corte seco. "
                "Siga o formato; da referência só o estilo, nunca roteiro, textos, pessoas ou cores.")
        antigo = novo.replace("Estilo a aproveitar", "O que copiar")
        for txt in (novo, antigo):
            r = P.referencia_do_job({"briefing": txt})
            self.assertEqual(r["o_que_copiar"], "o corte seco")
            self.assertEqual(r["segundo"], 3.5)
        self.assertNotIn("copi", novo.lower())

    def test_estilo_analise_antiga_com_copiado_passa(self):
        j = self.com_referencia()
        self.analise()                       # SECAO usa "Copiado: ritmo e legenda"
        r = P.referencia_analisada(j)
        self.assertEqual(r["usada"], "sim")
        self.assertIn("ritmo", r["copiado"])
        self.assertEqual(P.conferir_referencia(j), "")

    def test_estilo_analise_nova_com_estilo_aproveitado(self):
        j = self.com_referencia()
        self.analise()
        (self.sb / "ANALISE.md").write_text(
            SECAO.format(usada="sim", quadros="work/folhas/referencia.jpg", nao_deu="nada").replace(
                "Copiado: ritmo e legenda", "Estilo aproveitado: ritmo seco"), encoding="utf-8")
        r = P.referencia_analisada(j)
        self.assertEqual(r["usada"], "sim")
        self.assertEqual(r["frase"], "Referência: usada (estilo: ritmo seco)")

    def test_estilo_regra_g0_e_formatos(self):
        self.assertIn("G0", (RAIZ / "REGRAS.md").read_text(encoding="utf-8"))
        self.assertNotIn("igual ou melhor", (RAIZ / "formatos/CONTRATO.md").read_text(encoding="utf-8"))
        for md in (RAIZ / "formatos").glob("*/COMO-FAZER.md"):
            self.assertNotIn("igual ou melhor", md.read_text(encoding="utf-8"), md.parent.name)
        self.assertIn("nunca", P.REGRA_ESTILO)
        self.assertIn("estilo", P.REGRA_ESTILO)


if __name__ == "__main__":
    unittest.main()
