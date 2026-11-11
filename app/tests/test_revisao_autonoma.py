"""O Estúdio aprende e melhora sozinho: revisão depois de cada vídeo, gate da melhoria (sem Aplicar nada muda; prova falhou = desfaz),
passar a limpo com OK e "Recarregar agora" (recusa com vídeo rodando). Sem IA, sem rede, sem tocar o repositório (RAIZ e ESTUDIO temporários)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import _comum
import melhoria as M
import recarregar as R
import revisao as V

REL = "formatos/estilo-x/base/render.py"
ANTES = "def quadro(t):\n    return t\n"
DEPOIS = "def quadro(t):\n    return max(t, 0)\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        for alvo, valor in (("RAIZ", self.raiz), ("ESTUDIO", self.raiz / "app")):
            p = patch.object(_comum, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        self.apr = self.raiz / "clientes/C/cContent/modelos/m/aprendizado"
        self.apr.mkdir(parents=True)
        (self.raiz / "formatos/estilo-x/base").mkdir(parents=True)
        self.arq = self.raiz / REL
        self.arq.write_text(ANTES, encoding="utf-8")
        self.video = self.raiz / "saida.mp4"
        self.video.write_bytes(b"x")

    def hist(self):
        return _comum.ler_jsonl(self.apr / "historico.jsonl")


class Revisao(Base):
    def job(self, slug="v1"):
        return {"cliente": "C", "slug": slug, "modelo": "m", "saida": "saida.mp4", "sandbox": "sb", "formato": "estilo-x"}

    def rodar(self, achados, slug="v1"):
        ctx = {"saida": self.video, "sandbox": self.raiz / "sb", "pasta_aprendizado": self.apr, "formato": "estilo-x",
               "formato_titulo": "Estilo X", "gravado": False, "proporcao": "9:16"}

        def fake_ia(prompt, pasta):
            (pasta / "revisao-ia.json").write_text(json.dumps({"achados": achados}), encoding="utf-8")
            return 0
        import producao
        with patch.object(producao, "carregar", return_value=self.job(slug)), patch.object(V, "_contexto", return_value=ctx), \
             patch.object(V, "conferencia", return_value=[]), patch.object(V, "regua", return_value=[]), \
             patch.object(V, "folhas", return_value=[]), patch.object(V, "_ia_ok", return_value=True), patch.object(V, "_ia", fake_ia), \
             patch.object(V, "quadro", return_value=False), patch.object(V, "_nota"), \
             patch.object(_comum, "ffprobe", return_value={"duracao": 30.0}):
            return V.rodar("C", slug)

    def test_grava_historico_com_causa_e_conserto(self):
        r = self.rodar([{"t": 12, "tipo": "texto_ilegivel", "o_que": "A legenda some atrás do rosto", "causa": "o motor não mede contraste",
                         "conserto": "medir contraste em render.py antes de desenhar", "mecanico": "nao", "onde": "", "regra_furou": ""}])
        self.assertEqual(r["estado"], "pronta")
        self.assertEqual(len(r["achados"]), 1)
        h = self.hist()
        self.assertEqual(len(h), 1)
        for campo in ("tipo", "categoria", "texto", "origem", "createdAt", "job", "causa", "conserto"):
            self.assertTrue(h[0].get(campo), campo)
        self.assertEqual((h[0]["tipo"], h[0]["origem"], h[0]["job"]), ("revisao", "estudio", "C/v1"))
        self.assertEqual(h[0]["causa"], "o motor não mede contraste")
        self.assertEqual(V.carregar("C", "v1")["achados"][0]["rotulo"], "Texto ilegível ou cortado")

    def test_rodar_de_novo_nao_duplica_a_linha(self):
        a = [{"t": 3, "tipo": "parado_demais", "o_que": "Parado", "causa": "c", "conserto": "k", "mecanico": "nao"}]
        self.rodar(a)
        self.rodar(a)
        self.assertEqual(len(self.hist()), 1)

    def test_tipo_desconhecido_e_segundo_fora_do_video_sao_limpos(self):
        r = self.rodar([{"t": 999, "tipo": "inventado", "o_que": "x", "causa": "c", "conserto": "k", "mecanico": "talvez"}])
        a = r["achados"][0]
        self.assertEqual((a["tipo"], a["mecanico"]), ("outro", "nao"))
        self.assertLess(a["t"], 30)

    def test_so_propoe_melhoria_do_motor_claro_ou_repetido(self):
        claro = {"t": 5, "tipo": "rosto_cortado", "o_que": "Rosto cortado", "causa": "c", "conserto": "k", "mecanico": "claro", "onde": REL}
        r = self.rodar([claro])
        mid = r["achados"][0]["melhoria"]
        self.assertTrue(mid)
        self.assertEqual(M.carregar(mid)["estado"], "proposta")
        prov = {"t": 5, "tipo": "enquadramento", "o_que": "Enquadro ruim", "causa": "c", "conserto": "k", "mecanico": "provavel", "onde": REL}
        self.assertEqual(self.rodar([prov], slug="v2")["achados"][0]["melhoria"], "")   # 1 vídeo só: não basta
        self.rodar([prov], slug="v3")                                                    # 2º vídeo com a mesma falha
        self.assertTrue(V.carregar("C", "v3")["achados"][0]["melhoria"])

    def test_arquivo_fora_do_motor_nao_vira_melhoria(self):
        for onde in ("clientes/C/cContent/modelos/m/aprendizado/regras.json", "../etc/passwd", "app/ferramentas/ia.py", ""):
            self.assertFalse(M.permitido(onde), onde)
        self.assertTrue(M.permitido(REL))


class GateDaMelhoria(Base):
    def proposta(self):
        job = {"cliente": "C", "slug": "v1", "modelo": "m", "sandbox": "sb"}
        ctx = {"formato": "estilo-x", "formato_titulo": "Estilo X", "saida": self.video}
        a = {"t": 5, "tipo": "rosto_cortado", "o_que": "Rosto cortado", "causa": "sem limite", "conserto": "limitar t em zero",
             "onde": REL, "miniatura": "", "repetido_em": 2}
        return M.propor(job, ctx, a)

    def ia_que_escreve(self, texto):
        def fake(prompt, pasta, tipo="melhoria"):
            (pasta / "proposta" / REL).write_text(texto, encoding="utf-8")
            return 0
        return patch.object(M, "_executar_ia", fake)

    def prova_ok(self, testes=((set(), "ok"), (set(), "ok"))):
        return [patch.object(M, "_testes_para", return_value=["t"]), patch.object(M, "_faltas_do_estilo", return_value=set()),
                patch.object(M, "quadro_de_prova", return_value=(True, "quadro ok")),
                patch.object(M, "falhando_nos_testes", side_effect=list(testes))]

    def com(self, patches):
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_sem_aplicar_nenhum_arquivo_muda(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        r = M.carregar(rec["id"])
        self.assertEqual(r["estado"], "pronta")
        self.assertIn("+    return max(t, 0)", r["diff"])
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)   # só a cópia mudou
        M.pedir("agora_nao", rec["id"])
        self.assertEqual(M.carregar(rec["id"])["estado"], "recusada")
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)
        self.assertEqual(M.abertas(), [])

    def test_aplicar_grava_depois_da_prova_e_desfazer_volta(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        self.com(self.prova_ok())
        r = M.aplicar(rec["id"])
        self.assertEqual(r["estado"], "aplicada")
        self.assertEqual(self.arq.read_text(encoding="utf-8"), DEPOIS)
        self.assertTrue(all(p["ok"] for p in r["prova"]["passos"]))
        self.assertEqual([x["tipo"] for x in self.hist()], ["conserto"])   # o conserto aplicado fica no historico (REGRA Nº 2, passo 4)
        M.desfazer(rec["id"])
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)
        self.assertEqual(M.carregar(rec["id"])["estado"], "desfeita")

    def test_teste_que_falha_desfaz_e_diz_o_porque(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        self.com(self.prova_ok(testes=((set(), "ok"), ({"test_contrato (x.Y)"}, "1 com falha"))))
        r = M.aplicar(rec["id"])
        self.assertEqual(r["estado"], "falhou")
        self.assertIn("testes quebraram", r["motivo"])
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)

    def test_falha_que_ja_existia_nao_culpa_a_mudanca(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        velha = {"test_antigo (x.Y)"}
        self.com(self.prova_ok(testes=((velha, "r"), (velha, "r"))))
        self.assertEqual(M.aplicar(rec["id"])["estado"], "aplicada")

    def test_sintaxe_quebrada_desfaz(self):
        rec = self.proposta()
        with self.ia_que_escreve("def quadro(t:\n    return t\n"):
            M.preparar(rec["id"])
        self.com(self.prova_ok())
        r = M.aplicar(rec["id"])
        self.assertEqual(r["estado"], "falhou")
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)

    def test_quadro_de_prova_que_falha_desfaz(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        self.com([patch.object(M, "_testes_para", return_value=[]), patch.object(M, "_faltas_do_estilo", return_value=set()),
                  patch.object(M, "quadro_de_prova", return_value=(False, "o motor com a mudança não renderizou o quadro"))])
        r = M.aplicar(rec["id"])
        self.assertEqual(r["estado"], "falhou")
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)

    def test_ia_que_mexe_no_original_e_desfeita(self):
        rec = self.proposta()

        def malvada(prompt, pasta, tipo="melhoria"):
            self.arq.write_text("lixo\n", encoding="utf-8")
            (pasta / "proposta" / REL).write_text(DEPOIS, encoding="utf-8")
            return 0
        with patch.object(M, "_executar_ia", malvada):
            r = M.preparar(rec["id"])
        self.assertEqual(r["estado"], "falhou")
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)

    def test_arquivo_que_mudou_depois_da_previa_nao_e_pisado(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        self.arq.write_text(ANTES + "# outra frente mexeu\n", encoding="utf-8")
        r = M.aplicar(rec["id"])
        self.assertEqual(r["estado"], "falhou")
        self.assertIn("mudou depois da prévia", r["motivo"])
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES + "# outra frente mexeu\n")

    def test_desfazer_nao_pisa_em_mudanca_posterior(self):
        rec = self.proposta()
        with self.ia_que_escreve(DEPOIS):
            M.preparar(rec["id"])
        self.com(self.prova_ok())
        M.aplicar(rec["id"])
        self.arq.write_text(DEPOIS + "# depois\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            M.desfazer(rec["id"])
        self.assertIn("# depois", self.arq.read_text(encoding="utf-8"))

    def test_mudanca_grande_demais_nao_e_proposta(self):
        rec = self.proposta()
        with self.ia_que_escreve("".join(f"x{i} = {i}\n" for i in range(200))):
            r = M.preparar(rec["id"])
        self.assertEqual(r["estado"], "falhou")
        self.assertIn("grande demais", r["motivo"])
        self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)

    def test_aplicar_direto_sem_ver_prepara_e_aplica(self):
        rec = self.proposta()
        self.com(self.prova_ok())
        with self.ia_que_escreve(DEPOIS), patch.object(M, "disparar"):
            M.pedir("aplicar", rec["id"])      # o clique; o processo próprio é simulado abaixo
            self.assertEqual(self.arq.read_text(encoding="utf-8"), ANTES)   # clicar não muda arquivo: quem muda é o processo
            r = M.preparar(rec["id"])
        self.assertEqual(r["estado"], "aplicada")
        self.assertEqual(self.arq.read_text(encoding="utf-8"), DEPOIS)

    def test_melhoria_aparece_no_esperando_voce(self):
        import pendencias
        rec = self.proposta()
        it = [i for i in pendencias.melhorias() if i["id"] == rec["id"]]
        self.assertEqual(len(it), 1)
        self.assertEqual(it[0]["tipo"], "melhoria")
        self.assertTrue(it[0]["titulo"].startswith("Melhoria sugerida no estilo Estilo X"))

    def test_mesma_melhoria_nao_duplica_e_recusada_cala(self):
        a = self.proposta()
        b = self.proposta()
        self.assertEqual(a["id"], b["id"])
        M.pedir("agora_nao", a["id"])
        self.assertIsNone(self.proposta())


class PassarALimpo(Base):
    def setUp(self):
        super().setUp()
        (self.apr / "regras.json").write_text(json.dumps({"regras": [{"id": "r1", "categoria": "qa", "peso": 5, "texto": "Regra velha."}]}), encoding="utf-8")
        with (self.apr / "historico.jsonl").open("w", encoding="utf-8") as f:
            for i in range(M.LIMITE_HISTORICO + 5):
                f.write(json.dumps({"tipo": "feedback", "categoria": "qa", "texto": f"corrija {i}", "createdAt": "2026-10-29"}) + "\n")

    def test_so_propoe_acima_do_limite_e_nao_mexe_em_nada(self):
        rec = M.propor_regras(self.apr)
        self.assertEqual(rec["tipo"], "regras")
        self.assertEqual(json.loads((self.apr / "regras.json").read_text())["regras"][0]["texto"], "Regra velha.")
        self.assertEqual(M.propor_regras(self.apr)["id"], rec["id"])   # a mesma proposta aberta, sem duplicar

    def test_regras_novas_so_valem_com_ok(self):
        rec = M.propor_regras(self.apr)
        novo = {"regras": [{"id": "r1", "categoria": "qa", "peso": 6, "texto": "Regra velha, reescrita com 12 px."},
                           {"id": "r2", "categoria": "qa", "peso": 5, "texto": "Regra nova."}]}

        def fake(prompt, pasta, tipo="melhoria"):
            (pasta / "proposta" / "regras.json").write_text(json.dumps(novo), encoding="utf-8")
            return 0
        with patch.object(M, "_executar_ia", fake):
            M.preparar(rec["id"])
        r = M.carregar(rec["id"])
        self.assertEqual(r["estado"], "pronta")
        self.assertEqual([x["id"] for x in r["regras_novas"]], ["r2"])
        self.assertEqual([x["id"] for x in r["regras_reescritas"]], ["r1"])
        self.assertEqual(json.loads((self.apr / "regras.json").read_text())["regras"][0]["texto"], "Regra velha.")   # sem OK, nada muda
        r = M.aplicar(rec["id"])
        self.assertEqual(r["estado"], "aplicada")
        self.assertEqual(len(json.loads((self.apr / "regras.json").read_text())["regras"]), 2)
        self.assertIsNone(M.propor_regras(self.apr))   # o que já virou regra não pede de novo
        M.desfazer(rec["id"])
        self.assertEqual(json.loads((self.apr / "regras.json").read_text())["regras"][0]["texto"], "Regra velha.")

    def test_ia_que_estoura_o_teto_de_regras_nao_vale(self):
        rec = M.propor_regras(self.apr)
        gordo = {"regras": [{"id": f"r{i}", "categoria": "qa", "texto": f"t{i}"} for i in range(30)]}

        def fake(prompt, pasta, tipo="melhoria"):
            (pasta / "proposta" / "regras.json").write_text(json.dumps(gordo), encoding="utf-8")
            return 0
        with patch.object(M, "_executar_ia", fake):
            r = M.preparar(rec["id"])
        self.assertEqual(r["estado"], "falhou")


class Recarregar(Base):
    def test_recusa_com_video_rodando_e_agenda(self):
        with patch.object(R, "ocupado", return_value=["1 etapa(s) de vídeo na fila ou rodando"]), patch.object(R, "agendar_saida") as sai:
            r = R.pedir()
        self.assertFalse(r["recarregando"])
        self.assertTrue(r["agendado"])
        self.assertTrue(R.agendado())
        sai.assert_not_called()

    def test_livre_reinicia(self):
        with patch.object(R, "ocupado", return_value=[]), patch.object(R, "agendar_saida") as sai:
            r = R.pedir()
        self.assertTrue(r["recarregando"])
        sai.assert_called_once()
        self.assertFalse(R.agendado())

    def test_vigia_espera_acabar_e_reinicia_sozinho(self):
        _comum.gravar_json(R._flag(), {"em": "agora"})
        with patch.object(R, "ocupado", side_effect=[["vídeo"], []]), patch.object(R, "reiniciar") as rei, \
             patch.object(R.time, "sleep", side_effect=[None, None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                R.vigiar(0)
        rei.assert_called_once()          # 1ª volta ocupado: não; 2ª livre: sim
        self.assertFalse(R.agendado())

    def test_vigia_sem_pedido_nao_reinicia(self):
        with patch.object(R, "ocupado", return_value=[]), patch.object(R, "reiniciar") as rei, \
             patch.object(R.time, "sleep", side_effect=[None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                R.vigiar(0)
        rei.assert_not_called()

    def test_ocupado_ve_a_fila(self):
        import fila
        with patch.object(fila, "ler", return_value=[{"estado": "rodando"}]):
            self.assertTrue(any("fila" in x for x in R.ocupado()))
        with patch.object(fila, "ler", return_value=[{"estado": "concluido"}]):
            self.assertEqual(R.ocupado(), [])


if __name__ == "__main__":
    unittest.main()
