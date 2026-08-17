# CryptoArbitrage 美股-币安 价差套利监控 & 自动交易系统

## 给 AI 的完整开发规格

请根据以下规格，生成完整的 Python 项目代码。所有文件输出到 `CryptoArbitrage/` 目录下。

---

## 一、系统概述

这是一个**桌面 GUI + Web 双模式**的量化交易系统，核心逻辑是：
1. 实时监控美股（via yfinance）与币安加密货币（via ccxt）对应标的的价格差
2. 当价差超过阈值时，通过**阶梯式告警**（每 0.5% 一个台阶）通知用户
3. 在周末美股休市窗口期，自动用 10x 永续合约执行**阶梯加仓套利**交易
4. 支持用户自定义每个标的的分段加仓参数

---

## 二、技术栈

- **GUI**: PyQt5（系统托盘、深色主题、表格、多标签页）
- **数据源**: yfinance（美股价格）、ccxt（币安现货价格）
- **交易**: ccxt（Binance Futures + OKX Perpetual Swap，统一 10x 逐仓）
- **Web 端**: Flask + Jinja2，与桌面端共享监控数据（端口 5000）
- **通知**: QQ邮箱 SMTP / go-cqhttp QQ机器人 / 桌面弹窗 / 声音告警
- **持久化**: 4 个 JSON 配置文件

---

## 三、项目文件结构

```
CryptoArbitrage/
├── main.py                  # 主入口，启动 PyQt5 GUI
├── gui_app.py               # GUI 主窗口 + 所有对话框（~1900行）
├── paths.py                 # 路径管理（开发/PyInstaller 双模式）
├── data_fetcher.py          # 数据获取（yfinance + ccxt）
├── notifier.py              # 通知模块（邮件/QQ/桌面/声音）
├── monitor.py               # 监控引擎（QThread 后台轮询）
├── web_server.py            # Flask Web 服务器
├── requirements.txt         # Python 依赖
├── templates/
│   └── index.html           # Web 前端页面（移动端适配）
├── auto_trader/
│   ├── __init__.py          # 包说明
│   ├── strategy.py          # 策略状态机（开仓/加仓/止盈/反转）
│   ├── scheduler.py         # 时间窗口管理器
│   ├── exchange.py          # 交易所抽象层（Binance + OKX）
│   └── trade_engine.py      # 交易引擎（QThread 主循环）
├── config.json              # 监控标的列表（运行时生成）
├── settings.json            # 通知 & 代理设置（运行时生成）
├── auto_trader_config.json  # 交易API密钥 & 策略参数（运行时生成）
├── alert_log.json           # 告警历史（运行时生成）
└── app.log                  # 日志文件（运行时生成）
```

---

## 四、依赖（requirements.txt）

```
PyQt5>=5.15
yfinance>=0.2.0
ccxt>=4.0.0
requests>=2.28
pandas>=1.5
Flask>=3.0
```

---

## 五、配置文件规格

### 5.1 config.json — 监控标的列表
```json
{
    "pairs": [
        ["MSTR", "BTCUSDT", 0.5],
        ["COIN", "BTCUSDT", 0.8]
    ]
}
```
`["美股代码", "币安交易对", 监控阈值%]`，首次运行自动生成。

### 5.2 settings.json — 通知 & 代理 & 静默时段
```json
{
    "qq_enabled": false,
    "qq_user_id": 0,
    "qq_http_url": "http://127.0.0.1:5700",
    "email_enabled": false,
    "email_user": "",
    "email_pass": "",
    "email_to": "",
    "desktop_notify": true,
    "sound_alert": true,
    "poll_interval": 30,
    "alert_cooldown": 300,
    "start_minimized": false,
    "proxy": {
        "enabled": false,
        "http": "http://127.0.0.1:10809",
        "https": "http://127.0.0.1:10809"
    },
    "quiet_hours": {
        "enabled": false,
        "days": [0, 1, 2, 3, 4],
        "start": "09:00",
        "end": "17:00"
    }
}
```
- `quiet_hours`: 用户可自定义的邮件静默时段。`days` 中 0=周一...6=周日。支持跨天（如 start="22:00", end="06:00"）

### 5.3 auto_trader_config.json — 交易配置
```json
{
    "mode": "testnet",
    "trading_pairs": {
        "binance": ["MSTR:BTCUSDT"],
        "okx": ["COIN:BTCUSDT"]
    },
    "binance": {
        "enabled": true,
        "live_api_key": "", "live_secret": "",
        "testnet_api_key": "", "testnet_secret": ""
    },
    "okx": {
        "enabled": false,
        "live_api_key": "", "live_secret": "", "live_passphrase": "",
        "testnet_api_key": "", "testnet_secret": "", "testnet_passphrase": ""
    },
    "leverage": 10,
    "base_margin": 100,
    "take_profit_pct": 5.0,
    "poll_interval": 10,
    "pair_overrides": {
        "MSTR:BTCUSDT": {
            "base_margin": 150,
            "normal_thresholds": [0.3, 0.8, 1.5, 2.5],
            "margin_multipliers": [1, 1.5, 2, 2]
        }
    }
}
```
- `pair_overrides`: 按标的自定义阶梯参数，所有字段可选，缺失则回退全局默认
- `trading_pairs`: 向后兼容旧 list 格式 → 自动转为 dict

---

## 六、各模块详细规格

### 6.1 paths.py — 统一路径管理

```python
"""
统一配置路径管理
开发模式：配置文件读写 → 项目根目录
PyInstaller 打包（sys.frozen）：配置文件读写 → %APPDATA%/CryptoArbitrage/
"""
import os
import sys

def get_config_dir():
    """返回配置文件目录（保证目录存在）"""
    if getattr(sys, 'frozen', False):
        config_dir = os.path.join(os.environ.get('APPDATA', ''), 'CryptoArbitrage')
    else:
        config_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def migrate_old_configs(config_dir):
    """打包模式下，首次运行时从 exe 目录迁移旧配置到 APPDATA"""
    if not getattr(sys, 'frozen', False):
        return
    exe_dir = os.path.dirname(sys.executable)
    for fname in ['config.json', 'settings.json', 'auto_trader_config.json', 'alert_log.json']:
        old_path = os.path.join(exe_dir, fname)
        new_path = os.path.join(config_dir, fname)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            try:
                import shutil
                shutil.copy2(old_path, new_path)
            except Exception:
                pass
```

**关键逻辑**：
- 所有模块通过 `from paths import get_config_dir; CONFIG_DIR = get_config_dir()` 获取配置目录
- 开发模式返回 `paths.py` 所在目录（项目根目录）
- PyInstaller 打包后返回 `%APPDATA%\CryptoArbitrage\`（有写权限）

---

### 6.2 data_fetcher.py — 数据获取

```python
"""
数据获取模块 — yfinance 美股 + ccxt 币安现货
支持 HTTP 代理（国内访问必需）
"""
import yfinance as yf
import ccxt
import datetime, logging, time, json, os, requests
from paths import get_config_dir

logger = logging.getLogger(__name__)
SETTINGS_FILE = os.path.join(get_config_dir(), 'settings.json')

def _load_proxy():
    """从 settings.json 读取代理配置"""
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            s = json.load(f)
        proxy = s.get('proxy', {})
        if proxy.get('enabled') and proxy.get('http'):
            return {'http': proxy['http'], 'https': proxy.get('https') or proxy['http']}
    except Exception:
        pass
    return None

class PriceFetcher:
    def __init__(self):
        self._proxy = _load_proxy()
        self._session = None
        self._ticker_cache = {}
        self._last_request_time = 0
        self._min_interval = 1.5  # yfinance 请求最小间隔

        # 币安现货
        binance_kwargs = {'enableRateLimit': True, 'options': {'defaultType': 'spot'}, 'timeout': 15000}
        if self._proxy:
            binance_kwargs['proxies'] = self._proxy
        self.exchange = ccxt.binance(binance_kwargs)
        self._init_yf_session()

    def _init_yf_session(self):
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': 'Mozilla/5.0 ...'})
        if self._proxy:
            self._session.proxies.update(self._proxy)

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _get_ticker(self, symbol):
        if symbol not in self._ticker_cache:
            self._ticker_cache[symbol] = yf.Ticker(symbol, session=self._session)
        return self._ticker_cache[symbol]

    def _is_weekend(self):
        return datetime.datetime.now().weekday() >= 5

    def get_us_stock_price(self, symbol):
        """
        取美股参考价：
        - 周末：直接用最近交易日收盘价
        - 非周末：比较收盘价 vs 盘后价，返回较低者（保守估计）
        """
        try:
            self._rate_limit()
            ticker = self._get_ticker(symbol)
            data = ticker.history(period="5d")
            if data.empty:
                return None
            close_price = float(data['Close'].iloc[-1])
            if self._is_weekend():
                return round(close_price, 2)
            try:
                fast = ticker.fast_info
                post_price = fast.get('postMarketPrice')
                if post_price and float(post_price) > 0:
                    return round(min(close_price, float(post_price)), 2)
            except Exception:
                pass
            return round(close_price, 2)
        except Exception as e:
            logger.error(f"{symbol}: {e}")
            return None

    def get_binance_price(self, symbol):
        """获取币安现货最新成交价，重试 2 次"""
        for attempt in range(2):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                last = ticker.get('last')
                if last and last > 0:
                    return round(float(last), 2)
            except ccxt.RateLimitExceeded:
                time.sleep(3)
            except ccxt.NetworkError:
                return None
            except Exception as e:
                logger.error(f"币安 {symbol}: {e}")
                return None
        return None

    def reload_proxy(self):
        self._proxy = _load_proxy()
        if self._proxy:
            self.exchange.proxies = self._proxy
        else:
            self.exchange.proxies = None
        self._ticker_cache.clear()
        self._init_yf_session()

    def clear_cache(self):
        self._ticker_cache.clear()
```

**关键逻辑**：
- 美股取价策略：收盘价 vs 盘后价取较低者（保守锚定基准）
- 周末取最近交易日收盘价（周五）
- yfinance 通过共享 `requests.Session` 注入代理

---

### 6.3 notifier.py — 通知模块

```python
"""
通知模块 — QQ邮箱 / go-cqhttp / 桌面弹窗 / 声音
"""
import smtplib, ssl, requests, logging, json, os, time
from email.mime.text import MIMEText
from email.header import Header
from PyQt5.QtCore import Q_ARG
from PyQt5.QtWidgets import QSystemTrayIcon
from paths import get_config_dir

logger = logging.getLogger(__name__)
CONFIG_DIR = get_config_dir()
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')

def load_settings():
    default = {
        'qq_enabled': False, 'qq_user_id': 0, 'qq_http_url': 'http://127.0.0.1:5700',
        'email_enabled': False, 'email_smtp': 'smtp.qq.com', 'email_port': 465,
        'email_user': '', 'email_pass': '', 'email_to': '',
        'desktop_notify': True, 'sound_alert': True, 'alert_cooldown': 300,
        'quiet_hours': {'enabled': False, 'days': [0,1,2,3,4], 'start': '09:00', 'end': '17:00'},
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                default.update(json.load(f))
    except Exception as e:
        logger.warning(f"加载设置失败: {e}")
    return default

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

class Notifier:
    def __init__(self):
        self.settings = load_settings()
        self._cooldown = {}  # {alert_key: last_sent_time}
        self._tray = None

    def set_tray(self, tray):
        self._tray = tray

    def reload_settings(self):
        self.settings = load_settings()

    def _is_cooling_down(self, key):
        """告警冷却：同一 key 在 cooldown 秒内不重复发送"""
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
            return
        if self.settings.get('email_enabled'):
            self._send_email(title, message)
        if self.settings.get('qq_enabled'):
            self._send_qq(f"{title}\n{message}")
        if self.settings.get('desktop_notify'):
            self._send_desktop(title, message)
        if self.settings.get('sound_alert'):
            self._play_alert_sound()

    def _send_email(self, title, message):
        """QQ邮箱 SMTP-SSL 发送"""
        try:
            user = self.settings.get('email_user', '')
            passwd = self.settings.get('email_pass', '')
            if not user or not passwd:
                return
            msg = MIMEText(message, 'plain', 'utf-8')
            msg['Subject'] = Header(title, 'utf-8')
            msg['From'] = user
            msg['To'] = self.settings.get('email_to', '') or user
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.settings.get('email_smtp', 'smtp.qq.com'),
                                  self.settings.get('email_port', 465),
                                  context=ctx, timeout=10) as server:
                server.login(user, passwd)
                server.sendmail(user, [msg['To']], msg.as_string())
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")

    def _send_qq(self, message):
        """go-cqhttp HTTP API"""
        try:
            url = f"{self.settings.get('qq_http_url')}/send_private_msg"
            resp = requests.post(url, json={"user_id": self.settings.get('qq_user_id'), "message": message}, timeout=5)
        except Exception:
            pass

    def _send_desktop(self, title, message):
        """系统托盘弹窗"""
        if self._tray and self._tray.supportsMessages():
            self._tray.showMessage(title, message, QSystemTrayIcon.Warning, 3000)

    def _play_alert_sound(self):
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass
```

**关键逻辑**：
- `_is_cooling_down(alert_key)`: 同一告警 key 在 cooldown 秒内不重复发送（防刷屏）
- 多渠道并发：邮件（QQ SMTP）→ QQ机器人 → 桌面弹窗 → 声音

---

### 6.4 monitor.py — 监控引擎

```python
"""
监控引擎 — QThread 后台轮询价格，价差超阈值触发阶梯告警
"""
import time, threading, logging, os, json, datetime
from PyQt5.QtCore import QThread, pyqtSignal
from data_fetcher import PriceFetcher
from notifier import Notifier
from paths import get_config_dir

logger = logging.getLogger(__name__)
CONFIG_DIR = get_config_dir()
ALERT_LOG_FILE = os.path.join(CONFIG_DIR, 'alert_log.json')

class MonitorThread(QThread):
    data_updated = pyqtSignal(list)      # [(stock, crypto, us_price, binance_price, diff_str, threshold, status, time), ...]
    alert_triggered = pyqtSignal(dict)    # 单条告警记录

    def __init__(self, pairs_callback, parent=None):
        super().__init__(parent)
        self.pairs_callback = pairs_callback  # 返回 [(stock, crypto, threshold), ...]
        self.fetcher = PriceFetcher()
        self.notifier = Notifier()
        self._running = True
        self._paused = False
        self._poll_interval = 30
        self._alert_state = {}  # {alert_key: (last_level, confirm_count, direction)}

    def set_interval(self, seconds):
        self._poll_interval = max(5, min(300, seconds))

    def pause(self): self._paused = True
    def resume(self): self._paused = False
    def stop(self): self._running = False

    def reload_notifier(self):
        self.notifier.reload_settings()

    def run(self):
        """主循环：轮询 → 计算价差 → 阶梯告警 → sleep"""
        while self._running:
            if self._paused:
                time.sleep(1)
                continue
            pairs = self.pairs_callback()
            if not pairs:
                time.sleep(1)
                continue
            results = []
            now = datetime.datetime.now()
            for stock, crypto, threshold in pairs:
                result = self._check_pair(stock, crypto, threshold, now)
                results.append(result)
            self.data_updated.emit(results)
            # 可中断 sleep
            elapsed = 0
            while elapsed < self._poll_interval and self._running:
                if not self._paused:
                    time.sleep(1)
                    elapsed += 1
                else:
                    time.sleep(1)

    def _is_quiet_hours(self, now=None):
        """
        静默时段判断 — 读取 settings.json quiet_hours
        返回 True = 静默（不推送）
        支持同一天内时段（如 09:00→17:00）和跨天时段（如 22:00→06:00）
        """
        qh = self.notifier.settings.get('quiet_hours', {})
        if not qh.get('enabled'):
            return False
        if now is None:
            now = datetime.datetime.now()
        weekday = now.weekday()
        if weekday not in qh.get('days', [0,1,2,3,4]):
            return False
        now_minutes = now.hour * 60 + now.minute
        try:
            s_h, s_m = map(int, qh.get('start', '09:00').split(':'))
            e_h, e_m = map(int, qh.get('end', '17:00').split(':'))
        except (ValueError, AttributeError):
            return False
        start_minutes = s_h * 60 + s_m
        end_minutes = e_h * 60 + e_m
        if start_minutes <= end_minutes:
            return start_minutes <= now_minutes < end_minutes
        else:
            return now_minutes >= start_minutes or now_minutes < end_minutes

    def _calc_level(self, diff_percent):
        """价差阶梯级别：int(|diff| / 0.5) * 0.5"""
        return int(abs(diff_percent) * 2) / 2

    def _check_pair(self, stock, crypto, threshold, timestamp):
        """计算单个标的价差：(币安价 - 美股参考价) / 美股价 * 100"""
        us_price = self.fetcher.get_us_stock_price(stock)
        binance_price = self.fetcher.get_binance_price(crypto)
        if us_price is None or binance_price is None:
            return [stock, crypto, 'N/A', 'N/A', 'N/A', str(threshold), '数据异常', timestamp.strftime("%H:%M:%S")]
        diff_percent = round((binance_price - us_price) / us_price * 100, 2)
        status = self._evaluate_status(stock, crypto, us_price, binance_price, diff_percent, threshold, f"{stock}:{crypto}", timestamp)
        return [stock, crypto, str(us_price), str(binance_price), f"{diff_percent:+.2f}%", str(threshold), status, timestamp.strftime("%H:%M:%S")]

    def _evaluate_status(self, stock, crypto, us_price, binance_price, diff_percent, threshold, alert_key, timestamp):
        """价差超过阈值 → 进入阶梯告警；回归阈值内 → 重置"""
        if diff_percent <= -threshold:
            return self._check_ladder(stock, crypto, us_price, binance_price, diff_percent, threshold, alert_key, timestamp, direction='buy')
        elif diff_percent >= threshold:
            return self._check_ladder(stock, crypto, us_price, binance_price, diff_percent, threshold, alert_key, timestamp, direction='sell')
        else:
            self._alert_state.pop(alert_key, None)  # 回归正常范围，完全重置
            return f"正常 ({diff_percent:+.2f}%)"

    def _check_ladder(self, stock, crypto, us_price, binance_price, diff_percent, threshold, alert_key, timestamp, direction):
        """
        阶梯告警核心：
        - 需要连续 2 次确认（防瞬时波动）
        - 只有跨过新的 0.5% 台阶才重新告警（不重复刷）
        - 价差回落保留原级别，不告警
        """
        current_level = self._calc_level(diff_percent)
        prev_state = self._alert_state.get(alert_key)

        if prev_state and prev_state[2] == direction:
            last_level, confirm_count, _ = prev_state
        else:
            last_level, confirm_count = 0, 0

        confirm_count += 1
        self._alert_state[alert_key] = (last_level, confirm_count, direction)

        if confirm_count < 2:
            label = "折价" if direction == 'buy' else "溢价"
            return f"⏳ {label}确认中({current_level:.1f}%)..."

        if current_level > last_level:
            self._alert_state[alert_key] = (current_level, confirm_count, direction)
            # 构造告警消息
            icon = '🔴' if direction == 'buy' else '🟢'
            name = '买入信号' if direction == 'buy' else '溢价信号'
            label = '折价' if direction == 'buy' else '溢价'
            msg = (f"【{name} · {label}{current_level:.1f}%阶梯】\n"
                   f"美股 {stock}: ${us_price}\n币安 {crypto}: ${binance_price}\n"
                   f"{label}幅度: {diff_percent:+.2f}%\n触发阶梯: {current_level:.1f}%")

            # 静默时段不推送，但 GUI 正常显示
            if self._is_quiet_hours(timestamp):
                logger.debug(f"[{alert_key}] 静默时段，跳过推送")
            else:
                self.notifier.send_alert(f"{icon} {stock} → {crypto} {name}({current_level:.1f}%)", msg, alert_key=alert_key)
            self._log_alert(stock, crypto, 'BUY' if direction=='buy' else 'SELL', us_price, binance_price, diff_percent, timestamp)
            return f"{icon} {name}! [阶梯{current_level:.1f}%] ({diff_percent:+.2f}%)"
        elif current_level == last_level:
            label = "折价" if direction == 'buy' else "溢价"
            return f"{label}{current_level:.1f}% (监控中) ({diff_percent:+.2f}%)"
        else:
            label = "折价" if direction == 'buy' else "溢价"
            return f"{label}回落中 ←{last_level:.1f}% ({diff_percent:+.2f}%)"

    def _log_alert(self, stock, crypto, direction, us_price, binance_price, diff_percent, timestamp):
        """记录告警到 alert_log.json（最近 500 条）"""
        entry = {'time': timestamp.strftime('%Y-%m-%d %H:%M:%S'), 'stock': stock, 'crypto': crypto,
                 'direction': direction, 'us_price': us_price, 'binance_price': binance_price,
                 'diff_percent': round(diff_percent, 2)}
        try:
            logs = []
            if os.path.exists(ALERT_LOG_FILE):
                with open(ALERT_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            logs.append(entry)
            if len(logs) > 500:
                logs = logs[-500:]
            with open(ALERT_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"告警日志写入失败: {e}")
        self.alert_triggered.emit(entry)
```

**关键逻辑**：
- **价差计算**: `(币安价 - 美股参考价) / 美股参考价 * 100`
  - 负值 = 币安折价 = 买入信号
  - 正值 = 币安溢价 = 卖出信号
- **阶梯告警**: 每 0.5% 一个台阶，只有跨过新台阶才告警
  - 防止瞬时波动：需要连续 2 次轮询确认才触发
  - 同一台阶不重复告警
  - 价差回落保留原级别，不告警
  - 价差回归阈值内：完全重置
- **静默时段**: 用户可在设置中自定义；静默期间 GUI 照常显示状态，但跳过邮件/推送

---

### 6.5 auto_trader/strategy.py — 策略引擎

```python
"""
策略状态机 — 管理每个标的的开仓/加仓/止盈/反转
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)

class ActionType(Enum):
    NONE = 'none'
    OPEN_LONG = 'open_long'
    OPEN_SHORT = 'open_short'
    ADD_LONG = 'add_long'
    ADD_SHORT = 'add_short'
    TAKE_PROFIT = 'take_profit'
    FORCE_CLOSE = 'force_close'
    EMERGENCY_ALERT = 'emergency'

class Status(Enum):
    IDLE = 'idle'
    ACTIVE = 'active'
    CLOSED = 'closed'
    ALERT_ONLY = 'alert_only'
    REVERSAL = 'reversal'

@dataclass
class EntryRecord:
    time: datetime
    level: float
    direction: str      # 'long' | 'short'
    margin: float
    price: float
    exchange: str

@dataclass
class TradeAction:
    action_type: ActionType
    stock: str
    crypto: str
    margin: float = 0
    direction: str = ''
    level: float = 0
    diff_percent: float = 0
    emergency_msg: str = ''

@dataclass
class PairState:
    stock: str
    crypto: str
    direction: str = ''
    status: Status = Status.IDLE
    triggered_levels: set = field(default_factory=set)
    entries: list = field(default_factory=list)
    first_open_time: datetime | None = None
    close_time: datetime | None = None
    reversal: bool = False
    reversal_base_level: float = 0

    @property
    def alert_key(self):
        return f"{self.stock}:{self.crypto}"

    @property
    def total_margin(self):
        return sum(e.margin for e in self.entries)

    @property
    def is_active(self):
        return self.status in (Status.ACTIVE, Status.ALERT_ONLY, Status.REVERSAL)

@dataclass
class PairOverrides:
    """单个标的的自定义策略参数（所有字段可选，None = 使用全局默认）"""
    base_margin: float | None = None
    normal_thresholds: list | None = None
    margin_multipliers: list | None = None

class StrategyEngine:
    """
    策略引擎 — 对每个标的独立追踪状态，每次轮询调用 evaluate()

    核心参数：
    - 阶梯触发阈值（全局默认）: [0.5, 1.0, 2.0, 3.0] %
    - 保证金倍数（全局默认）: [1, 2, 3, 3]
    - base_margin: 首仓保证金
    - 反转触发: 平仓后 1 小时内反向 2%+ 开仓
    """

    DEFAULT_NORMAL_THRESHOLDS = [0.5, 1.0, 2.0, 3.0]
    DEFAULT_REVERSAL_THRESHOLDS = [2.0, 3.0, 4.0, 5.0]
    DEFAULT_MARGIN_MULTIPLIERS = [1, 2, 3, 3]
    EMERGENCY_LEVEL = 3.0
    TAKE_PROFIT_PCT = 5.0
    REVERSAL_WINDOW_HOURS = 1
    REVERSAL_THRESHOLD = 2.0

    def __init__(self, base_margin=100):
        self._states: dict[str, PairState] = {}
        self.leverage = 10
        self.base_margin = base_margin

    @staticmethod
    def _compute_levels(thresholds, multipliers, base_margin):
        """计算 [(触发阈值%, 保证金U), ...]"""
        return [(t, base_margin * m) for t, m in zip(thresholds, multipliers)]

    def resolve_levels(self, overrides, is_reversal):
        """
        根据 PairOverrides 解析阶梯参数，回退链：
        pair override → 全局默认
        """
        effective_base = self.base_margin
        if overrides and overrides.base_margin is not None:
            effective_base = overrides.base_margin

        if overrides and overrides.normal_thresholds and not is_reversal:
            thresholds = overrides.normal_thresholds
        elif is_reversal:
            thresholds = list(self.DEFAULT_REVERSAL_THRESHOLDS)
        else:
            thresholds = list(self.DEFAULT_NORMAL_THRESHOLDS)

        multipliers = list(self.DEFAULT_MARGIN_MULTIPLIERS)
        if overrides and overrides.margin_multipliers:
            multipliers = overrides.margin_multipliers

        return self._compute_levels(thresholds, multipliers, effective_base)

    def get_state(self, stock, crypto):
        key = f"{stock}:{crypto}"
        if key not in self._states:
            self._states[key] = PairState(stock=stock, crypto=crypto)
        return self._states[key]

    def reset_state(self, stock, crypto):
        self._states[f"{stock}:{crypto}"] = PairState(stock=stock, crypto=crypto)

    def reset_all(self):
        self._states.clear()

    def evaluate(self, stock, crypto, diff_percent, us_price, crypto_price, now, can_open, should_force_close, overrides=None):
        """
        主入口 — 每次轮询调用

        返回 TradeAction 或 None
        处理顺序：强制平仓 → 反转检查 → 止盈 → 紧急告警 → 加仓 → 开新仓
        """
        state = self.get_state(stock, crypto)
        abs_diff = abs(diff_percent)

        if should_force_close and state.is_active:
            return TradeAction(ActionType.FORCE_CLOSE, stock, crypto, direction=state.direction, diff_percent=diff_percent)

        if state.status == Status.CLOSED:
            return self._check_reversal(state, stock, crypto, diff_percent, crypto_price, now, can_open, overrides=overrides)

        if state.is_active:
            if abs_diff > self.EMERGENCY_LEVEL and state.status != Status.ALERT_ONLY:
                state.status = Status.ALERT_ONLY
                return TradeAction(ActionType.EMERGENCY_ALERT, stock, crypto,
                                   direction=state.direction, level=abs_diff,
                                   diff_percent=diff_percent,
                                   emergency_msg=f"⚠ {stock}-{crypto} 价差超过 {self.EMERGENCY_LEVEL}%!")
            if can_open:
                add = self._check_add(state, stock, crypto, diff_percent, crypto_price, now, overrides=overrides)
                if add:
                    return add
            return None

        if state.status == Status.IDLE and can_open:
            return self._check_entry(state, stock, crypto, diff_percent, crypto_price, now, overrides=overrides)

        return None

    def _check_entry(self, state, stock, crypto, diff_percent, crypto_price, now, overrides=None):
        """检查首次开仓：价差达到某级阈值 → 开仓"""
        abs_diff = abs(diff_percent)
        levels = self.resolve_levels(overrides, is_reversal=state.reversal)
        for level, margin in levels:
            if abs_diff >= level and level not in state.triggered_levels:
                direction = 'long' if diff_percent <= 0 else 'short'
                state.triggered_levels.add(level)
                state.direction = direction
                state.status = Status.ACTIVE if abs_diff <= self.EMERGENCY_LEVEL else Status.ALERT_ONLY
                state.first_open_time = now
                state.entries.append(EntryRecord(time=now, level=level, direction=direction,
                                                 margin=margin, price=crypto_price, exchange=''))
                at = ActionType.OPEN_LONG if direction == 'long' else ActionType.OPEN_SHORT
                return TradeAction(at, stock, crypto, margin=margin, direction=direction, level=level, diff_percent=diff_percent)
        return None

    def _check_add(self, state, stock, crypto, diff_percent, crypto_price, now, overrides=None):
        """检查加仓：价差达到更高一级阈值"""
        if state.status == Status.ALERT_ONLY:
            return None
        abs_diff = abs(diff_percent)
        levels = self.resolve_levels(overrides, is_reversal=state.reversal)
        for level, margin in levels:
            if abs_diff >= level and level not in state.triggered_levels:
                state.triggered_levels.add(level)
                state.entries.append(EntryRecord(time=now, level=level, direction=state.direction,
                                                 margin=margin, price=crypto_price, exchange=''))
                if abs_diff > self.EMERGENCY_LEVEL:
                    state.status = Status.ALERT_ONLY
                at = ActionType.ADD_LONG if state.direction == 'long' else ActionType.ADD_SHORT
                return TradeAction(at, stock, crypto, margin=margin, direction=state.direction, level=level, diff_percent=diff_percent)
        return None

    def _check_reversal(self, state, stock, crypto, diff_percent, crypto_price, now, can_open, overrides=None):
        """反转检查：平仓后 1 小时内反向 ≥ 2% 则反转开仓"""
        if not state.close_time or not state.first_open_time or not can_open:
            return None
        if state.close_time - state.first_open_time > timedelta(hours=self.REVERSAL_WINDOW_HOURS):
            return None
        if abs(diff_percent) < self.REVERSAL_THRESHOLD:
            return None
        new_direction = 'long' if diff_percent <= 0 else 'short'
        if new_direction == state.direction:
            return None
        # 触发反转
        state.direction = new_direction
        state.triggered_levels = set()
        state.entries = []
        state.first_open_time = now
        state.close_time = None
        state.reversal = True
        state.status = Status.IDLE
        return self._check_entry(state, stock, crypto, diff_percent, crypto_price, now, overrides=overrides)

    def mark_closed(self, stock, crypto, now, was_take_profit=True):
        """引擎平仓后调用"""
        state = self.get_state(stock, crypto)
        state.close_time = now
        state.status = Status.CLOSED
```

**关键逻辑**：
- **价差方向**: diff ≤ 0（币安折价）→ long；diff ≥ 0（币安溢价）→ short
- **阶梯参数**: `base_margin × 倍数` = 该级保证金。例如 base=100, mult=[1,2,3,3] → [100,200,300,300]U
- **`resolve_levels()`**: pair override → 全局默认的回退链
- **反转模式**: 平仓后 1 小时内反向 2%+ → 以更高阈值重新开仓
- **止盈**: 在 trade_engine 层从交易所查 unrealized_pnl / total_margin ≥ 5%

---

### 6.6 auto_trader/scheduler.py — 时间窗口

```python
"""
时间窗口管理器 — 北京时间（UTC+8）
- 周一 12:00 → 周六 08:00 : testnet（测试网模式，安全模拟）
- 周六 08:00 → 周日 18:00 : trading（可开仓 + 平仓，唯一真实交易窗口）
- 周日 18:00 → 周一 12:00 : close_only（只平仓不开仓，收割周末持仓）
"""
import datetime

BEIJING = datetime.timezone(datetime.timedelta(hours=8))
WINDOW_TESTNET = 'testnet'
WINDOW_TRADING = 'trading'
WINDOW_CLOSE_ONLY = 'close_only'

class TradingScheduler:
    def __init__(self):
        self._last_window = None
        self._force_close_done = False

    def get_window(self, dt=None):
        if dt is None:
            dt = datetime.datetime.now(BEIJING)
        weekday = dt.weekday()
        hour = dt.hour
        if weekday == 5:       # Sat
            return WINDOW_TRADING if hour >= 8 else WINDOW_TESTNET
        elif weekday == 6:     # Sun
            return WINDOW_TRADING if hour < 18 else WINDOW_CLOSE_ONLY
        elif weekday == 0:     # Mon
            return WINDOW_CLOSE_ONLY if hour < 12 else WINDOW_TESTNET
        else:                  # Tue-Fri
            return WINDOW_TESTNET

    def can_open_new(self, dt=None):
        return self.get_window(dt) == WINDOW_TRADING

    def can_manage_positions(self, dt=None):
        return self.get_window(dt) in (WINDOW_TRADING, WINDOW_CLOSE_ONLY)

    def should_force_close(self, dt=None):
        """周一 12:00 触发一次性强制平仓"""
        if dt is None:
            dt = datetime.datetime.now(BEIJING)
        if dt.weekday() == 0 and dt.hour >= 12:
            if not self._force_close_done:
                self._force_close_done = True
                return True
        else:
            self._force_close_done = False
        return False

    def reset_force_close(self):
        self._force_close_done = False

    def get_window_label(self, dt=None):
        return {WINDOW_TESTNET: '🧪 测试网模式', WINDOW_TRADING: '🟢 交易窗口',
                WINDOW_CLOSE_ONLY: '🟡 只平仓模式'}.get(self.get_window(dt), '❓')

    def next_status_change(self, dt=None):
        """返回下次窗口切换时间和类型，用于 GUI 倒计时"""
        # 按时间顺序检查 [Sat 08:00→trading, Sun 18:00→close_only, Mon 12:00→testnet]
        pass  # 详见源码
```

**关键逻辑**：
- 整个周期设计理念：周中模拟观察（testnet）→ 周末真实交易（trading）→ 周一切换前强制平仓（close_only）

---

### 6.7 auto_trader/exchange.py — 交易所抽象层

```python
"""
交易所抽象层 — Binance Futures + OKX Perpetual Swap
统一接口：逐仓模式 + 市价单 + 10x 杠杆
"""
import json, logging, os, time
from abc import ABC, abstractmethod
from dataclasses import dataclass
import ccxt
from paths import get_config_dir

logger = logging.getLogger(__name__)
SETTINGS_FILE = os.path.join(get_config_dir(), 'settings.json')

def _load_proxy():
    """从 settings.json 读取代理配置"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                s = json.load(f)
            proxy = s.get('proxy', {})
            if proxy.get('enabled') and proxy.get('http'):
                return {'http': proxy['http'], 'https': proxy.get('https') or proxy['http']}
    except Exception:
        pass
    return None

@dataclass
class OrderResult:
    success: bool; exchange: str; order_id: str | None
    side: str; amount: float; price: float; cost: float; error: str | None

@dataclass
class PositionInfo:
    symbol: str; side: str; contracts: float; entry_price: float
    mark_price: float; unrealized_pnl: float; pnl_pct: float
    collateral: float; leverage: int; liq_price: float

class ExchangeBase(ABC):
    """交易所基类"""
    def __init__(self, name, default_type):
        self.name = name
        self._default_type = default_type
        self._exchange = None
        self._connected = False
        self._testnet = False

    @property
    def is_connected(self):
        return self._connected

    def connect(self, api_key, secret, passphrase=None, testnet=False):
        self._testnet = testnet
        self._exchange = self._create_exchange(api_key, secret, passphrase, testnet)
        try:
            self._exchange.load_markets()
            self._connected = True
            logger.info(f"[{self.name}] {'测试网' if testnet else '实盘'} 连接成功")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] 连接失败: {e}")
            self._connected = False
            return False

    @abstractmethod
    def _create_exchange(self, api_key, secret, passphrase, testnet):
        pass

    def _symbol(self, raw_symbol):
        """BTCUSDT → BTC/USDT:USDT"""
        if '/' in raw_symbol:
            return raw_symbol
        return f"{raw_symbol[:-4]}/USDT:USDT" if raw_symbol.endswith('USDT') else f"{raw_symbol}/USDT:USDT"

    def set_isolated_margin(self, symbol, leverage=10):
        if not self._connected:
            return False
        try:
            self._set_margin_mode_impl(self._symbol(symbol), leverage)
            return True
        except Exception as e:
            logger.error(f"[{self.name}] 设置失败: {e}")
            return False

    @abstractmethod
    def _set_margin_mode_impl(self, symbol, leverage):
        pass

    def open_position(self, symbol, side, usdt_amount, leverage=10):
        """开仓/加仓 — 市价单，保证金 * 杠杆 = 名义价值"""
        if not self._connected:
            return OrderResult(False, self.name, None, side, 0, 0, 0, '未连接')
        s = self._symbol(symbol)
        try:
            self.set_isolated_margin(symbol, leverage)
            ticker = self._exchange.fetch_ticker(s)
            price = ticker.get('last')
            if not price or price <= 0:
                return OrderResult(False, self.name, None, side, 0, 0, 0, '价格获取失败')
            notional = usdt_amount * leverage
            raw_amount = notional / price
            amount_str = self._exchange.amount_to_precision(s, raw_amount)
            order = self._create_market_order(s, side, amount_str)
            return OrderResult(True, self.name, order.get('id', ''), side,
                              order.get('filled', float(amount_str)),
                              order.get('average', price) or price,
                              order.get('cost', notional) or notional, None)
        except Exception as e:
            return OrderResult(False, self.name, None, side, 0, 0, 0, str(e)[:100])

    @abstractmethod
    def _create_market_order(self, symbol, side, amount_str):
        pass

    def close_position(self, symbol, position_side):
        """平仓 — 反向市价单"""
        close_side = 'sell' if position_side == 'long' else 'buy'
        s = self._symbol(symbol)
        try:
            positions = self._exchange.fetch_positions([s])
            target = None
            for p in positions:
                if p.get('symbol') == s and p.get('side') == position_side:
                    target = p
                    break
            if not target or abs(target.get('contracts', 0)) < 1e-8:
                return OrderResult(True, self.name, None, close_side, 0, 0, 0, None)
            amount = abs(target['contracts'])
            amount_str = self._exchange.amount_to_precision(s, amount)
            order = self._close_market_order(s, close_side, amount_str)
            return OrderResult(True, self.name, order.get('id', ''), close_side,
                              order.get('filled', amount), order.get('average', 0) or 0,
                              order.get('cost', 0) or 0, None)
        except Exception as e:
            return OrderResult(False, self.name, None, close_side, 0, 0, 0, str(e)[:100])

    @abstractmethod
    def _close_market_order(self, symbol, close_side, amount_str):
        pass

    def fetch_position(self, symbol):
        if not self._connected:
            return None
        s = self._symbol(symbol)
        try:
            positions = self._exchange.fetch_positions([s])
            for p in positions:
                if p.get('symbol') == s and abs(p.get('contracts', 0)) > 1e-8:
                    return PositionInfo(
                        symbol=symbol, side=p.get('side', 'none'),
                        contracts=p.get('contracts', 0), entry_price=p.get('entryPrice', 0) or 0,
                        mark_price=p.get('markPrice', 0) or 0, unrealized_pnl=p.get('unrealizedPnl', 0) or 0,
                        pnl_pct=p.get('percentage', 0) or 0,
                        collateral=p.get('collateral', 0) or p.get('initialMargin', 0) or 0,
                        leverage=p.get('leverage', 0) or 0, liq_price=p.get('liquidationPrice', 0) or 0)
            return None
        except Exception as e:
            logger.error(f"查询持仓失败 {symbol}: {e}")
            return None

    def fetch_all_positions(self):
        if not self._connected:
            return []
        try:
            raw = self._exchange.fetch_positions()
            result = []
            for p in raw:
                if abs(p.get('contracts', 0)) < 1e-8:
                    continue
                sym = p.get('symbol', '')
                raw_sym = sym.split('/')[0] + 'USDT' if '/USDT' in sym else sym
                result.append(PositionInfo(
                    symbol=raw_sym, side=p.get('side', 'none'),
                    contracts=p.get('contracts', 0), entry_price=p.get('entryPrice', 0) or 0,
                    mark_price=p.get('markPrice', 0) or 0, unrealized_pnl=p.get('unrealizedPnl', 0) or 0,
                    pnl_pct=p.get('percentage', 0) or 0,
                    collateral=p.get('collateral', 0) or p.get('initialMargin', 0) or 0,
                    leverage=p.get('leverage', 0) or 0, liq_price=p.get('liquidationPrice', 0) or 0))
            return result
        except Exception as e:
            logger.error(f"查询全部持仓失败: {e}")
            return []

    def fetch_balance(self):
        if not self._connected:
            return 0.0
        try:
            bal = self._exchange.fetch_balance()
            return float(bal.get('free', {}).get('USDT', 0) or 0)
        except Exception as e:
            logger.error(f"余额查询失败: {e}")
            return 0.0

    @staticmethod
    def test_connection(api_key, secret, create_exchange_cb, passphrase=None, testnet=False):
        """独立测试连接，返回 {success, balance, futures_ok, error}"""
        result = {'success': False, 'balance': 0.0, 'futures_ok': False, 'error': ''}
        if not api_key or not secret:
            result['error'] = '请填写 API Key 和 Secret'
            return result
        try:
            exchange = create_exchange_cb(api_key, secret, passphrase, testnet)
        except Exception as e:
            result['error'] = f'创建实例失败: {str(e)[:180]}'
            return result
        try:
            exchange.load_markets()
        except Exception:
            pass
        try:
            bal = exchange.fetch_balance()
            result['balance'] = float(bal.get('free', {}).get('USDT', 0) or 0)
            result['futures_ok'] = True
            result['success'] = True
        except Exception as e:
            msg = str(e)
            if 'Api-Key' in msg or 'signature' in msg.lower():
                result['error'] = 'API Key 无效'
            elif 'Permission' in msg or '403' in msg:
                result['error'] = '权限不足，请确认已开通合约交易'
            elif 'timed out' in msg.lower():
                result['error'] = '网络超时，请检查代理设置'
            else:
                result['error'] = f'余额查询失败: {msg[:180]}'
        return result

# === Binance Futures ===
class BinanceFutures(ExchangeBase):
    def __init__(self):
        super().__init__('Binance', 'future')

    def _create_exchange(self, api_key, secret, passphrase, testnet):
        kwargs = {'apiKey': api_key, 'secret': secret, 'enableRateLimit': True,
                  'options': {'defaultType': 'future'}, 'timeout': 15000}
        proxy = _load_proxy()
        if proxy:
            kwargs['proxies'] = proxy
        exchange = ccxt.binance(kwargs)
        if testnet:
            # ccxt 4.x 合约测试网：需要合并 live + test URLs
            live_api = exchange.urls['api'].copy()
            exchange.set_sandbox_mode(True)
            test_urls = exchange.urls.get('test', {}).copy()
            exchange.set_sandbox_mode(False)
            exchange.urls['api'] = {**live_api, **test_urls}
        return exchange

    def _set_margin_mode_impl(self, symbol, leverage):
        self._exchange.set_margin_mode('isolated', symbol)
        self._exchange.set_leverage(leverage, symbol)

    def _create_market_order(self, symbol, side, amount_str):
        return self._exchange.create_order(symbol, 'market', side, float(amount_str))

    def _close_market_order(self, symbol, close_side, amount_str):
        return self._exchange.create_order(symbol, 'market', close_side, float(amount_str),
                                           params={'reduceOnly': True})

# === OKX Perpetual Swap ===
class OkxSwap(ExchangeBase):
    def __init__(self):
        super().__init__('OKX', 'swap')

    def _create_exchange(self, api_key, secret, passphrase, testnet):
        kwargs = {'apiKey': api_key, 'secret': secret, 'password': passphrase or '',
                  'enableRateLimit': True, 'timeout': 15000}
        proxy = _load_proxy()
        if proxy:
            kwargs['proxies'] = proxy
        exchange = ccxt.okx(kwargs)
        if testnet:
            exchange.set_sandbox_mode(True)
        return exchange

    def _set_margin_mode_impl(self, symbol, leverage):
        self._exchange.set_position_mode(False)
        self._exchange.set_leverage(leverage, symbol, params={'mgnMode': 'isolated', 'posSide': 'net'})

    def _create_market_order(self, symbol, side, amount_str):
        return self._exchange.create_order(symbol, 'market', side, float(amount_str),
                                           params={'tdMode': 'isolated'})

    def _close_market_order(self, symbol, close_side, amount_str):
        return self._exchange.create_order(symbol, 'market', close_side, float(amount_str),
                                           params={'tdMode': 'isolated', 'reduceOnly': True})
```

**关键逻辑**：
- Binance testnet: ccxt 4.x 的 sandbox mode 缺少部分 REST 端点 → 需要用 live URLs 为底，test URLs 覆盖
- 开仓: `保证金 × 杠杆 / 价格 = 合约数量`，市价单
- 平仓: 查持仓 → 反向市价单 + `reduceOnly=True`

---

### 6.8 auto_trader/trade_engine.py — 交易引擎

```python
"""
交易引擎 — QThread 主循环
调度链：TradingScheduler → StrategyEngine → Exchange
"""
import os, json, time, logging, datetime, threading
from PyQt5.QtCore import QThread, pyqtSignal
from auto_trader.scheduler import TradingScheduler, WINDOW_TRADING, WINDOW_CLOSE_ONLY, WINDOW_TESTNET
from auto_trader.strategy import StrategyEngine, TradeAction, ActionType, Status, PairState, PairOverrides
from auto_trader.exchange import BinanceFutures, OkxSwap, OrderResult, PositionInfo
from paths import get_config_dir

logger = logging.getLogger(__name__)
APP_DIR = get_config_dir()
TRADE_CONFIG_FILE = os.path.join(APP_DIR, 'auto_trader_config.json')
TRADE_LOG_FILE = os.path.join(APP_DIR, 'trade_log.json')

def _load_trade_config():
    """加载交易配置（含默认值）"""
    defaults = {
        'mode': 'testnet', 'trading_pairs': {},
        'binance': {'enabled': True, 'live_api_key': '', 'live_secret': '', 'testnet_api_key': '', 'testnet_secret': ''},
        'okx': {'enabled': False, 'live_api_key': '', 'live_secret': '', 'live_passphrase': '', 'testnet_api_key': '', 'testnet_secret': '', 'testnet_passphrase': ''},
        'leverage': 10, 'base_margin': 100, 'take_profit_pct': 5.0, 'poll_interval': 10,
    }
    try:
        if os.path.exists(TRADE_CONFIG_FILE):
            with open(TRADE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                for k, v in loaded.items():
                    if k in defaults and isinstance(defaults[k], dict) and isinstance(v, dict):
                        defaults[k].update(v)
                    else:
                        defaults[k] = v
    except Exception as e:
        logger.warning(f"交易配置加载失败: {e}")
    return defaults

def save_trade_config(config):
    with open(TRADE_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

class TradeEngine(QThread):
    status_updated = pyqtSignal(list)     # 持仓快照列表
    trade_executed = pyqtSignal(dict)     # 交易通知
    emergency_alert = pyqtSignal(str, str) # (title, body)
    log_message = pyqtSignal(str)

    def __init__(self, fetcher, notifier, pairs_callback, parent=None):
        super().__init__(parent)
        self.fetcher = fetcher
        self.notifier = notifier
        self.pairs_callback = pairs_callback
        self.config = _load_trade_config()
        self.scheduler = TradingScheduler()
        self.strategy = StrategyEngine(base_margin=self.config.get('base_margin', 100))
        self._pair_overrides: dict[str, PairOverrides] = {}
        self._load_pair_overrides()
        self.binance = BinanceFutures()
        self.okx = OkxSwap()
        self._running = True
        self._paused = True
        self._mode = self.config.get('mode', 'testnet')
        self._poll_interval = self.config.get('poll_interval', 10)

    def set_mode(self, mode):
        """切换 testnet/live"""
        if mode not in ('testnet', 'live'):
            return
        self._mode = mode
        self.config['mode'] = mode
        save_trade_config(self.config)
        self._connect_exchanges()

    def pause(self): self._paused = True
    def resume(self): self._paused = False
    def stop(self): self._running = False

    def _load_pair_overrides(self):
        raw = self.config.get('pair_overrides', {})
        self._pair_overrides = {}
        if not isinstance(raw, dict):
            return
        for key, val in raw.items():
            if not isinstance(val, dict):
                continue
            self._pair_overrides[key] = PairOverrides(
                base_margin=val.get('base_margin'),
                normal_thresholds=val.get('normal_thresholds'),
                margin_multipliers=val.get('margin_multipliers'))

    def reload_config(self):
        self.config = _load_trade_config()
        self._poll_interval = self.config.get('poll_interval', 10)
        self.strategy.base_margin = self.config.get('base_margin', 100)
        self._load_pair_overrides()
        self._connect_exchanges()

    def get_active_exchanges(self):
        result = []
        if self.binance.is_connected: result.append('binance')
        if self.okx.is_connected: result.append('okx')
        return result

    def run(self):
        """主循环：对每个交易所+标的组合调用 _process_pair"""
        self._connect_exchanges()
        while self._running:
            if self._paused:
                time.sleep(1)
                continue
            now = datetime.datetime.now()
            window = self.scheduler.get_window(now)
            can_open = self.scheduler.can_open_new(now)
            should_force = self.scheduler.should_force_close(now)

            trading_pairs = self.config.get('trading_pairs', {})
            if isinstance(trading_pairs, list):
                trading_pairs = {'binance': list(trading_pairs), 'okx': list(trading_pairs)}
            if not trading_pairs:
                all_keys = [f"{p[0]}:{p[1]}" for p in self.pairs_callback()]
                trading_pairs = {'binance': list(all_keys), 'okx': list(all_keys)}

            all_pairs_map = {f"{p[0]}:{p[1]}": (p[0], p[1], p[2] if len(p)>2 else 0.5) for p in self.pairs_callback()}

            snapshots = []
            seen_keys = set()
            for ex_name in ['binance', 'okx']:
                for key in trading_pairs.get(ex_name, []):
                    if key not in all_pairs_map:
                        continue
                    stock, crypto, threshold = all_pairs_map[key]
                    try:
                        snapshot = self._process_pair(stock, crypto, threshold, now, can_open, should_force, window, target_exchange=ex_name)
                        if key not in seen_keys:
                            snapshots.append(snapshot)
                            seen_keys.add(key)
                    except Exception as e:
                        logger.error(f"处理 {stock}:{crypto} 异常: {e}")

            self.status_updated.emit(snapshots)
            if should_force:
                self.scheduler.reset_force_close()
            # sleep...
```

**`_process_pair` 核心逻辑**：
```python
def _process_pair(self, stock, crypto, threshold, now, can_open, should_force, window, target_exchange=None):
    key = f"{stock}:{crypto}"
    us_price = self.fetcher.get_us_stock_price(stock)
    crypto_price = self.fetcher.get_binance_price(crypto)
    diff = round((crypto_price - us_price) / us_price * 100, 2) if us_price and crypto_price else 0
    overrides = self._pair_overrides.get(key)  # None = 使用全局默认
    action = self.strategy.evaluate(stock, crypto, diff, us_price or 0, crypto_price or 0, now, can_open and window==WINDOW_TRADING, should_force, overrides=overrides)
    if action:
        self._execute_action(action, crypto_price or 0, crypto, target_exchange)
    if window in (WINDOW_TRADING, WINDOW_CLOSE_ONLY):
        self._check_real_pnl(stock, crypto, now, target_exchange)
    state = self.strategy.get_state(stock, crypto)
    return self._build_snapshot(state, us_price, crypto_price, diff, window)
```

**开仓路由**：
```python
def _open_on_exchanges(self, crypto, side, total_margin, target_exchange=None):
    """
    target_exchange='binance' → 100% 在币安
    target_exchange='okx' → 100% 在 OKX
    target_exchange=None → 50/50 双交易所分摊
    """
```

**止盈检查**：
```python
def _check_real_pnl(self, stock, crypto, now, target_exchange=None):
    """从交易所查 unrealized_pnl / total_margin >= 5% → 止盈平仓"""
```

---

### 6.9 main.py — 主入口

```python
"""
启动 PyQt5 GUI 应用，初始化日志、配置、系统托盘
"""
import sys, os, logging, datetime, json
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from paths import get_config_dir, migrate_old_configs
from gui_app import MainWindow

APP_DIR = get_config_dir()
migrate_old_configs(APP_DIR)

def setup_logging():
    """日志输出到 app.log（pythonw 无控制台则只写文件）"""
    log_file = os.path.join(APP_DIR, 'app.log')
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', handlers=handlers)
    logging.getLogger('yfinance').setLevel(logging.WARNING)
    logging.getLogger('ccxt').setLevel(logging.WARNING)

def ensure_configs():
    """首次运行自动创建 config.json + settings.json"""
    # 详见源码：创建带默认值的 json 文件

def main():
    setup_logging()
    ensure_configs()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    window = MainWindow()
    # 根据 start_minimized 设置决定是否隐藏到托盘
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
```

---

### 6.10 gui_app.py — GUI 主界面（~1900行）

**结构概览**：

```
STYLESHEET (深色主题 CSS)
├── SettingsDialog — 设置对话框
│   ├── email/QQ/desktop/sound 通知配置
│   ├── proxy 代理配置
│   ├── poll_interval/cooldown/minimize 监控配置
│   └── quiet_hours 静默时段（7天勾选 + 起止时间QTimeEdit）
├── AddPairDialog — 添加监控标的
├── PairOverrideDialog — 单个标的的自定义阶梯参数编辑
│   ├── 启用开关 + base_margin SpinBox
│   ├── 4级 Normal 阈值 QDoubleSpinBox + 4级 保证金倍数
│   ├── 实时预览 "Lv1: 0.5% → 100U | ...  最大占用: 900U"
│   └── 重置为全局默认按钮
├── MainWindow(QMainWindow)
│   ├── QTabWidget (3个标签页)
│   │   ├── Tab 0: 价差监控
│   │   │   ├── QTableView (PriceTableModel: stock/crypto/us_price/binance_price/diff/threshold/status/time)
│   │   │   ├── 控制栏: 启动/暂停/添加/删除/导出告警/设置/代理状态
│   │   │   └── 日志区 QTextEdit
│   │   ├── Tab 1: 交易标的 & 策略
│   │   │   ├── QSplitter 左右分栏
│   │   │   │   ├── 左: 币安标的 QListWidget (勾选启用, 右键自定义策略, ⚙标记)
│   │   │   │   └── 右: OKX标的 QListWidget (同上)
│   │   │   ├── 底部: Global Base Margin SpinBox + Hint Label (按per-pair计算的最大占用)
│   │   │   └── 控制: 保存按钮 → _save_trading_pairs()
│   │   └── Tab 2: 自动交易
│   │       ├── 模式选择: testnet/live ComboBox + 窗口状态标签
│   │       ├── API Key 配置: Binance + OKX (live + testnet 各一套)
│   │       ├── 连接测试按钮 (test_connection API)
│   │       ├── 余额显示 QLabel
│   │       ├── 交易参数: leverage/base_margin/take_profit/poll_interval
│   │       ├── 启动/暂停/紧急平仓按钮
│   │       ├── 持仓表格 + 交易日志
│   │       └── 每个交易所标的分配 (勾选哪些在哪个交易所交易)
│   ├── QSystemTrayIcon (托盘图标 + 右键菜单)
│   └── MonitorThread 集成 (后台轮询, 信号驱动UI更新)
```

**关键 GUI 交互**：

1. **标的右键菜单** → `_on_pair_context_menu(pos, exchange)`:
   - "⚙ 编辑自定义阶梯/保证金..." → `_open_pair_override_dialog(key)` → `PairOverrideDialog`
   - "↩ 重置为全局默认" → `_reset_pair_override(key)` → 删除 config 中 overrides

2. **保存后刷新** → `_refresh_pair_lists()`:
   - 使用 `_pair_display_info(key)` 读取 per-pair 的 base_margin/阈值/最大占用
   - 有自定义参数的标的显示 `⚙ 阈值:0.3% 最大:525U [0.3/0.8/1.5%]` 金色字体
   - Hint 标签通过 `_calc_total_max(enabled_set)` 按 per-pair 实际值累加

3. **API Key 保存后** → `_fetch_and_display_balances()` 主动查询余额

4. **设置对话框 accept 后** → `monitor.reload_notifier()` + `monitor.set_interval()` + `fetcher.reload_proxy()`

---

### 6.11 web_server.py — Flask Web 服务器

独立的 Web 入口（`python web_server.py`），与桌面端共享：
- MonitorThread (同一套监控逻辑)
- config.json / settings.json
- REST API:
  - `GET /api/status` — 监控数据
  - `GET/POST /api/pairs` — 标的增删
  - `GET/POST /api/settings` — 设置读写
  - `GET /api/alerts` — 告警历史
  - `POST /api/monitor/pause` — 暂停/恢复
  - `GET /api/trader/status` — 交易引擎状态
  - `POST /api/trader/emergency_close` — 紧急平仓
- 模板 `templates/index.html` — 响应式移动端 Web UI

---

### 6.12 auto_trader/__init__.py

```python
"""
自动合约套利交易模块
基于美股-币安价差的均值回归，使用 10x 永续合约进行阶梯加仓交易
"""
```

---

## 七、关键数据流总结

### 监控告警流程：
```
MonitorThread.run()
  → PriceFetcher.get_us_stock_price() + get_binance_price()
  → 价差 = (币安 - 美股) / 美股 * 100%
  → 超过阈值 → _check_ladder()
    → 阶梯确认(2次) + 台阶判断(0.5%粒度)
    → _is_quiet_hours() 检查静默时段
    → Notifier.send_alert() 多渠道通知
    → _log_alert() 写入 alert_log.json
  → data_updated 信号 → GUI 表格更新
```

### 交易执行流程：
```
TradeEngine.run()
  → TradingScheduler.get_window() 判断窗口
  → for each exchange in [binance, okx]:
      for each pair assigned to that exchange:
        → PriceFetcher 取价 → 计算价差
        → StrategyEngine.evaluate(overrides)
          → resolve_levels(overrides) 获取该标的的阶梯参数
          → 状态机判断: 开仓? 加仓? 止盈? 反转? 紧急?
        → 执行动作:
          Exchange.open_position(margin, leverage) / close_position()
        → _check_real_pnl() 查 unrealized_pnl → 止盈
  → status_updated 信号 → GUI 持仓表格更新
```

### 配置热重载：
```
用户修改设置 → save → reload_config()
  → _load_trade_config()  (重读 JSON)
  → _load_pair_overrides() (重建 overrides 字典)
  → strategy.base_margin = ...
  → _connect_exchanges()   (重连交易所)
```

---

## 八、开发 & 部署

```bash
# 安装依赖
pip install -r requirements.txt

# 启动桌面 GUI
python main.py

# 启动 Web 服务
python web_server.py

# 打包为 exe（需要 PyInstaller）
pyinstaller --onedir --name CryptoArbitrage --add-data "templates;templates" \
  --hidden-import ccxt.binance --hidden-import ccxt.okx --noconsole main.py
```

---

## 九、设计原则

1. **价差方向**: 负值（币安折价/低于美股）→ long；正值（币安溢价/高于美股）→ short
2. **保守定价**: 美股取收盘价和盘后价中较低者，避免虚高锚定
3. **阶梯策略**: 价差越大，加仓保证金越多（base_margin × 倍数），摊薄成本
4. **防瞬时波动**: 需要连续 2 次轮询确认才触发告警/交易
5. **时间窗口隔离**: 周中模拟(testnet) + 周末实战(trading) + 周一切换前强制平仓(close_only)
6. **Per-pair 自定义**: 每个标的三层参数覆盖（pair_overrides → 全局 default）
7. **配置热重载**: 所有设置修改即时生效，无需重启
8. **多渠道通知**: 邮件/QQ/桌面/声音并行，用户可选
