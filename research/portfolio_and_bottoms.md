# Portfolio timing and ETF bottom-entry experiments

Run date: 2026-08-17. These are research results, not live-trading rules.

## Reproduce

```bash
python -m backtesting.portfolio
python -m backtesting.bottom_finder
python -m unittest discover -s backtesting/tests -v
```

Raw JSON is written under the gitignored `backtesting/data/` directory:

- `portfolio_comparison.json`
- `bottom_finder_comparison.json`

## 1. Basket selection comes after the policy

The selection rule is economic, not “the eight things that won recently”:

1. one liquid sleeve per distinct macro risk;
2. deep total-return history;
3. fixed equal policy weights;
4. one identical monthly timing rule per sleeve;
5. an inactive sleeve stays cash — it is not redistributed to recent winners.

Three baskets test the asset-selection decision:

| Basket | Sleeves | Purpose |
|---|---|---|
| Global 6 | SPY, EFA, EEM, IEF, GLD, DBC | US, developed ex-US, emerging markets, Treasuries, gold, broad commodities |
| Oil + transport 8 | Global 6 + XLE, IYT | Tests permanent energy-producer and transportation sleeves |
| Faber 5 | SPY, EFA, IEF, DBC, VNQ | Close ETF proxies for Faber's original five asset classes |

All portfolios rebalance monthly, use next-open fills, charge 10 bps commission
plus 5 bps slippage, and assign cash a 0% return.

### Results, common window 2007-02-07 to 2026-08-13

| Basket | Policy | Sharpe | CAGR | Vol | Max DD | Calmar | Avg invested |
|---|---|---:|---:|---:|---:|---:|---:|
| Global 6 | Static equal weight | 0.56 | 6.8% | 13.3% | 39.7% | 0.17 | 100% |
| Global 6 | Faber monthly | 0.66 | 5.2% | 8.3% | 14.6% | 0.36 | 67% |
| Global 6 | TSMOM 12-month | 0.66 | 5.4% | 8.5% | 16.8% | 0.32 | 67% |
| **Global 6** | **Dual confirm** | **0.69** | 4.9% | **7.4%** | **9.7%** | **0.51** | 57% |
| Oil + transport 8 | Static equal weight | 0.55 | 7.4% | 15.3% | 44.1% | 0.17 | 100% |
| Oil + transport 8 | Faber monthly | 0.63 | 5.4% | 9.0% | 16.4% | 0.33 | 67% |
| Oil + transport 8 | TSMOM 12-month | 0.63 | 5.6% | 9.3% | 19.7% | 0.28 | 67% |
| Oil + transport 8 | Dual confirm | 0.62 | 4.8% | 8.0% | 15.1% | 0.32 | 57% |
| Faber 5 | Static equal weight | 0.48 | 6.0% | 14.4% | 47.1% | 0.13 | 100% |
| Faber 5 | Faber monthly | 0.55 | 4.2% | 8.1% | 17.3% | 0.24 | 68% |
| Faber 5 | TSMOM 12-month | 0.55 | 4.5% | 8.8% | 22.8% | 0.20 | 68% |
| Faber 5 | Dual confirm | 0.64 | 4.3% | 7.0% | 13.1% | 0.33 | 58% |

`dual_confirm` invests a sleeve only when both:

- close is above its trailing 200-day SMA; and
- its trailing 252-day return is positive.

The signal is evaluated at the prior month-end close and filled at the next
monthly open.

### Oil, transportation, Trump, and Iran

There is no oil/transport event strategy or Trump/Iran tweet dataset in this
repository, including git history. XLE and IYT were therefore tested as transparent
economic sleeves, not as a reconstructed news strategy.

They increased static CAGR but worsened volatility and drawdown enough to lower
Sharpe. They also reduced risk-adjusted performance under all three timing policies.
Do not add them permanently to the strategic core on this evidence.

A defensible event strategy is a separate project. It requires:

- archived text with original publication timestamps and edits/deletions;
- prices synchronized to whether the event occurred during or outside market hours;
- a frozen event taxonomy and sentiment classifier built without future outcomes;
- explicit rules for duplicate headlines, rumors, official confirmation, and
  untradeable overnight gaps;
- an event-study baseline before a trading backtest.

Without those inputs, “Trump tweet” and “Iran war” rules are hindsight narratives.

## 2. ETF Bottom Finder

The experiment covers 29 ETFs:

- Broad development cohort: SPY, DIA, IWM, VTI, EFA, VEA, EEM, VWO, VT, ACWI, URTH.
- Held-out validation cohort: QQQ, SMH, XLK, XBI, IBB, XLF, XLE, XLI, XLY,
  XLP, XLV, XLU, IYT, VNQ, GLD, TLT, AGG, DBC.

Rules are weekly, signals fill at the next week's open, and a 26-week cooldown
prevents one crash from being counted as many independent opportunities. The
future local low is used only for evaluation, never for the signal.

### Metrics

- Bottom distance: entry / minimum low in the surrounding ±13 weeks − 1.
- After bottom: fraction whose entry is not before that local low.
- 13-week MAE: worst post-entry low over 13 weeks.
- 52-week excess: signal return minus the same ETF's unconditional median
  one-year return from an ordinary eligible week.

### All-ETF results

| Weekly rule | Signals | Within 10% of low | After low | 13w MAE | 52w return | 52w excess | Win rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Current Pine: 200w / 250w + reclaim** | 200 | 35.5% | **72.5%** | **-4.8%** | 14.9% | +6.1% | **78.9%** |
| Balanced: 40w / 52w + reclaim | 375 | 31.7% | 61.9% | -6.7% | 13.0% | +3.6% | 73.7% |
| RSI reclaim only | 263 | 35.0% | 54.4% | -6.8% | 12.7% | +3.6% | 75.9% |
| 40-week SMA reclaim | 203 | 14.8% | 85.2% | -5.9% | 13.5% | +3.0% | 70.1% |
| 20% DD + deep RSI reclaim | 96 | 10.4% | 56.2% | -10.9% | 17.8% | +6.4% | 78.1% |
| First cross into 20% drawdown | 218 | **55.0%** | 40.4% | -6.7% | 17.1% | +6.4% | 74.7% |

### Conclusion

Keep the current Pine rule for a single lump sum:

- price at or below `1.03 × SMA(200)` on the weekly chart;
- at least 10% below the 250-week peak;
- then either RSI recovery after an oversold sweep or a reclaim of SMA200.

It does not buy the exact low. Its median entry is 12.6% above the surrounding
trough. That is the cost of confirmation. It is the best balance because it:

- arrives after the low 72.5% of the time;
- has the smallest immediate adverse excursion;
- produces +6.1% median one-year uplift over an ordinary week;
- behaves similarly on broad ETFs (+5.6%) and held-out sectors (+6.7%);
- keeps nearly the same win rate before and after 2013.

Temporal caveat: its one-year excess return was -0.4% before 2013 and +8.4%
afterward, even though the win rate stayed near 79% in both periods. “Best” means
the safest confirmation/local-low balance among the rules tested, not proven
market-beating timing in every regime.

The raw 20% drawdown cross is closer to the exact low but is still early 60% of the
time, and its pre-2013 excess return was -2.7%. That is a post-GFC buy-the-dip rule,
not a stable confirmation rule.
