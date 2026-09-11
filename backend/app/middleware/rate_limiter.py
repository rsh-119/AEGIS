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

import ipaddress
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _peer_is_trusted_proxy(peer: str) -> bool:
    """Is the actual TCP peer allowed to speak for someone else?

    Returns False for anything unparseable — an unknown peer must never be
    granted proxy authority.
    """
    nets = get_settings().trusted_proxy_networks
    if nets and nets[0] == "*":
        return True
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def client_ip(request: Request) -> str:
    """The requesting client's IP, chosen so a client-supplied header cannot
    change it.

    Two independent conditions have to hold, and the first one was missing
    until real-transport testing caught it:

    1. THE PEER MUST BE A TRUSTED PROXY. X-Forwarded-For is only meaningful if
       something in front actually wrote it. A client connecting directly can
       send `X-Forwarded-For: <anything>`; with no proxy to append to it, that
       single value is simultaneously the leftmost AND the rightmost entry, so
       counting from either end reads the attacker's choice and every per-IP
       bucket is resettable at will. Counting hops does not help — the chain is
       exactly as long as the attacker made it. Verified against the built
       container: 40 logins with a rotating header, zero 429s.

       So the header is consulted only when request.client.host is inside
       TRUSTED_PROXY_IPS (default: loopback + RFC1918, where a reverse proxy,
       ingress or platform edge legitimately connects from). Otherwise the real
       socket peer is the key and the header is ignored outright.

       This is why backend/Dockerfile no longer passes
       --forwarded-allow-ips "*": that flag made uvicorn overwrite
       request.client.host with the leftmost X-Forwarded-For entry before this
       function ever ran, destroying the only value that cannot be forged.

    2. THE RIGHT ENTRY MUST BE PICKED. Every conforming proxy APPENDS the peer
       it saw, so the entries a client prepends sit on the left and the ones
       proxies wrote sit on the right. Counting TRUSTED_PROXY_HOPS from the
       right lands on the address the outermost trusted proxy observed; extra
       prepended entries shift out of the window and are ignored.

    X-Real-IP is deliberately never consulted: nothing in this deployment sets
    it, so honouring it would re-open the same hole through a second header.
    """
    settings = get_settings()
    peer = get_remote_address(request) or "unknown"

    if not _peer_is_trusted_proxy(peer):
        # Direct connection (or an untrusted hop). Its headers carry no
        # authority; the socket address is the only thing it cannot forge.
        return peer

    hops = max(1, settings.trusted_proxy_hops)
    forwarded = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in forwarded.split(",") if p.strip()]
    if parts:
        # len(parts) < hops means fewer proxies than configured (e.g. an
        # internal caller); clamp to the leftmost, which is then the only
        # value any proxy wrote.
        return parts[max(0, len(parts) - hops)]

    return peer


def _build_limiter() -> Limiter:
    """In-memory storage (slowapi's default) counts per-process — fine for a
    single instance, but once Aegis runs more than one backend instance each
    one tracks its own independent bucket, silently multiplying every limit
    (AUTH_LIMIT included) by the instance count. Point slowapi at Redis so all
    instances share one counter.

    limits' RedisStorage doesn't actually touch the network until the first
    request comes in (constructing it never raises even if Redis is down), so
    an eager ping here — same check cache.py already does before committing to
    Redis — is required to fail open onto in-memory storage instead of only
    discovering the outage on a live request.
    """
    settings = get_settings()
    storage_uri = None
    try:
        import redis as _r
        _r.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
        storage_uri = settings.redis_url
        logger.info("Rate limiter: Redis reachable — using shared storage across instances")
    except Exception as exc:
        logger.warning("Rate limiter: Redis unavailable (%s) — falling back to in-memory (per-instance) limits", exc)

    kwargs = {"storage_uri": storage_uri} if storage_uri else {}
    return Limiter(
        key_func=client_ip,
        default_limits=["120/minute"],
        headers_enabled=True,       # X-RateLimit-* response headers
        # Fail open on a storage error. slowapi routes any exception raised by
        # its own check — including redis.ConnectionError — into the
        # registered RateLimitExceeded handler, which then reads exc.detail
        # and raises AttributeError. With swallow_errors=False that turns a
        # Redis blip into a 500 on EVERY request (there is a 120/minute
        # default limit, so every route is checked). Redis is a soft
        # dependency everywhere else here (cache.py's memory fallback,
        # token_store's fail-open blocklist, health.py's "degraded"), and an
        # outage should degrade rate limiting, not take the API down.
        swallow_errors=True,
        **kwargs,
    )


limiter = _build_limiter()

# Convenience constants — import these in routers
AI_LIMIT      = "10/minute"
STOCK_LIMIT   = "60/minute"
SEARCH_LIMIT  = "30/minute"
GENERAL_LIMIT = "120/minute"
AUTH_LIMIT    = "5/15minute"   # brute-force/credential-stuffing guard — login + register only
PASSWORD_RESET_LIMIT = "3/15minute"   # forgot-password only — tighter than AUTH_LIMIT since it triggers a real email send
TWO_FA_LIMIT          = "5/15minute"  # authenticated 2FA setup/enable/disable, keyed per-account via user_or_ip_key
TWO_FA_VERIFY_LIMIT   = "5/5minute"   # 2fa/verify-login — per-IP only, no session exists yet to key per-account
AVATAR_UPLOAD_LIMIT   = "10/15minute" # profile photo upload — each one runs a Pillow resize/re-encode, not free


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
    return client_ip(request)


class ResilientSlowAPIMiddleware(SlowAPIMiddleware):
    """SlowAPIMiddleware that survives a rate-limit storage outage.

    swallow_errors=True stops a Redis failure from being routed into the
    RateLimitExceeded handler (which would read `exc.detail` off a
    ConnectionError and raise AttributeError). It does not finish the job:
    slowapi's dispatch still ends with

        response = limiter._inject_headers(response, request.state.view_rate_limit)

    and `view_rate_limit` is only assigned on the successful check path. With
    the check swallowed, that attribute never exists, so every request 500s on
    AttributeError instead — the same total outage, one line further down.

    Seeding it to None up front makes _inject_headers a documented no-op (it
    already guards `current_limit is not None`), so a storage outage costs the
    X-RateLimit-* headers and the limit itself, not the request.
    """

    async def dispatch(self, request: Request, call_next):
        if not hasattr(request.state, "view_rate_limit"):
            request.state.view_rate_limit = None
        return await super().dispatch(request, call_next)


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
