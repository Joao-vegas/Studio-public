"""Regressões de fala preservada, páginas de modelo e cobertura visual."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ferramentas'))
import corte
import corte_qualidade as Q
import referencia_frames as R
from visual_modelo import esquema


def seg(i,texto,a,b,manter=True):
    return dict(i=i,texto=texto,t0=a,t1=b,manter=manter)


class Fala(unittest.TestCase):
    def test_frases_com_negacao_e_numero_nao_sao_takes_iguais(self):
        for a,b in [('Isso é importante para você','Isso não é importante para você'),
                    ('O valor é de 100 reais','O valor é de 200 reais'),
                    ('O prazo é sempre importante','O prazo é talvez importante')]:
            self.assertEqual(corte._fora_por_repeticao([seg(0,a,0,2),seg(1,b,3,5)]),{})

    def test_tentativa_incompleta_e_marcador_contextual(self):
        self.assertIn(0,corte._fora_por_repeticao([seg(0,'A sua ideia precisa',0,2),seg(1,'A sua ideia precisa fazer sentido.',3,6)]))
        self.assertFalse(corte._tem_marcador('Eu errei muito antes de aprender.'))
        self.assertFalse(corte._tem_marcador('Entre uma etapa e outra existe uma espera.'))
        self.assertTrue(corte._tem_marcador('Errei, vamos de novo.'))

    def test_palavra_curta_sobrevive_ao_aperto(self):
        words=[dict(t0=0,t1=.2,p='Não'),dict(t0=1.5,t1=2,p='desista.')]
        result=corte._apertar([dict(t0=0,t1=2.1)],words,[dict(t0=.2,t1=1.5)])
        self.assertGreater(len(result),1)
        for w in words:self.assertTrue(any(b['t0']<=w['t0'] and b['t1']>=w['t1'] for b in result))
        self.assertLess(sum(b['t1']-b['t0'] for b in result),1.3)

    def test_lacuna_da_transcricao_nao_autoriza_cortar_audio(self):
        block=[dict(t0=0,t1=3)]
        words=[dict(t0=0,t1=.2,p='A'),dict(t0=2,t1=3,p='fala')]
        self.assertEqual(corte._apertar(block,words,[]),block)

    def test_silencio_sobreposto_nao_corta_palavra_baixa(self):
        words=[dict(t0=.8,t1=1.2,p='não')]
        result=corte._apertar([dict(t0=0,t1=2)],words,[dict(t0=.1,t1=1.8)])
        self.assertTrue(any(b['t0']<=.8 and b['t1']>=1.2 for b in result))

    def test_palavra_excluida_nao_retorna_por_uniao(self):
        rows=[seg(0,'Isso',0,1),seg(1,'errei',1.05,1.15,False),seg(2,'Faz sentido.',1.2,2)]
        result=corte._blocos({'segmentos':rows},{'duracao_s':2},palavras=[dict(t0=s['t0'],t1=s['t1'],p=s['texto']) for s in rows])
        self.assertEqual(len(result),2)
        self.assertLess(result[0]['t1'],1.05);self.assertGreater(result[1]['t0'],1.15)

    def test_ia_nao_pode_inventar_texto_ou_borda(self):
        source=[seg(0,'Não desista.',0,1)]
        Q.validar({'segmentos':source},source)
        for change in ({'texto':'Desista.'},{'t0':.2},{'i':'0a'}):
            with self.assertRaises(ValueError):Q.validar({'segmentos':[{**source[0],**change}]},source)

    def test_revisao_invalida_restabelece_selecao(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=[seg(0,'Não desista.',0,1)]
            (p/'segmentos.json').write_text(json.dumps(source))
            original=json.dumps({'segmentos':source}).encode();(p/'CORTE.json').write_bytes(original)
            (p/'prompt.txt').write_text('Revisar sentido')
            def invalid(*args,**kwargs):
                (p/'CORTE.json').write_text(json.dumps({'segmentos':[{**source[0],'texto':'Desista.'}]}))
                return 0
            with patch('ia.executar',side_effect=invalid):self.assertEqual(corte.executar_revisao(p/'prompt.txt',p),1)
            self.assertEqual((p/'CORTE.json').read_bytes(),original)

    def test_roteiro_mostra_apenas_escolhas_e_ligacao(self):
        d={'segmentos':[seg(0,'Essa é a razão.',0,1,False),seg(1,'Por isso funciona.',2,3)]}
        result=Q.continuidade(d)
        self.assertEqual(result['roteiro'],'Por isso funciona.');self.assertTrue(result['alertas'])

    def test_corte_antigo_precisa_ser_renderizado_com_motor_novo(self):
        d={'segmentos':[seg(0,'Olá.',0,1)]}
        d['aplicado']={'assinatura':corte.assinatura(d)}
        self.assertTrue(corte.desatualizado(d,True))
        d['aplicado']['motor']=corte.VERSAO_MOTOR
        self.assertFalse(corte.desatualizado(d,True))

    def test_render_falho_preserva_video_anterior(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=[seg(0,'Olá.',0,1)]
            for name,data in [('segmentos.json',source),('CORTE.json',{'segmentos':source}),('medidas.json',{'duracao_s':1})]:
                (p/name).write_text(json.dumps(data))
            out=p/'cortado.mp4';out.write_bytes(b'ANTERIOR')
            with patch.object(corte.subprocess,'run',return_value=type('Result',(),{'returncode':1,'stderr':'falhou'})()):
                with self.assertRaises(RuntimeError):corte.aplicar(p/'bruto.mp4',p/'CORTE.json',out)
            self.assertEqual(out.read_bytes(),b'ANTERIOR')


class Visual(unittest.TestCase):
    def test_diagrama_dividido_respeita_tres_areas(self):
        f={'estrutura':['Topo (0–816px): pessoa','Meio (816–1086px): placa da legenda','Base (1086–1920px): cena','Sem música'],
           'paleta':[{'cor':'#0E7A45'}],'formato':{'resolucao':'1080x1920'}}
        result=esquema(f,'reel-dividido-por-video');zones=result['estados'][0]['zonas']
        self.assertEqual(len(zones),3);self.assertEqual(zones[0]['h'],42.5)
        self.assertEqual(zones[1]['cor'],'#0E7A45');self.assertAlmostEqual(sum(x['h'] for x in zones),100)

    def test_ficha_portada_com_formato_em_texto_nao_quebra(self):
        result=esquema({'estrutura':[],'formato':'dialogo-3d'},'dialogo-3d')
        self.assertTrue(result['estados'])

    def test_cobertura_visual_incompleta_e_rejeitada(self):
        sheets=[dict(n=1,primeiro=1,ultimo=24),dict(n=2,primeiro=25,ultimo=48)]
        report={'folhas':[dict(n=1,primeiro=1,ultimo=24,observacao='Cena estável',evidencias=[dict(frame=1,descricao='Rosto no topo')])]}
        with self.assertRaises(ValueError):R.validar_relatorio(report,sheets)
        report['folhas'].append(dict(n=2,primeiro=25,ultimo=48,observacao='Troca de cena',evidencias=[dict(frame=30,descricao='Texto entra')]))
        self.assertTrue(R.validar_relatorio(report,sheets))
        report['folhas'][1]['evidencias'][0]['frame']=12
        with self.assertRaises(ValueError):R.validar_relatorio(report,sheets)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'requer ffmpeg')
    def test_mosaicos_incluem_todos_os_frames_inclusive_repetidos(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);video=p/'referencia.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=green:size=180x320:rate=24:duration=2','-c:v','libx264',str(video)],check=True,capture_output=True)
            index=R.extrair(video,p/'estudo')
            self.assertEqual(index['total_frames'],48);self.assertEqual(index['total_folhas'],2)
            self.assertEqual([x['n'] for x in index['frames']],list(range(1,49)))
            self.assertAlmostEqual(index['frames'][-1]['segundo'],47/24,places=5)
            self.assertEqual(R.extrair(video,p/'estudo')['assinatura'],index['assinatura'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'requer ffmpeg')
    def test_referencia_sem_audio_prepara_evidencias_sem_transcricao(self):
        import estudo
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sb=root/'ref';sb.mkdir();video=sb/'referencia.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=180x320:rate=12:duration=1','-c:v','libx264',str(video)],check=True,capture_output=True)
            d={'slug':'teste','cliente':'Teste','sandbox':'ref'}
            with patch.object(estudo,'RAIZ',root),patch.object(estudo,'salvar'),patch.object(estudo.shutil,'which',return_value=None),patch.object(estudo,'transcrever') as transcribe:
                estudo.preparar(d)
            transcribe.assert_not_called()
            self.assertEqual(d['frames'],12);self.assertEqual(d['metodo'],'todos-os-frames')
            self.assertFalse(json.loads((sb/'estudo/audio.json').read_text())['tem_audio'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'requer ffmpeg')
    def test_render_real_encurta_pausa_preservando_audio_e_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);video=p/'bruto.mp4'
            signal=r'aevalsrc=if(between(t\,0\,0.25)+between(t\,1.5\,2.8)\,0.2*sin(2*PI*440*t)\,0):s=48000:d=3'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=180x320:rate=30:duration=3','-f','lavfi','-i',signal,'-c:v','libx264','-c:a','aac',str(video)],check=True,capture_output=True)
            source=[seg(0,'Não desista.',0,2.8)]
            words={'words':[dict(word='Não',start=0,end=.25),dict(word='desista.',start=1.5,end=2.8)]}
            for name,data in [('segmentos.json',source),('CORTE.json',{'segmentos':source}),('words.json',words)]:
                (p/name).write_text(json.dumps(data))
            corte.medir(video,p,source)
            corte.aplicar(video,p/'CORTE.json',p/'cortado.mp4')
            data=json.loads((p/'CORTE.json').read_text())
            info=json.loads(subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,duration','-of','json',str(p/'cortado.mp4')],capture_output=True,text=True,check=True).stdout)
            self.assertEqual({x['codec_type'] for x in info['streams']},{'video','audio'})
            self.assertLess(data['aplicado']['duracao_s'],2.2)
            durations=[float(x['duration']) for x in info['streams']]
            self.assertLess(max(durations)-min(durations),.08)

class EspacoMorto(unittest.TestCase):
    """O espaço morto vem do auto-editor; aqui só a leitura do mapa dele e a queda pra reserva."""

    def test_chunks_viram_silencio_em_segundos(self):
        # [frame0, frame1, velocidade] — 1.0 é fala, 99999 é o que o auto-editor cortaria.
        sil=corte.sil_de_chunks([[0,30,99999.0],[30,90,1.0],[90,99,99999.0],[99,180,1.0]],fps=30.0,minimo=.25)
        self.assertEqual(sil,[{'t0':0.0,'t1':1.0,'duracao':1.0},{'t0':3.0,'t1':3.3,'duracao':0.3}])

    def test_buraco_curto_e_lixo_no_mapa_nao_entram(self):
        self.assertEqual(corte.sil_de_chunks([[0,3,99999.0]],fps=30.0,minimo=.25),[])   # 0,1s
        self.assertEqual(corte.sil_de_chunks([[0,30,99999.0]],fps=0,minimo=.25),[])     # sem fps
        self.assertEqual(corte.sil_de_chunks([None,[],['x','y','z'],[0,30]],fps=30.0),[])

    def test_sem_auto_editor_instalado_cai_no_silencedetect(self):
        with patch.object(corte,'_auto_editor',return_value=None), \
             patch.object(corte,'_silencios_ffmpeg',return_value=[{'t0':1.0,'t1':2.0,'duracao':1.0}]) as reserva:
            self.assertEqual(corte.silencios(Path('nao-existe.mp4')),[{'t0':1.0,'t1':2.0,'duracao':1.0}])
        reserva.assert_called_once()


class RoteiroComoGabarito(unittest.TestCase):
    """Com o roteiro na mão o corte deixa de adivinhar: ele CONFERE o que foi falado contra o escrito."""

    def montar(self, falas):
        palavras, segs, t = [], [], 0.0
        for i, f in enumerate(falas):
            ws = []
            for p in f.split():
                ws.append({'t0': round(t, 2), 't1': round(t + .18, 2), 'p': p}); t += .2
            palavras += ws
            segs.append({'i': i, 't0': ws[0]['t0'], 't1': ws[-1]['t1'], 'texto': f, 'palavras': len(ws)})
            t = round(t + .6, 2)
        return palavras, segs

    def protegidos(self, falas, roteiro):
        """Roda a regra de repetição e devolve o que ainda cai DEPOIS da conferência com o roteiro."""
        palavras, segs = self.montar(falas)
        fora = corte._fora_por_repeticao(segs)
        conf = corte.conferir_roteiro(palavras, segs, roteiro)
        texto = {s['i']: s['texto'] for s in segs}
        if conf['confiavel']:
            for i, m in list(fora.items()):
                if ('refeit' in m or 'falso começo' in m) and corte.vezes_no_roteiro(texto[i], conf['tokens']) >= 2:
                    fora.pop(i)
        return fora, conf

    def test_anafora_do_roteiro_nao_e_take_refeito(self):
        # O medo do João: o roteiro repete de propósito e o corte come a fala boa.
        falas = ["Você não precisa de mais seguidor para vender todo dia",
                 "Você não precisa de mais tráfego para vender todo dia"]
        roteiro = ("Você não precisa de mais seguidor para vender todo dia. "
                   "Você não precisa de mais tráfego para vender todo dia. É disso que eu vim falar.")
        palavras, segs = self.montar(falas)
        self.assertTrue(corte._fora_por_repeticao(segs), 'sem roteiro a regra derruba — é esse o risco')
        fora, _ = self.protegidos(falas, roteiro)
        self.assertEqual(fora, {}, 'fala que o roteiro repete de propósito não pode cair')

    def test_take_refeito_continua_saindo_quando_o_roteiro_diz_uma_vez(self):
        falas = ["A maioria dos dentistas erra no preço",
                 "A maioria dos dentistas erra no preço da consulta inicial"]
        roteiro = "A maioria dos dentistas erra no preço da consulta inicial. E isso custa caro no fim do mês."
        fora, _ = self.protegidos(falas, roteiro)
        self.assertIn(0, fora, 'ele gravou duas vezes o que estava escrito uma: sai')

    def test_tropeco_fora_do_roteiro_fica_marcado(self):
        falas = ["A maioria dos dentistas erra no preço da consulta",
                 "é peraí deixa eu ver aqui ó",
                 "E isso custa caro no fim do mês"]
        roteiro = "A maioria dos dentistas erra no preço da consulta. E isso custa caro no fim do mês."
        palavras, segs = self.montar(falas)
        conf = corte.conferir_roteiro(palavras, segs, roteiro)
        self.assertTrue(conf['confiavel'])
        self.assertLessEqual(conf['por_segmento'][1], corte.FORA_ROTEIRO)
        self.assertGreater(conf['por_segmento'][0], corte.FORA_ROTEIRO)
        self.assertGreater(conf['por_segmento'][2], corte.FORA_ROTEIRO)

    def test_roteiro_errado_nao_manda_em_nada(self):
        falas = ["A maioria dos dentistas erra no preço da consulta", "E isso custa caro no fim do mês"]
        palavras, segs = self.montar(falas)
        conf = corte.conferir_roteiro(palavras, segs,
                                      "Hoje eu vou ensinar a plantar tomate na varanda com terra adubada e sol")
        self.assertFalse(conf['confiavel'], 'roteiro de outro vídeo não pode cortar nada')

    def test_sem_roteiro_o_corte_segue_como_era(self):
        palavras, segs = self.montar(["A maioria dos dentistas erra no preço da consulta"])
        conf = corte.conferir_roteiro(palavras, segs, '')
        self.assertFalse(conf['confiavel']);self.assertEqual(conf['por_segmento'], {})

    def test_roteiro_guardado_na_work_e_relido(self):
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            self.assertEqual(corte.ler_roteiro(w), '')
            corte.ler_roteiro(w, '  Primeiro você olha as duas coisas.  ')
            self.assertEqual(corte.ler_roteiro(w), 'Primeiro você olha as duas coisas.')
            arq = w / 'r.txt'; arq.write_text('Veio de arquivo.')
            self.assertEqual(corte.ler_roteiro(w, str(arq)), 'Veio de arquivo.')


class GaguejoPorPalavra(unittest.TestCase):
    """O tropeço DENTRO do trecho — o que a regra de segmento é cega pra ver."""

    def palavras(self, texto, t0=0.0, passo=.22):
        ws, t = [], t0
        for p in texto.split():
            ws.append({'t0': round(t, 2), 't1': round(t + passo - .04, 2), 'p': p}); t += passo
        return ws, round(t, 2)

    def fala(self, *pedacos):
        """(texto, pausa_depois) → lista de palavras cronometradas."""
        ws, t = [], 0.0
        for texto, pausa in pedacos:
            novo, t = self.palavras(texto, t)
            ws += novo; t = round(t + pausa, 2)
        return ws

    def saiu(self, gag):
        return [g['texto'] for g in gag]

    def test_recomeca_na_mesma_respirada(self):
        # "ele fala três palavras, erra e volta a repetir"
        ws = self.fala(("Com um profissional", .3), ("com um profissional indicado pela Justiça", 0))
        gag = corte.gaguejos(ws)
        self.assertEqual(len(gag), 1)
        self.assertEqual(self.saiu(gag)[0], 'Com um profissional')

    def test_palavra_cortada_no_meio_sai(self):
        ws = self.fala(("exames histórico de afas--", .4), ("histórico de afastamento", 0))
        gag = corte.gaguejos(ws)
        self.assertTrue(gag, 'palavra truncada tem que sair')
        self.assertIn('afas--', ' '.join(self.saiu(gag)))

    def test_take_refeito_meio_minuto_depois(self):
        # "embala numa frase só e erra no final, aí tem que voltar"
        ws = self.fala(("Achar que parou quando está", 9.0),
                       ("Achar que parou quando o processo continua tramitando", 0))
        gag = corte.gaguejos(ws)
        self.assertTrue(gag, 'a janela curta não alcança; a larga tem que pegar')
        self.assertIn('Achar que parou quando está', ' '.join(self.saiu(gag)))

    def test_anafora_do_roteiro_sobrevive_a_janela_larga(self):
        # 🔴 o medo do João: o roteiro repete de propósito e o corte come a fala boa
        texto = "Você não precisa de mais seguidor para vender todo dia"
        ws = self.fala((texto, .5), ("Você não precisa de mais tráfego para vender todo dia", 0))
        roteiro = texto + ". Você não precisa de mais tráfego para vender todo dia. É disso que eu vim falar hoje."
        self.assertTrue(corte.gaguejos(ws), 'sem roteiro a janela larga derruba — é o risco')
        self.assertEqual(corte.gaguejos(ws, roteiro), [], 'com roteiro, a anáfora fica')

    def test_expressao_comum_nao_vira_take_refeito(self):
        # 🔴 "cê vai ter que contar…" no começo e "cê vai ter que entender…" no fim comeram 62s de fala boa
        meio = ("e eu falo com vários empresários que estão há dez anos no mercado com o mesmo faturamento "
                "só que o preço de tudo sobe e eles ganham cada vez menos fazendo a mesma rotina de sempre "
                "porque não entra na cabeça que repetir o comportamento não bate o teto que eles querem")
        ws = self.fala(("cê vai ter que contar com o ovo que não saiu da galinha e dar um passo maior do que a sua perna", .5),
                       (meio, .5),
                       ("então cê vai ter que entender que você vai ter que estar em movimentação", 0))
        self.assertEqual(corte.gaguejos(ws), [])

    def test_fala_limpa_nao_perde_nada(self):
        ws = self.fala(("A maioria dos dentistas erra no preço da consulta inicial", .5),
                       ("E isso custa caro no fim do mês", 0))
        self.assertEqual(corte.gaguejos(ws), [])

    def test_tirar_parte_o_bloco_no_meio(self):
        blocos = [{'t0': 0.0, 't1': 10.0}]
        fora = corte._tirar(blocos, [{'t0': 4.0, 't1': 6.0}])
        self.assertEqual(len(fora), 2)
        self.assertAlmostEqual(fora[0]['t1'], 3.97, places=2)
        self.assertAlmostEqual(fora[1]['t0'], 6.03, places=2)


if __name__=='__main__':unittest.main()
