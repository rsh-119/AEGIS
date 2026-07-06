"""
cache.py — Unified Redis-first cache with transparent in-memory fallback.

Architecture:
  L1  Redis (if available)  — survives restarts, shared across workers
  L2  In-memory dict        — automatic fallback, zero config required

TTL map (seconds):
  prices    5 min   live tick + quote data
  history   30 min  OHLCV candles
  market    10 min  indices, movers, market overview
  sector    30 min  sector aggregates
  peers     30 min  peer comparison + ratios
  mf_nav    1 h     NAV data (published once per day)
  mf_list   24 h    AMFI full fund list
  etf       10 min  ETF live prices
  nifty50   1 h     benchmark history
  ai        24 h     AI analysis (also in PostgreSQL ai_cache)
  forecast  30 min  ML forecast results
  search    10 min  search autocomplete results

Usage:
    from app.core.cache import cache

    # Get
    result = cache.get("quote:TCS.NS")

    # Set with category TTL
    cache.set("quote:TCS.NS", data, "prices")

    # Invalidate
    cache.delete("quote:TCS.NS")
    cache.flush("quote:")          # all keys starting with prefix
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── TTL registry (seconds) ────────────────────────────────────────────────────
TTL: dict[str, int] = {
    # NOTE: quote/history/sector/peers/etf TTLs are intentionally generous —
    # IndianAPI is the sole live-data source with a metered monthly quota
    # (~10k requests/month), so every cache hit avoided is quota saved.
    #
    # "prices" bumped from 10min to 1h: it caches the /stock + /get_stock_data
    # bundle (get_stock, get_quote_bundle, stock_service.get_quote), but the
    # stock page's *displayed* live price actually comes from a separate WS/SSE
    # stream (useRealtimePrice), not this snapshot — so the company profile /
    # shareholding / peer data bundled in here doesn't need 10-min freshness.
    "prices":    3600,    # 1 h     — /stock + /get_stock_data bundle
    "history":   21600,   # 6 h     — OHLCV candles are daily granularity anyway
    "market":    1800,    # 30 min  — indices/movers, only refetched during NSE trading hours
    "sector":    21600,   # 6 h
    "peers":     21600,   # 6 h     — peer fundamentals barely move intraday
    "mf_nav":    86400,   # 24 h    — NAV is published once per day by AMFI, never changes intraday
    "mf_list":   86400,   # 24 h
    "etf":       3600,    # 1 h     — ETF prices now sourced from IndianAPI (metered)
    "nifty50":   21600,   # 6 h
    "ai":        86400,   # 24 h    — one AI analysis per day per ticker
    "forecast":  3600,    # 1 h     — ML forecast stable intraday
    "search":    900,     # 15 min  — autocomplete results
    "analyst":   86400,   # 24 h    — analyst targets/forecasts update weekly at most
    "corporate": 86400,   # 24 h    — dividends/splits announced once per event
    "filing":    14400,   # 4 h     — BSE/NSE announcements during trading hours
    "news":      1800,    # 30 min  — company news, quota-metered on IndianAPI
    "overview":  1800,    # 30 min  — market overview, only refetched during NSE trading hours
    "market_snapshot": 432000,  # 5 days — last-known-good indices/movers, served as-is
                                 # outside trading hours (weekends/holidays included)
    "logo":      604800,  # 7 days  — company/fund logos essentially never change
}

# ── In-memory fallback ────────────────────────────────────────────────────────
class _MemStore:
    """Thread-safe dict with per-entry TTL. O(1) get/set."""

    def __init__(self) -> None:
        # key → (stored_at, ttl_seconds, value)
        self._d: dict[str, tuple[float, int, Any]] = {}

    def get(self, key: str) -> Any | None:
        v = self._d.get(key)
        if v is None:
            return None
        if time.time() - v[0] >= v[1]:
            del self._d[key]
            return None
        return v[2]

    def set(self, key: str, val: Any, ttl: int) -> None:
        self._d[key] = (time.time(), ttl, val)

    def delete(self, key: str) -> None:
        self._d.pop(key, None)

    def flush(self, prefix: str = "") -> None:
        if not prefix:
            self._d.clear()
            return
        for k in [k for k in self._d if k.startswith(prefix)]:
            del self._d[k]

    def size(self) -> int:
        return len(self._d)


# ── Main cache class ──────────────────────────────────────────────────────────
class Cache:
    """
    Redis-first cache with automatic in-memory fallback.

    The Redis client (redis-py) is thread-safe — safe to call from
    multiple threads / asyncio thread-pool executors simultaneously.
    """

    def __init__(self) -> None:
        self._redis: Any = None
        self._mem = _MemStore()

    # ── Initialisation ────────────────────────────────────────────────────────
    def connect(self, url: str = "redis://localhost:6379") -> None:
        """Try to connect to Redis. Falls back to memory silently."""
        try:
            import redis as _r  # type: ignore
            client = _r.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False,
            )
            client.ping()
            self._redis = client
            logger.info("Cache: Redis connected — %s", url)
        except Exception as exc:
            logger.warning("Cache: Redis unavailable (%s) — using in-memory fallback", exc)

    # ── Core ops ──────────────────────────────────────────────────────────────
    def get(self, key: str) -> Any | None:
        """Return cached value, or None on miss / expiry."""
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw is not None:
                    return json.loads(raw)
            except Exception as exc:
                logger.debug("Cache.get Redis error: %s", exc)
        return self._mem.get(key)

    def set(self, key: str, val: Any, category: str = "market") -> None:
        """Store value with TTL derived from category name."""
        ttl = TTL.get(category, 600)
        packed = json.dumps(val, default=str)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, packed)
                return
            except Exception as exc:
                logger.debug("Cache.set Redis error: %s", exc)
        self._mem.set(key, val, ttl)

    def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        self._mem.delete(key)

    def flush(self, prefix: str = "") -> None:
        """Delete all keys matching prefix (empty = entire cache)."""
        if self._redis is not None:
            try:
                pattern = f"{prefix}*" if prefix else "*"
                keys = self._redis.keys(pattern)
                if keys:
                    self._redis.delete(*keys)
                return
            except Exception as exc:
                logger.debug("Cache.flush Redis error: %s", exc)
        self._mem.flush(prefix)

    # ── Introspection ─────────────────────────────────────────────────────────
    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def stats(self) -> dict:
        info: dict[str, Any] = {"backend": self.backend}
        if self._redis is not None:
            try:
                r = self._redis.info("stats")
                info["redis_hits"]   = r.get("keyspace_hits", 0)
                info["redis_misses"] = r.get("keyspace_misses", 0)
                info["redis_keys"]   = self._redis.dbsize()
            except Exception:
                pass
        else:
            info["mem_keys"] = self._mem.size()
        return info


# ── Module singleton ──────────────────────────────────────────────────────────
cache = Cache()
