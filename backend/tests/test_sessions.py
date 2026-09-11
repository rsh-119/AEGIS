"""Session lifecycle: refresh rotation, reuse detection, revocation, logout.

These are the controls that decide whether a stolen token stays useful, so
each one is asserted on observable behaviour (can this token still reach a
protected route?) rather than on internal Redis state alone.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from jose import jwt

from app.core import token_store
from app.core.auth import (
    ALGORITHM,
    ACCESS_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    create_access_token,
    create_refresh_token,
    decode_token_full,
)
from app.core.cache import cache
from app.core.config import get_settings
from tests.conftest import VALID_PASSWORD, expired_token

settings = get_settings()


def _cookie(name: str, value: str) -> dict[str, str]:
    """Attach a captured cookie explicitly. httpx's cookie jar won't accept a
    hand-set cookie for the bare hostname "testserver", so replay/theft
    scenarios send the header directly — which is what an attacker does."""
    return {"Cookie": f"{name}={value}"}


# ── Refresh rotation ──────────────────────────────────────────────────────────

async def test_refresh_rotates_both_cookies(logged_in):
    client, _ = logged_in
    before_access = client.cookies[ACCESS_COOKIE_NAME]
    before_refresh = client.cookies[REFRESH_COOKIE_NAME]

    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200, r.text
    assert client.cookies[ACCESS_COOKIE_NAME] != before_access
    assert client.cookies[REFRESH_COOKIE_NAME] != before_refresh


async def test_refresh_keeps_the_same_session_id(logged_in):
    """Rotation must advance the chain, not mint a new session — otherwise
    revoke-all-sessions can never catch up with an active client."""
    client, _ = logged_in
    sid_before = decode_token_full(client.cookies[REFRESH_COOKIE_NAME], "refresh").sid
    await client.post("/api/auth/refresh")
    sid_after = decode_token_full(client.cookies[REFRESH_COOKIE_NAME], "refresh").sid
    assert sid_before == sid_after


async def test_refresh_without_a_token_is_401(client):
    assert (await client.post("/api/auth/refresh")).status_code == 401


async def test_refresh_body_returns_no_tokens(logged_in):
    client, _ = logged_in
    r = await client.post("/api/auth/refresh")
    assert "token" not in r.text.lower() or r.json() == {"detail": "Refreshed"}


async def test_refreshed_access_token_works(logged_in):
    client, user = logged_in
    await client.post("/api/auth/refresh")
    r = await client.get("/api/auth/me")
    assert r.status_code == 200 and r.json()["id"] == user.id


# ── Reuse detection ───────────────────────────────────────────────────────────

async def test_replaying_a_rotated_refresh_token_is_rejected(logged_in, client_factory):
    client, _ = logged_in
    stolen = client.cookies[REFRESH_COOKIE_NAME]

    assert (await client.post("/api/auth/refresh")).status_code == 200  # legit rotation

    attacker = await client_factory()
    r = await attacker.post("/api/auth/refresh", headers=_cookie(REFRESH_COOKIE_NAME, stolen))
    assert r.status_code == 401, "a rotated-away refresh token was replayable"
    assert "already used" in r.json()["detail"].lower()


async def test_reuse_detection_kills_the_whole_session(logged_in, client_factory):
    """The victim's *current* token must also stop working once a replay of
    an older one in the same chain is observed."""
    client, _ = logged_in
    stolen = client.cookies[REFRESH_COOKIE_NAME]
    await client.post("/api/auth/refresh")

    attacker = await client_factory()
    await attacker.post("/api/auth/refresh", headers=_cookie(REFRESH_COOKIE_NAME, stolen))

    victim = await client.post("/api/auth/refresh")
    assert victim.status_code == 401, "session survived a detected refresh-token replay"


async def test_revoked_session_blocks_access_tokens_too(logged_in):
    client, _ = logged_in
    sid = decode_token_full(client.cookies[ACCESS_COOKIE_NAME]).sid
    token_store.revoke_session(sid)
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"].lower()


async def test_refresh_fails_closed_when_redis_is_down(logged_in, monkeypatch):
    """token_store documents refresh-rotation as fail-CLOSED. A Redis outage
    must 503, never silently skip the reuse check."""
    client, _ = logged_in
    monkeypatch.setattr(token_store, "_redis", lambda: None)
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 503, "refresh silently succeeded with reuse detection unavailable"


async def test_access_check_fails_open_when_redis_is_down(logged_in, monkeypatch):
    """The blocklist read is documented as fail-OPEN — an outage must not log
    every user out."""
    client, _ = logged_in
    monkeypatch.setattr(token_store, "_redis", lambda: None)
    assert (await client.get("/api/auth/me")).status_code == 200


# ── Logout ────────────────────────────────────────────────────────────────────

async def test_logout_clears_cookies(logged_in):
    client, _ = logged_in
    r = await client.post("/api/auth/logout")
    assert r.status_code == 200
    assert not client.cookies.get(ACCESS_COOKIE_NAME)


async def test_logout_blocklists_the_access_token(logged_in, client_factory):
    client, _ = logged_in
    stolen_access = client.cookies[ACCESS_COOKIE_NAME]
    await client.post("/api/auth/logout")

    attacker = await client_factory()
    r = await attacker.get("/api/auth/me", headers=_cookie(ACCESS_COOKIE_NAME, stolen_access))
    assert r.status_code == 401, "access token still valid after logout"


async def test_logout_revokes_the_refresh_token_too(logged_in, client_factory):
    """A logout that leaves the refresh token usable means a captured refresh
    token survives the user explicitly ending their session — it can mint an
    unlimited stream of fresh access tokens for the full refresh lifetime."""
    client, _ = logged_in
    stolen_refresh = client.cookies[REFRESH_COOKIE_NAME]
    await client.post("/api/auth/logout")

    attacker = await client_factory()
    r = await attacker.post("/api/auth/refresh", headers=_cookie(REFRESH_COOKIE_NAME, stolen_refresh))
    assert r.status_code == 401, "refresh token survived logout — session was never revoked"


async def test_logout_is_idempotent_and_never_errors(client):
    assert (await client.post("/api/auth/logout")).status_code == 200


async def test_logout_works_for_bearer_clients(client, user_a, bearer, client_factory):
    """Script/API clients authenticate with a Bearer header; logout must be
    able to revoke that token too, not only cookie sessions."""
    sid = str(uuid.uuid4())
    token = create_access_token(user_a.id, sid)
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200

    await client.post("/api/auth/logout", headers=headers)

    r = await client.get("/api/auth/me", headers=headers)
    assert r.status_code == 401, "Bearer access token still valid after logout"


# ── Password reset revokes sessions ───────────────────────────────────────────

async def test_password_reset_revokes_existing_sessions(client, user_a, monkeypatch, client_factory):
    session_client = await client_factory()
    await session_client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    assert (await session_client.get("/api/auth/me")).status_code == 200

    captured: list[str] = []

    async def _send(to_email, token):
        captured.append(token)

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _send)
    await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    await client.post("/api/auth/reset-password",
                      json={"token": captured[0], "new_password": "ResetPass123!x"})

    r = await session_client.get("/api/auth/me")
    assert r.status_code == 401, "pre-reset session survived a password reset"


# ── Concurrency ───────────────────────────────────────────────────────────────

async def test_concurrent_refresh_does_not_break_the_chain(logged_in, client_factory):
    """Two tabs refreshing at once: at most one may win, and the session must
    end up in a deterministic state — either both succeed against the same
    chain pointer, or the loser is cleanly rejected."""
    client, _ = logged_in
    token = client.cookies[REFRESH_COOKIE_NAME]

    c1 = await client_factory()
    c2 = await client_factory()
    hdr = _cookie(REFRESH_COOKIE_NAME, token)

    r1, r2 = await asyncio.gather(
        c1.post("/api/auth/refresh", headers=hdr),
        c2.post("/api/auth/refresh", headers=hdr),
    )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes in ([200, 200], [200, 401]), f"unexpected concurrent-refresh outcome {codes}"


# ── Legacy (pre-`sid`) refresh tokens ─────────────────────────────────────────

def _legacy_refresh_token(user_id: int) -> str:
    """A refresh token in the shape this app minted BEFORE session ids existed:
    valid signature, correct type, no `sid`, no rotation chain."""
    from datetime import datetime, timedelta, timezone
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
        },
        settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )


async def test_refresh_rejects_a_pre_sid_token_from_the_cookie(client_factory, user_a):
    """A token with no `sid` is unrevocable — logout and password reset both
    revoke by session id — so it must not be honoured, cookie or not."""
    c = await client_factory()
    r = await c.post(
        "/api/auth/refresh",
        headers=_cookie(REFRESH_COOKIE_NAME, _legacy_refresh_token(user_a.id)),
    )
    assert r.status_code == 401, (
        "a pre-`sid` refresh token was accepted — it cannot be rotated or "
        "revoked, so honouring it is a permanent auth downgrade"
    )
    assert ACCESS_COOKIE_NAME not in r.cookies, "a session was minted from an unrevocable token"


async def test_refresh_rejects_a_pre_sid_token_from_the_body(client_factory, user_a):
    """Same via the script-client JSON body path, which is the only route a
    pre-migration token could realistically still arrive on."""
    c = await client_factory()
    r = await c.post(
        "/api/auth/refresh",
        json={"refresh_token": _legacy_refresh_token(user_a.id)},
    )
    assert r.status_code == 401
    assert ACCESS_COOKIE_NAME not in r.cookies


async def test_a_pre_sid_token_cannot_outlive_logout(logged_in, client_factory, user_a):
    """The concrete harm the legacy branch allowed: hold a pre-`sid` token,
    log out everywhere, and still mint fresh sessions. Prove it cannot."""
    client, _ = logged_in
    legacy = _legacy_refresh_token(user_a.id)

    assert (await client.post("/api/auth/logout")).status_code == 200

    c = await client_factory()
    r = await c.post("/api/auth/refresh", headers=_cookie(REFRESH_COOKIE_NAME, legacy))
    assert r.status_code == 401, "a token that logout cannot revoke still minted a session"
