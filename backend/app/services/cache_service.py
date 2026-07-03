"""
cache_service.py — Persistent DB-backed cache for expensive AI/data calls.

Two-level strategy:
  L1: in-memory dict (zero-cost, cleared on restart)
  L2: PostgreSQL ai_cache table (survives restarts, shared across processes)

Default TTL is 20 hours so summaries stay fresh day-to-day without
hammering Groq/OpenRouter on every page load.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models import AICache

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS: int = 20

# ── L1 in-memory layer ────────────────────────────────────────────────────────
_mem: dict[str, tuple[float, dict]] = {}  # key → (stored_epoch, data)

def _mem_get(key: str, ttl_hours: int) -> dict | None:
    import time
    entry = _mem.get(key)
    if entry and time.time() - entry[0] < ttl_hours * 3600:
        return entry[1]
    return None

def _mem_set(key: str, data: dict) -> None:
    import time
    _mem[key] = (time.time(), data)


# ── Public API ────────────────────────────────────────────────────────────────

async def get(key: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> dict | None:
    """Return cached dict if found and not expired, else None."""
    # L1 hit
    if (v := _mem_get(key, ttl_hours)) is not None:
        return v
    # L2 hit
    try:
        async with AsyncSessionLocal() as session:
            cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
            row = (await session.execute(
                select(AICache.content)
                .where(AICache.cache_key == key)
                .where(AICache.created_at >= cutoff)
                .order_by(AICache.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            if row:
                data = json.loads(row)
                _mem_set(key, data)          # promote to L1
                logger.info("DB cache hit: %s", key)
                return data
    except Exception as e:
        logger.warning("cache get error (%s): %s", key, e)
    return None


async def set(key: str, data: dict, model: str | None = None) -> None:
    """Persist data to L1 + L2, replacing any existing entry for this key."""
    _mem_set(key, data)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AICache).where(AICache.cache_key == key))
            session.add(AICache(
                cache_key=key,
                content=json.dumps(data, default=str),
                model=model,
            ))
            await session.commit()
        logger.info("DB cache set: %s", key)
    except Exception as e:
        logger.warning("cache set error (%s): %s", key, e)


async def invalidate(key: str) -> None:
    """Remove a specific key from both cache layers."""
    _mem.pop(key, None)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AICache).where(AICache.cache_key == key))
            await session.commit()
    except Exception as e:
        logger.warning("cache invalidate error (%s): %s", key, e)
