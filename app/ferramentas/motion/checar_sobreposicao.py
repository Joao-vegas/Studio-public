"""
Varre um motion (index.html com seek(t)) e lista todo par de elementos visíveis que se sobrepõem.

Uso: python3 Eu/scripts/motion/checar_sobreposicao.py motion-apresentacao-vegas/v7 [--passo 0.2] [--de 0 --ate 999]
Motor próprio (ex.: Marca3): --url motor/index.html?v=00-x --sel '#fg .k:not(.man):not(.ptit), .man .m, .ptit .m, .fun .n, .fun .b > span'
(o SEL padrão só conhece as classes do modelo motion-venda; motor diferente PRECISA de --sel, senão sai 0 falso)
Saída: intervalos de tempo com os pares que se encostam (texto, chips, cartões, carimbos, nós).
Sai com código 1 quando acha sobreposição (0 = zero pares): a conferência do formato pode confiar no exit code.
Elemento coberto por uma capa opaca (.bgov, .shot, #ad-bg, #h-dim, #fim: o escurecido do fecho) não conta.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append("/Users/joaomarcospiki/Cerebro/scripts")
from limpar_runtime import registrar_cleanup_no_atexit  # noqa: E402

JS = r"""
([EXTRA, LW, LH]) => {
  const SEL = EXTRA || '.cap .m, .big .m, .kp, .chip, .stamp, .lbl, .tagb, .cnt, .bubble, .eyebrow, .co, .wire, .lrow, .node, .adcard, #vs, #eq, #pp-ring, .hud, .disp.k, .mono.k, .lbar, #dest, #phone, .st, .pcard';
  const vis = el => { let o = 1; for (let e = el; e && e !== document.body; e = e.parentElement) { const c = getComputedStyle(e);
      if (c.display === 'none' || c.visibility === 'hidden') return 0; o *= +c.opacity; } return o; };
  const clip = (el, r) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { if (getComputedStyle(e).overflow === 'hidden') {
      const p = e.getBoundingClientRect(); r = { l: Math.max(r.l, p.left), t: Math.max(r.t, p.top), r: Math.min(r.r, p.right), b: Math.min(r.b, p.bottom) }; } } return r; };
  const itens = [];
  document.querySelectorAll(SEL).forEach(el => {
    if (vis(el) < .15) return;
    { const bb = el.getBoundingClientRect(); const cx = Math.min(LW - 1, Math.max(0, bb.left + bb.width / 2)), cy = Math.min(LH - 1, Math.max(0, bb.top + bb.height / 2));
      for (const e of document.elementsFromPoint(cx, cy)) { if (e === el || el.contains(e)) break;
        const capa = e.classList.contains('bgov') || e.closest('.shot') || ['ad-bg', 'h-dim', 'h-dim0', 'fim'].includes(e.id);
        if (capa && vis(e) > .8) return; } }
    const b = el.getBoundingClientRect(); let r = clip(el, { l: b.left, t: b.top, r: b.right, b: b.bottom });
    r = { l: Math.max(r.l, 0), t: Math.max(r.t, 0), r: Math.min(r.r, LW), b: Math.min(r.b, LH) };
    if (r.r - r.l < 4 || r.b - r.t < 4) return;
    const nome = (el.id || el.closest('[id]')?.id || el.className) + ' "' + (el.textContent || '').trim().slice(0, 28) + '"';
    itens.push({ el, r, nome });
  });
  const out = [];
  for (let i = 0; i < itens.length; i++) for (let j = i + 1; j < itens.length; j++) {
    const a = itens[i], b = itens[j];
    if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const w = Math.min(a.r.r, b.r.r) - Math.max(a.r.l, b.r.l), h = Math.min(a.r.b, b.r.b) - Math.max(a.r.t, b.r.t);
    if (w <= 2 || h <= 2) continue;
    const menor = Math.min((a.r.r - a.r.l) * (a.r.b - a.r.t), (b.r.r - b.r.l) * (b.r.b - b.r.t));
    if (w * h < 120 || w * h / menor < .02) continue;
    out.push(a.nome + '  ×  ' + b.nome);
  }
  return out;
}
"""


def main() -> int:
    registrar_cleanup_no_atexit()
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta")
    ap.add_argument("--passo", type=float, default=0.2)
    ap.add_argument("--de", type=float, default=0)
    ap.add_argument("--ate", type=float, default=9999)
    ap.add_argument("--url", help="página do motor quando não é <pasta>/index.html (ex.: motor/index.html?v=00-x)")
    ap.add_argument("--tam", default="1920x1080", help="palco LxA; vertical: 1080x1920 (sem isso o checador corta o palco e dá 0 falso)")
    ap.add_argument("--sel", default="", help="seletores do motor; SUBSTITUEM o padrão (ex.: '#fg .k:not(.man), .man .m')")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        lw, lh = (int(v) for v in a.tam.lower().split("x"))
        pg = nav.new_page(viewport={"width": lw, "height": lh})
        if a.url:
            base, _, q = a.url.partition("?")
            pg.goto(Path(base).resolve().as_uri() + ("?" + q if q else ""))
        else:
            pg.goto((Path(a.pasta).resolve() / "index.html").as_uri())
        pg.evaluate("window.pronto")
        total = min(pg.evaluate("window.TOTAL"), a.ate)
        abertos: dict[str, list[float]] = {}
        achados: list[tuple[float, float, str]] = []
        t = a.de
        while t <= total:
            pg.evaluate(f"seek({t})")
            agora = set(pg.evaluate(JS, [a.sel, lw, lh]))
            for par in agora:
                if par in abertos:
                    abertos[par][1] = t
                else:
                    abertos[par] = [t, t]
            for par in list(abertos):
                if par not in agora:
                    achados.append((abertos[par][0], abertos[par][1], par))
                    del abertos[par]
            t = round(t + a.passo, 3)
        achados += [(v[0], v[1], k) for k, v in abertos.items()]
        nav.close()
    for t0, t1, par in sorted(achados):
        print(f"{t0:6.1f}-{t1:6.1f}s  {par}")
    print(f"\n{len(achados)} sobreposições")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
