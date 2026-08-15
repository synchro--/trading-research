"""RSI dip in a 200-EMA uptrend. Textbook: RSI(14) crosses 40 from below while close > EMA200.

Chart signal: lime when RSI reclaims 40 above the 200. Same 3.5→2.0 ATR trail as v1
so the only structural change is the entry (RSI vs EMA50 reclaim). Flatten if close
loses the 200. Lengths are the published defaults, not fit to this universe.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.risk import SharedRisk, atr_trail


class RsiTrendDip:
    name = "rsi_trend_dip"

    def __init__(self, bars: list[Bar], risk: SharedRisk | None = None):
        self.risk = risk or SharedRisk()
        self.cfg = self.risk
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.ema200 = ta.ema(c, 200)
        self.atr = ta.atr(h, l, c, self.risk.atr_len)
        self.rsi = ta.rsi(c, 14)
        self._rsi_cross_40 = ta.crossover(self.rsi, np.full(len(c), 40.0))
        self._lose_200 = ta.crossunder(c, self.ema200)

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.ema200[i]) or np.isnan(self.atr[i]) or np.isnan(self.rsi[i]):
            return False
        return bool(self.close[i] > self.ema200[i] and self._rsi_cross_40[i])

    def should_flatten(self, i: int) -> bool:
        return bool(self._lose_200[i])

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(self.risk.atr_base_mult * atr)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        return atr_trail(self.close[i], float(self.atr[i]), entry_px, initial_risk, self.risk)
