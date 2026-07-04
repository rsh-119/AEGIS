"""
stock_service.py — Indian-market (NSE/BSE) stock data via IndianAPI.

Every ticker is normalised to an NSE (.NS) or BSE (.BO) symbol.
Search returns ONLY Indian-listed results.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from app.core.cache import cache
from app.services import indianapi_service

logger = logging.getLogger(__name__)


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

async def search_indian(query: str) -> list[dict]:
    """Local hardcoded index first (zero-latency), then IndianAPI's free static
    stock list for less common tickers (no quota cost — see indianapi_service)."""
    if len(query.strip()) < 2:
        return []
    key = f"search:{query.lower()}"
    if (c := cache.get(key)) is not None:
        return c

    local = _local_search(query)
    if len(local) >= 5:
        cache.set(key, local[:8], "search")
        return local[:8]

    seen = {r["symbol"] for r in local}
    extra = await indianapi_service.search_stocks(query, limit=12)
    supplemented = local + [r for r in extra if r["symbol"] not in seen]

    res = supplemented[:8]
    cache.set(key, res, "search")
    return res


# ── quote / fundamentals ──────────────────────────────────────────────────────

async def get_quote(ticker: str) -> dict:
    t = normalise_ticker(ticker)
    ck = f"quote:{t}"
    if (c := cache.get(ck)) is not None:
        return c

    bare = t.replace(".NS", "").replace(".BO", "")
    data = await indianapi_service.get_quote_bundle(t)
    if not data or not data.get("current_price"):
        return {"ticker": t, "error": "No data for this symbol"}

    res = _clean({
        "ticker": t,
        "currency": "INR",
        "exchange": "NSE" if t.endswith(".NS") else "BSE",
        **data,
    })
    res["fetched_at"] = int(time.time())
    cache.set(ck, res, "prices")
    return res


# ── price history + technicals ────────────────────────────────────────────────

def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


async def _history_from_indianapi(ticker: str, period: str) -> dict | None:
    """Fetch price+DMA+volume from IndianAPI /historical_data and reshape to
    Aegis' candle format. NOTE: IndianAPI's historical_data only exposes a
    daily CLOSE price (no intraday open/high/low), so open/high/low are set
    equal to close — charts render as a line, not true OHLC candlesticks."""
    bare = ticker.replace(".NS", "").replace(".BO", "")
    raw = await indianapi_service.get_historical_data(bare, period)
    if not raw:
        return None

    datasets = {d.get("metric"): d.get("values") or [] for d in (raw.get("datasets") or [])}
    price_pts = datasets.get("Price") or []
    if len(price_pts) < 5:
        return None

    dma50_map = {d[0]: d[1] for d in (datasets.get("DMA50") or [])}
    dma200_map = {d[0]: d[1] for d in (datasets.get("DMA200") or [])}
    vol_map = {d[0]: d[1] for d in (datasets.get("Volume") or [])}

    dates = [p[0] for p in price_pts]
    closes = pd.Series([float(p[1]) for p in price_pts], dtype=float)
    ma20 = closes.rolling(20).mean()
    rsi = _rsi(closes)

    candles = []
    for i, date in enumerate(dates):
        close = float(closes.iloc[i])
        dma50 = dma50_map.get(date)
        dma200 = dma200_map.get(date)
        vol = vol_map.get(date)
        candles.append({
            "date": date,
            "close": round(close, 2),
            "open": round(close, 2),
            "high": round(close, 2),
            "low": round(close, 2),
            "volume": int(vol) if vol else 0,
            "ma20": round(float(ma20.iloc[i]), 2) if not pd.isna(ma20.iloc[i]) else None,
            "ma50": round(float(dma50), 2) if dma50 is not None else None,
            "ma200": round(float(dma200), 2) if dma200 is not None else None,
            "rsi": round(float(rsi.iloc[i]), 1) if not pd.isna(rsi.iloc[i]) else None,
        })

    first, last = candles[0]["close"], candles[-1]["close"]
    pct = (last - first) / first * 100 if first else 0
    daily = closes.pct_change()
    vol_pct = float(daily.std() * (252 ** 0.5) * 100) if len(daily) > 1 else 0

    return _clean({
        "ticker": ticker,
        "period": period,
        "first_price": round(first, 2),
        "last_price": round(last, 2),
        "pct_change": round(pct, 2),
        "volatility_pct": round(vol_pct, 2),
        "latest_rsi": candles[-1]["rsi"],
        "candles": candles,
    })


async def get_history(ticker: str, period: str = "6mo") -> dict:
    t = normalise_ticker(ticker)
    ck = f"hist:{t}:{period}"
    if (c := cache.get(ck)) is not None:
        return c

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
