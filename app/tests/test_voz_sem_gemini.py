"""O Gemini saiu da voz (29-out-2026): VoiceStudio → ElevenLabs só com chave e voz → erro claro. Nada de rede, nada pago."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
import voz
import voicestudio
import custos as C


class OrdemDaVoz(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self._tmp.name) / 'config.json'
        self.env_arq = Path(self._tmp.name) / '.env'
        self.ps = [mock.patch.object(voz, 'CONFIG', self.cfg), mock.patch.object(voz, 'ENV', self.env_arq)]
        for p in self.ps: p.start()

    def tearDown(self):
        for p in self.ps: p.stop()
        self._tmp.cleanup()

    def test_gemini_nao_e_mais_uma_opcao_nem_aparece_no_status(self):
        self.assertNotIn('gemini', voz.PADROES)
        self.assertNotIn('gemini', voz.status())
        self.assertEqual(list(voz.PADROES), ['voicestudio', 'elevenlabs', 'gravada'])

    def test_chaves_gemini_no_env_nao_viram_reserva(self):
        self.env_arq.write_text('GEMINI_API_KEY_1=abc\nGEMINI_API_KEY_7=def\n')
        with mock.patch.object(voicestudio, 'no_ar', return_value=False):
            self.assertEqual(voz.motor_escolhido(), 'voicestudio')   # nunca 'gemini'

    def test_padrao_salvo_como_gemini_vira_voicestudio(self):
        self.cfg.write_text(json.dumps({'voz_padrao': 'gemini'}))
        self.assertEqual(voz.status()['padrao'], 'voicestudio')
        with mock.patch.object(voicestudio, 'no_ar', return_value=True):
            self.assertEqual(voz.motor_escolhido(), 'voicestudio')

    def test_voicestudio_no_ar_fala_pelo_voicestudio(self):
        with mock.patch.object(voicestudio, 'no_ar', return_value=True), \
                mock.patch.object(voicestudio, 'falar', return_value=Path('/tmp/x.mp3')) as f:
            voz.falar('oi', Path('/tmp/x'))
            f.assert_called_once()

    def test_voicestudio_fechado_sem_reserva_da_erro_claro(self):
        self.env_arq.write_text('GEMINI_API_KEY_7=def\nELEVENLABS_API_KEY=so-a-chave-sem-voz\n')   # chave sem voz não é reserva
        with mock.patch.object(voicestudio, 'no_ar', return_value=False), \
                mock.patch.object(voicestudio, 'falar') as f:
            with self.assertRaises(ValueError) as c: voz.falar('oi', Path('/tmp/x'))
        self.assertIn('Abra o VoiceStudio', str(c.exception))
        f.assert_not_called()

    def test_voicestudio_fechado_com_chave_e_voz_usa_elevenlabs(self):
        self.env_arq.write_text('ELEVENLABS_API_KEY=chave-qualquer-123\nELEVENLABS_VOICE_ID=v1\n')
        with mock.patch.object(voicestudio, 'no_ar', return_value=False), \
                mock.patch.object(voz, 'falar_eleven', return_value=Path('/tmp/x.mp3')) as e:
            voz.falar('oi', Path('/tmp/x'))
        e.assert_called_once()

    def test_narracao_tts_nao_chama_o_gemini_no_modo_padrao(self):
        fonte = (RAIZ / 'app/ferramentas/motion/narracao_tts.py').read_text(encoding='utf-8')
        ramo = fonte[fonte.index('if a.motor != "gemini":'):fonte.index('# V7: aspas')]
        self.assertNotIn('gemini.gerar', ramo)
        self.assertIn('_voz.falar', ramo)   # auto passa por voz.py (VoiceStudio → ElevenLabs → erro)


class CustosSemGemini(unittest.TestCase):
    def test_cartao_de_voz_gemini_some_quando_nao_ha_uso(self):
        with mock.patch.object(C, 'ler_jsonl', return_value=[]):
            nomes = [c['nome'] for c in C.onde_e_cobrado({})]
        self.assertFalse(any('Gemini' in n for n in nomes), nomes)
        self.assertIn('VoiceStudio: voz local', nomes)

    def test_cartao_volta_so_com_uso_recente_e_o_historico_segue(self):
        from datetime import datetime
        uso = [{'data': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'chave': 'chave 6'}]
        with mock.patch.object(C, 'ler_jsonl', side_effect=lambda caminho, *a, **k: uso if caminho == C.GEMINI_USO else []):
            nomes = [c['nome'] for c in C.onde_e_cobrado({})]
        self.assertTrue(any('Gemini' in n and 'não é mais usada' in n for n in nomes), nomes)
        self.assertEqual(C.CHAVES_GEMINI['chave 6'], 'pago')   # a conta histórica continua sabendo o que foi pago

    def test_equivalente_do_mes_vai_pro_cartao(self):
        v = C.visao(5.0, equivalente_mes_usd=12.345)
        self.assertEqual(v['equivalente_mes_usd'], 12.35)


if __name__ == '__main__':
    unittest.main()
