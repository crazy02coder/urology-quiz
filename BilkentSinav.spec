# Windows'ta: proje köküne cloudflared.exe koyun, sonra `pyinstaller --noconfirm BilkentSinav.spec` → dist\Bilkent Sınav.exe
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['desktop.py'],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
        ('app/fonts', 'app/fonts'),
        ('migrations', 'migrations'),
        ('.env.example', '.'),
    ],
    binaries=[('cloudflared.exe', '.')],
    # Uvicorn döngü/protokol modüllerini isimle yüklediği için otomatik bulunmazlar.
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('websockets') + collect_submodules('reportlab'),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Bilkent Sınav',
    icon='BilkentSinav.ico',
    console=True,
    upx=False,
)
