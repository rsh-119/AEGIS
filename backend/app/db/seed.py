"""Ephemeral dev-DB seeding — populates a fresh `aegis` database (e.g. the
Docker Postgres container, see docker-compose.yml) with realistic local
test data: users, holdings, watchlist items, a price alert, an AI-cache
entry, and a portfolio review.

Usage:
    python -m app.db.seed              # idempotent — safe to re-run
    python -m app.db.seed --reset      # wipes the 6 app tables first (CASCADE)

Refuses to run unless APP_ENV=development, so it can never be pointed at a
staging/production DATABASE_URL by accident.
"""

import argparse
import asyncio
import json
import sys
from datetime import date

from faker import Faker
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.auth import hash_password
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, engine
from app.models import AICache, Holding, PortfolioReview, PriceAlert, Subscription, User, WatchItem

DEV_PASSWORD = "DevTest123!"  # shared password for every seeded account — dev-only, printed below

# Curated real NSE tickers — Faker doesn't know Indian equities, so this
# stays hand-written rather than generated.
SAMPLE_HOLDINGS = [
    {"ticker": "ITC.NS", "company_name": "ITC", "shares": 25, "avg_price": 285.40,
     "buy_date": date(2025, 3, 12), "sector": "Tobacco"},
    {"ticker": "RELIANCE.NS", "company_name": "Reliance Industries", "shares": 8, "avg_price": 2650.75,
     "buy_date": date(2025, 1, 20), "sector": "Energy"},
    {"ticker": "HDFCBANK.NS", "company_name": "HDFC Bank", "shares": 15, "avg_price": 1580.00,
     "buy_date": date(2025, 5, 2), "sector": "Financial Services"},
    {"ticker": "TCS.NS", "company_name": "Tata Consultancy Services", "shares": 5, "avg_price": 3720.10,
     "buy_date": date(2025, 6, 18), "sector": "Information Technology"},
]

SAMPLE_WATCHLIST = [
    {"ticker": "INFY.NS", "company_name": "Infosys", "target_price": 1450.0},
    {"ticker": "TATAMOTORS.NS", "company_name": "Tata Motors", "target_price": 900.0},
    {"ticker": "SBIN.NS", "company_name": "State Bank of India", "target_price": 700.0},
]

# Real JSON shape produced by ai_service.diagnose_health — matches what
# /api/stocks/{ticker}/insights actually caches, so anything reading
# ai_cache in dev sees a realistic payload.
SAMPLE_HEALTH_CONTENT = json.dumps({
    "status": "Stable",
    "status_reason": "Seeded sample — mirrors the real health-diagnosis JSON shape for local dev.",
    "financial_health_score": 7,
    "summary": "Sample seeded AI health diagnosis for local development.",
    "concerns": ["This is seed data, not a real AI call — regenerate via /api/stocks/ITC.NS/insights for the real thing."],
})


def _guard_development_only() -> None:
    settings = get_settings()
    if settings.app_env != "development":
        print(
            f"Refusing to seed: APP_ENV={settings.app_env!r}, not 'development'. "
            "This guard exists so seed.py can never be pointed at a staging/prod DB by accident.",
            file=sys.stderr,
        )
        sys.exit(1)


async def _reset() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE users, holdings, watchlist, price_alerts, portfolio_reviews, ai_cache, subscriptions "
            "RESTART IDENTITY CASCADE"
        ))
    print("Reset: all 7 tables truncated (RESTART IDENTITY CASCADE).")


async def _get_or_create_user(session, *, email: str, username: str, is_admin: bool, is_pro: bool) -> User:
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        user = existing
    else:
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(DEV_PASSWORD),
            is_admin=is_admin,
        )
        session.add(user)
        await session.flush()  # get user.id before it's referenced by FK rows below

    if is_pro:
        # Pro status exists only in `subscriptions` (the users.is_pro column
        # was dropped in migration 8c1d4a7f9e20) — seed a row so
        # devtest@aegis.local actually passes get_pro_user_id/is_pro_user.
        sub = (await session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )).scalar_one_or_none()
        if sub is None:
            session.add(Subscription(user_id=user.id, plan="pro", status="active"))

    return user


async def _seed_holdings(session, user: User) -> None:
    for h in SAMPLE_HOLDINGS:
        existing = (await session.execute(
            select(Holding).where(Holding.user_id == user.id, Holding.ticker == h["ticker"])
        )).scalar_one_or_none()
        if existing:
            continue
        session.add(Holding(user_id=user.id, **h))


async def _seed_watchlist(session, user: User) -> None:
    for w in SAMPLE_WATCHLIST:
        # watchlist has a real DB-level unique constraint on (user_id, ticker)
        # — ON CONFLICT DO NOTHING is the correct idempotent primitive here,
        # not a SELECT-then-insert race.
        stmt = pg_insert(WatchItem).values(user_id=user.id, **w)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_watchlist_user_ticker")
        await session.execute(stmt)


async def _seed_price_alert(session, user: User) -> None:
    existing = (await session.execute(
        select(PriceAlert).where(PriceAlert.user_id == user.id, PriceAlert.ticker == "ITC.NS")
    )).scalar_one_or_none()
    if existing:
        return
    session.add(PriceAlert(
        user_id=user.id, ticker="ITC.NS", company_name="ITC",
        alert_type="below", target_price=280.0, is_active=True,
    ))


async def _seed_ai_cache(session) -> None:
    existing = (await session.execute(
        select(AICache).where(AICache.cache_key == "health:ITC.NS:v1")
    )).scalar_one_or_none()
    if existing:
        return
    session.add(AICache(cache_key="health:ITC.NS:v1", content=SAMPLE_HEALTH_CONTENT, model="seed-data"))


async def _seed_portfolio_review(session, user: User) -> None:
    existing = (await session.execute(
        select(PortfolioReview).where(PortfolioReview.user_id == user.id)
    )).scalar_one_or_none()
    if existing:
        return
    session.add(PortfolioReview(
        user_id=user.id,
        verdict="Sample seeded portfolio review — well-diversified across financials, energy, IT and consumer staples.",
        observations=["Seed data — not a real AI review.", "Regenerate via the real portfolio review endpoint for actual output."],
        holdings_sentiment=[{"ticker": h["ticker"], "sentiment": "neutral"} for h in SAMPLE_HOLDINGS],
        truncated=False,
        shown_holdings=len(SAMPLE_HOLDINGS),
        total_holdings=len(SAMPLE_HOLDINGS),
        incomplete_holdings=[],
        fingerprint="seed0000000000000000000",
    ))


async def seed(*, extra_users: int) -> None:
    _guard_development_only()
    # Fixed seed — Faker must generate the SAME emails/usernames on every
    # run (in call order) for _get_or_create_user's email lookup to find
    # the existing rows on a re-run instead of creating fresh duplicates.
    fake = Faker()
    Faker.seed(1234)

    async with AsyncSessionLocal() as session:
        primary = await _get_or_create_user(
            session, email="devtest@aegis.local", username="devtest", is_admin=True, is_pro=True,
        )
        await _seed_holdings(session, primary)
        await _seed_watchlist(session, primary)
        await _seed_price_alert(session, primary)
        await _seed_ai_cache(session)
        await _seed_portfolio_review(session, primary)

        # A few additional plain users (Faker-generated identity, same shared
        # dev password) so admin-panel / multi-user flows have more than one
        # row to look at — lighter touch than the primary user, watchlist only.
        for _ in range(extra_users):
            email = fake.unique.email()
            username = fake.unique.user_name()
            extra = await _get_or_create_user(
                session, email=email, username=username, is_admin=False, is_pro=False,
            )
            await _seed_watchlist(session, extra)

        await session.commit()

    print(f"Seed complete. Primary dev login: devtest@aegis.local / {DEV_PASSWORD}")
    print(f"Plus {extra_users} additional Faker-generated user(s), same shared password.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Truncate all 6 app tables first (RESTART IDENTITY CASCADE).")
    parser.add_argument("--extra-users", type=int, default=3, help="Number of additional Faker-generated users to seed (default: 3).")
    args = parser.parse_args()

    async def _run():
        _guard_development_only()
        if args.reset:
            await _reset()
        await seed(extra_users=args.extra_users)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
