"""/api/stocks/* — quotes, history, search, full analysis, forecast, health."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Query

from app.services import stock_service, news_service, ai_service, forecast_service, concall_service, peer_service, shareholding_service, financials_service, finance_math

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}

# xgboost/lgbm forecasts fit a model per horizon day (CPU-bound, ~10-25s each
# on Render's free tier). Running them inline on the event loop would block
# EVERY request to this service — WEB_CONCURRENCY=1 means one stalled
# forecast call stalls all other users too. Off-loaded to a thread pool so
# the event loop stays free (xgboost/lightgbm release the GIL during their
# native fit() calls, so multiple forecasts can genuinely overlap here too).
_forecast_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="forecast")


async def _forecast_async(candles: list[dict], horizon_days: int, model: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _forecast_pool, forecast_service.forecast, candles, horizon_days, model
    )


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


@router.get("/{ticker}/calculator")
async def returns_calculator(
    ticker: str,
    mode: str = "sip",       # "sip" | "lumpsum"
    amount: float = 5000,
    start_date: str = "",    # YYYY-MM-DD; defaults to earliest available price if blank
):
    """What-if returns calculator for this specific stock — SIP (one purchase
    per calendar month) or lumpsum (single purchase), from start_date to the
    latest available price. Reuses the same XIRR math as the portfolio page
    (app.services.finance_math) rather than a separate implementation."""
    if mode not in ("sip", "lumpsum"):
        raise HTTPException(status_code=400, detail="mode must be 'sip' or 'lumpsum'")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    hist = await stock_service.get_history(ticker, "max")
    if "error" in hist:
        raise HTTPException(status_code=404, detail="No price history available for this stock")
    closes = finance_math.closes_map(hist)
    if len(closes) < 2:
        raise HTTPException(status_code=404, detail="Not enough price history to calculate returns")

    earliest, latest = closes[0][0], closes[-1][0]
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date must be YYYY-MM-DD")
    else:
        start = earliest
    start = max(start, earliest)
    if start >= latest:
        raise HTTPException(status_code=400, detail="start_date must be before the latest available price date")

    current_price = closes[-1][1]

    if mode == "lumpsum":
        entry_price = finance_math.close_at(closes, start)
        units = amount / entry_price if entry_price else 0.0
        invested = amount
        current_value = units * current_price
        flows: list[tuple[date, float]] = [(start, -amount), (latest, current_value)]
    else:  # sip — one purchase per calendar month, start_date through latest
        flows = []
        units = 0.0
        invested = 0.0
        d = start
        while d <= latest:
            px = finance_math.close_at(closes, d)
            if px:
                units += amount / px
                invested += amount
                flows.append((d, -amount))
            month = d.month + 1
            year = d.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(d.day, 28)   # sidesteps month-length overflow (e.g. Jan 31 -> Feb 31)
            d = date(year, month, day)
        current_value = units * current_price
        flows.append((latest, current_value))

    xirr_pct = finance_math.xirr(flows)
    absolute_return_pct = round((current_value - invested) / invested * 100, 2) if invested else None

    return {
        "mode": mode,
        "ticker": stock_service.normalise_ticker(ticker),
        "start_date": start.isoformat(),
        "as_of": latest.isoformat(),
        "invested": round(invested, 2),
        "current_value": round(current_value, 2),
        "units": round(units, 4),
        "current_price": current_price,
        "absolute_return_pct": absolute_return_pct,
        "xirr_pct": xirr_pct,
    }


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
    return await _forecast_async(candles, min(horizon, 30), model)


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

    # Fetch the 2y history ONCE — the 3 forecast models used to each call
    # get_history(ticker, "2y") independently via asyncio.gather, and since
    # none of them had landed in cache yet, all 3 raced and fired 3 separate
    # IndianAPI requests for identical data instead of 1.
    # News/peer data are independent of each other and of the history fetch,
    # so they load concurrently — but must land BEFORE the AI calls below,
    # since analyse_stock/diagnose_health need the real sentiment/articles.
    hist_2y, peer_data, news_data = await asyncio.gather(
        stock_service.get_history(ticker, "2y"),
        peer_service.get_peer_comparison(ticker, quote.get("sector", ""), quote.get("industry")),
        news_service.get_news_and_sentiment(ticker, company),
    )
    candles_2y = hist_2y.get("candles", []) if "error" not in hist_2y else []
    peer_avg = peer_data.get("sector_avg", {})
    sentiment = news_data["sentiment"]
    articles  = news_data["articles"]

    async def _run_forecast(model: str) -> dict:
        if not candles_2y:
            return {"available": False, "reason": hist_2y.get("error", "No history available")}
        return await _forecast_async(candles_2y, 30, model)

    # AI + all 3 forecasts genuinely in parallel — forecasts run on a
    # thread pool (see _forecast_async) so they don't block each other or the
    # event loop.
    ai_analysis, health, fc_holt, fc_xgb, fc_lgbm = await asyncio.gather(
        ai_service.analyse_stock(quote, signals, hist, sentiment, peer_avg),
        ai_service.diagnose_health(quote, hist, sentiment, articles, peer_avg),
        _run_forecast("holt"),
        _run_forecast("xgboost"),
        _run_forecast("lgbm"),
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
    quote_failed = "error" in q and "current_price" not in q
    sector = q.get("sector", "")
    if quote_failed:
        # Live quote unavailable for this ticker (e.g. IndianAPI quota exhausted,
        # or a gap in their coverage) — fall back to the static sector map so
        # peer comparison can still render instead of an empty shell.
        sector = peer_service.static_sector_for_ticker(ticker) or ""
        if not sector:
            return {"peers": [], "sector_avg": {}, "partial": True, "error": q["error"]}
    result = await peer_service.get_peer_comparison(ticker, sector, q.get("industry"))
    if quote_failed:
        result["partial"] = True
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


@router.get("/{ticker}/financials")
async def stock_financials(ticker: str):
    """Screener-style financial statements: quarterly results, P&L, balance sheet, cash flow, ratios."""
    data = await financials_service.get_financials(ticker)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@router.get('/{ticker}/shareholding-history')
async def shareholding_history(ticker: str):
    """Quarterly shareholding pattern history (SEBI-mandated public disclosure) via IndianAPI."""
    return await shareholding_service.get_shareholding_history(ticker)


# ── IndianAPI-backed per-stock endpoints ──────────────────────────────────────

@router.get("/{ticker}/analyst-targets")
async def analyst_targets(ticker: str):
    """Analyst price targets and recommendations from IndianAPI."""
    from app.services.indianapi_service import get_stock_target_price
    bare = stock_service.bare_ticker(ticker)
    data = await get_stock_target_price(bare)
    if not data:
        raise HTTPException(status_code=404, detail="No analyst target data available")
    return data


@router.get("/{ticker}/analyst-forecasts")
async def analyst_forecasts(ticker: str):
    """Analyst revenue and EPS forecasts from IndianAPI."""
    from app.services.indianapi_service import get_stock_forecasts
    bare = stock_service.bare_ticker(ticker)
    data = await get_stock_forecasts(bare)
    if not data:
        raise HTTPException(status_code=404, detail="No forecast data available")
    return data


@router.get("/{ticker}/announcements")
async def stock_announcements(ticker: str):
    """Corporate announcements (BSE/NSE filings) from IndianAPI."""
    from app.services.indianapi_service import get_recent_announcements
    bare = stock_service.bare_ticker(ticker)
    data = await get_recent_announcements(bare)
    return data or []


@router.get("/{ticker}/corporate-actions")
async def stock_corporate_actions(ticker: str):
    """Dividends, splits, and bonus history from IndianAPI."""
    from app.services.indianapi_service import get_corporate_actions
    bare = stock_service.bare_ticker(ticker)
    return await get_corporate_actions(bare) or []


@router.get("/{ticker}/credit-ratings")
async def stock_credit_ratings(ticker: str):
    """CRISIL/ICRA/CARE credit ratings from IndianAPI."""
    from app.services.indianapi_service import get_credit_ratings
    bare = stock_service.bare_ticker(ticker)
    return await get_credit_ratings(bare) or []


@router.get("/{ticker}/annual-reports")
async def stock_annual_reports(ticker: str):
    """Annual report download links from IndianAPI."""
    from app.services.indianapi_service import get_annual_reports
    bare = stock_service.bare_ticker(ticker)
    return await get_annual_reports(bare) or []


@router.get("/{ticker}/concall-transcripts")
async def stock_concall_transcripts(ticker: str):
    """Raw earnings call transcript/PPT links from IndianAPI (distinct from the
    AI-synthesized /concall-summary, which is built from financials + news)."""
    from app.services.indianapi_service import get_concalls
    bare = stock_service.bare_ticker(ticker)
    return await get_concalls(bare) or []


@router.get("/{ticker}/logo")
async def stock_logo(ticker: str):
    """Company logo as a data: URI, from IndianAPI."""
    from app.services.indianapi_service import get_logo
    bare = stock_service.bare_ticker(ticker)
    logo = await get_logo(stock_name=bare)
    if not logo:
        raise HTTPException(status_code=404, detail="No logo available")
    return {"logo": logo}
