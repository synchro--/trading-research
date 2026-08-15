"""Connors & Alvarez RSI(2) mean reversion, long only.

Published rules (Connors, "Short Term Trading Strategies That Work"):
  entry  close > SMA(200) and close < SMA(5) and RSI(2) < 10  -> buy next open
  exit   close > SMA(5)                                       -> sell next open
  stop   none (Connors reports stops hurt this system)

Fully invested while in the trade, so it is a market-timing overlay rather than a
risk-per-trade swing book. Thresholds are the published ones, not searched here.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.risk import SharedRisk, Sizing


class ConnorsRsi2:
    name = "connors_rsi2"
    sizing = Sizing(mode="equity", value=1.0)
    uses_trail = False

    def __init__(self, bars: list[Bar]):
        self.risk = SharedRisk()
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.sma200 = ta.sma(c, 200)
        self.sma5 = ta.sma(c, 5)
        self.rsi2 = ta.rsi(c, 2)
        self.atr = ta.atr(h, l, c, self.risk.atr_len)
        self.vol = ta.realized_vol(c, 60)

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.sma200[i]) or np.isnan(self.sma5[i]) or np.isnan(self.rsi2[i]):
            return False
        return bool(
            self.close[i] > self.sma200[i]
            and self.close[i] < self.sma5[i]
            and self.rsi2[i] < 10.0
        )

    def should_flatten(self, i: int) -> bool:
        if np.isnan(self.sma5[i]):
            return False
        return bool(self.close[i] > self.sma5[i])

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(self.risk.atr_base_mult * atr)  # R yardstick only; no stop order

    def realized_vol(self, i: int) -> float:
        v = self.vol[i]
        return 0.0 if np.isnan(v) else float(v)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        return float("-inf")
