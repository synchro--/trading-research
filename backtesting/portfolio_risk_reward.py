#!/usr/bin/env python3
"""Portfolio risk-reward review: Sharpe/Sortino optimizer, LS vs Smart PAC,
crisis overlays, and growth-driver sleeves.

Three tracks:

1. Allocation optimizer (no scipy): Dirichlet random search over a deep-history
   asset set (SPY/EFA/EEM/AGG/GLD/VBR/VTV/SHY/IEF/XLE + CASH), daily-rebalanced
   static weights, metrics CAGR/vol/Sharpe/Sortino/maxDD/Calmar. Train
   2004-12..2015-12, test 2016-01..latest; selection maximises the harmonic
   mean of train Sharpe and Sortino (clipped to 0..3) under per-asset weight
   <= 0.40. Optimal vectors also run through the LS vs Smart PAC engine. A
   second, short-window optimizer runs on the actual 10 holdings + candidates
   (EUNA bonds, XLE energy) over their common calendar as a reality check.

2. Lump sum vs Smart PAC: same window scheme as dca_vs_lumpsum (horizons
   {10,12,14,16,18,20}y x every monthly start, 500/mo, 10+5 bps, waiting cash
   at ^IRX). Strategies: lump_sum, dca_mid, smart_pac (this study's
   budget-neutral 2x/0 dip rule: 2x on the deep dip trigger, 0 the following
   month, chained across consecutive triggers, exact sum == 500xN), and
   dip2x_half (from dip_dca — invests extra capital by design; per-EUR columns
   separate timing from budget). Portfolios: four classics plus
   actual_proxy / actual_plus_bonds / actual_plus_oil / optimal_*.

   Note: dip_dca's `dip2x_neutral` does NOT repay (neighbor=0 leaves the next
   month at 1x; research median invested 111,750 vs dca 72,000). smart_pac
   here is the corrected budget-neutral rule for fair LS comparison.

3. Stress and tilts: fixed crisis windows (GFC, euro debt, COVID, 2022 rates,
   2008 oil) on every deep portfolio; worst rolling 6-month return; growth
   sleeves SMH/XLE/XBI/XLF/QQQ standalone metrics (own history, split at 2016);
   hypothetical forward shocks (AI burst, war/oil, US moderate growth) applied
   arithmetically to the current actual holdings.

Assumptions match the parent studies: total-return Yahoo bars, fills at close,
no TER/taxes, nominal USD with EUR labels. Optimizer risk metrics assume daily
rebalancing to static weights (drag-free approximation).
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from backtesting.dca_vs_lumpsum import (
    CASH,
    CONTRIBUTION,
    HORIZON_YEARS,
    YIELD_SYMBOL,
    MarketData,
    build_market,
    enumerate_windows,
    plan_strategy,
    run_window,
)
from backtesting.dip_dca import plan_dip, rolling_max
from backtesting.engine.data import DATA_DIR, load_bars

FETCH_START = "2004-11-01"
TRAIN_END = "2015-12-31"
PAC_STRATEGIES = ("lump_sum", "dca_mid", "smart_pac", "dip2x_half")
SMART_PAC = "smart_pac"

# ------------------------------------------------------------ actual book
ACTUAL_VALUE_EUR = {
    "IWDA.AS": 3002.84,
    "XEON.DE": 2524.37,
    "IQSA.L": 2423.61,
    "ZPRX.DE": 2174.68,
    "E127.L": 1349.59,
    "IGLD.DE": 842.34,
    "ALAT.PA": 745.93,
    "VHYL.L": 630.47,
    "EUHD.MI": 625.68,
    "SEMI.L": 320.89,
}
CANDIDATES = ("EUNA.DE", "XLE")  # bond / energy adds, not currently held

_total_eur = sum(ACTUAL_VALUE_EUR.values())
ACTUAL_WEIGHTS = {s: v / _total_eur for s, v in ACTUAL_VALUE_EUR.items()}

# Deep proxies for the actual book (role mapping, renormalised to 1.0):
# global IWDA+IQSA+SEMI -> SPY/EFA 70/30; value/div ZPRX+VHYL+EUHD -> VBR/VTV;
# EM E127+ALAT -> EEM; gold IGLD -> GLD; cash XEON -> CASH.
ACTUAL_PROXY = {
    "SPY": 0.275,
    "EFA": 0.118,
    "VBR": 0.117,
    "VTV": 0.117,
    "EEM": 0.143,
    "GLD": 0.058,
    CASH: 0.172,
}
ACTUAL_PLUS_BONDS = {
    "SPY": 0.205,
    "EFA": 0.088,
    "AGG": 0.100,
    "VBR": 0.117,
    "VTV": 0.117,
    "EEM": 0.143,
    "GLD": 0.058,
    CASH: 0.172,
}
ACTUAL_PLUS_OIL = {
    "SPY": 0.239,
    "EFA": 0.103,
    "VBR": 0.117,
    "VTV": 0.117,
    "EEM": 0.124,
    "XLE": 0.070,
    "GLD": 0.058,
    CASH: 0.172,
}

OPTIMIZER_ASSETS = ["SPY", "EFA", "EEM", "AGG", "GLD", "VBR", "VTV", "SHY", "IEF", "XLE"]
MAX_W = 0.40
N_SAMPLES = 6000
GROWTH_FLOOR = 0.07  # train CAGR floor for selected_growth
GROWTH_DRIVERS = ("SMH", "XLE", "XBI", "XLF", "QQQ")

CRISIS_WINDOWS = (
    ("oil_spike_2008", "2008-01-02", "2008-06-30"),
    ("gfc_crash", "2008-09-01", "2009-03-31"),
    ("gfc_recovery", "2009-03-31", "2010-03-31"),
    ("euro_debt", "2011-07-01", "2011-12-31"),
    ("taper_tantrum", "2013-05-22", "2013-06-24"),
    ("covid_crash", "2020-02-19", "2020-03-23"),
    ("covid_recovery", "2020-03-23", "2020-12-31"),
    ("rates_bear_2022", "2022-01-03", "2022-10-12"),
)

# Arithmetic forward shocks on the current actual book (illustrative, not paths).
SCENARIOS = {
    "ai_burst": {
        "IWDA.AS": -0.35,
        "IQSA.L": -0.35,
        "ZPRX.DE": -0.40,
        "E127.L": -0.40,
        "ALAT.PA": -0.35,
        "VHYL.L": -0.25,
        "EUHD.MI": -0.25,
        "SEMI.L": -0.55,
        "IGLD.DE": 0.10,
        "XEON.DE": 0.0,
    },
    "war_oil_shock": {
        "IWDA.AS": -0.15,
        "IQSA.L": -0.15,
        "ZPRX.DE": -0.18,
        "E127.L": -0.20,
        "ALAT.PA": -0.10,
        "VHYL.L": -0.08,
        "EUHD.MI": -0.08,
        "SEMI.L": -0.20,
        "IGLD.DE": 0.25,
        "XEON.DE": 0.0,
    },
    "us_moderate_growth": {
        "IWDA.AS": 0.12,
        "IQSA.L": 0.12,
        "ZPRX.DE": 0.15,
        "E127.L": 0.10,
        "ALAT.PA": 0.14,
        "VHYL.L": 0.10,
        "EUHD.MI": 0.10,
        "SEMI.L": 0.18,
        "IGLD.DE": 0.00,
        "XEON.DE": 0.03,
    },
}


# ------------------------------------------------------------ loading

def load_deep_panel(end: str, force: bool) -> tuple[MarketData, dict[str, str]]:
    """Deep-history market on the intersection of optimizer + classic symbols."""
    from backtesting.dca_vs_lumpsum import PORTFOLIOS as CLASSIC

    symbols = sorted(
        set(OPTIMIZER_ASSETS)
        | {s for p in CLASSIC.values() for s in p if s != CASH}
        | {s for p in (ACTUAL_PROXY, ACTUAL_PLUS_BONDS, ACTUAL_PLUS_OIL) for s in p if s != CASH}
    )
    closes_raw: dict[str, dict[str, float]] = {}
    sources: dict[str, str] = {}
    for symbol in symbols:
        bars, src = load_bars(
            symbol, FETCH_START, end, provider="yahoo", warmup_calendar_days=0, force=force
        )
        assert bars[0].t <= "2005-01-31", f"{symbol} history too shallow: starts {bars[0].t}"
        closes_raw[symbol] = {b.t: b.c for b in bars}
        sources[symbol] = src

    from backtesting.engine.data import fetch_yahoo

    try:
        ybars = fetch_yahoo(YIELD_SYMBOL, "2004-01-01", end)
        ysrc = "yahoo raw (no split-adjust)"
    except Exception as e:
        ybars, ysrc = [], f"yahoo failed: {e}"
    sources[YIELD_SYMBOL] = ysrc
    yields_by_date: dict[str, float] = {}
    for b in ybars:
        y = b.c / (100.0 if b.c >= 0.2 else 1.0)
        if 0.0 < y < 0.15:
            yields_by_date[b.t] = y

    common = sorted(set.intersection(*(set(v) for v in closes_raw.values())))
    assert common[0] <= "2004-12-31", f"common calendar starts {common[0]}"
    closes = {s: np.array([closes_raw[s][d] for d in common]) for s in closes_raw}
    ff: dict[str, float] = {}
    last = 0.0
    for d in common:
        y = yields_by_date.get(d)
        if y is not None:
            last = y
        ff[d] = last
    return build_market(common, closes, ff), sources


def load_actual_panel(end: str, force: bool) -> tuple[list[str], list[str], np.ndarray]:
    """Common-calendar closes for the actual book + candidates.

    Returns (dates, symbols, closes[symbol, day])."""
    symbols = sorted(set(ACTUAL_VALUE_EUR) | set(CANDIDATES))
    closes_raw: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        bars, _ = load_bars(
            symbol, "2010-01-01", end, provider="yahoo", warmup_calendar_days=0, force=force
        )
        closes_raw[symbol] = {b.t: b.c for b in bars}
    common = sorted(set.intersection(*(set(v) for v in closes_raw.values())))
    closes = np.stack([np.array([closes_raw[s][d] for d in common]) for s in symbols])
    return common, symbols, closes


# ------------------------------------------------------------ risk metrics

def daily_returns(series: np.ndarray) -> np.ndarray:
    return series[1:] / series[:-1] - 1.0


def risk_metrics(rets: np.ndarray, start: str, end: str, periods: int = 252) -> dict:
    """CAGR/vol/Sharpe/Sortino/maxDD/Calmar from daily returns start->end."""
    if len(rets) < 2:
        return {"n": int(len(rets))}
    equity = np.cumprod(1.0 + rets)
    years = max((date.fromisoformat(end) - date.fromisoformat(start)).days, 1) / 365.25
    cagr = float(equity[-1] ** (1.0 / years) - 1.0) if equity[-1] > 0 else -1.0
    vol = float(np.std(rets, ddof=1) * np.sqrt(periods))
    mean = float(np.mean(rets))
    std = float(np.std(rets, ddof=1))
    sharpe = float(mean / std * np.sqrt(periods)) if std > 0 else 0.0
    downside = rets[rets < 0]
    dd_std = float(np.sqrt(np.mean(downside**2))) if len(downside) else 0.0
    sortino = float(mean / dd_std * np.sqrt(periods)) if dd_std > 0 else float("inf")
    peaks = np.maximum.accumulate(np.concatenate([[1.0], equity]))
    max_dd = float(np.max(1.0 - equity / peaks[1:]))
    return {
        "n": int(len(rets)),
        "cagr": cagr,
        "ann_vol": vol,
        "sharpe": sharpe,
        "sortino": None if not np.isfinite(sortino) else float(sortino),
        "max_dd": max_dd,
        "calmar": float(cagr / max_dd) if max_dd > 0 else None,
        "total_return": float(equity[-1] - 1.0),
    }


def split_metrics(rets: np.ndarray, dates: list[str] | np.ndarray) -> dict:
    """full/train/test metrics. `dates` are close dates, len == len(rets)+1.

    Return i is the move into dates[i+1]; train = returns whose end date <= TRAIN_END."""
    dates = list(dates)
    end_dates = dates[1 : len(rets) + 1]
    train_n = sum(1 for d in end_dates if d <= TRAIN_END)
    if train_n < 60 or len(rets) - train_n < 60:
        return {
            "full": risk_metrics(rets, dates[0], end_dates[-1]),
            "train": risk_metrics(rets, dates[0], end_dates[-1]),
            "test": risk_metrics(rets, dates[0], end_dates[-1]),
            "note": "split unavailable (too short); train=test=full",
        }
    return {
        "full": risk_metrics(rets, dates[0], end_dates[-1]),
        "train": risk_metrics(rets[:train_n], dates[0], end_dates[train_n - 1]),
        "test": risk_metrics(rets[train_n:], end_dates[train_n - 1], end_dates[-1]),
    }


def harmonic_sharpe_sortino(sharpe: float, sortino: float | None) -> float:
    s_h = float(np.clip(sharpe, 0.0, 3.0))
    s_s = float(np.clip(0.0 if sortino is None else sortino, 0.0, 3.0))
    if s_h + s_s == 0:
        return 0.0
    return 2.0 * s_h * s_s / (s_h + s_s)


def build_return_matrix(
    md: MarketData, assets: list[str]
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Daily returns [T-1, A] for assets + synthetic CASH from ^IRX accrual."""
    cols = [md.closes[s][1:] / md.closes[s][ :-1] - 1.0 for s in assets]
    cols.append(np.expm1(np.diff(md.cumlog)))
    rets = np.stack(cols, axis=1)
    return rets, np.array(md.dates[1:]), assets + [CASH]


def portfolio_returns_deep(md: MarketData, weights: dict[str, float]) -> np.ndarray:
    """Daily returns of the weighted book: risk composite blended with CASH accrual."""
    risky = sum(v for s, v in weights.items() if s != CASH)
    cash_w = weights.get(CASH, 0.0)
    if abs(risky + cash_w - 1.0) > 1e-9:
        raise ValueError(f"{weights}: weights sum to {risky + cash_w}, expected 1.0")
    comp = md.composite(weights)
    pr = comp[1:] / comp[:-1] - 1.0
    if cash_w:
        cr = np.expm1(np.diff(md.cumlog))
        return risky * pr + cash_w * cr
    return pr


def optimize_weights(
    rets: np.ndarray,
    dates: np.ndarray,
    assets: list[str],
    n_samples: int = N_SAMPLES,
    max_w: float = MAX_W,
    seed: int = 7,
) -> dict:
    """Dirichlet random search; select by train harmonic(Sharpe, Sortino).

    Constraints: w >= 0, sum = 1, each asset <= max_w. `dates` are the return
    end dates (same length as rets). Train/test split is the TRAIN_END cut when
    both sides are long enough; otherwise a chronological 70/30 split."""
    rng = np.random.default_rng(seed)
    n_assets = rets.shape[1]

    end_dates = list(dates)
    train_n = sum(1 for d in end_dates if d <= TRAIN_END)
    split_note = "train_end_cut"
    if train_n < 60 or len(rets) - train_n < 60:
        train_n = int(len(rets) * 0.7)
        split_note = "chronological_70_30"
    train_rets = rets[:train_n]
    test_rets = rets[train_n:]
    train_start = str(end_dates[0])
    train_end = end_dates[train_n - 1]
    test_start = end_dates[train_n - 1] if train_n < len(rets) else train_end
    test_end = end_dates[-1]

    samples: list[np.ndarray] = []
    scores: list[float] = []
    sharpes: list[float] = []
    sortinos: list[float] = []
    cagrs: list[float] = []
    attempts = 0
    while len(samples) < n_samples and attempts < n_samples * 20:
        attempts += 1
        w = rng.dirichlet(np.ones(n_assets))
        if w.max() > max_w:
            continue
        m = risk_metrics(train_rets @ w, train_start, train_end)
        sh = m.get("sharpe") or 0.0
        so = m.get("sortino") or 0.0
        samples.append(w)
        sharpes.append(sh)
        sortinos.append(so)
        cagrs.append(m.get("cagr") or 0.0)
        scores.append(harmonic_sharpe_sortino(sh, so))

    if not samples:
        raise RuntimeError("optimizer produced no feasible samples")
    W = np.stack(samples)
    scores_a = np.array(scores)
    sharpes_a = np.array(sharpes)
    sortinos_a = np.array(sortinos)
    cagrs_a = np.array(cagrs)

    def _report(i: int) -> dict:
        w = W[i]
        tr = risk_metrics(train_rets @ w, train_start, train_end)
        te = (
            risk_metrics(test_rets @ w, test_start, test_end)
            if len(test_rets) >= 2
            else {"n": 0}
        )
        return {
            "weights": {assets[j]: float(w[j]) for j in range(n_assets) if w[j] > 1e-4},
            "train": tr,
            "test": te,
        }

    i_harm = int(np.argmax(scores_a))
    i_sharpe = int(np.argmax(sharpes_a))
    i_sortino = int(np.argmax(sortinos_a))
    # Growth-constrained: best harmonic among samples with train CAGR >= 7%
    # (guards against the pure-risk optimum drifting into bond-heavy low growth).
    growth_ok = np.where(cagrs_a >= GROWTH_FLOOR)[0]
    if len(growth_ok):
        i_growth = int(growth_ok[np.argmax(scores_a[growth_ok])])
        growth_note = f"n={len(growth_ok)} feasible at train CAGR >= {GROWTH_FLOOR:.0%}"
    else:
        i_growth = i_harm
        growth_note = "no sample met train CAGR floor; fell back to pure harmonic"

    order = np.argsort(-sharpes_a)
    front: list[int] = []
    best_so = -np.inf
    for i in order:
        if sortinos_a[i] > best_so:
            front.append(int(i))
            best_so = sortinos_a[i]
    step = max(1, len(front) // 25)

    return {
        "n_feasible": len(samples),
        "n_attempts": attempts,
        "max_w": max_w,
        "split": split_note,
        "train_span": [train_start, train_end],
        "test_span": [test_start, test_end],
        "objective": "max harmonic(train sharpe, train sortino), clip 0..3",
        "growth_floor": GROWTH_FLOOR,
        "growth_note": growth_note,
        "selected_harmonic": _report(i_harm),
        "selected_sharpe": _report(i_sharpe),
        "selected_sortino": _report(i_sortino),
        "selected_growth": _report(i_growth),
        "pareto_front": [
            {
                "weights": {assets[j]: float(W[i, j]) for j in range(n_assets) if W[i, j] > 1e-4},
                "train_sharpe": float(sharpes_a[i]),
                "train_sortino": float(sortinos_a[i]),
            }
            for i in front[::step]
        ],
        "harmonic_train": float(scores_a[i_harm]),
    }


# ------------------------------------------------------------ PAC planning

def plan_any(
    strategy: str,
    comp: np.ndarray,
    months: list,
    contribution: float,
    roll20: np.ndarray,
):
    """Planner returning (buys, rebalance_days, invested_array, meta).

    smart_pac is the budget-neutral rule this study defines: 2x on the deep dip
    trigger, 0 the following month, chained across consecutive triggers, with a
    final balancing pass so invested == contribution * N exactly."""
    if strategy in ("lump_sum", "dca_mid"):
        buys, rbd = plan_strategy(strategy, comp, months, contribution)
        invested = float(sum(a for _, tr in buys for a, _ in tr))
        return buys, rbd, np.array([invested]), {}
    if strategy == "smart_pac":
        return plan_smart_pac(comp, months, contribution, roll20)
    buys, rbd, invested, meta = plan_dip(strategy, comp, months, contribution, roll20)
    return buys, rbd, invested, meta


def plan_smart_pac(
    comp: np.ndarray,
    months: list,
    contribution: float,
    roll20: np.ndarray,
    dd: float = 0.03,
    min_consec: int = 1,
):
    """Budget-neutral Smart PAC (2x/0) with exact sum == contribution * N.

    Trigger = same deep rule as dip_dca v2 (red running-low, >=dd below the
    rolling-high window). On a trigger deploy 2x; each subsequent non-trigger
    month first absorbs one pending payback (deploy 0) before resuming 1x.
    Consecutive triggers chain the payback forward. A trailing payback that
    does not fit before the window ends is settled by reducing the latest
    2x deployments toward 1x (never below 0), so the budget identity holds.
    """
    from backtesting.dip_dca import find_trigger_day

    n = len(months)
    triggers = [find_trigger_day(comp, m, roll20, dd, min_consec) for m in months]
    desired = [0.0] * n
    pending = 0
    for i, m in enumerate(months):
        if triggers[i] is not None:
            desired[i] = 2.0 * contribution
            pending += 1
        elif pending > 0:
            desired[i] = 0.0
            pending -= 1
        else:
            desired[i] = contribution

    budget = contribution * n
    total = sum(desired)
    if total > budget + 1e-9:
        excess = total - budget
        for k in range(n - 1, -1, -1):  # trim 2x -> 1x first
            if excess <= 1e-9:
                break
            if desired[k] > contribution + 1e-9:
                take = min(desired[k] - contribution, excess)
                desired[k] -= take
                excess -= take
        for k in range(n - 1, -1, -1):  # then any remainder -> 0
            if excess <= 1e-9:
                break
            if desired[k] > 0:
                take = min(desired[k], excess)
                desired[k] -= take
                excess -= take
    elif total < budget - 1e-9:
        desired[-1] += budget - total

    buys: list[tuple[int, list[tuple[float, int]]]] = []
    for i, m in enumerate(months):
        amt = desired[i]
        if amt <= 1e-9:
            continue
        day = triggers[i] if triggers[i] is not None else m.mid
        buys.append((day, [(amt, m.first)]))
    rebalance_days = [m.first for k, m in enumerate(months) if k >= 12 and k % 12 == 0]
    invested = np.array([a for _, tr in buys for a, _ in tr], dtype=float)
    assert abs(float(invested.sum()) - budget) < 1e-6, (
        f"smart_pac invested {invested.sum()} != {budget}"
    )
    meta = {
        "triggered_months": sum(1 for t in triggers if t is not None),
        "months": n,
        "pending_unpaid_at_end": pending,
    }
    return buys, rebalance_days, invested, meta


def run_pac_study(
    md: MarketData,
    portfolios: dict[str, dict[str, float]],
    horizons: tuple[int, ...] = HORIZON_YEARS,
    contribution: float = CONTRIBUTION,
) -> dict:
    all_windows: dict[int, list[list]] = {
        hy * 12: [ms for _, ms in enumerate_windows(md, hy * 12)] for hy in horizons
    }
    terminals: dict[tuple[str, str, int], np.ndarray] = {}
    invested: dict[tuple[str, str, int], np.ndarray] = {}
    records: list[dict] = []

    for p_name, weights in portfolios.items():
        comp = md.composite(weights)
        roll20 = rolling_max(comp, 20)
        for strategy in PAC_STRATEGIES:
            for hy in horizons:
                h = hy * 12
                terms, invs = [], []
                for months in all_windows[h]:
                    buys, rbd, inv, _ = plan_any(strategy, comp, months, contribution, roll20)
                    terms.append(run_window(md, weights, months, buys, rbd))
                    invs.append(float(np.sum(inv)))
                t_arr = np.array(terms)
                i_arr = np.array(invs)
                terminals[(p_name, strategy, h)] = t_arr
                invested[(p_name, strategy, h)] = i_arr
                for k, months in enumerate(all_windows[h]):
                    records.append(
                        {
                            "portfolio": p_name,
                            "strategy": strategy,
                            "horizon_years": hy,
                            "start": months[0].key,
                            "end": months[-1].key,
                            "invested": float(i_arr[k]),
                            "terminal": float(t_arr[k]),
                            "per_euro": float(t_arr[k] / i_arr[k]) if i_arr[k] else None,
                        }
                    )

    summary: list[dict] = []
    horizon_medians: dict[str, dict[str, dict[int, float]]] = {}
    for p_name in portfolios:
        hm: dict[str, dict[int, float]] = {}
        for strategy in PAC_STRATEGIES:
            T = np.concatenate([terminals[(p_name, strategy, hy * 12)] for hy in horizons])
            I = np.concatenate([invested[(p_name, strategy, hy * 12)] for hy in horizons])
            LS = np.concatenate([terminals[(p_name, "lump_sum", hy * 12)] for hy in horizons])
            LS_I = np.concatenate([invested[(p_name, "lump_sum", hy * 12)] for hy in horizons])
            DCA = np.concatenate([terminals[(p_name, "dca_mid", hy * 12)] for hy in horizons])
            DCA_I = np.concatenate([invested[(p_name, "dca_mid", hy * 12)] for hy in horizons])
            pe, pe_ls, pe_dca = T / I, LS / LS_I, DCA / DCA_I
            summary.append(
                {
                    "portfolio": p_name,
                    "strategy": strategy,
                    "n": int(len(T)),
                    "median": float(np.median(T)),
                    "mean": float(np.mean(T)),
                    "p5": float(np.percentile(T, 5)),
                    "p95": float(np.percentile(T, 95)),
                    "median_invested": float(np.median(I)),
                    "win_vs_ls": float(np.mean(T > LS)),
                    "adv_median_vs_ls": float(np.median(T / LS - 1.0)),
                    "win_vs_dca": float(np.mean(T > DCA)),
                    "adv_median_vs_dca": float(np.median(T / DCA - 1.0)),
                    "per_euro_adv_median_vs_dca": float(np.median(pe / pe_dca - 1.0)),
                    "per_euro_adv_median_vs_ls": float(np.median(pe / pe_ls - 1.0)),
                }
            )
            hm[strategy] = {
                hy: float(np.median(terminals[(p_name, strategy, hy * 12)])) for hy in horizons
            }
        horizon_medians[p_name] = hm
    return {"summary": summary, "horizon_medians": horizon_medians, "records": records}


# ------------------------------------------------------------ stress / drivers

def crisis_metrics(md: MarketData, portfolios: dict[str, dict[str, float]]) -> list[dict]:
    out: list[dict] = []
    for p_name, weights in portfolios.items():
        comp = md.composite(weights)
        idx = {d: i for i, d in enumerate(md.dates)}
        for label, a, b in CRISIS_WINDOWS:
            keys = [d for d in md.dates if a <= d <= b]
            if len(keys) < 5:
                continue
            i0, i1 = idx[keys[0]], idx[keys[-1]]
            out.append(
                {
                    "portfolio": p_name,
                    "window": label,
                    "start": keys[0],
                    "end": keys[-1],
                    "return": float(comp[i1] / comp[i0] - 1.0),
                }
            )
        if len(comp) > 130:
            log_r = np.log1p(comp[1:] / comp[:-1] - 1.0)
            roll_log = np.convolve(log_r, np.ones(126), mode="valid")
            out.append(
                {
                    "portfolio": p_name,
                    "window": "worst_6m_rolling",
                    "start": None,
                    "end": None,
                    "return": float(np.expm1(roll_log.min())),
                }
            )
    return out


def driver_metrics(end: str, force: bool = False) -> list[dict]:
    out = []
    for sym in GROWTH_DRIVERS:
        try:
            bars, src = load_bars(
                sym, "2004-01-01", end, provider="yahoo", warmup_calendar_days=0, force=force
            )
        except Exception as e:
            out.append({"symbol": sym, "error": str(e)})
            continue
        closes = np.array([b.c for b in bars])
        dates = [b.t for b in bars]
        out.append({"symbol": sym, "source": src, **split_metrics(daily_returns(closes), dates)})
    return out


def scenario_overlay(weights: dict[str, float], shocks: dict[str, float]) -> dict[str, float]:
    """Apply per-holding shocks then renormalise (weights stay a book share)."""
    out = {s: w * (1.0 + shocks.get(s, 0.0)) for s, w in weights.items()}
    total = sum(out.values())
    return {s: w / total for s, w in out.items()}


def scenario_return(weights: dict[str, float], shocks: dict[str, float]) -> float:
    """Portfolio-level return of applying shocks to current weights (pre-renorm)."""
    return float(sum(weights[s] * shocks.get(s, 0.0) for s in weights))


# ------------------------------------------------------------ printing / main

def _print_pac(summary: list[dict]) -> None:
    print("\n=== LS vs Smart PAC (all windows pooled) ===")
    print(
        f"{'portfolio':<18}{'strategy':<16}{'median':>11}{'inv med':>10}"
        f"{'win>LS':>8}{'advLS med':>10}{'win>dca':>8}{'€/€ vs dca':>11}"
    )
    print("-" * 92)
    for r in summary:
        print(
            f"{r['portfolio']:<18}{r['strategy']:<16}{r['median']:>11,.0f}"
            f"{r['median_invested']:>10,.0f}{r['win_vs_ls']:>7.0%}"
            f"{r['adv_median_vs_ls']:>+10.1%}{r['win_vs_dca']:>7.0%}"
            f"{r['per_euro_adv_median_vs_dca']:>+11.1%}"
        )


def _print_metrics(rows: list[dict], label_key: str = "portfolio") -> None:
    print(
        f"\n{'name':<18}{'CAGR':>8}{'vol':>8}{'Sharpe':>8}{'Sortino':>8}"
        f"{'maxDD':>8}{'Calmar':>8}{'trSh':>7}{'trSo':>7}{'teSh':>7}{'teSo':>7}"
    )
    print("-" * 96)
    for r in rows:
        f, tr, te = r["full"], r["train"], r["test"]
        print(
            f"{r[label_key]:<18}{f.get('cagr', 0):>7.1%}{f.get('ann_vol', 0):>7.1%}"
            f"{f.get('sharpe', 0):>8.2f}{f.get('sortino') or 0:>8.2f}"
            f"{f.get('max_dd', 0):>7.1%}{f.get('calmar') or 0:>8.2f}"
            f"{tr.get('sharpe', 0):>7.2f}{(tr.get('sortino') or 0):>7.2f}"
            f"{te.get('sharpe', 0):>7.2f}{(te.get('sortino') or 0):>7.2f}"
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--end", default="2026-12-31")
    p.add_argument("--horizons", default=",".join(str(h) for h in HORIZON_YEARS))
    p.add_argument("--contribution", type=float, default=CONTRIBUTION)
    p.add_argument("--samples", type=int, default=N_SAMPLES)
    p.add_argument("--reuse-cache", action="store_true")
    p.add_argument("--skip-pac", action="store_true", help="optimizer + stress only (fast)")
    p.add_argument("--out", default=str(DATA_DIR / "portfolio_risk_reward.json"))
    args = p.parse_args()
    force = not args.reuse_cache

    md, sources = load_deep_panel(args.end, force=force)
    print(f"deep panel {md.dates[0]} -> {md.dates[-1]}, {len(md.dates)} days; {len(sources)} symbols")

    # ---- phase 1: deep optimizer
    rets, ret_dates, assets = build_return_matrix(md, OPTIMIZER_ASSETS)
    opt = optimize_weights(rets, ret_dates, assets, n_samples=args.samples)
    for key in ("selected_harmonic", "selected_sharpe", "selected_sortino", "selected_growth"):
        r = opt[key]
        tr, te = r["train"], r["test"]
        print(
            f"[opt:{key}] train Sh {tr.get('sharpe', 0):.2f} So {tr.get('sortino') or 0:.2f} "
            f"CAGR {tr.get('cagr', 0):.1%} | test Sh {te.get('sharpe', 0):.2f} "
            f"So {te.get('sortino') or 0:.2f} CAGR {te.get('cagr', 0):.1%}"
        )
        print(f"  weights: {r['weights']}")

    from backtesting.dca_vs_lumpsum import PORTFOLIOS as CLASSIC

    portfolios: dict[str, dict[str, float]] = {
        **CLASSIC,
        "actual_proxy": dict(ACTUAL_PROXY),
        "actual_plus_bonds": dict(ACTUAL_PLUS_BONDS),
        "actual_plus_oil": dict(ACTUAL_PLUS_OIL),
        "optimal_harmonic": dict(opt["selected_harmonic"]["weights"]),
        "optimal_sharpe": dict(opt["selected_sharpe"]["weights"]),
        "optimal_sortino": dict(opt["selected_sortino"]["weights"]),
        "optimal_growth": dict(opt["selected_growth"]["weights"]),
    }

    port_rows = []
    for p_name, w in portfolios.items():
        pr = portfolio_returns_deep(md, w)
        port_rows.append({"portfolio": p_name, **split_metrics(pr, md.dates)})
    print("\n=== deep-panel risk metrics (daily-rebalanced static weights) ===")
    _print_metrics(port_rows)

    # ---- phase 2: LS vs Smart PAC
    pac = None
    if not args.skip_pac:
        horizons = tuple(int(h) for h in args.horizons.split(","))
        pac = run_pac_study(md, portfolios, horizons=horizons, contribution=args.contribution)
        _print_pac(pac["summary"])

    # ---- phase 3: crisis + worst 6m
    stress = crisis_metrics(md, portfolios)
    print("\n=== crisis windows (composite return) ===")
    wins = [w[0] for w in CRISIS_WINDOWS] + ["worst_6m_rolling"]
    print(f"{'portfolio':<18}" + "".join(f"{w:>14}" for w in wins))
    for p_name in portfolios:
        row = {c["window"]: c["return"] for c in stress if c["portfolio"] == p_name}
        line = f"{p_name:<18}"
        for w in wins:
            v = row.get(w)
            line += f"{v:>13.1%}" if v is not None else f"{'-':>14}"
        print(line)

    # ---- phase 4: actual book on real tickers
    dates_a, sym_a, closes_a = load_actual_panel(args.end, force=force)
    print(f"\nactual panel {dates_a[0]} -> {dates_a[-1]}, {len(dates_a)} days; {sym_a}")
    held = [s for s in sym_a if s in ACTUAL_VALUE_EUR]
    h_idx = [sym_a.index(s) for s in held]
    w_held = np.array([ACTUAL_WEIGHTS[s] for s in held])
    h_rets = (closes_a[h_idx, 1:] / closes_a[h_idx, :-1] - 1.0).T  # [T, n]
    actual_r = h_rets @ w_held
    actual_m = split_metrics(actual_r, dates_a)

    a_rets = (closes_a[:, 1:] / closes_a[:, :-1] - 1.0).T  # [T, A]
    actual_opt = optimize_weights(
        a_rets, np.array(dates_a[1:]), sym_a, n_samples=args.samples, max_w=MAX_W, seed=11
    )
    for key in ("selected_harmonic", "selected_sharpe", "selected_sortino"):
        r = actual_opt[key]
        tr, te = r["train"], r["test"]
        print(
            f"[actual-opt:{key}] train Sh {tr.get('sharpe', 0):.2f} So {tr.get('sortino') or 0:.2f} | "
            f"test Sh {te.get('sharpe', 0):.2f} So {te.get('sortino') or 0:.2f}"
        )
        print(f"  weights: {r['weights']}")

    print("\n=== actual book risk metrics (real tickers, common calendar) ===")
    _print_metrics([{"name": "current", **actual_m}], label_key="name")

    # ---- phase 5: scenario overlays on current book
    scen_rows = []
    for name, shocks in SCENARIOS.items():
        delta = scenario_return(ACTUAL_WEIGHTS, shocks)
        nw = scenario_overlay(ACTUAL_WEIGHTS, shocks)
        scen_rows.append({"scenario": name, "portfolio_return": delta, "post_weights": nw})
        print(f"[scenario:{name:<18}] portfolio return {delta:+.1%}")

    # ---- phase 6: growth drivers
    drivers = driver_metrics(args.end, force=False)
    print("\n=== growth-driver sleeves (own-history, split at 2016) ===")
    for d in drivers:
        if "error" in d:
            print(f"  {d['symbol']}: error {d['error']}")
            continue
        f, tr, te = d["full"], d["train"], d["test"]
        print(
            f"  {d['symbol']:<5} n={f.get('n', 0):<5} CAGR {f.get('cagr', 0):>6.1%} "
            f"Sharpe {f.get('sharpe', 0):>5.2f} Sortino {f.get('sortino') or 0:>5.2f} "
            f"maxDD {f.get('max_dd', 0):>6.1%} | train Sh {tr.get('sharpe', 0):>5.2f} "
            f"test Sh {te.get('sharpe', 0):>5.2f}"
        )

    # ---- write JSON
    payload = {
        "params": {
            "contribution": args.contribution,
            "horizons_years": [int(h) for h in args.horizons.split(",")],
            "commission_bps": 10.0,
            "slippage_bps": 5.0,
            "cash_yield_symbol": YIELD_SYMBOL,
            "train_end": TRAIN_END,
            "optimizer": {
                "assets": OPTIMIZER_ASSETS + [CASH],
                "n_samples": args.samples,
                "max_w": MAX_W,
                "method": "dirichlet random search, daily-rebalanced static weights",
            },
            "pac_strategies": list(PAC_STRATEGIES),
            "smart_pac": SMART_PAC,
        },
        "data": {
            "deep_range": [md.dates[0], md.dates[-1]],
            "deep_days": len(md.dates),
            "actual_range": [dates_a[0], dates_a[-1]],
            "actual_days": len(dates_a),
            "sources": sources,
        },
        "actual_weights": ACTUAL_WEIGHTS,
        "portfolios": portfolios,
        "optimizer": opt,
        "actual_optimizer": actual_opt,
        "portfolio_metrics": port_rows,
        "actual_metrics": actual_m,
        "scenarios": scen_rows,
        "drivers": drivers,
        "stress": stress,
        "pac": pac,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=float))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
