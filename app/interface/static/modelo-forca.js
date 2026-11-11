// Modelo + esforço (macro _modelo_forca.html): cartões do modelo + deslizante de esforço que brilha mais pra frente.
// Escreve nos dois <input hidden> (os nomes que o POST já lê) e avisa a tela com o evento "mf:mudou" (detail: modelo, esforco, nomeModelo, nomePt, nomeEn, gpt).
(function () {
  function init(box) {
    var D = JSON.parse(box.dataset.dados), $ = function (s) { return box.querySelector(s); };
    var hm = $('[data-mf-modelo]'), he = $('[data-mf-esforco]'), lista = $('.mf-modelos'), r = $('.mf-r'), esc = $('.mf-escala');
    var niveis = {}; D.niveis.forEach(function (n) { niveis[n.v] = n; });
    var estado = { modelo: hm.value || D.padrao.modelo, esforco: he.value || D.padrao.esforco };
    function m() { return D.modelos.filter(function (x) { return x.v === estado.modelo; })[0] || D.modelos[0]; }
    function barras(x) { var n = x.marca === 'gpt' ? 0 : ({ opus: 3, sonnet: 2, haiku: 1 }[x.v] || 2);
      return x.marca === 'gpt' ? '<span class="mf-ico mf-gpt-ico">G</span>' : '<span class="mf-ico mf-barras" data-n="' + n + '"><i></i><i></i><i></i></span>'; }
    function desenhaModelos() {
      lista.innerHTML = ''; lista.style.setProperty('--n', D.modelos.length);
      D.modelos.forEach(function (x) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'mf-modelo'; b.dataset.v = x.v;
        b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', x.v === estado.modelo);
        b.innerHTML = barras(x) + '<span class="mf-m-txt"><b>' + x.nome + '</b><small>' + x.serve + '</small></span>' + (x.custo ? '<em class="mf-custo mf-c-' + x.custo.replace('é', 'e') + '">' + x.custo + '</em>' : '');
        b.onclick = function () { estado.modelo = x.v; ajusta(); emite(); };
        lista.appendChild(b);
      });
    }
    function ajusta() {   // os níveis válidos do modelo escolhido; se o atual não existe nele, vai pro mais perto
      var x = m(), n = x.esforcos;
      if (n.indexOf(estado.esforco) < 0) estado.esforco = n.indexOf('high') >= 0 ? 'high' : n[n.length - 1];
      [].forEach.call(lista.children, function (b) { var on = b.dataset.v === x.v; b.classList.toggle('ativo', on); b.setAttribute('aria-checked', on); });
      r.max = n.length - 1; r.value = n.indexOf(estado.esforco);
      esc.innerHTML = '';
      n.forEach(function (v, i) {
        var s = document.createElement('button'); s.type = 'button'; s.className = 'mf-marca'; s.dataset.i = i;
        s.style.left = 'calc(14px + (100% - 28px) * ' + (n.length > 1 ? i / (n.length - 1) : 0) + ')';
        s.innerHTML = '<i>' + v + '</i><u>' + niveis[v].pt + '</u>';
        s.onclick = function () { r.value = i; sobe(); };
        esc.appendChild(s);
      });
      pinta();
    }
    function pinta() {
      var x = m(), n = x.esforcos, i = n.indexOf(estado.esforco), f = n.length > 1 ? i / (n.length - 1) : 1;
      var f2 = box.querySelector('.mf-forca'); f2.style.setProperty('--f', f.toFixed(2)); f2.style.setProperty('--p', Math.round(f * 100));
      $('.mf-nome').textContent = niveis[estado.esforco].pt; $('.mf-det').textContent = estado.esforco + ' · ' + x.nome.replace(/^Claude /, '');
      $('.mf-desc').textContent = niveis[estado.esforco].desc; r.setAttribute('aria-valuetext', niveis[estado.esforco].pt + ' (' + estado.esforco + ')');
      [].forEach.call(esc.children, function (s, k) { s.classList.toggle('ativo', k === i); });
      hm.value = estado.modelo; he.value = estado.esforco; $('.mf-gpt').hidden = x.marca !== 'gpt';
    }
    function emite() { var x = m(); pinta();
      box.dispatchEvent(new CustomEvent('mf:mudou', { bubbles: true, detail: { modelo: estado.modelo, esforco: estado.esforco, nomeModelo: x.nome, nomePt: niveis[estado.esforco].pt, nomeEn: estado.esforco, gpt: x.marca === 'gpt' } })); }
    function sobe() { estado.esforco = m().esforcos[+r.value]; emite(); }
    r.oninput = sobe;
    desenhaModelos(); ajusta(); emite();
  }
  [].forEach.call(document.querySelectorAll('[data-mf]'), init);
})();
