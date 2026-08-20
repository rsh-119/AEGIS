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
AUTH_LIMIT    = "5/15minute"   # brute-force/credential-stuffing guard — login + register only


def user_or_ip_key(request: Request) -> str:
    """Rate-limit key: authenticated user_id if a valid bearer token or
    access cookie is present, else fall back to remote IP. Used for AI
    endpoints where quota should be per-account, not shared across a
    NAT/office IP.

    Checks the Authorization header first (script/API clients), then the
    aegis_access cookie (browser clients) — auth moved to httpOnly cookies,
    so header-only lookup would silently degrade every browser user to
    per-IP quota instead of per-account."""
    from app.core.auth import ACCESS_COOKIE_NAME, decode_token

    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get(ACCESS_COOKIE_NAME)
    if token:
        try:
            return f"user:{decode_token(token, expected_type='access')}"
        except Exception:
            pass
    return get_remote_address(request)


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
