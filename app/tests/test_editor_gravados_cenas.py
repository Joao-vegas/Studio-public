"""Editar vídeo por cena nos 4 estilos gravados: Tela dividida, Fala com cenas, Chamada na tela e Lista de estáticos.
Vídeos sintéticos curtos (ffmpeg lavfi) em pasta temporária; os scripts dos modelos que seriam pesados (gerar.sh, tela.py) viram dublês
que só gravam o que receberam. A Lista de estáticos roda o render_lista.py de verdade (é curto)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ferramentas"))
import editor  # noqa: E402
from editor_gravados import chamada_na_tela as chamada  # noqa: E402
from editor_gravados import fala_com_cenas as fala  # noqa: E402
from editor_gravados import lista_de_estaticos as lista  # noqa: E402
from editor_gravados import tela_dividida as tela  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent.parent
TELA_PY = RAIZ / "clientes" / "Cliente1" / "cliente1Content" / "modelos" / "chamada-na-tela" / "tela.py"


def sintetico(destino: Path, seg: float = 6, tam: str = "1080x1920", audio: bool = True, fps: int = 30) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    ent = ["-f", "lavfi", "-i", f"testsrc2=size={tam}:rate={fps}:duration={seg}"]
    if audio:
        ent += ["-f", "lavfi", "-i", f"sine=frequency=300:duration={seg}"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ent, "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    *(["-c:a", "aac", "-shortest"] if audio else ["-an"]), str(destino)], check=True)
    return destino


def duracao(f: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(f)], text=True))


def quadros(f: Path) -> int:
    return int(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                        "stream=nb_read_frames", "-of", "default=nk=1:nw=1", str(f)], text=True))


def ctx(raiz: Path, slug: str):
    return (mock.patch.object(editor, "RAIZ", raiz), mock.patch.object(editor, "formato_da_pasta", lambda q: slug))


def palavras_groq(arq: Path, itens: list[tuple[str, float]]) -> None:
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps({"words": [{"word": w, "start": t, "end": t + 0.3} for w, t in itens]}), encoding="utf-8")


# ───────────────────────── Tela dividida ─────────────────────────

PLANO_TD = {"manchete": "A SITUAÇÃO TÁ FEIA", "resumo": "A SITUAÇÃO TÁ FEIA: resumo", "beats": [
    {"id": "b1", "inicio": 0.4, "fim": 2.0, "tipo": "broll", "fala": "um", "opcoes": [{"id": "b1-1", "arquivo": "brolls/um.mp4", "trecho": "1-4"}], "escolha": "b1-1"},
    {"id": "b2", "inicio": 2.0, "fim": 4.0, "tipo": "broll", "fala": "dois", "opcoes": [{"id": "b2-1", "arquivo": "brolls/dois.mp4"}], "escolha": "b2-1"},
    {"id": "b3", "inicio": 4.0, "fim": 6.0, "tipo": "broll", "fala": "tres", "opcoes": [{"id": "b3-1", "arquivo": None}], "escolha": "b3-1"},
    {"id": "f", "inicio": 5.0, "fim": 5.5, "tipo": "card", "fala": "x"}]}
COMANDO_TD = 'cd clientes/C/cContent/modelos/reel-dividido-por-video/_sandbox-x && zsh ../gerar.sh --dir . --titulo "A SITUAÇÃO TÁ FEIA" --srcs work/master.mp4 --takes "0,3" --step 3.0 --joao-h 1056 --video-offset-y 330\n'
# gerar.sh de mentira: grava os argumentos e copia o master como saída <ts>.mp4 (como o do João, sem --out)
GERAR_TD = '''#!/bin/zsh
SELF="$(cd "$(dirname "$0")" && pwd)"
echo "$@" > "$SELF/args.txt"
mkdir -p "$SELF/../../output/reel-dividido-por-video"
cp work/master.mp4 "$SELF/../../output/reel-dividido-por-video/20261030-120000.mp4"
'''


class TelaDividida(unittest.TestCase):
    def _sandbox(self, raiz: Path) -> Path:
        p = raiz / "clientes" / "C" / "cContent" / "modelos" / "reel-dividido-por-video" / "_sandbox-x"
        sintetico(p / "work" / "joao.mp4", 6)
        sintetico(p / "work" / "master.mp4", 6, "1080x594", audio=False)
        sintetico(p / "brolls" / "um.mp4", 5, "640x360", audio=False)
        sintetico(p / "brolls" / "dois.mp4", 1.5, "640x360", audio=False)   # curto: a cena de 2 s repete
        sintetico(p / "brolls" / "novo.mp4", 4, "1280x720", audio=False)
        palavras_groq(p / "work" / "words.json", [("um", .5), ("dois", 2.2), ("tres", 4.1)])
        (p / "PLANO.json").write_text(json.dumps(PLANO_TD), encoding="utf-8")
        (p / "comando.sh").write_text(COMANDO_TD, encoding="utf-8")
        (p.parent / "gerar.sh").write_text(GERAR_TD, encoding="utf-8")
        return p

    def test_ler_deriva_as_cenas_dos_beats_e_cobre_o_video_todo(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = tela.ler(p)
            self.assertEqual([c["de"] for c in doc["cenas"]], [0, 2, 4])          # o 1º começa em 0; o card não é cena de baixo
            self.assertEqual(doc["cenas"][0]["clipe"], "brolls/um.mp4")
            self.assertAlmostEqual(doc["cenas"][0]["inicio"], 0.6)                 # o 1º momento passa a começar em 0 (era 0.4): o clipe volta 0,4 s junto
            self.assertEqual(doc["cenas"][2]["clipe"], "work/master.mp4")           # sem clipe conhecido: o próprio master
            self.assertEqual((doc["manchete"], doc["joao_h"], doc["video_offset_y"]), ("A SITUAÇÃO TÁ FEIA", 1056, 330))
            self.assertAlmostEqual(doc["duracao"], 6, delta=.1)

    def test_ida_e_volta_estavel_e_comando_reescrito(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = tela.ler(p)
            tela.gravar(p, doc)
            plano1, cmd1 = (p / "PLANO.json").read_text(), (p / "comando.sh").read_text()
            self.assertEqual(tela.ler(p)["cenas"], doc["cenas"])
            tela.gravar(p, tela.ler(p))
            self.assertEqual(((p / "PLANO.json").read_text(), (p / "comando.sh").read_text()), (plano1, cmd1))   # 2ª passada não muda nada
            self.assertIn("--takes 0,3", cmd1)   # 6 s / 3 s
            self.assertIn("--joao-h 1056", cmd1)
            self.assertTrue(cmd1.startswith("cd clientes/C/cContent"))
            self.assertEqual(json.loads(plano1)["beats"], PLANO_TD["beats"])   # o resto do PLANO fica

    def test_gravar_troca_clipe_manchete_e_enquadramento(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = tela.ler(p)
            doc["cenas"][1].update(clipe="brolls/novo.mp4", inicio=1.5)
            doc.update(manchete="OUTRA COISA", video_offset_y=300, cta="COMENTE 'COLA'", cta_t=4.5)
            doc.pop("joao_h")
            tela.gravar(p, doc)
            c = (p / "comando.sh").read_text()
            for esperado in ("'OUTRA COISA'", "--video-offset-y 300", "--cta 'COMENTE '\"'\"'COLA'\"'\"''", "--cta-t 4.5"):
                self.assertIn(esperado, c)
            self.assertNotIn("--joao-h", c)
            novo = tela.ler(p)
            self.assertEqual((novo["cenas"][1]["clipe"], novo["cenas"][1]["inicio"], novo["manchete"]), ("brolls/novo.mp4", 1.5, "OUTRA COISA"))

    def test_master_tem_a_duracao_do_video_e_o_tamanho_do_bloco_de_baixo(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = tela.ler(p)
            doc["cenas"][1].update(clipe="brolls/novo.mp4", inicio=1.0)
            ren = tela._render(p, {})
            m = tela.montar_master(p, doc, ren)
            self.assertEqual(quadros(m), 6 * 30)                      # exato: nenhuma cena acumula erro
            larg = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(m)], text=True).strip()
            self.assertEqual(larg, "1080,594")                       # 1920 - 1056 - 270
            self.assertTrue((p / "work" / "master-base.mp4").is_file())   # o master da produção ficou guardado
            self.assertFalse(list((p / "work").glob(".master-*")))        # nada temporário sobrou

    def test_refazer_roda_o_gerar_e_leva_o_video_pra_saida(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            tela.gravar(p, tela.ler(p))
            self.assertEqual(tela.refazer(p), 0)
            self.assertTrue(tela.saida(p).is_file())
            self.assertEqual(tela.saida(p), Path(d) / "clientes" / "C" / "cContent" / "output" / "reel-dividido-por-video" / "x.mp4")
            args = (p.parent / "args.txt").read_text()
            self.assertIn("--srcs work/master.mp4", args)
            self.assertNotIn("20261030-120000", [q.stem for q in tela.saida(p).parent.glob("*.mp4")])   # o <ts>.mp4 virou o slug.mp4

    def test_editor_elementos_fiel_e_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b = ctx(raiz, "tela-dividida")
            with a, b:
                self.assertTrue(editor.gravado(p))
                self.assertTrue(editor.pasta(editor.rel(p)))
                cs = editor.cenas(p)
                self.assertEqual([e["campo"] for e in cs[0]["elementos"]], ["clipe", "inicio", "manchete", "cta", "enquadramento"])
                sp = editor.spec(p)
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois["cenas"][1].update(clipe="brolls/novo.mp4", inicio=2, de=2.5)
                depois["cenas"][0]["clipe"] = "fora.mp4"
                depois["manchete"] = "NÃO PODE"
                ok, avisos = editor._fiel(antes, depois, {"escopo": "elemento", "n": 2, "campo": "clipe"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["cenas"][1]["clipe"], ok["cenas"][1]["inicio"], ok["cenas"][1]["de"]), ("brolls/novo.mp4", 2, 2))
                self.assertEqual((ok["cenas"][0]["clipe"], ok["manchete"]), ("brolls/um.mp4", "A SITUAÇÃO TÁ FEIA"))
                self.assertTrue(avisos)
                ok, _ = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "manchete"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["manchete"], ok["cenas"][0]["clipe"]), ("NÃO PODE", "brolls/um.mp4"))
                t = editor.prompt(p, {"escopo": "cena", "n": 2, "n_fim": None, "campo": "", "texto": "troca", "print": ""})
                self.assertIn("editor/cenas.json", t)
                self.assertIn("a cena de baixo nunca fica sem clipe", t)
                self.assertNotIn("{arq_ia}", t)


# ───────────────────────── Fala com cenas ─────────────────────────

BEATS = "broll:4-8:brolls/cuts/b1.mp4@2;card:11-14:PARECE *MELHOR*;punch:16-20;card:22-24:@brolls/cards/b4.mp4;broll:30-34:brolls/x.mp4@1;punch:31-33"
COMANDO_FC = ('cd clientes/C/cContent/modelos/dividido-mascara/_sandbox-x && zsh ../gerar.sh --dir . '
              f'--music assets/m.mp3 --legy 900 --band-h 600 --beats "{BEATS}" --out work/render.mp4\n# nota do produtor\n')
GERAR_FC = '''#!/bin/zsh
SELF="$(cd "$(dirname "$0")" && pwd)"
printf '%s\\n' "$@" > "$SELF/args.txt"
mkdir -p "$SELF/../../output/dividido-mascara"
cp work/joao.mp4 "$SELF/../../output/dividido-mascara/20261030-130000.mp4"
'''
GERAR_FC_OUT = GERAR_FC + '''# variante com --out:
OUT=""; while [[ $# -gt 0 ]]; do case "$1" in --out) OUT="$2"; shift 2;; *) shift;; esac; done
case "$OUT" in --out) ;; esac  # --out) aceito
[[ -n "$OUT" ]] && cp work/joao.mp4 "$OUT"
'''
LIMPA_FC = '''import argparse, shutil
a = argparse.ArgumentParser()
for k in ("--src", "--ss", "--dur", "--out", "--h"):
    a.add_argument(k)
x = a.parse_args()
open(x.out, "wb").write(open(x.src, "rb").read())
open(x.out + ".args", "w").write(f"{x.ss} {x.dur} {x.h}")
'''


class FalaComCenas(unittest.TestCase):
    def _sandbox(self, raiz: Path, limpa: bool = True, com_out: bool = False) -> Path:
        p = raiz / "clientes" / "C" / "cContent" / "modelos" / "dividido-mascara" / "_sandbox-x"
        sintetico(p / "work" / "joao.mp4", 40, "270x480", fps=10)
        sintetico(p / "brolls" / "novo.mp4", 6, "640x360", audio=False)
        palavras_groq(p / "work" / "words.json", [("um", 4.5), ("dois", 11.2), ("tres", 30.5)])
        (p / "comando.sh").write_text(COMANDO_FC, encoding="utf-8")
        (p.parent / "gerar.sh").write_text(GERAR_FC_OUT if com_out else GERAR_FC, encoding="utf-8")
        if limpa:
            (p.parent / "limpa-broll.py").write_text(LIMPA_FC, encoding="utf-8")
        return p

    def test_ler_beats_viram_cenas_e_o_que_sobra_vira_fala(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            cs = fala.ler(p)["cenas"]
            self.assertEqual([(c["de"], c["tipo"]) for c in cs],
                             [(0, "fala"), (4, "broll"), (8, "fala"), (11, "card"), (14, "fala"), (16, "punch"), (20, "fala"),
                              (22, "peca"), (24, "fala"), (30, "broll"), (34, "fala")])   # o punch 31-33 se sobrepõe ao broll: fica de fora
            self.assertEqual((cs[1]["clipe"], cs[1]["inicio"], cs[3]["texto"], cs[7]["peca"]), ("brolls/cuts/b1.mp4", 2, "PARECE *MELHOR*", "brolls/cards/b4.mp4"))

    def test_ida_e_volta_nao_muda_o_comando(self):
        for limpa in (True, False):
            with tempfile.TemporaryDirectory() as d:
                p = self._sandbox(Path(d), limpa)
                doc = fala.ler(p)
                fala.gravar(p, doc)
                novo = (p / "comando.sh").read_text()
                self.assertEqual(fala._valor(fala._comando(p)[3], "--beats"), BEATS)    # nenhum beat mudou, nem o sobreposto
                self.assertIn("--music assets/m.mp3", novo)
                self.assertIn("--out work/render.mp4", novo)
                self.assertIn("# nota do produtor", novo)
                self.assertNotIn("editor-cortes", novo)
                self.assertEqual(fala.ler(p)["cenas"], doc["cenas"])

    def test_gravar_cena_nova_com_limpa_faz_corte_e_guarda_a_origem(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d), com_out=True)
            doc = fala.ler(p)
            doc["cenas"][2].update(tipo="broll", clipe=str(p / "brolls" / "novo.mp4"), inicio=1.5)   # a fala 8-11 ganha uma cena de apoio
            doc["cenas"][3].update(texto="OUTRA *FRASE*")
            fala.gravar(p, doc)
            c = (p / "comando.sh").read_text()
            beats = fala._valor(fala._comando(p)[3], "--beats")
            self.assertIn("card:11-14:OUTRA *FRASE*", beats)
            nome = next(b.split(":")[2].split("@")[0] for b in beats.split(";") if b.startswith("broll:8-11"))
            self.assertRegex(nome, r"^brolls/cuts/ed-[0-9a-f]{10}\.mp4$")
            self.assertIn("editor-cortes", c)
            novo = fala.ler(p)["cenas"][2]
            self.assertEqual((novo["clipe"], novo["inicio"]), (str(p / "brolls" / "novo.mp4"), 1.5))   # o editor mostra sempre a origem
            self.assertFalse((p / nome).exists())            # o corte nasce no refazer, não no gravar
            self.assertEqual(fala.refazer(p), 0)
            self.assertTrue((p / nome).is_file())
            self.assertEqual((p / (nome + ".args")).read_text(), "1.5 3.0 600")
            args = (p.parent / "args.txt").read_text().splitlines()
            self.assertEqual(args[args.index("--beats") + 1], beats)
            self.assertEqual(args[args.index("--out") + 1], str(fala.saida(p.resolve())))   # o --out da produção é trocado pelo caminho final...
            self.assertTrue(fala.saida(p).is_file())                              # variante com --out grava direto no caminho final

    def test_gancho_vira_a_cena_1_e_a_miniatura_sai_do_quadro_certo(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            c = (p / "comando.sh").read_text().replace("--dir . ", "--dir . --gancho brolls/g.mp4 --gancho-dur 2 ")
            (p / "comando.sh").write_text(c, encoding="utf-8")
            doc = fala.ler(p)
            self.assertEqual(doc["cenas"][0], {"de": 0.0, "tipo": "gancho"})
            self.assertEqual([(x["de"], x["tipo"]) for x in doc["cenas"][1:4]], [(2, "fala"), (6, "broll"), (10, "fala")])   # corpo + 2 s de gancho
            self.assertAlmostEqual(doc["duracao"], 42, delta=.1)
            fala.gravar(p, doc)                                   # ida e volta: os beats do corpo ficam como eram
            self.assertEqual(fala._valor(fala._comando(p)[3], "--beats"), BEATS)
            # vídeo final de mentira: 2 s de gancho vermelho + o corpo azul
            saida = fala.saida(p)
            saida.parent.mkdir(parents=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=96x160:r=10:d=2", "-f", "lavfi", "-i", "color=c=blue:s=96x160:r=10:d=40",
                            "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(saida)], check=True)
            a, b = ctx(raiz, "fala-com-cenas")
            with a, b:
                minis = editor.miniaturas(p)
                cor = lambda m: Image.open(raiz / m).convert("RGB").resize((1, 1)).getpixel((0, 0))
                self.assertGreater(cor(minis[0])[0], 200)         # cena 1 = o gancho (vermelho)
                self.assertGreater(cor(minis[1])[2], 200)         # cena 2 = já é o corpo (azul), não o gancho deslocado
                self.assertEqual(editor.cenas(p)[1]["fala"], "")  # a fala do corpo também anda junto
                self.assertEqual(editor.cenas(p)[2]["fala"], "um")   # "um" em 4,5 s do corpo = 6,5 s no vídeo final

    def test_variante_sem_out_o_video_novo_vira_o_slug_mp4(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d), limpa=False)
            self.assertEqual(fala.refazer(p), 0)
            self.assertTrue(fala.saida(p).is_file())
            self.assertEqual([q.name for q in fala.saida(p).parent.glob("*.mp4")], ["x.mp4"])   # o <ts>.mp4 do gerar.sh foi renomeado
            self.assertEqual((p.parent / "args.txt").read_text().splitlines().count("--out"), 1)   # e o --out da produção segue como estava (a variante o ignora)

    def test_sem_limpa_o_proprio_gerar_corta_arquivo_arroba_segundo(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d), limpa=False)
            doc = fala.ler(p)
            doc["cenas"][8].update(tipo="broll", clipe="brolls/novo.mp4", inicio=2)   # 24-30
            fala.gravar(p, doc)
            self.assertIn("broll:24-30:brolls/novo.mp4@2", fala._valor(fala._comando(p)[3], "--beats"))
            self.assertNotIn("editor-cortes", (p / "comando.sh").read_text())

    def test_fala_com_texto_vira_card_e_broll_apagado_volta_pro_joao(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d), limpa=False)
            doc = fala.ler(p)
            doc["cenas"][0].update(tipo="card", texto="COMEÇO")   # a fala do começo ganha uma frase na tela
            doc["cenas"][1]["tipo"] = "fala"                    # o broll 4-8 sai
            fala.gravar(p, doc)
            beats = fala._valor(fala._comando(p)[3], "--beats").split(";")
            self.assertIn("card:0-4:COMEÇO", beats)
            self.assertFalse([b for b in beats if b.startswith("broll:4-8")])
            self.assertIn("punch:31-33", beats)                  # beat que o editor não entende ou se sobrepõe nunca é perdido

    def test_editor_elementos_prompt_e_fiel(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b = ctx(raiz, "fala-com-cenas")
            with a, b:
                self.assertTrue(editor.pasta(editor.rel(p)))
                cs = editor.cenas(p)
                self.assertEqual(cs[1]["tipo_rotulo"], "Cena de apoio embaixo")
                self.assertEqual([e["campo"] for e in cs[1]["elementos"]], ["tipo", "clipe", "inicio", "texto"])
                self.assertIn("um", cs[1]["fala"])
                sp = editor.spec(p)
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois["cenas"][1].update(clipe="novo.mp4", inicio=3, tipo="card", de=4.5)
                ok, _ = editor._fiel(antes, depois, {"escopo": "elemento", "n": 2, "campo": "clipe"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["cenas"][1]["clipe"], ok["cenas"][1]["inicio"], ok["cenas"][1]["tipo"], ok["cenas"][1]["de"]), ("novo.mp4", 3, "card", 4))   # o tipo anda com o clipe (é assim que uma cena "fala" ganha cena de apoio); o tempo é da fala
                t = editor.prompt(p, {"escopo": "elemento", "n": 2, "n_fim": None, "campo": "clipe", "texto": "troca", "print": ""})
                self.assertIn("editor/cenas.json", t)
                self.assertIn("Você NÃO mexe no comando.sh", t)


# ───────────────────────── Chamada na tela ─────────────────────────

WORDS_CH = [("Olha", .2), ("isso", .6), ("agora", 1.2), ("a", 3.6), ("gente", 4.1), ("perde", 4.5), ("dinheiro", 5.0), ("todo", 5.5), ("mês", 5.9),
            ("com", 6.3), ("vendas", 8.0), ("baixas", 8.4), ("e", 9.0), ("fim", 9.5)]
STUB_TELA = '''import json, sys
from pathlib import Path
DUR = {"neon": 1.5, "riscado": 1.8, "etiqueta": 2.4, "contador": 1.6, "x": 1.7}
def planejar_motions(ws, ini, dur, rng):
    return []
if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    Path(cfg["out"]).write_bytes(b"video")
    Path(sys.argv[1] + ".recebido").write_text(json.dumps(cfg))
    if cfg.get("falhar"):
        sys.exit(3)
'''


class ChamadaNaTela(unittest.TestCase):
    def _sandbox(self, raiz: Path, tela_real: bool = True) -> Path:
        p = raiz / "clientes" / "C" / "cContent" / "modelos" / "chamada-na-tela" / "_sandbox-x"
        (p / "work").mkdir(parents=True)
        if tela_real:
            shutil.copy(TELA_PY, p.parent / "tela.py")
        else:
            (p.parent / "tela.py").write_text(STUB_TELA, encoding="utf-8")
        words = {"dur": 12.0, "pecas": [{"ini": 0, "fim": 12.0}], "words": [{"w": w, "s": s, "e": s + .3} for w, s in WORDS_CH]}
        (p / "work" / "words.json").write_text(json.dumps(words), encoding="utf-8")
        cfg = {"video": str(p / "work" / "joao.mp4"), "words": str(p / "work" / "words.json"), "out": str(p.parents[2] / "output" / "chamada-na-tela" / "x.mp4"),
               "titulo": ["QUEM VENDE", "PERDE"], "gancho": "bate", "seed": 7, "legenda": 1, "destaques": ["vendas"]}
        (p / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        return p

    def test_ler_acha_os_motions_do_tela_py_e_cobre_o_video(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = chamada.ler(p)
            cs = doc["cenas"]
            self.assertEqual(cs[0], {"de": 0.0, "tipo": "gancho"})
            motions = [(c["tipo"], c["texto"], c["de"]) for c in cs if c["tipo"] not in ("gancho", "fala")]
            self.assertEqual(motions, [("riscado", "DINHEIRO", 5.0), ("neon", "VENDAS", 8.0)])
            self.assertEqual([c["de"] for c in cs], sorted(c["de"] for c in cs))
            self.assertAlmostEqual(cs[3]["de"], 5.0 + 1.8)   # depois do motion volta a legenda
            self.assertEqual((doc["titulo_neon"], doc["gancho"], doc["legenda"]), (["QUEM VENDE", "PERDE"], "bate", 1))
            self.assertEqual(doc["palavras"], "editor/palavras.json")
            self.assertEqual(json.loads((p / "editor" / "palavras.json").read_text())[6]["word"], "dinheiro")

    def test_ida_e_volta_nao_grava_motions_nem_muda_o_config(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            antes = json.loads((p / "config.json").read_text())
            chamada.gravar(p, chamada.ler(p))
            self.assertEqual(json.loads((p / "config.json").read_text()), antes)   # sem "motions": o tela.py segue achando sozinho

    def test_editar_motion_grava_a_lista_explicita(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = chamada.ler(p)
            i = next(k for k, c in enumerate(doc["cenas"]) if c["tipo"] == "riscado")
            doc["cenas"][i].update(tipo="etiqueta", texto="PERDE TODO MÊS")
            j = next(k for k, c in enumerate(doc["cenas"]) if c["tipo"] == "neon")
            doc["cenas"][j]["tipo"] = "fala"                       # o motion de 8 s sai
            doc.update(gancho="luz", titulo_neon=["OUTRO", "TÍTULO"], destaques=["vendas", "mês"])
            chamada.gravar(p, doc)
            cfg = json.loads((p / "config.json").read_text())
            self.assertEqual([(m["tipo"], m["txt"], m["ini"]) for m in cfg["motions"]], [("etiqueta", "PERDE TODO MÊS", 5.0)])
            self.assertEqual(cfg["motions"][0]["fim"], 5.0 + 2.4)
            self.assertEqual((cfg["gancho"], cfg["titulo"], cfg["destaques"], cfg["seed"]), ("luz", ["OUTRO", "TÍTULO"], ["vendas", "mês"], 7))
            novo = chamada.ler(p)["cenas"]
            self.assertEqual([c["tipo"] for c in novo if c["tipo"] != "fala"], ["gancho", "etiqueta"])   # a lista explícita vale; o gatilho de 8 s não volta

    def test_fala_vira_motion_contador_sem_numero_vira_neon_e_empilha_precisa_de_itens(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = chamada.ler(p)
            fala_ = next(c for c in doc["cenas"] if c["tipo"] == "fala" and c["de"] > 9)
            fala_.update(tipo="contador", texto="SEM NÚMERO")
            antes = next(c for c in doc["cenas"] if c["tipo"] == "fala" and 6 < c["de"] < 8)
            antes.update(tipo="empilha", texto="X", itens=[["A", 6.9]])   # 1 item só: não vale
            chamada.gravar(p, doc)
            ms = json.loads((p / "config.json").read_text())["motions"]
            self.assertEqual([(m["tipo"], m["txt"]) for m in ms], [("riscado", "DINHEIRO"), ("neon", "VENDAS"), ("neon", "SEM NÚMERO")])

    def test_refazer_so_troca_o_video_se_o_render_der_certo(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d), tela_real=False)
            destino = chamada.saida(p)
            destino.parent.mkdir(parents=True)
            destino.write_bytes(b"antigo")
            self.assertEqual(chamada.refazer(p), 0)
            self.assertEqual(destino.read_bytes(), b"video")
            self.assertFalse(list(destino.parent.glob("*.novo.mp4")))
            cfg = json.loads((p / "config.json").read_text())
            cfg["falhar"] = True
            (p / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            destino.write_bytes(b"bom")
            self.assertNotEqual(chamada.refazer(p), 0)
            self.assertEqual(destino.read_bytes(), b"bom")        # render quebrado nunca troca o vídeo
            self.assertFalse(list(destino.parent.glob("*.novo.mp4")))

    def test_editor_globais_e_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            (p / "work" / "joao.mp4").write_bytes(b"")
            a, b = ctx(raiz, "chamada-na-tela")
            with a, b, mock.patch.object(editor, "RAIZ", raiz):
                self.assertTrue(editor.pasta(editor.rel(p)))
                cs = editor.cenas(p)
                self.assertEqual(cs[0]["tipo_rotulo"], "Gancho (título neon)")
                self.assertEqual([e["campo"] for e in cs[0]["elementos"]], ["tipo", "texto", "titulo", "gancho", "legenda", "destaques"])
                self.assertIn("dinheiro", " ".join(c["fala"] for c in cs))
                sp = editor.spec(p)
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois.update(titulo_neon=["NOVO", "TÍTULO"], gancho="luz")
                ok, _ = editor._fiel(antes, depois, {"escopo": "elemento", "n": 1, "campo": "titulo"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["titulo_neon"], ok["gancho"]), (["NOVO", "TÍTULO"], "bate"))
                t = editor.prompt(p, {"escopo": "elemento", "n": 1, "n_fim": None, "campo": "titulo", "texto": "outro título", "print": ""})
                self.assertIn("TOPO do arquivo", t)


# ───────────────────────── Lista de estáticos ─────────────────────────

class ListaDeEstaticos(unittest.TestCase):
    def _sandbox(self, raiz: Path) -> Path:
        from PIL import Image
        p = raiz / "clientes" / "C" / "cContent" / "modelos" / "lista-de-estaticos" / "_sandbox-x"
        sintetico(p / "work" / "bruto.mp4", 7, "270x480", fps=15)
        palavras_groq(p / "work" / "words.json", [("um", .5), ("dois", 3.1), ("tres", 5.2)])
        for i, cor in enumerate([(200, 30, 30), (30, 200, 30), (30, 30, 200)], 1):
            (p / "material").mkdir(exist_ok=True)
            Image.new("RGB", (400, 500), cor).save(p / "material" / f"{i}.png")
        cenas = {"video": "work/bruto.mp4", "titulo": [[["3 estáticos pra", "normal"]], [["vender mais", "forte"], [" hoje", "normal"]]],
                 "lado": "direita", "fim": 6.5, "palavras": "work/words.json", "cortes": [[1.0, 2.0]],
                 "itens": [{"nome": "um", "imagem": "material/1.png", "t": 2.5}, {"nome": "dois", "imagem": "material/2.png", "t": 3.5},
                           {"nome": "tres", "imagem": "material/3.png", "t": 5.0}]}
        (p / "cenas.json").write_text(json.dumps(cenas), encoding="utf-8")
        return p

    def test_ler_conta_o_tempo_depois_dos_cortes(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            doc = lista.ler(p)
            self.assertEqual([(c["tipo"], c["de"]) for c in doc["cenas"]], [("abertura", 0), ("item", 1.5), ("item", 2.5), ("item", 4.0)])   # 1 s de corte antes
            self.assertEqual(doc["duracao"], 5.5)
            self.assertEqual(doc["titulo"], "3 estáticos pra vender mais hoje")
            pal = json.loads((p / "editor" / "palavras.json").read_text())
            self.assertEqual([(w["word"], w["start"]) for w in pal], [("um", .5), ("dois", 2.1), ("tres", 4.2)])

    def test_ida_e_volta_e_edicao_mantem_t_e_cortes(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            antes = json.loads((p / "cenas.json").read_text())
            doc = lista.ler(p)
            lista.gravar(p, doc)
            self.assertEqual(json.loads((p / "cenas.json").read_text()), antes)
            doc["cenas"][2].update(nome="  novo nome ", imagem="material/1.png")
            doc.update(lado="esquerda", titulo_tela=[[["OUTRO", "forte"]]])
            lista.gravar(p, doc)
            c = json.loads((p / "cenas.json").read_text())
            self.assertEqual([(i["nome"], i["imagem"], i["t"]) for i in c["itens"]], [("um", "material/1.png", 2.5), ("novo nome", "material/1.png", 3.5), ("tres", "material/3.png", 5.0)])
            self.assertEqual((c["lado"], c["cortes"], c["fim"], c["titulo"]), ("esquerda", [[1.0, 2.0]], 6.5, [[["OUTRO", "forte"]]]))

    def test_refazer_renderiza_de_verdade_com_o_lado_pedido_e_troca_o_video(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._sandbox(Path(d))
            self.assertEqual(lista.refazer(p), 0)
            s = lista.saida(p)
            self.assertTrue(s.is_file())
            self.assertAlmostEqual(duracao(s), 5.5, delta=.4)
            self.assertFalse(list(s.parent.glob("*.novo.mp4")))
            ant = s.read_bytes()
            doc = lista.ler(p)
            doc["cenas"][1]["imagem"] = "material/3.png"
            lista.gravar(p, doc)
            self.assertEqual(lista.refazer(p), 0)
            self.assertNotEqual(s.read_bytes(), ant)

    def test_editor_elementos_e_globais(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d)
            p = self._sandbox(raiz)
            a, b = ctx(raiz, "lista-de-estaticos")
            with a, b:
                self.assertTrue(editor.pasta(editor.rel(p)))
                cs = editor.cenas(p)
                self.assertEqual([e["campo"] for e in cs[1]["elementos"]], ["nome", "imagem", "titulo", "lado", "estilo"])
                self.assertEqual([e["campo"] for e in cs[0]["elementos"]], ["titulo", "lado", "estilo"])
                self.assertEqual(cs[1]["fala"], "dois")
                sp = editor.spec(p)
                antes = editor._doc(p)
                depois = json.loads(json.dumps(antes))
                depois["cenas"][1]["nome"] = "mudou"
                depois["cenas"][2]["nome"] = "fora"
                ok, avisos = editor._fiel(antes, depois, {"escopo": "elemento", "n": 2, "campo": "nome"}, sp["juntos"], (), sp["globais"], True)
                self.assertEqual((ok["cenas"][1]["nome"], ok["cenas"][2]["nome"]), ("mudou", "dois"))
                self.assertTrue(avisos)


if __name__ == "__main__":
    unittest.main()
