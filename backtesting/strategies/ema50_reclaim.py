"""Naked EMA50 reclaim in a 50/200 bull regime — v1 without the RSI band.

Chart signal: same as v1 (price crosses back over EMA50 while 50>200) but no RSI
gate. Tests whether the RSI filter is doing work, without searching new lengths.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1, StrategyConfig
from backtesting.strategies.risk import SharedRisk, atr_trail


class EmaReclaimNaked(EmaPullbackV1):
    name = "ema50_reclaim"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None):
        super().__init__(bars, cfg)
        self.risk = SharedRisk()

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]):
            return False
        return self.bull_regime(i) and bool(self.reclaim[i])

    def should_flatten(self, i: int) -> bool:
        return bool(self.regime_break[i])

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        return atr_trail(self.close[i], float(self.atr[i]), entry_px, initial_risk, self.risk)
