"""/api/chat — free-form Indian stock market chat (ChatGPT-style, no ticker required)."""

from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter
from pydantic import BaseModel

from app.services import ai_service, stock_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

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

_TICKER_RE = re.compile(r"\b([A-Z][A-Z0-9&-]{1,14})\.(NS|BO)\b")


def _extract_tickers(text: str) -> list[str]:
    """Find stock tickers in the user's own message — used to fetch live
    grounding data BEFORE generation, so the model has real numbers to cite
    instead of reaching for "approximate" ones from memory."""
    found: list[str] = []
    for m in _TICKER_RE.finditer(text):
        t = f"{m.group(1)}.{m.group(2)}"
        if t not in found:
            found.append(t)
    lower = text.lower()
    for name, ticker in _NAME_TO_TICKER.items():
        if name in lower and ticker not in found:
            found.append(ticker)
    return found[:3]


def _change_pct(q: dict) -> float | None:
    price, prev = q.get("current_price"), q.get("previous_close")
    if isinstance(price, (int, float)) and isinstance(prev, (int, float)) and prev:
        return round((price - prev) / prev * 100, 2)
    return None


async def _fetch_grounding(tickers: list[str]) -> dict[str, dict]:
    """Live quote data for tickers mentioned in the current message."""
    if not tickers:
        return {}
    quotes = await asyncio.gather(*[stock_service.get_quote(t) for t in tickers], return_exceptions=True)
    out: dict[str, dict] = {}
    for ticker, q in zip(tickers, quotes):
        if isinstance(q, BaseException) or ("error" in q and "current_price" not in q):
            continue
        out[ticker] = {
            "company_name": q.get("company_name"),
            "sector": q.get("sector"),
            "current_price_inr": q.get("current_price"),
            "change_pct": _change_pct(q),
            "week52_high_inr": q.get("week52_high"),
            "week52_low_inr": q.get("week52_low"),
            "pe_ratio": q.get("pe_ratio"),
            "pb_ratio": q.get("pb_ratio"),
            "roe": q.get("roe"),
            "debt_to_equity": q.get("debt_to_equity"),
            "market_cap_inr": q.get("market_cap"),
        }
    return out


def _stock_card(ticker: str, quote: dict | None) -> dict:
    symbol = ticker.replace(".NS", "").replace(".BO", "")
    if quote:
        return {
            "ticker": ticker,
            "symbol": symbol,
            "name": quote.get("company_name", ""),
            "price": quote.get("current_price_inr"),
            "change_pct": quote.get("change_pct"),
            "pe": quote.get("pe_ratio"),
            "source": "live",
        }
    return {"ticker": ticker, "symbol": symbol, "price": None, "source": "stub"}


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class StocksRequest(BaseModel):
    tickers: list[str]


@router.post("")
async def chat(req: ChatRequest):
    tickers = _extract_tickers(req.message)
    grounding = await _fetch_grounding(tickers)

    history_lines = [
        f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content}"
        for msg in req.history[-12:]
    ]
    result = await ai_service.chat(req.message, "\n".join(history_lines), grounding)

    if "error" in result:
        return {"reply": "Sorry, I encountered an error. Please try again shortly.", "error": True}

    # Stock cards for tickers already grounded before generation are free (no
    # extra fetch). Tickers the *reply* mentions but weren't grounded yet are
    # returned as bare tickers — the client resolves those via POST
    # /api/chat/stocks in the background so a cache-miss quote lookup never
    # blocks the reply itself from reaching the user.
    reply_tickers = [t for t in result.get("tickers", []) if t not in grounding][:6]
    stocks = [_stock_card(t, grounding[t]) for t in grounding]
    stocks += [_stock_card(t, None) for t in reply_tickers]

    return {
        "reply": result["reply"],
        "suggestions": result.get("suggestions", []),
        "stocks": stocks,
        "answered_from_facts": result.get("answered_from_facts"),
    }


@router.post("/stocks")
async def chat_stocks(req: StocksRequest):
    """Resolve stock cards for tickers a chat reply mentioned. Split out from
    the main /api/chat call so a slow/cache-miss quote lookup never blocks
    the reply text from reaching the user (see chat() above)."""
    tickers = req.tickers[:6]
    grounding = await _fetch_grounding(tickers)
    return {"stocks": [_stock_card(t, grounding.get(t)) for t in tickers]}
