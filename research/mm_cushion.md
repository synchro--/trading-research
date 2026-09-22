# Money-market cushion study: 30k reserve + 500/mo, four allocation policies

Run date: 2026-09-17. Companion to `dca_vs_lumpsum.md` and `dip_dca.md`.

## Reproduce

```bash
uv run python -m backtesting.mm_cushion --reuse-cache
uv run python -m unittest backtesting.tests.test_mm_cushion -v
```

JSON artifact: `backtesting/data/mm_cushion.json` (gitignored).

Setup: same data/engine/windows as the parent studies (Yahoo total-return daily
bars 2004-11-18 -> 2026-09-16 · 498 windows per portfolio = {10,12,14,16,18,20}y
x every monthly start · 10 bps + 5 bps costs · fills at close · nominal USD
with EUR labels). The reserve earns simple T-bill interest (^IRX, y/360,
calendar-day accrual) — the nominal-USD proxy for a EUR XEON/conto-deposito
money-market fund. golden_butterfly keeps its internal 20% cash sleeve on top.

## Budget equality (the arithmetic)

Every approach receives the identical pools over every window:

- **30k** available at the window start (the reserve/XEON bucket), and
- **500/month** external income for N months (60k over a 10y window, 120k over 20y).

So total budget/commitment is exactly equal, 30k + 500xN; the four approaches
only differ in how that money is held and deployed:

1. `lump_sum_30k` — reserve invested at day 0; each incoming 500 invested on
   arrival (mid-month). Zero idle cash after day 0. Equities get the full
   30k + 500xN.
2. `dca_cushion` — 500/mo mid-month; the reserve sits untouched in the MMF
   the whole window (equities get only 500xN; MMF accrues interest).
3. `oracle_cushion` — as (2), but each month's 500 buys at the month's lowest
   close (hindsight; benchmark for the implementable rule below).
4. `dip2x_mm` — 500/mo normally; when an ETF day is red (below prev close)
   AND >= 3% below the previous-30-day rolling high AND within the first two
   weeks of the month, that month deploys 1000 that day: the monthly 500 plus
   an extra 500 **drawn from the reserve**. The draw is capped at the MMF
   balance. Total budget unchanged — the reserve depletes as it funds
   dip-buys ("less will be in the money-market fund").

## Results — pooled across 4 portfolios, 1,992 window-sims per strategy

| Strategy | median total | eq invested med | MMF left (med) | win vs LS | adv vs LS (med) |
|---|---:|---:|---:|---:|---:|
| lump_sum_30k | **201,750** | 102,000 | 0 | - | +0.0% |
| dca_cushion | 160,801 | 72,000 | 34,524 | 0% | -18.0% |
| oracle_cushion | 163,838 | 72,000 | 34,524 | 0% | -16.5% |
| dip2x_mm | 179,094 | 102,624 | 5,161 | 6% | -9.8% |

Per portfolio (median totals; derived head-to-heads):

| Portfolio | LS | dca | oracle | dip2x | dip vs dca | dip vs LS |
|---|---:|---:|---:|---:|---:|---:|
| stocks_100 | 234,278 | 180,369 | 185,859 | 211,290 | **+17.1%** | -9.8% |
| 80_20 | 213,288 | 168,220 | 171,803 | 189,806 | **+12.8%** | -11.0% |
| 60_40 | 191,984 | 154,673 | 156,980 | 165,262 | **+6.8%** | -13.9% |
| golden_butterfly | 182,074 | 152,638 | 154,375 | 161,837 | **+6.0%** | -11.1% |

Trigger activity for `dip2x_mm`: 41% of months (stocks_100), 29-37% on the
bond-heavy portfolios. Median MMF leftover at window end: ~5k (stocks) to
~11k (60/40, GB) — the reserve is mostly consumed, roughly fully deployed
into equities by the end of long windows. One caveat note: for windows where
the reserve was fully consumed early, the later years of `dip2x_mm` reduce to
plain DCA.

Sanity anchor — 2008-07 start, 10y, stocks_100 (X=60k + 30k reserve):

```
lump_sum 158.6k · dca_cushion 132.1k (MMF 30.9k intact) ·
oracle_cushion 136.1k · dip2x_mm 156.7k (MMF 1.8k left, 57 draws of 28.5k)
```

In a crash decade the dip-withdrawal rule nearly closes the gap to lump sum
(-1.2%), while the parked cushion trails by -17%.

## Findings

1. **Holding a 30k cash buffer for 10-20y is expensive**: the cushion
   approaches end 16.5-18% below the pure lump-sum deployment of the same
   budget. The buffer is a big deal at these sizes (30k vs 500/mo).
2. **Harvesting the buffer into equities on dip days recovers roughly HALF of
   that drag**: dip2x_mm cuts the LS gap from ≈ -18% to ≈ -10% pooled, and
   beats the parked-cushion DCA by **+6.0-17.1% median** (more on
   stock-heavy portfolios: +17.1% stocks_100, +12.8% on 80/20).
   It even modifies the LS comparison: dip2x lands within 6.0-13.9% of lump
   sum instead of 16.6-21.2%.
3. **Within the same budget, the trigger is doing real work here**: approach
   (4) vs (2) differ ONLY in the reserve treatment (parked vs harvested on
   the -3%/30d/+first-2-weeks trigger). A +6-17% median total-wealth
   difference from an implementable rule is far more than the ~0-2% timing
   edges of the earlier matched-capital studies — because this rule
   reallocates *capital* toward drawdown months, not just timing.
4. Oracle vs naive DCA deployment (+1.5pp) confirms once more that perfect
   monthly dip knowledge is a small part of the puzzle; capital structure is
   the bigger lever.
5. Even so, none of the cushion approaches historically beat simply
   investing the reserve at day 0: lump_sum_30k wins everywhere (win rates
   0-20%). The dip rule's best realistic role: a compromise for savers who
   insist on a liquid buffer — it degrades the cushion's cash drag by
   deploying ~80-97% of it into equities at drawdowns instead of never.
6. Practical note: dip2x_mm better resembles what a real saver can execute:
   classic DCA plus opportunistic withdrawal from the buffer during
   drawdowns — the liquidity reserve shrinks over time though, which
   contradicts the emergency-fund purpose of the buffer. The empirical
   wealth premium (+6-17% median vs parked) is the price paid in liquidity.

## Caveats

- Same overlapping-window caveats as parent studies; the sample (2004+) is
  equity-friendly, flattering lump sum.
- The reserve yield is a USD T-bill proxy; a real EUR XEON/conto deposito
  yields differently (about similar magnitude most of the era, but the
  2015-2021 ZIRP nearly killed MMF yields in EUR too).
- Oracles use hindsight by design; dip2x_mm is implementable (all decisions
  use information up to the current day).
- Approach (4)'s draws are capped at the MMF balance; a fully-drawn reserve
  degrades to plain mid-month DCA (visible in the MMF-left medians).
- FX ignored (nominal USD, EUR labels); no TER/taxes; fills at close.
- Verification: unit tests cover trigger rules (depth gate, first-two-weeks
  gate, red gate), reserve drainage and cap clamps, budget identities, and
  flat-market expectations across the four approaches.
