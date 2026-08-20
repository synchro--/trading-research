"""Supertrend(3.0, 10) long-only — mirror of supertrend_strategy.pine.

Entry: direction flips to uptrend (TV convention -1). Flatten: flips to downtrend.
Risk: v1.2 stepped Chandelier so only the entry engine differs from ema_pullback.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import StrategyConfig, stepped_chandelier_trail


class SupertrendLong:
    name = "supertrend"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None,
                 factor: float = 3.0, period: int = 10):
        self.cfg = cfg or StrategyConfig()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)
        self.st, self.direction = ta.supertrend(h, l, c, factor, period)
        self._last_entry: float | None = None
        self._hh: float = float("-inf")

    def _flip_up(self, i: int) -> bool:
        if i == 0 or np.isnan(self.direction[i]) or np.isnan(self.direction[i - 1]):
            return False
        return self.direction[i] == -1.0 and self.direction[i - 1] == 1.0

    def _flip_down(self, i: int) -> bool:
        if i == 0 or np.isnan(self.direction[i]) or np.isnan(self.direction[i - 1]):
            return False
        return self.direction[i] == 1.0 and self.direction[i - 1] == -1.0

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]):
            return False
        return self._flip_up(i)

    def should_flatten(self, i: int) -> bool:
        return self._flip_down(i)

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
