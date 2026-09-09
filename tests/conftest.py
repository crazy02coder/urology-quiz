import secrets
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app import importer

ORIGIN = 'http://testserver'
HEADERS = {'Origin':ORIGIN,'X-Requested-With':'BilkentQuiz'}

@pytest.fixture
def setup(tmp_path):
    settings = Settings('test-password',ORIGIN,f'sqlite:///{tmp_path}/exam.db',False)
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN) as admin:
        admin.headers.update(HEADERS)
        assert admin.post('/api/login',json={'password':'test-password'}).status_code == 200
        admin.headers['X-CSRF-Token'] = admin.get('/api/admin/me').json()['csrf']
        yield app, admin, settings

def seed(app, admin, options=(2,3,4,5)):
    from app.game import digest
    questions = [{'text':f'Test sorusu {i+1}', 'options':[f'Seçenek {n+1}' for n in range(count)], 'correct':i%count} for i,count in enumerate(options)]
    preview = importer.create_preview(app.state.db,digest(admin.cookies.get('admin_session')),'Test eğitimi',questions)
    exam = admin.post('/api/admin/exams',json={'preview_id':preview['preview_id']}).json()['exam_id']
    session = admin.post(f'/api/admin/exams/{exam}/sessions',json={'request_id':secrets.token_urlsafe(24)}).json()['session_id']
    return exam, session, preview

def participant(app, sid, nickname):
    client=TestClient(app,base_url=ORIGIN,headers=HEADERS)
    response=client.post(f'/api/sessions/{sid}/join',json={'nickname':nickname})
    assert response.status_code==200, response.text
    return client
