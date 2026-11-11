"""Editar vídeo gravado por cena: o núcleo (editor_gravados), o python da venv nos filhos, Caixinha / Crítica / Análise de tela e o
modo livre. Sandboxes sintéticas em pasta temporária; vídeos de 2 a 4 s feitos com ffmpeg lavfi."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ferramentas"))
import _comum  # noqa: E402
import editor  # noqa: E402
import editor_gravados  # noqa: E402
from editor_gravados import analise_de_tela, caixinha_de_perguntas, critica_ao_absurdo, livre  # noqa: E402


def video(f: Path, cor="red", seg=4.0, extra="") -> Path:
    """mp4 de `seg` s, 1080x1920 pequeno (180x320), com áudio; `extra` = filtro de vídeo."""
    Path(f).parent.mkdir(parents=True, exist_ok=True)
    vf = ["-vf", extra] if extra else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={cor}:s=180x320:r=10:d={seg}",
                    "-f", "lavfi", "-i", f"sine=f=300:d={seg}", *vf, "-shortest", "-pix_fmt", "yuv420p", str(f)], check=True)
    return Path(f)


def modelo(raiz: Path, nome: str, slug: str = "x") -> Path:
    p = raiz / "clientes" / "C" / "cContent" / "modelos" / nome / f"_sandbox-{slug}"
    (p / "work").mkdir(parents=True)
    return p


def saida(p: Path) -> Path:
    return p.parents[2] / "output" / p.parent.name / f"{p.name.removeprefix('_sandbox-')}.mp4"


def palavras(f: Path, n=24, passo=.5):   # passo 1,0 = uma frase a cada 3 s (cenas de 3 s)
    """Uma frase por ~3 s: palavras a cada `passo` s, ponto final a cada 6."""
    ws = [{"word": ("fim." if i % 6 == 5 else "fala"), "start": round(i * passo, 2), "end": round(i * passo + .3, 2)} for i in range(n)]
    f.write_text(json.dumps({"words": ws}), encoding="utf-8")


class Nucleo(unittest.TestCase):
    def test_carregar_junta_os_specs_e_pula_modulo_quebrado(self):
        import io
        real = editor_gravados.importlib.import_module

        def falha(nome, *a, **k):
            if nome.endswith(".livre"):
                raise RuntimeError("quebrou")
            return real(nome, *a, **k)
        err = io.StringIO()
        with mock.patch.object(editor_gravados.importlib, "import_module", falha), mock.patch("sys.stderr", err):
            specs = editor_gravados.carregar()
        self.assertNotIn("_livre", specs)
        self.assertIn("caixinha-de-perguntas", specs)
        self.assertIn("pulei livre", err.getvalue())
        self.assertTrue(all(s["gravado"] for s in specs.values()))

    def test_os_gravados_conhecidos_estao_no_editor(self):
        for slug in ("caixinha-de-perguntas", "critica-ao-absurdo", "analise-de-tela", "faixa-com-cenas", "_livre"):
            self.assertIn(slug, editor.MOTORES)
        self.assertEqual(editor.ainda_nao(), [])

    def test_com_venv_poe_a_venv_na_frente_e_o_python3_do_filho_e_o_dela(self):
        env = _comum.com_venv({"PATH": "/opt/homebrew/bin:/usr/bin"})
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(_comum.VENV_BIN))
        self.assertEqual(env["PATH"].split(os.pathsep).count(str(_comum.VENV_BIN)), 1)
        # do jeito que o ia.py abre o Claude: brew na frente, depois a venv na frente de tudo
        base = dict(os.environ, PATH="/opt/homebrew/bin:/usr/local/bin:" + os.environ["PATH"])
        r = subprocess.run(["zsh", "-c", "python3 -c 'import PIL, numpy, sys; print(sys.prefix)'"], env=_comum.com_venv(base),
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(r.stdout.strip()).resolve(), (_comum.ESTUDIO / ".venv").resolve())

    def test_ia_executar_usa_a_venv(self):
        import ia
        self.assertIn("com_venv", Path(ia.__file__).read_text(encoding="utf-8"))

    def test_atualizar_confere_o_ambiente(self):
        import atualizar
        ok, nota = atualizar.ambiente_python()
        self.assertTrue(ok, nota)

    def test_versao_guarda_e_volta_todos_os_arquivos(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = modelo(raiz, "analise-de-tela")
            video(p / "work" / "joao.mp4"); video(p / "work" / "tela.mp4"); (p.parent / "gerar.sh").write_text("")
            (p / "comando.sh").write_text('zsh ../gerar.sh --dir . --titulo "A|B"\n')
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: "analise-de-tela"), \
                    mock.patch.dict(editor.MOTORES["analise-de-tela"], {"arquivos": ["comando.sh", "work/extra.txt"]}):
                (p / "work" / "extra.txt").write_text("um")
                v1 = editor.guardar_versao(p, "original")
                (p / "comando.sh").write_text("mudou"); (p / "work" / "extra.txt").write_text("dois")
                editor.voltar(p, v1)
                self.assertEqual((p / "comando.sh").read_text(), 'zsh ../gerar.sh --dir . --titulo "A|B"\n')
                self.assertEqual((p / "work" / "extra.txt").read_text(), "um")
                self.assertEqual(len(editor.versoes(p)), 2)   # a de agora continua guardada

    def test_lista_mostra_o_que_nao_edita_com_o_motivo(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = modelo(raiz, "algum-modelo", "a-mao")
            video(saida(p), seg=2)
            (p / "work" / "joao.mp4").write_bytes(b"")
            q = modelo(raiz, "algum-modelo", "sem-nada")   # sem vídeo pronto: nem aparece
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q_: ""):
                lista = editor.videos()
            self.assertEqual([(v["nome"], v["pode"]) for v in lista], [("a-mao", False)])
            self.assertEqual(lista[0]["motivo"], "Montado à mão, sem o comando que refaz o vídeo.")

    def test_spec_gravado_com_fonte_cenas_json_aparece_editavel(self):
        """Lista de estáticos: gravado, mas o arquivo das cenas também se chama cenas.json (não é motor)."""
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = modelo(raiz, "sintetico")
            video(p / "work" / "joao.mp4", seg=3); video(saida(p), seg=3)
            (p / "cenas.json").write_text("{}")
            spec = {"gravado": True, "fonte": "cenas.json", "precisa": ["work/joao.mp4"],
                    "ler": lambda q: {"titulo": "Sintético", "saida": str(saida(q)), "duracao": 3, "cenas": [{"de": 0, "tipo": "x"}]},
                    "gravar": lambda q, doc: None, "cmd": lambda q: (["true"], q), "rotulos": {}, "tipos": {}, "juntos": {}, "sugestoes": [], "dicas": ""}
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: "sintetico"), \
                    mock.patch.dict(editor.MOTORES, {"sintetico": spec}):
                self.assertTrue(editor.gravado(p))
                self.assertEqual(editor.motivo_sem_edicao(p), "")
                lista = editor.videos()
                self.assertEqual([(v["nome"], v["pode"]) for v in lista], [("x", True)])

    def test_estilo_que_saiu_do_catalogo_tem_nome_na_lista(self):
        with tempfile.TemporaryDirectory() as d:
            p = modelo(Path(d), "frase-fixa")
            self.assertEqual(editor.titulo_do_estilo(p), "Frase fixa")
            self.assertEqual(editor.titulo_do_estilo(modelo(Path(d), "algum-outro-modelo", "y")), "Algum outro modelo")

    def test_formato_da_pasta_de_modelo_sem_formato(self):
        with tempfile.TemporaryDirectory() as d:
            p = modelo(Path(d), "formato-que-saiu")
            self.assertEqual(editor.formato_da_pasta(p), "")           # gravado (tem work/, sem cenas.json)
            (p / "cenas.json").write_text("{}")
            self.assertEqual(editor.formato_da_pasta(p), "editorial")  # motor


class Caixinha(unittest.TestCase):
    def _sandbox(self, raiz, tipo="caixinha"):
        p = modelo(raiz, "caixinha-de-perguntas" if tipo == "caixinha" else "frase-fixa")
        video(p / "work" / "joao.mp4", seg=20)
        palavras(p / "work" / "words.json", n=40)
        c = {"video": str(p.relative_to(raiz) / "work" / "joao.mp4"), "saida": "out/x.mp4", "texto": "q vc acha?", "y": 255}
        if tipo == "caixinha":
            c.update(tipo="caixinha", titulo="O que você quer saber?", posicao="cima")
        else:
            c.update(fonte="Barlow SemiBold", tamanho=60)
        (p / "camada.json").write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        return p

    def _ctx(self, raiz, p):
        return (mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(caixinha_de_perguntas, "RAIZ", raiz))

    def test_ler_cenas_da_fala_e_ida_e_volta_nao_muda(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b = self._ctx(raiz, p)
            with a, b:
                self.assertTrue(editor.pasta(editor.rel(p)))
                doc = editor._doc(p)
                self.assertGreaterEqual(len(doc["cenas"]), 3)
                self.assertEqual(doc["pergunta"], "q vc acha?")
                self.assertTrue(all(3 <= c2["de"] - c1["de"] <= 9 for c1, c2 in zip(doc["cenas"], doc["cenas"][1:])))
                antes = (p / "camada.json").read_text()
                editor._gravar(p, doc)
                self.assertEqual((p / "camada.json").read_text(), antes)
                self.assertEqual(editor.cenas(p)[0]["elementos"][0]["campo"], "pergunta")
                cmd, cwd = editor._cmd_gravado(p)
                self.assertEqual(cmd[1:3], [str(caixinha_de_perguntas.CAMADA), "renderizar"])

    def test_trocar_a_pergunta_so_com_o_elemento_marcado(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b = self._ctx(raiz, p)
            with a, b:
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois.update(pergunta="Dá pra ter cliente petista?", y=999)
                sp = editor.spec(p)
                ok, avisos = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "pergunta"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["pergunta"], ok["y"]), ("Dá pra ter cliente petista?", 255))
                editor._gravar(p, ok)
                c = json.loads((p / "camada.json").read_text())
                self.assertEqual((c["texto"], c["y"], c["tipo"]), ("Dá pra ter cliente petista?", 255, "caixinha"))

    def test_zoom_por_cena_vira_punch_livres(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b = self._ctx(raiz, p)
            with a, b:
                doc = editor._doc(p)
                de1, de2 = doc["cenas"][1]["de"], doc["cenas"][2]["de"]
                doc["cenas"][1]["zoom"] = "nao"
                editor._gravar(p, doc)
                livres = json.loads((p / "camada.json").read_text())["punch_livres"]
                self.assertEqual(livres[0][1], de1)
                self.assertEqual(livres[1][0], de2)
                self.assertEqual([c["zoom"] for c in editor._doc(p)["cenas"]][:3], ["sim", "nao", "sim"])   # volta igual
                doc["cenas"][1]["zoom"] = "sim"
                editor._gravar(p, doc)
                self.assertNotIn("punch_livres", json.loads((p / "camada.json").read_text()))   # tudo com zoom = o padrão

    def test_frase_fixa_acha_pela_camada(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz, "frase")
            a, b = self._ctx(raiz, p)
            with a, b, mock.patch.object(editor, "formato_da_pasta", lambda q: ""):
                self.assertTrue(editor.pasta(editor.rel(p)))
                self.assertIs(editor.spec(p), editor.MOTORES["frase-fixa"])
                doc = editor._doc(p)
                self.assertEqual((doc["frase"], doc["tamanho"]), ("q vc acha?", 60))
                self.assertNotIn("zoom", doc["cenas"][0])
                doc["frase"] = "Outra"
                editor._gravar(p, doc)
                self.assertEqual(json.loads((p / "camada.json").read_text())["texto"], "Outra")

    def test_sem_video_de_trabalho_nao_edita(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            (p / "work" / "joao.mp4").unlink()
            a, b = self._ctx(raiz, p)
            with a, b:
                self.assertIsNone(editor.pasta(editor.rel(p)))


class Critica(unittest.TestCase):
    def _sandbox(self, raiz, com_plano=True):
        p = modelo(raiz, "critica-ao-absurdo", "teste")
        (p.parent / "gerar.sh").write_text("")
        video(p / "work" / "absurdo.mp4", seg=60)
        video(p / "work" / "joao.mp4", seg=5)
        (p / "work" / "legenda").mkdir()
        palavras(p / "work" / "legenda" / "words.json", n=40)
        (p / "comando.sh").write_text("cd clientes/x && zsh ../gerar.sh --dir . --de 1:10 --ate 1:35 --sem-legenda --foco-x 0.4\n")
        if com_plano:
            (p / "PLANO.json").write_text(json.dumps({"de": "1:10", "ate": "1:35", "sem_legenda": True, "foco_x": 0.4, "ideia": "x"}))
        return p

    def test_ler_cenas_resposta_e_comando(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            with mock.patch.object(editor, "RAIZ", raiz):
                self.assertTrue(editor.pasta(editor.rel(p)))
                doc = editor._doc(p)
                self.assertEqual((doc["trecho_de"], doc["trecho_ate"], doc["sem_legenda"], doc["foco_x"]), (70, 95, True, .4))
                self.assertEqual(doc["cenas"][-1]["tipo"], "resposta")
                self.assertAlmostEqual(doc["duracao"], 25 + 5, places=1)
                cmd, cwd = editor._cmd_gravado(p)
                self.assertEqual(cmd[:5], ["zsh", "../gerar.sh", "--dir", ".", "--saida"])
                self.assertIn("--sem-legenda", cmd)
                self.assertEqual(cmd[cmd.index("--de") + 1], "70")
                self.assertEqual(cwd, p)

    def test_le_do_comando_quando_nao_tem_plano(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz, com_plano=False)
            with mock.patch.object(editor, "RAIZ", raiz):
                self.assertTrue(editor.pasta(editor.rel(p)))
                self.assertEqual(editor._doc(p)["trecho_ate"], 95)

    def test_gravar_muda_plano_e_comando_e_ida_e_volta_nao_mexe(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            with mock.patch.object(editor, "RAIZ", raiz):
                antes = ((p / "PLANO.json").read_text(), (p / "comando.sh").read_text())
                doc = editor._doc(p)
                editor._gravar(p, doc)
                self.assertEqual(((p / "PLANO.json").read_text(), (p / "comando.sh").read_text()), antes)
                doc.update(trecho_de=75.5, sem_resposta=True, sem_legenda=False)
                editor._gravar(p, doc)
                pl = json.loads((p / "PLANO.json").read_text())
                self.assertEqual((pl["de"], pl["ate"], pl["sem_legenda"], pl["sem_resposta"], pl["ideia"]), (75.5, 95, False, True, "x"))
                cm = (p / "comando.sh").read_text()
                self.assertIn("--de 75.5", cm)
                self.assertIn("--sem-resposta", cm)
                self.assertNotIn("--sem-legenda", cm)
                self.assertEqual(editor._doc(p)["cenas"][-1]["tipo"], "trecho")   # sem resposta: não tem cena de resposta

    def test_trecho_so_com_o_elemento_trecho(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            with mock.patch.object(editor, "RAIZ", raiz):
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois.update(trecho_de=80, sem_legenda=False)
                sp = editor.spec(p)
                ok, _ = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "trecho"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["trecho_de"], ok["sem_legenda"]), (80, True))


class Analise(unittest.TestCase):
    CMD = 'cd clientes/x && zsh ../gerar.sh --dir . --titulo "A FRASE|DA FAIXA" --faixa-ate 13 --tela-x 0.3 --rosto-fixo --cam-y 0.4 --legenda w.json\n'

    def _sandbox(self, raiz):
        p = modelo(raiz, "analise-de-tela", "t")
        (p.parent / "gerar.sh").write_text("")
        video(p / "work" / "joao.mp4", seg=20); video(p / "work" / "tela.mp4", seg=20)
        palavras(p / "work" / "words.json", n=40)
        (p / "comando.sh").write_text(self.CMD)
        return p

    def test_ler_gravar_preserva_o_que_o_editor_nao_conhece(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            with mock.patch.object(editor, "RAIZ", raiz):
                self.assertTrue(editor.pasta(editor.rel(p)))
                doc = editor._doc(p)
                self.assertEqual((doc["frase"], doc["tela_x"], doc["tela_modo"], doc["corte"], doc["rosto_fixo"]), ("A FRASE|DA FAIXA", .3, "cover", 960, True))
                editor._gravar(p, doc)
                self.assertEqual((p / "comando.sh").read_text(), self.CMD)   # sem mudança, o arquivo nem é tocado
                doc.update(tela_modo="fit", tela_zoom=1.2, frase="NOVA|FRASE", rosto_fixo=False)
                editor._gravar(p, doc)
                cm = (p / "comando.sh").read_text()
                for trecho in ("--tela-modo fit", "--tela-zoom 1.2", "'NOVA|FRASE'", "--faixa-ate 13", "--legenda w.json", "--cam-y 0.4"):
                    self.assertIn(trecho, cm)
                self.assertNotIn("--rosto-fixo", cm)
                self.assertTrue(cm.startswith("cd clientes/x && zsh ../gerar.sh"))

    def test_comando_do_render_sem_previa_e_com_saida(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            (p / "comando.sh").write_text(self.CMD.strip() + " --previa\n")
            with mock.patch.object(editor, "RAIZ", raiz):
                cmd, cwd = editor._cmd_gravado(p)
                self.assertNotIn("--previa", cmd)
                self.assertEqual(cmd[cmd.index("--saida") + 1], str(saida(p)))
                self.assertEqual(cmd[cmd.index("--titulo") + 1], "A FRASE|DA FAIXA")

    def test_fiel_enquadramento_nao_muda_a_frase(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            with mock.patch.object(editor, "RAIZ", raiz):
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois.update(tela_modo="fit", frase="NÃO")
                sp = editor.spec(p)
                ok, avisos = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "tela"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["tela_modo"], ok["frase"]), ("fit", "A FRASE|DA FAIXA"))


class Livre(unittest.TestCase):
    MONTAR = """#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"
read A B < janela.txt
OUT=../../../output/%s/x.mp4; mkdir -p "${OUT:h}"
ffmpeg -y -v error -f lavfi -i color=c=red:s=180x320:r=10:d=12 -f lavfi -i sine=f=300:d=12 -vf "drawbox=x=0:y=0:w=180:h=160:color=blue:t=fill:enable='between(t,$A,$B)'" -shortest -pix_fmt yuv420p "$OUT"
"""

    def _sandbox(self, raiz):
        p = modelo(raiz, "montado-a-mao")
        (p / "janela.txt").write_text("1.0 1.5\n")
        (p / "montar.sh").write_text(self.MONTAR % "montado-a-mao")
        video(p / "work" / "joao.mp4", seg=12)
        subprocess.run(["zsh", str(p / "montar.sh")], check=True)
        return p

    def _rodar(self, raiz, p, ped, mexe):
        """roda editor.rodar com uma 'IA' que executa `mexe(p)`."""
        def ia_falsa(prompt, log, raw, pid, s=None, tipo=None):
            mexe(p)
            log.write_text(""); raw.write_text("")
            return 0
        d = p / "editor" / "pedidos"
        d.mkdir(parents=True, exist_ok=True)
        (d / "p1.json").write_text(json.dumps(dict(ped, texto="muda", print="", modelo="", esforco="")))
        import ia
        with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(livre, "RAIZ", raiz), \
                mock.patch.object(editor, "formato_da_pasta", lambda q: ""), mock.patch.object(ia, "executar", ia_falsa), \
                mock.patch.object(ia, "para_alteracao", lambda **k: {}):
            code = editor.rodar(p, "p1")
            return code, editor.estado(p)

    def test_acha_o_comando_e_as_cenas(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(livre, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: ""):
                self.assertIs(editor.spec(p), editor.MOTORES["_livre"])
                self.assertTrue(editor.pasta(editor.rel(p)))
                cs = editor.cenas(p)
                self.assertGreaterEqual(len(cs), 1)
                self.assertEqual(cs[0]["elementos"], [])
                self.assertEqual(editor.fonte(p).name, "montar.sh")
                self.assertIn("janela.txt", editor.arquivos(p))

    def test_script_que_cita_arquivo_que_nao_existe_nao_edita(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            (p / "montar.sh").write_text(self.MONTAR % "montado-a-mao" + "# usa work/sumiu.mp4\n")
            with mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(livre, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: ""):
                self.assertIsNone(editor.pasta(editor.rel(p)))
                self.assertIn("work/sumiu.mp4", editor.motivo_sem_edicao(p))

    def test_mudanca_dentro_da_cena_vale(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            # a cena 1 vai de 0 a ~3 s (palavras a cada 0,5 s): muda a janela azul dentro dela
            palavras(p / "work" / "words.json", n=12, passo=1.0)
            code, est = self._rodar(raiz, p, {"escopo": "cena", "n": 1, "n_fim": None, "campo": ""},
                                    lambda q: (q / "janela.txt").write_text("1.0 2.0\n"))
            self.assertEqual((code, est.get("erro")), (0, ""), est)
            self.assertEqual((p / "janela.txt").read_text(), "1.0 2.0\n")
            with mock.patch.object(editor, "RAIZ", raiz):
                self.assertEqual(len(editor.versoes(p)), 2)

    def test_mudanca_que_vaza_volta_tudo(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            palavras(p / "work" / "words.json", n=12, passo=1.0)
            antes = saida(p).read_bytes()
            code, est = self._rodar(raiz, p, {"escopo": "cena", "n": 1, "n_fim": None, "campo": ""},
                                    lambda q: (q / "janela.txt").write_text("0.2 6.0\n"))   # a faixa azul passa da cena
            self.assertEqual(code, 1)
            self.assertIn("A mudança passou da cena 1; voltei como estava.", est["erro"])
            self.assertEqual((p / "janela.txt").read_text(), "1.0 1.5\n")
            self.assertEqual(saida(p).read_bytes(), antes)   # o vídeo também volta
            self.assertFalse(est["rodando"])

    def test_video_todo_so_confere_a_duracao(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            code, est = self._rodar(raiz, p, {"escopo": "video", "n": None, "n_fim": None, "campo": ""},
                                    lambda q: (q / "janela.txt").write_text("0.2 3.9\n"))
            self.assertEqual((code, est.get("erro")), (0, ""), est)

    def test_duracao_diferente_volta(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            palavras(p / "work" / "words.json", n=12, passo=1.0)
            antes = (p / "montar.sh").read_text()
            code, est = self._rodar(raiz, p, {"escopo": "video", "n": None, "n_fim": None, "campo": ""},
                                    lambda q: (q / "montar.sh").write_text((q / "montar.sh").read_text().replace("d=12", "d=14")))
            self.assertEqual(code, 1)
            self.assertIn("A duração do vídeo mudou", est["erro"])
            self.assertEqual((p / "montar.sh").read_text(), antes)

    def test_ia_que_nao_mexe_em_nada_e_nada_mudou(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            code, est = self._rodar(raiz, p, {"escopo": "video", "n": None, "n_fim": None, "campo": ""}, lambda q: None)
            self.assertEqual(code, 1)
            self.assertIn("Nada mudou", est["erro"])

    def test_comando_que_falha_volta_os_arquivos(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            code, est = self._rodar(raiz, p, {"escopo": "video", "n": None, "n_fim": None, "campo": ""},
                                    lambda q: (q / "janela.txt").write_text("lixo"))   # o `read A B` vira A=lixo, B vazio → ffmpeg erra
            self.assertEqual(code, 1)
            self.assertIn("voltei como estava", est["erro"])
            self.assertEqual((p / "janela.txt").read_text(), "1.0 1.5\n")


if __name__ == "__main__":
    unittest.main()
