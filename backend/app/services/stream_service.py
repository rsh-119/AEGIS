"""
stream_service.py — Real-time price stream for Aegis.

Architecture:
  - PriceCache      : thread-safe in-memory store for latest tick per ticker
                      (wraps the shared Redis-backed cache where available)
  - ExchangeStream  : async background worker that pulls live prices from Sugra
                      on a configurable interval and publishes to PriceCache
  - ConnectionMgr   : WebSocket subscription manager with per-ticker fan-out

WebSocket protocol (JSON text frames):

  Client → server:
    { "action": "subscribe",   "tickers": ["SBIN.NS", "INFY.NS"] }
    { "action": "unsubscribe", "tickers": ["SBIN.NS"] }

  Server → client (on each tick):
    { "type": "tick", "ticker": "SBIN.NS", "price": 834.55,
      "change_pct": -0.42, "volume": 1234567, "ts": 1719392340.123 }
    { "type": "snapshot", "data": { "SBIN.NS": {...}, ... } }   # on subscribe
    { "type": "error", "message": "..." }
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
from fastapi import WebSocket, WebSocketDisconnect

from app.core.cache import cache
from app.core.config import get_settings
from app.core.yf_session import YF_SESSION, yf_blocked, yf_on_rate_limit
from yfinance.exceptions import YFRateLimitError

_price_pool = ThreadPoolExecutor(max_workers=24, thread_name_prefix="price-stream")

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Tickers actively streamed ─────────────────────────────────────────────────
_DEFAULT_TICKERS: list[str] = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "BAJFINANCE.NS", "KOTAKBANK.NS", "LT.NS",
    "AXISBANK.NS", "WIPRO.NS", "HINDUNILVR.NS", "ITC.NS", "TATAMOTORS.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "NTPC.NS", "POWERGRID.NS", "ADANIPORTS.NS",
]

_STREAM_INTERVAL: float = 15.0  # seconds between full tick refreshes (one batch Sugra call)


# ── Thread-safe price cache ───────────────────────────────────────────────────
class PriceCache:
    """
    Latest tick per ticker — ultra-fast reads for the HTTP fallback endpoint.

    Uses the shared Redis-backed cache as L1 (survives worker restarts,
    shareable across replicas) and an in-memory dict as L2 for zero-latency
    reads within the same process.
    """

    _CACHE_CATEGORY = "prices"

    def __init__(self) -> None:
        self._mem: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, ticker: str) -> dict | None:
        # L1: in-process memory (zero latency)
        with self._lock:
            if ticker in self._mem:
                return self._mem[ticker]
        # L2: Redis / shared cache
        return cache.get(f"stream:tick:{ticker}")

    def put(self, ticker: str, tick: dict) -> None:
        with self._lock:
            self._mem[ticker] = tick
        cache.set(f"stream:tick:{ticker}", tick, self._CACHE_CATEGORY)

    def snapshot(self, tickers: list[str]) -> dict[str, dict]:
        return {t: d for t in tickers if (d := self.get(t)) is not None}


price_cache = PriceCache()


# ── WebSocket connection manager ──────────────────────────────────────────────
class ConnectionManager:
    """
    Manages active WebSocket connections and per-ticker subscriptions.

    Sends ONE batched frame per client per loop cycle (not N individual frames).
    Applies delta filtering — skips tickers whose price hasn't moved since last send.
    """

    def __init__(self) -> None:
        self._subs: dict[WebSocket, set[str]] = {}
        # tracks last-sent price per client per ticker for delta filtering
        self._last_prices: dict[WebSocket, dict[str, float]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._subs[ws] = set()
            self._last_prices[ws] = {}
        logger.info("WS client connected — total=%d", len(self._subs))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._subs.pop(ws, None)
            self._last_prices.pop(ws, None)
        logger.info("WS client disconnected — total=%d", len(self._subs))

    async def subscribe(self, ws: WebSocket, tickers: list[str]) -> None:
        """Add tickers to this client's subscription set and send a snapshot."""
        async with self._lock:
            if ws not in self._subs:
                return
            self._subs[ws].update(tickers)

        snap = price_cache.snapshot(tickers)
        if snap:
            await self._send(ws, {"type": "snapshot", "data": snap})

    async def unsubscribe(self, ws: WebSocket, tickers: list[str]) -> None:
        async with self._lock:
            if ws in self._subs:
                self._subs[ws].difference_update(tickers)

    async def broadcast_batch(self, tick_map: dict[str, dict]) -> None:
        """
        Fan-out a full tick_map to all clients in ONE frame each.

        Delta filtering: a tick is included only if price moved ≥ 0.01%
        from what was last sent to that client. This prevents re-serialising
        static data on every loop cycle.
        """
        async with self._lock:
            clients = list(self._subs.items())
            last_prices_snapshot = {ws: dict(lp) for ws, lp in self._last_prices.items()}

        dead: list[WebSocket] = []

        for ws, subs in clients:
            last = last_prices_snapshot.get(ws, {})
            relevant: dict[str, dict] = {}

            for ticker in subs:
                if ticker not in tick_map:
                    continue
                tick  = tick_map[ticker]
                price = tick.get("price") or 0
                prev  = last.get(ticker)
                if prev is None or price == 0 or abs(price - prev) / (prev or 1) >= 0.0001:
                    relevant[ticker] = tick

            if not relevant:
                continue

            try:
                await ws.send_text(json.dumps({"type": "batch", "ticks": relevant}, default=str))
                async with self._lock:
                    if ws in self._last_prices:
                        self._last_prices[ws].update(
                            {t: d.get("price", 0) for t, d in relevant.items()}
                        )
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._subs.pop(ws, None)
                    self._last_prices.pop(ws, None)

    async def _send(self, ws: WebSocket, data: Any) -> None:
        try:
            await ws.send_text(json.dumps(data, default=str))
        except Exception:
            pass

    @property
    def active_tickers(self) -> set[str]:
        result: set[str] = set()
        for subs in self._subs.values():
            result |= subs
        return result


connection_mgr = ConnectionManager()


# ── Exchange stream worker ────────────────────────────────────────────────────
class ExchangeStream:
    """
    Background asyncio task that fetches live prices from Sugra/yfinance
    and publishes ticks to PriceCache + ConnectionManager.

    On each cycle it fetches the union of:
      - All tickers currently subscribed via WebSocket
      - The default always-on tickers (so the HTTP fallback always has data)
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._loop(), name="exchange-stream")
            logger.info("ExchangeStream started")

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    # Tickers skipped due to repeated 404/bad-data — time-based, not permanent.
    # key=ticker, value=timestamp when the skip expires.
    _skip_until: dict[str, float] = {}
    _fail_counts: dict[str, int] = {}
    _MAX_FAILS   = 10          # consecutive per-ticker misses before skipping
    _SKIP_SECS   = 300         # skip duration: 5 minutes, then auto-retry

    def _is_skipped(self, ticker: str) -> bool:
        exp = self._skip_until.get(ticker)
        if exp is None:
            return False
        if time.time() > exp:
            # Expired — remove and allow retry
            del self._skip_until[ticker]
            self._fail_counts.pop(ticker, None)
            return False
        return True

    async def _batch_fetch(self, tickers: list[str]) -> dict[str, dict]:
        """
        Parallel yfinance history(period='2d') for all stream tickers.
        Runs in a dedicated thread pool — no external API credits consumed.
        """
        loop = asyncio.get_event_loop()

        def _fetch_one(sym: str) -> tuple[str, dict] | None:
            if yf_blocked():
                return None
            try:
                hist = yf.Ticker(sym, session=YF_SESSION).history(period="2d")
                if hist.empty:
                    return None
                price = float(hist["Close"].iloc[-1])
                prev  = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else price
                vol   = int(hist["Volume"].iloc[-1]) if "Volume" in hist.columns else 0
                chg   = (price - prev) / prev * 100 if prev else 0
                if price > 0:
                    return (sym, {
                        "price":      round(price, 2),
                        "change_pct": round(chg, 2),
                        "volume":     vol,
                        "ts":         time.time(),
                    })
            except YFRateLimitError:
                yf_on_rate_limit()
                return None
            except Exception:
                return None

        async def _timed_fetch(sym: str):
            try:
                return await asyncio.wait_for(
                    loop.run_in_executor(_price_pool, _fetch_one, sym),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                return None

        results = await asyncio.gather(*[_timed_fetch(t) for t in tickers],
                                       return_exceptions=True)

        tick_map: dict[str, dict] = {}
        for r in results:
            if isinstance(r, tuple):
                sym, tick = r
                tick_map[sym] = tick
                self._fail_counts.pop(sym, None)

        return tick_map

    async def _loop(self) -> None:
        while self._running:
            t0 = time.monotonic()

            watch = [
                t for t in (set(_DEFAULT_TICKERS) | connection_mgr.active_tickers)
                if not self._is_skipped(t)
            ]

            if watch:
                tick_map = await self._batch_fetch(watch)

                # Write to cache first (HTTP fallback readers see it immediately)
                for ticker, tick in tick_map.items():
                    price_cache.put(ticker, tick)

                # One batched frame per WS client (not N individual frames)
                if tick_map:
                    await connection_mgr.broadcast_batch(tick_map)

                if tick_map:
                    # Partial success — count per-ticker misses (specific bad tickers)
                    for ticker in watch:
                        if ticker not in tick_map:
                            count = self._fail_counts.get(ticker, 0) + 1
                            self._fail_counts[ticker] = count
                            if count >= self._MAX_FAILS:
                                self._skip_until[ticker] = time.time() + self._SKIP_SECS
                                logger.warning(
                                    "stream: cooling off %s for %ds after %d misses",
                                    ticker, self._SKIP_SECS, count,
                                )
                # else: total batch failure (circuit open / network) — don't penalise
                # individual tickers; they'll be retried next cycle automatically.

            elapsed = time.monotonic() - t0
            sleep_for = max(1.0, _STREAM_INTERVAL - elapsed)
            await asyncio.sleep(sleep_for)


exchange_stream = ExchangeStream()
