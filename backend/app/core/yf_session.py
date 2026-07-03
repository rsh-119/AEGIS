"""
yf_session.py — Shared curl_cffi session + circuit breaker for yfinance.

When Yahoo Finance rate-limits our IP, every yf.Ticker().history() call raises
YFRateLimitError immediately (< 1ms). Without a circuit breaker, every user
request retries the blocked call and piles up thread-pool slots.

The blocked-until timestamp is persisted to Redis so server restarts (--reload)
don't accidentally reset the circuit and immediately re-trigger the Yahoo ban.

Usage:
    from app.core.yf_session import YF_SESSION, yf_blocked, yf_on_rate_limit
"""
from __future__ import annotations

import logging
import time

from curl_cffi import requests as _curl

logger = logging.getLogger(__name__)

# 5-second connect+read timeout
YF_SESSION: _curl.Session = _curl.Session(timeout=5)

# ── IP-level rate-limit circuit breaker ───────────────────────────────────────
_YF_BACKOFF       = 86400        # 24 hours — Yahoo bans typically last 24-48h; 1h was too short and kept re-triggering
_yf_blocked_until: float = 0.0   # in-process fast path
_REDIS_KEY        = "yf:blocked_until"


def _redis_blocked_until() -> float:
    """Read persisted block timestamp from Redis (survives restarts)."""
    try:
        from app.core.cache import cache
        if cache._redis is None:
            return 0.0
        raw = cache._redis.get(_REDIS_KEY)   # returns bytes e.g. b'1751125662.12'
        return float(raw) if raw else 0.0
    except Exception:
        return 0.0


def yf_blocked() -> bool:
    global _yf_blocked_until
    now = time.time()
    if now < _yf_blocked_until:
        return True
    # In-process cache expired — check Redis (catches post-restart state)
    redis_until = _redis_blocked_until()
    if now < redis_until:
        _yf_blocked_until = redis_until   # restore in-process fast path
        return True
    return False


def yf_on_rate_limit() -> None:
    global _yf_blocked_until
    if not yf_blocked():
        until = time.time() + _YF_BACKOFF
        _yf_blocked_until = until
        # Persist to Redis so server restarts don't clear the circuit
        try:
            from app.core.cache import cache
            cache._redis.set(_REDIS_KEY, until, ex=_YF_BACKOFF + 60)
        except Exception:
            pass
        logger.warning("yfinance rate-limited — circuit open for %ds (1 hour)", _YF_BACKOFF)
