"""Engine strategies. Do not import etf_bottom_finder here."""
from __future__ import annotations

from backtesting.engine.types import Bar
from backtesting.strategies.connors_rsi2 import ConnorsRsi2
from backtesting.strategies.connors_rsi2_trail import ConnorsRsi2Trail
from backtesting.strategies.donchian_55 import Donchian55
from backtesting.strategies.ema50_reclaim import EmaReclaimNaked
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1
from backtesting.strategies.ema_pullback_voltarget import EmaPullbackVolTarget
from backtesting.strategies.faber_sma200 import FaberSma200, FaberSma200Daily
from backtesting.strategies.rsi_trend_dip import RsiTrendDip
from backtesting.strategies.tsmom_12m import Tsmom12M

REGISTRY = {
    "ema_pullback": EmaPullbackV1,
    "ema50_reclaim": EmaReclaimNaked,
    "rsi_trend_dip": RsiTrendDip,
    "donchian_55_20": Donchian55,
    "ema_pullback_vt": EmaPullbackVolTarget,
    "connors_rsi2": ConnorsRsi2,
    "connors_rsi2_trail": ConnorsRsi2Trail,
    "faber_sma200": FaberSma200,
    "faber_sma200_daily": FaberSma200Daily,
    "tsmom_12m": Tsmom12M,
}


def build(name: str, bars: list[Bar]):
    key = name.strip().lower()
    if key not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"unknown strategy {name!r}. choose: {known}")
    return REGISTRY[key](bars)
