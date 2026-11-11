"""Tela do passo 0 'Conversar' (peça B) e o Criar preenchido pelo briefing. Flask test client + cliente de API FALSO:
nenhum teste chama a API de verdade, nem grava em clientes/ ou app/jobs/ (tudo em pasta temporária)."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
import conversa
import pastas
from test_conversa import Falso, _png, _resp


def _eventos(texto: str) -> list[dict]:
    return [json.loads(l[6:]) for l in texto.split('\n\n') if l.startswith('data: ')]


class Tela(unittest.TestCase):
    def setUp(self):
        import servidor   # o app real: a página usa o base.html completo
        import simples
        self.simples = simples
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        (self.tmp / 'clientes').mkdir()
        self.api = Falso(
            _resp('Achei a capa da ótica.', ferramentas=[
                ('ver_imagem', {'pasta': 'Loja', 'arquivo': 'produto/capa.png'}),
                ('anotar_briefing', {'objetivo': 'Vender a Marca3', 'cliente': 'Cliente2', 'entrada': 'roteiro',
                                     'formato_sugerido': {'slug': 'explicador-3d', 'porque': 'conversa curta e engraçada'},
                                     'roteiro': 'Dono: Minha ótica vive vazia.\nAtendente: Agora não mais.',
                                     'material_liberado': [{'pasta': 'Loja', 'arquivo': 'produto/capa.png',
                                                            'papel': 'cena-produto', 'onde': 'fala 2'}],
                                     'referencia': {'video': 'Loja/refs/ref.mp4', 'segundo': 12.4,
                                                    'o_que_copiar': 'o corte seco pro produto'},
                                     'proibido': ['rosa neon']})]),
            _resp('Anotei tudo. Pode fechar.'))
        patches = [
            mock.patch.multiple(pastas, CONFIG=self.tmp / 'config' / 'pastas.json',
                                CLIENTES_DIR=self.tmp / 'clientes', INDICES=self.tmp / 'indices'),
            mock.patch.multiple(conversa, BRIEFINGS=self.tmp / 'briefings', MINIATURAS=self.tmp / 'mini'),
            mock.patch.object(conversa.custos, 'API_LIVRO', self.tmp / 'custos' / 'api.jsonl'),
            mock.patch.object(conversa, 'cliente_api', return_value=self.api),
            mock.patch('anthropic.Anthropic', side_effect=AssertionError('chamada real à API')),
            mock.patch.object(simples, 'CACHE', self.tmp / 'cache'),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)
        self.loja = self.tmp / 'mac' / 'Loja'
        _png(self.loja / 'produto' / 'capa.png')
        (self.loja / 'refs').mkdir()
        (self.loja / 'refs' / 'ref.mp4').write_bytes(b'video de mentira')
        (self.loja / '.env').write_text('ANTHROPIC_API_KEY=sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV0123\n', encoding='utf-8')
        pastas.ligar(str(self.loja), nome='Loja', tipo='referência')
        outra = self.tmp / 'mac' / 'Outra'
        _png(outra / 'foto.png')
        pastas.ligar(str(outra), nome='Outra', tipo='outro')
        self.c = servidor.app.test_client()

    def conversa_com_briefing(self) -> str:
        bid = self.c.post('/conversa/nova', json={'pastas': ['Loja'], 'modelo': 'sonnet'}).get_json()['id']
        r = self.c.post(f'/conversa/{bid}/mensagem', json={'texto': 'Anúncio da Marca3 no 3D, com a capa'})
        self.eventos = _eventos(r.get_data(as_text=True))
        return bid

    def test_tela_tem_pastas_modelo_custo_chat_card_e_pular(self):
        html = self.c.get('/conversar').get_data(as_text=True)
        for trecho in ('Conversar antes de criar', 'Pular →', '＋ Ligar pasta', 'data-modelo="sonnet"', 'data-modelo="opus"',
                       'id="cv-custo"', 'id="cv-falas"', 'Briefing até agora', 'Fechar briefing e seguir',
                       'É só teste: apagar quando eu aprovar', 'briefing.js'):
            self.assertIn(trecho, html)
        dados = json.loads(re.search(r'window\.CONVERSA = (\{.*?\});</script>', html).group(1))
        self.assertEqual({p['nome'] for p in dados['pastas']}, {'Loja', 'Outra'})
        self.assertEqual(dados['modelo'], 'sonnet')

    def test_conversa_simulada_ate_o_criar_preenchido(self):
        bid = self.conversa_com_briefing()
        tipos = [e['tipo'] for e in self.eventos]
        self.assertIn('miniatura', tipos)
        self.assertIn('briefing', tipos)
        self.assertEqual(tipos[-1], 'fim')
        self.assertEqual(len(self.api.pedidos), 2)          # duas voltas no cliente falso, nenhuma de verdade
        # a miniatura que a IA achou abre na tela (só de pasta ligada a esta conversa)
        r = self.c.get(f'/conversar/{bid}/arquivo', query_string={'pasta': 'Loja', 'arquivo': 'produto/capa.png'})
        self.assertEqual((r.status_code, r.mimetype), (200, 'image/jpeg'))
        r.close()
        # a tela retomada mostra a conversa e o card
        dados = json.loads(re.search(r'window\.CONVERSA = (\{.*?\});</script>',
                                     self.c.get(f'/conversar?id={bid}').get_data(as_text=True)).group(1))
        self.assertEqual(dados['conversa']['briefing']['formato_sugerido']['slug'], 'explicador-3d')
        self.assertTrue(any(f['papel'] == 'ia' for f in dados['conversa']['falas']))
        # o João edita o card e marca "é só teste"
        self.c.post(f'/conversa/{bid}/briefing', json={'descartavel': True, 'peculiaridade': 'capa no telão'})
        self.assertTrue(self.c.post(f'/conversa/{bid}/fechar').get_json()['briefing']['descartavel'])
        # conversa fechada não reabre o chat: vai pro Criar
        self.assertIn('/criar-agora?briefing=', self.c.get(f'/conversar?id={bid}').headers['Location'])
        novo = self.c.get(f'/criar-agora?briefing={bid}').get_data(as_text=True)   # o Novo vídeo chega preenchido (30-out-2026)
        self.assertIn(f'name="conversa" value="{bid}"', novo)
        self.assertIn('name="mat_conversa" value="0"', novo)
        self.assertIn('name="descartavel" value="1"', novo)
        self.assertIn('name="ref" value="refs/ref.mp4"', novo)
        self.assertIn('name="ref_pasta" value="Loja"', novo)
        self.assertIn('Atendente: Agora não mais.', novo)
        pre_novo = json.loads(re.search(r'PRE = (\{.*?\}), est = ', novo).group(1))
        self.assertIn('Vender a Marca3', pre_novo['direcao'])
        self.assertEqual(pre_novo['estilo'], 'explicador-3d')
        self.assertIn('Já preenchi com o que vocês combinaram na conversa', novo)
        html = self.c.get(f'/criar?briefing={bid}').get_data(as_text=True)
        pre = json.loads(re.search(r'var PRE=(\{.*?\});\n', html).group(1))
        self.assertEqual((pre['formato'], pre['cliente'], pre['entrada']), ('explicador-3d', 'Cliente2', 'roteiro'))
        self.assertIn('Atendente: Agora não mais.', pre['roteiro'])
        self.assertIn('Vender a Marca3', pre['texto'])
        self.assertIn('Não usar: rosa neon', pre['texto'])
        self.assertTrue(pre['descartavel'])
        self.assertEqual([m['nome'] for m in pre['material']], ['capa.png'])
        self.assertEqual((pre['ref']['pasta'], pre['ref']['rel'], pre['ref']['segundo']), ('Loja', 'refs/ref.mp4', 12.4))
        self.assertIn('Do briefing da conversa', html)
        self.assertIn('name="mat_conversa" value="0"', html)
        self.assertIn('id="ref-seletor"', html)
        self.assertIn('name="descartavel"', html)

    def test_criar_copia_material_e_referencia_pro_job(self):
        bid = self.conversa_com_briefing()
        self.c.post(f'/conversa/{bid}/fechar')
        sb = self.tmp / 'sandbox'
        criados, salvos = [], []

        def criar_falso(cli, mod, bruto, titulo, briefing, *a, **kw):
            j = {'cliente': cli, 'modelo': mod, 'slug': 'otica', 'sandbox': str(sb), 'briefing': briefing, 'materiais': []}
            criados.append(j)
            return j

        p = self.simples
        with mock.patch.object(p._fmt, 'usar', return_value=('Cliente2', 'explicador-3d')), \
                mock.patch.object(p._prod, 'criar', side_effect=criar_falso), \
                mock.patch.object(p._prod, 'salvar', side_effect=lambda j: salvos.append(dict(j))), \
                mock.patch.object(p._prod, 'brief_md', side_effect=lambda j: j['briefing']):
            r = self.c.post('/criar', data={'formato': 'explicador-3d', 'cliente': 'Cliente2', 'roteiro': 'Dono: oi',
                                            'briefing': 'Vender a ótica', 'conversa': bid, 'mat_conversa': '0',
                                            'ref': 'refs/ref.mp4', 'ref_pasta': 'Loja', 'segundo': '12.4',
                                            'ref_copiar': 'o corte seco', 'descartavel': '1'})
        self.assertEqual(r.status_code, 302)
        job = salvos[-1]
        self.assertEqual(job['materiais'], ['material/capa.png', 'material/ref.mp4'])
        self.assertIn('material/capa.png → cena-produto (fala 2)', job['briefing'])
        self.assertIn('REFERÊNCIA DESTE VÍDEO: material/ref.mp4, no segundo 12,4 s. Estilo a aproveitar: o corte seco', job['briefing'])
        self.assertTrue(job['descartavel'])
        self.assertEqual(job['conversa'], bid)
        usos = json.loads((sb / 'material' / 'usos.json').read_text())
        self.assertEqual(usos['capa.png']['onde'], ['fala 2'])
        self.assertTrue((self.loja / 'produto' / 'capa.png').is_file())        # o original fica onde estava
        self.assertIn('vale só pra este vídeo', (sb / 'BRIEF.md').read_text())

    def test_arquivo_so_de_pasta_desta_conversa_e_sem_segredo(self):
        bid = self.c.post('/conversa/nova', json={'pastas': ['Loja']}).get_json()['id']
        for pasta, arq in (('Outra', 'foto.png'), ('Loja', '.env'), ('Loja', '../Outra/foto.png'), ('Nada', 'x.png')):
            r = self.c.get(f'/conversar/{bid}/arquivo', query_string={'pasta': pasta, 'arquivo': arq})
            self.assertEqual(r.status_code, 404, (pasta, arq))
        self.assertEqual(self.c.get('/conversar/../../etc/arquivo').status_code, 404)

    def test_ligar_pasta_pelo_finder_ou_colando(self):
        nova = self.tmp / 'mac' / 'Swipe File'
        nova.mkdir()
        with mock.patch.object(pastas, 'escolher_no_finder', return_value=str(nova)):
            d = self.c.post('/conversar/ligar', json={'tipo': 'swipe'}).get_json()
        self.assertEqual(d['pasta'], {'nome': 'Swipe File', 'tipo': 'swipe'})
        self.assertIn('Swipe File', [p['nome'] for p in d['pastas']])
        with mock.patch.object(pastas, 'escolher_no_finder', return_value=None):
            self.assertEqual(self.c.post('/conversar/ligar', json={}).status_code, 400)
        r = self.c.post('/conversar/ligar', json={'caminho': str(self.tmp / 'nao-existe')})
        self.assertEqual(r.status_code, 400)
        self.assertIn('não encontrada', r.get_json()['erro'])

    def test_pasta_de_um_cliente_nao_aparece_pra_outro(self):
        dele = self.tmp / 'mac' / 'Cliente2 di Fiori'
        dele.mkdir()
        self.c.post('/conversar/ligar', json={'caminho': str(dele), 'tipo': 'cliente', 'cliente': 'Cliente2'})
        nomes = lambda cli: [p['nome'] for p in self.c.get('/conversar/pastas', query_string={'cliente': cli}).get_json()]
        self.assertIn('Cliente2 di Fiori', nomes('Cliente2'))
        self.assertNotIn('Cliente2 di Fiori', nomes('Cliente4'))

    def test_criar_sem_conversa_continua_igual(self):
        html = self.c.get('/criar').get_data(as_text=True)
        self.assertIn('var PRE=null;', html)
        self.assertNotIn('Do briefing da conversa', html)
        self.assertIn('/conversar', html)
        self.assertIn('Briefing não encontrado', self.c.get('/criar?briefing=nao-existe').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
