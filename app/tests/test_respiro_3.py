"""Respiro 3.0 (29-out-2026): storyboard visual do estilo, Força do Claude, vozes em português (arquétipos do VoiceStudio),
?estilo=&cliente= no Criar e tema claro das telas de trabalho."""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))

import storyboard_estilo as sb  # noqa: E402
import vozes  # noqa: E402


class Storyboard(unittest.TestCase):
    V = {"fps": 25.0, "duracao": 100.0,
         "planos": {"mediana_s": 0.5, "lista": [{"s": 0.0, "dura_s": 3.4}, {"s": 3.4, "dura_s": 0.4}, {"s": 40.0, "dura_s": 9.0}]},
         "transicoes": [{"tipo": "corte", "s": 3.4, "quadros": 1}, {"tipo": "dissolve", "s": 16.6, "quadros": 5}, {"tipo": "especial", "s": 38.8, "quadros": 4}],
         "numeros": [{"s": 55.0, "texto": "22 por cento", "evento": True, "evento_menos_palavra_q": 1}],
         "fala_imagem": {"oracoes": [{"s": 8.0, "texto": "Primeira frase longa o bastante pra ser cortada no meio do caminho certo", "troca": True, "troca_tipo": "corte", "imagem_nova": True},
                                     {"s": 70.0, "texto": "Outra", "troca": False, "imagem_nova": True, "evento": True},
                                     {"s": 80.0, "texto": "Sem nada", "troca": False, "imagem_nova": False, "evento": False}]}}

    def test_tempo_em_portugues(self):
        self.assertEqual(sb.tempo(2.34), "2,3 s")
        self.assertEqual(sb.tempo(0), "0,0 s")

    def test_momentos_do_estudo_tem_legenda_e_tempo(self):
        m = sb.momentos_estudo(self.V)
        leg = {x["legenda"] for x in m}
        self.assertIn("abertura: cena de 3,4 s", leg)
        self.assertIn("dissolve de 5 quadros (0,2 s)", leg)
        self.assertIn("transição especial (4 quadros)", leg)
        self.assertIn("corte seco · imagem nova", leg)
        self.assertTrue(any(x["legenda"].startswith("número falado") and x["fala"] for x in m))
        self.assertFalse(any(x["t"] == 80.0 for x in m))    # oração sem nada acontecendo não vira quadro
        self.assertTrue(all(len(x["fala"]) <= 45 for x in m))

    def test_escolher_espalha_pelo_video_e_comeca_na_abertura(self):
        esc = sb.escolher(sb.momentos_estudo(self.V), 100.0, 8)
        self.assertLessEqual(len(esc), 8)
        self.assertEqual(esc[0]["t"], 0.0)
        self.assertEqual([x["t"] for x in esc], sorted(x["t"] for x in esc))
        self.assertEqual(len({int(x["t"] // 12.5) for x in esc}), len(esc))   # no máximo um por faixa de tempo
        self.assertEqual(sb.escolher([], 100.0), [])

    def test_caminho_recusa_nome_de_fora_do_cache(self):
        for slug, nome in (("editorial", "../x.jpg"), ("../editorial", "a.jpg"), ("editorial", "a.png"), ("editorial", "a/b.jpg")):
            self.assertIsNone(sb.caminho(slug, nome))

    def test_estilo_inexistente_ou_sem_video_nao_quebra(self):
        self.assertEqual(sb.quadros("nao-existe-esse-estilo"), [])
        self.assertEqual(sb.quadros("../etc"), [])

    @unittest.skipUnless(shutil.which("ffmpeg") and (RAIZ / "formatos" / "editorial" / "exemplo-1.mp4").is_file(), "sem ffmpeg ou exemplo")
    def test_editorial_gera_tira_do_estudo_no_cache(self):
        qs = sb.quadros("editorial")
        self.assertGreaterEqual(len(qs), 4)
        self.assertEqual(qs[0]["tempo"], "0,0 s")
        r = sb.tira("editorial", esperar=True)
        self.assertEqual(r["estado"], "pronto")
        self.assertGreaterEqual(r["total"], len(qs))          # a tira guarda TODOS os planos; 'destaque' é o que aparece de cara
        self.assertTrue(all(q["fonte"] == "estudo" for q in [dict(q, fonte=r["fonte"]) for q in qs]))
        self.assertTrue(all(sb.caminho("editorial", q["arquivo"], r["ref_id"]) for q in r["quadros"]))
        self.assertTrue(str(sb.caminho("editorial", qs[0]["arquivo"], r["ref_id"])).startswith(str(sb.CACHE)))    # nunca em formatos/
        from servidor import app
        c = app.test_client()
        self.assertEqual(c.get(f"/storyboard/editorial/{r['ref_id']}/{qs[0]['arquivo']}").status_code, 200)
        self.assertEqual(c.get("/storyboard/editorial/nao-e-nosso.jpg").status_code, 404)
        self.assertEqual(c.get(f"/storyboard/editorial/..%2Fx/{qs[0]['arquivo']}").status_code, 404)
        h = c.get("/formato/editorial").get_data(as_text=True)
        self.assertIn('id="tira-lista"', h)
        self.assertIn("Ritmo e cenas", h)
        j = c.get("/api/storyboard/editorial").get_json()
        self.assertEqual(j["estado"], "pronto")
        self.assertEqual(len(j["quadros"]), r["total"])
        self.assertTrue(all(q["url"].startswith("/storyboard/editorial/") for q in j["quadros"]))
        self.assertTrue(j["resumo"]["tipos"] and j["resumo"]["numeros"])


class VozesArquetipos(unittest.TestCase):
    def test_sem_sotaque(self):
        self.assertEqual(vozes.sem_sotaque("male, middle-aged, low pitch, american accent"), "male, middle-aged, low pitch")
        self.assertEqual(vozes.sem_sotaque("female, young adult, chinese dialect, high pitch"), "female, young adult, high pitch")

    def test_nomes_em_portugues(self):
        n = lambda name, **f: vozes.nome_pt({"name": name, "facets": f})  # noqa: E731
        self.assertEqual(n("The Librarian"), "A Bibliotecária")
        self.assertEqual(n("Captain Crusty"), "Capitão Casca-Grossa")
        self.assertEqual(n("Spanish Narrator", gender="female"), "Narradora (espanhol)")
        self.assertEqual(n("Portuguese Explainer", gender="male"), "Explicador (português)")
        self.assertEqual(n("American · Male · Child · Moderate", gender="male", age="child", pitch="moderate pitch"), "Menino, tom médio")
        self.assertEqual(n("X · Female · Child", gender="female", age="child", pitch="high pitch"), "Menina, aguda")

    def test_descricao_a_partir_das_caracteristicas(self):
        d = vozes.descricao_arq({"use_case": "narration", "facets": {"gender": "female", "age": "middle-aged", "pitch": "low pitch"}})
        self.assertEqual(d, "feminina, grave, adulta · narração")
        d = vozes.descricao_arq({"use_case": "conversational", "facets": {"gender": "male", "age": "young adult", "pitch": "moderate pitch", "whisper": True}})
        self.assertEqual(d, "masculina, tom médio, jovem, sussurrada · conversa")

    ITENS = [
        {"id": "a1", "name": "The Librarian", "use_case": "narration", "instruct": "female, middle-aged, low pitch, british accent",
         "facets": {"gender": "female", "age": "middle-aged", "pitch": "low pitch"}},
        {"id": "a2", "name": "Spanish Narrator", "use_case": "narration", "instruct": "female, middle-aged, low pitch",       # mesmo timbre sem sotaque: cai junto
         "facets": {"gender": "female", "age": "middle-aged", "pitch": "low pitch"}},
        {"id": "a3", "name": "The Anchor", "use_case": "entertainment", "instruct": "male, middle-aged, moderate pitch, american accent",
         "facets": {"gender": "male", "age": "middle-aged", "pitch": "moderate pitch"}},
    ]

    def test_arquetipos_sem_timbre_repetido_e_com_tags(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vozes, "_itens_arquetipos", return_value=self.ITENS), \
                mock.patch.object(vozes, "ARQ_MAPA", Path(d) / "mapa.json"):
            arqs = vozes.arquetipos()
            self.assertEqual([a["id"] for a in arqs], ["a1", "a3"])
            self.assertEqual(arqs[0]["instruct"], "female, middle-aged, low pitch")      # o que vai pro VoiceStudio não leva sotaque
            self.assertIn("mulher", arqs[0]["tags"]); self.assertIn("grave", arqs[0]["tags"]); self.assertIn("portugues", arqs[0]["tags"])
            self.assertIn("noticia", arqs[1]["tags"])

    def test_mapa_arquetipo_para_perfil_cria_uma_vez_so(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vozes, "_itens_arquetipos", return_value=self.ITENS), \
                mock.patch.object(vozes, "ARQ_MAPA", Path(d) / "mapa.json"), \
                mock.patch.object(vozes, "_perfil_de_instrucao", return_value="perfil1") as cria, \
                mock.patch.object(vozes, "lista", return_value=[{"id": "perfil1"}]):
            self.assertEqual(vozes.perfil_do_arquetipo("arq:a1"), "perfil1")
            self.assertEqual(vozes.perfil_do_arquetipo("a1"), "perfil1")                  # 2ª vez: do mapa, sem gerar de novo
            self.assertEqual(cria.call_count, 1)
            nome, instr = cria.call_args[0][:2]
            self.assertEqual((nome, instr), ("A Bibliotecária", "female, middle-aged, low pitch"))
            self.assertEqual(json.loads((Path(d) / "mapa.json").read_text()), {"a1": "perfil1"})
            self.assertEqual(vozes.cartoes_arquetipos()[0]["id"], "arq:a3")             # o que já virou perfil sai de "Mais vozes"
            with mock.patch.object(vozes, "lista", return_value=[]):                       # perfil apagado no VoiceStudio: cria de novo
                vozes.perfil_do_arquetipo("a1")
            self.assertEqual(cria.call_count, 2)

    def test_arquetipo_que_nao_existe_recusa(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vozes, "_itens_arquetipos", return_value=self.ITENS), \
                mock.patch.object(vozes, "ARQ_MAPA", Path(d) / "mapa.json"):
            with self.assertRaises(ValueError):
                vozes.perfil_do_arquetipo("arq:nao-existe")

    def test_tags_de_perfil_pelo_nome(self):
        self.assertEqual(set(vozes.tags_perfil("Locutor de notícia", True)), {"homem", "noticia", "portugues", "clonada"})
        t = vozes.tags_perfil("Narradora jovem calma", True)
        self.assertIn("mulher", t); self.assertNotIn("homem", t); self.assertIn("jovem", t)
        self.assertIn("historia", vozes.tags_perfil("Senhor contador de história", True))
        self.assertNotIn("portugues", vozes.tags_perfil("Binge Files Narrator", False))
        self.assertTrue(set(vozes.ROTULOS_TAGS) >= {"homem", "mulher", "jovem", "adulto", "mais-velho", "grave", "agudo", "narracao", "noticia", "conversa", "historia", "portugues", "clonada"})


class Criar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from servidor import app
        app.testing = True
        cls.c = app.test_client()

    def test_forca_do_claude_faixas(self):
        import novo_rotas as n
        casos = {0: ("Rápido", "haiku", "low"), 19: ("Rápido", "haiku", "low"), 20: ("Bom", "sonnet", "medium"), 44: ("Bom", "sonnet", "medium"),
                 45: ("Forte", "sonnet", "high"), 69: ("Forte", "sonnet", "high"), 70: ("Muito forte", "opus", "high"), 89: ("Muito forte", "opus", "high"),
                 90: ("Ultra", "opus", "max"), 100: ("Ultra", "opus", "max")}
        for v, (nome, modelo, esf) in casos.items():
            f = n.forca_de(v)
            self.assertEqual((f["nome"], f["modelo"], f["esforco"]), (nome, modelo, esf), v)
        self.assertEqual(n.forca_de(n.FORCA_PADRAO)["modelo"], "sonnet")          # padrão: meio-forte
        self.assertEqual(n.forca_de(n.FORCA_PADRAO)["esforco"], "high")
        import ia
        self.assertTrue({f[3] for f in n.FORCAS} <= {v for v, _ in ia.ESFORCOS})

    def test_criar_agora_campos_e_sem_tela_antiga(self):
        h = self.c.get("/criar-agora").get_data(as_text=True)
        for campo in ('name="ia_modelo"', 'name="ia_esforco"', 'type="range"', 'name="voz"', 'name="titulo"', 'name="cliente"', 'name="formato"', 'name="roteiro"'):
            self.assertIn(campo, h, campo)
        self.assertNotIn("tela antiga", h)
        self.assertIn("Avulso", h)
        self.assertNotIn("<select name=\"ia_modelo\"", h)
        self.assertLess(h.index('name="cliente"'), h.index('name="titulo"'))        # "Pra quem" é o primeiro campo
        for q in ("Padrão", "Conferido", "Ultra"):
            self.assertIn(q, h)

    def test_criar_agora_todos_os_estilos_prontos_aparecem(self):
        import formatos
        h = self.c.get("/criar-agora").get_data(as_text=True)
        for f in formatos.listar():
            if f.get("status") == "pronto":
                self.assertIn(f'data-slug="{f["slug"]}"', h, f["slug"])
        self.assertIn("fv-mais", h)

    def test_estilo_e_cliente_pela_url(self):
        h = self.c.get("/criar-agora?estilo=editorial&cliente=Joao").get_data(as_text=True)
        self.assertIn('{"estilo": "editorial"}', h)
        self.assertRegex(h, r'<option selected>Joao</option>')
        self.assertIn('{"estilo": ""}', self.c.get("/criar-agora?estilo=nao-existe").get_data(as_text=True))
        self.assertIn('{"estilo": "editorial"}', self.c.get("/criar-agora?formato=editorial").get_data(as_text=True))

    def test_todo_caminho_de_criar_vai_pro_criar_agora(self):
        h = self.c.get("/formato/editorial").get_data(as_text=True)
        self.assertIn('href="/criar-agora?estilo=editorial"', h)
        h = self.c.get("/formatos?cliente=Joao").get_data(as_text=True)
        self.assertIn("/criar-agora?estilo=", h)
        self.assertNotRegex(h, r'href="/criar\?')
        r = self.c.get("/criar-video?cliente=Joao&modelo=dividido-mascara")
        if r.status_code in (301, 302):
            self.assertIn("/criar-agora", r.headers["Location"])
        self.assertEqual(self.c.get("/criar").status_code, 200)                       # a rota antiga continua

    def test_estilos_com_etiquetas(self):
        import novo_rotas as n
        self.assertEqual(set(n.tags_estilo({"slug": "explicador-3d", "titulo": "Explicador 3D", "grupo": "animacao", "entrada": "roteiro"})), {"animacao", "narracao", "3d"})
        self.assertEqual(set(n.tags_estilo({"slug": "tela-dividida", "grupo": "falando", "entrada": "video"})), {"falando", "gravado"})

    def test_vozes_tela_limpa(self):
        h = self.c.get("/vozes").get_data(as_text=True)
        self.assertIn("fv-busca", h)
        self.assertNotIn("vz-usar-cli", h)
        self.assertNotIn("Usar pro cliente", h)


class TemaClaro(unittest.TestCase):
    def test_ed_tem_versao_clara_e_escura(self):
        css = (RAIZ / "app/interface/static/estilo.css").read_text(encoding="utf-8")
        raiz = css[css.index(":root"):css.index("\n[data-theme=dark] {")]
        escuro = css[css.index("\n[data-theme=dark] {"):css.index("* { box-sizing")]
        self.assertRegex(raiz, r"--ed-bg:#ffffff")                  # claro é o padrão do :root
        self.assertRegex(escuro, r"--ed-bg:#0c0c0e")                 # escuro continua o do app
        self.assertRegex(css, r"\.editor:not\(\.ev\)\s*\{[^}]*--ed-bg:#0c0c0e")   # o editor de corte segue sala escura
        simples = (RAIZ / "app/interface/static/simples.css").read_text(encoding="utf-8")
        self.assertNotRegex(simples, r"\.nv\{[^}]*background:#")


if __name__ == "__main__":
    unittest.main()
