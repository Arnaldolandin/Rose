# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[('rose.ico', '.')],
    hiddenimports=[
        'PyPDF2', 'PIL._tkinter_finder',
        'cdp_common',
        'servipag',
        'sii',
        'rvm',
        'sap',
        'robos',
        'notarial',
        'autofact',
        'playwright', 'playwright.async_api', 'playwright.sync_api',
        'playwright._impl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'scipy', 'pandas', 'numpy', 'matplotlib', 'tensorboard', 'jinja2', 'fsspec'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Rose',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['rose.ico'],
)
