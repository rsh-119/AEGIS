"""Mutual Fund and ETF routes."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import mf_service

router = APIRouter(prefix="/api", tags=["mf"])


# ── Mutual Funds ──────────────────────────────────────────────────────────────

@router.get("/mf")
async def list_mfs(
    search:   str = Query(""),
    category: str = Query(""),
    page:     int = Query(1, ge=1),
    limit:    int = Query(40, ge=1, le=100),
):
    return await mf_service.get_mf_list(search=search, category=category, page=page, limit=limit)


class ReturnsBatchBody(BaseModel):
    codes: list[int]


@router.post("/mf/returns")
async def mf_returns_batch(body: ReturnsBatchBody):
    if not body.codes:
        raise HTTPException(400, "codes list required")
    return await mf_service.get_mf_returns_batch(body.codes)


@router.get("/mf/highlights")
async def mf_highlights(period: str = Query("1y")):
    return await mf_service.get_mf_highlights(period)


@router.get("/mf/{scheme_code}/nifty50")
async def mf_nifty50(scheme_code: int, from_date: str = Query(...)):
    return await mf_service.get_nifty50_chart(from_date)


@router.get("/mf/{scheme_code}")
async def mf_detail(scheme_code: int):
    data = await mf_service.get_mf_detail(scheme_code)
    if not data:
        raise HTTPException(404, "Mutual fund not found")
    return data


# ── ETFs ──────────────────────────────────────────────────────────────────────

@router.get("/etf")
async def list_etfs():
    return await mf_service.get_etf_list()


@router.get("/etf/highlights")
async def etf_highlights():
    return await mf_service.get_etf_highlights()


@router.get("/etf/{ticker:path}")
async def etf_detail(ticker: str):
    data = await mf_service.get_etf_detail(ticker)
    if not data:
        raise HTTPException(404, "ETF not found")
    return data


@router.get("/etf/{ticker:path}/nifty50")
async def etf_nifty50(ticker: str, from_date: str = Query(...)):
    return await mf_service.get_nifty50_chart(from_date)
