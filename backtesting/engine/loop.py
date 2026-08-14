"""Bar loop: T+1 open entries, prior-bar trail vs low, regime flatten next open."""
from __future__ import annotations

from backtesting.engine.broker import Broker
from backtesting.engine.types import Bar, EquityPoint, PendingEntry, RunResult
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1, StrategyConfig


def run(
    bars: list[Bar],
    *,
    symbol: str,
    start: str | None = None,
    initial_cash: float = 20_000.0,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    cfg: StrategyConfig | None = None,
    source: str = "",
) -> RunResult:
    if not bars:
        return RunResult(symbol=symbol, trades=[], equity=[], fills=[], open_position=None, source=source)

    strat = EmaPullbackV1(bars, cfg)
    cfg = strat.cfg
    broker = Broker(cash=initial_cash, commission_bps=commission_bps, slippage_bps=slippage_bps)

    pending_entry: PendingEntry | None = None
    pending_regime = False
    equity: list[EquityPoint] = []
    peak = initial_cash
    in_pos_bars = 0
    scored_bars = 0

    for i, bar in enumerate(bars):
        broker.mark_bar(i)
        live = start is None or bar.t[:10] >= start[:10]

        # 1. Open: regime flatten, then entry.
        if live and pending_regime and broker.position is not None:
            broker.sell(bar.t, bar.o, "regime")
            pending_regime = False
            pending_entry = None

        if live and pending_entry is not None and broker.position is None:
            broker.buy(bar.t, bar.o, pending_entry.qty, pending_entry.initial_risk)
        pending_entry = None

        # 2. Intrabar stop against the trail known at prior close (or initial stop).
        if live and broker.position is not None:
            stop_px = broker.stop_fill_price(bar.o, bar.l)
            if stop_px is not None:
                broker.sell(bar.t, stop_px, "trail")
                pending_regime = False

        # 3. Close: ratchet trail for tomorrow; arm next-bar actions.
        pos = broker.position
        if pos is not None:
            pos.trail = max(pos.trail, strat.trail_candidate(i, pos.entry_px, pos.initial_risk))
            if live and bool(strat.regime_break[i]):
                pending_regime = True
            if live:
                in_pos_bars += 1
        elif live:
            if strat.long_signal(i):
                risk = strat.initial_risk(i)
                eq = broker.equity(bar.c)
                qty = (eq * (cfg.risk_pct / 100.0) / risk) if risk > 0 else 0.0
                if qty > 0:
                    pending_entry = PendingEntry(initial_risk=risk, qty=qty)

        if live:
            scored_bars += 1
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
