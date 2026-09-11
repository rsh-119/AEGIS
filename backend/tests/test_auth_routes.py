"""/api/auth/* — registration, login, profile, password change/reset.

Covers the behaviours a session's integrity depends on, plus the negative
space: nothing that identifies a session may appear in a response body.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME
from app.core.database import AsyncSessionLocal
from app.models import User
from tests.conftest import VALID_PASSWORD

REG = {"email": "new@example.com", "username": "newuser", "password": VALID_PASSWORD}


# ── Registration ──────────────────────────────────────────────────────────────

async def test_register_creates_user_and_sets_both_cookies(client):
    r = await client.post("/api/auth/register", json=REG)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == REG["email"]
    assert body["is_pro"] is False
    assert ACCESS_COOKIE_NAME in r.cookies
    assert REFRESH_COOKIE_NAME in r.cookies


async def test_register_never_returns_password_or_hash(client):
    r = await client.post("/api/auth/register", json=REG)
    raw = r.text
    assert VALID_PASSWORD not in raw
    assert "hashed_password" not in raw
    assert "$2b$" not in raw


async def test_register_rejects_duplicate_email(client, make_user):
    await make_user(email=REG["email"], username="someoneelse")
    r = await client.post("/api/auth/register", json=REG)
    assert r.status_code == 409


async def test_register_rejects_duplicate_username(client, make_user):
    await make_user(email="other@example.com", username=REG["username"])
    r = await client.post("/api/auth/register", json=REG)
    assert r.status_code == 409


@pytest.mark.parametrize("password,reason", [
    ("Short1!", "under 12 chars"),
    ("alllowercase1!", "no uppercase"),
    ("ALLUPPERCASE1!", "no lowercase"),
    ("NoDigitsHere!!", "no digit"),
    ("NoSymbolsHere1", "no symbol"),
])
async def test_register_enforces_password_complexity(client, password, reason):
    r = await client.post("/api/auth/register", json={**REG, "password": password})
    assert r.status_code == 422, f"accepted a password with {reason}"


@pytest.mark.parametrize("username", ["ab", "has space", "has-dash", "a" * 31, "emoji😀"])
async def test_register_rejects_invalid_usernames(client, username):
    r = await client.post("/api/auth/register", json={**REG, "username": username})
    assert r.status_code == 422


async def test_register_rejects_malformed_email(client):
    r = await client.post("/api/auth/register", json={**REG, "email": "not-an-email"})
    assert r.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

async def test_login_succeeds_and_sets_cookies(client, user_a):
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    assert r.status_code == 200
    assert ACCESS_COOKIE_NAME in r.cookies and REFRESH_COOKIE_NAME in r.cookies


async def test_login_response_body_carries_no_tokens(client, user_a):
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    body = json.dumps(r.json())
    for leak in ("access_token", "refresh_token", "token", "jti", "sid"):
        assert leak not in body, f"login body leaked {leak}"


async def test_login_rejects_wrong_password(client, user_a):
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": "WrongPassword1!"})
    assert r.status_code == 401
    assert ACCESS_COOKIE_NAME not in r.cookies


async def test_login_rejects_unknown_email_with_same_message(client, user_a):
    unknown = await client.post("/api/auth/login", json={"email": "nobody@example.com", "password": VALID_PASSWORD})
    wrong = await client.post("/api/auth/login", json={"email": user_a.email, "password": "WrongPassword1!"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"], "login leaks whether an email exists"


async def test_inactive_user_cannot_log_in(client, make_user):
    u = await make_user(email="off@example.com", username="offuser", is_active=False)
    r = await client.post("/api/auth/login", json={"email": u.email, "password": VALID_PASSWORD})
    assert r.status_code == 403


async def test_oauth_only_account_cannot_password_login(client, make_user):
    """hashed_password is NULL for a Google-only account — verify_password
    must return False, not raise a 500."""
    u = await make_user(email="g@example.com", username="guser", password=None,
                        auth_provider="google", google_id="google-123")
    r = await client.post("/api/auth/login", json={"email": u.email, "password": VALID_PASSWORD})
    assert r.status_code == 401


# ── /me ───────────────────────────────────────────────────────────────────────

async def test_me_requires_auth(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_returns_current_user(logged_in):
    client, user = logged_in
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["id"] == user.id


async def test_me_never_exposes_secret_columns(logged_in):
    client, _ = logged_in
    body = (await client.get("/api/auth/me")).json()
    for secret in ("hashed_password", "totp_secret", "backup_codes",
                   "reset_token_hash", "reset_token_expires_at"):
        assert secret not in body, f"/me exposed {secret}"


async def test_bearer_header_is_accepted_for_script_clients(client, user_a, bearer):
    r = await client.get("/api/auth/me", headers=bearer(user_a.id))
    assert r.status_code == 200 and r.json()["id"] == user_a.id


# ── Profile update ────────────────────────────────────────────────────────────

async def test_username_change_without_password_is_allowed(logged_in):
    client, _ = logged_in
    r = await client.patch("/api/auth/me", json={"username": "renamed"})
    assert r.status_code == 200 and r.json()["username"] == "renamed"


async def test_username_change_rejects_taken_name(logged_in, user_b):
    client, _ = logged_in
    r = await client.patch("/api/auth/me", json={"username": user_b.username})
    assert r.status_code == 409


async def test_email_change_requires_current_password(logged_in):
    client, _ = logged_in
    r = await client.patch("/api/auth/me", json={"email": "hijack@example.com"})
    assert r.status_code == 401, "email (the recovery channel) changed without password reproof"


async def test_email_change_succeeds_with_current_password(logged_in):
    client, _ = logged_in
    r = await client.patch("/api/auth/me", json={
        "email": "moved@example.com", "current_password": VALID_PASSWORD,
    })
    assert r.status_code == 200 and r.json()["email"] == "moved@example.com"


async def test_email_change_rejects_wrong_current_password(logged_in):
    client, _ = logged_in
    r = await client.patch("/api/auth/me", json={
        "email": "moved@example.com", "current_password": "WrongPassword1!",
    })
    assert r.status_code == 401


async def test_email_change_rejects_address_owned_by_another_user(logged_in, user_b):
    client, _ = logged_in
    r = await client.patch("/api/auth/me", json={
        "email": user_b.email, "current_password": VALID_PASSWORD,
    })
    assert r.status_code == 409


# ── Password change ───────────────────────────────────────────────────────────

async def test_change_password_requires_correct_current(logged_in):
    client, _ = logged_in
    r = await client.post("/api/auth/me/password", json={
        "current_password": "WrongPassword1!", "new_password": "BrandNewPass1!x",
    })
    assert r.status_code == 401


async def test_change_password_enforces_complexity(logged_in):
    client, _ = logged_in
    r = await client.post("/api/auth/me/password", json={
        "current_password": VALID_PASSWORD, "new_password": "weak",
    })
    assert r.status_code == 422


async def test_change_password_then_new_password_works(logged_in, client_factory):
    client, user = logged_in
    new = "BrandNewPass1!x"
    r = await client.post("/api/auth/me/password", json={
        "current_password": VALID_PASSWORD, "new_password": new,
    })
    assert r.status_code == 200
    fresh = await client_factory()
    assert (await fresh.post("/api/auth/login", json={"email": user.email, "password": new})).status_code == 200
    assert (await fresh.post("/api/auth/login", json={"email": user.email, "password": VALID_PASSWORD})).status_code == 401


# ── Password reset ────────────────────────────────────────────────────────────

def _capture_reset_token(monkeypatch) -> list[str]:
    """The DB only ever stores the sha256, so tests intercept the plaintext
    token where it is actually produced: the outbound-email background task."""
    captured: list[str] = []

    async def _send(to_email, token):
        captured.append(token)

    monkeypatch.setattr("app.routers.auth.send_password_reset_email", _send)
    return captured


async def test_forgot_password_returns_generic_response_for_unknown_email(client):
    r = await client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
    assert r.status_code == 200
    assert "if that email is registered" in r.json()["detail"].lower()


async def test_forgot_password_response_is_identical_for_known_and_unknown(client, user_a):
    known = await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    unknown = await client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
    assert known.json() == unknown.json(), "response distinguishes registered emails"


async def test_forgot_password_stores_only_a_hash_never_the_token(client, user_a, monkeypatch):
    captured = _capture_reset_token(monkeypatch)
    r = await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    assert r.status_code == 200
    assert captured, "reset email task never scheduled"
    token = captured[0]

    async with AsyncSessionLocal() as s:
        u = (await s.execute(select(User).where(User.email == user_a.email))).scalar_one()
        assert u.reset_token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert u.reset_token_hash != token
    assert token not in r.text, "plaintext reset token returned in the HTTP response"


async def test_reset_password_happy_path(client, user_a, monkeypatch, client_factory):
    captured = _capture_reset_token(monkeypatch)
    await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    token = captured[0]

    new = "ResetPass123!x"
    r = await client.post("/api/auth/reset-password", json={"token": token, "new_password": new})
    assert r.status_code == 200

    fresh = await client_factory()
    assert (await fresh.post("/api/auth/login", json={"email": user_a.email, "password": new})).status_code == 200


async def test_reset_token_is_single_use(client, user_a, monkeypatch):
    captured = _capture_reset_token(monkeypatch)
    await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    token = captured[0]

    first = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "ResetPass123!x"})
    assert first.status_code == 200
    second = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "Another123!xy"})
    assert second.status_code == 400, "reset token was reusable"


async def test_expired_reset_token_is_rejected(client, user_a, monkeypatch):
    captured = _capture_reset_token(monkeypatch)
    await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    token = captured[0]

    async with AsyncSessionLocal() as s:
        u = (await s.execute(select(User).where(User.email == user_a.email))).scalar_one()
        u.reset_token_expires_at = datetime.utcnow() - timedelta(minutes=1)
        await s.commit()

    r = await client.post("/api/auth/reset-password", json={"token": token, "new_password": "ResetPass123!x"})
    assert r.status_code == 400


async def test_reset_password_rejects_garbage_token(client):
    r = await client.post("/api/auth/reset-password",
                          json={"token": "not-a-real-token", "new_password": "ResetPass123!x"})
    assert r.status_code == 400


async def test_reset_password_enforces_complexity(client, user_a, monkeypatch):
    captured = _capture_reset_token(monkeypatch)
    await client.post("/api/auth/forgot-password", json={"email": user_a.email})
    r = await client.post("/api/auth/reset-password", json={"token": captured[0], "new_password": "weak"})
    assert r.status_code == 422
