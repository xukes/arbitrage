#!/usr/bin/env bash
# 打包 macOS 应用：dist/CryptoArbitrage.app
set -e
cd "$(dirname "$0")"

VENV=.venv-mac
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r requirements.txt pyinstaller
fi

rm -rf build dist
"$VENV/bin/pyinstaller" --noconfirm crypto_arbitrage_mac.spec

# 本地自签名，避免 Gatekeeper 拦截
codesign --force --deep --sign - dist/CryptoArbitrage.app

echo "完成: dist/CryptoArbitrage.app"
