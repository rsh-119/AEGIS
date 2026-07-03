"""
IndianAPI.in — primary market data source for fast homepage loading.
Replaces yfinance 130-ticker batch (~30-60 s) with 2 quick API calls (~1-2 s).
Base URL: https://stock.indianapi.in
Auth: X-Api-Key header
"""
from __future__ import annotations

import logging
import re
import time

import httpx

from app.core.cache import cache
from app.core.config import get_settings

logger = logging.getLogger(__name__)
BASE_URL = "https://stock.indianapi.in"

# ── 429 circuit breaker ───────────────────────────────────────────────────────
# When IndianAPI returns 429, block ALL calls for this many seconds to let the
# rate-limit window reset before we try again.
_BACKOFF_SECONDS = 300   # 5 minutes
_blocked_until: float = 0.0


def _headers() -> dict[str, str]:
    return {"X-Api-Key": get_settings().indianapi_key}


async def _get(path: str, params: dict | None = None) -> dict | list | None:
    global _blocked_until
    if not get_settings().indianapi_enabled:
        return None   # monthly quota exhausted — all calls short-circuit
    if time.time() < _blocked_until:
        remaining = int(_blocked_until - time.time())
        logger.debug("IndianAPI circuit open — skipping %s (%ds remaining)", path, remaining)
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(f"{BASE_URL}{path}", headers=_headers(), params=params or {})
            if r.status_code == 429:
                _blocked_until = time.time() + _BACKOFF_SECONDS
                logger.warning(
                    "IndianAPI 429 on %s — circuit open for %ds", path, _BACKOFF_SECONDS
                )
                return None
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("IndianAPI %s error: %s", path, e)
        return None


# ── Value parsers ─────────────────────────────────────────────────────────────

def _parse_mcap(raw) -> float | None:
    """Parse market cap: handles float, int, or strings like '17.15L Cr', '5.43 T', '234 Cr'."""
    if isinstance(raw, (int, float)):
        return float(raw) if raw else None
    if not raw:
        return None
    s = str(raw).replace(",", "").strip()
    m = re.match(r"([\d.]+)\s*([A-Za-z\s]*)", s)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).strip().upper().replace(" ", "")
    if unit in ("LCR", "LAKHCR", "LAKHCRORE", "T"):
        return val * 1e12
    if unit in ("CR", "CRORE"):
        return val * 1e7
    if unit in ("L", "LAKH"):
        return val * 1e5
    if unit == "B":
        return val * 1e9
    return val


def _f(v) -> float | None:
    try:
        return float(v) if v is not None and v != "" else None
    except (ValueError, TypeError):
        return None


def _i(v) -> int | None:
    try:
        return int(v) if v is not None and v != "" else None
    except (ValueError, TypeError):
        return None


# ── Normalizer ────────────────────────────────────────────────────────────────

def _normalize(raw: dict) -> dict | None:
    """Map any IndianAPI stock dict → our internal Stock format."""
    ticker = (
        raw.get("stock_name") or raw.get("ticker") or
        raw.get("symbol") or raw.get("nse_code") or
        raw.get("ric") or raw.get("series") or ""
    ).strip().upper()
    if not ticker:
        return None

    name = (raw.get("company_name") or raw.get("name") or ticker).strip()

    price = _f(
        raw.get("current_price") or raw.get("price") or
        raw.get("ltp") or raw.get("last_price") or raw.get("close")
    )
    change_pct = _f(
        raw.get("percent_change") or raw.get("percentage_change") or
        raw.get("change_percentage") or raw.get("net_change_percentage") or
        raw.get("pChange")
    )
    mcap = _parse_mcap(raw.get("market_cap") or raw.get("mcap"))
    volume = _i(
        raw.get("volume") or raw.get("total_volume") or
        raw.get("traded_volume") or raw.get("totalTradedVolume")
    )
    pe = _f(raw.get("pe_ratio") or raw.get("pe") or raw.get("p_e"))

    return {
        "ticker":      ticker,
        "name":        name,
        "price":       price,
        "change_pct":  change_pct,
        "market_cap":  mcap,
        "pe_ratio":    pe,
        "volume":      volume,
        "avg_volume":  None,
        "cap_type":    "large",
        "website":     None,
    }


# ── Public API functions ──────────────────────────────────────────────────────

async def get_trending() -> dict[str, list[dict]]:
    """
    /trending — returns top gainers and losers.
    Handles both {"gainers": [...], "losers": [...]} and
    {"top_gainers": [...], "top_losers": [...]} response shapes.
    """
    data = await _get("/trending")
    if not data or not isinstance(data, dict):
        return {"gainers": [], "losers": []}

    # API wraps data under "trending_stocks" key as of mid-2026
    nested = data.get("trending_stocks") or {}
    raw_gainers = (
        data.get("gainers") or nested.get("top_gainers") or
        data.get("top_gainers") or data.get("Gainers") or []
    )
    raw_losers = (
        data.get("losers") or nested.get("top_losers") or
        data.get("top_losers") or data.get("Losers") or []
    )

    gainers = [s for s in (_normalize(r) for r in raw_gainers) if s]
    losers  = [s for s in (_normalize(r) for r in raw_losers)  if s]
    return {"gainers": gainers, "losers": losers}


async def get_nse_most_active() -> list[dict]:
    """/NSE_most_active — most actively traded NSE stocks."""
    data = await _get("/NSE_most_active")
    if not data:
        return []
    items = data if isinstance(data, list) else (
        data.get("data") or data.get("stocks") or data.get("results") or []
    )
    return [s for s in (_normalize(r) for r in items) if s]


async def get_bse_most_active() -> list[dict]:
    """/BSE_most_active — most actively traded BSE stocks."""
    data = await _get("/BSE_most_active")
    if not data:
        return []
    items = data if isinstance(data, list) else (
        data.get("data") or data.get("stocks") or data.get("results") or []
    )
    return [s for s in (_normalize(r) for r in items) if s]


async def get_52_week_high_low() -> dict[str, list[dict]]:
    """/fetch_52_week_high_low_data — 52-week highs and lows."""
    data = await _get("/fetch_52_week_high_low_data")
    if not data or not isinstance(data, dict):
        return {"highs": [], "lows": []}
    raw_highs = (
        data.get("52_week_high") or data.get("highs") or
        data.get("high") or data.get("nearHigh") or []
    )
    raw_lows = (
        data.get("52_week_low") or data.get("lows") or
        data.get("low") or data.get("nearLow") or []
    )
    return {
        "highs": [s for s in (_normalize(r) for r in raw_highs) if s],
        "lows":  [s for s in (_normalize(r) for r in raw_lows)  if s],
    }


async def get_price_shockers() -> list[dict]:
    """/price_shockers — stocks with unusual price movement."""
    data = await _get("/price_shockers")
    if not data:
        return []
    items = data if isinstance(data, list) else (
        data.get("data") or data.get("stocks") or []
    )
    return [s for s in (_normalize(r) for r in items) if s]


async def search_stock(query: str) -> list[dict]:
    """/search — search stocks by name or ticker."""
    data = await _get("/search", {"q": query})
    if not data:
        return []
    items = data if isinstance(data, list) else (
        data.get("results") or data.get("data") or []
    )
    return items


async def get_stock(ticker: str) -> dict | None:
    """/stock — full stock details by NSE ticker."""
    data = await _get("/stock", {"name": ticker})
    return data if isinstance(data, dict) else None


async def get_news(stock: str | None = None) -> list[dict]:
    """/news — latest market or stock-specific news."""
    params = {"stock": stock} if stock else {}
    data = await _get("/news", params)
    if not data:
        return []
    return data if isinstance(data, list) else (data.get("data") or [])


async def get_ipo() -> list[dict]:
    """/ipo — upcoming and recent IPOs."""
    data = await _get("/ipo")
    if not data:
        return []
    return data if isinstance(data, list) else (data.get("data") or [])


async def get_commodities() -> list[dict]:
    """/commodities — commodity prices (gold, silver, crude, etc.)."""
    data = await _get("/commodities")
    if not data:
        return []
    return data if isinstance(data, list) else (data.get("data") or [])


async def get_historical_data(ticker: str, period: str = "1y") -> dict | None:
    """/historical_data — OHLCV history for a stock. Cached 1 h."""
    ck = f"indianapi:history:{ticker}:{period}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = await _get("/historical_data", {"stock_name": ticker, "period": period})
    result = data if isinstance(data, dict) else None
    if result:
        cache.set(ck, result, "history")
    return result


async def get_stock_forecasts(ticker: str) -> dict | None:
    """/stock_forecasts — analyst forecasts. Cached 24 h."""
    ck = f"indianapi:forecasts:{ticker}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = await _get("/stock_forecasts", {"stock_name": ticker})
    result = data if isinstance(data, dict) else None
    if result:
        cache.set(ck, result, "analyst")
    return result


async def get_stock_target_price(ticker: str) -> dict | None:
    """/stock_target_price — analyst target prices. Cached 24 h."""
    ck = f"indianapi:targets:{ticker}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = await _get("/stock_target_price", {"stock_name": ticker})
    result = data if isinstance(data, dict) else None
    if result:
        cache.set(ck, result, "analyst")
    return result


async def get_recent_announcements(ticker: str | None = None) -> list[dict]:
    """/recent_announcements — corporate announcements. Cached 4 h."""
    ck = f"indianapi:announcements:{ticker or 'all'}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    params = {"stock_name": ticker} if ticker else {}
    data = await _get("/recent_announcements", params)
    result: list[dict] = data if isinstance(data, list) else (data.get("data") or [] if data else [])
    if result:
        cache.set(ck, result, "filing")
    return result


async def get_corporate_actions(ticker: str | None = None) -> list[dict]:
    """/corporate_actions — dividends, splits, bonuses. Cached 24 h."""
    ck = f"indianapi:corpactions:{ticker or 'all'}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    params = {"stock_name": ticker} if ticker else {}
    data = await _get("/corporate_actions", params)
    result: list[dict] = data if isinstance(data, list) else (data.get("data") or [] if data else [])
    if result:
        cache.set(ck, result, "corporate")
    return result
