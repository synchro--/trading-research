# Entry book v1.2 — stepped Chandelier ATR

## IQSE

ISIN `IE00BJQRDP39` → Yahoo `IQSE.DE` (Invesco Global Active ESG Equity UCITS ETF EUR PfHdg Acc).

## ATR rework (structural, not a length search)

**Problem with close − 3.5 ATR → tighten to 2.0 at 1.5R:**
- Trail ratcheted from *close* while still underwater → many −0.5R noise exits
- Median winner was only ~1.26R, so the 1.5R tighten stage rarely fired
- Almost all exits were trail (510/518)

**v1.2 rule (initial 3.5 ATR kept for sizing):**
1. `R < 1`: hard initial stop only (no close ratchet)
2. `1 ≤ R < 2`: breakeven floor at entry
3. `R ≥ 2`: LeBeau Chandelier `HH_since_entry − 3.0×ATR(14)`

## Results (2015→2026, 15 symbols incl. IQSE)

| System | med Sharpe | med CAGR | med DD | med E[R] | trades |
|--------|------------|----------|--------|----------|--------|
| Buy & hold | 0.84 | 19.2% | 56.5% | — | — |
| Faber monthly | 0.74 | 16.2% | 38.2% | — | 124 |
| TSMOM 12m | 0.61 | 12.1% | 35.3% | — | 87 |
| SMA50 + stepped | 0.57 | 1.8% | 6.4% | — | 343 |
| **EMA v1.2 stepped** | **0.56** | **2.0%** | **6.8%** | **~0.59** | 334 |
| EMA v1.1 old trail* | 0.46 | 1.4% | 7.0% | 0.35 | 518 |

\*v1.1 row from prior run on same book before IQSE; ATR change alone moved med Sharpe 0.46→0.56 and E[R] 0.35→0.59 on the 15-name set.

### EMA v1.2 highlights

| Symbol | Sharpe | E[R] | max DD | trades |
|--------|--------|------|--------|--------|
| IQSE.DE | **1.04** | **+1.06R** | 4.1% | 12 |
| NVDA | 0.84 | +0.96R | 6.8% | 24 |
| SMH | 0.77 | +0.74R | 6.6% | 29 |
| NET | 0.74 | +0.59R | 6.8% | 13 |
| GLD | 0.63 | +0.80R | 8.3% | 22 |
| BMPS.MI | 0.62 | +0.62R | 3.0% | 7 |
| TSM | 0.60 | +0.68R | 6.0% | 24 |
| KLAC | 0.56 | +0.57R | 7.4% | 30 |
| AVGO | 0.54 | +0.57R | 9.8% | 29 |
| META | 0.53 | +0.59R | 6.2% | 24 |
| AMD | 0.51 | +0.54R | 7.9% | 27 |
| VHYL.L | 0.49 | +0.51R | 5.8% | 21 |
| BNKE.PA | 0.36 | +0.32R | 11.1% | 26 |
| SPY | 0.32 | +0.32R | 7.8% | 26 |
| BPE.MI | 0.27 | +0.18R | 11.4% | 20 |

Fewer trades (hard stop lets noise work; fewer shakeouts) with better expectancy — correct for swing entry bets.

JSON: `backtesting/data/runs/entry_book_v12.json`
