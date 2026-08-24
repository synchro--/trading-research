# EMA Pullback Swing

Source of truth for the long-only swing system. Other agents implement from this file and [TODO.md](TODO.md). Do not invent rules that are not written here.

**Status:** v1.2 — RSI gate removed; ATR trail is stepped Chandelier (hard 3.5 → BE @ 1R → HH−3 ATR @ 2R). Do not retune lengths until a walk-forward protocol exists.

---

## 1. Intent and non-goals

**Intent.** Take a small number of pullback longs in a confirmed daily uptrend. Hold days to weeks (occasionally longer if the trail allows). Universe: liquid US equities and thematic ETFs (SMH, QQQ, and similar). One position per symbol.

**What “good” looks like.** Fewer entries than a raw 50/200 golden-cross system, with the entries that remain being EMA50 reclaims after a real dip — not chases and not the golden cross itself.

**Non-goals (v1).**

- Lump-sum / multi-year index allocation (that is the ETF overlay, appendix A).
- Shorts, minute bars, multi-symbol portfolio construction, live or paper trading.
- Weekly `request.security`, OBV, Keltner/Bollinger as entry filters.

---

## 2. File map

| Artifact | Role | Engine? |
|----------|------|---------|
| This file | Frozen v1 spec | Spec |
| [TODO.md](TODO.md) | Work queue | Tasks |
| [pinescript/ema_gc_adaptive.pine](pinescript/ema_gc_adaptive.pine) | TradingView mirror of v1.2 | Yes |
| [pinescript/etf_bottom_finder.pine](pinescript/etf_bottom_finder.pine) | Chart overlay for discretionary ETF adds | **No** |
| `golden_cross_strategy.pine`, `rsi_strategy.pine`, `bollinger_bands_strategy.pine` | Legacy examples | No |

`macro_entry.pine` was renamed to `ema_gc_adaptive.pine`. That file is the strategy, not an overlay.

---

## 3. v1 (frozen)

All series are **daily** unless noted. Indicators: EMA(close, 50), EMA(close, 200), ATR(14).

### 3.1 Regime

Bull regime when `EMA50 > EMA200`. No new longs otherwise.

The 50/200 golden cross is a **regime event**, not an entry. Do not buy the cross.

### 3.2 Entry

Signal is evaluated on bar **T close**. Engine fill is bar **T+1 open**. Flat only (no pyramiding).

All of the following must be true:

1. `EMA50 > EMA200` (already in bull regime; the cross itself does not qualify).
2. `close` crosses above `EMA50` (`ta.crossover(close, ema50)`).

~~RSI dip / band gate removed (v1.1).~~ Two independent books (tech + diverse) showed the RSI filter identical to naked reclaim; it filtered nothing. Do not reintroduce without a trade-log proof.

### 3.3 Initial risk and size

- `initial_risk` = `3.5 * ATR(14)` **frozen on the signal/entry bar**. Do not update it later.
- Position size = `(equity * 0.015) / initial_risk` (1.5% of equity at risk).
- If `initial_risk <= 0`, skip the trade.

### 3.4 Stepped Chandelier trail (v1.2)

Ratchet **up only** (longs). `R = (close - entry) / initial_risk`. `HH` = highest high since entry.

```
R < 1.0   -> keep initial stop (entry − initial_risk). Do NOT trail from close.
1 ≤ R < 2 -> trail floor = entry (breakeven lock)
R ≥ 2.0   -> trail = max(entry, HH − 3.0 × ATR(14))   // LeBeau Chandelier
```

On the first bar in the trade, `trail = entry - initial_risk`.

**Why this replaced close − 3.5 ATR → 2.0 ATR at 1.5R:** the old rule ratcheted the stop up from *close* while still underwater, creating many −0.5R noise exits, and most winners never reached 1.5R so the tight stage never fired (median winner ~1.26R). Hard stop until +1R + breakeven + Chandelier after +2R is the published structure (initial volatility stop + LeBeau trail) without searching new lengths.

**Same-bar rule (required).** Tomorrow’s stop is known at today’s close. Do not compute a new trail from bar T’s close/high and allow bar T’s low to hit it. Engine: the live stop on bar T is the trail from bar T−1 (or the initial stop on the entry bar). Pine: `process_orders_on_close=true` and the exit uses the **already-ratcheted** trail, then the trail is updated for the next bar.

### 3.5 Exits

Exactly two exits:

1. **Trail.** If `low <= trail`, fill at `min(open, trail)` (gap through the stop uses the open). Reason: `trail`.
2. **Regime break.** If `EMA50` crosses under `EMA200`, flatten at the **next open**. Reason: `regime`.

No take-profit limit. No time stop in v1.

### 3.6 Costs (engine)

Apply commission bps and optional slippage bps on every fill. TradingView without costs is not the baseline.

### 3.7 Defaults (do not change without a new version bump)

| Parameter | Value |
|-----------|-------|
| Fast EMA | 50 |
| Slow EMA | 200 |
| ATR length | 14 |
| Initial ATR multiple | 3.5 |
| Breakeven at | 1.0R |
| Chandelier from | 2.0R |
| Chandelier ATR multiple | 3.0 |
| Risk per trade | 1.5% of equity |

---

## 4. Why these rules

Classical 50/200 + fixed ATR fails in three ways this system is built to avoid:

1. **Chop.** Buying every 50-cross inside a range produces high churn. The regime gate (`EMA50 > EMA200`) is the primary filter; reclaim waits for price to return through the fast average after a pullback.
2. **Fixed ATR asymmetry / premature trail.** A tight stop (1.5–2.0 ATR) shakes out healthy growth names; a static wide stop gives back a trend. v1.2 keeps the wide **initial** 3.5 ATR stop for sizing, but does **not** ratchet from close while underwater. At +1R lock breakeven; at +2R switch to a LeBeau Chandelier (`HH − 3 ATR`). That is the published structure without searching new multiples.
3. **Buying the golden cross.** On SMH/QQQ the 50/200 cross often prints 15–25% off the low. A 3.5 ATR stop under that bar is a late entry with a wide stop. v1 waits for the first qualifying EMA50 reclaim instead.

The RSI band was removed after it matched naked reclaim on both the tech and diverse books. Do not retune RSI lengths to "make the gate work."

The thesis of the trade is “bull regime.” A trail-only exit can give back a full 3.5 ATR in a slow roll over. Death-cross flatten belongs in v1.

---

## 5. Weaknesses

### Must-fix (already applied in v1 Pine; do not reintroduce)

- Raw golden-cross entry (`long_trigger = gc_entry or re_entry`).
- `RSI >= 45` as the only reclaim filter.
- Two-bar EMA50 slope labeled as ADX (almost always true in a bull regime; not a quality filter).
- Trail-only exit with no death-cross flatten.
- Updating the trail from the same bar’s close and filling that bar’s low against it.
- Missing TRAIL / SAFE flags on the strategy Pine.

### Accepted in v1 (do not “fix” until a baseline trade log exists)

- Misses some RSI `< 40` washouts by design.
- Daily 50/200 can stay bullish while weekly is already rolling over (v2).
- Engine 0.1 uses Alpaca split-adjusted daily bars and does not credit dividends (total return slightly understated).
- Pine fills (`process_orders_on_close`) will not match engine fills (T+1 open) tick-for-tick. Compare trade *counts and reasons*, not exact PnL.

---

## 6. v2 backlog

Engine 0.1 exists. Do **not** add weekly/OBV/Keltner or retune lengths. The RSI band was deleted (inert). Optional later, only from a live trade log:

1. Weekly EMA slope as a **gate** (not a second entry).
2. Optional time stop (flatten after N bars if still `R < 1`).

A rolling walk-forward **re-fit** (the ML pattern: re-estimate parameters every k months) is not useful here. Lengths are literature defaults, not fitted weights. The useful analogue — freeze the rule, score names and years that were not used to choose it — is done in §6d.

Do not add these in a new engine pass.

---

## 6b. Measured baseline (refreshed 2026-08, EMA v1.2)

Book: KLAC, SMH, NET, GOOGL, SPY, QQQ, URTH. Live window **2021-06-01 → 2026-08-13**.
Reproduce with `python -m backtesting.compare --book tech`.

| System | Median Sharpe | Median CAGR | Median maxDD | Beats B&H |
|---|---|---|---|---|
| Buy & hold | 0.81 | 23.0% | 43.6% | — |
| Faber SMA200 | **0.87** | 15.3% | **26.9%** | 4/7 |
| TSMOM 12-month | 0.82 | 12.8% | 22.6% | 3/7 |
| Connors RSI(2) + ATR trail | 0.63 | 7.5% | 19.6% | 2/7 |
| Connors RSI(2) | 0.41 | 3.7% | 9.9% | 0/7 |
| **EMA Pullback v1.2** | 0.27 | 0.7% | **6.8%** | 0/7 |
| Donchian 55/20 | 0.22 | 1.1% | 8.7% | 0/7 |
| RSI trend dip | 0.10 | 0.2% | 5.0% | 0/7 |

`ema50_reclaim` is an alias of `ema_pullback` (RSI gate removed). Findings that still hold:

1. **RSI gate deleted.** It matched naked reclaim on two books. Do not bring it back.
2. **CAGR is a sizing artifact.** 1.5% risk over a 3.5-ATR stop deploys ~15–20% of equity. Never rank systems on CAGR when sizing differs.
3. **The risk block is the good part.** Lowest drawdown on this book (~7% vs 44% buy-and-hold). The entry is the weak half versus Faber on a 5-year tech sample.
4. **Faber is the overlay to beat on this sample**, not the swing timer. Whipsaw in 2022 remains its cost.

This 7-name window is **not** where v1.2 was selected. Use §6d for that. Median Sharpe gaps under ~0.2 are noise here.

---

## 6c. Uncorrelated book, 2001-2026

Book: JPM, LMT, AMGN, PFE, MCD, BRK-B, EEM, BTC-USD. Mean pairwise daily-return
correlation **0.33**. Yahoo **total-return** bars. Reproduce with
`python -m backtesting.compare --book diverse`.

| System | Median Sharpe | Median CAGR | Median maxDD | Beats B&H |
|---|---|---|---|---|
| Buy & hold | **0.52** | 10.4% | 65.0% | — |
| TSMOM 12-month | 0.43 | 5.8% | 46.2% | 1/8 |
| Faber SMA200 (monthly) | 0.38 | 5.5% | 55.5% | 2/8 |
| Faber SMA200 (daily) | 0.32 | 3.9% | 54.0% | 1/8 |
| **EMA Pullback v1.2** | 0.30 | 0.8% | **9.7%** | 1/8 |
| Donchian 55/20 | 0.24 | 1.1% | 15.6% | 1/8 |
| RSI trend dip | 0.19 | 0.4% | 9.1% | 0/8 |
| Connors RSI(2) + trail | 0.18 | 1.4% | 40.8% | 1/8 |
| Connors RSI(2) | 0.12 | 0.6% | 30.7% | 0/8 |

What still holds versus §6b:

1. **Faber monthly vs daily.** Sampling frequency dominated length choice. Daily Faber round-trips JPM 118 times and can draw down worse than buy-and-hold.
2. **Faber's tech-book win did not generalize** to this book.
3. **Connors without a stop** is a 25-year loser and a 2007–09 survivor. The missing stop is the open Connors item, not EMA.
4. **v1.2 risk generalized; the entry is not an overlay.** Drawdown stays ~10% including BTC (vs 83% buy-and-hold). Sharpe is below buy-and-hold because the book is mostly cash.

---

## 6d. Disjoint-name hold-out (how v1.2 was selected)

The 15-name entry book (NVDA…IQSE.DE, including GLD) was **frozen**. Selection used 78 names with **zero ticker overlap** (metals SLV/CPER/PPLT/PALL, one stock per sector in IT/UK/DE/JP/KR/HK/EM, plus country/sector ETFs). See [`research/oos_holdout.md`](../research/oos_holdout.md).

That is the right validation for a **frozen published rule**: new assets, not a rolling parameter re-fit.

**Selected before looking at the hold-out**

- Overlay: **Faber SMA200 monthly** (best median Sharpe on 78 names; stable in 2015–2020 and 2021–2026).
- Swing: **EMA v1.2** (flat 0.20 / 0.20 on that split). TSMOM dropped (negative E[R] in 2015–2020). Confluence v2 lost to EMA on the train set — do not treat a 0.02 hold-out Sharpe gap as selection.

**Hold-out book (unseen):** Faber median Sharpe 0.74 at ~38% DD; EMA v1.2 0.56 at ~7% DD. GLD (metals transferred): EMA 0.63 Sharpe, 8.3% DD.

Pine: `pinescript/faber_sma200.pine` (allocation) and `pinescript/ema_gc_adaptive.pine` (swing).

---

## 7. Engine 0.1 contract

Spec only in this pass. Implementation is a later, cheaper-model job. Follow this contract; do not “improve” it.

### Data

- Alpaca Stock Historical Bars, **1Day**, split-adjusted (Alpaca default).
- Cache under `backtesting/data/` (gitignored). Fetch-if-missing is fine.
- Reuse [backtesting/alpaca/client_stub.py](../backtesting/alpaca/client_stub.py) as a **downloader**, not a broker. Bypass or fix `_to_timeframe` so `1Day` is actually `TimeFrame.Day`.
- Warmup: fetch starts ~300 calendar days before the backtest start (need ≥200 daily bars before the first signal).
- One symbol per run (e.g. SMH, QQQ, AAPL). No universe scan.

### Loop and fills

| Event | Rule |
|-------|------|
| Entry | Signal on bar T close → fill T+1 open |
| Stop | Live trail is from **prior close**. If `low <= trail`, fill `min(open, trail)` |
| Regime flatten | Next open after EMA50 crosses under EMA200 |
| Costs | Commission bps + optional slippage bps on every fill |
| Pyramiding | Forbidden. Ignore signals while not flat |

Do not update the trail from the same bar’s close and then allow that bar’s low to hit it.

### Layout

```
backtesting/
  alpaca/                 # existing fetch stub
  engine/
    types.py              # Bar, Position, Fill, Trade
    data.py               # load cache; optional fetch-if-missing
    broker.py             # cash, qty, single position, stop vs bar.low
    loop.py               # for bar in bars: strategy.on_bar → broker
    metrics.py            # from trade list
  strategies/
    ema_gc_adaptive.py    # DESIGN v1 — not a port of etf_bottom_finder
  cli.py
```

### Outputs

- `trades.csv`: entry_time, entry_px, exit_time, exit_px, qty, R, pnl, reason (`trail` or `regime`)
- `equity.csv`: date, equity, drawdown
- stdout: n trades, win rate, expectancy (R), avg hold days, max DD, time-in-market, profit factor

### Acceptance

- Synthetic fixture: known EMA50/200 geometry produces exactly one entry and a trail or regime exit at the expected price.
- One real symbol (SMH daily, 2018–2024) runs end-to-end from Alpaca cache.
- Trade count is selective (pullbacks, not every golden cross). If it is not, inspect the log — do not tune blindly.
- Every exit has reason `trail` or `regime`. No look-ahead in fills.

### Out of scope for 0.1

`etf_bottom_finder.pine`, walk-forward, parameter grids, paper orders, shorts, minute bars, weekly/OBV/Keltner.

---

## Appendix A — ETF Bottom Finder (overlay, not engine)

[pinescript/etf_bottom_finder.pine](pinescript/etf_bottom_finder.pine) is a **chart indicator** for discretionary lump-sum / add-zone curiosity on broad ETFs. It is not a swing strategy. Do not load it in the engine. Do not put an ATR trail on it.

**Intended chart:** weekly. Daily RSI(14) crossing 30 is not a macro bottom.

**Zone (visual only):**

- Price at or below `1.03 * SMA(200)`.
- Drawdown from the lookback peak ≥ 10%.
- RSI swept oversold (`lowest RSI` over the RSI length ≤ threshold, default 35) **and** RSI crosses back above 30, **or** close crosses back above the 200 SMA.

Invalidation for this overlay is “new lows / failed reclaim of the 200,” not a trailing stop. A lump-sum allocator must not be shaken out by a 2 ATR wick.

### Cross-ETF validation (2026-08)

The overlay was tested unchanged against five alternative weekly entry rules on
29 ETFs. Broad indexes were the development cohort; 18 sectors, themes, bonds,
gold, and commodities were held out for validation. See
[`research/portfolio_and_bottoms.md`](../research/portfolio_and_bottoms.md) and
reproduce with `python -m backtesting.bottom_finder`.

Keep the current rule. Across 200 signals it had:

- 72.5% of entries after the surrounding ±13-week local low;
- -4.8% median 13-week adverse excursion;
- 14.9% median one-year total return and 78.9% positive outcomes;
- +6.1% median one-year return over an ordinary eligible week in the same ETF;
- similar uplift on broad (+5.6%) and held-out (+6.7%) ETFs.

The first cross into a 20% drawdown bought closer to the exact low but entered
before the low 60% of the time and had negative excess return before 2013. Do not
replace confirmation with raw drawdown entry.
