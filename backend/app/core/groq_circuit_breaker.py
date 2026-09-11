"""Circuit breaker for Groq streaming calls (/api/ai/ask-stream).

Modeled on app/services/indianapi_service.py's module-level _blocked_until
pattern. (There used to be a generic CircuitBreaker class in
app/core/circuit_breaker.py; it tripped on CONSECUTIVE failures only, had no
rolling-time-window support and — decisively — no callers anywhere, so it was
deleted rather than force-fitted here.) This module carries the rolling-window
failure list the "3 failures within 60s" spec needs, on top of the same
5-minute OPEN duration IndianAPI's breaker uses.

Tracks failures per-Groq-SERVICE, not per-key: _next_groq_client() in
ai_service.py round-robins GROQ_API_KEY/_2/_3 on every call regardless of
prior success/failure, so a single failed streaming call may have used any
of the N configured keys — attributing failures to individual keys would
need call-time key identity threaded through stream_answer(), for no clear
benefit (a Groq-wide outage and a single bad key both look identical from
here: streaming calls failing).

Module-level state, so it is per-process. The Dockerfile now runs a single
uvicorn worker precisely so that "per-process" and "per-instance" are the same
thing (see backend/Dockerfile); the same limitation applies to
indianapi_service.py's breaker and the SSE hub. If the process count is ever
raised, each worker trips and recovers independently — worst case ~Nx the
intended failure budget, and OPEN only skips the 1.5s peek optimization in
routers/ai.py, never correctness.
"""

from __future__ import annotations

import time

_FAILURE_WINDOW_SECONDS = 60
_FAILURE_THRESHOLD = 3
_OPEN_SECONDS = 300  # 5 min — matches IndianAPI's precedent exactly

_failure_times: list[float] = []
_opened_until: float = 0.0


def record_failure() -> None:
    """Call when the streaming peek (routers/ai.py's asyncio.wait_for(anext(gen), ...))
    raises anything — timeout or an immediate exception from stream_answer()."""
    global _opened_until
    now = time.time()
    _failure_times.append(now)
    cutoff = now - _FAILURE_WINDOW_SECONDS
    while _failure_times and _failure_times[0] < cutoff:
        _failure_times.pop(0)
    if len(_failure_times) >= _FAILURE_THRESHOLD:
        _opened_until = now + _OPEN_SECONDS
        _failure_times.clear()
        _update_metric(open=True)


def record_success() -> None:
    """Call when the peek returns a first chunk. Only a real streaming
    attempt clears an OPEN circuit — a successful non-streaming
    ai_service.answer() waterfall call does NOT count (see module docstring
    reasoning replicated in the caller)."""
    global _opened_until
    _failure_times.clear()
    if _opened_until:
        _opened_until = 0.0
        _update_metric(open=False)


def is_open() -> bool:
    return time.time() < _opened_until


def seconds_until_retry() -> int:
    return max(0, int(_opened_until - time.time()))


def status() -> dict:
    return {
        "name": "groq_stream",
        "state": "open" if is_open() else "closed",
        "failures": len(_failure_times),
        "seconds_until_retry": seconds_until_retry(),
    }


def _update_metric(open: bool) -> None:
    try:
        from app.core.metrics import circuit_breaker_state
        circuit_breaker_state.set(2 if open else 0, service="groq_stream")
    except Exception:
        pass
