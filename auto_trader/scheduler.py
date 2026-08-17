"""
时间窗口管理器
北京时间（UTC+8）为基准，控制交易窗口：
  - 周一 12:00 → 周六 08:00  : testnet（测试网模式）
  - 周六 08:00 → 周日 18:00  : trading（可开仓+平仓）
  - 周日 18:00 → 周一 12:00  : close_only（只平仓不开仓）
"""

import datetime

BEIJING = datetime.timezone(datetime.timedelta(hours=8))

WINDOW_TESTNET = 'testnet'
WINDOW_TRADING = 'trading'
WINDOW_CLOSE_ONLY = 'close_only'


class TradingScheduler:
    """交易时间窗口管理器"""

    def __init__(self):
        self._last_window = None
        self._force_close_done = False  # 本周强制平仓是否已执行

    def get_window(self, dt=None):
        """
        返回当前窗口状态
        返回: 'testnet' | 'trading' | 'close_only'
        """
        if dt is None:
            dt = datetime.datetime.now(BEIJING)

        weekday = dt.weekday()  # 0=Mon, 1=Tue, ..., 5=Sat, 6=Sun
        hour = dt.hour

        if weekday == 5:  # Saturday
            if hour >= 8:
                return WINDOW_TRADING
            else:
                return WINDOW_TESTNET
        elif weekday == 6:  # Sunday
            if hour < 18:
                return WINDOW_TRADING
            else:
                return WINDOW_CLOSE_ONLY
        elif weekday == 0:  # Monday
            if hour < 12:
                return WINDOW_CLOSE_ONLY
            else:
                return WINDOW_TESTNET
        else:  # Tuesday → Friday
            return WINDOW_TESTNET

    def can_open_new(self, dt=None):
        """是否可以开新仓（trading 窗口）"""
        return self.get_window(dt) == WINDOW_TRADING

    def can_manage_positions(self, dt=None):
        """是否可以管理持仓（trading 或 close_only 窗口）"""
        window = self.get_window(dt)
        return window in (WINDOW_TRADING, WINDOW_CLOSE_ONLY)

    def should_force_close(self, dt=None):
        """
        检查是否到达强制平仓时间点（周一 12:00）
        使用一次性标志防止每轮循环重复触发
        """
        if dt is None:
            dt = datetime.datetime.now(BEIJING)

        if dt.weekday() == 0 and dt.hour >= 12:
            if not self._force_close_done:
                self._force_close_done = True
                return True
        else:
            # 非周一 12:00 时段，重置标志
            self._force_close_done = False
        return False

    def is_testnet(self, dt=None):
        """当前是否为测试网模式"""
        return self.get_window(dt) == WINDOW_TESTNET

    def next_status_change(self, dt=None):
        """
        返回下一次窗口切换的时间和类型
        用于 GUI 显示倒计时
        """
        if dt is None:
            dt = datetime.datetime.now(BEIJING)

        current = self.get_window(dt)
        weekday = dt.weekday()
        hour = dt.hour

        # 按时间顺序检查下一个切换点
        transitions = [
            # (day_of_week, hour, minute, next_window)
            # 周六 08:00 testnet → trading
            (5, 8, 0, WINDOW_TRADING),
            # 周日 18:00 trading → close_only
            (6, 18, 0, WINDOW_CLOSE_ONLY),
            # 周一 12:00 close_only → testnet
            (0, 12, 0, WINDOW_TESTNET),
        ]

        for target_day, target_hour, target_minute, next_window in transitions:
            candidate = dt.replace(
                hour=target_hour, minute=target_minute, second=0, microsecond=0
            )
            # 调整到目标星期几
            days_ahead = target_day - weekday
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0 and (hour >= target_hour):
                days_ahead = 7
            candidate += datetime.timedelta(days=days_ahead)

            # 排除当前窗口自身
            candidate_window = self.get_window(candidate)
            if candidate_window != current:
                return candidate, candidate_window

        # Fallback
        return dt + datetime.timedelta(days=1), current

    def get_window_label(self, dt=None):
        """返回窗口的中文标签"""
        window = self.get_window(dt)
        labels = {
            WINDOW_TESTNET: '🧪 测试网模式',
            WINDOW_TRADING: '🟢 交易窗口',
            WINDOW_CLOSE_ONLY: '🟡 只平仓模式',
        }
        return labels.get(window, '❓ 未知')

    def reset_force_close(self):
        """重置强制平仓标志（用于手动触发后重置）"""
        self._force_close_done = False


# ── 独立测试 ──
if __name__ == '__main__':
    scheduler = TradingScheduler()
    now = datetime.datetime.now(BEIJING)
    print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M')} BJT")
    print(f"当前窗口: {scheduler.get_window_label()}")
    print(f"可开新仓: {scheduler.can_open_new()}")
    print(f"可管理持仓: {scheduler.can_manage_positions()}")
    print(f"需强制平仓: {scheduler.should_force_close()}")

    next_time, next_window = scheduler.next_status_change()
    print(f"下次切换: {next_time.strftime('%Y-%m-%d %H:%M')} → {next_window}")

    # 打印一周内的窗口切换
    print("\n未来一周切换表:")
    for i in range(10):
        t = now + datetime.timedelta(hours=i * 6)
        print(f"  {t.strftime('%m/%d %H:%M')} → {scheduler.get_window_label(t)}")
