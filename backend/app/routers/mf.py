"""Mutual Fund and ETF routes."""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import mf_service

router = APIRouter(prefix="/api", tags=["mf"])
logger = logging.getLogger(__name__)

_EMPTY_HIGHLIGHTS = {"popular": [], "top_gainers": [], "top_losers": [], "most_active": []}


# ── Mutual Funds ──────────────────────────────────────────────────────────────

@router.get("/mf")
async def list_mfs(
    search:   str = Query(""),
    category: str = Query(""),
    page:     int = Query(1, ge=1),
    limit:    int = Query(40, ge=1, le=100),
):
    try:
        return await mf_service.get_mf_list(search=search, category=category, page=page, limit=limit)
    except Exception as e:
        logger.warning("list_mfs failed: %s", e)
        return {"total": 0, "page": page, "limit": limit, "pages": 0, "funds": []}


class ReturnsBatchBody(BaseModel):
    codes: list[int]


@router.post("/mf/returns")
async def mf_returns_batch(body: ReturnsBatchBody):
    if not body.codes:
        raise HTTPException(400, "codes list required")
    try:
        return await mf_service.get_mf_returns_batch(body.codes)
    except Exception as e:
        logger.warning("mf_returns_batch failed: %s", e)
        return {}


@router.get("/mf/highlights")
async def mf_highlights(period: str = Query("1y")):
    try:
        return await mf_service.get_mf_highlights(period)
    except Exception as e:
        logger.warning("mf_highlights failed: %s", e)
        return _EMPTY_HIGHLIGHTS


@router.get("/mf/{scheme_code}/nifty50")
async def mf_nifty50(scheme_code: int, from_date: str = Query(...)):
    try:
        return await mf_service.get_nifty50_chart(from_date)
    except Exception:
        return []


@router.get("/mf/{scheme_code}")
async def mf_detail(scheme_code: int):
    try:
        data = await mf_service.get_mf_detail(scheme_code)
    except Exception as e:
        logger.warning("mf_detail %s failed: %s", scheme_code, e)
        raise HTTPException(503, "MF data temporarily unavailable")
    if not data:
        raise HTTPException(404, "Mutual fund not found")
    return data


@router.get("/mf/{scheme_code}/holdings")
async def mf_holdings(scheme_code: int):
    """Portfolio holdings of a fund, via IndianAPI (best-effort name match —
    absence of a match is normal and returns an empty list, not an error)."""
    try:
        detail = await mf_service.get_mf_detail(scheme_code)
        if not detail or not detail.get("name"):
            return []
        from app.services.indianapi_service import get_mf_holdings as _holdings
        return await _holdings(detail["name"]) or []
    except Exception as e:
        logger.warning("mf_holdings %s failed: %s", scheme_code, e)
        return []


# ── ETFs ──────────────────────────────────────────────────────────────────────

@router.get("/etf")
async def list_etfs():
    try:
        return await mf_service.get_etf_list()
    except Exception as e:
        logger.warning("list_etfs failed: %s", e)
        return []


@router.get("/etf/highlights")
async def etf_highlights():
    try:
        return await mf_service.get_etf_highlights()
    except Exception as e:
        logger.warning("etf_highlights failed: %s", e)
        return {}


@router.get("/etf/{ticker:path}")
async def etf_detail(ticker: str):
    try:
        data = await mf_service.get_etf_detail(ticker)
    except Exception as e:
        logger.warning("etf_detail %s failed: %s", ticker, e)
        raise HTTPException(503, "ETF data temporarily unavailable")
    if not data:
        raise HTTPException(404, "ETF not found")
    return data


@router.get("/etf/{ticker:path}/nifty50")
async def etf_nifty50(ticker: str, from_date: str = Query(...)):
    try:
        return await mf_service.get_nifty50_chart(from_date)
    except Exception:
        return []
