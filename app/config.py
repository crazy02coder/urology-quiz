import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

@dataclass
class Settings:
    admin_password: str
    public_base_url: str
    database_url: str
    cookie_secure: bool = True

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / '.env')
        password = os.getenv('ADMIN_PASSWORD', '')
        base = (os.getenv('PUBLIC_BASE_URL') or os.getenv('RENDER_EXTERNAL_URL', '')).rstrip('/')
        secure = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
        parsed = urlsplit(base)
        if not password:
            raise RuntimeError('ADMIN_PASSWORD tanımlanmalı. .env.example dosyasına bakın.')
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise RuntimeError('PUBLIC_BASE_URL geçerli bir origin olmalı; örnek: https://sinav.onrender.com')
        if parsed.scheme == 'https' and not secure:
            raise RuntimeError('HTTPS ortamında COOKIE_SECURE=true olmalı.')
        if os.getenv('RENDER') and (parsed.scheme != 'https' or parsed.hostname in ('localhost', '127.0.0.1') or not secure):
            raise RuntimeError('Render için PUBLIC_BASE_URL gerçek HTTPS adresi ve COOKIE_SECURE=true olmalı.')
        return cls(password, base, os.getenv('DATABASE_URL', 'sqlite:///./data/exam.db'), secure)

    @property
    def allowed_origins(self):
        origins = {self.public_base_url}
        parsed = urlsplit(self.public_base_url)
        # Uvicorn prints 127.0.0.1 while the local .env uses localhost.
        # Only equivalent loopback origins on the configured HTTP port qualify.
        if not self.cookie_secure and parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1'):
            port = parsed.port or 80
            suffix = f':{port}' if port != 80 else ''
            origins.update(f'http://{host}{suffix}' for host in ('localhost', '127.0.0.1', '[::1]'))
        return origins

    @property
    def database_path(self):
        if not self.database_url.startswith('sqlite:///'):
            raise RuntimeError('Yalnızca sqlite:/// bağlantıları destekleniyor.')
        path = Path(self.database_url[len('sqlite:///'):])
        return (path if path.is_absolute() else ROOT / path).resolve()
