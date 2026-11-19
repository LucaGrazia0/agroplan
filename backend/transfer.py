"""Move a verified local SQLite snapshot into an empty PostgreSQL database."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import time

from auth import digest, password_hash
from postgres_storage import database_url
from storage import connect, initialize

TABLES = ('agr_parcels', 'agr_crop_cycles', 'agr_bbch_observations', 'agr_soil_analyses', 'agr_satellite_observations', 'agr_field_observations', 'agr_analysis_results')


def issue_pairing(username, destination):
    """The plaintext code is written only to a private owner-controlled file."""
    code = secrets.token_urlsafe(32)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM auth_users WHERE username=? AND disabled=0', (username,)).fetchone():
            raise ValueError('Account non disponibile.')
        db.execute('INSERT INTO auth_pairings VALUES(?,?,?)', (digest(code), username, time.time()+7*86400))
        with destination.open('x') as file:
            destination.chmod(0o600)
            file.write(code+'\n')


def migrate(source, farm, username, backup):
    if not database_url():
        raise ValueError('Configurare DATABASE_URL nel solo ambiente backend.')
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open('xb'):
        pass
    backup.chmod(0o600)
    with closing(sqlite3.connect(source)) as local, closing(sqlite3.connect(backup)) as snapshot:
        local.backup(snapshot)
        if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup locale non valido.')
    initialize()
    counts = {}
    with closing(sqlite3.connect(backup)) as local, connect() as remote:
        local.row_factory = sqlite3.Row
        remote.execute('BEGIN IMMEDIATE')
        for table in TABLES:
            if remote.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                raise ValueError('Destinazione con dati esistenti: nessuna sovrascrittura eseguita.')
        if remote.execute('SELECT 1 FROM auth_users LIMIT 1').fetchone():
            raise ValueError('La destinazione ha già account. Usare una migrazione esplicita.')
        # Login with passwords is unused for this owner. Only one-time pairing
        # can mint a device session; no plaintext password is generated or saved.
        remote.execute('INSERT INTO auth_users(username,password_hash,farm_id) VALUES(?,?,?)',
                       (username, password_hash.hash(secrets.token_urlsafe(64)), farm))
        available = {r[0] for r in local.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            rows = local.execute(f'SELECT * FROM {table}').fetchall() if table in available else []
            for row in rows:
                data = dict(row)
                if table == 'agr_parcels':
                    data['farm_id'] = farm
                columns = list(data)
                remote.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", list(data.values()))
            if table in ('agr_crop_cycles','agr_bbch_observations','agr_soil_analyses'):
                remote.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'),(SELECT coalesce(max(id),0)+1 FROM {table}),false)")
            counts[table] = len(rows)
    return counts


def export_backup(destination):
    initialize()
    with connect() as db:
        data = {table:[dict(row) for row in db.execute(f'SELECT * FROM {table}')]
                for table in (*TABLES,'auth_users','auth_sessions','auth_attempts','auth_pairings')}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as file:
        destination.chmod(0o600)
        json.dump({'format':'agroplan-backup-v1','created_at':datetime.now(timezone.utc).isoformat(),'tables':data},file,ensure_ascii=False,allow_nan=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    migration=commands.add_parser('migrate')
    migration.add_argument('--source',type=Path,required=True)
    migration.add_argument('--farm',required=True)
    migration.add_argument('--owner',required=True)
    migration.add_argument('--backup',type=Path,required=True)
    pairing=commands.add_parser('pair-device')
    pairing.add_argument('--owner',required=True)
    pairing.add_argument('--output',type=Path,required=True)
    backup=commands.add_parser('backup')
    backup.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='migrate': print(json.dumps(migrate(args.source,args.farm,args.owner,args.backup)))
    elif args.command=='pair-device':
        initialize();issue_pairing(args.owner,args.output);print('Codice salvato nel file locale riservato.')
    else:
        export_backup(args.output);print('Backup privato completato.')


if __name__=='__main__':
    main()
