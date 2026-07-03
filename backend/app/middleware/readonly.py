"""
Firegun read-only mode.

When READONLY_MODE=true in .env (or the env var is set), all state-mutating
HTTP methods (POST, PUT, PATCH, DELETE) return 503 immediately, except for
a small allowlist of paths that must always work (probes, auth, etc.).

Intended for:
  • Emergency maintenance  — flip READONLY_MODE=true, restart
  • Zero-downtime deploys  — drain writes before rolling update
  • Incident containment   — stop cascade failures from write storms

Toggle without code change:
  export READONLY_MODE=true && uvicorn app.main:app …
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_WRITE_METHODS    = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_ALWAYS_ALLOWED   = frozenset({
    "/health/live",
    "/health/ready",
    "/api/health",
    "/metrics",
})


class ReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if (
            settings.readonly_mode
            and request.method in _WRITE_METHODS
            and request.url.path not in _ALWAYS_ALLOWED
        ):
            logger.warning(
                "READONLY MODE: blocked %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "error":    "Service is in read-only maintenance mode.",
                    "readonly": True,
                    "hint":     "Write operations are temporarily disabled. Try again later.",
                },
                headers={"Retry-After": "300"},
            )
        return await call_next(request)
