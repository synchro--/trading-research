"""
Alpaca integration stub (non-production)
- Loads creds from environment or .env (if python-dotenv is installed)
- Fetches historical bars
- Placeholders for paper order actions
"""
from __future__ import annotations
import os
import csv
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Optional .env support
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except Exception:
    pass

ALPACA_API_KEY_ID = os.getenv("ALPACA_API_KEY_ID")
ALPACA_API_SECRET_KEY = os.getenv("ALPACA_API_SECRET_KEY")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"

# Lazy imports so the file can be imported without alpaca-py installed
try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    # from alpaca.trading.requests import MarketOrderRequest  # For future use
    # from alpaca.trading.enums import OrderSide, TimeInForce
except Exception:  # pragma: no cover - not installed yet
    StockHistoricalDataClient = None  # type: ignore
    StockBarsRequest = None  # type: ignore
    TimeFrame = None  # type: ignore
    TradingClient = None  # type: ignore


@dataclass
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


class AlpacaProvider:
    def __init__(self,
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None,
                 paper: Optional[bool] = None):
        self.api_key = api_key or ALPACA_API_KEY_ID
        self.api_secret = api_secret or ALPACA_API_SECRET_KEY
        self.paper = ALPACA_PAPER if paper is None else paper

        if not self.api_key or not self.api_secret:
            raise RuntimeError("Missing ALPACA_API_KEY_ID/ALPACA_API_SECRET_KEY in env or .env")
        if StockHistoricalDataClient is None:
            raise RuntimeError("alpaca-py not installed. Run: pip install alpaca-py python-dotenv")

        self.data_client = StockHistoricalDataClient(self.api_key, self.api_secret)
        # Trading client for future paper orders
        self.trading_client = TradingClient(self.api_key, self.api_secret, paper=self.paper)

    # --- Data ---
    def fetch_bars(self,
                   symbol: str,
                   timeframe: str = "1Min",
                   start: Optional[str] = None,
                   end: Optional[str] = None,
                   limit: Optional[int] = None) -> List[Bar]:
        tf = self._to_timeframe(timeframe)
        req = StockBarsRequest(symbol_or_symbols=symbol,
                               timeframe=tf,
                               start=start,
                               end=end,
                               limit=limit)
        resp = self.data_client.get_stock_bars(req)
        bars = resp[symbol] if hasattr(resp, '__getitem__') else resp.data.get(symbol, [])  # type: ignore
        out: List[Bar] = []
        for b in bars:
            # Forwards-compat: b may expose attributes or mapping
            t = getattr(b, 'timestamp', None) or getattr(b, 't', None) or b["t"]
            out.append(Bar(
                t=str(t),
                o=float(getattr(b, 'open', None) or getattr(b, 'o', None) or b["o"]),
                h=float(getattr(b, 'high', None) or getattr(b, 'h', None) or b["h"]),
                l=float(getattr(b, 'low', None) or getattr(b, 'l', None) or b["l"]),
                c=float(getattr(b, 'close', None) or getattr(b, 'c', None) or b["c"]),
                v=float(getattr(b, 'volume', None) or getattr(b, 'v', None) or b["v"]))
            )
        return out

    @staticmethod
    def write_csv(bars: Iterable[Bar], out_path: str) -> None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(["t", "o", "h", "l", "c", "v"])  # ISO8601 ts, OHLCV
            for b in bars:
                w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])

    # --- Trading (placeholders) ---
    def submit_market_order(self, *_, **__):  # TODO: implement using MarketOrderRequest
        raise NotImplementedError("Order placement not implemented in the stub.")

    def cancel_all_orders(self) -> None:  # TODO: implement
        raise NotImplementedError("Cancel orders not implemented in the stub.")

    # --- Helpers ---
    @staticmethod
    def _to_timeframe(tf: str):
        tf_map = {
            "1Min": getattr(TimeFrame, 'Minute', None) or TimeFrame(1, 'Min'),
            "5Min": getattr(TimeFrame, 'Minute', None) or TimeFrame(5, 'Min'),
            "15Min": getattr(TimeFrame, 'Minute', None) or TimeFrame(15, 'Min'),
            "1Hour": getattr(TimeFrame, 'Hour', None) or TimeFrame(1, 'Hour'),
            "1Day": getattr(TimeFrame, 'Day', None) or TimeFrame(1, 'Day'),
        }
        if tf in tf_map and tf_map[tf] is not None:
            # Some alpaca-py versions use enums like TimeFrame.Minute; newer may use values
            val = tf_map[tf]
            return val if isinstance(val, TimeFrame) else TimeFrame.Minute  # best-effort fallback
        # Fallback: try to interpret common cases
        if hasattr(TimeFrame, 'from_str'):
            return TimeFrame.from_str(tf)  # type: ignore
        return TimeFrame.Day  # default fallback
