"""/api/watchlist/* — watchlist CRUD with live prices (auth required)."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.models import WatchItem
from app.schemas import WatchCreate
from app.services import stock_service

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
async def list_watch(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(WatchItem)
            .where(WatchItem.user_id == user_id)
            .order_by(WatchItem.created_at.desc())
        )
    ).scalars().all()
    if not rows:
        return {"items": []}
    quotes = await asyncio.gather(*[stock_service.get_quote(r.ticker) for r in rows])
    items = []
    for r, q in zip(rows, quotes):
        items.append({
            **r.to_dict(),
            "current_price": q.get("current_price") if "error" not in q else None,
            "company_name":  q.get("company_name") or r.company_name or r.ticker,
            "pct_change":    _intraday_pct(q),
        })
    return {"items": items}


@router.post("", status_code=201)
async def add_watch(
    body: WatchCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ticker = stock_service.normalise_ticker(body.ticker)
    exists = (
        await db.execute(
            select(WatchItem).where(
                WatchItem.ticker == ticker,
                WatchItem.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"{ticker} already on watchlist")
    q = await stock_service.get_quote(ticker)
    item = WatchItem(
        user_id=user_id,
        ticker=ticker,
        company_name=body.company_name or (q.get("company_name") if "error" not in q else ticker),
        target_price=body.target_price,
    )
    db.add(item)
    await db.flush()
    return item.to_dict()


@router.delete("/{item_id}")
async def delete_watch(
    item_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WatchItem, item_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Not found")
    await db.delete(row)
    return {"deleted": item_id}


def _intraday_pct(q: dict):
    price, prev = q.get("current_price"), q.get("previous_close")
    if isinstance(price, (int, float)) and isinstance(prev, (int, float)) and prev:
        return round((price - prev) / prev * 100, 2)
    return None
