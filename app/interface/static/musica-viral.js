/* "Música de fundo": Sem música · Com música (o João diz o clima em palavras; o Estúdio procura 3 opções sem voz cantada, com prévia e o motivo; "Outras 3").
   Usado no Novo vídeo e no Editar vídeo. As rotas são as de musica_rotas.py (/musica/viral/opcoes, /procurar, /previa).
   MusicaViral.criar({ raiz, params: () => ({formato, cliente, texto, dur}), padrao: 'viral'|'sem', nome: 'musica', onMudou })
   cria dentro de `raiz` os 3 botões e, no <form>, os campos <nome>_modo, <nome>_faixa e <nome>_titulo. Devolve {valor(), recarregar()}. */
(function () {
  var esc = function (t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;'); };
  var arq = function (c) { return '/arquivo/' + encodeURI(c); };

  function previa(card, faixa, entrada, aviso) {   // baixa (1ª vez) e toca 10 s do trecho
    var a = card.querySelector('audio'), b = card.querySelector('.mv-ouvir');
    if (a.src && !entrada) { a.paused ? a.play() : a.pause(); return Promise.resolve(); }
    b.disabled = true; var t0 = b.textContent; b.textContent = 'Baixando e achando o refrão…';
    return fetch('/musica/viral/previa?faixa=' + encodeURIComponent(faixa) + (entrada != null ? '&entrada=' + entrada : '')).then(function (r) { return r.json(); }).then(function (j) {
      b.disabled = false; b.textContent = t0;
      if (!j.ok) { aviso(j.erro); return; }
      if (!j.confere) { aviso('Marca d\'água ou defeito: ' + j.motivos.join('; ')); return; }
      a.src = arq(j.previa) + '?v=' + Date.now(); a.hidden = false; a.play();
    }).catch(function () { b.disabled = false; b.textContent = t0; aviso('Não consegui falar com o Estúdio.'); });
  }

  function criar(o) {
    var nome = o.nome || 'musica', modo = o.padrao || 'viral', escolhida = { id: '', titulo: '' }, carregado = false, opcoes = [], visto = [], direcao = '', req = 0;
    var raiz = o.raiz;
    raiz.classList.add('mv');
    raiz.innerHTML =
      '<div class="nv-seg mv-modos" role="radiogroup" aria-label="Música de fundo">' +
      '<button type="button" data-mv="sem"><span><b>Sem música</b><small>só a voz e os efeitos</small></span></button>' +
      '<button type="button" data-mv="viral"><span><b>Com música</b><small>você diz o clima, o Estúdio procura 3 opções</small></span></button></div>' +
      '<div class="mv-busca" hidden><input type="search" placeholder="Que tipo de música? (ex.: tensa de suspense, sem voz)" aria-label="Que tipo de música?"> <button type="button" class="btn mini primario">Procurar</button></div>' +
      '<p class="meta mv-msg" aria-live="polite"></p><div class="mv-lista"></div>' +
      '<input type="hidden" name="' + nome + '_modo"><input type="hidden" name="' + nome + '_faixa"><input type="hidden" name="' + nome + '_titulo">';
    var msg = raiz.querySelector('.mv-msg'), lista = raiz.querySelector('.mv-lista'), ini = raiz.querySelectorAll('[data-mv]'), busca = raiz.querySelector('.mv-busca');
    var campo = function (s) { return raiz.querySelector('[name=' + nome + '_' + s + ']'); };
    function grava() { campo('modo').value = modo; campo('faixa').value = modo === 'sem' ? '' : escolhida.id; campo('titulo').value = escolhida.titulo;
      [].forEach.call(ini, function (b) { b.classList.toggle('ativo', b.dataset.mv === modo); });
      if (o.onMudou) o.onMudou({ modo: modo, faixa: escolhida.id, titulo: escolhida.titulo }); }
    function escolhe(id, titulo) { escolhida = { id: id, titulo: titulo }; [].forEach.call(lista.querySelectorAll('.mv-opcao'), function (c) { c.classList.toggle('escolhida', c.dataset.id === id); }); grava(); }

    function card(it, comEscolher) {
      var c = document.createElement('div'); c.className = 'mv-opcao'; c.dataset.id = it.id;
      c.innerHTML = '<div class="mv-txt"><b>' + esc(it.titulo) + '</b> <small>' + esc(it.artista) + '</small>' +
        '<p class="meta">' + esc(it.motivo || '') + '</p>' +
        (it.checagem ? '<p class="meta mv-ok">✓ ' + esc(it.checagem) + '</p>' : '') +
        (it.aviso ? '<p class="meta mv-aviso">' + esc(it.aviso) + '</p>' : '') + '</div>' +
        '<audio controls preload="none" ' + (it.previa ? 'src="' + arq(it.previa) + '"' : 'hidden') + '></audio>' +
        '<div class="mv-acoes">' + (it.previa ? '' : '<button type="button" class="btn mini mv-ouvir">▶ Ouvir 10 s</button>') +
        (comEscolher ? '<button type="button" class="btn mini primario mv-usar">Usar esta</button>' : '') +
        '<button type="button" class="btn mini nao-usar" data-chave="viral:' + esc(it.id) + '" data-titulo="' + esc(it.titulo + ' - ' + it.artista) + '">Não usar mais</button></div>';
      var u = c.querySelector('.mv-usar'), ou = c.querySelector('.mv-ouvir');
      if (u) u.onclick = function () { escolhe(it.id, it.titulo + ' - ' + it.artista); };
      if (ou) ou.onclick = function () { previa(c, it.id, null, function (t) { msg.textContent = t; }); };
      return c;
    }

    function carregarOpcoes(forcar) {
      if (carregado && !forcar) return;
      var p = o.params ? o.params() : {}, meu = ++req;   // resposta velha (de uma busca anterior) é ignorada
      msg.textContent = 'Procurando e ouvindo as faixas pra ver se têm voz cantada… (uns 1 a 2 min na 1ª vez)';
      lista.innerHTML = '';
      var q = new URLSearchParams({ direcao: direcao, formato: p.formato || 'editorial', cliente: p.cliente || '', texto: (p.texto || '').slice(0, 3000), dur: p.dur || 75, n: 3, ignorar: visto.join(',') });
      fetch('/musica/viral/direcao?' + q).then(function (r) { return r.json(); }).then(function (j) {
        if (modo !== 'viral' || meu !== req) return;
        if (!j.ok) { msg.textContent = j.erro; return; }
        carregado = true; opcoes = j.opcoes;
        msg.textContent = j.opcoes.length ? 'Entendi: ' + j.entendi + '. Ouça e escolha (se não escolher, vale a 1ª).' : 'Nada serviu agora. Descreva de outro jeito e clique em Procurar.';
        j.opcoes.forEach(function (it) { lista.appendChild(card(it, true)); });
        if (j.recusadas && j.recusadas.length) { var d = document.createElement('details'); d.className = 'mv-rec';
          d.innerHTML = '<summary class="meta">' + j.recusadas.length + ' ficaram de fora</summary>' + j.recusadas.map(function (r) { return '<p class="meta">' + esc(r.titulo) + ': ' + esc(r.motivos.join('; ')) + '</p>'; }).join(''); lista.appendChild(d); }
        if (j.opcoes.length) escolhe(j.opcoes[0].id, j.opcoes[0].titulo + ' - ' + j.opcoes[0].artista);
        var mais = document.createElement('button'); mais.type = 'button'; mais.className = 'btn mini'; mais.textContent = 'Outras 3';
        mais.onclick = function () { visto = visto.concat(opcoes.map(function (x) { return x.id; })); carregado = false; carregarOpcoes(true); };
        lista.appendChild(mais);
      }).catch(function () { msg.textContent = 'Não consegui falar com o Estúdio. Tente de novo.'; });
    }

    // não é <form>: no Novo vídeo a página inteira já é um formulário (form dentro de form some no navegador)
    function procurarAgora() { direcao = busca.querySelector('input').value.trim(); visto = []; carregado = false; carregarOpcoes(true); }
    busca.querySelector('button').onclick = procurarAgora;
    busca.querySelector('input').onkeydown = function (e) { if (e.key === 'Enter') { e.preventDefault(); procurarAgora(); } };

    function mostrar(m) {
      if (m === 'procurar') m = 'viral';   // o antigo "Procurar" virou o campo de direção do "Com música"
      modo = m; lista.innerHTML = ''; msg.textContent = ''; busca.hidden = m !== 'viral';
      if (!m || m === 'sem') { escolhida = { id: '', titulo: '' }; grava(); return; }   // padrao '' (Editar vídeo): nada escolhido até o João clicar
      grava(); carregarOpcoes(false);
    }
    [].forEach.call(ini, function (b) { b.onclick = function () { mostrar(b.dataset.mv); }; });
    mostrar(modo);
    return { valor: function () { return { modo: modo, faixa: escolhida.id, titulo: escolhida.titulo }; },
             recarregar: function () { visto = []; carregado = false; if (modo === 'viral') carregarOpcoes(true); }, mostrar: mostrar };
  }
  document.addEventListener('click', function (e) {   // "Não usar mais" nas opções: a faixa nunca mais volta (acervo/musicas-reprovadas.jsonl)
    var b = e.target.closest('.mv .nao-usar'); if (!b) return; e.preventDefault();
    var fd = new URLSearchParams(); fd.append('chave', b.dataset.chave || ''); fd.append('titulo', b.dataset.titulo || ''); b.disabled = true;
    fetch('/musica/reprovar', { method: 'POST', body: fd }).then(function (r) { return r.json(); }).then(function (j) {
      var c = b.closest('.mv-opcao'); if (!j.ok) { b.disabled = false; alert(j.erro || 'Não deu.'); return; }
      if (c) { c.style.opacity = .4; c.querySelector('.mv-acoes').innerHTML = '<span class="meta">Não aparece mais.</span>'; } });
  });
  window.MusicaViral = { criar: criar, previa: previa };
})();
