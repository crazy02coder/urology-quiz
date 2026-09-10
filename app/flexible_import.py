"""Local, rule-based extraction. NLTK tokenizers need no downloaded models.

These are document structure rules, not medical reasoning. Unknown answers stay empty.
Every result is an editable draft and must be confirmed by an administrator.
"""
import re
import unicodedata
from nltk.tokenize import RegexpTokenizer
from fastapi import HTTPException
from .importer import load_docx

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
LINES = RegexpTokenizer(r'[^\r\n]+')
OPTION_MARKERS = RegexpTokenizer(r'(?<!\S)[A-Ja-j][).:\-]\s*', flags=re.UNICODE)
OPTION = re.compile(r'^([A-Ja-j])[).:\-]\s*(.*)$')
HEADING = re.compile(r'^(?:soru|question)\s*(?:(\d+)\s*[).:\-–—]?\s*|:\s*)(.*)$', re.I)
NUMBERED = re.compile(r'^(\d{1,3})[).\-](?:\s+(.*))?$')
ANSWER = re.compile(r'^(?:(?:doğru|dogru|correct)\s+)?(?:cevap|yanıt|yanit|answer)\b(?:\s*(?:&|ve)\s*açıklama)?\s*[:=\-]?\s*(.*)$', re.I)
ANSWER_LETTER = re.compile(r'^\(?([A-Ea-e])\)?(?:[).:\-]|\b)\s*(.*)$')
KEY_HEADING = re.compile(r'^(?:(?:doğru|dogru)\s+)?(?:cevap|yanıt|yanit)\s+anahtar[ıi]\s*:?(.*)$|^answer\s+key\s*:?(.*)$', re.I)
KEY_PAIR = re.compile(r'(?<!\w)(\d{1,3})\s*[).:=\-]?\s*([A-Ea-e])\b')
INLINE_ANSWER = re.compile(r'\s+(?=(?:(?:doğru|dogru|correct)\s+)?(?:cevap|yanıt|yanit|answer)\s*[:=]\s*[A-Ea-e]\b)', re.I)

def fold(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().replace('i\u0307', 'i').split())

def document_lines(filename, content):
    root, numbering = load_docx(filename, content)
    body = root.find(W + 'body')
    if body is None:
        raise HTTPException(422, 'DOCX gövdesi bulunamadı.')
    if any(body.find('.//' + W + tag) is not None for tag in ('ins', 'del')):
        raise HTTPException(422, 'Word içindeki izlenen değişiklikleri kabul veya reddedip dosyayı yeniden yükleyin.')
    warnings = []
    if any(body.find('.//' + W + tag) is not None for tag in ('drawing', 'pict', 'object', 'txbxContent')):
        warnings.append('Görseller ve metin kutuları okunmadı. Gerekli bilgileri önizlemede metin olarak ekleyin; OCR kullanılmıyor.')
    if body.find('.//' + W + 'tbl') is not None:
        warnings.append('Tablo hücreleri satır sırasıyla okundu. Soru ve şıkların doğru ayrıldığını kontrol edin.')
    formats, definitions, counters, overrides = {}, {}, {}, {}
    if numbering is not None:
        for abstract in numbering.findall(W + 'abstractNum'):
            for level in abstract.findall(W + 'lvl'):
                fmt, start = level.find(W + 'numFmt'), level.find(W + 'start')
                formats[(abstract.get(W+'abstractNumId'), level.get(W+'ilvl', '0'))] = (
                    fmt.get(W+'val', '') if fmt is not None else '',
                    int(start.get(W+'val', '1')) if start is not None else 1)
        for num in numbering.findall(W + 'num'):
            abstract = num.find(W + 'abstractNumId')
            if abstract is not None:
                definitions[num.get(W+'numId')] = abstract.get(W+'val')
            for level in num.findall(W+'lvlOverride'):
                start = level.find(W+'startOverride')
                if start is not None:
                    overrides[(num.get(W+'numId'), level.get(W+'ilvl','0'))] = int(start.get(W+'val','1'))

    def text_of(node):
        if node.tag in {W+t for t in ('drawing','pict','object','txbxContent')}:
            return ''
        if node.tag == W+'t': return node.text or ''
        if node.tag in (W+'br', W+'cr'): return '\n'
        if node.tag == W+'tab': return '\t'
        return ''.join(text_of(child) for child in node)

    def paragraphs(node):
        for child in node:
            if child.tag == W+'p': yield child
            elif child.tag in {W+t for t in ('tbl','tr','tc','sdt','sdtContent')}:
                yield from paragraphs(child)

    records, size = [], 0
    for line, paragraph in enumerate(paragraphs(body), 1):
        text = unicodedata.normalize('NFKC', text_of(paragraph)).strip()
        numpr = paragraph.find(W+'pPr/'+W+'numPr')
        if text and numpr is not None:
            numid, level = numpr.find(W+'numId'), numpr.find(W+'ilvl')
            if numid is not None:
                key = (numid.get(W+'val'), level.get(W+'val','0') if level is not None else '0')
                fmt, start = formats.get((definitions.get(key[0]), key[1]), ('', 1))
                counters[key] = counters.get(key, overrides.get(key, start)-1)+1
                value = counters[key]
                for nested in list(counters):
                    if nested[0] == key[0] and int(nested[1]) > int(key[1]):
                        del counters[nested]
                if not OPTION.match(text) and not NUMBERED.match(text) and not HEADING.match(text):
                    if fmt == 'decimal': text = f'{value}) {text}'
                    elif fmt in ('upperLetter','lowerLetter') and 1 <= value <= 26:
                        text = f'{chr(64+value)}) {text}'
        size += len(text)
        if size > 250_000 or line > 12000:
            raise HTTPException(422, 'Belge çok uzun. En fazla 250.000 karakterlik bölümler halinde yükleyin.')
        for token in LINES.tokenize(text):
            token = token.strip()
            if token: records.append((line, token))
    if not records:
        raise HTTPException(422, 'Dosyada okunabilir metin bulunamadı. Taranmış görsel yerine metin içeren DOCX yükleyin.')
    return records, warnings

def extract(filename, content):
    try:
        records, warnings = document_lines(filename, content)
    except (ValueError, OverflowError, RecursionError):
        raise HTTPException(422, 'Word numaralandırması veya belge yapısı okunamadı.')
    questions, pending, current, keys = [], [], None, {}
    in_key = False
    raw_source = '\n'.join(f'{line}: {text}' for line, text in records)

    def new_question(number=None, line=None, parts=None):
        return {'number':number, 'source_line':line, 'parts':parts or [], 'slots':{}, 'letters':[],
                'answer_text':'', 'tail':[], 'topic':'', 'hint':'', 'explanation':'', 'source':[], 'warnings':[]}

    def flush_tail():
        if current['tail'] and current['slots']:
            last = next(reversed(current['slots']))
            current['slots'][last] += '\n' + '\n'.join(current['tail'])
            current['tail'] = []

    def finish():
        if current is None: return
        flush_tail()
        if len(questions) >= 300:
            raise HTTPException(422, 'En fazla 300 soru destekleniyor.')
        questions.append(current)

    def process(line, text):
        nonlocal current, pending
        match = HEADING.match(text) or NUMBERED.match(text)
        if match:
            finish()
            number = int(match[1]) if match[1] else None
            current = new_question(number, line)
            current['source'].append(text)
            tail = match[2] or ''
            topic = re.match(r'^\s*(?:[-–—]\s*)?konu\s*:\s*(.*)$', tail, re.I)
            if topic: current['topic'] = topic[1]
            elif tail: current['parts'].append(tail)
            pending = []
            return
        answer = ANSWER.match(text)
        option = OPTION.match(text)
        if current is None:
            if option:
                current = new_question(line=line, parts=pending.copy())
                current['warnings'].append('Soru numarası bulunamadı; metin sınırlarını kontrol edin.')
                pending = []
            else:
                pending.append(text)
                return
        if option and option[1].upper() == 'A' and current['slots'] and (current['tail'] or current['letters']):
            between = current['tail']; current['tail'] = []
            finish()
            current = new_question(line=line, parts=between)
            current['warnings'].append('Yeni soru şıklardan ayrıldı; soru metnini kontrol edin.')
        current['source'].append(text)
        if answer:
            flush_tail()
            value = ANSWER_LETTER.match(answer[1].strip())
            answer_text = ''
            if value:
                current['letters'].append(value[1].upper())
                if re.match(r'^\(?[A-Ea-e]\)?[).:\-]', answer[1].strip()):
                    answer_text = value[2].strip()
            elif answer[1].strip():
                answer_text = answer[1].strip()
            if answer_text:
                if current['answer_text'] and fold(current['answer_text']) != fold(answer_text):
                    current['letters'].append('?')
                    current['warnings'].append('Birden fazla farklı cevap metni var; doğru şıkkı seçin.')
                current['answer_text'] = answer_text
            return
        if option:
            flush_tail()
            label = option[1].upper()
            if label in current['slots']:
                current['warnings'].append(f'{label} şıkkı birden fazla yazılmış; birleştirilen metni düzeltin.')
                current['slots'][label] += '\n' + option[2]
                current['letters'].append('?')
            else: current['slots'][label] = option[2].strip()
            return
        hint = re.match(r'^(?:ipucu|hint)\s*:\s*(.*)$', text, re.I)
        explanation = re.match(r'^(?:açıklama|aciklama|explanation)\s*:\s*(.*)$', text, re.I)
        if hint:
            current['hint'] += ('\n' if current['hint'] else '') + hint[1]
        elif explanation:
            current['explanation'] += ('\n' if current['explanation'] else '') + explanation[1]
        elif current['letters'] or current['answer_text']:
            current['explanation'] += ('\n' if current['explanation'] else '') + text
        elif current['slots']:
            current['tail'].append(text)
        else: current['parts'].append(text)

    for line, text in records:
        key_heading = KEY_HEADING.match(text)
        if key_heading:
            in_key = True
            text = next((part for part in key_heading.groups() if part), '')
        if in_key:
            pairs = KEY_PAIR.findall(text)
            for number, letter in pairs: keys.setdefault(int(number), set()).add(letter.upper())
            if text.strip() and not pairs:
                warnings.append(f'Paragraf {line}: Cevap anahtarındaki satır ayrıştırılamadı; kaynak metinden kontrol edin.')
            continue
        # A) ... B) ... on one line: split only ordered label sequences starting at A,
        # or a single option at the beginning. Clinical abbreviations remain text.
        for segment in ([text] if ANSWER.match(text) else INLINE_ANSWER.split(text)):
            spans = list(OPTION_MARKERS.span_tokenize(segment))
            labels = [segment[a:b].strip()[0].upper() for a,b in spans]
            inline = len(spans) >= 2 and labels == [chr(65+i) for i in range(len(labels))]
            if inline:
                if segment[:spans[0][0]].strip(): process(line, segment[:spans[0][0]].strip())
                for i, (start, _) in enumerate(spans):
                    end = spans[i+1][0] if i+1 < len(spans) else len(segment)
                    process(line, segment[start:end].strip())
            else: process(line, segment)
    finish()
    if not questions:
        questions = [new_question(line=records[0][0])]
        warnings.append('Soru sınırları bulunamadı. Kaynak metni kullanarak soruları aşağıda oluşturun.')
    result, numbers = [], [q['number'] for q in questions if q['number'] is not None]
    for i, q in enumerate(questions, 1):
        slots = q['slots']
        count = max([ord(label)-64 for label in slots] or [2])
        options = [slots.get(chr(65+j), '').strip() for j in range(count)]
        letters = set(q['letters'])
        if q['number'] in keys:
            if numbers.count(q['number']) == 1: letters.update(keys[q['number']])
            else: q['warnings'].append('Soru numarası tekrarlanıyor; cevap anahtarı otomatik uygulanmadı.')
        correct = ord(next(iter(letters)))-65 if len(letters) == 1 and next(iter(letters)) in 'ABCDE' else None
        if q['answer_text']:
            matches = [j for j, o in enumerate(options) if o and fold(o) == fold(q['answer_text'])]
            if correct is None and not letters and len(matches) == 1: correct = matches[0]
            elif correct is not None and q['answer_text'] and (not matches or correct not in matches):
                correct = None
                q['warnings'].append('Cevap harfi ile cevap metni eşleşmiyor; doğru şıkkı seçin.')
        if correct is not None and not 0 <= correct < len(options): correct = None
        if correct is None: q['warnings'].append('Tek bir doğru cevap belirlenemedi; doğru şıkkı seçin.')
        if not q['parts']: q['warnings'].append('Soru metni eksik.')
        if not 2 <= len(options) <= 5 or any(not o for o in options):
            q['warnings'].append('2–5 dolu şık olmalı. Eksik veya fazla şıkları düzeltin.')
        result.append({'text':'\n'.join(q['parts']).strip(), 'options':options, 'correct':correct,
                       'topic':q['topic'], 'hint':q['hint'], 'explanation':q['explanation'],
                       'source_line':q['source_line'], 'source_text':'\n'.join(q['source']), 'warnings':q['warnings']})
    unmatched = set(keys) - set(numbers)
    if unmatched: warnings.append('Bazı cevap anahtarı numaraları sorularla eşleştirilemedi: ' + ', '.join(map(str, sorted(unmatched))))
    return {'questions':result, 'warnings':warnings, 'source_text':raw_source}
