# Work queue

Follow [DESIGN.md](DESIGN.md). Do not invent rules. Check boxes as you finish. Engine 0.1 is a later job — spec is already in DESIGN §7.

---

## Do not

- Load or port `etf_bottom_finder.pine` into the engine.
- Optimize RSI / ATR / EMA lengths before a baseline `trades.csv` exists.
- Add weekly, OBV, or Keltner in 0.1 (those are v2).
- Compute a new trail from bar T’s close and fill bar T’s low against it.
- Reintroduce golden-cross entries, `RSI >= 45` as the only reclaim filter, or a fake ADX (2-bar EMA slope).
- Treat `ema_gc_adaptive.pine` as an overlay — it is the strategy.

---

## This pass (design + Pine)

- [x] Replace `DESIGN.md` with the v1 operating spec.
- [x] Add this `TODO.md`.
- [x] Update `pinescript/ema_gc_adaptive.pine` to DESIGN v1 (reclaim-only, RSI band, regime flatten, lagged trail) plus TRAIL / SAFE flags.
- [x] Overlay hygiene on `pinescript/etf_bottom_finder.pine` (entry-zone flags only; no ATR trail).

---

## Engine 0.1 (later — cheaper model)

Implement DESIGN.md §7. Mirror `ema_gc_adaptive.pine` / v1. Do not implement in the design pass.

- [x] Alpaca daily fetch + cache under `backtesting/data/` (gitignored). Reuse `backtesting/alpaca/client_stub.py` as downloader only. Make `1Day` actually `TimeFrame.Day`. Yahoo fallback if keys are missing.
- [x] Single-position broker: T+1 open entries, prior-bar trail vs `low`, fill `min(open, trail)` on a stop, regime flatten next open, commission + slippage bps.
- [x] `backtesting/strategies/ema_gc_adaptive.py` from DESIGN v1 numbers (table in DESIGN §3.7).
- [x] `backtesting/engine/` loop, types, metrics.
- [x] CLI: `python -m backtesting.cli --symbol SMH --start 2018-01-01 --end 2024-12-31`.
- [x] Synthetic fixture: one known entry and a trail or regime exit at the expected price.
- [x] One real run (SMH daily 2018–2024) from cache → `trades.csv` + `equity.csv` + stdout summary.

**Acceptance**

- Every exit reason is `trail` or `regime`.
- No look-ahead in fills.
- Trade count is selective (pullbacks, not every golden cross). If not, inspect the log — do not tune.
- `etf_bottom_finder` is not imported anywhere under `backtesting/strategies/`.

**Out of scope**

Walk-forward, parameter grids, paper orders, shorts, minute bars, weekly/OBV/Keltner, live trading.

---

## Literature benchmark pass (done — see DESIGN §6b)

- [x] Buy-and-hold benchmark per symbol. Nothing below it on Sharpe is an "edge".
- [x] Split-adjust prices in the loader. Alpaca's IEX tier ignores `adjustment=`; KLAC's 10:1 split read as a -90% crash and poisoned every KLAC number in the prior run.
- [x] Sizing modes (`risk`, `equity`, `voltarget`) and an opt-out from the ATR trail, so no-stop published systems run under their own rules.
- [x] Faber SMA200, Connors RSI(2), TSMOM 12-month, Connors + ATR trail.
- [x] Regime split (2022 bear vs 2023-2026) and a warmup-safe start date.

## Next

- [ ] Fix the warmup hole properly: the loop should refuse to trade until every indicator a strategy uses is non-NaN, instead of relying on the caller to pick a safe `--start`.
- [ ] Decide on the RSI gate in v1 — the data says it filters nothing. Delete it or justify it from a trade log.
- [ ] Longer and wider sample before promoting anything: pre-2020 history (needs a non-Alpaca source) and non-tech names, to break the correlation in the current book.
- [ ] If chasing Faber: test a buffer band around the SMA to cut the 2022 whipsaw. That is a parameter change — needs the wider sample first, or it is curve-fitting.
