"""Test the built Docker image using a disposable, isolated persistent volume."""
import subprocess
import time
import uuid
from pathlib import Path
import httpx
from websockets.sync.client import connect

def docker(*args):
    return subprocess.check_output(['docker',*args],text=True).strip()

def main():
    name='bilkent-smoke-'+uuid.uuid4().hex[:12]
    volume=name+'-data'
    base='http://127.0.0.1:8012'
    docker('volume','create',volume)
    try:
        docker('run','-d','--name',name,'-p','127.0.0.1:8012:10000','-v',volume+':/data',
               '-e','ADMIN_PASSWORD=docker-smoke-password','-e','PUBLIC_BASE_URL='+base,
               '-e','COOKIE_SECURE=false','-e','DATABASE_URL=sqlite:////data/exam.db',
               'bilkent-live-exam:local')
        def wait():
            for _ in range(100):
                try:
                    if httpx.get(base+'/healthz',timeout=1).status_code==200:return
                except httpx.HTTPError:pass
                time.sleep(.1)
            raise AssertionError('Docker sağlık kontrolü başarısız.')
        wait()
        headers={'Origin':base,'X-Requested-With':'BilkentQuiz'}
        with httpx.Client(base_url=base,headers=headers) as admin,httpx.Client(base_url=base,headers=headers) as p:
            admin.post('/api/login',json={'password':'docker-smoke-password'}).raise_for_status()
            admin.headers['X-CSRF-Token']=admin.get('/api/admin/me').json()['csrf']
            sample=Path(__file__).parent/'fixtures/uroloji.docx'
            response=admin.post('/api/admin/imports/preview',content=sample.read_bytes(),headers={'X-Filename':'test.docx','X-Exam-Title':'Docker smoke'})
            response.raise_for_status()
            preview=response.json()
            exam=admin.post('/api/admin/exams',json={'preview_id':preview['preview_id']}).json()['exam_id']
            sid=admin.post(f'/api/admin/exams/{exam}/sessions',json={'request_id':uuid.uuid4().hex}).json()['session_id']
            p.post(f'/api/sessions/{sid}/join',json={'nickname':'docker-katilimci'}).raise_for_status()
            admin.post(f'/api/admin/sessions/{sid}/control',json={'action':'start','expected_version':0}).raise_for_status()
            before=p.get(f'/api/sessions/{sid}').json()
            q=before['question']
            p.post(f'/api/sessions/{sid}/answers',json={'question_id':q['id'],'choice':1}).raise_for_status()
            docker('restart',name);wait()
            after=p.get(f'/api/sessions/{sid}').json()
            assert after['deadline']==before['deadline'] and after['own_choice']==1
            assert after['remaining_seconds']<before['remaining_seconds']
            assert admin.get('/api/admin/exams').json()[0]['question_count']==10
            cookie='; '.join(f'{key}={value}' for key,value in p.cookies.items())
            with connect(f'ws://127.0.0.1:8012/ws/participant/{sid}',origin=base,additional_headers={'Cookie':cookie}) as ws:
                import json
                state=json.loads(ws.recv(timeout=3))
                assert state['question']['id']==q['id'] and state['own_choice']==1
            docker('exec',name,'python','-m','scripts.database','backup','/data/smoke-backup.db')
            print('PASS: Docker /data, DOCX import, admin and participant cookies, persisted deadline/answer after restart, WebSocket reconnect, backup.')
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True)
        subprocess.run(['docker','volume','rm',volume],capture_output=True)

if __name__=='__main__':main()
