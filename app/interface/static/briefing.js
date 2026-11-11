/* Passo 0 "Conversar" e o seletor de referência (vídeo → pausa → "Marcar este momento").
   O seletor usa as mesmas classes do "Quero alterar" de Em andamento (and-ref*); aqui a lista de vídeos pode mudar
   (referências do formato, vídeos que a IA achou nas pastas). O Criar usa o mesmo seletor. */
(function () {
  var esc = function (t) { var x = document.createElement('span'); x.textContent = t == null ? '' : t; return x.innerHTML; };
  var fmt = function (s) { s = +s || 0; return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0'); };
  var chave = function (o) { return (o.pasta || '') + '|' + o.rel; };

  // opção: {video, poster, rel, pasta, nome} · valor: {rel, pasta, nome, segundo}
  function SeletorRef(raiz, aoMudar) {
    raiz.innerHTML = '<div class="and-refs-fila" hidden></div><div class="and-ref-player" hidden><video controls playsinline preload="metadata"></video>' +
      '<button type="button" class="btn mini" data-marcar>Marcar este momento</button></div>' +
      '<p class="and-ref-marca" hidden>Referência: <b></b> <button type="button" class="btn mini" data-limpa aria-label="Tirar a referência">×</button></p>';
    var fila = raiz.querySelector('.and-refs-fila'), player = raiz.querySelector('.and-ref-player'), video = player.querySelector('video'),
      marca = raiz.querySelector('.and-ref-marca'), opcoes = [], atual = null, valor = null;
    function realca() { var a = atual || valor; fila.querySelectorAll('.and-ref').forEach(function (b) { b.classList.toggle('ativo', !!a && chave(opcoes[+b.dataset.i]) === chave(a)); }); }
    function desenha() {
      fila.innerHTML = opcoes.map(function (o, i) {
        return '<button type="button" class="and-ref" data-i="' + i + '" title="' + esc(o.nome) + '"><img loading="lazy" alt="" src="' + esc(o.poster) + '"><span>' + esc(o.nome) + '</span></button>';
      }).join('');
      fila.hidden = !opcoes.length;
      fila.querySelectorAll('.and-ref').forEach(function (b) { b.addEventListener('click', function () { abre(opcoes[+b.dataset.i]); }); });
      realca();
    }
    function abre(o, seg) {
      atual = o; player.hidden = false; video.src = o.video;
      if (seg != null) video.addEventListener('loadedmetadata', function pula() { video.currentTime = +seg; video.removeEventListener('loadedmetadata', pula); });
      else video.play().catch(function () {});
      realca();
    }
    function mostra() { realca(); marca.hidden = !valor; if (valor) marca.querySelector('b').textContent = valor.nome + (valor.segundo != null ? ', ' + fmt(valor.segundo) : ''); }
    raiz.querySelector('[data-marcar]').addEventListener('click', function () {
      if (!atual) return;
      valor = {rel: atual.rel, pasta: atual.pasta || '', nome: atual.nome, segundo: +video.currentTime.toFixed(1)};
      mostra(); if (aoMudar) aoMudar(valor);
    });
    raiz.querySelector('[data-limpa]').addEventListener('click', function () { valor = null; mostra(); if (aoMudar) aoMudar(null); });
    return {
      opcoes: function (lista) {
        var vistos = {};
        opcoes = (lista || []).filter(function (o) { var k = chave(o); if (!o || !o.rel || vistos[k]) return false; vistos[k] = 1; return true; });
        desenha();
      },
      junta: function (o) { if (!opcoes.some(function (x) { return chave(x) === chave(o); })) { opcoes.unshift(o); desenha(); } },
      valor: function (v, abrir) {
        valor = v && v.rel ? v : null; mostra();
        var o = valor && opcoes.filter(function (x) { return chave(x) === chave(valor); })[0];
        if (o && abrir) abre(o, valor.segundo);
      },
      atual: function () { return valor; }
    };
  }
  window.SeletorRef = SeletorRef;

  var D = window.CONVERSA;
  if (!D) return;

  // ───────────── passo 0 ─────────────
  var $ = function (id) { return document.getElementById(id); };
  var conv = D.conversa, bid = conv ? conv.id : '', modelo = D.modelo, cliente = D.cliente;
  var custo = conv ? +conv.estado.custo_usd || 0 : 0, teto = conv ? conv.teto_usd : D.tetos[modelo];
  var b = conv ? conv.briefing : {objetivo: '', formato_sugerido: {slug: D.formato || '', porque: ''}, cliente: cliente, entrada: '', roteiro: '',
    peculiaridade: '', material_liberado: [], referencia: {video: '', segundo: null, o_que_copiar: ''}, proibido: [], descartavel: false, perguntas_abertas: []};
  var pastasLista = D.pastas || [], marcadas = conv ? (conv.estado.pastas || []).slice() : [], enviando = false, criando = null;
  var falasEl = $('cv-falas');

  function api(url, corpo) {
    return fetch(url, corpo === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)})
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.erro || 'Não deu certo. Tente de novo.'); return d; }); });
  }
  var dinheiro = function (v) { return 'US$ ' + (+v || 0).toFixed(2).replace('.', ','); };
  var nomeArq = function (a) { return String(a || '').split('/').pop(); };
  var ehVideo = function (a) { return /\.(mp4|mov|m4v|webm|mkv)$/i.test(a || ''); };
  var mesmo = function (m, pasta, arq) { return (m.pasta || '').toLowerCase() === (pasta || '').toLowerCase() && m.arquivo === arq; };
  function arquivoUrl(pasta, arq, video) { return '/conversar/' + encodeURIComponent(bid) + '/arquivo?pasta=' + encodeURIComponent(pasta) + '&arquivo=' + encodeURIComponent(arq) + (video ? '&video=1' : ''); }
  function custoTela() { var c = $('cv-custo'); c.textContent = dinheiro(custo); c.title = 'Teto desta conversa: ' + dinheiro(teto); }
  function modeloTela() { document.querySelectorAll('[data-modelo]').forEach(function (x) { x.classList.toggle('ativo', x.dataset.modelo === modelo); }); }

  // A conversa só nasce no disco quando o João manda a primeira fala ou mexe no card.
  function garantir() {
    if (bid) return Promise.resolve(bid);
    if (criando) return criando;
    criando = api('/conversa/nova', {cliente: cliente, formato: (b.formato_sugerido || {}).slug || '', pastas: marcadas, modelo: modelo, descartavel: !!b.descartavel})
      .then(function (d) {
        bid = d.id; teto = d.teto_usd; history.replaceState(null, '', '?id=' + encodeURIComponent(bid)); recusadas(d.recusadas);
        return api('/conversa/' + bid + '/briefing', lerCard());
      }).then(function (r) { b = r.briefing; return bid; })
      .catch(function (e) { criando = null; throw e; });
    return criando;
  }
  function recusadas(lista) { (lista || []).forEach(function (r) { aviso('A pasta ' + r.nome + ' ficou de fora: ' + r.motivo + '.'); }); }

  // ── pastas ligadas ──
  function chips() {
    var el = $('cv-pastas');
    el.innerHTML = pastasLista.length ? pastasLista.map(function (p) {
      var doCli = p.nivel === 'cliente', on = doCli || marcadas.indexOf(p.nome) >= 0;
      return '<label class="pessoa cv-chip' + (on ? ' escolhido' : '') + '" title="' + (doCli ? 'Pasta do cliente: entra sempre' : 'Clique pra ligar ou tirar deste vídeo') + '">' +
        '<input type="checkbox" hidden value="' + esc(p.nome) + '"' + (on ? ' checked' : '') + (doCli ? ' disabled' : '') + '><span>' + esc(p.nome) + (on ? ' ✓' : '') + '</span></label>';
    }).join('') : '<small class="sub">Nenhuma pasta ainda.</small>';
    el.querySelectorAll('input:not(:disabled)').forEach(function (i) {
      i.addEventListener('change', function () {
        marcadas = marcadas.filter(function (n) { return n !== i.value; }); if (i.checked) marcadas.push(i.value);
        chips(); salvaPastas();
      });
    });
  }
  function salvaPastas() { if (bid) api('/conversa/' + bid + '/ajustar', {pastas: marcadas}).then(function (d) { recusadas(d.recusadas); }).catch(function (e) { aviso(e.message); }); }
  function recarregaPastas() {
    return api('/conversar/pastas?cliente=' + encodeURIComponent(cliente)).then(function (l) {
      pastasLista = l; var nomes = l.map(function (p) { return p.nome; });
      marcadas = marcadas.filter(function (n) { return nomes.indexOf(n) >= 0; }); chips();
    });
  }
  function trocaCliente(novo) {
    if (novo === cliente) return;
    cliente = novo; b.cliente = novo; $('cv-cliente').value = novo;
    $('cv-pular').href = '/criar-agora' + (novo ? '?cliente=' + encodeURIComponent(novo) : '');
    recarregaPastas().then(function () { if (bid) salvar(true).then(salvaPastas); });
  }
  $('cv-cliente').addEventListener('change', function () { trocaCliente(this.value); });

  var caixa = $('cv-ligar-box');
  $('cv-ligar').addEventListener('click', function () {
    var t = [['outro', 'Pasta minha (vale pra todos)'], ['referência', 'Referências'], ['swipe', 'Swipe file']];
    if (cliente && cliente !== D.avulso) t.unshift(['cliente', 'Do ' + cliente + ' (só nos vídeos dele)']);
    $('cv-ligar-tipo').innerHTML = t.map(function (x) { return '<option value="' + esc(x[0]) + '">' + esc(x[1]) + '</option>'; }).join('');
    caixa.hidden = !caixa.hidden;
  });
  $('cv-ligar-fecha').addEventListener('click', function () { caixa.hidden = true; });
  function ligar(caminho, botao) {
    var bt = botao || (caminho ? $('cv-ligar-ok') : $('cv-finder')); bt.disabled = true;
    api('/conversar/ligar', {caminho: caminho, tipo: $('cv-ligar-tipo').value, cliente: cliente}).then(function (d) {
      pastasLista = d.pastas; if (d.pasta.tipo !== 'cliente' && marcadas.indexOf(d.pasta.nome) < 0) marcadas.push(d.pasta.nome);
      chips(); salvaPastas(); caixa.hidden = true; $('cv-ligar-caminho').value = ''; $('cv-ligar-nome').value = ''; $('cv-achados').innerHTML = '';
      if (!d.tem_manifesto) propoeManifesto(d.pasta.nome);
    }).catch(function (e) { aviso(e.message); }).then(function () { bt.disabled = false; });
  }
  // ── ligar pelo nome: o João digita "marca3" e escolhe entre os candidatos ──
  var esperaNome = null, seqNome = 0;
  $('cv-ligar-nome').addEventListener('input', function () {
    var q = this.value.trim(), n = ++seqNome, lista = $('cv-achados'); clearTimeout(esperaNome);
    if (q.length < 2) { lista.innerHTML = ''; return; }
    esperaNome = setTimeout(function () {
      api('/conversar/achar?q=' + encodeURIComponent(q)).then(function (r) {
        if (n !== seqNome) return;
        lista.innerHTML = r.length ? r.map(function (c, i) {
          return '<div class="cv-achado"><span><b>' + esc(c.nome) + '</b> <small>' + esc(c.caminho) + '</small><br><small>' +
            (c.tem_manifesto ? 'tem direcionamento ✓ · ' : '') + esc(c.tamanho) + (c.ligada ? ' · já ligada' : '') + '</small></span>' +
            '<button type="button" class="btn mini primario" data-i="' + i + '">' + (c.ligada ? 'Usar' : 'Ligar') + '</button></div>';
        }).join('') : '<small class="sub">Não achei pasta com esse nome. Use “Procurar no Mac” ou cole o caminho.</small>';
        lista.querySelectorAll('button').forEach(function (bt) { bt.addEventListener('click', function () { ligar(r[+bt.dataset.i].caminho, bt); }); });
      }).catch(function (e) { aviso(e.message); });
    }, 250);
  });
  // ── direcionamento (ESTUDIO.md): rascunho local, só grava na pasta depois do OK ──
  var pastaManifesto = '';
  function propoeManifesto(nome) {
    api('/conversar/manifesto/propor', {nome: nome}).then(function (r) {
      if (r.existe) return;
      pastaManifesto = nome; $('cv-manifesto-texto').value = r.texto; $('cv-manifesto').hidden = false;
    }).catch(function () {});
  }
  $('cv-manifesto-nao').addEventListener('click', function () { $('cv-manifesto').hidden = true; });
  $('cv-manifesto-ok').addEventListener('click', function () {
    var bt = this; bt.disabled = true;
    api('/conversar/manifesto/gravar', {nome: pastaManifesto, texto: $('cv-manifesto-texto').value, aprovado: true})
      .then(function () { $('cv-manifesto').hidden = true; aviso('Direcionamento gravado na pasta ' + pastaManifesto + '.'); })
      .catch(function (e) { aviso(e.message); }).then(function () { bt.disabled = false; });
  });
  $('cv-finder').addEventListener('click', function () { ligar(''); });
  $('cv-ligar-ok').addEventListener('click', function () { var c = $('cv-ligar-caminho').value.trim(); if (c) ligar(c); else $('cv-ligar-caminho').focus(); });

  // ── modelo ──
  document.querySelectorAll('[data-modelo]').forEach(function (x) {
    x.addEventListener('click', function () {
      modelo = x.dataset.modelo; modeloTela();
      if (!bid) { teto = D.tetos[modelo]; custoTela(); return; }
      api('/conversa/' + bid + '/ajustar', {modelo: modelo}).then(function (d) { teto = d.teto_usd; custoTela(); }).catch(function (e) { aviso(e.message); });
    });
  });

  // ── card "Briefing até agora" ──
  var seletor = SeletorRef($('bf-ref'), function (v) {
    b.referencia = {video: v ? (v.pasta ? v.pasta + '/' + v.rel : v.rel) : '', segundo: v ? v.segundo : null, o_que_copiar: $('bf-copiar').value};
    salvar(true);
  });
  var refsFormato = [], vistos = [];
  function opcoesRef() { seletor.opcoes(vistos.concat(refsFormato)); seletor.valor(refAtual(), false); }
  function refAtual() {
    var v = (b.referencia || {}).video || '';
    if (!v || /^https?:/.test(v)) return null;
    var i = v.indexOf('/'), pasta = v.slice(0, i), nomes = pastasLista.map(function (p) { return p.nome.toLowerCase(); });
    var ehPasta = i > 0 && nomes.indexOf(pasta.toLowerCase()) >= 0;
    var o = ehPasta ? {pasta: pasta, rel: v.slice(i + 1)} : {pasta: '', rel: v};
    if (ehPasta && bid) seletor.junta({video: arquivoUrl(o.pasta, o.rel, true), poster: arquivoUrl(o.pasta, o.rel), rel: o.rel, pasta: o.pasta, nome: nomeArq(o.rel)});
    return {rel: o.rel, pasta: o.pasta, nome: nomeArq(o.rel), segundo: (b.referencia || {}).segundo};
  }
  var ultimoFormato = null;
  function refsDoFormato(slug) {
    if (slug === ultimoFormato) return; ultimoFormato = slug;
    if (!slug) { refsFormato = []; opcoesRef(); return; }
    api('/api/referencias/' + encodeURIComponent(slug)).then(function (l) { refsFormato = l; opcoesRef(); }).catch(function () {});
  }
  function lista(t) { return String(t || '').split(/[,;\n]/).map(function (x) { return x.trim(); }).filter(Boolean); }
  function lerCard() {
    return {objetivo: $('bf-objetivo').value, formato_sugerido: {slug: $('bf-formato').value}, cliente: cliente, entrada: $('bf-entrada').value,
      roteiro: $('bf-roteiro').value, peculiaridade: $('bf-peculiaridade').value, proibido: lista($('bf-proibido').value),
      descartavel: $('bf-descartavel').checked, material_liberado: b.material_liberado || [],
      referencia: {video: (b.referencia || {}).video || '', segundo: (b.referencia || {}).segundo, o_que_copiar: $('bf-copiar').value}};
  }
  function preencheCard(nb) {
    b = nb; var foco = document.activeElement;
    var poe = function (id, v) { var el = $(id); if (el !== foco) el.value = v == null ? '' : v; };
    poe('bf-objetivo', b.objetivo); poe('bf-entrada', b.entrada); poe('bf-roteiro', b.roteiro); poe('bf-peculiaridade', b.peculiaridade);
    poe('bf-proibido', (b.proibido || []).join(', ')); poe('bf-copiar', (b.referencia || {}).o_que_copiar);
    var slug = (b.formato_sugerido || {}).slug || '', sel = $('bf-formato');
    if (sel !== foco) sel.value = sel.querySelector('option[value="' + slug.replace(/"/g, '') + '"]') ? slug : '';
    $('bf-porque').textContent = (b.formato_sugerido || {}).porque || '';
    $('bf-descartavel').checked = !!b.descartavel;
    var pg = b.perguntas_abertas || [];
    $('bf-perguntas-campo').hidden = !pg.length; $('bf-perguntas').innerHTML = pg.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('');
    if (b.cliente && b.cliente !== cliente) trocaClienteDaIA(b.cliente);
    var g = b.gasto_pastas; $('cv-gasto').textContent = g && g.tokens ? 'pastas: ~' + g.tokens + ' tokens' : '';
    mostraRoteiro(); desenhaMaterial(); refsDoFormato(sel.value); opcoesRef();
  }
  function trocaClienteDaIA(nome) {   // a IA anotou o cliente: a barra acompanha, se o nome existe na lista
    var ok = Array.prototype.some.call($('cv-cliente').options, function (o) { return o.value.toLowerCase() === nome.toLowerCase(); });
    if (!ok) return;
    cliente = Array.prototype.filter.call($('cv-cliente').options, function (o) { return o.value.toLowerCase() === nome.toLowerCase(); })[0].value;
    $('cv-cliente').value = cliente; recarregaPastas();
  }
  function mostraRoteiro() { var e = $('bf-entrada').value; $('bf-roteiro-campo').hidden = !(e === 'roteiro' || $('bf-roteiro').value.trim()); }
  function desenhaMaterial() {
    var m = b.material_liberado || [];
    $('bf-material').innerHTML = m.length ? m.map(function (x, i) {
      return '<div class="cv-mat"><img alt="" src="' + esc(arquivoUrl(x.pasta, x.arquivo)) + '" onerror="this.style.visibility=\'hidden\'"><span><b title="' + esc(x.arquivo) + '">' + esc(nomeArq(x.arquivo)) +
        '</b><small>' + esc([x.papel, x.onde].filter(Boolean).join(' · ') || x.pasta) + '</small></span><button type="button" class="btn mini" data-tira="' + i + '" aria-label="Tirar ' + esc(nomeArq(x.arquivo)) + '">×</button></div>';
    }).join('') : '<small class="sub">Nada ainda. Quando a IA mostrar uma imagem, clique em Usar.</small>';
    $('bf-material').querySelectorAll('[data-tira]').forEach(function (bt) {
      bt.addEventListener('click', function () { var x = m[+bt.dataset.tira]; usar(x.pasta, x.arquivo, false); });
    });
    document.querySelectorAll('.cv-mini').forEach(function (el) {
      var u = m.some(function (x) { return mesmo(x, el.dataset.pasta, el.dataset.arquivo); });
      el.classList.toggle('usar', u); if (u) el.classList.remove('nao');
    });
  }
  function usar(pasta, arq, sim) {
    var m = (b.material_liberado || []).filter(function (x) { return !mesmo(x, pasta, arq); });
    if (sim) m.push({pasta: pasta, arquivo: arq, papel: '', onde: ''});
    b.material_liberado = m; desenhaMaterial(); salvar(true);
  }
  var timer = null;
  function salvar(agora) {
    clearTimeout(timer); $('cv-salvo').textContent = '';
    var vai = function () {
      return garantir().then(function () { return api('/conversa/' + bid + '/briefing', lerCard()); })
        .then(function (r) { b = r.briefing; avisos(r.avisos); $('cv-salvo').textContent = 'salvo'; })
        .catch(function (e) { aviso(e.message); });
    };
    if (agora) return vai();
    return new Promise(function (ok) { timer = setTimeout(function () { vai().then(ok); }, 600); });
  }
  document.querySelectorAll('[data-bf]').forEach(function (el) {
    el.addEventListener(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', function () {
      if (el.id === 'bf-descartavel') b.descartavel = el.checked;
      if (el.id === 'bf-formato') refsDoFormato(el.value);
      mostraRoteiro(); salvar(el.tagName === 'SELECT' || el.type === 'checkbox');
    });
  });
  function avisos(l) { $('bf-avisos').innerHTML = (l || []).map(function (a) { return '<p class="aviso" style="margin:0 0 10px">' + esc(a) + '</p>'; }).join(''); }
  function aviso(t) { var el = $('cv-falta'); el.textContent = t; el.hidden = false; setTimeout(function () { if (el.textContent === t) el.hidden = true; }, 6000); }

  // ── chat ──
  function fala(papel, texto) {
    var v = $('cv-vazio'); if (v) v.remove();
    var d = document.createElement('div'); d.className = 'cv-fala ' + papel;
    if (texto) String(texto).split(/\n{2,}/).forEach(function (t) { var p = document.createElement('p'); p.textContent = t; d.appendChild(p); });
    falasEl.appendChild(d); falasEl.scrollTop = falasEl.scrollHeight; return d;
  }
  function linha(texto) { var v = $('cv-vazio'); if (v) v.remove(); var d = document.createElement('p'); d.className = 'cv-aviso'; d.textContent = texto; falasEl.appendChild(d); falasEl.scrollTop = falasEl.scrollHeight; return d; }
  function miniatura(bolha, pasta, arq) {
    var box = bolha.querySelector('.cv-minis');
    if (!box) { box = document.createElement('div'); box.className = 'cv-minis'; bolha.appendChild(box); }
    var el = document.createElement('div'); el.className = 'cv-mini'; el.dataset.pasta = pasta; el.dataset.arquivo = arq;
    el.innerHTML = '<img alt="" loading="lazy" src="' + esc(arquivoUrl(pasta, arq)) + '"><small title="' + esc(pasta + '/' + arq) + '">' + esc(nomeArq(arq)) + '</small>' +
      '<span class="cv-linha"><button type="button" class="btn mini" data-usar>Usar</button><button type="button" class="btn mini" data-nao>Não usar</button></span>';
    el.querySelector('[data-usar]').addEventListener('click', function () { usar(pasta, arq, true); });
    el.querySelector('[data-nao]').addEventListener('click', function () { usar(pasta, arq, false); el.classList.add('nao'); });
    box.appendChild(el);
    if ((b.material_liberado || []).some(function (x) { return mesmo(x, pasta, arq); })) el.classList.add('usar');
    if (ehVideo(arq)) { vistos.unshift({video: arquivoUrl(pasta, arq, true), poster: arquivoUrl(pasta, arq), rel: arq, pasta: pasta, nome: nomeArq(arq)}); opcoesRef(); }
  }
  var NOMES = {listar: 'Olhando a pasta', buscar: 'Procurando nas pastas', ler_texto: 'Lendo', ver_imagem: 'Vendo', anotar_briefing: 'Anotando no briefing'};
  function evento(ev, bolha, st) {
    var p = st.p;
    if (ev.tipo === 'texto') {
      if (!p) { if (!ev.texto.trim()) return; p = st.p = document.createElement('p'); bolha.insertBefore(p, st.status); }
      p.textContent += ev.texto;
    } else if (ev.tipo === 'ferramenta') {
      st.p = null; st.status.textContent = (NOMES[ev.nome] || 'Olhando') + ' ' + [ev.pasta, nomeArq(ev.arquivo)].filter(Boolean).join('/') + '…';
    } else if (ev.tipo === 'miniatura') { st.p = null; miniatura(bolha, ev.pasta, ev.arquivo); bolha.appendChild(st.status); }
    else if (ev.tipo === 'briefing') preencheCard(ev.briefing);
    else if (ev.tipo === 'resumo' || ev.tipo === 'aviso') linha(ev.texto);
    else if (ev.tipo === 'erro') { var n = document.createElement('small'); n.className = 'cv-nota erro'; n.textContent = ev.texto; bolha.appendChild(n); }
    else if (ev.tipo === 'teto') {
      var l = linha(ev.texto + ' '), bt = document.createElement('button'); bt.type = 'button'; bt.className = 'btn mini'; bt.textContent = 'Liberar mais';
      bt.addEventListener('click', function () { api('/conversa/' + bid + '/ajustar', {liberar: 1}).then(function (d) { teto = d.teto_usd; custoTela(); bt.remove(); }).catch(function (e) { aviso(e.message); }); });
      l.appendChild(bt);
    } else if (ev.tipo === 'fim') { custo = ev.custo_total; teto = ev.teto_usd; custoTela(); if (ev.briefing) preencheCard(ev.briefing); }
    falasEl.scrollTop = falasEl.scrollHeight;
  }
  $('cv-texto').addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('cv-form').requestSubmit(); } });
  $('cv-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var t = $('cv-texto').value.trim(); if (!t || enviando) return;
    enviando = true; $('cv-enviar').disabled = true; $('cv-texto').value = '';
    fala('voce', t);
    var bolha = fala('ia', ''), st = {p: null, status: document.createElement('small')};
    bolha.classList.add('pensando'); st.status.className = 'cv-status'; st.status.textContent = 'Pensando…'; bolha.appendChild(st.status);
    garantir().then(function () {
      return fetch('/conversa/' + bid + '/mensagem', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({texto: t})});
    }).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (d) { throw new Error(d.erro || 'A conversa não respondeu.'); });
      var leitor = r.body.getReader(), dec = new TextDecoder(), buf = '';
      function le() {
        return leitor.read().then(function (x) {
          if (x.done) return;
          buf += dec.decode(x.value, {stream: true});
          var partes = buf.split('\n\n'); buf = partes.pop();
          partes.forEach(function (bl) { if (bl.indexOf('data: ') === 0) evento(JSON.parse(bl.slice(6)), bolha, st); });
          return le();
        });
      }
      return le();
    }).catch(function (err) { evento({tipo: 'erro', texto: err.message}, bolha, st); })
      .then(function () {
        enviando = false; $('cv-enviar').disabled = false; bolha.classList.remove('pensando'); st.status.remove();
        if (!bolha.textContent.trim() && !bolha.querySelector('.cv-minis')) bolha.remove();
        $('cv-texto').focus();
      });
  });

  // ── fechar ──
  var insistiu = false;
  $('cv-fechar').addEventListener('click', function () {
    var c = lerCard(), falta = [], bt = this;
    if (!c.objetivo.trim()) falta.push('o objetivo'); if (!c.formato_sugerido.slug && c.entrada !== 'cortar') falta.push('o formato');
    if (!cliente) falta.push('pra quem é'); if (!c.entrada) falta.push('o que você tem');
    if (falta.length && !insistiu) {
      insistiu = true; bt.textContent = 'Seguir mesmo assim';
      aviso('Falta ' + falta.join(', ') + '. Preencha aqui ou escolha no próximo passo.'); return;
    }
    bt.disabled = true; bt.textContent = 'Abrindo o Criar…';
    clearTimeout(timer);
    garantir().then(function () { return api('/conversa/' + bid + '/briefing', lerCard()); })
      .then(function () { return api('/conversa/' + bid + '/fechar', {}); })
      .then(function () { location.href = '/criar-agora?briefing=' + encodeURIComponent(bid); })
      .catch(function (e) { aviso(e.message); bt.disabled = false; bt.textContent = 'Fechar briefing e seguir'; });
  });

  // ── começo: conversa retomada mostra o que já foi dito ──
  modeloTela(); custoTela(); chips();
  if (conv) {
    (conv.falas || []).forEach(function (f) {
      if (f.papel === 'aviso') { linha(f.texto); return; }
      var d = fala(f.papel === 'voce' ? 'voce' : 'ia', f.texto);
      (f.vistos || []).forEach(function (v) { var i = v.indexOf('/'); if (i > 0) miniatura(d, v.slice(0, i), v.slice(i + 1)); });
    });
  }
  preencheCard(b);
})();
