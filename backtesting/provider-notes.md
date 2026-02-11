# Backtesting & Provider Notes

This folder holds notes and stubs for integrating external data/broker APIs for backtesting or live-trading experiments.

## What to capture here
- Data acquisition (symbols, resolutions, history limits, corporate actions handling)
- Order model (market/limit/stop, partial fills, fees, slippage assumptions)
- Portfolio model (cash, leverage, margin, shorting rules)
- Result artifacts (equity curve CSV, trade log CSV/JSON, metrics)

## Placeholders
- Provider: <your provider name(s)>
- Auth: environment variables (e.g., `{{PROVIDER_API_KEY}}`) loaded locally — do not commit secrets.
- Data layout: store raw data under `backtesting/data/` (gitignored).

## Next steps
- Define a minimal schema for candles/trades and a converter into your backtest engine format.
- Add example scripts/notebooks (keep them out of git or commit only synthetic data).
