"""Behaviour that only appears against a real uvicorn process.

httpx's ASGITransport calls the ASGI app directly, so anything uvicorn's
transport layer contributes — its own response headers, HTTP/1.1 framing,
connection handling — is invisible to the in-process suite. The duplicate
`Server` header below passed every in-process test and was only caught by
curling a running container.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.slow


async def test_only_one_server_header_is_emitted(live_server):
    """uvicorn emits `Server: uvicorn` at the transport layer, before
    SecurityHeadersMiddleware sets `Server: Aegis`. Both end up on the
    response and clients read the first, so the middleware's stated purpose
    ("Remove server fingerprint") is defeated unless uvicorn's is suppressed
    with --no-server-header.
    """
    async with httpx.AsyncClient(base_url=live_server, timeout=15) as c:
        r = await c.get("/api/health")

    servers = r.headers.get_list("server")
    assert len(servers) == 1, f"{len(servers)} Server headers: {servers}"
    assert servers[0] == "Aegis"
    assert "uvicorn" not in servers[0].lower()


async def test_security_headers_survive_the_real_transport(live_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=15) as c:
        r = await c.get("/api/health")
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "max-age=" in r.headers.get("Strict-Transport-Security", "")
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert r.headers.get("X-Request-ID")


async def test_cache_directives_are_correct_over_the_wire(live_server):
    """The middleware fix verified end-to-end rather than by calling
    _get_rule(): private routes no-store, public market data still cached."""
    async with httpx.AsyncClient(base_url=live_server, timeout=15) as c:
        private = await c.get("/api/auth/me")           # 401, but rule still applies
        health = await c.get("/api/health")
        public = await c.get("/api/stocks/search?q=tcs")

    assert "public" not in health.headers.get("Cache-Control", "")
    assert "no-store" in health.headers.get("Cache-Control", "")
    assert "public" not in private.headers.get("Cache-Control", "")
    assert "public" in public.headers.get("Cache-Control", ""), (
        "public market data lost its shared-cache directive"
    )


async def test_unknown_route_returns_json_not_an_html_error_page(live_server):
    async with httpx.AsyncClient(base_url=live_server, timeout=15) as c:
        r = await c.get("/definitely/not/a/route")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "<html" not in r.text.lower()


async def test_oversized_header_is_rejected_without_a_500(live_server):
    """h11 caps header size; the failure must be a clean 4xx, not a crash."""
    async with httpx.AsyncClient(base_url=live_server, timeout=15) as c:
        try:
            r = await c.get("/api/health", headers={"X-Big": "A" * 40_000})
            assert r.status_code < 500, f"oversized header produced {r.status_code}"
        except httpx.RemoteProtocolError:
            pass   # server closed the connection — also an acceptable rejection


def test_the_live_server_fixture_matches_the_dockerfile():
    """The live-server fixture must launch uvicorn the way production does.

    This is the only suite that drives a REAL server over REAL sockets, so it is
    the only place transport-level behaviour can be observed — which is exactly
    why it is worth nothing if it launches a different configuration. That is
    not hypothetical: the fixture kept `--proxy-headers --forwarded-allow-ips
    "*"` after those flags were removed from the Dockerfile, and those are the
    very flags whose removal closed the X-Forwarded-For bypass. The suite was
    therefore testing a server that trusted forwarded headers when the shipped
    one does not.

    Compares the uvicorn flag sets rather than whole command lines: host, port
    and log level legitimately differ (a free port, quieter output).
    """
    import inspect
    import re
    from pathlib import Path

    from tests import conftest

    IGNORED = {"--host", "--port", "--log-level", "--access-log"}

    def flags(text: str) -> set[str]:
        return {f for f in re.findall(r'"(--[a-z-]+)"', text) if f not in IGNORED}

    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    cmd = dockerfile[dockerfile.index('CMD ["uvicorn"'):]
    docker_flags = flags(cmd)
    fixture_flags = flags(inspect.getsource(conftest.live_server))

    assert docker_flags, "could not parse uvicorn flags out of backend/Dockerfile"
    assert fixture_flags == docker_flags, (
        "the live-server fixture no longer launches uvicorn the way the "
        "Dockerfile does, so the real-transport tests are exercising a "
        "configuration that does not ship.\n"
        f"  only in Dockerfile: {sorted(docker_flags - fixture_flags)}\n"
        f"  only in fixture:    {sorted(fixture_flags - docker_flags)}"
    )
