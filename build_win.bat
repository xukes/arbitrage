@echo off
REM ============================================================
REM  打包 Windows 应用：dist\CryptoArbitrage\CryptoArbitrage.exe
REM  可选参数：
REM     build_win.bat            仅打包
REM     build_win.bat installer  打包并用 Inno Setup 生成安装包
REM  需要在 Windows 上运行，且 python 已加入 PATH。
REM ============================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

set "VENV=.venv-win"
set "PY=%VENV%\Scripts\python.exe"

REM ---- 1. 准备虚拟环境 ----
if not exist "%PY%" (
    echo [1/4] 创建虚拟环境 %VENV% ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请确认已安装 Python 3 并加入 PATH。
        exit /b 1
    )
    "%PY%" -m pip install --upgrade pip
    if errorlevel 1 exit /b 1
    "%PY%" -m pip install -r requirements.txt pyinstaller
    if errorlevel 1 (
        echo [错误] 安装依赖失败。
        exit /b 1
    )
) else (
    echo [1/4] 复用已有虚拟环境 %VENV%
)

REM ---- 2. 清理上次的构建产物 ----
echo [2/4] 清理 build\ 和 dist\ ...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

REM ---- 3. 打包 ----
echo [3/4] 运行 PyInstaller ...
"%PY%" -m PyInstaller --noconfirm crypto_arbitrage.spec
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败。
    exit /b 1
)
if not exist "dist\CryptoArbitrage\CryptoArbitrage.exe" (
    echo [错误] 未找到 dist\CryptoArbitrage\CryptoArbitrage.exe
    exit /b 1
)

REM ---- 4. 可选：生成安装包 ----
if /i "%~1"=="installer" (
    echo [4/4] 使用 Inno Setup 生成安装包 ...
    set "ISCC="
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    if not defined ISCC (
        where ISCC.exe >nul 2>&1 && set "ISCC=ISCC.exe"
    )
    if not defined ISCC (
        echo [警告] 未找到 ISCC.exe，跳过安装包生成。
        echo         请安装 Inno Setup 6: https://jrsoftware.org/isdl.php
    ) else (
        "!ISCC!" installer.iss
        if errorlevel 1 (
            echo [错误] Inno Setup 编译失败。
            exit /b 1
        )
        echo 安装包已生成于: Output\
    )
) else (
    echo [4/4] 跳过安装包生成（如需生成请运行: build_win.bat installer）
)

echo.
echo 完成: dist\CryptoArbitrage\CryptoArbitrage.exe
endlocal
