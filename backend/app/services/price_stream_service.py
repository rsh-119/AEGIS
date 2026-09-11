"""
price_stream_service.py — in-process fan-out for live stock price SSE streams.

Replaces per-client 30s polling of /api/stocks/{ticker}/quote (see
frontend/lib/useRealtimePrice.ts) with a single shared poll loop per actively-
watched ticker, feeding every connected SSE client from one place.

Deliberately NOT Redis Pub/Sub: production runs single-worker on Render's
free tier (see stocks.py's WEB_CONCURRENCY=1 comment), so there is only one
process to fan out from in the first place — a long-lived blocking pub/sub
subscriber against Upstash (connection-limited, and cache.py's Redis client
is the sync `redis-py`, not `redis.asyncio`) would add real cost for no
benefit here. Revisit only if Aegis ever runs more than one backend instance.

Deliberately does NOT bypass stock_service.get_quote()'s existing 1h cache:
that cache is what already caps upstream IndianAPI load to ~1 call/hour/
ticker regardless of how many clients are watching. Polling the *cache* every
few seconds is effectively free (in-memory/Redis GET), so this loop does that
and only pushes a tick to subscribers when the cached value actually changes
— giving instant push the moment the shared cache does refresh, without
increasing upstream cost over what today's polling already causes.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5     # seconds — cheap cache reads, not upstream calls
_QUEUE_MAXSIZE = 8     # a slow consumer drops ticks rather than backing up the poll loop

# Cap on how many distinct tickers may have a live poll loop at once.
# /api/stocks/{ticker}/stream is anonymous and takes an arbitrary ticker
# string, and each new value starts its own long-lived task that calls
# get_quote() every _POLL_INTERVAL seconds for as long as the socket stays
# open. On a cache miss that reaches IndianAPI, whose monthly quota is the
# scarcest resource this app has — so without a cap one client holding open
# N sockets against N invented symbols pins N background tasks and N upstream
# fetch loops. 200 is far above any real fan-out (the NIFTY 50 plus every
# stock page a user might have open) and far below a level that hurts.
MAX_STREAMED_TICKERS = 200


class StreamCapacityExceeded(Exception):
    """Raised by subscribe() when MAX_STREAMED_TICKERS distinct tickers are
    already being polled. Callers should surface 503, not fail silently."""


class PriceStreamHub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._last: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    async def subscribe(self, ticker: str) -> asyncio.Queue:
        """Register a new SSE client for `ticker`, starting its poll loop if
        this is the first subscriber. Returns a queue the caller reads ticks
        from; must be paired with unsubscribe() (e.g. in a finally block)."""
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        async with self._lock:
            is_new_ticker = ticker not in self._subscribers
            if is_new_ticker and len(self._tasks) >= MAX_STREAMED_TICKERS:
                logger.warning(
                    "price_stream: refusing %s — already polling %d tickers (cap %d)",
                    ticker, len(self._tasks), MAX_STREAMED_TICKERS,
                )
                raise StreamCapacityExceeded(ticker)

            subs = self._subscribers.setdefault(ticker, set())
            subs.add(q)
            if ticker not in self._tasks:
                self._tasks[ticker] = asyncio.create_task(
                    self._poll_loop(ticker), name=f"price-stream-{ticker}"
                )
                logger.info("price_stream: started poll loop for %s", ticker)

        last = self._last.get(ticker)
        if last is not None:
            q.put_nowait(last)   # fast first paint from whatever we already have cached
        return q

    async def unsubscribe(self, ticker: str, q: asyncio.Queue) -> None:
        """Drop a client. Stops the poll loop once nobody's left watching
        `ticker`, so idle tickers don't keep polling forever."""
        async with self._lock:
            subs = self._subscribers.get(ticker)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                del self._subscribers[ticker]
                task = self._tasks.pop(ticker, None)
                if task and not task.done():
                    task.cancel()
                self._last.pop(ticker, None)
                logger.info("price_stream: stopped poll loop for %s (no subscribers left)", ticker)

    def shutdown(self) -> None:
        """Cancel every active poll loop — called from main.py's lifespan on
        app shutdown so nothing lingers past process exit."""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._subscribers.clear()
        self._last.clear()

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _poll_loop(self, ticker: str) -> None:
        from app.services import stock_service   # local import avoids a startup import cycle

        try:
            while True:
                try:
                    data = await stock_service.get_quote(ticker)
                    if "error" not in data and data.get("current_price") is not None:
                        tick = {
                            "price": data.get("current_price"),
                            "change_pct": data.get("change_pct"),
                            "volume": data.get("volume"),
                            "ts": data.get("fetched_at") or int(time.time()),
                        }
                        prev = self._last.get(ticker)
                        if prev is None or prev["price"] != tick["price"] or prev["ts"] != tick["ts"]:
                            self._last[ticker] = tick
                            async with self._lock:
                                subs = list(self._subscribers.get(ticker, ()))
                            for q in subs:
                                if q.full():
                                    continue
                                q.put_nowait(tick)
                except Exception as exc:
                    logger.warning("price_stream: poll failed for %s — %s", ticker, exc)

                await asyncio.sleep(_POLL_INTERVAL)
        except asyncio.CancelledError:
            pass


# Module-level singleton, mirroring home_refresh_service.py's pattern.
price_stream_hub = PriceStreamHub()
