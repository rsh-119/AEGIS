"""Authorization: cross-user object access (IDOR), admin gating, and the
anonymous/free/pro/admin entitlement matrix enforced server-side.

Every Pro check here goes straight at the backend with a real token — a
frontend <ProGate> is presentation, not authorization.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models import Holding, PortfolioReview, PriceAlert, Subscription, WatchItem


# ── Fixtures that give USER_A some resources ──────────────────────────────────

async def _holding_for(user_id: int) -> Holding:
    async with AsyncSessionLocal() as s:
        h = Holding(user_id=user_id, ticker="TCS.NS", company_name="TCS",
                    shares=10, avg_price=3000.0, buy_date=date(2025, 1, 1))
        s.add(h)
        await s.commit()
        await s.refresh(h)
        return h


async def _watch_for(user_id: int) -> WatchItem:
    async with AsyncSessionLocal() as s:
        w = WatchItem(user_id=user_id, ticker="INFY.NS", company_name="Infosys")
        s.add(w)
        await s.commit()
        await s.refresh(w)
        return w


async def _alert_for(user_id: int) -> PriceAlert:
    async with AsyncSessionLocal() as s:
        a = PriceAlert(user_id=user_id, ticker="ITC.NS", alert_type="above", target_price=500.0)
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


# ── IDOR: holdings ────────────────────────────────────────────────────────────

async def test_user_b_cannot_read_user_a_holdings(client, user_a, user_b, bearer):
    await _holding_for(user_a.id)
    r = await client.get("/api/portfolio", headers=bearer(user_b.id))
    assert r.status_code == 200
    assert r.json()["holdings"] == []


async def test_user_b_cannot_patch_user_a_holding(client, user_a, user_b, bearer):
    h = await _holding_for(user_a.id)
    r = await client.patch(f"/api/portfolio/{h.id}",
                           json={"version": h.version, "shares": 999},
                           headers=bearer(user_b.id))
    assert r.status_code == 404, "cross-user holding update allowed"

    async with AsyncSessionLocal() as s:
        fresh = (await s.execute(select(Holding).where(Holding.id == h.id))).scalar_one()
        assert fresh.shares == 10, "victim's holding was modified"


async def test_user_b_cannot_delete_user_a_holding(client, user_a, user_b, bearer):
    h = await _holding_for(user_a.id)
    r = await client.delete(f"/api/portfolio/{h.id}", headers=bearer(user_b.id))
    assert r.status_code == 404

    async with AsyncSessionLocal() as s:
        assert (await s.execute(select(Holding).where(Holding.id == h.id))).scalar_one_or_none() is not None


async def test_anonymous_cannot_touch_holdings(client, user_a):
    h = await _holding_for(user_a.id)
    assert (await client.get("/api/portfolio")).status_code == 401
    assert (await client.delete(f"/api/portfolio/{h.id}")).status_code == 401
    assert (await client.patch(f"/api/portfolio/{h.id}", json={"version": 1})).status_code == 401
    assert (await client.post("/api/portfolio", json={
        "ticker": "X", "shares": 1, "avg_price": 1, "buy_date": "2025-01-01"})).status_code == 401


# ── IDOR: watchlist ───────────────────────────────────────────────────────────

async def test_user_b_cannot_read_or_delete_user_a_watchlist(client, user_a, user_b, bearer):
    w = await _watch_for(user_a.id)
    listed = await client.get("/api/watchlist", headers=bearer(user_b.id))
    assert listed.status_code == 200 and listed.json()["items"] == []

    r = await client.delete(f"/api/watchlist/{w.id}", headers=bearer(user_b.id))
    assert r.status_code == 404
    async with AsyncSessionLocal() as s:
        assert (await s.execute(select(WatchItem).where(WatchItem.id == w.id))).scalar_one_or_none() is not None


async def test_anonymous_cannot_touch_watchlist(client):
    assert (await client.get("/api/watchlist")).status_code == 401
    assert (await client.post("/api/watchlist", json={"ticker": "TCS"})).status_code == 401
    assert (await client.delete("/api/watchlist/1")).status_code == 401


# ── IDOR: alerts ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,suffix,body", [
    ("get", "", None),
    ("patch", "/{id}", {"target_price": 1.0}),
    ("delete", "/{id}", None),
    ("post", "/{id}/dismiss", None),
])
async def test_user_b_cannot_reach_user_a_alerts(client, user_a, user_b, bearer, method, suffix, body):
    a = await _alert_for(user_a.id)
    url = "/api/alerts" + suffix.format(id=a.id)
    kwargs = {"headers": bearer(user_b.id)}
    if body is not None:
        kwargs["json"] = body
    r = await getattr(client, method)(url, **kwargs)
    if suffix == "":
        assert r.json()["alerts"] == []
    else:
        assert r.status_code == 404, f"{method.upper()} {url} leaked another user's alert"

    async with AsyncSessionLocal() as s:
        fresh = (await s.execute(select(PriceAlert).where(PriceAlert.id == a.id))).scalar_one()
        assert fresh.target_price == 500.0 and fresh.is_active is True


async def test_anonymous_cannot_touch_alerts(client):
    assert (await client.get("/api/alerts")).status_code == 401
    assert (await client.post("/api/alerts", json={
        "ticker": "TCS", "alert_type": "above", "target_price": 1})).status_code == 401


# ── IDOR: AI portfolio reviews ────────────────────────────────────────────────

async def test_user_b_cannot_read_user_a_stored_ai_review(client, user_a, user_b, bearer):
    async with AsyncSessionLocal() as s:
        s.add(PortfolioReview(
            user_id=user_a.id, verdict="A's private verdict", observations=[],
            holdings_sentiment=[], truncated=False, shown_holdings=1,
            total_holdings=1, incomplete_holdings=[], fingerprint="abc123",
        ))
        await s.commit()

    r = await client.get("/api/portfolio/insights/ai/latest", headers=bearer(user_b.id))
    assert r.status_code == 200
    assert r.json()["ai"] is None, "another user's AI review was returned"


# ── IDOR: profile ─────────────────────────────────────────────────────────────

async def test_patch_me_only_ever_edits_the_caller(client, user_a, user_b, bearer):
    r = await client.patch("/api/auth/me", json={"username": "hijacked"}, headers=bearer(user_b.id))
    assert r.status_code == 200
    assert r.json()["id"] == user_b.id

    async with AsyncSessionLocal() as s:
        from app.models import User
        a = (await s.execute(select(User).where(User.id == user_a.id))).scalar_one()
        assert a.username == user_a.username


async def test_deleted_user_token_cannot_be_used(client, user_a, bearer):
    async with AsyncSessionLocal() as s:
        from app.models import User
        u = (await s.execute(select(User).where(User.id == user_a.id))).scalar_one()
        await s.delete(u)
        await s.commit()
    r = await client.get("/api/auth/me", headers=bearer(user_a.id))
    assert r.status_code == 404


# ── Admin ─────────────────────────────────────────────────────────────────────

ADMIN_ROUTES = [("get", "/api/admin/users"), ("get", "/api/admin/stats")]


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
async def test_admin_routes_reject_anonymous(client, method, url):
    assert (await getattr(client, method)(url)).status_code == 401


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
async def test_admin_routes_reject_normal_users(client, user_a, bearer, method, url):
    assert (await getattr(client, method)(url)).status_code == 401
    r = await getattr(client, method)(url, headers=bearer(user_a.id))
    assert r.status_code == 403


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
async def test_admin_routes_reject_pro_users(client, pro_user, bearer, method, url):
    """Paying for Pro must not confer admin."""
    r = await getattr(client, method)(url, headers=bearer(pro_user.id))
    assert r.status_code == 403


@pytest.mark.parametrize("method,url", ADMIN_ROUTES)
async def test_admin_routes_allow_admins(client, admin_user, bearer, method, url):
    assert (await getattr(client, method)(url, headers=bearer(admin_user.id))).status_code == 200


async def test_non_admin_cannot_grant_themselves_pro(client, user_a, bearer):
    r = await client.patch(f"/api/admin/users/{user_a.id}", json={"is_pro": True},
                           headers=bearer(user_a.id))
    assert r.status_code == 403
    async with AsyncSessionLocal() as s:
        assert (await s.execute(
            select(Subscription).where(Subscription.user_id == user_a.id)
        )).scalar_one_or_none() is None


async def test_admin_can_grant_and_revoke_pro(client, admin_user, user_a, bearer):
    grant = await client.patch(f"/api/admin/users/{user_a.id}", json={"is_pro": True},
                               headers=bearer(admin_user.id))
    assert grant.status_code == 200 and grant.json()["is_pro"] is True

    revoke = await client.patch(f"/api/admin/users/{user_a.id}", json={"is_pro": False},
                                headers=bearer(admin_user.id))
    assert revoke.json()["is_pro"] is False


async def test_admin_user_listing_never_exposes_password_hashes(client, admin_user, user_a, bearer):
    r = await client.get("/api/admin/users", headers=bearer(admin_user.id))
    assert r.status_code == 200
    body = r.text
    assert "hashed_password" not in body and "$2b$" not in body
    assert "totp_secret" not in body and "backup_codes" not in body
    assert "reset_token_hash" not in body


# ── Pro entitlements — the hard gates ─────────────────────────────────────────

PRO_ROUTES = [
    "/api/stocks/TCS.NS/forecast",
    "/api/stocks/TCS.NS/concall-summary",
    "/api/stocks/TCS.NS/analyst-targets",
    "/api/stocks/TCS.NS/analyst-forecasts",
]


@pytest.mark.parametrize("url", PRO_ROUTES)
async def test_pro_routes_401_for_anonymous(client, url):
    assert (await client.get(url)).status_code == 401


@pytest.mark.parametrize("url", PRO_ROUTES)
async def test_pro_routes_403_for_free_users(client, user_a, bearer, url):
    r = await client.get(url, headers=bearer(user_a.id))
    assert r.status_code == 403, f"{url} served a free user"
    assert "pro" in r.json()["detail"].lower()


@pytest.mark.parametrize("url", PRO_ROUTES)
async def test_pro_routes_pass_the_gate_for_pro_users(client, pro_user, bearer, url):
    """Past the entitlement gate the upstream data source is disabled in
    tests, so anything except 401/403 proves the gate itself let them in."""
    r = await client.get(url, headers=bearer(pro_user.id))
    assert r.status_code not in (401, 403), f"{url} blocked a Pro user"


async def test_document_analyze_is_pro_gated(client, user_a, pro_user, bearer):
    body = {"text": "x" * 500, "company": "TCS"}
    assert (await client.post("/api/documents/analyze", json=body)).status_code == 401
    assert (await client.post("/api/documents/analyze", json=body,
                              headers=bearer(user_a.id))).status_code == 403


# ── Pro entitlements — subscription state edge cases ──────────────────────────

async def test_canceled_subscription_does_not_grant_pro(client, make_user, bearer):
    u = await make_user(pro=True, pro_status="canceled")
    r = await client.get("/api/stocks/TCS.NS/concall-summary", headers=bearer(u.id))
    assert r.status_code == 403


async def test_past_due_subscription_does_not_grant_pro(client, make_user, bearer):
    u = await make_user(pro=True, pro_status="past_due")
    assert (await client.get("/api/stocks/TCS.NS/concall-summary",
                             headers=bearer(u.id))).status_code == 403


async def test_expired_subscription_does_not_grant_pro(client, make_user, bearer):
    u = await make_user(pro=True, pro_expires_at=datetime.utcnow() - timedelta(days=1))
    r = await client.get("/api/stocks/TCS.NS/concall-summary", headers=bearer(u.id))
    assert r.status_code == 403, "an expired subscription still unlocked Pro"


async def test_future_expiry_still_grants_pro(client, make_user, bearer):
    u = await make_user(pro=True, pro_expires_at=datetime.utcnow() + timedelta(days=30))
    r = await client.get("/api/stocks/TCS.NS/concall-summary", headers=bearer(u.id))
    assert r.status_code != 403


async def test_free_plan_row_does_not_grant_pro(client, make_user, bearer):
    u = await make_user()
    async with AsyncSessionLocal() as s:
        s.add(Subscription(user_id=u.id, plan="free", status="active"))
        await s.commit()
    assert (await client.get("/api/stocks/TCS.NS/concall-summary",
                             headers=bearer(u.id))).status_code == 403


async def test_users_table_has_no_is_pro_column_to_drift_out_of_sync(client, make_user, bearer):
    """The old users.is_pro boolean was dropped (migration 8c1d4a7f9e20) so it
    can no longer disagree with the `subscriptions` row that actually grants
    access. Assert both halves: the column is gone from the live schema, and a
    user with no subscription row is still locked out."""
    from sqlalchemy import inspect as sa_inspect
    from app.core.database import engine

    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {c["name"] for c in sa_inspect(sync_conn).get_columns("users")}
        )
    assert "is_pro" not in cols, (
        "users.is_pro is back — Pro status must live only in `subscriptions`, "
        "otherwise the two can disagree and a user can read as Pro without being Pro"
    )

    u = await make_user()
    assert (await client.get("/api/stocks/TCS.NS/concall-summary",
                             headers=bearer(u.id))).status_code == 403


async def test_user_payloads_still_report_is_pro_from_subscriptions(client, user_a, pro_user, bearer):
    """Dropping the column must not change the API contract: /api/auth/me still
    carries an is_pro flag, now derived from `subscriptions`."""
    free = await client.get("/api/auth/me", headers=bearer(user_a.id))
    assert free.status_code == 200 and free.json()["is_pro"] is False

    paid = await client.get("/api/auth/me", headers=bearer(pro_user.id))
    assert paid.status_code == 200 and paid.json()["is_pro"] is True


# ── Pro entitlements — soft gate ──────────────────────────────────────────────

async def test_insights_soft_gate_reports_locked_for_anonymous(client):
    r = await client.get("/api/stocks/TCS.NS/insights")
    assert r.status_code == 200
    assert r.json()["forecast_locked"] is True


async def test_insights_soft_gate_reports_locked_for_free_users(client, user_a, bearer):
    r = await client.get("/api/stocks/TCS.NS/insights", headers=bearer(user_a.id))
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_locked"] is True
    assert body.get("forecast") in (None, {}), "forecast data returned to a free user"


async def test_insights_soft_gate_unlocks_for_pro(client, pro_user, bearer):
    r = await client.get("/api/stocks/TCS.NS/insights", headers=bearer(pro_user.id))
    assert r.status_code == 200
    assert r.json()["forecast_locked"] is False


async def test_free_user_cannot_forge_pro_via_a_crafted_body(client, user_a, bearer):
    """No route should read plan/entitlement state from client input."""
    r = await client.get("/api/stocks/TCS.NS/insights?is_pro=true",
                         headers=bearer(user_a.id))
    assert r.json()["forecast_locked"] is True
