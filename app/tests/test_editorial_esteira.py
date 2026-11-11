"""Esteira do Editorial pela tela (29-out-2026, frente "Criar → vídeo nos estilos de roteiro"): cada quebra achada rodando o
estilo de verdade vira uma conferência aqui (roteiro narrado, roteiro sem corte, voz e IA no job, narração, dinamismo)."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
sys.path.insert(0, str(RAIZ / "app" / "interface"))
EX = RAIZ / "formatos" / "editorial" / "base" / "exemplos"


def _carrega(nome, caminho):
    s = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(s)
    sys.argv = ["x"]
    s.loader.exec_module(m)
    return m


class RoteiroDoClaudeEscreve(unittest.TestCase):
    def test_estilo_de_roteiro_pede_narracao_sem_nome_na_fala(self):
        import briefing_rotas as B
        p = B.montar_prompt("editorial", "", "confiança em quem fala com certeza", "roteiro")
        self.assertIn("NARRAÇÃO", p)
        self.assertIn("SEM \"Nome:\"", p)
        self.assertNotIn("\"Nome: fala\\nNome: fala\"", p)


class PrepararNarracao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = _carrega("preparar_narracao", EX / "preparar-narracao.py")

    def test_numero_por_extenso(self):
        f = self.m.por_extenso
        self.assertEqual(f("Em 2003, 9 bilhões de dólares"), "Em dois mil e três, nove bilhões de dólares")
        self.assertEqual(f("30% dos casos em 1847"), "trinta por cento dos casos em mil oitocentos e quarenta e sete")
        self.assertEqual(f("100 e 101"), "cem e cento e um")

    def test_confere_aceita_so_bloco_inteiro(self):
        esp = "por que alguém entrega milhões a quem nunca provou nada".split()
        self.assertTrue(self.m.confere(esp, esp)[0])
        self.assertFalse(self.m.confere(esp, ["e"] + esp)[0])           # palavra extra no começo
        self.assertFalse(self.m.confere(esp, esp[1:])[0])               # engoliu a 1ª
        self.assertFalse(self.m.confere(esp, esp[:-2] + ["tchau"])[0])  # fim trocado

    def test_blocos_nao_deixam_o_fecho_sozinho(self):
        fr = [f"frase número {i} do roteiro." for i in range(11)]
        bl = self.m.blocos_de(fr)
        self.assertGreater(len(bl[-1]), 1)
        self.assertEqual([x for b in bl for x in b], fr)


class DinamismoDoMotor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _carrega("render_editorial", RAIZ / "formatos/editorial/base/render.py")

    def test_plano_de_imagem_parado_reprova_e_clipe_nao(self):
        cenas = [{"n": 1, "tipo": "foto", "de": 0, "ate": 3.0}, {"n": 2, "tipo": "clipe", "de": 3, "ate": 5.5},
                 {"n": 3, "tipo": "foto", "de": 5.5, "ate": 7.4}]
        reprova, avisa = self.r.checar_dinamismo(cenas)
        self.assertEqual(len(reprova), 1)
        self.assertIn("cena 1", reprova[0])
        self.assertTrue(any("cena 3" in a for a in avisa))
        self.assertFalse(any("cena 2" in x for x in reprova + avisa))


class CriarComRoteiro(unittest.TestCase):
    def test_roteiro_nao_tem_corte_nem_pede_cortar_a_fala(self):
        import producao as P
        casos = P.criar.__code__.co_consts
        self.assertTrue(any(isinstance(c, str) and "video" == c for c in casos))
        src = (RAIZ / "app/ferramentas/producao.py").read_text(encoding="utf-8")
        self.assertIn('bool(cortar_bruto) and entrada == "video"', src)

    def test_fila_respeita_modelo_e_esforco_do_criar(self):
        src = (RAIZ / "app/ferramentas/fila.py").read_text(encoding="utf-8")
        self.assertIn("job.get('ia_escolhida')", src)
        simples = (RAIZ / "app/interface/simples.py").read_text(encoding="utf-8")
        self.assertIn('job["ia_escolhida"] = sel_', simples)


class PromptTemAVozEscolhida(unittest.TestCase):
    def test_voz_do_criar_chega_no_prompt(self):
        import producao as P
        self.assertIn("3ed4b3ea", P._voz_txt({"voz": "3ed4b3ea"}))
        self.assertEqual(P._voz_txt({}), "")


class FotoPequena(unittest.TestCase):
    def test_render_reprova_foto_pequena_em_tela_cheia(self):
        from PIL import Image
        r = _carrega("render_editorial2", RAIZ / "formatos/editorial/base/render.py")
        with tempfile.TemporaryDirectory() as t:
            pasta = Path(t); (pasta / "fotos").mkdir()
            Image.new("RGB", (344, 500)).save(pasta / "fotos/pequena.jpg")
            Image.new("RGB", (1200, 800)).save(pasta / "fotos/grande.jpg")
            doc = {"cenas": [{"tipo": "foto", "imagem": "fotos/pequena.jpg"}, {"tipo": "foto", "imagem": "fotos/grande.jpg"}]}
            reprova, avisa = r.checar_resolucao(doc, pasta)
            self.assertEqual(len(reprova), 1)
            self.assertIn("cena 1", reprova[0])

    def test_trocar_pequenas_nao_passa_de_dois_usos(self):
        import json
        import subprocess
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            sb = Path(t); (sb / "fotos").mkdir()
            Image.new("RGB", (300, 400)).save(sb / "fotos/x-0.jpg")
            for i in (1, 2):
                Image.new("RGB", (1300, 900)).save(sb / f"fotos/x-{i}.jpg")
            (sb / "cenas.json").write_text(json.dumps({"cenas": [{"tipo": "foto", "imagem": "fotos/x-0.jpg"}] * 3}))
            subprocess.run([sys.executable, str(EX / "trocar_pequenas.py"), str(sb)], check=True, capture_output=True)
            usos = [c["imagem"] for c in json.loads((sb / "cenas.json").read_text())["cenas"]]
            self.assertTrue(all(usos.count(x) <= 2 for x in usos))
            self.assertNotIn("fotos/x-0.jpg", usos[:2])


if __name__ == "__main__":
    unittest.main()
