"""
美股-币安 价差套利监控器
==========================
功能：
  - 实时监控美股与币安对应标的的价差
  - 价差超过阈值时通过 QQ / 桌面弹窗 / 声音 告警
  - 系统托盘后台运行，最小化不中断监控

用法：
  python main.py

首次运行会自动生成 config.json (标的列表) 和 settings.json (通知设置)
"""

import sys
import os
import logging
import datetime
import json

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from paths import get_config_dir, migrate_old_configs

from gui_app import MainWindow

# 项目目录（开发模式 = 项目根目录，打包模式 = %APPDATA%\CryptoArbitrage）
APP_DIR = get_config_dir()
migrate_old_configs(APP_DIR)


def setup_logging():
    """配置日志：输出到文件（pythonw 无控制台则只写文件）"""
    log_file = os.path.join(APP_DIR, 'app.log')
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]

    # pythonw.exe 下 sys.stdout 为 None，只写文件即可
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
    )
    # 减少第三方库日志噪音
    logging.getLogger('yfinance').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def ensure_configs():
    """确保必要的配置文件存在"""
    config_file = os.path.join(APP_DIR, 'config.json')
    settings_file = os.path.join(APP_DIR, 'settings.json')

    if not os.path.exists(config_file):
        default_config = {
            "pairs": [
                ["MSTR", "BTCUSDT", 0.5],
                ["COIN", "BTCUSDT", 0.8],
                ["MARA", "BTCUSDT", 1.0],
            ]
        }
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        logging.info(f"已创建默认配置文件: {config_file}")

    if not os.path.exists(settings_file):
        default_settings = {
            "qq_enabled": False,
            "qq_user_id": 0,
            "qq_http_url": "http://127.0.0.1:5700",
            "email_enabled": False,
            "email_user": "",
            "email_pass": "",
            "email_to": "",
            "desktop_notify": True,
            "sound_alert": True,
            "poll_interval": 30,
            "alert_cooldown": 300,
            "start_minimized": False,
            "proxy": {
                "enabled": False,
                "http": "http://127.0.0.1:10809",
                "https": "http://127.0.0.1:10809",
            },
            "quiet_hours": {
                "enabled": False,
                "days": [0, 1, 2, 3, 4],   # Mon-Fri
                "start": "09:00",
                "end": "17:00",
            },
        }
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(default_settings, f, indent=4, ensure_ascii=False)
        logging.info(f"已创建默认设置文件: {settings_file}")


def main():
    setup_logging()
    ensure_configs()

    logging.info("=" * 50)
    logging.info("套利监控器启动")
    logging.info(f"时间: {datetime.datetime.now()}")

    # PyQt5 高分屏适配
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("CryptoArbitrageMonitor")
    app.setOrganizationName("CryptoArb")

    window = MainWindow()

    # 检查是否需要最小化启动
    settings_file = os.path.join(APP_DIR, 'settings.json')
    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        if settings.get('start_minimized', False):
            window.hide()
        else:
            window.show()
    except Exception:
        window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
