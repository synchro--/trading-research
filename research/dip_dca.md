# DCA timing study II: oracles vs mid-month DCA + "2x on red running-low" rule

Run date: 2026-09-17. Companion to `dca_vs_lumpsum.md` (lump sum removed here).

## Reproduce

```bash
uv run python -m backtesting.dip_dca --reuse-cache
uv run python -m unittest backtesting.tests.test_dip_dca -v
```

JSON artifact: `backtesting/data/dip_dca.json` (gitignored).

Setup (same engine/data/windows as the parent study, lump sum excluded):
`Data 2004-11-18 -> 2026-09-16 · 498 windows per portfolio = {10,12,14,16,18,20}y x
every monthly start · 500/mo · 10 bps + 5 bps costs · waiting cash at ^IRX ·
annual rebalance · fills at chosen day's close · nominal USD, EUR labels`

## Strategies

| Strategy | Rule | Lookahead? |
|---|---|---|
| dca_mid | 500/mo at first trading day on/after the 15th | no |
| dip_shift | on the month's first **red running-low** day (close = new monthly minimum AND below prior trading day), buy the normal 500 there instead of mid-month | no |
| dip_double | same trigger, but doubles that month's contribution (1000 on the trigger day instead of 500 mid-month) | no |
| oracle_1m / pt_3m / pt_6m / cy_3m / cy_6m | hindsight benchmarks from the parent study | yes (by design) |

Key stats: absolute terminal advantage vs dca_mid AND **EUR-for-EUR timing
return** (terminal / nominal invested). dip_double invests more capital by
construction (median 134.5k vs 72k per window), so only the EUR-for-EUR columns
answer "is the timing skill real"; the absolute columns answer "will I end up
richer putting twice as much in".

## Results — pooled across 4 portfolios, 1,992 window-sims per strategy

| Strategy | win>dca | adv vs dca (med) | EUR-for-EUR (med) | EUR-for-EUR (mean) | median invested |
|---|---:|---:|---:|---:|---:|
| dca_mid (baseline) | - | +0.0% | +0.0% | +0.0% | 72,000 |
| dip_shift | 59% | +0.0% | **+0.0%** | **+0.0%** | 72,000 |
| dip_double | 100% | +86.0%* | +0.3% | +0.3% | 136,500 |
| oracle_1m | 100% | +2.3% | +2.3% | +2.4% | 72,000 |
| oracle_pt_3m | 100% | +4.3% | +4.3% | +4.5% | 72,000 |
| oracle_pt_6m | 100% | +6.1% | +6.1% | +6.4% | 72,000 |
| oracle_cy_3m | 100% | +4.8% | +4.8% | +5.0% | 72,000 |
| oracle_cy_6m | 100% | +7.5% | +7.5% | +7.8% | 72,000 |

*dip_double's +86% is almost entirely the doubled budget (invested 136.5k vs
72k); see EUR-for-EUR +0.3%.

### Per portfolio — EUR-for-EUR median advantage vs dca_mid

| Portfolio | dip_shift | dip_double | oracle_1m | pt_3m | pt_6m | cy_3m | cy_6m |
|---|---:|---:|---:|---:|---:|---:|---:|
| stocks_100 | -0.1% | +0.0% | +3.5% | +6.7% | +9.7% | +7.3% | +11.2% |
| 80_20 | -0.1% | +0.3% | +2.8% | +5.2% | +7.5% | +5.8% | +9.0% |
| 60_40 | -0.0% | +0.4% | +2.1% | +3.8% | +5.4% | +4.3% | +6.8% |
| golden_butterfly | +0.1% | +0.3% | +1.6% | +2.7% | +3.7% | +3.2% | +5.0% |

### Why the dip rule does nothing (trigger diagnostics)

The "red + running low of the month" condition fires in **85% of all months** —
it is barely a filter:

- 44% of triggers land on the **first trading day of the month** (day 1 is
  trivially a running low), 29% on day 2, 10% on day 3 → 83% within the first
  3 days.
- So the rule mostly degenerates to "invest near the month's open instead of
  mid-month", and those prices are not systematically lower — dip_shift ends
  inside noise of dca_mid (median 0.0%, win rate 44-98%, ~coin flip).
- The trigger rate is high because any small overnight gap down during the
  first days of a month qualifies: perpetual dips are ubiquitous, and buying
  them within the month is not the same as buying MEANINGFUL dips.

### dip_double (2x capital in dip months) specifics

- Median raised capital: +89% (+86% to +91% per portfolio range: invests ~1.87x
  median across windows). Its absolute terminal advantage ~+86-89% tracks that
  extra capital almost exactly.
- The tiny EUR-for-EUR premium (+0.1-0.4%) means doubling into red monthly
  running lows buys ~2x the risky exposure at roughly average prices for the
  month — a mild value-averaging effect, not a dip-buying edge.
- If you want that effect, understand it as "invest 2x as much, so you end with
  ~1.9x", not as timing skill: risk scales up with it (p5-p95 spreads scale up
  similarly).

## Findings

1. **The implementable signal captures ~none of the oracle's edge.** Perfect
   monthly-low knowledge is worth +2.3% (oracle_1m), but naive "red running
   low" timing is worth +0.0% (dip_shift, 59% pooled win rate): predicted
   overlap ≈ 0. Verified directly by the trigger diagnostics (83% of triggers
   in the first 3 days of the month).
2. **Even the oracle edge shrinks under capital matching**: with matched
   invested amounts, all of the oracle advantage vs dca comes from price dips,
   not capital size: oracle_1m +2.3% → cy_6m +7.5% (median per-euro).
3. **Scaling the contribution on red low days adds capital, not alpha.**
   dip_double vs dca_mid: +86% absolute vs +0.3% EUR-for-EUR. Same "dip-2x"
   per € performs like plain DCA.
4. **Tighter dip definitions could improve the implementable rule** (require a
   deeper drop, e.g., close ≤ 95% of month high so far, or trigger only after
   day 5; the current rule is too easy to satisfy). This study bounds what
   "check every day, buy at running lows" can plausibly add: order +0%, i.e.
   indistinguishable from picking a random day of the month.

## Round 2 (2026-09-17): deeper trigger + capital shifting

User refinement of the rule: the trigger stays "red + new monthly running low"
but additionally requires the composite to be **≥3% below its rolling
20-market-day high**; and the capital model becomes "double this month, half
the month after" (triggered month deploys 1000, the following month only 250;
a triggered month after a trigger chains the haircut forward). Two variants:
`dip2x_half` (as described) and `dip2x_neutral` (budget-neutral control: the
following month pays back the full 500 and deploys 0).

### Trigger diagnostics (v2 filter works)

- Trigger rate drops from **85% → 55%** (stocks_100; 39-50% for the
  bond-heavy portfolios).
- Day-of-month distribution: 26% on day 1, 16% day 2, 10% day 3 (was
  44/29/10) — still front-loaded, but now those days are real ≥3% drawdowns.

### Results — pooled across 4 portfolios (baseline dca_mid)

| Strategy | win>dca | adv med | adv mean | EUR-for-EUR med | EUR-for-EUR mean | median invested |
|---|---:|---:|---:|---:|---:|---:|
| dca_mid | - | +0.0% | +0.0% | +0.0% | +0.0% | 72,000 |
| dip_shift (v1) | 59% | +0.0% | +0.0% | **+0.0%** | **+0.0%** | 72,000 |
| dip_double_v1 (85% trig) | 100% | +74.3% | +74.7% | +0.6% | +0.6% | 129,500 |
| **dip2x_half** (50% stocks trig) | 100% | **+39.5%** | +39.9% | **+1.7%** | +1.5% | 104,750 |
| dip2x_neutral (50% trig) | 100% | +48.5% | +48.7% | +1.5% | +1.4% | 111,750 |
| oracle_1m (hindsight) | 100% | +2.3% | +2.4% | +2.3% | +2.4% | 72,000 |
| oracle_pt_6m (hindsight) | 100% | +6.1% | +6.4% | +6.1% | +6.4% | 72,000 |
| oracle_cy_6m (hindsight) | 100% | +7.5% | +7.8% | +7.5% | +7.8% | 72,000 |

Per-portfolio EUR-for-EUR median advantage vs dca_mid:

| Portfolio | dip_double_v1 | dip2x_half | dip2x_neutral | oracle_1m | oracle_cy_6m |
|---|---:|---:|---:|---:|---:|
| stocks_100 | +0.0% | +1.6% | +0.3% | +3.5% | +11.2% |
| 80_20 | +0.7% | +1.6% | +1.5% | +2.8% | +9.0% |
| 60_40 | +0.8% | +1.8% | +1.6% | +2.1% | +6.8% |
| golden_butterfly | +0.4% | +1.5% | +1.3% | +1.6% | +5.0% |

(old dip_shift column dropped above for width; it was ~0.0% everywhere.)

### Round-2 findings

1. **The −3%/20-day filter does the real work**: EUR-for-EUR edge of the
   implementable rule roughly triples, from +0.6% (v1 2x, no haircut) to
   **+1.7% (dip2x_half)** pooled. The trigger rate falls 85% → 55% (stocks).
2. **The budget-shift ("half the month after") is profitable but modest**:
   dip2x_half per-euro +1.7% ≈ dip2x_neutral (+1.5%) — the haircut mechanics
   add no magic; the improvement comes from the trigger, not the repayment
   structure. dip2x's +1.7% still captures only ~1/4 of what pure hindsight
   monthly dip knowledge buys (+2.3% for oracle_1m, unchanged from round 1).
3. **Capital still does most of the +39.5%**: dip2x_half invests ~1.45x the
   median capital (104.75k vs 72k). Absolute terminal advantage tracks capital
   size; the honest timing skill proxy remains the EUR-for-EUR column.
## Round 3 (2026-09-17): tighter triggers + cycle-lump implementable rule

Three refinements of the winning v2 rule (capital unchanged: 2x on trigger,
0.5x the month after):

- `dip2x_5pct15d` — deeper/wider trigger: ≥5% dip vs the 15-market-day high.
- `dip2x_consec2` — fires only on the 2nd consecutive red running-low day.
- `dip6m_deep` — cycle analogue of the 6-month oracle: inside each 6-month
  cycle, every deep (−3%/20d) red running-low day deploys the cash
  accumulated so far in the cycle; leftovers deploy at the mid of the cycle's
  last month. Strictly budget-neutral (invested == 500xN exactly).

### Results — pooled (baseline dca_mid)

| Strategy | trigger rate | adv med | adv mean | EUR-for-EUR med | EUR-for-EUR mean | median invested |
|---|---:|---:|---:|---:|---:|---:|
| dca_mid | - | +0.0% | +0.0% | +0.0% | +0.0% | 72,000 |
| dip2x_half (3%/20d) | 50% (stocks) | +39.5% | +39.9% | **+1.7%** | +1.5% | 104,750 |
| dip2x_neutral | 50% | +48.5% | +48.7% | +1.5% | +1.4% | 111,750 |
| **dip2x_5pct15d** | 24% (stocks) | **+16.3%** | +19.0% | **+1.6%** | +1.8% | 89,500 |
| dip2x_consec2 | 28% (stocks) | +20.2% | +21.7% | +1.4% | +1.3% | 91,250 |
| dip6m_deep | 24% (stocks) | -0.3% | -0.4% | **-0.3%** | -0.4% | 72,000 |
| oracle_1m | - | +2.3% | +2.4% | +2.3% | +2.4% | 72,000 |
| oracle_cy_6m | - | +7.5% | +7.8% | +7.5% | +7.8% | 72,000 |

### Round-3 findings

1. **A deeper trigger is NOT free — it trades frequency for depth.** −5%/15d
   halves the trigger budget shift (invested only ~89.5k vs 104.75k median)
   and keeps per-euro timing at +1.6% (mean +1.8%, the best mean among
   implementable rules) — roughly the same timing skill as dip2x_half but with
   3.5% fewer trigger months and less extra capital. If maximizing terminal
   wealth per shrinking savings rate matters, dip2x_half remains the best
   implementable rule at ~+1.7%.
2. **Requiring 2 consecutive red running-lows adds nothing** (+1.4% pooled,
   and worse on the 60_40 + GB portfolios): the second-day confirmation
   arrives after the dip and mostly buys mid-month-like prices.
3. **The cycle version (dip6m_deep) is a real negative** (−0.3% per-euro,
   13% win rate): without hindsight, waiting for cycle lows within a
   falling 6-month cycle buys *inside* persistent downtrends and delays
   capital — the opposite of what hindsight oracle_cy_6m (+7.5%) exploits.
   Implementable dip-timing has a ceiling around +2%.


4. GFC anchor (2008-07 start, 10y, stocks_100): v1 triggers 102/120 months,
   v2 68/120, 5%/15d 41, consec2 46, cycle version 36. dip2x_half ends 154.5k
   on 88.25k invested vs dca_mid 101.2k on 60k — again mostly capital.

## Pure-stock portfolio (stocks_100) — does volatility scale the edge?

stocks_100 (55% SPY / 30% EFA / 15% EEM) vs the pooled average:

| Strategy | EUre-for-EURe med (stocks) | EUR-for-EUR med (pooled) | ratio | oracle bound (stocks) |
|---|---:|---:|---:|---:|
| dip2x_half | +2.0% | +1.7% | ~1.2x | - |
| **dip2x_5pct15d** | **+3.4%** | +1.6% | **~2.1x** | - |
| dip2x_consec2 | +2.0% | +1.4% | ~1.4x | - |
| dip6m_deep | -0.5% | -0.3% | - | - |
| oracle_1m | +3.5% | +2.3% | ~1.5x | same |
| oracle_cy_6m | +11.2% | +7.5% | ~1.5x | same |

A pure stock portfolio roughly **scales the timing edge up ~1.5-2x** across the
board (more volatile composite = deeper, more exploitable dips), and the
sharper −5%/15d trigger benefits most: +3.4% median / +3.1% mean EUR-for-EUR
— the best implementable result of the whole study. The negative cycle rule
degrades further (-0.5%). Even so, +3.4% remains modest vs the hindsight
cy_6m bound (+11.2%), and the absolute terminal advantage is still mostly
extra capital (+31.7% abs for dip2x_5pct15d).

## Three-round conclusion


| Rule tier | Best per-euro timing edge (pooled, med) | Mechanism |
|---|---:|---|
| Perfect foresight of 6-month lows (oracle) | +7.5% | hindsight |
| Perfect foresight of monthly lows (oracle) | +2.3% | hindsight |
| Implementable:"2x on deep red monthly low, half next month" | **+1.7%** | −3%/20d trigger |
| Naive DCA (mid-month) | +0.0% | baseline |

Even with the best implementable trigger, per-euro timing returns only ~1.7%;
absolute benefits are dominated by any extra capital invested, and all
implementable dip rules remain well below the hindsight bounds.



## Caveats

- Same overlapping-window sample-size caveats as the parent study.
- dip_double comparisons are apples-to-oranges on terminal wealth by design
  (extra capital); use the EUR-for-EUR columns for skill, absolute columns for
  wealth-in-the-bank.
- Oracles are hindsight upper bounds; dip_shift/dip_double are implementable
  (decisions use only information up to the current day).
- GFC sanity anchor (2008-07, 10y, stocks_100): dip triggers 102/120 months;
  dip_shift 101.0k vs dca_mid 101.2k (same); dip_double 187.1k on 111k invested.
- Verification: trigger-logic unit tests (falling/rising/flat months, one-shot
  first-trigger, month-open gap-down), invested amounts identity for dip_shift,
  flat-market equivalence of all three DCA variants, and single-window
  hand-checks of trigger-day pricing.
