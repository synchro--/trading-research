"""Time-series momentum, Moskowitz/Ooi/Pedersen (2012), long-only daily proxy.

Published rule: sign of the trailing 12-month excess return decides the position,
re-checked monthly, with position size inversely proportional to ex-ante volatility
(the paper targets 40% annualized on futures; a cash equity account cannot lever
that far, so this targets 20% and caps at 1x).

Long-only here because DESIGN.md rules out shorts. Checked on the first bar of each
month using data through that close, filled the next open — no calendar lookahead.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.risk import SharedRisk, Sizing

VOL_TARGET = 0.20


class Tsmom12M:
    name = "tsmom_12m"
    sizing = Sizing(mode="voltarget", value=VOL_TARGET)
    uses_trail = False

    def __init__(self, bars: list[Bar]):
        self.risk = SharedRisk()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.mom12 = ta.pct_change_n(c, 252)
        self.atr = ta.atr(h, l, c, self.risk.atr_len)
        self.vol = ta.realized_vol(c, 60)
        self.month_start = np.zeros(len(bars), dtype=bool)
        for i in range(1, len(bars)):
            self.month_start[i] = bars[i].t[:7] != bars[i - 1].t[:7]

    def long_signal(self, i: int) -> bool:
        if not self.month_start[i] or np.isnan(self.mom12[i]):
            return False
        return bool(self.mom12[i] > 0.0 and self.realized_vol(i) > 0.0)

    def should_flatten(self, i: int) -> bool:
        if not self.month_start[i] or np.isnan(self.mom12[i]):
            return False
        return bool(self.mom12[i] <= 0.0)

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
