"""Shared risk / sizing primitives. Do not retune per symbol."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SharedRisk:
    atr_len: int = 14
    atr_base_mult: float = 3.5
    trail_tight_mult: float = 2.0
    profit_threshold: float = 1.5
    risk_pct: float = 1.5


@dataclass(frozen=True)
class Sizing:
    """How much to buy.

    risk      -> value = % of equity risked across the initial stop distance
    equity    -> value = fraction of equity deployed (1.0 = fully invested)
    voltarget -> value = annualized vol target; qty scales by target / realized vol
    """

    mode: str = "risk"
    value: float = 1.5
    max_exposure: float = 1.0  # cash account: never lever above 1x


def atr_trail(close: float, atr: float, entry_px: float, initial_risk: float, risk: SharedRisk) -> float:
    r = (close - entry_px) / initial_risk if initial_risk else 0.0
    mult = risk.trail_tight_mult if r >= risk.profit_threshold else risk.atr_base_mult
    return float(close - mult * atr)


def size_qty(sizing: Sizing, equity: float, price: float, initial_risk: float, realized_vol: float) -> float:
    if price <= 0 or equity <= 0:
        return 0.0
    if sizing.mode == "risk":
        if initial_risk <= 0:
            return 0.0
        qty = equity * (sizing.value / 100.0) / initial_risk
    elif sizing.mode == "equity":
        qty = equity * sizing.value / price
    elif sizing.mode == "voltarget":
        if realized_vol <= 0:
            return 0.0
        frac = sizing.value / realized_vol
        qty = equity * frac / price
    else:
        raise ValueError(f"unknown sizing mode {sizing.mode!r}")
    cap = equity * sizing.max_exposure / price
    return float(min(qty, cap))
