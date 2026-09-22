# Portfolio ETFs

Brokerage "ETFs and Topics" holdings. FTSE All-World USD (Acc) removed per request.
Values in EUR. Tickers are Yahoo-style for the primary listing.

| Name | Ticker | ISIN | Value (EUR) | Weight |
| --- | --- | --- | --- | --- |
| MSCI World USD (Acc) | IWDA.AS | IE00B4L5Y983 | 3002.84 | 16.49% |
| Euro Overnight Rate Swap | XEON.DE | LU0290358497 | 2524.37 | 13.86% |
| Quantitative Strategies ESG | IQSA.L | IE00BJQRDN15 | 2423.61 | 13.31% |
| MSCI Europe Small Cap Val | ZPRX.DE | IE00BSPLC298 | 2174.68 | 11.94% |
| MSCI Emerging Markets II US | E127.L | LU2573966905 | 1349.59 | 7.41% |
| Physical Gold USD (EUR Hedged) | IGLD.DE | IE0009JOT9U1 | 842.34 | 4.63% |
| MSCI EM Latin America EUR | ALAT.PA | LU1681045024 | 745.93 | 4.10% |
| FTSE All-World High Dividend | VHYL.L | IE00B8GKDB10 | 630.47 | 3.46% |
| EURO STOXX High Dividend Low Vol | EUHD | IE00BZ4BMM98 | 625.68 | 3.44% |
| Semiconductor USD (Acc) | SEMI.L | IE000I8KRLL9 | 320.89 | 1.76% |

Total: **14,640.40 EUR** (weights renormalised to 100% below; table sums to 80.40% of the raw column as printed by the broker export).

## Notes

- Tickers mapped from truncated names; verify against broker before trading.
- EM II (`E127.L`) and Latin America (`ALAT.PA`) are the ambiguous ones - could also be iShares (`EEM`, `LTAM`/`IUSC.DE`).
- Only `VHYL.L` currently exists in `backtesting/data/` as a Yahoo CSV (all ten are now cached by this study; `EUHD` resolves via `EUHD.MI`).

---

# Full portfolio review (2026-09-22)

Backtest engine: `backtesting/portfolio_risk_reward.py` (run: `uv run python -m backtesting.portfolio_risk_reward --reuse-cache`, artifact `backtesting/data/portfolio_risk_reward.json`, tests: `uv run python -m unittest discover -s backtesting/tests`). Method: deep panel 2004-11→2026-08 (5,468 days, total-return Yahoo bars), 10+5 bps costs, waiting cash at `^IRX`, annual rebalance, nominal USD with EUR labels; risk metrics under daily-rebalanced static weights (drag-free approximation). Prior studies cited inline (`research/*.md`). Numbers below are median across all windows unless stated.

## 1. Current allocation — three-pillar analysis

Renormalised weights (sum 100%):

| Bucket | Role | Weight | Holdings |
| --- | --- | --- | --- |
| Equity | growth | **77.1%** | IWDA 20.5, IQSA 16.6, ZPRX 14.9, E127 9.2, ALAT 5.1, VHYL 4.3, EUHD 4.3, SEMI 2.2 |
| Bonds | deflation/crash ballast | **0.0%** | — |
| Gold | crisis/inflation hedge | **5.8%** | IGLD |
| Cash (MMF) | liquidity, dry powder | **17.2%** | XEON |

Findings:

- **Missing pillar #2.** The book is 77% equity / 0% bonds / 6% gold / 17% cash. No defensive income sleeve exists; the only ballast is cash and a small gold line.
- **Equity is fine in size, uneven in structure.** Core global (IWDA+IQSA ≈ 37%) is sensible; ZPRX at ~15% is a large single-factor bet (Europe small-cap value); E127+ALAT ≈ 14% EM with a concentrated LatAm sleeve; SEMI is a 2% satellite — right size.
- **Cash is simultaneously too much and mislabelled.** 17% XEON exceeds any realistic emergency-fund need at this portfolio size *and* sits inside the investment book — it is neither invested at target nor safely out of reach (see §7 bucket 3).
- **Instrument selection is secondary.** Per the premise "80% long-term from asset allocation, 20% from instruments": the holdings are all low-fee, sensible, diversified UCITS ETFs — the 20% is largely won already. Every metric gap vs the optimised portfolios below is an **allocation** gap (0% bonds, 77% equity, thin gold), not an instrument gap. This matches Brinson (1986) and Ibbotson & Kaplan (2000) — see §6 citations: allocation explains ~94% of cross-sectional and ~90% of time-series return variation; individual security/instrument choice explains ~0–6%.

## 2. Reference portfolios and the 3-pillar framework

Lyn Alden's three-pillar framing (growth assets / income assets / store-of-value hedges) maps to:

- **Pillar 1 — Growth:** global equities (current 77% → target ~40%).
- **Pillar 2 — Income/stability:** bonds (current **0%** → target 15–20%).
- **Pillar 3 — Store of value:** gold + cash (current 23% → gold 10–20%, cash 20%+ kept split between invested cash and true emergency).

Classic reference portfolios measured on the same deep panel (all daily-rebalanced, full sample):

| Portfolio | CAGR | vol | Sharpe | Sortino | maxDD | Calmar |
| --- | --- | --- | --- | --- | --- | --- |
| stocks_100 (100% equity) | 9.6% | 20.3% | 0.55 | 0.53 | 58.3% | 0.16 |
| 80/20 | 8.8% | 16.7% | 0.59 | 0.56 | 49.2% | 0.18 |
| 60/40 | 7.8% | 13.1% | 0.64 | 0.61 | 38.6% | 0.20 |
| **golden_butterfly** (40 eq/20 short bonds/20 gold/20 cash) | **8.1%** | 9.5% | **0.86** | **0.82** | **22.2%** | **0.36** |
| actual_proxy (your book, proxied) | 9.0% | 15.5% | 0.63 | 0.60 | 45.6% | 0.20 |
| actual_plus_bonds (add 10% AGG) | 8.5% | 13.9% | 0.65 | 0.62 | 41.4% | 0.20 |
| actual_plus_oil (add 7% XLE) | 8.9% | 15.6% | 0.63 | 0.59 | 44.6% | 0.20 |
| **optimal_growth** (optimizer, CAGR floor 7%) | 7.5% | 7.5% | **0.99** | **0.94** | **20.8%** | **0.36** |
| optimal_harmonic (pure risk-optimum) | 5.4% | 4.7% | 1.15 | 1.10 | 13.3% | 0.40 |

## 3. Optimal risk-reward (the Sharpe/Sortino answer)

Dirichlet random search (6,000 samples, per-asset cap 40%) over SPY/EFA/EEM/AGG/GLD/VBR/VTV/SHY/IEF/XLE+CASH, train 2004-12→2015-12, test 2016→2026:

- **Pure risk-optimum (`optimal_harmonic`):** IEF 34% + AGG 25% + CASH 20% + GLD 6% + ~14% equity slivers. Train Sh/So 1.44/1.42 → test 0.93/0.89, but CAGR only 5.4% full-sample. This is the mathematical max-Sharpe/Sortino solution — and it is too conservative to be the *plan* (fails a 7% growth floor for an accumulator).
- **Growth-constrained optimum (`optimal_growth`, train CAGR ≥ 7%, n=2,287 feasible):** SPY 14.5%, IEF 15.7%, CASH 34.9%, GLD 13.9%, VTV 6.0%, EEM 5.7%, XLE 3.3%, AGG 3.1%, VBR 2.1%, EFA 0.8%. Train Sh/So/CAGR 0.91/0.89/7.0% → **test 1.25/1.17/8.1%** (generalises — test beat train). Full-sample: **7.5% CAGR, Sharpe 0.99, Sortino 0.94, maxDD 20.8%, Calmar 0.36.**
- The three objectives (harmonic/Sharpe/Sortino) pick the *same* bond-heavy sample — verified not a bug; one portfolio simply dominates the feasible set on all three risk metrics in the 2004–2015 train window.
- **Regime caveat (challenge):** cash-heavy/bond-heavy optima are partly a train-window artefact (2004–2015 included two equity crashes and a long bond bull). The test window (2016–2026: rates shock, COVID, AI boom) still shows `optimal_growth` at Sh 1.25 — the diversification survives out-of-sample, but expected forward CAGR should be read as ~7–8%, not the equity-like 9%+ of `actual_proxy`.

**Implementable mid-points** (same engine, EUR-proxy roles), for the trade-off frontier:

| Target | CAGR | Sharpe | Sortino | maxDD | note |
| --- | --- | --- | --- | --- | --- |
| 40 eq / 20 bonds / 20 gold / 20 cash (`golden_butterfly`) | 8.1% | **0.86** | **0.82** | **22.2%** | best practical risk-reward |
| **55 / 15 / 10 / 20** (`balanced`) | 8.3% | 0.77 | 0.73 | 33.5% | accumulator compromise |
| 70 / 10 / 8 / 12 (`growthfirst`) | 8.9% | 0.68 | 0.65 | 41.5% | ≈ current shape + bonds |
| current shape (`actual_proxy`) | 9.0% | 0.63 | 0.60 | 45.6% | highest CAGR, worst risk metrics |

**Optimal condition found:** moving from the current shape to the **golden-butterfly/balanced zone (≈40–55% equity, 15–20% bonds, 10–20% gold, 20% cash)** costs ~0.7–1.5pp CAGR vs staying put but lifts Sharpe from 0.63 → 0.77–0.86, Sortino 0.60 → 0.73–0.82, and halves max drawdown from ~45% → 22–34%. The floor version (`optimal_growth`) is the risk-first pole (Sh 0.99/So 0.94 at 7.5% CAGR). Given the explicit goal "good Sharpe AND good Sortino", **target ≈ 45–50% equity / 15–20% bonds / 10–12% gold / 20–25% cash**, reached gradually via contributions (§7), is the recommended condition.

**Actual book sanity check (real tickers, 2023-03→2026-08, 824 days):** current book CAGR 17.4%, Sharpe 1.72, Sortino 1.66, maxDD 12.7% — a short bull-window; do not extrapolate. Short-window optimizer on the real book wants **IQSA 33%, IGLD 21–34%, EUHD 21%, EUNA bonds 7–17%, XEON** and near-zero IWDA/SEMI/ZPRX — i.e., the same message from a different sample: *more gold, add bonds, less concentrated equity*. (Short-sample weight levels are unstable; use direction, not digits.)

## 4. Bond / gold / oil verdicts (pillar splits)

- **Bonds — add, 15–20%.** Currently 0%. `actual_plus_bonds` lifts Sharpe 0.63→0.65 and cuts maxDD 45.6%→41.4% at −0.5pp CAGR; every optimizer keeps bonds at 19–59% (AGG+IEF+SHY). JPM LTCMA 2026: best intermediate-Treasury outlook since the GFC — the bond ballast is historically cheap to add *now*. Vehicle: `EUNA.DE` (EUR-hedged aggregate proxy); keep the defensive sleeve in EUR to avoid FX on the safe leg.
- **Gold — keep and raise, 10–12% (up to 20% if following golden butterfly).** Currently 5.8%. Optimizers hold GLD at 6–14% (13.9% in `optimal_growth`, 21–34% in the short actual-book optimum); golden butterfly's 20% gold is a key reason for its 0.86 Sharpe. War scenario below: gold +25% is the only offset. Vehicle: `IGLD.DE` (already held).
- **Oil — optional, ≤5%, not a pillar.** `actual_plus_oil` (7% XLE from equity): Sharpe unchanged 0.63, Sortino 0.60→0.59, maxDD 45.6%→44.6%, CAGR −0.1pp. Helps only in the 2008 oil spike (−5.8% vs −8.3%); *hurts* in COVID and 2022. **Verdict: skip as strategic allocation; if desired, ≤5% tactical only.**
- **Cash:** keep ~20% *inside* the investment book as the PAC buffer (target bucket), and hold the true emergency fund **outside** the book (§7).

## 5. Lump sum vs Smart PAC (all windows)

Window scheme: horizons 10–20y × every monthly start, 500 EUR/mo, 10+5 bps, pooled medians. `smart_pac` = budget-neutral 2× on the deep-dip trigger (≥3% below rolling 20d high), 0 the next month, chained, invested ≡ 500×N exactly (fixed; `dip_dca`'s `dip2x_neutral` never repays — see module docstring).

| Portfolio | LS median | DCA mid | Smart PAC | Smart vs DCA (€/€) | Smart vs LS |
| --- | --- | --- | --- | --- | --- |
| actual_proxy | 207,204 | 135,060 | 144,564 | **+9.7%** (win 100%) | −28.2% |
| actual_plus_bonds | 191,726 | 127,637 | 133,955 | **+7.3%** (100%) | −28.6% |
| optimal_growth | 162,105 | 111,251 | 113,161 | **+3.2%** (100%) | −29.3% |
| golden_butterfly | 175,414 | 117,387 | 121,252 | **+4.5%** (100%) | −29.1% |
| stocks_100 | 218,760 | 145,392 | 159,766 | **+10.8%** (100%) | −27.1% |

Consistent with prior research: LS beats DCA by ~+45% median (`dca_master_report.md`); smart PAC's edge is vs *naive DCA*, not vs lump sum. `dip2x_half` (invests extra capital by design) reaches near-LS terminals but is budget-unfair; per-EUR vs DCA +1.3–2.0% here, matching `dip_dca.md` (+1.7% implementable, +3.4% with sharper trigger).

**Operational rules:**

1. Windfall/lump available → **invest immediately**; if behaviourally hard, stage over ≤12 months (hybrid 12-month tail costs only −0.4% mean vs LS, `hybrid_split.md`) — never longer.
2. Recurring salary PAC → **Smart PAC** (2× on deep red dip, 0 next month): +3–10% per EUR vs mid-month DCA, wins 100% of windows at zero extra budget.
3. Do not wait for a crash to deploy: wait-rules cost −1.3% to −31% median (`crash_deploy.md`); a parked 30k buffer over 10–20y costs −18% median vs investing it (`mm_cushion.md`).

## 6. Macro context 2026/27, scenarios, citations

### Fed SEP (September 16, 2026) — "moderate growth" base case

Real GDP **+2.3% (2026), +2.4% (2027)**, longer-run 2.0%; unemployment 4.1% through 2029; PCE inflation **3.7% (2026) → 2.3% (2027) → 2.1% (2028)**; core PCE 3.4% → 2.5% → 2.2%; fed funds 4.1% end-2026 and end-2027, easing to 3.9%/3.6% in 2028/29. Read: growth above trend-ish but benign, **inflation sticky in 2026 then cooling**, rates high-for-longer into 2027 — supports holding cash/short bonds now, adding duration gradually, and keeping the gold hedge while inflation is still >3%.

### JPM LTCMA 2026

Long-term capital-market assumptions: best intermediate Treasury return outlook since the GFC — first time in a decade the bond leg is expected to *earn* meaningfully while still ballasting equities (see §4 bond verdict).

### Scenario shocks on the current book (arithmetic overlays)

| Scenario | Portfolio return | Structure |
| --- | --- | --- |
| AI burst (semis −55%, broad equity −25…−40%, gold +10%) | **−27.2%** | concentration risk is small (SEMI 2%); hit is beta |
| War/oil shock (equity −8…−20%, gold +25%) | **−10.3%** | gold cushion works; **raising gold 6%→12% nearly halves this** |
| US moderate growth (matches Fed SEP) | **+10.1%** | base case ≈ equity beta + small-cap/value outperformance |

### AI: bull vs bear (narrative risk framing; backtested pieces flagged)

- **Bull:** AI-driven productivity lifts margins/growth — SMH own-history **CAGR 30.9%, Sharpe 1.03** (best sleeve measured), test-period Sharpe 1.08. Already inside the book via IWDA/IQSA/SEMI.
- **Bear:** multiple compression/CAPE-style unwind in AI leaders → scenario −27% for the book. Mitigants already in place: SEMI only 1.76%, no single-stock AI risk; add the bond/gold ballast (§4), do **not** add a dedicated AI ETF on top (double counting).
- **Quantum:** no liquid, long-history, tradeable pure-play — **no backtestable sleeve; zero allocation** (or a <1% options-budget curiosity outside this plan).

### Growth drivers (own-history, split at 2016)

| Sleeve | CAGR | Sharpe | Sortino | maxDD | train→test Sharpe | role in plan |
| --- | --- | --- | --- | --- | --- | --- |
| SMH (AI/semis) | 30.9% | 1.03 | 1.00 | 45.3% | 0.86→1.08 | satellite ≤5% (SEMI already 2%) |
| XLE (energy) | 10.5% | 0.49 | 0.47 | 71.3% | 0.47→0.51 | optional ≤5% (§4 verdict) |
| XBI (biotech) | 12.0% | 0.52 | 0.52 | 63.9% | 0.68→0.40 | speculative; deterioration OOS — skip or ≤3% |
| XLF (finance) | 6.2% | 0.35 | 0.35 | 82.7% | 0.22→0.67 | poor long-run risk-reward → **swing sleeve only**, not core |
| QQQ (AI/tech broad) | 10.9% | 0.52 | 0.50 | 83.0% | 0.32→0.94 | already via IWDA/IQSA; no separate line |

### Citations

**Asset allocation / IB classics (the 80/20 premise):**
- Brinson, Beebower & Hood (1986), *Determinants of Portfolio Performance*, Financial Analysts Journal — asset-allocation policy explains ~94% of the quarterly variance of pension-plan returns; security selection ~0%.
- Ibbotson & Kaplan (2000), *Does Asset Allocation Explain 94%, 93%, or 1 Percent of Variance?*, Ibbotson Associates — ~90% of the *time-series* variance of a 60/40 policy portfolio over decades; the famous 94% is cross-sectional. Both underpin the "80% allocation / 20% instruments" framing.
- Markowitz (1952), *Portfolio Selection*, JF — diversification across low-correlation assets (bonds/gold vs equity) is free risk reduction; the §3 optimiser is a direct descendant.
- Kahneman & Tversky (1979) / Thaler (n.d. behavioural finance) — why DCA feels safer than LS even though LS wins the median: regret minimisation, not return maximisation (`hybrid_split.md`: 12-month tail buys most of the behaviour benefit for −0.4% expected cost).

**Three-pillar / allocation frameworks:**
- Lyn Alden, April 2024 newsletter — three-pillar portfolio structure (growth / income / store-of-value): https://www.lynalden.com/april-2024-newsletter/
- JPMorgan LTCMA 2026: https://am.jpmorgan.com/us/en/asset-management/adv/insights/portfolio-insights/ltcma/ (PDF: assets.jpmprivatebank.com/.../JPM56789-LTCMA-2026.pdf)
- Federal Reserve, SEP September 16, 2026: https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm
- Bridgewater, *All Weather* (risk-parity note) — the 30/40/15/15-style weather-balance precedent for holding bonds+gold with equity.
- Vanguard, *Dollar-cost averaging just means taking risk later* — the canonical LS-vs-DCA trade-off note (PDF; results reproduced in `research/dca_master_report.md`).
- Meb Faber, *A Quantitative Approach to Tactical Asset Allocation* (SSRN) and the local TSMOM replication: timing/trend overlays lift Global-6 Sharpe 0.56→0.66 (`research/portfolio_and_bottoms.md`) — relevant if tactical risk-off rules are ever added; not required for this plan.
- Lazy-portfolio backtest comparison: https://awalyt.com/insights/lazy-portfolio-showdown-backtest (golden butterfly vs 60/40 vs all-weather — consistent with §2).

**Repo evidence (all reproducible):** `research/dca_master_report.md`, `research/dip_dca.md`, `research/hybrid_split.md`, `research/crash_deploy.md`, `research/mm_cushion.md`, `research/portfolio_and_bottoms.md`, `backtesting/data/portfolio_risk_reward.json`.

## 7. The three-bucket plan

### Bucket 1 — Core ETF portfolio (the 3-pillar book; all new PAC money)

**Target allocation** (gradual glide from current 77/0/6/17 — fund with contributions first, trim ZPRX/ALAT only as needed; no forced selling of IWDA/IQSA):

| Sleeve | Current | **Target** | Vehicle | Action |
| --- | --- | --- | --- | --- |
| Global equity core | 37.1% (IWDA+IQSA) | **30%** | IWDA.AS, IQSA.L | hold; PAC drip |
| Europe small value | 14.9% (ZPRX) | **8%** | ZPRX.DE | trim on rebalances |
| EM + LatAm | 14.3% (E127+ALAT) | **7%** (EM 5 / LatAm 2 cap) | E127.L, ALAT.PA | trim ALAT |
| Div equity | 7.6% (VHYL+EUHD) | **5%** | VHYL.L, EUHD.MI | hold |
| Semis satellite | 2.2% (SEMI) | **≤5%** | SEMI.L | optional top-up to 4–5% (SMH-quality AI tilt) |
| **Bonds** | **0%** | **15%** | **EUNA.DE (new)** | buy with XEON first |
| Gold | 5.8% | **12%** | IGLD.DE | buy down cash |
| Cash/PAC buffer | 17.2% | **18%*** | XEON.DE | target after transition; *or ~20% if following golden butterfly |

Resulting posture ≈ **47–50% equity / 15% bonds / 12% gold / 18–23% cash** — inside the measured optimum zone of §3 (expected ~8% CAGR, Sharpe ~0.8, Sortino ~0.75, maxDD ~25–30% vs today's ~45%).

- **Contributions (500/mo):** Smart PAC rule — 1,000 on a deep-dip month (composite ≥3% below rolling 20d high), 0 next month, else 500; until sleeve targets are met, **route buys to bonds and gold first**, then equity trims/top-ups.
- **Windfalls:** invest same day (or ≤12-month stage max).
- **Rebalance:** annually, or when a sleeve drifts ±5pp.
- Oil: none (§4). AI/quantum/biotech/finance: no dedicated core lines (§6 driver table).

### Bucket 2 — Dividend-bank swing sleeve (discretionary, ≤5–10% of total wealth ≈ 750–1,500 EUR per 14.6k book; separate from Bucket 1)

- Universe (`research/bank_correlation.py`): **BPE.MI, UCG.MI, ISP.MI, BMPS.MI, AZM.MI**, diversified with **VHYL/IDVY** when a single-name looks rich. Script structure: 5k → 1.25k × 2 banks + 1.25k × 2 dividend ETFs.
- Banks/finance score **Sh 0.35, maxDD 82.7% own-history (XLF)** — swing only, never core. Position cap ~25% of the sleeve per name; hard stop per trade; sleeve funded only from Bucket 1 proceeds after targets are met.
- Purpose: satisfy the active-trading urge with bounded ruin risk; core stays passive (the 80/20 evidence says instruments/selection are the small half of returns).

### Bucket 3 — Emergency fund (outside the investment book, in XEON)

- **3–6 months of expenses**, held at the bank/MMF, never counted as investable, never part of the 500/mo PAC.
- `mm_cushion.md`: a 30k buffer parked *for investing* over 10–20y costs −18% median vs investing it — so size the fund for **expenses only**, then invest everything above it. Establishing this buffer takes priority over Bucket 1 optimisation if it doesn't exist yet; after it exists, every surplus euro goes to Bucket 1 targets.

## 8. Conclusion

1. **Allocation, not instruments, is the lever.** The book already wins the "20% instruments" half (cheap, diversified UCITS); it loses on the "80% allocation" half: **0% bonds, thin gold, 77% equity** → Sharpe 0.63 / Sortino 0.60 / maxDD ~45% (proxy, 2004–2026).
2. **Optimal risk-reward condition found:** the golden-butterfly/balanced zone — **≈45–50% equity, 15–20% bonds (EUNA), 10–12% gold (IGLD), ~20% cash (XEON)** — measured 7.5–8.3% CAGR, **Sharpe 0.77–0.99, Sortino 0.73–0.94, maxDD 21–34%**, generalising out-of-sample (test Sharpe 1.0–1.25). Cost vs staying put: ~1pp CAGR. Benefit: Sharpe +0.2–0.4, drawdown roughly halved. The pure max-Sharpe/Sortino portfolio (5.4% CAGR, Sh 1.15) is the risk-first pole — keep it in mind for de-risking later life-stage, not for accumulation.
3. **Pillar decisions:** bonds **add 15%** (best add since GFC per JPM LTCMA 2026; Fed SEP keeps cash yielding 4.1% through 2027 while inflation cools 3.7%→2.3% — buy duration gradually); gold **raise 6%→12%** (war scenario −10% vs −27% AI-burst is the asymmetry that matters); oil **skip** (no Sharpe improvement; crisis benefit confined to 2008).
4. **Deploys:** have-it-now → **lump sum** (or ≤12-month hybrid, −0.4%); monthly salary → **budget-neutral Smart PAC** (+3–10% per EUR vs DCA, 100% of windows); never wait for −20/−30% crashes (−1.3% to −31% median cost).
5. **Risks framed for 2026/27:** Fed base case = moderate growth (+2.3/+2.4%) with sticky-then-falling inflation — good for the balanced book; the fat left tail is an **AI unwind (−27%)**, mitigated by small SEMI weight + bond/gold ballast, not by de-risking equities wholesale; **war/oil (−10%)** is largely absorbed by a 12% gold line; growth drivers (energy/biotech/finance) measure poorly OOS — keep them out of core, finance only in the bounded swing sleeve; quantum has no tradeable backtestable sleeve — zero allocation.
6. **Three buckets:** (1) core 3-pillar ETF portfolio at the target above, fed by Smart PAC until targets met; (2) small dividend-bank swing sleeve (≤5–10% wealth, bank universe per `bank_correlation.py`); (3) expense-sized emergency fund in XEON, strictly outside the book. Execute bucket 3 first if missing, then bucket 1 bond/gold buys from existing XEON, then bucket 2 only from surplus.

*Method caveats: nominal USD with EUR labels, no TER/taxes deducted (10+5 bps trading costs included), daily-rebalance approximation for risk metrics, short actual-book window (2023+) not comparable to deep-panel figures, optimizer weights are role-model targets not ticker-level trade instructions.*
