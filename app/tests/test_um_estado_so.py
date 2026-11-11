"""Um estado só: job.json e app/andamento/ conversam. Pasta temporária, nada pago, nada roda de verdade."""
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
import andamento as A
import producao as P

CLI, SLUG = "Cliente2", "roteiro"
SAIDA = "clientes/Cliente2/marca2Content/output/dialogo-3d/roteiro.mp4"
SANDBOX = "clientes/Cliente2/marca2Content/modelos/dialogo-3d/_sandbox-roteiro"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = raiz = Path(self.tmp.name).resolve()
        for alvo, valor in (("andamento.RAIZ", raiz), ("producao.RAIZ", raiz), ("_comum.RAIZ", raiz), ("_comum.ESTUDIO", raiz / "app"),
                            ("producao.JOBS", raiz / "app" / "jobs")):
            m, a = alvo.split(".")
            p = patch.object(sys.modules[m], a, valor)
            p.start()
            self.addCleanup(p.stop)
        (raiz / SAIDA).parent.mkdir(parents=True)
        (raiz / SAIDA).write_bytes(b"v" * 100)
        (raiz / SANDBOX).mkdir(parents=True)

    def mp4(self):
        """Caminho absoluto do vídeo (quem chama o andamento passa o caminho real; relativo contaria a partir da pasta atual)."""
        return str(self.raiz / SAIDA)

    def job(self, status="plano", slug=SLUG, titulo="Roteiro", **extra):
        j = {"slug": slug, "titulo": titulo, "cliente": CLI, "modelo": "dialogo-3d", "criado_em": "2026-10-10 01:09:10",
             "status": status, "sandbox": SANDBOX, "saida": None, "saida_esperada": SAIDA, "formato": "dialogo-3d", **extra}
        P.salvar(j)
        return j

    def status(self, slug=SLUG):
        return P.carregar(CLI, slug)["status"]

    def velho(self, slug=SLUG, seg=600):
        """Deixa o job.json mais velho (o job parou antes do andamento andar)."""
        arq = P._pasta_job(CLI, slug) / "job.json"
        t = time.time() - seg
        os.utime(arq, (t, t))


class PronoSincroniza(Base):
    def test_pronto_atualiza_o_job(self):
        self.job("plano")
        A.espera(CLI, SLUG, "Storyboard pronto: aprove", formato="dialogo-3d", titulo="Roteiro")
        self.assertEqual(self.status(), "plano")
        A.pronto(CLI, SLUG, video=self.mp4(), pasta=SANDBOX)
        j = P.carregar(CLI, SLUG)
        self.assertEqual((j["status"], j["saida"]), ("concluido", SAIDA))

    def test_espera_mantem_plano_e_erro_marca_erro(self):
        self.job("plano")
        A.passo(CLI, SLUG, "Montando", titulo="Roteiro")
        self.assertEqual(self.status(), "plano")   # trabalhando não mexe no job
        A.espera(CLI, SLUG, "Storyboard pronto")
        self.assertEqual(self.status(), "plano")
        A.erro(CLI, SLUG, "deu ruim")
        self.assertEqual(self.status(), "erro")

    def test_pronto_acha_a_saida_sozinho_e_pelo_slug_da_sandbox(self):
        self.job("plano", slug="job-da-tela")   # o chat gravou o andamento com outro slug, mas na mesma sandbox
        A.pronto(CLI, SLUG, pasta=SANDBOX, titulo="Roteiro")
        j = P.carregar(CLI, "job-da-tela")
        self.assertEqual((j["status"], j["saida"]), ("concluido", SAIDA))

    def test_nao_mexe_em_aprovado_nem_sem_saida(self):
        self.job("aprovado", saida=SAIDA)
        A.pronto(CLI, SLUG, video=self.mp4())
        self.assertEqual(self.status(), "aprovado")
        self.job("plano")
        (self.raiz / SAIDA).unlink()
        A.pronto(CLI, SLUG)   # sem mp4 em lugar nenhum: não inventa saída
        self.assertEqual(self.status(), "plano")

    def test_job_rodando_fica_com_o_runner(self):
        self.job("analisando")
        with patch.object(P, "_vivo", return_value=True):
            A.pronto(CLI, SLUG, video=self.mp4())
        self.assertEqual(self.status(), "analisando")


class Reconciliar(Base):
    def preso(self, aprovar=False):
        """O caso real: job parado em 'plano', andamento 'pronto' mais novo."""
        self.job("plano")
        self.velho()
        d = {"cliente": CLI, "slug": SLUG, "titulo": "Roteiro", "formato": "dialogo-3d", "inicio": "2026-10-10 01:12:06", "etapa": "pronto",
             "estado": "pronto", "atualizado": A.agora(), "pasta": SANDBOX, "video": SAIDA, "passos": [{"texto": "Vídeo pronto", "inicio": A.agora(), "estado": "pronto"}],
             "respostas": [{"em": A.agora(), "decisao": "aprovar", "estado_no_momento": "pronto", "etapa_no_momento": "pronto", "status": "feito"}] if aprovar else []}
        A._gravar(A._arq(CLI, SLUG), d)

    def test_conserta_o_preso(self):
        self.preso()
        self.assertEqual(P.reconciliar(), 1)
        j = P.carregar(CLI, SLUG)
        self.assertEqual((j["status"], j["saida"]), ("concluido", SAIDA))
        self.assertEqual(P.reconciliar(), 0)   # de novo não faz nada

    def test_preso_e_aprovado_vira_aprovado(self):
        self.preso(aprovar=True)
        P.reconciliar()
        self.assertEqual(self.status(), "aprovado")

    def test_concluido_aprovado_depois_vira_aprovado(self):
        self.job("concluido", saida=SAIDA)
        self.velho()
        d = {"cliente": CLI, "slug": SLUG, "titulo": "R", "inicio": A.agora(), "estado": "pronto", "etapa": "pronto", "atualizado": "2026-10-10 00:00:00",
             "passos": [], "respostas": [{"em": A.agora(), "decisao": "aprovar", "estado_no_momento": "pronto", "status": "feito"}]}
        A._gravar(A._arq(CLI, SLUG), d)
        P.reconciliar()
        self.assertEqual(self.status(), "aprovado")

    def test_job_mais_novo_que_o_andamento_nao_e_tocado(self):
        self.preso()
        self.job("plano")   # o João voltou ao storyboard depois: job.json novo
        d = A._ler(A._arq(CLI, SLUG)); d["atualizado"] = "2026-10-10 01:00:00"; A._gravar(A._arq(CLI, SLUG), d)
        self.assertEqual(P.reconciliar(), 0)
        self.assertEqual(self.status(), "plano")

    def test_so_le_e_escreve_o_job_json(self):
        self.preso()
        antes = {p: p.read_bytes() for p in self.raiz.rglob("*") if p.is_file() and p.name != "job.json"}
        P.reconciliar()
        self.assertEqual({p: p.read_bytes() for p in self.raiz.rglob("*") if p.is_file() and p.name != "job.json"}, antes)


class Telas(Base):
    def setUp(self):
        super().setUp()
        import servidor, simples
        for modulo in (simples, servidor):
            if hasattr(modulo, "RAIZ"):
                p = patch.object(modulo, "RAIZ", self.raiz)
                p.start()
                self.addCleanup(p.stop)
        self.simples = simples
        self.c = servidor.app.test_client()

    def paginas(self):
        return {n: self.c.get(u).get_data(as_text=True) for n, u in (("inicio", "/"), ("videos", "/videos"), ("andamento", "/andamento"))}

    def test_o_bug_do_joao_pronto_nao_fica_preso_no_storyboard(self):
        self.job("plano")
        self.velho()
        A.pronto(CLI, SLUG, video=self.mp4(), pasta=SANDBOX, titulo="Roteiro", formato="dialogo-3d")   # só o andamento anda
        j = P.carregar(CLI, SLUG); j["status"] = "plano"; P.salvar(j); self.velho()                 # …e o job fica preso (caso velho)
        p = self.paginas()
        self.assertEqual(self.status(), "concluido")
        self.assertNotIn("Aprovar o storyboard", p["inicio"])
        self.assertNotIn("Aprovar o storyboard", p["videos"])
        self.assertIn("Ficou bom?", p["inicio"])

    def test_nenhum_video_nos_dois_lugares(self):
        self.job("plano", titulo="Roteiro Unico")
        A.pronto(CLI, SLUG, video=self.mp4(), pasta=SANDBOX, titulo="Roteiro Unico", formato="dialogo-3d")
        p = self.paginas()
        self.assertIn("Roteiro Unico", p["andamento"])          # pronto sem aprovar: em Em andamento
        self.assertNotIn("Roteiro Unico", p["videos"])
        d = A._ler(A._arq(CLI, SLUG))
        d["respostas"] = [{"em": A.agora(), "decisao": "aprovar", "estado_no_momento": "pronto", "status": "feito"}]
        A._gravar(A._arq(CLI, SLUG), d)
        j = P.carregar(CLI, SLUG); j["status"] = "concluido"; P.salvar(j); self.velho()
        p = self.paginas()                                      # aprovado: só em Meus vídeos
        self.assertNotIn("Roteiro Unico", p["andamento"])
        self.assertIn("Roteiro Unico", p["videos"])
        self.assertEqual(self.status(), "aprovado")

    def test_lugar_cobre_todos_os_status(self):
        vis = {f"{CLI}/{SLUG}": {}}
        j = lambda st: {"cliente": CLI, "slug": SLUG, "status": st}
        self.assertEqual([self.simples.lugar(j(s), vis) for s in ("plano", "concluido", "aprovado", "exportado")], ["andamento", "andamento", "videos", "videos"])
        self.assertEqual([self.simples.lugar(j(s), {}) for s in ("plano", "novo", "concluido", "aprovado")], ["producao", "producao", "videos", "videos"])

    def test_storyboard_pendente_espera_e_aprovar_continua_funcionando(self):
        self.job("plano", titulo="Roteiro Pendente")
        A.espera(CLI, SLUG, "Storyboard pronto: aprove", titulo="Roteiro Pendente", formato="dialogo-3d")
        p = self.paginas()
        self.assertIn("Aprovar o storyboard", p["inicio"])
        self.assertEqual(p["inicio"].count("Roteiro Pendente"), 1)   # um item só: o de Esperando você
        self.assertIn("Roteiro Pendente", p["andamento"])
        self.assertNotIn("Roteiro Pendente", p["videos"])
        self.assertEqual(self.status(), "plano")
        P.salvar_plano(P.carregar(CLI, SLUG), {"beats": []})
        with patch.object(P, "_storyboard_da_ferramenta"), patch.object(P, "_escolher_musica"):
            P.aprovar_plano(CLI, SLUG, {}, {})
        self.assertEqual(self.status(), "plano_aprovado")
        A.passo(CLI, SLUG, "Renderizando o vídeo final")
        A.pronto(CLI, SLUG, video=self.mp4())
        self.assertEqual(self.status(), "concluido")   # e o fim da produção continua fechando o job

    def test_abrir_video_pronto_leva_ao_resultado(self):
        self.job("plano")
        self.velho()
        d = {"cliente": CLI, "slug": SLUG, "titulo": "R", "inicio": A.agora(), "estado": "pronto", "etapa": "pronto", "atualizado": A.agora(),
             "passos": [], "video": SAIDA, "pasta": SANDBOX}
        A._gravar(A._arq(CLI, SLUG), d)
        h = self.c.get(f"/andamento/{CLI}/{SLUG}").get_data(as_text=True)
        self.assertIn(f"/job/{CLI}/{SLUG}#render-final", h)
        self.assertEqual(self.status(), "concluido")


if __name__ == "__main__":
    unittest.main()
