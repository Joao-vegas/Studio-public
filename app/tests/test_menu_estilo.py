"""Menu enxuto, "Criar estilo novo" e "Melhorias deste estilo" (30-out-2026). Fixtures temporárias: nada pago, nada de rede."""
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from test_esteira import Base, C
import melhoria as M
import auto_juntar as AJ


class MenuEEstilo(Base):
    def menu(self, caminho='/'):
        t = self.client.get(caminho).get_data(as_text=True)
        lado = t.split('<aside class="s-nav">')[1].split('</aside>')[0]
        return t, re.findall(r'<a href="([^"]+)" class="s-item', lado)

    def test_menu_sem_o_que_tem_outra_porta_e_as_rotas_seguem_de_pe(self):
        _, hrefs = self.menu()
        for saiu in ('/novo-lote', '/editar', '/melhorias', '/elenco'):
            self.assertNotIn(saiu, hrefs)
        for fica in ('/', '/andamento', '/aprovar', '/videos', '/formatos', '/referencias', '/clientes', '/config'):
            self.assertIn(fica, hrefs)
        for rota in ('/melhorias', '/elenco', '/novo-lote', '/editar', '/andamento'):
            self.assertEqual(self.client.get(rota).status_code, 200, rota)

    def test_estilos_tem_o_botao_criar_estilo_novo(self):
        self.criar_formato()
        t = self.client.get('/formatos').get_data(as_text=True)
        self.assertIn('id="esn-criar"', t)
        self.assertIn('/referencias?novo=1#jogar', t)
        self.assertIn('o Estúdio monta o estilo e ele vira pronto quando você aprovar o 1º vídeo', t)

    def test_jogar_um_video_com_novo_marca_a_opcao(self):
        t = self.client.get('/referencias?novo=1').get_data(as_text=True)
        self.assertIn('name="estilo_novo" value="1" checked', t)
        self.assertNotIn('checked', self.client.get('/referencias').get_data(as_text=True).split('name="estilo_novo"')[1][:40])

    def test_estilo_novo_pedido_ignora_o_parecido(self):
        votado = ('explicador-3d', 'a leitura do estilo apontou esse')
        with patch.object(AJ, '_decidir', return_value=votado), patch.object(AJ, '_novo_estilo', return_value='meu-novo') as nn, \
             patch.object(AJ._er, 'estado', return_value={'estilo_novo': True, 'titulo': 'x'}), \
             patch.object(AJ, 'metricas', return_value={}), patch.object(AJ._er, '_salvar'), patch.object(AJ._er, 'pasta', return_value=self.root), patch.object(AJ, '_titulo', return_value='Meu novo'):
            info = AJ.referencia('abc')
        nn.assert_called_once()
        self.assertTrue(info['novo'])

    def test_pagina_do_estilo_lista_as_melhorias_dele_e_nao_as_dos_outros(self):
        self.criar_formato()
        pasta = self.root / 'melhorias'
        pasta.mkdir()
        base = {'tipo': 'motor', 'titulo': 'Melhoria no motor', 'formato_titulo': 'Doc Teste', 'criado_em': '2026-10-30T10:00:00', 'achados': [{'o_que': 'Legenda cortada na borda'}]}
        C.gravar_json(pasta / 'a1.json', {**base, 'id': 'a1', 'estado': 'proposta', 'formato': 'doc-teste'})
        C.gravar_json(pasta / 'a2.json', {**base, 'id': 'a2', 'estado': 'aplicada', 'formato': 'doc-teste'})
        C.gravar_json(pasta / 'b1.json', {**base, 'id': 'b1', 'estado': 'proposta', 'formato': 'outro', 'achados': [{'o_que': 'Só do outro'}]})
        with patch.object(M, 'pasta_melhorias', return_value=pasta):
            t = self.client.get('/formato/doc-teste').get_data(as_text=True)
        self.assertIn('Melhorias deste estilo', t)
        self.assertIn('Legenda cortada na borda', t)
        self.assertNotIn('Só do outro', t)
        self.assertIn('/melhoria/a1/aplicar', t)
        self.assertIn('/melhoria/a2/desfazer', t)
        self.assertNotIn('/melhoria/a2/aplicar', t)

    def test_card_de_referencia_usa_a_capa_e_nao_o_primeiro_quadro(self):
        import estilo_ref as ER
        vid = self.root / 'ref.mp4'
        vid.write_bytes(b'x')
        with patch.object(ER, 'listar', return_value=[{'id': 'r1', 'estado': 'pronto', 'nome_curto': 'ref', 'criado_em': '2026-10-30'}]), \
             patch.object(ER, 'video_de', return_value=vid), patch.object(ER, 'estilo_de', return_value={}):
            t = self.client.get('/referencias').get_data(as_text=True)
        self.assertIn('/thumb/', t)


if __name__ == '__main__':
    unittest.main()


class UmaContaSo(Base):
    """Início, selo do menu e /aprovar usam lotes.esperando(): o número é sempre o mesmo."""

    def feito_pelo_chat(self, slug, titulo, formato='editorial', horas=5):
        import andamento as A
        import datetime
        d = {'id': 'Joao/' + slug, 'cliente': 'Joao', 'slug': slug, 'titulo': titulo, 'formato': formato, 'estado': 'pronto', 'origem': 'chat',
             'video': 'x.mp4', 'atualizado': (datetime.datetime.now() - datetime.timedelta(hours=horas)).strftime('%Y-%m-%d %H:%M:%S')}
        return d

    def test_versoes_do_chat_viram_um_cartao_e_a_conta_bate(self):
        import lotes as L
        regs = [self.feito_pelo_chat('grupo', 'Grupo'), self.feito_pelo_chat('grupo-v2', 'Grupo (v2)'),
                self.feito_pelo_chat('grupo-v3', 'Grupo (v3)'), self.feito_pelo_chat('outro', 'Outro', 'analise-de-tela')]
        with patch.object(L.AND, 'listar', return_value=regs), patch.object(L, 'listar', return_value=[]):
            itens = L.esperando()
            chat = [i for i in itens if i.get('chat')]
            self.assertEqual(len(chat), 2)
            self.assertEqual(sorted(i['n_versoes'] for i in chat), [1, 3])
            self.assertEqual(L._expandir([('Joao', 'grupo-v2')]), [('Joao', 'grupo'), ('Joao', 'grupo-v2'), ('Joao', 'grupo-v3')])
            n = len(itens)
            t_inicio = self.client.get('/').get_data(as_text=True)
            t_aprovar = self.client.get('/aprovar').get_data(as_text=True)
        self.assertEqual(n, 2)
        self.assertIn('<b>2</b> coisas esperando você', t_inicio)
        self.assertIn('<span class="etiqueta destaque">2</span>', t_inicio)   # a seção do Início
        self.assertIn('<i class="s-badge">2</i>', t_aprovar)                  # o selo do menu
        self.assertIn('3 versões', t_aprovar)
        self.assertIn('feito pelo chat', t_aprovar)

    def test_tirar_antigos_so_esconde_o_do_chat_com_mais_de_3_dias(self):
        import lotes as L
        velho, novo = self.feito_pelo_chat('velho', 'Velho', horas=100), self.feito_pelo_chat('novo', 'Novo', horas=5)
        with patch.object(L.AND, 'listar', return_value=[velho, novo]), patch.object(L.AND, 'esconder', return_value=True) as esc:
            self.assertEqual(L.tirar_antigos_chat(3), 1)
        esc.assert_called_once_with('Joao', 'velho')
