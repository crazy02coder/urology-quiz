import hashlib
import json
import secrets
import sqlite3
import time
import unicodedata
from fastapi import HTTPException

DURATION = 45

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def participant_cookie(sid):
    return f'participant_{sid}'

def session_row(conn, sid):
    row = conn.execute('SELECT s.*, e.title FROM sessions s JOIN exams e ON e.id=s.exam_id WHERE s.id=?', (sid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Oturum bulunamadı.')
    return row

def participant_row(conn, sid, token):
    if not token:
        return None
    return conn.execute('SELECT * FROM participants WHERE session_id=? AND token_hash=?', (sid, digest(token))).fetchone()

def expire(conn, sid, now):
    conn.execute("UPDATE sessions SET phase='results',version=version+1 WHERE id=? AND phase='question' AND deadline<=?", (sid, now))

def join(db, sid, nickname, old_token):
    nickname = unicodedata.normalize('NFKC', nickname).strip()
    key = nickname.casefold().replace('i\u0307', 'i').replace('ı', 'i')
    if not 2 <= len(nickname) <= 30 or any(unicodedata.category(c).startswith('C') for c in nickname):
        raise HTTPException(422, 'Takma adın 2–30 karakter olmalı; kontrol karakteri içermemeli.')
    with db.transaction() as conn:
        session = session_row(conn, sid)
        existing = participant_row(conn, sid, old_token)
        if existing:
            return old_token
        if session['phase'] != 'lobby':
            raise HTTPException(409, 'Oturum başladı. Yeni katılımcı alınmıyor.')
        token = secrets.token_urlsafe(32)
        try:
            conn.execute('INSERT INTO participants VALUES (?,?,?,?,?,?)',
                         (secrets.token_urlsafe(16), sid, nickname, key, digest(token), time.time()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Bu takma ad kullanımda. Başka bir takma ad seç.')
        return token

def advance(db, sid, action, expected_version):
    with db.transaction() as conn:
        now = time.time()
        expire(conn, sid, now)
        session = session_row(conn, sid)
        if session['version'] != expected_version:
            raise HTTPException(409, 'Oturum değişti. Güncel ekranı kontrol edin.')
        count = conn.execute('SELECT COUNT(*) FROM questions WHERE exam_id=?', (session['exam_id'],)).fetchone()[0]
        if action == 'start' and session['phase'] == 'lobby':
            index, phase, deadline = 0, 'question', now + DURATION
        elif action == 'next' and session['phase'] == 'results' and session['question_index'] + 1 < count:
            index, phase, deadline = session['question_index'] + 1, 'question', now + DURATION
        elif action == 'finish' and session['phase'] == 'results' and session['question_index'] == count - 1:
            index, phase, deadline = session['question_index'], 'finished', session['deadline']
        else:
            raise HTTPException(409, 'Bu aşamada bu işlem yapılamaz.')
        conn.execute('UPDATE sessions SET phase=?,question_index=?,deadline=?,version=version+1,finished_at=? WHERE id=?',
                     (phase, index, deadline, now if phase == 'finished' else None, sid))

def answer(db, sid, token, question_id, choice):
    with db.transaction() as conn:
        now = time.time()
        session = session_row(conn, sid)
        p = participant_row(conn, sid, token)
        if not p:
            raise HTTPException(401, 'Bu oturuma katılmalısın.')
        q = conn.execute('SELECT * FROM questions WHERE exam_id=? AND position=?',
                         (session['exam_id'], session['question_index'])).fetchone()
        if not q or q['id'] != question_id:
            raise HTTPException(409, 'Bu soru artık açık değil.')
        if session['phase'] != 'question' or now >= session['deadline']:
            raise HTTPException(409, 'Süre doldu. Cevap kabulü kapandı.')
        if type(choice) is not int or not 0 <= choice < len(json.loads(q['options'])):
            raise HTTPException(422, 'Geçerli bir şık seç.')
        previous = conn.execute('SELECT choice FROM answers WHERE participant_id=? AND question_id=?', (p['id'], question_id)).fetchone()
        if previous:
            if previous['choice'] == choice:
                return {'saved': True}
            raise HTTPException(409, 'Cevabın zaten kaydedildi ve değiştirilemez.')
        conn.execute('INSERT INTO answers VALUES (?,?,?,?,?)', (p['id'], sid, question_id, choice, now))
        return {'saved': True}

def state(db, sid, token=None, admin=False):
    with db.transaction() as conn:
        now = time.time()
        expire(conn, sid, now)
        s = session_row(conn, sid)
        p = participant_row(conn, sid, token)
        if not admin and not p:
            return {'joined': False, 'title': s['title'], 'phase': s['phase']}
        participants = conn.execute('SELECT nickname FROM participants WHERE session_id=? ORDER BY created_at', (sid,)).fetchall()
        count = conn.execute('SELECT COUNT(*) FROM questions WHERE exam_id=?', (s['exam_id'],)).fetchone()[0]
        result = {'joined': bool(p), 'session_id': sid, 'title': s['title'], 'phase': s['phase'],
                  'version': s['version'], 'question_index': s['question_index'], 'question_count': count,
                  'server_now': now, 'deadline': s['deadline'], 'participant_count': len(participants),
                  'remaining_seconds': max(0, s['deadline'] - now) if s['phase'] == 'question' else 0}
        if admin:
            result['participants'] = [r['nickname'] for r in participants]
        if p:
            result['nickname'] = p['nickname']
        if s['phase'] in ('question', 'results'):
            q = conn.execute('SELECT * FROM questions WHERE exam_id=? AND position=?', (s['exam_id'], s['question_index'])).fetchone()
            options = json.loads(q['options'])
            result['question'] = {'id': q['id'], 'text': q['text'], 'options': options, 'topic': q['topic']}
            if p:
                a = conn.execute('SELECT choice FROM answers WHERE participant_id=? AND question_id=?', (p['id'], q['id'])).fetchone()
                result['own_choice'] = a['choice'] if a else None
            if s['phase'] == 'results':
                counts = [0] * len(options)
                for row in conn.execute('SELECT choice,COUNT(*) AS n FROM answers WHERE session_id=? AND question_id=? GROUP BY choice', (sid, q['id'])):
                    counts[row['choice']] = row['n']
                result['question']['correct'] = q['correct']
                result['question']['hint'] = q['hint']
                result['question']['explanation'] = q['explanation']
                result['distribution'] = counts
                result['unanswered'] = len(participants) - sum(counts)
        if s['phase'] == 'finished' and p:
            totals = conn.execute('SELECT COUNT(*) AS answered,COALESCE(SUM(a.choice=q.correct),0) AS correct FROM answers a JOIN questions q ON q.id=a.question_id WHERE a.participant_id=? AND a.session_id=?', (p['id'], sid)).fetchone()
            result['summary'] = {'correct': totals['correct'], 'wrong': totals['answered'] - totals['correct'], 'blank': count - totals['answered']}
        return result

def history(db, sid):
    with db.connect() as conn:
        s = session_row(conn, sid)
        if s['phase'] != 'finished':
            raise HTTPException(409, 'Cevap dökümü oturum bitince açılır.')
        questions = [dict(q) for q in conn.execute('SELECT id,position,text,options,correct FROM questions WHERE exam_id=? ORDER BY position', (s['exam_id'],))]
        for q in questions:
            q['options'] = json.loads(q['options'])
        rows = []
        for p in conn.execute('SELECT id,nickname FROM participants WHERE session_id=? ORDER BY created_at', (sid,)):
            answers = {a['question_id']: a['choice'] for a in conn.execute('SELECT question_id,choice FROM answers WHERE participant_id=? AND session_id=?', (p['id'], sid))}
            rows.append({'nickname': p['nickname'], 'answers': answers})
        return {'title': s['title'], 'questions': questions, 'participants': rows}
