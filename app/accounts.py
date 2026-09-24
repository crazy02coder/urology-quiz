"""Yönetici hesabı: şifre değiştirilene kadar .env'deki ADMIN_PASSWORD geçerlidir.

Değiştirilen şifre düz metin olarak değil, tuzlu scrypt özeti olarak saklanır.
"""
import base64
import hashlib
import hmac
import secrets
import time

USERNAME = 'admin'
SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1}
MIN_LENGTH, MAX_LENGTH = 8, 128

RULES = (
    (lambda value: len(value) >= MIN_LENGTH, f'En az {MIN_LENGTH} karakter olmalı.'),
    (lambda value: any(c.isupper() for c in value), 'En az bir büyük harf içermeli.'),
    (lambda value: any(c.islower() for c in value), 'En az bir küçük harf içermeli.'),
    (lambda value: any(c.isdigit() for c in value), 'En az bir rakam içermeli.'),
    (lambda value: any(not c.isalnum() and not c.isspace() for c in value), 'En az bir özel karakter içermeli.'),
)

def _b64(data):
    return base64.b64encode(data).decode('ascii')

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${_b64(salt)}${_b64(digest)}"

def check_hash(stored, password):
    try:
        scheme, n, r, p, salt, expected = stored.split('$')
        if scheme != 'scrypt':
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False

def credentials(conn):
    return conn.execute('SELECT username,password_hash FROM admin_credentials WHERE id=1').fetchone()

def username(conn):
    row = credentials(conn)
    return row['username'] if row else USERNAME

def verify(conn, settings, password):
    row = credentials(conn)
    if row:
        return check_hash(row['password_hash'], password)
    return hmac.compare_digest(password.encode(), settings.admin_password.encode())

def password_problems(password):
    if len(password) > MAX_LENGTH:
        return [f'En fazla {MAX_LENGTH} karakter olabilir.']
    return [message for test, message in RULES if not test(password)]

def set_password(conn, password):
    conn.execute('INSERT INTO admin_credentials(id,username,password_hash,updated_at) VALUES (1,?,?,?)'
                 ' ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash, updated_at=excluded.updated_at',
                 (username(conn), hash_password(password), time.time()))
