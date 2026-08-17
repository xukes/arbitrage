"""
GUI 界面 (PyQt5) — 现代深色主题
"""

import sys
import json
import os
import datetime
import threading
import socket

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableView, QAbstractItemView,
    QToolBar, QAction, QStatusBar, QLabel, QSystemTrayIcon, QMenu,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QVBoxLayout,
    QWidget, QPushButton, QCheckBox, QSpinBox, QDoubleSpinBox, QGroupBox,
    QHeaderView, QMessageBox, QTextEdit, QSplitter, QHBoxLayout,
    QFrame, QGridLayout, QStyle, QTabWidget, QComboBox, QProgressBar,
    QListWidget, QListWidgetItem, QTimeEdit
)
from PyQt5.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QThread, QTimer, QSize, QTime
)
from PyQt5.QtGui import (
    QIcon, QColor, QFont, QBrush, QPalette, QLinearGradient
)

from monitor import MonitorThread
from auto_trader.trade_engine import TradeEngine, save_trade_config, _load_trade_config
from auto_trader.scheduler import TradingScheduler, WINDOW_TRADING, WINDOW_CLOSE_ONLY, WINDOW_TESTNET
from paths import get_config_dir

CONFIG_DIR = get_config_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')
ALERT_LOG_FILE = os.path.join(CONFIG_DIR, 'alert_log.json')


# ═══════════════════════════════════════════
# 深色主题样式表
# ═══════════════════════════════════════════

STYLESHEET = """
/* === 全局 === */
QMainWindow { background: #0d1117; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 13px; color: #c9d1d9; }
QMenu { background: #161b22; border: 1px solid #30363d; padding: 4px; }
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 4px; }
QMenu::item:selected { background: #1f6feb; }
QMenu::separator { height: 1px; background: #30363d; margin: 4px 8px; }

/* === 工具栏 === */
QToolBar { background: #161b22; border-bottom: 1px solid #30363d; padding: 4px 8px; spacing: 4px; }
QToolBar QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 6px 14px; color: #c9d1d9; font-weight: 500; }
QToolBar QToolButton:hover { background: #21262d; border-color: #30363d; }
QToolBar QToolButton:pressed { background: #30363d; }

/* === 表格 === */
QTableView {
    background: #0d1117; alternate-background-color: #161b22;
    border: none; gridline-color: #21262d; selection-background-color: #1f3a5f;
    outline: none; font-size: 12px;
}
QTableView::item { padding: 8px 12px; border-bottom: 1px solid #21262d; }
QTableView::item:selected { background: #1f3a5f; }
QHeaderView::section {
    background: #161b22; color: #8b949e; font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px;
    padding: 10px 12px; border: none; border-bottom: 2px solid #30363d;
    border-right: 1px solid #21262d;
}

/* === 状态栏 === */
QStatusBar { background: #161b22; border-top: 1px solid #30363d; color: #8b949e; font-size: 11px; padding: 4px 8px; }

/* === 日志 === */
QTextEdit { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px; font-family: "Cascadia Code", "Consolas", monospace; font-size: 11px; color: #8b949e; }

/* === 分组框 === */
QGroupBox { font-weight: 600; color: #c9d1d9; border: 1px solid #30363d; border-radius: 8px; margin-top: 12px; padding: 16px 12px 12px 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }

/* === 输入框 === */
QLineEdit, QSpinBox {
    background: #0d1117; border: 1px solid #30363d; border-radius: 6px;
    padding: 8px 10px; color: #c9d1d9; font-size: 13px;
}
QLineEdit:focus, QSpinBox:focus { border-color: #1f6feb; }

/* === 复选框 === */
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #30363d; border-radius: 4px; background: #0d1117; }
QCheckBox::indicator:checked { background: #1f6feb; border-color: #1f6feb; }

/* === 按钮 === */
QPushButton { background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 8px 18px; color: #c9d1d9; font-weight: 500; }
QPushButton:hover { background: #30363d; }
QPushButton:pressed { background: #1f6feb; border-color: #1f6feb; }

QDialogButtonBox QPushButton { min-width: 80px; }

/* === 对话框 === */
QDialog { background: #161b22; }

/* === 滚动条 === */
QScrollBar:vertical { background: #0d1117; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #30363d; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #484f58; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #0d1117; height: 10px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #30363d; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* === 分割器 === */
QSplitter::handle { background: #21262d; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }
"""

# ═══════════════════════════════════════════
# 统计卡片组件
# ═══════════════════════════════════════════


class StatCard(QFrame):
    """顶部统计卡片"""

    def __init__(self, title, value="—", color="#58a6ff", parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setStyleSheet(f"""
            QFrame#StatCard {{
                background: #161b22; border: 1px solid #30363d;
                border-radius: 10px; padding: 14px 18px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 11px; color: #8b949e; font-weight: 500; letter-spacing: 0.5px; border: none;")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {color}; border: none;")
        layout.addWidget(self.value_label)

    def set_value(self, value):
        self.value_label.setText(str(value))


# ═══════════════════════════════════════════
# 表格模型
# ═══════════════════════════════════════════

class ArbitrageModel(QAbstractTableModel):
    HEADERS = ["美股", "币安", "美股价格", "币安价格", "价差(%)", "阈值(%)", "状态", "更新时间"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []

    def update_all(self, rows):
        self.beginResetModel()
        self._data = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._data):
            return None

        value = self._data[row][col]

        if role == Qt.DisplayRole:
            return str(value)

        if role == Qt.ForegroundRole:
            status = str(self._data[row][6])
            if '买入信号' in status:
                return QColor(255, 123, 114)
            elif '溢价信号' in status:
                return QColor(63, 185, 80)
            elif '确认中' in status:
                return QColor(210, 153, 34)
            elif '数据异常' in status:
                return QColor(139, 148, 158)
            return QColor(201, 209, 217)

        if role == Qt.BackgroundRole:
            status = str(self._data[row][6])
            if '买入信号' in status:
                return QColor(73, 5, 5)
            elif '溢价信号' in status:
                return QColor(5, 50, 30)
            return None

        if role == Qt.TextAlignmentRole:
            if col >= 2:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.FontRole:
            if col in (4, 6):
                f = QFont()
                f.setBold(True)
                return f

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None


# ═══════════════════════════════════════════
# 设置对话框
# ═══════════════════════════════════════════

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙  设置")
        self.setMinimumWidth(440)
        self.setStyleSheet(STYLESHEET)
        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # ---- 邮件通知 ----
        email_group = QGroupBox("📧 QQ邮箱通知（推荐，点QQ邮箱设置→账户→开启SMTP获取授权码）")
        email_layout = QFormLayout(email_group)
        email_layout.setSpacing(10)

        self.chk_email = QCheckBox("启用 QQ邮箱 通知")
        self.txt_email_user = QLineEdit()
        self.txt_email_user.setPlaceholderText("你的QQ号@qq.com，如 123456789@qq.com")
        self.txt_email_pass = QLineEdit()
        self.txt_email_pass.setEchoMode(QLineEdit.Password)
        self.txt_email_pass.setPlaceholderText("QQ邮箱授权码（非QQ密码）")
        self.txt_email_to = QLineEdit()
        self.txt_email_to.setPlaceholderText("接收通知的邮箱（留空则发给自己）")

        email_layout.addRow(self.chk_email)
        email_layout.addRow("发件邮箱:", self.txt_email_user)
        email_layout.addRow("授权码:", self.txt_email_pass)
        email_layout.addRow("接收邮箱:", self.txt_email_to)
        layout.addWidget(email_group)

        # ---- QQ机器人（可选） ----
        notify_group = QGroupBox("🤖 QQ机器人通知（需 go-cqhttp，可选）")
        notify_layout = QFormLayout(notify_group)
        notify_layout.setSpacing(10)

        self.chk_qq = QCheckBox("启用 QQ 通知（需先启动 go-cqhttp）")
        self.txt_qq_url = QLineEdit()
        self.txt_qq_url.setPlaceholderText("http://127.0.0.1:5700")
        self.txt_qq_uid = QLineEdit()
        self.txt_qq_uid.setPlaceholderText("输入你的 QQ 号")

        self.chk_desktop = QCheckBox("启用桌面弹窗通知")
        self.chk_sound = QCheckBox("启用声音告警")

        notify_layout.addRow(self.chk_qq)
        notify_layout.addRow("HTTP 地址:", self.txt_qq_url)
        notify_layout.addRow("QQ 号码:", self.txt_qq_uid)
        notify_layout.addRow(self.chk_desktop)
        notify_layout.addRow(self.chk_sound)
        layout.addWidget(notify_group)

        # ---- 代理设置 ----
        proxy_group = QGroupBox("🌐 代理设置（国内访问 yfinance/币安 必需）")
        proxy_layout = QFormLayout(proxy_group)
        proxy_layout.setSpacing(10)

        self.chk_proxy = QCheckBox("启用 HTTP 代理")
        self.txt_proxy_http = QLineEdit()
        self.txt_proxy_http.setPlaceholderText("http://127.0.0.1:10809")
        self.txt_proxy_https = QLineEdit()
        self.txt_proxy_https.setPlaceholderText("同 HTTP 代理地址（可留空）")

        proxy_layout.addRow(self.chk_proxy)
        proxy_layout.addRow("HTTP 代理:", self.txt_proxy_http)
        proxy_layout.addRow("HTTPS 代理:", self.txt_proxy_https)
        layout.addWidget(proxy_group)

        # ---- 监控设置 ----
        monitor_group = QGroupBox("⏱ 监控设置")
        monitor_layout = QFormLayout(monitor_group)
        monitor_layout.setSpacing(10)

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 300)
        self.spin_interval.setSuffix(" 秒")
        self.spin_interval.setValue(30)

        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(30, 3600)
        self.spin_cooldown.setSuffix(" 秒")
        self.spin_cooldown.setValue(300)

        self.chk_minimize = QCheckBox("启动时最小化到系统托盘")

        monitor_layout.addRow("轮询间隔:", self.spin_interval)
        monitor_layout.addRow("告警冷却:", self.spin_cooldown)
        monitor_layout.addRow(self.chk_minimize)
        layout.addWidget(monitor_group)

        # ---- 邮件静默时段 ----
        quiet_group = QGroupBox("🔇 邮件静默时段（此时段内不发送邮件/推送通知）")
        quiet_vlayout = QVBoxLayout(quiet_group)
        quiet_vlayout.setSpacing(8)

        self.chk_quiet = QCheckBox("启用静默时段")
        quiet_vlayout.addWidget(self.chk_quiet)

        # 星期选择
        day_row = QHBoxLayout()
        day_row.addWidget(QLabel("生效日期:"))
        DAY_NAMES = ['一', '二', '三', '四', '五', '六', '日']
        self.chk_quiet_days = []
        for i, name in enumerate(DAY_NAMES):
            cb = QCheckBox(name)
            self.chk_quiet_days.append(cb)
            day_row.addWidget(cb)
        day_row.addStretch()
        quiet_vlayout.addLayout(day_row)

        # 时间选择
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("起始时间:"))
        self.time_quiet_start = QTimeEdit()
        self.time_quiet_start.setDisplayFormat("HH:mm")
        time_row.addWidget(self.time_quiet_start)
        time_row.addSpacing(12)
        time_row.addWidget(QLabel("结束时间:"))
        self.time_quiet_end = QTimeEdit()
        self.time_quiet_end.setDisplayFormat("HH:mm")
        time_row.addWidget(self.time_quiet_end)
        time_row.addStretch()
        quiet_vlayout.addLayout(time_row)

        layout.addWidget(quiet_group)

        # ---- 按钮 ----
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                s = json.load(f)
        except Exception:
            s = {}
        self.chk_qq.setChecked(s.get('qq_enabled', False))
        self.txt_qq_url.setText(s.get('qq_http_url', 'http://127.0.0.1:5700'))
        self.txt_qq_uid.setText(str(s.get('qq_user_id', '')))
        self.chk_desktop.setChecked(s.get('desktop_notify', True))
        self.chk_sound.setChecked(s.get('sound_alert', True))

        # 邮箱设置
        self.chk_email.setChecked(s.get('email_enabled', False))
        self.txt_email_user.setText(s.get('email_user', ''))
        self.txt_email_pass.setText(s.get('email_pass', ''))
        self.txt_email_to.setText(s.get('email_to', ''))

        self.spin_interval.setValue(s.get('poll_interval', 30))
        self.spin_cooldown.setValue(s.get('alert_cooldown', 300))
        self.chk_minimize.setChecked(s.get('start_minimized', False))

        # 代理设置
        proxy = s.get('proxy', {})
        self.chk_proxy.setChecked(proxy.get('enabled', False))
        self.txt_proxy_http.setText(proxy.get('http', ''))
        self.txt_proxy_https.setText(proxy.get('https', ''))

        # 静默时段设置
        qh = s.get('quiet_hours', {})
        self.chk_quiet.setChecked(qh.get('enabled', False))
        days = qh.get('days', [0, 1, 2, 3, 4])
        for i, cb in enumerate(self.chk_quiet_days):
            cb.setChecked(i in days)
        try:
            s_parts = qh.get('start', '09:00').split(':')
            self.time_quiet_start.setTime(QTime(int(s_parts[0]), int(s_parts[1])))
            e_parts = qh.get('end', '17:00').split(':')
            self.time_quiet_end.setTime(QTime(int(e_parts[0]), int(e_parts[1])))
        except Exception:
            pass

    def _on_ok(self):
        settings = {
            'qq_enabled': self.chk_qq.isChecked(),
            'qq_http_url': self.txt_qq_url.text().strip(),
            'qq_user_id': int(self.txt_qq_uid.text() or '0'),
            'desktop_notify': self.chk_desktop.isChecked(),
            'sound_alert': self.chk_sound.isChecked(),
            'email_enabled': self.chk_email.isChecked(),
            'email_user': self.txt_email_user.text().strip(),
            'email_pass': self.txt_email_pass.text().strip(),
            'email_to': self.txt_email_to.text().strip(),
            'poll_interval': self.spin_interval.value(),
            'alert_cooldown': self.spin_cooldown.value(),
            'start_minimized': self.chk_minimize.isChecked(),
            'proxy': {
                'enabled': self.chk_proxy.isChecked(),
                'http': self.txt_proxy_http.text().strip(),
                'https': self.txt_proxy_https.text().strip() or self.txt_proxy_http.text().strip(),
            },
            'quiet_hours': {
                'enabled': self.chk_quiet.isChecked(),
                'days': [i for i, cb in enumerate(self.chk_quiet_days) if cb.isChecked()],
                'start': self.time_quiet_start.time().toString('HH:mm'),
                'end': self.time_quiet_end.time().toString('HH:mm'),
            },
        }
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        self.accept()


# ═══════════════════════════════════════════
# 添加标对话框
# ═══════════════════════════════════════════

class AddPairDialog(QDialog):
    def __init__(self, parent=None, stock="", crypto="", threshold=0.5):
        super().__init__(parent)
        self.setWindowTitle("➕ 添加套利对")
        self.setMinimumWidth(380)
        self.setStyleSheet(STYLESHEET)
        layout = QFormLayout(self)
        layout.setSpacing(12)

        self.stock_edit = QLineEdit(stock)
        self.stock_edit.setPlaceholderText("如 MSTR, COIN, MARA")
        self.crypto_edit = QLineEdit(crypto)
        self.crypto_edit.setPlaceholderText("如 BTCUSDT, ETHUSDT")
        self.threshold_edit = QLineEdit(str(threshold))
        self.threshold_edit.setPlaceholderText("触发预警的价差百分比，如 0.5")

        layout.addRow("美股代码:", self.stock_edit)
        layout.addRow("币安交易对:", self.crypto_edit)
        layout.addRow("预警阈值(%):", self.threshold_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self):
        return (self.stock_edit.text().strip().upper(),
                self.crypto_edit.text().strip().upper(),
                float(self.threshold_edit.text() or '0.5'))


# ═══════════════════════════════════════════
# API 密钥设置对话框
# ═══════════════════════════════════════════

class ApiKeyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔑 交易所 API 密钥配置")
        self.setMinimumWidth(500)
        self.setStyleSheet(STYLESHEET)
        self.config = _load_trade_config()
        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 模式选择
        mode_group = QGroupBox("🔀 交易模式")
        mode_layout = QHBoxLayout(mode_group)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("🧪 测试网", "testnet")
        self.combo_mode.addItem("💰 实盘", "live")
        mode_layout.addWidget(QLabel("当前模式:"))
        mode_layout.addWidget(self.combo_mode)
        mode_layout.addStretch()
        layout.addWidget(mode_group)

        # Binance
        bnb_group = QGroupBox("🔶 币安合约 (Binance Futures)")
        bnb_layout = QFormLayout(bnb_group)
        bnb_layout.setSpacing(8)
        self.bnb_testnet_key = QLineEdit()
        self.bnb_testnet_key.setPlaceholderText("测试网 API Key")
        self.bnb_testnet_secret = QLineEdit()
        self.bnb_testnet_secret.setEchoMode(QLineEdit.Password)
        self.bnb_testnet_secret.setPlaceholderText("测试网 Secret Key")
        self.bnb_live_key = QLineEdit()
        self.bnb_live_key.setPlaceholderText("实盘 API Key")
        self.bnb_live_secret = QLineEdit()
        self.bnb_live_secret.setEchoMode(QLineEdit.Password)
        self.bnb_live_secret.setPlaceholderText("实盘 Secret Key")
        self.chk_bnb = QCheckBox("启用币安合约")
        bnb_layout.addRow(self.chk_bnb)
        bnb_layout.addRow(QLabel("<b>测试网:</b>"))
        bnb_layout.addRow("API Key:", self.bnb_testnet_key)
        bnb_layout.addRow("Secret:", self.bnb_testnet_secret)
        bnb_layout.addRow(QLabel("<b>实盘:</b>"))
        bnb_layout.addRow("API Key:", self.bnb_live_key)
        bnb_layout.addRow("Secret:", self.bnb_live_secret)
        # 测试连接按钮
        bnb_test_row = QHBoxLayout()
        self.btn_test_bnb = QPushButton("🔍 测试连接")
        self.btn_test_bnb.setMinimumHeight(28)
        self.btn_test_bnb.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_test_bnb.clicked.connect(self._test_binance)
        bnb_test_row.addWidget(self.btn_test_bnb)
        self.lbl_bnb_result = QLabel("")
        self.lbl_bnb_result.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        bnb_test_row.addWidget(self.lbl_bnb_result, 1)
        bnb_layout.addRow(bnb_test_row)
        layout.addWidget(bnb_group)

        # OKX
        okx_group = QGroupBox("🔷 OKX 永续合约 (OKX Swap)")
        okx_layout = QFormLayout(okx_group)
        okx_layout.setSpacing(8)
        self.okx_testnet_key = QLineEdit()
        self.okx_testnet_key.setPlaceholderText("测试网 API Key")
        self.okx_testnet_secret = QLineEdit()
        self.okx_testnet_secret.setEchoMode(QLineEdit.Password)
        self.okx_testnet_secret.setPlaceholderText("测试网 Secret Key")
        self.okx_testnet_pass = QLineEdit()
        self.okx_testnet_pass.setEchoMode(QLineEdit.Password)
        self.okx_testnet_pass.setPlaceholderText("测试网 Passphrase")
        self.okx_live_key = QLineEdit()
        self.okx_live_key.setPlaceholderText("实盘 API Key")
        self.okx_live_secret = QLineEdit()
        self.okx_live_secret.setEchoMode(QLineEdit.Password)
        self.okx_live_secret.setPlaceholderText("实盘 Secret Key")
        self.okx_live_pass = QLineEdit()
        self.okx_live_pass.setEchoMode(QLineEdit.Password)
        self.okx_live_pass.setPlaceholderText("实盘 Passphrase")
        self.chk_okx = QCheckBox("启用 OKX 合约")
        okx_layout.addRow(self.chk_okx)
        okx_layout.addRow(QLabel("<b>测试网:</b>"))
        okx_layout.addRow("API Key:", self.okx_testnet_key)
        okx_layout.addRow("Secret:", self.okx_testnet_secret)
        okx_layout.addRow("Passphrase:", self.okx_testnet_pass)
        okx_layout.addRow(QLabel("<b>实盘:</b>"))
        okx_layout.addRow("API Key:", self.okx_live_key)
        okx_layout.addRow("Secret:", self.okx_live_secret)
        okx_layout.addRow("Passphrase:", self.okx_live_pass)
        # 测试连接按钮
        okx_test_row = QHBoxLayout()
        self.btn_test_okx = QPushButton("🔍 测试连接")
        self.btn_test_okx.setMinimumHeight(28)
        self.btn_test_okx.setStyleSheet("font-size: 11px; padding: 4px 10px;")
        self.btn_test_okx.clicked.connect(self._test_okx)
        okx_test_row.addWidget(self.btn_test_okx)
        self.lbl_okx_result = QLabel("")
        self.lbl_okx_result.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        okx_test_row.addWidget(self.lbl_okx_result, 1)
        okx_layout.addRow(okx_test_row)
        layout.addWidget(okx_group)

        # 警告
        warn = QLabel("⚠️ API密钥以明文存储。请创建仅限<b>交易</b>权限的API Key，<b>不要开启提现权限！</b>")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #d29922; font-size: 12px; padding: 8px; background: #29240e; border-radius: 6px;")
        layout.addWidget(warn)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self):
        c = self.config
        self.combo_mode.setCurrentIndex(0 if c.get('mode') == 'testnet' else 1)
        b = c.get('binance', {})
        self.chk_bnb.setChecked(b.get('enabled', True))
        self.bnb_testnet_key.setText(b.get('testnet_api_key', ''))
        self.bnb_testnet_secret.setText(b.get('testnet_secret', ''))
        self.bnb_live_key.setText(b.get('live_api_key', ''))
        self.bnb_live_secret.setText(b.get('live_secret', ''))
        o = c.get('okx', {})
        self.chk_okx.setChecked(o.get('enabled', False))
        self.okx_testnet_key.setText(o.get('testnet_api_key', ''))
        self.okx_testnet_secret.setText(o.get('testnet_secret', ''))
        self.okx_testnet_pass.setText(o.get('testnet_passphrase', ''))
        self.okx_live_key.setText(o.get('live_api_key', ''))
        self.okx_live_secret.setText(o.get('live_secret', ''))
        self.okx_live_pass.setText(o.get('live_passphrase', ''))

    def _test_binance(self):
        """测试币安连接"""
        from auto_trader.exchange import BinanceFutures
        self.btn_test_bnb.setEnabled(False)
        self.btn_test_bnb.setText("⏳ 测试中...")
        self.lbl_bnb_result.setText("")

        is_testnet = self.combo_mode.currentData() == 'testnet'
        if is_testnet:
            key = self.bnb_testnet_key.text().strip()
            secret = self.bnb_testnet_secret.text().strip()
        else:
            key = self.bnb_live_key.text().strip()
            secret = self.bnb_live_secret.text().strip()

        if not key or not secret:
            self.lbl_bnb_result.setText("❌ 请先填写 API Key 和 Secret")
            self.lbl_bnb_result.setStyleSheet("color: #f85149; font-size: 11px;")
            self.btn_test_bnb.setEnabled(True)
            self.btn_test_bnb.setText("🔍 测试连接")
            return

        QApplication.processEvents()
        bnb = BinanceFutures()
        result = BinanceFutures.test_connection(
            key, secret, bnb._create_exchange, testnet=is_testnet
        )

        if result['success']:
            self.lbl_bnb_result.setText(
                f"✅ 连接成功 | USDT余额: {result['balance']:.2f} | 合约权限: OK"
            )
            self.lbl_bnb_result.setStyleSheet("color: #3fb950; font-size: 11px;")
        else:
            self.lbl_bnb_result.setText(f"❌ {result['error']}")
            self.lbl_bnb_result.setStyleSheet("color: #f85149; font-size: 11px;")

        self.btn_test_bnb.setEnabled(True)
        self.btn_test_bnb.setText("🔍 测试连接")

    def _test_okx(self):
        """测试 OKX 连接"""
        from auto_trader.exchange import OkxSwap
        self.btn_test_okx.setEnabled(False)
        self.btn_test_okx.setText("⏳ 测试中...")
        self.lbl_okx_result.setText("")

        is_testnet = self.combo_mode.currentData() == 'testnet'
        if is_testnet:
            key = self.okx_testnet_key.text().strip()
            secret = self.okx_testnet_secret.text().strip()
            passphrase = self.okx_testnet_pass.text().strip()
        else:
            key = self.okx_live_key.text().strip()
            secret = self.okx_live_secret.text().strip()
            passphrase = self.okx_live_pass.text().strip()

        if not key or not secret:
            self.lbl_okx_result.setText("❌ 请先填写 API Key 和 Secret")
            self.lbl_okx_result.setStyleSheet("color: #f85149; font-size: 11px;")
            self.btn_test_okx.setEnabled(True)
            self.btn_test_okx.setText("🔍 测试连接")
            return

        QApplication.processEvents()
        okx = OkxSwap()
        result = OkxSwap.test_connection(
            key, secret, okx._create_exchange, passphrase=passphrase, testnet=is_testnet
        )

        if result['success']:
            self.lbl_okx_result.setText(
                f"✅ 连接成功 | USDT余额: {result['balance']:.2f} | 合约权限: OK"
            )
            self.lbl_okx_result.setStyleSheet("color: #3fb950; font-size: 11px;")
        else:
            self.lbl_okx_result.setText(f"❌ {result['error']}")
            self.lbl_okx_result.setStyleSheet("color: #f85149; font-size: 11px;")

        self.btn_test_okx.setEnabled(True)
        self.btn_test_okx.setText("🔍 测试连接")

    def _on_ok(self):
        c = self.config
        c['mode'] = self.combo_mode.currentData()
        c['binance'] = {
            'enabled': self.chk_bnb.isChecked(),
            'testnet_api_key': self.bnb_testnet_key.text().strip(),
            'testnet_secret': self.bnb_testnet_secret.text().strip(),
            'live_api_key': self.bnb_live_key.text().strip(),
            'live_secret': self.bnb_live_secret.text().strip(),
        }
        c['okx'] = {
            'enabled': self.chk_okx.isChecked(),
            'testnet_api_key': self.okx_testnet_key.text().strip(),
            'testnet_secret': self.okx_testnet_secret.text().strip(),
            'testnet_passphrase': self.okx_testnet_pass.text().strip(),
            'live_api_key': self.okx_live_key.text().strip(),
            'live_secret': self.okx_live_secret.text().strip(),
            'live_passphrase': self.okx_live_pass.text().strip(),
        }
        save_trade_config(c)
        self.accept()
class TradePositionModel(QAbstractTableModel):
    HEADERS = ["美股", "币安", "方向", "状态", "已触发阶梯", "保证金(U)",
               "美股$", "币安$", "价差%", "首次开仓"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []

    def update_all(self, rows):
        self.beginResetModel()
        self._data = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._data):
            return None

        d = self._data[row]
        keys = ['stock', 'crypto', 'direction', 'status_label',
                'triggered_levels', 'total_margin',
                'us_price', 'crypto_price', 'diff', 'first_open']

        if col < len(keys):
            val = d.get(keys[col], '—')
        else:
            val = '—'

        if role == Qt.DisplayRole:
            if col == 4:  # triggered_levels
                levels = d.get('triggered_levels', [])
                return ', '.join(f"{l:.1f}%" for l in levels) if levels else '—'
            if col == 8:  # diff
                v = d.get('diff', 0)
                return f"{v:+.2f}%" if v else '—'
            if col == 5:  # margin
                m = d.get('total_margin', 0)
                return f"{m:.0f}" if m else '—'
            if col in (6, 7):  # prices
                p = val
                return f"${p}" if p and p != '—' else '—'
            return str(val)

        if role == Qt.ForegroundRole:
            direction = d.get('direction', '')
            if direction == 'long':
                return QColor(255, 123, 114)
            elif direction == 'short':
                return QColor(63, 185, 80)
            status = d.get('status', '')
            if status == 'alert_only':
                return QColor(255, 123, 114)
            if status == 'closed':
                return QColor(139, 148, 158)
            return QColor(201, 209, 217)

        if role == Qt.BackgroundRole:
            status = d.get('status', '')
            if status == 'alert_only':
                return QColor(73, 5, 5)
            if status == 'active':
                return QColor(5, 40, 60)
            return None

        if role == Qt.TextAlignmentRole:
            if col >= 2:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None
# ═══════════════════════════════════════════
# 分标的策略编辑对话框
# ═══════════════════════════════════════════

class PairOverrideDialog(QDialog):
    """编辑单个标的的自定义分段加仓参数"""

    DEFAULTS = {
        'normal_thresholds': [0.5, 1.0, 2.0, 3.0],
        'margin_multipliers': [1, 2, 3, 3],
    }

    def __init__(self, parent=None, pair_key=""):
        super().__init__(parent)
        self.pair_key = pair_key
        self.setWindowTitle(f"⚙ 自定义策略参数 — {pair_key}")
        self.setMinimumWidth(480)
        self.setStyleSheet(STYLESHEET)
        self._init_ui()
        self._load()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 启用开关
        self.chk_enable = QCheckBox("覆盖全局默认参数（自定义此标的阶梯和保证金）")
        self.chk_enable.toggled.connect(self._on_toggle)
        layout.addWidget(self.chk_enable)

        # 首仓保证金
        margin_group = QGroupBox("首仓保证金 (Base Margin)")
        margin_layout = QHBoxLayout(margin_group)
        margin_layout.addWidget(QLabel("首仓:"))
        self.spin_base_margin = QSpinBox()
        self.spin_base_margin.setRange(1, 10000)
        self.spin_base_margin.setSuffix(" U")
        margin_layout.addWidget(self.spin_base_margin)
        margin_layout.addStretch()
        layout.addWidget(margin_group)

        # 常规阶梯
        normal_group = QGroupBox("常规阶梯 (Normal) — 触发阈值 + 保证金倍数")
        normal_layout = QGridLayout(normal_group)
        normal_layout.setSpacing(8)
        normal_layout.addWidget(QLabel(""), 0, 0)
        normal_layout.addWidget(QLabel("<b>触发阈值%</b>"), 0, 1)
        normal_layout.addWidget(QLabel("<b>保证金倍数</b>"), 0, 2)
        self.normal_threshold_spins = []
        self.normal_multiplier_spins = []
        for i in range(4):
            normal_layout.addWidget(QLabel(f"Level {i+1}:"), i+1, 0)
            ts = QDoubleSpinBox()
            ts.setRange(0.1, 10.0)
            ts.setSingleStep(0.1)
            ts.setDecimals(1)
            ts.setSuffix("%")
            ts.setValue(self.DEFAULTS['normal_thresholds'][i])
            ts.valueChanged.connect(self._update_preview)
            normal_layout.addWidget(ts, i+1, 1)
            self.normal_threshold_spins.append(ts)

            ms = QDoubleSpinBox()
            ms.setRange(0.5, 10.0)
            ms.setSingleStep(0.5)
            ms.setDecimals(1)
            ms.setSuffix("x")
            ms.setValue(self.DEFAULTS['margin_multipliers'][i])
            ms.valueChanged.connect(self._update_preview)
            normal_layout.addWidget(ms, i+1, 2)
            self.normal_multiplier_spins.append(ms)
        layout.addWidget(normal_group)

        # 实时预览
        self.lbl_preview = QLabel("")
        self.lbl_preview.setStyleSheet(
            "font-size: 12px; color: #d29922; background: #161b22; "
            "border-radius: 6px; padding: 10px;"
        )
        self.lbl_preview.setWordWrap(True)
        layout.addWidget(self.lbl_preview)

        self.spin_base_margin.valueChanged.connect(self._update_preview)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_reset = QPushButton("↩ 重置为全局默认")
        btn_reset.clicked.connect(self._reset_to_defaults)
        btn_layout.addWidget(btn_reset)
        btn_layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)
        layout.addLayout(btn_layout)

        self._update_preview()

    def _on_toggle(self, enabled):
        for w in self.findChildren(QGroupBox):
            w.setEnabled(enabled)
        self.spin_base_margin.setEnabled(enabled)
        self._update_preview()

    def _load(self):
        config = _load_trade_config()
        overrides = config.get('pair_overrides', {})
        data = overrides.get(self.pair_key, {})
        has_override = bool(data)
        self.chk_enable.setChecked(has_override)

        global_base = config.get('base_margin', 100)
        self.spin_base_margin.setValue(data.get('base_margin', global_base))

        nt = data.get('normal_thresholds', self.DEFAULTS['normal_thresholds'])
        for i, spin in enumerate(self.normal_threshold_spins):
            if i < len(nt):
                spin.setValue(nt[i])

        mm = data.get('margin_multipliers', self.DEFAULTS['margin_multipliers'])
        for i, spin in enumerate(self.normal_multiplier_spins):
            if i < len(mm):
                spin.setValue(mm[i])

        self._on_toggle(has_override)

    def _update_preview(self):
        base = self.spin_base_margin.value()
        mults = [s.value() for s in self.normal_multiplier_spins]
        margins = [base * m for m in mults]
        thresh = [s.value() for s in self.normal_threshold_spins]
        lines = []
        for i in range(4):
            lines.append(f"Lv{i+1}: {thresh[i]:.1f}% → {margins[i]:.0f}U")
        self.lbl_preview.setText(
            " | ".join(lines) + f"\n最大占用: {sum(margins):.0f}U"
        )

    def _on_ok(self):
        config = _load_trade_config()
        if 'pair_overrides' not in config:
            config['pair_overrides'] = {}

        if self.chk_enable.isChecked():
            config['pair_overrides'][self.pair_key] = {
                'base_margin': self.spin_base_margin.value(),
                'normal_thresholds': [s.value() for s in self.normal_threshold_spins],
                'margin_multipliers': [s.value() for s in self.normal_multiplier_spins],
            }
        else:
            config['pair_overrides'].pop(self.pair_key, None)
            if not config['pair_overrides']:
                del config['pair_overrides']

        save_trade_config(config)
        self.accept()

    def _reset_to_defaults(self):
        config = _load_trade_config()
        global_base = config.get('base_margin', 100)
        self.spin_base_margin.setValue(global_base)
        for i, spin in enumerate(self.normal_threshold_spins):
            spin.setValue(self.DEFAULTS['normal_thresholds'][i])
        for i, spin in enumerate(self.normal_multiplier_spins):
            spin.setValue(self.DEFAULTS['margin_multipliers'][i])


# ═══════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pairs = []
        self.load_config()
        self.setStyleSheet(STYLESHEET)
        self.init_ui()
        self.init_tray()
        self.init_monitor()

    # ===== UI =====

    def init_ui(self):
        self.setWindowTitle("美股-币安  价差套利监控 & 自动交易")
        self.setGeometry(100, 100, 1100, 720)
        self.setMinimumSize(900, 550)

        # ---- QTabWidget ----
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #30363d; background: #0d1117; }
            QTabBar::tab { background: #161b22; color: #8b949e; padding: 8px 20px;
                           border: 1px solid #30363d; border-bottom: none;
                           border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #0d1117; color: #c9d1d9;
                                    border-bottom: 2px solid #1f6feb; }
            QTabBar::tab:hover { background: #21262d; }
        """)
        self.setCentralWidget(self.tab_widget)

        # ==== Tab 0: 监控 ====
        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout(monitor_tab)
        monitor_layout.setContentsMargins(16, 12, 16, 12)
        monitor_layout.setSpacing(12)

        # 统计卡片
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)
        self.card_total = StatCard("监控标的", "0", "#58a6ff")
        self.card_normal = StatCard("正常", "—", "#3fb950")
        self.card_alert = StatCard("告警信号", "—", "#ff7b72")
        self.card_update = StatCard("最后更新", "—", "#8b949e")
        self.card_status = StatCard("系统状态", "● 运行中", "#3fb950")
        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_normal)
        cards_layout.addWidget(self.card_alert)
        cards_layout.addWidget(self.card_update)
        cards_layout.addWidget(self.card_status)
        monitor_layout.addLayout(cards_layout)

        # 工具栏
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("background: #161b22; border-radius: 8px;")
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        self.btn_add = QPushButton("＋ 添加标的")
        self.btn_add.clicked.connect(self.on_add_pair)
        self.btn_add.setStyleSheet(self._btn_style("#21262d", "#30363d"))
        self.btn_del = QPushButton("✕ 删除选中")
        self.btn_del.clicked.connect(self.on_delete_pair)
        self.btn_pause = QPushButton("⏸ 暂停监控")
        self.btn_pause.clicked.connect(self.on_toggle_pause)
        self.btn_settings = QPushButton("⚙ 设置")
        self.btn_settings.clicked.connect(self.on_settings)
        self.btn_export = QPushButton("⬇ 导出告警")
        self.btn_export.clicked.connect(self.on_export_alerts)
        for btn in [self.btn_add, self.btn_del, self.btn_pause, self.btn_settings, self.btn_export]:
            btn.setMinimumHeight(32)
            toolbar_layout.addWidget(btn)
        toolbar_layout.addStretch()
        monitor_layout.addWidget(toolbar_widget)

        # 表格 + 日志
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(2)
        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_view.setShowGrid(False)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setFrameShape(QFrame.NoFrame)
        self.model = ArbitrageModel(self)
        self.table_view.setModel(self.model)
        splitter.addWidget(self.table_view)

        log_widget = QWidget()
        log_widget.setMaximumHeight(160)
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 4, 0, 0)
        log_header = QLabel("📋 告警日志")
        log_header.setStyleSheet("font-size: 11px; color: #8b949e; font-weight: 600; padding: 0 4px;")
        log_layout.addWidget(log_header)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("等待信号触发...")
        self.log_text.setFrameShape(QFrame.NoFrame)
        log_layout.addWidget(self.log_text)
        splitter.addWidget(log_widget)
        splitter.setSizes([420, 140])
        monitor_layout.addWidget(splitter)

        self.tab_widget.addTab(monitor_tab, "📊 套利监控")

        # ==== Tab 1: 自动交易 ====
        self._init_trading_tab()

        # ---- 状态栏 ----
        self.status_label = QLabel("等待首次数据...")
        self.statusBar().addPermanentWidget(self.status_label)

        self._refresh_table_display()

    def _init_trading_tab(self):
        """初始化交易标签页"""
        trade_tab = QWidget()
        trade_layout = QVBoxLayout(trade_tab)
        trade_layout.setContentsMargins(16, 12, 16, 12)
        trade_layout.setSpacing(12)

        # ---- 交易统计卡片 ----
        t_cards = QHBoxLayout()
        t_cards.setSpacing(12)
        self.tcard_positions = StatCard("活跃仓位", "0", "#58a6ff")
        self.tcard_margin = StatCard("总保证金", "0 U", "#d29922")
        self.tcard_pnl = StatCard("浮盈/亏", "$0.00", "#8b949e")
        self.tcard_window = StatCard("时间窗口", "—", "#8b949e")
        self.tcard_mode = StatCard("交易模式", "🧪 测试网", "#58a6ff")
        self.tcard_balance = StatCard("💰 USDT余额", "—", "#3fb950")
        t_cards.addWidget(self.tcard_positions)
        t_cards.addWidget(self.tcard_balance)
        t_cards.addWidget(self.tcard_margin)
        t_cards.addWidget(self.tcard_pnl)
        t_cards.addWidget(self.tcard_window)
        t_cards.addWidget(self.tcard_mode)
        trade_layout.addLayout(t_cards)

        # ---- 控制按钮 ----
        t_toolbar = QWidget()
        t_toolbar.setStyleSheet("background: #161b22; border-radius: 8px;")
        t_tb_layout = QHBoxLayout(t_toolbar)
        t_tb_layout.setContentsMargins(12, 8, 12, 8)
        t_tb_layout.setSpacing(8)

        self.btn_trade_toggle = QPushButton("▶ 启动交易")
        self.btn_trade_toggle.clicked.connect(self._on_trade_toggle)
        self.btn_emergency = QPushButton("🛑 紧急平仓")
        self.btn_emergency.setStyleSheet(
            "QPushButton { background: #da3633; border-color: #f85149; color: #fff; font-weight: 600; }"
            "QPushButton:hover { background: #f85149; }"
        )
        self.btn_emergency.clicked.connect(self._on_emergency_close)
        self.btn_api_keys = QPushButton("🔑 API密钥")
        self.btn_api_keys.clicked.connect(self._on_api_keys)
        self.btn_mode_switch = QPushButton("🔄 切换实盘/测试")
        self.btn_mode_switch.clicked.connect(self._on_mode_switch)

        for btn in [self.btn_trade_toggle, self.btn_emergency, self.btn_api_keys, self.btn_mode_switch]:
            btn.setMinimumHeight(32)
            t_tb_layout.addWidget(btn)

        # 分隔线 + 首仓保证金
        sep = QLabel("│")
        sep.setStyleSheet("color: #30363d; font-size: 16px; padding: 0 4px;")
        t_tb_layout.addWidget(sep)

        lbl_margin = QLabel("首仓:")
        lbl_margin.setStyleSheet("font-size: 12px; color: #8b949e;")
        t_tb_layout.addWidget(lbl_margin)

        self.spin_base_margin = QSpinBox()
        self.spin_base_margin.setRange(1, 10000)
        self.spin_base_margin.setSuffix(" U")
        self.spin_base_margin.setValue(100)
        self.spin_base_margin.setToolTip("首仓保证金，后续补仓比例为 1x→2x→3x→3x")
        self.spin_base_margin.valueChanged.connect(self._on_base_margin_changed)
        t_tb_layout.addWidget(self.spin_base_margin)

        self.lbl_level_preview = QLabel("(100 / 200 / 300 / 300 U)")
        self.lbl_level_preview.setStyleSheet("font-size: 11px; color: #484f58;")
        t_tb_layout.addWidget(self.lbl_level_preview)

        # 从配置加载当前首仓值
        trade_cfg = _load_trade_config()
        base = trade_cfg.get('base_margin', 100)
        self.spin_base_margin.blockSignals(True)
        self.spin_base_margin.setValue(base)
        self.spin_base_margin.blockSignals(False)
        self.lbl_level_preview.setText(
            f"({base} / {base*2} / {base*3} / {base*3} U)"
        )

        t_tb_layout.addStretch()
        trade_layout.addWidget(t_toolbar)

        # ---- 标的选择（分交易所） ----
        pair_splitter = QSplitter(Qt.Horizontal)
        pair_splitter.setHandleWidth(2)

        # ── 币安标的列表 ──
        bnb_pair_group = QGroupBox("🔶 币安交易标的 (Binance)")
        bnb_layout = QVBoxLayout(bnb_pair_group)
        bnb_layout.setSpacing(6)

        bnb_btn_layout = QHBoxLayout()
        self.btn_bnb_all = QPushButton("☑ 全选")
        self.btn_bnb_all.clicked.connect(lambda: self._on_select_all_pairs('binance'))
        self.btn_bnb_none = QPushButton("☐ 取消")
        self.btn_bnb_none.clicked.connect(lambda: self._on_deselect_all_pairs('binance'))
        for b in [self.btn_bnb_all, self.btn_bnb_none]:
            b.setMinimumHeight(26)
            b.setStyleSheet("font-size: 10px; padding: 3px 8px;")
            bnb_btn_layout.addWidget(b)
        bnb_btn_layout.addStretch()
        self.lbl_bnb_hint = QLabel("最大占用: 0 U")
        self.lbl_bnb_hint.setStyleSheet("font-size: 10px; color: #8b949e;")
        bnb_btn_layout.addWidget(self.lbl_bnb_hint)
        bnb_layout.addLayout(bnb_btn_layout)

        self.bnb_pair_list = QListWidget()
        self.bnb_pair_list.setMaximumHeight(180)
        self.bnb_pair_list.setStyleSheet("""
            QListWidget {
                background: #0d1117; border: 1px solid #30363d;
                border-radius: 6px; font-size: 11px;
            }
            QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #21262d; }
            QListWidget::item:hover { background: #161b22; }
        """)
        self.bnb_pair_list.itemChanged.connect(lambda item: self._on_pair_check_changed(item, 'binance'))
        self.bnb_pair_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bnb_pair_list.customContextMenuRequested.connect(
            lambda pos: self._on_pair_context_menu(pos, 'binance'))
        bnb_layout.addWidget(self.bnb_pair_list)

        # ── OKX 标的列表 ──
        okx_pair_group = QGroupBox("🔷 OKX交易标的 (OKX)")
        okx_layout = QVBoxLayout(okx_pair_group)
        okx_layout.setSpacing(6)

        okx_btn_layout = QHBoxLayout()
        self.btn_okx_all = QPushButton("☑ 全选")
        self.btn_okx_all.clicked.connect(lambda: self._on_select_all_pairs('okx'))
        self.btn_okx_none = QPushButton("☐ 取消")
        self.btn_okx_none.clicked.connect(lambda: self._on_deselect_all_pairs('okx'))
        for b in [self.btn_okx_all, self.btn_okx_none]:
            b.setMinimumHeight(26)
            b.setStyleSheet("font-size: 10px; padding: 3px 8px;")
            okx_btn_layout.addWidget(b)
        okx_btn_layout.addStretch()
        self.lbl_okx_hint = QLabel("最大占用: 0 U")
        self.lbl_okx_hint.setStyleSheet("font-size: 10px; color: #8b949e;")
        okx_btn_layout.addWidget(self.lbl_okx_hint)
        okx_layout.addLayout(okx_btn_layout)

        self.okx_pair_list = QListWidget()
        self.okx_pair_list.setMaximumHeight(180)
        self.okx_pair_list.setStyleSheet("""
            QListWidget {
                background: #0d1117; border: 1px solid #30363d;
                border-radius: 6px; font-size: 11px;
            }
            QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #21262d; }
            QListWidget::item:hover { background: #161b22; }
        """)
        self.okx_pair_list.itemChanged.connect(lambda item: self._on_pair_check_changed(item, 'okx'))
        self.okx_pair_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.okx_pair_list.customContextMenuRequested.connect(
            lambda pos: self._on_pair_context_menu(pos, 'okx'))
        okx_layout.addWidget(self.okx_pair_list)

        pair_splitter.addWidget(bnb_pair_group)
        pair_splitter.addWidget(okx_pair_group)
        pair_splitter.setSizes([450, 450])
        trade_layout.addWidget(pair_splitter)

        # ---- 持仓表格 ----
        t_splitter = QSplitter(Qt.Vertical)
        t_splitter.setHandleWidth(2)

        self.trade_table = QTableView()
        self.trade_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.trade_table.setAlternatingRowColors(True)
        self.trade_table.horizontalHeader().setStretchLastSection(True)
        self.trade_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.trade_table.setShowGrid(False)
        self.trade_table.verticalHeader().setVisible(False)
        self.trade_table.setFrameShape(QFrame.NoFrame)
        self.trade_model = TradePositionModel(self)
        self.trade_table.setModel(self.trade_model)
        t_splitter.addWidget(self.trade_table)

        # 交易日志
        t_log_widget = QWidget()
        t_log_widget.setMaximumHeight(140)
        t_log_layout = QVBoxLayout(t_log_widget)
        t_log_layout.setContentsMargins(0, 4, 0, 0)
        t_log_header = QLabel("📋 交易日志")
        t_log_header.setStyleSheet("font-size: 11px; color: #8b949e; font-weight: 600; padding: 0 4px;")
        t_log_layout.addWidget(t_log_header)
        self.trade_log = QTextEdit()
        self.trade_log.setReadOnly(True)
        self.trade_log.setPlaceholderText("交易引擎尚未启动，请配置API密钥后点击\"启动交易\"...")
        self.trade_log.setFrameShape(QFrame.NoFrame)
        t_log_layout.addWidget(self.trade_log)
        t_splitter.addWidget(t_log_widget)
        t_splitter.setSizes([400, 120])
        trade_layout.addWidget(t_splitter)

        self.tab_widget.addTab(trade_tab, "💰 自动交易")

        # 定时刷新窗口标签
        self._refresh_window_label()
        self._window_timer = QTimer()
        self._window_timer.timeout.connect(self._refresh_window_label)
        self._window_timer.start(30000)

        # 交易引擎初始化（在 init_monitor 中完成）

        # 初始化标的勾选列表
        self._refresh_pair_lists()

    def _refresh_window_label(self):
        """更新交易窗口标签"""
        try:
            sched = TradingScheduler()
            label = sched.get_window_label()
            self.tcard_window.set_value(label)
            # 根据窗口更新颜色
            w = sched.get_window()
            if w == WINDOW_TRADING:
                self.tcard_window.value_label.setStyleSheet(
                    "font-size: 22px; font-weight: 700; color: #3fb950; border: none;")
            elif w == WINDOW_CLOSE_ONLY:
                self.tcard_window.value_label.setStyleSheet(
                    "font-size: 22px; font-weight: 700; color: #d29922; border: none;")
            else:
                self.tcard_window.value_label.setStyleSheet(
                    "font-size: 22px; font-weight: 700; color: #8b949e; border: none;")
        except Exception:
            pass

    # ── 标的选择 ────────────────────────

    def _refresh_pair_lists(self):
        """从监控标的列表重建两个交易所的交易标的勾选列表"""
        if not hasattr(self, 'bnb_pair_list'):
            return

        # 读取配置
        trade_config = _load_trade_config()
        trading_pairs = trade_config.get('trading_pairs', {})
        # 向后兼容：旧格式是 list → 转换为新格式 dict
        if isinstance(trading_pairs, list):
            # 旧格式：所有标的分配给两个交易所
            trading_pairs = {'binance': list(trading_pairs), 'okx': list(trading_pairs)}
            trade_config['trading_pairs'] = trading_pairs
            save_trade_config(trade_config)

        bnb_enabled = set(trading_pairs.get('binance', []))
        okx_enabled = set(trading_pairs.get('okx', []))

        global_base = trade_config.get('base_margin', 100)
        pair_overrides = trade_config.get('pair_overrides', {})

        def _pair_display_info(key):
            """返回 (base_margin, first_threshold, max_margin, thresholds_str)"""
            ov = pair_overrides.get(key, {})
            bm = ov.get('base_margin', global_base)
            mults = ov.get('margin_multipliers', [1, 2, 3, 3])
            thresh = ov.get('normal_thresholds', [0.5, 1.0, 2.0, 3.0])
            pair_max = int(bm * sum(mults))
            thresh_str = "/".join(f"{t:.1f}" for t in thresh[:3]) + "%"
            return bm, thresh[0], pair_max, thresh_str

        def _populate_list(list_widget, enabled_set):
            list_widget.blockSignals(True)
            list_widget.clear()

            sorted_pairs = sorted(self.pairs, key=lambda p: (
                0 if f"{p[0]}:{p[1]}" in enabled_set else 1, p[0]
            ))

            for pair in sorted_pairs:
                stock, crypto = pair[0], pair[1]
                monitor_threshold = pair[2] if len(pair) > 2 else 0.5
                key = f"{stock}:{crypto}"
                is_checked = key in enabled_set

                bm, first_th, pair_max, thresh_str = _pair_display_info(key)

                if key in pair_overrides:
                    # 自定义策略：显示自定义阈值和最大占用
                    text = (f"{stock} → {crypto}   ⚙ 阈值:{first_th}% "
                            f"最大:{pair_max}U [{thresh_str}]")
                else:
                    text = (f"{stock} → {crypto}   (监控阈值 {monitor_threshold}%, "
                            f"最大 {pair_max}U)")

                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)

                if key in pair_overrides:
                    item.setForeground(QColor("#d29922"))
                elif is_checked:
                    item.setForeground(QColor("#c9d1d9"))
                else:
                    item.setForeground(QColor("#484f58"))

                list_widget.addItem(item)

            list_widget.blockSignals(False)

        _populate_list(self.bnb_pair_list, bnb_enabled)
        _populate_list(self.okx_pair_list, okx_enabled)

        # 更新资金估算 — 按每个标的的实际最大保证金累加
        def _calc_total_max(enabled_set):
            total = 0
            for key in enabled_set:
                _, _, pair_max, _ = _pair_display_info(key)
                total += pair_max
            return total

        bnb_total = _calc_total_max(bnb_enabled)
        okx_total = _calc_total_max(okx_enabled)
        self.lbl_bnb_hint.setText(
            f"最大占用: {bnb_total} U（{len(bnb_enabled)}个标的）"
        )
        self.lbl_okx_hint.setText(
            f"最大占用: {okx_total} U（{len(okx_enabled)}个标的）"
        )

    def _get_checked_pairs(self, list_widget):
        """获取 QListWidget 中勾选的标的 key 列表"""
        enabled = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.Checked:
                enabled.append(item.data(Qt.UserRole))
        return enabled

    def _save_trading_pairs(self):
        """将当前两个交易所的勾选状态保存到 auto_trader_config.json"""
        config = _load_trade_config()
        trading_pairs = config.get('trading_pairs', {})
        if isinstance(trading_pairs, list):
            trading_pairs = {'binance': list(trading_pairs), 'okx': list(trading_pairs)}

        if hasattr(self, 'bnb_pair_list'):
            trading_pairs['binance'] = self._get_checked_pairs(self.bnb_pair_list)
        if hasattr(self, 'okx_pair_list'):
            trading_pairs['okx'] = self._get_checked_pairs(self.okx_pair_list)

        config['trading_pairs'] = trading_pairs
        save_trade_config(config)

        # 热重载引擎
        if hasattr(self, 'trade_engine') and self.trade_engine:
            self.trade_engine.reload_config()

        # 统一刷新列表显示（hint 标签也在 _refresh_pair_lists 中计算）
        self._refresh_pair_lists()

    def _on_pair_check_changed(self, item, exchange):
        """勾选/取消勾选标的后保存配置"""
        self._save_trading_pairs()

    def _on_select_all_pairs(self, exchange):
        """全选某个交易所的所有标的"""
        list_widget = {'binance': self.bnb_pair_list, 'okx': self.okx_pair_list}.get(exchange)
        if list_widget:
            list_widget.blockSignals(True)
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(Qt.Checked)
            list_widget.blockSignals(False)
            self._save_trading_pairs()

    def _on_deselect_all_pairs(self, exchange):
        """取消全选某个交易所的所有标的"""
        list_widget = {'binance': self.bnb_pair_list, 'okx': self.okx_pair_list}.get(exchange)
        if list_widget:
            list_widget.blockSignals(True)
            for i in range(list_widget.count()):
                list_widget.item(i).setCheckState(Qt.Unchecked)
            list_widget.blockSignals(False)
            self._save_trading_pairs()

    # ── 分标的策略编辑 ────────────────────

    def _on_pair_context_menu(self, pos, exchange):
        """右键菜单：编辑或重置标的自定义策略"""
        list_widget = {'binance': self.bnb_pair_list, 'okx': self.okx_pair_list}.get(exchange)
        if not list_widget:
            return
        item = list_widget.itemAt(pos)
        if not item:
            return
        key = item.data(Qt.UserRole)

        config = _load_trade_config()
        has_override = key in config.get('pair_overrides', {})

        menu = QMenu(self)
        edit_action = menu.addAction("⚙ 编辑自定义阶梯/保证金...")
        menu.addSeparator()
        reset_action = menu.addAction("↩ 重置为全局默认")
        reset_action.setEnabled(has_override)

        action = menu.exec_(list_widget.mapToGlobal(pos))
        if action == edit_action:
            self._open_pair_override_dialog(key)
        elif action == reset_action:
            self._reset_pair_override(key)

    def _open_pair_override_dialog(self, key):
        """打开标的自定义策略编辑对话框"""
        dialog = PairOverrideDialog(self, pair_key=key)
        if dialog.exec_() == QDialog.Accepted:
            self._refresh_pair_lists()
            if hasattr(self, 'trade_engine') and self.trade_engine:
                self.trade_engine.reload_config()
            self.trade_log.append(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚙ {key} 自定义策略已更新"
            )

    def _reset_pair_override(self, key):
        """重置某个标的为全局默认策略"""
        config = _load_trade_config()
        overrides = config.get('pair_overrides', {})
        if key in overrides:
            del overrides[key]
            if not overrides:
                config.pop('pair_overrides', None)
            else:
                config['pair_overrides'] = overrides
            save_trade_config(config)
            self._refresh_pair_lists()
            if hasattr(self, 'trade_engine') and self.trade_engine:
                self.trade_engine.reload_config()
            self.trade_log.append(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ↩ {key} 已重置为全局默认"
            )

    def _on_base_margin_changed(self, value):
        """首仓保证金变更时保存配置并更新预览"""
        # 更新预览
        self.lbl_level_preview.setText(
            f"({value} / {value*2} / {value*3} / {value*3} U)"
        )
        # 保存配置
        config = _load_trade_config()
        config['base_margin'] = value
        save_trade_config(config)
        # 刷新标的选择列表中的保证金标注
        self._refresh_pair_lists()
        # 热重载引擎
        if hasattr(self, 'trade_engine') and self.trade_engine:
            self.trade_engine.reload_config()

    # ── 交易控制 ────────────────────────

    def _on_trade_toggle(self):
        if not hasattr(self, 'trade_engine') or not self.trade_engine:
            QMessageBox.warning(self, "提示", "交易引擎未初始化，请先配置API密钥。")
            return

        if self.trade_engine._paused:
            self.trade_engine.resume()
            self.btn_trade_toggle.setText("⏸ 暂停交易")
            self.btn_trade_toggle.setStyleSheet(
                "QPushButton { background: #d29922; border-color: #d29922; color: #000; font-weight: 600; }"
                "QPushButton:hover { background: #e2a62a; }"
            )
            self.trade_log.append("▶ 交易已启动")
        else:
            self.trade_engine.pause()
            self.btn_trade_toggle.setText("▶ 启动交易")
            self.btn_trade_toggle.setStyleSheet("")
            self.trade_log.append("⏸ 交易已暂停")

    def _on_emergency_close(self):
        reply = QMessageBox.question(
            self, "⚠️ 确认紧急平仓",
            "确定要立即平掉所有持仓吗？\n\n这将使用市价单关闭所有当前持仓！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if hasattr(self, 'trade_engine') and self.trade_engine:
                self.trade_engine.emergency_close_all()
                self.trade_log.append("🛑 已执行紧急全部平仓！")
            else:
                QMessageBox.warning(self, "提示", "交易引擎未启动。")

    def _on_api_keys(self):
        dialog = ApiKeyDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            if hasattr(self, 'trade_engine') and self.trade_engine:
                self.trade_engine.reload_config()
                self._refresh_pair_lists()
                self.trade_log.append("🔑 API配置已更新，交易所已重新连接")
                mode = self.trade_engine._mode
                self.tcard_mode.set_value("🧪 测试网" if mode == 'testnet' else "💰 实盘")
                # 主动拉取余额显示
                self._fetch_and_display_balances()
            QMessageBox.information(self, "配置已保存", "API密钥已保存。请点击\"启动交易\"开始运行。")

    def _on_mode_switch(self):
        if not hasattr(self, 'trade_engine') or not self.trade_engine:
            QMessageBox.warning(self, "提示", "请先配置API密钥。")
            return
        current = self.trade_engine._mode
        new_mode = 'live' if current == 'testnet' else 'testnet'
        reply = QMessageBox.question(
            self, "切换交易模式",
            f"确定从 {'🧪 测试网' if current == 'testnet' else '💰 实盘'} "
            f"切换到 {'💰 实盘' if new_mode == 'live' else '🧪 测试网'}？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.trade_engine.set_mode(new_mode)
            self.tcard_mode.set_value("🧪 测试网" if new_mode == 'testnet' else "💰 实盘")
            self.trade_log.append(f"🔄 已切换到 {'测试网' if new_mode == 'testnet' else '实盘'} 模式")

    # ── 交易信号处理 ────────────────────

    def _fetch_and_display_balances(self):
        """主动查询并显示已连接交易所的 USDT 余额"""
        if not hasattr(self, 'trade_engine') or not self.trade_engine:
            return
        try:
            balances = self.trade_engine.fetch_balances()
            active = self.trade_engine.get_active_exchanges()
            if not active:
                self.tcard_balance.set_value("—")
                self.tcard_balance.value_label.setToolTip("")
                return

            total = sum(balances.values())
            if total > 0:
                # 分别显示两个交易所余额
                bnb_bal = balances.get('binance', 0)
                okx_bal = balances.get('okx', 0)
                parts = []
                if 'binance' in active:
                    parts.append(f"BNB:{bnb_bal:.0f}")
                if 'okx' in active:
                    parts.append(f"OKX:{okx_bal:.0f}")
                self.tcard_balance.set_value(f"${total:.0f}")
                self.tcard_balance.value_label.setToolTip(" | ".join(parts))
            else:
                # 已连接但余额为 0
                names = [n[:3].upper() for n in active]
                self.tcard_balance.set_value("$0")
                self.tcard_balance.value_label.setToolTip(f"{' + '.join(names)}: $0")
        except Exception:
            pass

    def _on_trade_status(self, snapshots):
        """接收交易引擎状态更新"""
        self.trade_model.update_all(snapshots)
        # 更新卡片
        active = sum(1 for s in snapshots if s.get('status') in ('active', 'alert_only', 'reversal'))
        total_margin = sum(s.get('total_margin', 0) for s in snapshots)
        self.tcard_positions.set_value(str(active))
        self.tcard_margin.set_value(f"{total_margin:.0f}U")

        # 查询并显示余额
        self._fetch_and_display_balances()

    def _on_trade_executed(self, entry):
        """接收交易执行通知"""
        direction = entry.get('direction', '')
        icon = '🔴' if direction == 'long' else '🟢' if direction == 'short' else '📌'
        self.trade_log.append(
            f"[{entry.get('time', '')}] {icon} {entry.get('action', '')} "
            f"{entry.get('pair', '')} {entry.get('margin', '')}U "
            f"Lv.{entry.get('level', '')}"
        )

    def _on_trade_log(self, msg):
        """接收交易日志消息"""
        self.trade_log.append(msg)

    def _on_emergency_alert_signal(self, title, body):
        """接收紧急告警"""
        QMessageBox.warning(self, title, body)
        self.trade_log.append(f"⚠️ {title}")

    # ── 配置读写 ────────────────────────

    def load_config(self):
        """加载监控标的配置"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.pairs = data.get('pairs', [])
        except Exception:
            self.pairs = []

    def save_config(self):
        """保存监控标的配置"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({'pairs': self.pairs}, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    # ── 按钮样式 ────────────────────────

    def _btn_style(self, base="#21262d", hover="#30363d"):
        return f"""
            QPushButton {{
                background: {base}; border: 1px solid {hover};
                border-radius: 6px; padding: 6px 14px; font-weight: 500;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """

    # ── 工具栏操作 ──────────────────────

    def on_add_pair(self):
        """添加套利对"""
        dialog = AddPairDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            stock, crypto, threshold = dialog.get_values()
            if stock and crypto:
                self.pairs.append([stock, crypto, threshold])
                self.save_config()
                self._refresh_table_display()
                self._refresh_pair_lists()
                self.log_text.append(
                    f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ➕ "
                    f"已添加 {stock} → {crypto} (阈值{threshold}%)"
                )
                # pairs 通过 callback 动态获取，无需手动重载

    def on_delete_pair(self):
        """删除选中的套利对"""
        idx = self.table_view.currentIndex().row()
        if idx < 0:
            QMessageBox.information(self, "提示", "请先在表格中选中要删除的行")
            return
        if idx < len(self.pairs):
            removed = self.pairs.pop(idx)
            self.save_config()
            self._refresh_table_display()
            self._refresh_pair_lists()
            self.log_text.append(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✕ "
                f"已删除 {removed[0]} → {removed[1]}"
            )
            # pairs 通过 callback 动态获取，无需手动重载

    def on_toggle_pause(self):
        """暂停/恢复监控"""
        if hasattr(self, 'monitor') and self.monitor:
            if self.monitor._paused:
                self.monitor.resume()
                self.btn_pause.setText("⏸ 暂停监控")
                self.card_status.set_value("● 运行中")
                self.card_status.value_label.setStyleSheet(
                    "font-size: 22px; font-weight: 700; color: #3fb950; border: none;")
                self.log_text.append(
                    f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ▶ 监控已恢复"
                )
            else:
                self.monitor.pause()
                self.btn_pause.setText("▶ 恢复监控")
                self.card_status.set_value("⏸ 已暂停")
                self.card_status.value_label.setStyleSheet(
                    "font-size: 22px; font-weight: 700; color: #d29922; border: none;")
                self.log_text.append(
                    f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⏸ 监控已暂停"
                )

    def on_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.reload_notifier()
                try:
                    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                        s = json.load(f)
                    self.monitor.set_interval(s.get('poll_interval', 30))
                    self.monitor.fetcher.reload_proxy()
                except Exception:
                    pass
            self.log_text.append(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚙ 设置已更新"
            )

    def on_export_alerts(self):
        """导出告警日志"""
        try:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            save_path = os.path.join(CONFIG_DIR, f"alert_export_{ts}.json")
            if os.path.exists(ALERT_LOG_FILE):
                with open(ALERT_LOG_FILE, 'r', encoding='utf-8') as f:
                    alerts = json.load(f)
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(alerts, f, indent=4, ensure_ascii=False)
                QMessageBox.information(self, "导出成功",
                                        f"告警日志已导出到:\n{save_path}")
            else:
                QMessageBox.information(self, "提示", "暂无告警日志可导出")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _refresh_table_display(self):
        """从 pairs 刷新表格显示"""
        rows = []
        for p in self.pairs:
            stock, crypto = p[0], p[1]
            threshold = p[2] if len(p) > 2 else 0.5
            rows.append([stock, crypto, '—', '—', '—', threshold, '等待数据...', '—'])
        self.model.update_all(rows)
        self.card_total.set_value(str(len(self.pairs)))

    # ── 系统托盘 ────────────────────────

    def init_tray(self):
        """初始化系统托盘"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示窗口")
        show_action.triggered.connect(self.show)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("退出")
        quit_action.triggered.connect(self._quit_app)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        """托盘激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def _quit_app(self):
        """退出应用"""
        if hasattr(self, 'trade_engine') and self.trade_engine:
            self.trade_engine.stop()
            self.trade_engine.wait(3000)
        if hasattr(self, 'monitor') and self.monitor:
            self.monitor.stop()
            self.monitor.wait(3000)
        if hasattr(self, 'tray'):
            self.tray.hide()
        QApplication.quit()

    # ── 监控引擎 & 数据回调 ─────────────

    def init_monitor(self):
        """启动监控线程"""
        self.monitor = MonitorThread(pairs_callback=lambda: self.pairs)
        self.monitor.data_updated.connect(self._on_data_update)
        self.monitor.alert_triggered.connect(self._on_alert)
        self.monitor.start()

        # 加载轮询设置
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                s = json.load(f)
            self.monitor.set_interval(s.get('poll_interval', 30))
            if s.get('start_minimized', False):
                self.hide()
        except Exception:
            pass

        # 初始化交易引擎
        self._init_trade_engine()

    def _init_trade_engine(self):
        """初始化自动交易引擎"""
        if not hasattr(self, 'monitor') or not self.monitor:
            self.trade_log.append("[系统] ⚠ 监控未就绪，交易引擎初始化推迟")
            return
        self.trade_engine = TradeEngine(
            self.monitor.fetcher,
            self.monitor.notifier,
            lambda: self.pairs,
            self
        )
        self.trade_engine.status_updated.connect(self._on_trade_status)
        self.trade_engine.trade_executed.connect(self._on_trade_executed)
        self.trade_engine.log_message.connect(self._on_trade_log)
        self.trade_engine.emergency_alert.connect(self._on_emergency_alert_signal)
        self.trade_engine.start()
        self.trade_log.append("[系统] 交易引擎已初始化，等待手动启动...")
        # 延迟拉取余额（等交易所连接完成）
        QTimer.singleShot(2000, self._fetch_and_display_balances)

    def _on_data_update(self, results):
        """接收监控数据"""
        self.model.update_all(results)
        now = datetime.datetime.now().strftime('%H:%M:%S')
        self.card_update.set_value(now)

        normal = sum(1 for r in results if '正常' in str(r[6]))
        alert = sum(1 for r in results if '信号' in str(r[6]))
        self.card_normal.set_value(str(normal))
        self.card_alert.set_value(str(alert))

        self.status_label.setText(
            f"最后更新: {now}  |  标的: {len(self.pairs)}"
        )

    def _on_alert(self, entry):
        """接收告警"""
        dt = entry.get('time', datetime.datetime.now().strftime('%H:%M:%S'))
        stock = entry.get('stock', '?')
        crypto = entry.get('crypto', '?')
        diff = entry.get('diff', 0)
        msg = entry.get('message', '')
        self.log_text.append(
            f"[{dt}] ⚠ {stock}→{crypto} 价差 {diff:+.2f}% | {msg}"
        )

    # ── 窗口关闭 ────────────────────────

    def closeEvent(self, event):
        """关闭窗口事件 — 最小化到托盘或退出"""
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                s = json.load(f)
            if s.get('start_minimized', False) and QSystemTrayIcon.isSystemTrayAvailable():
                self.hide()
                event.ignore()
                return
        except Exception:
            pass
        self._quit_app()
        event.accept()

# ═══════════════════════════════════════════

