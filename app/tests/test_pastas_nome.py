"""Ligar pasta pelo NOME, ESTUDIO.md com frontmatter, contexto com teto de tokens e rascunho que não grava sozinho.
Tudo em pasta temporária e com cliente de API falso: nenhum teste chama a API nem varre o disco de verdade."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'tests'))
import conversa
import pastas
from test_conversa import Falso, _resp

FRONT = '''---
liberado: [mockups, produto]
proibido: [crm]
fatos: {preço: 'R$ 67', oferta: frete grátis}
tom: 'direto, sem enrolação'
resumo: 'Loja de óculos do Cliente2'
---
# Corpo longo, só sob demanda
liberado: tudo
proibido: produto
'''


def _txt(p: Path, texto: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding='utf-8')


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        (self.tmp / 'clientes').mkdir()
        self.projetos = self.tmp / 'projetos'
        self.projetos.mkdir()
        self.patches = [
            mock.patch.multiple(pastas, CONFIG=self.tmp / 'config' / 'pastas.json', CLIENTES_DIR=self.tmp / 'clientes',
                                INDICES=self.tmp / 'indices', PROJETOS=self.projetos),
            mock.patch.multiple(conversa, BRIEFINGS=self.tmp / 'briefings', MINIATURAS=self.tmp / 'mini'),
            mock.patch.object(conversa.custos, 'API_LIVRO', self.tmp / 'custos' / 'api.jsonl'),
            mock.patch.object(conversa, 'cliente_api', side_effect=AssertionError('chamada real à API')),
            mock.patch.object(conversa.formatos, 'listar', return_value=[]),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self._tmp.cleanup()

    def nomes(self, texto):
        return [c['nome'] for c in pastas.achar(texto)]


class AcharPeloNome(Base):
    def test_acento_hifen_espaco_e_caixa_dao_no_mesmo(self):
        (self.projetos / 'Trafego' / 'Marca3').mkdir(parents=True)
        for q in ('marca3', 'MARCA3', 'marca3', 'Marca3', 'marca3'):
            r = pastas.achar(q)
            self.assertEqual([c['nome'] for c in r], ['Marca3'], q)
        c = pastas.achar('marca3')[0]
        self.assertTrue(c['caminho'].endswith('Trafego/Marca3'))
        self.assertFalse(c['tem_manifesto'])
        self.assertIn('arquivo', c['tamanho'])

    def test_so_procura_nas_raizes_permitidas(self):
        fora = self.tmp / 'fora' / 'Marca3'
        fora.mkdir(parents=True)
        cerebro = self.tmp / 'Cerebro' / 'Clientes' / 'Marca3'
        cerebro.mkdir(parents=True)
        visitadas = []
        andar = os.walk
        with mock.patch.object(pastas.os, 'walk', side_effect=lambda r, *a, **k: (visitadas.append(str(r)), andar(r, *a, **k))[1]):
            self.assertEqual(pastas.achar('marca3'), [])
        self.assertFalse([v for v in visitadas if v.startswith(str(self.tmp / 'fora')) or v.startswith(str(self.tmp / 'Cerebro'))])
        # entra na lista de config: aí sim
        _txt(pastas.CONFIG, json.dumps({'pastas': [], 'pastas_raizes': [str(self.tmp / 'fora')]}))
        self.assertEqual(self.nomes('marca3'), ['Marca3'])
        self.assertEqual(self.nomes('marca'), ['Marca3'])

    def test_nao_varre_a_home_nem_alem_de_3_niveis(self):
        _txt(pastas.CONFIG, json.dumps({'pastas_raizes': [str(Path.home())]}))
        self.assertNotIn(Path.home().resolve(), [r for r, _ in pastas.raizes_busca()])
        (self.projetos / 'a' / 'b' / 'c' / 'marca3').mkdir(parents=True)   # nível 4: fundo demais
        self.assertEqual(pastas.achar('marca3'), [])
        (self.projetos / 'a' / 'b' / 'marca3').mkdir()                      # nível 3: entra
        self.assertEqual(len(pastas.achar('marca3')), 1)

    def test_pasta_ligada_e_cliente_do_estudio_tambem_valem(self):
        (self.tmp / 'clientes' / 'Cliente2' / 'marca2Content').mkdir(parents=True)
        self.assertEqual(self.nomes('cliente2'), ['Cliente2'])
        solta = self.tmp / 'solta' / 'Loja Nova'
        (solta / 'mockups').mkdir(parents=True)
        pastas.ligar(str(solta), nome='Loja Nova', tipo='outro')
        r = pastas.achar('loja nova')
        self.assertEqual([c['ligada'] for c in r], ['Loja Nova'])
        self.assertEqual(self.nomes('mockups'), ['mockups'])   # subpasta de pasta ligada

    def test_bloqueio_e_respeitado(self):
        for n in ('node_modules/marca3', '.git/marca3', 'senha-marca3', 'marca3-token',
                  'crm-marca3', '.marca3', 'x/.env/marca3'):
            (self.projetos / n).mkdir(parents=True)
        self.assertEqual(pastas.achar('marca3'), [])
        (self.projetos / 'Marca3').mkdir()
        self.assertEqual(self.nomes('marca3'), ['Marca3'])

    def test_ordem_e_limite_de_5(self):
        for n in ('Minha Marca3', 'Marca3 Trafego', 'Marca3', 'Marca3 2', 'Marca3 3',
                  'Marca3 4', 'Outra Coisa'):
            (self.projetos / n).mkdir()
        r = pastas.achar('marca3')
        self.assertEqual(len(r), 5)
        self.assertEqual(r[0]['nome'], 'Marca3')                       # exato primeiro
        self.assertNotIn('Outra Coisa', [c['nome'] for c in r])
        self.assertEqual(self.nomes('minha marca')[0], 'Minha Marca3')
        # contém por último, mesmo tendo direcionamento? não: a ordem vem antes; no mesmo grau, quem tem ESTUDIO.md sobe
        _txt(self.projetos / 'Marca3 4' / 'ESTUDIO.md', FRONT)
        r = pastas.achar('marca3')
        self.assertEqual([c['nome'] for c in r][:2], ['Marca3', 'Marca3 4'])
        self.assertTrue(r[1]['tem_manifesto'])
        self.assertEqual(r[1]['caminho'], str(self.projetos / 'Marca3 4'))

    def test_texto_curto_ou_vazio_nao_acha_nada(self):
        (self.projetos / 'a').mkdir()
        self.assertEqual(pastas.achar(''), [])
        self.assertEqual(pastas.achar('a'), [])

    def test_gravar_a_lista_nao_apaga_as_raizes_do_config(self):
        _txt(pastas.CONFIG, json.dumps({'pastas': [], 'pastas_raizes': ['/tmp/x']}))
        d = self.tmp / 'mac' / 'Loja'
        d.mkdir(parents=True)
        pastas.ligar(str(d), nome='Loja')
        self.assertEqual(json.loads(pastas.CONFIG.read_text())['pastas_raizes'], ['/tmp/x'])


class FrontmatterPrimeiro(Base):
    def test_frontmatter_e_lido_sozinho(self):
        d = self.tmp / 'Loja'
        _txt(d / 'ESTUDIO.md', FRONT + ('linha de corpo sem fim\n' * 50000))   # corpo gigante, contraditório
        m = pastas.ler_manifesto(d)
        self.assertEqual(m['formato'], 'frontmatter')
        self.assertEqual(m['liberado'], ['mockups', 'produto'])                 # o 'liberado: tudo' do corpo não vale
        self.assertEqual(m['proibido'], ['crm'])
        self.assertIn('preço: R$ 67', m['fatos'])
        self.assertEqual(m['tom'], 'direto, sem enrolação')
        self.assertEqual(m['resumo'], 'Loja de óculos do Cliente2')
        self.assertEqual(set(pastas.ler_frontmatter(d)), {'liberado', 'proibido', 'fatos', 'tom', 'resumo'})

    def test_so_a_cabeca_do_arquivo_e_lida(self):
        d = self.tmp / 'Loja'
        _txt(d / 'ESTUDIO.md', FRONT + 'x' * 200000)
        lido = []
        abrir = Path.open

        def espia(self, *a, **k):
            f = abrir(self, *a, **k)
            real = f.read
            f.read = lambda n=-1: (lido.append(n), real(n))[1]
            return f
        with mock.patch.object(Path, 'open', espia), mock.patch.object(Path, 'read_text', side_effect=AssertionError('leu o arquivo todo')):
            pastas.ler_manifesto(d)
        self.assertEqual(lido, [pastas.HEAD_MANIFESTO])

    def test_formato_antigo_continua_valendo(self):
        d = self.tmp / 'Velha'
        _txt(d / 'ESTUDIO.md', '## Liberado\n- mockups\n- produto\n\n## Fatos\n- preço: R$ 67\n\nTom: direto\n')
        m = pastas.ler_manifesto(d)
        self.assertEqual((m['formato'], m['liberado'], m['tom']), ('antigo', ['mockups', 'produto'], 'direto'))
        self.assertEqual(m['fatos'], ['preço: R$ 67'])
        # '---' que não fecha ou YAML quebrado cai no antigo, sem estourar
        _txt(d / 'ESTUDIO.md', '---\nliberado: [a, b\n---\nTom: seco\n')
        self.assertEqual(pastas.ler_manifesto(d)['formato'], 'antigo')

    def test_frontmatter_liberado_filtra_o_indice(self):
        d = self.tmp / 'Loja'
        (d / 'produto').mkdir(parents=True)
        _txt(d / 'produto' / 'a.txt', 'ok')
        _txt(d / 'crm' / 'b.txt', 'ok')
        _txt(d / 'ESTUDIO.md', FRONT)
        ind = pastas.indexar({'nome': 'Loja', 'caminho': str(d), 'tipo': 'outro'}, miniaturas=False)
        self.assertEqual({e['rel'] for e in ind['arquivos']}, {'produto/a.txt'})


class ContextoComTeto(Base):
    def _pasta_grande(self, nome, subs=200, arqs=3):
        d = self.tmp / 'mac' / nome
        for i in range(subs):
            for j in range(arqs):
                _txt(d / f'subpasta-numero-{i}' / f'arquivo-{j}.txt', 'texto')
        _txt(d / 'ESTUDIO.md', '---\nliberado: [' + ', '.join(f'subpasta-numero-{i}' for i in range(subs)) + ']\n'
             'fatos: {' + ', '.join(f'fato{i}: "{"valor muito longo " * 20}"' for i in range(40)) + '}\n'
             f"tom: '{'tom longo ' * 200}'\nresumo: '{'resumo longo ' * 200}'\n---\n")
        return pastas.ligar(str(d), nome=nome, tipo='outro')

    def test_teto_duro_de_1500_tokens_com_uma_ou_varias_pastas(self):
        for nome in ('Grande', 'Enorme', 'Imensa'):
            self._pasta_grande(nome)
        for marcadas in (['Grande'], ['Grande', 'Enorme', 'Imensa']):
            ativ = pastas.ativas('', marcadas)
            linhas, gasto = conversa.contexto_pastas(ativ)
            total = pastas.estimar_tokens('\n'.join(linhas))
            self.assertLessEqual(total, conversa.TETO_TOKENS_PASTAS, marcadas)
            self.assertLessEqual(gasto['tokens'], conversa.TETO_TOKENS_PASTAS)
            self.assertEqual(set(gasto['pastas']), set(marcadas))

    def test_contexto_tem_frontmatter_e_indice_resumido_sem_listar_arquivos(self):
        d = self.tmp / 'mac' / 'Loja'
        _txt(d / 'mockups' / 'a.png', 'x')
        _txt(d / 'mockups' / 'b.png', 'x')
        _txt(d / 'produto' / 'capa.txt', 'x')
        _txt(d / 'ESTUDIO.md', FRONT)
        pastas.ligar(str(d), nome='Loja', tipo='outro')
        linhas, gasto = conversa.contexto_pastas(pastas.ativas('', ['Loja']))
        txt = '\n'.join(linhas)
        for esperado in ('R$ 67', 'direto, sem enrolação', 'Loja de óculos', 'mockups/ (', 'produto/ ('):
            self.assertIn(esperado, txt)
        self.assertNotIn('capa.txt', txt)           # nome de arquivo só pelas ferramentas
        self.assertNotIn('Corpo longo', txt)        # corpo do ESTUDIO.md também
        self.assertGreater(gasto['tokens'], 0)

    def test_estimativa_fica_no_briefing_depois_de_uma_mensagem(self):
        self._pasta_grande('Grande', subs=30)
        bid = conversa.criar(pastas_marcadas=['Grande'])['id']
        api = Falso(_resp('oi'))
        eventos = list(conversa.enviar(bid, 'oi', api=api))
        self.assertEqual(eventos[-1]['tipo'], 'fim')
        g = conversa.briefing(bid)['gasto_pastas']
        self.assertEqual(set(g), {'tokens', 'teto', 'pastas'})
        self.assertGreater(g['tokens'], 0)
        self.assertLessEqual(g['tokens'], g['teto'])
        # o texto que foi de fato pra API respeita o teto no trecho das pastas
        fixo = api.pedidos[0]['system'][0]['text']
        trecho = fixo[fixo.index('PASTAS LIGADAS'):]
        self.assertLessEqual(pastas.estimar_tokens(trecho), conversa.TETO_TOKENS_PASTAS + 60)
        self.assertEqual(g, eventos[-1]['briefing']['gasto_pastas'])


class RascunhoNaoGravaSozinho(Base):
    def _loja(self):
        d = self.tmp / 'mac' / 'Loja'
        for sub in ('mockups', 'produto', 'senhas', 'crm-clientes', 'node_modules', '.git', 'chaves-api', 'logo'):
            _txt(d / sub / 'a.png', 'x')
        _txt(d / 'solto.env', 'x')
        return d

    def _foto(self, d):
        return {str(p.relative_to(d)): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(d.rglob('*')) if p.is_file()}

    def test_propor_nao_grava_nada(self):
        d = self._loja()
        antes = self._foto(d)
        r = pastas.propor_manifesto(d)
        self.assertEqual(self._foto(d), antes)
        self.assertFalse((d / 'ESTUDIO.md').exists())
        self.assertFalse(r['existe'])
        self.assertTrue(r['texto'].startswith('---\n'))

    def test_subpastas_viram_candidatas_e_segredo_nunca_entra(self):
        r = pastas.propor_manifesto(self._loja())
        self.assertEqual(r['liberado'], ['logo', 'mockups', 'produto'])
        for proibida in ('senhas', 'crm', 'node_modules', '.git', 'chaves', '.env'):
            self.assertNotIn(proibida, r['texto'])
        # o rascunho é frontmatter válido e o parser entende
        d = self.tmp / 'copia'
        _txt(d / 'ESTUDIO.md', r['texto'])
        m = pastas.ler_manifesto(d)
        self.assertEqual((m['formato'], m['liberado']), ('frontmatter', ['logo', 'mockups', 'produto']))

    def test_gravar_so_com_aprovacao_e_sem_sobrescrever(self):
        d = self._loja()
        texto = pastas.propor_manifesto(d)['texto']
        with self.assertRaises(ValueError):
            pastas.gravar_manifesto(d, texto)
        with self.assertRaises(ValueError):
            pastas.gravar_manifesto(d, texto, aprovado=False)
        self.assertFalse((d / 'ESTUDIO.md').exists())
        pastas.gravar_manifesto(d, texto, aprovado=True)
        self.assertTrue((d / 'ESTUDIO.md').is_file())
        with self.assertRaises(ValueError):          # já existe: não sobrescreve
            pastas.gravar_manifesto(d, texto, aprovado=True)

    def test_gravar_recusa_texto_ruim(self):
        d = self._loja()
        for ruim in ('sem frontmatter', '---\nliberado: [a, b\n---\n',
                     '---\ntom: "senha = abcdefghijkl1234"\n---\n'):
            with self.assertRaises(ValueError, msg=ruim):
                pastas.gravar_manifesto(d, ruim, aprovado=True)
        self.assertFalse((d / 'ESTUDIO.md').exists())


class Telas(Base):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
        import servidor
        self.c = servidor.app.test_client()

    def test_rotas_achar_propor_e_gravar(self):
        d = self.projetos / 'Marca3'
        (d / 'produto').mkdir(parents=True)
        r = self.c.get('/conversar/achar', query_string={'q': 'marca3'}).get_json()
        self.assertEqual([x['nome'] for x in r], ['Marca3'])
        lig = self.c.post('/conversar/ligar', json={'caminho': r[0]['caminho']}).get_json()
        self.assertFalse(lig['tem_manifesto'])
        prop = self.c.post('/conversar/manifesto/propor', json={'nome': 'Marca3'}).get_json()
        self.assertIn('produto', prop['texto'])
        self.assertFalse((d / 'ESTUDIO.md').exists())
        sem = self.c.post('/conversar/manifesto/gravar', json={'nome': 'Marca3', 'texto': prop['texto']})
        self.assertEqual(sem.status_code, 400)
        self.assertFalse((d / 'ESTUDIO.md').exists())
        ok = self.c.post('/conversar/manifesto/gravar', json={'nome': 'Marca3', 'texto': prop['texto'], 'aprovado': True})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue((d / 'ESTUDIO.md').is_file())
        self.assertEqual(self.c.post('/conversar/manifesto/propor', json={'nome': 'Nao Ligada'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
