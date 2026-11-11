// "Momento a momento": todos os planos do vídeo de referência (quadro do meio, tempo, duração, o que é) + o resumo
// "Cenas que esse estilo usa" (tipo · contagem · miniatura, clica pra filtrar) e 3 números da régua.
// Dados de /api/storyboard/<slug>[?ref=]: {estado: pronto|preparando|erro|sem, quadros[], resumo{tipos[],numeros[]}, total}.
// O servidor prepara o que falta uma vez, em segundo plano; aqui a gente pergunta de novo até ficar pronto.
var TiraUI = (function () {
  function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  // o: {url, caixa, resumo, conta, lista, vale() -> bool (a escolha mudou? larga), compacto}
  function montar(o) {
    var tentativas = 0, filtro = '', todos = false, dados = null;
    o.caixa.hidden = true; o.lista.innerHTML = ''; o.resumo.innerHTML = ''; o.conta.textContent = '';
    function vale() { return !o.vale || o.vale(); }

    function pinta() {
      var qs = dados.quadros, total = qs.length;
      var vis = qs.filter(function (q) { return filtro ? q.tipo === filtro : (todos || q.destaque); });
      o.lista.innerHTML = vis.map(function (q) {
        return '<li data-tipo="' + esc(q.tipo) + '"><img src="' + esc(q.url) + '" alt="Quadro do meio do plano em ' + esc(q.tempo) + '" loading="lazy" width="360">'
          + '<b>' + esc(q.tempo) + '</b><small class="tira-dura">' + esc(q.dura) + '</small><span>' + esc(q.legenda) + '</span>'
          + (q.fala ? '<em>“' + esc(q.fala) + '”</em>' : '') + '</li>'; }).join('');
      o.lista.scrollLeft = 0;
      var rot = filtro ? (dados.resumo.tipos.filter(function (t) { return t.tipo === filtro; })[0] || {}).rotulo : '';
      if (filtro) o.conta.innerHTML = vis.length + ' de ' + total + ' planos: ' + esc(rot) + ' · <button type="button" class="tira-link" data-a="limpa">ver a tira de novo</button>';
      else if (total > vis.length) o.conta.innerHTML = 'Mostrando os planos principais (' + vis.length + ' de ' + total + ') · <button type="button" class="tira-link" data-a="todos">ver os ' + total + '</button>';
      else if (todos && qs.some(function (q) { return !q.destaque; })) o.conta.innerHTML = 'Os ' + total + ' planos · <button type="button" class="tira-link" data-a="limpa">ver só os principais</button>';
      else o.conta.textContent = total + (total === 1 ? ' plano' : ' planos') + ' no vídeo, do primeiro ao último';
      [].forEach.call(o.resumo.querySelectorAll('.tira-tipo'), function (b) { b.classList.toggle('ativo', b.dataset.tipo === filtro); b.setAttribute('aria-pressed', b.dataset.tipo === filtro ? 'true' : 'false'); });
    }

    function pronto(j) {
      dados = j; var r = j.resumo || { tipos: [], numeros: [] };
      o.resumo.innerHTML = '<h3 class="tira-tit">Cenas que esse estilo usa</h3><p class="meta tira-uma">Os tipos de cena do vídeo de referência. Clique num tipo pra ver só ele.</p>'
        + '<div class="tira-tipos">' + r.tipos.map(function (t) {
          return '<button type="button" class="tira-tipo" data-tipo="' + esc(t.tipo) + '" aria-pressed="false">'
            + (t.url ? '<img src="' + esc(t.url) + '" alt="" loading="lazy" width="360">' : '<i></i>')
            + '<span><b>' + t.n + '</b> ' + esc(t.rotulo) + '</span></button>'; }).join('') + '</div>'
        + ((r.frases || []).length ? '<ul class="tira-nums tira-frases">' + r.frases.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('') + '</ul>'
          : r.numeros.length ? '<ul class="tira-nums">' + r.numeros.map(function (n) { return '<li><b>' + esc(n.valor) + '</b> ' + esc(n.rotulo) + '</li>'; }).join('') + '</ul>' : '')
        + (r.numeros.length ? '<details class="tira-detalhe"><summary>Ver os números</summary><ul class="tira-nums">' + r.numeros.map(function (n) { return '<li><b>' + esc(n.valor) + '</b> ' + esc(n.rotulo) + '</li>'; }).join('') + '</ul></details>' : '');
      [].forEach.call(o.resumo.querySelectorAll('.tira-tipo'), function (b) { b.onclick = function () { filtro = filtro === b.dataset.tipo ? '' : b.dataset.tipo; pinta(); }; });
      o.conta.onclick = function (ev) { var a = ev.target.dataset && ev.target.dataset.a; if (!a) return; if (a === 'todos') { todos = true; filtro = ''; } else { todos = false; filtro = ''; } pinta(); };
      o.caixa.hidden = false; pinta();
    }

    function pede() {
      fetch(o.url).then(function (r) { return r.json(); }).then(function (j) {
        if (!vale()) return;
        if (j.estado === 'preparando' && tentativas++ < 120) {
          o.caixa.hidden = false; o.conta.textContent = 'Estudando o vídeo de referência, plano a plano… (só na 1ª vez, até 1 minuto)';
          setTimeout(pede, 3000); return; }
        if (j.estado === 'pronto' && (j.quadros || []).length) pronto(j); else o.caixa.hidden = true;
      }).catch(function () {});
    }
    pede();
  }
  return { montar: montar };
})();
