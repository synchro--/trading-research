"""Connors RSI(2) entry with an ATR trailing exit instead of the 5-day SMA exit.

Not a new idea and not a parameter search: StockCharts' writeup of the RSI(2) system
notes the 5-SMA exit leaves trends on the table and suggests "setting a trailing stop
or employing the Parabolic SAR ... to ensure that a position remains as long as the
trend extends". The measured weakness of plain Connors here is exactly that — a Sharpe
near 0.5 while in the market only ~9% of the time, so it cannot compound.

Entry is the published Connors rule, verbatim. The exit is DESIGN.md's frozen adaptive
ATR trail, unchanged. This isolates one hypothesis: does holding the winners longer
convert Connors' entry edge into a better risk-adjusted return?
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.connors_rsi2 import ConnorsRsi2
from backtesting.strategies.risk import Sizing, atr_trail


class ConnorsRsi2Trail(ConnorsRsi2):
    name = "connors_rsi2_trail"
    sizing = Sizing(mode="voltarget", value=0.20)
    uses_trail = True

    def __init__(self, bars: list[Bar]):
        super().__init__(bars)
        c = np.array([b.c for b in bars], dtype=float)
        self.ema200 = ta.ema(c, 200)

    def should_flatten(self, i: int) -> bool:
        """Trend break only; the ATR trail handles ordinary exits."""
        if np.isnan(self.ema200[i]):
            return False
        return bool(self.close[i] < self.ema200[i])

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return float("-inf")
        return atr_trail(self.close[i], float(atr), entry_px, initial_risk, self.risk)
