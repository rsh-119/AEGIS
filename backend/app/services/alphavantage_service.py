"""
alphavantage_service.py — Alpha Vantage as a supplementary data source.

Supports Indian stocks via BSE suffix (e.g. RELIANCE.BSE, TCS.BSE).
NSE tickers (RELIANCE.NS) are auto-converted to BSE format on call.

Free-tier limit: 25 req/day — all responses are cached aggressively in Redis.
Cache TTLs: quotes = 5 min, daily_series = 6 h, so we burn at most ~5 calls/day
during active use.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import httpx

from app.core.cache import cache
from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_BASE = "https://www.alphavantage.co/query"


class _AVKeyPool:
    """Round-robin AV key pool; marks a key exhausted when AV returns its daily-limit message."""

    def __init__(self) -> None:
        self._keys: list[str] = []
        self._idx  = 0
        self._lock = threading.Lock()
        self._exhausted: dict[str, float] = {}

    def load(self, keys: list[str]) -> None:
        self._keys = [k for k in keys if k.strip()]

    def next_key(self) -> str:
        if not self._keys:
            return ""
        now = time.time()
        with self._lock:
            for _ in range(len(self._keys)):
                key = self._keys[self._idx % len(self._keys)]
                self._idx += 1
                if now >= self._exhausted.get(key, 0.0):
                    return key
            key = self._keys[self._idx % len(self._keys)]
            self._idx += 1
            return key

    def mark_exhausted(self, key: str, for_seconds: float = 86_400.0) -> None:
        with self._lock:
            self._exhausted[key] = time.time() + for_seconds
            logger.warning("AlphaVantage key …%s exhausted (daily limit) for %.0fh", key[-4:], for_seconds / 3600)


def _init_av_pool() -> _AVKeyPool:
    pool = _AVKeyPool()
    raw  = settings.alphavantage_api_keys or settings.alphavantage_api_key
    pool.load([k.strip() for k in raw.split(",") if k.strip()])
    logger.info("AlphaVantage key pool: %d key(s)", len(pool._keys))
    return pool


_av_pool = _init_av_pool()

# NSE → BSE mapping for the most-common tickers that sometimes 404 on yfinance
_NSE_TO_BSE: dict[str, str] = {
    "TATAMOTORS.NS":  "TATAMOTORS.BSE",
    "LTIMINDTREE.NS": "LTIMINDTREE.BSE",
    "CANBK.NS":       "CANBK.BSE",
    "KEIIND.NS":      "KEIIND.BSE",
    "BIRLASOFT.NS":   "BIRLASOFT.BSE",
    "ZENSAR.NS":      "ZENSAR.BSE",
    "OILINDIA.NS":    "OIL.BSE",
    "TATAPOWER.NS":   "TATAPOWER.BSE",
    "ADANIPORTS.NS":  "ADANIPORTS.BSE",
    "HDFCBANK.NS":    "HDFCBANK.BSE",
    "RELIANCE.NS":    "RELIANCE.BSE",
    "TCS.NS":         "TCS.BSE",
    "INFY.NS":        "INFY.BSE",
    "WIPRO.NS":       "WIPRO.BSE",
    "ICICIBANK.NS":   "ICICIBANK.BSE",
    "AXISBANK.NS":    "AXISBANK.BSE",
    "SBIN.NS":        "SBIN.BSE",
    "ITC.NS":         "ITC.BSE",
    "LT.NS":          "LT.BSE",
    "BAJFINANCE.NS":  "BAJFINANCE.BSE",
}


def _bse_symbol(ticker: str) -> str:
    """Convert NSE ticker to BSE format for Alpha Vantage."""
    if ticker in _NSE_TO_BSE:
        return _NSE_TO_BSE[ticker]
    if ticker.endswith(".NS"):
        return ticker[:-3] + ".BSE"
    return ticker  # already BSE or unknown


async def _av_get(params: dict) -> dict | None:
    """Single GET to Alpha Vantage; rotates key on daily-limit response."""
    key = _av_pool.next_key()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(_BASE, params={**params, "apikey": key})
            r.raise_for_status()
            data = r.json()
            if "Information" in data:
                # AV daily limit hit — mark key exhausted, retry once with next key
                _av_pool.mark_exhausted(key)
                retry_key = _av_pool.next_key()
                if retry_key and retry_key != key:
                    r2 = await client.get(_BASE, params={**params, "apikey": retry_key})
                    r2.raise_for_status()
                    data = r2.json()
                    if "Information" in data or "Error Message" in data:
                        logger.warning("AlphaVantage both keys exhausted for %s", params.get("function"))
                        return None
                else:
                    logger.warning("AlphaVantage daily limit hit, no spare key")
                    return None
            if "Error Message" in data:
                logger.warning("AlphaVantage error for %s: %s", params, data)
                return None
            return data
    except Exception as exc:
        logger.warning("AlphaVantage request failed: %s", exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def get_quote(ticker: str) -> dict | None:
    """
    Live BSE quote for a ticker. Returns a flat dict with:
      symbol, price, open, high, low, volume, change, change_pct, latest_day
    Cached 5 min.
    """
    bse = _bse_symbol(ticker)
    key = f"av:quote:{bse}"
    hit = cache.get(key)
    if hit:
        return hit

    data = await _av_get({"function": "GLOBAL_QUOTE", "symbol": bse})
    if not data or "Global Quote" not in data or not data["Global Quote"]:
        return None

    q = data["Global Quote"]
    result = {
        "symbol":     q.get("01. symbol", bse),
        "price":      float(q["05. price"]) if q.get("05. price") else None,
        "open":       float(q["02. open"])  if q.get("02. open")  else None,
        "high":       float(q["03. high"])  if q.get("03. high")  else None,
        "low":        float(q["04. low"])   if q.get("04. low")   else None,
        "volume":     int(q["06. volume"])  if q.get("06. volume") else None,
        "change":     float(q["09. change"])       if q.get("09. change")       else None,
        "change_pct": q.get("10. change percent", "").replace("%", ""),
        "latest_day": q.get("07. latest trading day"),
        "source":     "alphavantage",
    }
    cache.set(key, result, "prices")  # 5-min TTL
    return result


async def get_daily_series(ticker: str, outputsize: str = "compact") -> list[dict] | None:
    """
    Daily OHLCV for up to 100 trading days (compact) or full history (full).
    Returns list of {date, open, high, low, close, volume} sorted newest-first.
    Cached 6 h.
    """
    bse = _bse_symbol(ticker)
    key = f"av:daily:{bse}:{outputsize}"
    hit = cache.get(key)
    if hit:
        return hit

    data = await _av_get({
        "function":   "TIME_SERIES_DAILY",
        "symbol":     bse,
        "outputsize": outputsize,
    })
    if not data or "Time Series (Daily)" not in data:
        return None

    ts = data["Time Series (Daily)"]
    rows = []
    for date, vals in sorted(ts.items(), reverse=True):
        rows.append({
            "date":   date,
            "open":   float(vals.get("1. open",   0)),
            "high":   float(vals.get("2. high",   0)),
            "low":    float(vals.get("3. low",    0)),
            "close":  float(vals.get("4. close",  0)),
            "volume": int(vals.get("5. volume",   0)),
        })

    cache.set(key, rows, "ai")  # 6-h TTL (reuses "ai" category = 21600s)
    return rows


async def get_ai_context(ticker: str) -> str:
    """
    Returns a concise text block with Alpha Vantage BSE data for use in AI prompts.
    Single cached call — safe to call in ai_service without burning extra quota.
    """
    quote = await get_quote(ticker)
    if not quote:
        return ""

    bse = _bse_symbol(ticker)
    lines = [
        f"[Alpha Vantage BSE data for {bse}]",
        f"  Latest day : {quote.get('latest_day')}",
        f"  Price      : ₹{quote.get('price')}",
        f"  Open/High/Low: ₹{quote.get('open')} / ₹{quote.get('high')} / ₹{quote.get('low')}",
        f"  Volume     : {quote.get('volume'):,}" if quote.get("volume") else "",
        f"  Change     : {quote.get('change')} ({quote.get('change_pct')}%)",
    ]

    # Add recent trend from daily series (last 5 closes)
    series = await get_daily_series(ticker, "compact")
    if series and len(series) >= 5:
        recent = series[:5]
        trend = ", ".join(f"₹{r['close']}" for r in recent)
        lines.append(f"  Last 5 closes: {trend}")

    return "\n".join(l for l in lines if l)
