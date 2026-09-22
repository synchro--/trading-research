"""Unit tests for the hybrid LS/DCA split study."""
from __future__ import annotations

import unittest

import numpy as np

from backtesting.dca_vs_lumpsum import build_market, plan_strategy, run_window
from backtesting.hybrid_split import (
    DIP_VARIANT,
    SPLITS,
    STRATEGIES,
    TAILS,
    plan_hybrid,
    strategy_grid,
    value_at,
)
from backtesting.mm_cushion import rolling_max_calendar
from backtesting.tests.test_dca_vs_lumpsum import PORT, business_dates, make_market


class GridTests(unittest.TestCase):
    def test_grid_names_unique_and_complete(self) -> None:
        grid = strategy_grid()
        names = [n for n, _, _ in grid]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("ls", names)
        self.assertIn("dca_full", names)
        self.assertIn(DIP_VARIANT, names)
        for a in SPLITS:
            for m in TAILS:
                self.assertTrue(any(n.startswith(f"hyb{int(a*100)}_m") and t == m for n, _, t in grid))


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.md = make_market(400, yield_rate=0.0)
        self.comp = self.md.composite(PORT)
        self.roll30 = rolling_max_calendar(self.comp, list(self.md.dates), 30)
        self.months = self.md.months[:24]
        self.budget = 500.0 * len(self.months)

    def test_budget_identity_all_combos(self) -> None:
        for name, alpha, tail in strategy_grid():
            buys, rbd = plan_hybrid(
                alpha, tail, self.budget, self.months, self.comp, self.roll30, list(self.md.dates),
                dip=name == DIP_VARIANT,
            )
            deployed = sum(a for _, trs in buys for a, _ in trs)
            self.assertAlmostEqual(deployed, self.budget, places=6, msg=name)

    def test_ls_matches_parent_lump_sum(self) -> None:
        buys, rbd = plan_hybrid(1.0, 0, self.budget, self.months, self.comp, self.roll30, list(self.md.dates))
        parent_buys, parent_rbd = plan_strategy("lump_sum", self.comp, self.months, 500.0)
        t1 = run_window(self.md, PORT, self.months, buys, rbd)
        t2 = run_window(self.md, PORT, self.months, parent_buys, parent_rbd)
        self.assertAlmostEqual(t1, t2, places=6)

    def test_tail_lengths(self) -> None:
        for tail, expected in ((12, 12), (24, 24), (None, 24)):
            buys, _ = plan_hybrid(0.5, tail, self.budget, self.months, self.comp, self.roll30, list(self.md.dates))
            tail_buys = [b for b in buys if b[0] != self.months[0].first]
            self.assertEqual(len(tail_buys), min(expected, len(self.months) - 0))
            for day, trs in tail_buys:
                self.assertEqual(trs[0][1], self.months[0].first)  # anchored at t0

    def test_alpha_one_has_no_tail(self) -> None:
        buys, _ = plan_hybrid(1.0, None, self.budget, self.months, self.comp, self.roll30, list(self.md.dates))
        self.assertEqual(len(buys), 1)

    def test_anchor_is_window_start_for_tail(self) -> None:
        buys, _ = plan_hybrid(0.5, 24, self.budget, self.months, self.comp, self.roll30, list(self.md.dates))
        for _, trs in buys:
            for _, anchor in trs:
                self.assertEqual(anchor, self.months[0].first)

    def test_flat_market_hybrid_equals_budget_minus_costs(self) -> None:
        md = make_market(400, yield_rate=0.0)
        comp = md.composite(PORT)
        roll = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:24]
        budget = 500.0 * len(months)
        for alpha in (0.0, 0.5, 1.0):
            buys, rbd = plan_hybrid(alpha, None, budget, months, comp, roll, list(md.dates))
            term = run_window(md, PORT, months, buys, rbd)
            cost = (1 + 0.0005) * (1 + 0.001)
            self.assertAlmostEqual(term, budget / cost, places=6)


class ValueAtTests(unittest.TestCase):
    def test_flat_market_value_at_equals_budget(self) -> None:
        md = make_market(400, yield_rate=0.0)
        comp = md.composite(PORT)
        roll = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:24]
        budget = 500.0 * len(months)
        for alpha, tail in ((1.0, 0), (0.5, 12), (0.5, None), (0.0, None)):
            buys, _ = plan_hybrid(alpha, tail, budget, months, comp, roll, list(md.dates))
            v = value_at(md, PORT, buys, months[11].last)
            self.assertAlmostEqual(v, budget, delta=budget * 0.002)

    def test_value_at_includes_waiting_cash(self) -> None:
        md = make_market(400, yield_rate=0.03)
        comp = md.composite(PORT)
        roll = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:24]
        buys, _ = plan_hybrid(0.0, None, 500.0 * 24, months, comp, roll, list(md.dates))
        v = value_at(md, PORT, buys, months[11].last)
        # halfway through the tail: flat prices -> same as budget plus accrued interest on the waiting part
        self.assertGreaterEqual(v, 500.0 * 24 - 500.0)

    def test_dip_variant_doubles_at_least_one_month(self) -> None:
        dates = business_dates(400)
        n = len(dates)
        spy = np.full(n, 100.0)
        probe = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        feb = probe.months[1].first
        spy[feb + 2] = 94.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll = rolling_max_calendar(comp, list(md.dates), 30)
        months = md.months[:12]
        budget = 500.0 * 12
        base, _ = plan_hybrid(0.5, None, budget, months, comp, roll, list(md.dates))
        dip, _ = plan_hybrid(0.5, None, budget, months, comp, roll, list(md.dates), dip=True)
        self.assertGreater(sum(a for _, trs in dip for a, _ in trs), 0)
        self.assertAlmostEqual(sum(a for _, trs in dip for a, _ in trs), budget, places=6)
        # dip variant must deploy a doubled amount somewhere, or earlier than base
        base_amounts = sorted(a for _, trs in base for a, _ in trs)
        dip_amounts = sorted(a for _, trs in dip for a, _ in trs)
        self.assertNotEqual(base_amounts, dip_amounts)


if __name__ == "__main__":
    unittest.main()
