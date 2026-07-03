"""
concall_service.py — generates AI concall summaries from quarterly financials.

Uses yfinance quarterly income statement, balance sheet, and cashflow.
Sends structured data to Groq to produce plain-English summaries for
each of the last 4 quarters, as if synthesizing a management concall.
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date as _date
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import yfinance as yf

from app.services.stock_service import normalise_ticker, _clean
from app.services import cache_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
_pool = ThreadPoolExecutor(max_workers=4)

_CONCALL_TTL_HOURS = 20  # quarterly data barely changes — regenerate once a day


# ── helpers ───────────────────────────────────────────────────────────────────

def _fy_label(date: pd.Timestamp) -> str:
    """Convert a quarter end date to Indian FY label like Q2 FY25."""
    m, y = date.month, date.year
    if m >= 4:
        fy = y + 1
        q = (m - 4) // 3 + 1
    else:
        fy = y
        q = 4
    return f"Q{q} FY{str(fy)[2:]}"


def _safe(df: pd.DataFrame, row: str, col) -> float | None:
    try:
        if row not in df.index:
            return None
        val = df.loc[row, col]
        return None if pd.isna(val) else float(val)
    except Exception:
        return None


def _cr(v: float | None) -> str | None:
    """Format a raw INR value to Crores string."""
    if v is None:
        return None
    return f"₹{v / 1e7:,.2f} Cr"


# ── quarterly data fetch ──────────────────────────────────────────────────────

def _fetch_sync(ticker: str) -> dict:
    from app.core.yf_session import yf_blocked, yf_on_rate_limit
    from yfinance.exceptions import YFRateLimitError
    t = normalise_ticker(ticker)
    if yf_blocked():
        return {"error": "yfinance rate-limited — try again later"}
    try:
        stock = yf.Ticker(t)
        info = stock.info or {}
        company = info.get("longName") or info.get("shortName") or t.replace(".NS", "")
        sector = info.get("sector", "")

        income = stock.quarterly_income_stmt
        balance = stock.quarterly_balance_sheet
        cashflow = stock.quarterly_cashflow

        if income is None or income.empty:
            return {"error": "No quarterly financial data available for this stock on Yahoo Finance."}

        # Take up to 8 columns to allow YoY comparison (4 current + 4 prior year)
        all_cols = list(income.columns)
        # Skip quarters that haven't ended yet (period_end > today)
        today = _date.today()
        all_cols = [c for c in all_cols if pd.Timestamp(c).date() <= today]
        recent_cols = all_cols[:4]
        prior_cols = all_cols[4:8] if len(all_cols) >= 8 else []

        quarters: list[dict] = []
        for i, col in enumerate(recent_cols):
            date = pd.Timestamp(col)
            label = _fy_label(date)

            rev = _safe(income, "Total Revenue", col)
            gross = _safe(income, "Gross Profit", col)
            op_inc = _safe(income, "Operating Income", col)
            net = _safe(income, "Net Income", col)
            ebitda = _safe(income, "EBITDA", col)
            interest = _safe(income, "Interest Expense", col)
            tax = _safe(income, "Tax Provision", col)

            total_debt = _safe(balance, "Total Debt", col) if balance is not None and not balance.empty else None
            equity = (
                _safe(balance, "Stockholders Equity", col) or _safe(balance, "Common Stock Equity", col)
                if balance is not None and not balance.empty else None
            )
            ocf = _safe(cashflow, "Operating Cash Flow", col) if cashflow is not None and not cashflow.empty else None
            capex = _safe(cashflow, "Capital Expenditure", col) if cashflow is not None and not cashflow.empty else None

            q: dict = {
                "label": label,
                "period_end": date.strftime("%Y-%m-%d"),
                "revenue_raw": rev,
                "net_income_raw": net,
                "revenue": _cr(rev),
                "gross_profit": _cr(gross),
                "operating_income": _cr(op_inc),
                "net_income": _cr(net),
                "ebitda": _cr(ebitda),
                "interest_expense": _cr(interest),
                "tax": _cr(tax),
                "gross_margin_pct": round(gross / rev * 100, 1) if rev and gross else None,
                "operating_margin_pct": round(op_inc / rev * 100, 1) if rev and op_inc else None,
                "net_margin_pct": round(net / rev * 100, 1) if rev and net else None,
                "total_debt": _cr(total_debt),
                "equity": _cr(equity),
                "operating_cashflow": _cr(ocf),
                "capex": _cr(capex),
                "free_cashflow": _cr((ocf or 0) + (capex or 0)) if ocf else None,
            }

            # YoY comparison with same quarter last year
            if i < len(prior_cols):
                pcol = prior_cols[i]
                prev_rev = _safe(income, "Total Revenue", pcol)
                prev_net = _safe(income, "Net Income", pcol)
                prev_op = _safe(income, "Operating Income", pcol)
                if prev_rev and rev:
                    q["revenue_yoy_pct"] = round((rev - prev_rev) / abs(prev_rev) * 100, 1)
                if prev_net and net:
                    q["net_income_yoy_pct"] = round((net - prev_net) / abs(prev_net) * 100, 1)
                if prev_op and op_inc:
                    q["op_income_yoy_pct"] = round((op_inc - prev_op) / abs(prev_op) * 100, 1)
                q["prev_revenue"] = _cr(prev_rev)
                q["prev_net_income"] = _cr(prev_net)

            quarters.append(q)

        return _clean({"company": company, "sector": sector, "quarters": quarters})

    except YFRateLimitError as e:
        yf_on_rate_limit()
        return {"error": "yfinance rate-limited — try again later"}
    except Exception as e:
        logger.error("concall fetch error %s: %s", ticker, e)
        return {"error": str(e)}


async def _fetch_quarterly(ticker: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_pool, _fetch_sync, ticker)


# ── Earnings news per quarter ─────────────────────────────────────────────────

def _fetch_quarter_news_sync(company: str, label: str) -> list[str]:
    """Fetch news headlines about a specific quarterly result from Google News RSS."""
    # e.g. label = "Q2 FY25" → search for "Reliance Q2 FY25 results concall"
    queries = [
        f'"{company}" {label} results',
        f'"{company}" quarterly earnings {label}',
        f'"{company}" concall {label}',
    ]
    headlines = []
    seen: set[str] = set()
    for q in queries:
        try:
            url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in (feed.entries or [])[:8]:
                title = (entry.get("title") or "").strip()
                if title and title[:60] not in seen:
                    seen.add(title[:60])
                    headlines.append(title)
        except Exception:
            pass
    return headlines[:15]


async def _fetch_all_quarter_news(company: str, labels: list[str]) -> dict[str, list[str]]:
    """Fetch earnings news for each quarter label concurrently."""
    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(_pool, _fetch_quarter_news_sync, company, lbl) for lbl in labels]
    )
    return {lbl: news for lbl, news in zip(labels, results)}


# ── AI summarisation ──────────────────────────────────────────────────────────

async def _ai_summarise(company: str, sector: str, quarters: list[dict], news_map: dict[str, list[str]]) -> list[dict]:
    from app.services.ai_service import _chat_json

    # Attach news to each quarter before sending
    for q in quarters:
        q["earnings_news_headlines"] = news_map.get(q["label"], [])

    system = """You are a senior equity research analyst synthesizing quarterly earnings for Indian retail investors.

You have TWO sources of truth per quarter:
1. FINANCIAL DATA — actual audited numbers (revenue, profit, margins, cashflow, YoY changes)
2. EARNINGS NEWS HEADLINES — real articles from the results week capturing management quotes, analyst reactions, forward guidance

YOUR MOST IMPORTANT TASK: Extract specific commitments and promises management made on the concall (from news headlines). These are promises like revenue targets, margin improvement timelines, capex plans, debt reduction pledges, new product launches, capacity additions, or geographic expansion. Retail investors need to track whether management delivered on promises.

For each quarter produce these fields:
- "headline": One sharp sentence capturing the quarter's story (numbers first, e.g. "Revenue +18% YoY but PAT margin compressed 200bps to 12.3%")
- "summary": 5-7 sentences. Must cite exact numbers from data. Cover: topline growth %, PAT trend, margin direction with bps change, cashflow quality, and what drove results. Reference news headlines where they add context.
- "key_numbers": object with exactly 4 most important metrics {"Revenue": "₹X Cr", "PAT": "₹Y Cr", "PAT Margin": "Z%", "Revenue YoY": "+X%"}
- "highlights": 4-5 specific positives (numbers mandatory — e.g. "Gross margin expanded 180bps QoQ to 38.2% driven by product mix")
- "concerns": 3-4 specific concerns (numbers mandatory — e.g. "D/E at 1.8x elevated; interest cost up 22% YoY to ₹340 Cr")
- "management_commentary": 2-3 sentences on what management said. PRIORITIZE direct quotes or paraphrased comments from news headlines. Cover what they attributed results to.
- "management_promises": Array of 3-5 specific forward commitments management made. FORMAT: "By [when]: [what was promised] — [source/context]". Examples: "By Q2 FY26: Revenue target of ₹5,000 Cr", "FY27: EBITDA margin target of 22%+", "Next quarter: ₹800 Cr capex for new plant". If news doesn't mention promises, infer logical guidance from data trends.
- "guidance_note": One sentence on what to watch in the next quarter (specific metric + threshold)
- "analyst_view": One sentence on how analysts/market reacted (from news, or null if unavailable)

Tone: direct, data-first, no vague language. Cite exact numbers always.
Do NOT hallucinate numbers not in the data or headlines. If no news is available, base analysis on financial data only.

Respond ONLY with valid JSON (no markdown fences):
{ "summaries": [ { "label": "Q2 FY25", "headline": "...", "summary": "...", "key_numbers": {}, "highlights": [...], "concerns": [...], "management_commentary": "...", "management_promises": ["...", "..."], "guidance_note": "...", "analyst_view": "..." }, ... ] }"""

    user = json.dumps(
        {"company": company, "sector": sector, "quarters": quarters},
        default=str,
    )
    result = await _chat_json(system, user, max_tokens=4000)
    if "error" in result:
        logger.warning("Concall AI error: %s", result["error"])
        return []
    return result.get("summaries", [])


# ── public API ────────────────────────────────────────────────────────────────

async def get_concall_summary(ticker: str) -> dict:
    key = f"concall2:{normalise_ticker(ticker)}"

    # L1+L2 persistent cache — saves Groq quota; quarterly data changes every ~3 months
    if (cached := await cache_service.get(key, ttl_hours=_CONCALL_TTL_HOURS)) is not None:
        logger.info("concall cache hit: %s", key)
        return cached

    data = await _fetch_quarterly(ticker)
    if "error" in data:
        return data

    labels = [q["label"] for q in data["quarters"]]

    # 1. Fetch earnings news for all quarters in parallel
    news_map = await _fetch_all_quarter_news(data["company"], labels)

    # 2. Generate AI summaries using financial data + real news context
    summaries = await _ai_summarise(data["company"], data["sector"], data["quarters"], news_map)

    # Merge AI summaries back into quarter data
    summary_map = {s["label"]: s for s in summaries if isinstance(s, dict)}
    for q in data["quarters"]:
        ai = summary_map.get(q["label"], {})
        q["headline"] = ai.get("headline")
        q["summary"] = ai.get("summary")
        q["key_numbers"] = ai.get("key_numbers", {})
        q["highlights"] = ai.get("highlights", [])
        q["concerns"] = ai.get("concerns", [])
        q["management_commentary"] = ai.get("management_commentary")
        q["management_promises"] = ai.get("management_promises", [])
        q["guidance_note"] = ai.get("guidance_note")
        q["analyst_view"] = ai.get("analyst_view")
        q["news_headlines"] = news_map.get(q["label"], [])

    result = {"company": data["company"], "sector": data["sector"], "quarters": data["quarters"]}
    # Persist to DB — next call within 20h skips AI entirely
    await cache_service.set(key, result, model="groq-waterfall")
    return result
