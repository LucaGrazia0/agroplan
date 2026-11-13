"""Exercise every main HTTP flow against real providers and a disposable DB."""
import argparse
from datetime import date,timedelta
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def run():
    import httpx
    with tempfile.TemporaryDirectory(prefix='agroplan-live-') as temp:
        directory=Path(temp)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        token=secrets.token_urlsafe(32)
        password=secrets.token_urlsafe(24)
        env={**os.environ,'AGROPLAN_DB_PATH':str(directory/'smoke.sqlite'),
             'AGROPLAN_SETUP_TOKEN':token,'AGROPLAN_LOCAL_MODE':'0'}
        with (directory/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--app-dir',str(ROOT/'backend'),
                '--host','127.0.0.1','--port',str(port),'--log-level','warning'],cwd=ROOT,env=env,stdout=log,stderr=log)
            checks=[]
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=240) as client:
                    for _ in range(100):
                        try:
                            if client.get('/health',timeout=1).status_code==200: break
                        except httpx.HTTPError: pass
                        if server.poll() is not None: raise RuntimeError('Avvio backend fallito')
                        time.sleep(.1)
                    else: raise RuntimeError('Backend non raggiungibile')
                    last_request=['avvio']
                    def call(method,path,expected=200,**kwargs):
                        last_request[0]=method+' '+path
                        response=client.request(method,path,**kwargs)
                        if response.status_code!=expected:
                            raise RuntimeError(f'{path}: HTTP {response.status_code}')
                        return response
                    call('GET','/')
                    checks.append('interfaccia e API dalla stessa origine')
                    call('POST','/auth/setup',expected=201,json={'username':'integration-check','password':password,
                        'farm_id':'test-farm','setup_token':token})
                    login=call('POST','/auth/login',json={'username':'integration-check','password':password}).json()
                    client.headers['Authorization']='Bearer '+login['access_token']
                    checks.append('primo account e accesso')
                    points=[{'lat':44.65,'lng':11.18},{'lat':44.651,'lng':11.18},{'lat':44.651,'lng':11.181}]
                    parcel={'id':'live-test','name':'Campo temporaneo di verifica','crop':'Frumento tenero','points':points,'soil':{},'revision':0}
                    saved=call('PUT','/parcels/live-test',json=parcel).json()
                    assert call('GET','/parcels').json()[0]['revision']==saved['revision']
                    checks.append('particelle e persistenza')
                    cycle=call('POST','/crop/cycles',expected=201,json={'parcel_id':'live-test','season':str(date.today().year),
                        'crop':'frumento_tenero','sowing_date':(date.today()-timedelta(days=50)).isoformat()}).json()
                    weather=call('POST','/weather',json={'latitude':44.65,'longitude':11.18,'history_days':30}).json()
                    assert len(weather['history'])==30 and len(weather['forecast'])==7
                    call('POST',f"/crop/cycles/{cycle['id']}/bbch",expected=201,
                        json={'observed_at':weather['historical_end'],'bbch':25})
                    analysis=call('POST','/agronomy/analyze',json={'parcel_id':'live-test','latitude':44.65,'longitude':11.18,'history_days':30}).json()
                    assert analysis['crop_context']['latest_bbch']['bbch']==25
                    assert analysis['windows']['7']['rain_mm'] is not None
                    checks.append('meteo reale, colture, BBCH e indicatori')
                    soil={'parcel_id':'live-test','sample_date':date.today().isoformat(),'ph':6.5,'client_id':'temporary-sample'}
                    first=call('POST','/soil/analyses',expected=201,json=soil).json()
                    again=call('POST','/soil/analyses',expected=201,json=soil).json()
                    assert first['id']==again['id']
                    mapped=call('POST','/soil/automatic-analysis',json={'parcel_id':'live-test','points':points}).json()
                    assert mapped['status']=='ok' and mapped['results'][0]['soil_units']
                    checks.append('analisi manuali senza duplicati e cartografia suolo reale')
                    geometry={'type':'Polygon','coordinates':[[[p['lng'],p['lat']] for p in points]+[[points[0]['lng'],points[0]['lat']]]]}
                    catalog=call('POST','/scenes',json={'geometry':geometry,'start_date':(date.today()-timedelta(days=90)).isoformat(),
                        'end_date':date.today().isoformat(),'limit':100}).json()['scenes']
                    usable=[s for s in catalog if isinstance(s.get('cloud_cover'),(int,float)) and s['cloud_cover']<=30]
                    assert usable
                    day=min(usable,key=lambda s:s['cloud_cover'])['datetime'][:10]
                    for index in ['ndvi','dvi']:
                        series=call('POST','/parcel-timeseries',json={'geometry':geometry,'dates':[day],'index':index}).json()
                        assert series['observations'][0]['status']=='ok'
                        png=call('POST','/overlay',json={'geometry':geometry,'date':day,'index':index,'width':128,'height':128})
                        assert png.content.startswith(b'\x89PNG\r\n\x1a\n')
                    legacy=call('POST','/statistics',json={'geometry':geometry,'date':day}).json()
                    assert legacy['indices']['ndvi']['mean'] is not None and legacy['indices']['dvi']['mean'] is not None
                    checks.append('catalogo Copernicus, NDVI, DVI, statistiche e immagini reali')
                    services=call('POST','/integrations/status',json={}).json()
                    if not services['all_available']:
                        failed=[{'id':s['id'],'status':s['status']} for s in services['services'] if s['status']!='ok']
                        raise RuntimeError('Servizi non disponibili: '+json.dumps(failed))
                    checks.append('verifica collegamenti: tutti disponibili')
                    call('DELETE',f"/parcels/live-test?revision={saved['revision']}",expected=204)
                    assert call('GET','/parcels').json()==[]
                    call('POST','/auth/logout',expected=204)
                    call('GET','/auth/me',expected=401)
                    checks.append('cancellazione e revoca della sessione')
                return {'ok':True,'checks':checks,'temporary_database':True}
            except AssertionError as exc:
                raise RuntimeError('Esito inatteso: '+last_request[0]) from exc
            finally:
                server.terminate()
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired: server.kill(); server.wait()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try: result=run()
    except Exception as exc:
        result={'ok':False,'error':str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__,'temporary_database':True}
    data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    print(data)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(data)
    raise SystemExit(0 if result['ok'] else 1)
