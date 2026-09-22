# Leverage, month-low dip trading and taxable swing trading vs DCA / lump sum

Run date: 2026-09-20. Module: `backtesting/lever_tax_swing.py` ·
JSON: `backtesting/data/lever_tax_swing.json` · reproduce:
`uv run python -m backtesting.lever_tax_swing --reuse-cache`

Setup: SPY total-return daily bars (Yahoo, 2004-11-18 → 2026-09-16, 5,503 days) as the
"global index" proxy · 10 bps commission + 5 bps slippage per leg · waiting cash earns
^IRX (13w T-bill, simple y/360) · fills at close, signals T+1 · windows = every monthly
start 2004-12 → horizons {10,12,14,16,18,20}y (498 windows total: 143/119/95/71/47/23) ·
identical money in every strategy: lump X = 500 × N months; DCA/oracle/swing contribute
500/mo · no parameter fitting (leverage 2x/3x, 20% tranche, SMA200, 26% tax are all
prior-specification values).

## 1. Falsifiable hypothesis

H1: if one is convinced the index trends up, holding a daily-reset 2x/3x leveraged
index product increases terminal wealth at the same horizon without ruin.
Support = median terminal > 1x with acceptable p5 and no blow-up windows; rejection =
median ≤ 1x, or drawdown/terminal failure worse than 1x in a majority of windows.

H2: timing monthly contributions to each month's lowest close (hindsight oracle,
20% tranches) or tradably via an SMA200 + first-MTD-negative rule beats plain
monthly DCA. Support = median terminal > DCA and win-rate vs DCA > 50%.

H3: repeatedly flipping cash→index→cash in a taxable account "a lot for 20 years"
is viable in Italy despite 26% tax on realized gains. Support = taxed swing terminal
≥ sheltered version − small drag (say < 5% relative).

## 2. Leakage controls

- Look-ahead: all tradable signals use close data through day t and execute T+1 close
  (SMA200 regime, MTD-negative tranches). The ONLY strategies intentionally using
  future info are flagged `oracle_*` (dip day known only in hindsight) — they are
  upper bounds, matching the conventions of the earlier dca reports.
- Survivorship: single ETF (SPY) plus simulated leveraged paths — SPY itself cannot
  be selected ex post among survivors; the SSO/UPRO cross-check below validates the
  simulation against the real funds.
- Split: no parameter is estimated, so there is no train/test split to contaminate.
  Robustness is instead checked by cohort of window start year (2004-09 / 2010-14 /
  2015-20) and by horizon — chronological, never random.
- Target leakage: none — no ML model, no features fitted on labels.
- Leveraged-path simulation: r_lev = lev*r − (lev−1)*rf/252 − (ER + (lev−1)*borrow)/252.
  Calibration against the real ETFs' last 10y: SSO real 23.9% vs sim 23.3% CAGR, vol
  36.2% vs 36.2%; UPRO real 29.6% vs sim 28.9%, vol 54.6% both. Sim slightly
  conservative; no borrowing-margin-call modelling beyond the path reset.

## 3. Results — pooled over all 498 windows (terminal €, contributions 500/mo)

| Strategy | median | p5 | p95 | win vs LS | adv vs LS med | med maxDD | trades/win |
|---|---:|---:|---:|---:|---:|---:|---:|
| ls_1x (lump) | 328,597 | 124,933 | 879,140 | — | — | 55% | 1/0 |
| ls_2x | 624,009 | 135,979 | 2,247,486 | 99% | +86.9% | 84% | 1/0 |
| ls_3x | 843,198 | 104,179 | 4,770,683 | 89% | +131.9% | **96%** | 1/0 |
| dca_1x | 184,124 | 105,596 | 462,220 | 0% | −40.3% | 33% | 180/0 |
| dca_2x | 317,485 | 145,300 | 1,130,757 | 57% | +9.8% | 59% | 180/0 |
| dca_3x | 494,908 | 182,653 | 2,090,335 | 95% | +69.1% | 76% | 180/0 |
| oracle_dip_20 (hindsight) | 170,969 | 99,566 | 431,077 | 0% | −44.7% | 32% | 61/0 |
| swing_sma200 (tradable) | 143,624 | 86,618 | 321,383 | 0% | −53.2% | 16% | 183/40 |
| swing_sma200_tax (26%) | 121,394 | 77,312 | 237,699 | 0% | −61.4% | 24% | 183/40 |

Median CAGR 20y: ls_1x 10.7% · ls_2x 14.6% · ls_3x 15.1% · dca_1x 7.5% · dca_2x 12.2% ·
dca_3x 15.6% · oracle 7.3% · swing 5.6% · swing_tax 4.0%.

Sanity anchor: the master report (`research/dca_master_report.md`) uses a 55/30/15
SPY/EFA/EEM mix and finds LS ≈ +45% over DCA (pooled). This study is pure SPY, which
outperformed that mix, so the LS-over-DCA gap widens to ≈ +68% — same direction,
plausible magnitude.

## 4. Reading the three hypotheses

**H1 (leverage).** SUPPORTED in this sample, with big caveats. 2x and 3x beat 1x in
99%/89% of windows at the median, and even DCA_3x beats DCA_1x by +184%. BUT:
(i) median max drawdown of ls_3x is 96% (some windows touch >90% — e.g. 2008
starts), effectively ruin (recovery requires >1000%); ls_2x is a more believable
payoff (median DD 84%, still brutal); (ii) the sample contains post-2008 US
outperformance, the greatest regime for leverage in recorded history — see limits
below; (iii) p5 of ls_3x is BELOW p5 of ls_1x (104k vs 125k): the left tail is
worse, not better.

**H2 (monthly-dip trading, 20% tranches).** Rejected, and the closest thing to a
fair test confirms it: even the ORACLE version — perfect hindsight of the monthly low
— gives −44.7% vs LS and only −7.4% vs plain DCA. The tradable SMA200 + MTD-dip rule
(which deploys whole idle stacks on regime re-entries) does worse than DCA by −22%.
This replicates the prior conclusion: matched-capital dip-timing does not beat
buy-and-hold; the only thing it does better is drawdown (32% oracle, 16-24% swing vs
55% LS).

**H3 (taxable frequent flipping).** REJECTED. Same rule, taxed account: median
terminal drops from 143,624 to 121,394 (−15.5%) and −61.4% vs lump sum. Average tax
burned per window ≈ €20,685 — about 14% of the taxed terminal (≈ €1.9k+/yr on a €60k
lifetime contribution basis). 40 taxed flips per window with SMA* ≈ annual
round-trip cadence; "do that a lot" (more flips) is monotonically worse since Italy
has no taxation deferral and losses are only carried 4 years. The tax alone turns an
already-losing (-53% vs LS) strategy into a losing-er one.

## 5. Robustness

- By window-start cohort (medians, 20y): all orderings above hold across
  2004-09 / 2010-14 / 2015-20 starts; the 2004-09 cohort is the hardest for leverage
  (GFC at close range) yet dca_3x still shows 1.20M median vs 514k dca_1x and ls_2x
  1.83M vs 0.92M.
- Non-simulated sensitivity: this run cannot test regimes before 2008 (daily-reset
  paths need daily data and post-2008 real funds only trace the end); the master
  report's deep-history study (1926-) shows the same LS>DCA ordering.
- Worst 20y window is the same start (2004-12 era) for every strategy — a single
  crisis dominates the left tail; 5-year cohorts can mislead small n.

## 6. What would make me doubt this

- One asset (SPY-US) stands in for the "global index"; duration-2004+ covers only one
  real leverage-stress epoch (2008) plus the post-crisis bull. A 1929-55 (or Europe
  lost-decade) analogue would likely reverse 3x's ranking.
- The swing rules were NOT optimized — but they are also plainly sub-optimal designs
  chosen to mirror the user's description (annualized ~5.5% while SPY gave 12.7%);
  a better-designed rule (different SMA, buffer band, hold-through-2008) could look
  better — and then would be at risk of being a fitted artifact.
- Transaction economics (10+5 bps, no TER drag, no FX) are generous; the tax model
  omits dividend withholding (no tax on distributions in the sim) and the annual
  'regime dichiarativo' on accumulating ETFs — both directions unfavorable to the
  taxable strategy in reality.
- No margin-call/liquidation modelling inside 3x daily resets; real funds trade
  with overnight repo costs that spike when it matters most (March 2020).
- n=498 windows are heavily overlapping (same days counted in ~73% of windows);
  treat win-rates as descriptive, not inferential.
