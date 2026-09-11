"""
prewarm_service.py — background task that keeps AI Summary/Company Health
warm for a small set of popular tickers, so a real visitor rarely hits the
cold-cache path that runs the full Groq/OpenRouter/NVIDIA waterfall live.

Same rationale as home_refresh_service.py's HomeRefreshTask (a simple
asyncio loop, checked cheaply and often, doing real work rarely) — this is
a sibling task, not a replacement, and follows the same tick-counting shape.

Why this exists: analyse_stock()/diagnose_health() (ai_service.py) cache
their result per ticker for _AI_CACHE_TTL_HOURS (20h). The *first* real
visitor to a given ticker after that TTL lapses pays the full LLM cost live
— everyone else in that window gets an instant cache hit. This task
absorbs that first-visitor cost on a schedule instead, for the handful of
tickers most likely to actually be viewed, so it happens in the
background rather than in front of a real user.

Deliberately small and slow, not a general cache-warmer for every stock in
the market:
  - POPULAR_TICKERS is a short, hand-picked list of large, broadly-followed
    NSE names (same tickers as the free-form chat's _NAME_TO_TICKER map in
    routers/chat.py, since those are this app's own idea of "commonly
    asked about") — not an attempt to cover the whole market, and not
    derived from any real usage/popularity data, since this app doesn't
    track page views anywhere yet. Adjust this list directly if it stops
    matching what your users actually look up.
  - Tickers are refreshed one at a time with a delay between each
    (_TICKER_GAP), not all at once — a burst of ~2 dozen concurrent LLM
    calls (2 per ticker: analysis + health) risks tripping Groq's free-tier
    per-key rate limit for real user traffic happening at the same moment.
  - analyse_stock()/diagnose_health() already check their own cache first,
    so re-running this over an already-warm ticker is a cheap no-op (one
    Redis/Postgres read each) — safe to run on a fixed interval rather than
    needing to track each ticker's individual TTL expiry precisely.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_CHECK_INTERVAL = 600   # 10 min — cheap tick, same cadence as HomeRefreshTask
_PASS_TICKS     = 114   # ~19h between passes — just under the 20h cache TTL
_TICKER_GAP     = 8     # seconds between tickers within one pass

POPULAR_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "ITC.NS", "HINDUNILVR.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "MARUTI.NS",
]


class AIPrewarmTask:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="ai-prewarm")
        logger.info(
            "AIPrewarmTask started — %d tickers, ~%dh between passes",
            len(POPULAR_TICKERS), _PASS_TICKS * _CHECK_INTERVAL // 3600,
        )

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("AIPrewarmTask stopped")

    async def _loop(self) -> None:
        # Run one pass shortly after startup (staggered well behind
        # main.py's own _prewarm(), which already runs at the 3s mark) so a
        # freshly-deployed instance doesn't start every popular ticker's
        # cache cold, then settle into the regular interval.
        await asyncio.sleep(30)
        tick = 0
        while self._running:
            if tick % _PASS_TICKS == 0:
                await self._run_pass()
            tick += 1
            await asyncio.sleep(_CHECK_INTERVAL)

    async def _run_pass(self) -> None:
        if not (settings.groq_api_key or settings.nvidia_api_key):
            return   # no AI configured at all — nothing to warm
        from app.services import ai_service

        logger.info("AI prewarm: starting pass over %d tickers", len(POPULAR_TICKERS))
        warmed = 0
        for ticker in POPULAR_TICKERS:
            if not self._running:
                break
            try:
                fetched = await ai_service.fetch_ai_context(ticker)
                if fetched is None:
                    logger.warning("AI prewarm: %s — no quote available, skipped", ticker)
                    continue
                quote, hist, signals, sentiment, articles, peer_avg = fetched
                await asyncio.gather(
                    ai_service.analyse_stock(quote, signals, hist, sentiment, peer_avg),
                    ai_service.diagnose_health(quote, hist, sentiment, articles, peer_avg),
                )
                warmed += 1
            except Exception:
                # Best-effort — one ticker's failure (a transient provider
                # error, a bad quote) must never stop the rest of the pass.
                logger.exception("AI prewarm: %s failed", ticker)
            await asyncio.sleep(_TICKER_GAP)
        logger.info("AI prewarm: pass done — %d/%d tickers warmed", warmed, len(POPULAR_TICKERS))


ai_prewarm_task = AIPrewarmTask()
