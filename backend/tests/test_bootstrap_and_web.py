import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
import storage
from auth import router as auth_router, require_user, User
from integrations import register_integration_routes
from soil_sources import parse_soil_units
from web_app import mount_web_app

TOKEN='local-setup-'+'x'*40


@pytest.fixture
def empty_client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'empty.sqlite')
    monkeypatch.setenv('AGROPLAN_SETUP_TOKEN',TOKEN)
    with TestClient(main.app) as client:
        yield client


def test_first_account_is_paired_and_cannot_be_recreated(empty_client):
    status=empty_client.get('/auth/status')
    assert status.json()['setup_required'] and status.json()['setup_enabled']
    assert TOKEN not in status.text
    account={'username':'luca','password':'a-secure-local-password','farm_id':'farm-local','setup_token':'invalid-'+'y'*40}
    assert empty_client.post('/auth/setup',json=account).status_code==403
    account['setup_token']=TOKEN
    created=empty_client.post('/auth/setup',json=account)
    assert created.status_code==201
    assert empty_client.post('/auth/setup',json={**account,'username':'other'}).status_code==409
    assert empty_client.get('/auth/status').json()['setup_enabled'] is False
    login=empty_client.post('/auth/login',json={'username':'luca','password':account['password']})
    auth={'Authorization':'Bearer '+login.json()['access_token']}
    assert empty_client.get('/auth/me',headers=auth).json()['farm_id']=='farm-local'
    assert empty_client.get('/parcels',headers=auth).json()==[]


def test_first_setup_disabled_without_operator_token(empty_client,monkeypatch):
    monkeypatch.delenv('AGROPLAN_SETUP_TOKEN')
    assert empty_client.get('/auth/status').json()['setup_enabled'] is False
    assert empty_client.post('/auth/setup',json={'username':'luca','password':'a-secure-local-password','farm_id':'farm-local','setup_token':TOKEN}).status_code==403


def test_legacy_data_are_only_claimed_when_requested(empty_client):
    with storage.connect() as db:
        db.execute("INSERT INTO agr_parcels(id,farm_id) VALUES('old-field','__legacy__')")
    assert empty_client.get('/auth/status').json()['legacy_available'] is True
    account={'username':'luca','password':'a-secure-local-password','farm_id':'farm-local','setup_token':TOKEN,'claim_legacy':True}
    assert empty_client.post('/auth/setup',json=account).status_code==201
    with storage.connect() as db:
        row=db.execute("SELECT farm_id,revision FROM agr_parcels WHERE id='old-field'").fetchone()
        assert tuple(row)==('farm-local',0)


def test_old_database_is_backed_up_before_migration(tmp_path,monkeypatch):
    database=tmp_path/'old.sqlite'
    with closing(sqlite3.connect(database)) as db:
        db.execute('CREATE TABLE preserved(value TEXT)')
        db.execute("INSERT INTO preserved VALUES('keep me')")
        db.commit()
    monkeypatch.setattr(storage,'DB',database)
    storage.initialize()
    backups=list((tmp_path/'backups').glob('*.sqlite'))
    assert len(backups)==1 and backups[0].stat().st_mode & 0o777 == 0o600
    with closing(sqlite3.connect(backups[0])) as db:
        assert db.execute('SELECT value FROM preserved').fetchone()[0]=='keep me'
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='auth_users'").fetchone() is None
    storage.initialize()
    assert len(list((tmp_path/'backups').glob('*.sqlite')))==1


def test_one_origin_serves_frontend_and_api(tmp_path,monkeypatch):
    web=tmp_path/'web'; web.mkdir()
    (web/'index.html').write_text('<html>AgroPlan frontend</html>')
    monkeypatch.setenv('AGROPLAN_WEB_DIR',str(web))
    monkeypatch.setattr(storage,'DB',tmp_path/'web.sqlite')
    storage.initialize()
    app=FastAPI()
    app.include_router(auth_router)
    mount_web_app(app)
    with TestClient(app) as client:
        assert 'AgroPlan frontend' in client.get('/').text
        assert client.get('/').headers['cache-control']=='no-cache'
        assert client.get('/auth/status').headers['content-type'].startswith('application/json')
        assert client.get('/auth/unknown').status_code==404


def test_diagnostics_are_authenticated_and_report_failures(client):
    assert client.post('/integrations/status',json={}).status_code==401
    calls=[]
    async def available(req):
        calls.append('ok')
        return {'status':'ok','message':'Service ready'}
    async def broken(req): raise RuntimeError('Do not expose internal data')
    app=FastAPI()
    app.dependency_overrides[require_user]=lambda:User('tester','test-farm')
    register_integration_routes(app,{'ready':available,'broken':broken})
    with TestClient(app) as check:
        response=check.post('/integrations/status',json={})
        again=check.post('/integrations/status',json={})
    assert response.status_code==200 and response.json()['all_available'] is False
    assert [s['status'] for s in response.json()['services']]==['ok','unavailable']
    assert 'Do not expose' not in response.text
    assert calls==['ok'] and again.json()['checked_at']==response.json()['checked_at']


def test_soil_names_do_not_shift_when_descriptions_contain_semicolons():
    headers=['OBJECTID','ID delineazione','NUM_POL','TIPO_POLIG','TIPO_RILEV','DATA_AGG','AMBIENTE','Sigla unità cart.','NOME_UC','CARATTERI_STAZ','USO_SUOLO','FID_DISTR_SUOLI','NOTE_SUOLI','MET_APPOS_LIMITE','FID_LIMITE','DESC_COMPLETA','NOTE_ILLUSTRATIVE','CODICE','HECTARES','Shape','SHAPE.AREA','SHAPE.LEN']
    body=['12','34','56','delineazione','rilevata','2026','Pianura','TEST1','consociazione dei suoli CAMPIONE franco limosi','Descrizione originale del territorio; altra descrizione senza etichette inventate','seminativi','Buono','note','metodo','limite','https://example.test/details','illustrazioni','DPD','10','Polygon','1000','200']
    units=parse_soil_units('@Carta_Suoli_50k '+';'.join(headers+body)+';')
    assert units[0]['code']=='TEST1'
    assert units[0]['name']=='consociazione dei suoli CAMPIONE franco limosi'
    assert 'altra descrizione senza etichette inventate' in units[0]['descriptions']
    assert parse_soil_units('No features')==[]


def test_legacy_statistics_use_complete_calendar_days(client,headers,monkeypatch):
    payloads=[]
    async def upstream(path,payload,accept='application/json'):
        import httpx
        payloads.append(payload)
        return httpx.Response(200,json={'data':[{'outputs':{'index':{'bands':{'B0':{'stats':{
            'mean':.61,'min':.2,'max':.8,'stDev':.1,'sampleCount':100,'noDataCount':20}}}}}}]})
    monkeypatch.setattr(main,'sentinel_post',upstream)
    geometry={'type':'Polygon','coordinates':[[[11.18,44.65],[11.181,44.65],[11.181,44.651],[11.18,44.65]]]}
    result=client.post('/statistics',headers=headers(),json={'geometry':geometry,'date':'2026-10-01'})
    assert result.status_code==200
    assert result.json()['indices']['ndvi']['mean']==.61
    assert result.json()['indices']['dvi']['stDev']==.1
    assert len(payloads)==2
    for payload in payloads:
        assert payload['aggregation']['timeRange']=={'from':'2026-10-01T00:00:00Z','to':'2026-10-02T00:00:00Z'}
        assert payload['input']['bounds']['geometry']==geometry
