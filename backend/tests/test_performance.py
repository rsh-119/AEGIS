"""Latency and load measurement against a real uvicorn process.

Numbers here are from a local machine with warm caches and INDIANAPI_ENABLED
false, so they measure Aegis's own overhead (routing, middleware, ORM,
serialisation) rather than upstream market-data latency. They are a floor,
not a production forecast — Render's free tier adds cold starts and slower
CPU on top.
"""

from __future__ import annotations

import asyncio
import statistics
import time

import httpx
import pytest

from app.core.auth import create_access_token
from app.core.cache import cache
from app.core.database import AsyncSessionLocal
from app.core.auth import hash_password
from app.models import Holding, User, WatchItem

pytestmark = pytest.mark.slow

# Ceilings for Aegis's own overhead on a warm local run. Deliberately loose —
# these exist to catch a regression of the order "someone added a blocking
# call to the hot path", not to police millisecond drift.
P95_BUDGET_MS = {
    "/health/live": 50,
    "/api/health": 100,
    "/api/stocks/TCS.NS/quote": 250,
    "/api/stocks/TCS.NS/history": 400,
    "/api/market/overview": 500,
    "/api/portfolio": 800,
    "/api/watchlist": 800,
}


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
    return ordered[idx]


def _report(label: str, samples: list[float], errors: int = 0) -> dict:
    stats = {
        "endpoint": label,
        "n": len(samples),
        "errors": errors,
        "p50": round(_pct(samples, 50), 1),
        "p95": round(_pct(samples, 95), 1),
        "p99": round(_pct(samples, 99), 1),
        "max": round(max(samples), 1) if samples else 0.0,
    }
    print(f"  {label:38} n={stats['n']:4}  p50={stats['p50']:7.1f}ms  "
          f"p95={stats['p95']:7.1f}ms  p99={stats['p99']:7.1f}ms  errors={errors}")
    return stats


async def _measure(client: httpx.AsyncClient, url: str, n: int,
                   headers: dict | None = None) -> tuple[list[float], int]:
    """`errors` counts unexpected failures only. 503 is excluded: with
    INDIANAPI_ENABLED=false, "upstream has no data" is the correct answer for
    the market-data routes, and counting it as an error would misreport a
    working degradation path as a fault."""
    samples: list[float] = []
    errors = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            r = await client.get(url, headers=headers or {})
            if r.status_code >= 500 and r.status_code != 503:
                errors += 1
        except Exception:
            errors += 1
        samples.append((time.perf_counter() - t0) * 1000)
    return samples, errors


@pytest.fixture
async def seeded_user():
    """A user with 10 holdings and 10 watch items — a realistic portfolio, so
    the per-user endpoints do real work rather than returning empty."""
    async with AsyncSessionLocal() as s:
        u = User(email="perf@example.com", username="perfuser",
                 hashed_password=hash_password("CorrectHorse1!x"))
        s.add(u)
        await s.flush()
        from datetime import date
        for i in range(10):
            s.add(Holding(user_id=u.id, ticker=f"PERF{i}.NS", company_name=f"Perf {i}",
                          shares=10 + i, avg_price=100.0 + i, buy_date=date(2025, 1, 1)))
            s.add(WatchItem(user_id=u.id, ticker=f"WATCH{i}.NS", company_name=f"Watch {i}"))
        await s.commit()
        uid = u.id

    # Warm the quote cache so this measures Aegis, not a cold upstream miss.
    for i in range(10):
        for prefix in ("PERF", "WATCH"):
            cache.set(f"quote:{prefix}{i}.NS", {
                "ticker": f"{prefix}{i}.NS", "current_price": 150.0, "previous_close": 148.0,
                "company_name": f"{prefix} {i}", "sector": "IT", "fetched_at": int(time.time()),
            }, "prices")
    return uid


# ── Latency ───────────────────────────────────────────────────────────────────

async def test_public_endpoint_latency(live_server):
    print("\n── Public endpoint latency (warm, local) ──")
    results = []
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        for url in ["/health/live", "/api/health", "/api/stocks/TCS.NS/quote",
                    "/api/stocks/TCS.NS/history", "/api/market/overview"]:
            await _measure(c, url, 3)          # warm-up, discarded
            samples, errors = await _measure(c, url, 40)
            results.append(_report(url, samples, errors))

    over = [r for r in results
            if r["endpoint"] in P95_BUDGET_MS and r["p95"] > P95_BUDGET_MS[r["endpoint"]]]
    assert not over, "p95 over budget: " + ", ".join(
        f"{r['endpoint']} {r['p95']}ms > {P95_BUDGET_MS[r['endpoint']]}ms" for r in over
    )


async def test_authenticated_endpoint_latency(live_server, seeded_user):
    print("\n── Authenticated endpoint latency (10 holdings / 10 watch items) ──")
    headers = {"Authorization": f"Bearer {create_access_token(seeded_user, 'perf-sid')}"}
    results = []
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        for url in ["/api/auth/me", "/api/portfolio", "/api/watchlist", "/api/alerts"]:
            await _measure(c, url, 3, headers)
            samples, errors = await _measure(c, url, 30, headers)
            results.append(_report(url, samples, errors))

    assert all(r["errors"] == 0 for r in results), "authenticated endpoints returned 5xx"
    over = [r for r in results
            if r["endpoint"] in P95_BUDGET_MS and r["p95"] > P95_BUDGET_MS[r["endpoint"]]]
    assert not over, "p95 over budget: " + ", ".join(
        f"{r['endpoint']} {r['p95']}ms" for r in over
    )


async def test_login_latency_is_dominated_by_bcrypt(live_server):
    """Login is deliberately slow (bcrypt). Recorded so it isn't mistaken for
    a regression later, and to confirm it stays within a sane bound."""
    print("\n── Login latency ──")
    async with AsyncSessionLocal() as s:
        u = User(email="loginperf@example.com", username="loginperf",
                 hashed_password=hash_password("CorrectHorse1!x"))
        s.add(u)
        await s.commit()

    samples = []
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        for _ in range(5):
            t0 = time.perf_counter()
            r = await c.post("/api/auth/login",
                             json={"email": "loginperf@example.com", "password": "CorrectHorse1!x"})
            samples.append((time.perf_counter() - t0) * 1000)
            if r.status_code == 429:
                break
    stats = _report("POST /api/auth/login", samples)
    assert stats["p95"] < 3000, "login latency far above the bcrypt cost alone"


# ── N+1 / query-count regression ──────────────────────────────────────────────

async def test_portfolio_list_does_not_issue_a_query_per_holding(seeded_user):
    """The route fans out quote lookups per holding (cached), but the DB side
    must stay at one SELECT regardless of how many holdings exist."""
    from sqlalchemy import event
    from app.core.database import engine

    statements: list[str] = []

    def _before(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before)
    try:
        from httpx import ASGITransport, AsyncClient
        from app.main import app
        headers = {"Authorization": f"Bearer {create_access_token(seeded_user, 'nplus1')}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/portfolio", headers=headers)
        assert r.status_code == 200
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before)

    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    print(f"\n  /api/portfolio with 10 holdings issued {len(selects)} SELECT(s)")
    assert len(selects) <= 3, (
        f"{len(selects)} SELECTs for 10 holdings — looks like a query per row"
    )


# ── Load ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("concurrency", [10, 25, 50])
async def test_concurrent_load_on_a_public_endpoint(live_server, concurrency):
    """Ramped load against a cheap cached endpoint. Looking for error-rate
    growth and latency collapse, not a throughput number."""
    url = "/api/health"
    per_worker = 10

    async def _worker(client):
        samples = []
        errors = 0
        for _ in range(per_worker):
            t0 = time.perf_counter()
            try:
                r = await client.get(url)
                if r.status_code >= 500:
                    errors += 1
            except Exception:
                errors += 1
            samples.append((time.perf_counter() - t0) * 1000)
        return samples, errors

    async with httpx.AsyncClient(
        base_url=live_server, timeout=60,
        limits=httpx.Limits(max_connections=concurrency * 2),
    ) as c:
        t0 = time.perf_counter()
        results = await asyncio.gather(*[_worker(c) for _ in range(concurrency)])
        wall = time.perf_counter() - t0

    samples = [s for r in results for s in r[0]]
    errors = sum(r[1] for r in results)
    total = concurrency * per_worker
    print(f"\n── Load @ {concurrency} concurrent ──")
    _report(f"{url} @{concurrency}", samples, errors)
    print(f"  throughput={total / wall:.0f} req/s  wall={wall:.2f}s  "
          f"error_rate={errors / total * 100:.1f}%")

    assert errors == 0, f"{errors}/{total} requests failed at {concurrency} concurrent"
    assert _pct(samples, 95) < 5000, "p95 collapsed under load"


async def test_repeated_sse_cycles_do_not_leak(live_server):
    """100 connect/disconnect cycles, then confirm the server still answers
    at normal latency — a proxy for orphaned tasks or queues accumulating."""
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        before, _ = await _measure(c, "/health/live", 10)
        for _ in range(100):
            async with c.stream("GET", "/api/stocks/LEAKTEST.NS/stream") as r:
                assert r.status_code == 200
        after, errors = await _measure(c, "/health/live", 10)

    print(f"\n  /health/live p95 before={_pct(before, 95):.1f}ms "
          f"after 100 SSE cycles={_pct(after, 95):.1f}ms")
    assert errors == 0
    assert _pct(after, 95) < max(100.0, _pct(before, 95) * 5), (
        "latency degraded sharply after repeated SSE connect/disconnect"
    )
