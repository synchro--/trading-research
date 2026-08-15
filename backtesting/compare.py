#!/usr/bin/env python3
"""Run every registered strategy over the book and rank them against buy-and-hold.

Usage: python -m backtesting.compare [--json out.json]

Sharpe is the ranking metric because it is scale-invariant: a strategy that risks
1.5% per trade and one that goes all-in score the same if the underlying signal is
equally good. CAGR is reported alongside because it is *not* scale-invariant and
answers a different question (how much capital the rules actually put to work).
"""
from __future__ import annotations

import argparse
import json
import statistics as st

from backtesting.cli import SYMBOL_ALIASES, _resolve
from backtesting.engine.data import load_bars
from backtesting.engine.loop import run
from backtesting.engine.metrics import buy_hold, summarize
from backtesting.strategies import REGISTRY

BOOK = ["KLAC", "SMH", "NET", "GOOGL", "SPY", "QQQ", "URTH"]

# Alpaca's IEX history starts 2020-07-27 for most of the book. Starting the live
# window at the first bar hands buy-and-hold a free 10 months, because anything keyed
# off a 200-day average is still NaN and stuck in cash. 2021-06-01 is the first date
# where every strategy's slowest indicator is warm, so it is the only fair comparison.
START, END = "2021-06-01", "2026-08-13"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=",".join(BOOK))
    p.add_argument("--start", default=START)
    p.add_argument("--end", default=END)
    p.add_argument("--cash", type=float, default=20_000.0)
    p.add_argument("--json", default="")
    args = p.parse_args()

    symbols = [_resolve(s) for s in args.symbols.split(",") if s.strip()]
    data = {s: load_bars(s, args.start, args.end) for s in symbols}

    bench = {}
    for s, (bars, _) in data.items():
        bench[s] = buy_hold(bars, args.start, args.cash)

    rows: list[dict] = []
    for name in REGISTRY:
        for s, (bars, source) in data.items():
            res = run(bars, symbol=s, start=args.start, initial_cash=args.cash,
                      strategy=name, source=source)
            m = summarize(res)
            m["strategy"] = name
            m["bh_sharpe"] = bench[s]["sharpe"] or 0.0
            m["bh_cagr"] = bench[s]["cagr"]
            m["bh_max_dd"] = bench[s]["max_dd"]
            m["sharpe_vs_bh"] = (m["sharpe"] or 0.0) - m["bh_sharpe"]
            rows.append(m)

    print(f"\n{'strategy':<18}{'medSharpe':>10}{'medCAGR':>9}{'medDD':>8}"
          f"{'beatBH':>8}{'medΔSh':>8}{'trades':>8}{'time%':>7}")
    print("-" * 74)

    bh_sh = [b["sharpe"] or 0.0 for b in bench.values()]
    bh_cg = [b["cagr"] for b in bench.values()]
    bh_dd = [b["max_dd"] for b in bench.values()]
    print(f"{'BUY & HOLD':<18}{st.median(bh_sh):>10.2f}{st.median(bh_cg):>8.1%}"
          f"{st.median(bh_dd):>8.1%}{'—':>8}{'—':>8}{'—':>8}{'100%':>7}")

    table = []
    for name in REGISTRY:
        r = [x for x in rows if x["strategy"] == name]
        sh = [x["sharpe"] or 0.0 for x in r]
        entry = {
            "strategy": name,
            "median_sharpe": st.median(sh),
            "median_cagr": st.median([x["cagr"] for x in r]),
            "median_dd": st.median([x["max_dd"] for x in r]),
            "beat_bh": sum(1 for x in r if x["sharpe_vs_bh"] > 0),
            "n_symbols": len(r),
            "median_d_sharpe": st.median([x["sharpe_vs_bh"] for x in r]),
            "total_trades": sum(x["n"] for x in r),
            "median_time": st.median([x["time_in_market"] for x in r]),
        }
        table.append(entry)
    for e in sorted(table, key=lambda x: -x["median_sharpe"]):
        print(f"{e['strategy']:<18}{e['median_sharpe']:>10.2f}{e['median_cagr']:>8.1%}"
              f"{e['median_dd']:>8.1%}{e['beat_bh']}/{e['n_symbols']:<6}"
              f"{e['median_d_sharpe']:>+8.2f}{e['total_trades']:>8}{e['median_time']:>6.0%}")

    if args.json:
        payload = {"benchmark": bench, "rows": rows, "table": table,
                   "start": args.start, "end": args.end}
        with open(args.json, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
