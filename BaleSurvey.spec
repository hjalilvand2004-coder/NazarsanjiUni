# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — BaleSurvey portable (onedir) for Windows.

Build:
    pyinstaller BaleSurvey.spec --noconfirm --clean
Output:
    dist/BaleSurvey/BaleSurvey.exe        (لانچر کنسولی)
    dist/BaleSurvey/_internal/            (کتابخانه‌ها + templates/static/xlsx)

Layout در حالت اجرا (frozen):
    sys._MEIPASS        = <exe_dir>/_internal   (فقط‌خواندنی — منابع)
    sys.executable dir  = <exe_dir>             ( data/ اینجا ساخته می‌شود — نوشتنی)

نکته: دیتابیس و فایل‌های نوشتنی هرگز داخل بسته قرار نمی‌گیرند؛
در اولین اجرا در <exe_dir>/data/ ساخته و از xlsx پایه (داخل بسته) تغذیه می‌شوند.
"""
import os

block_cipher = None
PROJ = os.path.abspath('.')

# فقط منابع فقط‌خواندنی داخل بسته قرار می‌گیرند
datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('data/CourceListYekta.xlsx', 'data'),
    ('data/CourceListDetail.xlsx', 'data'),
]
binaries = []

# ماژول‌هایی که import پویا (درون try/except) دارند تا حتماً بسته شوند
hiddenimports = [
    'portable', 'sso', 'preferences', 'slot_times', 'instructors', 'questions',
    'src', 'src.config', 'src.database', 'src.helpers', 'src.bale_api',
    'src.educational_content',
    'openpyxl', 'pandas', 'jwt', 'cryptography', 'requests',
]

a = Analysis(
    ['website.py'],
    pathex=[PROJ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'matplotlib', 'PIL', 'seaborn', 'notebook', 'IPython', 'pytest',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BaleSurvey',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name='BaleSurvey')
