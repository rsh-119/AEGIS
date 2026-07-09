"""
peer_service.py — peer comparison and sector averages for Indian stocks.
Compares a stock against its sector peers on key financial ratios,
exactly like screener.in's comparison table.
"""

from __future__ import annotations

import asyncio
import logging

from app.services import indianapi_service
from app.services.stock_service import normalise_ticker, _clean
from app.core.cache import cache

logger = logging.getLogger(__name__)

# ── Sector → peer ticker list (NSE) ───────────────────────────────────────────
_SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": [
        "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIMINDTREE.NS",
        "MPHASIS.NS", "PERSISTENT.NS", "COFORGE.NS", "KPITTECH.NS",
        "OFSS.NS", "TATAELXSI.NS", "LTTS.NS", "HEXT.NS", "ZENSARTECH.NS",
        "MASTEK.NS", "CYIENT.NS", "BSOFT.NS", "SASKEN.NS",
        "INTELLECT.NS", "NEWGEN.NS", "HAPPSTMNDS.NS", "RATEGAIN.NS", "TANLA.NS",
    ],
    "Financial Services": [
        "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "SBIN.NS", "AXISBANK.NS",
        "BAJFINANCE.NS", "INDUSINDBK.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS", "BANDHANBNK.NS",
        "RBLBANK.NS", "YESBANK.NS", "PNB.NS", "BANKBARODA.NS", "CANBK.NS",
        "UNIONBANK.NS", "AUBANK.NS", "UJJIVANSFB.NS", "UITASBNK.NS", "HDFCLIFE.NS",
        "SBILIFE.NS", "ICICIPRULI.NS", "BAJAJFINSV.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS",
        "SHRIRAMFIN.NS", "M&MFIN.NS", "PNBHOUSING.NS", "LICHSGFIN.NS", "RECLTD.NS",
    ],
    "Energy": [
        "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "HINDPETRO.NS", "IOC.NS",
        "GAIL.NS", "ADANIENT.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "PETRONET.NS",
        "GUJENERGY.NS", "OIL.NS", "MRPL.NS", "CASTROLIND.NS", "GSPL.NS",
        "MGL.NS", "IGL.NS", "AEGISLOG.NS", "ATGL.NS",
    ],
    "Consumer Defensive": [
        "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "DABUR.NS", "MARICO.NS",
        "BRITANNIA.NS", "GODREJCP.NS", "TATACONSUM.NS", "PGHH.NS", "EMAMILTD.NS",
        "JYOTHYLAB.NS", "PATANJALI.NS", "ZYDUSWELL.NS", "AWL.NS", "GOCOLORS.NS",
        "VBL.NS", "RADICO.NS", "UNITDSPR.NS", "VAIBHAVGBL.NS",
    ],
    "Consumer Cyclical": [
        "MARUTI.NS", "TVSMOTOR.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
        "TATAMOTORS.NS", "M&M.NS", "TRENT.NS", "PVRINOX.NS", "TITAN.NS", "JUBLFOOD.NS",
        "BATAINDIA.NS", "METROBRAND.NS", "RELAXO.NS", "VIPIND.NS",
        "SHOPERSTOP.NS", "NYKAA.NS", "MANYAVAR.NS", "CROMPTON.NS", "HAVELLS.NS",
        "VOLTAS.NS", "BLUESTARCO.NS", "WHIRLPOOL.NS", "SYMPHONY.NS", "AMBER.NS",
    ],
    "Healthcare": [
        "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS",
        "AUROPHARMA.NS", "ALKEM.NS", "TORNTPHARM.NS", "BIOCON.NS", "LALPATHLAB.NS",
        "FORTIS.NS", "APOLLOHOSP.NS", "MAXHEALTH.NS", "MANKIND.NS", "AJANTPHARM.NS",
        "IPCALAB.NS", "NATCOPHARM.NS", "JBCHEPHARM.NS", "GLAND.NS", "ERIS.NS",
        "SYNGENE.NS", "THYROCARE.NS", "METROPOLIS.NS", "KRSNAA.NS", "VIJAYA.NS",
    ],
    "Industrials": [
        "LT.NS", "HAL.NS", "BEL.NS", "BHEL.NS", "BOSCHLTD.NS",
        "SIEMENS.NS", "ABB.NS", "CUMMINSIND.NS", "BHARATFORG.NS", "THERMAX.NS",
        "HAVELLS.NS", "POLYCAB.NS", "KEI.NS", "KPIL.NS", "AIAENG.NS",
        "GRINDWELL.NS", "KIRLOSENG.NS", "ELGIEQUIP.NS", "TIMKEN.NS", "SCHAEFFLER.NS",
        "SKFINDIA.NS", "ASTRAL.NS", "SUPREMEIND.NS", "FINPIPE.NS", "VGUARD.NS",
    ],
    "Basic Materials": [
        "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "SAIL.NS", "NMDC.NS",
        "NATIONALUM.NS", "VEDL.NS", "HINDZINC.NS", "AMBUJACEM.NS", "ULTRACEMCO.NS",
        "ACC.NS", "SHREECEM.NS", "DALBHARAT.NS", "JKCEMENT.NS", "RAMCOCEM.NS",
        "GRASIM.NS", "APCOTEXIND.NS", "PIDILITIND.NS", "ASIANPAINT.NS", "BERGEPAINT.NS",
        "KANSAINER.NS", "SHAREINDIA.NS", "MOIL.NS", "GMRAIRPORT.NS", "COALINDIA.NS",
    ],
    "Real Estate": [
        "DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS", "PRESTIGE.NS",
        "BRIGADE.NS", "SOBHA.NS", "LODHA.NS", "SUNTECK.NS", "KOLTEPATIL.NS",
        "MAHLIFE.NS", "ANANTRAJ.NS", "NCLIND.NS", "EMBDL.NS", "ARVSMART.NS",
    ],
    "Communication Services": [
        "BHARTIARTL.NS", "IDEA.NS", "ETERNAL.NS", "NAUKRI.NS", "SUNTV.NS",
        "ZEEL.NS", "NETWORK18.NS", "INDIAMART.NS", "JUSTDIAL.NS",
        "HATHWAY.NS", "TTML.NS", "ONMOBILE.NS", "NAZARA.NS", "DELHIVERY.NS",
    ],
    "Utilities": [
        "NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "ADANIGREEN.NS", "CESC.NS",
        "TORNTPOWER.NS", "NHPC.NS", "SJVN.NS", "IREDA.NS", "JSWENERGY.NS",
        "ADANIPOWER.NS", "RPOWER.NS", "INOXWIND.NS", "SUZLON.NS",
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


# Reverse index (ticker -> sector) built from the bucket above — lets callers
# find a stock's sector even when its own live quote is unavailable (e.g. a
# ticker IndianAPI's /stock endpoint simply doesn't carry, like LTIMindtree).
_TICKER_TO_SECTOR: dict[str, str] = {
    t.upper(): sector for sector, tickers in _SECTOR_PEERS.items() for t in tickers
}


def static_sector_for_ticker(ticker: str) -> str | None:
    return _TICKER_TO_SECTOR.get(normalise_ticker(ticker).upper())


async def _fetch_peer(ticker: str) -> dict | None:
    """Single-call peer fundamentals via IndianAPI /get_stock_data — already
    includes sector-relative comparisons (sectorPe, sectorRoe, etc.)."""
    t = normalise_ticker(ticker)
    bare = t.replace(".NS", "").replace(".BO", "")
    try:
        raw = await indianapi_service.get_stock_data(bare)
        if not raw:
            return None
        parsed = indianapi_service.parse_stock_data(raw)
        return _clean({
            "ticker": t,
            "name": raw.get("name") or t.replace(".NS", ""),
            "market_cap": parsed.get("market_cap"),
            "pe_ratio": parsed.get("pe_ratio"),
            "pb_ratio": parsed.get("pb_ratio"),
            "roe": parsed.get("roe"),
            "revenue_growth": parsed.get("revenue_growth"),
            "earnings_growth": parsed.get("earnings_growth"),
            "debt_to_equity": parsed.get("debt_to_equity"),
            "profit_margin": parsed.get("profit_margin"),
            "dividend_yield": parsed.get("dividend_yield"),
            "eps": parsed.get("eps"),
            "sector_pe": parsed.get("sector_pe"),
            "sector_roe": parsed.get("sector_roe"),
            "sector_roce": parsed.get("sector_roce"),
        })
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
    t = normalise_ticker(ticker)
    key = f"peers:{t}"
    if (c := cache.get(key)) is not None:
        return c

    # Primary: IndianAPI's own curated peerCompanyList (real editorial peers,
    # zero extra API calls — reuses the /stock response get_quote already fetched).
    bare = t.replace(".NS", "").replace(".BO", "")
    stock_raw = await indianapi_service.get_stock(bare)
    peers = await indianapi_service.get_peer_companies(stock_raw) if stock_raw else []

    # Fallback: hardcoded sector bucket (used only if IndianAPI has no peer data)
    if not peers:
        peer_tickers = _peer_tickers(sector, industry, ticker)
        if peer_tickers:
            results = await asyncio.gather(*[_fetch_peer(t) for t in peer_tickers])
            peers = [r for r in results if r is not None]

    sector_avg = _sector_averages(peers)
    out = {"peers": peers, "sector_avg": sector_avg, "sector": sector}
    cache.set(key, out, "peers")
    return out
