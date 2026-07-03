"""/api/market/* — market overview: indices, gainers, losers, cap segments, sector drilldown."""

from fastapi import APIRouter, HTTPException, Query
from app.services import market_service, stock_service

router = APIRouter(prefix="/api/market", tags=["market"])

# Slug → yfinance symbol
_INDEX_SYMBOLS: dict[str, str] = {
    "nifty50":      "^NSEI",
    "sensex":       "^BSESN",
    "banknifty":    "^NSEBANK",
    "niftyit":      "^CNXIT",
    "niftypharma":  "^CNXPHARMA",
    "niftyauto":    "^CNXAUTO",
    "niftyfmcg":    "^CNXFMCG",
    "niftymetal":   "^CNXMETAL",
    "niftyenergy":  "^CNXENERGY",
    "niftyinfra":   "^CNXINFRA",
    "niftyrealty":  "^CNXREALTY",
    "niftymedia":   "^CNXMEDIA",
}

@router.get("/sectors")
async def sectors():
    """List all available sectors with their stock counts."""
    from app.services.peer_service import _SECTOR_PEERS
    return [
        {"sector": name, "count": len(tickers), "tickers": [t.replace(".NS", "").replace(".BO", "") for t in tickers]}
        for name, tickers in _SECTOR_PEERS.items()
    ]


@router.get("/indices")
async def indices():
    """Fast endpoint — only the 5 headline index prices. Used by the top MarketBar."""
    return await market_service.get_indices()


@router.get("/overview")
async def overview():
    return await market_service.get_market_overview()


@router.get("/index/{slug}")
async def index_data(slug: str, period: str = "1y"):
    yf_sym = _INDEX_SYMBOLS.get(slug.lower())
    if not yf_sym:
        raise HTTPException(status_code=404, detail=f"Unknown index: {slug}")
    if period not in {"1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}:
        period = "1y"
    hist = await stock_service.get_history(yf_sym, period)
    quote = await stock_service.get_quote(yf_sym)
    return {"slug": slug, "symbol": yf_sym, "history": hist, "quote": quote}


@router.get("/cap/{size}")
async def cap_stocks(size: str):
    """Return all tracked stocks for large / mid / small cap tier."""
    if size not in {"large", "mid", "small"}:
        raise HTTPException(status_code=400, detail="size must be large, mid, or small")
    return await market_service.get_cap_stocks(size)


@router.get("/etfs")
async def etf_data():
    """Return curated NSE ETF list with 1Y/3Y/5Y price returns."""
    return await market_service.get_etf_data()


@router.get("/bulk-deals")
async def bulk_deals(limit: int = Query(20, ge=1, le=50)):
    """Recent NSE bulk & block deals sorted by deal value."""
    from app.services.bulk_deals_service import get_bulk_deals
    return await get_bulk_deals(limit=limit)


@router.get("/sector/{sector}")
async def sector_stocks(sector: str):
    result = await market_service.get_sector_stocks(sector)
    if result.get("error") and not result.get("stocks"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── IndianAPI-backed endpoints ────────────────────────────────────────────────

@router.get("/ipo")
async def ipo():
    """Upcoming and recent IPOs."""
    return await market_service.get_ipo()


@router.get("/commodities")
async def commodities():
    """Live commodity prices — gold, silver, crude oil, etc."""
    return await market_service.get_commodities()


@router.get("/52week")
async def week52():
    """Stocks near 52-week highs and lows."""
    return await market_service.get_52week()


@router.get("/price-shockers")
async def price_shockers():
    """Stocks with unusual intraday price movements."""
    return await market_service.get_price_shockers()


@router.get("/announcements")
async def announcements(ticker: str | None = None):
    """Recent corporate announcements. Pass ?ticker=RELIANCE for stock-specific."""
    return await market_service.get_announcements(ticker)


@router.get("/corporate-actions")
async def corporate_actions(ticker: str | None = None):
    """Dividends, splits, bonuses. Pass ?ticker=INFY for stock-specific."""
    return await market_service.get_corporate_actions(ticker)
