# Windows'ta: proje köküne cloudflared.exe koyun, sonra `pyinstaller --noconfirm BilkentSinav.spec`
# → dist\Bilkent Sınav.exe ve dist\Bilkent Sınav (Deneme).exe
from PyInstaller.utils.hooks import collect_submodules

DATAS = [
    ('app/templates', 'app/templates'),
    ('app/static', 'app/static'),
    ('app/fonts', 'app/fonts'),
    ('migrations', 'migrations'),
    ('.env.example', '.'),
]
# Uvicorn döngü/protokol modüllerini isimle yüklediği için otomatik bulunmazlar.
HIDDEN = collect_submodules('uvicorn') + collect_submodules('websockets') + collect_submodules('reportlab')

def build(script, name, datas=(), excludes=()):
    a = Analysis([script], datas=DATAS + list(datas), binaries=[('cloudflared.exe', '.')],
                 hiddenimports=HIDDEN, excludes=list(excludes))
    EXE(PYZ(a.pure), a.scripts, a.binaries, a.datas, [],
        name=name, icon='BilkentSinav.ico', console=True, upx=False)

build('desktop.py', 'Bilkent Sınav', excludes=['tkinter'])
# 2 dakikalık deneme sürümü (deneme.py): süre dolunca her açılışta iletişim penceresi gösterir.
build('deneme.py', 'Bilkent Sınav (Deneme)', datas=[('BilkentSinav.ico', '.')])
