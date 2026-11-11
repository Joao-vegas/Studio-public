"""Espaço: cópia por clone (com volta pra cópia normal), desduplicar, Lixeira do Mac, apagar leva tudo do vídeo
(inclusive o upload dele) e a tela Liberar espaço (o que entra, o que nunca entra, aviso de editar por cena)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import _comum
import espaco as E
import andamento  # noqa: F401
import producao  # noqa: F401
import saidas as S

VELHO = time.time() - 10 * 86400     # mais velho que a janela de 7 dias do Liberar espaço


def velho(p: Path):
    for q in [p, *p.rglob("*")]:
        os.utime(q, (VELHO, VELHO))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = self.raiz = Path(self.tmp.name).resolve()
        for alvo, valor in (("saidas.RAIZ", raiz), ("andamento.RAIZ", raiz), ("_comum.RAIZ", raiz), ("_comum.ESTUDIO", raiz / "app"),
                            ("_comum.JOBS", raiz / "app" / "jobs"), ("producao.JOBS", raiz / "app" / "jobs"), ("producao.RAIZ", raiz)):
            m, a = alvo.split(".")
            p = patch.object(sys.modules[m], a, valor)
            p.start()
            self.addCleanup(p.stop)
        self.lixo = raiz / ".Trash-teste"

    def video(self, slug="v1", cli="Joao", modelo="analise-de-tela", cenas=False, pronto=True):
        c = self.raiz / "clientes" / cli / "xContent"
        sb = c / "modelos" / modelo / f"_sandbox-{slug}"
        (sb / "work").mkdir(parents=True)
        (sb / "work" / "joao.mp4").write_bytes(b"w" * 2_000_000)
        (sb / "work" / "words.json").write_text("{}")
        (sb / "quadros").mkdir()
        (sb / "quadros" / "q.png").write_bytes(b"q" * 1_500_000)
        (sb / "bruto").mkdir()
        (sb / "bruto" / "b.mp4").write_bytes(b"b" * 3_000_000)
        (sb / "editor" / "versoes" / "v1").mkdir(parents=True)
        (sb / "editor" / "versoes" / "v1" / "video-v1.mp4").write_bytes(b"e" * 1_200_000)
        (sb / "PLANO.json").write_text("{}")
        if cenas:
            (sb / "cenas.json").write_text("{}")
        out = c / "output" / modelo
        out.mkdir(parents=True, exist_ok=True)
        if pronto:
            (out / f"{slug}.mp4").write_bytes(b"f" * 4_000_000)
        velho(sb)
        jd = self.raiz / "app" / "jobs" / cli / slug
        jd.mkdir(parents=True)
        (jd / "job.json").write_text(json.dumps({"slug": slug, "titulo": slug.upper(), "cliente": cli, "modelo": modelo,
                                                 "status": "concluido" if pronto else "analisando",
                                                 "sandbox": str(sb.relative_to(self.raiz)), "bruto": str((sb / "bruto" / "b.mp4").relative_to(self.raiz)),
                                                 "saida": str((out / f"{slug}.mp4").relative_to(self.raiz)) if pronto else None}))
        velho(jd)
        if pronto:
            velho(out / f"{slug}.mp4")
        return sb, out / f"{slug}.mp4", jd


class Clonar(Base):
    def test_clone_tem_o_mesmo_conteudo_e_a_mesma_data(self):
        a = self.raiz / "a.mp4"
        a.write_bytes(b"x" * 100_000)
        os.utime(a, (VELHO, VELHO))
        r = _comum.clonar(a, self.raiz / "sub" / "b.mp4")
        self.assertIn(r, ("clone", "copia"))
        self.assertEqual((self.raiz / "sub" / "b.mp4").read_bytes(), a.read_bytes())
        self.assertAlmostEqual((self.raiz / "sub" / "b.mp4").stat().st_mtime, VELHO, delta=2)

    def test_sem_apfs_cai_pra_copia_normal(self):
        a = self.raiz / "a.mp4"
        a.write_bytes(b"x" * 1000)
        falha = type("R", (), {"returncode": 1, "stderr": b"nao"})()
        with patch("subprocess.run", return_value=falha):
            self.assertEqual(_comum.clonar(a, self.raiz / "b.mp4"), "copia")
        self.assertEqual((self.raiz / "b.mp4").read_bytes(), a.read_bytes())

    def test_destino_existente_e_trocado(self):
        a, b = self.raiz / "a.bin", self.raiz / "b.bin"
        a.write_bytes(b"novo")
        b.write_bytes(b"velho velho")
        _comum.clonar(a, b)
        self.assertEqual(b.read_bytes(), b"novo")


class Desduplicar(Base):
    def test_copia_identica_vira_clone_e_diferente_fica(self):
        d = self.raiz / "clientes" / "J" / "xContent"
        (d / "output").mkdir(parents=True)
        (d / "w").mkdir()
        conteudo = os.urandom(300_000)
        orig, copia, outro = d / "output" / "a.mp4", d / "w" / "a-copia.mp4", d / "w" / "outro.mp4"
        orig.write_bytes(conteudo)
        copia.write_bytes(conteudo)
        outro.write_bytes(os.urandom(300_000))
        for p in (orig, copia, outro):
            os.utime(p, (VELHO, VELHO))
        antes = E.desduplicar(base=self.raiz, minimo=100_000)
        self.assertEqual((antes["grupos"], antes["copias"], antes["feitos"]), (1, 1, 0))     # só mede
        r = E.desduplicar(aplicar=True, base=self.raiz, minimo=100_000)
        self.assertEqual((r["feitos"], r["erros"]), (1, []))
        self.assertEqual(copia.read_bytes(), conteudo)
        self.assertEqual(orig.read_bytes(), conteudo)
        self.assertNotEqual(outro.read_bytes(), conteudo)
        self.assertAlmostEqual(copia.stat().st_mtime, VELHO, delta=2)
        self.assertEqual(E.desduplicar(base=self.raiz, minimo=100_000)["copias"], 0)         # já virou clone: não conta de novo

    def test_arquivo_mexido_agora_nao_e_tocado(self):
        d = self.raiz / "x"
        d.mkdir()
        c = os.urandom(200_000)
        (d / "a.mp4").write_bytes(c)
        (d / "b.mp4").write_bytes(c)             # data de agora: pode estar sendo escrito
        r = E.desduplicar(aplicar=True, base=self.raiz, minimo=100_000)
        self.assertEqual(r["feitos"], 0)


class LixeiraMac(Base):
    def test_move_mantendo_o_caminho_e_recusa_fora_do_estudio(self):
        (self.raiz / "app" / "jobs").mkdir(parents=True)
        f = self.raiz / "app" / "jobs" / "x.txt"
        f.write_text("oi")
        r = E.para_lixeira_mac([f], "Meu vídeo")
        self.assertFalse(f.exists())
        self.assertTrue((Path(r["pasta"]) / "app" / "jobs" / "x.txt").is_file())
        self.assertTrue(r["nome"].startswith("meu-video-"))
        fora = Path(self.tmp.name).parent / "fora.txt"
        with self.assertRaises(ValueError):
            E.para_lixeira_mac([fora], "x")

    def test_atalho_nunca_vai(self):
        real = self.raiz / "real"
        real.mkdir()
        (self.raiz / "atalho").symlink_to(real)
        with self.assertRaises(ValueError):
            E.para_lixeira_mac([self.raiz / "atalho"], "x")


class ApagarVideo(Base):
    def test_apagar_leva_tudo_dele_inclusive_o_upload_e_o_resto_fica(self):
        sb, mp4, jd = self.video("v1")
        outro_sb, outro_mp4, _ = self.video("v2")
        up = self.raiz / "app" / ".uploads"
        up.mkdir(parents=True)
        (up / "20261029-000000-b.mp4").write_bytes(b"b" * 3_000_000)      # o bruto que ele usou
        (up / "20261029-000001-outro.mp4").write_bytes(b"z" * 3_000_001)  # de outro vídeo
        velho(up)
        medido = E.tamanho_video("Joao", "v1")
        self.assertGreater(medido["bytes"], 9_000_000)
        self.assertTrue(sb.exists())                                      # medir não mexe em nada
        r = S.apagar_video("Joao", "v1")
        self.assertTrue(r["apagados"], r)
        self.assertFalse(sb.exists() or mp4.exists() or jd.exists())
        self.assertFalse((up / "20261029-000000-b.mp4").exists())
        self.assertTrue((up / "20261029-000001-outro.mp4").exists())
        self.assertTrue(outro_sb.exists() and outro_mp4.exists())
        pasta = Path(r["apagados"][0]["lixeira_mac"])
        self.assertTrue(pasta.parent == self.lixo and (pasta / "app" / ".uploads" / "20261029-000000-b.mp4").is_file())
        self.assertIn("Lixeira do Mac", S.mensagem(r))

    def test_video_so_com_mp4_no_output_leva_o_mp4_e_o_rascunho(self):
        sb, mp4, jd = self.video("feito-pelo-chat")
        import shutil
        shutil.rmtree(jd)                                                 # sem job, como o que o chat fez
        r = E.lote(caminhos=[str(mp4.relative_to(self.raiz))])
        self.assertEqual(r["apagados"], 1, r)
        self.assertFalse(mp4.exists() or sb.exists())

    def test_lote_mede_sem_apagar(self):
        sb, mp4, _ = self.video("v1")
        r = E.lote(["Joao/v1"], medir=True)
        self.assertEqual(r["apagados"], 1)
        self.assertTrue(sb.exists() and mp4.exists())


class LiberarEspaco(Base):
    def itens(self, slug="v1"):
        x = E.itens_liberaveis()
        return {i["tipo"]: i for g in x["grupos"] for v in g["videos"] if v["slug"] == slug for i in v["itens"]}

    def test_oferece_work_e_quadros_e_nunca_o_pronto_nem_as_versoes(self):
        sb, mp4, _ = self.video("v1")
        its = self.itens()
        self.assertEqual(set(its), {"work", "quadros", "bruto"})
        self.assertFalse(its["bruto"]["marcado"])                         # o bruto é do João: nunca vem marcado
        self.assertEqual(its["work"]["caminhos"], ["clientes/Joao/xContent/modelos/analise-de-tela/_sandbox-v1/work/joao.mp4"])
        todos = {c for i in its.values() for c in i["caminhos"]}
        self.assertFalse(any("output" in c or "editor" in c or c.endswith(".json") for c in todos))

    def test_todo_item_do_video_avisa_que_nao_edita_mais(self):
        self.video("v1")
        for tipo, it in self.itens().items():
            self.assertIn("não dá mais pra editar nem refazer", it["aviso"], tipo)   # em português simples, em cada item
            self.assertIn("o vídeo pronto continua", it["aviso"], tipo)

    def test_video_ainda_em_producao_nao_entra(self):
        self.video("v1", pronto=False)
        self.assertEqual(self.itens(), {})

    def test_liberar_manda_pra_lixeira_do_mac_so_o_marcado(self):
        sb, mp4, _ = self.video("v1")
        its = self.itens()
        r = E.liberar([its["work"]["id"], its["quadros"]["id"]])
        self.assertFalse((sb / "work" / "joao.mp4").exists())
        self.assertTrue((sb / "work" / "words.json").exists())            # json de texto fica
        self.assertTrue(mp4.exists() and (sb / "bruto" / "b.mp4").exists() and (sb / "editor" / "versoes" / "v1" / "video-v1.mp4").exists())
        self.assertTrue(Path(r["pasta"]).parent == self.lixo)
        with self.assertRaises(ValueError):
            E.liberar(["inventado"])                                      # caminho nunca vem do navegador

    def test_upload_ja_usado_vem_marcado_e_o_sem_uso_nao(self):
        sb, _, _ = self.video("v1")
        up = self.raiz / "app" / ".uploads"
        up.mkdir(parents=True)
        (up / "usado.mp4").write_bytes(b"b" * 3_000_000)                  # igual ao bruto do rascunho
        (up / "sozinho.mp4").write_bytes(b"s" * 3_000_001)
        velho(up)
        g = next(g for g in E.itens_liberaveis()["grupos"] if g["nome"].startswith("Envios"))
        marcado = {i["caminhos"][0]: i["marcado"] for v in g["videos"] for i in v["itens"]}
        self.assertTrue(marcado["app/.uploads/usado.mp4"])
        self.assertFalse(marcado["app/.uploads/sozinho.mp4"])


class Protecao(Base):
    """Nunca oferece mídia de vídeo esperando o João, em produção ou editado nos últimos 7 dias."""
    def itens(self, slug="v1"):
        x = E.itens_liberaveis()
        return {i["tipo"] for g in x["grupos"] for v in g["videos"] if v["slug"] == slug for i in v["itens"]}

    def registrar(self, cli, slug, estado):
        import andamento
        p = self.raiz / "app" / ".andamento" / cli
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{slug}.json").write_text(json.dumps({"cliente": cli, "slug": slug, "estado": estado, "origem": "tela", "video": "x.mp4",
                                                    "atualizado": "2020-01-01 00:00:00"}))
        return p

    def test_esperando_aprovacao_nao_entra(self):
        self.video("v1")
        self.assertTrue(self.itens())                                                # sozinho entra
        with patch.object(E, "_esperando_aprovacao", return_value={("Joao", "v1")}):
            self.assertEqual(self.itens(), set())

    def test_registro_esperando_ou_pronto_tambem_protege_mesmo_sem_lotes(self):
        import andamento
        self.video("v1")
        reg = {"cliente": "Joao", "slug": "v1", "estado": "esperando"}
        with patch("andamento.registros", side_effect=lambda: iter([reg])), patch("lotes.esperando", side_effect=RuntimeError("x")):
            self.assertEqual(E._esperando_aprovacao(), {("Joao", "v1")})
            self.assertEqual(self.itens(), set())

    def test_editado_nos_ultimos_7_dias_nao_entra(self):
        sb, mp4, jd = self.video("v1")
        self.assertTrue(self.itens())
        recente = time.time() - 2 * 86400
        os.utime(sb / "editor" / "versoes", (recente, recente))                      # uma edição por cena há 2 dias
        self.assertEqual(self.itens(), set())
        os.utime(sb / "editor" / "versoes", (VELHO, VELHO))
        os.utime(sb, (VELHO, VELHO))
        self.assertTrue(self.itens())
        os.utime(mp4, (recente, recente))                                            # re-renderizou o pronto há 2 dias
        self.assertEqual(self.itens(), set())

    def test_upload_do_video_protegido_tambem_fica(self):
        sb, _, _ = self.video("v1")
        up = self.raiz / "app" / ".uploads"
        up.mkdir(parents=True)
        (up / "b.mp4").write_bytes(b"b" * 3_000_000)
        velho(up)
        nomes = lambda: {i["caminhos"][0] for g in E.itens_liberaveis()["grupos"] if g["nome"].startswith("Envios") for v in g["videos"] for i in v["itens"]}
        self.assertIn("app/.uploads/b.mp4", nomes())
        with patch.object(E, "_esperando_aprovacao", return_value={("Joao", "v1")}):
            self.assertNotIn("app/.uploads/b.mp4", nomes())


class FinderFalso(Base):
    """Lixeira falsa (ESTUDIO_LIXEIRA_MAC) e Finder simulado: o Terminal de verdade não lê ~/.Trash, só o Finder."""
    def setUp(self):
        super().setUp()
        self.lixo.mkdir(parents=True, exist_ok=True)
        for alvo, fn in (("_finder_listar", self.listar), ("_finder_mover", self.mover), ("_finder_tamanho", lambda p: 123)):
            p = patch.object(E, alvo, fn)
            p.start()
            self.addCleanup(p.stop)
        self.movimentos = []

    def listar(self, pasta):
        pasta = Path(pasta)
        if not pasta.is_dir():
            return None
        return [(q.name, q.is_dir()) for q in sorted(pasta.iterdir())]

    def mover(self, origem, destino):
        import shutil
        origem, destino = Path(origem), Path(destino)
        if not origem.exists() or not destino.is_dir() or (destino / origem.name).exists():
            return False                                                             # o Finder também não troca o que existe
        shutil.move(str(origem), str(destino / origem.name))
        self.movimentos.append(origem.name)
        return True


class DesfazerLimpeza(FinderFalso):
    def liberar_work(self, slug="v1"):
        self.video(slug)
        its = {i["tipo"]: i for g in E.itens_liberaveis()["grupos"] for v in g["videos"] if v["slug"] == slug for i in v["itens"]}
        return E.liberar([its["work"]["id"], its["quadros"]["id"]])

    def test_liberar_grava_manifesto_com_a_pasta_e_os_caminhos_relativos(self):
        r = self.liberar_work()
        m = E.ultima_limpeza()
        self.assertEqual(m["pasta"], r["pasta"])
        self.assertEqual(set(m["caminhos"]), set(r["rels"]))
        self.assertTrue(all(not c.startswith("/") for c in m["caminhos"]))
        self.assertTrue((self.raiz / "app" / ".cache" / "limpezas").glob("*.json"))
        self.assertIsNone(m["desfeito"])

    def test_desfazer_devolve_tudo_pro_mesmo_lugar(self):
        r = self.liberar_work()
        sb = self.raiz / "clientes" / "Joao" / "xContent" / "modelos" / "analise-de-tela" / "_sandbox-v1"
        self.assertFalse((sb / "work" / "joao.mp4").exists())
        d = E.desfazer_limpeza()
        self.assertTrue((sb / "work" / "joao.mp4").is_file())
        self.assertTrue((sb / "quadros" / "q.png").is_file())
        self.assertGreaterEqual(d["devolvidos"], 1)
        self.assertEqual((d["ficaram"], d["sumiram"]), (0, 0))
        self.assertIsNone(E.ultima_limpeza())                                        # já desfeita: o botão some
        with self.assertRaises(ValueError):
            E.desfazer_limpeza()

    def test_pasta_com_pasta_junta_sem_substituir_o_que_existe(self):
        self.liberar_work()
        sb = self.raiz / "clientes" / "Joao" / "xContent" / "modelos" / "analise-de-tela" / "_sandbox-v1"
        (sb / "work").mkdir(exist_ok=True)
        (sb / "work" / "joao.mp4").write_bytes(b"NOVO")                              # alguém refez o arquivo no meio tempo
        d = E.desfazer_limpeza()
        self.assertEqual((sb / "work" / "joao.mp4").read_bytes(), b"NOVO")           # não foi trocado
        self.assertEqual(d["ficaram"], 1)
        self.assertTrue((sb / "quadros" / "q.png").is_file())                        # o que não existia voltou

    def test_ja_devolvido_a_mao_conta_como_sumiu_e_nao_quebra(self):
        r = self.liberar_work()
        import shutil
        shutil.rmtree(Path(r["pasta"]))                                              # Lixeira esvaziada
        d = E.desfazer_limpeza()
        self.assertEqual(d["devolvidos"], 0)
        self.assertGreaterEqual(d["sumiram"], 1)

    def test_manifesto_de_limpeza_antiga_sem_devolver_nada(self):
        antiga = self.lixo / "liberar-espaco-2026-10-30-140914"
        (antiga / "clientes" / "Cliente1" / "mContent" / "x").mkdir(parents=True)
        (antiga / "clientes" / "Cliente1" / "mContent" / "x" / "a.mp4").write_bytes(b"a" * 10)
        arq = E.manifesto_legado(antiga)
        self.assertEqual(arq.name, "2026-10-30-140914.json")
        m = E.ultima_limpeza()
        self.assertEqual((m["pasta"], m["caminhos"], m["itens"]), (str(antiga), ["clientes"], 1))
        self.assertEqual(self.movimentos, [])                                        # só montou o manifesto: nada foi devolvido
        self.assertTrue((antiga / "clientes" / "Cliente1" / "mContent" / "x" / "a.mp4").exists())
        E.desfazer_limpeza()                                                         # e quando o botão for apertado, devolve
        self.assertTrue((self.raiz / "clientes" / "Cliente1" / "mContent" / "x" / "a.mp4").is_file())

    def test_caminho_com_ponto_ponto_nunca_sai_do_estudio(self):
        antiga = self.lixo / "liberar-espaco-2026-01-01-000000"
        antiga.mkdir()
        E.gravar_manifesto(antiga, ["../fora"])
        d = E.desfazer_limpeza()
        self.assertEqual(d["ignorados"], 1)
        self.assertFalse((self.raiz.parent / "fora").exists())


class FinderPrimitivas(unittest.TestCase):
    """O Finder de verdade, numa pasta temporária (não a Lixeira): lista com nome acentuado e move sem trocar."""
    @unittest.skipUnless(sys.platform == "darwin", "só no Mac")
    def test_listar_e_mover_de_verdade(self):
        with tempfile.TemporaryDirectory(prefix="estudio-finder-") as t:
            base = Path(t).resolve()
            (base / "Estúdio" / "pasta ç").mkdir(parents=True)
            (base / "Estúdio" / "pasta ç" / "a b.txt").write_text("oi")
            (base / "dest").mkdir()
            lista = E._finder_listar(base / "Estúdio")
            if lista is None:
                self.skipTest("o Finder não respondeu aqui")
            self.assertEqual(lista, [("pasta ç", True)])
            self.assertTrue(E._finder_mover(base / "Estúdio" / "pasta ç", base / "dest"))
            self.assertTrue((base / "dest" / "pasta ç" / "a b.txt").is_file())
            self.assertFalse(E._finder_mover(base / "nao-existe", base / "dest"))


if __name__ == "__main__":
    unittest.main()
