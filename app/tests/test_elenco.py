"""Elenco do ESTILO Explicador 3D (PLANO-2.0, item 7): ler/gravar formatos/<slug>/elenco.json, mesclar no elenco do roteiro
(render.py: elenco.js <- estilo <- cliente antigo <- roteiro) e as telas /elenco e /elenco/<slug>. Nada pago, nada de navegador."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app" / "ferramentas"))
sys.path.insert(0, str(RAIZ / "app" / "interface"))
import elenco as EL  # noqa: E402

_spec = importlib.util.spec_from_file_location("render_explicador", RAIZ / "formatos" / "explicador-3d" / "base" / "render.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


class Biblioteca(unittest.TestCase):
    def test_bases_do_elenco_js(self):
        b = EL.bases()
        self.assertGreaterEqual(len(b), 17)
        self.assertIn("dentista", b)
        self.assertEqual(len(b), len(set(b)))

    def test_rotulo(self):
        self.assertEqual(EL.rotulo("medica"), "Médica")
        self.assertEqual(EL.rotulo("dr_paulo"), "Dr paulo")


class Gravacao(unittest.TestCase):
    """Grava no elenco do ESTILO (formatos/<slug>/elenco.json). Aqui o arquivo é redirecionado pra uma pasta temporária."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.antes = EL.RAIZ
        self._arq = EL.arquivo
        arq = Path(self.tmp.name) / "elenco.json"
        EL.arquivo = lambda slug=EL.FORMATO: (EL._cfg(slug), arq)[1]
        self.arq = arq

    def tearDown(self):
        EL.arquivo = self._arq
        self.tmp.cleanup()

    def test_salva_so_o_que_mudou_e_cria_o_arquivo(self):
        nome = EL.salvar("explicador-3d", "Dr. Paulo", "dentista", {"camisa": {"tipo": "jaleco", "cor": "#ff0000"}, "bone": None})
        self.assertEqual(nome, "dr_paulo")
        self.assertTrue(self.arq.is_file())
        self.assertEqual(json.loads(self.arq.read_text())["dr_paulo"]["base"], "dentista")
        self.assertEqual(EL.ler("explicador-3d")["dr_paulo"]["camisa"]["cor"], "#ff0000")

    def test_mesmo_nome_do_base_e_nome_novo_convivem(self):
        EL.salvar("explicador-3d", "dentista", "dentista", {"pele": "#9a5f3c"})
        EL.salvar("explicador-3d", "dentista_noite", "dentista", {"calca": {"cor": "#000000"}})
        self.assertEqual(set(EL.ler("explicador-3d")), {"dentista", "dentista_noite"})

    def test_recusa_base_inexistente_campo_estranho_nome_vazio_e_estilo_sem_elenco(self):
        with self.assertRaises(ValueError):
            EL.salvar("explicador-3d", "x", "naoexiste", {})
        with self.assertRaises(ValueError):
            EL.salvar("explicador-3d", "x", "dentista", {"asa": True})
        with self.assertRaises(ValueError):
            EL.salvar("explicador-3d", "  ", "dentista", {})
        with self.assertRaises(ValueError):
            EL.salvar("frase-fixa", "x", "dentista", {})

    def test_voltar_ao_original(self):
        EL.salvar("explicador-3d", "dentista", "dentista", {"pele": "#9a5f3c"})
        self.assertTrue(EL.remover("explicador-3d", "dentista"))
        self.assertEqual(EL.ler("explicador-3d"), {})
        self.assertFalse(EL.remover("explicador-3d", "dentista"))

    def test_arquivo_do_estilo_fica_em_formatos(self):
        self.assertEqual(self._arq("explicador-3d"), EL.RAIZ / "formatos" / "explicador-3d" / "elenco.json")


class Registro(unittest.TestCase):
    def test_so_o_explicador_tem_elenco_hoje(self):
        self.assertEqual(list(EL.ELENCOS), ["explicador-3d"])
        self.assertTrue(EL.existe("explicador-3d"))
        self.assertFalse(EL.existe("frase-fixa"))

    def test_estilos_para_a_lista(self):
        e = EL.estilos()
        self.assertEqual(e[0]["slug"], "explicador-3d")
        self.assertGreaterEqual(e[0]["total"], 17)

    def test_previa_diz_onde_esta_a_base_do_formato(self):
        p = EL.previa("explicador-3d")
        self.assertEqual(p["base"], "/arquivo/formatos/explicador-3d/base/")
        self.assertEqual((p["personagem"], p["elenco"]), ("gente.js", "elenco.js"))


class Mescla(unittest.TestCase):
    CLI = {"dentista": {"base": "dentista", "camisa": {"cor": "#c0392b"}},
           "dr_paulo": {"base": "dentista", "bigode": True}}

    def test_nome_simples_pega_o_figurino_do_cliente(self):
        r = R.mesclar_elenco({"dono": "dentista", "vizinho": "comerciante"}, self.CLI)
        self.assertEqual(r["dono"], self.CLI["dentista"])
        self.assertEqual(r["vizinho"], "comerciante")

    def test_personagem_criado_pelo_cliente(self):
        self.assertEqual(R.mesclar_elenco({"dono": "dr_paulo"}, self.CLI)["dono"]["bigode"], True)

    def test_base_puro_tambem_vale_como_nome(self):
        r = R.mesclar_elenco({"dono": {"base": "dentista"}}, self.CLI)
        self.assertEqual(r["dono"]["camisa"]["cor"], "#c0392b")

    def test_roteiro_com_campos_manda_sobre_o_cliente(self):
        roteiro = {"dono": {"base": "dentista", "camisa": {"cor": "#00ff00"}}}
        self.assertEqual(R.mesclar_elenco(roteiro, self.CLI), roteiro)

    def test_sem_elenco_do_cliente_nada_muda(self):
        roteiro = {"dono": "dentista"}
        self.assertEqual(R.mesclar_elenco(roteiro, {}), roteiro)

    def _planejar(self, estilo, cliente, doc):
        with tempfile.TemporaryDirectory() as t:
            modelo = Path(t) / "modelo"
            sandbox = modelo / "_sandbox-x"
            sandbox.mkdir(parents=True)
            if cliente is not None:
                (modelo / "elenco.json").write_text(json.dumps(cliente), encoding="utf-8")
            velho = R.elenco_do_estilo
            R.elenco_do_estilo = lambda: estilo
            try:
                return R.planejar(doc, sandbox)["extra"]["elenco"]
            finally:
                R.elenco_do_estilo = velho

    DOC = {"elenco": {"dono": "dentista"}, "cenas": [{"de": 0, "ate": 2}], "duracao": 2}

    def test_o_motor_recebe_o_elenco_do_estilo(self):
        r = self._planejar(self.CLI, None, self.DOC)
        self.assertEqual(r["dono"]["camisa"]["cor"], "#c0392b")
        self.assertEqual(self._planejar({}, None, self.DOC)["dono"], "dentista")

    def test_elenco_antigo_do_cliente_vale_por_cima_do_estilo(self):
        cli = {"dentista": {"base": "dentista", "camisa": {"cor": "#00ff00"}}}
        r = self._planejar(self.CLI, cli, self.DOC)
        self.assertEqual(r["dono"]["camisa"]["cor"], "#00ff00")
        r2 = self._planejar({"dentista": {"base": "dentista", "pele": "#111111"}}, cli, self.DOC)
        self.assertEqual((r2["dono"]["pele"], r2["dono"]["camisa"]["cor"]), ("#111111", "#00ff00"))

    def test_o_render_acha_o_elenco_do_estilo_no_lugar_certo(self):
        arq = R.ESTUDIO / "formatos" / "explicador-3d" / "elenco.json"
        self.assertEqual(R.AQUI.parent / "elenco.json", arq)   # a base mora em formatos/explicador-3d/base
        self.assertIsInstance(R.elenco_do_estilo(), dict)


class Producao(unittest.TestCase):
    def test_prompt_cita_o_personagem_e_o_elenco_do_estilo(self):
        import producao
        txt = producao._personagem_txt({"cliente": "Joao", "personagem": "dentista"})
        self.assertIn("PERSONAGEM ESCOLHIDO: dentista", txt)
        self.assertIn("formatos/explicador-3d/elenco.json", txt)
        self.assertNotIn("modelos/explicador-3d", txt)
        self.assertEqual(producao._personagem_txt({"cliente": "Joao"}), "")


class Tela(unittest.TestCase):
    def test_lista_e_tela_do_estilo(self):
        from servidor import app
        c = app.test_client()
        r = c.get("/elenco")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("/elenco/explicador-3d", html)
        self.assertIn("Estilo com personagens aparece aqui", html)
        r = c.get("/elenco/explicador-3d")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Elenco do Explicador 3D", html)
        self.assertIn("elenco-previa.js", html)
        self.assertNotIn('id="el-cliente"', html)
        self.assertEqual(c.get("/elenco/frase-fixa").status_code, 404)
        self.assertEqual(c.post("/elenco/frase-fixa/salvar", json={"nome": "a", "base": "dentista"}).status_code, 400)
        self.assertEqual(c.post("/elenco/frase-fixa/voltar", json={"nome": "a"}).status_code, 400)
        self.assertEqual(c.post("/elenco/explicador-3d/salvar", json={"nome": "a", "base": "naoexiste"}).status_code, 400)
        with c.get("/arquivo/formatos/explicador-3d/base/gente.js") as g:
            self.assertEqual(g.status_code, 200)

    def test_elenco_na_pagina_do_estilo_e_fileira_no_criar(self):
        from servidor import app
        c = app.test_client()
        html = c.get("/formato/explicador-3d").get_data(as_text=True)
        self.assertIn("/elenco/explicador-3d", html)
        self.assertIn("Editar elenco", html)
        self.assertNotIn("Editar elenco", c.get("/formato/frase-fixa").get_data(as_text=True))
        self.assertIn('name="personagem"', c.get("/criar-agora").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
