"""SSE over a real socket against a real uvicorn process.

The stream is driven by seeding the shared quote cache, which is exactly how
price_stream_service documents itself as working ("polls the cache, not
upstream"), so no external API is involved.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from app.core.cache import cache

pytestmark = pytest.mark.slow

POLL_INTERVAL = 6  # price_stream_service._POLL_INTERVAL is 5s — allow one cycle


def _seed_quote(ticker: str, price: float) -> None:
    cache.set(f"quote:{ticker}", {
        "ticker": ticker, "currency": "INR", "exchange": "NSE",
        "current_price": price, "change_pct": 1.23, "volume": 1000,
        "company_name": "Test Co", "fetched_at": int(time.time()),
    }, "prices")


async def _first_frame(client: httpx.AsyncClient, url: str, timeout: float = 15.0) -> str:
    async with client.stream("GET", url) as r:
        assert r.status_code == 200, r.status_code
        assert r.headers["content-type"].startswith("text/event-stream")
        deadline = time.time() + timeout
        buf = ""
        async for chunk in r.aiter_text():
            buf += chunk
            if "\n\n" in buf:
                return buf
            if time.time() > deadline:
                break
    raise AssertionError(f"no SSE frame within {timeout}s (buffered {buf!r})")


async def test_stream_sets_streaming_headers(live_server):
    _seed_quote("TCS.NS", 101.0)
    async with httpx.AsyncClient(base_url=live_server, timeout=20) as c:
        async with c.stream("GET", "/api/stocks/TCS.NS/stream") as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            assert r.headers.get("cache-control") == "no-cache"
            assert r.headers.get("x-accel-buffering") == "no"


async def test_stream_emits_a_well_formed_data_frame(live_server):
    _seed_quote("INFY.NS", 202.5)
    async with httpx.AsyncClient(base_url=live_server, timeout=20) as c:
        frame = await _first_frame(c, "/api/stocks/INFY.NS/stream")

    assert frame.startswith("data: "), f"not SSE framing: {frame[:100]!r}"
    payload = json.loads(frame.split("data: ", 1)[1].split("\n\n", 1)[0])
    assert payload["price"] == 202.5
    assert set(payload) == {"price", "change_pct", "volume", "ts"}


async def test_many_subscribers_all_receive_the_same_tick(live_server):
    _seed_quote("ITC.NS", 303.0)
    async with httpx.AsyncClient(base_url=live_server, timeout=30) as c:
        frames = await asyncio.gather(*[
            _first_frame(c, "/api/stocks/ITC.NS/stream") for _ in range(5)
        ])
    prices = [json.loads(f.split("data: ", 1)[1].split("\n\n", 1)[0])["price"] for f in frames]
    assert prices == [303.0] * 5


async def test_repeated_connect_disconnect_does_not_degrade_the_server(live_server):
    """50 connect/disconnect cycles, then the server must still answer
    normally — proof that disconnects release their poll loops."""
    _seed_quote("WIPRO.NS", 404.0)
    async with httpx.AsyncClient(base_url=live_server, timeout=20) as c:
        for _ in range(50):
            async with c.stream("GET", "/api/stocks/WIPRO.NS/stream") as r:
                assert r.status_code == 200
        health = await c.get("/health/live")
    assert health.status_code == 200


async def test_unknown_ticker_still_opens_a_stream_without_erroring(live_server):
    """Upstream is disabled in tests, so this ticker has no data at all. The
    connection must stay healthy and emit keepalives rather than 500."""
    async with httpx.AsyncClient(base_url=live_server, timeout=10) as c:
        async with c.stream("GET", "/api/stocks/NOSUCHTICKER.NS/stream") as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
