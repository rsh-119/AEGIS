"""
stream.py — Real-time price WebSocket + HTTP fallback.

WebSocket endpoint:  /ws/stocks
HTTP fallback:       GET /api/stream/price/{ticker}
Admin stats:         GET /api/stream/status
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.stream_service import connection_mgr, price_cache, exchange_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])


# ── WebSocket ─────────────────────────────────────────────────────────────────
@router.websocket("/ws/stocks")
async def ws_stocks(ws: WebSocket):
    """
    Real-time price WebSocket.

    Protocol:
      Client sends JSON control frames:
        { "action": "subscribe",   "tickers": ["SBIN.NS", "INFY.NS"] }
        { "action": "unsubscribe", "tickers": ["SBIN.NS"] }
        { "action": "ping" }

      Server pushes tick frames:
        { "type": "tick",     "ticker": "SBIN.NS", "price": 834.55,
          "change_pct": -0.42, "volume": 1234567, "ts": 1719392340.123 }
        { "type": "snapshot", "data": { "SBIN.NS": {...}, ... } }
        { "type": "pong" }
        { "type": "error",    "message": "..." }
    """
    await connection_mgr.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                await ws.send_text(json.dumps({"type": "error", "message": "invalid JSON"}))
                continue

            action  = msg.get("action", "")
            tickers = msg.get("tickers", [])

            # Normalise tickers — accept both "SBIN" and "SBIN.NS"
            tickers = [
                t.upper() if t.upper().endswith(".NS") else f"{t.upper()}.NS"
                for t in tickers
                if isinstance(t, str) and t.strip()
            ]

            if action == "subscribe":
                await connection_mgr.subscribe(ws, tickers)
            elif action == "unsubscribe":
                await connection_mgr.unsubscribe(ws, tickers)
            elif action == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            else:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": f"unknown action: {action!r}",
                }))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS error: %s", exc)
    finally:
        await connection_mgr.disconnect(ws)


# ── HTTP fallback ─────────────────────────────────────────────────────────────
@router.get("/api/stream/price/{ticker}")
async def get_latest_price(
    ticker: str = Path(..., description="NSE ticker e.g. SBIN.NS or SBIN"),
):
    """
    Zero-overhead latest-price endpoint backed by the in-memory tick cache.
    Used by clients that cannot maintain a WebSocket (polling fallback).
    Returns 404 if the ticker has never been streamed.
    """
    if not ticker.upper().endswith(".NS"):
        ticker = f"{ticker.upper()}.NS"
    else:
        ticker = ticker.upper()

    tick = price_cache.get(ticker)
    if tick is None:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker} not in stream cache — subscribe via WebSocket first or wait for pre-warm",
        )
    return {"ticker": ticker, **tick}


# ── Batch REST fallback ───────────────────────────────────────────────────────
@router.get("/api/stream/prices")
async def batch_prices(tickers: str = Query(..., description="Comma-separated tickers e.g. RELIANCE,TCS")):
    """
    Batch latest-price endpoint for clients that cannot use WebSocket or SSE.
    Returns only tickers currently in the in-memory stream cache.
    """
    result: dict[str, dict] = {}
    for raw in tickers.split(","):
        t = raw.strip().upper()
        if not t:
            continue
        if not t.endswith(".NS"):
            t = f"{t}.NS"
        tick = price_cache.get(t)
        if tick:
            result[t] = tick
    return result


# ── SSE endpoint (lighter than WS, auto-reconnect, HTTP/1.1 compatible) ──────
@router.get("/api/stream/sse")
async def sse_prices(
    request: Request,
    tickers: str = Query(..., description="Comma-separated tickers"),
):
    """
    Server-Sent Events stream — one-way server push, works behind any HTTP proxy.
    Falls between WebSocket (best) and REST polling (worst) in latency/overhead.
    Sends a delta frame (only changed prices) at most once per second.
    """
    ticker_list: list[str] = []
    for raw in tickers.split(","):
        t = raw.strip().upper()
        if not t:
            continue
        ticker_list.append(t if t.endswith(".NS") else f"{t}.NS")

    async def generate():
        last: dict[str, float] = {}
        # Tell the browser to retry after 3 s on unexpected disconnect
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                break
            updates: dict[str, dict] = {}
            for t in ticker_list:
                tick = price_cache.get(t)
                if not tick or not tick.get("price"):
                    continue
                prev = last.get(t)
                price = tick["price"]
                if prev is None or abs(price - prev) / (prev or 1) >= 0.0001:
                    updates[t] = tick
                    last[t] = price
            if updates:
                yield f"data: {json.dumps(updates, default=str)}\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",   # disable nginx/proxy buffering
            "Connection": "keep-alive",
        },
    )


# ── Status ────────────────────────────────────────────────────────────────────
@router.get("/api/stream/status", include_in_schema=False)
async def stream_status():
    """Quick health-check for the streaming subsystem."""
    return {
        "ws_clients":     len(connection_mgr._subs),
        "active_tickers": sorted(connection_mgr.active_tickers),
        "stream_running": exchange_stream._running,
        "cached_tickers": [
            t for t in [
                "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "SBIN.NS"
            ] if price_cache.get(t) is not None
        ],
    }
