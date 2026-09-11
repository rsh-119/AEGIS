# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN addgroup --system aegis && adduser --system --ingroup aegis aegis

WORKDIR /app

# Runtime system deps only
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=aegis:aegis . .

USER aegis

EXPOSE 8000

# Graceful shutdown: --timeout-keep-alive gives k8s preStop hook time to drain
#
# NO --proxy-headers / --forwarded-allow-ips. That pair is deliberately absent.
#
# --forwarded-allow-ips "*" makes uvicorn overwrite request.client.host with the
# LEFTMOST X-Forwarded-For entry before the application sees the request. Since
# every conforming proxy APPENDS the peer it saw, the leftmost entry is whatever
# the CLIENT wrote — so that flag replaces the one address a caller cannot forge
# with one they fully control. Rate limits keyed off it were resettable at will:
# 40 login attempts with a rotating header produced zero 429s against a
# 5-per-15-minutes limit.
#
# Counting hops from the RIGHT of the header fixes that only while a proxy is
# genuinely in front. Reach this container directly — as docker-compose.yml's
# published port 8000 allows — and a single self-supplied header entry is both
# the first and the last, so hop counting reads the attacker's value again.
# Confirmed against this image before the peer check below was added.
#
# Client IP for rate limiting is therefore decided entirely in
# app/middleware/rate_limiter.py's client_ip(), which:
#   1. trusts X-Forwarded-For ONLY when the real socket peer is inside
#      TRUSTED_PROXY_IPS (default loopback + RFC1918 — where a reverse proxy,
#      ingress or platform edge connects from), and
#   2. then counts TRUSTED_PROXY_HOPS entries from the RIGHT.
# Both need request.client.host to be the TRUE peer, which is exactly what
# those uvicorn flags destroyed.
#
# If your proxy connects from a public address, add it to TRUSTED_PROXY_IPS
# rather than restoring these flags.
# --no-server-header: uvicorn emits its own `Server: uvicorn` at the transport
# layer, which arrives BEFORE the `Server: Aegis` that SecurityHeadersMiddleware
# sets — so responses carried two Server headers and clients read the first,
# defeating the fingerprint masking that middleware exists for. Suppressing
# uvicorn's leaves exactly one.
#
# --workers 1: deliberate, and a correctness decision rather than a capacity
# one. Three pieces of state in this app are per-PROCESS, not shared:
#
#   • the SSE price-stream hub (services/price_stream_service.py) — one poll
#     loop per ticker PER WORKER, so N workers means N× the calls against
#     IndianAPI's metered monthly quota for the same set of viewers;
#   • the in-process prompt cache (services/ai_service.py) — an N-way split
#     hit rate, so repeated prompts re-bill LLM calls that should have hit;
#   • both circuit breakers (indianapi_service, core/groq_circuit_breaker) —
#     each worker trips and recovers independently, so the effective failure
#     budget against a failing upstream is N× what the threshold says.
#
# This previously ran --workers 2 while every one of those modules documented a
# single-process assumption. Two workers did not make those assumptions true;
# it just made them quietly wrong. Rate limiting and session/refresh state are
# already shared correctly via Redis, so they are not the constraint here.
#
# Raising this is a real change, not a flag flip: move the SSE hub and the
# prompt cache to Redis and make the breakers shared first, then raise it and
# re-measure. Until then, scale with more INSTANCES only if you accept the same
# N× costs above — the trade is identical, and k8s/deployment.yaml's replicas
# carries the same warning.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-keep-alive", "10", \
     "--no-server-header", \
     "--access-log"]
