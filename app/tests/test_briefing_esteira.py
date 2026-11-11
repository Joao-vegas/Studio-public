"""Peça C do plano do briefing (10-out-2026): o briefing do passo 0 manda na esteira, e o aviso cedo do material.

Tudo em pasta temporária (test_esteira.Base): nada pago, nenhuma chamada de API, catálogo real só lido."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures   # noqa: F401  (põe app/ferramentas no caminho)
import formatos
from test_esteira import Base

C, P = fixtures.C, fixtures.P

BRIEFING = {
    "objetivo": "vender o pack Marca3", "formato_sugerido": {"slug": "doc-teste", "porque": "tem fala"},
    "cliente": "Teste", "entrada": "video", "roteiro": "", "peculiaridade": "ótica, cena do produto no telão",
    "material_liberado": [{"pasta": "Loja", "arquivo": "produto/capa.png", "papel": "cena-produto", "onde": "fala 4"},
                          {"pasta": "Loja", "arquivo": "mockups/livro.png", "papel": "mockup", "onde": "fim"}],
    "referencia": {"video": "material/ref.mp4", "segundo": 12.4, "o_que_copiar": "o corte seco pro produto"},
    "proibido": ["rosa neon"], "descartavel": False, "perguntas_abertas": [],
}


class BriefingNaEsteira(Base):
    def setUp(self):
        super().setUp()
        d = self.criar_formato()
        dados = C.ler_json(d / "formato.json")
        dados["material_aceito"] = ["cena-produto", "foto-pessoa"]
        C.gravar_json(d / "formato.json", dados)
        self.j = self.job_formato()

    def gravar_briefing(self, b=None):
        C.gravar_json(P._pasta_job("Teste", "video") / "briefing.json", b or BRIEFING)

    def test_sem_briefing_json_o_prompt_fica_como_antes(self):
        antes = P.prompt_esteira(self.j, "ate_aprovacao")
        self.assertNotIn("BRIEFING DESTE VÍDEO", antes)
        self.assertEqual(P.secao_briefing(self.j), "")

    def test_prompt_traz_o_briefing_acima_do_geral_e_na_ordem_certa(self):
        self.gravar_briefing()
        for fase in ("ate_aprovacao", "depois"):
            with self.subTest(fase=fase):
                a = P.prompt_esteira(self.j, fase)
                i = a.index("BRIEFING DESTE VÍDEO")
                self.assertLess(i, a.index("2. REGRAS"))            # acima das regras (o geral é o REGRAS.md)
                self.assertLess(i, a.index("Leia REGRAS.md"))
                secao = a[i:a.index("2. REGRAS")]
                for trecho in ("vender o pack Marca3", "ótica, cena do produto no telão",
                               "Loja/produto/capa.png → cena-produto, fala 4", "material/ref.mp4 no segundo 12,4 s",
                               "o corte seco pro produto", "rosa neon", "vale SÓ pra este vídeo",
                               "modelo do cliente > formato > geral", "NÃO vira regra", "aprenda isso"):
                    self.assertIn(trecho, secao)
                # o que o formato não aceita vem avisado; o que ele aceita, não
                self.assertIn("não tem lugar pra: mockups/livro.png (mockup)", secao)
                self.assertNotIn("produto/capa.png (cena-produto)", secao)

    def test_briefing_pelo_id_da_conversa(self):
        bid = "b-teste"
        C.gravar_json(P.JOBS.parent / "briefings" / bid / "briefing.json", BRIEFING)
        self.assertEqual(P.secao_briefing(self.j), "")
        self.j["briefing_id"] = bid
        self.assertIn("vender o pack Marca3", P.secao_briefing(self.j))
        self.j["briefing_id"] = "../fora"                     # id com caminho não sai da pasta de briefings
        self.assertEqual(P.secao_briefing(self.j), "")

    def test_briefing_vazio_nao_entra(self):
        self.gravar_briefing({"objetivo": "", "material_liberado": [], "descartavel": False})
        self.assertNotIn("BRIEFING DESTE VÍDEO", P.prompt_esteira(self.j, "ate_aprovacao"))


class AvisoCedo(Base):
    def setUp(self):
        super().setUp()
        d = self.criar_formato()
        self.dados = C.ler_json(d / "formato.json")
        self.dados["material_aceito"] = ["cena-produto"]
        C.gravar_json(d / "formato.json", self.dados)

    def test_devolve_so_o_que_o_formato_nao_aceita(self):
        fora = formatos.material_fora(BRIEFING)                  # sem formato: o sugerido no briefing
        self.assertEqual([m["arquivo"] for m in fora], ["mockups/livro.png"])
        self.assertIn("mockup", fora[0]["aviso"])
        self.assertEqual(formatos.material_fora(BRIEFING, "doc-teste"), fora)
        self.assertEqual(formatos.material_fora(BRIEFING, {**self.dados, "material_aceito": ["cena-produto", "mockup"]}), [])

    def test_formato_sem_lista_ou_material_sem_papel_avisam(self):
        b = {**BRIEFING, "material_liberado": [{"arquivo": "x.png", "papel": ""}]}
        self.assertIn("sem papel", formatos.material_fora(b, "doc-teste")[0]["aviso"])
        sem_lista = {k: v for k, v in self.dados.items() if k != "material_aceito"}
        self.assertEqual(len(formatos.material_fora(BRIEFING, sem_lista)), 2)
        self.assertEqual(formatos.material_fora({}, "doc-teste"), [])
        self.assertEqual(formatos.material_fora(BRIEFING, "nao-existe"), [])


if __name__ == "__main__":
    unittest.main()
