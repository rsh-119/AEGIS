"""/api/admin/* — internal dashboard for the app owner. All routes require is_admin."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.models import Holding, PriceAlert, Subscription, User, WatchItem

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, user_id)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


class UserProUpdate(BaseModel):
    is_pro: bool


@router.patch("/users/{user_id}")
async def set_user_pro(
    user_id: int,
    body: UserProUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a user's Pro entitlement — no billing exists yet, so this is
    currently the only way to grant/revoke Pro access. Upserts into
    subscriptions rather than writing users.is_pro (see entitlements.py) —
    request/response shape stays {is_pro: bool} on purpose, so the frontend
    (admin/page.tsx's toggle, ProGate, etc.) needs zero changes."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    sub = (
        await db.execute(select(Subscription).where(Subscription.user_id == user_id))
    ).scalar_one_or_none()
    if sub is None:
        sub = Subscription(user_id=user_id)
        db.add(sub)
    sub.plan = "pro" if body.is_pro else "free"
    sub.status = "active"
    await db.flush()
    return {**user.to_dict(), "is_pro": sub.plan == "pro"}


@router.get("/users")
async def list_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """All registered users with per-user activity counts, newest first."""
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()

    # One grouped count query per table beats N+1 per-user queries.
    holdings_counts = dict(
        (await db.execute(select(Holding.user_id, func.count()).group_by(Holding.user_id))).all()
    )
    watchlist_counts = dict(
        (await db.execute(select(WatchItem.user_id, func.count()).group_by(WatchItem.user_id))).all()
    )
    alert_counts = dict(
        (await db.execute(select(PriceAlert.user_id, func.count()).group_by(PriceAlert.user_id))).all()
    )
    # is_pro now lives in subscriptions, not the (still-present but no
    # longer read) users.is_pro column — one grouped query, same pattern
    # as the counts above, not N+1.
    pro_plans = dict(
        (await db.execute(select(Subscription.user_id, Subscription.plan)
                           .where(Subscription.status == "active"))).all()
    )

    return {
        "users": [
            {
                **u.to_dict(),
                "is_pro": pro_plans.get(u.id) == "pro",
                "holdings_count": holdings_counts.get(u.id, 0),
                "watchlist_count": watchlist_counts.get(u.id, 0),
                "alerts_count": alert_counts.get(u.id, 0),
            }
            for u in users
        ]
    }


@router.get("/stats")
async def admin_stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Summary counters for the dashboard header."""
    total_users     = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    active_users    = (await db.execute(select(func.count()).select_from(User).where(User.is_active))).scalar_one()
    total_holdings  = (await db.execute(select(func.count()).select_from(Holding))).scalar_one()
    total_watchlist = (await db.execute(select(func.count()).select_from(WatchItem))).scalar_one()
    total_alerts    = (await db.execute(select(func.count()).select_from(PriceAlert))).scalar_one()
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_holdings": total_holdings,
        "total_watchlist_items": total_watchlist,
        "total_alerts": total_alerts,
    }
