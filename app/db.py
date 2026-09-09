import sqlite3
from contextlib import contextmanager
from .config import ROOT

class Database:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def migrate(self):
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)')
        for file in sorted((ROOT / 'migrations').glob('*.sql')):
            with self.transaction() as conn:
                if conn.execute('SELECT 1 FROM schema_migrations WHERE name=?', (file.name,)).fetchone():
                    continue
                # Each migration and its receipt commit together; never executescript's implicit commit.
                statement = ''
                for line in file.read_text().splitlines(True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        conn.execute(statement)
                        statement = ''
                if statement.strip():
                    raise RuntimeError(f'Eksik SQL: {file.name}')
                conn.execute('INSERT INTO schema_migrations VALUES (?)', (file.name,))
