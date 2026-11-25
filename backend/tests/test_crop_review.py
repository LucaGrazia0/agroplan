from datetime import date
from fastapi import HTTPException
from crop_analysis import build_crop_review
import storage
import main
from auth import digest
import time


def test_missing_data_and_outdated_bbch_are_explicit():
    crop={'crop':'orzo','sowing_date':None,'latest_bbch':{'bbch':25,'observed_at':'2026-09-01'}}
    result=build_crop_review(crop,None,[],today=date(2026,11,13))
    assert result['satellite']['delta'] is None
    assert result['coverage']['soil'] is False
    assert any('semina' in text for text in result['missing_data'])
    assert any(check['title']=='Aggiorna il rilievo BBCH' for check in result['checks'])


def test_cloudy_duplicate_and_stale_satellite_data_do_not_form_a_trend():
    items=[{'observed_at':'2026-11-10','mean':0.7,'valid_percent':80},
           {'observed_at':'2026-11-10','mean':0.7,'valid_percent':80},
           {'observed_at':'2026-11-01','mean':0.4,'valid_percent':20},
           {'observed_at':'2026-06-01','mean':0.1,'valid_percent':90}]
    assert build_crop_review(None,None,items,today=date(2026,11,13))['satellite']['delta'] is None
    items.append({'observed_at':'2026-11-05','mean':0.5,'valid_percent':75})
    assert build_crop_review(None,None,items,today=date(2026,11,13))['satellite']['delta']==0.2


def test_overview_is_private_and_keeps_legacy_data_visible(client,headers,parcel):
    alice=headers()
    client.put('/parcels/field-1',json=parcel,headers=alice)
    with storage.connect() as db:
        db.execute("INSERT INTO agr_parcels(id,farm_id) VALUES('old','farm-a')")
        db.execute("INSERT INTO agr_crop_cycles(parcel_id,season,crop) VALUES('old','2026','orzo')")
    data=client.get('/agronomy/overview',headers=alice).json()
    assert data['parcel_count']==2
    assert any(p['review']['coverage']['geometry'] is False for p in data['parcels'])
    assert client.get('/agronomy/overview',headers=headers('bob')).json()['parcels']==[]
    assert client.get('/agronomy/overview').status_code==401


def test_weather_outage_preserves_crop_and_soil_review(client,headers,parcel,monkeypatch):
    alice=headers()
    client.put('/parcels/field-1',json=parcel,headers=alice)
    client.post('/crop/cycles',json={'parcel_id':'field-1','season':'2026','crop':'orzo'},headers=alice)
    async def offline(*args): raise HTTPException(503,'offline')
    monkeypatch.setattr(main,'_nasa_weather',offline)
    async def unavailable(*args): raise main.httpx.ConnectError('offline')
    monkeypatch.setattr(main,'_open_meteo_weather',unavailable)
    data=client.post('/agronomy/analyze',json={'parcel_id':'field-1','latitude':44.5,'longitude':11.3},headers=alice).json()
    assert data['crop_review']['coverage']['crop'] is True
    assert data['windows']=={}
    assert data['crop_review']['coverage']['weather_7_days'] is False


def test_device_pairing_is_one_time_private_expiring_and_revocable(client):
    code='pairing-test-code-that-is-at-least-32-characters'
    with storage.connect() as db:
        db.execute('INSERT INTO auth_pairings VALUES(?,?,?)',(digest(code),'alice',time.time()+60))
    assert client.get('/auth/status').json()['pairing_available'] is True
    assert client.post('/auth/pair',json={'code':'incorrect-code-long-enough-to-pass-validation'}).status_code==401
    paired=client.post('/auth/pair',json={'code':code})
    assert paired.status_code==200
    assert client.post('/auth/pair',json={'code':code}).status_code==401
    auth={'Authorization':'Bearer '+paired.json()['access_token']}
    assert client.get('/auth/me',headers=auth).json()['farm_id']=='farm-a'
    assert client.post('/auth/logout',headers=auth).status_code==204
    assert client.get('/auth/me',headers=auth).status_code==401
