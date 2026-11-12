import sqlite3
import sys
from pathlib import Path
import manage
import storage


def test_backup_preserves_data_and_is_verified(client, headers, parcel, tmp_path, monkeypatch):
    auth = headers()
    client.put('/parcels/field-1',json=parcel,headers=auth)
    destination = tmp_path / 'backup.sqlite'
    monkeypatch.setattr(manage, 'DB', storage.DB)
    monkeypatch.setattr(sys,'argv',['manage.py','backup',str(destination)])
    manage.main()
    with sqlite3.connect(destination) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT id FROM agr_parcels').fetchone()[0]=='field-1'
    assert destination.stat().st_mode & 0o777 == 0o600


def test_legacy_claim_does_not_change_current_owners(client, headers, parcel, monkeypatch):
    auth = headers()
    client.put('/parcels/field-1',json=parcel,headers=auth)
    with storage.connect() as db:
        db.execute("INSERT INTO agr_crop_cycles(parcel_id,season,crop) VALUES('legacy','2025','orzo')")
    monkeypatch.setattr(sys,'argv',['manage.py','claim-legacy','--farm','farm-a'])
    manage.main()
    with storage.connect() as db:
        assert db.execute("SELECT farm_id FROM agr_parcels WHERE id='field-1'").fetchone()[0]=='farm-a'
        assert db.execute("SELECT revision FROM agr_parcels WHERE id='legacy'").fetchone()[0]==0
    assert client.put('/parcels/legacy',json={**parcel,'id':'legacy'},headers=auth).status_code==200
