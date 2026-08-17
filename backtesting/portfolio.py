#!/usr/bin/env python3
"""Portfolio-level timing experiments.

The single-symbol experiments apply portfolio papers to isolated assets. This
module tests the papers in their intended shape: equal-weight sleeves, monthly
rebalance, and inactive sleeves held as cash.

The basket is selected by economic role before seeing results:

* global6: US, developed ex-US, emerging markets, Treasuries, gold, commodities
* oil_transport8: global6 plus energy producers and transportation
* faber5: close ETF proxies for Faber's original five asset classes

No geopolitical text signal is used. The repository contains no Trump/Iran/oil
event dataset, and coding one from remembered events would introduce look-ahead.
XLE and IYT are instead tested as transparent economic sleeves.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np

from backtesting.engine.data import DATA_DIR, load_bars
from backtesting.engine.indicators import periods_per_year
from backtesting.engine.metrics import sharpe, sortino
from backtesting.engine.types import Bar


BASKETS = {
    "global6": ["SPY", "EFA", "EEM", "IEF", "GLD", "DBC"],
    "oil_transport8": ["SPY", "EFA", "EEM", "IEF", "GLD", "DBC", "XLE", "IYT"],
    "faber5": ["SPY", "EFA", "IEF", "DBC", "VNQ"],
}
METHODS = ("static_ew", "faber_monthly", "tsmom_12m", "dual_confirm")


@dataclass
class PortfolioPoint:
    t: str
    equity: float
    cash: float
    invested_fraction: float
    turnover: float


def _common_bars(data: dict[str, list[Bar]]) -> tuple[list[str], dict[str, dict[str, Bar]]]:
    maps = {s: {b.t: b for b in bars} for s, bars in data.items()}
    common = sorted(set.intersection(*(set(m) for m in maps.values())))
    return common, maps


def _signals(method: str, closes: np.ndarray, i: int) -> np.ndarray:
    n = closes.shape[1]
    if method == "static_ew":
        return np.ones(n, dtype=bool)
    sma_ok = closes[i] > np.mean(closes[i - 199 : i + 1], axis=0)
    mom_ok = closes[i] > closes[i - 252]
    if method == "faber_monthly":
        return sma_ok
    if method == "tsmom_12m":
        return mom_ok
    if method == "dual_confirm":
        return sma_ok & mom_ok
    raise ValueError(f"unknown method {method!r}")


def run_portfolio(
    symbols: list[str],
    data: dict[str, list[Bar]],
    *,
    method: str,
    initial_cash: float = 100_000.0,
    commission_bps: float = 10.0,
    slippage_bps: float = 5.0,
    warmup_bars: int = 252,
) -> list[PortfolioPoint]:
    dates, maps = _common_bars(data)
    if len(dates) <= warmup_bars + 2:
        return []
    opens = np.array([[maps[s][d].o for s in symbols] for d in dates], dtype=float)
    closes = np.array([[maps[s][d].c for s in symbols] for d in dates], dtype=float)

    qty = np.zeros(len(symbols), dtype=float)
    cash = float(initial_cash)
    out: list[PortfolioPoint] = []
    commission = commission_bps / 10_000.0
    slippage = slippage_bps / 10_000.0

    for i in range(warmup_bars, len(dates)):
        rebalance = i == warmup_bars or dates[i][:7] != dates[i - 1][:7]
        turnover = 0.0
        if rebalance:
            # Signal on the prior close, transact at this open.
            signal_i = i - 1
            active = _signals(method, closes, signal_i)
            equity_open = cash + float(np.dot(qty, opens[i]))
            target_value = active.astype(float) * (equity_open / len(symbols))
            current_value = qty * opens[i]
            delta_value = target_value - current_value

            # Sells first so proceeds fund buys. Slippage and commission apply to
            # traded notional, matching the single-symbol engine.
            for j in np.where(delta_value < 0)[0]:
                sell_value = min(-delta_value[j], current_value[j])
                fill = opens[i, j] * (1.0 - slippage)
                shares = min(qty[j], sell_value / opens[i, j])
                notional = shares * fill
                qty[j] -= shares
                cash += notional * (1.0 - commission)
                turnover += notional
            for j in np.where(delta_value > 0)[0]:
                desired = delta_value[j]
                fill = opens[i, j] * (1.0 + slippage)
                affordable = cash / (1.0 + commission)
                notional = min(desired, affordable)
                shares = notional / fill
                cost = shares * fill
                qty[j] += shares
                cash -= cost * (1.0 + commission)
                turnover += cost

        equity = cash + float(np.dot(qty, closes[i]))
        invested = float(np.dot(qty, closes[i])) / equity if equity > 0 else 0.0
        out.append(
            PortfolioPoint(
                t=dates[i],
                equity=equity,
                cash=cash,
                invested_fraction=invested,
                turnover=turnover,
            )
        )
    return out


def portfolio_metrics(points: list[PortfolioPoint], initial_cash: float = 100_000.0) -> dict:
    if len(points) < 2:
        return {}
    equity = np.array([p.equity for p in points], dtype=float)
    returns = equity[1:] / equity[:-1] - 1.0
    per = periods_per_year([p.t for p in points])
    years = (date.fromisoformat(points[-1].t) - date.fromisoformat(points[0].t)).days / 365.25
    cagr = (equity[-1] / equity[0]) ** (1.0 / years) - 1.0
    peaks = np.maximum.accumulate(np.insert(equity, 0, initial_cash))[1:]
    drawdowns = 1.0 - equity / peaks
    max_dd = float(np.max(drawdowns))
    ann_vol = float(np.std(returns, ddof=1) * math.sqrt(per))
    sh = sharpe(returns.tolist(), periods=per)
    so = sortino(returns.tolist(), periods=per)
    ulcer = float(math.sqrt(np.mean(np.square(drawdowns))) * 100.0)

    max_underwater = 0
    underwater = 0
    for dd in drawdowns:
        if dd > 1e-12:
            underwater += 1
            max_underwater = max(max_underwater, underwater)
        else:
            underwater = 0

    traded = sum(p.turnover for p in points)
    avg_equity = float(np.mean(equity))
    return {
        "start": points[0].t,
        "end": points[-1].t,
        "end_equity": float(equity[-1]),
        "return_pct": float(equity[-1] / equity[0] - 1.0),
        "cagr": float(cagr),
        "annual_volatility": ann_vol,
        "sharpe": float(sh),
        "sortino": None if not math.isfinite(so) else float(so),
        "max_dd": max_dd,
        "calmar": float(cagr / max_dd) if max_dd > 0 else None,
        "ulcer_index": ulcer,
        "max_underwater_days": int(max_underwater),
        "average_invested": float(np.mean([p.invested_fraction for p in points])),
        "annual_turnover": float(traded / avg_equity / years) if avg_equity > 0 else 0.0,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2005-01-01")
    p.add_argument("--end", default="2026-08-13")
    p.add_argument("--provider", default="yahoo")
    p.add_argument("--force-fetch", action="store_true")
    p.add_argument("--out", default=str(DATA_DIR / "portfolio_comparison.json"))
    args = p.parse_args()

    all_symbols = sorted({s for basket in BASKETS.values() for s in basket})
    loaded: dict[str, list[Bar]] = {}
    sources: dict[str, str] = {}
    for symbol in all_symbols:
        bars, source = load_bars(
            symbol,
            args.start,
            args.end,
            provider=args.provider,
            warmup_calendar_days=800,
            force=args.force_fetch,
        )
        loaded[symbol] = bars
        sources[symbol] = source

    rows = []
    curves = {}
    for basket_name, symbols in BASKETS.items():
        basket_data = {s: loaded[s] for s in symbols}
        for method in METHODS:
            points = run_portfolio(symbols, basket_data, method=method)
            metrics = portfolio_metrics(points)
            metrics.update({"basket": basket_name, "method": method, "symbols": symbols})
            rows.append(metrics)
            curves[f"{basket_name}:{method}"] = [
                {"t": p.t, "equity": p.equity, "invested": p.invested_fraction}
                for p in points
            ]

    payload = {
        "start_requested": args.start,
        "end_requested": args.end,
        "costs": {"commission_bps": 10.0, "slippage_bps": 5.0},
        "baskets": BASKETS,
        "sources": sources,
        "rows": rows,
        "curves": curves,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"{'basket':<16}{'method':<18}{'Sharpe':>8}{'CAGR':>9}{'vol':>8}{'maxDD':>9}{'Calmar':>9}{'invested':>10}")
    print("-" * 87)
    for row in rows:
        print(
            f"{row['basket']:<16}{row['method']:<18}{row['sharpe']:>8.2f}"
            f"{row['cagr']:>8.1%}{row['annual_volatility']:>8.1%}{row['max_dd']:>9.1%}"
            f"{(row['calmar'] or 0):>9.2f}{row['average_invested']:>10.1%}"
        )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
