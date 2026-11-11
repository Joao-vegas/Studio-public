// Tela Elenco do Explicador 3D: grade de personagens em 3D + editor de cor/roupa/cabelo/pele + salvar no elenco do estilo.
(function () {
  var D = JSON.parse(document.getElementById('el-dados').textContent);
  var $ = function (id) { return document.getElementById(id); };
  var E, vit, vivo, itens = [], sel = null, d = null, salvoSpec = null;

  var ROUPA = ['#eef2f5', '#22252e', '#2e8fb8', '#b3202c', '#e8b23a', '#4a8a52', '#c8507a', '#7a6a4a', '#5a3a8a', '#e07a2a'];
  var CALCA = ['#26303f', '#111111', '#3b5b8c', '#6b5a45', '#5a6a7a', '#3a4a6a', '#7a6a4a', '#e8e8e8'];
  var CABELO = ['#111111', '#2a1a10', '#3a2416', '#8a5a2a', '#c99a3a', '#d8c060', '#9a9a9a', '#cfcfcf', '#b3202c'];
  var PELE = ['#f0cdb2', '#e8b896', '#dcaa86', '#c98f68', '#b8784e', '#9a5f3c', '#6e4429', '#4a2c1a'];
  var SAPATO = ['#1d1f27', '#6b4a33', '#e8e8e8', '#a8322a', '#2a3a5a'];
  var ESTILOS = [['careca', 'Careca'], ['curto', 'Curto'], ['topete', 'Topete'], ['espetado', 'Espetado'], ['franja', 'Franja'], ['cacheado', 'Cacheado'],
    ['coque', 'Coque'], ['rabo', 'Rabo'], ['longo', 'Longo']];

  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  var rot = function (n) { return D.rotulos[n] || (n.charAt(0).toUpperCase() + n.slice(1).replace(/_/g, ' ')); };
  var hex6 = function (c) { c = String(c || '#000000'); return /^#[0-9a-f]{3}$/i.test(c) ? '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3] : c; };
  var limpo = function (o) { var r = {}; Object.keys(o).forEach(function (k) { if (k.charAt(0) !== '_' && o[k] != null) r[k] = o[k]; }); return r; };

  function mostrarErro(t) { var e = $('el-erro'); e.textContent = t || ''; e.hidden = !t; }

  // ── lista de cartões: os personagens prontos (com o figurino do estilo, se o João mudou) + os que ele criou
  function montarItens() { itens = E.itens(D.elenco); }

  function cartao(it) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'el-card'; b.dataset.nome = it.nome;
    b.innerHTML = '<canvas width="300" height="400"></canvas><b>' + rot(it.nome) + '</b>' +
      (it.mudou ? '<span class="selo ok">' + (it.novo ? 'criado' : 'alterado') + '</span>' : '');
    b.onclick = function () { abrir(it); };
    it.cartao = b; return b;
  }

  async function desenharTodos() {
    for (var i = 0; i < itens.length; i++) {
      var it = itens[i]; if (!it.cartao) continue;
      try { vit.desenhar(it.cartao.querySelector('canvas'), E.resolver(it.spec)); } catch (e) { console.warn(it.nome, e); }
      await new Promise(function (r) { setTimeout(r, 0); });
    }
  }

  function grade() {
    montarItens();
    var g = $('el-grade'); g.innerHTML = '';
    itens.forEach(function (it) { g.appendChild(cartao(it)); });
    return desenharTodos();
  }

  // ── editor
  function abrir(it) {
    sel = it; d = E.resolver(it.spec); salvoSpec = clone(d);
    [].forEach.call(document.querySelectorAll('.el-card'), function (c) { c.classList.toggle('ativo', c.dataset.nome === it.nome); });
    $('el-vazio').hidden = true; $('el-editor').hidden = false;
    $('el-titulo').textContent = rot(it.nome);
    $('el-nome').value = it.nome; $('el-msg').textContent = '';
    if (!vivo) { vivo = E.vivo($('el-vivo')); $('el-vivo').__vivo = vivo; }
    vivo.enquadrar('busto'); marcarEnq('busto');
    controles(); atualizar();
    if (window.innerWidth <= 900) $('el-painel').scrollIntoView({ behavior: 'smooth' });
  }

  // o que mudou em relação ao original: campo de cima inteiro (o motor troca o objeto todo, não mescla por dentro); removido vira null
  function diferenca() {
    var base = limpo(E.ELENCO[sel.base]), atual = limpo(d), troca = {};
    Object.keys(atual).forEach(function (k) { if (JSON.stringify(atual[k]) !== JSON.stringify(base[k])) troca[k] = atual[k]; });
    Object.keys(base).forEach(function (k) { if (!(k in atual)) troca[k] = null; });
    return troca;
  }

  function atualizar() {
    vivo.mostrar(d);
    var nome = $('el-nome').value.trim();
    var novo = nome && nome !== sel.nome;
    $('el-salvar').textContent = 'Salvar no elenco';
    $('el-nome-dica').textContent = novo ? 'Vira um personagem novo do elenco, nascido de ' + rot(sel.base) + '.' :
      (sel.novo ? 'Salva por cima deste personagem do elenco.' : 'Mesmo nome: troca o figurino de ' + rot(sel.base) + ' em todos os vídeos do estilo.');
    var temSalvo = !!(D.elenco || {})[sel.nome];
    $('el-voltar').hidden = !temSalvo;
    $('el-voltar').textContent = sel.novo ? 'Apagar este personagem' : 'Voltar ao original';
    $('el-desfazer').disabled = JSON.stringify(limpo(d)) === JSON.stringify(limpo(salvoSpec));
  }

  function mudou() { atualizar(); }
  var ENQ_ROT = { busto: 'Meio corpo', tudo: 'Corpo inteiro' };
  function marcarEnq(m) { [].forEach.call(document.querySelectorAll('#el-enq button'), function (b) { b.classList.toggle('ativo', b.dataset.enq === m); }); }
  function enquadrar(m) { if (vivo) vivo.enquadrar(m); marcarEnq(m); }
  [].forEach.call(document.querySelectorAll('#el-enq button'), function (b) { b.onclick = function () { enquadrar(b.dataset.enq); }; });
  function pai(chave) { d[chave] = d[chave] || {}; return d[chave]; }

  // ── peças de controle
  function amostras(rotulo, paleta, ler, gravar) {
    var l = document.createElement('div'); l.className = 'el-linha';
    l.innerHTML = '<span>' + rotulo + '</span>';
    var s = document.createElement('div'); s.className = 'el-sw'; l.appendChild(s);
    var inp = document.createElement('input'); inp.type = 'color';
    function marcar() {
      var atual = hex6(ler()).toLowerCase(); inp.value = atual;
      [].forEach.call(s.querySelectorAll('button'), function (b) { b.classList.toggle('ativo', b.dataset.cor === atual); });
    }
    paleta.forEach(function (c) { var b = document.createElement('button'); b.type = 'button'; b.dataset.cor = hex6(c).toLowerCase(); b.title = c; b.style.background = c;
      b.onclick = function () { gravar(c); marcar(); mudou(); }; s.appendChild(b); });
    inp.oninput = function () { gravar(inp.value); marcar(); mudou(); };
    s.appendChild(inp); marcar(); return l;
  }
  function opcoes(rotulo, lista, ler, gravar) {
    var l = document.createElement('div'); l.className = 'el-linha'; l.innerHTML = '<span>' + rotulo + '</span>';
    var o = document.createElement('div'); o.className = 'el-opcoes'; l.appendChild(o);
    function marcar() { var v = ler(); [].forEach.call(o.children, function (b, i) { b.classList.toggle('ativo', lista[i][0] === v); }); }
    lista.forEach(function (it) { var b = document.createElement('button'); b.type = 'button'; b.textContent = it[1];
      b.onclick = function () { gravar(it[0]); marcar(); mudou(); }; o.appendChild(b); });
    marcar(); return l;
  }
  // enq: pra onde a câmera vai quando você mexe neste grupo (cima/rosto = perto, baixo = pernas e sapato)
  function grupo(titulo, filhos, enq) {
    var g = document.createElement('div'); g.className = 'el-grupo'; g.innerHTML = '<h3>' + titulo + '</h3>'; g.dataset.enq = enq || 'busto';
    filhos.forEach(function (f) { if (f) g.appendChild(f); });
    var foco = function () { if (vivo) { vivo.enquadrar(g.dataset.enq); marcarEnq(g.dataset.enq === 'baixo' || g.dataset.enq === 'tudo' ? 'tudo' : 'busto'); } };
    g.addEventListener('pointerdown', foco); g.addEventListener('focusin', foco);
    return g;
  }
  // controle que não faz sentido pra este personagem: some e fica a razão em uma linha
  // linha de um detalhe pequeno (gola do jaleco, gravata): a câmera chega perto só enquanto você mexe nela
  function pertinho(linha) {
    var foco = function (e) { e.stopPropagation(); if (vivo) { vivo.enquadrar('pescoco'); marcarEnq('busto'); } };
    linha.addEventListener('pointerdown', foco); linha.addEventListener('focusin', foco); return linha;
  }
  function nota(texto) { var p = document.createElement('p'); p.className = 'meta el-nota'; p.textContent = texto; return p; }

  function controles() {
    var box = $('el-controles'); box.innerHTML = '';
    var ct = function () { return d.camisa || {}; };
    var tipo = function () { return ct().tipo || ''; };
    var soTipo = function (t) { return tipo() === t; };

    function trocarTipo(t) {
      var c = pai('camisa');
      if (t) c.tipo = t; else delete c.tipo;
      if (t !== 'jaleco') delete c.cor2;
      if (t !== 'terno') { delete c.gravata; delete c.cor3; }
      if (t === 'jaleco' && !c.cor2) c.cor2 = '#2ec4b6';
      if (t === 'terno') { c.gravata = c.gravata || '#b4232c'; c.cor3 = c.cor3 || '#f2f2f2'; }
      // moletom, jaleco e terno são de manga longa e lisos: tira o que ficaria escondido ou estranho por baixo
      if (t === 'moletom' || t === 'jaleco' || t === 'terno') { delete c.manga; delete c.estampa; }
      if (t === 'moletom') c.capuz = true; else delete c.capuz;
      delete c.gola;   // o "gola: true" das camisas prontas é só sombra; quem escolhe Gola ganha a gola alta de verdade
      controles();
    }

    var roupa = [
      opcoes('Tipo de roupa', [['', 'Camisa'], ['moletom', 'Moletom'], ['gola', 'Gola'], ['jaleco', 'Jaleco'], ['terno', 'Terno']], tipo, trocarTipo),
      amostras('Cor da roupa', ROUPA, function () { return ct().cor || '#3a6ea5'; }, function (c) { pai('camisa').cor = c; }),
    ];
    if (soTipo('jaleco')) roupa.push(pertinho(amostras('Gola do jaleco (detalhe pequeno)', ROUPA, function () { return ct().cor2 || '#2ec4b6'; }, function (c) { pai('camisa').cor2 = c; })));
    if (soTipo('terno')) {
      roupa.push(amostras('Gravata', ROUPA, function () { return ct().gravata || '#b4232c'; }, function (c) { pai('camisa').gravata = c; }));
      roupa.push(amostras('Camisa por dentro', ROUPA, function () { return ct().cor3 || '#f2f2f2'; }, function (c) { pai('camisa').cor3 = c; }));
    }
    if (soTipo('moletom')) {
      roupa.push(opcoes('Capuz e bolso', [['nao', 'Sem'], ['sim', 'Com']], function () { return ct().capuz ? 'sim' : 'nao'; },
        function (v) { var c = pai('camisa'); if (v === 'sim') c.capuz = true; else delete c.capuz; }));
    }
    if (!soTipo('jaleco') && !soTipo('terno') && !soTipo('moletom')) {
      roupa.push(opcoes('Manga', [['', 'Longa'], ['curta', 'Curta']], function () { return ct().manga || ''; },
        function (v) { var c = pai('camisa'); if (v) c.manga = v; else delete c.manga; }));
    }
    if (!soTipo('jaleco') && !soTipo('terno')) {
      roupa.push(opcoes('Estampa', [['', 'Lisa'], ['florida', 'Florida'], ['xadrez', 'Xadrez'], ['listra', 'Listrada']], function () { return ct().estampa || ''; },
        function (v) { var c = pai('camisa'); if (v) c.estampa = v; else delete c.estampa; }));
    }
    if (soTipo('moletom')) roupa.push(nota('Moletom é de manga longa.'));
    if (soTipo('jaleco') || soTipo('terno')) roupa.push(nota((soTipo('jaleco') ? 'Jaleco' : 'Terno') + ' é liso e de manga longa: sem estampa nem manga curta.'));
    box.appendChild(grupo('Parte de cima', roupa, 'busto'));

    var cl = function () { return d.calca || {}; };
    box.appendChild(grupo('Parte de baixo', [
      opcoes('Tipo', [['', 'Calça'], ['bermuda', 'Bermuda'], ['saia', 'Saia']], function () { return cl().tipo || ''; },
        function (v) { var c = pai('calca'); if (v) c.tipo = v; else delete c.tipo; controles(); }),
      amostras('Cor', CALCA, function () { return cl().cor || '#2b3550'; }, function (c) { pai('calca').cor = c; }),
      amostras('Sapato', SAPATO, function () { return d.sapato || '#1d1f27'; }, function (c) { d.sapato = c; }),
    ], 'baixo'));

    var cab = function () { return d.cabelo || {}; };
    var cabelo = [
      opcoes('Corte', ESTILOS, function () { return cab().estilo || 'curto'; }, function (v) { pai('cabelo').estilo = v; controles(); }),
      (cab().estilo === 'careca') ? nota('Careca: não tem cabelo pra pintar.') :
        amostras('Cor do cabelo', CABELO, function () { return cab().cor || '#3a2416'; }, function (c) { pai('cabelo').cor = c; }),
      opcoes('Boné', [['nao', 'Sem boné'], ['sim', 'Com boné']], function () { return d.bone ? 'sim' : 'nao'; },
        function (v) { if (v === 'sim') d.bone = d.bone || '#1f6fb0'; else d.bone = null; controles(); }),
    ];
    if (d.bone) cabelo.push(amostras('Cor do boné', ROUPA, function () { return d.bone; }, function (c) { d.bone = c; }));
    box.appendChild(grupo('Cabelo', cabelo, 'rosto'));

    var rosto = [
      amostras('Pele', PELE, function () { return d.pele || '#d9a37e'; }, function (c) { d.pele = c; }),
      opcoes('Óculos', [['', 'Sem'], ['true', 'Normal'], ['escuro', 'Escuro']], function () { return d.oculos === true ? 'true' : (d.oculos || ''); },
        function (v) { d.oculos = v === 'true' ? true : (v || null); }),
    ];
    var mulher = !!d.mulher || cl().tipo === 'saia' || ['coque', 'rabo', 'longo'].indexOf(cab().estilo) >= 0;
    if (mulher) rosto.push(nota('Barba: só nos personagens homens.'));
    else rosto.push(opcoes('Barba', [['nenhuma', 'Barbeado'], ['', 'Por fazer'], ['curta', 'Curta'], ['barbuda', 'Barbuda']], function () { return d.barba === 'cheia' ? 'curta' : (d.barba || ''); },
      function (v) { d.barba = v || null; }));
    rosto.push(opcoes('Bigode', [['nao', 'Sem'], ['fino', 'Fino'], ['grosso', 'Grosso']], function () { return d.bigode === 'grosso' ? 'grosso' : (d.bigode ? 'fino' : 'nao'); },
      function (v) { d.bigode = v === 'grosso' ? 'grosso' : (v === 'fino' ? true : null); }));
    box.appendChild(grupo('Rosto', rosto, 'rosto'));
  }

  // ── salvar / voltar
  function post(url, corpo) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
      .then(function (r) { return r.json(); });
  }
  function recarregarGrade(nomeAtivo) {
    return grade().then(function () {
      var it = itens.filter(function (x) { return x.nome === nomeAtivo; })[0];
      if (it) { it.cartao.classList.add('ativo'); sel = it; salvoSpec = clone(d); atualizar(); }
    });
  }

  $('el-salvar').onclick = function () {
    var nome = $('el-nome').value.trim(), troca = diferenca();
    if (!nome) { $('el-msg').textContent = 'Dê um nome pro personagem.'; return; }
    if (!Object.keys(troca).length && nome === sel.nome && !sel.novo) { $('el-msg').textContent = 'Você ainda não mudou nada.'; return; }
    $('el-msg').textContent = 'Salvando…';
    post('/elenco/' + D.slug + '/salvar', { nome: nome, base: sel.base, troca: troca }).then(function (j) {
      if (!j.ok) { $('el-msg').textContent = '✗ ' + j.erro; return; }
      D.elenco[j.nome] = Object.assign({ base: sel.base }, troca);
      $('el-nome').value = j.nome; $('el-titulo').textContent = rot(j.nome);
      return recarregarGrade(j.nome).then(function () { $('el-msg').textContent = '✓ Salvo no elenco do Explicador 3D. Os próximos vídeos do estilo usam este figurino.'; });
    });
  };
  $('el-voltar').onclick = function () {
    $('el-msg').textContent = 'Voltando…';
    var nome = sel.nome, eraNovo = sel.novo;
    post('/elenco/' + D.slug + '/voltar', { nome: nome }).then(function (j) {
      if (!j.ok) { $('el-msg').textContent = '✗ ' + j.erro; return; }
      delete D.elenco[nome];
      grade().then(function () {
        var it = itens.filter(function (x) { return x.nome === nome; })[0];
        if (it) { abrir(it); $('el-msg').textContent = '✓ De volta ao original.'; }
        else { sel = null; $('el-editor').hidden = true; $('el-vazio').hidden = false; }
      });
    });
  };
  $('el-desfazer').onclick = function () { d = clone(salvoSpec); controles(); atualizar(); $('el-msg').textContent = ''; };
  $('el-nome').oninput = atualizar;

  ElencoPrevia.carregar(D.previa).then(function (m) {
    E = m; vit = E.vitrine(300, 400);
    $('el-carregando').remove();
    return grade();
  }).catch(function (e) {
    console.error(e);
    mostrarErro('Não consegui montar a prévia 3D neste navegador (' + e.message + '). Os personagens continuam valendo no vídeo.');
  });
})();
