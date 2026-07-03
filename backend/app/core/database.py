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
        ]
        from sqlalchemy import text
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as exc:
                # Non-fatal — table may already be migrated or constraint may not exist
                import logging
                logging.getLogger(__name__).debug("migration skipped: %s", exc)
