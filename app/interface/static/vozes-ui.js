// Voz: prévia em português (▶ gera na hora no 1º clique e guarda) e filtro por busca + etiquetas, 5 cartões por vez.
(function () {
  var aud = new Audio(), atual = null;
  function norm(s) { return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }

  function estado(b, st) {
    var ico = b.querySelector('.vz-ico'), rot = b.querySelector('.vz-rot');
    b.classList.remove('tocando', 'gerando', 'erro');
    if (st === 'tocando') { b.classList.add('tocando'); ico.textContent = '■'; rot.textContent = 'Parar'; }
    else if (st === 'gerando') { b.classList.add('gerando'); ico.textContent = '…'; rot.textContent = 'Gerando a prévia (só na 1ª vez)'; }
    else if (st === 'erro') { b.classList.add('erro'); ico.textContent = '!'; rot.textContent = 'Ouvir'; }
    else { ico.textContent = '▶'; rot.textContent = 'Ouvir'; }
  }
  // Situação da voz (voicestudio.estado): ligando · gerando outra voz · desligada (com "Ligar a voz") · instalar
  function api(url, post) {
    return fetch(url, post ? { method: 'POST' } : { cache: 'no-store' }).then(function (r) { return r.json(); })
      .catch(function () { return { estado: 'fora', texto: 'Não consegui falar com o Estúdio.', pode_ligar: false }; });
  }
  function pinta(el, e) {
    el.textContent = e.texto + ' ';
    if (e.estado === 'fora' && e.pode_ligar) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'vz-ligar'; b.textContent = 'Ligar a voz';
      b.onclick = function () { ligar(el); }; el.appendChild(b);
    }
  }
  function espera(el, e, depois, n) {
    n = n || 0;
    if ((e.estado === 'ligando' || e.estado === 'ocupado') && n < 45) {
      pinta(el, e); setTimeout(function () { api('/api/voz/estado').then(function (x) { espera(el, x, depois, n + 1); }); }, 2000); return;
    }
    if (e.estado === 'no_ar') { el.textContent = 'A voz está no ar. Tente de novo.'; if (el.dataset.recarrega) location.reload(); if (depois) depois(); return; }
    pinta(el, e);
  }
  function ligar(el, depois) { el.textContent = 'Ligando a voz (uns 10 s)…'; api('/api/voz/ligar', true).then(function (e) { espera(el, e, depois); }); }
  // `el` recebe o motivo de verdade (no ar: o texto de reserva `motivo`)
  function explicar(el, motivo) {
    return api('/api/voz/estado').then(function (e) {
      if (e.estado === 'no_ar') el.textContent = motivo || 'Não deu agora. Tente de novo.'; else pinta(el, e);
      return e;
    });
  }
  function aviso(b, on) {
    var c = b.closest('.fv-item'), e = c && c.querySelector('.vz-erro'); if (!e) return; e.hidden = !on;
    if (on) explicar(e.querySelector('.vz-erro-txt') || e);
  }
  function parar() {
    aud.onplaying = aud.onended = aud.onerror = null; aud.pause();
    if (atual) { estado(atual, 'parado'); atual = null; }
  }
  function tocar(b) {
    parar(); atual = b; aviso(b, false);
    estado(b, b.dataset.pronta === '1' ? 'tocando' : 'gerando');
    aud.onplaying = function () { b.dataset.pronta = '1'; estado(b, 'tocando'); };
    aud.onended = parar;
    aud.onerror = function () { var x = atual; aud.onplaying = aud.onended = aud.onerror = null; atual = null; if (x) { estado(x, 'erro'); aviso(x, true); } };
    aud.src = b.dataset.url; aud.play().catch(function () {});
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('.vz-play');
    if (b) { ev.preventDefault(); ev.stopPropagation(); if (atual === b) parar(); else tocar(b); return; }
    var r = ev.target.closest && ev.target.closest('.vz-retry');
    if (r) { ev.preventDefault(); ev.stopPropagation(); var pb = r.closest('.fv-item').querySelector('.vz-play'); if (pb) tocar(pb); }
  }, true);

  function filtro(raiz) {
    var busca = raiz.querySelector('.fv-busca'), box = raiz.querySelector('.fv-tags'), rot = JSON.parse(box.dataset.rotulos), ativas = {};
    var grupos = [].slice.call(raiz.querySelectorAll('.fv-grupo')), presentes = {};
    [].forEach.call(raiz.querySelectorAll('.fv-item'), function (i) { (i.dataset.tags || '').split(' ').forEach(function (t) { if (t) presentes[t] = 1; }); });
    Object.keys(rot).filter(function (t) { return presentes[t]; }).forEach(function (t) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'fv-tag'; b.textContent = rot[t]; b.dataset.tag = t; b.setAttribute('aria-pressed', 'false');
      b.onclick = function () { if (ativas[t]) delete ativas[t]; else ativas[t] = 1; b.classList.toggle('ativo', !!ativas[t]); b.setAttribute('aria-pressed', ativas[t] ? 'true' : 'false'); aplica(); };
      box.appendChild(b); });
    function bate(i, q) {
      if (i.dataset.fixo) return true;
      var ts = ' ' + (i.dataset.tags || '') + ' ';
      return (!q || norm(i.dataset.busca).indexOf(q) >= 0) && Object.keys(ativas).every(function (t) { return ts.indexOf(' ' + t + ' ') >= 0; });
    }
    function aplica() {
      var q = norm(busca.value.trim());
      grupos.forEach(function (g) {
        var itens = [].slice.call(g.querySelectorAll('.fv-item')), ok = itens.filter(function (i) { return bate(i, q); }), n = 0, aberto = g.dataset.aberto === '1';
        var contaveis = ok.filter(function (i) { return !i.dataset.fixo; });
        itens.forEach(function (i) {
          var mostra = ok.indexOf(i) >= 0 && (i.dataset.fixo || aberto || n < 5 || !!i.querySelector('input:checked') || i.classList.contains('ativo'));
          if (mostra && !i.dataset.fixo) n++;
          i.hidden = !mostra; });
        var mais = g.querySelector('.fv-mais'), vazio = g.querySelector('.fv-vazio');
        if (mais) { mais.hidden = contaveis.length <= 5; mais.textContent = aberto ? 'Mostrar menos' : 'Ver todas (' + contaveis.length + ')'; }
        if (vazio) vazio.hidden = contaveis.length > 0;
      });
    }
    grupos.forEach(function (g) { var m = g.querySelector('.fv-mais'); if (m) m.onclick = function () { g.dataset.aberto = g.dataset.aberto === '1' ? '0' : '1'; aplica(); }; });
    busca.addEventListener('input', aplica);
    raiz.addEventListener('change', aplica);
    aplica();
    return { aplica: aplica };
  }
  window.VozesUI = { filtro: filtro, parar: parar, explicar: explicar, ligar: ligar, estado: function () { return api('/api/voz/estado'); }, pinta: pinta, espera: espera };
})();
