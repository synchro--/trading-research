"""
Alpaca historical bars only — no orders.
Keys load from environment / gitignored .env via credentials.py.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

from backtesting.alpaca.credentials import alpaca_credentials, alpaca_data_feed

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
except Exception:  # pragma: no cover
    StockHistoricalDataClient = None  # type: ignore
    StockBarsRequest = None  # type: ignore
    TimeFrame = None  # type: ignore


@dataclass
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


class AlpacaProvider:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper: Optional[bool] = None,
    ):
        if api_key and api_secret:
            self.api_key, self.api_secret = api_key, api_secret
        else:
            self.api_key, self.api_secret = alpaca_credentials()
        self.paper = True if paper is None else paper
        if StockHistoricalDataClient is None:
            raise RuntimeError("alpaca-py not installed. Run: pip install alpaca-py python-dotenv")
        self.data_client = StockHistoricalDataClient(self.api_key, self.api_secret)
        self.feed = alpaca_data_feed()

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Bar]:
        tf = self._to_timeframe(timeframe)
        start_dt = self._parse_dt(start) if start else None
        end_dt = self._parse_dt(end) if end else None
        from alpaca.data.enums import Adjustment, DataFeed

        feed_map = {
            "iex": DataFeed.IEX,
            "sip": DataFeed.SIP,
            "delayed_sip": DataFeed.DELAYED_SIP,
        }
        preferred = feed_map.get(self.feed, DataFeed.IEX)
        feeds = [preferred]
        if DataFeed.IEX not in feeds:
            feeds.append(DataFeed.IEX)

        raw_bars = []
        last_err: Exception | None = None
        used_feed = preferred
        for feed in feeds:
            try:
                req = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=tf,
                    start=start_dt,
                    end=end_dt,
                    limit=limit,
                    adjustment=Adjustment.SPLIT,
                    feed=feed,
                )
                resp = self.data_client.get_stock_bars(req)
                raw_bars = resp[symbol] if hasattr(resp, "__getitem__") else resp.data.get(symbol, [])  # type: ignore
                if raw_bars:
                    used_feed = feed
                    break
            except Exception as e:
                last_err = e
                raw_bars = []
        if not raw_bars and last_err is not None:
            raise last_err
        self._last_feed = str(used_feed)

        out: List[Bar] = []
        for b in raw_bars:
            t = getattr(b, "timestamp", None) or getattr(b, "t", None) or b["t"]
            out.append(
                Bar(
                    t=str(t),
                    o=float(getattr(b, "open", None) or getattr(b, "o", None) or b["o"]),
                    h=float(getattr(b, "high", None) or getattr(b, "h", None) or b["h"]),
                    l=float(getattr(b, "low", None) or getattr(b, "l", None) or b["l"]),
                    c=float(getattr(b, "close", None) or getattr(b, "c", None) or b["c"]),
                    v=float(getattr(b, "volume", None) or getattr(b, "v", None) or b["v"]),
                )
            )
        return out

    @staticmethod
    def write_csv(bars: Iterable[Bar], out_path: str) -> None:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t", "o", "h", "l", "c", "v"])
            for b in bars:
                w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])

    def submit_market_order(self, *_, **__):
        raise NotImplementedError("Orders are out of scope — historical data only.")

    def cancel_all_orders(self) -> None:
        raise NotImplementedError("Orders are out of scope — historical data only.")

    @staticmethod
    def _parse_dt(value: str):
        from datetime import datetime, timezone

        raw = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _to_timeframe(tf: str):
        from alpaca.data.timeframe import TimeFrameUnit

        key = tf.replace(" ", "")
        mapping = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        if key in mapping and mapping[key] is not None:
            return mapping[key]
        n = int("".join(ch for ch in key if ch.isdigit()) or "1")
        if "Min" in key:
            return TimeFrame(n, TimeFrameUnit.Minute)
        if "Hour" in key:
            return TimeFrame(n, TimeFrameUnit.Hour)
        return TimeFrame(1, TimeFrameUnit.Day)
