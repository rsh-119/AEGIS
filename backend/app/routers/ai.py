"""/api/ai/* — grounded Q&A endpoint."""

import asyncio
import logging
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.core import groq_circuit_breaker
from app.middleware.rate_limiter import AI_LIMIT, limiter, user_or_ip_key
from app.schemas import AskRequest
from app.services import ai_service, bulk_deals_service, news_service, stock_service

router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger(__name__)

_STREAM_PEEK_TIMEOUT_SECONDS = 1.5  # was a bare inline literal before the circuit breaker


async def _gather_ask_context(
    ticker: str,
) -> tuple[dict | None, dict | None, list[dict], list[dict]]:
    """Single-pass fetch for Ask AI — quote, history, and bulk deals run in
    parallel (Stage 1, none of the three depend on each other); news depends
    on the company name resolved from `quote`, so it runs after (Stage 2).
    Returns (quote, hist, articles, bulk_deals) — quote is None on a
    resolution error (bad/unknown ticker)."""
    quote, hist, all_deals = await asyncio.gather(
        stock_service.get_quote(ticker),
        stock_service.get_history(ticker, "3mo"),
        bulk_deals_service.get_bulk_deals(limit=75),
    )
    if "error" in quote:
        return None, None, [], []

    bare = ticker.replace(".NS", "").replace(".BO", "")
    bulk_deals = [d for d in all_deals if d.get("symbol") == bare][:10]

    company = quote.get("company_name")
    news_data = await news_service.get_news_and_sentiment(ticker, company)
    articles = news_data.get("articles", [])

    return quote, hist, articles, bulk_deals


@router.post("/ask")
@limiter.limit(AI_LIMIT, key_func=user_or_ip_key)
async def ask(request: Request, response: Response, body: AskRequest):
    quote = hist = bulk_deals = None
    articles: list[dict] = []
    if body.ticker:
        t0 = time.monotonic()
        quote, hist, articles, bulk_deals = await _gather_ask_context(body.ticker)
        logger.info(
            "ask pre_fetch_ms=%.0f ticker=%s", (time.monotonic() - t0) * 1000, body.ticker
        )

    result = ai_service.public_result(
        await ai_service.answer(body.question, quote, hist, articles, bulk_deals)
    )
    return {"question": body.question, **result}


@router.post("/ask-stream")
@limiter.limit(AI_LIMIT, key_func=user_or_ip_key)
async def ask_stream(request: Request, response: Response, body: AskRequest):
    """Streaming counterpart to /ask. Single-provider (Groq) — see
    ai_service.stream_answer() for why this deliberately forgoes the
    validate+repair+multi-provider waterfall that /ask uses.

    Peek-before-commit: we start consuming the generator and wait up to 1.5s
    for a first chunk *before* committing to a StreamingResponse. HTTP
    headers can't be un-sent once a streaming response starts, so this is
    the only place a fallback to the non-streaming waterfall can happen —
    if nothing arrives in time (or the stream errors immediately), we fall
    through to ai_service.answer() using the same already-fetched context
    and return a normal JSON response instead.

    Content-Type is text/event-stream per spec, but the payload is raw
    decoded text chunks (no "data: " SSE framing) — the frontend reads this
    via fetch + ReadableStream, not the native EventSource API, so framing
    would only add parsing overhead for no benefit.

    Circuit breaker (app.core.groq_circuit_breaker): after 3 peek failures
    within 60s, skip the 1.5s wait_for entirely for 5 minutes and go
    straight to the waterfall — same fallback outcome, no wasted timeout on
    every request during a known Groq outage. Doesn't and can't help with a
    stream failing *after* the first chunk (headers already sent by then) —
    stream_answer() has no internal try/except by deliberate design (see its
    docstring); that failure mode is out of reach for anything sitting here.
    """
    quote = hist = bulk_deals = None
    articles: list[dict] = []
    if body.ticker:
        t0 = time.monotonic()
        quote, hist, articles, bulk_deals = await _gather_ask_context(body.ticker)
        logger.info(
            "ask-stream pre_fetch_ms=%.0f ticker=%s",
            (time.monotonic() - t0) * 1000, body.ticker,
        )

    if groq_circuit_breaker.is_open():
        logger.info("ask-stream: circuit open, skipping peek (ticker=%s)", body.ticker)
        result = ai_service.public_result(
            await ai_service.answer(body.question, quote, hist, articles, bulk_deals)
        )
        return JSONResponse({"question": body.question, **result})

    gen = ai_service.stream_answer(body.question, quote, hist, articles, bulk_deals)

    try:
        first_chunk = await asyncio.wait_for(anext(gen), timeout=_STREAM_PEEK_TIMEOUT_SECONDS)
    except Exception as e:
        groq_circuit_breaker.record_failure()
        logger.warning(
            "ask-stream: falling back to non-streaming waterfall (ticker=%s): %s",
            body.ticker, e,
        )
        result = ai_service.public_result(
            await ai_service.answer(body.question, quote, hist, articles, bulk_deals)
        )
        return JSONResponse({"question": body.question, **result})

    groq_circuit_breaker.record_success()

    async def _emit():
        yield first_chunk
        async for chunk in gen:
            yield chunk

    return StreamingResponse(_emit(), media_type="text/event-stream")


@router.get("/diagnostics")
async def diagnostics():
    """Waterfall observability — which provider is actually serving AI calls,
    average latency, and how often schema validation needed a repair retry.
    Process-lifetime in-memory counters, not persisted across restarts."""
    return {
        "providers": ai_service.get_provider_stats(),
        "schema_repairs": ai_service.get_repair_counts(),
    }
