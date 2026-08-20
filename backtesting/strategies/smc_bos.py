"""Smart Money Concepts structure breaks, long-only — the testable core of
smart_money_concept.pine (LuxAlgo). Drawing/visual layers are not portable.

Structure detection follows LuxAlgo's internal-structure logic: a swing high/low
is confirmed `length` bars after the extreme (default 5 = LuxAlgo internal).
Long entry on a bullish BOS or CHoCH (close crosses above the last confirmed
swing high). Flatten on bearish CHoCH (close crosses below the last confirmed
swing low). Risk: v1.2 stepped Chandelier.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import StrategyConfig, stepped_chandelier_trail


class SmcBos:
    name = "smc_bos"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None, length: int = 5):
        self.cfg = cfg or StrategyConfig()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)

        n = len(bars)
        ph = ta.pivot_high(h, length, length)
        pl = ta.pivot_low(l, length, length)

        self.long_sig = np.zeros(n, dtype=bool)
        self.flat_sig = np.zeros(n, dtype=bool)
        swing_high = np.nan   # last confirmed, not yet broken
        swing_low = np.nan
        trend = 0             # +1 bullish structure, -1 bearish
        for i in range(1, n):
            if ph[i] >= 0:
                swing_high = h[ph[i]]
            if pl[i] >= 0:
                swing_low = l[pl[i]]
            if not np.isnan(swing_high) and c[i - 1] <= swing_high < c[i]:
                # bullish BOS (trend already up) or CHoCH (reversal) — long either way
                self.long_sig[i] = True
                trend = 1
                swing_high = np.nan  # level consumed
            if not np.isnan(swing_low) and c[i - 1] >= swing_low > c[i]:
                self.flat_sig[i] = True
                trend = -1
                swing_low = np.nan
        self._last_entry: float | None = None
        self._hh: float = float("-inf")

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]):
            return False
        return bool(self.long_sig[i])

    def should_flatten(self, i: int) -> bool:
        return bool(self.flat_sig[i])

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(self.cfg.atr_base_mult * atr)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        if self._last_entry is None or abs(self._last_entry - entry_px) > 1e-9:
            self._hh = float(self.high[i])
            self._last_entry = entry_px
        cand, self._hh = stepped_chandelier_trail(
            close=float(self.close[i]), high=float(self.high[i]), atr=float(self.atr[i]),
            entry_px=entry_px, initial_risk=initial_risk, hh=self._hh,
            be_r=self.cfg.be_r, trail_r=self.cfg.trail_r,
            chandelier_mult=self.cfg.chandelier_mult,
        )
        return cand
