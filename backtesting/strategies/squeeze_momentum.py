"""LazyBear Squeeze Momentum release, long-only — mirror of squeeze_momentum_lazy.pine.

Entry: squeeze releases (BB inside KC yesterday, outside today) with positive
linreg momentum, gated by the EMA50>EMA200 bull regime (swing context; the raw
indicator has no directional filter of its own).
Risk: v1.2 stepped Chandelier. Faithful quirk kept: BB deviation uses multKC.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import StrategyConfig, stepped_chandelier_trail


class SqueezeMomentum:
    name = "squeeze_momentum"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None,
                 length: int = 20, mult_kc: float = 1.5):
        self.cfg = cfg or StrategyConfig()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)
        self.ema50 = ta.ema(c, self.cfg.fast_len)
        self.ema200 = ta.ema(c, self.cfg.slow_len)
        self.regime_break = ta.crossunder(self.ema50, self.ema200)

        basis = ta.sma(c, length)
        dev = mult_kc * ta.stdev(c, length)  # original LazyBear quirk: multKC on BB
        upper_bb, lower_bb = basis + dev, basis - dev
        tr = ta.true_range(h, l, c)
        rangema = ta.sma(tr, length)
        upper_kc = basis + rangema * mult_kc
        lower_kc = basis - rangema * mult_kc
        self.sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
        mid = (ta.rolling_max(h, length) + ta.rolling_min(l, length)) / 2.0
        anchor = (mid + ta.sma(c, length)) / 2.0
        self.val = ta.linreg(c - anchor, length, 0)
        self._last_entry: float | None = None
        self._hh: float = float("-inf")

    def bull_regime(self, i: int) -> bool:
        e50, e200 = self.ema50[i], self.ema200[i]
        if np.isnan(e50) or np.isnan(e200):
            return False
        return bool(e50 > e200)

    def long_signal(self, i: int) -> bool:
        if i == 0 or np.isnan(self.atr[i]) or np.isnan(self.val[i]):
            return False
        released = bool(self.sqz_on[i - 1]) and not bool(self.sqz_on[i])
        return released and self.val[i] > 0 and self.bull_regime(i)

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
            close=float(self.close[i]), high=float(self.high[i]), atr=float(self.atr[i]),
            entry_px=entry_px, initial_risk=initial_risk, hh=self._hh,
            be_r=self.cfg.be_r, trail_r=self.cfg.trail_r,
            chandelier_mult=self.cfg.chandelier_mult,
        )
        return cand
