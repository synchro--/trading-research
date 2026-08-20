"""Confluence v2 — the combination that survived component A/B on the entry book.

Two literature-grounded entry paths inside one regime:

  Regime      EMA50 > EMA200 (no new longs otherwise, flatten on death cross)
  Trigger A   close crosses back above EMA50 (pullback resumption — v1.2 base)
  Trigger B   LazyBear squeeze release with positive momentum, valid only if
              close > AVWAP anchored at the last confirmed swing low.
              Breakout entries need location context (Shannon's AVWAP usage);
              reclaims already have it by construction, so AVWAP does not gate A.
  Exit        v1.2 stepped Chandelier (hard 3.5 ATR -> BE @ 1R -> HH-3 ATR @ 2R)

Rejected in testing (see research/indicator_suite.md):
  - Ichimoku cloud gate: too laggy on daily bars (med Sharpe 0.38)
  - AVWAP as a hard filter on all entries: OOS-unstable (0.22 in 2015-2020)
  - RSI divergence gate: regime luck, hurts the 2015-2020 half
  - Lorentzian kNN, SMC BOS, Supertrend as entries: dominated by EMA reclaim
"""
from __future__ import annotations

import numpy as np

from backtesting.engine.types import Bar
from backtesting.strategies.avwap import anchored_vwap_swing_low
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1, StrategyConfig
from backtesting.strategies.squeeze_momentum import SqueezeMomentum


class ConfluenceV2(EmaPullbackV1):
    name = "confluence_v2"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None,
                 avwap_pivot_len: int = 10):
        super().__init__(bars, cfg)
        sq = SqueezeMomentum(bars, cfg)
        self.sqz_on = sq.sqz_on
        self.val = sq.val
        self.avwap = anchored_vwap_swing_low(bars, avwap_pivot_len)

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]) or not self.bull_regime(i):
            return False
        if bool(self.reclaim[i]):
            return True
        if i == 0:
            return False
        released = bool(self.sqz_on[i - 1]) and not bool(self.sqz_on[i])
        if not (released and not np.isnan(self.val[i]) and self.val[i] > 0):
            return False
        return not np.isnan(self.avwap[i]) and bool(self.close[i] > self.avwap[i])
