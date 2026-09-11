"""TOTP two-factor: setup → enable → login challenge → verify → backup codes
→ disable, plus the abuse cases around each step."""

from __future__ import annotations

import time

import pyotp
import pytest
from sqlalchemy import select

from app.core import totp
from app.core.auth import ACCESS_COOKIE_NAME, create_pre_auth_token
from app.core.database import AsyncSessionLocal
from app.models import User
from tests.conftest import VALID_PASSWORD


async def _enable_2fa(client) -> tuple[str, list[str]]:
    """Full setup+enable, returning (plaintext secret, backup codes)."""
    setup = await client.post("/api/auth/2fa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    enable = await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert enable.status_code == 200, enable.text
    return secret, enable.json()["backup_codes"]


async def _reload(user_id: int) -> User:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(User).where(User.id == user_id))).scalar_one()


# ── Setup ─────────────────────────────────────────────────────────────────────

async def test_setup_requires_authentication(client):
    assert (await client.post("/api/auth/2fa/setup")).status_code == 401


async def test_setup_returns_secret_and_provisioning_uri(logged_in):
    client, user = logged_in
    r = await client.post("/api/auth/2fa/setup")
    assert r.status_code == 200
    body = r.json()
    assert body["secret"]
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert "issuer=Aegis" in body["otpauth_uri"]


async def test_setup_stores_the_secret_encrypted_not_plaintext(logged_in):
    client, user = logged_in
    secret = (await client.post("/api/auth/2fa/setup")).json()["secret"]
    stored = (await _reload(user.id)).totp_secret
    assert stored != secret, "TOTP secret stored in plaintext"
    assert stored.startswith("gAAAAA"), "stored value is not a Fernet token"
    assert totp.decrypt_secret(stored) == secret


async def test_setup_501s_when_encryption_key_is_unset(logged_in, monkeypatch):
    client, _ = logged_in
    monkeypatch.setattr("app.routers.auth.settings.totp_encryption_key", "")
    r = await client.post("/api/auth/2fa/setup")
    assert r.status_code == 501


async def test_setup_is_idempotent_before_enable(logged_in):
    client, user = logged_in
    first = (await client.post("/api/auth/2fa/setup")).json()["secret"]
    second = (await client.post("/api/auth/2fa/setup")).json()["secret"]
    assert first != second
    assert (await _reload(user.id)).is_2fa_enabled is False


# ── Enable ────────────────────────────────────────────────────────────────────

async def test_enable_requires_setup_first(logged_in):
    client, _ = logged_in
    r = await client.post("/api/auth/2fa/enable", json={"code": "123456"})
    assert r.status_code == 400


async def test_enable_rejects_a_wrong_code(logged_in):
    client, user = logged_in
    secret = (await client.post("/api/auth/2fa/setup")).json()["secret"]
    wrong = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"
    r = await client.post("/api/auth/2fa/enable", json={"code": wrong})
    assert r.status_code == 401
    assert (await _reload(user.id)).is_2fa_enabled is False


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "", "12 34 56"])
async def test_enable_rejects_malformed_codes(logged_in, code):
    client, _ = logged_in
    await client.post("/api/auth/2fa/setup")
    r = await client.post("/api/auth/2fa/enable", json={"code": code})
    assert r.status_code == 422


async def test_enable_returns_backup_codes_stored_as_hashes(logged_in):
    client, user = logged_in
    _, codes = await _enable_2fa(client)
    assert len(codes) == 8
    stored = (await _reload(user.id)).backup_codes
    assert len(stored) == 8
    for plain, hashed in zip(codes, stored):
        assert plain != hashed, "backup code stored in plaintext"
        assert hashed.startswith("$2b$"), "backup code is not bcrypt-hashed"


# ── Login challenge ───────────────────────────────────────────────────────────

async def test_login_with_2fa_returns_pre_auth_token_and_no_session(client, user_a):
    r0 = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    assert r0.status_code == 200
    await _enable_2fa(client)
    client.cookies.clear()

    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    body = r.json()
    assert body["requires_2fa"] is True
    assert body["pre_auth_token"]
    assert ACCESS_COOKIE_NAME not in r.cookies, "session issued before the second factor"


async def test_pre_auth_token_alone_cannot_reach_protected_routes(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    await _enable_2fa(client)
    client.cookies.clear()

    pre_auth = (await client.post(
        "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
    )).json()["pre_auth_token"]

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {pre_auth}"})
    assert r.status_code == 401, "a pre-auth token was accepted as an access token"


async def test_verify_login_with_valid_totp_issues_a_session(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    secret, _ = await _enable_2fa(client)
    client.cookies.clear()

    pre_auth = (await client.post(
        "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
    )).json()["pre_auth_token"]

    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": pre_auth, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200, r.text
    assert ACCESS_COOKIE_NAME in r.cookies
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_verify_login_rejects_a_wrong_totp(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    secret, _ = await _enable_2fa(client)
    client.cookies.clear()
    pre_auth = (await client.post(
        "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
    )).json()["pre_auth_token"]

    bad = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"
    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": pre_auth, "code": bad})
    assert r.status_code == 401
    assert ACCESS_COOKIE_NAME not in r.cookies


async def test_verify_login_rejects_an_expired_pre_auth_token(client, user_a, monkeypatch):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    secret, _ = await _enable_2fa(client)
    client.cookies.clear()

    from datetime import datetime, timedelta, timezone
    from jose import jwt
    from app.core.auth import ALGORITHM
    from app.core.config import get_settings
    expired = jwt.encode(
        {"sub": str(user_a.id), "type": "pre_auth", "jti": "x",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_settings().jwt_secret_key, algorithm=ALGORITHM,
    )
    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": expired, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 401


async def test_verify_login_rejects_an_access_token_as_pre_auth(client, user_a, bearer):
    """Token-type confusion: an access token must not substitute for the
    pre-auth token, or 2FA is bypassable by anyone holding a session."""
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    secret, _ = await _enable_2fa(client)
    access = client.cookies[ACCESS_COOKIE_NAME]
    client.cookies.clear()

    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": access, "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 401


async def test_verify_login_rejects_pre_auth_for_a_user_without_2fa(client, user_a):
    """A forged/leftover pre-auth token for a non-2FA account must not mint a
    session without any second factor being checked."""
    pre_auth = create_pre_auth_token(user_a.id)
    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": pre_auth, "code": "123456"})
    assert r.status_code == 401


# ── Backup codes ──────────────────────────────────────────────────────────────

async def test_backup_code_completes_login(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    _, codes = await _enable_2fa(client)
    client.cookies.clear()
    pre_auth = (await client.post(
        "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
    )).json()["pre_auth_token"]

    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": pre_auth, "code": codes[0]})
    assert r.status_code == 200, r.text
    assert ACCESS_COOKIE_NAME in r.cookies


async def test_backup_code_is_single_use(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    _, codes = await _enable_2fa(client)
    client.cookies.clear()

    async def _challenge():
        return (await client.post(
            "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
        )).json()["pre_auth_token"]

    first = await client.post("/api/auth/2fa/verify-login",
                              json={"pre_auth_token": await _challenge(), "code": codes[0]})
    assert first.status_code == 200
    client.cookies.clear()

    second = await client.post("/api/auth/2fa/verify-login",
                               json={"pre_auth_token": await _challenge(), "code": codes[0]})
    assert second.status_code == 401, "backup code was reusable"


async def test_using_one_backup_code_leaves_the_others_valid(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    _, codes = await _enable_2fa(client)
    client.cookies.clear()

    async def _challenge():
        return (await client.post(
            "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
        )).json()["pre_auth_token"]

    assert (await client.post("/api/auth/2fa/verify-login",
                              json={"pre_auth_token": await _challenge(), "code": codes[0]})).status_code == 200
    client.cookies.clear()
    assert (await client.post("/api/auth/2fa/verify-login",
                              json={"pre_auth_token": await _challenge(), "code": codes[1]})).status_code == 200


async def test_invalid_backup_code_is_rejected(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    await _enable_2fa(client)
    client.cookies.clear()
    pre_auth = (await client.post(
        "/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD}
    )).json()["pre_auth_token"]

    r = await client.post("/api/auth/2fa/verify-login",
                          json={"pre_auth_token": pre_auth, "code": "ZZZZ-ZZZZ"})
    assert r.status_code == 401


# ── Disable ───────────────────────────────────────────────────────────────────

async def test_disable_requires_authentication(client):
    r = await client.post("/api/auth/2fa/disable", json={"current_password": VALID_PASSWORD})
    assert r.status_code == 401


async def test_disable_requires_correct_password(logged_in):
    client, user = logged_in
    await _enable_2fa(client)
    r = await client.post("/api/auth/2fa/disable", json={"current_password": "WrongPassword1!"})
    assert r.status_code == 401
    assert (await _reload(user.id)).is_2fa_enabled is True


async def test_disable_clears_secret_and_backup_codes(logged_in):
    client, user = logged_in
    await _enable_2fa(client)
    r = await client.post("/api/auth/2fa/disable", json={"current_password": VALID_PASSWORD})
    assert r.status_code == 200
    fresh = await _reload(user.id)
    assert fresh.is_2fa_enabled is False
    assert fresh.totp_secret is None
    assert fresh.backup_codes == []


async def test_oauth_account_without_password_cannot_disable_2fa(client, make_user, bearer):
    u = await make_user(email="g2@example.com", username="g2user", password=None,
                        auth_provider="google", google_id="gid-2")
    r = await client.post("/api/auth/2fa/disable", json={"current_password": "anything"},
                          headers=bearer(u.id))
    assert r.status_code == 401


# ── Secret hygiene ────────────────────────────────────────────────────────────

async def test_totp_secret_never_appears_in_me_or_login_responses(client, user_a):
    await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    secret, codes = await _enable_2fa(client)

    me = await client.get("/api/auth/me")
    assert secret not in me.text
    for c in codes:
        assert c not in me.text

    client.cookies.clear()
    login = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    assert secret not in login.text


def test_verify_totp_code_tolerates_one_step_of_drift():
    secret = totp.generate_secret()
    t = pyotp.TOTP(secret)
    now = int(time.time())
    assert totp.verify_totp_code(secret, t.at(now)) is True
    assert totp.verify_totp_code(secret, t.at(now - 30)) is True
    assert totp.verify_totp_code(secret, t.at(now + 30)) is True
    assert totp.verify_totp_code(secret, t.at(now - 300)) is False


def test_verify_totp_code_never_raises_on_garbage():
    secret = totp.generate_secret()
    for junk in ["", "abc", "!!!!!!", "0" * 100, None]:
        assert totp.verify_totp_code(secret, junk) is False


def test_decrypt_with_a_rotated_key_raises_config_error_not_auth_error(monkeypatch):
    from cryptography.fernet import Fernet
    blob = totp.encrypt_secret("JBSWY3DPEHPK3PXP")
    monkeypatch.setattr("app.core.totp.settings.totp_encryption_key", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError):
        totp.decrypt_secret(blob)
