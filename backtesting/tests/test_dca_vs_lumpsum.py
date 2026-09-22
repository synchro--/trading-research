"""Unit tests for the DCA vs lump-sum rolling-window study (synthetic bars)."""
from __future__ import annotations

import unittest
from datetime import date, timedelta

import numpy as np

from backtesting.dca_vs_lumpsum import (
    CASH,
    COMM,
    SLIP,
    accrual_factor,
    argmin_day,
    build_market,
    enumerate_windows,
    plan_strategy,
    run_window,
)

PORT = {"SPY": 0.6, "EFA": 0.4}
STRATEGIES = (
    "dca_mid",
    "oracle_1m",
    "oracle_pt_3m",
    "oracle_pt_6m",
    "oracle_cy_3m",
    "oracle_cy_6m",
    "lump_sum",
)


def business_dates(n: int, start: str = "2005-01-03") -> list[str]:
    out: list[str] = []
    d = date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def make_market(n_days: int = 300, spec: dict[str, list[float]] | None = None, yield_rate: float = 0.04):
    dates = business_dates(n_days)
    n = len(dates)
    closes: dict[str, np.ndarray] = {"SPY": np.full(n, 100.0), "EFA": np.full(n, 50.0)}
    for sym, arr in (spec or {}).items():
        a = np.asarray(arr, dtype=float)
        if len(a) == n:  # ignore specs of the wrong length
            closes[sym] = a
    yields = {t: yield_rate for t in dates}
    return build_market(dates, closes, yields)


class AccrualTests(unittest.TestCase):
    def test_calendar_day_simple_interest(self) -> None:
        dates = business_dates(300)
        md = build_market(dates, {"SPY": np.ones(300)}, {t: 0.05 for t in dates})
        idx = md.dates.index("2006-01-02")
        factor = accrual_factor(md.cumlog, idx, 0)
        cal_days = (date.fromisoformat(md.dates[idx]) - date.fromisoformat(md.dates[0])).days
        expected = (1.0 + 0.05 / 360.0) ** cal_days
        self.assertAlmostEqual(factor, expected, places=9)

    def test_factor_nonpositive_window_is_one(self) -> None:
        cumlog = np.array([0.0, 0.001, 0.002])
        self.assertEqual(accrual_factor(cumlog, 1, 2), 1.0)
        self.assertEqual(accrual_factor(cumlog, 2, 2), 1.0)

    def test_zero_yield_is_flat(self) -> None:
        dates = business_dates(60)
        md = build_market(dates, {"SPY": np.ones(60)}, {t: 0.0 for t in dates})
        self.assertAlmostEqual(accrual_factor(md.cumlog, 0, 59), 1.0, places=12)


class MonthTests(unittest.TestCase):
    def test_mid_month_rolls_past_weekend(self) -> None:
        # 2007-12-15 was a Saturday: mid-month day must be Monday the 17th
        dates = business_dates(400, start="2007-01-02")
        md = build_market(dates, {"SPY": np.ones(400)}, {t: 0.0 for t in dates})
        dec = next(m for m in md.months if m.key == "2007-12")
        self.assertEqual(md.dates[dec.mid], "2007-12-17")

    def test_complete_flag_follows_last_trading_day(self) -> None:
        dates = business_dates(400, start="2007-01-02")
        md = build_market(dates, {"SPY": np.ones(400)}, {t: 0.0 for t in dates})
        for m in md.months:
            self.assertEqual(m.complete, md.dates[m.last][8:10] >= "20")


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.md = make_market(300)
        self.comp = self.md.composite(PORT)
        self.months = enumerate_windows(self.md, 12)[0][1]

    def test_invested_identity_for_all_strategies(self) -> None:
        for s in STRATEGIES:
            buys, _ = plan_strategy(s, self.comp, self.months, 500.0)
            invested = sum(a for _, tr in buys for a, _ in tr)
            self.assertAlmostEqual(invested, 500.0 * len(self.months), places=6)
            days = [d for d, _ in buys]
            self.assertEqual(days, sorted(days))
            self.assertTrue(all(d <= self.md.months[-1].last for d in days))

    def test_dca_mid_uses_mid_month_day(self) -> None:
        buys, _ = plan_strategy("dca_mid", self.comp, self.months, 500.0)
        self.assertEqual([d for d, _ in buys], [m.mid for m in self.months])
        self.assertTrue(all(a == 500.0 for _, tr in buys for a, _ in tr))

    def test_oracle_1m_buys_monthly_low(self) -> None:
        buys, _ = plan_strategy("oracle_1m", self.comp, self.months, 500.0)
        for (d, _), m in zip(buys, self.months):
            self.assertEqual(d, argmin_day(self.comp, m.days))
            self.assertIn(d, m.days)

    def test_per_tranche_span_truncated_at_window_end(self) -> None:
        n_months = len(self.months)
        buys, _ = plan_strategy("oracle_pt_3m", self.comp, self.months, 500.0)
        for k, (d, _) in enumerate(buys):
            end = min(k + 3, n_months) - 1
            allowed = [x for mm in self.months[k : end + 1] for x in mm.days]
            self.assertIn(d, allowed)

    def test_cycle_amounts(self) -> None:
        buys, _ = plan_strategy("oracle_cy_3m", self.comp, self.months, 500.0)
        self.assertEqual(len(buys), 4)  # 12 months / 3
        for _, tranches in buys:
            self.assertEqual(len(tranches), 3)
            self.assertTrue(all(a == 500.0 for a, _ in tranches))

    def test_lump_sum_single_day0_buy(self) -> None:
        buys, _ = plan_strategy("lump_sum", self.comp, self.months, 500.0)
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0][0], self.months[0].first)
        self.assertEqual(buys[0][1][0][0], 500.0 * len(self.months))


class SimTests(unittest.TestCase):
    def _window(self, md, h_months: int):
        return enumerate_windows(md, h_months)[0][1]

    def test_flat_market_dca_equals_lump_sum(self) -> None:
        md = make_market(300, spec={"SPY": []}, yield_rate=0.0)  # [] invalid -> flat 100
        months = self._window(md, 2)
        comp = md.composite(PORT)
        for s in ("dca_mid", "lump_sum"):
            buys, rbd = plan_strategy(s, comp, months, 500.0)
            term = run_window(md, PORT, months, buys, rbd)
            self.assertAlmostEqual(term, 1000.0 / ((1 + SLIP) * (1 + COMM)), places=6)
            self.assertEqual(rbd, [])

    def test_oracle_beats_lump_sum_after_dip(self) -> None:
        md = make_market(300)
        closes = md.closes["SPY"].copy()
        for d in md.months[2].days:
            closes[d] = 80.0
        md2 = build_market(md.dates, dict(md.closes, SPY=closes), md.yields)
        months = md2.months[0:4]
        comp = md2.composite(PORT)
        out = {}
        for s in ("lump_sum", "oracle_pt_3m"):
            buys, rbd = plan_strategy(s, comp, months, 500.0)
            out[s] = run_window(md2, PORT, months, buys, rbd)
        self.assertGreater(out["oracle_pt_3m"], out["lump_sum"])

    def test_no_lookahead_for_dca_and_lump_sum(self) -> None:
        md = make_market(300)
        months = md.months[0:3]
        comp = md.composite(PORT)
        event_days = {m.mid for m in months} | {m.first for m in months} | {months[-1].last}
        pert = md.closes["SPY"].copy()
        touched = 0
        for i in range(months[0].first, months[-1].last):
            if i not in event_days:
                pert[i] = 123.0
                touched += 1
        md2 = build_market(md.dates, dict(md.closes, SPY=pert), md.yields)
        self.assertGreater(touched, 0)
        for s in ("dca_mid", "lump_sum"):
            buys, rbd = plan_strategy(s, comp, months, 500.0)
            t1 = run_window(md, PORT, months, buys, rbd)
            t2 = run_window(md2, PORT, months, buys, rbd)
            self.assertAlmostEqual(t1, t2, places=6)

    def test_oracle_ignores_non_min_close_changes(self) -> None:
        md = make_market(300)
        comp = md.composite(PORT)
        months = md.months[0:3]
        buys0, _ = plan_strategy("oracle_1m", comp, months, 500.0)
        mins = [d for d, _ in buys0]
        closes = np.where(np.isin(np.arange(len(md.closes["SPY"])), mins), md.closes["SPY"], 500.0)
        md2 = build_market(md.dates, dict(md.closes, SPY=closes), md.yields)
        buys1, _ = plan_strategy("oracle_1m", md2.composite(PORT), md2.months[0:3], 500.0)
        self.assertEqual([d for d, _ in buys0], [d for d, _ in buys1])

    def test_rebalance_costs_money_in_drifting_market(self) -> None:
        dates = business_dates(300)
        n = len(dates)
        d12 = None
        spy = np.full(n, 100.0)
        spy[:n] = 100.0 + np.linspace(0.0, 100.0, n)
        spy[n // 2 :] = 200.0  # spike then flat; rebalance day sits inside
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        months = md.months[0:13]
        d12 = months[12].first
        self.assertEqual(dates[d12][:4], "2006")
        buys, rbd = plan_strategy("lump_sum", md.composite(PORT), months, 500.0)
        self.assertEqual(len(rbd), 1)
        term_with = run_window(md, PORT, months, buys, rbd)
        term_without = run_window(md, PORT, months, buys, [])
        self.assertLess(term_with, term_without)  # rebalancing SPY->EFA at flat 50 costs
        self.assertGreater(term_with, term_without * 0.997)

    def test_golden_butterfly_cash_sleeve_accrues(self) -> None:
        md = make_market(300, spec={"SPY": []})
        gb = {"SPY": 0.4, "EFA": 0.4, CASH: 0.2}
        months = self._window(md, 1)
        buys, rbd = plan_strategy("lump_sum", md.composite(gb), months, 500.0)
        term = run_window(md, gb, months, buys, rbd)
        yf = accrual_factor(md.cumlog, months[-1].last, months[0].first)
        risky = 500.0 * 0.8 / ((1 + SLIP) * (1 + COMM))
        cash = 500.0 * 0.2
        self.assertAlmostEqual(term, risky + cash * yf, places=4)


class WindowTests(unittest.TestCase):
    def test_enumeration_counts(self) -> None:
        md = make_market(300)
        wins12 = enumerate_windows(md, 12)
        self.assertGreaterEqual(len(wins12), 3)
        for _, months in wins12:
            self.assertEqual(len(months), 12)
        for i, (start, months) in enumerate(enumerate_windows(md, 1)):
            self.assertEqual(len(months), 1)

    def test_argmin_takes_earliest_on_tie(self) -> None:
        comp = np.array([3.0, 1.0, 2.0, 1.0])
        self.assertEqual(argmin_day(comp, [0, 1, 2, 3]), 1)


if __name__ == "__main__":
    unittest.main()
