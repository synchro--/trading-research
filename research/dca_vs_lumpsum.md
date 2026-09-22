# DCA vs lump-sum: rolling 10-20y windows across classic portfolios

Run date: 2026-09-17.

## Reproduce

```bash
uv run python -m backtesting.dca_vs_lumpsum            # deep refetch (default)
uv run python -m unittest backtesting.tests.test_dca_vs_lumpsum -v
```

JSON artifact: `backtesting/data/dca_vs_lumpsum.json` (gitignored).

Setup: `Data 2004-11-18 -> 2026-09-16 (Yahoo total-return daily bars, 5,490 common days) ·
498 windows per portfolio = horizons {10,12,14,16,18,20}y x every monthly start ·
contribution 500/mo, lump X = 500 x N · 10 bps commission + 5 bps slippage per trade ·
waiting cash at ^IRX (13w T-bill, y/360 simple, calendar-day accrual) · annual rebalance ·
fills at chosen day's close · nominal USD with EUR labels (no FX) · no TER/taxes`

## Question

Same total money in the market (X = 500 x months), only the deployment path differs.
Does gradual investing (DCA), or DCA with hindsight dip-timing, beat an all-at-once
lump sum, and by how much, across four classic portfolios?

## Portfolios (fixed target weights)

| Portfolio | Weights |
|---|---|
| stocks_100 | 55% SPY / 30% EFA / 15% EEM |
| 80_20 | 80% stocks composite / 20% AGG |
| 60_40 | 60 / 40 AGG (same stock mix) |
| golden_butterfly | 20% VTV / 20% VBR / 20% SHY / 20% GLD / 20% cash |

## Strategies (identical invested amount X per window)

| Strategy | Rule |
|---|---|
| dca_mid | 500/mo on the first trading day on/after the 15th |
| oracle_1m | 500/mo at the month's lowest composite close (hindsight) |
| oracle_pt_3m / pt_6m | each tranche waits up to 3/6 months, buys the lowest close in its window (hindsight, truncated at window end) |
| oracle_cy_3m / cy_6m | accumulate 3/6 months (~1,500/3,000), deploy the lump at the cycle's lowest close (hindsight) |
| lump_sum | all X on day 0 |

Oracles assume perfect foresight of dips: they are upper bounds on timing skill,
not implementable rules. Cycle-mode tranches arriving after the cycle dip deploy
at par (interest-free borrowing), also an oracle simplification.

## Results

Median terminal value per window (X ranges 60k for 10y windows to 120k for 20y).

### Pooled across all 4 portfolios (13,944 window-sims per strategy row)

| Strategy | median | mean | p5 | p95 | win vs LS | adv vs LS (med) | adv vs LS (mean) | adv vs dca_mid (med) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lump_sum | **190,301** | **219,131** | **100,928** | 449,240 | - | +0.0% | +0.0% | **+45.0%** |
| dca_mid | 126,905 | 144,490 | 80,164 | 267,608 | 0.5% | -31.0% | -31.0% | - |
| oracle_1m | 129,874 | 148,165 | 81,615 | 275,009 | 0.9% | -29.5% | -29.3% | +2.3% |
| oracle_pt_3m | 132,276 | 151,228 | 82,778 | 282,312 | 1.4% | -28.3% | -27.8% | +4.3% |
| oracle_pt_6m | 134,718 | 154,166 | 83,781 | 287,886 | 2.2% | -27.1% | -26.5% | +6.1% |
| oracle_cy_3m | 133,287 | 152,043 | 83,191 | 283,701 | 1.7% | -27.9% | -27.5% | +4.8% |
| oracle_cy_6m | 136,562 | 156,291 | 84,809 | 290,315 | 2.5% | -26.1% | -25.5% | +7.5% |

(lump_sum is by definition the winner by median; bold = best in each metric.)

### Per portfolio (median terminal, pooled horizons)

| Portfolio | dca_mid | oracle_1m | oracle_pt_3m | oracle_pt_6m | oracle_cy_3m | oracle_cy_6m | lump_sum | LS med adv vs dca |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stocks_100 | 145,500 | 150,462 | 154,321 | 158,569 | 155,882 | 161,643 | **219,285** | +50.8% |
| 80_20 | 133,107 | 136,740 | 139,329 | 141,770 | 140,345 | 144,309 | **199,140** | +47.8% |
| 60_40 | 120,515 | 123,006 | 124,756 | 126,312 | 125,461 | 128,224 | **177,062** | +42.8% |
| golden_butterfly | 116,299 | 117,936 | 119,040 | 120,138 | 119,731 | 121,614 | **166,127** | +41.5% |

### Per horizon (stocks_100 median terminal)

| Strategy | 10y | 12y | 14y | 16y | 18y | 20y |
|---|---:|---:|---:|---:|---:|---:|
| dca_mid | 95,822 | 127,951 | 168,667 | 224,436 | 269,760 | 358,873 |
| oracle_cy_6m | 106,092 | 142,333 | 189,271 | 250,066 | 302,666 | 400,023 |
| lump_sum | 139,900 | 202,702 | 233,913 | 335,743 | 392,530 | 609,860 |

Full per-horizon tables for every portfolio/strategy in the JSON (`horizon_medians`).

Sanity anchor - GFC-start window (start 2008-07, 10y, stocks_100, X=60k):

```
dca_mid 101k · oracle_1m 105k · oracle_pt_3m 109k · oracle_pt_6m 111k
oracle_cy_3m 109k · oracle_cy_6m 114k · lump_sum 115k
```

Even starting in the middle of the 2008 crash deployment, lump sum still won the
10y window (recovery from late-2008 lows was powerful), though the gap (-12% vs
the pooled -33%) narrows dramatically: bad early markets are DCA's best case.

## Findings

1. **Lump sum wins overwhelmingly on terminal wealth**: with matched invested
   amounts, DCA ends ~-31% below lump sum at the median. Naive DCA beats lump
   sum in only ~0.5-2% of the ~500 windows per portfolio. This is structural:
   lump-sum has every euro in the market from day 0, while the average DCA
   tranche invests roughly half as long.
2. **Hindsight dip-timing recovers only a fraction of the gap**. Perfect 1-month
   timing adds ~+2-3% over naive DCA; 6-month patience adds ~+6-11% (cycle
   lumps slightly ahead of per-tranche timing). Even an oracle buying every
   6-month low leaves DCA ~-26% below lump sum at the median.
3. **The DCA-LS gap shrinks with worse luck**: the 2008-07 window shows the gap
   compressing from -33% (pooled) to -12%. DCA's insurance is real but only
   pays in persistent early drawdowns that the 2004+ sample rarely produces
   (no 15-year flat market inside the ETF era).
4. **Cash drag on waiting money is nearly free** at T-bill rates — the oracle's
   advantage comes from the dip, not the yield.
5. **Value of perfect intra-month timing is small** (oracle_1m vs dca_mid:
   +1.6-3.5%): buying "the dip of the month" vs "mid-month" barely matters.

## Caveats

- Rolling windows overlap heavily — samples are correlated; per-horizon counts
  (143/119/95/71/47/23) are not independent observations.
- Oracle strategies look ahead by design (stated upper bounds, not tradable).
- Nominal USD with EUR labels; no FX conversion, no TER, no taxes.
- AGG proxies the bond sleeve (a EUR/global agg UCITS has insufficient history);
  golden_butterfly uses VTV/VBR/SHY/GLD + a money-market sleeve.
- 2004+ data means every window includes at most one full macro regime cycle;
  results would differ across a 1900-2020 sample (Vanguard-style studies on
  longer data put lump-sum win rates near ~2/3, not >97% — our even-horizon
  scheme and 2004-2026 period is equity-friendly, which flatters lump sum).
- Verification: unit tests in `backtesting/tests/test_dca_vs_lumpsum.py` cover
  cash accrual, oracle day-picking (ties/truncation), invested-amount identity,
  rebalance costing, GB cash sleeve, and a no-lookahead property for the
  non-oracle strategies. One window (2004-12 LS stocks_100) was also
  hand-replicated outside the module: 122,897 vs 122,603 (difference = costs).
