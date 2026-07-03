"""/api/stocks/* — quotes, history, search, full analysis, forecast, health."""

import asyncio
from fastapi import APIRouter, HTTPException, Query

from app.services import stock_service, news_service, ai_service, forecast_service, concall_service, peer_service, shareholding_service

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}


@router.get("/search")
async def search(q: str = Query(..., min_length=2)):
    """Autocomplete — Indian (NSE/BSE) results only."""
    return await stock_service.search_indian(q)


@router.get("/batch-quotes")
async def batch_quotes(tickers: str = Query(..., description="Comma-separated ticker list, max 30")):
    """
    Fetch quotes for multiple tickers in one request.
    Returns a dict keyed by normalised ticker symbol.
    Ideal for portfolio dashboards and watchlists.
    """
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()][:30]
    if not syms:
        return {}
    results = await asyncio.gather(*[stock_service.get_quote(s) for s in syms], return_exceptions=True)
    return {
        sym: (r if not isinstance(r, Exception) else {"ticker": sym, "error": str(r)})
        for sym, r in zip(syms, results)
    }


@router.get("/{ticker}/quote")
async def quote(ticker: str):
    data = await stock_service.get_quote(ticker)
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data


@router.get("/{ticker}/history")
async def history(ticker: str, period: str = "6mo"):
    if period not in _PERIODS:
        period = "6mo"
    data = await stock_service.get_history(ticker, period)
    # Return 200 with empty candles rather than 503 — chart shows empty state gracefully
    if "error" in data and "candles" not in data:
        data["candles"] = []
    return data


@router.get("/{ticker}/news")
async def news(ticker: str):
    q = await stock_service.get_quote(ticker)
    company = q.get("company_name") if "error" not in q else None
    return await news_service.get_news_and_sentiment(ticker, company)


@router.get("/{ticker}/forecast")
async def price_forecast(ticker: str, horizon: int = 30, model: str = "holt"):
    hist = await stock_service.get_history(ticker, "2y")
    candles = hist.get("candles", [])
    if not candles:
        raise HTTPException(status_code=503, detail="Insufficient history for forecast")
    if model not in ("holt", "xgboost", "lgbm"):
        model = "holt"
    return forecast_service.forecast(
        candles,
        horizon_days=min(horizon, 30),
        model=model,
    )


@router.get("/{ticker}/core")
async def core_data(ticker: str, period: str = "6mo"):
    """Fast endpoint — quote + history + signals only. No AI, no news, no forecasts.
    Designed to render the stock page immediately while deferred data loads in the background."""
    if period not in _PERIODS:
        period = "6mo"
    quote, hist = await asyncio.gather(
        stock_service.get_quote(ticker),
        stock_service.get_history(ticker, period),
    )
    # Return partial data rather than 503 — stock page shows what it can
    if "error" in quote and "current_price" not in quote:
        t = stock_service.normalise_ticker(ticker)
        quote = {"ticker": t, "error": quote["error"]}
    if "error" in hist and "candles" not in hist:
        hist = {"ticker": quote.get("ticker", ticker), "candles": [], "error": hist.get("error")}
    return {
        "quote":   quote,
        "history": hist,
        "signals": stock_service.ratio_signals(quote),
    }


@router.get("/{ticker}/insights")
async def insights(ticker: str):
    """Deferred endpoint — news, AI analysis, health diagnosis, and all three forecasts.
    Called in parallel with /core so these load in the background while the page is already visible."""
    quote, hist = await asyncio.gather(
        stock_service.get_quote(ticker),
        stock_service.get_history(ticker, "6mo"),
    )
    # If quote is unavailable, return an empty insights shell rather than 503
    if "error" in quote and "current_price" not in quote:
        return {"error": quote["error"], "news": [], "ai": {}, "health": {}, "forecasts": {}}

    company  = quote.get("company_name")
    signals  = stock_service.ratio_signals(quote)

    # News + AI + forecasts all in parallel
    news_data, ai_analysis, health, fc_holt, fc_xgb, fc_lgbm = await asyncio.gather(
        news_service.get_news_and_sentiment(ticker, company),
        ai_service.analyse_stock(quote, signals, hist, {}),  # sentiment injected below after news
        ai_service.diagnose_health(quote, hist, {}, []),
        _forecast_from_hist(ticker, "holt"),
        _forecast_from_hist(ticker, "xgboost"),
        _forecast_from_hist(ticker, "lgbm"),
    )

    return {
        "news":       news_data["articles"],
        "sentiment":  news_data["sentiment"],
        "ai_analysis": ai_analysis,
        "health":     health,
        "forecast": {
            "holt":    fc_holt,
            "xgboost": fc_xgb,
            "lgbm":    fc_lgbm,
        },
    }


@router.get("/{ticker}/analysis")
async def full_analysis(ticker: str, period: str = "6mo"):
    """Legacy combined endpoint — kept for backwards compatibility."""
    if period not in _PERIODS:
        period = "6mo"
    core, ins = await asyncio.gather(
        core_data(ticker, period),
        insights(ticker),
    )
    return {**core, **ins}


@router.get("/{ticker}/peers")
async def peers(ticker: str):
    """Peer comparison + sector averages."""
    q = await stock_service.get_quote(ticker)
    # When yfinance is rate-limited, return an empty peers shell rather than 503
    if "error" in q and "current_price" not in q:
        return {"peers": [], "sector_avg": {}, "partial": True, "error": q["error"]}
    result = await peer_service.get_peer_comparison(
        ticker, q.get("sector", ""), q.get("industry")
    )
    return result


@router.get("/{ticker}/concall-summary")
async def concall_summary(ticker: str):
    """AI-generated concall summary for the last 4 quarters."""
    data = await concall_service.get_concall_summary(ticker)
    if "error" in data:
        # Return 503 only for non-rate-limit errors; for rate-limit return empty so UI shows graceful state
        detail = data["error"]
        if "rate-limit" in detail.lower() or "rate limited" in detail.lower():
            return {"summaries": [], "partial": True, "error": detail}
        raise HTTPException(status_code=503, detail=detail)
    return data


async def _forecast_from_hist(ticker: str, model: str = "holt") -> dict:
    hist = await stock_service.get_history(ticker, "2y")
    if "error" in hist:
        return {"available": False, "reason": hist["error"]}
    return forecast_service.forecast(hist.get("candles", []), horizon_days=30, model=model)


@router.get('/{ticker}/shareholding-history')
async def shareholding_history(ticker: str):
    """Quarterly shareholding pattern history from BSE India (SEBI public disclosure)."""
    return await shareholding_service.get_shareholding_history(ticker)


# ── IndianAPI-backed per-stock endpoints ──────────────────────────────────────

@router.get("/{ticker}/analyst-targets")
async def analyst_targets(ticker: str):
    """Analyst price targets and recommendations from IndianAPI."""
    from app.services.indianapi_service import get_stock_target_price
    bare = ticker.upper().replace(".NS", "").replace(".BO", "")
    data = await get_stock_target_price(bare)
    if not data:
        raise HTTPException(status_code=404, detail="No analyst target data available")
    return data


@router.get("/{ticker}/analyst-forecasts")
async def analyst_forecasts(ticker: str):
    """Analyst revenue and EPS forecasts from IndianAPI."""
    from app.services.indianapi_service import get_stock_forecasts
    bare = ticker.upper().replace(".NS", "").replace(".BO", "")
    data = await get_stock_forecasts(bare)
    if not data:
        raise HTTPException(status_code=404, detail="No forecast data available")
    return data


@router.get("/{ticker}/announcements")
async def stock_announcements(ticker: str):
    """Corporate announcements (BSE/NSE filings) from IndianAPI."""
    from app.services.indianapi_service import get_recent_announcements
    bare = ticker.upper().replace(".NS", "").replace(".BO", "")
    data = await get_recent_announcements(bare)
    return data or []


@router.get("/{ticker}/corporate-actions")
async def stock_corporate_actions(ticker: str):
    """Dividends, splits, and bonus history — IndianAPI primary, yfinance fallback."""
    import asyncio
    from app.services.indianapi_service import get_corporate_actions
    bare = ticker.upper().replace(".NS", "").replace(".BO", "")
    data = await get_corporate_actions(bare)
    if data:
        return data

    # yfinance fallback: dividends + stock splits
    def _yf_actions():
        import yfinance as yf
        from app.core.yf_session import YF_SESSION
        t = yf.Ticker(ticker, session=YF_SESSION)
        out = []
        try:
            for date, amt in t.dividends.items():
                if amt > 0:
                    out.append({"type": "Dividend", "date": str(date.date()), "amount": round(float(amt), 2)})
        except Exception:
            pass
        try:
            for date, ratio in t.splits.items():
                if ratio > 0:
                    out.append({"type": "Split", "date": str(date.date()), "ratio": float(ratio)})
        except Exception:
            pass
        out.sort(key=lambda x: x["date"], reverse=True)
        return out[:30]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _yf_actions)
