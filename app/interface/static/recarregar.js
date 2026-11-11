/* "Recarregar agora": pede ao servidor pra reiniciar (o launchd sobe de novo) e recarrega a página quando a versão nova responder. */
(function () {
  var f = document.getElementById('recarregar-form');
  if (!f) return;
  var msg = document.getElementById('recarregar-msg'), btn = f.querySelector('button');
  var inicio0 = null;
  function saude() { return fetch('/api/health', {cache: 'no-store'}).then(function (r) { return r.json(); }); }
  function esperarNovo() {
    var t = setInterval(function () {
      saude().then(function (h) { if (inicio0 !== null && h.inicio !== inicio0) { clearInterval(t); location.reload(); } }).catch(function () { msg.textContent = 'Reiniciando…'; });
    }, 1500);
  }
  saude().then(function (h) { inicio0 = h.inicio; if (f.dataset.agendado === '1') esperarNovo(); }).catch(function () {});
  f.addEventListener('submit', function (e) {
    e.preventDefault();
    btn.disabled = true; msg.textContent = 'Pedindo…';
    fetch('/api/recarregar', {method: 'POST'}).then(function (r) { return r.json(); }).then(function (d) {
      if (d.recarregando) { msg.textContent = 'Recarregando… a página volta sozinha.'; }
      else { msg.textContent = 'Tem ' + (d.motivo || []).join(' e ') + ': recarrega sozinho quando terminar.'; btn.hidden = true; }
      esperarNovo();
    }).catch(function () { msg.textContent = 'Reiniciando…'; esperarNovo(); });
  });
})();
