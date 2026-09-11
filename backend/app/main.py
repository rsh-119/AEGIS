"""
main.py — Aegis FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload --port 8000

Middleware stack (outermost → innermost):
  1. ReadOnlyMiddleware   — Firegun: blocks writes when READONLY_MODE=true
  2. RequestIDMiddleware  — attaches X-Request-ID, times requests, records metrics
  3. ResilientSlowAPIMiddleware — per-client rate limiting (120 req/min default)
  4. CORSMiddleware       — cross-origin headers
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.database import init_db
from app.core.cache import cache
from app.core.logging_config import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.readonly import ReadOnlyMiddleware
from app.middleware.rate_limiter import ResilientSlowAPIMiddleware, limiter, rate_limit_exceeded_handler
from app.middleware.http_cache import HttpCacheMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import stocks, ai, portfolio, watchlist, market, chat, documents, mf
from app.routers.auth import router as auth_router
from app.routers.alerts import router as alerts_router
from app.routers.health import router as health_router
from app.routers.admin import router as admin_router

settings = get_settings()

# Configure structured logging before anything else
configure_logging(app_env=settings.app_env, log_level=settings.log_level)
logger = logging.getLogger(__name__)

# Error tracking — no-op until SENTRY_DSN is set (same fail-closed-until-
# configured pattern as admin_api_key). FastAPI/Starlette integrations
# auto-enable once sentry-sdk detects those packages are installed.
if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,   # 10% of requests get performance tracing
        send_default_pii=False,   # don't attach request bodies/headers/user IPs
    )
    logger.info("Sentry error tracking enabled — env=%s", settings.app_env)


async def _prewarm():
    """Warm the slowest caches in background so the first user request is fast.

    IndianAPI has a metered monthly quota, so pre-warm is deliberately light —
    it must not burn quota that real user requests would otherwise use.

      R1 — no external API (MF list from AMFI)
      R2 — IndianAPI: market overview + ETF/MF highlights
    """
    await asyncio.sleep(3)
    try:
        from app.services.mf_service import get_mf_list, get_etf_list, get_mf_highlights, get_etf_highlights
        from app.services.market_service import get_market_overview
        from app.services.bulk_deals_service import get_bulk_deals
        logger.info("Cache: pre-warming…")

        # R1 — no external API calls
        await asyncio.gather(get_mf_list(), return_exceptions=True)

        # R2 — IndianAPI only (skipped when INDIANAPI_ENABLED=false)
        if settings.indianapi_enabled:
            await asyncio.gather(get_etf_list(), get_mf_highlights("1y"), get_etf_highlights(), return_exceptions=True)

        await asyncio.gather(get_market_overview(), get_bulk_deals(), return_exceptions=True)

        logger.info("Cache: pre-warm done")
    except Exception as exc:
        logger.warning("Cache: pre-warm failed: %s", exc)


def warn_if_proxy_trust_is_not_narrowed(settings) -> str | None:
    """Log a startup warning when TRUSTED_PROXY_IPS has not been narrowed.

    TRUSTED_PROXY_IPS is a deployment-topology parameter with no safe universal
    default, so leaving it unset must be VISIBLE rather than silent. The shipped
    default trusts loopback + RFC1918, which is where a reverse proxy, k8s
    ingress or platform edge genuinely connects from — and is also where a NAT
    gateway sits. Docker's `-p 8000:8000` rewrites every caller's source address
    into the bridge subnet, so with the default in place a directly-published
    backend accepts the caller's own X-Forwarded-For and per-IP rate limits
    become resettable at will (confirmed against the built image).

    An IP check cannot tell those two cases apart, so the fix is operational:
    narrow this to the proxy's actual address. Warning at startup is what turns
    "nobody knew" into "it was in the logs on every boot".

    Returns the warning category ("default" | "wildcard" | None) so this is
    testable without booting a second application.
    """
    if settings.app_env != "production":
        return None

    from app.core.config import Settings as _Settings
    default = _Settings.model_fields["trusted_proxy_ips"].default

    if settings.trusted_proxy_ips == default:
        logger.warning(
            "TRUSTED_PROXY_IPS is at its default (loopback + RFC1918). Per-IP "
            "rate limiting is only sound if every caller reaches this app "
            "through a proxy on one of those addresses. If this backend is "
            "published directly (e.g. docker run -p), a NAT gateway peer is "
            "trusted and X-Forwarded-For can be forged to reset any bucket. "
            "Set TRUSTED_PROXY_IPS to your ingress/proxy CIDR."
        )
        return "default"

    if settings.trusted_proxy_ips.strip() == "*":
        logger.warning(
            "TRUSTED_PROXY_IPS='*' — X-Forwarded-For is accepted from ANY peer. "
            "Correct only if this app is unreachable except through a trusted "
            "proxy; otherwise every per-IP rate limit is bypassable."
        )
        return "wildcard"

    logger.info(
        "TRUSTED_PROXY_IPS is explicitly configured (%d network(s)).",
        len(settings.trusted_proxy_networks),
    )
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Aegis API starting — env=%s", settings.app_env)

    # Fail fast — before touching Redis/DB — if a production deploy is about
    # to sign every user's session with no real secret at all.
    if not settings.jwt_secret_key:
        if settings.app_env == "production":
            raise RuntimeError(
                "FATAL: JWT_SECRET_KEY is not set while APP_ENV=production. "
                "Set a real secret (e.g. `openssl rand -hex 32`) before starting."
            )
        # Dev/local convenience: generate an ephemeral secret so the app still
        # boots with zero config, rather than shipping a shared hardcoded
        # placeholder every dev machine (and, historically, prod) could sign
        # tokens with. Ephemeral means restarts invalidate existing sessions —
        # fine for local dev, which is exactly the case this branch is for.
        import secrets
        settings.jwt_secret_key = secrets.token_hex(32)
        logger.warning("JWT_SECRET_KEY is unset — generated an ephemeral dev secret (won't survive a restart).")
    elif len(settings.jwt_secret_key) < 32:
        logger.warning("JWT_SECRET_KEY is set but shorter than 32 chars — consider `openssl rand -hex 32`.")

    cache.connect(settings.redis_url)
    await init_db()
    if not (settings.groq_api_key or settings.nvidia_api_key):
        logger.warning("No AI keys configured — AI features will be disabled.")
    if settings.readonly_mode:
        logger.warning("READONLY MODE is active — write operations are blocked.")

    warn_if_proxy_trust_is_not_narrowed(settings)

    asyncio.create_task(_prewarm())
    from app.services.home_refresh_service import home_refresh
    from app.services.prewarm_service import ai_prewarm_task

    async def _start_background():
        await asyncio.sleep(90)
        # HomeRefreshTask starts after the first prewarm so cache is already warm
        home_refresh.start()
        ai_prewarm_task.start()

    asyncio.create_task(_start_background())
    yield
    home_refresh.stop()
    ai_prewarm_task.stop()
    from app.services.price_stream_service import price_stream_hub
    price_stream_hub.shutdown()
    logger.info("Aegis API shutting down")


_is_prod = settings.app_env == "production"

app = FastAPI(
    title="Aegis API",
    description="Indian stock market intelligence — quotes, AI analysis, forecasts.",
    version="1.0.0",
    lifespan=lifespan,
    # Disable interactive docs in production — they expose schema and aid enumeration
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# ── Middleware (added last = executed first) ──────────────────────────────────

app.add_middleware(CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Cache-Control"],
)
app.add_middleware(SecurityHeadersMiddleware)

if settings.rate_limit_enabled:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(ResilientSlowAPIMiddleware)

app.add_middleware(HttpCacheMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(ReadOnlyMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(alerts_router)
app.include_router(stocks.router)
app.include_router(ai.router)
app.include_router(portfolio.router)
app.include_router(watchlist.router)
app.include_router(market.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(mf.router)
app.include_router(admin_router)


# ── Legacy health endpoint (kept for backward compat) ─────────────────────────

@app.get("/api/health", include_in_schema=False)
async def health_legacy():
    return {
        "status":        "ok",
        "ai_primary":    "groq" if settings.groq_api_key else "none",
        "ai_model":      settings.groq_model,
        "ai_configured": bool(settings.nvidia_api_key or settings.groq_api_key),
        "market":        "NSE/BSE (India)",
        "readonly":      settings.readonly_mode,
        "cache":         cache.stats(),
    }


@app.get("/api/cache/stats", include_in_schema=False)
async def cache_stats():
    # Strip sensitive key names from stats before returning
    return cache.stats()


@app.delete("/api/cache", include_in_schema=False)
async def cache_flush(request: Request, prefix: str = ""):
    from fastapi import HTTPException
    # Require an admin key in production to prevent cache-flooding DoS.
    # Read from the X-Admin-Key header (matches /health/status), not a query
    # param — a query param rides along in proxy/CDN access logs and shell
    # history, turning any log leak into a cache-flush-DoS vector for free.
    # Deliberately NOT settings.jwt_secret_key — that secret signs every
    # user's session token, so reusing it here would mean a leak of this
    # header is a full auth bypass, not just a cache-flush leak.
    if _is_prod:
        key = request.headers.get("x-admin-key", "")
        if not settings.admin_api_key or key != settings.admin_api_key:
            raise HTTPException(status_code=403, detail="Forbidden")
    cache.flush(prefix)
    return {"flushed": True, "prefix": prefix or "*"}
