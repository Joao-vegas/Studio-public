// Criar (/criar-agora): quando o estilo é o Explicador 3D aparece a fileira "Personagem" com o elenco DO ESTILO (os prontos, já com
// o figurino que o João salvou na tela Elenco, + os que ele criou). Um clique escolhe e vai no POST como "personagem" (o prompt da
// produção cita o nome e o elenco.json do estilo).
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var dados = JSON.parse($('nv-elencos').textContent), E = null, montado = false;

  function chip(it, valor, rotulo) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'el-chip' + ($('nv-personagem').value === valor ? ' ativo' : '');
    b.dataset.valor = valor;
    b.innerHTML = (it ? '<canvas width="150" height="200"></canvas>' : '<span class="el-ia">IA</span>') + '<b>' + rotulo + '</b>' + (it && it.mudou ? '<small>' + (it.novo ? 'criado' : 'figurino seu') + '</small>' : '');
    b.onclick = function () {
      $('nv-personagem').value = valor;
      [].forEach.call($('nv-pers-fila').children, function (c) { c.classList.toggle('ativo', c === b); });
    };
    return b;
  }

  function montar() {
    var fila = $('nv-pers-fila'), r = dados.rotulos;
    fila.innerHTML = '';
    fila.appendChild(chip(null, '', 'A IA escolhe'));
    var lista = E.itens(dados.elenco), cvs = [];
    lista.forEach(function (it) { var c = chip(it, it.nome, r[it.nome] || it.nome.replace(/_/g, ' ')); fila.appendChild(c); cvs.push(c.querySelector('canvas')); });
    if (!$('nv-personagem').value) fila.firstChild.classList.add('ativo');
    return E.desenharMiniaturas(lista, cvs);
  }

  function sincronizar() {
    var ligado = $('nv-formato').value === 'explicador-3d';
    $('nv-pers').hidden = !ligado;
    if (!ligado) { $('nv-personagem').value = ''; return; }
    if (montado) return;
    montado = true;
    ElencoPrevia.carregar(dados.previa).then(function (m) { E = m; return montar(); })
      .catch(function (e) { montado = false; console.warn(e); $('nv-pers-fila').innerHTML = '<p class="meta">Não consegui montar a prévia 3D. Escolha o personagem na tela Elenco.</p>'; });
  }

  document.addEventListener('click', function () { setTimeout(sincronizar, 0); });
})();
