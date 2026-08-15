#!/usr/bin/env python3
"""CLI: python -m backtesting.cli --symbol SMH --start 2018-01-01 --end 2026-08-13"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from backtesting.engine.data import DATA_DIR, load_bars
from backtesting.engine.loop import run
from backtesting.engine.metrics import format_summary, summarize

# User names → Alpaca/Yahoo symbols. SPX is the SPY ETF (Alpaca has no cash index).
# MSCI World is URTH (iShares MSCI World).
SYMBOL_ALIASES = {
    "KLA": "KLAC",
    "KLAC": "KLAC",
    "SMH": "SMH",
    "NET": "NET",
    "CLOUDFLARE": "NET",
    "GOOG": "GOOGL",
    "GOOGL": "GOOGL",
    "GOOGLE": "GOOGL",
    "SPX": "SPY",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "URTH": "URTH",
    "MSCI": "URTH",
    "MSCIWORLD": "URTH",
}


def _resolve(raw: str) -> str:
    return SYMBOL_ALIASES.get(raw.strip().upper().replace(" ", ""), raw.strip().upper())


def _write_outputs(result, out_dir: Path, metrics: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "trades.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry_time", "entry_px", "exit_time", "exit_px", "qty", "R", "pnl", "reason", "hold_bars"])
        for t in result.trades:
            w.writerow([t.entry_time, t.entry_px, t.exit_time, t.exit_px, t.qty, t.r_multiple, t.pnl, t.reason, t.hold_bars])
    with (out_dir / "equity.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "equity", "drawdown"])
        for p in result.equity:
            w.writerow([p.t, p.equity, p.drawdown])
    (out_dir / "summary.json").write_text(json.dumps(metrics, indent=2, default=str))


def main() -> None:
    p = argparse.ArgumentParser(description="EMA Pullback Swing v1 backtest (DESIGN.md)")
    p.add_argument("--symbol", help="Single symbol")
    p.add_argument("--symbols", help="Comma-separated symbols")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default="2026-08-13")
    p.add_argument("--cash", type=float, default=20_000.0)
    p.add_argument("--commission-bps", type=float, default=10.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--strategy", default="ema_pullback",
                   help="ema_pullback | ema50_reclaim | rsi_trend_dip | donchian_55_20 | all")
    p.add_argument("--force-fetch", action="store_true")
    p.add_argument("--out", default="", help="Output dir (default backtesting/data/runs/SYMBOL)")
    args = p.parse_args()

    raw = []
    if args.symbol:
        raw.append(args.symbol)
    if args.symbols:
        raw.extend(s for s in args.symbols.split(",") if s.strip())
    if not raw:
        p.error("pass --symbol or --symbols")

    from backtesting.strategies import REGISTRY

    names = list(REGISTRY) if args.strategy.strip().lower() == "all" else [args.strategy]
    summaries = []
    for strat_name in names:
        for name in raw:
            symbol = _resolve(name)
            bars, source = load_bars(symbol, args.start, args.end, force=args.force_fetch)
            result = run(
                bars,
                symbol=symbol,
                start=args.start,
                initial_cash=args.cash,
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                strategy=strat_name,
                source=source,
            )
            metrics = summarize(result)
            metrics["alias"] = name
            metrics["strategy"] = strat_name
            print(f"[{strat_name}]", format_summary(metrics), f"  src={source}  bars={len(bars)}")
            out = DATA_DIR / "runs" / strat_name / symbol
            if args.out and len(raw) == 1 and len(names) == 1:
                out = Path(args.out)
            _write_outputs(result, out, metrics)
            summaries.append(metrics)

    if len(summaries) > 1:
        print("\n--- batch ---")
        for m in summaries:
            print(f"[{m['strategy']}]", format_summary(m))


if __name__ == "__main__":
    main()
