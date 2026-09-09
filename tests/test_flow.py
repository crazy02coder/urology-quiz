import io
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from app import game, importer
from app.main import create_app
from conftest import HEADERS, ORIGIN, participant, seed

def get_state(client,sid,admin=False):
    return client.get(f'/api/{"admin/" if admin else ""}sessions/{sid}').json()

def control(admin,sid,action,version=None):
    if version is None: version=get_state(admin,sid,True)['version']
    return admin.post(f'/api/admin/sessions/{sid}/control',json={'action':action,'expected_version':version})

def expire(app,sid):
    with app.state.db.transaction() as conn:
        conn.execute('UPDATE sessions SET deadline=? WHERE id=?',(time.time()-.01,sid))

def test_atomic_preview_and_repeated_save(setup):
    app,admin,_=setup
    exam,sid,preview=seed(app,admin)
    assert len(admin.get('/api/admin/exams').json())==1
    assert admin.post('/api/admin/exams',json={'preview_id':preview['preview_id']}).json()['exam_id']==exam
    assert [len(q['options']) for q in preview['questions']]==[2,3,4,5]
    assert control(admin,sid,'start').status_code==200

@pytest.mark.parametrize('bad',[
    {'text':' ', 'options':['A','B'],'correct':0,'source_line':8},
    {'text':'Q', 'options':['A',''],'correct':0,'source_line':8},
    {'text':'Q', 'options':['A','B'],'correct':4,'source_line':8},
    {'text':'Q', 'options':['A'],'correct':0,'source_line':8},
    {'text':'Q', 'options':['A']*6,'correct':0,'source_line':8},
    {'text':'Q', 'options':['A','B'],'correct':[0,1],'source_line':8},
])
def test_validation_no_partial_save(setup,bad):
    app,admin,_=setup
    with pytest.raises(HTTPException) as error:
        importer.create_preview(app.state.db,'owner','Başlık',[{'text':'OK','options':['A','B'],'correct':0},bad])
    assert 'Soru 2 (satır 8)' in str(error.value.detail)
    assert admin.get('/api/admin/exams').json()==[]
    with app.state.db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM previews').fetchone()[0]==0

def test_upload_limit_and_file_type(setup):
    _,admin,_=setup
    assert admin.get('/api/admin/imports/status').json()['extensions']==['.docx']
    assert admin.post('/api/admin/imports/preview',content=b'anything',headers={'X-Filename':'x.exe'}).status_code==415
    assert admin.post('/api/admin/imports/preview',content=b'anything',headers={'X-Filename':'x.docx'}).status_code==422
    assert admin.post('/api/admin/imports/preview',content=b'x'*(5*1024*1024+1)).status_code==413
    assert admin.post('/api/admin/exams',json={'preview_id':'fake'}).status_code==404

def test_login_access_csrf_logout_and_rate_limit(setup):
    app,admin,_=setup
    outsider=TestClient(app,base_url=ORIGIN,headers=HEADERS)
    assert outsider.get('/api/admin/exams').status_code==401
    assert outsider.get('/static/admin.html').status_code==404
    assert admin.post('/api/admin/logout',json={},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert admin.post('/api/admin/logout',json={},headers={'Origin':'https://evil.test'}).status_code==403
    assert admin.post('/api/admin/logout',json={}).status_code==200
    assert admin.get('/api/admin/me').status_code==401
    for _ in range(5):
        assert outsider.post('/api/login',json={'password':'bad'}).status_code==401
    assert outsider.post('/api/login',json={'password':'test-password'}).status_code==429

def test_nicknames_cookie_identity_and_isolation(setup):
    app,admin,_=setup
    exam,sid,_=seed(app,admin)
    p=participant(app,sid,'  KizilBaris  ')
    assert get_state(p,sid)['nickname']=='KizilBaris'
    other=TestClient(app,base_url=ORIGIN,headers=HEADERS)
    assert other.post(f'/api/sessions/{sid}/join',json={'nickname':'kizilbaris'}).status_code==409
    sid2=admin.post(f'/api/admin/exams/{exam}/sessions',json={'request_id':secrets.token_urlsafe(24)}).json()['session_id']
    participant(app,sid2,'kizilbaris')
    assert get_state(p,sid2)['joined'] is False
    assert p.get('/api/admin/sessions').status_code==401
    assert p.post(f'/api/admin/sessions/{sid}/control',json={'action':'start','expected_version':0}).status_code==401
    control(admin,sid,'start')
    assert other.post(f'/api/sessions/{sid}/join',json={'nickname':'yeni'}).status_code==409
    assert p.post(f'/api/sessions/{sid}/join',json={'nickname':'KizilBaris'}).status_code==200
    assert get_state(p,sid)['joined'] is True

def test_turkish_case_equivalence(setup):
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    participant(app,sid,'ışık')
    other=TestClient(app,base_url=ORIGIN,headers=HEADERS)
    assert other.post(f'/api/sessions/{sid}/join',json={'nickname':'IŞIK'}).status_code==409
    participant(app,sid,'İPEK')
    assert other.post(f'/api/sessions/{sid}/join',json={'nickname':'ipek'}).status_code==409

def test_live_flow_two_participants_no_early_leak_and_results(setup):
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    p1,p2=participant(app,sid,'bir'),participant(app,sid,'iki')
    with p1.websocket_connect(f'/ws/participant/{sid}',headers={'Origin':ORIGIN}) as ws1, p2.websocket_connect(f'/ws/participant/{sid}',headers={'Origin':ORIGIN}) as ws2:
        assert ws1.receive_json()['phase']=='lobby'
        assert ws2.receive_json()['phase']=='lobby'
        result=control(admin,sid,'start'); assert result.status_code==200
        def wait_question(ws):
            for _ in range(10):
                state=ws.receive_json()
                if state['phase']=='question':return state
            pytest.fail('Soru gelmedi')
        a,b=wait_question(ws1),wait_question(ws2)
        assert a['question']['id']==b['question']['id']
        assert a['deadline']==b['deadline']
        assert 44 < a['remaining_seconds'] <= 45
        for state in (a,b):
            assert 'correct' not in state['question']
            assert 'distribution' not in state and 'participants' not in state
        qid=a['question']['id']
        assert p1.post(f'/api/sessions/{sid}/answers',json={'question_id':qid,'choice':0}).status_code==200
        assert p2.post(f'/api/sessions/{sid}/answers',json={'question_id':qid,'choice':1}).status_code==200
        assert get_state(p1,sid)['phase']=='question' # all answered: still full time
        assert control(admin,sid,'next').status_code==409
        assert admin.get(f'/api/admin/sessions/{sid}/history').status_code==409
        expire(app,sid)
        assert p1.post(f'/api/sessions/{sid}/answers',json={'question_id':qid,'choice':0}).status_code==409
        state=get_state(p1,sid)
        assert state['phase']=='results' and state['question']['correct']==0
        assert state['distribution']==[1,1] and state['unanswered']==0
        assert get_state(p2,sid)['phase']=='results'
        assert control(admin,sid,'next').status_code==200
        next_state=get_state(p1,sid)
        assert next_state['question_index']==1 and 44<next_state['remaining_seconds']<=45
        assert p1.post(f'/api/sessions/{sid}/answers',json={'question_id':qid,'choice':0}).status_code==409

def test_concurrent_answers_and_double_control(setup):
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    p=participant(app,sid,'isim')
    assert control(admin,sid,'start',0).status_code==200
    assert control(admin,sid,'start',0).status_code==409
    qid=get_state(p,sid)['question']['id']
    def send(choice):return p.post(f'/api/sessions/{sid}/answers',json={'question_id':qid,'choice':choice}).status_code
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(send,[0,0]))==[200,200]
    assert send(1)==409
    with app.state.db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM answers').fetchone()[0]==1
    expire(app,sid)
    version=get_state(admin,sid,True)['version']
    assert control(admin,sid,'next',version).status_code==200
    assert control(admin,sid,'next',version).status_code==409
    assert get_state(p,sid)['question_index']==1

def test_wrong_session_choice_rejected(setup):
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    _,sid2,_=seed(app,admin)
    p=participant(app,sid,'katilimci'); p2=participant(app,sid2,'katilimci')
    control(admin,sid,'start'); control(admin,sid2,'start')
    qid=get_state(p,sid)['question']['id']; qid2=get_state(p2,sid2)['question']['id']
    assert p.post(f'/api/sessions/{sid2}/answers',json={'question_id':qid2,'choice':0}).status_code==401
    assert p.post(f'/api/sessions/{sid}/answers',json={'question_id':qid2,'choice':0}).status_code==409
    for choice in [-1,2,True,'0']:
        assert p.post(f'/api/sessions/{sid}/answers',json={'question_id':qid,'choice':choice}).status_code==422

def test_finish_summary_history_and_blank(setup):
    app,admin,_=setup
    _,sid,_=seed(app,admin,options=(2,3,4))
    p=participant(app,sid,'kisinin_adi')
    control(admin,sid,'start')
    for index,choice in enumerate([0,0,None]):
        state=get_state(p,sid)
        if choice is not None:p.post(f'/api/sessions/{sid}/answers',json={'question_id':state['question']['id'],'choice':choice})
        expire(app,sid)
        state=get_state(p,sid)
        assert state['unanswered']==(1 if choice is None else 0)
        if index<2:assert control(admin,sid,'next').status_code==200
    assert control(admin,sid,'finish').status_code==200
    assert get_state(p,sid)['summary']=={'correct':1,'wrong':1,'blank':1}
    history=admin.get(f'/api/admin/sessions/{sid}/history').json()
    assert len(history['participants'][0]['answers'])==2
    assert len(history['questions'])==3

def test_restart_persists_remaining_and_expiration(setup):
    app,admin,settings=setup
    _,sid,_=seed(app,admin)
    p=participant(app,sid,'yenileme'); control(admin,sid,'start')
    before=get_state(p,sid)
    with TestClient(create_app(settings),base_url=ORIGIN) as restarted:
        restarted.cookies.update(p.cookies)
        after=get_state(restarted,sid)
        assert after['deadline']==before['deadline']
        assert after['remaining_seconds']<=before['remaining_seconds']
        assert after['nickname']=='yenileme'
        expire(app,sid)
        assert get_state(restarted,sid)['phase']=='results'
        with restarted.websocket_connect(f'/ws/participant/{sid}',headers={'Origin':ORIGIN}) as ws:
            assert ws.receive_json()['phase']=='results'

def test_exact_45_second_boundary(setup,monkeypatch):
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    p=participant(app,sid,'sinir')
    now=time.time()+60
    clock=SimpleNamespace(time=lambda:now)
    monkeypatch.setattr(game,'time',clock)
    control(admin,sid,'start')
    state=get_state(p,sid); assert state['deadline']==now+45
    now+=44.999
    assert get_state(p,sid)['phase']=='question'
    now+=.001
    assert p.post(f'/api/sessions/{sid}/answers',json={'question_id':state['question']['id'],'choice':0}).status_code==409
    assert get_state(p,sid)['phase']=='results'

def test_qr_png_and_session_creation_idempotency(setup):
    app,admin,_=setup
    exam,sid,_=seed(app,admin)
    request_id=secrets.token_urlsafe(24)
    a=admin.post(f'/api/admin/exams/{exam}/sessions',json={'request_id':request_id}).json()
    b=admin.post(f'/api/admin/exams/{exam}/sessions',json={'request_id':request_id}).json()
    assert a==b and a['session_id']!=sid
    assert a['join_url']==f'{ORIGIN}/join/{a["session_id"]}'
    png=admin.get(f'/api/admin/sessions/{sid}/qr.png')
    assert png.status_code==200 and png.headers['content-type']=='image/png'
    im=Image.open(io.BytesIO(png.content)); assert im.width>=300

def test_websocket_auth_and_origin(setup):
    app,admin,_=setup
    _,sid,_=seed(app,admin)
    outsider=TestClient(app,base_url=ORIGIN)
    from starlette.websockets import WebSocketDisconnect
    for role,client,origin in [('admin',outsider,ORIGIN),('participant',outsider,ORIGIN),('admin',admin,'https://evil.test')]:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f'/ws/{role}/{sid}',headers={'Origin':origin}):pass
