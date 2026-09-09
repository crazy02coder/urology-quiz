import sqlite3
import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from conftest import HEADERS,ORIGIN,seed
from scripts.database import backup

def test_secure_cookie_flags(tmp_path):
    app=create_app(Settings('password','https://testserver',f'sqlite:///{tmp_path}/exam.db',True))
    with TestClient(app,base_url='https://testserver') as client:
        response=client.post('/api/login',json={'password':'password'},headers={'Origin':'https://testserver','X-Requested-With':'BilkentQuiz'})
        cookie=response.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        assert 'max-age=43200' in cookie
        assert client.get('/api/admin/me').status_code==200

def test_preview_belongs_to_creating_admin_session(setup):
    app,admin,_=setup
    _,_,preview=seed(app,admin)
    second=TestClient(app,base_url=ORIGIN,headers=HEADERS)
    second.post('/api/login',json={'password':'test-password'})
    second.headers['X-CSRF-Token']=second.get('/api/admin/me').json()['csrf']
    assert second.post('/api/admin/exams',json={'preview_id':preview['preview_id']}).status_code==404

def test_migrations_and_online_backup_restore(setup,tmp_path):
    app,admin,settings=setup
    exam,_,_=seed(app,admin)
    app.state.db.migrate();app.state.db.migrate()
    with app.state.db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==3
    file=tmp_path/'backup.db'
    backup(settings.database_path,file)
    with sqlite3.connect(file) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('SELECT id FROM exams').fetchone()[0]==exam
    # Restore into a separate stopped database through the actual maintenance command.
    import os
    target=tmp_path/'restored.db'
    env={**os.environ,'ADMIN_PASSWORD':'test-password','PUBLIC_BASE_URL':ORIGIN,'COOKIE_SECURE':'false','DATABASE_URL':f'sqlite:///{target}'}
    command=[sys.executable,'-m','scripts.database','restore',str(file),'--server-stopped']
    first=subprocess.run(command,env=env,capture_output=True,text=True)
    assert first.returncode==0,first.stderr
    second=subprocess.run(command,env=env,capture_output=True,text=True)
    assert second.returncode==0,second.stderr
    assert list(tmp_path.glob('exam-before-restore-*.db'))
    with sqlite3.connect(target) as conn:
        assert conn.execute('SELECT id FROM exams').fetchone()[0]==exam

def test_logout_revokes_open_websocket(setup):
    from starlette.websockets import WebSocketDisconnect
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    with admin.websocket_connect(f'/ws/admin/{sid}',headers={'Origin':ORIGIN}) as ws:
        assert ws.receive_json()['phase']=='lobby'
        assert admin.post('/api/admin/logout',json={}).status_code==200
        for _ in range(10):
            try:ws.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code==4401;break
        else:raise AssertionError('Çıkış socket yetkisini iptal etmedi.')
