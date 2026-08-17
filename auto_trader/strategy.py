"""
策略状态机
管理每个标的的交易状态：开仓、加仓、止盈、反转、紧急告警
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(Enum):
    NONE = 'none'
    OPEN_LONG = 'open_long'         # 开多
    OPEN_SHORT = 'open_short'       # 开空
    ADD_LONG = 'add_long'           # 加多
    ADD_SHORT = 'add_short'         # 加空
    TAKE_PROFIT = 'take_profit'     # 止盈平仓
    FORCE_CLOSE = 'force_close'     # 强制平仓
    EMERGENCY_ALERT = 'emergency'   # >3% 紧急告警


class Status(Enum):
    IDLE = 'idle'              # 无持仓，等待信号
    ACTIVE = 'active'          # 持仓中
    CLOSED = 'closed'          # 已平仓（同窗口不再开仓）
    ALERT_ONLY = 'alert_only'  # >3% 紧急，停止加仓
    REVERSAL = 'reversal'      # 反转模式


@dataclass
class EntryRecord:
    """单次入场记录"""
    time: datetime
    level: float          # 触发价差级别
    direction: str        # 'long' | 'short'
    margin: float         # 保证金 USDT
    price: float          # 成交价格
    exchange: str         # 'binance' | 'okx'


@dataclass
class TradeAction:
    """策略输出的交易动作"""
    action_type: ActionType
    stock: str
    crypto: str
    margin: float = 0          # 保证金金额
    direction: str = ''        # 'long' | 'short'
    level: float = 0           # 触发级别
    diff_percent: float = 0
    emergency_msg: str = ''    # >3% 时的告警信息


@dataclass
class PairState:
    """单个标的的完整状态"""
    stock: str
    crypto: str
    direction: str = ''        # 'long' | 'short' | ''
    status: Status = Status.IDLE
    triggered_levels: set = field(default_factory=set)  # 已触发的价差阶梯
    entries: list = field(default_factory=list)          # EntryRecord[]
    first_open_time: datetime | None = None
    close_time: datetime | None = None
    reversal: bool = False     # 是否为反转模式
    reversal_base_level: float = 0  # 反转基准价差

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
    """单个标的的自定义策略参数。所有字段可选，None 表示使用全局默认"""
    base_margin: float | None = None
    normal_thresholds: list | None = None
    margin_multipliers: list | None = None


class StrategyEngine:
    """
    策略引擎
    对每个标的独立追踪状态，每次轮询调用 evaluate()
    """

    # ── 策略参数 ──
    # 阶梯触发阈值（全局默认，可被 pair_overrides 覆盖）
    DEFAULT_NORMAL_THRESHOLDS = [0.5, 1.0, 2.0, 3.0]
    DEFAULT_REVERSAL_THRESHOLDS = [2.0, 3.0, 4.0, 5.0]
    # 保证金倍数（相对于 base_margin）
    DEFAULT_MARGIN_MULTIPLIERS = [1, 2, 3, 3]

    EMERGENCY_LEVEL = 3.0       # 超过此级别紧急告警
    TAKE_PROFIT_PCT = 5.0       # 止盈比例（保证金%）
    REVERSAL_WINDOW_HOURS = 1   # 反转时间窗口
    REVERSAL_THRESHOLD = 2.0    # 反转触发价差

    def __init__(self, base_margin=100):
        self._states: dict[str, PairState] = {}
        self.leverage = 10
        self.base_margin = base_margin

    @property
    def normal_levels(self):
        """常规阶梯（全局默认，根据 base_margin 动态计算）"""
        return self._compute_levels(
            self.DEFAULT_NORMAL_THRESHOLDS, self.DEFAULT_MARGIN_MULTIPLIERS,
            self.base_margin)

    @property
    def reversal_levels(self):
        """反转阶梯（全局默认，根据 base_margin 动态计算）"""
        return self._compute_levels(
            self.DEFAULT_REVERSAL_THRESHOLDS, self.DEFAULT_MARGIN_MULTIPLIERS,
            self.base_margin)

    @staticmethod
    def _compute_levels(thresholds, multipliers, base_margin):
        """计算 [(触发阈值%, 保证金U), ...] 列表"""
        return [(t, base_margin * m)
                for t, m in zip(thresholds, multipliers)]

    def resolve_levels(self, overrides: PairOverrides | None, is_reversal: bool):
        """
        根据 overrides 解析某个标的的实际阶梯参数。
        返回 [(threshold%, marginU), ...] 列表。
        """
        # 决定用哪个 base_margin
        effective_base = self.base_margin
        if overrides and overrides.base_margin is not None:
            effective_base = overrides.base_margin

        # 决定用哪组阈值
        if overrides and overrides.normal_thresholds and not is_reversal:
            thresholds = overrides.normal_thresholds
        elif is_reversal:
            thresholds = list(self.DEFAULT_REVERSAL_THRESHOLDS)
        else:
            thresholds = list(self.DEFAULT_NORMAL_THRESHOLDS)

        # 决定用哪组倍数
        multipliers = list(self.DEFAULT_MARGIN_MULTIPLIERS)
        if overrides and overrides.margin_multipliers:
            multipliers = overrides.margin_multipliers

        return self._compute_levels(thresholds, multipliers, effective_base)

    def get_state(self, stock, crypto) -> PairState:
        """获取或创建标的状态"""
        key = f"{stock}:{crypto}"
        if key not in self._states:
            self._states[key] = PairState(stock=stock, crypto=crypto)
        return self._states[key]

    def reset_state(self, stock, crypto):
        """重置标的状态（新窗口开始时调用）"""
        key = f"{stock}:{crypto}"
        self._states[key] = PairState(stock=stock, crypto=crypto)

    def reset_all(self):
        """重置所有状态"""
        self._states.clear()

    def _reset_to_idle(self, state):
        """把单个标的状态重置回空闲（平仓后重新捕捉机会用）"""
        state.direction = ''
        state.status = Status.IDLE
        state.triggered_levels = set()
        state.entries = []
        state.first_open_time = None
        state.close_time = None
        state.reversal = False
        state.reversal_base_level = 0

    def evaluate(self, stock, crypto, diff_percent, us_price,
                 crypto_price, now: datetime, can_open: bool,
                 should_force_close: bool,
                 overrides: PairOverrides | None = None) -> TradeAction | None:
        """
        主入口：每次轮询评估一个标的

        参数:
          stock, crypto: 标的
          diff_percent: (币安-美股)/美股*100
          us_price: 美股参考价
          crypto_price: 币安价格
          now: 当前时间
          can_open: 是否允许开新仓
          should_force_close: 是否强制平仓

        返回: TradeAction 或 None
        """
        state = self.get_state(stock, crypto)
        abs_diff = abs(diff_percent)

        # ── 强制平仓 ──
        if should_force_close and state.is_active:
            return TradeAction(
                action_type=ActionType.FORCE_CLOSE,
                stock=stock, crypto=crypto,
                direction=state.direction,
                diff_percent=diff_percent,
            )

        # ── 已平仓 → 检查反转 ──
        if state.status == Status.CLOSED:
            return self._check_reversal(state, stock, crypto, diff_percent,
                                        crypto_price, now, can_open,
                                        overrides=overrides)

        # ── 活跃持仓 → 检查止盈 + 加仓 + 紧急 ──
        if state.is_active:
            # 1. 止盈检查
            tp_action = self._check_take_profit(state, stock, crypto, diff_percent)
            if tp_action:
                return tp_action

            # 2. 紧急告警（>3%）
            if abs_diff > self.EMERGENCY_LEVEL and state.status != Status.ALERT_ONLY:
                state.status = Status.ALERT_ONLY
                return TradeAction(
                    action_type=ActionType.EMERGENCY_ALERT,
                    stock=stock, crypto=crypto,
                    direction=state.direction,
                    level=abs_diff,
                    diff_percent=diff_percent,
                    emergency_msg=(
                        f"⚠️ {stock}-{crypto} 价差超过 {self.EMERGENCY_LEVEL}%!\n"
                        f"当前价差: {diff_percent:+.2f}%\n"
                        f"已加仓: {state.triggered_levels}\n"
                        f"总保证金: {state.total_margin}U\n"
                        f"请检查消息面异动，决定是否手动操作。"
                    ),
                )

            # 3. 加仓检查
            if can_open:
                add_action = self._check_add(state, stock, crypto, diff_percent,
                                             crypto_price, now, overrides=overrides)
                if add_action:
                    return add_action

            return None

        # ── 空闲 → 检查开仓 ──
        if state.status == Status.IDLE and can_open:
            return self._check_entry(state, stock, crypto, diff_percent,
                                     crypto_price, now, overrides=overrides)

        return None

    # ── 开仓检查 ────────────────────────

    def _check_entry(self, state, stock, crypto, diff_percent,
                     crypto_price, now, overrides=None):
        """检查是否触发首次开仓"""
        abs_diff = abs(diff_percent)
        levels = self.resolve_levels(overrides, is_reversal=state.reversal)

        for level, margin in levels:
            if abs_diff >= level and level not in state.triggered_levels:
                direction = 'long' if diff_percent <= 0 else 'short'
                action_type = ActionType.OPEN_LONG if direction == 'long' else ActionType.OPEN_SHORT
                return TradeAction(
                    action_type=action_type,
                    stock=stock, crypto=crypto,
                    margin=margin, direction=direction,
                    level=level, diff_percent=diff_percent,
                )

        return None

    # ── 加仓检查 ────────────────────────

    def _check_add(self, state, stock, crypto, diff_percent,
                   crypto_price, now, overrides=None):
        """检查是否触发新阶梯加仓"""
        abs_diff = abs(diff_percent)
        direction = state.direction

        if state.status == Status.ALERT_ONLY:
            # 超过 3% 后不再加仓
            return None

        levels = self.resolve_levels(overrides, is_reversal=state.reversal)

        for level, margin in levels:
            if abs_diff >= level and level not in state.triggered_levels:
                action_type = ActionType.ADD_LONG if direction == 'long' else ActionType.ADD_SHORT
                return TradeAction(
                    action_type=action_type,
                    stock=stock, crypto=crypto,
                    margin=margin, direction=direction,
                    level=level, diff_percent=diff_percent,
                )

        return None

    def commit(self, action: TradeAction, now: datetime, crypto_price: float):
        """
        开仓/加仓成功后，把状态真正落账（由 trade_engine 在订单成交后调用）。

        之前策略在返回动作时就乐观写入 entries/status，导致交易所下单失败或
        未连接时，GUI 仍显示「持仓中」，而实盘根本没有仓位（虚拟持仓）。
        现在改为：订单成交成功 → 才 commit 落账；失败则状态保持原样。
        """
        state = self.get_state(action.stock, action.crypto)

        if action.action_type in (ActionType.OPEN_LONG, ActionType.OPEN_SHORT):
            state.direction = action.direction
            state.status = (
                Status.ACTIVE if abs(action.diff_percent) <= self.EMERGENCY_LEVEL
                else Status.ALERT_ONLY
            )
            if state.first_open_time is None:
                state.first_open_time = now
        elif action.action_type in (ActionType.ADD_LONG, ActionType.ADD_SHORT):
            if abs(action.diff_percent) > self.EMERGENCY_LEVEL:
                state.status = Status.ALERT_ONLY

        state.triggered_levels.add(action.level)
        state.entries.append(EntryRecord(
            time=now, level=action.level, direction=action.direction,
            margin=action.margin, price=crypto_price, exchange='',
        ))
        logger.info(
            f"[{state.alert_key}] 成交落账: {action.direction} "
            f"(level={action.level}%), margin={action.margin}U, "
            f"total={state.total_margin}U"
        )

    def adopt_position(self, stock, crypto, direction, margin, price, now,
                       abs_diff=0.0, levels=None):
        """
        将交易所已有真实持仓纳入策略管理（对账）。

        场景：程序重启后策略内存状态清空，但交易所仍有真实持仓，
        若不纳入管理，止盈/平仓会因 state 空闲而被跳过，导致
        「软件显示没持仓、账户却有仓位」或「盈利了却不平仓」。
        """
        state = self.get_state(stock, crypto)
        if state.is_active:
            return
        state.direction = direction
        state.status = Status.ACTIVE
        state.first_open_time = now
        # 标记当前价差已覆盖的阶梯，避免纳入后立即重复加仓
        for lv, _ in (levels or []):
            if lv <= abs_diff:
                state.triggered_levels.add(lv)
        state.entries.append(EntryRecord(
            time=now, level=0.0, direction=direction,
            margin=margin, price=price, exchange='',
        ))
        logger.info(
            f"[{state.alert_key}] 对账：纳入真实持仓 {direction} "
            f"margin={margin}U, 已覆盖阶梯={sorted(state.triggered_levels)}"
        )

    # ── 止盈检查 ────────────────────────

    def _check_take_profit(self, state, stock, crypto, diff_percent):
        """
        检查止盈条件：价差回归到盈利阈值
        当方向正确时：long期望价差回归（diff从负变0），short期望diff从正变0
        盈亏计算：|diff_open - diff_now| × leverage = 保证金收益率

        简化：浮动盈亏达到总保证金 × 5% 就止盈
        实际在 trade_engine 层从交易所查 unrealized_pnl 做精确判断
        这里只做策略层面的标记判断
        """
        # 策略层不计算精确盈亏（价格变动微妙），
        # 在 trade_engine 层根据交易所 fetch_positions 的
        # unrealized_pnl / total_margin >= 5% 来判断
        return None

    # ── 反转检查 ────────────────────────

    def _check_reversal(self, state, stock, crypto, diff_percent,
                        crypto_price, now, can_open, overrides=None):
        """检查是否触发反转（1小时内 + 反向≥2%）。超过窗口则重置为空闲，重新捕捉机会"""
        if not state.close_time or not state.first_open_time:
            return None

        elapsed = state.close_time - state.first_open_time
        if elapsed > timedelta(hours=self.REVERSAL_WINDOW_HOURS):
            # 反转窗口已过，重置为空闲，等待下一次开仓机会
            self._reset_to_idle(state)
            logger.info(f"[{state.alert_key}] 反转窗口已过，重置为空闲，等待下一次机会")
            return None

        if not can_open:
            return None

        abs_diff = abs(diff_percent)
        if abs_diff < self.REVERSAL_THRESHOLD:
            return None

        # 方向相反
        new_direction = 'long' if diff_percent <= 0 else 'short'
        if new_direction == state.direction:
            return None

        # 触发反转
        logger.info(f"[{state.alert_key}] 🔄 反转触发! {state.direction}→{new_direction}, "
                    f"elapsed={elapsed}, diff={diff_percent:+.2f}%")

        # 重置并进入反转模式
        old_direction = state.direction
        state.direction = new_direction
        state.triggered_levels = set()
        state.entries = []
        state.first_open_time = now
        state.close_time = None
        state.reversal = True
        state.status = Status.IDLE  # 让 _check_entry 触发新开仓

        # 立即检查开仓
        return self._check_entry(state, stock, crypto, diff_percent,
                                 crypto_price, now, overrides=overrides)

    # ── 标记平仓 ────────────────────────

    def mark_closed(self, stock, crypto, now, was_take_profit=True):
        """引擎平仓后调用，标记状态"""
        state = self.get_state(stock, crypto)
        state.close_time = now
        state.status = Status.CLOSED

        logger.info(f"[{state.alert_key}] 平仓完成 "
                    f"({'止盈' if was_take_profit else '强制平仓'}), "
                    f"duration={now - (state.first_open_time or now)}, "
                    f"total_margin={state.total_margin}U")
