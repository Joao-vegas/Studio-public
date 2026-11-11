"""Editar vídeo de motor entrega o vídeo novo no job["saida"] (o que a tela mostra), tratado como o runner trata (30-out-2026).
Job e sandbox sintéticos; sem IA nem render de verdade."""
import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
import andamento as AND
import checar_cauda
import editor
P = fixtures.P


class Entrega(unittest.TestCase):
    job = fixtures.Isolado.job

    def setUp(self):
        fixtures.Isolado.setUp(self)
        for mod in (editor, AND):
            self.stack.enter_context(patch.object(mod, "RAIZ", self.root))
        self.fechar = self.stack.enter_context(patch.object(checar_cauda, "fechar", return_value=""))
        self.conferir = self.stack.enter_context(patch.object(P, "conferir_pos_render", return_value=[]))

    def _motor(self, status="concluido", slug="video", conteudo=b"NOVO"):
        """Vídeo de motor: o render deixa video.mp4 na sandbox; o entregue (job.saida) ainda é o antigo (b'FINAL')."""
        j = self.job(status=status, slug=slug)
        sb = self.root / j["sandbox"]
        (sb / "video.mp4").write_bytes(conteudo)
        self.stack.enter_context(patch.object(editor, "_doc", return_value={"saida": "video.mp4"}))
        return j, sb, self.root / j["saida"]

    def test_vira_o_entregue_tratado_e_o_anterior_vira_versao(self):
        j, sb, saida = self._motor()
        self.assertEqual(editor.entregar(sb), "")
        self.assertEqual(saida.read_bytes(), b"NOVO")
        self.assertEqual((sb / "editor/versoes/v1/video-v1.mp4").read_bytes(), b"FINAL")   # o que a tela mostrava vira versão
        self.fechar.assert_called_once()                                                  # o mesmo tratamento do fim do runner
        self.assertEqual(self.fechar.call_args.args[0], saida)
        self.conferir.assert_called_once()
        self.assertEqual(P.carregar("Teste", "video")["status"], "concluido")
        self.assertGreaterEqual(saida.stat().st_mtime, (sb / "video.mp4").stat().st_mtime)

    def test_aprovado_volta_pro_ficou_bom(self):
        j, sb, saida = self._motor(status="aprovado")
        AND.registrar("Teste", "video", "Vídeo pronto", "pronto", titulo="Meu vídeo", formato="estilo", origem="tela", video=str(saida))
        AND.responder("Teste", "video", "aprovar")
        self.assertTrue(AND.aprovado_em(AND.carregar("Teste", "video")))
        with patch.object(AND, "agora", return_value="2099-01-01 00:00:00"):   # depois da aprovação (segundos não separam)
            editor.entregar(sb)
        self.assertEqual(P.carregar("Teste", "video")["status"], "concluido")
        d = AND.carregar("Teste", "video")
        self.assertEqual((d["estado"], d["video"]), ("pronto", j["saida"]))
        self.assertFalse(AND.aprovado_em(d))                                        # a aprovação era do vídeo velho
        self.assertEqual(d["atual"]["texto"], "Vídeo editado: assista e aprove")

    def test_exportado_nao_e_tocado(self):
        for st in ("exportado", "arquivado"):
            j, sb, saida = self._motor(status=st, slug="v-" + st)
            aviso = editor.entregar(sb)
            self.assertIn("já tinha sido exportado", aviso)
            self.assertEqual(saida.read_bytes(), b"FINAL")
            self.assertFalse((sb / "editor").exists())
            self.assertEqual(P.carregar("Teste", "v-" + st)["status"], st)
        self.fechar.assert_not_called()

    def test_gravado_que_ja_grava_na_saida_nao_duplica(self):
        j = self.job(status="aprovado")
        sb, saida = self.root / j["sandbox"], self.root / j["saida"]
        saida.write_bytes(b"RENDER NOVO")                                             # o render do gravado escreveu direto aqui
        with patch.object(editor, "_doc", return_value={"saida": str(saida)}):
            self.assertEqual(editor.entregar(sb), "")
        self.assertFalse((sb / "editor").exists())                                    # nada guardado nem copiado
        self.fechar.assert_not_called()
        self.conferir.assert_not_called()
        self.assertEqual(P.carregar("Teste", "video")["status"], "aprovado")          # e o status não mexe

    def test_sem_job_fica_como_hoje(self):
        j, sb, saida = self._motor(slug="chat")
        orfao = sb.with_name("_sandbox-orfao")
        sb.rename(orfao)
        self.assertEqual(editor.entregar(orfao), "")
        self.assertEqual(saida.read_bytes(), b"FINAL")

    def test_job_mexendo_agora_nao_troca_o_entregue(self):
        j, sb, saida = self._motor(status="feedback")
        self.assertIn("mexendo", editor.entregar(sb))
        self.assertEqual(saida.read_bytes(), b"FINAL")

    def test_quem_gera_video_novo_entrega(self):
        for f in (editor.rodar, editor._rodar_narracao, editor.voltar):   # rodar, narração/material/refazer e voltar versão
            self.assertIn("entregar(p)", inspect.getsource(f), f.__name__)


if __name__ == "__main__":
    unittest.main()
