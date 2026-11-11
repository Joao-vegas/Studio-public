"""Biblioteca mostra TODAS as músicas e efeitos do Estúdio (Biblioteca, formatos, clientes), sem copiar arquivo.
Tudo em pasta temporária; sem rede, sem geração paga."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_v2 as fixtures
C, servidor = fixtures.C, fixtures.servidor
import musica_busca as MB


class Base(fixtures.Isolado):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(MB, "ACERVO", self.root / "acervo/itens"))
        self.stack.enter_context(patch.object(MB, "JOBS", self.jobs))

    def faixa(self, rel_path, dados=b"ID3" + b"\0" * 2048):
        p = self.root / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados)
        return p

    def item_acervo(self, slug, tipo, titulo):
        d = self.root / "acervo/itens" / slug
        d.mkdir(parents=True)
        (d / "clip.mp3").write_bytes(b"ID3" + b"\0" * 64)
        C.gravar_json(d / "meta.json", {"titulo": titulo, "tags": ["calma"], "tipo": tipo, "clima": "calma"})

    def tudo(self):
        self.faixa("formatos/doc/base/audio/musicas/31.mp3")
        self.faixa("formatos/doc/base/audio/musicas/32.mp3")
        self.faixa("formatos/doc/base/audio/sfx/pop.mp3")
        C.gravar_json(self.root / "formatos/doc/base/audio/catalogo.json", {"musicas": [
            {"id": "31", "arquivo": "audio/musicas/31.mp3", "nome": "Calma boa", "clima": "calma", "duracao_s": 110},
            {"id": "32", "arquivo": "audio/musicas/32.mp3", "nome": "Ruim", "status": "rejeitada"}]})
        self.faixa("clientes/Ana/anaContent/modelos/reel/assets/musica/bed-tensao.mp3")
        self.faixa("clientes/Ana/anaContent/modelos/reel/assets/sfx/click.mp3")
        self.faixa("clientes/Ana/anaContent/modelos/reel/assets/musica/tema.mp3")
        self.faixa("clientes/Ana/anaContent/banco-musicas/legado.mp3")   # banco de cliente não é mais fonte: não aparece
        # cópia do formato dentro do cliente: aparece uma vez só (no formato)
        self.faixa("clientes/Ana/anaContent/modelos/reel/assets/musica/31.mp3")
        self.faixa("clientes/Bia/biaContent/modelos/reel/assets/musica/bed-epic.mp3", b"ID3" + b"\0" * 999)
        self.item_acervo("cama-1", "musica", "Cama da Biblioteca")


class FontesDoEstudio(Base):
    def test_junta_biblioteca_formatos_e_clientes_sem_copiar(self):
        self.tudo()
        f = MB.fontes_estudio("musica")
        self.assertEqual([i["titulo"] for i in f["biblioteca"]], ["Cama da Biblioteca"])
        self.assertEqual([(i["titulo"], i["origem_nome"], i["clima"]) for i in f["formatos"]], [("Calma boa", "doc", "calma")])
        self.assertEqual(sorted((i["origem_nome"], Path(i["arquivo"]).name) for i in f["clientes"]),
                         [("Ana", "bed-tensao.mp3"), ("Ana", "tema.mp3"), ("Bia", "bed-epic.mp3")])
        self.assertEqual(next(i["clima"] for i in f["clientes"] if i["arquivo"].endswith("bed-tensao.mp3")), "tensa")
        self.assertEqual(f["formatos"][0]["duracao_txt"], MB._dur_txt(110))
        self.assertEqual(list((self.root / "acervo/itens").iterdir()), [self.root / "acervo/itens/cama-1"])  # nada foi copiado

    def test_efeitos_vem_das_pastas_de_sfx(self):
        self.tudo()
        f = MB.fontes_estudio("sfx")
        self.assertEqual([(i["origem_nome"], i["titulo"], i["tipo"]) for i in f["formatos"]], [("doc", "Pop", "sfx")])
        self.assertEqual([(i["origem_nome"], i["titulo"]) for i in f["clientes"]], [("Ana", "Click")])

    def test_termo_filtra_e_formato_com_mp3_solto_em_audio(self):
        self.tudo()
        self.faixa("formatos/cf/base/audio/33.mp3")
        self.assertEqual([i["titulo"] for i in MB.fontes_estudio("musica", "tensa")["clientes"]], ["Bed tensao"])
        self.assertEqual(MB.fontes_estudio("musica", "tensa")["formatos"], [])
        self.assertEqual([i["origem_nome"] for i in MB.fontes_estudio("musica")["formatos"]], ["cf", "doc"])

    def test_opcoes_comecam_pelo_cliente_depois_biblioteca_depois_formato(self):
        self.tudo()
        self.faixa("clientes/Teste/testeContent/modelos/estilo/assets/musica/bed-um.mp3")
        ops = MB.opcoes("Teste", "", n=3, formato="doc")
        self.assertEqual([o["fonte"] for o in ops], ["cliente", "biblioteca", "formato"])


class TelaBiblioteca(Base):
    def test_aba_musicas_lista_tudo_com_player_e_filtra_por_fonte(self):
        self.tudo()
        h = self.client.get("/acervo?tipo=musica").get_data(as_text=True)
        for t in ("Cama da Biblioteca", "Calma boa", "Bed tensao", "Bed epic", "Nos estilos", "Nos clientes"):
            self.assertIn(t, h)
        self.assertIn("/arquivo/formatos/doc/base/audio/musicas/31.mp3", h)
        h2 = self.client.get("/acervo?tipo=musica&fonte=formatos").get_data(as_text=True)
        self.assertIn("Calma boa", h2)
        self.assertNotIn("Bed tensao", h2)
        self.assertNotIn("Cama da Biblioteca", h2)
        h3 = self.client.get("/acervo?tipo=sfx&q=click").get_data(as_text=True)
        self.assertIn("Click", h3)
        self.assertNotIn("Pop", h3)

    def test_aba_tudo_resume_o_que_tem_fora(self):
        self.tudo()
        h = self.client.get("/acervo?tipo=").get_data(as_text=True)   # "tipo=" vazio = Tudo (sem isso a Biblioteca abre em Vídeos)
        self.assertIn("Tem mais no Estúdio fora da Biblioteca", h)

    def test_busca_de_musica_mostra_cliente_biblioteca_e_formato_nessa_ordem(self):
        self.tudo()
        j = self.job("plano")
        j["formato"] = "doc"
        fixtures.P.salvar(j)
        h = self.client.get("/musica?job=Teste/video").get_data(as_text=True)
        self.assertEqual(h.count("Na sua Biblioteca"), 1)
        self.assertLess(h.index("Na sua Biblioteca"), h.index("que vêm com o formato"))
        self.assertIn("Calma boa", h)
        self.assertIn("Cama da Biblioteca", h)


if __name__ == "__main__":
    unittest.main()
