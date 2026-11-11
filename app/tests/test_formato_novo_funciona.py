"""Formato novo funciona de verdade, do zero até o pedido à IA (rodada-3, FUNCIONAR.md). Tudo isolado, nada pago.

Cada teste cobre um defeito achado no teste ponta a ponta:
- o gravado novo pegava o nome do modelo da base, que já era de outro formato (o vídeo antigo caía no formato errado);
- sem --titulo, a tela Criar mostrava "TROQUE: nome do formato";
- --base que não existe deixava a pasta do formato pela metade;
- referencia com arquivo que não é vídeo dizia "ok" e gravava lixo como exemplo; exemplo com vídeo que não existe
  estourava erro técnico; folha sem exemplo saía 0;
- o 1º quadro do motor do _modelo saía preto (a 1ª cena entrava aos poucos desde o 0 s)."""
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures   # noqa: F401  (põe app/ferramentas no caminho)
import formatos
import producao as P
import simples
from test_esteira import Base, video

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


class FormatoNovo(Base):
    def setUp(self):
        super().setUp()
        shutil.copytree(REAL / "_modelo", self.formatos / "_modelo", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "app/ferramentas").mkdir(parents=True, exist_ok=True)
        (self.root / "app/ferramentas/storyboard.py").write_text("print('storyboard')"); (self.root / "app/ferramentas/conferir_video.py").write_text("print('conferir')")
        (self.root / "REGRAS.md").write_text("# Regras")   # o motor genérico acha a raiz do Estúdio por aqui
        self.stack.enter_context(patch.object(simples, "UPLOADS", self.est))
        self.client = fixtures.servidor.app.test_client()

    def aprontar(self, slug: str) -> None:
        """O que o João faz depois do novo: referência, ESTUDO.md respondido, TROQUE: trocado, pronto."""
        self.assertEqual(cli("referencia", slug, str(video(self.root / "ref.mp4", dur=5)))[0], 0)
        d = self.formatos / slug
        est = d / "ESTUDO.md"
        est.write_text(est.read_text(encoding="utf-8").replace("  R:", "  R: cena de 2 s, corte seco", 1), encoding="utf-8")
        for p in [d / "formato.json", d / "COMO-FAZER.md", *((d / "base").iterdir() if (d / "base").is_dir() else [])]:
            p.write_text(p.read_text(encoding="utf-8").replace(formatos.MARCA_MODELO, "Feito:"), encoding="utf-8")
        self.assertEqual(formatos.marcar_pronto(slug), [])

    def criar_pela_tela(self, slug: str, titulo: str) -> dict:
        clip = video(self.root / "bruto.mp4")
        r = self.client.post("/criar", data={"formato": slug, "cliente": "Teste", "titulo": titulo,
                                             "videos": [(clip.open("rb"), "bruto.mp4")]},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        return P.carregar("Teste", C.make_slug(titulo))

    def test_motor_novo_da_tela_ao_pedido_da_esteira(self):
        code, txt = cli("novo", "meu-motor", "--motor", "--titulo", "Meu motor")
        self.assertEqual(code, 0, txt)
        self.aprontar("meu-motor")
        self.assertIn('data-formato="meu-motor"', self.client.get("/criar").get_data(as_text=True))
        job = self.criar_pela_tela("meu-motor", "Teste do motor")
        self.assertEqual((job["formato"], job["modelo"]), ("meu-motor", "meu-motor"))
        modelo = self.content / "modelos/meu-motor"
        for arq in ("render.py", "index.html"):   # o motor foi pro modelo do cliente
            self.assertTrue((modelo / arq).is_file(), arq)
        self.assertEqual(C.ler_json(modelo / "aprendizado/regras.json")["regras"], [])
        etapas = C.ler_json(self.formatos / "meu-motor/formato.json")["esteira"]["etapas"]
        a = P.prompt_esteira(job, "ate_aprovacao")
        self.assertIn("formatos/meu-motor/COMO-FAZER.md", P.prompt_esteira(job, "ate_aprovacao") + P.camadas_de_regra(job))
        for e in etapas:                                   # os passos do formato, na ordem
            self.assertIn(e["titulo"], a)
        self.assertLess(a.index(etapas[0]["titulo"]), a.index(etapas[-1]["titulo"]))
        self.assertIn("exemplo-1-folha.jpg", a)            # o exemplo é a régua
        self.assertIn("PARA AQUI", a)                      # para no storyboard pro João aprovar
        self.assertIn("formatos/meu-motor/ESTUDO.md", a)   # lê o estudo em vez de reestudar
        self.assertIn("--storyboard", a)
        # o som que o formato declara chega na IA; o catálogo que o formato novo não tem, não
        self.assertIn("O FORMATO DIZ (manda sobre a lista): Feito: de onde vem a música", a)
        self.assertIn("O FORMATO DIZ (de onde vêm os efeitos): Feito:", a)
        self.assertNotIn("audio/catalogo.json", a)
        d = P.prompt_esteira(job, "depois")
        self.assertIn("--conferir", d)
        self.assertIn("folha-comparacao.jpg", d)

    def test_gravado_novo_ganha_modelo_proprio_e_nao_rouba_o_de_outro_formato(self):
        self.criar_formato(slug="vizinho", modelos=("estilo",), esteira=False)   # o formato que já usa o modelo estilo
        (self.mod / "gerar.sh").write_text('#!/bin/zsh\n# uso: gerar.sh --dir <pasta>\nOUT_DIR="$VC/output/estilo"; mkdir -p "$OUT_DIR"\n')
        base = "clientes/Teste/testeContent/modelos/estilo"
        code, txt = cli("novo", "meu-gravado", "--gravado", "--base", base + "/")
        self.assertEqual(code, 0, txt)
        dados = C.ler_json(self.formatos / "meu-gravado/formato.json")
        self.assertEqual((dados["modelos"], dados["base"], dados["titulo"]), (["meu-gravado"], base, "Meu gravado"))
        self.assertEqual(formatos.de_modelo("estilo")["slug"], "vizinho")   # o vídeo antigo continua no formato dele
        code, txt = cli("novo", "outro", "--gravado", "--base", base, "--modelo", "estilo")
        self.assertEqual(code, 1)
        self.assertIn("já é do formato vizinho", txt)
        self.assertFalse((self.formatos / "outro").exists())
        # pela tela: o cliente ganha o modelo meu-gravado, cópia da base, com o aprendizado zerado
        self.aprontar("meu-gravado")
        job = self.criar_pela_tela("meu-gravado", "Teste gravado")
        self.assertEqual((job["formato"], job["modelo"]), ("meu-gravado", "meu-gravado"))
        novo = self.content / "modelos/meu-gravado"
        gerar = (novo / "gerar.sh").read_text()
        self.assertIn('OUT_DIR="$VC/output/meu-gravado"', gerar)   # a saída não cai na pasta do modelo estilo
        self.assertIn("output/estilo", (self.mod / "gerar.sh").read_text())
        self.assertEqual(C.ler_json(novo / "aprendizado/regras.json")["regras"], [])
        txt = P.camadas_de_regra(job)
        self.assertIn("PASSOS DO FORMATO", txt)
        self.assertIn("zsh ../gerar.sh --dir .", txt)
        self.assertIn("Som do formato: música: Feito: de onde vem a música", txt)
        self.assertIn("formatos/meu-gravado/ESTUDO.md", txt)

    def test_validar_acusa_dois_formatos_com_o_mesmo_modelo(self):
        self.criar_formato(slug="vizinho", modelos=("estilo",), esteira=False)
        self.assertEqual(cli("novo", "meu-formato", "--motor")[0], 0)
        d = self.formatos / "meu-formato/formato.json"
        C.gravar_json(d, {**C.ler_json(d), "modelos": ["estilo"]})
        self.assertTrue(any("também é do formato vizinho" in x for x in formatos.validar("meu-formato")))

    def test_base_que_nao_existe_nao_deixa_pasta(self):
        code, txt = cli("novo", "sem-base", "--gravado", "--base", "clientes/Teste/testeContent/modelos/nao-tem")
        self.assertEqual(code, 1)
        self.assertIn("não existe", txt)
        self.assertFalse((self.formatos / "sem-base").exists())

    def test_nome_errado_diz_o_que_tentar(self):
        for nome, dica in (("teste-café", "teste-cafe"), ("meu formato", "meu-formato"), ("Meu-Formato", "meu-formato")):
            code, txt = cli("novo", nome, "--motor")
            self.assertEqual(code, 1, nome)
            self.assertIn(f"Tente: {dica}", txt)
            self.assertNotIn("Traceback", txt)
        self.assertEqual([p.name for p in self.formatos.iterdir()], ["_modelo"])
        self.assertEqual(cli("novo", "meu-formato", "--motor")[0], 0)
        code, txt = cli("novo", "meu-formato", "--motor")
        self.assertEqual(code, 1)
        self.assertIn("já existe", txt)

    def test_sem_titulo_a_tela_nao_mostra_troque(self):
        self.assertEqual(cli("novo", "meu-formato", "--motor")[0], 0)
        self.assertEqual(formatos.carregar("meu-formato")["titulo"], "Meu formato")
        est = formatos.esteira(formatos.carregar("meu-formato"))
        self.assertEqual((est["musica_de_onde"], est["efeitos_de_onde"]), ("", ""))   # "TROQUE:" não vai pra IA
        self.assertIn("# Como fazer: Meu formato", (self.formatos / "meu-formato/COMO-FAZER.md").read_text(encoding="utf-8"))
        self.assertIn('data-titulo="Meu formato"', self.client.get("/criar").get_data(as_text=True))

    def test_referencia_e_exemplo_recusam_o_que_nao_e_video(self):
        self.assertEqual(cli("novo", "meu-formato", "--motor")[0], 0)
        d = self.formatos / "meu-formato"
        texto = self.root / "nota.mp4"
        texto.write_text("não sou vídeo")
        for args in (("referencia", "meu-formato", str(texto)), ("exemplo", "meu-formato", str(texto))):
            code, txt = cli(*args)
            self.assertEqual(code, 1, args)
            self.assertIn("não é um vídeo", txt)
            self.assertNotIn("Traceback", txt)
        self.assertFalse(list(d.glob("exemplo-*")))
        self.assertFalse((d / "ESTUDO.md").exists())
        self.assertEqual(C.ler_json(d / "formato.json")["exemplos"], [])
        for args, msg in ((("referencia", "meu-formato", str(self.root / "nao.mp4")), "Vídeo não encontrado"),
                          (("exemplo", "meu-formato", str(self.root / "nao.mp4")), "Vídeo não encontrado"),
                          (("referencia", "nao-tem", str(texto)), "Formato não encontrado"),
                          (("pronto", "nao-tem"), "Formato não encontrado"),
                          (("folha", "nao-tem"), "Formato não encontrado"),
                          (("folha", "meu-formato"), "ainda não tem")):
            code, txt = cli(*args)
            self.assertEqual(code, 1, args)
            self.assertIn(msg, txt)
            self.assertNotIn("Traceback", txt)

    @unittest.skipUnless(TEM_PLAYWRIGHT, "sem Playwright")
    def test_primeiro_quadro_do_motor_novo_nao_e_preto(self):
        from PIL import Image
        self.assertEqual(cli("novo", "meu-formato", "--motor")[0], 0)
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out, True)
        r = subprocess.run([sys.executable, "render.py", "--cenas", "cenas-modelo.json", "--out", str(out), "--quadro", "0"],
                           cwd=self.formatos / "meu-formato/base", capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        png = next((out / "quadros").glob("*.png"))
        self.assertGreater(max(Image.open(png).convert("L").getextrema()), 200)   # tem letra branca, não só o fundo


if __name__ == "__main__":
    unittest.main()
