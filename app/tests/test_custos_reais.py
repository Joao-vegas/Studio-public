"""Custos reais: o número grande é só o 'dinheiro que saiu'; cartões de cobrança com média real ou 'ainda sem medida';
fila_cobranca api mantém a trava da chave e assinatura a dispensa. Nada chama o claude nem gasta crédito (Popen falso)."""
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ferramentas'))
import custos as C
import ia
import via_api

AGORA = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class Sandbox(unittest.TestCase):
    """Todos os livros apontam pra uma pasta temporária; nada do Estúdio de verdade é lido ou gravado."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.patches = [patch.object(C, n, self.dir / f) for n, f in (
            ('LIVRO', 'execucoes.jsonl'), ('API_LIVRO', 'api.jsonl'), ('VIDEOS', 'videos.jsonl'), ('GEMINI_USO', 'gemini.jsonl'),
            ('KIE_TSV', 'kie.tsv'), ('CATALOGO_KIE', 'catalogo.md'), ('ASSINATURAS', 'assinaturas.json'))]
        self.patches += [patch.object(C, 'podar'), patch.object(C, '_do_cerebro', return_value=[]),
                         patch.object(C, 'claude_code_conversas', return_value={'n': 1, 'usd': 50.0, 'erro': ''})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        patch.stopall()
        self.tmp.cleanup()

    def grava(self, nome, *linhas):
        (self.dir / nome).write_text(''.join(json.dumps(l) + '\n' for l in linhas))

    def cartao(self, nome, cfg=None):
        return next(c for c in C.onde_e_cobrado(cfg or {}) if c['nome'].startswith(nome))


class DinheiroQueSaiu(Sandbox):
    def test_soma_nao_inclui_equivalente_de_plano(self):
        self.grava('execucoes.jsonl', {'data': AGORA, 'provedor': 'claude', 'modelo': 'sonnet', 'usd': 5.0, 'tokens': {}, 'onde': ''})
        self.grava('api.jsonl', {'quando': AGORA, 'fila': 'f', 'tarefa': 't', 'modelo': 'opus', 'usd': 2.0, 'estado': 'ok'})
        (self.dir / 'kie.tsv').write_text('data\tprojeto\tmodelo\ttipo\tcreditos\tusd\tstatus\n'
                                          f'{AGORA[:16]}\tp\tz-image\timagem\t1\t1.0000\tok\n')
        r = C.resumo('tudo')
        self.assertEqual(r['dinheiro_saiu_usd'], 3.0)            # API 2,00 + kie.ai 1,00
        self.assertEqual(r['equivalente_plano_usd'], 55.0)       # 5,00 das execuções + 50,00 das conversas, à parte
        self.assertEqual(C.dinheiro_que_saiu({'pago': 3.0, 'assinatura': 99.0, 'estimado': 9.0}), 3.0)


class Cartoes(Sandbox):
    def test_sem_dado_diz_ainda_sem_medida(self):
        for nome in ('Claude nos vídeos', 'Fila', 'kie.ai', 'ElevenLabs'):
            c = self.cartao(nome)
            self.assertEqual(c['custa'], ['ainda sem medida'], nome)
            self.assertFalse(c['medido'])

    def test_quatro_linhas_fixas_em_todo_cartao(self):
        cartoes = C.onde_e_cobrado({})
        self.assertEqual(len(cartoes), 7)   # VoiceStudio entrou na midia-v2; o cartão do Gemini saiu em 29-out-2026 (só volta com uso recente no livro)
        for c in cartoes:
            for campo in ('nome', 'usa', 'cobrado', 'custa', 'mudar'):
                self.assertTrue(c[campo], (c['nome'], campo))

    def test_media_real_da_fila(self):
        self.grava('api.jsonl',
                   {'quando': AGORA, 'fila': 'a', 'tarefa': 't1', 'modelo': 'opus', 'usd': 2.0, 'estado': 'ok'},
                   {'quando': AGORA, 'fila': 'a', 'tarefa': 't2', 'modelo': 'opus', 'usd': 4.0, 'estado': 'ok'},
                   {'quando': AGORA, 'fila': 'a', 'tarefa': 't3', 'modelo': 'opus', 'usd': 9.0, 'estado': 'erro'})
        c = self.cartao('Fila')
        self.assertTrue(c['medido'])
        self.assertIn('US$ 3,00', c['custa'][0])
        self.assertIn('últimas 2', c['custa'][0])

    def test_preco_da_kie_vem_do_catalogo(self):
        (self.dir / 'catalogo.md').write_text('### Os que o João mais usa\n\n| Modelo | Preço | Quando |\n|---|---|---|\n'
                                              '| `z-image` | **US$ 0,004** | volume |\n\n### Outra\n| `x` | 9 | y |\n')
        self.assertEqual(self.cartao('kie.ai')['custa'], ['z-image: US$ 0,004'])

    def test_cobrado_de_segue_a_escolha(self):
        self.assertIn('Sai dinheiro', self.cartao('Fila', {'fila_cobranca': 'api'})['cobrado'])
        self.assertIn('Não sai dinheiro', self.cartao('Fila', {'fila_cobranca': 'assinatura'})['cobrado'])


class FilaCobranca(unittest.TestCase):
    CHAVE = 'sk-ant-falsa'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.api, self.plano = self.dir / 'api.jsonl', self.dir / 'execucoes.jsonl'
        for n, v in (('CONFIG', self.dir / 'config.json'), ('LIVRO', self.api), ('LIVRO_PLANO', self.plano)):
            patch.object(via_api, n, v).start()
        patch.object(via_api, 'claude_bin', return_value='claude-falso').start()
        patch.object(via_api, 'chave', return_value=self.CHAVE).start()

    def tearDown(self):
        patch.stopall()
        self.tmp.cleanup()

    def escolhe(self, modo):
        (self.dir / 'config.json').write_text(json.dumps({'fila_cobranca': modo}))

    def rodar(self, fonte):
        eventos = [{'type': 'system', 'subtype': 'init', 'apiKeySource': fonte},
                   {'type': 'result', 'result': 'feito', 'total_cost_usd': 1.5, 'is_error': False, 'num_turns': 2}]

        class Proc:
            pid = 99999999
            returncode = 0
            stdin = io.StringIO()
            stdout = [json.dumps(e) + '\n' for e in eventos]
            killed = False
            def wait(self): return 0
            def kill(self): Proc.killed = True

        with patch.object(via_api.subprocess, 'Popen', return_value=Proc()) as pop:
            out = via_api.rodar(self.dir / 'fila' / 'tarefa', {'nome': 'tarefa', 'prompt': 'x', 'modelo': 'sonnet'}, 1.0)
        return out, pop

    def test_padrao_e_validacao(self):
        self.assertEqual(ia.DEFAULTS['fila_cobranca'], 'api')
        self.assertEqual(via_api.cobranca_fila(), 'api')   # sem a opção no config: continua api
        with self.assertRaises(ValueError):
            ia.validar({**ia.DEFAULTS, 'fila_cobranca': 'talvez'})
        self.assertIn(json.loads(ia.CONFIG.read_text()).get('fila_cobranca'), ('api', 'assinatura'))

    def test_api_mantem_a_trava(self):
        self.escolhe('api')
        out, _ = self.rodar('none')   # o Claude Code diz que NÃO está usando a chave
        self.assertEqual(out['estado'], 'erro')
        self.assertIn('não está cobrando da API', out['erro'])
        out, pop = self.rodar('ANTHROPIC_API_KEY')
        self.assertEqual(out['estado'], 'ok')
        self.assertEqual(pop.call_args.kwargs['env']['ANTHROPIC_API_KEY'], self.CHAVE)
        linhas = [json.loads(l) for l in self.api.read_text().splitlines()]
        self.assertEqual(linhas[-1]['usd'], 1.5)           # api: vai pro livro do dinheiro que saiu
        self.assertFalse(self.plano.exists())

    def test_assinatura_dispensa_chave_e_trava(self):
        self.escolhe('assinatura')
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'sk-ant-do-ambiente'}):
            out, pop = self.rodar('none')
        self.assertEqual(out['estado'], 'ok')
        self.assertNotIn('ANTHROPIC_API_KEY', pop.call_args.kwargs['env'])
        self.assertFalse(self.api.exists())                # não conta como dinheiro que saiu
        linha = json.loads(self.plano.read_text().splitlines()[-1])
        self.assertEqual((linha['provedor'], linha['usd']), ('claude', 1.5))

    def test_assinatura_avisa_na_fila(self):
        self.escolhe('assinatura')
        arq = self.dir / 'fila.json'
        arq.write_text(json.dumps({'teto_usd': 5, 'etapas': []}))
        with patch('builtins.print') as imp:
            est = via_api.fila(arq)
        self.assertIn('limite da semana', est['aviso'])
        self.assertIn('limite da semana', imp.call_args.args[0])
        self.escolhe('api')
        self.assertNotIn('aviso', via_api.fila(arq))


if __name__ == '__main__':
    unittest.main()
