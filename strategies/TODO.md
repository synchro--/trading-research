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

- [ ] Alpaca daily fetch + cache under `backtesting/data/` (gitignored). Reuse `backtesting/alpaca/client_stub.py` as downloader only. Make `1Day` actually `TimeFrame.Day`.
- [ ] Single-position broker: T+1 open entries, prior-bar trail vs `low`, fill `min(open, trail)` on a stop, regime flatten next open, commission + slippage bps.
- [ ] `backtesting/strategies/ema_gc_adaptive.py` from DESIGN v1 numbers (table in DESIGN §3.7).
- [ ] `backtesting/engine/` loop, types, metrics.
- [ ] CLI: `python -m backtesting.cli --symbol SMH --start 2018-01-01 --end 2024-12-31`.
- [ ] Synthetic fixture: one known entry and a trail or regime exit at the expected price.
- [ ] One real run (SMH daily 2018–2024) from cache → `trades.csv` + `equity.csv` + stdout summary.

**Acceptance**

- Every exit reason is `trail` or `regime`.
- No look-ahead in fills.
- Trade count is selective (pullbacks, not every golden cross). If not, inspect the log — do not tune.
- `etf_bottom_finder` is not imported anywhere under `backtesting/strategies/`.

**Out of scope**

Walk-forward, parameter grids, paper orders, shorts, minute bars, weekly/OBV/Keltner, live trading.
