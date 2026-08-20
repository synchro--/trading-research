"""Ichimoku Cloud (9/26/52, Hosoda), long-only — mirror of ichimoku_suite.pine.

Classic literature rule set:
  entry   TK cross (tenkan over kijun) while price is above the cloud,
          with chikou confirmation (close > close 26 bars ago)
  flatten close crosses below the cloud bottom (regime off)
Cloud at bar i uses spans computed 26 bars earlier (the displacement), so
nothing references future bars. Risk: v1.2 stepped Chandelier.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import StrategyConfig, stepped_chandelier_trail


class IchimokuCloud:
    name = "ichimoku"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None,
                 conversion: int = 9, base: int = 26, span_b_len: int = 52,
                 displacement: int = 26):
        self.cfg = cfg or StrategyConfig()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)

        n = len(bars)
        tenkan = ta.donchian_mid(h, l, conversion)
        kijun = ta.donchian_mid(h, l, base)
        span_a = (tenkan + kijun) / 2.0
        span_b = ta.donchian_mid(h, l, span_b_len)

        # Cloud at bar i = spans computed `displacement` bars ago
        cloud_top = np.full(n, np.nan, dtype=float)
        cloud_bot = np.full(n, np.nan, dtype=float)
        cloud_top[displacement:] = np.maximum(span_a[:-displacement], span_b[:-displacement])
        cloud_bot[displacement:] = np.minimum(span_a[:-displacement], span_b[:-displacement])

        tk_up = ta.crossover(tenkan, kijun)
        chikou = np.zeros(n, dtype=bool)
        chikou[displacement:] = c[displacement:] > c[:-displacement]

        self.long_sig = np.zeros(n, dtype=bool)
        self.flat_sig = np.zeros(n, dtype=bool)
        for i in range(1, n):
            if np.isnan(cloud_top[i]) or np.isnan(cloud_bot[i]):
                continue
            self.long_sig[i] = bool(tk_up[i]) and c[i] > cloud_top[i] and bool(chikou[i])
            prev_bot = cloud_bot[i - 1]
            self.flat_sig[i] = (not np.isnan(prev_bot)
                                and c[i - 1] >= prev_bot and c[i] < cloud_bot[i])
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
