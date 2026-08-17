"""
监控引擎
后台线程定时轮询价格，计算价差，触发告警
"""

import time
import threading
import logging
import os
import json
import datetime

from PyQt5.QtCore import QThread, pyqtSignal

from data_fetcher import PriceFetcher
from notifier import Notifier
from paths import get_config_dir

logger = logging.getLogger(__name__)

CONFIG_DIR = get_config_dir()
ALERT_LOG_FILE = os.path.join(CONFIG_DIR, 'alert_log.json')


class MonitorThread(QThread):
    """后台监控线程"""
    # 信号：将更新后的数据发往 GUI
    data_updated = pyqtSignal(list)
    # 信号：告警日志
    alert_triggered = pyqtSignal(dict)

    # 静默时段由用户在 settings.json 中自行配置（quiet_hours 字段）

    def __init__(self, pairs_callback, parent=None):
        """
        pairs_callback: 可调用对象，返回最新的标的列表 [(stock, crypto, threshold), ...]
                       这样就不需要共享可变对象，避免线程安全问题
        """
        super().__init__(parent)
        self.pairs_callback = pairs_callback
        self.fetcher = PriceFetcher()
        self.notifier = Notifier()
        self._running = True
        self._paused = False
        self._poll_interval = 30  # 默认轮询间隔（秒）
        # 阶梯告警：{alert_key: (last_alerted_level, confirm_count, direction)}
        # level = int(abs(diff) / 0.5) * 0.5，只有跨过新的 0.5% 阶梯才重新告警
        self._alert_state = {}

    def set_interval(self, seconds):
        """设置轮询间隔"""
        self._poll_interval = max(5, min(300, seconds))

    def pause(self):
        self._paused = True
        logger.info("监控已暂停")

    def resume(self):
        self._paused = False
        logger.info("监控已恢复")

    def stop(self):
        self._running = False
        logger.info("监控线程正在停止...")

    def reload_notifier(self):
        """重新加载通知器设置"""
        self.notifier.reload_settings()

    def run(self):
        logger.info(f"监控线程启动，轮询间隔 {self._poll_interval}s")

        while self._running:
            try:
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

                # 使用可中断的 sleep（每秒检查一次状态）
                elapsed = 0
                while elapsed < self._poll_interval and self._running:
                    if not self._paused:
                        time.sleep(1)
                        elapsed += 1
                    else:
                        time.sleep(1)

            except Exception as e:
                logger.error(f"监控循环异常: {e}", exc_info=True)
                time.sleep(10)

        logger.info("监控线程已退出")

    def _is_quiet_hours(self, now=None):
        """
        判断当前是否在用户设置的静默时段内。
        settings.json quiet_hours:
          - enabled: 是否启用静默
          - days: 生效的星期 [0=Mon ... 6=Sun]
          - start: "HH:MM" 起始时间
          - end: "HH:MM" 结束时间

        返回 True = 静默（不推送），False = 可以推送。
        """
        qh = self.notifier.settings.get('quiet_hours', {})
        if not qh.get('enabled'):
            return False

        if now is None:
            now = datetime.datetime.now()
        weekday = now.weekday()  # 0=Mon ... 6=Sun
        days = qh.get('days', [0, 1, 2, 3, 4])
        if weekday not in days:
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
            # 同一天内：start ≤ now < end
            return start_minutes <= now_minutes < end_minutes
        else:
            # 跨天：now ≥ start 或 now < end（如 22:00→06:00 覆盖夜间）
            return now_minutes >= start_minutes or now_minutes < end_minutes

    def _calc_level(self, diff_percent):
        """计算当前价差所在的阶梯级别（0.5% 为一阶梯）"""
        return int(abs(diff_percent) * 2) / 2  # 0.72→0.5, 1.23→1.0, 2.56→2.5

    def _check_pair(self, stock, crypto, threshold, timestamp):
        """检查单个交易对"""
        alert_key = f"{stock}:{crypto}"

        # 获取价格
        us_price = self.fetcher.get_us_stock_price(stock)
        binance_price = self.fetcher.get_binance_price(crypto)

        if us_price is None or binance_price is None:
            status = "数据异常"
            diff_str = "N/A"
            diff_percent = 0
            self._alert_state.pop(alert_key, None)
        else:
            # 计算价差：(币安 - 美股) / 美股 * 100
            diff_percent = round((binance_price - us_price) / us_price * 100, 2)
            diff_str = f"{diff_percent:+.2f}%"
            status = self._evaluate_status(
                stock, crypto, us_price, binance_price,
                diff_percent, threshold, alert_key, timestamp
            )

        return [stock, crypto, str(us_price) if us_price else "N/A",
                str(binance_price) if binance_price else "N/A",
                diff_str, str(threshold), status,
                timestamp.strftime("%H:%M:%S")]

    def _evaluate_status(self, stock, crypto, us_price, binance_price,
                         diff_percent, threshold, alert_key, timestamp):
        """评估状态并触发告警（阶梯式：每 0.5% 一个台阶，跨过新台阶才告警）"""
        if diff_percent <= -threshold:
            # 币安折价 → 买入信号
            return self._check_ladder(
                stock, crypto, us_price, binance_price,
                diff_percent, threshold, alert_key, timestamp,
                direction='buy'
            )

        elif diff_percent >= threshold:
            # 币安溢价 → 卖出信号
            return self._check_ladder(
                stock, crypto, us_price, binance_price,
                diff_percent, threshold, alert_key, timestamp,
                direction='sell'
            )

        else:
            # 正常范围，清除状态（价差回到阈值内则完全重置）
            self._alert_state.pop(alert_key, None)
            return f"正常 ({diff_percent:+.2f}%)"

    def _check_ladder(self, stock, crypto, us_price, binance_price,
                       diff_percent, threshold, alert_key, timestamp,
                       direction):
        """阶梯告警核心逻辑"""
        current_level = self._calc_level(diff_percent)
        # 状态: (last_alerted_level, confirm_count, direction)
        prev_state = self._alert_state.get(alert_key)

        # 解析/初始化状态
        if prev_state and prev_state[2] == direction:
            last_level, confirm_count, _ = prev_state
        else:
            # 方向变了（或首次触发），重置
            last_level = 0
            confirm_count = 0

        confirm_count += 1
        self._alert_state[alert_key] = (last_level, confirm_count, direction)

        # ── 需要确认 2 次（防瞬时波动）──
        if confirm_count < 2:
            label = "折价" if direction == 'buy' else "溢价"
            return f"⏳ {label}确认中({current_level:.1f}%)... ({diff_percent:+.2f}%)"

        # ── 阶梯判断：只有跨过新的 0.5% 台阶才告警 ──
        if current_level > last_level:
            # 触发告警──更新已告警级别
            self._alert_state[alert_key] = (current_level, confirm_count, direction)

            if direction == 'buy':
                signal_name = "买入信号"
                signal_icon = "🔴"
                signal_code = 'BUY'
                label = "折价"
            else:
                signal_name = "溢价信号"
                signal_icon = "🟢"
                signal_code = 'SELL'
                label = "溢价"

            msg = (
                f"【{signal_name} · {label}{current_level:.1f}%阶梯】\n"
                f"美股 {stock}: ${us_price}\n"
                f"币安 {crypto}: ${binance_price}\n"
                f"{label}幅度: {diff_percent:+.2f}%\n"
                f"触发阶梯: {current_level:.1f}%\n"
                f"时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # 静默期（美股交易时段）不推送邮件/通知，但 GUI 仍正常显示
            if self._is_quiet_hours(timestamp):
                logger.debug(f"[{alert_key}] 静默时段，跳过推送 (价差{diff_percent:+.2f}%)")
            else:
                self.notifier.send_alert(
                    f"{signal_icon} {stock} → {crypto} {signal_name}({current_level:.1f}%)",
                    msg,
                    alert_key=alert_key
                )
            self._log_alert(stock, crypto, signal_code, us_price, binance_price,
                            diff_percent, timestamp)
            return f"{signal_icon} {signal_name}! [阶梯{current_level:.1f}%] ({diff_percent:+.2f}%)"

        elif current_level == last_level:
            # 同一阶梯──不重复告警
            label = "折价" if direction == 'buy' else "溢价"
            return f"{label}{current_level:.1f}% (监控中) ({diff_percent:+.2f}%)"

        else:
            # current_level < last_level：价差回落但仍在阈值外──保留原级别，不告警
            label = "折价" if direction == 'buy' else "溢价"
            return f"{label}回落中 ←{last_level:.1f}% ({diff_percent:+.2f}%)"

    def _log_alert(self, stock, crypto, direction, us_price, binance_price,
                   diff_percent, timestamp):
        """记录告警到本地 JSON 文件"""
        entry = {
            'time': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'stock': stock,
            'crypto': crypto,
            'direction': direction,
            'us_price': us_price,
            'binance_price': binance_price,
            'diff_percent': round(diff_percent, 2),
        }
        try:
            logs = []
            if os.path.exists(ALERT_LOG_FILE):
                with open(ALERT_LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            logs.append(entry)
            # 只保留最近 500 条
            if len(logs) > 500:
                logs = logs[-500:]
            with open(ALERT_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"告警日志写入失败: {e}")

        # 发射信号给 GUI
        self.alert_triggered.emit(entry)
