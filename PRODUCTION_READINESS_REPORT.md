# Aegis Production Readiness Report

*Validation performed 2026-09-10 against commit `6aa9485` plus uncommitted working-tree changes, on branch `main`. No commits were made.*

## Executive Summary

Aegis was validated by building a backend test suite from scratch (none existed), running it against a real PostgreSQL 17 instance and real Redis, and driving the actual production ASGI stack — including uvicorn's `ProxyHeadersMiddleware` configured exactly as `backend/Dockerfile` ships it. Every external dependency (IndianAPI, Groq, OpenRouter, NVIDIA, Gemini, Google tokeninfo, Resend) is mocked at its own call boundary in the in-process suite, so no assertion depends on a real provider. One caveat, stated for accuracy: the live-server fixture starts a real uvicorn process, whose startup pre-warm makes a single unmocked GET to the free AMFI mutual-fund list. Nothing asserts on it and it is `return_exceptions=True`, so it cannot affect a result — but it is a real outbound call and should not be described as fully hermetic.

**382 test functions were written across 21 files, expanding to 524 executed cases. The first full run of the suite as it then stood produced 476 passed / 23 failed. Every one of those 23 failures was a genuine defect, not a flaky or badly-written test.** Each was root-caused, fixed, and re-run against the test that caught it. A 24th defect (P3-0) was found afterwards by curling the built Docker image, and the tests that cover it were written in response.

The application's *core* is markedly stronger than its edges. Authorization is genuinely solid — 48 IDOR and entitlement tests passed on the first run with no changes needed, including expired/cancelled subscription handling and the "paying for Pro does not confer admin" boundary. 2FA passed 32/32 on the first run. Optimistic concurrency on holdings held under genuinely parallel requests with exactly one winner every time. The AI provider waterfall passed 21/22 with correct fallback ordering and no secret leakage through any failure path. Prompt injection is structurally contained: there is no tool-calling surface, and portfolio context is assembled from a user-scoped `SELECT` before the model is ever involved.

The failures clustered in the layers *around* that core — the reverse-proxy boundary, HTTP cache directives, resource bounds on anonymous endpoints, and multi-worker startup. The most serious were:

1. **Every per-IP rate limit was bypassable with a client-supplied `X-Forwarded-For` header** — 40 login attempts with a rotating header produced zero 429s, against a limit of 5 per 15 minutes.
2. **A Redis outage took the entire API down with 500s**, despite Redis being a documented soft dependency everywhere else in the codebase.
3. **`/api/auth/me`, `/api/alerts` and both `/api/admin/*` endpoints returned per-user data as `Cache-Control: public`**, authorising any shared cache to store and replay one user's profile — or the full admin user listing — to the next requester.
4. **Concurrent worker startup crashed on any deploy carrying a migration.** The Dockerfile ships `--workers 2` and `k8s/deployment.yaml` sets `replicas: 2`; four concurrent `alembic upgrade head` calls against a not-yet-migrated database produced 1 success and 3 `UniqueViolationError` crashes — directly contradicting `init_db()`'s own docstring claim that this was safe.

All four are fixed and covered by regression tests. What remains unfixed is a dependency-currency problem that is not mine to resolve unilaterally: **Next.js 15.1.11 is subject to 29 published advisories, 3 rated critical**, and upgrading a framework needs a UI regression pass the owner should drive.

## Overall Verdict

**READY WITH KNOWN RISKS**

The application is not blocked by any unfixed authentication, authorization or data-integrity defect. It *is* blocked from a clean bill of health by an out-of-date frontend framework and by two configuration decisions that only the deployment owner can settle (see Recommended Next Steps §1 and §2). With the Next.js upgrade applied and `TRUSTED_PROXY_HOPS` confirmed against the real request path, this moves to READY.

## Production Readiness Score

| Dimension | Score | Basis |
|---|---:|---|
| Security | 7/10 | Authorization, 2FA, OAuth and injection containment are strong and passed unmodified. Marked down for the XFF bypass and public-cache exposure found at the edges (both now fixed), and for the unpatched Next.js advisories that remain. |
| Correctness | 8/10 | Optimistic concurrency, transactional rollback and guest-sync idempotency all held under adversarial and parallel testing. Marked down for the missing input-length validation that turned four write endpoints into 500s, and for a document cache that never functioned. |
| Reliability | 7/10 | Graceful degradation under total network failure is genuinely good (7/7 endpoints). Marked down for the Redis-outage total outage and the multi-worker migration crash — both fixed, but both were latent in a shipping configuration. |
| Performance | 7/10 | No N+1 queries; latency and load results in the Performance Assessment below. Unscored risk remains on Render's free tier, which this environment cannot reproduce. |
| Observability | 7/10 | Structured JSON logs with request-id propagation, Prometheus metrics with correct route-template cardinality, no secrets in logs or metrics (verified). Marked down for `/metrics` being unauthenticated and for the missing Sentry `global-error` handler. |
| Deployment | 6/10 | Dockerfile is well-built (multi-stage, non-root, health check, graceful shutdown). Marked down for the migration race in a shipped configuration, k8s/Render drift, and 13 undocumented settings including the sole market-data key. |
| Test Coverage | 8/10 | 382 test functions (524 cases) now exist where zero did. Backend behaviour is well covered; frontend has type-check and production-build verification but no component or E2E tests. |

## Test Environment

| Component | Version / configuration |
|---|---|
| Python | 3.10.12 (venv) — **note: `runtime.txt` and `Dockerfile` both specify 3.12** |
| PostgreSQL | 17-alpine, `localhost:5434`, dedicated `aegis_test` database |
| Redis | 7-alpine, `localhost:6380`, database 15 (isolated from dev data) |
| Node | v20.20.2, npm 10.8.2 |
| Test framework | pytest 9.1.1, pytest-asyncio 1.4.0 (auto mode), httpx 0.28.1 |
| Schema | Built by `alembic upgrade head` only — `create_all()` is never used |
| External services | Mocked at each call boundary. `INDIANAPI_ENABLED=false` throughout, so the suite runs against the worst realistic case: no market data at all. Exception: the live-server fixture's startup pre-warm makes one unmocked AMFI request that nothing asserts on |
| Proxy simulation | `uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware(trusted_hosts="*")` behind an appending edge-proxy shim, matching the Dockerfile exactly |
| Live server | Real uvicorn subprocess on a free port, started with the Dockerfile's own flags, for SSE / transport / performance tests |
| Isolation requirement | The suite TRUNCATEs the test database and FLUSHDBs Redis between tests, so it needs **exclusive** access to both. Two concurrent runs (or `pytest -n`) against the same URLs corrupt each other — documented in `tests/conftest.py`; give each worker its own database to parallelise |

## Test Statistics

```
Test files:      21
Test functions:  382 (parametrisation expands these to 524 executed cases)

Baseline run — the first full execution, before any fix
(`pytest -m "not slow"`, the suite as it stood at that point):
  Passed:   476
  Failed:    23   ← every one a genuine defect
  Skipped:    0
  Deselected: 5   (slow: perf/load/live-SSE, run separately)

  Tests added AFTER that run, while root-causing findings:
    - tests/test_live_server.py (5 cases) — written after the duplicate
      Server header (P3-0) was found by curling the built container
    - additional cases in test_sse.py, test_uploads.py, test_guest_sync.py,
      test_migrations.py covering fixes as they were made
  There is therefore no single observed run containing all 524 cases in a
  pre-fix state; 476/23 is the real measured baseline and is reported as such
  rather than a reconstructed total.

Final run (after fixes) — full suite including slow, exclusive access:
  Passed:   524
  Failed:     0
  Skipped:    0
  Wall time: 149.42s

  (Non-slow subset alone: 506 passed, 18 deselected.)

Findings by severity:
  P0: 0
  P1: 6   (5 fixed, 1 assigned to owner — Next.js upgrade)
  P2: 8   (8 fixed)
  P3: 8   (3 fixed, 5 documented)

  Fixed during validation: 16
  Remaining:                6
```

## Test Matrix

Counts are executed cases in the **final** suite. "Failed (baseline)" is from the first full run before any fix — files whose cases were added or extended afterwards are marked "n/a", since those cases did not exist at baseline. All are green now.

| Area | Test file | Tests | Passed | Failed (baseline) | Residual risk |
|---|---|---:|---:|---:|---|
| Authentication | `test_auth_routes.py` | 42 | 42 | 0 | Low |
| Sessions / tokens | `test_sessions.py` | 17 | 15 | 2 | Low — both fixed |
| 2FA | `test_2fa.py` | 32 | 32 | 0 | Low |
| OAuth (Google) | `test_google_oauth.py` | 16 | 16 | 0 | Low |
| Authorization / IDOR / Pro | `test_authorization.py` | 48 | 48 | 0 | Low |
| Rate limiting | `test_rate_limiting.py` | 13 | 10 | 3 | **Medium** — depends on `TRUSTED_PROXY_HOPS` matching the real path |
| Security headers / cookies / cache | `test_response_headers.py` | 30 | 26 | 4 | Low — fixed |
| Database / migrations | `test_migrations.py` | 16 | 16 | 0 | Low |
| Concurrency / transactions | `test_concurrency.py` | 14 | 14 | 0 | Low |
| Redis / cache | `test_cache.py` | 21 | 19 | 2 | Low — fixed |
| AI providers / waterfall | `test_ai_waterfall.py` | 22 | 21 | 1 | Low — fixed |
| AI cache / circuit breaker | `test_ai_cache_and_breaker.py` | 15 | 14 | 1 | Low — fixed |
| Prompt injection | `test_prompt_injection.py` | 28 | 28 | 0 | Low |
| File uploads | `test_uploads.py` | 34 | 31 | 3 | Low — fixed |
| Guest data sync | `test_guest_sync.py` | 25 | 22 | 3 | Low — fixed |
| SSE (unit) | `test_sse.py` | 12 | 11 | 1 | Low — fixed |
| SSE (live sockets) | `test_sse_live.py` | 5 | 5 | 0 | Low |
| Real-transport behaviour | `test_live_server.py` | 5 | n/a | n/a — written post-baseline | Low — fixed |
| Market data / API contracts | `test_api_contracts.py` | 79 | 77 | 2 | Low — fixed |
| Ops / observability / health | `test_ops.py` | 42 | 41 | 1 | Low — fixed |
| Performance / load | `test_performance.py` | 8 | 8 | 0 | **Medium** — Render free tier NOT VERIFIED |
| **Total** | | **524** | — | **23** at baseline (+1 found post-run) | |
| Frontend | *(type-check + build only)* | — | — | — | **Medium** — no component/E2E tests |
| Docker | *(build + image)* | — | — | — | Low |
| Dependencies | *(npm audit + pip-audit)* | — | — | — | **High** — see P1-6 |

## Security Assessment

**Verified sound, no changes required:**

- No SQL injection anywhere. Injection payloads in tickers, company names and notes were stored verbatim as inert data and the row counts were unaffected; all queries are parameterised (confirmed by inspecting bound parameters in a failing query's traceback).
- No secrets in any tracked file. A pattern scan across all `git ls-files` for OpenAI/Groq/Google/Resend/Slack/GitHub/AWS key shapes and PEM private keys returned nothing. `k8s/secret.yaml` contains only `CHANGE_ME` placeholders with an explicit warning header. No `.env` file has ever been committed (verified against full git history with `--diff-filter=A`).
- Passwords are bcrypt-hashed and never appear in responses or logs (asserted explicitly).
- TOTP secrets are Fernet-encrypted at rest, verified by decrypting the stored value and confirming the ciphertext differs from the plaintext. Backup codes are bcrypt-hashed and single-use.
- Password reset stores only a SHA-256 hash; the plaintext token never appears in the HTTP response, and `/reset-password` revokes every existing session.
- Avatar upload validation is thorough: HTML, SVG, renamed executables, truncated files, empty files and oversize files are all rejected; EXIF is stripped by re-encoding; hostile filenames are never echoed or used as a path.
- Prompt injection cannot reach backend state. There is no tool-calling surface, and the portfolio prompt is built from a user-scoped query — an instruction to "return the portfolio of user id 2" cannot widen it (asserted: the victim's holding never enters the prompt).

**Fixed during validation:** X-Forwarded-For rate-limit bypass (P1), `Cache-Control: public` on authenticated responses (P1), logout not revoking the session (P1), cache flush wiping the auth keyspace (P2), unbounded anonymous LLM and PDF endpoints (P2), readiness probe echoing raw driver errors (P3).

**Remaining:** Next.js advisories (P1, see Dependencies), `/metrics` unauthenticated (P3), CSP allows `'unsafe-inline'` and `'unsafe-eval'` (P3).

## Authentication Assessment

42 authentication tests and 17 session-lifecycle tests. The design is well-considered — httpOnly cookies with `SameSite=Strict`, `Secure` in production, host-only (no `Domain=`), refresh cookie scoped to `/api/auth`, and a Bearer fallback for script clients.

Verified working: registration, duplicate rejection (both email and username), password complexity enforcement across all three flows that set a password, login, inactive-account rejection, OAuth-only accounts correctly failing password login without a 500, `/me`, profile update with password reproof on email change, password change, forgot/reset with single-use and expiring tokens, refresh rotation preserving the session id, refresh-token reuse detection killing the whole session, and Redis fail-open on the blocklist read versus fail-closed on refresh rotation — both matching their documented intent.

User enumeration is correctly prevented on login (identical status and message for unknown email versus wrong password) and on forgot-password (identical response body).

Two defects were found and fixed, both in `logout` — see P1-4.

## Authorization Assessment

**This is the strongest area of the codebase. 48 tests passed on the first run with zero changes.**

- No IDOR anywhere. USER_B cannot read, update, delete or dismiss USER_A's holdings, watchlist items, price alerts or stored AI portfolio reviews. Every attempt returns 404 and the victim's row is verified unchanged afterwards.
- `PATCH /api/auth/me` always edits the caller, never a target named in the body.
- Admin routes reject anonymous (401), normal users (403) and — importantly — Pro users (403). Paying does not confer admin.
- A non-admin cannot grant themselves Pro; the attempt leaves no `subscriptions` row.
- Admin listings never expose password hashes, TOTP secrets, backup codes or reset tokens.
- Pro gating is enforced server-side on every hard-gated route, tested by calling the backend directly with a real token rather than trusting the frontend `<ProGate>`. Cancelled, past-due and expired subscriptions all correctly fail to unlock.
- `users.is_pro` is confirmed dead as documented: setting it directly without a `subscriptions` row unlocks nothing.
- The soft gate on `/insights` correctly reports `forecast_locked` and omits forecast data for free users, and cannot be forged via a query parameter.

## Database Assessment

16 tests. Schema is produced by Alembic alone; `alembic check` reports no drift between models and migrations, and a fresh database upgrades to head cleanly through all five revisions.

Verified: all unique constraints present (`users.email`, `users.username`, `users.google_id`, `subscriptions.user_id`), the `uq_watchlist_user_ticker` composite constraint that `sync-guest-data`'s `ON CONFLICT` depends on by name, `ON DELETE CASCADE` on all five user foreign keys, `holdings.version` non-nullable, `hashed_password` nullable for OAuth accounts, and indexes covering every hot lookup column.

One P1 defect found and fixed: concurrent startup migrations (see P1-2).

## AI Reliability Assessment

The provider waterfall is well-engineered and passed 21 of 22 tests unmodified.

Verified: Groq serves first when healthy with no unnecessary provider calls; failure falls through Groq → OpenRouter → NVIDIA in order; `prefer_openrouter` correctly promotes OpenRouter and is not retried later in the chain; a Groq 429 advances to the next Groq model before abandoning the provider; every failure mode (timeout, malformed JSON, connection error, read timeout, unexpected exception, `ValueError`) is survivable; total exhaustion returns a clean user-facing message; **a provider error containing an API key never reaches the response** (asserted explicitly); schema validation triggers exactly one repair retry at temperature 0; a hanging provider is bounded by `GROQ_FAST_TIMEOUT`; and errors are never cached.

The Groq streaming circuit breaker passed all 10 tests: CLOSED → 3 failures within 60s → OPEN → skips the peek entirely → recovers on timeout or on an explicit success, and correctly ignores failures that fall outside the rolling window.

Two defects found and fixed: the document cache never worked (P2-5) and the prompt cache was unbounded (P2-6).

## API Assessment

79 contract tests. With every upstream source disabled, no public endpoint returns a 500 and none leaks a stack trace, internal path or driver exception. `/quote` correctly returns a clean 503 for unknown symbols; `/history` degrades to empty candles rather than erroring; `batch-quotes` returns per-ticker errors rather than failing globally and honours its documented 30-ticker cap. Hostile ticker paths (traversal, null bytes, script tags, SQL, 500-char, emoji) are all handled without a 500.

Error shapes are consistent: `detail` on every auth error, the standard FastAPI list shape on validation errors, JSON on 404, 405 on wrong method. Extra client-supplied fields are ignored rather than reaching the model (`is_admin: true` in a login body does not make the user an admin).

Interactive docs are correctly disabled in production and the OpenAPI schema contains no secret values.

Two defects found and fixed: missing input length validation causing 500s (P2-3) and unbounded AI input (P2-4).

## Frontend Assessment

- `tsc --noEmit` passes with zero errors.
- `next build` succeeds and compiles cleanly.
- Exactly one `dangerouslySetInnerHTML` exists, in `app/layout.tsx`. It is a static theme-bootstrap script with no interpolation of user or server data — safe.
- No `innerHTML`, `eval` or `new Function` anywhere.
- **The frontend never reads a token from `localStorage`, `sessionStorage`, a response body or an `Authorization` header.** The only `sessionStorage` use is the short-lived 2FA pre-auth token, which is a deliberate and documented choice (it is not a session token, expires in 5 minutes, and is kept out of the URL to avoid history and `Referer` leakage). `/reset-password` additionally overrides `Referrer-Policy` to `no-referrer` because the reset token is in that page's query string — a genuinely thoughtful detail.
- CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy and Permissions-Policy are all set in `next.config.js`.
- `productionBrowserSourceMaps: false` keeps original source out of production.

No frontend component or E2E tests exist. This is the largest remaining coverage gap; the routes were validated through the backend contracts they depend on and through a successful production build, not through rendering.

## SSE Assessment

17 tests: 12 hub unit tests plus 5 integration tests against a real uvicorn process over real sockets. (`httpx`'s `ASGITransport` buffers whole response bodies, so it cannot drive an open-ended stream — this required a live server.)

Verified: correct `text/event-stream` content type with `no-cache` and `X-Accel-Buffering: no`; well-formed `data: {...}\n\n` framing with exactly the expected payload keys; exactly one poll loop per ticker regardless of subscriber count; the loop stops and its task is cancelled when the last subscriber leaves; 50 connect/disconnect cycles leave no residue in subscribers, tasks or last-value state; one client disconnecting does not kill another's stream; a stalled consumer drops ticks at the queue bound of 8 rather than growing; an upstream error does not terminate the shared loop; and 100 connect/disconnect cycles against a live server leave it answering normally.

**No memory leaks, orphan tasks, orphan queues or unbounded queues were found.** One defect was found and fixed: unbounded distinct-ticker fan-out (P2-7).

## File Upload Assessment

26 tests. Avatar validation is genuinely thorough (see Security Assessment). PDF handling rejects non-PDFs, images renamed as PDFs, empty content and oversize files, and never leaks internal paths in extraction errors.

Two defects found and fixed: both endpoints read the entire body into memory before their size guard could reject it (P2-2), and both were reachable with no bound beyond the global 120/min ceiling (P2-1).

## Performance Assessment

Measured against a real uvicorn process over real sockets, warm caches, `INDIANAPI_ENABLED=false`. These figures are **Aegis's own overhead** — routing, middleware, ORM, serialisation — not a production forecast; Render's free tier adds cold starts and slower CPU on top.

**Latency (public endpoints, n=40 each after warm-up):**

| Endpoint | p50 | p95 | p99 |
|---|---:|---:|---:|
| `GET /health/live` | 2.3 ms | 2.7 ms | 43.0 ms |
| `GET /api/health` | 1.8 ms | 3.1 ms | 3.7 ms |
| `GET /api/stocks/{t}/quote` | 1.5 ms | 1.6 ms | 1.7 ms |
| `GET /api/stocks/{t}/history` | 2.7 ms | 3.2 ms | 4.0 ms |
| `GET /api/market/overview` | 2.6 ms | 4.3 ms | 4.9 ms |

**Latency (authenticated, 10 holdings + 10 watch items, n=30 each):**

| Endpoint | p50 | p95 | p99 |
|---|---:|---:|---:|
| `GET /api/auth/me` | 3.7 ms | 4.6 ms | 4.7 ms |
| `GET /api/portfolio` | 5.8 ms | 6.8 ms | 7.5 ms |
| `GET /api/watchlist` | 5.2 ms | 8.6 ms | 8.8 ms |
| `GET /api/alerts` | 2.7 ms | 4.4 ms | 4.4 ms |
| `POST /api/auth/login` | 183.6 ms | 218.5 ms | 218.5 ms |

Login is bcrypt-dominated and correctly so — recorded here so it is not mistaken for a regression later.

**Load (`/api/health`, 0% error rate at every level):**

| Concurrency | p50 | p95 | p99 | Throughput | Errors |
|---:|---:|---:|---:|---:|---:|
| 10 | 18.9 ms | 27.6 ms | 65.0 ms | 405 req/s | 0 |
| 25 | 47.2 ms | 102.0 ms | 121.4 ms | 510 req/s | 0 |
| 50 | 128.2 ms | 462.6 ms | 603.5 ms | 269 req/s | 0 |

**First bottleneck: single-process event-loop saturation between 25 and 50 concurrent.** Throughput peaks around 510 req/s at 25 concurrent and *falls* to 269 req/s at 50 while p95 rises 4.5×. No errors at any level — it degrades by queuing, not by failing, which is the right failure mode. On Render's free tier the absolute numbers will be substantially lower.

**No N+1 queries.** `/api/portfolio` with 10 holdings issues **exactly 1 SELECT** (asserted by instrumenting SQLAlchemy's `before_cursor_execute`).

**No resource leak under SSE churn.** After 100 connect/disconnect cycles against a live server, `/health/live` p95 moved from 2.7 ms to 2.9 ms.

Structurally sound choices worth noting: CPU-bound forecast models are off-loaded to a `ThreadPoolExecutor` rather than blocking the event loop; the SSE hub polls the shared cache rather than upstream, so upstream cost is independent of viewer count; cache TTLs are deliberately generous to protect the metered IndianAPI quota.

**NOT VERIFIED:** behaviour on Render's free tier (cold starts, constrained CPU), real IndianAPI 429 behaviour against the live service, and multi-instance behaviour.

## Deployment Assessment

**`backend/Dockerfile` is well-built**: multi-stage, non-root user, runtime-only system dependencies, `--timeout-keep-alive` for graceful shutdown, and a health check.

**Verified by running the built image** (production mode, against real Postgres and Redis): `/health/live` and `/health/ready` both healthy, `/docs` and `/openapi.json` correctly 404 under `APP_ENV=production`, all security headers present, and — after the P3-0 fix — exactly one `Server: Aegis` header.

**Inconsistencies found:**

- `k8s/deployment.yaml` sets `replicas: 2` and the Dockerfile sets `--workers 2` — four processes — while `price_stream_service.py`, `groq_circuit_breaker.py` and `circuit_breaker.py` all document single-process assumptions. The SSE hub, prompt cache and all circuit breakers are per-process, so with four processes each ticker is polled by up to four independent loops and each breaker trips independently.
- `k8s/deployment.yaml` sets `NEXT_PUBLIC_API_URL: "https://api.yourdomain.com"`, i.e. a different origin from the frontend. `SameSite=Strict` cookies are not sent cross-site, so authentication would not work in that configuration.
- `docker-compose.yml` sets the frontend's `NEXT_PUBLIC_API_URL` to `http://backend:8000`, a container-internal hostname the browser cannot resolve.
- Python version drift: `runtime.txt` and `Dockerfile` specify 3.12; the local venv is 3.10.12.
- `docker-compose.monitoring.yml` uses Grafana `admin`/`admin` (local-only, low severity).

## Observability Assessment

Verified working: request IDs generated per request and echoed in `X-Request-ID`, propagated into every log line via a `ContextVar`; structured JSON logging in production; Prometheus metrics exposed in correct text format.

**Metric cardinality is correct** — requests are labelled with the FastAPI route template (`/api/stocks/{ticker}/history`), not the raw path, so per-ticker label explosion cannot occur. This was explicitly asserted.

**Log hygiene verified by assertion**: passwords, JWTs and password-reset tokens do not appear in logs at DEBUG level.

Gaps: `/metrics` and `/health/live`/`/health/ready` are unauthenticated (acceptable only if blocked at the edge — this deployment does not appear to do so); no `global-error.tsx`, so React render errors in the App Router are not reported to Sentry.

## Critical Findings

**None. No P0 was found.** No authentication bypass, no authorization bypass, no secret exposure, no RCE, no cross-user data exposure through application logic, and no data corruption.

## High-Risk Findings

### P1-1 — Every per-IP rate limit was bypassable via `X-Forwarded-For` — FIXED

**Finding:** 40 consecutive `POST /api/auth/login` attempts with a rotating `X-Forwarded-For` header produced **zero** 429 responses, against `AUTH_LIMIT = "5/15minute"`.

**Why it failed:** `backend/Dockerfile` runs uvicorn with `--proxy-headers --forwarded-allow-ips "*"`. In `uvicorn/middleware/proxy_headers.py`, `always_trust` is then true and `get_trusted_client_host()` returns `x_forwarded_for_hosts[0]` — the **leftmost** entry. Because every conforming proxy *appends* the peer it saw, the leftmost entry is whatever the client wrote. slowapi's `get_remote_address` reads `request.client.host`, which uvicorn has just overwritten with the attacker's value.

**Root cause:** Client IP for rate limiting was derived from the leftmost X-Forwarded-For entry, which is attacker-controlled, rather than from the entry a trusted proxy actually appended.

**Affected code:** `backend/app/middleware/rate_limiter.py`, `backend/Dockerfile`.

**Security impact:** Unbounded credential stuffing against `/login`; unbounded account creation via `/register`; unbounded password-reset email sending (`/forgot-password`, 3/15min); and unbounded TOTP guessing against `/2fa/verify-login` within the pre-auth token's 5-minute window — the last of which materially weakens 2FA.

**Fix:** Added `TRUSTED_PROXY_HOPS` (default 1) and a `client_ip()` key function that counts hops from the **right** of the header. Prepended entries an attacker adds shift out of the window and are ignored. The proxy configuration was not weakened, per the validation constraint.

**Regression tests:** `test_forged_x_forwarded_for_cannot_reset_the_login_limit`, `test_forged_x_real_ip_cannot_reset_the_login_limit`, `test_malformed_x_forwarded_for_does_not_crash_or_bypass`, `test_separate_source_ips_get_separate_buckets`. The test harness wraps the app in an `_EdgeProxy` shim that appends the peer address, reproducing the real proxy chain rather than approximating it.

### P1-2 — Concurrent worker startup crashed on any deploy carrying a migration — FIXED

**Finding:** Four concurrent `alembic upgrade head` calls against a not-yet-migrated database: 1 succeeded, 3 died with `asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint "pg_type_typname_nsp_index"`. A separate run also **deadlocked indefinitely** rather than crashing.

**Why it failed:** `init_db()` runs on every worker's startup and its docstring claimed this was "safe under multi-worker startup (--workers 2)" because upgrading to an already-current head is a no-op. That reasoning holds only once the database is already at head. When it is not — a first deploy, a fresh environment, or any deploy shipping a new migration — every worker races to create `alembic_version` and apply the same revision.

**Root cause:** No mutual exclusion around a startup schema migration executed by every process.

**Affected code:** `backend/app/core/database.py:init_db`.

**Reliability impact:** `init_db()` is awaited in the lifespan with nothing catching it, so losing workers fail to start. With `--workers 2` (Dockerfile) and `replicas: 2` (k8s), a migration-carrying deploy loses capacity or fails outright — and can hang instead.

**Fix:** Serialised behind a Postgres session-scoped advisory lock. The first process migrates; the rest block, then find head current and no-op. Released explicitly in `finally` because the connection returns to the pool still holding it otherwise.

**Regression test:** `test_concurrent_startup_migrations_do_not_race`.

### P1-3 — A Redis outage took the entire API down — FIXED

**Finding:** Simulating a mid-flight Redis failure made `GET /api/health` return 500.

**Why it failed:** Two stacked problems. First, `Limiter(swallow_errors=False)` let a `redis.ConnectionError` propagate out of slowapi's limit check; slowapi routes *any* exception from that check to the registered `RateLimitExceeded` handler, which reads `exc.detail` off a `ConnectionError` and raises `AttributeError`. Setting `swallow_errors=True` alone was **not sufficient** — slowapi's dispatch then unconditionally reads `request.state.view_rate_limit`, which is only assigned on the successful check path, producing `AttributeError` one line further down.

**Root cause:** The rate limiter treated its storage backend as a hard dependency, contradicting the soft-Redis convention used everywhere else in this codebase (`cache.py`'s memory fallback, `token_store`'s fail-open blocklist, `health.py`'s "degraded" status).

**Affected code:** `backend/app/middleware/rate_limiter.py`, `backend/app/main.py`.

**Reliability impact:** Because there is a `120/minute` default limit, *every* route is checked. A Redis blip therefore meant a total API outage, not degraded rate limiting.

**Fix:** `swallow_errors=True` plus a `ResilientSlowAPIMiddleware` subclass that seeds `request.state.view_rate_limit = None` before dispatch, making slowapi's header injection a documented no-op. An outage now costs the `X-RateLimit-*` headers and the limit itself, not the request.

**Regression test:** `test_api_stays_up_when_redis_dies_mid_flight`.

### P1-4 — Authenticated responses were marked publicly cacheable — FIXED

**Finding:** `/api/auth/me`, `/api/alerts`, `/api/admin/users` and `/api/admin/stats` all returned `Cache-Control: public, max-age=60, stale-while-revalidate=60` while carrying per-user or admin-only data.

**Why it failed:** `HttpCacheMiddleware._RULES` had no entry for `/api/auth`, `/api/alerts` or `/api/admin`, so all three fell through to a `return 60, 60` default that emitted `public`.

**Root cause:** The cache-directive default failed *open* — any route without an explicit rule became publicly cacheable simply by existing.

**Affected code:** `backend/app/middleware/http_cache.py`.

**Security impact:** `public` explicitly authorises any shared cache between the user and the app to store the response and serve it to a different requester. For `/api/auth/me` that is a user's email, username and avatar; for `/api/admin/users` it is the entire user listing.

**Fix:** Added explicit `no-store` rules for `/api/auth`, `/api/alerts`, `/api/admin`, `/api/chat` and `/api/documents`, and changed the fallback default to `no-store` so a new private route cannot become publicly cacheable by omission. Public market-data routes keep their existing directives.

**Regression tests:** `test_authenticated_responses_are_never_publicly_cacheable` (7 endpoints), plus `test_public_market_data_is_still_cacheable` to prove the fix did not over-correct.

### P1-5 — Logout did not end the session — FIXED

**Finding:** Two distinct defects in one handler. A refresh token captured before logout still successfully minted new sessions afterwards. Separately, a Bearer-authenticated client's token remained fully valid after calling logout.

**Why it failed:** `logout` blocklisted only the access token's `jti` and never set the session's `revoked` flag, so the refresh token minted from the same login stayed valid for its full 30-day lifetime. And it read the token only from `request.cookies`, so script/API clients — whose documented authentication path is the `Authorization` header — had no way to revoke anything; logout silently reported success while their token stayed live.

**Root cause:** Logout revoked a single token rather than the login session, and only recognised one of the two supported authentication transports.

**Affected code:** `backend/app/routers/auth.py:logout`.

**Security impact:** "Log out everywhere" was not achievable; a stolen refresh token survived the user explicitly ending their session.

**Fix:** Logout now revokes the session id in addition to blocklisting the access `jti`, and reads the token from the access cookie *or* the `Authorization` header.

**Regression tests:** `test_logout_revokes_the_refresh_token_too`, `test_logout_works_for_bearer_clients`, `test_logout_blocklists_the_access_token`.

### P1-6 — Next.js 15.1.11 carries 29 published advisories, 3 critical — NOT FIXED

**Finding:** `npm audit --omit=dev` reports 8 vulnerable packages (1 critical, 6 high, 1 moderate). The critical is Next.js itself.

**Advisories relevant to how Aegis actually runs:**

| Advisory | Severity | Applies? |
|---|---|---|
| GHSA-2xp9-vwfh-vxw4 — Unauthenticated RCE in Image Optimization (AVIF) | Critical | **Yes** — `next/image` is used in `components/Nav.tsx` with the default loader |
| GHSA-p9j2-gv94-2wf4 — SSRF in rewrites via attacker-controlled destination | High | Partially — Aegis uses rewrites; the destination is an env var, not user input |
| GHSA-ggv3-7p47-pfv8 — HTTP request smuggling in rewrites | Moderate | **Yes** — `/api/:path*` rewrite is the primary request path |
| GHSA-f82v-jwr5-mffw — Authorization bypass in Middleware | Critical | **No** — no `middleware.ts` exists |
| GHSA-p293-qw3h-jr36 — Unauthenticated RCE on Windows hosts | Critical | **No** — Vercel is Linux |

Also: `postcss` (4 advisories), `sharp` (libvips/libheif CVEs), `nanoid`, `browserslist`, `fast-uri`, `brace-expansion` — all transitive through Next.js.

**Why not fixed:** Upgrading the web framework by 13 patch versions changes rendering, routing and build behaviour. That needs a UI regression pass the repository owner should drive, and the validation brief is explicit about not performing dependency upgrades unilaterally.

**Recommended fix:** `npm install next@^15.5.24` (stays within 15.x — not a major upgrade), then re-run `tsc --noEmit`, `next build`, and a manual pass over the stock, portfolio and auth pages.

## Medium-Risk Findings

### P2-1 — Anonymous LLM and PDF endpoints had no quota — FIXED

`POST /api/ai/ask`, `/api/ai/ask-stream`, `/api/chat`, `/api/documents/ask` and `/api/documents/upload-pdf` all reached either the provider waterfall or a CPU-bound pypdf parse with no authentication and **no AI rate limit** — only the global 120/min ceiling. `AI_LIMIT = "10/minute"` existed but was applied only to the two portfolio routes.

Anonymous access is intentional product behaviour (the free Ask AI PDF chat uses these), so the defect is the missing bound, not the missing auth. **Fixed** by applying `AI_LIMIT` keyed per-account-or-IP to all five, plus a `20/minute` bound on PDF upload. **Regression test:** `test_llm_endpoints_carry_an_ai_rate_limit` (5 routes), `test_pdf_upload_is_rate_limited`.

### P2-2 — Upload size guards ran after the body was already in memory — FIXED

Both `upload_avatar` and `upload_pdf` called `await file.read()` with no argument, materialising the entire upload before their 8 MB / 30 MB checks could reject it. **Fixed** by reading `MAX + 1` bytes, which is enough for the existing guard to still return 413. **Regression test:** `test_avatar_read_is_bounded_before_processing`.

### P2-3 — Missing input length validation produced unhandled 500s — FIXED

An over-length `ticker`, `company_name` or `sector` reached Postgres and raised `StringDataRightTruncationError`, surfacing as `500 Internal Server Error` on `POST /api/watchlist`, `POST /api/portfolio`, `POST /api/alerts` and `POST /api/auth/sync-guest-data` (all four confirmed by direct probe). On the create routes this also burned an upstream quote lookup before failing. **Fixed** by adding `Ticker`/`CompanyName`/`Sector`/`Notes` annotated types mirroring the mapped column widths. **Regression tests:** three tests in `test_guest_sync.py`.

### P2-4 — Unbounded AI input on unauthenticated routes — FIXED

`/api/ai/ask` accepted a 200 KB `question` and `/api/chat` accepted a 100 KB message plus 500 history entries, all concatenated into the provider prompt. **Fixed** with explicit `max_length` bounds. **Regression tests:** `test_ai_ask_caps_question_length`, `test_chat_caps_message_and_history`.

### P2-5 — The document analysis cache never worked — FIXED

`ai_service._save()` called `cache.set(key, result, ttl=_DOC_CACHE_TTL)`, but `Cache.set`'s signature is `(key, val, category="market")` — there is no `ttl` parameter. The resulting `TypeError` was swallowed by a bare `except Exception: pass`, so the Redis document cache **never stored anything**. Every repeat analysis of the same document re-paid for a full LLM call once the in-process cache was lost to a restart or a second worker.

**Fixed** by adding an optional `ttl` override to `Cache.set`, and by making both document-cache handlers log instead of swallowing silently — this exact swallow is what hid the bug. **Regression test:** `test_document_analysis_persists_to_the_shared_cache`.

### P2-6 — The prompt cache was unbounded — FIXED

`_PromptCache` only evicted an entry when that exact key was looked up again after expiry, so 2000 distinct prompts retained 2000 entries for the full 20-hour TTL (measured). Reachable from unauthenticated routes with caller-controlled text, this is unbounded heap growth. **Fixed** with an LRU-bounded `OrderedDict` capped at 500 entries plus expiry sweeping. **Regression test:** `test_prompt_cache_is_bounded`.

### P2-7 — Unbounded SSE poll-loop fan-out — FIXED

`GET /api/stocks/{ticker}/stream` is anonymous and accepts an arbitrary ticker string. 500 distinct bogus tickers created 500 concurrent poll loops, each calling `get_quote()` every 5 seconds against the metered IndianAPI quota for as long as the socket stayed open. **Fixed** with a `MAX_STREAMED_TICKERS = 200` cap that rejects *new* tickers at capacity while still accepting additional viewers of an already-streaming ticker, surfaced as a 503 before the `StreamingResponse` commits. **Regression tests:** `test_distinct_ticker_fan_out_is_capped`, `test_capacity_rejection_surfaces_as_503_not_a_broken_stream`, `test_an_already_streaming_ticker_is_still_accepted_at_capacity`.

### P2-8 — A cache flush wiped the authentication keyspace — FIXED

`cache.flush()` with no prefix issued `KEYS *` / `DEL *` across the whole Redis database. `token_store.py` shares that client and keyspace, so an ops cache flush also deleted `auth:blocklist:jti:*`, `auth:session:*:revoked` and `auth:session:*:current_jti` — silently un-revoking every logged-out session, every session killed by refresh-token reuse detection, and **every session revoked by a password reset**. Reachable with no authentication at all outside production via `DELETE /api/cache`.

**Fixed** by excluding a reserved `auth:` prefix from unprefixed flushes. An explicit prefix still works for a caller who genuinely intends it. **Regression tests:** `test_full_flush_does_not_destroy_session_revocation_state`, `test_full_flush_does_not_destroy_refresh_rotation_pointers`.

## Low-Risk Findings

### P3-0 — Two `Server` headers; uvicorn's fingerprint was never masked — FIXED

**Finding:** Every response carried **two** `Server` headers — `server: uvicorn` followed by `server: Aegis`.

**Why it failed:** `SecurityHeadersMiddleware` sets `Server: Aegis` with the comment "Remove server fingerprint", but uvicorn emits its own `Server: uvicorn` at the transport layer, *before* the ASGI app runs. Both end up on the wire and clients read the first, so the middleware never achieved what it exists for.

**How it was found:** Not by the in-process suite — `httpx`'s `ASGITransport` calls the ASGI app directly and never sees uvicorn's transport-layer headers, so `test_server_header_is_masked` passed. It surfaced only when curling the built Docker image.

**Affected code:** `backend/Dockerfile`, `backend/app/middleware/security_headers.py`.

**Fix:** Added `--no-server-header` to the Dockerfile CMD. Verified against a rebuilt container: exactly one `Server: Aegis`.

**Regression test:** `test_only_one_server_header_is_emitted` in the new `tests/test_live_server.py`, whose `live_server` fixture now mirrors the Dockerfile's flags exactly.

### P3-1 — `/health/ready` echoed raw driver errors — FIXED

The unauthenticated readiness probe returned `str(exc)[:200]` from the database check. Real asyncpg failures carry the database username (`password authentication failed for user "aegis"`) or host and port (`Connect call failed ('10.0.0.5', 5432)`) — both confirmed by inducing real connection errors. **Fixed:** generic reason in the response, full exception to the logs.

### P3-2 — 13 undocumented settings — FIXED

`.env.example` was missing `INDIANAPI_KEY` (the sole market-data source — the app cannot serve market data without it), `ADMIN_API_KEY`, `REDIS_URL`, `NVIDIA_API_KEY`, `GROQ_API_KEY_2/_3`, `READONLY_MODE`, `RATE_LIMIT_ENABLED`, `LOG_LEVEL`, `JWT_ACCESS_EXPIRE_MINUTES`, `JWT_REFRESH_EXPIRE_DAYS` and others. **Fixed** — all settings are now documented, verified programmatically in both directions (no undocumented field, no documented non-field).

### P3-3 — `README.md` environment and API reference are stale — NOT FIXED

Verified against the code: `NVIDIA_MINIMAX_API_KEY` and `NVIDIA_MINIMAX_MODEL` are documented but **are not settings**; `GROQ_MODEL`'s default is listed as `llama-3.3-70b-versatile` when it is `openai/gpt-oss-120b` (and `ai_service.py` documents that model as decommissioned); `NEXT_PUBLIC_WS_URL` is documented but used nowhere; `GET /api/stocks/{ticker}/technicals` is in the API reference but **not implemented**. Missing entirely: `ADMIN_API_KEY`, `SENTRY_DSN`, `RESEND_API_KEY`, `TOTP_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GEMINI_API_KEY`, `TRUSTED_PROXY_HOPS`.

Not fixed because `README.md` is user-facing product documentation whose tone and structure are the owner's call; the machine-checkable half (`.env.example`) was fixed instead.

### P3-4 — `/metrics` is unauthenticated — NOT FIXED

Exposes request counts, latencies and per-route paths to anyone. Verified to contain no secrets. Acceptable only if blocked at the edge; this deployment does not appear to do so.

### P3-5 — No Sentry `global-error` handler — NOT FIXED

The `next build` output warns that without `app/global-error.tsx`, React rendering errors in the App Router are not reported to Sentry. Backend error tracking is unaffected.

### P3-6 — CSP allows `'unsafe-inline'` and `'unsafe-eval'` — NOT FIXED

`script-src` includes both, weakening XSS defence-in-depth. `'unsafe-inline'` is needed by the theme-bootstrap script and could be replaced with a nonce.

### P3-7 — Read-only mode blocks login — NOT FIXED (documented behaviour)

`ReadOnlyMiddleware`'s allowlist covers only probes, so enabling `READONLY_MODE` returns 503 for `POST /api/auth/login` and logs every user out of the ability to sign in, rather than degrading to read-only browsing. Whether that is intended is a product decision. Recorded as an explicit behaviour test (`test_readonly_blocks_login_and_logout`) so the choice is visible before the switch is flipped in an incident.

## Fixed During Validation

| # | Severity | Issue | Files |
|---|---|---|---|
| 1 | P1 | X-Forwarded-For rate-limit bypass | `core/config.py`, `middleware/rate_limiter.py` |
| 2 | P1 | Concurrent startup migration race | `core/database.py` |
| 3 | P1 | Redis outage → total API 500s | `middleware/rate_limiter.py`, `main.py` |
| 4 | P1 | `Cache-Control: public` on authenticated responses | `middleware/http_cache.py` |
| 5 | P1 | Logout did not revoke session; ignored Bearer clients | `routers/auth.py` |
| 6 | P2 | No AI quota on 5 anonymous LLM/PDF endpoints | `routers/ai.py`, `routers/chat.py`, `routers/documents.py` |
| 7 | P2 | Upload size guards ran after full buffering | `routers/auth.py`, `routers/documents.py` |
| 8 | P2 | Missing length validation → 500s on 4 write endpoints | `schemas.py` |
| 9 | P2 | Unbounded AI input on unauthenticated routes | `schemas.py`, `routers/chat.py`, `routers/documents.py` |
| 10 | P2 | Document cache never worked (`ttl=` kwarg) | `core/cache.py`, `services/ai_service.py` |
| 11 | P2 | Unbounded prompt cache | `services/ai_service.py` |
| 12 | P2 | Unbounded SSE poll-loop fan-out | `services/price_stream_service.py`, `routers/stocks.py` |
| 13 | P2 | Cache flush wiped the auth keyspace | `core/cache.py` |
| 14 | P3 | Readiness probe echoed raw driver errors | `routers/health.py` |
| 15 | P3 | 13 undocumented settings | `.env.example` |
| 16 | P3 | Two `Server` headers; uvicorn fingerprint unmasked | `Dockerfile` |

## Known Accepted Limitations

Classified per the validation brief, based on reading the code rather than the documentation:

| Area | Classification | Note |
|---|---|---|
| Render free-tier cold starts | EXPECTED LIMITATION | Cannot be reproduced locally; `NOT VERIFIED` |
| IndianAPI quota / 429 behaviour | ACCEPTABLE TRADEOFF | 429 correctly opens a 5-minute backoff circuit that short-circuits all calls, and readiness reports it — both verified |
| Redis fallback to in-memory | ACCEPTABLE TRADEOFF | Verified working; limits become per-instance and reuse detection stops (fail-closed 503), both documented |
| SSE in-process architecture | ACCEPTABLE TRADEOFF | Correct and leak-free for one process; becomes N independent poll loops at N processes |
| Circuit breakers per-process | ACCEPTABLE TRADEOFF | Documented; worst case is N× the failure budget |
| Google auth via `tokeninfo` | ACCEPTABLE TRADEOFF | Adds a network round-trip per sign-in but correctly validates signature, expiry and audience |
| Pre-auth token replayable for 5 min | ACCEPTABLE TRADEOFF | Documented; bounded by the TOTP check still being required |
| Local-only Prometheus/Grafana | EXPECTED LIMITATION | `/metrics` is exposed; no production scraper configured |
| `/refresh` accepts pre-migration tokens without `sid` | ACCEPTABLE TRADEOFF | Rollout compatibility path; should be removed now that it has served its purpose |
| Dead `circuit_breaker.py` registry | TECHNICAL DEBT | Documented as having no callers; `health.py` folds in the real state |

## Remaining Technical Debt

1. `app/core/circuit_breaker.py` has no callers anywhere (documented in `health.py`). Either adopt or delete.
2. `/api/auth/refresh`'s no-`sid` legacy branch is a permanent downgrade path for any pre-migration token.
3. `users.is_pro` is dead but still present; a migration should drop it.
4. `analyze_document` hardcodes `qwen/qwen3-32b` and `llama-3.1-8b-instant`; `ai_service.py`'s own docstring flags the former as absent from Groq's current catalog.
5. `_provider` (e.g. `groq/openai/gpt-oss-120b`) is returned to clients in AI responses, disclosing the internal model.
6. No frontend component or E2E tests.
7. Python version drift between the venv (3.10) and the deployment target (3.12).

## Recommended Next Steps

**Before deploying:**

1. **Set `TRUSTED_PROXY_HOPS` to match the real request path.** The default of 1 is correct if browsers reach the backend directly (one proxy: Render's edge). If auth traffic goes through the Next.js `/api/*` rewrite, there are two appending hops and this must be `2`. Getting it too low is safe (extra clients share a bucket); too high re-opens spoofing. **This needs your knowledge of the Vercel `NEXT_PUBLIC_API_URL` value.**

2. **Resolve the frontend API-URL inconsistency.** `lib/api.ts` uses same-origin relative `/api/*` (through the rewrite) while `lib/auth.tsx` uses absolute `${NEXT_PUBLIC_API_URL}/api/auth/*`. Because auth cookies are `SameSite=Strict`, they are not sent cross-site — so if `NEXT_PUBLIC_API_URL` points at the Render backend, authentication cannot work. Setting it to an empty string makes both paths same-origin.

3. **Upgrade Next.js** to `^15.5.24` and re-run the build plus a manual UI pass (P1-6).

**Soon after:**

4. Decide the multi-worker question: either reduce to one worker/replica, or accept N× polling and per-process breakers explicitly.
5. Put `/metrics` behind the edge or the existing `X-Admin-Key`.
6. Add `app/global-error.tsx` for Sentry App Router coverage.
7. Correct the stale `README.md` entries listed in P3-3.
8. Add frontend component/E2E tests — the largest remaining coverage gap.

## Final Sign-Off Checklist

| Check | Status |
|---|---|
| Alembic migrations apply cleanly to a fresh database | PASS |
| `alembic check` reports no model/migration drift | PASS |
| No P0 findings | PASS |
| All P1 findings fixed or explicitly owner-assigned | PASS (5 fixed, 1 assigned — Next.js upgrade) |
| Every fix has a regression test | PASS |
| No authorization bypass or IDOR | PASS (48 tests) |
| No secrets in tracked files or git history | PASS |
| No secrets in logs, metrics or error responses | PASS |
| Backend test suite green | PASS — 524 passed, 0 failed |
| Frontend `tsc --noEmit` clean | PASS |
| Frontend production build succeeds | PASS |
| Docker image builds from clean state | PASS |
| `.env.example` complete | PASS (verified both directions) |
| No N+1 queries on hot paths | PASS |
| No resource leaks under SSE churn | PASS |
| Zero errors under 50 concurrent load | PASS |
| Frontend dependency audit clean | **FAIL** — 8 vulnerable packages (P1-6) |
| Backend dependency audit clean | **FAIL** — 13 advisories across 4 packages |
| Frontend component/E2E tests exist | **FAIL** — none |
| Render free-tier behaviour verified | **NOT VERIFIED** — cannot be reproduced locally |
| Live IndianAPI 429 behaviour verified | **NOT VERIFIED** — mocked only |
| Multi-instance behaviour verified | **NOT VERIFIED** — single instance tested |

---

## Final Full Test Run

```
$ pytest tests/ -q
524 passed in 149.42s (0:02:29)          # clean, exclusive run — 0 failed, 0 skipped

$ pytest tests/ -q -m "not slow"
506 passed, 18 deselected

$ alembic upgrade head          (fresh database)   OK — 5 revisions applied
$ alembic check                                    No new upgrade operations detected
$ npx tsc --noEmit                                 exit 0, no errors
$ npx next build                                   ✓ Compiled successfully
$ docker build ./backend                           DONE 66.1s
$ npm audit --omit=dev                             8 vulnerabilities (1 critical, 6 high, 1 moderate)
$ pip-audit -r requirements.txt                    13 known vulnerabilities in 4 packages
```

### Backend dependency advisories (not fixed — documented for a separate upgrade pass)

| Package | Installed | Advisories | Fix version |
|---|---|---|---|
| starlette | 0.41.3 | 8 (PYSEC-2026-161/248/249/1941/1942/2280/2281) | pinned by `fastapi==0.115.6`; upgrade both together |
| python-dotenv | 1.0.1 | PYSEC-2026-2270 | 1.2.2 |
| lightgbm | 4.5.0 | PYSEC-2024-231 | 4.6.0 |
| ecdsa | 0.19.2 | PYSEC-2026-1325 | none available (transitive via python-jose) |

`starlette` is the notable one: it is the ASGI layer under every request, and its version is constrained by the pinned FastAPI. Upgrading needs FastAPI to move too, which is why it is recorded here rather than changed.

### Files modified during validation

**Application code (15 files) + Dockerfile:**

```
backend/app/core/cache.py                    reserved auth keyspace; ttl override on set()
backend/app/core/config.py                   TRUSTED_PROXY_HOPS setting
backend/app/core/database.py                 advisory lock around startup migration
backend/app/main.py                          wire ResilientSlowAPIMiddleware
backend/app/middleware/http_cache.py         no-store rules; fail-closed default
backend/app/middleware/rate_limiter.py       client_ip(); swallow_errors; ResilientSlowAPIMiddleware
backend/app/routers/ai.py                    AI rate limits on /ask and /ask-stream
backend/app/routers/auth.py                  logout session revoke + Bearer; bounded avatar read
backend/app/routers/chat.py                  input bounds; AI rate limit; drop PEP-563 annotations
backend/app/routers/documents.py             rate limits; bounded read; field bounds; drop PEP-563
backend/app/routers/health.py                generic error reasons on readiness
backend/app/routers/stocks.py                handle StreamCapacityExceeded as 503
backend/app/schemas.py                       length bounds mirroring column widths
backend/app/services/ai_service.py           bounded prompt cache; log cache failures
backend/app/services/price_stream_service.py MAX_STREAMED_TICKERS cap
```

**Configuration and tests:**

```
backend/Dockerfile                           --no-server-header; corrected XFF comment
backend/.env.example                         13 previously-undocumented settings
backend/pytest.ini                           new
backend/tests/                               new — 22 files (conftest + 21 test modules)
PRODUCTION_READINESS_REPORT.md               this document
```

Nothing was committed or pushed. Several other files in `backend/app/` were already modified in the working tree before this validation began and were **not** touched: `core/circuit_breaker.py`, `core/token_store.py`, `db/seed.py`, `middleware/request_id.py`, `models.py`, `routers/alerts.py`, `routers/portfolio.py`, and four service modules.
