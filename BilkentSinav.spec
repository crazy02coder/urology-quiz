# Windows'ta: proje köküne cloudflared.exe koyun, sonra `pyinstaller --noconfirm BilkentSinav.spec`
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['desktop.py'],
    datas=[
        ('app/templates', 'app/templates'),
        ('app/static', 'app/static'),
        ('app/fonts', 'app/fonts'),
        ('migrations', 'migrations'),
    ],
    binaries=[('cloudflared.exe', '.')],
    # Uvicorn döngü/protokol modüllerini isimle yüklediği için otomatik bulunmazlar.
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('websockets'),
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BilkentSinav',
    icon='app/static/img/saglik-bakanligi.png',
    console=True,
    upx=False,
)
