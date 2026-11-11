// Prévia 3D do elenco do Explicador 3D, ao vivo no navegador: importa o gente.js e o elenco.js do próprio formato
// (servidos por /arquivo/...), então o personagem que aparece aqui é o mesmo que o motor desenha no vídeo.
// Uso: ElencoPrevia.carregar().then(function (E) { E.vitrine().desenhar(canvas2d, dados); E.vivo(el).mostrar(dados); });
(function () {
  var BASE_PADRAO = '/arquivo/formatos/explicador-3d/base/';
  var TRES = '/arquivo/app/motores/3d/node_modules/three/build/three.module.js';
  var prontos = {};

  // cfg = {base, personagem, elenco} do registro ELENCOS (app/ferramentas/elenco.py); sem cfg, o Explicador 3D
  function carregar(cfg) {
    cfg = cfg || {};
    var BASE = cfg.base || BASE_PADRAO, chave = BASE;
    if (prontos[chave]) return prontos[chave];
    prontos[chave] = (async function () {
      if (!document.querySelector('script[type=importmap]')) {
        var m = document.createElement('script'); m.type = 'importmap';
        m.textContent = JSON.stringify({ imports: { three: TRES } }); document.head.appendChild(m);
      }
      var THREE = await import(TRES);
      var G = await import(BASE + (cfg.personagem || 'gente.js'));
      var E = await import(BASE + (cfg.elenco || 'elenco.js'));
      return api(THREE, G, E);
    })();
    return prontos[chave];
  }

  function api(THREE, G, E) {
    var clone = function (o) { return JSON.parse(JSON.stringify(o)); };

    // {base, ...troca} | "nome" | campos completos → personagem completo (o mesmo resolverElenco do motor)
    function resolver(spec) { return clone(E.resolverElenco({ x: spec }).x); }

    // um palco: renderer transparente + luz + sombra no chão; mostra uma pessoa de cada vez
    function Palco(w, h, canvas) {
      var r = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
      r.setPixelRatio(1); r.setSize(w, h, false); r.setClearColor(0x000000, 0);
      r.toneMapping = THREE.NoToneMapping;   // igual ao motor do vídeo: a cor que você escolhe é a cor que aparece (o ACES lavava tudo)
      var cena = new THREE.Scene(), cam = new THREE.PerspectiveCamera(26, w / h, .1, 60);
      cena.add(new THREE.HemisphereLight(0xfff4e8, 0x5a6078, 1.15));
      var chave = new THREE.DirectionalLight(0xffeedd, 2.1); chave.position.set(2.2, 3.4, 3.2); cena.add(chave);
      var recorte = new THREE.DirectionalLight(0x9db8ff, .9); recorte.position.set(-3, 2.5, -2.5); cena.add(recorte);
      var c = document.createElement('canvas'); c.width = c.height = 128; var g = c.getContext('2d');
      var gr = g.createRadialGradient(64, 64, 4, 64, 64, 62); gr.addColorStop(0, 'rgba(0,0,0,.55)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
      var chao = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
      chao.rotation.x = -Math.PI / 2; chao.position.y = .004; cena.add(chao);
      var atual = null, altura = 1.8, modo = 'tudo';
      // enquadramento: 'tudo' (corpo inteiro), 'busto' (do quadril pra cima, a roupa e o rosto grandes) e 'baixo' (calça e sapato)
      var ENQ = { tudo: [.5, 1.1], busto: [.74, .55], rosto: [.9, .3], pescoco: [.78, .32], baixo: [.27, .58] };
      var alvo = { y: 0, d: 5 }, atualCam = { y: 0, d: 5 };
      function calcAlvo() {
        var e = ENQ[modo] || ENQ.tudo;
        alvo.y = altura * e[0]; alvo.d = (altura * e[1] / 2) / Math.tan(13 * Math.PI / 180);
      }
      function poeCam() { cam.position.set(0, atualCam.y + altura * .02, atualCam.d); cam.lookAt(0, atualCam.y, 0); }
      function enquadrar(m, imediato) {
        modo = ENQ[m] ? m : 'tudo'; calcAlvo();
        if (imediato) { atualCam.y = alvo.y; atualCam.d = alvo.d; poeCam(); }
      }

      function soltar(p) {
        cena.remove(p.raiz);
        p.raiz.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
      }
      function mostrar(d) {
        d = clone(d); d.semente = d.semente || 1;
        var mulher = !!d.mulher || (d.calca && d.calca.tipo === 'saia') || ['coque', 'rabo', 'longo'].indexOf((d.cabelo || {}).estilo) >= 0;
        // o rosto pintado é cacheado pelo _id: o mesmo id enquanto só a roupa muda, outro quando pele, barba ou olhos mudam
        d._id = 'e' + JSON.stringify([d.pele, d.olhos, d.barba, d.bigode, (d.cabelo || {}).cor, d.idade, mulher, d.oculos, d.semente]);
        if (atual) soltar(atual);
        atual = G.criarPessoa(d);
        atual.aplicar({ braco: G.POSES.neutro, rosto: 'feliz', cab: [0, 0, 0] });
        cena.add(atual.raiz);
        altura = atual.altura;
        calcAlvo();
        if (!primeira) { primeira = true; atualCam.y = alvo.y; atualCam.d = alvo.d; }
        poeCam();
      }
      var primeira = false;
      function render(ang, direto) {
        // a câmera desliza até o enquadramento; a vitrine (um frame por pessoa) vai direto
        if (direto) { atualCam.y = alvo.y; atualCam.d = alvo.d; } else { atualCam.y += (alvo.y - atualCam.y) * .18; atualCam.d += (alvo.d - atualCam.d) * .18; }
        poeCam();
        if (atual) atual.raiz.rotation.y = ang || 0; r.render(cena, cam);
      }
      return { r: r, mostrar: mostrar, render: render, enquadrar: enquadrar };
    }

    // vitrine: um palco só, a pessoa vai pra um canvas 2D de cada cartão (poucos contextos WebGL)
    function vitrine(w, h) {
      var p = Palco(w || 300, h || 400);
      return {
        desenhar: function (destino, d, ang) {
          p.mostrar(d); p.render(ang == null ? -.35 : ang, true);
          destino.width = p.r.domElement.width; destino.height = p.r.domElement.height;
          destino.getContext('2d').drawImage(p.r.domElement, 0, 0);
        },
      };
    }

    // vivo: o personagem grande girando devagar (arrastar com o mouse gira na mão)
    function vivo(canvas) {
      var p = Palco(canvas.width, canvas.height, canvas), ang = -.35, arrasta = null, ligado = true, ultimo = 0, gira = true;
      p.enquadrar('busto');
      canvas.addEventListener('pointerdown', function (e) { arrasta = e.clientX; canvas.setPointerCapture(e.pointerId); });
      canvas.addEventListener('pointermove', function (e) { if (arrasta !== null) { ang += (e.clientX - arrasta) * .012; arrasta = e.clientX; } });
      canvas.addEventListener('pointerup', function () { arrasta = null; });
      function laco(t) {
        if (!ligado) return;
        if (gira && arrasta === null && ultimo) ang += (t - ultimo) * .0004;
        ultimo = t; p.render(ang); requestAnimationFrame(laco);
      }
      requestAnimationFrame(laco);
      return {
        mostrar: p.mostrar, parar: function () { ligado = false; },
        enquadrar: function (m, imediato) { p.enquadrar(m, imediato); },
        // teste: congela o giro num ângulo e desenha na hora
        fixar: function (a) { gira = false; ang = a; for (var i = 0; i < 60; i++) p.render(ang); },
      };
    }

    // os cartões do elenco do estilo: os prontos (com o figurino do estilo, se mudou) + os que foram criados. elenco = {nome: {base, ...troca}}
    function itens(elenco) {
      elenco = elenco || {};
      var r = Object.keys(E.ELENCO).map(function (n) { return { nome: n, base: n, spec: elenco[n] || n, mudou: !!elenco[n], novo: false }; });
      Object.keys(elenco).forEach(function (n) { if (!E.ELENCO[n]) r.push({ nome: n, base: elenco[n].base, spec: elenco[n], mudou: true, novo: true }); });
      return r;
    }

    // miniaturas prontas dentro de um canvas por item (a vitrine desenha um por vez, sem estourar contextos WebGL)
    var _vit = null, _feitos = {};
    async function desenharMiniaturas(lista, canvases) {
      _vit = _vit || vitrine(150, 200);
      for (var i = 0; i < lista.length; i++) {
        var cv = canvases[i]; if (!cv) continue;
        var k = JSON.stringify(lista[i].spec) + '|' + lista[i].nome;
        try {
          if (_feitos[k]) cv.getContext('2d').drawImage(_feitos[k], 0, 0);
          else {
            _vit.desenhar(cv, resolver(lista[i].spec));
            var c2 = document.createElement('canvas'); c2.width = cv.width; c2.height = cv.height; c2.getContext('2d').drawImage(cv, 0, 0); _feitos[k] = c2;
          }
        } catch (e) { console.warn(lista[i].nome, e); }
        await new Promise(function (ok) { setTimeout(ok, 0); });
      }
    }

    return { ELENCO: E.ELENCO, resolver: resolver, vitrine: vitrine, vivo: vivo, itens: itens, desenharMiniaturas: desenharMiniaturas };
  }

  window.ElencoPrevia = { carregar: carregar };
})();
