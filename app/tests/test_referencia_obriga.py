"""Peça 5b do plano do briefing (10-out-2026): referência que obriga.

A esteira pede a seção "Referência analisada" no ANALISE.md e a conferência reprova sem ela; cada formato declara os
layouts que sabe montar; a referência que pede outro layout é avisada antes de gastar; o storyboard diz se usou.
Tudo em pasta temporária (test_esteira.Base): nada pago, nenhuma chamada de API, catálogo real só lido."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures   # noqa: F401  (põe app/ferramentas no caminho)
import formatos
import conversa
import ia
import runner
from test_esteira import Base

C, P = fixtures.C, fixtures.P
REAL = formatos.FORMATOS
LINHA_REF = ("REFERÊNCIA DESTE VÍDEO: material/ref.mp4, no segundo 3,5. O que copiar: a tela dividida, ele em cima e a Bia"
             " embaixo. Siga o formato, mas copie o jeito dessa referência. Extraia quadros dela antes de planejar.")
SECAO = """# Storyboard

Cena 1: o dono na porta.

## Referência analisada
Usada: {usada}
Quadros: {quadros}
Layout: dividido
Copiado: ritmo e legenda
Não deu: {nao_deu}
"""


class LayoutsDoCatalogo(unittest.TestCase):
    def test_todo_formato_real_declara_layouts_validos(self):
        slugs = [d.name for d in REAL.iterdir() if (d / "formato.json").is_file()]
        self.assertGreaterEqual(len(slugs), 9)
        for slug in slugs:
            with self.subTest(formato=slug):
                self.assertEqual([x for x in formatos.validar(slug) if "layouts" in x], [])
                lays = C.ler_json(REAL / slug / "formato.json")["layouts"]
                self.assertTrue(lays and all(x in formatos.LAYOUTS for x in lays))
        self.assertEqual(C.ler_json(REAL / "lista-de-estaticos/formato.json")["layouts"], ["cheio"])   # só cheio: o exemplo dos avisos abaixo
        self.assertIn("dividido", C.ler_json(REAL / "tela-dividida/formato.json")["layouts"])

    def test_aviso_de_layout_ausente(self):
        d3 = formatos.carregar("lista-de-estaticos")   # só faz tela cheia (tela-dividida faz dividido)
        a = formatos.aviso_layout({"video": "material/ref.mp4", "o_que_copiar": "a tela dividida, ele em cima e ela embaixo"}, d3)
        self.assertEqual(a["layout"], "dividido")
        self.assertEqual(a["tem"], ["cheio"])
        self.assertIn("tela-dividida", a["outros"])
        for trecho in ("tela dividida", "Lista de estáticos (pessoa no canto) só faz tela cheia", "trocar pro formato", "ensinar o Lista de estáticos (pessoa no canto)"):
            self.assertIn(trecho, a["aviso"])
        # o "layout" marcado na conversa ganha das palavras; o briefing inteiro também serve (formato sugerido)
        self.assertEqual(formatos.aviso_layout({"layout": "cantinho", "o_que_copiar": "tela dividida"}, d3)["layout"], "cantinho")
        b = {"formato_sugerido": {"slug": "lista-de-estaticos"}, "referencia": {"video": "x.mp4", "o_que_copiar": "split screen"}}
        self.assertEqual(formatos.aviso_layout(b)["layout"], "dividido")
        self.assertIsNone(formatos.aviso_layout({"o_que_copiar": "a tela dividida, ele em cima e ela embaixo"}, "tela-dividida"))   # sem a frase de "não faz"

    def test_sem_aviso_quando_cabe_ou_nao_pede(self):
        self.assertIsNone(formatos.aviso_layout({"o_que_copiar": "o ritmo e a legenda colorida"}, "tela-dividida"))
        self.assertIsNone(formatos.aviso_layout({"o_que_copiar": "a tela dividida"}, "tela-dividida"))
        self.assertIsNone(formatos.aviso_layout({"o_que_copiar": "a tela dividida"}, "nao-existe"))
        self.assertEqual(formatos.layout_pedido("janela com pinheiros ao fundo"), [])   # cenário não é layout

    def test_conversa_avisa_o_layout(self):
        b = {"formato_sugerido": {"slug": "lista-de-estaticos"}, "material_liberado": [],
             "referencia": {"video": "Loja/ref.mp4", "o_que_copiar": "", "layout": "dividido"}}
        avisos = conversa.avisos_material(b)
        self.assertEqual(len(avisos), 1)
        self.assertIn("ensinar o Lista de estáticos (pessoa no canto)", avisos[0])
        b["formato_sugerido"]["slug"] = "dialogo-3d"
        self.assertEqual(conversa.avisos_material(b), [])   # o 3D divide: nada a avisar
        b["referencia"]["layout"] = "cheio"
        self.assertEqual(conversa.avisos_material(b), [])


class ValidarLayouts(Base):
    def test_layouts_validados(self):
        d = self.criar_formato()
        dados = C.ler_json(d / "formato.json")
        faltas = lambda: [x for x in formatos.validar("doc-teste") if "layouts" in x]
        for ruim in (None, [], "cheio"):
            with self.subTest(layouts=ruim):
                dados["layouts"] = ruim
                C.gravar_json(d / "formato.json", dados)
                self.assertTrue(any('falta "layouts"' in x for x in faltas()))
        dados["layouts"] = ["cheio", "holograma"]
        C.gravar_json(d / "formato.json", dados)
        self.assertTrue(any("não conhece: holograma" in x for x in faltas()))
        dados["layouts"] = ["cheio", "dividido"]
        C.gravar_json(d / "formato.json", dados)
        self.assertEqual(faltas(), [])


class ReferenciaObriga(Base):
    def setUp(self):
        super().setUp()
        d = self.criar_formato()
        dados = C.ler_json(d / "formato.json")
        dados["layouts"] = ["cheio"]
        C.gravar_json(d / "formato.json", dados)
        self.j = self.job_formato()
        self.sb = self.root / self.j["sandbox"]

    def com_referencia(self):
        self.j["briefing"] = "clima: limpo\n\n" + LINHA_REF
        P.salvar(self.j)
        return P.carregar("Teste", "video")

    def analise(self, usada="sim", quadros="work/folhas/referencia.jpg", nao_deu="nada", folha=True):
        (self.sb / "ANALISE.md").write_text(SECAO.format(usada=usada, quadros=quadros, nao_deu=nao_deu), encoding="utf-8")
        if folha:
            (self.sb / "work/folhas").mkdir(parents=True, exist_ok=True)
            (self.sb / "work/folhas/referencia.jpg").write_bytes(b"jpg")

    def test_acha_a_referencia_do_criar(self):
        self.assertIsNone(P.referencia_do_job(self.j))
        r = P.referencia_do_job(self.com_referencia())
        self.assertEqual(r["video"], "material/ref.mp4")
        self.assertEqual(r["segundo"], 3.5)
        self.assertIn("tela dividida", r["o_que_copiar"])

    def test_prompt_pede_a_secao_so_com_referencia(self):
        self.assertNotIn("Referência analisada", P.prompt_esteira(self.j, "ate_aprovacao"))
        a = P.prompt_esteira(self.com_referencia(), "ate_aprovacao")
        for trecho in ("## Referência analisada", "Usada: sim | em parte | não", "app/ferramentas/folha.py",
                       "work/folhas/referencia.jpg", "a conferência reprova", "Este formato sabe montar: cheio",
                       "a referência pede dividido e o formato não tem"):
            self.assertIn(trecho, a)

    def test_conferencia_reprova_sem_a_secao(self):
        self.assertEqual(P.conferir_referencia(self.j), "")             # sem referência: nada a conferir
        j = self.com_referencia()
        self.assertIn("não tem a seção", P.conferir_referencia(j))      # sem ANALISE.md
        (self.sb / "ANALISE.md").write_text("# Storyboard\nCena 1.\n", encoding="utf-8")
        self.assertIn("não tem a seção", P.conferir_referencia(j))      # o achado de 10-out: ANALISE.md sem citar a referência
        self.analise(folha=False)
        self.assertIn("folha de quadros", P.conferir_referencia(j))     # diz que usou, mas a folha não existe
        self.analise(usada="talvez")
        self.assertIn("não diz se a referência foi usada", P.conferir_referencia(j))
        self.analise(usada="em parte", nao_deu="")
        self.assertIn("não diz por quê", P.conferir_referencia(j))
        self.analise()
        self.assertEqual(P.conferir_referencia(j), "")

    def test_storyboard_diz_se_usou(self):
        j = self.com_referencia()
        self.assertEqual(P.referencia_storyboard("Teste", "video"), "")   # storyboard ainda não saiu
        self.analise()
        self.assertEqual(P.referencia_storyboard("Teste", "video"), "Referência: usada (estilo: ritmo e legenda)")
        self.analise(usada="em parte", nao_deu="o motor 3D não divide a tela")
        self.assertEqual(P.referencia_storyboard("Teste", "video"), "Referência: usada em parte; não deu: o motor 3D não divide a tela")
        self.analise(usada="não, porque o link não baixou", folha=False)
        self.assertEqual(P.conferir_referencia(j), "")
        self.assertEqual(P.referencia_storyboard("Teste", "video"), "Referência: não usada porque o link não baixou")
        (self.sb / "storyboard.jpg").write_bytes(b"jpg")
        html = self.client.get("/job/Teste/video").get_data(as_text=True)
        self.assertIn("Referência: não usada porque o link não baixou", html)
        self.assertLess(html.index("Referência: não usada porque"), html.index('class="storyboard-grande'))   # no topo

    def test_runner_reprova_o_storyboard_sem_a_secao(self):
        self.com_referencia()
        prompt = self.root / "prompt.txt"
        prompt.write_text("x", encoding="utf-8")
        argv = ["runner.py", "Teste", "video", "analise", str(prompt), "plano"]
        with patch.object(sys, "argv", argv), patch.dict(os.environ), patch.object(ia, "executar", return_value=0), \
                patch.object(ia, "selecao", return_value={"provedor": "claude", "modelo": "sonnet"}), \
                patch.object(runner, "_custos_ao_vivo"), patch.object(runner, "_andamento"):
            runner.main()
            j = P.carregar("Teste", "video")
            self.assertEqual(j["status"], "erro")
            self.assertIn("Referência analisada", j["erro"])
            self.analise()
            runner.main()
            j = P.carregar("Teste", "video")
            self.assertEqual(j["status"], "plano")
            self.assertNotIn("erro", j)


class TelaCriar(Base):
    def test_api_aviso_layout(self):
        with patch.object(formatos, "FORMATOS", REAL):
            d = self.client.get("/api/aviso-layout?formato=lista-de-estaticos&copiar=a%20tela%20dividida").get_json()
            self.assertIn("ensinar o Lista de estáticos (pessoa no canto)", d["aviso"])
            d = self.client.get("/api/aviso-layout?formato=dialogo-3d&copiar=a%20tela%20dividida").get_json()
            self.assertEqual(d["aviso"], "")
            d = self.client.get("/api/aviso-layout?formato=dialogo-3d&copiar=o%20ritmo").get_json()
            self.assertEqual(d["aviso"], "")


if __name__ == "__main__":
    unittest.main()
