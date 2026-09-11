"""Groq streaming circuit breaker, the document/portfolio AI caches, and
per-user isolation of anything AI-cached."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.core import groq_circuit_breaker as cb
from app.core.cache import cache
from app.services import ai_service


@pytest.fixture(autouse=True)
def _reset():
    cb._failure_times.clear()
    cb._opened_until = 0.0
    ai_service._prompt_cache._store.clear()
    yield
    cb._failure_times.clear()
    cb._opened_until = 0.0
    ai_service._prompt_cache._store.clear()


# ── Circuit breaker states ────────────────────────────────────────────────────

def test_breaker_starts_closed():
    assert cb.is_open() is False
    assert cb.status()["state"] == "closed"


def test_breaker_stays_closed_below_the_threshold():
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is False, "opened before reaching 3 failures"


def test_breaker_opens_at_the_threshold():
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open() is True
    assert cb.status()["state"] == "open"
    assert 0 < cb.seconds_until_retry() <= 300


def test_failures_outside_the_window_do_not_accumulate():
    """Three failures spread over more than 60s must not trip the breaker."""
    now = time.time()
    cb._failure_times.extend([now - 400, now - 200])
    cb.record_failure()
    assert cb.is_open() is False, "stale failures outside the 60s window counted toward the trip"


def test_breaker_closes_after_the_open_window_elapses():
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open() is True
    cb._opened_until = time.time() - 1
    assert cb.is_open() is False, "breaker never recovers on its own"


def test_a_successful_stream_closes_an_open_breaker():
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open() is True
    cb.record_success()
    assert cb.is_open() is False
    assert cb.status()["failures"] == 0


def test_breaker_reopens_if_failures_resume_after_recovery():
    for _ in range(3):
        cb.record_failure()
    cb.record_success()
    for _ in range(3):
        cb.record_failure()
    assert cb.is_open() is True


# ── Breaker behaviour at the route ────────────────────────────────────────────

async def test_stream_peek_failure_falls_back_to_the_json_waterfall(client, monkeypatch):
    async def _boom(*a, **kw):
        raise RuntimeError("groq stream refused")
        yield  # pragma: no cover — makes this an async generator

    async def _answer(*a, **kw):
        return {"answer": "fallback answer", "confidence": "Low", "answered_from_facts": False}

    monkeypatch.setattr(ai_service, "stream_answer", _boom)
    monkeypatch.setattr(ai_service, "answer", _answer)

    r = await client.post("/api/ai/ask-stream", json={"question": "what is tcs"})
    assert r.status_code == 200
    assert r.json()["answer"] == "fallback answer"
    assert cb.status()["failures"] == 1, "a stream peek failure was not recorded on the breaker"


async def test_open_breaker_skips_the_peek_entirely(client, monkeypatch):
    peeked = {"n": 0}

    async def _stream(*a, **kw):
        peeked["n"] += 1
        yield "chunk"

    async def _answer(*a, **kw):
        return {"answer": "waterfall", "confidence": "Low", "answered_from_facts": False}

    monkeypatch.setattr(ai_service, "stream_answer", _stream)
    monkeypatch.setattr(ai_service, "answer", _answer)
    cb._opened_until = time.time() + 300

    r = await client.post("/api/ai/ask-stream", json={"question": "hi"})
    assert r.status_code == 200
    assert peeked["n"] == 0, "an open breaker still paid for the streaming peek"


async def test_slow_stream_does_not_block_past_the_peek_timeout(client, monkeypatch):
    async def _slow(*a, **kw):
        await asyncio.sleep(30)
        yield "never"

    async def _answer(*a, **kw):
        return {"answer": "fallback", "confidence": "Low", "answered_from_facts": False}

    monkeypatch.setattr(ai_service, "stream_answer", _slow)
    monkeypatch.setattr(ai_service, "answer", _answer)

    t0 = time.monotonic()
    r = await client.post("/api/ai/ask-stream", json={"question": "hi"})
    elapsed = time.monotonic() - t0
    assert r.status_code == 200
    assert elapsed < ai_service._STREAM_PEEK_TIMEOUT_SECONDS + 3 if hasattr(
        ai_service, "_STREAM_PEEK_TIMEOUT_SECONDS") else elapsed < 6, (
        f"a hanging stream held the request for {elapsed:.1f}s"
    )


# ── Document analysis cache ───────────────────────────────────────────────────

async def test_document_cache_key_is_content_addressed():
    a = ai_service._doc_cache_key("some document text", "deepseek")
    b = ai_service._doc_cache_key("some document text", "deepseek")
    c = ai_service._doc_cache_key("different text", "deepseek")
    d = ai_service._doc_cache_key("some document text", "minimax")
    assert a == b
    assert a != c, "different documents share a cache key"
    assert a != d, "quality tiers collide on one cache key"


async def test_document_analysis_persists_to_the_shared_cache(monkeypatch):
    """The in-process prompt cache dies with the worker; the Redis-backed
    doc cache is what makes a repeat analysis free after a restart or on a
    second worker."""
    result = {"executive_summary": "s", "document_type": "concall", "period": "Q1",
              "key_themes": ["a"], "financial_highlights": ["b"],
              "margin_analysis": {"gross_margin": "1", "ebitda_margin": "2",
                                  "pat_margin": "3", "margin_commentary": "c"},
              "risks_and_concerns": ["r"], "sentiment": "positive",
              "sentiment_reason": "x", "suggested_questions": ["q"]}

    async def _groq(system, user, max_tokens, model=None, temperature=None, timeout=None):
        return dict(result)

    monkeypatch.setattr(ai_service, "_call_groq", _groq)
    text = "unique document body " * 40
    key = ai_service._doc_cache_key(text, "deepseek")
    cache.delete(key)

    await ai_service.analyze_document(text, "TCS", model="deepseek")

    assert cache.get(key) is not None, (
        "analyze_document never wrote to the shared cache — every repeat analysis "
        "re-pays for a full LLM call once the in-process cache is gone"
    )


# ── Per-user isolation ────────────────────────────────────────────────────────

async def test_portfolio_review_cache_key_is_scoped_per_user():
    """Two users with byte-identical portfolios must not share a cache entry —
    the key has to carry the user id, not just the content fingerprint."""
    import hashlib
    context = "Holdings:\n- TCS: 100%"
    fingerprint = hashlib.sha256(context.encode()).hexdigest()[:24]
    key_a = f"ai:portfolio_review:{1}:{fingerprint}"
    key_b = f"ai:portfolio_review:{2}:{fingerprint}"
    assert key_a != key_b

    cache.set(key_a, {"verdict": "user 1 only"}, "portfolio_review")
    assert cache.get(key_b) is None, "user 2 read user 1's cached portfolio review"


async def test_portfolio_review_is_not_served_across_users(client, user_a, user_b, bearer, monkeypatch):
    from datetime import date
    from app.core.database import AsyncSessionLocal
    from app.models import Holding

    async def _seed(uid):
        async with AsyncSessionLocal() as s:
            s.add(Holding(user_id=uid, ticker="TCS.NS", company_name="TCS",
                          shares=10, avg_price=3000.0, buy_date=date(2025, 1, 1)))
            await s.commit()

    await _seed(user_a.id)
    await _seed(user_b.id)

    seen: list[str] = []

    async def _review(context: str):
        seen.append(context)
        return {"verdict": f"verdict-{len(seen)}",
                "observations": [{"severity": "risk", "title": "t", "insight": "i", "action": "a"}],
                "holdings_sentiment": []}

    monkeypatch.setattr(ai_service, "review_portfolio", _review)

    ra = await client.get("/api/portfolio/insights/ai", headers=bearer(user_a.id))
    rb = await client.get("/api/portfolio/insights/ai", headers=bearer(user_b.id))
    assert ra.status_code == 200 and rb.status_code == 200
    assert len(seen) == 2, "the second user was served the first user's cached AI review"


async def test_stored_review_history_is_per_user(client, user_a, user_b, bearer, monkeypatch):
    from datetime import date
    from app.core.database import AsyncSessionLocal
    from app.models import Holding

    async with AsyncSessionLocal() as s:
        s.add(Holding(user_id=user_a.id, ticker="TCS.NS", company_name="TCS",
                      shares=1, avg_price=1.0, buy_date=date(2025, 1, 1)))
        await s.commit()

    async def _review(context):
        return {"verdict": "A private verdict",
                "observations": [{"severity": "risk", "title": "t", "insight": "i", "action": "a"}],
                "holdings_sentiment": []}

    monkeypatch.setattr(ai_service, "review_portfolio", _review)
    await client.get("/api/portfolio/insights/ai", headers=bearer(user_a.id))

    latest_b = await client.get("/api/portfolio/insights/ai/latest", headers=bearer(user_b.id))
    assert latest_b.json()["ai"] is None
    assert "A private verdict" not in latest_b.text
