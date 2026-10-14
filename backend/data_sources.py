"""Unified market-data layer.

Exposes a single ``fetch_ohlcv`` entry point that normalizes data from
multiple providers into one schema::

    [{"time": <unix seconds>, "open": .., "high": .., "low": .., "close": .., "volume": ..}, ...]

Providers
---------
- ``binance``  : crypto, via the public REST klines endpoint (no API key).
- ``yfinance`` : stocks, gold / commodities and forex, via Yahoo Finance.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Interval handling
# ---------------------------------------------------------------------------
# Canonical intervals used by the API / frontend.
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]

_BINANCE_INTERVAL = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}

# Yahoo has no native 4h; we fall back to 1h for that bucket.
_YF_INTERVAL = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "60m", "4h": "60m", "1d": "1d", "1w": "1wk",
}

# Yahoo limits how far intraday data can go back; pick a safe period per interval.
_YF_PERIOD = {
    "1m": "5d", "5m": "1mo", "15m": "1mo", "30m": "1mo",
    "1h": "3mo", "4h": "3mo", "1d": "2y", "1w": "5y",
}

_BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",  # public data mirror, fewer geo blocks
]

# A few example symbols surfaced in the UI per source.
SOURCES: Dict[str, Dict[str, Any]] = {
    "binance": {
        "label": "Crypto (Binance)",
        "examples": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
        "hint": "ใส่สัญลักษณ์แบบ Binance เช่น BTCUSDT, ETHUSDT",
    },
    "yfinance": {
        "label": "หุ้น / ทองคำ / Forex (Yahoo)",
        "examples": ["AAPL", "PTT.BK", "GC=F", "XAUUSD=X", "EURUSD=X", "^SET.BK"],
        "hint": "หุ้นสากล: AAPL | หุ้นไทย: PTT.BK | ทอง: GC=F | Forex: EURUSD=X",
    },
    "demo": {
        "label": "Demo (ออฟไลน์ — ข้อมูลจำลอง)",
        "examples": ["DEMO", "TREND", "WAVE"],
        "hint": "ข้อมูลจำลองแบบ deterministic ใช้ทดลองแอป/indicator/backtest โดยไม่ต้องต่อเน็ต",
    },
}

_INTERVAL_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 86400, "1w": 604800,
}


class DataError(Exception):
    """Raised when market data cannot be retrieved."""


# ---------------------------------------------------------------------------
# Binance
# ---------------------------------------------------------------------------
def _fetch_binance(symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
    iv = _BINANCE_INTERVAL.get(interval)
    if iv is None:
        raise DataError(f"Binance ไม่รองรับ interval: {interval}")

    params = {"symbol": symbol.upper(), "interval": iv, "limit": min(max(limit, 1), 1000)}
    last_err: Exception | None = None
    for host in _BINANCE_HOSTS:
        try:
            resp = requests.get(f"{host}/api/v3/klines", params=params, timeout=20)
            if resp.status_code == 400:
                raise DataError(f"ไม่พบสัญลักษณ์ '{symbol}' บน Binance")
            resp.raise_for_status()
            rows = resp.json()
            out = []
            for k in rows:
                out.append({
                    "time": int(k[0]) // 1000,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return out
        except DataError:
            raise
        except Exception as exc:  # network / parse -> try next host
            last_err = exc
            continue
    raise DataError(f"ดึงข้อมูล Binance ไม่สำเร็จ: {last_err}")


# ---------------------------------------------------------------------------
# Yahoo Finance
# ---------------------------------------------------------------------------
def _fetch_yfinance(symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
    import yfinance as yf

    iv = _YF_INTERVAL.get(interval)
    period = _YF_PERIOD.get(interval, "1y")
    if iv is None:
        raise DataError(f"Yahoo ไม่รองรับ interval: {interval}")

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=iv, auto_adjust=False)
    except Exception as exc:
        raise DataError(f"ดึงข้อมูล Yahoo ไม่สำเร็จ: {exc}")

    if df is None or df.empty:
        raise DataError(f"ไม่พบข้อมูลสำหรับ '{symbol}' (ลองตรวจสัญลักษณ์/interval)")

    df = df.reset_index()
    # The datetime column is named 'Datetime' (intraday) or 'Date' (daily).
    time_col = "Datetime" if "Datetime" in df.columns else "Date"

    # Resample to 4h if requested (Yahoo has no native 4h bucket).
    if interval == "4h":
        df = _resample_4h(df, time_col)
        time_col = "Date"

    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ts = pd.Timestamp(row[time_col])
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC")
        unix = int(ts.timestamp())
        try:
            out.append({
                "time": unix,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]) if not pd.isna(row["Volume"]) else 0.0,
            })
        except (ValueError, TypeError):
            continue  # skip rows with NaN prices

    if not out:
        raise DataError(f"ไม่มีแท่งเทียนที่ใช้ได้สำหรับ '{symbol}'")
    return out[-limit:] if limit else out


# ---------------------------------------------------------------------------
# Demo (offline, deterministic synthetic candles)
# ---------------------------------------------------------------------------
def _fetch_demo(symbol: str, interval: str, limit: int) -> List[Dict[str, Any]]:
    """Generate reproducible synthetic OHLCV so the app works without network."""
    step = _INTERVAL_SECONDS.get(interval, 3600)
    n = min(max(limit, 10), 2000)
    # Seed from the symbol so the same symbol always yields the same series.
    seed = sum(ord(ch) for ch in (symbol or "DEMO").upper()) or 42
    base = 100.0 + (seed % 50)
    price = base
    now = int(time.time())
    start = now - n * step
    out: List[Dict[str, Any]] = []
    for i in range(n):
        # deterministic pseudo-random drift + sine wave + mild noise
        drift = 0.02 * math.sin(i / 18.0) + 0.015 * math.sin(i / 47.0)
        noise = math.sin(seed + i * 1.37) * 0.6
        o = price
        c = max(0.5, o * (1 + drift / 100) + noise)
        hi = max(o, c) + abs(math.sin(seed + i * 2.1)) * (o * 0.004)
        lo = min(o, c) - abs(math.cos(seed + i * 1.7)) * (o * 0.004)
        vol = 1000 + abs(math.sin(seed + i * 0.9)) * 5000
        out.append({
            "time": start + i * step,
            "open": round(o, 4), "high": round(hi, 4),
            "low": round(lo, 4), "close": round(c, 4), "volume": round(vol, 2),
        })
        price = c
    return out


def _resample_4h(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    tmp = df.set_index(pd.DatetimeIndex(df[time_col]))
    agg = tmp.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna(subset=["Open"])
    agg = agg.reset_index().rename(columns={agg.index.name or "index": "Date"})
    if "Date" not in agg.columns:
        agg = agg.rename(columns={agg.columns[0]: "Date"})
    return agg


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def fetch_ohlcv(source: str, symbol: str, interval: str, limit: int = 500) -> List[Dict[str, Any]]:
    source = (source or "").lower().strip()
    symbol = (symbol or "").strip()
    if not symbol:
        raise DataError("กรุณาระบุสัญลักษณ์ (symbol)")
    if interval not in INTERVALS:
        raise DataError(f"interval ไม่ถูกต้อง ใช้ได้: {', '.join(INTERVALS)}")

    if source == "binance":
        return _fetch_binance(symbol, interval, limit)
    if source == "yfinance":
        return _fetch_yfinance(symbol, interval, limit)
    if source == "demo":
        return _fetch_demo(symbol, interval, limit)
    raise DataError(f"ไม่รู้จักแหล่งข้อมูล '{source}'")


def to_dataframe(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convert the normalized candle list into an OHLCV DataFrame."""
    df = pd.DataFrame(candles)
    if df.empty:
        return df
    df = df.sort_values("time").drop_duplicates(subset="time").reset_index(drop=True)
    return df
