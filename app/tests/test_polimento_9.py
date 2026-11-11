"""Polimento v2, volta 9: transcrição em pedaços com nova tentativa, erros simples, fila que se recupera, prazo por etapa."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import _comum  # noqa: E402
import estilo_ref  # noqa: E402
import fala  # noqa: E402
import fila  # noqa: E402
import ia  # noqa: E402


class Transcricao(unittest.TestCase):
    def test_video_longo_vira_pedacos_com_tempo_somado(self):
        chamadas = []

        def falso(cmd, **k):
            if cmd[0] == "curl":
                chamadas.append(1)
                return mock.Mock(returncode=0, stdout='{"words":[{"start":1,"end":2,"word":"a"}],"segments":[{"start":0,"end":3,"text":"a"}],"text":"a"}\n200', stderr="")
            Path(cmd[-1]).write_bytes(b"x")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(fala.subprocess, "run", falso), mock.patch("_comum.ffprobe", return_value={"duracao": 1500}):
            js = fala.groq_transcrever("v.mp4", "k")
        self.assertEqual(len(chamadas), 3)
        self.assertEqual([w["start"] for w in js["words"]], [1, 601, 1201])

    def test_429_tenta_3_vezes_e_avisa_simples(self):
        n = []

        def falso(cmd, **k):
            if cmd[0] == "curl":
                n.append(1)
                return mock.Mock(returncode=0, stdout='{"error":{"message":"rate_limit_exceeded"}}\n429', stderr="")
            Path(cmd[-1]).write_bytes(b"x")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(fala.subprocess, "run", falso), mock.patch("_comum.ffprobe", return_value={"duracao": 5}), \
                mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError) as c:
                fala.groq_transcrever("v.mp4", "k")
        self.assertEqual(len(n), 3)
        self.assertEqual(str(c.exception), _comum.MSG_GROQ_LIMITE)


class ErroSimples(unittest.TestCase):
    def test_tabela(self):
        casos = {"Request Entity Too Large": "grande demais", "rate_limit_exceeded": "limite", "No space left on device": "espaço",
                 "Could not resolve host: x": "internet", "Invalid data found when processing input": "corrompido",
                 "moov atom not found": "corrompido", "No such file or directory": "sumiu", "Permission denied": "permissão",
                 "Traceback boom": "Tentar de novo"}
        for entrada, trecho in casos.items():
            self.assertIn(trecho, _comum.erro_simples(entrada))

    def test_portugues_passa_direto(self):
        self.assertEqual(_comum.erro_simples("Salve suas escolhas antes de renderizar."), "Salve suas escolhas antes de renderizar.")


class Fila(unittest.TestCase):
    def _ciclo(self, item, job):
        salvos = []
        P = mock.Mock(carregar=lambda c, s: job, salvar=lambda j: salvos.append(dict(j)), _pasta_job=lambda c, s: Path(tempfile.mkdtemp()))
        gravado = {}
        avisos = []
        with mock.patch.dict("sys.modules", {"producao": P}), mock.patch.object(fila, "ler", return_value=[item]), \
                mock.patch.object(fila, "gravar_json", lambda p, v: gravado.update(v=v)), \
                mock.patch.object(fila, "_aviso", lambda *a: avisos.append(a)), \
                mock.patch.object(fila, "vivo", return_value=False), mock.patch.object(fila.ia, "config", return_value=dict(renders_simultaneos=1, analises_simultaneas=1)), \
                mock.patch.object(fila.subprocess, "Popen"), mock.patch("custos.registrar_video_job", create=True):
            fila.ciclo()
        return gravado["v"], avisos

    def test_primeira_queda_reenfileira_e_segunda_vira_erro(self):
        pf = Path(tempfile.mkdtemp()) / "p.txt"
        pf.write_text("x")
        item = dict(id="a", cliente="C", slug="s", tipo="producao", prompt=str(pf), estado="rodando", pid=1)
        job = dict(status="renderizando")
        itens, avisos = self._ciclo(dict(item), dict(job))
        self.assertEqual(itens[0]["estado"], "erro")
        self.assertTrue(any(i.get("tentativa") == 1 for i in itens))
        itens, avisos = self._ciclo(dict(item, tentativa=1), dict(job))
        self.assertEqual([i["estado"] for i in itens], ["erro"])
        self.assertEqual(avisos[0][0], "erro")


class Prazo(unittest.TestCase):
    def test_estoura_e_para(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            with mock.patch.object(ia, "comando", return_value=["/bin/sleep", "30"]), mock.patch.object(ia, "max_min", return_value=1 / 60), \
                    mock.patch.object(ia, "ambiente", return_value={}), mock.patch.object(ia, "rotulo", return_value="x"):
                code = ia.executar("p", t / "l", t / "r", t / "pid", {"provedor": "claude", "cobranca": "assinatura"}, tipo="analise")
            self.assertEqual(code, 1)
            self.assertIn("Passou de", (t / "l").read_text())


class EstiloParado(unittest.TestCase):
    def test_analisando_antigo_vira_erro(self):
        with tempfile.TemporaryDirectory() as t:
            id_ = "a" * 8
            ant = Path(t)
            d = ant / id_
            d.mkdir()
            (d / "estado.json").write_text('{"estado":"analisando","atualizado_em":"2020-01-01 00:00:00"}')
            with mock.patch.object(estilo_ref, "ESTILOS", ant):
                self.assertEqual(estilo_ref.estado(id_)["estado"], "erro")


if __name__ == "__main__":
    unittest.main()
