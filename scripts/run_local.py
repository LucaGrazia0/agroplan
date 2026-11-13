"""Run the complete app locally; the first account is created by its owner."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8091)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:
        parser.error('La porta deve essere tra 1024 e 65535.')
    base=f'http://localhost:{args.port}'
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',args.port))
    except OSError:
        try:
            with urllib.request.urlopen(base+'/health',timeout=3) as response:
                status=json.load(response)
            if status.get('service')!='agroplan' or not status.get('web_available'):
                raise ValueError()
        except Exception:
            parser.error(f'La porta {args.port} è occupata. Chiudi il vecchio server o scegli --port.')
        print(f'AgroPlan è già avviato: {base}',flush=True)
        if not args.no_browser:
            link=ROOT/'.local/setup-link.txt'
            webbrowser.open(link.read_text().strip() if link.exists() else base)
        return
    from storage import initialize,connect
    initialize()
    with connect() as db:
        first=db.execute('SELECT 1 FROM auth_users LIMIT 1').fetchone() is None
    url=base
    if first:
        os.environ['AGROPLAN_SETUP_TOKEN']=secrets.token_urlsafe(32)
        url=base+'/#/setup?setup_token='+os.environ['AGROPLAN_SETUP_TOKEN']
        link=ROOT/'.local/setup-link.txt'
        link.parent.mkdir(parents=True,exist_ok=True)
        # Owner-only file; the token is never printed or stored in tracked files.
        fd=os.open(link,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as out:
            out.write(url+'\n')
        link.chmod(0o600)
    print(f'AgroPlan: {base}',flush=True)
    if first:
        print('Primo accesso: apri il collegamento riservato in .local/setup-link.txt e scegli la tua password.',flush=True)
    import main as backend
    import uvicorn
    if not args.no_browser:
        # Opening is deferred until the server is reachable.
        import threading,time
        def open_when_ready():
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base+'/health',timeout=1):
                        webbrowser.open(url)
                    return
                except Exception:
                    time.sleep(.2)
        threading.Thread(target=open_when_ready,daemon=True).start()
    uvicorn.run(backend.app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__':
    main()
