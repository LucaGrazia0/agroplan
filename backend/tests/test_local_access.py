import pytest
from fastapi.testclient import TestClient

import main
import storage
from local_access import prepare_local_farm


@pytest.fixture
def local_client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'local.sqlite')
    monkeypatch.setenv('AGROPLAN_LOCAL_MODE','1')
    monkeypatch.setenv('AGROPLAN_LOCAL_FARM_ID','local-test')
    monkeypatch.delenv('RENDER',raising=False)
    with TestClient(main.app,base_url='http://localhost',client=('127.0.0.1',50000)) as client:
        yield client


def test_local_app_works_without_password_or_account(local_client,parcel):
    status=local_client.get('/auth/status').json()
    assert status['local_mode'] is True and status['setup_required'] is False
    assert local_client.get('/auth/me').json()['farm_id']=='local-test'
    assert local_client.put('/parcels/field-1',json=parcel).status_code==200
    assert len(local_client.get('/parcels').json())==1
    assert local_client.post('/crop/cycles',json={'parcel_id':'field-1','season':'2026','crop':'orzo'}).status_code==201
    assert local_client.post('/auth/logout').status_code==204
    with storage.connect() as db:
        assert db.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0


def test_remote_origins_and_rebound_hosts_cannot_use_local_access(local_client):
    assert local_client.get('/parcels',headers={'Origin':'https://other.example'}).status_code==401
    assert local_client.get('/parcels',headers={'Host':'rebound.example'}).status_code==401
    assert local_client.get('/parcels',headers={'Sec-Fetch-Site':'cross-site'}).status_code==401
    assert local_client.get('/parcels',headers={'Origin':'http://localhost'}).status_code==200
    with TestClient(main.app,base_url='http://localhost',client=('192.0.2.1',50000)) as remote:
        assert remote.get('/parcels').status_code==401


def test_local_mode_is_disabled_on_hosting(local_client,monkeypatch):
    monkeypatch.setenv('RENDER','true')
    assert local_client.get('/parcels').status_code==401
    assert local_client.get('/auth/status').json().get('local_mode',False) is False


def test_local_access_preserves_existing_accounts_and_assigns_old_data(local_client,monkeypatch):
    monkeypatch.delenv('AGROPLAN_LOCAL_FARM_ID')
    with storage.connect() as db:
        db.execute("INSERT INTO auth_users(username,password_hash,farm_id) VALUES('owner','unchanged-hash','existing-farm')")
        db.execute("INSERT INTO agr_parcels(id,farm_id) VALUES('old-field','__legacy__')")
    assert prepare_local_farm()=='existing-farm'
    with storage.connect() as db:
        assert db.execute("SELECT password_hash FROM auth_users WHERE username='owner'").fetchone()[0]=='unchanged-hash'
        assert tuple(db.execute("SELECT farm_id,revision FROM agr_parcels WHERE id='old-field'").fetchone())==('existing-farm',0)
