"""Unit tests for the cash-is-king crash deployment study."""
from __future__ import annotations

import unittest

import numpy as np

from backtesting.crash_deploy import LOOKBACK_CAL_DAYS, find_dd_day, plan_crash
from backtesting.dca_vs_lumpsum import build_market
from backtesting.mm_cushion import rolling_max_calendar, run_cushion_window
from backtesting.tests.test_dca_vs_lumpsum import PORT, business_dates


def crash_market(spy: np.ndarray, n: int):
    dates = business_dates(n)
    md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
    return md, md.composite(PORT), rolling_max_calendar(md.composite(PORT), list(md.dates), LOOKBACK_CAL_DAYS)


class TriggerTests(unittest.TestCase):
    def test_find_dd_day(self) -> None:
        n = 320
        spy = np.full(n, 100.0)
        spy[150:] = 60.0  # SPY -40% => composite -24% (EFA cushions)
        md, comp, roll = crash_market(spy, n)
        day20 = find_dd_day(comp, roll, md.months, 0.20)
        day30 = find_dd_day(comp, roll, md.months, 0.30)
        self.assertIsNotNone(day20)
        self.assertLessEqual(comp[day20], 0.80 * roll[day20])  # trigger day meets the threshold
        self.assertIsNone(day30)  # only -24% composite happened

    def test_no_trigger_in_rising_market(self) -> None:
        n = 320
        spy = np.linspace(100.0, 150.0, n)
        md, comp, roll = crash_market(spy, n)
        self.assertIsNone(find_dd_day(comp, roll, md.months, 0.20))


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        n = 320
        self.spy = np.full(n, 100.0)
        self.spy[150:] = 60.0  # SPY -40% => composite dd 24%
        self.md, self.comp, self.roll = crash_market(self.spy, n)
        self.months = self.md.months[:15]
        self.budget = 500.0 * 15

    def test_ls_deploys_day0(self) -> None:
        buys, rbd, meta = plan_crash("ls", self.comp, self.roll, self.months, self.budget)
        self.assertEqual(buys[0][0], self.months[0].first)
        self.assertEqual(meta["months_to_trigger"], 0)

    def test_wait20_lump_deploys_at_trigger(self) -> None:
        buys, rbd, meta = plan_crash("wait20_lump", self.comp, self.roll, self.months, self.budget)
        self.assertTrue(meta["triggered"])
        day = find_dd_day(self.comp, self.roll, self.months, 0.20)
        self.assertEqual(buys[0][0], day)
        self.assertEqual(buys[0][1][0][1], self.budget)

    def test_wait30_never_triggers_on_24pct(self) -> None:
        buys, rbd, meta = plan_crash("wait30_lump", self.comp, self.roll, self.months, self.budget)
        self.assertFalse(meta["triggered"])
        self.assertEqual(buys, [])

    def test_dca12_equal_tranches_fit_window(self) -> None:
        buys, rbd, meta = plan_crash("wait20_dca12", self.comp, self.roll, self.months, self.budget)
        amounts = [a for _, trs in buys for _k, a, _d in trs]
        day = find_dd_day(self.comp, self.roll, self.months, 0.20)
        k = next(i for i, m in enumerate(self.months) if day <= m.last)
        legs = min(12, len(self.months) - k)
        self.assertEqual(len(amounts), legs)
        self.assertAlmostEqual(sum(amounts), self.budget, places=6)
        self.assertTrue(all(abs(a - self.budget / legs) < 1e-9 for a in amounts))

    def test_tranche_plan_sums_to_thirds_present(self) -> None:
        buys, rbd, meta = plan_crash("wait20_tranches", self.comp, self.roll, self.months, self.budget)
        amounts = [a for _, trs in buys for _k, a, _d in trs]
        # this market dips only -28%: the 10% and 20% thirds fire, the 30% does not
        self.assertEqual(len(amounts), 2)
        self.assertAlmostEqual(amounts[0], self.budget / 3, places=6)

    def test_parked_never_buys(self) -> None:
        buys, rbd, meta = plan_crash("parked", self.comp, self.roll, self.months, self.budget)
        self.assertEqual(buys, [])
        self.assertFalse(meta["triggered"])


class SimTests(unittest.TestCase):
    def test_crash_deployment_beats_ls_when_market_falls_then_flat(self) -> None:
        """Prices 100 -> 60 (crash) -> 70 (partial recovery): LS buys at 100,
        wait20 deploys at ~80 and recovers to 70 -> wait20 wins."""
        n = 320
        spy = np.full(n, 100.0)
        spy[120:190] = 60.0  # crash phase
        spy[190:] = 70.0
        md, comp, roll = crash_market(spy, n)
        months = md.months[:15]
        budget = 500.0 * 15
        out = {}
        for s in ("ls", "wait20_lump"):
            buys, rbd, _ = plan_crash(s, comp, roll, months, budget)
            res = run_cushion_window(
                md, PORT, months, buys, rbd, mmf0=0.0 if s == "ls" else budget
            )
            out[s] = res["terminal"]
        self.assertGreater(out["wait20_lump"], out["ls"])

    def test_parked_all_cash_when_never_deployed(self) -> None:
        n = 320
        spy = np.full(n, 100.0)
        md, comp, roll = crash_market(spy, n)
        months = md.months[:15]
        budget = 500.0 * 15
        for s in ("wait20_lump", "parked"):
            buys, rbd, _ = plan_crash(s, comp, roll, months, budget)
            res = run_cushion_window(md, PORT, months, buys, rbd, mmf0=budget)
            self.assertAlmostEqual(res["mmf_left"], budget, places=6)
            self.assertAlmostEqual(res["terminal"], budget, places=6)

    def test_never_triggered_cash_beats_ls_in_a_crash(self) -> None:
        """If the market crashes -24% and stays down, the 30% rule never fires:
        staying in cash still beats LS deployed at the top."""
        n = 320
        spy = np.full(n, 100.0)
        spy[100:] = 60.0  # -40%, no recovery
        md, comp, roll = crash_market(spy, n)
        months = md.months[:15]
        budget = 500.0 * 15
        buys_pred, rbd, meta = plan_crash("wait30_lump", comp, roll, months, budget)
        self.assertFalse(meta["triggered"])  # composite only -24% < 30%
        buys_ls, rbd_ls, _ = plan_crash("ls", comp, roll, months, budget)
        t_wait = run_cushion_window(md, PORT, months, buys_pred, rbd, mmf0=budget)["terminal"]
        t_ls = run_cushion_window(md, PORT, months, buys_ls, rbd_ls, mmf0=0.0)["terminal"]
        self.assertGreater(t_wait, t_ls)


if __name__ == "__main__":
    unittest.main()
