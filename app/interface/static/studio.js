// Atualizações de status não descartam escolhas nem deslocam a edição para o topo.
(() => {
  let dirty = false;
  const storageKey = 'studio-view:' + location.pathname;
  const snapshot = () => {
    if (!location.pathname.startsWith('/job/')) return;
    try { sessionStorage.setItem(storageKey, JSON.stringify({ y: scrollY,
      details: [...document.querySelectorAll('details')].map(d => d.open),
      media: [...document.querySelectorAll('video,audio')].map(v => ({src:v.getAttribute('src'),time:v.currentTime})) })); } catch (_) {}
  };
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    sessionStorage.removeItem(storageKey);
    if(saved) {
      document.querySelectorAll('details').forEach((d,i) => {if(saved.details[i] !== undefined)d.open=saved.details[i]});
      document.querySelectorAll('video,audio').forEach(v => {
        const m=saved.media.find(m=>m.src===v.getAttribute('src'));
        if(m) { const restore=()=>{v.currentTime=m.time}; if(v.readyState)restore();else v.addEventListener('loadedmetadata',restore,{once:true}); }
      });
      if(!location.hash) requestAnimationFrame(()=>scrollTo({top:saved.y,behavior:'instant'}));
    }
  } catch (_) {}
  document.addEventListener('input', e => {if(e.target.closest('form'))dirty=true});
  document.addEventListener('change', e => {if(e.target.closest('form'))dirty=true});
  document.addEventListener('submit', e => {if(!e.defaultPrevented){snapshot();dirty=false}});
  window.addEventListener('beforeunload', e => {if(dirty){e.preventDefault();e.returnValue=''}});
  window.studioReload = () => {
    if(document.hidden || document.querySelector('dialog[open]') || [...document.querySelectorAll('video,audio')].some(v=>!v.paused))return false;
    if(dirty || document.querySelector('form :focus')) {
      if(!document.querySelector('.refresh-notice')) {
        const note=document.createElement('div');note.className='aviso refresh-notice';note.setAttribute('role','status');
        note.textContent='Há atualizações. Salve suas escolhas antes de atualizar a página.';document.body.append(note);
      }
      return false;
    }
    snapshot();location.reload();return true;
  };
})();

(() => {
  const theme = document.getElementById('theme-toggle');
  theme?.addEventListener('click', () => {const v=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=v;try{localStorage.setItem('estudio-theme',v)}catch(e){}});
  // menu lateral recolhível (☰): aberto <-> fino (só ícones, nome no hover); lembra a escolha (uma por grupo: telas comuns e telas de trabalho)
  const navBtn = document.getElementById('nav-toggle'), root = document.documentElement;
  const navMarca = () => { const fino = root.dataset.nav === 'fino'; navBtn?.setAttribute('aria-expanded', String(!fino)); navBtn?.setAttribute('aria-label', fino ? 'Abrir o menu' : 'Recolher o menu'); };
  navMarca();
  navBtn?.addEventListener('click', () => { root.dataset.nav = root.dataset.nav === 'fino' ? 'aberto' : 'fino'; navMarca(); try { localStorage.setItem(root.dataset.foco ? 'estudio-nav-foco' : 'estudio-nav', root.dataset.nav); } catch (e) {} });
  document.querySelectorAll('[data-filter]').forEach(input => input.addEventListener('input', () => {
    const q=input.value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();let count=0;
    document.querySelectorAll(input.dataset.filter).forEach(el=>{el.hidden=!(el.dataset.search||el.textContent).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(q);if(!el.hidden)count++});
    document.querySelectorAll('.empty-filter').forEach(x=>x.hidden=!!count);
  }));
  document.querySelectorAll('[data-model]').forEach(b=>b.addEventListener('click',()=>{document.getElementById('gpt-model').value=b.dataset.model;document.querySelector('[name=provedor][value=openai]').checked=true;document.getElementById('gpt-model').focus()}));
  document.querySelectorAll('form[data-confirm]').forEach(f=>f.addEventListener('submit',e=>{if(!confirm(f.dataset.confirm))e.preventDefault()}));
  // ─── Apagar com prévia: um PAINEL só pra todo Apagar do Estúdio (lista o que vai pra Lixeira do Mac, com miniatura, tamanho,
  // o que é e "Mostrar no Finder"). Uso: <form method=post action=... data-apagar-previa="/espaco/previa?arquivo=<caminho>&explica=<texto>">
  // (ou data-apagar="video=cliente%2Fslug" / "corte=slug"); o painel abre no submit e só envia o form depois do "Mandar pra Lixeira".
  // Em JS: EstudioApagar.abrir({url | corpo, titulo, soVer}) → Promise<boolean>. Servidor: espaco.previa (templates/_apagar_ui.html).
  const apEsc = t => String(t == null ? '' : t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const apUrl = c => '/espaco/arquivo?c=' + encodeURIComponent(c);
  const apMidia = it => {
    if (it.kind === 'video') return '<video class="pa-midia" src="' + apUrl(it.caminho) + '#t=0.1" controls preload="metadata" playsinline></video>';
    if (it.kind === 'imagem') return '<img class="pa-midia" loading="lazy" src="' + apUrl(it.caminho) + '" alt="">';
    if (it.kind === 'audio') return '<div class="pa-midia pa-audio"><audio controls preload="none" src="' + apUrl(it.caminho) + '"></audio></div>';
    if (it.kind === 'pasta' && it.dentro && it.dentro.length) return apMidia(it.dentro[0]);
    return '<div class="pa-midia pa-sem" aria-hidden="true">' + (it.kind === 'pasta' ? 'pasta' : 'arquivo') + '</div>';
  };
  const apItem = it => '<li class="pa-item"><div class="pa-thumb">' + apMidia(it) + '</div><div class="pa-info">'
    + '<p class="pa-nome"><b>' + apEsc(it.rotulo) + '</b> <span class="pa-tam">' + apEsc(it.tamanho) + '</span></p>'
    + (it.explica ? '<p class="pa-explica">' + apEsc(it.explica) + '</p>' : '') + (it.aviso ? '<p class="pa-aviso">' + apEsc(it.aviso) + '</p>' : '')
    + '<p class="pa-arq">' + apEsc(it.nome) + (it.kind === 'pasta' ? ' · ' + it.n_arquivos + ' arquivo' + (it.n_arquivos === 1 ? '' : 's') : '') + '</p>'
    + (it.dentro && it.dentro.length > 1 ? '<details class="pa-dentro"><summary>Ver dentro (' + it.dentro.length + ')</summary><div class="pa-dentro-grade">'
        + it.dentro.map(d => '<div class="pa-mini">' + apMidia(d) + '<small>' + apEsc(d.tamanho) + '</small></div>').join('') + '</div></details>' : '')
    + '<button type="button" class="btn mini" data-ap-finder="' + apEsc(it.caminho) + '">Mostrar no Finder</button></div></li>';
  const apFinder = async caminhos => {
    const p = new URLSearchParams(); [].concat(caminhos).forEach(c => p.append('caminho', c));
    try { const r = await (await fetch('/espaco/finder', {method: 'POST', body: p})).json(); if (!r.ok) alert(r.erro || 'Não consegui abrir o Finder.'); }
    catch (_) { alert('Não consegui abrir o Finder.'); }
  };
  let apDlg = null;
  const apCria = () => {
    if (apDlg) return apDlg;
    apDlg = document.createElement('dialog'); apDlg.className = 'pa-painel'; apDlg.setAttribute('aria-labelledby', 'ap-titulo');
    apDlg.innerHTML = '<div class="pa-corpo"><h2 id="ap-titulo"></h2><p class="pa-sub meta"></p><div class="pa-lista"></div>'
      + '<div class="pa-acoes"><button type="button" class="btn" data-ap="cancelar">Cancelar</button><button type="button" class="btn perigo" data-ap="ok">Mandar pra Lixeira</button></div></div>';
    document.body.append(apDlg);
    apDlg.addEventListener('click', e => { const f = e.target.closest('[data-ap-finder]'); if (f) { apFinder(f.dataset.apFinder); return; } if (e.target === apDlg) apDlg.close(); });
    apDlg.addEventListener('close', () => apDlg.querySelectorAll('video,audio').forEach(m => { m.pause(); m.removeAttribute('src'); m.load(); }));
    return apDlg;
  };
  const apAbrir = async ({url, corpo, titulo, soVer, botao}) => {
    let r;
    try {
      r = await (await (corpo ? fetch(url || '/espaco/previa', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)}) : fetch(url))).json();
    } catch (_) { alert('Não consegui montar a lista do que vai pra Lixeira. Tente de novo.'); return false; }
    if (!r.ok) { alert(r.erro || 'Não achei nada pra mostrar.'); return false; }
    const d = apCria();
    d.querySelector('h2').textContent = soVer ? (titulo || 'O que tem aqui') : 'Vai pra Lixeira do Mac: ' + r.n + (r.n === 1 ? ' item' : ' itens') + ', ' + r.texto;
    d.querySelector('.pa-sub').textContent = soVer ? 'Só pra você ver. Nada sai daqui.' : (titulo ? titulo + '. ' : '') + 'Confira antes de mandar. Dá pra recuperar pelo Finder; o espaço só volta quando você esvaziar a Lixeira.';
    d.querySelector('.pa-lista').innerHTML = r.grupos.map(g => '<section class="pa-grupo">' + (g.titulo ? '<h3>' + apEsc(g.titulo) + '</h3>' : '')
      + (g.avisos || []).map(a => '<p class="pa-aviso">' + apEsc(a) + '</p>').join('')
      + '<ul>' + g.itens.map(apItem).join('') + '</ul></section>').join('')
      + (r.recusados && r.recusados.length ? '<p class="pa-aviso">Ficam de fora: ' + r.recusados.map(x => apEsc(x.nome + ' (' + x.motivo + ')')).join('; ') + '</p>' : '');
    const ok = d.querySelector('[data-ap=ok]'), cancela = d.querySelector('[data-ap=cancelar]');
    ok.hidden = !!soVer; ok.textContent = botao || 'Mandar pra Lixeira'; cancela.textContent = soVer ? 'Fechar' : 'Cancelar';
    return new Promise(res => {
      let feito = false;
      const fim = v => { if (feito) return; feito = true; ok.onclick = cancela.onclick = null; d.removeEventListener('close', aoFechar); if (d.open) d.close(); res(v); };
      const aoFechar = () => fim(false);
      ok.onclick = () => fim(true); cancela.onclick = () => fim(false); d.addEventListener('close', aoFechar);
      d.showModal(); cancela.focus();
    });
  };
  window.EstudioApagar = {abrir: apAbrir, finder: apFinder};
  document.addEventListener('click', e => { const b = e.target.closest('[data-ap-finder]:not(dialog *)'); if (b) { e.preventDefault(); apFinder(b.dataset.apFinder.split('|')); } });
  document.addEventListener('click', e => { const b = e.target.closest('[data-ap-ver]'); if (b) { e.preventDefault(); try { apAbrir({corpo: {grupos: [JSON.parse(b.dataset.apVer)]}, soVer: true, titulo: b.dataset.apTitulo}); } catch (_) {} } });
  document.querySelectorAll('form[data-apagar],form[data-apagar-previa]').forEach(f => f.addEventListener('submit', async e => {
    if (f.dataset.pronto) return; e.preventDefault();
    const url = f.dataset.apagarPrevia || '/espaco/previa?' + f.dataset.apagar;
    if (await apAbrir({url, titulo: f.dataset.titulo})) { f.dataset.pronto = '1'; e.submitter ? f.requestSubmit(e.submitter) : f.submit(); }
  }));
  document.querySelectorAll('form[data-apagar-lote]').forEach(f => f.addEventListener('submit', async e => {   // ⋯ Apagar e Apagar marcados das grades de vídeo
    const sub = e.submitter; if (f.dataset.pronto || (f.dataset.apagarLote === 'botao' && !(sub && sub.hasAttribute('data-apaga')))) return; e.preventDefault();
    const p = new URLSearchParams(), fd = new FormData(f);
    if (sub && sub.name) fd.append(sub.name, sub.value);
    for (const [k, v] of fd) { if (k === 'video' || k === 'caminho' || k === 'rascunho' || k === 'musica') p.append(k, v); else if (k === 'apagar_um') p.append('video', v); }
    const n = ['video', 'caminho', 'rascunho', 'musica'].reduce((t, k) => t + p.getAll(k).length, 0), soMusica = p.getAll('musica').length === n;
    if (!n) { alert('Marque pelo menos ' + (soMusica ? 'uma música.' : 'um vídeo.')); return; }
    if (await apAbrir({url: '/espaco/previa?' + p, titulo: n === 1 ? '“' + ((sub && sub.dataset.titulo) || (soMusica ? 'esta música' : 'este vídeo')) + '”' : n + (soMusica ? ' músicas' : ' itens')})) { f.dataset.pronto = '1'; sub ? f.requestSubmit(sub) : f.submit(); }
  }));
  document.querySelectorAll('[data-marcar-todos]').forEach(b=>b.addEventListener('click',()=>{const cx=Array.from(document.querySelectorAll('input[form=apagar-lote][type=checkbox]'));const marcar=cx.some(c=>!c.checked);cx.forEach(c=>c.checked=marcar);b.textContent=marcar?'Desmarcar todos':'Marcar todos'}));
  document.querySelectorAll('.drop').forEach(drop=>{
    const input=drop.querySelector('input[type=file]');if(!input)return;
    ['dragenter','dragover'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.add('ativo')}));
    ['dragleave','drop'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.remove('ativo')}));
    drop.addEventListener('drop',e=>{const dt=new DataTransfer();Array.from(e.dataTransfer.files).slice(0,input.multiple?undefined:1).forEach(f=>dt.items.add(f));input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}))});
    input.addEventListener('change',()=>{let status=drop.querySelector('.file-status');if(!status){status=document.createElement('small');status.className='file-status';status.setAttribute('aria-live','polite');drop.append(status)}status.textContent=Array.from(input.files).map(f=>f.name+' · '+(f.size/1024/1024).toFixed(1)+' MB').join(' / ')});
  });
  document.addEventListener('keydown',e=>{if(e.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){const q=document.querySelector('.quick-search,input[type=search]');if(q){e.preventDefault();q.focus()}}});
  document.querySelectorAll('form').forEach(f=>f.addEventListener('submit',e=>{if(e.defaultPrevented)return;const button=e.submitter;if(button){setTimeout(()=>{button.disabled=true;button.dataset.original=button.textContent;button.textContent='Aguarde…';
    // nunca fica preso: se a resposta demora (servidor ocupado) o botão volta em 20 s; voltar pelo histórico também o restaura
    setTimeout(()=>{if(button.dataset.original!==undefined){button.disabled=false;button.textContent=button.dataset.original;delete button.dataset.original}},20000)},0)}}));
  window.addEventListener('pageshow',e=>{if(e.persisted)document.querySelectorAll('button[data-original]').forEach(b=>{b.disabled=false;b.textContent=b.dataset.original;delete b.dataset.original})});
  if(document.querySelector('[data-poll]')) {
    const poll = () => { if (!document.hidden) window.studioReload(); setTimeout(poll, 5000); };
    setTimeout(poll, 5000);
  }
})();

// Troca o momento desenhado, mantendo as proporções e a legenda de cada cena.
document.querySelectorAll('[data-blueprint]').forEach(root=>{
  root.querySelectorAll('[data-blueprint-select]').forEach(button=>button.addEventListener('click',()=>{
    root.querySelectorAll('[data-blueprint-select]').forEach(x=>x.setAttribute('aria-pressed',String(x===button)));
    root.querySelectorAll('[data-blueprint-state]').forEach(x=>x.hidden=x.dataset.blueprintState!==button.dataset.blueprintSelect);
  }));
});

// Roteiro fiel à seleção: nunca completa frases nem introduz palavras.
document.querySelectorAll('input[data-fala]').forEach(input=>input.addEventListener('change',()=>{
  const section=input.closest('section'),text=section?.querySelector('.roteiro-texto');
  input.closest('.corte-seg')?.classList.toggle('fora',!input.checked);
  if(text) text.textContent=Array.from(section.querySelectorAll('input[data-fala]:checked')).map(x=>x.dataset.fala).join(' ')||'Marque os trechos que devem ficar.';
}));

// Enquadramento visual, sem chamadas à API.
const ratioForm=document.getElementById('broll-draft');
ratioForm?.addEventListener('change',()=>{
  document.getElementById('scene-frame').style.setProperty('--ratio',ratioForm.elements.ratio.value.replace(':','/'));
  const selected=document.getElementById('scene-beat').selectedOptions[0];
  document.getElementById('scene-fala').textContent=selected?.dataset.fala||'';
});
// Consultar uma tarefa existente nunca gera uma segunda tarefa.
const generation=document.querySelector('[data-generation-status]');
if(generation) {
  let fetching=false, timer;
  const check=async()=>{
    clearTimeout(timer);
    if(fetching)return;
    if(document.hidden){timer=setTimeout(check,6000);return}
    fetching=true;
    try {
      const response=await fetch(generation.dataset.generationStatus);
      const state=await response.json();
      generation.textContent=state.erro||state.label;
      if(['pronto','falhou','incerto'].includes(state.status)){window.studioReload();return}
    } catch(_) {generation.textContent='Não foi possível consultar agora. Nenhuma nova geração foi iniciada.'}
    finally {fetching=false}
    timer=setTimeout(check,6000);
  };
  document.querySelector('[data-generation-refresh]')?.addEventListener('click',check);
  timer=setTimeout(check,2000);
}
// Uma opção desligada não envia quantidade/fonte escondidas.
document.querySelectorAll('[data-broll-settings]').forEach(root=>{
  const toggle=root.querySelector('[data-broll-toggle]');
  const update=()=>{root.querySelectorAll('.broll-options input,.broll-options select').forEach(input=>input.disabled=!toggle.checked);toggle.setAttribute('aria-expanded',String(toggle.checked))};
  toggle.addEventListener('change',update);update();
});
// A linha do processo acompanha evidências reais sem recriar a página.
window.studioUpdatePipeline = steps => (steps||[]).forEach(step=>{
  const element=[...document.querySelectorAll('[data-process-step]')].find(el=>el.dataset.processStep===step.id);
  if(!element)return;
  element.className='process-step state-'+step.estado;
  element.querySelector('.process-state').textContent=({pronto:'Pronto',rodando:'Em andamento',revisar:'Sua aprovação',aguardando:'Próxima etapa',atencao:'Precisa de atenção'})[step.estado];
  element.querySelector('p').textContent=step.detalhe;
});

// menu lateral: com a lista longa, abre já rolado até o item da página atual
(function () {
  var nav = document.querySelector('.s-nav'), a = nav && nav.querySelector('.s-item.ativo');
  if (!a) return;
  var r = a.getBoundingClientRect(), n = nav.getBoundingClientRect(), rodape = nav.querySelector('.s-rodape'), limite = n.bottom - (rodape ? rodape.offsetHeight : 0) - 12;
  if (r.bottom > limite) nav.scrollTop += r.bottom - limite;
})();
