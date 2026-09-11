"""AI provider waterfall, prompt caching and the Groq streaming breaker.

Every provider is mocked at its own call boundary so fallback order can be
observed exactly. No test here may reach a real provider.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from groq import APIStatusError as GroqAPIStatusError, RateLimitError as GroqRateLimitError
from pydantic import BaseModel

from app.services import ai_service


class _Schema(BaseModel):
    answer: str


GOOD = {"answer": "ok"}


@pytest.fixture(autouse=True)
def _reset_ai_state(monkeypatch):
    ai_service._prompt_cache._store.clear()
    ai_service._provider_calls.clear() if hasattr(ai_service, "_provider_calls") else None
    from app.core import groq_circuit_breaker as cb
    cb._failure_times.clear()
    cb._opened_until = 0.0
    yield
    ai_service._prompt_cache._store.clear()
    cb._failure_times.clear()
    cb._opened_until = 0.0


def _record(calls: list, name: str, *, result=None, exc: Exception | None = None,
            delay: float = 0.0):
    async def _fn(system, user, max_tokens, model=None, temperature=None, timeout=None):
        calls.append(name)
        if delay:
            await asyncio.sleep(delay)
        if exc:
            raise exc
        return dict(result if result is not None else GOOD)
    return _fn


def _groq_error(status: int) -> Exception:
    resp = httpx.Response(status, request=httpx.Request("POST", "https://api.groq.com"))
    if status == 429:
        return GroqRateLimitError("rate limited", response=resp, body=None)
    return GroqAPIStatusError("upstream error", response=resp, body=None)


# ── Ordering ──────────────────────────────────────────────────────────────────

async def test_groq_serves_first_when_healthy(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq"))
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "openrouter"))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    result = await ai_service._chat_json("sys", "user", use_cache=False)
    assert result["answer"] == "ok"
    assert calls == ["groq"], f"unnecessary providers were called: {calls}"
    assert result["_provider"].startswith("groq/")


async def test_groq_failure_falls_through_to_openrouter_then_nvidia(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq", exc=RuntimeError("boom")))
    monkeypatch.setattr(ai_service, "_call_openrouter",
                        _record(calls, "openrouter", exc=RuntimeError("boom")))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    result = await ai_service._chat_json("sys", "user", use_cache=False)
    assert result["answer"] == "ok"
    assert calls[0] == "groq"
    assert "openrouter" in calls and calls[-1] == "nvidia"


async def test_prefer_openrouter_puts_openrouter_first_and_skips_it_later(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "openrouter"))
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq"))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    await ai_service._chat_json("sys", "user", use_cache=False, prefer_openrouter=True)
    assert calls == ["openrouter"]


async def test_openrouter_is_not_retried_after_the_preferred_attempt_failed(monkeypatch):
    """Once the preferred route has exhausted OpenRouter's model list, the
    later stage must not run it a second time."""
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_openrouter",
                        _record(calls, "openrouter", exc=RuntimeError("down")))
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq", exc=RuntimeError("down")))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    await ai_service._chat_json("sys", "user", use_cache=False, prefer_openrouter=True)
    groq_index = calls.index("groq")
    assert "openrouter" not in calls[groq_index:], f"OpenRouter retried after Groq: {calls}"


async def test_groq_429_advances_to_the_next_groq_model_before_leaving_the_provider(monkeypatch):
    calls: list[str] = []
    seen_models: list[str] = []

    async def _groq(system, user, max_tokens, model=None, temperature=None, timeout=None):
        calls.append("groq")
        seen_models.append(model)
        raise _groq_error(429)

    monkeypatch.setattr(ai_service, "_call_groq", _groq)
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "openrouter"))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    await ai_service._chat_json("sys", "user", use_cache=False)
    assert len(seen_models) >= 2, f"a 429 abandoned Groq without trying its fallback models: {seen_models}"
    assert "openrouter" in calls


# ── Provider failure modes ────────────────────────────────────────────────────

@pytest.mark.parametrize("exc", [
    asyncio.TimeoutError(),
    json.JSONDecodeError("bad json", "", 0),
    httpx.ConnectError("no route to host"),
    httpx.ReadTimeout("slow"),
    RuntimeError("unexpected"),
    ValueError("garbage"),
])
async def test_every_provider_failure_mode_falls_through_cleanly(monkeypatch, exc):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq", exc=exc))
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "openrouter", exc=exc))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    result = await ai_service._chat_json("sys", "user", use_cache=False)
    assert result["answer"] == "ok", f"{type(exc).__name__} was not survivable"


async def test_all_providers_down_returns_a_clean_user_facing_error(monkeypatch):
    for name in ("_call_groq", "_call_openrouter", "_call_nvidia"):
        monkeypatch.setattr(ai_service, name, _record([], name, exc=RuntimeError("down")))

    result = await ai_service._chat_json("sys", "user", use_cache=False)
    assert "error" in result
    assert "temporarily unavailable" in result["error"].lower()


async def test_total_failure_never_leaks_provider_internals_to_the_user(monkeypatch):
    secret = "sk-live-groq-abcdef123456"
    for name in ("_call_groq", "_call_openrouter", "_call_nvidia"):
        monkeypatch.setattr(ai_service, name,
                            _record([], name, exc=RuntimeError(f"401 unauthorized key={secret}")))

    result = await ai_service._chat_json("sys", "user", use_cache=False)
    blob = json.dumps(result)
    assert secret not in blob, "an API key from a provider error reached the response"
    assert "401" not in blob and "unauthorized" not in blob.lower()


async def test_empty_provider_response_is_treated_as_a_failure(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq", result={}))
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "openrouter"))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    result = await ai_service._chat_json("sys", "user", use_cache=False, schema=_Schema)
    assert result.get("answer") == "ok"
    assert "openrouter" in calls, f"an empty response was accepted as success: {calls}"


# ── Schema validation and repair ──────────────────────────────────────────────

async def test_invalid_schema_triggers_exactly_one_repair_retry(monkeypatch):
    attempts: list[float | None] = []

    async def _groq(system, user, max_tokens, model=None, temperature=None, timeout=None):
        attempts.append(temperature)
        return {"wrong_field": 1} if len(attempts) == 1 else dict(GOOD)

    monkeypatch.setattr(ai_service, "_call_groq", _groq)
    result = await ai_service._chat_json("sys", "user", use_cache=False, schema=_Schema)
    assert result["answer"] == "ok"
    assert len(attempts) == 2, f"expected one repair retry, got {len(attempts)} attempts"
    assert attempts[1] == 0.0, "repair pass did not drop to temperature 0"


async def test_a_provider_that_fails_repair_is_abandoned_for_the_next(monkeypatch):
    calls: list[str] = []

    async def _bad(system, user, max_tokens, model=None, temperature=None, timeout=None):
        calls.append("groq")
        return {"wrong_field": 1}

    monkeypatch.setattr(ai_service, "_call_groq", _bad)
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "openrouter"))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nvidia"))

    result = await ai_service._chat_json("sys", "user", use_cache=False, schema=_Schema)
    assert result["answer"] == "ok"
    assert "openrouter" in calls


# ── Latency bounds ────────────────────────────────────────────────────────────

async def test_a_hanging_provider_cannot_hang_the_request_forever(monkeypatch):
    """Each Groq attempt but the last is capped at GROQ_FAST_TIMEOUT so a slow
    provider cannot eat the whole budget before a fallback is even tried."""
    seen: list[float | None] = []

    async def _groq(system, user, max_tokens, model=None, temperature=None, timeout=None):
        seen.append(timeout)
        raise asyncio.TimeoutError()

    monkeypatch.setattr(ai_service, "_call_groq", _groq)
    monkeypatch.setattr(ai_service, "_call_openrouter", _record([], "or"))
    await ai_service._chat_json("sys", "user", use_cache=False)
    assert seen and seen[0] <= ai_service.GROQ_FAST_TIMEOUT, (
        f"first Groq attempt used a {seen[0]}s budget, not the short leash"
    )


# ── Prompt cache ──────────────────────────────────────────────────────────────

async def test_identical_prompts_skip_every_provider(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq"))

    await ai_service._chat_json("sys", "same", use_cache=True)
    await ai_service._chat_json("sys", "same", use_cache=True)
    assert calls == ["groq"], f"prompt cache missed on an identical prompt: {calls}"


async def test_a_different_prompt_is_not_served_from_cache(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq"))

    await ai_service._chat_json("sys", "first", use_cache=True)
    await ai_service._chat_json("sys", "second", use_cache=True)
    assert len(calls) == 2


async def test_use_cache_false_always_calls_a_provider(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(ai_service, "_call_groq", _record(calls, "groq"))
    await ai_service._chat_json("sys", "same", use_cache=False)
    await ai_service._chat_json("sys", "same", use_cache=False)
    assert len(calls) == 2


async def test_failures_are_never_cached(monkeypatch):
    calls: list[str] = []
    state = {"fail": True}

    async def _groq(system, user, max_tokens, model=None, temperature=None, timeout=None):
        calls.append("groq")
        if state["fail"]:
            raise RuntimeError("down")
        return dict(GOOD)

    monkeypatch.setattr(ai_service, "_call_groq", _groq)
    monkeypatch.setattr(ai_service, "_call_openrouter", _record(calls, "or", exc=RuntimeError("down")))
    monkeypatch.setattr(ai_service, "_call_nvidia", _record(calls, "nv", exc=RuntimeError("down")))

    first = await ai_service._chat_json("sys", "u", use_cache=True)
    assert "error" in first

    state["fail"] = False
    second = await ai_service._chat_json("sys", "u", use_cache=True)
    assert second.get("answer") == "ok", "an error response was cached and replayed"


async def test_prompt_cache_is_bounded(monkeypatch):
    """Anonymous, unbounded-length prompts reach this cache (/api/ai/ask,
    /api/chat). An entry is only ever evicted when that exact key is looked
    up again after expiry, so distinct prompts accumulate for the full TTL."""
    monkeypatch.setattr(ai_service, "_call_groq", _record([], "groq"))
    ai_service._prompt_cache._store.clear()

    for i in range(2000):
        await ai_service._chat_json("sys", f"unique-question-{i}", use_cache=True)

    size = len(ai_service._prompt_cache._store)
    assert size <= 1000, (
        f"prompt cache holds {size} entries after 2000 distinct prompts with no "
        "eviction policy — unbounded growth on an unauthenticated path"
    )
