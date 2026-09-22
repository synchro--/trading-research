#!/usr/bin/env python3
"""Deep-history study: lump sum vs DCA on US data going back to 1926.

Data (all open, no API key):
* Ken French daily research factors (Dartmouth): Mkt-RF, RF from 1926-07-01.
  US market total return = Mkt-RF + RF; the 1-month bill (RF) is the cash
  yield — this is the canonical academic US equity series (CRSP value-weighted,
  dividends included, i.e. accumulation-equivalent).
* FRED DGS10 (10-year Treasury constant maturity yield, daily from 1962).
  A constant-maturity 10-year bond index is synthesized with monthly returns
  r_m = y_{m-1}/12 - D * (y_m - y_{m-1}) and modified duration D = 8 (a
  documented approximation; FRED has no open total-return bond series).

Portfolios: stocks_100 (1926+), 80_20 and 60_40 (1962+; gold has no open daily
pre-2004 history, so the balanced/golden-butterfly proxies are not included).
Strategies: lump_sum, dca_mid, oracle_1m, oracle_cy_6m (same engines as the
modern study; X = 500 x months matched across strategies).

Everything is nominal USD, total return, no taxes/fees beyond 10+5 bps.
"""
from __future__ import annotations

import argparse
import io
import json
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import numpy as np

from backtesting.dca_vs_lumpsum import (
    CONTRIBUTION,
    MarketData,
    build_market,
    enumerate_windows,
    plan_strategy,
    run_window,
)

FRENCH_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
DATA_DIR = Path(__file__).resolve().parents[0] / "data" / "deep"
BOND_DURATION = 8.0  # years, constant approximation
STRATEGIES = ("lump_sum", "dca_mid", "oracle_1m", "oracle_cy_6m")


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research-backtest)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def get_french_daily_text(force: bool = False) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = DATA_DIR / "F-F_Research_Data_Factors_daily.csv"
    if force or not cache.exists():
        raw = _fetch(FRENCH_URL)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            cache.write_bytes(zf.read(name))
    return cache.read_text(encoding="latin-1")


def get_fred_text(series: str, force: bool = False) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = DATA_DIR / f"{series}.csv"
    if force or not cache.exists():
        cache.write_bytes(_fetch(FRED_URL.format(series=series)))
    return cache.read_text()


def parse_french_daily(text: str) -> list[tuple[str, float, float]]:
    """[(iso_date, market_total_return_decimal, risk_free_decimal)]."""
    out: list[tuple[str, float, float]] = []
    for line in text.splitlines():
        parts = line.strip().split(",")
        if not parts or len(parts) < 5:
            continue
        token = parts[0].strip()
        if len(token) != 8 or not token.isdigit():
            continue
        try:
            mkt_rf = float(parts[1])
            rf = float(parts[4])
        except ValueError:
            continue
        d = f"{token[:4]}-{token[4:6]}-{token[6:]}"
        out.append((d, (mkt_rf + rf) / 100.0, rf / 100.0))
    if not out:
        raise RuntimeError("French daily file did not parse")
    return out


def parse_fred_csv(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for i, line in enumerate(text.splitlines()):
        parts = line.split(",")
        if i == 0 or len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not d or v in (".", ""):
            continue
        try:
            out[d] = float(v)
        except ValueError:
            continue
    return out


def build_bond_index(dates: list[str], yields_by_date: dict[str, float]) -> np.ndarray:
    """Constant-maturity 10y bond total-return index on `dates` (monthly steps).

    r_m = y_{m-1}/12 - D * (y_m - y_{m-1}) with yields in decimal."""
    index = np.ones(len(dates))
    level = 1.0
    prev_month = None
    prev_yield = None
    month_last = {}
    for i, d in enumerate(dates):
        if d in yields_by_date:
            month_last[d[:7]] = i
    month_yield: dict[str, float] = {}
    for d, y in yields_by_date.items():
        month_yield[d[:7]] = y / 100.0  # decimal
    for m in sorted(month_yield):
        y = month_yield[m]
        if prev_yield is not None:
            level *= 1.0 + prev_yield / 12.0 - BOND_DURATION * (y - prev_yield)
        prev_yield = y
        if m in month_last:
            idx = month_last[m]
            for j in range(idx, len(dates)):
                if dates[j][:7] == m:
                    index[j] = level
                else:
                    break
    # days before the first bond month stay flat (not used by the portfolios)
    return index


def load_deep_market() -> tuple[MarketData, dict[str, np.ndarray]]:
    french = parse_french_daily(get_french_daily_text())
    dates = [d for d, _, _ in french]
    mkt_tr = np.array([r for _, r, _ in french])
    rf = np.array([r for _, _, r in french])
    stocks = np.cumprod(1.0 + mkt_tr)
    # cash accrual: exact 1-month-bill daily compounding (overrides y/360)
    cumlog = np.concatenate([[0.0], np.cumsum(np.log1p(rf[1:]))])

    dgs10 = parse_fred_csv(get_fred_text("DGS10"))
    bond_dates = [d for d in dates if d >= min(dgs10)] if dgs10 else []
    bonds_by_date = {k: v for k, v in dgs10.items()}
    if bond_dates:
        bonds = build_bond_index(dates, bonds_by_date)
        # before DGS10 starts the bond sleeve is undefined; portfolios gate on it
    else:
        bonds = np.ones(len(dates))

    md = build_market(dates, {"STOCKS": stocks, "BONDS": bonds}, {d: 0.0 for d in dates})
    md.cumlog = cumlog
    if bond_dates:
        first_bond_idx = next(
            i for i, d in enumerate(dates) if d[:7] > min(dgs10)[:7]
        )
    else:
        first_bond_idx = len(dates)
    return md, {"first_bond_idx": first_bond_idx}


PORTFOLIOS = {
    "stocks_100": {"STOCKS": 1.0},
    "80_20": {"STOCKS": 0.8, "BONDS": 0.2},
    "60_40": {"STOCKS": 0.6, "BONDS": 0.4},
}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--horizons", default="10,12,14,16,18,20")
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--force-fetch", action="store_true")
    p.add_argument("--out", default=str(DATA_DIR / "deep_history.json"))
    args = p.parse_args()

    if args.force_fetch or not (DATA_DIR / "DGS10.csv").exists():
        get_french_daily_text(force=args.force_fetch)
        get_fred_text("DGS10", force=args.force_fetch)

    md, meta = load_deep_market()
    print(f"deep data {md.dates[0]} -> {md.dates[-1]} ({len(md.dates)} trading days); "
          f"bonds from index {meta['first_bond_idx']} ({md.dates[meta['first_bond_idx']]})")
    horizons = [int(h) for h in args.horizons.split(",")]

    results: dict[tuple[str, str, int], np.ndarray] = {}
    starts: dict[tuple[str, int], list[str]] = {}
    for p_name, weights in PORTFOLIOS.items():
        comp = md.composite(weights)
        has_bonds = "BONDS" in weights
        for hy in horizons:
            h_months = hy * 12
            wins = [ms for _, ms in enumerate_windows(md, h_months)]
            if has_bonds:
                wins = [ms for ms in wins if ms[0].first >= meta["first_bond_idx"]]
            starts[(p_name, h_months)] = [ms[0].key for ms in wins]
            for strategy in STRATEGIES:
                terms = []
                for months in wins:
                    buys, rbd = plan_strategy(strategy, comp, months, args.contribution)
                    terms.append(run_window(md, weights, months, buys, rbd))
                results[(p_name, strategy, h_months)] = np.array(terms)
            n = len(wins)
            if n == 0:
                print(f"  {p_name} {hy}y: no windows")
                continue
            t_ls = results[(p_name, "lump_sum", h_months)]
            row = f"  {p_name:<11}{hy:>3}y n={n:<5}"
            for s in STRATEGIES[1:]:
                adv = results[(p_name, s, h_months)] / t_ls - 1.0
                row += f"  {s}: {np.median(adv):>+6.1%} (win {np.mean(adv > 0):>4.0%})"
            print(row)

    # aggregate + per-decade analysis (stocks_100, all horizons pooled)
    summary = []
    decade: dict[tuple[str, str, int], list[float]] = {}
    dca_win_windows = []
    for p_name in PORTFOLIOS:
        for hy in horizons:
            t_ls = results[(p_name, "lump_sum", hy * 12)]
            for s in STRATEGIES:
                adv = results[(p_name, s, hy * 12)] / t_ls - 1.0
                summary.append(
                    {
                        "portfolio": p_name,
                        "strategy": s,
                        "horizon_years": hy,
                        "n": int(len(adv)),
                        "median": float(np.median(results[(p_name, s, hy * 12)])),
                        "adv_median": float(np.median(adv)),
                        "adv_mean": float(np.mean(adv)),
                        "win_vs_ls": float(np.mean(adv > 0)),
                    }
                )
                if s == "dca_mid":
                    for k, a in zip(starts[(p_name, hy * 12)], adv):
                        decade.setdefault((p_name, s, int(k[:4]) // 10 * 10), []).append(a)
                        if a > 0:
                            dca_win_windows.append((p_name, hy, k, float(a)))

    print("\n=== dca_mid vs ls, by start decade (mean advantage) ===")
    for p_name in PORTFOLIOS:
        line = f"{p_name:<12}"
        for dec in sorted({d for (pn, _, d) in decade if pn == p_name}):
            vals = decade[(p_name, "dca_mid", dec)]
            line += f" {dec}s: {np.mean(vals)*100:>+6.1f}% ({len(vals)})"
        print(line)

    print(f"\n=== windows where DCA beat lump sum: {len(dca_win_windows)} ===")
    for p_name, hy, k, a in sorted(dca_win_windows, key=lambda x: x[3], reverse=True)[:25]:
        print(f"  {p_name:<11} {hy:>2}y start {k}: {a:+.1%}")

    # per-window 10y series for stocks_100 (figure input)
    per_window_10y = []
    if ("stocks_100", "lump_sum", 120) in results:
        t_ls = results[("stocks_100", "lump_sum", 120)]
        adv_d = results[("stocks_100", "dca_mid", 120)] / t_ls - 1.0
        adv_o = results[("stocks_100", "oracle_cy_6m", 120)] / t_ls - 1.0
        per_window_10y = [
            {"start": k, "dca_adv": float(a), "oracle_adv": float(o)}
            for k, a, o in zip(starts[("stocks_100", 120)], adv_d, adv_o)
        ]

    payload = {
        "params": {
            "contribution": args.contribution,
            "horizons_years": horizons,
            "bond_duration": BOND_DURATION,
            "sources": {"stocks_cash": "Ken French daily factors (Mkt-RF+RF, RF)", "bonds": "FRED DGS10 synthesized TR"},
            "portfolios": PORTFOLIOS,
        },
        "data": {"range": [md.dates[0], md.dates[-1]], "days": len(md.dates)},
        "summary": summary,
        "dca_win_windows": [
            {"portfolio": p, "horizon_years": h, "start": k, "adv_vs_ls": a}
            for p, h, k, a in dca_win_windows
        ],
        "per_window_10y_stocks": per_window_10y,
        "decade_mean_adv": [
            {"portfolio": p, "decade": d, "mean_adv": float(np.mean(v)), "n": len(v)}
            for (p, _s, d), v in sorted(decade.items())
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
