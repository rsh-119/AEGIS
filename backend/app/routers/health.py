"""
Health check endpoints.

/health/live    — Kubernetes liveness probe (always 200 unless process is dead)
/health/ready   — Kubernetes readiness probe (DB + Redis + circuit-breaker state)
/health/status  — Full ops dashboard (metrics, cache, breakers, uptime)
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from app.core import groq_circuit_breaker
from app.core.cache import cache
from app.core.config import get_settings
from app.core.database import engine
from app.core.metrics import registry
from app.services.indianapi_service import indianapi_backoff_remaining, indianapi_blocked

router  = APIRouter(tags=["health"])
logger  = logging.getLogger(__name__)
_START  = time.time()


def _all_circuit_statuses() -> list[dict]:
    """Every circuit breaker this codebase actually operates, in the shape
    /health/ready and /health/status both expect.

    There is no generic breaker registry to consult: app/core/circuit_breaker.py
    was a registry with no callers (nothing ever called get_breaker), so it
    always returned an empty list and was removed. The two breakers that are
    real are open-coded in their own modules — IndianAPI's 429 backoff in
    indianapi_service._blocked_until, and the Groq streaming breaker in
    app.core.groq_circuit_breaker — and are folded in here."""
    statuses: list[dict] = []
    if indianapi_blocked():
        statuses.append({
            "name": "indianapi", "state": "open", "failures": 0,
            "total_trips": 0, "seconds_until_retry": indianapi_backoff_remaining(),
        })
    # Groq streaming breaker (app.core.groq_circuit_breaker) — folded in the
    # same way, but deliberately NOT added to _CRITICAL below: a stream
    # outage degrades to non-streaming JSON via the still-working waterfall,
    # a UX regression, not an outage worth pulling the pod from rotation for.
    if groq_circuit_breaker.is_open():
        statuses.append(groq_circuit_breaker.status())
    return statuses


# ── Liveness probe ────────────────────────────────────────────────────────────

@router.get("/health/live", include_in_schema=False)
async def liveness():
    """
    Kubernetes liveness probe.
    Returns 200 as long as the event loop is alive.
    If this returns non-200, k8s will restart the pod.
    """
    return {"status": "alive", "uptime_s": round(time.time() - _START)}


# ── Readiness probe ───────────────────────────────────────────────────────────

@router.get("/health/ready", include_in_schema=False)
async def readiness():
    """
    Kubernetes readiness probe.
    Returns 200 = ready to serve traffic.
    Returns 503 = remove from load-balancer rotation until fixed.

    Checks: PostgreSQL connectivity, Redis connectivity, circuit-breaker health.
    """
    checks: dict = {}
    overall_ok   = True

    # ── Database ──────────────────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = {
            "status":     "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
    except Exception as exc:
        # Deliberately generic: this endpoint is unauthenticated, and real
        # asyncpg failures carry infrastructure detail — the database
        # username ('password authentication failed for user "aegis"') or the
        # host and port ("Connect call failed ('10.0.0.5', 5432)"). The full
        # exception goes to the logs, where ops can actually see it, rather
        # than to anyone who curls the probe during an outage.
        checks["database"] = {"status": "error", "error": "database unreachable"}
        overall_ok = False
        logger.error("Readiness: DB check failed: %s", exc)

    # ── Redis ─────────────────────────────────────────────────────────────────
    if cache.backend == "redis":
        try:
            t0 = time.perf_counter()
            cache._redis.ping()
            checks["redis"] = {
                "status":     "ok",
                "latency_ms": round((time.perf_counter() - t0) * 1000),
            }
        except Exception as exc:
            # Redis degraded but app can fall back to memory — not fatal.
            # Reason kept generic for the same reason as the database branch.
            checks["redis"] = {"status": "degraded", "error": "redis unreachable"}
            logger.warning("Readiness: Redis degraded: %s", exc)
    else:
        checks["redis"] = {"status": "memory_fallback", "note": "Redis not configured"}

    # ── Circuit breakers ──────────────────────────────────────────────────────
    cb_all  = _all_circuit_statuses()
    cb_open = [s["name"] for s in cb_all if s["state"] == "open"]
    checks["circuit_breakers"] = {
        "total":      len(cb_all),
        "open":       cb_open,
        "open_count": len(cb_open),
    }
    # Open circuits on critical services → not ready
    _CRITICAL = {"indianapi", "database"}
    if any(name in _CRITICAL for name in cb_open):
        overall_ok = False

    return JSONResponse(
        status_code=200 if overall_ok else 503,
        content={
            "status":   "ready" if overall_ok else "not_ready",
            "uptime_s": round(time.time() - _START),
            "env":      get_settings().app_env,
            "checks":   checks,
        },
    )


# ── Full status dashboard ─────────────────────────────────────────────────────

@router.get("/health/status")
async def full_status(request: Request):
    """
    Human/ops-readable system status.
    In production, requires X-Admin-Key header matching ADMIN_API_KEY.
    """
    from fastapi import HTTPException
    settings = get_settings()
    if settings.app_env == "production":
        key = request.headers.get("x-admin-key", "")
        if not settings.admin_api_key or key != settings.admin_api_key:
            raise HTTPException(status_code=403, detail="Forbidden")
    return {
        "service":  "aegis-api",
        "version":  "1.0.0",
        "env":      settings.app_env,
        "uptime_s": round(time.time() - _START),
        "readonly": settings.readonly_mode,
        "ai": {
            "primary":    "groq",
            "fallback":   "nvidia/deepseek",
            "groq_key":   bool(settings.groq_api_key),
            "nvidia_key": bool(settings.nvidia_api_key),
        },
        "cache":            cache.stats(),
        "circuit_breakers": _all_circuit_statuses(),
    }


# ── Prometheus metrics scrape endpoint ────────────────────────────────────────

@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request):
    """
    Prometheus text exposition format (v0.0.4).
    Add this URL to your prometheus.yml scrape_configs.

    Protected in production by the same X-Admin-Key as /health/status. The
    payload holds no secrets (asserted in tests/test_ops.py) but it does
    publish the full route inventory, request volumes and latency
    distributions — free reconnaissance, and a free read on how much traffic
    the service actually takes.

    Two ways to scrape it in production:
      • send `X-Admin-Key: $ADMIN_API_KEY` (Prometheus `http_headers:`), or
      • set METRICS_PUBLIC=true when the endpoint is genuinely unreachable
        from outside the cluster — which is what k8s/deployment.yaml's
        prometheus.io/scrape annotation describes.

    Fails closed: with APP_ENV=production, METRICS_PUBLIC unset and
    ADMIN_API_KEY unset, this 403s rather than serving to anyone.
    """
    from fastapi import HTTPException
    settings = get_settings()
    if settings.app_env == "production" and not settings.metrics_public:
        key = request.headers.get("x-admin-key", "")
        if not settings.admin_api_key or key != settings.admin_api_key:
            raise HTTPException(status_code=403, detail="Forbidden")
    return PlainTextResponse(
        registry.expose_all(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
