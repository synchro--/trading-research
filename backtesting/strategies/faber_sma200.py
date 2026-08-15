"""Faber (2007) moving-average timing model, daily 200-SMA version.

Published rule: long while price is above its long-term SMA, cash otherwise. The
paper uses a 10-month SMA on monthly closes; the daily 200-SMA is the equivalent
Faber cites as the starting point. No stop, fully invested, price-only.

This is the literature's canonical Sharpe improver: same-ish return as buy-and-hold
with materially lower volatility and drawdown.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.risk import SharedRisk, Sizing


class FaberSma200:
    name = "faber_sma200"
    sizing = Sizing(mode="equity", value=1.0)
    uses_trail = False

    def __init__(self, bars: list[Bar]):
        self.risk = SharedRisk()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.sma200 = ta.sma(c, 200)
        self.atr = ta.atr(h, l, c, self.risk.atr_len)
        self.vol = ta.realized_vol(c, 60)
        self._above = ta.crossover(c, self.sma200)
        self._below = ta.crossunder(c, self.sma200)

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.sma200[i]):
            return False
        return bool(self._above[i])

    def should_flatten(self, i: int) -> bool:
        return bool(self._below[i])

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(self.risk.atr_base_mult * atr)

    def realized_vol(self, i: int) -> float:
        v = self.vol[i]
        return 0.0 if np.isnan(v) else float(v)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        return float("-inf")
