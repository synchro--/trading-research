# Cash is king? Waiting for a crash before deploying

Run date: 2026-09-17. Companion to `dca_master_report.md`.

## Reproduce

```bash
uv run python -m backtesting.crash_deploy --reuse-cache
uv run python -m unittest backtesting.tests.test_crash_deploy -v
```

JSON: `backtesting/data/crash_deploy.json`.

**Design** (windfall framing, identical budget X = 500 × months in every arm):
the whole budget sits in the money-market fund (^IRX) at day 0 and is deployed
only when an implementable crash trigger fires:

> drawdown vs the trailing **2 calendar-year high** of the portfolio composite
> reaches 20% (or 30%); no lookahead

| Strategy | Rule |
|---|---|
| ls | all X at day 0 (baseline) |
| wait20_lump | all X on the first day dd ≥ 20% |
| wait30_lump | all X on the first day dd ≥ 30% |
| wait20_dca12 | X/12 at the trigger, then monthly over 12 months |
| wait20_tranches | ⅓ at dd≥10%, ⅓ at dd≥20%, ⅓ at dd≥30% |
| parked | never deploy (pure MMF control) |

Anything never deployed stays in cash and still counts in terminal wealth.

![crash deployment](plots/g1_crash_deploy.png)

## Pooled results (baseline `ls`, 498 windows × 4 portfolios)

| Strategy | median | adv med | adv mean | win vs LS | triggered | median wait | cash left |
|---|---:|---:|---:|---:|---:|---:|---:|
| ls | **190,301** | +0.0% | +0.0% | - | 100% | 0 | 0 |
| wait20_dca12 | 168,916 | **-1.3%** | -3.1% | **49%** | 99% | ~20-40mo | 4,422 |
| wait20_lump | 165,088 | -3.8% | -6.7% | 34% | 99% | ~20-40mo | 4,377 |
| wait20_tranches | 162,338 | -10.0% | -9.4% | 27% | 100% | ~3-16mo | 12,905 |
| wait30_lump | 126,841 | -30.9% | -18.8% | 34% | **54%** | 22-36mo | 15,309 |
| parked | 88,380 | -52.9% | -52.7% | 0% | 0% | - | 88,380 |

### The pure-stock exception (stocks_100)

| Strategy | median | adv med | adv mean | win vs LS |
|---|---:|---:|---:|---:|
| ls | 219,285 | +0.0% | +0.0% | - |
| **wait20_dca12** | **220,622** | **+11.0%** | **+9.3%** | **59%** |
| wait20_lump | 208,699 | +0.0% | -3.5% | 35% |

## Findings

1. **Crash-waiting pays only for 100% stocks and only in the DCA-after-crash
   form.** For stocks_100 the "wait for −20%, then DCA over 12 months" rule
   beats lump sum in **59% of windows and by +11% at the median** (+9.3% mean)
   — the only strategy in the entire program that beats LS on the mean.
   In balanced portfolios it loses (80/20 -2.0%, 60/40 -8.1%, GB -11.5% mean):
   their drawdowns are shallower and rebounds weaker, so the cash drag
   dominates.
2. **Don't wait for a −30% crash**: it simply doesn't come in 46% of windows
   (and never in the Golden Butterfly composite 2004+), leaving the money in
   cash: -18.8% mean pooled, -47% for GB.
3. **The drawdown-then-DCA shape matters**: deploying all at the trigger
   (wait20_lump: -6.7% mean) is worse than spreading the deployment over the
   following year (wait20_dca12: -3.1% mean; +9.3% stocks). Deep drawdowns can
   deepen (2008: -20% triggers, then -55% total), so drip-feeding after the
   trigger beats catching the falling knife — even in the strategy designed to
   avoid it.
4. **Never fully in cash (parked) is catastrophic** (-53%): the control shows
   why the emotional "cash is king" instinct must at least have a rule.
5. **Median waiting times are long** (20 months for stocks; 34-40 months for
   balanced portfolios): most of the time you sit out the early part of a bull
   market to buy a later correction. It worked in 2004-2026 mainly because
   corrections were frequent and V-shaped — a regime caveat worth stressing.

## Caveats

- Regime-dependent: 2004-2026 contains frequent sharp recoveries (2009, 2020)
  that reward buying after crashes; a secular bear (1929-1945 type) or a
  Japan-style long grind changes this.
- The 20% trigger is measured on the portfolio composite (2-year lookback);
  results are sensitive to the threshold and lookback.
- Same sample/cost/nominal-USD caveats as the parent studies.
