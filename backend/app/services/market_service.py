"""
market_service.py — market overview: indices, gainers, losers, cap segments.

Data priority per data type:
  gainers / losers / high_volume : IndianAPI /trending + /NSE_most_active  (1 fast call each)
  nifty50 / nifty100 / buckets   : yfinance batch                           (1 call, 175 tickers)
  indices bar                    : yfinance history(period="2d")              (5 parallel calls)
  IPO / commodities / 52wk / announcements : IndianAPI dedicated endpoints
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import requests as _requests
import yfinance as yf
from app.core.yf_session import YF_SESSION

from app.core.cache import cache
from app.services.stock_service import _clean, _TTL

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=32)
_cache = _TTL(ttl=720)   # 12-min TTL — background refresh runs every 10 min
_idx_cache = _TTL(ttl=60)  # 60-second cache for indices-only endpoint

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


def _fetch_quote_sync(ticker: str) -> dict | None:
    try:
        info = yf.Ticker(ticker).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev = info.get("previousClose")
        if not price:
            return None
        chg = (price - prev) / prev * 100 if prev else 0
        mc = info.get("marketCap")
        return _clean({
            "ticker": ticker,
            "name": info.get("shortName") or ticker.replace(".NS", ""),
            "price": price,
            "change_pct": round(chg, 2),
            "market_cap": mc,
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_to_equity": info.get("debtToEquity"),
            "dividend_yield": info.get("dividendYield"),
            "volume": info.get("volume"),
            "avg_volume": info.get("averageVolume"),
            "sector": info.get("sector"),
            "website": info.get("website"),
            "cap_type": (
                "large" if mc and mc >= _LARGE_CAP
                else "mid" if mc and mc >= _MID_CAP
                else "small"
            ),
        })
    except Exception as e:
        logger.debug("mover fetch failed %s: %s", ticker, e)
        return None


def _safe_info(ticker: str) -> dict:
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def _batch_overview_sync(tickers: list[str]) -> list[dict]:
    """
    Batch-download prices via yf.download() (one HTTP request, rate-limit safe),
    then enrich each valid ticker with .info in a capped thread pool.
    Cap type is read from _CAP_TYPE_MAP (predefined), so misclassification due to
    missing marketCap values never happens.
    """
    from app.core.yf_session import yf_blocked, yf_on_rate_limit
    from yfinance.exceptions import YFRateLimitError
    import pandas as pd

    if yf_blocked():
        return []

    # Step 1: Batch price + volume download — far more reliable than 130 individual .info calls
    try:
        raw = yf.download(
            tickers, period="5d", auto_adjust=True,
            group_by="ticker", progress=False, threads=True,
            session=YF_SESSION,
        )
    except YFRateLimitError:
        yf_on_rate_limit()
        return []
    except Exception as exc:
        logger.warning("batch overview download failed (%s); falling back to individual fetch", exc)
        return [r for r in (_fetch_quote_sync(t) for t in tickers) if r]

    multi = isinstance(raw.columns, pd.MultiIndex)

    # Parse price + volume per ticker
    price_map: dict[str, tuple[float, float | None, int | None]] = {}
    for t in tickers:
        try:
            closes = raw[t]["Close"].dropna() if multi else raw["Close"].dropna()
            vols   = raw[t]["Volume"].dropna() if multi else raw["Volume"].dropna()
            if closes.empty:
                continue
            price = float(closes.iloc[-1])
            prev  = float(closes.iloc[-2]) if len(closes) >= 2 else None
            vol   = int(vols.iloc[-1]) if not vols.empty else None
            price_map[t] = (price, prev, vol)
        except Exception:
            pass

    if not price_map:
        return []

    # Step 2: Fetch .info for all tickers that have a valid price (reduced concurrency)
    valid = list(price_map.keys())
    with ThreadPoolExecutor(max_workers=16) as ex:
        info_map: dict[str, dict] = dict(zip(valid, ex.map(_safe_info, valid)))

    results: list[dict] = []
    for ticker in valid:
        price, prev, vol = price_map[ticker]
        chg  = round((price - prev) / prev * 100, 2) if prev else 0.0
        info = info_map.get(ticker, {})

        mc      = info.get("marketCap")
        name    = info.get("shortName") or ticker.replace(".NS", "").replace(".BO", "")
        pe      = info.get("trailingPE")
        avg_vol = info.get("averageVolume")
        website = info.get("website")

        results.append(_clean({
            "ticker":     ticker,
            "name":       name,
            "price":      price,
            "change_pct": chg,
            "market_cap": mc,
            "pe_ratio":   pe,
            "volume":     vol,
            "avg_volume": avg_vol,
            "website":    website,
            "cap_type":   _CAP_TYPE_MAP.get(ticker, "small"),
        }))

    return results


def _fetch_sector_quote_sync(ticker: str) -> dict | None:
    """Extended quote fetch for sector/peer pages — includes QoQ revenue growth + net profit."""
    from app.core.yf_session import yf_blocked, yf_on_rate_limit
    from yfinance.exceptions import YFRateLimitError
    if yf_blocked():
        return None
    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev  = info.get("previousClose")
        if not price:
            return None
        chg = (price - prev) / prev * 100 if prev else 0
        mc  = info.get("marketCap")

        # Revenue growth QoQ — computed from last 2 quarters of income stmt
        rev_qoq: float | None = None
        net_income = info.get("netIncomeToCommon")   # TTM net income (INR)
        try:
            qf = t.quarterly_income_stmt
            if qf is not None and not qf.empty:
                rev_rows = [r for r in qf.index if "Total Revenue" in str(r) or "Operating Revenue" in str(r)]
                if rev_rows:
                    revs = qf.loc[rev_rows[0]].dropna().tolist()
                    if len(revs) >= 2 and revs[1]:
                        rev_qoq = round((revs[0] / revs[1] - 1) * 100, 2)
                # Net income from quarterly if not in info
                if net_income is None:
                    ni_rows = [r for r in qf.index if "Net Income" in str(r)]
                    if ni_rows:
                        ni_vals = qf.loc[ni_rows[0]].dropna().tolist()
                        net_income = sum(ni_vals[:4]) if len(ni_vals) >= 4 else ni_vals[0] if ni_vals else None
        except Exception:
            pass

        return _clean({
            "ticker":             ticker,
            "name":               info.get("shortName") or ticker.replace(".NS", ""),
            "price":              price,
            "change_pct":         round(chg, 2),
            "market_cap":         mc,
            "pe_ratio":           info.get("trailingPE"),
            "pb_ratio":           info.get("priceToBook"),
            "roe":                info.get("returnOnEquity"),
            "revenue_growth":     info.get("revenueGrowth"),       # YoY
            "revenue_growth_qoq": rev_qoq,                         # QoQ
            "profit_margin":      info.get("profitMargins"),
            "net_income":         net_income,                       # TTM (INR)
            "debt_to_equity":     info.get("debtToEquity"),
            "dividend_yield":     info.get("dividendYield"),
            "volume":             info.get("volume"),
            "sector":             info.get("sector"),
            "website":            info.get("website"),
            "cap_type": (
                "large" if mc and mc >= _LARGE_CAP
                else "mid"   if mc and mc >= _MID_CAP
                else "small"
            ),
        })
    except YFRateLimitError:
        yf_on_rate_limit()
        return None
    except Exception as e:
        logger.debug("sector fetch failed %s: %s", ticker, e)
        return None


def _fetch_index_sync(name: str, symbol: str) -> dict | None:
    try:
        # history(period="2d") is ~10× faster than .info — returns OHLCV only
        hist = yf.Ticker(symbol, session=YF_SESSION).history(period="2d")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
        prev  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
        chg_pts = price - prev
        chg_pct = chg_pts / prev * 100 if prev else 0
        return {
            "name":       name,
            "symbol":     symbol,
            "price":      round(price, 2),
            "change_pts": round(chg_pts, 2),
            "change_pct": round(chg_pct, 2),
        }
    except Exception as e:
        logger.debug("index fetch failed %s: %s", symbol, e)
        return None


def _batch_returns_sync(tickers: list[str]) -> dict[str, dict]:
    """Batch-download 5Y history for all tickers; return 1Y/3Y/5Y price returns."""
    import pandas as pd
    try:
        data = yf.download(
            tickers, period="5y", auto_adjust=True,
            group_by="ticker", progress=False, threads=True,
            session=YF_SESSION,
        )
        out: dict[str, dict] = {}
        for t in tickers:
            try:
                # MultiIndex columns when >1 ticker; flat when exactly 1
                if isinstance(data.columns, pd.MultiIndex):
                    closes = data[t]["Close"].dropna()
                else:
                    closes = data["Close"].dropna()
                n = len(closes)
                if n == 0:
                    continue
                curr = float(closes.iloc[-1])
                def _ret(days: int) -> float | None:
                    if n < days * 0.6:
                        return None
                    base = float(closes.iloc[max(0, n - days)])
                    return round((curr / base - 1) * 100, 2) if base else None
                out[t] = {
                    "return_1y": _ret(252),
                    "return_3y": _ret(756),
                    "return_5y": _ret(1260),
                }
            except Exception:
                pass
        return out
    except Exception:
        return {}


async def get_sector_stocks(sector: str) -> dict:
    """Return all tracked stocks for a given sector with live quotes + price returns."""
    from app.services.peer_service import _SECTOR_PEERS
    from app.core.yf_session import yf_blocked

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

    # When yfinance is blocked return stub list so the picker is still usable
    if yf_blocked():
        stub_stocks = [
            {"ticker": t, "name": t.replace(".NS", "").replace(".BO", ""),
             "price": None, "change_pct": None, "market_cap": None}
            for t in tickers
        ]
        return {"sector": matched_key or sector, "stocks": stub_stocks, "stats": {}, "partial": True}

    loop = asyncio.get_event_loop()

    # Fetch extended quotes (with QoQ revenue + net income) + batch history in parallel
    quote_results, returns = await asyncio.gather(
        asyncio.gather(*[loop.run_in_executor(_pool, _fetch_sector_quote_sync, t) for t in tickers]),
        loop.run_in_executor(_pool, _batch_returns_sync, tickers),
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


async def get_indices(_force: bool = False) -> list[dict]:
    """
    Fetch the 5 headline index prices from NSE's official API (no yfinance).
    Cached 60 s. Pass _force=True to bypass cache (used by HomeRefreshTask).
    """
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

    if indices:
        _idx_cache.set("indices", indices)
    return indices




_OVERVIEW_REDIS_KEY = "market:overview"


async def get_market_overview(_force: bool = False) -> dict:
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

    # ── Run all 3 data sources in parallel ────────────────────────────────────
    # IndianAPI: gainers/losers + high-volume  (2 fast calls, no Sugra credits)
    # yfinance:  full 175-ticker batch          (1 batch call for nifty buckets)
    # Sugra:     indices bar only              (5 symbols, minimal credits)
    # Primary: NSE direct API for gainers/losers (no yfinance, no API key)
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

    logger.info("Market overview: NSE gainers=%d losers=%d", len(gainers), len(losers))

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
    else:
        logger.warning("Market overview: NSE returned no data — keeping existing cache")
    return _cache.get("market_overview") or result


# ── Curated ETF list ──────────────────────────────────────────────────────────
_ETFS = [
    {"ticker": "NIFTYBEES.NS",  "name": "Nifty 50 BeES",       "category": "Index"},
    {"ticker": "JUNIORBEES.NS", "name": "Nifty Next 50 BeES",  "category": "Index"},
    {"ticker": "BANKBEES.NS",   "name": "Bank Nifty BeES",      "category": "Sector"},
    {"ticker": "ITBEES.NS",     "name": "Nifty IT BeES",        "category": "Sector"},
    {"ticker": "PHARMABEES.NS", "name": "Pharma BeES",          "category": "Sector"},
    {"ticker": "GOLDBEES.NS",   "name": "Gold BeES",            "category": "Commodity"},
    {"ticker": "SILVERBEES.NS", "name": "Silver BeES",          "category": "Commodity"},
    {"ticker": "ICICIB22.NS",   "name": "Bharat 22 ETF",        "category": "Index"},
    {"ticker": "BSLNIFTY.NS",   "name": "ABSL Nifty 50 ETF",    "category": "Index"},
    {"ticker": "UTINIFTETF.NS", "name": "UTI Nifty 50 ETF",     "category": "Index"},
    {"ticker": "MOM100.NS",     "name": "Motilal Midcap 100",   "category": "Index"},
]


def _fetch_etf_sync(etf: dict) -> dict | None:
    try:
        info = yf.Ticker(etf["ticker"]).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("navPrice")
        prev  = info.get("previousClose")
        if not price:
            return None
        chg = (price - prev) / prev * 100 if prev else 0
        return _clean({
            "ticker":   etf["ticker"],
            "name":     etf["name"],
            "category": etf["category"],
            "price":    price,
            "change_pct": round(chg, 2),
        })
    except Exception:
        return None


async def get_etf_data() -> list:
    cached = _cache.get("etfs")
    if cached is not None:
        return cached

    loop    = asyncio.get_event_loop()
    tickers = [e["ticker"] for e in _ETFS]

    quote_results, returns = await asyncio.gather(
        asyncio.gather(*[loop.run_in_executor(_pool, _fetch_etf_sync, e) for e in _ETFS]),
        loop.run_in_executor(_pool, _batch_returns_sync, tickers),
    )

    out = []
    for q in quote_results:
        if q is None:
            continue
        ret = returns.get(q["ticker"], {})
        out.append({**q,
            "return_1y": ret.get("return_1y"),
            "return_3y": ret.get("return_3y"),
            "return_5y": ret.get("return_5y"),
        })

    _cache.set("etfs", out)
    return out


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
