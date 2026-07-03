"""
Circuit breaker for external API calls.

States:
  CLOSED    — normal operation; counting consecutive failures
  OPEN      — fast-failing all calls; waiting for recovery_timeout
  HALF_OPEN — one test call allowed; close on success / reopen on failure

Usage:
    from app.core.circuit_breaker import get_breaker, CircuitOpen

    breaker = get_breaker("indianapi", failure_threshold=5, recovery_timeout=30)

    if not breaker.is_available():
        raise CircuitOpen("indianapi")

    try:
        result = await call_indianapi(...)
        breaker.record_success()
    except Exception:
        breaker.record_failure()
        raise

Or with the decorator:
    @circuit_protected("yfinance", failure_threshold=3, recovery_timeout=60)
    async def fetch_price(ticker: str): ...
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class State(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


_STATE_METRIC = {"closed": 0, "half_open": 1, "open": 2}


@dataclass
class CircuitBreaker:
    name:              str
    failure_threshold: int   = 5     # consecutive failures to trip OPEN
    recovery_timeout:  float = 30.0  # seconds before attempting HALF_OPEN

    _state:           State = field(default=State.CLOSED, init=False, repr=False)
    _failures:        int   = field(default=0,            init=False, repr=False)
    _opened_at:       float = field(default=0.0,          init=False, repr=False)
    _half_open_calls: int   = field(default=0,            init=False, repr=False)
    _total_trips:     int   = field(default=0,            init=False, repr=False)

    @property
    def state(self) -> State:
        self._maybe_recover()
        return self._state

    def _maybe_recover(self) -> None:
        if self._state == State.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                logger.info(
                    "CircuitBreaker[%s]: OPEN → HALF_OPEN (recovery timeout elapsed)", self.name
                )
                self._state           = State.HALF_OPEN
                self._half_open_calls = 0
                self._update_metric()

    def is_available(self) -> bool:
        self._maybe_recover()
        if self._state == State.CLOSED:
            return True
        if self._state == State.HALF_OPEN and self._half_open_calls < 1:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        if self._state == State.HALF_OPEN:
            logger.info(
                "CircuitBreaker[%s]: HALF_OPEN → CLOSED (probe succeeded)", self.name
            )
        self._state    = State.CLOSED
        self._failures = 0
        self._update_metric()

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == State.HALF_OPEN:
            logger.warning(
                "CircuitBreaker[%s]: HALF_OPEN → OPEN (probe failed)", self.name
            )
            self._trip()
            return
        if self._failures >= self.failure_threshold and self._state == State.CLOSED:
            logger.warning(
                "CircuitBreaker[%s]: CLOSED → OPEN (%d consecutive failures)",
                self.name, self._failures,
            )
            self._trip()

    def _trip(self) -> None:
        self._state       = State.OPEN
        self._opened_at   = time.monotonic()
        self._total_trips += 1
        self._update_metric()

    def _update_metric(self) -> None:
        try:
            from app.core.metrics import circuit_breaker_state
            circuit_breaker_state.set(
                _STATE_METRIC.get(self._state.value, 0), service=self.name
            )
        except Exception:
            pass

    def seconds_until_retry(self) -> int:
        if self._state != State.OPEN:
            return 0
        elapsed = time.monotonic() - self._opened_at
        return max(0, int(self.recovery_timeout - elapsed))

    def status(self) -> dict:
        self._maybe_recover()
        return {
            "name":              self.name,
            "state":             self._state.value,
            "failures":          self._failures,
            "total_trips":       self._total_trips,
            "seconds_until_retry": self.seconds_until_retry(),
        }


class CircuitOpen(Exception):
    """Raised when a circuit breaker rejects a call (state == OPEN)."""


# ── Global registry ───────────────────────────────────────────────────────────

_registry: dict[str, CircuitBreaker] = {}


def get_breaker(
    name:              str,
    failure_threshold: int   = 5,
    recovery_timeout:  float = 30.0,
) -> CircuitBreaker:
    if name not in _registry:
        _registry[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _registry[name]


def all_statuses() -> list[dict]:
    return [b.status() for b in _registry.values()]


def circuit_protected(
    service_name:      str,
    failure_threshold: int   = 5,
    recovery_timeout:  float = 30.0,
):
    """
    Async decorator — wraps a coroutine with circuit-breaker protection.

    Raises CircuitOpen immediately if the circuit is tripped, so callers
    can react without waiting for a network timeout.
    """
    def decorator(fn: Callable) -> Callable:
        breaker = get_breaker(service_name, failure_threshold, recovery_timeout)

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not breaker.is_available():
                secs = breaker.seconds_until_retry()
                raise CircuitOpen(
                    f"'{service_name}' circuit OPEN — retry in {secs}s"
                )
            try:
                result = await fn(*args, **kwargs)
                breaker.record_success()
                return result
            except CircuitOpen:
                raise
            except Exception:
                breaker.record_failure()
                raise

        wrapper.__name__ = fn.__name__
        wrapper.__doc__  = fn.__doc__
        return wrapper

    return decorator
