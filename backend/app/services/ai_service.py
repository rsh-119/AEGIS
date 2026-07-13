"""
ai_service.py — Multi-provider AI for Indian stock analysis.

Provider chain (automatic waterfall — each step tried only if prior step fails):
  0. Prompt cache (20h TTL) — returns instantly for repeated calls
  1. Groq    llama-3.3-70b-versatile        (primary — 100k TPD free, low latency)
  2. Groq    llama-3.1-8b-instant           (fallback #1 — 500k TPD)
  3. Groq    llama-3.3-70b-specdec          (fallback #2)
  4. Groq    meta-llama/llama-4-scout       (fallback #3)
  5. NVIDIA  deepseek-ai/deepseek-v4-flash  (fallback #4 — chain-of-thought, rate-limited)
  6. NVIDIA  minimaxai/minimax-m2.7         (fallback #5 — 8k context, separate key)
  7. OpenRouter  settings.openrouter_model  (fallback #6 — paid key)
  8. OpenRouter  meta-llama/llama-3.3-70b-instruct:free
  9. OpenRouter  google/gemma-3-27b-it:free
 10. OpenRouter  mistralai/mistral-small-3.2-24b-instruct:free

Four capabilities:
  • analyse_stock()    — valuation, risks, outlook (structured, data-cited)
  • diagnose_health()  — "what's going wrong" over recent quarters
  • answer()           — grounded Q&A with live context injection
  • analyze_document() — deep concall / annual report analysis
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time

import httpx
from groq import AsyncGroq, RateLimitError, APIStatusError
from openai import AsyncOpenAI
from openai import RateLimitError as NvidiaRateLimitError, APIStatusError as NvidiaAPIStatusError

from app.core.config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

_groq_client:     AsyncGroq   | None = None
_nvidia_client:   AsyncOpenAI | None = None
_minimax_client:  AsyncOpenAI | None = None

# ── Groq key pool — round-robins across all configured keys ──────────────────
_groq_key_index: int = 0
_groq_clients:   list[AsyncGroq] = []

def _get_groq_pool() -> list[AsyncGroq]:
    """Return one AsyncGroq client per configured key, building lazily."""
    global _groq_clients
    if not _groq_clients:
        _groq_clients = [AsyncGroq(api_key=k) for k in settings.groq_keys if k]
    return _groq_clients

def _next_groq_client() -> AsyncGroq | None:
    """Pick next Groq client in round-robin order."""
    global _groq_key_index
    pool = _get_groq_pool()
    if not pool:
        return None
    client = pool[_groq_key_index % len(pool)]
    _groq_key_index += 1
    return client

# ── Document analysis semaphore — limit concurrent AI calls ──────────────────
# Each call uses ~4,500 tokens. Groq free: 12K tokens/min per key.
# With N keys: budget = N × 12K. 2 concurrent slots per key keeps us within limit.
# The semaphore is resized after settings load (see _build_doc_semaphore below).
_DOC_SEMAPHORE: asyncio.Semaphore | None = None

def _doc_semaphore() -> asyncio.Semaphore:
    global _DOC_SEMAPHORE
    if _DOC_SEMAPHORE is None:
        n_keys = max(1, len(settings.groq_keys))
        # 2 concurrent slots per key — leaves headroom for the chat waterfall
        _DOC_SEMAPHORE = asyncio.Semaphore(n_keys * 2)
    return _DOC_SEMAPHORE

# ── Request-level prompt cache ────────────────────────────────────────────────
# Keyed by sha256(system+user); TTL matches analysis cache so same context
# never re-hits any provider within the same day.
_PROMPT_CACHE_TTL = 20 * 3600  # 20 hours

class _PromptCache:
    def __init__(self, ttl: int):
        self._ttl   = ttl
        self._store: dict[str, tuple[dict, float]] = {}

    def _key(self, system: str, user: str) -> str:
        return hashlib.sha256((system + user).encode()).hexdigest()[:24]

    def get(self, system: str, user: str) -> dict | None:
        k = self._key(system, user)
        entry = self._store.get(k)
        if entry and time.monotonic() - entry[1] < self._ttl:
            return entry[0]
        if entry:
            del self._store[k]
        return None

    def set(self, system: str, user: str, value: dict) -> None:
        self._store[self._key(system, user)] = (value, time.monotonic())

_prompt_cache = _PromptCache(ttl=_PROMPT_CACHE_TTL)
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# Groq fallback models — each has a separate daily quota
_GROQ_EXTRA_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-specdec",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]

# OpenRouter free fallbacks
_OPENROUTER_EXTRA_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
]


# ── Provider clients ──────────────────────────────────────────────────────────

def _get_groq() -> AsyncGroq | None:
    """Single-client getter (used by chat waterfall). Doc analysis uses _next_groq_client()."""
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_client


def _get_nvidia() -> AsyncOpenAI | None:
    global _nvidia_client
    if not settings.nvidia_api_key:
        return None
    if _nvidia_client is None:
        _nvidia_client = AsyncOpenAI(
            base_url=_NVIDIA_BASE_URL,
            api_key=settings.nvidia_api_key,
        )
    return _nvidia_client


def _get_minimax() -> AsyncOpenAI | None:
    global _minimax_client
    if not settings.nvidia_minimax_api_key:
        return None
    if _minimax_client is None:
        _minimax_client = AsyncOpenAI(
            base_url=_NVIDIA_BASE_URL,
            api_key=settings.nvidia_minimax_api_key,
        )
    return _minimax_client


def _parse_json(raw: str | None) -> dict:
    """Parse JSON defensively — strips <think> blocks and markdown fences."""
    if not raw:
        raise json.JSONDecodeError("Empty response from model", "", 0)
    text = raw.strip()
    # strip DeepSeek chain-of-thought <think>...</think> block
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # strip ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$",          "", text)
    return json.loads(text.strip())


# ── NVIDIA / DeepSeek call ────────────────────────────────────────────────────

async def _call_nvidia(system: str, user: str, max_tokens: int, model: str | None = None) -> dict:
    client = _get_nvidia()
    if client is None:
        raise RuntimeError("NVIDIA_API_KEY not configured")
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=model or settings.nvidia_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.6,
            top_p=0.95,
            max_tokens=max_tokens,
            extra_body={"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}},
            stream=False,
        ),
        timeout=settings.ai_timeout_seconds,
    )
    content = resp.choices[0].message.content
    return _parse_json(content)


# ── MiniMax M2.7 call (via NVIDIA endpoint, separate key) ────────────────────

async def _call_minimax(system: str, user: str, max_tokens: int) -> dict:
    client = _get_minimax()
    if client is None:
        raise RuntimeError("NVIDIA_MINIMAX_API_KEY not configured")
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=settings.nvidia_minimax_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.3,    # lower than default 1.0 for structured JSON tasks
            top_p=0.95,
            max_tokens=min(max_tokens, 8192),
            stream=False,
        ),
        timeout=settings.ai_timeout_seconds,
    )
    content = resp.choices[0].message.content
    return _parse_json(content)


# ── Groq call ─────────────────────────────────────────────────────────────────

async def _call_groq(system: str, user: str, max_tokens: int, model: str | None = None) -> dict:
    # Use round-robin pool if multiple keys are configured, else fall back to single client
    client = _next_groq_client() or _get_groq()
    if client is None:
        raise RuntimeError("GROQ_API_KEY not configured")
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=model or settings.groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.15,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        ),
        timeout=settings.ai_timeout_seconds,
    )
    return _parse_json(resp.choices[0].message.content)


# ── OpenRouter call ───────────────────────────────────────────────────────────

async def _call_openrouter(system: str, user: str, max_tokens: int, model: str | None = None) -> dict:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    _model = model or settings.openrouter_model
    payload = {
        "model": _model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": 0.15,
        "max_tokens":  max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://aegis.app",
        "X-Title":       "AEGIS Stock Intelligence",
    }
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as http:
        r = await http.post(_OPENROUTER_URL, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        raw  = data["choices"][0]["message"]["content"]
        return _parse_json(raw)


# ── Unified waterfall: NVIDIA → Groq → OpenRouter ────────────────────────────

async def _chat_json(system: str, user: str, max_tokens: int = 1200, use_cache: bool = True) -> dict:
    """
    Multi-model waterfall — Groq (primary) → NVIDIA DeepSeek → OpenRouter.
    Prompt-level cache: identical (system, user) pairs return cached result
    within 20 hours without hitting any provider.
    Moves to the next provider on any error. Returns a dict; never raises.
    """
    # ── 0. Prompt cache — skip all providers for repeated calls.
    #    use_cache=False for live-data prompts (e.g. portfolio review/Q&A)
    #    where a fresh model call is expected every time. ─────────────────────
    if use_cache:
        cached = _prompt_cache.get(system, user)
        if cached is not None:
            logger.debug("Prompt cache hit — skipping provider calls")
            return cached

    errors: list[str] = []

    # ── 1. Groq: primary model then fallbacks ─────────────────────────────────
    if settings.groq_api_key:
        for gmodel in [settings.groq_model] + _GROQ_EXTRA_MODELS:
            try:
                result = await _call_groq(system, user, max_tokens, gmodel)
                if gmodel != settings.groq_model:
                    logger.info("Groq fallback succeeded: %s", gmodel)
                if use_cache:
                    _prompt_cache.set(system, user, result)
                return result
            except RateLimitError:
                errors.append(f"Groq/{gmodel}: 429 rate-limited")
                logger.warning("Groq/%s: 429 rate-limited — trying next model", gmodel)
            except APIStatusError as e:
                status = getattr(e, "status_code", 0)
                if status in (400, 413, 422):
                    errors.append(f"Groq/{gmodel}: HTTP {status}")
                    logger.warning("Groq/%s: HTTP %s — trying next model", gmodel, status)
                else:
                    errors.append(f"Groq/{gmodel}: HTTP {status}")
                    logger.warning("Groq/%s: HTTP %s — trying NVIDIA", gmodel, status)
                    break
            except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
                errors.append(f"Groq/{gmodel}: {type(e).__name__}")
                logger.warning("Groq/%s: %s — trying NVIDIA", gmodel, e)
                break
    else:
        errors.append("Groq: no API key")

    # ── 2. NVIDIA / DeepSeek — fallback ──────────────────────────────────────
    if settings.nvidia_api_key:
        try:
            result = await _call_nvidia(system, user, max_tokens)
            if use_cache:
                _prompt_cache.set(system, user, result)
            return result
        except NvidiaRateLimitError:
            errors.append("NVIDIA/DeepSeek: 429 rate-limited")
            logger.warning("NVIDIA/DeepSeek: 429 rate-limited — trying OpenRouter")
        except NvidiaAPIStatusError as e:
            status = getattr(e, "status_code", 0)
            errors.append(f"NVIDIA/DeepSeek: HTTP {status}")
            logger.warning("NVIDIA/DeepSeek: HTTP %s — trying OpenRouter", status)
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            errors.append(f"NVIDIA/DeepSeek: {type(e).__name__}: {e}")
            logger.warning("NVIDIA/DeepSeek: %s — trying OpenRouter", e)
    else:
        errors.append("NVIDIA: no API key")

    # ── 3. MiniMax M2.7 via NVIDIA — separate key, 8k context ────────────────
    if settings.nvidia_minimax_api_key:
        try:
            result = await _call_minimax(system, user, max_tokens)
            logger.info("MiniMax M2.7 succeeded")
            if use_cache:
                _prompt_cache.set(system, user, result)
            return result
        except NvidiaRateLimitError:
            errors.append("MiniMax/M2.7: 429 rate-limited")
            logger.warning("MiniMax/M2.7: 429 rate-limited — trying OpenRouter")
        except NvidiaAPIStatusError as e:
            status = getattr(e, "status_code", 0)
            errors.append(f"MiniMax/M2.7: HTTP {status}")
            logger.warning("MiniMax/M2.7: HTTP %s — trying OpenRouter", status)
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            errors.append(f"MiniMax/M2.7: {type(e).__name__}: {e}")
            logger.warning("MiniMax/M2.7: %s — trying OpenRouter", e)
    else:
        errors.append("MiniMax: no API key")

    # ── 5. OpenRouter: primary then 3 free fallbacks ──────────────────────────
    if settings.openrouter_api_key:
        for ormodel in [settings.openrouter_model] + _OPENROUTER_EXTRA_MODELS:
            try:
                logger.info("Trying OpenRouter model: %s", ormodel)
                result = await _call_openrouter(system, user, max_tokens, ormodel)
                if use_cache:
                    _prompt_cache.set(system, user, result)
                return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    errors.append(f"OpenRouter/{ormodel}: rate-limited")
                    logger.warning("OpenRouter/%s: rate-limited — trying next model", ormodel)
                    continue
                errors.append(f"OpenRouter/{ormodel}: HTTP {e.response.status_code}")
                break
            except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
                errors.append(f"OpenRouter/{ormodel}: {type(e).__name__}")
                logger.error("OpenRouter/%s error: %s", ormodel, e)
                break
    else:
        errors.append("OpenRouter: no API key")

    summary = " | ".join(errors)
    logger.error("All AI providers exhausted: %s", summary)
    return {"error": "AI temporarily unavailable — all providers busy. Try again in a few minutes."}


# ── Helper: pre-compute derived metrics ──────────────────────────────────────

def _pct_off_high(q: dict):
    hi, price = q.get("week52_high"), q.get("current_price")
    if isinstance(hi, (int, float)) and isinstance(price, (int, float)) and hi:
        return round((price - hi) / hi * 100, 2)
    return None

def _pct_above_low(q: dict):
    lo, price = q.get("week52_low"), q.get("current_price")
    if isinstance(lo, (int, float)) and isinstance(price, (int, float)) and lo:
        return round((price - lo) / lo * 100, 2)
    return None

def _pct(v) -> str | None:
    """Convert a decimal like 0.145 → '14.5%'. Returns None if not a number."""
    if isinstance(v, (int, float)):
        return f"{round(v * 100, 1)}%"
    return None

def _crore(v) -> str | None:
    """Convert raw INR market cap to ₹ Crore string."""
    if isinstance(v, (int, float)) and v:
        cr = v / 1e7
        if cr >= 1_00_000:
            return f"₹{cr/1_00_000:.2f} Lakh Cr"
        if cr >= 1_000:
            return f"₹{round(cr):,} Cr"
        return f"₹{cr:.0f} Cr"
    return None

def _rsi_zone(rsi) -> str:
    if not isinstance(rsi, (int, float)):
        return "N/A"
    if rsi < 30:
        return f"{rsi:.1f} — Oversold (potential bounce zone)"
    if rsi > 70:
        return f"{rsi:.1f} — Overbought (may pull back)"
    return f"{rsi:.1f} — Neutral (no extreme signal)"

def _peg(q: dict) -> str | None:
    pe = q.get("pe_ratio")
    eg = q.get("earnings_growth")
    if isinstance(pe, (int, float)) and isinstance(eg, (int, float)) and eg > 0:
        peg = pe / (eg * 100)
        label = "attractive" if peg < 1 else ("fair" if peg < 2 else "stretched")
        return f"{peg:.2f} ({label}; <1 = undervalued for growth)"
    return None

def _build_context(quote: dict, hist: dict, sentiment: dict, signals: list[str]) -> dict:
    """Pre-compute all derived metrics so the AI explains rather than calculates."""
    price  = quote.get("current_price")
    hi52   = quote.get("week52_high")
    lo52   = quote.get("week52_low")
    rsi    = hist.get("latest_rsi")
    pos    = sentiment.get("positive", 0)
    neg    = sentiment.get("negative", 0)
    total  = pos + neg
    sent_ratio = f"{pos}/{total} positive" if total else "N/A"

    return {
        # Identity
        "company":      quote.get("company_name"),
        "ticker":       quote.get("ticker"),
        "sector":       quote.get("sector"),
        "industry":     quote.get("industry"),
        "market_cap":   _crore(quote.get("market_cap")),

        # Price & 52W range
        "current_price_inr":    f"₹{price:,.2f}" if isinstance(price, (int, float)) else None,
        "week52_high_inr":      f"₹{hi52:,.2f}"  if isinstance(hi52, (int, float))  else None,
        "week52_low_inr":       f"₹{lo52:,.2f}"  if isinstance(lo52, (int, float))  else None,
        "pct_below_52w_high":   f"{_pct_off_high(quote)}% (distance from peak)"  if _pct_off_high(quote) else None,
        "pct_above_52w_low":    f"{_pct_above_low(quote)}% (recovery from trough)" if _pct_above_low(quote) else None,

        # Valuation ratios
        "pe_ratio":             quote.get("pe_ratio"),
        "forward_pe":           quote.get("forward_pe"),
        "pb_ratio":             quote.get("pb_ratio"),
        "peg_ratio":            _peg(quote),
        "eps_inr":              quote.get("eps"),
        "dividend_yield":       _pct(quote.get("dividend_yield")),

        # Profitability
        "roe":                  _pct(quote.get("roe")),
        "profit_margin":        _pct(quote.get("profit_margin")),
        "revenue_growth_yoy":   _pct(quote.get("revenue_growth")),
        "earnings_growth_yoy":  _pct(quote.get("earnings_growth")),

        # Balance sheet
        "debt_to_equity":       quote.get("debt_to_equity"),

        # Technicals
        "rsi_14":               _rsi_zone(rsi),
        "period_return":        f"{hist.get('pct_change'):.1f}%" if isinstance(hist.get("pct_change"), (int, float)) else None,
        "annualised_volatility": f"{hist.get('volatility_pct'):.1f}%" if isinstance(hist.get("volatility_pct"), (int, float)) else None,

        # Sentiment
        "news_sentiment":       sentiment.get("label"),
        "news_ratio":           sent_ratio,

        # Pre-flagged signals
        "analyst_signals":      signals,
    }


# ── 1. Stock analysis ─────────────────────────────────────────────────────────

_AI_CACHE_TTL_HOURS = 20  # regenerate analysis once per day


async def analyse_stock(quote: dict, signals: list[str], hist: dict, sentiment: dict) -> dict:
    from app.services import cache_service
    ticker = quote.get("ticker", "unknown")
    cache_key = f"analyse_stock:{ticker}"
    if (cached := await cache_service.get(cache_key, ttl_hours=_AI_CACHE_TTL_HOURS)) is not None:
        logger.info("AI analysis cache hit: %s", ticker)
        return cached

    ctx = _build_context(quote, hist, sentiment, signals)

    system = """You are a senior equity research analyst at a top Indian brokerage (think Motilal Oswal, HDFC Securities).
You are writing a detailed research note for a RETAIL INVESTOR who may be new to investing.

MANDATORY RULES:
1. Every statement MUST cite the exact number from the data. NEVER say "the stock has high valuations" — say "P/E of 24.5x vs typical sector range of 15-20x = 22% premium".
2. Convert all ratios to plain English: ROE of 0.18 = "earns ₹18 for every ₹100 of investor money".
3. Always compare to benchmarks: P/E vs sector, ROE vs 15% threshold, D/E vs 1.0 safe limit, RSI vs 30/70 levels.
4. Risks and positives must be 5-6 bullet points each — specific, numbered, data-backed.
5. plain_summary = 3 clear sentences a first-time investor can understand. No jargon.
6. bull_case and bear_case = concrete scenarios with numbers and catalysts.
7. what_to_watch = 4 specific triggers to monitor (earnings dates, RSI levels, debt paydown, margin trends).
8. key_metrics = exactly 8 entries covering: P/E, P/B, ROE, Revenue Growth, Profit Margin, D/E, RSI, and 52W Position.
   For each metric: explain what the number means in plain English in "explanation" field.
   signal must be: "good" | "warn" | "bad" | "neutral"
9. valuation_grade: A (very cheap), B (cheap), C (fair), D (expensive), F (very expensive).

Respond ONLY with this JSON (no markdown fences, no extra keys):
{
  "verdict": "Undervalued | Fairly valued | Overvalued | Mixed",
  "verdict_reason": "One sharp sentence explaining the verdict with numbers",
  "confidence": "High | Medium | Low",
  "valuation_grade": "A | B | C | D | F",
  "plain_summary": "3 plain sentences for a first-time investor — what company does, current financial state, bottom line on whether it looks attractive",
  "valuation": "4-5 sentences. Compare P/E to sector, discuss P/B and book value, assess ROE quality, comment on PEG if available, state whether valuation is justified by growth. Use exact numbers throughout.",
  "key_metrics": [
    { "label": "P/E Ratio", "value": "...", "context": "Sector avg / threshold", "signal": "good|warn|bad|neutral", "explanation": "Plain English: what this number means for the investor" },
    { "label": "P/B Ratio", "value": "...", "context": "...", "signal": "...", "explanation": "..." },
    { "label": "ROE", "value": "...", "context": "Good: >15%", "signal": "...", "explanation": "For every ₹100 of investor money, company earns ₹..." },
    { "label": "Revenue Growth", "value": "...", "context": "Strong: >10%", "signal": "...", "explanation": "..." },
    { "label": "Profit Margin", "value": "...", "context": "Varies by sector", "signal": "...", "explanation": "Out of every ₹100 in sales, company keeps ₹... as profit" },
    { "label": "Debt / Equity", "value": "...", "context": "Safe: <1.0", "signal": "...", "explanation": "For every ₹1 of equity, company has borrowed ₹..." },
    { "label": "RSI (14-day)", "value": "...", "context": "Oversold <30, Overbought >70", "signal": "...", "explanation": "..." },
    { "label": "52W Position", "value": "...", "context": "...", "signal": "...", "explanation": "..." }
  ],
  "risks": [
    "Risk 1 — cite specific number and explain why it matters",
    "Risk 2 — ...",
    "Risk 3 — ...",
    "Risk 4 — ...",
    "Risk 5 — ..."
  ],
  "positives": [
    "Positive 1 — cite specific number",
    "Positive 2 — ...",
    "Positive 3 — ...",
    "Positive 4 — ..."
  ],
  "bull_case": "2-3 sentences: If everything goes right — what catalyst, what upside, what the path looks like",
  "bear_case": "2-3 sentences: If things go wrong — what triggers the decline, what the downside risk is",
  "outlook": "3-4 sentences on near-term price momentum, technical setup (RSI, distance from 52W high/low), news sentiment direction, and what the next 3-6 months may look like",
  "what_to_watch": [
    "Specific trigger or metric to monitor — e.g. 'Next quarterly earnings: watch if revenue growth sustains above 10%'",
    "...",
    "...",
    "..."
  ]
}"""

    user = json.dumps(ctx, default=str)
    result = await _chat_json(system, user, max_tokens=2800)
    if "error" not in result:
        await cache_service.set(cache_key, result, model=settings.groq_model)
    return result


# ── 2. Company health diagnosis ───────────────────────────────────────────────

async def diagnose_health(quote: dict, hist: dict, sentiment: dict, articles: list[dict]) -> dict:
    from app.services import cache_service
    ticker = quote.get("ticker", "unknown")
    cache_key = f"health:{ticker}"
    if (cached := await cache_service.get(cache_key, ttl_hours=_AI_CACHE_TTL_HOURS)) is not None:
        logger.info("Health cache hit: %s", ticker)
        return cached

    ctx = _build_context(quote, hist, sentiment, [])

    system = """You are a forensic financial analyst. Diagnose this company's financial health like a doctor examining a patient.
Be direct. Do not sugarcoat. Do not be vague.

RULES:
1. Every concern and positive MUST include the exact number and what it means.
2. concerns = 5-6 items. Include margin trends, debt level, growth trajectory, RSI signal, and news tone.
3. positives = 4-5 items. Only include if data genuinely supports it.
4. red_flags = 0-3 items. Only truly alarming issues (D/E > 2, negative margins, revenue contraction, RSI > 80).
5. summary = 3-4 sentences in plain retail-investor English.
6. financial_health_score = 1-10 (10 = pristine balance sheet, strong growth, low debt; 1 = on the brink).
7. status_reason = one sentence explaining why you chose that status.

Respond ONLY with this JSON (no markdown):
{
  "status": "Healthy | Stable | Under pressure | Distressed",
  "status_reason": "One sentence with the primary reason for this rating",
  "financial_health_score": 7,
  "summary": "3-4 plain sentences — current financial state, trajectory, key concern or strength, and what retail investor should know",
  "concerns": [
    "Specific concern with exact number and impact",
    "...",
    "...",
    "...",
    "..."
  ],
  "positives": [
    "Specific positive with exact number",
    "...",
    "...",
    "..."
  ],
  "red_flags": [
    "Only truly alarming issues here — or leave empty array if none"
  ]
}"""

    ctx["recent_headlines"] = [a["title"] for a in articles[:10]]
    user = json.dumps(ctx, default=str)
    result = await _chat_json(system, user, max_tokens=1800)
    if "error" not in result:
        await cache_service.set(cache_key, result, model=settings.groq_model)
    return result


# ── 3. Grounded Q&A ───────────────────────────────────────────────────────────

async def answer(
    question: str,
    quote: dict | None,
    hist: dict | None,
    articles: list[dict] | None = None,
) -> dict:
    grounding: dict = {}
    if quote:
        grounding = {
            "company_name": quote.get("company_name"),
            "ticker": quote.get("ticker"),
            "sector": quote.get("sector"),
            "industry": quote.get("industry"),
            "current_price_inr": quote.get("current_price"),
            "previous_close_inr": quote.get("previous_close"),
            "day_high_inr": quote.get("day_high"),
            "day_low_inr": quote.get("day_low"),
            "week52_high_inr": quote.get("week52_high"),
            "week52_low_inr": quote.get("week52_low"),
            "market_cap_inr": quote.get("market_cap"),
            "pe_ratio": quote.get("pe_ratio"),
            "forward_pe": quote.get("forward_pe"),
            "pb_ratio": quote.get("pb_ratio"),
            "eps": quote.get("eps"),
            "roe": quote.get("roe"),
            "debt_to_equity": quote.get("debt_to_equity"),
            "profit_margin": quote.get("profit_margin"),
            "revenue_growth": quote.get("revenue_growth"),
            "earnings_growth": quote.get("earnings_growth"),
            "dividend_yield": quote.get("dividend_yield"),
            "beta": quote.get("beta"),
            "volume_today": quote.get("volume"),
            "avg_volume_3mo": quote.get("avg_volume"),
            "float_shares": quote.get("float_shares"),
            "shares_outstanding": quote.get("shares_outstanding"),
            "held_by_insiders_pct": quote.get("held_by_insiders_pct"),
            "held_by_institutions_pct": quote.get("held_by_institutions_pct"),
            "short_ratio": quote.get("short_ratio"),
            "current_leadership": quote.get("officers"),
            "company_summary": quote.get("summary"),
        }
        if hist:
            grounding["return_pct_3mo"] = hist.get("pct_change")
            grounding["rsi_14"] = hist.get("latest_rsi")
            grounding["annualised_volatility_pct"] = hist.get("volatility_pct")

        # Institutional & insider data (may be absent for Indian stocks)
        if quote.get("institutional_holders"):
            grounding["top_institutional_holders"] = quote["institutional_holders"]
        if quote.get("mutualfund_holders"):
            grounding["top_mutualfund_holders"] = quote["mutualfund_holders"]
        if quote.get("insider_transactions"):
            grounding["recent_insider_transactions"] = quote["insider_transactions"]

        if articles:
            grounding["recent_news"] = [
                {
                    "title": a["title"],
                    "publisher": a.get("publisher", ""),
                    "sentiment_score": a.get("sentiment", 0),
                }
                for a in articles[:12]
            ]

        # Inject IndianAPI live-market context (price, targets, announcements)
        ticker = quote.get("ticker") if quote else None
        if ticker:
            try:
                from app.services.indianapi_service import get_stock
                bare = ticker.replace(".NS", "").replace(".BO", "")
                idata = await get_stock(bare)
                if idata and idata.get("current_price"):
                    price = idata["current_price"]
                    chg   = idata.get("change_pct", 0) or 0
                    mc    = idata.get("market_cap")
                    mc_str = f"₹{mc/1e7:.0f}Cr" if mc else "N/A"
                    lines = [
                        f"=== Live Market Data (IndianAPI, INR) ===",
                        f"• {ticker}: ₹{price:,.2f} {'▲' if chg >= 0 else '▼'}{abs(chg):.2f}% | MCap {mc_str}",
                    ]
                    if idata.get("pe_ratio"):
                        lines.append(f"  P/E {idata['pe_ratio']:.1f}")
                    if idata.get("pb_ratio"):
                        lines.append(f"  P/B {idata['pb_ratio']:.2f}")
                    grounding["live_market_data"] = "\n".join(lines)
            except Exception:
                pass

            # Real NSE bulk/block deals for this ticker specifically — the
            # "top_institutional_holders"/"insider_transactions" fields below
            # are yfinance-era leftovers that IndianAPI never populates for
            # Indian stocks, so bulk-deal questions always fell through to
            # "not available" even though this exact data already powers
            # /api/market/bulk-deals elsewhere in the app.
            try:
                from app.services.bulk_deals_service import get_bulk_deals
                bare = ticker.replace(".NS", "").replace(".BO", "")
                all_deals = await get_bulk_deals(limit=75)
                deals = [d for d in all_deals if d.get("symbol") == bare][:10]
                if deals:
                    grounding["recent_bulk_deals"] = [
                        {
                            "date": d.get("date"),
                            "entity": d.get("entity"),
                            "deal_type": d.get("deal_type"),
                            "quantity": d.get("quantity"),
                            "price_inr": d.get("price"),
                            "value_cr": d.get("value_cr"),
                            "exchange": d.get("exchange"),
                        }
                        for d in deals
                    ]
            except Exception:
                pass

    system = """You are Aegis AI — a sharp, knowledgeable financial analyst assistant for Indian stock markets (NSE/BSE).

CONTEXT BLOCK: Live data fetched right now for this stock. Includes "live_market_data" — a real-time IndianAPI snapshot with live price, change, and market cap. Always prefer this over training memory for prices, ratios, ownership, and leadership.
TRAINING KNOWLEDGE: Background facts, sector context, historical events, general market mechanics up to early 2025.

HOW TO ANSWER:
1. PRICES / RATIOS / LEADERSHIP → Use CONTEXT only, cite exact numbers (e.g. "trading at ₹1,313 with a P/E of 22x").
2. BULK DEALS / INSTITUTIONAL ACTIVITY → Check "recent_bulk_deals" in CONTEXT first (real NSE/BSE bulk & block deals for this exact stock — entity, buy/sell, quantity, price, value in ₹Cr, date). Report them directly, e.g. "On {date}, {entity} {bought/sold} {quantity} shares at ₹{price} ({value_cr} Cr)." Also check "top_institutional_holders", "top_mutualfund_holders", "recent_insider_transactions" for additional ownership context. Only if "recent_bulk_deals" is absent or empty, say no bulk deals were reported in the recent window and direct the user to NSE's bulk deal page (www.nseindia.com > Market Data > Bulk Deals) or BSE's equivalent.
3. RECENT EVENTS (investments, acquisitions, partnerships) → Scan "recent_news" headlines first. If a headline matches, cite it with the publisher. Then add relevant training context.
4. QUESTIONS OUTSIDE THE DATA → Never say just "not available." Instead: (a) share everything relevant from the context, (b) use training knowledge for background, (c) tell the user exactly where to find the missing data (NSE/BSE website, company filings, SEBI disclosures, screener.in, etc.).
5. VOLUME ANALYSIS → Compare "volume_today" vs "avg_volume_3mo". If today's volume is >1.5x average, flag it as unusual activity.
6. ALWAYS cite specific numbers. Never give vague phrases like "the stock has shown mixed signals."
7. Answer in 4-6 sentences. End with: "Note: this is information, not investment advice."

Respond ONLY with JSON: { "answer": "string", "confidence": "High | Medium | Low" }
Confidence: High = direct data available. Medium = partial data + training. Low = mostly training/inference."""

    user = json.dumps({"question": question, "context": grounding}, default=str)
    return await _chat_json(system, user, max_tokens=900)


# ── 4. Document analysis ──────────────────────────────────────────────────────

_DOC_CACHE_TTL = 4 * 3600  # 4 hours — same PDF content returns cached result


def _doc_cache_key(text: str, model: str) -> str:
    return "doc:analysis:" + hashlib.sha256((text[:9000] + model).encode()).hexdigest()[:20]


_DOC_ANALYSIS_SYSTEM = """You are an elite Indian equity research analyst. Analyze the given financial document (concall transcript, annual report, or earnings release) and extract key insights for retail investors. Ground every point in the document — never hallucinate numbers.

Rules: cite all figures exactly as written (₹ Cr, %, bps). management_promises must be verbatim or near-verbatim. suggested_questions must be things the document does NOT fully answer.

Respond ONLY with valid JSON (no markdown fences):
{"executive_summary":"4-5 sentences: document type, period, performance narrative, key retail investor takeaway","document_type":"Concall transcript|Annual report|Investor presentation|Earnings release|Other","company_name":"string or null","period":"e.g. Q4 FY25","key_themes":["theme1","theme2","theme3","theme4","theme5"],"financial_highlights":["Revenue: figure+YoY growth","PAT: figure+margin","EBITDA: figure+margin+bps change","key ratio","cashflow highlight"],"margin_analysis":{"gross_margin":"X% (±Ybps or N/A)","ebitda_margin":"X% (±Ybps or N/A)","pat_margin":"X% (±Ybps or N/A)","margin_commentary":"2 sentences on drivers and management target"},"revenue_breakdown":["Segment: figure+share+growth or N/A"],"key_management_quotes":["verbatim/near-verbatim quote 1","quote 2","quote 3"],"management_promises":[{"commitment":"exact promise","timeline":"by when","metric":"measurable target"}],"risks_and_concerns":["risk 1 with data","risk 2","risk 3"],"strategic_initiatives":["initiative with capex/timeline details"],"guidance":"exact forward guidance or null","capex_guidance":"capex amount/timeline/purpose or null","sentiment":"Positive|Cautiously optimistic|Neutral|Cautious|Negative","sentiment_reason":"one sentence with evidence","suggested_questions":["probing q1","q2","q3","q4","q5","q6"]}"""


async def analyze_document(text: str, company: str | None = None, model: str = "deepseek") -> dict:
    """Deep analysis of an uploaded concall transcript / annual report / investor presentation."""
    model = model.lower()

    # ── Redis doc cache — same PDF + model → instant result, no API call ────
    cache_key = _doc_cache_key(text, model)
    try:
        from app.core.cache import cache as _redis_cache
        hit = _redis_cache.get(cache_key)
        if hit:
            logger.debug("Doc cache hit: %s", cache_key)
            return hit
    except Exception:
        pass

    # ── Semaphore — queue excess concurrent requests, never let them all pile ─
    async with _doc_semaphore():
        user = f"Company context: {company or 'Extract from document'}\n\n--- DOCUMENT START ---\n{text[:9000]}\n--- DOCUMENT END ---"
        system = _DOC_ANALYSIS_SYSTEM

        # In-process prompt cache (same request within 20h window)
        cached = _prompt_cache.get(system, user)
        if cached is not None:
            return cached

        def _save(result: dict) -> dict:
            _prompt_cache.set(system, user, result)
            try:
                from app.core.cache import cache as _rc
                _rc.set(cache_key, result, ttl=_DOC_CACHE_TTL)
            except Exception:
                pass
            return result

        # ── Detailed: Qwen3-32B — reasoning model, best quality ─────────────
        if model == "deepseek":
            try:
                logger.info("analyze_document: Qwen3-32B (reasoning)")
                result = await _call_groq(system, user, max_tokens=3500, model="qwen/qwen3-32b")
                return _save(result)
            except Exception as e:
                logger.warning("analyze_document: Qwen3-32B failed (%s) — falling back", e)

        # ── Standard: Llama-4-Scout — fast, newer model ──────────────────────
        elif model == "minimax":
            try:
                logger.info("analyze_document: Llama-4-Scout (standard)")
                result = await _call_groq(system, user, max_tokens=3000,
                                          model="meta-llama/llama-4-scout-17b-16e-instruct")
                return _save(result)
            except Exception as e:
                logger.warning("analyze_document: Llama-4-Scout failed (%s) — falling back", e)

        # ── Quick / fallback: llama-3.3-70b ──────────────────────────────────
        result = await _chat_json(system, user, max_tokens=3000)
        if "error" not in result:
            _save(result)
        return result


async def ask_document(text: str, question: str, company: str | None = None) -> dict:
    """Answer a specific question about an uploaded document, grounded in the document text."""
    system = """You are an expert equity analyst answering questions about a company document.

RULES:
1. Base your answer ONLY on the document provided. Do not hallucinate facts.
2. If the answer IS in the document: give a detailed, specific answer with exact quotes or numbers.
3. If the answer is PARTIALLY in the document: answer what you can, clearly flag what's missing.
4. If the answer is NOT in the document: say so clearly, then suggest where to find it.
5. Answers should be 3-6 sentences. Lead with the direct answer, then add context.
6. Quote directly from the document when possible (use quotes marks).

Respond ONLY with valid JSON:
{
  "answer": "Detailed answer with quotes or specific references from the document",
  "confidence": "High | Medium | Low",
  "source_context": "Relevant excerpt or section from document supporting the answer, or null"
}"""

    user = json.dumps({
        "company": company or "Unknown",
        "question": question,
        "document": text,
    }, default=str)
    return await _chat_json(system, user, max_tokens=900)


async def review_portfolio(context: str) -> dict:
    """Structured portfolio review — an overall verdict plus 3-4 typed
    observations, each with a reasoned insight and a concrete action.
    Uncached — "Run again" should genuinely re-run, not replay."""
    system = """You are a seasoned Indian equity portfolio reviewer writing a short, sharp review.
Given a retail investor's portfolio snapshot, return STRICT JSON:
{"verdict": "<one-sentence overall read of this portfolio — honest, specific, max 25 words>",
 "observations": [
  {"severity": "risk" | "opportunity" | "neutral",
   "title": "<the specific issue or strength, max 10 words>",
   "insight": "<2-3 sentences of reasoning: WHY this matters for THIS portfolio, using its actual numbers (weights, P&L, XIRR). Max 55 words>",
   "action": "<one concrete next step, starting with a verb, max 22 words>"}
]}
RULES:
1. 3 or 4 observations, most important first, covering different angles
   (concentration, laggards, winners, benchmark gap, missing sectors...).
2. Be specific — name stocks/sectors and quote the snapshot's numbers.
3. Interpret, don't restate: explain consequences and trade-offs.
4. The verdict should read like a human reviewer's opening line, not a summary of fields.
5. No disclaimers, no extra keys, no markdown."""
    result = await _chat_json(system, context, max_tokens=900, use_cache=False)

    verdict = str(result.get("verdict") or "").strip() or None
    obs = result.get("observations")
    if not isinstance(obs, list):
        return {"verdict": verdict, "observations": []}
    clean = []
    for o in obs[:4]:
        if not isinstance(o, dict):
            continue
        sev = o.get("severity")
        title = str(o.get("title") or "").strip()
        insight = str(o.get("insight") or "").strip()
        action = str(o.get("action") or "").strip()
        if title and action:
            clean.append({
                "severity": sev if sev in ("risk", "opportunity", "neutral") else "neutral",
                "title": title,
                "insight": insight,
                "action": action,
            })
    return {"verdict": verdict, "observations": clean}


async def ask_portfolio(question: str, context: str) -> dict:
    """Portfolio-grounded Q&A: the user's holdings snapshot IS the grounding.
    Returns {"answer": str, "followups": [str, str]}. Uncached — the
    snapshot is live data, so every ask deserves a fresh model pass."""
    system = """You are Aegis, a portfolio assistant for an Indian retail investor.
You will get PORTFOLIO SNAPSHOT (the investor's real holdings) and QUESTION.
Return STRICT JSON: {"answer": "<answer>", "followups": ["<q1>", "<q2>"]}
RULES:
1. Ground every claim in the snapshot — quote its exact numbers (₹, %, weights).
2. Answer the question directly in 2-5 sentences. Specific > generic.
3. If the snapshot can't answer it, say exactly what data is missing, then
   answer what you can from general Indian-market knowledge, clearly labelled.
4. Indian conventions: ₹, lakh/crore, NSE/BSE, LTCG/STCG where relevant.
5. "followups": 2 short natural next questions THIS investor would ask (max 8 words each).
6. No markdown, no disclaimers."""
    user = f"PORTFOLIO SNAPSHOT:\n{context}\n\nQUESTION: {question}"
    result = await _chat_json(system, user, max_tokens=700, use_cache=False)
    answer = str(result.get("answer") or "").strip()
    followups = [str(f).strip() for f in (result.get("followups") or []) if str(f).strip()][:2]
    if not answer:
        return {"answer": None, "followups": []}
    return {"answer": answer, "followups": followups}
