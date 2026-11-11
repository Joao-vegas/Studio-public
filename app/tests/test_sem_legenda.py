"""Sem legenda (todos os formatos) e Usar em outro formato. Pasta temporária, cliente falso: nada pago, nenhuma IA roda,
nenhum vídeo é renderizado (o DOM do Diálogo 3D é um HTML de mentira com só o #leg)."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from test_esteira import Base, C, P
import formatos
import reuso
import saidas

REAL = formatos.FORMATOS


class Contrato(unittest.TestCase):
    def todos(self):
        return sorted(REAL.glob('*/formato.json'))

    def test_formatos_declaram_a_legenda(self):
        arqs = self.todos()
        self.assertGreaterEqual(len(arqs), 10)
        for a in arqs:
            with self.subTest(formato=a.parent.name):
                leg = json.loads(a.read_text(encoding='utf-8')).get('legenda')
                self.assertIsInstance(leg, dict)
                self.assertIsInstance(leg.get('desligavel'), bool)
                self.assertTrue(leg.get('como' if leg['desligavel'] else 'motivo', '').strip())
                self.assertEqual(formatos.legenda_do(json.loads(a.read_text(encoding='utf-8')))['desligavel'], leg['desligavel'])

    def test_cada_formato_diz_como_honra(self):
        como = {a.parent.name: json.loads(a.read_text(encoding='utf-8'))['legenda'] for a in self.todos()}
        self.assertIn('legenda', como['explicador-3d']['como'])
        self.assertIn('--leg-hide', como['fala-com-cenas']['como'])
        self.assertFalse(como['tela-dividida']['desligavel'])

    def test_validar_reprova_sem_o_campo_ou_incompleto(self):
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            dados = json.loads((REAL / 'explicador-3d' / 'formato.json').read_text(encoding='utf-8'))
            legenda = dados.pop('legenda')
            casos = {'sem': None, 'sem-como': {'desligavel': True}, 'sem-motivo': {'desligavel': False},
                     'tipo-ruim': {'desligavel': 'sim', 'como': 'x'}, 'ok': legenda, 'ok-nao': {'desligavel': False, 'motivo': 'Já sai sem.'}}
            for nome, leg in casos.items():
                d = raiz / nome
                d.mkdir()
                (d / 'formato.json').write_text(json.dumps(dict(dados, **({'legenda': leg} if leg is not None else {}))), encoding='utf-8')
            with patch.object(formatos, 'FORMATOS', raiz):
                faltas = {n: [f for f in formatos.validar(n) if 'legenda' in f] for n in casos}
        for n in ('sem', 'sem-como', 'sem-motivo', 'tipo-ruim'):
            self.assertTrue(faltas[n], n)
        self.assertEqual(faltas['ok'], [])
        self.assertEqual(faltas['ok-nao'], [])


class Honrar(unittest.TestCase):
    """O que cada motor faz de verdade com o flag (checagem estática: ninguém renderiza vídeo aqui)."""
    def le(self, rel):
        return (formatos.RAIZ / rel).read_text(encoding='utf-8')

    def test_documentario_le_o_flag(self):
        doc = self.le('formatos/documentario/base/render.py')
        self.assertIn('est.get("sem_legenda")', doc)
        self.assertEqual(doc.count('"sem_legenda"'), 4)     # cena, blocos, quadro do storyboard e a conferência do queixo


class Pedido(Base):
    def setUp(self):
        super().setUp()
        d = self.criar_formato()
        dados = C.ler_json(d / 'formato.json')
        dados['legenda'] = {'desligavel': True, 'como': 'cenas.json: "sem_legenda": true'}
        C.gravar_json(d / 'formato.json', dados)
        d2 = self.criar_formato('fixo', modelos=('estilo',))
        dados = C.ler_json(d2 / 'formato.json')
        dados['legenda'] = {'desligavel': False, 'motivo': 'Já sai sem legenda.'}
        C.gravar_json(d2 / 'formato.json', dados)

    def prompts(self, j):
        return [P.prompt_esteira(j, 'ate_aprovacao'), P.prompt_esteira(j, 'depois')]

    def test_linha_so_quando_a_legenda_esta_desligada(self):
        j = self.job_formato()
        for p in self.prompts(j):
            self.assertNotIn('SEM LEGENDA', p)
        j['legenda'] = False
        for p in self.prompts(j):
            self.assertIn('SEM LEGENDA: não queime nem gere legenda neste vídeo', p)
            self.assertIn('Como desligar neste formato: cenas.json: "sem_legenda": true', p)
            self.assertIn('NÃO cobram legenda', p)
        j['legenda'] = True
        self.assertNotIn('SEM LEGENDA', self.prompts(j)[0])

    def test_formato_que_nao_desliga_nao_recebe_a_linha(self):
        j = self.job_formato(formato='fixo')
        j['legenda'] = False
        self.assertNotIn('SEM LEGENDA', self.prompts(j)[0])

    def test_criar_grava_legenda_false_so_quando_desligada(self):
        b = self.root / 'a.mp4'; b.write_bytes(b'x')
        j = P.criar('Teste', 'estilo', b, 'Sem', formato='doc-teste', legenda=False)
        self.assertIs(j['legenda'], False)
        self.assertIn('Sem legenda', (self.root / j['sandbox'] / 'BRIEF.md').read_text())
        b2 = self.root / 'b.mp4'; b2.write_bytes(b'x')
        self.assertNotIn('legenda', P.criar('Teste', 'estilo', b2, 'Com', formato='doc-teste'))

    def envia(self, formato, legenda):
        r = self.client.post('/criar', data={'formato': formato, 'cliente': 'Teste', 'titulo': 'Pedido ' + formato, 'legenda': legenda,
                                              'videos': (io.BytesIO(b'video'), 'a.mp4')}, content_type='multipart/form-data')
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        return P.carregar('Teste', 'pedido-' + formato)

    def test_criar_honra_o_interruptor_so_no_formato_que_desliga(self):
        self.assertIs(self.envia('doc-teste', '0')['legenda'], False)
        self.assertNotIn('legenda', self.envia('fixo', '0'))          # formato fixo: o 0 é ignorado
        self.assertTrue(self.client.get('/job/Teste/pedido-doc-teste').get_data(as_text=True).count('sem legenda') >= 1)

    def test_tela_criar_mostra_o_interruptor_ligavel_ou_travado(self):
        t = self.client.get('/criar').get_data(as_text=True)
        self.assertIn('id="legenda-on"', t)
        self.assertIn('Use sem legenda se o vídeo vai entrar em outro formato.', t)
        self.assertIn('name="legenda" id="legenda-campo" value="1"', t)   # padrão: ligada
        ok = self.client.get('/api/formato/doc-teste').get_json()['legenda']
        fixo = self.client.get('/api/formato/fixo').get_json()['legenda']
        self.assertTrue(ok['desligavel'])
        self.assertFalse(fixo['desligavel'])                              # a tela trava o interruptor e mostra o motivo
        self.assertEqual(fixo['motivo'], 'Já sai sem legenda.')
        self.assertIn('legOn.disabled=true', t)


class Reusar(Base):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(saidas, 'RAIZ', self.root))
        for slug, entrada in (('origem', 'video'), ('destino', 'video'), ('mista', 'video-ou-roteiro'), ('so-roteiro', 'roteiro'), ('evento', 'filmagem')):
            d = self.criar_formato(slug, modelos=('estilo',))
            dados = C.ler_json(d / 'formato.json')
            dados.update(entrada=entrada, titulo=slug.capitalize())
            C.gravar_json(d / 'formato.json', dados)
        self.pronto = self.content / 'output/estilo/final.mp4'
        self.pronto.parent.mkdir(parents=True, exist_ok=True)
        self.pronto.write_bytes(b'VIDEO-PRONTO' * 50)

    def test_so_aparecem_formatos_que_recebem_video_gravado(self):
        slugs = [o['slug'] for o in reuso.opcoes()]
        self.assertEqual(sorted(slugs), ['destino', 'mista', 'origem'])
        self.assertNotIn('origem', [o['slug'] for o in reuso.opcoes('origem')])

    def test_cria_job_com_a_copia_e_o_original_intacto(self):
        antes = self.pronto.read_bytes()
        j = reuso.usar(str(self.pronto.relative_to(self.root)), 'destino', 'Meu anúncio')
        self.assertEqual(j['titulo'], 'Meu anúncio (em Destino)')
        self.assertEqual((j['cliente'], j['formato'], j['status']), ('Teste', 'destino', 'novo'))
        copia = self.root / j['bruto']
        self.assertEqual(copia.read_bytes(), antes)
        self.assertNotEqual(copia, self.pronto)
        self.assertEqual(self.pronto.read_bytes(), antes)               # o original continua lá, igual
        self.assertNotIn('legenda', j)                                  # legenda ligada: quem decide é o formato de destino
        self.assertIn('REAPROVEITADO', j['briefing'])
        self.assertEqual(P.carregar('Teste', j['slug'])['status'], 'novo')   # nada disparou a IA

    def test_rotas_escolha_e_criacao(self):
        cam = str(self.pronto.relative_to(self.root))
        t = self.client.get('/reusar', query_string={'caminho': cam, 'titulo': 'Meu anúncio'}).get_data(as_text=True)
        self.assertIn('<b>Mista</b>', t)                                  # o formato de onde o vídeo veio (estilo → destino) não é oferecido
        self.assertNotIn('<b>Destino</b>', t)
        self.assertNotIn('So-roteiro', t)
        r = self.client.post('/reusar', data={'caminho': cam, 'formato': 'mista', 'titulo': 'Meu anúncio'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/job/Teste/', r.headers['Location'])
        self.assertEqual(self.client.post('/reusar', data={'caminho': cam, 'formato': 'so-roteiro'}).status_code, 302)
        self.assertEqual(len(P.listar('Teste')), 1)                     # formato sem entrada de vídeo: nada foi criado

    def test_trava_de_caminho_e_formato(self):
        with self.assertRaises(ValueError):
            reuso.usar('../fora.mp4', 'destino')
        with self.assertRaises(ValueError):
            reuso.usar(str(self.pronto.relative_to(self.root)), 'evento')


if __name__ == '__main__':
    unittest.main()
