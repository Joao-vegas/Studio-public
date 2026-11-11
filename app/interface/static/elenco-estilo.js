// Página do estilo Explicador 3D: o elenco do estilo em fileira de miniaturas (o mesmo que aparece no Criar), com o link "Editar elenco".
(function () {
  var dados = JSON.parse(document.getElementById('el-estilo-dados').textContent), fila = document.getElementById('el-estilo-fila');
  ElencoPrevia.carregar(dados.previa).then(function (E) {
    var lista = E.itens(dados.elenco), cvs = [];
    fila.innerHTML = '';
    lista.forEach(function (it) {
      var a = document.createElement('a'); a.className = 'el-chip'; a.href = '/elenco';
      a.innerHTML = '<canvas width="150" height="200"></canvas><b>' + (dados.rotulos[it.nome] || it.nome.replace(/_/g, ' ')) + '</b>' +
        (it.mudou ? '<small>' + (it.novo ? 'criado' : 'alterado') + '</small>' : '');
      fila.appendChild(a); cvs.push(a.querySelector('canvas'));
    });
    return E.desenharMiniaturas(lista, cvs);
  }).catch(function (e) { console.warn(e); fila.innerHTML = '<p class="meta">Não consegui montar a prévia 3D neste navegador.</p>'; });
})();
