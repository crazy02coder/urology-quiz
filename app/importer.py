"""DOCX adapter based on Uroloji_Asistan_Vaka_Sorulari.docx.

Reads document content without executing macros, links or embedded instructions.
"""
import io
import base64
import json
import re
import secrets
import time
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET
from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from fastapi import HTTPException

MAX_FILE_BYTES = 5 * 1024 * 1024
# Soru sayısında pratik bir üst sınır; sunum sınavları için serbest bırakıldı.
MAX_QUESTIONS = 1000
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({'.docx'})

def load_docx(filename: str, content: bytes):
    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, 'Yalnızca .docx dosyaları destekleniyor.')
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, 'Dosya en fazla 5 MB olabilir.')
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(i.file_size for i in entries) > 20*1024*1024:
                raise HTTPException(422, 'DOCX açılmış içerik boyutu sınırı aşıldı (20 MB).')
            if len({i.filename for i in entries}) != len(entries) or any('vbaProject' in i.filename for i in entries):
                raise HTTPException(422, 'Makrolu veya yinelenen içerikli DOCX kabul edilmez.')
            if archive.getinfo('word/document.xml').file_size > 8*1024*1024:
                raise HTTPException(422, 'Belge metni çok büyük.')
            xml = archive.read('word/document.xml')
            # Prohibit DTDs/entities; the parser never resolves relationships or fetches URLs.
            if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                raise HTTPException(422, 'DOCX içinde desteklenmeyen XML tanımı var.')
            root = SafeET.fromstring(xml, forbid_dtd=True)
            numbering = None
            if 'word/numbering.xml' in archive.namelist():
                info = archive.getinfo('word/numbering.xml')
                if info.file_size > 1024*1024:
                    raise HTTPException(422, 'Word numaralandırma bilgisi çok büyük.')
                numbering = SafeET.fromstring(archive.read(info), forbid_dtd=True)
    except (BadZipFile, KeyError, ET.ParseError, DefusedXmlException, RuntimeError, OSError, ValueError):
        raise HTTPException(422, 'Geçerli, şifresiz bir DOCX dosyası yükleyin.')
    return root, numbering

def parse_file(filename: str, content: bytes) -> list[dict]:
    root, _ = load_docx(filename, content)
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    w = '{' + ns['w'] + '}'
    body = root.find('w:body', ns)
    if body is None:
        raise HTTPException(422, 'DOCX gövdesi bulunamadı.')
    if body.find('.//w:tbl', ns) is not None:
        raise HTTPException(422, 'Tablo içindeki sorular desteklenmiyor. Örnek dosyadaki paragraf düzenini kullanın.')
    if any(body.find('.//w:'+tag,ns) is not None for tag in ('ins','del','drawing','pict','object','txbxContent','sdt')):
        raise HTTPException(422, 'İzlenen değişiklik, görsel veya metin kutusu var. Soruları örnekteki düz metin düzeninde yükleyin.')
    paragraphs=[]
    for line, p in enumerate(body.findall('w:p', ns),1):
        text=''.join(n.text or '' if n.tag==w+'t' else '\n' if n.tag in (w+'br',w+'cr') else '\t' if n.tag==w+'tab' else '' for n in p.iter()).strip()
        if text: paragraphs.append((line,text))
    questions, errors, current = [], [], None
    heading = re.compile(r'^Soru\s+(\d+)\s*(?:[-–—]\s*Konu\s*:\s*(.*))?$',re.I)
    def location():
        return f'Soru {current["number"]} (paragraf {current["source_line"]})'
    def finish():
        if current is None:return
        labels=current.pop('labels'); current['text']='\n'.join(current.pop('parts')).strip()
        if labels != [chr(65+i) for i in range(len(labels))]:
            errors.append(f'{location()}: Şıklar A ile başlayıp sırayla ilerlemeli; eksik veya yinelenen şık var.')
        if current['correct'] is None:
            errors.append(f'{location()}: Tek bir doğru cevap bulunamadı.')
        questions.append(current.copy())
    for line,text in paragraphs:
        match=heading.fullmatch(text)
        if match:
            finish()
            number=int(match[1])
            current={'number':number,'source_line':line,'topic':match[2] or '', 'parts':[], 'options':[], 'labels':[], 'correct':None,'hint':'','explanation':''}
            if number!=len(questions)+1:
                errors.append(f'Soru {number} (paragraf {line}): Soru numaraları 1 ile başlayıp sırayla ilerlemeli.')
            continue
        if current is None:
            if re.match(r'^(?:Soru\s+\d|[A-E]\)|Doğru Cevap)',text,re.I):
                errors.append(f'Paragraf {line}: Soru başlığı örnekteki “Soru 1 - Konu: …” düzeninde olmalı.')
            continue # document title and introduction, never executable instructions
        option=re.fullmatch(r'([A-E])\)\s*(.*)',text,re.S)
        if option:
            if current['correct'] is not None:
                errors.append(f'{location()}: Cevap anahtarından sonra şık bulundu (paragraf {line}).')
            current['labels'].append(option[1]);current['options'].append(option[2]);continue
        if text.startswith('İpucu:'):
            if current['hint']:errors.append(f'{location()}: Birden fazla ipucu paragrafı var.')
            current['hint']=text[len('İpucu:'):].strip();continue
        if text.startswith('Doğru Cevap & Açıklama:'):
            matches=list(re.finditer(r'\bCevap:\s*([A-E])\)',text))
            if len(matches)!=1 or current['correct'] is not None:
                errors.append(f'{location()}: “Cevap: A)” biçiminde tek doğru cevap belirtilmeli.');continue
            current['correct']=ord(matches[0][1])-65
            tail=text[matches[0].end():].strip()
            selected=tail.split('\n',1)[0].strip()
            index=current['correct']
            if index<len(current['options']) and selected and selected!=current['options'][index].strip():
                errors.append(f'{location()}: Cevap anahtarındaki metin seçilen şıkla eşleşmiyor.')
            current['explanation']=tail.split('\n',1)[1].strip() if '\n' in tail else ''
            continue
        if current['options'] or current['correct'] is not None or re.match(r'^(?:Soru\s+\d|[A-Z]\)|Doğru Cevap)',text):
            errors.append(f'{location()}: Paragraf {line} tanınmadı. Şık ve cevap düzenini kontrol edin.')
        else:
            current['parts'].append(text)
    finish()
    if not questions:errors.append('Soru bulunamadı. Başlıklar “Soru 1 - Konu: …” düzeninde olmalı.')
    # Collect structural and content errors; no partial preview/persistence on failure.
    try: cleaned=validate_questions(questions)
    except HTTPException as exc:
        errors.extend(exc.detail if isinstance(exc.detail,list) else [exc.detail]);cleaned=[]
    if errors:raise HTTPException(422,errors)
    return cleaned

def validate_questions(questions):
    errors, cleaned = [], []
    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_QUESTIONS:
        raise HTTPException(422, [f'Dosyada 1–{MAX_QUESTIONS} soru bulunmalı.'])
    for i, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            errors.append(f'Soru {i}: Geçersiz soru.'); continue
        location = f'Soru {i}' + (f' (satır {q["source_line"]})' if q.get('source_line') else '')
        text, options, correct = q.get('text'), q.get('options'), q.get('correct')
        if not isinstance(text, str) or not text.strip() or len(text) > 3000:
            errors.append(f'{location}: Soru metni boş olamaz ve 3000 karakteri geçemez.')
        if not isinstance(options, list) or not 2 <= len(options) <= 5:
            errors.append(f'{location}: 2–5 şık bulunmalı.')
            options = []
        elif any(not isinstance(o, str) or not o.strip() or len(o) > 1000 for o in options):
            errors.append(f'{location}: Eksik/boş şık var veya şık 1000 karakterden uzun.')
        if type(correct) is not int or not 0 <= correct < len(options):
            errors.append(f'{location}: Mevcut şıklardan tek bir doğru cevap belirtilmeli.')
        metadata={}
        for field in ('topic','hint','explanation'):
            value=q.get(field,'')
            if not isinstance(value,str) or len(value)>5000:
                errors.append(f'{location}: {field} alanı geçersiz veya çok uzun.');value=''
            metadata[field]=value.strip()
        images = q.get('images', [])
        if not isinstance(images, list) or len(images) > 12 or any(
            not isinstance(img, dict) or not isinstance(img.get('id'), str) or
            not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', img['id']) or
            img.get('placement') not in ('question', 'explanation') for img in images):
            errors.append(f'{location}: Görsel bilgileri geçersiz.'); images = []
        cleaned.append({'text': text.strip() if isinstance(text, str) else '', 'images': images,
                        'options': [o.strip() if isinstance(o, str) else '' for o in options], 'correct': correct, **metadata})
    if errors:
        raise HTTPException(422, errors)
    return cleaned

def create_preview(db, admin_hash, title, questions):
    title = title.strip()
    if not 1 <= len(title) <= 160:
        raise HTTPException(422, 'Sınav başlığı 1–160 karakter olmalı.')
    cleaned = validate_questions(questions)
    preview_id = secrets.token_urlsafe(24)
    with db.transaction() as conn:
        conn.execute('DELETE FROM previews WHERE expires_at < ?', (time.time(),))
        conn.execute('INSERT INTO previews(id,admin_hash,title,questions,expires_at,exam_id) VALUES (?,?,?,?,?,NULL)',
                     (preview_id, admin_hash, title, json.dumps(cleaned), time.time() + 3600))
    return {'preview_id': preview_id, 'title': title, 'questions': cleaned}

def create_review_preview(db, admin_hash, title, extraction):
    title = title.strip()
    if not 1 <= len(title) <= 160:
        raise HTTPException(422, 'Sınav başlığı 1–160 karakter olmalı.')
    draft = {**extraction, 'requires_review': True}
    preview_id = secrets.token_urlsafe(24)
    with db.transaction() as conn:
        conn.execute('DELETE FROM previews WHERE expires_at < ?', (time.time(),))
        conn.execute('INSERT INTO previews(id,admin_hash,title,questions,expires_at,exam_id) VALUES (?,?,?,?,?,NULL)',
                     (preview_id, admin_hash, title, json.dumps(draft), time.time() + 3600))
    # Binary assets remain server-side even though the upload flow uses JSON drafts.
    return {'preview_id': preview_id, 'title': title, **{k:v for k,v in draft.items() if k != 'image_assets'}}

def save_preview(db, admin_hash, preview_id, edited_questions=None, review_confirmed=False):
    with db.transaction() as conn:
        preview = conn.execute('SELECT * FROM previews WHERE id=? AND admin_hash=?', (preview_id, admin_hash)).fetchone()
        if not preview or preview['expires_at'] < time.time():
            raise HTTPException(404, 'Önizleme bulunamadı veya süresi doldu. Dosyayı yeniden yükleyin.')
        if preview['exam_id']:
            return preview['exam_id']
        stored = json.loads(preview['questions'])
        assets = stored.get('image_assets', {}) if isinstance(stored, dict) else {}
        if isinstance(stored, dict):
            if not review_confirmed:
                raise HTTPException(422, 'Soruları, şıkları ve doğru cevapları kontrol ettiğinizi onaylayın.')
            stored = stored['questions']
        questions = validate_questions(edited_questions if edited_questions is not None else stored)
        exam_id = secrets.token_urlsafe(16)
        image_bytes = 0
        decoded_assets = {}
        conn.execute('INSERT INTO exams(id,title,created_at) VALUES (?,?,?)', (exam_id, preview['title'], time.time()))
        for i, q in enumerate(questions):
            question_id = secrets.token_urlsafe(16)
            conn.execute('INSERT INTO questions(id,exam_id,position,text,options,correct,topic,hint,explanation) VALUES (?,?,?,?,?,?,?,?,?)',
                         (question_id, exam_id, i, q['text'], json.dumps(q['options']), q['correct'], q['topic'], q['hint'], q['explanation']))
            for position, ref in enumerate(q['images']):
                asset = assets.get(ref['id'])
                if asset is None:
                    raise HTTPException(422, f'Soru {i+1}: Görsel bulunamadı. Dosyayı yeniden yükleyin.')
                if ref['id'] not in decoded_assets:
                    decoded_assets[ref['id']] = base64.b64decode(asset['data'], validate=True)
                data = decoded_assets[ref['id']]
                image_bytes += len(data)
                if image_bytes > 20 * 1024 * 1024:
                    raise HTTPException(422, 'Tekrarlanan görseller dahil sınavın toplam görsel boyutu 20 MB’ı geçemez.')
                conn.execute('INSERT INTO question_images(id,question_id,position,placement,mime_type,data) VALUES (?,?,?,?,?,?)',
                             (secrets.token_urlsafe(24), question_id, position, ref['placement'], asset['mime_type'], data))
        # The saved exam owns the pictures now; keep only the receipt for retries.
        conn.execute('UPDATE previews SET questions=? WHERE id=?', (json.dumps(questions), preview_id))
        conn.execute('UPDATE previews SET exam_id=? WHERE id=?', (exam_id, preview_id))
        return exam_id
