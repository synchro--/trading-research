"""Trade-list metrics (DESIGN.md §7)."""
from __future__ import annotations

from backtesting.engine.types import RunResult, Trade


def summarize(result: RunResult) -> dict:
    trades: list[Trade] = result.trades
    n = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    eq = result.equity
    start_eq = eq[0].equity if eq else 0.0
    end_eq = eq[-1].equity if eq else 0.0
    max_dd = max((p.drawdown for p in eq), default=0.0)
    in_pos = 0
    if eq:
        # time-in-market from hold bars vs calendar of equity points
        in_pos = sum(t.hold_bars for t in trades)
        if result.open_position is not None:
            # remainder of last trade not closed — approximate via last equity stretch not needed
            pass
    tim = (in_pos / len(eq)) if eq else 0.0
    reasons = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return {
        "symbol": result.symbol,
        "source": result.source,
        "n": n,
        "wins": len(wins),
        "win_rate": (len(wins) / n) if n else 0.0,
        "expectancy_r": (sum(t.r_multiple for t in trades) / n) if n else 0.0,
        "avg_hold_days": (sum(t.hold_bars for t in trades) / n) if n else 0.0,
        "max_dd": max_dd,
        "time_in_market": tim,
        "profit_factor": (gross_win / gross_loss) if gross_loss else (float("inf") if gross_win else 0.0),
        "net_pnl": sum(t.pnl for t in trades),
        "start_equity": start_eq,
        "end_equity": end_eq,
        "return_pct": ((end_eq / start_eq) - 1.0) if start_eq else 0.0,
        "reasons": reasons,
        "open_trade": result.open_position is not None,
    }


def format_summary(m: dict) -> str:
    pf = m["profit_factor"]
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return (
        f"{m['symbol']}: n={m['n']}  win={m['win_rate']:.1%}  "
        f"E[R]={m['expectancy_r']:.2f}  hold={m['avg_hold_days']:.1f}d  "
        f"maxDD={m['max_dd']:.1%}  time={m['time_in_market']:.1%}  "
        f"PF={pf_s}  ret={m['return_pct']:.1%}  reasons={m['reasons']}"
    )
