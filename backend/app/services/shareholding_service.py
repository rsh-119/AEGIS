"""
Shareholding pattern history via BSE India.

BSE India (bseindia.com) is the official stock exchange regulated by SEBI.
Companies are legally mandated by SEBI LODR to disclose quarterly shareholding
patterns, and BSE is required to make this public. This data is regulatory
public disclosure — not proprietary commercial data.
"""

import requests
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)
_pool  = ThreadPoolExecutor(max_workers=4)

# BSE India requires a Referer header — no auth, no API key needed.
_BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/",
    "Accept":  "application/json, text/plain, */*",
}

# 24-hour in-memory cache — shareholding changes quarterly
class _Cache:
    def __init__(self):
        self._store: dict = {}

    def get(self, key: str):
        import time
        entry = self._store.get(key)
        if entry and time.time() - entry["ts"] < 86400:
            return entry["v"]
        return None

    def set(self, key: str, val):
        import time
        self._store[key] = {"v": val, "ts": time.time()}

_cache = _Cache()


def _get_bse_code_sync(nse_symbol: str) -> Optional[str]:
    """
    Find BSE scrip code for an NSE ticker symbol via BSE's public search API.
    Source: https://api.bseindia.com (BSE India — official exchange)
    """
    try:
        url = (
            "https://api.bseindia.com/BseIndiaAPI/api/getCompanyData/w"
            f"?scripcode=&strSearch={nse_symbol}&flag=0"
        )
        r = requests.get(url, headers=_BSE_HEADERS, timeout=10)
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            return None
        # Prefer exact NSE code match
        for row in rows:
            if str(row.get("NSECODE", "")).upper() == nse_symbol.upper():
                code = str(row.get("SCRIP_CODE") or row.get("SCRIPCODE") or "")
                if code:
                    return code
        # Fall back to first result
        first = rows[0]
        code = str(first.get("SCRIP_CODE") or first.get("SCRIPCODE") or "")
        return code or None
    except Exception as e:
        logger.debug("BSE code lookup failed for %s: %s", nse_symbol, e)
        return None


def _parse_quarter_label(raw: str) -> str:
    """Convert BSE quarter strings like '31-Mar-2024' → 'Mar 2024'."""
    try:
        from datetime import datetime
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                return dt.strftime("%b %Y")
            except ValueError:
                pass
    except Exception:
        pass
    return raw.strip()


def _fetch_shareholding_sync(scrip_code: str) -> list:
    """
    Fetch quarterly shareholding pattern history from BSE India.
    Source: https://www.bseindia.com/corporates/Shhold.aspx
    Data: SEBI-mandated quarterly regulatory disclosure (LODR Reg 31).
    """
    try:
        url = (
            "https://api.bseindia.com/BseIndiaAPI/api/ShareHoldingPatterns/w"
            f"?scripcode={scrip_code}"
        )
        r = requests.get(url, headers=_BSE_HEADERS, timeout=15)
        r.raise_for_status()
        raw = r.json()

        # BSE returns a list of category-level rows, one per quarter per category.
        # Categories include Promoters, FPI, Mutual Funds, Other Institutions, Public, etc.
        # We aggregate them into 4 buckets per quarter.
        if not isinstance(raw, list):
            raw = raw.get("Table") or raw.get("data") or []

        quarters: dict[str, dict] = {}

        for row in raw:
            # Quarter identifier — could be "31-Mar-2024" or "Q12024" etc.
            qdate = (
                row.get("QUARTER_END")
                or row.get("QuarterEnd")
                or row.get("quarter_end")
                or row.get("Qtrid")
                or ""
            )
            if not qdate:
                continue

            pct_raw = (
                row.get("Percent_Share")
                or row.get("percent_share")
                or row.get("PERCENT_SHARE")
                or row.get("PER_SHARE")
                or 0
            )
            try:
                pct = float(pct_raw)
            except (ValueError, TypeError):
                pct = 0.0

            category = str(
                row.get("Category")
                or row.get("CATEGORY")
                or row.get("category")
                or ""
            ).lower()

            if qdate not in quarters:
                quarters[qdate] = {
                    "raw_date": qdate,
                    "quarter":  _parse_quarter_label(qdate),
                    "promoter": 0.0,
                    "fii":      0.0,
                    "dii":      0.0,
                    "public":   0.0,
                }

            q = quarters[qdate]

            if "promoter" in category:
                q["promoter"] = max(q["promoter"], pct)
            elif any(k in category for k in ("fpi", "fii", "foreign")):
                q["fii"] += pct
            elif any(k in category for k in ("mutual", "insurance", "bank", "institution", "dii", "nbfc")):
                q["dii"] += pct
            elif "public" in category or "retail" in category or "individual" in category:
                q["public"] += pct

        if not quarters:
            return []

        # Sort chronologically (newest first)
        def _sort_key(item):
            from datetime import datetime
            raw = item["raw_date"]
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(raw.strip(), fmt).timestamp()
                except ValueError:
                    pass
            return 0

        result = sorted(quarters.values(), key=_sort_key, reverse=True)
        # Return last 12 quarters (3 years)
        return result[:12]

    except Exception as e:
        logger.debug("BSE shareholding fetch failed for %s: %s", scrip_code, e)
        return []


async def get_shareholding_history(ticker: str) -> dict:
    """
    Returns quarterly shareholding pattern history for a stock.
    Fetches from BSE India (SEBI-mandated public disclosure).
    """
    cache_key = f"sh:{ticker}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    nse_symbol = ticker.replace(".NS", "").replace(".BO", "")
    loop = asyncio.get_event_loop()

    scrip_code = await loop.run_in_executor(_pool, _get_bse_code_sync, nse_symbol)
    if not scrip_code:
        result = {"quarters": [], "error": "BSE code not found", "source": "BSE India"}
        _cache.set(cache_key, result)
        return result

    quarters = await loop.run_in_executor(_pool, _fetch_shareholding_sync, scrip_code)

    result = {
        "quarters": quarters,
        "scrip_code": scrip_code,
        "source": "BSE India",
        "source_url": f"https://www.bseindia.com/stock-share-price/{nse_symbol}/shareHoldingPatterns/{scrip_code}/",
    }
    _cache.set(cache_key, result)
    return result
