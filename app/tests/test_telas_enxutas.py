"""Telas enxutas: o essencial à vista (o que é, o vídeo, o botão, o próximo passo) e o resto numa linha clicável.
Sem termo técnico na tela (sandbox, historico.jsonl, beats). Fixtures temporárias: nada pago, nada de rede."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_esteira import Base, C, P
from test_andamento_resposta import Base as BaseAndamento
import andamento as A


class FormatoEJob(Base):
    def test_pagina_do_formato_recolhe_aprendizado_custo_e_referencias(self):
        d = self.criar_formato()
        C.gravar_json(d / 'aprendizado/regras.json', {'regras': [{'id': 'cena-curta', 'titulo': 'Cena até 2,5 s',
                                                                  'texto': 'Cada cena no cenas.json dura até 2,5 s.'}]})
        t = self.client.get('/formato/doc-teste').get_data(as_text=True)
        self.assertIn('Usar este estilo', t)
        self.assertIn('<summary>O que já aprendemos (1) ', t)
        self.assertIn('<summary>Quanto custa</summary>', t)
        self.assertIn('id="estudos"', t)
        self.assertIn('+ Juntar uma referência a este estilo', t)
        # no Criar, a regra aparece pelo título (curto), não pelo texto cru
        self.assertEqual(self.client.get('/api/formato/doc-teste').get_json()['regras_formato'], ['Cena até 2,5 s'])

    def test_pagina_do_formato_com_regras_so_em_markdown_nao_quebra(self):
        d = self.criar_formato()
        (d / 'aprendizado/regras.md').write_text('| ID | Regra |\n|---|---|\n| G1 | Cena curta. |\n', encoding='utf-8')
        r = self.client.get('/formato/doc-teste')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Cena curta', r.get_data(as_text=True))

    def test_pagina_do_formato_um_exemplo_so_e_aprendemos_no_fim(self):
        d = self.criar_formato()
        P_ = Path(d)
        for n, quando in ((2, '2026-10-08'), (3, '2026-10-10')):
            (P_ / f'exemplo-{n}.mp4').write_bytes((P_ / 'exemplo-1.mp4').read_bytes())
        dados = C.ler_json(d / 'formato.json')
        dados['exemplos'] += [{'arquivo': 'exemplo-2.mp4', 'legenda': 'Antigo B', 'origem': 'b.mp4', 'principal_desde': '2026-10-08'},
                              {'arquivo': 'exemplo-3.mp4', 'legenda': 'Aprovado recente', 'origem': 'c.mp4', 'principal_desde': '2026-10-10'}]
        C.gravar_json(d / 'formato.json', dados)
        C.gravar_json(d / 'aprendizado/regras.json', {'regras': [
            {'id': 'a', 'titulo': 'Cena curta', 'categoria': 'layout', 'texto': 'Cena até 2,5 s. ' * 20},
            {'id': 'b', 'titulo': 'Voz calma', 'categoria': 'audio', 'texto': 'Voz sem grito.'}]})
        t = self.client.get('/formato/doc-teste').get_data(as_text=True)
        self.assertIn('src="/arquivo/formatos/doc-teste/exemplo-3.mp4"', t.split('id="player"')[1].split('>')[0] + '"')
        self.assertIn('id="legenda-exemplo" style="margin-top:10px;font-size:13px">Aprovado recente</p>', t)   # só um à vista
        self.assertEqual(t.count('id="player"'), 1)
        self.assertIn('<summary>Ver outros exemplos (2)</summary>', t)
        self.assertLess(t.index('Como funciona'), t.index('id="estudos"'))
        self.assertLess(t.index('id="estudos"'), t.index('Juntar uma referência'))
        self.assertLess(t.index('Juntar uma referência'), t.index('id="aprendemos"'))   # regras por último
        self.assertLess(t.index('Quanto custa'), t.index('id="aprendemos"'))
        self.assertIn('<h4>Imagem e cenas', t)
        self.assertIn('<h4>Voz e música', t)
        self.assertIn('…</small>', t)                                                    # a linha curta é cortada
        self.assertEqual(sorted(p.name for p in P_.glob('exemplo-*.mp4')), ['exemplo-1.mp4', 'exemplo-2.mp4', 'exemplo-3.mp4'])

    def test_pagina_do_formato_com_um_exemplo_nao_tem_ver_outros(self):
        self.criar_formato()
        t = self.client.get('/formato/doc-teste').get_data(as_text=True)
        self.assertNotIn('Ver outros exemplos', t)

    def test_pagina_do_video_sem_termo_tecnico_e_com_ficou_bom(self):
        self.criar_formato()
        j = self.job_formato('concluido')
        j['corte_aplicado'] = {'segmentos_mantidos': 3, 'segmentos_total': 4, 'duracao_s': 61.5, 'em': '2026-10-09',
                               'arquivo': j['bruto']}
        P.salvar(j)
        t = self.client.get('/job/Teste/video').get_data(as_text=True)
        self.assertIn('<details class="painel recolhido" id="bruto"><summary>✔ Corte do bruto aprovado', t)
        self.assertIn('3 de 4 trechos · 1:01', t)
        self.assertIn('<h2>Ficou bom?</h2>', t)
        self.assertIn('ETAPAS DO VÍDEO', t)
        self.assertIn('Pasta de trabalho:', t)
        visivel = t.split('execution-details')[0]                  # "Detalhes técnicos" (log e prompt) fica recolhido
        for tecnico in ('Sandbox:', 'historico.jsonl', 'regras.json', 'RESULTADO.md', 'a sandbox', 'beat b3', '>beats<', '>broll<'):
            self.assertFalse(tecnico in visivel, tecnico)
        self.assertIn('<option value="broll">Cenas de apoio</option>', t)   # o valor gravado não muda


class AndamentoEnxuto(BaseAndamento):
    def setUp(self):
        super().setUp()
        import servidor
        self.c = servidor.app.test_client()

    def test_passos_antigos_e_respostas_ficam_recolhidos(self):
        A.passo('Joao', 'ep', 'Lendo as regras', formato='dialogo-3d', titulo='Ep')
        for i in range(8):
            A.passo('Joao', 'ep', f'Passo {i}')
        A.espera('Joao', 'ep', 'Storyboard pronto')
        n = len(A.carregar('Joao', 'ep')['passos'])
        html = self.c.get('/andamento/Joao/ep').get_data(as_text=True)
        self.assertIn(f'Ver os {n - 6} passos anteriores', html)
        self.assertIn('O storyboard ficou bom?', html)            # a caixa "Ficou bom?" continua no topo
        A.responder('Joao', 'ep', 'ajustar', 'legenda menor')
        html = self.c.get('/andamento/Joao/ep').get_data(as_text=True)
        self.assertIn('<summary>Respostas dadas (1)</summary>', html)


if __name__ == '__main__':
    unittest.main()
