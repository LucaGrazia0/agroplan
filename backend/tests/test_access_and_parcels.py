import time
import main
import storage


def test_authentication_required(client, parcel):
    assert client.get('/health').status_code == 200
    for path in ['/parcels', '/crop/cycles?parcel_id=field-1', '/soil/analyses?parcel_id=field-1']:
        assert client.get(path).status_code == 401
    assert client.put('/parcels/field-1', json=parcel).status_code == 401
    assert client.post('/weather', json={'latitude':44.5,'longitude':11.3}).status_code == 401
    geometry = {'type':'Polygon','coordinates':[[[11.3,44.5],[11.31,44.5],[11.31,44.51],[11.3,44.5]]]}
    for path in ['/scenes', '/overlay', '/statistics']:
        assert client.post(path, json={'geometry':geometry}).status_code == 401
    assert client.post('/parcel-timeseries', json={'geometry':geometry,'dates':['2026-10-01']}).status_code == 401


def test_login_logout_expiry_and_session_hash(client, headers):
    assert client.post('/auth/login', json={'username':'alice','password':'wrong'}).status_code == 401
    auth = headers()
    assert client.get('/auth/me', headers=auth).json()['farm_id'] == 'farm-a'
    with storage.connect() as db:
        token = auth['Authorization'].split()[1]
        assert db.execute('SELECT token_hash FROM auth_sessions').fetchone()[0] != token
    assert client.post('/auth/logout', headers=auth).status_code == 204
    assert client.get('/auth/me', headers=auth).status_code == 401
    auth = headers()
    with storage.connect() as db:
        db.execute('UPDATE auth_sessions SET expires_at=?', (time.time()-1,))
    assert client.get('/auth/me', headers=auth).status_code == 401


def test_login_throttling(client):
    for _ in range(5):
        assert client.post('/auth/login', json={'username':'alice','password':'wrong'}).status_code == 401
    assert client.post('/auth/login', json={'username':'alice','password':'correct-horse-battery-staple'}).status_code == 429
    with storage.connect() as db:
        db.execute('UPDATE auth_attempts SET blocked_until=?', (time.time()-1,))
    assert client.post('/auth/login', json={'username':'alice','password':'correct-horse-battery-staple'}).status_code == 200


def test_persistence_ownership_conflicts_and_deletion(client, headers, parcel):
    alice, bob, anna = headers(), headers('bob'), headers('anna')
    saved = client.put('/parcels/field-1', json=parcel, headers=alice)
    assert saved.status_code == 200
    assert saved.json()['revision'] == 1
    assert client.get('/parcels', headers=anna).json()[0]['name'] == 'Campo Nord'
    assert client.get('/parcels', headers=bob).json() == []
    assert client.put('/parcels/field-1', json=parcel, headers=bob).status_code == 404
    assert client.delete('/parcels/field-1?revision=1', headers=bob).status_code == 404
    updated = client.put('/parcels/field-1', json={**parcel,'revision':1,'name':'Campo aggiornato'}, headers=anna)
    assert updated.json()['revision'] == 2
    conflict = client.put('/parcels/field-1', json={**parcel,'revision':1}, headers=alice)
    assert conflict.status_code == 409 and conflict.json()['detail']['current']['name'] == 'Campo aggiornato'
    assert client.delete('/parcels/field-1?revision=1', headers=alice).status_code == 409
    assert client.delete('/parcels/field-1?revision=2', headers=alice).status_code == 204
    assert client.get('/parcels', headers=alice).json() == []
    assert client.put('/parcels/field-1', json=parcel, headers=alice).status_code == 409


def test_complete_crop_soil_agronomy_flow(client, headers, parcel, monkeypatch):
    alice, bob = headers(), headers('bob')
    client.put('/parcels/field-1', json=parcel, headers=alice)
    cycle_data = {'parcel_id':'field-1','season':'2026','crop':'frumento_tenero','sowing_date':'2026-09-20'}
    assert client.post('/crop/cycles', json=cycle_data, headers=bob).status_code == 404
    cycle = client.post('/crop/cycles', json=cycle_data, headers=alice).json()
    path = f"/crop/cycles/{cycle['id']}/bbch"
    assert client.post(path, json={'observed_at':'2026-10-01','bbch':25}, headers=alice).status_code == 201
    assert client.get(path, headers=bob).status_code == 404
    assert client.post(path, json={'observed_at':'2026-10-01','bbch':25}, headers=bob).status_code == 404
    assert client.get('/crop/cycles?parcel_id=field-1', headers=bob).status_code == 404
    analysis = {'parcel_id':'field-1','sample_date':'2026-10-01','ph':6.5}
    assert client.post('/soil/analyses', json=analysis, headers=alice).status_code == 201
    assert client.get('/soil/analyses?parcel_id=field-1', headers=alice).json()[0]['ph'] == 6.5
    assert client.post('/soil/analyses', json=analysis, headers=bob).status_code == 404
    assert client.get('/soil/analyses?parcel_id=field-1', headers=bob).status_code == 404
    from datetime import date, timedelta
    async def weather(*args, **kwargs):
        rows = [{'date':(date(2026,10,1)-timedelta(days=i)).isoformat(), 'temperature_2m_max':20,
                 'temperature_2m_min':10, 'precipitation_sum':2, 'et0_fao_evapotranspiration':3} for i in range(60)]
        return {'history':rows,'source':'Test','historical_end':'2026-10-01'}
    # The registered handler resolves its global weather helpers at request time.
    monkeypatch.setattr(main, '_open_meteo_weather', weather)
    async def no_forecast(req): return {}, []
    monkeypatch.setattr(main, '_met_norway_weather', no_forecast)
    request = {'parcel_id':'field-1','latitude':44.5,'longitude':11.3}
    result = client.post('/agronomy/analyze', json=request, headers=alice)
    assert result.status_code == 200
    assert result.json()['crop_context']['latest_bbch']['bbch'] == 25
    assert result.json()['crop_context']['sowing_date'] == '2026-09-20'
    assert result.json()['windows']['7']['climatic_balance_mm'] == -7
    assert client.post('/agronomy/analyze', json=request, headers=bob).status_code == 404
    # Deletion also denies access to remaining related records.
    client.delete('/parcels/field-1?revision=1', headers=alice)
    assert client.get(path, headers=alice).status_code == 404


def test_existing_records_are_reserved(client, headers, parcel):
    with storage.connect() as db:
        db.execute("INSERT INTO agr_crop_cycles(parcel_id,season,crop) VALUES('legacy','2025','orzo')")
    storage.initialize()
    auth = headers()
    assert client.put('/parcels/legacy', json={**parcel,'id':'legacy'}, headers=auth).status_code == 404
    assert client.get('/crop/cycles?parcel_id=legacy', headers=auth).status_code == 404


def test_soil_retry_is_idempotent_and_conflicting_reuse_is_rejected(client, headers, parcel):
    auth = headers()
    client.put('/parcels/field-1', json=parcel, headers=auth)
    analysis = {'parcel_id':'field-1','client_id':'offline-1','sample_date':'2026-10-01','ph':6.5}
    first = client.post('/soil/analyses', json=analysis, headers=auth)
    retry = client.post('/soil/analyses', json=analysis, headers=auth)
    assert first.status_code == retry.status_code == 201
    assert first.json()['id'] == retry.json()['id']
    assert len(client.get('/soil/analyses?parcel_id=field-1', headers=auth).json()) == 1
    assert client.post('/soil/analyses', json={**analysis,'ph':7}, headers=auth).status_code == 409


def test_degenerate_parcels_are_rejected(client, headers, parcel):
    auth = headers()
    point = parcel['points'][0]
    for points in [[point]*3, [{'lat':44.5,'lng':11.3},{'lat':44.51,'lng':11.31},{'lat':44.52,'lng':11.32}]]:
        assert client.put('/parcels/field-1',json={**parcel,'points':points},headers=auth).status_code == 422
    assert client.get('/parcels',headers=auth).json() == []
