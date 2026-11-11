"""O formato 'so-cortar' saiu do catálogo (10-out-2026), mas o corte de vídeo continua: tela /cortes, entrada 'cortar'
do Criar (atalho de tela, sem formato por trás) e a etapa de corte dos jobs (cortar_bruto)."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_grupo_3_tela_m_sica_tela as G
import corte
import formatos
import pipeline
P, simples = G.P, G.simples

REAL = formatos.FORMATOS


class CorteSemOFormato(G.Base):
    def test_catalogo_nao_tem_mais_so_cortar(self):
        self.assertFalse((REAL / 'so-cortar').exists())
        self.assertNotIn('so-cortar', [f['slug'] for f in formatos.listar(ocultos=True)])
        self.assertNotIn('so-cortar', formatos.SEM_CENAS)
        self.assertFalse(hasattr(formatos, 'APRENDIZADO_FORA'))

    def test_telas_continuam_abrindo(self):
        for rota in ('/cortes', '/criar', '/formatos'):
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(rota).status_code, 200)

    def test_criar_com_entrada_cortar_monta_o_corte_avulso(self):
        pasta = self.est / 'cortes'
        chamadas = []
        with patch.object(corte, 'CORTES', pasta), \
                patch.object(corte, 'avulso_montar', side_effect=lambda *a, **k: chamadas.append((a, k))):
            r = self.client.post('/criar', data={'formato': 'so-cortar', 'cliente': 'Teste', 'titulo': 'Meu corte',
                                                 'roteiro': 'Texto gravado.', 'videos': (io.BytesIO(b'raw'), 'raw.mp4')})
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r.headers['Location'].endswith('/cortes/meu-corte'))
            self.assertTrue((pasta / 'meu-corte/original.mp4').is_file())
            self.assertTrue((pasta / 'meu-corte/corte.json').is_file())
            self.assertEqual(chamadas[0][0][0], 'meu-corte')
            self.assertEqual(chamadas[0][1]['roteiro'], 'Texto gravado.')
            self.assertEqual(self.client.get('/cortes/meu-corte').status_code, 200)

    def test_criar_cortar_sem_video_avisa_e_nao_cria_nada(self):
        pasta = self.est / 'cortes'
        with patch.object(corte, 'CORTES', pasta):
            r = self.client.post('/criar', data={'formato': 'so-cortar', 'cliente': 'Teste', 'titulo': 'Vazio'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(pasta.exists() and any(pasta.iterdir()))

    def test_job_com_corte_monta_a_etapa_de_cortar_a_fala(self):
        j = self.job('novo')
        self.assertEqual({e['id']: e['detalhe'] for e in pipeline.etapas(j)}['fala'], 'Usar a gravação como enviada')
        j['cortar_bruto'] = True
        P.salvar(j)
        et = {e['id']: e for e in pipeline.etapas(P.carregar('Teste', 'video'))}
        self.assertEqual(et['fala']['estado'], 'aguardando')
        self.assertIn('repetições', et['fala']['detalhe'])


if __name__ == '__main__':
    unittest.main()
