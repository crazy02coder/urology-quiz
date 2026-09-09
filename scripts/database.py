"""python -m scripts.database backup|restore FILE"""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from app.config import Settings

def backup(source: Path, target: Path):
    if not source.exists():
        raise SystemExit(f'Kaynak bulunamadı: {source}')
    if target.exists():
        raise SystemExit('Hedef zaten var. Yeni bir dosya adı kullanın.')
    target.parent.mkdir(parents=True, exist_ok=True)
    # WAL readers may need writable sidecar files on a fresh/recovered database.
    # mode=rw never creates a missing source; the backup API only reads its data.
    with closing(sqlite3.connect(f'{source.as_uri()}?mode=rw', uri=True)) as src:
        if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Kaynak veritabanı bütünlük kontrolünü geçemedi.')
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            # A standalone backup must not depend on WAL/SHM sidecars.
            dst.execute('PRAGMA journal_mode=DELETE')
    target.chmod(0o600)

def main():
    parser = argparse.ArgumentParser(description='SQLite tutarlı yedekleme ve geri yükleme')
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('file', type=Path)
    parser.add_argument('--server-stopped', action='store_true', help='Geri yüklemeden önce uygulama durdurulmuş olmalı')
    args = parser.parse_args()
    db = Settings.from_env().database_path
    file = args.file.resolve()
    if args.action == 'backup':
        backup(db, file)
        print(f'Yedek oluşturuldu: {file}')
    else:
        if not args.server_stopped:
            parser.error('Sunucuyu durdurun ve --server-stopped ekleyin.')
        if not file.exists() or file == db:
            parser.error('Ayrı ve mevcut bir yedek dosyası seçin.')
        with closing(sqlite3.connect(f'{file.as_uri()}?mode=ro', uri=True)) as src:
            if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                parser.error('Yedek bütünlük kontrolünü geçemedi.')
            if not src.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone():
                parser.error('Dosya bu uygulamaya ait bir veritabanı değil.')
            if db.exists():
                from datetime import datetime, timezone
                recovery = db.with_name(f'exam-before-restore-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.db')
                backup(db, recovery)
                print(f'Geri dönüş yedeği: {recovery}')
            db.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(db)) as dst:
                src.backup(dst)
            db.chmod(0o600)
        print(f'Geri yüklendi: {db}. Uygulamayı yeniden başlatabilirsiniz.')

if __name__ == '__main__':
    main()
