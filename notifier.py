"""
通知模块
支持多渠道：QQ邮箱 / go-cqhttp QQ机器人 / 桌面弹窗 / 声音告警
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.header import Header
import requests
import logging
import json
import os
import sys
import time

from PyQt5.QtCore import Q_ARG
from PyQt5.QtWidgets import QSystemTrayIcon
from paths import get_config_dir

logger = logging.getLogger(__name__)

CONFIG_DIR = get_config_dir()
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')


def load_settings():
    default = {
        'qq_enabled': False,
        'qq_user_id': 0,
        'qq_http_url': 'http://127.0.0.1:5700',
        'email_enabled': False,
        'email_smtp': 'smtp.qq.com',
        'email_port': 465,
        'email_user': '',
        'email_pass': '',
        'email_to': '',
        'desktop_notify': True,
        'sound_alert': True,
        'alert_cooldown': 300,
        'quiet_hours': {
            'enabled': False,
            'days': [0, 1, 2, 3, 4],   # 0=Mon ... 6=Sun, default: weekday
            'start': '09:00',
            'end': '17:00',
        },
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                default.update(json.load(f))
    except Exception as e:
        logger.warning(f"加载设置失败: {e}")
    return default


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存设置失败: {e}")


class Notifier:
    def __init__(self):
        self.settings = load_settings()
        self._cooldown = {}
        self._tray = None

    def set_tray(self, tray):
        self._tray = tray

    def reload_settings(self):
        self.settings = load_settings()

    def _is_cooling_down(self, key):
        now = time.time()
        cd = self.settings.get('alert_cooldown', 300)
        if key in self._cooldown:
            if now - self._cooldown[key] < cd:
                return True
        self._cooldown[key] = now
        self._cooldown = {k: v for k, v in self._cooldown.items() if now - v < cd * 2}
        return False

    def send_alert(self, title, message, alert_key=None):
        if alert_key and self._is_cooling_down(alert_key):
            logger.debug(f"告警 {alert_key} 冷却中，跳过")
            return

        results = []

        # 1. QQ邮箱（优先，最可靠）
        if self.settings.get('email_enabled'):
            result = self._send_email(title, message)
            results.append(('邮箱', result))

        # 2. go-cqhttp QQ机器人
        if self.settings.get('qq_enabled'):
            result = self._send_qq(f"{title}\n{message}")
            results.append(('QQBot', result))

        # 3. 桌面弹窗
        if self.settings.get('desktop_notify'):
            result = self._send_desktop(title, message)
            results.append(('桌面', result))

        # 4. 声音
        if self.settings.get('sound_alert'):
            self._play_alert_sound()

        logger.info(f"告警: {title} | {' '.join(f'{k}:{v}' for k, v in results)}")

    # ── QQ邮箱 ──────────────────────────────────

    def _send_email(self, title, message):
        """通过 QQ 邮箱 SMTP 发送通知"""
        try:
            smtp_server = self.settings.get('email_smtp', 'smtp.qq.com')
            port = self.settings.get('email_port', 465)
            user = self.settings.get('email_user', '')
            passwd = self.settings.get('email_pass', '')
            to_addr = self.settings.get('email_to', '') or user

            if not user or not passwd:
                return '未配置'

            msg = MIMEText(message, 'plain', 'utf-8')
            msg['Subject'] = Header(title, 'utf-8')
            msg['From'] = user
            msg['To'] = to_addr

            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, port, context=ctx, timeout=10) as server:
                server.login(user, passwd)
                server.sendmail(user, [to_addr], msg.as_string())
            return '已发送'
        except smtplib.SMTPAuthenticationError:
            logger.error("邮箱登录失败，检查授权码")
            return '认证失败'
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return f'失败({e})'

    # ── go-cqhttp ───────────────────────────────

    def _send_qq(self, message):
        try:
            url = f"{self.settings.get('qq_http_url', 'http://127.0.0.1:5700')}/send_private_msg"
            data = {"user_id": self.settings.get('qq_user_id'), "message": message}
            resp = requests.post(url, json=data, timeout=5)
            if resp.status_code == 200 and resp.json().get('status') == 'ok':
                return 'OK'
            return f'失败({resp.status_code})'
        except requests.ConnectionError:
            return '无连接'
        except Exception as e:
            return f'异常({e})'

    # ── 桌面 ────────────────────────────────────

    def _send_desktop(self, title, message):
        try:
            if self._tray and self._tray.supportsMessages():
                self._tray.showMessage(title, message, QSystemTrayIcon.Warning, 3000)
                return 'OK'
            return '无托盘'
        except Exception as e:
            return f'失败({e})'

    # ── 声音 ────────────────────────────────────

    def _play_alert_sound(self):
        try:
            if sys.platform == 'darwin':
                import subprocess
                subprocess.Popen(
                    ['afplay', '/System/Library/Sounds/Ping.aiff'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif sys.platform.startswith('win'):
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                from PyQt5.QtWidgets import QApplication
                QApplication.beep()
        except Exception:
            pass
