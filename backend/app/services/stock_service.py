"""
stock_service.py — Indian-market (NSE/BSE) stock data via yfinance.

Every ticker is normalised to an NSE (.NS) or BSE (.BO) symbol.
Search returns ONLY Indian-listed results.
A small in-process TTL cache reduces duplicate Yahoo calls.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import yfinance as yf

from app.core.cache import cache
from app.core.yf_session import YF_SESSION, yf_blocked, yf_on_rate_limit
from yfinance.exceptions import YFRateLimitError

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=8)


# ── Legacy _TTL kept for any external imports ─────────────────────────────────
class _TTL:
    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        self._d: dict[str, tuple[float, object]] = {}

    def get(self, k: str):
        v = self._d.get(k)
        if v and time.time() - v[0] < self.ttl:
            return v[1]
        return None

    def set(self, k: str, val):
        self._d[k] = (time.time(), val)


# ── helpers ───────────────────────────────────────────────────────────────────

def normalise_ticker(ticker: str) -> str:
    """Ensure an Indian suffix. Bare symbols default to NSE (.NS)."""
    t = ticker.strip().upper()
    if t.startswith("^"):          # index symbol — pass through unchanged
        return t
    if t.endswith(".NS") or t.endswith(".BO"):
        return t
    return f"{t}.NS"


def _clean(obj):
    """Recursively replace NaN/inf with None so JSON is valid."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        return None if (np.isnan(obj) or np.isinf(obj)) else obj
    return obj


async def _run(fn, *args):
    return await asyncio.get_event_loop().run_in_executor(_pool, fn, *args)


# ── local NSE index for instant prefix matching ───────────────────────────────
# Covers Nifty 50, Nifty Next 50, and popular mid/small caps.
# Ticker keys are bare (no .NS suffix); values are display names.
_NSE_INDEX: dict[str, str] = {
    # Nifty 50
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "HDFCBANK": "HDFC Bank",
    "INFY": "Infosys",
    "ICICIBANK": "ICICI Bank",
    "HINDUNILVR": "Hindustan Unilever",
    "ITC": "ITC",
    "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel",
    "BAJFINANCE": "Bajaj Finance",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "LT": "Larsen & Toubro",
    "AXISBANK": "Axis Bank",
    "ASIANPAINT": "Asian Paints",
    "MARUTI": "Maruti Suzuki India",
    "SUNPHARMA": "Sun Pharmaceutical Industries",
    "TITAN": "Titan Company",
    "NESTLEIND": "Nestle India",
    "WIPRO": "Wipro",
    "ULTRACEMCO": "UltraTech Cement",
    "POWERGRID": "Power Grid Corporation",
    "NTPC": "NTPC",
    "ADANIENT": "Adani Enterprises",
    "ADANIPORTS": "Adani Ports & SEZ",
    "ONGC": "Oil & Natural Gas Corporation",
    "TECHM": "Tech Mahindra",
    "HCLTECH": "HCL Technologies",
    "BAJAJFINSV": "Bajaj Finserv",
    "TATAMOTORS": "Tata Motors",
    "TATASTEEL": "Tata Steel",
    "JSWSTEEL": "JSW Steel",
    "COALINDIA": "Coal India",
    "DRREDDY": "Dr. Reddy's Laboratories",
    "CIPLA": "Cipla",
    "DIVISLAB": "Divi's Laboratories",
    "EICHERMOT": "Eicher Motors",
    "BPCL": "Bharat Petroleum Corporation",
    "HEROMOTOCO": "Hero MotoCorp",
    "BRITANNIA": "Britannia Industries",
    "GRASIM": "Grasim Industries",
    "APOLLOHOSP": "Apollo Hospitals Enterprise",
    "SBILIFE": "SBI Life Insurance",
    "HDFCLIFE": "HDFC Life Insurance",
    "TATACONSUM": "Tata Consumer Products",
    "INDUSINDBK": "IndusInd Bank",
    "M&M": "Mahindra & Mahindra",
    "BAJAJ-AUTO": "Bajaj Auto",
    "HINDALCO": "Hindalco Industries",
    "SHREECEM": "Shree Cement",
    # Nifty Next 50 & popular
    "ETERNAL": "Eternal (Zomato)",
    "DMART": "Avenue Supermarts (DMart)",
    "IRCTC": "Indian Railway Catering & Tourism",
    "HAL": "Hindustan Aeronautics",
    "BEL": "Bharat Electronics",
    "BHEL": "Bharat Heavy Electricals",
    "DABUR": "Dabur India",
    "MARICO": "Marico",
    "GODREJCP": "Godrej Consumer Products",
    "PIDILITIND": "Pidilite Industries",
    "BERGEPAINT": "Berger Paints India",
    "KANSAINER": "Kansai Nerolac Paints",
    "AMBUJACEM": "Ambuja Cements",
    "ACC": "ACC",
    "INDIGO": "IndiGo (InterGlobe Aviation)",
    "IRFC": "Indian Railway Finance Corporation",
    "RECLTD": "REC",
    "PFC": "Power Finance Corporation",
    "NHPC": "NHPC",
    "VEDL": "Vedanta",
    "HINDZINC": "Hindustan Zinc",
    "NATIONALUM": "National Aluminium Company",
    "SAIL": "Steel Authority of India",
    "NMDC": "NMDC",
    "GAIL": "GAIL India",
    "IOC": "Indian Oil Corporation",
    "HPCL": "Hindustan Petroleum Corporation",
    "MRF": "MRF",
    "APOLLOTYRE": "Apollo Tyres",
    "BALKRISIND": "Balkrishna Industries",
    "CEAT": "CEAT",
    "BOSCHLTD": "Bosch",
    "BHARATFORG": "Bharat Forge",
    "MPHASIS": "Mphasis",
    "PERSISTENT": "Persistent Systems",
    "COFORGE": "Coforge",
    "LTIMINDTREE": "LTIMindtree",
    "LTTS": "L&T Technology Services",
    "KPITTECH": "KPIT Technologies",
    "TATAELXSI": "Tata Elxsi",
    "TATAPOWER": "Tata Power Company",
    "ADANIGREEN": "Adani Green Energy",
    "NAUKRI": "Info Edge India (Naukri)",
    "POLICYBZR": "PB Fintech (Policybazaar)",
    "ICICIGI": "ICICI Lombard General Insurance",
    "CHOLAFIN": "Cholamandalam Investment & Finance",
    "MUTHOOTFIN": "Muthoot Finance",
    "SHRIRAMFIN": "Shriram Finance",
    "CAMS": "Computer Age Management Services",
    "CDSL": "Central Depository Services",
    "MCX": "Multi Commodity Exchange",
    "BANKBARODA": "Bank of Baroda",
    "PNB": "Punjab National Bank",
    "CANBK": "Canara Bank",
    "UNIONBANK": "Union Bank of India",
    "IDFCFIRSTB": "IDFC First Bank",
    "FEDERALBNK": "Federal Bank",
    "BANDHANBNK": "Bandhan Bank",
    "YESBANK": "Yes Bank",
    "AUBANK": "AU Small Finance Bank",
    "INDIANB": "Indian Bank",
    "LUPIN": "Lupin",
    "AUROPHARMA": "Aurobindo Pharma",
    "ALKEM": "Alkem Laboratories",
    "TORNTPHARM": "Torrent Pharmaceuticals",
    "BIOCON": "Biocon",
    "LALPATHLAB": "Dr. Lal PathLabs",
    "METROPOLIS": "Metropolis Healthcare",
    "FORTIS": "Fortis Healthcare",
    "MAXHEALTH": "Max Healthcare Institute",
    "TRENT": "Trent",
    "PAGEIND": "Page Industries (Jockey)",
    "ABFRL": "Aditya Birla Fashion and Retail",
    "RAYMOND": "Raymond",
    "PVRINOX": "PVR INOX",
    "ZEEL": "Zee Entertainment Enterprises",
    "SUNTV": "Sun TV Network",
    "DLF": "DLF",
    "OBEROIRLTY": "Oberoi Realty",
    "GODREJPROP": "Godrej Properties",
    "PHOENIXLTD": "Phoenix Mills",
    "RELAXO": "Relaxo Footwears",
    "BATA": "Bata India",
    "MGL": "Mahanagar Gas",
    "IGL": "Indraprastha Gas",
    "GUJGASLTD": "Gujarat Gas",
    "TORNTPOWER": "Torrent Power",
    "CESC": "CESC",
    "TATACOMM": "Tata Communications",
    "IDEA": "Vodafone Idea",
    "SPICEJET": "SpiceJet",
    "REDINGTON": "Redington",
    "AAVAS": "Aavas Financiers",
    "CANFINHOME": "Can Fin Homes",
    "HOMEFIRST": "Home First Finance",
    "LICHSGFIN": "LIC Housing Finance",
    "PNBHOUSING": "PNB Housing Finance",
    "MANAPPURAM": "Manappuram Finance",
    "SJVN": "SJVN",
    "MOTHERSON": "Samvardhana Motherson",
    "AARTIIND": "Aarti Industries",
    "NYKAA": "FSN E-Commerce Ventures (Nykaa)",
    "PAYTM": "One97 Communications (Paytm)",
    "BSE": "BSE",
    "HAPPSTMNDS": "Happiest Minds Technologies",
    "RBLBANK": "RBL Bank",
    "PRESTIGE": "Prestige Estates Projects",
    "BRIGADE": "Brigade Enterprises",
    "SOBHA": "Sobha",
    "VMART": "V-Mart Retail",
    "CAMPUS": "Campus Activewear",
    "NH": "Narayana Hrudayalaya",
    "PGHH": "Procter & Gamble Hygiene",
    "ABBOTINDIA": "Abbott India",
    "PFIZER": "Pfizer India",
    "GLAXO": "GlaxoSmithKline Pharmaceuticals",
    "NETWORK18": "Network18 Media & Investments",
    "JSWENERGY": "JSW Energy",
    "INDIGOPNTS": "Indigo Paints",
    "LICI": "Life Insurance Corporation of India",
    "RVNL": "Rail Vikas Nigam",
    "TIINDIA": "Tube Investments of India",
    "SOLARINDS": "Solar Industries India",
    "GRINDWELL": "Grindwell Norton",
    "3MINDIA": "3M India",
    "HONAUT": "Honeywell Automation India",
    "ABB": "ABB India",
    "SIEMENS": "Siemens India",
    "CUMMINSIND": "Cummins India",
    "THERMAX": "Thermax",
    "SCHAEFFLER": "Schaeffler India",
    "SKFINDIA": "SKF India",
    "TIMKEN": "Timken India",
    "ASTRAL": "Astral",
    "SUPREMEIND": "Supreme Industries",
    "FINPIPE": "Finolex Industries",
    "APLAPOLLO": "APL Apollo Tubes",
    "JINDALSAW": "Jindal Saw",
    "JINDALSTEL": "Jindal Steel & Power",
    "JINDALPOLY": "Jindal Poly Films",
}

# Pre-build a sorted list for faster prefix matching
_NSE_LIST: list[tuple[str, str]] = sorted(_NSE_INDEX.items())


def _local_search(query: str) -> list[dict]:
    """Instant prefix match against the local NSE index. O(n) but n≈200."""
    q_up = query.upper()
    q_lo = query.lower()
    ticker_hits: list[dict] = []
    name_hits: list[dict] = []

    for ticker, name in _NSE_LIST:
        sym = f"{ticker}.NS"
        entry = {"symbol": sym, "name": name, "exchange": "NSE"}
        name_lo = name.lower()

        if ticker.startswith(q_up):
            ticker_hits.append(entry)
        elif name_lo.startswith(q_lo):
            name_hits.append(entry)
        elif len(query) >= 3 and q_lo in name_lo:
            # For 3+ char queries, also do substring match on name
            name_hits.append(entry)

    # Ticker prefix matches come first, then name matches
    return (ticker_hits + name_hits)[:8]


# ── search (Indian only) ──────────────────────────────────────────────────────

def _search_sync(query: str) -> list[dict]:
    """Local index first (instant), then Yahoo Finance for unknowns."""
    local = _local_search(query)
    local_syms = {r["symbol"] for r in local}

    # If local index already gives 5+ results, skip Yahoo call (fast path)
    if len(local) >= 5:
        return local[:8]

    # Supplement with Yahoo for less common tickers
    yahoo: list[dict] = []
    seen = set(local_syms)
    try:
        searches: list[dict] = []
        try:
            searches += yf.Search(query, max_results=12).quotes
        except Exception:
            pass
        try:
            searches += yf.Search(f"{query}.NS", max_results=6).quotes
        except Exception:
            pass

        for s in searches:
            sym = (s.get("symbol") or "").upper()
            if sym and sym.endswith(".NS") and sym not in seen:
                yahoo.append({
                    "symbol": sym,
                    "name": s.get("shortname") or s.get("longname") or sym,
                    "exchange": "NSE",
                })
                seen.add(sym)
        for s in searches:
            sym = (s.get("symbol") or "").upper()
            if sym and sym.endswith(".BO") and sym not in seen:
                yahoo.append({
                    "symbol": sym,
                    "name": s.get("shortname") or s.get("longname") or sym,
                    "exchange": "BSE",
                })
                seen.add(sym)
    except Exception as e:
        logger.warning("yahoo search failed for %s: %s", query, e)

    return (local + yahoo)[:8]


async def search_indian(query: str) -> list[dict]:
    if len(query.strip()) < 2:
        return []
    key = f"search:{query.lower()}"
    if (c := cache.get(key)) is not None:
        return c
    res = await _run(_search_sync, query)
    cache.set(key, res, "search")
    return res


# ── quote / fundamentals ──────────────────────────────────────────────────────

def _quote_sync(ticker: str) -> dict:
    t = normalise_ticker(ticker)
    if yf_blocked():
        return {"ticker": t, "error": "yfinance rate-limited — try again later"}
    try:
        stock = yf.Ticker(t)
        try:
            info = stock.info or {}
        except (KeyError, Exception):
            # yfinance raises KeyError('exchangeTimezoneName') on some 404 tickers
            info = {}
        if not info.get("currentPrice") and not info.get("regularMarketPrice"):
            # fast_info fallback
            fi = stock.fast_info
            price = getattr(fi, "last_price", None)
            if not price:
                return {"ticker": t, "error": "No data for this symbol"}
            return _clean({
                "ticker": t,
                "company_name": t.replace(".NS", "").replace(".BO", ""),
                "current_price": price,
                "previous_close": getattr(fi, "previous_close", price),
                "currency": "INR",
                "exchange": "NSE" if t.endswith(".NS") else "BSE",
            })

        base = _clean({
            "ticker": t,
            "company_name": info.get("longName") or info.get("shortName") or t,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "open": info.get("open"),
            "day_high": info.get("dayHigh"),
            "day_low": info.get("dayLow"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "eps": info.get("trailingEps"),
            "book_value": info.get("bookValue"),
            "roe": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "volume": info.get("volume"),
            "avg_volume": info.get("averageVolume"),
            "float_shares": info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "held_by_insiders_pct": info.get("heldPercentInsiders"),
            "held_by_institutions_pct": info.get("heldPercentInstitutions"),
            "shares_short": info.get("sharesShort"),
            "short_ratio": info.get("shortRatio"),
            "currency": info.get("currency", "INR"),
            "exchange": "NSE" if t.endswith(".NS") else "BSE",
            "website": info.get("website"),
            "summary": (info.get("longBusinessSummary") or "")[:600],
            "officers": [
                {"name": o.get("name"), "title": o.get("title")}
                for o in (info.get("companyOfficers") or [])[:6]
                if o.get("name")
            ],
        })

        # Institutional & insider ownership (best-effort — not always available for Indian stocks)
        try:
            inst_df = stock.institutional_holders
            if inst_df is not None and not inst_df.empty:
                base["institutional_holders"] = [
                    {
                        "holder": str(row.get("Holder", "")),
                        "shares": int(row["Shares"]) if pd.notna(row.get("Shares")) else None,
                        "pct_out": round(float(row["% Out"]) * 100, 2) if pd.notna(row.get("% Out")) else None,
                        "date_reported": str(row.get("Date Reported", ""))[:10],
                    }
                    for _, row in inst_df.head(10).iterrows()
                ]
        except Exception:
            pass

        try:
            mut_df = stock.mutualfund_holders
            if mut_df is not None and not mut_df.empty:
                base["mutualfund_holders"] = [
                    {
                        "holder": str(row.get("Holder", "")),
                        "shares": int(row["Shares"]) if pd.notna(row.get("Shares")) else None,
                        "pct_out": round(float(row["% Out"]) * 100, 2) if pd.notna(row.get("% Out")) else None,
                        "date_reported": str(row.get("Date Reported", ""))[:10],
                    }
                    for _, row in mut_df.head(10).iterrows()
                ]
        except Exception:
            pass

        try:
            ins_df = stock.insider_transactions
            if ins_df is not None and not ins_df.empty:
                base["insider_transactions"] = [
                    {
                        "insider": str(row.get("Insider Trading", "")),
                        "transaction": str(row.get("Transaction", "")),
                        "shares": int(row["#Shares"]) if pd.notna(row.get("#Shares")) else None,
                        "value": float(row["Value"]) if pd.notna(row.get("Value")) else None,
                        "date": str(row.get("Start Date", ""))[:10],
                    }
                    for _, row in ins_df.head(10).iterrows()
                ]
        except Exception:
            pass

        return base
    except YFRateLimitError:
        yf_on_rate_limit()
        return {"ticker": t, "error": "yfinance rate-limited — try again later"}
    except Exception as e:
        logger.warning("quote fallback yfinance %s: %s", t, e)
        return {"ticker": t, "error": str(e)}


async def _indianapi_price_fields(ticker: str) -> dict:
    """Fetch live price + fundamentals from IndianAPI. Returns {} on failure."""
    try:
        from app.services.indianapi_service import get_stock
        bare = ticker.replace(".NS", "").replace(".BO", "")
        data = await get_stock(bare)
        if not data or not data.get("current_price"):
            return {}
        return {k: v for k, v in data.items() if v is not None}
    except Exception:
        return {}


async def get_quote(ticker: str) -> dict:
    t = normalise_ticker(ticker)
    ck = f"quote:{t}"
    if (c := cache.get(ck)) is not None:
        return c

    # Tier 1 (primary): yfinance — comprehensive fundamentals, most reliable
    try:
        yf_res = await _run(_quote_sync, ticker)
    except Exception as exc:
        yf_res = {"ticker": t, "error": str(exc)}

    if "error" not in yf_res:
        res = yf_res
    else:
        # Tier 2 (fallback): IndianAPI — when yfinance fails (rate-limit, delisted, etc.)
        logger.info("get_quote: yfinance failed for %s, trying IndianAPI: %s", t, yf_res.get("error"))
        india_fields = await _indianapi_price_fields(t)
        if india_fields and india_fields.get("current_price"):
            res = {"ticker": t, **india_fields}
        else:
            res = yf_res

    if "error" not in res:
        res["fetched_at"] = int(time.time())
        cache.set(ck, res, "prices")
    return res


# ── price history + technicals ────────────────────────────────────────────────

def _history_sync(ticker: str, period: str) -> dict:
    t = normalise_ticker(ticker)
    if yf_blocked():
        return {"ticker": t, "error": "yfinance rate-limited — try again later"}
    try:
        hist = yf.Ticker(t, session=YF_SESSION).history(period=period)
        if hist.empty:
            return {"ticker": t, "error": "No price history"}

        hist["MA20"]  = hist["Close"].rolling(20).mean()
        hist["MA50"]  = hist["Close"].rolling(50).mean()
        hist["MA200"] = hist["Close"].rolling(200).mean()
        hist["RSI"]   = _rsi(hist["Close"])

        first, last = hist["Close"].iloc[0], hist["Close"].iloc[-1]
        pct = (last - first) / first * 100 if first else 0
        daily = hist["Close"].pct_change()
        vol = float(daily.std() * (252 ** 0.5) * 100) if len(daily) > 1 else 0

        candles = []
        for idx, row in hist.iterrows():
            candles.append({
                "date": idx.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 2),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                "ma20":  round(float(row["MA20"]),  2) if not pd.isna(row["MA20"])  else None,
                "ma50":  round(float(row["MA50"]),  2) if not pd.isna(row["MA50"])  else None,
                "ma200": round(float(row["MA200"]), 2) if not pd.isna(row["MA200"]) else None,
                "rsi": round(float(row["RSI"]), 1) if not pd.isna(row["RSI"]) else None,
            })

        return _clean({
            "ticker": t,
            "period": period,
            "first_price": round(float(first), 2),
            "last_price": round(float(last), 2),
            "pct_change": round(float(pct), 2),
            "volatility_pct": round(vol, 2),
            "latest_rsi": candles[-1]["rsi"] if candles else None,
            "candles": candles,
        })
    except YFRateLimitError:
        yf_on_rate_limit()
        return {"ticker": t, "error": "yfinance rate-limited — try again later"}
    except Exception as e:
        logger.warning("history yfinance fallback %s: %s", t, e)
        return {"ticker": t, "error": str(e)}


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))




async def _history_from_indianapi(ticker: str, period: str) -> dict | None:
    """Fetch OHLCV from IndianAPI /historical_data and reshape to Aegis candles format."""
    try:
        from app.services.indianapi_service import get_historical_data
        bare = ticker.replace(".NS", "").replace(".BO", "")
        raw = await get_historical_data(bare, period)
        if not raw:
            return None
        # IndianAPI returns {"datasets": [{"label": ..., "data": [...]}], "labels": [...dates]}
        labels = raw.get("labels") or []
        datasets = raw.get("datasets") or []
        close_data = next((d["data"] for d in datasets if "close" in d.get("label", "").lower()), None)
        if not close_data or len(close_data) != len(labels):
            return None

        closes = pd.Series(close_data, dtype=float)
        ma20  = closes.rolling(20).mean()
        ma50  = closes.rolling(50).mean()
        ma200 = closes.rolling(200).mean()
        rsi   = _rsi(closes)

        candles = []
        for i, (date, close) in enumerate(zip(labels, close_data)):
            if close is None:
                continue
            candles.append({
                "date":  date,
                "close": round(float(close), 2),
                "open":  round(float(close), 2),
                "high":  round(float(close), 2),
                "low":   round(float(close), 2),
                "volume": 0,
                "ma20":  round(float(ma20.iloc[i]),  2) if not pd.isna(ma20.iloc[i])  else None,
                "ma50":  round(float(ma50.iloc[i]),  2) if not pd.isna(ma50.iloc[i])  else None,
                "ma200": round(float(ma200.iloc[i]), 2) if not pd.isna(ma200.iloc[i]) else None,
                "rsi":   round(float(rsi.iloc[i]),   1) if not pd.isna(rsi.iloc[i])   else None,
            })

        if len(candles) < 5:
            return None

        first, last = candles[0]["close"], candles[-1]["close"]
        pct = (last - first) / first * 100 if first else 0

        return _clean({
            "ticker":        ticker,
            "period":        period,
            "first_price":   round(first, 2),
            "last_price":    round(last, 2),
            "pct_change":    round(pct, 2),
            "volatility_pct": 0,
            "latest_rsi":    candles[-1]["rsi"],
            "candles":       candles,
        })
    except Exception as e:
        logger.debug("IndianAPI history failed for %s: %s", ticker, e)
        return None




async def get_history(ticker: str, period: str = "6mo") -> dict:
    t = normalise_ticker(ticker)
    ck = f"hist:{t}:{period}"
    if (c := cache.get(ck)) is not None:
        return c

    # Tier 1 (primary): yfinance — most complete, handles all periods
    res = await _run(_history_sync, ticker, period)
    if res and "error" in res:
        res = None

    # Tier 2 (fallback): IndianAPI historical_data — when yfinance fails
    if res is None:
        logger.info("get_history: yfinance failed for %s/%s, trying IndianAPI", t, period)
        res = await _history_from_indianapi(t, period)

    if res is None:
        res = {"ticker": t, "period": period, "error": "No history data available"}

    if "error" not in res:
        cache.set(ck, res, "history")
    return res


# ── ratio signals ─────────────────────────────────────────────────────────────

def ratio_signals(q: dict) -> list[dict]:
    """Return enriched signal objects with type, severity, title, detail, and metric."""
    signals: list[dict] = []

    def add(title: str, detail: str, kind: str, metric: str, severity: str = "medium"):
        signals.append({"title": title, "detail": detail, "type": kind, "metric": metric, "severity": severity})

    pe = q.get("pe_ratio")
    if isinstance(pe, (int, float)):
        if pe < 10:
            add(f"Deep Value P/E: {pe:.1f}×", "Trading well below Nifty average (~22×). Could signal undervaluation or underlying risk — check earnings quality.", "positive", "P/E Ratio", "high")
        elif pe < 15:
            add(f"Low P/E: {pe:.1f}×", "Below Nifty average of ~22×. May be undervalued if earnings are stable and growing.", "positive", "P/E Ratio")
        elif pe > 70:
            add(f"Very High P/E: {pe:.1f}×", "Priced for exceptional future growth. Any earnings miss could sharply compress the multiple.", "negative", "P/E Ratio", "high")
        elif pe > 45:
            add(f"High P/E: {pe:.1f}×", "Rich valuation relative to Nifty average. Earnings growth must stay strong to justify the multiple.", "warning", "P/E Ratio")

    pb = q.get("pb_ratio")
    if isinstance(pb, (int, float)):
        if pb < 1:
            add(f"Trades Below Book: {pb:.2f}×", "Price-to-Book below 1 — stock is trading below net asset value. Can signal distress or deep value.", "warning", "P/B Ratio")
        elif pb > 10:
            add(f"High P/B: {pb:.1f}×", "Significant premium over book value — market expects high future returns on equity.", "warning", "P/B Ratio")

    roe = q.get("roe")
    if isinstance(roe, (int, float)):
        if roe > 0.30:
            add(f"Excellent ROE: {roe*100:.1f}%", "Generating very strong returns on shareholders' equity — a hallmark of quality compounders.", "positive", "ROE", "high")
        elif roe > 0.20:
            add(f"Strong ROE: {roe*100:.1f}%", "Efficient use of shareholder capital, well above the 15% threshold for quality businesses.", "positive", "ROE")
        elif roe < 0:
            add(f"Negative ROE: {roe*100:.1f}%", "Company is destroying shareholder value — losses exceed equity base. Monitor cash runway.", "negative", "ROE", "high")
        elif roe < 0.08:
            add(f"Weak ROE: {roe*100:.1f}%", "Below-par returns on equity. Capital allocation or margin improvement needed.", "warning", "ROE")

    de = q.get("debt_to_equity")
    if isinstance(de, (int, float)):
        if de > 200:
            add(f"Very High Debt/Equity: {de:.0f}%", "Highly leveraged balance sheet. Rising interest rates or a slowdown could stress debt servicing.", "negative", "D/E Ratio", "high")
        elif de > 100:
            add(f"Elevated Debt/Equity: {de:.0f}%", "Moderate-to-high leverage. Watch interest coverage and operating cashflow trends.", "warning", "D/E Ratio")
        elif de < 10 and de >= 0:
            add(f"Nearly Debt-Free: {de:.0f}%", "Very low leverage gives financial flexibility and resilience in downturns.", "positive", "D/E Ratio")

    rg = q.get("revenue_growth")
    if isinstance(rg, (int, float)):
        if rg > 0.25:
            add(f"Strong Revenue Growth: +{rg*100:.1f}%", "Topline expanding rapidly — indicates strong demand or market share gains.", "positive", "Revenue Growth", "high")
        elif rg > 0.10:
            add(f"Healthy Revenue Growth: +{rg*100:.1f}%", "Consistent above-average topline growth. Business momentum is positive.", "positive", "Revenue Growth")
        elif rg < -0.10:
            add(f"Revenue Declining: {rg*100:.1f}% YoY", "Significant top-line contraction. Investigate whether this is sector-wide or company-specific.", "negative", "Revenue Growth", "high")
        elif rg < 0:
            add(f"Revenue Shrinking: {rg*100:.1f}% YoY", "Modest topline decline. Watch for a second consecutive quarter to confirm a trend.", "warning", "Revenue Growth")

    eg = q.get("earnings_growth")
    if isinstance(eg, (int, float)):
        if eg > 0.30:
            add(f"Earnings Accelerating: +{eg*100:.1f}%", "Rapid PAT growth — operating leverage or margin expansion is amplifying revenue gains.", "positive", "Earnings Growth", "high")
        elif eg < -0.30:
            add(f"Earnings Collapsing: {eg*100:.1f}% YoY", "Severe PAT decline. Check for one-time charges, rising costs, or structural margin pressure.", "negative", "Earnings Growth", "high")
        elif eg < 0:
            add(f"Earnings Shrinking: {eg*100:.1f}% YoY", "PAT falling faster than or despite stable revenue — margin pressure squeezing profitability.", "negative", "Earnings Growth")

    pm = q.get("profit_margin")
    if isinstance(pm, (int, float)):
        if pm > 0.25:
            add(f"Fat Net Margin: {pm*100:.1f}%", "Exceptional profitability — strong pricing power and cost control at work.", "positive", "Net Margin")
        elif pm < 0:
            add(f"Loss-Making: {pm*100:.1f}% margin", "Company is currently unprofitable. Assess cash burn rate and path to profitability.", "negative", "Net Margin", "high")
        elif pm < 0.05:
            add(f"Thin Net Margin: {pm*100:.1f}%", "Low profitability leaves little buffer for cost increases or revenue softness.", "warning", "Net Margin")

    dy = q.get("dividend_yield")
    if isinstance(dy, (int, float)) and dy > 0.04:
        add(f"High Dividend Yield: {dy*100:.2f}%", "Attractive income yield. Verify dividend is covered by free cashflow before treating as sustainable.", "positive", "Dividend Yield")

    beta = q.get("beta")
    if isinstance(beta, (int, float)):
        if beta > 1.5:
            add(f"High Beta: {beta:.2f}", "Significantly more volatile than Nifty. Amplifies gains in bull markets and losses in bear markets.", "warning", "Beta")
        elif beta < 0.5:
            add(f"Low Beta: {beta:.2f}", "Defensive stock — moves little with market. Suitable for capital preservation strategies.", "positive", "Beta")

    return signals
