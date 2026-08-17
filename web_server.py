"""
Web 服务器 — 手机/电脑均可访问，与桌面端共享配置和监控数据
启动: python web_server.py
访问: http://localhost:5000 或 http://你的电脑IP:5000
"""

import sys
import os
import json
import time
import datetime
import threading

from flask import Flask, jsonify, request, render_template

# 确保项目路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import PriceFetcher
from notifier import Notifier
from monitor import MonitorThread
from paths import get_config_dir

# ── 配置 ──────────────────────────────

APP_DIR = get_config_dir()
CONFIG_FILE = os.path.join(APP_DIR, 'config.json')
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
ALERT_LOG_FILE = os.path.join(APP_DIR, 'alert_log.json')

app = Flask(__name__)

# ── 共享状态 ──────────────────────────

pairs = []           # [(stock, crypto, threshold), ...]
latest_results = []  # 最新监控结果
alert_history = []   # 最近告警记录
monitor = None
trade_engine = None  # 交易引擎（由 GUI 注入）
trade_snapshots = []  # 最新交易快照
trade_history = []    # 交易执行历史

def load_pairs():
    global pairs
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            pairs = json.load(f).get('pairs', [])
    except Exception:
        pairs = []

def save_pairs():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'pairs': pairs}, f, indent=4, ensure_ascii=False)

def get_pairs_copy():
    return list(pairs)

# ── API ───────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    return jsonify({
        'results': latest_results,
        'paused': monitor._paused if monitor else True,
        'pair_count': len(pairs),
        'update_time': datetime.datetime.now().strftime('%H:%M:%S'),
    })

@app.route('/api/pairs', methods=['GET'])
def api_get_pairs():
    return jsonify({'pairs': pairs})

@app.route('/api/pairs/add', methods=['POST'])
def api_add_pair():
    data = request.get_json()
    stock = data.get('stock', '').strip().upper()
    crypto = data.get('crypto', '').strip().upper()
    threshold = float(data.get('threshold', 0.5))
    if stock and crypto:
        pairs.append([stock, crypto, threshold])
        save_pairs()
        return jsonify({'ok': True, 'message': f'已添加 {stock} → {crypto}'})
    return jsonify({'ok': False, 'message': '参数不完整'}), 400

@app.route('/api/pairs/delete', methods=['POST'])
def api_delete_pair():
    data = request.get_json()
    idx = data.get('index', -1)
    if 0 <= idx < len(pairs):
        removed = pairs.pop(idx)
        save_pairs()
        return jsonify({'ok': True, 'message': f'已删除 {removed[0]}'})
    return jsonify({'ok': False, 'message': '无效的索引'}), 400

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({})

@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    try:
        settings = request.get_json()
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
        if monitor:
            monitor.reload_notifier()
            monitor.set_interval(settings.get('poll_interval', 30))
            monitor.fetcher.reload_proxy()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500

@app.route('/api/alerts', methods=['GET'])
def api_get_alerts():
    try:
        if os.path.exists(ALERT_LOG_FILE):
            with open(ALERT_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return jsonify({'alerts': logs[-50:]})  # 最近 50 条
    except Exception:
        pass
    return jsonify({'alerts': []})

@app.route('/api/monitor/pause', methods=['POST'])
def api_toggle_pause():
    if not monitor:
        return jsonify({'ok': False}), 500
    data = request.get_json()
    paused = data.get('paused', not monitor._paused)
    if paused:
        monitor.pause()
    else:
        monitor.resume()
    return jsonify({'ok': True, 'paused': monitor._paused})

@app.route('/api/monitor/config', methods=['POST'])
def api_config():
    """批量更新配置：pairs + settings"""
    data = request.get_json()
    if 'pairs' in data:
        global pairs
        pairs = data['pairs']
        save_pairs()
    return jsonify({'ok': True})

# ── 监控回调 ───────────────────────────

@app.route('/api/trader/status')
def api_trader_status():
    """交易引擎状态"""
    if not trade_engine:
        return jsonify({'running': False, 'paused': True, 'mode': 'none',
                        'connections': [], 'window': 'unknown', 'snapshots': []})

    try:
        from auto_trader.scheduler import TradingScheduler
        sched = TradingScheduler()
    except Exception:
        sched = None

    return jsonify({
        'running': trade_engine._running,
        'paused': trade_engine._paused,
        'mode': trade_engine._mode,
        'connections': trade_engine.get_active_exchanges(),
        'window': sched.get_window() if sched else 'unknown',
        'window_label': sched.get_window_label() if sched else '?',
        'snapshots': trade_snapshots,
    })

@app.route('/api/trader/positions')
def api_trader_positions():
    """当前交易状态快照"""
    positions = []
    for s in trade_snapshots:
        if s.get('status') in ('active', 'alert_only', 'reversal'):
            positions.append(s)
    return jsonify({'positions': positions, 'total': len(positions)})

@app.route('/api/trader/history')
def api_trader_history():
    """交易历史"""
    return jsonify({'trades': trade_history[-50:]})

@app.route('/api/trader/emergency_close', methods=['POST'])
def api_trader_emergency_close():
    """紧急全部平仓"""
    if not trade_engine:
        return jsonify({'ok': False, 'message': '交易引擎未启动'}), 500
    try:
        trade_engine.emergency_close_all()
        return jsonify({'ok': True, 'message': '紧急平仓已执行'})
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500

@app.route('/api/trader/toggle', methods=['POST'])
def api_trader_toggle():
    """启动/暂停交易"""
    if not trade_engine:
        return jsonify({'ok': False, 'message': '交易引擎未启动'}), 500
    data = request.get_json() or {}
    paused = data.get('paused', not trade_engine._paused)
    if paused:
        trade_engine.pause()
    else:
        trade_engine.resume()
    return jsonify({'ok': True, 'paused': trade_engine._paused})

# ── 监控回调 ───────────────────────────

def on_data_updated(results):
    global latest_results
    latest_results = results

def on_alert(entry):
    global alert_history
    alert_history.append(entry)
    # 只保留最近 100 条内存记录
    if len(alert_history) > 100:
        alert_history = alert_history[-100:]

# ── 启动 ───────────────────────────────

def start_monitor():
    global monitor
    load_pairs()
    monitor = MonitorThread(pairs_callback=get_pairs_copy)
    monitor.data_updated.connect(on_data_updated)
    monitor.alert_triggered.connect(on_alert)
    # Web 服务器没有 tray，桌面通知自然失效
    monitor.start()

    # 加载轮询间隔
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            s = json.load(f)
        monitor.set_interval(s.get('poll_interval', 30))
    except Exception:
        pass
    print(f"[Web] 监控已启动，{len(pairs)} 个标的，间隔 {monitor._poll_interval}s")

def main():
    load_pairs()
    print(f"[Web] 启动中... 地址: http://localhost:5000")
    print(f"[Web] 手机访问: http://你的电脑IP:5000")
    start_monitor()
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
