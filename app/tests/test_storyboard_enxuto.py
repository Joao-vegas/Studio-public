"""Storyboard enxuto: o pedido leva o resumo das regras (sem mandar ler tudo), a folha de quadros pronta e, no ajuste,
só as cenas que o João citou. Nada pago, nenhum storyboard de verdade."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_esteira as E
import folha
import resumo_regras
P, C = E.P, E.C


class Pedido(E.Base):
    def setUp(self):
        super().setUp()
        d = self.criar_formato()
        C.gravar_json(d / 'aprendizado/regras.json', {'regras': [
            {'id': 'leve', 'titulo': 'Regra leve', 'texto': 'Texto da leve.', 'peso': 2},
            {'id': 'forte', 'titulo': 'Regra forte', 'texto': 'Texto da forte.', 'evitar': 'Fazer errado.', 'peso': 9, 'cobre': ['E1'], 'desde': 'x'}]})
        (d / 'COMO-FAZER.md').write_text('# Como fazer\n## Cenas\nx\n## Som\ny\n')
        self.j = self.job_formato('novo')

    def test_resumo_no_lugar_de_ler_tudo(self):
        t = P.prompt_esteira(self.j, 'ate_aprovacao')
        self.assertIn('[forte] Regra forte: Texto da forte. Evitar: Fazer errado.', t)
        self.assertLess(t.index('[forte]'), t.index('[leve]'))            # mais peso primeiro
        self.assertNotIn('cobre', t.split('REGRAS DO FORMATO')[1].split('\n')[1])
        self.assertIn('NÃO dê cat no COMO-FAZER.md', t)
        self.assertNotIn('tudo em formatos/', t)
        self.assertIn('Cenas · Som', t)
        self.assertIn('app/ferramentas/folha.py', t)
        self.assertIn('RODADA NOVA', t)

    def test_ajuste_mexe_so_nas_cenas_citadas(self):
        t = P.prompt_esteira(self.j, 'ate_aprovacao', ajuste='troca a cena 7 e o quadro 12 por escritório; aos 0:45 tira o card')
        self.assertIn('AJUSTE DO STORYBOARD', t)
        self.assertIn('Cenas citadas: cenas 7, 12; 0:45', t)
        self.assertIn('mexa SÓ no que o pedido cita', t)
        self.assertNotIn('RODADA NOVA', t)

    def test_analisar_com_ajuste_leva_o_pedido(self):
        with patch.object(P, '_disparar') as disp:
            P.analisar('Teste', 'video', ajuste='cena 3 mais curta')
        self.assertIn('Cenas citadas: cena 3', disp.call_args[0][1])


    def test_quero_alterar_do_andamento_refaz_so_o_citado(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'interface'))
        import andamento_rotas
        self.assertFalse(andamento_rotas.ajustar_storyboard_da_tela('Teste', 'video', 'cena 2'))   # ainda sem storyboard
        j = P.carregar('Teste', 'video'); j['status'] = 'plano'; P.salvar(j)
        with patch.object(P, '_disparar') as disp:
            self.assertTrue(andamento_rotas.ajustar_storyboard_da_tela('Teste', 'video', 'troca a cena 2', '12.5'))
        self.assertIn('Cenas citadas: cena 2', disp.call_args[0][1])
        self.assertIn('segundo 12.5', disp.call_args[0][1])


class Citadas(unittest.TestCase):
    def test_numeros_e_tempos(self):
        self.assertEqual(P.cenas_citadas('cenas 3 e 4, quadro 9'), 'cenas 3, 4, 9')
        self.assertEqual(P.cenas_citadas('no 1:12 a música sobe; aos 30 s corta'), '1:12; 30 s')
        self.assertEqual(P.cenas_citadas('ficou ótimo'), '')


class Resumo(unittest.TestCase):
    def test_formato_real_cabe_no_alvo(self):
        for slug in ('documentario', 'tela-dividida', 'fala-com-cenas'):
            with self.subTest(slug=slug):
                self.assertLessEqual(resumo_regras.palavras(resumo_regras.resumo(slug, 'Joao', 'dividido-mascara')), resumo_regras.ALVO_PALAVRAS)


class Folha(unittest.TestCase):
    def test_folha_de_video_de_teste(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / 't.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=duration=6:size=320x180:rate=10',
                            '-pix_fmt', 'yuv420p', str(v)], check=True)
            out = folha.folha(v, Path(d) / 'f.jpg', passo=1, colunas=3)
            from PIL import Image
            with Image.open(out) as im:
                w, h = im.size
            self.assertLessEqual(w, 1600)
            self.assertEqual(h, 2 * (1600 // 3 * 180 // 320 + (1600 // 3 * 180 // 320) % 2))
            with self.assertRaises(ValueError):
                folha.folha(v, Path(d) / 'g.jpg', de=10)


if __name__ == '__main__':
    unittest.main()
