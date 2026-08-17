"""Load Alpaca credentials from the environment. Never hardcode keys."""
from __future__ import annotations

import os
from pathlib import Path

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parents[1]


def load_alpaca_env() -> None:
    """Load gitignored .env files. Process env wins over file values."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    # Local secrets first, then repo-root .env. Do not override a real env var.
    load_dotenv(_DIR / ".env", override=False)
    load_dotenv(_ROOT / ".env", override=False)


def alpaca_credentials() -> tuple[str, str]:
    load_alpaca_env()
    key = (os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID") or "").strip()
    secret = (os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY") or "").strip()
    if not key or not secret:
        raise RuntimeError(
            "Missing Alpaca keys. Copy backtesting/alpaca/.env.example to "
            "backtesting/alpaca/.env and set ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY."
        )
    return key, secret


def alpaca_data_feed() -> str:
    load_alpaca_env()
    return (os.getenv("ALPACA_DATA_FEED") or "iex").strip().lower()
