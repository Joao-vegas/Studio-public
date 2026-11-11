"""Estúdio 2.0, Frente 3: referência rápida (estilo_ref + telas). IA simulada; tudo em pasta temporária."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / 'app' / 'ferramentas'))
sys.path.insert(0, str(RAIZ / 'app' / 'interface'))
import estilo_ref
import formatos

FALA = "hoje eu vou te mostrar como dobrar suas vendas em trinta dias sem gastar nada com anuncio"


def estilo_ok(**extra):
    e = {"layout": [{"nome": "pessoa", "y": 0, "altura": 1920}],
         "ritmo": {"corte_a_cada_s": 2.5, "plano_medio_s": 2.5},
         "legenda": {"posicao_y_pct": 70, "fonte_aprox": "sans pesada", "cor_hex": "#FFD400", "caixa": False,
                     "palavras_por_vez": 2, "maiusculas": True},
         "som": {"musica": True, "clima": "tenso", "efeitos": ["whoosh"]},
         "cores": ["#111111", "#FFD400"],
         "gancho": {"mecanismo": "pergunta direta com número na primeira frase", "ate_s": 3},
         "formato_sugerido": {"slug": "teste-f3", "nota": 80, "porque": "pessoa falando com legenda"},
         "estudo_respostas": {k: "2,5 s, corte seco" for k, _ in estilo_ref.chaves_perguntas()}}
    e.update(extra)
    return e


def ia_falsa(estilo):
    def _executar(prompt, log, raw, pid, s=None, on_event=None, tipo=None):
        (Path(log).parent / "estilo.json").write_text(json.dumps(estilo), encoding="utf-8")
        return 0
    return _executar


class Estilo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        (t / "formatos" / "teste-f3").mkdir(parents=True)
        (t / "formatos" / "teste-f3" / "formato.json").write_text(json.dumps({"titulo": "Teste", "frase": "x", "tipo": "motor"}))
        self.video = t / "ref.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=10:duration=5",
                        "-f", "lavfi", "-i", "sine=frequency=300:duration=5", "-shortest", "-pix_fmt", "yuv420p", str(self.video)], check=True)
        self.ps = [mock.patch.object(estilo_ref, "ESTILOS", t / "estilos"), mock.patch.object(formatos, "FORMATOS", t / "formatos"),
                   mock.patch.object(estilo_ref, "_transcricao", lambda v, p, c: (FALA, "", ""))]
        for p in self.ps:
            p.start()

    def tearDown(self):
        for p in self.ps:
            p.stop()
        self.tmp.cleanup()

    def test_medir(self):
        m = estilo_ref.medir(self.video, Path(self.tmp.name) / "m")
        self.assertEqual(m["proporcao"], "9:16")
        self.assertTrue(1 <= len(m["cores"]) <= 5 and all(c.startswith("#") for c in m["cores"]))
        self.assertTrue((Path(self.tmp.name) / "m" / "folha.jpg").is_file())
        self.assertTrue((Path(self.tmp.name) / "m" / "medidas.json").is_file())

    def test_validar_falta_campo(self):
        e = estilo_ok()
        del e["gancho"]
        with self.assertRaisesRegex(ValueError, "gancho"):
            estilo_ref.validar(e)
        e = estilo_ok()
        e["estudo_respostas"].pop("Som:0")
        with self.assertRaisesRegex(ValueError, "Som:0"):
            estilo_ref.validar(e)
        self.assertIs(estilo_ref.validar(estilo_ok())["som"]["musica"], True)

    def test_copia_proibida(self):
        estilo_ref.copia_proibida(estilo_ok(), FALA)   # não copia: passa
        ruim = estilo_ok(gancho={"mecanismo": "ele diz: Hoje, eu vou te mostrar COMO dobrar suas vendas", "ate_s": 3})
        with self.assertRaises(ValueError):
            estilo_ref.copia_proibida(ruim, FALA)

    def test_entender_e_confirmar(self):
        with mock.patch.object(estilo_ref.ia, "executar", ia_falsa(estilo_ok())):
            id_ = estilo_ref.entender(self.video, esperar=True)
        self.assertEqual(estilo_ref.estado(id_)["estado"], "pronto")
        r = estilo_ref.confirmar(id_, "teste-f3", "legenda amarela", principal=True)
        self.assertTrue(r["ok"])
        pasta = next((Path(formatos.FORMATOS) / "teste-f3" / "estudos").iterdir())
        txt = (pasta / "ESTUDO.md").read_text(encoding="utf-8")
        self.assertNotRegex(txt, r"(?m)^\s*R:\s*$")
        self.assertIn("R: 2,5 s", txt)
        self.assertTrue((pasta / "estilo.json").is_file() and (pasta / "PRINCIPAL").exists())
        self.assertTrue(self.video.is_file())   # nunca move o arquivo do João
        self.assertEqual(estilo_ref.estado(id_)["estado"], "confirmado")

    def test_estilo_copiado_e_recusado(self):
        ruim = estilo_ok(gancho={"mecanismo": "hoje eu vou te mostrar como dobrar suas vendas", "ate_s": 3})
        with mock.patch.object(estilo_ref.ia, "executar", ia_falsa(ruim)) as m:
            id_ = estilo_ref.entender(self.video, esperar=True)
        st = estilo_ref.estado(id_)
        self.assertEqual(st["estado"], "erro")
        self.assertTrue(st["erro"])

    def test_formato_novo_nao_cria_sozinho(self):
        with mock.patch.object(estilo_ref.ia, "executar", ia_falsa(estilo_ok(formato_sugerido={"slug": "novo", "nota": 20, "porque": "nada serve"}))):
            id_ = estilo_ref.entender(self.video, esperar=True)
        r = estilo_ref.confirmar(id_, None, "estilo bonito")
        self.assertTrue(r["novo"] and "formatos.py novo" in r["comando"])
        self.assertFalse((Path(formatos.FORMATOS) / "teste-f3" / "estudos").exists())

    def test_telas(self):
        from servidor import app
        c = app.test_client()
        self.assertEqual(c.get("/referencia-rapida").status_code, 302)   # vai pra /referencias
        self.assertEqual(c.get("/referencias").status_code, 200)
        with mock.patch.object(estilo_ref.ia, "executar", ia_falsa(estilo_ok())):
            id_ = estilo_ref.entender(self.video, esperar=True)
        r = c.get(f"/referencia-rapida/{id_}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Entendi assim", r.get_data(as_text=True))
        self.assertEqual(c.get(f"/referencia-rapida/{id_}/folha").status_code, 200)
        self.assertEqual(c.get("/referencia-rapida/abcdef012345").status_code, 404)
        self.assertIn("/referencia-rapida", c.get("/referencias").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
