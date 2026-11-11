"""A cópia do motor (cliente novo e sandbox de cada vídeo) não leva as músicas nem a demo/ da base do formato:
o render.py acha os dois na base. Antes cada vídeo copiava 154 MB de música."""
import subprocess
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
from test_esteira import Base
import edicao, formatos

P = fixtures.P


class CopiaSemMusicas(Base):
    def criar_base_com_audio(self):
        d = self.criar_formato(modelos=('doc-novo',), exemplo=False)
        b = d / 'base'
        for rel in ('audio/musicas/31.mp3', 'audio/sfx/pop.mp3', 'audio/catalogo.json', 'demo/pessoa.jpg',
                    'fontes/Tinos.ttf', 'cenas/demo/fica.jpg'):
            (b / rel).parent.mkdir(parents=True, exist_ok=True)
            (b / rel).write_text('x')
        return b

    def test_usar_nao_copia_musicas_nem_demo(self):
        b = self.criar_base_com_audio()
        self.assertEqual(formatos.usar('doc-teste', 'Teste'), ('Teste', 'doc-novo'))
        dst = self.content / 'modelos/doc-novo'
        self.assertFalse((dst / 'audio/musicas').exists())
        self.assertFalse((dst / 'demo').exists())
        for rel in ('audio/sfx/pop.mp3', 'audio/catalogo.json', 'fontes/Tinos.ttf', 'render.py', 'index.html',
                    'cenas/demo/fica.jpg'):   # só a demo/ da raiz fica na base; pasta "demo" mais funda é do motor
            self.assertTrue((dst / rel).is_file(), rel)
        self.assertTrue((b / 'audio/musicas/31.mp3').is_file())   # a base continua inteira

    def test_rsync_da_sandbox_exclui_musicas_e_demo(self):
        d = self.criar_formato()
        fixtures.C.gravar_json(d / 'base/audio/catalogo.json', {'musicas': []})   # sem o catálogo o pedido nem cita (formato novo)
        j = self.job_formato()
        edicao.aplicar(j, {'origem': 'misto', 'quantidade': 5})
        P.salvar(j)
        j = P.carregar('Teste', 'video')
        txt = P.prompt_esteira(j, 'ate_aprovacao')
        linha = next(l for l in txt.splitlines() if l.strip().startswith('rsync '))
        for ex in ("--exclude '_sandbox*'", "--exclude 'aprendizado/'", "--exclude '/audio/musicas/'", "--exclude '/demo/'"):
            self.assertIn(ex, linha)
        self.assertIn('formatos/doc-teste/base/audio/catalogo.json', txt)   # a música é procurada na base, não na sandbox
        self.assertNotIn('(na sandbox)', txt)
        # o comando roda de verdade: sfx e catálogo vão, músicas e demo/ não
        src, sb = self.root / 'motor', self.root / 'sb'
        for rel in ('audio/musicas/1.mp3', 'audio/sfx/pop.mp3', 'audio/catalogo.json', 'demo/p.jpg', 'render.py',
                    'aprendizado/regras.json', '_sandbox-x/a', 'cenas/demo/k'):
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_text('x')
        cmd = linha.strip().split(' "')[0]   # o rsync com os --exclude, sem as pastas de origem e destino
        subprocess.run(cmd + f' "{src}/" "{sb}/"', shell=True, check=True)
        copiados = sorted(p.relative_to(sb).as_posix() for p in sb.rglob('*') if p.is_file())
        self.assertEqual(copiados, ['audio/catalogo.json', 'audio/sfx/pop.mp3', 'cenas/demo/k', 'render.py'])


if __name__ == '__main__':
    unittest.main()
