"""Load cached daily bars; fetch from Alpaca if missing. Yahoo/Stooq fallback if no keys."""
from __future__ import annotations

import csv
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backtesting.engine.types import Bar

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "backtesting" / "data"


def _cache_path(symbol: str, provider: str = "") -> Path:
    suffix = f"_{provider}" if provider else ""
    return DATA_DIR / f"{symbol.upper().replace('-', '')}_1d{suffix}.csv"


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


# Alpaca's `adjustment` flag is a no-op on the IEX tier: RAW, SPLIT and ALL all come
# back unadjusted, so a 10:1 split reads as a -90% bar and every strategy "sees" a
# crash that never happened. Detect and back-adjust ourselves.
_SPLIT_RATIOS = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 15.0, 20.0, 30.0, 50.0]
_SPLIT_TOL = 0.04


def _match_split_ratio(gap: float) -> float | None:
    """Return the split ratio if an overnight gap looks like a clean n:1 or 1:n split."""
    for r in _SPLIT_RATIOS:
        for cand in (r, 1.0 / r):
            if abs(gap / cand - 1.0) <= _SPLIT_TOL:
                return cand
    return None


def adjust_splits(bars: list[Bar], symbol: str = "") -> tuple[list[Bar], list[str]]:
    """Back-adjust prices for unadjusted splits. Returns (bars, notes).

    Measured on prev_close -> today's open: the split lands exactly on the overnight
    boundary, while close-to-close also carries that day's real move and can miss the
    ratio (KLAC's 10:1 reads as 9.47 on closes but 10.14 on the open).
    """
    notes: list[str] = []
    if len(bars) < 2:
        return bars, notes
    splits: list[tuple[int, float]] = []
    for i in range(1, len(bars)):
        prev_c, o, c = bars[i - 1].c, bars[i].o, bars[i].c
        if prev_c <= 0 or o <= 0 or c <= 0:
            continue
        gap = prev_c / o
        if 0.72 < gap < 1.4:
            continue
        ratio = _match_split_ratio(gap)
        if ratio is not None:
            splits.append((i, ratio))
            notes.append(f"{symbol} split {ratio:g}:1 on {bars[i].t} ({prev_c:.2f} -> {o:.2f} open)")
    if not splits:
        return bars, notes
    out = list(bars)
    for idx, ratio in splits:
        for j in range(idx):
            b = out[j]
            out[j] = Bar(t=b.t, o=b.o / ratio, h=b.h / ratio, l=b.l / ratio, c=b.c / ratio, v=b.v * ratio)
    return out, notes


def _has_alpaca_keys() -> bool:
    try:
        from backtesting.alpaca.credentials import alpaca_credentials

        alpaca_credentials()
        return True
    except Exception:
        return False


def fetch_alpaca(symbol: str, start: str, end: str) -> tuple[list[Bar], str]:
    from backtesting.alpaca.client_stub import AlpacaProvider

    provider = AlpacaProvider()
    raw = provider.fetch_bars(symbol, timeframe="1Day", start=start, end=end)
    bars = [
        Bar(t=str(b.t)[:10], o=b.o, h=b.h, l=b.l, c=b.c, v=b.v)
        for b in raw
        if b.h >= b.l and b.c > 0
    ]
    feed = str(getattr(provider, "_last_feed", "iex"))
    return bars, feed


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
    # Yahoo's quote OHLC is split-adjusted but not dividend-adjusted, which makes
    # dividend payers look far worse than they were (PFE shows a negative 26-year
    # return on price alone). Rescale OHLC by adjclose/close to get a total-return
    # series, so buy-and-hold is not penalised against strategies that sit in cash.
    adj = None
    try:
        adj = result["indicators"]["adjclose"][0]["adjclose"]
    except (KeyError, IndexError, TypeError):
        adj = None
    bars: list[Bar] = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if o is None or h is None or l is None or c is None or c == 0:
            continue
        k = 1.0
        if adj is not None and i < len(adj) and adj[i] is not None:
            k = float(adj[i]) / float(c)
        day = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
        bars.append(
            Bar(t=day, o=float(o) * k, h=float(h) * k, l=float(l) * k, c=float(c) * k,
                v=float(q["volume"][i] or 0))
        )
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
    provider: str = "auto",
) -> tuple[list[Bar], str]:
    """Return (bars, source). Bars include warmup history before `start`.

    provider: "auto" picks Alpaca for recent windows and Yahoo for anything
    reaching before Alpaca's IEX history (which starts mid-2020 on this tier).
    Pass "yahoo" or "alpaca" to force one. Caches are kept per provider so a
    deep Yahoo series never gets mixed with a shallow Alpaca one.
    """
    fetch_start = (datetime.fromisoformat(start) - timedelta(days=warmup_calendar_days)).date().isoformat()
    if provider == "auto":
        provider = "yahoo" if fetch_start < "2020-08-01" else "alpaca"

    cache = _cache_path(symbol, "" if provider == "alpaca" else provider)
    if force or not cache.exists():
        bars: list[Bar] = []
        errors: list[str] = []
        order = ["alpaca", "yahoo", "stooq"] if provider == "alpaca" else ["yahoo", "stooq", "alpaca"]
        for prov in order:
            if bars:
                break
            try:
                if prov == "alpaca":
                    if not _has_alpaca_keys():
                        errors.append("alpaca: no ALPACA_API_KEY_ID/SECRET in env")
                        continue
                    bars, feed = fetch_alpaca(symbol, fetch_start, end)
                    source = f"alpaca:{feed}"
                elif prov == "yahoo":
                    bars = fetch_yahoo(symbol, fetch_start, end)
                    source = "yahoo"
                else:
                    bars = fetch_stooq(symbol)
                    source = "stooq"
            except Exception as e:
                errors.append(f"{prov}: {e}")
        if not bars:
            raise RuntimeError(f"No bars for {symbol}: " + " | ".join(errors))
        write_csv(bars, cache)
    else:
        bars = read_csv(cache)
        source = f"cache:{cache.name}"

    bars = [b for b in bars if b.t <= end]
    if not bars:
        raise RuntimeError(f"No bars for {symbol} up to {end}")
    bars, split_notes = adjust_splits(bars, symbol)
    for note in split_notes:
        print(f"  [data] back-adjusted {note}")
    if split_notes:
        source += "+splitadj"
    return bars, source
