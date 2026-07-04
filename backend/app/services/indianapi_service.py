"""
IndianAPI.in — sole live market-data source for Aegis (dev.indianapi.in, v2).

Replaces yfinance entirely. Metered plan: ~10k requests/month, so every
function here leans hard on the shared Redis cache — see TTL categories
in app/core/cache.py. A 429 opens a circuit breaker that short-circuits
ALL calls for _BACKOFF_SECONDS to let the rate-limit window reset.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx

from app.core.cache import cache
from app.core.config import get_settings

logger = logging.getLogger(__name__)
BASE_URL = "https://dev.indianapi.in"

# ── 429 circuit breaker ───────────────────────────────────────────────────────
_BACKOFF_SECONDS = 300   # 5 minutes
_blocked_until: float = 0.0


def _headers() -> dict[str, str]:
    return {"X-API-Key": get_settings().indianapi_key}


async def _get(path: str, params: dict | None = None) -> dict | list | None:
    global _blocked_until
    if not get_settings().indianapi_enabled:
        return None   # monthly quota exhausted — all calls short-circuit
    if time.time() < _blocked_until:
        remaining = int(_blocked_until - time.time())
        logger.debug("IndianAPI circuit open — skipping %s (%ds remaining)", path, remaining)
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{BASE_URL}{path}", headers=_headers(), params=params or {})
            if r.status_code == 429:
                _blocked_until = time.time() + _BACKOFF_SECONDS
                logger.warning("IndianAPI 429 on %s — circuit open for %ds", path, _BACKOFF_SECONDS)
                return None
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("IndianAPI %s error: %s", path, e)
        return None


async def _post(path: str, json_body: dict) -> dict | None:
    global _blocked_until
    if not get_settings().indianapi_enabled:
        return None
    if time.time() < _blocked_until:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{BASE_URL}{path}", headers=_headers(), json=json_body)
            if r.status_code == 429:
                _blocked_until = time.time() + _BACKOFF_SECONDS
                logger.warning("IndianAPI 429 on %s — circuit open for %ds", path, _BACKOFF_SECONDS)
                return None
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("IndianAPI %s error: %s", path, e)
        return None


def indianapi_blocked() -> bool:
    return time.time() < _blocked_until


# ── value parsers ─────────────────────────────────────────────────────────────

def _f(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _i(v) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


def _cr_to_inr(v) -> float | None:
    """IndianAPI market caps are quoted in ₹ Crore — convert to raw INR."""
    f = _f(v)
    return f * 1e7 if f is not None else None


def _pct_to_fraction(v) -> float | None:
    """IndianAPI percentages (e.g. 4.58 meaning 4.58%) → fraction (0.0458)."""
    f = _f(v)
    return f / 100 if f is not None else None


def _ratio_to_pct(v) -> float | None:
    """IndianAPI D/E-style ratios (e.g. 0.44) → percentage number (44.0),
    matching the convention the rest of Aegis' ratio_signals() expects."""
    f = _f(v)
    return f * 100 if f is not None else None


def _parse_mcap(raw) -> float | None:
    """Parse loosely-formatted market cap strings like '17.15L Cr', '5.43 T'."""
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


# ── normalizer for movers-style list endpoints (trending, most_active, etc.) ──

def _normalize(raw: dict) -> dict | None:
    """Map any IndianAPI movers-list stock dict → Aegis' internal Stock format."""
    ticker = (
        raw.get("stock_name") or raw.get("ticker") or raw.get("ticker_id") or
        raw.get("symbol") or raw.get("nse_code") or
        raw.get("ric") or raw.get("company") or raw.get("company_name") or ""
    ).strip().upper()
    ticker = ticker.replace(".NS", "").replace(".BO", "")
    if not ticker:
        return None

    name = (raw.get("company_name") or raw.get("company") or raw.get("name") or ticker).strip()

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
        "ticker":      f"{ticker}.NS",
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


# ── /stock — live price + technicals + shareholding + corp actions + news ────

def _latest_pct(categories: list[dict] | None) -> float | None:
    if not categories:
        return None
    try:
        latest = max(categories, key=lambda c: c.get("holdingDate", ""))
        return _f(latest.get("percentage"))
    except Exception:
        return None


def parse_stock(raw: dict) -> dict:
    """Flatten /stock's response into Aegis' quote schema (best-effort)."""
    reuse = raw.get("stockDetailsReusableData") or {}
    cur = raw.get("currentPrice") or {}
    price = _f(cur.get("NSE")) or _f(cur.get("BSE")) or _f(reuse.get("price"))

    # Shareholding: array of {categoryName, displayName, categories:[{holdingDate,percentage}]}
    promoter_pct = fii_pct = dii_pct = None
    for cat in (raw.get("shareholding") or []):
        disp = (cat.get("displayName") or "").upper()
        pct = _latest_pct(cat.get("categories"))
        if disp == "PROMOTER":
            promoter_pct = pct
        elif disp == "FII":
            fii_pct = pct
        elif disp in ("MF", "DII"):
            dii_pct = pct

    dma = {
        f"dma{row.get('days')}": _f(row.get("nsePrice")) or _f(row.get("bsePrice"))
        for row in (raw.get("stockTechnicalData") or [])
    }

    return {
        "company_name":  raw.get("companyName"),
        "industry":      raw.get("industry"),
        "sector":        raw.get("industry"),
        "current_price": price,
        "previous_close": _f(reuse.get("close")),
        "day_high":      _f(reuse.get("high")),
        "day_low":       _f(reuse.get("low")),
        "week52_high":   _f(reuse.get("yhigh")) or _f(raw.get("yearHigh")),
        "week52_low":    _f(reuse.get("ylow")) or _f(raw.get("yearLow")),
        "market_cap":    _cr_to_inr(reuse.get("marketCap")),
        "pe_ratio":      _f(reuse.get("pPerEBasicExcludingExtraordinaryItemsTTM")),
        "dividend_yield": _pct_to_fraction(reuse.get("currentDividendYieldCommonStockPrimaryIssueLTM")),
        "debt_to_equity": _ratio_to_pct(reuse.get("totalDebtPerTotalEquityMostRecentQuarter")),
        "held_by_insiders_pct":     promoter_pct,
        "held_by_institutions_pct": (fii_pct or 0) + (dii_pct or 0) if (fii_pct or dii_pct) else None,
        "summary":       ((raw.get("companyProfile") or {}).get("companyDescription") or "")[:600],
        "website":       None,
        **dma,
    }


def parse_stock_data(raw: dict) -> dict:
    """Flatten /get_stock_data's response into clean ratio/growth fields."""
    stats = raw.get("stats") or {}
    financials = {f.get("title"): f for f in (raw.get("financials") or [])}
    revenue = financials.get("Revenue") or {}
    profit = financials.get("Profit") or {}

    return {
        "pe_ratio":         _f(stats.get("peRatio")),
        "pb_ratio":         _f(stats.get("pbRatio")),
        "eps":              _f(stats.get("epsTtm")),
        "book_value":       _f(stats.get("bookValue")),
        "roe":              _pct_to_fraction(stats.get("roe")),
        "debt_to_equity":   _ratio_to_pct(stats.get("debtToEquity")),
        "dividend_yield":   _pct_to_fraction(stats.get("divYield")),
        "profit_margin":    _pct_to_fraction(stats.get("netProfitMargin")),
        "operating_margin": _pct_to_fraction(stats.get("operatingProfitMargin")),
        "market_cap":       _cr_to_inr(stats.get("marketCap")),
        "industry_pe":      _f(stats.get("industryPe")),
        "peg_ratio":        _f(stats.get("pegRatio")),
        "cap_type":         (stats.get("cappedType") or "").lower().replace(" cap", "") or None,
        "sector_pe":        _f(stats.get("sectorPe")),
        "sector_pb":        _f(stats.get("sectorPb")),
        "sector_roe":       _pct_to_fraction(stats.get("sectorRoe")),
        "sector_roce":      _pct_to_fraction(stats.get("sectorRoce")),
        "sector_dividend_yield": _pct_to_fraction(stats.get("sectorDivYield")),
        "revenue_growth":   _f((revenue.get("cagr") or {}).get("oneYearTtm")),
        "earnings_growth":  _f((profit.get("cagr") or {}).get("oneYearTtm")),
        "company_summary":  raw.get("company_summary"),
        "nse_scrip_code":   raw.get("nse_scrip_code"),
        "bse_scrip_code":   raw.get("bse_scrip_code"),
    }


async def get_stock(name_or_symbol: str) -> dict | None:
    """/stock — live price, technicals, shareholding, peers, corp actions, news.
    Cached — shared by get_quote_bundle() and peer_service so both don't
    double-hit the API for the same ticker within the TTL window."""
    ck = f"indianapi:stock:{name_or_symbol}"
    hit = cache.get(ck)
    if hit is not None:
        return hit or None
    data = await _get("/stock", {"symbol": name_or_symbol})
    result = data if isinstance(data, dict) and "companyName" in data else None
    if result:
        cache.set(ck, result, "prices")
    return result


async def get_stock_data(name_or_symbol: str) -> dict | None:
    """/get_stock_data — clean ratios, margins, growth, sector comparisons. Cached."""
    ck = f"indianapi:stock_data:{name_or_symbol}"
    hit = cache.get(ck)
    if hit is not None:
        return hit or None
    data = await _get("/get_stock_data", {"stock_name": name_or_symbol})
    result = data if isinstance(data, dict) and "stats" in data else None
    if result:
        cache.set(ck, result, "peers")   # fundamentals-only, changes slowly
    return result


async def get_peer_companies(stock_raw: dict) -> list[dict]:
    """/stock's companyProfile.peerCompanyList — real, curated peers with ratios,
    free as part of the same call get_quote already makes. No .NS/.BO symbol is
    given, so resolve one via the free static stock list (name -> nse-code)."""
    entries = ((stock_raw.get("companyProfile") or {}).get("peerCompanyList") or [])
    if not entries:
        return []
    all_stocks = await _get_all_stocks()
    by_name = {s.get("name", "").strip().lower(): s for s in all_stocks if s.get("name")}

    peers: list[dict] = []
    for e in entries:
        name = (e.get("companyName") or "").strip()
        nse = (by_name.get(name.lower()) or {}).get("nse-code")
        if not nse:
            continue
        peers.append({
            "ticker": f"{nse}.NS",
            "name": name,
            "price": _f(e.get("price")),
            "day_change_pct": _f(e.get("percentChange")),
            "market_cap": _cr_to_inr(e.get("marketCap")),
            "pe_ratio": _f(e.get("priceToEarningsValueRatio")),
            "pb_ratio": _f(e.get("priceToBookValueRatio")),
            "roe": _pct_to_fraction(e.get("returnOnAverageEquityTrailing12Month") or e.get("returnOnAverageEquity5YearAverage")),
            "profit_margin": _pct_to_fraction(e.get("netProfitMarginPercentTrailing12Month") or e.get("netProfitMargin5YearAverage")),
            "dividend_yield": _pct_to_fraction(e.get("dividendYieldIndicatedAnnualDividend")),
            "week52_high": _f(e.get("yhigh")),
            "week52_low": _f(e.get("ylow")),
        })
    return peers


async def get_quote_bundle(ticker: str) -> dict:
    """Merge /stock + /get_stock_data into one flat quote dict. Cached by caller."""
    bare = ticker.replace(".NS", "").replace(".BO", "")
    ck = f"indianapi:quote_bundle:{bare}"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    stock_raw = await get_stock(bare)
    if not stock_raw:
        return {}
    data = parse_stock(stock_raw)

    stock_data_raw = await get_stock_data(bare)
    if stock_data_raw:
        extra = parse_stock_data(stock_data_raw)
        for k, v in extra.items():
            if v is not None and data.get(k) is None:
                data[k] = v
            elif k not in data:
                data[k] = v

    if data.get("current_price"):
        cache.set(ck, data, "prices")
    return data


# ── /historical_data — price + DMA50/DMA200 + volume, no intraday OHLC ────────

_PERIOD_MAP = {
    "1mo": "1m", "1m": "1m",
    "6mo": "6m", "6m": "6m",
    "1y": "1yr", "1yr": "1yr",
    "3y": "3yr", "3yr": "3yr",
    "5y": "5yr", "5yr": "5yr",
    "10y": "10yr", "10yr": "10yr",
    "max": "max", "2y": "3yr",
}


async def get_historical_data(name_or_symbol: str, period: str = "1y") -> dict | None:
    """/historical_data — cached; datasets: Price, DMA50, DMA200, Volume.

    NOTE: filter="default" (which bundles Price+DMA50+DMA200+Volume) silently
    caps at ~1 year of DAILY data no matter what period is requested — a real
    quirk in the live API, verified empirically. filter="price" honours the
    period correctly (weekly granularity beyond 1yr) but drops DMA/volume.
    So: short periods use "default" (daily + DMA + volume); long periods fall
    back to "price" (weekly, price-only) to actually cover the requested range.
    """
    api_period = _PERIOD_MAP.get(period, "1yr")
    use_price_only = api_period in ("3yr", "5yr", "10yr", "max")
    filt = "price" if use_price_only else "default"
    ck = f"indianapi:history:{name_or_symbol}:{api_period}:{filt}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = await _get("/historical_data", {
        "stock_name": name_or_symbol, "period": api_period, "filter": filt,
    })
    result = data if isinstance(data, dict) and data.get("datasets") else None
    if result:
        cache.set(ck, result, "history")
    return result


# ── /historical_stats — full quarterly financials (replaces yfinance) ────────

async def get_historical_stats(name_or_symbol: str, stats: str = "all") -> dict | None:
    ck = f"indianapi:hstats:{name_or_symbol}:{stats}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = await _get("/historical_stats", {"stock_name": name_or_symbol, "stats": stats})
    result = data if isinstance(data, dict) else None
    if result:
        cache.set(ck, result, "history")
    return result


# ── /stock_target_price, /stock_forecasts — analyst estimates ────────────────
# Both require IndianAPI's internal stock_id (e.g. "S0003051"), not an NSE
# symbol, so resolve via the free static stock list first.

async def _stock_id_for(name_or_symbol: str) -> str | None:
    stocks = await _get_all_stocks()
    bare = name_or_symbol.upper().strip()
    for s in stocks:
        if (s.get("nse-code") or "").upper() == bare:
            return s.get("id")
    return None


async def get_stock_target_price(name_or_symbol: str) -> dict | None:
    """/stock_target_price — analyst price targets + Buy/Hold/Sell distribution.
    Cached 24h — analyst targets update at most weekly."""
    ck = f"indianapi:target:{name_or_symbol}"
    hit = cache.get(ck)
    if hit is not None:
        return hit or None

    stock_id = await _stock_id_for(name_or_symbol)
    if not stock_id:
        return None
    data = await _get("/stock_target_price", {"stock_id": stock_id})
    if not isinstance(data, dict) or "error" in data:
        return None

    pt = data.get("priceTarget") or {}
    rec = data.get("recommendation") or {}
    stats = (rec.get("Statistics") or {}).get("Statistic") or []
    by_rating = {int(s["Recommendation"]): int(s.get("NumberOfAnalysts") or 0) for s in stats if "Recommendation" in s}

    result = {
        "mean_target": _f(pt.get("Mean")),
        "high_target": _f(pt.get("High")),
        "low_target": _f(pt.get("Low")),
        "median_target": _f(pt.get("Median")),
        "strong_buy": by_rating.get(1, 0),
        "buy": by_rating.get(2, 0),
        "hold": by_rating.get(3, 0),
        "sell": by_rating.get(4, 0),
        "strong_sell": by_rating.get(5, 0),
    }
    if result["mean_target"] is None and not by_rating:
        return None
    cache.set(ck, result, "analyst")
    return result


async def get_stock_forecasts(name_or_symbol: str) -> dict | None:
    """/stock_forecasts — analyst revenue (SAL) + EPS estimates by fiscal year.
    Cached 24h."""
    ck = f"indianapi:forecasts:{name_or_symbol}"
    hit = cache.get(ck)
    if hit is not None:
        return hit or None

    stock_id = await _stock_id_for(name_or_symbol)
    if not stock_id:
        return None

    async def _measure(code: str) -> dict:
        data = await _get("/stock_forecasts", {
            "stock_id": stock_id, "measure_code": code,
            "period_type": "Annual", "data_type": "Estimates", "age": "Current",
        })
        if not isinstance(data, dict) or "error" in data:
            return {}
        rows = data.get("data") or data.get("values") or []
        out: dict[str, float] = {}
        for r in rows:
            period = r.get("period") or r.get("fiscalYear") or r.get("FiscalYear")
            val = _f(r.get("value") or r.get("Value") or r.get("mean") or r.get("Mean"))
            if period and val is not None:
                out[str(period)] = val
        return out

    revenue_by_period, eps_by_period = await asyncio.gather(_measure("SAL"), _measure("EPS"))
    if not revenue_by_period and not eps_by_period:
        return None

    periods = sorted(set(revenue_by_period) | set(eps_by_period))
    result = {
        "periods": [
            {"period": p, "revenue": revenue_by_period.get(p), "eps": eps_by_period.get(p)}
            for p in periods
        ]
    }
    cache.set(ck, result, "analyst")
    return result


# ── /concalls — earnings call transcripts ─────────────────────────────────────

async def get_concalls(name_or_symbol: str) -> list[dict]:
    ck = f"indianapi:concalls:{name_or_symbol}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    data = await _get("/concalls", {"stock_name": name_or_symbol})
    result = data if isinstance(data, list) else []
    if result:
        cache.set(ck, result, "corporate")
    return result


# ── batch live price (chunked, tolerant of individual bad symbols) ───────────

async def batch_live_price(symbols: list[str], exchange: str = "NSE", chunk_size: int = 40) -> dict[str, dict]:
    """
    /nse_stock_batch_live_price or /bse_stock_batch_live_price.

    A single invalid/delisted symbol fails the WHOLE batch on this API, so we
    chunk requests and, on a chunk failure, retry that chunk's symbols one by
    one to isolate and skip only the bad ones.
    """
    path = "/nse_stock_batch_live_price" if exchange == "NSE" else "/bse_stock_batch_live_price"
    out: dict[str, dict] = {}

    chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
    for chunk in chunks:
        data = await _post(path, {"stock_symbols": chunk})
        if isinstance(data, dict) and "error" not in data:
            out.update(data)
            continue
        # Chunk failed (likely one bad symbol) — retry individually
        for sym in chunk:
            single = await _post(path, {"stock_symbols": [sym]})
            if isinstance(single, dict) and "error" not in single:
                out.update(single)
    return out


# ── /indices ───────────────────────────────────────────────────────────────────

async def get_indices_data(exchange: str | None = None, index_type: str | None = None) -> list[dict]:
    ck = f"indianapi:indices:{exchange}:{index_type}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    params: dict[str, str] = {}
    if exchange:
        params["exchange"] = exchange
    if index_type:
        params["index_type"] = index_type
    data = await _get("/indices", params)
    result = (data or {}).get("indices", []) if isinstance(data, dict) else []
    if result:
        cache.set(ck, result, "market")
    return result


# ── Search — local, quota-free (downloads the public static stock list once) ─

_STOCK_LIST_CACHE_KEY = "indianapi:all_stocks"


async def _get_all_stocks() -> list[dict]:
    hit = cache.get(_STOCK_LIST_CACHE_KEY)
    if hit is not None:
        return hit
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{BASE_URL}/static/all_stocks.json")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("IndianAPI all_stocks.json fetch failed: %s", e)
        return []
    if isinstance(data, list) and data:
        cache.set(_STOCK_LIST_CACHE_KEY, data, "mf_list")   # 24h — static list, no quota cost
    return data if isinstance(data, list) else []


async def search_stocks(query: str, limit: int = 8) -> list[dict]:
    """Prefix/substring match against the full NSE+BSE stock list. Free — no API quota used."""
    stocks = await _get_all_stocks()
    if not stocks:
        return []
    q_up, q_lo = query.upper(), query.lower()
    ticker_hits: list[dict] = []
    name_hits: list[dict] = []
    for s in stocks:
        nse = (s.get("nse-code") or "").strip()
        name = (s.get("name") or "").strip()
        if not nse or not name:
            continue
        entry = {"symbol": f"{nse}.NS", "name": name, "exchange": "NSE"}
        if nse.upper().startswith(q_up):
            ticker_hits.append(entry)
        elif name.lower().startswith(q_lo):
            name_hits.append(entry)
        elif len(query) >= 3 and q_lo in name.lower():
            name_hits.append(entry)
    return (ticker_hits + name_hits)[:limit]


# ── Market overview / discovery endpoints ─────────────────────────────────────

async def get_trending() -> dict[str, list[dict]]:
    """/trending — top gainers and losers."""
    data = await _get("/trending")
    if not data or not isinstance(data, dict):
        return {"gainers": [], "losers": []}
    nested = data.get("trending_stocks") or {}
    raw_gainers = nested.get("top_gainers") or data.get("gainers") or []
    raw_losers = nested.get("top_losers") or data.get("losers") or []
    gainers = [s for s in (_normalize(r) for r in raw_gainers) if s]
    losers = [s for s in (_normalize(r) for r in raw_losers) if s]
    return {"gainers": gainers, "losers": losers}


async def get_nse_most_active() -> list[dict]:
    data = await _get("/NSE_most_active")
    if not data:
        return []
    items = data if isinstance(data, list) else (data.get("data") or [])
    return [s for s in (_normalize(r) for r in items) if s]


async def get_bse_most_active() -> list[dict]:
    data = await _get("/BSE_most_active")
    if not data:
        return []
    items = data if isinstance(data, list) else (data.get("data") or [])
    return [s for s in (_normalize(r) for r in items) if s]


async def get_52_week_high_low() -> dict[str, list[dict]]:
    data = await _get("/fetch_52_week_high_low_data")
    if not data or not isinstance(data, dict):
        return {"highs": [], "lows": []}
    nse = data.get("NSE_52WeekHighLow") or {}
    highs = nse.get("high52Week") or []
    lows = nse.get("low52Week") or []
    return {
        "highs": [s for s in (_normalize(r) for r in highs) if s],
        "lows":  [s for s in (_normalize(r) for r in lows) if s],
    }


async def get_price_shockers() -> list[dict]:
    data = await _get("/price_shockers")
    if not data or not isinstance(data, dict):
        return []
    items = (data.get("NSE_PriceShocker") or []) + (data.get("BSE_PriceShocker") or [])
    return [s for s in (_normalize(r) for r in items) if s]


async def get_news(page_no: int = 1, size: int = 20) -> list[dict]:
    data = await _get("/news", {"page_no": page_no, "size": size})
    if not data:
        return []
    return data if isinstance(data, list) else (data.get("data") or [])


async def get_company_news(stock: str) -> list[dict]:
    data = await _get("/company_news", {"stock_name": stock})
    if not data:
        return []
    return data if isinstance(data, list) else (data.get("data") or [])


async def get_ipo() -> list[dict]:
    data = await _get("/ipo")
    if not data:
        return []
    if isinstance(data, dict):
        return (data.get("upcoming") or []) + (data.get("open") or []) + (data.get("listed") or [])
    return data


async def get_commodities() -> list[dict]:
    data = await _get("/commodities")
    if not data:
        return []
    return data if isinstance(data, list) else (data.get("data") or [])


async def get_recent_announcements(ticker: str | None = None) -> list[dict]:
    ck = f"indianapi:announcements:{ticker or 'all'}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    params = {"stock_name": ticker} if ticker else {}
    data = await _get("/recent_announcements", params)
    result: list[dict] = data if isinstance(data, list) else ((data or {}).get("data") or [])
    if result:
        cache.set(ck, result, "filing")
    return result


async def get_corporate_actions(ticker: str | None = None) -> list[dict]:
    ck = f"indianapi:corpactions:{ticker or 'all'}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    params = {"stock_name": ticker} if ticker else {}
    data = await _get("/corporate_actions", params)
    result: list[dict] = data if isinstance(data, list) else ((data or {}).get("data") or [])
    if result:
        cache.set(ck, result, "corporate")
    return result
