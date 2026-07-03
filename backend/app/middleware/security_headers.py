"""
security_headers.py — Add hardened HTTP security headers to all API responses.

Covers: Clickjacking, MIME sniffing, information disclosure (Server header),
cross-origin isolation, and referrer leakage.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Force HTTPS
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        # Limit referrer leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Remove server fingerprint
        response.headers["Server"] = "Aegis"
        # Restrict cross-origin resource sharing at the browser level
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        return response
