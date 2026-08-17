"""Trade-list and equity-curve metrics (DESIGN.md §7)."""
from __future__ import annotations

import math
from datetime import date

from backtesting.engine.indicators import periods_per_year
from backtesting.engine.types import EquityPoint, RunResult, Trade

_PERIODS = 252
_RF = 0.0  # excess vs 0; stated in reports


def _parse_day(t: str) -> date:
    return date.fromisoformat(t[:10])


def _daily_returns(eq: list[EquityPoint]) -> list[float]:
    out: list[float] = []
    for a, b in zip(eq, eq[1:]):
        if a.equity > 0:
            out.append(b.equity / a.equity - 1.0)
    return out


def cagr(eq: list[EquityPoint]) -> float:
    if len(eq) < 2 or eq[0].equity <= 0:
        return 0.0
    years = (_parse_day(eq[-1].t) - _parse_day(eq[0].t)).days / 365.25
    if years <= 0:
        return 0.0
    return (eq[-1].equity / eq[0].equity) ** (1.0 / years) - 1.0


def sharpe(returns: list[float], rf: float = _RF, periods: int = _PERIODS) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return ((mean - rf / periods) / std) * math.sqrt(periods)


def sortino(returns: list[float], mar: float = _RF, periods: int = _PERIODS) -> float:
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    mar_d = mar / periods
    downside = [(r - mar_d) ** 2 for r in returns if r < mar_d]
    if not downside:
        return float("inf") if mean > mar_d else 0.0
    dd = math.sqrt(sum(downside) / n)
    if dd == 0:
        return 0.0
    return ((mean - mar_d) / dd) * math.sqrt(periods)


def buy_hold(bars, start: str | None, initial_cash: float = 20_000.0,
             commission_bps: float = 10.0, slippage_bps: float = 5.0,
             warmup_bars: int = 0) -> dict:
    """Benchmark: buy the first live open, hold to the end. Same costs as the engine.

    `warmup_bars` must match what the strategies were given, or the benchmark gets a
    head start on symbols whose history begins after the requested start date.
    """
    live = [b for i, b in enumerate(bars)
            if (start is None or b.t[:10] >= start[:10]) and i >= warmup_bars]
    if len(live) < 2:
        return {"cagr": 0.0, "sharpe": 0.0, "sortino": None, "max_dd": 0.0, "return_pct": 0.0}
    entry_px = live[0].o * (1.0 + slippage_bps / 10_000.0)
    qty = (initial_cash * (1.0 - commission_bps / 10_000.0)) / entry_px
    eq: list[EquityPoint] = []
    peak = initial_cash
    for b in live:
        e = qty * b.c
        peak = max(peak, e)
        eq.append(EquityPoint(t=b.t, equity=e, drawdown=(peak - e) / peak if peak else 0.0))
    per = periods_per_year([p.t for p in eq])
    rets = _daily_returns(eq)
    sh = sharpe(rets, periods=per)
    so = sortino(rets, periods=per)
    return {
        "cagr": cagr(eq),
        "sharpe": None if not math.isfinite(sh) else sh,
        "sortino": None if not math.isfinite(so) else so,
        "max_dd": max((p.drawdown for p in eq), default=0.0),
        "return_pct": eq[-1].equity / initial_cash - 1.0,
    }


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
    in_pos = sum(t.hold_bars for t in trades)
    tim = (in_pos / len(eq)) if eq else 0.0
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    per = periods_per_year([p.t for p in eq])
    rets = _daily_returns(eq)
    sh = sharpe(rets, periods=per)
    so = sortino(rets, periods=per)
    return {
        "symbol": result.symbol,
        "periods_per_year": per,
        "source": result.source,
        "n": n,
        "wins": len(wins),
        "win_rate": (len(wins) / n) if n else 0.0,
        "expectancy_r": (sum(t.r_multiple for t in trades) / n) if n else 0.0,
        "avg_hold_days": (sum(t.hold_bars for t in trades) / n) if n else 0.0,
        "max_dd": max_dd,
        "cagr": cagr(eq),
        "sharpe": None if not math.isfinite(sh) else sh,
        "sortino": None if not math.isfinite(so) else so,
        "rf": _RF,
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
    so = m.get("sortino")
    so_s = "inf" if so is None else f"{so:.2f}"
    sh = m.get("sharpe") or 0.0
    return (
        f"{m['symbol']}: n={m['n']}  win={m['win_rate']:.1%}  "
        f"E[R]={m['expectancy_r']:.2f}  Sharpe={sh:.2f}  Sortino={so_s}  "
        f"CAGR={m['cagr']:.1%}  maxDD={m['max_dd']:.1%}  "
        f"hold={m['avg_hold_days']:.1f}d  time={m['time_in_market']:.1%}  "
        f"PF={pf_s}  ret={m['return_pct']:.1%}  reasons={m['reasons']}"
    )
