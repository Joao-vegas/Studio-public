"""Formato novo do zero, sem IA (formatos/CONTRATO.md): novo --motor|--gravado → referencia → pronto.

A classe DoZero cria UM formato de teste no catálogo de verdade (formatos/zz-teste-do-zero-*) e apaga no fim, mesmo se
falhar: o formato nasce passando no validar, aparece na página e no Criar como receita, o motor genérico faz
storyboard/quadro/vídeo/conferência e o ESTUDO.md em branco vira o resumo que os vídeos leem. Nada pago."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures   # noqa: F401  (põe app/ferramentas no caminho)
import formatos
from test_esteira import Base, video
from _comum import com_venv, rodar_com_limite

C = fixtures.C
REAL = formatos.FORMATOS
try:
    import playwright  # noqa: F401
    TEM_PLAYWRIGHT = True
except ImportError:
    TEM_PLAYWRIGHT = False


def cli(*args) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = formatos.main(list(args))
    return code, out.getvalue() + err.getvalue()


class DoZero(unittest.TestCase):
    """Cria e apaga um formato de teste no catálogo real."""

    def setUp(self):
        self.assertEqual(formatos.FORMATOS, REAL)
        self.slug = f"zz-teste-do-zero-{os.getpid()}"
        self.d = REAL / self.slug
        self.addCleanup(shutil.rmtree, self.d, True)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def motor(self, *args) -> subprocess.CompletedProcess:
        return rodar_com_limite([sys.executable, "render.py", "--cenas", "cenas-modelo.json", "--out", str(self.tmp), *args], 180,
                                cwd=self.d / "base", capture_output=True, text=True, env=com_venv())

    def test_formato_do_zero_de_ponta_a_ponta(self):
        # 1. novo --motor: nasce do _modelo, receita, esteira declarada, passando no validar
        code, txt = cli("novo", self.slug, "--motor", "--titulo", "Teste do zero")
        self.assertEqual(code, 0, txt)
        self.assertIn("validar sem falta", txt)
        self.assertIn(f"formatos.py referencia {self.slug}", txt)
        self.assertEqual(formatos.validar(self.slug), [])
        dados = C.ler_json(self.d / "formato.json")
        self.assertEqual((dados["tipo"], dados["status"], dados["base"]), ("motor", "receita", f"formatos/{self.slug}/base"))
        self.assertTrue(dados["esteira"]["etapas"])
        for arq in ("render.py", "index.html", "README.md", "cenas-modelo.json"):
            self.assertTrue((self.d / "base" / arq).is_file(), arq)
        self.assertIn(f'FORMATO = "{self.slug}"', (self.d / "base/render.py").read_text(encoding="utf-8"))
        self.assertEqual(cli("novo", self.slug, "--motor")[0], 1)   # repetido recusa

        # 2. a página e o Criar enxergam sozinhos, como receita (ainda não roda pela tela)
        f = next(x for x in formatos.listar() if x["slug"] == self.slug)
        self.assertEqual((f["status"], f["na_tela"], f["estudo"]), ("receita", False, ""))
        import servidor
        c = servidor.app.test_client()
        r = c.get(f"/formato/{self.slug}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Teste do zero", r.get_data(as_text=True))
        self.assertIn(f'data-formato="{self.slug}"', c.get("/criar").get_data(as_text=True))

        # 3. referencia: exemplo principal com folha marcada no tempo + ESTUDO.md em branco
        ref = video(self.tmp / "ref.mp4", dur=5)
        code, txt = cli("referencia", self.slug, str(ref))
        self.assertEqual(code, 0, txt)
        self.assertIn("exemplo principal", txt)
        for arq in ("exemplo-1.mp4", "exemplo-1.jpg", "exemplo-1-folha.jpg", "ESTUDO.md"):
            self.assertTrue((self.d / arq).is_file(), arq)
        ex = C.ler_json(self.d / "formato.json")["exemplos"][0]
        self.assertEqual((ex["arquivo"], ex["folha"], ex["legenda"]), ("exemplo-1.mp4", "exemplo-1-folha.jpg", "Referência"))
        estudo = (self.d / "ESTUDO.md").read_text(encoding="utf-8")
        for tema in ("## Ritmo", "## Legenda", "## Enquadramento", "## Som", "Medido sozinho (ffmpeg)", "exemplo-1-folha.jpg"):
            self.assertIn(tema, estudo)
        self.assertEqual(formatos.estudo_estado(self.slug), "branco")
        self.assertIn("responda UMA vez", formatos.estudo_txt(self.slug))
        self.assertEqual(formatos.validar(self.slug), [])   # receita pode estar em branco
        self.assertIn("ESTUDO.md", c.get(f"/formato/{self.slug}").get_data(as_text=True))
        # 2ª referência não troca o principal nem o ESTUDO.md
        self.assertEqual(cli("referencia", self.slug, str(video(self.tmp / "ref2.mp4")), "--legenda", "Outra")[0], 0)
        exs = C.ler_json(self.d / "formato.json")["exemplos"]
        self.assertEqual([e["arquivo"] for e in exs], ["exemplo-1.mp4", "exemplo-2.mp4"])
        self.assertEqual((self.d / "ESTUDO.md").read_text(encoding="utf-8"), estudo)
        self.assertEqual(cli("referencia", self.slug, str(self.tmp / "nao-tem.mp4"))[0], 1)

        # 4. o motor genérico já funciona: storyboard, quadro, vídeo curto e conferência contra o exemplo
        if TEM_PLAYWRIGHT:
            r = self.motor("--storyboard")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((self.tmp / "storyboard.jpg").is_file())
            self.assertTrue(C.ler_json(self.tmp / "qa/checagem.json")["ok"])
            self.assertEqual(self.motor("--quadro", "cenas").returncode, 0)
            self.assertEqual(len(list((self.tmp / "quadros").glob("*.png"))), 3)
            r = self.motor("--ate", "1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = self.motor("--conferir", "--video", str(self.tmp / "teste.mp4"))
            self.assertEqual(r.returncode, 1)   # 1 s de 6: reprova com o motivo
            self.assertIn("as cenas somam 6,0 s", r.stdout)
            self.assertTrue((self.tmp / "qa/folha-comparacao.jpg").is_file())

        # 5. pronto só com o estudo respondido e sem TROQUE:
        faltas = formatos.marcar_pronto(self.slug)
        self.assertTrue(any("ESTUDO.md" in x for x in faltas))
        self.assertTrue(any(formatos.MARCA_MODELO in x for x in faltas))
        self.assertEqual(C.ler_json(self.d / "formato.json")["status"], "receita")
        (self.d / "ESTUDO.md").write_text(estudo.replace("  R:", "  R: cena de 2 s, corte seco", 1), encoding="utf-8")
        self.assertEqual(formatos.estudo_estado(self.slug), "feito")
        self.assertIn("não reestude", formatos.estudo_txt(self.slug).lower())
        for p in (self.d / "formato.json", self.d / "COMO-FAZER.md", self.d / "base/index.html", self.d / "base/README.md"):
            p.write_text(p.read_text(encoding="utf-8").replace(formatos.MARCA_MODELO, "Feito:"), encoding="utf-8")
        code, txt = cli("pronto", self.slug)
        self.assertEqual(code, 0, txt)
        f = formatos.carregar(self.slug)
        self.assertEqual((f["status"], f["na_tela"], f["estudo"]), ("pronto", True, "feito"))


class Isolado(Base):
    """Formatos temporários (nada no catálogo real)."""

    def setUp(self):
        super().setUp()
        shutil.copytree(REAL / "_modelo", self.formatos / "_modelo", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "app/ferramentas").mkdir(parents=True, exist_ok=True)
        (self.root / "app/ferramentas/storyboard.py").write_text("print('storyboard')"); (self.root / "app/ferramentas/conferir_video.py").write_text("print('conferir')")

    def test_gravado_tira_modelo_e_render_da_base(self):
        (self.mod / "gerar.sh").write_text("#!/bin/zsh\n# uso: gerar.sh --dir <pasta>\n")
        code, txt = cli("novo", "meu-gravado", "--gravado", "--base", "clientes/Teste/testeContent/modelos/estilo")
        self.assertEqual(code, 0, txt)
        dados = C.ler_json(self.formatos / "meu-gravado/formato.json")
        self.assertEqual((dados["tipo"], dados["modelos"]), ("gravado", ["estilo"]))
        self.assertEqual(dados["esteira"]["comandos"]["render"], "zsh ../gerar.sh --dir .")
        self.assertFalse((self.formatos / "meu-gravado/base").exists())
        self.assertEqual(formatos.validar("meu-gravado"), [])

    def test_gravado_sem_base_recusa(self):
        code, txt = cli("novo", "sem-base", "--gravado")
        self.assertEqual(code, 1)
        self.assertIn("--base", txt)
        self.assertFalse((self.formatos / "sem-base").exists())

    def test_pronto_sem_exemplo_fica_receita(self):
        formatos.novo_formato("sem-exemplo")
        d = self.formatos / "sem-exemplo"
        for p in (d / "formato.json", d / "COMO-FAZER.md", *(d / "base").iterdir()):
            p.write_text(p.read_text(encoding="utf-8").replace(formatos.MARCA_MODELO, "Feito:"), encoding="utf-8")
        faltas = formatos.marcar_pronto("sem-exemplo")
        self.assertTrue(any("sem exemplo" in x for x in faltas), faltas)
        self.assertEqual(C.ler_json(d / "formato.json")["status"], "receita")
        dados = C.ler_json(d / "formato.json")
        C.gravar_json(d / "formato.json", {**dados, "oculto": True})   # oculto pode esperar o exemplo
        self.assertEqual(formatos.marcar_pronto("sem-exemplo"), [])

    def test_pedido_a_ia_le_o_estudo_em_vez_de_reestudar(self):
        import producao as P
        self.criar_formato(modelos=("doc-teste",))
        (self.formatos / "doc-teste/ESTUDO.md").write_text("# Estudo\n\n## Ritmo\n- Quanto dura?\n  R: 2 s por cena\n")
        txt = P.camadas_de_regra(self.job_formato())
        self.assertIn("formatos/doc-teste/ESTUDO.md", txt)
        self.assertIn("não reestude", txt.lower())


if __name__ == "__main__":
    unittest.main()
