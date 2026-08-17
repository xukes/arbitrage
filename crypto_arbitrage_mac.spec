# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for CryptoArbitrage (macOS .app)
Build: pyinstaller crypto_arbitrage_mac.spec
"""

ROOT = SPECPATH

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
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CryptoArbitrage',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 会破坏 macOS 签名
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,       # 跟随当前 Python 架构（arm64 / x86_64）
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CryptoArbitrage',
)

app = BUNDLE(
    coll,
    name='CryptoArbitrage.app',
    icon=None,
    bundle_identifier='com.cryptoarb.monitor',
    info_plist={
        'CFBundleName': 'CryptoArbitrage',
        'CFBundleDisplayName': '套利监控器',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
        # 托盘后台程序：不在 Dock 显示图标可改为 True
        'LSUIElement': False,
        'NSAppTransportSecurity': {'NSAllowsArbitraryLoads': True},
    },
)
