import hashlib
import json
import secrets
import sqlite3
import time
import unicodedata
from fastapi import HTTPException

# Deneyim yılı grupları: 0'dan başlar, üst sınırı None olan grup açık uçludur.
EXPERIENCE_GROUPS = ((0, 0, 'Yeni başlayan'), (1, 2, '1–2 yıl'), (3, 5, '3–5 yıl'),
                     (6, 10, '6–10 yıl'), (11, None, '10+ yıl'))
MAX_EXPERIENCE_YEARS = 60

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def group_label(years):
    for low, high, label in EXPERIENCE_GROUPS:
        if years >= low and (high is None or years <= high):
            return label
    return EXPERIENCE_GROUPS[-1][2]

def empty_groups():
    return {label: {'label': label, 'participants': 0, 'answered': 0, 'correct': 0, 'total': 0}
            for _, _, label in EXPERIENCE_GROUPS}

def ordered_groups(buckets, key='total'):
    result = []
    for _, _, label in EXPERIENCE_GROUPS:
        bucket = buckets[label]
        if not bucket[key]:
            continue
        base = bucket[key] or 1
        result.append({**bucket, 'percent': round(100 * bucket['correct'] / base, 1)})
    return result

def participant_cookie(sid):
    return f'participant_{sid}'

def session_row(conn, sid):
    row = conn.execute('SELECT s.*, e.title FROM sessions s JOIN exams e ON e.id=s.exam_id WHERE s.id=?', (sid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Sınav bulunamadı.')
    return row

def participant_row(conn, sid, token):
    if not token:
        return None
    return conn.execute('SELECT * FROM participants WHERE session_id=? AND token_hash=?', (sid, digest(token))).fetchone()

def expire(conn, sid, now):
    conn.execute("UPDATE sessions SET phase='results',version=version+1 WHERE id=? AND phase='question' AND deadline<=?", (sid, now))

def join(db, sid, nickname, experience_years, old_token):
    nickname = unicodedata.normalize('NFKC', nickname).strip()
    key = nickname.casefold().replace('i\u0307', 'i').replace('ı', 'i')
    if not 2 <= len(nickname) <= 30 or any(unicodedata.category(c).startswith('C') for c in nickname):
        raise HTTPException(422, 'Takma adın 2–30 karakter olmalı; kontrol karakteri içermemeli.')
    if type(experience_years) is not int or not 0 <= experience_years <= MAX_EXPERIENCE_YEARS:
        raise HTTPException(422, f'Deneyim yılı 0 ile {MAX_EXPERIENCE_YEARS} arasında bir tam sayı olmalı.')
    with db.transaction() as conn:
        session = session_row(conn, sid)
        existing = participant_row(conn, sid, old_token)
        if existing:
            return old_token
        if session['phase'] != 'lobby':
            raise HTTPException(409, 'Sınav başladı. Yeni katılımcı alınmıyor.')
        token = secrets.token_urlsafe(32)
        try:
            conn.execute('INSERT INTO participants(id,session_id,nickname,nickname_key,token_hash,created_at,experience_years)'
                         ' VALUES (?,?,?,?,?,?,?)',
                         (secrets.token_urlsafe(16), sid, nickname, key, digest(token), time.time(), experience_years))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Bu takma ad kullanımda. Başka bir takma ad seç.')
        return token

def advance(db, sid, action, expected_version, question_duration_seconds=None):
    with db.transaction() as conn:
        now = time.time()
        expire(conn, sid, now)
        session = session_row(conn, sid)
        if session['version'] != expected_version:
            raise HTTPException(409, 'Sınav durumu değişti. Güncel ekranı kontrol edin.')
        duration = session['question_duration_seconds']
        if question_duration_seconds is not None:
            if action != 'start' or type(question_duration_seconds) is not int or not 5 <= question_duration_seconds <= 300:
                raise HTTPException(422, 'Süre yalnızca sınavı başlatırken 5–300 saniye arasında belirlenebilir.')
            duration = question_duration_seconds
        count = conn.execute('SELECT COUNT(*) FROM questions WHERE exam_id=?', (session['exam_id'],)).fetchone()[0]
        if action == 'start' and session['phase'] == 'lobby':
            index, phase, deadline = 0, 'question', now + duration
        elif action == 'next' and session['phase'] == 'results' and session['question_index'] + 1 < count:
            index, phase, deadline = session['question_index'] + 1, 'question', now + duration
        elif action == 'finish' and session['phase'] == 'results' and session['question_index'] == count - 1:
            index, phase, deadline = session['question_index'], 'finished', session['deadline']
        else:
            raise HTTPException(409, 'Bu aşamada bu işlem yapılamaz.')
        conn.execute('UPDATE sessions SET phase=?,question_index=?,deadline=?,version=version+1,finished_at=?,question_duration_seconds=? WHERE id=?',
                     (phase, index, deadline, now if phase == 'finished' else None, duration, sid))

def answer(db, sid, token, question_id, choice):
    with db.transaction() as conn:
        now = time.time()
        session = session_row(conn, sid)
        p = participant_row(conn, sid, token)
        if not p:
            raise HTTPException(401, 'Bu sınava katılmalısın.')
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
        participants = conn.execute('SELECT nickname,experience_years FROM participants WHERE session_id=? ORDER BY created_at', (sid,)).fetchall()
        count = conn.execute('SELECT COUNT(*) FROM questions WHERE exam_id=?', (s['exam_id'],)).fetchone()[0]
        result = {'joined': bool(p), 'session_id': sid, 'title': s['title'], 'phase': s['phase'],
                  'version': s['version'], 'question_index': s['question_index'], 'question_count': count,
                  'question_duration_seconds': s['question_duration_seconds'],
                  'server_now': now, 'deadline': s['deadline'], 'participant_count': len(participants),
                  'remaining_seconds': max(0, s['deadline'] - now) if s['phase'] == 'question' else 0}
        if admin:
            result['participants'] = [{'nickname': r['nickname'], 'experience_years': r['experience_years']} for r in participants]
        if p:
            result['nickname'] = p['nickname']
            result['experience_years'] = p['experience_years']
        if s['phase'] in ('question', 'results'):
            q = conn.execute('SELECT * FROM questions WHERE exam_id=? AND position=?', (s['exam_id'], s['question_index'])).fetchone()
            options = json.loads(q['options'])
            result['question'] = {'id': q['id'], 'text': q['text'], 'options': options, 'topic': q['topic']}
            # Yalnızca kaç kişinin cevapladığı; hangi şıkkın seçildiği soru açıkken paylaşılmaz.
            result['answered_count'] = conn.execute('SELECT COUNT(*) FROM answers WHERE session_id=? AND question_id=?',
                                                    (sid, q['id'])).fetchone()[0]
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
                # Deneyim kırılımı yalnızca sonuç aşamasında üretilir; soru açıkken doğru cevabı ele verirdi.
                buckets = empty_groups()
                for row in conn.execute('SELECT p.experience_years AS years, a.choice AS choice FROM participants p'
                                        ' LEFT JOIN answers a ON a.participant_id=p.id AND a.question_id=?'
                                        ' WHERE p.session_id=?', (q['id'], sid)):
                    bucket = buckets[group_label(row['years'])]
                    bucket['participants'] += 1
                    bucket['total'] += 1
                    if row['choice'] is not None:
                        bucket['answered'] += 1
                        bucket['correct'] += row['choice'] == q['correct']
                result['experience'] = ordered_groups(buckets)
        if s['phase'] == 'finished' and p:
            totals = conn.execute('SELECT COUNT(*) AS answered,COALESCE(SUM(a.choice=q.correct),0) AS correct FROM answers a JOIN questions q ON q.id=a.question_id WHERE a.participant_id=? AND a.session_id=?', (p['id'], sid)).fetchone()
            result['summary'] = {'correct': totals['correct'], 'wrong': totals['answered'] - totals['correct'], 'blank': count - totals['answered']}
        return result

def exam_questions(conn, exam_id):
    questions = [dict(q) for q in conn.execute(
        'SELECT id,position,text,options,correct,topic,hint,explanation FROM questions WHERE exam_id=? ORDER BY position', (exam_id,))]
    for q in questions:
        q['options'] = json.loads(q['options'])
    return questions

def finished_session(conn, sid, message):
    s = session_row(conn, sid)
    if s['phase'] != 'finished':
        raise HTTPException(409, message)
    return s

def history(db, sid):
    with db.connect() as conn:
        s = finished_session(conn, sid, 'Cevap dökümü sınav bitince açılır.')
        questions = exam_questions(conn, s['exam_id'])
        rows = []
        for p in conn.execute('SELECT id,nickname,experience_years FROM participants WHERE session_id=? ORDER BY created_at', (sid,)):
            answers = {a['question_id']: a['choice'] for a in conn.execute('SELECT question_id,choice FROM answers WHERE participant_id=? AND session_id=?', (p['id'], sid))}
            rows.append({'nickname': p['nickname'], 'experience_years': p['experience_years'],
                         'experience_group': group_label(p['experience_years']), 'answers': answers})
        return {'title': s['title'], 'questions': questions, 'participants': rows}

def statistics(db, sid):
    """Bitmiş bir oturumun tam dökümü: soru başına, deneyim grubu başına ve kişi başına."""
    with db.connect() as conn:
        s = finished_session(conn, sid, 'İstatistikler sınav bitince açılır.')
        questions = exam_questions(conn, s['exam_id'])
        people = [dict(r) for r in conn.execute(
            'SELECT id,nickname,experience_years,created_at FROM participants WHERE session_id=? ORDER BY created_at', (sid,))]
        answers = {}
        for a in conn.execute('SELECT participant_id,question_id,choice FROM answers WHERE session_id=?', (sid,)):
            answers[(a['participant_id'], a['question_id'])] = a['choice']

        overall = empty_groups()
        for person in people:
            overall[group_label(person['experience_years'])]['participants'] += 1

        question_rows, total_correct, total_answered = [], 0, 0
        for q in questions:
            counts = [0] * len(q['options'])
            buckets = empty_groups()
            unanswered = 0
            for person in people:
                bucket = buckets[group_label(person['experience_years'])]
                bucket['participants'] += 1
                bucket['total'] += 1
                choice = answers.get((person['id'], q['id']))
                if choice is None or not 0 <= choice < len(counts):
                    unanswered += 1
                    continue
                counts[choice] += 1
                bucket['answered'] += 1
                bucket['correct'] += choice == q['correct']
            correct_count = counts[q['correct']] if 0 <= q['correct'] < len(counts) else 0
            total_correct += correct_count
            total_answered += sum(counts)
            question_rows.append({**q, 'distribution': counts, 'unanswered': unanswered,
                                  'correct_count': correct_count, 'answered': sum(counts),
                                  'percent': round(100 * correct_count / len(people), 1) if people else 0.0,
                                  'groups': ordered_groups(buckets)})

        people_rows = []
        for person in people:
            correct = wrong = 0
            for q in questions:
                choice = answers.get((person['id'], q['id']))
                if choice is None:
                    continue
                if choice == q['correct']:
                    correct += 1
                else:
                    wrong += 1
            label = group_label(person['experience_years'])
            overall[label]['total'] += len(questions)
            overall[label]['answered'] += correct + wrong
            overall[label]['correct'] += correct
            people_rows.append({'nickname': person['nickname'], 'experience_years': person['experience_years'],
                                'experience_group': label, 'correct': correct, 'wrong': wrong,
                                'blank': len(questions) - correct - wrong,
                                'percent': round(100 * correct / len(questions), 1) if questions else 0.0})
        people_rows.sort(key=lambda r: (-r['correct'], r['nickname'].casefold()))

        denominator = len(people) * len(questions)
        return {'title': s['title'], 'session_id': sid, 'finished_at': s['finished_at'],
                'created_at': s['created_at'], 'question_duration_seconds': s['question_duration_seconds'],
                'participant_count': len(people), 'question_count': len(questions),
                'total_correct': total_correct, 'total_answered': total_answered,
                'average_percent': round(100 * total_correct / denominator, 1) if denominator else 0.0,
                'average_correct': round(total_correct / len(people), 1) if people else 0.0,
                'groups': ordered_groups(overall), 'questions': question_rows, 'participants': people_rows}

def review(db, sid, token):
    """Katılımcının kendi cevap dökümü: doğru cevap, ipucu ve açıklama dahil."""
    with db.connect() as conn:
        s = finished_session(conn, sid, 'Cevap dökümün sınav bitince açılır.')
        p = participant_row(conn, sid, token)
        if not p:
            raise HTTPException(401, 'Bu sınava katılmalısın.')
        questions = exam_questions(conn, s['exam_id'])
        answers = {a['question_id']: a['choice'] for a in conn.execute(
            'SELECT question_id,choice FROM answers WHERE participant_id=? AND session_id=?', (p['id'], sid))}
        label = group_label(p['experience_years'])

        rows, correct, wrong = [], 0, 0
        peers = [dict(r) for r in conn.execute(
            'SELECT id,experience_years FROM participants WHERE session_id=?', (sid,))]
        group_ids = [peer['id'] for peer in peers if group_label(peer['experience_years']) == label]
        group_answers = {}
        if group_ids:
            placeholders = ','.join('?' * len(group_ids))
            for a in conn.execute(f'SELECT participant_id,question_id,choice FROM answers WHERE session_id=? AND participant_id IN ({placeholders})',
                                  (sid, *group_ids)):
                group_answers[(a['participant_id'], a['question_id'])] = a['choice']

        group_correct = 0
        for q in questions:
            choice = answers.get(q['id'])
            if choice is not None:
                correct += choice == q['correct']
                wrong += choice != q['correct']
            hits = sum(group_answers.get((pid, q['id'])) == q['correct'] for pid in group_ids)
            group_correct += hits
            rows.append({**q, 'own_choice': choice,
                         'group_correct': hits, 'group_total': len(group_ids),
                         'group_percent': round(100 * hits / len(group_ids), 1) if group_ids else 0.0})
        denominator = len(group_ids) * len(questions)
        return {'title': s['title'], 'nickname': p['nickname'], 'experience_years': p['experience_years'],
                'experience_group': label, 'group_size': len(group_ids),
                'group_average_percent': round(100 * group_correct / denominator, 1) if denominator else 0.0,
                'summary': {'correct': correct, 'wrong': wrong, 'blank': len(questions) - correct - wrong},
                'percent': round(100 * correct / len(questions), 1) if questions else 0.0,
                'questions': rows}
