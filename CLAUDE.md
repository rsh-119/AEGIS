# AEGIS — context for Claude Code

Indian stock market intelligence platform. FastAPI backend (`backend/`), Next.js 15 frontend (`frontend/`).

## LLM setup (actual, verified 2026-07-18)
- Waterfall in `backend/app/services/ai_service.py::_chat_json`:
  **Groq (llama-3.3-70b, multi-key round-robin + extra models) → MiniMax M2.7 (via NVIDIA) → OpenRouter (Nemotron-3-super-120B + free fallbacks) → NVIDIA GLM-5.2 (last resort, 180s window — free-tier queue is ~2-3 min)**
- Detailed prose tasks (`answer`, `ask_document`, `ask_portfolio`) pass `prefer_openrouter=True` and lead with Nemotron instead.
- All providers are OpenAI-compatible chat completions. Groq + OpenRouter get `response_format=json_object`; OpenRouter also gets `reasoning: {enabled: false}` (Nemotron's reasoning stream otherwise eats the max_tokens budget).
- Successful responses carry a `_provider` tag for diagnostics.
- OpenRouter free-model IDs **rotate** — a 404 on the chat leg means the roster changed, not a bad key.
- Prompt cache: in-memory, 20h, keyed on (system, user). Portfolio AI calls bypass it (`use_cache=False`). Result caches: Postgres `ai_cache` table via `cache_service` (analyse/health/concall 20h). Concall only caches **complete** runs.

## Non-negotiable rules for AI features
1. The model NEVER states a price, ratio, CEO name, or date from its own memory.
   Every number in the output must come from the injected facts/context block.
2. No investment advice. No "buy/sell/hold". Analysis and framing only.
3. Indian conventions: INR, crore/lakh, NSE/BSE tickers, FY ending March, SEBI context.
4. Every AI endpoint returns validated JSON. Never raw prose.
5. If a fact is missing from the injected data, output "Not available" — never estimate.
6. Compute every number in Python before the call. The model interprets numbers; it does not calculate them.

## AI surfaces (actual routes)
- `POST /api/ai/ask` — grounded Q&A (`ai_service.answer`), quote+history+news+bulk-deals grounding
- `GET /api/stocks/{ticker}/…` deferred bundle — calls `analyse_stock` + `diagnose_health`
- `GET /api/stocks/{ticker}/concall-summary` — `concall_service` (quarterly financials + news → per-quarter summaries; NOT transcript-based)
- `POST /api/portfolio/insights?ai=1`, `POST /api/portfolio/ask` — portfolio review/Q&A (uncached)
- Document analysis/Q&A — `analyze_document` / `ask_document`

## Gotchas
- `.env` is gitignored and holds all provider keys; never hardcode keys or echo them.
- `uvicorn --reload` only watches `.py` files — after editing `.env`, `touch app/main.py`.
- Never run `npm run build` while `next dev` is running (corrupts `.next`).
- Frontend commits: short single-line messages, no Co-Authored-By trailer.
