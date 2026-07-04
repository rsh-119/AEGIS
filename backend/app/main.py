"""
main.py — Aegis FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload --port 8000

Middleware stack (outermost → innermost):
  1. ReadOnlyMiddleware   — Firegun: blocks writes when READONLY_MODE=true
  2. RequestIDMiddleware  — attaches X-Request-ID, times requests, records metrics
  3. SlowAPIMiddleware    — per-IP rate limiting (120 req/min default)
  4. CORSMiddleware       — cross-origin headers
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.core.cache import cache
from app.core.logging_config import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.readonly import ReadOnlyMiddleware
from app.middleware.rate_limiter import limiter, rate_limit_exceeded_handler
from app.middleware.http_cache import HttpCacheMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers import stocks, ai, portfolio, watchlist, market, chat, documents, mf
from app.routers.auth import router as auth_router
from app.routers.alerts import router as alerts_router
from app.routers.health import router as health_router

settings = get_settings()

# Configure structured logging before anything else
configure_logging(app_env=settings.app_env, log_level=settings.log_level)
logger = logging.getLogger(__name__)


async def _prewarm():
    """Warm the slowest caches in background so the first user request is fast.

    IndianAPI has a metered monthly quota, so pre-warm is deliberately light —
    it must not burn quota that real user requests would otherwise use.

      R1 — no external API (MF list from AMFI)
      R2 — IndianAPI: trending + most-active + market overview + ETF/MF highlights
    """
    await asyncio.sleep(3)
    try:
        from app.services.mf_service import get_mf_list, get_etf_list, get_mf_highlights, get_etf_highlights
        from app.services.market_service import get_market_overview
        from app.services.bulk_deals_service import get_bulk_deals
        from app.services.indianapi_service import get_trending, get_nse_most_active
        logger.info("Cache: pre-warming…")

        # R1 — no external API calls
        await asyncio.gather(get_mf_list(), return_exceptions=True)

        # R2 — IndianAPI only (skipped when INDIANAPI_ENABLED=false)
        if settings.indianapi_enabled:
            await asyncio.gather(get_trending(), get_nse_most_active(), return_exceptions=True)
            await asyncio.gather(get_etf_list(), get_mf_highlights("1y"), get_etf_highlights(), return_exceptions=True)

        await asyncio.gather(get_market_overview(), get_bulk_deals(), return_exceptions=True)

        logger.info("Cache: pre-warm done")
    except Exception as exc:
        logger.warning("Cache: pre-warm failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Aegis API starting — env=%s", settings.app_env)
    cache.connect(settings.redis_url)
    await init_db()
    if not (settings.groq_api_key or settings.nvidia_api_key):
        logger.warning("No AI keys configured — AI features will be disabled.")
    if settings.readonly_mode:
        logger.warning("READONLY MODE is active — write operations are blocked.")
    asyncio.create_task(_prewarm())
    from app.services.home_refresh_service import home_refresh

    async def _start_background():
        await asyncio.sleep(90)
        # HomeRefreshTask starts after the first prewarm so cache is already warm
        home_refresh.start()

    asyncio.create_task(_start_background())
    yield
    home_refresh.stop()
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
    app.add_middleware(SlowAPIMiddleware)

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
async def cache_flush(prefix: str = "", x_admin_key: str | None = None):
    from fastapi import HTTPException
    # Require an admin key in production to prevent cache-flooding DoS
    admin_key = settings.jwt_secret_key  # reuse — same secret, no extra config needed
    if _is_prod and x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")
    cache.flush(prefix)
    return {"flushed": True, "prefix": prefix or "*"}
