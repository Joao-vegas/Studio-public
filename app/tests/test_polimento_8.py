"""Polimento volta 8: referência por link com som, aviso sem som, 'serve' com nota 60, telas sem slug. Sem rede, sem IA."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest import mock

import test_v2_frente3 as f3
from test_v2_frente3 import estilo_ok, ia_falsa, estilo_ref, formatos


class Polimento8(f3.Estilo):
    def _pronto(self, **extra):
        with mock.patch.object(estilo_ref.ia, "executar", ia_falsa(estilo_ok(**extra))):
            return estilo_ref.entender(self.video, esperar=True)

    def test_download_pede_audio_e_junta(self):
        chamadas = []

        def falso(cmd, **kw):
            chamadas.append(cmd)
            dst = Path(cmd[cmd.index("-o") + 1])
            dst.write_bytes(self.video.read_bytes())
            return subprocess.CompletedProcess(cmd, 0, "Título do vídeo\n", "")
        with mock.patch.object(estilo_ref.subprocess, "run", falso) as _, \
                mock.patch.object(estilo_ref.ia, "executar", ia_falsa(estilo_ok())):
            real = subprocess.run
            with mock.patch.object(estilo_ref, "medir", lambda v, p: {"som": True, "folha": "folha.jpg", "quadros": []}):
                id_ = estilo_ref.entender("https://www.youtube.com/shorts/abc123", esperar=True)
        cmd = chamadas[0]
        self.assertIn("--merge-output-format", cmd)
        self.assertIn("ba", cmd[cmd.index("-f") + 1])
        self.assertEqual(estilo_ref.estado(id_)["titulo"], "Título do vídeo")
        self.assertEqual(estilo_ref.nome_curto(estilo_ref.estado(id_)), "Título do vídeo")
        self.assertTrue(real)

    def test_sem_som_avisa_e_nao_transcreve(self):
        chamou = []
        ps = [mock.patch.object(estilo_ref, "_transcricao", lambda *a: chamou.append(1) or ("x", "", "")),
              mock.patch.object(estilo_ref, "medir", lambda v, p: {"som": False, "folha": "folha.jpg", "quadros": []})]
        for p in ps:
            p.start()
        try:
            id_ = self._pronto()
        finally:
            for p in ps:
                p.stop()
        self.assertEqual(chamou, [])
        st = estilo_ref.estado(id_)
        self.assertIn("veio sem som", st["aviso"])
        self.assertEqual(st["detalhe_transcricao"], "sem áudio no arquivo")

    def test_prompt_sem_audio(self):
        p = estilo_ref._prompt("x", Path("/tmp/x"), {"som": False}, "", "", "")
        self.assertIn("SEM ÁUDIO", p)
        self.assertIn("nunca diga o assunto", p)
        self.assertNotIn("SEM ÁUDIO", estilo_ref._prompt("x", Path("/tmp/x"), {"som": True}, "", "", ""))

    def test_serve_e_confirmar_nota_baixa(self):
        baixo = estilo_ok(formato_sugerido={"slug": "teste-f3", "nota": 45, "porque": "mais ou menos", "perto": "teste-f3"})
        self.assertFalse(estilo_ref.serve(baixo))
        self.assertTrue(estilo_ref.serve(estilo_ok()))
        self.assertFalse(estilo_ref.serve(estilo_ok(formato_sugerido={"slug": "nao-existe", "nota": 90, "porque": "x"})))
        id_ = self._pronto(**{"formato_sugerido": baixo["formato_sugerido"]})
        r = estilo_ref.confirmar(id_, None, "x")
        self.assertTrue(r["novo"])
        self.assertFalse((Path(formatos.FORMATOS) / "teste-f3" / "estudos").exists())

    def test_tela_nota_baixa_e_titulo(self):
        from servidor import app
        c = app.test_client()
        id_ = self._pronto(formato_sugerido={"slug": "teste-f3", "nota": 45, "porque": "mais ou menos"})
        h = c.get(f"/referencia-rapida/{id_}").get_data(as_text=True)
        self.assertIn("Nenhum formato serve bem", h)
        self.assertIn("Criar este estilo novo", h)
        self.assertLess(h.index("Criar este estilo novo"), h.index("confirmar e guardar"))
        self.assertNotIn(" px a partir", h)
        self.assertNotIn("plano médio", h)
        id2 = self._pronto()
        h2 = c.get(f"/referencia-rapida/{id2}").get_data(as_text=True)
        self.assertIn("Serve no formato</b> Teste", h2)
        r = c.post(f"/referencia-rapida/{id2}/confirmar", data={"formato": "teste-f3", "nome": "n"}, follow_redirects=True)
        t = r.get_data(as_text=True)
        self.assertIn("Guardei no estilo Teste", t)
        self.assertIn("guardado em Teste", t)
        lista = c.get("/referencias").get_data(as_text=True)
        self.assertNotIn("exemplo-1.mp4", lista)

    def test_mesma_referencia_nao_entra_duas_vezes(self):
        """30-out-2026: a régua do estilo não conta o mesmo vídeo duas vezes (testes guardaram os mesmos cortes 3 vezes)."""
        id1 = self._pronto()
        r = estilo_ref.confirmar(id1, "teste-f3", "primeira")
        self.assertTrue(r["ok"])
        self.assertEqual(estilo_ref.referencia_repetida("teste-f3", self.video), Path(r["pasta"]).name)
        id2 = self._pronto()
        with self.assertRaises(ValueError) as e:
            estilo_ref.confirmar(id2, "teste-f3", "segunda")
        self.assertIn("não conta a mesma referência duas vezes", str(e.exception))
        self.assertEqual(len(list((Path(formatos.FORMATOS) / "teste-f3" / "estudos").iterdir())), 1)

    def test_nome_curto_de_link(self):
        self.assertEqual(estilo_ref.nome_curto({"link": "https://www.youtube.com/shorts/bCZAbi8eY8Q"}), "YouTube · bCZAbi8eY8Q")
        self.assertTrue(estilo_ref.nome_curto({"link": "https://www.instagram.com/reel/XyZ_1/"}).startswith("Instagram"))


# não reexecutar os testes herdados da classe base aqui
for _n in [n for n in dir(f3.Estilo) if n.startswith("test_")]:
    setattr(Polimento8, _n, None)
del _n

if __name__ == "__main__":
    unittest.main()
