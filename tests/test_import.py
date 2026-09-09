import io
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import pytest
from fastapi import HTTPException
from app.importer import parse_file

SAMPLE=Path(__file__).parent/'fixtures/uroloji.docx'

def docx(paragraphs):
    body=''.join(f'<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>' for text in paragraphs)
    xml=f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    buffer=io.BytesIO()
    with ZipFile(buffer,'w',ZIP_DEFLATED) as z:z.writestr('word/document.xml',xml)
    return buffer.getvalue()

def test_real_sample_upload_preview_save(setup):
    app,admin,_=setup
    result=admin.post('/api/admin/imports/preview',content=SAMPLE.read_bytes(),headers={'X-Filename':'uroloji.docx','X-Exam-Title':'Uroloji'} )
    assert result.status_code==200,result.text
    data=result.json()
    assert len(data['questions'])==10
    assert [q['correct'] for q in data['questions']]==[1,2,1,3,0,0,2,3,3,0]
    assert all(len(q['options'])==4 and q['explanation'] and q['hint'] for q in data['questions'])
    assert admin.get('/api/admin/exams').json()==[]
    assert admin.post('/api/admin/exams',json={'preview_id':data['preview_id']}).status_code==200
    assert admin.get('/api/admin/exams').json()[0]['question_count']==10

def test_docx_two_to_five_options():
    paragraphs=['Örnek sınav']
    for number,count in enumerate(range(2,6),1):
        paragraphs.extend([f'Soru {number} - Konu: Test',f'Soru metni {number}'])
        paragraphs.extend(f'{chr(65+i)}) Şık {i}' for i in range(count))
        paragraphs.append('Doğru Cevap & Açıklama:\nCevap: A) Şık 0\nDoğru! Açıklama.')
    result=parse_file('test.docx',docx(paragraphs))
    assert [len(q['options']) for q in result]==[2,3,4,5]

@pytest.mark.parametrize('paragraphs',[
    ['Soru 1 - Konu: Test','A) A','B) B','Doğru Cevap & Açıklama:\nCevap: A) A'],
    ['Soru 1 - Konu: Test','Soru?','A) A','C) C','Doğru Cevap & Açıklama:\nCevap: A) A'],
    ['Soru 1 - Konu: Test','Soru?','A) A','B) B','Doğru Cevap & Açıklama:\nCevap: E) E'],
    ['Soru 1 - Konu: Test','Soru?','A) A','B) ','Doğru Cevap & Açıklama:\nCevap: A) A'],
    ['Soru 1 - Konu: Test','Soru?','A) A','B) B','Doğru Cevap & Açıklama:\nCevap: A) Yanlış metin'],
    ['Soru 1 - Konu: Test','Soru?','A) A','B) B','Doğru Cevap & Açıklama:\nCevap: A) A\nCevap: B) B'],
])
def test_malformed_document_rejected_atomically(setup,paragraphs):
    app,admin,_=setup
    response=admin.post('/api/admin/imports/preview',content=docx(paragraphs),headers={'X-Filename':'test.docx','X-Exam-Title':'test'})
    assert response.status_code==422
    assert 'Soru 1' in response.text
    assert admin.get('/api/admin/exams').json()==[]

def test_zip_bomb_and_xml_entities_rejected():
    buffer=io.BytesIO()
    with ZipFile(buffer,'w',ZIP_DEFLATED) as z:z.writestr('word/document.xml',b'x'*(21*1024*1024))
    with pytest.raises(HTTPException):parse_file('test.docx',buffer.getvalue())
    buffer=io.BytesIO()
    with ZipFile(buffer,'w') as z:z.writestr('word/document.xml','<!DOCTYPE foo [<!ENTITY x "bad">]><foo/>')
    with pytest.raises(HTTPException):parse_file('test.docx',buffer.getvalue())

def test_hints_and_explanations_do_not_leak(setup):
    from conftest import participant
    from test_flow import control,get_state,expire
    app,admin,_=setup
    import secrets
    result=admin.post('/api/admin/imports/preview',content=SAMPLE.read_bytes(),headers={'X-Filename':'uroloji.docx','X-Exam-Title':'Uroloji'}).json()
    exam=admin.post('/api/admin/exams',json={'preview_id':result['preview_id']}).json()['exam_id']
    sid=admin.post(f'/api/admin/exams/{exam}/sessions',json={'request_id':secrets.token_urlsafe(24)}).json()['session_id']
    p=participant(app,sid,'katilimci');control(admin,sid,'start')
    q=get_state(p,sid)['question']
    for field in ['correct','hint','explanation']:assert field not in q
    expire(app,sid)
    q=get_state(p,sid)['question']
    assert q['hint'] and q['explanation'] and q['correct']==1
