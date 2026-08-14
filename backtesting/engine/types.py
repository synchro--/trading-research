from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


@dataclass
class Position:
    qty: float
    entry_px: float
    entry_time: str
    initial_risk: float
    trail: float


@dataclass(frozen=True)
class Fill:
    t: str
    side: str  # buy | sell
    px: float
    qty: float
    reason: str


@dataclass(frozen=True)
class Trade:
    entry_time: str
    entry_px: float
    exit_time: str
    exit_px: float
    qty: float
    r_multiple: float
    pnl: float
    reason: str  # trail | regime
    hold_bars: int


@dataclass
class EquityPoint:
    t: str
    equity: float
    drawdown: float


@dataclass
class PendingEntry:
    initial_risk: float
    qty: float


@dataclass
class RunResult:
    symbol: str
    trades: list[Trade]
    equity: list[EquityPoint]
    fills: list[Fill]
    open_position: Optional[Position]
    source: str = ""
