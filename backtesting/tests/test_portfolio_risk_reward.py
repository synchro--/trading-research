"""Unit tests for the portfolio risk-reward review (synthetic bars)."""
from __future__ import annotations

import unittest

import numpy as np

from backtesting.dca_vs_lumpsum import CASH, build_market
from backtesting.dip_dca import rolling_max
from backtesting.portfolio_risk_reward import (
    ACTUAL_PROXY,
    PAC_STRATEGIES,
    build_return_matrix,
    crisis_metrics,
    harmonic_sharpe_sortino,
    plan_any,
    plan_smart_pac,
    portfolio_returns_deep,
    risk_metrics,
    scenario_overlay,
    scenario_return,
    split_metrics,
)
from backtesting.tests.test_dca_vs_lumpsum import business_dates, make_market

PORT = {"SPY": 0.6, "EFA": 0.4}


class RiskMetricTests(unittest.TestCase):
    def test_flat_series_zero_vol_positive_tiny_cagr(self) -> None:
        rets = np.zeros(500)
        m = risk_metrics(rets, "2005-01-03", "2006-12-29")
        self.assertEqual(m["sharpe"], 0.0)
        self.assertAlmostEqual(m["ann_vol"], 0.0, places=12)
        self.assertAlmostEqual(m["max_dd"], 0.0, places=12)
        self.assertAlmostEqual(m["cagr"], 0.0, places=12)

    def test_constant_positive_sharpe_and_sortino(self) -> None:
        rng = np.random.default_rng(0)
        rets = 0.0005 + rng.normal(0, 0.001, 2000)
        m = risk_metrics(rets, "2005-01-03", "2012-12-31")
        self.assertGreater(m["sharpe"], 0)
        self.assertGreater(m["sortino"], m["sharpe"] - 1e-9)  # few negative days asymmetric
        self.assertGreater(m["cagr"], 0)

    def test_known_drawdown(self) -> None:
        rets = np.array([0.10, -0.50, 0.10])
        m = risk_metrics(rets, "2005-01-03", "2005-01-06")
        # equity: 1.1, 0.55, 0.605 -> maxDD = 0.5
        self.assertAlmostEqual(m["max_dd"], 0.5, places=9)

    def test_harmonic_bounds(self) -> None:
        self.assertEqual(harmonic_sharpe_sortino(0.0, 2.0), 0.0)
        self.assertAlmostEqual(harmonic_sharpe_sortino(1.0, 1.0), 1.0)
        # clip at 3
        self.assertAlmostEqual(harmonic_sharpe_sortino(10.0, 10.0), 3.0)

    def test_split_short_series_falls_back_to_full(self) -> None:
        rets = np.full(50, 0.001)
        m = split_metrics(rets, business_dates(51))
        self.assertEqual(m["train"], m["full"])
        self.assertIn("note", m)


class ReturnMatrixTests(unittest.TestCase):
    def test_matrix_shape_and_cash_column(self) -> None:
        md = make_market(300, yield_rate=0.04)
        rets, dates, assets = build_return_matrix(md, ["SPY", "EFA"])
        self.assertEqual(rets.shape, (299, 3))
        self.assertEqual(len(dates), 299)
        self.assertEqual(assets, ["SPY", "EFA", CASH])
        # flat market at 4% cash yield: risk cols 0, cash col ~0.04/360 per calendar day
        self.assertTrue(np.allclose(rets[:, 0], 0.0))
        self.assertTrue((rets[:, 2] > 0).all())

    def test_portfolio_returns_blends_cash(self) -> None:
        md = make_market(300, yield_rate=0.0)
        w = {"SPY": 0.5, "EFA": 0.3, CASH: 0.2}
        r = portfolio_returns_deep(md, w)
        self.assertEqual(len(r), 299)
        self.assertTrue(np.allclose(r, 0.0))  # flat prices, zero yield

    def test_weights_must_sum_to_one(self) -> None:
        md = make_market(120)
        with self.assertRaises(ValueError):
            portfolio_returns_deep(md, {"SPY": 0.5, "EFA": 0.2})


class OptimizerHelpersOnRealPath(unittest.TestCase):
    """plan_any budget identities (no full optimizer — that needs real data)."""

    def setUp(self) -> None:
        self.md = make_market(400)
        self.comp = self.md.composite(PORT)
        self.roll = rolling_max(self.comp, 20)
        self.months = self.md.months[:12]

    def test_budget_identity_lump_and_dca(self) -> None:
        for s in ("lump_sum", "dca_mid"):
            buys, _, inv, _ = plan_any(s, self.comp, self.months, 500.0, self.roll)
            self.assertAlmostEqual(float(inv.sum()), 6000.0, places=6)
            raw = sum(a for _, tr in buys for a, _ in tr)
            self.assertAlmostEqual(raw, 6000.0, places=6)

    def test_budget_identity_smart_pac_on_triggering_market(self) -> None:
        # declining path so deep dips actually fire
        dates = business_dates(400, start="2007-01-02")
        n = len(dates)
        spy = np.full(n, 100.0)
        md0 = build_market(dates, {"SPY": spy.copy(), "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        for mi, depth in [(2, 0.08), (3, 0.10), (5, 0.07)]:
            for k, d in enumerate(md0.months[mi].days):
                spy[d] = 100.0 * (1.0 - depth - 0.005 * k)
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        comp = md.composite(PORT)
        roll = rolling_max(comp, 20)
        months = md.months[:12]
        buys, rbd, inv, meta = plan_smart_pac(comp, months, 500.0, roll)
        self.assertAlmostEqual(float(inv.sum()), 6000.0, places=6)
        self.assertGreaterEqual(meta["triggered_months"], 2)
        # trigger months deploy 2x, payback months deploy 0
        by_day = {d: tr[0][0] for d, tr in buys}
        amounts = sorted(by_day.values())
        self.assertIn(1000.0, amounts)

    def test_budget_identity_dip2x_neutral(self) -> None:
        buys, _, inv, _ = plan_any("dip2x_neutral", self.comp, self.months, 500.0, self.roll)
        self.assertAlmostEqual(float(inv.sum()), 500.0 * len(self.months), places=6)

    def test_dip2x_half_budget_matches_plan_dip(self) -> None:
        from backtesting.dip_dca import plan_dip

        ref_buys, _, ref_inv, _ = plan_dip("dip2x_half", self.comp, self.months, 500.0, self.roll)
        buys, _, inv, _ = plan_any("dip2x_half", self.comp, self.months, 500.0, self.roll)
        self.assertAlmostEqual(float(inv.sum()), float(ref_inv.sum()), places=9)
        self.assertEqual([d for d, _ in buys], [d for d, _ in ref_buys])

    def test_all_strategies_sorted_days_within_window(self) -> None:
        for s in PAC_STRATEGIES:
            buys, rbd, _, _ = plan_any(s, self.comp, self.months, 500.0, self.roll)
            days = [d for d, _ in buys]
            self.assertEqual(days, sorted(days), s)
            self.assertTrue(all(d <= self.months[-1].last for d in days), s)


class ScenarioTests(unittest.TestCase):
    def test_overlay_renormalises(self) -> None:
        w = {"A": 0.5, "B": 0.5}
        nw = scenario_overlay(w, {"A": -0.4, "B": 0.0})
        self.assertAlmostEqual(sum(nw.values()), 1.0, places=12)
        # A shrinks in relative share
        self.assertLess(nw["A"], w["A"])

    def test_scenario_return_is_weight_dot_shock(self) -> None:
        w = {"A": 0.6, "B": 0.4}
        r = scenario_return(w, {"A": -0.5, "B": 0.1})
        self.assertAlmostEqual(r, 0.6 * -0.5 + 0.4 * 0.1, places=12)

    def test_identity_shock_keeps_weights(self) -> None:
        w = dict(ACTUAL_PROXY)
        nw = scenario_overlay(w, {})
        for s in w:
            self.assertAlmostEqual(nw[s], w[s], places=12)


class CrisisTests(unittest.TestCase):
    def test_crisis_window_return_on_synthetic_crash(self) -> None:
        dates = business_dates(800, start="2007-01-01")
        n = len(dates)
        spy = np.full(n, 100.0)
        for i, d in enumerate(dates):
            if d >= "2008-11-03":  # mid gfc_crash window
                spy[i] = 50.0
        md = build_market(dates, {"SPY": spy, "EFA": np.full(n, 50.0)}, {t: 0.0 for t in dates})
        rows = crisis_metrics(md, {"all_spy": {"SPY": 1.0}})
        gfc = next(r for r in rows if r["window"] == "gfc_crash")
        self.assertLess(gfc["return"], -0.3)
        worst = next(r for r in rows if r["window"] == "worst_6m_rolling")
        self.assertLess(worst["return"], -0.4)


class ActualProxyTests(unittest.TestCase):
    def test_proxy_weights_sum_to_one(self) -> None:
        self.assertAlmostEqual(sum(ACTUAL_PROXY.values()), 1.0, places=9)

    def test_pac_strategies_have_smart_pac(self) -> None:
        self.assertIn("smart_pac", PAC_STRATEGIES)
        self.assertIn("lump_sum", PAC_STRATEGIES)


if __name__ == "__main__":
    unittest.main()
