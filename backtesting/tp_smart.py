#!/usr/bin/env python3
"""Round 2: LS vs DCA vs quarterly take-profit trading vs EMA-boosted DCA.

Strategies (identical contribution schedule unless noted):
* ls1:      all X = 500 x months on day 1
* dca:      500/mo at month mid
* tp4:      500/mo contributions, budget X; up to 4 live trades/year, each
            sized 10% of X; entered on the first trading day of each quarter
            (calendar rule, no signal, no look-ahead); exits at close >=
            entry*1.05 (+5% take-profit) or after 252 trading days (time
            stop). Signal day t -> fill at t+1 close. Proceeds stay as cash
            earning ^IRX and are redeployed on future quarter entries.
* smart_ema:500/mo baseline; in ANY month where the EMA Pullback v1.2 long
            signal fires (EMA50>EMA200 and close crosses above EMA50), that
            month's mid-month buy is 2500 (5x) instead of 500. Note: total
            money invested differs from the other three -- reported too.

Conventions: SPY total-return bars, 10 bps commission + 5 bps slippage per
leg, waiting cash earns ^IRX (y/360), fills at close, signals T+1, windows =
monthly starts and horizons {10,12,14,16,18,20}y. No parameter fitting:
+5%, 10%, 4 trades/yr, 5x boost are the user's stated hypothesis values.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backtesting.dca_vs_lumpsum import Month
from backtesting.engine import indicators as ta
from backtesting.engine.data import DATA_DIR
from backtesting.lever_tax_swing import (
    COMM,
    CONTRIBUTION,
    SLIP,
    accrual_factor,
    simulate,
    enumerate_windows,
    load_experiment,
)

def ema_signal_months(prices: np.ndarray, months: list[Month]) -> set[str]:
    """Months where the EMA Pullback v1.2 long signal fires at least once.

    Signal at day i: EMA50>EMA200 (both today and yesterday) AND close crosses
    above EMA50 at i. Uses backtesting.engine.indicators.ema (Pine-style,
    warmup NaN-safe). Keys are month keys like "2005-03".
    """
    e50 = ta.ema(prices, 50)
    e200 = ta.ema(prices, 200)
    prev = np.concatenate([[np.nan], e50[:-1]])
    cross = (prices > e50) & (np.roll(prices, 1) <= np.roll(e50, 1))
    bull = (e50 > e200) & (prev > np.concatenate([[np.nan], e200[:-1]]))
    fire = bull & cross & ~np.isnan(e50) & ~np.isnan(e200)
    fired: set[str] = set()
    for m in months:
        for d in m.days:
            if d < len(prices) and fire[d]:
                fired.add(m.key)
                break
    return fired


@dataclass
class Result:
    term: float
    max_dd: float
    total_contrib: float
    n_buys: int
    n_sells: int
    n_tp_exits: int
    n_time_exits: int
    days_invested: int

TAKE_PROFIT = 0.05
SLOT = 0.10              # 10% of total budget per trade
MAX_OPEN = 4
TIME_STOP_BARS = 252


TAKE_PROFIT = 0.05
SLOT = 0.10              # 10% of total budget per trade
MAX_OPEN = 4
TIME_STOP_BARS = 252


def run_tp4(prices: np.ndarray, months: list[Month], cumlog: np.ndarray,
            offset: int, X: float) -> Result:
    """Quarterly entries, 10%-of-budget size, +5% TP or ~1y time stop.

    Contribution 500 arrives every month first day; deployed via quarterly
    calendar entries only. Signal/no-lookahead: entries are calendar-fixed,
    exits trigger on close data of day t and fill at day t+1 close.
    """
    W = len(prices)
    clog = cumlog[offset:offset + W]

    def gs(day: int, anchor: int) -> float:
        return accrual_factor(clog, day, anchor) if day > anchor else 1.0

    cash = 0.0
    cash_anchor = 0
    budget_per_trade = SLOT * X
    contribs = {m.first: CONTRIBUTION for m in months}
    open_trades: list[dict] = []
    n_buys = n_sells = n_tp = n_time = 0
    equity = np.empty(W)
    invested_days = 0

    def grow(day: int) -> None:
        nonlocal cash, cash_anchor
        if day > cash_anchor:
            cash *= accrual_factor(clog, day, cash_anchor)
            cash_anchor = day

    def enter(day: int, price: float) -> None:
        nonlocal cash, n_buys
        slots = MAX_OPEN - len(open_trades)
        if slots <= 0:
            return
        take = min(slots, int(cash // budget_per_trade))
        for _ in range(take):
            basis = price * (1.0 + SLIP) * (1.0 + COMM)
            cash -= budget_per_trade
            open_trades.append({"qty": budget_per_trade / basis, "entry": day,
                                "px": price, "basis": basis})
            n_buys += 1

    def close_trade(day: int, price: float, trade: dict, why: str) -> None:
        nonlocal cash, n_sells, n_tp, n_time
        gain = (price * (1.0 - SLIP) * (1.0 - COMM) - trade["basis"]) * trade["qty"]
        proceeds = trade["qty"] * price * (1.0 - SLIP) * (1.0 - COMM)
        cash += proceeds
        n_sells += 1
        if why == "tp":
            n_tp += 1
        else:
            n_time += 1
    entry_days = {m.days[0] for i, m in enumerate(months) if i % 3 == 0}
    signal_exit = {}  # day -> list of trades to exit at that close (decided t, fill t+1)
    for day in range(W):
        price = prices[day]
        if day in contribs:
            grow(day)
            cash += contribs[day]
        # exits queued from yesterday's signal fill today
        for trade in signal_exit.pop(day, []):
            close_trade(day, price, trade, trade.pop("_why"))
            open_trades.remove(trade)
        if day in entry_days and cash >= budget_per_trade:
            enter(day, price)
        # today's close inspects open trades; queue exits for tomorrow
        for trade in list(open_trades):
            if price >= trade["px"] * (1.0 + TAKE_PROFIT):
                trade["_why"] = "tp"
            elif day - trade["entry"] + 1 >= TIME_STOP_BARS:
                trade["_why"] = "time"
            else:
                continue
            signal_exit.setdefault(day + 1, []).append(trade)
        grow(day)
        equity[day] = cash + sum(t["qty"] * price for t in open_trades)
        if open_trades:
            invested_days += 1
    grow(W - 1)
    term = equity[-1]
    dd = 0.0
    peak = -1.0
    for v in equity:
        peak = max(peak, v)
        dd = max(dd, 1.0 - v / peak)
    return Result(term=term, max_dd=float(dd), total_contrib=X, n_buys=n_buys,
                  n_sells=n_sells, n_tp_exits=n_tp, n_time_exits=n_time,
                  days_invested=invested_days)


def run_smart_ema(prices: np.ndarray, months: list[Month], cumlog: np.ndarray,
                  offset: int, fired: set[str]) -> Result:
    """500/mo at month mid, and months where the EMA v1.2 signal fired buy 2500
    (5x) instead of 500 -- also at mid. Total contributions therefore vary."""
    W = len(prices)
    clog = cumlog[offset:offset + W]

    def grow(day: int) -> None:
        nonlocal cash, cash_anchor
        if day > cash_anchor:
            cash *= accrual_factor(clog, day, cash_anchor)
            cash_anchor = day

    def buy(day: int, amount: float) -> None:
        nonlocal shares, cash, n_buys
        grow(day)
        take = min(amount, cash)
        if take <= 0:
            return
        shares += take / (prices[day] * (1.0 + SLIP) * (1.0 + COMM))
        cash -= take
        n_buys += 1

    shares = cash = 0.0
    cash_anchor = 0
    n_buys = 0
    equity = np.empty(W)
    invested_days = 0
    total_contrib = 0.0
    deploys = {m.mid: (2500.0 if m.key in fired else 500.0) for m in months}
    for day in range(W):
        if day in deploys:
            grow(day)
            take = deploys[day]
            cash += take
            total_contrib += take
            buy(day, take)
        grow(day)
        price = prices[day]
        equity[day] = shares * price + cash
        if shares > 0:
            invested_days += 1
    dd = 0.0
    peak = -1.0
    for v in equity:
        peak = max(peak, v)
        dd = max(dd, 1.0 - v / peak)
    return Result(term=float(equity[-1]), max_dd=float(dd), total_contrib=total_contrib,
                  n_buys=n_buys, n_sells=0, n_tp_exits=0, n_time_exits=0,
                  days_invested=invested_days)

def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--reuse-cache", action="store_true")
    p.add_argument("--horizons", default=",".join(str(h) for h in (10, 12, 14, 16, 18, 20)))
    p.add_argument("--out", default=str(DATA_DIR / "round2_tp_smart.json"))
    args = p.parse_args()

    dates, paths, months, cumlog, src = load_experiment(args.end, not args.reuse_cache)
    spy = paths["1x"]
    fired_full = ema_signal_months(spy, months)
    horizons = [int(x) for x in args.horizons.split(",")]
    print(f"data {dates[0]}..{dates[-1]} ({len(dates)} days), {src}; "
          f"EMA signal months (full series): {len(fired_full)}/{len(months)}")

    labels = ("ls", "dca", "tp4", "smart_ema")
    start_years: list[int] = []
    out: dict[str, dict] = {
        "meta": {"start": dates[0], "end": dates[-1], "src": src,
                 "tp": TAKE_PROFIT, "slot": SLOT, "max_open": MAX_OPEN,
                 "time_stop": TIME_STOP_BARS,
                 "ema_signal_months_full": len(fired_full)},
    }
    per_h: dict[str, dict] = {k: {} for k in labels}
    pooled: dict[str, list] = {k: [] for k in labels}
    contrib_total: dict[str, list] = {k: [] for k in labels}
    trades_stats: dict[str, list] = {k: [] for k in labels}
    dds: dict[str, list] = {k: [] for k in labels}

    for h in horizons:
        ws = enumerate_windows(months, dates, h * 12)
        for mw in ws:
            start_years.append(int(mw[0].key[:4]))
            off = mw[0].first
            W = mw[-1].last - off + 1
            mwr = [Month(key=m.key, first=m.first - off, mid=m.mid - off,
                         last=m.last - off, days=tuple(d - off for d in m.days))
                   for m in mw]
            X = CONTRIBUTION * len(mw)
            ps = spy[off:off + W]
            fired_win = ema_signal_months(ps, mwr)
            res = {
                "ls": simulate("ls", ps, mwr, cumlog, off, X, 0.0),
                "dca": simulate("dca", ps, mwr, cumlog, off, X, 0.0),
                "tp4": run_tp4(ps, mwr, cumlog, off, X),
                "smart_ema": run_smart_ema(ps, mwr, cumlog, off, fired_win),
            }
            for k, r in res.items():
                pooled[k].append(r.term)
                contrib_total[k].append(r.total_contrib if k == "smart_ema" else X)
                dds[k].append(r.max_dd)
                if k == "tp4":
                    trades_stats[k].append((r.n_buys, r.n_sells, r.n_tp_exits, r.n_time_exits))
        for k in labels:
            a = np.array(pooled[k])
            per_h[k][h] = {"median_terrn": float(np.median(a)),
                           "avg_contrib": float(np.mean(contrib_total[k]))}
    for k in labels:
        a = np.array(pooled[k])
        eff = np.array(contrib_total[k])
        yrs = np.array(start_years)
        cohorts = {}
        for decade, (lo, hi) in (("2004-09", (2004, 2009)), ("2010-14", (2010, 2014)),
                                 ("2015-20", (2015, 2020))):
            mask = (yrs >= lo) & (yrs <= hi)
            if mask.any():
                cohorts[decade] = float(np.median(a[mask]))
        out[k] = {
            "n": int(len(a)),
            "median": float(np.median(a)), "mean": float(np.mean(a)),
            "p5": float(np.percentile(a, 5)), "p95": float(np.percentile(a, 95)),
            "med_maxdd": float(np.median(dds[k])),
            "avg_contrib": float(np.mean(eff)),
            "term_per_1000_contrib": float(np.median(a / eff * 1000)),
            "cohorts_start_year": cohorts,
            "trades": trades_stats.get(k, [(np.nan,) * 4]),
        }
    json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(out, indent=1)[:3800])

if __name__ == "__main__":
    main()
