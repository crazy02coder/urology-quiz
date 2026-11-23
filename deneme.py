"""Deneme sürümü başlatıcısı: ilk açılıştan 2 dakika sonra kalıcı olarak kapanır.

Süre dolduktan sonra her açılışta yalnızca iletişim penceresini gösterir.
BilkentSinav.spec bunu "Bilkent Sınav (Deneme).exe" olarak paketler.
"""
import os
import sys
import time
from pathlib import Path

import desktop

LIMIT = 120
KEY = r'Software\BilkentSinav'
MARK = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BilkentSinav' / 'deneme'
CONTACT = 'Prof. Dr. Serdar Müldür veya yardımcısı Bahadır Arslan'

def _registry(values=None):
    # İlk açılış ve bitiş bilgisi hem kayıt defterinde hem de dosyada tutulur; biri silinse de diğeri kalır.
    import winreg
    if values is None:
        stored = {}
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            for name in ('DenemeBaslangic', 'DenemeBitti'):
                with desktop.suppress(OSError):
                    stored[name] = winreg.QueryValueEx(key, name)[0]
        return stored
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

def _file(values=None):
    if values is None:
        lines = MARK.read_text(encoding='utf-8').splitlines()
        return dict(line.split('=', 1) for line in lines if '=' in line)
    stored = {}
    with desktop.suppress(OSError):
        stored = _file()
    MARK.parent.mkdir(parents=True, exist_ok=True)
    MARK.write_text(''.join(f'{k}={v}\n' for k, v in {**stored, **values}.items()), encoding='utf-8')

def load():
    stored = {}
    for read in (_registry, _file):
        try:
            for name, value in read().items():
                if name == 'DenemeBaslangic':
                    stored[name] = min(float(value), stored.get(name, float('inf')))
                elif value == '1':
                    stored[name] = '1'
        except (OSError, ValueError):
            continue
    return stored

def save(**values):
    for write in (_registry, _file):
        try:
            write(values)
        except OSError:
            continue

def first_run():
    stored = load()
    if 'DenemeBaslangic' not in stored:
        stored['DenemeBaslangic'] = time.time()
        save(DenemeBaslangic=repr(stored['DenemeBaslangic']))
    return stored['DenemeBaslangic'], stored.get('DenemeBitti') == '1'

def show_expired():
    if sys.platform == 'win32':
        import ctypes
        # Konsolu gizle; kullanıcı yalnızca pencereyi görsün.
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    message = ('Bu uygulamanın deneme süresi sona ermiştir.\n\n'
               f'Kullanmaya devam etmek için lütfen {CONTACT} ile iletişime geçin.')
    try:
        dialog(message)
    except Exception:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, desktop.TITLE, 0x30 | 0x40000)

def dialog(message):
    import tkinter as tk
    teal, ink, muted, line, soft = '#076E68', '#152B39', '#536675', '#D9E4E9', '#EAF3F3'
    root = tk.Tk()
    root.title(desktop.TITLE)
    root.configure(bg='white')
    root.resizable(False, False)
    root.attributes('-topmost', True)
    with desktop.suppress(Exception):
        root.iconbitmap(str(desktop.BUNDLE / 'BilkentSinav.ico'))

    header = tk.Frame(root, bg=teal)
    header.pack(fill='x')
    logo = None
    with desktop.suppress(Exception):
        logo = tk.PhotoImage(file=str(desktop.BUNDLE / 'app/static/img/saglik-bakanligi.png')).subsample(8, 8)
        tk.Label(header, image=logo, bg='white', padx=5, pady=5).pack(side='left', padx=(20, 12), pady=14)
    titles = tk.Frame(header, bg=teal)
    titles.pack(side='left', pady=14, padx=(0 if logo else 20, 20))
    tk.Label(titles, text='Bilkent Şehir Hastanesi', bg=teal, fg='white', font=('Segoe UI Semibold', 13)).pack(anchor='w')
    tk.Label(titles, text='Canlı Eğitim · Sınav Uygulaması', bg=teal, fg=soft, font=('Segoe UI', 10)).pack(anchor='w')

    body = tk.Frame(root, bg='white')
    body.pack(fill='both', padx=28, pady=(24, 8))
    badge = tk.Frame(body, bg='#FFF3F3', highlightbackground='#D99197', highlightthickness=1)
    badge.pack(anchor='w')
    tk.Label(badge, text='  ⏱  Deneme süresi doldu  ', bg='#FFF3F3', fg='#94323F', font=('Segoe UI Semibold', 10)).pack(padx=4, pady=3)
    tk.Label(body, text=message, bg='white', fg=ink, font=('Segoe UI', 11), justify='left', wraplength=420).pack(anchor='w', pady=(16, 0))

    tk.Frame(root, bg=line, height=1).pack(fill='x', pady=(20, 0))
    footer = tk.Frame(root, bg='#F3F6F8')
    footer.pack(fill='x')
    tk.Label(footer, text='Bu pencere her açılışta gösterilir.', bg='#F3F6F8', fg=muted, font=('Segoe UI', 9)).pack(side='left', padx=28)
    button = tk.Button(footer, text='Tamam', command=root.destroy, bg=teal, fg='white', activebackground='#05554F',
                       activeforeground='white', relief='flat', font=('Segoe UI Semibold', 10), padx=22, pady=6, cursor='hand2')
    button.pack(side='right', padx=28, pady=14)
    root.bind('<Return>', lambda _: root.destroy())
    root.bind('<Escape>', lambda _: root.destroy())

    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry(f'+{x}+{y}')
    root.lift()
    root.focus_force()
    button.focus_set()
    root.mainloop()

def main():
    desktop.prepare_console()
    started, expired = first_run()
    now = time.time()
    # Saat geri alınırsa da süre dolmuş sayılır.
    if expired or now < started - 60 or now >= started + LIMIT:
        save(DenemeBitti='1')
        show_expired()
        return
    print(f'Deneme sürümü: kalan süre {int(started + LIMIT - now)} saniye.', flush=True)
    try:
        desktop.main(expires_at=started + LIMIT)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f'\nHata: {error}')
        if time.time() < started + LIMIT:
            input('Kapatmak için Enter tuşuna basın...')
    if time.time() >= started + LIMIT:
        save(DenemeBitti='1')
        show_expired()

if __name__ == '__main__':
    main()
