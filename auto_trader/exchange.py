"""
交易所抽象层
支持 Binance Futures 和 OKX Perpetual Swap
统一接口：逐仓模式 + 市价单 + 10x 杠杆
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import ccxt
from paths import get_config_dir

logger = logging.getLogger(__name__)

# ── 代理配置 ──────────────────────────

SETTINGS_FILE = os.path.join(get_config_dir(), 'settings.json')


def _load_proxy():
    """从 settings.json 加载代理配置（供 ccxt 使用）"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                s = json.load(f)
            proxy = s.get('proxy', {})
            if proxy.get('enabled') and proxy.get('http'):
                return {
                    'http': proxy['http'],
                    'https': proxy.get('https') or proxy['http'],
                }
    except Exception:
        pass
    return None


@dataclass
class OrderResult:
    """下单返回"""
    success: bool
    exchange: str        # 'binance' | 'okx'
    order_id: str | None
    side: str            # 'buy' | 'sell'
    amount: float        # 成交数量（合约张数）
    price: float         # 成交均价
    cost: float          # 成交金额（USDT）
    error: str | None


@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str
    side: str            # 'long' | 'short' | 'none'
    contracts: float     # 持仓数量
    entry_price: float   # 开仓均价
    mark_price: float    # 标记价格
    unrealized_pnl: float  # 未实现盈亏（USDT）
    pnl_pct: float       # 盈亏百分比（交易所口径 = unrealizedPnl/initialMargin*100）
    collateral: float    # 持仓权益（isolatedWallet+unrealizedPnl，含浮盈，勿当保证金用）
    initial_margin: float = 0.0  # 初始保证金（真正的开仓保证金，用于算收益率）
    leverage: int = 0
    liq_price: float = 0.0  # 强平价格


class ExchangeBase(ABC):
    """交易所基类"""

    def __init__(self, name, default_type):
        self.name = name
        self._default_type = default_type
        self._exchange = None
        self._connected = False
        self._testnet = False
        self._hedged = False  # 账户是否为双向持仓(Hedge)模式

    @property
    def is_connected(self):
        return self._connected

    def connect(self, api_key, secret, passphrase=None, testnet=False):
        """连接交易所"""
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
        """创建 ccxt exchange 实例"""
        pass

    def _symbol(self, raw_symbol):
        """转换交易对格式: BTCUSDT → BTC/USDT:USDT"""
        # 如果是标准格式，直接用；否则拼接
        if '/' in raw_symbol:
            return raw_symbol
        return f"{raw_symbol[:-4]}/USDT:USDT" if raw_symbol.endswith('USDT') else f"{raw_symbol}/USDT:USDT"

    def set_isolated_margin(self, symbol, leverage=10):
        """设置逐仓模式 + 杠杆"""
        if not self._connected:
            return False
        s = self._symbol(symbol)
        try:
            self._set_margin_mode_impl(s, leverage)
            logger.info(f"[{self.name}] {s} 已设置逐仓 ×{leverage}")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] {s} 设置失败: {e}")
            return False

    @abstractmethod
    def _set_margin_mode_impl(self, symbol, leverage):
        """平台特定的逐仓+杠杆设置"""
        pass

    def open_position(self, symbol, side, usdt_amount, leverage=10):
        """
        开仓/加仓
        side: 'buy'=做多, 'sell'=做空
        usdt_amount: 保证金金额
        返回 OrderResult
        """
        if not self._connected:
            return OrderResult(False, self.name, None, side, 0, 0, 0, '未连接')

        s = self._symbol(symbol)
        try:
            # 确保已设置逐仓
            self.set_isolated_margin(symbol, leverage)

            # 获取当前价格
            ticker = self._exchange.fetch_ticker(s)
            price = ticker.get('last')
            if not price or price <= 0:
                return OrderResult(False, self.name, None, side, 0, 0, 0, '价格获取失败')

            # 计算数量: 名义价值 / 价格
            notional = usdt_amount * leverage
            raw_amount = notional / price
            amount_str = self._exchange.amount_to_precision(s, raw_amount)

            # 下单
            order = self._create_market_order(s, side, amount_str)

            return OrderResult(
                success=True,
                exchange=self.name,
                order_id=order.get('id', ''),
                side=side,
                amount=order.get('filled', float(amount_str)),
                price=order.get('average', price) or price,
                cost=order.get('cost', notional) or notional,
                error=None,
            )
        except Exception as e:
            logger.error(f"[{self.name}] 开仓失败 {symbol} {side}: {e}")
            return OrderResult(False, self.name, None, side, 0, 0, 0, str(e)[:100])

    @abstractmethod
    def _create_market_order(self, symbol, side, amount_str):
        """创建市价单（平台特定）"""
        pass

    def close_position(self, symbol, position_side):
        """
        平仓: 对当前持仓方向做反向市价单
        返回 OrderResult
        """
        if not self._connected:
            return OrderResult(False, self.name, None, 'close', 0, 0, 0, '未连接')

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
                logger.warning(f"[{self.name}] {s} 无 {position_side} 持仓可平")
                return OrderResult(True, self.name, None, close_side, 0, 0, 0, None)

            amount = abs(target['contracts'])
            amount_str = self._exchange.amount_to_precision(s, amount)

            order = self._close_market_order(s, close_side, amount_str)

            return OrderResult(
                success=True,
                exchange=self.name,
                order_id=order.get('id', ''),
                side=close_side,
                amount=order.get('filled', amount),
                price=order.get('average', 0) or 0,
                cost=order.get('cost', 0) or 0,
                error=None,
            )
        except Exception as e:
            logger.error(f"[{self.name}] 平仓失败 {symbol} {position_side}: {e}")
            return OrderResult(False, self.name, None, close_side, 0, 0, 0, str(e)[:100])

    @abstractmethod
    def _close_market_order(self, symbol, close_side, amount_str):
        """创建平仓市价单（平台特定）"""
        pass

    def fetch_position(self, symbol):
        """获取指定持仓，无持仓返回 None"""
        if not self._connected:
            return None
        s = self._symbol(symbol)
        try:
            positions = self._exchange.fetch_positions([s])
            for p in positions:
                if p.get('symbol') == s and abs(p.get('contracts', 0)) > 1e-8:
                    return PositionInfo(
                        symbol=symbol,
                        side=p.get('side', 'none'),
                        contracts=p.get('contracts', 0),
                        entry_price=p.get('entryPrice', 0) or 0,
                        mark_price=p.get('markPrice', 0) or 0,
                        unrealized_pnl=p.get('unrealizedPnl', 0) or 0,
                        pnl_pct=p.get('percentage', 0) or 0,
                        collateral=p.get('collateral', 0) or 0,
                        initial_margin=p.get('initialMargin', 0) or 0,
                        leverage=p.get('leverage', 0) or 0,
                        liq_price=p.get('liquidationPrice', 0) or 0,
                    )
            return None
        except Exception as e:
            logger.error(f"[{self.name}] 查询持仓失败 {symbol}: {e}")
            return None

    def fetch_all_positions(self):
        """获取所有持仓"""
        if not self._connected:
            return []
        try:
            raw = self._exchange.fetch_positions()
            result = []
            for p in raw:
                if abs(p.get('contracts', 0)) < 1e-8:
                    continue
                # 反向解析 symbol
                sym = p.get('symbol', '')
                raw_sym = sym.split('/')[0] + 'USDT' if '/USDT' in sym else sym
                result.append(PositionInfo(
                    symbol=raw_sym,
                    side=p.get('side', 'none'),
                    contracts=p.get('contracts', 0),
                    entry_price=p.get('entryPrice', 0) or 0,
                    mark_price=p.get('markPrice', 0) or 0,
                    unrealized_pnl=p.get('unrealizedPnl', 0) or 0,
                    pnl_pct=p.get('percentage', 0) or 0,
                    collateral=p.get('collateral', 0) or 0,
                    initial_margin=p.get('initialMargin', 0) or 0,
                    leverage=p.get('leverage', 0) or 0,
                    liq_price=p.get('liquidationPrice', 0) or 0,
                ))
            return result
        except Exception as e:
            logger.error(f"[{self.name}] 查询全部持仓失败: {e}")
            return []

    def fetch_balance(self):
        """查询 USDT 可用余额"""
        if not self._connected:
            return 0.0
        try:
            bal = self._exchange.fetch_balance()
            return float(bal.get('free', {}).get('USDT', 0) or 0)
        except Exception as e:
            logger.error(f"[{self.name}] 余额查询失败: {e}")
            return 0.0

    def is_testnet(self):
        return self._testnet

    @staticmethod
    def test_connection(api_key, secret, create_exchange_cb,
                       passphrase=None, testnet=False):
        """独立测试连接（不依赖已连接的实例），返回详细结果 dict"""
        result = {
            'success': False,
            'balance': 0.0,
            'futures_ok': False,
            'error': '',
        }
        if not api_key or not secret:
            result['error'] = '请填写 API Key 和 Secret'
            return result

        try:
            exchange = create_exchange_cb(api_key, secret, passphrase, testnet)
        except Exception as e:
            result['error'] = f'创建交易所实例失败: {str(e)[:180]}'
            return result

        # Step 1: 尝试加载市场（testnet 可能缺少部分端点，容错处理）
        markets_ok = False
        try:
            exchange.load_markets()
            markets_ok = True
        except Exception as e:
            msg = str(e)
            # ccxt 4.x Binance testnet 缺少 sapi 端点，这是正常的
            if '404' in msg or 'sapi' in msg.lower():
                logger.debug(f"load_markets 忽略非致命错误: {msg[:120]}")
                try:
                    # 只加载 futures 相关市场
                    exchange.load_markets(reload=True, params={'type': 'future'})
                    markets_ok = True
                except Exception:
                    pass
            elif 'timed out' in msg.lower() or 'Network' in msg or 'Connection' in msg:
                result['error'] = '网络超时，请检查代理设置或网络连接'
                return result
            else:
                # 其他 load_markets 错误：可能依旧是网络/权限问题
                pass

        # Step 2: 查询余额（验证 API Key 有效性 + 合约权限 + 余额）
        try:
            bal = exchange.fetch_balance()
            usdt = float(bal.get('free', {}).get('USDT', 0) or 0)
            result['balance'] = usdt
            result['futures_ok'] = True
            result['success'] = True
            return result
        except Exception as e:
            msg = str(e)
            # 精准分类错误
            if 'Invalid Api-Key' in msg or 'Api-Key' in msg:
                result['error'] = 'API Key 或 Secret 无效'
            elif '1021' in msg or 'timestamp' in msg.lower() or 'recvwindow' in msg.lower():
                result['error'] = '电脑系统时间不准确（币安拒绝请求）。请同步时间：Windows设置→时间和语言→日期和时间→打开「自动设置时间」并点「立即同步」'
            elif 'Permission' in msg or 'permission' in msg or '403' in msg:
                result['error'] = '权限不足，请确认API Key已开通合约交易权限'
            elif 'Invalid' in msg or 'invalid' in msg or 'signature' in msg.lower() or '401' in msg:
                result['error'] = 'API Key 或 Secret 无效'
            elif 'timed out' in msg.lower() or 'Network' in msg or 'Connection' in msg:
                result['error'] = '网络超时，请检查代理设置'
            elif 'balance' in msg.lower() and ('not' in msg.lower() or 'permission' in msg.lower()):
                result['error'] = '合约账户权限不足，请检查API Key是否开通Futures'
            elif markets_ok:
                result['error'] = f'余额查询失败: {msg[:180]}'
            else:
                result['error'] = f'连接失败: {msg[:180]}'
            return result


# ═══════════════════════════════════════════════════════════
# Binance Futures
# ═══════════════════════════════════════════════════════════

class BinanceFutures(ExchangeBase):
    def __init__(self):
        super().__init__('Binance', 'future')

    def connect(self, api_key, secret, passphrase=None, testnet=False):
        """连接交易所，并检测账户持仓模式（单向 One-way / 双向 Hedge）"""
        ok = super().connect(api_key, secret, passphrase, testnet)
        if ok:
            try:
                mode = self._exchange.fetch_position_mode()
                self._hedged = bool(mode.get('hedged', False))
                logger.info(
                    f"[{self.name}] 持仓模式: {'双向(Hedge)' if self._hedged else '单向(One-way)'}"
                )
            except Exception as e:
                logger.warning(f"[{self.name}] 读取持仓模式失败，默认按单向处理: {e}")
                self._hedged = False
        return ok

    def _create_exchange(self, api_key, secret, passphrase, testnet):
        kwargs = {
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                # 自动校时：对方电脑时间不准（-1021 错误）时自动对齐服务器时间
                'adjustForTimeDifference': True,
            },
            'timeout': 15000,
        }
        proxy = _load_proxy()
        if proxy:
            kwargs['proxies'] = proxy
            logger.info(f"[Binance] 代理已启用: {proxy['https']}")
        exchange = ccxt.binance(kwargs)
        if testnet:
            # ccxt 4.x: 合约测试网需要特殊处理
            # 1. 保存 live URLs
            live_api = exchange.urls['api'].copy()
            # 2. 获取 test URLs（set_sandbox_mode 会生成）
            exchange.set_sandbox_mode(True)
            test_urls = exchange.urls['test'].copy() if 'test' in exchange.urls else {}
            exchange.set_sandbox_mode(False)
            # 3. 合并：live 为底，test 覆盖（缺失的 sapi 等端点沿用 live）
            exchange.urls['api'] = {**live_api, **test_urls}
            logger.info("[Binance] 已切换到测试网")
        return exchange

    def _set_margin_mode_impl(self, symbol, leverage):
        # -4046 "No need to change margin type" / -4059 "No need to change leverage"
        # 表示已经是目标状态，属于正常情况，忽略即可（不再当作错误刷屏）
        try:
            self._exchange.set_margin_mode('isolated', symbol)
        except Exception as e:
            msg = str(e)
            if 'No need to change' not in msg and '-4046' not in msg and '-4059' not in msg:
                raise

        try:
            self._exchange.set_leverage(leverage, symbol)
        except Exception as e:
            msg = str(e)
            if 'No need to change' not in msg and '-4046' not in msg and '-4059' not in msg:
                raise

    def _create_market_order(self, symbol, side, amount_str):
        params = {}
        if self._hedged:
            # 双向持仓模式下必须指定 positionSide，否则报 -4061
            params['positionSide'] = 'LONG' if side == 'buy' else 'SHORT'
        return self._exchange.create_order(
            symbol, 'market', side, float(amount_str), params=params)

    def _close_market_order(self, symbol, close_side, amount_str):
        params = {}
        if self._hedged:
            # 双向持仓模式：用 positionSide 指定平哪一侧；不能用 reduceOnly（会报 -1106）
            params['positionSide'] = 'LONG' if close_side == 'sell' else 'SHORT'
        else:
            # 单向持仓模式：用 reduceOnly 平仓
            params['reduceOnly'] = True
        return self._exchange.create_order(
            symbol, 'market', close_side, float(amount_str), params=params)


# ═══════════════════════════════════════════════════════════
# OKX Perpetual Swap
# ═══════════════════════════════════════════════════════════

class OkxSwap(ExchangeBase):
    def __init__(self):
        super().__init__('OKX', 'swap')

    def _create_exchange(self, api_key, secret, passphrase, testnet):
        kwargs = {
            'apiKey': api_key,
            'secret': secret,
            'password': passphrase or '',
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
            },
            'timeout': 15000,
        }
        proxy = _load_proxy()
        if proxy:
            kwargs['proxies'] = proxy
            logger.info(f"[OKX] 代理已启用: {proxy['https']}")
        exchange = ccxt.okx(kwargs)
        if testnet:
            exchange.set_sandbox_mode(True)
        return exchange

    def _set_margin_mode_impl(self, symbol, leverage):
        self._exchange.set_position_mode(False)  # net mode
        self._exchange.set_leverage(leverage, symbol, params={
            'mgnMode': 'isolated',
            'posSide': 'net',
        })

    def _create_market_order(self, symbol, side, amount_str):
        return self._exchange.create_order(
            symbol, 'market', side, float(amount_str),
            params={'tdMode': 'isolated'}
        )

    def _close_market_order(self, symbol, close_side, amount_str):
        return self._exchange.create_order(
            symbol, 'market', close_side, float(amount_str),
            params={'tdMode': 'isolated', 'reduceOnly': True}
        )
