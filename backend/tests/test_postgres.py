"""Optional real PostgreSQL tests; isolated disposable schema per test."""
import os
import uuid
from urllib.parse import urlsplit,parse_qsl,urlencode
import pytest
from fastapi.testclient import TestClient
import storage
import main
from auth import password_hash


@pytest.fixture
def pg_client(monkeypatch):
    url=os.getenv('AGROPLAN_TEST_POSTGRES_URL')
    if not url: pytest.skip('PostgreSQL integration URL not configured')
    import psycopg
    from psycopg import sql
    schema='test_'+uuid.uuid4().hex
    with psycopg.connect(url,autocommit=True) as db:
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    uri=urlsplit(url)
    query=dict(parse_qsl(uri.query),options='-csearch_path='+schema)
    monkeypatch.setenv('DATABASE_URL',uri._replace(query=urlencode(query)).geturl())
    monkeypatch.setenv('AGROPLAN_LOCAL_MODE','0')
    try:
        with TestClient(main.app) as client:
            with storage.connect() as db:
                db.execute('INSERT INTO auth_users(username,password_hash,farm_id) VALUES(?,?,?)',('alice',password_hash.hash('test-only-password'),'farm-a'))
            token=client.post('/auth/login',json={'username':'alice','password':'test-only-password'}).json()['access_token']
            yield client,{'Authorization':'Bearer '+token}
    finally:
        from postgres_storage import close_pool
        close_pool(os.environ['DATABASE_URL'])
        with psycopg.connect(url,autocommit=True) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_real_postgres_persistence_ids_conflicts_and_analysis(pg_client,parcel):
    client,auth=pg_client
    assert client.put('/parcels/field-1',json=parcel,headers=auth).json()['revision']==1
    assert client.put('/parcels/field-1',json=parcel,headers=auth).status_code==409
    cycle=client.post('/crop/cycles',json={'parcel_id':'field-1','season':'2026','crop':'orzo'},headers=auth).json()
    assert isinstance(cycle['id'],int)
    assert client.post(f"/crop/cycles/{cycle['id']}/bbch",json={'observed_at':'2026-11-01','bbch':25},headers=auth).status_code==201
    soil={'parcel_id':'field-1','sample_date':'2026-11-01','ph':6.5,'client_id':'pg-soil'}
    first=client.post('/soil/analyses',json=soil,headers=auth)
    assert first.status_code==201
    assert client.post('/soil/analyses',json=soil,headers=auth).json()['id']==first.json()['id']
    assert client.get('/agronomy/overview',headers=auth).json()['parcels'][0]['review']['coverage']['soil'] is True
    from datetime import date
    from field_records import save_result
    observation={'parcel_id':'field-1','observed_at':date.today().isoformat(),'symptoms':['spots'],'notes':'Rilievo di prova'}
    assert client.put('/observations/'+str(uuid.uuid4()),json=observation,headers=auth).status_code==200
    assert len(client.get('/observations?parcel_id=field-1',headers=auth).json())==1
    save_result('field-1',{'parcel_id':'field-1','crop_review':{'summary':'Test PostgreSQL'}})
    assert len(client.get('/agronomy/results?parcel_id=field-1',headers=auth).json())==1
    assert client.post('/auth/logout',headers=auth).status_code==204
    assert client.get('/parcels',headers=auth).status_code==401


def test_verified_local_migration_and_passwordless_pairing(pg_client,parcel,tmp_path,monkeypatch):
    import json
    from transfer import migrate,issue_pairing,export_backup
    client,_=pg_client
    with storage.connect() as db:
        db.execute('DELETE FROM auth_sessions')
        db.execute('DELETE FROM auth_users')
    source=tmp_path/'source.sqlite'
    with monkeypatch.context() as local:
        local.delenv('DATABASE_URL')
        local.setattr(storage,'DB',source)
        storage.initialize()
        with storage.connect() as db:
            db.execute('INSERT INTO agr_parcels(id,farm_id,payload,revision) VALUES(?,?,?,?)',('field-1','local',json.dumps(parcel),1))
            db.execute("INSERT INTO agr_crop_cycles(id,parcel_id,season,crop) VALUES(10,'field-1','2026','orzo')")
            db.execute("INSERT INTO agr_bbch_observations(cycle_id,observed_at,bbch) VALUES(10,'2026-11-01',25)")
    backup=tmp_path/'before.sqlite'
    counts=migrate(source,'farm-owner','owner',backup)
    assert backup.is_file() and counts['agr_crop_cycles']==1
    pairing=tmp_path/'pair.txt'
    issue_pairing('owner',pairing)
    response=client.post('/auth/pair',json={'code':pairing.read_text().strip()})
    assert response.status_code==200
    auth={'Authorization':'Bearer '+response.json()['access_token']}
    assert client.get('/agronomy/overview',headers=auth).json()['parcels'][0]['crop_context']['latest_bbch']['bbch']==25
    next_cycle=client.post('/crop/cycles',json={'parcel_id':'field-1','season':'2027','crop':'orzo'},headers=auth).json()
    assert next_cycle['id']>10
    exported=tmp_path/'cloud.json'
    export_backup(exported)
    assert len(json.loads(exported.read_text())['tables']['agr_crop_cycles'])==2
