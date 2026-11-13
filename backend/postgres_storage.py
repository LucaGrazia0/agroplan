"""PostgreSQL connection exposing the small SQLite API used by AgroPlan."""
import re
import threading

_pools = {}
_pool_lock = threading.Lock()


class DatabaseUnavailable(RuntimeError):
    pass


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    if cursor.description is None:
        return lambda values: Row()
    names = [column.name for column in cursor.description]
    return lambda values: Row(zip(names, values))


class Cursor:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self): return self.cursor.fetchone()
    def fetchall(self): return self.cursor.fetchall()
    def __iter__(self): return iter(self.cursor)
    @property
    def rowcount(self): return self.cursor.rowcount


class Connection:
    def __init__(self, url):
        from psycopg_pool import ConnectionPool
        try:
            with _pool_lock:
                if url not in _pools:
                    _pools[url] = ConnectionPool(url, min_size=1, max_size=4, timeout=30,
                        kwargs={'row_factory':row_factory, 'connect_timeout':15},
                        check=ConnectionPool.check_connection)
                self.pool = _pools[url]
            self.raw = self.pool.getconn()
        except Exception:
            raise DatabaseUnavailable('Database temporaneamente non raggiungibile.') from None

    def execute(self, statement, parameters=()):
        sql = statement.strip()
        if sql.upper() == 'BEGIN IMMEDIATE':
            # Serialize ownership, revision and first-account decisions across
            # processes, preserving the existing SQLite transaction semantics.
            sql = 'LOCK TABLE agr_parcels, auth_users, auth_attempts IN SHARE ROW EXCLUSIVE MODE'
        if sql.startswith('INSERT OR IGNORE '):
            sql = sql.replace('INSERT OR IGNORE ', 'INSERT ', 1) + ' ON CONFLICT DO NOTHING'
        sql = sql.replace('?', '%s')
        returning = re.match(r'INSERT INTO (agr_bbch_observations|agr_soil_analyses)\b', sql, re.I)
        if returning:
            sql = sql.rstrip(';') + ' RETURNING id'
        cursor = self.raw.execute(sql, parameters)
        row = cursor.fetchone() if returning else None
        return Cursor(cursor, row['id'] if row else None)

    def executemany(self, statement, parameters):
        cursor = self.raw.cursor()
        cursor.executemany(statement.replace('?', '%s'), parameters)
        return Cursor(cursor)

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip():
                statement = statement.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
                statement = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', statement)
                self.execute(statement)

    def close(self): self.pool.putconn(self.raw)


def close_pool(url):
    pool = _pools.pop(url, None)
    if pool: pool.close()


def database_url():
    import os
    return os.getenv('DATABASE_URL', '').strip()
