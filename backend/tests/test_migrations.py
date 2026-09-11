"""Schema is produced by Alembic alone, and the constraints the application
relies on for correctness actually exist in the database."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.database import engine


async def _fetch(sql: str, **params):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params)).fetchall()
    return rows


async def test_schema_is_at_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()

    rows = await _fetch("SELECT version_num FROM alembic_version")
    assert [r[0] for r in rows] == [head]


async def test_all_application_tables_exist():
    rows = await _fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    names = {r[0] for r in rows}
    assert {
        "users", "subscriptions", "holdings", "watchlist",
        "price_alerts", "portfolio_reviews", "ai_cache",
    } <= names


@pytest.mark.parametrize("table,column", [
    ("users", "email"),
    ("users", "username"),
    ("users", "google_id"),
    ("subscriptions", "user_id"),
])
async def test_unique_constraints_present(table, column):
    rows = await _fetch(
        """
        SELECT i.indisunique
        FROM pg_index i
        JOIN pg_class c   ON c.oid = i.indrelid
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
        WHERE c.relname = :t AND a.attname = :col AND i.indisunique
        """,
        t=table, col=column,
    )
    assert rows, f"{table}.{column} has no unique index — duplicates are possible"


async def test_watchlist_has_composite_unique_constraint():
    """sync_guest_data relies on ON CONFLICT against this constraint by name."""
    rows = await _fetch(
        "SELECT conname FROM pg_constraint WHERE conname = 'uq_watchlist_user_ticker'"
    )
    assert rows, "uq_watchlist_user_ticker missing — sync-guest-data's ON CONFLICT would error"


@pytest.mark.parametrize("table", [
    "holdings", "watchlist", "price_alerts", "portfolio_reviews", "subscriptions",
])
async def test_user_fk_cascades_on_delete(table):
    """Deleting a user must not strand their rows."""
    rows = await _fetch(
        """
        SELECT c.confdeltype::text
        FROM pg_constraint c
        JOIN pg_class child  ON child.oid  = c.conrelid
        JOIN pg_class parent ON parent.oid = c.confrelid
        WHERE c.contype = 'f' AND child.relname = :t AND parent.relname = 'users'
        """,
        t=table,
    )
    assert rows, f"{table} has no FK to users"
    assert all(r[0] == "c" for r in rows), f"{table}.user_id FK is not ON DELETE CASCADE"


async def test_holdings_version_column_is_not_nullable():
    """Optimistic concurrency depends on version always being present."""
    rows = await _fetch(
        "SELECT is_nullable, column_default FROM information_schema.columns "
        "WHERE table_name='holdings' AND column_name='version'"
    )
    assert rows and rows[0][0] == "NO"


async def test_hashed_password_is_nullable_for_oauth_accounts():
    rows = await _fetch(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='users' AND column_name='hashed_password'"
    )
    assert rows and rows[0][0] == "YES"


async def test_concurrent_startup_migrations_do_not_race():
    """init_db() runs on every worker's startup. The Dockerfile ships
    `--workers 2` and k8s/deployment.yaml sets `replicas: 2`, so four
    processes call it at once — and on a database that is not yet at head
    (a first deploy, or any deploy carrying a new migration) they all try to
    create `alembic_version` or apply the same revision.

    Without serialisation this reproduces as: 1 worker succeeds, the rest die
    with UniqueViolationError. init_db() is awaited in the lifespan with
    nothing catching it, so those workers fail to start.
    """
    import asyncio
    import os
    from sqlalchemy.ext.asyncio import create_async_engine

    admin_url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    race_db = "aegis_migration_race"
    race_url = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + f"/{race_db}"

    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {race_db}"))
        await conn.execute(text(f"CREATE DATABASE {race_db}"))

    # alembic/env.py resolves the URL from get_settings().database_url, so
    # both the settings value and the engine holding the advisory lock have to
    # point at the race database for this to exercise the real path.
    import app.core.database as db_mod
    from app.core.config import get_settings

    settings = get_settings()
    original_url = settings.database_url
    original_engine = db_mod.engine
    race_engine = create_async_engine(race_url)
    settings.database_url = race_url
    db_mod.engine = race_engine
    try:
        results = await asyncio.gather(
            *[db_mod.init_db() for _ in range(4)], return_exceptions=True
        )
        failures = [r for r in results if isinstance(r, BaseException)]
        assert not failures, (
            f"{len(failures)}/4 concurrent startup migrations failed against a "
            f"fresh database — first error: {failures[0]!r}"
        )

        async with race_engine.connect() as conn:
            rows = (await conn.execute(text("SELECT version_num FROM alembic_version"))).fetchall()
        assert len(rows) == 1, f"alembic_version ended up with {len(rows)} rows"
    finally:
        settings.database_url = original_url
        db_mod.engine = original_engine
        await race_engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {race_db}"))
        await admin.dispose()


async def test_indexes_exist_on_hot_lookup_columns():
    """Every per-user list endpoint filters on user_id; reset-password looks
    up by reset_token_hash. Missing indexes here are seq scans per request."""
    rows = await _fetch(
        "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname='public'"
    )
    defs = "\n".join(f"{t}:{d}" for t, d in rows)
    for table, col in [
        ("holdings", "user_id"), ("watchlist", "user_id"),
        ("price_alerts", "user_id"), ("portfolio_reviews", "user_id"),
        ("users", "reset_token_hash"),
    ]:
        assert f"{table}:" in defs and col in defs, f"no index covering {table}.{col}"
