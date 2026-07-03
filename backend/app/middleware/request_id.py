"""
RequestID + timing middleware.

Per request:
  1. Reads X-Request-ID from incoming headers, or generates a 12-hex-char ID.
  2. Sets the ID in request_id_var so every log line for this request carries it.
  3. Times the request and records Prometheus metrics (counter + histogram).
  4. Echoes X-Request-ID back in the response header.
  5. Warns on slow requests (>1 s).
"""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import request_id_var
from app.core.metrics import (
    active_requests,
    http_request_duration_seconds,
    http_requests_total,
)

logger = logging.getLogger(__name__)

# Paths that don't need metrics (probes + metrics scrape)
_SKIP_PATHS = frozenset({"/health/live", "/health/ready", "/metrics"})

# Path prefixes whose slowness is expected (market data, AI, history) — higher threshold
_SLOW_PREFIXES = ("/api/stocks/", "/api/mf/", "/api/ai/", "/api/chat")
_SLOW_THRESHOLD = 8.0    # seconds — warn if stock/AI endpoints exceed this
_FAST_THRESHOLD = 2.0    # seconds — warn for all other endpoints


def _normalise_path(path: str) -> str:
    """Collapse dynamic path segments to avoid metric cardinality explosion."""
    parts = path.split("/")
    out   = []
    _DYNAMIC_PARENTS = frozenset({
        "stock", "index", "sector", "mf", "portfolio", "watchlist", "document"
    })
    for i, part in enumerate(parts):
        if i > 0 and out and out[-1].lstrip("/") in _DYNAMIC_PARENTS:
            out.append("{id}")
        else:
            out.append(part)
    return "/".join(out)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid   = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        skip  = request.url.path in _SKIP_PATHS

        if not skip:
            active_requests.inc()

        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            status   = str(response.status_code)
        except Exception as exc:
            status = "500"
            raise
        finally:
            elapsed = time.perf_counter() - t0
            request_id_var.reset(token)

            if not skip:
                active_requests.dec()
                path = _normalise_path(request.url.path)
                http_requests_total.inc(
                    method=request.method, path=path, status=status
                )
                http_request_duration_seconds.observe(
                    elapsed, method=request.method, path=path
                )
                threshold = (
                    _SLOW_THRESHOLD
                    if any(request.url.path.startswith(p) for p in _SLOW_PREFIXES)
                    else _FAST_THRESHOLD
                )
                if elapsed > threshold:
                    logger.warning(
                        "Slow request %s %s — %.2fs",
                        request.method,
                        request.url.path,
                        elapsed,
                        extra={"duration_ms": round(elapsed * 1000), "path": request.url.path},
                    )

        response.headers["X-Request-ID"] = rid
        return response
