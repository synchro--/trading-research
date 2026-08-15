"""Donchian / Turtle system-2 long: 55-day high in, 20-day low out.

Chart signal: close breaks above the prior 55-day high. Exit when price loses the
prior 20-day low. Sizing uses 2×ATR (the published Turtle N-stop), not a length
search on this universe. No RSI, no 50/200 — this is breakout, not pullback.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.risk import SharedRisk


class Donchian55:
    name = "donchian_55_20"

    def __init__(self, bars: list[Bar], risk: SharedRisk | None = None):
        self.risk = risk or SharedRisk()
        self.cfg = self.risk
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.low = l
        self.atr = ta.atr(h, l, c, self.risk.atr_len)
        # Prior window only (exclude today) so the break is evaluated on a closed bar.
        self.prior_55_high = np.roll(ta.rolling_max(h, 55), 1)
        self.prior_55_high[0] = np.nan
        self.prior_20_low = np.roll(ta.rolling_min(l, 20), 1)
        self.prior_20_low[0] = np.nan

    def long_signal(self, i: int) -> bool:
        ch = self.prior_55_high[i]
        if np.isnan(ch) or np.isnan(self.atr[i]):
            return False
        return bool(self.close[i] > ch and self.close[i - 1] <= ch)

    def should_flatten(self, i: int) -> bool:
        return False  # 20-day low is the trail, not a separate flatten

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(2.0 * atr)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        floor = self.prior_20_low[i]
        stop = entry_px - initial_risk
        if np.isnan(floor):
            return stop
        return float(max(stop, floor))
