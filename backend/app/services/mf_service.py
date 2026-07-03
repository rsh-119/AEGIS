"""
mf_service.py — Indian Mutual Fund and ETF data.
  MF data  : mfapi.in (AMFI source, free, no key needed)
  ETF data : yfinance (NSE-listed ETFs)
  Benchmark: ^NSEI (Nifty 50) via yfinance
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import httpx
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from app.core.cache import cache
from app.core.yf_session import YF_SESSION, yf_blocked, yf_on_rate_limit

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=12)

MFAPI = "https://api.mfapi.in"
NIFTY50 = "^NSEI"

# ── NSE-listed ETFs ────────────────────────────────────────────────────────────
_ETFS: list[tuple[str, str, str, str]] = [
    # (ticker, name, asset_class, sub_category)
    ("NIFTYBEES.NS",  "Nippon India ETF Nifty BeES",           "Equity", "Index"),
    ("JUNIORBEES.NS", "Nippon India ETF Junior BeES",          "Equity", "Index"),
    ("SETFNIF50.NS",  "SBI ETF Nifty 50",                      "Equity", "Index"),
    ("HDFCNIFTY.NS",  "HDFC Nifty 50 ETF",                     "Equity", "Index"),
    ("MOM100.NS",     "Motilal Oswal Nasdaq 100 ETF",          "Equity", "Global"),
    ("BANKBEES.NS",   "Nippon India Banking ETF",              "Equity", "Banking"),
    ("ITBEES.NS",     "Nippon India ETF Nifty IT",             "Equity", "IT"),
    ("PHARMABEES.NS", "Nippon India ETF Pharma BeES",          "Equity", "Pharma"),
    ("INFRABEES.NS",  "Nippon India ETF Infra BeES",           "Equity", "Infra"),
    ("PSUBNKBEES.NS", "Nippon India ETF PSU Bank BeES",        "Equity", "PSU"),
    ("ICICIB22.NS",   "ICICI Prudential Bharat 22 ETF",        "Equity", "PSU"),
    ("NV20.NS",       "UTI Nifty 200 Momentum 30 ETF",         "Equity", "Factor"),
    ("GOLDBEES.NS",   "Nippon India Gold ETF",                  "Gold",   "Commodity"),
    ("SILVERBEES.NS", "Nippon India Silver ETF",                "Silver", "Commodity"),
    ("LIQUIDBEES.NS", "Nippon India Liquid ETF",                "Debt",   "Liquid"),
    ("SHARIABEES.NS", "Nippon India ETF Shariah BeES",         "Equity", "Shariah"),
]

# ── MF category keywords ───────────────────────────────────────────────────────
_CAT_KEYS: dict[str, list[str]] = {
    "equity":  ["equity", "growth", "large cap", "mid cap", "small cap",
                "multi cap", "flexi cap", "focused", "value", "contra",
                "dividend yield"],
    "debt":    ["debt", "liquid", "bond", "gilt", "overnight",
                "money market", "ultra short", "credit risk",
                "corporate bond", "banking and psu", "floater"],
    "hybrid":  ["hybrid", "balanced", "aggressive", "conservative",
                "arbitrage", "dynamic asset", "multi asset"],
    "index":   ["index fund", "nifty", "sensex", "bse 500"],
    "elss":    ["elss", "tax saver", "tax saving", "tax-saver"],
    "gold":    ["gold"],
}

# ── NAV helpers ────────────────────────────────────────────────────────────────
def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%d-%m-%Y")


def _calc_return(navs: list[dict], days: int) -> float | None:
    """navs sorted newest-first. Returns % gain or None."""
    if not navs:
        return None
    try:
        latest = float(navs[0]["nav"])
        cutoff = datetime.now() - timedelta(days=days)
        past_entries = [n for n in navs if _parse_date(n["date"]) <= cutoff]
        if not past_entries:
            return None
        past = float(past_entries[0]["nav"])
        if past == 0:
            return None
        return round((latest - past) / past * 100, 2)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MF functions
# ─────────────────────────────────────────────────────────────────────────────

async def get_mf_list(
    search: str = "",
    category: str = "",
    page: int = 1,
    limit: int = 40,
) -> dict:
    """Paginated list of all mutual funds (names + codes only)."""
    ck = "mf:full_list"
    all_funds = cache.get(ck)
    if all_funds is None:
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.get(f"{MFAPI}/mf")
            resp.raise_for_status()
            all_funds = resp.json()
        cache.set(ck, all_funds, "mf_list")

    if search:
        q = search.lower()
        all_funds = [f for f in all_funds if q in f["schemeName"].lower()]

    if category:
        keys = _CAT_KEYS.get(category.lower(), [category.lower()])
        all_funds = [
            f for f in all_funds
            if any(kw in f["schemeName"].lower() for kw in keys)
        ]

    total = len(all_funds)
    offset = (page - 1) * limit
    page_funds = all_funds[offset: offset + limit]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "funds": [
            {"scheme_code": f["schemeCode"], "name": f["schemeName"]}
            for f in page_funds
        ],
    }


async def get_mf_returns_batch(scheme_codes: list[int]) -> dict[int, dict]:
    """Fetch 1Y/3Y/5Y returns for a batch of scheme codes (max 40).

    Uses a single shared httpx client across all requests — one connection
    pool instead of 40 separate TCP+SSL handshakes.
    """
    codes = scheme_codes[:40]

    # Serve cached codes immediately; only fetch the rest
    result: dict[int, dict] = {}
    uncached: list[int] = []
    for code in codes:
        hit = cache.get(f"mf:ret:{code}")
        if hit is not None:
            result[code] = hit
        else:
            uncached.append(code)

    if not uncached:
        return result

    limits = httpx.Limits(max_connections=50, max_keepalive_connections=50)
    async with httpx.AsyncClient(
        timeout=20,
        limits=limits,
        http2=True,        # multiplexes multiple requests over one connection
    ) as client:
        async def _fetch(code: int) -> tuple[int, dict | None]:
            try:
                resp = await client.get(f"{MFAPI}/mf/{code}")
                resp.raise_for_status()
                data = resp.json()
                navs = data.get("data", [])
                meta = data.get("meta", {})
                nav_t = float(navs[0]["nav"]) if navs else None
                nav_p = float(navs[1]["nav"]) if len(navs) > 1 else None
                res = {
                    "nav":         nav_t,
                    "nav_date":    navs[0]["date"] if navs else None,
                    "return_1d":   round((nav_t - nav_p) / nav_p * 100, 2)
                                   if nav_t and nav_p else None,
                    "return_1y":   _calc_return(navs, 365),
                    "return_3y":   _calc_return(navs, 1095),
                    "return_5y":   _calc_return(navs, 1825),
                    "fund_house":  meta.get("fund_house", ""),
                    "scheme_type": meta.get("scheme_type", ""),
                }
                cache.set(f"mf:ret:{code}", res, "mf_nav")
                return code, res
            except Exception as e:
                logger.debug("mf returns %s: %s", code, e)
                return code, None

        fetched = await asyncio.gather(*[_fetch(c) for c in uncached])
        result.update({k: v for k, v in fetched if v is not None})

    return result


async def get_mf_detail(scheme_code: int) -> dict:
    """Full MF detail + NAV chart (5 years)."""
    ck = f"mf:detail:{scheme_code}"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.get(f"{MFAPI}/mf/{scheme_code}")
        resp.raise_for_status()
        data = resp.json()

    navs = data.get("data", [])    # newest first
    meta = data.get("meta", {})

    cutoff_5y = datetime.now() - timedelta(days=1825)
    chart: list[dict] = []
    for n in reversed(navs):       # oldest first for chart
        try:
            dt = _parse_date(n["date"])
            if dt >= cutoff_5y:
                chart.append({"date": dt.strftime("%Y-%m-%d"), "nav": float(n["nav"])})
        except Exception:
            continue

    start_date = chart[0]["date"] if chart else None

    result = {
        "scheme_code":    scheme_code,
        "name":           meta.get("scheme_name", ""),
        "fund_house":     meta.get("fund_house", ""),
        "scheme_type":    meta.get("scheme_type", ""),
        "scheme_category": meta.get("scheme_category", ""),
        "nav":            float(navs[0]["nav"]) if navs else None,
        "nav_date":       navs[0]["date"] if navs else None,
        "return_1y":      _calc_return(navs, 365),
        "return_3y":      _calc_return(navs, 1095),
        "return_5y":      _calc_return(navs, 1825),
        "chart":          chart,
        "chart_start":    start_date,
    }
    cache.set(ck, result, "mf_nav")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Nifty 50 benchmark
# ─────────────────────────────────────────────────────────────────────────────

async def get_nifty50_chart(from_date: str) -> list[dict]:
    """Nifty 50 close prices from `from_date` (YYYY-MM-DD) for chart overlay."""
    ck = f"nifty50:{from_date}"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    def _fetch():
        if yf_blocked():
            return []
        try:
            hist = yf.Ticker(NIFTY50, session=YF_SESSION).history(start=from_date, auto_adjust=True)
            if hist.empty:
                return []
            return [
                {"date": dt.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2)}
                for dt, row in hist.iterrows()
            ]
        except YFRateLimitError:
            yf_on_rate_limit()
            return []
        except Exception:
            return []

    loop = asyncio.get_event_loop()
    pts = await loop.run_in_executor(_pool, _fetch)
    if pts:
        cache.set(ck, pts, "nifty50")
    return pts


# ─────────────────────────────────────────────────────────────────────────────
# ETF functions
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_etf_list_sync() -> list[dict]:
    """
    Batch-download all ETF price histories in ONE yfinance call instead
    of 23 separate ticker calls. ~5-10x faster.
    """
    import pandas as pd

    tickers = [t for t, _, _, _ in _ETFS]
    meta    = {t: (n, a, s) for t, n, a, s in _ETFS}

    try:
        raw = yf.download(
            tickers,
            period="5y",
            auto_adjust=True,
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as e:
        logger.warning("ETF batch download failed: %s", e)
        return []

    result = []
    for ticker in tickers:
        try:
            name, asset_class, sub = meta[ticker]

            # MultiIndex when >1 ticker: raw[ticker] → DataFrame(OHLCV)
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker not in raw.columns.get_level_values(0):
                    continue
                h = raw[ticker].dropna(how="all")
            else:
                h = raw.dropna(how="all")

            if h.empty or "Close" not in h.columns:
                continue

            price = float(h["Close"].iloc[-1])
            prev  = float(h["Close"].iloc[-2]) if len(h) > 1 else None
            day_chg = (price - prev) / prev * 100 if prev else None

            def _ret(days: int, _h=h, _p=price) -> float | None:
                cutoff = _h.index[-1] - timedelta(days=days)
                past = _h[_h.index <= cutoff]
                if past.empty:
                    return None
                old = float(past["Close"].iloc[-1])
                return round((_p - old) / old * 100, 2) if old else None

            vol = float(h["Volume"].iloc[-1]) if "Volume" in h.columns and not pd.isna(h["Volume"].iloc[-1]) else None
            result.append({
                "ticker":         ticker,
                "name":           name,
                "asset_class":    asset_class,
                "sub_category":   sub,
                "price":          round(price, 2),
                "day_change_pct": round(day_chg, 2) if day_chg is not None else None,
                "volume":         vol,
                "aum":            None,
                "expense_ratio":  None,
                "return_1y":      _ret(365),
                "return_3y":      _ret(1095),
                "return_5y":      _ret(1825),
            })
        except Exception as e:
            logger.debug("ETF %s compute failed: %s", ticker, e)

    return result


async def get_etf_list() -> list[dict]:
    ck = "etf:list"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    loop = asyncio.get_event_loop()
    etfs = await loop.run_in_executor(_pool, _fetch_etf_list_sync)
    if etfs:
        cache.set(ck, etfs, "etf")
    return etfs


def _fetch_etf_detail_sync(ticker: str) -> dict | None:
    if yf_blocked():
        return None
    try:
        t    = yf.Ticker(ticker, session=YF_SESSION)
        info = t.info or {}
        hist = t.history(period="5y", auto_adjust=True)

        price = info.get("regularMarketPrice") or (
            float(hist["Close"].iloc[-1]) if not hist.empty else None
        )
        prev  = info.get("previousClose") or (
            float(hist["Close"].iloc[-2]) if len(hist) > 1 else None
        )
        day_chg = (price - prev) / prev * 100 if price and prev else None

        chart = [
            {"date": dt.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2)}
            for dt, row in hist.iterrows()
        ] if not hist.empty else []

        def _ret(days: int) -> float | None:
            if hist.empty:
                return None
            now_p = float(hist["Close"].iloc[-1])
            cutoff = hist.index[-1] - timedelta(days=days)
            past = hist[hist.index <= cutoff]
            if past.empty:
                return None
            return round((now_p - float(past["Close"].iloc[-1])) / float(past["Close"].iloc[-1]) * 100, 2)

        return {
            "ticker":       ticker,
            "name":         info.get("shortName") or info.get("longName") or ticker,
            "price":        round(price, 2) if price else None,
            "day_change_pct": round(day_chg, 2) if day_chg is not None else None,
            "aum":          info.get("totalAssets"),
            "expense_ratio": info.get("annualReportExpenseRatio"),
            "fund_family":  info.get("fundFamily", ""),
            "return_1y":    _ret(365),
            "return_3y":    _ret(1095),
            "return_5y":    _ret(1825),
            "chart":        chart,
            "chart_start":  chart[0]["date"] if chart else None,
        }
    except YFRateLimitError:
        yf_on_rate_limit()
        return None
    except Exception as e:
        logger.debug("ETF detail fetch failed %s: %s", ticker, e)
        return None


async def get_etf_detail(ticker: str) -> dict | None:
    ck = f"etf:detail:{ticker}"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_pool, _fetch_etf_detail_sync, ticker)
    if result:
        cache.set(ck, result, "etf")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Highlights
# ─────────────────────────────────────────────────────────────────────────────

# Curated flagship funds — searched by keyword match against the AMFI list
_POPULAR_SEARCHES: list[tuple[str, ...]] = [
    ("sbi",          "bluechip",        "direct", "growth"),
    ("hdfc",         "flexi cap",       "direct", "growth"),
    ("icici",        "bluechip",        "direct", "growth"),
    ("axis",         "bluechip",        "direct", "growth"),
    ("mirae",        "large cap",       "direct", "growth"),
    ("nippon",       "small cap",       "direct", "growth"),
    ("kotak",        "emerging equity", "direct", "growth"),
    ("parag parikh", "flexi cap",       "direct", "growth"),
    ("quant",        "small cap",       "direct", "growth"),
    ("dsp",          "mid cap",         "direct", "growth"),
]


def _pick_popular_codes(all_funds: list[dict]) -> list[int]:
    result: list[int] = []
    for terms in _POPULAR_SEARCHES:
        for f in all_funds:
            n = f["schemeName"].lower()
            if all(t in n for t in terms):
                result.append(f["schemeCode"])
                break
    return result


async def get_mf_highlights(period: str = "1y") -> dict:
    ck = f"mf:highlights:{period}"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    all_funds: list[dict] = cache.get("mf:full_list") or []
    if not all_funds:
        return {"popular": [], "top_gainers": [], "top_losers": [], "most_active": []}

    # 120 evenly-spaced funds for top/bottom ranking
    step    = max(1, len(all_funds) // 120)
    sampled = all_funds[::step][:120]

    pop_codes = _pick_popular_codes(all_funds)
    all_codes = list({f["schemeCode"] for f in sampled} | set(pop_codes))

    # Fetch all chunks in parallel (each chunk shares its own connection pool)
    chunks = [all_codes[i : i + 40] for i in range(0, min(len(all_codes), 200), 40)]
    chunk_results = await asyncio.gather(*[get_mf_returns_batch(ch) for ch in chunks])
    returns: dict[int, dict] = {}
    for r in chunk_results:
        returns.update(r)

    code_to_name = {f["schemeCode"]: f["schemeName"] for f in all_funds}

    def _item(code: int) -> dict | None:
        r = returns.get(code)
        return {"scheme_code": code, "name": code_to_name.get(code, ""), **r} if r else None

    all_items = [x for c in all_codes if (x := _item(c))]
    popular   = [x for c in pop_codes  if (x := _item(c))]

    ret_key  = f"return_{period}"
    with_ret = sorted(
        [x for x in all_items if x.get(ret_key) is not None],
        key=lambda x: x[ret_key], reverse=True,
    )
    most_active = sorted(
        [x for x in all_items if x.get("return_1d") is not None],
        key=lambda x: abs(x["return_1d"]), reverse=True,
    )

    result = {
        "popular":     popular[:8],
        "top_gainers": with_ret[:5],
        "top_losers":  list(reversed(with_ret[-5:])) if len(with_ret) >= 5 else with_ret[::-1],
        "most_active": most_active[:5],
    }
    cache.set(ck, result, "mf_list")   # 24h TTL — highlights are computed from daily NAV data
    return result


async def get_etf_highlights() -> dict:
    ck = "etf:highlights"
    hit = cache.get(ck)
    if hit is not None:
        return hit

    etfs = await get_etf_list()
    if not etfs:
        return {"popular": [], "top_gainers": [], "top_losers": [], "most_active": []}

    with_1y  = [e for e in etfs if e.get("return_1y")       is not None]
    with_day = [e for e in etfs if e.get("day_change_pct")   is not None]
    with_vol = [e for e in etfs if e.get("volume")           is not None]

    result = {
        "popular":     etfs[:8],
        "top_gainers": sorted(with_1y,  key=lambda e: e["return_1y"],       reverse=True)[:5],
        "top_losers":  sorted(with_1y,  key=lambda e: e["return_1y"])[:5],
        "most_active": sorted(with_vol or with_day,
                              key=lambda e: e.get("volume") or abs(e.get("day_change_pct", 0)),
                              reverse=True)[:5],
    }
    cache.set(ck, result, "etf")   # 10 min TTL
    return result
