"""Guest-data import: localStorage holdings/watchlist → account.

The payload is fully attacker-controlled (it is literally read out of the
browser's own storage), so the questions are ownership, idempotency, caps and
whether hostile strings survive into the database as anything but data.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models import Holding, WatchItem

HOLDING = {"ticker": "TCS.NS", "shares": 10, "avg_price": 3000.0, "buy_date": "2025-01-01"}
WATCH = {"ticker": "INFY.NS", "company_name": "Infosys"}


async def _count(model, user_id: int) -> int:
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )).scalar_one()


# ── Auth ──────────────────────────────────────────────────────────────────────

async def test_sync_requires_authentication(client):
    r = await client.post("/api/auth/sync-guest-data",
                          json={"holdings": [HOLDING], "watchlist": [WATCH]})
    assert r.status_code == 401


async def test_sync_always_imports_into_the_caller_account(client, user_a, user_b, bearer):
    """There is no user_id in the payload, and there must not be — the import
    target is the token, never client input."""
    r = await client.post("/api/auth/sync-guest-data",
                          json={"holdings": [HOLDING], "watchlist": [WATCH],
                                "user_id": user_b.id},
                          headers=bearer(user_a.id))
    assert r.status_code == 200
    assert await _count(Holding, user_a.id) == 1
    assert await _count(Holding, user_b.id) == 0, "guest data landed on another account"


# ── Import behaviour ──────────────────────────────────────────────────────────

async def test_sync_imports_holdings_and_watchlist(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data",
                          json={"holdings": [HOLDING], "watchlist": [WATCH]},
                          headers=bearer(user_a.id))
    assert r.status_code == 200
    body = r.json()
    assert body["holdings"] == {"imported": 1, "skipped": 0}
    assert body["watchlist"] == {"imported": 1, "skipped": 0}


async def test_empty_payload_is_a_no_op(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data",
                          json={"holdings": [], "watchlist": []},
                          headers=bearer(user_a.id))
    assert r.status_code == 200
    assert r.json()["holdings"]["imported"] == 0


async def test_missing_fields_default_to_empty(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data", json={}, headers=bearer(user_a.id))
    assert r.status_code == 200


async def test_repeated_sync_does_not_duplicate_rows(client, user_a, bearer):
    """The frontend only clears localStorage on a 2xx, so a retried sync is
    expected — it must be idempotent, not additive."""
    payload = {"holdings": [HOLDING], "watchlist": [WATCH]}
    first = await client.post("/api/auth/sync-guest-data", json=payload, headers=bearer(user_a.id))
    second = await client.post("/api/auth/sync-guest-data", json=payload, headers=bearer(user_a.id))

    assert first.json()["holdings"]["imported"] == 1
    assert second.json()["holdings"]["imported"] == 0
    assert second.json()["holdings"]["skipped"] == 1
    assert await _count(Holding, user_a.id) == 1
    assert await _count(WatchItem, user_a.id) == 1


async def test_ten_repeated_syncs_stay_at_one_row(client, user_a, bearer):
    payload = {"holdings": [HOLDING], "watchlist": [WATCH]}
    for _ in range(10):
        await client.post("/api/auth/sync-guest-data", json=payload, headers=bearer(user_a.id))
    assert await _count(Holding, user_a.id) == 1
    assert await _count(WatchItem, user_a.id) == 1


async def test_distinct_buys_of_the_same_ticker_are_both_kept(client, user_a, bearer):
    """Buying the same stock twice on different dates is legitimate."""
    r = await client.post("/api/auth/sync-guest-data", json={"holdings": [
        HOLDING, {**HOLDING, "buy_date": "2025-06-01"},
    ]}, headers=bearer(user_a.id))
    assert r.json()["holdings"]["imported"] == 2


async def test_duplicate_watch_tickers_in_one_payload_collapse(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data",
                          json={"watchlist": [WATCH, WATCH]},
                          headers=bearer(user_a.id))
    assert r.status_code in (200, 409, 422)
    if r.status_code == 200:
        assert await _count(WatchItem, user_a.id) == 1


async def test_sync_does_not_disturb_another_users_rows(client, user_a, user_b, bearer):
    await client.post("/api/auth/sync-guest-data",
                      json={"watchlist": [WATCH]}, headers=bearer(user_b.id))
    await client.post("/api/auth/sync-guest-data",
                      json={"watchlist": [WATCH]}, headers=bearer(user_a.id))
    assert await _count(WatchItem, user_a.id) == 1
    assert await _count(WatchItem, user_b.id) == 1


# ── Caps and malformed payloads ───────────────────────────────────────────────

async def test_holdings_cap_is_enforced(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data",
                          json={"holdings": [HOLDING] * 51}, headers=bearer(user_a.id))
    assert r.status_code == 422


async def test_watchlist_cap_is_enforced(client, user_a, bearer):
    items = [{"ticker": f"T{i}.NS"} for i in range(101)]
    r = await client.post("/api/auth/sync-guest-data",
                          json={"watchlist": items}, headers=bearer(user_a.id))
    assert r.status_code == 422


async def test_a_huge_payload_is_rejected_not_absorbed(client, user_a, bearer):
    items = [{"ticker": f"T{i}.NS", "company_name": "x" * 5000} for i in range(500)]
    r = await client.post("/api/auth/sync-guest-data",
                          json={"watchlist": items}, headers=bearer(user_a.id))
    assert r.status_code == 422
    assert await _count(WatchItem, user_a.id) == 0


async def test_malformed_entries_are_rejected_wholesale(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data", json={
        "holdings": [HOLDING, {"ticker": "BAD"}],  # missing required fields
    }, headers=bearer(user_a.id))
    assert r.status_code == 422
    assert await _count(Holding, user_a.id) == 0, "a partially-invalid payload wrote rows anyway"


async def test_negative_and_zero_values_are_rejected(client, user_a, bearer):
    for bad in ({"shares": -5}, {"shares": 0}, {"avg_price": -1}, {"avg_price": 0}):
        r = await client.post("/api/auth/sync-guest-data",
                              json={"holdings": [{**HOLDING, **bad}]},
                              headers=bearer(user_a.id))
        assert r.status_code == 422, f"accepted {bad}"


async def test_wrong_types_are_rejected(client, user_a, bearer):
    for bad in ({"shares": "lots"}, {"buy_date": "not-a-date"}, {"avg_price": None}):
        r = await client.post("/api/auth/sync-guest-data",
                              json={"holdings": [{**HOLDING, **bad}]},
                              headers=bearer(user_a.id))
        assert r.status_code == 422, f"accepted {bad}"


async def test_unknown_fields_cannot_set_server_controlled_columns(client, user_a, user_b, bearer):
    """A crafted payload must not be able to set id/user_id/version."""
    r = await client.post("/api/auth/sync-guest-data", json={"holdings": [
        {**HOLDING, "id": 9999, "user_id": user_b.id, "version": 42},
    ]}, headers=bearer(user_a.id))
    assert r.status_code == 200

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Holding).where(Holding.user_id == user_a.id))).scalars().all()
        assert len(rows) == 1
        assert rows[0].id != 9999
        assert rows[0].user_id == user_a.id
        assert rows[0].version == 1
    assert await _count(Holding, user_b.id) == 0


async def test_json_body_that_is_not_an_object_is_rejected(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data", json=[1, 2, 3], headers=bearer(user_a.id))
    assert r.status_code == 422


async def test_malformed_json_is_rejected_cleanly(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data",
                          content=b"{not json",
                          headers={**bearer(user_a.id), "Content-Type": "application/json"})
    assert r.status_code == 422
    assert "Traceback" not in r.text


# ── Hostile strings ───────────────────────────────────────────────────────────

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "\"><svg/onload=alert(1)>",
    "'; DROP TABLE holdings; --",
]


async def test_hostile_strings_are_stored_as_inert_data(client, user_a, bearer):
    """They must round-trip byte-identically — neither executed nor silently
    mangled — and the tables must still exist afterwards."""
    for i, payload in enumerate(XSS_PAYLOADS):
        r = await client.post("/api/auth/sync-guest-data", json={"holdings": [
            {**HOLDING, "buy_date": f"2025-01-{i + 1:02d}", "company_name": payload, "notes": payload},
        ]}, headers=bearer(user_a.id))
        assert r.status_code == 200, r.text

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Holding).where(Holding.user_id == user_a.id))).scalars().all()
    stored = {r.company_name for r in rows}
    assert len(rows) == len(XSS_PAYLOADS), "SQL-injection-shaped input changed the row count"
    for payload in XSS_PAYLOADS:
        assert payload in stored, f"{payload!r} was mangled rather than stored verbatim"


async def test_sql_injection_in_ticker_does_not_execute(client, user_a, bearer):
    """Kept inside the column's 20-char limit so this isolates the injection
    question from the separate length-validation gap below."""
    r = await client.post("/api/auth/sync-guest-data", json={
        "watchlist": [{"ticker": "';DELETE FROM w--"}],
    }, headers=bearer(user_a.id))
    assert r.status_code == 200, r.text
    await client.post("/api/auth/sync-guest-data",
                      json={"watchlist": [WATCH]}, headers=bearer(user_a.id))
    assert await _count(WatchItem, user_a.id) == 2


async def test_unicode_and_control_characters_survive(client, user_a, bearer):
    r = await client.post("/api/auth/sync-guest-data", json={"holdings": [
        {**HOLDING, "company_name": "टाटा 株式会社 🏦"},
    ]}, headers=bearer(user_a.id))
    assert r.status_code == 200
    async with AsyncSessionLocal() as s:
        row = (await s.execute(select(Holding).where(Holding.user_id == user_a.id))).scalars().first()
    assert row.company_name == "टाटा 株式会社 🏦"


async def test_overlong_company_name_is_a_validation_error_not_a_500(client, user_a, bearer):
    """company_name maps to String(120). Without a schema-level max_length the
    value reaches Postgres and raises StringDataRightTruncationError, which
    surfaces as an unhandled 500."""
    r = await client.post("/api/auth/sync-guest-data", json={"holdings": [
        {**HOLDING, "company_name": "A" * 5000},
    ]}, headers=bearer(user_a.id))
    assert r.status_code == 422, f"overlong company_name produced {r.status_code}"


async def test_overlong_ticker_is_a_validation_error_not_a_500(client, user_a, bearer):
    """ticker maps to String(20)."""
    r = await client.post("/api/auth/sync-guest-data",
                          json={"watchlist": [{"ticker": "T" * 100}]},
                          headers=bearer(user_a.id))
    assert r.status_code == 422, f"overlong ticker produced {r.status_code}"


async def test_overlong_sector_is_a_validation_error_not_a_500(client, user_a, bearer):
    """sector maps to String(60)."""
    r = await client.post("/api/auth/sync-guest-data",
                          json={"holdings": [{**HOLDING, "sector": "S" * 500}]},
                          headers=bearer(user_a.id))
    assert r.status_code == 422, f"overlong sector produced {r.status_code}"
