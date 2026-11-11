"""Volta 7 (ajuste): conferência no 'pronto' do chat, enumeração não é gaguejo, fim do bruto, fala do vídeo cortado, título do lote."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ferramentas"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "interface"))

import conferir_video  # noqa: E402
import corte  # noqa: E402


def _w(p, t0, t1):
    return {"p": p, "t0": t0, "t1": t1}


class Enumeracao(unittest.TestCase):
    def test_reacao_instantanea_quimica_nao_e_gaguejo(self):
        frase = "é uma reação instantânea é uma reação química do seu organismo".split()
        W = [_w(p, i * 0.3, i * 0.3 + 0.25) for i, p in enumerate(frase)]
        T = [corte._tok(w) for w in W]
        fora = corte._perto(W, T, 6, 2, 8, 0.7, 0.8, 3.5)
        self.assertEqual(fora, [])

    def test_repeticao_igual_continua_gaguejo(self):
        self.assertFalse(corte._enumeracao(["a", "casa"], ["a", "casa"], 1.0, 1.1))
        self.assertFalse(corte._enumeracao(["histórico"], ["históricos"], 1.0, 1.1))
        self.assertTrue(corte._enumeracao(["reacao", "instantanea"], ["reacao", "quimica"], 1.0, 1.1))
        self.assertFalse(corte._enumeracao(["reacao", "instantanea"], ["reacao", "quimica"], 1.0, 1.6))


class FimDoBruto(unittest.TestCase):
    def test_ultimo_trecho_sem_ponto_ate_o_fim_sai(self):
        segs = [{"i": 0, "t0": 0, "t1": 10, "texto": "Fala boa."}, {"i": 1, "t0": 50, "t1": 60.0, "texto": "o tempo certo de tomar"}]
        fora = {}
        corte._marcar_corte_no_fim(segs, fora, 60.0)
        self.assertEqual(fora, {1: "frase cortada no fim do bruto"})

    def test_com_ponto_ou_antes_do_fim_fica(self):
        segs = [{"i": 0, "t0": 50, "t1": 60.0, "texto": "Terminou."}]
        fora = {}
        corte._marcar_corte_no_fim(segs, fora, 60.0)
        self.assertEqual(fora, {})
        segs = [{"i": 0, "t0": 40, "t1": 50, "texto": "sem ponto"}]
        corte._marcar_corte_no_fim(segs, fora, 60.0)
        self.assertEqual(fora, {})


class FalaDoVideo(unittest.TestCase):
    def test_usa_so_o_mantido_e_limita_na_duracao(self):
        with tempfile.TemporaryDirectory() as t:
            sb = Path(t)
            (sb / "work").mkdir()
            words = [{"word": "Oi.", "start": 0, "end": 1}, {"word": "de", "start": 50, "end": 59.9}, {"word": "tomar", "start": 59.9, "end": 60}]
            (sb / "work/words.json").write_text(json.dumps({"words": words}), encoding="utf-8")
            (sb / "work/CORTE.json").write_text(json.dumps({"segmentos": [
                {"t0": 0, "t1": 1, "manter": True}, {"t0": 50, "t1": 60, "manter": False}]}), encoding="utf-8")
            ws, fim = conferir_video.fala_do_video(sb, 54.3)
            self.assertEqual([w["word"] for w in ws], ["Oi."])
            self.assertEqual(fim, 1.0)
            (sb / "work/CORTE.json").unlink()
            _, fim = conferir_video.fala_do_video(sb, 54.3)
            self.assertEqual(fim, 54.3)


class Legenda(unittest.TestCase):
    def test_grupo_nao_fecha_em_palavra_fraca(self):
        raiz = Path(__file__).resolve().parents[2] / "clientes/Joao/vegasContent/modelos/critica-ao-absurdo/build.py"
        import importlib.util
        sp = importlib.util.spec_from_file_location("build_critica", raiz)
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        ws = [_w(p, i * 0.2, i * 0.2 + 0.15) for i, p in enumerate("é a química do seu organismo".split())]
        for b in m.grupos(ws):
            self.assertNotIn(b["palavras"][-1].lower(), ("do", "seu", "a", "de"), b)


if __name__ == "__main__":
    unittest.main()
