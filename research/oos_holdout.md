# True OOS: discovery universe, then frozen entry-book hold-out

The 15-name entry book (NVDA…IQSE.DE, including GLD) is **frozen**. No strategy
was ranked or selected on it in this protocol. Selection used 78 names with
**zero ticker overlap**.

Window: 2015-01-01 → 2026-08-13 · Yahoo · 10 bps + 5 bps · T+1 open · 252-bar warmup.

## Universes

**Discovery (train), 78 names**

- Metals: SLV, CPER, PPLT, PALL (silver, copper, platinum, palladium)
- Italy: ISP, ENI, ENEL, STLAM, RACE, PRY, REC, TIT (not BMPS/BPER)
- UK: HSBA, SHEL, AZN, ULVR, RIO, RR, VOD, DGE
- Germany: SAP, SIE, ALV, BAS, BMW, MRK, DTE, RWE
- Japan: 7203, 6758, 8306, 6501, 4502, 8031, 9432
- Korea: 005930, 005380, 105560, 035420, 051910
- Hong Kong: 0700, 0941, 1299, 0388, 0005, 0857, 2318
- EM stocks: VALE, PBR, ITUB, INFY, IBN, BABA, AMX, MELI
- ETFs: QQQ, IWM, EFA, EEM, XLE, XLF, XLV, XLI, XLP, VNQ, TLT, DBC, HYG,
  EWJ, EWG, EWU, EWY, EWH, EWI, INDA, EWZ, EWW, MCHI

**Hold-out (test):** NVDA, AVGO, META, AMD, TSM, NET, KLAC, SMH, BMPS.MI, BPE.MI,
BNKE.PA, GLD, VHYL.L, SPY, IQSE.DE

## Discovery ranking (selection)

| Strategy | Med Sharpe | Med CAGR | Med DD | Trades |
|---|---|---|---|---|
| Buy & hold | 0.46 | 8.4% | 52.9% | — |
| **Faber SMA200 monthly** | **0.37** | 5.7% | 41.2% | 877 |
| **TSMOM 12m** | **0.33** | 4.0% | 39.1% | 648 |
| **EMA pullback v1.2** | **0.26** | 0.7% | 8.0% | 1703 |
| EMA vol-target | 0.23 | 1.8% | 28.1% | 1703 |
| Confluence v2 | 0.23 | 0.7% | 8.9% | 2039 |
| Squeeze | 0.22 | 0.5% | 8.1% | 1469 |
| SMA50 reclaim | 0.20 | 0.5% | 7.7% | 1689 |
| Ichimoku | 0.20 | 0.4% | 7.4% | 1547 |
| Supertrend | 0.17 | 0.5% | 10.4% | 3740 |
| Lorentzian kNN | 0.15 | 0.5% | 10.9% | 3204 |

Discovery time-split (still not the hold-out):

| | 2015–2020 | 2021–2026 |
|---|---|---|
| Faber | 0.25 | 0.44 |
| TSMOM | **0.11 / −0.11R** | 0.47 |
| EMA v1.2 | 0.20 | 0.20 |
| Confluence | 0.19 | 0.17 |
| Ichimoku | 0.21 | 0.17 |

**Selected before touching the hold-out**

1. Allocation overlay: Faber (stable both halves). TSMOM dropped — expectancy
   negative in 2015–2020.
2. Swing timer: EMA v1.2 (flat 0.20 / 0.20). Confluence does **not** win the
   train set, so it is not a selected winner — only reported as a comparator.

## Metals sleeve → GLD (hold-out)

Metals median Sharpe: TSMOM 0.32, Faber 0.31, Ichimoku 0.26, Confluence 0.21, EMA 0.15.

GLD was unseen:

| | Sharpe | E[R] | Max DD | Trades |
|---|---|---|---|---|
| Buy & hold | 0.75 | — | 26.4% | — |
| **EMA v1.2** | **0.63** | +0.80R | **8.3%** | 22 |
| Ichimoku | 0.62 | +0.78R | 7.5% | 19 |
| SMA50 | 0.61 | +0.72R | 6.6% | 22 |
| TSMOM | 0.59 | +0.86R | 26.3% | 9 |
| Confluence | 0.55 | +0.63R | 9.8% | 28 |
| Faber | 0.49 | — | 31.6% | 11 |

On gold, the metals swing winner (Ichimoku) transfers; EMA is slightly better
and was the selected swing rule anyway. Faber/TSMOM keep ~buy-and-hold drawdowns.

## Hold-out book (never used for selection)

| Strategy | Med Sharpe | Med E[R] | Med DD |
|---|---|---|---|
| Faber (selected overlay) | **0.74** | n/a (full equity) | 38.2% |
| TSMOM (rejected on train split) | 0.61 | n/a | 35.3% |
| Confluence (not selected) | 0.58 | 0.57 | 8.0% |
| SMA50 | 0.57 | 0.62 | 6.4% |
| **EMA v1.2 (selected swing)** | **0.56** | **0.59** | **6.8%** |
| Ichimoku | 0.47 | 0.55 | 5.9% |

Faber still leads the hold-out on Sharpe because this book is a long equity bull.
EMA remains the swing rule that keeps DD ~7%. Confluence beating EMA on the
hold-out (0.58 vs 0.56) is **not** a selection result — it lost on the 78-name
train set. Treat that 0.02 gap as noise.

SMH / IQSE on the hold-out (EMA still the swing pick): SMH 0.77, IQSE 1.04.

## Country medians on discovery (EMA vs Faber)

| Market | Faber | TSMOM | EMA | Confluence |
|---|---|---|---|---|
| Italy | 0.74 | 0.53 | 0.53 | 0.49 |
| UK | 0.23 | 0.29 | −0.05 | 0.04 |
| Germany | 0.25 | 0.34 | 0.18 | 0.21 |
| Japan | 0.60 | 0.49 | 0.34 | 0.42 |
| Korea | 0.37 | 0.27 | 0.31 | 0.24 |
| Hong Kong | 0.49 | 0.34 | 0.32 | 0.40 |
| EM stocks | 0.30 | 0.27 | 0.15 | 0.26 |
| ETFs | 0.39 | 0.30 | 0.14 | 0.12 |

UK is hostile to daily EMA reclaim (choppy large-caps). Faber/TSMOM survive it.

## Practical

- **Overlay / stay invested:** `strategies/pinescript/faber_sma200.pine`
- **Swing entries (1.5% risk, ~7% DD):** `strategies/pinescript/ema_gc_adaptive.pine`
- Confluence v2 is optional, not the OOS-selected swing winner.

Compare books: `--book discovery` (train), `--book metals`, `--book entry` (hold-out).
