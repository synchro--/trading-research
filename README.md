# Trading Strategies (Pine v6 + API backtesting)

This repo hosts trading strategies for TradingView (Pine Script v6) and notes for running/backtesting ideas via external APIs.

## Structure
- `strategies/DESIGN.md` — frozen v1 spec for the swing system (start here)
- `strategies/TODO.md` — work queue, including engine 0.1 for a later pass
- `strategies/pinescript/` — ready-to-paste Pine
  - `ema_gc_adaptive.pine` — v1 swing strategy (mirrors DESIGN.md)
  - `etf_bottom_finder.pine` — chart overlay only; not an engine strategy
  - `templates/strategy_template.pine` — starter template (Pine v6)
- `backtesting/` — Alpaca fetch stub; engine 0.1 is specified in DESIGN.md §7, not built yet
- `research/` — raw ideas, links, and experiments

## Quick start (TradingView)
1. Open TradingView → Pine Editor.
2. Copy a file from `strategies/pinescript/` and paste into a new script.
3. Ensure the header is `//@version=6` (the template already is).
4. Save and add to chart; tweak inputs in the sidebar; run a backtest.

## Creating a new strategy
- Copy `strategies/pinescript/templates/strategy_template.pine` and modify signals, risk, and exits.
- Keep file names descriptive, e.g. `rsi_mean_revert_v1.pine`.

## API backtesting/integration
- See `backtesting/provider-notes.md` for integration placeholders (REST, credentials, data layout).
- This repo does not include provider SDKs or secrets. Put API keys in environment variables or a local `.env` ignored by git.

## Conventions
- Pine version: v6 for new scripts.
- Keep signals and risk controls clearly separated by comment blocks.
- Document assumptions (fees, slippage, session, instrument) at the top of each script.

## Disclaimer
This code is for research/education. No financial advice. Trade at your own risk.
