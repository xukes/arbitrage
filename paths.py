"""
统一配置路径管理

开发模式：配置文件读写 -> 项目根目录
PyInstaller 打包（sys.frozen）：配置文件读写 -> %%APPDATA%%/CryptoArbitrage/
"""
import os
import sys


def get_config_dir():
    """
    返回配置文件目录（保证目录存在）。
    打包后自动切到 %%APPDATA%%/CryptoArbitrage，开发时用项目根目录。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包 — 配置文件写到用户目录
        if sys.platform == 'darwin':
            base = os.path.expanduser('~/Library/Application Support')
        elif sys.platform.startswith('win'):
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:
            base = os.environ.get(
                'XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = os.path.join(base, 'CryptoArbitrage')
    else:
        # 开发模式 — paths.py 在项目根目录
        config_dir = os.path.dirname(os.path.abspath(__file__))

    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def migrate_old_configs(config_dir):
    """
    首次运行时，如果 exe 旁边有旧配置文件，自动迁移到 APPDATA。
    只在打包模式下执行。
    """
    if not getattr(sys, 'frozen', False):
        return  # 开发模式无需迁移

    exe_dir = os.path.dirname(sys.executable)
    config_files = [
        'config.json',
        'settings.json',
        'auto_trader_config.json',
        'alert_log.json',
    ]

    for fname in config_files:
        old_path = os.path.join(exe_dir, fname)
        new_path = os.path.join(config_dir, fname)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                import shutil
                shutil.copy2(old_path, new_path)
            except Exception:
                pass
