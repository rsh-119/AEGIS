"""API contracts: status codes, validation, error shape, and the behaviour of
public endpoints when every upstream data source is unavailable.

INDIANAPI_ENABLED is false throughout the suite, so these run against the
worst realistic case: no market data at all.
"""

from __future__ import annotations

import pytest

PUBLIC_GETS = [
    "/api/health",
    "/health/live",
    "/health/ready",
    "/health/status",
    "/metrics",
    "/api/ai/diagnostics",
    "/api/stocks/TCS.NS/history",
    "/api/stocks/TCS.NS/news",
    "/api/stocks/TCS.NS/core",
    "/api/stocks/TCS.NS/peers",
    "/api/stocks/TCS.NS/financials",
    "/api/stocks/TCS.NS/insights",
    "/api/stocks/TCS.NS/announcements",
    "/api/stocks/TCS.NS/corporate-actions",
    "/api/stocks/TCS.NS/credit-ratings",
    "/api/stocks/TCS.NS/annual-reports",
    "/api/stocks/TCS.NS/concall-transcripts",
    "/api/stocks/TCS.NS/shareholding-history",
    "/api/stocks/TCS.NS/logo",
    "/api/stocks/search?q=tcs",
    "/api/stocks/batch-quotes?tickers=TCS.NS,INFY.NS",
    "/api/market/overview",
]


# ── Degradation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", PUBLIC_GETS)
async def test_public_endpoints_never_500_without_upstream_data(client, url):
    r = await client.get(url)
    assert r.status_code < 500, f"{url} -> {r.status_code}: {r.text[:300]}"


@pytest.mark.parametrize("url", PUBLIC_GETS + ["/api/stocks/TCS.NS/quote"])
async def test_public_endpoints_never_leak_stack_traces(client, url):
    r = await client.get(url)
    body = r.text
    for marker in ("Traceback", "site-packages", "/home/", 'File "', "asyncpg."):
        assert marker not in body, f"{url} leaked {marker!r}"


async def test_quote_for_an_unknown_symbol_is_a_clean_503(client):
    r = await client.get("/api/stocks/NOSUCHSYMBOL.NS/quote")
    assert r.status_code == 503
    assert "detail" in r.json()
    assert "Traceback" not in r.text


async def test_history_degrades_to_empty_candles_rather_than_erroring(client):
    r = await client.get("/api/stocks/TCS.NS/history")
    assert r.status_code == 200
    assert isinstance(r.json().get("candles"), list)


async def test_batch_quotes_returns_per_ticker_errors_not_a_global_failure(client):
    r = await client.get("/api/stocks/batch-quotes?tickers=TCS.NS,BOGUS.NS")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"TCS.NS", "BOGUS.NS"}


async def test_batch_quotes_caps_the_ticker_list(client):
    tickers = ",".join(f"T{i}.NS" for i in range(200))
    r = await client.get(f"/api/stocks/batch-quotes?tickers={tickers}")
    assert r.status_code == 200
    assert len(r.json()) <= 30, "batch-quotes fanned out beyond its documented 30-ticker cap"


async def test_batch_quotes_rejects_a_missing_parameter(client):
    assert (await client.get("/api/stocks/batch-quotes")).status_code == 422


# ── Input validation ──────────────────────────────────────────────────────────

async def test_search_requires_a_minimum_query_length(client):
    assert (await client.get("/api/stocks/search?q=a")).status_code == 422
    assert (await client.get("/api/stocks/search")).status_code == 422


async def test_history_normalises_an_unknown_period(client):
    r = await client.get("/api/stocks/TCS.NS/history?period=banana")
    assert r.status_code == 200


@pytest.mark.parametrize("ticker", [
    "../../etc/passwd", "TCS.NS%00", "<script>alert(1)</script>",
    "'; DROP TABLE users; --", "A" * 500, "🏦",
])
async def test_hostile_ticker_paths_are_handled_safely(client, ticker):
    import urllib.parse
    r = await client.get(f"/api/stocks/{urllib.parse.quote(ticker, safe='')}/quote")
    # 503 is the documented "upstream has no data" answer and is fine here;
    # what must never happen is an unhandled 500 or a leaked trace.
    assert r.status_code in (200, 404, 422, 503), f"{ticker!r} -> {r.status_code}"
    assert "Traceback" not in r.text and "site-packages" not in r.text


async def test_alert_type_is_constrained(client, user_a, bearer):
    r = await client.post("/api/alerts", json={
        "ticker": "TCS.NS", "alert_type": "sideways", "target_price": 100,
    }, headers=bearer(user_a.id))
    assert r.status_code == 422


async def test_alert_target_price_must_be_positive(client, user_a, bearer):
    for price in (0, -1):
        r = await client.post("/api/alerts", json={
            "ticker": "TCS.NS", "alert_type": "above", "target_price": price,
        }, headers=bearer(user_a.id))
        assert r.status_code == 422


async def test_ask_rejects_an_empty_portfolio_question(client, user_a, bearer):
    r = await client.post("/api/portfolio/ask", json={"question": ""}, headers=bearer(user_a.id))
    assert r.status_code == 400


async def test_portfolio_ask_caps_question_length(client, user_a, bearer):
    r = await client.post("/api/portfolio/ask", json={"question": "x" * 5000},
                          headers=bearer(user_a.id))
    assert r.status_code == 400


async def test_ai_ask_caps_question_length(client):
    """/api/ai/ask has no auth and no length bound on `question`; the whole
    string is placed into the provider prompt."""
    r = await client.post("/api/ai/ask", json={"question": "x" * 200_000})
    assert r.status_code == 422, (
        f"/api/ai/ask accepted a 200 KB question ({r.status_code}) — an "
        "unauthenticated caller controls the full prompt size"
    )


async def test_chat_caps_message_and_history(client):
    r = await client.post("/api/chat", json={
        "message": "x" * 100_000,
        "history": [{"role": "user", "content": "y" * 1000} for _ in range(500)],
    })
    assert r.status_code == 422, (
        f"/api/chat accepted an unbounded message+history ({r.status_code})"
    )


@pytest.mark.parametrize("url,body", [
    ("/api/auth/register", {}),
    ("/api/auth/login", {}),
    ("/api/auth/google", {}),
    ("/api/chat", {}),
    ("/api/ai/ask", {}),
])
async def test_missing_required_fields_are_422(client, url, body):
    assert (await client.post(url, json=body)).status_code == 422


async def test_malformed_json_is_422_not_500(client):
    r = await client.post("/api/auth/login", content=b"{broken",
                          headers={"Content-Type": "application/json"})
    assert r.status_code == 422


async def test_wrong_content_type_is_handled(client):
    r = await client.post("/api/auth/login", content=b"email=a&password=b",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code in (415, 422)


async def test_extra_fields_are_ignored_not_rejected(client, user_a):
    r = await client.post("/api/auth/login", json={
        "email": user_a.email, "password": "CorrectHorse1!x", "is_admin": True,
    })
    assert r.status_code == 200
    assert r.json()["is_admin"] is False, "a client-supplied field reached the model"


# ── Error shape ───────────────────────────────────────────────────────────────

async def test_404_has_a_json_body(client):
    r = await client.get("/api/definitely/not/a/route")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


async def test_405_on_a_wrong_method(client):
    assert (await client.delete("/api/auth/login")).status_code == 405


async def test_auth_errors_use_a_consistent_detail_key(client):
    for url in ("/api/auth/me", "/api/portfolio", "/api/watchlist", "/api/alerts"):
        r = await client.get(url)
        assert r.status_code == 401
        assert "detail" in r.json(), f"{url} used a non-standard error shape"


async def test_validation_errors_use_the_standard_fastapi_shape(client):
    r = await client.post("/api/auth/login", json={})
    body = r.json()
    assert "detail" in body and isinstance(body["detail"], list)


# ── Docs exposure ─────────────────────────────────────────────────────────────

async def test_docs_are_available_in_development(client):
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200


def test_docs_are_disabled_when_app_env_is_production():
    """docs_url/redoc_url/openapi_url are fixed when FastAPI is instantiated,
    so this builds a SECOND app in a clean interpreter with
    APP_ENV=production and asks it for the routes.

    The previous version grepped app/main.py for the three literal expressions.
    That passes whether or not the flags actually take effect — it would keep
    passing if FastAPI changed how the arguments are honoured, or if a later
    line re-enabled the routes — and it fails on a harmless reformat. Asserting
    on the constructed app measures the property itself.
    """
    import json
    import os
    import subprocess
    import sys

    code = r"""
import os, json
os.environ["APP_ENV"] = "production"
os.environ["JWT_SECRET_KEY"] = "production-mode-secret-at-least-32-chars-long"
from app.main import app
from fastapi.testclient import TestClient
paths = []
def walk(routes):
    for r in routes:
        p = getattr(r, "path", None)
        if p:
            paths.append(p)
        walk(getattr(r, "routes", []) or [])
walk(app.routes)
with TestClient(app) as c:
    codes = {u: c.get(u).status_code for u in ("/docs", "/redoc", "/openapi.json")}
print(json.dumps({
    "docs_url": app.docs_url, "redoc_url": app.redoc_url,
    "openapi_url": app.openapi_url,
    "doc_paths_present": [p for p in paths if p in ("/docs", "/redoc", "/openapi.json")],
    "codes": codes,
}))
"""
    env = {**os.environ, "APP_ENV": "production"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, env=env, cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.returncode == 0, f"production app failed to start:\n{out.stderr[-2000:]}"
    got = json.loads(out.stdout.strip().splitlines()[-1])

    assert got["docs_url"] is None, "interactive docs are enabled in production"
    assert got["redoc_url"] is None, "redoc is enabled in production"
    assert got["openapi_url"] is None, "the OpenAPI schema is served in production"
    assert got["doc_paths_present"] == [], (
        f"documentation routes are still registered in production: {got['doc_paths_present']}"
    )
    for url, code in got["codes"].items():
        assert code == 404, f"{url} returned {code} in production, expected 404"


async def test_openapi_schema_exposes_no_secret_values(client):
    """Env-var *names* appearing in a docstring are fine; actual configured
    values are not."""
    from app.core.config import get_settings
    settings = get_settings()
    body = (await client.get("/openapi.json")).text
    for secret in (settings.jwt_secret_key, settings.database_url,
                   settings.groq_api_key, settings.totp_encryption_key):
        if secret:
            assert secret not in body, "OpenAPI schema contains a configured secret value"
    assert "hashed_password" not in body
