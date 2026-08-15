"""EMA Pullback Swing v1 — DESIGN.md §3. Do not port etf_bottom_finder."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar


@dataclass(frozen=True)
class StrategyConfig:
    fast_len: int = 50
    slow_len: int = 200
    atr_len: int = 14
    rsi_len: int = 14
    rsi_dip_look: int = 8
    rsi_dip_level: float = 50.0
    rsi_band_lo: float = 40.0
    rsi_band_hi: float = 65.0
    atr_base_mult: float = 3.5
    trail_tight_mult: float = 2.0
    profit_threshold: float = 1.5
    risk_pct: float = 1.5


class EmaPullbackV1:
    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None):
        self.cfg = cfg or StrategyConfig()
        self.bars = bars
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.ema50 = ta.ema(c, self.cfg.fast_len)
        self.ema200 = ta.ema(c, self.cfg.slow_len)
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)
        self.rsi = ta.rsi(c, self.cfg.rsi_len)
        self.reclaim = ta.crossover(c, self.ema50)
        self.regime_break = ta.crossunder(self.ema50, self.ema200)

    def bull_regime(self, i: int) -> bool:
        e50, e200 = self.ema50[i], self.ema200[i]
        if np.isnan(e50) or np.isnan(e200):
            return False
        if i == 0 or np.isnan(self.ema50[i - 1]) or np.isnan(self.ema200[i - 1]):
            return False
        return bool(e50 > e200 and self.ema50[i - 1] > self.ema200[i - 1])

    def rsi_had_dip(self, i: int) -> bool:
        look = self.cfg.rsi_dip_look
        lo = max(0, i - look + 1)
        window = self.rsi[lo : i + 1]
        if np.all(np.isnan(window)):
            return False
        return bool(np.nanmin(window) < self.cfg.rsi_dip_level)

    def long_signal(self, i: int) -> bool:
        rsi = self.rsi[i]
        if np.isnan(rsi) or np.isnan(self.atr[i]):
            return False
        in_band = self.cfg.rsi_band_lo <= rsi <= self.cfg.rsi_band_hi
        return (
            self.bull_regime(i)
            and bool(self.reclaim[i])
            and self.rsi_had_dip(i)
            and in_band
        )

    def should_flatten(self, i: int) -> bool:
        return bool(self.regime_break[i])

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(self.cfg.atr_base_mult * atr)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        close = self.close[i]
        atr = self.atr[i]
        r = (close - entry_px) / initial_risk if initial_risk else 0.0
        mult = (
            self.cfg.trail_tight_mult
            if r >= self.cfg.profit_threshold
            else self.cfg.atr_base_mult
        )
        return float(close - mult * atr)
