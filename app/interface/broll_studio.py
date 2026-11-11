"""Editor visual de b-rolls, integrado aos trechos do plano."""
from flask import abort, flash, jsonify, redirect, render_template, request, url_for
import producao as prod
import broll_ia as B


def register(app):
    @app.context_processor
    def kie_context():
        return {'kie_configurada': B.configured()}

    @app.get('/brolls-ia')
    def broll_inicio():
        jobs = [j for j in prod.listar() if j['status'] not in ('arquivado', 'exportado')]
        return render_template('broll_inicio.html', jobs=jobs)

    @app.post('/config/kie/verificar')
    def kie_verificar():
        try:
            creditos = B.call('GET', 'https://api.kie.ai/api/v1/chat/credit')
            flash('✓ Kie.ai respondeu: chave válida. Saldo: ' + str(creditos) + ' créditos. Nenhuma geração foi iniciada.')
        except Exception:
            flash('✗ Não foi possível validar a conexão com a Kie.ai. Confira a internet e a chave local; nenhuma geração foi iniciada.')
        return redirect(url_for('config') + '#kie')

    def job(cli, slug, writable=False):
        j = prod.carregar(cli, slug)
        if not j:
            abort(404)
        if writable and (j.get('rodando') or j['status'] in ('na_fila', 'arquivado', 'exportado') or prod.corte_rodando(j)):
            raise ValueError('Aguarde a etapa atual terminar ou abra uma edição ativa.')
        return j

    def catalogo(modelos):
        # Listas (não dicts) para manter a ordem no tojson; o modelo é escolhido na hora de criar.
        return [dict(id=k, nome=m['nome'], nota=m['nota'], precos=[[r, p] for r, p in m['usd'].items()],
                     duracoes=list(m.get('duracoes', ())), desde=min(m['usd'].values()), varia=len(m['usd']) > 1)
                for k, m in modelos.items()]

    def context(j):
        # Imagem: o último modelo usado neste vídeo, senão o sugerido. Animação: o sugerido.
        usados = (r.get('model') for r in B.listing(j) if r.get('tipo') == 'imagem')
        img = next((m for m in usados if m in B.MODELOS_IMAGEM), B.IMAGE_SUGERIDO)
        return dict(j=j, ratios=B.RATIOS, estados=B.STATES, kie_ok=B.configured(), preco_em=B.PRICE_DATE,
                    mod_img=catalogo(B.MODELOS_IMAGEM), mod_vid=catalogo(B.MODELOS_VIDEO),
                    img_padrao=img, vid_padrao=B.VIDEO_SUGERIDO,
                    nomes={k: m['nome'] for d in (B.MODELOS_IMAGEM, B.MODELOS_VIDEO) for k, m in d.items()})

    @app.route('/job/<cli>/<slug>/brolls', methods=['GET', 'POST'])
    def broll_studio(cli, slug):
        j = job(cli, slug, request.method == 'POST')
        if request.method == 'POST':
            r = B.draft(j, request.form)
            return redirect(url_for('broll_detail', cli=cli, slug=slug, ident=r['id']))
        plan = prod.plano(j) or {}
        beats = plan.get('beats', [])
        chosen = next((b for b in beats if b['id'] == request.args.get('beat')), beats[0] if beats else None)
        return render_template('broll_studio.html', **context(j), beats=beats, escolhido=chosen, itens=B.listing(j))

    @app.get('/job/<cli>/<slug>/brolls/<ident>')
    def broll_detail(cli, slug, ident):
        j = job(cli, slug)
        r = B.load(j, ident)
        parent = B.load(j, r['origem']) if r.get('origem') else None
        return render_template('broll_detail.html', **context(j), r=r, parent=parent)

    @app.post('/job/<cli>/<slug>/brolls/<ident>/confirmar')
    def broll_confirm(cli, slug, ident):
        j = job(cli, slug, True)
        if request.form.get('aprovar') != '1':
            raise ValueError('Revise e aprove o custo desta geração.')
        B.confirm(j, ident, request.form.get('nonce', ''))
        return redirect(url_for('broll_detail', cli=cli, slug=slug, ident=ident))

    @app.get('/job/<cli>/<slug>/brolls/<ident>/status')
    def broll_status(cli, slug, ident):
        j = job(cli, slug)
        try:
            r = B.refresh(j, ident)
            return jsonify(status=r['status'], label=B.STATES[r['status']], pronto=r['status'] == 'pronto')
        except Exception:
            return jsonify(erro='Consulta indisponível. A tarefa não foi reenviada; tente consultar novamente.'), 503

    @app.post('/job/<cli>/<slug>/brolls/<ident>/usar')
    def broll_use(cli, slug, ident):
        j = job(cli, slug, True)
        r = B.use(j, ident)
        flash('B-roll selecionado no trecho. Revise o plano antes de renderizar.')
        return redirect(url_for('job', cli=cli, slug=slug) + '#' + r['beat'])

    @app.post('/job/<cli>/<slug>/brolls/<ident>/texto')
    def broll_overlay(cli, slug, ident):
        j = job(cli, slug, True)
        r = B.overlay(j, ident, request.form.get('texto', ''), request.form.get('posicao', 'top'))
        return redirect(url_for('broll_detail', cli=cli, slug=slug, ident=r['id']))

    @app.post('/job/<cli>/<slug>/brolls/<ident>/retomar')
    def broll_recover(cli, slug, ident):
        j = job(cli, slug, True)
        B.recover(j, ident, request.form.get('task_id', '').strip())
        flash('Tarefa vinculada. Vamos consultar o resultado existente, sem gerar novamente.')
        return redirect(url_for('broll_detail', cli=cli, slug=slug, ident=ident))
