import hashlib
import json
import secrets
import sqlite3
import time
import unicodedata
from fastapi import HTTPException

MAX_EXPERIENCE_YEARS = 60

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def group_label(years):
    """Deneyim yılı aralıklara bölünmez; her yıl kendi grubudur."""
    return f'{years} yıl'

def empty_groups():
    return {}

def bucket(buckets, years):
    if years not in buckets:
        buckets[years] = {'years': years, 'label': group_label(years),
                          'participants': 0, 'answered': 0, 'correct': 0, 'total': 0}
    return buckets[years]

def ordered_groups(buckets, key='total'):
    result = []
    for years in sorted(buckets):
        item = buckets[years]
        if not item[key]:
            continue
        result.append({**item, 'percent': round(100 * item['correct'] / item[key], 1)})
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

def question_images(conn, question_id, revealed=False):
    return [dict(row) for row in conn.execute(
        "SELECT id,placement FROM question_images WHERE question_id=? AND (placement='question' OR ?) ORDER BY position",
        (question_id, revealed))]

def image_content(db, sid, image_id, token=None, admin=False):
    with db.connect() as conn:
        s = session_row(conn, sid)
        if not admin and not participant_row(conn, sid, token):
            raise HTTPException(401, 'Bu sınava katılmalısın.')
        image = conn.execute('SELECT i.id,i.placement,q.position FROM question_images i JOIN questions q ON q.id=i.question_id'
                             ' WHERE i.id=? AND q.exam_id=?', (image_id, s['exam_id'])).fetchone()
        if not image or s['phase'] == 'lobby' or image['position'] > s['question_index']:
            raise HTTPException(404, 'Görsel henüz erişilebilir değil.')
        revealed = (s['phase'] in ('results', 'finished') or image['position'] < s['question_index'] or
                    (s['phase'] == 'question' and s['deadline'] is not None and s['deadline'] <= time.time()))
        if image['placement'] == 'explanation' and not revealed:
            raise HTTPException(404, 'Görsel henüz erişilebilir değil.')
        row = conn.execute('SELECT mime_type,data FROM question_images WHERE id=?', (image_id,)).fetchone()
        return row['data'], row['mime_type']

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
        conn.execute('INSERT INTO answers(participant_id,session_id,question_id,choice,answered_at) VALUES (?,?,?,?,?)',
                     (p['id'], sid, question_id, choice, now))
        return {'saved': True}

def question_groups(conn, sid, q):
    """Bir sorunun deneyim yılına göre doğru/yanlış kovaları."""
    buckets = {}
    for row in conn.execute('SELECT p.experience_years AS years, a.choice AS choice FROM participants p'
                            ' LEFT JOIN answers a ON a.participant_id=p.id AND a.question_id=?'
                            ' WHERE p.session_id=?', (q['id'], sid)):
        item = bucket(buckets, row['years'])
        item['participants'] += 1
        item['total'] += 1
        if row['choice'] is not None:
            item['answered'] += 1
            item['correct'] += row['choice'] == q['correct']
    return buckets

def past_question(db, sid, index, token=None, admin=False):
    """Sonuçları açılmış bir soruyu salt okunur gösterir; oturum durumu değişmez."""
    with db.transaction() as conn:
        now = time.time()
        expire(conn, sid, now)
        s = session_row(conn, sid)
        p = participant_row(conn, sid, token)
        if not admin and not p:
            raise HTTPException(401, 'Bu sınava katılmalısın.')
        count = conn.execute('SELECT COUNT(*) FROM questions WHERE exam_id=?', (s['exam_id'],)).fetchone()[0]
        if type(index) is not int or not 0 <= index < count:
            raise HTTPException(404, 'Soru bulunamadı.')
        if s['phase'] == 'finished':
            revealed = count - 1
        elif s['phase'] == 'results':
            revealed = s['question_index']
        else:
            revealed = s['question_index'] - 1
        if index > revealed:
            raise HTTPException(409, 'Bu sorunun sonuçları henüz açılmadı.')
        q = conn.execute('SELECT * FROM questions WHERE exam_id=? AND position=?', (s['exam_id'], index)).fetchone()
        options = json.loads(q['options'])
        counts = [0] * len(options)
        for row in conn.execute('SELECT choice,COUNT(*) AS n FROM answers WHERE session_id=? AND question_id=? GROUP BY choice',
                                (sid, q['id'])):
            counts[row['choice']] = row['n']
        total = conn.execute('SELECT COUNT(*) FROM participants WHERE session_id=?', (sid,)).fetchone()[0]
        own = None
        if p:
            a = conn.execute('SELECT choice FROM answers WHERE participant_id=? AND question_id=?', (p['id'], q['id'])).fetchone()
            own = a['choice'] if a else None
        return {'review': True, 'title': s['title'], 'phase': 'results', 'joined': bool(p),
                'question_index': index, 'question_count': count, 'revealed_max': revealed,
                'participant_count': total, 'answered_count': sum(counts),
                'question': {'id': q['id'], 'text': q['text'], 'options': options, 'topic': q['topic'],
                             'correct': q['correct'], 'hint': q['hint'], 'explanation': q['explanation'],
                             'images': question_images(conn, q['id'], revealed=True)},
                'distribution': counts, 'unanswered': total - sum(counts), 'own_choice': own,
                'experience': ordered_groups(question_groups(conn, sid, q)),
                'nickname': p['nickname'] if p else None}

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
                  'remaining_seconds': max(0, s['deadline'] - now) if s['phase'] == 'question' else 0,
                  'revealed_max': (count - 1 if s['phase'] == 'finished'
                                   else s['question_index'] if s['phase'] == 'results'
                                   else s['question_index'] - 1)}
        if admin:
            result['participants'] = [{'nickname': r['nickname'], 'experience_years': r['experience_years']} for r in participants]
        if p:
            result['nickname'] = p['nickname']
            result['experience_years'] = p['experience_years']
        if s['phase'] in ('question', 'results'):
            q = conn.execute('SELECT * FROM questions WHERE exam_id=? AND position=?', (s['exam_id'], s['question_index'])).fetchone()
            options = json.loads(q['options'])
            result['question'] = {'id': q['id'], 'text': q['text'], 'options': options, 'topic': q['topic'],
                                  'images': question_images(conn, q['id'], revealed=s['phase'] == 'results')}
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
                result['experience'] = ordered_groups(question_groups(conn, sid, q))
        if s['phase'] == 'finished' and p:
            totals = conn.execute('SELECT COUNT(*) AS answered,COALESCE(SUM(a.choice=q.correct),0) AS correct FROM answers a JOIN questions q ON q.id=a.question_id WHERE a.participant_id=? AND a.session_id=?', (p['id'], sid)).fetchone()
            result['summary'] = {'correct': totals['correct'], 'wrong': totals['answered'] - totals['correct'], 'blank': count - totals['answered']}
        return result

def exam_questions(conn, exam_id):
    questions = [dict(q) for q in conn.execute(
        'SELECT id,position,text,options,correct,topic,hint,explanation FROM questions WHERE exam_id=? ORDER BY position', (exam_id,))]
    for q in questions:
        q['options'] = json.loads(q['options'])
        q['images'] = question_images(conn, q['id'], revealed=True)
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
            bucket(overall, person['experience_years'])['participants'] += 1

        question_rows, total_correct, total_answered = [], 0, 0
        for q in questions:
            counts = [0] * len(q['options'])
            buckets = empty_groups()
            unanswered = 0
            for person in people:
                item = bucket(buckets, person['experience_years'])
                item['participants'] += 1
                item['total'] += 1
                choice = answers.get((person['id'], q['id']))
                if choice is None or not 0 <= choice < len(counts):
                    unanswered += 1
                    continue
                counts[choice] += 1
                item['answered'] += 1
                item['correct'] += choice == q['correct']
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
            item = bucket(overall, person['experience_years'])
            item['total'] += len(questions)
            item['answered'] += correct + wrong
            item['correct'] += correct
            label = item['label']
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
        group_ids = [peer['id'] for peer in peers if peer['experience_years'] == p['experience_years']]
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
