"""Conexões (Configurações): link oficial de cada chave, situação medida, teste que nunca gera. Nada de rede de verdade nem do app/.env real."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
import chaves
import conexoes as X

LINKS = {'groq': 'https://console.groq.com/keys', 'kie': 'https://kie.ai/api-key', 'claude': 'https://console.anthropic.com/settings/keys',
         'codex': 'https://platform.openai.com/api-keys', 'elevenlabs': 'https://elevenlabs.io/app/settings/api-keys'}


class Resp:
    def __init__(self, dados): self._d = json.dumps(dados).encode()
    def read(self): return self._d
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Links(unittest.TestCase):
    def test_os_cinco_links_oficiais(self):
        for i, url in LINKS.items(): self.assertEqual(X.POR_ID[i]['link'], url, i)

    def test_toda_chave_tem_link_https_e_uma_linha_de_como_fazer(self):
        for a in X.APPS:
            if a['var']:
                self.assertTrue(a['link'].startswith('https://'), a['id'])
                self.assertTrue(a['como'] and '\n' not in a['como'], a['id'])

    def test_nao_tem_gemini_na_lista(self):
        self.assertFalse(any('gemini' in a['id'] or 'gemini' in a['nome'].lower() for a in X.APPS))

    def test_a_lista_chaves_e_onde_estao_tambem_tem_link(self):
        for nome in ('Groq', 'kie.ai', 'Anthropic (Claude)', 'OpenAI (GPT)', 'ElevenLabs'):
            self.assertIn(nome, X.LINK_POR_SERVICO)
        self.assertNotIn('Gemini (Google)', X.LINK_POR_SERVICO)


class Tela(unittest.TestCase):
    """A página /config mostra cada link abrindo em nova aba, sem vazar nenhum valor de chave."""
    def test_links_na_pagina(self):
        import servidor
        with mock.patch.object(chaves, 'chave', side_effect=lambda n, *a, **k: 'segredo-de-teste-123456' if n == 'GROQ_API_KEY' else ''):
            html = servidor.app.test_client().get('/config').get_data(as_text=True)
        self.assertNotIn('segredo-de-teste-123456', html)
        for url in LINKS.values():
            self.assertIn(f'href="{url}" target="_blank" rel="noopener noreferrer"', html, url)
        self.assertIn('Onde pego a chave', html)
        self.assertIn('Trocar chave', html)
        self.assertNotIn('GEMINI_API_KEY_8', html)
        self.assertNotIn('Voz de IA (Gemini)', html)


class Situacao(unittest.TestCase):
    def test_sem_chave_falta_e_com_chave_liga(self):
        a = X.POR_ID['groq']
        with mock.patch.object(chaves, 'chave', return_value=''):
            self.assertEqual(X.situacao(a, {})['estado'], X.FALTA)
        with mock.patch.object(chaves, 'chave', return_value='gsk_valor-bem-longo-1234'), mock.patch.object(X, '_teste_salvo', return_value={}):
            s = X.situacao(a, {})
        self.assertEqual(s['estado'], X.LIGADO)
        self.assertEqual(s['final'], '…1234')
        self.assertNotIn('gsk_valor', json.dumps(s))

    def test_teste_que_falhou_mostra_fora_do_ar(self):
        falha = {'ok': False, 'texto': 'A Groq não aceitou essa chave.', 'quando': '29/10 10:00'}
        with mock.patch.object(chaves, 'chave', return_value='gsk_valor-bem-longo-1234'), mock.patch.object(X, '_teste_salvo', return_value=falha):
            self.assertEqual(X.situacao(X.POR_ID['groq'], {})['estado'], X.FORA)

    def test_voicestudio_mede_a_porta(self):
        import voicestudio
        with mock.patch.object(voicestudio, 'no_ar', return_value=False):
            s = X.situacao(X.POR_ID['voicestudio'], {})
        self.assertEqual(s['estado'], X.FORA)
        with mock.patch.object(voicestudio, 'no_ar', return_value=True):
            self.assertEqual(X.situacao(X.POR_ID['voicestudio'], {})['estado'], X.LIGADO)

    def test_elevenlabs_sem_voz_e_reserva_desligada(self):
        import voz
        sem_voz = {'padrao': 'voicestudio', 'voicestudio': {'voz': 'd'}, 'elevenlabs': {'chave': True, 'voice_id': '', 'nome_voz': ''}}
        with mock.patch.object(voz, 'status', return_value=sem_voz), mock.patch.object(chaves, 'chave', return_value='eleven-chave-1234567'):
            s = X.situacao(X.POR_ID['elevenlabs'], {})
        self.assertEqual((s['estado'], s['rotulo']), (X.FALTA, 'reserva, desligada'))

    def test_claude_mostra_assinatura_ou_api(self):
        with mock.patch.object(X, 'claude_login', return_value={'binario': True, 'logado': True, 'plano': 'max'}), \
                mock.patch.object(chaves, 'ler', return_value=''):
            s = X.situacao(X.POR_ID['claude'], {'provedor': 'claude', 'cobranca': 'assinatura'})
        self.assertEqual((s['estado'], s['custo']), (X.LIGADO, 'Assinatura'))
        self.assertIn('assinatura', s['texto'])
        with mock.patch.object(X, 'claude_login', return_value={'binario': True, 'logado': True, 'plano': 'max'}), \
                mock.patch.object(chaves, 'ler', return_value='sk-ant-chave-bem-longa-9999'):
            s = X.situacao(X.POR_ID['claude'], {'provedor': 'claude', 'cobranca': 'api'})
        self.assertIn('API', s['custo'])
        self.assertNotIn('sk-ant', json.dumps(s))


class Testar(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(X, 'TESTES', Path(self._tmp.name) / 't.json'); self.p.start()
        self.k = mock.patch.object(chaves, 'chave', return_value='chave-de-teste-123456'); self.k.start()

    def tearDown(self): self.k.stop(); self.p.stop(); self._tmp.cleanup()

    def test_kie_so_consulta_o_saldo(self):
        vistas = []
        def abrir(req, timeout=0): vistas.append((req.get_method(), req.full_url)); return Resp({'code': 200, 'data': 402})
        r = X.testar('kie', abrir)
        self.assertTrue(r['ok'])
        self.assertIn('402', r['texto'])
        self.assertEqual(vistas, [('GET', 'https://api.kie.ai/api/v1/chat/credit')])   # nunca um POST de geração

    def test_groq_lista_modelos_e_chave_recusada_vira_frase_simples(self):
        self.assertTrue(X.testar('groq', lambda req, timeout=0: Resp({'data': [{}, {}]}))['ok'])
        import urllib.error
        def recusa(req, timeout=0): raise urllib.error.HTTPError(req.full_url, 401, 'x', {}, io.BytesIO(b''))
        r = X.testar('groq', recusa)
        self.assertFalse(r['ok'])
        self.assertIn('não aceitou', r['texto'])
        self.assertNotIn('chave-de-teste-123456', r['texto'])

    def test_resultado_fica_guardado_pra_situacao(self):
        X.testar('groq', lambda req, timeout=0: Resp({'data': []}))
        self.assertTrue(X._teste_salvo(X.POR_ID['groq']).get('ok'))

    def test_sem_chave_nao_chama_a_rede(self):
        with mock.patch.object(chaves, 'chave', return_value=''):
            r = X.testar('groq', lambda *a, **k: self.fail('não devia chamar a rede'))
        self.assertFalse(r['ok'])


if __name__ == '__main__':
    unittest.main()
