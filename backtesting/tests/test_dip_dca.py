"""Unit tests for the DCA timing study II (dip-triggered contributions)."""
from __future__ import annotations

import unittest

import numpy as np

from backtesting.dca_vs_lumpsum import COMM, SLIP, build_market
from backtesting.dip_dca import STRATEGIES, find_trigger_day, plan_dip, run_window
from backtesting.tests.test_dca_vs_lumpsum import PORT, business_dates, make_market


def md_with_month_path(path: list[float], prev_close: float = 100.0):
    """Synthetic market: month 0 flat at prev_close, month 1 closes = *path*.

    Returns (md, comp, month_2, first_day_index_of_month_2)."""
    dates = business_dates(70)
    n = len(dates)
    closes = np.full(n, prev_close)
    probe = build_market(dates, {"SPY": closes, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
    start = probe.months[1].first
    for k, v in enumerate(path):
        closes[start + k] = v
    md = build_market(dates, {"SPY": closes, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
    return md, md.composite(PORT), md.months[1], start


class DipTriggerTests(unittest.TestCase):
    def test_falling_month_triggers_first_day(self) -> None:
        # every day a new low, red vs prior close -> the FIRST day fires
        _, comp, feb, start = md_with_month_path([99.0, 98.0, 97.0] + [97.0] * 21)
        self.assertEqual(find_trigger_day(comp, feb), start)

    def test_first_trigger_not_overridden_by_deeper_low(self) -> None:
        # day1 flat (green, no), day2 dips (trigger), day3 dips deeper: rule stops at day2
        _, comp, feb, start = md_with_month_path([100.0, 98.0, 95.0] + [95.0] * 21)
        self.assertEqual(find_trigger_day(comp, feb), start + 1)

    def test_rising_month_never_triggers(self) -> None:
        _, comp, feb, _ = md_with_month_path([101.0, 102.0, 103.0] + [103.0] * 21)
        self.assertIsNone(find_trigger_day(comp, feb))

    def test_flat_month_never_triggers(self) -> None:
        _, comp, feb, _ = md_with_month_path([100.0] * 23)
        self.assertIsNone(find_trigger_day(comp, feb))


class DipPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.md = make_market(300)
        self.comp = self.md.composite(PORT)
        self.months = self.md.months[:12]

    def test_dip_shift_keeps_invested_identity(self) -> None:
        buys, rbd, invested, meta = plan_dip("dip_shift", self.comp, self.months, 500.0)
        self.assertAlmostEqual(float(invested.sum()), 500.0 * 12, places=6)
        for (day, tranches), m in zip(buys, self.months):
            trig = find_trigger_day(self.comp, m)
            self.assertEqual(day, trig if trig is not None else m.mid)
            self.assertEqual(tranches[0][0], 500.0)

    def test_dip_double_v1_doubles_only_triggered_months(self) -> None:
        buys, rbd, invested, meta = plan_dip("dip_double_v1", self.comp, self.months, 500.0)
        self.assertEqual(len(buys), 12)
        self.assertEqual(float(invested.sum()), 500.0 * (12 + meta["triggered_months"]))

    def test_all_family_strategies_plan(self) -> None:
        from backtesting.dip_dca import DIP_CONFIG, ROLL_WINDOW, plan, rolling_max

        wins_needed = {int(cfg["win"]) for cfg in DIP_CONFIG.values() if "win" in cfg}
        rolls = {w: rolling_max(self.comp, w) for w in wins_needed}
        for s in STRATEGIES:
            buys, rbd, invested, _ = plan(s, self.comp, self.months, 500.0, rolls)
            self.assertTrue(buys)
            self.assertGreater(float(invested.sum()), 0)

    def test_dip2x_neutral_keeps_budget_neutral(self) -> None:
        from backtesting.dip_dca import ROLL_WINDOW, plan_dip, rolling_max

        roll = rolling_max(self.comp, ROLL_WINDOW)
        # trailing haircut beyond the window end can only make total <= 500xN
        buys, rbd, invested, _ = plan_dip("dip2x_neutral", self.comp, self.months, 500.0, roll)
        self.assertLessEqual(float(invested.sum()), 500.0 * 12 + 1e-6)

    def test_dip2x_half_2x_then_half(self) -> None:
        """Every 1000 deployment is followed by a 250 month or another trigger."""
        from backtesting.dip_dca import ROLL_WINDOW, plan_dip, rolling_max

        roll = rolling_max(self.comp, ROLL_WINDOW)
        buys, rbd, invested, _ = plan_dip("dip2x_half", self.comp, self.months, 500.0, roll)
        deploys = [amt for _, trs in buys for amt, _ in trs]
        self.assertGreater(len(deploys), 0)
        for i, amt in enumerate(deploys):
            if amt == 1000.0 and i + 1 < len(deploys) and deploys[i + 1] != 1000.0:
                self.assertEqual(deploys[i + 1], 250.0)

    def test_plan_rejects_lump_sum(self) -> None:
        from backtesting.dip_dca import plan

        with self.assertRaises(ValueError):
            plan("lump_sum", self.comp, self.months, 500.0)


class DipSimTests(unittest.TestCase):
    def test_flat_market_all_three_equal(self) -> None:
        from backtesting.dip_dca import DIP_CONFIG, ROLL_WINDOW, plan, rolling_max

        md = make_market(300, yield_rate=0.0)  # flat prices: no red days ever
        comp = md.composite(PORT)
        wins_needed = {int(cfg["win"]) for cfg in DIP_CONFIG.values() if "win" in cfg}
        rolls = {w: rolling_max(comp, w) for w in wins_needed}
        months = md.months[:2]
        for s in ("dca_mid", "dip_shift", "dip_double_v1", "dip2x_half", "dip2x_neutral", "dip6m_deep"):
            buys, rbd, cap, _ = plan(s, comp, months, 500.0, rolls)
            term = run_window(md, PORT, months, buys, rbd)
            self.assertAlmostEqual(term, 1000.0 / ((1 + SLIP) * (1 + COMM)), places=6)

    def test_deep_trigger_gated_by_20d_dip(self) -> None:
        from backtesting.dip_dca import DIP_DD, ROLL_WINDOW, find_trigger_day, rolling_max

        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        # shallow new low (-1.5%): red running low but NOT below 0.97 x 20d high
        for k, v in enumerate([99.0, 98.5] + [98.5] * 10):
            spy[feb + k] = v
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll = rolling_max(comp, ROLL_WINDOW)
        self.assertIsNone(find_trigger_day(comp, md.months[1], roll))
        # deep new low: composite must clear the 3% threshold (EFA sleeve
        # cushions the SPY drop, so SPY -6% -> composite -2.4% is NOT enough)
        spy2 = np.full(n, 100.0)
        for k, v in enumerate([99.0, 93.5] + [93.5] * 10):
            spy2[feb + k] = v
        md2 = build_market(dates, {"SPY": spy2, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp2 = md2.composite(PORT)
        roll2 = rolling_max(comp2, ROLL_WINDOW)
        self.assertEqual(find_trigger_day(comp2, md2.months[1], roll2), feb + 1)

    def test_dip2x_half_chain_on_consecutive_triggers(self) -> None:
        from backtesting.dip_dca import ROLL_WINDOW, plan_dip, rolling_max

        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        m2 = probe.months[1].first
        m3 = probe.months[2].first
        spy[m2] = 96.0       # month 2 opens -4% and keeps sliding: triggered
        spy[m2 + 1] = 95.0
        spy[m3] = 94.0       # month 3 also opens below (red, new low, deep)
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll = rolling_max(comp, ROLL_WINDOW)
        buys, rbd, invested, _ = plan_dip("dip2x_half", comp, md.months[1:4], 500.0, roll)
        # months 2,3 triggered: 1000 + 1000, month 4 absorbs 250
        self.assertEqual([a for _, trs in buys for a, _ in trs], [1000.0, 1000.0, 250.0])

    def test_consec2_requires_two_qualifying_days(self) -> None:
        from backtesting.dip_dca import DIP_DD, ROLL_WINDOW, find_trigger_day, rolling_max

        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        # single qualifying day (day 2 deep red low), day 3 recovers: streak reset
        for k, v in enumerate([99.0, 93.5, 94.5, 95.0]):
            spy[feb + k] = v
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll = rolling_max(comp, ROLL_WINDOW)
        self.assertIsNone(find_trigger_day(comp, md.months[1], roll, DIP_DD, min_consec=2))
        # two qualifying days in a row: fires on the 2nd
        spy2 = np.full(n, 100.0)
        for k, v in enumerate([99.0, 93.5, 93.0, 93.2]):
            spy2[feb + k] = v
        md2 = build_market(dates, {"SPY": spy2, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp2 = md2.composite(PORT)
        roll2 = rolling_max(comp2, ROLL_WINDOW)
        self.assertEqual(
            find_trigger_day(comp2, md2.months[1], roll2, DIP_DD, min_consec=2), feb + 2
        )

    def test_5pct15d_variant_gates_on_level_and_window(self) -> None:
        from backtesting.dip_dca import find_trigger_day, rolling_max

        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        # composite dd ~ -3% (spy -6%): fails the 5% threshold
        for k, v in enumerate([99.0, 94.0] + [94.0] * 8):
            spy[feb + k] = v
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll15 = rolling_max(comp, 15)
        self.assertIsNone(find_trigger_day(comp, md.months[1], roll15, 0.05))
        # deeper: spy -9% -> composite -5.4%: passes
        spy2 = np.full(n, 100.0)
        for k, v in enumerate([99.0, 91.0] + [91.0] * 8):
            spy2[feb + k] = v
        md2 = build_market(dates, {"SPY": spy2, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp2 = md2.composite(PORT)
        roll15b = rolling_max(comp2, 15)
        self.assertEqual(find_trigger_day(comp2, md2.months[1], roll15b, 0.05), feb + 1)

    def test_cycle6m_fallback_and_leftovers(self) -> None:
        from backtesting.dip_dca import ROLL_WINDOW, plan, rolling_max

        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        # cycle months 1..6 (window has ~13 months): dip mid month 3, expiry elsewhere
        cls = probe.months
        first3 = cls[1].first
        spy[first3 + 1] = 93.5   # deep red running low inside the cycle: fires
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        rolls = {ROLL_WINDOW: rolling_max(comp, ROLL_WINDOW)}
        # run over the first 6 full months (cycle 1 = months 0..5 starting at data start)
        buys, rbd, invested, _ = plan("dip6m_deep", comp, md.months[0:6], 500.0, rolls)
        # budget-neutral
        self.assertAlmostEqual(float(invested.sum()), 3000.0, places=6)
        # first buy event = the firing day, deploying the 2 contributions so far
        fired = [b for b in buys if b[1][0][0] == 2 * 500.0 or len(b[1]) == 2]
        self.assertTrue(fired)
        self.assertIn(pad := buys[0][0], [first3 + 1])
        # leftover later contributions deploy within the last cycle month
        days_from_unfired = [d for d, trs in buys if len(trs) == 4]
        self.assertEqual(days_from_unfired, [probe.months[5].mid])

    def test_dip_double_fires_on_month_open_gap_down(self) -> None:
        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        spy[feb] = 98.0  # month opens below prior month => red running low on day 1
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        months = md.months[1:2]
        buys, rbd, invested, meta = plan_dip("dip_double_v1", comp, months, 500.0)
        self.assertEqual(meta["triggered_months"], 1)
        self.assertEqual(buys[0][0], feb)
        self.assertEqual(buys[0][1][0][0], 1000.0)
        term = run_window(md, PORT, months, buys, rbd)
        cost = (1 + SLIP) * (1 + COMM)
        spy_end = float(md.closes["SPY"][months[-1].last])  # 100: month recovers
        expected = (600.0 * spy_end / 98.0 + 400.0 * 1.0 * 50.0 / 50.0) / cost
        self.assertAlmostEqual(term, expected, places=6)

    def test_dip_shift_intra_month_dip_at_trigger_price(self) -> None:
        dates = business_dates(320)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        for k, v in enumerate([101.0, 98.0, 96.0, 97.0]):
            spy[feb + k] = v
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        months = md.months[1:2]
        buys, rbd, invested, meta = plan_dip("dip_shift", comp, months, 500.0)
        self.assertEqual(meta["triggered_months"], 1)
        # trigger on the 2nd trading day (98 < 101 red); NOT on the deeper 3rd day
        self.assertEqual(buys[0][0], feb + 1)
        term = run_window(md, PORT, months, buys, rbd)
        cost = (1 + SLIP) * (1 + COMM)
        spy_end = float(md.closes["SPY"][months[-1].last])  # 100: post-dip recovery
        expected = (300.0 * spy_end / 98.0 + 200.0 * 50.0 / 50.0) / cost
        self.assertAlmostEqual(term, expected, places=6)


if __name__ == "__main__":
    unittest.main()
