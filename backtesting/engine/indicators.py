"""Pine-compatible EMA / RMA / ATR / RSI (TradingView ta.*)."""
from __future__ import annotations

import numpy as np


def ema(src: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(src), np.nan, dtype=float)
    if len(src) < length:
        return out
    alpha = 2.0 / (length + 1)
    out[length - 1] = float(np.mean(src[:length]))
    for i in range(length, len(src)):
        out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1]
    return out


def rma(src: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(src), np.nan, dtype=float)
    start = 0
    while start < len(src) and np.isnan(src[start]):
        start += 1
    if start + length > len(src):
        return out
    alpha = 1.0 / length
    out[start + length - 1] = float(np.mean(src[start:start + length]))
    for i in range(start + length, len(src)):
        out[i] = alpha * src[i] + (1.0 - alpha) * out[i - 1]
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    tr = np.empty(len(close), dtype=float)
    tr[0] = high[0] - low[0]
    prev = close[:-1]
    tr[1:] = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - prev), np.abs(low[1:] - prev)),
    )
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    return rma(true_range(high, low, close), length)


def rsi(close: np.ndarray, length: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    delta[0] = np.nan
    gain = np.where(np.isnan(delta), np.nan, np.clip(delta, 0.0, None))
    loss = np.where(np.isnan(delta), np.nan, np.clip(-delta, 0.0, None))
    avg_gain = rma(gain, length)
    avg_loss = rma(loss, length)
    out = np.full(len(close), np.nan, dtype=float)
    for i in range(len(close)):
        g, l = avg_gain[i], avg_loss[i]
        if np.isnan(g) or np.isnan(l):
            continue
        if l == 0 and g == 0:
            out[i] = 50.0
        elif l == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + g / l)
    return out


def periods_per_year(dates: list[str]) -> int:
    """252 for exchange-traded names, 365 for instruments that trade every day.

    Crypto has no weekends, so annualizing its daily stats with 252 overstates
    return and understates volatility. Infer the calendar from the bars instead.
    """
    if len(dates) < 30:
        return 252
    from datetime import date

    span = (date.fromisoformat(dates[-1][:10]) - date.fromisoformat(dates[0][:10])).days
    if span <= 0:
        return 252
    per_year = len(dates) / (span / 365.25)
    return 365 if per_year > 300 else 252


def sma(src: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(src), np.nan, dtype=float)
    if length <= 0 or len(src) < length:
        return out
    csum = np.cumsum(np.insert(src, 0, 0.0))
    out[length - 1 :] = (csum[length:] - csum[:-length]) / length
    return out


def realized_vol(close: np.ndarray, length: int = 60, periods: int = 252) -> np.ndarray:
    """Annualized stdev of daily simple returns over a trailing window."""
    out = np.full(len(close), np.nan, dtype=float)
    rets = np.full(len(close), np.nan, dtype=float)
    rets[1:] = close[1:] / close[:-1] - 1.0
    for i in range(length, len(close)):
        w = rets[i - length + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = float(np.std(w, ddof=1) * np.sqrt(periods))
    return out


def pct_change_n(close: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(close), np.nan, dtype=float)
    if len(close) <= length:
        return out
    out[length:] = close[length:] / close[:-length] - 1.0
    return out


def rolling_max(src: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(src), np.nan, dtype=float)
    if length <= 0 or len(src) < length:
        return out
    for i in range(length - 1, len(src)):
        out[i] = float(np.max(src[i - length + 1 : i + 1]))
    return out


def rolling_min(src: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(src), np.nan, dtype=float)
    if length <= 0 or len(src) < length:
        return out
    for i in range(length - 1, len(src)):
        out[i] = float(np.min(src[i - length + 1 : i + 1]))
    return out


def stdev(src: np.ndarray, length: int) -> np.ndarray:
    """Population stdev over a rolling window (Pine ta.stdev)."""
    out = np.full(len(src), np.nan, dtype=float)
    for i in range(length - 1, len(src)):
        w = src[i - length + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = float(np.std(w))
    return out


def linreg(src: np.ndarray, length: int, offset: int = 0) -> np.ndarray:
    """Pine ta.linreg: value of the least-squares line at the window's last bar."""
    out = np.full(len(src), np.nan, dtype=float)
    x = np.arange(length, dtype=float)
    x_mean = x.mean()
    denom = float(((x - x_mean) ** 2).sum())
    for i in range(length - 1, len(src)):
        w = src[i - length + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        slope = float(((x - x_mean) * (w - w.mean())).sum()) / denom
        intercept = float(w.mean()) - slope * x_mean
        out[i] = intercept + slope * (length - 1 - offset)
    return out


def macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(np.where(np.isnan(line), 0.0, line), signal)
    sig[np.isnan(line)] = np.nan
    return line, sig, line - sig


def supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               factor: float = 3.0, period: int = 10):
    """TradingView ta.supertrend. Returns (st, direction).

    direction follows the TV convention: -1 = uptrend (st below price),
    +1 = downtrend. Long entry on flip to -1.
    """
    n = len(close)
    hl2 = (high + low) / 2.0
    a = atr(high, low, close, period)
    upper = hl2 + factor * a
    lower = hl2 - factor * a
    st = np.full(n, np.nan, dtype=float)
    direction = np.full(n, np.nan, dtype=float)
    f_upper = np.full(n, np.nan, dtype=float)
    f_lower = np.full(n, np.nan, dtype=float)
    started = False
    for i in range(n):
        if np.isnan(a[i]):
            continue
        if not started:
            f_upper[i], f_lower[i] = upper[i], lower[i]
            direction[i] = 1.0
            st[i] = f_upper[i]
            started = True
            continue
        f_lower[i] = lower[i] if (lower[i] > f_lower[i - 1] or close[i - 1] < f_lower[i - 1]) else f_lower[i - 1]
        f_upper[i] = upper[i] if (upper[i] < f_upper[i - 1] or close[i - 1] > f_upper[i - 1]) else f_upper[i - 1]
        if st[i - 1] == f_upper[i - 1]:
            direction[i] = -1.0 if close[i] > f_upper[i] else 1.0
        else:
            direction[i] = 1.0 if close[i] < f_lower[i] else -1.0
        st[i] = f_lower[i] if direction[i] == -1.0 else f_upper[i]
    return st, direction


def pivot_low(low: np.ndarray, left: int, right: int) -> np.ndarray:
    """Confirmed pivot lows. out[i] = index of the pivot bar confirmed AT bar i
    (i.e. the pivot is at i - right), else -1. No lookahead: usable from bar i."""
    n = len(low)
    out = np.full(n, -1, dtype=int)
    for i in range(left + right, n):
        p = i - right
        w = low[p - left : p + right + 1]
        if np.any(np.isnan(w)):
            continue
        if low[p] == np.min(w) and np.sum(w == low[p]) == 1:
            out[i] = p
    return out


def pivot_high(high: np.ndarray, left: int, right: int) -> np.ndarray:
    n = len(high)
    out = np.full(n, -1, dtype=int)
    for i in range(left + right, n):
        p = i - right
        w = high[p - left : p + right + 1]
        if np.any(np.isnan(w)):
            continue
        if high[p] == np.max(w) and np.sum(w == high[p]) == 1:
            out[i] = p
    return out


def donchian_mid(high: np.ndarray, low: np.ndarray, length: int) -> np.ndarray:
    return (rolling_max(high, length) + rolling_min(low, length)) / 2.0


def crossover(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return out


def crossunder(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    return out
