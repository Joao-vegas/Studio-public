"""Corte automático + "Seguir direto até o vídeo final" (23-out-2026)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import producao as P  # noqa: E402


class SeguirDireto(unittest.TestCase):
    def test_todo_estilo_segue_direto_depois_do_storyboard(self):
        """João, 30-out-2026: o gate é o vídeo final ("Ficou bom?"), não o storyboard. Só vídeo sem estilo (modelo antigo) para."""
        for slug in ("caixinha-de-perguntas", "documentario", "editorial", "explicador-3d", "faixa-com-cenas"):
            self.assertTrue(P._segue_direto(slug), slug)
        self.assertFalse(P._segue_direto(""))
        self.assertFalse(P._segue_direto("estilo-que-nao-existe"))

    def test_chave_do_criar_vem_ligada(self):
        base = Path(P.__file__).resolve().parents[1] / "interface" / "templates"
        for nome in ("novo.html", "criar.html"):
            txt = (base / nome).read_text(encoding="utf-8")
            i = txt.index('name="direto" value="1"')
            self.assertIn("checked", txt[i:i + 120], nome)

    def test_critica_nao_corta_o_video_absurdo(self):
        import formatos
        self.assertIs(formatos.carregar("critica-ao-absurdo").get("corte_automatico"), False)

    def test_runner_avanca_quando_segue_direto(self):
        txt = (Path(P.__file__).parent / "runner.py").read_text(encoding="utf-8")
        self.assertIn("job.get('seguir_direto')", txt)
        self.assertIn("P.avancar(cli,slug)", txt)


if __name__ == "__main__":
    unittest.main()
