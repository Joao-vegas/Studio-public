"""Abre a versão atual; reinicia uma instância antiga em vez de abrir sua página."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

ESTUDIO=Path(__file__).resolve().parents[1]
URL='http://localhost:7655'


def versao():
    h=hashlib.sha256()
    for folder in (ESTUDIO/'interface',ESTUDIO/'ferramentas'):
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix in ('.py','.html','.css','.js'):
                h.update(str(p.relative_to(ESTUDIO)).encode());h.update(p.read_bytes())
    return h.hexdigest()[:16]


def health():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=2) as r:return json.load(r)
    except Exception:return None


def main():
    expected=versao();current=health()
    if not current or current.get('build')!=expected:
        service=Path.home()/'Library/LaunchAgents/com.joao.app.plist'
        if service.exists():
            print('Atualizando a instância local do Estúdio…',flush=True)
            subprocess.run(['bash',str(ESTUDIO/'servico/instalar_servico.sh')],check=True)
        else:
            listener=subprocess.run(['lsof','-tiTCP:7655','-sTCP:LISTEN'],capture_output=True,text=True)
            for pid in listener.stdout.split():
                args=subprocess.run(['ps','-p',pid,'-o','command='],capture_output=True,text=True).stdout
                if unicodedata.normalize('NFC',str(ESTUDIO/'interface/servidor.py')) not in unicodedata.normalize('NFC',args) and 'app/interface/servidor.py' not in args:
                    raise SystemExit('A porta 7655 está sendo usada por outro aplicativo. Feche-o e tente novamente.')
                os.kill(int(pid),signal.SIGTERM)
            python=ESTUDIO/'.venv/bin/python'
            logs=ESTUDIO/'servico/logs';logs.mkdir(parents=True,exist_ok=True)
            with (logs/'manual.log').open('a') as f:
                subprocess.Popen([str(python) if python.exists() else sys.executable,str(ESTUDIO/'interface/servidor.py')],
                                 cwd=ESTUDIO.parent,start_new_session=True,stdout=f,stderr=subprocess.STDOUT)
        for _ in range(60):
            current=health()
            if current and current.get('build')==expected:break
            time.sleep(.25)
        else:raise SystemExit('O Estúdio não confirmou a versão nova. Consulte app/servico/logs/err.log.')
    print('Estúdio atualizado em '+URL,flush=True)
    subprocess.run(['open',URL+'/?v='+expected],check=True)

if __name__=='__main__':main()
