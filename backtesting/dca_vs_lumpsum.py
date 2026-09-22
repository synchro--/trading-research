#!/usr/bin/env python3
"""DCA vs lump-sum accumulation across classic portfolios, rolling 10-20y windows.

Every strategy invests the identical total amount X = contribution x months in
the window; the only difference is timing:

* dca_mid       500/mo on the first trading day on/after the 15th
* oracle_1m     500/mo at the lowest composite close of the arrival month
* oracle_pt_3m  each monthly tranche waits up to 3 months and buys at the lowest
                composite close within [arrival month, +2] (truncated at window end)
* oracle_pt_6m  same with 6 months of patience
* oracle_cy_3m  accumulate 3 months, deploy 3x contribution at the cycle's lowest close
* oracle_cy_6m  accumulate 6 months, deploy 6x contribution at the cycle's lowest close
* lump_sum      all X on the window's first trading day

The oracle strategies use hindsight (perfect dip selection) and are upper
bounds on timing skill, not implementable rules. In cycle mode a tranche whose
arrival falls after the cycle's dip day is deployed at par (interest-free
borrowing), likewise an oracle simplification.

Assumptions:
* daily total-return bars via backtesting.engine.data.load_bars (Yahoo, split
  and dividend adjusted); fills at the chosen day's close
* commission 10 bps + slippage 5 bps on every ETF buy/sell leg; no TER/taxes
* waiting contributions accrue the 13-week T-bill yield (^IRX, decimal, simple
  360-basis) per calendar day. Money-market transfers are free
* contributions arrive on the first trading day of each month
* annual rebalance to target weights on each window anniversary
* nominal USD reported with EUR labels (no FX, per study design)
* windows: every monthly start from 2004-12 (GLD inception constraint),
  horizons {10,12,14,16,18,20} years, ending by the last complete data month
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

CONTRIBUTION = 500.0
HORIZON_YEARS = (10, 12, 14, 16, 18, 20)
COMMISSION_BPS = 10.0
SLIPPAGE_BPS = 5.0
COMM = COMMISSION_BPS / 10_000.0
SLIP = SLIPPAGE_BPS / 10_000.0
CASH = "CASH"
YIELD_SYMBOL = "^IRX"

STOCK_MIX = {"SPY": 0.55, "EFA": 0.30, "EEM": 0.15}
PORTFOLIOS: dict[str, dict[str, float]] = {
    "stocks_100": dict(STOCK_MIX),
    "80_20": {"SPY": 0.44, "EFA": 0.24, "EEM": 0.12, "AGG": 0.20},
    "60_40": {"SPY": 0.33, "EFA": 0.18, "EEM": 0.09, "AGG": 0.40},
    "golden_butterfly": {"VTV": 0.20, "VBR": 0.20, "SHY": 0.20, "GLD": 0.20, CASH: 0.20},
}
STRATEGIES = (
    "dca_mid",
    "oracle_1m",
    "oracle_pt_3m",
    "oracle_pt_6m",
    "oracle_cy_3m",
    "oracle_cy_6m",
    "lump_sum",
)
ETF_SYMBOLS = sorted({s for p in PORTFOLIOS.values() for s in p if s != CASH})
FETCH_START = "2004-11-01"  # GLD inception


@dataclass
class Month:
    key: str  # "YYYY-MM"
    first: int
    mid: int
    last: int
    days: tuple[int, ...]

    @property
    def complete(self) -> bool:
        """True when the month's last trading day is at/after the 20th."""
        return int(self._last_date[8:10]) >= 20


@dataclass
class MarketData:
    dates: list[str]
    closes: dict[str, np.ndarray]
    yields: dict[str, float]
    cumlog: np.ndarray
    months: list[Month]

    def composite(self, weights: dict[str, float]) -> np.ndarray:
        symbols = [s for s in weights if s != CASH]
        wsum = sum(weights[s] for s in symbols)
        arr = np.zeros(len(self.dates), dtype=float)
        for s in symbols:
            arr += (weights[s] / wsum) * (self.closes[s] / self.closes[s][0])
        return arr


def _build_cumlog(dates: list[str], yields: dict[str, float]) -> np.ndarray:
    """Cumulative log accrual factor; y/360 simple interest per calendar day."""
    out = np.zeros(len(dates), dtype=float)
    last_yield = next(iter(yields.values())) if yields else 0.0
    cum = 0.0
    prev_date = date.fromisoformat(dates[0])
    for i, d in enumerate(dates):
        cur = date.fromisoformat(d)
        y = yields.get(dates[i - 1], last_yield) if i else last_yield
        if i:
            cum += (cur - prev_date).days * math.log1p(y / 360.0)
            prev_date = cur
        out[i] = cum
    return out


def build_market(
    dates: list[str],
    closes: dict[str, np.ndarray],
    yields_by_date: dict[str, float],
) -> MarketData:
    months: list[Month] = []
    bucket: dict[str, list[int]] = {}
    for i, d in enumerate(dates):
        bucket.setdefault(d[:7], []).append(i)
    for key in sorted(bucket):
        days = bucket[key]
        mid = next((i for i in days if int(dates[i][8:10]) >= 15), days[-1])
        months.append(
            Month(key=key, first=days[0], mid=mid, last=days[-1], days=tuple(days))
        )
    months[-1]._last_date = dates[months[-1].last]  # type: ignore[attr-defined]
    for m in months:
        m.__dict__["_last_date"] = dates[m.last]
    return MarketData(
        dates=dates,
        closes=closes,
        yields=yields_by_date,
        cumlog=_build_cumlog(dates, yields_by_date),
        months=months,
    )


def accrual_factor(cumlog: np.ndarray, d: int, a: int) -> float:
    if d <= a:
        return 1.0
    return math.exp(float(cumlog[d] - cumlog[a]))


def argmin_day(comp: np.ndarray, days) -> int:
    days = list(days)
    return days[int(np.argmin(comp[days]))]


# ---------------------------------------------------------------- planning

def plan_strategy(
    strategy: str,
    comp: np.ndarray,
    months: list[Month],
    contribution: float,
) -> tuple[list[tuple[int, list[tuple[float, int]]]], list[int]]:
    """Return (buy events [(day, [(amount, anchor_day), ...])], rebalance days)."""
    horizon = len(months)
    buys: list[tuple[int, list[tuple[float, int]]]] = []
    if strategy == "lump_sum":
        buys.append((months[0].first, [(contribution * horizon, months[0].first)]))
    elif strategy == "dca_mid":
        for m in months:
            buys.append((m.mid, [(contribution, m.first)]))
    elif strategy == "oracle_1m":
        for m in months:
            buys.append((argmin_day(comp, m.days), [(contribution, m.first)]))
    elif strategy.startswith("oracle_pt_"):
        n = int(strategy.rsplit("_", 1)[1].rstrip("m"))
        for k, m in enumerate(months):
            span = [d for mm in months[k : k + n] for d in mm.days]
            buys.append((argmin_day(comp, span), [(contribution, m.first)]))
    elif strategy.startswith("oracle_cy_"):
        n = int(strategy.rsplit("_", 1)[1].rstrip("m"))
        for c in range(0, horizon, n):
            group = months[c : c + n]
            span = [d for mm in group for d in mm.days]
            day = argmin_day(comp, span)
            buys.append((day, [(contribution, mm.first) for mm in group]))
    else:
        raise ValueError(f"unknown strategy {strategy!r}")
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    invested = sum(a for _, tr in buys for a, _ in tr)
    assert abs(invested - contribution * horizon) < 1e-6, (
        f"{strategy}: invested {invested} != {contribution * horizon}"
    )
    return buys, rebalance_days


def run_window(
    md: MarketData,
    weights: dict[str, float],
    months: list[Month],
    buys: list[tuple[int, list[tuple[float, int]]]],
    rebalance_days: list[int],
) -> float:
    symbols = [s for s in weights if s != CASH]
    w = np.array([weights[s] for s in symbols], dtype=float)  # raw target weights
    w_cash = weights.get(CASH, 0.0)
    close = np.stack([md.closes[s] for s in symbols])
    shares = np.zeros(len(symbols), dtype=float)
    gb = 0.0  # money-market sleeve (Golden Butterfly CASH) or rebalance residue
    gb_anchor = months[0].first

    events: list[tuple[int, int, object]] = []
    for day, tranches in buys:
        events.append((day, 1, tranches))
    for day in rebalance_days:
        events.append((day, 0, None))
    events.sort(key=lambda e: (e[0], e[1]))

    for day, order, payload in events:
        if gb_anchor < day:
            gb *= accrual_factor(md.cumlog, day, gb_anchor)
            gb_anchor = day
        if order == 0:
            vals = shares * close[:, day]
            total = float(vals.sum()) + gb
            pool = gb
            targets = w * total
            sell_idx = np.where(vals > targets + 1e-9)[0]
            buy_idx = np.where(vals < targets - 1e-9)[0]
            for i in sell_idx:
                sell = float(vals[i] - targets[i])
                shares[i] -= sell / close[i, day]
                pool += sell * (1.0 - SLIP) * (1.0 - COMM)
            for i in buy_idx:
                spend = min(float(targets[i] - vals[i]), pool)
                if spend <= 0:
                    continue
                shares[i] += spend / (close[i, day] * (1.0 + SLIP) * (1.0 + COMM))
                pool -= spend
            gb = pool
        else:
            cash_in = 0.0
            for amount, anchor in payload:
                cash_in += amount * accrual_factor(md.cumlog, day, anchor)
            if w_cash:
                gb += cash_in * w_cash
            shares += (cash_in * w) / (close[:, day] * (1.0 + SLIP) * (1.0 + COMM))

    end_idx = months[-1].last
    if gb_anchor < end_idx:
        gb *= accrual_factor(md.cumlog, end_idx, gb_anchor)
    return float((shares * close[:, end_idx]).sum() + gb)


# ---------------------------------------------------------------- data load

def enumerate_windows(md: MarketData, horizon_months: int) -> list[tuple[int, list[Month]]]:
    """(start month position, month slice) for one horizon, end months complete."""
    complete_last = max(i for i, m in enumerate(md.months) if m.complete)
    return [
        (i, md.months[i : i + horizon_months])
        for i in range(len(md.months))
        if i + horizon_months - 1 <= complete_last
    ]


def load_experiment(end: str, force: bool) -> tuple[MarketData, dict[str, str]]:
    closes_raw: dict[str, dict[str, float]] = {}
    sources: dict[str, str] = {}
    for symbol in ETF_SYMBOLS:
        bars, src = load_bars(
            symbol, FETCH_START, end, provider="yahoo", warmup_calendar_days=0, force=force
        )
        assert bars[0].t <= "2005-01-31", f"{symbol} history too shallow: starts {bars[0].t}"
        closes_raw[symbol] = {b.t: b.c for b in bars}
        sources[symbol] = src
    # ^IRX is a yield index: load it raw and skip adjust_splits entirely — the
    # split heuristic mis-fires on sub-percent yield levels and corrupts it
    from backtesting.engine.data import fetch_yahoo
    try:
        ybars = fetch_yahoo(YIELD_SYMBOL, "2004-01-01", end)
        ysrc = "yahoo raw (no split-adjust)"
    except Exception as e:
        ybars, ysrc = [], f"yahoo failed: {e}"
    sources[YIELD_SYMBOL] = ysrc
    yvals = np.array([b.c for b in ybars], dtype=float)
    scale = 100.0 if (len(yvals) and np.median(yvals) >= 0.2) else 1.0
    yields_by_date: dict[str, float] = {}
    for b in ybars:
        y = b.c / scale
        if 0.0 < y < 0.15:  # sanity: ^IRX spans ~0.01%..~6%
            yields_by_date[b.t] = y

    common = sorted(set.intersection(*(set(v) for v in closes_raw.values())))
    assert common[0] <= "2004-12-31", f"common calendar starts {common[0]}, expected 2004-12"
    closes = {s: np.array([closes_raw[s][d] for d in common]) for s in closes_raw}
    # forward-fill the yield series onto the ETF calendar (0 until first quote)
    ff: dict[str, float] = {}
    last = 0.0
    for d in common:
        y = yields_by_date.get(d)
        if y is not None:
            last = y
        ff[d] = last
    md = build_market(common, closes, ff)
    return md, sources


# ---------------------------------------------------------------- stats

def summarize(terminals: np.ndarray, ls: np.ndarray, dca: np.ndarray) -> dict:
    ratio = terminals / ls - 1.0
    ratio_dca = terminals / dca - 1.0
    return {
        "n": int(len(terminals)),
        "median": float(np.median(terminals)),
        "mean": float(np.mean(terminals)),
        "p5": float(np.percentile(terminals, 5)),
        "p25": float(np.percentile(terminals, 25)),
        "p75": float(np.percentile(terminals, 75)),
        "p95": float(np.percentile(terminals, 95)),
        "win_vs_lump_sum": float(np.mean(terminals > ls)),
        "adv_median_vs_lump_sum": float(np.median(ratio)),
        "adv_mean_vs_lump_sum": float(np.mean(ratio)),
        "win_vs_dca_mid": float(np.mean(terminals > dca)),
        "adv_median_vs_dca_mid": float(np.median(ratio_dca)),
        "adv_mean_vs_dca_mid": float(np.mean(ratio_dca)),
    }


def fmt_eur(v: float) -> str:
    return f"{v:,.0f}"


def print_main_table(name: str, rows: list[dict], window_count: int) -> None:
    print(f"\n=== {name}  ({window_count} windows, contrib 500/mo, lump X 60k-120k) ===")
    print(
        f"{'strategy':<14}{'median':>12}{'mean':>12}{'p5':>12}{'p95':>12}"
        f"{'win>LS':>8}{'advLS med':>11}{'advLS mean':>12}{'advDCA med':>12}"
    )
    print("-" * 104)
    best = max(rows, key=lambda r: r["median"])
    for r in rows:
        star = "*" if r["strategy"] == best["strategy"] else " "
        print(
            f"{r['strategy']:<14}{fmt_eur(r['median']):>12}{fmt_eur(r['mean']):>12}"
            f"{fmt_eur(r['p5']):>12}{fmt_eur(r['p95']):>12}"
            f"{r['win_vs_lump_sum']:>7.0%} {r['adv_median_vs_lump_sum']:>+10.1%}"
            f"{r['adv_mean_vs_lump_sum']:>+11.1%}{r['adv_median_vs_dca_mid']:>+11.1%} {star}"
        )


def print_horizon_table(name: str, horizon_medians: dict[str, dict[int, float]]) -> None:
    horizons = sorted(next(iter(horizon_medians.values())))
    print(f"\n{name}: median terminal by horizon")
    print(f"{'strategy':<14}" + "".join(f"{h:>8}y" for h in horizons))
    for s in STRATEGIES:
        row = horizon_medians.get(s, {})
        print(f"{s:<14}" + "".join(f"{row[h]:>9,.0f}" for h in horizons))


# ---------------------------------------------------------------- main

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start-month", default="2004-12")
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--horizons", default=",".join(str(h) for h in HORIZON_YEARS))
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--reuse-cache", action="store_true", help="skip deep refetch")
    p.add_argument("--out", default=str(DATA_DIR / "dca_vs_lumpsum.json"))
    args = p.parse_args()

    md, sources = load_experiment(args.end, force=not args.reuse_cache)
    sources_note = f"data {md.dates[0]} -> {md.dates[-1]}, {len(md.dates)} common days"

    horizons = [int(h) for h in args.horizons.split(",")]
    all_windows: dict[int, list[list[Month]]] = {}
    window_counts: dict[int, int] = {}
    for h_years in horizons:
        h_months = h_years * 12
        wins = [months for _, months in enumerate_windows(md, h_months)]
        all_windows[h_months] = wins
        window_counts[h_years] = len(wins)
    print(f"{sources_note}; {YIELD_SYMBOL} yield source; windows: {window_counts}")
    for s, src in sources.items():
        print(f"  [data] {s:<6} {src}")

    terminals: dict[tuple[str, str, int], np.ndarray] = {}
    comp_cache: dict[str, np.ndarray] = {}
    for p_name, weights in PORTFOLIOS.items():
        if p_name not in comp_cache:
            comp_cache[p_name] = md.composite(weights)
        comp = comp_cache[p_name]
        for h_months, wins in all_windows.items():
            for strategy in STRATEGIES:
                vals = []
                for months in wins:
                    buys, rebalance_days = plan_strategy(strategy, comp, months, args.contribution)
                    vals.append(run_window(md, weights, months, buys, rebalance_days))
                terminals[(p_name, strategy, h_months)] = np.array(vals)

    # ------------------------------------------------- aggregate + report
    summary_rows = []
    horizon_medians: dict[str, dict[str, dict[int, float]]] = {}
    pooled: dict[str, dict[str, np.ndarray]] = {}
    for p_name in PORTFOLIOS:
        rows = []
        hm: dict[str, dict[int, float]] = {}
        for strategy in STRATEGIES:
            t_all = np.concatenate(
                [terminals[(p_name, strategy, h * 12)] for h in horizons]
            )
            ls_all = np.concatenate(
                [terminals[(p_name, "lump_sum", h * 12)] for h in horizons]
            )
            dca_all = np.concatenate(
                [terminals[(p_name, "dca_mid", h * 12)] for h in horizons]
            )
            stats = summarize(t_all, ls_all, dca_all)
            stats.update({"portfolio": p_name, "strategy": strategy})
            rows.append(stats)
            hm[strategy] = {
                h: float(np.median(terminals[(p_name, strategy, h * 12)])) for h in horizons
            }
            pooled.setdefault(strategy, {"t": [], "ls": [], "dca": []})
            pooled[strategy]["t"].append(t_all)
            pooled[strategy]["ls"].append(ls_all)
            pooled[strategy]["dca"].append(dca_all)
        horizon_medians[p_name] = hm
        print_main_table(p_name, rows, sum(window_counts.values()))
        print_horizon_table(p_name, hm)
        summary_rows.extend(rows)

    print("\n=== pooled across portfolios (all windows, vs lump_sum) ===")
    print(f"{'strategy':<14}{'win>LS':>8}{'advLS med':>11}{'advLS mean':>12}")
    print("-" * 48)
    pooled_rows = []
    for s in STRATEGIES:
        t_all = np.concatenate(pooled[s]["t"])
        ls_all = np.concatenate(pooled[s]["ls"])
        dca_all = np.concatenate(pooled[s]["dca"])
        stats = summarize(t_all, ls_all, dca_all)
        stats.update({"portfolio": "pooled", "strategy": s})
        pooled_rows.append(stats)
        print(
            f"{s:<14}{stats['win_vs_lump_sum']:>7.0%} "
            f"{stats['adv_median_vs_lump_sum']:>+10.1%}"
            f"{stats['adv_mean_vs_lump_sum']:>+11.1%}"
        )
    summary_rows.extend(pooled_rows)

    # sanity anchor: GFC-start window (2008-07, 10y, stocks_100)
    print("\n=== sanity: 2008-07 start, 10y, stocks_100 terminals ===")
    try:
        w_idx = next(
            i for i, m in enumerate(md.months) if m.key == "2008-07"
        )
        gfc_months = md.months[w_idx : w_idx + 120]
        gfc_comp = comp_cache["stocks_100"]
        for strategy in STRATEGIES:
            buys, rbd = plan_strategy(strategy, gfc_comp, gfc_months, args.contribution)
            term = run_window(md, PORTFOLIOS["stocks_100"], gfc_months, buys, rbd)
            print(f"  {strategy:<14} {fmt_eur(term)}")
    except StopIteration:
        print("  (2008-07 not found, skipped)")

    total_invested = {h: args.contribution * h * 12 for h in horizons}
    payload = {
        "params": {
            "contribution": args.contribution,
            "horizons_years": horizons,
            "total_invested_per_window": total_invested,
            "commission_bps": COMMISSION_BPS,
            "slippage_bps": SLIPPAGE_BPS,
            "cash_yield_symbol": YIELD_SYMBOL,
            "start_month": args.start_month,
            "portfolios": PORTFOLIOS,
            "strategies": list(STRATEGIES),
        },
        "data": {
            "range": [md.dates[0], md.dates[-1]],
            "common_days": len(md.dates),
            "sources": sources,
            "yield_scale_note": "simple interest y/360 per calendar day, ffilled to ETF calendar",
        },
        "window_counts": {str(h): window_counts[h] for h in window_counts},
        "summary": summary_rows,
        "horizon_medians": horizon_medians,
        "records": [
            {
                "portfolio": p_name,
                "strategy": strategy,
                "horizon_years": h_months // 12,
                "start": wins[i][0].key,
                "end": wins[i][-1].key,
                "invested": args.contribution * len(wins[i]),
                "terminal": float(terminals[(p_name, strategy, h_months)][i]),
            }
            for p_name in PORTFOLIOS
            for h_months, wins in all_windows.items()
            for i in range(len(wins))
            for strategy in STRATEGIES
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
