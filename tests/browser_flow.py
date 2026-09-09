"""Real Chromium / HTTP / WebSocket smoke test in an isolated temporary database.

Run: .venv/bin/python tests/browser_flow.py
Uses installed Chrome by default; set BROWSER_CHANNEL=chromium for Playwright's browser.
The first question waits a real 45 seconds; later deadlines are advanced only in test DB.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
import io
import zxingcpp
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'test-results'
BASE='http://127.0.0.1:8011'

def main():
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bilkent-test-') as directory:
        db=Path(directory)/'exam.db'
        env={**os.environ,'ADMIN_PASSWORD':'browser-test-password','PUBLIC_BASE_URL':BASE,
             'DATABASE_URL':f'sqlite:///{db}','COOKIE_SECURE':'false'}
        with (OUT/'server.log').open('w') as log:
            proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8011'],cwd=ROOT,env=env,stdout=log,stderr=log)
            try:
                for _ in range(100):
                    try:
                        if httpx.get(BASE+'/healthz').status_code==200:break
                    except httpx.ConnectError:pass
                    time.sleep(.1)
                else:raise AssertionError('Test sunucusu açılmadı.')
                run_browser(db)
            finally:
                proc.terminate();proc.wait(timeout=10)

def run_browser(db):
    with sync_playwright() as pw:
        channel=os.getenv('BROWSER_CHANNEL','chrome')
        browser=pw.chromium.launch(channel=None if channel=='chromium' else channel,headless=True)
        admin_context=browser.new_context(viewport={'width':1440,'height':1000})
        phone_context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        second_context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        admin=admin_context.new_page();phone=phone_context.new_page();second=second_context.new_page()
        errors=[]
        for page in (admin,phone,second):
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('console',lambda msg:errors.append(msg.text) if msg.type=='error' and 'Content Security Policy' in msg.text else None)
        admin.goto(BASE+'/admin');admin.screenshot(path=str(OUT/'desktop-login.png'),full_page=True)
        admin.locator('#password').fill('browser-test-password');admin.get_by_role('button',name='Giriş yap').click()
        expect(admin.locator('#title')).to_be_visible()
        admin.locator('#title').fill('Üroloji asistanları · Vaka soruları')
        admin.locator('#file').set_input_files(str(ROOT/'tests/fixtures/uroloji.docx'))
        admin.get_by_role('button',name='Önizlemeyi aç').click()
        expect(admin.locator('.preview-question')).to_have_count(10)
        assert 'Doğru cevap' in admin.locator('#preview').inner_text()
        admin.get_by_role('button',name='Sınavı kaydet').click()
        expect(admin.locator('.exam-row')).to_have_count(1)
        admin.screenshot(path=str(OUT/'desktop-dashboard.png'),full_page=True)
        admin.get_by_role('button',name='Canlı oturum oluştur').click()
        expect(admin.locator('#join-url')).to_be_visible()
        join_url=admin.locator('#join-url').input_value();sid=join_url.split('/')[-1]
        # The QR is requested from this same app and the embedded link is authoritative.
        qr=admin_context.request.get(BASE+f'/api/admin/sessions/{sid}/qr.png')
        assert qr.status==200 and qr.body().startswith(b'\x89PNG')
        decoded=zxingcpp.read_barcode(Image.open(io.BytesIO(qr.body())))
        assert decoded and decoded.text==join_url
        join_url=decoded.text
        (OUT/'qr.png').write_bytes(qr.body())
        phone.goto(join_url);phone.locator('#nickname').fill('kizilbaris');phone.get_by_role('button',name='Oturuma katıl').click()
        expect(phone.get_by_role('heading',name='Yöneticinin başlatması bekleniyor')).to_be_visible()
        phone.emulate_media(reduced_motion='reduce')
        assert phone.locator('.waiting-dot').evaluate("el=>getComputedStyle(el).animationName")=='none'
        phone.emulate_media(reduced_motion='no-preference')
        second.goto(join_url);second.locator('#nickname').fill('KIZILBARIS');second.get_by_role('button',name='Oturuma katıl').click()
        expect(second.locator('#error')).to_contain_text('kullanımda')
        second.locator('#nickname').fill('mavi');second.get_by_role('button',name='Oturuma katıl').click()
        expect(admin.locator('.name-chip')).to_have_count(2)
        admin.screenshot(path=str(OUT/'desktop-lobby.png'),full_page=True)
        phone.screenshot(path=str(OUT/'mobile-lobby.png'),full_page=True)
        start=time.monotonic();admin.get_by_role('button',name='Başlat',exact=False).click()
        expect(phone.locator('[data-choice]')).to_have_count(4)
        expect(second.locator('[data-choice]')).to_have_count(4)
        state1=phone_context.request.get(BASE+f'/api/sessions/{sid}').json()
        state2=second_context.request.get(BASE+f'/api/sessions/{sid}').json()
        assert state1['deadline']==state2['deadline']
        assert all(field not in state1['question'] for field in ['correct','explanation','hint'])
        assert 43<int(phone.locator('#timer').inner_text())<=45
        assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
        phone.screenshot(path=str(OUT/'mobile-question.png'),full_page=True)
        phone.locator('[data-choice="1"]').click()
        expect(phone.locator('.answer-status')).to_contain_text('Cevabın kaydedildi')
        phone.reload();expect(phone.locator('.answer-status')).to_contain_text('Cevabın kaydedildi')
        assert phone.locator('[data-choice="0"]').is_disabled()
        second_context.set_offline(True)
        expect(second.locator('#connection')).to_contain_text('kesildi',timeout=9000)
        second_context.set_offline(False)
        expect(second.locator('#connection')).to_contain_text('Canlı bağlantı',timeout=15000)
        second.locator('[data-choice="0"]').click()
        expect(second.locator('.answer-status')).to_contain_text('Cevabın kaydedildi')
        assert admin.locator('[data-control="next"]').count()==0
        assert phone.locator('.distribution').count()==0
        print('PASS: DOCX upload, preview, save, QR, duplicate nickname, simultaneous start, answer lock, refresh and reconnect.',flush=True)
        expect(phone.locator('.distribution')).to_be_visible(timeout=50000)
        elapsed=time.monotonic()-start
        assert elapsed>=44.9,elapsed
        assert phone.locator('.chart-column strong').all_text_contents()==['1','1','0','0']
        expect(phone.locator('.correct')).to_have_count(1);expect(phone.locator('.incorrect')).to_have_count(3)
        assert phone.locator('[data-control]').count()==0
        late=phone_context.request.post(BASE+f'/api/sessions/{sid}/answers',data={'question_id':state1['question']['id'],'choice':1},headers={'Origin':BASE,'X-Requested-With':'BilkentQuiz'})
        assert late.status==409
        phone.screenshot(path=str(OUT/'mobile-results.png'),full_page=True)
        admin.screenshot(path=str(OUT/'desktop-results.png'),full_page=True)
        question_id=state1['question']['id'];phone.wait_for_timeout(1200)
        assert phone_context.request.get(BASE+f'/api/sessions/{sid}').json()['question']['id']==question_id
        print(f'PASS: real 45-second deadline ({elapsed:.2f}s), late answer rejection, red/green results, distribution and administrator-controlled wait.',flush=True)
        for index in range(1,10):
            admin.get_by_role('button',name='Sonraki soru').click()
            expect(phone.locator('.question-meta')).to_contain_text(f'SORU {index+1} / 10')
            assert phone_context.request.get(BASE+f'/api/sessions/{sid}').json()['phase']=='question'
            with sqlite3.connect(db) as conn:conn.execute('UPDATE sessions SET deadline=? WHERE id=?',(time.time()-.1,sid))
            expect(admin.locator('.distribution')).to_be_visible()
        admin.get_by_role('button',name='Oturumu bitir').click()
        expect(phone.locator('.summary')).to_be_visible()
        assert phone.locator('.summary strong').all_text_contents()==['1','0','9']
        assert second.locator('.summary strong').all_text_contents()==['0','1','9']
        phone.screenshot(path=str(OUT/'mobile-completed.png'),full_page=True)
        admin.get_by_role('button',name='Cevap kayıtlarını göster').click()
        expect(admin.locator('tbody tr')).to_have_count(2)
        phone.emulate_media(reduced_motion='reduce')
        assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
        # Narrow view and 200% text enlargement remain usable.
        phone.set_viewport_size({'width':320,'height':740})
        phone.evaluate("document.documentElement.style.fontSize='200%'")
        assert phone.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        print('PASS: all 10 questions, final personal counts, admin history, mobile width and reduced motion. No JavaScript/CSP errors.',flush=True)
        browser.close()

if __name__=='__main__':main()
