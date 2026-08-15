"""Shared risk defaults. Do not retune per symbol."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SharedRisk:
    atr_len: int = 14
    atr_base_mult: float = 3.5
    trail_tight_mult: float = 2.0
    profit_threshold: float = 1.5
    risk_pct: float = 1.5


def atr_trail(close: float, atr: float, entry_px: float, initial_risk: float, risk: SharedRisk) -> float:
    r = (close - entry_px) / initial_risk if initial_risk else 0.0
    mult = risk.trail_tight_mult if r >= risk.profit_threshold else risk.atr_base_mult
    return float(close - mult * atr)
