#!/usr/bin/env python3
"""Leverage + dip trading + taxed swing vs DCA and lump sum.

Question (report research/lever_tax_swing_report.md): if the index trends up
long term, is the right response (a) daily-reset 2x/3x leverage, (b) trading
20%-of-capital tranches into down months at the oracle monthly low, or (c)
repeatedly flipping between cash and index while paying Italy's 26% capital
gains tax -- compared against plain monthly DCA and full lump sum?

All strategies invest the same total money X = 500 x months-in-window.
Oracle strategies are perfect-hindsight upper bounds (flagged, not tradable).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backtesting.dca_vs_lumpsum import (
    COMM,
    HORIZON_YEARS,
    SLIP,
    YIELD_SYMBOL,
    Month,
    accrual_factor,
    build_market,
)
from backtesting.engine.data import DATA_DIR, fetch_yahoo, load_bars

FETCH_START = "2004-11-01"
ASSET = "SPY"
LEV_ER = 0.0084            # annual TER of SSO/UPRO-style daily-reset ETFs
LEV_BORROW_SPREAD = 0.0050  # financing spread over T-bill on borrowed leg
SMA200 = 200
TAX = 0.26
CONTRIBUTION = 500.0

def lever_path(spy: np.ndarray, yff: dict[str, float], dates: list[str], lev: float) -> np.ndarray:
    """Daily-reset leveraged total-return index built from SPY TR + ^IRX."""
    n = len(spy)
    r = spy[1:] / spy[:-1] - 1.0
    rf = np.array([yff[dates[i]] for i in range(1, n)])
    drag = (LEV_ER + (lev - 1) * LEV_BORROW_SPREAD) / 252.0
    rr = lev * r - (lev - 1) * rf / 252.0 - drag
    rel = np.concatenate([[1.0], np.cumprod(1.0 + rr)])
    return rel * spy[0]

def calibrate_leverage(paths: dict[str, np.ndarray]):
    """Check the simulated leveraged series against quoted SSO/UPRO proxies."""
    got = {}
    for sym, name in (("SSO", "2x"), ("UPRO", "3x")):
        try:
            b, _ = load_bars(sym, "2010-01-01", "2026-09-30", provider="yahoo")
            if len(b) < 3000:
                continue
            real = np.array([x.c for x in b])
            sim = paths.get(name)
            if sim is None:
                continue
            n = min(2520, len(real), len(sim))
            sre = real[-n:] / real[-n] * sim[-1] / sim[-n]
            real_cagr = (real[-1] / real[-n]) ** (252.0 / n) - 1
            sim_cagr = (sim[-1] / sim[-n]) ** (252.0 / n) - 1
            real_vol = np.diff(np.log(real[-n:])).std() * (252.0**0.5)
            sim_vol = np.diff(np.log(sre)).std() * (252.0**0.5)
            got[name] = dict(symbol=sym, n_days=n, real_cagr=float(real_cagr),
                             sim_cagr=float(sim_cagr), real_vol=float(real_vol),
                             sim_vol=float(sim_vol))
        except Exception as e:  # quant-check only, never fatal
            got[name] = dict(symbol=sym, error=str(e))
    return got

def load_experiment(end: str, force: bool):
    bars, src = load_bars(ASSET, FETCH_START, end, provider="yahoo", force=force)
    dates = [b.t for b in bars]
    spy = np.array([b.c for b in bars])
    from backtesting.dca_vs_lumpsum import _build_cumlog
    try:
        ybars = fetch_yahoo(YIELD_SYMBOL, "2004-01-01", end)
    except Exception:
        ybars = []
    yraw = {b.t: b.c for b in ybars}
    scale = 100.0 if yraw and np.median(list(yraw.values())) >= 0.2 else 1.0
    yraw = {k: v / scale for k, v in yraw.items() if 0.0 < v / scale < 0.15}
    yff: dict[str, float] = {}
    last = 0.0
    for d in dates:
        if d in yraw:
            last = yraw[d]
        yff[d] = last
    months: list[Month] = []
    bucket: dict[str, list[int]] = {}
    for i, d in enumerate(dates):
        bucket.setdefault(d[:7], []).append(i)
    for key in sorted(bucket):
        days = bucket[key]
        mid = next((i for i in days if int(dates[i][8:10]) >= 15), days[-1])
        months.append(Month(key=key, first=days[0], mid=mid, last=days[-1], days=tuple(days)))
    cumlog = _build_cumlog(dates, yff)
    paths = {"1x": spy}
    for lev in (2, 3):
        paths[f"{lev}x"] = lever_path(spy, yff, dates, lev)
    months[-1].__dict__["_last_date"] = dates[months[-1].last]
    return dates, paths, months, cumlog, src

def complete_last(months: list[Month], dates: list[str]) -> int:
    idx = [i for i, m in enumerate(months) if int(dates[m.last][8:10]) >= 20]
    return max(idx)

def enumerate_windows(months: list[Month], dates: list[str], horizon_months: int):
    last_complete = complete_last(months, dates)
    return [
        months[i : i + horizon_months]
        for i in range(last_complete + 1)
        if i + horizon_months - 1 <= last_complete
    ]

@dataclass
class SimResult:
    term: float
    max_dd: float
    n_buys: int
    n_sells: int
    tax_paid: float
    n_loss_sales: int
    days_invested: int


def simulate(kind: str, prices: np.ndarray, months: list[Month],
             cumlog_full: np.ndarray, offset_day: int, total_money: float,
             tax_rate: float, tax_anchored_to_window: bool = False
             ) -> SimResult:
    """Window simulation. Kind is one of:
    'ls'        all-in day 1
    'mapping_dca'  monthly mid-month DCA (contrib schedule)
    'swing'     SMA200 trend flip with 20%-of-idle-cash bonus tranches on the
                first negative-month day while above SMA200 (T+1 fills)
    'oracle'    hindsight: each calendar month that ends negative, buy
                max(500, 20% of idle) at that month's lowest close
    tax_rate applies to realized FIFO gains at sale under 'swing' only.
    Contributions: 500 on the first trading day of every window month.
    """
    W = len(prices)
    cumlog = cumlog_full[offset_day:offset_day + W]
    # rolling SMA via cumulative sum (index t = sum of last 200 closes)
    cs = np.concatenate([[0.0], np.cumsum(prices)])
    def sma_at(t: int) -> float:
        return (cs[t + 1] - cs[t + 1 - SMA200]) / SMA200 if t + 1 >= SMA200 else None

    # ---- schedule executor events (day -> action); decisions use day t, fill t+1
    pending: dict[int, list[str]] = {}
    if kind == "ls":
        pending[0] = ["buy_all"]
    elif kind == "dca":
        for m in months:
            pending.setdefault(m.mid, []).append("buy_500")
    elif kind == "oracle":
        for m in months:
            if prices[m.last] < prices[m.first]:
                dip = min(m.days, key=lambda d: prices[d])
                pending.setdefault(dip, []).append("buy_tranche")
    elif kind == "swing":
        above = np.zeros(W, dtype=bool)
        for t in range(W):
            s = sma_at(t)
            if s is not None:
                above[t] = prices[t] > s
        for t in range(1, W):
            if above[t] and not above[t - 1]:
                pending.setdefault(t + 1, []).append("buy_all")
            if not above[t] and above[t - 1]:
                pending.setdefault(t + 1, []).append("sell_all")
        # one 20%-of-idle bonus tranche: first day of a month closing below the
        # previous month's last close (MTD negative), executable next day
        for k in range(1, len(months)):
            m = months[k]
            prev_close = prices[m.first - 1]
            for d in m.days:
                if prices[d] < prev_close:
                    pending.setdefault(d + 1, []).append("buy_tranche")
                    break
    # ---- executor
    shares = 0.0
    cash = 0.0
    cash_anchor = 0
    lots: list[tuple[float, float]] = []
    carry_minus = 0.0
    carry_anchor: int | None = None
    tax_paid = 0.0
    n_buys = n_sells = n_loss_sales = 0
    equity = np.empty(W)
    month_of_pos = [0] * W
    for k, m in enumerate(months):
        for d in m.days:
            if d < W:
                month_of_pos[d] = k

    def grow_cash_to(day: int) -> None:
        nonlocal cash, cash_anchor
        if day > cash_anchor:
            cash *= accrual_factor(cumlog, day, cash_anchor)
            cash_anchor = day

    def do_buy(day: int, mode: str) -> None:
        nonlocal shares, cash, n_buys
        grow_cash_to(day)
        price = prices[day]
        if mode == "buy_all":
            amount = cash
        elif mode == "buy_tranche":
            amount = max(CONTRIBUTION, 0.20 * cash)
        else:  # buy_500 (contribution tranche at mid month)
            amount = CONTRIBUTION
        amount = min(amount, cash)
        if amount <= 0:
            return
        qty = amount / (price * (1.0 + SLIP) * (1.0 + COMM))
        lots.append((qty, amount / qty))
        shares += qty
        cash -= amount
        n_buys += 1

    def do_sell(day: int) -> None:
        nonlocal shares, cash, lots, tax_paid, n_sells, n_loss_sales
        nonlocal carry_minus, carry_anchor
        if shares <= 0:
            return
        grow_cash_to(day)
        price = prices[day]
        proceeds = shares * price * (1.0 - SLIP) * (1.0 - COMM)
        basis = sum(q * b for q, b in lots)
        gain = proceeds - basis
        lots = []
        shares = 0.0
        n_sells += 1
        if tax_rate <= 0.0:
            cash += proceeds
            if gain < 0:
                n_loss_sales += 1
            return
        tax_year = int(months[month_of_pos[day]].key[:4])
        if gain > 0:
            offset = 0.0
            if carry_minus > 0 and carry_anchor is not None and tax_year - carry_anchor <= 4:
                offset = min(carry_minus, gain)
            net = gain - offset
            if net > 0:
                tax_paid += tax_rate * net
            carry_minus = max(0.0, carry_minus - offset)
        else:
            carry_minus += -gain
            if carry_anchor is None:
                carry_anchor = tax_year
        tax = tax_rate * net if (gain > 0 and net > 0) else 0.0
        cash += proceeds - tax
        if gain < 0:
            n_loss_sales += 1
    # funding: ls gets the whole X on day 0 (pending buy_all spends it);
    # dca contributions at mid-month; oracle/swing get 500/mo at month firsts
    contribs: dict[int, float] = {}
    if kind == "ls":
        contribs[0] = total_money
    elif kind == "dca":
        for m in months:
            contribs[m.mid] = contribs.get(m.mid, 0.0) + CONTRIBUTION
    else:
        for m in months:
            contribs[m.first] = contribs.get(m.first, 0.0) + CONTRIBUTION

    invested_days = 0
    for day in range(W):
        # contributions arrive first thing (idle cash until deployed)
        if day in contribs:
            grow_cash_to(day)
            cash += contribs[day]
        for action in pending.get(day, []):
            if action in ("buy_all", "buy_tranche", "buy_500"):
                do_buy(day, action)
            elif action == "sell_all":
                do_sell(day)
        equity[day] = shares * prices[day] + cash
        if shares > 0:
            invested_days += 1

    dd = 0.0
    peak = -1.0
    for v in equity:
        peak = max(peak, v)
        dd = max(dd, 1.0 - v / peak)
    return SimResult(term=float(equity[-1]), max_dd=float(dd), n_buys=n_buys,
                     n_sells=n_sells, tax_paid=tax_paid, n_loss_sales=n_loss_sales,
                     days_invested=invested_days)

STRATEGIES = (
    # (label, kind, asset_path_key, tax_rate)
    ("ls_1x", "ls", "1x", 0.0),
    ("ls_2x", "ls", "2x", 0.0),
    ("ls_3x", "ls", "3x", 0.0),
    ("dca_1x", "dca", "1x", 0.0),
    ("dca_2x", "dca", "2x", 0.0),
    ("dca_3x", "dca", "3x", 0.0),
    ("oracle_dip_20", "oracle", "1x", 0.0),      # hindsight, NOT tradable
    ("swing_sma200", "swing", "1x", 0.0),        # tradable, sheltered
    ("swing_sma200_tax", "swing", "1x", TAX),    # same rule, Italian taxable
)

def summarize(terms: np.ndarray, base_ls: np.ndarray, base_dca: np.ndarray) -> dict:
    return {
        "n": int(len(terms)),
        "median": float(np.median(terms)),
        "mean": float(np.mean(terms)),
        "p5": float(np.percentile(terms, 5)),
        "p95": float(np.percentile(terms, 95)),
        "maxdd_median": None,  # filled by caller
        "win_vs_ls": float(np.mean(terms > base_ls)),
        "adv_med_vs_ls": float(np.median(terms / base_ls - 1.0)),
        "adv_med_vs_dca": float(np.median(terms / base_dca - 1.0)),
        "cagr_median": None,
    }

def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--reuse-cache", action="store_true")
    p.add_argument("--horizons", default=",".join(str(h) for h in HORIZON_YEARS))
    p.add_argument("--out", default=str(DATA_DIR / "lever_tax_swing.json"))
    args = p.parse_args()

    dates, paths, months, cumlog, src = load_experiment(args.end, not args.reuse_cache)
    calib = calibrate_leverage(paths)
    horizons = [int(x) for x in args.horizons.split(",")]
    print(f"data: {dates[0]}..{dates[-1]} ({len(dates)} days); {src}")
    sums: dict[str, dict] = {}
    medians_by_h: dict[str, dict[int, float]] = {}
    dds_by_h: dict[str, dict[int, float]] = {}
    taxes_paid_avg: dict[str, float] = {}
    trades: dict[str, tuple] = {}
    robustness: dict[str, dict[str, float]] = {}

    for h in horizons:
        ws = enumerate_windows(months, dates, h * 12)
        print(f"horizon {h}y: {len(ws)} windows")
        for label, kind, pkey, tax_rate in STRATEGIES:
            terms, dds, taxes, buys, sells, yrs = [], [], [], [], [], []
            for mw in ws:
                off = mw[0].first
                Ww = mw[-1].last - off + 1
                mw_rel = [
                    Month(key=m.key, first=m.first - off, mid=m.mid - off,
                          last=m.last - off, days=tuple(d - off for d in m.days))
                    for m in mw
                ]
                res = simulate(kind, paths[pkey][off:off + Ww], mw_rel, cumlog,
                               off, CONTRIBUTION * len(mw), tax_rate)
                terms.append(res.term)
                dds.append(res.max_dd)
                taxes.append(res.tax_paid)
                buys.append(res.n_buys); sells.append(res.n_sells)
                yrs.append(int(mw[0].key[:4]))
            # robustness split: cohort by start year
            a = np.array(terms)
            sums.setdefault(label, {})[f"terms_{h}"] = a.tolist()
            sums[label][f"dds_{h}"] = list(dds)
            medians_by_h.setdefault(label, {})[h] = float(np.median(a))
            dds_by_h.setdefault(label, {})[h] = float(np.median(dds))
            taxes_paid_avg.setdefault(label, []).extend(taxes)
            trades.setdefault(label, []).append((np.mean(buys), np.mean(sells)))
            for decade, (lo, hi) in (("2005-09", (2004, 2009)), ("2010-14", (2010, 2014)),
                                     ("2015-20", (2015, 2020))):
                mask = np.array([lo <= y <= hi for y in yrs])
                if mask.any():
                    robustness.setdefault(label, {})[f"{decade}_{h}y"] = float(np.median(a[mask]))
    print("run complete")
    # ---- pooled stats over all horizons + baselines references
    pooled: dict[str, dict] = {}
    base_terms = {}
    for label, *_ in STRATEGIES:
        all_terms = np.concatenate([
            np.array(sums[label][f"terms_{h}"]) for h in horizons
        ])
        pooled[label] = {"n": int(len(all_terms)), "median": float(np.median(all_terms)),
                         "mean": float(np.mean(all_terms)),
                         "p5": float(np.percentile(all_terms, 5)),
                         "p95": float(np.percentile(all_terms, 95))}
    for base in ("ls_1x", "dca_1x"):
        bt = np.concatenate([np.array(sums[base][f"terms_{h}"]) for h in horizons])
        base_terms[base] = bt
    for label in pooled:
        at = np.concatenate([np.array(sums[label][f"terms_{h}"]) for h in horizons])
        pooled[label]["adv_med_vs_ls"] = float(np.median(at / base_terms["ls_1x"] - 1.0))
        pooled[label]["adv_med_vs_dca"] = float(np.median(at / base_terms["dca_1x"] - 1.0))
        pooled[label]["win_vs_ls"] = float(np.mean(at > base_terms["ls_1x"]))
    # worst window per strategy: weakest start with a 20y horizon
    worst: dict[str, float] = {}
    for label in pooled:
        t20 = np.array(sums[label].get("terms_20", []))
        if len(t20):
            worst[label] = float(np.min(t20))
    # CAGR medians: (median terminal / X)^(1/h) - 1
    cagrs: dict[str, dict[int, float]] = {}
    for h in horizons:
        for label, *_ in STRATEGIES:
            t = np.array(sums[label][f"terms_{h}"])
            X = 500.0 * h * 12
            cagrs.setdefault(label, {})[h] = float(np.median(t) ** (1.0 / h) / X ** (1.0 / h) - 1.0)
    out = {
        "data": {"start": dates[0], "end": dates[-1], "days": len(dates), "src": src},
        "lev_calibration": calib,
        "pooled": pooled, "medians_by_h": medians_by_h, "dds_by_h": dds_by_h,
        "robustness": robustness, "worst_20y": worst,
        "avg_tax_per_window": {k: float(np.mean(v)) for k, v in taxes_paid_avg.items()},
        "avg_trades": {k: (float(np.mean([x[0] for x in v])), float(np.mean([x[1] for x in v]))) for k, v in trades.items()},
        "cagr_median_by_h": {k: {str(h): v for h, v in vs.items()} for k, vs in cagrs.items()},
    }
    json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(out, indent=1)[:4000])

if __name__ == "__main__":
    main()
