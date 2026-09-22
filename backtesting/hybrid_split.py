#!/usr/bin/env python3
"""Hybrid LS/DCA split study: how should a windfall be staged into the market?

Windfall framing: the full budget X = contribution x months is available at
day 0 (matching the X of dca_vs_lumpsum.py). Strategies invest alpha x X on day
0 and spread the remaining (1-alpha) x X over the next M months (M = 12, 24, or
the full window N). Every euro of the tail sits in the money-market account
(T-bill yield, ^IRX) until its scheduled buy, so the strategy pays the
opportunity cost of waiting exactly like the Vanguard cost-averaging studies.

An extra variant (alpha=0.5, M=N) accelerates the tail: each month, if the
first-two-weeks red-dip trigger fires (>=3% below the previous-30-day high,
see mm_cushion.py), the scheduled tail buy doubles, drawing from the remaining
tail budget.

Baselines: ls (alpha=1) and dca_full (alpha=0, M=N, one buy per month at the
mid-month day).

Stats per strategy, pooled over the 498 windows of each portfolio: terminal
wealth vs ls, and a first-year "regret" metric: P(value at month 12 < X) and
the mean shortfall when underwater (Vanguard reports the analogous 22.4% vs
17.6% decline frequencies).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from backtesting.dca_vs_lumpsum import (
    CONTRIBUTION,
    PORTFOLIOS,
    enumerate_windows,
    load_experiment,
    plan_strategy,
    run_window,
)
from backtesting.mm_cushion import find_mm_trigger, rolling_max_calendar

SPLITS = (0.25, 0.50, 0.75)
TAILS = (12, 24, None)  # None = whole window
DIP_VARIANT = "hyb50_full_dip"


def strategy_name(alpha: float, tail) -> str:
    return f"hyb{int(round(alpha * 100))}_m{tail if tail else 'full'}"


def strategy_grid() -> list[tuple[str, float, int | None]]:
    out: list[tuple[str, float, int | None]] = [("ls", 1.0, 0), ("dca_full", 0.0, None)]
    for a in SPLITS:
        for m in TAILS:
            out.append((strategy_name(a, m), a, m))
    out.append((DIP_VARIANT, 0.50, None))
    return out


STRATEGIES = [s for s, _, _ in strategy_grid()]


def plan_hybrid(
    alpha: float,
    tail_months: int | None,
    budget: float,
    months: list,
    comp: np.ndarray,
    roll30: np.ndarray,
    dates: list[str],
    dip: bool = False,
):
    """Return (buys, rebalance_days). All tranches anchor at the window start
    (the money exists from day 0)."""
    anchor = months[0].first
    buys: list[tuple[int, list[tuple[float, int]]]] = []
    deployed = 0.0
    if alpha > 0:
        buys.append((anchor, [(alpha * budget, anchor)]))
        deployed += alpha * budget
    tail = (1.0 - alpha) * budget
    m_eff = min(tail_months, len(months)) if tail_months else len(months)
    if m_eff <= 0 or tail <= 1e-9:
        return buys, [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    per_month = tail / m_eff
    remaining = tail
    for k in range(m_eff):
        m = months[k]
        amount = min(per_month, remaining)
        if amount <= 1e-9:
            continue
        day = m.mid
        if dip:
            trig = find_mm_trigger(comp, roll30, m, dates)
            if trig is not None:
                amount = min(2.0 * per_month, remaining)
                day = trig
        buys.append((day, [(amount, anchor)]))
        remaining -= amount
        deployed += amount
    assert abs(deployed - budget) < 1e-6, f"budget mismatch {deployed} vs {budget}"
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    buys.sort(key=lambda b: b[0])
    return buys, rebalance_days


def value_at(md, weights: dict[str, float], buys, v_idx: int) -> float:
    """Total wealth at calendar index v_idx: invested sleeves + GB cash sleeve +
    still-waiting tail cash (MMF). No rebalance happens before month 12, so the
    share math is exact; trading costs are ignored in this regret proxy."""
    symbols = [s for s in weights if s != "CASH"]
    w = np.array([weights[s] for s in symbols], dtype=float)
    w_cash = weights.get("CASH", 0.0)
    closes = {s: md.closes[s] for s in symbols}
    shares = {s: 0.0 for s in symbols}
    gb = 0.0
    waiting = 0.0
    for day, trs in buys:
        for amount, anchor in trs:
            if day > v_idx:
                waiting += amount * float(np.exp(md.cumlog[v_idx] - md.cumlog[anchor]))
                continue
            cash_in = amount * float(np.exp(md.cumlog[day] - md.cumlog[anchor]))
            for s, wi in zip(symbols, w):
                shares[s] += (cash_in * wi) / closes[s][day]
            gb += cash_in * w_cash
    return float(sum(shares[s] * closes[s][v_idx] for s in symbols) + gb + waiting)


def main() -> None:
    from backtesting.engine.data import DATA_DIR

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--horizons", default="10,12,14,16,18,20")
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--reuse-cache", action="store_true")
    p.add_argument("--out", default=str(DATA_DIR / "hybrid_split.json"))
    args = p.parse_args()

    md, sources = load_experiment(args.end, force=not args.reuse_cache)
    horizons = [int(h) for h in args.horizons.split(",")]
    all_windows: dict[int, list] = {}
    window_counts: dict[int, int] = {}
    for hy in horizons:
        all_windows[hy * 12] = [ms for _, ms in enumerate_windows(md, hy * 12)]
        window_counts[hy] = len(all_windows[hy * 12])
    print(f"data {md.dates[0]} -> {md.dates[-1]}; windows {window_counts}")

    comp_cache: dict[str, np.ndarray] = {}
    roll_cache: dict[str, np.ndarray] = {}
    grid = strategy_grid()

    rows: dict[tuple[str, str, int], np.ndarray] = {}
    v12: dict[tuple[str, str, int], np.ndarray] = {}
    invests: dict[tuple[str, str, int], float] = {}
    for p_name, weights in PORTFOLIOS.items():
        if p_name not in comp_cache:
            comp = md.composite(weights)
            comp_cache[p_name] = comp
            roll_cache[p_name] = rolling_max_calendar(comp, list(md.dates), 30)
        comp, roll30 = comp_cache[p_name], roll_cache[p_name]
        for h, wins in all_windows.items():
            budget = args.contribution * h
            for name, alpha, tail in grid:
                terms, vals = [], []
                for months in wins:
                    dip = name == DIP_VARIANT
                    buys, rbd = plan_hybrid(
                        alpha, tail, budget, months, comp, roll30, list(md.dates), dip=dip
                    )
                    terms.append(run_window(md, weights, months, buys, rbd))
                    v_idx = months[11].last
                    vals.append(value_at(md, weights, buys, v_idx))
                rows[(p_name, name, h)] = np.array(terms)
                v12[(p_name, name, h)] = np.array(vals)
                invests[(p_name, name, h)] = budget

    summary = []
    pooled: dict[str, dict[str, list]] = {}
    for p_name in PORTFOLIOS:
        per_port = []
        for name, _, _ in grid:
            t_all = np.concatenate([rows[(p_name, name, hy * 12)] for hy in horizons])
            v_all = np.concatenate([v12[(p_name, name, hy * 12)] for hy in horizons])
            b_all = np.concatenate(
                [np.full(len(rows[(p_name, name, hy * 12)]), invests[(p_name, name, hy * 12)]) for hy in horizons]
            )
            ls_all = np.concatenate([rows[(p_name, "ls", hy * 12)] for hy in horizons])
            underwater = v_all < b_all
            stats = {
                "portfolio": p_name,
                "strategy": name,
                "n": int(len(t_all)),
                "median": float(np.median(t_all)),
                "mean": float(np.mean(t_all)),
                "p5": float(np.percentile(t_all, 5)),
                "p95": float(np.percentile(t_all, 95)),
                "win_vs_ls": float(np.mean(t_all > ls_all)),
                "adv_median_vs_ls": float(np.median(t_all / ls_all - 1.0)),
                "adv_mean_vs_ls": float(np.mean(t_all / ls_all - 1.0)),
                "underwater_12m": float(np.mean(underwater)),
                "shortfall_12m_mean": float(np.mean((b_all - v_all)[underwater] / b_all[underwater]))
                if underwater.any()
                else 0.0,
            }
            per_port.append(stats)
            slot = pooled.setdefault(name, {"t": [], "v": [], "b": [], "ls": []})
            slot["t"].append(t_all)
            slot["v"].append(v_all)
            slot["b"].append(b_all)
            slot["ls"].append(ls_all)
        print(f"\n=== {p_name} (windfall X = 500 x months, {sum(window_counts.values())} windows) ===")
        print(f"{'strategy':<16}{'median':>11}{'mean':>11}{'p5':>10}{'p95':>11}"
              f"{'win>LS':>8}{'adv med':>9}{'adv mean':>10}{'underwater1y':>13}")
        print("-" * 98)
        for r in per_port:
            print(f"{r['strategy']:<16}{r['median']:>11,.0f}{r['mean']:>11,.0f}{r['p5']:>10,.0f}"
                  f"{r['p95']:>11,.0f}{r['win_vs_ls']:>7.0%} {r['adv_median_vs_ls']:>+8.1%}"
                  f"{r['adv_mean_vs_ls']:>+9.1%}{r['underwater_12m']:>12.0%}")
        summary.extend(per_port)

    print("\n=== pooled across portfolios (baseline ls) ===")
    print(f"{'strategy':<16}{'median':>11}{'win>LS':>8}{'adv med':>9}{'adv mean':>10}{'underwater1y':>13}")
    print("-" * 68)
    for name, _, _ in grid:
        slot = pooled[name]
        t_all = np.concatenate(slot["t"])
        v_all = np.concatenate(slot["v"])
        b_all = np.concatenate(slot["b"])
        ls_all = np.concatenate(slot["ls"])
        underwater = v_all < b_all
        stats = {
            "portfolio": "pooled",
            "strategy": name,
            "n": int(len(t_all)),
            "median": float(np.median(t_all)),
            "mean": float(np.mean(t_all)),
            "p5": float(np.percentile(t_all, 5)),
            "p95": float(np.percentile(t_all, 95)),
            "win_vs_ls": float(np.mean(t_all > ls_all)),
            "adv_median_vs_ls": float(np.median(t_all / ls_all - 1.0)),
            "adv_mean_vs_ls": float(np.mean(t_all / ls_all - 1.0)),
            "underwater_12m": float(np.mean(underwater)),
            "shortfall_12m_mean": float(np.mean((b_all - v_all)[underwater] / b_all[underwater]))
            if underwater.any()
            else 0.0,
        }
        summary.append(stats)
        print(f"{name:<16}{stats['median']:>11,.0f}{stats['win_vs_ls']:>7.0%} "
              f"{stats['adv_median_vs_ls']:>+8.1%}{stats['adv_mean_vs_ls']:>+9.1%}"
              f"{stats['underwater_12m']:>12.0%}")

    payload = {
        "params": {
            "contribution": args.contribution,
            "horizons_years": horizons,
            "splits": list(SPLITS),
            "tails_months": [t if t else "full" for t in TAILS],
            "dip_variant": DIP_VARIANT,
            "portfolios": PORTFOLIOS,
        },
        "data": {"range": [md.dates[0], md.dates[-1]], "sources": sources},
        "window_counts": window_counts,
        "summary": summary,
        "records": [
            {
                "portfolio": p_name,
                "strategy": name,
                "horizon_years": h // 12,
                "start": wins[i][0].key,
                "terminal": float(rows[(p_name, name, h)][i]),
                "value_12m": float(v12[(p_name, name, h)][i]),
                "budget": float(invests[(p_name, name, h)]),
            }
            for p_name in PORTFOLIOS
            for h, wins in all_windows.items()
            for i in range(len(wins))
            for name, _, _ in grid
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
