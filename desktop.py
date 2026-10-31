"""Windows başlatıcı: sunucuyu açar, Cloudflare hızlı tüneliyle herkese açık HTTPS adresi alır.

Tek exe olarak paketlenir (BilkentSinav.spec → dist/Bilkent Sınav.exe).
Veritabanı exe'nin yanındaki data/ klasöründe durur. Geliştirmede: python desktop.py
"""
import re
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

FROZEN = getattr(sys, 'frozen', False)
BUNDLE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
HOME = Path(sys.executable).resolve().parent if FROZEN else BUNDLE
DATA = HOME / 'data'
TUNNEL_URL = re.compile(r'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com')
TITLE = 'Bilkent Sınav'

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

def admin_password():
    # Panelin kendi şifresi: exe yanındaki .env, yoksa projenin varsayılanı (.env.example).
    # Panelde Ayarlar'dan değiştirilen şifre veritabanında tutulur ve bunun yerine geçer.
    from dotenv import dotenv_values
    for path in (HOME / '.env', BUNDLE / '.env.example'):
        if password := dotenv_values(path).get('ADMIN_PASSWORD'):
            return password
    raise RuntimeError('ADMIN_PASSWORD bulunamadı.')

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
          f'{line}\n', flush=True)
    webbrowser.open(f'{url}/admin')

def prepare_console():
    # Çıktı dosyaya/boruya yönlenince Windows cp1254 kullanır; Türkçe ve çerçeve karakterleri çökmesin.
    for stream in (sys.stdout, sys.stderr):
        if stream and not stream.isatty():
            stream.reconfigure(encoding='utf-8', errors='replace')
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW(TITLE)

def main():
    # Uygulama içe aktarmaları burada: eksik modül olursa pencere anında kapanmasın, hata görünsün.
    import uvicorn
    from app.config import Settings
    from app.db import Database
    from app.main import create_app

    DATA.mkdir(exist_ok=True)
    database = DATA / 'exam.db'
    db = Database(database)
    db.migrate()
    port = free_port()
    print('Cloudflare bağlantısı hazırlanıyor...', flush=True)
    tunnel = open_tunnel(port)
    settings = Settings(admin_password(), tunnel.url, f'sqlite:///{database.as_posix()}', True)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=port, workers=1,
                                           proxy_headers=True, forwarded_allow_ips='127.0.0.1', log_level='warning'))
    threading.Thread(target=announce, args=(server, tunnel, tunnel.url), daemon=True).start()
    keep_awake()
    try:
        server.run()
    finally:
        tunnel.stop()

if __name__ == '__main__':
    prepare_console()
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f'\nHata: {error}')
        input('Kapatmak için Enter tuşuna basın...')
