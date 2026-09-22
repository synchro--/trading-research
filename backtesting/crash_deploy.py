#!/usr/bin/env python3
"""Cash-is-king study: hold the budget in the money-market fund and deploy it
only after a big drawdown, versus lump-sum day 0.

Windfall framing, identical budget to the other studies: X = contribution x
months sits in the MMF at t0 (accruing ^IRX) and is deployed only when the
implementable crash trigger fires:

    dd_t = 1 - comp[t] / max(comp over the trailing 2 calendar years)
    trigger when dd_t >= threshold

Strategies (all budgets identical; whatever is never deployed stays in the MMF
and still counts in the terminal wealth, so "never triggered" is a real,
visibly bad outcome):

  ls              baseline: all X invested at day 0
  wait20_lump     all X deployed on the first day dd >= 20%
  wait30_lump     all X deployed on the first day dd >= 30%
  wait20_dca12    X/12 deployed at the trigger day and on each of the next 11
                  monthly mid-month days (DCA after the crash)
  wait20_tranches thirds deployed on the first days dd >= 10% / 20% / 30%
  parked          never deployed (pure MMF), the degenerate control

No lookahead: the drawdown is measured on past prices only.
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
)
from backtesting.mm_cushion import rolling_max_calendar, run_cushion_window

LOOKBACK_CAL_DAYS = 730  # trailing 2 calendar years
STRATEGIES = ("ls", "wait20_lump", "wait30_lump", "wait20_dca12", "wait20_tranches", "parked")


def find_dd_day(comp: np.ndarray, roll: np.ndarray, months: list, dd: float) -> int | None:
    """First trading day of the window with drawdown >= dd (or None)."""
    for m in months:
        for d in m.days:
            if comp[d] <= (1.0 - dd) * roll[d]:
                return d
    return None


def plan_crash(strategy: str, comp, roll, months, budget: float):
    """Return (buys, rebalance_days, meta). Buys draw from the MMF pool."""
    buys: list[tuple[int, list[tuple[str, float, int]]]] = []
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    meta = {"triggered": False, "months_to_trigger": None}
    if strategy == "parked":
        return buys, rebalance_days, meta
    if strategy == "ls":
        buys.append((months[0].first, [("mmf", budget, months[0].first)]))
        meta["triggered"] = True
        meta["months_to_trigger"] = 0
        return buys, rebalance_days, meta
    if strategy == "wait20_lump":
        day = find_dd_day(comp, roll, months, 0.20)
        if day is not None:
            buys.append((day, [("mmf", budget, day)]))
            meta["triggered"] = True
    elif strategy == "wait30_lump":
        day = find_dd_day(comp, roll, months, 0.30)
        if day is not None:
            buys.append((day, [("mmf", budget, day)]))
            meta["triggered"] = True
    elif strategy == "wait20_dca12":
        day = find_dd_day(comp, roll, months, 0.20)
        if day is not None:
            meta["triggered"] = True
            k = next(i for i, m in enumerate(months) if day <= m.last)
            legs = min(12, len(months) - k)  # compress if the window ends sooner
            tranche = budget / legs
            buys.append((day, [("mmf", tranche, day)]))
            for j in range(1, legs):
                buys.append((months[k + j].mid, [("mmf", tranche, months[k + j].mid)]))
    elif strategy == "wait20_tranches":
        for dd, frac in ((0.10, 1 / 3), (0.20, 1 / 3), (0.30, 1 / 3)):
            day = find_dd_day(comp, roll, months, dd)
            if day is not None:
                meta["triggered"] = True
                buys.append((day, [("mmf", budget * frac, day)]))
    if meta["triggered"]:
        first_day = min(d for d, _ in buys)
        meta["first_day"] = first_day
        meta["months_to_trigger"] = next(
            i for i, m in enumerate(months) if first_day <= m.last
        )
    return buys, rebalance_days, meta


def main() -> None:
    from backtesting.engine.data import DATA_DIR

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--horizons", default="10,12,14,16,18,20")
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--reuse-cache", action="store_true")
    p.add_argument("--out", default=str(DATA_DIR / "crash_deploy.json"))
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
    results: dict[tuple[str, str, int], dict[str, np.ndarray]] = {}
    for p_name, weights in PORTFOLIOS.items():
        if p_name not in comp_cache:
            comp = md.composite(weights)
            comp_cache[p_name] = comp
            roll_cache[p_name] = rolling_max_calendar(comp, list(md.dates), LOOKBACK_CAL_DAYS)
        comp, roll = comp_cache[p_name], roll_cache[p_name]
        for h, wins in all_windows.items():
            budget = args.contribution * h
            for strategy in STRATEGIES:
                terms, mmf_left, trig, mtt, deployed = [], [], [], [], []
                for months in wins:
                    buys, rbd, meta = plan_crash(strategy, comp, roll, months, budget)
                    # every strategy holds the windfall in the MMF at t0; ls just
                    # draws it all on day 0
                    res = run_cushion_window(md, weights, months, buys, rbd, mmf0=budget)
                    terms.append(res["terminal"])
                    mmf_left.append(res["mmf_left"])
                    trig.append(1.0 if meta["triggered"] else 0.0)
                    if meta.get("months_to_trigger") is not None:
                        mtt.append(float(meta["months_to_trigger"]))
                    deployed.append(budget - res["mmf_left"])
                results[(p_name, strategy, h)] = {
                    "t": np.array(terms),
                    "mmf": np.array(mmf_left),
                    "trig": np.array(trig),
                    "mtt": np.array(mtt) if mtt else np.array([np.nan]),
                    "deployed": np.array(deployed),
                }

    summary = []
    pooled: dict[str, dict[str, list]] = {}
    for p_name in PORTFOLIOS:
        print(f"\n=== {p_name} (windfall X = 500 x months, {sum(window_counts.values())} windows) ===")
        print(f"{'strategy':<16}{'median':>11}{'mean':>11}{'p5':>10}{'p95':>11}"
              f"{'win>LS':>8}{'adv med':>9}{'adv mean':>10}{'trig%':>7}{'med mo':>8}{'cash left':>11}")
        print("-" * 114)
        ls_all = np.concatenate([results[(p_name, "ls", hy * 12)]["t"] for hy in horizons])
        for strategy in STRATEGIES:
            t_all = np.concatenate([results[(p_name, strategy, hy * 12)]["t"] for hy in horizons])
            mmf_all = np.concatenate([results[(p_name, strategy, hy * 12)]["mmf"] for hy in horizons])
            trig_all = np.concatenate([results[(p_name, strategy, hy * 12)]["trig"] for hy in horizons])
            mtt_all = np.concatenate([results[(p_name, strategy, hy * 12)]["mtt"] for hy in horizons])
            stats = {
                "portfolio": p_name,
                "strategy": strategy,
                "n": int(len(t_all)),
                "median": float(np.median(t_all)),
                "mean": float(np.mean(t_all)),
                "p5": float(np.percentile(t_all, 5)),
                "p95": float(np.percentile(t_all, 95)),
                "win_vs_ls": float(np.mean(t_all > ls_all)),
                "adv_median_vs_ls": float(np.median(t_all / ls_all - 1.0)),
                "adv_mean_vs_ls": float(np.mean(t_all / ls_all - 1.0)),
                "trigger_rate": float(np.mean(trig_all)),
                "median_months_to_trigger": float(np.nanmedian(mtt_all)) if np.isfinite(mtt_all).any() else None,
                "median_mmf_left": float(np.median(mmf_all)),
            }
            summary.append(stats)
            slot = pooled.setdefault(strategy, {"t": [], "mmf": [], "trig": [], "mtt": [], "ls": []})
            slot["t"].append(t_all)
            slot["mmf"].append(mmf_all)
            slot["trig"].append(trig_all)
            slot["mtt"].append(mtt_all)
            slot["ls"].append(ls_all)
            med_mo = f"{stats['median_months_to_trigger']:>8.0f}" if stats["median_months_to_trigger"] is not None else f"{'-':>8}"
            print(f"{strategy:<16}{stats['median']:>11,.0f}{stats['mean']:>11,.0f}"
                  f"{stats['p5']:>10,.0f}{stats['p95']:>11,.0f}{stats['win_vs_ls']:>7.0%} "
                  f"{stats['adv_median_vs_ls']:>+8.1%}{stats['adv_mean_vs_ls']:>+9.1%}"
                  f"{stats['trigger_rate']:>6.0%}{med_mo}{stats['median_mmf_left']:>11,.0f}")

    print("\n=== pooled across portfolios (baseline ls) ===")
    print(f"{'strategy':<16}{'median':>11}{'win>LS':>8}{'adv med':>9}{'adv mean':>10}{'trig%':>7}{'cash left':>11}")
    print("-" * 72)
    for strategy in STRATEGIES:
        slot = pooled[strategy]
        t_all = np.concatenate(slot["t"])
        ls_all = np.concatenate(slot["ls"])
        mmf_all = np.concatenate(slot["mmf"])
        trig_all = np.concatenate(slot["trig"])
        stats = {
            "portfolio": "pooled",
            "strategy": strategy,
            "n": int(len(t_all)),
            "median": float(np.median(t_all)),
            "mean": float(np.mean(t_all)),
            "p5": float(np.percentile(t_all, 5)),
            "p95": float(np.percentile(t_all, 95)),
            "win_vs_ls": float(np.mean(t_all > ls_all)),
            "adv_median_vs_ls": float(np.median(t_all / ls_all - 1.0)),
            "adv_mean_vs_ls": float(np.mean(t_all / ls_all - 1.0)),
            "trigger_rate": float(np.mean(trig_all)),
            "median_mmf_left": float(np.median(mmf_all)),
        }
        summary.append(stats)
        print(f"{strategy:<16}{stats['median']:>11,.0f}{stats['win_vs_ls']:>7.0%} "
              f"{stats['adv_median_vs_ls']:>+8.1%}{stats['adv_mean_vs_ls']:>+9.1%}"
              f"{stats['trigger_rate']:>6.0%}{stats['median_mmf_left']:>11,.0f}")

    payload = {
        "params": {
            "contribution": args.contribution,
            "horizons_years": horizons,
            "lookback_calendar_days": LOOKBACK_CAL_DAYS,
            "strategies": list(STRATEGIES),
            "portfolios": PORTFOLIOS,
        },
        "data": {"range": [md.dates[0], md.dates[-1]], "sources": sources},
        "window_counts": window_counts,
        "summary": summary,
        "records": [
            {
                "portfolio": p_name,
                "strategy": strategy,
                "horizon_years": h // 12,
                "start": wins[i][0].key,
                "terminal": float(results[(p_name, strategy, h)]["t"][i]),
                "mmf_left": float(results[(p_name, strategy, h)]["mmf"][i]),
            }
            for p_name in PORTFOLIOS
            for h, wins in all_windows.items()
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
