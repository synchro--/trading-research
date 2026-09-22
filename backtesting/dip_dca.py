#!/usr/bin/env python3
"""DCA timing study II: hindsight oracles vs naive DCA vs an implementable dip rule.

Follow-up to dca_vs_lumpsum.py with lump sum removed. Focal question: how much
does perfect monthly dip knowledge buy, and can an implementable rule capture
most of it?

The implementable rules (no lookahead — decisions use only dates up to the
current day), evaluated every day of each month on the fixed-weight composite:

  trigger day = first day of the month that is BOTH
    * a new running low of the month so far (lowest close of the month yet),
    * red — lower than the previous trading day's close
  v2 additionally requires the day to be >= 3% below the rolling 20-market-day
  high (comp[d] <= 0.97 * max(composite over the last 20 closes)).

  dip2x_half    v2: triggered month deploys 2x the contribution (1000) on the
                trigger day; the FOLLOWING month absorbs a haircut and deploys
                only 250 ("double this month, half the month after"). A
                triggered month after a trigger chains the haircut forward.
  dip2x_neutral v2, budget-neutral control: same 2x but the following month
                pays the full 500 back (deploys 0).
  dip_shift     v1: triggered month deploys the normal 500 on the trigger day
                instead of mid-month (matched capital, pure signal timing)
  dip_double_v1 v1: triggered month deploys 2x, no haircut (extra capital)
  dip2x_5pct15d v2 with a deeper/wider trigger: >= 5% dip vs 15-day high
  dip2x_consec2 v2, trigger requires 2 consecutive red running-low days
  dip6m_deep    6-month cycle version: deep dips deploy cycle-accumulated cash,
                leftovers at the cycle's last mid-month (budget-neutral)
  dca_mid       baseline: 1x at the first trading day on/after the 15th

Oracle benchmarks (reused from dca_vs_lumpsum): oracle_1m, oracle_pt_3m/6m,
oracle_cy_3m/6m — hindsight, upper bounds only.

Same market model, costs, data and window scheme as dca_vs_lumpsum.py:
Yahoo total-return daily bars 2004-12 -> latest complete month, horizons
{10,12,14,16,18,20}y x every monthly start, waiting cash at ^IRX, 10+5 bps
costs per ETF leg, annual rebalance, nominal USD with EUR labels.

Because dip_double invests extra capital by design, stats are reported both on
absolute terminal wealth and on EUR-for-EUR timing return (terminal / nominal
invested within each window), which isolates timing quality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from backtesting.dca_vs_lumpsum import (
    CONTRIBUTION,
    PORTFOLIOS,
    enumerate_windows,
    load_experiment,
    plan_strategy,
    run_window,
)

ORACLE_STRATEGIES = ("oracle_1m", "oracle_pt_3m", "oracle_pt_6m", "oracle_cy_3m", "oracle_cy_6m")
DIP_STRATEGIES = (
    "dip_shift",
    "dip_double_v1",
    "dip2x_half",
    "dip2x_neutral",
    "dip2x_5pct15d",
    "dip2x_consec2",
    "dip6m_deep",
)
STRATEGIES = ("dca_mid",) + DIP_STRATEGIES + ORACLE_STRATEGIES

# dip rule configuration
ROLL_WINDOW = 20          # default "last rolling N market days"
DIP_DD = 0.03             # default trigger requires >= 3% below the rolling high
DIP_CONFIG: dict[str, dict[str, float | int | str]] = {
    # v1 rules (shallow trigger: monthly running low + red) kept for comparison
    "dip_shift": {"trigger": "v1", "factor": 1.0, "neighbor": 0.0},
    "dip_double_v1": {"trigger": "v1", "factor": 2.0, "neighbor": 0.0},
    # v2 rules: trigger month deploys 2x, the following month absorbs a haircut
    "dip2x_half": {"trigger": "deep", "dd": 0.03, "win": 20, "factor": 2.0, "neighbor": 0.5},
    "dip2x_neutral": {"trigger": "deep", "dd": 0.03, "win": 20, "factor": 2.0, "neighbor": 0.0},
    # round-3 refinements
    "dip2x_5pct15d": {"trigger": "deep", "dd": 0.05, "win": 15, "factor": 2.0, "neighbor": 0.5},
    "dip2x_consec2": {
        "trigger": "deep", "dd": 0.03, "win": 20, "factor": 2.0, "neighbor": 0.5,
        "min_consec": 2,  # needs 2 consecutive red running-low days
    },
    # cycle version: within each 6-month cycle, every deep red running-low day
    # deploys the cash accumulated so far in that cycle; leftovers deploy at the
    # mid of the last cycle month (budget-neutral, no haircut)
    "dip6m_deep": {"trigger": "cycle6m", "dd": 0.03, "win": 20},
}


def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    """Max of each trailing window (inclusive of the current day)."""
    arr = np.asarray(arr, dtype=float)
    if len(arr) < window:
        high = float(arr.max())
        return np.full(len(arr), high)
    out = sliding_window_view(arr, window).max(axis=1)
    pad = np.full(window - 1, np.max(arr[:window]))
    return np.concatenate([pad, out])


def find_trigger_in_days(
    comp: np.ndarray,
    days: list[int],
    roll_max: np.ndarray | None = None,
    dd: float | None = None,
    min_consec: int = 1,
) -> int | None:
    """First day in `days` that satisfies the trigger, or None.

    Conditions: running low of the span so far (strictly below every earlier
    close in `days`), red (below the previous trading day's close), and — when
    a roll_max is given — at least `dd` (default DIP_DD) below the trailing
    high of the last `window` closes. `min_consec` requires that many
    consecutive qualifying days before firing (day of the Nth qualifying day)."""
    dd_eff = (DIP_DD if dd is None else dd) if roll_max is not None else 0.0
    running_min = None
    streak = 0
    for d in days:
        new_low = running_min is None or comp[d] < running_min
        red = d > 0 and comp[d] < comp[d - 1]
        deep = True if roll_max is None else comp[d] <= (1.0 - dd_eff) * roll_max[d]
        if new_low and red and deep:
            streak += 1
            if streak >= min_consec:
                return d
        else:
            streak = 0
        running_min = comp[d] if running_min is None else min(running_min, comp[d])
    return None


def find_trigger_day(
    comp: np.ndarray,
    month,
    roll_max: np.ndarray | None = None,
    dd: float | None = None,
    min_consec: int = 1,
) -> int | None:
    """First qualifying day of the month (monthly running-low variant)."""
    return find_trigger_in_days(comp, list(month.days), roll_max, dd, min_consec)


def plan_dip(
    strategy: str,
    comp: np.ndarray,
    months: list,
    contribution: float = CONTRIBUTION,
    roll_max: np.ndarray | None = None,
):
    """Return (buy events, rebalance days, per-window nominal invested, meta).

    Capital flow: a triggered month deploys factor x contribution on the
    trigger day; the NEXT month absorbs a haircut (neighbor fraction of the
    contribution; 0.5 = literally "half the month after"). A triggered month
    following another trigger overrides the haircut and chains it one month
    further. Mid-month fallback for untriggered months."""
    cfg = DIP_CONFIG[strategy]
    if cfg["trigger"] == "cycle6m":
        return plan_cycle_deep(
            comp, months, contribution, int(cfg["win"]),
            float(cfg["dd"]), roll_max,
        )
    factor, neighbor_frac = float(cfg["factor"]), float(cfg["neighbor"])
    dd = float(cfg.get("dd", 0.0))
    min_consec = int(cfg.get("min_consec", 1))
    buys: list[tuple[int, list[tuple[float, int]]]] = []
    invested: list[float] = []
    triggered = 0
    haircut = 0.0
    for m in months:
        trigger = find_trigger_day(
            comp, m,
            roll_max if str(cfg["trigger"]).startswith("deep") else None,
            dd, min_consec,
        )
        if trigger is not None:
            triggered += 1
            amount = contribution * factor
            haircut = contribution * neighbor_frac
            buys.append((trigger, [(amount, m.first)]))
            invested.append(amount)
        else:
            amount = contribution - haircut
            haircut = 0.0
            if amount > 1e-9:
                buys.append((m.mid, [(amount, m.first)]))
                invested.append(amount)
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    meta = {"triggered_months": triggered, "months": len(months)}
    if strategy == "dip_shift":  # matched-capital variant keeps the identity
        assert abs(sum(invested) - contribution * len(months)) < 1e-6
    return buys, rebalance_days, np.array(invested, dtype=float), meta


def plan_cycle_deep(
    comp: np.ndarray,
    months: list,
    contribution: float,
    window: int,
    dd: float,
    roll_max: np.ndarray | None,
    cycle_len: int = 6,
):
    """Trigger = red + new running low OF THE CYCLE + deep vs 20-day high.

    Every contribution accrues from its month's first trading day. On each
    qualifying day inside the cycle, all contributions accumulated so far in
    the cycle deploy at that day's close. Leftover (a cycle whose later
    contributions see no further qualifying day) deploy at the mid of the
    cycle's last month. Strictly budget-neutral per cycle."""
    buys: list[tuple[int, list[tuple[float, int]]]] = []
    invested: list[float] = []
    fired_events = 0
    for c in range(0, len(months), cycle_len):
        group = months[c : c + cycle_len]
        cycle_min = None
        pending: list[tuple[float, int]] = []
        for gi, m in enumerate(group):
            for d in m.days:
                if d == m.first:
                    pending.append((contribution, m.first))
                new_low = cycle_min is None or comp[d] < cycle_min
                red = d > 0 and comp[d] < comp[d - 1]
                deep = comp[d] <= (1.0 - dd) * float(roll_max[d])
                if new_low and red and deep and pending:
                    buys.append((d, pending))
                    invested.append(contribution * len(pending))
                    fired_events += 1
                    pending = []
                cycle_min = comp[d] if cycle_min is None else min(cycle_min, comp[d])
        last = group[-1]
        if pending:
            buys.append((last.mid, pending))
            invested.append(contribution * len(pending))
        else:
            fired_events += 1  # cycle ended fully invested
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    assert abs(sum(invested) - contribution * len(months)) < 1e-6, (
        f"{sum(invested)} != {contribution * len(months)}"
    )
    meta = {
        "triggered_months": fired_events,
        "months": len(months),
        "note": "fired cycle-deploy events (hindsight-free)",
    }
    return buys, rebalance_days, np.array(invested, dtype=float), meta


def plan(strategy: str, comp, months, contribution, roll_by_window=None):
    """Uniform planner for all DCA-family strategies."""
    if strategy == "lump_sum":
        raise ValueError("lump_sum excluded from this study")
    if strategy in DIP_CONFIG:
        cfg = DIP_CONFIG[strategy]
        roll = None
        if str(cfg["trigger"]).startswith(("deep", "cycle")):
            win = int(cfg["win"])
            roll = (roll_by_window or {}).get(win)
            if roll is None:
                raise KeyError(f"missing rolling max for window {win}")
        return plan_dip(strategy, comp, months, contribution, roll)
    buys, rbd = plan_strategy(strategy, comp, months, contribution)
    invested = np.full(len(months), contribution)
    return buys, rbd, invested, {}


def summarize(terminals, invested, dca_terminals, dca_invested) -> dict:
    per_euro = terminals / invested
    dca_per_euro = dca_terminals / dca_invested
    return {
        "n": int(len(terminals)),
        "median_invested": float(np.median(invested)),
        "mean_invested": float(np.mean(invested)),
        "median": float(np.median(terminals)),
        "mean": float(np.mean(terminals)),
        "p5": float(np.percentile(terminals, 5)),
        "p25": float(np.percentile(terminals, 25)),
        "p75": float(np.percentile(terminals, 75)),
        "p95": float(np.percentile(terminals, 95)),
        "win_vs_dca_mid": float(np.mean(terminals > dca_terminals)),
        "adv_median_vs_dca_mid": float(np.median(terminals / dca_terminals - 1.0)),
        "adv_mean_vs_dca_mid": float(np.mean(terminals / dca_terminals - 1.0)),
        "per_euro_adv_median_vs_dca": float(np.median(per_euro / dca_per_euro - 1.0)),
        "per_euro_adv_mean_vs_dca": float(np.mean(per_euro / dca_per_euro - 1.0)),
    }


def main() -> None:
    from backtesting.engine.data import DATA_DIR

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--horizons", default="10,12,14,16,18,20")
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--reuse-cache", action="store_true", help="skip deep refetch")
    p.add_argument("--out", default=str(DATA_DIR / "dip_dca.json"))
    args = p.parse_args()

    md, sources = load_experiment(args.end, force=not args.reuse_cache)
    horizons = [int(h) for h in args.horizons.split(",")]
    all_windows: dict[int, list] = {}
    window_counts: dict[int, int] = {}
    for h_years in horizons:
        all_windows[h_years * 12] = [ms for _, ms in enumerate_windows(md, h_years * 12)]
        window_counts[h_years] = len(all_windows[h_years * 12])
    print(f"data {md.dates[0]} -> {md.dates[-1]}, {len(md.dates)} common days; windows {window_counts}")

    terminals: dict[tuple[str, str, int], np.ndarray] = {}
    invested: dict[tuple[str, str, int], np.ndarray] = {}
    trigger_stats: dict[tuple[str, str, int], dict] = {}
    comp_cache: dict[str, np.ndarray] = {}
    roll_cache: dict[str, dict[int, np.ndarray]] = {}
    for p_name, weights in PORTFOLIOS.items():
        if p_name not in comp_cache:
            c = md.composite(weights)
            comp_cache[p_name] = c
            roll_cache[p_name] = {
                win: rolling_max(c, win) for win in sorted({int(cfg["win"]) for cfg in DIP_CONFIG.values() if "win" in cfg})
            }
        comp = comp_cache[p_name]
        for h, wins in all_windows.items():
            for strategy in STRATEGIES:
                terms, caps, trig = [], [], {}
                for months in wins:
                    buys, rbd, cap, meta = plan(
                        strategy, comp, months, args.contribution, roll_cache[p_name]
                    )
                    terms.append(run_window(md, weights, months, buys, rbd))
                    caps.append(float(cap.sum()))
                    if meta:
                        trig = meta
                terminals[(p_name, strategy, h)] = np.array(terms)
                invested[(p_name, strategy, h)] = np.array(caps)
                if trig:
                    trigger_stats[(p_name, strategy, h)] = trig

    summary_rows: list[dict] = []
    horizon_medians: dict[str, dict[str, dict[int, float]]] = {}
    pooled: dict[str, dict[str, list]] = {}
    for p_name in PORTFOLIOS:
        rows: list[dict] = []
        hm: dict[str, dict[int, float]] = {}
        for strategy in STRATEGIES:
            t_all = np.concatenate([terminals[(p_name, strategy, h * 12)] for h in horizons])
            c_all = np.concatenate([invested[(p_name, strategy, h * 12)] for h in horizons])
            dt_all = np.concatenate([terminals[(p_name, "dca_mid", h * 12)] for h in horizons])
            dc_all = np.concatenate([invested[(p_name, "dca_mid", h * 12)] for h in horizons])
            stats = summarize(t_all, c_all, dt_all, dc_all)
            stats.update({"portfolio": p_name, "strategy": strategy})
            trig_rows = [trigger_stats[(p_name, strategy, h * 12)] for h in horizons if (p_name, strategy, h * 12) in trigger_stats]
            if trig_rows:
                total_months = sum(t["months"] for t in trig_rows)
                trig_total = sum(t["triggered_months"] for t in trig_rows)
                stats["triggered_months_pct"] = trig_total / total_months if total_months else None
            rows.append(stats)
            hm[strategy] = {
                h: float(np.median(terminals[(p_name, strategy, h * 12)])) for h in horizons
            }
            slot = pooled.setdefault(strategy, {"t": [], "c": [], "dt": [], "dc": []})
            slot["t"].append(t_all)
            slot["c"].append(c_all)
            slot["dt"].append(dt_all)
            slot["dc"].append(dc_all)
        horizon_medians[p_name] = hm
        print(f"\n=== {p_name} ({sum(window_counts.values())} windows, contrib {args.contribution:.0f}/mo) ===")
        print(
            f"{'strategy':<18}{'median':>11}{'mean':>11}{'p5':>10}{'p95':>11}"
            f"{'inv med':>9}{'win>dca':>9}{'adv med':>9}{'adv mean':>10}"
            f"{'€/€ med':>9}{'€/€ mean':>10}"
        )
        print("-" * 120)
        best = max(rows, key=lambda r: r["per_euro_adv_median_vs_dca"])
        for r in rows:
            star = "*" if r["strategy"] == best["strategy"] else " "
            trig = r.get("triggered_months_pct")
            name = r["strategy"] + (f" ({trig:.0%}trig)" if isinstance(trig, float) else "")
            print(
                f"{name:<18}{r['median']:>11,.0f}{r['mean']:>11,.0f}{r['p5']:>10,.0f}"
                f"{r['p95']:>11,.0f}{r['median_invested']:>9,.0f}"
                f"{r['win_vs_dca_mid']:>8.0%} {r['adv_median_vs_dca_mid']:>+8.1%}"
                f"{r['adv_mean_vs_dca_mid']:>+9.1%}{r['per_euro_adv_median_vs_dca']:>+8.1%}"
                f"{r['per_euro_adv_mean_vs_dca']:>+9.1%} {star}"
            )
        summary_rows.extend(rows)

    print("\n=== pooled across portfolios (all windows, baseline dca_mid median) ===")
    print(f"{'strategy':<18}{'win>dca':>9}{'adv med':>9}{'adv mean':>10}{'€/€ med':>9}{'€/€ mean':>10}{'inv med':>10}")
    print("-" * 80)
    pooled_rows = []
    for strategy in STRATEGIES:
        slot = pooled[strategy]
        t_all = np.concatenate(slot["t"])
        c_all = np.concatenate(slot["c"])
        dt_all = np.concatenate(slot["dt"])
        dc_all = np.concatenate(slot["dc"])
        stats = summarize(t_all, c_all, dt_all, dc_all)
        stats.update({"portfolio": "pooled", "strategy": strategy})
        pooled_rows.append(stats)
        print(
            f"{strategy:<18}{stats['win_vs_dca_mid']:>8.0%} {stats['adv_median_vs_dca_mid']:>+8.1%}"
            f"{stats['adv_mean_vs_dca_mid']:>+9.1%}{stats['per_euro_adv_median_vs_dca']:>+8.1%}"
            f"{stats['per_euro_adv_mean_vs_dca']:>+9.1%}{stats['median_invested']:>10,.0f}"
        )
    summary_rows.extend(pooled_rows)
    print(
        "\nadv columns: absolute terminal advantage (dip_double invests extra capital by design); "
        "EUR-for-EUR (€/€) columns compare timing return (terminal / nominal invested)."
    )

    # sanity anchor: 2008-07 10y stocks_100 with dip rule trigger counts
    print("\n=== sanity: 2008-07 start, 10y, stocks_100 — terminal (invested) ===")
    w_start = next(i for i, m in enumerate(md.months) if m.key == "2008-07")
    gfc_months = md.months[w_start : w_start + 120]
    gfc_comp = comp_cache["stocks_100"]
    for strategy in STRATEGIES:
        buys, rbd, cap, meta = plan(
            strategy, gfc_comp, gfc_months, args.contribution, roll_cache["stocks_100"]
        )
        term = run_window(md, PORTFOLIOS["stocks_100"], gfc_months, buys, rbd)
        trig = meta.get("triggered_months") if meta else "-"
        print(f"  {strategy:<14} {term:>12,.0f}  ({cap.sum():>8,.0f})  triggers {trig}")

    payload = {
        "params": {
            "contribution": args.contribution,
            "horizons_years": horizons,
            "dip_rule": (
                "trigger = first red running-low composite day of the month; "
                "v2 adds >=3% dip vs rolling 20-market-day high. dip2x_half: 2x on trigger, "
                "next month 0.5x; dip2x_neutral: 2x on trigger, next month 0x."
            ),
            "portfolios": PORTFOLIOS,
            "strategies": list(STRATEGIES),
        },
        "data": {
            "range": [md.dates[0], md.dates[-1]],
            "common_days": len(md.dates),
            "sources": sources,
        },
        "window_counts": window_counts,
        "summary": summary_rows,
        "horizon_medians": horizon_medians,
        "records": [
            {
                "portfolio": p_name,
                "strategy": strategy,
                "horizon_years": h,
                "start": wins[i][0].key,
                "invested": float(invested[(p_name, strategy, h)][i]),
                "terminal": float(terminals[(p_name, strategy, h)][i]),
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
