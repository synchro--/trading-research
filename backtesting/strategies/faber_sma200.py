"""Faber (2007) moving-average timing model.

Published rule: at each MONTH END, long if price is above its 10-month SMA, cash
otherwise. No stop, fully invested, price-only. The monthly sampling is not an
incidental detail of the paper — it is what keeps the rule from whipsawing.

Two variants are registered:

  FaberSma200        the published rule, checked monthly (200 trading days ~ 10 months)
  FaberSma200Daily   the same threshold checked every bar

The daily variant is kept because the gap between them is the whole lesson. Over
2001-2026 on JPM the daily check round-trips 118 times and posts a 74% drawdown —
worse than buy-and-hold — while the monthly check trades a fraction as often.
Sampling frequency, not the moving-average length, is what makes this system work.

Checked on the first bar of each month using data through that close and filled the
next open, so no calendar lookahead.
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
    monthly = True

    def __init__(self, bars: list[Bar]):
        self.risk = SharedRisk()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.sma200 = ta.sma(c, 200)
        self.atr = ta.atr(h, l, c, self.risk.atr_len)
        self.vol = ta.realized_vol(c, 60)
        self.month_start = np.zeros(len(bars), dtype=bool)
        for i in range(1, len(bars)):
            self.month_start[i] = bars[i].t[:7] != bars[i - 1].t[:7]

    def _rebalance_bar(self, i: int) -> bool:
        return bool(self.month_start[i]) if self.monthly else True

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.sma200[i]) or not self._rebalance_bar(i):
            return False
        return bool(self.close[i] > self.sma200[i])

    def should_flatten(self, i: int) -> bool:
        if np.isnan(self.sma200[i]) or not self._rebalance_bar(i):
            return False
        return bool(self.close[i] < self.sma200[i])

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


class FaberSma200Daily(FaberSma200):
    name = "faber_sma200_daily"
    monthly = False
