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
- [Deployment](#deployment)
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
| **News + Sentiment** | Latest headlines scored with VADER sentiment analysis (no NewsAPI key required) |
| **Credit Ratings & Annual Reports** | Latest credit rating actions and direct links to filed annual reports |
| **Company Logos & Corporate Actions** | Auto-resolved stock logos plus dividends/splits/bonus history |
| **Mutual Funds & ETFs** | Popular, top-gaining, and top-losing funds/ETFs across 1Y/3Y/5Y horizons via AMFI data, with holdings breakdown and similar-fund suggestions |

### Portfolio & Alerts
| Feature | Description |
|---|---|
| **Portfolio Tracker** | Add holdings with buy price and quantity; see live P&L and XIRR |
| **Watchlist** | Track stocks with custom target prices and alerts |
| **Price Alerts** | Set high/low price triggers with notification support |
| **Live Price Polling** | 30s cached-quote polling per stock page — tuned to stay within IndianAPI's metered quota |
| **Sortable Tables** | Bidirectional column sorting on watchlist, portfolio, and commodities tables |

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
| **AI / LLM** | Groq (Llama 3.3 70B + fallback models), NVIDIA NIM (DeepSeek, MiniMax), OpenRouter — multi-step waterfall routing |
| **Market Data** | IndianAPI, NSE direct, AMFI, Alpha Vantage (no yfinance) |
| **Auth** | JWT (python-jose) + bcrypt |
| **Observability** | Prometheus, Alertmanager, structured logging |
| **Deployment** | Docker Compose (dev), Kubernetes with HPA (prod) |

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
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/                       # Next.js 15 application
│   ├── app/                        # Pages: /, /stock/[ticker], /market, /mf,
│   │                               # /portfolio, /watchlist, /peers, /concall,
│   │                               # /ask, /alerts, /sector/[name], /index/[slug],
│   │                               # /ipo, /commodities, /login, /register
│   ├── components/                 # Nav, SearchBox, PriceChart, HealthCard,
│   │                               # ForecastCard, TechnicalsCard, PeerComparison,
│   │                               # ConcallCard, AskAI, MarketBar, StockLogo,
│   │                               # MFHighlights, LoginPrompt, ui/ (shadcn), ...
│   ├── lib/                        # api.ts, auth.tsx, SWR config, IndexedDB utils
│   ├── Dockerfile
│   └── .env.local.example
│
└── k8s/                            # Kubernetes manifests
    ├── namespace.yaml
    ├── deployment.yaml             # 2 replicas, RollingUpdate
    ├── service.yaml
    ├── configmap.yaml
    ├── secret.yaml                 # Template only — use real secrets manager
    └── hpa.yaml                    # Horizontal Pod Autoscaler
```

---

## Quick Start

### Prerequisites

- Node.js 22+ and npm
- Python 3.12+
- Docker and Docker Compose (for the database)
- A free [Groq API key](https://console.groq.com)

---

### 1. Start the Database

```bash
docker compose up -d db redis
```

This starts PostgreSQL on port `5433` and Redis on `6379`. Tables are auto-created on first backend startup.

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
| PostgreSQL | localhost:5433 |
| Redis | localhost:6379 |

To also start the monitoring stack (Prometheus + Alertmanager):

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `GROQ_API_KEY` | Yes | Free at [console.groq.com](https://console.groq.com) — primary AI provider |
| `GROQ_API_KEY_2` / `GROQ_API_KEY_3` | No | Extra Groq keys to widen the token budget |
| `GROQ_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `NVIDIA_API_KEY` | No | NVIDIA NIM key — DeepSeek fallback |
| `NVIDIA_MODEL` | No | Default: `deepseek-ai/deepseek-v4-flash` |
| `NVIDIA_MINIMAX_API_KEY` | No | Separate NVIDIA NIM key — MiniMax fallback |
| `NVIDIA_MINIMAX_MODEL` | No | Default: `minimaxai/minimax-m2.7` |
| `OPENROUTER_API_KEY` | No | OpenRouter key (final AI fallback) |
| `OPENROUTER_MODEL` | No | Default: `openai/gpt-oss-120b:free` |
| `INDIANAPI_KEY` | No | IndianAPI key for market/stock data |
| `INDIANAPI_ENABLED` | No | Set `false` to disable if the monthly quota is exhausted |
| `JWT_SECRET_KEY` | Yes | Random 32-byte string for JWT signing |
| `JWT_ACCESS_EXPIRE_MINUTES` | No | Default: `60` |
| `JWT_REFRESH_EXPIRE_DAYS` | No | Default: `30` |
| `REDIS_URL` | No | Falls back to in-memory cache if absent |
| `CORS_ORIGINS` | No | Default: `http://localhost:3000` |
| `APP_ENV` | No | `development` or `production` |
| `AI_TIMEOUT_SECONDS` | No | Default: `60` |
| `NEWS_API_KEY` | No | Falls back to free RSS feeds if absent |
| `READONLY_MODE` | No | Blocks all write operations when `true` |
| `RATE_LIMIT_ENABLED` | No | Toggle slowapi rate limiting (default `true`) |
| `LOG_LEVEL` | No | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | Backend base URL (default: `http://localhost:8000`) |
| `NEXT_PUBLIC_WS_URL` | No | WebSocket URL (default: `ws://localhost:8000`) |

---

## API Reference

### Stocks

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stocks/search?q={query}` | Indian stock autocomplete (NSE/BSE) |
| `GET` | `/api/stocks/{ticker}/quote` | Live price, change, volume, fundamentals |
| `GET` | `/api/stocks/{ticker}/history?period=1y` | OHLCV candlestick data |
| `GET` | `/api/stocks/{ticker}/technicals` | RSI, MA, support/resistance |
| `GET` | `/api/stocks/{ticker}/peers` | Peer comparison ratios |
| `GET` | `/api/stocks/{ticker}/shareholding-history` | Promoter/FII/DII/retail breakdown over time |
| `GET` | `/api/stocks/{ticker}/credit-ratings` | Latest credit rating actions |
| `GET` | `/api/stocks/{ticker}/annual-reports` | Links to filed annual reports |
| `GET` | `/api/stocks/{ticker}/logo` | Resolved company logo |
| `GET` | `/api/stocks/{ticker}/corporate-actions` | Dividends, splits, bonus history |
| `GET` | `/api/stocks/{ticker}/announcements` | Exchange announcements |

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

### AI

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/stocks/{ticker}/insights` | AI valuation/risk analysis, health diagnosis, and forecasts (parallel) |
| `GET` | `/api/stocks/{ticker}/concall-summary` | AI-generated earnings call summary |
| `POST` | `/api/ai/ask` | Grounded Q&A with live data context |
| `POST` | `/api/documents/upload-pdf` | Upload a concall/annual-report PDF for analysis |
| `POST` | `/api/documents/analyze` | Analyze an uploaded document |
| `POST` | `/api/documents/ask` | Ask questions grounded in an uploaded document |

### Mutual Funds & ETFs

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/mf/highlights` | Top funds by performance |
| `GET` | `/api/mf/{code}` | Fund detail and NAV history |
| `GET` | `/api/mf/{code}/holdings` | Fund's underlying holdings |
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
| `POST` | `/api/auth/logout` | Invalidate session |

Full interactive documentation: **http://localhost:8000/docs**

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
  --from-literal=GROQ_API_KEY="gsk_..." \
  --from-literal=NVIDIA_API_KEY="nvapi-..." \
  --from-literal=JWT_SECRET_KEY="$(openssl rand -hex 32)"

# Deploy
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

The HPA scales between 2 and 10 backend replicas based on CPU utilization.

---

## Notes

- Tickers default to `.NS` (NSE); append `.BO` for BSE (e.g., `RELIANCE.BO`)
- The 30-day price projection is a statistical model — clearly labelled in the UI. Not a prediction
- The AI waterfall tries Groq first, then NVIDIA NIM (DeepSeek, then MiniMax), then OpenRouter — any one key is sufficient
- Redis is optional; the backend falls back to an in-memory LRU cache automatically

---

## Disclaimer

Aegis is for **educational and informational purposes only**. Nothing on this platform constitutes investment advice, a recommendation to buy or sell any security, or a solicitation of any investment. Always do your own research and consult a SEBI-registered financial advisor before making investment decisions.
