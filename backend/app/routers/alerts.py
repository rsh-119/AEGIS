"""/api/alerts/* — price alert CRUD (requires auth)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.models import PriceAlert
from app.schemas import AlertCreate, AlertUpdate
from app.services import stock_service

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(PriceAlert)
            .where(PriceAlert.user_id == user_id)
            .order_by(PriceAlert.created_at.desc())
        )
    ).scalars().all()
    return {"alerts": [r.to_dict() for r in rows]}


@router.post("", status_code=201)
async def create_alert(
    body: AlertCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ticker = stock_service.normalise_ticker(body.ticker)
    q = await stock_service.get_quote(ticker)
    alert = PriceAlert(
        user_id=user_id,
        ticker=ticker,
        company_name=q.get("company_name") if "error" not in q else ticker,
        alert_type=body.alert_type,
        target_price=body.target_price,
    )
    db.add(alert)
    await db.flush()
    return alert.to_dict()


@router.patch("/{alert_id}")
async def update_alert(
    alert_id: int,
    body: AlertUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(PriceAlert, alert_id)
    if not alert or alert.user_id != user_id:
        raise HTTPException(404, "Alert not found")
    if body.target_price is not None:
        alert.target_price = body.target_price
        alert.triggered_at = None   # reset trigger on price change
        alert.is_active = True
    if body.is_active is not None:
        alert.is_active = body.is_active
    await db.flush()
    return alert.to_dict()


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(PriceAlert, alert_id)
    if not alert or alert.user_id != user_id:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    return {"deleted": alert_id}


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark a triggered alert as acknowledged (deactivate it)."""
    alert = await db.get(PriceAlert, alert_id)
    if not alert or alert.user_id != user_id:
        raise HTTPException(404, "Alert not found")
    alert.is_active = False
    await db.flush()
    return alert.to_dict()
