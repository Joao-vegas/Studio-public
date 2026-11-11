/* Prévia muda nas miniaturas de referência (.and-ref com data-video): mouse em cima toca ali mesmo,
   no celular o primeiro toque toca a prévia e o segundo abre o player grande. Só uma toca por vez. */
(function () {
  var CHAVE = 'estudio-ref-dica', tocando = null, ultimoToque = 0;
  var botao = function (el) { return el && el.closest ? el.closest('.and-ref[data-video]') : null; };

  function para() {
    if (!tocando) return;
    var v = tocando.querySelector('.and-ref-previa');
    tocando.classList.remove('tocando');
    if (v) { v.pause(); v.currentTime = 0; }
    tocando = null;
  }
  function toca(b) {
    if (tocando === b) return;
    para();
    var v = b.querySelector('.and-ref-previa');
    if (!v) {
      v = document.createElement('video');
      v.className = 'and-ref-previa'; v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'none'; v.tabIndex = -1;
      v.src = b.dataset.video;
      b.insertBefore(v, b.firstChild);
    }
    b.classList.add('tocando'); tocando = b;
    v.play().catch(function () {});
    document.querySelectorAll('.and-ref-dica').forEach(function (d) { d.hidden = true; });
    try { localStorage.setItem(CHAVE, '1'); } catch (e) {}
  }

  document.addEventListener('mouseover', function (e) {
    if (Date.now() - ultimoToque < 800) return; // o navegador do celular imita mouse depois do toque
    var b = botao(e.target); if (b && b !== botao(e.relatedTarget)) toca(b);
  });
  document.addEventListener('mouseout', function (e) {
    if (Date.now() - ultimoToque < 800) return;
    var b = botao(e.target); if (b && b === tocando && b !== botao(e.relatedTarget)) para();
  });
  document.addEventListener('touchstart', function (e) {
    ultimoToque = Date.now();
    if (tocando && botao(e.target) !== tocando) para(); // tocou noutro lugar: a prévia anterior para
  }, {passive: true, capture: true});
  // Captura: no toque, o primeiro clique só toca a prévia; o seguinte segue pro código que abre o player.
  document.addEventListener('click', function (e) {
    var b = botao(e.target); if (!b) return;
    if (Date.now() - ultimoToque < 800 && tocando !== b) { e.stopPropagation(); e.preventDefault(); toca(b); }
    else para();
  }, true);
  document.addEventListener('visibilitychange', function () { if (document.hidden) para(); });

  try { if (localStorage.getItem(CHAVE)) document.querySelectorAll('.and-ref-dica').forEach(function (d) { d.hidden = true; }); } catch (e) {}
})();
