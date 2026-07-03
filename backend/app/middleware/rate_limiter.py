"""
Rate limiting using slowapi (already in requirements.txt).

Default limits:
  General API:  120 req/min per IP
  AI endpoints: 10  req/min per IP  (expensive GPU/LLM calls)
  Stock data:   60  req/min per IP
  Search:       30  req/min per IP

Apply per-route overrides with the @limiter.limit("...") decorator.
SlowAPIMiddleware is added to the FastAPI app in main.py.

Error handler returns JSON (not HTML) on 429:
  {"error": "Rate limit exceeded", "retry_after": 60}
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    headers_enabled=True,       # X-RateLimit-* response headers
    swallow_errors=False,
)

# Convenience constants — import these in routers
AI_LIMIT      = "10/minute"
STOCK_LIMIT   = "60/minute"
SEARCH_LIMIT  = "30/minute"
GENERAL_LIMIT = "120/minute"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return JSON 429 instead of the default HTML page."""
    return JSONResponse(
        status_code=429,
        content={
            "error":       "Rate limit exceeded",
            "detail":      str(exc.detail),
            "retry_after": 60,
        },
        headers={
            "Retry-After":          "60",
            "X-RateLimit-Limit":    str(exc.detail),
            "X-RateLimit-Remaining": "0",
        },
    )
