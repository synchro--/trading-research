"""Alias kept for older compare JSON / docs — identical to ema_pullback after RSI removal."""
from __future__ import annotations

from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1, StrategyConfig


class EmaReclaimNaked(EmaPullbackV1):
    name = "ema50_reclaim"

    def __init__(self, bars, cfg: StrategyConfig | None = None):
        super().__init__(bars, cfg)
