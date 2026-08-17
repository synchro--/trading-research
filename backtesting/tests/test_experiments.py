from __future__ import annotations

import unittest
from datetime import date, timedelta

from backtesting.bottom_finder import weekly_bars
from backtesting.engine.types import Bar
from backtesting.portfolio import portfolio_metrics, run_portfolio


def bar(t: str, px: float) -> Bar:
    return Bar(t=t, o=px, h=px * 1.01, l=px * 0.99, c=px, v=1.0)


class WeeklyAggregationTests(unittest.TestCase):
    def test_weekly_bar_uses_first_open_last_close_and_extremes(self):
        bars = [
            Bar("2024-01-01", 100, 102, 99, 101, 10),
            Bar("2024-01-02", 101, 105, 100, 104, 20),
            Bar("2024-01-05", 104, 106, 98, 99, 30),
            Bar("2024-01-08", 99, 101, 97, 100, 40),
        ]
        weekly = weekly_bars(bars)
        self.assertEqual(len(weekly), 2)
        self.assertEqual(weekly[0].o, 100)
        self.assertEqual(weekly[0].c, 99)
        self.assertEqual(weekly[0].h, 106)
        self.assertEqual(weekly[0].l, 98)
        self.assertEqual(weekly[0].v, 60)


class PortfolioTests(unittest.TestCase):
    def test_static_equal_weight_buys_each_sleeve_once(self):
        d0 = date(2020, 1, 1)
        a, b = [], []
        for i in range(300):
            t = (d0 + timedelta(days=i)).isoformat()
            a.append(bar(t, 100.0 + i * 0.1))
            b.append(bar(t, 100.0))
        points = run_portfolio(
            ["A", "B"],
            {"A": a, "B": b},
            method="static_ew",
            initial_cash=10_000,
            commission_bps=0,
            slippage_bps=0,
            warmup_bars=252,
        )
        self.assertTrue(points)
        self.assertAlmostEqual(points[0].invested_fraction, 1.0)
        self.assertGreater(points[-1].equity, points[0].equity)
        metrics = portfolio_metrics(points, initial_cash=10_000)
        self.assertGreater(metrics["cagr"], 0)
        self.assertAlmostEqual(metrics["average_invested"], 1.0)


if __name__ == "__main__":
    unittest.main()
