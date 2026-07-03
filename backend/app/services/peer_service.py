"""
peer_service.py — peer comparison and sector averages for Indian stocks.
Compares a stock against its sector peers on key financial ratios,
exactly like screener.in's comparison table.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf

from app.services.stock_service import normalise_ticker, _clean
from app.core.cache import cache

logger = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=12)

# ── Sector → peer ticker list (NSE) ───────────────────────────────────────────
_SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": [
        "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS",
        "MPHASIS.NS", "PERSISTENT.NS", "COFORGE.NS", "KPITTECH.NS",
        "OFSS.NS", "TATAELXSI.NS", "LTTS.NS", "HEXAWARE.NS", "ZENSARTECH.NS",
        "MASTEK.NS", "CYIENT.NS", "BSOFT.NS", "SASKEN.NS",
        "INTELLECT.NS", "NEWGEN.NS", "HAPPSTMNDS.NS", "RATEGAIN.NS", "TANLA.NS",
    ],
    "Financial Services": [
        "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "SBIN.NS", "AXISBANK.NS",
        "BAJFINANCE.NS", "INDUSINDBK.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS", "BANDHANBNK.NS",
        "RBLBANK.NS", "YESBANK.NS", "PNB.NS", "BANKBARODA.NS", "CANBK.NS",
        "UNIONBANK.NS", "AUBANK.NS", "UJJIVANSFB.NS", "EQUITASBNK.NS", "HDFCLIFE.NS",
        "SBILIFE.NS", "ICICIPRULI.NS", "BAJAJFINSV.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS",
        "SHRIRAMFIN.NS", "M&MFIN.NS", "PNBHOUSING.NS", "LICHSGFIN.NS", "RECLTD.NS",
    ],
    "Energy": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "HPCL.NS", "IOC.NS",
        "GAIL.NS", "ADANIENT.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "PETRONET.NS",
        "GUJARATGAS.NS", "OIL.NS", "MRPL.NS", "CASTROLIND.NS", "GSPL.NS",
        "ADANITOTAL.NS", "MGL.NS", "IGL.NS", "AEGASIND.NS", "ATGL.NS",
    ],
    "Consumer Defensive": [
        "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "DABUR.NS", "MARICO.NS",
        "BRITANNIA.NS", "GODREJCP.NS", "TATACONSUM.NS", "PGHH.NS", "EMAMILTD.NS",
        "JYOTHYLAB.NS", "PATANJALI.NS", "ZYDUSWELL.NS", "AGRO.NS", "GOCOLORS.NS",
        "VBL.NS", "RADICO.NS", "UNITEDSPRT.NS", "MCDOWELL-N.NS", "VAIBHAVGBL.NS",
    ],
    "Consumer Cyclical": [
        "MARUTI.NS", "TVSMOTORS.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
        "M&M.NS", "TRENT.NS", "PVRINOX.NS", "TITAN.NS", "JUBLFOOD.NS",
        "VEDANT.NS", "BATAINDIA.NS", "METROBRAND.NS", "RELAXO.NS", "VIPIND.NS",
        "SHOPERSTOP.NS", "NYKAA.NS", "MANYAVAR.NS", "CROMPTON.NS", "HAVELLS.NS",
        "VOLTAS.NS", "BLUESTARCO.NS", "WHIRLPOOL.NS", "SYMPHONY.NS", "AMBER.NS",
    ],
    "Healthcare": [
        "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS",
        "AUROPHARMA.NS", "ALKEM.NS", "TORNTPHARM.NS", "BIOCON.NS", "LALPATHLAB.NS",
        "FORTIS.NS", "APOLLOHOSP.NS", "MAXHEALTH.NS", "MANKIND.NS", "AJANTPHARM.NS",
        "IPCALAB.NS", "NATCOPHARM.NS", "JBCHEPHARM.NS", "GLAND.NS", "ERIS.NS",
        "SYNGENE.NS", "THYROCARE.NS", "METROPOLIS.NS", "KRSNAA.NS", "VIJAYALAB.NS",
    ],
    "Industrials": [
        "LT.NS", "HAL.NS", "BEL.NS", "BHEL.NS", "BOSCHLTD.NS",
        "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS", "BHARATFORG.NS", "THERMAX.NS",
        "HAVELLS.NS", "POLYCAB.NS", "KEI.NS", "KALPATPOWR.NS", "AIAENG.NS",
        "GRINDWELL.NS", "KIRLOSKAR.NS", "ELGIEQUIP.NS", "TIMKEN.NS", "SCHAEFFLER.NS",
        "SKFINDIA.NS", "ASTRAL.NS", "SUPREMEIND.NS", "FINOLEX.NS", "VGUARD.NS",
    ],
    "Basic Materials": [
        "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "SAIL.NS", "NMDC.NS",
        "NATIONALUM.NS", "VEDL.NS", "HINDZINC.NS", "AMBUJACEM.NS", "ULTRACEMCO.NS",
        "ACC.NS", "SHREECEM.NS", "DALBHARAT.NS", "JKCEMENT.NS", "RAMCOCEM.NS",
        "GRASIM.NS", "APCOTEXIND.NS", "PIDILITIND.NS", "ASIANPAINT.NS", "BERGER.NS",
        "KANSAINER.NS", "SHAREINDIA.NS", "MOIL.NS", "GMRINFRA.NS", "COALINDIA.NS",
    ],
    "Real Estate": [
        "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS", "PRESTIGE.NS",
        "BRIGADE.NS", "SOBHA.NS", "LODHA.NS", "SUNTECK.NS", "KOLTEPATIL.NS",
        "MAHLIFE.NS", "ANANTRAJ.NS", "NCLIND.NS", "IBREALEST.NS", "ARVSMART.NS",
    ],
    "Communication Services": [
        "BHARTIARTL.NS", "IDEA.NS", "ETERNAL.NS", "NAUKRI.NS", "SUNTV.NS",
        "ZEEL.NS", "NETWORK18.NS", "TV18BRDCST.NS", "INDIAMART.NS", "JUSTDIAL.NS",
        "HATHWAY.NS", "TTML.NS", "ONMOBILE.NS", "NAZARA.NS", "DELHIVERY.NS",
    ],
    "Utilities": [
        "NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "CESC.NS",
        "TORNTPOWER.NS", "NHPC.NS", "SJVN.NS", "IREDA.NS", "JSWENERGY.NS",
        "ADANIPOWER.NS", "RPOWER.NS", "NPCIL.NS", "INOXWIND.NS", "SUZLON.NS",
    ],
}

_INDUSTRY_TO_SECTOR = {
    "Banks": "Financial Services",
    "Insurance": "Financial Services",
    "Capital Markets": "Financial Services",
    "Consumer Finance": "Financial Services",
    "Software—Application": "Technology",
    "Software—Infrastructure": "Technology",
    "Information Technology Services": "Technology",
    "Semiconductor": "Technology",
    "Oil & Gas Integrated": "Energy",
    "Oil & Gas Refining & Marketing": "Energy",
    "Oil & Gas E&P": "Energy",
    "Utilities—Regulated Electric": "Utilities",
    "Utilities—Renewable": "Utilities",
    "Drug Manufacturers": "Healthcare",
    "Medical Devices": "Healthcare",
    "Diagnostics & Research": "Healthcare",
    "Auto Manufacturers": "Consumer Cyclical",
    "Auto Parts": "Consumer Cyclical",
    "Packaged Foods": "Consumer Defensive",
    "Household & Personal Products": "Consumer Defensive",
    "Beverages—Non-Alcoholic": "Consumer Defensive",
    "Steel": "Basic Materials",
    "Aluminum": "Basic Materials",
    "Cement": "Basic Materials",
    "Engineering & Construction": "Industrials",
    "Aerospace & Defense": "Industrials",
    "Real Estate": "Real Estate",
    "Telecom": "Communication Services",
}


def _peer_tickers(sector: str, industry: str | None, self_ticker: str) -> list[str]:
    """Return peer tickers for the sector, excluding self."""
    key = sector or (industry and _INDUSTRY_TO_SECTOR.get(industry, "")) or ""
    peers = _SECTOR_PEERS.get(key, [])
    self_norm = normalise_ticker(self_ticker)
    return [p for p in peers if p.upper() != self_norm.upper()][:9]


def _fetch_peer_sync(ticker: str) -> dict | None:
    from app.core.yf_session import yf_blocked, yf_on_rate_limit
    from yfinance.exceptions import YFRateLimitError
    if yf_blocked():
        return None
    try:
        t = normalise_ticker(ticker)
        info = yf.Ticker(t).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        prev = info.get("previousClose")
        if not price:
            return None
        day_chg = (price - prev) / prev * 100 if prev else None
        return _clean({
            "ticker": t,
            "name": info.get("shortName") or info.get("longName") or t.replace(".NS", ""),
            "price": price,
            "day_change_pct": round(day_chg, 2) if day_chg is not None else None,
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "debt_to_equity": info.get("debtToEquity"),
            "profit_margin": info.get("profitMargins"),
            "dividend_yield": info.get("dividendYield"),
            "eps": info.get("trailingEps"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low": info.get("fiftyTwoWeekLow"),
        })
    except YFRateLimitError:
        yf_on_rate_limit()
        return None
    except Exception as e:
        logger.debug("peer fetch failed for %s: %s", ticker, e)
        return None


def _sector_averages(peers: list[dict]) -> dict:
    """Compute median (not mean, less skewed) for each numeric metric."""
    import statistics

    def med(key: str) -> float | None:
        vals = [p[key] for p in peers if p.get(key) is not None]
        if not vals:
            return None
        try:
            return round(statistics.median(vals), 3)
        except Exception:
            return None

    return {
        "pe_ratio": med("pe_ratio"),
        "pb_ratio": med("pb_ratio"),
        "roe": med("roe"),
        "revenue_growth": med("revenue_growth"),
        "earnings_growth": med("earnings_growth"),
        "debt_to_equity": med("debt_to_equity"),
        "profit_margin": med("profit_margin"),
        "dividend_yield": med("dividend_yield"),
    }


async def get_peer_comparison(ticker: str, sector: str, industry: str | None) -> dict:
    key = f"peers:{normalise_ticker(ticker)}"
    if (c := cache.get(key)) is not None:
        return c

    peer_tickers = _peer_tickers(sector, industry, ticker)
    if not peer_tickers:
        return {"peers": [], "sector_avg": {}, "sector": sector}

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(_pool, _fetch_peer_sync, t) for t in peer_tickers]
    )
    peers = [r for r in results if r is not None]
    sector_avg = _sector_averages(peers)

    out = {"peers": peers, "sector_avg": sector_avg, "sector": sector}
    cache.set(key, out, "peers")
    return out
