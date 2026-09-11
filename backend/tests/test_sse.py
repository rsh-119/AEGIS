"""PriceStreamHub unit tests: subscriber lifecycle and resource cleanup.

Wire format and client-disconnect behaviour need a real socket and live in
test_sse_live.py — httpx's ASGITransport buffers the whole response body, so
it can never drive an open-ended stream.

The hub is in-process, so a leak here is a leak in the only backend process
there is. Every test asserts the hub is empty again afterwards.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.price_stream_service import (
    MAX_STREAMED_TICKERS,
    PriceStreamHub,
    StreamCapacityExceeded,
    price_stream_hub,
)


@pytest.fixture(autouse=True)
def _clean_hub():
    price_stream_hub.shutdown()
    yield
    price_stream_hub.shutdown()


@pytest.fixture
def fake_quote(monkeypatch):
    """Replace the upstream quote fetch; the hub polls the cache, not the API."""
    state = {"price": 100.0, "ts": 1, "calls": 0, "raise_error": False}

    async def _get_quote(ticker: str):
        state["calls"] += 1
        if state["raise_error"]:
            raise RuntimeError("upstream exploded")
        return {"ticker": ticker, "current_price": state["price"],
                "change_pct": 1.0, "volume": 1000, "fetched_at": state["ts"]}

    monkeypatch.setattr("app.services.stock_service.get_quote", _get_quote)
    return state


# ── Lifecycle ─────────────────────────────────────────────────────────────────

async def test_one_poll_loop_per_ticker_regardless_of_subscriber_count(fake_quote):
    hub = PriceStreamHub()
    queues = [await hub.subscribe("TCS.NS") for _ in range(5)]
    assert len(hub._tasks) == 1, "a poll loop was started per subscriber"
    assert len(hub._subscribers["TCS.NS"]) == 5
    for q in queues:
        await hub.unsubscribe("TCS.NS", q)
    hub.shutdown()


async def test_poll_loop_stops_when_the_last_subscriber_leaves(fake_quote):
    hub = PriceStreamHub()
    q = await hub.subscribe("TCS.NS")
    task = hub._tasks["TCS.NS"]
    await hub.unsubscribe("TCS.NS", q)

    assert "TCS.NS" not in hub._tasks
    assert "TCS.NS" not in hub._subscribers
    assert "TCS.NS" not in hub._last
    await asyncio.sleep(0)
    assert task.cancelled() or task.done(), "poll-loop task outlived its subscribers"


async def test_repeated_connect_disconnect_leaves_no_residue(fake_quote):
    hub = PriceStreamHub()
    for _ in range(50):
        q = await hub.subscribe("TCS.NS")
        await hub.unsubscribe("TCS.NS", q)
    assert hub._subscribers == {} and hub._tasks == {} and hub._last == {}


async def test_duplicate_subscribers_are_tracked_independently(fake_quote):
    hub = PriceStreamHub()
    q1 = await hub.subscribe("TCS.NS")
    q2 = await hub.subscribe("TCS.NS")
    assert q1 is not q2
    await hub.unsubscribe("TCS.NS", q1)
    assert "TCS.NS" in hub._tasks, "one client leaving killed the other's stream"
    await hub.unsubscribe("TCS.NS", q2)
    assert "TCS.NS" not in hub._tasks
    hub.shutdown()


async def test_unsubscribe_is_safe_for_an_unknown_queue(fake_quote):
    """A disconnect can arrive for a ticker the hub never tracked (a client
    that dropped before subscribe completed). It must be a no-op, not an error
    — and specifically must not create the ticker as a side effect, which would
    hand any caller a way to spawn poll loops through the disconnect path."""
    hub = PriceStreamHub()
    await hub.unsubscribe("NOPE.NS", asyncio.Queue())   # must not raise

    assert "NOPE.NS" not in hub._subscribers, "unsubscribe created the ticker"
    assert "NOPE.NS" not in hub._tasks, "unsubscribe started a poll loop"
    assert hub._tasks == {}, f"hub gained tasks from a no-op unsubscribe: {hub._tasks}"


async def test_shutdown_cancels_every_loop(fake_quote):
    hub = PriceStreamHub()
    for t in ("A.NS", "B.NS", "C.NS"):
        await hub.subscribe(t)
    tasks = list(hub._tasks.values())
    hub.shutdown()
    await asyncio.sleep(0)
    assert all(t.cancelled() or t.done() for t in tasks)
    assert hub._subscribers == {} and hub._tasks == {}


# ── Backpressure and failure ──────────────────────────────────────────────────

async def test_a_stalled_consumer_drops_ticks_instead_of_growing_unbounded(fake_quote):
    hub = PriceStreamHub()
    q = await hub.subscribe("TCS.NS")
    for i in range(200):
        if not q.full():
            q.put_nowait({"price": i, "ts": i})
    assert q.qsize() <= 8, f"queue grew to {q.qsize()} — no bound on a slow consumer"
    await hub.unsubscribe("TCS.NS", q)


async def test_upstream_failure_does_not_kill_the_poll_loop(fake_quote):
    hub = PriceStreamHub()
    fake_quote["raise_error"] = True
    q = await hub.subscribe("TCS.NS")
    await asyncio.sleep(0.05)
    task = hub._tasks["TCS.NS"]
    assert not task.done(), "one upstream error terminated the shared poll loop"
    await hub.unsubscribe("TCS.NS", q)
    hub.shutdown()


async def test_first_frame_is_served_from_last_known_value(fake_quote):
    """A second subscriber should paint immediately from cached state."""
    hub = PriceStreamHub()
    q1 = await hub.subscribe("TCS.NS")
    hub._last["TCS.NS"] = {"price": 123.0, "change_pct": 1.0, "volume": 5, "ts": 9}
    q2 = await hub.subscribe("TCS.NS")
    assert q2.qsize() == 1
    assert q2.get_nowait()["price"] == 123.0
    for q in (q1, q2):
        await hub.unsubscribe("TCS.NS", q)
    hub.shutdown()


# ── Abuse ─────────────────────────────────────────────────────────────────────

async def test_distinct_ticker_fan_out_is_capped(fake_quote):
    """The endpoint is anonymous and takes an arbitrary ticker string. Each
    distinct value starts its own long-lived task that polls upstream every
    5s for as long as the socket is held open, so without a cap one client
    can pin an arbitrary number of background tasks and upstream fetch loops
    against the metered quota."""
    hub = PriceStreamHub()
    accepted = 0
    rejected = 0
    for i in range(MAX_STREAMED_TICKERS + 50):
        try:
            await hub.subscribe(f"FAKE{i}.NS")
            accepted += 1
        except StreamCapacityExceeded:
            rejected += 1
    count = len(hub._tasks)
    hub.shutdown()

    assert count <= MAX_STREAMED_TICKERS, f"{count} poll loops exceeded the cap"
    assert rejected == 50, f"expected 50 rejections past the cap, got {rejected}"


async def test_capacity_rejection_surfaces_as_503_not_a_broken_stream(client, fake_quote, monkeypatch):
    """The rejection has to happen before the StreamingResponse commits —
    once streaming starts the status code can no longer be changed."""
    async def _full(ticker):
        raise StreamCapacityExceeded(ticker)

    monkeypatch.setattr(price_stream_hub, "subscribe", _full)
    r = await client.get("/api/stocks/TCS.NS/stream")
    assert r.status_code == 503
    # A concrete value isn't asserted: slowapi's header injection rewrites
    # Retry-After to its own window when it is larger. Presence is the
    # contract — the client is told to back off rather than to retry blind.
    assert r.headers.get("Retry-After")
    assert not r.headers["content-type"].startswith("text/event-stream")


async def test_an_already_streaming_ticker_is_still_accepted_at_capacity(fake_quote):
    """The cap counts distinct tickers, not subscribers — a popular ticker
    must not stop accepting viewers just because the hub is full."""
    hub = PriceStreamHub()
    first = await hub.subscribe("TCS.NS")
    for i in range(MAX_STREAMED_TICKERS - 1):
        await hub.subscribe(f"FAKE{i}.NS")
    assert len(hub._tasks) == MAX_STREAMED_TICKERS

    second = await hub.subscribe("TCS.NS")   # must not raise
    assert len(hub._subscribers["TCS.NS"]) == 2
    hub.shutdown()
