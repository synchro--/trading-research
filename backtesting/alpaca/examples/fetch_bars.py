#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from backtesting.alpaca.client_stub import AlpacaProvider


def main():
    p = argparse.ArgumentParser(description="Fetch bars via Alpaca and write CSV")
    p.add_argument("--symbol", required=True)
    p.add_argument("--timeframe", default="1Day", help="e.g., 1Min, 5Min, 15Min, 1Hour, 1Day")
    p.add_argument("--start", help="ISO8601 date/time, e.g., 2024-01-01 or 2024-01-01T09:30:00Z")
    p.add_argument("--end", help="ISO8601 date/time")
    p.add_argument("--limit", type=int)
    p.add_argument("--out", required=True, help="Output CSV path")
    args = p.parse_args()

    provider = AlpacaProvider()
    bars = provider.fetch_bars(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        limit=args.limit,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider.write_csv(bars, str(out_path))
    print(f"Wrote {len(bars)} bars -> {out_path}")


if __name__ == "__main__":
    main()
