import asyncio
import hmac
import secrets
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, StrictInt

from .config import ROOT, Settings
from .db import Database
from . import accounts, game, importer, flexible_import, qr_card

class Login(BaseModel):
    password: str = Field(max_length=500)

class Join(BaseModel):
    nickname: str = Field(max_length=100)
    experience_years: StrictInt = Field(ge=0, le=game.MAX_EXPERIENCE_YEARS)

class Answer(BaseModel):
    question_id: str = Field(max_length=80)
    choice: StrictInt

class Control(BaseModel):
    action: str
    expected_version: int
    question_duration_seconds: StrictInt | None = Field(default=None, ge=5, le=300)

class Save(BaseModel):
    preview_id: str = Field(max_length=80)
    questions: list[dict] | None = Field(default=None, max_length=importer.MAX_QUESTIONS)
    review_confirmed: StrictBool = False

class PasswordChange(BaseModel):
    current_password: str = Field(max_length=500)
    new_password: str = Field(max_length=500)

class NewSession(BaseModel):
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

class BodyLimit:
    """Bound incoming bytes even with chunked transfer; reject before parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        limit = importer.MAX_FILE_BYTES if scope['path'] in ('/api/admin/imports/preview', '/api/admin/exams') else 32768
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            total += len(message.get('body', b''))
            if total > limit:
                return await JSONResponse({'detail': 'Dosya ve sınav kaydı en fazla 5 MB, diğer istekler en fazla 32 KB olabilir.'}, 413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body'):
                break
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        await self.app(scope, replay, send)

def create_app(settings=None):
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(app):
        db.migrate()
        async def deadlines():
            while True:
                with db.transaction() as conn:
                    conn.execute("UPDATE sessions SET phase='results',version=version+1 WHERE phase='question' AND deadline<=?", (time.time(),))
                await asyncio.sleep(.2)
        task = asyncio.create_task(deadlines())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title='Bilkent Şehir Hastanesi · ', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.settings = db, settings

    def admin_auth(cookies, csrf=None, mutation=False):
        token = cookies.get('admin_session', '')
        with db.connect() as conn:
            row = conn.execute('SELECT * FROM admin_sessions WHERE token_hash=? AND expires_at>?', (game.digest(token), time.time())).fetchone()
        if not row:
            raise HTTPException(401, 'Yönetici girişi gerekli.')
        if mutation and not hmac.compare_digest(row['csrf'], csrf or ''):
            raise HTTPException(403, 'Güvenlik doğrulaması başarısız. Sayfayı yenileyin.')
        return row

    @app.middleware('http')
    async def security(request, call_next):
        try:
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if request.headers.get('origin') not in settings.allowed_origins or request.headers.get('x-requested-with') != 'BilkentQuiz':
                    raise HTTPException(403, 'İstek kaynağı doğrulanamadı.')
            if request.url.path.startswith('/api/admin/'):
                request.state.admin = admin_auth(request.cookies, request.headers.get('x-csrf-token'), request.method != 'GET')
            response = await call_next(request)
        except HTTPException as exc:
            response = JSONResponse({'detail': exc.detail}, exc.status_code)
        response.headers.update({
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        })
        if settings.cookie_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    app.add_middleware(BodyLimit)
    app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')

    def html(name):
        return FileResponse(ROOT / 'app/templates' / name)

    @app.get('/healthz')
    def health():
        with db.connect() as conn:
            conn.execute('SELECT 1').fetchone()
        return {'ok': True}

    @app.get('/')
    def home():
        return html('home.html')

    @app.get('/admin')
    def admin_page(request: Request):
        try:
            admin_auth(request.cookies)
            return html('admin.html')
        except HTTPException:
            return html('login.html')

    @app.get('/admin/sessions/{sid}')
    def admin_session_page(sid: str, request: Request):
        try:
            admin_auth(request.cookies)
        except HTTPException:
            return RedirectResponse('/admin', 303)
        with db.connect() as conn:
            game.session_row(conn, sid)
        return html('session.html')

    @app.get('/join/{sid}')
    def join_page(sid: str):
        with db.connect() as conn:
            exists = conn.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone()
        if not exists:
            return FileResponse(ROOT / 'app/templates/invalid.html', status_code=404)
        return html('session.html')

    @app.post('/api/login')
    def login(data: Login, request: Request):
        client_key = game.digest(request.client.host if request.client else 'unknown')
        now = time.time()
        with db.transaction() as conn:
            conn.execute('DELETE FROM login_attempts WHERE window_start<?', (now - 900,))
            row = conn.execute('SELECT * FROM login_attempts WHERE client_key=?', (client_key,)).fetchone()
            if row and row['count'] >= 5:
                return JSONResponse({'detail': 'Çok fazla hatalı deneme. 15 dakika sonra yeniden deneyin.'}, 429, headers={'Retry-After': str(max(1, int(900 - now + row['window_start'])))})
            if not accounts.verify(conn, settings, data.password):
                conn.execute('INSERT INTO login_attempts(client_key,count,window_start) VALUES (?,1,?)'
                             ' ON CONFLICT(client_key) DO UPDATE SET count=count+1', (client_key, now))
                return JSONResponse({'detail': 'Şifre hatalı.'}, 401)
            conn.execute('DELETE FROM login_attempts WHERE client_key=?', (client_key,))
            conn.execute('DELETE FROM admin_sessions WHERE expires_at<=?', (now,))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            conn.execute('DELETE FROM admin_sessions WHERE token_hash=?', (game.digest(request.cookies.get('admin_session', '')),))
            conn.execute('INSERT INTO admin_sessions(token_hash,csrf,expires_at) VALUES (?,?,?)', (game.digest(token), csrf, now + 12 * 3600))
        response = JSONResponse({'ok': True})
        response.set_cookie('admin_session', token, max_age=43200, httponly=True, secure=settings.cookie_secure, samesite='strict', path='/')
        return response

    @app.get('/api/admin/account')
    def account():
        with db.connect() as conn:
            return {'username': accounts.username(conn)}

    @app.post('/api/admin/password')
    def change_password(data: PasswordChange, request: Request):
        problems = accounts.password_problems(data.new_password)
        if problems:
            raise HTTPException(422, problems)
        with db.transaction() as conn:
            if not accounts.verify(conn, settings, data.current_password):
                raise HTTPException(403, 'Mevcut şifre hatalı.')
            if accounts.verify(conn, settings, data.new_password):
                raise HTTPException(422, 'Yeni şifre mevcut şifreyle aynı olamaz.')
            accounts.set_password(conn, data.new_password)
            # Şifre değişince diğer cihazlardaki yönetici oturumları kapanır.
            conn.execute('DELETE FROM admin_sessions WHERE token_hash<>?', (request.state.admin['token_hash'],))
        return {'ok': True}

    @app.get('/api/admin/me')
    def me(request: Request):
        return {'csrf': request.state.admin['csrf']}

    @app.post('/api/admin/logout')
    def logout(request: Request):
        with db.transaction() as conn:
            conn.execute('DELETE FROM admin_sessions WHERE token_hash=?', (request.state.admin['token_hash'],))
        response = JSONResponse({'ok': True})
        response.delete_cookie('admin_session', path='/', secure=settings.cookie_secure, httponly=True, samesite='strict')
        return response

    @app.get('/api/admin/exams')
    def exams():
        with db.connect() as conn:
            return [dict(r) for r in conn.execute('SELECT e.*,COUNT(q.id) AS question_count FROM exams e'
                                                 ' LEFT JOIN questions q ON q.exam_id=e.id'
                                                 ' WHERE e.archived_at IS NULL GROUP BY e.id ORDER BY e.created_at DESC')]

    @app.delete('/api/admin/exams/{exam_id}')
    def delete_exam(exam_id: str):
        """Oturum geçmişi olan sınav arşivlenir; sonuçlar ve kayıtlar korunur."""
        with db.transaction() as conn:
            exam = conn.execute('SELECT title,archived_at FROM exams WHERE id=?', (exam_id,)).fetchone()
            if not exam or exam['archived_at'] is not None:
                raise HTTPException(404, 'Kayıtlı sınav bulunamadı.')
            sessions = conn.execute('SELECT COUNT(*) FROM sessions WHERE exam_id=?', (exam_id,)).fetchone()[0]
            if sessions:
                conn.execute('UPDATE exams SET archived_at=? WHERE id=?', (time.time(), exam_id))
                return {'deleted': True, 'archived': True, 'sessions': sessions}
            conn.execute('DELETE FROM previews WHERE exam_id=?', (exam_id,))
            conn.execute('DELETE FROM questions WHERE exam_id=?', (exam_id,))
            conn.execute('DELETE FROM exams WHERE id=?', (exam_id,))
        return {'deleted': True, 'archived': False, 'sessions': 0}

    @app.get('/api/admin/imports/status')
    def import_status():
        return {'enabled': bool(importer.ALLOWED_EXTENSIONS), 'extensions': sorted(importer.ALLOWED_EXTENSIONS), 'max_bytes': importer.MAX_FILE_BYTES}

    @app.post('/api/admin/imports/preview')
    async def preview(request: Request):
        filename = unquote(request.headers.get('x-filename', ''))
        if not importer.ALLOWED_EXTENSIONS:
            importer.parse_file(filename, b'')
        if Path(filename).suffix.lower() not in importer.ALLOWED_EXTENSIONS:
            raise HTTPException(415, 'Bu dosya türü desteklenmiyor.')
        content = await request.body()
        extraction = await asyncio.to_thread(flexible_import.extract, filename, content)
        return importer.create_review_preview(db, request.state.admin['token_hash'], unquote(request.headers.get('x-exam-title', '')), extraction)

    @app.post('/api/admin/exams')
    def save(data: Save, request: Request):
        return {'exam_id': importer.save_preview(db, request.state.admin['token_hash'], data.preview_id, data.questions, data.review_confirmed)}

    @app.post('/api/admin/exams/{exam_id}/sessions')
    def new_session(exam_id: str, data: NewSession):
        with db.transaction() as conn:
            if not conn.execute('SELECT 1 FROM questions WHERE exam_id=?', (exam_id,)).fetchone():
                raise HTTPException(404, 'Kayıtlı sınav bulunamadı.')
            # Random browser request ID makes retries idempotent; server owns the join ID.
            previous = conn.execute('SELECT session_id FROM session_requests WHERE request_id=? AND exam_id=?', (data.request_id, exam_id)).fetchone()
            if previous:
                sid = previous['session_id']
            else:
                sid = secrets.token_urlsafe(24)
                conn.execute('INSERT INTO sessions(id,exam_id,created_at) VALUES (?,?,?)', (sid, exam_id, time.time()))
                conn.execute('INSERT INTO session_requests(request_id,exam_id,session_id) VALUES (?,?,?)', (data.request_id, exam_id, sid))
        return {'session_id': sid, 'join_url': f'{settings.public_base_url}/join/{sid}'}

    @app.get('/api/admin/sessions')
    def sessions():
        with db.connect() as conn:
            return [dict(r) for r in conn.execute('SELECT s.*,e.title,(SELECT COUNT(*) FROM participants p WHERE p.session_id=s.id) AS participant_count FROM sessions s JOIN exams e ON e.id=s.exam_id ORDER BY s.created_at DESC')]

    @app.get('/api/admin/sessions/{sid}')
    def admin_state(sid: str):
        result = game.state(db, sid, admin=True)
        result['join_url'] = f'{settings.public_base_url}/join/{sid}'
        return result

    @app.get('/api/admin/sessions/{sid}/qr.png')
    def qr(sid: str):
        with db.connect() as conn:
            game.session_row(conn, sid)
        image = qr_card.render(f'{settings.public_base_url}/join/{sid}')
        return Response(image, media_type='image/png', headers={'Content-Disposition': f'inline; filename="bilkent-{sid}.png"'})

    @app.post('/api/admin/sessions/{sid}/control')
    def control(sid: str, data: Control):
        game.advance(db, sid, data.action, data.expected_version, data.question_duration_seconds)
        return game.state(db, sid, admin=True)

    @app.get('/api/admin/sessions/{sid}/history')
    def history(sid: str):
        return game.history(db, sid)

    @app.get('/api/admin/sessions/{sid}/stats')
    def stats(sid: str):
        return game.statistics(db, sid)

    @app.delete('/api/admin/sessions/{sid}')
    def delete_session(sid: str):
        with db.transaction() as conn:
            if not conn.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone():
                raise HTTPException(404, 'Oturum bulunamadı.')
            conn.execute('DELETE FROM answers WHERE session_id=?', (sid,))
            conn.execute('DELETE FROM participants WHERE session_id=?', (sid,))
            conn.execute('DELETE FROM session_requests WHERE session_id=?', (sid,))
            conn.execute('DELETE FROM sessions WHERE id=?', (sid,))
        return {'deleted': True}

    @app.get('/api/sessions/{sid}')
    def public_state(sid: str, request: Request):
        return game.state(db, sid, request.cookies.get(game.participant_cookie(sid)))

    @app.post('/api/sessions/{sid}/join')
    def participant_join(sid: str, data: Join, request: Request):
        token = game.join(db, sid, data.nickname, data.experience_years, request.cookies.get(game.participant_cookie(sid)))
        response = JSONResponse({'joined': True})
        response.set_cookie(game.participant_cookie(sid), token, max_age=7*86400, httponly=True,
                            secure=settings.cookie_secure, samesite='strict', path='/')
        return response

    @app.get('/api/sessions/{sid}/questions/{index}')
    def past_question(sid: str, index: int, request: Request):
        # Yönetici de katılımcı da açılmış soruları geriye dönük inceleyebilir.
        try:
            admin_auth(request.cookies)
            admin = True
        except HTTPException:
            admin = False
        return game.past_question(db, sid, index, request.cookies.get(game.participant_cookie(sid)), admin)

    @app.get('/api/sessions/{sid}/review')
    def participant_review(sid: str, request: Request):
        return game.review(db, sid, request.cookies.get(game.participant_cookie(sid)))

    @app.get('/api/sessions/{sid}/images/{image_id}')
    def question_image(sid: str, image_id: str, request: Request):
        try:
            admin_auth(request.cookies)
            admin = True
        except HTTPException:
            admin = False
        data, mime = game.image_content(db, sid, image_id, request.cookies.get(game.participant_cookie(sid)), admin)
        return Response(content=data, media_type=mime)

    @app.post('/api/sessions/{sid}/answers')
    def submit_answer(sid: str, data: Answer, request: Request):
        return game.answer(db, sid, request.cookies.get(game.participant_cookie(sid)), data.question_id, data.choice)

    @app.websocket('/ws/{role}/{sid}')
    async def live(ws: WebSocket, role: str, sid: str):
        if ws.headers.get('origin') not in settings.allowed_origins or role not in ('admin', 'participant'):
            await ws.close(code=4403); return
        admin = role == 'admin'
        token = ws.cookies.get(game.participant_cookie(sid))
        try:
            if admin:
                admin_auth(ws.cookies)
            initial = game.state(db, sid, token, admin)
            if not admin and not initial['joined']:
                raise HTTPException(401)
        except HTTPException:
            await ws.close(code=4401); return
        await ws.accept()
        # Read-only socket: all writes go through authenticated, CSRF-checked HTTP.
        # Snapshots give reconnects a full authoritative state, including persisted deadline.
        try:
            while True:
                if admin:
                    admin_auth(ws.cookies)
                payload = game.state(db, sid, token, admin)
                if admin:
                    payload['join_url'] = f'{settings.public_base_url}/join/{sid}'
                await ws.send_json(payload)
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=.5)
                    if message['type'] == 'websocket.disconnect':
                        break
                except asyncio.TimeoutError:
                    pass
        except HTTPException:
            await ws.close(code=4401)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass

    return app
