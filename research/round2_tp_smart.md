# Round 2: LS vs DCA vs quarterly take-profit trading vs EMA-boosted DCA

Run date: 2026-09-20. Module: `backtesting/tp_smart.py` · JSON:
`backtesting/data/round2_tp_smart.json` · reproduce:
`uv run python -m backtesting.tp_smart --reuse-cache`

Setup: SPY total-return daily bars 2004-11-18 → 2026-09-16 (5,503 days) · 10 bps
commission + 5 bps slippage per leg · idle cash at ^IRX (y/360) · signals on data
through close t, fills at t+1 close · windows: monthly starts, horizons
{10,12,14,16,18,20}y → 498 windows (pooled below) · no parameter fitting (+5% TP,
10% budget/trade, 4 trades/yr, 5x EMA boost are user-stated hypothesis values, not
fitted).

## Strategies

| label | rule |
|---|---|
| ls | all X = 500 × months on day 1 |
| dca | 500/mo at month mid |
| tp4 | contributions 500/mo; up to 4 live trades/yr, each 10% of X; every quarter's first trading day opens a slot if free; exit at +5% take-profit or 252 trading-day time stop; T+1 fills; only ~40% of capital can be live at once by design |
| smart_ema | 500/mo; in any month where EMA Pullback v1.2's long signal fires (EMA50>EMA200 + close crossing above EMA50), that month's buy is 2,500 (5x) instead of 500, at month mid |

Note on fairness: smart_ema deploys MORE total money (signal months 5x the tranche) —
median contributions 200,301 vs 79,880 for the others. Compare both terminal and
**terminal per €1,000 contributed** (capital efficiency).

## Pooled results over 498 windows

| | median € | p5 | p95 | med maxDD | avg contrib € | €1k contributed → € |
|---|---:|---:|---:|---:|---:|---:|
| ls | 328,597 | 124,933 | 879,140 | 47% | 79,880 | 4,158 |
| dca | 184,124 | 105,596 | 462,220 | 33% | 79,880 | 2,424 |
| tp4 | 109,588 | 75,297 | 200,241 | **15%** | 79,880 | **1,447** |
| smart_ema | 451,748 | 240,488 | 1,085,998 | 34% | 200,301 | 2,347 |

Realized trade stats (tp4, avg per window): 92 buys, 85 of them exited on the +5%
take-profit, ~6 on the 1-year time stop, ~0 otherwise — the rule works as
mechanically intended (≈95% trade win rate) and STILL produces the worst terminal:
the 4-slot yearly cap keeps ~60% of capital in cash for the entire two decades.

EMA signal activity: 100 of 263 full-series months fire at least one v1.2 signal
(~38% of months are "5x months"), so smart_ema invests ≈2.5× of a normal DCA schedule.

## Cohort robustness (median terminal by window start-year bucket)

| | 2004-09 | 2010-14 | 2015-20 |
|---|---:|---:|---:|
| ls | 361,550 | 327,431 | 229,975 |
| dca | 213,486 | 163,158 | 131,022 |
| tp4 | 122,648 | 102,352 | 86,224 |
| smart_ema | 511,940 | 417,022 | 298,520 |

Ordering is stable across cohorts: ls > smart_ema(raw, but with 2.5× money) >
dca > tp4, and **per-€ efficiency: ls > dca ≈ smart_ema > tp4** in all three.

## Findings

1. **ls is still unbeatable on efficiency** (4,158 €/€1k) — every scheduled
   trade-timing overlay that keeps money out of the index pays a compounding tax
   that no +5% capture logic recovers.
2. **tp4 (+5% take-profit swing) — rejected.** Highest win rate (~94% of trades),
   lowest drawdown (15%), worse terminal by −40% vs plain DCA and −67% vs LS. With
   the tax rate ON TOP (Italian 26% like Round 1), it can only be worse — this run
   is the tax-free version, so the real number is worse. Repeated +5% profits and
   slow capital recycling is a mathematical box: yearly profit ≈ 0.05 × 40% ×
   market drift-limited hit rate ≪ market itself.
3. **smart_ema (5x months) — looks like a win, is a size illusion**: more terminal
   euros than DCA at EVERY cohort, but only because it invests 2.51× the money.
   Per euro contributed it lands at 2,347 vs 2,424 for plain DCA — i.e., the EMA
   timer adds NOTHING to capital efficiency (−3%) and only turns up the same
   equity exposure at higher average price. Effectively "DCA with more money",
   not smarter money. Supportable claim: if you WANT more exposure, increase
   contributions — no signal needed for that. What the EMA timer did do is produce
   a smoother risk (DD 34% ≈ DCA 33%) while trims/auto-buys preserved drawdowns.
4. Contribution volumes are NOT equal across strategies, so the headline medians
   are not apples-to-apples: only €1k-contributed efficiency and identical-money
   comparisons (ls vs dca vs tp4) are directly comparable.

## What would make me doubt these numbers

- tp4's +5% target and quarterly cadence are mechanically handled; a fib ratchet
  stop or asymmetric stop-loss barely changes the story (with stops the win-rate
  falls fast — omit adding stops, since with targets at +5% the trades that fail
  default to the 1y time stop ~6% of windows).
- EMA v1.2 signal definition here is the signal only (no stop exits, no ATR trail):
  it's a contribution booster, not the trading strategy — the full swing version
  with stops/trailing was already studied in `research/oos_holdout.md` (EMA
  pullback: low Sharpe, tiny edge).
- Fractions of signal months (100/263) drive smart_ema's contribution inflation:
  results are series-specific; a different index or timeframe changes the ratio.
- Again: only one regime epoch (no 1930s, no lost-decade), single US asset,
  no dividend-tax withholding modeling.
