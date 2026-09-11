"""
Firegun read-only mode.

When READONLY_MODE=true, state-mutating HTTP methods (POST, PUT, PATCH,
DELETE) return 503 — with the deliberate exception of the paths listed in
_ALWAYS_ALLOWED below.

Intended for:
  • Emergency maintenance  — flip READONLY_MODE=true, restart
  • Zero-downtime deploys  — drain writes before rolling update
  • Incident containment   — stop cascade failures from write storms

Toggle without code change:
  export READONLY_MODE=true && uvicorn app.main:app …

── Why authentication is exempt ──────────────────────────────────────────────
The allowlist used to cover only the probes. That meant READONLY_MODE also
returned 503 for POST /api/auth/login, POST /api/auth/refresh and POST
/api/auth/logout — so flipping the switch during an incident locked every
user out of *reading* their own portfolio, watchlist and alerts, and expired
sessions could not even be refreshed. For a mode whose entire purpose is
"reads keep working", that is the wrong failure: it degrades the product to
anonymous-only at exactly the moment ops wants it observable.

Authentication is not an application-domain write. Establishing, rotating or
ending a session mutates only session state (a Redis key and a cookie), not
market, portfolio or billing data — which is what this switch exists to
freeze. So the session lifecycle is allowed through and everything that
writes user data stays blocked.

What stays BLOCKED on purpose, even though it lives under /api/auth:
  • /api/auth/register        — creates a row in `users`
  • /api/auth/me (PATCH)      — edits a row in `users`
  • /api/auth/change-password — edits a row in `users`
  • /api/auth/forgot-password — writes a reset token AND sends an email
  • /api/auth/reset-password  — edits a row in `users`
  • /api/auth/sync-guest-data — bulk-writes holdings and watchlist rows
  • /api/auth/2fa/*  (setup/enable/disable)  — edits a row in `users`
…which is why this is an explicit allowlist of four exact paths rather than a
`/api/auth` prefix match. 2fa/verify-login is the one 2FA route that is
allowed: it completes a login and writes nothing but session state.

Logout is allowed for a security reason, not a convenience one: refusing it
would mean a user who believes they have signed out has not, and a stolen
token could not be revoked for the duration of the incident. "Cannot revoke"
is a worse state to be stuck in than "can revoke".
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_WRITE_METHODS    = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Exact paths only — see the module docstring for why this is not a prefix match.
_ALWAYS_ALLOWED   = frozenset({
    # Probes / ops
    "/health/live",
    "/health/ready",
    "/api/health",
    "/metrics",
    # Session lifecycle — mutates session state only, never user data.
    "/api/auth/login",
    "/api/auth/google",
    "/api/auth/2fa/verify-login",
    "/api/auth/refresh",
    "/api/auth/logout",
})


class ReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if (
            settings.readonly_mode
            and request.method in _WRITE_METHODS
            and request.url.path.rstrip("/") not in _ALWAYS_ALLOWED
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
