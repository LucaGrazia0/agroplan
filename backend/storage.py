"""SQLite storage shared by HTTP handlers and maintenance commands."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from postgres_storage import database_url

load_dotenv(Path(__file__).with_name('.env'))
DB = Path(os.getenv('AGROPLAN_DB_PATH', str(Path(__file__).with_name('agroplan.db'))))


@contextmanager
def connect():
    if database_url():
        from postgres_storage import Connection
        conn = Connection(database_url())
        try:
            with conn.raw.transaction():
                yield conn
        finally:
            conn.close()
        return
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
    if database_url():
        return
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
        if not database_url():
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
            CREATE TABLE IF NOT EXISTS agr_satellite_observations (
                parcel_id TEXT NOT NULL, observed_at TEXT NOT NULL,
                mean REAL, valid_percent REAL, fetched_at TEXT NOT NULL,
                geometry_hash TEXT NOT NULL,
                PRIMARY KEY(parcel_id, observed_at));
            CREATE TABLE IF NOT EXISTS agr_field_observations (
                id TEXT PRIMARY KEY, parcel_id TEXT NOT NULL, observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_field_parcel ON agr_field_observations(parcel_id,observed_at);
            CREATE TABLE IF NOT EXISTS agr_analysis_results (
                id TEXT PRIMARY KEY, parcel_id TEXT NOT NULL, created_at TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_results_parcel ON agr_analysis_results(parcel_id,created_at);
            CREATE TABLE IF NOT EXISTS agr_analysis_parameters (
                parcel_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS agr_workspace_state (
                farm_id TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS agr_workspace_archives (
                id TEXT PRIMARY KEY, farm_id TEXT NOT NULL, created_at TEXT NOT NULL,
                payload TEXT NOT NULL, restored_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_workspace_archives ON agr_workspace_archives(farm_id,created_at);
            CREATE TABLE IF NOT EXISTS auth_pairings (
                code_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY(username) REFERENCES auth_users(username) ON DELETE CASCADE);
        ''')
        columns = ({r[0] for r in db.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='agr_soil_analyses'")}
                   if database_url() else {r[1] for r in db.execute('PRAGMA table_info(agr_soil_analyses)')})
        if 'client_id' not in columns:
            db.execute('ALTER TABLE agr_soil_analyses ADD COLUMN client_id TEXT')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_soil_idempotency ON agr_soil_analyses(parcel_id,client_id)')
        # Reserve all pre-authentication records. A new account cannot claim old
        # agronomic data just by submitting a known parcel ID.
        db.execute('''INSERT OR IGNORE INTO agr_parcels(id, farm_id)
            SELECT parcel_id, '__legacy__' FROM agr_crop_cycles
            UNION SELECT parcel_id, '__legacy__' FROM agr_soil_analyses''')

    if not database_url():
        DB.chmod(0o600)
