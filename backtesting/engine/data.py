"""Load cached daily bars; fetch from Alpaca if missing. Yahoo/Stooq fallback if no keys."""
from __future__ import annotations

import csv
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtesting.engine.types import Bar

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backtesting" / "data"


def _cache_path(symbol: str) -> Path:
    return DATA_DIR / f"{symbol.upper()}_1d.csv"


def write_csv(bars: list[Bar], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "o", "h", "l", "c", "v"])
        for b in bars:
            w.writerow([b.t, b.o, b.h, b.l, b.c, b.v])


def read_csv(path: Path) -> list[Bar]:
    out: list[Bar] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            out.append(
                Bar(
                    t=row["t"][:10],
                    o=float(row["o"]),
                    h=float(row["h"]),
                    l=float(row["l"]),
                    c=float(row["c"]),
                    v=float(row.get("v") or 0),
                )
            )
    out.sort(key=lambda b: b.t)
    return out


def _has_alpaca_keys() -> bool:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / "backtesting" / "alpaca" / ".env")
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    return bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_SECRET_KEY"))


def fetch_alpaca(symbol: str, start: str, end: str) -> list[Bar]:
    from backtesting.alpaca.client_stub import AlpacaProvider

    provider = AlpacaProvider()
    raw = provider.fetch_bars(symbol, timeframe="1Day", start=start, end=end)
    return [
        Bar(t=str(b.t)[:10], o=b.o, h=b.h, l=b.l, c=b.c, v=b.v)
        for b in raw
        if b.h >= b.l and b.c > 0
    ]


def _http_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (research-backtest; +https://github.com/synchro--/trading-research)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_yahoo(symbol: str, start: str, end: str) -> list[Bar]:
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2 = int((datetime.fromisoformat(end).replace(tzinfo=timezone.utc) + timedelta(days=2)).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?interval=1d&period1={p1}&period2={p2}&events=div%7Csplit"
    )
    payload = _http_json(url)
    result = payload["chart"]["result"][0]
    ts = result["timestamp"]
    q = result["indicators"]["quote"][0]
    bars: list[Bar] = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if o is None or h is None or l is None or c is None:
            continue
        day = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        bars.append(Bar(t=day, o=float(o), h=float(h), l=float(l), c=float(c), v=float(q["volume"][i] or 0)))
    bars.sort(key=lambda b: b.t)
    return bars


def fetch_stooq(symbol: str) -> list[Bar]:
    slug = symbol.lower()
    if "." not in slug:
        slug = f"{slug}.us"
    url = f"https://stooq.com/q/d/l/?s={slug}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode()
    bars: list[Bar] = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        try:
            bars.append(
                Bar(
                    t=row["Date"][:10],
                    o=float(row["Open"]),
                    h=float(row["High"]),
                    l=float(row["Low"]),
                    c=float(row["Close"]),
                    v=float(row.get("Volume") or 0),
                )
            )
        except (KeyError, ValueError):
            continue
    bars.sort(key=lambda b: b.t)
    return bars


def load_bars(
    symbol: str,
    start: str,
    end: str,
    *,
    warmup_calendar_days: int = 300,
    force: bool = False,
) -> tuple[list[Bar], str]:
    """Return (bars, source). Bars include warmup history before `start`."""
    fetch_start = (datetime.fromisoformat(start) - timedelta(days=warmup_calendar_days)).date().isoformat()
    cache = _cache_path(symbol)
    source = "cache"
    if force or not cache.exists():
        bars: list[Bar] = []
        errors: list[str] = []
        if _has_alpaca_keys():
            try:
                bars = fetch_alpaca(symbol, fetch_start, end)
                source = "alpaca"
            except Exception as e:
                errors.append(f"alpaca: {e}")
        else:
            errors.append("alpaca: no ALPACA_API_KEY_ID/SECRET in env")
        if not bars:
            try:
                bars = fetch_yahoo(symbol, fetch_start, end)
                source = "yahoo"
            except Exception as e:
                errors.append(f"yahoo: {e}")
        if not bars:
            try:
                bars = fetch_stooq(symbol)
                source = "stooq"
            except Exception as e:
                errors.append(f"stooq: {e}")
        if not bars:
            raise RuntimeError(f"No bars for {symbol}: " + " | ".join(errors))
        write_csv(bars, cache)
    else:
        bars = read_csv(cache)
        source = f"cache:{cache.name}"

    bars = [b for b in bars if b.t <= end]
    if not bars:
        raise RuntimeError(f"No bars for {symbol} up to {end}")
    return bars, source
