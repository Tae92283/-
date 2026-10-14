"""Technical-indicator catalog and computation.

Indicators are computed server-side with the `ta` library (pure pandas, no
compiled dependencies) and returned as plot-ready line / histogram series.

Each catalog entry declares:
    - id, name, group
    - overlay : True  -> draw on the price chart
                False -> draw in a separate oscillator pane
    - params  : [{key, label, default}]
    - compute : callable(df, params) -> list[plot]
                where plot = {key, type: 'line'|'histogram', color}
                the series values are attached as {..., 'data': [{time, value}]}
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

import numpy as np
import pandas as pd
import ta


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _series(times: pd.Series, values: pd.Series) -> List[Dict[str, Any]]:
    """Zip a time column with a value series, dropping NaN / inf points."""
    out = []
    for t, v in zip(times, values):
        if v is None:
            continue
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            continue
        out.append({"time": int(t), "value": fv})
    return out


def _p(params: Dict[str, Any], key: str, default: Any) -> Any:
    val = params.get(key, default)
    try:
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
    except (ValueError, TypeError):
        return default
    return val


# ---------------------------------------------------------------------------
# indicator computation functions
# ---------------------------------------------------------------------------
def _ma(fn):
    def compute(df, params):
        length = _p(params, "length", 20)
        color = params.get("color", "#2962FF")
        s = fn(df["close"], length)
        return [{"key": "ma", "type": "line", "color": color,
                 "data": _series(df["time"], s)}]
    return compute


def _sma(df, params):
    length = _p(params, "length", 20)
    s = ta.trend.SMAIndicator(df["close"], window=length).sma_indicator()
    return [{"key": "sma", "type": "line", "color": params.get("color", "#2962FF"),
             "data": _series(df["time"], s)}]


def _ema(df, params):
    length = _p(params, "length", 21)
    s = ta.trend.EMAIndicator(df["close"], window=length).ema_indicator()
    return [{"key": "ema", "type": "line", "color": params.get("color", "#FF6D00"),
             "data": _series(df["time"], s)}]


def _wma(df, params):
    length = _p(params, "length", 20)
    s = ta.trend.WMAIndicator(df["close"], window=length).wma()
    return [{"key": "wma", "type": "line", "color": params.get("color", "#AB47BC"),
             "data": _series(df["time"], s)}]


def _vwap(df, params):
    s = ta.volume.VolumeWeightedAveragePrice(
        df["high"], df["low"], df["close"], df["volume"],
        window=_p(params, "length", 14)).volume_weighted_average_price()
    return [{"key": "vwap", "type": "line", "color": params.get("color", "#00BCD4"),
             "data": _series(df["time"], s)}]


def _bbands(df, params):
    length = _p(params, "length", 20)
    dev = _p(params, "dev", 2.0)
    bb = ta.volatility.BollingerBands(df["close"], window=length, window_dev=dev)
    return [
        {"key": "upper", "type": "line", "color": "#26A69A", "data": _series(df["time"], bb.bollinger_hband())},
        {"key": "basis", "type": "line", "color": "#FF6D00", "data": _series(df["time"], bb.bollinger_mavg())},
        {"key": "lower", "type": "line", "color": "#26A69A", "data": _series(df["time"], bb.bollinger_lband())},
    ]


def _keltner(df, params):
    length = _p(params, "length", 20)
    kc = ta.volatility.KeltnerChannel(df["high"], df["low"], df["close"], window=length)
    return [
        {"key": "upper", "type": "line", "color": "#7E57C2", "data": _series(df["time"], kc.keltner_channel_hband())},
        {"key": "basis", "type": "line", "color": "#B39DDB", "data": _series(df["time"], kc.keltner_channel_mband())},
        {"key": "lower", "type": "line", "color": "#7E57C2", "data": _series(df["time"], kc.keltner_channel_lband())},
    ]


def _donchian(df, params):
    length = _p(params, "length", 20)
    dc = ta.volatility.DonchianChannel(df["high"], df["low"], df["close"], window=length)
    return [
        {"key": "upper", "type": "line", "color": "#EF5350", "data": _series(df["time"], dc.donchian_channel_hband())},
        {"key": "basis", "type": "line", "color": "#FFB74D", "data": _series(df["time"], dc.donchian_channel_mband())},
        {"key": "lower", "type": "line", "color": "#EF5350", "data": _series(df["time"], dc.donchian_channel_lband())},
    ]


def _ichimoku(df, params):
    conv = _p(params, "conversion", 9)
    base = _p(params, "base", 26)
    span_b = _p(params, "spanB", 52)
    ich = ta.trend.IchimokuIndicator(df["high"], df["low"],
                                     window1=conv, window2=base, window3=span_b)
    return [
        {"key": "tenkan", "type": "line", "color": "#2962FF", "data": _series(df["time"], ich.ichimoku_conversion_line())},
        {"key": "kijun", "type": "line", "color": "#EF5350", "data": _series(df["time"], ich.ichimoku_base_line())},
        {"key": "spanA", "type": "line", "color": "#26A69A", "data": _series(df["time"], ich.ichimoku_a())},
        {"key": "spanB", "type": "line", "color": "#FF6D00", "data": _series(df["time"], ich.ichimoku_b())},
    ]


def _psar(df, params):
    step = _p(params, "step", 0.02)
    maxstep = _p(params, "maxStep", 0.2)
    ps = ta.trend.PSARIndicator(df["high"], df["low"], df["close"], step=step, max_step=maxstep)
    return [{"key": "psar", "type": "line", "color": params.get("color", "#FFD600"),
             "data": _series(df["time"], ps.psar())}]


def _rsi(df, params):
    length = _p(params, "length", 14)
    s = ta.momentum.RSIIndicator(df["close"], window=length).rsi()
    return [{"key": "rsi", "type": "line", "color": "#7E57C2",
             "data": _series(df["time"], s), "levels": [30, 50, 70]}]


def _macd(df, params):
    fast = _p(params, "fast", 12)
    slow = _p(params, "slow", 26)
    signal = _p(params, "signal", 9)
    m = ta.trend.MACD(df["close"], window_slow=slow, window_fast=fast, window_sign=signal)
    return [
        {"key": "macd", "type": "line", "color": "#2962FF", "data": _series(df["time"], m.macd())},
        {"key": "signal", "type": "line", "color": "#FF6D00", "data": _series(df["time"], m.macd_signal())},
        {"key": "hist", "type": "histogram", "color": "#26A69A", "data": _series(df["time"], m.macd_diff())},
    ]


def _stoch(df, params):
    k = _p(params, "k", 14)
    d = _p(params, "d", 3)
    st = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"], window=k, smooth_window=d)
    return [
        {"key": "k", "type": "line", "color": "#2962FF", "data": _series(df["time"], st.stoch())},
        {"key": "d", "type": "line", "color": "#FF6D00", "data": _series(df["time"], st.stoch_signal()), "levels": [20, 80]},
    ]


def _stochrsi(df, params):
    length = _p(params, "length", 14)
    sr = ta.momentum.StochRSIIndicator(df["close"], window=length)
    return [
        {"key": "k", "type": "line", "color": "#2962FF", "data": _series(df["time"], sr.stochrsi_k() * 100)},
        {"key": "d", "type": "line", "color": "#FF6D00", "data": _series(df["time"], sr.stochrsi_d() * 100), "levels": [20, 80]},
    ]


def _atr(df, params):
    length = _p(params, "length", 14)
    s = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=length).average_true_range()
    return [{"key": "atr", "type": "line", "color": "#EF5350", "data": _series(df["time"], s)}]


def _adx(df, params):
    length = _p(params, "length", 14)
    a = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=length)
    return [
        {"key": "adx", "type": "line", "color": "#000000", "data": _series(df["time"], a.adx()), "levels": [25]},
        {"key": "+di", "type": "line", "color": "#26A69A", "data": _series(df["time"], a.adx_pos())},
        {"key": "-di", "type": "line", "color": "#EF5350", "data": _series(df["time"], a.adx_neg())},
    ]


def _cci(df, params):
    length = _p(params, "length", 20)
    s = ta.trend.CCIIndicator(df["high"], df["low"], df["close"], window=length).cci()
    return [{"key": "cci", "type": "line", "color": "#7E57C2",
             "data": _series(df["time"], s), "levels": [-100, 0, 100]}]


def _williams(df, params):
    length = _p(params, "length", 14)
    s = ta.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"], lbp=length).williams_r()
    return [{"key": "wpr", "type": "line", "color": "#AB47BC",
             "data": _series(df["time"], s), "levels": [-80, -20]}]


def _roc(df, params):
    length = _p(params, "length", 12)
    s = ta.momentum.ROCIndicator(df["close"], window=length).roc()
    return [{"key": "roc", "type": "line", "color": "#00BCD4",
             "data": _series(df["time"], s), "levels": [0]}]


def _obv(df, params):
    s = ta.volume.OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()
    return [{"key": "obv", "type": "line", "color": "#546E7A", "data": _series(df["time"], s)}]


def _mfi(df, params):
    length = _p(params, "length", 14)
    s = ta.volume.MFIIndicator(df["high"], df["low"], df["close"], df["volume"], window=length).money_flow_index()
    return [{"key": "mfi", "type": "line", "color": "#26A69A",
             "data": _series(df["time"], s), "levels": [20, 80]}]


def _ao(df, params):
    s = ta.momentum.AwesomeOscillatorIndicator(df["high"], df["low"]).awesome_oscillator()
    return [{"key": "ao", "type": "histogram", "color": "#26A69A", "data": _series(df["time"], s)}]


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------
CATALOG: Dict[str, Dict[str, Any]] = {
    # --- overlays (price chart) ---
    "sma": {"name": "SMA", "group": "Overlay", "overlay": True, "compute": _sma,
            "params": [{"key": "length", "label": "Length", "default": 20}, {"key": "color", "label": "สี", "default": "#2962FF", "type": "color"}]},
    "ema": {"name": "EMA", "group": "Overlay", "overlay": True, "compute": _ema,
            "params": [{"key": "length", "label": "Length", "default": 21}, {"key": "color", "label": "สี", "default": "#FF6D00", "type": "color"}]},
    "wma": {"name": "WMA", "group": "Overlay", "overlay": True, "compute": _wma,
            "params": [{"key": "length", "label": "Length", "default": 20}, {"key": "color", "label": "สี", "default": "#AB47BC", "type": "color"}]},
    "vwap": {"name": "VWAP", "group": "Overlay", "overlay": True, "compute": _vwap,
             "params": [{"key": "length", "label": "Length", "default": 14}]},
    "bbands": {"name": "Bollinger Bands", "group": "Overlay", "overlay": True, "compute": _bbands,
               "params": [{"key": "length", "label": "Length", "default": 20}, {"key": "dev", "label": "StdDev", "default": 2.0}]},
    "keltner": {"name": "Keltner Channel", "group": "Overlay", "overlay": True, "compute": _keltner,
                "params": [{"key": "length", "label": "Length", "default": 20}]},
    "donchian": {"name": "Donchian Channel", "group": "Overlay", "overlay": True, "compute": _donchian,
                 "params": [{"key": "length", "label": "Length", "default": 20}]},
    "ichimoku": {"name": "Ichimoku Cloud", "group": "Overlay", "overlay": True, "compute": _ichimoku,
                 "params": [{"key": "conversion", "label": "Conversion", "default": 9}, {"key": "base", "label": "Base", "default": 26}, {"key": "spanB", "label": "Span B", "default": 52}]},
    "psar": {"name": "Parabolic SAR", "group": "Overlay", "overlay": True, "compute": _psar,
             "params": [{"key": "step", "label": "Step", "default": 0.02}, {"key": "maxStep", "label": "Max Step", "default": 0.2}]},

    # --- oscillators (separate pane) ---
    "rsi": {"name": "RSI", "group": "Oscillator", "overlay": False, "compute": _rsi,
            "params": [{"key": "length", "label": "Length", "default": 14}]},
    "macd": {"name": "MACD", "group": "Oscillator", "overlay": False, "compute": _macd,
             "params": [{"key": "fast", "label": "Fast", "default": 12}, {"key": "slow", "label": "Slow", "default": 26}, {"key": "signal", "label": "Signal", "default": 9}]},
    "stoch": {"name": "Stochastic", "group": "Oscillator", "overlay": False, "compute": _stoch,
              "params": [{"key": "k", "label": "%K", "default": 14}, {"key": "d", "label": "%D", "default": 3}]},
    "stochrsi": {"name": "Stochastic RSI", "group": "Oscillator", "overlay": False, "compute": _stochrsi,
                 "params": [{"key": "length", "label": "Length", "default": 14}]},
    "atr": {"name": "ATR", "group": "Oscillator", "overlay": False, "compute": _atr,
            "params": [{"key": "length", "label": "Length", "default": 14}]},
    "adx": {"name": "ADX / DMI", "group": "Oscillator", "overlay": False, "compute": _adx,
            "params": [{"key": "length", "label": "Length", "default": 14}]},
    "cci": {"name": "CCI", "group": "Oscillator", "overlay": False, "compute": _cci,
            "params": [{"key": "length", "label": "Length", "default": 20}]},
    "williams": {"name": "Williams %R", "group": "Oscillator", "overlay": False, "compute": _williams,
                 "params": [{"key": "length", "label": "Length", "default": 14}]},
    "roc": {"name": "ROC", "group": "Oscillator", "overlay": False, "compute": _roc,
            "params": [{"key": "length", "label": "Length", "default": 12}]},
    "mfi": {"name": "MFI", "group": "Oscillator", "overlay": False, "compute": _mfi,
            "params": [{"key": "length", "label": "Length", "default": 14}]},
    "obv": {"name": "OBV", "group": "Oscillator", "overlay": False, "compute": _obv, "params": []},
    "ao": {"name": "Awesome Oscillator", "group": "Oscillator", "overlay": False, "compute": _ao, "params": []},
}


def catalog_meta() -> List[Dict[str, Any]]:
    """Catalog without compute callables (JSON-serializable, for the UI)."""
    meta = []
    for ind_id, spec in CATALOG.items():
        meta.append({
            "id": ind_id,
            "name": spec["name"],
            "group": spec["group"],
            "overlay": spec["overlay"],
            "params": spec.get("params", []),
        })
    return meta


def compute(df: pd.DataFrame, specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute a list of indicator specs against an OHLCV DataFrame."""
    results = []
    for spec in specs:
        ind_id = spec.get("id")
        entry = CATALOG.get(ind_id)
        if entry is None:
            continue
        params = spec.get("params", {}) or {}
        try:
            plots = entry["compute"](df, params)
        except Exception as exc:  # noqa: BLE001 - surface a per-indicator error
            results.append({"id": ind_id, "name": entry["name"], "overlay": entry["overlay"],
                            "error": str(exc), "plots": []})
            continue
        results.append({
            "id": ind_id,
            "name": entry["name"],
            "overlay": entry["overlay"],
            "plots": plots,
        })
    return results
