"""Bar loop: T+1 open entries, prior-bar trail vs low, flatten next open."""
from __future__ import annotations

from backtesting.engine.broker import Broker
from backtesting.engine.types import Bar, EquityPoint, PendingEntry, RunResult
from backtesting.strategies import build
from backtesting.strategies.risk import Sizing, size_qty


def run(
    bars: list[Bar],
    *,
    symbol: str,
    start: str | None = None,
    initial_cash: float = 20_000.0,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    strategy: str = "ema_pullback",
    source: str = "",
    strat=None,
    warmup_bars: int = 0,
) -> RunResult:
    """warmup_bars: refuse to trade before this bar index, so slow indicators are
    warm. Symbols in a book start on different dates; without this, an SMA200 rule
    sits in NaN-cash while buy-and-hold is already long and the comparison is rigged.
    """
    if not bars:
        return RunResult(symbol=symbol, trades=[], equity=[], fills=[], open_position=None, source=source)

    strat = strat or build(strategy, bars)
    risk_pct = getattr(getattr(strat, "cfg", None), "risk_pct", None) or getattr(
        getattr(strat, "risk", None), "risk_pct", 1.5
    )
    sizing: Sizing = getattr(strat, "sizing", None) or Sizing(mode="risk", value=risk_pct)
    uses_trail: bool = getattr(strat, "uses_trail", True)
    broker = Broker(cash=initial_cash, commission_bps=commission_bps, slippage_bps=slippage_bps)

    pending_entry: PendingEntry | None = None
    pending_flatten = False
    equity: list[EquityPoint] = []
    peak = initial_cash

    for i, bar in enumerate(bars):
        broker.mark_bar(i)
        live = (start is None or bar.t[:10] >= start[:10]) and i >= warmup_bars

        if live and pending_flatten and broker.position is not None:
            broker.sell(bar.t, bar.o, "regime")
            pending_flatten = False
            pending_entry = None

        if live and pending_entry is not None and broker.position is None:
            broker.buy(
                bar.t,
                bar.o,
                pending_entry.qty,
                pending_entry.initial_risk,
                initial_trail=None if uses_trail else float("-inf"),
            )
        pending_entry = None

        if live and uses_trail and broker.position is not None:
            stop_px = broker.stop_fill_price(bar.o, bar.l)
            if stop_px is not None:
                broker.sell(bar.t, stop_px, "trail")
                pending_flatten = False

        pos = broker.position
        if pos is not None:
            if uses_trail:
                pos.trail = max(pos.trail, strat.trail_candidate(i, pos.entry_px, pos.initial_risk))
            if live and strat.should_flatten(i):
                pending_flatten = True
        elif live:
            if strat.long_signal(i):
                risk = strat.initial_risk(i)
                eq = broker.equity(bar.c)
                vol = getattr(strat, "realized_vol", None)
                qty = size_qty(sizing, eq, bar.c, risk, vol(i) if vol else 0.0)
                if qty > 0:
                    pending_entry = PendingEntry(initial_risk=risk, qty=qty)

        if live:
            eq = broker.equity(bar.c)
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak else 0.0
            equity.append(EquityPoint(t=bar.t, equity=eq, drawdown=dd))

    return RunResult(
        symbol=symbol,
        trades=broker.trades,
        equity=equity,
        fills=broker.fills,
        open_position=broker.position,
        source=source,
    )
