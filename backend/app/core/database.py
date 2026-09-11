"""Async SQLAlchemy engine, session factory, and Base."""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# backend/ — parent of app/core/ two levels up. Alembic needs an absolute
# path since init_db() may run from any process cwd.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a scoped async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Arbitrary but fixed key for the migration advisory lock. Any process running
# migrations for this database must use the same value.
_MIGRATION_LOCK_KEY = 8_421_337


async def init_db() -> None:
    """Bring the schema up to date via Alembic (alembic/versions/) instead of
    a hand-maintained list of raw `IF NOT EXISTS` ALTER TABLE strings — see
    alembic/versions/4f57afa92297_baseline.py for the migration that replaced
    that list and reconciled the drift it had accumulated. Runs on every
    startup, same as the old list did.

    Serialised behind a Postgres advisory lock. This used to be documented as
    "safe under multi-worker startup" on the grounds that upgrading to an
    already-current head is a no-op — true only once the database is already
    at head. When it is NOT (a first deploy, a fresh environment, or any
    deploy that ships a new migration — i.e. exactly when this code matters),
    concurrent workers race: all of them try to create `alembic_version` or
    apply the same revision, and every loser dies with
    UniqueViolationError/DuplicateTable. init_db() is awaited in the lifespan
    with nothing catching it, so those workers fail to start. Reproduced with
    4 concurrent upgrades against an empty database: 1 succeeded, 3 crashed.

    With the lock, the first process migrates and the rest block, then find
    head already current and no-op. Session-scoped (not xact-scoped) so it
    spans the executor call, and released explicitly in `finally` because the
    connection goes back to the pool still holding it otherwise.
    """
    import asyncio
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    def _upgrade():
        cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
        # Do not let Alembic reconfigure this process's logging. env.py's
        # fileConfig() call both disables every existing logger (silencing all
        # 26 `app.*` loggers for the life of the process) and replaces the root
        # handler, which swapped production's structured JSON formatter for the
        # dev one. Both were confirmed in the built container. The `alembic`
        # CLI passes no attributes and keeps its own logging.
        cfg.attributes["configure_logger"] = False
        command.upgrade(cfg, "head")

    loop = asyncio.get_event_loop()

    if engine.dialect.name != "postgresql":
        await loop.run_in_executor(None, _upgrade)
        return

    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_KEY})
        try:
            await loop.run_in_executor(None, _upgrade)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _MIGRATION_LOCK_KEY})
