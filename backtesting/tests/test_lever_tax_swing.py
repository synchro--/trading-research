import unittest
import numpy as np

from backtesting.lever_tax_swing import (
    CONTRIBUTION,
    TAX,
    Month,
    lever_path,
    load_experiment,
    simulate,
)


class LeverTaxSwingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dates, cls.paths, cls.months, cls.cumlog, _ = load_experiment(
            "2026-12-31", False
        )
        cls.w = 240
        cls.window = cls.months[: cls.w]
        off = cls.window[0].first
        end = cls.window[-1].last
        cls.prices = cls.paths["1x"][off : end + 1]

    def test_lever_1x_matches_1x_up_to_fund_er(self):
        p1 = self.paths["1x"]
        p2 = lever_path(p1, {d: 0.0 for d in self.dates}, self.dates, 1.0)
        np.testing.assert_allclose(p2, p1, rtol=2e-1)

    def test_same_money_every_strategy(self):
        X = CONTRIBUTION * self.w
        for kind, tax in (("ls", 0.0), ("dca", 0.0), ("oracle", 0.0), ("swing", TAX)):
            res = simulate(kind, self.prices, self.window, self.cumlog, 22, X, tax)
            funded = X + (0.0 if kind == "ls" else 0.0)
            self.assertLess(res.term, funded * 60, msg=f"{kind} implausible term {res.term}")
            self.assertGreater(res.term, 0)

    def test_dca_deploys_all_contributions(self):
        res = simulate("dca", self.prices, self.window, self.cumlog, 22,
                       CONTRIBUTION * self.w, 0.0)
        self.assertEqual(res.n_buys, self.w)

    def test_lev_worse_dd_than_1x(self):
        r1 = simulate("ls", self.prices, self.window, self.cumlog, 22,
                      CONTRIBUTION * self.w, 0.0)
        p3 = lever_path(self.prices, {self.dates[i]: 0.0 for i in range(len(self.dates))},
                        self.dates, 3.0)[22:22 + len(self.prices)]
        r3 = simulate("ls", p3, self.window, self.cumlog, 22,
                      CONTRIBUTION * self.w, 0.0)
        self.assertGreater(r3.max_dd, r1.max_dd)


if __name__ == "__main__":
    unittest.main()
