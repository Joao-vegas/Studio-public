"""Cobrança da IA: com 'api' o env do claude -p leva a chave e não leva o login; sem 'api' não leva. Não chama o claude."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import ia
import custos as C
import via_api

CHAVE_FALSA = 'sk-ant-chave-de-teste'
LOGIN = {'CLAUDE_CODE_OAUTH_TOKEN': 'x', 'CLAUDECODE': '1', 'CLAUDE_CODE_SESSION_ID': 'y', 'PATH': '/usr/bin'}


class Ambiente(unittest.TestCase):
    def env(self, cobranca, provedor='claude'):
        s = {'provedor': provedor, 'modelo': 'sonnet', 'cobranca': cobranca}
        base = {k: v for k, v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}
        with patch.dict(os.environ, {**base, **LOGIN}, clear=True), patch.object(via_api, 'chave', return_value=CHAVE_FALSA):
            return ia.ambiente(s)

    def test_api_tem_chave_e_sem_login(self):
        e = self.env('api')
        self.assertEqual(e['ANTHROPIC_API_KEY'], CHAVE_FALSA)
        self.assertFalse([k for k in e if k.startswith(('CLAUDE_CODE_OAUTH', 'CLAUDECODE', 'CLAUDE_CODE_SESSION'))])

    def test_assinatura_nao_tem_chave(self):
        self.assertNotIn('ANTHROPIC_API_KEY', self.env('assinatura'))

    def test_gpt_nunca_leva_chave_da_anthropic(self):
        with patch('chaves.ler', return_value='sk-openai-de-teste'):
            e = self.env('api', provedor='openai')
        self.assertNotIn('ANTHROPIC_API_KEY', e)
        self.assertEqual(e['CODEX_API_KEY'], 'sk-openai-de-teste')   # o GPT leva a chave dele, não a da Anthropic

    def test_sem_chave_para_com_aviso_simples(self):
        with patch.object(via_api, 'chave', side_effect=SystemExit('sem chave')):
            with self.assertRaises(ValueError) as c:
                ia.ambiente({'provedor': 'claude', 'cobranca': 'api'})
        self.assertIn('falta a chave', str(c.exception))
        self.assertNotIn(CHAVE_FALSA, str(c.exception))

    def test_config_padrao_e_validacao(self):
        self.assertEqual(ia.DEFAULTS['cobranca'], 'api')
        with patch('chaves.configurada', return_value=True):
            self.assertEqual(ia.cobranca({'provedor': 'claude'}), 'api')
            self.assertEqual(ia.cobranca({'provedor': 'claude', 'cobranca': 'assinatura'}), 'assinatura')
            self.assertEqual(ia.cobranca({'provedor': 'openai', 'cobranca': 'api'}), 'assinatura')   # o GPT tem a própria caixa (cobranca_gpt)
        with patch('chaves.configurada', return_value=False):
            self.assertEqual(ia.cobranca({'provedor': 'claude'}), 'assinatura')   # sem chave a caixa fica desligada
        cfg = {**ia.DEFAULTS, 'cobranca': 'qualquer'}
        with self.assertRaises(ValueError):
            ia.validar(cfg)

    def test_config_do_estudio_tem_cobranca_valida(self):
        # api ou assinatura é escolha do João em Configurações; o teste só cobra que o valor exista e seja válido
        self.assertIn(json.loads(ia.CONFIG.read_text()).get('cobranca'), ('api', 'assinatura'))


class Livro(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [patch.object(C, n, v) for n, v in (
            ('PASTA', self.tmp), ('LIVRO', self.tmp / 'execucoes.jsonl'), ('API_LIVRO', self.tmp / 'api.jsonl'),
            ('VIDEOS', self.tmp / 'videos.jsonl'), ('GEMINI_USO', self.tmp / 'gemini_uso.jsonl'), ('ARQUIVO', self.tmp / 'arquivo'),
            ('CACHE_CCUSAGE', self.tmp / 'cache'), ('_do_cerebro', lambda ini=None: []), ('_da_kie', lambda ini=None: []))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_execucao_pela_api_vai_pro_livro_da_api(self):
        C.registrar_execucao({'provedor': 'claude', 'modelo': 'sonnet', 'cobranca': 'api'}, 0.5, {}, None)
        C.registrar_execucao({'provedor': 'claude', 'modelo': 'sonnet', 'cobranca': 'assinatura'}, 2.0, {}, None)
        self.assertEqual(len((self.tmp / 'api.jsonl').read_text().splitlines()), 1)
        self.assertEqual(len((self.tmp / 'execucoes.jsonl').read_text().splitlines()), 1)

    def test_api_aparece_como_pago_somada_por_fila_e_tarefa(self):
        agora = C.agora()
        linhas = [{'quando': agora, 'fila': 'F1', 'tarefa': 'a', 'usd': 1.0, 'estado': 'ok'},
                  {'quando': agora, 'fila': 'F1', 'tarefa': 'a', 'usd': 0.5, 'estado': 'ok'},
                  {'quando': agora, 'fila': 'F2', 'tarefa': 'b', 'usd': 0.25, 'estado': 'ok'}]
        (self.tmp / 'api.jsonl').write_text('\n'.join(json.dumps(l) for l in linhas) + '\n')
        r = C.resumo('hoje')
        self.assertAlmostEqual(r['total']['pago'], 1.75)
        self.assertEqual([(a['fila'], a['tarefa'], a['n'], round(a['usd'], 2)) for a in r['api']],
                         [('F1', 'a', 2, 1.5), ('F2', 'b', 1, 0.25)])
        self.assertTrue(any(s['gaveta'] == 'pago' and s['servico'] == 'Claude pela API' for s in r['por_servico']))


if __name__ == '__main__':
    unittest.main()
