"""Versão nunca se perde nos gravados: re-renderizar ou re-analisar guarda antes o final anterior (30-out-2026)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
import editor
P, C = fixtures.P, fixtures.C


class VersaoDoFinal(unittest.TestCase):
    job = fixtures.Isolado.job

    def setUp(self):
        fixtures.Isolado.setUp(self)

    def test_render_de_novo_guarda_o_final_anterior(self):
        j = self.job(status='concluido')
        final = self.root / j['saida']
        self.assertEqual(P.guardar_final_anterior(j, 'antes de renderizar de novo'), 'v1')
        final.write_bytes(b'FINAL 2 maior')      # o render sobrescreve o final
        self.assertEqual(P.guardar_final_anterior(j, 'antes de renderizar de novo'), 'v2')
        sb = self.root / j['sandbox']
        self.assertEqual((sb / 'editor/versoes/v1/video-v1.mp4').read_bytes(), b'FINAL')
        self.assertEqual((sb / 'editor/versoes/v2/video-v2.mp4').read_bytes(), b'FINAL 2 maior')
        self.assertTrue((sb / 'editor/versoes/v1/PLANO.json').is_file())
        with patch.object(editor, 'RAIZ', self.root), patch.object(editor, 'rel', C.rel):
            self.assertEqual([x['n'] for x in editor.versoes(sb)], [1, 2])   # a tela do Editar vídeo enxerga
        self.assertEqual(len(j['versoes']), 2)

    def test_mesmo_video_nao_repete(self):
        j = self.job(status='concluido')
        self.assertEqual(P.guardar_final_anterior(j, 'x'), 'v1')
        self.assertEqual(P.guardar_final_anterior(j, 'x'), 'v1')
        self.assertEqual(len(list((self.root / j['sandbox'] / 'editor/versoes').iterdir())), 1)

    def test_sem_final_nao_faz_nada(self):
        j = self.job(status='plano')
        (self.root / j['saida']).unlink()
        self.assertEqual(P.guardar_final_anterior(j, 'x'), '')
        self.assertFalse((self.root / j['sandbox'] / 'editor').exists())

    def test_disparar_guarda_antes_de_producao_e_analise(self):
        for tipo in ('producao', 'analise'):
            j = self.job(status='plano', slug='v-' + tipo)
            with patch.object(P, '_esteira', return_value=None), patch('fila.enfileirar'):
                P._disparar(j, 'prompt', tipo)
            self.assertTrue((self.root / j['sandbox'] / 'editor/versoes/v1/video-v1.mp4').is_file(), tipo)


if __name__ == '__main__':
    unittest.main()
