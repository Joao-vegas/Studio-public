"""midia-v2 parte 2: VoiceStudio como voz padrão, voz no Criar e no cliente, 'Seu material' por formato.
Nada de rede de verdade (VOICESTUDIO_URL falsa), nada pago, nada gravado em clientes/ ou app/jobs/."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
import voz
import voicestudio
import formatos as F


class VoiceStudio(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self._tmp.name) / 'config.json'
        self.env = mock.patch.dict(os.environ, {'VOICESTUDIO_URL': 'http://127.0.0.1:1'})
        self.env.start()
        self.p = mock.patch.object(voz, 'CONFIG', self.cfg)
        self.p.start()

    def tearDown(self):
        self.p.stop(); self.env.stop(); self._tmp.cleanup()

    def test_fora_do_ar(self):
        self.assertFalse(voicestudio.no_ar())
        self.assertEqual(voicestudio.vozes(), [])

    def test_padrao_e_voicestudio(self):
        self.assertEqual(voz.status()['padrao'], 'voicestudio')
        self.assertIn('voicestudio', list(voz.PADROES)[:1])

    def test_fora_do_ar_cai_pra_elevenlabs_so_com_chave_e_voz(self):
        st = lambda eleven: {'padrao': 'voicestudio', 'voicestudio': {'voz': 'default'}, 'elevenlabs': eleven}
        with mock.patch.object(voz, 'status', return_value=st({'chave': True, 'voice_id': 'x'})):
            self.assertEqual(voz.motor_escolhido(), 'elevenlabs')
        for eleven in ({'chave': True, 'voice_id': ''}, {'chave': False, 'voice_id': 'x'}):   # falta chave ou voz: sem reserva
            with mock.patch.object(voz, 'status', return_value=st(eleven)):
                self.assertEqual(voz.motor_escolhido(), 'voicestudio')

    def test_gravada_nao_e_trocada(self):
        self.cfg.write_text(json.dumps({'voz_padrao': 'gravada'}))
        self.assertEqual(voz.motor_escolhido(), 'gravada')

    def test_falar_usa_reserva_sem_chamar_o_voicestudio(self):
        with mock.patch.object(voz, 'motor_escolhido', return_value='elevenlabs'), \
                mock.patch.object(voz, 'falar_eleven', return_value=Path('/tmp/x.mp3')) as fe:
            voz.falar('oi', Path('/tmp/x'))
            fe.assert_called_once()

    def test_blocos_respeitam_o_limite(self):
        texto = ' '.join(['Esta é uma frase de teste.'] * 120)
        bl = voicestudio.blocos(texto, 800)
        self.assertGreater(len(bl), 1)
        self.assertTrue(all(len(b) <= 800 for b in bl))
        self.assertEqual(' '.join(bl).split(), texto.split())

    def test_salvar_voz_voicestudio(self):
        voz.salvar('voicestudio', voz_voicestudio='demo0001')
        st = voz.status()
        self.assertEqual((st['padrao'], st['voicestudio']['voz']), ('voicestudio', 'demo0001'))


class Telas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import servidor
        cls.c = servidor.app.test_client()

    def test_criar_formato_narrado_pede_voz(self):
        t = self.c.get('/criar?formato=explicador-3d').get_data(as_text=True)
        self.assertIn('name="voz"', t)

    def test_criar_critica_ao_absurdo_pede_trecho_e_foto(self):
        t = self.c.get('/criar?formato=critica-ao-absurdo').get_data(as_text=True)
        self.assertIn('trecho_de', t)
        self.assertIn('foto_baixo', t)

    def test_cliente_tem_voz_e_favoritos_sem_dado_de_negocio(self):
        r = self.c.get('/cliente/Joao')
        self.assertEqual(r.status_code, 200)
        t = r.get_data(as_text=True)
        self.assertIn('Favoritos', t)
        self.assertIn('Voz preferida', t)
        self.assertNotIn('Descrição curta', t)

    def test_novo_cliente_nao_pede_dado_de_negocio(self):
        t = self.c.get('/novo-cliente').get_data(as_text=True)
        self.assertNotIn('Quem é, nicho, produto', t)

    def test_amostra_fora_do_ar_da_erro_claro(self):
        with mock.patch.dict(os.environ, {'VOICESTUDIO_URL': 'http://127.0.0.1:1'}):
            self.assertEqual(self.c.get('/voz/amostra?voz=default').status_code, 503)


class Pede(unittest.TestCase):
    def test_formatos_reais_tem_pede_valido(self):
        for f in F.listar(ocultos=True):
            self.assertTrue(f.get('pede'), f['slug'])
            for c in f['pede']:
                self.assertIn(c['tipo'], F.TIPOS_PEDE, f['slug'])

    def test_critica_pede_campos_do_plano(self):
        campos = {c['campo']: c for c in F.carregar('critica-ao-absurdo')['pede']}
        self.assertTrue(campos['video_absurdo']['obrigatorio'])
        self.assertTrue(campos['trecho_de']['obrigatorio'] and campos['trecho_ate']['obrigatorio'])
        self.assertEqual(campos['foto_baixo']['tipo'], 'foto')

    def test_validar_acusa_formato_sem_pede(self):
        pasta = RAIZ / 'formatos' / 'critica-ao-absurdo'
        dados = json.loads((pasta / 'formato.json').read_text(encoding='utf-8'))
        dados.pop('pede')
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t) / 'critica-ao-absurdo'
            import shutil
            shutil.copytree(pasta, tmp, ignore=shutil.ignore_patterns('*.mp4', '*.jpg'))
            (tmp / 'formato.json').write_text(json.dumps(dados, ensure_ascii=False), encoding='utf-8')
            with mock.patch.object(F, 'FORMATOS', Path(t)):
                faltas = F.validar('critica-ao-absurdo')
        self.assertTrue(any('pede' in x for x in faltas), faltas)

    def test_material_do_formato_entra_no_prompt(self):
        import producao
        f = F.carregar('critica-ao-absurdo')
        txt = producao._material_formato_txt({'material_formato': {'trecho_de': '0:42', 'trecho_ate': '1:08'}}, f)
        self.assertIn('MATERIAL DESTE VÍDEO', txt)
        self.assertIn('Trecho: de (segundo) = 0:42', txt)
        self.assertEqual(producao._material_formato_txt({}, f), '')


if __name__ == '__main__':
    unittest.main()
