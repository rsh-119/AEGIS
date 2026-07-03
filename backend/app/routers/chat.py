"""/api/chat — free-form Indian stock market chat (ChatGPT-style, no ticker required)."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter
from pydantic import BaseModel
from groq import AsyncGroq

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/chat", tags=["chat"])

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq | None:
    global _client
    if not settings.groq_api_key:
        return None
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client


_SYSTEM = """\
You are Aegis AI — an expert Indian stock market analyst and financial research assistant.

Your deep knowledge covers:
- NSE (National Stock Exchange) and BSE (Bombay Stock Exchange) listed companies
- All major Indian indices: Nifty 50, Sensex, Bank Nifty, Nifty IT, Nifty Pharma, Nifty Midcap, Nifty Smallcap
- SEBI regulations, RBI monetary policy, Indian budget impacts
- FII/DII flows, promoter holdings, institutional activity
- Indian taxation: STCG (15%), LTCG (10% above ₹1 lakh), STT, dividend tax
- IPOs, QIPs, rights issues, buybacks in Indian markets
- Sector rotation, global macro impact on Indian markets
- Fundamental analysis: P/E, P/B, ROE, ROCE, D/E for Indian companies
- Technical analysis: support/resistance, moving averages, RSI, MACD
- Mutual funds, index ETFs (Nifty BeES, Sensex ETF), SIPs
- Corporate governance, concall insights, promoter pledging
- Top Indian companies across Technology, Banking, FMCG, Pharma, Auto, Infra, Energy

Response guidelines:
- Be direct, concise, and data-driven
- Use ₹ for Indian Rupee amounts
- Use bullet points and **bold** for section titles — do NOT use # ## ### heading syntax
- Distinguish between facts and analysis/opinion
- For stock-specific advice, remind users this is educational, not financial advice
- When asked about specific stocks, give balanced bull/bear perspectives
- Cite approximate figures when exact real-time data isn't available
- Keep responses conversational — avoid document-style structure with multiple heading levels

You MUST respond ONLY with a valid JSON object (no markdown fences, no extra text):
{
  "reply": "<your full markdown-formatted answer>",
  "suggestions": ["<follow-up question 1>", "<follow-up question 2>", "<follow-up question 3>"],
  "tickers": ["<NSE_SYMBOL.NS>"]
}

Rules for the JSON fields:
- "reply": your complete answer in markdown
- "suggestions": exactly 3 natural follow-up questions the user might ask next, based on your reply
- "tickers": NSE symbols (e.g. "HDFCBANK.NS", "INFY.NS") for any specific stocks you mentioned — max 6, empty array if none
"""

# Common company name → NSE ticker mapping for fast resolution
_NAME_TO_TICKER: dict[str, str] = {
    "hdfc bank": "HDFCBANK.NS", "hdfcbank": "HDFCBANK.NS",
    "infosys": "INFY.NS", "infy": "INFY.NS",
    "tcs": "TCS.NS", "tata consultancy": "TCS.NS",
    "reliance": "RELIANCE.NS", "ril": "RELIANCE.NS",
    "icici bank": "ICICIBANK.NS", "icicibank": "ICICIBANK.NS",
    "sbi": "SBIN.NS", "state bank": "SBIN.NS",
    "wipro": "WIPRO.NS",
    "hcl tech": "HCLTECH.NS", "hcltech": "HCLTECH.NS",
    "l&t": "LT.NS", "larsen": "LT.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "kotak": "KOTAKBANK.NS", "kotak bank": "KOTAKBANK.NS",
    "axis bank": "AXISBANK.NS",
    "itc": "ITC.NS",
    "hindustan unilever": "HINDUNILVR.NS", "hul": "HINDUNILVR.NS",
    "asian paints": "ASIANPAINT.NS",
    "maruti": "MARUTI.NS", "maruti suzuki": "MARUTI.NS",
    "tata motors": "TATAMOTORS.NS",
    "sun pharma": "SUNPHARMA.NS",
    "nestle": "NESTLEIND.NS",
    "ultratech": "ULTRACEMCO.NS",
    "titan": "TITAN.NS",
    "adani ports": "ADANIPORTS.NS",
    "bharti airtel": "BHARTIARTL.NS", "airtel": "BHARTIARTL.NS",
    "ntpc": "NTPC.NS",
    "power grid": "POWERGRID.NS",
    "ongc": "ONGC.NS",
    "coal india": "COALINDIA.NS",
    "tech mahindra": "TECHM.NS",
    "tata steel": "TATASTEEL.NS",
    "jsw steel": "JSWSTEEL.NS",
    "hindalco": "HINDALCO.NS",
    "dr reddy": "DRREDDY.NS",
    "cipla": "CIPLA.NS",
    "divis": "DIVISLAB.NS",
    "bajaj auto": "BAJAJ-AUTO.NS",
    "hero motocorp": "HEROMOTOCO.NS",
    "eicher": "EICHERMOT.NS",
    "indusind bank": "INDUSINDBK.NS",
}


def _lookup_stocks(tickers: list[str]) -> list[dict]:
    """Fetch stock data from cache for tickers mentioned in the reply."""
    from app.services.stream_service import price_cache
    from app.core.cache import cache

    results = []
    seen: set[str] = set()

    for ticker in tickers[:6]:
        if ticker in seen:
            continue
        seen.add(ticker)

        # Try price cache first (real-time stream data)
        tick = price_cache.get(ticker)
        if tick:
            results.append({
                "ticker":     ticker,
                "symbol":     ticker.replace(".NS", "").replace(".BO", ""),
                "price":      tick.get("price"),
                "change_pct": tick.get("change_pct"),
                "source":     "live",
            })
            continue

        # Try quote cache
        cached_q = cache.get(f"quote:{ticker}")
        if cached_q and isinstance(cached_q, dict):
            results.append({
                "ticker":     ticker,
                "symbol":     ticker.replace(".NS", "").replace(".BO", ""),
                "name":       cached_q.get("company_name", ""),
                "price":      cached_q.get("current_price"),
                "change_pct": cached_q.get("change_pct"),
                "pe":         cached_q.get("pe_ratio"),
                "source":     "cache",
            })
            continue

        # No data available — include ticker stub so frontend can link to stock page
        results.append({
            "ticker": ticker,
            "symbol": ticker.replace(".NS", "").replace(".BO", ""),
            "price":  None,
            "change_pct": None,
            "source": "stub",
        })

    return results


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@router.post("")
async def chat(req: ChatRequest):
    client = _get_client()
    if client is None:
        return {"reply": "AI is not configured. Please set GROQ_API_KEY.", "error": True}

    messages: list[dict] = [{"role": "system", "content": _SYSTEM}]
    for msg in req.history[-12:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=0.4,
                max_tokens=2000,
                response_format={"type": "json_object"},
            ),
            timeout=30,
        )
        raw = resp.choices[0].message.content or "{}"

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: extract reply from raw text if JSON is malformed
            parsed = {"reply": raw, "suggestions": [], "tickers": []}

        reply       = parsed.get("reply") or parsed.get("text") or raw
        suggestions = parsed.get("suggestions") or []
        tickers     = parsed.get("tickers") or []

        # Clamp to 3 suggestions, strip empty strings
        suggestions = [s for s in suggestions if isinstance(s, str) and s.strip()][:3]

        # Resolve any tickers that are just company names
        resolved: list[str] = []
        for t in tickers:
            if isinstance(t, str):
                t = t.strip()
                if t.endswith(".NS") or t.endswith(".BO"):
                    resolved.append(t)
                else:
                    mapped = _NAME_TO_TICKER.get(t.lower())
                    if mapped:
                        resolved.append(mapped)

        stocks = _lookup_stocks(resolved) if resolved else []

        return {
            "reply":       reply,
            "suggestions": suggestions,
            "stocks":      stocks,
        }

    except asyncio.TimeoutError:
        return {"reply": "Request timed out. Please try again.", "error": True}
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        return {"reply": "Sorry, I encountered an error. Please try again shortly.", "error": True}
