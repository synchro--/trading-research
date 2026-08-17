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

# The original book: correlated US tech. Alpaca IEX history, mid-2020 onward.
TECH_BOOK = ["KLAC", "SMH", "NET", "GOOGL", "SPY", "QQQ", "URTH"]

# Deliberately uncorrelated, one name per sector, on Yahoo total-return history so
# the sample reaches back through 2000-02, 2008 and 2020 rather than one bull run.
DIVERSE_BOOK = ["JPM", "LMT", "AMGN", "PFE", "MCD", "BRK-B", "EEM", "BTC-USD"]

BOOKS = {"tech": TECH_BOOK, "diverse": DIVERSE_BOOK}

# Slowest indicator in the registry is TSMOM's 252-bar lookback. Every strategy and
# the benchmark start at the same bar so no one gets a head start.
WARMUP_BARS = 252
START, END = "2021-06-01", "2026-08-13"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--book", default="tech", choices=sorted(BOOKS), help="named symbol set")
    p.add_argument("--symbols", default="", help="override --book with a custom list")
    p.add_argument("--start", default="")
    p.add_argument("--end", default=END)
    p.add_argument("--cash", type=float, default=20_000.0)
    p.add_argument("--provider", default="auto", choices=["auto", "yahoo", "alpaca"])
    p.add_argument("--warmup", type=int, default=WARMUP_BARS)
    p.add_argument("--force-fetch", action="store_true")
    p.add_argument("--json", default="")
    args = p.parse_args()

    raw = args.symbols.split(",") if args.symbols else BOOKS[args.book]
    symbols = [_resolve(s) for s in raw if s.strip()]
    start = args.start or ("2001-01-01" if args.book == "diverse" and not args.symbols else START)

    data = {}
    for s in symbols:
        try:
            data[s] = load_bars(s, start, args.end, provider=args.provider,
                                warmup_calendar_days=600, force=args.force_fetch)
        except RuntimeError as e:
            # e.g. asking for BTC in 2008. Skip rather than abort the whole book.
            print(f"  [skip] {s}: {e}")
    if not data:
        raise SystemExit("no symbols have data in this window")
    symbols = list(data)

    bench = {}
    for s, (bars, _) in data.items():
        bench[s] = buy_hold(bars, start, args.cash, warmup_bars=args.warmup)

    rows: list[dict] = []
    for name in REGISTRY:
        for s, (bars, source) in data.items():
            res = run(bars, symbol=s, start=start, initial_cash=args.cash,
                      strategy=name, source=source, warmup_bars=args.warmup)
            m = summarize(res)
            m["strategy"] = name
            m["bh_sharpe"] = bench[s]["sharpe"] or 0.0
            m["bh_cagr"] = bench[s]["cagr"]
            m["bh_max_dd"] = bench[s]["max_dd"]
            m["sharpe_vs_bh"] = (m["sharpe"] or 0.0) - m["bh_sharpe"]
            rows.append(m)

    spans = {s: (b[0].t, b[-1].t) for s, (b, _) in data.items()}
    print(f"\nbook={args.book}  start={start}  end={args.end}  warmup={args.warmup} bars")
    for s in symbols:
        print(f"  {s:<9} {spans[s][0]} -> {spans[s][1]}  ({len(data[s][0])} bars, {data[s][1]})")
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
                   "start": start, "end": args.end, "book": args.book,
                   "symbols": symbols, "warmup_bars": args.warmup}
        with open(args.json, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
