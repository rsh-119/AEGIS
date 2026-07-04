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

from app.core.cache import cache
from app.core.circuit_breaker import all_statuses as cb_statuses
from app.core.config import get_settings
from app.core.database import engine
from app.core.metrics import registry

router  = APIRouter(tags=["health"])
logger  = logging.getLogger(__name__)
_START  = time.time()


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
        checks["database"] = {"status": "error", "error": str(exc)[:200]}
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
            # Redis degraded but app can fall back to memory — not fatal
            checks["redis"] = {"status": "degraded", "error": str(exc)[:200]}
            logger.warning("Readiness: Redis degraded: %s", exc)
    else:
        checks["redis"] = {"status": "memory_fallback", "note": "Redis not configured"}

    # ── Circuit breakers ──────────────────────────────────────────────────────
    cb_all  = cb_statuses()
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
    In production, requires X-Admin-Key header matching JWT_SECRET_KEY.
    """
    from fastapi import HTTPException
    settings = get_settings()
    if settings.app_env == "production":
        key = request.headers.get("x-admin-key", "")
        if key != settings.jwt_secret_key:
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
        "circuit_breakers": cb_statuses(),
    }


# ── Prometheus metrics scrape endpoint ────────────────────────────────────────

@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """
    Prometheus text exposition format (v0.0.4).
    Add this URL to your prometheus.yml scrape_configs.
    """
    return PlainTextResponse(
        registry.expose_all(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
