"""
market_service.py — market overview: indices, gainers, losers, cap segments.

Data priority per data type:
  gainers / losers / high_volume : NSE direct API (no key needed)
  nifty50 / nifty100 / buckets   : IndianAPI (sector/ETF pages only)
  indices bar                    : NSE direct API
  IPO / commodities / 52wk / announcements : IndianAPI dedicated endpoints
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as _dtime
from zoneinfo import ZoneInfo

import requests as _requests

from app.core.cache import cache
from app.services import indianapi_service
from app.services.stock_service import _clean, _TTL

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=32)
_cache = _TTL(ttl=1800)   # 30-min TTL — matches trading-hours refetch cadence
_idx_cache = _TTL(ttl=60)  # 60-second cache for indices-only endpoint

# ── NSE trading-hours gate ────────────────────────────────────────────────────
# Outside these hours, prices can't have changed, so indices/movers are served
# straight from the long-lived snapshot cache with no live fetch attempted at
# all — see get_indices()/get_market_overview() and home_refresh_service.py's
# end-of-day snapshot job.
_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN = _dtime(9, 15)
_MARKET_CLOSE = _dtime(15, 30)

# Fixed-date national holidays (never move year to year) — safe to hardcode.
# Variable-date festivals (Diwali, Holi, Eid, etc.) are NOT included since
# guessing wrong dates isn't worth the risk; add exact dates here if you have
# NSE's official trading-holiday list for the year.
_FIXED_HOLIDAYS_MMDD = {(1, 26), (8, 15), (10, 2)}  # Republic Day, Independence Day, Gandhi Jayanti

_SNAPSHOT_INDICES_KEY = "market:snapshot:indices"
_SNAPSHOT_OVERVIEW_KEY = "market:snapshot:overview"


def is_market_hours(now: datetime | None = None) -> bool:
    now = now.astimezone(_IST) if now else datetime.now(_IST)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    if (now.month, now.day) in _FIXED_HOLIDAYS_MMDD:
        return False
    return _MARKET_OPEN <= now.time() <= _MARKET_CLOSE

# ── NSE direct session for index data (no yfinance) ──────────────────────────
_nse_session = _requests.Session()
_nse_session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
})
_nse_cookie_lock = threading.Lock()
_nse_cookies_loaded = False

def _ensure_nse_cookies() -> None:
    global _nse_cookies_loaded
    if _nse_cookies_loaded:
        return
    with _nse_cookie_lock:
        if not _nse_cookies_loaded:
            _nse_session.get("https://www.nseindia.com/", timeout=10)
            _nse_cookies_loaded = True

# NSE index name → display name mapping
_NSE_INDEX_MAP = {
    "NIFTY 50":      "Nifty 50",
    "NIFTY NEXT 50": "Nifty Next 50",
    "NIFTY BANK":    "Bank Nifty",
    "NIFTY IT":      "Nifty IT",
    "NIFTY PHARMA":  "Nifty Pharma",
}

# IndianAPI's /indices name (uppercased for matching) → same display names as above.
# Used as a fallback when NSE direct is blocked (403 from cloud IPs, e.g. Render).
_INDIANAPI_INDEX_MAP = {
    "NIFTY 50":      "Nifty 50",
    "NIFTY NEXT 50": "Nifty Next 50",
    "NIFTY BANK":    "Bank Nifty",
    "NIFTY IT":      "Nifty IT",
    "NIFTY PHARMA":  "Nifty Pharma",
}

# Keep _INDICES for any legacy callers (no longer used for actual fetching)
_INDICES = {
    "Nifty 50":      "^NSEI",
    "Nifty Next 50": "^NSEMDCP50",
    "Bank Nifty":    "^NSEBANK",
    "Nifty IT":      "^CNXIT",
    "Nifty Pharma":  "^CNXPHARMA",
}

# ── NSE index fetch (no yfinance, no rate-limit risk) ────────────────────────

def _fetch_indices_from_nse_sync() -> list[dict]:
    """Fetch the 5 headline indices directly from NSE's official API."""
    try:
        _ensure_nse_cookies()
        r = _nse_session.get(
            "https://www.nseindia.com/api/allIndices",
            timeout=10,
        )
        r.raise_for_status()
        all_indices: list[dict] = r.json().get("data", [])
    except Exception as exc:
        logger.warning("NSE indices fetch failed: %s", exc)
        return []

    out: list[dict] = []
    for row in all_indices:
        name = row.get("index", "")
        display = _NSE_INDEX_MAP.get(name)
        if not display:
            continue
        try:
            price = float(row["last"])
            prev  = float(row["previousClose"])
            chg   = float(row["percentChange"])
            out.append({
                "name":       display,
                "price":      round(price, 2),
                "prev_close": round(prev, 2),
                "change_pct": round(chg, 2),
                "change_pts": round(price - prev, 2),
                "open":       float(row.get("open") or prev),
                "high":       float(row.get("high") or price),
                "low":        float(row.get("low") or price),
                "year_high":  float(row.get("yearHigh") or 0) or None,
                "year_low":   float(row.get("yearLow") or 0) or None,
            })
        except (KeyError, TypeError, ValueError):
            continue

    # Preserve consistent display order
    _order = list(_NSE_INDEX_MAP.values())
    out.sort(key=lambda x: _order.index(x["name"]) if x["name"] in _order else 99)
    return out


# ── NSE gainers / losers (primary — no yfinance, no API key needed) ──────────

def _nse_stock(sym: str, ltp, prev_price, per_change, volume=None) -> dict:
    ticker = f"{sym}.NS"
    price  = float(ltp or 0) or None
    pct    = float(per_change or 0)
    if not price:
        return {}
    return {
        "ticker":     ticker,
        "name":       sym,
        "price":      round(price, 2),
        "change_pct": round(pct, 2),
        "market_cap": None,
        "pe_ratio":   None,
        "volume":     int(volume) if volume else None,
        "avg_volume": None,
        "cap_type":   "large",
        "website":    None,
    }


def _fetch_nse_gainers_losers_sync() -> dict[str, list[dict]]:
    """
    Fetch top gainers and losers for Nifty 50 directly from NSE.
    Uses two sources:
      - live-analysis-variations: top 20 gainers from NIFTY + NIFTYNEXT50
      - market-data-pre-open:     all 50 Nifty stocks (derive losers from here)
    No API key, no yfinance.
    """
    result: dict[str, list[dict]] = {"gainers": [], "losers": []}
    try:
        _ensure_nse_cookies()

        # Source 1: live-analysis-variations (gainers only — losers endpoint doesn't exist)
        r = _nse_session.get(
            "https://www.nseindia.com/api/live-analysis-variations",
            params={"index": "gainers", "name": "nifty50", "data": "secFno"},
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        gainers_raw: list[dict] = []
        for key in ("NIFTY", "NIFTYNEXT50"):
            for row in (data.get(key) or {}).get("data") or []:
                s = _nse_stock(
                    row.get("symbol", ""),
                    row.get("ltp"),
                    row.get("prev_price"),
                    row.get("perChange"),
                    row.get("trade_quantity"),
                )
                if s:
                    gainers_raw.append(s)
        seen: set[str] = set()
        unique_gainers: list[dict] = []
        for s in sorted(gainers_raw, key=lambda x: -(x["change_pct"] or 0)):
            if s["ticker"] not in seen:
                seen.add(s["ticker"])
                unique_gainers.append(s)
        result["gainers"] = unique_gainers[:30]

        # Source 2: FO pre-open (211 stocks) gives a wide enough pool for 30 losers
        # even on strongly bullish days. Fall back to NIFTY-only if FO fails.
        fo_stocks: list[dict] = []
        for key in ("FO", "NIFTY"):
            r2 = _nse_session.get(
                "https://www.nseindia.com/api/market-data-pre-open",
                params={"key": key},
                timeout=12,
            )
            r2.raise_for_status()
            for item in r2.json().get("data") or []:
                m = item.get("metadata") or {}
                sym = m.get("symbol", "").strip()
                s = _nse_stock(sym, m.get("lastPrice"), m.get("previousClose"), m.get("pChange"))
                if s and s["ticker"] not in {x["ticker"] for x in fo_stocks}:
                    fo_stocks.append(s)
            if len([s for s in fo_stocks if s["change_pct"] < 0]) >= 30:
                break  # enough losers found

        result["losers"] = sorted(
            [s for s in fo_stocks if s["change_pct"] < 0],
            key=lambda x: (x["change_pct"] or 0),
        )[:30]

    except Exception as exc:
        logger.warning("NSE gainers/losers fetch failed: %s", exc)
    logger.info("NSE movers: gainers=%d losers=%d", len(result["gainers"]), len(result["losers"]))
    return result


async def _fetch_movers_from_indianapi() -> dict[str, list[dict]]:
    """Fallback when NSE direct is blocked (403 from cloud IPs, e.g. Render).

    IMPORTANT: this restricts to the same large-cap (_LARGE_CAP_TICKERS)
    universe as the NSE-direct primary path, via IndianAPI's batch live-price
    endpoint. Using IndianAPI's /trending instead (a whole-market scan) was
    tried first but surfaces thinly-traded small/micro-caps with extreme %
    swings (e.g. a stock up 20% on a handful of trades) — a materially worse
    "Market Movers" experience than the curated large-cap list users expect.
    """
    bare = [t.replace(".NS", "") for t in _LARGE_CAP_TICKERS]
    prices = await indianapi_service.batch_live_price(bare, exchange="NSE")

    stocks: list[dict] = []
    for sym, row in prices.items():
        s = _nse_stock(sym, row.get("ltp"), None, row.get("day_change_percent"), row.get("volume"))
        if s:
            stocks.append(s)

    gainers = sorted([s for s in stocks if s["change_pct"] > 0], key=lambda x: -x["change_pct"])[:30]
    losers = sorted([s for s in stocks if s["change_pct"] < 0], key=lambda x: x["change_pct"])[:30]
    return {"gainers": gainers, "losers": losers}


# ── Watchlist for movers — split by cap tier so classification is predefined ──
_LARGE_CAP_TICKERS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","HINDUNILVR.NS",
    "ITC.NS","SBIN.NS","BHARTIARTL.NS","BAJFINANCE.NS","KOTAKBANK.NS","LT.NS",
    "AXISBANK.NS","ASIANPAINT.NS","MARUTI.NS","SUNPHARMA.NS","TITAN.NS","NESTLEIND.NS",
    "WIPRO.NS","ULTRACEMCO.NS","POWERGRID.NS","NTPC.NS","ADANIENT.NS","ADANIPORTS.NS",
    "ONGC.NS","TECHM.NS","HCLTECH.NS","BAJAJFINSV.NS","TATAMOTORS.NS","TATASTEEL.NS",
    "JSWSTEEL.NS","COALINDIA.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","EICHERMOT.NS",
    "BPCL.NS","HEROMOTOCO.NS","BRITANNIA.NS","GRASIM.NS","APOLLOHOSP.NS","ETERNAL.NS",
    "TATACONSUM.NS","INDUSINDBK.NS","M&M.NS","BAJAJ-AUTO.NS","HINDALCO.NS","HAL.NS",
    "BEL.NS","IRCTC.NS","LTIMINDTREE.NS","PERSISTENT.NS","TATAPOWER.NS","DLF.NS","DMART.NS",
    "NAUKRI.NS","CHOLAFIN.NS","MUTHOOTFIN.NS","BANKBARODA.NS","PNB.NS","CANBK.NS",
    "SHRIRAMFIN.NS","LODHA.NS","GODREJPROP.NS","MAXHEALTH.NS","MANKIND.NS","OFSS.NS",
    "LTTS.NS","COFORGE.NS","MPHASIS.NS","POLYCAB.NS","ASTRAL.NS","DALBHARAT.NS",
]

_MID_CAP_TICKERS = [
    "TVSMOTOR.NS","BALKRISIND.NS","ESCORTS.NS","CEATLTD.NS","ABFRL.NS",
    "CROMPTON.NS","BLUESTARCO.NS","VOLTAS.NS","WHIRLPOOL.NS","HAVELLS.NS",
    "KEIIND.NS","SUPREMEIND.NS","JKCEMENT.NS","RAMCOCEM.NS","AIAENG.NS",
    "ELGIEQUIP.NS","GRINDWELL.NS","TIMKEN.NS","SCHAEFFLER.NS","SKFINDIA.NS",
    "ABBOTINDIA.NS","IPCALAB.NS","AJANTPHARM.NS","ALKEM.NS","NATCOPHARM.NS",
    "METROPOLIS.NS","THYROCARE.NS","LALPATHLAB.NS","KRSNAA.NS","FORTIS.NS",
    "BRIGADE.NS","SOBHA.NS","OBEROIRLTY.NS","PHOENIXLTD.NS","KOLTEPATIL.NS",
    "SUNTV.NS","INDIAMART.NS","JUSTDIAL.NS","RBLBANK.NS","FEDERALBNK.NS",
    "BANDHANBNK.NS","IDFCFIRSTB.NS","AUBANK.NS","UJJIVANSFB.NS","EQUITASBNK.NS",
    "SJVN.NS","NHPC.NS","CESC.NS","TORNTPOWER.NS","IREDA.NS","JSWENERGY.NS",
    "PIIND.NS","SYNGENE.NS","BIOCON.NS","AUROPHARMA.NS","LUPIN.NS",
    "MCDOWELL-N.NS","RADICO.NS","VBL.NS","EMAMILTD.NS","JYOTHYLAB.NS",
    "TRENT.NS","BATAINDIA.NS","METROBRAND.NS","SHOPERSTOP.NS","NYKAA.NS",
    "DELHIVERY.NS","NAZARA.NS","RATEGAIN.NS","HAPPSTMNDS.NS","TANLA.NS",
]

_SMALL_CAP_TICKERS = [
    "YESBANK.NS","IDEA.NS","RPOWER.NS","SAIL.NS","NMDC.NS","NATIONALUM.NS",
    "ZENSAR.NS","MASTEK.NS","CYIENT.NS","BIRLASOFT.NS","INTELLECT.NS","NEWGEN.NS",
    "PGHH.NS","ZYDUSWELL.NS","GOCOLORS.NS","VAIBHAVGBL.NS",
    "INOXWIND.NS","PVRINOX.NS","NCLIND.NS","IBREALEST.NS","ARVSMART.NS",
    "SASKEN.NS","NIITLTD.NS","HATHWAY.NS","TTML.NS",
    "OILINDIA.NS","MRPL.NS","CASTROLIND.NS","GSPL.NS","MGL.NS","IGL.NS",
]

# Market-cap thresholds in INR (used to classify unknown tickers by market cap)
_LARGE_CAP = 200_000_000_000   # ≥ ₹20,000 Cr
_MID_CAP   =  10_000_000_000   # ≥ ₹1,000 Cr

_MOVERS_POOL = _LARGE_CAP_TICKERS + _MID_CAP_TICKERS + _SMALL_CAP_TICKERS

# Predefined cap tier (used only internally for /cap endpoint)
_CAP_TYPE_MAP: dict[str, str] = {
    **{t: "large" for t in _LARGE_CAP_TICKERS},
    **{t: "mid"   for t in _MID_CAP_TICKERS},
    **{t: "small" for t in _SMALL_CAP_TICKERS},
}

# ── Nifty index membership sets ───────────────────────────────────────────────
_NIFTY50: set[str] = {
    "ADANIENT.NS","ADANIPORTS.NS","APOLLOHOSP.NS","ASIANPAINT.NS","AXISBANK.NS",
    "BAJAJ-AUTO.NS","BAJFINANCE.NS","BAJAJFINSV.NS","BEL.NS","BHARTIARTL.NS",
    "BPCL.NS","BRITANNIA.NS","CIPLA.NS","COALINDIA.NS","DIVISLAB.NS","DRREDDY.NS",
    "EICHERMOT.NS","ETERNAL.NS","GRASIM.NS","HCLTECH.NS","HDFCBANK.NS","HEROMOTOCO.NS",
    "HINDALCO.NS","HINDUNILVR.NS","ICICIBANK.NS","INDUSINDBK.NS","INFY.NS","ITC.NS",
    "JSWSTEEL.NS","KOTAKBANK.NS","LT.NS","M&M.NS","MARUTI.NS","NESTLEIND.NS",
    "NTPC.NS","ONGC.NS","POWERGRID.NS","RELIANCE.NS","SBIN.NS","SHRIRAMFIN.NS",
    "SUNPHARMA.NS","TATACONSUM.NS","TATAMOTORS.NS","TATASTEEL.NS","TCS.NS",
    "TECHM.NS","TITAN.NS","TRENT.NS","ULTRACEMCO.NS","WIPRO.NS",
}

# Nifty Next 50 = large caps not in Nifty 50 (Nifty 100 = N50 ∪ Next50)
_NIFTY_NEXT50: set[str] = set(_LARGE_CAP_TICKERS) - _NIFTY50

# Nifty Midcap 100 ≈ our mid-cap pool; Nifty Smallcap 100 ≈ our small-cap pool
_NIFTY_MIDCAP100: set[str]   = set(_MID_CAP_TICKERS)
_NIFTY_SMALLCAP100: set[str] = set(_SMALL_CAP_TICKERS)


async def _fetch_sector_quote(ticker: str) -> dict | None:
    """Extended quote for sector/peer pages — IndianAPI /get_stock_data gives
    ratios + margins + YoY growth (via financials cagr) in a single call."""
    bare = ticker.replace(".NS", "").replace(".BO", "")
    raw = await indianapi_service.get_stock_data(bare)
    if not raw:
        return None
    parsed = indianapi_service.parse_stock_data(raw)
    price_raw = await indianapi_service.get_stock(bare)
    price = None
    change_pct = None
    if price_raw:
        p = indianapi_service.parse_stock(price_raw)
        price = p.get("current_price")
        prev = p.get("previous_close")
        if price and prev:
            change_pct = round((price - prev) / prev * 100, 2)
    if not price:
        return None
    mc = parsed.get("market_cap")
    return _clean({
        "ticker":         ticker,
        "name":           raw.get("name") or ticker.replace(".NS", ""),
        "price":          price,
        "change_pct":     change_pct,
        "market_cap":     mc,
        "pe_ratio":       parsed.get("pe_ratio"),
        "pb_ratio":       parsed.get("pb_ratio"),
        "roe":            parsed.get("roe"),
        "revenue_growth": parsed.get("revenue_growth"),
        "profit_margin":  parsed.get("profit_margin"),
        "debt_to_equity": parsed.get("debt_to_equity"),
        "dividend_yield": parsed.get("dividend_yield"),
        "cap_type": (
            "large" if mc and mc >= _LARGE_CAP
            else "mid"   if mc and mc >= _MID_CAP
            else "small"
        ),
    })


async def _batch_returns(tickers: list[str]) -> dict[str, dict]:
    """1Y/3Y/5Y price returns per ticker via IndianAPI historical_data."""
    out: dict[str, dict] = {}

    async def _one(t: str) -> None:
        bare = t.replace(".NS", "").replace(".BO", "")
        raw = await indianapi_service.get_historical_data(bare, "5y")
        if not raw:
            return
        price_ds = next((d for d in (raw.get("datasets") or []) if d.get("metric") == "Price"), None)
        if not price_ds or not price_ds.get("values"):
            return
        values = price_ds["values"]
        closes = [float(v[1]) for v in values]
        n = len(closes)
        curr = closes[-1]

        def _ret(days: int) -> float | None:
            if n < days * 0.6:
                return None
            base = closes[max(0, n - days)]
            return round((curr / base - 1) * 100, 2) if base else None

        out[t] = {
            "return_1y": _ret(252),
            "return_3y": _ret(756),
            "return_5y": _ret(1260),
        }

    await asyncio.gather(*[_one(t) for t in tickers], return_exceptions=True)
    return out


async def get_sector_stocks(sector: str) -> dict:
    """Return all tracked stocks for a given sector with live quotes + price returns."""
    from app.services.peer_service import _SECTOR_PEERS

    key = f"sector:{sector}"

    # L1 in-memory
    if (cached := _cache.get(key)) is not None:
        return cached
    # L2 Redis (financial ratios are stable intraday — 24h TTL)
    if (cached := cache.get(key)) is not None:
        _cache.set(key, cached)
        return cached

    matched_key = next((k for k in _SECTOR_PEERS if k.lower() == sector.lower()), None)
    tickers = _SECTOR_PEERS.get(matched_key or sector, [])

    if not tickers:
        return {"sector": sector, "stocks": [], "error": "No stocks found for this sector"}

    # Fetch extended quotes + batch history returns in parallel
    quote_results, returns = await asyncio.gather(
        asyncio.gather(*[_fetch_sector_quote(t) for t in tickers]),
        _batch_returns(tickers),
    )

    stocks = [r for r in quote_results if r is not None]
    # Merge 1Y/3Y/5Y returns into each stock dict
    for s in stocks:
        ret = returns.get(s["ticker"], {})
        s["return_1y"] = ret.get("return_1y")
        s["return_3y"] = ret.get("return_3y")
        s["return_5y"] = ret.get("return_5y")

    stocks.sort(key=lambda x: -(x.get("market_cap") or 0))

    import statistics
    def med(field: str) -> float | None:
        vals = [s[field] for s in stocks if s.get(field) is not None]
        return round(statistics.median(vals), 3) if vals else None

    stats = {
        "median_pe":      med("pe_ratio"),
        "median_pb":      med("pb_ratio"),
        "median_return_1y": med("return_1y"),
        "count":          len(stocks),
    }

    out = {"sector": matched_key or sector, "stocks": stocks, "stats": stats}
    if stocks:
        _cache.set(key, out)
        cache.set(key, out, "analyst")   # 24h Redis — financial ratios are stable
    return out


async def _fetch_indices_from_indianapi() -> list[dict]:
    """Fallback when NSE direct is blocked (403 from cloud IPs, e.g. Render).
    IndianAPI's /indices works fine from any cloud IP but lacks open/high/low/
    year-high/year-low — those are set to None (MarketBar only needs
    name/price/change_pct/change_pts, so this is a safe degradation)."""
    # No exchange/index_type filter — "POPULAR" excludes sector indices like
    # Bank/IT/Pharma (those are under "SECTOR"), so fetch the full unfiltered list.
    rows = await indianapi_service.get_indices_data()
    out: list[dict] = []
    for row in rows:
        display = _INDIANAPI_INDEX_MAP.get((row.get("name") or "").upper())
        if not display:
            continue
        try:
            price = float(row["price"])
            net_change = float(row.get("netChange") or 0)
            out.append({
                "name":       display,
                "price":      round(price, 2),
                "prev_close": round(price - net_change, 2),
                "change_pct": float(row.get("percentChange") or 0),
                "change_pts": round(net_change, 2),
                "open":       None,
                "high":       None,
                "low":        None,
                "year_high":  None,
                "year_low":   None,
            })
        except (KeyError, TypeError, ValueError):
            continue

    order = list(_INDIANAPI_INDEX_MAP.values())
    out.sort(key=lambda x: order.index(x["name"]) if x["name"] in order else 99)
    return out


async def get_indices(_force: bool = False) -> list[dict]:
    """
    Fetch the 5 headline index prices — NSE direct primary (free, but blocked
    from cloud IPs like Render with a 403), IndianAPI as fallback.

    Outside NSE trading hours, prices can't have changed, so this returns the
    last snapshot with NO live fetch attempted at all (unless there's no
    snapshot yet, e.g. a cold start). During trading hours it's cached 60s
    in-process / 30min in Redis. Pass _force=True to bypass both checks
    (used by the end-of-day snapshot job).
    """
    if not _force and not is_market_hours():
        snap = cache.get(_SNAPSHOT_INDICES_KEY)
        if snap:
            return snap
        # No snapshot yet at all — fall through and fetch once so there's something to show

    if not _force:
        cached = _idx_cache.get("indices")
        if cached is not None:
            return cached

    loop = asyncio.get_event_loop()
    try:
        indices = await asyncio.wait_for(
            loop.run_in_executor(_pool, _fetch_indices_from_nse_sync),
            timeout=12.0,
        )
    except asyncio.TimeoutError:
        logger.warning("NSE indices fetch timed out")
        indices = []

    if not indices:
        indices = await _fetch_indices_from_indianapi()

    if indices:
        _idx_cache.set("indices", indices)
        cache.set(_SNAPSHOT_INDICES_KEY, indices, "market_snapshot")
    return indices




_OVERVIEW_REDIS_KEY = "market:overview"


async def get_market_overview(_force: bool = False) -> dict:
    if not _force and not is_market_hours():
        snap = cache.get(_SNAPSHOT_OVERVIEW_KEY)
        if snap:
            return snap
        # No snapshot yet at all — fall through and fetch once so there's something to show

    if not _force:
        # L1 — module-level in-memory (fastest)
        cached = _cache.get("market_overview")
        if cached:
            return cached
        # L2 — Redis (survives restarts / reloads)
        cached = cache.get(_OVERVIEW_REDIS_KEY)
        if cached:
            _cache.set("market_overview", cached)  # warm L1
            return cached

    loop = asyncio.get_event_loop()

    # ── Run indices + movers in parallel (both NSE-direct, no quota cost) ────
    nse_movers_task = loop.run_in_executor(_pool, _fetch_nse_gainers_losers_sync)
    indices_task    = get_indices()

    indices, nse_movers = await asyncio.gather(
        indices_task, nse_movers_task,
        return_exceptions=True,
    )

    if isinstance(indices, Exception):
        indices = []
    if isinstance(nse_movers, Exception):
        nse_movers = {"gainers": [], "losers": []}

    gainers     = nse_movers.get("gainers", [])
    losers      = nse_movers.get("losers",  [])
    high_volume: list[dict] = []
    stocks: list[dict]      = []  # full bucket list — not fetched anymore
    source = "nse"

    # Fallback when NSE direct is blocked (403 from cloud IPs, e.g. Render) —
    # restricted to the same large-cap universe as the primary path (see
    # _fetch_movers_from_indianapi docstring for why /trending alone isn't used).
    if not gainers and not losers:
        try:
            trending = await _fetch_movers_from_indianapi()
            gainers, losers = trending.get("gainers", []), trending.get("losers", [])
            if gainers or losers:
                source = "indianapi"
        except Exception as exc:
            logger.warning("IndianAPI trending fallback failed: %s", exc)

    logger.info("Market overview: source=%s gainers=%d losers=%d", source, len(gainers), len(losers))

    result = {
        "indices":           indices,
        "gainers":           gainers,
        "losers":            losers,
        "high_volume":       high_volume,
        "fetched_at":        int(__import__("time").time()),
    }
    has_data = bool(gainers or losers or indices)
    old_cached = _cache.get("market_overview") or cache.get(_OVERVIEW_REDIS_KEY)
    if has_data or not old_cached:
        _cache.set("market_overview", result)
        cache.set(_OVERVIEW_REDIS_KEY, result, "overview")
        cache.set(_SNAPSHOT_OVERVIEW_KEY, result, "market_snapshot")
    else:
        logger.warning("Market overview: both NSE and IndianAPI returned no data — keeping existing cache")
    return _cache.get("market_overview") or result


async def get_cap_stocks(size: str) -> dict:
    """Return all tracked stocks for a cap tier. Triggers overview fetch if cache is cold."""
    key = f"cap:{size}"
    if (c := _cache.get(key)) is not None:
        return c
    # Warm the cache by running the full overview fetch
    await get_market_overview()
    return _cache.get(key) or {"cap": size, "stocks": [], "count": 0}


# ── IndianAPI-backed market data endpoints ────────────────────────────────────

async def get_ipo() -> list[dict]:
    """Upcoming and recent IPOs via IndianAPI. Cached 1h."""
    ck = "market:ipo"
    if (hit := cache.get(ck)) is not None:
        return hit
    from app.services.indianapi_service import get_ipo as _ipo
    data = await _ipo()
    if data:
        cache.set(ck, data, "nifty50")   # 1h TTL
    return data or []


async def get_commodities() -> list[dict]:
    """Commodity prices (gold, silver, crude, etc.) via IndianAPI. Cached 10min."""
    ck = "market:commodities"
    if (hit := cache.get(ck)) is not None:
        return hit
    from app.services.indianapi_service import get_commodities as _comm
    data = await _comm()
    if data:
        cache.set(ck, data, "market")
    return data or []


async def get_52week() -> dict:
    """52-week highs and lows via IndianAPI. Cached 1h."""
    ck = "market:52week"
    if (hit := cache.get(ck)) is not None:
        return hit
    from app.services.indianapi_service import get_52_week_high_low
    data = await get_52_week_high_low()
    if data.get("highs") or data.get("lows"):
        cache.set(ck, data, "nifty50")
    return data


async def get_announcements(ticker: str | None = None) -> list[dict]:
    """Corporate announcements via IndianAPI. Cached 30min."""
    ck = f"market:announcements:{ticker or 'all'}"
    if (hit := cache.get(ck)) is not None:
        return hit
    from app.services.indianapi_service import get_recent_announcements
    data = await get_recent_announcements(ticker)
    if data:
        cache.set(ck, data, "sector")
    return data or []


async def get_corporate_actions(ticker: str | None = None) -> list[dict]:
    """Dividends, splits, bonuses via IndianAPI. Cached 1h."""
    ck = f"market:corp_actions:{ticker or 'all'}"
    if (hit := cache.get(ck)) is not None:
        return hit
    from app.services.indianapi_service import get_corporate_actions as _ca
    data = await _ca(ticker)
    if data:
        cache.set(ck, data, "nifty50")
    return data or []


async def get_price_shockers() -> list[dict]:
    """Stocks with unusual price movements via IndianAPI. Cached 10min."""
    ck = "market:price_shockers"
    if (hit := cache.get(ck)) is not None:
        return hit
    from app.services.indianapi_service import get_price_shockers as _ps
    data = await _ps()
    if data:
        cache.set(ck, data, "market")
    return data or []
