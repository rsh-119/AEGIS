"""Pro-tier entitlement checks.

Lives here rather than in core/auth.py because it's needed by multiple
routers (stocks.py, documents.py) — unlike require_admin, which only
admin.py itself needs. core/auth.py has zero DB/model dependencies today;
this is kept separate so that stays true.

Backed by the `subscriptions` table (app.models.Subscription), not
users.is_pro — that column is still present on User but no longer read by
application code as of this table's introduction. See
alembic/versions/<hash>_add_subscriptions.py for the backfill that gave
every pre-existing is_pro=True user a matching active/pro row.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.models import Subscription


async def get_pro_user_id(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> int:
    """Hard-gate a route to Pro users. 401s if not logged in (via
    get_current_user_id), 403s if logged in but not Pro."""
    if not await _is_pro(user_id, db):
        raise HTTPException(status_code=403, detail="This feature requires an AEGIS Pro subscription")
    return user_id


async def is_pro_user(user_id: int | None, db: AsyncSession) -> bool:
    """Soft check for endpoints that degrade gracefully instead of hard-
    gating (used by /insights, where forecast is Pro-only but the AI
    analysis and health check in the same response must stay free)."""
    if user_id is None:
        return False
    return await _is_pro(user_id, db)


async def _is_pro(user_id: int, db: AsyncSession) -> bool:
    sub = (
        await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    ).scalar_one_or_none()
    if sub is None or sub.plan != "pro" or sub.status != "active":
        return False
    if sub.expires_at is not None and sub.expires_at < datetime.utcnow():
        return False
    return True
