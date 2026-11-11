"""Saídas: listar, apagar (com trava de caminho), referência protegida em lote e registro em apagados.jsonl.
Tudo numa pasta temporária; o formatos.referencia é trocado por um falso (nada copia pra formatos/ de verdade)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "interface"))
import _comum
import andamento as A
import producao as P
import saidas as S

CONTENT = {"Joao": "vegasContent", "Cliente2": "marca2Content"}


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
        self.out_j = raiz / "clientes/Joao/vegasContent/output"
        self.ep = self.out_j / "dialogo-3d" / "ep1"
        self.ep.mkdir(parents=True)
        (self.ep / "folha.jpg").write_bytes(b"j" * 1000)
        (self.ep / "quadros").mkdir()
        (self.ep / "quadros" / "q1.png").write_bytes(b"p" * 2000)
        (self.out_j / "dialogo-3d" / "ep1.mp4").write_bytes(b"v" * 500)
        (self.out_j / "dialogo-3d" / "solto.mp4").write_bytes(b"v" * 300)
        (self.out_j / "dialogo-3d" / "notas.txt").write_text("não é vídeo")
        self.ref = raiz / "clientes/Cliente2/marca2Content/output/dividido-mascara/ref1"
        self.ref.mkdir(parents=True)
        (self.ref / "REFERENCIA.json").write_text(json.dumps({"formato": "fala-com-cenas", "motivo": "ritmo"}))
        (self.ref.parent / "ref1.mp4").write_bytes(b"v" * 700)
        self.fora = raiz / "clientes/Joao/vegasContent/material"
        self.fora.mkdir(parents=True)
        (self.fora / "bruto.mp4").write_bytes(b"b" * 100)
        self.log = raiz / "app/custos/apagados.jsonl"

    def r(self, p: Path) -> str:
        return str(p.relative_to(self.raiz))

    def jobdir(self, cli, slug) -> Path:
        return self.raiz / "app/jobs" / cli / slug

    def _job(self, cli, slug, modelo, status="aprovado", saida=None, **extra) -> Path:
        """Cria app/jobs/<cli>/<slug>/job.json (saída padrão: output/<modelo>/<slug>.mp4) e devolve a pasta do job."""
        c = f"clientes/{cli}/{CONTENT[cli]}"
        d = self.jobdir(cli, slug)
        d.mkdir(parents=True, exist_ok=True)
        job = {"slug": slug, "titulo": slug.upper(), "cliente": cli, "modelo": modelo, "status": status, "criado_em": "2026-10-10 00:00:00",
               "sandbox": f"{c}/modelos/{modelo}/_sandbox-{slug}", "saida": saida or f"{c}/output/{modelo}/{slug}.mp4",
               "versoes": [], **extra}
        (d / "job.json").write_text(json.dumps(job))
        (d / "log.txt").write_text("x" * 50)
        return d

    def registros(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []


class Listar(Base):
    def test_lista_pasta_e_mp4_como_um_so_com_tamanho_e_referencia(self):
        itens = {i["slug"]: i for i in S.listar()}
        self.assertEqual(set(itens), {"ep1", "solto", "ref1"})
        ep = itens["ep1"]
        self.assertEqual((ep["cliente"], ep["modelo"], ep["bytes"]), ("Joao", "dialogo-3d", 3500))
        self.assertEqual((ep["pasta"], ep["video"], ep["folha"]),
                         (self.r(self.ep), self.r(self.ep.parent / "ep1.mp4"), self.r(self.ep / "folha.jpg")))
        self.assertIsNone(ep["referencia"])
        self.assertEqual(itens["ref1"]["referencia"]["formato"], "fala-com-cenas")
        self.assertEqual((itens["solto"]["pasta"], itens["solto"]["bytes"]), ("", 300))
        self.assertEqual([i["slug"] for i in S.listar("Cliente2")], ["ref1"])
        self.assertEqual(S.total(list(itens.values())), 0.0)   # 4,5 kB arredonda pra 0,0 MB


class Apagar(Base):
    def test_apaga_pasta_e_mp4_e_registra(self):
        r = S.apagar([self.r(self.ep)])
        self.assertEqual([i["slug"] for i in r["apagados"]], ["ep1"])
        self.assertFalse(self.ep.exists())
        self.assertFalse((self.ep.parent / "ep1.mp4").exists())
        self.assertTrue((self.ep.parent / "solto.mp4").exists())
        reg = self.registros()
        self.assertEqual(len(reg), 1)
        self.assertEqual((reg[0]["cliente"], reg[0]["slug"], reg[0]["video"], reg[0]["referencia"]),
                         ("Joao", "ep1", "clientes/Joao/vegasContent/output/dialogo-3d/ep1.mp4", False))
        self.assertIn("quando", reg[0])

    def test_apagar_pelo_mp4_leva_a_pasta_junto(self):
        S.apagar([self.r(self.ep.parent / "ep1.mp4")])
        self.assertFalse(self.ep.exists())

    def test_referencia_nunca_sai_em_lote(self):
        r = S.apagar([self.r(self.ep), self.r(self.ref)], confirmar=True)
        self.assertEqual([i["slug"] for i in r["apagados"]], ["ep1"])
        self.assertTrue(self.ref.is_dir())
        self.assertTrue((self.ref.parent / "ref1.mp4").exists())
        self.assertIn("referência", r["recusados"][0]["motivo"])
        self.assertEqual([x["slug"] for x in self.registros()], ["ep1"])

    def test_referencia_sozinha_so_com_confirmar(self):
        r = S.apagar([self.r(self.ref)])
        self.assertEqual(r["apagados"], [])
        self.assertTrue(self.ref.is_dir())
        r = S.apagar([self.r(self.ref)], confirmar=True)
        self.assertEqual(len(r["apagados"]), 1)
        self.assertFalse(self.ref.exists())
        self.assertFalse((self.ref.parent / "ref1.mp4").exists())
        self.assertTrue(self.registros()[0]["referencia"])


class Trava(Base):
    def recusa(self, caminho):
        r = S.apagar([caminho])
        self.assertEqual(r["apagados"], [], caminho)
        self.assertEqual(len(r["recusados"]), 1, caminho)
        with self.assertRaises(ValueError):
            S.conferir(caminho)

    def test_ponto_ponto(self):
        self.recusa("clientes/Joao/vegasContent/output/dialogo-3d/../../material/bruto.mp4")
        self.recusa("clientes/Joao/vegasContent/output/../material")
        self.assertTrue((self.fora / "bruto.mp4").exists())

    def test_fora_de_output(self):
        self.recusa(self.r(self.fora / "bruto.mp4"))
        self.recusa(self.r(self.fora))
        self.recusa("app/custos")
        self.recusa(str(self.fora / "bruto.mp4"))   # absoluto também
        self.recusa("/etc/hosts")
        self.assertTrue((self.fora / "bruto.mp4").exists())

    def test_pasta_do_modelo_inteira_ou_output_nao(self):
        self.recusa(self.r(self.out_j / "dialogo-3d"))
        self.recusa(self.r(self.out_j))
        self.recusa(self.r(self.out_j / "dialogo-3d" / "notas.txt"))
        self.assertTrue(self.ep.is_dir())

    def test_video_solto_com_pasta_do_mesmo_nome_na_output_nao_derruba_nem_apaga(self):
        (self.out_j / "livre").mkdir()
        (self.out_j / "livre" / "ep.mp4").write_bytes(b"v")
        (self.out_j / "livre.mp4").write_bytes(b"v")
        res = S.apagar([self.r(self.out_j / "livre.mp4")])
        self.assertEqual(res["apagados"], [])
        self.assertEqual(len(res["recusados"]), 1)
        self.assertTrue((self.out_j / "livre.mp4").is_file() and (self.out_j / "livre" / "ep.mp4").is_file())

    def test_link_simbolico(self):
        alvo = self.raiz / "importante"
        alvo.mkdir()
        (alvo / "x.mp4").write_bytes(b"x")
        os.symlink(alvo, self.out_j / "dialogo-3d" / "atalho")
        os.symlink(alvo / "x.mp4", self.out_j / "dialogo-3d" / "atalho2.mp4")
        os.symlink(alvo, self.out_j / "modelo-link")   # pasta do modelo é um link: o que tem dentro também é recusado
        self.recusa(self.r(self.out_j / "dialogo-3d" / "atalho"))
        self.recusa(self.r(self.out_j / "dialogo-3d" / "atalho2.mp4"))
        self.recusa(self.r(self.out_j / "modelo-link" / "x.mp4"))
        self.assertTrue((alvo / "x.mp4").exists())
        self.assertNotIn("atalho", {i["slug"] for i in S.listar()})
        self.assertEqual(self.registros(), [])

    def test_vazio_e_inexistente(self):
        with self.assertRaises(ValueError):
            S.conferir("")
        self.assertEqual(S.apagar(["", "  "]), {"apagados": [], "recusados": [], "mb": 0})
        self.recusa(self.r(self.out_j / "dialogo-3d" / "nao-existe"))


class Referencia(Base):
    def setUp(self):
        super().setUp()
        self.chamadas = []

        def falso(slug, video, legenda="", principal=False):
            if slug != "dialogo-3d":
                raise ValueError(f"Formato não encontrado: formatos/{slug}/")
            self.chamadas.append((slug, Path(video), legenda))
            return {"arquivo": "exemplo-3.mp4"}
        p = patch.object(S._formatos, "referencia", falso)
        p.start()
        self.addCleanup(p.stop)

    def test_guarda_referencia_e_vira_exemplo(self):
        it = S.guardar_referencia(self.r(self.ep), "dialogo-3d", "ritmo perfeito")
        self.assertEqual(self.chamadas, [("dialogo-3d", self.ep.parent / "ep1.mp4", "ritmo perfeito")])
        d = json.loads((self.ep / "REFERENCIA.json").read_text())
        self.assertEqual((d["formato"], d["motivo"], d["exemplo"]), ("dialogo-3d", "ritmo perfeito", "formatos/dialogo-3d/exemplo-3.mp4"))
        self.assertEqual(it["referencia"]["formato"], "dialogo-3d")
        self.assertEqual(S.apagar([self.r(self.ep), self.r(self.out_j / "dialogo-3d" / "solto.mp4")])["apagados"][0]["slug"], "solto")
        self.assertTrue(self.ep.is_dir())

    def test_video_solto_ganha_pasta_com_referencia(self):
        S.guardar_referencia(self.r(self.out_j / "dialogo-3d" / "solto.mp4"), "dialogo-3d")
        self.assertTrue((self.out_j / "dialogo-3d" / "solto" / "REFERENCIA.json").is_file())
        it = {i["slug"]: i for i in S.listar()}["solto"]
        self.assertIsNotNone(it["referencia"])

    def test_formato_errado_ou_sem_video_nao_marca(self):
        with self.assertRaises(ValueError):
            S.guardar_referencia(self.r(self.ep), "nao-existe")
        self.assertFalse((self.ep / "REFERENCIA.json").exists())
        (self.ep.parent / "ep1.mp4").unlink()
        with self.assertRaises(ValueError):
            S.guardar_referencia(self.r(self.ep), "dialogo-3d")
        with self.assertRaises(ValueError):
            S.guardar_referencia(self.r(self.fora / "bruto.mp4"), "dialogo-3d")


class Rotas(Base):
    def setUp(self):
        super().setUp()
        import servidor
        self.c = servidor.app.test_client()

    def test_tela_saidas_lista_e_apaga_marcados(self):
        h = self.c.get("/saidas").get_data(as_text=True)
        for t in ("ep1", "solto", "ref1", "Apagar marcados", "Guardar como referência", "Referência"):
            self.assertIn(t, h)
        self.assertIn('data-apagar-previa="/espaco/previa?caminho=', h)      # o painel (ver antes de apagar) avisa que é referência
        self.assertIn('REFER%C3%8ANCIA', h)
        r = self.c.post("/saidas/apagar", data={"caminho": [self.r(self.ep), self.r(self.ref)], "confirmar": "1"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.ep.exists())
        self.assertTrue(self.ref.is_dir())   # lote: referência fica mesmo com confirmar
        self.c.post("/saidas/apagar", data={"caminho": "clientes/Joao/vegasContent/output/../material/bruto.mp4"})
        self.assertTrue((self.fora / "bruto.mp4").exists())

    def test_meus_videos_nao_apaga_referencia_nem_em_lote(self):
        import simples
        self._job("Cliente2", "ref1", "dividido-mascara", status="exportado")
        self._job("Cliente2", "solto", "dividido-mascara", status="exportado", saida=self.r(self.ref.parent / "solto.mp4"))
        (self.ref.parent / "solto.mp4").write_bytes(b"v" * 10)
        self.c.post("/videos/Cliente2/ref1/apagar")
        self.c.post("/videos/apagar-finalizados")
        self.assertTrue(self.ref.is_dir() and (self.ref.parent / "ref1.mp4").is_file())   # referência fica, sozinha ou em lote
        self.assertTrue(self.jobdir("Cliente2", "ref1").is_dir())
        self.assertFalse((self.ref.parent / "solto.mp4").exists())                          # o outro finalizado saiu inteiro
        self.assertFalse(self.jobdir("Cliente2", "solto").exists())

    def test_meus_videos_tem_link(self):
        self.assertIn("/saidas", self.c.get("/videos").get_data(as_text=True))

    def test_ficou_bom_ganha_guardar_apagar_deixar(self):
        A.pronto("Joao", "ep1", formato="dialogo-3d", titulo="Ep 1", pasta=self.ep, video=self.ep.parent / "ep1.mp4")
        h = self.c.get("/andamento/Joao/ep1").get_data(as_text=True)
        for t in ("Guardar como referência", "Deixar por enquanto", 'value="apagar"'):
            self.assertIn(t, h)
        self.assertEqual(self.c.post("/andamento/Joao/ep1/saida", data={"acao": "deixar"}).status_code, 302)
        self.assertTrue(self.ep.is_dir())
        r = self.c.post("/andamento/Joao/ep1/saida", data={"acao": "apagar", "confirmar": "1"})
        self.assertIn("/andamento", r.headers["Location"])
        self.assertFalse(self.ep.exists())
        self.assertEqual(self.registros()[0]["slug"], "ep1")


class ApagarTudo(Base):
    """O caminho único: apaga TUDO de um vídeo e só o que é dele."""

    def setUp(self):
        super().setUp()
        raiz, c = self.raiz, "clientes/Joao/vegasContent"
        self.saida = self.out_j / "dialogo-3d"
        for n, t in (("ep1.info", "i"), ("ep1.json", "{}"), ("ep1.jpg", "j"), ("ep1-v2.mp4", "v2"),
                     ("ep10.mp4", "outro vídeo"), ("ep10.json", "{}"), ("ep1-extra.json", "{}")):
            (self.saida / n).write_text(t * 100)
        self.job = self._job("Joao", "ep1", "dialogo-3d", briefing_id="b1",
                             versoes=[{"arquivo": f"{c}/output/dialogo-3d/ep1-v2.mp4"},
                                      {"arquivo": f"{c}/material/bruto.mp4"}])
        self.job_outro = self._job("Joao", "ep10", "dialogo-3d", briefing_id="b2")
        self._job("Joao", "ep11", "dialogo-3d", briefing_id="b2")
        modelo = raiz / c / "modelos/dialogo-3d"
        self.sb = modelo / "_sandbox-ep1"
        (self.sb / "quadros").mkdir(parents=True)
        (self.sb / "quadros/a.png").write_bytes(b"s" * 4000)
        self.sb_compartilhada, self.sb_outro = modelo / "_sandbox", modelo / "_sandbox-ep10"
        for d in (self.sb_compartilhada, self.sb_outro):
            d.mkdir(parents=True)
            (d / "x.txt").write_text("fica")
        (modelo / "aprendizado").mkdir()
        self.regras = modelo / "aprendizado/regras.json"
        self.regras.write_text("[1]")
        for b in ("b1", "b2"):
            (raiz / "app/briefings" / b).mkdir(parents=True)
            (raiz / "app/briefings" / b / "briefing.json").write_text("{}")
        self.mac = raiz.parent / (raiz.name + "-mac") / "ep1"
        self.mac.mkdir(parents=True)
        (self.mac / "final.mp4").write_bytes(b"copia")
        self.addCleanup(shutil_rmtree, self.mac.parent)
        self.acervo = raiz / "acervo/itens/x/meta.json"
        self.acervo.parent.mkdir(parents=True)
        self.acervo.write_text("{}")
        self.custo = raiz / "app/custos/videos.jsonl"
        self.custo.parent.mkdir(parents=True, exist_ok=True)
        self.custo.write_text('{"usd": 1.5}\n')
        A.pronto("Joao", "ep1", formato="dialogo-3d", titulo="Ep 1", pasta=self.ep, video=self.saida / "ep1.mp4")
        A.pronto("Joao", "ep10", formato="dialogo-3d", titulo="Ep 10")
        self.and_ep1 = raiz / "app/andamento/Joao/ep1.json"
        self.ficam = [self.saida / "ep10.mp4", self.saida / "ep10.json", self.saida / "ep1-extra.json", self.fora / "bruto.mp4",
                      self.sb_compartilhada / "x.txt", self.sb_outro / "x.txt", self.regras, self.acervo, self.custo,
                      self.mac / "final.mp4", self.jobdir("Joao", "ep10") / "job.json", raiz / "app/andamento/Joao/ep10.json",
                      raiz / "app/briefings/b2/briefing.json", self.ref / "REFERENCIA.json"]
        self.somem = [self.ep, self.saida / "ep1.mp4", self.saida / "ep1.info", self.saida / "ep1.json", self.saida / "ep1.jpg",
                      self.saida / "ep1-v2.mp4", self.job, self.sb, self.and_ep1, raiz / "app/briefings/b1"]

    def confere(self):
        for p in self.ficam:
            self.assertTrue(p.exists(), f"deveria ficar: {p}")

    def test_cada_artefato_some_e_o_resto_fica(self):
        self.assertTrue(all(p.exists() for p in self.somem))
        r = S.apagar([self.r(self.ep)])
        self.assertEqual((len(r["apagados"]), r["recusados"]), (1, []))
        for p in self.somem:
            self.assertFalse(p.exists(), f"deveria sair: {p}")
        self.confere()
        self.assertTrue((self.fora / "bruto.mp4").exists())   # render fora da pasta do vídeo (listado no job) é preservado
        a = r["apagados"][0]
        self.assertGreater(a["bytes"], 3500)                   # contou também job, sandbox, versão e metadados
        tipos = {f["tipo"] for f in a["pecas"]}
        self.assertEqual(tipos, {"pasta", "video", "versao", "metadados", "job", "sandbox", "andamento", "briefing"})
        msg = S.mensagem(r)
        self.assertIn("Lixeira do Mac", msg)
        self.assertIn("rascunhos", msg)
        self.assertIn("exportada", msg)
        self.assertIn("fica guardado", " ".join(a["avisos"]))   # o que está fora das pastas do vídeo não vai pra Lixeira

    def test_log_guarda_so_o_que_saiu_e_o_custo_fica(self):
        S.apagar([self.r(self.saida / "ep1.mp4")])
        reg = self.registros()[-1]
        self.assertEqual((reg["slug"], reg["referencia"]), ("ep1", False))
        self.assertIn("app/jobs/Joao/ep1", reg["pecas"])
        self.assertEqual(self.custo.read_text(), '{"usd": 1.5}\n')   # livro de gasto intocado

    def test_pelo_nome_do_job_o_mesmo_caminho(self):
        r = S.apagar_video("Joao", "ep1")
        self.assertEqual(len(r["apagados"]), 1)
        for p in self.somem:
            self.assertFalse(p.exists(), f"deveria sair: {p}")
        self.confere()

    def test_sem_saida_ainda_apaga_projeto_rascunho_e_registro(self):
        for p in (self.ep, self.saida / "ep1.mp4"):
            shutil_rmtree(p) if p.is_dir() else p.unlink()
        r = S.apagar_video("Joao", "ep1")
        self.assertEqual(len(r["apagados"]), 1)
        for p in (self.job, self.sb, self.and_ep1):
            self.assertFalse(p.exists())
        self.confere()
        self.assertEqual(S.apagar_video("Joao", "ep1")["recusados"][0]["motivo"], "Esse vídeo já não existe.")

    def test_referencia_protegida_e_so_sai_com_confirmacao_dedicada(self):
        j = self._job("Cliente2", "ref1", "dividido-mascara")
        A.pronto("Cliente2", "ref1", formato="fala-com-cenas", pasta=self.ref, video=self.ref.parent / "ref1.mp4")
        r = S.apagar([self.r(self.ref)])
        self.assertTrue(r["recusados"][0]["motivo"].startswith("É referência"))
        r = S.apagar_video("Cliente2", "ref1")
        self.assertTrue(r["recusados"][0]["motivo"].startswith("É referência"))
        r = S.apagar_video("Cliente2", "ref1", lote=True, confirmar=True)   # lote nunca leva referência
        self.assertEqual(r["apagados"], [])
        self.assertTrue(self.ref.is_dir() and j.is_dir() and (self.raiz / "app/andamento/Cliente2/ref1.json").is_file())
        r = S.apagar([self.r(self.ref)], confirmar=True)
        self.assertEqual(len(r["apagados"]), 1)
        self.assertFalse(self.ref.exists() or j.exists() or (self.raiz / "app/andamento/Cliente2/ref1.json").exists())
        self.assertTrue(self.registros()[-1]["referencia"])

    def test_video_rodando_nao_apaga(self):
        (self.job / "runner.pid").write_text(str(os.getpid()))
        r = S.apagar([self.r(self.ep)])
        self.assertIn("rodando", r["recusados"][0]["motivo"])
        self.assertTrue(self.ep.is_dir() and self.job.is_dir() and self.sb.is_dir())
        (self.job / "runner.pid").unlink()
        j = json.loads((self.job / "job.json").read_text())
        j["status"] = "na_fila"
        (self.job / "job.json").write_text(json.dumps(j))
        self.assertIn("rodando", S.apagar_video("Joao", "ep1")["recusados"][0]["motivo"])
        self.assertTrue(self.job.is_dir())

    def test_chat_trabalhando_agora_nao_apaga(self):
        A.passo("Joao", "ep1", "Renderizando")
        r = S.apagar([self.r(self.ep)])
        self.assertIn("sendo feito", r["recusados"][0]["motivo"])
        self.assertTrue(self.ep.is_dir() and self.and_ep1.is_file())

    def test_lote_respeita_as_travas(self):
        j = self._job("Cliente2", "ref1", "dividido-mascara")
        (self.job_outro / "runner.pid").write_text(str(os.getpid()))
        r = S.apagar([self.r(self.ep), self.r(self.ref), self.r(self.saida / "ep10.mp4")], confirmar=True)
        self.assertEqual([a["slug"] for a in r["apagados"]], ["ep1"])
        motivos = " | ".join(x["motivo"] for x in r["recusados"])
        self.assertIn("referência", motivos)
        self.assertIn("rodando", motivos)
        self.assertTrue(self.ref.is_dir() and j.is_dir() and (self.saida / "ep10.mp4").is_file() and self.job_outro.is_dir())
        self.assertFalse(self.job.exists())

    def test_briefing_compartilhado_fica_ate_o_ultimo_video(self):
        S.apagar_video("Joao", "ep10")
        self.assertTrue((self.raiz / "app/briefings/b2").is_dir())   # ep11 ainda usa
        S.apagar_video("Joao", "ep11")
        self.assertFalse((self.raiz / "app/briefings/b2").exists())

    def test_atalho_nao_leva_o_destino(self):
        alvo = self.raiz / "fora-do-projeto"
        alvo.mkdir()
        (alvo / "importante.txt").write_text("fica")
        shutil_rmtree(self.sb)
        self.sb.symlink_to(alvo)
        r = S.apagar([self.r(self.ep)])
        self.assertTrue((alvo / "importante.txt").is_file())
        self.assertTrue(self.sb.is_symlink())
        self.assertIn("atalho", " ".join(r["apagados"][0]["avisos"]))

    def test_rotas_mostram_o_que_saiu_e_quanto_liberou(self):
        import servidor
        c = servidor.app.test_client()
        r = c.post("/videos/Joao/ep1/apagar", follow_redirects=True)
        h = r.get_data(as_text=True)
        self.assertIn("Lixeira do Mac", h)
        self.assertIn("rascunhos", h)
        for p in self.somem:
            self.assertFalse(p.exists(), f"deveria sair: {p}")
        self.confere()

    def test_botao_da_pagina_do_video_tambem(self):
        import servidor
        r = servidor.app.test_client().post("/job/Joao/ep1/apagar", follow_redirects=True)
        self.assertIn("Lixeira do Mac", r.get_data(as_text=True))
        for p in self.somem:
            self.assertFalse(p.exists(), f"deveria sair: {p}")
        self.confere()

    def test_botao_do_em_andamento_leva_tudo(self):
        import servidor
        c = servidor.app.test_client()
        r = c.post("/andamento/Joao/ep1/saida", data={"acao": "apagar", "confirmar": "1"})
        self.assertEqual(r.status_code, 302)
        for p in self.somem:
            self.assertFalse(p.exists(), f"deveria sair: {p}")
        self.confere()


def shutil_rmtree(p):
    import shutil
    shutil.rmtree(p, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
