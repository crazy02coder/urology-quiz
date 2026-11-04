"""Bitmiş oturumun dışa aktarımı: tek sayfalık Excel özeti ve kişi bazlı PDF cevap dökümü."""
import io
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from PIL import Image as PILImage
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import ROOT

XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PDF_TYPE = 'application/pdf'
LOGO = ROOT / 'app/static/img/saglik-bakanligi.png'
FONTS = {'NotoSans': 'NotoSans-Regular.ttf', 'NotoSans-SemiBold': 'NotoSans-SemiBold.ttf', 'NotoSans-Bold': 'NotoSans-Bold.ttf'}
# Türkiye'de tek saat dilimi var; Render UTC çalıştığı için yerel saate güvenilmez.
TURKEY = timezone(timedelta(hours=3))

TEAL, TEAL_SOFT, INK, MUTED, LINE = '076E68', 'EAF3F3', '152B39', '536675', 'D9E4E9'
OK_BG, OK_TEXT, BAD_BG, BAD_TEXT, BLANK_BG = 'DDF1E4', '145D3B', 'FBE3E5', '94323F', 'EEF2F4'

def letter(index):
    return chr(65 + index)

def when(timestamp):
    return datetime.fromtimestamp(timestamp, TURKEY).strftime('%d.%m.%Y %H:%M') if timestamp else '-'

def pick_of(question, answers):
    choice = answers.get(question['id'])
    return choice if choice is not None and 0 <= choice < len(question['options']) else None

def score_of(questions, answers):
    picks = [pick_of(q, answers) for q in questions]
    correct = sum(pick == q['correct'] for pick, q in zip(picks, questions))
    blank = picks.count(None)
    percent = correct / len(questions) if questions else 0.0
    return {'correct': correct, 'wrong': len(questions) - correct - blank, 'blank': blank, 'ratio': percent}

def put_text(sheet, row, column, value):
    # Takma ad ve soru metni dışarıdan gelir: "=" ile başlayan değer formül olarak çalışmamalı.
    cell = sheet.cell(row, column)
    cell.value = ILLEGAL_CHARACTERS_RE.sub('', str(value))
    cell.data_type = 's'
    return cell

def session_workbook(data):
    """Satırlar kişi, sütunlar soru: her hücrede işaretlenen şık, üstte doğru cevap, altta soru listesi."""
    questions, fixed = data['questions'], ('Sıra', 'Katılımcı', 'Deneyim (yıl)', 'Doğru', 'Yanlış', 'Boş', 'Başarı')
    first_question = len(fixed) + 1
    people = sorted(((person, score_of(questions, person['answers'])) for person in data['participants']),
                    key=lambda item: (-item[1]['correct'], item[0]['nickname'].casefold()))

    book = Workbook()
    sheet = book.active
    sheet.title = 'Sonuçlar'
    side = Side(style='thin', color=LINE)
    border = Border(left=side, right=side, top=side, bottom=side)
    center = Alignment(horizontal='center', vertical='center')
    fill = lambda color: PatternFill('solid', start_color=color, end_color=color)

    put_text(sheet, 1, 1, data['title']).font = Font(bold=True, size=14, color=TEAL)
    put_text(sheet, 2, 1, f"Başlangıç: {when(data['created_at'])}  ·  Bitiş: {when(data['finished_at'])}  ·  {len(people)} katılımcı  ·  {len(questions)} soru").font = Font(color=MUTED)
    put_text(sheet, 3, 1, 'Hücrelerde işaretlenen şık yazar. Yeşil doğru, kırmızı yanlış, "–" boş. Şıklar tablonun altındaki soru listesindedir.').font = Font(color=MUTED)

    answer_row, count_row, header_row = 5, 6, 7
    for row, label in ((answer_row, 'Doğru cevap'), (count_row, 'Doğru bilen kişi')):
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=len(fixed))
        cell = put_text(sheet, row, 2, label)
        cell.font, cell.alignment = Font(bold=True), Alignment(horizontal='right', vertical='center')
    for column, name in enumerate(fixed, 1):
        put_text(sheet, header_row, column, name)
    for i, q in enumerate(questions):
        column = first_question + i
        put_text(sheet, header_row, column, f'S{i + 1}')
        cell = put_text(sheet, answer_row, column, letter(q['correct']))
        cell.font, cell.fill, cell.alignment, cell.border = Font(bold=True, color=OK_TEXT), fill(OK_BG), center, border
        cell = sheet.cell(count_row, column, sum(pick_of(q, person['answers']) == q['correct'] for person, _ in people))
        cell.alignment, cell.border = center, border
    last_column = first_question + len(questions) - 1
    for column in range(1, last_column + 1):
        cell = sheet.cell(header_row, column)
        cell.font, cell.fill, cell.alignment, cell.border = Font(bold=True, color='FFFFFF'), fill(TEAL), center, border

    for rank, (person, score) in enumerate(people, 1):
        row = header_row + rank
        values = (rank, None, person['experience_years'], score['correct'], score['wrong'], score['blank'], score['ratio'])
        for column, value in enumerate(values, 1):
            if column != 2:
                sheet.cell(row, column, value).alignment = center
            sheet.cell(row, column).border = border
        put_text(sheet, row, 2, person['nickname'])
        sheet.cell(row, len(fixed)).number_format = '0.0%'
        for i, q in enumerate(questions):
            pick = pick_of(q, person['answers'])
            cell = put_text(sheet, row, first_question + i, '–' if pick is None else letter(pick))
            cell.alignment, cell.border = center, border
            if pick is None:
                cell.fill, cell.font = fill(BLANK_BG), Font(color=MUTED)
            elif pick == q['correct']:
                cell.fill, cell.font = fill(OK_BG), Font(color=OK_TEXT)
            else:
                cell.fill, cell.font = fill(BAD_BG), Font(bold=True, color=BAD_TEXT)
    last_row = header_row + len(people)
    sheet.auto_filter.ref = f'A{header_row}:{get_column_letter(last_column)}{last_row}'
    sheet.freeze_panes = sheet.cell(header_row + 1, 3)

    # Filtre ve sıralama yalnızca yukarıdaki tabloyu etkiler; soru listesi tablo aralığının dışında kalır.
    row = last_row + 2
    put_text(sheet, row, 1, 'Soru listesi').font = Font(bold=True, size=12, color=TEAL)
    for i, q in enumerate(questions):
        row += 1
        lines = [q['text']] + [f"{letter(j)}) {option}{'  (doğru cevap)' if j == q['correct'] else ''}" for j, option in enumerate(q['options'])]
        body = '\n'.join(lines)
        cell = put_text(sheet, row, 1, f'S{i + 1}')
        cell.font, cell.alignment = Font(bold=True), Alignment(horizontal='center', vertical='top')
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=len(fixed))
        put_text(sheet, row, 2, body).alignment = Alignment(wrap_text=True, vertical='top')
        wrapped = sum(max(1, math.ceil(len(part) / 70)) for part in body.split('\n'))
        sheet.row_dimensions[row].height = min(409, 15 * wrapped + 4)

    for column, width in enumerate((6, 28, 13, 8, 8, 8, 10), 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    for column in range(first_question, last_column + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 5.5
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    output = io.BytesIO()
    book.save(output)
    return output.getvalue()

@lru_cache(maxsize=1)
def pdf_styles():
    for name, file in FONTS.items():
        pdfmetrics.registerFont(TTFont(name, str(ROOT / 'app/fonts' / file)))
    pdfmetrics.registerFontFamily('NotoSans', normal='NotoSans', bold='NotoSans-Bold', italic='NotoSans', boldItalic='NotoSans-Bold')
    style = lambda name, font='NotoSans', size=10, leading=None, color=INK, **extra: ParagraphStyle(
        name, fontName=font, fontSize=size, leading=leading or size * 1.32, textColor=HexColor(f'#{color}'), **extra)
    return {
        'brand': style('brand', 'NotoSans-Bold', 13, color=TEAL),
        'brand_small': style('brand_small', size=8.5, color=MUTED),
        'title': style('title', 'NotoSans-Bold', 15, spaceBefore=8, spaceAfter=2),
        'meta': style('meta', size=9.5, color=MUTED, spaceAfter=8),
        'tile_label': style('tile_label', size=8, color=MUTED, alignment=1),
        'tile_value': style('tile_value', 'NotoSans-Bold', 15, alignment=1),
        'number': style('number', 'NotoSans-Bold', 9.5, color=TEAL),
        'question': style('question', 'NotoSans-SemiBold', 10.5, spaceAfter=5),
        'topic': style('topic', size=8.5, color=MUTED, spaceAfter=2),
        'option': style('option', size=9.5),
        'option_letter': style('option_letter', 'NotoSans-Bold', 9.5, alignment=1),
        'status_correct': style('status_correct', 'NotoSans-Bold', 9.5, color=OK_TEXT, alignment=2),
        'status_wrong': style('status_wrong', 'NotoSans-Bold', 9.5, color=BAD_TEXT, alignment=2),
        'status_blank': style('status_blank', 'NotoSans-Bold', 9.5, color=MUTED, alignment=2),
        'mark_correct': style('mark_correct', 'NotoSans-SemiBold', 8, color=OK_TEXT, alignment=2),
        'mark_wrong': style('mark_wrong', 'NotoSans-SemiBold', 8, color=BAD_TEXT, alignment=2),
    }

def para(text, style):
    return Paragraph(escape(ILLEGAL_CHARACTERS_RE.sub('', str(text))).replace('\n', '<br/>'), style)

def picture(data, max_width, max_height):
    # Görseli düz RGB'ye çevirmek saydam PNG ve WebP için de aynı sonucu verir.
    try:
        with PILImage.open(io.BytesIO(data)) as source:
            image = source.convert('RGBA')
    except OSError:
        return None
    flat = PILImage.new('RGB', image.size, 'white')
    flat.paste(image, mask=image.getchannel('A'))
    buffer = io.BytesIO()
    flat.save(buffer, 'PNG')
    buffer.seek(0)
    scale = min(max_width / flat.width, max_height / flat.height, .75)
    return Image(buffer, flat.width * scale, flat.height * scale, hAlign='LEFT')

def question_block(q, index, width, styles):
    pick, correct = q['own_choice'], q['correct']
    status, label = (('status_blank', 'Boş bırakıldı') if pick is None
                     else ('status_correct', 'Doğru') if pick == correct else ('status_wrong', 'Yanlış'))
    head = Table([[para(f'SORU {index + 1}', styles['number']), para(label, styles[status])]], colWidths=[width * .6, width * .4])
    head.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                              ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    parts = [head]
    if q.get('topic'):
        parts.append(para(q['topic'], styles['topic']))
    parts.append(para(q['text'], styles['question']))
    for data in q['pictures']:
        image = picture(data, width, 70 * mm)
        if image:
            parts += [image, Spacer(1, 5)]

    rows, commands = [], [('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LINEBELOW', (0, 0), (-1, -1), .5, HexColor(f'#{LINE}')),
                          ('LINEABOVE', (0, 0), (-1, 0), .5, HexColor(f'#{LINE}')),
                          ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]
    for j, option in enumerate(q['options']):
        if j == correct:
            mark = para('İşaretlediği · Doğru cevap' if pick == j else 'Doğru cevap', styles['mark_correct'])
            commands.append(('BACKGROUND', (0, j), (-1, j), HexColor(f'#{OK_BG}')))
        elif j == pick:
            mark = para('İşaretlediği · Yanlış', styles['mark_wrong'])
            commands.append(('BACKGROUND', (0, j), (-1, j), HexColor(f'#{BAD_BG}')))
        else:
            mark = ''
        rows.append([para(letter(j), styles['option_letter']), para(option, styles['option']), mark])
    table = Table(rows, colWidths=[9 * mm, width - 44 * mm, 35 * mm])
    table.setStyle(TableStyle(commands))
    parts += [table, Spacer(1, 13)]
    return KeepTogether(parts)

def participant_pdf(data):
    """Kişinin cevap kâğıdı: tüm sorular, işaretlediği şık, doğru cevap ve sonuç."""
    styles = pdf_styles()
    questions, person = data['questions'], data['participant']
    answers = {q['id']: q['own_choice'] for q in questions if q['own_choice'] is not None}
    score = score_of(questions, answers)
    for q in questions:
        q['own_choice'] = pick_of(q, answers)

    margin = 18 * mm
    width = A4[0] - 2 * margin
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=16 * mm, bottomMargin=17 * mm,
                                 title=f"{person['nickname']} - {data['title']}", author='Bilkent Şehir Hastanesi')

    brand = Table([[Image(str(LOGO), 13 * mm, 13 * mm, mask='auto'),
                    [para('Bilkent Şehir Hastanesi', styles['brand']), para('Personel eğitimleri · Cevap dökümü', styles['brand_small'])]]],
                  colWidths=[16 * mm, width - 16 * mm])
    brand.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))

    tiles = [('Doğru', score['correct'], OK_TEXT), ('Yanlış', score['wrong'], BAD_TEXT), ('Boş', score['blank'], MUTED),
             ('Başarı', f"%{round(100 * score['ratio'], 1):g}", TEAL)]
    tile_row = [[para(label, styles['tile_label']),
                 Paragraph(escape(str(value)), ParagraphStyle(f'tile_{label}', parent=styles['tile_value'], textColor=HexColor(f'#{color}')))]
                for label, value, color in tiles]
    summary = Table([tile_row], colWidths=[width / 4] * 4)
    summary.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), HexColor(f'#{TEAL_SOFT}')),
                                 ('INNERGRID', (0, 0), (-1, -1), 3, HexColor('#FFFFFF')),
                                 ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 9)]))

    story = [brand, para(person['nickname'], styles['title']),
             para(f"{data['title']}  ·  {person['experience_years']} yıl deneyim  ·  {when(data['finished_at'])}", styles['meta']),
             summary, Spacer(1, 16)]
    story += [question_block(q, i, width, styles) for i, q in enumerate(questions)]

    footer = ILLEGAL_CHARACTERS_RE.sub('', f"{person['nickname']} · {data['title']}")
    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('NotoSans', 8)
        canvas.setFillColor(HexColor(f'#{MUTED}'))
        canvas.drawString(margin, 10 * mm, footer[:90])
        canvas.drawRightString(A4[0] - margin, 10 * mm, f'Sayfa {doc.page}')
        canvas.restoreState()
    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return output.getvalue()
