"""Telas de produção em lote, arquivo e estudo de referências."""
from pathlib import Path
import json
import subprocess
import uuid
from flask import request, render_template, redirect, url_for, flash, abort, jsonify, send_file
from _comum import RAIZ, ESTUDIO, clientes, cliente, modelo, gravar_json, ler_json, VIDEO_EXTS
import producao as P
import ia, fila, regras, lotes, estudo, arquivo, semantica
import formatos as _fmt

STATUS={'novo':'Pronto para analisar','na_fila':'Na fila','analisando':'Analisando','plano':'Aprovar o storyboard',
        'plano_aprovado':'Pronto para produzir','previas':'Gerando prévias','renderizando':'Produzindo vídeo',
        'concluido':'Revisar vídeo','feedback':'Aplicando feedback','aprovado':'Pronto para finalizar',
        'exportado':'Cópia verificada','arquivado':'Arquivado','erro':'Precisa de atenção','interrompido':'Interrompido',
        'rodando':'Em execução','preparando':'Preparando referência','proposta':'Revisar proposta','construindo':'Construindo modelo','pronto':'Pronto para provar'}


def upload(f,extensions=None):
    if not f or not f.filename:raise ValueError('Selecione um arquivo.')
    if extensions and Path(f.filename).suffix.lower() not in extensions:raise ValueError('Formato de arquivo não suportado.')
    p=ESTUDIO/'.uploads'/(uuid.uuid4().hex[:8]+'-'+Path(f.filename).name);p.parent.mkdir(exist_ok=True);f.save(p);return p


def register(app):
    @app.context_processor
    def v2_context():
        return dict(ia_ok=ia.disponivel(),ia_rotulo=ia.rotulo(),ia_cfg=ia.config(),status_labels=STATUS,
                    status_label=lambda s:STATUS.get(s,s),categorias=regras.CATEGORIAS)

    @app.errorhandler(ValueError)
    def invalid(e):
        if request.path.startswith('/api/'):return jsonify(erro=str(e)),400
        flash('✗ '+str(e))
        from urllib.parse import urlparse
        ref=urlparse(request.referrer or '/')
        target=ref.path+('?' + ref.query if ref.query else '')
        return redirect(target if request.method=='POST' and (not ref.netloc or ref.netloc==request.host) else url_for('home'))

    @app.route('/arquivo')
    @app.route('/cliente/<nome>/arquivo')
    def arquivo_lista(nome=None):
        jobs=[j for j in P.listar(nome) if j['status']=='arquivado']
        return render_template('arquivo.html',jobs=jobs,nome=nome)

    @app.post('/job/<cli>/<slug>/finder')
    def abrir_finder(cli,slug):
        j=P.carregar(cli,slug)
        if not j or not j.get('pasta_mac'):abort(404)
        p=Path(j['pasta_mac'])
        if not p.is_dir():raise ValueError('A pasta exportada não está disponível neste Mac.')
        subprocess.run(['open',str(p)],check=True)
        return redirect(url_for('arquivo_lista',nome=cli))

    @app.post('/job/<cli>/<slug>/priorizar')
    def priorizar(cli,slug):
        fila.priorizar(cli,slug);flash('✓ Vídeo movido para o início da fila.')
        return redirect(url_for('job',cli=cli,slug=slug))

    @app.post('/cliente/<nome>/modelo/<mod>/regras/restaurar')
    def regras_restaurar(nome,mod):
        m=modelo(cliente(nome),mod)
        if not m:abort(404)
        if any(j.get('rodando') or j['status']=='na_fila' for j in P.listar(nome) if j['modelo']==mod):raise ValueError('Aguarde as produções deste modelo antes de restaurar as regras.')
        regras.restaurar(m['pasta']/'aprendizado/regras.json');flash('✓ Regras originais restauradas. A versão anterior também ficou salva.')
        return redirect(url_for('modelo',nome=nome,mod=mod)+'#regras')

    @app.post('/config/modelos/atualizar')
    def modelos_atualizar():
        try:flash(f'✓ Catálogo atualizado: {ia.atualizar_catalogo()} modelos. A disponibilidade depende da sua conta e do Codex.')
        except Exception:flash('✗ Não foi possível atualizar o catálogo. Verifique a conexão e a autenticação; o catálogo local continua disponível.')
        return redirect(url_for('config'))

    @app.post('/acervo/reindexar')
    def acervo_reindexar():
        d=semantica.reindexar();flash(f"✓ Índice atualizado: {len(d['itens'])} itens, {d['alterados']} alterações. Motor: {d['motor']}.")
        return redirect(url_for('acervo'))

    @app.route('/lotes')
    def lista_lotes():return render_template('lotes.html',lotes=lotes.listar())

    @app.route('/novo-lote',methods=['GET','POST'])
    def novo_lote():
        if request.method=='POST' and request.form.get('formato'):
            # 2.0: um estilo só pra todos os brutos (arquivos e/ou uma pasta do Mac)
            files,pulados=[],0
            for f in request.files.getlist('brutos'):
                if not f.filename:continue
                try:files.append(upload(f,VIDEO_EXTS))
                except ValueError:pulados+=1
            if pulados:flash('Pulei '+str(pulados)+(' arquivo que não é vídeo.' if pulados==1 else ' arquivos que não são vídeo.'))
            try:
                brutos=list(files)
                if request.form.get('pasta','').strip():brutos+=lotes.brutos_da_pasta(request.form['pasta'])
                if not brutos:raise ValueError('Escolha os vídeos: arraste arquivos ou cole o caminho de uma pasta.')
                lote=lotes.criar_por_estilo(request.form.get('cliente',''),request.form['formato'],brutos,
                                            request.form.get('briefing','').strip(),request.form.get('titulo',''),
                                            analisar=request.form.get('analisar','1')=='1')
                n=len(lote['jobs']);flash('✓ '+str(n)+(' vídeo criado.' if n==1 else ' vídeos criados.'))
                return redirect(url_for('lote_detalhe',slug=lote['slug']))
            except ValueError as e:
                flash('✗ '+str(e));return redirect(url_for('novo_lote',formato=request.form.get('formato','')))
            finally:
                for p in files:p.unlink(missing_ok=True)
        if request.method=='POST':
            files,mats,pulados=[],[],0
            for f in request.files.getlist('brutos'):
                if not f.filename:continue
                try:files.append(upload(f,VIDEO_EXTS))
                except ValueError:pulados+=1
            mats=[upload(f) for f in request.files.getlist('materiais') if f.filename]
            if pulados:flash('Pulei '+str(pulados)+(' arquivo que não é vídeo.' if pulados==1 else ' arquivos que não são vídeo.'))
            try:
                rows=[]
                if request.form.get('modo')=='variacoes':
                    if len(files)!=1:raise ValueError('Para criar variações, envie exatamente um bruto.')
                    rows=[dict(bruto=files[0],modelo=m,titulo=request.form.get('titulo','Variação')+' · '+m,camadas=request.form.getlist('camadas')) for m in request.form.getlist('modelos')]
                else:
                    for i,p in enumerate(files):rows.append(dict(bruto=p,modelo=request.form.get(f'modelo_{i}') or request.form.get('modelo'),
                        titulo=request.form.get(f'titulo_{i}') or p.stem[9:],observacao=request.form.get(f'obs_{i}',''),
                        camadas=list(dict.fromkeys(request.form.getlist('camadas')+request.form.getlist(f'camadas_{i}')))))
                lote=lotes.criar(request.form.get('cliente'),request.form.get('titulo') or 'Novo projeto',request.form.get('briefing',''),rows,mats)
                if request.form.get('analisar')=='1':lotes.acao(lote,'analisar')
                return redirect(url_for('lote_detalhe',slug=lote['slug']))
            finally:
                for p in files+mats:p.unlink(missing_ok=True)
        cls=clientes()
        camadas={c['nome']:[m for m in c['modelos'] if ler_json(c['content']/'modelos'/m/'ficha.json',{}).get('tipo')=='camada'] for c in cls}
        estilos=[f for f in _fmt.listar() if f.get('entrada')=='video' and f.get('modelos') and not lotes.exige_por_video(f)]
        return render_template('novo_lote.html',clientes=[c for c in cls if c['nome']!=_fmt.AVULSO],mapa={c['nome']:c['modelos'] for c in cls},camadas=camadas,
                               estilos=estilos,pre_formato=request.args.get('formato',''))

    @app.route('/aprovar',methods=['GET','POST'])
    def aprovar_varios():
        if request.method=='POST':
            if request.form.get('acao')=='tirar_antigos':   # só esconde da lista os do chat parados há mais de 3 dias; nada é apagado
                n=lotes.tirar_antigos_chat(3)
                flash(f'✓ Tirei {n} vídeo(s) feito(s) pelo chat da lista. Eles seguem em Meus vídeos.' if n else 'Nenhum vídeo do chat com mais de 3 dias na lista.')
                return redirect(url_for('aprovar_varios'))
            ap=[tuple(x.split('/',1)) for x in [request.form.get('apagar_um','')] if '/' in x]
            if not ap and request.form.get('acao')=='apagar':ap=[tuple(x.split('/',1)) for x in request.form.getlist('video') if '/' in x]
            if ap or request.form.get('acao')=='apagar':
                if not ap:flash('Marque ao menos um vídeo.')
                import saidas
                for cli,slug in ap:   # mesmo caminho único de apagar de Meus vídeos (producao.apagar → saidas.apagar_video)
                    try:flash(saidas.mensagem(P.apagar(cli,slug)))
                    except ValueError as e:flash(f'✗ {slug}: {e}')
                return redirect(url_for('aprovar_varios'))
            um=request.form.get('tirar_um','').replace('tirar:','',1)
            if um:
                flash(' · '.join(lotes.tirar_da_lista([tuple(um.split('/',1))])) if '/' in um else 'Vídeo não encontrado.')
                return redirect(url_for('aprovar_varios'))
            itens=[tuple(x.split('/',1)) for x in request.form.getlist('video') if '/' in x]
            if not itens:flash('Marque ao menos um vídeo.');return redirect(url_for('aprovar_varios'))
            if request.form.get('acao')=='tirar':
                flash(' · '.join(lotes.tirar_da_lista(itens)));return redirect(url_for('aprovar_varios'))
            frases={x:request.form.get('frase_'+x,'') for x in request.form.getlist('video')}
            res=lotes.aprovar_varios(itens,frases)
            flash(' · '.join(res))
            return redirect(url_for('aprovar_varios'))
        todos=lotes.esperando()
        import andamento as _and   # faixa "Rodando agora": vídeos ainda em produção (não aparecem em Esperando você)
        rodando=[dict(titulo=d.get('titulo',''),cliente=d['cliente'],slug=d['slug'],etapa=_and.NOMES.get(d.get('etapa'),''),texto=(d.get('atual') or {}).get('texto',''),ha=d.get('ha',''))
                 for d in _and.listar() if d.get('estado')=='trabalhando']
        return render_template('aprovar.html',rodando=rodando,itens=[i for i in todos if i['tipo']=='storyboard'],videos=[i for i in todos if i['tipo']=='video'],outros=[i for i in todos if i['tipo'] not in ('storyboard','video')])

    @app.route('/lote/<slug>',methods=['GET','POST'])
    def lote_detalhe(slug):
        l=lotes.carregar(slug)
        if not l:abort(404)
        if request.method=='POST':
            action=request.form.get('acao')
            if action not in ('analisar','renderizar','finalizar','apagar'):raise ValueError('Ação inválida.')
            results=lotes.acao(l,action)
            flash(' · '.join(results) if results else 'Nenhum vídeo pronto para esta ação.')
            return redirect(url_for('lista_lotes') if action=='apagar' else url_for('lote_detalhe',slug=slug))
        jobs=[j for s in l['jobs'] if (j:=P.carregar(l['cliente'],s))]
        def _estilo(j):
            f=_fmt.carregar(j.get('formato') or '') or _fmt.de_modelo(j.get('modelo',''))
            return f['titulo'] if f else (j.get('modelo') or '')
        return render_template('lote.html',l=l,jobs=jobs,cont=lotes.contagem(l),estilo_de=_estilo)

    @app.route('/referencias')
    def referencias():
        # UMA porta pras referências: as jogadas (referência rápida, já com o estudo quadro a quadro), os estudos antigos e os completos
        import estilo_ref as _er, estudos_tela as _et, frase_estilo as _fe, formatos as _f
        cards=[]
        def _capa(v):
            # a capa escolhida (a mesma de Meus vídeos), não o 1º quadro, que sai preto
            try:
                p=(Path(v) if Path(str(v)).is_absolute() else RAIZ/str(v)).resolve()
                return url_for('thumb_rota',caminho=str(p.relative_to(RAIZ.resolve()))) if p.is_file() else ''
            except (OSError,ValueError,TypeError):
                return ''
        for r in _er.listar():
            st=r.get('estado');fs=(_er.estilo_de(r['id']) if st in ('pronto','confirmado') else {})
            cards.append(dict(tipo='rapida',nome=r['nome_curto'],quando=(r.get('criado_em') or '')[:10],estilo=r.get('formato_nome',''),
                frase=_fe.da_referencia(fs),estado={'analisando':'olhando','pronto':'falta você aprovar','erro':'deu erro','confirmado':'guardada'}.get(st,st),
                cor='ok' if st=='confirmado' else 'erro' if st=='erro' else 'espera',link=url_for('referencia_rapida_ver',id_=r['id']),
                video=url_for('referencia_rapida_video',id_=r['id']) if st!='erro' and _er.video_de(r['id']) else '',
                capa=_capa(_er.video_de(r['id'])) if st!='erro' else ''))
        for e in _et.lista():
            es=e['estado'];dest=(_f.carregar(es.get('juntado_em_estilo') or '') or {}).get('titulo','') if es.get('juntado_em_estilo') else ''
            cards.append(dict(tipo='estudo',nome=e['nome'],quando=e.get('quando','')[:5],estilo=dest,
                frase='Estudado quadro a quadro: ritmo, câmera, som e legenda medidos.' if es.get('pronto') else (es.get('erro') or 'Estudando…'),
                estado='guardada' if es.get('juntado') else 'olhando' if es.get('rodando') else 'deu erro' if es.get('erro') else 'falta você aprovar',
                cor='ok' if es.get('juntado') else 'erro' if es.get('erro') else 'espera',link=url_for('estudar_ver',sid=e['id']),
                video=url_for('arquivo',caminho=e['videos'][0]) if e['videos'] else '',capa=_capa(e['videos'][0]) if e['videos'] else ''))
        for d in estudo.listar():
            ok=d.get('status')=='pronto';er=d.get('status')=='erro'
            cards.append(dict(tipo='completo',nome=d.get('nome_aprovado') or d['titulo'],quando=d['criado_em'][:10],estilo=d.get('modelo') or '',
                frase=estudo.erro_simples(d) if er else 'Estudo completo (o demorado), com proposta de estilo.',
                estado='deu erro' if er else STATUS.get(d.get('status'),d.get('status')),cor='ok' if ok else 'erro' if er else 'espera',
                link=url_for('referencia',slug=d['slug']),video=''))
        return render_template('referencias.html',cards=cards,clientes=clientes())

    @app.route('/nova-referencia',methods=['GET','POST'])
    def nova_referencia():
        if request.method=='POST':
            cli=request.form.get('cliente')
            if request.form.get('novo_cliente','').strip():
                import novo_cliente
                cli=novo_cliente.criar(request.form['novo_cliente'])['nome']
            # Vários vídeos do mesmo estilo (e/ou vários links, um por linha): o Estúdio acha o que se repete.
            videos=[upload(f,VIDEO_EXTS) for f in request.files.getlist('video') if f and f.filename]
            urls=[l.strip() for campo in ('urls','url') for l in request.form.get(campo,'').splitlines() if l.strip()]
            anexos=[upload(f) for f in request.files.getlist('anexos') if f.filename]
            brief=estudo.briefing_com_pontos(
                request.form.get('briefing',''), request.form.getlist('pontos'),
                {k[6:]:v for k,v in request.form.items() if k.startswith('nota__')},
                request.form.get('momentos',''))
            d=estudo.criar(cli,videos,urls,anexos,brief,request.form.get('inicio'),request.form.get('fim'))
            estudo.iniciar(d['slug']);return redirect(url_for('referencia',slug=d['slug']))
        return render_template('nova_referencia.html',clientes=clientes(),pontos=estudo.PONTOS_DE_OBSERVACAO)

    @app.route('/referencia/<slug>',methods=['GET','POST'])
    def referencia(slug):
        d=estudo.carregar(slug)
        if not d:abort(404)
        if request.method=='POST':
            action=request.form.get('acao')
            if action=='construir':estudo.iniciar(slug,'construir',request.form.get('nome'))
            elif action=='refazer':
                d['briefing']+='\n\nRevisão do João: '+request.form.get('observacao','');estudo.salvar(d)
                (RAIZ/d['sandbox']/'BRIEF.md').write_text(d['briefing']);estudo.iniciar(slug)
            else:raise ValueError('Ação inválida.')
            return redirect(url_for('referencia',slug=slug))
        sb=RAIZ/d['sandbox'];md=sb/'ESTUDO.md'
        log=estudo.ESTUDOS/slug/'execucao.log'
        proof=[j for j in P.listar(d['cliente']) if j['modelo']==d.get('modelo')]
        modo='completo' if request.args.get('modo')=='completo' else 'segundos'
        seconds=ler_json(estudo.pasta_evidencias(d)/'segundos-indice.json',{}) or {}
        if not seconds:modo='completo'
        index=seconds if modo=='segundos' else (ler_json(estudo.pasta_evidencias(d)/'frames-indice.json',{}) or {})
        all_sheets=index.get('folhas',[])
        pages=max(1,(len(all_sheets)+5)//6)
        try:page=max(1,min(pages,int(request.args.get('pagina',1))))
        except ValueError:page=1
        return render_template('referencia.html',d=d,p=d.get('proposta') or ler_json(sb/'proposta.json',{}) or {},
                               estudo_md=md.read_text() if md.is_file() else '',log=log.read_text()[-12000:] if log.is_file() else '',provas=proof,
                               folhas_visuais=all_sheets[(page-1)*6:page*6],pagina=page,paginas=pages,modo=modo,tem_segundos=bool(seconds))

    @app.get('/referencia/<slug>/folha/<int:numero>')
    def referencia_folha(slug,numero):
        d=estudo.carregar(slug)
        if not d or numero<1:abort(404)
        tipo='folhas-segundos' if request.args.get('modo')=='segundos' else 'folhas-completas'
        path=estudo.pasta_evidencias(d)/tipo/f'folha-{numero:04}.jpg'
        if not path.is_file():abort(404)
        return send_file(path,mimetype='image/jpeg')
