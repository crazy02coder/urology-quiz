"""Read embedded DOCX pictures without fetching external relationships or OCR."""
import base64
import io
import posixpath
import secrets
import warnings
from urllib.parse import unquote
from zipfile import ZipFile, BadZipFile

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
V = '{urn:schemas-microsoft-com:vml}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
MIMES = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}


def selected_children(node):
    # Word often duplicates a picture as a modern drawing and a legacy fallback.
    if node.tag == MC + 'AlternateContent':
        branch = node.find(MC + 'Choice')
        if branch is None:
            branch = node.find(MC + 'Fallback')
        return [branch] if branch is not None else []
    return list(node)


class Pictures:
    def __init__(self, content):
        # Called only after load_docx has enforced archive size and XML limits.
        self.content = content
        self.assets = {}
        self.by_path = {}
        self.relationships = {}
        self.total = 0
        with ZipFile(io.BytesIO(content)) as archive:
            path = 'word/_rels/document.xml.rels'
            if path not in archive.namelist():
                return
            if archive.getinfo(path).file_size > 1024 * 1024:
                raise HTTPException(422, 'Word görsel bağlantıları çok büyük.')
            try:
                root = SafeET.fromstring(archive.read(path), forbid_dtd=True)
            except (ParseError, DefusedXmlException, BadZipFile, RuntimeError, OSError):
                raise HTTPException(422, 'Word görsel bağlantıları okunamadı.')
            self.relationships = {r.get('Id'): r.attrib for r in root}

    def read(self, drawing):
        refs = []

        def visit(node):
            if node.tag in (A + 'blip', V + 'imagedata'):
                rid = node.get(R + 'embed') or node.get(R + 'id')
                if not rid or node.get(R + 'link'):
                    raise HTTPException(422, 'Bağlantılı görsel desteklenmiyor. Resmi Word dosyasına gömülü olarak ekleyin.')
                refs.append(rid)
                return
            for child in selected_children(node):
                visit(child)

        visit(drawing)
        if not refs:
            raise HTTPException(422, 'Word şekli veya grafiği doğrudan okunamadı. PNG veya JPG resim olarak ekleyin.')
        return [self.asset(rid) for rid in dict.fromkeys(refs)]

    def asset(self, rid):
        rel = self.relationships.get(rid, {})
        if rel.get('TargetMode', '').lower() == 'external' or not rel.get('Type', '').endswith('/image'):
            raise HTTPException(422, 'Görsel dosyanın içine gömülü olmalı; dış bağlantılar okunmaz.')
        target = unquote(rel.get('Target', '')).replace('\\', '/')
        path = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'word/' + target)
        if not path.startswith('word/media/') or '?' in path or '#' in path:
            raise HTTPException(422, 'Geçersiz Word görsel yolu.')
        if path in self.by_path:
            return self.by_path[path]
        with ZipFile(io.BytesIO(self.content)) as archive:
            try:
                info = archive.getinfo(path)
                if info.file_size > 5 * 1024 * 1024:
                    raise HTTPException(422, 'Tek görsel en fazla 5 MB olabilir.')
                data = archive.read(path)
            except (KeyError, BadZipFile, RuntimeError, OSError):
                raise HTTPException(422, 'Word dosyasındaki bir görsel eksik veya bozuk.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as picture:
                    mime = MIMES.get(picture.format)
                    if not mime:
                        raise HTTPException(422, 'Görseller PNG, JPG veya WebP olmalı. Word içinde resmi bu biçimlerden biriyle değiştirin.')
                    if picture.width * picture.height > 16_000_000:
                        raise HTTPException(422, 'Görsel en fazla 16 megapiksel olabilir. Resmi küçültüp yeniden yükleyin.')
                    picture.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(422, 'Görsel bozuk veya çok büyük. PNG veya JPG olarak yeniden ekleyin.')
        self.total += len(data)
        if self.total > 15 * 1024 * 1024 or len(self.assets) >= 100:
            raise HTTPException(422, 'Bir dosyada en fazla 100 farklı görsel ve toplam 15 MB görsel içeriği olabilir.')
        image_id = secrets.token_urlsafe(24)
        self.assets[image_id] = {'mime_type': mime, 'data': base64.b64encode(data).decode('ascii')}
        self.by_path[path] = image_id
        return image_id
