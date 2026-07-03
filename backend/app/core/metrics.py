"""
Lightweight Prometheus-format metrics — no external dependencies.

Exposes a /metrics endpoint in Prometheus text exposition format (v0.0.4).
Counters/histograms are thread-safe (Lock-protected) in-process stores.

Available metrics:
  aegis_http_requests_total          — counter by method/path/status
  aegis_http_request_duration_seconds — histogram by method/path
  aegis_external_api_calls_total      — counter by provider/outcome
  aegis_external_api_duration_seconds — histogram by provider
  aegis_cache_operations_total        — counter by operation/result
  aegis_circuit_breaker_state         — gauge per service (0=closed,1=half_open,2=open)
  aegis_active_requests               — gauge (in-flight count)
  aegis_ai_requests_total             — counter by provider/outcome
"""
from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict, List, Sequence


_lock = Lock()


# ── Metric base types ─────────────────────────────────────────────────────────

class Counter:
    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        self.name   = name
        self.help   = help_text
        self.labels = list(labels)
        self._values: Dict[tuple, float] = defaultdict(float)

    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with _lock:
            self._values[key] += amount

    def expose(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        for key, value in sorted(self._values.items()):
            lines.append(f"{self.name}{_fmt_labels(self.labels, key)} {value:.0f}")
        return "\n".join(lines)


class Gauge:
    def __init__(self, name: str, help_text: str, labels: Sequence[str] = ()):
        self.name   = name
        self.help   = help_text
        self.labels = list(labels)
        self._values: Dict[tuple, float] = defaultdict(float)

    def set(self, value: float, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with _lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with _lock:
            self._values[key] += amount

    def dec(self, amount: float = 1.0, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with _lock:
            self._values[key] -= amount

    def expose(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} gauge"]
        for key, value in sorted(self._values.items()):
            lines.append(f"{self.name}{_fmt_labels(self.labels, key)} {value}")
        return "\n".join(lines)


class Histogram:
    _DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        help_text: str,
        labels: Sequence[str] = (),
        buckets: Sequence[float] | None = None,
    ):
        self.name    = name
        self.help    = help_text
        self.labels  = list(labels)
        self.buckets = sorted(buckets or self._DEFAULT_BUCKETS)
        # per label-key: bucket cumulative counts (len = len(buckets)+1, last is +Inf)
        self._counts: Dict[tuple, List[float]] = defaultdict(
            lambda: [0.0] * (len(self.buckets) + 1)
        )
        self._sum:   Dict[tuple, float] = defaultdict(float)
        self._total: Dict[tuple, float] = defaultdict(float)

    def observe(self, value: float, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with _lock:
            self._sum[key]   += value
            self._total[key] += 1
            for i, b in enumerate(self.buckets):
                if value <= b:
                    self._counts[key][i] += 1
            self._counts[key][-1] += 1  # +Inf bucket always

    def expose(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        for key in sorted(self._total):
            lp  = _fmt_labels_partial(self.labels, key)
            lc  = _fmt_labels(self.labels, key)
            cum = 0.0
            for i, b in enumerate(self.buckets):
                cum += self._counts[key][i]
                bucket_lbl = f'{{{lp}le="{b}"}}' if lp else f'{{le="{b}"}}'
                lines.append(f"{self.name}_bucket{bucket_lbl} {cum:.0f}")
            inf_lbl = f'{{{lp}le="+Inf"}}' if lp else '{le="+Inf"}'
            lines.append(f"{self.name}_bucket{inf_lbl} {self._counts[key][-1]:.0f}")
            lines.append(f"{self.name}_sum{lc} {self._sum[key]:.6f}")
            lines.append(f"{self.name}_count{lc} {self._total[key]:.0f}")
        return "\n".join(lines)


# ── Registry ──────────────────────────────────────────────────────────────────

class _Registry:
    def __init__(self) -> None:
        self._metrics: list = []

    def register(self, m):
        self._metrics.append(m)
        return m

    def expose_all(self) -> str:
        return "\n\n".join(m.expose() for m in self._metrics) + "\n"


registry = _Registry()


# ── Application metrics (module-level singletons) ─────────────────────────────

http_requests_total = registry.register(Counter(
    "aegis_http_requests_total",
    "Total HTTP requests handled",
    labels=["method", "path", "status"],
))

http_request_duration_seconds = registry.register(Histogram(
    "aegis_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labels=["method", "path"],
))

external_api_calls_total = registry.register(Counter(
    "aegis_external_api_calls_total",
    "External API calls by provider and outcome (success|error|circuit_open)",
    labels=["provider", "outcome"],
))

external_api_duration_seconds = registry.register(Histogram(
    "aegis_external_api_duration_seconds",
    "External API call duration in seconds",
    labels=["provider"],
))

cache_operations_total = registry.register(Counter(
    "aegis_cache_operations_total",
    "Cache hit/miss counts",
    labels=["operation", "result"],
))

circuit_breaker_state = registry.register(Gauge(
    "aegis_circuit_breaker_state",
    "Circuit breaker state per service (0=closed, 1=half_open, 2=open)",
    labels=["service"],
))

active_requests = registry.register(Gauge(
    "aegis_active_requests",
    "Number of in-flight HTTP requests",
))

ai_requests_total = registry.register(Counter(
    "aegis_ai_requests_total",
    "AI completion requests by provider and outcome",
    labels=["provider", "outcome"],
))


# ── Label helpers ─────────────────────────────────────────────────────────────

def _fmt_labels(labels: list[str], key: tuple) -> str:
    if not labels:
        return ""
    pairs = ",".join(f'{l}="{v}"' for l, v in zip(labels, key))
    return "{" + pairs + "}"


def _fmt_labels_partial(labels: list[str], key: tuple) -> str:
    """Return label pairs without braces, for building bucket labels."""
    if not labels:
        return ""
    return ",".join(f'{l}="{v}"' for l, v in zip(labels, key)) + ","
