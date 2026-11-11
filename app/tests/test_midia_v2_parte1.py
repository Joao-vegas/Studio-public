"""midia-v2 parte 1: histórico de uso, rodízio de música/efeito, favoritos. Pasta temporária; sem rede, sem geração paga."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
C = fixtures.C
import musica_busca as MB
import uso_midia as U
import acervo


class Base(fixtures.Isolado):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(MB, "ACERVO", self.root / "acervo/itens"))
        self.stack.enter_context(patch.object(MB, "JOBS", self.jobs))

    def mp3(self, rel, dados):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ID3" + dados * 300)
        return p

    def sandbox(self, nome, faixa, cliente="Ana", modelo="reel"):
        sb = self.root / f"clientes/{cliente}/{cliente.lower()}Content/modelos/{modelo}/_sandbox-{nome}"
        C.gravar_json(sb / "cenas.json", {"musica": {"arquivo": "audio/musica.mp3"}, "efeitos": False})
        self.mp3(f"{sb.relative_to(self.root)}/audio/musica.mp3", faixa)
        return sb


class Historico(Base):
    def test_mesma_faixa_copiada_tem_a_mesma_chave_e_nao_duplica(self):
        a = self.sandbox("v1", b"A")
        b = self.sandbox("v2", b"A")
        self.assertEqual(U.chave_de(a / "audio/musica.mp3"), U.chave_de(b / "audio/musica.mp3"))
        r = U.semear()
        self.assertEqual(r["novas"], 2)
        self.assertEqual(U.semear()["novas"], 0)                       # rodar de novo não duplica
        self.assertEqual(len(U.recentes("Ana", "musica", 8)), 2)
        self.assertEqual(len({u["chave"] for u in U.ler()}), 1)

    def test_registrar_entrega_e_idempotente_e_usa_caminho_relativo(self):
        sb = self.sandbox("v1", b"B")
        self.assertEqual(U.registrar_entrega("Ana", "reel", "reel", "v1", sb), 1)
        self.assertEqual(U.registrar_entrega("Ana", "reel", "reel", "v1", sb), 0)
        self.assertFalse(Path(U.ler()[0]["arquivo"]).is_absolute())


class Rodizio(Base):
    def cenario(self):
        for nome, d in (("usada", b"U"), ("outra", b"O"), ("nova", b"N")):
            self.mp3(f"clientes/Ana/anaContent/modelos/reel/assets/musica/{nome}.mp3", d)
        self.mp3("clientes/Bia/biaContent/modelos/reel/assets/musica/x.mp3", b"X")
        sb = self.sandbox("v1", b"U")
        U.registrar_entrega("Ana", "reel", "reel", "v1", sb)

    def test_faixa_usada_pelo_cliente_some(self):
        self.cenario()
        nomes = [Path(o["arquivo"]).name for o in MB.opcoes("Ana", "", n=5)]
        self.assertNotIn("usada.mp3", nomes)
        self.assertIn("nova.mp3", nomes)

    def test_favorita_usada_na_janela_vai_pro_fim(self):
        self.cenario()
        r = acervo.favoritar_arquivo(self.root / "clientes/Ana/anaContent/modelos/reel/assets/musica/usada.mp3", "Usada", "musica")
        self.assertTrue(r["slug"])
        ops = MB.opcoes("Ana", "", n=5)
        nomes = [Path(o["arquivo"]).name for o in ops]
        self.assertIn("nova.mp3", nomes)
        self.assertNotEqual(nomes[0], "usada.mp3")   # favorita também respeita a janela: não passa na frente das faixas novas

    def test_favoritar_duas_vezes_o_mesmo_arquivo_gera_um_item(self):
        p = self.mp3("clientes/Ana/anaContent/modelos/reel/assets/musica/f.mp3", b"F")
        a = acervo.favoritar_arquivo(p, "F", "musica")
        b = acervo.favoritar_arquivo(p, "F", "musica")
        self.assertEqual(a["slug"], b["slug"])
        self.assertEqual(len(list((self.root / "acervo/itens").iterdir())), 1)
        self.assertEqual([i["slug"] for i in acervo.favoritos("musica")], [a["slug"]])
        acervo.favoritar(a["slug"], ligar=False)
        self.assertEqual(acervo.favoritos("musica"), [])

    def test_uso_em_outro_cliente_cai_pro_fim(self):
        self.mp3("clientes/Ana/anaContent/modelos/reel/assets/musica/comum.mp3", b"C")
        self.mp3("clientes/Ana/anaContent/modelos/reel/assets/musica/livre.mp3", b"L")
        sb = self.sandbox("w1", b"C", cliente="Bia")
        U.registrar_entrega("Bia", "reel", "reel", "w1", sb)
        nomes = [Path(o["arquivo"]).name for o in MB.opcoes("Ana", "", n=5)]
        self.assertEqual(nomes[0], "livre.mp3")
        self.assertEqual(nomes[-1], "comum.mp3")

    def test_efeito_variante_menos_usada(self):
        base = self.root / "formatos/doc/base/audio/sfx"
        self.mp3("formatos/doc/base/audio/sfx/pop/a.mp3", b"1")
        self.mp3("formatos/doc/base/audio/sfx/pop/b.mp3", b"2")
        self.assertIn(MB.sfx_do_papel("pop", "Ana", "j", base).name, ("a.mp3", "b.mp3"))
        self.mp3("formatos/doc/base/audio/sfx/click.mp3", b"3")                  # arquivo solto antigo continua valendo
        self.assertEqual(MB.sfx_do_papel("click", "Ana", "j", base).name, "click.mp3")


class BuscaVariada(Base):
    def test_termos_da_fala_trazem_3_climas(self):
        ts = MB.termos_da_fala("Perdi tudo, foi um erro e um golpe. Mas a virada veio com um método e resultado.", "documentario")
        self.assertGreaterEqual(len(ts), 3)
        self.assertGreaterEqual(len({c for c, _ in ts}), 3)

    def test_buscar_varias_sem_repetir_e_sem_o_que_o_cliente_usou(self):
        def falso(termo, n=8, tipo="musica", pagina=1):
            return {"itens": [{"fonte": "mixkit", "id": str(100 + i), "chave": f"mixkit:{termo}:{i}", "titulo": f"Mixkit {100 + i}"}
                              for i in range(4)] + [{"fonte": "mixkit", "id": "999", "chave": "mixkit:igual", "titulo": "Mixkit 999"}]}
        with patch.object(MB, "buscar_mixkit", side_effect=falso), \
                patch.object(MB, "usadas_recentemente", return_value=[{"arquivo": "audio/101.mp3", "titulo": "101", "chave": ""}]):
            grupos = MB.buscar_varias(MB.termos_da_fala("dor e medo, virada", None), "musica", cliente="Ana", job="j")
        itens = [i for g in grupos for i in g["itens"]]
        self.assertGreaterEqual(len(itens), 6)
        self.assertGreaterEqual(len(grupos), 3)
        self.assertEqual(len({i["chave"] for i in itens}), len(itens))      # sem duplicata ("igual" só uma vez)
        self.assertNotIn("101", [i["id"] for i in itens])                   # a que o cliente usou saiu


class FolhaEApoio(Base):
    def test_folha_de_previa_tem_cabecalho_e_6_quadros(self):
        import subprocess
        import folha_broll as F
        from PIL import Image
        v = self.root / "t.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=4:size=320x180:rate=12", str(v)], check=True)
        saida = F.folha_opcoes([{"video": str(v), "fonte": "youtube", "link": "https://x/y", "de": 1, "ate": 3},
                                {"video": str(v), "fonte": "pexels", "de": 0, "ate": 2}], self.root / "f.jpg")
        with Image.open(saida) as im:
            self.assertEqual(im.width, F.LARGURA)
            self.assertGreater(im.height, 2 * 74)

    def test_politica_de_apoio_no_pedido_da_esteira(self):
        import edicao
        job = {"formato": "fala-com-cenas", "broll_config": {"origem": "busca", "do_formato": True}}
        txt = edicao.instrucao_esteira(job)
        self.assertIn("folha", txt.lower())
        self.assertIn("POLÍTICA DE CENA DE APOIO", txt)
        job["broll_config"] = {"origem": "nenhum", "quantidade": 0}           # o João tirou a cena de apoio
        self.assertEqual(edicao.instrucao_esteira(job), "")
        self.assertEqual(edicao.instrucao_esteira({"formato": "frase-fixa", "broll_config": {"origem": "busca"}}), "")


class Contrato(Base):
    def test_formatos_de_verdade_cumprem_som_e_apoio(self):
        import formatos
        from _comum import RAIZ
        for d in sorted((Path(__file__).resolve().parents[2] / "formatos").iterdir()):
            if d.is_dir() and (d / "formato.json").is_file():
                falta = [x for x in formatos.validar(d.name) if x.startswith(("som.", "apoio", "falta \"apoio")) or "Som e cena" in x]
                self.assertEqual(falta, [], d.name)


class Rotas(Base):
    def test_biblioteca_filtra_favoritos(self):
        a = acervo.favoritar_arquivo(self.mp3("formatos/doc/base/audio/musicas/a.mp3", b"A"), "Faixa amada", "musica")
        self.mp3("formatos/doc/base/audio/musicas/b.mp3", b"B")
        acervo.adicionar_arquivo(self.root / "formatos/doc/base/audio/musicas/b.mp3", "Faixa comum", tags="x", descrever_auto=False)
        html = self.client.get("/acervo?tipo=musica&uso=fav").get_data(as_text=True)
        self.assertIn("Faixa amada", html)
        self.assertNotIn("Faixa comum", html)
        self.assertIn("♥ Favoritos", html)

    def test_andamento_mostra_a_folha_de_previa(self):
        import andamento as A
        j = self.job(status="plano")
        pasta = self.root / j["sandbox"] / "work" / "brolls"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "folha-cena1.jpg").write_bytes(b"\xff\xd8\xff")
        A.registrar("Teste", "video", "Esperando", "esperando", titulo="Meu vídeo")
        html = self.client.get("/andamento/Teste/video").get_data(as_text=True)
        self.assertIn("Prévia das cenas de apoio", html)
        self.assertIn("folha-cena1.jpg", html)

    def test_favoritar_pela_rota_cria_um_item_e_lista(self):
        p = self.mp3("formatos/doc/base/audio/musicas/z.mp3", b"Z")
        for _ in range(2):
            r = self.client.post("/musica/favorito", json={"arquivo": "formatos/doc/base/audio/musicas/z.mp3", "tipo": "musica", "geral": "1"})
            self.assertTrue(r.get_json()["ok"])
        lista = self.client.get("/musica/favoritos?tipo=musica").get_json()
        self.assertEqual(len(lista), 1)
        r = self.client.post("/musica/favorito", json={"arquivo": "../fora.mp3", "tipo": "musica"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
