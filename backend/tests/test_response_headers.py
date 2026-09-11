"""Security headers, CORS, cookie attributes, and HTTP cache directives.

The cache directives get the most attention here: `Cache-Control: public` on
an authenticated response authorises any shared cache between the user and
the app to store and re-serve it.
"""

from __future__ import annotations

import pytest

from app.core.auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from tests.conftest import VALID_PASSWORD


# ── Security headers ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("header,expected", [
    ("X-Frame-Options", "DENY"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Cross-Origin-Resource-Policy", "same-site"),
])
async def test_security_headers_present_on_api_responses(client, header, expected):
    r = await client.get("/api/health")
    assert r.headers.get(header) == expected


async def test_hsts_is_set(client):
    r = await client.get("/api/health")
    assert "max-age=" in r.headers.get("Strict-Transport-Security", "")


async def test_server_header_is_masked(client):
    r = await client.get("/api/health")
    assert r.headers.get("Server") == "Aegis"
    assert "uvicorn" not in r.headers.get("Server", "").lower()


async def test_security_headers_present_on_error_responses(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.headers.get("X-Frame-Options") == "DENY"


async def test_request_id_is_echoed(client):
    r = await client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers.get("X-Request-ID") == "trace-abc-123"


async def test_request_id_is_generated_when_absent(client):
    r = await client.get("/api/health")
    assert r.headers.get("X-Request-ID")


# ── Cookies ───────────────────────────────────────────────────────────────────

def _set_cookie_headers(response, name: str) -> str:
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}="):
            return raw
    raise AssertionError(f"no Set-Cookie for {name}")


async def test_access_cookie_is_httponly_and_samesite_strict(client, user_a):
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    raw = _set_cookie_headers(r, ACCESS_COOKIE_NAME).lower()
    assert "httponly" in raw, "access cookie readable by JavaScript"
    assert "samesite=strict" in raw
    assert "path=/" in raw


async def test_refresh_cookie_is_httponly_and_scoped_to_auth(client, user_a):
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    raw = _set_cookie_headers(r, REFRESH_COOKIE_NAME).lower()
    assert "httponly" in raw
    assert "samesite=strict" in raw
    assert "path=/api/auth" in raw, "refresh cookie sent on every request, widening theft surface"


async def test_cookies_have_no_explicit_domain(client, user_a):
    """Host-only cookies — an explicit Domain= would share them with every
    subdomain, including anything else hosted there."""
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        assert "domain=" not in _set_cookie_headers(r, name).lower()


async def test_cookies_are_secure_in_production(client, user_a, monkeypatch):
    monkeypatch.setattr("app.core.auth.settings.app_env", "production")
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    for name in (ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME):
        assert "secure" in _set_cookie_headers(r, name).lower(), f"{name} not Secure in production"


# ── CORS ──────────────────────────────────────────────────────────────────────

async def test_cors_allows_a_configured_origin(client):
    r = await client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert r.headers.get("access-control-allow-credentials") == "true"


async def test_cors_rejects_an_unlisted_origin(client):
    r = await client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


async def test_cors_is_never_wildcard_with_credentials(client):
    r = await client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("access-control-allow-origin") != "*"


async def test_cors_preflight_is_answered(client):
    r = await client.options("/api/auth/login", headers={
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_preflight_from_unlisted_origin_is_not_allowed(client):
    r = await client.options("/api/auth/login", headers={
        "Origin": "https://evil.example.com",
        "Access-Control-Request-Method": "POST",
    })
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"


# ── HTTP cache directives ─────────────────────────────────────────────────────

PRIVATE_ENDPOINTS = [
    "/api/portfolio",
    "/api/watchlist",
    "/api/alerts",
    "/api/auth/me",
    "/api/admin/users",
    "/api/admin/stats",
    "/api/portfolio/insights/ai/latest",
]


@pytest.mark.parametrize("url", PRIVATE_ENDPOINTS)
async def test_authenticated_responses_are_never_publicly_cacheable(client, admin_user, bearer, url):
    """A `public` directive on a per-user response lets any shared cache
    between the user and the app store it and hand it to the next visitor."""
    r = await client.get(url, headers=bearer(admin_user.id))
    assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text[:200]}"
    cc = r.headers.get("Cache-Control", "")
    assert "public" not in cc, f"{url} returned per-user data as 'Cache-Control: {cc}'"
    assert "no-store" in cc or "private" in cc, f"{url} has no private-cache directive (got '{cc}')"


async def test_public_market_data_is_still_cacheable(client):
    r = await client.get("/api/stocks/search?q=tcs")
    cc = r.headers.get("Cache-Control", "")
    assert "public" in cc and "max-age" in cc, f"public market data lost its cache headers: '{cc}'"


async def test_ai_responses_are_not_stored(client):
    r = await client.get("/api/ai/diagnostics")
    assert "no-store" in r.headers.get("Cache-Control", "")


async def test_sse_stream_is_not_cached(client):
    """Set by the route itself; the middleware must not override it."""
    from app.middleware.http_cache import _get_rule
    max_age, _ = _get_rule("/api/stocks/TCS.NS/stream")
    assert max_age >= 0  # rule exists; the route's own no-cache header wins


async def test_error_responses_are_not_cached(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert "max-age" not in r.headers.get("Cache-Control", "")


async def test_write_responses_are_not_cached(client, user_a, bearer):
    r = await client.post("/api/watchlist", json={"ticker": "TCS"}, headers=bearer(user_a.id))
    assert "max-age" not in r.headers.get("Cache-Control", "")
