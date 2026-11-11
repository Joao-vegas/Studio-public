/* Editor de corte: a IA corta primeiro; aqui o João ajusta. Botão único Cortar daqui/Termina aqui, arrastar pra marcar, alças e Devolver. Sem biblioteca.
   A prévia pula o que vai sair NA HORA (laço por quadro, não pelo timeupdate, que só chega 4x por segundo).
   Toda marca encaixa no silêncio mais perto: a ponta nunca cai no meio de uma palavra. */
(function () {
  var dados = JSON.parse(document.getElementById('c-dados').textContent);
  var $ = function (id) { return document.getElementById(id); };
  var v = $('v'), caixa = $('c-caixa'), roll = $('c-rolagem'), canvas = $('c-onda'), marcasEl = $('c-marcas');
  var picos = [], POR_S = 50, limiar = 0.04, zoom = 1, ini = null, sel = -1, parar = null;
  // cada marca: {a, b, tipo:'tirar'|'devolver', ia:bool, bolinha:bool}
  var marcas = (dados.salvo || dados.ia || []).map(function (c) { return { a: c[0], b: c[1], tipo: 'tirar', ia: !dados.salvo, bolinha: false }; });

  function fmt(t) { var m = Math.floor(t / 60), s = (t % 60).toFixed(1); return m + ':' + (s < 10 ? '0' : '') + s; }
  function dur() { return v.duration || 1; }
  function arred(x) { return Math.round(x * 100) / 100; }

  // ── silêncio: a partir da forma de onda ──
  function calibra() {
    if (!picos.length) return;
    var o = picos.slice().sort(function (x, y) { return x - y; });
    limiar = Math.max(0.02, Math.min(0.12, o[Math.floor(o.length * 0.9)] * 0.12));   // 12% da fala alta
  }
  function quieto(i) { return i < 0 || i >= picos.length || picos[i] < limiar; }
  // ponta encaixada: procura o silêncio mais perto (até `raio` s) e para nele; sem silêncio, fica onde está
  function encaixa(t, raio) {
    if (!picos.length) return t;
    var c = Math.round(t * POR_S), r = Math.round((raio || 0.3) * POR_S);
    for (var d = 0; d <= r; d++) {
      if (quieto(c - d)) return (c - d) / POR_S;
      if (quieto(c + d)) return (c + d) / POR_S;
    }
    return t;
  }

  // espelho de corte_manual.combinar (Python)
  function une(l) {
    l = l.slice().sort(function (x, y) { return x[0] - y[0]; }); var o = [];
    l.forEach(function (c) { if (o.length && c[0] <= o[o.length - 1][1]) o[o.length - 1][1] = Math.max(o[o.length - 1][1], c[1]); else o.push([c[0], c[1]]); });
    return o;
  }
  function combinar(tirar, devolver) {
    var fica = une(tirar.filter(function (c) { return c[1] > c[0]; }));
    une(devolver.filter(function (c) { return c[1] > c[0]; })).forEach(function (d) {
      var novo = [];
      fica.forEach(function (c) {
        if (d[1] <= c[0] || d[0] >= c[1]) { novo.push(c); return; }
        if (d[0] > c[0]) novo.push([c[0], d[0]]);
        if (d[1] < c[1]) novo.push([d[1], c[1]]);
      });
      fica = novo;
    });
    return fica.filter(function (c) { return c[1] - c[0] >= 0.05; }).map(function (c) { return [arred(c[0]), arred(c[1])]; });
  }
  var cache = [];
  function resultado() {
    var t = [], d = [];
    marcas.forEach(function (m) { (m.tipo === 'tirar' ? t : d).push([m.a, m.b]); });
    return combinar(t, d);
  }

  function largura() { return Math.max(roll.clientWidth, 1) * zoom; }
  function x2t(x) { return x / largura() * dur(); }
  function t2x(t) { return t / dur() * largura(); }
  function tDoMouse(ev) { var r = roll.getBoundingClientRect(); return Math.max(0, Math.min(dur(), x2t(ev.clientX - r.left + roll.scrollLeft))); }

  function ondaDesenha() {
    var w = Math.round(largura()), h = 150;
    caixa.style.width = w + 'px'; canvas.width = w; canvas.height = h;
    var g = canvas.getContext('2d'); g.clearRect(0, 0, w, h);
    g.fillStyle = '#7d8590';
    if (picos.length) {
      for (var x = 0; x < w; x++) {
        var i = Math.floor(x / w * picos.length), j = Math.max(i + 1, Math.floor((x + 1) / w * picos.length)), p = 0;
        for (var k = i; k < j && k < picos.length; k++) p = Math.max(p, picos[k]);
        var al = Math.max(1, p * (h - 26)); g.fillRect(x, 22 + (h - 26 - al) / 2, 1, al);
      }
    }
    g.fillStyle = '#aab'; g.font = '11px sans-serif';
    var passo = zoom >= 4 ? 1 : zoom >= 2 ? 2 : 5;
    for (var s = 0; s < dur(); s += passo) { g.fillRect(t2x(s), 0, 1, 8); g.fillText(Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2), t2x(s) + 3, 18); }
  }

  function alca(m, lado, cor) {
    var a = document.createElement('div');
    a.className = 'ed-alca'; a.style.background = cor;
    a.style.left = t2x(lado === 'a' ? m.a : m.b) + 'px';
    a.onmousedown = function (e) {
      e.preventDefault(); e.stopPropagation();
      v.pause();
      function mov(ev) {
        var t = tDoMouse(ev);
        if (lado === 'a') m.a = arred(Math.min(t, m.b - 0.05)); else m.b = arred(Math.max(t, m.a + 0.05));
        v.currentTime = t; desenha();
      }
      function solta() { document.removeEventListener('mousemove', mov); document.removeEventListener('mouseup', solta); }
      document.addEventListener('mousemove', mov); document.addEventListener('mouseup', solta);
    };
    return a;
  }

  function desenha() {
    marcas.sort(function (x, y) { return x.a - y.a; });
    marcasEl.innerHTML = '';
    marcas.forEach(function (m, i) {
      var cor = m.tipo === 'tirar' ? '#e5484d' : '#30a46c';
      var f = document.createElement('div');
      f.className = 'ed-faixa';
      f.style.cssText = 'opacity:' + (i === sel ? .7 : .45) + ';background:' + cor + (i === sel ? ';outline:2px solid #fff;outline-offset:-2px' : '') +
        ';left:' + t2x(m.a) + 'px;width:' + Math.max(2, t2x(m.b) - t2x(m.a)) + 'px;' + (m.tipo === 'devolver' ? 'top:50%;' : '');
      f.onmousedown = function (e) { e.stopPropagation(); };
      f.onclick = function (e) { e.stopPropagation(); escolhe(i); };
      marcasEl.appendChild(f);
      marcasEl.appendChild(alca(m, 'a', cor)); marcasEl.appendChild(alca(m, 'b', cor));
      if (m.bolinha) {
        var b = document.createElement('div');
        b.className = 'ed-bolinha'; b.style.background = cor; b.style.left = t2x((m.a + m.b) / 2) + 'px';
        marcasEl.appendChild(b);
      }
    });
    lista();
    cache = resultado();
    var tira = cache.reduce(function (s, c) { return s + c[1] - c[0]; }, 0);
    $('total').textContent = cache.length ? ('Sai ' + tira.toFixed(1) + ' s · fica ' + (dur() - tira).toFixed(1) + ' s') : 'Nenhum trecho marcado ainda.';
    $('remover').value = JSON.stringify(cache);
    $('aplicar').disabled = !cache.length;
    $('n').textContent = marcas.length;
  }

  function escolhe(i) { sel = i; v.currentTime = Math.max(0, marcas[i].a - 0.3); desenha(); }

  function btn(txt, cls, fn, dica) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'btn mini' + (cls ? ' ' + cls : ''); b.textContent = txt;
    if (dica) b.title = dica;
    b.onclick = function (e) { e.stopPropagation(); fn(); }; return b;
  }
  function ajuste(rotulo, menos, mais) {
    var g = document.createElement('div'); g.className = 'ed-ajuste';
    var s = document.createElement('span'); s.textContent = rotulo; g.appendChild(s);
    g.appendChild(btn('◀', '', menos, rotulo + ' 0,1 s antes')); g.appendChild(btn('▶', '', mais, rotulo + ' 0,1 s depois'));
    return g;
  }

  function lista() {
    var L = $('lista'); L.innerHTML = '';
    marcas.forEach(function (m, i) {
      var r = document.createElement('div'); r.className = 'ed-trecho' + (i === sel ? ' sel' : '');
      var topo = document.createElement('div'); topo.className = 'ed-linha';
      var t = document.createElement('div'); t.className = 'ed-cab';
      t.innerHTML = '<b class="ed-tipo ' + m.tipo + '">' + (m.tipo === 'tirar' ? 'Sai' : 'Volta') + '</b> ' + fmt(m.a) + '–' + fmt(m.b) +
        ' <small>' + (m.b - m.a).toFixed(1) + 's' + (m.ia ? ' · IA' : '') + '</small>';
      t.onclick = function () { escolhe(i); };
      topo.appendChild(t);
      topo.appendChild(btn('▶', '', function () { sel = i; v.currentTime = Math.max(0, m.a - 1.5); parar = m.b + 1.5; v.play(); desenha(); }, 'Ouvir com o trecho'));
      topo.appendChild(btn(m.tipo === 'tirar' ? '↺' : '✂', '', function () { m.tipo = m.tipo === 'tirar' ? 'devolver' : 'tirar'; desenha(); },
        m.tipo === 'tirar' ? 'Devolver: esse trecho volta pro vídeo' : 'Tirar: esse trecho sai do vídeo'));
      topo.appendChild(btn('✕', 'perigo', function () { marcas.splice(i, 1); sel = -1; desenha(); }, 'Apagar a marca'));
      r.appendChild(topo);
      if (i === sel) {
        var aj = document.createElement('div'); aj.className = 'ed-linha';
        aj.appendChild(ajuste('Começo', function () { m.a = arred(Math.max(0, m.a - 0.1)); desenha(); }, function () { m.a = arred(Math.min(m.b - 0.05, m.a + 0.1)); desenha(); }));
        aj.appendChild(ajuste('Fim', function () { m.b = arred(Math.max(m.a + 0.05, m.b - 0.1)); desenha(); }, function () { m.b = arred(Math.min(dur(), m.b + 0.1)); desenha(); }));
        r.appendChild(aj);
      }
      L.appendChild(r);
    });
    var s = L.querySelector('.sel'); if (s) s.scrollIntoView({ block: 'nearest' });
  }

  function nova(a, b, bolinha) {
    a = arred(Math.max(0, a)); b = arred(Math.min(dur(), b));
    if (b - a < 0.05) return;
    marcas.push({ a: a, b: b, tipo: 'tirar', ia: false, bolinha: !!bolinha });
    sel = -1; desenha();
    marcas.forEach(function (m, i) { if (m.a === a && m.b === b) sel = i; });
    lista();
  }
  // um botão só: aperta onde o erro começa, aperta de novo onde termina (tecla C ou M). Pode marcar vários e aplicar tudo no fim.
  var vivo = document.createElement('div'); vivo.className = 'ed-faixa ed-fantasma';
  function corte() {
    var bt = $('b-corte');
    if (ini === null) {
      ini = v.currentTime; marcasEl.appendChild(vivo);
      bt.innerHTML = '■ Termina aqui <kbd>C</kbd>'; bt.classList.add('marcando');
      $('marcando').innerHTML = 'Cortando desde <b>' + fmt(ini) + '</b>. Deixe tocar e aperte de novo onde o erro acaba.';
      return;
    }
    var a = Math.min(ini, v.currentTime), b = Math.max(ini, v.currentTime);
    ini = null; vivo.remove();
    bt.innerHTML = '✂ Cortar daqui <kbd>C</kbd>'; bt.classList.remove('marcando'); $('marcando').textContent = '';
    nova(encaixa(a, 0.12), encaixa(b, 0.12), false);
  }
  function cancela() { if (ini === null) return; ini = null; vivo.remove(); $('b-corte').innerHTML = '✂ Cortar daqui <kbd>C</kbd>'; $('b-corte').classList.remove('marcando'); $('marcando').textContent = ''; }
  $('b-corte').onclick = corte;
  document.addEventListener('keydown', function (e) {
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    var k = e.key.toLowerCase();
    if (k === 'c' || k === 'm') corte(); else if (k === 'escape') cancela();
    else if (e.key === ' ') { e.preventDefault(); v.paused ? v.play() : v.pause(); }
    else if ((k === 'backspace' || k === 'delete') && sel >= 0) { e.preventDefault(); marcas.splice(sel, 1); sel = -1; desenha(); }
  });

  // linha do tempo: clicar leva o vídeo pro ponto; ARRASTAR pinta o trecho que sai
  var arrasto = null, fantasma = document.createElement('div');
  fantasma.className = 'ed-faixa ed-fantasma';
  caixa.addEventListener('mousedown', function (e) {
    e.preventDefault();
    arrasto = { x: e.clientX, t: tDoMouse(e), moveu: false };
    function mov(ev) {
      if (Math.abs(ev.clientX - arrasto.x) < 5 && !arrasto.moveu) return;
      if (!arrasto.moveu) { arrasto.moveu = true; v.pause(); marcasEl.appendChild(fantasma); }
      var t = tDoMouse(ev), a = Math.min(arrasto.t, t), b = Math.max(arrasto.t, t);
      fantasma.style.left = t2x(a) + 'px'; fantasma.style.width = Math.max(2, t2x(b) - t2x(a)) + 'px';
      v.currentTime = t;
    }
    function solta(ev) {
      document.removeEventListener('mousemove', mov); document.removeEventListener('mouseup', solta);
      var t = tDoMouse(ev);
      if (arrasto.moveu) { fantasma.remove(); nova(encaixa(Math.min(arrasto.t, t), 0.2), encaixa(Math.max(arrasto.t, t), 0.2), false); }
      else v.currentTime = t;
      arrasto = null;
    }
    document.addEventListener('mousemove', mov); document.addEventListener('mouseup', solta);
  });

  // laço por quadro: cursor andando liso, prévia pulando o trecho na hora e a rolagem seguindo o cursor
  function quadro() {
    var t = v.currentTime, cx = t2x(t);
    $('c-cursor').style.left = cx + 'px';
    if (ini !== null) { var x0 = t2x(Math.min(ini, t)); vivo.style.left = x0 + 'px'; vivo.style.width = Math.max(2, Math.abs(cx - t2x(ini))) + 'px'; }
    if (!v.paused) {
      if (parar !== null && t >= parar) { v.pause(); parar = null; }
      else if ($('pular').checked && parar === null && ini === null) {
        for (var i = 0; i < cache.length; i++) if (t >= cache[i][0] - 0.02 && t < cache[i][1] - 0.03) { v.currentTime = cache[i][1]; break; }
      }
      if (zoom > 1 && !arrasto && (cx < roll.scrollLeft || cx > roll.scrollLeft + roll.clientWidth - 40)) roll.scrollLeft = cx - 40;
    }
    requestAnimationFrame(quadro);
  }
  requestAnimationFrame(quadro);

  function mudaZoom(d) { zoom = Math.max(1, Math.min(16, d > 0 ? zoom * 2 : zoom / 2)); $('z-n').textContent = zoom + '×'; ondaDesenha(); desenha(); }
  $('z-mais').onclick = function () { mudaZoom(1); }; $('z-menos').onclick = function () { mudaZoom(-1); };
  $('f').addEventListener('submit', function () { var b = $('aplicar'); b.disabled = true; b.textContent = 'Cortando…'; });

  // botão clicado não fica com o foco: senão o espaço (play/pausa) apertava ele de novo
  document.querySelector('.editor').addEventListener('mouseup', function () {
    var a = document.activeElement; if (a && a.tagName === 'BUTTON' && a.id !== 'aplicar') a.blur();
  });
  // passando o mouse na linha do tempo: uma linha e o segundo exato
  var hover = $('c-hover');
  caixa.addEventListener('mousemove', function (e) {
    var t = tDoMouse(e); hover.style.display = 'block'; hover.style.left = t2x(t) + 'px'; hover.dataset.t = fmt(t);
  });
  caixa.addEventListener('mouseleave', function () { hover.style.display = 'none'; });

  function inicia() { ondaDesenha(); desenha(); }
  v.addEventListener('loadedmetadata', inicia);
  if (v.readyState >= 1) inicia();
  fetch('/corte-manual/onda?video=' + encodeURIComponent(dados.video)).then(function (r) { return r.ok ? r.json() : { picos: [] }; })
    .then(function (d) { picos = d.picos || []; POR_S = d.por_segundo || 50; calibra(); ondaDesenha(); }).catch(function () {});
})();
