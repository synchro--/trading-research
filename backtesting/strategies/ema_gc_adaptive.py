"""EMA Pullback Swing v1.2 — DESIGN.md §3. Do not port etf_bottom_finder.

Entry: EMA50>EMA200 + close crossover EMA50 (RSI gate removed).

ATR risk (v1.2 stepped Chandelier):
  - initial stop = entry − 3.5×ATR(14) (sizing unchanged)
  - while R < 1: do not ratchet from close (hard initial stop only)
  - at R ≥ 1: lock breakeven (trail floor = entry)
  - at R ≥ 2: LeBeau Chandelier trail = HH_since_entry − 3.0×ATR
"""
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
    atr_base_mult: float = 3.5
    be_r: float = 1.0
    trail_r: float = 2.0
    chandelier_mult: float = 3.0
    risk_pct: float = 1.5


def stepped_chandelier_trail(
    *,
    close: float,
    high: float,
    atr: float,
    entry_px: float,
    initial_risk: float,
    hh: float,
    be_r: float,
    trail_r: float,
    chandelier_mult: float,
) -> tuple[float, float]:
    """Return (trail_candidate, updated_hh).

    Returning -inf means "do not ratchet" so the broker keeps the initial stop.
    """
    if atr <= 0 or np.isnan(atr) or initial_risk <= 0:
        return float("-inf"), hh
    hh = max(hh, high)
    r = (close - entry_px) / initial_risk
    if r < be_r:
        return float("-inf"), hh
    if r < trail_r:
        return float(entry_px), hh
    return float(max(entry_px, hh - chandelier_mult * atr)), hh


class EmaPullbackV1:
    name = "ema_pullback"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None):
        self.cfg = cfg or StrategyConfig()
        self.bars = bars
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.ema50 = ta.ema(c, self.cfg.fast_len)
        self.ema200 = ta.ema(c, self.cfg.slow_len)
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)
        self.reclaim = ta.crossover(c, self.ema50)
        self.regime_break = ta.crossunder(self.ema50, self.ema200)
        self._last_entry: float | None = None
        self._hh: float = float("-inf")

    def bull_regime(self, i: int) -> bool:
        e50, e200 = self.ema50[i], self.ema200[i]
        if np.isnan(e50) or np.isnan(e200):
            return False
        if i == 0 or np.isnan(self.ema50[i - 1]) or np.isnan(self.ema200[i - 1]):
            return False
        return bool(e50 > e200 and self.ema50[i - 1] > self.ema200[i - 1])

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]):
            return False
        return self.bull_regime(i) and bool(self.reclaim[i])

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
            close=float(self.close[i]),
            high=float(self.high[i]),
            atr=float(self.atr[i]),
            entry_px=entry_px,
            initial_risk=initial_risk,
            hh=self._hh,
            be_r=self.cfg.be_r,
            trail_r=self.cfg.trail_r,
            chandelier_mult=self.cfg.chandelier_mult,
        )
        return cand
