"""SMA50 reclaim twin of ema_pullback — same v1.2 stepped Chandelier risk."""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import StrategyConfig, stepped_chandelier_trail


class Sma50Reclaim:
    name = "sma50_reclaim"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None):
        self.cfg = cfg or StrategyConfig()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.sma50 = ta.sma(c, self.cfg.fast_len)
        self.sma200 = ta.sma(c, self.cfg.slow_len)
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)
        self.reclaim = ta.crossover(c, self.sma50)
        self.regime_break = ta.crossunder(self.sma50, self.sma200)
        self._last_entry: float | None = None
        self._hh: float = float("-inf")

    def bull_regime(self, i: int) -> bool:
        s50, s200 = self.sma50[i], self.sma200[i]
        if np.isnan(s50) or np.isnan(s200):
            return False
        if i == 0 or np.isnan(self.sma50[i - 1]) or np.isnan(self.sma200[i - 1]):
            return False
        return bool(s50 > s200 and self.sma50[i - 1] > self.sma200[i - 1])

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]):
            return False
        return self.bull_regime(i) and bool(self.reclaim[i])

    def should_flatten(self, i: int) -> bool:
        return bool(self.regime_break[i])

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
            close=float(self.close[i]),
            high=float(self.high[i]),
            atr=float(self.atr[i]),
            entry_px=entry_px,
            initial_risk=initial_risk,
            hh=self._hh,
            be_r=self.cfg.be_r,
            trail_r=self.cfg.trail_r,
            chandelier_mult=self.cfg.chandelier_mult,
        )
        return cand
