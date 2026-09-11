"""
http_cache.py — Add Cache-Control + stale-while-revalidate headers to API responses.

Rules (matched longest-prefix first):
  /api/stream/…      → no-store          (live SSE/WS; never cache)
  /api/stocks/search → max-age=300       (autocomplete; 5 min browser cache)
  /api/stocks/*/quote → max-age=60, swr=60   (live price; 1 min + 1 min stale ok)
  /api/stocks/*/history → max-age=900,swr=900 (15 min candles; 15 min stale ok)
  /api/stocks/…      → max-age=300,swr=300 (other stock data)
  /api/market/…      → max-age=300,swr=300 (indices/movers)
  /api/mf/…          → max-age=1800,swr=1800 (NAV; 30 min)
  /api/sector/…      → max-age=900,swr=900
  /api/peers/…       → max-age=900,swr=900
  /api/portfolio/…   → no-store          (user-specific; never cache on proxy)
  /api/watchlist/…   → no-store
  /api/alerts/…      → no-store          (user-specific)
  /api/auth/…        → no-store          (user-specific; includes /me)
  /api/admin/…       → no-store          (admin-only data)
  /api/ai/…          → no-store          (session-tied LLM responses)
  /api/chat…         → no-store
  /api/documents/…   → no-store          (uploaded document content)
  anything else      → no-store          (fail closed; see _DEFAULT below)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# (path_prefix, max_age_seconds, stale_while_revalidate_seconds)
# None swr = no stale-while-revalidate
_RULES: list[tuple[str, int, int | None]] = [
    # ── Per-user / privileged: never storable by a shared cache ──────────────
    ("/api/stream",          0,    None),   # no-store
    ("/api/portfolio",       0,    None),   # no-store
    ("/api/watchlist",       0,    None),   # no-store
    ("/api/alerts",          0,    None),   # no-store
    ("/api/auth",            0,    None),   # no-store — /me carries email, avatar
    ("/api/admin",           0,    None),   # no-store — full user listing
    ("/api/ai",              0,    None),   # no-store
    ("/api/chat",            0,    None),   # no-store
    ("/api/documents",       0,    None),   # no-store — uploaded document text
    # ── Public market data: safe to cache in shared caches ───────────────────
    ("/api/stocks/search",   300,  300),
    ("/api/stocks/batch",    60,   60),
    ("/api/stocks/",         300,  300),
    ("/api/market",          300,  300),
    ("/api/mf",              1800, 1800),
    ("/api/sector",          900,  900),
    ("/api/peers",           900,  900),
]

# Unmatched paths get no-store rather than a public max-age. The previous
# default (public, max-age=60) applied to every route with no rule above —
# which included /api/auth/me, /api/alerts and /api/admin/*, authorising any
# shared cache between the user and the app to store one user's profile,
# alerts or the full admin user listing and replay it to the next requester.
# A new private route must not become publicly cacheable just by existing, so
# the default fails closed and public caching is opt-in via _RULES.
_DEFAULT: tuple[int, int | None] = (0, None)


def _get_rule(path: str) -> tuple[int, int | None]:
    for prefix, max_age, swr in _RULES:
        if path.startswith(prefix):
            return max_age, swr
    return _DEFAULT


class HttpCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Only cache GET/HEAD 2xx responses to /api/* paths
        if request.method not in ("GET", "HEAD"):
            return response
        if not request.url.path.startswith("/api/"):
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response

        # Don't override if route already set Cache-Control (e.g. SSE endpoint)
        if "cache-control" in response.headers:
            return response

        max_age, swr = _get_rule(request.url.path)

        if max_age == 0:
            response.headers["Cache-Control"] = "no-store"
        else:
            parts = [f"public", f"max-age={max_age}"]
            if swr:
                parts.append(f"stale-while-revalidate={swr}")
            response.headers["Cache-Control"] = ", ".join(parts)

        return response
