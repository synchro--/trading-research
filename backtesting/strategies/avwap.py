"""Anchored VWAP helpers — mirror of avwap_suite.pine (swing-low anchor).

anchored_vwap_swing_low: at each bar, the VWAP accumulated since the most
recently CONFIRMED swing low (pivot low with `length` bars each side, usable
only from the confirmation bar — no lookahead). Used by confluence_v2 as an
entry-quality filter: close above this line means the move off the last low is
supported by volume-weighted positioning (Brian Shannon's published usage).
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar


def anchored_vwap_swing_low(bars: list[Bar], length: int = 10) -> np.ndarray:
    h = np.array([b.h for b in bars], dtype=float)
    l = np.array([b.l for b in bars], dtype=float)
    c = np.array([b.c for b in bars], dtype=float)
    v = np.array([b.v for b in bars], dtype=float)
    v = np.where(v > 0, v, 1.0)  # some ETF feeds report zero volume days
    tp = (h + l + c) / 3.0
    pl = ta.pivot_low(l, length, length)

    n = len(bars)
    out = np.full(n, np.nan, dtype=float)
    anchor = -1
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        if pl[i] >= 0:
            # new confirmed pivot: re-anchor at the pivot bar, replaying the
            # bars between the pivot and now (all in the past at bar i)
            anchor = pl[i]
            cum_pv = float((tp[anchor : i + 1] * v[anchor : i + 1]).sum())
            cum_v = float(v[anchor : i + 1].sum())
        elif anchor >= 0:
            cum_pv += float(tp[i] * v[i])
            cum_v += float(v[i])
        if anchor >= 0 and cum_v > 0:
            out[i] = cum_pv / cum_v
    return out
