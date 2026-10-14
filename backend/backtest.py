"""Lightweight long/flat backtesting engine.

The engine is vectorized: each strategy produces a boolean *position* series
(True = long, False = flat). We enter on the *next* bar's open relative to the
signal to avoid look-ahead bias, mark-to-market on close, and apply a per-trade
commission on every position change.

It returns performance statistics, an equity curve and the list of trades
(with entry / exit markers) ready to plot on the price chart.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import ta


# ---------------------------------------------------------------------------
# strategy signal generators -> boolean "is long" series
# ---------------------------------------------------------------------------
def _ma_cross(df: pd.DataFrame, p: Dict[str, Any]) -> pd.Series:
    fast = int(p.get("fast", 20))
    slow = int(p.get("slow", 50))
    f = df["close"].rolling(fast).mean()
    s = df["close"].rolling(slow).mean()
    return (f > s).fillna(False)


def _rsi_reversion(df: pd.DataFrame, p: Dict[str, Any]) -> pd.Series:
    length = int(p.get("length", 14))
    buy = float(p.get("oversold", 30))
    sell = float(p.get("overbought", 55))
    rsi = ta.momentum.RSIIndicator(df["close"], window=length).rsi()
    pos = []
    holding = False
    for v in rsi:
        if np.isnan(v):
            pos.append(False)
            continue
        if not holding and v < buy:
            holding = True
        elif holding and v > sell:
            holding = False
        pos.append(holding)
    return pd.Series(pos, index=df.index)


def _macd_cross(df: pd.DataFrame, p: Dict[str, Any]) -> pd.Series:
    fast = int(p.get("fast", 12))
    slow = int(p.get("slow", 26))
    signal = int(p.get("signal", 9))
    m = ta.trend.MACD(df["close"], window_slow=slow, window_fast=fast, window_sign=signal)
    return (m.macd() > m.macd_signal()).fillna(False)


def _bb_breakout(df: pd.DataFrame, p: Dict[str, Any]) -> pd.Series:
    length = int(p.get("length", 20))
    dev = float(p.get("dev", 2.0))
    bb = ta.volatility.BollingerBands(df["close"], window=length, window_dev=dev)
    upper = bb.bollinger_hband()
    basis = bb.bollinger_mavg()
    pos = []
    holding = False
    for c, u, b in zip(df["close"], upper, basis):
        if np.isnan(u):
            pos.append(False)
            continue
        if not holding and c > u:
            holding = True
        elif holding and c < b:
            holding = False
        pos.append(holding)
    return pd.Series(pos, index=df.index)


STRATEGIES: Dict[str, Dict[str, Any]] = {
    "ma_cross": {
        "name": "MA Crossover",
        "desc": "ซื้อเมื่อเส้นเร็วตัดขึ้นเหนือเส้นช้า ขายเมื่อตัดลง",
        "fn": _ma_cross,
        "params": [{"key": "fast", "label": "Fast MA", "default": 20},
                   {"key": "slow", "label": "Slow MA", "default": 50}],
    },
    "rsi_reversion": {
        "name": "RSI Reversion",
        "desc": "ซื้อเมื่อ RSI ต่ำกว่า oversold ขายเมื่อเกิน overbought",
        "fn": _rsi_reversion,
        "params": [{"key": "length", "label": "RSI Length", "default": 14},
                   {"key": "oversold", "label": "Oversold", "default": 30},
                   {"key": "overbought", "label": "Overbought", "default": 55}],
    },
    "macd_cross": {
        "name": "MACD Signal Cross",
        "desc": "ถือ long เมื่อ MACD อยู่เหนือเส้น signal",
        "fn": _macd_cross,
        "params": [{"key": "fast", "label": "Fast", "default": 12},
                   {"key": "slow", "label": "Slow", "default": 26},
                   {"key": "signal", "label": "Signal", "default": 9}],
    },
    "bb_breakout": {
        "name": "Bollinger Breakout",
        "desc": "ซื้อเมื่อราคาทะลุกรอบบน ขายเมื่อกลับต่ำกว่าเส้นกลาง",
        "fn": _bb_breakout,
        "params": [{"key": "length", "label": "Length", "default": 20},
                   {"key": "dev", "label": "StdDev", "default": 2.0}],
    },
}


def strategies_meta() -> List[Dict[str, Any]]:
    return [{"id": sid, "name": s["name"], "desc": s["desc"], "params": s["params"]}
            for sid, s in STRATEGIES.items()]


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min() * 100) if len(dd) else 0.0


def _bars_per_year(times: pd.Series) -> float:
    if len(times) < 2:
        return 252.0
    median_sec = float(np.median(np.diff(times.values)))
    if median_sec <= 0:
        return 252.0
    return (365.0 * 24 * 3600) / median_sec


def run_backtest(df: pd.DataFrame, strategy: str, params: Dict[str, Any],
                 initial_cash: float = 10_000.0, commission: float = 0.001) -> Dict[str, Any]:
    strat = STRATEGIES.get(strategy)
    if strat is None:
        raise ValueError(f"ไม่รู้จักกลยุทธ์ '{strategy}'")
    if df.empty or len(df) < 30:
        raise ValueError("ข้อมูลไม่พอสำหรับ backtest (ต้องมีอย่างน้อย ~30 แท่ง)")

    df = df.reset_index(drop=True)
    is_long = strat["fn"](df, params).astype(bool).reset_index(drop=True)

    # Enter on the next bar -> shift the position signal by 1.
    position = is_long.shift(1).fillna(False).astype(bool)

    close = df["close"].astype(float)
    ret = close.pct_change().fillna(0.0)

    # Strategy bar returns; charge commission whenever the position flips.
    strat_ret = position.astype(float) * ret
    turnover = position.astype(int).diff().abs().fillna(position.iloc[0].astype(int))
    strat_ret = strat_ret - turnover * commission

    equity = (1.0 + strat_ret).cumprod() * initial_cash
    bh_equity = (1.0 + ret).cumprod() * initial_cash

    # --- trades & markers ---
    trades: List[Dict[str, Any]] = []
    markers: List[Dict[str, Any]] = []
    entry_price = None
    entry_time = None
    pos_arr = position.values
    for i in range(len(df)):
        t = int(df["time"].iloc[i])
        price = float(close.iloc[i])
        now = bool(pos_arr[i])
        prev = bool(pos_arr[i - 1]) if i > 0 else False
        if now and not prev:  # entry
            entry_price, entry_time = price, t
            markers.append({"time": t, "position": "belowBar", "color": "#26A69A",
                            "shape": "arrowUp", "text": "BUY"})
        elif prev and not now and entry_price is not None:  # exit
            pnl_pct = (price - entry_price) / entry_price * 100
            trades.append({"entry_time": entry_time, "entry_price": entry_price,
                           "exit_time": t, "exit_price": price, "return_pct": round(pnl_pct, 2)})
            markers.append({"time": t, "position": "aboveBar", "color": "#EF5350",
                            "shape": "arrowDown", "text": "SELL"})
            entry_price = None
    # close any open trade at the last bar
    if entry_price is not None:
        last_t = int(df["time"].iloc[-1])
        last_p = float(close.iloc[-1])
        pnl_pct = (last_p - entry_price) / entry_price * 100
        trades.append({"entry_time": entry_time, "entry_price": entry_price,
                       "exit_time": last_t, "exit_price": last_p,
                       "return_pct": round(pnl_pct, 2), "open": True})

    eq = equity.values
    wins = [t for t in trades if t["return_pct"] > 0]
    ann = _bars_per_year(df["time"])
    vol = strat_ret.std()
    sharpe = float((strat_ret.mean() / vol) * np.sqrt(ann)) if vol > 0 else 0.0

    stats = {
        "total_return_pct": round((eq[-1] / initial_cash - 1) * 100, 2),
        "buy_hold_return_pct": round((bh_equity.values[-1] / initial_cash - 1) * 100, 2),
        "max_drawdown_pct": round(_max_drawdown(eq), 2),
        "num_trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "sharpe": round(sharpe, 2),
        "final_equity": round(float(eq[-1]), 2),
        "initial_cash": initial_cash,
    }

    equity_curve = [{"time": int(df["time"].iloc[i]), "value": round(float(eq[i]), 2)}
                    for i in range(len(eq))]

    return {"stats": stats, "equity_curve": equity_curve, "trades": trades, "markers": markers}
