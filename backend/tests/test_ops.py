"""Operational surface: read-only mode, health/readiness separation,
observability, log hygiene, and behaviour when each dependency is down."""

from __future__ import annotations

import json
import logging
from datetime import date

import httpx
import pytest

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models import Holding
from tests.conftest import VALID_PASSWORD

settings = get_settings()


# ── Read-only mode ────────────────────────────────────────────────────────────

@pytest.fixture
def readonly(monkeypatch):
    monkeypatch.setattr(settings, "readonly_mode", True)
    yield
    monkeypatch.setattr(settings, "readonly_mode", False)


@pytest.mark.parametrize("method,url,body", [
    ("post", "/api/watchlist", {"ticker": "TCS.NS"}),
    ("post", "/api/portfolio", {"ticker": "TCS.NS", "shares": 1,
                                "avg_price": 1, "buy_date": "2025-01-01"}),
    ("post", "/api/alerts", {"ticker": "TCS.NS", "alert_type": "above", "target_price": 1}),
    ("delete", "/api/watchlist/1", None),
    ("patch", "/api/alerts/1", {"is_active": False}),
])
async def test_readonly_blocks_writes(client, user_a, bearer, readonly, method, url, body):
    kwargs = {"headers": bearer(user_a.id)}
    if body is not None:
        kwargs["json"] = body
    r = await getattr(client, method)(url, **kwargs)
    assert r.status_code == 503
    assert r.json()["readonly"] is True
    assert r.headers.get("Retry-After") == "300"


@pytest.mark.parametrize("url", [
    "/api/health", "/health/live", "/health/ready",
    "/api/stocks/TCS.NS/history", "/api/market/overview",
])
async def test_readonly_keeps_reads_working(client, readonly, url):
    assert (await client.get(url)).status_code < 500


async def test_readonly_still_allows_authenticated_reads(client, user_a, bearer, readonly):
    async with AsyncSessionLocal() as s:
        s.add(Holding(user_id=user_a.id, ticker="TCS.NS", shares=1,
                      avg_price=1.0, buy_date=date(2025, 1, 1)))
        await s.commit()
    assert (await client.get("/api/portfolio", headers=bearer(user_a.id))).status_code == 200


async def test_readonly_allows_the_full_session_lifecycle(client, user_a, readonly):
    """Read-only mode must degrade to read-only BROWSING, not to anonymous-only.

    Login/refresh/logout mutate session state (a Redis key and a cookie), not
    market or user data, so they stay open — otherwise flipping the switch
    during an incident locks every user out of reading their own portfolio,
    and expired sessions cannot even be refreshed.
    """
    login = await client.post("/api/auth/login",
                              json={"email": user_a.email, "password": VALID_PASSWORD})
    assert login.status_code == 200, (
        f"login must survive read-only mode: {login.status_code} {login.text[:200]}"
    )

    refresh = await client.post("/api/auth/refresh")
    assert refresh.status_code == 200, "refresh must survive read-only mode"

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 200, (
        "logout must survive read-only mode — otherwise a user who believes "
        "they signed out has not, and a stolen token cannot be revoked"
    )


@pytest.mark.parametrize("method,url,body", [
    # Everything under /api/auth that writes USER data, as opposed to session
    # state, must still be blocked. An accidental `/api/auth` prefix match in
    # the allowlist would open every one of these.
    ("post",  "/api/auth/register", {"email": "ro@example.com", "username": "rouser",
                                     "password": VALID_PASSWORD}),
    ("patch", "/api/auth/me", {"username": "renamed"}),
    ("post",  "/api/auth/forgot-password", {"email": "ro@example.com"}),
    ("post",  "/api/auth/reset-password", {"token": "x" * 40, "new_password": VALID_PASSWORD}),
    ("post",  "/api/auth/change-password", {"current_password": VALID_PASSWORD,
                                            "new_password": VALID_PASSWORD}),
    ("post",  "/api/auth/sync-guest-data", {"holdings": [], "watchlist": []}),
    ("post",  "/api/auth/2fa/setup", None),
])
async def test_readonly_still_blocks_user_data_writes_under_api_auth(
    client, user_a, bearer, readonly, method, url, body
):
    kwargs = {"headers": bearer(user_a.id)}
    if body is not None:
        kwargs["json"] = body
    r = await getattr(client, method)(url, **kwargs)
    assert r.status_code == 503, (
        f"{method.upper()} {url} writes user data and must stay blocked in "
        f"read-only mode, got {r.status_code}"
    )
    assert r.json()["readonly"] is True


async def test_readonly_off_by_default(client, user_a, bearer):
    r = await client.post("/api/watchlist", json={"ticker": "TCS.NS"}, headers=bearer(user_a.id))
    assert r.status_code == 201


# ── Health / readiness separation ─────────────────────────────────────────────

async def test_liveness_is_cheap_and_always_ok(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


async def test_liveness_stays_up_when_the_database_is_down(client, monkeypatch):
    """A liveness failure restarts the pod; a dead database must not cause a
    restart loop."""
    from app.core import database

    class _Broken:
        def connect(self):
            raise ConnectionError("db down")

    monkeypatch.setattr(database, "engine", _Broken())
    monkeypatch.setattr("app.routers.health.engine", _Broken())
    assert (await client.get("/health/live")).status_code == 200


async def test_readiness_reports_ok_when_dependencies_are_up(client):
    r = await client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "ok"


async def test_readiness_fails_when_the_database_is_down(client, monkeypatch):
    class _BrokenEngine:
        def connect(self):
            raise ConnectionError("db down")

    monkeypatch.setattr("app.routers.health.engine", _BrokenEngine())
    r = await client.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"


async def test_readiness_tolerates_redis_being_degraded(client, monkeypatch):
    """Redis is a soft dependency — degraded, not out of rotation."""
    from app.core.cache import cache

    class _BrokenRedis:
        def ping(self):
            raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "_redis", _BrokenRedis())
    r = await client.get("/health/ready")
    assert r.status_code == 200, "a Redis blip pulled the instance out of the load balancer"
    assert r.json()["checks"]["redis"]["status"] == "degraded"


async def test_readiness_does_not_echo_raw_driver_errors(client, monkeypatch):
    """/health/ready is unauthenticated and echoes str(exc)[:200] from the
    database check. Real asyncpg failures carry the DB username
    ('password authentication failed for user "aegis"') or the host and port
    ("Connect call failed ('10.0.0.5', 5432)"), so an outage hands infra
    details to anyone probing the endpoint."""
    class _BrokenEngine:
        def connect(self):
            raise ConnectionError('password authentication failed for user "aegis"')

    monkeypatch.setattr("app.routers.health.engine", _BrokenEngine())
    r = await client.get("/health/ready")
    assert r.status_code == 503
    assert "aegis" not in r.text.lower() or "password authentication" not in r.text.lower(), (
        "readiness echoed the raw driver error, exposing the database username"
    )


async def test_health_status_is_admin_gated_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_api_key", "the-admin-key")
    assert (await client.get("/health/status")).status_code == 403
    assert (await client.get("/health/status",
                             headers={"X-Admin-Key": "wrong"})).status_code == 403
    assert (await client.get("/health/status",
                             headers={"X-Admin-Key": "the-admin-key"})).status_code == 200


async def test_health_status_fails_closed_when_no_admin_key_is_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert (await client.get("/health/status")).status_code == 403


async def test_health_status_reports_key_presence_not_key_values(client):
    r = await client.get("/health/status")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["ai"]["groq_key"], bool)
    for secret in (settings.groq_api_key, settings.nvidia_api_key, settings.jwt_secret_key):
        if secret:
            assert secret not in r.text


async def test_cache_flush_is_admin_gated_in_production(client, monkeypatch):
    monkeypatch.setattr("app.main._is_prod", True)
    monkeypatch.setattr(settings, "admin_api_key", "the-admin-key")
    assert (await client.delete("/api/cache")).status_code == 403
    assert (await client.delete("/api/cache",
                                headers={"X-Admin-Key": "the-admin-key"})).status_code == 200


async def test_cache_flush_does_not_accept_the_key_as_a_query_parameter(client, monkeypatch):
    """A key in a query string ends up in proxy access logs."""
    monkeypatch.setattr("app.main._is_prod", True)
    monkeypatch.setattr(settings, "admin_api_key", "the-admin-key")
    r = await client.delete("/api/cache?x_admin_key=the-admin-key")
    assert r.status_code == 403


# ── Metrics ───────────────────────────────────────────────────────────────────

async def test_metrics_exposes_prometheus_text(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "aegis_http_requests_total" in r.text


async def test_metrics_records_requests_by_route_template_not_raw_path(client):
    """Raw paths would create one time series per ticker — unbounded
    cardinality that eventually takes Prometheus down."""
    for t in ("TCS.NS", "INFY.NS", "WIPRO.NS"):
        await client.get(f"/api/stocks/{t}/history")
    body = (await client.get("/metrics")).text
    assert "{ticker}" in body, "metrics are labelled with raw ticker paths"
    assert "TCS.NS" not in body, "per-ticker label values create unbounded cardinality"


async def test_metrics_contains_no_secrets(client):
    body = (await client.get("/metrics")).text
    for secret in (settings.jwt_secret_key, settings.database_url, settings.groq_api_key):
        if secret:
            assert secret not in body


async def test_metrics_is_open_in_development(client):
    """Local dev and docker-compose scrape it with no credentials — keep that
    working, or every developer's Prometheus target goes red."""
    assert (await client.get("/metrics")).status_code == 200


async def test_metrics_requires_the_admin_key_in_production(client, monkeypatch):
    """In production /metrics is behind X-Admin-Key, same as /health/status.
    It leaks no secrets (asserted above) but it does publish the whole route
    inventory, traffic volume and latency distribution."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_api_key", "super-secret-admin-key")

    anon = await client.get("/metrics")
    assert anon.status_code == 403, "production /metrics served to an anonymous caller"

    wrong = await client.get("/metrics", headers={"X-Admin-Key": "not-the-key"})
    assert wrong.status_code == 403

    right = await client.get("/metrics", headers={"X-Admin-Key": "super-secret-admin-key"})
    assert right.status_code == 200
    assert "aegis_http_requests_total" in right.text


async def test_metrics_fails_closed_in_production_when_no_admin_key_is_set(client, monkeypatch):
    """An unset ADMIN_API_KEY must not mean "no check" — that is precisely how
    a guard ends up being a no-op in the one environment it matters in."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert (await client.get("/metrics")).status_code == 403
    assert (await client.get("/metrics", headers={"X-Admin-Key": ""})).status_code == 403


async def test_metrics_public_escape_hatch_reopens_it_for_in_cluster_scrapers(client, monkeypatch):
    """k8s/deployment.yaml scrapes via a prometheus.io/scrape annotation from
    inside the cluster, where the endpoint is not externally reachable. That
    deployment sets METRICS_PUBLIC=true rather than threading a header through
    Prometheus — the opt-in must be explicit and must work."""
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_api_key", "")
    monkeypatch.setattr(settings, "metrics_public", True)
    try:
        assert (await client.get("/metrics")).status_code == 200
    finally:
        monkeypatch.setattr(settings, "metrics_public", False)


async def test_metrics_publishes_the_indianapi_breaker_state(client, monkeypatch):
    """alerting_rules.yml fires on `aegis_circuit_breaker_state == 2` and the
    Grafana panel reads the same gauge, but nothing was ever writing an
    "indianapi" series to it — so the alert for the one upstream with a
    metered monthly quota could never fire."""
    import time as _time
    from app.services import indianapi_service

    monkeypatch.setattr(indianapi_service, "_blocked_until", _time.time() + 300)
    indianapi_service._publish_state(open=True)

    body = (await client.get("/metrics")).text
    assert 'aegis_circuit_breaker_state{service="indianapi"} 2' in body, (
        f"indianapi breaker state is not exported; gauge lines present: "
        f"{[l for l in body.splitlines() if 'circuit_breaker_state' in l]}"
    )


# ── Log hygiene ───────────────────────────────────────────────────────────────

_CANARY = "LOG-PIPELINE-CANARY-b7f2"


def _emit_canary() -> None:
    """Write a known line through the same logger hierarchy the app uses."""
    logging.getLogger("app.routers.auth").debug(_CANARY)


def _captured(caplog) -> str:
    """Joined log output, having first proved the capture pipeline is live.

    Every assertion below is of the form "secret not in <log output>", which
    passes unconditionally when the output is empty. It was empty for two
    independent reasons, and both had to be fixed before these tests meant
    anything:

      1. alembic/env.py called fileConfig() with the default
         disable_existing_loggers=True. init_db() runs that on every startup,
         so all 26 `app.*` loggers were disabled — in the test session AND in
         production. See alembic/env.py.
      2. Even with capture working, a successful login or /me request emits no
         log records at all, so `caplog.records` is legitimately empty and the
         "secret not in logs" check still compares against "".

    So the callers emit a canary through the app's own logger hierarchy, and
    this asserts the canary came back. If logging is disabled, unrouted, or
    filtered, that fails here instead of silently passing the real assertion.
    """
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert _CANARY in blob, (
        "the log-capture pipeline is not live for this test, so the secret "
        "assertion below would pass against an empty string and prove nothing. "
        "See tests/test_log_capture.py and alembic/env.py."
    )
    return blob


async def test_login_does_not_log_credentials(client, user_a, caplog):
    with caplog.at_level(logging.DEBUG):
        _emit_canary()
        await client.post("/api/auth/login",
                          json={"email": user_a.email, "password": "CorrectHorse1!x"})
    blob = _captured(caplog)
    assert "CorrectHorse1!x" not in blob, "the password appeared in logs"


async def test_tokens_are_not_logged(client, user_a, bearer, caplog):
    headers = bearer(user_a.id)
    token = headers["Authorization"].split()[1]
    with caplog.at_level(logging.DEBUG):
        _emit_canary()
        await client.get("/api/auth/me", headers=headers)
    blob = _captured(caplog)
    assert token not in blob, "a JWT appeared in logs"


async def test_reset_token_is_not_logged_when_email_is_configured(
    client, user_a, monkeypatch, caplog,
):
    captured: list[str] = []

    async def _send(to, token):
        captured.append(token)

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _send)
    with caplog.at_level(logging.DEBUG):
        _emit_canary()
        await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    blob = _captured(caplog)
    assert captured, "the reset flow never produced a token — nothing was tested"
    assert captured[0] not in blob, "the password-reset token appeared in logs"


def test_json_log_formatter_emits_request_id_and_no_extras_leak():
    from app.core.logging_config import _JsonFormatter, request_id_var

    request_id_var.set("req-123")
    rec = logging.LogRecord("t", logging.INFO, "f", 1, "hello %s", ("world",), None)
    out = json.loads(_JsonFormatter().format(rec))
    assert out["request_id"] == "req-123"
    assert out["msg"] == "hello world"
    assert out["level"] == "INFO"


# ── External dependency failures ──────────────────────────────────────────────

@pytest.fixture
def broken_http(monkeypatch):
    """Every *outbound* httpx call fails. The in-process test client is also
    an httpx.AsyncClient, so requests to testserver are passed through —
    otherwise the fixture would break the test harness rather than the app."""
    real_get = httpx.AsyncClient.get
    real_post = httpx.AsyncClient.post

    def _is_local(url) -> bool:
        return "testserver" in str(url) or str(url).startswith("/")

    async def _get(self, url, *a, **kw):
        if _is_local(url) or _is_local(self.base_url):
            return await real_get(self, url, *a, **kw)
        raise httpx.ConnectError("network down")

    async def _post(self, url, *a, **kw):
        if _is_local(url) or _is_local(self.base_url):
            return await real_post(self, url, *a, **kw)
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _post)


@pytest.mark.parametrize("url", [
    "/api/stocks/TCS.NS/history",
    "/api/stocks/TCS.NS/news",
    "/api/stocks/TCS.NS/peers",
    "/api/stocks/TCS.NS/financials",
    "/api/market/overview",
    "/api/mf/highlights",
    "/api/stocks/search?q=tcs",
])
async def test_total_network_failure_degrades_without_500(client, broken_http, url):
    r = await client.get(url)
    assert r.status_code < 500, f"{url} -> {r.status_code}: {r.text[:200]}"
    assert "ConnectError" not in r.text, f"{url} leaked the transport exception"


async def test_indianapi_429_opens_the_backoff_circuit(monkeypatch):
    from app.services import indianapi_service as svc

    svc._blocked_until = 0.0
    calls = {"n": 0}

    class _Resp:
        status_code = 429

        def json(self):
            return {}

        def raise_for_status(self):
            pass

    async def _get(self, *a, **kw):
        calls["n"] += 1
        return _Resp()

    # indianapi_service holds its own reference to get_settings, so patch the
    # name it actually calls; the suite otherwise runs with the API disabled.
    monkeypatch.setattr(svc, "get_settings", lambda: type(
        "S", (), {"indianapi_enabled": True, "indianapi_key": "k"})())
    monkeypatch.setattr(httpx.AsyncClient, "get", _get)

    assert await svc._get("/stock") is None
    assert svc.indianapi_blocked() is True
    assert svc.indianapi_backoff_remaining() > 0

    before = calls["n"]
    assert await svc._get("/stock") is None
    assert calls["n"] == before, "the circuit was open but the call still went upstream"

    svc._blocked_until = 0.0


async def test_readiness_marks_indianapi_open_circuit_as_not_ready(client, monkeypatch):
    from app.services import indianapi_service as svc
    import time as _t
    svc._blocked_until = _t.time() + 300
    try:
        r = await client.get("/health/ready")
        assert r.status_code == 503
        assert "indianapi" in r.json()["checks"]["circuit_breakers"]["open"]
    finally:
        svc._blocked_until = 0.0


async def test_email_send_failure_does_not_fail_the_request(client, user_a, monkeypatch, broken_http):
    monkeypatch.setattr(settings, "resend_api_key", "re_fake_key")
    r = await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    assert r.status_code == 200, "a Resend outage broke the forgot-password flow"


# ── Proxy-trust startup warning ───────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (None,            "default"),    # the shipped default — RFC1918, NAT-ambiguous
    ("*",             "wildcard"),   # the check disabled entirely
    ("10.44.0.0/16",  None),         # explicitly narrowed
    ("10.44.0.0/16,192.0.2.7", None),
])
def test_production_startup_warns_when_proxy_trust_is_not_narrowed(value, expected, monkeypatch):
    """TRUSTED_PROXY_IPS has no safe universal default — the shipped one trusts
    RFC1918, which is both where a real ingress lives and where a NAT gateway
    lives. An IP check cannot separate them, so the mitigation is operational:
    narrow it per deployment. That only happens if NOT doing it is visible, so
    the lifespan warns on every production boot until it is set.

    Drives the real function the lifespan calls, rather than re-implementing
    its branches in the test.
    """
    from app.core.config import Settings
    from app.main import warn_if_proxy_trust_is_not_narrowed

    default = Settings.model_fields["trusted_proxy_ips"].default
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "trusted_proxy_ips", default if value is None else value)

    assert warn_if_proxy_trust_is_not_narrowed(settings) == expected


def test_the_warning_is_logged_at_warning_level_not_info(monkeypatch, caplog):
    """An INFO line in a production log is not a signal anyone acts on."""
    import logging as _logging
    from app.core.config import Settings
    from app.main import warn_if_proxy_trust_is_not_narrowed

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "trusted_proxy_ips",
                        Settings.model_fields["trusted_proxy_ips"].default)

    with caplog.at_level(_logging.WARNING, logger="app.main"):
        warn_if_proxy_trust_is_not_narrowed(settings)

    msgs = [r.getMessage() for r in caplog.records if r.levelno >= _logging.WARNING]
    assert any("TRUSTED_PROXY_IPS" in m for m in msgs), (
        f"no WARNING mentioning TRUSTED_PROXY_IPS was emitted: {msgs}"
    )


def test_development_is_not_nagged(monkeypatch):
    """Local dev has no proxy and no internet exposure — warning there would
    train people to ignore the message that matters in production."""
    from app.main import warn_if_proxy_trust_is_not_narrowed
    monkeypatch.setattr(settings, "app_env", "development")
    assert warn_if_proxy_trust_is_not_narrowed(settings) is None


def test_the_lifespan_actually_calls_it(monkeypatch):
    """Guard against the function above becoming dead code that the tests keep
    green while production never runs it."""
    import inspect
    from app import main
    assert "warn_if_proxy_trust_is_not_narrowed(settings)" in inspect.getsource(main.lifespan)
