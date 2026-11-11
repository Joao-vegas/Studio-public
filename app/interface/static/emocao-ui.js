// Emoção de cada frase do roteiro: uma lista com uma etiqueta (select) por frase, que o João troca antes de criar.
// Usada no Criar (EmocaoUI.criar) e no Editar vídeo > Narração (EmocaoUI.montar).
var EmocaoUI = (function () {
  function montar(box, linhas, emocoes, quando) {
    box.innerHTML = '';
    linhas.forEach(function (l, i) {
      var row = document.createElement('div'), sel = document.createElement('select'), tx = document.createElement('span');
      row.className = 'emo-frase'; sel.className = 'emo-et'; sel.setAttribute('aria-label', 'Emoção da frase ' + (i + 1));
      emocoes.forEach(function (e) { var o = document.createElement('option'); o.value = e.slug; o.textContent = e.rotulo; if (e.slug === l.emocao) o.selected = true; sel.appendChild(o); });
      sel.onchange = function () { l.emocao = sel.value; if (quando) quando(linhas); };
      tx.className = 'emo-tx'; tx.textContent = l.texto;
      row.appendChild(sel); row.appendChild(tx); box.appendChild(row);
    });
  }
  function marcar(url, roteiro) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ roteiro: roteiro }) }).then(function (r) { return r.json(); });
  }
  // Criar: o roteiro entrou (colado, escrito pelo Claude) ou o João clicou -> o Claude marca; o JSON vai no formulário (name="emocoes").
  function criar(o) {
    var ultimo = '';
    function rodar() {
      var t = o.roteiro.value.trim();
      if (!t || t === ultimo) return;
      ultimo = t; o.msg.textContent = 'O Claude está marcando a emoção de cada frase…'; o.botao.disabled = true;
      marcar(o.url, t).then(function (j) {
        o.botao.disabled = false;
        if (!j.ok) { o.msg.textContent = '✖ ' + (j.erro || 'não deu'); ultimo = ''; return; }
        o.msg.textContent = 'Troque o que quiser:'; o.json.value = JSON.stringify(j.linhas);
        montar(o.lista, j.linhas, j.emocoes, function (ls) { o.json.value = JSON.stringify(ls); });
      }).catch(function () { o.botao.disabled = false; o.msg.textContent = '✖ A IA não respondeu. Ao criar, eu marco sozinho.'; ultimo = ''; });
    }
    o.botao.onclick = function () { ultimo = ''; rodar(); };
    o.roteiro.addEventListener('change', rodar);               // sai do campo, ou a tela preencheu o roteiro (dispatchEvent)
    o.roteiro.addEventListener('input', function () { if (o.roteiro.value.trim() !== ultimo) { o.json.value = ''; } });
  }
  return { montar: montar, marcar: marcar, criar: criar };
})();
