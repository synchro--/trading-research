"""EMA Pullback v1 signal with volatility-targeted sizing.

Same entries, same ATR trail, same exits as v1 — only the position size changes,
from 1.5%-risk-per-trade to a 20% annualized vol target (MOP-style, capped at 1x).
Exists to separate two questions that 1.5%-risk sizing conflates: is the *signal*
good, and is the *capital deployment* sane? v1 as frozen deploys ~15-20% of equity
per trade, so its headline CAGR says more about sizing than about edge.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1
from backtesting.strategies.risk import Sizing


class EmaPullbackVolTarget(EmaPullbackV1):
    name = "ema_pullback_vt"
    sizing = Sizing(mode="voltarget", value=0.20)
    uses_trail = True

    def __init__(self, bars: list[Bar]):
        super().__init__(bars)
        self.vol = ta.realized_vol(np.array([b.c for b in bars], dtype=float), 60)

    def realized_vol(self, i: int) -> float:
        v = self.vol[i]
        return 0.0 if np.isnan(v) else float(v)
