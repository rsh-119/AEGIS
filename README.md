# Aegis — Indian Market Intelligence Platform

> Institutional-grade stock research for every Indian investor. AI-powered concall summaries, live fundamentals, peer benchmarks, portfolio intelligence, and real-time price streaming — completely free.

![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?style=flat-square&logo=postgresql)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Docker Setup](#docker-setup)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Deployment](#deployment)
- [Notes](#notes)
- [Disclaimer](#disclaimer)

---

## Features

### Market Intelligence
| Feature | Description |
|---|---|
| **Indian-only Search** | Live NSE/BSE autocomplete across all search bars — filters out non-Indian tickers automatically |
| **Live Stock Quotes** | Real-time price, % change, 52-week high/low, volume, market cap |
| **Interactive Price Chart** | OHLCV candlestick chart with MA20, MA50, and RSI overlays |
| **Market Overview** | Top gainers, losers, and most-active stocks updated continuously |
| **Bulk & Block Deals** | NSE bulk/block deal slider for the last 2 trading days, sorted by value |
| **Sector Analysis** | Sector-level heatmaps and constituent breakdowns |
| **IPO Tracker** | Upcoming, active, and recently listed IPOs |
| **Commodities** | Live commodity prices alongside equities and indices |
| **52-Week & Price Shockers** | Stocks hitting 52-week highs/lows and biggest single-day movers |

### AI-Powered Analysis
| Feature | Description |
|---|---|
| **AI Stock Analysis** | Multi-provider LLM waterfall (Groq → NVIDIA → OpenRouter) for valuation, risk, and outlook |
| **Company Health Diagnosis** | Flags declining revenue, margin pressure, rising debt, and negative news signals |
| **Concall Summaries** | AI-generated earnings call summaries — key highlights, guidance, risks in seconds |
| **Grounded AI Q&A** | Ask anything about a stock; leadership and price questions use live data, never stale training memory |
| **30-Day Price Projection** | Transparent linear-trend + volatility-band forecast, clearly labelled — not a prediction |

### Fundamentals & Research
| Feature | Description |
|---|---|
| **Full Fundamentals** | P/E, P/B, EV/EBITDA, ROE, ROCE, debt-to-equity, revenue/profit trends |
| **Technical Indicators** | RSI, moving averages, volume analysis, support/resistance levels |
| **Valuation Charts** | Visual comparison of current vs. historical valuation multiples |
| **Shareholding Pattern** | Promoter, FII, DII, retail breakdown with interactive pie chart |
| **Peer Benchmarking** | Compare any stock across its sector on key financial ratios side-by-side |
| **News + Sentiment** | Latest headlines scored with VADER sentiment analysis and split into positive/negative, with an overall sentiment badge (no NewsAPI key required) |
| **Credit Ratings & Annual Reports** | Latest credit rating actions and direct links to filed annual reports |
| **Company Logos & Corporate Actions** | Auto-resolved stock logos plus dividends/splits/bonus history |
| **Mutual Funds & ETFs** | Popular, top-gaining, and top-losing funds/ETFs across 1Y/3Y/5Y horizons via AMFI data, with holdings breakdown and similar-fund suggestions |

### Portfolio & Alerts
| Feature | Description |
|---|---|
| **Portfolio Tracker** | Add holdings with buy price and quantity; see live P&L and XIRR |
| **Watchlist** | Track stocks with custom target prices and alerts |
| **Stock Quick View** | Clicking a watchlist row opens a lightweight preview (price, chart, key stats, related news) instead of jumping straight to the full research page — a "Detail view" link goes there when you need it |
| **Price Alerts** | Set high/low price triggers with notification support |
| **Live Price Polling** | 30s cached-quote polling per stock page — tuned to stay within IndianAPI's metered quota |
| **Sortable Tables** | Bidirectional column sorting on watchlist, portfolio, and commodities tables |
| **Returns Calculator** | Project a monthly SIP or lump-sum investment forward at an assumed annual return |

### Platform
| Feature | Description |
|---|---|
| **User Authentication** | JWT-based register/login with refresh tokens |
| **Rate Limiting** | 120 requests/min per IP with slowapi |
| **Redis Caching** | Aggressive caching with graceful in-memory fallback when Redis is unavailable |
| **Circuit Breaker** | Automatic fallback on external API failures |
| **Prometheus Metrics** | Built-in `/metrics` endpoint for Grafana dashboards |

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, SWR, Framer Motion, Recharts |
| **Backend** | FastAPI, Python 3.12, Pydantic v2, SQLAlchemy 2.0 (async) |
| **Database** | PostgreSQL 17 with asyncpg driver |
| **Cache** | Redis 7 with in-memory fallback |
| **AI / LLM** | Groq (`openai/gpt-oss-120b` primary, `-20b` fallback), OpenRouter, NVIDIA NIM, Gemini — multi-step waterfall routing |
| **Market Data** | IndianAPI, NSE direct, AMFI, Alpha Vantage (no yfinance) |
| **Auth** | JWT (python-jose) + bcrypt |
| **Observability** | Prometheus, Alertmanager, structured logging |
| **Deployment** | Docker Compose (dev), Kubernetes (prod) — single backend replica, see [Deployment](#deployment) |
| **Testing** | pytest (backend), Vitest + Testing Library (frontend components), Playwright (E2E) |

---

## Architecture

```
aegis/
├── docker-compose.yml              # Full stack: Postgres, Redis, backend, frontend
├── docker-compose.monitoring.yml   # Prometheus + Alertmanager
│
├── backend/                        # FastAPI application
│   ├── app/
│   │   ├── main.py                 # Entrypoint — lifespan, middleware, routers
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   ├── schemas.py              # Pydantic v2 request/response schemas
│   │   ├── core/                   # Config, database, Redis cache, auth, metrics
│   │   ├── middleware/             # Request ID, rate limiter, HTTP cache, security headers
│   │   ├── routers/                # stocks, market, ai, mf, portfolio, watchlist,
│   │   │                           # chat, documents, alerts, auth, health
│   │   └── services/               # stock, market, ai, concall, forecast, peer,
│   │                               # bulk_deals, news, mf, indianapi, alphavantage,
│   │                               # home_refresh, shareholding, cache, ...
│   ├── tests/                      # pytest suite (runs against real Postgres + Redis)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/                       # Next.js 15 application
│   ├── app/                        # Pages: /, /stock/[ticker] (+/preview quick
│   │                               # view), /market, /mf (+ /[code]), /portfolio,
│   │                               # /watchlist, /peers, /concall (+ /document),
│   │                               # /ask, /alerts, /sector/[name], /index/[slug],
│   │                               # /ipo, /commodities, /calculator, /pricing,
│   │                               # /account, /admin, /login, /register
│   ├── components/                 # Nav, SearchBox, PriceChart, HealthCard,
│   │                               # ForecastCard, TechnicalsCard, PeerComparison,
│   │                               # ConcallCard, AskAI, MarketBar, StockLogo,
│   │                               # MFHighlights, LoginPrompt, ui/ (shadcn), ...
│   ├── lib/                        # api.ts, auth.tsx, guestData.ts, SWR config,
│   │                               # IndexedDB utils
│   ├── tests/                      # Vitest component/unit tests
│   ├── e2e/                        # Playwright end-to-end tests
│   ├── Dockerfile
│   └── .env.local.example
│
└── k8s/                            # Kubernetes manifests
    ├── namespace.yaml
    ├── deployment.yaml             # backend: 1 replica (see Deployment), RollingUpdate
    ├── service.yaml
    ├── configmap.yaml
    ├── secret.yaml                 # Template only — use real secrets manager
    └── hpa.yaml                    # HPA — pinned to 1 replica, see Deployment
```

---

## Quick Start

### Prerequisites

- Node.js 22+ and npm
- **Python 3.12** — the version `backend/Dockerfile`, `backend/runtime.txt` and
  `backend/.python-version` all target. Other 3.x versions may work but are not
  what production runs; pyenv/uv pick this up automatically from
  `.python-version`
- Docker and Docker Compose (for the database)
- A free [Groq API key](https://console.groq.com)

---

### 1. Start the Database

```bash
docker compose up -d db redis
```

This starts PostgreSQL on host port `5434` and Redis on host port `6380` (both remapped from the defaults, which are already taken on the maintainer's machine — see the comments in `docker-compose.yml`). Schema is created/migrated automatically on first backend startup via Alembic (see `backend/MIGRATIONS.md`); to also load realistic sample data, run `python -m app.db.seed` from `backend/` afterward.

---

### 2. Set Up the Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then open .env and fill in your keys
```

Edit `.env` and set at minimum:
- `GROQ_API_KEY` — free at [console.groq.com](https://console.groq.com)
- `DATABASE_URL` — already set correctly for the Docker Postgres above

```bash
uvicorn app.main:app --reload --port 8000
```

API docs are available at **http://localhost:8000/docs**

---

### 3. Set Up the Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # default values work for local dev
npm run dev
```

Open **http://localhost:3000**

---

## Docker Setup

To run the entire stack (database, backend, frontend) with a single command:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and add your API keys

docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| PostgreSQL | localhost:5434 |
| Redis | localhost:6380 |

To also start the monitoring stack (Prometheus + Grafana + Alertmanager):

```bash
# Grafana has no default credentials — set them first, or compose refuses to start
echo "GRAFANA_ADMIN_USER=admin"                       >> .env
echo "GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 16)" >> .env

docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

| Service | URL |
|---|---|
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3002 |
| Alertmanager | http://localhost:9093 |

`docker-compose.yml` sets `APP_ENV=production` for the backend container, which
puts `/metrics` behind `X-Admin-Key`. Either add that header to the scrape
config in `prometheus.yml` (there is a commented-out block ready for it) or set
`METRICS_PUBLIC=true` in `backend/.env`.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | PostgreSQL async connection string. No default — the app refuses to start without it |
| `JWT_SECRET_KEY` | **Yes** in prod | Signs access and refresh tokens (`openssl rand -hex 32`). With `APP_ENV=production` and this unset the app exits at startup; in development an ephemeral secret is generated so local runs need no setup |
| `INDIANAPI_KEY` | **Yes** for market data | The sole live market-data source. Without it quotes, charts and fundamentals all return "no data" — the app still starts |
| `INDIANAPI_ENABLED` | No | `false` hard-stops all IndianAPI calls when the monthly quota is spent. Default `true` |
| `GROQ_API_KEY` | No | Primary AI provider — free at [console.groq.com](https://console.groq.com) |
| `GROQ_API_KEY_2` / `GROQ_API_KEY_3` | No | Extra Groq keys; the waterfall round-robins across them to widen the free-tier token budget |
| `GROQ_MODEL` | No | Default: `openai/gpt-oss-120b` |
| `OPENROUTER_API_KEY` | No | OpenRouter key — second step in the waterfall |
| `OPENROUTER_MODEL` | No | Default: `nvidia/nemotron-3-super-120b-a12b:free` |
| `NVIDIA_API_KEY` | No | NVIDIA NIM key — last-resort fallback (correct but slow) |
| `NVIDIA_MODEL` | No | Default: `deepseek-ai/deepseek-v4-flash` |
| `GEMINI_API_KEY` | No | Free-tier key used as a fast first attempt for portfolio review/Q&A only |
| `GEMINI_MODEL` | No | Default: `gemini-3.6-flash` |
| `DOC_MODEL_DETAILED` | No | Groq model behind the "Deep Reasoning" document tier. Default: `openai/gpt-oss-120b`. Blank disables the tier |
| `DOC_MODEL_STANDARD` | No | Groq model behind the "Standard" document tier. Default: `openai/gpt-oss-20b`. Blank disables the tier |
| `AI_TIMEOUT_SECONDS` | No | Default: `60` |
| `REDIS_URL` | No | Default: `redis://localhost:6379`. Falls back to an in-memory cache if unreachable — see the caveat under [Notes](#notes) |
| `ADMIN_API_KEY` | No | Sent as the `X-Admin-Key` header. Gates `GET /health/status`, `GET /metrics` and `DELETE /api/cache` in production — all fail closed until it is set |
| `METRICS_PUBLIC` | No | `true` serves `/metrics` unauthenticated in production. Only for a network-isolated scraper. Default `false` |
| `JWT_ACCESS_EXPIRE_MINUTES` | No | Default: `60` |
| `JWT_REFRESH_EXPIRE_DAYS` | No | Default: `30` |
| `TRUSTED_PROXY_HOPS` | No | Appending reverse proxies in front of the app; picks the rate-limit client IP by counting from the right of `X-Forwarded-For`. **Leave at `1`** — see [Deployment](#deployment) |
| `TRUSTED_PROXY_IPS` | **Set it in production** | Which socket peers may set `X-Forwarded-For`. Default is loopback + RFC1918. Narrow it to your proxy's actual address — see [Deployment](#deployment) |
| `CORS_ORIGINS` | No | Comma-separated. Default: `http://localhost:3000` |
| `APP_ENV` | No | `development` (default) or `production`. Production disables `/docs`, `/redoc` and `/openapi.json`, sets `Secure` on cookies, and gates the admin endpoints |
| `READONLY_MODE` | No | Blocks writes with 503 for maintenance. Login/refresh/logout and reads keep working — see [Notes](#notes) |
| `RATE_LIMIT_ENABLED` | No | Toggle slowapi rate limiting. Default `true` |
| `LOG_LEVEL` | No | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. Default `INFO` |
| `SENTRY_DSN` | No | Error tracking. Disabled until set |
| `RESEND_API_KEY` | No | Password-reset email. Until set, `forgot-password` logs the reset link at INFO instead of sending it |
| `EMAIL_FROM_ADDRESS` | No | From address for reset emails |
| `FRONTEND_URL` | No | Used to build the reset link. Default: `http://localhost:3000` |
| `TOTP_ENCRYPTION_KEY` | No | Fernet key encrypting each user's TOTP secret at rest. `/2fa/setup` returns 501 until set |
| `GOOGLE_CLIENT_ID` | No | Google Sign-In. Must match the frontend's `NEXT_PUBLIC_GOOGLE_CLIENT_ID` |
| `NEWS_API_KEY` | No | Richer headlines; falls back to free RSS if absent |

`backend/.env.example` is the authoritative list and is kept in step with
`app/core/config.py` by `backend/tests/test_config_documentation.py`, which
fails if a setting is undocumented or a documented key is not a real setting.

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `API_PROXY_TARGET` | No | Where the Next.js `/api/:path*` rewrite proxies to, **server-side**. Default: `http://localhost:8000`. Read at **build time** — see the note below |
| `NEXT_PUBLIC_API_URL` | No | Deprecated alias for `API_PROXY_TARGET`, still honoured so existing Vercel/Render builds keep working. Despite the name it is no longer used by any browser-side code |
| `NEXT_PUBLIC_SENTRY_DSN` | No | Client error tracking. Disabled until set |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | No | Google Sign-In button. Not rendered until set. Must match the backend's `GOOGLE_CLIENT_ID` |

**The browser never talks to the backend directly.** Every API call in the app
— including authentication — goes to same-origin `/api/*`, and `next.config.js`
rewrites that to the backend server-side. This is not stylistic: the backend
sets its session cookies `SameSite=Strict`, so a cross-site request to the
backend origin would not carry them and login would fail in production while
still working locally, where both are `localhost`.

**The rewrite target is baked in at build time.** Next.js evaluates
`rewrites()` during `next build` and freezes the result into
`.next/routes-manifest.json`; the running server never calls it again. Setting
it only in a container's runtime environment has no effect — pass it as a
build arg (`docker build --build-arg API_PROXY_TARGET=...`), or set it in the
build environment on Vercel.

---

## API Reference

### Stocks

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stocks/search?q={query}` | Indian stock autocomplete (NSE/BSE) |
| `GET` | `/api/stocks/{ticker}/quote` | Live price, change, volume, fundamentals |
| `GET` | `/api/stocks/{ticker}/history?period=1y` | OHLCV candlestick data |
| `GET` | `/api/stocks/{ticker}/core?period=6mo` | Quote + history + ratio signals in one call — what the stock page loads first |
| `GET` | `/api/stocks/{ticker}/stream` | Server-Sent Events live price stream |
| `GET` | `/api/stocks/batch-quotes?tickers=A,B` | Up to 30 quotes in one call |
| `GET` | `/api/stocks/{ticker}/financials` | Income statement / balance sheet / cash flow |
| `GET` | `/api/stocks/{ticker}/news` | Headlines with VADER sentiment |
| `GET` | `/api/stocks/{ticker}/peers` | Peer comparison ratios |
| `GET` | `/api/stocks/{ticker}/shareholding-history` | Promoter/FII/DII/retail breakdown over time |
| `GET` | `/api/stocks/{ticker}/credit-ratings` | Latest credit rating actions |
| `GET` | `/api/stocks/{ticker}/annual-reports` | Links to filed annual reports |
| `GET` | `/api/stocks/{ticker}/logo` | Resolved company logo |
| `GET` | `/api/stocks/{ticker}/corporate-actions` | Dividends, splits, bonus history |
| `GET` | `/api/stocks/{ticker}/announcements` | Exchange announcements |
| `GET` | `/api/stocks/{ticker}/analyst-targets` | Analyst price targets — **Pro** |
| `GET` | `/api/stocks/{ticker}/analyst-forecasts` | Analyst estimate history — **Pro** |

There is no `/api/stocks/{ticker}/technicals` endpoint. Technical indicators
(RSI, moving averages) are computed from `/history` and returned inside
`/core`'s `signals` and `/insights`.

### Market

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/market/overview` | Top gainers, losers, most-active |
| `GET` | `/api/market/bulk-deals` | NSE bulk & block deals |
| `GET` | `/api/market/indices` | Nifty 50, Sensex, Bank Nifty, etc. |
| `GET` | `/api/market/ipo` | Upcoming, active, and recently listed IPOs |
| `GET` | `/api/market/commodities` | Live commodity prices |
| `GET` | `/api/market/52week` | 52-week high/low movers |
| `GET` | `/api/market/price-shockers` | Biggest single-day movers |
| `GET` | `/api/market/sector/{sector}` | Constituents of a sector |
| `GET` | `/api/market/sectors` | Sector heatmap |
| `GET` | `/api/market/cap/{size}` | Large/mid/small-cap constituents |
| `GET` | `/api/market/index/{slug}` | Index detail and constituents |
| `GET` | `/api/market/corporate-actions` | Market-wide dividends, splits, bonuses |
| `GET` | `/api/market/indianapi-usage` | Remaining metered IndianAPI quota |

### AI

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stocks/{ticker}/insights` | AI valuation/risk analysis, health diagnosis, and forecasts (parallel) |
| `GET` | `/api/stocks/{ticker}/concall-summary` | AI-generated earnings call summary |
| `POST` | `/api/ai/ask` | Grounded Q&A with live data context |
| `POST` | `/api/ai/ask-stream` | Same, streamed as SSE |
| `POST` | `/api/chat` | Conversational assistant with stock cards |
| `GET` | `/api/stocks/{ticker}/ai-summary` | AI valuation/risk summary |
| `GET` | `/api/stocks/{ticker}/health-diagnosis` | Company health diagnosis |
| `GET` | `/api/portfolio/insights/ai` | AI portfolio review |
| `POST` | `/api/portfolio/ask` | Q&A grounded in the caller's own holdings |
| `POST` | `/api/documents/upload-pdf` | Upload a concall/annual-report PDF for analysis |
| `POST` | `/api/documents/analyze` | Analyze an uploaded document |
| `POST` | `/api/documents/ask` | Ask questions grounded in an uploaded document |

### Mutual Funds & ETFs

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/mf/highlights` | Top funds by performance |
| `GET` | `/api/mf/{scheme_code}` | Fund detail and NAV history |
| `GET` | `/api/mf/{scheme_code}/holdings` | Fund's underlying holdings |
| `GET` | `/api/mf/{scheme_code}/calculator` | SIP / lumpsum return calculator |
| `GET` | `/api/etf/highlights` | Top ETFs by performance |
| `GET` | `/api/etf/{ticker}` | ETF detail and NAV history |

### Portfolio & Watchlist

| Method | Endpoint | Description |
|---|---|---|
| `GET/POST/DELETE` | `/api/portfolio` | Holdings with live P&L |
| `GET/POST/DELETE` | `/api/watchlist` | Watchlist with target prices |
| `GET/POST/DELETE` | `/api/alerts` | Price alert rules |

### Auth

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create account |
| `POST` | `/api/auth/login` | Get access + refresh tokens |
| `POST` | `/api/auth/refresh` | Rotate refresh token |
| `GET` | `/api/auth/me` | Current user profile |
| `POST` | `/api/auth/logout` | Revoke the session — both the access token and the refresh chain |
| `POST` | `/api/auth/google` | Sign in with a Google ID token |
| `POST` | `/api/auth/2fa/setup` \| `/enable` \| `/disable` \| `/verify-login` | TOTP two-factor |
| `POST` | `/api/auth/forgot-password` \| `/reset-password` | Password reset by emailed token |
| `POST` | `/api/auth/me/password` | Change password while signed in |
| `POST` \| `DELETE` | `/api/auth/me/avatar` | Profile photo upload / removal |
| `POST` | `/api/auth/sync-guest-data` | Import anonymous localStorage holdings/watchlist on first login |

`/login` and `/refresh` do **not** return tokens in the response body. Auth is
delivered as httpOnly `SameSite=Strict` cookies (`Secure` in production), with
an `Authorization: Bearer` fallback accepted for script clients.

### Ops

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health/live` | none | Liveness probe |
| `GET` | `/health/ready` | none | Readiness — database, Redis, circuit breakers |
| `GET` | `/health/status` | `X-Admin-Key` in prod | Full ops dashboard |
| `GET` | `/metrics` | `X-Admin-Key` in prod | Prometheus exposition |
| `GET` | `/api/admin/users`, `/api/admin/stats` | admin account | User administration |
| `DELETE` | `/api/cache` | `X-Admin-Key` in prod | Flush cache (never the `auth:` keyspace) |

Full interactive documentation: **http://localhost:8000/docs** — disabled when
`APP_ENV=production`, along with `/redoc` and `/openapi.json`.

---

## Testing

### Backend

```bash
cd backend
source venv/bin/activate
pytest                       # full suite
pytest -m "not slow"         # skip perf/load/live-SSE
```

The suite runs against a **real** PostgreSQL and Redis rather than fakes —
`docker compose up -d db redis` provides both — and builds its schema with
`alembic upgrade head`, never `create_all()`, so it exercises the schema
production gets. Every external service (IndianAPI, Groq, OpenRouter, NVIDIA,
Gemini, Google, Resend) is mocked at its own call boundary; `INDIANAPI_ENABLED`
is `false` throughout, so the tests run against the worst realistic case of no
market data at all.

> **The suite needs exclusive access to its database and Redis db.** It
> `TRUNCATE`s every application table and `FLUSHDB`s Redis between tests, so two
> runs against the same `DATABASE_URL`/`REDIS_URL` corrupt each other.
> **`pytest-xdist` (`-n`) is not supported** for the same reason. To
> parallelise, give each worker its own database and Redis db via the
> `TEST_DATABASE_URL` / `TEST_REDIS_URL` environment overrides.

Defaults are `postgresql+asyncpg://aegis:aegis@localhost:5434/aegis_test` and
`redis://localhost:6380/15`.

### Frontend

```bash
cd frontend
npm test                     # Vitest — component/unit
npx tsc --noEmit             # type check
npm run test:e2e             # Playwright — needs `npm run build` first
```

`npm run test:e2e` starts `next start` against a production build and stubs
every `/api/*` call in `e2e/fixtures.ts`, so it never contacts IndianAPI, an
LLM provider, Postgres or Redis and is deterministic offline. First run needs
`npx playwright install chromium`.

`e2e/live.spec.ts` is a second, **opt-in** suite that drives the real stack —
real backend, real Postgres and Redis, real cookies — and is skipped unless
`E2E_LIVE=1`. It is the only place things like actual `Set-Cookie` flags,
CSP enforcement in a browser and hydration can be observed. Its header
documents the accounts it needs. Note it shares the per-IP login rate limit
(5/15min), so repeated local runs need
`docker exec aegis-redis-1 redis-cli -n 3 FLUSHDB` between them.

> `npm run lint` is **not configured** — this repo has never had an ESLint
> config, so `next lint` prompts to create one interactively. `tsc --noEmit` is
> the type gate. (`next lint` is also deprecated and is removed in Next.js 16.)

### Security scanning

```bash
cd frontend && npm audit --omit=dev
cd backend  && pip-audit -r requirements.txt
```

---

## Deployment

### Docker Compose (Single Server)

```bash
# Production — set strong secrets in backend/.env first
docker compose up -d --build
```

### Kubernetes

```bash
# Apply namespace and config
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml

# Create real secrets (do NOT use secret.yaml as-is)
kubectl create secret generic aegis-secrets -n aegis \
  --from-literal=DATABASE_URL="postgresql+asyncpg://user:pass@host/aegis" \
  --from-literal=INDIANAPI_KEY="..." \
  --from-literal=GROQ_API_KEY="gsk_..." \
  --from-literal=NVIDIA_API_KEY="nvapi-..." \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=ADMIN_API_KEY="$(openssl rand -hex 32)" \
  --from-literal=TOTP_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

`JWT_SECRET_KEY` is **mandatory**: with `APP_ENV=production` and no value the
pod raises at startup and CrashLoopBackOffs rather than starting degraded.
`ADMIN_API_KEY` and `TOTP_ENCRYPTION_KEY` fail *closed* — without them
`/metrics`, `/health/status` and `DELETE /api/cache` return 403, and
`/2fa/setup` returns 501. Rotating `TOTP_ENCRYPTION_KEY` later invalidates
every stored TOTP secret and forces all 2FA users to re-enrol, so set it once.

Also set `TRUSTED_PROXY_IPS` in `k8s/configmap.yaml` to your ingress
controller's pod CIDR (see below) — the default trusts the whole RFC1918 range,
which in a cluster means any workload could forge a client IP.

```bash
# Deploy
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

### Scaling — read before raising the replica count

**The backend runs one process, deliberately.** `backend/Dockerfile` uses
`--workers 1`, `k8s/deployment.yaml` sets `replicas: 1`, and `k8s/hpa.yaml` is
pinned to min/max 1. This is a correctness constraint, not a throughput
setting: three things are per-process state rather than shared, so every extra
process multiplies their cost.

| Per-process state | Cost of a second process |
|---|---|
| SSE price-stream hub (`services/price_stream_service.py`) | One poll loop per ticker *per process* — N× calls against IndianAPI's metered monthly quota for the same viewers |
| In-process prompt cache (`services/ai_service.py`) | Hit rate splits N ways; repeated prompts re-bill full LLM calls |
| Circuit breakers (IndianAPI, Groq streaming) | Each process trips and recovers independently — N× the intended failure budget |

Rate limiting and session/refresh state are already shared correctly through
Redis and are not the constraint. To scale horizontally, move the SSE hub and
prompt cache to Redis and make the breakers shared first; the tuned HPA
behaviour is left in `k8s/hpa.yaml` for that day. Until then, scale vertically.

### `TRUSTED_PROXY_IPS` — narrow this in production

Per-IP rate limits are only as trustworthy as the `X-Forwarded-For` header they
read, and that header is only meaningful if something in front actually wrote
it. A caller reaching the backend **directly** can send their own
`X-Forwarded-For`; with no proxy to append to it, that one value is both the
first and the last entry, so counting hops from either end reads the attacker's
choice. Forty login attempts with a rotating header then produce zero 429s
against a 5-per-15-minutes limit.

The app therefore consults the header **only when the real socket peer is
inside `TRUSTED_PROXY_IPS`**, and keys off the true peer otherwise. (This is
also why `backend/Dockerfile` no longer passes `--proxy-headers
--forwarded-allow-ips "*"`: those flags overwrote `request.client.host` with
the client-written entry before the app could see the real one.)

**The default — loopback plus the RFC1918 ranges — is convenient, not strict.**
An IP check cannot distinguish a genuine reverse proxy on a private address
from a NAT. Docker's `ports: "8000:8000"` rewrites the source address into the
bridge subnet, so a caller from anywhere presents a `172.x` peer and their
header is honoured. Two mitigations ship for this:

- `docker-compose.yml` binds the backend, database and Redis to `127.0.0.1`, so
  the NAT-fronted backend is not published to the network at all.
- `TRUSTED_PROXY_IPS` is configurable. In production, set it to your proxy's
  address rather than leaving the default:

  ```bash
  TRUSTED_PROXY_IPS=10.8.0.5        # verified: closes the bypass entirely
  ```

  Symptom of setting it too narrowly is over-limiting (every client shares one
  bucket), which is the safe direction to be wrong in. `*` disables the check
  and is only correct if the app is genuinely unreachable except through a
  proxy.

`backend/tests/test_rate_limiting.py` covers both topologies — behind an
appending proxy, and connected directly — plus the NAT caveat above.

### `TRUSTED_PROXY_HOPS` — leave it at 1

Per-IP rate limits key off `X-Forwarded-For`, counting `TRUSTED_PROXY_HOPS`
entries from the **right**, so entries a client prepends are ignored.

Raising it to `2` looks correct for browser → Vercel → Render, and would give
each client its own bucket instead of everyone sharing Vercel's egress
address. It is not safe here: the Render service URL is publicly resolvable, so
an attacker can bypass Vercel, connect to the backend directly with a forged
header, and have Render's edge append their real peer — two entries, the
leftmost attacker-chosen. At `hops=2` that forged value becomes the rate-limit
key and per-IP limiting is defeated.

The known cost of staying at `1` is that requests arriving through the rewrite
share one bucket. That is the safe direction to be wrong in. Raise it to `2`
only once the backend has no public origin (Render private service, or an IP
allowlist restricting it to the proxy), then re-run
`backend/tests/test_rate_limiting.py`.

---

## Notes

- Tickers default to `.NS` (NSE); append `.BO` for BSE (e.g., `RELIANCE.BO`)
- The 30-day price projection is a statistical model — clearly labelled in the UI. Not a prediction
- The AI waterfall tries Groq first (`openai/gpt-oss-120b`, then `-20b`), then OpenRouter, then NVIDIA NIM. Portfolio review/Q&A try a free-tier Gemini key first. Any one key is sufficient; the chain fails quietly and moves on
- Redis is optional in development — the backend falls back to an in-memory cache. In **production it is not really optional**: rate limits become per-instance, and refresh-token reuse detection fails closed (`POST /api/auth/refresh` returns 503 by design rather than accepting a token it cannot verify)
- `READONLY_MODE=true` blocks writes but deliberately keeps login, refresh, logout and all reads working, so an incident degrades the site to read-only browsing rather than to anonymous-only. Writes under `/api/auth` (register, profile edit, password change/reset, guest sync, 2FA setup) stay blocked

---

## Disclaimer

Aegis is for **educational and informational purposes only**. Nothing on this platform constitutes investment advice, a recommendation to buy or sell any security, or a solicitation of any investment. Always do your own research and consult a SEBI-registered financial advisor before making investment decisions.
