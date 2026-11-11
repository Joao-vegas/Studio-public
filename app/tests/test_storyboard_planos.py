"""Tira 'Momento a momento': todos os planos, quadro do meio, rótulo de verdade, agrupamento por tipo. Nada pago."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import storyboard_estilo as sb  # noqa: E402


def estudo(planos, trans=(), numeros=(), fps=25.0, mediana=1.0):
    """planos: [(q, q_fim)]; trans: [(q, tipo, quadros)]."""
    lista = [{"q": a, "q_fim": b, "s": round(a / fps, 2), "dura_s": round((b - a + 1) / fps, 2)} for a, b in planos]
    return {"fps": fps, "duracao": (planos[-1][1] + 1) / fps,
            "planos": {"n": len(lista), "por_min": 40.0, "media_s": 1.5, "mediana_s": mediana, "lista": lista},
            "transicoes": [{"q": q, "q_fim": q + n - 1, "quadros": n, "tipo": t, "s": round(q / fps, 3)} for q, t, n in trans],
            "numeros": list(numeros), "camera": {"pct_quadros_andando": 88.0}}


# 0-3,4 s abertura · corte · especial (4 quadros) · dissolve · rajada · longa (12 s) · corte
V = estudo([(0, 85), (86, 120), (121, 160), (161, 200), (201, 203), (204, 503), (504, 540)],
           trans=[(86, "corte", 1), (121, "especial", 4), (161, "dissolve", 5), (201, "corte", 1), (204, "corte", 1), (504, "corte", 1)],
           numeros=[{"s": 20.5, "texto": "22 por cento", "evento": True}])


class Meio(unittest.TestCase):
    def test_quadro_do_meio_nunca_o_do_corte(self):
        self.assertEqual(sb.meio({"q": 86, "q_fim": 120}), 103)
        self.assertEqual(sb.meio({"q": 319, "q_fim": 319}), 319)
        for p in V["planos"]["lista"]:
            if p["q_fim"] > p["q"]:
                self.assertTrue(p["q"] < sb.meio(p) <= p["q_fim"])


class Rotulos(unittest.TestCase):
    def setUp(self):
        self.it = sb.classificar(V)

    def test_um_item_por_plano_na_ordem_do_video(self):
        self.assertEqual(len(self.it), 7)
        self.assertEqual([i["t"] for i in self.it], sorted(i["t"] for i in self.it))
        self.assertEqual(self.it[0]["tipo"], "abertura")
        self.assertIn("abertura: cena de 3,4", self.it[0]["legenda"])

    def test_tipo_vem_da_transicao_de_entrada(self):
        t = [i["tipo"] for i in self.it]
        self.assertEqual(t[1], "corte")
        self.assertEqual(t[2], "especial")
        self.assertEqual(t[3], "dissolve")
        self.assertEqual(t[4], "rajada")
        self.assertEqual(t[5], "longa")
        self.assertEqual(t[6], "numero")
        self.assertIn("transição especial (4", self.it[2]["legenda"])
        self.assertIn("dissolve de 5", self.it[3]["legenda"])
        self.assertIn("cena longa", self.it[5]["legenda"])

    def test_nenhum_rotulo_generico_nem_repetido_sem_dado(self):
        self.assertFalse(any("um momento do vídeo" in i["legenda"] for i in self.it))
        self.assertEqual(sb.rotulo_tipo("corte"), "corte seco")
        self.assertEqual(sb.rotulo_tipo("peca:frase"), "peça: frase")

    def test_numero_falado_e_texto_da_tela(self):
        v = estudo([(0, 85), (86, 160), (161, 200)], trans=[(86, "corte", 1), (161, "corte", 1)],
                   numeros=[{"s": 4.0, "texto": "157 mil", "evento": False}])
        it = sb.classificar(v, ocr={sb.meio(v["planos"]["lista"][2]): "Placa de trânsito"})
        self.assertEqual(it[1]["tipo"], "numero")
        self.assertEqual(it[1]["fala"], "157 mil")
        self.assertEqual(it[2]["tipo"], "texto")
        self.assertEqual(it[2]["fala"], "Placa de trânsito")

    def test_peca_do_motor_quando_ha_cenas(self):
        it = sb.classificar(V, pecas=[(0.0, "frase"), (3.4, "recorte"), (8.0, "card")])
        self.assertEqual([i["tipo"] for i in it[:3]], ["peca:frase", "peca:recorte", "peca:recorte"])
        self.assertEqual(it[6]["tipo"], "peca:card")
        self.assertEqual({t["rotulo"]: t["n"] for t in sb.resumir(it, V)["tipos"]}, {"peça: frase": 1, "peça: recorte": 3, "peça: card": 3})


class Agrupamento(unittest.TestCase):
    def test_resumo_conta_por_tipo_com_numeros_da_regua(self):
        it = [dict(i, arquivo=f"{i['i']}.jpg") for i in sb.classificar(V)]
        r = sb.resumir(it, V)
        conta = {t["tipo"]: t["n"] for t in r["tipos"]}
        self.assertEqual(conta["corte"], 1)
        self.assertEqual(conta["numero"], 1)            # o 7º plano tem o número falado
        self.assertEqual(conta["abertura"], 1)
        self.assertEqual(sum(conta.values()), 7)
        self.assertTrue(all(t["exemplo"] for t in r["tipos"]))
        self.assertEqual([n["rotulo"] for n in r["numeros"]], ["cortes por minuto", "duração média do plano", "do tempo com a câmera andando"])
        self.assertEqual(r["numeros"][2]["valor"], "88%")

    def test_ate_o_limite_mostra_todos(self):
        it = sb.destacar(sb.classificar(V))
        self.assertTrue(all(i["destaque"] for i in it))

    def test_passou_do_limite_mantem_os_20_primeiros_segundos_e_amostra_o_resto_por_tipo(self):
        # 200 planos de 0,5 s (12 quadros): 40 nos primeiros 20 s; do resto, 1 especial e 1 dissolve raros no meio
        pl = [(k * 12, k * 12 + 11) for k in range(200)]
        tr = [(a, "corte", 1) for a, _ in pl[1:]]
        tr[99] = (pl[100][0], "especial", 4)
        tr[149] = (pl[150][0], "dissolve", 5)
        v = estudo(pl, trans=tr, mediana=0.5)
        it = sb.destacar(sb.classificar(v), limite=60)
        vis = [i for i in it if i["destaque"]]
        self.assertLessEqual(len(vis), 62)
        self.assertGreater(len(vis), 40)
        self.assertTrue(all(i["destaque"] for i in it if i["t"] < 20))
        self.assertTrue(any(i["tipo"] == "especial" and i["destaque"] for i in it))      # o raro não some
        self.assertTrue(any(i["tipo"] == "dissolve" and i["destaque"] for i in it))
        depois = [i["t"] for i in vis if i["t"] >= 20]
        self.assertGreater(max(depois), 80)                                              # espalhado até o fim, não só o começo


class Ocr(unittest.TestCase):
    def test_texto_que_repete_na_mesma_altura_e_legenda_nao_e_peca(self):
        lidos = {q: [("legenda", 62.0), ("fala", 62.5)] for q in range(10)}              # legenda fixa em todo plano
        lidos[3] = [("legenda", 62.0), ("PLACAR", 20.0), ("HISTÓRICO", 21.0)]            # texto de verdade, noutra altura
        lidos[5] = [("ruim", 20.0)]                                                       # 1 palavra curta: ruído
        r = sb.limpar_ocr(lidos)
        self.assertEqual(list(r), [3])
        self.assertEqual(r[3], "PLACAR HISTÓRICO")


class Cenas(unittest.TestCase):
    def test_le_o_tipo_da_peca_do_cenas_json_ao_lado_do_video(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "video.mp4"
            v.write_bytes(b"x")
            self.assertEqual(sb.pecas_do_cenas(v), [])
            (Path(d) / "cenas.json").write_text(json.dumps({"cenas": [{"tipo": "recorte", "de": 1.85}, {"tipo": "frase", "de": 0}, {"de": 5}]}))
            self.assertEqual(sb.pecas_do_cenas(v), [(0.0, "frase"), (1.85, "recorte")])


class Arquivos(unittest.TestCase):
    def test_caminho_com_ref_recusa_nome_de_fora(self):
        for slug, nome, ref in (("editorial", "a.jpg", "../x"), ("editorial", "../a.jpg", "x"), ("editorial", "a.jpg", ".."), ("editorial", "a/b.jpg", "x")):
            self.assertIsNone(sb.caminho(slug, nome, ref))

    def test_sem_video_nao_quebra(self):
        self.assertEqual(sb.tira("nao-existe-esse-estilo")["estado"], "sem")
        self.assertEqual(sb.tira("../etc")["quadros"], [])


if __name__ == "__main__":
    unittest.main()
