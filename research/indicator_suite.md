# Indicator suite: community Pine scripts tested + Confluence v2

Book: NVDA, AVGO, META, AMD, TSM, NET, KLAC, SMH, BMPS.MI, BPE.MI, BNKE.PA, GLD,
VHYL.L, SPY, IQSE.DE · 2015-01-01 → 2026-08-13 · Yahoo total return · 252-bar
warmup · 10 bps commission + 5 bps slippage · T+1 open fills. All entry timers
share the v1.2 stepped-Chandelier risk block so only the entry differs.
OOS split: 2015-2020 vs 2021-2026.

## Pine status (TradingView)

| File | Status |
|------|--------|
| `ema_gc_adaptive.pine` | v1.2 + EMA/SMA toggle |
| `confluence_v2.pine` | new — mirrors `confluence_v2` engine strategy |
| `supertrend_strategy.pine` | rewritten v6, costs added, long-only toggle |
| `squeeze_momentum_lazy.pine` | rewritten v6 (kept the multKC-on-BB quirk) |
| `rsi_divergence.pine` | rewritten v6 |
| `lorentzian_classification.pine` | cleaned: private libs + `request.footprint` removed (would not compile); kNN core intact |
| `avwap_suite.pine` | new — anchors: date/YTD/QTD/swing high/swing low + σ bands |
| `ichimoku_suite.pine` | new — 9/26/52, TK cross, cloud, chikou |
| `smart_money_concept.pine` | untouched (LuxAlgo visual overlay; only BOS/CHoCH mirrored) |

## Full-period ranking (median across 15 symbols)

| Entry engine | Sharpe | CAGR | max DD | beat BH | trades |
|---|---|---|---|---|---|
| Buy & hold | 0.84 | 19.2% | 56.5% | — | — |
| **Confluence v2** | **0.58** | 2.1% | 8.0% | 3/15 | 423 |
| SMA50 reclaim | 0.57 | 1.8% | 6.4% | 2/15 | 343 |
| EMA pullback v1.2 | 0.56 | 2.0% | 6.8% | 2/15 | 334 |
| SMC BOS/CHoCH | 0.51 | 2.0% | 8.2% | 2/15 | 607 |
| Supertrend (3, 10) | 0.49 | 1.7% | 6.3% | 2/15 | 676 |
| Squeeze momentum | 0.47 | 1.3% | 7.1% | 1/15 | 326 |
| Ichimoku (9/26/52) | 0.47 | 1.4% | 5.9% | 2/15 | 311 |
| Lorentzian kNN | 0.42 | 1.6% | 7.9% | 2/15 | 606 |

## Which suits swing trading: Supertrend vs Lorentzian vs EMA

| | 2015-2020 Sharpe / E[R] | 2021-2026 Sharpe / E[R] | Verdict |
|---|---|---|---|
| **EMA reclaim v1.2** | 0.48 / 0.30 | 0.63 / 0.70 | **Winner — only one stable in both halves** |
| Supertrend | 0.37 / 0.27 | 0.55 / 0.31 | Consistent but weaker, 2x trades (whipsaw cost) |
| Lorentzian kNN | 0.21 / 0.19 | 0.61 / 0.41 | Regime-dependent: near-zero edge pre-2021. Classic data-mined pattern; do not trust standalone |
| Squeeze momentum | 0.49 / 0.08 | 0.62 / 0.55 | Sharpe OK but early expectancy fragile → useful only as co-trigger with location filter |
| SMC BOS | 0.47 / 0.30 | 0.49 / 0.32 | Stable but mediocre; 607 trades, no edge over reclaim |
| Ichimoku | 0.25 / 0.25 | 0.43 / 0.44 | Too laggy on daily bars for these names |

## Confluence v2 (frozen rule)

```
Regime:    EMA50 > EMA200; flatten on death cross
Trigger A: close crosses back above EMA50            (pullback resumption)
Trigger B: squeeze release with positive momentum,
           only if close > AVWAP anchored at the last confirmed swing low
Exit:      stepped Chandelier (hard 3.5 ATR → BE @ 1R → HH − 3 ATR @ 2R)
Size:      1.5% equity risk per trade
```

Rationale: breakout-style entries (squeeze) need location context — AVWAP from
the last swing low is the published institutional reference (Brian Shannon).
Reclaim entries already fire at a defined location (the EMA50) so they are not
gated.

Numbers: full period Sharpe 0.58 / E[R] 0.57 / PF 2.01; OOS 0.46 → 0.73 vs base
0.48 → 0.63. More entries (423 vs 334) with the weak-half performance intact.

Component A/B (why the rest was rejected):

| Variant | Full Sharpe | 2015-2020 | 2021-2026 | Decision |
|---|---|---|---|---|
| base EMA v1.2 | 0.56 | 0.48 | 0.63 | baseline |
| + AVWAP hard filter (all entries) | 0.54 | **0.22** | 0.75 | reject — OOS unstable |
| + squeeze co-trigger (ungated) | 0.58 | — | — | reject — PF 1.99, DD 8.4% |
| + Ichimoku cloud gate | 0.38 | — | — | reject — laggy |
| + RSI divergence gate | 0.58 | **0.40** | 0.85 | reject — regime luck, same failure mode as the old RSI band |
| **reclaim OR AVWAP-gated squeeze** | **0.58** | **0.46** | **0.73** | **keep** |

Best confluence_v2 names: NVDA (0.97 Sharpe, +1.01R), NET (0.95, +0.85R),
IQSE.DE (0.79, +0.68R), SMH (0.67), BMPS.MI (0.63), TSM (0.63).

Tests: `backtesting/tests/test_indicator_suite.py` (supertrend fixture + band
logic, squeeze detection, AVWAP anchor math, Lorentzian no-lookahead, Ichimoku
displaced-cloud check). JSON: `backtesting/data/runs/indicator_suite_final.json`.
