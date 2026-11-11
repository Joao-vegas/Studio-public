"""Um .env só (app/.env): ordem cliente > app > ambiente, nada vai pro os.environ, nenhuma saída mostra valor,
sincronizar e limpar-clientes não apagam linha alheia. Tudo em pasta temporária: os .env reais nem são abertos."""
import io
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

AQUI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(AQUI / 'ferramentas'), str(AQUI / 'interface')]
import _comum
import chaves
import corte
import fala
import ia
import novo_cliente

APP = 'groq-do-app-que-nunca-aparece-AA11'
CLI = 'groq-do-cliente-que-nunca-aparece-BB22'
AMB = 'groq-do-ambiente-que-nunca-aparece-CC33'
PEX = 'pexels-do-app-que-nunca-aparece-DD44'
KIE = 'kie-do-app-que-nunca-aparece-EE55'
OPENAI = 'sk-openai-que-nunca-aparece-FF66'
VALORES = (APP, CLI, AMB, PEX, KIE, OPENAI)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = t = Path(self.tmp.name)
        for d in ('app', 'clientes/Joao', 'clientes/Novo', 'gb', 'gerador'): (t / d).mkdir(parents=True)
        self.app_env = t / 'app/.env'
        self.app_env.write_text(f'# comentario\nGROQ_API_KEY={APP}\nPEXELS_API_KEY="{PEX}"\nKIE_API_KEY={KIE}\nOPENAI_API_KEY={OPENAI}\n')
        os.chmod(self.app_env, 0o600)
        (t / 'clientes/Joao/.env').write_text(f'GROQ_API_KEY={CLI}\nOPENAI_API_KEY={OPENAI}\nOUTRA=fica\n')
        self.gb, self.ger = t / 'gb/.env', t / 'gerador/.env'
        self.gb.write_text('# minha nota\nPEXELS_API_KEY=velha\nGB_PROJECT=meu-projeto\n')
        self.ger.write_text(f'KIE_API_KEY={KIE}\nOUTRO_DO_GERADOR=x\n')
        self.patches = [patch.object(chaves, 'RAIZ', t), patch.object(chaves, 'APP_ENV', self.app_env),
                        patch.object(chaves, 'GB_ENV', self.gb), patch.object(chaves, 'GERADOR_ENV', self.ger),
                        patch.object(chaves, 'BACKUPS', t / 'backups'),
                        patch.dict(os.environ, {'GROQ_API_KEY': AMB, 'SO_NO_AMBIENTE': AMB})]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def saida(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf): chaves.main(list(argv))
        return buf.getvalue()

    def sem_valor(self, texto):
        for v in VALORES: self.assertNotIn(v, texto)


class Ordem(Base):
    def test_cliente_depois_app_depois_ambiente(self):
        self.assertEqual(chaves.chave('GROQ_API_KEY', 'Joao'), CLI)
        self.assertEqual(chaves.chave('GROQ_API_KEY', 'Novo'), APP)        # cliente sem .env
        self.assertEqual(chaves.chave('GROQ_API_KEY'), APP)
        self.assertEqual(chaves.chave('GROQ_API_KEY', self.t / 'clientes/Joao'), CLI)   # aceita a pasta
        self.assertEqual(chaves.chave('PEXELS_API_KEY'), PEX)              # aspas saem
        self.app_env.write_text('GROQ_API_KEY=\n')
        self.assertEqual(chaves.chave('GROQ_API_KEY', 'Novo'), AMB)        # vazia no app não esconde o ambiente
        self.assertEqual(chaves.chave('NAO_EXISTE'), '')

    def test_quem_le_usa_a_mesma_ordem(self):
        with patch.object(corte, 'RAIZ', self.t), patch.object(fala, 'RAIZ', self.t):
            self.assertEqual(corte.chave_groq('Joao'), CLI)
            self.assertEqual(corte.chave_groq('Novo'), APP)

    def test_nada_vai_pro_os_environ(self):
        antes = dict(os.environ)
        chaves.chave('OPENAI_API_KEY', 'Joao'); chaves.mostrar('KIE_API_KEY'); chaves.listar(); chaves.ler_env(self.app_env)
        self.assertEqual(dict(os.environ), antes)
        self.assertNotIn(OPENAI, os.environ.values())

    def test_catalogo_le_do_app_env_sem_ambiente(self):
        visto = {}
        def abrir(req, timeout=0):
            visto['auth'] = req.headers.get('Authorization')
            return io.BytesIO(b'{"data": [{"id": "gpt-teste"}]}')
        with patch.object(chaves, 'ler', return_value=''), patch('urllib.request.urlopen', abrir), \
                patch.object(ia, 'gravar_json'), patch.object(ia, 'catalogo', return_value=[]):
            ia.atualizar_catalogo()
        self.assertEqual(visto['auth'], 'Bearer ' + OPENAI)
        self.assertNotIn('OPENAI_API_KEY', os.environ)


class SemValor(Base):
    def test_mostrar_so_nome_onde_e_hash(self):
        m = chaves.mostrar('GROQ_API_KEY', 'Joao')
        self.assertEqual((m['onde'], m['configurada'], len(m['hash'])), ('clientes/Joao/.env', True, 8))
        self.assertEqual(chaves.mostrar('SO_NO_AMBIENTE')['onde'], 'ambiente')
        self.sem_valor(repr([m, chaves.mostrar('SO_NO_AMBIENTE'), chaves.mostrar('KIE_API_KEY')]))

    def test_nenhuma_saida_do_terminal_tem_valor(self):
        txt = ''.join(self.saida(*a) for a in (['listar'], ['sincronizar'], ['limpar-clientes'], ['juntar']))
        self.sem_valor(txt)
        self.assertIn('GROQ_API_KEY', txt)
        self.assertIn(chaves._hash(APP), txt)


class Juntar(Base):
    def test_traz_o_que_falta_mantendo_linhas_e_permissao(self):
        self.app_env.write_text('# comentario\nGEMINI_API_KEY_7=g7\n'); os.chmod(self.app_env, 0o600)
        (self.t / 'clientes/Avulso').mkdir()
        (self.t / 'clientes/Avulso/.env').write_text(f'GROQ_API_KEY={CLI}\nOPENAI_API_KEY={OPENAI}\n')
        (self.t / 'clientes/Joao/.env').write_text(f'GROQ_API_KEY={CLI}\nOPENAI_API_KEY=outra-conta\n')
        self.gb.write_text(f'PEXELS_API_KEY={PEX}\n')
        r = chaves.juntar()
        self.assertEqual(r['GROQ_API_KEY'], 'adicionada')
        self.assertIn('diferentes', r['OPENAI_API_KEY'])                     # cópias com hash diferente: não traz
        self.assertEqual(r['PIXABAY_API_KEY'], 'não achei de onde trazer')
        linhas = self.app_env.read_text().splitlines()
        self.assertEqual(linhas[:2], ['# comentario', 'GEMINI_API_KEY_7=g7'])
        self.assertEqual(chaves.ler_env(self.app_env), {'GEMINI_API_KEY_7': 'g7', 'GROQ_API_KEY': CLI, 'PEXELS_API_KEY': PEX})
        self.assertEqual(stat.S_IMODE(self.app_env.stat().st_mode), 0o600)
        self.assertEqual(chaves.juntar()['GROQ_API_KEY'], 'já estava')


class Sincronizar(Base):
    def test_so_troca_o_que_mudou_e_mantem_o_resto(self):
        os.chmod(self.gb, 0o640)
        antes_ger = self.ger.stat().st_mtime_ns
        r = {(Path(a).parent.name, n): e for a, n, e in chaves.sincronizar()}
        self.assertEqual(r[('gb', 'PEXELS_API_KEY')], 'atualizada')
        self.assertEqual(r[('gb', 'PIXABAY_API_KEY')], 'falta no app/.env')
        self.assertEqual(r[('gerador', 'KIE_API_KEY')], 'igual')
        self.assertEqual(self.gb.read_text(), f'# minha nota\nPEXELS_API_KEY={PEX}\nGB_PROJECT=meu-projeto\n')
        self.assertEqual(stat.S_IMODE(self.gb.stat().st_mode), 0o640)
        self.assertEqual(self.ger.stat().st_mtime_ns, antes_ger)              # igual: nem regrava
        self.assertEqual(self.ger.read_text(), f'KIE_API_KEY={KIE}\nOUTRO_DO_GERADOR=x\n')

    def test_skill_nao_instalada_nao_cria_pasta(self):
        with patch.object(chaves, 'GERADOR_ENV', self.t / 'sumiu/.env'):
            r = chaves.sincronizar()
        self.assertIn('skill não instalada', [e for _, n, e in r if n == 'KIE_API_KEY'])
        self.assertFalse((self.t / 'sumiu').exists())

    def test_tela_do_broll_grava_no_app_env_e_copia_pra_skill(self):
        with patch.object(_comum, 'ESTUDIO', self.t / 'app'), patch.object(_comum, 'GB_ENV', self.gb):
            _comum.gb_env_gravar({'PIXABAY_API_KEY': 'pix-nova-12345'})
            self.assertEqual(_comum.gb_env()['PEXELS_API_KEY'], PEX)          # app/.env ganha da skill
        self.assertEqual(chaves.ler_env(self.app_env)['PIXABAY_API_KEY'], 'pix-nova-12345')
        self.assertEqual(chaves.ler_env(self.gb)['PIXABAY_API_KEY'], 'pix-nova-12345')
        self.assertEqual(chaves.ler_env(self.gb)['GB_PROJECT'], 'meu-projeto')


class LimparClientes(Base):
    def test_sem_sim_so_lista(self):
        antes = (self.t / 'clientes/Joao/.env').read_text()
        r = chaves.limpar_clientes()
        self.assertEqual(r, [{'cliente': 'Joao', 'repetidas': ['OPENAI_API_KEY'], 'removidas': False}])   # GROQ é diferente: fica
        self.assertEqual((self.t / 'clientes/Joao/.env').read_text(), antes)
        self.assertFalse((self.t / 'backups').exists())

    def test_com_sim_faz_backup_e_tira_so_a_repetida(self):
        env = self.t / 'clientes/Joao/.env'
        antes = env.read_text()
        chaves.limpar_clientes(sim=True)
        self.assertEqual(env.read_text(), f'GROQ_API_KEY={CLI}\nOUTRA=fica\n')
        (copia,) = (self.t / 'backups').glob('limpar-clientes-*/Joao.env')
        self.assertEqual(copia.read_text(), antes)
        self.assertEqual(stat.S_IMODE(copia.stat().st_mode), 0o600)


class NovoCliente(Base):
    def test_cliente_novo_nao_ganha_env(self):
        with patch.object(novo_cliente, 'RAIZ', self.t), patch.object(novo_cliente, '_cliente', return_value={'nome': 'Carla'}):
            novo_cliente.criar('Carla', env_de='Joao')
        self.assertTrue((self.t / 'clientes/Carla').is_dir())
        self.assertFalse((self.t / 'clientes/Carla/.env').exists())
        self.assertEqual(chaves.chave('GROQ_API_KEY', 'Carla'), APP)


if __name__ == '__main__':
    unittest.main()
