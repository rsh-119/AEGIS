"""The internal `_provider` tag must not cross the HTTP boundary.

Every waterfall return path in ai_service stamps the result with `_provider`
(e.g. "groq/openai/gpt-oss-120b") so per-provider latency can be attributed in
metrics. It is operational telemetry, not part of any API contract — nothing in
the frontend reads it — and publishing it tells a caller which vendor and which
exact model backs each feature, and lets them detect from the outside when the
service has fallen through to a degraded fallback tier.

These tests drive the real routes with a stubbed provider so the assertion is
about what the API actually returns, not about what the helper does in
isolation.
"""

from __future__ import annotations

import pytest

from app.services import ai_service


PROVIDER_TAG = "groq/some-internal-model-id"


@pytest.fixture
def stub_provider(monkeypatch):
    """Make every provider call succeed, returning a payload that satisfies
    each route's schema AND carries the internal tag the waterfall would add."""
    async def _ok(system, user, max_tokens, model=None, temperature=None, timeout=None):
        return {
            # AskResponse
            "answer": "ok", "confidence": "High", "answered_from_facts": True,
            # ChatResponse / generic
            "reply": "ok", "message": "ok",
            # DocumentAnalysisResponse — every required field, so the route
            # returns 200 and the assertion is about disclosure, not validation.
            "executive_summary": "ok",
            "document_type": "concall",
            "company_name": "TCS",
            "period": "Q1 FY26",
            "key_themes": ["growth"],
            "financial_highlights": ["revenue +18% YoY"],
            "margin_analysis": {
                "gross_margin": "40%", "ebitda_margin": "25%",
                "pat_margin": "18%", "margin_commentary": "stable",
            },
            "risks_and_concerns": ["currency"],
            "sentiment": "Positive",
            "sentiment_reason": "margins held",
            "suggested_questions": ["What drove margin expansion?"],
            "_provider": PROVIDER_TAG,
        }

    for fn in ("_call_groq", "_call_openrouter", "_call_nvidia", "_call_gemini"):
        if hasattr(ai_service, fn):
            monkeypatch.setattr(ai_service, fn, _ok)
    ai_service._prompt_cache.clear() if hasattr(ai_service._prompt_cache, "clear") else None
    yield


def _assert_clean(body, where: str):
    """No key anywhere in the payload may start with '_'. The convention is
    prefix-based on purpose: a field added later is private by default."""
    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                assert not (isinstance(k, str) and k.startswith("_")), (
                    f"{where}: internal field {path}.{k} leaked to the client "
                    f"(value={v!r})"
                )
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(body)
    assert PROVIDER_TAG not in str(body), f"{where}: the provider tag appears in the body"


async def test_ask_does_not_disclose_the_provider(client, stub_provider):
    r = await client.post("/api/ai/ask", json={"question": "what is the outlook?"})
    assert r.status_code == 200
    _assert_clean(r.json(), "POST /api/ai/ask")


async def test_chat_does_not_disclose_the_provider(client, stub_provider):
    """/api/chat builds its response dict field-by-field rather than splatting
    the model result, so it never disclosed the provider. This is a guard
    against that changing to `**result` later, not evidence of a fixed bug —
    recorded as such so the suite is not read as proving more than it does."""
    r = await client.post("/api/chat", json={"message": "hello", "history": []})
    assert r.status_code == 200
    _assert_clean(r.json(), "POST /api/chat")


async def test_document_analysis_does_not_disclose_the_provider(client, pro_user, bearer, stub_provider):
    r = await client.post(
        "/api/documents/analyze",
        json={"text": "Revenue grew 18% YoY. " * 40, "company": "TCS", "model": "deepseek"},
        headers=bearer(pro_user.id),
    )
    assert r.status_code == 200, r.text[:300]
    _assert_clean(r.json(), "POST /api/documents/analyze")


async def test_document_qa_does_not_disclose_the_provider(client, pro_user, bearer, stub_provider):
    r = await client.post(
        "/api/documents/ask",
        json={"text": "Revenue grew 18% YoY. " * 40, "question": "How did revenue do?",
              "company": "TCS"},
        headers=bearer(pro_user.id),
    )
    assert r.status_code == 200, r.text[:300]
    _assert_clean(r.json(), "POST /api/documents/ask")


async def test_the_provider_is_still_recorded_internally(stub_provider):
    """Stripping is a presentation concern only — the provider must still reach
    metrics, or per-provider latency attribution silently dies with it."""
    from app.schemas import AskResponse

    before = dict(ai_service.get_provider_stats())
    result = await ai_service._chat_json("sys", "user-unique-prompt-for-stats",
                                         max_tokens=100, schema=AskResponse,
                                         use_cache=False)
    assert result.get("_provider"), "the service layer stopped tagging the provider"
    after = ai_service.get_provider_stats()
    assert after != before or any(after.values()), (
        "provider stats were not updated — telemetry was lost along with the field"
    )

    assert "_provider" not in ai_service.public_result(result)
