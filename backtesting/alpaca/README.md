# Alpaca Integration Stub

This is a minimal, non-production stub to help you experiment with Alpaca for data retrieval and (eventual) paper trading.

What’s included
- `client_stub.py` — tiny wrapper that:
  - loads API keys from environment variables (or `.env` if `python-dotenv` is installed)
  - fetches historical bars to a Python list or CSV
  - includes placeholders for order submission/cancellation (paper trading)
- `examples/fetch_bars.py` — example: download bars and write a CSV.
- `.env.example` — copy to `.env` and fill in your keys locally (never commit secrets).

Environment variables
- `ALPACA_API_KEY_ID`
- `ALPACA_API_SECRET_KEY`
- Optional: `ALPACA_PAPER` ("true"/"false"; default: true)

Install (optional venv recommended)
```bash path=null start=null
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install alpaca-py python-dotenv
```

Run the example
```bash path=null start=null
cp backtesting/alpaca/.env.example backtesting/alpaca/.env  # then edit with your keys
python backtesting/alpaca/examples/fetch_bars.py --symbol AAPL --timeframe 1Day --start 2024-01-01 --end 2024-01-31 --out backtesting/data/aapl_2024_01_1d.csv
```

Notes
- This is a learning scaffold, not production code.
- Keep raw data under `backtesting/data/` (gitignored).
- For live trading, add robust error handling, retries, and a persistent order/trade log.
