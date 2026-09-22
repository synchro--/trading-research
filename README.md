# Trading Strategies (Pine v6 + API backtesting)

This repo hosts trading strategies for TradingView (Pine Script v6) and notes for running/backtesting ideas via external APIs.

## Structure
- `strategies/DESIGN.md` — frozen v1 spec for the swing system (start here)
- `strategies/TODO.md` — work queue, including engine 0.1 for a later pass
- `strategies/pinescript/` — ready-to-paste Pine
  - `ema_gc_adaptive.pine` — v1 swing strategy (mirrors DESIGN.md)
  - `etf_bottom_finder.pine` — chart overlay only; not an engine strategy
  - `templates/strategy_template.pine` — starter template (Pine v6)
- `backtesting/` — daily single-symbol engine plus portfolio and ETF-entry experiments
- `research/` — raw ideas, links, and experiment reports
  - `dca_master_report.md` — consolidated report with figures: LS vs DCA, dip timing, money-market cushions, final tournament
  - `portfolio_and_bottoms.md` — equal-weight basket and 29-ETF lump-sum results
  - `dca_vs_lumpsum.md` — DCA vs lump-sum over rolling 10-20y windows, 4 classic portfolios
  - `dip_dca.md` — oracle dip timing vs mid-month DCA + dip-triggered contribution rules
  - `mm_cushion.md` — 30k money-market cushion + 500/mo: lump sum vs parked vs dip-harvested reserve
  - `hybrid_split.md` — staged windfall deployment: α lump + tail DCA, regret frontier
  - `crash_deploy.md` — cash-is-king: wait for a −20%/−30% drawdown, then deploy
  - `deep_history.md` — lump sum vs DCA on US data since 1926 (Ken French + FRED)

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

## Reproduce research
```bash
uv run python -m backtesting.compare --book diverse
uv run python -m backtesting.portfolio
uv run python -m backtesting.bottom_finder
uv run python -m backtesting.dca_vs_lumpsum --reuse-cache
uv run python -m backtesting.mm_cushion --reuse-cache
uv run python -m backtesting.dip_dca --reuse-cache
uv run python -m backtesting.hybrid_split --reuse-cache
uv run python -m backtesting.crash_deploy --reuse-cache
uv run python -m backtesting.deep_history
uv run python -m backtesting.research_plots
uv run python -m unittest discover -s backtesting/tests -v
```

Deep-history experiments use Yahoo total-return bars; recent single-stock runs can
use Alpaca IEX. Generated data and JSON results live under gitignored
`backtesting/data/`.

## Conventions
- Pine version: v6 for new scripts.
- Keep signals and risk controls clearly separated by comment blocks.
- Document assumptions (fees, slippage, session, instrument) at the top of each script.

## Disclaimer
This code is for research/education. No financial advice. Trade at your own risk.
