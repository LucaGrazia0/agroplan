"""Provisioned accounts, revocable opaque sessions, and parcel authorization."""
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pwdlib import PasswordHash

from storage import connect
from local_access import request_allowed

router = APIRouter(prefix='/auth', tags=['Accesso'])
password_hash = PasswordHash.recommended()
_dummy_hash = password_hash.hash(secrets.token_urlsafe(32))
security = HTTPBearer(auto_error=False)
SESSION_SECONDS = 8 * 60 * 60


@dataclass(frozen=True)
class User:
    username: str
    farm_id: str


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def require_user(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]):
    if request_allowed(request):
        import os
        return User('locale', os.getenv('AGROPLAN_LOCAL_FARM_ID', 'azienda-locale'))
    if credentials is not None:
        with connect() as db:
            row = db.execute('''SELECT u.username,u.farm_id FROM auth_sessions s
                JOIN auth_users u ON s.username=u.username
                WHERE s.token_hash=? AND s.expires_at>? AND u.disabled=0''',
                (digest(credentials.credentials), time.time())).fetchone()
        if row:
            return User(row['username'], row['farm_id'])
    raise HTTPException(401, 'Accedi per continuare.', headers={'WWW-Authenticate': 'Bearer'})


CurrentUser = Annotated[User, Depends(require_user)]


def require_parcel(parcel_id, user):
    with connect() as db:
        row = db.execute('SELECT * FROM agr_parcels WHERE id=? AND farm_id=? AND deleted=0',
                         (parcel_id, user.farm_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Particella non trovata.')
    return row


def require_cycle(cycle_id, user):
    with connect() as db:
        row = db.execute('''SELECT c.* FROM agr_crop_cycles c JOIN agr_parcels p ON p.id=c.parcel_id
            WHERE c.id=? AND p.farm_id=? AND p.deleted=0''', (cycle_id, user.farm_id)).fetchone()
    if row is None:
        raise HTTPException(404, 'Ciclo non trovato.')
    return row


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


@router.post('/login')
def login(item: Login):
    username = item.username.strip().lower()
    now = time.time()
    with connect() as db:
        attempt = db.execute('SELECT * FROM auth_attempts WHERE username=?', (username,)).fetchone()
        if attempt and attempt['blocked_until'] > now:
            raise HTTPException(429, 'Troppi tentativi. Riprova tra qualche minuto.', headers={'Retry-After': '300'})
        row = db.execute('SELECT * FROM auth_users WHERE username=?', (username,)).fetchone()
    valid = password_hash.verify(item.password, row['password_hash'] if row else _dummy_hash)
    if not valid or row is None or row['disabled']:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM auth_attempts WHERE username=?', (username,)).fetchone()
            failures = (current['failures'] if current and current['blocked_until'] == 0 else 0) + 1
            blocked_until = (current['blocked_until'] if current and current['blocked_until'] > now
                             else now + 300 if failures >= 5 else 0)
            db.execute('''INSERT INTO auth_attempts VALUES(?,?,?) ON CONFLICT(username) DO UPDATE
                SET failures=excluded.failures,blocked_until=excluded.blocked_until''',
                (username, failures, blocked_until))
        raise HTTPException(401, 'Credenziali non valide.')
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('DELETE FROM auth_attempts WHERE username=?', (username,))
        db.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (now,))
        db.execute('INSERT INTO auth_sessions VALUES(?,?,?)', (digest(token), username, now + SESSION_SECONDS))
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': SESSION_SECONDS,
            'user': {'username': username, 'farm_id': row['farm_id']}}


@router.get('/me')
def me(user: CurrentUser):
    return {'username': user.username, 'farm_id': user.farm_id}


@router.post('/logout', status_code=204)
def logout(request: Request, user: CurrentUser):
    token = request.headers.get('authorization', '').partition(' ')[2]
    with connect() as db:
        db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(token),))


class PairDevice(BaseModel):
    code: str = Field(min_length=32, max_length=200)


@router.post('/pair')
def pair_device(item: PairDevice):
    now = time.time()
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('''SELECT u.username,u.farm_id FROM auth_pairings p
            JOIN auth_users u ON p.username=u.username
            WHERE p.code_hash=? AND p.expires_at>? AND u.disabled=0''', (digest(item.code), now)).fetchone()
        if row is None:
            raise HTTPException(401, 'Codice di abbinamento non valido o già utilizzato.')
        db.execute('DELETE FROM auth_pairings WHERE code_hash=?', (digest(item.code),))
        seconds = 90 * 24 * 60 * 60
        db.execute('INSERT INTO auth_sessions VALUES(?,?,?)', (digest(token), row['username'], now + seconds))
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': seconds,
            'user': {'username': row['username'], 'farm_id': row['farm_id']}}


class SetupAccount(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=1024)
    farm_id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')
    setup_token: str = Field(min_length=32, max_length=200)
    claim_legacy: bool = False


@router.get('/status')
def account_status(request: Request):
    import os
    if request_allowed(request):
        return {'local_mode': True, 'user': {'username': 'Uso locale',
                'farm_id': os.getenv('AGROPLAN_LOCAL_FARM_ID', 'azienda-locale')},
                'setup_required': False, 'setup_enabled': False, 'legacy_available': False}
    with connect() as db:
        empty = db.execute('SELECT 1 FROM auth_users LIMIT 1').fetchone() is None
        legacy = db.execute("SELECT 1 FROM agr_parcels WHERE farm_id='__legacy__' LIMIT 1").fetchone() is not None
        pairing = db.execute('SELECT 1 FROM auth_pairings WHERE expires_at>? LIMIT 1', (time.time(),)).fetchone() is not None
    return {'setup_required': empty, 'setup_enabled': empty and len(os.getenv('AGROPLAN_SETUP_TOKEN', '')) >= 32,
            'legacy_available': empty and legacy, 'pairing_available': pairing}


@router.post('/setup', status_code=201)
def setup_account(item: SetupAccount):
    import os
    import re
    username = item.username.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.@+-]{0,99}', username):
        raise HTTPException(422, 'Nome utente non valido.')
    expected = os.getenv('AGROPLAN_SETUP_TOKEN', '')
    if len(expected) < 32 or not secrets.compare_digest(item.setup_token.encode(), expected.encode()):
        raise HTTPException(403, 'Codice di attivazione non valido. Usa il collegamento generato all’avvio.')
    hashed = password_hash.hash(item.password)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM auth_users LIMIT 1').fetchone():
            raise HTTPException(409, 'Il primo account è già stato creato. Accedi con le tue credenziali.')
        db.execute('INSERT INTO auth_users(username,password_hash,farm_id) VALUES(?,?,?)',
                   (username, hashed, item.farm_id))
        if item.claim_legacy:
            db.execute("UPDATE agr_parcels SET farm_id=?,revision=0 WHERE farm_id='__legacy__'", (item.farm_id,))
    return {'username': username, 'farm_id': item.farm_id}
