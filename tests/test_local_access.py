import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from conftest import seed


@pytest.mark.parametrize('origin', ['http://localhost:8000', 'http://127.0.0.1:8000'])
def test_local_login_and_websocket_with_uvicorn_address(tmp_path, origin):
    settings = Settings('local-test', 'http://localhost:8000', f'sqlite:///{tmp_path}/exam.db', False)
    app = create_app(settings)
    with TestClient(app, base_url=origin, headers={'Origin': origin, 'X-Requested-With': 'BilkentQuiz'}) as client:
        assert client.post('/api/login', json={'password': 'local-test'}).status_code == 200
        client.headers['X-CSRF-Token'] = client.get('/api/admin/me').json()['csrf']
        _, sid, _ = seed(app, client)
        with client.websocket_connect(origin.replace('http://', 'ws://') + f'/ws/admin/{sid}', headers={'Origin': origin}) as ws:
            assert ws.receive_json()['phase'] == 'lobby'
        assert client.post('/api/admin/logout', json={}).status_code == 200


@pytest.mark.parametrize('origin', ['http://127.0.0.1:9000', 'https://localhost:8000', 'https://evil.test', 'null'])
def test_local_alias_does_not_allow_other_origins(tmp_path, origin):
    settings = Settings('local-test', 'http://localhost:8000', f'sqlite:///{tmp_path}/exam.db', False)
    with TestClient(create_app(settings)) as client:
        assert client.post('/api/login', json={'password': 'local-test'},
                           headers={'Origin': origin, 'X-Requested-With': 'BilkentQuiz'}).status_code == 403


def test_production_keeps_exact_origin():
    settings = Settings('test', 'https://quiz.onrender.com', 'sqlite:////data/exam.db', True)
    assert settings.allowed_origins == {'https://quiz.onrender.com'}
