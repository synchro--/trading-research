"""Unit tests for the indicator-suite mirrors (DESIGN plan: Pine parity checks)."""
from __future__ import annotations

import unittest
from datetime import date, timedelta

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.avwap import anchored_vwap_swing_low
from backtesting.strategies.lorentzian_knn import LorentzianKnn


def _bars(rows) -> list[Bar]:
    d0 = date(2020, 1, 1)
    return [
        Bar(t=(d0 + timedelta(days=i)).isoformat(), o=o, h=h, l=l, c=c, v=v)
        for i, (o, h, l, c, v) in enumerate(rows)
    ]


class SupertrendTests(unittest.TestCase):
    def test_direction_flips_and_band_logic(self):
        # Downtrend then strong rally: direction must start +1 (down) and flip to -1.
        n = 60
        px = np.concatenate([np.linspace(100, 80, 30), np.linspace(80, 130, 30)])
        h, l, c = px + 1, px - 1, px
        st, direction = ta.supertrend(h, l, c, factor=3.0, period=10)
        valid = ~np.isnan(direction)
        self.assertTrue(valid.any())
        self.assertEqual(direction[valid][0], 1.0)
        self.assertEqual(direction[-1], -1.0)
        flips = np.where((direction[1:] == -1.0) & (direction[:-1] == 1.0))[0]
        self.assertEqual(len(flips), 1)
        i = flips[0] + 1
        # In an uptrend the supertrend line sits below price; band never falls.
        for j in range(i, n):
            self.assertLess(st[j], c[j])
            if j > i:
                self.assertGreaterEqual(st[j], st[j - 1] - 1e-9)

    def test_hand_computed_first_bands(self):
        # Flat tape: upper = hl2 + 3*atr, lower = hl2 - 3*atr; tr = h-l = 2 -> atr = 2.
        n = 15
        h = np.full(n, 101.0)
        l = np.full(n, 99.0)
        c = np.full(n, 100.0)
        st, direction = ta.supertrend(h, l, c, factor=3.0, period=10)
        i = 9  # first bar with a valid ATR
        self.assertAlmostEqual(st[i], 100.0 + 3.0 * 2.0)  # starts in downtrend -> upper band
        self.assertEqual(direction[i], 1.0)


class SqueezeTests(unittest.TestCase):
    def test_squeeze_detected_in_compression_then_releases(self):
        rng = np.random.default_rng(7)
        # Wide-range regime, then dead-flat compression, then a breakout.
        wide = 100 + np.cumsum(rng.normal(0, 3.0, 60))
        flat = np.full(40, wide[-1]) + rng.normal(0, 0.05, 40)
        breakout = flat[-1] + np.cumsum(np.full(15, 2.0))
        px = np.concatenate([wide, flat, breakout])
        h, l, c = px + 0.2, px - 0.2, px
        length, mult_kc = 20, 1.5
        basis = ta.sma(c, length)
        dev = mult_kc * ta.stdev(c, length)
        tr = ta.true_range(h, l, c)
        rangema = ta.sma(tr, length)
        sqz_on = ((basis - dev) > (basis - rangema * mult_kc)) & ((basis + dev) < (basis + rangema * mult_kc))
        # squeeze must be on during the flat stretch and off during the breakout
        self.assertTrue(sqz_on[85:99].any())
        self.assertFalse(bool(sqz_on[-1]))


class AvwapTests(unittest.TestCase):
    def test_avwap_is_volume_weighted_from_confirmed_pivot(self):
        # V-shape: low at bar 10, pivot length 3 -> confirmed at bar 13.
        px = list(np.linspace(110, 100, 11)) + list(np.linspace(101, 115, 15))
        rows = [(p, p + 1, p - 1, p, 100 + i) for i, p in enumerate(px)]
        bars = _bars(rows)
        av = anchored_vwap_swing_low(bars, length=3)
        self.assertTrue(np.isnan(av[12]))  # not confirmed yet
        tp = np.array([(b.h + b.l + b.c) / 3 for b in bars])
        v = np.array([b.v for b in bars], dtype=float)
        expected_13 = (tp[10:14] * v[10:14]).sum() / v[10:14].sum()
        self.assertAlmostEqual(av[13], expected_13)
        expected_20 = (tp[10:21] * v[10:21]).sum() / v[10:21].sum()
        self.assertAlmostEqual(av[20], expected_20)


class LorentzianNoLookaheadTests(unittest.TestCase):
    def test_signals_do_not_change_when_future_bars_change(self):
        rng = np.random.default_rng(42)
        n = 260
        px = 100 * np.cumprod(1 + rng.normal(0.0005, 0.02, n))
        vol = rng.integers(1_000, 5_000, n).astype(float)
        rows = [(p, p * 1.01, p * 0.99, p, v) for p, v in zip(px, vol)]
        bars_full = _bars(rows)
        # Perturb the last 20 bars heavily
        rows2 = rows[:-20] + [(p * 0.5, p * 0.51, p * 0.49, p * 0.5, v) for (p, _, _, _, v) in
                              [(r[0], 0, 0, 0, r[4]) for r in rows[-20:]]]
        bars_cut = _bars(rows2)
        a = LorentzianKnn(bars_full)
        b = LorentzianKnn(bars_cut)
        cut = n - 20
        # Rolling normalization looks back `lookback` bars, never forward, so all
        # signals strictly before the perturbation must be identical.
        self.assertTrue((a.long_first[:cut] == b.long_first[:cut]).all())
        self.assertTrue((a.short_first[:cut] == b.short_first[:cut]).all())


class IchimokuTests(unittest.TestCase):
    def test_cloud_uses_displaced_spans_and_long_requires_above_cloud(self):
        from backtesting.strategies.ichimoku import IchimokuCloud

        rng = np.random.default_rng(3)
        px = 100 * np.cumprod(1 + rng.normal(0.001, 0.01, 400))
        rows = [(p, p * 1.005, p * 0.995, p, 1000) for p in px]
        s = IchimokuCloud(_bars(rows))
        # any long signal bar must have close above both displaced spans
        h = np.array([r[1] for r in rows])
        l = np.array([r[2] for r in rows])
        tenkan = ta.donchian_mid(h, l, 9)
        kijun = ta.donchian_mid(h, l, 26)
        span_a = (tenkan + kijun) / 2
        span_b = ta.donchian_mid(h, l, 52)
        for i in np.where(s.long_sig)[0]:
            top = max(span_a[i - 26], span_b[i - 26])
            self.assertGreater(s.close[i], top)


if __name__ == "__main__":
    unittest.main()
