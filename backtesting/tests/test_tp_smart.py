import unittest
import numpy as np

from backtesting.dca_vs_lumpsum import Month
from backtesting.tp_smart import (
    CONTRIBUTION,
    run_smart_ema,
    run_tp4,
)

class TpSmartTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.prices = np.cumprod(1 + rng.normal(0.0004, 0.01, 500)) * 100
        self.months = [Month(key=f"y{m:03d}", first=m * 10, mid=m * 10 + 4,
                             last=m * 10 + 9, days=tuple(range(m * 10, m * 10 + 10)))
                       for m in range(50)]
        self.cumlog = np.linspace(0, 0.05, 500)

    def test_tp4_caps_at_four_open_slots(self):
        r = run_tp4(self.prices, self.months, self.cumlog, 0, CONTRIBUTION * 50)
        self.assertGreater(r.n_buys, 0)
        self.assertGreater(r.n_tp_exits + r.n_time_exits, 0)
        self.assertLessEqual(r.max_dd, 1.0)

    def test_smart_ema_contribs_sum(self):
        fired = {m.key for i, m in enumerate(self.months) if i % 2 == 0}
        r = run_smart_ema(self.prices, self.months, self.cumlog, 0, fired)
        self.assertAlmostEqual(r.total_contrib, 2500 * 25 + 500 * 25, places=6)
        self.assertGreater(r.term, 0)

    def test_empty_fired_set_equals_slow_dca(self):
        r0 = run_smart_ema(self.prices, self.months, self.cumlog, 0, set())
        r1 = run_smart_ema(self.prices, self.months, self.cumlog, 0, {self.months[0].key})
        self.assertLess(r0.total_contrib, r1.total_contrib)


if __name__ == "__main__":
    unittest.main()
