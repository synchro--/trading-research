"""Unit tests for the deep-history data plumbing (no network)."""
from __future__ import annotations

import unittest

import numpy as np

from backtesting.deep_history import (
    STRATEGIES,
    build_bond_index,
    parse_fred_csv,
    parse_french_daily,
)

FRENCH_FIXTURE = """\n
This file was created by CMPT_ME_BEME_RETS using the 202401 CRSP database.
The 1-month TBill return is from Ibbotson and Associates.

,Mkt-RF,SMB,HML,RF
19260701,0.10,-0.25,-0.27,0.01
19260702,0.45,-0.11,-0.20,0.01
19260706,-0.32,0.10,0.28,0.01

Annual Factors:
,Mkt-RF,SMB,HML,RF
1927,29.47,-2.41,-3.83,3.12
"""

FRED_FIXTURE = """observation_date,DGS10
1962-01-02,4.06
1962-01-03,.
1962-01-04,4.03
"""


class ParserTests(unittest.TestCase):
    def test_french_daily(self) -> None:
        rows = parse_french_daily(FRENCH_FIXTURE)
        self.assertEqual(len(rows), 3)
        d, mkt, rf = rows[0]
        self.assertEqual(d, "1926-07-01")
        self.assertAlmostEqual(mkt, 0.0011, places=9)  # (0.10+0.01)/100
        self.assertAlmostEqual(rf, 0.0001, places=9)
        self.assertEqual(rows[-1][0], "1926-07-06")

    def test_fred_csv_skips_missing(self) -> None:
        rows = parse_fred_csv(FRED_FIXTURE)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows["1962-01-02"], 4.06)
        self.assertNotIn("1962-01-03", rows)


class BondIndexTests(unittest.TestCase):
    def test_falling_yields_raise_bond_index(self) -> None:
        dates = [
            "2000-01-03", "2000-01-31", "2000-02-01", "2000-02-29",
            "2000-03-01", "2000-03-31",
        ]
        yields = {
            "2000-01-03": 6.0, "2000-01-31": 6.0,
            "2000-02-01": 5.5, "2000-02-29": 5.5,
            "2000-03-01": 5.0, "2000-03-31": 5.0,
        }
        idx = build_bond_index(dates, yields)
        self.assertGreater(idx[-1], 1.0)
        # Feb gained 6%/12 + 8 * 0.5% = 0.5% + 4% = 4.5% at the Jan->Feb step
        self.assertGreater(idx[3], 1.04)

    def test_flat_yields_accrue_coupon(self) -> None:
        dates = ["2000-01-03", "2000-01-31", "2000-02-01", "2000-02-29"]
        yields = {"2000-01-03": 6.0, "2000-01-31": 6.0, "2000-02-01": 6.0, "2000-02-29": 6.0}
        idx = build_bond_index(dates, yields)
        self.assertGreater(idx[-1], 1.004)
        self.assertLess(idx[-1], 1.01)


if __name__ == "__main__":
    unittest.main()
