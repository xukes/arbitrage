"""
交易引擎 — QThread 主循环
串联 scheduler → strategy → exchange，执行自动交易

架构：
  TradeEngine(QThread)
    ├── TradingScheduler   (时间窗口判断)
    ├── StrategyEngine     (每标的策略状态机)
    ├── BinanceFutures     (币安合约)
    ├── OkxSwap            (OKX 永续)
    └── PriceFetcher       (复用 monitor 的)
"""

import os
import json
import time
import logging
import datetime
import threading

from PyQt5.QtCore import QThread, pyqtSignal

from auto_trader.scheduler import (
    TradingScheduler, WINDOW_TRADING, WINDOW_CLOSE_ONLY, WINDOW_TESTNET
)
from auto_trader.strategy import (
    StrategyEngine, TradeAction, ActionType, Status, PairState, PairOverrides
)
from auto_trader.exchange import (
    BinanceFutures, OkxSwap, OrderResult, PositionInfo
)
from paths import get_config_dir

logger = logging.getLogger(__name__)

APP_DIR = get_config_dir()
TRADE_CONFIG_FILE = os.path.join(APP_DIR, 'auto_trader_config.json')
TRADE_LOG_FILE = os.path.join(APP_DIR, 'trade_log.json')


def _load_trade_config():
    """加载交易配置"""
    defaults = {
        'mode': 'testnet',
        'trading_pairs': [],
        'binance': {
            'enabled': True,
            'live_api_key': '', 'live_secret': '',
            'testnet_api_key': '', 'testnet_secret': '',
        },
        'okx': {
            'enabled': False,
            'live_api_key': '', 'live_secret': '', 'live_passphrase': '',
            'testnet_api_key': '', 'testnet_secret': '', 'testnet_passphrase': '',
        },
        'leverage': 10,
        'base_margin': 100,
        'take_profit_pct': 5.0,
        'poll_interval': 10,
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
    """保存交易配置"""
    try:
        with open(TRADE_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"交易配置保存失败: {e}")


class TradeEngine(QThread):
    """
    自动交易引擎线程
    独立于 MonitorThread 运行，复用其 PriceFetcher + Notifier
    """

    # ── Signals ──
    status_updated = pyqtSignal(list)       # 持仓状态列表
    trade_executed = pyqtSignal(dict)       # 单笔交易通知
    emergency_alert = pyqtSignal(str, str)  # 紧急告警 (title, body)
    log_message = pyqtSignal(str)           # 日志消息

    def __init__(self, fetcher, notifier, pairs_callback,
                 parent=None):
        """
        fetcher: PriceFetcher (共享 monitor 的)
        notifier: Notifier (共享 monitor 的)
        pairs_callback: 返回监控标的列表 [(stock, crypto, threshold), ...]
        """
        super().__init__(parent)
        self.fetcher = fetcher
        self.notifier = notifier
        self.pairs_callback = pairs_callback
        self.config = _load_trade_config()
        self.scheduler = TradingScheduler()
        self.strategy = StrategyEngine(
            base_margin=self.config.get('base_margin', 100)
        )
        self._pair_overrides: dict[str, PairOverrides] = {}
        self._load_pair_overrides()
        self.binance = BinanceFutures()
        self.okx = OkxSwap()

        self._running = True
        self._paused = True  # 默认暂停，需手动启动
        self._mode = self.config.get('mode', 'testnet')  # 'testnet' | 'live'
        self._poll_interval = self.config.get('poll_interval', 10)
        self._last_force_close_warn = None  # 周一 12:00 临近时的告警时间

    # ── 公共 API ──────────────────────────

    def set_mode(self, mode):
        """切换 testnet/live 模式"""
        if mode not in ('testnet', 'live'):
            return
        self._mode = mode
        self.config['mode'] = mode
        save_trade_config(self.config)
        self._connect_exchanges()
        logger.info(f"交易模式切换到: {mode}")

    def set_mode_auto(self):
        """根据时间窗口自动切换模式"""
        window = self.scheduler.get_window()
        if window == WINDOW_TESTNET:
            self.set_mode('testnet')
        else:
            self.set_mode('live')

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False

    def _load_pair_overrides(self):
        """从 config 加载 pair_overrides → {key: PairOverrides}"""
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
                margin_multipliers=val.get('margin_multipliers'),
            )

    def reload_config(self):
        """热重载配置（API 密钥变更后调用）"""
        self.config = _load_trade_config()
        self._poll_interval = self.config.get('poll_interval', 10)
        self.strategy.base_margin = self.config.get('base_margin', 100)
        self._load_pair_overrides()
        self._connect_exchanges()

    def get_active_exchanges(self):
        """返回已连接的交易所列表"""
        result = []
        if self.binance.is_connected:
            result.append('binance')
        if self.okx.is_connected:
            result.append('okx')
        return result

    def fetch_balances(self):
        """查询已连接交易所的 USDT 余额，返回 {exchange_name: float}"""
        result = {}
        for name, ex in [('binance', self.binance), ('okx', self.okx)]:
            if ex.is_connected:
                try:
                    result[name] = ex.fetch_balance()
                except Exception:
                    pass
        return result

    def emergency_close_all(self):
        """紧急全部平仓"""
        self.log_message.emit("⚠ 正在执行紧急全部平仓...")
        for key, state in list(self.strategy._states.items()):
            if state.is_active:
                if self._close_all(state):
                    state.status = Status.CLOSED
                    state.close_time = datetime.datetime.now()
                else:
                    self.log_message.emit(f"⚠️ {state.alert_key} 紧急平仓失败，保持持仓")
        self.log_message.emit("🛑 紧急平仓完成")

    # ── 主循环 ────────────────────────────

    def run(self):
        """主循环"""
        logger.info("交易引擎启动")
        self._connect_exchanges()

        while self._running:
            try:
                if self._paused:
                    time.sleep(1)
                    continue

                now = datetime.datetime.now()
                window = self.scheduler.get_window(now)
                can_open = self.scheduler.can_open_new(now)
                should_force = self.scheduler.should_force_close(now)
                window_label = self.scheduler.get_window_label(now)

                # 获取交易标的（新格式: dict by exchange, 旧格式: list）
                trading_pairs = self.config.get('trading_pairs', {})
                if isinstance(trading_pairs, list):
                    # 向后兼容：旧格式 list → 两个交易所共用
                    trading_pairs = {'binance': list(trading_pairs), 'okx': list(trading_pairs)}
                if not trading_pairs:
                    # 默认使用所有监控标的
                    all_pairs = self.pairs_callback()
                    all_keys = [f"{p[0]}:{p[1]}" for p in all_pairs]
                    trading_pairs = {'binance': list(all_keys), 'okx': list(all_keys)}

                # 构建 exchange → [(stock, crypto, threshold), ...] 映射
                all_pairs_map = {}
                for p in self.pairs_callback():
                    key = f"{p[0]}:{p[1]}"
                    all_pairs_map[key] = (p[0], p[1], p[2] if len(p) > 2 else 0.5)

                # 对每个交易所 + 标的组合处理
                snapshots = []
                seen_keys = set()

                for ex_name in ['binance', 'okx']:
                    pair_keys = trading_pairs.get(ex_name, [])
                    for key in pair_keys:
                        if key not in all_pairs_map:
                            continue
                        stock, crypto, threshold = all_pairs_map[key]

                        try:
                            snapshot = self._process_pair(
                                stock, crypto, threshold, now,
                                can_open, should_force, window,
                                target_exchange=ex_name
                            )
                            if key not in seen_keys:
                                snapshots.append(snapshot)
                                seen_keys.add(key)
                        except Exception as e:
                            logger.error(f"处理 {stock}:{crypto} 异常: {e}", exc_info=True)

                # 发射状态更新
                self.status_updated.emit(snapshots)

                # 强制平仓后重置
                if should_force:
                    self.scheduler.reset_force_close()

                # 可中断 sleep
                elapsed = 0
                while elapsed < self._poll_interval and self._running:
                    if not self._paused:
                        time.sleep(1)
                        elapsed += 1
                    else:
                        time.sleep(1)

            except Exception as e:
                logger.error(f"交易引擎循环异常: {e}", exc_info=True)
                time.sleep(10)

        logger.info("交易引擎已停止")
        self._disconnect_exchanges()

    def _process_pair(self, stock, crypto, threshold, now,
                      can_open, should_force, window, target_exchange=None):
        """处理单个标的，返回快照 dict。target_exchange: 'binance'|'okx'|None(两个都用)"""
        key = f"{stock}:{crypto}"

        # 获取价格
        us_price = self.fetcher.get_us_stock_price(stock)
        crypto_price = self.fetcher.get_binance_price(crypto)

        # 计算价差
        if us_price and crypto_price and us_price > 0:
            diff = round((crypto_price - us_price) / us_price * 100, 2)
        else:
            diff = 0

        # 查找该标的的自定义策略参数
        overrides = self._pair_overrides.get(key)

        # 对账：重启后策略状态为空闲，但交易所可能仍有真实持仓，先纳入管理
        self._reconcile_position(stock, crypto, diff, now, target_exchange, overrides)

        # 调用策略
        action = self.strategy.evaluate(
            stock, crypto, diff, us_price or 0, crypto_price or 0,
            now, can_open and window == WINDOW_TRADING, should_force,
            overrides=overrides
        )

        # 执行动作
        if action:
            self._execute_action(action, crypto_price or 0, crypto, target_exchange)

        # 检查止盈（从交易所查实际盈亏）——只要有持仓就检查，不限于交易窗口
        self._check_real_pnl(stock, crypto, now, target_exchange)

        # 构建快照
        state = self.strategy.get_state(stock, crypto)
        return self._build_snapshot(state, us_price, crypto_price, diff, window)

    # ── 执行交易 ──────────────────────────

    def _execute_action(self, action, crypto_price, crypto, target_exchange=None):
        """执行策略返回的交易动作。target_exchange: 'binance'|'okx'|None(两个都用)"""
        a = action.action_type

        if a in (ActionType.OPEN_LONG, ActionType.ADD_LONG):
            ok = self._open_on_exchanges(crypto, 'buy', action.margin, target_exchange)
            if ok:
                # 订单成交后才落账，避免下单失败仍显示「持仓中」的虚拟仓位
                self.strategy.commit(action, datetime.datetime.now(), crypto_price)
                self.trade_executed.emit({
                    'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'pair': f"{action.stock}:{crypto}",
                    'action': 'open_long' if a == ActionType.OPEN_LONG else 'add_long',
                    'direction': 'long',
                    'margin': action.margin,
                    'level': action.level,
                    'diff': action.diff_percent,
                    'exchange': target_exchange or 'both',
                })
                self.log_message.emit(
                    f"🔴 {action.stock}→{crypto} {'开多' if a == ActionType.OPEN_LONG else '加多'} "
                    f"{action.margin}U [阶梯{action.level:.1f}%] ({action.diff_percent:+.2f}%)"
                    f"{' @'+target_exchange if target_exchange else ''}"
                )
            else:
                self.log_message.emit(
                    f"⚠️ {action.stock}→{crypto} {'开多' if a == ActionType.OPEN_LONG else '加多'}失败"
                    f"（交易所未连接或下单失败，当前模式: {self._mode}），未计入持仓"
                )

        elif a in (ActionType.OPEN_SHORT, ActionType.ADD_SHORT):
            ok = self._open_on_exchanges(crypto, 'sell', action.margin, target_exchange)
            if ok:
                self.strategy.commit(action, datetime.datetime.now(), crypto_price)
                self.trade_executed.emit({
                    'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'pair': f"{action.stock}:{crypto}",
                    'action': 'open_short' if a == ActionType.OPEN_SHORT else 'add_short',
                    'direction': 'short',
                    'margin': action.margin,
                    'level': action.level,
                    'diff': action.diff_percent,
                    'exchange': target_exchange or 'both',
                })
                self.log_message.emit(
                    f"🟢 {action.stock}→{crypto} {'开空' if a == ActionType.OPEN_SHORT else '加空'} "
                    f"{action.margin}U [阶梯{action.level:.1f}%] ({action.diff_percent:+.2f}%)"
                    f"{' @'+target_exchange if target_exchange else ''}"
                )
            else:
                self.log_message.emit(
                    f"⚠️ {action.stock}→{crypto} {'开空' if a == ActionType.OPEN_SHORT else '加空'}失败"
                    f"（交易所未连接或下单失败，当前模式: {self._mode}），未计入持仓"
                )

        elif a == ActionType.TAKE_PROFIT:
            self._close_pair(action.stock, action.crypto, now=datetime.datetime.now(),
                           target_exchange=target_exchange)
            self.log_message.emit(
                f"✅ {action.stock}→{action.crypto} 止盈平仓 "
                f"({action.diff_percent:+.2f}%)"
            )

        elif a == ActionType.FORCE_CLOSE:
            self._close_pair(action.stock, action.crypto,
                             now=datetime.datetime.now(), is_force=True,
                             target_exchange=target_exchange)
            self.log_message.emit(
                f"⏰ {action.stock}→{action.crypto} 强制平仓（周一12:00）"
            )

        elif a == ActionType.EMERGENCY_ALERT:
            self._send_emergency(action)
            self.emergency_alert.emit(
                f"⚠️ {action.stock}→{action.crypto} 价差异常!",
                action.emergency_msg
            )

    def _open_on_exchanges(self, crypto, side, total_margin, target_exchange=None):
        """
        在指定交易所开仓。
        target_exchange='binance' → 100% 在币安
        target_exchange='okx' → 100% 在 OKX
        target_exchange=None → 50/50 分摊（向后兼容）
        """
        leverage = self.config.get('leverage', 10)
        results = []

        if target_exchange:
            # 单交易所：全部保证金在一个交易所开
            ex_map = {'binance': self.binance, 'okx': self.okx}
            ex = ex_map.get(target_exchange)
            if ex and ex.is_connected:
                r = ex.open_position(crypto, side, total_margin, leverage)
                results.append(r)
            elif ex:
                logger.warning(f"[{target_exchange}] 未连接，无法开仓 {crypto}")
        else:
            # 双交易所：各 50%
            half = round(total_margin / 2, 1)
            if self.binance.is_connected:
                r = self.binance.open_position(crypto, side, half, leverage)
                results.append(r)
            if self.okx.is_connected:
                r = self.okx.open_position(crypto, side, half, leverage)
                results.append(r)
            # 如果只有一个交易所连接，把另一半也下到那个交易所
            connected = self.get_active_exchanges()
            if len(connected) == 1 and len(results) == 1:
                ex = self.binance if connected[0] == 'binance' else self.okx
                r = ex.open_position(crypto, side, half, leverage)
                results.append(r)

        # 汇总结果，任一单成交即视为成功
        any_success = False
        for r in results:
            if r.success:
                any_success = True
                self.log_message.emit(
                    f"  [{r.exchange}] {r.side} {r.amount} @ ${r.price:.2f} "
                    f"≈ ${r.cost:.0f}"
                )
            else:
                self.log_message.emit(
                    f"  [{r.exchange}] 下单失败: {r.error}"
                )

        if not results:
            logger.warning(
                f"开仓失败：没有已连接的交易所（当前模式: {self._mode}，"
                f"请检查 API Key 与 testnet/live 模式是否匹配）"
            )
        return any_success

    def _reconcile_position(self, stock, crypto, diff, now, target_exchange=None, overrides=None):
        """对账：若交易所存在真实持仓而策略状态空闲，则纳入管理（避免重复加仓）"""
        state = self.strategy.get_state(stock, crypto)
        if state.is_active:
            return
        exchanges_to_check = [(target_exchange, self._ex_by_name(target_exchange))] \
            if target_exchange else [('binance', self.binance), ('okx', self.okx)]
        for ex_name, ex in exchanges_to_check:
            if not (ex and ex.is_connected):
                continue
            try:
                pos = ex.fetch_position(crypto)
            except Exception:
                continue
            if pos and pos.side in ('long', 'short'):
                # 用真实初始保证金，而非 collateral（后者含浮盈，会放大分母导致止盈算错）
                margin = pos.initial_margin or (pos.collateral - pos.unrealized_pnl) \
                    or self.config.get('base_margin', 100)
                levels = self.strategy.resolve_levels(overrides, is_reversal=state.reversal)
                self.strategy.adopt_position(
                    stock, crypto, pos.side, margin, pos.entry_price,
                    now, abs(diff), levels)
                self.log_message.emit(
                    f"🔄 {stock}→{crypto} 检测到交易所已有持仓({pos.side})，已纳入管理"
                )
                return

    def _check_real_pnl(self, stock, crypto, now, target_exchange=None):
        """从交易所查实际盈亏，触发止盈（分母用交易所真实初始保证金，与币安后台 ROI% 一致）"""
        state = self.strategy.get_state(stock, crypto)
        if not state.is_active:
            return

        total_margin = state.total_margin
        if total_margin <= 0:
            return

        total_pnl = 0.0
        total_initial_margin = 0.0
        exchanges_to_check = [(target_exchange, self._ex_by_name(target_exchange))] \
            if target_exchange else [('binance', self.binance), ('okx', self.okx)]

        for ex_name, ex in exchanges_to_check:
            if ex and ex.is_connected:
                pos = ex.fetch_position(crypto)
                if pos:
                    total_pnl += pos.unrealized_pnl
                    total_initial_margin += pos.initial_margin or 0.0

        # 分母优先用交易所实际初始保证金，取不到时回退到策略记录的保证金
        base_margin = total_initial_margin or total_margin

        # 检查止盈条件
        take_profit_pct = self.config.get('take_profit_pct', 5.0)
        if base_margin > 0 and (total_pnl / base_margin * 100) >= take_profit_pct:
            logger.info(
                f"[{stock}:{crypto}] 止盈触发! "
                f"PnL=${total_pnl:.2f} / Margin=${base_margin:.2f} "
                f"= {total_pnl/base_margin*100:.1f}%"
            )
            ok = self._close_all(state, target_exchange)
            if ok:
                state.status = Status.CLOSED
                state.close_time = now
                self.strategy.mark_closed(stock, crypto, now, was_take_profit=True)
                # 记账到 GUI 交易日志
                self.trade_executed.emit({
                    'time': now.strftime('%Y-%m-%d %H:%M:%S'),
                    'pair': f"{stock}:{crypto}",
                    'action': 'take_profit',
                    'direction': state.direction,
                    'margin': total_margin,
                    'level': '',
                })
                self.log_message.emit(
                    f"✅ {stock}→{crypto} 止盈平仓 "
                    f"(PnL=${total_pnl:.2f} / {total_pnl/base_margin*100:.1f}%)"
                )
            else:
                self.log_message.emit(
                    f"⚠️ {stock}→{crypto} 止盈触发但平仓失败，保持持仓，下次轮询重试"
                )

    def _ex_by_name(self, name):
        """根据名称获取交易所实例"""
        return {'binance': self.binance, 'okx': self.okx}.get(name)

    def _close_all(self, state, target_exchange=None):
        """平掉标的所有持仓（指定交易所或全部）。返回是否成功（无持仓/已平视为成功）"""
        direction = state.direction
        if not direction:
            return False
        exchanges_to_close = [(target_exchange, self._ex_by_name(target_exchange))] \
            if target_exchange else [('binance', self.binance), ('okx', self.okx)]
        attempted = 0
        all_ok = True
        for ex_name, ex in exchanges_to_close:
            if ex and ex.is_connected:
                attempted += 1
                r = ex.close_position(state.crypto, direction)
                if not r.success:
                    all_ok = False
                    self.log_message.emit(f"  [{r.exchange}] 平仓失败: {r.error}")
        return attempted > 0 and all_ok

    def _close_pair(self, stock, crypto, now, is_force=False, target_exchange=None):
        """平仓并更新策略状态"""
        state = self.strategy.get_state(stock, crypto)
        if not self._close_all(state, target_exchange):
            self.log_message.emit(
                f"⚠️ {stock}→{crypto} 平仓失败，保持持仓，下次轮询重试"
            )
            return
        self.strategy.mark_closed(
            stock, crypto, now, was_take_profit=not is_force
        )
        self.trade_executed.emit({
            'time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'pair': f"{stock}:{crypto}",
            'action': 'force_close' if is_force else 'take_profit',
            'direction': state.direction,
            'total_margin': state.total_margin,
        })

    def _send_emergency(self, action: TradeAction):
        """发送 >3% 紧急告警"""
        self.notifier.send_alert(
            f"⚠️ 紧急: {action.stock}→{action.crypto} 价差 {action.diff_percent:+.2f}%",
            action.emergency_msg,
            alert_key=f"emergency:{action.stock}:{action.crypto}"
        )

    def _connect_exchanges(self):
        """连接交易所（有 API Key 即连接，不依赖 enabled 开关）"""
        mode = self._mode  # 'testnet' | 'live'
        logger.info(f"连接交易所 (模式: {mode})...")

        # Binance
        bcfg = self.config.get('binance', {})
        if mode == 'testnet':
            bnb_key, bnb_secret = bcfg.get('testnet_api_key', ''), bcfg.get('testnet_secret', '')
        else:
            bnb_key, bnb_secret = bcfg.get('live_api_key', ''), bcfg.get('live_secret', '')
        if bnb_key and bnb_secret:
            self.binance.connect(bnb_key, bnb_secret, testnet=(mode == 'testnet'))
            self.log_message.emit(
                f"Binance {'测试网' if mode == 'testnet' else '实盘'} "
                f"{'已连接' if self.binance.is_connected else '连接失败'}"
            )
        else:
            self.binance._connected = False

        # OKX
        ocfg = self.config.get('okx', {})
        if mode == 'testnet':
            okx_key = ocfg.get('testnet_api_key', '')
            okx_secret = ocfg.get('testnet_secret', '')
            okx_passphrase = ocfg.get('testnet_passphrase', '')
        else:
            okx_key = ocfg.get('live_api_key', '')
            okx_secret = ocfg.get('live_secret', '')
            okx_passphrase = ocfg.get('live_passphrase', '')
        if okx_key and okx_secret:
            self.okx.connect(okx_key, okx_secret, okx_passphrase or None,
                             testnet=(mode == 'testnet'))
            self.log_message.emit(
                f"OKX {'测试网' if mode == 'testnet' else '实盘'} "
                f"{'已连接' if self.okx.is_connected else '连接失败'}"
            )
        else:
            self.okx._connected = False

    def _disconnect_exchanges(self):
        """断开交易所连接"""
        self.binance._connected = False
        self.okx._connected = False
        logger.info("交易所已断开")

    def _build_snapshot(self, state, us_price, crypto_price, diff, window):
        """构建持仓快照字典（用于 GUI）"""
        return {
            'stock': state.stock,
            'crypto': state.crypto,
            'direction': state.direction or '—',
            'status': state.status.value,
            'status_label': self._status_label(state.status),
            'triggered_levels': sorted(list(state.triggered_levels)),
            'total_margin': state.total_margin,
            'entry_count': len(state.entries),
            'first_open': state.first_open_time.strftime('%H:%M')
                if state.first_open_time else '—',
            'us_price': us_price,
            'crypto_price': crypto_price,
            'diff': diff,
            'window': window,
            'reversal': state.reversal,
        }

    def _status_label(self, status):
        """状态中文标签"""
        labels = {
            Status.IDLE: '空闲',
            Status.ACTIVE: '🟢 持仓中',
            Status.CLOSED: '⚫ 已平仓',
            Status.ALERT_ONLY: '🔴 紧急监控',
            Status.REVERSAL: '🔄 反转模式',
        }
        return labels.get(status, str(status.value))
