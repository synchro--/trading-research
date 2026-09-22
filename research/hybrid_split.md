# Hybrid LS/DCA splits: staged deployment of a windfall

Run date: 2026-09-17. Companion to `dca_master_report.md`.

## Reproduce

```bash
uv run python -m backtesting.hybrid_split --reuse-cache
uv run python -m unittest backtesting.tests.test_hybrid_split -v
```

JSON: `backtesting/data/hybrid_split.json`.

**Design**: the full budget X = 500 × months is available at day 0. A share α
is invested immediately; the rest is spread over a tail of M months and sits in
the money market (^IRX) until deployed. α ∈ {25, 50, 75}% × M ∈ {12, 24,
full-window} = 9 hybrids, plus `ls` (α=1), `dca_full` (α=0, M=N), and a dip-
accelerated variant (`hyb50_full_dip`: the full-window tail doubles its monthly
buy on the first-two-weeks red-dip trigger). 498 windows × 4 portfolios.

![hybrid frontier](plots/f1_hybrid_frontier.png)

## Pooled results (baseline `ls`)

| Strategy | median | adv med | adv mean | win vs LS | down at month 12 | mean shortfall |
|---|---:|---:|---:|---:|---:|---:|
| ls | **190,301** | +0.0% | +0.0% | - | 20% | 15.4% |
| hyb75_m12 | 189,435 | -0.7% | -0.2% | 24% | 19% | 13.2% |
| hyb50_m12 | 189,061 | -1.4% | **-0.4%** | 24% | 18% | 11.5% |
| hyb25_m12 | 187,316 | -2.1% | -0.7% | 24% | 18% | 9.5% |
| hyb50_m24 | 185,363 | -3.0% | -1.2% | 26% | 19% | 9.3% |
| hyb50_mfull | 163,020 | -13.6% | -13.6% | 1% | 19% | 7.8% |
| hyb50_full_dip | 169,802 | -9.7% | -9.3% | 7% | 19% | 8.1% |
| dca_full | 133,572 | -27.3% | -27.3% | 1% | **8%** | **0.4%** |

Per portfolio (α=50, 12-month tail): -1.9% stocks_100, -1.6% 80/20,
-1.3% 60/40, -1.1% GB (median).

## Findings

1. **Short tails are nearly free**: a 12-month tail costs only -0.4% on
   average (median -1.4%) versus investing everything on day 0, and still wins
   ~1 in 4 windows. This is the Vanguard result reproduced on 2004-2026 data
   (their 12-month CA on 60/40 lost by ~2.3% on average over 1926-2011).
2. **Long tails pay the full cash drag**: stretching the rest over the whole
   window costs -13.6% (α=50) to -20.5% (α=25) — the same opportunity cost the
   original study measured (-27% for full DCA).
3. **Regret falls with staging, but only slightly for 12-month tails**:
   P(underwater at 1 year) drops from 20% (ls) to 18% (hyb50_m12) — while full
   DCA cuts it to 8%. The behavioural benefit of a 12-month tail is small; the
   real regret reduction requires a long cash-heavy deployment, which is
   exactly what costs the most return.
4. **The dip-accelerated tail does not help** (-9.3% mean vs -27.3% for plain
   full DCA, i.e. it recovers part of the drag but stays far behind short
   tails). Consistent with the dip-rule study: triggers add ~1-2% per euro at
   best.
5. **Dip-accelerated vs plain long tail**: `hyb50_full_dip` (-9.7%) beats
   `hyb50_mfull` (-13.6%) by ~4pp — the dip-doubling rule recovers about a
   third of the long-tail drag.

## Practical reading

If you inherit €60k and want to sleep well: invest 50-75% immediately and stage
the rest over 12 months — the expected cost is ~€250-800 on a €60k windfall
(0.4-1.4%), and you avoid the regret tail. Anything longer than a year is
paying ~1%+ per quarter of extra staging for weaker regret reduction.

## Caveats

Same sample caveats as the parent studies (2004+ data, overlapping windows,
nominal USD, accumulation-equivalent total returns, 10+5 bps costs, no taxes).
The underwater-1y metric is a proxy that ignores trading costs and marks at
month 12.
