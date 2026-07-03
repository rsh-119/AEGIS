"""/api/portfolio/* — holdings CRUD with live P&L (auth required)."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.database import get_db
from app.models import Holding
from app.schemas import HoldingCreate
from app.services import stock_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
async def list_holdings(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(Holding).where(Holding.user_id == user_id)
        )
    ).scalars().all()
    if not rows:
        return {"holdings": [], "summary": _empty_summary()}

    quotes = await asyncio.gather(*[stock_service.get_quote(h.ticker) for h in rows])

    holdings, invested_total, value_total = [], 0.0, 0.0
    for h, q in zip(rows, quotes):
        price = q.get("current_price") or h.avg_price if "error" not in q else h.avg_price
        invested = h.shares * h.avg_price
        value = h.shares * price
        invested_total += invested
        value_total += value
        holdings.append({
            **h.to_dict(),
            "current_price": round(price, 2),
            "invested":       round(invested, 2),
            "current_value":  round(value, 2),
            "pnl":            round(value - invested, 2),
            "pnl_pct":        round((value - invested) / invested * 100 if invested else 0, 2),
            "sector":         q.get("sector") or h.sector or "Unknown",
            "company_name":   q.get("company_name") or h.company_name or h.ticker,
        })

    return {
        "holdings": holdings,
        "summary": {
            "invested": round(invested_total, 2),
            "value":    round(value_total, 2),
            "pnl":      round(value_total - invested_total, 2),
            "pnl_pct":  round((value_total - invested_total) / invested_total * 100 if invested_total else 0, 2),
            "count":    len(holdings),
        },
    }


@router.post("", status_code=201)
async def add_holding(
    body: HoldingCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ticker = stock_service.normalise_ticker(body.ticker)
    q = await stock_service.get_quote(ticker)
    holding = Holding(
        user_id=user_id,
        ticker=ticker,
        company_name=body.company_name or (q.get("company_name") if "error" not in q else ticker),
        shares=body.shares,
        avg_price=body.avg_price,
        buy_date=body.buy_date,
        sector=body.sector or (q.get("sector") if "error" not in q else None),
        notes=body.notes,
    )
    db.add(holding)
    await db.flush()
    return holding.to_dict()


@router.delete("/{holding_id}")
async def delete_holding(
    holding_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Holding, holding_id)
    if not row or row.user_id != user_id:
        raise HTTPException(404, "Holding not found")
    await db.delete(row)
    return {"deleted": holding_id}


def _empty_summary():
    return {"invested": 0, "value": 0, "pnl": 0, "pnl_pct": 0, "count": 0}
