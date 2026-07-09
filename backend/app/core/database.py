"""Async SQLAlchemy engine, session factory, and Base."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

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


async def init_db() -> None:
    """Create all tables; apply additive migrations for existing tables."""
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive migrations — safe to run repeatedly (IF NOT EXISTS)
        migrations = [
            # Add user_id to holdings (existing rows keep NULL = legacy)
            "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE",
            # watchlist unique constraint was on ticker alone — relax it to (user_id, ticker)
            "ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE",
            # Remove old single-user unique constraint if it exists
            "ALTER TABLE watchlist DROP CONSTRAINT IF EXISTS watchlist_ticker_key",
            # The above never actually matched — the old unique constraint was
            # materialized as a plain unique INDEX (ix_watchlist_ticker), not a
            # named table CONSTRAINT, from an earlier `unique=True, index=True`
            # column definition. DROP CONSTRAINT silently no-ops on an index,
            # so this stale unique-on-ticker-alone index survived, blocking any
            # second user from ever watching a stock someone else already had.
            "DROP INDEX IF EXISTS ix_watchlist_ticker",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_watchlist_user_ticker ON watchlist (user_id, ticker)",
            # Admin flag for the /api/admin/* dashboard — defaults false, granted manually
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE",
        ]
        from sqlalchemy import text
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as exc:
                # Non-fatal — table may already be migrated or constraint may not exist
                import logging
                logging.getLogger(__name__).debug("migration skipped: %s", exc)
