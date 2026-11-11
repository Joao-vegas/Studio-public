"""Regressão 29-out-2026: o corte automático termina, mas o processo ainda segurava o .runner.pid; analisar() achava que o corte
rodava, guardava "analisar_depois" e o vídeo ficava parado em "cortado" pra sempre. _aplicar_no_video tem que soltar o pid antes."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import corte  # noqa: E402
import producao as P  # noqa: E402


class CorteSeguePraStoryboard(unittest.TestCase):
    def test_solta_o_pid_antes_de_analisar(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            work = raiz / "sb" / "work"
            work.mkdir(parents=True)
            (work / ".runner.pid").write_text("1")
            job = {"cliente": "X", "slug": "y", "sandbox": "sb"}
            visto = {}

            def analisar(cli, slug, ajuste=""):
                visto["pid"] = (work / ".runner.pid").exists()

            with mock.patch.object(P, "RAIZ", raiz), mock.patch.object(P, "aplicar_corte"), mock.patch.object(P, "carregar", return_value=job), \
                    mock.patch.object(P, "salvar"), mock.patch.object(P, "analisar", analisar), mock.patch.object(corte, "_andamento"):
                corte._aplicar_no_video("X/y")
            self.assertEqual(visto, {"pid": False})


if __name__ == "__main__":
    unittest.main()


class MaterialDoCriarChegaNaIA(unittest.TestCase):
    def test_pergunta_da_caixinha_entra_no_prompt_dos_gravados(self):
        job = {"cliente": "Avulso", "slug": "t", "modelo": "caixinha-de-perguntas", "formato": "caixinha-de-perguntas",
               "sandbox": "x", "material_formato": {"pergunta": "q vc acha do governo?"}}
        self.assertIn("q vc acha do governo?", P.camadas_de_regra(job))


class PunchDaCaixinha(unittest.TestCase):
    def test_filtro_sem_pontos_e_com_pontos(self):
        import camada
        self.assertEqual(camada.filtro_punch([]), "scale=1080:1920:flags=lanczos")
        f = camada.filtro_punch([3.0, 8.0])
        self.assertIn("crop=1080:1920", f)
        self.assertNotIn("+-", f)
        self.assertIn("(t-8.0)", f)


class AnalisarDeNovoRefaz(unittest.TestCase):
    def test_guarda_o_plano_antigo_sem_apagar(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            sb = raiz / "sb"
            sb.mkdir()
            (sb / "PLANO.json").write_text("{}")
            (sb / "ANALISE.md").write_text("x")
            with mock.patch.object(P, "RAIZ", raiz):
                P._guardar_plano_gravado({"cliente": "X", "slug": "y", "sandbox": "sb"})
            self.assertFalse((sb / "PLANO.json").exists())
            self.assertEqual(len(list((sb / "work" / "rodadas").glob("PLANO-*.json"))), 1)
            self.assertEqual(len(list((sb / "work" / "rodadas").glob("ANALISE-*.md"))), 1)


class SeguirDiretoEscolheCena(unittest.TestCase):
    def test_opcao_padrao(self):
        b = {"tipo": "broll", "escolha": None, "opcoes": [{"id": "b1-1"}, {"id": "b1-2"}]}
        self.assertEqual(P._opcao_padrao(b), "b1-1")
        self.assertEqual(P._opcao_padrao({**b, "recomendada": "b1-2"}), "b1-2")
        self.assertEqual(P._opcao_padrao({"tipo": "punch", "opcoes": []}), "")
