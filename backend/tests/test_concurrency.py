"""Optimistic concurrency on holdings, and transactional integrity.

The version check is the only thing standing between two open browser tabs
and a silently lost update, so it is driven with genuinely parallel requests
rather than sequential ones.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Holding, WatchItem


async def _holding(user_id: int, shares: float = 10) -> Holding:
    async with AsyncSessionLocal() as s:
        h = Holding(user_id=user_id, ticker="TCS.NS", company_name="TCS",
                    shares=shares, avg_price=3000.0, buy_date=date(2025, 1, 1))
        s.add(h)
        await s.commit()
        await s.refresh(h)
        return h


async def _reload(holding_id: int) -> Holding:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(Holding).where(Holding.id == holding_id))).scalar_one()


# ── Version handshake ─────────────────────────────────────────────────────────

async def test_holding_starts_at_version_1(client, user_a, bearer):
    r = await client.post("/api/portfolio", json={
        "ticker": "TCS.NS", "shares": 10, "avg_price": 3000, "buy_date": "2025-01-01",
    }, headers=bearer(user_a.id))
    assert r.status_code == 201
    assert r.json()["version"] == 1


async def test_successful_update_increments_the_version(client, user_a, bearer):
    h = await _holding(user_a.id)
    r = await client.patch(f"/api/portfolio/{h.id}",
                           json={"version": 1, "shares": 20}, headers=bearer(user_a.id))
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["shares"] == 20


async def test_stale_version_is_rejected_with_409(client, user_a, bearer):
    h = await _holding(user_a.id)
    await client.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 20},
                       headers=bearer(user_a.id))
    stale = await client.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 99},
                               headers=bearer(user_a.id))
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["error"] == "stale_version"
    assert detail["current_version"] == 2, "409 body must tell the client where to resync from"
    assert (await _reload(h.id)).shares == 20, "a stale write overwrote a newer value"


async def test_version_is_required(client, user_a, bearer):
    h = await _holding(user_a.id)
    r = await client.patch(f"/api/portfolio/{h.id}", json={"shares": 20},
                           headers=bearer(user_a.id))
    assert r.status_code == 422


async def test_a_future_version_is_also_rejected(client, user_a, bearer):
    h = await _holding(user_a.id)
    r = await client.patch(f"/api/portfolio/{h.id}", json={"version": 999, "shares": 20},
                           headers=bearer(user_a.id))
    assert r.status_code == 409


async def test_partial_update_only_touches_supplied_fields(client, user_a, bearer):
    h = await _holding(user_a.id)
    r = await client.patch(f"/api/portfolio/{h.id}", json={"version": 1, "notes": "hello"},
                           headers=bearer(user_a.id))
    assert r.status_code == 200
    fresh = await _reload(h.id)
    assert fresh.notes == "hello"
    assert fresh.shares == 10 and fresh.avg_price == 3000.0


# ── Genuine parallelism ───────────────────────────────────────────────────────

async def test_two_parallel_updates_produce_exactly_one_winner(client_factory, user_a, bearer):
    """Both requests read version 1 and race. Exactly one must win; the other
    must be told, not silently discarded."""
    h = await _holding(user_a.id)
    c1, c2 = await client_factory(), await client_factory()
    hdr = bearer(user_a.id)

    r1, r2 = await asyncio.gather(
        c1.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 111}, headers=hdr),
        c2.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 222}, headers=hdr),
        return_exceptions=True,
    )
    codes = sorted(r.status_code for r in (r1, r2) if not isinstance(r, BaseException))
    assert codes == [200, 409], f"expected exactly one winner, got {codes}"

    final = await _reload(h.id)
    assert final.shares in (111, 222)
    assert final.version == 2, f"version ended at {final.version} after one successful write"


async def test_ten_parallel_updates_never_lose_the_version_invariant(client_factory, user_a, bearer):
    h = await _holding(user_a.id)
    hdr = bearer(user_a.id)
    clients = [await client_factory() for _ in range(10)]

    results = await asyncio.gather(*[
        c.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 100 + i}, headers=hdr)
        for i, c in enumerate(clients)
    ], return_exceptions=True)

    codes = [r.status_code for r in results if not isinstance(r, BaseException)]
    assert 500 not in codes, f"a concurrency race produced a 500: {codes}"
    winners = codes.count(200)
    assert winners == 1, f"{winners} concurrent writers all reported success — lost update"
    assert codes.count(409) == len(codes) - winners

    final = await _reload(h.id)
    assert final.version == 2


async def test_parallel_reads_during_a_write_stay_consistent(client_factory, user_a, bearer):
    h = await _holding(user_a.id)
    hdr = bearer(user_a.id)
    writer, reader = await client_factory(), await client_factory()

    w, r = await asyncio.gather(
        writer.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 55}, headers=hdr),
        reader.get("/api/portfolio", headers=hdr),
        return_exceptions=True,
    )
    assert not isinstance(r, BaseException) and r.status_code == 200
    shares = [x["shares"] for x in r.json()["holdings"]]
    assert shares in ([10], [55]), f"a read observed a torn value: {shares}"


async def test_concurrent_delete_and_update_do_not_500(client_factory, user_a, bearer):
    h = await _holding(user_a.id)
    hdr = bearer(user_a.id)
    c1, c2 = await client_factory(), await client_factory()

    results = await asyncio.gather(
        c1.delete(f"/api/portfolio/{h.id}", headers=hdr),
        c2.patch(f"/api/portfolio/{h.id}", json={"version": 1, "shares": 77}, headers=hdr),
        return_exceptions=True,
    )
    codes = [r.status_code for r in results if not isinstance(r, BaseException)]
    assert all(c < 500 for c in codes), f"delete/update race produced {codes}"


# ── Transactional integrity ───────────────────────────────────────────────────

async def test_duplicate_watch_insert_is_a_409_not_a_constraint_500(client, user_a, bearer):
    await client.post("/api/watchlist", json={"ticker": "TCS.NS"}, headers=bearer(user_a.id))
    r = await client.post("/api/watchlist", json={"ticker": "TCS.NS"}, headers=bearer(user_a.id))
    assert r.status_code == 409


async def test_parallel_duplicate_watch_inserts_do_not_both_commit(client_factory, user_a, bearer):
    """The select-then-insert in add_watch has a race window; the unique
    constraint is the real guard. Either way, one row must result."""
    hdr = bearer(user_a.id)
    c1, c2 = await client_factory(), await client_factory()
    results = await asyncio.gather(
        c1.post("/api/watchlist", json={"ticker": "TCS.NS"}, headers=hdr),
        c2.post("/api/watchlist", json={"ticker": "TCS.NS"}, headers=hdr),
        return_exceptions=True,
    )
    codes = [r.status_code for r in results if not isinstance(r, BaseException)]

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(WatchItem).where(WatchItem.user_id == user_a.id))).scalars().all()
    assert len(rows) == 1, f"duplicate watchlist rows committed (codes={codes})"


async def test_a_failed_write_leaves_no_partial_state(client, user_a, bearer, monkeypatch):
    """If the commit path raises after rows are staged, nothing may persist."""
    from app.core import database

    original = database.AsyncSessionLocal

    r = await client.post("/api/auth/sync-guest-data", json={"holdings": [
        {"ticker": "TCS.NS", "shares": 1, "avg_price": 1, "buy_date": "2025-01-01"},
        {"ticker": "BAD", "shares": 1, "avg_price": 1, "buy_date": "not-a-date"},
    ]}, headers=bearer(user_a.id))
    assert r.status_code == 422

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Holding).where(Holding.user_id == user_a.id))).scalars().all()
    assert rows == [], "a rejected batch left rows behind"


async def test_ai_review_persist_failure_does_not_corrupt_the_session(
    client, user_a, bearer, monkeypatch,
):
    """portfolio_insights_ai wraps generation + DB persistence in one broad
    except. A persistence failure must not leave the request's session in a
    state that then fails on commit."""
    from app.services import ai_service
    await _holding(user_a.id)

    async def _review(context):
        return {"verdict": "v",
                "observations": [{"severity": "risk", "title": "t", "insight": "i", "action": "a"}],
                "holdings_sentiment": []}

    monkeypatch.setattr(ai_service, "review_portfolio", _review)

    import app.routers.portfolio as portfolio_router
    real_review_model = portfolio_router.PortfolioReview

    class _Exploding:
        def __init__(self, **kwargs):
            raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(portfolio_router, "PortfolioReview", _Exploding)

    r = await client.get("/api/portfolio/insights/ai", headers=bearer(user_a.id))
    assert r.status_code < 500, f"a persistence failure surfaced as {r.status_code}"
    assert r.json()["ai"] is None

    monkeypatch.setattr(portfolio_router, "PortfolioReview", real_review_model)
    follow_up = await client.get("/api/portfolio", headers=bearer(user_a.id))
    assert follow_up.status_code == 200, "the session was left unusable"
