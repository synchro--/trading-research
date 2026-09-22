# Deep history: lump sum vs DCA on US data since 1926

Run date: 2026-09-17. Companion to `dca_master_report.md`.

## Reproduce

```bash
uv run python -m backtesting.deep_history          # fetches once, then cached
uv run python -m unittest backtesting.tests.test_deep_history -v
```

JSON: `backtesting/data/deep/deep_history.json`. Raw open data cached in
`backtesting/data/deep/` (Ken French daily factor zip, FRED DGS10 csv).

**Data** (all open, no API key):
- **US equity total return + cash**: Ken French daily research factors
  (Mkt-RF + RF = market total return; RF = 1-month bill) from **1926-07-01**
  to 2026-07-31 (26,296 trading days). This is the canonical academic CRSP
  value-weighted series with dividends — accumulation-equivalent.
- **US 10y Treasury total return**: FRED `DGS10` (daily, from 1962), synthesized
  with monthly returns `y_{m-1}/12 − D·Δy`, modified duration D = 8 (FRED has
  no open total-return bond series).
- Gold has no open daily pre-2004 history anymore (Stooq is behind a bot wall,
  FRED's LBMA series is discontinued), so golden-butterfly style portfolios are
  not extended here — this study is US stocks and stocks/bonds only.

**Portfolios**: stocks_100 (1,082 ten-year windows), 80_20 and 60_40 (655
windows each, from 1962). Strategies: lump_sum, dca_mid, oracle_1m,
oracle_cy_6m — identical engines and X = 500 × months as the modern studies.

![deep history](plots/h1_deep_history.png)

## Results — stocks_100, per horizon

| Horizon | n | LS median | dca adv med | dca adv mean | dca win | oracle_cy_6m adv med | oracle win |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10y | 1,082 | 171,136 | -38.6% | -30.8% | **8%** | -32.4% | 14% |
| 12y | 1,058 | 248,722 | -43.7% | -35.6% | 6% | -38.0% | 11% |
| 14y | 1,034 | 348,599 | -46.9% | -39.8% | 6% | -41.4% | 9% |
| 16y | 1,010 | 470,762 | -49.8% | -43.7% | 4% | -44.5% | 7% |
| 18y | 986 | 670,142 | -52.6% | -47.2% | 4% | -47.5% | 6% |
| 20y | 962 | 930,885 | -56.1% | -51.0% | 4% | -51.5% | 5% |

`dca_full`-style win rates rise from **0.5% (2004-2026 sample) to 8% (1926+)**,
and the number of DCA-win windows explodes from 9 to **388** — almost all of
them starting **1929-01 to 1930-09** (the Great Depression entries), where DCA
beat lump sum by **+50% to +127%**. Mean advantage by start decade (stocks,
all horizons): 1920s +23%, 1930s -29%, 1940s -54%, 1950s -54%, 1960s -33%,
1970s -56%, 1980s -57%, 1990s -51%, 2000s -29%, 2010s -57%.

## Findings

1. **The deep sample is *worse* for DCA on the median, better on the tail**:
   median disadvantage grows from -31% (2004+) to -38.6% (10y, 1926+) because
   of the post-WWII bull; but DCA's win frequency rises 16x (0.5% → 8%)
   because the Great Depression finally supplies the scenario the modern
   sample lacks: a lost decade *immediately after* the deployment starts.
2. **The 1929-1940 cohort is the complete DCA case study**: starting in 1929
   and DCA-ing through the crash beats lump-sum-at-the-top by 50-127% at every
   horizon from 10 to 18 years. This is exactly the "LS deployed during a bear
   market" question from §5, now with the sample that can answer it — but even
   here it requires starting *at the top*, not "during the bear".
3. **Hindsight dip-timing still only recovers part of the gap**: the 6-month
   oracle improves the median by ~6pp in 10y windows (-38.6% → -32.4%) and
   raises win frequency to 14% — more than in the modern sample, because deeper
   drawdowns give patience more to work with.
4. **Vanguard reconciliation**: Vanguard's "LS beats 12-month DCA ~2/3 of the
   time" is about *staged* deployment, not 100-month DCA. Our 12-month hybrids
   lose the same ~2/3 (hybrid_split.md), while full-window DCA loses ~92-99%
   of windows. Different questions, consistent answers.
5. **Bonds soften everything** (60/40: dca adv med -27.6% at 10y vs -38.6% for
   stocks) — lower volatility, lower opportunity cost of waiting.

## Caveats

- US-only (no open long-run daily EFA/EEM/gold data); nominal USD.
- Bond sleeve is a duration approximation (D = 8, monthly steps), acceptable
  for 60/40-style sleeves but not a true index.
- French daily factors are CRSP value-weighted and exclude the pre-1926 era
  (no 1900-1925 sample).
- Overlapping windows: 1,082 ten-year windows are ~90 independent decades.
- The pre-1950 sample includes structural changes (fixed commissions,
  different market composition); treat magnitudes as indicative.
