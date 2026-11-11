/* Zona de soltar arquivo (.soltar): a zona inteira é o botão. Mostra a linha do arquivo escolhido e o destaque ao arrastar. */
(function () {
  function tamanho(b) { return b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : Math.max(1, Math.round(b / 1e6)) + ' MB'; }
  function liga(z) {
    var inp = z.querySelector('input[type=file]'); if (!inp || z.dataset.ligada) return; z.dataset.ligada = '1';
    var nome = z.querySelector('.soltar-nome'), info = z.querySelector('.soltar-info'), mini = z.querySelector('.soltar-mini');
    function atualiza() {
      var f = Array.prototype.slice.call(inp.files || []);
      z.classList.toggle('com-arquivo', f.length > 0);
      if (!f.length) { if (mini) { mini.removeAttribute('src'); } return; }
      var total = f.reduce(function (a, x) { return a + x.size; }, 0);
      if (nome) nome.textContent = f.length === 1 ? f[0].name : f.length + ' arquivos';
      if (info) info.textContent = tamanho(total);
      if (mini && /^video\//.test(f[0].type || '')) { mini.src = URL.createObjectURL(f[0]); mini.currentTime = 0.1; }
    }
    inp.addEventListener('change', atualiza);
    ['dragenter', 'dragover'].forEach(function (t) { z.addEventListener(t, function (e) { e.preventDefault(); z.classList.add('arrastando'); }); });
    ['dragleave', 'drop'].forEach(function (t) { z.addEventListener(t, function (e) { e.preventDefault(); z.classList.remove('arrastando'); }); });
    z.addEventListener('drop', function (e) { if (e.dataTransfer.files.length) { inp.files = e.dataTransfer.files; atualiza(); } });
    atualiza();
  }
  document.addEventListener('DOMContentLoaded', function () { document.querySelectorAll('.soltar').forEach(liga); });
  if (document.readyState !== 'loading') document.querySelectorAll('.soltar').forEach(liga);
})();
