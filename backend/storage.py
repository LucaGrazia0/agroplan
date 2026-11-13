"""SQLite storage shared by HTTP handlers and maintenance commands."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))
DB = Path(os.getenv('AGROPLAN_DB_PATH', str(Path(__file__).with_name('agroplan.db'))))


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def backup_before_first_migration():
    if not DB.is_file():
        return
    from contextlib import closing
    from datetime import datetime, timezone
    with closing(sqlite3.connect(DB)) as source:
        if source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_users'").fetchone():
            return
        directory = DB.parent / 'backups'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        destination = directory / f'pre-accessi-{stamp}.sqlite'
        with destination.open('xb'):
            pass
        destination.chmod(0o600)
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup precedente alla migrazione non valido.')


def initialize():
    backup_before_first_migration()
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS agr_crop_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT, parcel_id TEXT NOT NULL,
                season TEXT NOT NULL, crop TEXT NOT NULL, variety TEXT,
                sowing_date TEXT, UNIQUE(parcel_id, season));
            CREATE TABLE IF NOT EXISTS agr_bbch_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER NOT NULL,
                observed_at TEXT NOT NULL, bbch INTEGER NOT NULL CHECK(bbch BETWEEN 0 AND 99),
                notes TEXT, FOREIGN KEY(cycle_id) REFERENCES agr_crop_cycles(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS agr_soil_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, parcel_id TEXT NOT NULL,
                sample_date TEXT NOT NULL, source TEXT NOT NULL,
                ph REAL, nitrogen_g_kg REAL, sand_percent REAL, silt_percent REAL,
                clay_percent REAL, phosphorus_mg_kg REAL, potassium_mg_kg REAL, notes TEXT);
            CREATE TABLE IF NOT EXISTS auth_users (
                username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
                farm_id TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY(username) REFERENCES auth_users(username) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS auth_attempts (
                username TEXT PRIMARY KEY, failures INTEGER NOT NULL, blocked_until REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS agr_parcels (
                id TEXT PRIMARY KEY, farm_id TEXT NOT NULL,
                payload TEXT, revision INTEGER NOT NULL DEFAULT 1,
                deleted INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS idx_parcels_farm ON agr_parcels(farm_id);
            CREATE INDEX IF NOT EXISTS idx_bbch_cycle_date ON agr_bbch_observations(cycle_id, observed_at);
            CREATE INDEX IF NOT EXISTS idx_soil_parcel_date ON agr_soil_analyses(parcel_id, sample_date);
        ''')
        columns = {r[1] for r in db.execute('PRAGMA table_info(agr_soil_analyses)')}
        if 'client_id' not in columns:
            db.execute('ALTER TABLE agr_soil_analyses ADD COLUMN client_id TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_soil_idempotency ON agr_soil_analyses(parcel_id,client_id)')
        # Reserve all pre-authentication records. A new account cannot claim old
        # agronomic data just by submitting a known parcel ID.
        db.execute('''INSERT OR IGNORE INTO agr_parcels(id, farm_id)
            SELECT parcel_id, '__legacy__' FROM agr_crop_cycles
            UNION SELECT parcel_id, '__legacy__' FROM agr_soil_analyses''')

    DB.chmod(0o600)
