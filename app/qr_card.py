"""Yansıtmaya uygun katılım QR kartı: üstte kurum adı, ortada logo, proje renginde çerçeve."""
import io
from functools import lru_cache

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H

from .config import ROOT

LOGO = ROOT / 'app/static/img/saglik-bakanligi.png'
TEAL = (7, 110, 104)
TEAL_SOFT = (234, 243, 243)
INK = (16, 46, 58)
MUTED = (83, 102, 117)
FONTS = (
    '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
    '/Library/Fonts/Arial Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
    '/System/Library/Fonts/Helvetica.ttc',
)

@lru_cache(maxsize=8)
def font(size):
    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)

@lru_cache(maxsize=1)
def logo_image():
    return Image.open(LOGO).convert('RGBA')

def centered(draw, y, text, size, fill, width):
    face = font(size)
    draw.text(((width - draw.textlength(text, font=face)) / 2, y), text, font=face, fill=fill)

def render(url):
    # H düzeyi hata düzeltme: ortadaki logo kodun ~%9'unu kapatsa da okunur kalır.
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=14, border=2)
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color=INK, back_color='white').convert('RGBA')

    side = image.width
    badge_side = int(side * 0.25)
    badge = Image.new('RGBA', (badge_side, badge_side), (0, 0, 0, 0))
    ring = max(4, badge_side // 22)
    ImageDraw.Draw(badge).ellipse((0, 0, badge_side - 1, badge_side - 1), fill='white', outline=TEAL, width=ring)
    emblem = logo_image().copy()
    inner = badge_side - ring * 2 - badge_side // 7
    emblem.thumbnail((inner, inner), Image.LANCZOS)
    badge.alpha_composite(emblem, ((badge_side - emblem.width) // 2, (badge_side - emblem.height) // 2))
    image.alpha_composite(badge, ((side - badge_side) // 2, (side - badge_side) // 2))

    margin, header, footer = 44, 132, 84
    width, height = side + margin * 2, side + margin * 2 + header + footer
    card = Image.new('RGBA', (width, height), 'white')
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((6, 6, width - 7, height - 7), radius=40, outline=TEAL, width=10)
    draw.rounded_rectangle((margin - 10, margin + header - 10, margin + side + 9, margin + header + side + 9),
                           radius=24, fill=TEAL_SOFT)
    centered(draw, margin, 'Bilkent Şehir Hastanesi', 48, INK, width)
    centered(draw, margin + 66, 'PERSONEL EĞİTİMLERİ · CANLI SINAV', 22, TEAL, width)
    card.alpha_composite(image, (margin, margin + header))
    centered(draw, margin + header + side + 30, 'Katılmak için kamerayla okutun', 26, MUTED, width)

    buffer = io.BytesIO()
    card.convert('RGB').save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()
