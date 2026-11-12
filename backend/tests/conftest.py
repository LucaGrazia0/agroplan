import pytest
from fastapi.testclient import TestClient
import main
import storage
from auth import password_hash


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB', tmp_path / 'test.sqlite')
    main._weather_cache.clear()
    main._weather_locks.clear()
    with TestClient(main.app) as client:
        with storage.connect() as db:
            hashed = password_hash.hash('correct-horse-battery-staple')
            db.executemany('INSERT INTO auth_users(username,password_hash,farm_id) VALUES(?,?,?)',
                           [('alice', hashed, 'farm-a'), ('bob', hashed, 'farm-b'), ('anna', hashed, 'farm-a')])
        yield client


@pytest.fixture
def headers(client):
    def login(username='alice'):
        response = client.post('/auth/login', json={'username': username, 'password': 'correct-horse-battery-staple'})
        assert response.status_code == 200
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    return login


@pytest.fixture
def parcel():
    return {'id': 'field-1', 'name': 'Campo Nord', 'crop': 'Frumento tenero', 'soil': {},
            'points': [{'lat': 44.5, 'lng': 11.3}, {'lat': 44.51, 'lng': 11.3},
                       {'lat': 44.51, 'lng': 11.31}], 'revision': 0}
