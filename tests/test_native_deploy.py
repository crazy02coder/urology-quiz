import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from app.config import ROOT, Settings


def test_relative_database_path_does_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings('test', 'http://localhost:8000', 'sqlite:///./data/exam.db', False)
    assert settings.database_path == ROOT / 'data/exam.db'
    settings.database_url = 'sqlite:////data/exam.db'
    assert settings.database_path == Path('/data/exam.db')


def test_moved_project_native_uvicorn_entrypoint_and_render_url(tmp_path):
    project = tmp_path / 'renamed-project'
    project.mkdir()
    for directory in ('app', 'migrations'):
        shutil.copytree(ROOT / directory, project / directory, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'main.py', project / 'main.py')
    env = {**os.environ, 'ADMIN_PASSWORD': 'native-test-password', 'RENDER': 'true',
           'RENDER_EXTERNAL_URL': 'https://native-test.onrender.com', 'COOKIE_SECURE': 'true',
           'DATABASE_URL': 'sqlite:///./data/exam.db'}
    env.pop('PUBLIC_BASE_URL', None)
    command = [sys.executable, '-m', 'uvicorn', 'main:app', '--app-dir', str(project),
               '--host', '127.0.0.1', '--port', '8013', '--workers', '1']
    with (tmp_path / 'uvicorn.log').open('w') as log:
        process = subprocess.Popen(command, cwd=tmp_path, env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    if httpx.get('http://127.0.0.1:8013/healthz').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError((tmp_path / 'uvicorn.log').read_text())
            assert (project / 'data/exam.db').exists()
            assert not (tmp_path / 'data/exam.db').exists()
            assert httpx.get('http://127.0.0.1:8013/admin').status_code == 200
            assert httpx.get('http://127.0.0.1:8013/static/style.css').status_code == 200
            response = httpx.post('http://127.0.0.1:8013/api/login', json={'password': 'native-test-password'},
                                 headers={'Origin': env['RENDER_EXTERNAL_URL'], 'X-Requested-With': 'BilkentQuiz'})
            assert response.status_code == 200
            assert 'Secure' in response.headers['set-cookie']
        finally:
            process.terminate()
            process.wait(timeout=10)
