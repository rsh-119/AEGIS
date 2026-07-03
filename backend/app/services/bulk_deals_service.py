"""
bulk_deals_service.py — Real NSE/BSE bulk & block deals.

Primary:  NSE live API  (https://www.nseindia.com/api/bulk-deals)
          — requires a valid session cookie, fetched from the NSE homepage.
Fallback: NSE archive CSV
          (https://nsearchives.nseindia.com/content/equities/bulk.csv)
          — no auth, updated each trading day.

Returns list of:
  { symbol, company, entity, deal_type, quantity, price, value_cr, date, exchange }

Cached for 30 minutes — bulk deals are published once a day after market close.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, timedelta

import httpx

from app.core.cache import cache

logger = logging.getLogger(__name__)

_NSE_HOME    = "https://www.nseindia.com"
_NSE_API     = "https://www.nseindia.com/api/bulk-deals"
_NSE_CSV     = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
_BLOCK_CSV   = "https://nsearchives.nseindia.com/content/equities/block.csv"
_TIMEOUT     = 15.0

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}


def _clean_entity(name: str) -> str:
    """Trim all-caps noise, keep meaningful entity name."""
    name = name.strip()
    # NSE stores names in ALL CAPS; title-case them
    if name == name.upper():
        # Preserve known abbreviations
        abbrs = {"FPI", "FII", "NRI", "DII", "MF", "AIF", "LLP", "LTD", "PVT",
                 "PLC", "ETF", "ICICI", "HDFC", "SBI", "UTI", "DSP", "IIFL",
                 "IDFC", "HUL", "SEBI", "NSE", "BSE", "NSDL"}
        words = []
        for w in name.split():
            words.append(w if w in abbrs else w.title())
        name = " ".join(words)
    return name


def _parse_nse_api(data: dict) -> list[dict]:
    """Parse NSE API JSON response into Aegis bulk deal dicts."""
    rows: list[dict] = []
    for item in data.get("data", []) or []:
        symbol   = (item.get("SYMBOL") or item.get("symbol") or "").upper().strip()
        company  = _clean_entity(item.get("SECURITY") or item.get("name") or symbol)
        entity   = _clean_entity(item.get("CLIENT_NAME") or item.get("entity") or "—")
        raw_type = (item.get("DEAL_TYPE") or item.get("entityType") or "").upper().strip()
        deal_type = "BUY" if raw_type in ("BUY", "B") else "SELL" if raw_type in ("SELL", "S") else raw_type
        try:
            qty = int(str(item.get("QUANTITY") or item.get("buyQty") or item.get("sellQty") or 0).replace(",", ""))
        except (ValueError, TypeError):
            qty = 0
        try:
            price = float(str(item.get("PRICE") or item.get("price") or 0).replace(",", ""))
        except (ValueError, TypeError):
            price = 0.0
        raw_date = str(item.get("mTDATE") or item.get("date") or "").strip()
        if not symbol or price <= 0:
            continue
        rows.append({
            "symbol":    symbol,
            "ticker":    f"{symbol}.NS",
            "company":   company,
            "entity":    entity,
            "deal_type": deal_type,
            "quantity":  qty,
            "price":     round(price, 2),
            "value_cr":  round(qty * price / 1e7, 2),
            "date":      raw_date,
            "exchange":  "NSE",
        })
    return rows


def _parse_csv(text: str, exchange: str = "NSE") -> list[dict]:
    """Parse NSE archive CSV into Aegis bulk deal dicts.

    NSE bulk.csv headers (as of 2026):
      Date, Symbol, Security Name, Client Name, Buy/Sell,
      Quantity Traded, Trade Price / Wght. Avg. Price, Remarks
    """
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text.strip()))
    for item in reader:
        # Support both current and older NSE CSV header variants
        symbol  = (
            item.get("Symbol") or item.get("SYMBOL") or ""
        ).upper().strip()
        company = _clean_entity(
            item.get("Security Name") or item.get("Security / Issue Name")
            or item.get("Name") or item.get("SECURITY") or symbol
        )
        entity = _clean_entity(
            item.get("Client Name") or item.get("CLIENT_NAME") or "—"
        )
        raw_type = (
            item.get("Buy/Sell") or item.get("Buy / Sell")
            or item.get("DEAL_TYPE") or item.get("Type") or ""
        ).upper().strip()
        deal_type = (
            "BUY"  if "BUY"  in raw_type or raw_type == "B" else
            "SELL" if "SELL" in raw_type or raw_type == "S" else
            raw_type
        )
        try:
            qty = int(
                str(item.get("Quantity Traded") or item.get("QUANTITY") or 0)
                .replace(",", "")
            )
        except (ValueError, TypeError):
            qty = 0
        try:
            price_raw = str(
                item.get("Trade Price / Wght. Avg. Price")
                or item.get("Trade Price / Wt. Avg. Price")
                or item.get("PRICE") or 0
            )
            price = float(price_raw.replace(",", ""))
        except (ValueError, TypeError):
            price = 0.0
        raw_date = str(item.get("Date") or item.get("mTDATE") or "").strip()

        if not symbol or price <= 0:
            continue
        rows.append({
            "symbol":    symbol,
            "ticker":    f"{symbol}.NS",
            "company":   company,
            "entity":    entity,
            "deal_type": deal_type,
            "quantity":  qty,
            "price":     round(price, 2),
            "value_cr":  round(qty * price / 1e7, 2),
            "date":      raw_date,
            "exchange":  exchange,
        })
    return rows


async def _fetch_via_session() -> list[dict]:
    """Two-step NSE session fetch: homepage → API."""
    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers=_BROWSER_HEADERS,
    ) as client:
        # Step 1: warm up session / get cookies
        try:
            await client.get(_NSE_HOME)
        except Exception:
            pass  # cookies may already be set

        # Step 2: bulk deals API
        r = await client.get(_NSE_API, params={"type": "bulk_deals"})
        r.raise_for_status()
        data = r.json()
        rows = _parse_nse_api(data)
        logger.info("NSE bulk deals via API: %d deals", len(rows))
        return rows


async def _fetch_via_csv() -> list[dict]:
    """Fallback: NSE archive CSV (no auth, daily file)."""
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_BROWSER_HEADERS) as client:
        for url, exch in [(_NSE_CSV, "NSE"), (_BLOCK_CSV, "NSE")]:
            try:
                r = await client.get(url)
                r.raise_for_status()
                parsed = _parse_csv(r.text, exch)
                rows.extend(parsed)
                logger.info("NSE bulk deals via CSV %s: %d deals", url, len(parsed))
            except Exception as exc:
                logger.debug("CSV fetch failed %s: %s", url, exc)
    return rows


async def get_bulk_deals(limit: int = 20) -> list[dict]:
    """
    Return recent bulk deals sorted by deal value (largest first).
    Cached 30 minutes.
    """
    ck = "market:bulk_deals"
    hit = cache.get(ck)
    if hit is not None:
        return hit[:limit]

    rows: list[dict] = []

    # Try NSE session API first
    try:
        rows = await _fetch_via_session()
    except Exception as exc:
        logger.warning("NSE bulk deals session API failed: %s", exc)

    # Fall back to archive CSV
    if not rows:
        try:
            rows = await _fetch_via_csv()
        except Exception as exc:
            logger.warning("NSE bulk deals CSV fallback failed: %s", exc)

    if not rows:
        logger.warning("NSE bulk deals: all sources failed, returning empty")
        return []

    # Deduplicate (same symbol + entity + deal_type) and sort by value
    seen: set[str] = set()
    unique: list[dict] = []
    for r in rows:
        key = f"{r['symbol']}:{r['entity']}:{r['deal_type']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)

    unique.sort(key=lambda x: x["value_cr"], reverse=True)

    cache.set(ck, unique, "nifty50")   # 1h TTL — NSE bulk deals are published once daily
    return unique[:limit]
