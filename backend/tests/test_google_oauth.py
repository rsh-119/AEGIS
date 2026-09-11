"""Google Sign-In. Google's tokeninfo endpoint is mocked at the httpx layer
so the real service is never contacted."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.core.auth import ACCESS_COOKIE_NAME
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models import User

settings = get_settings()
CLIENT_ID = settings.google_client_id


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _mock_tokeninfo(monkeypatch, *, status: int = 200, claims: dict | None = None,
                    raise_error: Exception | None = None):
    """Patch the single httpx GET core/oauth.py makes."""
    async def _get(self, url, **kwargs):
        if raise_error:
            raise raise_error
        return _FakeResponse(status, claims or {})

    monkeypatch.setattr(httpx.AsyncClient, "get", _get)


def _claims(**overrides) -> dict:
    base = {
        "sub": "google-user-1",
        "email": "gauth@example.com",
        "email_verified": "true",
        "aud": CLIENT_ID,
        "iss": "https://accounts.google.com",
    }
    base.update(overrides)
    return base


async def _get_user(email: str) -> User | None:
    async with AsyncSessionLocal() as s:
        return (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()


# ── Happy paths ───────────────────────────────────────────────────────────────

async def test_valid_google_token_creates_account_and_session(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, claims=_claims())
    r = await client.post("/api/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "gauth@example.com"
    assert body["auth_provider"] == "google"
    assert body["has_password"] is False
    assert ACCESS_COOKIE_NAME in r.cookies


async def test_second_login_reuses_the_same_account(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, claims=_claims())
    first = await client.post("/api/auth/google", json={"credential": "t"})
    second = await client.post("/api/auth/google", json={"credential": "t"})
    assert first.json()["id"] == second.json()["id"]


async def test_username_is_derived_from_the_email_local_part(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, claims=_claims(email="Jane.Doe+tag@example.com"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.json()["username"] == "janedoetag"


async def test_username_collision_gets_a_suffix(client, monkeypatch, make_user):
    await make_user(email="taken@example.com", username="collide")
    _mock_tokeninfo(monkeypatch, claims=_claims(email="collide@example.com"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 200
    assert r.json()["username"] != "collide"
    assert r.json()["username"].startswith("collide")


async def test_verified_email_links_to_an_existing_local_account(client, monkeypatch, make_user):
    local = await make_user(email="both@example.com", username="bothuser")
    _mock_tokeninfo(monkeypatch, claims=_claims(email="both@example.com", sub="g-link-1"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 200
    assert r.json()["id"] == local.id
    assert (await _get_user("both@example.com")).google_id == "g-link-1"


# ── Rejections ────────────────────────────────────────────────────────────────

async def test_unverified_email_does_not_link_to_an_existing_account(client, monkeypatch, make_user):
    """An unverified Google email must never take over a local account — that
    would be a full account takeover for anyone who can create a Google
    account with someone else's address unverified."""
    local = await make_user(email="victim@example.com", username="victimuser")
    _mock_tokeninfo(monkeypatch, claims=_claims(email="victim@example.com",
                                                email_verified="false", sub="g-attacker"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 401
    assert (await _get_user("victim@example.com")).google_id is None


async def test_audience_mismatch_is_rejected(client, monkeypatch):
    """A token minted for a *different* app's client id must not be accepted."""
    _mock_tokeninfo(monkeypatch, claims=_claims(aud="some-other-app.apps.googleusercontent.com"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 401
    assert "this app" in r.json()["detail"].lower()


async def test_missing_audience_claim_is_rejected(client, monkeypatch):
    claims = _claims()
    claims.pop("aud")
    _mock_tokeninfo(monkeypatch, claims=claims)
    assert (await client.post("/api/auth/google", json={"credential": "t"})).status_code == 401


async def test_expired_or_invalid_token_is_rejected(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, status=400, claims={"error": "invalid_token"})
    r = await client.post("/api/auth/google", json={"credential": "expired"})
    assert r.status_code == 401


async def test_network_failure_is_401_not_500(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, raise_error=httpx.ConnectError("dns failure"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 401


async def test_timeout_is_401_not_500(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, raise_error=httpx.ReadTimeout("slow"))
    assert (await client.post("/api/auth/google", json={"credential": "t"})).status_code == 401


async def test_google_login_is_501_when_client_id_is_unset(client, monkeypatch):
    monkeypatch.setattr("app.core.oauth.settings.google_client_id", "")
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 501


async def test_no_verified_email_and_no_existing_account_is_rejected(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, claims=_claims(email=None, email_verified="false"))
    assert (await client.post("/api/auth/google", json={"credential": "t"})).status_code == 401


async def test_inactive_google_account_cannot_sign_in(client, monkeypatch, make_user):
    await make_user(email="ginactive@example.com", username="ginactive", password=None,
                    auth_provider="google", google_id="g-inactive", is_active=False)
    _mock_tokeninfo(monkeypatch, claims=_claims(email="ginactive@example.com", sub="g-inactive"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 403


async def test_google_account_with_2fa_gets_the_challenge_not_a_session(client, monkeypatch, make_user, db):
    u = await make_user(email="g2fa@example.com", username="g2fauser", password=None,
                        auth_provider="google", google_id="g-2fa")
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(User).where(User.id == u.id))).scalar_one()
        row.is_2fa_enabled = True
        row.totp_secret = __import__("app.core.totp", fromlist=["x"]).encrypt_secret("JBSWY3DPEHPK3PXP")
        await s.commit()

    _mock_tokeninfo(monkeypatch, claims=_claims(email="g2fa@example.com", sub="g-2fa"))
    r = await client.post("/api/auth/google", json={"credential": "t"})
    assert r.status_code == 200
    assert r.json()["requires_2fa"] is True
    assert ACCESS_COOKIE_NAME not in r.cookies


async def test_google_response_never_leaks_the_credential(client, monkeypatch):
    _mock_tokeninfo(monkeypatch, claims=_claims())
    r = await client.post("/api/auth/google", json={"credential": "super-secret-id-token"})
    assert "super-secret-id-token" not in r.text
