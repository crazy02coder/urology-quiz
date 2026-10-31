"""Windows başlatıcı: sunucuyu açar, Cloudflare hızlı tüneliyle herkese açık HTTPS adresi alır.

Tek exe olarak paketlenir (BilkentSinav.spec, .github/workflows/windows-exe.yml).
Veritabanı exe'nin yanındaki data/ klasöründe durur. Geliştirmede: python desktop.py
"""
import getpass
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from contextlib import suppress
from pathlib import Path

import uvicorn

from app import accounts
from app.config import Settings
from app.db import Database
from app.main import create_app

FROZEN = getattr(sys, 'frozen', False)
BUNDLE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
HOME = Path(sys.executable).resolve().parent if FROZEN else BUNDLE
DATA = HOME / 'data'
TUNNEL_URL = re.compile(r'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com')

class Tunnel:
    """Hesap gerektirmez; her açılışta yeni bir trycloudflare.com adresi verir."""
    def __init__(self, binary, port):
        self.url, self.found, self.connected = None, threading.Event(), threading.Event()
        self.process = subprocess.Popen(
            [str(binary), 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{port}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        # Çıktı sürekli okunmazsa boru dolar ve cloudflared kilitlenir.
        with (DATA / 'tunnel.log').open('w', encoding='utf-8') as log:
            for line in self.process.stdout:
                log.write(line)
                log.flush()
                match = TUNNEL_URL.search(line)
                if match and not self.url:
                    self.url = match.group(0)
                    self.found.set()
                if 'Registered tunnel connection' in line:
                    self.connected.set()
        self.found.set()

    def stop(self):
        if self.process.poll() is None:
            self.process.terminate()
            with suppress(subprocess.TimeoutExpired):
                self.process.wait(5)

def cloudflared():
    for path in (BUNDLE / 'cloudflared.exe', HOME / 'cloudflared.exe'):
        if path.exists():
            return path
    if found := shutil.which('cloudflared'):
        return Path(found)
    raise RuntimeError('cloudflared bulunamadı.')

def open_tunnel(port):
    binary = cloudflared()
    for attempt in range(3):
        tunnel = Tunnel(binary, port)
        tunnel.found.wait(45)
        if tunnel.url:
            return tunnel
        tunnel.stop()
        if attempt < 2:
            print('  Cloudflare yanıt vermedi, yeniden deneniyor...')
            time.sleep(3)
    raise RuntimeError('Cloudflare bağlantısı kurulamadı. İnternet bağlantısını kontrol edin (ayrıntı: data/tunnel.log).')

def free_port(preferred=8000):
    for port in (preferred, 0):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
                return probe.getsockname()[1]
            except OSError:
                continue

def ensure_password(db):
    with db.connect() as conn:
        if accounts.credentials(conn):
            return
    print('İlk kurulum: yönetici şifresini belirleyin (kullanıcı adı: admin).')
    while True:
        password = getpass.getpass('Yeni şifre: ')
        if problems := accounts.password_problems(password):
            print('\n'.join(f'  - {problem}' for problem in problems))
            continue
        if getpass.getpass('Şifre tekrar: ') != password:
            print('  - Şifreler aynı değil.')
            continue
        break
    with db.transaction() as conn:
        accounts.set_password(conn, password)
    print('Şifre kaydedildi. Sonradan yönetici panelindeki Ayarlar’dan değiştirebilirsiniz.\n')

def keep_awake():
    # Sınav sürerken Windows uyku moduna geçmesin.
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)

def announce(server, tunnel, url):
    while not server.started:
        time.sleep(.2)
    tunnel.connected.wait(30)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f'{url}/healthz', timeout=5) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    line = '═' * 62
    print(f'\n{line}\n  Bilkent Şehir Hastanesi · Canlı Eğitim\n\n'
          f'  Yönetici paneli : {url}/admin\n'
          f'  Sınav adresi    : {url}\n\n'
          '  Bu pencere açık kaldığı sürece sınav yayında.\n'
          '  Kapatınca sınav durur. Adres her açılışta değişir;\n'
          '  QR kodu yönetici panelinden alın.\n'
          f'{line}\n')
    webbrowser.open(f'{url}/admin')

def main():
    DATA.mkdir(exist_ok=True)
    database = DATA / 'exam.db'
    db = Database(database)
    db.migrate()
    ensure_password(db)
    port = free_port()
    print('Cloudflare bağlantısı hazırlanıyor...')
    tunnel = open_tunnel(port)
    # Şifre veritabanındaki özetten doğrulanır; buradaki değer hiçbir zaman kullanılmaz.
    settings = Settings(secrets.token_urlsafe(32), tunnel.url, f'sqlite:///{database.as_posix()}', True)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=port, workers=1,
                                           proxy_headers=True, forwarded_allow_ips='127.0.0.1', log_level='warning'))
    threading.Thread(target=announce, args=(server, tunnel, tunnel.url), daemon=True).start()
    keep_awake()
    try:
        server.run()
    finally:
        tunnel.stop()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f'\nHata: {error}')
        input('Kapatmak için Enter tuşuna basın...')
