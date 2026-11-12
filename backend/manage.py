"""Offline administrator commands. Never pass passwords in command arguments."""
import argparse
from contextlib import closing
import getpass
import re
import sqlite3
from pathlib import Path

from auth import password_hash
from storage import DB, connect, initialize


def main():
    parser = argparse.ArgumentParser(description='Gestione AgroPlan')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create-user')
    create.add_argument('username')
    create.add_argument('--farm', required=True, help='Identificativo azienda; riutilizzarlo per condividere i dati')
    reset = commands.add_parser('set-password')
    reset.add_argument('username')
    disable = commands.add_parser('disable-user')
    disable.add_argument('username')
    claim = commands.add_parser('claim-legacy')
    claim.add_argument('--farm', required=True)
    backup = commands.add_parser('backup')
    backup.add_argument('destination', type=Path)
    args = parser.parse_args()
    initialize()
    if args.command in ('create-user', 'set-password'):
        username = args.username.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.@+-]{0,99}', username):
            parser.error('Nome utente non valido.')
        if args.command == 'create-user' and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}', args.farm):
            parser.error('Identificativo azienda non valido.')
        password = getpass.getpass('Password (almeno 12 caratteri): ')
        if len(password) < 12 or len(password) > 1024:
            parser.error('La password deve contenere da 12 a 1024 caratteri.')
        if password != getpass.getpass('Ripeti password: '):
            parser.error('Le password non coincidono.')
        hashed = password_hash.hash(password)
        with connect() as db:
            exists = db.execute('SELECT 1 FROM auth_users WHERE username=?', (username,)).fetchone()
            if args.command == 'create-user':
                if exists:
                    parser.error('Utente già presente. Usa set-password per cambiare la password.')
                db.execute('INSERT INTO auth_users(username,password_hash,farm_id) VALUES(?,?,?)',
                           (username, hashed, args.farm))
            else:
                if not exists:
                    parser.error('Utente non trovato.')
                db.execute('UPDATE auth_users SET password_hash=? WHERE username=?', (hashed, username))
                db.execute('DELETE FROM auth_sessions WHERE username=?', (username,))
        print('Account aggiornato.')
    elif args.command == 'disable-user':
        with connect() as db:
            if db.execute('UPDATE auth_users SET disabled=1 WHERE username=?', (args.username.strip().lower(),)).rowcount == 0:
                parser.error('Utente non trovato.')
            db.execute('DELETE FROM auth_sessions WHERE username=?', (args.username.strip().lower(),))
        print('Account disabilitato; sessioni revocate.')
    elif args.command == 'claim-legacy':
        with connect() as db:
            if not db.execute('SELECT 1 FROM auth_users WHERE farm_id=?', (args.farm,)).fetchone():
                parser.error('Crea prima un account per questa azienda.')
            count = db.execute("UPDATE agr_parcels SET farm_id=?,revision=0 WHERE farm_id='__legacy__'", (args.farm,)).rowcount
        print(f'{count} particelle precedenti assegnate. Importa ora i confini dalla copia locale.')
    elif args.command == 'backup':
        destination = args.destination.resolve()
        if destination == DB.resolve():
            parser.error('La destinazione non può coincidere con il database attivo.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids silently overwriting a previous backup.
        with destination.open('xb'):
            pass
        destination.chmod(0o600)
        try:
            with connect() as source, closing(sqlite3.connect(destination)) as target:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Verifica integrità backup fallita')
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        print(f'Backup verificato: {destination}')


if __name__ == '__main__':
    main()
