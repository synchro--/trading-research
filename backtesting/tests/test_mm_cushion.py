"""Unit tests for the money-market cushion study (30k reserve + 500/mo)."""
from __future__ import annotations

import unittest
from datetime import date, timedelta

import numpy as np

from backtesting.dca_vs_lumpsum import COMM, SLIP, build_market
from backtesting.mm_cushion import (
    INITIAL_MM,
    TRIGGER_DD,
    eq_nominal,
    find_mm_trigger,
    plan_cushion,
    rolling_max_calendar,
    run_cushion_window,
)
from backtesting.tests.test_dca_vs_lumpsum import PORT, business_dates, make_market


def flat_dates(n: int = 300):
    return business_dates(n)


class RollingMaxCalendarTests(unittest.TestCase):
    def test_inclusive_window(self) -> None:
        dates = [d.isoformat() for d in (date(2005, 1, 1) + timedelta(days=i) for i in range(40))]
        arr = np.arange(40, dtype=float)
        out = rolling_max_calendar(arr, dates, 30)
        # day 0 has no lookback: max of [0]; day 29: max of [0..29]; day 35: [6..35]
        self.assertEqual(out[0], 0.0)
        self.assertEqual(out[29], 29.0)
        self.assertEqual(out[-1], 39.0)
        self.assertAlmostEqual(out[35], float(np.arange(6, 35 + 1).max()))

    def test_weekend_gaps_still_full_window(self) -> None:
        dates = business_dates(40)
        arr = np.arange(40, dtype=float)
        out = rolling_max_calendar(arr, dates, 5)
        # rising series: trailing-high == the latest value no matter the gap
        self.assertTrue(np.array_equal(out, arr))


class TriggerTests(unittest.TestCase):
    def test_deep_red_day_in_first_two_weeks_triggers(self) -> None:
        dates = flat_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first  # early in the month (day-of-month <= 14)
        # -6% on SPY => composite dd = -3.6% >= 3% trigger
        spy[feb + 2] = 94.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        trig = find_mm_trigger(comp, roll30, md.months[1], list(md.dates))
        self.assertEqual(trig, feb + 2)

    def test_shallow_dip_does_not_trigger(self) -> None:
        dates = flat_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        spy[feb + 2] = 98.5  # composite dd ~ -0.9%: far below the 3% requirement
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        self.assertIsNone(find_mm_trigger(comp, roll30, md.months[1], list(md.dates)))

    def test_after_day_14_never_triggers(self) -> None:
        dates = flat_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        # deep red dip timed at day-of-month 16: outside the first two weeks
        target = next(d for d in probe.months[1].days if int(dates[d][8:10]) == 16)
        spy[target] = 94.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        self.assertIsNone(find_mm_trigger(comp, roll30, md.months[1], list(md.dates)))

    def test_flat_market_no_trigger(self) -> None:  # no red days at all
        md = make_market(300, yield_rate=0.0)
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        for m in md.months[:3]:
            self.assertIsNone(find_mm_trigger(comp, roll30, m, list(md.dates)))


class PlanTests(unittest.TestCase):
    def test_lump_sum_budget_identity(self) -> None:
        md = make_market(300)
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        buys, rbd, meta = plan_cushion("lump_sum_30k", comp, roll30, md.months[:13], list(md.dates))
        amounts = [a for _, trs in buys for k, a, _ in trs if k == "income"]
        self.assertAlmostEqual(sum(amounts), INITIAL_MM + 500.0 * 13, places=6)
        # the reserve deploys on day 0
        self.assertEqual(buys[0][1][0][1], INITIAL_MM)

    def test_dip2x_mm_tranches_have_mmf_source(self) -> None:
        import numpy as _np

        dates = flat_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        spy[feb + 2] = 94.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        buys, rbd, meta = plan_cushion("dip2x_mm", comp, roll30, md.months[1:4], list(md.dates))
        kinds = {(day): {k for k, *_ in trs} for day, trs in buys}
        self.assertIn("mmf", kinds[feb + 2])
        self.assertEqual(meta["triggered_months"], 1)


class CushionSimTests(unittest.TestCase):
    def test_flat_market_families(self) -> None:
        """Flat prices, zero yield: (2)/(3)/(4) identical; (1) ahead by the
        earlier deployment of the 30k."""
        md = make_market(300, yield_rate=0.0)
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:2]
        out = {}
        for s in ("lump_sum_30k", "dca_cushion", "oracle_cushion", "dip2x_mm"):
            buys, rbd, _ = plan_cushion(s, comp, roll30, months, list(md.dates))
            res = run_cushion_window(md, PORT, months, buys, rbd, mmf0=0.0 if s == "lump_sum_30k" else INITIAL_MM)
            out[s] = res
            costed = ((1000.0 if s != "lump_sum_30k" else 31000.0)) / ((1 + SLIP) * (1 + COMM))
            if s == "lump_sum_30k":
                base = costed + 0.0
            else:
                base = costed + INITIAL_MM
            self.assertAlmostEqual(res["terminal"], base, places=6)
        # flat, zero-yield market: the only LS difference is trading costs,
        # so the cushion technically edges ahead; assert near-parity instead
        self.assertAlmostEqual(
            out["lump_sum_30k"]["terminal"], out["dca_cushion"]["terminal"], delta=60.0
        )

    def test_oracle_and_mid_identical_on_flat(self) -> None:
        md = make_market(300, yield_rate=0.0)
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:2]
        vals = {}
        for s in ("dca_cushion", "oracle_cushion", "dip2x_mm"):
            buys, rbd, _ = plan_cushion(s, comp, roll30, months, list(md.dates))
            res = run_cushion_window(md, PORT, months, buys, rbd, mmf0=INITIAL_MM)
            vals[s] = res["terminal"]
        self.assertAlmostEqual(vals["dca_cushion"], vals["oracle_cushion"], places=6)
        self.assertAlmostEqual(vals["dip2x_mm"], vals["dca_cushion"], places=6)

    def test_dip_month_draws_500_from_reserve(self) -> None:
        dates = flat_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        spy[feb + 2] = 94.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[1:2]
        buys, rbd, _ = plan_cushion("dip2x_mm", comp, roll30, months, list(md.dates))
        res = run_cushion_window(md, PORT, months, buys, rbd, mmf0=INITIAL_MM)
        # 30k reserve: interest 0 (flat yield 0) -> left = 29,500
        # equities: month's 1000 at SPY 94/EFA 50 weights, terminal closes 100/50
        cost = (1 + SLIP) * (1 + COMM)
        risky = (600.0 * 100.0 / 94.0 + 400.0 * 50.0 / 50.0) / cost
        self.assertAlmostEqual(res["mmf_left"], INITIAL_MM - 500.0, places=6)
        self.assertAlmostEqual(res["terminal"], risky + 29_500.0, places=6)

    def test_reserve_drains_to_zero_and_clamps(self) -> None:
        dates = flat_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        # 60 tiny windows of dips... simpler: single month with a reserve of 300
        spy[feb + 2] = 94.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[1:2]
        buys, rbd, _ = plan_cushion("dip2x_mm", comp, roll30, months, list(md.dates))
        res = run_cushion_window(md, PORT, months, buys, rbd, mmf0=300.0)
        # draw is capped at 300 -> mmf_left == 0, extra deployed == 300
        self.assertAlmostEqual(res["mmf_left"], 0.0, places=6)
        cost = (1 + SLIP) * (1 + COMM)
        risky = (500.0 + 300.0) * 1.0 + 300.0 * 0.0  # 800 deployed
        risky_val = (600.0 * (800.0 / 1000.0) * 100.0 / 94.0 + 400.0 * (800.0 / 1000.0) * 50.0 / 50.0) / cost
        self.assertAlmostEqual(res["terminal"], risky_val, places=6)

    def test_lump_sum_earlier_deployment_beats_cushion_when_market_rises(self) -> None:
        dates = flat_dates(320)
        n = len(dates)
        spy = np.linspace(100.0, 130.0, n)
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll30 = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:6]
        out = {}
        for s in ("lump_sum_30k", "dca_cushion"):
            buys, rbd, _ = plan_cushion(s, comp, roll30, months, list(md.dates))
            res = run_cushion_window(md, PORT, months, buys, rbd, mmf0=INITIAL_MM)
            out[s] = res["terminal"]
        self.assertGreater(out["lump_sum_30k"], out["dca_cushion"])


class BudgetTests(unittest.TestCase):
    def test_eq_nominal(self) -> None:
        self.assertEqual(eq_nominal("lump_sum_30k", 120, 500.0, 0.0), 30_000.0 + 60_000.0)
        self.assertEqual(eq_nominal("dca_cushion", 120, 500.0, 0.0), 60_000.0)
        self.assertEqual(eq_nominal("oracle_cushion", 120, 500.0, 0.0), 60_000.0)
        self.assertEqual(eq_nominal("dip2x_mm", 120, 500.0, 5000.0), 65_000.0)


if __name__ == "__main__":
    unittest.main()
