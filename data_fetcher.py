"""
数据获取模块
数据源：美股用 yfinance，币安用 ccxt
支持 HTTP 代理（国内访问 yahoo finance 和币安 API 必需）
"""

import yfinance as yf
import ccxt
import datetime
import logging
import time
import json
import os
import requests

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
            return {
                'http': proxy['http'],
                'https': proxy.get('https') or proxy['http'],
            }
    except Exception:
        pass
    return None


class PriceFetcher:
    def __init__(self):
        self._proxy = _load_proxy()
        self._session = None
        self._ticker_cache = {}
        self._last_request_time = 0
        self._min_interval = 1.5  # yfinance 请求最小间隔（秒）

        # ── 币安 ──
        binance_kwargs = {
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
            'rateLimit': 1200,
            'timeout': 15000,
        }
        if self._proxy:
            binance_kwargs['proxies'] = self._proxy
            logger.info(f"币安 代理已启用: {self._proxy['https']}")
        self.exchange = ccxt.binance(binance_kwargs)

        # ── yfinance 专用 Session ──
        self._init_yf_session()

    def _init_yf_session(self):
        """创建带代理的 requests Session，所有 yfinance 请求走代理"""
        self._session = requests.Session()
        # 关键：忽略系统代理（Windows 可能残留旧的系统代理端口），
        # 只用 settings.json 里配置的代理，否则会被死掉的系统代理劫持。
        self._session.trust_env = False
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        if self._proxy:
            self._session.proxies.update(self._proxy)
            logger.info(f"yfinance 代理已启用: {self._proxy['https']}")
        else:
            logger.info("yfinance 直连模式（无代理）")

    def _rate_limit(self):
        """控制请求频率，避免被 yfinance 限流"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _get_ticker(self, symbol):
        """获取缓存的 yfinance Ticker（注入共享 session）"""
        if symbol not in self._ticker_cache:
            self._ticker_cache[symbol] = yf.Ticker(symbol, session=self._session)
        return self._ticker_cache[symbol]

    def _is_weekend(self):
        return datetime.datetime.now().weekday() >= 5

    def _fetch_yahoo_chart(self, symbol, retries=3):
        """
        直接请求 Yahoo Finance chart 接口获取原始数据。
        绕过 yfinance 的 cookie/crumb 机制（新版 yfinance 的 crumb 请求
        在代理环境下不稳定，会导致 history() 返回空）。
        """
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {'range': '5d', 'interval': '1d', 'includePrePost': True}
        for attempt in range(retries):
            try:
                resp = self._session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    result = data.get('chart', {}).get('result')
                    if result:
                        return result[0]
                    logger.warning(f"{symbol}: Yahoo 返回空 result")
                    return None
                elif resp.status_code in (429, 451):
                    # 限流或地域封锁，退避重试
                    logger.debug(f"{symbol}: Yahoo HTTP {resp.status_code}，重试 {attempt+1}/{retries}")
                    time.sleep(1.5 * (attempt + 1))
                else:
                    logger.warning(f"{symbol}: Yahoo HTTP {resp.status_code}")
                    time.sleep(1)
            except Exception as e:
                logger.debug(f"{symbol}: 请求失败({attempt+1}/{retries}): {e}")
                time.sleep(1.5 * (attempt + 1))
        return None

    def get_us_stock_price(self, symbol):
        """
        获取美股参考价格
        策略：取收盘价和盘后价中较低者，作为锚定基准
          - 周六/周日：直接用最近交易日收盘价（周五）
          - 非周末：  对比收盘价 vs 盘后价，返回较低值
        """
        try:
            self._rate_limit()
            result = self._fetch_yahoo_chart(symbol)
            if result is None:
                logger.warning(f"{symbol}: Yahoo 数据获取失败，检查代理/网络")
                return None

            meta = result.get('meta', {})

            # 最近收盘价：5 天内最后一个非空 close
            quote = result.get('indicators', {}).get('quote', [])
            close_series = quote[0].get('close', []) if quote else []
            closes = [c for c in close_series if c is not None]
            if not closes:
                rmp = meta.get('regularMarketPrice')
                if rmp:
                    return round(float(rmp), 2)
                logger.warning(f"{symbol}: 无收盘价数据")
                return None

            close_price = float(closes[-1])
            logger.debug(f"{symbol}: 收盘价 ${close_price:.2f}")

            # 周末：直接用收盘价
            if self._is_weekend():
                return round(close_price, 2)

            # 盘后价对比，取较低者
            post_price = meta.get('postMarketPrice')
            if post_price and float(post_price) > 0:
                post_price = float(post_price)
                chosen = min(close_price, post_price)
                if chosen == post_price:
                    logger.debug(f"{symbol}: 盘后价 ${post_price:.2f} 低于收盘价，采用盘后价")
                else:
                    logger.debug(f"{symbol}: 收盘价 ${close_price:.2f} 低于盘后价，采用收盘价")
                return round(chosen, 2)

            return round(close_price, 2)

        except Exception as e:
            logger.error(f"{symbol}: {e}")
            return None

    def get_binance_price(self, symbol):
        """获取币安现货最新成交价"""
        for attempt in range(2):
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                last = ticker.get('last')
                if last and last > 0:
                    return round(float(last), 2)
                return None
            except ccxt.RateLimitExceeded:
                time.sleep(3)
            except ccxt.NetworkError:
                logger.error(f"币安 {symbol}: 网络不通")
                return None
            except Exception as e:
                logger.error(f"币安 {symbol}: {e}")
                return None
        return None

    def reload_proxy(self):
        """重新加载代理配置并重建 session"""
        self._proxy = _load_proxy()
        if self._proxy:
            self.exchange.proxies = self._proxy
        else:
            self.exchange.proxies = None
        self._ticker_cache.clear()
        self._init_yf_session()

    def clear_cache(self):
        self._ticker_cache.clear()
