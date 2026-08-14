# EMA Pullback Swing

Source of truth for the long-only swing system. Other agents implement from this file and [TODO.md](TODO.md). Do not invent rules that are not written here.

**Status:** v1 frozen. Do not retune RSI, ATR, or EMA lengths until engine 0.1 has produced a baseline trade log.

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
| [pinescript/ema_gc_adaptive.pine](pinescript/ema_gc_adaptive.pine) | TradingView mirror of v1 | Yes — this is what 0.1 mirrors |
| [pinescript/etf_bottom_finder.pine](pinescript/etf_bottom_finder.pine) | Chart overlay for discretionary ETF adds | **No** |
| `golden_cross_strategy.pine`, `rsi_strategy.pine`, `bollinger_bands_strategy.pine` | Legacy examples | No |

`macro_entry.pine` was renamed to `ema_gc_adaptive.pine`. That file is the strategy, not an overlay.

---

## 3. v1 (frozen)

All series are **daily** unless noted. Indicators: EMA(close, 50), EMA(close, 200), ATR(14), RSI(close, 14).

### 3.1 Regime

Bull regime when `EMA50 > EMA200`. No new longs otherwise.

The 50/200 golden cross is a **regime event**, not an entry. Do not buy the cross.

### 3.2 Entry

Signal is evaluated on bar **T close**. Engine fill is bar **T+1 open**. Flat only (no pyramiding).

All of the following must be true:

1. `EMA50 > EMA200` (already in bull regime; the cross itself does not qualify).
2. `close` crosses above `EMA50` (`ta.crossover(close, ema50)`).
3. RSI(14) printed **below 50** at least once in the last **8** bars (a dip happened).
4. RSI(14) on bar T is in **[40, 65]** (recovering, not washed out, not chasing).

### 3.3 Initial risk and size

- `initial_risk` = `3.5 * ATR(14)` **frozen on the signal/entry bar**. Do not update it later.
- Position size = `(equity * 0.015) / initial_risk` (1.5% of equity at risk).
- If `initial_risk <= 0`, skip the trade.

### 3.4 Adaptive trail

Ratchet **up only** (longs). `R = (close - entry) / initial_risk`.

```
active_mult = 3.5  if R < 1.5
active_mult = 2.0  if R >= 1.5
candidate   = close - active_mult * ATR(14)
trail       = max(trail, candidate)
```

On the first bar in the trade, `trail = entry - initial_risk` (not `close - ATR * mult`).

**Same-bar rule (required).** Tomorrow’s stop is known at today’s close. Do not compute a new trail from bar T’s close and allow bar T’s low to hit it. Engine: the live stop on bar T is the trail from bar T−1 (or the initial stop on the entry bar). Pine: `process_orders_on_close=true` and the exit uses the **already-ratcheted** trail, then the trail is updated for the next bar.

`initial_risk` stays frozen. The trail distance uses **live** ATR. Do not “fix” that mix in v1; it is documented in §5.

### 3.5 Exits

Exactly two exits:

1. **Trail.** If `low <= trail`, fill at `min(open, trail)` (gap through the stop uses the open). Reason: `trail`.
2. **Regime break.** If `EMA50` crosses under `EMA200`, flatten at the **next open**. Reason: `regime`.

No take-profit limit. No time stop in v1.

### 3.6 Costs (engine)

Apply commission bps and optional slippage bps on every fill. TradingView without costs is not the baseline.

### 3.7 Defaults (do not change in v1)

| Parameter | Value |
|-----------|-------|
| Fast EMA | 50 |
| Slow EMA | 200 |
| ATR length | 14 |
| RSI length | 14 |
| RSI dip lookback | 8 bars |
| RSI band | 40–65 |
| Base ATR multiple | 3.5 |
| Tight ATR multiple | 2.0 |
| Tighten at | 1.5R |
| Risk per trade | 1.5% of equity |

---

## 4. Why these rules

Classical 50/200 + fixed ATR fails in three ways this system is built to avoid:

1. **Chop.** Buying every 50-cross inside a range produces high churn. The regime gate (`EMA50 > EMA200`) plus “reclaim after a dip” is the filter.
2. **Fixed ATR asymmetry.** A tight stop (1.5–2.0 ATR) shakes out healthy growth names; a static wide stop (4.5 ATR) gives back a trend. Wide (3.5) until 1.5R, then 2.0, matches how those names actually move. At 1.5R, price is `entry + 5.25 ATR`; the tight stop sits near `close - 2 ATR` and locks roughly 0.9R.
3. **Buying the golden cross.** On SMH/QQQ the 50/200 cross often prints 15–25% off the low. A 3.5 ATR stop under that bar is a late entry with a wide stop. v1 waits for the first qualifying EMA50 reclaim instead.

`RSI >= 45` at the reclaim bar (the previous Pine) kept late reclaims (RSI 55–70) and skipped deeper ones (RSI 35–44). The v1 band does the opposite: require evidence of a dip (`RSI < 50` in the last 8 bars) and refuse both washouts (`RSI < 40`) and chases (`RSI > 65`).

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

Blocked until engine 0.1 has a baseline `trades.csv`. Then, in order:

1. Weekly EMA slope as a **gate** (not a second entry). `request.security` / resampled weekly close.
2. RSI band retune from the trade log (not from intuition).
3. Optional time stop (e.g. flatten after N bars if still `R < 1`).
4. Evaluate Keltner/vol bands vs static ATR multiples.
5. OBV / accumulation last, if at all.

Do not add these in engine 0.1.

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
