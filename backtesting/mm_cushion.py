#!/usr/bin/env python3
"""Money-market cushion study: one budget (30k reserve + 500/mo income), four
allocation policies, rolling 10-20y windows.

Budget equality (the "compute the calculations" part): all four approaches
receive the identical pools — 30k available at the window start plus the
500/month income stream for every month of the window. What differs is only
where that money sits and when it is deployed into the ETF portfolio:

1. lump_sum_30k   the reserve is invested at day 0 and every incoming 500 on
                  its arrival (mid-month): zero idle cash after day 0.
2. dca_cushion    500/mo at mid-month + 30k untouched in a money-market fund
                  (XEON-like; modeled at the ^IRX T-bill proxy since these
                  bars are nominal USD) — accrues simple y/360 per calendar day.
3. oracle_cushion as (2), but each month's 500 buys at the month's lowest
                  composite close (hindsight benchmark for approach 4).
4. dip2x_mm       500/mo normally; when an ETF day is BOTH red (below the
                  previous trading day close) AND at least 3% below the
                  previous-30-day rolling high AND within the first two weeks
                  of the month, the month deploys 1000 that day: 500 income +
                  500 DRAWN FROM the reserve (draw capped at the remaining
                  balance). Same total budget; equities get more, less stays
                  in the MMF.

Notes:
* the MMF is an external account: annual rebalancing only touches ETF sleeves
  (incl. golden_butterfly's internal 20% cash sleeve, kept unchanged)
* fills at the chosen day's close, 10 bps commission + 5 bps slippage per ETF
  leg, fractional shares, no TER/taxes; windows/parent study conventions apply
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from backtesting.dca_vs_lumpsum import (
    COMM,
    CONTRIBUTION,
    SLIP,
    PORTFOLIOS,
    enumerate_windows,
    load_experiment,
    plan_strategy,
)

INITIAL_MM = 30_000.0   # money-market reserve (approaches 2-4)
CAL_WINDOW = 30         # "previous 30 day rolling window" (calendar days)
TRIGGER_DD = 0.03       # >= 3% below the rolling high
HALF_MONTH = 14         # trigger only within the first two weeks
STRATEGIES = ("lump_sum_30k", "dca_cushion", "oracle_cushion", "dip2x_mm")


def rolling_max_calendar(arr: np.ndarray, dates: list[str], cal_days: int) -> np.ndarray:
    """Max of each trailing calendar-day window (inclusive), two-pointer."""
    arr = np.asarray(arr, dtype=float)
    out = np.empty(len(arr), dtype=float)
    lo = 0
    for i in range(len(arr)):
        lim = date.fromisoformat(dates[i]).toordinal() - (cal_days - 1)
        while date.fromisoformat(dates[lo]).toordinal() < lim:
            lo += 1
        out[i] = arr[lo : i + 1].max()
    return out


def find_mm_trigger(
    comp: np.ndarray, roll30: np.ndarray, month, dates: list[str]
) -> int | None:
    """First day in the month's first two weeks that is red AND >= 3% below
    the previous-30-day high. Returns the day index or None."""
    for d in month.days:
        if int(dates[d][8:10]) > HALF_MONTH:
            break
        red = d > 0 and comp[d] < comp[d - 1]
        if red and comp[d] <= (1.0 - TRIGGER_DD) * roll30[d]:
            return d
    return None


def plan_cushion(
    strategy: str,
    comp: np.ndarray,
    roll30: np.ndarray,
    months: list,
    dates: list[str],
    contribution: float = CONTRIBUTION,
):
    """Return (buys, rebalance_days, meta).

    buys: [(day, tranches)]; tranches are (kind, amount, anchor) with kind
    "income" (accrues T-bill interest from anchor to deploy day) or "mmf"
    (drawn from the reserve at par, capped by the pool balance)."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}")
    buys: list[tuple[int, list[tuple[str, float, int]]]] = []
    triggered = 0
    if strategy == "lump_sum_30k":
        buys.append((months[0].first, [("income", INITIAL_MM, months[0].first)]))
        buys.extend((m.mid, [("income", contribution, m.first)]) for m in months)
    elif strategy in ("dca_cushion", "oracle_cushion"):
        legacy = "dca_mid" if strategy == "dca_cushion" else "oracle_1m"
        legacy_buys, _rbd = plan_strategy(legacy, comp, months, contribution)
        buys.extend(
            (day, [("income", amount, anchor) for amount, anchor in trs])
            for day, trs in legacy_buys
        )
    elif strategy == "dip2x_mm":
        for m in months:
            trigger = find_mm_trigger(comp, roll30, m, dates)
            if trigger is not None:
                triggered += 1
                buys.append(
                    (trigger, [("income", contribution, m.first), ("mmf", contribution, m.first)])
                )
            else:
                buys.append((m.mid, [("income", contribution, m.first)]))
    else:  # pragma: no cover
        raise ValueError(strategy)
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    meta = {"triggered_months": triggered, "months": len(months)}
    return buys, rebalance_days, meta


def run_cushion_window(
    md,
    weights: dict[str, float],
    months: list,
    buys: list[tuple[int, list[tuple[str, float, int]]]],
    rebalance_days: list[int],
    mmf0: float = 0.0,
) -> dict:
    """Portfolio ledger plus an external money-market pool.

    Income tranches accrue the T-bill rate from their anchor day to their
    deploy day; "mmf" tranches draw from the pool at par (capped by balance).
    The pool accrues interest daily and is never touched by rebalances.
    Returns {"terminal", "mmf_left", "mmf_drawn"} — terminal includes the
    leftover MMF."""
    symbols = [s for s in weights if s != "CASH"]
    w = np.array([weights[s] for s in symbols], dtype=float)
    w_cash = weights.get("CASH", 0.0)
    close = np.stack([md.closes[s] for s in symbols])
    shares = np.zeros(len(symbols), dtype=float)
    gb = 0.0  # GB's internal cash sleeve (participates in annual rebalances)
    gb_anchor = months[0].first
    mmf = float(mmf0)
    mm_anchor = months[0].first
    drawn_total = 0.0

    def factor(day: int, anchor: int) -> float:
        if day <= anchor:
            return 1.0
        return float(np.exp(md.cumlog[day] - md.cumlog[anchor]))

    buy_map: dict[int, list[list[tuple[str, float, int]]]] = {}
    for day, trs in buys:
        buy_map.setdefault(day, []).append(trs)
    events = sorted({*buy_map, *rebalance_days})

    for day in events:
        if gb_anchor < day:
            gb *= factor(day, gb_anchor)
            gb_anchor = day
        if mm_anchor < day:
            mmf *= factor(day, mm_anchor)
            mm_anchor = day
        if day in rebalance_days:
            vals = shares * close[:, day]
            total = float(vals.sum()) + gb
            pool = gb
            targets = w * total
            for i in np.where(vals > targets + 1e-9)[0]:
                sell = float(vals[i] - targets[i])
                shares[i] -= sell / close[i, day]
                pool += sell * (1.0 - SLIP) * (1.0 - COMM)
            for i in np.where(vals < targets - 1e-9)[0]:
                spend = min(float(targets[i] - vals[i]), pool)
                if spend <= 0:
                    continue
                shares[i] += spend / (close[i, day] * (1.0 + SLIP) * (1.0 + COMM))
                pool -= spend
            gb = pool
        if day in buy_map:
            cash_in = 0.0
            for trs in buy_map[day]:
                for kind, amount, anchor in trs:
                    if kind == "income":
                        cash_in += amount * factor(day, anchor)
                    elif kind == "mmf":
                        take = min(amount, mmf)
                        mmf -= take
                        drawn_total += take
                        cash_in += take
                    else:  # pragma: no cover
                        raise RuntimeError(f"unknown tranche kind {kind!r}")
            if w_cash:
                gb += cash_in * w_cash
            shares += (cash_in * w) / (close[:, day] * (1.0 + SLIP) * (1.0 + COMM))

    end_idx = months[-1].last
    if gb_anchor < end_idx:
        gb *= factor(end_idx, gb_anchor)
    if mm_anchor < end_idx:
        mmf *= factor(end_idx, mm_anchor)
    equity_end = float((shares * close[:, end_idx]).sum() + gb)
    return {"terminal": equity_end + mmf, "mmf_left": mmf, "mmf_drawn": drawn_total}


def summarize(data: dict[str, np.ndarray], ls_terminals: np.ndarray) -> dict:
    terminals = data["t"]
    return {
        "median": float(np.median(terminals)),
        "mean": float(np.mean(terminals)),
        "p5": float(np.percentile(terminals, 5)),
        "p95": float(np.percentile(terminals, 95)),
        "median_inv": float(np.median(data["inv"])),
        "median_mmf_left": float(np.median(data["mmf"])),
        "win_vs_lump": float(np.mean(terminals > ls_terminals)),
        "adv_median_vs_lump": float(np.median(terminals / ls_terminals - 1.0)),
        "adv_mean_vs_lump": float(np.mean(terminals / ls_terminals - 1.0)),
    }


def eq_nominal(strategy: str, n_months: int, contribution: float, drawn: float) -> float:
    """Nominal equity budget for context reporting."""
    base = contribution * n_months
    if strategy == "lump_sum_30k":
        return base + INITIAL_MM
    if strategy in ("dca_cushion", "oracle_cushion"):
        return base
    if strategy == "dip2x_mm":
        return base + drawn
    raise ValueError(strategy)


def main() -> None:
    from backtesting.engine.data import DATA_DIR

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--horizons", default="10,12,14,16,18,20")
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--mm0", type=float, default=INITIAL_MM)
    p.add_argument("--reuse-cache", action="store_true")
    p.add_argument("--out", default=str(DATA_DIR / "mm_cushion.json"))
    args = p.parse_args()

    md, sources = load_experiment(args.end, force=not args.reuse_cache)
    horizons = [int(h) for h in args.horizons.split(",")]
    all_windows: dict[int, list] = {}
    window_counts: dict[int, int] = {}
    for hy in horizons:
        all_windows[hy * 12] = [ms for _, ms in enumerate_windows(md, hy * 12)]
        window_counts[hy] = len(all_windows[hy * 12])
    print(f"data {md.dates[0]} -> {md.dates[-1]}; windows {window_counts}; reserve {args.mm0:,.0f}")

    comp_cache: dict[str, np.ndarray] = {}
    roll30_cache: dict[str, np.ndarray] = {}
    terminals: dict[tuple[str, str, int], np.ndarray] = {}
    invested: dict[tuple[str, str, int], np.ndarray] = {}
    mmf_left: dict[tuple[str, str, int], np.ndarray] = {}
    trig_stats: dict[tuple[str, str, int], dict] = {}
    for p_name, weights in PORTFOLIOS.items():
        if p_name not in comp_cache:
            comp = md.composite(weights)
            comp_cache[p_name] = comp
            roll30_cache[p_name] = rolling_max_calendar(comp, list(md.dates), CAL_WINDOW)
        comp, roll30 = comp_cache[p_name], roll30_cache[p_name]
        for h, wins in all_windows.items():
            for strategy in STRATEGIES:
                terms, inv, mmfl, trig = [], [], [], {}
                for months in wins:
                    buys, rbd, meta = plan_cushion(
                        strategy, comp, roll30, months, list(md.dates), args.contribution
                    )
                    res = run_cushion_window(
                        md, weights, months, buys, rbd,
                        mmf0=args.mm0 if strategy != "lump_sum_30k" else 0.0,
                    )
                    terms.append(res["terminal"])
                    mmfl.append(res["mmf_left"])
                    inv.append(
                        eq_nominal(strategy, len(months), args.contribution, res["mmf_drawn"])
                    )
                    if meta and meta.get("triggered_months"):
                        trig = meta
                terminals[(p_name, strategy, h)] = np.array(terms)
                invested[(p_name, strategy, h)] = np.array(inv)
                mmf_left[(p_name, strategy, h)] = np.array(mmfl)
                if trig:
                    trig_stats[(p_name, strategy, h)] = trig

    summary_rows: list[dict] = []
    pooled: dict[str, dict[str, list]] = {}
    for p_name in PORTFOLIOS:
        rows = []
        for strategy in STRATEGIES:
            t_all = np.concatenate([terminals[(p_name, strategy, hy * 12)] for hy in horizons])
            i_all = np.concatenate([invested[(p_name, strategy, hy * 12)] for hy in horizons])
            m_all = np.concatenate([mmf_left[(p_name, strategy, hy * 12)] for hy in horizons])
            lt_all = np.concatenate(
                [terminals[(p_name, "lump_sum_30k", hy * 12)] for hy in horizons]
            )
            stats = summarize({"t": t_all, "inv": i_all, "mmf": m_all}, lt_all)
            stats.update({"portfolio": p_name, "strategy": strategy})
            trig_rows = [
                trig_stats[(p_name, strategy, hy * 12)]
                for hy in horizons
                if (p_name, strategy, hy * 12) in trig_stats
            ]
            if trig_rows:
                tm = sum(t["months"] for t in trig_rows)
                tg = sum(t["triggered_months"] for t in trig_rows)
                stats["triggered_months_pct"] = tg / tm if tm else None
            rows.append(stats)
            slot = pooled.setdefault(strategy, {"t": [], "inv": [], "mmf": [], "lt": []})
            slot["t"].append(t_all)
            slot["inv"].append(i_all)
            slot["mmf"].append(m_all)
            slot["lt"].append(lt_all)

        print(
            f"\n=== {p_name} ({sum(window_counts.values())} windows, "
            f"reserve {args.mm0:,.0f} + {args.contribution:.0f}/mo) ==="
        )
        print(
            f"{'strategy':<18}{'total med':>11}{'mean':>11}{'p5':>10}{'p95':>11}"
            f"{'eq inv med':>11}{'mmf left':>10}{'win>LS':>8}{'adv med':>9}{'adv mean':>10}"
        )
        print("-" * 112)
        for r in rows:
            t = r.get("triggered_months_pct")
            nm = r["strategy"] + (f" ({t:.0%}trig)" if isinstance(t, float) else "")
            print(
                f"{nm:<18}{r['median']:>11,.0f}{r['mean']:>11,.0f}{r['p5']:>10,.0f}"
                f"{r['p95']:>11,.0f}{r['median_inv']:>11,.0f}{r['median_mmf_left']:>10,.0f}"
                f"{r['win_vs_lump']:>7.0%} {r['adv_median_vs_lump']:>+8.1%}"
                f"{r['adv_mean_vs_lump']:>+9.1%}"
            )
        summary_rows.extend(rows)

    print("\n=== pooled across portfolios (baseline lump_sum_30k) ===")
    print(f"{'strategy':<18}{'median':>11}{'eq inv med':>11}{'mmf left':>10}{'win>LS':>8}{'adv med':>9}{'adv mean':>10}")
    print("-" * 88)
    for strategy in STRATEGIES:
        slot = pooled[strategy]
        stats = summarize(
            {
                "t": np.concatenate(slot["t"]),
                "inv": np.concatenate(slot["inv"]),
                "mmf": np.concatenate(slot["mmf"]),
            },
            np.concatenate(slot["lt"]),
        )
        stats.update({"portfolio": "pooled", "strategy": strategy})
        summary_rows.append(stats)
        print(
            f"{strategy:<18}{stats['median']:>11,.0f}{stats['median_inv']:>11,.0f}"
            f"{stats['median_mmf_left']:>10,.0f}{stats['win_vs_lump']:>7.0%} "
            f"{stats['adv_median_vs_lump']:>+8.1%}{stats['adv_mean_vs_lump']:>+9.1%}"
        )

    # sanity: 2008-07 10y stocks_100
    print("\n=== sanity: 2008-07 start, 10y, stocks_100 — terminal (mmf left, drawn) ===")
    w0 = next(i for i, m in enumerate(md.months) if m.key == "2008-07")
    gms = md.months[w0 : w0 + 120]
    comp = comp_cache["stocks_100"]
    roll30 = roll30_cache["stocks_100"]
    for strategy in STRATEGIES:
        buys, rbd, meta = plan_cushion(strategy, comp, roll30, gms, list(md.dates), args.contribution)
        res = run_cushion_window(
            md, PORTFOLIOS["stocks_100"], gms, buys, rbd,
            mmf0=args.mm0 if strategy != "lump_sum_30k" else 0.0,
        )
        trig = meta.get("triggered_months", "-")
        print(
            f"  {strategy:<16}{res['terminal']:>12,.0f}  "
            f"(mmf left {res['mmf_left']:>9,.0f}, drew {res['mmf_drawn']:>8,.0f})  triggers {trig}"
        )

    payload = {
        "params": {
            "mm0": args.mm0,
            "contribution": args.contribution,
            "horizons_years": horizons,
            "trigger": (
                f"red AND >={TRIGGER_DD:.0%} below rolling {CAL_WINDOW}d high, "
                f"first {HALF_MONTH} days of month; extra 500 withdrawn from the reserve"
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
        "records": [
            {
                "portfolio": p_name,
                "strategy": strategy,
                "horizon_years": h,
                "start": wins[i][0].key,
                "terminal": float(terminals[(p_name, strategy, h)][i]),
                "mmf_left": float(mmf_left[(p_name, strategy, h)][i]),
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
