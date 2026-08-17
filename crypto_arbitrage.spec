# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for CryptoArbitrage
Build: pyinstaller crypto_arbitrage.spec
"""

import sys
import os

# Project root (SPECPATH is where the .spec file lives)
ROOT = SPECPATH

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ('templates', 'templates'),
    ],
    hiddenimports=[
        # ccxt exchange modules
        'ccxt.binance',
        'ccxt.okx',
        'ccxt.base.exchange',
        # PyQt5
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.sip',
        # Flask + deps
        'flask',
        'flask.logging',
        'jinja2',
        'jinja2.ext',
        'markupsafe',
        # pandas (yfinance dep)
        'pandas',
        'numpy',
        # misc
        'yfinance',
        'requests',
        'email.mime.text',
        'email.mime.multipart',
        'smtplib',
        'ssl',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CryptoArbitrage',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no console window for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # no custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CryptoArbitrage',
)
