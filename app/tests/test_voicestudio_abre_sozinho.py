"""Plano B: sem o runtime instalado o Estúdio abre o aplicativo VoiceStudio (open e /health simulados). O caminho normal, sem janela, está em test_voz_sem_janela.py."""
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
import voicestudio


class AbreSozinho(unittest.TestCase):
    def setUp(self):
        voicestudio._ABRIU["quando"] = 0.0
        voicestudio.TESTANDO["forcar"] = True
        self.addCleanup(voicestudio.TESTANDO.update, forcar=False)

    def test_no_ar_nao_abre_nada(self):
        with mock.patch.object(voicestudio, 'no_ar', return_value=True), mock.patch.object(voicestudio.subprocess, 'run') as run:
            self.assertTrue(voicestudio.garantir_no_ar(5))
            run.assert_not_called()

    def test_fechado_abre_o_app_e_espera_o_health(self):
        respostas = iter([False, False, False, True])
        with mock.patch.object(voicestudio, 'no_ar', side_effect=lambda: next(respostas)), mock.patch.object(voicestudio, '_health', return_value='fora'), \
                mock.patch.object(voicestudio, 'runtime_pronto', return_value=False), mock.patch.object(voicestudio, 'subir_sem_janela', return_value=False), \
                mock.patch.object(voicestudio.subprocess, 'run') as run, mock.patch('time.sleep'):
            voicestudio.garantir_no_ar(30)
        run.assert_called_once()
        self.assertEqual(run.call_args[0][0], ['open', '-g', '-j', '-a', 'VoiceStudio'])

    def test_nao_sobe_devolve_falso_e_falar_diz_abra_o_voicestudio(self):
        with mock.patch.object(voicestudio, 'garantir_no_ar', return_value=False), \
                mock.patch.object(voicestudio, 'estado', return_value={'estado': 'fora', 'texto': '', 'pode_ligar': True}):
            with self.assertRaises(ValueError) as e:
                voicestudio.falar('oi', Path('/tmp/x.mp3'))
        self.assertIn('Abra o VoiceStudio', str(e.exception))

    def test_nao_reabre_antes_de_30_segundos(self):
        with mock.patch.object(voicestudio.subprocess, 'run') as run:
            voicestudio.abrir_app(); voicestudio.abrir_app()
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
