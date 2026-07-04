"""/api/market/* — market overview: indices, gainers, losers, cap segments, sector drilldown."""

from fastapi import APIRouter, HTTPException, Query
from app.services import market_service, stock_service, indianapi_service

router = APIRouter(prefix="/api/market", tags=["market"])

# Slug → IndianAPI index name. These are NOT yfinance symbols — IndianAPI's
# historical_data does fuzzy company-name matching, so plain "SENSEX" actually
# resolves to an unrelated instrument; "BSE SENSEX" is the verified-correct form.
_INDEX_SYMBOLS: dict[str, str] = {
    "nifty50":      "NIFTY",
    "sensex":       "BSE SENSEX",
    "banknifty":    "NIFTY BANK",
    "niftyit":      "NIFTY IT",
    "niftypharma":  "NIFTY PHARMA",
    "niftyauto":    "NIFTY AUTO",
    "niftyfmcg":    "NIFTY FMCG",
    "niftymetal":   "NIFTY METAL",
    "niftyenergy":  "NIFTY ENERGY",
    "niftyinfra":   "NIFTY INFRA",
    "niftyrealty":  "NIFTY REALTY",
    "niftymedia":   "NIFTY MEDIA",
}

# Slug → display name shown in /indices snapshot lookups for the quote portion
_INDEX_DISPLAY_NAMES: dict[str, str] = {
    "nifty50":      "NIFTY 50",
    "sensex":       "SENSEX",
    "banknifty":    "NIFTY Bank",
    "niftyit":      "NIFTY IT",
    "niftypharma":  "NIFTY PHARMA",
    "niftyauto":    "NIFTY AUTO",
    "niftyfmcg":    "NIFTY FMCG",
    "niftymetal":   "NIFTY METAL",
    "niftyenergy":  "NIFTY ENERGY",
    "niftyinfra":   "NIFTY INFRA",
    "niftyrealty":  "NIFTY REALTY",
    "niftymedia":   "NIFTY MEDIA",
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
    index_name = _INDEX_SYMBOLS.get(slug.lower())
    if not index_name:
        raise HTTPException(status_code=404, detail=f"Unknown index: {slug}")
    if period not in {"1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}:
        period = "1y"

    hist = await stock_service._history_from_indianapi(index_name, period)
    if hist is None:
        hist = {"symbol": index_name, "period": period, "error": "No history data available"}

    display_name = _INDEX_DISPLAY_NAMES.get(slug.lower(), index_name)
    indices = await indianapi_service.get_indices_data()
    row = next((i for i in indices if i.get("name") == display_name), None)
    quote = None
    if row:
        price = float(row["price"])
        net_change = float(row.get("netChange") or 0)
        quote = {
            "current_price": price,
            "previous_close": round(price - net_change, 2),
            "pct_change": float(row.get("percentChange") or 0),
        }

    return {"slug": slug, "symbol": index_name, "history": hist, "quote": quote}


@router.get("/cap/{size}")
async def cap_stocks(size: str):
    """Return all tracked stocks for large / mid / small cap tier."""
    if size not in {"large", "mid", "small"}:
        raise HTTPException(status_code=400, detail="size must be large, mid, or small")
    return await market_service.get_cap_stocks(size)


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
