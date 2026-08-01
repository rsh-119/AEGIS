"""
ai_service.py — Multi-provider AI for Indian stock analysis.

Provider chain (automatic waterfall — each step tried only if prior step fails).
`prefer_openrouter=True` tasks (Ask AI, portfolio/document Q&A) try step 5 FIRST,
then fall through to the same chain from step 1 on failure:
  0. Prompt cache (20h TTL) — returns instantly for repeated calls
  1. Groq    llama-3.3-70b-versatile              (primary — 100k TPD free, low latency)
  2. Groq    llama-3.1-8b-instant                 (fallback #1 — 500k TPD)
  5. OpenRouter  settings.openrouter_model         (nvidia/nemotron-3-super-120b-a12b:free)
     OpenRouter  nvidia/nemotron-3-ultra-550b-a55b:free
     OpenRouter  google/gemma-4-31b-it:free
     OpenRouter  nvidia/nemotron-3-nano-30b-a3b:free
  6. NVIDIA  settings.nvidia_model (z-ai/glm-5.2)  (last resort — correct but ~1-3 min queue)

Verified 2026-08-01 by direct per-model test (see /api/health or ask Claude to
re-run it): GLM-5.2 is the most groundedness-accurate but far slower (~80s)
than Groq's primary model (~4s, nearly as accurate) — Groq staying primary is
the right call. Previously-listed "Groq specdec / llama-4-scout" and "NVIDIA
MiniMax M2.7" fallback steps were removed — all three now return hard errors
(decommissioned / 404 / EOL) from their providers, not real fallback capacity.

Four capabilities:
  • analyse_stock()    — valuation, risks, outlook (structured, data-cited)
  • diagnose_health()  — "what's going wrong" over recent quarters
  • answer()           — grounded Q&A with live context injection
  • analyze_document() — deep concall / annual report analysis
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import re
import time

import httpx
from groq import AsyncGroq, RateLimitError, APIStatusError
from openai import AsyncOpenAI
from openai import RateLimitError as NvidiaRateLimitError, APIStatusError as NvidiaAPIStatusError
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.services.prompts import analysis as _p_analysis
from app.services.prompts import health as _p_health
from app.services.prompts import ask as _p_ask
from app.services.prompts import chat as _p_chat
from app.services.prompts import document as _p_document
from app.services.prompts import portfolio as _p_portfolio

logger   = logging.getLogger(__name__)
settings = get_settings()

# ── Sampling — tuned per task, not per provider ──────────────────────────────
# Previously each provider hardcoded its own temperature (Groq/OpenRouter 0.15,
# MiniMax 0.3, NVIDIA 0.6/top_p 0.95) — so the same task landed on wildly
# different sampling depending purely on which provider answered the call,
# and NVIDIA's 0.6 was a real outlier for fact-citation-heavy JSON. _chat_json
# now takes an explicit per-task temperature and passes it to whichever
# provider ends up serving the request, so sampling is consistent regardless
# of where in the waterfall the answer came from.
_TEMP_STRUCTURED    = 0.2   # fact-grounded JSON: analysis, health, Ask AI, document Q&A
_TEMP_CONVERSATIONAL = 0.35  # portfolio review/Q&A — uncached, meant to read naturally
                             # run-to-run, but still grounded in the injected snapshot

# ── Waterfall observability — in-memory, process-lifetime counters ──────────
# Deliberately not Prometheus/Grafana (no metrics infra exists elsewhere in
# this codebase) — just enough visibility to answer "which provider is
# actually serving traffic" and "how often does schema validation fail" via
# a debug endpoint, without standing up new infrastructure.
_provider_stats: dict[str, dict[str, float]] = {}
_repair_counts:  dict[str, int] = {}


def _record_call(provider: str, latency_s: float) -> None:
    s = _provider_stats.setdefault(provider, {"calls": 0, "total_latency_s": 0.0})
    s["calls"] += 1
    s["total_latency_s"] += latency_s


def _record_repair(schema_name: str) -> None:
    _repair_counts[schema_name] = _repair_counts.get(schema_name, 0) + 1


def get_provider_stats() -> dict:
    """Calls served and average latency per provider since process start."""
    return {
        provider: {
            "calls": int(s["calls"]),
            "avg_latency_s": round(s["total_latency_s"] / s["calls"], 2) if s["calls"] else 0.0,
        }
        for provider, s in _provider_stats.items()
    }


def get_repair_counts() -> dict:
    """How many times each response schema needed the one-shot repair retry."""
    return dict(_repair_counts)


_groq_client:     AsyncGroq   | None = None
_nvidia_client:   AsyncOpenAI | None = None

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
    # "llama-3.3-70b-specdec" and "meta-llama/llama-4-scout-17b-16e-instruct"
    # were removed 2026-08-01 — both now hard-fail (decommissioned / 404) on
    # every call, verified by direct per-model test. Don't re-add a model here
    # without confirming it still resolves on Groq's console first.
]

# OpenRouter free fallbacks
_OPENROUTER_EXTRA_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
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

async def _call_nvidia(system: str, user: str, max_tokens: int, model: str | None = None, temperature: float | None = None) -> dict:
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
            temperature=temperature if temperature is not None else _TEMP_STRUCTURED,
            top_p=0.9,
            max_tokens=max_tokens,
            # DeepSeek-only knob; GLM and other NVIDIA models reject/ignore it
            extra_body=(
                {"chat_template_kwargs": {"thinking": True, "reasoning_effort": "high"}}
                if "deepseek" in (model or settings.nvidia_model)
                else None
            ),
            stream=False,
        ),
        timeout=max(settings.ai_timeout_seconds, 180),
    )
    content = resp.choices[0].message.content
    return _parse_json(content)



# ── Groq call ─────────────────────────────────────────────────────────────────

async def _call_groq(system: str, user: str, max_tokens: int, model: str | None = None, temperature: float | None = None) -> dict:
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
            temperature=temperature if temperature is not None else _TEMP_STRUCTURED,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        ),
        timeout=settings.ai_timeout_seconds,
    )
    return _parse_json(resp.choices[0].message.content)


# ── OpenRouter call ───────────────────────────────────────────────────────────

async def _call_openrouter(system: str, user: str, max_tokens: int, model: str | None = None, temperature: float | None = None) -> dict:
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not configured")
    _model = model or settings.openrouter_model
    payload = {
        "model": _model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": temperature if temperature is not None else _TEMP_STRUCTURED,
        "max_tokens":  max_tokens,
        "response_format": {"type": "json_object"},
        # Nemotron free models emit a separate `reasoning` stream that burns the
        # max_tokens budget — answers truncate (finish_reason=length) or come
        # back empty. Disable it; models without the switch simply ignore this.
        "reasoning": {"enabled": False},
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

def _repair_prompt(user: str, errors: str) -> str:
    return (
        f"{user}\n\n---\nYour previous JSON response failed schema validation:\n{errors}\n"
        "Return corrected JSON only — every required field present, matching the exact"
        " types and enum values requested. No markdown, no commentary."
    )


async def _call_validated(
    call_fn, system: str, user: str, max_tokens: int, schema: type[BaseModel] | None,
    temperature: float = _TEMP_STRUCTURED,
) -> dict:
    """Run one provider call at the task's tuned `temperature` and validate its
    JSON against `schema` if given. On a validation failure, retry exactly once
    at temperature=0 (independent of the task temperature — a repair pass wants
    the most deterministic output possible) with the validation errors appended
    to the prompt. If the repair also fails validation, the ValidationError
    propagates — the waterfall's existing except-Exception handling in each
    provider block treats that exactly like any other provider failure and
    moves on to the next one."""
    result = await call_fn(system, user, max_tokens, temperature=temperature)
    if schema is None:
        return result
    try:
        schema.model_validate(result)
        return result
    except ValidationError as e:
        _record_repair(schema.__name__)
        logger.warning("%s failed schema validation — repairing once at temp=0: %s", schema.__name__, e)
        result = await call_fn(system, _repair_prompt(user, str(e)), max_tokens, temperature=0.0)
        schema.model_validate(result)  # raises again if still broken -> caller moves to next provider
        return result


async def _openrouter_attempt(
    system: str, user: str, max_tokens: int, use_cache: bool, errors: list[str],
    schema: type[BaseModel] | None = None, temperature: float = _TEMP_STRUCTURED,
) -> dict | None:
    """Try OpenRouter primary + free fallbacks; None if all fail."""
    if not settings.openrouter_api_key:
        errors.append("OpenRouter: no API key")
        return None
    for ormodel in [settings.openrouter_model] + _OPENROUTER_EXTRA_MODELS:
        try:
            logger.info("Trying OpenRouter model: %s", ormodel)
            call_fn = functools.partial(_call_openrouter, model=ormodel)
            result = await _call_validated(call_fn, system, user, max_tokens, schema, temperature)
            result.setdefault("_provider", f"openrouter/{ormodel}")
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
        except (asyncio.TimeoutError, json.JSONDecodeError, ValidationError, Exception) as e:
            errors.append(f"OpenRouter/{ormodel}: {type(e).__name__}")
            logger.error("OpenRouter/%s error: %s", ormodel, e)
            break
    return None


async def _chat_json(
    system: str, user: str, max_tokens: int = 1200,
    use_cache: bool = True, prefer_openrouter: bool = False,
    schema: type[BaseModel] | None = None, temperature: float = _TEMP_STRUCTURED,
) -> dict:
    """
    Multi-model waterfall — Groq (primary) → NVIDIA DeepSeek → OpenRouter.
    Prompt-level cache: identical (system, user) pairs return cached result
    within 20 hours without hitting any provider.
    Moves to the next provider on any error. Returns a dict; never raises.
    If `schema` is given, each provider's JSON is validated against it with
    one repair-retry (temperature=0) before being accepted; a response that
    still fails validation after the repair is treated as that provider
    failing, and the waterfall moves on to the next one.
    `temperature` is applied uniformly to whichever provider ends up serving
    the request — sampling is tuned per task (see _TEMP_STRUCTURED /
    _TEMP_CONVERSATIONAL), not left to whatever a given provider defaults to.
    """
    t0 = time.monotonic()

    # ── 0. Prompt cache — skip all providers for repeated calls.
    #    use_cache=False for live-data prompts (e.g. portfolio review/Q&A)
    #    where a fresh model call is expected every time. ─────────────────────
    if use_cache:
        cached = _prompt_cache.get(system, user)
        if cached is not None:
            logger.debug("Prompt cache hit — skipping provider calls")
            _record_call("cache", time.monotonic() - t0)
            return cached

    errors: list[str] = []
    openrouter_tried = False

    # ── 0.5 Preferred route: OpenRouter's Nemotron-120B leads for tasks that
    #    want detailed, context-grounded prose (Ask AI, portfolio/document Q&A);
    #    everything else keeps the fast Groq path. Falls through to the normal
    #    chain on failure. ────────────────────────────────────────────────────
    if prefer_openrouter:
        openrouter_tried = True
        result = await _openrouter_attempt(system, user, max_tokens, use_cache, errors, schema, temperature)
        if result is not None:
            _record_call(result.get("_provider", "openrouter"), time.monotonic() - t0)
            return result
        logger.warning("Preferred OpenRouter route failed — falling back to Groq chain")

    # ── 1. Groq — primary (fast path; GLM fallback is slow but capable) ──────
    if settings.groq_api_key:
        for gmodel in [settings.groq_model] + _GROQ_EXTRA_MODELS:
            try:
                call_fn = functools.partial(_call_groq, model=gmodel)
                result = await _call_validated(call_fn, system, user, max_tokens, schema, temperature)
                result.setdefault("_provider", f"groq/{gmodel}")
                if gmodel != settings.groq_model:
                    logger.info("Groq fallback succeeded: %s", gmodel)
                if use_cache:
                    _prompt_cache.set(system, user, result)
                _record_call(result["_provider"], time.monotonic() - t0)
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
                    logger.warning("Groq/%s: HTTP %s — trying NVIDIA/GLM", gmodel, status)
                    break
            except (asyncio.TimeoutError, json.JSONDecodeError, ValidationError, Exception) as e:
                errors.append(f"Groq/{gmodel}: {type(e).__name__}")
                logger.warning("Groq/%s: %s — trying NVIDIA/GLM", gmodel, e)
                break
    else:
        errors.append("Groq: no API key")

    # ── OpenRouter (skipped when the preferred route already tried it) ───────
    if not openrouter_tried:
        result = await _openrouter_attempt(system, user, max_tokens, use_cache, errors, schema, temperature)
        if result is not None:
            _record_call(result.get("_provider", "openrouter"), time.monotonic() - t0)
            return result

    # ── NVIDIA (GLM-5.2) — last resort: correct output but ~2-3 min queue ────
    if settings.nvidia_api_key:
        try:
            result = await _call_validated(_call_nvidia, system, user, max_tokens, schema, temperature)
            result.setdefault("_provider", f"nvidia/{settings.nvidia_model}")
            if use_cache:
                _prompt_cache.set(system, user, result)
            _record_call(result["_provider"], time.monotonic() - t0)
            return result
        except NvidiaRateLimitError:
            errors.append("NVIDIA: 429 rate-limited")
            logger.warning("NVIDIA: 429 rate-limited — giving up")
        except NvidiaAPIStatusError as e:
            status = getattr(e, "status_code", 0)
            errors.append(f"NVIDIA: HTTP {status}")
            logger.warning("NVIDIA: HTTP %s — giving up", status)
        except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
            errors.append(f"NVIDIA: {type(e).__name__}: {e}")
            logger.warning("NVIDIA: %s — giving up", e)
    else:
        errors.append("NVIDIA: no API key")


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

_NA = "Not available"

def _vs_sector_pct(stock_val, sector_val, label: str) -> str | None:
    """Precompute a 'X% premium/discount to sector median' string — the model
    must never estimate this comparison itself."""
    if not isinstance(stock_val, (int, float)) or not isinstance(sector_val, (int, float)) or not sector_val:
        return None
    diff_pct = round((stock_val / sector_val - 1) * 100, 1)
    if abs(diff_pct) < 1:
        return f"in line with sector median {label} of {sector_val}"
    direction = "premium to" if diff_pct > 0 else "discount to"
    return f"{abs(diff_pct)}% {direction} sector median {label} of {sector_val}"

def _vs_sector_pp(stock_val, sector_val, label: str) -> str | None:
    """Precompute a percentage-point gap for already-percentage metrics (ROE, margin, growth)."""
    if not isinstance(stock_val, (int, float)) or not isinstance(sector_val, (int, float)):
        return None
    gap_pp = round((stock_val - sector_val) * 100, 1)
    if abs(gap_pp) < 0.5:
        return f"in line with sector median {label} of {round(sector_val * 100, 1)}%"
    direction = "above" if gap_pp > 0 else "below"
    return f"{abs(gap_pp)}pp {direction} sector median {label} of {round(sector_val * 100, 1)}%"

def _fill_na(d: dict) -> dict:
    """Structural half of the grounding contract: any missing scalar becomes the
    literal string 'Not available' so the model has nothing left to estimate."""
    out = {}
    for k, v in d.items():
        if v is None:
            out[k] = _NA
        elif isinstance(v, dict):
            out[k] = _fill_na(v)
        else:
            out[k] = v
    return out

def _build_context(quote: dict, hist: dict, sentiment: dict, signals: list[str], peer_avg: dict | None = None) -> dict:
    """Pre-compute all derived metrics so the AI explains rather than calculates.
    Every comparison to a sector benchmark is computed here in Python — the model
    only ever restates a number it was handed, never infers or recalls one."""
    price  = quote.get("current_price")
    hi52   = quote.get("week52_high")
    lo52   = quote.get("week52_low")
    rsi    = hist.get("latest_rsi")
    pos    = sentiment.get("positive", 0)
    neg    = sentiment.get("negative", 0)
    total  = pos + neg
    sent_ratio = f"{pos}/{total} positive" if total else "N/A"

    peer_avg = peer_avg or {}
    sector_comparison = {
        "sector_median_pe":        peer_avg.get("pe_ratio"),
        "pe_vs_sector":            _vs_sector_pct(quote.get("pe_ratio"), peer_avg.get("pe_ratio"), "P/E"),
        "sector_median_pb":        peer_avg.get("pb_ratio"),
        "pb_vs_sector":            _vs_sector_pct(quote.get("pb_ratio"), peer_avg.get("pb_ratio"), "P/B"),
        "sector_median_roe":       _pct(peer_avg.get("roe")),
        "roe_vs_sector":           _vs_sector_pp(quote.get("roe"), peer_avg.get("roe"), "ROE"),
        "sector_median_margin":    _pct(peer_avg.get("profit_margin")),
        "margin_vs_sector":        _vs_sector_pp(quote.get("profit_margin"), peer_avg.get("profit_margin"), "profit margin"),
        "sector_median_rev_growth": _pct(peer_avg.get("revenue_growth")),
        "rev_growth_vs_sector":    _vs_sector_pp(quote.get("revenue_growth"), peer_avg.get("revenue_growth"), "revenue growth"),
        "sector_median_de":        peer_avg.get("debt_to_equity"),
        "de_vs_sector":            _vs_sector_pct(quote.get("debt_to_equity"), peer_avg.get("debt_to_equity"), "debt/equity"),
    }

    ctx = {
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

        # Balance sheet — stored as "debt is X% of equity" (100% = D/E ratio of 1.0)
        "debt_to_equity_pct":   f"{quote.get('debt_to_equity'):.0f}%" if isinstance(quote.get("debt_to_equity"), (int, float)) else None,

        # Technicals
        "rsi_14":               _rsi_zone(rsi),
        "period_return":        f"{hist.get('pct_change'):.1f}%" if isinstance(hist.get("pct_change"), (int, float)) else None,
        "annualised_volatility": f"{hist.get('volatility_pct'):.1f}%" if isinstance(hist.get("volatility_pct"), (int, float)) else None,

        # Sentiment
        "news_sentiment":       sentiment.get("label"),
        "news_ratio":           sent_ratio,

        # Sector benchmark — every comparison already computed in Python
        "sector_comparison":    sector_comparison,

        # Pre-flagged signals
        "analyst_signals":      signals,
    }
    return _fill_na(ctx)


# ── 1. Stock analysis ─────────────────────────────────────────────────────────

_AI_CACHE_TTL_HOURS = 20  # regenerate analysis once per day


async def analyse_stock(quote: dict, signals: list[str], hist: dict, sentiment: dict, peer_avg: dict | None = None) -> dict:
    from app.services import cache_service
    ticker = quote.get("ticker", "unknown")
    cache_key = f"analyse_stock:{ticker}:{_p_analysis.VERSION}"
    if (cached := await cache_service.get(cache_key, ttl_hours=_AI_CACHE_TTL_HOURS)) is not None:
        logger.info("AI analysis cache hit: %s", ticker)
        return cached

    ctx = _build_context(quote, hist, sentiment, signals, peer_avg)

    user = json.dumps(ctx, default=str)
    from app.schemas import AnalysisResponse
    result = await _chat_json(_p_analysis.SYSTEM, user, max_tokens=2800, schema=AnalysisResponse)
    if "error" not in result:
        await cache_service.set(cache_key, result, model=settings.groq_model)
    return result


# ── 2. Company health diagnosis ───────────────────────────────────────────────

async def diagnose_health(quote: dict, hist: dict, sentiment: dict, articles: list[dict], peer_avg: dict | None = None) -> dict:
    from app.services import cache_service
    ticker = quote.get("ticker", "unknown")
    cache_key = f"health:{ticker}:{_p_health.VERSION}"
    if (cached := await cache_service.get(cache_key, ttl_hours=_AI_CACHE_TTL_HOURS)) is not None:
        logger.info("Health cache hit: %s", ticker)
        return cached

    ctx = _build_context(quote, hist, sentiment, [], peer_avg)
    ctx["recent_headlines"] = [a["title"] for a in articles[:10]]
    user = json.dumps(ctx, default=str)
    from app.schemas import HealthResponse
    result = await _chat_json(_p_health.SYSTEM, user, max_tokens=1800, schema=HealthResponse)
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

    user = json.dumps({"question": question, "context": grounding}, default=str)
    from app.schemas import AskResponse
    return await _chat_json(_p_ask.ANSWER_SYSTEM, user, max_tokens=900, prefer_openrouter=True, schema=AskResponse)


# ── 3b. Free-form chat (no ticker required) ──────────────────────────────────

async def chat(message: str, history_text: str, grounding: dict) -> dict:
    """Free-form Indian stock-market chat. Grounded in live data for any stock
    mentioned in the current message (via `grounding`); conversational for
    general market questions that cite no stock-specific numbers."""
    parts = []
    if history_text:
        parts.append(f"CONVERSATION SO FAR:\n{history_text}")
    if grounding:
        parts.append(f"LIVE DATA (INR, use for any stock-specific numbers):\n{json.dumps(grounding, default=str)}")
    parts.append(f"CURRENT MESSAGE: {message}")
    user = "\n\n".join(parts)
    from app.schemas import ChatResponse
    return await _chat_json(_p_chat.SYSTEM, user, max_tokens=2000, prefer_openrouter=True, schema=ChatResponse)


# ── 4. Document analysis ──────────────────────────────────────────────────────

_DOC_CACHE_TTL = 4 * 3600  # 4 hours — same PDF content returns cached result


def _doc_cache_key(text: str, model: str) -> str:
    return "doc:analysis:" + hashlib.sha256((text[:9000] + model + _p_document.VERSION).encode()).hexdigest()[:20]


async def analyze_document(text: str, company: str | None = None, model: str = "deepseek") -> dict:
    """Deep analysis of an uploaded concall transcript / annual report / investor presentation."""
    model = model.lower()
    t0 = time.monotonic()

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
        from app.schemas import DocumentAnalysisResponse
        user = f"Company context: {company or 'Extract from document'}\n\n--- DOCUMENT START ---\n{text[:9000]}\n--- DOCUMENT END ---"
        system = _p_document.SYSTEM

        # In-process prompt cache — keyed on (system, user + model) so the two
        # named quality tiers can't collide and silently return each other's
        # cached result for the same document.
        cache_lookup_key = user + model
        cached = _prompt_cache.get(system, cache_lookup_key)
        if cached is not None:
            return cached

        def _save(result: dict) -> dict:
            _prompt_cache.set(system, cache_lookup_key, result)
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
                call_fn = functools.partial(_call_groq, model="qwen/qwen3-32b")
                result = await _call_validated(call_fn, system, user, 3500, DocumentAnalysisResponse, _TEMP_STRUCTURED)
                result.setdefault("_provider", "groq/qwen/qwen3-32b")
                _record_call(result["_provider"], time.monotonic() - t0)
                return _save(result)
            except Exception as e:
                logger.warning("analyze_document: Qwen3-32B failed (%s) — falling back", e)

        # ── Standard: Llama-3.1-8B — fast, low-latency ───────────────────────
        # "minimax" is a legacy tier id (frontend still sends it) — it never
        # actually called NVIDIA MiniMax. It previously called Groq's
        # llama-4-scout, which Groq has since dropped (404 on every call);
        # swapped for a model confirmed live 2026-08-01.
        elif model == "minimax":
            try:
                logger.info("analyze_document: Llama-3.1-8B (standard)")
                call_fn = functools.partial(_call_groq, model="llama-3.1-8b-instant")
                result = await _call_validated(call_fn, system, user, 3000, DocumentAnalysisResponse, _TEMP_STRUCTURED)
                result.setdefault("_provider", "groq/llama-3.1-8b-instant")
                _record_call(result["_provider"], time.monotonic() - t0)
                return _save(result)
            except Exception as e:
                logger.warning("analyze_document: Llama-3.1-8B failed (%s) — falling back", e)

        # ── Quick / fallback: llama-3.3-70b (full waterfall) ─────────────────
        result = await _chat_json(system, user, max_tokens=3000, schema=DocumentAnalysisResponse)
        if "error" not in result:
            _save(result)
        return result


async def ask_document(text: str, question: str, company: str | None = None) -> dict:
    """Answer a specific question about an uploaded document, grounded in the document text."""
    user = json.dumps({
        "company": company or "Unknown",
        "question": question,
        "document": text,
    }, default=str)
    from app.schemas import AskResponse
    return await _chat_json(_p_ask.ASK_DOCUMENT_SYSTEM, user, max_tokens=900, prefer_openrouter=True, schema=AskResponse)


async def review_portfolio(context: str) -> dict:
    """Structured portfolio review — an overall verdict plus 3-4 typed
    observations, each with a reasoned insight and a concrete action.
    Uncached — "Run again" should genuinely re-run, not replay."""
    result = await _chat_json(_p_portfolio.REVIEW_SYSTEM, context, max_tokens=900, use_cache=False, temperature=_TEMP_CONVERSATIONAL)

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
    user = f"PORTFOLIO SNAPSHOT:\n{context}\n\nQUESTION: {question}"
    result = await _chat_json(_p_portfolio.ASK_SYSTEM, user, max_tokens=900, use_cache=False, prefer_openrouter=True, temperature=_TEMP_CONVERSATIONAL)
    answer = str(result.get("answer") or "").strip()
    followups = [str(f).strip() for f in (result.get("followups") or []) if str(f).strip()][:2]
    if not answer:
        return {"answer": None, "followups": []}
    return {"answer": answer, "followups": followups}
