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


def require_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)]):
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
    token = request.headers['authorization'].split(' ', 1)[1]
    with connect() as db:
        db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(token),))
