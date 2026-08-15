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


def crossover(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] > b[1:]) & (a[:-1] <= b[:-1])
    return out


def crossunder(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.zeros(len(a), dtype=bool)
    out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    return out
