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


async def init_db() -> None:
    """Bring the schema up to date via Alembic (alembic/versions/) instead of
    a hand-maintained list of raw `IF NOT EXISTS` ALTER TABLE strings — see
    alembic/versions/4f57afa92297_baseline.py for the migration that replaced
    that list and reconciled the drift it had accumulated. Runs on every
    startup, same as the old list did; upgrading to an already-current head
    is a no-op, so this is safe under multi-worker startup (--workers 2)."""
    import asyncio
    from alembic import command
    from alembic.config import Config

    def _upgrade():
        cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
        command.upgrade(cfg, "head")

    await asyncio.get_event_loop().run_in_executor(None, _upgrade)
