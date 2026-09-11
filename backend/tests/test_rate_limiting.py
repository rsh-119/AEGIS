"""Rate limiting, and whether it can be walked around.

The production entrypoint (backend/Dockerfile) runs uvicorn with NO
--proxy-headers and NO --forwarded-allow-ips, deliberately: those flags made
uvicorn overwrite request.client.host with the leftmost (client-written)
X-Forwarded-For entry, destroying the one address a caller cannot forge. The
whole client-IP decision lives in rate_limiter.client_ip() instead.

Two topologies are exercised here, because the interesting failures live in the
difference between them:

  _client()        — behind an APPENDING edge proxy on a trusted (private)
                     address, i.e. Render / a k8s ingress.
  _direct_client() — connected straight to the app from a public address, i.e.
                     docker-compose.yml's published port 8000. This is the case
                     that used to be bypassable, and the earlier harness could
                     not express it at all.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.cache import cache
from app.core.config import get_settings
from app.main import app
from app.middleware.rate_limiter import AUTH_LIMIT, user_or_ip_key
from tests.conftest import VALID_PASSWORD


class _EdgeProxy:
    """Stands in for the reverse proxy that actually fronts this app (Render's
    edge, a k8s ingress, nginx).

    The behaviour that matters is that a conforming proxy *appends* the peer
    address it saw to X-Forwarded-For rather than replacing the header. So a
    client that sends its own `X-Forwarded-For: 10.0.0.1` produces
    `10.0.0.1, <real client ip>` by the time uvicorn sees it — which is
    precisely why reading the leftmost entry hands control of the rate-limit
    key to the caller.
    """

    def __init__(self, app, peer: str = "198.51.100.7"):
        self.app = app
        self.peer = peer

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            peer = self.peer
            headers = list(scope["headers"])
            existing = next(
                (v.decode("latin1") for k, v in headers if k == b"x-forwarded-for"), ""
            )
            headers = [(k, v) for k, v in headers if k != b"x-forwarded-for"]
            chain = f"{existing}, {peer}" if existing else peer
            headers.append((b"x-forwarded-for", chain.encode("latin1")))
            scope = {**scope, "headers": headers}
        return await self.app(scope, receive, send)


# The edge proxy connects from a private address, which is what makes it
# trusted to speak for someone else (see TRUSTED_PROXY_IPS).
PROXY_PEER = "10.0.0.1"


def _client(ip: str = "198.51.100.7") -> AsyncClient:
    """A client at `ip` behind an APPENDING edge proxy, which is how the app is
    reached on Render and in k8s. The ASGI scope's client is the PROXY's own
    (private, therefore trusted) address; the real caller only appears inside
    X-Forwarded-For, exactly as in production."""
    proxied = _EdgeProxy(app, peer=ip)
    return AsyncClient(
        transport=ASGITransport(app=proxied, client=(PROXY_PEER, 40000)),
        base_url="http://testserver",
    )


def _direct_client(ip: str = "198.51.100.7") -> AsyncClient:
    """A client connected STRAIGHT to the app from a public address, with no
    proxy in the path — docker-compose.yml publishes port 8000 exactly like
    this. Nothing appends to X-Forwarded-For here, so whatever the client sends
    is the entire header."""
    return AsyncClient(
        transport=ASGITransport(app=app, client=(ip, 40000)),
        base_url="http://testserver",
    )


def _reset_buckets():
    if cache._redis is not None:
        cache._redis.flushdb()


async def _hammer(client, url: str, body: dict, n: int, headers: dict | None = None) -> list[int]:
    codes = []
    for _ in range(n):
        r = await client.post(url, json=body, headers=headers or {})
        codes.append(r.status_code)
    return codes


# ── The limits fire at all ────────────────────────────────────────────────────

async def test_login_limit_triggers_and_returns_json_429(user_a):
    _reset_buckets()
    async with _client() as c:
        codes = await _hammer(c, "/api/auth/login",
                              {"email": user_a.email, "password": "WrongPassword1!"}, 8)
    assert 429 in codes, f"AUTH_LIMIT ({AUTH_LIMIT}) never fired: {codes}"
    assert codes.index(429) <= 5, f"limit fired later than {AUTH_LIMIT} allows: {codes}"


async def test_429_body_is_json_with_retry_after(user_a):
    _reset_buckets()
    async with _client() as c:
        last = None
        for _ in range(8):
            last = await c.post("/api/auth/login",
                                json={"email": user_a.email, "password": "WrongPassword1!"})
            if last.status_code == 429:
                break
    assert last.status_code == 429
    assert last.headers.get("content-type", "").startswith("application/json")
    assert last.json()["error"] == "Rate limit exceeded"
    assert last.headers.get("Retry-After") == "60"


async def test_register_is_rate_limited():
    _reset_buckets()
    async with _client() as c:
        codes = []
        for i in range(8):
            r = await c.post("/api/auth/register", json={
                "email": f"spam{i}@example.com", "username": f"spam{i}",
                "password": VALID_PASSWORD,
            })
            codes.append(r.status_code)
    assert 429 in codes, f"unlimited account creation from one IP: {codes}"


async def test_forgot_password_is_rate_limited(user_a, monkeypatch):
    async def _send(to, token):
        return None
    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _send)
    _reset_buckets()
    async with _client() as c:
        codes = await _hammer(c, "/api/auth/forgot-password", {"email": user_a.email}, 6)
    assert 429 in codes, f"unlimited reset-email sends: {codes}"
    assert codes.index(429) <= 3


async def test_2fa_verify_login_is_rate_limited(user_a):
    _reset_buckets()
    from app.core.auth import create_pre_auth_token
    token = create_pre_auth_token(user_a.id)
    async with _client() as c:
        codes = await _hammer(c, "/api/auth/2fa/verify-login",
                              {"pre_auth_token": token, "code": "000000"}, 8)
    assert 429 in codes, f"unlimited TOTP guesses: {codes}"


async def test_separate_source_ips_get_separate_buckets(user_a):
    _reset_buckets()
    async with _client("198.51.100.1") as c1:
        codes1 = await _hammer(c1, "/api/auth/login",
                               {"email": user_a.email, "password": "WrongPassword1!"}, 6)
    assert 429 in codes1
    async with _client("198.51.100.2") as c2:
        r = await c2.post("/api/auth/login",
                          json={"email": user_a.email, "password": VALID_PASSWORD})
    assert r.status_code == 200, "one IP's limit spilled onto an unrelated IP"


# ── Header spoofing ───────────────────────────────────────────────────────────

async def test_forged_x_forwarded_for_cannot_reset_the_login_limit(user_a):
    """An attacker who can reach the backend sends their own X-Forwarded-For.
    The edge proxy APPENDS the real peer, so the header arrives as
    "<forged>, <real>". If the client IP is taken from the left of that list,
    every per-IP limit resets on demand and login brute-forcing is unbounded.
    """
    _reset_buckets()
    async with _client("198.51.100.9") as c:
        codes = []
        for i in range(40):
            r = await c.post(
                "/api/auth/login",
                json={"email": user_a.email, "password": f"Guess{i}!aaaaaa"},
                headers={"X-Forwarded-For": f"10.0.{i // 256}.{i % 256}"},
            )
            codes.append(r.status_code)
    blocked = codes.count(429)
    assert blocked > 0, (
        f"40 login attempts with a rotating X-Forwarded-For produced zero 429s "
        f"— the rate limit is bypassable by header spoofing ({codes[:10]}…)"
    )


async def test_forged_x_real_ip_cannot_reset_the_login_limit(user_a):
    _reset_buckets()
    async with _client("198.51.100.11") as c:
        codes = []
        for i in range(12):
            r = await c.post(
                "/api/auth/login",
                json={"email": user_a.email, "password": f"Guess{i}!aaaaaa"},
                headers={"X-Real-IP": f"10.1.0.{i}"},
            )
            codes.append(r.status_code)
    assert 429 in codes, f"X-Real-IP spoofing reset the bucket: {codes}"


async def test_malformed_x_forwarded_for_does_not_crash_or_bypass(user_a):
    _reset_buckets()
    async with _client("198.51.100.12") as c:
        codes = []
        for junk in ["", "   ", "not-an-ip", "1.2.3.4,,,", "::::", "a" * 500,
                     "1.2.3.4, 5.6.7.8, 9.10.11.12", "999.999.999.999"] * 2:
            r = await c.post("/api/auth/login",
                             json={"email": user_a.email, "password": "WrongPassword1!"},
                             headers={"X-Forwarded-For": junk})
            codes.append(r.status_code)
    assert 500 not in codes, f"a malformed X-Forwarded-For produced a 500: {codes}"
    assert 429 in codes, f"malformed X-Forwarded-For values dodged the limit: {codes}"


# ── Bucket keying ─────────────────────────────────────────────────────────────

def test_user_or_ip_key_prefers_the_authenticated_user(user_a=None):
    """Per-account keying for AI/avatar quota, so an office NAT doesn't share
    one bucket — and so a user can't get a fresh quota by changing IP."""
    from starlette.requests import Request
    from app.core.auth import create_access_token

    token = create_access_token(4242, "sid-1")

    def _req(headers: list[tuple[bytes, bytes]], client=("1.2.3.4", 1)):
        return Request({"type": "http", "headers": headers, "client": client,
                        "method": "GET", "path": "/", "query_string": b"", "scheme": "http"})

    assert user_or_ip_key(_req([(b"authorization", f"Bearer {token}".encode())])) == "user:4242"
    assert user_or_ip_key(_req([(b"cookie", f"aegis_access={token}".encode())])) == "user:4242"
    assert user_or_ip_key(_req([])) == "1.2.3.4"
    # A garbage token must fall back to IP, never raise.
    assert user_or_ip_key(_req([(b"authorization", b"Bearer garbage")])) == "1.2.3.4"


async def test_ai_quota_is_keyed_per_account_not_per_ip(pro_user, user_a, bearer):
    """Two users behind one IP must not share the AI bucket."""
    _reset_buckets()
    async with _client("198.51.100.20") as c:
        a_codes = []
        for _ in range(14):
            r = await c.get("/api/portfolio/insights/ai", headers=bearer(user_a.id))
            a_codes.append(r.status_code)
        assert 429 in a_codes, f"AI limit never fired: {a_codes}"

        other = await c.get("/api/portfolio/insights/ai", headers=bearer(pro_user.id))
    assert other.status_code != 429, "one account's AI quota blocked a different account on the same IP"


# ── Redis behaviour ───────────────────────────────────────────────────────────

async def test_rate_limiter_uses_shared_redis_storage():
    """In-memory storage counts per-process; with --workers 2 that silently
    doubles every limit. Confirm the configured backend is shared."""
    from app.middleware.rate_limiter import limiter
    storage = limiter._storage if hasattr(limiter, "_storage") else limiter.limiter.storage
    assert "redis" in type(storage).__module__.lower() or "redis" in type(storage).__name__.lower(), (
        f"rate limiter is using {type(storage).__name__}, not shared Redis storage"
    )


async def test_api_stays_up_when_redis_dies_mid_flight(user_a, monkeypatch):
    """Redis is a soft dependency everywhere else in this codebase. If the
    limiter hard-fails on a storage error, a Redis blip becomes a total
    outage rather than degraded rate limiting."""
    from app.middleware.rate_limiter import limiter
    import redis

    storage = getattr(limiter, "_storage", None) or limiter.limiter.storage

    def _boom(*a, **kw):
        raise redis.exceptions.ConnectionError("redis is gone")

    for method in ("incr", "get", "acquire_entry"):
        if hasattr(storage, method):
            monkeypatch.setattr(storage, method, _boom, raising=False)

    async with _client("198.51.100.30") as c:
        r = await c.get("/api/health")
    assert r.status_code < 500, (
        f"a Redis outage took the whole API down (got {r.status_code}) — "
        "rate limiting should degrade, not fail the request"
    )


# ── TRUSTED_PROXY_HOPS: why it is 1 and not 2 ─────────────────────────────────
#
# The setting says how many proxies in front of this app APPEND to
# X-Forwarded-For. client_ip() counts that many entries from the RIGHT, so
# anything an attacker prepends shifts out of the window.
#
# The tempting value is 2, because production is browser -> Vercel edge ->
# Render -> FastAPI when traffic arrives through the Next.js /api/* rewrite,
# and at hops=1 every one of those clients presents Vercel's egress address and
# shares a single bucket. These tests record why 2 is nonetheless the wrong
# value for the current deployment, in a form that fails if someone raises it.


def _client_ip_with(
    hops: int,
    xff: str | None,
    peer: str = "10.0.0.1",          # a TRUSTED (private) proxy address
) -> str:
    """Run the real key function against a synthetic request.

    `peer` is the actual socket address. It defaults to a private one because
    that is what makes X-Forwarded-For trusted at all — see
    TRUSTED_PROXY_IPS.
    """
    from starlette.requests import Request
    from app.middleware.rate_limiter import client_ip

    settings = get_settings()
    original = settings.trusted_proxy_hops
    settings.trusted_proxy_hops = hops
    try:
        headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
        return client_ip(Request({
            "type": "http", "headers": headers, "client": (peer, 1234),
            "method": "GET", "path": "/", "query_string": b"", "scheme": "http",
        }))
    finally:
        settings.trusted_proxy_hops = original


def test_default_is_one_hop():
    """The shipped default. Changing it is a security decision, so it is
    asserted rather than assumed by the tests below."""
    from app.core.config import Settings
    assert Settings.model_fields["trusted_proxy_hops"].default == 1


def test_default_trusted_peers_are_loopback_and_private_only():
    """The default must not include any public range — that would hand proxy
    authority to the internet."""
    import ipaddress
    from app.core.config import Settings

    default = Settings.model_fields["trusted_proxy_ips"].default
    assert default != "*", "X-Forwarded-For is trusted from anyone by default"
    for entry in default.split(","):
        net = ipaddress.ip_network(entry.strip(), strict=False)
        assert net.is_private or net.is_loopback or net.is_link_local, (
            f"{entry} is a PUBLIC range — anyone on the internet could then "
            f"forge X-Forwarded-For and reset every per-IP bucket"
        )


# ── Condition 1: the peer must be a trusted proxy ────────────────────────────

def test_a_direct_public_caller_cannot_speak_for_anyone():
    """THE case that real-transport testing caught, and that the previous
    harness could not express.

    With no proxy in the path, a self-supplied X-Forwarded-For is both the
    first and the last entry — so counting hops from either end reads the
    attacker's own value. Hop counting cannot save this; only refusing to read
    the header from an untrusted peer can.
    """
    forged = "1.2.3.4"
    key = _client_ip_with(1, forged, peer="198.51.100.7")
    assert key == "198.51.100.7", (
        "a direct caller's X-Forwarded-For was honoured — every per-IP limit "
        "is resettable by sending a different header value"
    )
    assert key != forged


@pytest.mark.parametrize("chain", [
    "1.2.3.4",
    "1.2.3.4, 5.6.7.8",
    "1.2.3.4, 5.6.7.8, 9.10.11.12",
    ", ".join(f"10.0.0.{i}" for i in range(20)),
])
def test_no_forged_chain_length_helps_an_untrusted_peer(chain):
    """An attacker who controls the whole header also controls its length, so
    they could otherwise pick whatever shape defeats the hop count."""
    assert _client_ip_with(1, chain, peer="198.51.100.7") == "198.51.100.7"
    assert _client_ip_with(2, chain, peer="198.51.100.7") == "198.51.100.7"


def test_a_trusted_proxy_peer_is_still_honoured():
    """The check must not be so strict that the real deployment breaks — a
    proxy on a private address still gets to name the client."""
    assert _client_ip_with(1, "198.51.100.7", peer="10.0.0.1") == "198.51.100.7"
    assert _client_ip_with(1, "198.51.100.7", peer="172.16.4.2") == "198.51.100.7"
    assert _client_ip_with(1, "198.51.100.7", peer="127.0.0.1") == "198.51.100.7"


def test_an_unparseable_peer_is_not_trusted():
    """Fail closed: an address we cannot parse gets no proxy authority."""
    assert _client_ip_with(1, "1.2.3.4", peer="unknown") == "unknown"


# ── Condition 2: the right entry must be picked ──────────────────────────────

def test_one_hop_ignores_a_prepended_client_value():
    """Render's edge appends the real peer, so the header is
    "<forged>, <real>". Counting one from the right lands on the real peer."""
    assert _client_ip_with(1, "10.9.9.9, 198.51.100.7") == "198.51.100.7"


def test_one_hop_ignores_an_arbitrarily_long_forged_chain():
    forged = ", ".join(f"10.0.0.{i}" for i in range(30))
    assert _client_ip_with(1, f"{forged}, 198.51.100.7") == "198.51.100.7"


def test_two_hops_reads_one_entry_further_left():
    """TRUSTED_PROXY_HOPS stays at 1 for this deployment (see
    core/config.py), but the counting itself must be correct for anyone who
    genuinely has two appending proxies and sets it.

    Note the residual risk this encodes: from a TRUSTED peer, hops=2 does
    consume one attacker-supplied entry. That is inherent — it is why the
    value must match the real number of appending proxies, and why the peer
    check above is what actually keeps the internet out.
    """
    assert _client_ip_with(2, "198.51.100.7, 10.0.0.9") == "198.51.100.7"
    assert _client_ip_with(2, "1.2.3.4, 198.51.100.7, 10.0.0.9") == "198.51.100.7"


def test_fewer_entries_than_hops_never_reads_past_the_left_edge():
    """An internal caller (probe, in-cluster scrape) arrives with one entry or
    none. Indexing must clamp, not wrap around."""
    assert _client_ip_with(2, "198.51.100.7") == "198.51.100.7"
    assert _client_ip_with(3, "198.51.100.7, 10.0.0.1") == "198.51.100.7"


def test_no_header_falls_back_to_the_socket_peer():
    assert _client_ip_with(1, None, peer="10.0.0.9") == "10.0.0.9"
    assert _client_ip_with(1, None, peer="203.0.113.99") == "203.0.113.99"


def test_x_real_ip_is_never_consulted():
    """Nothing in this deployment sets X-Real-IP, so honouring it would only
    re-open the same spoofing hole through a second header — from a trusted
    peer as well as an untrusted one."""
    from starlette.requests import Request
    from app.middleware.rate_limiter import client_ip

    for peer in ("10.0.0.1", "203.0.113.50"):
        req = Request({
            "type": "http",
            "headers": [(b"x-real-ip", b"1.2.3.4")],
            "client": (peer, 1234),
            "method": "GET", "path": "/", "query_string": b"", "scheme": "http",
        })
        assert client_ip(req) == peer


@pytest.mark.parametrize("junk", ["", "   ", ",,,", "not-an-ip", "::::", "a" * 300])
def test_malformed_headers_never_crash_the_key_function(junk):
    """A key function that raises takes down every rate-limited route with it."""
    key = _client_ip_with(1, junk)
    assert isinstance(key, str) and key, f"client_ip returned {key!r} for {junk!r}"


# ── End-to-end through the app, both topologies ──────────────────────────────

async def test_a_direct_caller_cannot_rotate_past_the_login_limit(user_a):
    """The container check that found this: 40 logins with a rotating
    X-Forwarded-For and no proxy in front produced zero 429s."""
    _reset_buckets()
    async with _direct_client("198.51.100.77") as c:
        codes = []
        for i in range(20):
            r = await c.post(
                "/api/auth/login",
                json={"email": user_a.email, "password": f"Guess{i}!aaaaaa"},
                headers={"X-Forwarded-For": f"10.0.{i // 256}.{i % 256}"},
            )
            codes.append(r.status_code)
            if r.status_code == 429:
                break
    assert 429 in codes, (
        f"a directly-connected client reset its own rate-limit bucket by "
        f"rotating X-Forwarded-For: {codes}"
    )


def test_a_nat_gateway_peer_is_trusted_by_default_which_is_a_known_limitation():
    """Recorded limitation, asserted so it cannot change unnoticed.

    TRUSTED_PROXY_IPS defaults to loopback + RFC1918, because that is where a
    reverse proxy, k8s ingress or platform edge genuinely connects from. An IP
    check cannot tell that apart from a NAT: Docker's `ports: "8000:8000"`
    rewrites the source address into the bridge subnet (172.x), so a caller
    from anywhere presents a "private" peer and their X-Forwarded-For is
    honoured. Confirmed against the built image — 40 logins with a rotating
    header, zero 429s.

    There is no default that fixes this, because the two cases are
    indistinguishable by address alone. The mitigations, both applied:
      • docker-compose.yml binds the backend to 127.0.0.1 so it is not
        published to the network behind a NAT in the first place;
      • TRUSTED_PROXY_IPS is configurable, so a real deployment can narrow it
        to the proxy's exact address.

    Nothing here is a bypass of the *fix* — a caller from a PUBLIC peer is
    correctly refused (see test_a_direct_public_caller_cannot_speak_for_anyone).
    This pins the boundary of what the fix covers.
    """
    forged = "1.2.3.4"
    # A Docker bridge gateway address — private, therefore trusted by default.
    assert _client_ip_with(1, forged, peer="172.19.0.1") == forged, (
        "the default trust list no longer covers RFC1918. That may well be an "
        "improvement, but it changes behaviour for Render/k8s (where the proxy "
        "peer is private) — re-check TRUSTED_PROXY_IPS before accepting it."
    )


def test_narrowing_trusted_proxy_ips_closes_the_nat_case():
    """The escape hatch has to actually work: point TRUSTED_PROXY_IPS at the
    real proxy only, and a NAT gateway loses its authority."""
    settings = get_settings()
    original = settings.trusted_proxy_ips
    settings.trusted_proxy_ips = "10.8.0.5"          # the one real proxy
    try:
        assert _client_ip_with(1, "1.2.3.4", peer="172.19.0.1") == "172.19.0.1"
        assert _client_ip_with(1, "198.51.100.7", peer="10.8.0.5") == "198.51.100.7"
    finally:
        settings.trusted_proxy_ips = original


def test_a_malformed_entry_narrows_trust_rather_than_widening_it():
    settings = get_settings()
    original = settings.trusted_proxy_ips
    settings.trusted_proxy_ips = "not-a-cidr, 10.8.0.5"
    try:
        assert _client_ip_with(1, "1.2.3.4", peer="172.19.0.1") == "172.19.0.1"
        assert _client_ip_with(1, "198.51.100.7", peer="10.8.0.5") == "198.51.100.7"
    finally:
        settings.trusted_proxy_ips = original
