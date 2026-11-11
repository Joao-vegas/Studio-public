"""Cliente é só a pele: a página mostra identidade + vídeos entregues (sem formato vazio nem contagem 0), a pasta
output/<formato>/ só nasce com o primeiro vídeo, cliente novo nasce sem pastas de formato e a limpeza de pastas vazias
respeita a trava. Tudo em pasta temporária; nada pago."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from test_esteira import Base, C, P
import novo_cliente
import saidas as S


class ClientePele(Base):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(S, 'RAIZ', self.root))
        self.out = self.content / 'output'
        C.gravar_json(self.root / 'clientes/Teste/identidade.json',
                      {'cores': ['#112233', '#aabbcc'], 'fontes': 'Anton; Barlow', 'uso': 'sério, sem gíria', 'papeis': {'x': '#112233'}})

    def pagina(self, nome='Teste'):
        r = self.client.get(f'/cliente/{nome}')
        self.assertEqual(r.status_code, 200)
        return r.get_data(as_text=True)

    def test_pagina_mostra_identidade_e_videos_sem_formato_vazio(self):
        self.job('exportado')
        for vazia in ('anuncios', 'twitter-meme'):
            (self.out / vazia).mkdir()
        t = self.pagina()
        self.assertIn('#112233', t)
        self.assertIn('Anton · Barlow', t)
        self.assertIn('sério, sem gíria', t)
        self.assertIn('Vídeos dele', t)   # 29-out: a página do cliente virou cabeçalho (cara) + vídeos + estilos; o resto recolhido em "Mais opções"
        self.assertIn('Meu vídeo', t)
        for sumiu in ('anuncios', 'twitter-meme', 'calibrado', 'Formatos que ele usa'):
            self.assertNotIn(sumiu, t)
        self.assertLess(t.index('cl-cab'), t.index('Vídeos dele'))
        self.assertLess(t.index('Vídeos dele'), t.index('id="material"'))

    def test_sem_video_nao_mostra_contagem_zero_nem_ajustes(self):
        t = self.pagina()
        self.assertIn('Ainda nenhum vídeo pronto', t)
        self.assertNotIn('0 vídeo', t)
        self.assertNotIn('Ajustes aprendidos', t)
        self.assertNotIn('0 vídeo', self.client.get('/clientes').get_data(as_text=True))
        self.assertNotIn('0 vídeo', self.client.get('/criar').get_data(as_text=True))

    def test_ajustes_aprendidos_so_com_regra_e_recolhidos(self):
        C.gravar_json(self.mod / 'aprendizado/regras.json', {'regras': [{'id': 'a', 'titulo': 'Sem gíria', 'texto': 'x', 'categoria': 'tom'}]})
        t = self.pagina()
        self.assertIn('<summary>Ajustes aprendidos deste cliente</summary>', t)
        self.assertGreater(t.index('Ajustes aprendidos'), t.index('Templates do Teste'))

    def test_pasta_de_saida_so_nasce_com_o_video(self):
        self.assertFalse(self.out.exists())
        bruto = self.root / 'bruto.mp4'
        bruto.write_bytes(b'RAW')
        job = P.criar('Teste', 'estilo', bruto, 'Novo vídeo')
        self.assertFalse(self.out.exists(), 'criar o job não pode criar output/')
        self.assertIn('output/estilo/', job['saida_esperada'])
        self.assertEqual(S.listar('Teste'), [])
        self.assertEqual(C.cliente('Teste')['n_videos'], 0)
        self.assertIn('Ainda nenhum vídeo pronto', self.pagina())   # pasta inexistente = lista vazia, sem erro
        # quem gera o vídeo cria a pasta no momento (gerar.sh: mkdir -p)
        final = self.root / job['saida_esperada']
        final.parent.mkdir(parents=True)
        final.write_bytes(b'MP4')
        self.assertEqual([i['slug'] for i in S.listar('Teste')], [job['slug']])

    def test_cliente_novo_nasce_no_padrao_com_as_5_pastas(self):
        cli = novo_cliente.criar('Carla', descricao='Loja')
        pasta = self.root / 'clientes/Carla'
        self.assertEqual(sorted(p.name for p in pasta.iterdir()), ['carlaContent', 'identidade.json'])
        cinco = ['entrada', 'material', 'modelos', 'output', 'transcricoes']
        self.assertEqual(sorted(p.name for p in (pasta / 'carlaContent').iterdir()), cinco)
        for sub in cinco:
            self.assertEqual([p.name for p in (pasta / 'carlaContent' / sub).iterdir()], ['.gitkeep'])
        ident = C.ler_json(pasta / 'identidade.json')
        self.assertEqual((ident['cliente'], ident['descricao']), ('Carla', 'Loja'))
        self.assertTrue(ident['cores'] and ident['fontes'] and ident['tom'])
        self.assertEqual(cli['nome'], 'Carla')
        self.assertEqual(cli['n_modelos'], 0)
        t = self.pagina('Carla')
        self.assertIn('Ainda nenhum vídeo pronto', t)
        self.assertEqual(S.listar('Carla'), [])

    def test_cliente_novo_aparece_nas_telas_e_pela_tela_de_novo_cliente(self):
        r = self.client.post('/novo-cliente', data={'nome': 'João Pé', 'descricao': 'x'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue((self.root / 'clientes/JoaoPe/joaopeContent/transcricoes/.gitkeep').is_file())
        for rota in ('/clientes', '/criar', '/cliente/JoaoPe', '/novo-cliente'):
            resp = self.client.get(rota)
            self.assertEqual(resp.status_code, 200, rota)
        self.assertIn('JoaoPe', self.client.get('/clientes').get_data(as_text=True))
        self.assertIn('JoaoPe', self.client.get('/criar').get_data(as_text=True))
        for ruim in ('..', 'a/b', ''):
            r = self.client.post('/novo-cliente', data={'nome': ruim}, follow_redirects=True)
            self.assertIn('✗', r.get_data(as_text=True))
        self.assertFalse((self.root / 'clientes/ab').exists())

    def test_limpar_vazias_nunca_remove_as_5_pastas_do_cliente(self):
        novo_cliente.criar('Carla')
        content = self.root / 'clientes/Carla/carlaContent'
        for sub in ('entrada', 'material', 'modelos', 'output', 'transcricoes'):   # tira o .gitkeep: as 5 ficam VAZIAS
            (content / sub / '.gitkeep').unlink()
        (content / 'output/anuncios').mkdir()
        achadas = S.limpar_pastas_vazias(dry_run=False)
        self.assertIn('clientes/Carla/carlaContent/output/anuncios', achadas)
        self.assertEqual(len([a for a in achadas if a.startswith('clientes/Carla/')]), 1)
        for sub in ('entrada', 'material', 'modelos', 'output', 'transcricoes'):
            self.assertTrue((content / sub).is_dir(), sub)

    def test_salvar_a_cara_mantem_o_resto_do_identidade(self):
        r = self.client.post('/cliente/Teste/identidade', data={'cores': '#000000', 'fontes': 'Anton; Bebas', 'tom': 'curto'})
        self.assertEqual(r.status_code, 302)
        d = C.ler_json(self.root / 'clientes/Teste/identidade.json')
        self.assertEqual((d['cores'], d['fontes'], d['tom'], d['papeis']), (['#000000'], ['Anton', 'Bebas'], 'curto', {'x': '#112233'}))


class LimparVazias(Base):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(S, 'RAIZ', self.root))
        self.out = self.content / 'output'
        (self.out / 'anuncios').mkdir(parents=True)
        (self.out / 'twitter-meme/ep/quadros').mkdir(parents=True)        # vazia dentro de vazia
        (self.out / 'dialogo-3d/ep1').mkdir(parents=True)
        (self.out / 'dialogo-3d/ep1/folha.jpg').write_bytes(b'j')
        (self.out / 'dialogo-3d/vazia').mkdir()
        (self.out / 'dividido-mascara').mkdir()
        (self.out / 'dividido-mascara/.gitkeep').touch()                  # tem arquivo (mesmo oculto): fica
        self.fora = self.content / 'material/colecao'
        self.fora.mkdir(parents=True)
        self.fora2 = self.root / 'clientes/Teste/documentacao'
        self.fora2.mkdir()

    def estado(self):
        return sorted(str(p.relative_to(self.root)) for p in (self.root / 'clientes').rglob('*'))

    def test_dry_run_so_lista(self):
        antes = self.estado()
        achadas = S.limpar_pastas_vazias()
        self.assertEqual(self.estado(), antes)
        base = 'clientes/Teste/testeContent/output/'
        self.assertEqual(sorted(achadas), sorted(base + x for x in (
            'anuncios', 'twitter-meme', 'twitter-meme/ep', 'twitter-meme/ep/quadros', 'dialogo-3d/vazia')))

    def test_remove_so_vazias_de_baixo_pra_cima_e_nunca_arquivo_ou_fora_de_output(self):
        achadas = S.limpar_pastas_vazias(dry_run=False)
        self.assertEqual(achadas[0], 'clientes/Teste/testeContent/output/twitter-meme/ep/quadros')   # filho antes do pai
        self.assertFalse((self.out / 'anuncios').exists())
        self.assertFalse((self.out / 'twitter-meme').exists())
        self.assertFalse((self.out / 'dialogo-3d/vazia').exists())
        self.assertTrue((self.out / 'dialogo-3d/ep1/folha.jpg').is_file())
        self.assertTrue((self.out / 'dividido-mascara/.gitkeep').exists())
        self.assertTrue(self.out.is_dir(), 'a própria output/ não sai')
        self.assertTrue(self.fora.is_dir() and self.fora2.is_dir(), 'vazias fora de output/ ficam')
        self.assertEqual(S.limpar_pastas_vazias(dry_run=False), [])

    def test_link_simbolico_e_trava_de_caminho(self):
        alvo = self.root / 'fora-vazia'
        alvo.mkdir()
        (self.out / 'atalho').symlink_to(alvo)
        S.limpar_pastas_vazias(dry_run=False)
        self.assertTrue(alvo.is_dir() and (self.out / 'atalho').is_symlink())
        for ruim in (self.fora, self.out, self.root / 'clientes', self.out / '..' / 'material'):
            with self.subTest(ruim=str(ruim)), self.assertRaises(ValueError):
                S.conferir_pasta_vazia(ruim)
        S.conferir_pasta_vazia(self.out / 'anuncios')


if __name__ == '__main__':
    unittest.main()
