"""Lorentzian kNN classifier, long-only — mirror of lorentzian_classification.pine.

Faithful port of the community kNN core: 12 rolling-normalized features,
Lorentzian distance d = Σ log(1+|Δ|) with temporal decay, K=4 vote weighted
1/(1+d), EMA(3) smoothing, threshold 0.85 + confidence > 0.5 + 5-bar cooldown.

Dropped from the Pine original: private library imports and request.footprint
flow data (tick data does not exist offline). Walk-forward: at bar t the label
window only uses closes up to bar t.

Entry: first long classification. Flatten: first short classification.
Risk: v1.2 stepped Chandelier.
"""
from __future__ import annotations

import numpy as np

from backtesting.engine import indicators as ta
from backtesting.engine.types import Bar
from backtesting.strategies.ema_gc_adaptive import StrategyConfig, stepped_chandelier_trail


def _normalize(series: np.ndarray, length: int) -> np.ndarray:
    """Pine normalize_series: rolling min/max scale to [-1, 1]."""
    lo = ta.rolling_min(series, length)
    hi = ta.rolling_max(series, length)
    rng = hi - lo
    out = np.where(rng > 0, 2.0 * (series - lo) / np.where(rng > 0, rng, 1.0) - 1.0, 0.0)
    out[np.isnan(series)] = 0.0
    return out


def _pct_back(c: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(c), np.nan, dtype=float)
    out[n:] = (c[n:] - c[:-n]) / c[:-n]
    return out


class LorentzianKnn:
    name = "lorentzian_knn"

    def __init__(self, bars: list[Bar], cfg: StrategyConfig | None = None,
                 k: int = 4, lookback: int = 100, horizon: int = 5,
                 decay: float = 0.98, threshold: float = 0.85,
                 smooth: int = 3, cooldown: int = 5):
        self.cfg = cfg or StrategyConfig()
        self.k, self.lookback, self.horizon = k, lookback, horizon
        self.decay, self.threshold, self.cooldown = decay, threshold, cooldown
        c = np.array([b.c for b in bars], dtype=float)
        h = np.array([b.h for b in bars], dtype=float)
        l = np.array([b.l for b in bars], dtype=float)
        v = np.array([b.v for b in bars], dtype=float)
        self.close = c
        self.high = h
        self.atr = ta.atr(h, l, c, self.cfg.atr_len)

        avg_vol = ta.sma(v, 20)
        with np.errstate(divide="ignore", invalid="ignore"):
            vr0 = np.where(avg_vol > 0, v / avg_vol, 0.0)
        vr1 = np.roll(vr0, 1); vr1[0] = 0.0
        vr2 = np.roll(vr0, 2); vr2[:2] = 0.0
        basis = ta.sma(c, 20)
        sd = ta.stdev(c, 20)
        bb_width = (basis + 2 * sd) - (basis - 2 * sd)
        rsi = ta.rsi(c, 14)
        macd_line, _, _ = ta.macd(c, 12, 26, 9)

        feats = [
            _normalize(_pct_back(c, 1), lookback),
            _normalize(_pct_back(c, 2), lookback),
            _normalize(_pct_back(c, 3), lookback),
            _normalize(_pct_back(c, 5), lookback),
            _normalize(_pct_back(c, 8), lookback),
            _normalize(vr0, lookback),
            _normalize(vr1, lookback),
            _normalize(vr2, lookback),
            _normalize(np.where(c > 0, self.atr / c, np.nan), lookback),
            _normalize(np.where(c > 0, bb_width / c, np.nan), lookback),
            np.where(np.isnan(rsi), 0.0, (rsi - 50.0) / 50.0),
            _normalize(np.where(c > 0, macd_line / c, np.nan), lookback),
        ]
        self.F = np.column_stack(feats)  # (n, 12)
        self._compute_signals()
        self._last_entry: float | None = None
        self._hh: float = float("-inf")

    def _compute_signals(self) -> None:
        n = len(self.close)
        c = self.close
        raw_pred = np.zeros(n, dtype=float)
        raw_conf = np.zeros(n, dtype=float)
        min_bar = self.lookback + self.horizon + 10
        offsets_all = np.arange(self.horizon, self.lookback)
        decay_pow = np.maximum(self.decay ** offsets_all.astype(float), 0.01)
        for t in range(min_bar, n):
            end = min(self.lookback - 1, t - self.horizon - 10)
            m = offsets_all <= end
            offs = offsets_all[m]
            if len(offs) == 0:
                continue
            hist = self.F[t - offs]                     # (m, 12)
            dist = np.log1p(np.abs(self.F[t] - hist)).sum(axis=1) / decay_pow[m]
            # outcome: sign of the horizon-forward move from each historical bar
            # (t - off + horizon <= t, so it is fully in the past at bar t)
            fut = c[t - offs + self.horizon] - c[t - offs]
            outcome = np.where(fut > 0, 1.0, -1.0)
            kk = min(self.k, len(dist))
            idx = np.argpartition(dist, kk - 1)[:kk]
            w = 1.0 / (1.0 + dist[idx])
            tot = w.sum()
            if tot <= 0:
                continue
            raw_pred[t] = float((outcome[idx] * w).sum() / tot)
            up = w[outcome[idx] > 0].sum()
            down = w[outcome[idx] < 0].sum()
            raw_conf[t] = float(abs(up - down) / tot)

        pred = self._ema_all(raw_pred, 3)
        conf = self._ema_all(raw_conf, 3)
        long_raw = (pred > self.threshold) & (conf > 0.5)
        short_raw = (pred < -self.threshold) & (conf > 0.5)

        self.long_first = np.zeros(n, dtype=bool)
        self.short_first = np.zeros(n, dtype=bool)
        last_sig = -10**9
        prev_l = prev_s = False
        for i in range(n):
            clear = (i - last_sig) >= self.cooldown
            fl = bool(long_raw[i]) and not prev_l and clear
            fs = bool(short_raw[i]) and not prev_s and clear
            if fl or fs:
                last_sig = i
            self.long_first[i] = fl
            self.short_first[i] = fs
            prev_l, prev_s = bool(long_raw[i]), bool(short_raw[i])

    @staticmethod
    def _ema_all(x: np.ndarray, length: int) -> np.ndarray:
        """EMA seeded from the first value (Pine ta.ema on a full series)."""
        out = np.empty(len(x), dtype=float)
        alpha = 2.0 / (length + 1)
        acc = x[0]
        out[0] = acc
        for i in range(1, len(x)):
            acc = alpha * x[i] + (1 - alpha) * acc
            out[i] = acc
        return out

    def long_signal(self, i: int) -> bool:
        if np.isnan(self.atr[i]):
            return False
        return bool(self.long_first[i])

    def should_flatten(self, i: int) -> bool:
        return bool(self.short_first[i])

    def initial_risk(self, i: int) -> float:
        atr = self.atr[i]
        if np.isnan(atr) or atr <= 0:
            return 0.0
        return float(self.cfg.atr_base_mult * atr)

    def trail_candidate(self, i: int, entry_px: float, initial_risk: float) -> float:
        if self._last_entry is None or abs(self._last_entry - entry_px) > 1e-9:
            self._hh = float(self.high[i])
            self._last_entry = entry_px
        cand, self._hh = stepped_chandelier_trail(
            close=float(self.close[i]), high=float(self.high[i]), atr=float(self.atr[i]),
            entry_px=entry_px, initial_risk=initial_risk, hh=self._hh,
            be_r=self.cfg.be_r, trail_r=self.cfg.trail_r,
            chandelier_mult=self.cfg.chandelier_mult,
        )
        return cand
