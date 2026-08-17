#!/usr/bin/env python3
"""Cross-ETF experiment for lump-sum entry signals.

This is not a trading strategy and has no exit rule. Each signal is evaluated as
a prospective long-term allocation made at the next week's open. Hindsight is
used only for scoring how close the signal was to the surrounding local low.

To reduce overfitting, variants are specified before the run and ranked twice:
on broad-market ETFs and on a held-out set of sectors/themes. Parameters are not
searched per symbol.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.data import DATA_DIR, load_bars
from backtesting.engine.types import Bar


BROAD_ETFS = [
    "SPY", "DIA", "IWM", "VTI", "EFA", "VEA", "EEM", "VWO", "VT", "ACWI", "URTH",
]
VALIDATION_ETFS = [
    "QQQ", "SMH", "XLK", "XBI", "IBB", "XLF", "XLE", "XLI", "XLY", "XLP",
    "XLV", "XLU", "IYT", "VNQ", "GLD", "TLT", "AGG", "DBC",
]
ETF_UNIVERSE = BROAD_ETFS + VALIDATION_ETFS

# No grid search: these are distinct, legible hypotheses.
VARIANTS = {
    # Pine as written on its documented weekly timeframe. 200/250 weeks is a
    # much slower rule than its input labels imply.
    "pine_current": {
        "sma": 200, "dd_window": 250, "dd_min": 0.10, "rsi_sweep": 35.0,
        "rsi_reclaim": 30.0, "near_sma": 1.03, "mode": "either",
    },
    # Weekly equivalents of the familiar daily 200-SMA / one-year high.
    "balanced_reclaim": {
        "sma": 40, "dd_window": 52, "dd_min": 0.10, "rsi_sweep": 35.0,
        "rsi_reclaim": 35.0, "near_sma": 1.05, "mode": "either",
    },
    "rsi_reclaim": {
        "sma": 40, "dd_window": 52, "dd_min": 0.10, "rsi_sweep": 35.0,
        "rsi_reclaim": 35.0, "near_sma": None, "mode": "rsi",
    },
    "sma_reclaim": {
        "sma": 40, "dd_window": 52, "dd_min": 0.10, "rsi_sweep": 35.0,
        "rsi_reclaim": 35.0, "near_sma": None, "mode": "sma",
    },
    "capitulation_reclaim": {
        "sma": 40, "dd_window": 52, "dd_min": 0.20, "rsi_sweep": 30.0,
        "rsi_reclaim": 35.0, "near_sma": None, "mode": "rsi",
    },
    # A deliberately naive baseline: first cross into a 20% drawdown.
    "drawdown_cross": {
        "sma": 40, "dd_window": 52, "dd_min": 0.20, "rsi_sweep": 35.0,
        "rsi_reclaim": 35.0, "near_sma": None, "mode": "drawdown",
    },
}


@dataclass
class SignalScore:
    symbol: str
    variant: str
    signal_date: str
    entry_date: str
    entry_price: float
    drawdown_at_signal: float
    bottom_distance: float | None
    weeks_from_local_bottom: int | None
    mae_13w: float | None
    return_26w: float | None
    return_52w: float | None
    return_156w: float | None
    excess_return_52w: float | None


def weekly_bars(bars: list[Bar]) -> list[Bar]:
    groups: dict[tuple[int, int], list[Bar]] = defaultdict(list)
    for bar in bars:
        d = date.fromisoformat(bar.t[:10])
        iso = d.isocalendar()
        groups[(iso.year, iso.week)].append(bar)
    out = []
    for key in sorted(groups):
        week = sorted(groups[key], key=lambda b: b.t)
        out.append(
            Bar(
                t=week[-1].t,
                o=week[0].o,
                h=max(b.h for b in week),
                l=min(b.l for b in week),
                c=week[-1].c,
                v=sum(b.v for b in week),
            )
        )
    return out


def _rolling_max(src: np.ndarray, length: int) -> np.ndarray:
    out = np.full(len(src), np.nan)
    for i in range(length - 1, len(src)):
        out[i] = float(np.max(src[i - length + 1 : i + 1]))
    return out


def signal_indices(bars: list[Bar], cfg: dict, cooldown_weeks: int = 26) -> list[int]:
    c = np.array([b.c for b in bars], dtype=float)
    h = np.array([b.h for b in bars], dtype=float)
    sma = ta.sma(c, cfg["sma"])
    rsi = ta.rsi(c, 14)
    peak = _rolling_max(h, cfg["dd_window"])
    dd = 1.0 - c / peak

    sweep = np.zeros(len(c), dtype=bool)
    for i in range(13, len(c)):
        window = rsi[i - 13 : i + 1]
        valid = window[~np.isnan(window)]
        sweep[i] = bool(len(valid) and np.min(valid) <= cfg["rsi_sweep"])
    rsi_cross = np.zeros(len(c), dtype=bool)
    sma_cross = np.zeros(len(c), dtype=bool)
    dd_cross = np.zeros(len(c), dtype=bool)
    for i in range(1, len(c)):
        rsi_cross[i] = (
            not np.isnan(rsi[i - 1])
            and rsi[i - 1] <= cfg["rsi_reclaim"]
            and rsi[i] > cfg["rsi_reclaim"]
        )
        sma_cross[i] = (
            not np.isnan(sma[i - 1])
            and c[i - 1] <= sma[i - 1]
            and c[i] > sma[i]
        )
        dd_cross[i] = (
            not np.isnan(dd[i - 1])
            and dd[i - 1] < cfg["dd_min"]
            and dd[i] >= cfg["dd_min"]
        )

    signals = []
    last = -10_000
    for i in range(1, len(c) - 1):
        if np.isnan(dd[i]) or dd[i] < cfg["dd_min"]:
            continue
        if cfg["near_sma"] is not None:
            if np.isnan(sma[i]) or c[i] > sma[i] * cfg["near_sma"]:
                continue
        mode = cfg["mode"]
        trigger = {
            "rsi": sweep[i] and rsi_cross[i],
            "sma": sma_cross[i],
            "either": (sweep[i] and rsi_cross[i]) or sma_cross[i],
            "drawdown": dd_cross[i],
        }[mode]
        if trigger and i - last >= cooldown_weeks:
            signals.append(i)
            last = i
    return signals


def score_signal(
    symbol: str,
    variant: str,
    bars: list[Bar],
    i: int,
    cfg: dict,
    baseline_52w: float | None,
) -> SignalScore:
    entry_i = i + 1
    entry = bars[entry_i].o
    peak_start = max(0, i - cfg["dd_window"] + 1)
    prior_peak = max(b.h for b in bars[peak_start : i + 1])
    dd = 1.0 - bars[i].c / prior_peak

    # Local-low quality uses +/-13 weeks only as a scoring label. It never feeds
    # the signal. Positive weeks_from_bottom means the signal came after the low.
    lo = max(0, entry_i - 13)
    hi = min(len(bars), entry_i + 14)
    local_slice = bars[lo:hi]
    local_offset = min(range(len(local_slice)), key=lambda j: local_slice[j].l)
    bottom_i = lo + local_offset
    local_low = bars[bottom_i].l
    bottom_distance = entry / local_low - 1.0

    def forward_return(weeks: int) -> float | None:
        j = entry_i + weeks
        return bars[j].c / entry - 1.0 if j < len(bars) else None

    mae_hi = min(len(bars), entry_i + 14)
    mae = min(b.l for b in bars[entry_i:mae_hi]) / entry - 1.0 if entry_i < mae_hi else None
    r52 = forward_return(52)
    return SignalScore(
        symbol=symbol,
        variant=variant,
        signal_date=bars[i].t,
        entry_date=bars[entry_i].t,
        entry_price=float(entry),
        drawdown_at_signal=float(dd),
        bottom_distance=float(bottom_distance),
        weeks_from_local_bottom=int(entry_i - bottom_i),
        mae_13w=float(mae) if mae is not None else None,
        return_26w=forward_return(26),
        return_52w=r52,
        return_156w=forward_return(156),
        excess_return_52w=(r52 - baseline_52w) if r52 is not None and baseline_52w is not None else None,
    )


def _median(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    return float(st.median(clean)) if clean else None


def summarize(scores: list[SignalScore]) -> dict:
    r52 = [s.return_52w for s in scores if s.return_52w is not None]
    by_symbol: dict[str, list[SignalScore]] = defaultdict(list)
    for score in scores:
        by_symbol[score.symbol].append(score)
    symbol_medians = []
    for symbol_scores in by_symbol.values():
        vals = [s.return_52w for s in symbol_scores if s.return_52w is not None]
        if vals:
            symbol_medians.append(float(st.median(vals)))
    return {
        "signals": len(scores),
        "symbols_with_signal": len(by_symbol),
        "median_signals_per_symbol": _median([float(len(v)) for v in by_symbol.values()]),
        "median_bottom_distance": _median([s.bottom_distance for s in scores]),
        "median_weeks_from_bottom": _median([float(s.weeks_from_local_bottom) for s in scores]),
        "within_10pct_of_bottom": (
            sum((s.bottom_distance or math.inf) <= 0.10 for s in scores) / len(scores)
            if scores else None
        ),
        "signal_after_bottom": (
            sum((s.weeks_from_local_bottom or 0) >= 0 for s in scores) / len(scores)
            if scores else None
        ),
        "more_than_4w_early": (
            sum((s.weeks_from_local_bottom or 0) < -4 for s in scores) / len(scores)
            if scores else None
        ),
        "median_mae_13w": _median([s.mae_13w for s in scores]),
        "median_return_26w": _median([s.return_26w for s in scores]),
        "median_return_52w": _median(r52),
        "median_excess_return_52w": _median([s.excess_return_52w for s in scores]),
        "median_return_156w": _median([s.return_156w for s in scores]),
        "win_rate_52w": sum(v > 0 for v in r52) / len(r52) if r52 else None,
        "positive_symbol_medians_52w": (
            sum(v > 0 for v in symbol_medians) / len(symbol_medians) if symbol_medians else None
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2000-01-01")
    p.add_argument("--end", default="2026-08-13")
    p.add_argument("--provider", default="yahoo")
    p.add_argument("--force-fetch", action="store_true")
    p.add_argument("--out", default=str(DATA_DIR / "bottom_finder_comparison.json"))
    args = p.parse_args()

    weekly: dict[str, list[Bar]] = {}
    sources = {}
    for symbol in ETF_UNIVERSE:
        try:
            bars, source = load_bars(
                symbol,
                args.start,
                args.end,
                provider=args.provider,
                warmup_calendar_days=2000,
                force=args.force_fetch,
            )
            weekly[symbol] = weekly_bars(bars)
            sources[symbol] = source
        except RuntimeError as exc:
            print(f"  [skip] {symbol}: {exc}")

    # Unconditional one-year return for every eligible week in each ETF. This is
    # the fair hurdle for a long-only timing indicator: positive forward returns
    # alone are not evidence in an upward-drifting asset.
    baseline_52w = {}
    for symbol, bars in weekly.items():
        returns = [
            bars[i + 52].c / bars[i + 1].o - 1.0
            for i in range(250, len(bars) - 52)
        ]
        baseline_52w[symbol] = float(st.median(returns)) if returns else None

    all_scores: list[SignalScore] = []
    summaries = []
    for variant, cfg in VARIANTS.items():
        variant_scores = []
        for symbol, bars in weekly.items():
            for i in signal_indices(bars, cfg):
                score = score_signal(symbol, variant, bars, i, cfg, baseline_52w[symbol])
                variant_scores.append(score)
                all_scores.append(score)
        for cohort, cohort_symbols in (
            ("all", list(weekly)),
            ("broad", [s for s in BROAD_ETFS if s in weekly]),
            ("validation", [s for s in VALIDATION_ETFS if s in weekly]),
        ):
            cohort_scores = [s for s in variant_scores if s.symbol in cohort_symbols]
            summaries.append({"variant": variant, "cohort": cohort, **summarize(cohort_scores)})

    temporal_summaries = []
    for variant in VARIANTS:
        variant_scores = [s for s in all_scores if s.variant == variant]
        for period, start_year, end_year in (
            ("pre_2013", "1900", "2013"),
            ("post_2013", "2013", "2100"),
        ):
            scores = [s for s in variant_scores if start_year <= s.entry_date[:4] < end_year]
            temporal_summaries.append(
                {"variant": variant, "period": period, **summarize(scores)}
            )

    payload = {
        "start": args.start,
        "end": args.end,
        "universe": list(weekly),
        "broad_etfs": [s for s in BROAD_ETFS if s in weekly],
        "validation_etfs": [s for s in VALIDATION_ETFS if s in weekly],
        "sources": sources,
        "variants": VARIANTS,
        "unconditional_median_return_52w": baseline_52w,
        "summaries": summaries,
        "temporal_summaries": temporal_summaries,
        "signals": [asdict(s) for s in all_scores],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(
        f"{'variant':<24}{'cohort':<12}{'signals':>8}{'close10':>9}{'after':>9}"
        f"{'MAE13':>9}{'R52':>9}{'excess':>9}{'win52':>9}{'R156':>9}"
    )
    print("-" * 115)
    for row in summaries:
        def pct(key: str) -> str:
            value = row[key]
            return "—" if value is None else f"{value:.1%}"

        print(
            f"{row['variant']:<24}{row['cohort']:<12}{row['signals']:>8}"
            f"{pct('within_10pct_of_bottom'):>9}{pct('signal_after_bottom'):>9}"
            f"{pct('median_mae_13w'):>9}{pct('median_return_52w'):>9}"
            f"{pct('median_excess_return_52w'):>9}{pct('win_rate_52w'):>9}"
            f"{pct('median_return_156w'):>9}"
        )
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
