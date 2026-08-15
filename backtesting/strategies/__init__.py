"""Engine strategies. Do not import etf_bottom_finder here."""
from __future__ import annotations

from backtesting.engine.types import Bar
from backtesting.strategies.donchian_55 import Donchian55
from backtesting.strategies.ema50_reclaim import EmaReclaimNaked
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1
from backtesting.strategies.rsi_trend_dip import RsiTrendDip

REGISTRY = {
    "ema_pullback": EmaPullbackV1,
    "ema50_reclaim": EmaReclaimNaked,
    "rsi_trend_dip": RsiTrendDip,
    "donchian_55_20": Donchian55,
}


def build(name: str, bars: list[Bar]):
    key = name.strip().lower()
    if key not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"unknown strategy {name!r}. choose: {known}")
    return REGISTRY[key](bars)
