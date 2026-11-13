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
    assert client.post('/auth/logout',headers=auth).status_code==204
    assert client.get('/parcels',headers=auth).status_code==401
