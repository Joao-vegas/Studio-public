import importlib.util
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "app/ferramentas"))


def _build_caixa():
    p = RAIZ / "clientes/Avulso/avulsoContent/modelos/frase-fixa/build-caixa.py"
    spec = importlib.util.spec_from_file_location("build_caixa_t6", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class CaixaFraseFixa(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.m = _build_caixa()

    def _sala(self):
        return self.np.full((self.m.H, self.m.W), 15, dtype=self.np.uint8)

    def test_sala_escura_sem_texto_nao_vira_caixa(self):
        self.assertEqual(self.m.blocos_do_quadro(self._sala()), [])

    def test_sala_escura_inteira_com_rosto_nao_vira_caixa(self):
        q = self._sala()
        q[600:1200, 300:800] = 150  # rosto no meio
        self.assertEqual(self.m.blocos_do_quadro(q), [])

    def test_caixa_de_tres_linhas_dentro_da_sala(self):
        q = self._sala()
        q[:1000] = 120; q[1400:] = 120  # fundo claro em volta, caixa preta no meio
        q[1000:1400] = 10  # caixa preta de 400 px
        for y0 in (1150, 1250, 1330):  # 3 linhas de texto branco
            q[y0:y0 + 30, 400:660] = 250
        blocos = self.m.blocos_do_quadro(q)
        self.assertEqual(len(blocos), 1)
        b0, b1 = blocos[0]
        self.assertEqual((b0, b1), (1150, 1360))

    def test_sem_bloco_valido_escolher_devolve_none(self):
        self.assertIsNone(self.m.escolher_bloco([[], [], []]))

    def test_folga_de_28(self):
        import inspect
        self.assertEqual(inspect.signature(self.m.cobrir_bloco).parameters["folga"].default, 28)


class ConferirVideo(unittest.TestCase):
    def test_fim_de_frase(self):
        import conferir_video as c
        palavras = lambda *ws: [{"word": w} for w in ws]  # noqa: E731
        self.assertEqual(c.checar_fim_de_frase(palavras("Oi.", "Vai", "dar...")), ["Termina no meio da frase"])
        self.assertEqual(c.checar_fim_de_frase(palavras("Oi.", "Vai", "dar")), ["Termina no meio da frase"])
        self.assertEqual(c.checar_fim_de_frase(palavras("Oi.", "Vai", "dar.")), [])
        self.assertEqual(c.checar_fim_de_frase(palavras("sem", "pontuação")), [])   # sem pontuação não dá pra saber

    def test_formato_1080x1920_com_audio(self):
        import conferir_video as c
        self.assertEqual(c.checar_formato({"largura": 1080, "altura": 1920}, True), [])
        self.assertEqual(len(c.checar_formato({"largura": 540, "altura": 960}, False)), 2)

    def test_comando_conferir_e_padrao_dos_gravados(self):
        import formatos
        self.assertIn("conferir_video.py", formatos.COMANDOS_GRAVADO["conferir"])
        self.assertTrue((RAIZ / "app/ferramentas/conferir_video.py").is_file())

    def test_avisos_da_conferencia(self):
        import json
        import tempfile
        import producao
        with tempfile.TemporaryDirectory() as td:
            sb = Path(td) / "sb"; (sb / "qa").mkdir(parents=True)
            old = producao.RAIZ
            producao.RAIZ = Path("/")
            try:
                job = {"sandbox": str(sb).lstrip("/")}
                self.assertEqual(producao.avisos_da_conferencia(job), [])
                (sb / "qa/conferir.json").write_text(json.dumps({"ok": False, "avisos": ["Tela preta em 3 s"]}))
                self.assertEqual(producao.avisos_da_conferencia(job), ["Tela preta em 3 s"])
                (sb / "qa/conferir.json").write_text(json.dumps({"ok": True, "avisos": []}))
                self.assertEqual(producao.avisos_da_conferencia(job), [])
            finally:
                producao.RAIZ = old


class RegrasNaIA(unittest.TestCase):
    REGRAS = ["formatos/fala-com-cenas", "formatos/tela-dividida", "clientes/Joao/vegasContent/modelos/dividido-mascara",
              "clientes/Joao/vegasContent/modelos/reel-dividido-por-video", "clientes/Cliente2/marca2Content/modelos/dividido-mascara"]

    def test_nenhuma_regra_passa_de_600(self):
        import json
        for p in self.REGRAS:
            for r in json.loads((RAIZ / p / "aprendizado/regras.json").read_text(encoding="utf-8"))["regras"]:
                self.assertLessEqual(len(r.get("texto", "")), 600, f"{p}: {r['id']}")

    def test_nivel_2_guarda_medidas_e_evitar(self):
        import resumo_regras as r
        linha = r._linha({"id": "x", "titulo": "Legenda baixa", "texto": "Legenda a 900 px do topo, 3 palavras, -14 LUFS.",
                          "evitar": "Legenda em cima da boca."}, 2)
        self.assertIn("900", linha); self.assertIn("-14", linha); self.assertIn("Evitar: Legenda em cima da boca.", linha)

    def test_ultimas_reclamacoes(self):
        import json
        import tempfile
        import resumo_regras as r
        with tempfile.TemporaryDirectory() as td:
            h = Path(td) / "historico.jsonl"
            linhas = [{"tipo": "feedback", "texto": f"reclamação {i}", "createdAt": f"2026-10-0{i}"} for i in range(1, 8)]
            linhas.append({"tipo": "aprovacao", "texto": "aprovado", "createdAt": "2026-10-09"})
            h.write_text("\n".join(json.dumps(x) for x in linhas))
            out = r._reclamacoes([h])
            self.assertEqual(len(out), 5)
            self.assertIn("reclamação 7", out[-1]); self.assertNotIn("aprovado", " ".join(out))

    def test_aprendizado_avisa_acima_de_600_e_recusa_regra_sem_origem(self):
        import json
        import tempfile
        import aprendizado
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "x" / "aprendizado"; pasta.mkdir(parents=True)
            self.addCleanup(setattr, aprendizado, "RAIZ", aprendizado.RAIZ)
            aprendizado.RAIZ = Path(td)
            (pasta / "regras.json").write_text(json.dumps({"regras": [{"id": "a", "texto": "x" * 700, "origem": "João"}]}))
            self.assertEqual(aprendizado.orcamento(pasta)["acima_de_600"], ["a"])
            with self.assertRaises(ValueError):
                aprendizado.substituir(pasta, [{"id": "a", "texto": "x" * 10, "origem": "João"}, {"id": "b", "texto": "nova"}])


class Vocabulario(unittest.TestCase):
    def test_prompt_e_correcao(self):
        import vocabulario as v
        self.assertTrue(v.prompt("Cliente1").startswith("Produto1"))
        self.assertLessEqual(len(v.prompt("Cliente1")), 200)
        w = [{"word": "black"}, {"word": "farma,"}, {"word": "black"}, {"word": "friday."}]
        self.assertEqual(v.corrigir_lista(w, ["Produto1", "Black Friday"]), 4)
        self.assertEqual([x["word"] for x in w], ["Black", "Farma,", "Black", "Friday."])
        self.assertEqual(v.prompt("ClienteQueNaoExiste"), "")

    def test_cliente_vem_do_caminho(self):
        import vocabulario as v
        self.assertEqual(v.cliente_de("/x/clientes/Joao/vegasContent/modelos/a"), "Joao")


class MusicaReprovadaEAssunto(unittest.TestCase):
    def test_assunto_pelas_palavras(self):
        import regras
        self.assertEqual(regras.categoria_do_texto("a música tá clichê"), "audio")
        self.assertEqual(regras.categoria_do_texto("troca esse b-roll"), "broll")
        self.assertEqual(regras.categoria_do_texto("a legenda cobre o queixo"), "legenda")
        self.assertEqual(regras.categoria_do_texto("a cor tá errada"), "layout")
        self.assertEqual(regras.categoria_do_texto("ficou estranho"), "geral")

    def test_musica_reprovada_nao_volta(self):
        import json
        import tempfile
        import musica_busca as mb
        with tempfile.TemporaryDirectory() as td:
            raiz = Path(td); (raiz / "acervo").mkdir()
            (raiz / "acervo/musicas-reprovadas.jsonl").write_text(
                json.dumps({"cliente": "Cliente2", "chave": "k1", "arquivo": "ruim.mp3"}) + "\n")
            antigo = mb._raiz
            mb._raiz = lambda: raiz
            try:
                self.assertEqual(mb.reprovadas("Cliente2"), ({"k1"}, {"ruim.mp3"}))
                self.assertEqual(mb.reprovadas("Outro"), (set(), set()))
            finally:
                mb._raiz = antigo


if __name__ == "__main__":
    unittest.main()
