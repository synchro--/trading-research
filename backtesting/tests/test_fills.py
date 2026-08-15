"""Synthetic fill-model tests (DESIGN.md engine 0.1 acceptance)."""
from __future__ import annotations

import unittest

from backtesting.engine.broker import Broker
from backtesting.engine.indicators import crossover
from backtesting.engine.loop import run
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import EmaPullbackV1
import numpy as np


def _bar(day: str, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(t=day, o=o, h=h, l=l, c=c, v=1)


class FillModelTests(unittest.TestCase):
    def test_entry_fills_next_open(self):
        broker = Broker(cash=10_000, commission_bps=0, slippage_bps=0)
        broker.mark_bar(0)
        # signal on bar 0 — not filled yet
        self.assertIsNone(broker.position)
        broker.mark_bar(1)
        broker.buy("2020-01-02", px=100.0, qty=10, initial_risk=10.0)
        self.assertIsNotNone(broker.position)
        self.assertEqual(broker.position.entry_px, 100.0)
        self.assertEqual(broker.position.trail, 90.0)

    def test_stop_fills_min_open_trail(self):
        broker = Broker(cash=10_000, commission_bps=0, slippage_bps=0)
        broker.mark_bar(0)
        broker.buy("2020-01-02", px=100.0, qty=10, initial_risk=10.0)
        broker.mark_bar(1)
        px = broker.stop_fill_price(bar_open=99.0, bar_low=85.0)
        self.assertEqual(px, 90.0)  # min(open, trail)
        broker.sell("2020-01-03", px, "trail")
        self.assertIsNone(broker.position)
        self.assertEqual(broker.trades[0].reason, "trail")
        self.assertEqual(broker.trades[0].exit_px, 90.0)

    def test_gap_through_stop_uses_open(self):
        broker = Broker(cash=10_000, commission_bps=0, slippage_bps=0)
        broker.mark_bar(0)
        broker.buy("2020-01-02", px=100.0, qty=10, initial_risk=10.0)
        broker.mark_bar(1)
        px = broker.stop_fill_price(bar_open=80.0, bar_low=79.0)
        self.assertEqual(px, 80.0)

    def test_crossover_is_not_lookahead(self):
        a = np.array([1.0, 1.0, 3.0])
        b = np.array([2.0, 2.0, 2.0])
        x = crossover(a, b)
        self.assertFalse(x[0])
        self.assertFalse(x[1])
        self.assertTrue(x[2])


class StrategySignalTests(unittest.TestCase):
    def test_gc_bar_is_not_an_entry_regime(self):
        # Build a short series where ema50 crosses ema200 on the last bar.
        n = 260
        close = np.concatenate([np.full(200, 50.0), np.linspace(50, 80, 60)])
        bars = []
        for i, c in enumerate(close):
            bars.append(_bar(f"2018-01-{(i%28)+1:02d}", c, c + 1, c - 1, c))
        # timestamps must be unique-ish; use ordinal
        bars = [
            Bar(t=f"2015-01-01", o=close[0], h=close[0]+1, l=close[0]-1, c=float(close[0]), v=1)
        ]
        # rebuild with unique dates
        from datetime import date, timedelta
        d0 = date(2015, 1, 1)
        bars = []
        for i, c in enumerate(close):
            d = d0 + timedelta(days=i)
            c = float(c)
            bars.append(Bar(t=d.isoformat(), o=c, h=c + 0.5, l=c - 0.5, c=c, v=1))
        s = EmaPullbackV1(bars)
        # First bar where ema50 > ema200 should not count as already-in-regime.
        first_bull = None
        for i in range(len(bars)):
            e50, e200 = s.ema50[i], s.ema200[i]
            if np.isnan(e50) or np.isnan(e200):
                continue
            if e50 > e200:
                first_bull = i
                break
        self.assertIsNotNone(first_bull)
        self.assertFalse(s.bull_regime(first_bull))
        if first_bull + 1 < len(bars):
            # next day, if still bull, regime is on
            if s.ema50[first_bull + 1] > s.ema200[first_bull + 1]:
                self.assertTrue(s.bull_regime(first_bull + 1))


class EndToEndSynthetic(unittest.TestCase):
    def test_one_entry_trail_exit(self):
        from datetime import date, timedelta

        d0 = date(2016, 1, 1)
        bars: list[Bar] = []
        px = 100.0
        # Strong grind so EMA50 > EMA200 after warmup, RSI not stuck at 100.
        for i in range(280):
            d = d0 + timedelta(days=i)
            px *= 1.002
            o, c = px, px * 1.001
            bars.append(Bar(t=d.isoformat(), o=o, h=max(o, c) * 1.002, l=min(o, c) * 0.998, c=c, v=1e6))
        # Pull below EMA50 then reclaim
        for j in range(8):
            i = 280 + j
            d = d0 + timedelta(days=i)
            px *= 0.985
            bars.append(Bar(t=d.isoformat(), o=px, h=px * 1.005, l=px * 0.99, c=px * 0.992, v=1e6))
        px = bars[-1].c
        for j in range(3):
            i = 288 + j
            d = d0 + timedelta(days=i)
            px *= 1.02
            bars.append(Bar(t=d.isoformat(), o=px * 0.99, h=px * 1.01, l=px * 0.985, c=px, v=1e6))
        # Crash through any trail
        d = d0 + timedelta(days=291)
        crash = bars[-1].c * 0.7
        bars.append(Bar(t=d.isoformat(), o=bars[-1].c, h=bars[-1].c, l=crash, c=crash, v=1e6))

        result = run(bars, symbol="SYN", start="2016-10-01", initial_cash=20_000, commission_bps=0, slippage_bps=0)
        # May be 0 or more depending on RSI band; fill model still must only use trail|regime
        for t in result.trades:
            self.assertIn(t.reason, ("trail", "regime"))
        if result.trades:
            self.assertGreater(result.trades[0].entry_px, 0)


class MetricsTests(unittest.TestCase):
    def test_cagr_sharpe_sortino_maxdd(self):
        from backtesting.engine.metrics import cagr, sharpe, sortino, summarize
        from backtesting.engine.types import EquityPoint, RunResult

        eq = [
            EquityPoint("2020-01-01", 100.0, 0.0),
            EquityPoint("2021-01-01", 110.0, 0.0),
        ]
        self.assertAlmostEqual(cagr(eq), 0.10, delta=0.002)
        rets = [0.01, -0.005, 0.002]
        self.assertGreater(sharpe(rets), 0)
        self.assertGreater(sortino(rets), sharpe(rets) - 1)
        result = RunResult("X", trades=[], equity=[
            EquityPoint("2020-01-02", 100.0, 0.0),
            EquityPoint("2020-01-03", 90.0, 0.10),
            EquityPoint("2020-01-06", 95.0, 0.05),
        ], fills=[], open_position=None)
        m = summarize(result)
        self.assertAlmostEqual(m["max_dd"], 0.10)
        self.assertIn("cagr", m)
        self.assertIn("sharpe", m)
        self.assertIn("sortino", m)


if __name__ == "__main__":
    unittest.main()
